# 复制到 Codex 的首个任务

```text
$analog-optimizer

先读取该 Skill 的项目决策、图契约、后端契约和 M1 验收要求，并检查当前仓库与 AGENTS.md。

这是一个基于 Virtuoso/Spectre 和 virtuoso-bridge-lite 的模拟电路 sizing 项目。
后续方向是端口感知 Graph Transformer + goal-conditioned SAC，首版不加 surrogate、LLM 或 Mamba。

本轮只完成第一阶段：
1. 可测试的 Backend Protocol、结构化请求/结果，以及显式 synthetic 的 MockBackend。
2. 对已声明 Spectre 语法子集的解析器，保留来源位置并诊断不支持的输入。
3. 统一 CircuitGraph：device/net、D/G/S/B 连接、参数组、合法域、回写映射。
4. 转成 PyG，保留端口关系和可变参数组；两个不同大小的图可以正确 batch/unbatch。
5. synthetic netlist fixtures、单元测试和一个离线 demo。

先复用仓库已有代码，不重写已有的正常模块。
先核实本机 virtuoso-bridge 的安装位置、实际模块/签名，不编造上游 API。
没有真实 PDK、bridge 连接或许可证时先完成离线部分，明确哪些真实能力未验证。

必须测试 S/B 同网仍保留两种端口关系、层次 net 不误合并、未知器件/表达式不被静默丢弃、参数组映射与 PyG batch 不串图。

本轮不要实现 SAC 更新或完整训练器，不进行真实电路写操作、不启动昂贵仿真、不自动安装其他 skill。
给出实际运行的测试命令和结果，以及支持/不支持的解析范围。
```

当 M1 已经完成且通过验收，把本任务换成当前 milestone 的具体要求，不重复生成骨架。
