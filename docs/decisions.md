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
