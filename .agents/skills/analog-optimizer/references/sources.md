# 来源与核实边界

整理与公开文档核对日期：2026-09-19。
用户决策来自近期聊天；本包中的图 schema、Backend Protocol、动作组接口、奖励示例、测试与阶段是针对项目编写的约定，**不是原论文或上游 API 的逐字规范**。
引用这些约定时应称“本项目设计”，不要称“官方规定”。

## S1 — OpenAI / Codex Skills

`https://developers.openai.com/codex/skills/`

核对时跳转至官方 `https://learn.chatgpt.com/docs/build-skills`。
支持 `SKILL.md` 的 name/description、可选 references 和 `agents/openai.yaml`；文档列出的本地项目目录为 `.agents/skills`，用户级为 `~/.agents/skills`。
文档说明可显式用 `$` 选择，description 用于自动匹配；更新未出现时重启 Codex。
本包的目录/安装说明依据该来源，不保证旧版本客户端行为完全相同。

## S2 — Virtuoso bridge 上游

`https://github.com/Arcadia-1/virtuoso-bridge-lite`

用于核对仓库来源、SKILL/standalone Spectre 分离、配置与官方文档位置。
本包没有复制上游实现或接入用户机器；真正调用前以本地安装版本、上游源码签名和 `--help` 为准。
不要把上游 README 的性能或平台表述直接当作本用户环境的测试结果。

## S3 — Bridge 包元数据

`https://raw.githubusercontent.com/Arcadia-1/virtuoso-bridge-lite/main/pyproject.toml`

核对的项目名为 `virtuoso-bridge`，console script 指向 `virtuoso_bridge.cli`。
本包不固定依赖版本，也不基于同名 PyPI 项目猜安装来源。
上游 main 会变化；具体运行记录应该保存安装版本或 commit。

## S4 — PyTorch Geometric HeteroData

`https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.data.HeteroData.html`

用于核对多类型节点/边存储能力。参数组绑定、端口 multigraph 和 batch 额外索引是本项目需要自行实现与测试的部分。

## S5 — OpenAI Spinning Up: Soft Actor-Critic

`https://spinningup.openai.com/en/latest/algorithms/sac.html`

用于核对连续 SAC 的 stochastic actor、双 Q、target Q、tanh/reparameterization、熵目标和 replay 更新基础。
本包提出的可变参数组、per-graph mask、自动温度方案、跨电路训练和离散投影不是该示例实现已提供的能力。
不要直接把其固定动作维度代码粘贴后声称支持可变拓扑。

## S6 — PyG TransformerConv

`https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.TransformerConv.html`

用于核对邻域注意力与 edge features 的支持范围。
它属于 message-passing 图算子；仅使用此层不能声称实现了任意全局 graph transformer 或某篇特定论文。

## 未在本包中核实的材料

聊天里提到的 2023 Li 模拟电路优化工作和 DEGT 论文没有在本次制作中完成全文/代码核对。
本包不写入它们的精确实验数字、未确认的 RL 算法、surrogate 使用情况或“首次”结论。
要写论文对比/复现，另行阅读原论文与对应代码，并记录版本和引用。
