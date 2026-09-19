# M5：真实同类新拓扑补验

2026-09-19，用户要求补齐 M5 未完成部分。本轮新增独立两级 OTA，验证从五管 OTA 到真实新拓扑的迁移，同时重新对照同拓扑新规格。M6 未启动。

## 电路与动作

原 `GATOR_TESTS/ota5_v1` 和 `tb_ota5_ac_v1` 保持既有配置与权限。新增 `ota7_m5_v2` 和 `tb_ota7_m5_ac_v2`：第一阶段为电流镜负载差分对；增加 PMOS 共源输出管 M6、NMOS 电流源 M7，以及 1 pF Miller 电容 CC。交换第一阶段输入极性，使 VOUT/(VINP−VINN) 保持低频同相，沿用差分 AC 测量定义。

新电路含 7 个 MOS、内部 CC、外部 1 pF CL 与原四个理想电压源。解析图为 13 个器件节点，精确端口 incidence 同构检查确认它与原图不同。它从原 OTA 扩展而来，是同一拓扑族的结构留出，不代表独立采样的广泛电路分布。

| 参数组 | 基线 | 范围与约束 |
| --- | --- | --- |
| 输入对 M1/M2 | 各 4 µm | 3.6–4.4 µm，5 nm 步长，共享一个动作 |
| 输出级 M6/M7 | 8 / 2 µm | M6 7.2–8.8 µm、20 nm 步长；M7 为 M6/4，因此仍是 5 nm 网格；共享第二个动作 |

固定长度、fingers、multiplicity、镜像与尾管、补偿及负载。原五管配置仍只有输入对一个动作。新 profile 不扩大旧 profile 的权限。CDF 回写后检查实际宽度、比例、派生 geometry、固定器件和端口；原生导出再次对照参考图及 CDF。退出时恢复全部可调器件，并核对其完整 geometry。

创建阶段曾尝试 M6=16 µm；PDK CDF 将单指宽度截为 10 µm，读回验证拒绝继续。该失败创建只留下本次创建的未完成 `ota7_m5_v1` 核心单元及本地证据，**0 次 Spectre**；没有覆盖、删除或修复用户其他电路。成功版本将 M6/M7 同比缩小到 8/2 µm。两次创建前后原五管电路的完整读回均相同。

## 基线与参数域验收

[七次真实验收](../artifacts/local/m5-ota7-qualification/928f514a0f4f405b8fca9121c22edb51/verification.json) 包括基线、仅输入对上界、重复基线、仅输出级上界、两组共同下界、两组共同上界和恢复。均为 nominal TT/27°C/1.0 V，全部有效。重复三次基线的执行网表摘要及全部指标完全一致；两个动作均真实改变网表和物理响应；七管 operating points 均提取。最后完整 CDF 快照恢复一致。

| 基线指标 | 实测值 |
| --- | ---: |
| 低频差分增益 | 53.283526 dB |
| UGF | 3.232190 MHz |
| 相位裕度估计 | 27.166775° |
| 电源功耗 | 3.122063 µW |
| 输出 DC | 0.373218 V |

PM 是开环单次向下 unity crossing 的单位负反馈估计，未做 STB 验证；该基线裕度较低，不作为产品设计指标。功耗不包含理想偏置源所替代的实际偏置发生器。原生导出参考和适配器重新导出的执行网表一致，测量使用同一 DC/AC 精度与差分归一化；未宣称与另一套 ADE/STB 测量等价。

## 冻结实验协议

[新拓扑规格](../configs/gpdk045_ota7_transfer.json) 要求增益 ≥53.30 dB、UGF ≥3.24 MHz、PM estimate ≥30°、功耗 0–3.24 µW、输出 0.3–0.5 V，且恰好一次向下 unity crossing。源电路沿用原先冻结的 train/validation/test 规格。

规格在上述电路调试/参数域验收之后、迁移实验之前确定，因此属于前瞻冻结的 nominal 验收实验。新拓扑没有进入源模型训练或统计拟合，但调试者已经观察过其基线与若干边界；不能称为完全盲测。七次验收不进入 replay，单独计入成本。

- seeds：17、29、43；GT 与 port-GNN 每种、每 seed 在源 train 上各做 16 个候选，另计一次 reset。
- validation：GT 冻结后诊断，共 2 次调用/seed，不选模型或超参数。
- 每个 test task/seed：GT scratch、GT frozen、GT adapt、random、pattern search、port-GNN adapt；每方法 12 个候选加一次 reset，不提前成功停止。
- 每个适配任务使用独立 replay 和新优化器；只复制同架构权重与 alpha。测试后不回写源模型。
- 保持原 SAC、32 hidden、2 layers、4 heads、batch size 2、固定物理归一化及 nominal reward。M5 六方法沿用原比较矩阵；其他编码器可以通过 `--encoders` 显式选择并重新计算预算，本轮没有宣称六架构完整比较。
- 共享 Virtuoso session 下，各 episode 串行获得同一把锁，并按电路路由独立配置和基线检查；本轮不是并行吞吐实验。每次候选都经过真实 CDF/原生导出和新的 Spectre 调用，不缓存、不重试。
- 计划 576 次实验评价，额外 2 次结束后的基线复验；加上先前 7 次新拓扑验收，总预算 585 次实际调用。原 M5 首轮的 97 次属于历史成本，不混入本轮统计。

## 结果与复现

完整离线回归 **440 passed，0 failed，0 skipped**；仅有上游 TorchScript 弃用提示。真实实验完成 **578 次调用**，加上新电路资格验收的 **7 次**，本轮共 **585 次 Spectre**，全部测量有效，无仿真失败、无重试、无缓存命中。实验完成 36 个测试 runs、288 次实际 SAC 更新；源训练及测试任务学习合计 312 条新经验。

[完整报告](../artifacts/local/m5-real-topology/b94f8650edd347168e3a30c064b0f04c/report.json)、[冻结协议](../artifacts/local/m5-real-topology/b94f8650edd347168e3a30c064b0f04c/protocol.json)、[独立审计](../artifacts/local/m5-real-topology/b94f8650edd347168e3a30c064b0f04c/audit.json)、[最终 CDF 与模型摘要核对](../artifacts/local/m5-real-topology/b94f8650edd347168e3a30c064b0f04c/final-inspection.json)。

| 方法 | 同拓扑新规格达标 | 真实新拓扑达标 | 新拓扑首次达标调用数（17 / 29 / 43） | 新拓扑 best reward 均值 |
| --- | ---: | ---: | --- | ---: |
| GT 从零 | 3/3 | 0/3 | — / — / — | -0.003110 |
| GT 冻结 | 0/3 | 0/3 | — / — / — | -0.044415 |
| GT 微调 | 3/3 | 1/3 | — / — / 3 | -0.000348 |
| 随机搜索 | 3/3 | 1/3 | 9 / — / — | -0.001364 |
| 坐标模式搜索 | 3/3 | 3/3 | 10 / 10 / 10 | 0.000000 |
| port-GNN 微调 | 3/3 | 2/3 | 6 / — / 3 | -0.000671 |

“—”表示 13 次调用预算内未达标，按右删失保留，不是缺失样本。报告还保存每个 run 的首次达标时间、失败类型、重复候选数、best-so-far、原始指标/单位/尺寸和 Wilson 区间。reward 仅是 capped violation 汇总，所有达标点均为 0；没有额外优化某个物理性能或把不同可行点排出质量优劣。

**当前没有 GT 迁移优于随机或坐标搜索的证据。** GT 微调在新拓扑上的达标率与随机搜索同为 1/3，却还需每个 seed 17 次源预训练调用；GT validation 另有 2 次诊断调用。port-GNN 微调为 2/3，但只有三个种子，且同样有预训练成本，不能据此宣布稳定迁移优势。坐标搜索在新拓扑的三个种子均于第 10 次调用达标。

成本为预训练 102、validation 6、test 468、最终复验 2 次；7 次新电路验收另外列账。每个源 checkpoint 在两项测试中重复使用，各目标任务的微调经验不回流源模型。GT 的 actor+Q1+Q2 共 105,476 参数，port-GNN 共 92,804 参数；这里保持宽度/深度相同，未声称参数量匹配。

实验执行与最后两次复验共 **1763.75 s（29.40 min）**，不含电路搭建、7 次前置验收和入口导入时间。各阶段 wall-clock、推理、更新和候选耗时在报告中单独保存。

独立审计加载 **24 个 checkpoint**，核对源码/协议/配置摘要、每条 transition 的真实来源与任务规格、源训练不含新拓扑器件、复制权重与冻结权重、逐候选动作比例/网格、Spectre 调用证据及 reward 重算；每个 checkpoint 两次加载后的下一次 SAC 更新损失与权重精确一致。这些本地恢复检查不产生新的仿真或实验训练数据。

所有 episode 均恢复；实验后两个电路各追加一次基线仿真，执行网表及全部指标与各自基线一致。随后独立只读检查确认原五管和新七管的完整 CDF 快照均与本轮开始前/创建参考完全相同。PDK 入口与 MOS 模型文件前后 SHA-256 与原 M2 基线相同；这不是整个 PDK 的递归摘要。

本轮补齐 M5 尚缺的真实同类新拓扑闭环与固定预算迁移验收。范围仍是一个源拓扑、一个结构留出拓扑、三个种子和窄宽度域的 nominal 实验；不代表充分收敛、普遍泛化或迁移优越性。PVT/MC、跨类别迁移、surrogate 与 M6 未在本轮启用。

复现现有已建立电路的实验：

```bash
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_real_topology.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --target-creation-receipt artifacts/local/m5-ota7-v2-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --reference-measurements artifacts/local/opamp-baseline/simulations/e89c0a254d034f8fa40fb0dcf7995c50/measurements.json \
  --target-qualification artifacts/local/m5-ota7-qualification/928f514a0f4f405b8fca9121c22edb51/verification.json \
  --bridge-site-packages /home/fyworkstation/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages \
  --output artifacts/local/m5-real-topology
```

加 `--dry-run` 仅检查配置、已验收网表摘要、结构划分和调用预算，不连接 bridge、不创建后端或运行 Spectre。以上路径仅为本机复现记录；连接、库、receipt、模型文件与参考测量均由 CLI 显式提供。

离线回归：`/tmp/analog-optimizer-venv/bin/python -m pytest -q`。真实结果审计：`/tmp/analog-optimizer-venv/bin/python -B examples/audit_real_topology.py artifacts/local/m5-real-topology/b94f8650edd347168e3a30c064b0f04c`。审计只读已保存结果，加载可信本地 checkpoint 并验证下一次更新的精确恢复，不产生新的 Spectre 调用。
