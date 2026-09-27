# 工况、Monte Carlo 与算力预算

2026-09-26 更新：`docs/plan-reward-v2-real-flow.md` 授权 OTA7 的显式 `always`
训练计划（nominal + 四个 screening corners），其他 profile 拒绝训练 corners；post-validation
仍独立。reward-v2 已通过 OTA7 有界真实 A/B/C 验收：73 次 Spectre（A21、B44 含一次
记录失败、C8），0 次不确定调用，全部物理恢复和基线复验通过。用户确认 unknown license，
并明确批准 B44/总77；正常许可流程未被绕过。A 的原生派生/独立导出网表、PSF/供电
检查通过；C 的共享预算拒绝剩余四槽时启动五工况。默认仍是 corners off；MC 未实现。
无 robust-feasible 设计，不证明 reward 优势、worst-case 完整性或良率。见 `docs/reward-v2.md`。

## 当前生效的范围

早期工况接口任务限定在 M3；后来的 M4/M5/M6 和 reward-v2 授权不受该历史范围限制。
nominal SAC、独立 Corner check 与显式 OTA7 五工况训练已实现。通用 top-k 批处理和 MC
执行仍未实现。以下“以后”建议不自动启动实验，研究调用预算仍需单独决定。

默认 nominal 模式不吸收事后 PVT/MC 结果。显式 `always` 模式按整个计划预留调用，
每步都执行五工况并进入 v2 reward/replay；reset 只跑 nominal，不冒充完整覆盖。
两种模式不可在 exact resume 中混用。五个筛选点仍不是全组合或 yield 检验。

## 工况来源与当前 GPDK045

先读目标 PDK 的模型入口、器件类型、温度范围、SOA/电压说明及统计模型；不要照搬用户已经撤回的示例，也不要把别的 PDK 的 SS/FF/MC 名称或电压写成默认值。

当前 `configs/gpdk045_conditions.json` 来源：

- `models/spectre/gpdk045.scs`：tt/ss/ff/fs/sf，以及单独的 mc 入口。
- `docs/gpdk045_PDK_Model_Report.pdf` 表 2.1/2.3：对应模型的 −40..125°C 与五种工艺角。
- `models/spectre/gpdk045_soa.scs`：`max_vdd_1v=1.1`，注释解释为 1 V +10% 的检查阈值；不能仅凭器件名或手册某页的旧 1.2 V 标注放宽范围。

保留当前已验证 TT/27°C/1.0 V nominal。工程筛选集合是 TT/27/1.0、SS/125/0.9、FF/−40/1.1、FS/27/1.0、SF/27/1.0（温度 °C，电压 V）。0.9 V 是项目 −10% 筛选点，不是 PDK 声明的最低电压。这个集合不证明穷尽所有 worst-case。原模型入口的 SOA 为 OFF；限制测试台供电不等同于已执行全部端电压可靠性检查。

当前理想输入共模 0.6 V、偏置 0.4 V 不随供电缩放，负载 1 pF 固定。改变这一策略需要新配置与基线，不能在 PVT 扩展时隐式调整。

## 基础设施契约

- 静态电路与 nominal 几何继续使用统一 CircuitGraph/参数组；同尺寸匹配不禁止 PDK 注入器件随机 mismatch。
- PVT 是外部评价条件，不是 sizing action。真实 request、不可变网表、result、图 metadata 和日志的 context 必须一致；VDD 特征与实际执行值一致。
- MC 必须区分 process/mismatch/all、模型 section、sample count、seed 与逐样本 index。当前接口是预留能力；未实现必须显式 UnsupportedCapability，不能运行 N 次 nominal 充数。
- 保存每个失败/未知样本和工况，分别统计设计失败、测量失败与基础设施失败。排除故障后的成功样本比例不能冒充全计划良率。
- 未来缓存 key 覆盖实际尺寸、模型/PDK 指纹、测试台、PVT、MC 设置与 sample identity、分析精度、测量版本。只用 width 或 seed 都不够。
- 同时计候选数、corner/sample points、Spectre invocations、失败/重试与耗时；一批 MC 可以只有少量进程调用，但有许多样本成本。

## top 3 后验证数据规则

先按同一电路、规格、nominal context 的有效 nominal_reward 排序，对实际执行尺寸去重。同分时采用固定规则并记录；当前 reward 饱和后不能声称已区分所有达标设计的优劣。少于三个有效独立设计时返回实际数量，不复制凑满。

每个候选的五个结果应有相同尺寸、origin 和准确的 corner identity。不能混用另一候选或旧工况结果。固定每个 corner 的所有 required specs 共同判定通过。

```
robust_score = nominal_reward - lambda_failed * number_of_failed_corners
```

lambda 是显式配置，当前工程默认 1.0，不是理论最优值。robust_score 是后验证辅助排名，**只要有一个已知失败 corner，该设计就不能被接受**。缺失或基础设施/测量异常时保留 inconclusive；已确认失败可先标 rejected，但不补造未完成部分的 score 或 pass rate。全部计划完成后才计算完整通过率。

worst-case 对 min 取最小值、max 取最大值、range 检查两端偏差，同时保存对应 corner 和有效覆盖数。不要将均值代替约束达标，也不要将观察到的最差点称为整个工艺空间的数学 worst-case。

## 以后明确授权时可选的低成本扩展

这些是建议的实验设计，未实现，也不改变当前 nominal-only 默认。

1. **先保留训练与验证分离。** 在训练完成或显式设置的检查点冻结候选集合，只给 top 3 做五点筛选。单轮最多 15 个确定性工况点，另计失败/重试；不要在每个 SAC step 后都自动付出这笔成本。
2. **若需要 PVT-aware 训练，先做少量 corner 抽样。** 例如每个 sizing step 只抽 1–2 个训练 corners，将工况或评估计划作为显式条件；周期性用完整验证集合检查。保留难点 corner 的采样概率，同时保证其它训练条件仍有覆盖。抽样 reward 不等于已完成全 corner 验证；与 nominal 基线比较真实点数、达标率和总时间。
3. **MC 先用于有限候选，逐级分配预算。** 例如 8 → 32 → 128 个样本仅作为预算级别示意；先淘汰明显失败者，只给有希望的候选追加样本。任何良率结论需要对应样本数、统计方法和置信区间，小批全通过不能证明高良率。自适应停止/选择需使用适用的区间或明确独立的最终验证，不能套用未经校正的固定样本结论。
4. **比较候选时可研究配对随机样本。** 在模型与实例身份可复现的前提下，用共同随机样本降低比较噪声；记录 seed/采样法/统计变量，不假设只设同一 seed 就跨拓扑一致。最终验证使用独立保留的随机样本，避免反复优化到固定种子。
5. **最后才研究统计鲁棒训练。** 可比较小批统计样本的期望 violation、尾部风险或良率约束；目标、样本数和不确定性进入明确契约，先测试奖励方差和偏差。不直接把一次随机失败当作确定性设计标签，不把小批 worst sample 称为可靠尾部估计。与原 nominal replay 分版本管理，迁移 checkpoint 时校验 context/reward/schema。
6. **按测量后的瓶颈分配算力。** GPU 主要用于图网络，Spectre、netlisting、传输和 PSF 的成本独立计时。先复用一次尺寸更新/导出的不可变 job 副本；并行只能使用隔离结果目录、允许的 CPU/内存/许可证与安全会话隔离。不能用“有 GPU”推断多 corner 仿真廉价，也不默认改成多 worker。

当前不引入 surrogate。未来任何加速方案都作为独立实验，与相同总仿真预算的 nominal+后验证方案比较。

## 统计语义参考

- [Cadence：process、mismatch 与 all 的区别](https://community.cadence.com/cadence_technology_forums/f/custom-ic-design/20466/monte-carlo-simulation-global-local-vs-local-and-process-vs-mismatch)。具体 section 组合仍以本地 PDK 为准，不能默认所有 deterministic corners 都支持相同统计模式。
- [Cadence：Monte Carlo sampling 与置信区间](https://community.cadence.com/cadence_blogs_8/b/cic/posts/the-art-of-analog-design-part-2-monte-carlo-sampling)。corner pass rate、模拟模型下的统计通过率与真实制造良率需分别表述。
