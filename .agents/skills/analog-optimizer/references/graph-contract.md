# 网表、CircuitGraph 与参数契约

以下是为本项目提出的实现契约，不是某个上游库已经存在的 schema。
实现前核对仓库，已有等价模型时做兼容适配，而不是平行重写。

## 1. 统一图的最小信息

建议使用独立于 PyTorch/Cadence 的 typed data classes 或现有 schema 库：

```text
CircuitGraph
  schema_version
  circuit_id / topology_id / source_manifest
  devices: Device[]
  nets: Net[]
  connections: TerminalConnection[]
  parameter_groups: ParameterGroup[]
  context: CircuitContext
  diagnostics: Diagnostic[]

Device
  id / instance_path             # 定位，不作可迁移语义 embedding
  kind / polarity / model_ref    # model_ref 为本地映射键
  raw_parameters / resolved_parameters
  parameter_valid_mask / source_span

Net
  id / hierarchical_name
  roles                         # ground, supply, input, output... 来源需记录
  source_span

TerminalConnection
  device_id / terminal_name / terminal_role / terminal_ordinal / net_id

ParameterGroup
  id / parameter_kind / unit / domain
  value / lower / upper / scale / legal_values_or_step
  members[] / binding_rules / mutable

CircuitContext
  ports / supplies / temperature / corner / analysis_context
  task_features / specification_set / schema_versions
```

`source_manifest` 记录 netlist/testbench 摘要、PDK 映射版本、解析器版本与输入来源。
公开或远端使用前按用户权限脱敏，不能把 model 文件内容作为普通特征上传。

## 2. 端口语义必须保真

首版选择 device-net 二部 multigraph，端口是连接关系的属性或关系类型。
不要同时无理由引入 device/net/port 三层节点；只有明确试验需要时再增加显式 port 节点。

MOS 示例关系：

```text
(device, d_to_net, net)     (net, net_to_d, device)
(device, g_to_net, net)     (net, net_to_g, device)
(device, s_to_net, net)     (net, net_to_s, device)
(device, b_to_net, net)     (net, net_to_b, device)
```

- 原图每个端口保留一条连接，再为消息传递生成方向明确的反向边。
- 某 MOS 的 S、B 都接同一地网时，两条连接仍不同。
- 对电阻、电容及源保留实际端口标签；只有明确对称的器件才允许对称化。
- 理想电源的正负端不能当成任意对称端口。
- 端口顺序由器件映射或 subckt 声明决定。不能只因实例名以 `M` 开头就假定 D/G/S/B。
- GND、VDD、输入/输出角色优先来自 `global`、声明、测试台配置或显式映射；启发式识别必须标记来源。
- 不同作用域同名局部 net 不能合并；全局网只能按显式规则合并。

## 3. Spectre parser 首版范围

先读取用户实际小网表，公开声明支持的语法子集，再写 fixture 驱动测试。
首版至少覆盖注释、空白、器件端口列表、参数赋值、普通数值/单位、基本 parameters 与 subckt 定义/调用。

解析要求：

- Tokenize 后保留文件/行号/原始值；不要把一串宽松正则当成支持全部 Spectre 的解析器。
- 明确支持的 dialect。`simulator lang=spice` 或混合语言必须分派到对应解析器，或报可定位错误。
- 数值单位按声明的 dialect 解释；不能把 SPICE 的大小写/后缀规则直接套给所有 Spectre 输入。
- 表达式使用白名单解析器或保留表达式；禁止 `eval()` 执行输入网表表达式。
- 未解析表达式为 unknown，不以 0 代替；真实参数回写前必须解决所需值与边界。
- `include` 受允许目录约束，处理相对路径、循环和深度限制；不递归展开加密/私有模型文件。
- 根据已解析的 subckt 定义判定调用，而不是只根据实例名前缀判断。
- 层次展开保留完整 instance path 和端口映射，区分局部与全局 net；递归或不支持的结构明确拒绝。
- 不把器件模型内部展开为无意义的大图；PDK 器件可作为映射后具有已知端口的原子器件。
- analyses、save、options、刺激源、DUT 与测试台范围有显式策略，不能静默丢弃影响任务的上下文。
- 无法解析时仍可输出诊断，但不能把 incomplete graph 用作已验证仿真/优化输入。

**Canonical 不等于完成了图同构规范化。** 按名称排序只能保证当前输入的确定性，不保证重命名后的同构 hash。
拓扑划分需要显式 topology lineage 或经检验的结构去重，不能只 hash 文本或排好序的名字。

## 4. 数值与特征

内部物理量用明确单位；长度、频率、功率等适当转换为统一单位，dB 等指标则保留定义并记录单位。
尺寸正值可用 log 域归一化；电压等有符号量用线性或另行定义的变换。

学习特征可包括器件种类/极性、当前参数、合法边界、可调 mask、网角色及经过验证的工作点信息。
工作点特征为可选项，不能在无 OP 结果时冒填真实值。

缺失值用有限占位数加 mask；mask 不能省略，也不能把占位零解释为物理零。
normalizer 在训练集拟合并随 checkpoint 保存；测试时不得以全体测试结果重新拟合。
未知类别使用显式 unknown 或报错策略；加载 checkpoint 时不偷偷扩充语义词表。

## 5. 参数组与动作映射

参数组是独立可调自由度，不等于一只 MOS。
同一器件可以有 W 和 L 两个组；同一个组可以约束多个器件的相同或比例绑定参数。

```text
group_g → binding 1: device_A.w = g
        → binding 2: device_B.w = 2 * g
```

每个组必须拥有非空、经过交叉约束检查的合法域；一条绑定的合法域应反推到组域。
要区分 per-finger width、total width、finger count、multiplicity，具体语义从本地 PDK 获得。
不要默认 `W × nf × m` 总是正确，也不要重复展开相同自由度。

器件绑定之外的偏置/全局参数必须有显式对象和关联位置，不塞进“最后几维固定动作”。
固定或派生参数不产生独立 stochastic action；依赖循环与矛盾约束必须报错。
动作回写使用可审计的 ID 映射，不依赖输入行顺序。

## 6. PyG 转换

`HeteroData` 支持分开的节点/边类型存储，可作为本项目的首选表示之一；见 [S4](sources.md)。
但不要为仅仅“用了 PyG”重构已验证的同构 typed graph。

转换函数需返回或保存：

```text
pyg_graph
node_id_maps / terminal_relation_vocabulary
parameter_group_index / member_bindings
feature_schema / masks / per_graph_context
```

要求：

- 预先定义类型词表与特征维度；缺某类边时输出合法空 tensor，而非 batch 时随机改变 schema。
- `edge_index` 是整数索引，浮点 features 有一致 dtype；逐类型验证索引范围。
- 不擅自用 edge coalescing 丢掉多端口信息；是否可合并必须经过关系语义测试。
- batch/unbatch 恢复参数组与器件绑定；对自定义索引检查 PyG 的 offset 行为。
- dense attention 时给每个图的 padding 与图间边界加 mask，不让不同样本互相 attention。
- 结构缓存只能复用同一拓扑/版本的连接；改变尺寸应刷新动态 features。

### 当前训练输入缓存

`SACLearner` 已默认启用两层 CPU LRU：2048 条完整观测输入、64 个静态拓扑模板。各编码器（当时六种，2026-09-26 起只剩 GT/RGCN/GATv2）共用同一机制，各 learner 独立持有；缓存不属于学习权重或 replay 原始记录。

- `TopologyTensorCache` 复用 kind/net roles/端口正反向边/ordinal/组绑定/mutable；有序节点、边、组、关系、绑定、schema 改变即失效。`to_pyg(..., topology_cache=cache)` 每次仍校验并刷新动态尺寸、mask、组域及来源/回写 metadata。
- `ObservationTensorCache` 复用完整原始输入、context 和组特征。键为完整 Observation 与 FeatureSchema/SpecSchema 的本地内容摘要，覆盖尺寸、目标、测量/mask、预算、status、origin、工况及来源，不能只用对象地址或 job ID。replay 深拷贝仍应命中；名字仅用于索引和回写一致性，不是学习语义或图同构证明。
- `batch_observations(..., cache=cache)` 每次拼接新 batch、调整索引并复制 opaque metadata；调用方修改返回张量或 metadata 不应污染缓存。静态模板对外返回独立张量。
- 容量按条目计，超限 LRU 淘汰；两项容量均设为 0 可关闭，`learner.input_cache.info()/clear()` 用于检查与释放。缓存淘汰/重启后允许重新转换，不承诺无限期“只转换一次”。
- 不缓存 embedding、attention、Q、动作或梯度；每次按当前参数执行网络前向/反向。带邻接缓存的算子必须关闭跨批缓存（已删除的 GCN 编码器用 `GCNConv(cached=False)`），避免混合拓扑误用上一批邻接。缓存不写入 checkpoint，冷恢复按需重建且下一步训练应精确一致。
- 真实候选的参数回读、网表导出/解析与一致性核验保留；这不是仿真结果缓存。转换阶段计时与完整 SAC 更新分别记录，不把训练端提速当成 Spectre 或端到端提速。

项目 `docs/input-tensor-cache.md` 记录接口、复现命令与验收；测试必须覆盖内容变更失效、混合 batch、返回值隔离、有限容量及六编码器缓存开/关的训练等价性。

### 当前 M1 神经网络视图

原 `to_pyg()` 保留 HeteroData；普通算子用 `graph.neural.to_homogeneous_pyg()`，已有单图 HeteroData 可用 `as_homogeneous()`。不需要构造 RL Observation。默认 `circuit-neural-v1`：

- `x[N,49]` float32：node type one-hot(2)、device kind one-hot(8)、参数值/有效/存在/可调各 8 列、net role(7)。使用 `node_feature_slices(schema)` 获取列，宽度为 `2 + K_device + 4P + R_net`，不随图大小变化。device/net 不适用字段填有限零，类型和缺失 mask 明确保留；不把原 device.x 的参数与 net.x 的角色按同一列混用。
- `edge_index[2,E]`、`edge_type[E]`、`edge_ordinal[E]` 均为 int64。relation 编号为 `2 * role_id + direction`（0=device→net，1=net→device）；正反向/并联端口不合并。`edge_attr[E,15]` 为 relation one-hot + log1p(ordinal)，`edge_weight[E]` 为单位权重。不能用端口类别编号冒充 GCN 连续边权重。
- GCN 消费 x/index/weight，RGCN 消费 x/index/type，GAT/GT 消费 x/index/attr；MLP 只处理节点特征并按组读取。普通 GCN 刻意忽略端口标签，但原图仍保存全部端口信息。（这里指通用 PyG 算子；优化器的编码器自 2026-09-26 起只有 GT/RGCN/GATv2，2026-09-30 同步。）
- 单图先转换，再 `batch_homogeneous([data,...])`，得到按图连续的节点 batch/ptr 和 group_x_batch/ptr。组绑定第一行按 G 偏移，第二行按全图 N 偏移；成员必须为 device，拒绝跨图边/绑定及不同 schema 混批。
- `dense_node_features()` 返回 `[B,Nmax,F]` 与 `[B,Nmax]` 布尔 mask，不截断节点。padding 不产生动作，attention/pooling 须使用 mask；固定长度展平 MLP 不因此变成通用拓扑模型。
- SAC 保留已有按类型学习投影及组归一化，只将端口边打包复用同一 `port_edge_tensors()`。其 all-devices-then-all-nets 排列与导出 batch 的按图排列不同，索引不得交叉使用。

验收需包含直接 PyG 算子前向/反向及单图/混合 batch 一致性、S/B 同网、空图/零组、缺失与真实零、dense mask、重排、动态特征刷新和实际导出网表快照。字段、命令与最新证据见项目 `docs/m1-neural-inputs.md`；不因导出成功而宣称真实电路迁移成立。

## 7. 必须提供的测试

1. MOS D/G/S/B、S 与 B 同网、多端口同网、反向边一致性。
2. 层次重复局部 net、subckt 端口映射、include 循环、混合语言拒绝、未知器件诊断。
3. 单位、表达式、缺失值、合法参数组、绑定域冲突、整数投影边界。
4. 两个不同大小/参数数量的图在同一个 batch 前后正确恢复；不存在跨图边。
5. 重命名/重排 fixture 保持结构等价与回写映射正确；绝不靠名字 embedding 过测试。
6. 模型阶段在 eval 模式比较置换前后的参数组输出和图级 Q；随机策略比较分布参数或受控随机样本。
