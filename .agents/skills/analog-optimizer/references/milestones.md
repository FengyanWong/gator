# 分阶段实现与验收

不要预设整个项目已经开始，也不要一次性生成所有目录和空类。
先检查当前 repo；已完成的步骤用测试确认后跳过。每次交付一个明确阶段或阶段内的小任务。

当前项目已完成 M1–M5（含真实同类新拓扑补验）与下述 M6 前编码器接口；M6 已于 2026-09-20 在试点规模收尾（见 M6 一节）。具体已验证能力与限制见 [项目决策](project-decisions.md)，不要将历史阶段范围当成当前暂停指令。

## M0：代码与运行环境清点

输入：用户现有仓库、依赖声明、已配置的 bridge（若有）。
输出：已有模块与可复用路径、执行环境、当前缺口、首个验收目标。

- 明确 Python 位于 WSL 还是 VM；Virtuoso/Spectre 在哪里；不写死任何个人主机值。
- 核对 bridge 上游模块/版本/签名；不自动升级、重装或修改 daemon。
- 查是否有可分享的 sample netlist；没有就用 synthetic fixture。
- 记录无法获得的真实环境信息，但不因此停止离线开发。
- 为后续工况接口读取实际 model sections、统计入口、温度范围与所用器件电压限制；保存文件版本/摘要，区分来源事实和工程筛选点。

## M1：第一轮编码，仅基础链路

默认首次任务就是这一阶段：

```text
Backend Protocol + explicit MockBackend
  → documented Spectre syntax subset
  → CircuitGraph / terminal-aware connections / parameter groups
  → PyG conversion
  → synthetic fixtures + tests + small offline demo
```

目标输出：

- 独立于 bridge 的图和结果类型，明确 schema 和诊断。
- 真正可用的 parser 子集，不声称支持完整 Spectre。
- 可验证端口关系、层次与参数映射的 fixtures。
- PyG adapter 及两个不同大小图的 batch/unbatch 测试。
- 显式 synthetic mock；真实 adapter 接口可检查，但未接通能力必须如实标记。
- Backend 的 request/result/artifact 预留一致的 PVT/MC context；不支持的 MC 执行显式报错。图中保存实际工况 metadata，不能把统计模型随机变量变成 sizing action。
- README 说明依赖、支持范围、运行 demo/测试方式。

验收：在无 Cadence/PDK/SSH 的环境运行离线测试；demo 输出图结构摘要和参数映射；错误输入有可定位诊断。
**本阶段不实现 actor/critic、SAC 更新、surrogate 或并行调度。**

## M2：一条真实仿真基线

在用户允许且真实环境可用时，连接一个现成可仿真的电路。
导出或读取原网表 → 运行 baseline → 提取指标 → 对一个获准参数小幅修改 → 读回/重新 netlist 验证 → 复跑 → 恢复。

验收：真实结果包含来源、执行参数、版本、状态和耗时；与已有手动/脚本基线按明确容差一致。
若新网表运行路径与 ADE 不同，先验证模型、分析、corner 和测量等价，不直接比较耗时。
此阶段仍先验收一个明确 nominal。扩展 PVT 时使用参数一致的 job 副本，保持原尺寸/CDF 的检查与恢复，不并发改同一原理图；模型/电压/温度标签必须与执行网表和测量一致。

## M3：环境与非学习闭环

实现参数合法化、measurement evaluator、reward、reset/step、failure policy、candidate logging。
先用随机候选驱动整个真实流程，检查边界、失败、重复候选和停止条件。

M3 的工况接口范围：增加 typed PVT/Monte Carlo 请求、逐样本身份、来源与预算接口；`reset/step` 强制 nominal-only。另提供纯函数按 nominal reward 去重选 top 3、汇总固定 5 corners 的 worst-case/pass rate/robust score，并记录淘汰或未完成原因。没有模型输出时，不把随机候选称为 SAC 优化结果。top-k 后验证调度和 MC 执行不属于该接口交付，当前仍未实现。

验收还包括：非 nominal 结果无法进入 replay；错误工况/尺寸的结果被拒绝；任何失败 corner 都排除通过资格；缺失/基础设施故障不虚构通过率；MC 未实现明确拒绝；原 nominal 网表及动作语义保持兼容。未来可选复杂度见 [工况与统计验证](pvt-monte-carlo.md)，不因接口存在而自动启用。

验收：有限预算的小实验能完整恢复/复盘，成功不会漏过必需约束，失败成本有记录。
之后才引入神经网络；不要用训练曲线调试测量公式。

## M4：Graph Transformer 与 SAC

先在小型 synthetic environment 验证网络 shape、mask、梯度、target 更新和 checkpoint 恢复，再运行少量真实采样。
明确 attention_mode、参数组 actor、action-conditioned twin critics、温度和有效维度熵规则。

验收：两种不同 graph/action 大小可同 batch 更新；padding 不影响有效输出/loss；更新可重复、无 NaN；checkpoint 恢复保留 schema 和动作语义。
mock 学会某个 synthetic 函数不构成电路优化效果证据。

## M5：同类拓扑与规格迁移

冻结划分，比较从零训练、冻结 policy 和固定预算 adaptation；加入随机/非 RL 对照及端口感知 GNN 对照。

验收：报告达标率、真实调用、wall-clock、预训练成本、失败/删失和多种子；没有泄漏。

当前已补齐真实七管两级 OTA 的结构留出及 1→2 维动作对照：本轮 585 次 Spectre、3 seeds × 6 methods、24 个 checkpoint 审计及两电路恢复；440 项离线测试通过。GT 微调/随机各 1/3、坐标 3/3、port-GNN 微调 2/3，新拓扑的 GT 迁移优势仍未证实。只有一个结构留出拓扑，先做基线验收再冻结目标，不声称广泛或盲测泛化；见项目 `docs/m5-real-topology.md`。

## M6：跨类别、可选加速与扩展

进入 M6 前，用户要求的 GT/MLP/GCN/RGCN/GAT 可替换接口已实现：统一模型契约、每架构 scratch/frozen/adapt、配置/checkpoint 隔离与动态预算。保留 M5 port-GNN 和默认六方法。验收包括混合图/动作、端口消融、精确恢复及四架构合成迁移流程；该接口验收本身不构成 M6 或真实新拓扑证据；后续真实新拓扑补验见上面的 M5 记录。

基础有效后，再研究 LDO/VCO/OpAmp 跨类别迁移与单策略多环境采样。
之后才按明确假设引入 surrogate、结构全局 attention、更多参数域或其他优化器。

验收：每项扩展独立消融、最终真实验证、完整成本比较；没有因新功能破坏前面阶段的契约。

M6 已在试点规模收尾（2026-09-20，用户决定）：合成跨类别协议、真实 LDO/VCO 基线与 VCO 快速数值策略鉴定、冻结的 23 指标真实协议、三折 × 六编码器 × 三种子的真实试点（2,811 次 Spectre、1,566 次 SAC 更新，独立审计通过），以及 VCO 严格模式复验（28 次，36/36 确认）。M6 真实调用合计 2,877 次。GT 微调 OTA 2/3、LDO 3/3、VCO 3/3，坐标搜索各类 3/3，冻结策略 0/3；没有 GT 或迁移优势的证据，也没有劣势的证据。每类仅一个已表征拓扑、3 个种子、8 步 episode、仅 nominal，因此不是盲测，也不支持泛化、排序或收敛结论。单策略多环境采样、surrogate、全局 attention、更多参数域、其他优化器、PVT/MC 均未开始，不属于本次收尾；能回答 M6 问题的更大规模前瞻实验需用户另行决定与预算。本计划在 M6 之后未定义新阶段；Web 工作台按独立规格另行开发，不属于 M 系列。见项目 `docs/decisions.md`、`docs/m6-real-results.md`、`docs/m6-vco-requalification.md`。

## 项目目录示意

仅在新仓库缺少对应结构时使用；不是要求一次性生成所有文件：

```text
src/analog_optimizer/
  backends/
  netlist/
  graph/
  parameters/
  measurements/
  envs/             # M3 起
  models/           # M4 起
  training/         # M4 起
  evaluation/       # M3 起的纯汇总接口；后续才增加实验执行
tests/
  unit/
  fixtures/synthetic/
  integration/      # 明确 opt-in
configs/
examples/
```

## 每次完成时的报告格式

```text
本次完成：明确的行为变化和文件范围。
验收：实际运行的命令、通过/失败/跳过情况。
边界：哪些仅静态检查，哪些没有真实 Cadence 环境验证。
下一步：一个具体可执行任务，不承诺后台执行。
```

不能用大量“稍后实现”的空文件冒充阶段完成。
