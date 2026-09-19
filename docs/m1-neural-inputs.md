# M1 图提取：统一神经网络输入

2026-09-19 核查并补齐。M1 的 `CircuitGraph → to_pyg()` 原本已经保留节点种类、尺寸及缺失 mask、端口角色/序号、正反向连接和参数组绑定，足够支撑现有 GT/RGCN/GAT。原 SAC 适配层也已将不同节点投影到统一 hidden_dim；没有发现需要重写 Spectre parser 的信息缺失。

缺口在于**直接向普通 PyG 算子导出**：原 device.x 的 8 列是参数，net.x 的 7 列是 net roles，不能将自动补齐宽度后的同一列视作同一种特征；原输出没有统一 `edge_attr`。此外，参数组与节点采用不同索引空间，普通 Data 的默认 batch 偏移不能代替自定义规则。

现在保留原有 `HeteroData`，增加 `graph/neural.py` 的 `circuit-neural-v1` 同构视图。支持本项目的 GCN、RGCN、GAT、Graph Transformer、port-GNN 和共享逐节点 MLP；后续网络可基于固定语义字段选用稀疏或稠密节点输入。

## 张量契约

设 N 为 device+net 节点数，E 为正反向端口边数，G 为独立参数组数，M 为组成员绑定数。默认 FeatureSchema 下：

| 字段 | 形状 / dtype | 含义 |
| --- | --- | --- |
| `x` | `[N,49]` / float32 | 固定列语义，见下表；缺失/类型不适用位置填有限零并保留 mask/type |
| `node_type` | `[N]` / int64 | 0=device，1=net |
| `edge_index` | `[2,E]` / int64 | 同一节点索引空间；每个端口保留正反向边，不 coalesce |
| `edge_type` | `[E]` / int64 | `2 * terminal_role_id + direction`，共 14 种关系 |
| `edge_ordinal` | `[E]` / int64 | 原端口序号，正反向一致 |
| `edge_attr` | `[E,15]` / float32 | 14 维 relation one-hot + `log1p(ordinal)` |
| `edge_weight` | `[E]` / float32 | 当前每条边权重为 1；不将类别编号当作数值权重 |
| `group_x` | `[G,3]` / float64 | 物理 value/lower/upper，沿用原单位；不是直接学习用的归一化特征 |
| `group_member_index` | `[2,M]` / int64 | 第一行为 group ID，第二行为全局节点 ID，成员须为 device |
| 其他 `group_*` | 同原 M1 契约 | kind、mutable、mask、绑定参数及比例；单位/合法域/写回身份在 metadata |

`node_feature_slices(schema)` 提供列映射；宽度随显式 FeatureSchema 变化，不随图大小变化：`2 + K_device + 4P + R_net`。默认列为：

| 范围 | 语义 |
| --- | --- |
| 0:2 | 节点类型 one-hot |
| 2:10 | 器件类别 one-hot；net 填零 |
| 10:18 | 参数 signed-log1p/value-reference |
| 18:26 | 参数值有效 mask |
| 26:34 | 参数存在 mask |
| 34:42 | 参数可调 mask |
| 42:49 | net roles multi-hot；device 填零 |

instance/net 名及 model ID 不进入 x。S/B 同网仍为两条不同类型的边；未知器件默认拒绝，仅显式 `allow_incomplete=True` 可导出诊断图。整数索引、有限数值、边方向、端口属性、schema 一致性和跨图组绑定均有校验。

## 调用方式

```python
from analog_optimizer.graph.neural import (
    to_homogeneous_pyg, batch_homogeneous, dense_node_features,
)
from torch_geometric.nn import GCNConv, GATConv, RGCNConv, TransformerConv

# graph_a/graph_b 来自现有 SpectreParser；不需要创建 RL Observation。
a = to_homogeneous_pyg(graph_a)
b = to_homogeneous_pyg(graph_b)
batch = batch_homogeneous([a, b])
F, D = batch.x.shape[1], batch.edge_attr.shape[1]

gcn = GCNConv(F, 32, cached=False)
gcn_nodes = gcn(batch.x, batch.edge_index, batch.edge_weight)
gat = GATConv(F, 8, heads=4, edge_dim=D, add_self_loops=False)
gat_nodes = gat(batch.x, batch.edge_index, batch.edge_attr)
rgcn = RGCNConv(F, 32, num_relations=D - 1)
rgcn_nodes = rgcn(batch.x, batch.edge_index, batch.edge_type)
gt = TransformerConv(F, 8, heads=4, edge_dim=D)
gt_nodes = gt(batch.x, batch.edge_index, batch.edge_attr)

dense_x, node_mask = dense_node_features(batch)  # [B,Nmax,F], [B,Nmax]
```

先逐图转换，再 `batch_homogeneous()`，保证每个图的节点连续。batch 提供节点 `batch/ptr` 和组 `group_x_batch/group_x_ptr`；自定义 CircuitData 对组编号加 G 偏移、对组成员节点编号加 N 偏移，unbatch 恢复原索引。schema 不同的图不能混 batch，即使宽度相同也拒绝。

`dense_node_features()` 不截断节点；padding 由布尔 node_mask 区分，attention/pooling 必须使用它，动作仍按独立参数组处理。可变大小 MLP 使用逐节点共享网络与组聚合；将整个 Nmax 展平进固定输出层不属于通用跨拓扑接口。

原 SAC 继续使用已有的 device/net 投影及组归一化，所有编码器共用这些输入处理。其端口边打包已改为复用 `port_edge_tensors()`，与 M1 同构导出使用同一关系编号、方向和 ordinal 规则，避免维护两套转换。稀疏训练 batch 的节点排列仍为所有 device 后接所有 net；导出 batch 按图连续排列。两者的索引必须随各自张量使用，不能交叉拼接。

SAC 已默认启用两层有界输入缓存：复用静态拓扑及同一历史观测的原始张量，动态内容变化时刷新，batch 偏移和网络前向仍每次执行。详见 [缓存接口与实测](input-tensor-cache.md)。

## 普通 GCN 与 RGCN

新增 `ModelConfig(encoder_type='gcn')`，训练/迁移 CLI 同样接受 `gcn`。它是 topology-only `GCNConv` 对照：使用连通性及多重边数量，忽略 relation/ordinal；保留 residual、LayerNorm、FFN、规格与动作绑定。使用 `cached=False`，避免将上一拓扑的归一化邻接误用于下一拓扑；模型块不加自环，由 residual 保留自身表示。[GCNConv 官方接口](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.GCNConv.html)

GCN 不等于 RGCN。RGCN 使用角色×方向关系，GAT/GT 使用端口边特征；选择普通 GCN 不会删除原始数据中的端口字段，其他编码器仍可读取。GT 保持默认，旧 M5 六方法默认设置保留。

## 验收证据

- 完整回归 **319 项通过，零失败、零跳过**：[JUnit](../artifacts/local/m1-neural-tests.xml)。
- 直接使用 M1 导出的张量驱动 GCN/GAT/RGCN/Transformer/MLP 的前向与反向，对比单图和混合 batch；覆盖 opamp、LDO、VCO、两级 opamp synthetic fixture，以及现有 GPDK045 OTA 导出网表快照。读取快照不运行 Spectre。
- 验证 S/B 同网不合并、缺失/未解析/真实零区分、零组/空图/custom schema、dense mask、跨图边/绑定拒绝、重命名/重排等变、动态尺寸刷新及 SAC 端口规则一致性。
- 六编码器 × scratch/frozen/adapt + 两个非 RL 基线，覆盖新规格及新拓扑 2→3 维动作；完成 **168 次 synthetic 评价、58 个 episode、40 个测试 run**。预训练/validation/test 分别为 36/12/120，全部恢复，新增真实调用 0：[report](../artifacts/local/m1-neural-smoke/42178da0581149389a68a290f066990b/report.json)。这是输入和流程验收，不是实际电路迁移优劣证据。

```bash
/tmp/analog-optimizer-venv/bin/python examples/netlist_demo.py \
  tests/fixtures/synthetic/opamp.scs --config configs/opamp.json --homogeneous
/tmp/analog-optimizer-venv/bin/python -m pytest -q -ra \
  --junitxml=artifacts/local/m1-neural-tests.xml
/tmp/analog-optimizer-venv/bin/python examples/benchmark_transfer.py \
  --encoders graph_transformer mlp rgcn gat gcn port_gnn \
  --seeds 17 --pretrain-steps 2 --test-steps 2 --max-calls 170 \
  --output artifacts/local/m1-neural-smoke
```

Parser、原 `to_pyg()` 接口、动作授权与 nominal-only 限制不变。checkpoint 延续代码/schema/配置严格校验；本次改码前的 checkpoint 不会自动迁移。
