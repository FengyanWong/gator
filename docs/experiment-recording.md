# 轻量实验记录

`recording/` 是可选的 SQLite 记录路径，接入已有 `CircuitSizingEnv`、串行/并行 collector、replay 和 SAC checkpoint。开启后，每次请求在参数写入前登记，每次结果与对应 transition 在同一事务内提交；收到提交确认后才处理附件和清理。不开启时，原有 JSON 日志接口继续兼容。记录功能不改变动作、reward、SAC 或 PVT/MC 调度。真实训练入口的记录闭环已完成小规模验收，见 [真实记录验收](recording-real-verification.md)。

## 开启

数据库必须放在本机 Linux 文件系统，例如 WSL 的 ext4 home 目录。不要放 `/mnt/c`、`/mnt/d` 的 9p/DrvFS、NFS、SMB 或 VMware 共享目录。多进程通过本地 Unix socket 把请求交给同一个有界队列 writer；不允许多台机器直接打开这个数据库写入。

```bash
# 当前项目环境；首次另可 pip install -e '.[graph,test,export]'
PY=/tmp/analog-optimizer-venv/bin/python

# 纯 synthetic 示例，不访问 Virtuoso/Spectre。
$PY examples/train_synthetic_sac.py \
  --recording-root /tmp/gator-example-records \
  --recording-config configs/recording.example.json \
  --episodes 1 --steps 2 --batch-size 2

# 对已有 train_opamp_sac_parallel.py 命令增加同样两个参数即可。
# 保留原来的 CDF 表、profile、spec、模型和连接参数；这会运行真实仿真，非本次验收命令。
```

`/tmp` 只适合验收，可被系统清理。长期实验请使用持久的本机 ext4 目录并备份 SQLite 数据库及 checkpoint。运行中备份使用 SQLite backup API；不要只复制 WAL 模式下的主 `.sqlite3` 文件。

Python 接入：

```python
from analog_optimizer.recording import ExperimentStore, RunRecorder
from analog_optimizer.recording.setup import create_run

with ExperimentStore('/home/your-user/gator-records') as store:
    run_id = create_run(store, project_root, configuration,
                        project_files=['configs/my_circuit.json'],
                        templates={'circuit': parameterized_netlist_text})
    recorder = RunRecorder(store, run_id, worker_id='0')
    # 使用已有 backend / graph / specs；不替换算法。
    env = CircuitSizingEnv(backend, graph, specs, work_root, recorder=recorder)
    replay = ReplayBuffer(origin='real', store=store)
    # 然后按原来方式进入 env context、reset/step 或 collect_episode。
```

多进程使用 `manager, store = start_service(root, config)`，将 `RunRecorder(store, run_id)` 传给 `collect_parallel_episodes(..., recorder=...)`，主进程使用同一个 store 创建 replay。最后先 `store.close()`，再 `manager.shutdown()`。不要把线程内的 `ExperimentStore` 本体传入 spawned worker。

内置 `NativeEnvironmentFactory` 在构造环境时传入 recorder，不生成每个 worker 的重复 JSON config/图。自定义 factory 可实现 `create_recorded(lane, recorder)`，在其中将 recorder 传给 `CircuitSizingEnv`；只有 `__call__(lane)` 的旧 factory 仍兼容，但其构造时已写出的文件不会被擅自删除。

## 保存什么

| 数据 | 保存方式 |
| --- | --- |
| 图、task、spec、配置、参数定义、模型版本、模板、项目源码 | `assets` 内容哈希去重；task 引用 graph/spec，evaluation 引用 task/graph/condition |
| 仿真尝试 | `evaluations` 保存 request/result、UTC epoch 开始结束时间、耗时、worker/episode/step、phase、重试/缓存引用、原始参数/指标/有效性、状态/错误、OP、来源及 corner/sample/seed |
| 动态状态 | `states` 保留完整 Observation 的必要字段；静态图只引用，动态参数/metadata/source 改变保存精确 patch，并在写入时核验重建结果 |
| transition | `transitions` 引用前后 state；保留 proposal、reward、分项、两种结束标记、bootstrap、策略版本、action mask 和实际 observation 契约，包括不允许进入训练 replay 的失败 transition |
| 恢复与清理 | `workspaces`、`attachments`、`checkpoints` 保存归属、完成状态、持久化引用与 retained/omitted/evicted 原因 |
| 更新诊断 | 默认每 100 次更新汇总标量 count/mean/min/max；正常结束 flush 尾批；不保存梯度、embedding、attention 或逐步模型副本 |

Python float 使用 float64 的无损往返表示，整数保持整数；数值数组保存原始 bytes、dtype、shape、C order，字段顺序显式保留。原本 float32 的 observation 数组不会被转为 float64，也不将原始物理值转为 float32。无效指标为 `null` + validity；后端提供的有限但无效的部分指标另存 `partial_metrics`，不会充当有效测量。

当前实际 Observation 使用尺寸、规格、测量/mask、状态、剩余预算、工况，归一化为固定物理 reference；没有在线统计量。图差异保存后可以精确重建当前 Observation，不依赖再次运行 Spectre。已有真实后端解析出的器件 OP 会同时保存，含指标校验失败前已经生成的 OP；不额外打开分析或新增内部节点波形保存。

静态 task 记录现有 reward 版本、min/max/range 方向、单位、目标/scale/weight、容差 0、变量顺序/单位/domain/bounds/step、参数绑定和 `absolute-group-v1` 转换规则。模板、分析与提取代码作为项目自有资产保存。实测 Spectre 版本从已有输出日志读取，取不到明确记录 unavailable；不能凭库版本推断 simulator 版本。

`create_run()` 保存项目 `src/`、`examples/`、依赖版本、显式选择的配置及模板。Git 可用时记录 commit、相关 tracked diff 和当前源码；没有 Git 元数据时标记 unavailable，仍保存源码快照，包括未跟踪的项目源码。不会把“只有 commit”当作可复现性证据。模型文件请使用 `provenance.fingerprint()` 记录路径/版本/哈希；并行 CDF 入口保留已有 PDK 指纹、model 路径、section 和参数表。**不复制 PDK、安装目录、许可证或连接凭据；重跑仍需要原有 PDK、Virtuoso Bridge 和 Virtuoso/Spectre 环境。**

低层调用也可使用 `store.call('begin', run_id, task_id, graph_id, request, eval_id=...)`、`start`、`finish` 记录单独验证/重试。每个 corner/随机样本分别使用独立 eval_id，携带 corner_id/sample_id/seed；不会按相同尺寸合并随机重复。缓存记录必须引用已提交原 evaluation，关键参数/原始指标核验一致，不能再调 `start` 或增加 Spectre invocation。此模块不新增缓存、重试、PVT 或 MC 调度。

## 摘要规则

每个 run 保存初始设计、best_feasible、best_infeasible、各自 eval/参数/原始指标/约束判定、首次达标时间和已确认真实调用数、累计次数/失败/缓存/wall time。默认 feasible 选择规则是 **first_feasible**：保留首个满足全部必需规格的设计，不声称它是数值目标最优。若有明确目标，在创建 run 前设置：

```python
configuration['selection'] = {
    'objective': {'metric': 'supply_power_w', 'direction': 'min'}
}
```

该目标必须是有效测量。best_infeasible 使用必需约束的**未截断、加权平均归一化违反量**，同分保留先提交者；无效指标候选不参与比较。实际训练 reward 仍按现有 capped violation 计算，没有修改。未达标时 `has_feasible=False, best_feasible=None`。validation/PVT/MC 不覆盖 nominal best。多种 task 混用的 run 需要选择有相同物理含义的目标；独立任务比较建议独立 run。

`real_simulations` 是有执行证据的调用数；`real_dispatches` 另计 Spectre 派发，`unconfirmed_invocations` 标记断连/异常时无法确认是否启动的尝试。未完成请求也单列 pending。遇到这类不确定情况不能把确认数宣称为精确总调用数；查询原工作目录后补齐结果，不能盲目再跑。mock 次数、cache 次数和真实次数分开。

## 读取、reward 重算和导出

日常查阅优先用 `summary`：默认选择最近创建的 run，显示进度、未完成登记、达标/未达标/失败数量、初始/最佳设计的实际参数和约束、最近评价、checkpoint 和本地空间。`--run` 指定其他 run，`--recent 10` 调整最近评价条数。`open` 只表示没有登记结束，**不能据此判定 worker 仍存活**。

开启 recording 的 `train_synthetic_sac.py`、`train_opamp_sac_parallel.py`，以及 `benchmark_recording.py`，完成结束登记和 writer 关闭后会自动保存一份 UTF-8 中文文本到 **`<recording-root>/summaries/<run_id>.txt`**，并在 `report.json` / 验收报告中记录 `summary_path`。因此数据库使用 ext4 时，摘要也在同一 ext4 目录；每个 run 独立命名。文本是带导出时间的静态快照，磁盘用量是导出前的测量，不会自动刷新。导出失败会显式打印 `SUMMARY_EXPORT_FAILED` 并写入报告的 `summary_export_error`，不掩盖原有训练异常。

已有记录可以补导出；省略 `--run` 时选最新 run，重导出只原子替换该 run 的文本，不改写数据库：

```bash
$PY examples/save_recording_summary.py /home/your-user/gator-records --run RUN_ID
```

强制终止进程或 writer 未能正常关闭时，结束导出可能来不及执行；恢复后可使用上面的命令读取已提交数据。

```bash
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records summary
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records summary --run RUN_ID --json
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records runs
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records show --run RUN_ID
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records pending
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records usage
PYTHONPATH=src $PY -m analog_optimizer.recording /tmp/gator-example-records export \
  --run RUN_ID --output /tmp/one-run-export
```

自动控制脚本可读取 `RunReader(root).overview(run_id)` 或上述 `summary --json`。返回格式为 `run-overview-v1`，区分 `lifecycle`、`pending_by_state`、`summary.outcome_counts`、`summary.error_counts`、`latest_checkpoint` 和 `storage`。新 run 的分组计数随结果在同一事务内更新，读取摘要不扫描全部历史；旧数据库没有这些计数时只读扫描兼容。统计数量包含该 run 的验证评价，最佳设计仍遵循 nominal 选择规则。SQLite 内容来自一致的读快照，磁盘用量为快照后的即时测量，只覆盖本地记录根目录，不代表 VMware 端占用。

`show`、`runs`、`pending`、`usage` 原有 JSON 接口保留；`summary` 的文本只格式化时间/空间，物理参数与指标不降低精度。数据库是实验日志；独立 `.pt` 模型权重的保存/加载不要求读取 SQLite，只有使用成员 ID 保存的完整 replay 恢复需要原数据库。

```python
from analog_optimizer.recording.reader import RunReader
from analog_optimizer.measurements.specs import SpecificationEvaluator

with RunReader(recording_root) as reader:
    for evaluation in reader.evaluations(run_id):
        result = evaluation['result']
        if result is None:
            continue
        task = reader.call('read', 'asset', evaluation['task_id'])
        specs = reader.call('read', 'asset', task['spec_id'])
        verdict = SpecificationEvaluator(specs).evaluate(
            result['metrics'], result['metric_units'], result['metric_validity'])
        # 重算训练 reward 时还要应用原始 status/candidate_evaluated 的失败/截断约定。
        # 也可以换新规格离线评价；不要把新 reward 覆盖进原始 evaluation。
```

导出是显式请求，依赖 `pyarrow`，使用一致的 SQLite read snapshot、分批写 Parquet + ZSTD。`metrics.parquet` 是方便分析的 float64 长表；其余关系表保留精确 payload，可用 `recording.codec.unpack(blob)` 解码。只导出指定 run 及其引用资产，不默认长期保留第二份完整数据。源数据库中的所有失败、缓存和逐样本结果都可读，不从 replay 推导原始实验数据。

## checkpoint 与恢复 replay

```python
from analog_optimizer.training.sac import SACLearner
from analog_optimizer.training.replay import ReplayBuffer

# checkpoint 只加载可信的本地产物；传入同一数据库的 writer 或只读 RunReader。
learner, replay, run_state = SACLearner.load(
    checkpoint_path, experiment=experiment, model_config=model_config, store=store)

# 仅重建 replay；manifest 在 checkpoint['replay'] 内。
replay = ReplayBuffer.from_manifest(manifest, store)
# 指定失败 transition 的完整动态内容：
transition_data = store.call('read', 'transition', eval_id)
```

checkpoint 包含现有 actor/encoder、twin critics、targets、三个 optimizer、log_alpha、固定 normalizer/schema、配置/代码/依赖、Torch/Python/NumPy RNG、训练计数和 collector RNG。replay 只存成员 ID/物理槽顺序、capacity/cursor/insertions、采样 RNG 和数据库 identity/high-water position，不复制样本。数据库可以有 checkpoint 之后的新记录，但不能比 checkpoint 恢复位置更旧、缺少成员或换成另一数据库。

新增 transition 在提交事务内由 writer 计算完整字段的 SHA-256 指纹。replay 入池只查询已提交记录的小型指纹，不重建前后图；动作、动态状态、dtype/shape、结束标记或来源信息改变都会被拒绝。恢复时仍完整重建状态、校验训练契约并复核指纹；缺少指纹的历史行走完整回读兼容路径，无需迁移数据库。checkpoint 的数据库登记位置直接复用实际写入 `.pt` 的位置，不在保存后重新取一次可能已前移的位置。

`result.environment` 的 `diagnostics-v2` 保留环境诊断、投影和耗时，不再次复制 `result.metrics/metric_units/metric_validity/applied_parameters`、`request.requested_parameters` 以及 `request.condition_id` 所引用的工况。原始内容仍完整保存在各自字段；恢复 Observation 所需的动态数组继续保留。

`CheckpointManager` 默认每 500 个 env steps 保存；并行路径在本轮全部结果收齐后的边界检查，因此可晚至一个 worker round。最近两份完整 checkpoint 滚动保留；没有固定验证流程时只保留一个 **final_policy**。`policy(..., validation=...)` 要求预先固定且一致的 rule、完整验证证据和有限 score，才允许保存 best_policy。所有 worker 共用主进程的一个 learner/checkpoint manager。

先序列化到临时文件，预留新增文件占用，fsync、哈希校验和实际加载验证，再原子发布，最后淘汰旧 checkpoint。测试核验重载后下一次采样、loss、模型参数一致。**精确性覆盖 learner/replay；现有 collector 不支持接管正在运行的模拟器或从半个 episode 精确继续。** 周期 checkpoint 明确标记需从新的 episode reset 继续，保存已有计数和 collector RNG；并行 CLI 仍只接受完整运行边界的 checkpoint 自动续跑。不能把这称为外部仿真轨迹的逐步精确恢复。旧源码摘要不匹配的 checkpoint 不自动迁移。

## 空间、附件和异常恢复

默认预算见 `configs/recording.example.json`：每 run 附件 256 MiB，initial ≤1、当前 best ≤1、按错误类型去重的 failure ≤2；每条错误摘要 ≤16 KiB。项目记录根目录预算 20 GiB，每个工作文件系统保留 ≥5 GiB。还为每个 in-flight evaluation 保留 256 MiB 临时/传输空间和 1 MiB 数值结果，另留 64 MiB journal；checkpoint 临时新文件按实测序列化大小预留，旧文件同时计算在已用空间中。

附件同时受数量和字节预算控制，记录 omitted/evicted 原因。空间不足先淘汰允许删除的附件；正常 checkpoint 发布时滚动删除过期文件，最近两份仍受保护。仍不足抛 `SpaceExhausted`，停止派发，不删除 graph/evaluation/state/transition 等核心数值数据。数据库 I/O 失败会锁住 writer 后续写操作并向调用者报错；不会吞掉错误后继续仿真或清理。

本地导出、Spectre 输入、结果和中间传输文件全部放入 evaluation 的专属 owned workspace；只有匹配数据库提交 receipt、ownership token、规范路径、已完成状态才清理。拒绝 symlink、路径越界和归属不明的目录。Virtuoso Bridge 远端使用专属 scratch 根目录和相同 ownership 标记，通过现有 Spectre-host transport 清理 VMware 内的原始结果；删除前检查 PID/存活 Spectre 进程。远端容量在派发前检查；网络不确定、取消或任务仍运行时保留目录和恢复记录，不扫除其他 bridge 目录、PDK 或用户文件。远端 helper 仅依赖 Python 2.7/3 标准库，优先使用可用的 `python3`，否则使用 `python`；不会因操作失败而换解释器重试。主训练程序仍要求 Python 3.10+。已实测 16 次 Spectre 工作目录的提交后清理及真实波形附件保留，详见 [真实记录验收](recording-real-verification.md)。

writer 异常退出后已提交数据仍可读，`pending()` 显示 pending/running。确认旧 worker 已停止后可以 `store.call('recover', eval_ids)` 标记 interrupted；它不会擅自重跑或删除文件。随后从对应目录核实结果并调用 `finish`，明确标记工作完成，再用 receipt 清理。无法确认远端是否结束时保留未完成状态，不从超时推断可删除。

环境路径把请求与 owned workspace 放在一个仿真前事务登记；结果仍在独立事务提交并返回确认。随后 `finalize_workspace(receipt, token)` 在一个事务中处理本地完成标记、保留角色和清理元数据，保留路径/归属/进程检查。删除之后若元数据提交失败，可在恢复 writer 后显式重试补齐状态；缺失的附件来源会标记 omitted 和原因。不会将尚未持久化的结果与文件删除放进同一个事务。

SQLite 运行时版本和 schema 保存于 `meta`。本机版本 3.37.2，默认 DELETE journal + synchronous=EXTRA。WAL 只接受已修复的版本分支：3.44.6+（3.44 分支）、3.50.7+（3.50 分支）、3.51.3+（3.51 分支）、3.53+；拒绝已撤回的 3.52，并只允许已知本地文件系统。开启 WAL 时设置 1000-page autocheckpoint、8 MiB journal_size_limit，关闭 writer 时 TRUNCATE checkpoint；这些不是 WAL 大小的硬上限。[SQLite WAL-reset 问题及修复说明](https://www.sqlite.org/wal.html)

预算检查是派发门槛，不能限制正在运行的 Spectre 突然写出超大文件，也不能阻止别的进程消耗空间。**严格限制临时容量需要各主机对应文件系统的配额或独立受限卷**；不能用定时/派发前检查宣称绝不超限。未知状态的工作目录和未经确认的新 checkpoint 临时文件不会被猜测为可删除，仍计入预算。

后续已统一入口资源清理，支持周期 checkpoint 从新 episode 续跑，并将迁移入口接入 SQLite 与独立 seed 并行。开启记录后的报告历史改为有限近期窗口，完整评价仍在数据库中；详见 [运行恢复与入口说明](runtime-reliability.md)。

## 未保留波形的边界

保留下来的参数、指标、有效性、工作点、状态、动作及奖励可用于统计分析、修改 spec/reward、数据集导出和 replay 重建。没有保留完整原始波形的 evaluation，无法事后重新测量未保存的交越、瞬态峰值/settling、噪声谱、未提取的内部节点信号或未运行的分析；需要原有 PDK/仿真环境重新运行。完整 Pareto 集可以从全部数值记录重新计算，不需要复制候选波形。

## 离线验收

```bash
$PY -m pytest -q
$PY examples/benchmark_recording.py \
  --output /tmp/gator-recording-6000-20260919 \
  --report artifacts/local/recording-6000-report.json
```

6000 次验收使用 `MockBackend` 指标/状态注入和 toy 参数读回，包含成功、未达标、timeout、nonconverged、缺失指标；不计算电路物理，不调用真实 Spectre。体积测量包含所有 evaluation 和动态 transition、有限 replay 成员引用、两份完整 checkpoint 和一份 final policy。测量结果见同目录 `recording-verification.md` 与机器可读报告。

记录开销的独立对照：

```bash
$PY examples/benchmark_recording_overhead.py \
  --output /tmp/gator-recording-overhead-new \
  --report artifacts/local/recording-overhead-report.json
```

默认每种路径 600 次 mock evaluation、3 次重复，轮换顺序并先预热：原有 JSON 路径、同一个 SQLite writer 加旧式 replay 全量回读、优化后的 SQLite 指纹核对。动作/故障注入/模型配置/更新日程/checkpoint 周期保持一致，核对完整轨迹摘要和全部网络权重一致。报告启动、评价、transition 构建、入池、SAC 更新、checkpoint 的耗时以及空间。原有 JSON 路径仍有日志和后端输出，不是完全无 I/O 的基线；这不是实测 Spectre 性能。`--update-every` 默认 10，测试用于分离记录成本，不代表正式训练超参数。
