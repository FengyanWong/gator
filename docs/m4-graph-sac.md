# M4：图模型、SAC 与小预算真实闭环

2026-09-19，用户要求“m4 继续下一步”。已实现模型与训练，并在离线验收后接回原 GPDK045 OTA。训练保持 nominal-only；本轮不启用 PVT/MC 调度、surrogate 或多 worker。

[完整机器可读验收汇总](../artifacts/local/m4-acceptance-summary.json)：231 项测试通过、5 次真实 Spectre、基线恢复、checkpoint 精确更新恢复，以及中断续跑与连续运行的一致性均通过。

## 实现与动作语义

`models/inputs.py` 将既有 `Observation → CircuitGraph → HeteroData` 转成 packed batch：图节点与参数组只包含真实项，跨图边被拒绝。每张图的 active group 索引决定动作数量；外部 padded 动作通过 `pack_actions()` 先索引有效位置，NaN/Inf padding 不参与任何运算。固定组没有 stochastic action，但其尺寸仍属于图状态。

`models/graph_transformer.py` 实现 `local_port_attention`。器件类别与当前尺寸/mask、net 角色、规格条件进入节点；端口角色、方向及 ordinal 进入 edge features。每个 block 使用 pre-LayerNorm、多头 dot-product attention、residual 和 feed-forward；无 dropout、无节点序号或实例名 embedding。`TransformerConv` 的 edge features 进入 key/value，属于邻域注意力，参见 [PyG 原始文档](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.TransformerConv.html)。本实现不是全局 Graphormer 或 DEGT 复现。

每个参数组聚合绑定成员的节点表示、参数种类与比例，结合当前值、边界、步长、linear/log、continuous/integer 以及目标条件。共享 actor head 输出 `mu/log_std`，使用重参数化 `tanh` 采样。稳定的 log-Jacobian 修正确保饱和动作仍产生有限 log-probability；每图只累计独立 mutable 参数组。

两个 critic 分别将动作与组 token 绑定，注入对应器件后执行图 attention，再聚合节点和动作组得到图级 Q。actor、Q1、Q2、两个 target 各有独立 encoder 参数。动作改变、绑定改变和端口变化均有数值/梯度测试。

`training/sac.py` 实现双 Q、target Q、自动温度和软更新；算法基础参见 [SAC 原论文](https://arxiv.org/abs/1812.05905)。可变动作组与端口图为本项目的实现选择：

```text
Q 的动作语义：normalized proposal z，而非投影后的物理值
y = r + gamma * bootstrap * (min(Q1_target, Q2_target) - alpha * log_pi_next)
actor_loss = mean(alpha * log_pi - min(Q1, Q2))
target_entropy(graph) = -active_action_count(graph)
alpha_loss = -mean(log_alpha * detach(log_pi + target_entropy))
target = (1 - tau) * target + tau * critic
```

目标分支不求导，actor 更新时 critic 权重冻结但保留 action→Q 梯度。真实 5 nm 网格沿用 M3 确定性合法化；proposal 与 executed parameters 同时保留，仍是连续代理加投影，不是严格的离散 SAC。

模型默认 64 hidden、4 heads、2 blocks；本次 demo 与真实 smoke 使用 32 hidden、4 heads、2 blocks，测试使用 16 hidden、2 heads、2 blocks。SAC 默认 `gamma=.99`、`tau=.005`、学习率 `3e-4`、初始 `alpha=.2`、梯度范数上限 10。这些参数尚未做调优或性能选择。

## 状态、规格和 replay

状态包含当前图尺寸、parameter present/valid/optimizable masks、测量与有效性、状态、剩余步数，以及 nominal 温度/电压。固定规格 registry 包含 metric ID、unit 和物理 reference；min/max/range、目标存在标记、target/scale/weight、required/active 均参与条件化。未知 metric/unit/schema 显式报错。未激活规格被屏蔽，缺失测量使用有限占位和独立 mask。

归一化用固定 reference 与 signed-log1p，不拟合样本统计量。支持的参数单位按当前 schema 明确限定为 w/l:m、m/nf:1、r:ohm、c:F、ind:H、dc:V；未注册的电流/其它参数语义需要显式扩展契约后才能训练。

`Transition.from_step` 要求 M3 完成的候选 journal，核验 nominal purpose、来源/工况、proposal、实际参数、指标、状态、奖励、job、终止标记及下一状态。`ReplayBuffer` 保存独立快照，real/synthetic 不可混用；PVT/MC、工况变更、错误尺寸、错误奖励、缺失必需测量、基础设施/测量故障都不能进入训练。明确归因的非收敛/无效设计可以进入终止 penalty。有限任务的剩余步数耗尽为 terminated，bootstrap=False；不将外部超时当作有奖励的设计失败。

`training/runner.py` 是单 worker collector。reset 消耗仿真调用但不入 replay；每新增一个有效 transition，在 replay 满足 batch 大小后做一次更新。先进行显式 random warmup，再使用当前 actor。输出保存 proposal 来源、候选日志、奖励/达标、重复候选以及推理/采样/更新耗时。

## 离线验收

**231 项离线测试通过，零失败、零跳过；其中 M4 新增 33 项。** 无 Cadence/SSH 的完整 pytest 验证：两种不同 graph/action 大小的混合 batch；单图与混图输出相同；节点、net、group、member 重排与重命名等价；端口影响 attention 并获得梯度；动作绑定影响 Q 且梯度回到 actor；NaN padding 不影响有效输出/梯度；有效组熵；饱和动作；目标/状态/尺寸变化；温度方向；target 软更新；有限时域和故障排除；journal 不一致；独立 replay 快照；完整 checkpoint 精确恢复。

运行环境：Python 3.10、Torch `2.14.0+cpu`、PyG `2.8.0.post1`、NumPy `2.2.6`；本轮仅验证 CPU，demo 固定 1 个 Torch 线程并启用 deterministic algorithms。

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q
/tmp/analog-optimizer-venv/bin/python examples/train_synthetic_sac.py
```

synthetic demo 使用 opamp 的 2 个动作组和 LDO 的 1 个动作组。`SyntheticSizingBackend` 计算执行参数的显式二次 toy score，既不求解电路，也不读取真实测量。两种结构各运行 6 个 episode、每个 4 步，总计 48 条 transition、12 次 reset、60 次 synthetic 调用和 41 次训练更新。

- [双拓扑 synthetic 完整报告](../artifacts/local/m4-synthetic/fc392f76da534962bfe97a40c524890c/report.json)
- [synthetic checkpoint](../artifacts/local/m4-synthetic/fc392f76da534962bfe97a40c524890c/checkpoint.pt)

另实际运行 `--resume`，新增两种结构各 1 个 episode：8 条经验、10 次 synthetic 调用，累计 56 条经验与 49 次更新。与从头连续运行每种结构各 7 个 episode 相比，续跑部分的每个 proposal、reward、success、loss 完全相同；最终 actor、critics、targets、alpha、三个优化器、Torch RNG 和 collector 状态逐项一致。

- [恢复采样报告](../artifacts/local/m4-synthetic/f3767a6a96424ea182dbb1559598c6e4/report.json)
- [不中断的对照运行](../artifacts/local/m4-synthetic-continuous/1f5e07e4bd7d4a6791be9b17dd6392be/report.json)

```bash
/tmp/analog-optimizer-venv/bin/python examples/train_synthetic_sac.py \
  --resume artifacts/local/m4-synthetic/fc392f76da534962bfe97a40c524890c/checkpoint.pt \
  --episodes 1
```

synthetic 与真实 demo 均在保存 checkpoint 后，用内存中的 learner 和恢复出的 learner 分别再做一次相同采样/更新，检查 losses、actor、critics、targets 和 alpha 完全一致；探针不修改保存的训练 checkpoint，也不增加仿真调用。demo 的训练调用次数不包含这两个恢复验证更新。

## 真实 nominal 小验收

复用已有 bridge 0.8.0 与专用 `GATOR_TESTS` OTA，TT/27°C/1.0 V，仅 M1/M2 匹配宽度 3.6–4.4 µm、5 nm 网格，保持 mirror/tail 固定。SAC 从随机初始化开始，没有把 toy 权重当作有效电路预训练。固定 seed `20260919`；1 次 random warmup，随后 2 次 policy candidate，batch size 2，产生 3 条真实经验和 2 次 SAC 更新。

| 阶段 | 执行宽度 µm | 增益 dB | UGF MHz | 功耗 µW | 全部 smoke specs 达标 |
| --- | ---: | ---: | ---: | ---: | --- |
| 原始基线 | 4.000 | 25.000934 | 3.527748 | 1.956295 | 否 |
| Random warmup | 4.105 | 25.009131 | 3.540390 | 1.957693 | 否 |
| Policy candidate 1 | 3.685 | 24.974497 | 3.487607 | 1.951845 | 否 |
| Policy candidate 2 | 4.195 | 25.015937 | 3.550956 | 1.958859 | 是 |
| 恢复基线 | 4.000 | 25.000934 | 3.527748 | 1.956295 | 否 |

5 次真实 Spectre 全部完成，脚本计时 15.91 s；这只是一台机器上的小电路验收耗时。恢复后的网表 SHA-256 与初始基线一致、所有保存指标匹配，退出后再确认参数恢复。第三个候选满足现有 smoke specs，但仅有 2 次训练更新，不能归因于学习收敛，也不证明优于随机搜索。规格仍是已有基线附近的验收目标，不是独立 benchmark；PM 为原开环估计，功耗不含真实偏置发生器。

- [真实运行报告、候选与 checkpoint 路径](../artifacts/local/m4-real/879546dc1ec54801861b4c11b22462bc/report.json)
- [4 µm 恢复记录](../artifacts/local/m4-real/879546dc1ec54801861b4c11b22462bc/restoration.json)
- [保存的真实训练 checkpoint](../artifacts/local/m4-real/879546dc1ec54801861b4c11b22462bc/checkpoint.pt)
- [沙箱连接失败尝试](../artifacts/local/m4-real/9f829599b9124fee9c25cb2285491f17/report.json)：无法访问已有隧道，0 次仿真、未连接设计。获得外部连接授权后重跑成功；真实总成本仍是 5 次。

复现时使用已有 bridge/专用设计会话，保存并关闭冲突的 ADE 窗口。`--bridge-site-packages` 可把已有可信 bridge 环境加入模块搜索路径，无需重装或修改上游；若当前 Python 已安装经验证的 bridge，省略此参数。

```bash
/tmp/analog-optimizer-venv/bin/python -B examples/train_opamp_sac_smoke.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --reference-measurements artifacts/local/opamp-baseline/simulations/ff6dc7e7c3944d77a0ace70da4d63385/measurements.json \
  --output artifacts/local/m4-real \
  --bridge-site-packages /home/fyworkstation/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages
```

## 保存与恢复边界

checkpoint 包含 actor/Q1/Q2/target 网络、三个优化器、log_alpha、feature/spec vocab 和固定 normalizer、模型/SAC 配置、动作与终止语义、实验划分/设计与映射来源、代码摘要、Torch/PyG 版本、CPU/Python/NumPy RNG、replay 内容/位置/采样 RNG、更新与采样计数和 collector 状态。加载要求调用者传入一致的 experiment/config/schema，拒绝静默迁移。

只加载可信的本地 checkpoint：Torch 文件包含 Python dataclass/replay，加载使用 pickle。`source_digest` 覆盖 `src/analog_optimizer` 全部 Python 源文件，源码变化后需要显式审查迁移，不能直接加载旧训练状态。

synthetic CLI 的 `--resume CHECKPOINT` 在完整 episode 边界继续，使用新 UUID 日志目录，恢复模型、replay 和 collector RNG 后重新 reset 环境。真实 smoke 保存的 learner/replay 同样可恢复更新，但没有实现断线后接管半完成仿真或真实采样 CLI 自动续跑；必须先处理恢复记录，再从新环境的基线开始。

下一步是固定真实任务的规格集合、采样预算与种子，开展 nominal SAC 对随机搜索的有限预算比较，报告达标率、首次达标调用数、全部真实调用/失败和训练耗时。当前证据没有覆盖跨拓扑泛化或 PVT/MC 鲁棒性。

## 2026-10-06 记录 7.221：学习步提速，结果逐位不变

- `ReplayBuffer.update_learner(learner, n)`：与 `sample(n)` 用同一生成器、同样的条目与顺序，但把已入库的 transition 借给 `learner.update`（只读），不再深拷贝；真实 `mscr_ota7t` replay 每批 8 条的深拷贝约 28 ms。公共 `sample()` 仍深拷贝；测试在更新前后对整个 replay 做指纹比对。工作台引擎的两处学习调用改用它。
- gamma 恰为 0 时，`SACLearner.update` 不再构造下一状态 batch，也不运行下一状态 actor 和两个 target critic：目标就是奖励。下一状态 actor 本应抽取的噪声仍以同形状、dtype、device 抽取（`Normal.rsample` 即一次 `normal_()`；transition 契约保证下一状态的可调组数与当前状态相同），所以 torch 随机数状态与之后的所有动作逐位不变。任何非零 gamma（再小也一样）保持原计算。`SACLearner.zero_gamma_shortcut` 只供测试关闭以作对照；它从不改变配置的 gamma。代价：未用分支里偶然的非有限值检查随之消失；transition 校验、损失与梯度检查不变。
- 输入缓存键改为 schema 摘要 + 观测内容摘要；replay 借出的观测摘要每条只算一次。learner 默认缓存 8192 条（原 2048），另有 256 MiB 字节上限，见 `docs/input-tensor-cache.md`。
- 不变：SAC 算法、奖励、动作语义、checkpoint 格式与字段及其写入节奏。源码摘要改变：此前的 checkpoint 只能在其原源码下完整续跑（fine-tune/frozen 仍可加载，只有警告），见 `docs/decisions.md`。
