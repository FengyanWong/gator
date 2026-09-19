# 实验记录离线验收 — 2026-09-19

初版完整回归：**403 passed，0 failed，0 skipped**，用时 83.19 s。仅使用本地 mock、解析 toy 后端及注入的 Bridge adapter fixture；真实 Virtuoso/Spectre 调用为 **0**。后续重复 I/O 优化的验收另列，保留这轮历史证据。

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q
/tmp/analog-optimizer-venv/bin/python examples/benchmark_recording.py \
  --output /tmp/gator-recording-final-6000-20260919 \
  --report artifacts/local/recording-final-6000-report.json
```

新增验收覆盖成功/未达标/超时/不收敛/缺失指标/取消、参数量化后的实际执行值、state/action/reward/next_state 与两类结束标记、静态去重、线程和 spawned worker 幂等提交、进程 `os._exit` 后恢复、写事务失败时禁止清理/继续派发、路径越界/symlink/存活 PID 保护、容量不足及淘汰状态一致性、附件数量和字节限制、checkpoint 原子失败保留、精确 learner/replay 续算、Parquet float64 往返及共享 task 的跨 run 导出隔离。已有环境、SAC、图、输入缓存、迁移与并行测试也全部通过。

另外完成双拓扑 recorded synthetic CLI smoke：6 次 toy evaluation、4 条 replay、3 次更新、两个环境均恢复初始参数，checkpoint 续算一致。并行 recorded collector 使用两个真实 spawned **本地 mock worker** 和一个 SQLite writer 通过验收。

## 6000 次体积

开发过程中执行两轮各 6000 次 mock；下表报告后轮，不把前轮或测试样本合并计算。后轮 run_id 为 `b310c7bad670446d88baac155917800b`，耗时 394.05 s。保存 6000 evaluations、5819 transitions、5940 共享 states；其中 timeout/nonconverged/measurement_error 各 60 次，共 180 次失败，全部在数据库。内存 replay 最多 256 条。

| 类别 | 文件字节数 | 约合 | ext4 已分配字节（含对应目录） |
| --- | ---: | ---: | ---: |
| SQLite 数据库 | 25,382,912 | 24.21 MiB | 25,387,008 |
| journal / WAL | 0 | 0 B | 0 |
| 完整附件，3 份 | 2,852 | 2.79 KiB | 16,384 |
| checkpoint，2 full + 1 final policy | 3,750,446 | 3.58 MiB | 3,764,224 |
| 临时仿真文件 | 0 | 0 B | 4,096（空目录本身） |

整个记录根目录的文件合计 29,136,543 B，包含少量 collector/restoration 文件。SQLite `quick_check=ok`，foreign key errors=0；graph、spec、task、condition、模板、项目快照各仅一份。数据库同时保存所有失败 transition；只有符合现有 replay 契约的 transition 进入训练 buffer，淘汰 buffer 成员不会改变数据库。

完整 checkpoint 从持久化 transition 重建 replay 后，下一次采样、SAC update 结果及 actor 参数一致；这轮 checkpoint 的源码摘要匹配当轮代码，后续改码不会自动迁移旧 checkpoint。周期 checkpoint 由一个共享 learner 产生，保留两份；未运行固定 policy 验证，因此另一个文件明确标为 final_policy。

`MockBackend` 的输出附件很小；**这个附件体积不代表真实 Spectre 的波形大小**。真实附件仍受 256 MiB/run 数量与字节预算控制。测量也不代表 Spectre 提速或算法质量。

## 导出与产物

对完整 6000 条记录执行按需 Parquet+ZSTD 导出；逐条比较解码 evaluation 原始 score 与 Parquet float64 值，缺失值仍为 null。全部一致，transition/state 行数也核对。导出副本放在临时目录，核验后自动删除，没有长期保留第二份数据。

- [6000 次机器可读报告](../artifacts/local/recording-final-6000-report.json)
- [完整导出核验报告](../artifacts/local/recording-final-export-verification.json)
- 数据库、附件、checkpoint：`/tmp/gator-recording-final-6000-20260919/`（临时验收目录，长期使用应迁移至持久 ext4 存储）
- [配置示例](../configs/recording.example.json)
- [读取、导出、恢复及清理说明](experiment-recording.md)

上述离线轮次未做真实 VMware/Spectre 工作目录删除或真实波形验收；后续 16 次真实仿真、远端清理及 checkpoint 续跑结果见 [真实记录验收](recording-real-verification.md)。精确恢复覆盖 learner/replay；collector 从新 episode reset，不能接管半完成仿真。缺失波形无法事后生成未提取的指标；原有 PDK、模型及仿真环境仍是复跑前提。

## 重复 I/O 优化后的复验

完整回归 **411 passed，0 failed，0 skipped**，88.79 s。新增 8 项测试覆盖轻量入池拒绝篡改/未提交数据、事务回滚不能授权 replay、恢复时检测指纹不一致及旧行兼容、静态资产登记/状态写入次数、合并事务的持久化/存活进程门槛、清理删除后回滚的补齐、摘要无需扫描新 run 历史，以及 checkpoint 登记位置与文件一致。并行测试同时确认内置的构造期 recorder hook 不生成重复 config/candidates 文件。

又独立完成 **6000 次 mock evaluation**：run_id `8f390fc192d94f5d9c744f580798e3f6`，保存 5819 transitions、5940 states、180 次失败（各类 60 次），replay 容量 256，真实调用 0。learner/replay 精确恢复验证通过。本轮体积验收耗时 288.62 s，初段与完整测试并行，不能直接与历史轮次相减推导性能收益；隔离的开销对照见 [记录开销](recording-overhead.md)。

| 类别 | 文件字节数 | 约合 |
| --- | ---: | ---: |
| SQLite 数据库 | 25,780,224 | 24.59 MiB |
| journal / WAL | 0 | 0 B |
| 附件，3 份 | 2,850 | 2.78 KiB |
| checkpoint，2 full + 1 final policy | 3,750,574 | 3.58 MiB |
| 临时输出 | 0 | 0 B |

总文件占用 29,533,981 B，含少量 collector/restoration 文件。增加的 transition 指纹、分组计数和 workspace 索引也计入数据库，未宣称这些优化必然降低数据库文件大小。

运行中的 `summary --json` 已验证分组计数与提交总数一致；旧版 6000 条数据库也通过只读摘要兼容检查，得到 3880 次达标、1940 次未达标、180 次失败且无 pending。原数据库未迁移或删除。

- [优化后 6000 次报告](../artifacts/local/recording-optimized-6000-report.json)
- [数据库、checkpoint 和全量导出核验](../artifacts/local/recording-optimized-verification.json)
- [人工查阅摘要示例](../artifacts/local/recording-summary-example.txt)
- 新一轮产物：`/tmp/gator-recording-optimized-6000-20260919/`；长期保留仍需使用持久 ext4 目录。
