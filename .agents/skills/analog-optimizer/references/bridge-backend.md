# Virtuoso bridge 与仿真后端

## 1. 名称与事实边界

核对日期：2026-09-19。上游仓库名是 `Arcadia-1/virtuoso-bridge-lite`；核对的 `pyproject.toml` 中发行包名为 `virtuoso-bridge`，import 命名空间为 `virtuoso_bridge`。[S2–S3](sources.md)
不要仅凭仓库名字执行 `pip install virtuoso-bridge-lite`，也不要假定本机版本等于当前上游。

上游提供 SKILL 执行与 standalone Spectre 能力，两条路径可以分开使用。[S2](sources.md)
这不表示所有 schematic/ADE export 或测量任务都已有统一 API。写代码前查本地真实签名和返回对象。

建议只读检查：

```bash
command -v python
command -v virtuoso-bridge
python -m pip show virtuoso-bridge
virtuoso-bridge --help
```

真实连接检测要使用用户已有 profile，遵守本机权限；不要为了检查而重置用户配置或部署新 daemon。
上游 `AGENTS.md` 与 `skills/virtuoso`、`skills/spectre`、`skills/netlist` 是接口使用参考，不是本项目研究架构的替代品。

## 2. 项目自有 Backend

以下名称是建议设计的**项目 Protocol**，不是声称上游原生支持：

```text
healthcheck(config) -> BackendHealth
export_netlist(circuit_ref, work_dir) -> NetlistArtifact
read_parameters(circuit_ref, bindings) -> ParameterSnapshot
apply_parameters(circuit_ref, assignments, job_context) -> AppliedParameters
run_simulation(request) -> SimulationResult
collect_measurements(result, measurement_spec) -> MeasurementResult
close() -> None
```

每个方法有输入 schema、超时、错误类别与测试。
不支持的 capability 显式返回/抛出 `UnsupportedCapability`；不能用 TODO 返回成功。
可按实际代码合并方法，但要保留可测试边界。

实现层：

```text
MockBackend                       # synthetic，离线测试默认
VirtuosoBridgeBackend             # 适配已核对的上游调用
Runner / MeasurementExtractor     # 必要时细分；不强制过早抽象
```

真实 Backend 不得依赖 mock。缺少 Cadence 时保持 adapter 的明确未接入状态；离线测试与 contract test 可继续完成。

## 3. 请求与结果契约

请求包含 `job_id`、netlist/testbench 标识、候选参数、corner/温度、analysis 配置、超时、资源限制、输出目录和来源类型。
参数回写后需要验证实际生效值：网表读回或经核实的数据库/变量读回，不把 API 无异常当成成功更新。

结果至少包含：

```text
job_id / backend_kind / result_origin: real | synthetic
status / reason_code / retryable / candidate_evaluated
proposed_action / applied_parameters
metrics / metric_units / metric_validity
artifact_locations / redacted_log_summary
timing_breakdown / config_fingerprint / provenance
```

推荐区分：

- `ok`：运行和所需测量流程完成；是否满足规格由 evaluator 另算。
- `invalid_design`、`nonconverged`：候选参数或电路行为引起的无效设计。
- `measurement_error`：输出或指标提取不满足契约，不填正常数值。
- `timeout`：需额外判断是在求解、排队还是网络阶段。
- `transport_error`、`license_error`、`backend_error`：基础设施或接口失败。

状态与 reward 不直接一一混用。基础设施失败通常不作为“这个候选设计很差”的学习样本；记录重试与实际消耗，必要时中断。
电路相关失败可以按声明的有限 penalty 规则处理；无法判断原因的失败标记 ambiguous，不凭空归因。

### M3 工况/统计接口

项目使用 typed `PVTCorner(id, model_section, temperature_c, supply_v)` 与 `SimulationCondition(corner, purpose, monte_carlo)`；purpose 为 nominal/pvt_validation/mc_validation。`NetlistArtifact`、`SimulationRequest`、`SimulationResult` 与日志记录相同 context，request 不可给已生成网表换标签。生成网表前验证工况支持范围，拒绝未知 section、越界条件或未实现的 MC，不能等到回写后才发现不支持。

`MonteCarloConfig(samples, seed, variation, model_section)` 与 `MonteCarloResult` 保留将来的统计执行入口。每个样本有独立 sample_index、status、validity 和 artifact；保留失败样本。同批样本必须来自相同 nominal 尺寸与 provenance，不能混入另一候选或 synthetic/real 来源。批次另记录 simulator_invocations，不能把一个批次只计为一个样本。当前 GPDK045 adapter 不执行 MC；`run_monte_carlo` 明确报不支持。

PVT 变化只作用于批准的测试台 job 副本。当前 OTA 的电源允许工况覆盖，VINP/VINN/VBIAS 保持原绝对电压；不暗中按 VDD 缩放偏置。实际图中的 VDD 特征需跟随执行值，PDK 模型内容及统计语法仍不送进结构 parser。训练 context、采样预算和后验证预算分开，见 [详细契约](pvt-monte-carlo.md)。

## 4. 运行模式与可恢复性

- Python 可在 WSL/Linux，Virtuoso/Spectre 可在 Linux VM；本地模式与远程模式使用同一项目 API。
- 本地路径和远端路径是不同命名空间。上传后验证远端文件存在/摘要，不把 WSL 文件路径直接传给 VM。
- Cadence 环境可能由 csh 配置加载；尊重上游/本机设置，不把 csh 文件直接 `source` 到 bash。
- 优先使用现有 SSH profile；不记录密码、不关闭 host-key 验证，不假定免密已配置。
- 显式绑定所需 bridge 配置，避免长期进程被其他目录的 `.env` 改变目标；具体绑定方法查本地版本。
- 对共享 Virtuoso session 加锁。修改 schematic 时使用设计副本/检查点和经过验证的恢复策略。
- netlist-only 参数化路径只有在模型、corner、测量与原测试台一致并被验证后才能替代 ADE 路径。
- job 使用唯一目录，原子写入输入和结果清单，保存候选参数摘要；禁止多任务覆盖同一 `input.scs`。
- 重试必须有限、有原因分类；优先从 `job_id` 查询已有结果，避免断连后盲目重复昂贵仿真。
- 超时只停止本 job 的进程组或已知任务，不使用无差别 `killall spectre` / `killall virtuoso`。

## 5. 并行原则

先完成单 worker 真实基线，再增加 worker。多环境共享单策略/经验池是后续扩展，不是首版依赖。

相互独立的仿真实例需要独立工作目录、受控资源、独立设计状态，或共享只读设计加独立网表。
单个 Virtuoso session 不允许多个 worker 无锁交错修改同一设计。

将仿真采样和训练更新分开计时，记录 CPU 线程、内存、许可证、队列延迟与失败率。
不要把“7 个 worker”或历史加速比硬编码为最优配置。

## 6. 性能与数据记录

至少测量：

```text
queue_wait / connect_or_transport / parameter_update / netlisting
simulation / transfer / measurement_parse / graph_build
policy_inference / learner_update / total_wall
```

可先复用连接、减少重复 netlisting/全量 waveform 传输、缓存静态图，但每项优化都需要回归测试。
若使用缓存，key 必须覆盖执行参数、PDK/model 版本标识、testbench、corner、仿真精度、测量版本及随机种子等影响输出的因素。
统计 cache hit 与真实调用分开；不得跨 train/test 偷用尚未允许的候选结果。

## 7. 接入验收

离线测试：mock 不访问网络；注入 timeout/指标缺失/参数回写失败；结果结构验证；日志脱敏。
真实测试：读取一个明确目标 → 导出/读取网表 → 运行原始参数 → 校验测量 → 改一个获准参数 → 确认生效 → 按约定恢复。
真实测试缺权限或缺 PDK 时明确 skip/blocked，不能宣称端到端已通过。
