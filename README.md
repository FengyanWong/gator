# GATOR

GATOR sizes analog circuits: it searches for the device sizes, such as widths, lengths and multipliers, that make a
circuit of fixed topology meet its specifications. It proposes sizes, simulates every proposal in a real circuit
simulator, and learns from the results.

You give it the circuit, the values it may change and the specifications. You work in a browser page served from
your own machine; the page and its server are called the workbench. A run never simulates more designs than you
approved when you pressed Start. It leaves you its best design and the data of every design it simulated.

![How GATOR sizes a circuit: the circuit, its sizes and the specifications are read as a circuit graph; a graph
encoder and policy propose device sizes, which are moved to legal values and simulated; the measurements and the
reward go back to the policy, which learns from them.](docs/images/sizing-loop.svg)

In the picture, the *policy* is the part of the neural network that proposes sizes. The *reward* is a design's score,
computed from its measurements and the specifications.

- **Simulators:** Cadence Spectre, for schematics drawn in Cadence Virtuoso and reached through the
  [virtuoso-bridge](https://github.com/Arcadia-1/virtuoso-bridge-lite) package, or the free ngspice, for SPICE
  netlists.
- **Cost:** every design is simulated. With Virtuoso and Spectre, 800 designs took 8 to 14 minutes on a test circuit,
  four simulations at a time.
- **Status:** built by Fengyan Wang for an MSc by Research (MScR) at the University of Edinburgh's School of
  Engineering. The MScR experiments are complete (3 November 2026). Later changes are maintenance; the code stays
  usable.
- **In this repository:** the code and the written record, not the run data, the saved models (trained networks) or
  the thesis. A run from a clone therefore starts *from scratch*, with an untrained network.

New here? Go to [Install and run](#install-and-run) and [what you can do next](#what-you-can-do-next). Read
[Limits and safeguards](#limits-and-safeguards) before you point GATOR at a design of your own.

## How it works

The name stands for **Graph-Aware Transformer Optimizer for Reinforcement learning**:

- **Graph-aware.** The circuit is read from its netlist (the list of its devices and connections) as a graph. Each
  device and each net (a wire) is a point, and each device terminal is a link between them. The graph keeps which
  terminal touches which net, so a gate is not taken for a drain. It also keeps the hierarchy of subcircuits and
  which devices share a value.
- **Transformer.** A neural network reads that graph; the part that reads it is the encoder. By default it is a graph
  transformer, and it can be swapped: six encoders are included, graph transformer, RGCN, GATv2, GraphGPS, CircuitGPS
  and parameter-group cross-attention.
- **Optimizer.** Each step proposes one complete design: one value per independent parameter (matched devices share
  one). Before simulation, each value is moved to a legal one, inside its bounds and on its grid of allowed values.
- **Reinforcement learning.** The network learns by trial and error from the simulation results, with Soft
  Actor-Critic (SAC), during a run or from an archive of earlier runs (offline training). A trained model can be
  trained further (fine-tuned) on new specifications, another fabrication process or another circuit.

Two classical searches (not neural networks) can take the network's place in a run, for a comparison on equal terms:
a trust-region Bayesian optimiser (TuRBO-1) and a Pareto optimiser. Both are chosen in a configuration file, not on
the page. The Pareto optimiser needs BoTorch (0.16.1 was used), which the install commands do not install.

## What the experiments found

Several experiments asked whether a trained model can be reused: for new specifications, in another fabrication
process, or on another circuit. Words used below:

- A *task* is one circuit with its adjustable parameters, measurements and specifications.
- A *design* is one complete set of sizes. It *passes* when it meets every specification.
- A *run* is one execution of a task. In the experiments it normally had 800 simulated designs.
- *From scratch* means a fresh network, trained on this one task only.
- *Early passes* are the share of passing designs among designs 9 to 108 of a run.
- A *seed* fixes a run's random choices. A repeat is the same run with another seed.
- A *PDK* is the design kit of one fabrication process.

In short: reusing a trained model helps once it is trained further on the new task, and how much depends on the task.
The gain is time: passing designs come sooner, and the final designs are usually no better. Bracketed numbers are
entries in the project's dated record. Each link opens the log file that holds the entry; search it for the number.

Where a trained model helped:

- **New specifications, same circuit.** A model first trained on two related tasks reached passing designs earlier,
  on three analog circuits (an amplifier, a ring oscillator and a regulator) and a flip-flop. On the regulator and
  the flip-flop, a run from scratch found no passing design
  ([records 7.310 and 7.314](docs/workbench-log/7.301-7.323.md)).
- **Another fabrication process.** Models trained in the generic 45 nm PDK were trained further on circuits moved to
  a second PDK. Early passes, with a range over the different start models:

  | Circuit in the second PDK | From scratch | From a model trained in the generic 45 nm PDK |
  |---|---|---|
  | Amplifier | 3 % | 60-66 % |
  | Ring oscillator | 2 % | 29-41 % |

  On a regulator almost nothing passed from any start ([record 7.329](docs/workbench-log/7.324-7.335.md)). In the
  reverse direction, back to the generic PDK, only the amplifier gained
  ([record 7.454](docs/workbench-log/7.439-7.459.md)).
- **A circuit the model had not seen.** A general model was trained on the recorded designs of several circuits. On
  a telescopic amplifier, which was not among them, it raised the early passes from 21 % to 79 %
  ([record 7.330](docs/workbench-log/7.324-7.335.md)).

The limits:

- **Final designs were not better.** A run from a trained model usually ended level with a run from scratch. On the
  ring oscillator its best designs used about twice the power.
- **No use without further training.** A trained model that was not trained further proposed 300 designs, and none
  passed. That held on every circuit moved to another fabrication process and on four circuits from a published
  study.
- **Bayesian optimisation was stronger on a published regulator.** TuRBO-1 found 337 to 396 passing designs of 800,
  against at most 264 in any SAC run ([record 7.318](docs/workbench-log/7.301-7.323.md)). Given a shared archive of
  earlier designs, it also stayed the best method for a fixed target over three seeds
  ([record 7.453](docs/workbench-log/7.439-7.459.md)).

Most comparisons have one to three runs for each setting compared, and every evaluation is a nominal schematic
simulation (see [Limits and safeguards](#limits-and-safeguards)).
[The experiments in plain words](docs/plan-transfer-experiment.md#1-in-plain-words) lists the questions asked.

## Install and run

You need Linux (WSL included), Python 3.10 and, to build the browser page, Node.js (18, or 20 and later; 24 was
used). Training uses the CPU build of PyTorch, so no GPU is needed. Create and activate a virtual environment of your
own (it grows to about 1 GB), then:

1. Get the code.

   ```bash
   git clone https://github.com/FengyanWong/gator.git && cd gator
   ```

2. Install PyTorch from its CPU index, then GATOR.

   ```bash
   python -m pip install -c constraints.txt torch --index-url https://download.pytorch.org/whl/cpu
   python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
   ```

3. Build the browser page.

   ```bash
   (cd frontend && npm ci && npm run build)
   ```

4. Run the tests.

   ```bash
   OMP_NUM_THREADS=1 PYTHONPATH="$PWD/src" python -m pytest -q -n 4 --dist loadgroup
   ```

5. Start the server. It keeps running in that terminal.

   ```bash
   PYTHONPATH="$PWD/src" python -m gator_workbench.cli serve --port 8765
   ```

6. Open <http://127.0.0.1:8765/> in a browser.

Tried as written on a fresh clone (5 November 2026): steps 1 to 5 ran, and about 2,850 tests passed in three
minutes. Another 35 to 40 were skipped: they read evidence folders that are not in the repository, or need ngspice,
BoTorch or virtuoso-bridge. A saved model loads only under the versions it was saved with, so
[constraints.txt](constraints.txt) pins the exact torch, torch-geometric, numpy and networkx versions. The pinned
`torch==2.14.0+cpu` exists only on PyTorch's CPU index, which is why torch is installed from there first.

### What you can do next

| You have | You can | You also need |
|---|---|---|
| No simulator | Run the tests, open the page and print an example circuit's graph, but not size a circuit | Nothing more |
| ngspice, which is free | Size the built-in example amplifier | ngspice installed |
| Cadence Virtuoso and Spectre | Size a cell of your own | virtuoso-bridge 0.8.0 (installed separately); a PDK; a cell with its testbench |

**No simulator.** The tests use a stand-in circuit of their own, and the page opens with no task to run. This prints
the graph GATOR builds from a five-transistor amplifier's netlist:

```bash
PYTHONPATH="$PWD/src" python examples/netlist_demo.py \
  --config configs/gpdk045_opamp.json examples/circuits/gpdk045_ota5.scs
```

**ngspice.** Install ngspice where the server runs: it looks for the `ngspice` command on its own machine. Then:

1. Open the Connection window (its button is in the page's header) and add an "ngspice on this machine" connection.
2. In the Tasks window, choose **From an ngspice netlist...**, then **Example** (a five-transistor amplifier on
   textbook transistor models; no PDK needed).
3. Save it as a task.
4. Fill in Specs, which the example leaves to you: your requirements on the values it measures. The Probes tab lists
   them, such as gain, unity-gain frequency, phase margin and supply power.
5. Press Start.

Details: [the ngspice window](docs/workbench.md#an-ngspice-netlist-as-a-task-the-ngspice-window-added-2026-09-23-user-request)
in the workbench reference.

**Cadence Virtuoso and Spectre.** A run writes device sizes into the cell it works in, so work on a copy. Reading a
cell into the page does not copy it: copy the cell and its testbench in Virtuoso first, then read the copy in. The
page asks you to confirm that it is a copy. See
[connection profiles](docs/workbench.md#connection-profiles-section-21) and
[a task's Virtuoso side](docs/workbench.md#a-tasks-virtuoso-side-the-cell-it-works-in-saving-the-run).

## Limits and safeguards

What GATOR does on your machine:

- Simulations start only when you press a button. Saving a new task is one such press: it simulates the task's
  starting design once.
- The one thing the page does by itself is a connection test when it opens. It costs no budget and simulates none of
  your circuits.
- A Virtuoso run writes sizes into a working copy of the cell, the copy you made and named, never into your original
  design. The sizes are put back when the run ends; a forced abort can leave them changed. Saving a task also writes
  a Maestro test named GATOR into the copy's testbench.
- The Agent tab only advises. A suggestion goes through the normal editor as one change that you can undo, and the
  Agent never starts a simulation.

What it does not do, or needs:

- Every evaluation is a nominal schematic simulation: the schematic at typical conditions. No saved task simulates
  at process corners, and there is no Monte Carlo and no layout.
- The simulator side was built against one 45 nm generic PDK and one foundry PDK on a Cadence host. The foundry PDK
  is the second PDK of the experiments; its name and files are kept out of this repository.
- The Agent tab is optional. Its adviser on parameter setup and optimisation settings is a local language model, an
  NVIDIA Nemotron model on your own GPU. It runs through a pinned llama.cpp build for Windows (WSL included). The
  large model needs 22 GiB of free GPU memory, the small one 8 GiB.

## What is in the repository

| Location | What it holds |
|---|---|
| [frontend/](frontend/) | The browser page (React, TypeScript): read a circuit from Virtuoso or an ngspice netlist, edit its parameters, probes and specifications, start, pause and continue runs, read their data, compare saved models. |
| [src/gator_workbench/](src/gator_workbench/) | The server behind the page: saved tasks, run control, the recorded data, the two classical searches and the local Agent. The [workbench reference](docs/workbench.md) describes every panel. |
| [src/analog_optimizer/](src/analog_optimizer/) | The optimizer library: netlist parser, circuit graph, parameter actions, measurements, reward, the six encoders, SAC and the simulator backends. See the [optimizer package](docs/optimizer-package.md). |
| [tests/](tests/) | Offline tests with stand-in simulators and pinned fixtures. |
| [examples/](examples/) | Scripts of the early milestones, benchmarks and audits, kept as research history, not as tutorials. The netlist demo above is one of them. |
| [configs/](configs/) | Parser mappings and research configurations. Files pinned by an audit stay unchanged. |
| [docs/](docs/README.md) | The written record: references, plans with their outcomes, and a dated record of every change and experiment, listed in the [index of records](docs/frontend_implementation_status.md). [README history](docs/history-readme-milestones.md) keeps the first README's milestones. |
| [.agents/](.agents/), [CLAUDE.md](CLAUDE.md), [the specification](gator_claude_code_fable51_frontend_data_outputs_en.md) | The research contracts, the working rules and the workbench's specification, written for the coding agents that helped build GATOR. |
| [pyproject.toml](pyproject.toml), [constraints.txt](constraints.txt) | Dependencies, and the exact versions that saved models need. |

Not in the repository:

- the simulation data, the saved models and the evidence folders that the records cite (`artifacts/local/` and
  `outputs/` are local and git-ignored),
- the circuits and scripts of the later experiments,
- any PDK or Cadence file,
- the thesis.

The records show what was done and found, but the experiments cannot be re-run from a clone alone.

The dated records are kept as they were written: they name folders of the author's machine, and some early ones are
in Chinese. The [decisions document](docs/decisions.md) stops on 15 October 2026; later decisions are in the records.
The workbench, the records and this README were written with the help of coding agents. The records say what was
done by whom and when.

Read next:

- The [glossary](docs/glossary.md), for the project's words.
- [How the networks size a circuit](docs/graph-transformers-reading-guide.md), about 25 minutes. It follows GraphGPS
  and CircuitGPS, two of the six encoders, and assumes transistors but not transformers.
- The [functionality reference](docs/functionality-reference.md): each feature's code, tests and record.

## Citing and licence

To cite GATOR, cite this repository: Fengyan Wang, *GATOR: Graph-Aware Transformer Optimizer for Reinforcement
learning*, 2026, <https://github.com/FengyanWong/gator>. For questions, open an issue there.

GATOR is released under the [MIT licence](LICENSE). The licence covers this repository's code and documents. It does
not cover Cadence Virtuoso, Spectre, any PDK, the NVIDIA models or the other software GATOR works with. Each of those
has its own terms.
