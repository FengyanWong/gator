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
