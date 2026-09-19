# M5：规格迁移与拓扑迁移验收

后续用户要求补齐本页的真实新拓扑缺口，现已完成独立七管两级 OTA 的真实迁移对照及恢复审计，见 [M5 真实拓扑补验](m5-real-topology.md)。本页保留首轮 97 次真实调用的历史记录。

2026-09-19，用户授权继续 M5。新增可执行的固定划分、多种子迁移对照流程，沿用 nominal-only、单 worker 和原有动作权限。真实实验仍是 GPDK045 五管 OTA 的规格迁移；新拓扑只使用明确标注的合成结构与解析函数，尚未验证真实电路拓扑迁移。

## 冻结协议与防泄漏

入口为 `examples/benchmark_transfer.py`。每次运行创建 UUID 目录，先以独占创建方式写入 `protocol.json`，再开始第一次仿真。协议包含完整图与参数组、train/validation/test 规格、种子、模型结构、预算、输入文件摘要、代码摘要和方法定义。已存在的协议不能覆盖。

`evaluation/transfer.py` 对 device/net/terminal incidence graph 做精确同构检查；节点标签使用器件类别、net role 和 terminal/ordinal/role，实例名称、排列、尺寸和参数组 ID 不参与身份判断。S/B 同网仍保留不同 terminal 节点。跨划分的同构图不能声称 unseen topology；同拓扑同规格不能跨划分，改变 reward weight/scale 也不算新规格。

- 预训练经验只接受 `train`，并检查每条 transition 的规格、图和动作契约。
- validation 只运行 GT 冻结策略，属于诊断，不用于选择 checkpoint、超参数或测试阈值。
- 每个测试任务、方法、种子新建环境。每次从相同基线 reset，使用相同目标、动作边界与候选预算。
- 微调复制 actor、双 critic、target 和温度参数，优化器及经验池重新建立；不携带预训练 replay，不重用其它测试任务的 adaptation。
- 冻结策略使用 deterministic mean policy；不创建经验池、不更新权重。执行前后及整轮测试结束分别验证权重摘要。
- 输入继续使用 M4 固定物理参考归一化，不从测试数据估计统计量。每个学习阶段保存独立 checkpoint，其中仍有完整 schema、优化器、随机状态和 replay。

真实规格围绕 M2–M4 已知基线设计，并在 M5 采样前冻结；这属于前瞻冻结的流程 pilot，不是对历史结果完全盲测的性能 benchmark。

## 六种方法

| 标识 | 初始化与在线行为 | 预训练成本 |
| --- | --- | --- |
| `gt_scratch` | 全新 GT+SAC；首次随机 warmup 后用策略 | 无 |
| `gt_frozen` | 预训练 GT 的确定性均值策略；权重固定 | 计入 GT 预训练 |
| `gt_adapt` | 预训练 GT；新优化器/replay，固定预算更新 | 计入 GT 预训练 |
| `random` | 在每个 normalized action 维度独立均匀采样 | 无 |
| `pattern_search` | 从共同基线做坐标正负轮询；无改善的一轮结束后将步长减半 | 无 |
| `gnn_adapt` | 预训练端口 GNN+SAC；与 GT adaptation 相同在线预算 | 计入 GNN 预训练 |

GNN 通过 `ModelConfig.attention_mode='port_message_passing'` 选择，仅将邻域注意力替换为端口特征参与的 MLP 消息及目标节点均值聚合；共享相同参数组 actor、action-conditioned twin critics、SAC、特征和动作合法化。主模型仍为 `local_port_attention` Graph Transformer。两者均为 32 hidden、2 layers；GT 为 4 heads。参数量另行记录，不能称为严格参数量匹配。

固定的是每个在线任务的调用预算；微调相比从零训练仍有额外预训练成本，报告不会把它藏在在线数值中。GNN 本轮只比较 adaptation，未完整覆盖 GNN scratch/frozen 消融。

## 预算、失败与报告口径

一次调用是一个 nominal 候选的 DC/AC 测量包，对应一次 Spectre invocation，包含两个 analysis。reset、warmup、重复候选、已尝试的失败调用都计数；不缓存、不自动重试。成功后仍跑完预算，保留 best-so-far 轨迹。共同初始基线也作为第 1 次候选评价，若它满足规格，首次达标调用数即为 1。

每条候选记录保留 proposal、实际尺寸、网表、测量、有效性、状态、日志与分阶段耗时。`run.json` 汇总首次达标调用数/时间、best reward 与原始指标/单位/尺寸、最大归一化 violation、失败类型、重复候选、推理/更新/总耗时和恢复状态。reward 与 violation 沿用 M3 capped violation 定义，不是额外优化的物理目标。

未达标的 run 保留 `first_feasible_call=null`、`right_censored=true` 和实际 censor 时间/调用数，不把预算终点算成成功时间。中断运行保留已发生的失败与成本，报告列出尚未执行的任务；不会把这些任务伪装成已完成实验。

汇总按 test task/method 分组，保留逐 seed 的首次达标信息及删失，提供 success rate、Wilson 95% 描述区间及 best-reward mean/std。3 个种子不能支持稳定优越结论；确定性 pattern search 的重复运行尤其不构成三个独立搜索轨迹。对仿真结果确定的电路，种子差异主要来自算法随机性，并非制造变化或 Monte Carlo。

`report.json` 单列 train/validation/test 成本、每个架构/seed 的预训练成本、在线边际成本及 `pretraining_plus_online_calls`。该字段仅为预训练加当前在线任务；完整运行成本还包括 validation 诊断及真实恢复验证，以顶层 `calls`/`real_simulation_calls` 为准。计时来自本机实测，不用来承诺其他主机吞吐。

## 复现

```bash
# 完整离线测试，无 Cadence、SSH 或 PDK 要求。
/tmp/analog-optimizer-venv/bin/python -B -m pytest -q

# 三种子，两个训练规格，规格与新拓扑各一个 test task。
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_transfer.py \
  --output artifacts/local/m5-synthetic

# 专用真实 OTA；使用已有配置，97 次 Spectre 的小预算流程验收。
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_transfer.py \
  --origin real --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --reference-measurements artifacts/local/opamp-baseline/simulations/ff6dc7e7c3944d77a0ace70da4d63385/measurements.json \
  --bridge-site-packages /home/fyworkstation/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages \
  --output artifacts/local/m5-real
```

真实命令中的路径只是本机复现记录，程序无硬编码主机/账户/PDK 模型路径。仍只开放 M1/M2 共享宽度 3.6–4.4 µm、5 nm 网格，其他器件固定。新拓扑结构 fixture 增加第二级与负载电流源，动作从 2 维变为 3 维；没有把旧图重命名当成新拓扑。

## 验收范围与下一步

本轮交付 M5 的实验基础设施、合成拓扑流程与真实同拓扑规格迁移 pilot。没有 PVT/MC 调度、跨类别迁移、surrogate、真实新拓扑的仿真后端或正式的泛化优势结论。真实新拓扑需要新增独立 OTA 副本及其可恢复后端，先完成物理基线和测量等价性验证，再冻结拓扑划分并扩大迁移实验。

## 本次离线实测

完整回归：**246 passed，0 failed，0 skipped**。M5 新增 15 项行为测试，覆盖重命名/尺寸变化/权重修改导致的泄漏、分区与任务隔离、冻结参数、权重复制无别名、端口 GNN 混合 batch 与梯度、预算限制、故障成本、右删失和完整实验的 checkpoint 数据来源。原有 M1–M4 测试保留并通过。

[合成完整报告](../artifacts/local/m5-synthetic/67772899459d47aa838aa77abd564e2b/report.json) 与 [冻结协议](../artifacts/local/m5-synthetic/67772899459d47aa838aa77abd564e2b/protocol.json)：seeds 17、29、43；每架构/seed 在两个训练规格上各采样 16 步，共 34 次评价、31 次更新；每个 test task 包含初始基线与 8 个候选。总计 **534 次 synthetic 评价、0 次真实仿真、44.66 s**，其中预训练 204 次、validation 6 次、test 324 次。另有开发期单种子联调 62 次 synthetic 评价，保存在 `artifacts/local/m5-dev`；不混入冻结实验统计，也不产生 Spectre 调用。

| 方法 | 同拓扑新规格达标 runs/3 | 新拓扑达标 runs/3 |
| --- | ---: | ---: |
| GT 从零 | 2/3 | 2/3 |
| GT 冻结 | 1/3 | 1/3 |
| GT 微调 | 1/3 | 1/3 |
| 随机搜索 | 2/3 | 1/3 |
| 坐标模式搜索 | 3/3 | 0/3 |
| 端口 GNN 微调 | 2/3 | 2/3 |

这些数据仅证明跨图动作接口与对照流程可运行。GT 迁移未表现出一致优势；toy reward 是按参数种类定义的二次函数，与真实器件物理无关。两个模型的 actor+双 critic 可训练网络参数量分别为 GT **105,476**、GNN **92,804**，不含 target 网络和单独的熵温度参数。

## 本次真实实测

[真实报告](../artifacts/local/m5-real/21717ace2f564d77b48b6939d49093d6/report.json)、[冻结协议](../artifacts/local/m5-real/21717ace2f564d77b48b6939d49093d6/protocol.json) 及 [机器可读验收汇总](../artifacts/local/m5-acceptance-summary.json)。seeds 为 17、29、43，全部目标在采样前冻结于 `configs/gpdk045_opamp_transfer.json`。

| 划分 | gain 最低值 dB | UGF 最低值 MHz |
| --- | ---: | ---: |
| train | 25.010 | 3.54 |
| validation | 25.015 | 3.55 |
| test | 25.020 | 3.56 |

三者共同约束为 PM estimate ≥90°、功耗 0–2.1 µW、输出 DC 0.2–0.8 V，以及恰好一次向下 unity crossing。PM 仍为已有开环估计，功耗不含真实偏置发生器。这些是当前测试台的验收规格，非产品性能要求。

**97 次 Spectre，全部测量有效，无仿真失败、无自动重试；总耗时 272.80 s。** 预训练 18 次、validation 6 次、test 72 次、末尾恢复复验 1 次。每个架构/seed 的预训练只有初始基线 + 2 个候选、1 次 SAC 更新；每个测试 run 是初始基线 + 3 个候选，学习方法做 2 次更新。此预算足以检查采样/更新/迁移路径，远不足以评估收敛。

| 方法 | 达标 runs/3 | 首次达标调用数（seeds 17 / 29 / 43） | best reward 均值 |
| --- | ---: | --- | ---: |
| GT 从零 | 1/3 | — / 3 / — | −0.005200 |
| GT 冻结 | 0/3 | — / — / — | −0.006838 |
| GT 微调 | 1/3 | — / 2 / — | −0.002263 |
| 随机搜索 | 2/3 | 4 / 4 / — | −0.001154 |
| 坐标模式搜索 | 3/3 | 4 / 4 / 4 | 0 |
| 端口 GNN 微调 | 1/3 | — / 2 / — | −0.002309 |

“—”是未达标、按实际预算右删失，不是缺失后剔除的样本。单个 seed 的 GT/GNN 微调首次达标比随机搜索早，不能抵消其额外预训练成本或另外两个 seed 的失败；**当前没有迁移优于随机/坐标搜索的证据**。按现有成功率及成本，不能给出有依据的预训练成本摊销点。

各 run 退出均核对恢复；最后额外一次仿真验证 M1/M2 均恢复到 **4 µm**。所有 reset 与末尾复验网表 SHA-256 一致：`f7c3a7d9367f64cdeb033563aea65fc0f236a518cabfd49d7eb3372d811610e2`，与 M2–M4 原基线相同。全部记录的基线指标也完全相同：gain 25.000933870852414 dB、UGF 3.5277477990905726 MHz、PM estimate 92.0985749897789°、功耗 1.956295379446648 µW、输出 DC 0.6667594494734167 V。

最初沙箱内连接尝试在连接隧道阶段失败，**0 次 Spectre 调用**；获得沙箱外执行批准后使用同一现有隧道完成本次实验。失败尝试保留在 `artifacts/local/m5-real/23c9eec1958d41dd96d3109e8fd31fa5`，不是仿真失败，也没有启动新 daemon。

后审计加载了 **39 个 checkpoint（合成 24、真实 15）**，验证协议/代码摘要、逐 transition 的来源与规格分区、源权重到各测试初始化的一致性、冻结权重及恢复记录；均通过。审计脚本保留在 `artifacts/local/m5-audit.py`。本轮没有覆盖真实新拓扑，因此 M5 的完整物理泛化验收仍需后续独立 OTA 基线。
