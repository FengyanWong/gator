# 记录开销对照 — 2026-09-19

使用本机 WSL2/ext4、Python 3.10.12、SQLite 3.37.2（DELETE + synchronous=EXTRA）、PyTorch 单线程。每种路径 600 次 MockBackend evaluation，3 次重复并轮换顺序；另有 90 次预热。共有 5400 次计时评价，**真实 Spectre 调用为 0**。

三种路径使用相同图、动作种子、失败注入、replay 容量 256、32 hidden/2 layers/4 heads 模型、batch=8、每 10 个 env steps 更新一次、每 500 步 checkpoint，并在结束保存完整 checkpoint 和 final policy。每个种子下，逐次评价/动作/参数/状态/结束标记的摘要及全部 actor/critics/targets/温度参数完全一致。

| 项目：三次重复的中位数 | 原有 JSON 路径 | SQLite + 完整回读入池 | SQLite + 指纹入池 |
| --- | ---: | ---: | ---: |
| 600 次评价总耗时（含初始化和最终保存） | 12.12 s | 31.85 s | 28.09 s |
| 循环平均每次评价（含定期 SAC 更新/checkpoint） | 18.38 ms | 49.67 ms | 44.05 ms |
| replay 入池平均耗时 | 1.33 ms | 7.56 ms | 3.24 ms |
| checkpoint 平均耗时（含 final policy，3 次） | 662.57 ms | 230.21 ms | 246.39 ms |

完整回读与指纹两组使用**同一个优化后的 writer**，只切换入池核验方式；这不是整个旧版 recorder 与新版的对比。指纹入池减少约 57% 的入池耗时。相对于原有 JSON 路径，SQLite 记录在这组快速 mock 中平均增加约 **25.67 ms/评价**，循环耗时约增加 140%；不能说记录对所有训练都“几乎没有开销”。原有 JSON 路径仍写日志并保留 backend 输出，不是完全关闭 I/O 的基线。

文件系统延迟有明显波动：SQLite 指纹组的三次总耗时为 28.09、27.33、49.78 s。这里只报告样本与中位数，不宣称稳定的端到端加速或真实 Spectre 的百分比。对于耗时数秒到数十秒的仿真，应使用实际仿真时长加上这些记录成本估算，再做真实环境计时；本任务没有发起这种昂贵测试。

第二轮计时前，将请求/工作目录登记合并为一个仿真前事务，将本地清理元数据合并为一个**结果提交之后**的事务。普通无附件评价的主要写事务从 6 个降到 4 个。请求、实际参数派发、结果提交和后续清理仍各有明确持久化边界，未使用关闭 fsync、丢记录或降低浮点精度的方式换速度。

```bash
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_recording_overhead.py \
  --output /tmp/gator-recording-overhead-batched-20260919 \
  --report artifacts/local/recording-overhead-report.json
```

- [完整分阶段数据与各轮样本](../artifacts/local/recording-overhead-report.json)
- [事务合并前的开发期计时](../artifacts/local/recording-overhead-before-transaction-batching.json)（文件系统波动明显，不与后轮相减宣称所有差值都是优化收益）
- [逐项重复读写检查与保留理由](recording-io-audit.md)
- [查询和配置说明](experiment-recording.md)

这是单 worker 的记录开销对照；并行 writer 正确性另由真实 spawned 本地 mock worker 测试验证，未测真实 VMware I/O 或多 worker 仿真吞吐。
