# 图输入张量缓存

2026-09-19，用户要求减少训练更新中的重复图转换。所有六种编码器现在共用默认启用的输入缓存；首次使用一条观测时转换，之后 replay 深拷贝和重复采样均可复用。在缓存未被淘汰、清空或随进程退出释放的前提下，同一份观测内容只转换一次。

## 缓存什么

| 层次 | 复用内容 | 何时刷新 |
| --- | --- | --- |
| 静态拓扑 | 器件类别、net roles、各端口正反向边和 ordinal、参数组绑定及 mutable mask | 节点/边/组顺序、端口、绑定、可调性或 FeatureSchema 改变 |
| 完整观测输入 | 原始图张量、尺寸与有效/存在 mask、规格/测量/context、组特征 | 完整观测内容或 FeatureSchema/SpecSchema 改变 |
| 每次训练仍执行 | batch 拼接、索引偏移、边打包、当前权重下的 encoder/attention、前向/反向与优化器 | 每次调用 |

缓存与编码器类型无关，不为 GT、MLP、GCN、RGCN、GAT、port-GNN 生成六份不同的 canonical graph。一个 learner 内 actor/Q1/Q2/targets 复用准备好的 batch；它们仍有独立网络参数。各个独立训练/迁移 learner 自己持有缓存，不建立跨实验全局缓存。

同一拓扑的新尺寸候选会命中静态模板，并生成当前尺寸和测量对应的动态输入。缓存不会保存 embedding、attention 权重、Q 值、动作或梯度；更新模型后，相同历史观测必须重新前向。普通 GCN 仍为 `cached=False`，不能用 PyG 层的单图邻接缓存替代这里的按内容匹配。

真实环境的参数回读、网表导出、解析与一致性核验继续执行。这次优化的是内存中的输入转换，不将一次提取的旧尺寸视作下一次真实仿真的观测，也不复用仿真结果。

## 接口与有效性

- `graph/pyg_converter.py` 的 `TopologyTensorCache` 提供静态模板。`to_pyg(graph, topology_cache=cache)` 返回独立张量，并刷新尺寸、mask、group value/bounds、回写与来源 metadata。省略缓存仍支持原调用方式。
- `models/inputs.py` 的 `ObservationTensorCache` 管理准备好的 CPU 输入；`batch_observations(..., cache=cache)` 复用输入，省略参数则每次转换。
- `SACLearner` 默认配置 `input_cache_capacity=8192`（2026-10-06 记录 7.221 起，原为 2048）、`input_cache_max_bytes=256 MiB`、`topology_cache_capacity=64`。两层均为有容量上限的 LRU，超限淘汰最久未使用条目；容量按条目计，实际内存随图及 metadata 大小变化。两项都设为 `0` 可关闭复用，结果不变。
- `learner.input_cache.info()` 返回两层命中/未命中、当前条目数和容量（记录 7.221 起另有淘汰次数、张量字节和字节上限）；`clear()` 释放条目并重置计数。统计不进入训练损失或随机状态。
- 完整观测缓存的键是内容摘要（记录 7.221 起为 schema 摘要 + `observation_digest(observation)`，见文末；此前为 `(FeatureSchema, SpecSchema, Observation)` 整体的本地 pickle 序列化 SHA-256）；只序列化计算摘要，不读取 pickle 文件。它覆盖嵌套可变内容、数值、mask、目标、预算、状态、origin、工况和来源信息。不能改成对象地址或单独的 job ID，否则 replay 深拷贝会失效，原地变更也可能误读旧值。字典插入顺序等表示差异可能造成额外未命中，只影响成本。
- 静态键保留有序节点/边/组身份、器件模型/端口、net roles、绑定比例及 schema；名字只用来确认索引与回写位置，不作为学习语义或图同构证明。来源文件路径和尺寸不属于静态键。
- 缓存未命中时完整校验观测；SAC 的 transition 校验仍每次执行。命中返回的是先前已经校验的相同内容。对外 batch 张量及 opaque metadata 与缓存隔离，调用方修改 batch 不会污染后续采样。
- 缓存属于派生运行时数据，不写入 checkpoint。恢复后按需重建；`SACLearner.load()` 可重新指定两项容量。缓存容量不改变学习契约，严格代码/schema/依赖校验仍保留，因此此次改码前的 checkpoint 不会自动迁移。

```python
from analog_optimizer.models.inputs import ObservationTensorCache, batch_observations

cache = ObservationTensorCache(capacity=2048, topology_capacity=64)
first = batch_observations(observations, cache=cache)
again = batch_observations(observations, cache=cache)
print(cache.info())
# SACLearner 已默认接入同样机制，act() 与 update() 都使用它。
```

## 验收与计时

完整回归 **354 项通过，零失败、零跳过**：[JUnit](../artifacts/local/input-cache-tests.xml)。新增测试覆盖 replay 深拷贝命中、新尺寸/测量/规格/预算/工况刷新、schema 与索引次序失效、mask/来源隔离、LRU 淘汰/清空/禁用及无效输入拒绝。六种编码器均验证开启/关闭缓存时连续两次更新的损失、actor/critics/targets 参数和 alpha 完全一致；原有六架构 checkpoint 测试继续验证缓存冷启动的精确下一步恢复。

离线计时使用 CPU 单线程、Torch 2.14.0+cpu、PyG 2.8.0.post1、opamp/LDO 合成图混合 batch=32；网络为 hidden=32、2 layers、4 heads。输入计时 30 次；完整更新预热 2 次后计时 8 次，交替测试先后顺序，取中位数。对照为同一版实现关闭缓存；包括输入摘要计算、batch/metadata 复制和完整 `SACLearner.update()`，不包括 replay 深拷贝、后端、网络通信或 Spectre。

| 测量 | 关闭缓存 | 缓存命中 | 倍率 |
| --- | ---: | ---: | ---: |
| 输入 batch | 35.66 ms | 10.86 ms | 3.28× |
| GT 完整 SAC 更新 | 112.22 ms | 62.31 ms | 1.80× |
| MLP 完整 SAC 更新 | 99.70 ms | 48.58 ms | 2.05× |
| RGCN 完整 SAC 更新 | 125.19 ms | 75.74 ms | 1.65× |
| GAT 完整 SAC 更新 | 110.90 ms | 59.82 ms | 1.85× |
| port-GNN 完整 SAC 更新 | 106.35 ms | 55.73 ms | 1.91× |
| GCN 完整 SAC 更新 | 104.70 ms | 52.97 ms | 1.98× |

仅启用静态模板时输入 batch 为 31.46 ms；主要收益来自历史观测输入复用。每个 learner 的 10 次更新共处理 640 个 current/next 输入，只有 18 个完整观测未命中、2 个静态拓扑未命中。计时同时逐次验证六种架构的损失与最终参数完全一致。性能随图大小、batch、硬件和命中率变化；不是端到端仿真提速或迁移优势证据。

计时生成 **18 次 synthetic 解析评价，新增真实调用 0**，两个 synthetic 环境均恢复。完整数据、配置与源码摘要见 [report.json](../artifacts/local/input-cache-benchmark/report.json)。此优化未启动 M6。

```bash
/tmp/analog-optimizer-venv/bin/python -B -m pytest -q -ra \
  --junitxml=artifacts/local/input-cache-tests.xml
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_input_cache.py \
  --batch-size 32 --repeats 30 --updates 8 \
  --output artifacts/local/input-cache-benchmark
```

## 2026-10-06 记录 7.221：内容摘要键、借出样本、字节计数与容量

- 键 = `sha256(schema 摘要 + observation_digest(观测))`。schema 摘要按 (FeatureSchema, SpecSchema) 记忆（两者为深度不可变的 frozen dataclass，拓扑缓存的键本已要求可哈希）；`observation_digest` 是整条观测的 pickle SHA-256，覆盖此前键所覆盖的全部内容。内容相同的观测（含深拷贝）仍命中同一条目。
- `ReplayBuffer.update_learner(learner, n)` 把已入库的 transition 借给 `learner.update`（不深拷贝），并把每条 transition 两个观测的摘要只算一次（`_digests`，按对象身份并校验同一对象，环形覆盖时删除；不写入 checkpoint，冷恢复后按需重算）后经 `batch(..., digests=...)` 传入。其他调用（`act()`、公共 `sample()` 之后的 `update()`）每次完整摘要。`PdkViewLearner` 的视图生成新对象，忽略传入摘要，按视图自身内容摘要。
- `info()` 新增 `evictions`、`tensor_bytes`（每条目张量字节之和；拓扑缓存返回独立张量，故每条目自有）与 `max_bytes`；可选字节上限超出时淘汰最久未用条目，但总保留刚加入的一条。
- 容量研究（记录的 GATv2 `mscr_ota7t` replay 复制 1/3/7/14 倍，副本在图 metadata 中标记以得到新内容；GT 预设、gamma 0、batch 8、单线程；`artifacts/local/reviews/learner-step-7221-2026-10-06/`）：

| replay transition 数 | 不同当前状态 | 容量 2048 | 4096 | 12000 |
| ---: | ---: | --- | --- | --- |
| 751 | 598 | 100 %，44.5 ms | 100 %，43.1 ms | 100 %，44.2 ms |
| 2,253 | 1,794 | 100 %，45.4 ms | 100 %，45.4 ms | 100 %，45.8 ms |
| 5,257 | 4,186 | 52 %，52.7 ms | 97 %，46.8 ms | 100 %，45.5 ms |
| 10,000 | 7,964 | 29 %，58.6 ms | 55 %，61.5 ms（负载 3.3） | 100 %，48.0 ms |

  每个条目约 4.6 kB 张量（7,964 条共 36.4 MB），一次未命中的转换约 1.3 ms；进程内存主要是 replay 本身（10,000 条约 3.5 GB RSS）。因此 `SACLearner` 默认容量由 2048 改为 8192（覆盖满 10,000 条 replay 的全部当前状态），并设 256 MiB 字节上限以防异常大的图。
