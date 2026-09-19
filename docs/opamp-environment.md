# 单 worker 环境与有限随机候选验收

2026-09-19：已完成 `CircuitSizingEnv.reset/step`、动作合法化、规格评价、奖励、失败分类、候选日志及恢复。完整实验执行 **8 次真实 Spectre DC/AC**，全部通过流程验收；包含排查 CDF 取整前的首轮，本次开发共消耗 **11 次真实仿真**。**156 项离线测试通过，0 失败，0 跳过。**

同日后续 M3 接口扩展增加显式 PVT/MC context，完整离线测试增至 **198 项**；没有重跑或增加真实仿真。下文的 8 次实测与旧日志仍是原阶段证据，新的接口验收见 [PVT／MC 接口说明](pvt-mc-interfaces.md)。

## 真实结果

与先前相同的 GPDK045 五管 OTA、1 V、TT、27°C、1 pF。仅修改 `XU1/M1.w` 与 `XU1/M2.w` 的匹配组，范围 3.6–4.4 µm，5 nm 网格。随机种子 `20260919`；候选计划及生成前后 RNG 状态保存在报告内。

本次验收目标：10 Hz 增益 ≥25.015 dB、UGF ≥3.55 MHz、相位裕度估计 ≥90°、VDD 功耗在 0–2.1 µW、输出 DC 在 0.2–0.8 V、向下单位增益交越恰好一次。每项都是必需约束，详细归一化尺度见 [规格配置](../configs/gpdk045_opamp_smoke_specs.json)。这些目标围绕已测基线设置，用于覆盖达标/未达标路径，不是产品要求或独立的优化评估集。

| 阶段 | 执行宽度 µm | 增益 dB | UGF MHz | 功耗 µW | 全部规格满足 |
| --- | ---: | ---: | ---: | ---: | --- |
| 原始基线 | 4.000 | 25.000934 | 3.527748 | 1.956295 | 否 |
| 下边界 | 3.600 | 24.966838 | 3.476153 | 1.950572 | 否 |
| 上边界 | 4.400 | 25.030739 | 3.574150 | 1.961415 | 是 |
| 随机 1 | 4.105 | 25.009131 | 3.540390 | 1.957693 | 否 |
| 随机 2 | 4.245 | 25.019633 | 3.556722 | 1.959495 | 是 |
| 随机 3 | 3.710 | 24.976713 | 3.490923 | 1.952214 | 否 |
| 重复随机 3 | 3.710 | 24.976713 | 3.490923 | 1.952214 | 否 |
| 恢复原始基线 | 4.000 | 25.000934 | 3.527748 | 1.956295 | 否 |

恢复后的执行网表 SHA-256 与初始基线相同，所有保存指标相同；重复 3.710 µm 的网表和指标也相同。程序使用相对容差 `1e-6`、绝对容差 `1e-12` 验收指标。上下文退出后再读回确认 M1/M2 为 **4 µm**，没有留下达标候选覆盖基线。

本次完整实验的脚本计时为 24.58 s，每个候选约 2.67–3.26 s。这是当前机器、已连接会话及这份小电路的单次测量，不代表通用吞吐。候选记录分别包含参数更新/读回、netlisting、graph build、仿真与测量合并耗时；未把 SSH、传输和 PSF 解析进一步分开计时。

- [完整机器可读报告](../artifacts/local/opamp-environment/b69515371dc740d59e6ff35d6d75a0dd/verification.json)
- [环境恢复记录](../artifacts/local/opamp-environment/b69515371dc740d59e6ff35d6d75a0dd/restoration.json)
- [后端恢复记录及 CDF](../artifacts/local/bridge-state/0a581f577f8044ea8e80b7847a3e0903/restoration.json)
- [8 份真实导出的 PyG batch 与摘要审计](../artifacts/local/opamp-environment/b69515371dc740d59e6ff35d6d75a0dd/pyg_audit.json)
- [包含失败首轮的总调用与成本记录](../artifacts/local/opamp-environment/acceptance-summary.json)

## 实际发现并修复的 CDF 取整问题

首轮的基线、3.6 µm 和 4.4 µm 均完成仿真。第一个随机 proposal 对应 4.1067917531630854 µm，实际 CDF 将 `w/fw` 取整为 **4.105 µm**。原先只检查连续范围不够；严格读回验证拒绝该次参数更新，回滚后恢复 4 µm，没有将不匹配值送入 Spectre。

随后单独复现一次回写/读回以保留尝试快照，未调用 Spectre；再为 profile 增加显式 **5 nm 软件动作网格**，在回写前完成 nearest-grid 投影，并拒绝绕过合法化的 off-grid 参数。记录保留原 normalized proposal、投影原因、合法化目标和实际 CDF 值。此网格在上述真实候选中已验证，不宣称已遍历整个范围或确定任意 GPDK045 器件的最小制造网格。

- [失败首轮报告：3 次仿真](../artifacts/local/opamp-environment/886b62d6827b49da9c8a3ca340950565/verification.json)
- [CDF 取整诊断：回滚及尝试读回](../artifacts/local/bridge-state/e03797feda6d4b409432f0549cd14bcc/update-1eb3fe6d0cfa4f839282f71992f60d58.json)

失败首轮的调用数和成本保留，不并入成功样本或隐藏为缓存。修复后从恢复的基线重新完成 8 次验收，合计 11 次。

## 接口与行为

```python
with CircuitSizingEnv(backend, graph, specs, output, max_steps=6) as env:
    observation, info = env.reset()  # 恢复并真实评估初始参数，也消耗一次调用。
    observation, reward, terminated, truncated, info = env.step(
        {"input_pair_width": 0.2}
    )
```

- **动作**：仅接受所有 mutable 参数组的有限 `[-1,1]` proposal。linear/log 绝对映射后使用既有 group projection 处理网格/整数，按 ratio 和原始参数名展开成员。动作越界、缺组、多组在 I/O 前报错，不消耗步数。固定组不下发。
- **图**：`get_circuit_graph(artifact)` 从该导出的真实结构读取，检查结构和执行网表摘要。profile 将 mirror/tail 设为 immutable。环境核对图拓扑、动作契约及实际参数，observations 是独立快照，可直接 `to_pyg(observation.graph)`；派生几何也来自新网表。
- **规格**：min/max/range、unit、正 scale、weight、required、active。缺失、NaN/Inf、错误单位、无效 mask 都不能产生成功。可选缺失指标不参与均值；至少需要一个 active required 规格。
- **奖励**：每项 violation 为到合法区间的非负距离除以 scale，再截断到 1；reward 为负加权平均，位于 `[-1,0]`。目标本身可以为零或负数，不直接用目标做分母。成功独立检查每个必需约束，没有成功 bonus。
- **失败**：明确 `invalid_design/nonconverged` 且 `candidate_evaluated=True` 才产生有限终止 penalty `-1`。测量错误、超时、许可证/传输/后端错误返回 `reward=None`，truncate 且不进入 replay；基础设施失败不伪造下一观测。回写/导出/结构异常记录后抛出，禁止继续 step。未采用 mock 降级或自动重试。
- **预算**：`max_steps` 是每个 episode 的 step 上限，reset 的基线另计。剩余步数进入 observation，耗尽时 `terminated=True`、`bootstrap=False`；不是外部采样 time-limit。默认达标即终止；验收脚本关闭提前终止，以覆盖全部计划。reset 也返回边界信息，不能假定 reset 后一定允许 step。
- **重复候选**：以实际执行参数识别 `duplicate_of`，每次仍重跑、消耗预算；没有仿真缓存。
- **日志与恢复**：UUID 目录、原子 JSON 状态记录，保存 config fingerprint、reset/step、proposal、实际参数、图、规格、指标/mask、结果来源、job/artifact/hash、计时及错误。`restoration.json` 单独确认恢复；恢复失败保留 `recovery_required` 并抛错。日志用于审计复盘，目前不支持从半途失败的 episode 自动恢复训练。

这是普通 Python 环境，不是完整的 Gymnasium 注册环境。`expected_origin` 默认 `real`；测试替身需显式选择 `synthetic`。旧 `MockBackend` 仍不声称具有参数执行或物理仿真能力。

工况扩展后，真实环境从后端获取已配置 nominal，或显式传入 `condition`；PVT/MC validation 请求在连接和回写前被拒绝。每次评估核对 artifact/result 的工况与样本身份，防止后验证结果进入 nominal transition。新日志使用 `sizing-env-v2`，配置、观测与候选记录保存工况。旧 v1 记录缺少显式工况，不能直接导入新 top-k 接口，需要先审计迁移。

## 复现

先保存并关闭同一会话的活动 ADE Assembler/Explorer/Maestro 窗口，保留 Virtuoso 与已有 bridge。脚本使用先前创建的专用测试电路，沿用项目 `state_root` 锁和恢复策略。

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q

/home/fyworkstation/virtuoso-bridge-lite/.venv/bin/python -B \
  examples/verify_opamp_environment.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --reference-measurements artifacts/local/opamp-baseline/simulations/ff6dc7e7c3944d77a0ace70da4d63385/measurements.json \
  --output artifacts/local/opamp-environment \
  --seed 20260919 --random-candidates 3
```

每次生成新目录，不覆盖旧实验。pytest 无需 Cadence、SSH 或 bridge；完整图测试使用已安装 Torch/PyG 的临时环境。新增 53 项测试覆盖动作、单位/有效性、权重与约束、实际图刷新、预算/重复、origin/参数绑定、阶段异常、连接故障和恢复失败；故障注入明确为 synthetic。所有 156 项测试实际通过。

另用图环境离线审计了本次 8 份真实导出：执行副本摘要一致；每图只有 1 个 mutable 组、2 个 mutable 成员；动态宽度与实测记录一致；8 图 PyG batch/unbatch 成功且无跨图边。审计文件保存 Python/Torch/PyG 版本及实现/配置的 SHA-256。上游 bridge checkout 仍干净，commit 保持 `38aa8f22b2617e9b29e3b9f3a5770f27a938e1f0`。

## 边界与下一步

本页记录的 M3 实验没有训练神经网络，也没有证明随机搜索或 RL 的性能优势。该实验只验证这份电路的 DC/AC 单 corner；相位裕度是开环单位负反馈估计，不是 STB；功耗不含实际偏置发生器。未做 PVT、瞬态、全网格覆盖或泛化。

本页记录的 M3 交付当时止于工况接口及纯函数验收。用户随后明确授权进入 M4；新的模型、SAC 与真实小验收见 [M4 记录](m4-graph-sac.md)，本页历史仿真数量保持原值。
