# Sources and verification boundaries

Compiled and checked against public documentation on 2026-09-19.
User decisions come from recent chats; the graph schema, Backend Protocol, action-group interface, reward examples, tests and milestones in this package are project-specific conventions, **not verbatim specifications from original papers or upstream APIs**.
Call them "this project's design" when citing them, not "official requirements".

## S1 — OpenAI / Codex Skills

`https://developers.openai.com/codex/skills/`

At the time of checking, this redirected to the official `https://learn.chatgpt.com/docs/build-skills`.
It supports name/description in `SKILL.md`, optional references and `agents/openai.yaml`; the documented local project directory is `.agents/skills` and the user-level directory is `~/.agents/skills`.
The documentation says `$` can select a skill explicitly and description is used for automatic matching; restart Codex if an update does not appear.
This package's directory/installation instructions use that source and do not guarantee identical behavior in older client versions.

## S2 — Virtuoso bridge upstream

`https://github.com/Arcadia-1/virtuoso-bridge-lite`

Used to check the repository source, the separation of SKILL and standalone Spectre, configuration and official documentation locations.
This package has not copied the upstream implementation or connected to the user's machine; before making real calls, consult the locally installed version, upstream source signatures and `--help`.
Do not treat performance or platform claims in the upstream README as test results from this user's environment.

## S3 — Bridge package metadata

`https://raw.githubusercontent.com/Arcadia-1/virtuoso-bridge-lite/main/pyproject.toml`

The project name checked was `virtuoso-bridge`, with the console script pointing to `virtuoso_bridge.cli`.
This package does not pin a dependency version or infer an installation source from a same-named PyPI project.
Upstream main can change; actual run records should retain the installed version or commit.

## S4 — PyTorch Geometric HeteroData

`https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.data.HeteroData.html`

Used to verify support for storing multiple node/edge types. Parameter-group bindings, terminal multigraphs and extra batch indices must be implemented and tested by this project.

## S5 — OpenAI Spinning Up: Soft Actor-Critic

`https://spinningup.openai.com/en/latest/algorithms/sac.html`

Used to check the foundations of continuous SAC: stochastic actor, twin Q, target Q, tanh/reparameterization, entropy targets and replay updates.
The variable parameter groups, per-graph masks, automatic temperature scheme, cross-circuit training and discrete projection proposed in this package are not capabilities already supplied by that example implementation.
Do not paste its fixed-action-dimension code and claim support for variable topologies.

## S6 — PyG TransformerConv

`https://pytorch-geometric.readthedocs.io/en/latest/generated/torch_geometric.nn.conv.TransformerConv.html`

Used to check the scope of neighborhood attention and edge-feature support.
This is a message-passing graph operator; using this layer alone does not justify claiming implementation of an arbitrary global graph transformer or a particular paper.

## Material not verified in this package

The full texts/code of the 2023 Li analog circuit optimization work and DEGT paper mentioned in chat were not checked during preparation of this package.
This package does not include their exact experimental numbers, unconfirmed RL algorithms, surrogate use or claims of being "first".
For paper comparisons/reproduction, separately read the original papers and corresponding code, and record versions and citations.
