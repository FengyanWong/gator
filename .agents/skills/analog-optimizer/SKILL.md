---
name: analog-optimizer
description: "开发和审查基于 Cadence Virtuoso/Spectre、virtuoso-bridge-lite、端口感知电路图与 goal-conditioned SAC 的模拟电路尺寸优化项目。用于 netlist/CircuitGraph/PyG、仿真后端、可变动作、Graph Transformer/RGCN/GATv2 编码器对照与迁移实验；不用于通用头脑风暴或纯版图生成。LLM 驱动的尺寸优化只按 docs/brief-llm-sizing-for-astra.md 进行。"
---

# Analog Optimizer

协助用户逐步构建**可测试、可恢复、可复现实验**的模拟电路尺寸优化研究系统。
以用户最新请求、仓库现状和已验证的接口为准；本 Skill 是项目约定，不是上游 API 文档，也不是已经实现或验证的优化器。
中文解释，保留英文代码标识符。先检查已有代码，再做最小可验收改动。

## 先读什么

每次使用先读仓库根目录的 `CLAUDE.md`（当前规则）与 [项目决策](references/project-decisions.md)（研究侧 M1-M6 的范围；最新状态以 `docs/decisions.md` 开头的 Current state 一节为准：M6 已于 2026-09-20 以试点规模收尾）；再按任务选择材料，不必一次加载全部：

| 当前任务 | 读取材料 |
|---|---|
| 工作台（Web UI：`src/gator_workbench/`、`frontend/`） | `docs/frontend_implementation_status.md`（开发记录索引）；`docs/workbench.md`（各功能现状，约 145 kB）只读所改功能的小节：先 `grep -n '^##' docs/workbench.md` 看标题，再按行号读；工作台代码只放在这两个目录 |
| 首次启动、拆分任务、验收 | [阶段与交付](references/milestones.md) |
| Virtuoso、Spectre、SSH、WSL、VM、运行失败 | [后端契约](references/bridge-backend.md) |
| netlist、device/net graph、端口、参数组、PyG | [图与解析契约](references/graph-contract.md) |
| 编码器切换、Graph Transformer/RGCN/GATv2、actor/critic、SAC、reward | [学习与动作契约](references/learning-and-actions.md) |
| 泛化、基线、消融、性能、论文结论 | [实验与审查](references/evaluation.md) |
| PVT/Monte Carlo 接口、top-k 后验证、未来算力预算 | [工况与统计验证](references/pvt-monte-carlo.md) |
| 外部 API、文献或安装方式需要核对 | [来源与核实边界](references/sources.md) |

## 当前默认方向

```text
Virtuoso schematic / exported Spectre netlist
  → verified extraction / parser
  → canonical CircuitGraph: devices + nets + terminal-aware connections
  → PyG representation + parameter groups + target specifications
  → selectable encoder (default: Graph Transformer; also RGCN, GATv2, GraphGPS, parameter-group cross-attention)
  → goal-conditioned SAC actor + action-conditioned twin graph critics
  → normalized action → legal physical parameter assignment
  → backend adapter → Virtuoso bridge / Spectre
  → validated measurements + status → observation / reward / replay
```

- 默认使用 **Graph Transformer + goal-conditioned SAC**。通过统一编码器接口可切换的有 Graph Transformer、RGCN、GATv2、GraphGPS 与参数组交叉注意力（`graph_transformer` / `rgcn` / `gatv2` / `graph_gps` / `group_cross_attention`，见 `src/analog_optimizer/models/encoders.py`；后两者于 2026-10-06 加入，记录 7.228）：port-GNN 已于 2026-09-24 删除（源码提交 bbdfe36 及之前仍可运行它），MLP 与 GCN 于 2026-09-26 删除，GATv1（`gat`）同日由 GATv2 取代；旧名称会被明确拒绝，旧权重不迁移（2026-09-30 同步）。不要将编码器消融扩展为更换 SAC 或增加 surrogate。
- 首版**不加入 surrogate**，也不把 surrogate 插成 encoder 与 SAC 之间的必经层。
- LLM 驱动的尺寸优化：2026-09-29 用户决定按 `docs/brief-llm-sizing-for-astra.md` 加入（新子包 `src/analog_optimizer/search/`，一次 digest 变更；截至 2026-09-30 尚未开始）。对这项工作，该 brief 取代本 Skill 及其参考中“不引入 LLM 搜索 / LLM 内环”的规则；其他工作仍不默认加入 LLM（2026-09-30 同步）。
- 优化范围先是固定拓扑的器件尺寸、偏置及被明确允许的参数；不是拓扑搜索或自动布局布线。
- 初始目标是可靠单电路闭环；之后验证同类电路的规格与拓扑迁移，再研究 LDO/VCO/OpAmp 跨类别迁移。
- 当前项目已完成 M4、M5 首轮与真实同类新拓扑补验，以及 M6 前的编码器接口；M6 已完成合成跨类别协议、真实 LDO/VCO 基线鉴定和一次冻结的真实跨类别试点（2,811 次 Spectre 调用、1,566 次 SAC 更新，独立审计与 544 项回归全部通过），但未证明 GT 迁移优势；随后的严格模式（reference）复验以 28 次 Spectre 调用确认了全部 36 个成功 VCO 运行的首个可行设计（见 `docs/m6-vco-requalification.md`）；M6 已于 2026-09-20 按用户决定在试点规模收尾：流程已在真实电路上跑通并经独立审计，但迁移或 GT 是否有优势在该规模下没有结论；更大规模前瞻实验及各项可选扩展均未进行，需用户另行决定与预算。里程碑计划在 M6 之后未定义新阶段。不要在 `src/analog_optimizer/` 内随意新增或修改 `.py`：`source_digest()` 决定既有 checkpoint 能否加载及冻结协议能否复核。不要再用早期“止于 M3”的范围限制覆盖后续授权；新任务仍以用户请求为准。最新证据和边界见项目 `docs/decisions.md`、`docs/m5-real-topology.md`、`docs/encoder-ablation.md`、`docs/m6-real-results.md`。
- 训练/采样默认 nominal（condition policy `off`）；并行 Spectre 采集入口默认 4 个 worker（各自隔离的网表与作业目录，共享一个 learner/replay，见 `docs/parallel-spectre-sac.md`）。reward v2（2026-09-26）起，`real:gpdk045_ota7` 可显式选择 `always`（每步 nominal + 四个 screening corners），reward v2.1（2026-09-29）起还可选 `after_nominal`（nominal 通过全部 hard spec 后才跑 corners）；此时各工况结果进入训练 reward 和 replay（`SACLearner(condition_policy=...)`，见 `docs/reward-v2.md` 与 [工况与统计验证](references/pvt-monte-carlo.md)），其他任务只能 nominal。事后验证仍是独立的：自 2026-09-22 起工作台的 Corner check 可对一次 run 的最佳设计在 5 个 GPDK045 工况下重新仿真（`docs/workbench.md`），其结果不回到训练；Monte Carlo 执行仍未实现（只有计划 `docs/plan-finalist-monte-carlo.md`）（2026-09-30 同步）。
- 工艺角与温度从实际 PDK 模型/文档读取，电压还需核对所用器件的限制。用户撤回的 1.8 V 示例不作为 GPDK045 当前 OTA 的配置。区分 PDK 明文范围与项目自行选取的筛选点。
- 当前 GT 使用局部端口注意力；宽度、层数及与其他架构的优劣仍需实验比较，不能从接口通过推断迁移优势。

用户明确修改架构时，按新请求调整，并同步项目中的决策记录；不要拿本文件阻止用户改变方向。

## 开工流程

1. **检查仓库。** 阅读 `CLAUDE.md`（本仓库没有 `AGENTS.md`）、README、依赖声明（精确版本见 `constraints.txt`）、配置、测试及相关模块；检查未提交改动，不覆盖用户工作——多个会话共用同一工作区与 git index。
2. **确认范围。** 用简短文字指出本次输入、输出、受影响接口和验收条件。能够从仓库解决的问题先查代码，不重复询问。
3. **核对环境。** 确认 Python 所在环境、bridge 的真实安装位置与版本、Virtuoso/Spectre 所在主机、现有连接方式；不在日志输出凭据。
4. **最小实现。** 优先修改已有模块；只在缺失时创建结构。不可把假实现包装成真实后端。
5. **先离线验证。** 无 Cadence、PDK、SSH、GPU 时，解析和 mock 测试仍应可运行；真实测试必须单独启用。
6. **报告证据。** 说明改了什么、运行了哪些命令、通过/失败/跳过的测试、未验证部分，以及一个具体的下一步。

只有实质阻断正确性或涉及有风险的真实操作时才提问。缺少 PDK、网络或许可证，不阻止离线部分交付。

## 必须保持的技术约束

### 数据与图

- 原始 instance/net 名仅用于定位和回写，不把 `M1`、`M3` 等名字当作跨电路的学习语义。
- 保留 MOS 的 D/G/S/B 端口及正反向关系；同一器件多端口连到同一 net 时，不可合并成一条无类型边。
- 器件端口顺序和参数含义必须来自解析出的定义、CDF/PDK 映射或用户配置，不凭名称猜测。
- 使用统一 `CircuitGraph` 与参数组表，支持不同器件数、net 数和可调参数数；图对象不依赖 bridge 活连接。
- 未知器件/未解析表达式必须明确标记。涉及优化的未知语义必须报错，不静默丢器件、接地或填零。
- 静态拓扑与动态尺寸/测量分开存储；learner 已默认启用有界静态模板和完整观测输入缓存，按内容摘要命中；学习更新经 `ReplayBuffer.update_learner` 借出 replay 中的 transition（不深拷贝，观测摘要每条只算一次），公共 `sample()` 仍深拷贝；gamma 恰为 0 时更新跳过下一状态的 batch/actor/target critic，结果与随机数状态逐位不变（2026-10-06 记录 7.221）。尺寸/规格/schema 变化须刷新对应输入，不能缓存 encoder 更新后的过期 embedding；容量与失效规则见 [图契约](references/graph-contract.md)。
- PyG batch 不可产生跨电路边；padding、缺失参数、无效测量必须有独立 mask。
- M1 已有 `graph/neural.py` 的固定语义同构导出与 dense 节点视图；不要直接将 device/net 的不同含义 x 列自动拼成共同语义。参数组 batch 偏移分别按组数和节点数计算，具体见 [图契约](references/graph-contract.md)。

### 学习与动作

- Actor 为每个**独立可调参数组**输出分布；共享输出头，不为每个拓扑创建固定长度专用最终层。
- Critic 明确接收图状态、规格和动作，并把动作与其对应的参数/器件绑定；不能只读 pooled graph 忽略动作。
- 跨电路共享的是结构与训练权重；这不等于强制 actor、Q1、Q2 在同一次训练中共享全部 encoder 参数。
- 编码器统一返回节点、参数组、context 表示，共用 SAC heads 与动作契约；GT 与 GATv2 的注意力读取端口边特征，RGCN 以 terminal role × direction 为关系（原 MLP/GCN 对照已于 2026-09-26 删除）。各架构分别预训练，不直接互载权重。
- 连续 SAC 使用重参数化、tanh 变换、正确的 log-probability 修正、双 Q、target Q 与软更新。
- 每个图只对有效独立动作维度求 log-probability 和熵；参数组绑在一起只计算一次，不计 padding。
- 保存提议动作和执行后的物理参数；明确 critic 使用哪一种表示，不能在 replay 与 policy loss 之间悄悄切换。
- 整数、finger、multiplicity、匹配约束要通过合法化处理；连续量化代理不等于严格的离散/混合动作 SAC。
- 成功由所有必需有效规格共同决定。仿真失败、指标缺失、不达标与基础设施故障必须区分。
- `robust_score = nominal_reward - lambda_failed * failed_corners` 仅用于后验证；任何已知失败 corner 都使设计失去通过资格，不能靠高 nominal reward 抵消。工况缺失/测量或基础设施故障时保留未完成状态，不伪造完整 pass rate 或 robust score。
- 保存 encoder、actor、critics、target critics、优化器、温度参数、normalizer、schema、词表、配置、随机状态和恢复所需 replay。

### 后端与真实运行

- 优先使用用户选定的 `virtuoso-bridge` / `virtuoso-bridge-lite`；先读本地上游代码或帮助，再调用已确认 API。
- 项目 `Backend` 的方法是我们自己的抽象，不要冒充 bridge 内置方法。
- mock 后端显式标注为 synthetic；绝不在真实后端报错后偷偷返回 mock 成功。
- 写原理图前确认目标和当前授权，使用副本/检查点或经核实的恢复策略；不得默认覆盖原设计。
- 每个仿真 job 使用唯一目录和标识；只清理本项目拥有的文件和进程。
- 在网表、request/result、图观测与日志间传递同一份 PVT/MC context；明确 nominal/pvt_validation/mc_validation。Monte Carlo 未实现时显式报不支持，禁止把重复 nominal 仿真包装成统计样本。
- 并行只在隔离的 cellview、session 或不可变网表上进行（并行 Spectre SAC 即如此：一个准备进程串行处理候选，各 worker 只跑各自的网表）；否则不并发修改同一 Virtuoso 设计。
- 先测通信、参数更新、netlisting、仿真、解析与训练耗时，再讨论提速；不要把换 bridge 当成必然仿真加速。
- 不硬编码主机、用户名、PDK 路径、模型名、许可证路径；不要自动上传私有 PDK、netlist、波形或密钥。

## 实验与研究纪律

- 区分同拓扑新规格、同类新拓扑、跨类别迁移、跨 PDK 迁移。后两项不属于首版已验证能力。
- 先冻结 train/validation/test 的拓扑和规格划分；重命名或重排同一电路不是 unseen topology。
- 超参数选择、normalizer 拟合和 replay 不可偷用 test 数据；使用 test 数据更新过权重就是 adaptation，不是 zero-shot。
- 同时报告真实仿真调用数、失败/重试、wall-clock、达标率、time-to-first-feasible、最终质量和训练成本。
- 编码器比较为每种架构提供 scratch/frozen/adapt，保留随机搜索和合适的非 RL 基线；同宽度/深度不等于参数量匹配，分别记录参数量、预训练和在线成本。
- 2023 Li 工作、DEGT 或其他论文的实现细节先查原文/代码。无法确认时写“未核实”，不得虚构复现或新颖性。

## 内置方案审查

当用户要求 review、挑刺、grill、检查可行性或准备大改时，给出具体问题与验证方法：

- 端口感知编码器（GT、GATv2 的边特征，RGCN 的关系）是否真的使用端口信息？M1 同构/dense 导出是否保持列语义、mask 和组索引偏移？
- 可变大小的图是否仍配着固定动作头？critic 是否真的 action-conditioned？
- 差异来自模型，还是更多仿真、预训练数据、更宽参数范围或并行资源？
- 奖励是否把缺失/失败当好结果？参数回写是否真正生效？
- 泛化划分是否泄漏？零样本与微调是否分开？
- 当前任务是否可以用一个离线测试或单次真实仿真先验收？

每条指出风险、证据/缺失证据、可执行测试。不要只赞同架构，也不要无止境追问而不编码。

## 完成标准

交付可运行的小步实现及对应测试；清楚区分已运行、仅静态检查与未运行内容。
先完成本次约定的 milestone，不能用未实现的模型骨架或一大段计划代替验收结果。
