# 实验、泛化与技术审查

本文件规定如何得到可解释的证据，不宣称某种架构一定优于另一种。

## 1. 四种问题分开问

| 实验 | 训练与测试差异 | 能支持的结论 |
|---|---|---|
| 同拓扑新规格 | 电路连接相同，目标或运行条件改变 | 规格条件化泛化 |
| 同类新拓扑 | 如新的 LDO 连接/参数规模 | 同类结构迁移 |
| 跨电路类别 | LDO、VCO、OpAmp 间变化 | 仅在覆盖的类别与协议范围内的迁移 |
| 跨 PDK | 器件模型与合法域变化 | 另行定义的工艺迁移，非首版默认范围 |

同一电路重命名、实例重新排序、参数随机初始化，不算新拓扑。
统一图支持可变大小不等于优化策略有有效泛化。

## 2. 防泄漏协议

- 训练前冻结拓扑 lineage、规格分布、测试台与 train/validation/test manifest。
- 用显式拓扑族标记与结构去重检查；不把文件名或 raw netlist hash 当作唯一防泄漏保障。
- normalizer、词表选择、surrogate、离线 replay 和超参数选择都遵守划分。
- 从同一基电路轻微修改得到的电路是否算 unseen，在实验前定义并报告。
- validation 可以选超参数；test 不反复用于调参后还称为无偏测试。
- 对基线给相同测试台、参数合法域、起点规则、规格、corner、精度与停止条件。
- 并行数、CPU 线程、GPU、许可证和预训练数据不能藏在“算法差异”里。

## 3. Zero-shot 与 adaptation

**Zero-shot policy**：不以测试电路的数据更新权重或测试集统计。若需要当前电路的初始测量或在线多步查询，仍要计入这些真实仿真。
必须进一步区分“直接生成一次参数”与“冻结 policy 的多步优化”，不能混称无仿真 zero-shot。

**Few-shot / online adaptation**：允许固定预算内的测试电路仿真和学习，必须报告预算、更新对象、初始化和是否保存后续经验。

**From scratch**：同样的在线预算从随机模型/无预训练启动。
跨任务积累经验的顺序依赖要记录，不能让后测任务无声明地获得额外知识。

## 4. 基线与消融

先有可复现随机搜索，再按代码可用性选一个合适的非 RL 优化器（如 CMA-ES、CEM 或 BO）。
选择依据是参数域、预算与可维护性，不要求首版一次实现所有算法。

当前项目已实现随机搜索与坐标模式搜索。用户要求的编码器对照通过统一 SAC 接口比较（2026-09-30 同步：只剩下面三种编码器；
node-wise MLP、topology-only GCN、GATv1 与 M5 的 port-aware message-passing GNN 已删除，历史结果仍以各自记录为准）：

```text
port-aware Graph Transformer + SAC       # 主方案
port-relational RGCN + SAC               # role × direction 关系
port-aware GATv2 + SAC                   # GATv2Conv 动态注意力，端口边特征进入注意力
scratch / frozen / adapt                 # 每种显式选择的编码器均运行三种模式
```

显式使用 `--encoders` 时，每种架构独立预训练并做冻结 validation 诊断；不传时只运行 `graph_transformer` 的三种模式加随机搜索与坐标模式搜索（`examples/benchmark_transfer.py` 的默认；M5 六方法含已删除的 port-GNN，只能在源码提交 bbdfe36 运行）。固定划分、规格、动作合法域、seed、预训练/在线预算和更新规则；各策略采集的候选可能不同，同样的预算不等于同一数据集。

`scratch` 随机初始化；`frozen` 复制同架构权重并冻结，以均值策略做多步评价；`adapt` 复制同架构网络/alpha，但重新创建优化器与空 replay。每个测试任务独立，数据不回流源模型。当前 validation 仅作诊断，不做模型或超参数选择。

分别比较每种架构的 frozen/adapt 与其自己的 scratch，再跨架构比较；保留随机与非 RL 对照。报告实际 actor+Q1+Q2 参数数、预训练和在线成本，同宽度/深度不宣称参数量匹配。预算按选择矩阵计算，超出上限在创建后端前拒绝；切换编码器不自动增加真实仿真预算。

固定拓扑展平 MLP 或用户旧 DDPG/RGCN 是另外的参考，不能与当前共享的 RGCN-SAC（或已删除的逐节点 MLP-SAC）混称；须说明动作维度与优化器差异。端口语义/规格条件化的额外消融仍需单独实现和验收。
TD3、surrogate、global attention、gated residual、额外 OP 特征和并行采样均是后续单独消融。
一次改变多个因素后，不把提升全部归因于一个新模块。

2023 Li 与 DEGT 仅作为需核对的相关工作。复现前确认具体文章、开源版本、真实训练/测试协议和授权；不要凭先前聊天补造论文细节。
未阅读原文/代码前不声称“首次”“超越”“完全复现”。

## 5. 最少报告什么

| 类别 | 指标 |
|---|---|
| 达标 | 必需规格全部达标率、失败类别、有效设计比例 |
| 样本效率 | 首次达标前真实仿真调用数、固定预算下 best-so-far 质量 |
| 时间效率 | time-to-first-feasible、总 wall-clock、吞吐、分阶段耗时 |
| 质量 | 每项原始物理指标、最坏 violation、次要目标、Pareto 结果（适用时） |
| 成本 | 预训练、调参、warm-up、失败、重试、corner/analysis 次数和并行资源 |
| 稳定性 | 多个独立随机种子、跨测试电路分布、区间与个例 |

仿真预算需定义“一次调用”是单 analysis、单 corner 还是完整候选测试包；同时保存底层调用和候选评价计数。
cache hit 不当作新仿真，warm-start 数据和实际失败调用不能从成本里消失。

优化器包只预留 nominal top 3 的固定 5-corner 后验证接口（工作台 Corner check 对 1-3 个最佳设计执行 5 工况复仿真），不跑全组合。必须先按 nominal reward 对实际执行参数去重、固定 top-k，再做后验证；不得用事后 PVT 结果反选 nominal top-k 或混入训练（reward v2 / v2.1 为 OTA7 显式选择的训练工况是另一回事，见 [工况与统计验证](pvt-monte-carlo.md)）。`pass_rate` 的分母是全部配置 corners；有未知结果时不给完整通过率。对 min/max/range 按约束方向报告最差指标与对应 corner。robust_score 只在结果完整时计算，任何已知失败 corner 都排除通过资格。

这五个 corners 用于选择候选，属于 validation，不是独立 test。未来重复依据它们调参时仍需独立留出验证条件/统计种子再报告泛化或良率。MC 样本通过率、corner pass rate 和真实制造良率不是同一个指标。更多预算规则见 [工况与统计验证](pvt-monte-carlo.md)。

未在预算内达标的 run 是未达标/右删失，不从 time-to-feasible 均值里删除，也不假装预算终点就是成功时间。
报告条件于成功的时间时必须同时给出成功率和删失规则。
正式实验的 seed 数由预算决定；只有一次运行时明确标成 pilot，不给稳定优越结论。

## 6. 迁移是否值得

分别展示：

```text
online savings per task
upfront training + hyperparameter-search cost
number of tasks needed to recover upfront cost (when measurable)
```

不要只报微调后每个测试任务更快，却不说明为此用了多少预训练 Spectre 数据。
可以同时给“已训练模型重复使用”的边际成本和“从零建立该系统”的总成本。
若跨类别失败，分析是规格/测量不统一、数据分布、表示、动作域或算法限制，不能仅用换更大模型替代诊断。

## 7. Review / grill 清单

给每个问题附代码位置、数据或缺少的证据，并提供具体测试：

1. **端口与拓扑**：改变 D/G/S/B 连接是否改变真实传给模型的特征？重排 ID 是否保持输出等变？
2. **动作与 Q**：组数不同能否 batch？动作绑到正确器件吗？actor 梯度能通过 Q 回来吗？
3. **奖励**：未振荡、测量缺失、非收敛、许可证失败是否分开？成功判定会不会绕过必需规格？
4. **仿真真实性**：回写是否生效？重复候选是否命中正确缓存？测试台与 corner 是否意外变化？
5. **泛化**：测试拓扑是否只是重命名？测试数据是否进入 replay、normalizer、surrogate 或调参？
6. **公平性**：模型提升是否来自更多数据/资源、更宽边界、不同停止条件或排除失败？
7. **工程收益**：瓶颈在哪里？训练计算开销是否吞掉仿真节省？恢复是否保留完整学习状态？

审查不要求额外安装 `brainstorming` 或 `grillme`，也不等于照搬这些第三方 skill 的内容。
