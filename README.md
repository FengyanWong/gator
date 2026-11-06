# GATOR

GATOR sizes analog circuits. *Sizing* means choosing the device sizes, such as transistor widths and lengths, that
make a circuit meet its specifications. GATOR searches for them by trial: it proposes sizes, simulates every proposal
in a real circuit simulator, and learns from the results.

You give it three things:

- a circuit whose connections (its topology) are fixed,
- the values it may change, such as device widths, lengths and multipliers,
- the specifications to meet.

You work in a browser page served from your own machine; the page and its server are called the workbench. Every
simulated design is recorded, and a run never simulates more designs than you approved when you pressed Start. A run
leaves you its best design and the data of every design it simulated.

![How GATOR sizes a circuit: the circuit, its sizes and the specifications are read as a circuit graph; a graph
encoder and policy propose device sizes, which are moved to legal values and simulated; the measurements and the
reward go back to the policy, which learns from them.](docs/images/sizing-loop.svg)

In the picture, the *policy* is the part of GATOR's neural network that proposes the sizes. The *reward* is the score
a design gets, worked out from its measurements and the specifications.

At a glance:

- **Simulators:** either Cadence Spectre, for circuits drawn as schematics in Cadence Virtuoso and reached through
  the [virtuoso-bridge](https://github.com/Arcadia-1/virtuoso-bridge-lite) package, or the free ngspice, for circuits
  written as text (SPICE netlists).
- **Cost of a run:** every design has to be simulated. With Virtuoso and Spectre, 800 designs took 8 to 14 minutes on
  a test circuit, with four simulations at a time.
- **Status:** GATOR was built by Fengyan Wang for an MSc by Research (MScR) at the University of Edinburgh's School of
  Engineering. The MScR experiments are complete (3 November 2026), and later changes are maintenance. The code stays
  usable.
- **In this repository:** the code and the written record. The run data, the saved models (trained networks) and the
  thesis are not in it, so a run from a clone starts with an untrained network. The results below call that *from
  scratch*.

New here? Go to [Install and run](#install-and-run), or straight to
[what you can do with the simulator you have](#what-you-can-do-next). Before you point GATOR at a design of your own,
read [Limits and safeguards](#limits-and-safeguards).

## How it works

The name stands for **Graph-Aware Transformer Optimizer for Reinforcement learning**: an optimizer that reads the
circuit as a graph, with a transformer, and learns by reinforcement learning. Word by word:

- **Graph-aware.** GATOR reads the circuit from its netlist, the text that lists the devices and how they connect, as
  a graph of devices and nets. Each device and each net (a wire) is a point of the graph, and each device terminal is
  a link between them. The graph keeps which terminal of a device touches which net, so a gate is not taken for a
  drain. It also keeps the hierarchy of subcircuits, and which devices share a value.
- **Transformer.** A neural network reads that graph. The part that reads it is called the encoder, and by default it
  is a graph transformer. This encoder can be swapped. Six are included: graph transformer, RGCN, GATv2, GraphGPS,
  CircuitGPS and parameter-group cross-attention.
- **Optimizer.** Each step proposes one complete design: one value for every independent parameter (matched devices
  share one). Before a design is simulated, every value is moved to a legal value: inside its bounds and on its grid,
  the spacing between its allowed values.
- **Reinforcement learning.** The network learns by trial and error from the simulation results, with the Soft
  Actor-Critic algorithm (SAC). It can learn during a run, or from an archive of earlier runs (offline training). A
  trained model can then be trained further (fine-tuned) on new specifications, another fabrication process or
  another circuit.

Two classical searches, which are not neural networks, can take the network's place in a run, for comparison on equal
terms: a trust-region Bayesian optimiser (TuRBO-1) and a Pareto optimiser. They are chosen in a configuration file,
not on the page. The Pareto optimiser needs BoTorch (0.16.1 was used), which the install commands below do not
install.

## What the experiments found

Several experiments asked whether a trained model can be reused: for new specifications, in another fabrication
process, or on another circuit.

A few words first:

- A *task* is one circuit with its adjustable parameters, its measurements and its specifications.
- A *design* is one complete set of sizes. It *passes* when it meets every specification.
- A *run* is one execution of a task. It normally had 800 simulated designs.
- *From scratch* means a fresh network, trained on this one task only.
- *Early passes* are the share of passing designs among a hundred early designs: designs 9 to 108 of a run.
- A *seed* fixes a run's random choices. A repeat is the same run with another seed.
- A *PDK* is the design kit of one fabrication process.

In short: reusing a trained model helps once it is trained further on the new task, and how much depends on the task.
What it gains is time: passing designs come sooner, and the final designs are usually no better.

The numbers in brackets are entries in the project's dated record. Each link opens the log file that holds the entry;
search that page for the number.

Where a trained model helped:

- **New specifications, same circuit.** A model first trained on two related tasks reached passing designs earlier.
  That held on three analog circuits (an amplifier, a ring oscillator and a regulator) and on a flip-flop. On the
  regulator and the flip-flop, a run from scratch found no passing design
  ([records 7.310 and 7.314](docs/workbench-log/7.301-7.323.md)).
- **Another fabrication process.** Models trained in the generic 45 nm PDK were trained further on circuits moved to
  a second PDK. The table gives the early passes; a range covers the different start models. On a regulator almost
  nothing passed from any start ([record 7.329](docs/workbench-log/7.324-7.335.md)).

  | Circuit in the second PDK | From scratch | From a model trained in the generic 45 nm PDK |
  |---|---|---|
  | Amplifier | 3 % | 60-66 % |
  | Ring oscillator | 2 % | 29-41 % |

  In the reverse direction, from the second PDK back to the generic one, only the amplifier gained
  ([record 7.454](docs/workbench-log/7.439-7.459.md)).
- **A circuit the model had not seen.** A general model was trained on the recorded designs of several circuits. On a
  telescopic amplifier, which was not among them, it raised the early passes from 21 % to 79 %
  ([record 7.330](docs/workbench-log/7.324-7.335.md)).

The limits:

- **The final designs were not better.** A run from a trained model usually ended level with a run from scratch. On
  the ring oscillator its best designs were worse: they used about twice the power.
- **A trained model was no use without that further training.** With no further training, a trained model proposed
  300 designs and none passed. That held on every circuit moved to another fabrication process, and on four circuits
  from a published study.
- **Bayesian optimisation was stronger on a published regulator.** The Bayesian optimiser (TuRBO-1) found 337 to 396
  passing designs of 800, against at most 264 in any SAC run ([record 7.318](docs/workbench-log/7.301-7.323.md)).
  Given a shared archive of earlier designs, it also stayed the best method for a fixed target over three seeds
  ([record 7.453](docs/workbench-log/7.439-7.459.md)).

How far these results reach: most comparisons have one to three runs for each setting compared, and every evaluation
is a nominal schematic simulation (see [Limits and safeguards](#limits-and-safeguards)).
[The experiments in plain words](docs/plan-transfer-experiment.md#1-in-plain-words) lists the questions asked.

## Install and run

You need:

- Linux (WSL included),
- Python 3.10,
- Node.js, to build the browser page: version 18, or 20 and later (24 was used),
- a virtual environment of your own, which grows to about 1 GB.

No GPU is needed: training uses the CPU build of PyTorch. Create and activate the virtual environment first, then:

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

These commands were tried as written. On a fresh clone (5 November 2026), steps 1 to 5 ran, and about 2,850 tests
passed in three minutes. Another 35 to 40 were skipped, because they read evidence folders that are not in the
repository or need ngspice, BoTorch or the bridge (virtuoso-bridge).

PyTorch is installed first for a reason. A saved model loads only under the versions it was saved with, so
[constraints.txt](constraints.txt) pins the exact torch, torch-geometric, numpy and networkx versions. The pinned
`torch==2.14.0+cpu` exists only on PyTorch's CPU index, so torch is installed from there first.

### What you can do next

That depends on the simulator you have.

| You have | You can | You also need |
|---|---|---|
| No simulator | Run the tests, open the page and print the graph of an example netlist. You cannot size a circuit yet. | Nothing more |
| ngspice, which is free | Size the built-in example amplifier | ngspice installed |
| Cadence Virtuoso and Spectre | Size a cell of your own | virtuoso-bridge 0.8.0 (installed separately); a PDK; a cell with its testbench |

**No simulator.** The tests run on a stand-in circuit of their own, and the page opens with no task to run. The
command below prints the graph GATOR builds from a five-transistor amplifier's netlist:

```bash
PYTHONPATH="$PWD/src" python examples/netlist_demo.py \
  --config configs/gpdk045_opamp.json examples/circuits/gpdk045_ota5.scs
```

**ngspice.** Install ngspice first: the server looks for the `ngspice` command on its own machine. Then:

1. In the Connection window, add an "ngspice on this machine" connection. The Connection button is in the page's
   header.
2. In the Tasks window, choose **From an ngspice netlist...** and then **Example**. The example is a five-transistor
   amplifier on textbook transistor models that needs no PDK.
3. Save it as a task.
4. Fill in Specs, which the example leaves to you. The Probes tab lists the values the example measures, such as
   its gain, unity-gain frequency, phase margin and supply power. Specs holds your requirements on them.
5. Press Start.

More detail is in the workbench reference, under
[the ngspice window](docs/workbench.md#an-ngspice-netlist-as-a-task-the-ngspice-window-added-2026-09-23-user-request).

**Cadence Virtuoso and Spectre.** A run writes device sizes into the cell it works in, so work on a copy. Reading a
cell into the page does not make one: copy the cell and its testbench in Virtuoso first, then read the copy in. The
page asks you to confirm that it is a copy. See
[connection profiles](docs/workbench.md#connection-profiles-section-21) and
[a task's Virtuoso side](docs/workbench.md#a-tasks-virtuoso-side-the-cell-it-works-in-saving-the-run).

## Limits and safeguards

What GATOR does on your machine:

- Simulations start only when you press a button. Saving a new task is one such press: it simulates the task's
  starting design once.
- The one thing the page does by itself is a free connection test when it opens. Free means that it costs no budget
  and simulates none of your circuits.
- A Virtuoso run writes sizes into a working copy of the cell, the copy you made and named, never into your original
  design. The sizes are put back when the run ends; a forced abort can leave them changed. Saving a task also writes
  a Maestro test named GATOR into the copy's testbench.
- The Agent tab only advises. A suggestion goes through the normal editor as one change that you can undo, and the
  Agent never starts a simulation.

What it does not do, or needs:

- Every evaluation is a nominal schematic simulation: the schematic at typical conditions. No saved task simulates
  at process corners, and there is no Monte Carlo and no layout.
- The simulator side was built against one 45 nm generic PDK and one foundry PDK on a Cadence host. The foundry PDK
  is the second PDK of the experiments. Its name and files are kept out of this repository.
- The Agent tab is optional. It offers a local language model that advises on parameter setup and optimisation
  settings. The model is an NVIDIA Nemotron model on your own GPU, run through a pinned llama.cpp build for
  Windows (WSL included). The large model needs 22 GiB of free GPU memory, the small one 8 GiB.

## What is in the repository

| Location | What it holds |
|---|---|
| [frontend/](frontend/) | The browser page (React, TypeScript). There you read a circuit from Virtuoso or an ngspice netlist, and edit its parameters, probes and specifications. You start, pause and continue runs, read their data and compare saved models. |
| [src/gator_workbench/](src/gator_workbench/) | The server behind the page: saved tasks, run control, the recorded data, the two classical searches and the local Agent. The [workbench reference](docs/workbench.md) describes every panel. |
| [src/analog_optimizer/](src/analog_optimizer/) | The optimizer library: the netlist parser, the circuit graph, parameter actions, measurements, the reward, the six encoders, SAC and the simulator backends. See the [optimizer package](docs/optimizer-package.md). |
| [tests/](tests/) | Offline tests with stand-in simulators and pinned fixtures. |
| [examples/](examples/) | The scripts of the early milestones, benchmarks and audits, kept as research history and not as tutorials. The netlist demo above is one of them. |
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

The records show what was done and found. The experiments cannot be re-run from a clone alone.

The dated records are kept as they were written. They name folders of the author's machine, and some early ones are
in Chinese. The [decisions document](docs/decisions.md) stops on 15 October 2026; later decisions are in the records.
The workbench, the records and this README were written with the help of coding agents. The records say what was
done by whom and when.

Read next:

- The [glossary](docs/glossary.md), for the project's words.
- [How the networks size a circuit](docs/graph-transformers-reading-guide.md), which takes about 25 minutes. It
  follows two of the six encoders, GraphGPS and CircuitGPS, and assumes transistors but not transformers.
- The [functionality reference](docs/functionality-reference.md), which maps each feature to its code, tests and
  record.

## Citing and licence

To cite GATOR, cite this repository: Fengyan Wang, *GATOR: Graph-Aware Transformer Optimizer for Reinforcement
learning*, 2026, <https://github.com/FengyanWong/gator>. For questions, open an issue there.

GATOR is released under the [MIT licence](LICENSE). The licence covers this repository's code and documents. It does
not cover Cadence Virtuoso, Spectre, any PDK, the NVIDIA models or the other software GATOR works with. Each of those
has its own terms.
