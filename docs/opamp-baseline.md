# GPDK045 五管 OTA：真实基线验收

2026-09-19 已在现有 Cadence VM 中新建并仿真基础 OTA。原理图创建、CDF 参数回调、网表导出、真实 Spectre DC/AC、指标提取、负载扰动、原参数复跑及 PyG 转换均已执行。

## 电路与测试条件

| 项目 | 配置 |
| --- | --- |
| Library | `GATOR_TESTS`，绑定 `gpdk045` |
| 运放 | `ota5_v1/schematic`，另有生成的 `symbol` |
| 测试台 | `tb_ota5_ac_v1/schematic` |
| 结构 | M1/M2 NMOS 差分对，M3/M4 PMOS 电流镜负载，M5 NMOS 尾管 |
| M1/M2 | W=4 µm，L=0.5 µm，nf=1，m=1 |
| M3/M4 | W=8 µm，L=0.5 µm，nf=1，m=1 |
| M5 | W=4 µm，L=1 µm，nf=1，m=1 |
| 测试条件 | VDD=1 V，VCM=0.6 V，VBIAS=0.4 V，CL=1 pF |
| 模型 | GPDK045 v6.0，`g45n1svt` / `g45p1svt`，section `tt` |
| 温度与精度 | temp=tnom=27°C；reltol=1e-5，vabstol=1e-8，iabstol=1e-13 |
| AC | 10 Hz–1 GHz，60 points/decade；VINP=0.5∠0°，VINN=0.5∠180° |

这是用于验证优化链路的低电流单级 OTA。输入管的实测 VGS≈0.3845 V、VTH≈0.4538 V；当前工作点并非高过驱动偏置。没有进行尺寸优化，也没有设置已经满足的产品规格。

实际读取的 MOS CDF `termOrder` 为 D/G/S/B。所有 MOS 的 `w=fw`、`fingers=1`，以及扩散面积/周长已在正确调用 PAS 回调后读回核实。例如输入管 `ad=as=560 f`、`pd=ps=8.28 µ`；PMOS 的对应值为 `1.12 p`、`16.28 µ`。测试台使用 `gnd!`，导出后参考节点为 `0`。

## 测量结果

| 指标 | 原始 CL=1 pF | CL=1.1 pF | 恢复原参数复跑 |
| --- | ---: | ---: | ---: |
| 10 Hz 开环差分增益 | 25.000934 dB | 25.000934 dB | 25.000934 dB |
| −3 dB 带宽 | 198.288 kHz | 180.370 kHz | 198.288 kHz |
| 单位增益频率 | 3.527748 MHz | 3.209482 MHz | 3.527748 MHz |
| 单位负反馈相位裕度估计 | 92.099° | 92.200° | 92.099° |
| VOUT 直流 | 0.666759 V | 0.666759 V | 0.666759 V |
| VDD 电流 | 1.956295 µA | 1.956295 µA | 1.956295 µA |
| VDD 供电功耗 | 1.956295 µW | 1.956295 µW | 1.956295 µW |

增益使用 `VOUT/(VINP−VINN)`，未假定输入激励永远为 1 V。频率交点在 log(frequency) 上插值；没有交点返回 `None` 并标记无效，不填零。相位裕度是开环响应对单位负反馈的估计，**不是 STB 实测**。供电功耗不包含实际偏置发生器；VBIAS 当前为理想电压源。

![真实 Spectre AC 曲线](../artifacts/local/opamp-baseline/report/opamp_ac.png)

三次 Spectre 运行都退出 0，完整日志均报告 **0 errors / 0 warnings / 2 notices**。原参数两次执行网表 SHA-256 完全相同；关键指标在相对容差 `1e-6`、绝对容差 `1e-12` 下通过比较，本次保存的值实际一致。CL 变化只发生在该 job 的执行网表中，原始结构文件、原理图和导出包未改变。

| 运行 | job_id |
| --- | --- |
| 基线 | `ff6dc7e7c3944d77a0ace70da4d63385` |
| CL +10% | `70784ca0a0e44298b7f6efdd7fa124f4` |
| 原参数复跑 | `e89c0a254d034f8fa40fb0dcf7995c50` |

## 版本与证据

- 本地 Python/bridge：`/home/fyworkstation/virtuoso-bridge-lite/.venv/bin/python`，bridge **0.8.0**，commit `38aa8f22b2617e9b29e3b9f3a5770f27a938e1f0`，上游 checkout 无本次修改。
- Virtuoso：IC23.1-64b；Spectre：**23.1.0.242.isr1**。
- 完整导出、CDF 读回、原理图截图、模型入口/MOS 文件摘要、每次执行网表、PSF、日志及测量保存在 `artifacts/local/opamp-baseline/`。该目录已加入 `.gitignore`；PDK 模型没有复制入项目。
- [图转换摘要](../artifacts/local/opamp-baseline/graph_summary.json)、[重复性比较](../artifacts/local/opamp-baseline/report/comparison.json)、[原理图截图](../artifacts/local/opamp-baseline/ota5_schematic.png)。

初次导出的 `input.scs` 带有 PDK 默认 `section=mc` 且没有 AC 分析。本实验保留该原始文件，以包内原样的结构 `netlist` 为输入，另建 **TT DC/AC** 执行网表；没有将原始 ADE 设置直接当作基线。`examples/circuits/gpdk045_ota5.scs` 是修正后导出的结构快照，不包含模型定义。

上游 bridge 0.8.0 的 `result.status=success` 同时可能带有 `errors=["license error"]`：其 `runner.py` 把全文出现的 `license` 和 `error` 组合判断，连正常授权信息与 `0 errors` 也会匹配。项目保留这条原始诊断，并增加独立的退出码、完成摘要、显式错误标记与有限测量检查；其它未知诊断仍拒绝通过。此处不是实际许可证失败，也未修改上游代码。

PAS 回调修正依据实际 CDF/函数签名和 [Cadence 官方支持说明](https://community.cadence.com/cadence_technology_forums/f/custom-ic-skill/31459/what-s-the-difference-between-add-a-device-manually-and-dbcreateinst-it-caused-forminitproc-failed)：使用 instance CDF、调用 formInitProc，并保持 `cdfgForm=nil`。项目实现只适用于已验证的 GPDK045，不泛化为任意 PDK setter。

## 复现

以下命令在 `/mnt/d/gator` 执行，使用这台机器已经配置的环境；脚本参数可换为其它明确配置的路径。不会自动安装 bridge、启动 daemon 或修改连接 profile。

重新运行现有真实基线：

```bash
/home/fyworkstation/virtuoso-bridge-lite/.venv/bin/python -B \
  examples/simulate_opamp_baseline.py \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --structure examples/circuits/gpdk045_ota5.scs \
  --model-file /home/minlei/pdk/gpdk045_v_6_0/models/spectre/gpdk045.scs \
  --output artifacts/local/opamp-baseline/simulations
```

加 `--load-capacitance 1.1p` 可运行本次扰动实验。每次生成独立 UUID 目录；`latest_job.txt` 只在仿真和测量均成功后更新。测量读取失败可以对原 job 运行 `examples/analyze_opamp_baseline.py JOB_DIRECTORY`，无需重新占用许可证仿真。

重新导出已有测试台：

```bash
/home/fyworkstation/virtuoso-bridge-lite/.venv/bin/python -B \
  examples/build_opamp_baseline.py export \
  --env /home/fyworkstation/.virtuoso-bridge/.env \
  --library GATOR_TESTS --output artifacts/local/opamp-baseline
```

导出使用上游 `schematic.export_netlist()` / OCEAN，会改变当前 OCEAN simulator/design 选择；脚本在发现活动 ADE/Maestro 窗口时拒绝执行。单 worker 下使用专用测试台，保留每次导出包。

创建另一份独立电路时，使用 `create` 并指定新的 `--library`、`--remote-library-path` 和 `--output`。`configs/gpdk045_opamp_design.json` 包含器件尺寸和偏置；脚本遇到已有目标 cell 会直接拒绝覆盖。

离线图转换及测试：

```bash
/tmp/analog-optimizer-venv/bin/python examples/netlist_demo.py \
  examples/circuits/gpdk045_ota5.scs --config configs/gpdk045_opamp.json
/tmp/analog-optimizer-venv/bin/python -m pytest -q
```

本次最终结果：**89 passed，0 failed，0 skipped**。图有 **10 devices、8 nets、30 terminal connections、60 directed PyG edges、3 parameter groups**，无解析诊断。输入对、镜像对、尾管宽度各为独立组；当前组边界是下一阶段实验范围，尚未验证整段范围内所有尺寸都能仿真。

## 当前边界与下一步

目前完成的是单一 TT/27°C 的 DC/AC 基线和负载敏感性验证；未测瞬态、slew rate、噪声、失调、PVT/Monte Carlo、版图寄生或独立 STB。没有旧的手动/ADE 基线，因此建立了新基线并验证重复性。

后续已完成小范围匹配宽度回写、重新导出、执行参数验证和恢复，见 [后端验收](opamp-backend.md)。下一步实现 measurement evaluator 与 `reset/step`，用少量随机候选验证闭环。Graph Transformer/SAC 留到这条闭环可靠之后。
