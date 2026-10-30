# Performance and learning efficiency: functionality review and Claude handoff

Date: 2026-10-05. Status: **plan only; no runtime or training changes implemented by this review**.

**Scope narrowed by the user:** the current implementation handoff is
[Lower- and moderate-risk performance improvements](plan-low-moderate-risk-performance.md), covering only original
proposals #1, #2, #4, #5, #7 and #8. The other proposals below remain reviewed possibilities outside that work.

User request: check whether all 13 previously proposed improvements affect functionality, then prepare a plan for
Claude to work on them. The numbering below matches that proposal list. This document is the execution handoff;
writing it does not start experiments, change settings, deploy code, or authorize new Spectre or paid-agent work.

## 1. Decision for each proposal

Several proposals can preserve the training calculation, but they are not all transparent speedups. “Preserves
behavior” below means the same valid inputs, sampling sequence, update schedule and budget produce the same
learning state and outputs. Timing values will change. Under a wall-clock stopping limit, even a faster equivalent
implementation can collect more designs and therefore end with a different model.

| # | Proposed improvement | Functionality impact | Decision for implementation |
|---|---|---|---|
| 1 | Skip unused future-value work when gamma is zero | Can preserve valid-run arithmetic, but removing the next-action sample changes RNG consumption and later actions unless compensated. Optimizer edits also change checkpoint compatibility. | Implement a conditional, equivalence-tested path. Read the run's actual gamma; never set it to zero for speed. |
| 2 | Remove replay sampling deep copies | A direct removal breaks the current mutation-isolation contract. Frozen dataclasses contain mutable dictionaries and graphs. | Preserve the public copying API; add a protected internal learner path only after ownership and mutation tests. |
| 3 | Overlap collection and learning | Changes the policy version used to propose candidates, replay availability, completion order and possibly first-feasible behavior. Off-policy SAC does not make these changes equivalent. | Separate optional scheduling mode, default off. Keep the existing synchronous mode and prove recovery/budget correctness first. |
| 4 | Reduce CPU contention | No intended algorithm change. Thread counts, lane counts, timeouts and wall-time budgets can nevertheless change results. | Resource guidance and explicit launch controls; no automatic changes to user jobs, worker counts or VM allocation. |
| 5 | Cheaper graph input-cache keys and better capacity | Can preserve input tensors. Unsafe identity keys or mutable cached objects cause stale inputs; larger caches consume memory. | Build on #2's immutable ownership, with content-key fallback and a bounded memory budget. Never cache trained embeddings. |
| 6 | Cheaper checkpoints and storage | Can preserve restored state; changing snapshots, acknowledgements or pruning can break crash recovery and output consumers. | Profile first. Prototype versioned immutable replay storage if material; keep durability and existing output capabilities. |
| 7 | Faster chart data preparation | No intended learner change. Slicing too early can change smoothing, cumulative values, gaps, restarts and comparison alignment. | Preserve displayed values and metadata, then share per-frame work and update incrementally. |
| 8 | Cheaper training API polling | No intended learner change. Incorrect invalidation can hide new data, duplicate rows or show stale run state. | Cache immutable/append-only work with explicit replacement detection; preserve the response and cursor contract. |
| 9 | Download waveforms only when retained | Measurements may stay identical, but available files, failure diagnostics, remote cleanup and retry behavior can change. Some profiles need local raw files. | Capability-gated prototype, default off until backend and retention parity are demonstrated. |
| 10 | Reuse calibration observations in replay | Deliberately changes the training data and warm-up. Current calibration and training also have different episode horizons. | Explicit optional import with compatibility and provenance checks. Reject incompatible old data; do not automatically copy calibration replay. |
| 11 | Compare 4/8/16 updates per transition | Deliberately changes learning dynamics, training cost and potentially convergence/quality. | Controlled experiment using existing settings; retain the current configured value and presets. |
| 12 | Compare smaller encoders | Deliberately changes model capacity, learned behavior and weight compatibility. | Controlled same-architecture experiment; no automatic resizing of saved models or replacement of starting presets. |
| 13 | Use resume/fine-tune where appropriate | Resume continues compatible state; fine-tune intentionally resets some state and can help or hurt. These modes already exist. | Verify and document existing workflows, then compare explicit source choices. No automatic mode or model selection. |

**Cross-cutting compatibility:** every edit to any Python file under `src/analog_optimizer/` changes
`training/sac.py::source_digest()`. Existing full checkpoints require their original source and library versions.
Even #1, #2 or #5 with exact numerical parity cannot promise old checkpoints will load under the changed package.
Never bypass this check or rewrite an old checkpoint's digest to claim compatibility.

## 2. Evidence and current implementation

This review inspected the shared checkout while other sessions were working. Observed HEAD:
`223cca9952ba6592408fbc7aa1101cf037477fdd`. This is an inspection anchor, not a claim that the working tree was clean.
Calibration, editor, task-saving and layout changes were in progress; records 7.211 and 7.216–7.218 were reserved.
Recheck their completed code before implementation. Do not restore these files to this review's versions.

Useful starting points:

- [Project rules](../CLAUDE.md), [optimizer skill](../.agents/skills/analog-optimizer/SKILL.md),
  [current decisions](decisions.md), [function map](functionality-reference.md), and the workbench specification
  `gator_claude_code_fable51_frontend_data_outputs_en.md` at the repository root.
- [Original profiling provenance](../artifacts/local/performance-audit-20261005/provenance.json),
  [training measurements](../artifacts/local/performance-audit-20261005/training-profile.json),
  [chart measurements](../artifacts/local/performance-audit-20261005/chart-profile.json), and
  [I/O measurements](../artifacts/local/performance-audit-20261005/io-profile.json). Reproduction scripts are beside them.
- [Current presets](network-presets.md) and
  [preset experiment evidence](../artifacts/local/reviews/starting-presets-2026-10-05/README.md).

The training microbenchmark used synthetic opamp observations, batch 8, one CPU thread, warm caches and 15 timed
updates per encoder. It measured full update medians of approximately 54/91/131 ms for GT/RGCN/GATv2. Replay
sampling added about 8–9 ms per batch. The next-observation preparation, next actor and target critics together cost
about 20–21% of an update with gamma zero. That percentage is measured work, **not a demonstrated end-to-end speedup**;
preserving RNG consumption has a cost, and phase savings overlap across proposals.

Eight chart builds on a changed frame took approximately 3 ms at 8,000 updates and 84 ms at 200,000, even when viewing
the latest 1,000. This excluded browser rendering. The current chart has since gained further features; benchmark
the actual implementation being changed. The small JSONL/fsync test showed no Linux `/tmp` advantage over D:, so
do not recommend moving all outputs based on that test.

Do not redo optimizations that are already present:

- The learner already caches raw observation tensors and static topology templates (2,048 observations/64 templates).
- The Training tab already polls only while relevant, bounds retained rows, and caches each chart until its inputs
  change. The API already returns bounded journal cursor pages. New work is below these existing mechanisms.
- `_reuse_final_checkpoint()` already avoids rewriting a periodic checkpoint when the final state is identical.
- Simulator scratch and adapter journals already have configurable native Linux locations; reset reuse, reduced
  native exports/readbacks, model-library trimming and reduced unused simulator output already exist.
- Workers already set Torch to one CPU thread. Resume and fine-tune are implemented.
- Persistent Spectre is not an additional quick win: the [recorded trials](plan-persistent-spectre.md) produced
  incorrect results for length/multiplicity changes. Do not enable it as part of this plan.

## 3. Execution rules and release boundaries

When asked to execute this plan, first re-read current rules/status and inspect the diff. Keep unrelated edits and
the shared index intact. Do not commit, push, rebuild the served frontend, restart the backend, or change live task
settings merely because this handoff exists.

1. Establish an isolated implementation checkout/snapshot and scratch settings/output directories. Old workers must
   continue to use their original source. Editing optimizer files beneath a running worker is particularly unsafe:
   the process may retain imported old code while `source_digest()` reads new files at its next save.
2. Set `GATOR_WORKBENCH_SETTINGS_DIR` before importing workbench modules in every scratch process and its children.
   Label synthetic data `origin=synthetic`, `provenance=mock`, and put it under a `mock/` output directory.
3. Preserve user-selected gamma, learning rates, alpha, batch size, episode rules, update ratio, architecture, reward,
   conditions and action semantics. Missing legacy values keep their established meaning; do not alter schema
   defaults or saved configurations to make an optimization apply.
4. Treat #1/#2/#5 as one coordinated optimizer release for compatibility planning, while keeping individually
   reviewable changes and tests. Record the final source digest and original-code recovery instructions. Default-off
   switches do not prevent digest invalidation when files have changed.
5. #3/#9/#10 remain optional capabilities. #11/#12/#13 are experiments/workflow choices, not silent default changes.
   Experimental settings must be explicit in the run configuration and recorded in checkpoints/manifests.
6. Real Virtuoso/Spectre tests, schematic writes and paid calls need the existing project's explicit authorization and
   a bounded budget. Prepare offline code, tests and an exact run matrix first; historical budgets from other chats
   are not available to spend. Do not start/stop the bridge daemon/tunnel or other sessions' jobs.

## 4. Work packages

### 1 — Conditional gamma-zero path

**Code:** `src/analog_optimizer/training/sac.py::SACLearner.update`,
`src/analog_optimizer/models/graph_transformer.py::GroupActor.sample`.

The current code builds the next batch, samples the next actor and evaluates both target critics before multiplying
their contribution by the selected gamma. With exactly zero gamma and finite valid state, the target is the reward.
This says nothing about what gamma the user should choose.

Implementation:

1. Branch on `self.config.gamma == 0`, not a preset name or an approximate-zero threshold. Every nonzero value keeps
   the existing bootstrap calculation, including terminated-state masking. Keep target networks, soft updates,
   checkpoint fields, actor/critic/temperature updates and transition validation.
2. First omit only the target critic forwards, retaining the next actor sample. This preserves its RNG draw and is
   a useful conservative milestone even if the full optimization is not viable.
3. To omit next-batch construction and the actor forward too, explicitly reproduce the discarded sample's RNG
   consumption from the validated packed action shape, dtype and device. The current actor uses `Normal.rsample()`
   and current encoders use zero dropout. Do not assume an arbitrary `randn` call consumes the same sequence.
   Use the pinned libraries and prove equality for all supported shapes. If that cannot be proved, keep step 2.
4. Retain invalid-transition, origin, reward, condition and action-contract rejection. A skipped branch no longer
   diagnoses non-finite values in that unused computation; document that limit and retain meaningful finite-state,
   loss and gradient checks. Do not claim parity for corrupt learner state.

Acceptance: reference and optimized paths give identical losses, target values, parameters, target parameters,
optimizer states, alpha, RNG states and subsequent actions over multiple updates on all three encoders. Cover gamma
0, a small nonzero value, 0.5 and 0.99; mixed graph/action sizes; terminal and bootstrapping transitions; batch size 1
and odd packed action counts; warm/cold caches and save/resume. Test nonzero gamma independently of the gamma-zero
reference so a branch accidentally forcing gamma to zero cannot pass.

Extend `tests/test_graph_sac.py` and `tests/test_input_cache.py`. Compare same-seed trajectories in a fixed offline
schedule. Report achieved update speed and whole synthetic-run speed separately.

### 2 — Replay sampling without copying entire graphs each update

**Code:** `src/analog_optimizer/training/replay.py`, learner call sites in `src/gator_workbench/engine.py` and other
collectors found by searching for `replay.sample`.

The existing public behavior is tested: mutating a sampled proposal must not alter replay. `@dataclass(frozen=True)`
does not protect its nested objects. Do not replace `deepcopy(self._rng.sample(...))` with a bare shared list.

Implementation:

1. Preserve admission validation and the owned copy on admission. Preserve public `sample()` mutation isolation.
2. Add an internal sampling path used only by the learner, with a clear lifetime/ownership contract. Prefer an
   immutable prepared representation or an encapsulated read-only borrow; writable replay objects must not escape
   to general callers. Prepared batches must allocate their mutable tensors/metadata independently.
3. Sample the same indices, without replacement, using the existing replay RNG and ring order. Do not simultaneously
   switch to NumPy/Torch sampling or change how often sampling occurs.
4. Keep validation at untrusted boundaries and the learner's reward/origin/condition checks. Do not remove repeated
   checks merely on the assumption that a dataclass is deeply immutable. Optimize validation only as separately
   proven work if an immutable representation actually establishes that invariant.

Acceptance: mutate original admitted data, public samples, batch tensors and nested metadata; stored transitions and
future batches remain unchanged. Learner updates cannot mutate replay. Ring wraparound, repeated samples, eviction,
checkpoint restore, database-backed replay and rejected transitions retain behavior. Fixed-seed sample IDs, RNG
state and resulting updates equal the old path. Preserve the existing mutation test in `test_graph_sac.py`.

### 3 — Optional overlap of collection and learning

**Code:** `src/gator_workbench/engine.py::_loop/_commit/_maybe_update/_dispatch/_checkpoint`, `lanes.py`, ledger and
search scheduling; optimizer parallel collectors only if they need the same explicitly scoped feature.

This is a behavior change. Currently `_commit` performs the configured updates before the scheduler continues;
dispatching sooner means some actions come from an older policy. Reordering admissions changes replay samples too.

Implementation:

1. Instrument result-ready time, result-received time, durable commit time, queue wait, dispatch policy version,
   replay sample time, update time and checkpoint wait. Existing result elapsed time can include scheduler delay;
   do not relabel it as simulator-only time.
2. Keep one owner of the learner, its optimizers and training RNG. Never perform inference concurrently on tensors
   being updated. Use explicit immutable policy snapshots and a separate recorded action RNG if inference is moved
   to a collector. This is a versioned scheduling/RNG contract, not old-trajectory parity.
3. Keep one dataset writer and one ledger owner. Use bounded queues and explicit backpressure. A collected transition
   must have durable admission before it is acknowledged/consumed by asynchronous learning. Record pending update
   work, the sample/admission boundary and applied-update watermark so recovery neither loses nor repeats updates.
4. Freeze a scheduling rule before testing: which completed results are admitted in which order, when update debt
   is generated, which replay boundary each update can sample, and maximum policy lag. Initial prototype: at most
   one update group of lag (the configured `updates_per_transition`), recorded explicitly; it must wait rather than
   silently exceed its limit. Do not increase the configured update-to-data ratio.
5. Define pause, abort, first-feasible stop, manual save, periodic save and shutdown barriers. Stop new dispatch,
   account for in-flight/uncertain simulator work, finish or durably record pending training work, then publish a
   consistent checkpoint. Define forced cancellation separately. No background writes after the run lock releases.
6. Initially support ordinary SAC only. Reject unsupported combinations explicitly until LLM-only, LLM warm-up,
   initial-learning, frozen and corner-training schedules have dedicated coverage. Default synchronous mode remains
   unchanged. Do not publish an unsupported combination as generally available.

Acceptance: synthetic lanes with deliberately out-of-order completion, learner delay, failures and cancellation;
no overspend, duplicate admission/update or concurrent model mutation. Crash at each handoff and checkpoint boundary;
restored queues/counters/RNG agree with the documented schedule. Test one and multiple lanes. Then compare sample
efficiency and wall-time with the old mode; mathematical SAC validity alone is insufficient acceptance.

### 4 — CPU resource policy

**Code/workflow:** worker launch configuration, local test runners and operating instructions; inspect existing
`src/gator_workbench/worker.py` thread controls first.

Separate host contention from model cost. The recorded RGCN run was slower while a 12-worker test suite competed for
the same machine/VM CPU; that is useful operational evidence, not a new controlled benchmark.

Implementation: document a quiet-run profile, retain one Torch thread unless a benchmark supports another explicit
choice, and expose/record resource controls only where missing. Prefer lower concurrency for this project's tests
when simulations are active. Do not automatically kill, suspend, renice or change affinity of unrelated processes.
Do not silently reduce simulation lanes: it changes collection order and throughput.

Acceptance: record effective process/thread/lane counts and host load in timing results. Repeat a synthetic timing
fixture under controlled idle/load conditions. Distinguish faster scheduling from different timeout behavior or a
different wall-time budget. No promise of bitwise cross-thread equivalence.

### 5 — Cache keys, topology sharing and capacity

**Code:** `src/analog_optimizer/models/inputs.py::ObservationTensorCache`,
`src/analog_optimizer/graph/pyg_converter.py::TopologyTensorCache`; depends on #2's ownership design.

Implementation:

1. Compute an immutable observation identity once at trusted ingestion, including feature/spec schema and every
   input-affecting field. Use that identity for owned replay observations. Keep the content-hash path for arbitrary
   mutable observations passed through the public API.
2. Do not key only by Python `id()`, candidate ID or topology ID. Observation roles, schemas, sizes, measurements,
   validity, specifications, reward/condition context, remaining budget and optional operating points can differ.
3. Reuse existing static topology templates. Never memoize trainable encoder outputs across weight updates.
4. Bound cache memory as well as entry count; measure hits, misses, resident bytes and evictions on replay pools
   larger than 2,048 and 10,000 entries. Do not blindly cache all graphs. Cache contents remain disposable and are
   not part of the learned state required to resume.

Acceptance: extend `tests/test_input_cache.py` for every invalidation dimension, schema changes, mixed graph batch
offsets, mutation, eviction, cold restore and cache-off parity. Public mutable observations still detect nested
changes. Losses/parameters equal the uncached reference. The old 17-observation microbenchmark is insufficient to
select capacity or claim a full-replay speedup.

### 6 — Checkpoint and storage cost

**Code:** `src/gator_workbench/checkpoints.py`, `engine.py::_checkpoint/_initial_update/_reuse_final_checkpoint`,
`storage/dataset.py`, `trajectory.py`, `src/analog_optimizer/training/sac.py::save/load`.

The weights-only file is intentionally safe to read with `weights_only=True`; the full training file includes trusted
Python objects. They are not interchangeable artifacts. Initial-learning currently saves before acknowledging each
update and reconciles a pending learner row on recovery. That is a correctness boundary, not redundant logging.

Implementation:

1. Measure lane-drain wait, replay serialization, tensor serialization, hashing, fsync, pruning and peak memory
   separately at representative replay sizes and all three networks. Measure #1/#2/#5 first because they may change
   the bottleneck. Preserve the already implemented final-save reuse.
2. If replay rewriting is material, prototype immutable replay chunks plus a versioned snapshot manifest: ring
   membership/order/position, insertions, sample RNG and durable dataset cursor. Reuse existing recording-backed
   replay facilities where suitable, but do not assume the workbench dataset is the same database.
3. A new snapshot must reference only durable immutable data, validate all hashes, and publish `latest` last. Keep
   the previous checkpoint valid during failure. Reference-aware pruning must protect data needed by latest,
   manual and other retained checkpoints. Export must materialize a self-contained restorable bundle.
4. Preserve both full resume and safe model inspection/loading. Removing duplicate tensor serialization would
   require a versioned format separating tensors and optimizer/RNG/replay state with validated loaders; do that
   only if measurements justify it. No ad hoc hard links between files with different contents or trust semantics.
5. Do not weaken per-acknowledgement WAL durability or change flush/checkpoint intervals as a hidden optimization.
   Asynchronous serialization, if later attempted, needs an immutable snapshot of tensors and replay, bounded memory
   and a publication barrier. Never serialize live `state_dict()` tensor references while training mutates them.

Acceptance: disk-full/permission failures, interrupted write/rename/publication, corrupt/missing chunk, stale pointer,
pruning, export/import, cold resume and exact next update. Cover initial-learning's pending row, manual Save now,
periodic/final saves, frozen/weights-only modes and disabled replay snapshots. Keep the last complete checkpoint
usable after each injected failure. Format change and optimizer digest change are separate compatibility concerns.

### 7 — Chart preparation

**Code:** `frontend/src/panels/trainingData.ts`, `TrainingTab.tsx`, `TrainingChart.tsx`.

Implementation: retain the per-chart `builtCache`, then share learner ordering, categories, restart markers and
derived arrays per run/data generation across charts. Maintain append-oriented derived state; invalidate/rebuild
when a provisional tail is replaced, history is thinned, the run changes or a restart supersedes updates. Select the
visible range early only with correct prefix state/lookback. An N-evaluation smoothing window can contain many more
than N learner rows; cumulative pass rates and best-so-far values need state from the earlier history. Preserve
duplicate x positions when multiple updates belong to one evaluation. Cover `keyNumbers()` work added in 7.215 too.

Acceptance: old and new builders produce identical values, gap semantics, limits, labels, markers, row identities,
superseded segments, comparison alignment and decimated extrema. Cover all/follow/fixed views, both learner x axes,
1–8 charts, 1–4 runs, smoothing on/off, restarts, tail replacement and caps. Long-running sessions have bounded memory.
Use `frontend/scripts/training_data_check.mjs` and `training_tab_check.mjs`; profile changed frames and real browser
rendering separately. Do not gain speed by lowering row caps, changing smoothing or omitting series.

### 8 — Training API polling

**Code:** `src/gator_workbench/training_series.py::read_training/run_objective/learner_record`,
`storage/dataset.py` readers and `api/run_routes.py` as needed.

Implementation: coalesce repeated config/manifest reads within one request first. Then use a bounded per-run cache
for compiled immutable configuration and an incremental flush-log index. Key by authorized canonical run location
and file/generation identity, not just a run ID or mtime. Detect append, truncation, atomic replacement, resume,
deletion/recreation and WAL compaction; rebuild on uncertainty. Partial trailing records must remain pending until
complete. On this filesystem, transient stat failures must not become cached empty configuration. Keep worker
liveness, run state, segment changes and live WAL cursors fresh. Cache scope must preserve output-root access checks.

Acceptance: responses/cursors equal an uncached reader through flush publication, concurrent polling, bounded pages,
torn tails, resumed segments, restart, file replacement and run switching. No duplicated or dropped rows and no stale
worker status. Cache eviction or restart changes cost only. Extend `tests/workbench/test_wb_training_series.py` and
run the chart integration checks. Measure unchanged polls and incremental polls at growing flush-log sizes.

### 9 — Deferred waveform transfer

**Code:** `src/analog_optimizer/backends/virtuoso_bridge.py::_new_simulator/_raw_format`,
`src/analog_optimizer/recording/remote.py`, Maestro/recipe measurement adapters and
`src/gator_workbench/engine.py::_job_rows/_apply_retention`.

Implementation:

1. Inspect the installed bridge runner's actual download and cleanup API; do not invent an option. Measure bytes
   and transfer time separately from remote measurement. First prototype with a fake runner.
2. Enable only for profiles that complete every required measurement remotely. Local PSF parsers, optional OP
   extraction and other artifact consumers must declare their requirements; retain the full path when uncertain.
3. Always retrieve the required logs, status, measurements, request/deck identity and provenance. Keep remote raw
   results under an owned, unique job identity until retention has been decided and any required transfer is durable.
4. For `all`, retrieve every artifact; for best/failure policies, retrieve exactly the artifacts those policies
   retain, including failures/retries/corners. A download failure is not permission to silently delete remote data
   or change a simulation verdict. Record retriable transfer state and prevent unbounded remote disk growth.
5. Recovery must finish or report pending transfers before cleanup; a browser/export must not be told that a file
   exists locally when it is merely scheduled. Preserve retention manifests, quotas and best-design replacement.

Acceptance: fake remote files for success, design failure, infrastructure failure, retries, all retention policies,
partial downloads, crash after evaluation commit, and remote cleanup failure. Measurements/rewards are equal to the
full-transfer path; retained file hashes match. Prepare a bounded real A/B test for later authorization. If the
installed bridge cannot support safe deferred transfer or transfers are negligible, close this item with that
evidence and keep the existing path rather than weakening retention functionality.

### 10 — Optional calibration data reuse

**Code:** `src/gator_workbench/calibration.py`, `api/run_routes.py`, `modes.py`, `trajectory.py`, config/run manifests
and replay admission; frontend controls only after the import contract is settled.

This is more involved than copying 64 results. `calibration.prepare()` sets episode length to the calibration design
count (normally 64), disables success termination and prevents SGD. Normal starting presets use episode length 4.
Observations contain remaining steps, and transitions validate finite-horizon termination. Baseline runs disable
checkpoints; reusable transitions may instead exist in the optional states/transition archive. Metrics alone are
not full replay transitions. The calibration suggestion rules are also changing in record 7.217.

Implementation:

1. Add an explicit “use compatible calibration data” source selection, off by default, with an eligibility report
   and admitted/rejected counts. Do not change ordinary scratch, resume or fine-tune behavior.
2. Require complete state/action/next-state/provenance records, identical circuit/topology lineage, PDK/mapping,
   simulator/testbench/measurement definitions, action bounds/units/legalization, condition policy/plan, feature
   schema/operating-point availability and compatible episode/termination semantics. Read the source without
   altering it. Source location, hashes and import version belong in the new run's manifest/checkpoint.
3. For explicitly supported spec/reward relabeling, rebuild both observations' goal/reward-dependent fields and
   reward from the recorded valid raw measurements/condition results using the actual target run configuration.
   Recheck success, terminal flags and replay eligibility. Preserve raw evidence and real/synthetic origin. Reject
   incomplete, invalid or infrastructure-failure data; never synthesize measurements or a missing corner.
4. **Initially reject the current 64-step calibration data for a 4-step target.** Gamma zero does not remove the
   remaining-step input or magically make horizons compatible. Do not edit remaining_steps/terminal flags merely
   to pass validation. A future optional calibration collection mode can use the target episode contract and record
   the extra resets/calls it requires; any budget change must be visible before launch. Relabeling horizon semantics
   would require its own justified design and tests and is not a transparent optimization in this plan.
5. Separate imported sample count from newly collected transitions. Start with the target run's normal warm-up and
   update trigger based on new data, with imported data merely available to sample. Shortening warm-up or adding
   offline pretraining is a separate experiment. Do not let `replay.insertions` accidentally grant updates or bypass
   warm-up. Import must be idempotent across resume, including ring and sampling RNG state.
6. Account for calibration simulations and training cost in total budgets and comparisons. Keep train/validation/test
   lineage rules; data already used for adaptation cannot be described as an untouched test or zero-shot evaluation.

Acceptance: valid compatible import, changed scales/goals, incompatible horizon/task/PDK/action/OP/conditions,
archive disabled, missing states, duplicate imports, partial aborted calibration, checkpoint resume and mutation of
the source after selection. Test with nonzero gamma as well as zero. Use `test_wb_calibration.py`,
`test_wb_modes_trajectory.py` and replay tests. Compare learning with and without import on equal total simulation
budgets; a correct importer is not evidence that calibration reuse improves learning.

### 11 — Update-to-data ratio experiment

**Code:** existing `run.advanced.updates_per_transition`, engine scheduling and experiment harness; no algorithm
rewrite is required. Values 4/8/16 are trial arms, not a replacement default.

Freeze gamma, architecture, reward, alpha, learning rates, replay, batch, episode, warm-up, conditions, lane/thread
counts and dataset policy. Compare 4/8/16 using the existing configured 8 arm as control only where that is the
task's selected baseline. Record actual replay-eligible transitions, updates, logging frequency and all simulator
calls; “eight per evaluation” is shorthand and is not true for resets or ineligible failures.

Run separate equal-simulation-budget and equal-wall-time analyses. Report first feasible design/call/time, final
feasibility rate, objective quality, failures, gradient/entropy/alpha behavior and CPU cost. Do not decide solely on
updates per second. Check any interaction with #3 and #10 in a later factorial experiment, not in the initial ratio
comparison. Keep the existing preset unless a separately reviewed result supports changing it.

### 12 — Encoder size experiment

**Code:** existing network configuration and experiment harness; preserve `network_presets.py` defaults.

Compare current and smaller sizes **within each architecture** under matched training settings. A bounded pilot can
use GT 48/4/4 versus 32/4/2; RGCN hidden 32/layers 4 versus hidden 32/layers 2 (heads unused); GATv2 192/3/4 versus
96/3/4 and 96/3/2. These are candidate arms, not a claim they are optimal. Record actor, critics and targets' parameter
counts, peak memory, update/action latency and checkpoint bytes, plus the learning/quality metrics from #11.

Use fresh models for each shape; do not load incompatible weights or resize saved networks. Preserve port features,
parameter-group action dimensions, masking and critic action conditioning. Separate capacity changes from learning
rate/update-ratio changes. Smaller is accepted as a useful option only if its learning/quality tradeoff is measured;
do not substitute an architecture because its name resembles an existing one.

### 13 — Resume and fine-tune workflow

**Code:** existing `src/gator_workbench/modes.py`, checkpoint compatibility, `ModelChooser.tsx`, run/model provenance
and `test_wb_modes_trajectory.py`.

First verify the current workflow and documentation; do not build a second transfer system. Resume requires compatible
full state and continues replay, counters, optimizer and RNG. Fine-tune creates a new run, initializes from explicitly
selected compatible weights and resets replay/optimizers; changed reward/condition contracts reset critics/targets
under the current code. Frozen mode performs no training. Preserve these distinctions and source-read-only behavior.

Where guidance is missing, explain what will load/reset and source/pretraining cost using existing compatibility
reports. Keep model choice explicit; never interpret “faster learning” as permission to select a different saved
model. Compare scratch and fine-tune from a frozen declared source, and frozen evaluation where meaningful. Verify
no source or holdout-data leakage and no transfer between incompatible shapes/schemas. Negative transfer is a valid
result. Resume is continuation, not an independent scratch-vs-transfer arm with free earlier training.

## 5. Implementation order and deliverables

| Phase | Items | Deliverable and exit condition |
|---|---|---|
| A: establish measurements | Baseline for all; #4; #13 workflow audit | Reproducible timing fixtures, current-code/source/config provenance, resource guidance and existing-mode verification. No new preset or behavior. |
| B: read/display improvements | #7, #8 | Equivalent chart/API output, bounded memory, measured CPU/I/O reduction, isolated browser checks. Can ship without an optimizer digest change. |
| C: equivalent learner improvements | #1, #2, #5 | Exact numerical/RNG tests under fixed schedule, mutation/cache tests, cold checkpoint restore, measured performance, documented new source digest and old-code recovery path. |
| D: storage and transfer | #6, #9 | Measured justification, optional prototypes where needed, fault-injection and export/retention parity; real backend trial prepared but not implicitly run. |
| E: new behavior, explicit opt-in | #3, #10 | Recorded scheduling/import contract, default-off configuration, compatibility errors, crash/budget tests, offline demonstrations and rollback to existing mode for new runs. |
| F: learning experiments | #11, #12, #13; then #3/#10 | Frozen experiment manifests, results with cost/quality tradeoffs, and a recommendation. No default changes bundled with implementation. |

Do not combine every optimization in one change and attribute the total gain to each. After C, re-profile before
investing in D/E: the original priority ranking may change. Every item gets a final disposition: implemented and
validated, already provided by existing behavior, or deferred with measured/technical reason and the remaining
acceptance step. “Work on all” does not mean enabling a feature that failed its correctness gate.

## 6. Validation and experiment protocol

For implementation changes, extend existing tests instead of duplicating the implementation in assertions. The main
starting suites are `tests/test_graph_sac.py`, `tests/test_input_cache.py`, `tests/test_parallel_training.py`,
`tests/test_recording.py`, `tests/test_recording_overhead.py` and `tests/workbench/`. Inspect their current fixtures
and test grouping before choosing focused subsets. Run the focused suites after each relevant change and a full
regression before delivery of the integrated implementation.

Example isolated invocation (replace paths with the actual implementation checkout and its scratch directories):

```bash
GATOR_WORKBENCH_SETTINGS_DIR=/tmp/gator-perf-test-settings OMP_NUM_THREADS=1 \
  /home/fyworkstation/analog-optimizer-venv/bin/python -m pytest -q \
  tests/test_graph_sac.py tests/test_input_cache.py
```

Keep scratch settings dedicated to the test run. Select test concurrency to avoid contention with active simulations;
do not automatically launch the documented 12-worker full suite beside a timed experiment. For frontend changes,
type-check and build only in the isolated checkout. Run `training_data_check.mjs` and `training_tab_check.mjs` against
a scratch backend. When launching the Windows Node/browser from WSL, pass `GATOR_WORKBENCH_URL` through `WSLENV`, as
described in `CLAUDE.md`, and verify it reached the browser.

Performance comparisons must use the same dependencies, fixture/input data, seed, hardware/thread settings and
measurement boundaries. Report cold start separately from steady state; repeat samples and give median and tail
latency plus memory/bytes. Replay/cache tests must include full-size pools and changing observations. Timing thresholds
belong in an explicit benchmark report, not fragile wall-clock unit-test assertions. Do not add phase percentages
as if they were independent end-to-end gains.

For learning experiments, first prepare a manifest listing exact task revisions, source models/data, reward and
configuration hashes, arms, seeds, episode/reset behavior, stopping rules and maximum underlying simulator calls.
Use existing cheap ngspice fixtures for an initial bounded study only within authorized resources; synthetic fixtures
prove software contracts, not circuit learning. An initial study should cover at least two compatible tasks and three
seeds per arm; it is exploratory evidence, not proof of a general winner. Run families sequentially rather than an
uncontrolled Cartesian product. A 1,000-evaluation target is only a proposed pilot size; count resets, retries and
conditions separately and state the full cost before any requested real campaign.

Choose non-inferiority/quality criteria before collecting comparison results, based on the selected task's physical
objectives and acceptable tradeoffs. If none is agreed, report the feasibility/time/objective tradeoff and retain
defaults. Keep held-out evaluation separate from tuning and include calibration/pretraining cost. Do not reuse the
earlier multi-setting preset comparison to claim that gamma, size or learning rate alone caused its improvement.

## 7. Documentation, rollback and completion

For each implemented function, update its row in `functionality-reference.md`, the applicable section of
`workbench.md`, and a new entry in `workbench-log/7.119-and-later.md` plus the status index. Optimizer releases also
update the digest/current compatibility state in `decisions.md` and applicable skill references. Add commit-table
rows only when a commit is actually requested and made. Preserve frozen evidence files and original run data.

Rollback is version-specific: new runs can select the old optional scheduler/import/transfer mode; old checkpoints
must run under their original code and libraries. New-format checkpoints may require the new reader even if an
optional behavior is disabled. Keep the original code and output intact, and test both recovery paths. Do not switch
an active run's semantics or downgrade its checkpoint files in place.

Claude's completion report must include all 13 item numbers and their dispositions; changed functions; behavior and
checkpoint compatibility effects; tests actually run; before/after measurements; experiment costs/results; unresolved
limits; and the exact concrete action, if any, still needing real-run/deployment authorization. This planning review
performed source/document inspection only: no new training benchmark, regression suite, simulator run or paid call.
