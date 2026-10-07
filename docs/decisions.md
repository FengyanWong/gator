# Current state (2026-10-07)

A summary for new sessions; everything below is the chronological record, oldest first, left as written.

- **Six-circuit encoder baseline (7.244, plan only):** [A/B/C runbook](plan-encoder-baseline-abc.md)
  fixes OTA5t, OTA7t-width, LDO1, LDO2, RING3 and VCO_linear_c as the reusable suite. New A/B/C
  runs use the relaxed LDO HF PSRR targets (-3/-2.3 dB), fixed existing starting vectors, the common
  41-slot registry and matched 800-launch scratch/fine-tune recipes (1e-3, eight updates, target-only;
  loaded primary arms reset temperature to 0.01). Primary C trains every architecture separately on
  the same eighteen historical A/B archives of those six families (15,800 recorded evaluations).
  Encoder-specific A/B data, rehearsal and OTA8m are separately labelled extensions. Baselines are
  required per circuit/start and reusable only after equivalence checks. Historical verdicts are
  preserved; this request changes documentation only and starts no physical or training work.
- **Encoder comparison on the six circuits (7.256, plan only):** [plan-encoder-comparison.md](plan-encoder-comparison.md)
  instantiates the A/B/C runbook for GraphGPS and the parameter-group cross-attention encoder: the twelve prepared
  runs of 7.231 are stage A; B on the `_b` tasks from each encoder's own A model; C from one offline general model
  per encoder on the 18-archive common pool. Two proposed departures from the runbook, for the user to decide: the
  registry is the task's own in A/B and the 41-slot list in C, and loaded arms keep their learned temperature (as
  every recorded GT run did); GT needs two relaxed-target LDO A runs and two LDO B fine-tune runs for matched
  references. Pilot budget for both encoders 64,466 launches, with the held-out stage D on the folded cascode `mscr_otafc` and
  the telescopic cascode `mscr_otatc` that the session "Task button and fine-tuning comparison plan" is building (its
  record pending; OTA8m does not count as held-out); stage A alone 11,276. Nothing started.

- **General-network offline experiment (7.233–7.243):** the user authorized the plan in
  [plan-general-network.md](plan-general-network.md), including mandatory baselines for all six start-C tasks.
  Workbench-only training and rehearsal preserve the optimizer digest. Rehearsal is an explicit exception to
  fine_tune's default target-only batches: its bounded, pinned source training partition supplies half the batch,
  with independent resumable sampling; target replay starts empty. Source validation and C baselines never enter it.
  General/OTA5t-only models have completed 20,000 offline updates. Offline diagnostics allow the planned real probes;
  the complete six-circuit comparison misses the overall criterion: C1 on three (four required), C2/C4 on all six.
  Both LDOs pass C3; own OTA5t's 91% early versus general's 83% satisfies C5. This one-seed recipe comparison does not
  isolate pretrained weights. Historical source costs are 17,124 / 2,400 evaluations,
  counted separately from new launches. C qualification preserves failed designs: the four OTA7t baseline measurement
  errors were explained by retained STB waveforms below unity across the recorded sweep, without rerunning or filling
  missing metrics; both LDOs' analogous failures were reviewed likewise. All six C baselines are qualified with 64 random
  draws each, zero learning and 391 launches: LDO2's periodic reset check required one supplemental exact-seed draw.
  Spent cost includes blocked runs and the supplement. All six frozen probes and thirteen S/G/O arms are complete;
  every independent training audit and restoration passes. Final phase-2 cost is 12,591; `phase2-reviewed.json` pins
  the complete result. Phase 3 now has owned `mscr_ota8m`/`tb_ota8m` cells and a qualified 65-design baseline:
  all valid, 64 random draws, zero learning, all measured DC screens pass (maximum terminal difference 0.723 V).
  Baseline-only rank-28 goals are frozen in saved revision 2. Phase 3 completed: frozen probe 0/300, scratch 486/800,
  general 24/800, all valid. Early S→G is 1→0/100, late 245→22/266: C1/C2 fail, C4 passes its fixed definition.
  All restorations and independent audits pass; the queue exited. Required work is complete at exactly 14,556 new
  launches, with seven qualified baselines, seven frozen probes and fifteen learning arms. `experiment-reviewed.json`
  pins final evidence and source invariance. This series-RZ compensation variant of the pooled OTA7t is not a new
  amplifier family; the complete G recipe underperforms scratch here. Optional extra seeds/folded-cascode work remain unstarted.
  The subsequent user-authorized OTA8m follow-up is complete (section 22): unchanged G reached the 75/100 criterion
  at charged cost 1,370 and stopped after 588 extra launches, final window 76/100. Fresh original-general weights with
  scratch's 1e-3/eight-update/target-only recipe pass 491/800 (late 217/266), versus original G 24/800 (late 22/266).
  Scratch's 486/800 and stronger late 245/266 prevent a clear claim of benefit over scratch. All audits/restorations
  pass; source model/pool/runtime are unchanged, and a verified original-G-800 snapshot preserves historical evidence.
  Follow-up cost is 1,388; total new cost is 15,944. Both original frozen-protocol verdicts remain unchanged.

- **Optimizer source digest:** `0b0808bcbf8a7d22254292b1ef60476743b043ecd8ad59cc9f0320954a7dbac8`, set by `40d1249`
  (record 7.228, 2026-10-06: GraphGPS and parameter-group cross-attention added, authorized by the user; see
  [implementation](global-encoders.md); no real-simulator comparison or transfer-advantage claim; 7.228 alone on `5560c01`
  would hash `061768e0...`, a tree never committed). Before it:
  `aafdd71dfcd1b2008f997fb91d211a614f91822d9e4afeabfe4ac88c6d1da38e`, set by `71f95c3` (record 7.226, 2026-10-06: the LLM
  search package `search/` and `ActionMapper.encode` removed with the LLM search methods; nothing else in the package
  changed). Before it:
  `4aebbfab2176605c6e984d3b42ae622335246dfed693c5b9cc39f942c0aaad73`, set by `510ba0e` (record 7.221, 2026-10-06: a
  learner step takes its replay sample lent instead of deep-copied, skips the next-state work when the discount is
  exactly 0, and keys the input cache by digests worked out once; every result and random-number state identical;
  input cache 8,192 entries). Before it: `f83342bcc50a7b385cadad1770d8ae06962d48fa4cdbcb76ceceef08bcb7cc77`, set by
  `ab34f03` (record 7.149, 2026-10-02: the windows are checked before each native export only, not before every
  write). Before it:
  `34bc85f4472fddf90a0245515121c4ffc2dd4632ce30561c9026e46efb41e89b`, set by `1c308a5`
  (records 7.137, 7.140, 7.142 and 7.143, 2026-10-02: the native preparation reads the cell three times per
  candidate, not five; by default it builds most netlists from the readback, with a native export every 5th candidate; a
  value one float step past its bound counts as the bound, in the group check and in `ActionMapper.encode`; up to 6
  Spectre lanes instead of 4). Before it:
  `41983cc7977168096a9517cdd08528e84a7ea2bd18ea76b0777e1ccbb0c8234e`, set by `c700032`
  (record 7.144: the GPDK045 profiles' copied checks merged, behaviour identical, 2026-10-02). Before it:
  `4632786135d13ed7775237f3139c37f4848e7b40e0efe7b0b0360bafb5df7270`, set by `8edbf6d`
  (record 7.132: the Spectre parser reads PWL `[ ]` arrays, 2026-10-01). Before it: `0d045b8e...`, set by `5362ebb`
  (record 7.129: the optimizer fixes held back from review round 5, 2026-10-01); `f42a3098...`, set by
  `898b134` (record 7.126: corner jobs two at a time, every 5th reset simulated, Maestro results not parsed);
  `100945fb...`, set by `4634200` (LLM sizing, records 7.116 and 7.120); `3f00832c...` before that, set by `8cf53ae`
  (reward v2.1).
- **Encoders:** `graph_transformer` (default), `rgcn`, `gatv2`, plus experimental `graph_gps` and
  `group_cross_attention`. The new encoders support optional random-walk structural inputs and all four workbench
  run modes. They preserve the parser and SAC/action contracts. `port_gnn` was removed on 2026-09-24; `mlp` and `gcn`
  on 2026-09-26, when `gatv2` replaced `gat` (GATv1).
- **Reward:** v2.1 ([reward-v2.md](reward-v2.md)). Schema defaults keep the old arithmetic: capped violations,
  worst-spec share 0, objective and margin weights 0, conditions `off` (nominal only), gate band 0.5, objective shape
  `clipped`. New workbench configurations start with the set compared in training on 2026-10-05 (record 7.183):
  compressed violations, share 0.5, objective and margin bonus weights 1, objective shape compressed. Corner training
  (`always`, `after_nominal`) was offered for `real:gpdk045_ota7` only; no task has it since 2026-09-30 (7.128).
- **Older checkpoints** resume exactly only under their own source: digest `4aebbfab...` (record 7.221) from `510ba0e` up to
  `5560c01`, the commit before 7.226's `71f95c3` - the fine-tune comparison's runs (record 7.227, started 2026-10-06 06:58
  from a copy of `5560c01`) are saved under it; digest `f83342bc...` (record 7.149; every save
  point written before record 7.221, the eight viewing copies of 2026-10-05's Spectre runs in `outputs/` included) from
  `ab34f03` up to `2825305`, the commit before 7.221's `510ba0e` - checked 2026-10-06: that source loads the GATv2 run's final save point
  and two loads give identical next updates, the 7.221 source refuses it; under the new source such a save point still
  loads for fine-tune and frozen (a warning) but not for Continue; digest `02127bc3...` (M6 pilot, six encoders) from
  `bbdfe36`; `aa987cf0...` (five encoders incl. MLP, GCN, GATv1) from `9bc488f`; `f087a4ce...` (reward v2) from
  `1135b8b` up to the commit before `8cf53ae`; `3f00832c...` (reward v2.1) from `8cf53ae` up to the commit before `4634200`; `100945fb...` (LLM sizing) from `4634200` up to the commit before `898b134`; `f42a3098...` (record 7.126) from `898b134` up to the commit before `5362ebb`; `0d045b8e...` (record 7.129) from `5362ebb` up to the commit before `8edbf6d`; `46327861...` (record 7.132) from `8edbf6d` up to the commit before `c700032`; `41983cc7...` (record 7.144) from `c700032` up to the commit before `1c308a5`. Digests never committed (`66ce02ab...`, `046e35c6...`, `78e8ca37...`, `c3a340b9...`, `e3f8c5b8...` and `efa93649...`, the working trees of records 7.137-7.143, used by scratch trial runs only; `75c7cfac...`, `5e8a1bc1...`, `11e62657...`, `3473ed9c...`, and
  `27a36b2b...`, the LLM sizing build before the duplicate-check fix, which Astra's acceptance evidence names) are in
  the entries below.
- **Tasks:** since 2026-09-30 (record 7.128) the workbench offers only the user's saved tasks (the MScR library) and
  ngspice tasks: no MOCK task (the tests register a stand-in) and no built-in verified circuit; OTA7 and LDO went with
  their example files, so the M5/M6 audits re-validate from a checkout before that commit. No task trains at corners.
- **Monte Carlo:** not implemented; a plan only ([plan-finalist-monte-carlo.md](plan-finalist-monte-carlo.md)).
- **LLM sizing:** four modes implemented; free calibration complete (80 runs / 4,800 candidates / zero passes)
  ([brief](brief-llm-sizing-for-astra.md), [implementation](llm-sizing.md)). The user authorized feasibility-only
  calibration with fixed starting bias currents for every arm and independent upstream rechecks of every pass.
  The old short-run selection rule qualified no circuit. The user has now removed it: B3-eligible circuits remain
  eligible; the comparison plans equal 2,000-candidate runs (provisional), uncapped constraint progress and independent
  re-simulation of every pass, including comparison arms. Historical results are preserved; no new runs are started.
  Positive-design parity remains unqualified (G9). Protocol revision record 7.122: final full suite 1615 passed,
  one expected Agent-schema failure, zero skips; current evidence includes the F1 fix. The prior full suite
  passed 1,581 tests with one expected Agent-schema failure. The duplicate-check issue on continuous rows that kept
  G6 partial was fixed in the package afterwards (record 7.120; 1,601 tests with its own); the gate evidence predates
  the fix. The tested frontend and backend were deployed on port 8765 at the user's request (record 7.123):
  1,615 tests passed with one expected failure, 123 scratch browser checks passed, and the live page rendered all
  four methods. Core feature commits are `4634200` and `7c7a0ff`; the protocol revision is in `d8b8c4f`.
  Paid slices remain unapproved. G10 retains the historical server-rejected request.

# M1 决策 — 2026-09-19

- 范围严格限制于附件最后的 First Coding Task：后端抽象、解析、规范图、PyG、离线测试与 demo。后续 Graph Transformer + goal-conditioned SAC 方向保持不变，此次不生成模型或训练骨架。
- 工作目录起初只有 skill 和用户已有 `test.txt`；没有可复用项目代码，也没有有效 Git checkout。保留这些已有文件。
- 真实接口来源明确为 `Arcadia-1/virtuoso-bridge-lite`。当前 WSL Python 无 `virtuoso_bridge`，PATH 中无 bridge/Virtuoso/Spectre；VM/profile/PDK 未提供或核实。因此不编造真实 adapter，不触发连接、写设计或昂贵仿真。
- 核心模块使用 Python 标准库和 JSON dataclasses 配置；Torch/PyG 作为可选 extra，便于无 Cadence/GPU 时先验收解析。
- 电路使用 device-net terminal multigraph；参数组用独立绑定表，PyG 自定义该表 batch offset。静态结构和动态尺寸分开，但本阶段不实现缓存系统。
- 模型到器件类型/端口/参数别名映射显式配置。synthetic 模型映射仅用于结构测试，不宣称 PDK 语义。语法支持边界、未知值和不支持能力见 README。
- 当前没有共享 encoder、action head、reward 或训练 checkpoint 的工程决定；留待对应阶段。无架构方向变更。

# M2 运放基线 — 2026-09-19

- 用户明确表示没有现成基线，要求搭建基础 opamp。创建独立 `GATOR_TESTS` 库，绑定已安装的 GPDK045 v6.0，新增 `ota5_v1` 和 `tb_ota5_ac_v1`；复用已有 bridge/SSH/daemon，不修改已有 VCO。
- 核实本地 bridge 0.8.0、commit `38aa8f22b2617e9b29e3b9f3a5770f27a938e1f0`；Virtuoso IC23.1、Spectre 23.1.0.242.isr1。凭据保留在已有 profile，程序通过显式 `--env` 绑定；PDK 文件只在已有 VM 上读取/使用。
- 采用五管、单级、单端输出 OTA，理想电源/偏置，1 pF 负载。先验证 DC/AC；不要求当前尺寸已优化，不把五管 OTA 的结果推广到通用运放性能。
- GPDK045 的 PAS CDF 参数回调必须用 instance CDF、`cdfgForm=nil`、`PasCdfFormInit`。已验证 `w/fw/l` 及派生扩散面积/周长读回更新，通用上游 setter 不用于这些 MOS。analogLib 接地使用 `gnd!`，导出为 Spectre `0`。
- 导出接口的默认 model section 为 `mc`，本实验明确从原始结构文件构建新的 `tt`、27°C DC/AC 测试台；保留完整原始导出包和执行网表，不宣称与 ADE 历史结果等价。
- Parser 仅增加原生无括号 subckt 声明的支持；PDK include 不送入图解析器。图映射端口来自实际 CDF `termOrder=(D G S B)`。
- 三次真实运行：原始 CL=1 pF、仅 job 副本 CL=1.1 pF、原始 CL=1 pF 复跑。执行网表摘要、测量、PSF 和日志均保存；不需要修改/恢复原理图。
- 已确认上游 bridge 0.8.0 的宽泛错误提取会把正常 license 信息与 `0 errors` 组合为 `license error`。保留该原始诊断，并以退出码、Spectre 完成摘要、显式错误标记和所需有限测量独立验收；未修改上游安装。
- 真实能力当前位于可运行实验脚本，尚未封装通用 `VirtuosoBackend` 实现或环境。架构方向仍为 Graph Transformer + goal-conditioned SAC。

# M3 后端适配 — 2026-09-19

- 用户确认先核对与 bridge 的职责边界，再授权继续实现。采用组合式薄适配器，复用上游客户端、导出、Spectre runner 和 PSF reader；不修改上游安装、不启动新 daemon。
- 首版仅支持当前 GPDK045 OTA、固定 TT/27°C DC/AC 和 M1/M2 匹配宽度，避免把 PDK 回调流程宣称为通用 setter。其余参数与连接对照保存的真实参考验证。
- 连接要求显式环境、创建记录、初始参考状态；Linux 文件锁和进程内独占锁约束项目 worker。回写前记录检查点，回写后对照 CDF 和导出网表；上下文退出恢复尺寸。恢复失败明确保留 recovery_required，不吞掉错误。
- `SimulationRequest.parameters` 用于核对不可变导出的执行参数，不透传为上游 runner 的 params。每个导出和仿真 job 均有独立 UUID、摘要、原始输出及结构化结果。
- 实际执行 4 → 4.4 → 4 µm 三次真实仿真；增宽引起派生几何和响应变化，恢复后的执行网表与原基线 SHA-256 相同，指标一致。完整证据及运行约束见 [后端验收](opamp-backend.md)。
- 离线故障注入和已有测试合计 103 项通过，零失败、零跳过。尚未实现 reset/step、奖励、随机搜索或训练；这些是下一步。

# M3 环境与非学习闭环 — 2026-09-19

- 用户继续授权下一步，并在真实验收前保存、关闭了冲突的 OTA ADE Assembler 窗口。复用原有专用电路、bridge 和单 worker 锁；不改变训练架构或开放额外器件。
- `ActionMapper` 按图中的独立 mutable 组接收绝对 normalized proposal，支持 linear/log 和既有合法网格投影。真实 profile 将动作收窄为 M1/M2 共享宽度 3.6–4.4 µm，其它两组固定。未来 critic 使用 normalized proposal；日志同时保存合法化结果和实际读回参数。
- 首次随机候选 4.106791753 µm 被实际 CDF 取整为 4.105 µm，严格检查触发回滚；上下文退出恢复 4 µm。保留失败证据，并增加 5 nm 软件动作网格及 off-grid 参数拒绝。这是当前 profile 的经实测兼容网格，不宣称已推导所有器件的最小制造网格。后续连续 SAC 属于连续代理加确定性投影。
- `SpecificationEvaluator` 是纯函数；成功要求所有 active required 规格有效、单位正确且满足各自约束。奖励是各项归一化 violation 截断至 1 后的负加权平均，范围 [-1, 0]，不加成功奖励。验收目标围绕已知基线设置，仅检查闭环行为，不构成优化 benchmark 或产品性能指标。
- 环境使用普通 Python reset/step 接口，无 Gymnasium 依赖。剩余步数进入 observation，预算作为有限时域任务的一部分；耗尽时 terminated，不 bootstrap。基础设施和测量失败返回 reward=None、truncated、replay_eligible=False；只有后端明确归因且确实评估的电路失败返回 -1。异常记录后抛出，禁止继续 step。
- 不使用仿真缓存或自动重试。重复执行参数仍消耗预算和真实调用，记录 duplicate_of。每次更新后的图来自实际导出结构并验证摘要、拓扑、动作契约和执行参数，不只修改旧图中的 w。日志保存 reset/step、规格、图、proposal、实际值、指标/mask、状态、计时和 RNG/候选计划。
- 完整复验 8 次真实仿真通过；包含失败首轮的 3 次，本轮共 11 次 Spectre。CDF 诊断另外只回写/读回，无仿真；所有尝试均恢复。最终 156 项离线测试通过、零 skip。完整结果、成本和恢复证据见 [环境报告](opamp-environment.md)。

# M3 及之前：工况接口修订 — 2026-09-19

- 用户要求当前只改 M3 及之前，不推进 M4 或后续。增加 PVT/Monte Carlo 基础类型、网表/request/result/图/日志中的一致工况、MC 批次接口与明确不支持行为。没有模型、训练或后验证调度。
- 用户撤回原 1.8 V 示例。只读核对已安装 GPDK045 v6.0 后，按当前 1 V 基线配置 TT/27/1.0、SS/125/0.9、FF/−40/1.1、FS/27/1.0、SF/27/1.0，温度单位 °C、电压 V。0.9 V 是工程 −10% 筛选点，并非 PDK 最低电压；来源、文件摘要及边界见 [接口说明](pvt-mc-interfaces.md)。
- `CircuitSizingEnv` 强制 nominal-only，奖励及动作维度不变。新日志为 v2，工况不匹配的 artifact/result 不会成为 nominal transition；PVT/MC 验证不能混入 replay。
- top 3 选择和固定 corner 汇总仅实现为纯函数。按实际尺寸去重，任一失败 corner 都排除通过资格；完整结果才计算 pass rate 与 nominal_reward − λ × failed_corners。基础设施故障保留 unknown，不冒充设计失败或通过。
- PVT 的供电变化仅写入 job 副本，实际图特征同步；原导出与摘要仍保留，理想偏置保持绝对电压。MC 样本数、seed、variation、section、sample identity 和调用预算保留接口，尚不执行。
- 项目 analog-optimizer skill 同步当前范围和以后按算力预算扩展 PVT/MC training 的参考。此次没有新增真实 Spectre 调用或原理图回写；198 项离线测试通过，零失败、零跳过。

# M4 Graph Transformer 与 SAC — 2026-09-19

- 用户明确要求“m4 继续下一步”，覆盖此前暂停在 M3 的阶段限制；本次进入模型、SAC 和少量真实 nominal 采样。架构仍为 Graph Transformer + goal-conditioned SAC，保持原有参数授权与工况限制。
- 采用 `local_port_attention`：PyG `TransformerConv` 的多头邻域注意力，端口角色/方向和 ordinal 编码进入 key/value；每层含 residual、LayerNorm 和 feed-forward。不是全局 Graphormer/DEGT 复现。宽度/层数是可配置工程选择，尚无性能优劣结论。
- 使用 packed device/net 图和参数组表，避免节点/动作 padding 进入 attention、pooling 或 entropy。actor 通过同一共享 head 输出每个 mutable 参数组的分布；固定组没有随机动作。critic 将组动作注入绑定器件后做端口 attention，保留组级动作 readout；actor/Q1/Q2 及 target 权重独立。
- 状态包含当前尺寸、缺失/有效/可调 mask、规格身份/单位/方向/目标/scale/weight、当前测量与有效性、剩余步数及 nominal 温度/电压。采用固定物理 reference + signed-log1p，无统计量拟合或 test 数据输入。规格 registry 和原有 FeatureSchema 随 checkpoint 保存；未知语义显式拒绝。
- SAC 采用双 target Q、重参数化 tanh actor、稳定 Jacobian 修正、自动温度和 Polyak 更新；每图目标熵为负的有效组数。Q 在训练 replay 与 policy loss 中都接收 normalized proposal；环境继续使用 M3 的确定性合法化。网格/整数仍是连续代理加投影。
- `Transition.from_step` 核验环境候选日志及 executed sizing。replay 拒绝非 nominal、混合 real/synthetic、工况/目标/图契约变更、无效测量或基础设施故障。有限步数耗尽不 bootstrap；明确归因的电路失败可保留终止惩罚。每新增一个有效 transition 最多做一次更新，reset 不入 replay。
- checkpoint 保存所有网络/优化器/温度、固定 normalizer/schema、配置/实验与 PDK 映射来源、代码摘要/库版本、CPU/Python/NumPy RNG、replay 内容与采样 RNG、计数和 collector 状态。只恢复可信本地产物，在 episode 边界重新 reset；不接管运行中的 Virtuoso job。schema/action/config/代码/依赖不一致时拒绝无提示加载。
- 完成双拓扑 analytic toy 闭环、混合 batch 更新、NaN padding、重命名/重排等价、动作与端口梯度、target/温度方向、失败排除及精确恢复测试。真实验收新增 5 次 Spectre：baseline + 1 次随机 warmup + 2 次 policy candidate + restored baseline；3 条真实经验、2 次更新，原始 4 µm 已恢复。
- 当前目录依然不是 Git checkout；不创建虚假 commit。详细结果、完整成本与可复现命令见 [M4 验收](m4-graph-sac.md)。本次没有 PVT/MC 调度、surrogate、多 worker 或迁移效果结论。新增模型/训练入口可以独立停用，M1–M3 接口保持兼容。

# M5 首轮：固定划分、规格迁移与合成拓扑验收 — 2026-09-19

- 用户明确要求“m5继续”，授权进入 M5；此前 skill 中停留在 M3 的上下文快照不再限制当前阶段。维持 Graph Transformer + goal-conditioned SAC、nominal-only 和单 worker。
- 现有真实 profile 仍只支持五管 OTA 的一个匹配宽度组，不扩大原理图参数权限。本轮真实部分是同拓扑新规格；拓扑迁移先以同类运放合成图 2→3 维动作进行流程验收。新增第二级与电流源使图确实不相同，不使用重命名电路冒充新拓扑。
- 新协议在执行前冻结图、目标、划分、方法、seed、预算和文件/代码摘要。使用 NetworkX exact isomorphism 检查带 terminal 节点的 incidence graph，保留并联端口连接、忽略名字和尺寸；NetworkX 明确列入 graph extra。
- 六方法固定为 GT scratch/frozen/adapt、random、coordinate pattern search、port-GNN adapt。主方案不变，GNN 仅作非 attention 对照；同宽度/深度但参数量不同，报告参数数量。不引入 surrogate 或其它优化器主方案。
- validation 只作 GT 冻结诊断，不做超参数或 checkpoint 选择。预训练仅用 train；每个测试任务复制预训练网络/温度，但创建独立优化器与 replay；测试数据不回流源模型。固定物理参考归一化不拟合测试数据。
- 固定同一在线调用预算，baseline/reset 也计数，成功后继续到预算终点。初始基线可成为第一个达标设计。失败、重复、恢复验证、预训练和诊断成本全部保留；不自动重试。未达标保持右删失；中断保留已完成失败 run，另列尚未执行任务。
- 真实目标是根据既有 M2–M4 基线设计、M5 前冻结的 pilot，不称完全独立的性能 benchmark；3 个种子用于流程验收，不据此宣称迁移优势。小预算为 97 次真实调用（预训练 18、诊断 6、测试 72、恢复验证 1）。
- 完整 246 项离线测试通过；冻结 synthetic 实验完成 534 次解析评价；真实试验完成 97 次 Spectre，M1/M2 恢复 4 µm，原网表摘要及全部基线指标一致。39 个 checkpoint 的数据分区及权重隔离后审计通过。GT 微调 1/3、随机 2/3、坐标搜索 3/3 达标；这是极小预算 pilot，不构成算法优劣结论。结果与验收文件见 [M5 记录](m5-transfer.md)。所有新增功能可通过不运行 M5 入口停用；M1–M4 默认 attention 模式和后端契约保持兼容。

# M6 前：编码器可替换接口 — 2026-09-19

- 用户要求预留 Graph Transformer、MLP、RGCN、GAT 的切换接口，以比较最终知识迁移效果。本轮将四种方案全部接到可运行的共同接口，保留 port-GNN 和 GT 默认值，不启动 M6 或新增真实 Spectre 采样。
- `ModelConfig.encoder_type` 选择编码器；`CircuitEncoder/build_encoder` 共用输入、动作绑定与组 readout，仅替换节点处理块。MLP 使用逐节点共享网络和组聚合，不读取电路连接；RGCN 使用 terminal role × direction 关系；GAT 使用带端口特征的加性邻域注意力。模型定义、ordinal 差异及实现来源见 [编码器说明](encoder-ablation.md)。
- 迁移 runner 显式选择编码器后，给每种架构完整 scratch/frozen/adapt 对照以及冻结 validation 诊断；训练数据分区、微调隔离和预算审计保持一致。共同宽度/深度并不等于参数量相同，实际参数数及预训练成本分别记录。
- 默认 M5 六方法及旧 attention_mode 构造入口保留。checkpoint 保存编码器类型，拒绝跨架构加载/转移；仍严格校验代码摘要，因此不自动迁移改码前的 checkpoint。
- 完整离线回归 296 项通过，零失败、零跳过。四架构 synthetic smoke 完成 116 次解析评价，覆盖同拓扑规格及新拓扑 2→3 维动作，所有环境恢复；无真实迁移效果结论。源码、离线测试和验收产物见 [编码器说明](encoder-ablation.md)。停用方式为不传新 `--encoders` 参数；旧实验产物保留。
- 用户随后要求同步文档与 skill：项目级 `analog-optimizer` 主文件、决策/学习/实验/阶段/PVT 参考及契约示例已同步，修正“当前止于 M3”的过期限制。此同步只更新说明与示例，不启动 M6、训练或真实仿真。

# M1 图提取与通用神经网络输入复核 — 2026-09-19

- 用户要求检查 M1 图信息是否支持 GCN/GAT 等网络，并修正不合适的输入形状。原 CircuitGraph 信息完整、现有 RGCN/GAT 可经 SAC 适配使用；缺口为原始 HeteroData 的 device/net 数值列语义不同、缺少统一 edge_attr，以及直接同构 batch 的组索引偏移。保留已验证 parser 和 to_pyg，新增 `graph/neural.py` 同构视图。
- `circuit-neural-v1` 默认节点 `[N,49]`、边特征 `[E,15]`，显式保存 node_type、relation ID、ordinal、单位边权重、组绑定与 metadata。特征列按 schema 固定，节点数/边数/组数可变；batch 校验 schema/方向/跨图边/绑定，并支持带布尔 mask 的 dense 节点输入。
- SAC 的端口边打包与 M1 导出共用实现；保留其已验证的 device/net 投影与组动作语义。新增普通 `gcn` 作为只使用连接的对照，明确区别于使用关系类型的 `rgcn`；六种编码器都可走相同迁移入口，GT 默认不变。
- 完整回归 319 项通过，零失败、零跳过；直接算子测试包含三类 synthetic 电路、两级运放与现有真实导出快照。六编码器迁移 smoke 完成 168 次 synthetic 评价，所有环境恢复，新增真实仿真 0。详细字段、调用和证据见 [M1 输入说明](m1-neural-inputs.md)。

# 图输入缓存优化 — 2026-09-19

- 用户要求优化每次训练中的重复图张量转换。实现 learner 内两层有界 LRU：默认 64 个静态拓扑模板、2048 条完整观测原始输入，六种编码器共用；按需准备，replay 深拷贝按完整内容命中。
- 尺寸/测量/目标/mask/预算/工况/来源/schema 变化不会读到旧观测输入；索引顺序/端口/绑定变化不会读到旧静态模板。每次仍组 batch、调整索引并用当前权重重新前向/反向；不缓存 embedding，也不省略真实后端回读与网表核验。
- 输入缓存不进入 checkpoint，冷启动保持精确恢复；两项容量均设为 0 可关闭，GCNConv 仍 cached=False。恢复接口允许重设缓存容量，源码/schema 的严格加载边界保持不变。
- 完整 354 项离线测试通过，零失败、零跳过。六编码器缓存开/关的损失与参数完全一致；本机 CPU 合成 batch=32 输入阶段 35.66→10.86 ms，GT 完整更新 112.22→62.31 ms。计时未包含 replay 深拷贝或后端，不能称为 Spectre/端到端提速。
- 计时产生 18 次 synthetic 解析评价、真实调用 0；未启动 M6。复现、限制与产物见 [输入缓存说明](input-tensor-cache.md)。项目 analog-optimizer skill 同步静态/动态缓存和禁止缓存 learned representation 的约定。

# 有限 CDF 表与并行 Spectre SAC — 2026-09-19

- 用户明确授权预先建立有限参数表，使用 CDF 读回与 Python 模板，并加入用户指定最大 worker 数的并行 Spectre 训练。本授权更新此前单 worker 采样的范围；共享原理图仍独占串行修改，训练阶段使用独立不可变网表，无多 worker 原理图写入。
- 现有 GPDK045 OTA 的输入对宽度 3.6–4.4 µm、5 nm 网格共 161 个值全部采集。每行读取完整 CDF 派生参数，并与原生 Virtuoso 网表逐参数/逐连接对照后发布；其他尺寸/finger/multiplicity/偏置固定。恢复初始原理图及验证 PDK 文件摘要后才写出有效表；未从这些值推断整个 PDK 的 min/max/step。
- 训练入口 `examples/train_opamp_sac_parallel.py --max-workers N` 使用最多 N 个独立 worker 进程，每个进程一个顺序环境和最多一个 Spectre 作业。主进程统一生成动作、按稳定 worker 顺序收集本轮结果，独占 replay 与 SAC 更新；nominal、reward、proposal critic、有限时域终止及失败排除语义保持不变。第一版使用同步轮次，不宣称异步流水线。
- 表与 profile/schema/model/PDK 摘要绑定，训练 worker 启动时校验；Python 模板更新全部允许变化的网表参数，随后仍执行完整参数和图核验。复用的是 CDF 参数与网表，不复用仿真结果，不引入 surrogate。
- 真实表预计算 204.58 s、162 次原生导出、0 次 Spectre，全部 161 行通过且恢复。首次训练 8 次 Spectre、6 条经验、5 次更新；真实续训新增 8 次 Spectre，累计 12 条经验与 11 次更新。主机采样确认 2 个 Spectre PID 同时运行，观测峰值没有超过 2；最终只读检查确认原理图仍为初始尺寸。
- checkpoint 仅在完整运行结束后保存，恢复网络/优化器/replay/RNG，并在新的独立环境真实 reset 后继续。失败运行不接管半完成作业，无自动重试。旧 M4/M5 checkpoint 仍受源码摘要约束，不自动迁移。
- 本轮仅扩展采样执行路径，未启动 M6、PVT/MC 训练或真实新拓扑迁移。原串行入口保持兼容。完整使用方法、证据和性能计时边界见 [并行训练说明](parallel-spectre-sac.md)。
- 最终完整离线回归 373 项通过、零失败、零跳过。真实成本合计 16 次 Spectre；离线进程测试明确使用 synthetic 环境，不计作真实电路证据。

# 轻量实验记录与恢复 — 2026-09-19

- 用户要求独立于 replay 保存所有昂贵仿真尝试，并实现存储、清理、测试。复用当前 Virtuoso Bridge 和已有 SAC/collector，不改变优化算法，不新增 surrogate、PVT/MC 调度或真实仿真。本次实际真实调用为 0。
- 新增 opt-in `recording/`：SQLite 唯一核心源，单 writer 队列与进程间本地 IPC；静态资产内容哈希，动态状态精确 patch，evaluation/transition 原子提交，参数和测量无损保存。开启后不生成逐候选 JSON 或在 checkpoint 中重复保存 replay 样本。
- 本机 SQLite 3.37.2 使用 DELETE journal + synchronous=EXTRA；WAL 仅在已修复 WAL-reset 的版本分支与已知本地文件系统启用。不在 WSL `/mnt/d` 的 9p 或网络共享上写数据库。
- feasible 独立判定全部 required spec；默认保留首个 feasible，支持显式物理指标 min/max；infeasible 比较未截断加权违反量。不将 reward 最大解释为达标或全局最优。无法确认启动的仿真另列不确定计数。
- 默认 500 env steps checkpoint、两份完整文件和一个 final policy；replay 用数据库成员 ID/槽顺序/cursor/RNG 恢复。保留现有源码/schema/依赖的严格校验；精确恢复覆盖 learner/replay，外部 collector 仍从新 episode reset，不能接管半完成模拟器。
- 默认附件 256 MiB/run、项目 20 GiB、每文件系统空闲 5 GiB，并保留临时、journal、checkpoint 替换空间。只清理有归属标记、已结束、结果已获持久化确认的项目工作目录。VMware 端通过已有 Bridge transport 接专属 scratch 检查与清理；本次只做 helper 离线验证，不声称真实远端清理已验收。严格临时容量限制需要文件系统配额。
- 使用方法与波形缺失后的可恢复边界见 [实验记录说明](experiment-recording.md)，最终测试与 6000 次 MockBackend 体积见 [记录验收](recording-verification.md)。关闭方式为不传 `--recording-root`；历史产物不迁移、不删除。

# 实验记录重复 I/O 优化 — 2026-09-19

- 用户明确记录主要服务运行管理与手动查阅，授权减少重复 I/O、改善摘要和测量开销。权重保存/加载继续独立；不修改 SAC、动作、reward 或仿真流程，不调用真实 Spectre。
- replay 入池由完整数据库重建改为核对同事务保存的完整字段指纹；恢复仍完整校验，历史行没有指纹时保留原回读兼容。缓存已持久化静态资产 ID 和不可变图定义，避免重复 next_state 处理、已存在内容的重复压缩/写入，以及清理/导出中的冗余回读。环境诊断中的重复字段按明确 result/request/condition 引用保存。
- 请求/工作目录同一事务登记，结果独立提交后再合并本地保留/清理元数据事务。普通无附件评价主要写事务由 6 个变为 4 个；未降低 SQLite durability。清理仍要求已确认结果、目录归属和进程退出；删除后元数据失败可以显式重试补齐。
- checkpoint 数据库登记复用实际写入文件的恢复位置。内置并行 factory 在环境构造时接入 recorder，避免每 worker 先落一份旧 JSON 配置；外部 factory 的可选 `create_recorded` hook 保留向后兼容。
- 新增只读 `summary` 文本及 `summary --json` / `RunReader.overview()`，新 run 的分组统计不扫描历史。未结束登记不代表 worker 存活；存储统计只覆盖本地记录根目录。
- 完整离线回归 **411 passed，0 failed，0 skipped**。600 次评价×3 种路径×3 次重复的配对计时核对全部评价轨迹及网络参数一致；入池约 7.56→3.24 ms，但相比原有 JSON 路径 SQLite 在快速 mock 上仍增加约 25.67 ms/评价，文件系统耗时有波动。不能将此表述为所有训练中零开销或真实 Spectre 提速。证据见 [重复 I/O 审查](recording-io-audit.md)、[开销对照](recording-overhead.md)。
- 回退方式：不传 `--recording-root` 仍走原 JSON 路径；旧数据库无须迁移。源码摘要校验仍严格，改码前 checkpoint 不自动迁移。

# 实验记录真实闭环验收 — 2026-09-19

- 用户授权执行单 worker、2-worker 和 checkpoint 续跑的小规模真实验收。复用已有 OTA、有限 CDF 表和 nominal specs；合计新增 16 次 Spectre、12 条 transition、10 次实际训练更新，无自动重试或原理图回写。
- 发现虚拟机只有 Python 2.7.5，原记录 helper 写死 python3。第一次尝试在派发前失败，真实调用为 0。修复 helper 的解释器选择及标准库兼容性，保留归属、路径、容量、存活进程和提交确认门槛；不因操作失败而换解释器重试，不安装新解释器。
- 数据库放在持久 WSL ext4 `/home/fyworkstation/gator-records/recording-real-20260919/`。本轮仅将 checkpoint 间隔设为 2 步以验证轮换，默认 500 步不变。三个成功 run 各保留 2 full checkpoint + 1 final policy；六份真实 AC/DC 波形附件与数据库指标/网表摘要一致。
- 逐条参数/网表/reward/transition、Parquet 数值及 checkpoint 重载后的下一次采样、loss、网络和 optimizer 状态全部核对通过。共清理 17 个本地与 16 个远端 owned workspace，包含确认未启动仿真的首次失败空目录，失败历史仍保留。SQLite 完整性正常、pending=0、无不确定调用。
- 600 次虚拟机进程采样中 22 次确认两个 Spectre 同时运行，观测峰值为 2；前后 Virtuoso 完整 CDF 快照相同，输入对仍为 4 µm。完整离线回归 413 passed，零失败、零跳过。证据和复现见 [真实记录验收](recording-real-verification.md)。
- 验收覆盖现有单参数 nominal 任务的工程闭环；不推导训练收敛、迁移优势或加速比，不扩展动作域/PVT/MC/M6。恢复仍从新 episode 开始；真实磁盘耗尽和大波形超预算没有刻意触发，严格临时容量上限仍需文件系统配额。

# 中文摘要随记录保存 — 2026-09-19

- 用户要求中文 summary 也保存到 ext4。当前真实续跑 run 的摘要已补存到记录根目录的 `summaries/0aeec628645143d686a93137beb2c404.txt`，原工作区摘要保留。
- 新增 `examples/save_recording_summary.py`，复用只读 `RunReader.overview()` 和现有中文排版，UTF-8 临时文件 fsync 后原子发布，每个 run 单独命名。两个 recorded 训练入口和 6000 次记录验收入口在结束登记、关闭 writer 后自动导出，并记录 `summary_path`；衍生文本失败显式报告，不掩盖训练异常。文本不自动刷新，已有 run 可单独补导出。
- 修改只在 examples 和说明文档中，未改变训练核心、数据库 schema 或源码摘要，已验证的真实 checkpoint 保持兼容。双拓扑 synthetic CLI smoke 完成 6 次 toy evaluation、4 条经验、3 次训练更新，恢复和自动摘要导出通过；新增真实 Spectre 调用为 0。

# 运行恢复、worker 限时与迁移入口整合 — 2026-09-19

- 用户明确要求修复周期备份与 CLI 不兼容、初始化/报告异常清理、worker 无期限等待、迁移入口未接入有限表与记录，以及长运行报告内存增长。沿用现有 nominal、SAC、动作/奖励、分区和调用预算规则，不扩展真实参数权限或启动 M6。
- 并行完整轮次与完整运行 checkpoint 使用统一累计计数；恢复从新 episode reset 开始，保留 checkpoint 位置的 learner/replay/RNG。synthetic 周期备份补齐累计字段。失败更新的轮次不发布新备份；未接管在途仿真。
- 公共运行资源管理覆盖服务启动后的初始化、训练和结束处理，各项清理独立尝试，保留原始错误。环境恢复记录写入失败也继续尝试 backend 恢复/关闭。
- 以拥有明确进程句柄的 spawned worker 替换无期限 executor 等待；操作、关闭、terminate/kill 分阶段限时。只停止本次本地 worker，远端未知状态保留且无自动重试。训练仍按稳定 lane 顺序入池，保留正常 peer 的已完成样本。
- 迁移入口增加有限表、SQLite 和独立 seed 并行；真实并行必须选择不可变网表。协议与总预算在启动前冻结，各 seed 和各测试任务保持独立 learner/replay。阶段 run 关联控制 run 的来源配置，测试 replay 仅持有本任务成员 ID。
- SQLite 模式只在内存保留近期报告条目，累计统计与完整数据库评价保留。未开启记录的 JSON 行为兼容；不宣称对所有 backend 缓存设置了进程级内存硬上限。
- 本轮采用离线故障注入与 CLI 测试，真实 Spectre 调用为 0。源码已变化，旧 checkpoint 的严格代码摘要限制仍有效，不自动迁移。参数、成本计数边界、复现与验收见 [运行可靠性说明](runtime-reliability.md)。
- 完整回归 **430 passed，0 failed，0 skipped**（175.26 秒），含新增 17 项恢复、清理、限时退出和迁移入口验收；记录见 `artifacts/local/runtime-reliability-tests.xml`。

# 撤销 CDF 预计算表，接入逐候选原生准备 — 2026-09-19

- 用户明确撤回穷举 CDF 表方案，要求完整候选逐次经过 PDK 参数处理、读回和原生导出，并把最大 Spectre 并发设为 4。此前有限表章节仅代表历史决定和历史验收。
- 删除建表入口与查表/模板后端；训练与 benchmark 均改为一个专用 Virtuoso 准备进程，串行执行完整候选事务，再把独立且核验过的网表交给各环境 Spectre 进程。A 仿真期间可准备 B，不预枚举、不缓存。
- 保留现有 GPDK045 的初始化、回调顺序、结束处理及 M1/M2 匹配宽度授权；不将其推广到其他 PDK，不扩大 L/fingers 等动作域。使用已有 receipt 核验的项目测试电路及会话锁，最后由准备进程恢复原理图。
- 默认和硬上限均为 4；可选 1–4。候选/环境身份、原始 proposal、实际 CDF 参数、派生量及网表摘要保留；同步轮次稳定入池、中央 SAC、记录与故障恢复规则继续有效。旧表方案 checkpoint 因实验和源码签名变化不自动迁移。
- 实现及验收见 [逐候选 CDF 与并行 Spectre](parallel-spectre-sac.md)。
- 完整离线回归 **426 passed、0 failed、0 skipped**（177.21 秒），新增测试包含 JSON/SQLite 四 worker 准备流水线。bridge 0.8.0 已安装，但既有隧道未运行；本轮真实调用为 0，新版真实闭环未验收。

# 逐候选 CDF 与并行 Spectre 真实验收 — 2026-09-19

- 用户恢复 bridge 连接后明确要求真实验收。使用已有专用 OTA、M1/M2 匹配宽度组及 nominal 条件，完成单 worker、默认四 worker、checkpoint 续跑三个阶段：合计 **24 次 Spectre、18 条新 transition、16 次实际 SAC 更新**，失败、重试、不确定调用和缓存命中均为 0。
- 24 个实际候选均经真实 CDF 回写、读回与原生导出。逐条参数、派生 geometry、图状态、网表摘要、reward 和环境轨迹核对通过；三个阶段后完整原理图快照相同，输入对恢复 4 µm。PDK 模型文件摘要未变。
- 四 worker 阶段进程采样覆盖 16 个 Spectre PID，45 条记录看到两个 Spectre 同时运行；实测峰值 **2**，未超过硬上限 4。本轮不证明四路满载或加速比，不扩展参数域、PVT/MC、真实新拓扑或 M6。
- 三个最终 checkpoint 精确恢复下一次 replay 采样、loss、网络和 optimizer 状态；审计只在内存执行额外更新，不追加仿真。每 run 保留 2 full checkpoint、1 final policy 及 initial/best 原生网表与 AC/DC 附件。24 个本地和 24 个远端 owned workspace 已清理，数据库完整且 pending=0。
- 持久记录位于 WSL ext4 `native-cdf-real-31afdfba86bb`，详见 [真实验收记录](native-cdf-real-verification.md)。本轮未修改生产源码；此前完整离线回归 426 项通过，真实验收脚本及只读审计作为本机产物保存。


## M5 真实同类新拓扑补验（2026-09-19）

- 用户要求“做 M5 剩下没做的”，本轮补齐独立真实两级 OTA 基线、可恢复后端及固定预算拓扑迁移对照，未启动 M6。新增专用 `ota7_m5_v2` / `tb_ota7_m5_ac_v2`，原五管电路权限不变。
- 七管 Miller OTA 使用输入匹配宽度与输出级 4:1 比例宽度两个动作组，均经 CDF 回写、读回、派生 geometry、原生导出和恢复验证。首次 16 µm 单指配置被 CDF 限为 10 µm，校验拒绝并记录 0 次 Spectre 的创建失败；成功版本 M6/M7=8/2 µm。
- 新拓扑在源训练中完全留出，但先做了基线/参数域验收再确定规格，属于前瞻冻结的 nominal 验收，不是盲测。源 train/validation/test 规格维持首轮定义；每个 test task 独立微调，冻结模型不更新，validation 不选超参数。
- 3 seeds × 6 methods：每架构/seed 16 步源预训练；每测试 run 12 步，reset 单独计入预算。新增 7 次电路验收 + 576 次实验评价 + 2 次最终复验 = **585 次真实 Spectre**，全部测量有效、无失败/重试/缓存。共 288 次实际 SAC 更新。
- 新拓扑达标率：GT scratch/frozen 0/3，GT adapt 1/3，random 1/3，pattern search 3/3，port-GNN adapt 2/3；没有 GT 迁移优势证据。GT 与 GNN 分别有 105,476 / 92,804 个 actor+Q1+Q2 参数，未声称等参数比较。
- 离线 **440 passed，0 failed，0 skipped**；24 个 checkpoint 核对来源、隔离、冻结权重和下一次更新的精确恢复。两个电路最终 CDF 全快照、基线网表与指标均恢复，PDK 入口/MOS 摘要保持一致。证据、成本、复现命令见 [M5 真实拓扑验收](m5-real-topology.md)；机器可读汇总位于 `artifacts/local/m5-topology-acceptance-summary.json`。

## M6 started: cross-category offline protocol (2026-09-19)

- The user authorized M6 and subsequently requested English communication. This supersedes earlier status snapshots saying M6 has not started. M5 was committed separately as `a7fed13` before these M6 changes.
- The first increment targets category holdout and shared source learning using the existing synthetic fixtures. `TransferTask` now separates circuit class from topology family and supports test-only `category` transfer. Train/validation class overlap, relabeled topology/family leakage and missing class declarations are rejected. M5 within-family rules remain intact.
- Each leave-one-class-out fold pretrains on the other two classes with one learner/replay per encoder and seed. All six encoders get scratch/frozen/adapt plus random and coordinate-search controls. Target adaptation, source training and folds remain isolated; source episodes run sequentially with their order frozen in the protocol.
- The ring-like fixture now has three width actions with PMOS/NMOS ratio constraints. Three explicitly named toy metrics exercise distinct identities, masks and min/max/range goals. A separate fixed M6 specification registry is passed through benchmark/checkpoint construction; the M5 default registry is unchanged. These objectives do not measure electrical performance.
- The whole suite is frozen and budgeted before evaluation, including source/validation/test/reset costs. The audit recomputes executed toy objectives/rewards, checks task membership and copied/frozen weights, and probes exact next-update recovery from every checkpoint without new backend calls.
- No real circuit permissions, PVT/MC execution, surrogate, global attention or new parallel sampling path are added. Real LDO/VCO baseline qualification is the next M6 step. Run commands, acceptance evidence and limitations are in [M6 cross-category work](m6-cross-category.md). The synthetic suite is a first milestone increment, not completion of M6 or evidence of transfer superiority.
- Acceptance: **454 tests passed, zero failures/skips**. The three-fold, three-seed suite completed **1,656 synthetic evaluations and 702 SAC updates**, with **0 real calls**. All 396 environments restored; the independent audit verified all evaluations and exact next-update recovery for **162 checkpoints**. Evidence is linked from the M6 document and `artifacts/local/m6-acceptance-summary.json`.

## M6 second increment: real LDO qualification (2026-09-19)

- The user's request to work on the next step advances M6 to a dedicated real LDO baseline. Added `ldo_m6_v1` / `tb_ldo_m6_v1`, a six-MOS PMOS-pass regulator with ideal reference/bias, a fixed divider, 10 nF output capacitor and a 10→20 µA held load step. Existing OTA cells remain unchanged. Creation refuses existing targets and preserves ownership/protection evidence.
- Added a separate LDO profile with matched input width 3.6–4.4 µm and pass width 7.2–8.8 µm, both on a 5 nm grid. Every candidate uses native CDF callbacks/readback/export; fixed parameters, connections and geometry are checked. Circuit-specific deck/measurement hooks preserve the existing OTA defaults and session restoration behavior.
- Physical measurements cover output error, supply/quiescent current, endpoint line/load regulation, 1 kHz PSRR and finite-window load-step deviation/ripple. Missing traces and inconsistent stimuli fail explicitly. Nominal qualification is the only supported LDO condition; PVT/MC and learner updates were not run.
- Real cost: **12 Spectre invocations**, comprising one initial measurement failure, one corrected baseline, seven width/repeat/restoration checks and three environment evaluations. The first run used an incorrect current-source trace suffix; installed Spectre help and raw data established `ILOAD:i`, and the failure remains recorded. Eleven evaluations were valid and passed the predeclared engineering criteria; no automatic retry or uncertain call was hidden.
- Baseline output is 0.792484 V for a 0.8 V target, quiescent current 2.941 µA, PSRR 38.827 dB at 1 kHz, and held-step deviation 2.645 mV. Repeated baseline deck hashes and metrics match exactly. Both environment transitions passed the existing replay contract, with no learner updates. These qualification criteria are not frozen transfer-test targets or evidence of optimization advantage.
- Full regression: **472 passed, zero failures/skips**. Saved-artifact auditing verified all 12 executions, original export file hashes, CDF/deck parameters, rewards and restoration, and recomputed all successful metrics directly from PSF. Final read-only checks matched all three core snapshots and the two PDK file hashes from M5. The PDK comparison covers the entry and MOS files only.
- Evidence, commands and limits are in [real LDO qualification](m6-ldo-baseline.md) and `artifacts/local/m6-ldo-acceptance-summary.json`. The testbench does not establish dropout, startup, loop phase margin, general stability or production LDO suitability. Real VCO qualification is next, followed by a separately frozen physical schema and real transfer budget. Historical checkpoints keep their original strict source digest; no automatic migration or existing-artifact deletion occurs. M6 remains in progress.

## M6 third increment: real VCO qualification (2026-09-19)

- The user requested continuation after LDO qualification. Added dedicated `vco_m6_v1` / `tb_vco_m6_v1`: three NMOS-current-limited inverter stages, nine MOS total, fixed 50 fF stage loads and three independently writable limiter widths, 0.9–1.1 µm on a 5 nm grid. Native CDF callbacks, derived geometry, complete exports, fixed connections/parameters and rollback/restoration are verified. Both OTA cores and the LDO remain unchanged.
- Each candidate invokes Spectre once with three independently initialized transients at 0.55/0.65/0.75 V control, TT/27°C/1.0 V supply. Every stage must sustain full-swing cycles with sufficient temporal resolution, stable periods and consistent stage frequencies. Control tuning must be monotonic. Missing or invalid oscillation fails measurement rather than receiving a fabricated frequency.
- Startup uses declared initial conditions. Detection reports completion of eight consistent cycles and does not prove unassisted/noise-driven startup. Power uses time-weighted integration, and period spread is a deterministic periodicity diagnostic, not jitter or phase noise. No PSS/PNoise, PVT/MC, layout, real learner updates or transfer experiment was added.
- Real cost: **13 Spectre invocations / 39 transient analyses**, all valid, with zero simulation failures, automatic retries or uncertain calls. This includes the initial baseline, eight width/repeat/restoration checks, one half-step numerical check and three environment evaluations. Both environment transitions passed the replay contract and the finite-horizon episode terminated correctly; training updates remain zero.
- Baseline frequencies are 80.1496 / 171.1402 / 274.0147 MHz across the three controls; nominal power is 26.5558 µW. Baseline repeats match exactly. Halving maximum timestep from 100 to 50 ps changed frequency by at most 0.000526%, passing the predeclared comparison limits for tuning, power, swing, duty and detection timing.
- Regression acceptance: **495 distinct tests passed, zero skips and no unresolved failures**. The initial sandbox run passed 487 and blocked eight local multiprocessing socket tests; the same eight passed with IPC enabled and no intervening source edits. Both JUnit records remain. Independent saved-waveform audits cover all 13 executions and metrics, and final read-only inspection matches all four core snapshots and the preflight PDK entry/MOS hashes.
- Evidence and commands are in [real VCO qualification](m6-vco-baseline.md) and `artifacts/local/m6-vco-acceptance-summary.json`. M6 real qualification now totals 25 calls including the earlier retained LDO measurement failure. Next is the frozen physical registry/split/budget and real cross-category comparison. Previously observed qualification data must remain disclosed; M6 transfer performance is still unverified, and old checkpoints are not automatically migrated.

## M6 fourth increment: VCO runtime qualification (2026-09-20)

- Following the user's runtime question and request for the next step, separated the VCO numerical policy from its physical design/creation receipt. Qualified fast mode now defaults to 0.6 µs transients, a 0.2–0.6 µs measurement window, moderate accuracy, `reltol=1e-4` and a 50 ps maximum step. Explicit reference mode preserves the original strict deck. OTA/LDO settings, physical circuit and width permissions are unchanged.
- All three control voltages and all stage waveform checks remain. At least eight cycles are required in each half-window, with sustained detection by the new 200 ns measurement start. Numerical settings accompany manifests and measurements; mismatches fail. The independent audit rebuilds the expected deck and supports both old strict and new fast artifacts.
- Settings and metric agreement limits were frozen before the first fast trial. Twelve fast evaluations at eight unique width assignments passed against saved strict results. Maximum frequency difference was 0.0296%, tuning-gain difference 0.0454%, power difference 0.2081% and swing difference 0.1643 mV; no limit was relaxed. Baseline repeats matched exactly.
- Average backend time fell from 59.10 s across 11 historical strict comparison jobs to 6.02 s across 12 fast jobs. A fresh strict baseline reproduced the original deck and metrics exactly; same-session strict/fast times were 56.93/5.84 s, about 9.74× faster. These times include execution/download/measurement but exclude CDF update, export and session setup. Spectre's aggregate footer disagrees with its accumulated elapsed and external timers; all are retained separately, and speedup uses external monotonic timing.
- Cost: **13 new real Spectre calls / 39 transients**, all successful, zero retries/uncertain calls/learner updates. Cumulative M6 real qualification cost is 38 calls. The waveform audit covers all 13 new jobs and two existing legacy jobs without rerunning them. All four core snapshots and the entry/MOS PDK hashes are unchanged.
- Full regression: **501 passed, zero failures/errors/skips**; one upstream TorchScript warning. Details and reproduction are in [VCO runtime qualification](m6-vco-runtime.md) and `artifacts/local/m6-vco-runtime-acceptance-summary.json`. The eight sampled width assignments do not exhaust the grid or establish PVT behavior. Next remains the frozen physical registry/split/budget and real cross-category comparison; M6 transfer performance remains unverified.

## M6 fifth increment: frozen physical pilot (2026-09-20)

- The user requested continuation with the real metric definitions, task split and budget. Added a separate physical manifest and immutable protocol builder, binding the qualified OTA/LDO/VCO to 23 metric slots, fixed units/reference scales, explicit nominal decks and 1/2/3 independently mutable action groups. The synthetic suite and existing M5 default schema remain unchanged.
- Three folds each train and validate on two classes and test the third. All six encoders run scratch/frozen/adapt, with random and coordinate-pattern baselines; seeds 17/29/43, 32 hidden channels, two layers, four heads where applicable, batch size two and eight steps per source/target episode. Validation is a frozen diagnostic with one step. Source replay is shared only within a fold/encoder/seed; adaptation uses copied same-architecture weights/alpha and fresh optimizers/replay.
- Frozen call ceiling: **2,811 real candidate packages** = 972 source + 216 validation + 1,620 target + 3 final baseline resets. Resets, duplicates and failures count; there are no automatic retries, cache hits or parallel native writers. The serial runner preserves partial fold costs on error and compares the full four-core/model snapshots before and after execution. Every ordinary episode restores its own circuit; the three extra resets separately verify baseline metrics/decks.
- OTA targets reuse the observed M5 pilot. LDO goals tighten output error to 7.5/7.4/7.3 mV for train/validation/test; VCO uses 165–170/170–175/175–180 MHz windows with 27/27.5/28 µW power caps and required secondary constraints. These are explicitly selected from prior qualification knowledge. One characterized topology per class and short training episodes make this an engineering pilot, not blind generalization or a convergence claim. The 38 prior M6 qualification calls and earlier M5 evidence remain disclosed; saved transitions/checkpoints and fitted held-out statistics are not imported.
- The saved protocol pins configuration, source/dependency versions, receipts, baseline metrics/decks, numerical policies and inspected model/core evidence. Freeze refuses overwrites; check-plan and execute reject drift before native environment construction. VCO uses the qualified fast policy throughout this pilot. Strict requalification of optimized final designs is a separate future budget.
- **530 regression tests passed**, zero failures/errors/skips, one upstream TorchScript warning. New coverage includes six-encoder physical inputs, inactive metric masks, changed units/policies/tasks/horizons, global-cap rejection, immutable plans, partial-failure accounting and final-baseline costs. Freeze/check-plan pass against the actual saved local qualification artifacts. **Zero new real Spectre calls and zero real learner updates** were made in this increment; live suite execution remains unverified.
- Protocol, commands and limits are documented in [physical M6 pilot](m6-real-protocol.md); machine acceptance is `artifacts/local/m6-real-protocol-acceptance-summary.json`. Next is execution of the frozen pilot followed by saved-result and learner-checkpoint audits. M6 is still in progress.

## M6 sixth increment: physical pilot execution and audit (2026-09-20)

- The frozen physical pilot was executed as authorized, using the saved protocol `993f759f07b5f87b97048973bf526a97633129a8fff547d2067b0041a07f5129` unchanged through the existing bridge connection: three leave-one-class-out folds, six encoders, seeds 17/29/43, with the qualified fast VCO policy. No production code, targets, hyperparameters or budget changed during execution; there was no automatic resume.
- Real cost: exactly **2,811 real Spectre calls** (937 per circuit: 972 source + 216 validation + 1,620 target + 3 final baseline resets) and **1,566 SAC updates** in 14,934.71 s (4 h 8 min 55 s). There were zero simulation failures, automatic retries, cache hits or uncertain invocations. All circuits and models were restored, and the three final baseline evaluations passed. Cumulative M6 physical cost is 2,849 calls including the 38 earlier qualification calls with their one disclosed LDO measurement failure.
- Results: GT adaptation succeeded on 2/3 OTA, 3/3 LDO and 3/3 VCO seeds; GT scratch 2/3 in each class; coordinate pattern search 3/3 in every class without pretraining; all six frozen encoders 0/3 everywhere. Twelve LDO/VCO scratch successes at seed 17 came from the initial random exploration candidate. These results do not establish a GT or transfer advantage: the circuits were already characterized, the budget is short, capacity is not parameter-matched and the Wilson intervals are wide.
- The independent audit passed with **zero new simulator calls**. All 2,811 saved candidate packages were verified against journals, native exports, deck/file hashes and rebuilt graphs; all 2,811 raw metric packages and rewards were recomputed from saved PSF; all **162 checkpoints** reproduced their next sampled update exactly from two independent reloads, with task isolation and unchanged frozen weights confirmed; all 399 environment restorations were verified. The audit took 2,560.88 s and its probes ran only in memory.
- Final regression after the audit: **544 passed, zero failures/errors/skips**, one upstream TorchScript warning. Per-seed tables, timing, physical examples and reproduction commands are in [physical pilot results](m6-real-results.md); machine acceptance is `artifacts/local/m6-real-acceptance-summary.json`.
- Limits: one characterized topology per class, eight-step episodes, nominal-only measurements, assisted-startup fast VCO policy, no PVT/MC, transient-noise or phase-noise analysis, and model hashes covering only the PDK entry/MOS files. Strict-mode requalification of optimized VCO designs and a larger, prospectively defined circuit/budget set remain separate future work. The M6 physical cross-category pilot is complete; PVT scheduling, Monte Carlo and surrogate extensions remain unverified.

## M6 seventh increment: strict VCO requalification protocol (2026-09-20)

- Following the user's request to continue M6, prepared the step named by the pilot results: reference-mode resimulation of the feasible held-out VCO designs that the pilot found with the fast numerical policy. That policy was qualified at eight width assignments, none of them an optimized design, and several claims lie inside the measured fast/strict differences (up to 0.0296% frequency, 0.2081% power): MLP scratch/29 is 0.015% above the 175 MHz floor, GAT scratch/43 0.025%, and MLP/GCN adaptation/17 are 0.194% below the 28 µW cap.
- Added `evaluation/vco_requalification.py` and `examples/requalify_vco_designs.py` with `freeze`/`check`/`execute`/`compare`. The plan is deterministic from saved evidence. It requires the pilot's passed audit and pins the suite/fold/audit hashes, every design's fast record, job, deck hash, physical source-netlist hash and metrics, the saved strict baseline, both numerical policies, the frozen VCO test specifications, agreement limits and source hashes. It refuses overwrites, and every command rebuilds the plan and rejects drift first. OTA/LDO code, pilot artifacts, learners and replay are untouched.
- Offline analysis shows the saved best design is the first feasible candidate in all 36 successful VCO runs, so requalifying it tests that run's success and first-feasible-call claim. Two scopes were frozen before any strict run so the choice cannot follow results: `best`, 26 unique designs behind 36 runs, **28 strict calls** (`cf88a690…5d52`); and `feasible`, all 67 unique feasible candidates carrying 80 candidate claims, **69 strict calls** (`f4ffcb24…9d97`), which alone permits re-scoring runs and first feasible calls under the strict policy. Fast failures are not resimulated in either scope.
- Agreement limits are those frozen before the first fast trial (0.1% frequencies/tuning, 0.5% power, 1 mV swing, 0.001 duty, 2 ns detection) and are not retuned. Declared before execution: exceeding a limit, or an invalid strict simulation of a design, fails the requalification; a lost feasibility verdict is a reported finding. Both strict baselines must reproduce the saved strict baseline metrics and deck hash. Uncertain invocations and non-measurement failures stop the run without retry, and restoration of the VCO plus the three protected cores is always checked. The per-call timeout is 180 s because historical strict jobs used up to 44 s of the 60 s default; it is not part of the deck.
- The execution report keeps the existing VCO qualification layout, so `examples/audit_vco_baseline.py` can rebuild every strict deck and recompute metrics from saved PSF unchanged.
- **574 regression tests passed**, zero failures/errors/skips, one upstream TorchScript warning. Thirty new offline tests cover design collection and claims, tampered or escaping evidence, overwrite and drift rejection, identity of the limits with the fast-policy qualification, call accounting, stop-without-retry, restoration failure and separation of agreement from feasibility. **Zero new real Spectre calls and zero learner updates** in this increment; cumulative M6 physical cost stays 2,849 calls.
- Protocol and commands are in [strict VCO requalification](m6-vco-requalification.md); machine acceptance is `artifacts/local/m6-vco-requalification-protocol-acceptance-summary.json`. The same session also finalized the sixth increment's audit write-up and corrected a stale M6 status line. Next is authorized execution of one frozen scope, then its comparison, waveform audit and final four-core/PDK inspection. M6 remains in progress.

## M6 eighth increment: strict VCO requalification executed (2026-09-20)

- The user authorized the smaller `best` scope (plan `cf88a690…5d52`). Execution spent exactly **28 reference-mode Spectre calls / 84 transients** in 1,711.5 s wall time, 59.4 s backend time per call, with zero failures, retries, uncertain invocations, cache hits or learner updates. The `feasible` plan stays frozen and unexecuted. Cumulative M6 physical cost is 2,877 candidate packages.
- **All 26 designs are strict-valid and strict-feasible, confirming all 36 first-feasible success claims of the pilot's VCO column.** No run is unconfirmed; the pilot's VCO success and first-feasible-call tables are unchanged. Runs were confirmed, not re-scored, and fast failures were not resimulated.
- The fast policy stayed within every limit frozen before its first trial at these optimized designs: nominal frequency 0.0178%, any control-point frequency 0.0345%, tuning gain 0.0519%, tuning fraction 0.0363%, power 0.2545%, swing 0.1589 mV, duty 0.0000956, startup detection 0.00769 ns. Three of these exceed the maxima seen at the eight qualification points; no limit was relaxed. The frequency difference is systematic: fast minus strict is +0.0153% on average and +0.0141% to +0.0178% for every design.
- Some verdicts are narrow and describe this numerical policy, not design margin: MLP scratch/29 is 175.00103 MHz, 1.03 kHz above the floor; GAT scratch/43 is 0.0096% above it; MLP/GCN adaptation/17 are 0.092% below the 180 MHz ceiling and 0.280% below the 28 µW cap. An offline scan of all 460 valid fast-infeasible held-out VCO candidates found none failing only the ceiling within +0.0178% or only the power cap within +0.2545%, so strict simulation is unlikely to convert a fast failure; this was not simulated.
- Both strict baselines were identical, matched the saved strict baseline and deck hash, and the VCO plus three protected cores were restored. The offline comparison revalidated the frozen plan and physical netlist identity; the independent waveform audit rebuilt all 28 decks and recomputed all 28 metric packages from PSF; the read-only final inspection matched all four cores and the PDK entry/MOS hashes to the pilot's after-snapshot. Results are in [strict VCO requalification](m6-vco-requalification.md); machine acceptance is `artifacts/local/m6-vco-requalification-acceptance-summary.json`.
- Lesson recorded: the requalification module was first placed under `src/analog_optimizer/`, which changed `source_digest()` from the pilot's `02127bc3…` to `2b21a512…` and made the pilot checkpoints and frozen plan non-revalidatable in the working tree. The frozen requalification plan pinned that file by path and hash, so it was left untouched until execute, compare, audit and inspection were complete, then relocated (next entry). Post-hoc tooling belongs in `examples/` or a separate package.

## M6 ninth increment: requalification tooling moved out of the package (2026-09-20)

- After execute, compare, waveform audit and final inspection had completed against the pinned sources, `vco_requalification.py` was moved from `src/analog_optimizer/evaluation/` to `examples/`. Content changes are limited to two package-relative imports, its entry in the pinned source list and a docstring note. `src/analog_optimizer/` is byte-identical to commit `6e0b7f7` again.
- Verified in the working tree: `source_digest()` equals the pilot's `02127bc3…ea101`, and `validate_frozen_plan` accepts the pilot's saved protocol `993f759f…`, so the 162 pilot checkpoints match the code contract again. Any checkpoint written between about 15:50 and 16:50 on 2026-09-20 pinned the transient digest `2b21a512…` and will not load; none belongs to a recorded experiment.
- `plan-best.json` (executed) and the original `plan-feasible.json` pin the pre-move sources and are rejected by `check`/`compare` now, by design; their evidence was verified before the move. The unexecuted larger scope was re-frozen as `plan-feasible-r2.json` (`d0335829…bfe0`), identical to the original except `source_hashes` and digest. This re-freeze happened after the `best` results were known and is disclosed; its content had been fixed beforehand.
- Rule going forward: post-hoc tooling (audits, comparisons, requalification, exporters, the workbench) stays outside `src/analog_optimizer/`. Changing that package is a deliberate decision that creates a new digest and must be recorded here. The parallel workbench implementation follows the same rule in `src/gator_workbench/`.

## M6 closed at pilot scale (2026-09-20)

- The user decided to close M6 at pilot scale and move on. "Complete at pilot scale" means the cross-category pipeline was built, exercised end to end on real circuits, independently audited and reported with its limits. It does **not** mean the research question, whether cross-category pretraining or a graph transformer helps, has been answered.
- Delivered across nine increments: an offline category-holdout protocol with leakage checks (1,656 synthetic evaluations, 702 updates); dedicated real LDO and VCO circuits with native CDF control, physical measurements, failure classification and restoration; a qualified, roughly ten times faster VCO numerical policy; a frozen 23-metric physical protocol with a pre-declared call ceiling; the three-fold, six-encoder, three-seed physical pilot; its independent artifact and checkpoint audit; and a strict-mode requalification of the VCO success claims.
- Real cost: **2,877 M6 Spectre candidate packages** = 38 qualification calls (including one retained LDO measurement failure) + 2,811 pilot + 28 strict requalification, plus 1,566 real SAC updates. There were no automatic retries, cache hits or hidden failures. All four cores and the PDK entry/MOS hashes were unchanged at the final inspection. Final regression: 574 passed, zero failures/errors/skips, excluding the separately owned `tests/workbench`.
- Findings: GT adaptation succeeded on 2/3 OTA, 3/3 LDO and 3/3 VCO seeds; GT scratch 2/3 in each class; every frozen encoder 0/3; coordinate pattern search 3/3 in every class without pretraining. All 36 VCO successes were confirmed with the reference deck, and the fast policy agreed within its pre-frozen limits with a systematic +0.015% frequency difference. **There is no evidence of a GT or transfer advantage, and none of a disadvantage**: with three seeds, a 3/3 result has a Wilson 95% interval of about 0.44–1.00.
- Limits that define "pilot scale": one previously characterized topology per class, so not a blind category test; targets chosen with knowledge of qualification data; eight-step episodes; three seeds; nominal TT/27 °C only; an assisted-startup VCO testbench; encoders not parameter-matched; twelve scratch successes came from the initial random candidate; wall times from a shared host. The pilot validates the machinery and gives a first look. It cannot support general transfer, encoder-ranking, convergence or robustness claims.
- Explicitly not done and not part of this closure: a larger, prospectively defined set of unseen circuits with longer training, which is the experiment that could answer the M6 question; single-policy heterogeneous concurrent sampling; surrogate models; structural global attention; wider parameter domains; other optimizers; PVT top-k post-verification scheduling, Monte Carlo, and phase or transient noise. The 69-call `plan-feasible-r2.json` requalification stays frozen and unexecuted. Each of these needs a new, explicit user decision and budget.
- Roadmap: the milestone plan defines nothing after M6, and M6's remaining items were optional extensions, so further work is user-defined. The web workbench specified in `gator_claude_code_fable51_frontend_data_outputs_en.md` is being built separately in `src/gator_workbench/` and tracked in [frontend implementation status](frontend_implementation_status.md); it is not an M-series milestone. Machine-readable closure: `artifacts/local/m6-closure-summary.json`.

## port_gnn removed from the package (2026-09-24)

- User decision after the review "which encoders can be ignored or deleted": `port_gnn` (the M5 port message-passing control, legacy `attention_mode='port_message_passing'`) is deleted from `src/analog_optimizer/models/encoders.py`, from the benchmark runner and from the M6 protocol configuration. It answered the same question as `rgcn` (edge-typed message passing without attention), had no published reference behind its exact form, and every encoder scored alike in the M6 real pilot (adaptation 2/3, 3/3, 3/3 for all six).
- Consequence accepted by the user, stated before the decision: the source digest changed from `02127bc3...` to `aa987cf0e3033d9c87b16693e10f8632eb69942d0d8d182ad7e3ac61ce9aecd1`. Every checkpoint saved before, and the M6 audit re-runs, load only from source commit `bbdfe365718bd0e780aecafd60eabd8f1306fdf0`, the last that carries port_gnn. The executed M6 protocol keeps its six-encoder definition inside `artifacts/local/m6-real-protocol/protocol.json` (with `source_sha256`); `configs/m6_real_cross_category.json` now lists five encoders, so a re-run of that protocol plans 2,370 calls instead of the 2,811 of record.
- Naming the encoder is refused in words everywhere it could be typed: `ModelConfig` (both spellings), `benchmark_models` (`settings['encoders']` is now required; the omitted-selection M5 six-method protocol went with port_gnn) and the workbench run schema. Five encoders remain: `graph_transformer` (default), `gat`, `rgcn`, `gcn`, `mlp`. The test that exercised port-GNN's port gradients (`tests/test_transfer.py`) left with it; the per-encoder gradient tests in `tests/test_graph_sac.py` cover the five.

## Only Graph Transformer, RGCN and GAT remain (2026-09-26)

- User first restricted M6 to RGCN, GAT and Graph Transformer, then explicitly requested deletion of the other encoders. Removed `NodeMLPBlock` and `GCNBlock`, their optimizer registrations, CLI choices, workbench schema options and publication presets. `port_gnn` was already removed. The shared feed-forward `mlp()` helper remains part of the retained encoders and SAC heads; it is not an encoder option.
- `ModelConfig`, the benchmark configuration and the workbench reject removed encoder names explicitly. The workbench offers only `graph_transformer`, `rgcn` and `gat`, including its frontend fallback. Existing settings and experiment artifacts are preserved. Generic PyG graph-export tests remain independent of optimizer encoder availability.
- New M6 runs use three encoders, each with scratch/frozen/adaptation, plus random and coordinate search: 11 target methods. The default synthetic suite plans 873 evaluations; the one-seed/two-step smoke plans 189. The physical manifest plans and caps 1,488 candidate packages (486 source + 108 validation + 891 target + 3 final baselines). No real run or new physical frozen protocol was created.
- Source digest changed from `aa987cf0e3033d9c87b16693e10f8632eb69942d0d8d182ad7e3ac61ce9aecd1` to `75c7cfaccd163604760a6e0c1a71e79e69b80e2c125381d092c117e15a9ef43f`. Exact `SACLearner.load`/workbench resume needs matching historical source and dependencies: `9bc488f` is the last five-encoder source, and `bbdfe36` matches the recorded six-encoder physical M6 pilot. Workbench fine-tune/frozen modes retain their existing shape/schema checks and source-difference warning for supported architectures; deleted encoders cannot be reconstructed. No compatibility check was bypassed.
- Historical six-encoder result tables, checkpoints, audits and strict VCO requalification evidence were not changed. Current run instructions and budgets now identify the three-encoder configuration; historical plans must be checked with their pinned source/configuration. M6 remains closed at pilot scale, without a new transfer-performance claim.
- Validation: full regression **1,223 passed**, zero failures/skips, in 117.29 s with local IPC enabled; after the final error-message clarification, all **12 focused rejection tests passed**. TypeScript `tsc --noEmit` passed. The first sandboxed targeted run was interrupted after 161 passes when it stalled; the complete rerun passed. Only synthetic/test-fixture execution was used, with zero new real simulator or paid agent calls. Frontend browser checks were updated for RGCN, but this session did not rebuild the live dist or rerun the browser script.

Final-source synthetic smoke and independent audit: **189 evaluations, 45 SAC updates and 27 checkpoints**, all restoration/isolation/exact-recovery checks passed, zero real calls. Scratch evidence: `/tmp/gator-three-encoders-final/db9586935928441dbda2159769239794/audit.json`; the source digest matches the final value above.

## Replace GATv1 with GATv2 (2026-09-26)

- User explicitly requested replacing the old GAT after discussing its attention and checkpoint compatibility. The only encoder choices are now `graph_transformer`, `rgcn` and `gatv2`; GT remains the default. `PortGATv2Block` uses PyG `GATv2Conv` with port edge features, separate source/target projections (`share_weights=False`), no inserted self-loops and no additional internal residual. The existing outer residual, LayerNorm/feed-forward, goal inputs, parameter-group actions, critics and SAC semantics are unchanged.
- Optimizer/CLI/workbench selections, M6 manifest, benchmark labels, attention capture and agent settings guidance all use `gatv2`. Old `gat` configurations are rejected with an explicit replacement message; old GAT weights are not migrated. Saved `gat` preset entries are left untouched and are not read as `gatv2` settings. Preset numbers retain the former GAT starting values, with every cited field marked as borrowed from a different architecture. Historical GAT paper quotations, parameter counts, results and artifacts retain their original meaning.
- At hidden 32/four heads, the attention convolution has 3,200 parameters versus the former GATv1 convolution's 2,176. This is not a parameter-matched comparison or evidence of improved optimization/generalization. The three-encoder M6 budgets remain 873 default synthetic evaluations and 1,488 planned real calls. No real run or new physical frozen protocol was created.
- Optimizer source digest changed from `75c7cfaccd163604760a6e0c1a71e79e69b80e2c125381d092c117e15a9ef43f` to `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54`. A verified snapshot of the preceding optimizer source, constraints and package declaration is preserved at `artifacts/local/optimizer-source-snapshots/75c7cfaccd163604760a6e0c1a71e79e69b80e2c125381d092c117e15a9ef43f/`; its `snapshot.json` records the matching digest. Exact resume still requires the checkpoint's source/dependency contract. Existing workbench transfer compatibility checks are unchanged; they do not make GATv1 weights compatible with GATv2. No historical checkpoint or frozen evidence was rewritten.
- Validation: **1,230 tests passed**, zero failures/skips (139.62 s, 12 workers with local IPC), including GATv2 SAC updates, exact next-update restoration, mixed graph batches, port/action gradients, saved-model structure and graph-view attention normalization. Legacy configuration/settings rejection is covered. `tsc --noEmit` passed; browser fixtures were updated, but the live frontend was not rebuilt or the backend restarted. Full-suite JUnit: `/tmp/gator-gatv2-tests.xml`.
- Final-source M6 smoke and independent audit: **189 synthetic evaluations, 45 SAC updates, 27 checkpoints**, all environments restored, train/validation/test isolated and checkpoint recovery verified. Evidence: `/tmp/gator-gatv2-smoke/39b99aaaf550426a8621a2df353afdc9/audit.json`. Synthetic CLI dry-run lists exactly the three retained encoders and 873 evaluations. Physical planning is tested with fixture bindings; a direct CLI dry-run without bindings correctly refuses to prepare a plan. Zero real simulator or paid agent calls.

The initial sandboxed focused test run stalled after 149 passes on local IPC. Automatic approval review first rejected the interrupt because it mistook the sandbox wrapper PID for pytest; a targeted process check confirmed the child PID, and the stop was approved. SIGINT did not end the blocked process, so an approved SIGTERM stopped only that run. The complete regression rerun above passed with local IPC enabled.

## Reward v2: worst case across test conditions - preflight stopped (2026-09-26)

- The reward design decision of 2026-09-24 ("write the plan with permission of changing the optimizer part for astra for the reward design plan") was invoked for implementation on 2026-09-26. The user required section 6 order, no commit/push/live frontend build/backend on 8765, and a stop when a requirement cannot be met as written. Step 1 is complete; implementation stopped before step 2, pending clarification of S2/G11 and P5/G10.
- S2 at worst-spec share 1 ignores soft-spec violations, contradicting G11's universal "0 iff every active spec is met". A checked two-spec example has hard violation 0, soft violation 1, equal weights: nominal reward -0.5, S2 reward at share 1 is 0. Separately, P5/G10 demand five encoders but the current package has only Graph Transformer, RGCN and GATv2 after the user's changes in records 7.86-7.87. Proposed corrections are recorded but not applied; no gate was relaxed.
- Exact list of optimizer files changed by this task: **none (`[]`)**. Before and after digest are both `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54`. The brief's `aa987cf0e3033d9c87b16693e10f8632eb69942d0d8d182ad7e3ac61ce9aecd1` is historical, not this task's measured baseline. Existing uncommitted work was preserved.
- G7 baseline, using the default `synthetic:gpdk045_ota5` starter: task hash `5f181ef30c4ba6b5a1663871f07d48c9ed976334b6b8babd9870a7157c8a978a`, config hash `8d242d6799322f37853cde5e13613ef9c99fc4c027c9cd6a3e6d748f510d241d`. Full configuration saved in `artifacts/local/reward-v2-baseline.json`; no post-implementation comparison or end-to-end G7 run. G9 baseline recorded. G1 **not run** (0 candidates compared, differences not assessed). G8 **not run** (0 suite tests, duration not applicable); TypeScript and browser checks not run. G2-G6/G10/G11 execution not started; G11 has the specification contradiction above, not a passing result.
- Not done: section 6 steps 2-7, including evaluator, observation/replay/checkpoint, operating-point input, condition scheduling/adapters, workbench/UI, identity script, implementation docs and acceptance suite. The user-required stop precedes these changes. Optional migration is not authorized. Cost: **zero simulator calls**, including synthetic; zero bridge/SSH/agent CLI calls; no backend started, live build, commit or push. All real Spectre behavior remains unverified.
- Findings: `artifacts/local/reviews/astra-reward-v2.md` (git-ignored, requirement IDs and the proposed resolution). Workbench record **7.88**, the next free number under D3; 7.84 was already occupied and the rollover already completed. This entry records a blocked preflight, not delivery of reward v2.

## Reward v2 replacement plan: real-flow validation and optimizer permission (2026-09-26)

- The user said: "Dont use fictional MOCK, run real flow if test is needed. Consider the project, give a new plan with permission to modify optimizer code." Delivered [the replacement plan](plan-reward-v2-real-flow.md), with explicit permission for its listed optimizer modules. It supersedes the earlier plan/brief for implementation, including their no-simulation rule and MOCK acceptance stages. The earlier documents now point to it. This turn writes a plan; it does not implement or execute it.
- Proposed reward: preserve the exact legacy default; explicitly select compressed violations and a 0.5 worst-hard-spec share for initial robust runs; evaluate all four additional corners for valid nominal candidates, including nominal failures to meet specs. Skip-on-fail training is deferred because its unmeasured corners make the comparison optimistic. Feasibility is a separate complete-coverage hard-spec verdict. Correct the lambda=1 property, preserve optional-coverage semantics and use the current GT/RGCN/GATv2 set.
- Proposed margin revision: reward the tightest eligible hard-spec clearance, excluding zero-width equality constraints from the bonus but not from feasibility. The real OTA7 target `unity_downward_crossings == 1` would otherwise force the minimum margin to zero. Keep objective/margin bonuses off in the initial live learning smoke; preserve operating-point inputs from actual nominal DC measurements. Exact resume must refuse changed reward/condition contracts; permitted fine-tuning starts new replay/critics for changed rewards. Legacy failure termination stays in compatibility mode; robust attributed failures may continue with masked observations, without inventing new failure attribution.
- Real qualification starts with the dedicated `real:gpdk045_ota7` flow and its existing two width groups. The plan proposes stage ceilings of **21 + 43 + 13 = 77** new Spectre invocations, including baseline/repeat/restoration confirmations, real save/resume and shared launch-budget validation. These are proposed engineering ceilings, not user-supplied numbers or spent calls. Launch capacity is reserved before dispatch for the whole candidate. A separate optional three-arm/three-seed reward study is costed at at most **999** calls and is not automatically launched as a software test. No MOCK or fake-backend result qualifies either stage. Pure calculations and replay of recorded real measurements remain explicitly labeled checks; unrun legacy synthetic-suite coverage must be disclosed.
- Exact optimizer files changed by this planning turn: **[]**. Re-measured source digest remains `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54`; no checkpoint contract changed yet. Zero real or synthetic simulator calls, zero bridge/SSH/agent CLI calls, no backend started, no live frontend build, no commit or push. Budget arithmetic and source/encoder identity were checked locally; no implementation acceptance gates were run. Current simulator availability and all new real-flow behavior remain unverified. Workbench planning record: **7.89**.

## Reward v2 implementation: real acceptance blocked by license visibility (2026-09-26)

- The user invoked the replacement plan with "go on build the reward". Its explicitly permitted
  optimizer changes are now integrated: versioned reward/coverage, tightest eligible clearance,
  nominal operating points, v2 inputs/replay/checkpoints, derived OTA7 decks, whole-candidate launch
  reservations, recording and workbench/UI plumbing. GT/RGCN/GATv2 blocks and SAC update equations
  are retained. Current details and exact scope are in [reward-v2.md](reward-v2.md).
- The pre-edit optimizer source was snapshotted without a commit. Digest changed from
  `5e8a1bc155e60233d1bfa5eb8ec20e7d3d9c6fbd57b70eadfbec8a192e4ada54` to
  `11e6265703332c3479072d76be3ebb771a345d3639f4b5486b4cd918b1e0cf98`; exactly 17 permitted
  package files differ. Protected configs/examples and both default real OTA7 hashes are unchanged.
  V1 checkpoints are refused, not migrated. Shared peer commits/builds were preserved; this task
  did not commit, push, build live dist or operate the backend on 8765.
- Final selected non-MOCK checks: 66 passed, 0 failed/errors/skips, 12.81 s; TypeScript passed.
  Final-source identity checks all 2,811 historical REAL M6 records (2,808 fold + 3 final): bitwise
  reward, absolute 1e-12, verdict and violation agreement all 2,811; zero exclusions. Historical-real
  transitions exercise all three encoders with OP on/off, actual updates and exact next-update
  recovery. These are not new on-policy runs or an old-checkpoint/PSF requalification.
- A frozen no-call preflight passed bridge/profile/tunnel/daemon/readiness/Spectre, but license
  visibility is `unknown / license_not_checkable`. Per the user's stop-and-ask instruction, real
  stages A/B/C are unstarted: **0 new Spectre calls, 0 physical mutations, no restoration required**.
  The user was asked to resolve the prerequisite or explicitly acknowledge unknown license status.
  Final-source re-freeze, real stages, current-source scratch browser checks and physical failure/
  success coverage remain outstanding. No optional study or replacement MOCK flow was run.
- Section-8 gate results and raw paths:
  `artifacts/local/reward-v2-real/20260926-implementation-01/acceptance-summary.json`.
  A1/A2 pass their no-call checks; A3-A8 are blocked/partial, not full acceptance. Record **7.94**.
- Final scope audit also found that `recording/reader.py`, absent from the permission list, still
  rebuilds overview constraint rows from nominal metrics. The file was not edited; explicit limited
  permission was requested. Core recording preserves all v2 data, but that legacy display remains
  an implementation gap, not a passing robust report.

## Reward v2: bounded real qualification completed (2026-09-26)

- Follow-up authorization acknowledged `license_not_checkable` through the existing gate and
  permitted the `recording/reader.py` repair. Spectre used normal licensing; no licensing bypass.
  The reader/report now use stored condition results, actual bounds and explicit coverage.
- A passed with 21 real calls. The first B attempt spent one nominal call before a missing `json`
  import in the workbench commit path stopped persistence. Raw result and charged ledger survive;
  there was no evaluation/job row or transition. Fixed the import, added regression coverage, and
  asked before increasing B. User reply: **"允许 B 上限 44，总上限仍 77"**. The replacement freeze
  pins passed A, the failed B evidence and repaired source. B then used 43 calls; C used 8.
- Total **73 confirmed Spectre calls, 0 uncertain**, including all baseline/reset/restoration calls
  and the failed-at-recording call. No automatic physical retries. B pause/save/resume produced
  10 evaluations, 42 job rows, 8 transitions and 7 SAC updates. C produced 3 evaluations, 7 jobs,
  1 transition and no update; its shared 11-call training cap refused another five-job candidate
  when only four slots remained. All preparation restores and final baseline confirmations passed.
- Preserved and resolved acceptance-driver faults: pre-dispatch counting of `None` (zero calls),
  same-process resume lock handoff (continued the already prepared segment), and cross-encoder
  legacy attention alias (recorded replay only). Browser text assertion and scratch-service
  interruption were repaired without any simulation. Reports retain the earlier failures.
- Final checks: **70 selected non-MOCK tests**, zero failures/errors/skips; 2,811/2,811 historical
  real reward identities are bitwise equal (also within 1e-12, no exclusions); six GT/RGCN/GATv2
  x OP on/off checks on B's real replay pass exact next-update recovery. TypeScript and 18 browser
  checks pass against current source on isolated 5187/8837 with actual real API/results, no route
  interception. Scratch services stopped; no live dist build, 8765 operation, commit or push.
- Final optimizer digest `3473ed9c8336e0a01e82bb84d13f4ea416961024092810c22cd4ce8ce58f8731`;
  19 files differ from the recoverable baseline snapshot. All 63 protected hashes and default real
  config/task hashes are unchanged. Final manifest SHA-256:
  `dd0c2355f25801e73d21614715b313e827a314a436af3eab23f9acdeb796e88c`.
- Gates A1-A8 pass as bounded engineering qualification, with declared physical coverage gaps.
  One B nominal-feasible candidate, no robust-feasible design; no reward superiority conclusion.
  Physical bonus/failure/cancellation/uncertain-launch/worker-loss cases were not induced; legacy
  full suite, MC, v1 migration, skip-on-fail and the separately proposed 999-call study remain undone.
  [Status and exact file list](reward-v2.md), machine evidence:
  `artifacts/local/reward-v2-real/20260926-qualification-05/acceptance-summary.json`. Record **7.95**.

## Reward v2 audit fixes (2026-09-26)

- The audit of the reward-v2 implementation (workbench record 7.97) ran the repository's full regression suite, which the qualification had replaced by a 70-test selection, and found it red: 130 failed, 115 errors. Two behaviour regressions and one plumbing gap were fixed on the user's instruction ("fix the three issues") under the standing reward-v2 permission: (1) `envs/sizing.py` treated a result without `simulator_invocations` as an uncertain physical launch and truncated the candidate, which made every synthetic / MOCK evaluation fail; a synthetic result is now a complete call with zero real invocations and only a real task's launch can be left unresolved (`recording/store.py` accepts an intent with 0 or 1 uncertain calls); (2) `models/inputs.py` refused every `SpecSchema.version` but `spec-input-v2`, which broke the untouched M6 modules that name their registries; the version is identity again and the layout is a separate validated field `layout = 'spec-input-v2'` in every checkpoint contract; (3) MOCK runs now receive the run's reward settings (the learner enforces them on every replay batch).
- Source digest changed from `3473ed9c8336e0a01e82bb84d13f4ea416961024092810c22cd4ce8ce58f8731` (the digest of the real A/B/C qualification) to `f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a`. Exactly three package files changed: `envs/sizing.py`, `models/inputs.py`, `recording/store.py`. The reward arithmetic is unchanged: the recorded-real identity check on the final source gives 2,811 / 2,811 bitwise, 0 exclusions. Checkpoints written at `3473ed9c...` (the qualification's B run) load only from a source with that digest, as every earlier digest step.
- Validation: full suite on a clean snapshot **1,266 passed, 7 failed, 15 errors**, all 22 being the evidence-dependent reward-v2 tests that cannot see `artifacts/` from a snapshot; on the working tree those 143 tests pass, so every collected test passes. Eleven adversarial environment tests of the audit pass on the fixed tree. Zero simulator, bridge or agent calls; nothing committed or pushed. Details: workbench record 7.98, `docs/reward-v2.md` "Audit Fixes", `artifacts/local/reviews/fable-audit-reward-v2.md`.

## Reward v2.1 (2026-09-29)

The user authorized only section 4 package changes of `docs/brief-reward-v2.1-for-astra.md`, as one digest step, and
workbench steps in section 7 order. D1: continue attributed failures; D2: band 0.5; D3: compressed violations/share 0.5
only for new configurations; D4: separate optional alpha learning rate; D5: the brief's explicit scale suggestions,
without backfilling saved empty scales. Approved numerical guards preserve strict gate ordering and objective <1 under
floating-point rounding. Approved episode clarification preserves termination without bootstrap at the normal horizon
and configured success termination; only the failure-caused early ending is removed.

Package digest before: `f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a`.
After: `3f00832c89c1cf7af5cbc5ab6dac74c20250a76ea7bfa3a2df06717087fdd6f4`.
Exactly eight package files differ from the pre-edit snapshot: `measurements/specs.py`, `envs/sizing.py`, `models/inputs.py`,
`training/replay.py`, `training/sac.py`, `training/runner.py`, `training/parallel.py`, `recording/reader.py`. The workbench
step makes no further digest change. Historical exact-resume source/dependency checks are not bypassed.

The user rejected shipping 0.0065 based on a transient 500-update entropy crossing and requested a 1,000-update repeat
at 0.003, 0.005, 0.0065 and 0.01. None meets the declared sustained ±0.15-nat criterion with arrival by 500 and no
individual dip below −2. New configurations therefore leave alpha learning rate empty, inheriting the actor's rate.
This is an algebraic synthetic-transition unit check, not tuning on circuits; all original and extended results remain.

Offline gates pass: 2,811/2,811 bitwise identities, all 12 recorded A/B/C rewards exact, pinned OTA7/default/protected
and saved-file hashes unchanged, full suite 1,414 passed, TypeScript clean, 27 hermetic scratch browser checks.
The corner-target warning identifies recorded misses without blocking a start; no target or parameter range was changed.
Section 7 stops after step 5. D6 launch ceiling is unapproved and D7 is deferred; no physical call, live build,
backend-8765 action, commit or push. [Full report](../artifacts/local/reviews/astra-reward-v2.1.md),
[contract and limits](reward-v2.md#reward-v21-2026-09-29), workbench record 7.106.


## Reward v2.1 real-check ceiling and connection stop (2026-09-29)

D6 is approved for at most 30 OTA7 Spectre launches: first run the workbench connection test, stop if it does not
pass and never repair the tunnel/daemon; state the sequence first; include qualification-05 stage B’s last design;
no retries; restore the captured starting design and confirm it nominally inside the cap; audit reservations,
charges, actual launches and all rewards. Planned 10 expected / 18 maximum launches, including restoration.

The first full connection check passed every layer except `spectre_license`, which returned unknown /
`license_not_checkable`. Execution stopped before any parameter write or simulation. Reservations / charged / made
are 0 / 0 / 0. This is an unverified license status, not an observed license denial. Proceeding with that unknown
status awaits the user’s decision. No tunnel/daemon changes or retries. Package digest remains the one above.
[Evidence and report](../artifacts/local/reviews/astra-reward-v2.1.md#step-6-follow-up-approved-ceiling-stopped-at-connection-test),
workbench record 7.107.


## Reward v2.1 real check completed (2026-09-29)

After the assistant explicitly asked whether to proceed with license status unverified, the user answered “go on”.
All other D6 conditions remained: the stated fixed-action sequence, 30-launch ceiling, no retries or tunnel/daemon
repair, stage B’s last nominal-passing design, starting-design restoration and a final nominal run inside the cap.

Completed in 32.519 s with **10 real Spectre launches**. Cumulative reserved capacity **18**, charged/made **10**,
unused released **8**, outstanding/uncertain/retries **0**. Stage B steps 1 and 2 each failed nominal and skipped all
corners; its last design passed nominal and ran all four corners, but did not pass the complete specification plan.
Three transitions passed replay admission; the final step respected the normal horizon without bootstrap.
All six recorded rewards independently recompute exactly (maximum difference 0.0); ten independent PSF reparses match.
Starting/restored full snapshots and all six nominal metrics match exactly, including the final confirmation as launch 10.

This is a fixed-action physical gate check, with zero learner updates. No broken design was forced; A1’s physical
failure case remains unobserved. D7 and the matched comparison are still separate decisions. Package digest remains
`3f00832c89c1cf7af5cbc5ab6dac74c20250a76ea7bfa3a2df06717087fdd6f4`; no implementation change, live build, 8765 action,
commit or push. [Section 10 report](../artifacts/local/reviews/astra-reward-v2.1.md#step-6-completion-real-gate-check-and-restoration),
[execution audit](../artifacts/local/reviews/astra-reward-v2.1/step6-20260929-01/execution-audit.json), record 7.108.


## D7 replaced by an OTA7 current-reference variant plan (2026-09-29)

The user declined choices 1–3 as the next step and requested **plan only**: a new OTA7 task with an ideal current
reference into a diode-connected NMOS feeding M5/M7, reference current based on their recorded nominal operating
point, and input common mode VDD/2 at every condition. Same targets; frozen original task and all pinned files
untouched. The user copies the new testbench in Virtuoso. The task must not write an original DUT through a copied
parent testbench. No code, cell write or simulation is authorized by this planning request.

First proposed qualification is exactly five launches: the reference design at nominal and four existing corners,
with a separate budget approval before execution. Report misses; only measured remaining misses may lead to a
proposal for corner-specific limits. No automatic return to a sizing search, wider ranges or a matched study.

Nine recorded designs reproduce SS gain misses 3.661441–3.860192 dB, SS UGB 0.969687–0.999504 MHz and FS power
1.002168–1.280706 µW. The recorded reference currents are M5 1.956361054911864 µA and M7 1.165778491724812 µA.
Their ratio differs from the width ratio; one reference-current seed does not establish a calibrated simultaneous
match after the input common-mode change. Nominal-current tolerance was asked and remains pending.

The user explicitly chose to keep the **core-only 3.24 µW power target**, with bias/reference power reported
separately. [Variant plan](plan-ota7-current-reference-variant.md) gives the proposed topology, current seed and
qualification/approval sequence. No new simulation or implementation; record 7.110.

## Reward v2.1 commit authorization (2026-09-29)

The user explicitly requested `commit`. Reward v2.1 is committed as separate package and workbench changes under
the brief's rule; pushing is not authorized. Package commit `8cf53ae` retains the audited final digest above.
Fresh full shared-tree regression: 1,417 passed; the selected workbench snapshot: 727 passed. TypeScript passes on
both trees; selected reward and Specs browser checks pass 27 and 15 cases. Shared-file selections exclude unrelated
sessions' edits. The OTA7 variant follow-up is stopped and remains outside these commits. Record 7.111.

## LLM sizing plan reduced to two search choices (2026-09-29)

After requesting the fewest modes, choosing SAC and LLM warm start → SAC, and reviewing current LLM/RL publications,
the user requested an updated plan. The [revised brief](brief-llm-sizing-for-astra.md) replaces the nine-method design.
Plain SAC remains unchanged. The assisted method collects simulation-verified experience, explicitly trains the
existing SAC learner on it, then hands control to SAC without a second random warm-up. Handover depends on admitted
transitions and completed updates, not elapsed time. The selected graph encoder, reward, replay eligibility and
action contract remain unchanged. A failed LLM start may fill its remaining slots with recorded random fallback.

Random and pattern search stay benchmark baselines. Matched random and seeded starts receive the same initial SAC
update budget as the LLM arm to separate the value of its data from extra training. Stagnation assistance and LLM
action masks are deferred; they add no workbench modes or placeholder implementation. Literature motivates the
experiment, not a claim that this combination is best. Proposed counts and paid-call ceilings are documented in the
brief; no new real LLM, Spectre or bridge call is authorized by this planning request.

Plan revision only: no optimizer or workbench implementation change and no new simulation. Earlier preflight evidence
at `5a39f89` remains historical baseline evidence; implementation acceptance is still outstanding. The brief resolves
the old S6/W1 waiting question and keeps the section 7 order. No new commit or push requested.

## LLM sizing plan expanded to four search choices (2026-09-30)

The user explicitly added **LLM only** (AI proposes every design) and **SAC with LLM rescue** (SAC runs; AI
contributes suggestions when progress stalls). This supersedes the two-choice scope and rescue deferral in the
2026-09-29 entry above. The [brief](brief-llm-sizing-for-astra.md) now specifies exactly four methods: `sac`,
`llm_warmstart`, `llm`, and `sac_llm_rescue`.

LLM only uses one baseline and subsequent LLM-proposed designs with simulation feedback; it has no SAC learner
and stops when proposals or authorization are exhausted. Its first implementation uses one lane and supports
search-state resume without policy weights. Rescue keeps normal SAC warm-up and learning, requests suggestions
asynchronously after a recorded stall, and admits eligible simulated suggestions to SAC replay. SAC keeps running
while waiting or after provider failure; round and call limits bound intervention. Warm start retains its explicit
initial training phase and has no later rescue. Random/pattern search remain benchmark baselines.

Settings, UI captions, hints, persistence, acceptance gates and benchmark slices are updated together. Paid ceilings
for the new benchmark slice remain proposals requiring separate approval. This change updates the plan only; no
optimizer/workbench code, real model call or simulation was run, and nothing was committed or pushed.

## Four sizing methods implemented; benchmark acceptance incomplete (2026-09-30)

On the user's “ok build, note frontend backend consistency”, the four-mode brief was implemented in its section 7
order through free verification. New package code is confined to `search/` and additive `ActionMapper.encode`;
SAC losses, reward, replay eligibility and legalization are unchanged. The optimizer digest changes once from
`3f00832c89c1cf7af5cbc5ab6dac74c20250a76ea7bfa3a2df06717087fdd6f4` to
`27a36b2b74ec29f69bf916a8d6079b2cca78dea07fd9887d939211fe070d2f49`.
The refreshed preflight snapshot at HEAD `60800796` and final plain-SAC run match in all seven raw tables after
documented time/path normalization. New workbench settings, scheduling, provider isolation, persistence, tables and
frontend follow one contract. User and other sessions' pre-existing changes remain preserved and uncommitted.

An earlier full suite passed 1,466 tests with one benchmark subprocess timing out under parallel load; that unchanged
test passed alone in 27.47 s. The final suite passed 1,482 with two old validation expectations failing; both were
updated for the newly visible current-unit blocker, and all 15 affected-module tests passed on rerun. Supplemental
checks cover prompt compaction, controls and rescue resume. The final provider/API module passed 20 tests, including
model-specific effort inheritance. TypeScript passed, as did 31 sizing and 96 Agent browser
checks on scratch ports. All six scheduler arms
completed a free level-1 ngspice fixture with fake AI responses and fixed bias current. This establishes integration,
not an improvement in circuit performance. Evidence and gate details are in
`artifacts/local/llm-sizing/acceptance-summary.json` and [LLM sizing](llm-sizing.md).

AnalogGym-Opt is outside the repository at MIT commit `10093e3496ef2c7d06494d91d131b0cc5de6c25b`. Ten amplifiers passed
20 strict seeded parity designs each; seven circuits are excluded, without relaxed tolerances. Calibration is not
run: the benchmark asks for several after-feasible objectives but GATOR permits one. A second blocker is the existing
SAC input contract, which rejects `dc/A` parameter groups. Workbench validation now explains this before starting;
extending the optimizer outside the brief's allowed files awaits the user. No benchmark variables or objectives were
silently changed. Reached analysis commands are now recorded before raw-file retention; incomplete output keeps
unknown totals. Both best-design testbenches are exported and re-parsed. A representative ACBC design passed strict
parity with analysis instrumentation and again through the exported decks. Final suite results are in the acceptance
report; no package digest changed during these workbench fixes.

G10 failed: executable discovery in a regression test accidentally launched one real Codex request. The server
rejected its configuration-proposal schema with HTTP 400 and produced no model output. Usage/cost were unreported,
so zero cost is not proven. Discovery is now sizing-specific and tests block real model executables. The incident
is retained at `artifacts/local/llm-sizing/provider-launch-incident.json`. No Claude, Spectre or bridge call was made
by this work, and no paid experiment is approved. L1/L2 remain open before any paid slice. No commit, push, live
frontend build or 8765 restart; record 7.116.

## LLM duplicate check compares to a tolerance (2026-09-30)

On the user's instruction ("fix the four") the one open finding of the LLM-sizing audit was fixed in the optimizer
package: `LlmProposer` compared proposed, evaluated and queued designs as exact floats, and a size on a group
without a grid step comes back from `legalize(encode(v))` a few ulp away, so 32 % of exact repeats were evaluated
again. Designs are now the same when every group is within 1e-9 relative. The change is confined to
`search/llm.py` (9 lines out, 10 in); SAC, reward, replay and legalization are untouched and the seeded MOCK SAC run is row-identical.
Optimizer digest `27a36b2b…` → `100945fb780852ea3776a2395f83474bd208ed2f1ee5a27aff7cdf28b0d2651b`. It was landed only
after Astra's calibration and its finalize step had ended (user choice), because both record and check the digest;
Astra's evidence files keep describing the tree before the fix. Full suite 1,601 passed / 1 expected failure.
No commit, no real simulator or model call; record 7.120.

## Real runs: corners two at a time, every 5th reset simulated, Maestro results not parsed (2026-09-30)

From the optimization review of 2026-09-30 (record 7.115) the user chose three changes to the optimizer package, had
them built and tested in a scratch copy while Astra's sizing methods were in flight, and on "Land now" had them landed
together as one digest step, without the calibration audit's `idc` fix ("Mine only"):

- a candidate's corner simulations run two at a time after its nominal one when the circuit is measured from Spectre's
  own results; circuits measured by OCEAN in the Virtuoso session keep one at a time;
- a lane simulates the unchanged starting design at its first reset, every 5th reset and after any failure; the other
  resets reuse the last simulated one and are not charged (MOCK runs unchanged);
- a Maestro task's Spectre writes its own binary results and the bridge no longer parses a text copy ("fetch only when
  kept" would have needed a rewrite of the bridge's Spectre runner, so the user chose "skip only the parse").

Rows, stops and launch accounting match one-at-a-time; OCEAN values agree with the text results to within 2 ulp.
Optimizer digest `100945fb…` → `f42a309884ec5b499f8c38e18a811fd330a0ffa4740363616aeb56104f59146e`. Landed with no
Astra job running and a guarded script that refused any other starting digest. Full suite on a copy of the tree: 1,591
passed without the change, 1,609 with it (18 new tests), none failed. Checked the same evening on MScR circuits (the
user: "Run tests on MScR circuits"): on real:mscr_ota7t the same 10 evaluations bought 8 steps instead of 5 at the
same pace; a real:mscr_ring3 run exposed a fault of the form writer (record 7.127), unrelated to this change.
Committed as `898b134` and `e2584fa`. Record 7.126.

## The MOCK task and the real OTA7 and LDO tasks deleted, with their example files (2026-09-30)

On the user's request ("delete the mock OTA5 task and the two real tasks (OTA7&LDO) which are not in the mscr
library") the workbench now offers only the user's saved tasks and ngspice tasks. The user chose "Delete everywhere"
for the MOCK task synthetic:gpdk045_ota5 (the tests keep that circuit as a stand-in they register through
GATOR_WORKBENCH_SYNTHETIC_FIXTURES; the product refuses it with a plain note) and "Also delete their files" for
real:gpdk045_ota7 and real:gpdk045_ldo: their example netlists and configurations and every test that used them are
gone, while the optimizer package's research profiles, configs/m6_real_cross_category.json and the research scripts
stay. Told that the M5/M6 audits and the frozen M6 plan re-hash those configurations, the user chose "Delete them
anyway": those audits re-validate from a checkout before this change, and CLAUDE.md's evidence rule says so. With OTA7
gone no task trains at corners and Corner check has no task. No package file changed, so the optimizer digest is
untouched. Full suite of the tree with the change 1,532 passed, none failed; 33 of 34 browser checks pass (the 34th
fails on an old ngspice model in outputs/ with the old code too). Committed in `e2584fa`. Record 7.128.

## Optimizer fixes held back from review round 5 (2026-10-01)

The round-5 review (record 7.117) left its optimizer findings for one digest step; the user chose "later, after Astra
commits" and, on 2026-10-01, "go ahead with the optimizer fixes", then "land now". Built and tested in a scratch copy of
the tree (7.126 included) and landed on top of 7.126:

- the top grid point of a range typed in decimals no longer lands one float step above its upper bound
  (`ParameterGroup.project` clamps after rounding; every in-range projection is bitwise unchanged; the workbench's
  `compile.grid_top` guard of round 5 stays and agrees with it);
- a corner summary whose OK corner lacks the value of a "Missing value = failed" spec fails that corner instead of
  raising (TypeError for an empty value, KeyError for an absent one; the workbench guard caught only the first);
- a worker result that arrives just after its deadline's wait gives up is returned, not reported as a timeout;
- cost only, the same results: a checkpoint pickles the replay without deep-copying it first (the same bytes; 1,000
  transitions 1.56 s -> 0.49 s), a replay check reads the graph instead of copying it, a batch copies only the mutable
  part of its metadata, and a synthetic (MOCK) environment's journals skip the fsync (10.7 -> 5.9 ms per write on a 9p
  mount); 10 unused imports, `PolicySample.mean_actions`, a per-metric computation and an implied condition removed.

Seeded synthetic training is identical before and after (weights, optimizer states, replay transitions; batch 64 about
24 % faster); G1 reward identity 2,811 / 2,811 on both digests. Optimizer digest `f42a3098…` ->
`0d045b8e3406d93120a81273dc20427b6d04f62901615d2efe4237273a9648c5`: checkpoints saved under an earlier digest no longer
`resume` (`fine_tune` and `frozen` still load). Not taken: the "worst value" tie-break of passing range specs (it changes
network inputs), the homogeneous graph view (`demo.py --homogeneous` uses it) and the GPDK045 profile copy-paste.
Landed with no job running in the tree and a guarded script that refused any other starting digest. Committed as
`5362ebb`. Record 7.129.

## The native preparation reads the cell three times per candidate, not five (2026-10-01)

Measured on Spectre (record 7.136): the one Virtuoso preparation process writes and netlists every candidate, and with
4 lanes it was busy 90% of the time, mostly on five whole-cell reads (0.23 s per candidate on `mscr_ota7t`, about 0.4 s
per read on `mscr_vco_lin`). Two of them repeated a check made a moment earlier, with nothing in between:
- `read_parameters()`, straight after `set_parameters`' own readback;
- the read at the start of `generate_netlist`, together with a second window check.

Asked whether to remove them, the user chose "Yes, remove them". Now the service takes the write's readback
(`VirtuosoBridgeBackend.written_parameters`) and exports with `generate_netlist(..., just_written=True)`, which uses
that readback as its snapshot. The checks that stay:
- the cell is still read before each write, after it and after the export;
- the export is still compared with the readback;
- a cell edited meanwhile is still refused.

New tests in `tests/test_native_preparation.py`: three reads and one window check per candidate, and an edit during the
export refused. Other callers of `generate_netlist` are unchanged. The saving is about 0.12 s per candidate on
`mscr_ota7t` and about 0.85 s on `mscr_vco_lin`.

Optimizer digest `46327861…` -> `66ce02ab91eda506b52a2a727746ff370b7517383eaf3680d507a647caf54797`: checkpoints saved
under an earlier digest no longer `resume` (`fine_tune` and `frozen` still load). Committed as `1c308a5` (optimizer)
and `8043c07`. Record 7.137.

## Netlists built from the readback, checked against every native export; a value at its bound is accepted (2026-10-02)

Record 7.138 found that the decks of different candidates differ only in values: the written ones and those the PDK
callbacks derive, all of which the readback after each write already holds. Asked, the user chose to build each
netlist from the readback in a check-only mode first ("Yes, check-only first"):
- `CdfWritableProfile.render_export` (workbench) puts the readback's values into the value slots of the session's
  first native export.
- With `GATOR_NETLIST_BUILD=check`, the preparation service (`native_preparation.py`) compares that build with every
  candidate's native export, statement by statement, and stops the run on a difference.
- The native export is still the one simulated. Without the variable, nothing changes.

The Spectre trial the user approved (60 simulations, then 40 more) found a separate bug:
- **What happened:** `mscr_ring3` and `mscr_vco_lin` stopped on their first policy design with "l: invalid
  bounds/current value".
- **Cause:** the length was exactly its top value, 180 nm, and the netlist parser reads "180n" as
  1.8000000000000002e-07, which `ParameterGroup.validate` refused against the upper bound 1.8e-07.
- **Fix:** `ParameterGroup.validate` now allows a relative 1e-12 at either bound, the span the form writer's
  `Write.legal` already allows. Only values that were refused before change outcome.
- **Follow-up** (found by the "RL reward design" session): `ActionMapper.encode` allows the same span and maps such a
  value to the end of the action range. Otherwise a starting design one float step past a bound passed the group check
  but failed encoding, in `SeededProposer` and when an LLM reply repeated the start.

Results:
- After the fix all three tasks completed (20 evaluations each at 4 lanes), and every candidate's built netlist had its
  native export's statements.
- 28 exports of `tb_ota7t` timed on Virtuoso: setting OCEAN up once per session would save about 0.09 s per native
  export (0.27 -> 0.18 s). The library refresh and incremental netlisting saved nothing measurable.

Optimizer digest `66ce02ab…` -> `c3a340b9c426742923327c881dcf04d2eeab89efa7a4e1e192b348e89de4513b`. It is one
uncommitted step with 7.137: checkpoints saved under an earlier digest no longer `resume`, while `fine_tune` and
`frozen` still load. Skipping native exports, and the set-up-once export, are open for the user to decide. Committed as
`1c308a5` (optimizer) and `8043c07`. Record 7.140.

## Real runs build most netlists from the readback; OCEAN set up once per export session (2026-10-02)

The check-only mode of 7.140 matched on every candidate. Told what changes and what does not (the netlist Spectre
receives has the same statements, so the results are the same; the guarantee becomes "Virtuoso's export every 5th
candidate, compared with the build" instead of "Virtuoso's export for every candidate"), the user chose:
- "On by default" for building netlists from the readback;
- "Yes" for setting OCEAN up once.

Since then the preparation service (`native_preparation.py`) runs `GATOR_NETLIST_BUILD=skip` by default:
- The first candidate and every `NATIVE_EVERY` = 5th get the native export, compared with the build. A difference stops
  the run.
- The others get the built netlist, without an export or a read after the write.
- `check` keeps 7.140's mode, and `native` exports every candidate and builds nothing.
- The manifest names the source of each netlist.

`VirtuosoBridgeBackend._export_netlist` sets OCEAN up once and only netlists after that, about 0.09 s less per export.
It sets up again when the netlist returned is not the testbench's. Tasks measured inside Virtuoso (the Maestro recipe)
keep the bridge's export, as the user's answer said. Every MScR task is such a task, so there it changes nothing.

On Spectre at 4 lanes (20 evaluations each, cells equal to their records afterwards), against the check-only runs:
- `mscr_ota7t`: 0.70 -> 0.54 s per evaluation;
- `mscr_ring3`: 0.71 -> 0.64 s;
- `mscr_vco_lin`: 2.0 s, unchanged, because its transient jobs set the pace.

Optimizer digest `c3a340b9…` -> `e3f8c5b84c4480f5dcc1feec9539e1635b18306f7ceea86e5e5b2d229ae51315`, the same
uncommitted step as 7.137 and 7.140. Committed as `1c308a5` (optimizer) and `8043c07`. Record 7.142.

## Up to 6 Spectre lanes for a real task (2026-10-02)

With netlists built from the readback (7.142), Spectre set the pace. On `mscr_ota7t` a job took about 1.2 s, of which the
circuit's analyses took about 0.05 s; the rest was start-up, a licence check, reading the PDK model files (0.4-0.8 s)
and copying files. The simulator host has 8 cores and the package allowed 4 lanes. The user chose "Raise to 6":
- `MAX_SPECTRE_WORKERS` (`native_preparation.py`) is 6.
- The workbench's task limit follows it (`tasks.REAL_LANES`).

On Spectre (20 evaluations each, cells equal to their records afterwards), 6 lanes against 4:
- `mscr_ota7t`: 0.54 -> 0.41 s per evaluation;
- `mscr_vco_lin`: 2.03 -> 1.40 s.

Six jobs at once ran with no licence error. Jobs sometimes waited up to 0.8 s for a licence, and each job ran 10-15%
slower on the shared CPUs. The preparation process was busy 71-79% again, so more lanes would gain little without a
cheaper preparation or a Spectre that stays running between jobs.

Optimizer digest `e3f8c5b8…` -> `efa93649d1e792602174994abf4a019e23e9dcf2ccef9ef0e1dd25a1beaab7ca`, the same
uncommitted step as 7.137, 7.140 and 7.142. Committed as `1c308a5` (optimizer) and `8043c07`. Record 7.143.

## Simulator scratch on the local disk; the window check before exports only (2026-10-02)

Where a candidate's time went at 6 lanes on `mscr_ota7t` (7.143's run, from its tables, Spectre's log and the stack
samples; nothing re-run): 0.62 s before Spectre starts (the preparation, about 0.3 s, and its queue); 1.47 s of Spectre
job (Spectre about 1.0 s, of which reading the PDK models 0.43 s; transfers about 0.25 s; the measurement about 0.1 s);
under 0.1 s after. The user chose all four next steps offered:
- **Concurrency 6** for runs from the page: the saved setting was 1. A setting, no code.
- **Job folders on the WSL disk** (workbench code). A run whose folder is on a slow mount (D: from WSL is 9p) keeps its
  lanes' export packages and per-job folders in `/tmp/gator-work/<experiment>/<run>` (`layout.local_scratch`,
  `lanes.ScratchLinked`). The lanes' own folders stay in the run folder: launch journals, candidate records,
  restoration records. Retention moves each kept job folder there as before. `GATOR_LOCAL_SCRATCH=off` turns it off.
  Replayed offline, a job folder took 153.5 ms on D: and 1.7 ms on the WSL disk.
- **One call less per candidate** (optimizer). The window check guards OCEAN's export against an open ADE/Maestro window.
  It now runs before each native export (`generate_netlist`), not before every write (`set_parameters`). A netlist built
  from the readback (4 of every 5 candidates since 7.142) runs no OCEAN, so it checks none. The check took about 0.03 s
  of the one-at-a-time preparation. An open window now stops the run at the next export rather than at the next write;
  the cell is restored either way.
- **A Spectre that stays running:** the user lifted the adapter's rule "No ... Spectre runner ... is reimplemented
  here" for it. Plan: `docs/plan-persistent-spectre.md`; nothing built.

On Spectre with the run folder on D: (`mscr_ota7t`, 6 lanes, 40 evaluations each): 0.84 s per evaluation with the
job folders on D:, 0.50 s with the scratch; cells equal to their records afterwards.

Optimizer digest `34bc85f4…` -> `f83342bcc50a7b385cadad1770d8ae06962d48fa4cdbcb76ceceef08bcb7cc77`, committed as `ab34f03` (optimizer) and `a16bdd1` (workbench).
Record 7.149.

## A Spectre that stays running in each lane: built, tried, removed (2026-10-02/03)

The user chose to build it knowing that a rerun's values depend, in about the sixth digit, on the candidates before it
(7.149's G0): "I'd rather have the ~25% speed-up with those tiny order-dependent differences, build it". The adapter's
rule against a Spectre runner of our own was lifted for it, and the session was built off by default, with a fresh check
every 5th run and a fallback to fresh runs.

On the real Spectre the protocol worked, but trial 1 showed far larger differences (gain 263 against 342). The cause: a
running Spectre follows changes of `w` and `sca`/`scb`/`scc` but not of `l` or `m`, whether through `sclSetAttribute` or
alter analyses. Sizing changes `l` and `m`, so the session could not give correct values. The checks caught it at the
first comparison in every lane, so no wrong value entered the run.

Removed at the user's decision ("Remove it"): the hook, the session code and its tests. The adapter's rule stands as
before, and the digest is back to 7.149's. Record 7.152.

## A trimmed model library, for any circuit (2026-10-03)

User: "build the trimmed library for any circuit", after record 7.153 had measured about 0.25 s of model reading saved
per Spectre job on `mscr_ota7t`, with identical values. Decided:
- The parts come from the library's own layout and the circuit's own devices, at the start of each run - never from a
  list per PDK or per task. The layout is read on the simulator host by names only, so no model text leaves the host or
  enters the repository.
- Only for a task with a recorded baseline. That baseline was simulated with the whole model file, and every simulated
  reset of the start design is compared with it at 1e-6: the guard is the existing one, at no extra simulation. A Single
  baseline simulation (no baseline yet) and the corner check (no baseline at the corners) include the whole file. A
  first-run comparison of the whole and the trimmed file (two more Spectre runs) was not built: those runs would sit
  outside the simulations a run is authorized for.
- Workbench code only (`gator_workbench/model_library.py`, the recipes' decks, the run's builder): no optimizer digest
  step. `GATOR_MODEL_LIBRARY=full` turns it off.

Record 7.154.

## Maestro's unread info outputs left out of a run's deck (2026-10-03)

User: "yes, build it", after asking "you sure dropping the six info outputs will not break any other type of
evaluations?" and two checks on Spectre. A Maestro deck's six info outputs (`modelParameter`, `element`,
`outputParameter`, `designParamVals`, `primitives`, `subckts`) are left out of every run deck of a Maestro task, with a
comment line where they were:
- nothing in GATOR reads them, and the decks GATOR builds itself never had them (their one info output is `dcOpInfo`);
- an output could read them only through `VAR` or `getData(... ?result "<one of them>")`; a task whose outputs do keeps
  all six;
- on Spectre the analysis results were byte-identical without them and the OCEAN measurement the same for all 10
  outputs tried, while each job took about 0.36 s less;
- the operating points (`dcOpInfo`, `finalTimeOP`) stay; `GATOR_INFO_OUTPUTS=keep` keeps the six. Workbench code only.

Record 7.157.

## The run adapter's lock and crash journals on the WSL disk (2026-10-03)

User: "move the crash journal off D:", after record 7.165 found the crash journal of each candidate's write costing
16.2 ms on D: (9p) against 1.3 ms on the WSL disk. The adapter's whole state root moved - the session lock with the
journals, since they share a folder - to `~/.local/state/gator/bridge-state` (`paths.bridge_state_dir()`,
`GATOR_BRIDGE_STATE_DIR`). Decided with it:
- one folder for every GATOR process, not one per settings folder: runs from scratch settings and from the page share
  one Virtuoso session and must keep excluding each other;
- a persistent folder (not `/tmp`): the journals are what tells, after a crash, what was written;
- the tests get a folder of their own (an autouse fixture), so no test can take the real lock;
- sessions before the move stay in `artifacts/local/bridge-state`. Workbench code only.

Record 7.167.

## Folder settings of the connection module (2026-10-03)

User: "I realized the project might be used by others. Add directory settings for necessary files in the connection
module with current setting as default". Decided:
- The folders the workbench fixed outside the repository and the output folder become settings: three on the backend
  machine (adapter state, simulator scratch, bridge checkout) and two on the simulator host (initial-condition files,
  Maestro netlists). Each default is the value used before, so nothing changes until a folder is saved.
- They live in the connection file, as one block for the whole file rather than one per connection. The local folders
  belong to the machine; the simulator-side ones would differ only between two hosts laid out differently, which would
  then be a hand edit.
- Only values that differ from the defaults are written. Connections are still never changed from the browser.
- This is the one connection route that takes paths, and each path is checked:
  - a full path with no `..`;
  - a safe set of characters for the simulator host;
  - a write test for the folders GATOR writes into;
  - not on a slow mount for the scratch;
  - the bridge checkout must exist.
- An environment variable keeps precedence (`GATOR_BRIDGE_STATE_DIR`, used by the tests); a folder it decides cannot be
  edited. The adapter state folder does not change while its lock is held.
- Initial-condition files in the default folder stay recognized after a change.
- Left out:
  - Spectre's job folders on the simulator host: the bridge env file's `VB_REMOTE_SCRATCH_ROOT`;
  - the agents' scratch: the system's temporary folder;
  - the settings folder, which holds the connection file;
  - the output folder, which is already a setting.

Record 7.168.

## The tested defaults: three soft actor-critic values, the reward of a new configuration, the Specs scale (2026-10-05)

User: "check and test other default setting values, and give best default value", then "can you test with spectre
simulations not ngspice?" (about 1 hour and at most 8,000 launches on `real:mscr_ota7t` approved; 1,925 used), then
"record the reasons somewhere" and "update the reward plan according to finding and build it". Measured with 175 soft
actor-critic runs on two ngspice circuits (195,961 simulations) and five Spectre runs; every number is in
`artifacts/local/reviews/defaults-study-2026-10-05/README.md`. Each value below is followed by its reason.

Soft actor-critic (the GATOR baseline of RL networks; the schema defaults are NOT changed):
- **Starting temperature 0.01** (was 0.2). At 0.2 the exploration term (about 1.2) is several times any reward
  difference (0.1 to 0.3), and the temperature's own learning rate cannot bring it down within a run (0.200 to 0.192 in
  131 updates). 0.05 learns as early but ends lower (88 % passing against 97 %); 0.002 learns twice as late.
- **8 updates per evaluation** (was 1). With 1 nothing learns, whatever the temperature, batch or learning rate (at most
  15 % passing after 1,500 evaluations, against 1 % for a random search). 4 learns at about evaluation 1,000, 8 at
  about 470, 16 at about 330. One update takes 0.1 to 0.15 s, so 8 cost about 0.9 s per design.
- **Discount 0** (was 0.99). An action is a whole design and its reward is that design's own measurement, so the value
  of later steps adds only noise: learned at evaluation 269 instead of 466 (and 367 instead of 686 on the second
  circuit). Measured on ngspice only.
- **Why it had to come first:** with the old values the search is uniform and no reward setting changes it. On Spectre,
  "capped, share 0" and "compressed, share 0.5" gave the same design in 147 of 150 positions; 922 designs with the old
  values, none passing; with temperature 0.01 and 8 updates, 36 of 760 passing (the first at design 591).
- **Kept:** batch 8 (32 costs four times as much per update for the same result), learning rate 3e-4, warm-up 8,
  episode length 4, and an empty temperature learning rate (3e-3 and 1e-2 gave nothing alone, were worse with more
  updates, and two runs ended early with a collapsed policy).
- **Budget:** learning starts after 250 to 600 evaluations, so a from-scratch SAC run below 300 is told that it is a
  random search. The page's starting budget of 60 is kept: every evaluation is a real simulation the user authorizes.
- **Where the values live:** the schema defaults (`AdvancedRL`) keep 0.2 / 1 / 0.99, so every saved configuration,
  test and checkpoint means what it meant; the three values are `network_presets.TESTED`, part of `gator_baseline()`
  and of every publication preset's fields that no publication reports. An encoder whose saved values equal the old
  baseline and were saved before the change follows the baseline; the file is not rewritten. Static validation names
  values that do not learn (`sac_values_random_search`), in the page as on the command line.

The reward of a new configuration (frontend `SIMPLE_REWARD`; the schema defaults keep the old arithmetic):
- **Worst hard-spec share 0.5.** With 0 a run ends with fewer passing designs (76 to 86 % of the last 200 against 88 to
  94 %): one row just outside its limit costs only its share of the average. With 1 learning is slower and failed in 2
  of 6 runs: a second failing row earns nothing.
- **Compressed violations.** No difference from capped in training. Capped is flat once a row is a full scale away,
  and 48 of the 227 designs recorded on Spectre have such a row.
- **Objective bonus weight 1.** 27 to 30 % lower power among passing designs on 9 of 9 paired runs, no slower. 0.5 does
  the same. Without an objective row the bonus is 0, so the weight needs no switch and no warning.
- **Objective shape compressed.** No difference from clipped on a "minimise" row, which a clipped bonus never clips;
  compressed also keeps paying on a "maximise" row beyond twice its limit.
- **Tightest-margin bonus weight 1.** 99 % of the last designs pass against 88 to 94 %, no slower, also together with
  the objective bonus. Without a bonus every passing design scores 0 and the policy settles on the edge of the limits.
- **Missing value = failed stays off.** Switched on, it never learned faster and was slower on 7 of 9 paired runs. Off,
  1 % of the designs are dropped and 1 of 89 learning runs stopped on five consecutive failures. It belongs on a row
  whose missing value is the failure itself (an oscillator that does not start has no frequency).
- **Not decided by a test:** the nominal gate band (0.5) and the corner policy; no task has corner decks.
- **A configuration that holds other values is never changed by itself:** the run panel says which values differ and
  offers the tested set on a button.

The Specs scale:
- **Empty, that is the size of the limit.** A scale of 10 % of the limit was better on three of the seven tasks'
  recorded designs and worse on four (71 of 227 designs above a miss of 0.9, against 3). Half the limit is the best
  single value, by a small margin (`artifacts/local/reviews/scale-study-2026-10-05/`).
- **6 dB for a dB row** instead of 3: a fraction of a 30 or 40 dB limit makes each dB count three to five times less
  than the same spec in V/V; 6 dB was better on three of the four tasks with dB rows and equal on the fourth.
- **No more 10 degrees for a phase row or half the width of an interval:** they acted as hidden weights (10 degrees
  reordered the recorded designs of `mscr_ota7t`; half an interval put 30 of 42 ring-oscillator designs above 0.9).
- **Hard and the scale behind "More columns":** none of the 51 saved Specs rows is soft or has a typed scale.
- **A limit of 0 with no scale blocks a run:** it was silently measured against 1 of the row's unit.

Left open: discount 0 and the reward comparisons on Spectre (the approved hour went into the SAC values, because a
six-lane run hit the bridge daemon's limit of 4,096 remembered requests per 15 minutes); the 13 dB rows of four saved
tasks (filled the same day, on the user's "fill them with 6": record 7.187). The larger daemon cache (`RB_NONCE_CACHE_MAX` 32768) was set in the
running Virtuoso the same day, on the user's word; it is not yet in Virtuoso's start-up (record 7.183).

Record 7.183.

## Ideal parts are the workbench's own knowledge, not an example file's (2026-10-05)

- **What happened.** A device type is known from the loaded PDK (Load PDK reads the technology library's own
  description) or from the "verified" list, collected from the example circuits' mapping files. analogLib's ideal
  current source and resistor were in one of those files only. Deleting the examples (record 7.128) therefore made
  "Save task" refuse six of the seven MScR tasks, unnoticed until the first save four days later.
- **Decided now.** The two definitions live in `native_cells.ANALOGLIB_VERIFIED`: deleting an example can no longer
  take a device type away.
- **The user's rule:** "it should be recognizing all the loaded components". Built the same day as record 7.190 (next
  entry).

Record 7.187.

## Ideal parts are read from analogLib with the PDK (2026-10-05)

The user: "build it, read analogLib with the PDK". Decided while building:

- **Read with the PDK, stored in the PDK's record.** One more read-only query in the same press, about a second. No
  new store and no new button: wherever a PDK is read, the ideal parts are read. A failed query never costs the PDK.
- **Verified definitions go first.** A part the project had verified keeps its definition, pin names included. The
  optimizer's description of a circuit holds pin names (`graph_contract`), and a current source's pins are `p` and `n`
  in every saved task while the library says `PLUS` and `MINUS`: taking the library's names would have changed the
  description of every saved task at its next save, for no gain. The library's description fills what had none - and
  would fill all of them, identically for voltage source, capacitor and probe, if the last hand-written file went.
- **The pin order is chosen by the netlist.** One Spectre component is netlisted with different pins by different cells
  (a `vsource` with two nodes or six), and a parser mapping has one pin list per component. So a description is used
  only when it has as many pins as the netlist's lines have nodes; this holds for verified and PDK definitions too.
- **No kind of its own is no refusal.** A controlled source or a port has no kind in the optimizer's standard list. It
  is read as "unknown" with its pins named - as a PDK's diode or bipolar already is - so the cell can be saved and run.
  The six standard kinds come from a small table of Spectre's own primitives (`pdk.IDEAL_KINDS`), not from names.
- **The PDK first, then the cell's mapping.** The read order of a cell changed so that the first read recognizes what
  that very read describes.
- **Left out:** generic libraries other than analogLib; the five components for which analogLib states no pin order;
  more than 64 pins on one line. Each is named where it is met.

Record 7.190.

## The GATOR baseline deleted; the publication preset is the one setting per encoder (2026-10-05)

The user: "Delete the gator baseline in RL networks and keep the publication preset, delete two buttons".

- **Deleted:** the GATOR baseline (32 / 4 / 2 for every encoder with the three tested values), its button, and the
  "Publication preset" button beside it; with them the reset route `POST /api/network-settings/{encoder}/reset`,
  which nothing else called.
- **Kept:** the publication preset of each encoder, which already takes the tested values where no publication gives
  one (`network_presets.TESTED`); the schema defaults, so a configuration without a network block means what it meant;
  editing per encoder, and Use saved defaults / Save as defaults when a configuration differs.
- **The way back to a published number is typing it.** When all of an encoder's numbers equal its preset, the saved
  copy is forgotten and "In use: publication preset" returns; every number is listed under "Where the ... values come
  from". No new button: the user asked for fewer.
- **An encoder put on the baseline reads as its publication preset** (the file is not rewritten): the schema defaults
  saved before the tested values existed (05:00 UTC), as the user's Graph Transformer was, or the baseline saved on
  2026-10-05 with them. The same numbers saved after that day were typed by the operator and stay theirs.
- **What this means for Graph Transformer:** the two values that decide whether soft actor-critic learns stay (starting
  temperature 0.01, 8 updates per evaluation). Discount 0.9 instead of 0, 48 / 4 / 4, batch 32, replay 50 and episode
  30 were not measured on GATOR circuits; in the study batch 32 cost four times as much per update as 8, for the same
  result.

Record 7.191.

## The starting preset: published network size, every training number of the runs that learned (2026-10-05)

The user, the same afternoon: "can you transfer all the learned settings to the current preset", then "What I meant is
merge the publication preset and overwrite those settings with the previous learned settings, keep this as the
starting preset with no multiple choices between gator baseline and publication preset". Asked which numbers count as
learned, they chose "All training numbers": network shape from the papers, every training number from the runs that
learned (and, asked the same in another session, "take 10000 and 4 as well").

- **Taken from the runs that learned, for every encoder:** starting temperature 0.01, 8 updates per evaluation and
  discount 0 - compared and chosen in record 7.183 - and batch 8, learning rate 3e-4, warm-up 8, replay 10,000 and
  episode length 4, the values those runs were made with (`network_presets.LEARNED`).
- **Said as what it is.** Only the first three were compared and chosen. Learning rate 1e-3 did better in both runs
  that tried it, but never with 8 updates; batch 32 learned a little earlier with 4 updates at four times the cost per
  update; warm-up 64 brought no gain; replay and episode length were not varied. Each field's note says which.
- **Kept from the papers:** the network sizes as hidden / heads / layers (Graph Transformer 48 / 4 / 4, RGCN
  32 / 4 / 4, GATv2 192 / 3 / 4). The runs that learned used 32 / 4 / 2, so these sizes are untested here. Target smoothing (0.005) and
  the other four numbers were already the runs' values everywhere.
- **The published numbers stay visible:** a replaced field names its published value in its note and keeps it under
  `published`; the pinned test still checks them against the sources.
- **One name for it.** The page says "starting preset" (the user's word) where it said "publication preset"; the API's
  origin is still `publication`, so nothing that reads it changes.
- **Not measured as a whole.** The three encoders now differ from the measured setting only in network size; nobody
  has run a published size with these training numbers on a GATOR circuit.

Record 7.192.

## Calibration with the baseline run: proposed from random designs, applied by a press (2026-10-05)

The user asked whether the settings could be tuned in initial runs ("not on the fly during the run but have an
calibration setting during initail runs"), then, of all the settings ("not only the alpha but all the settings in RL
network and reward settings"), and settled where it belongs: "shouldnt each task run the baseline run? can you add the
calibration functionality to that".

- **Two settings are calibrated, because two depend on the task and can be read from random designs.** The Scale of a
  Specs row (how far outside its limit counts as a miss of 1) and the Initial alpha (the starting temperature). A free
  study on the ngspice circuit `ota5` (66 runs of 1,000 evaluations, 3 seeds per setting) looked at the others: network
  size (16 / 2 / 1, 32 / 4 / 2, 48 / 4 / 4) and encoder (Graph Transformer, RGCN, GATv2) ended at the same share of
  passing designs (93 to 95 %); episode length 4 and 8 the same, 1 worse; memory 50 with episode 30 worse. Those stay
  preset values. Learning rate 1e-3 was better than the preset's 3e-4 in all three seeds (learned at design 139 to 179
  against 251 to 294): one value for every task, so a preset and not a calibration - the user took it into the
  starting presets the same day (record 7.199).
- **The Scale is the median miss among the random designs that miss the row.** A typical failing design then scores
  0.5 on every row under the compressed shape, whatever the row's unit or the size of its limit. Tested: same learning
  speed, more passing designs in the last third of a run - 93 % to 98 % without bonuses (two rounds of three seeds),
  97.0 % to 99.1 % with the page's tested reward.
- **It has a price, and the user is told.** With the tested reward the passing designs drew about 7 % more power
  (median 80 uW against 75 uW in the last third; the lowest 64 to 68 against 61 to 64): a miss costs more with the
  smaller scales, so the search keeps more distance from the limits. More passing designs, a little less of the
  objective.
- **The Initial alpha is 0.1 x the standard deviation of the reward among the random designs,** with the proposed
  scales. 0.1 is what the tested 0.01 was on the circuit it was tested on (reward spread 0.09). Tested where it should
  matter: with scales ten times too large, 0.01 ended at 64 % passing and the calibrated 0.0025 at 91 %; a hundred
  times too large, 1 % and 20 %. It repairs a flat reward only in part - the Scale is the first setting, the
  temperature the second. With calibrated scales the spread is about the same on every task by construction, and the
  proposal lands near 0.01: on `ota5` 0.014, which made no difference (98.6 % against 99.1 %).
- **The objective row gets no proposal - a judgment.** Its Scale also measures the objective bonus, so a proposal from
  the misses would change what the bonus means. Measured, it made no difference whether that row was calibrated too
  (150 uW limit, Scale 80 uW): 99.3 % passing and 81 uW with it, 99.1 % and 80 uW without.
- **Nothing for the capped shape.** The median puts a typical miss at 1, which is the cap: half of the failing designs
  would count the same. The page's tested reward is compressed.
- **Guard rails that are judgment, not measurement:** at least 8 designs (and one in eight) must miss a row; a Scale
  stays within 0.01 to 10 times the size of the limit (tested proposals were 0.03 to 0.7 times); the Initial alpha
  within 0.0001 to 0.05 (validation warns above 0.05); two digits. 64 designs because the proposals of 64 agreed with
  those of 4,153 and those of 32 or 16 often had too few misses to propose at all.
- **Proposed, never applied by the run.** The run writes `calibration.json`; the page applies on a press, as one Undo
  step, and a saved task still needs Save task. A run that changed a task's Specs by itself would have changed what
  every later run of that task means.
- **A tick, not a second button, and not a renamed one** (record 7.197; REPLACED by record 7.202). It is the same run,
  longer; "Single baseline simulation" still named what the baseline is, and the tick said what is added. On by default
  because the user wants every task's baseline run to calibrate; the question before a real run names the number of
  simulations.
- **A prompt when the run ends, still the user's press** (record 7.204, user: "after calibration is there a prompt for
  applying those calibrated results? or is it automatic?", then "build the prompt when the run finishes"). The proposals
  sat only in Run status and could be missed. Of the two ways offered the user took the prompt: a line under the header
  with Apply calibration and Not now. Applying by itself was advised against - the page would hold Specs the saved task
  does not, and block every start until Save task, without anyone having asked for the change. The line and the Run
  status button share one piece of code, so they cannot come to differ; the answer is kept per run in the browser.
- **One button, "Baseline simulation", always calibrating** (record 7.202, user: "can we merge single baseline simulation
  and calibration to baseline simulation"). Nothing was lost with the tick: a starting design that cannot be measured
  ends the run after one simulation, and the baseline alone is Abort once the random designs begin (a stopped run still
  gives the task its reference). The user's second idea, that **Check now** also simulate the starting design once, was
  advised against and not taken (their choice): Check now is the free check Start runs by itself, so every press would
  have cost a simulation and a budget question; it is shown only for tasks saved from a Virtuoso cell, so ngspice and
  MOCK tasks would have had no baseline; and a simulation is a run (folder, Pause/Abort, Run status), a check an answer
  in place.
- **The baseline comes first and alone.** No other lane starts before it is committed, and an invalid one ends the
  run: with the calibration's higher failure limit (random designs may fail to be measured many times in a row) a
  starting design that cannot be simulated would otherwise have used the whole budget on resets.
- **The same designs as a warm-up.** The random designs are recorded as phase `warmup`, source `random_warmup`: no new
  phase name, the table schema is unchanged.
- **Measured on Spectre afterwards, and it did not help there** (record 7.211, user: "Spectre test of calibration"):
  `real:mscr_ota7t`, the Graph Transformer starting preset, one lane, 800 launches, the plain reward without bonuses,
  two seeds per arm. With the four proposed scales and Initial alpha 0.011 the first passing design came at 455 and 177
  against 202 and 146 with the empty boxes; the last third passed 93.5 % against 97.0 %; the passing designs' bias
  current was 682 against 705 uA, inside the seeds' own spread (619 to 746). So the ngspice gain (93 to 98 %) did not
  carry over to this task: the proposals stay proposals - shown, explained, applied only by a press - and nothing
  applies them by default. The seed spread is large (one calibrated seed learned 250 designs late); two seeds on one
  task is no proof that calibration hurts.
- **Not measured:** what the proposals do on Spectre circuits other than `mscr_ota7t`; with the page's tested reward
  (bonuses) on Spectre; the guard rails' numbers.

Record 7.197. Evidence: `artifacts/local/reviews/calibration-study-2026-10-05/README.md`.

## What a Scale does to the margin bonus; the calibration's window rule; Apply and save (2026-10-05, record 7.217)

The user asked "check the current reward design, is there anything to improve?", "together with the calibration
flow", and to the six points that came of it: "build the items". Three are built as offered, one is built narrower,
and two are not built; the free test runs that decided this are in
`artifacts/local/reviews/reward-review-2026-10-05/README.md` (ngspice, the page's starting reward, today's presets).

- **What the recorded runs showed.** After learning, a design that still fails misses one row by a hair: on Spectre
  (`mscr_ota7t`, three encoders) 3.9 to 14.2 % of the late designs fail, by 1 to 7 % of a limit; on ngspice 7.3 %.
- **The margin bonus is paid on the row with the least room measured in its Scale.** It is the margin weight times
  the compressed smallest room / Scale over the hard rows. So a Scale decides, above all, WHICH row the bonus
  protects. With every Scale the size of its limit that was the gain row for 61 % of the passing designs of the test
  circuit (6 dB of room on a 52 dB limit reads as 12 %) and the frequency row - the one that fails - for 13 %
  (23 MHz on 100 MHz reads as 23 %). Across nine settings the share of passing designs followed the share of them
  whose bonus sat on the failing row: 94 to 96 % passing with that share at 0 to 23 %, 98.5 to 98.8 % with it at 39
  to 87 %.
- **Making the failing row's own Scale smaller did nothing.** The frequency row at 10 % of its limit, everything else
  as it was: 94.3 % against 94.4 %. The miss cost ten times more, and the bonus left the row altogether.
- **A window with a wide Scale takes the bonus from every other row.** A design inside a window has at most half its
  width of room, so with the size of the limit as its Scale a window is nearly always the row with the least: 82 % of
  the passing designs on the test circuit once its dB row held the page's 6, and 99 % on a two-stage OTA whose 40 mV
  output window had the Scale 0.92 V. With half the window instead: 95.7 % to 98.7 % passing in the last third on the
  first circuit (every seed above every seed without), 91.7 % to 96.0 % on the second (six seeds each; inside the
  spread between its seeds, 83 to 98 %). The price is the one calibration has: the typical passing design drew about
  8 % more power (84 against 78 uW), the best design of a run 62 against 60 uW.
- **Hence the calibration's rule for a window, and only where the designs say it is safe.** A window that at least half
  of the random designs are inside is proposed at most half its width: there the Scale decides nothing about finding
  the window. A window most random designs miss keeps the typical miss, with the cost to the margin bonus said in the
  table. On the ring oscillator's frequency row 63 of 64 random designs miss, typically by 30 half-widths: half the
  window as its Scale would make nearly all of them count the same (0.94 to 0.98), which is what record 7.183 saw
  when it re-scored recorded designs. A test in between - a frequency window that 97 % of random designs miss, by 6.6
  half-widths at the median - found the window as fast with half its width (first passing design at 84 to 96 against
  70 to 90) and ended the same (62 to 69 % in all four settings): no harm there, no gain either, so nothing argues for
  cutting such a Scale.
- **The page's suggestion for a new row stays as record 7.183 left it** - offered as points 1 and 2, not built.
  *Half a window:* right for a window designs already hit, wrong in kind for one that must be found, and the page
  cannot tell them apart when a row is typed; a Baseline simulation can, so the rule is there. *10 degrees on a phase
  row:* no change where the phase margin is far from its limit (95.4 % against 95.7 %); where it binds, 94.8 % against
  91.7 % alone and no change beside the window rule (95.7 % against 96.0 %) - there it moved the failures from the
  frequency row to the phase row (33 and 65 against 68 and 25): the smaller Scale sent the bonus away from the phase
  row. On Spectre the calibrated Scales, with 9.6 degrees on that row, did not help `mscr_ota7t` (record 7.211).
- **A fixed bonus for passing was tested and is not built.** 96.3 % against 94.4 %, inside the spread between seeds,
  with the same row failing; it would have needed a change of the optimizer package.
- **The Initial alpha is proposed only when it differs from the value the run had by a factor of 2 or more.** 0.011
  to 0.014 against 0.01 made no measurable difference; a factor of 4 did (the calibration entry above). A closer
  proposal only made the page differ from the saved default. A judgment between those two measurements.
- **A result of another rule is worked out again when it is read, and the run's file is not rewritten.** The designs
  are simulated and paid for; a rule is arithmetic. The answer names both rules. Seven Baseline simulations of this
  day are such runs.
- **Apply and save, for a task saved from a cell.** Apply alone left the page differing from its task and every start
  blocked until Save task - right by the rule that a task starts only with the rows it has saved, and read as a fault
  (the user: "whats the problem here"). One press now does both, by asking Save task itself to run: one way of
  saving, with its own progress, its questions and its refusals. Apply only stays, for looking before saving.
- **Not measured, and said so:** nothing here ran on Spectre, and the one Spectre test of calibrated Scales did not
  carry the ngspice gain over. The window rule changes what is proposed, never what is applied.
- **Seen in the seven real calibrations and left as it is:** where random designs miss a row by far more than its
  limit - a broken LDO's dropout, 9 V typical on a 0.22 V limit - the typical miss is LARGER than the Scale in use,
  and the proposal loosens the row (2.2 V after the tenfold limit). Nothing measured says whether that helps; it is a
  reason to read a proposal before applying it, and a candidate for the next change of the rule.

## Learning rate 1e-3 in the starting presets (2026-10-05)

The user, told what the calibration study had measured: "use learning rate 1e-3 in the starting preset".

- **Measured** (calibration study, `artifacts/local/reviews/calibration-study-2026-10-05`, ngspice `ota5`, Graph
  Transformer 32 / 4 / 2, 8 updates per evaluation, discount 0, 1,000 evaluations, seeds 0-2): learning rate 1e-3
  learned at evaluation 174, 139, 179 against 251, 262, 294 with 3e-4, and 98.1 % of the last third passed against
  93.1 %. The price: the passing designs' median power was about 5 % higher (105-110 uW against 101-103 uW). Earlier,
  with one update per evaluation and with 4 updates at batch 32, 1e-3 had also done better (record 7.183's study).
- **Decided:** every starting preset takes 1e-3 (`network_presets.LEARNED`). It joins starting temperature, updates
  and discount as a value compared and chosen (`COMPARED`, basis `gator_tested`). For Graph Transformer and GATv2 the
  published value is 1e-3 already, so their field keeps the citation and adds the measurement; RGCN's published 3e-4 is
  replaced and kept in the note.
- **Not changed:** the schema default (3e-4), so a configuration without an Advanced block means what it meant; the
  recognition of an encoder put on the deleted GATOR baseline (it compares with the old baseline's own values).
- **Then measured as a whole** (`artifacts/local/reviews/starting-presets-2026-10-05`, same circuit, budget and seeds):
  every starting preset learns with 1e-3 - Graph Transformer 48 / 4 / 4 at 187, 219, 164 (98.5 % passing in the last
  third), RGCN 32 / 4 / 4 at 215, 139, 183 (99.2 %), GATv2 192 / 3 / 4 at 209, 212, 300 (96.7 %). So the published
  network sizes are kept: they learn as early as 32 / 4 / 2, at 25 to 40 % more time per run on this small circuit.
- **And on Spectre** (the user's approval "Yes, up to 800 designs"; `real:mscr_ota7t`, one lane, seed 0, the morning
  run's Specs, parameters and reward): the Graph Transformer starting preset passed 469 of 760 designs, the first at
  design 202, against 36 and 591 for the morning run of record 7.183 (32 / 4 / 2, 3e-4, discount 0.99). The runs differ
  in three settings at once, so this confirms the preset as a whole, not the learning rate alone.

Record 7.199.

## SAC is the only search method; the Agent tab opens Claude Code or Codex (2026-10-06, record 7.226)

The user: "rewrite the whole agent tab to minimal. Have two buttons to open claude code cli or codex cli in local shell
targeting the current workbench working directory with the permission of a usual agent launch (depend on personal
setting.) It shares the claude.ai or codex account history. For the LLM aided opt part, delete the search method box and
comments on the frontend. SAC is the only default and other methods should be launched through agent tab opened agent cli
user description (e.g. help the design when opt stuck). With deletion of the search method box, optimize related code on
the optimizer side. The button what is missing can be kept with a window showing what should be done."

- **Decided:** SAC is the only search method. The Search method box and its LLM methods (record 7.116) go, with the AI
  call and cost ceilings, the run's AI thread and hints, the header's "LLM n / m" and the engine's search session. Help
  from a language model during an optimization is asked of Claude Code or Codex, opened from the Agent tab.
- **Optimizer source digest `4aebbfab...` -> `aafdd71d...`**, one step, the user's answer "Yes, delete it" to whether the
  package's LLM search code goes too: `search/` (proposers, schedule, the LLM proposer) and `ActionMapper.encode` (its
  inverse mapping, used by nothing else). No other package line changed. No saved run pins `4aebbfab...`: every save
  point under `outputs/` is `f83342bc...` or older, so what resumes today still resumes, and fine_tune and frozen load
  as before. That digest is the step alone on HEAD; landed in a working tree that also holds record 7.228's uncommitted
  encoders (another session, same morning), the tree hashes `0b0808bc...` until each step is committed on its own.
- **The comparison driver of the parked SKY130 benchmark** (`examples/benchmark_llm_sizing.py`, `llm_sizing_evidence.py`,
  and the engine's `seed_proposer` / `evaluation_observer` hooks it used) is deleted (the user: "Delete the driver"). The
  AnalogGym import, its 17 tasks and the calibration stay parked and untouched.
- **What stays:** a run made with an LLM method stays readable - its tables keep their declared columns (`llm_calls`,
  `llm_call_id`, the llm_* phases), so the data dictionary is unchanged - and is never continued as SAC (code
  `search_method_removed`); its RL model, where it has one, can start a new fine_tune run. A configuration that carries
  `run.search` loads without it, with both hashes unchanged for SAC (the block was hashed as absent at its default).
- **Proven unchanged:** the same seeded MOCK runs (scratch with seeds 11 and 23, a resume, frozen and fine_tune from the
  first) under the old and the new code record identical values in every table (evaluations, parameters, metrics,
  learner updates, transitions, simulator jobs); only timestamps, random ids, temporary paths and the state references
  derived from the run id differ. `status.json` loses its `search` key (null for SAC) and `run_summary.json` its
  `search` and `agent_usage` keys.
- **The Agent tab** keeps two buttons that open the CLI in a terminal window of its own, in the repository, started as
  the user starts it (no permission option, model or prompt from the workbench; the user's account and history; Codex
  with the Codex app's own home), and "What's missing?" in a window of its own. Everything of the tab's own agent goes
  (records 7.6-7.186): conversation, providers and model lists, proposals, reviews, the Virtuoso setup and tools.

## Fine-tuning a trained model on a new starting point: no transfer-advantage claim, a measured head start (2026-10-06, record 7.229)

- **What was run:** six MScR circuits (ota5t, ota7t_w, ring3, vco_lin_c, ldo1_rgcn, ldo2_rgcn), each with a model trained
  from scratch on its original starting design (the A runs of records 7.199, 7.216 and the ota7t width task) and a new
  task `real:mscr_<name>_b` started from a random design of record (record 7.227); on each B task one run that loads the A
  model (Mode fine_tune) and one from random weights, seed 1, 800 launches, the A run's settings. Twelve runs, 9,600
  Spectre launches, all completed; every save point under optimizer source `4aebbfab` (the runs import a frozen copy of
  commit 5560c01), so they resume only under that source and load for fine-tune and frozen under the current one.
- **Criteria of record, revised before the verdict** (the user rejected "first passing design" as the measure: a single
  chance event, the first 8 designs of every run being random warm-ups): passing share of designs 9-108, cumulative passes
  by 100 / 200 / 400, the "50 % by" point, last-third share; C1 = 30 points of early passing share, C2 = last third within 5
  points, C3 = the LDOs pass at the relaxed HF PSRR target (-3 / -2.3 dB; -5 dB was never reached in 1,500 designs).
- **What the data says:** the loaded model is ahead in its first 100 own proposals on all six circuits (90 / 93 / 89 %
  against 11 / 1 / 5 % on ota5t / ota7t_w / vco_lin_c; 16 % against 2 % on ring3; 27 % and 4 % against 0 % on the LDOs) and
  ends as well or better on all six. On both LDOs only the loaded model passes at the relaxed target (89 and 58 designs).
  The fixed rule's absolute 30-point bar is met on three of six; the rule says "no transfer", the bar is what fails. One
  seed per arm. On ldo1_rgcn the loaded model loses part of the transfer while training on (27 % early, 7 % at the end;
  the critics were trained at the old target).
- **Decision:** reported as measured; no claim beyond these circuits. Offered, not ordered: frozen zero-shot runs (300
  launches), a second seed on ring3 and ldo1_rgcn, fine-tune with `reset_critic` on ldo1_rgcn.


## Task creation owns the baseline; Calibration samples only random designs (2026-10-07)

User request: “when a task is created, run a hardcoded baseline on itself. Change the Baseline button to Calibration
and the button only run the calibration steps”. Implemented in workbench code only (record 7.248).

- New Virtuoso/Save as and ngspice tasks automatically launch their own saved starting design with a fixed nominal
  one-evaluation/one-launch budget, one lane, seed 0, zero retries, no checkpoints or learning. Training controls do
  not set this recipe. A known connection failure blocks it without discarding the saved task; unknown probe results
  permit the bounded attempt. Its status persists, and missing/failed baselines offer a fixed-budget retry.
- Calibration now makes 64 random evaluations and no initial/reset simulations, at any lane count. No replay or
  learner updates. Scale/Initial alpha proposals and explicit application retain their previous rules.
- In-place Virtuoso updates that invalidate a baseline trigger its replacement; specs-only saves preserve it.
  Existing combined archives and the historical script API retain their semantics. Ordinary training is unchanged.
- A spec-less ngspice import checks only measurement presence for its baseline, without storing performance targets
  into the task. The actual deck and measurement receipts stay in the run.

## A circuit built for the purpose is the held-out test; the rank rule needs a phase-margin floor; the recipe sets the late phase, the weights the head start (2026-10-07, record 7.262)

- **What was run:** the general model's six C-task arms redone with the scratch recipe (G2), and two held-out circuits
  built for the purpose in library MScR: a folded-cascode OTA of our own design (`real:mscr_otafc`) and the single-ended
  port of the Analog Design Bench telescopic-cascode task (`real:mscr_otatc`, Yilin Xu, CC BY-NC 4.0 task content kept
  outside the repository), each with a required 64-design baseline, goals from the baseline-only rule, a frozen probe,
  scratch and the general model with the scratch recipe. `docs/plan-general-network.md` section 23.
- **Decisions.** (1) The head start belongs to the weights, the late phase to the recipe: G2 gives the same early shares as
  the anti-drift arms on every circuit, while the anti-drift recipe ends higher on ring3 and ldo1; C1 stays at three of
  six under either recipe. (2) The rank rule's phase-margin limit is replaced by the 60 deg floor for every held-out
  circuit: at rank 30 it asked the folded cascode for PM >= 90.24 deg, which no design of 800 met jointly with the other
  rows (both arms 0 / 800; kept on record as the first goal set). (3) Under the revised goals the start designs pass, so
  the resets are counted in the recorded totals and the policy-only view is reported beside them. (4) The telescopic
  cascode meets C1, C2 and C4 (73 % against 8 % early; 100 % against 89 % late) and is the one "transfers to an unseen
  amplifier" result of the study; the folded cascode meets C2 and C4 only (+7 points early), with the caveat that LDO2's
  pooled error amplifier is itself a folded cascode. The typed-graph audit (no whole-graph isomorphism, no pooled core
  embedded) goes with both results. (5) OTA8m's cells are renamed `mscr_ota7t_rz` / `tb_ota7t_rz` and its task is deleted
  (backup kept): it was the pooled OTA7t with a nulling resistor, not a held-out circuit.
