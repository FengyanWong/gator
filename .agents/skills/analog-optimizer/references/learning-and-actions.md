# 可切换编码器、SAC 与动作契约

2026-09-26 reward-v2 更新优先于本文的旧 nominal-only/编码器说明：用户授权按
`docs/plan-reward-v2-real-flow.md` 修改 optimizer；当前编码器是 GT/RGCN/GATv2/GraphGPS/参数组交叉注意力（后两者 2026-10-06 加入，记录 7.228）。
v2 evaluator、21N+11 输入、可选 nominal OP、完整 condition plan、replay 和 checkpoint
契约已接入并通过 OTA7 有界真实 A/B/C 验收：73 次 Spectre（A21、B44 含一次记录失败、C8），
总上限 77，B44 是用户另行明确批准。用户确认 unknown license 后按正常许可证流程执行，
没有绕过许可。B 产生 8 条 transition、7 次 SAC 更新；GT/RGCN/GATv2 各 OP 开/关的
6 项更新与精确下一次更新恢复使用 B 的真实 replay，不是六组新 on-policy 实验。
没有发现 robust-feasible 设计，也没有证明新 reward 更优。详见 `docs/reward-v2.md`；
不要自动迁移旧 checkpoint，不要用 MOCK 代替验收，也不要启动未授权的 999-call 研究。
2026-09-29 reward v2.1（摘要 `3f00832c...`，提交 `8cf53ae`）又加入 `after_nominal`、可选的缺失值失败、
失败后 episode 继续、objective 形状与 margin sides、独立 alpha 学习率；OTA7 物理门检用 10 次 Spectre（记录 7.108）。

本文给出项目设计与验证要求；当前实现状态见 [项目决策](project-decisions.md)，不能把接口验收当作迁移效果证据。
算法基础参考 [S5](sources.md)，图算子事实参考 [S4、S6](sources.md)；参数组化、mask、奖励和跨电路组合是本项目的设计选择。

## 1. 状态、规格和模型输入

建议状态：`s = (G_static, x_current, context, measurements, validity, status, budget_state)`。
规格 `g` 与状态分别传入；状态里的测量必须来自当前执行参数，而不是旧候选。
`budget_state` 仅在剩余步数影响任务终止/决策时需要，但一旦使用就要明确其 Markov/终止语义。

每条规格至少包含：

```text
metric_id / unit / comparator: min | max | range
lower_target / upper_target / positive_normalization_scale
weight / required / active
```

LDO/VCO/OpAmp 不共用无语义的“第一个指标”。规格身份、方向、数值和 mask 都应进入条件化表示。
可选实现是固定注册表+mask，或共享 spec-token encoder；具体根据现有代码与测试决定。
规格归一化不从完整测试集估计统计量。

先确保输入包含尺寸、目标与有效性信息，再增加 OP、偏置工作区或历史特征；每次增加有 ablation 和缺失值策略。

默认仍为 nominal-only；显式选择 reward-v2 `always` 的已验收 OTA7 可将完整五工况评价进入
训练 reward/replay。输入图和 OP 只来自 nominal，独立保留完整工况计划和结果；缺失必需
测量/基础设施失败不生成 reward/replay。后验证仍是独立记录，旧 `robust_score` 不替换
训练 reward。MC、skip-on-fail 和其他 profile 的训练 corners 未获本轮物理验收。
（2026-09-30 同步：reward v2.1 的 `after_nominal` 只在 nominal 通过全部 hard spec 后才跑 corners，
已在 OTA7 上做过物理门检；MC 与其他 profile 的训练 corners 仍未实现。）

## 2. Port-aware Graph Transformer

需要满足：

- 器件/net 类型、D/G/S/B 或等价 terminal 关系确实参与 attention 的 key/value/bias 或 typed relation 运算。
- 不使用由原始节点序号或实例名产生的语义 positional embedding。
- 有 residual、normalization、feed-forward 等稳定模块时，写出具体数据流并测试；不要只堆一个名称叫 Transformer 的类。
- 节点级表示保留到 actor/critic，不能只给一个固定 pooled vector 再接固定维度动作头。
- 跨图 attention 被禁止；padding mask 同时影响 attention、pooling 和 loss。

实现时明确标注 attention 范围：

```text
local_port_attention       # 沿真实连接的多头图注意力
structural_global_attention # 同一图内全局 attention，带已定义结构偏置
hybrid_attention            # 明确组合顺序的局部/全局方案
```

先采用哪种是待测试工程选择，不强行把“全局越多越先进”写成规则。
PyG `TransformerConv` 是基于邻域的 message-passing attention，并支持 edge features；只使用该层不能宣称实现了全局 Graphormer/DEGT。[S6](sources.md)

结构距离、扩散/谱特征等属于后续选项。增加前明确其图定义、缓存、复杂度、置换一致性以及是否确实提升独立测试结果。

### 编码器切换契约（M6 前已实现）

通过 `models.ModelConfig(encoder_type=...)` 和 `models.build_encoder()` 选择。共同接口为 `encoder(GraphBatch, actions=None) → (nodes[N,H], groups[G,H], context[B,H])`。actor/Q1/Q2 使用同一种配置但独立权重；保留共同特征、规格、动作注入、参数组 readout 和 SAC heads，仅替换节点处理。

当前（2026-09-30 同步，见 `src/analog_optimizer/models/encoders.py` 的 `ENCODER_TYPES`）只有前五行；其余已删除，名称被明确拒绝，旧权重不迁移：

| encoder_type | 当前节点处理与语义 |
|---|---|
| `graph_transformer`（默认） | `TransformerConv` 局部多头注意力，role/direction/ordinal 进入边特征 |
| `rgcn` | `RGCNConv`，terminal role × direction 为 relation，逐关系 mean；不额外编码 ordinal |
| `gatv2` | `GATv2Conv` 多头注意力（`share_weights=False`），端口边特征进入注意力；不增加自环，以外层 residual 保留自身表示 |
| `graph_gps` | GraphGPS 式（`PortGPSBlock`，2026-10-06，记录 7.228）：每层并行的端口局部注意力消息（同 GT）与电路内全局自注意力（`CircuitAttention`）；默认 `structural_encoding='rwse'` |
| `group_cross_attention` | GT 的局部层加参数组对节点的交叉注意力读出（`GroupAttentionReadout`，2026-10-06，记录 7.228）；可选 RWSE |
| ~~`port_gnn`~~ | 已于 2026-09-24 删除（原 M5 端口 MLP message 与 destination mean）；仅源码提交 bbdfe36 及之前可用 |
| ~~`mlp`~~ | 已于 2026-09-26 删除（原共享逐节点 MLP，忽略电路边/端口/ordinal）；最后含它的五编码器源码为提交 9bc488f |
| ~~`gcn`~~ | 已于 2026-09-26 删除（原普通 `GCNConv`，忽略 role/ordinal）；同上 |
| ~~`gat`~~ | GATv1（`GATConv`），2026-09-26 由 `gatv2` 取代；GATv1 权重不能载入 GATv2 |

- 原 MLP 对照（已删除）是适配可变节点数/动作数的无连接信息消融，不等同于固定拓扑展平 MLP。
- GT/GATv2 的 hidden_dim 须能被 heads 整除；RGCN 不使用 heads。同宽度/层数不保证参数量匹配。
- 不为新拓扑创建专用最终层。验证混合 batch 与单图输出一致、重命名/重排等变、动作归属及梯度、精确恢复；另验证端口感知图编码器（GT/RGCN/GATv2）对结构/端口变化敏感。
- 原 `models.graph_transformer` 导入保留，旧 `attention_mode='local_port_attention'` 仍映射到 GT；`port_message_passing`（port-GNN）已被拒绝。新调用使用 `encoder_type`。冲突配置拒绝，不能静默回退到 GT。
- checkpoint 保存编码器配置。不同架构不能直接互载；代码摘要/schema/依赖仍严格校验，不默认兼容改码前的 checkpoint。

具体命令与验收记录以项目 `docs/encoder-ablation.md` 为准；迁移模式与比较规则见 [实验与审查](evaluation.md)。

M1 已补齐独立于 RL 的同构张量导出、dense 节点 mask 与 batch 组索引校验，详见 [图契约](graph-contract.md)。通用原始 x 的列宽与模型 hidden_dim 不同，使用相应输入投影；不要修改 canonical 图去适应某个网络的最终层。任何带邻接缓存的算子（如已删除的 GCN）必须关闭跨调用缓存，避免混合拓扑误用上一张图。

训练输入现已使用 learner 内有界缓存：静态模板及完整历史观测的原始张量可以复用；batch、当前参数下的网络表示/attention 与梯度仍每次重新计算。缓存容量不改变学习契约，冷 checkpoint 恢复保持精确训练结果；不可把原始输入缓存扩展为 stale embedding 或跨任务 fitted statistics。实现与失效约定见 [图契约](graph-contract.md)，项目计时见 `docs/input-tensor-cache.md`。

## 3. 可变维度 Actor

独立参数组 `j` 聚合其所有成员的节点表示，结合参数种类、当前值、边界、域与目标条件，经过共享 head 输出 `mu_j, log_std_j`。
聚合对成员顺序不敏感；对所有可调参数组应用同一组共享权重或明确的类型条件化 head。
不要为每一个新拓扑重新分配一套最后输出层。

连续部分：

```text
u_j = mu_j + exp(log_std_j) * epsilon_j
z_j = tanh(u_j)                          # normalized proposal in (-1, 1)
```

使用数值稳定的 tanh log-Jacobian 修正，限制 `log_std` 到配置允许范围。
每个图的 `log_pi` 对有效独立参数组求和，组内绑定器件只算一次。
无有效动作的图禁止进入普通 SAC 训练；明确跳过/报错，而不是生成虚假的零维熵损失。
若 padding，先将无效项设置为安全有限值，再 masked reduce，避免 `0 * NaN` 仍产生 NaN。

## 4. 动作到物理参数

建议先实现一种动作语义并在配置中明确：

**绝对线性映射：**

```text
p = lower + (z + 1) / 2 * (upper - lower)
```

**正值参数的绝对对数映射：**

```text
p = exp(log(lower) + (z + 1) / 2 * (log(upper) - log(lower)))
```

对数映射要求 `0 < lower < upper`；零/负值不能偷加很小常数后混入同一种语义。
相对增量模式必须另行定义步长、clipping 和 state 依赖，并用独立测试验证，不与绝对模式混用。

之后执行明确的合法化：整数/网格/枚举投影、组绑定、边界与交叉约束校验。
保存 `proposal z`、`applied physical parameters`、投影原因、量化/裁剪统计及转换版本。
缓存和真实电路状态以实际执行参数为准。

### 连续 SAC 遇到离散参数

首个连续学习基线可固定离散参数；以后把整数用连续提议再量化，应标记为**连续代理+投影**。
投影会造成多个提议映射到同一物理候选，不能宣称是严格的混合动作 SAC。

建议先固定如下约定：critic 对 normalized proposal `z` 定义 Q；环境内部做确定性合法化。
replay 存储该 `z` 和实际参数，policy loss 也以同一 `z` 语义查询 critic。
这样不需要对 round 求导，但 critic 对投影引起的不连续仍只是函数近似，需测试。

若以后改成 applied-action critic，必须同时重新设计 policy gradient、概率/熵和量化语义；不可只替换 replay 中的一列。
环境不对 Spectre、网表编辑或外部仿真反向传播；policy 通过可微 critic 获得梯度。

## 5. Action-conditioned Twin Critics

每个 critic 接收 `s, g, z`，先将组动作绑定到参数 token 或其器件成员，再做 action-conditioned 节点处理和图级 pooling，输出每图一个 Q。图编码器传播邻域消息，动作归属与组 readout 保留。
动作的归属关系不可丢失；不能把任意顺序动作向量拼在 pooled graph 后，随后声称天然跨拓扑。
同一图改变动作应有可追踪的 critic 输入变化；梯度测试应能检测 actor→action→Q 通路。

默认 Q1/Q2 为独立参数集合；actor 与 critics 可复用结构代码，但不默认共享可训练张量。
若共享 encoder，必须写明每项 loss 更新哪些参数、梯度是否停止、target 对应哪个状态，避免重复 step。
跨电路共享同一模型，与同一次训练中 actor/critics 的 encoder 共享，是两种不同问题。

## 6. SAC 更新与 mask

采用无单独 V 网络的连续 SAC 变体作为起点：双 Q、target Q、重参数化 actor、熵项、replay 与 Polyak/soft update。[S5](sources.md)
自动温度可作为本项目默认实现选择，但需记录其配置和测试。

项目目标约定：

```text
y = r + gamma * bootstrap_mask * (
        min(Q1_target(s_next, g, z_next), Q2_target(s_next, g, z_next))
        - alpha * log_pi_next
    )
L_actor = mean(alpha * log_pi - min(Q1(s, g, z), Q2(s, g, z)))
```

target 分支不反传，next action 从当前 actor 重新采样；target Q 软更新需要包含对应 encoder。
温度更新对 actor 输出使用适当 detach，写清 loss 符号，测试其在高/低熵情况下调整方向。

每图有效动作维度可以不同：`target_entropy = -c * active_action_count` 可作为需测试的起点，`c` 是配置项。
熵、Q target、奖励尺度须在大图/小图混合 batch 上校验；不能用全局 padded 维度当所有电路的 entropy target。

区分 `terminated` 与 `truncated`。外部采样时间上限不自动等于 MDP 终止；明确何时 bootstrap。
若步数预算就是任务定义的一部分，把剩余预算纳入状态，并按该有限时域任务定义终止。
基础设施失效不应随意构造 next state 和 reward 放入 replay。

单 learner 的 update-to-data ratio 以新增有效 transition 数计算，而不是每个并行 worker 各跑一套不受控更新。

## 7. Reward 与指标有效性

优先实现一个纯函数 evaluator，与 simulator 和训练代码解耦。
先校验单位、方向和指标是否有效；正比例归一化尺度 `s_i > 0` 来自配置或训练统计，不直接除以可能为零/负的目标。

建议以非负 violation 起步：

```text
min constraint:   v_i = max(0, (target_i - measured_i) / s_i)
max constraint:   v_i = max(0, (measured_i - target_i) / s_i)
range constraint: v_i = max(0, (lower_i - measured_i) / s_i,
                              (measured_i - upper_i) / s_i)
V = sum(active_i * weight_i * v_i) / sum(active_i * weight_i)
base_reward = -V
```

公式只适用于已通过有效性检查的必需指标；没有有效必需指标时不能产生成功。
成功要求所有必需指标有效且各自满足阈值/预定义容差，而不是平均 violation 看起来较小。

若加入达标奖励、功耗等次要目标，明确幅度、是否约束优先及 stop 条件，防止牺牲必需约束刷分。
不可把未振荡的 VCO 当作“零功耗最佳”；VCO 频率前需验证振荡、幅度、稳态窗口。
OpAmp 的相位裕量需要有效的交越/loop 定义；LDO 的 dropout、稳定性、负载条件要有独立测量契约。
每个具体测量公式必须来自本项目测试台/测量规范和 fixture，不在模型里凭名字猜。

历史讨论提过 potential-based reward；首版不强制。若沿用，明确 base reward、Phi、gamma 和终止边界，并测试真正的 `gamma * Phi(s_next) - Phi(s)`，不要把任意差分奖励都叫 potential-based。

## 8. 保存经验与恢复

完整训练恢复至少记录：

```text
encoder / actor / Q1 / Q2 / target Q1 / target Q2
optimizers / alpha or log_alpha / temperature optimizer
feature/spec normalizers / type vocabularies / graph & action schema
config / code revision / dependency versions / PDK-map identity
RNG states / sampler states / replay data or replay manifest
training counters / topology split / failure and simulation budgets
```

新拓扑不能靠改输出层伪装成同一个可迁移 policy。
恢复时校验 schema/词表/动作转换版本；不匹配需迁移或拒绝，不能无提示载入。
仅推理可不带 critics/replay，但要保留 actor encoder、规格/参数归一化和动作语义。

## 9. Surrogate 的后续边界

默认关闭，也没有“encoder → surrogate → SAC”的必需串联。
将来若研究 surrogate，先明确用途：预测指标、筛选候选、辅助表征或模型式 rollout；每一种都需要不同的验证。
训练/校准只用允许的数据，记录不确定性与 OOD；真实测量和预测结果分表标记。
最终设计必须通过真实 Spectre 验证；同时报告 surrogate 构建成本与带来的真实调用节省。
