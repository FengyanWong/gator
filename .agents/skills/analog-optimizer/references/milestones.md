# Implementation stages and acceptance

Do not assume the whole project has already started, and do not generate all directories and empty classes at once.
Inspect the current repository first; verify completed steps with tests and skip them. Deliver one defined stage or a small task within a stage at a time.

The current project has completed M1–M5 (including the additional real same-category new-topology validation) and the encoder interface before M6 described below; M6 closed at pilot scale on 2026-09-20 (see the M6 section). See [Project decisions](project-decisions.md) for verified capabilities and limits; do not treat historical stage boundaries as a current instruction to pause.

## M0: Inventory the code and runtime environment

Inputs: the user's existing repository, dependency declarations and configured bridge, if any.
Outputs: existing modules and reusable paths, execution environment, current gaps and the first acceptance target.

- Establish whether Python runs in WSL or the VM, and where Virtuoso/Spectre run; do not hard-code personal host values.
- Check upstream bridge modules/versions/signatures; do not automatically upgrade, reinstall or modify the daemon.
- Check for a shareable sample netlist; use a synthetic fixture if none is available.
- Record unavailable real-environment information without stopping offline development because of it.
- For later condition interfaces, read the actual model sections, statistical entry points, temperature range and voltage limits of the devices used. Retain file versions/digests and distinguish source facts from engineering screening points.

## M1: First coding round, basic flow only

This stage is the default first task:

```text
Backend Protocol + explicit MockBackend
  → documented Spectre syntax subset
  → CircuitGraph / terminal-aware connections / parameter groups
  → PyG conversion
  → synthetic fixtures + tests + small offline demo
```

Target outputs:

- Graph and result types independent of the bridge, with explicit schemas and diagnostics.
- A usable parser subset, without claiming full Spectre support.
- Fixtures that verify terminal relations, hierarchy and parameter mappings.
- A PyG adapter and batch/unbatch tests with two differently sized graphs.
- An explicitly synthetic mock; the real adapter interface can be inspected, but unconnected capabilities must be reported honestly.
- Consistent PVT/MC context reserved in Backend request/result/artifact; explicitly reject unsupported MC execution. Store actual condition metadata in the graph; do not turn statistical model random variables into sizing actions.
- A README describing dependencies, supported scope and how to run the demo/tests.

Acceptance: offline tests run without Cadence/PDK/SSH; the demo outputs a graph-structure summary and parameter mapping; invalid inputs have diagnostics that locate the problem.
**This stage does not implement actor/critic, SAC updates, a surrogate or parallel scheduling.**

## M2: One real simulation baseline

When authorized by the user and the real environment is available, connect one existing circuit that can be simulated.
Export or read the original netlist → run the baseline → extract metrics → slightly change one authorized parameter → verify by readback/new netlisting → rerun → restore.

Acceptance: real results include provenance, executed parameters, versions, status and timing; they match the existing manual/script baseline within explicit tolerances.
If the new netlist execution path differs from ADE, first verify equivalence of models, analyses, corners and measurements instead of directly comparing timing.
This stage still first accepts one explicit nominal condition. PVT extensions use job copies with identical parameters, retain checks/restoration of original sizes/CDF, and do not modify the same schematic concurrently; model/voltage/temperature labels must match the executed netlist and measurements.

## M3: Environment and non-learning loop

Implement parameter legalization, the measurement evaluator, reward, reset/step, failure policy and candidate logging.
Drive the full real flow with random candidates first, checking boundaries, failures, repeated candidates and stopping conditions.

M3 condition-interface scope: add typed PVT/Monte Carlo requests, per-sample identity, provenance and budget interfaces; `reset/step` enforces nominal-only operation. Also provide pure functions that deduplicate and select the top 3 by nominal reward, summarize worst-case/pass rate/robust score for a fixed 5 corners, and record rejection or incomplete reasons. Without model outputs, do not call random candidates SAC optimization results. Top-k post-validation scheduling and MC execution are outside this interface delivery and remain unimplemented.

Acceptance also requires that non-nominal results cannot enter replay; results with incorrect conditions/sizes are rejected; any failed corner disqualifies a pass; missing results/infrastructure failures do not produce invented pass rates; unimplemented MC is explicitly rejected; and original nominal netlists and action semantics stay compatible. Future optional complexity is described in [Conditions and statistical validation](pvt-monte-carlo.md); an interface's existence does not enable it automatically. (2026-09-30 note: the M3 nominal-only training constraint was later relaxed by the user-authorized reward v2 / v2.1: `real:gpdk045_ota7` can explicitly select training conditions whose results enter replay; nominal remains the default and MC remains unimplemented.)

Acceptance: a small experiment within a limited budget can be fully recovered/reviewed; success cannot bypass required constraints, and failure costs are recorded.
Only then introduce neural networks; do not debug measurement formulas through training curves.

## M4: Graph Transformer and SAC

First verify network shapes, masks, gradients, target updates and checkpoint recovery in a small synthetic environment, then run a small amount of real sampling.
Specify attention_mode, the parameter-group actor, action-conditioned twin critics, temperature and entropy rules for valid dimensions.

Acceptance: two different graph/action sizes can update in the same batch; padding does not affect valid outputs/loss; updates are reproducible and have no NaN; checkpoint recovery preserves schema and action semantics.
A mock learning a synthetic function is not evidence of effective circuit optimization.

## M5: Same-category topology and specification transfer

Freeze splits and compare training from scratch, a frozen policy and adaptation with a fixed budget; include random/non-RL controls and a port-aware GNN control.

Acceptance: report pass rates, real calls, wall-clock time, pretraining costs, failures/censoring and multiple seeds, without leakage.

The real seven-transistor two-stage OTA structural holdout and 1→2 action-dimension comparison are now complete: this round used 585 Spectre calls, 3 seeds × 6 methods, audits of 24 checkpoints and restoration of both circuits; 440 offline tests passed. GT adaptation/random each achieved 1/3, coordinate search 3/3 and port-GNN adaptation 2/3; a GT transfer advantage on the new topology remains unproven. There is only one structurally held-out topology, and targets were frozen after baseline acceptance; do not claim broad or blind-test generalization. See the project's `docs/m5-real-topology.md`.

## M6: Cross-category transfer, optional acceleration and extensions

Before M6, the user-requested interchangeable GT/MLP/GCN/RGCN/GAT interface was implemented: a common model contract, scratch/frozen/adapt per architecture, isolated configurations/checkpoints and dynamic budgets. M5 port-GNN and the default six methods were retained then (2026-09-30 note: port-GNN was removed on 2026-09-24 and the default six-method set was dropped with it; the default now runs GT only. MLP and GCN were removed on 2026-09-26, GAT was replaced by GATv2 that day, and the encoders are now GT/RGCN/GATv2). Acceptance covered mixed graphs/actions, terminal ablations, exact recovery and synthetic transfer for four architectures; interface acceptance alone is not evidence for M6 or real new topologies. See the M5 record above for the later additional real new-topology validation.

After establishing that the basics work, study cross-category LDO/VCO/OpAmp transfer and multi-environment sampling with one policy.
Only then introduce surrogates, structural global attention, more parameter domains or other optimizers under explicit hypotheses.

Acceptance: separate ablations for every extension, final real validation and complete cost comparisons; new features must not break earlier stages' contracts.

M6 closed at pilot scale (2026-09-20, user decision): the synthetic cross-category protocol, real LDO/VCO baselines and VCO fast numerical-policy qualification, a frozen real protocol with 23 metrics, a real pilot with three folds × six encoders × three seeds (2,811 Spectre calls, 1,566 SAC updates, independent audit passed), and strict-mode VCO requalification (28 calls, 36/36 confirmed). M6 totaled 2,877 real calls. GT adaptation achieved OTA 2/3, LDO 3/3 and VCO 3/3; coordinate search achieved 3/3 in each category, and frozen policies 0/3. There is no evidence of a GT or transfer advantage, nor of a disadvantage. Each category has only one characterized topology, 3 seeds, 8-step episodes and nominal conditions only; this is not a blind test and does not support generalization, ranking or convergence conclusions. Single-policy multi-environment sampling, surrogates, global attention, additional parameter domains, other optimizers and PVT/MC have not started and are outside this closure; larger prospective experiments capable of answering the M6 questions need a separate user decision and budget. This plan defines no new stage after M6; the Web workbench is developed under a separate specification outside the M series. See the project's `docs/decisions.md`, `docs/m6-real-results.md` and `docs/m6-vco-requalification.md`.

## Example project structure

Use only when a new repository lacks the corresponding structure; this is not a request to generate every file at once:

```text
src/analog_optimizer/
  backends/
  netlist/
  graph/
  parameters/
  measurements/
  envs/             # from M3
  models/           # from M4
  training/         # from M4
  evaluation/       # pure summary interfaces from M3; experiment execution added later
tests/
  unit/
  fixtures/synthetic/
  integration/      # explicit opt-in
configs/
examples/
```

## Report format at completion

```text
Completed: concrete behavior changes and affected files.
Acceptance: commands actually run and passed/failed/skipped results.
Boundaries: static checks only, and work not validated in a real Cadence environment.
Next step: one concrete executable task, without promising background execution.
```

A collection of empty "implement later" files does not constitute a completed stage.
