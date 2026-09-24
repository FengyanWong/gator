# analog-optimizer — Codex 项目 Skill

版本：0.3；同步日期：2026-09-22。
按照近期模拟电路优化讨论编写，保留当前方向：**端口感知 Graph Transformer + goal-conditioned SAC + Virtuoso bridge / Spectre**。
默认**不加 surrogate、LLM、Mamba**。项目已完成 M1–M5 与编码器接口（MLP/GCN/RGCN/GAT 与默认 GT 的统一 SAC 迁移对照，port-GNN 已于 2026-09-24 删除）；M6 已于 2026-09-20 以试点规模收尾（流程跑通并经独立审计，迁移或 GT 优势未得出结论）。此后的工作是 Web 工作台（`src/gator_workbench/`、`frontend/`）。最新状态以仓库的 `docs/decisions.md`、`CLAUDE.md` 与 `docs/workbench.md` 为准；[项目决策](references/project-decisions.md) 记录研究侧的约定。

本包是给 Codex 的指令和参考材料，**不是优化器代码、已训练模型或已接通的 Virtuoso 插件**。
安装不会安装 Python 依赖、连接 VM、修改原理图或运行 Spectre。

## 文件

```text
analog-optimizer/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── project-decisions.md
│   ├── graph-contract.md
│   ├── bridge-backend.md
│   ├── learning-and-actions.md
│   ├── evaluation.md
│   ├── pvt-monte-carlo.md
│   ├── milestones.md
│   └── sources.md
├── assets/
│   └── icon.svg
└── README.zh-CN.md
```

主 Skill 指向按任务加载的参考文件，不需要每次把整个包复制到聊天框。
没有第三方 skill 的必装依赖；其中的 review 清单是针对本项目单独编写的。

## 安装：优先项目级

官方当前的本地发现目录和调用方式见 [S1](references/sources.md)。
把 zip 中完整的 `analog-optimizer` 文件夹放到**实际在 Codex 打开的项目根目录**的 `.agents/skills/` 下：

```text
你的项目/.agents/skills/analog-optimizer/SKILL.md
```

不要只复制主文件，否则按需引用的规范文件会缺失。
不要多套一层 `analog-optimizer/analog-optimizer/`。
若同名 Skill 已存在，先比较或备份，不直接合并覆盖。

### WSL / Linux

在实际项目根目录打开终端。下面示例假定 zip 已放进 `~/Downloads`；Windows 下载的文件可能需要从 `/mnt/c/Users/.../Downloads` 指向真实路径。

```bash
mkdir -p .agents/skills

if [ -e .agents/skills/analog-optimizer ] || [ -L .agents/skills/analog-optimizer ]; then
  printf '%s\n' '目标已存在；请先检查或备份，不覆盖。'
else
  unzip "$HOME/Downloads/analog-optimizer-skill.zip" -d .agents/skills
fi
```

也可以通过文件管理器手动解压复制，不要求一定使用 unzip。

### Windows PowerShell

在实际项目根目录打开 PowerShell，下载位置不同时修改 `$zip`：

```powershell
$zip = Join-Path $HOME "Downloads\analog-optimizer-skill.zip"
$dest = Join-Path (Get-Location) ".agents\skills"
$target = Join-Path $dest "analog-optimizer"

if (Test-Path -LiteralPath $target) {
    throw "目标已存在；请先检查或备份，不覆盖。"
}
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath $dest
```

WSL 用户目录、Windows 用户目录和 VM 用户目录不同。按实际使用 Codex 的环境安装；不能假定装在一个 HOME 中就会自动出现在另一个环境。
共享同一仓库时检查实际项目路径和文件可读性。

## 所有项目使用

可把同一个文件夹放到运行 Codex 环境的 `~/.agents/skills/`。
本次核对的官方用户级路径是 **`~/.agents/skills`**，不沿用早先聊天中把 `~/.codex/skills` 当作当前首选位置的写法。
同名 Skill 不会自动合并，通常只选项目级或用户级一种安装，避免重复入口。[S1](references/sources.md)

## 使用

在 Codex 中输入 `$analog-optimizer`，再写具体任务。
CLI/IDE 的 skill 选择方式及自动匹配由当前客户端支持情况决定；新文件未出现时重启 Codex。[S1](references/sources.md)

已有项目从当前阶段继续。也可以直接要求审查，例如：

```text
$analog-optimizer
审查当前 graph builder 与 actor/critic：检查端口信息是否进入模型、参数组数量变化是否支持、critic 是否真的读取动作。给出代码位置、具体问题和可运行测试，不修改真实电路。
```

## 尚未确定的参数

本包不填造 PDK 器件名、W/L 范围、SSH 账号、IP、仿真路径、规格目标、温度、corner 或训练预算。
示例配置中的 null 和空列表是需从仓库/环境补齐的契约，不是声称可直接启动的配置。

当前项目已采用局部端口注意力、可配置网络规模、绝对 normalized proposal 与合法化投影；它们是已落地的工程选择，不表示优于其他方案。编码器接口、MLP 消融定义及 checkpoint 边界见 [学习契约](references/learning-and-actions.md)，对照公平性见 [实验规范](references/evaluation.md)。

## 修改与版本

项目架构发生变化时，优先更新仓库里的决策记录和项目级 Skill。
本包不应优先于用户最新明确要求、上层指令或仓库现有权限控制。
真实 bridge 接口始终以本地安装版本与经核对的源码为准。[S2–S3](references/sources.md)

## 验证边界

包格式、YAML、内部引用可以离线检查；Codex 的实际触发效果、用户仓库兼容性和真实 Virtuoso/Spectre 运行必须在相应环境验收。
本包不携带 PDK、凭据、可执行脚本、第三方源码或虚构的实验结果。
