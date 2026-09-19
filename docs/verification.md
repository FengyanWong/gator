# First Coding Task 验收记录

日期：2026-09-19。执行目录：`/mnt/d/gator`。全部是离线 synthetic 验收。

本文件记录 M1 当时的验收状态。随后完成的真实 GPDK045 OTA 接入见 [M2 运放基线](opamp-baseline.md)；真实后端、尺寸回写/恢复及最新 103 项测试结果见 [M3 后端验收](opamp-backend.md)。

## 实际环境

| 项目 | 值 |
| --- | --- |
| Python | 3.10.12，WSL/Linux |
| 测试解释器 | `/tmp/analog-optimizer-venv/bin/python` |
| PyTorch | 2.14.0+cpu |
| PyTorch Geometric | 2.8.0.post1 |
| pytest | 9.1.1 |
| 项目 | 0.1.0，可编辑安装 |

初始系统 Python 没有 pip、Torch、PyG、pytest 或 `virtuoso_bridge`。标准 venv 的 ensurepip 不可用，因此仅在 `/tmp/analog-optimizer-venv` 引导 pip 并安装测试依赖；未修改系统 Python、未安装 bridge。

## 执行与结果

```bash
/tmp/analog-optimizer-venv/bin/python -m pip install --no-deps --no-build-isolation -e .
/tmp/analog-optimizer-venv/bin/python -m pytest -q
/tmp/analog-optimizer-venv/bin/python -m pip check
```

最终测试结果：**72 passed in 3.48s；0 failed，0 skipped**。Editable package 安装成功；`pip check` 返回 `No broken requirements found`。

覆盖：MOS D/G/S/B、同网多端口及反向边；配置驱动端口顺序；三个不同结构；层次局部 net、参数作用域与 override；include 越界/symlink/循环/深度；混合 dialect 和 unsupported statements 拒绝；大小写单位后缀；表达式白名单、未知值和非有限值；参数组合法域、整数投影、匹配/比例绑定、原始参数名回写；不同 graph/group 大小及零参数组的 PyG batch/unbatch、无跨图连接；synthetic 后端状态、指标缺失和唯一 job 目录。

首轮测试发现 `1e999` 在数值转换后可能变成名为 `inf` 的符号；已改为在 AST 解析前拒绝非有限字面量，并通过回归测试。

```bash
/tmp/analog-optimizer-venv/bin/python examples/netlist_demo.py \
  tests/fixtures/synthetic/opamp.scs --config configs/opamp.json \
  --mock-export /tmp/analog-optimizer-demo-jobs
/tmp/analog-optimizer-venv/bin/analog-graph-demo \
  tests/fixtures/synthetic/vco.scs --config configs/synthetic.json
PYTHONPATH=src python3 -m analog_optimizer.demo \
  tests/fixtures/synthetic/vco.scs --config configs/synthetic.json --no-pyg
```

三个 demo 命令均退出 0。前两个实际打印 PyG tensors；第三个在没有 Torch/PyG 的系统解释器运行成功。输出另存于 `/tmp/analog-optimizer-demo-opamp.txt` 与 `/tmp/analog-optimizer-demo-vco.txt`。PyG/Torch 导入时有上游 `torch.jit.script` 弃用 FutureWarning，未屏蔽，不影响上述退出码或结果。

实际转换计数：

| Fixture | Device | Net | Terminal connection | PyG directed edge | Parameter group |
| --- | ---: | ---: | ---: | ---: | ---: |
| opamp | 7 | 7 | 22 | 44 | 2 |
| ldo | 6 | 5 | 14 | 28 | 1 |
| vco | 10 | 8 | 32 | 64 | 0 |

## 未验证范围

- 当前 PATH 无 `virtuoso-bridge`、`virtuoso`、`spectre`；未核实其他主机或 Python 环境的安装情况。
- 未提供/读取 VM profile、PDK、许可证或真实网表。`virtuoso-bridge-lite` 的本地版本、真实调用签名、导出、参数回写、OP 和真实仿真均未验证。
- 未进行真实集成测试，没有以 synthetic 成功替代真实结果。
- 未实现 encoder、actor/critic、SAC、训练、surrogate 或泛化评估。该结果只证明本 README 声明的解析/图转换子集。

下一步：核对实际安装的 `virtuoso-bridge-lite` 版本与只读网表导出接口，选择一份获准的真实 Spectre 网表进行解析兼容性验收。
