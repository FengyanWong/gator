# GATOR

**GATOR** stands for **Graph-Aware Transformer Optimizer for Reinforcement learning**. It is a research workbench
for sizing analog circuits: choosing device widths, lengths, multipliers and other parameters of a circuit whose
connectivity is fixed so that it meets its electrical specifications.

- **Graph-aware:** a circuit becomes a graph of devices and nets that keeps terminal identity, hierarchy and parameter
  bindings. Nothing about the circuit is flattened into a feature vector by hand.
- **Transformer:** a graph transformer encodes that graph. The encoder is a swappable part: a plain graph transformer,
  RGCN, GATv2, GraphGPS and GATOR's own CircuitGPS and parameter-group cross-attention are provided.
- **Optimizer:** the policy proposes one action per independent parameter group; actions are mapped to legal physical
  values with bounds, grids and integer domains before anything is simulated. A trust-region Bayesian optimiser
  (TuRBO-1) and a Pareto optimiser share the same evaluation interface, so learned and classical search can be compared
  on equal terms.
- **Reinforcement learning:** the policy is trained with Soft Actor-Critic from simulation results, online during a
  run or offline from an archive of earlier runs, and a trained model can be fine-tuned on a new task, a new process or
  a new circuit.

Every candidate design is evaluated by a real circuit simulator. GATOR drives Cadence Virtuoso schematics and Spectre
through the [virtuoso-bridge](https://github.com/Arcadia-1/virtuoso-bridge-lite) package, or ngspice netlists directly.
It records every evaluation, keeps real simulations inside an authorised budget, and writes data rather than reports.

GATOR was built for an MSc by Research at the University of Edinburgh's School of Engineering. Its experiments are
finished; the code stays usable, and this repository is its complete record.

## What is in the box

- **A browser workbench** ([frontend/](frontend/), served by [src/gator_workbench/](src/gator_workbench/)): read a
  circuit from Virtuoso or an ngspice netlist, edit its parameters, probes and specifications, start, pause, continue
  and audit runs, compare saved models, check a design at process corners, and ask a local language model for advice
  on settings. The [workbench reference](docs/workbench.md) describes every panel.
- **The optimizer library** ([src/analog_optimizer/](src/analog_optimizer/)): the netlist parser, the circuit graph,
  parameter actions, measurements and specifications, the reward, the encoders, SAC, replay and checkpoints, and the
  simulator backends. The [optimizer package](docs/optimizer-package.md) describes its contracts. Its source digest
  gates saved models and audits: a saved model loads only under the code and library versions it was saved with.
- **Research entry points** ([examples/](examples/)): the milestone scripts, benchmarks and audits behind the recorded
  results, some pinned by hash.
- **A development record** ([docs/](docs/README.md)): dated records of every change and experiment, the research
  decisions, plans with their outcomes, and frozen evidence. The [functionality reference](docs/functionality-reference.md)
  maps each feature to its code, tests and record.

## What the experiments found

In short: a model pretrained on related sizing tasks finds feasible designs sooner on a new task, and transfers across
a process change on two of three ported circuits, but it does not reliably find better designs than learning from
scratch, and on a published regulator Bayesian optimisation found more feasible designs than every SAC variant. Frozen,
unadapted models produced no feasible design anywhere. Against a shared archive of earlier designs, trust-region Bayesian
optimisation with that archive stayed the best fixed-target method across three seeds. The dated records under
[docs/](docs/README.md) hold the numbers; the manuscripts live in a separate private repository.

## Start

GATOR runs on Linux, including WSL, with Python 3.10 and Node.js. Real simulation needs a simulator host: Cadence
Virtuoso with Spectre reached through the bridge, or a local ngspice. Without either, the mock backend and the
recorded data still exercise the whole workbench.

```bash
python -m pip install -c constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
(cd frontend && npm ci && npm run build)
OMP_NUM_THREADS=1 PYTHONPATH="$PWD/src" python -m pytest -q -n 4 --dist loadgroup
PYTHONPATH="$PWD/src" python -m gator_workbench.cli serve --port 8765
```

Then open <http://127.0.0.1:8765/>. [constraints.txt](constraints.txt) pins the exact torch, torch-geometric, numpy
and networkx versions: saved models load only under the versions they were saved with, and `torch==2.14.0+cpu` exists
only on PyTorch's CPU index, so torch is installed from there first. The test command uses four workers; on a quiet
machine use twelve. Tests that need local evidence folders report a skip. The environment and the shared-machine
rules of the original setup are in the [workbench reference](docs/workbench.md#start).

## Repository map

| Location | What it holds |
|---|---|
| [src/gator_workbench/](src/gator_workbench/) | The backend: saved tasks, run control, the recorded data, the local Agent; see the [workbench reference](docs/workbench.md). |
| [src/analog_optimizer/](src/analog_optimizer/) | Circuit graphs, backend adapters and the learner; see the [optimizer package](docs/optimizer-package.md). |
| [frontend/](frontend/) | The React/TypeScript page and its browser checks. |
| [tests/](tests/) | Offline tests, controlled fakes and pinned fixtures. |
| [configs/](configs/) | Parser mappings and research configurations; audit-pinned files stay unchanged. Local settings are git-ignored. |
| [examples/](examples/) | Research entry points, benchmarks and audits. |
| [docs/](docs/README.md) | The document index: references, plans, frozen evidence and the development records. |
| artifacts/, outputs/ | Local evidence, run data, logs and saved models; git-ignored. |
| [.agents/](.agents/) | A skill with the research contracts, written for coding agents. |
| [CLAUDE.md](CLAUDE.md) | Working rules for the coding agents that helped build GATOR. |
| [pyproject.toml](pyproject.toml), [constraints.txt](constraints.txt) | Dependencies, commands and the exact model-compatible versions. |

[Project decisions](docs/decisions.md) holds the research contracts and their dated changes; the
[development index](docs/frontend_implementation_status.md) lists every workbench and experiment record.

## Status and limits

- The MScR experiments are complete (3 November 2026). Later changes are maintenance.
- The simulator side was built against one 45 nm generic PDK and one foundry PDK on a Cadence host; the foundry PDK's
  name and files are kept out of this repository.
- Real simulations, schematic writes and the local Agent's model downloads happen only on an explicit request from
  the page; nothing starts on its own.
- The local Agent tab runs an NVIDIA Nemotron model on the user's own GPU through a pinned llama.cpp build. It advises
  on parameters and run settings; its suggestions are checked and applied through the normal editor as one undoable
  change, and it never starts a simulation.
- The workbench, the records and this README were written with the help of coding agents; the project's records say
  what was done by whom and when.

## History

The milestone paragraphs of the first README and its reference sections are preserved unchanged in
[README history](docs/history-readme-milestones.md), with an English milestone table.
