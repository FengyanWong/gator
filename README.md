# Analog Optimizer

**M6 is closed at pilot scale (2026-09-20):** the cross-category pipeline was built, run on real circuits and independently audited, while the question of whether transfer or a graph transformer helps is not answered at this scale; see the closing entry in [project decisions](docs/decisions.md). In the pilot, the [three category holdouts](docs/m6-real-results.md) used exactly 2,811 Spectre calls and 1,566 SAC updates, with final circuit/baseline restoration passed. The independent audit verified all 2,811 saved candidate packages and 162 learner checkpoints with zero new simulator calls, and the final regression suite passed 544 tests. GT adaptation achieved 2/3 OTA, 3/3 LDO and 3/3 VCO successes; coordinate search achieved 3/3 in every class without pretraining. This short experiment on known circuits does not establish a GT advantage. The [frozen protocol](docs/m6-real-protocol.md), [VCO runtime qualification](docs/m6-vco-runtime.md) and earlier [synthetic benchmark](docs/m6-cross-category.md) remain separate evidence.

## Workbench (web UI, since 2026-09-20)

`src/gator_workbench/` (FastAPI backend) and `frontend/` (React/TypeScript) make the optimizer usable from a browser: circuits from registered tasks or read from Virtuoso, the Parameters / Probes / Specs editors, run control, data-only outputs, an optional agent that proposes configurations, and a check of a run's best designs at five PVT corners. Real simulations stay a user-authorized budget. What each feature does: [docs/workbench.md](docs/workbench.md); its development record: the index [docs/frontend_implementation_status.md](docs/frontend_implementation_status.md) and [docs/workbench-log/](docs/workbench-log/).

```bash
python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
PYTHONPATH=src python -m gator_workbench.cli serve               # http://127.0.0.1:8765/
cd frontend && npm run build                                     # the page the backend serves
OMP_NUM_THREADS=1 python -m pytest -q -n 12 --dist load          # every test, in about a minute
```

`constraints.txt` holds the exact torch / torch-geometric / numpy / networkx versions: a saved model only loads under the versions it was saved with.

已实现离线基础链路：`VirtuosoBackend` 抽象 → synthetic `MockBackend` 导出网表 → Spectre 子集解析器 → `CircuitGraph` → PyTorch Geometric `HeteroData`。包含 op-amp、LDO、VCO 三个小型 synthetic fixture。另外已在真实 Virtuoso 中创建 GPDK045 五管 OTA 和测试台，完成 Spectre DC/AC、负载扰动、原参数复跑以及真实网表到 PyG 的验收；见 [运放基线](docs/opamp-baseline.md)。

真实接口使用已有的 **Virtuoso Bridge**（发行包 `virtuoso-bridge`，import `virtuoso_bridge`）。已实现专用于当前 GPDK045 OTA 的 `VirtuosoBridgeBackend` 薄适配层，完成 M1/M2 宽度 4 → 4.4 → 4 µm 的真实回写、仿真和恢复；见 [后端验收](docs/opamp-backend.md)。本项目的 `VirtuosoBackend` 方法属于自有接口，底层继续调用上游连接、导出和 Spectre API；尚未实现通用 PDK 适配。

已进一步实现单 worker 的 **`CircuitSizingEnv.reset/step` → 参数合法化 → 真实仿真 → 规格评价/奖励 → 候选记录与恢复**。M3 完整验收实际运行 8 次 Spectre，覆盖宽度边界、3 个随机候选、重复候选和恢复基线。真实 CDF 的宽度取整已纳入 5 nm 动作网格。详见 [环境与随机候选验收](docs/opamp-environment.md)。

M3 已补充 typed PVT/Monte Carlo 工况接口、GPDK045 来源配置、nominal-only 环境约束及 top 3／corner 汇总纯函数。MC 执行仍明确不支持，后验证调度尚未实现。详见 [PVT／MC 接口说明](docs/pvt-mc-interfaces.md)。 (Since 2026-09-22 the workbench's Corner check simulates a run's best designs again at the five GPDK045 corners - see [docs/workbench.md](docs/workbench.md); Monte Carlo is still not supported.)

2026-09-19 用户继续授权 **M4**：已实现局部端口感知 Graph Transformer、参数组 actor、独立 action-conditioned twin critics、连续 proposal SAC、nominal-only replay 和完整训练 checkpoint。**231 项离线测试通过，零失败、零跳过。** 双拓扑 synthetic demo 支持同 batch 的 2 维／1 维动作及精确恢复；真实小验收新增 **5 次 Spectre、3 条经验、2 次 SAC 更新**，恢复后的基线网表与指标一致。实测候选之一达到当前 smoke specs；这不证明收敛或优化优势。实现、测试和复现命令见 [M4 验收记录](docs/m4-graph-sac.md)。

**M5 首轮**新增冻结 train/validation/test 划分、精确端口图同构防泄漏、独立任务微调与六方法对照：GT 从零／冻结／微调、随机搜索、坐标模式搜索、端口 GNN 微调。首轮验收 **246 项离线测试通过，零失败、零跳过**；三种子合成实验完成 534 次解析评价，覆盖同拓扑新规格和 2→3 维动作的新拓扑。真实规格试验完成 **97 次 Spectre**，基线参数、网表和指标已恢复一致；GT 微调 1/3、随机搜索 2/3、坐标搜索 3/3 达标，当前没有迁移优势证据。该首轮未覆盖真实新拓扑；完整结果、成本与限制见 [M5 验收记录](docs/m5-transfer.md)。

**M5 真实新拓扑补验已完成**：新增独立 GPDK045 七管 Miller 两级 OTA，真实动作维度 1→2；3 seeds × 6 methods 完成同拓扑规格及新拓扑对照。本轮 **585 次真实 Spectre、288 次 SAC 更新**，完整回归 **440 passed，0 failed，0 skipped**；24 个 checkpoint 审计及两个电路完整 CDF/网表/指标恢复均通过。新拓扑 GT 微调 1/3、随机 1/3、坐标搜索 3/3、port-GNN 微调 2/3 达标，仍没有 GT 迁移优势证据。详见 [M5 真实拓扑验收](docs/m5-real-topology.md)。

**M6 前编码器接口**已支持 `graph_transformer / mlp / rgcn / gat` 切换，并保留 M5 的 `port_gnn`。共用参数组 actor、动作条件化 critics 和 SAC；显式选择编码器后，每种都运行从零／冻结／微调三种模式，记录独立成本与参数量。完整离线回归 **296 项通过，零失败、零跳过**；四架构 synthetic smoke 已完成 116 次解析评价，没有新增真实仿真或迁移优势结论。接口、命令、兼容边界见 [编码器对照说明](docs/encoder-ablation.md)。

**M1 神经网络输入复核**进一步增加 `to_homogeneous_pyg()`：固定语义的 `x / edge_index / edge_type / edge_attr / edge_weight`、正确的参数组 batch 偏移，以及带 mask 的 dense 节点视图；训练层复用同一端口边转换。新增普通 `gcn` 对照，与 `rgcn` 分开。该次验收 **319 项离线测试通过，零失败、零跳过**，六编码器完成 168 次 synthetic 流程评价。原 parser/HeteroData 保持兼容，详见 [M1 通用输入契约](docs/m1-neural-inputs.md)。

**训练输入缓存**已默认启用：同一拓扑复用连接与端口，同一历史观测复用原始张量；更新尺寸/规格/测量时刷新输入，每次训练重新计算网络表示。354 项离线测试通过；本机合成 batch=32 的 GT 完整 SAC 更新实测约 112→62 ms，未新增真实仿真。容量、失效规则和计时边界见 [输入缓存说明](docs/input-tensor-cache.md)。

**并行 Spectre SAC**改为按实际候选调用 CDF 并导出原生网表：一个专用 Virtuoso 准备进程串行处理完整候选，各环境独立并行运行 Spectre，共享主进程 learner/replay。默认及最大并发均为 **4**；不再预计算或依赖 CDF 表。新版真实验收通过 **24 次 Spectre、18 条新经验、16 次 SAC 更新**，覆盖单 worker、默认四 worker 和 checkpoint 续跑；实际 Spectre 并发峰值为 2，原理图已恢复。参数语义与运行见 [并行训练说明](docs/parallel-spectre-sac.md)，证据与限制见 [真实验收](docs/native-cdf-real-verification.md)。

**轻量实验记录**可通过训练入口的 `--recording-root` 开启：单 writer SQLite 保存所有 evaluation、静态资产引用和完整动态 transition，独立于内存 replay；checkpoint 使用 replay 成员 ID，默认保留最近两份及一份 final policy。带容量门槛、提交确认后的附件/工作目录清理、只读查询和按需 Parquet+ZSTD 导出。数据库使用 WSL 本机 ext4 目录；配置与恢复边界见 [实验记录说明](docs/experiment-recording.md)。后续真实验收完成 16 次 Spectre，覆盖单 worker、2-worker 和 checkpoint 续跑；实际波形保留、远端清理、数据及恢复审计通过，完整回归 413 项通过。见 [真实记录验收](docs/recording-real-verification.md)。

日常查看：`python -m analog_optimizer.recording /path/to/records summary`；加 `--json` 可给自动控制脚本使用。已减少 replay 全量回读、重复静态登记与状态写入，检查清单见 [重复 I/O 审查](docs/recording-io-audit.md)；`examples/benchmark_recording_overhead.py` 可复测记录开销。

**运行可靠性与迁移入口**已补齐周期 checkpoint 续训、累计计数、初始化/异常清理和 worker 等待上限；记录模式的报告历史有界。迁移入口使用逐候选 CDF 与原生导出，可接入 SQLite 和独立 seed 并行，保持各任务 learner/replay 隔离。参数、恢复边界及离线验收见 [运行说明](docs/runtime-reliability.md)。

## 安装与运行

Python 3.10+。解析器、数据类和 MockBackend 只依赖标准库；PyG 为可选依赖。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# CPU 环境可先按 PyTorch 官方源安装，避免默认下载 CUDA 依赖：
python -m pip install -c constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -c constraints.txt -e '.[graph,test]'     # exact versions: saved models need them
python -m pytest -q
python examples/netlist_demo.py tests/fixtures/synthetic/opamp.scs --config configs/opamp.json
# 无 Cadence：两个 analytic toy 环境、一个 SAC learner、checkpoint 验收。
python examples/train_synthetic_sac.py
# M5：固定划分、3 seeds、6 methods，使用解析 toy 后端。
python examples/benchmark_transfer.py
# M6 前：四架构的最小迁移流程验收。
python examples/benchmark_transfer.py --encoders graph_transformer mlp rgcn gat --seeds 17 --pretrain-steps 2 --test-steps 2 --max-calls 120
# M6: validate the cross-category suite and its total budget, without evaluations.
python examples/benchmark_cross_category.py --dry-run
```

Demo 输出 devices、nets、带 terminal/ordinal/role 的连接、参数组、节点 features/masks、正反向边和参数组绑定 tensors。

```bash
# 经 synthetic Backend 导出再解析；只适用于自包含网表。
analog-graph-demo tests/fixtures/synthetic/opamp.scs --config configs/opamp.json --mock-export .demo-jobs
# 无 Torch/PyG 时仍可使用系统 Python 验证结构。
PYTHONPATH=src python3 -m analog_optimizer.demo tests/fixtures/synthetic/vco.scs --config configs/synthetic.json --no-pyg
```

本次验收使用 `/tmp/analog-optimizer-venv`，没有修改系统 Python。临时环境可能被系统清理；上面的安装步骤用于建立持久环境。实际版本和结果见 [验收记录](docs/verification.md)。未安装图依赖时，pytest 会明确 skip `test_pyg.py`；完整验收必须安装 graph extra 并确认 **零 skip**。

## 目录与接口

| 位置 | 用途 |
| --- | --- |
| `src/analog_optimizer/backends/` | Backend 抽象、synthetic mock、真实 bridge 适配器和 GPDK045 电路约束 |
| `src/analog_optimizer/netlist/` | tokenizer、白名单表达式、JSON 配置、层次解析 |
| `src/analog_optimizer/graph/` | 独立数据类、参数组校验、异构 PyG 与固定语义同构/dense 输入转换 |
| `configs/` | synthetic model/端口映射、net 角色、可调参数组; also the GPDK045 real-circuit configs. The M5/M6 audits pin these files by hash: do not edit, reformat or move them |
| `src/gator_workbench/`, `frontend/` | the workbench (web UI): backend and page; see [docs/workbench.md](docs/workbench.md) |
| `constraints.txt` | exact library versions that saved models need |
| `src/analog_optimizer/parameters/` | 按独立可调组映射 normalized proposal，执行边界/网格/整数合法化 |
| `src/analog_optimizer/measurements/specs.py` | 单位、有效性、min/max/range 规格和有限奖励 |
| `src/analog_optimizer/envs/` | 单 worker 环境、有限步数、失败处理、候选日志和恢复 |
| `src/analog_optimizer/evaluation/` | nominal top-k/corner 汇总纯函数，以及 M5 划分检查、定额迁移实验和成本汇总；不调度 PVT/MC |
| `src/analog_optimizer/models/` | 固定特征/规格注册表、packed batch、可切换 GT/MLP/GCN/RGCN/GAT/port-GNN 编码器、group actor/critic |
| `src/analog_optimizer/training/` | nominal replay、连续 SAC、串行/并行 collector、checkpoint 保存/恢复 |
| `src/analog_optimizer/recording/` | 单 writer SQLite、静态去重、动态状态、摘要、容量/附件清理、checkpoint、只读查询与导出 |
| `tests/fixtures/synthetic/` | 三个合成网表，使用同一个解析器 |
| `examples/netlist_demo.py` | 命令行 demo |

`MockBackend` 生成唯一 job 目录、网表摘要和 provenance。`run_simulation` **只返回调用者显式注入的测试指标/状态**，不执行电路求解，`origin=synthetic` 且 `candidate_evaluated=False`。缺失/非有限指标使用 `None` 和 validity mask；基础设施失败、非收敛和测量失败有不同状态。参数读写与 OP 提取会抛出 `UnsupportedCapability`；没有静默 mock fallback、重试或自动安装 bridge。

M4 新增的 `SyntheticSizingBackend` 是独立、显式的解析二次函数测试后端，能够执行参数映射并对 toy score 求值，`origin=synthetic`。它用于训练接口测试，不计算电路指标，也不会作为真实后端故障时的替代。

## 支持的 Spectre 子集

- 默认 Spectre native dialect；可显式声明 `simulator lang=spectre`。大小写保留。
- 空白、`//` 注释、行尾反斜杠续行。
- `instance (net ...) model parameter=value ...`；器件端口顺序完全来自配置中的 model 映射，不检查实例名前缀。
- 十进制、科学记数法，以及 `T G M K k m u n p f a` 后缀；`M=1e6`，`m=1e-3`。本子集拒绝 `meg`、`um` 等未声明后缀。
- `parameters`、前向参数引用、`+ - * / **`、括号及引号/花括号包裹表达式。AST 白名单求值，无 `eval()`；依赖环、未定义符号、函数调用、非有限值保留为 unresolved。长度、复杂度、幂指数有上限。
- `subckt name (ports)` 或 Virtuoso 原生导出的 `subckt name port1 port2` / `ends [name]`，默认参数放在内部 `parameters` 行；支持嵌套调用、调用时 override，拒绝递归、嵌套定义和未声明 override。显式配置的模型优先作为原子器件。
- `global` 与配置 `global_nets`；默认全局 `0`。层次局部 net 用完整实例路径隔离。net **角色**只来自配置；不会凭 `VDD` 名字猜角色。
- `include "file"` 仅展开配置 `include_roots` 内的明文结构文件；路径相对于包含它的文件，检查真实路径、symlink 越界、循环和深度。默认禁用 includes；不会自动递归读取 PDK。
- 顶层 `save`，以及具名 `dc/ac/tran/options/info` 语句保留为 source-located context，**不执行、不求值**。默认包含顶层测试台和所有实例；`--top name` 只展开指定 subckt，并保留顶层分析上下文以供审查。

不支持 SPICE/混合 dialect、无括号的实例端口列表、`+` 续行、`*`/块注释、escaped identifiers、数组、条件/统计语句、model 定义、加密 PDK 或 include section。真实验收解析导出包内的结构文件 `netlist`，模型加载与分析由 Spectre 执行。遇到不支持的活动结构语句抛出带文件/行/列的 `ParseError`；不是通用 Spectre parser。

未知模型会保留 device 和每个 ordinal 连接，生成 error diagnostic，并令 `graph.complete=False`。PyG 默认拒绝 incomplete graph；`allow_incomplete=True` 仅用于诊断。未解析数值保留 token 化 raw expression、来源、reason、`None`；`complete` 只表示**结构**完整，不表示可仿真或所有参数已解析。被声明为可优化的参数必须已解析且器件语义已知。

## 图、参数组与 PyG

- 静态 `Device/Net/Connection` 和动态 `CircuitGraph.parameters` 分开。保留 MOS D/G/S/B，包括 S/B 同网；PyG 为每个 terminal role 生成独立正反关系，不 coalesce。
- 参数组由配置声明，支持匹配组、正比例绑定、连续/整数域、显式步长、linear/log scale、mutable 标记及成员边界冲突校验。`assignments` 返回完整实例路径与**原始参数名**的映射；它不修改网表/原理图，不根据共享表达式推断新自由度。层次参数/全局变量回写需后续真实 adapter 明确实现。
- `FeatureSchema` 固定器件类别、角色、参数词表和物理 reference scale；每种关系都生成 tensor，缺少边时 shape 为 `[2, 0]`。未知 schema 类别报错，不自动扩充词表。定制模型/字段时需显式传入共同 schema。
- `device.kind` 是类别索引；数值 `device.x` 使用 `sign(v) * log1p(abs(v/reference))`。`parameter_present` 区分缺失，`parameter_mask` 区分可用数值，`optimizable_mask` 标识可调成员。真实零、缺失和 unresolved 不混用；名称和模型 ID 仅存于 metadata。
- 参数组是独立表，不改变 device-net 电路二部图。`group_x` 为 float64 的物理 `[value, lower, upper]`；`group_member_index` 的两行分别是 group/device 索引，`group_member_parameter` 和 `group_member_ratio` 保留绑定语义。units/domain/step 位于 per-graph metadata；`group_mask` 与 `group_mutable` 分开。
- `CircuitHeteroData` 为组/器件绑定定义单独的 batch offset。标准 `Batch.from_data_list(...).to_data_list()` 可恢复图、组和 metadata，测试检查不存在跨电路边/绑定。同一 batch 必须使用同一 `FeatureSchema`。
- Canonical graph 表示统一数据契约，不提供图同构规范化或 topology hash；M5 评估另以精确端口 incidence graph 同构检查跨划分的重复拓扑，忽略实例名与尺寸。
- PyG 适配参考 [HeteroData 文档](https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.data.HeteroData.html) 和 [batching 文档](https://pytorch-geometric.readthedocs.io/en/latest/notes/batching.html)。M4 模型/训练及 M5 迁移评估消费同一图契约；已补齐一项真实同类新拓扑迁移对照；surrogate 与广泛泛化优势仍未验证。

真实环境只开放 `input_pair_width`，范围 3.6–4.4 µm、linear 映射、5 nm 网格；镜像与尾管参数组在环境图中为 `mutable=False`。通用图解析配置 `gpdk045_opamp.json` 中较宽的参数范围仅用于表示，不能直接作为真实动作权限。提议动作和实际执行值分开记录；连续提议加网格投影不等于严格的离散 SAC。

M5's same-class real topology verification and encoder interfaces are complete. M6 now has an offline cross-category protocol, qualified nominal LDO/VCO baselines and one executed, audited physical cross-category pilot; the pilot does not establish transfer or encoder superiority, a [strict-mode requalification](docs/m6-vco-requalification.md) confirmed the first feasible design of all 36 successful VCO runs with the reference deck (28 further Spectre calls), and M6 was then closed at pilot scale. A larger prospectively defined circuit set, the experiment that could answer the transfer question, was not run and needs a new decision and budget. Training stays nominal-only. The existing real parallel path serializes native CDF preparation and permits at most four Spectre workers; the M5 multi-circuit and M6 category experiments run sequentially. PVT scheduling, Monte Carlo and surrogate extensions remain unverified. The latest milestone status is recorded in [project decisions](docs/decisions.md), [M6 protocol](docs/m6-cross-category.md), [LDO qualification](docs/m6-ldo-baseline.md), [VCO qualification](docs/m6-vco-baseline.md) and [physical pilot results](docs/m6-real-results.md).
