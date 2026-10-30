# GATOR

GATOR is a research workbench for sizing analog circuits with graph-based soft actor-critic learning.
Its browser page connects circuit tasks, the Parameters / Probes / Specs editors, run control and recorded data.
The Python optimizer supplies circuit graphs, parameter actions, measurements, learning and saved models.

## Start

Use these five commands from a new or independent checkout, with its own Python environment activated and Node.js
available. Environment creation and this machine's WSL setup are in [Start](docs/workbench.md#start).
The installation uses [constraints.txt](constraints.txt): exact saved-model recovery requires the recorded source and
library versions, including the CPU build of torch.

On the shared experiment machine, do not run these installation, build or serve commands against the live checkout
or its environment: they would change the installation, replace the served page or contend for port 8765.
Use the existing experiment session's startup procedure; a separate verification backend needs its own settings,
output root and unused port. Real simulations require an explicitly authorized budget.

```bash
python -m pip install -c constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
(cd frontend && npm ci && npm run build)
OMP_NUM_THREADS=1 PYTHONPATH="$PWD/src" python -m pytest -q -n 4 --dist loadgroup
PYTHONPATH="$PWD/src" python -m gator_workbench.cli serve --port 8765
```

Open [the local workbench](http://127.0.0.1:8765/) after starting it. The test command uses four workers while other
sessions may be busy; on a quiet machine use twelve. Tests needing absent local evidence report a skip.

## Repository map

| Location | What it holds |
|---|---|
| [src/gator_workbench/](src/gator_workbench/) | The backend, saved tasks, run control and data outputs; see the [workbench reference](docs/workbench.md). |
| [src/analog_optimizer/](src/analog_optimizer/) | Circuit graphs, backend adapters and the learner; see the [optimizer package](docs/optimizer-package.md). Its source digest gates saved models and audits. |
| [frontend/](frontend/) | The React/TypeScript page and browser checks. |
| [tests/](tests/) | Offline tests, controlled fakes and pinned fixtures. |
| [configs/](configs/) | Parser mappings and research configurations; audit-pinned files must stay unchanged. Local settings are ignored by Git. |
| [examples/](examples/) | Research entry points, benchmarks and audits; some scripts are pinned by the M5/M6 audits. |
| [docs/](docs/README.md) | The document index, current references, plans and frozen evidence. |
| [artifacts/](artifacts/) | Research evidence and local reviews; local scratch evidence is ignored by Git. |
| outputs/ | Generated run data, logs and saved models, ignored by Git. |
| [Private thesis repository](https://github.com/FengyanWong/gator-thesis) | MScR and PhD manuscripts, PDFs, figures, audit data and complete revision histories. |
| [.agents/](.agents/) | Repository skills and their research contracts. |
| [CLAUDE.md](CLAUDE.md) | Instructions for working beside other sessions and protecting experiments. |
| [pyproject.toml](pyproject.toml), [constraints.txt](constraints.txt) | Package dependencies, commands and exact model-compatible versions. |

Find a button, route, function or test in the [functionality reference](docs/functionality-reference.md).
Read [project decisions](docs/decisions.md) for the research contracts and their dated changes, and the
[development index](docs/frontend_implementation_status.md) for later workbench and experiment records.

## Current state

The workbench uses saved Virtuoso and ngspice tasks, produces data rather than reports, and keeps real runs within
an authorized budget. The optimizer supports `graph_transformer` (the default), `rgcn`, `gatv2`, `graph_gps`,
`group_cross_attention` and `circuit_gps`; [global encoders](docs/global-encoders.md) and
[CircuitGPS](docs/circuit-gps.md) describe the latter architectures. Exact resume requires the checkpoint's source
and dependency versions. M6 closed at pilot scale: the physical pipeline and its audit passed, but that pilot did
not establish a transfer or encoder advantage. [Project decisions](docs/decisions.md) records that boundary;
its dated summaries and the newer [development records](docs/frontend_implementation_status.md) keep each later
experiment's evidence and conclusions separate.

## History

The former README's fourteen milestone paragraphs and four reference sections are preserved unchanged in
[README history](docs/history-readme-milestones.md), with an English milestone table and working links to every
original reference. The current package contract is in [optimizer package](docs/optimizer-package.md).
