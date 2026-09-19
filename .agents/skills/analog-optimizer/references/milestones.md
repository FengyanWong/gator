# 分阶段实现与验收

不要预设整个项目已经开始，也不要一次性生成所有目录和空类。
先检查当前 repo；已完成的步骤用测试确认后跳过。每次交付一个明确阶段或阶段内的小任务。

当前项目已完成 M1–M4、M5 首轮及下述 M6 前编码器接口；M6 尚未开始。具体已验证能力与限制见 [项目决策](project-decisions.md)，不要将历史阶段范围当成当前暂停指令。

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

## M6：跨类别、可选加速与扩展

进入 M6 前，用户要求的 GT/MLP/GCN/RGCN/GAT 可替换接口已实现：统一模型契约、每架构 scratch/frozen/adapt、配置/checkpoint 隔离与动态预算。保留 M5 port-GNN 和默认六方法。验收包括混合图/动作、端口消融、精确恢复及四架构合成迁移流程；这不等于 M6 或真实新拓扑迁移完成。

基础有效后，再研究 LDO/VCO/OpAmp 跨类别迁移与单策略多环境采样。
之后才按明确假设引入 surrogate、结构全局 attention、更多参数域或其他优化器。

验收：每项扩展独立消融、最终真实验证、完整成本比较；没有因新功能破坏前面阶段的契约。

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
