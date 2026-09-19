# M3：PVT 与 Monte Carlo 接口

2026-09-19，按用户最新要求只修改 M3 及之前。实现基础设施、配置、注释和离线纯函数；没有启动 M4、Graph Transformer/SAC、top-k 仿真调度或 Monte Carlo 执行。此次只读核对已有 VM 中的 GPDK045 文件，没有修改原理图或运行真实 Spectre。

## 从实际 PDK 选择工况

当前 OTA 使用 GPDK045 v6.0 的 `nmos1v/pmos1v`、`g45n1svt/g45p1svt` 模型，已有真实基线为 TT／27°C／1.0 V。用户原先的 1.8 V 示例已撤回，不保留为配置。

权威项目配置：[gpdk045_conditions.json](../configs/gpdk045_conditions.json)。选取五个代表点，不做全组合：

| ID | Model section | 温度 °C | VDD V |
| --- | --- | ---: | ---: |
| nominal | tt | 27 | 1.0 |
| ss_hot_low | ss | 125 | 0.9 |
| ff_cold_high | ff | −40 | 1.1 |
| fs_nominal | fs | 27 | 1.0 |
| sf_nominal | sf | 27 | 1.0 |

依据是模型入口 `models/spectre/gpdk045.scs` 的 `tt/ss/ff/fs/sf` sections、`docs/gpdk045_PDK_Model_Report.pdf` 第 1–2 页表 2.1/2.3 的 −40..125°C 范围，以及 `models/spectre/gpdk045_soa.scs` 中 `max_vdd_1v=1.1` 的检查阈值。配置记录上述文件的 SHA-256；仓库没有复制 PDK 模型或文档。

**0.9 V 是项目相对已验证 1.0 V 基线的 −10% 筛选选择，不是 PDK 声明的最低工作电压。** 五种工艺角有模型依据，但这五个 P/V/T 组合仍是工程抽样，不代表 PDK 指定的唯一集合，也不保证覆盖全部 worst-case。模型入口当前加载 SOA OFF，电源边界检查不等于已启用器件端电压可靠性检查。理想输入共模 0.6 V、偏置 0.4 V、负载 1 pF 保持原值，未隐式随 VDD 缩放。

## 已实现的契约

| 接口 | 当前行为 |
| --- | --- |
| `PVTCorner` | 保存 ID、model section、温度、电源，校验有限值；PDK 范围由 profile 检查 |
| `SimulationCondition` | 区分 `nominal/pvt_validation/mc_validation`，提供序列化和工况 fingerprint |
| `MonteCarloConfig` | 保存样本数、seed、process/mismatch/all、统计 section；仅为接口 |
| `NetlistArtifact/SimulationRequest/SimulationResult` | 传递同一工况；禁止给已生成网表重新标注其它工况 |
| `MonteCarloResult` | 逐样本结果、明确 sample index、保留失败、独立记录 Spectre 调用次数 |
| `generate_netlist(..., condition=...)` | 先验证工况，再在导出 job 副本中设置模型 section、温度和 VDD |
| `get_circuit_graph()` | 来自执行副本，VDD 数值与工况一致，metadata 保存工况 |
| `CircuitSizingEnv` | 只接收 nominal，观测和 v2 日志记录工况，结果身份不一致时报错 |
| `run_monte_carlo()` | 显式抛出 `UnsupportedCapability`；不以重复 nominal 冒充统计仿真 |

配置文件可通过 `Gpdk045OtaProfile(..., conditions_file=...)` 显式指定，默认与 mapping 文件同目录。PVT 不增加 sizing 动作维度。结构解析器仍只处理导出结构，不解析 PDK 或统计模型。nominal 执行网表保持原内容和摘要；其它工况仅改变批准的 job 副本中的温度、section 与 VDD，原始导出仍保留。

示例仅说明准备接口，不是自动运行脚本：

```python
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition

condition = SimulationCondition(
    PVTCorner("ss_hot_low", "ss", 125.0, 0.9),
    purpose="pvt_validation",
)
# 在已连接的专用 backend 上显式准备工况网表；不在 nominal env.step 中调用。
artifact = backend.generate_netlist(job_root, condition=condition)
```

future MC 的 `mc` section 来自 PDK 入口；是否正确激活 process/mismatch、样本目录及失败提取仍须以后单独实现和真实验收。目前任何 MC 执行请求都会在远程操作前被拒绝。

## 为以后 top 3 筛选准备的纯函数

[evaluation/corners.py](../src/analog_optimizer/evaluation/corners.py) 不导出网表、不运行仿真，也没有 replay 或训练器：

- `NominalDesign.from_record()` 只导入有效、已完成且有明确 nominal provenance 的候选。旧日志不靠文件名推断工况。
- `select_top_designs(..., k=3)` 在同一问题、nominal 工况和 origin 下按 nominal reward 排序，对实际执行尺寸去重；同分按 candidate ID 固定排序。当前 reward 饱和后的并列不代表已区分所有可行设计的优劣。
- `summarize_corners()` 要求尺寸、工况和 origin 一致，按相同规格统计通过数、失败数及每项最差有效指标和覆盖数。min 取最小，max 取最大，range 检查两端违约。
- 结果完整时计算 `pass_rate = passed / 5` 和 `robust_score = nominal_reward - lambda_failed * failed`，配置默认 λ=1.0。任何已确认失败都令候选 `rejected`，即使 λ=0 也不能通过。
- 缺失、测量或基础设施错误保留 unknown；完整 pass rate 和 robust score 为 `None`。明确归因的已评估 invalid design/nonconverged 才算失败 corner。不会用剩余成功样本伪造完整通过率。

约定未来仅对 nominal top 3 做一次五点验证，最多 15 个确定性工况点；重试另计。nominal reward 保持原定义，后验证结果不进入 nominal replay/normalizer。筛选集合属于 validation，不等同于独立 test 或制造良率。

## 验收与尚未运行的部分

完整测试：`/tmp/analog-optimizer-venv/bin/python -m pytest -q`，**198 passed，0 failed，0 skipped**。覆盖五个工况的 deck/graph/manifest 一致性、nominal 网表兼容、非法工况与 MC 提前拒绝、环境工况隔离、候选去重、失败硬淘汰、未知结果和最差指标方向。测试使用明确的 synthetic 替身，无 Cadence 或 SSH 依赖。

真实证据仍限于先前的 nominal 基线、宽度循环和随机候选验收，见 [环境报告](opamp-environment.md)。尚未真实验证新增 PVT 路径、MC、鲁棒性能或良率。

[analog-optimizer skill 的工况参考](../.agents/skills/analog-optimizer/references/pvt-monte-carlo.md) 另记录未来按预算逐步增加复杂度的建议：稀疏 PVT 抽样、分级 MC 样本预算、统计不确定性、独立最终种子和 CPU/Spectre 与 GPU 学习成本分开计量。这些是后续参考，不是本轮实现。
