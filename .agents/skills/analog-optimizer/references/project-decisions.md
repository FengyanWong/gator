# 项目决策与上下文

同步日期：2026-09-19。依据用户后续授权及项目 `docs/decisions.md`、`docs/encoder-ablation.md` 更新。
这是项目状态快照；最新用户请求、真实代码和对应验收记录优先。历史 M3 范围不再限制已经获准并完成的 M4/M5。

## 1. 当前工作方向

| 项目 | 当前约定 | 边界 |
|---|---|---|
| 优化任务 | 模拟/混合信号电路 sizing 与明确允许的偏置参数 | 首版不做拓扑生成和版图优化 |
| 电路平台 | Cadence Virtuoso + Spectre | 真实 PDK/测试台以本地为准 |
| 接口选择 | 用户指定 Virtuoso bridge；讨论的仓库是 `Arcadia-1/virtuoso-bridge-lite` | 不自动迁回 SkillBridge，不引入 LLM agent 内环 |
| 电路表示 | 统一、端口感知的 device-net 图 | 保存端口信息并传到模型；不是简单 adjacency |
| Encoder | 默认局部端口 Graph Transformer，可选 MLP/GCN/RGCN/GAT/port-GNN | 统一节点/参数组接口；可运行不等于迁移效果已证实 |
| 优化器 | Goal-conditioned SAC | 可以做其他算法基线，但不默认替换 |
| 初版 surrogate | 不使用 | 以后只能作为单独实验加入 |
| 当前训练工况 | 已验证 nominal only | PVT/MC 结果不进入 reward、replay 或 normalizer |
| PVT 筛选 | nominal top 3 独立设计 × 5 个代表性工况 | 已有配置、数据契约和汇总纯函数；执行调度尚未实现 |
| Monte Carlo | 保留类型、样本身份和显式不支持接口 | 未来先后验证，再考虑有限预算的训练扩展 |
| 可迁移目标 | 参数组级动作、统一 schema、规格条件化 | 不承诺任意电路 zero-shot |
| 当前阶段 | M1–M5、M6 前编码器接口已完成；M6 于 2026-09-20 在试点规模收尾 | 跨类别迁移仅有试点证据，GT/迁移优势仍未证实；更大规模前瞻实验与可选扩展未开始 |

## 2. 历史经验：用于兼容，不直接搬成默认值

用户有 Python、DDPG/RGCN、SkillBridge、Virtuoso ADE Assembler/OCEAN/Spectre 经验，做过 VCO/环振与 LDO 相关 sizing。
过去讨论过共享经验池与多仿真实例，并关心如何保留 policy 与 representation、减少 Spectre 调用和总运行时间。

因此：

- 优先复用用户已有的电路配置、测量脚本与经过测试的仿真流程。
- 接口层支持替换，但不要把老项目中某组 W/L、VDD、reward、episode 长度或噪声设置写成跨电路常量。
- 老 DDPG 的探索噪声并不是 SAC 的默认探索机制。
- 旧项目或其他机器的耗时/并行加速比只是历史测量，不是这台机器的新性能承诺。
- 不依据历史机器配置假定存在可用 CUDA GPU；先核对当前硬件与环境。

## 3. 部署上下文

用户近期讨论的两条路径：

```text
A. Python / Codex 位于 WSL 或 Linux
   → SSH / bridge
   → Linux VM 内的 Virtuoso / Spectre

B. Python 与 Virtuoso / Spectre 同在 Linux VM
   → local bridge / local runner
```

两者都应该通过配置接入相同的项目 Backend。
路径 A/B 谁更快要测量，不根据网络往返或“本地”标签直接下结论。
用户机器、SSH 账号和路径可能变化，不在 Skill 中写死。

## 4. 首版不默认做的事情

- 不加入 surrogate、diffusion、Mamba、LLM 搜索、多智能体竞赛、分布式训练集群。
- 不把所有器件尺寸、偏置、整数参数一次性全部放开。
- 不强行把不同电路补成同一种固定拓扑，或为每种电路维护独立模型输出层。
- 不把 Graph Transformer 换成“更省事”的 GNN 后仍称原方案已完成。
- 不在基础仿真尚不可靠时讨论数千步训练的收敛优劣。
- 不把其他 skill 的流程当作必须安装的依赖。本 Skill 自带任务拆分和技术审查要求。

## 5. 已实现的工程选择与待验证项

当前代码采用 PyG `HeteroData`/packed batch、固定规格注册表与 mask、固定物理 reference 归一化、绝对 normalized proposal 与合法化投影，以及各自独立的 actor/Q1/Q2 编码器。真实基线为 GPDK045 五管 OTA；不得将其参数权限推广到其他电路。

GT 使用局部 `TransformerConv`；基准入口默认 32 hidden、2 layers、4 heads，用户可以显式配置。全局 attention、结构距离、surrogate、更多动作域及多 worker 尚属后续选项。网络规模、正式预算与各架构迁移优劣需要独立实验，不是已确认性能结论。

若没有真实 PDK/网表，先生成**明确标注 synthetic 的结构测试**，而不是补造“商用电路结果”。

## 6. 泛化的工作假设

研究目标是让统一表示和共享 policy 在新规格或新拓扑上减少所需真实仿真。
优先按如下顺序检验：单电路闭环 → 同类规格迁移 → 同类新拓扑 → LDO/VCO/OpAmp 跨类别。
统一图能够容纳不同电路，不自动证明模型已经学会可迁移优化；是否加速以独立测试集为准。

## 7. 变更记录要求

重要变更写入项目自己的决策文件，记录日期、原因、影响模块、测试及可撤销方式。
不要修改全局 Skill 来偷偷改变其他项目；项目专属决定优先保存于项目仓库。

## 8. M3 工况接口决策（2026-09-19 用户修订）

历史上用户将该次工况接口修改限定在 M3 及之前；后来已明确授权并完成 M4/M5。仍然有效的工况约束是：新增工况接口不改变动作维度，不启用 PVT/MC training，主优化器继续使用 goal-conditioned SAC。

实际项目已用 `SimulationCondition/PVTCorner/MonteCarloConfig` 表达工况，并为统计批次保留逐样本结果接口。当前默认仍为 TT/27°C/1.0 V；这是已验证的 OTA 基线，不能因为器件名或文档表格而自动更换 nominal。

读取已安装 GPDK045 v6.0 后选取：TT/27°C/1.0 V、SS/125°C/0.9 V、FF/−40°C/1.1 V、FS/27°C/1.0 V、SF/27°C/1.0 V。模型入口提供五种 process sections；模型报告给出 −40..125°C；SOA 文件的 `max_vdd_1v=1.1` 明确限值。0.9 V 是项目以原基线下降 10% 的筛选选择，不是 PDK 明文最低工作电压。这五个组合不等于全组合或已证明的 worst-case 集合。

权威项目配置及来源摘要位于 `configs/gpdk045_conditions.json`。本段是上下文快照，未来修改先看实际配置与用户授权，不把当前电路的数值复制到别的 PDK。详细规则与未来算力建议见 [工况与统计验证](pvt-monte-carlo.md)。

## 9. M4/M5 与 M6 前编码器接口（当前状态）

- M4 已实现 nominal SAC、参数组 actor、动作条件化独立 twin critics、replay 及完整 checkpoint。M5 已实现冻结任务划分、防泄漏、独立任务微调和成本报告；真实规格 pilot 没有证明迁移优势，真实新拓扑与跨类别迁移尚未验证。
- 用户要求在 M6 之前支持 GT/MLP/RGCN/GAT 对照。`ModelConfig.encoder_type` 与 `CircuitEncoder/build_encoder` 已接好；`port_gnn` 保留兼容。定义与共同契约见 [学习与动作](learning-and-actions.md)，公平比较见 [实验与审查](evaluation.md)。
- `examples/benchmark_transfer.py --encoders ...` 对每种显式选择的架构运行 scratch/frozen/adapt，并给每种架构冻结 validation 诊断；不传该参数保留 M5 六方法。`examples/train_synthetic_sac.py --encoder ...` 选择单 learner 编码器。
- 各架构分别预训练；迁移复制同架构网络与 alpha，优化器/replay 重新创建。checkpoint 保存编码器与配置并严格匹配代码/schema/依赖；改码前的 M4/M5 checkpoint 不会自动迁移，跨架构权重加载拒绝。
- 此次代码验收为 296 项离线测试通过、零失败、零跳过；四架构 smoke 完成 116 次 synthetic 评价，覆盖同拓扑规格和 2→3 维动作的新拓扑，新增真实调用为 0。记录和复现命令在项目 `docs/encoder-ablation.md`；这些是接口证据，不是电路知识迁移优势。
- 该次文档和 skill 同步没有启动 M6 或新的训练/仿真。后续阶段依用户新请求及实际验收情况推进。

## 10. M1 神经网络输入复核（最新补充）

用户随后要求检查 M1 是否支持 GCN/GAT 等网络。原图信息足够，补齐了普通算子的固定语义同构视图 `circuit-neural-v1`（默认节点 49 列、边特征 15 列）、带 mask 的 dense 节点输入与正确组 batch 偏移；不重写 parser。SAC 与新导出复用端口打包逻辑，细节见 [图契约](graph-contract.md)。

新增普通 `gcn`，作为只读连接、不读端口标签的对照，区别于 `rgcn`。最新验收为 319 项离线测试通过、零失败、零跳过；六编码器 smoke 共 168 次 synthetic 评价，全部恢复，新增真实调用 0。直接输入测试覆盖 opamp/LDO/VCO、两级 opamp 和现有真实 OTA 导出快照。记录在项目 `docs/m1-neural-inputs.md`，不代表 M6 或真实迁移效果验证完成。

## 11. 训练输入缓存（最新补充）

用户随后要求优化每次更新中的重复图转换。learner 已默认启用两层有界 LRU（2048 条完整观测原始输入、64 个静态拓扑模板），六编码器共用；replay 深拷贝按内容命中，尺寸/规格/测量/schema 改变刷新输入，网络表示始终按当前权重重算。真实回读与网表核验保留，未启动 M6。

完整 354 项离线测试通过、零失败、零跳过；六编码器缓存开/关损失和参数一致，冷 checkpoint 精确恢复。CPU 合成 batch=32 输入阶段约 35.66→10.86 ms，GT 完整更新约 112.22→62.31 ms；这些时间不含 replay 深拷贝或后端，不是 Spectre 提速。计时生成 18 次 synthetic 解析评价，新增真实调用 0。接口与证据见项目 `docs/input-tensor-cache.md`，长期约定见 [图契约](graph-contract.md)。


## 12. M5 真实同类新拓扑补验（最新状态）

用户要求补齐 M5。已新增 GPDK045 七管 Miller 两级 OTA 的独立核心/测试台、严格 CDF 宽度组 profile 和多电路串行实验入口。原五管动作权限不变；新拓扑有输入匹配宽度和 M6/M7=4:1 输出宽度两个动作组。两电路的每次回写、导出、测量和最终恢复均验证。

完整回归 440 passed、零失败/跳过。本轮 7 次电路验收 + 576 次冻结实验 + 2 次最终复验，共 585 次真实 Spectre、288 次 SAC 更新；3 seeds × 6 methods，同时覆盖源拓扑新规格与新拓扑。24 个 checkpoint 的来源/隔离、冻结权重及下一次更新精确恢复审计通过。最终 CDF 全快照、基线网表、指标与 PDK 入口/MOS 摘要均一致。

新拓扑 GT 从零/冻结 0/3，GT 微调 1/3，随机 1/3，坐标 3/3，port-GNN 微调 2/3。尚无 GT 迁移优势证据；仅一个留出拓扑且先完成基线/参数域验收后再冻结目标，不称为广泛或盲测泛化。M6、PVT/MC、surrogate 未在本轮启动。以项目 `docs/m5-real-topology.md` 和 `artifacts/local/m5-topology-acceptance-summary.json` 为本轮证据，前面首轮记录中的真实拓扑缺口已由此补齐。
