# 记录链路重复读写检查

本次检查覆盖环境提交、SQLite writer、replay 入池/恢复、附件清理、checkpoint 和只读导出；不修改 reward、SAC 更新或真实参数核验。

| 已处理的重复工作 | 调整与正确性边界 |
| --- | --- |
| 每个 replay 样本重新加载 transition、前后 state 和静态图 | writer 在同一结果事务生成字段指纹；入池只读取小型 transition 元数据并验证已提交；恢复仍完整重建和核对 |
| 每次评价登记同一个 condition 和 simulator_version | 每个 recorder 用内容键缓存至多 32 个已确认持久化的资产 ID；版本/工况变化生成新 ID；重新 bind 清空缓存 |
| 已存在的资产/state 仍压缩并尝试 INSERT OR IGNORE | 先查内容 ID 是否存在，命中时不再压缩或写入；原始数值和精度不变 |
| 同一个 next_state 在 evaluation 和 transition 中各处理一次 | 单次提交内共享同一对象的已验证 state_id；不同对象仍独立验证，不能用相同尺寸推断状态相同 |
| 每次状态处理重复解压图/spec 并编码静态模板 | writer 使用至多 16 个不可变 graph/task 定义缓存；不缓存动态观测、embedding 或网络输出 |
| finish 内多次回读刚写入的 evaluation | 沿用事务内已验证的行和结果；提交失败仍不返回确认 |
| 同一次请求的登记和工作目录登记分别提交；清理标志也单独提交 | 请求与 owned workspace 在仿真前的同一事务登记；结果先独立提交并确认，再单独事务处理本地保留/清理元数据，减少每步落盘次数；保留存活进程检查及清理中断后的显式重试 |
| 生成每个清理 receipt 都查询数据库高水位 | 数据库 UUID 在 writer 启动时读取；高水位仅在 checkpoint/replay manifest 等需要处查询 |
| 附件选择把整个 run 配置及 evaluation 传回 worker | writer 返回当前保留角色和错误类型；结束确认、持久化 receipt、路径/进程检查继续执行 |
| 环境诊断里再次保存同一组 metrics/参数/工况 | diagnostics-v2 引用已有 result/request/condition 字段；保留诊断、投影和计时；动态 Observation 仍可精确重建 |
| checkpoint 保存后第二次生成 replay manifest | 数据库登记复用真正写入 checkpoint 的恢复位置，防止保存期间有新提交导致元数据前移 |
| 导出时为每条 evaluation 反复加载同一 task/spec 引用 | 收集不同 task ID 后各读一次；run 配置也只读一次，保持分批导出和一致快照 |
| 每次查看新 run 摘要扫描全部历史结果 | 状态/错误/来源/达标分组随结果事务累加；摘要只取少数候选与最近记录；历史格式保留只读兼容扫描 |
| 并行 factory 先创建旧 JSON 环境再挂 recorder，留下每 worker 的重复 config/图 | 内置 factory 用 `create_recorded(lane, recorder)` 在环境构造时接入；外部旧 factory 继续兼容，但需实现该可选 hook 才能避免其自行生成的旧配置文件，不擅自删除外部文件 |

保留的读写有明确用途：

- 仿真前登记请求、提交结果、fsync 和失败后的停止派发保证数据持久性。
- 实际参数回读与导出网表比对验证后端执行结果；不能由提议动作替代。
- 结果和 Observation 中的动态指标服务于不同的已验证契约，不按“看起来相同”删除恢复所需的数据。
- replay 的可变图深拷贝与入池契约校验防止调用者修改已收集样本；这属于内存隔离，不是再次落盘。
- checkpoint 的临时写入、文件哈希检查和实际反序列化验证，以及替换期间两份文件，保护上一份可恢复状态。
- final policy 只保留 actor 权重，方便独立加载；完整 checkpoint 则包含继续训练所需的其余状态。
- 目录容量扫描、文件系统剩余空间、归属和存活进程检查读取当前状态，不能用旧缓存替代安全判断。
- 大规模 Parquet 导出分多遍读取关系表以保持内存有界，是用户显式触发的离线操作，不进入每步训练路径。

性能证据使用 `examples/benchmark_recording_overhead.py`：报告原有 JSON、SQLite 完整回读和 SQLite 指纹入池三种路径，明确区分总记录成本与单独入池优化。新测试验证不回读动态状态、拒绝篡改/未提交数据、事务回滚、完整恢复指纹检查、历史格式兼容、静态登记/状态写入次数、摘要不扫描历史、checkpoint 恢复位置一致性。具体测量见 `recording-verification.md`；不据此声称真实 Spectre 加速。

清理若在文件删除后、元数据提交前中断，核心结果已在前一事务持久化。重试可将清理状态补齐；已经不存在的附件来源标记 `workspace_missing_after_cleanup_or_recovery`，不伪造 retained。未登记的孤立附件不猜测性删除，仍由目录预算计入占用。
