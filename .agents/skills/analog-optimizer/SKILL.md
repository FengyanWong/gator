---
name: analog-optimizer
description: "Develop and review analog circuit sizing projects based on Cadence Virtuoso/Spectre, virtuoso-bridge-lite, port-aware circuit graphs and goal-conditioned SAC. Use for netlist/CircuitGraph/PyG, simulation backends, variable actions, Graph Transformer/RGCN/GATv2 encoder comparisons and transfer experiments; not for general brainstorming or layout generation alone. LLM-driven sizing follows docs/brief-llm-sizing-for-astra.md only."
---

# Analog Optimizer

Help the user build an analog circuit sizing research system step by step, with **testable, recoverable and reproducible experiments**.
Follow the user's latest request, the repository's current state and verified interfaces; this skill states project conventions, not upstream API documentation or an already implemented or validated optimizer.
Explain in English and preserve English code identifiers. Inspect existing code first, then make the smallest change that can be accepted and verified.

## What to read first

On each use, first read the repository-root `CLAUDE.md` (current rules) and [Project decisions](references/project-decisions.md) (the research scope of M1-M6; the latest state is the Current state section at the start of `docs/decisions.md`: M6 closed at pilot scale on 2026-09-20). Then choose the material for the task; there is no need to load everything at once:

| Current task | Material to read |
|---|---|
| Workbench (Web UI: `src/gator_workbench/`, `frontend/`) | `docs/frontend_implementation_status.md` (development record index); in `docs/workbench.md` (the current state of each feature, about 145 kB), read only the sections of the feature being changed: first use `grep -n '^##' docs/workbench.md` to see the headings, then read by line number; workbench code belongs only in these two directories |
| First startup, task breakdown, acceptance | [Milestones and deliverables](references/milestones.md) |
| Virtuoso, Spectre, SSH, WSL, VM, run failures | [Backend contract](references/bridge-backend.md) |
| netlist, device/net graph, terminals, parameter groups, PyG | [Graph and parsing contract](references/graph-contract.md) |
| Encoder selection, Graph Transformer/RGCN/GATv2, actor/critic, SAC, reward | [Learning and action contract](references/learning-and-actions.md) |
| Generalization, baselines, ablations, performance, paper conclusions | [Experiments and review](references/evaluation.md) |
| PVT/Monte Carlo interfaces, top-k post-validation, future compute budgets | [Conditions and statistical validation](references/pvt-monte-carlo.md) |
| External APIs, literature or installation methods to verify | [Sources and verification boundaries](references/sources.md) |

## Current default direction

```text
Virtuoso schematic / exported Spectre netlist
  → verified extraction / parser
  → canonical CircuitGraph: devices + nets + terminal-aware connections
  → PyG representation + parameter groups + target specifications
  → selectable encoder (default: Graph Transformer; also RGCN, GATv2, GraphGPS, parameter-group cross-attention)
  → goal-conditioned SAC actor + action-conditioned twin graph critics
  → normalized action → legal physical parameter assignment
  → backend adapter → Virtuoso bridge / Spectre
  → validated measurements + status → observation / reward / replay
```

- Use **Graph Transformer + goal-conditioned SAC** by default. The common encoder interface supports Graph Transformer, RGCN, GATv2, GraphGPS and parameter-group cross-attention (`graph_transformer` / `rgcn` / `gatv2` / `graph_gps` / `group_cross_attention`; see `src/analog_optimizer/models/encoders.py`; the last two were added on 2026-10-06, record 7.228): port-GNN was removed on 2026-09-24 (it still runs at source commit bbdfe36 and earlier), MLP and GCN were removed on 2026-09-26, and GATv1 (`gat`) was replaced by GATv2 that day; old names are explicitly rejected and old weights are not migrated (synchronized 2026-09-30). Do not expand an encoder ablation into replacing SAC or adding a surrogate.
- The first version **does not include a surrogate**, nor does it insert one as a required layer between the encoder and SAC.
- LLM-driven sizing: on 2026-09-29 the user decided to add it according to `docs/brief-llm-sizing-for-astra.md` (a new `src/analog_optimizer/search/` subpackage, one digest change; not yet started as of 2026-09-30). For that work, the brief replaces the rules against "LLM search / an LLM inner loop" in this skill and its references; other work still does not include an LLM by default (synchronized 2026-09-30).
- Optimization initially covers device sizes, biases and explicitly allowed parameters of a fixed topology; it does not cover topology search or automatic placement and routing.
- The initial goal is a reliable loop for a single circuit; next validate specification and topology transfer within a circuit class, then study cross-category LDO/VCO/OpAmp transfer.
- The project has completed M4, the first M5 round and the additional real same-category new-topology validation, and the encoder interface before M6. M6 completed the synthetic cross-category protocol, real LDO/VCO baseline qualification and one frozen real cross-category pilot (2,811 Spectre calls, 1,566 SAC updates, independent audit and all 544 regression tests passed), but did not demonstrate a GT transfer advantage. Subsequent strict-mode (reference) requalification confirmed the first feasible design of all 36 successful VCO runs with 28 Spectre calls (see `docs/m6-vco-requalification.md`). M6 closed at pilot scale on 2026-09-20 by the user's decision: the flow ran on real circuits and passed an independent audit, but the scale does not support a conclusion on a transfer or GT advantage; larger prospective experiments and all optional extensions were not performed and need a separate user decision and budget. The milestone plan defines no new stage after M6. Do not casually add or change `.py` files in `src/analog_optimizer/`: `source_digest()` determines whether existing checkpoints can load and frozen protocols can be revalidated. Do not use the earlier "stop at M3" scope to override later authorization; new tasks still follow the user's request. For the latest evidence and boundaries, see the project's `docs/decisions.md`, `docs/m5-real-topology.md`, `docs/encoder-ablation.md` and `docs/m6-real-results.md`.
- Training/sampling defaults to nominal (condition policy `off`); the parallel Spectre collection entry point defaults to 4 workers (each with isolated netlists and job directories, sharing one learner/replay; see `docs/parallel-spectre-sac.md`). Since reward v2 (2026-09-26), `real:gpdk045_ota7` can explicitly select `always` (nominal + four screening corners per step), and since reward v2.1 (2026-09-29) it can also select `after_nominal` (run corners only after nominal passes every hard spec). In those cases, each condition's results enter the training reward and replay (`SACLearner(condition_policy=...)`; see `docs/reward-v2.md` and [Conditions and statistical validation](references/pvt-monte-carlo.md)); other tasks support nominal only. Post-validation remains independent: since 2026-09-22 the workbench's Corner check can resimulate a run's best designs under 5 GPDK045 conditions (`docs/workbench.md`), and its results do not feed back into training; Monte Carlo execution is still unimplemented (only the plan `docs/plan-finalist-monte-carlo.md` exists) (synchronized 2026-09-30).
- Read process corners and temperatures from the actual PDK models/documentation; also check voltage against the devices' limits. The 1.8 V example withdrawn by the user is not the configuration of the current GPDK045 OTA. Distinguish explicit PDK ranges from screening points chosen by the project.
- The current GT uses local terminal attention; width, depth and comparative performance against other architectures still need experiments. Passing the interface checks does not establish a transfer advantage.

When the user explicitly changes the architecture, follow the new request and update the project's decision record; do not use this file to prevent the user from changing direction.

## Workflow

1. **Inspect the repository.** Read `CLAUDE.md` (this repository has no `AGENTS.md`), README, dependency declarations (exact versions are in `constraints.txt`), configurations, tests and relevant modules. Check uncommitted changes and preserve the user's work: several sessions share the workspace and git index.
2. **Confirm the scope.** Briefly state the inputs, outputs, affected interfaces and acceptance criteria for this task. Check the code first for questions the repository can answer; do not ask again.
3. **Check the environment.** Confirm the Python environment, the bridge's actual installation location and version, the host running Virtuoso/Spectre, and the existing connection method; do not log credentials.
4. **Implement the smallest change.** Prefer existing modules; create structure only where it is missing. Do not present a fake implementation as a real backend.
5. **Validate offline first.** Parsing and mock tests should still run without Cadence, a PDK, SSH or a GPU; real tests must be enabled separately.
6. **Report evidence.** State what changed, the commands run, passed/failed/skipped tests, unverified parts and one concrete next step.

Ask only when correctness is materially blocked or a risky real operation is involved. A missing PDK, network or license does not prevent delivery of the offline portion.

## Technical constraints to preserve

### Data and graphs

- Original instance/net names are for locating objects and writing back only; do not treat names such as `M1` and `M3` as learning semantics shared across circuits.
- Preserve MOS D/G/S/B terminals and forward/reverse relations; when several terminals of one device connect to the same net, do not merge them into one untyped edge.
- Device terminal order and parameter meaning must come from parsed definitions, CDF/PDK mappings or user configuration; do not infer them from names.
- Use a common `CircuitGraph` and parameter-group table, supporting different numbers of devices, nets and adjustable parameters; the graph object must not depend on a live bridge connection.
- Explicitly mark unknown devices and unresolved expressions. Unknown semantics involved in optimization must raise an error; never silently discard devices, ground them or fill values with zero.
- Store static topology separately from dynamic sizes/measurements. The learner already enables bounded static-template and complete-observation input caches by default, keyed by content digest. Learning updates borrow replay transitions through `ReplayBuffer.update_learner` (no deep copy, each observation digest computed once); public `sample()` still deep-copies. When gamma is exactly 0, updates skip the next-state batch/actor/target critic, with results and random state unchanged bit for bit (2026-10-06, record 7.221). Changes to sizes/specifications/schema must refresh the corresponding inputs; never cache embeddings made stale by encoder updates. Capacity and invalidation rules are in the [Graph contract](references/graph-contract.md).
- PyG batches must not create edges between circuits; padding, missing parameters and invalid measurements need separate masks.
- M1 already provides the fixed-semantics homogeneous export and dense node view in `graph/neural.py`; do not automatically concatenate device/net x columns with different meanings into supposedly shared semantics. Compute parameter-group batch offsets separately from group counts and node counts; see the [Graph contract](references/graph-contract.md).

### Learning and actions

- The actor outputs a distribution for every **independently adjustable parameter group** using a shared output head; do not create a dedicated fixed-length final layer for each topology.
- The critic explicitly receives graph state, specifications and actions, and binds each action to its parameter/device; it must not read only the pooled graph and ignore actions.
- Sharing structure and trained weights across circuits does not require actor, Q1 and Q2 to share all encoder parameters within one training run.
- Encoders return a common set of node, parameter-group and context representations and use the same SAC heads and action contract. GT and GATv2 attention read terminal edge features; RGCN uses terminal role × direction as relations (the old MLP/GCN controls were removed on 2026-09-26). Pretrain each architecture separately; do not load weights directly across architectures.
- Continuous SAC uses reparameterization, the tanh transform, the correct log-probability correction, twin Q functions, target Q functions and soft updates.
- Compute log-probability and entropy only over valid independent action dimensions per graph; count tied parameter groups once and exclude padding.
- Save both proposed actions and executed physical parameters. Specify which representation the critic uses; do not silently switch between replay and policy loss.
- Handle integer, finger, multiplicity and matching constraints through legalization; a continuous quantization proxy is not strict discrete/mixed-action SAC.
- Success depends on all required valid specifications together. Distinguish simulation failure, missing metrics, unmet specifications and infrastructure failure.
- `robust_score = nominal_reward - lambda_failed * failed_corners` is for post-validation only; any known failed corner disqualifies a design, and a high nominal reward cannot offset it. Preserve an incomplete status when conditions are missing or measurement/infrastructure fails; do not invent a complete pass rate or robust score.
- Save the encoder, actor, critics, target critics, optimizers, temperature parameter, normalizer, schema, vocabulary, configuration, random state and replay needed for recovery.

### Backends and real runs

- Prefer the user's chosen `virtuoso-bridge` / `virtuoso-bridge-lite`; read local upstream code or help before calling a verified API.
- The project's `Backend` methods are our abstractions; do not present them as built-in bridge methods.
- Explicitly label a mock backend as synthetic; never silently return mock success after the real backend fails.
- Before writing a schematic, confirm the target and current authorization, and use a copy/checkpoint or a verified recovery strategy; never overwrite the original design by default.
- Give every simulation job a unique directory and identifier; clean up only files and processes owned by this project.
- Pass the same PVT/MC context through netlists, request/result, graph observations and logs; distinguish nominal/pvt_validation/mc_validation. Explicitly report Monte Carlo as unsupported when it is unimplemented; never present repeated nominal simulations as statistical samples.
- Run in parallel only with isolated cellviews, sessions or immutable netlists (as parallel Spectre SAC does: one preparation process handles candidates serially, and each worker runs only its own netlists); otherwise do not modify the same Virtuoso design concurrently.
- Measure communication, parameter updates, netlisting, simulation, parsing and training time before discussing speed improvements; changing the bridge does not guarantee faster simulation.
- Do not hard-code hosts, usernames, PDK paths, model names or license paths; do not automatically upload private PDKs, netlists, waveforms or keys.

## Experiment and research discipline

- Distinguish new specifications on the same topology, new topologies in the same category, cross-category transfer and cross-PDK transfer. The last two are not validated capabilities of the first version.
- Freeze train/validation/test splits of topologies and specifications first; renaming or reordering the same circuit does not make it an unseen topology.
- Hyperparameter selection, normalizer fitting and replay must not use test data improperly; updating weights with test data is adaptation, not zero-shot.
- Report real simulation calls, failures/retries, wall-clock time, pass rate, time-to-first-feasible, final quality and training cost together.
- Encoder comparisons provide scratch/frozen/adapt for each architecture and retain random search and suitable non-RL baselines. Equal width/depth does not mean matched parameter counts; record parameter counts, pretraining costs and online costs separately.
- Check the original papers/code before discussing implementation details of the 2023 Li work, DEGT or other papers. Mark anything unconfirmed as "unverified"; do not invent reproduction or novelty claims.

## Built-in design review

When the user requests a review, critique, grill, feasibility check or a major change, give concrete questions and verification methods:

- Do the port-aware encoders (GT/GATv2 edge features and RGCN relations) actually use terminal information? Do M1 homogeneous/dense exports preserve column semantics, masks and group-index offsets?
- Does a variable-size graph still have a fixed action head? Is the critic actually action-conditioned?
- Does a difference come from the model, or from more simulations, pretraining data, wider parameter ranges or parallel resources?
- Does the reward treat missing/failed results as good results? Do parameter writes actually take effect?
- Is there leakage in the generalization split? Are zero-shot and fine-tuning separated?
- Can the current task first be accepted with one offline test or a single real simulation?

For each point, state the risk, evidence/missing evidence and an executable test. Do not merely endorse the architecture, and do not keep asking questions indefinitely instead of coding.

## Completion criteria

Deliver small runnable changes with corresponding tests; clearly distinguish executed work, static checks and work not run.
Complete the agreed milestone first; an unimplemented model skeleton or a long plan is not a substitute for acceptance results.
