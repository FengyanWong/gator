# 真实后端适配与尺寸闭环验收

2026-09-19：已实现 `VirtuosoBridgeBackend`，并通过真实 M1/M2 匹配宽度 **4 → 4.4 → 4 µm** 的回写、导出、Spectre DC/AC、指标提取和恢复验收。

这是面向已验证 GPDK045 五管 OTA 的单 worker 适配器，尚不是任意电路/PDK 的通用后端。本报告记录最初的尺寸循环；后续 `reset/step` 与随机候选验收见 [环境报告](opamp-environment.md)。

## 与 virtuoso-bridge-lite 的边界

| 操作 | 实际执行方 | 项目增加的契约 |
| --- | --- | --- |
| 连接/关闭 | `VirtuosoClient.from_env()` / `close()` | 要求已有 tunnel；固定配置；不调用 warm、ensure_ready 或 stop |
| 读原理图 | `client.schematic.read()` | 显式 library/cell；检查 master、端口、固定尺寸和参考状态 |
| 改 MOS 尺寸 | `client.execute_skill()` | 复用已验证 GPDK045 PAS 回调；检查点、匹配约束、CDF 读回和恢复 |
| 导出 | `client.schematic.export_netlist()` | 独立目录；核对固定拓扑、其它器件参数和执行尺寸；保存完整导出包 |
| 仿真 | `SpectreSimulator.from_env().run_simulation(deck)` | 参数必须已经写入并验证网表；独立执行副本；不可变摘要与请求绑定 |
| PSF/测量 | 上游 PSF reader + 项目 AC 指标函数 | 原始诊断保留；检查实际完成证据和必需指标；明确单位、有效性及来源 |

没有修改上游安装。验收后检查上游 Git checkout 仍然干净，commit 为 `38aa8f22b2617e9b29e3b9f3a5770f27a938e1f0`，版本 0.8.0。新适配器显式拒绝未经复核的其它版本。

`SimulationRequest.parameters` 仅用来核对该导出已执行的尺寸，不直接透传给上游同名的 `params`。后者不是晶体管尺寸回写 API。`SimulationRequest.analysis` 当前不接受覆盖；真实验收使用原有 TT、27°C 和 DC/AC 设置。后续 M3 扩展支持显式 typed 工况和 job 内电源/温度/model section 准备，新增路径仅经过离线验收；见 [PVT／MC 接口说明](pvt-mc-interfaces.md)。

## 已验收的结果

| 指标 | 4 µm | 4.4 µm | 恢复 4 µm |
| --- | ---: | ---: | ---: |
| 10 Hz 增益，dB | 25.000934 | 25.030739 | 25.000934 |
| −3 dB 带宽，kHz | 198.288172 | 200.217191 | 198.288172 |
| 单位增益频率，MHz | 3.527748 | 3.574150 | 3.527748 |
| 相位裕度估计，° | 92.098575 | 92.068275 | 92.098575 |
| VDD 功耗，µW | 1.956295 | 1.961415 | 1.956295 |

相位裕度仍是开环响应下单位负反馈估计，不是 STB 实测；功耗仍不含理想偏置源对应的实际偏置发生器。

M1/M2 的 `w=fw` 确实由 4 µm 变为 4.4 µm。对应 `ad/as` 从 560 f 变为 616 f，`pd/ps` 从 8.28 µ 变为 9.08 µ，`nrd/nrs` 从 35 m 变为 31.8182 m；恢复后这些值全部回到初始值。导出网表与实际 CDF 读回一致，其它器件的参数及连接保持参考值。

三次原生 Spectre 日志均为退出码 0、0 errors、0 warnings、2 notices。保留上游 0.8.0 的 `license error` 误报诊断，通过已有独立完成验证器判定；没有把所有许可证错误忽略掉。

首末执行网表 SHA-256 都为 `f7c3a7d9367f64cdeb033563aea65fc0f236a518cabfd49d7eb3372d811610e2`，与上一阶段真实基线也相同。4.4 µm 网表摘要为 `26a2661310d8c01508bebf66a1dfd63fd761d3ff8bd0fc71d029ba1d9c85fd72`。首末指标在相对容差 `1e-6`、绝对容差 `1e-12` 下通过重复性检查，本次保存值实际相同。

- [机器可读验收报告](../artifacts/local/opamp-backend/9b2dff4cb98f484799001fd20d571eab/verification.json)
- [恢复记录及 CDF 读回](../artifacts/local/bridge-state/5c63b01c21e34814aaae2b85f61680bb/restoration.json)
- 运行 job：基线 `2c9fb05d4618482b9bcb76f676e48c09`，增宽 `272b24f3b6294034abad68edfa256f64`，恢复 `1165a8dd0e6648a38cd1ea8698de2b9e`。

报告旁保存三份完整导出包、执行网表、原始 bridge 结果、Spectre 日志、PSF、AC CSV、指标和工作点。`artifacts/local/` 仍被 Git 忽略。

## 使用和恢复

关键实现：

- `src/analog_optimizer/backends/virtuoso_bridge.py`：适配器、任务隔离、生命周期、记录。
- `src/analog_optimizer/backends/gpdk045.py`：当前电路的固定约束、CDF 回调和网表校验。
- `src/analog_optimizer/measurements/opamp.py`：从基线脚本提取的实际测量逻辑。
- `examples/circuits/gpdk045_ota5.cdf.json`：先前真实 CDF 读回的最小参考快照，不包含模型定义。
- `examples/verify_opamp_backend.py`：只读检查及完整尺寸循环。

在当前已配置机器上复跑：

```bash
/home/fyworkstation/virtuoso-bridge-lite/.venv/bin/python -B \
  examples/verify_opamp_backend.py cycle \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS \
  --creation-receipt artifacts/local/opamp-baseline/creation.json \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --reference-measurements artifacts/local/opamp-baseline/simulations/ff6dc7e7c3944d77a0ace70da4d63385/measurements.json \
  --output artifacts/local/opamp-backend
```

改为 `inspect` 并省略 `--reference-measurements`，仅连接和核对初始状态，不回写或仿真。

适配器使用 Linux/WSL 的文件锁以及进程内独占锁。同一项目的调用者必须使用相同 `state_root`；一个后端只允许其创建连接的线程调用。关闭时释放自己的客户端资源，并恢复自己绑定前的环境配置；不关闭共享 tunnel。

每次回写前保存 pending 日志和完整读回；部分失败会尝试回滚。`restore()` 和上下文退出会恢复初始宽度并核对派生参数。若恢复失败，保留 `recovery_required` 和异常，不宣称恢复成功。断电、强制杀进程或网络永久中断无法保证自动恢复，需要按初始记录恢复后再连接。新会话要求设计与已验证参考尺寸一致。

## 验证边界

- **103 项离线测试通过，0 失败、0 跳过。** 覆盖半途回写失败、CDF 派生值未更新、恢复失败记录、配置变化、文件/进程锁、活动 ADE、网表被修改、参数不匹配、超时、缺失指标/PSF 和无效工作点。故障注入使用明确的测试替身，不代表在 VM 上制造过这些故障。
- 三次真实宽度循环已运行；没有运行随机搜索、SAC、PVT 或瞬态。
- 仅开放 M1/M2 的完整匹配宽度组。软件暂定允许 3.6–4.4 µm；真实验收点只有 4 和 4.4 µm，不宣称整个范围均已验证。
- 文件锁仅约束本项目配合使用锁的进程，不能阻止用户 GUI 或其它 bridge 脚本修改同一会话。OCEAN 导出仍会改变会话选择，且活动窗口检测不能证明不存在后台 ADE 会话。使用专用会话，并避免同时操作该设计。
- 未能可靠归因的上游失败保守记为 `backend_error`，不会直接作为劣质尺寸样本；没有盲目重试，也没有 mock 降级。
- 模型入口路径、corner、温度与执行摘要均记录；没有新增递归 PDK 内容指纹。此前模型入口/MOS 文件摘要仍在基线记录中。

后续已完成单 worker `reset/step`、规格评价和随机候选，并补充 5 nm 宽度网格、失败时的尝试读回快照和经过摘要检查的导出图接口；见 [环境报告](opamp-environment.md)。M3 工况接口验收后，用户继续授权模型与训练，最新进展见 [M4 验收](m4-graph-sac.md)。
