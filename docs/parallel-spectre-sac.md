# 有限 CDF 表、Python 网表与并行 Spectre SAC

2026-09-19，用户授权预先建立有限参数表，用 CDF 读回与 Python 模板生成网表，并通过用户输入控制同时运行的 Spectre worker 数量。

## 两个阶段

1. `examples/build_opamp_cdf_table.py`：独占现有 Virtuoso 会话，在已授权 GPDK045 OTA 上串行修改 M1/M2 匹配宽度，读取完整 CDF 参数。范围仍为 3.6–4.4 µm、5 nm 网格，共 161 行，其他尺寸、finger、multiplicity 和偏置固定。保存原生测试台网表作为模板；每行把 `w/ad/as/pd/ps/nrd/nrs/sa/sb/sd/sca/scb/scc` 从 CDF 读回写入模板，并与该行的 Virtuoso 原生导出逐参数、逐连接比较。基线导出一次，加上 161 行原生导出；此阶段不调用 Spectre。全部通过且原理图恢复之后才发布 `table.json`，失败保留记录并由原有后端恢复。
2. `examples/train_opamp_sac_parallel.py`：读取并校验有限表，Python 查表生成各自的不可变网表。通过原有 bridge standalone Spectre 和测量提取路径执行 DC/AC，训练期间不连接或修改 Virtuoso。

表记录 PDK 文件内容摘要、模型路径、bridge 版本、图/映射/设计/工况/搜索域的配置摘要及每行核验记录。PDK 树在准备前后和每个 worker 启动时检查，未复制或上传 PDK 内容。只排除临时 `.cdslck`/`.lock` 文件。配置、模板或 PDK 变化后需要重建；这不是通用 PDK 自动约束提取，也没有重新推导 CDF 几何公式。表只缓存器件参数和网表，不缓存仿真结果。

## worker 和 SAC 的关系

`--max-workers N` 必须由调用者指定为正整数，表示同时存在的 Spectre 作业上限。实际 worker 数为 `min(N, episodes)`；每个 worker 是独立的 Python 子进程，最多运行一个 Spectre 作业。各 worker 有独立的 backend、环境状态、网表、PSF、日志与计数，使用同一个只读 CDF 表。独立进程也隔离 bridge 的进程级环境变量和 stdout 重定向。

主进程持有唯一的 actor、critics、replay 和优化器。第一版采用同步轮次：主进程按各环境当前观测生成动作，多个 worker 同时执行；本轮全部返回后，按固定 worker 顺序核验 transition、写 replay，并在达到 batch 大小后对每条有效新增经验做一次 SAC 更新。下一轮使用更新后的 actor。记录 proposal、policy version、执行尺寸与候选 ID；不会把不同 worker 的前后状态拼成一条轨迹。

每个 episode 有一次真实 reset 和指定步数的候选；reset 不进入 replay，但计入仿真调用。总预算上限为 `episodes × (steps-per-episode + 1)`。当前入口保持 nominal-only、固定步数且不因达标提前停止。明确归因的电路失败沿用有限惩罚；超时、基础设施或测量错误不进入 replay，当前轮其他已完成的有效样本仍被收集，然后排空并关闭所有 worker，报告失败。没有自动重试。

`--max-workers` 不是单个 Spectre 的内部线程数，也不承诺相同数量的物理核心或许可证。可以先用 2，再比较不同并行数的有效候选吞吐。进程启动、PDK 检查和有限表准备成本单独考虑；小预算 smoke 不能用于证明加速比或学习优势。

## 当前环境复现

先保存并关闭与专用 OTA 冲突的 ADE/Maestro 窗口，保持已有 bridge 会话。以下是本机已配置路径，不是代码硬编码的连接参数。

```bash
/tmp/analog-optimizer-venv/bin/python -B examples/build_opamp_cdf_table.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --pdk-root /home/minlei/pdk/gpdk045_v_6_0 \
  --output artifacts/local/opamp-cdf-table \
  --bridge-site-packages /home/fyworkstation/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages
```

输出目录必须不存在，避免覆盖已有表。完成后同一张表可以跨训练运行复用：

```bash
/tmp/analog-optimizer-venv/bin/python -B examples/train_opamp_sac_parallel.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --cdf-table artifacts/local/opamp-cdf-table/table.json \
  --reference-measurements artifacts/local/opamp-baseline/simulations/ff6dc7e7c3944d77a0ace70da4d63385/measurements.json \
  --max-workers 2 --episodes 2 --steps-per-episode 3 --warmup 2 --batch-size 2 \
  --output artifacts/local/parallel-sac \
  --bridge-site-packages /home/fyworkstation/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages
```

调整 `--max-workers` 控制并发，`--episodes` 控制全体 worker 合计 episode 数量，`--steps-per-episode` 控制各 episode 的候选步数。`--encoder` 支持既有六种编码器。首次启动和每个 episode 的基线均与提供的真实参考指标核对。

`report.json` 保存各 worker 的 PID/目录、reset、候选、SAC loss、调用数、并发上限及恢复状态。完成后保存完整 `checkpoint.pt`。`--resume CHECKPOINT` 从一个已完成运行继续新增 `--episodes` 个 episode，恢复网络、优化器、replay 和 RNG；要求实验配置与源码一致。每个新 episode 重新真实 reset，不接管半完成的 Spectre 作业。失败运行保留完整日志，不产生可当作成功运行继续的 checkpoint。

## 验收

完整离线回归 **373 项通过，零失败、零跳过**。新增验收覆盖表缺行/摘要错误/派生参数变化、独立网表、原生导出不一致时拒绝发布并恢复、PDK 内容变化、真实子进程的 1/2 worker 上限、不同完成顺序的轨迹与 replay 归属、SAC 更新、checkpoint 下一次更新精确恢复，以及一个 worker 超时后排除其经验并排空其他 worker。

本轮真实验收已完成：

| 阶段 | Spectre 调用 | replay 条数 | SAC 更新 |
| --- | ---: | ---: | ---: |
| CDF 预计算与全部 161 行核验 | 0 | 0 | 0 |
| 2 worker × 1 episode × 3 候选，另各 1 次 reset | 8 | 6 | 5 |
| 从 checkpoint 续训同样预算 | 8 | 累计 12 | 累计 11 |

有限表准备耗时 204.58 s，包含 162 次原生导出、161 行 CDF 回写/读回及恢复。PDK 摘要覆盖 2014 个文件，准备前后保持一致。训练入口两次运行分别耗时 11.37 s、10.52 s（collector 计时，包含 worker 启动/检查/关闭，不含主进程模型初始化和最终 checkpoint 保存）。训练阶段没有原理图回写；worker 基线均与已有真实指标匹配。首次运行的 Python 网表准备平均 68 ms，参数选择/读回约 0.52 ms；这是本次测量，不是与旧路径成对执行的速度基准。

续训期间在 Spectre 主机以约 0.1 s 间隔采样 300 次进程列表，15 次看到两个不同 PID 的本项目 Spectre 同时运行，观测峰值为 **2**，没有超过 `--max-workers 2`。不是只凭 Python Future 数量判断实际仿真并发。最终额外只读检查确认 Virtuoso M1/M2 仍为 4 µm，其他固定尺寸与基线一致。两次真实训练合计 **16 次 Spectre**，没有自动重试；前面的沙箱连接失败尝试为 0 次仿真。

- [有限 CDF 表](../artifacts/local/opamp-cdf-table/table.json)、[准备统计](../artifacts/local/opamp-cdf-table/preparation.json)
- [首次 2-worker 训练](../artifacts/local/parallel-sac/cfc7994e674c4b8a94f39a7fa87f25bc/report.json)
- [真实 checkpoint 续训](../artifacts/local/parallel-sac/71c21ac121eb49cd80fccef4a71448bb/report.json)
- [Spectre 主机进程采样摘要](../artifacts/local/parallel-sac-process-monitor.json)、[原始记录](../artifacts/local/parallel-sac-process-monitor.log)
- [最终原理图只读检查](../artifacts/local/parallel-final-inspection/220b9874a36248cf8dbc2582e478abde/verification.json)
- [完整离线回归 JUnit](../artifacts/local/parallel-spectre-tests.xml)

这些结果验证有限表、实际并发和 SAC 数据更新链路，不构成 SAC 收敛、迁移优势或线性加速结论。当前表仅适用于固定的五管 OTA、输入对单一宽度参数组、nominal 工况；扩大 W/L/nf 或换 PDK/拓扑需要建立新的合法化与表验证契约。
