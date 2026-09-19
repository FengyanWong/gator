# 运行恢复、退出与迁移入口整合

本轮修复程序运行能力，保持 nominal、动作合法化、奖励、SAC 更新规则和任务隔离。未新增真实 Spectre 调用，未启动 M6。

## 周期 checkpoint 恢复

`examples/train_opamp_sac_parallel.py --resume FILE` 接受完整采样轮结束或完整运行结束的 checkpoint。周期备份包含已完成轮次的 learner、replay、RNG 和累计计数；多次恢复时会加入前次计数。`--episodes` 始终表示这次追加的新 episode 数。

恢复从新的环境 reset 开始，不接管半完成的仿真，不恢复原 worker 的 episode 状态。未完成 episode 的已入池经验仍保留，但不算作已完成 episode。只有完整、成功处理的轮次才发布周期 checkpoint；SAC 更新失败的轮次不发布新备份。

synthetic 入口的周期备份也包含完整累计计数，避免恢复后缺少 `completed_episodes` / `synthetic_calls`。恢复顺序从入口的新 episode 调度开始，不宣称 collector 轨迹与未中断运行完全相同。

计数沿所选 checkpoint 的训练分支累计；若选择较早的 checkpoint，原运行在它之后产生的评价仍保留在原 run 中，不会自动加入恢复的 replay。核算全部实验成本应汇总对应 run 的评价，而非只读取恢复分支的计数。

源码、依赖、模型、任务和 schema 的严格兼容校验保留。本轮修改了源码，改码前的 checkpoint 不自动迁移。

## 统一清理与 worker 等待

`training/runtime.py` 为并行训练、synthetic 训练和迁移 CLI 管理记录服务。从服务创建后立即保护资源，初始化/加载失败也会关闭 writer 和 manager。更新摘要、run 结束登记、writer 关闭、manager 关闭、中文摘要及最终报告分别尝试；后续错误写入 `cleanup_errors`，不覆盖原始训练错误。环境恢复记录无法写入时，仍尝试恢复参数并关闭 backend。

新增公共参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--worker-timeout-seconds` | 300 | 主进程等待单个 worker 操作的上限，包含通信 |
| `--shutdown-timeout-seconds` | 10 | 关闭操作及各阶段进程退出等待的上限 |
| `--history-limit` | 100 | 开启 SQLite 后，报告保留的近期条目数；0 表示只留统计 |

并行训练仍按同步轮次与固定 lane 顺序入池，每个新样本最多更新一次。worker 超时后先尝试正常关闭，再 terminate / kill 本次创建的本地 Python 子进程。报告保存未确认操作、worker 状态和已确认调用下界；已经成功完成的其他 lane 样本仍入池。

停止本地 worker 不代表远端 Spectre 已结束。远端未确认 job 和 owned workspace 保留，不自动重试、不据此删除。`shutdown-timeout-seconds` 是每个退出阶段的限时，不是所有 worker 合计的总时限。

迁移 seed worker 在完成评价或阶段时报告进展；主进程同时检查所有 seed 的停滞期限，某个 seed 的正常进展不会掩盖另一个 seed 的卡死。

## 迁移入口

`examples/benchmark_transfer.py` 支持 `--recording-root`、`--recording-config` 和 `--max-workers`（默认及最大 4）。真实候选由单个专用 Virtuoso 服务串行处理 CDF 与原生导出，再独立并行仿真；已移除有限 CDF 表依赖。

并行单位为**独立 seed**。每个进程内依次完成该 seed 的预训练、validation 和测试；每个进程最多一个仿真环境，不再嵌套采样进程。各 seed 的 learner、RNG、优化器和 replay 独立，同一测试任务的 frozen / scratch / adapt 规则保持原样。主进程在启动 worker 前冻结完整协议并检查总调用预算。

不同阶段使用独立记录 run；控制 run 保存项目和协议来源。完整报告中 `phases` / `test_runs` 的 `recording_run_id` 指向具体评价记录。控制 run 的 summary 不代替整个 benchmark 的聚合报告；总调用、达标率和成本以 `report.json` 为准。训练阶段保存周期 checkpoint、final policy 和更新摘要；replay 使用该阶段实际入池的数据库成员 ID。

离线示例（路径由调用者指定）：

```bash
python examples/benchmark_transfer.py \
  --origin synthetic --seeds 17 29 --encoders mlp \
  --pretrain-steps 2 --test-steps 2 --max-calls 76 \
  --max-workers 2 --recording-root /path/on/ext4/records \
  --history-limit 100 --output artifacts/local/recorded-transfer
```

真实入口沿用连接、模型和参考测量参数，无需 `--cdf-table`。新的逐候选 CDF 流程及验收边界见 [并行训练说明](parallel-spectre-sac.md)。

## 长运行报告

开启记录后，训练 `stages/resets`、synthetic episode 列表以及迁移的动作/记录/更新/曲线只保留有限近期条目。`*_count` 与成功率、首次达标、最佳指标、失败数等累计统计覆盖全部评价；完整数值历史留在 SQLite。最早的成功和最佳候选不会因退出近期窗口而消失。

不启用记录时保留原 JSON 完整历史行为。此上限针对新增的运行报告历史，不宣称所有 backend 缓存和整个进程内存都有统一硬上限。

## 验证

完整离线回归 **430 passed，0 failed，0 skipped**，用时 175.26 秒。唯一 warning 来自现有 PyTorch `torch.jit.script` 弃用提示。

验收包括 CLI 周期备份连续恢复、累计计数、learner/replay 精确重载、初始化和报告故障、worker 卡死/意外退出、环境恢复记录失败、并行 seed 与串行权重/预算一致、replay 分区隔离、完整计数与有限历史。

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q -ra \
  --junitxml=artifacts/local/runtime-reliability-tests.xml
```

测试结果见 [JUnit 记录](../artifacts/local/runtime-reliability-tests.xml)。测试中的后端均明确标为 synthetic；本轮真实仿真调用为 0。
