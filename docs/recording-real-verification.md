# 实验记录真实闭环验收 — 2026-09-19

使用已有 GPDK045 五管 OTA、161 行有限 CDF 表、nominal TT/27°C/1.0 V 和原 smoke specs，完成 **16 次 Spectre、12 条新 transition、10 次实际训练更新**。完整离线回归 **413 passed，0 failed，0 skipped**，76.14 s。数据库、参数、网表摘要、reward、波形附件、checkpoint 恢复及远端清理审计均通过。

## 真实调用与恢复

| 阶段 | 实际 worker | Spectre 调用 | 新 transition | 新 SAC 更新 | collector 时间 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 单 worker，1 episode × 3 候选 + reset | 1 | 4 | 3 | 2 | 13.00 s |
| 2-worker，2 episodes × 3 候选 + resets | 2 | 8 | 6 | 5 | 14.80 s |
| 加载上行 checkpoint，追加 1 episode | 1 | 4 | 3 | 3 | 13.25 s |

恢复命令仍设 `--max-workers 2`，由于只有一个新 episode，实际启动一个 worker。恢复后该训练链累计 12 次调用、9 条 replay、8 次更新；单 worker 的首个 run 是独立训练，不能把两个 replay 合并成同一 learner 的经验。

每个 reset 都与既有真实参考测量逐项比对。训练使用各自独立的不可变网表，无原理图写入；前后只读检查的完整 CDF 快照（instances/nets/pins/notes）相同，输入对均为 4 µm。运行中无自动重试，全部 16 次结果有效。Spectre 版本从真实日志保存为 `23.1.0.242.isr1 64bit -- 7 Sep 2023`。

2-worker 期间以约 0.1 s 间隔采样 600 次虚拟机进程，共 22 次看到两个本项目 Spectre PID 同时运行，峰值为 2。时间包括 worker 启停、PDK 检查、记录和清理，不含主进程模型初始化及最后 checkpoint 保存；不是成对加速比实验，也不说明模型收敛或迁移优势。

## 发现并修复的问题

首次单 worker 尝试在仿真前失败：虚拟机提供 Python 2.7.5，记录清理 helper 原来写死 `python3`，且使用 Python 3 的 pathlib/异常接口。该尝试 **0 次派发、0 次 Spectre、0 条 transition**，失败 evaluation 和错误摘要保留。

`recording/remote.py` 改为兼容 Python 2.7/3 的标准库实现，按解释器是否存在选择 `python3` 或 `python`。容量、目录归属、规范路径、符号链接和存活进程门槛保持。操作报错后不切换解释器重试。新增两个解释器选择测试，扩展错误 token、路径越界、symlink、存活 PID 的拒绝测试；真实虚拟机上也已执行创建、完成和删除链路，无新解释器安装。

首次失败留下的本地空目录，在确认原 worker 已退出、未派发仿真、只有归属标记后，通过匹配的持久化 receipt 收尾，数值记录未改写。记录为一个失败附件，不删除失败历史。

## 数据和文件审计

- 16 条真实 evaluation 的请求、实际参数、CDF 行、重建网表摘要与执行摘要一致；全部 12 条 transition 的 proposal 合法化、前后状态、reward、结束标记及 worker 归属一致。
- 逐 run 从数据库重建 replay，加载最终 checkpoint 后重复下一次采样和 SAC 更新；采样指纹、loss、actor、twin critics、targets、alpha 和三个 optimizer 状态完全一致。审计更新只在内存运行，不计作新增训练或仿真。
- 周期 checkpoint 在本次配置中设为 2 步，产品默认仍为 500 步。每个成功 run 留下最近两份 full checkpoint 和一份 final policy；并行及恢复 run 的旧文件实际轮换删除。
- 每个成功 run 保留一份 initial 和一份 best 附件，共六份真实附件。逐份核对测量与数据库一致、两份网表 SHA-256 一致，并确认 AC/DC PSF 文件存在。单份压缩约 149 kB，未超过 256 MiB/run 附件预算。
- 全部 run 按需导出 Parquet，在临时目录逐项核对 144 个指标的 float64 数值/有效性及 evaluation/transition 行数；导出验证后不保留重复数据副本。
- 17 个本地工作目录（含首次失败）和 16 个远端工作目录全部清理；远端只剩 scratch 根目录归属标记与锁。SQLite `quick_check=ok`，foreign key errors=0，pending=0，没有不确定仿真计数。

数据库、附件和 checkpoint 放在持久 WSL ext4：

```text
/home/fyworkstation/gator-records/recording-real-20260919/
```

| 类别 | 文件字节数 |
| --- | ---: |
| SQLite | 749,568 |
| 附件，六份真实波形 + 一份预检失败 | 893,199 |
| checkpoint，三个 run 各 2 full + 1 final policy | 11,204,746 |
| journal / 临时输出 | 0 |
| 总计 | 12,847,513（约 12.25 MiB） |

本轮验证真实小文件下的保留与轮换行为；没有故意填满虚拟机磁盘或制造大波形超预算。严格临时容量上限仍需要文件系统配额。collector 从新 episode reset，未验证接管半完成仿真。当前仍只有输入对宽度一个可调组，本轮没有扩展参数域、真实新拓扑、PVT/MC 或 M6。

## 复现与证据

使用 [并行入口](parallel-spectre-sac.md) 中的本机连接、CDF 表和参考测量参数，增加：

```bash
--recording-root /home/fyworkstation/gator-records/recording-real-20260919 \
--recording-config artifacts/local/recording-real-acceptance/recording-config.json
```

三阶段依次为 `--max-workers 1 --episodes 1`、`--max-workers 2 --episodes 2`、`--max-workers 2 --episodes 1 --resume CHECKPOINT`；均设 `--steps-per-episode 3 --warmup 2 --batch-size 2`。第三阶段加载第二阶段报告中的 `checkpoint` 路径，使用同一个记录数据库。需要保持源码/schema/依赖一致。

- [单 worker 报告](../artifacts/local/recording-real-single/b223568083b14df5933b5197ce4268b6/report.json)
- [2-worker 报告](../artifacts/local/recording-real-parallel/124846fed46a4e018a4fb912e016ecb5/report.json)
- [真实续跑报告](../artifacts/local/recording-real-resumed/f6b7c010565049d3aea3d296ba3afcdb/report.json)
- [数据、波形、checkpoint、清理与并发审计](../artifacts/local/recording-real-acceptance/audit.json)、[只读审计脚本](../artifacts/local/recording-real-acceptance/audit.py)
- [前后完整设计比对与测试计数](../artifacts/local/recording-real-acceptance/design-verification.json)、[完整回归 JUnit](../artifacts/local/recording-real-regression-tests.xml)
- [初次 0 调用失败](../artifacts/local/recording-real-single/aa78e12092094dc581f75adf1d52bc90/report.json)、[失败目录收尾凭据](../artifacts/local/recording-real-acceptance/preflight-recovery.json)
- [虚拟机进程采样](../artifacts/local/recording-real-acceptance/process-monitor.log)
