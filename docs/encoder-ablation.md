# M6 前：可切换编码器与迁移对照

2026-09-19，按用户要求为 MLP、RGCN、GAT 与 Graph Transformer 的知识迁移比较接入统一接口。默认仍为 Graph Transformer；本次完成模型与实验入口改造，以及离线验收，不启动 M6 或新的真实仿真。

项目级 [analog-optimizer skill](../.agents/skills/analog-optimizer/SKILL.md) 及学习、实验、阶段参考已同步这些约定，并修正早期“当前止于 M3”的过期范围。后续维护以实际代码和本页验收记录核对 skill，避免将接口通过误写成迁移效果成立。

## 2026-10-06: two additional encoders

`graph_gps` and `group_cross_attention` are implemented alongside GT/RGCN/GATv2;
the default remains `graph_transformer`. Both share the existing parser, action
bindings and SAC heads. See [architecture, structural ablations, integration and
current comparison CLI](global-encoders.md). Their correctness tests are not
transfer-performance evidence; the historical experiments below retain their
original scope and results.

## 接口与模型定义

```python
from analog_optimizer.models import ModelConfig
from analog_optimizer.training.sac import SACLearner

learner = SACLearner(
    experiment={"origin": "synthetic", "split": "train", "designs": ["fixture"]},
    model_config=ModelConfig(encoder_type="rgcn", hidden_dim=32, heads=4, layers=2),
)
```

GATv1 (`gat`) was replaced by GATv2 (`gatv2`) on 2026-09-26. Old GAT configurations are refused, not aliased; train new weights. Historical results below remain GATv1 results.

`encoder_type` 现在仅可选 `graph_transformer`、`rgcn`、`gatv2`。`mlp` 和 `gcn` 已于 2026-09-26 按用户要求删除；`port_gnn` 已于 2026-09-24 删除。旧版本的测试数字和下文已删除架构的说明保留为历史记录，最新决定见 [项目决策](decisions.md)。删除前的 checkpoint 需要其对应的源码及依赖版本；MLP/GCN 最后可用源码为 `9bc488f`。`models/encoders.py` 的 `build_encoder()` 是 actor 和两个 critic 的共同构造入口。所有编码器遵循：

```text
encoder(GraphBatch, actions=None)
    → nodes:   [全部 device + net 节点数, hidden_dim]
    → groups:  [全部独立参数组数, hidden_dim]
    → context: [图数, hidden_dim]
```

输入特征/规格、参数组绑定、actor 输出头、critic 动作注入及 readout、SAC/replay/reward 共用实现；每个网络的权重独立。替换编码器不需要按新拓扑重建固定长度输出层。新增架构可在 `build_block()` 中加入对应节点处理块，并沿用此契约。

| 选择 | 节点处理 | 使用的连接信息 |
| --- | --- | --- |
| `graph_transformer` | `TransformerConv` 多头邻域注意力 + residual/LayerNorm/FFN | terminal role × direction 的 embedding 和 ordinal 特征进入 attention |
| ~~`mlp`~~（2026-09-26 删除） | 共享逐节点 MLP + residual/LayerNorm，随后使用共同参数组 readout | 忽略电路边、端口角色和 ordinal；保留器件特征、规格和参数组绑定 |
| `rgcn` | `RGCNConv` 逐关系 mean 消息 + residual/LayerNorm/FFN | 每个 terminal role × direction 是独立 relation；本实现不额外编码 ordinal |
| `gatv2` | `GATv2Conv` 动态多头邻域注意力 + residual/LayerNorm/FFN | role/direction/ordinal 特征在非线性之前进入 attention；source/target 投影独立；不生成虚构端口的 self-loop |
| ~~`port_gnn`~~（2026-09-24 删除） | M5 已有的端口 MLP 消息 + destination mean | role/direction/ordinal 参与 message |
| ~~`gcn`~~（2026-09-26 删除） | 普通 `GCNConv` + residual/LayerNorm/FFN，`cached=False` | 使用连通性及多重边数量；忽略端口标签/ordinal，原数据仍保留这些字段 |

MLP 是为可变节点数和动作数设计的无连接信息消融，**不是将固定拓扑展平的普通全连接策略**。actor 按绑定成员读取表示；critic 另外聚合所有节点和动作组。它检验这些输入下使用电路连接信息的收益，不能代表所有 MLP 设计的能力。

图算子的语义核对了本地 PyG 2.8.0.post1 源码及官方 [RGCNConv](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.RGCNConv.html)、[GATv2Conv](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.GATv2Conv.html) 文档。这里只是基于标准算子的项目实现，不宣称复现某篇论文完整模型。`heads` 仅控制 GT/GATv2；这两者要求 hidden_dim 能被 heads 整除。

## 迁移比较入口

```bash
# 三种保留编码器 × scratch/frozen/adapt，外加随机搜索与坐标搜索。
# 小预算 synthetic 接口验收，不是电路求解。
~/analog-optimizer-venv/bin/python examples/benchmark_transfer.py \
  --origin synthetic \
  --encoders graph_transformer rgcn gatv2 \
  --seeds 17 --pretrain-steps 2 --test-steps 2 --max-calls 120 \
  --output artifacts/local/encoder-ablation-smoke

# 只跑一个编码器的三种模式也受支持。
python examples/benchmark_transfer.py --encoders rgcn

# 单 learner 的训练/恢复入口同样可选编码器。
python examples/train_synthetic_sac.py --encoder rgcn
```

不传 `--encoders` 时仅运行 Graph Transformer 的三种模式及两种搜索基线。显式选择后，每种架构都有独立预训练、冻结 validation 诊断，以及下面三种测试模式；随机搜索与坐标搜索在每个任务/seed 中各执行一次。

- `scratch`：该架构随机初始化，从测试任务自己的空 replay 开始训练。
- `frozen`：复制同架构预训练权重，以确定性均值策略做固定预算多步评估；不更新权重、不收集训练 replay。初始测量与在线评价都计数，不称为无仿真推理。
- `adapt`：复制同架构预训练的 actor、Q、target Q 与 alpha，使用新的优化器和空 replay 微调；源模型保持不变。

用各架构自己的 frozen/adapt 与 scratch 比较迁移收益，再跨架构比较。不同架构之间不直接复制权重。train/validation/test 划分、seed、特征参考尺度、参数合法域、奖励、停止条件、在线步数和更新规则相同；每个架构有相同预训练采样预算，但其策略采集的候选可以不同，不声称使用了完全相同的数据集。

`--hidden-dim`、`--layers`、`--heads` 控制共同模型配置。默认同宽度/深度，**并未严格匹配参数量**。冻结协议、每个 run 和 checkpoint 均记录具体编码器与配置；报告记录 actor+Q1+Q2 参数数、预训练成本、在线成本、成功/删失、首次达标调用数及时间、best-so-far 质量。实际矩阵决定预算；超过 `--max-calls` 时在创建后端前拒绝执行。Use the budget calculated for the selected three-encoder matrix; account for GATv2's extra source/target projection parameters when comparing equal-width models.

## 兼容与恢复

- 原 `models.graph_transformer` 下的 `ModelConfig`、`GroupActor`、`GraphCritic` 和 `PortGraphEncoder` 导入仍保留，新的入口可直接从 `models` 导入。
- 旧 `attention_mode='local_port_attention'` 映射到 GT；`'port_message_passing'`（port-GNN）自 2026-09-24 起被拒绝并说明原因。新代码使用 `encoder_type`；同时指定且冲突时拒绝。
- checkpoint 保留既有的代码摘要、schema、配置和依赖严格匹配规则，并保存明确的 `encoder_type`；加载时需提供匹配的 `model_config`。每种编码器通过精确下一次更新恢复测试。
- 改码前的 M4/M5 checkpoint 因代码摘要/配置变化不会被当前代码无提示恢复。本次没有历史 checkpoint 迁移工具；旧实验产物未被修改。跨架构加载/权重迁移显式报错。
- 停用新对照只需不传 `--encoders`，训练默认仍为 GT；后端、动作权限和 nominal-only 限制不变。


GATv2 follows [Brody et al., ICLR 2022](https://arxiv.org/abs/2105.14491). At hidden 32 and four heads, each attention layer has 3,200 parameters versus the previous GATv1 layer's 2,176. `share_weights=False`, `add_self_loops=False` and the block's existing outer residual are explicit. Input features, goals, action binding and SAC stay unchanged. This is an implementation change, not evidence of better circuit optimization.

## 本次验收

完整离线回归 **296 项通过，零失败、零跳过**，记录见 [JUnit XML](../artifacts/local/encoder-ablation-tests.xml)。其中模型与迁移测试 98 项通过，涵盖五种编码器的混合拓扑 batch、重命名/重排等变性、有效动作熵、动作归属与梯度、独立权重、SAC/target 更新和精确 checkpoint 恢复。另验证 MLP 对删边/换端口不变，图模型对连接/端口变化敏感，错误架构与超预算在执行前拒绝。

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q -ra \
  --junitxml=artifacts/local/encoder-ablation-tests.xml
```

四架构 CLI smoke 完成 **116 次 synthetic 评价、40 个 episode、28 个测试 run**；预训练/validation/test 调用分别为 24/8/84，全部环境恢复，真实调用为 0。涵盖同拓扑新规格和同类新拓扑的 2→3 维动作。32 hidden、2 layers 下 actor+Q1+Q2 参数量为 GT 105476、MLP 72164、RGCN 158756、GAT 87044。

记录：[report.json](../artifacts/local/encoder-ablation-smoke/9e606bc1d8ff4b5ab717153b2cd3169a/report.json)、[protocol.json](../artifacts/local/encoder-ablation-smoke/9e606bc1d8ff4b5ab717153b2cd3169a/protocol.json)。这组极小预算只验证接口，没有证明任何真实知识迁移优势；正式比较仍需要冻结实际任务和足够的独立种子及仿真预算。

六种编码器的 `SACLearner` 现已共用默认输入缓存，保持各自独立网络与实验数据；比较时应使用相同缓存配置并报告完整耗时。缓存只复用原始输入，不复用 learned embedding。接口、等价性与实测见 [输入缓存说明](input-tensor-cache.md)。
