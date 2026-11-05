# GATOR

GATOR sizes analog circuits. Give it a circuit whose connections are fixed, the values it may change (device widths,
lengths, multipliers and the like) and the specifications to meet. It proposes values, simulates every proposal in a
real circuit simulator, and learns from the results.

![How GATOR sizes a circuit: the circuit, its sizes and the specifications are read as a circuit graph; a graph
encoder and policy propose device sizes, which are moved to legal values and simulated; the measurements and the
reward go back to the policy, which learns from them.](docs/images/sizing-loop.svg)

The name stands for **Graph-Aware Transformer Optimizer for Reinforcement learning**:

- **Graph-aware:** the circuit is read from its netlist as a graph of devices and nets. The graph keeps which
  terminal of a device touches which net (a gate is not a drain), the hierarchy, and which devices share a value.
- **Transformer:** a neural network reads that graph, by default a graph transformer. This encoder can be swapped;
  six are included.
- **Optimizer:** each step proposes one value per independent parameter (matched devices share one). Every proposal
  is moved to a legal value, inside its bounds and on its grid, before it is simulated.
- **Reinforcement learning:** the network learns by trial and error from the simulation results, with the Soft
  Actor-Critic algorithm (SAC), during a run or from an archive of earlier runs. A trained model can then be trained
  further on new specifications, another process or another circuit.

Two classical searches can take the network's place in a run, for comparison on equal terms: a trust-region Bayesian
optimiser (TuRBO-1) and a Pareto optimiser.

The simulator is Cadence Spectre on Virtuoso schematics, reached through the
[virtuoso-bridge](https://github.com/Arcadia-1/virtuoso-bridge-lite) package, or the free ngspice on SPICE netlists.
Every simulated design is recorded, and a run never simulates more designs than you approved when you pressed Start.

GATOR was built by Fengyan Wang for an MSc by Research at the University of Edinburgh's School of Engineering. The
experiments are finished and the code stays usable. This repository holds the code and the written record; the run
data, the saved models and the thesis are not in it.

## What the experiments found

A design *passes* when it meets every specification, and a run normally had 800 simulated designs. In short: reusing
a trained model helps once it is trained further on the new task, and how much depends on the task.

- **New specifications, same circuit:** a model pretrained on two related tasks reached passing designs earlier on
  three analog circuits and a flip-flop; on the regulator and the flip-flop a run from scratch found none
  ([records 7.310 and 7.314](docs/workbench-log/7.301-7.323.md)).
- **Another process:** models trained in the generic 45 nm PDK raised the share of passing designs among the first
  hundred from 3 % to 60-66 % on an amplifier and from 2 % to 29-41 % on a ring oscillator moved to a second PDK; on
  a regulator almost nothing passed from any start. In the reverse direction only the amplifier gained
  ([record 7.329](docs/workbench-log/7.324-7.335.md), [record 7.454](docs/workbench-log/7.439-7.459.md)).
- **A circuit the model had not seen:** a general model, trained on the recorded designs of several circuits, raised
  that early share from 21 % to 79 % on a telescopic amplifier ([record 7.330](docs/workbench-log/7.324-7.335.md)).
- **Not better final designs:** a run from a trained model usually ended level with a run from scratch, and on the
  ring oscillator its best designs used about twice the power.
- **No use without that further training:** a trained model that only proposed designs passed with none of 300 on
  every circuit moved to another process and on four circuits from a published study.
- **Bayesian optimisation was stronger on a published regulator:** 337 to 396 passing designs of 800, against at most
  264 in any SAC run ([record 7.318](docs/workbench-log/7.301-7.323.md)). Given a shared archive of earlier designs,
  it also stayed the best method for a fixed target over three seeds
  ([record 7.453](docs/workbench-log/7.439-7.459.md)).

Most comparisons have one to three runs per arm, and every evaluation is a nominal schematic simulation.
[The experiments in plain words](docs/plan-transfer-experiment.md#1-in-plain-words) lists the questions asked.

## Start

GATOR runs on Linux, WSL included, with Python 3.10 and Node.js (18, or 20 and later; 24 was used). Training uses the
CPU build of PyTorch, so no GPU is needed. Use a virtual environment of your own; it grows to about 1 GB.

```bash
git clone https://github.com/FengyanWong/gator.git && cd gator
python -m pip install -c constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
(cd frontend && npm ci && npm run build)
OMP_NUM_THREADS=1 PYTHONPATH="$PWD/src" python -m pytest -q -n 4 --dist loadgroup
PYTHONPATH="$PWD/src" python -m gator_workbench.cli serve --port 8765
```

Then open <http://127.0.0.1:8765/>. On a fresh clone (5 November 2026) these commands ran as written: about 2,850
tests passed in three minutes and 35 to 40 were skipped, because they read evidence folders that are not in the
repository or need ngspice, BoTorch or the bridge. [constraints.txt](constraints.txt) pins the exact torch,
torch-geometric, numpy and networkx versions, because a saved model loads only under the versions it was saved with;
`torch==2.14.0+cpu` exists only on PyTorch's CPU index, so torch is installed from there first.

What you can do next depends on the simulator you have:

- **None:** the tests run on a stand-in circuit of their own, and the page opens with no task to run. This prints the
  graph GATOR builds from a five-transistor amplifier's netlist:

  ```bash
  PYTHONPATH="$PWD/src" python examples/netlist_demo.py --config configs/gpdk045_opamp.json examples/circuits/gpdk045_ota5.scs
  ```
- **ngspice:** in the Connection window add an "ngspice on this machine" connection. In the Tasks window choose
  **From an ngspice netlist...** and then **Example**, a five-transistor amplifier on textbook transistor models
  that needs no PDK. Save it as a task, fill in Specs and press Start. The details are in
  [the ngspice window](docs/workbench.md#an-ngspice-netlist-as-a-task-the-ngspice-window-added-2026-09-23-user-request).
- **Cadence Virtuoso and Spectre:** you also need virtuoso-bridge 0.8.0, installed separately, a PDK, and a cell with
  its testbench. See [connection profiles](docs/workbench.md#connection-profiles-section-21) and
  [a task's Virtuoso side](docs/workbench.md#a-tasks-virtuoso-side-the-cell-it-works-in-saving-the-run). On a test
  circuit, 800 designs took 8 to 14 minutes with four simulations at a time.

## What is in the repository

| Location | What it holds |
|---|---|
| [frontend/](frontend/) | The browser page (React, TypeScript): read a circuit from Virtuoso or an ngspice netlist, edit its parameters, probes and specifications, start, pause and continue runs, read their data and compare saved models. |
| [src/gator_workbench/](src/gator_workbench/) | The server behind the page: saved tasks, run control, the recorded data, the two classical searches and the local Agent. The [workbench reference](docs/workbench.md) describes every panel. |
| [src/analog_optimizer/](src/analog_optimizer/) | The optimizer library: the netlist parser, the circuit graph, parameter actions, measurements, the reward, the six encoders (graph transformer, RGCN, GATv2, GraphGPS, CircuitGPS, parameter-group cross-attention), SAC and the simulator backends. See the [optimizer package](docs/optimizer-package.md). |
| [tests/](tests/) | Offline tests with stand-in simulators and pinned fixtures. |
| [examples/](examples/) | The scripts of the early milestones, benchmarks and audits, kept as research history and not as tutorials. |
| [configs/](configs/) | Parser mappings and research configurations; files pinned by an audit stay unchanged. |
| [docs/](docs/README.md) | The written record: references, plans with their outcomes, and a dated record of every change and experiment, listed in the [index of records](docs/frontend_implementation_status.md). |
| [.agents/](.agents/), [CLAUDE.md](CLAUDE.md), [the specification](gator_claude_code_fable51_frontend_data_outputs_en.md) | The research contracts, the working rules and the workbench's specification, written for the coding agents that helped build GATOR. |
| [pyproject.toml](pyproject.toml), [constraints.txt](constraints.txt) | Dependencies, and the exact versions that saved models need. |

Not in the repository: the simulation data, the saved models and the evidence folders that the records cite
(`artifacts/local/` and `outputs/` are local and git-ignored), the circuits and scripts of the later experiments, any
PDK or Cadence file, and the thesis. The records show what was done and found; the results cannot be re-run from a
clone alone.

Read next: the [glossary](docs/glossary.md) for the project's words;
[how the networks size a circuit](docs/graph-transformers-reading-guide.md), which assumes transistors but not
transformers; the [functionality reference](docs/functionality-reference.md), which maps each feature to its code,
tests and record; and [README history](docs/history-readme-milestones.md) for the first README's milestones.

## Status and limits

- The MScR experiments are complete (3 November 2026). Later changes are maintenance.
- Every evaluation is a nominal schematic simulation. No saved task simulates at process corners, and there is no
  Monte Carlo and no layout.
- A Virtuoso run writes sizes into a working copy of the cell, the copy you made and named, never into your original
  design.
- Simulations start only when you press a button; saving a new task simulates its starting design once. The one thing
  the page does by itself is a free connection test when it opens.
- The two classical searches are chosen in a configuration file, not on the page, and the Pareto optimiser needs
  BoTorch (0.16.1 was used), which the commands above do not install.
- The Agent tab runs an NVIDIA Nemotron model on your own GPU through a pinned llama.cpp build for Windows (WSL
  included), with 22 GiB of free GPU memory for the large model or 8 for the small one. It only advises: a suggestion
  goes through the normal editor as one undoable change, and it never starts a simulation.
- The simulator side was built against one 45 nm generic PDK and one foundry PDK on a Cadence host; the foundry PDK's
  name and files are kept out of this repository.
- The dated records are kept as they were written: they name folders of the author's machine, some early ones are
  in Chinese, and the decisions document stops on 15 October 2026 (later decisions are in the records).
- The workbench, the records and this README were written with the help of coding agents; the records say what was
  done by whom and when.

## Citing and licence

To cite GATOR, cite this repository: Fengyan Wang, *GATOR: Graph-Aware Transformer Optimizer for Reinforcement
learning*, 2026, <https://github.com/FengyanWong/gator>. For questions, open an issue there.

GATOR is released under the [MIT licence](LICENSE). The licence covers this repository's code and documents; it
does not cover Cadence Virtuoso, Spectre, any PDK, the NVIDIA models or the other software it works with, each of
which has its own terms.
