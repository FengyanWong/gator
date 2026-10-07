# Six-circuit encoder run plan: A, B and C

Protocol version 1 — 2026-10-07 (Europe/London). Status: **plan written; no new runs started**.

Instantiated for GraphGPS and the parameter-group cross-attention encoder, with the recorded Graph Transformer runs
as references and two declared departures (the registry per stage, the temperature carried), in
[plan-encoder-comparison.md](plan-encoder-comparison.md) (2026-10-07, record 7.256).

The baseline suite is **OTA5t, OTA7t, LDO1, LDO2, RING3 and VCO_linear_c**. Repeat the same
experiment with each selected encoder. Graph Transformer is the reference encoder. A measures
learning from scratch, B measures transfer from that circuit's A model to another starting design,
and C measures transfer from one pooled general model to a third starting design.

This is the prospective runbook. It incorporates Claude's recorded A/B work and encoder-library
preparation, and the chat **“Revise plan and start task C”**, including the completed OTA8m recipe
follow-up. It does not rewrite their results or change registered tasks. Physical execution is a
later action; this request creates the plan.

## 1. What the previous work established

| Work inspected | Recorded outcome | Consequence for this protocol |
| --- | --- | --- |
| A: six specialist Graph Transformer runs | Four used 800 launches; both LDOs reached 1,500 under the old −5 dB HF PSRR target | Historical references, not six matched 800-launch baselines |
| B: twelve scratch/fine-tune runs | Loaded models had higher early passing shares on all six; the fixed 30-point criterion was met on three. LDO1 fell from 27% early to 7% late | Retain early and late measures, and measure deterioration |
| GraphGPS / cross-attention preparation | Twelve A-start tasks and scratch configurations prepared in `graphgps` / `xatten`; record 7.231 contains no real runs | Reuse these task copies after checking equivalence; prepared configurations need this protocol's registry/settings |
| C: six scratch/general pairs and OTA5t own-data control | General met the early criterion on 3/6, late criterion on 6/6. S and G used different learning recipes | Preserve the result as a recipe comparison; use matched recipes for the next study |
| OTA8m follow-up | At 800 launches: original G 24 passes; original-general weights with scratch's recipe 491; scratch 486. Final-third passes: 22, 217, 245 of 266 | Strong recipe dependence; no clear pretraining advantage from this one seed |

Historical C plus its required held-out experiment used 14,556 new Spectre launches. The later
follow-up added 1,388, for 15,944. These costs and verdicts stay with that experiment.
The old G recipe changed learning rate, update count and rehearsal together; its result cannot
identify which change caused the difference. The new primary comparison removes that bundle.

Evidence: [A/B plan and results](plan-finetune-vs-scratch.md),
[general-network plan and completed follow-up](plan-general-network.md),
[records 7.216–7.243](workbench-log/7.119-and-later.md), and
[new encoder implementation](global-encoders.md). This review checked documentation, saved
configuration/receipt data and the relevant loading/pretraining code; it did not repeat physical
simulations or independently re-run every historical audit.

## 2. Freeze these six circuit identities

| Display name | Canonical existing A task | Existing B / C suffix | Existing encoder-library suffix | Lanes |
| --- | --- | --- | --- | ---: |
| OTA5t | `real:mscr_ota5t` | `_b` / `_c` | `ota5t` | 4 |
| OTA7t | `real:mscr_ota7t_w` | `_b` / `_c` | `ota7t_w` | 1 |
| LDO1 | `real:mscr_ldo1_rgcn` | `_b` / `_c` | `ldo1` | 4 |
| LDO2 | `real:mscr_ldo2_rgcn` | `_b` / `_c` | `ldo2` | 1 |
| RING3 | `real:mscr_ring3` | `_b` / `_c` | `ring3` | 4 |
| VCO_linear_c | `real:mscr_vco_lin_c` | `_b` / `_c` | `vco_lin_c` | 4 |

OTA7t here always means the **width-enabled** variant. `_rgcn` is part of the historical LDO
task name; it does not select the run's encoder. `VCO_linear_c` names the constrained linear-VCO
task above, not the earlier `mscr_vco_lin` task. The `c` inside `vco_lin_c` is part of its circuit
identity; its third-start task is `mscr_vco_lin_c_c`.

Use LDO1 `psrr_hf_db <= -3 dB` and LDO2 `<= -2.3 dB` in **all new A/B/C arms**. Keep every
other saved target, equation, unit, hard/soft flag, scale, parameter bound, quantization step,
tie, fixed bias, measurement, analysis, PDK and initial condition identical between encoders.
Keep Scale 6 on the existing dB rows. Targets come from the existing B/C comparison, not from
new runs. Preserve each circuit's own bench voltage; there is no suite-wide voltage override.

The old strict-target LDO A runs cannot be presented as matched controls for new relaxed-target
A runs. Re-scoring their archive is allowed for a declared offline source pool; it does not
turn their original training into a relaxed-target run.

Freeze starts once, before selecting or running another encoder:

| Stage | Physical starting design | Pilot seed | Meaning |
| --- | --- | ---: | --- |
| A | Existing canonical A design; encoder-library A copies reproduce it | 0 | Independent specialist training |
| B | Existing saved B design, selected by the historical median-valid-nonpassing rule | 1 | Same topology/specifications, new starting observation |
| C | Existing saved C design, selected by the historical 25th-percentile rule excluding A/B starts | 2 | Same six circuits, third starting observation |

Reuse the **selected parameter vectors**, not a fresh quantile selection from each encoder's
own outcomes. The C selections and source hashes are in
`artifacts/general-network-20261006/start-c.json`; B selections and source references are in
the A/B plan and its configuration folder. Parameter rows may have `initial_value: null`:
freeze the actual saved task/base graph and restored physical values, not just that field.
Changing starts does not create an unseen topology. Absolute actions can jump anywhere in
the legal domain, so B/C measure transfer under a changed reset observation, not local search
distance from a worse design.

## 3. Shared settings and allowed encoder changes

Use these settings for every primary **learning** arm, including fine-tuning:

| Setting | Frozen value |
| --- | --- |
| Nominal budget | 800 charged Spectre launches; evaluation cap 800; no early success stop |
| Learning rate / updates | `1e-3` / 8 updates per admitted transition, `update_every=1` |
| Batch / replay / warm-up | 8 / 10,000 / 8 admitted warm-up transitions |
| Discount / target update | `gamma=0`, `tau=0.005` |
| Temperature | Start at `initial_alpha=0.01`; primary fine-tune arms set `reset_temperature=true` |
| Other SAC controls | Inherit S's explicit values: `alpha_learning_rate=null`, target entropy per action 1, max gradient norm 10 |
| Episodes | Length 4; `episode_terminates_on_success=false` |
| Adaptation | Train the whole model; `freeze_encoder=false`, `encoder_only_transfer=false`, `reset_critic=false` |
| Online data | Empty target replay and fresh optimizers/counters at each start; `rehearsal=null` |
| Reward | Existing starting reward: compressed misses, worst-spec share 0.5, objective/margin weights 1, compressed objective; copy the full reward block |
| Conditions / inputs | Nominal only (`off`); standard component vocabulary; operating-point inputs off |
| Concurrency | Circuit-specific lanes in section 2; same hardware/thread limits within comparisons |

Resetting temperature in the primary loaded arms is a deliberate prospective change from the
historical full-state transfers. It makes initial entropy temperature equal to scratch while
actor, twin critics and target critics retain their pretrained weights. Carrying learned alpha
is a separately labelled option, not a silent change to the primary recipe. Freeze all omitted
runtime controls too by copying the canonical S configuration, including cache/reset policy,
retry limits, timeout and checkpoint cadence.

Use **one fixed spec registry in A, B, C and offline training**. Reuse the audited 41-slot list
and references from `artifacts/general-network-20261006/training/spec_registry.json` after checking
its schema and hash. Unused slots remain masked. Keeping these slots does not permit extra
circuits into the six-circuit source pool. This avoids the old specialist/global-schema mismatch.
Do not derive a fresh registry from each circuit's UI scales or from test observations.

| Encoder ID | Primary structural input | Existing library, if prepared |
| --- | --- | --- |
| `graph_transformer` | `none` | `MScR` |
| `rgcn` | `none` | Reuse equivalent saved tasks |
| `gatv2` | `none` | Reuse equivalent saved tasks |
| `graph_gps` | `rwse` | `graphgps` |
| `group_cross_attention` | `none` | `xatten` |

Start at hidden dimension 48, four layers and four heads where applicable. Record each actual
model contract and actor/Q1/Q2 parameter counts; equal dimensions do not mean equal parameter
counts. GraphGPS with RWSE is a comparison of that preset, not an isolated attention ablation.
A `graph_gps`/`none` run is an optional structural-input ablation.

Each encoder gets its own newly trained weights. Never load a GT checkpoint into another
architecture. Raw archived transitions can be shared across encoders after contract checks;
weights cannot. Old GT runs also need matched new controls if their registry, targets,
temperature policy or source differs. No architecture-specific tuning on B/C results.

## 4. Baseline qualification before learning

Require a qualified baseline for each of the 18 circuit/start combinations: starting design
plus **64 seeded random draws**, with zero learner updates. Use the stage's seed. A baseline
can qualify with zero passing designs; it establishes measurement behavior and restoration,
not an attainable pass-rate threshold. Keep explained design failures, including absent unity
crossings, as failures. Infrastructure faults or unexplained missing required measurements
block that task's dependent runs until resolved.

Baselines belong to the circuit/start contract, not to an encoder. Reuse an existing baseline
when task semantics, parameter vector, bench, measurements, targets/scales and runtime
measurement behavior are verified equivalent and its archive is intact. A new library/cell
copy needs a recorded equivalence mapping and Check now; a name alone proves nothing.
Otherwise qualify that combination before learning. Do not launch 18 new baselines simply
because a new encoder is selected.

Nominal qualification cost is 18 × 65 = **1,170 launches** when none can be reused. The previous
six C baselines actually used 391, not 390: a paid reset displaced a random draw in LDO2 and
required a supplemental draw. Count draws and charged launches separately. If overhead would
exceed a frozen cap, stop at the cap and revise the budget explicitly; never manufacture a
complete 64-draw record. Keep calibration/baseline data out of pretraining and initial replay.

## 5. Task A — six independent specialist models

For encoder E, run `A-S(E, circuit)` from random weights on each A start: six runs × 800.
Use the relaxed LDO targets and common registry from the beginning. Save the final checkpoint
and its architecture, code/dependency/schema hashes, physical task snapshot and launch ledger.
These six models are the only parents for this encoder's Task B specialist-transfer arms.
Use the fixed final checkpoint, not the best checkpoint selected after seeing B outcomes.

Question: how well does E learn each circuit with the same simulation and learning budget?
Compare E with the matched GT A runs circuit by circuit. A does not measure transfer.

## 6. Task B — same-circuit transfer to start B

Run two independent 800-launch arms on each B task, both seed 1:

| Arm | Initialization | Learning/data |
| --- | --- | --- |
| `B-S` | Random weights | Shared recipe, target-only |
| `B-F` | Final A-S checkpoint of the same encoder and circuit | Same recipe; pretrained networks, reset temperature, fresh optimizers/replay |

Use the same B vector, rows and lanes in each pair. Do not continue the A run in place and do
not inject its replay into B-F. Record the parent checkpoint and explicit loaded/reset fields.
This is the prospective counterpart of Claude's A→B experiment, with consistent LDO targets
and a registry that also supports Task C. Cost: **9,600 launches per encoder**.

## 7. Task C — one general model, then six independent start-C pairs

### 7.1 Fix the offline data before comparing architectures

The primary C experiment uses **the same archived data for every encoder**. From the old
22-run request at `artifacts/general-network-20261006/request.json`, select exactly the six
canonical A task IDs in section 2 and their B IDs: six A runs plus twelve B runs, **18 archives**.
Their recorded evaluation cost is **15,800** (6,200 A + 9,600 B); training-eligible transitions
are fewer and must be counted by the audit. Exclude `mscr_vco_lin`, `mscr_ldo2_rgcn_gt`,
`mscr_ldo_basic`, every C run, all baselines/probes and every OTA8m run.

This narrows the historical 17,124-evaluation pool to the requested six-circuit suite. It also
means the old general checkpoint is a historical reference, not this study's GT checkpoint.
Filter by explicit saved task IDs and pin run IDs/archive hashes; never glob all of `outputs/`.
Verify the 18 archives still match their hashes and their recorded costs before training.

Preserve the existing validated relabelling of strict-target LDO A transitions to −3/−2.3 dB.
Recompute both states consistently, first verify unchanged-target reward reproduction, and
retain original provenance. Split **whole episodes**, 90% train / 10% validation, before
relabelling; derived samples stay with their original episode. Freeze the exact split once per
repetition for all encoders. Use task-balanced sampling across the twelve A/B task identities; each circuit
therefore has equal total representation. Validation data never enter update batches.

Train a new general model of E with **20,000 offline SAC updates**, batch 8, seed 0, shared
41-slot registry, section 3's learning rate/gamma/alpha/tau and E's architecture. Checkpoints
every 1,000 updates; select the fixed 20,000-update checkpoint. Record per-task held-out critic
error, actor proposals, legal-action checks and validation curves. Offline critic predictions
do not establish actual circuit feasibility, even with gamma 0; simulator probes remain needed.
Review and publish via the existing workbench pretraining/diagnostics/publication path.

Train the OTA5t-only control with the same method and registry on its three selected A/B
archives (2,400 historical evaluations, overlapping the general pool). This is arm O's parent.

The full A→B→C **end-to-end variant** may instead train E's general model on E's own eighteen
new A/B archives (14,400 evaluations at the new fixed budgets). Label it `C-own-data`, freeze it
before C, and report it separately: different encoders then supplied different training data.
Do not pool a later encoder's extra runs into only its general model, or combine results from
this variant with the primary `C-common-data` table. It needs its own C runs/budget if both
variants are evaluated. No new source simulations are required for primary C.

### 7.2 Frozen probes and matched adaptation

First qualify all six C baselines. Run a **300-launch sampled frozen general probe on each C
start**. This intentionally replaces the old probes' B starts, allowing direct start alignment.
Keep weights, alpha and normalization fixed; zero updates and no probe replay carried into
adaptation. Report policy proposals, reset checks, duplicate executed designs and total costs
separately. These are known-circuit probes without online learning, not unseen-topology tests.

Then run the following, each from an independent fresh run, seed 2, 800 launches:

| Arm | Circuits | Parent | Online recipe |
| --- | --- | --- | --- |
| `C-S` | All six | None | Section 3 |
| `C-G` | All six | E's original common-data general checkpoint | Same as C-S; target-only, reset temperature |
| `C-O` | OTA5t only | E's OTA5t-only offline checkpoint | Same as C-S/C-G |

Each C-G starts from the **same original general checkpoint**. Never feed the adapted OTA
model into the subsequent LDO or VCO run. Do not return C observations to the source pool.
C-O checks the offline specialist route and pooled-versus-specialist performance on the same
C task; the old B result at another seed/schema is only context.

Costs per encoder: frozen probes **1,800**, C-S/C-G **9,600**, C-O **800**. General and own-model
pretraining add CPU/GPU work, no new Spectre launches, and separately reported historical cost.

## 8. Measurements and decision rules

Use the same comparison code and exact fractions for every arm. Preserve failures in passing
share denominators. Report operational faults separately; incomplete budgets cannot be labelled
completed paired comparisons. Record both committed evaluations and charged-launch counts.

- **Primary early measure:** passing share of committed evaluations 9–108, matching the old
  fixed window. It is not necessarily 100 policy proposals because of resets and concurrent
  warm-ups. Also report the first 100 actual policy proposals and their charged cost.
- **Learning efficiency:** cumulative passes at charged costs 100/200/400/800, with pending
  results identified; charged cost to the first completed 100-evaluation window with ≥50% and
  ≥75% passing. Treat unreached thresholds as censored. The user's 75% operational target is
  retained as a secondary measure; primary arms still complete their fixed budgets.
- **Final performance:** last `floor(N/3)` committed evaluations (266 when N=800), final 100,
  total passing/valid shares, raw required metrics and per-row failures, reward and worst
  constraint violation. Report duplicate/unique designs and best achieved quality too.
- **Cost:** real launches including failed/retried/reset work, candidate counts, actual learner
  updates, wall time and resource settings; offline training and historical source cost apart.
  First feasible design/time is a footnote, not the main transfer claim.

For B-F versus B-S and C-G versus C-S, retain interpretable historical thresholds:

| Criterion | Rule |
| --- | --- |
| C1, early benefit | Loaded early passing share exceeds scratch by at least 30 percentage points |
| C2, late preservation | Loaded final-third passing share is at least scratch minus 5 points |
| C3, LDO feasibility | Loaded arm has at least one all-required-spec pass at the fixed relaxed target |
| C4, within-task deterioration | Loaded late share is at least its early share minus 10 points; its initially weakest row's failure share rises by no more than 15 points after evaluation 200 |

Choose the weakest row by failure share in the first 200 evaluations, tie-break by metric ID;
missing/invalid required rows count as failures. Always report every row. C4 can pass for a
policy that remains poor: it is not proof of successful transfer or retained source knowledge.

Report per-circuit deltas first. For continuity, a pilot meets the B suite rule when C1+C2 hold
on at least 5/6; it meets the C suite rule when C1 holds on ≥4/6, C2 on 6/6 and C4 on ≥5/6.
Missing a threshold is reported as **“the predefined suite criterion was not met”**, together
with the gains actually measured. It is not evidence that every circuit has zero benefit.
For C-O, report O−S, G−S and G−O on this same start; do not impose GT's historical 90% early
share on all encoders.

One seed per stage is a pilot. For repeatability, predeclare three full repetitions before
viewing new results: A/B/C seeds `(0,1,2)`, `(10,11,12)`, `(20,21,22)`; offline seeds 0/10/20,
same physical starts. The existing pretrainer uses its seed for both the episode split and
model/sampling randomness: pin all three splits in advance, and use the identical split across
encoders within a repetition. Pair seeds between encoders and methods, report
individual runs and circuit-level paired differences with uncertainty. Do not select extra
seeds only for favorable or borderline circuits. Historical evidence already informed this
protocol, so it is not a new blind test of GT generalization.

## 9. Drift prevention and unseen circuits are separate extensions

Primary fine-tuning uses matched learning and target-only batches. No automatic switching to
scratch, selective reset or adaptive recipe change is part of it.

For a rehearsal ablation, add `C-G-R`: same general parent, temperature policy, `1e-3` learning
rate and eight updates, but four target + four source-training samples per batch. Everything
else stays fixed. This isolates the replay change; it costs 800 per selected circuit. The old
`2e-4`/two-update/half-source recipe may be reproduced as a **historical bundle**, never relabelled
as this one-factor ablation. A learning-rate or update-count ablation changes only that setting.

Measure source retention on a fixed source validation bank before/after adaptation: action
changes and critic errors are diagnostic only. A claim about retained physical performance
needs separately budgeted frozen source-task probes, with identical before/after protocol.
Do not select a “best” checkpoint using C test results and report it as the fixed final model.

Keep **OTA8m outside the six-circuit baseline and all source pools**. It is an optional seventh
evaluation task, using the already frozen revision-2 goals, qualified baseline, and matched
300 frozen / 800 scratch / 800 general protocol. It is a series-RZ compensation variant of
OTA7t, not a new amplifier family, and its results have already informed recipe choices. A
fresh claim of unseen-family generalization needs a genuinely new, prospectively frozen
topology. Leave-one-out and a new folded-cascode design are not required by this runbook.

## 10. Budget worksheet

| Work | New launches per encoder / pilot |
| --- | ---: |
| A: six scratch | 4,800 |
| B: six scratch + six specialist fine-tune | 9,600 |
| C: six frozen probes | 1,800 |
| C: six scratch + six general fine-tune | 9,600 |
| C: OTA5t own-data control | 800 |
| **Primary total** | **26,600** |

Add circuit/start qualification once: **0 if all 18 equivalent baselines can be reused**, up
to 1,170 nominal launches if all need measurement, plus explicitly budgeted overhead. Different
physical configurations may require separate qualification. Baseline reuse is established in
the manifest; it is not assumed merely to reduce the budget.

For K encoders and R repetitions, primary policy cost is **26,600 × K × R**. Reusable baseline
qualification and historical source collection are not multiplied by encoder count. The fixed
15,800-evaluation pool is shared, and OTA5t's 2,400 is a subset, not another acquisition cost;
offline compute is incurred for each separately trained model/repetition. Example: the two
new encoders need 53,200 primary launches for one pilot each, plus qualification as required.
Including a newly matched GT reference makes that 79,800 for three encoders.

Optional additions: six rehearsal arms +4,800; OTA8m extension +1,900 with an accepted existing
baseline or +1,965 nominally with a new baseline; full `C-own-data` probe/S/G/O set +12,200
(reuse C-S only if its entire frozen contract and repetition match). Random search and an
appropriate non-RL optimizer need equal 800-launch budgets on each selected target: +4,800
per method for six C tasks, shared across encoders. The 64-draw baseline is a calibration
sample, not an equal-budget random-search comparator. Current workbench Search is SAC-only;
a real non-RL harness must be verified or built separately before claiming algorithm superiority.

These are prospective budgets, not authorization to run every encoder or extension. Finish
fixed-budget arms even if 75% is reached early. Any later continuation is a separate curve;
preserve the original 800-launch snapshot for the paired comparison.

## 11. Execution handoff

1. **Freeze the study.** Select encoders/repetitions and materialize a manifest with protocol
   version, six canonical IDs, A/B/C vectors, task/graph/bench/config hashes, registry and
   reward, seeds, lanes, budgets, source runs/split, checkpoint selection, metrics and queue
   order. Alternate scratch/loaded order using a schedule fixed before results. Record
   encoder parameter counts and compute resources. Store under a new experiment directory.
2. **Pin executable source.** The current workspace has uncommitted pretraining/rehearsal
   work from Task C. A plain archive of HEAD omits it. Snapshot the reviewed full runtime,
   dependencies and file hashes; keep the optimizer digest unchanged. Do not edit another
   session's code or old archives. Prove schema, mixed-graph batch isolation, load/reset,
   frozen and resume behavior offline for the selected architectures.
3. **Prepare task/config copies.** Reuse `graphgps` and `xatten` A tasks where equivalent;
   point new B/C configs at the frozen B/C task or an explicitly equivalent owned copy.
   A task does not force an encoder. Keep original cells and old run configs intact. Produce
   new configs for the common registry and temperature policy; do not execute the old
   twelve-run `queue.sh` unchanged and call it this protocol.
4. **Qualify baselines**, then run A and B. Check task/editor/cell agreement before and after
   every run, preserve restoration evidence, use isolated simulation lanes and the existing
   session lock. Read the daemon's nonce-cache capacity for parallel runs as the existing
   queue does; do not silently repair bridge settings or start a tunnel.
5. **Prepare C's fixed pool.** Filter and audit the 18 explicit archives, verify/relabel/split,
   train each architecture separately, review diagnostics, publish general/own checkpoints,
   and prove compatibility with all C configs before opening simulator lanes.
6. **Run C**, independent frozen/S/G/O runs, using the same original parents. Complete the
   fixed matrix, then compute the criteria. Do not tune a failing encoder midway, drop its
   failed circuits or revise goals after examining its output.
7. **Audit and deliver.** Check initial physical parameters; parent weights and resets;
   target-only replay; actual update counts; frozen tensor invariance; ledger costs; source
   pool exclusion; unchanged source hashes; and final restoration. Save a machine-readable
   per-run and paired table, plus the interpretation bounded by seeds and task lineage.

Existing entrypoints are `gator_workbench.cli validate CONFIG`,
`gator_workbench.cli pretrain REQUEST --output NEW_DIRECTORY --audit-only`, the same pretrain
command without `--audit-only`, and `gator_workbench.cli run CONFIG`. Real execution uses its
explicit authorization/transfer flags only after the chosen run scope is authorized. Publication
and baseline/audit scripts are available in the historical experiment but have pinned old paths;
adapt copies into the new experiment directory. This document is a run specification, not a
claim that a new all-encoder queue or its runnable configuration set has already been generated.

Useful local starting points:

- `artifacts/local/reviews/encoder-libraries-2026-10-06/`: prepared GraphGPS/XAtten A tasks/configs.
- `artifacts/local/reviews/finetune-vs-scratch-2026-10-06/`: B configs, source models and comparison.
- `artifacts/general-network-20261006/`: C starts/configs, archive request, registry, qualification,
  source snapshot, offline publication and completed audits.
- `artifacts/general-network-20261006/ota8m-recipe-followup/`: immutable G-800 snapshot and the
  matched-recipe follow-up; preserve it when comparing with the historical result.
