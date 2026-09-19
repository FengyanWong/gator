# 逐候选 CDF 与并行 Spectre 真实验收 — 2026-09-19

新版流程完成 **24 次真实 Spectre、18 条新 transition、16 次实际 SAC 更新**，三个阶段及最终审计均通过。每次候选（含 reset）均执行 CDF 回写、读回和原生导出，不读取预计算表，不使用候选缓存。默认及最大 Spectre 并发为 **4**；本轮四 worker 阶段观测到的 Spectre 并发峰值为 **2**。

## 范围与调用数

使用已有 receipt 核验的 `GATOR_TESTS` OTA 测试电路、GPDK045 v6.0、nominal TT/27°C/1.0 V 和原 smoke specs。动作仍仅为 M1/M2 匹配宽度 3.6–4.4 µm、5 nm 网格；L、fingers、multiplicity 和其他器件参数固定。bridge 为 0.8.0，真实日志保存 Spectre 版本 `23.1.0.242.isr1 64bit -- 7 Sep 2023`。

| 阶段 | 实际 worker | Spectre 调用 / CDF 准备 | 新 transition | 新 SAC 更新 | collector 时间 | Spectre 观测峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 单 worker：1 episode × 3 steps + reset | 1 | 4 / 4 | 3 | 2 | 16.88 s | 1 |
| 默认四 worker：4 episodes × 3 steps + resets | 4 | 16 / 16 | 12 | 11 | 25.93 s | 2 |
| 加载第二阶段 checkpoint，追加 1 episode | 1 | 4 / 4 | 3 | 3 | 16.16 s | 1 |

第三阶段保持默认 `max_workers=4`，只需一个新 episode，因此实际启动一个 worker。恢复后该训练链累计 20 次调用、15 条 replay、14 次更新；首个单 worker run 是独立训练。全部调用均已确认，失败、自动重试、不确定调用和缓存命中均为 0。审计未追加仿真。

每个阶段结束后再次连接 Virtuoso，只读比较完整 CDF 快照；三个阶段均与运行前完全一致，M1/M2 恢复到 4 µm。六次 reset 的原生执行网表摘要及全部测量与既有真实基线一致。PDK 入口和 MOS 模型文件的前后 SHA-256 也与基线记录一致。

## 并行与耗时证据

通过虚拟机 `/proc` 约 25 ms 间隔采样，三个阶段分别取得 834、1099、776 条记录，覆盖全部 24 个 Spectre 调用的进程身份。四 worker 阶段有 45 条采样看到两个 Spectre 同时运行，未观测到超过上限 4 的情况。本轮未实测四个 Spectre 同时运行，不能把 worker 数当成实际占用峰值。

四 worker 阶段每候选平均准备耗时 1.843 s（包含 1.093 s 排队），其中参数回写/读回 0.170 s、netlisting 0.398 s；仿真与测量平均 0.981 s。这些时间有嵌套，不能相加作为总耗时。按本机 CDF journal 完成时间及历时估算的区间内，有 58 条采样同时记录了运行中的 Spectre；该重叠诊断含 SSH 传输延迟，不是精确同步的时间轨迹。

collector 时间包括准备服务及 worker 的运行、记录、清理和恢复，未覆盖入口的全部模型初始化及最终 checkpoint 保存。三阶段预算不同，本轮属于工程闭环验收，不是配对吞吐或加速比实验，也不证明训练收敛、迁移优势或四路满载能力。

## 数据、网表与恢复审计

- 24 个候选、导出和仿真 job ID 均独立。逐条核对模型提议合法化、实际 CDF 参数、网表摘要、图观测、匹配关系及派生 geometry；CDF 回写 journal 全部为 `applied`，准备次数与真实调用数相等。
- 独立重算 reward、有效性和达标判定；18 条 transition 的前后状态、proposal、实际参数、worker/episode 归属及终止标记一致，没有跨环境串接。
- 三个最终 checkpoint 均按数据库保存的完整实验配置重载，并重建 replay。重复加载后的下一次采样指纹、loss、actor、critics、targets、alpha 和三个 optimizer 状态完全一致。审计更新仅在内存执行，不计入上述 16 次实际训练更新。
- 本次配置将 checkpoint 间隔设为 2 步以验证轮换，产品默认仍为 500 步。每个 run 保留 2 full checkpoint + 1 final policy，已淘汰文件实际不存在。
- 每个 run 保留 initial、best 两份附件，共六份。逐份核对原生顶层 `package/netlist` 与导出 manifest 摘要、CDF readback、导出参数和两份执行网表，并确认测量及 AC/DC PSF 文件存在且与数据库一致。
- 24 个本地、24 个远端 owned workspace 均已清理；远端 scratch 只剩根目录归属标记与锁，没有本轮遗留 Spectre。SQLite `quick_check=ok`、foreign key errors=0、pending=0。

数据库、checkpoint、附件及中文摘要保存在持久 WSL ext4：

```text
/home/fyworkstation/gator-records/native-cdf-real-31afdfba86bb/
```

审计时记录根目录约 12.21 MiB：SQLite 573,440 B、附件 1,012,225 B、checkpoint 11,210,314 B、其他摘要 10,064 B；journal 和临时数据为 0。另有工作区中的验收日志和 bridge 恢复 journal，不计入该目录容量。

本次没有修改生产 Python 源码。新流程已有完整离线回归 **426 passed、0 failed、0 skipped**；本轮补充真实验证，未重复整套离线测试。验收不扩展动作域、PVT/MC、真实新拓扑或 M6；checkpoint 续跑仍从新 episode reset 开始，不接管在途仿真。

## 复现与证据

使用[并行入口](parallel-spectre-sac.md)的连接、receipt、模型和参考测量参数，并设置 `--steps-per-episode 3 --warmup 2 --batch-size 2`。三个阶段依次为 `--max-workers 1 --episodes 1`、`--episodes 4`、`--episodes 1 --resume CHECKPOINT`；后两阶段故意不传 `--max-workers`，验证默认值 4。各阶段共用同一记录数据库；源码、schema、配置和依赖必须保持一致。

本机验收脚本包含此次机器的路径和连接配置，运行会新建一组记录并执行 24 次真实仿真：

```bash
/tmp/analog-optimizer-venv/bin/python -B \
  artifacts/local/native-cdf-real-acceptance/run_acceptance.py
```

仅重新审计已保存结果、不会调用 Spectre：

```bash
/tmp/analog-optimizer-venv/bin/python -B \
  artifacts/local/native-cdf-real-acceptance/audit.py \
  artifacts/local/native-cdf-real-acceptance/31afdfba86bb
```

- [总验收记录及完整命令](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/acceptance.json)、[最终审计](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/audit.json)
- [单 worker 报告](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/single/067b791772184f9a8cbe202c09f95062/report.json)、[四 worker 报告](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/parallel/f351640b37ce4570872dcc6838dc96e2/report.json)、[续跑报告](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/resumed/9758f4f3136b491291bc71590c3f2a97/report.json)
- [运行前快照](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/before.json)、[最终恢复快照](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/resumed-restoration.json)、[四 worker 进程采样](../artifacts/local/native-cdf-real-acceptance/31afdfba86bb/parallel-process-monitor.jsonl)
- [真实验收脚本](../artifacts/local/native-cdf-real-acceptance/run_acceptance.py)、[只读审计脚本](../artifacts/local/native-cdf-real-acceptance/audit.py)、[此前完整离线回归](../artifacts/local/native-cdf-regression-tests.xml)

以上本机产物保留用于复查，未上传 PDK、网表或波形。
