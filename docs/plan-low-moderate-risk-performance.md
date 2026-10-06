# Claude handoff: lower- and moderate-risk performance improvements

Date: 2026-10-05. **Built on 2026-10-06 as record 7.221 (`510ba0e` + `a39bc5b`): A-F implemented and tested; see the entry in `docs/workbench-log/7.119-and-later.md` and `artifacts/local/reviews/learner-step-7221-2026-10-06/`.**

Implement the six work packages below when this handoff is assigned for execution. The objective is less computation
and I/O while preserving the user's selected training settings, numerical calculations, data and existing controls.
This is the user's narrowed scope following the [13-proposal review](plan-performance-and-learning-efficiency.md).
This document takes precedence over that broader plan for this work.

## Scope

| Work package | Original proposal | Risk | Intended result |
|---|---|---|---|
| A — Chart preparation | #7 | Lower | Less repeated computation across charts and new frames; the same plotted information. |
| B — Training API reads | #8 | Lower | Fewer repeated config reads and full flush-log scans; the same fresh data and cursor behavior. |
| C — CPU contention | #4 | Lower | Controlled test/benchmark resource use and clear launch guidance; existing run resources stay explicit. |
| D — Conditional gamma-zero calculation | #1 | Moderate | Skip unnecessary target-Q computation when the run's selected gamma is exactly zero. |
| E — Replay sampling copies | #2 | Moderate | Avoid copying entire observations for each internal learner sample while preserving mutation isolation. |
| F — Observation input cache | #5 | Moderate | Avoid repeated serialization for safely owned observations and bound memory use. |

The following are outside this implementation: overlapping collection and learning (#3), changing checkpoint storage
or save frequency (#6), deferred waveform transfer (#9), calibration-data reuse (#10), update-ratio experiments (#11),
network resizing (#12), and new fine-tune/model-selection behavior (#13). Do not add these as dependencies or follow-up
cleanup. Gamma, learning rates, alpha, batch size, warm-up, replay capacity, episode rules, update frequency, network
sizes, reward, action semantics and simulation conditions remain the selected run's values. Existing legacy defaults
retain their meaning. Keep pause/abort/save, budget accounting and replay admission rules.

“Same behavior” means equal results for the same inputs, RNG state and controlled update/completion order. Faster
execution can naturally change completion order with parallel simulators or collect more designs under a wall-time
limit. Do not promise bitwise equality of entire timed multi-lane runs.

## Preparation and compatibility

1. Read `CLAUDE.md`, the optimizer skill, current `docs/decisions.md`, the development index and relevant Training
   sections in `workbench.md`. Inspect current code and the shared working-tree diff. The earlier review occurred
   during concurrent calibration, task-save and UI work; preserve that work. No source edits, commit, push or live
   deployment are part of writing this plan.
2. For implementation, use an isolated checkout/snapshot with the intended current code. Record its Git revision,
   relevant uncommitted changes, dependency versions and source digest. Set `GATOR_WORKBENCH_SETTINGS_DIR` before
   workbench imports, including subprocesses, and use separate output directories and a scratch backend port.
3. Keep an immutable copy of the original optimizer source and its dependency versions available for existing
   checkpoints. A Git revision alone is insufficient if the source had uncommitted changes. Verify the snapshot
   matches the old checkpoint contract before calling it a recovery path.
4. Every Python edit under `src/analog_optimizer/` changes `source_digest()`. **D/E/F therefore affect checkpoint
   compatibility even if they preserve every numerical result.** Old checkpoints remain usable with their original
   code and libraries. Do not rewrite their digest, weaken loader checks, silently migrate them or promise that
   disabling an optimization will make them compatible with changed source.
5. Keep D/E/F out of the source tree used by active workers. An imported old module and a new on-disk digest can
   otherwise be combined in a later save. Deliver A/B/C independently; integrate D/E/F as a documented optimizer
   version for new runs after acceptance. Keep checkpoint format, fields, durability and cadence unchanged.
6. All acceptance here can be prepared with offline/synthetic fixtures. No new Virtuoso/Spectre runs, schematic
   changes, paid agents, bridge restart, live task-setting changes or live frontend build/backend restart are needed.
   Use existing project authorization rules for any later deployment or real validation.

## A — Share chart preparation and update only affected data

**Files:** `frontend/src/panels/trainingData.ts`, `TrainingTab.tsx`; `TrainingChart.tsx` only if necessary.

The page already has per-chart `builtCache`, bounded retained rows, incremental polling and draw throttling. Improve
the work beneath that cache rather than adding another generic memo wrapper.

Implementation:

1. Establish current changed-frame timing for 1 and 8 charts, one run and four compared runs, using the existing
   synthetic chart profiler. Separate data preparation from browser rendering and include the recent key-number table.
2. Share learner ordering, categories, restart/superseded markers and common derived data per run/data generation.
   Use a generation that changes on append, tail replacement, thinning, reset and run replacement. Bound cache
   lifetime to the stores/views it serves; removing a compared run must release its data.
3. Incrementally append derived values where valid. Rebuild affected state when a flush replaces provisional rows,
   a restart supersedes updates or row retention changes history.
4. Limit work to visible rows only when correct prefix state/lookback is available. Cumulative pass shares and
   best-so-far need earlier history. Smoothing by N evaluations may require many more than N update rows. Preserve
   duplicate x coordinates for several updates after one evaluation, edge neighbors and extrema used by decimation.
5. Retain existing polling/draw intervals, charts, row caps, units, controls and missing-data explanations.

Acceptance:

- Compare old and new builders for series values, row identity, gaps, labels, limits, restart markers, superseded
  updates and decimated extrema. Cover update/evaluation axes, smoothing on/off, all/follow/fixed views, 1–8 charts,
  1–4 runs, absent metrics, resumed runs, tail replacement and retention caps.
- Extend `frontend/scripts/training_data_check.mjs` and `training_tab_check.mjs`. Type-check and build only in the
  isolated checkout. Verify chart interactions in the scratch browser and that repeated run switching releases memory.
- Report changed-frame CPU time and memory at 8,000, 100,000 and 200,000 updates. Do not gain speed by dropping
  information, lowering row limits or changing smoothing. If incremental arithmetic changes floating-point rounding,
  quantify it and require an explicitly justified tolerance without changing displayed values or extrema selection.

## B — Coalesce and cache training API reads safely

**Files:** `src/gator_workbench/training_series.py::read_training/run_objective/learner_record`;
the dataset reader only where required. Preserve the existing endpoint/response schema.

Implementation:

1. Read config and manifest once per request and pass the parsed values to internal helpers. Keep compatibility
   for callers that use the existing helpers independently.
2. Add a bounded cache for compiled configuration keyed by authorized canonical run location and robust file
   identity/generation. Do not cache live worker status or mutable segment information as immutable configuration.
3. Maintain a bounded incremental index of completed `flushes.jsonl` entries. Remember a verified read offset and
   trailing incomplete bytes. Consume complete appended records only. Preserve existing corrupt-record errors.
4. Detect truncation, atomic replacement, run deletion/recreation, resume and WAL compaction. On uncertain identity,
   rebuild from the authoritative files. Do not rely only on mtime or run ID; account for transient 9p stat failures.
   Do not cache a transient read failure as a valid empty config or empty dataset.
5. Preserve output-root access checks, reader thread safety, current row/page limits and tail-cursor protocol.
   A stale or evicted cache must change performance only, never which data is returned.

Acceptance:

- Extend `tests/workbench/test_wb_training_series.py`. Compare the optimized and uncached readers under a controlled
  clock/liveness fixture, including unchanged polls, growing flush logs, a partly appended record, corrupt complete
  records, atomic replacement, same-path run recreation, concurrent requests and cache eviction.
- Exercise publication of Parquet parts, tail-to-flush replacement, cursor reset and resumed segments. No missing or
  duplicate rows; worker state remains fresh. Repeat the browser training checks against the scratch server.
- Measure request latency, file-read/parsed-byte counts and cache memory for small and long runs. Preserve the current
  bounded cursor implementation; do not restore whole-journal response payloads to simplify caching.

## C — Avoid contention during development and measurement

**Files/workflow:** existing test and benchmark launchers and operating documentation. Inspect
`src/gator_workbench/worker.py` before adding thread controls; Torch is already set to one thread there.

Implementation:

1. Record effective thread/lane counts, test-worker count and host load in performance measurements.
2. Make benchmark invocations use explicit resource settings and run timed arms sequentially on comparable host
   load. Reuse existing test-concurrency options. If a benchmark launcher lacks one, add a scoped explicit option
   without changing simulation-worker defaults or introducing a machine-wide resource manager.
3. Document a quiet measurement procedure and how to lower this project's test concurrency while other work is
   active. Avoid running a 12-worker regression suite alongside a timed simulation benchmark.

Acceptance: check launcher argument handling if changed and confirm effective settings in fixture output. Do not
kill/suspend/renice other jobs, alter VM allocation, silently reduce simulation lanes, or change live run thread
counts. If existing controls are sufficient, documentation and reproducible invocation are the complete deliverable.

## D — Preserve gamma and RNG while removing unused work

**Files:** `src/analog_optimizer/training/sac.py::SACLearner.update`; inspect
`src/analog_optimizer/models/graph_transformer.py::GroupActor.sample` when reasoning about random draws.

Implementation, conservative first step:

1. Branch on the actual `self.config.gamma == 0`. For that branch, use reward as the target and skip the two target-Q
   forward passes. Keep the existing next-observation batch and next-actor sample initially: the unused sample still
   consumes randomness needed to preserve subsequent actor samples.
2. Keep the full existing calculation for every nonzero gamma, including tiny nonzero values. Preserve transition
   validation, bootstrap/terminal semantics, current critics, actor/temperature updates, target soft updates, RNG
   sources, counters and checkpoint fields. Never force a configured gamma to zero for performance.
3. Removing the next batch and next actor forward is optional within this package only if equivalent discarded RNG
   consumption can be proved for every supported packed action shape, dtype/device and pinned library version.
   A different-looking normal draw is not sufficient evidence. Keep the conservative path if proof fails; its smaller
   speedup is acceptable. Do not introduce a new action RNG stream or change sampling order to make this easier.

Acceptance:

- Extend `tests/test_graph_sac.py`. Compare reference and optimized paths over multiple updates on GT/RGCN/GATv2:
  target values, all reported losses, all model/target weights, optimizer states, alpha, counters, Python/NumPy/Torch
  RNG states and the next actions. Use exact equality in the deterministic pinned CPU environment.
- Test gamma 0, a tiny positive value, 0.5 and 0.99; batch 1 and batch 8; mixed graph/action sizes and odd packed
  dimensions; terminal/bootstrapping transitions; cold/warm caches. Test selected gamma propagation from a scratch
  run configuration as well as the learner directly. Nonzero gamma must not take the new zero path.
- Preserve invalid-transition and current loss/gradient error checks. Equivalence claims cover valid finite learner
  state: the omitted target branch no longer incidentally detects a non-finite intermediate in that unused branch.
- Save and resume under the new source and verify the exact next update. Keep old-source recovery separately tested.
  Report actual gains; the earlier 20–21% figure included next-batch/actor work and is not this first step's promise.

## E — Internal replay sampling without repeated full copies

**Files:** `src/analog_optimizer/training/replay.py`, `src/gator_workbench/engine.py` learner call sites;
inspect other `replay.sample` callers before changing any shared API.

Implementation:

1. Preserve admission validation, persistence verification and the owned copy on admission. Preserve public
   `ReplayBuffer.sample()` behavior: callers may mutate their samples without altering stored data.
2. Introduce an encapsulated learner-only read path, or immutable prepared samples, with explicit ownership and
   lifetime. Nested dictionaries/graphs are mutable even inside frozen dataclasses. Do not expose writable replay
   entries as a new general-purpose sampling API. Mutable batch tensors and metadata must own their storage.
3. Keep the same `random.Random` state, index selection without replacement, ring ordering and number of sampling
   calls. Do not change replay capacity, admission, update timing or how warm-up is counted.
4. Keep contract validation. A mere “read only” comment is insufficient justification for dropping checks or copies
   across a public boundary. If the ownership guarantee needs a larger storage redesign, retain the existing path
   and document that limit rather than expanding into excluded checkpoint/storage work.
5. Internal optimization handles must remain disposable. Save/load the established transition representation and
   replay state; no new checkpoint format, serialized cache objects or reconstruction from missing source records.

Acceptance:

- Preserve the public mutation-isolation test in `tests/test_graph_sac.py`. Also mutate original admitted data,
  nested sample dictionaries, graph parameters, batch tensors and source metadata; replay and future batches stay
  unchanged. Fingerprint replay before/after learner updates to detect hidden mutation.
- Compare sample IDs/order, replay RNG, losses, parameters and subsequent actions against the copying path. Cover
  ring wraparound, eviction, repeated samples, mixed graphs, persistent replay, rejected admissions and cold resume.
- Benchmark sample-plus-update time, allocations and resident memory. A representation with high conversion or
  validation cost is acceptable only if a repeated end-to-end fixture shows a material benefit without weaker checks.

## F — Cheaper safe input-cache keys and bounded memory

**Files:** `src/analog_optimizer/models/inputs.py::ObservationTensorCache`,
`src/analog_optimizer/graph/pyg_converter.py::TopologyTensorCache`; depends on E's safe ownership contract.

Implementation:

1. Reuse the current observation/topology caches. For trusted owned observations, establish an immutable identity
   once and reuse it instead of pickling/hashing the full observation on every cache hit. Preserve content-based keys
   for mutable observations passed through the public API. Avoid identity reuse across different cache owners.
2. Include schema and all input-affecting state: topology/ports, parameter values/domains/ties, specs, measurements,
   validity, reward/condition context, remaining steps and optional operating points. Candidate ID or Python `id()`
   alone is not a valid key. Changed schema or mutable content must invalidate the prepared input.
3. Cache deterministic raw tensors only. Trainable embeddings must be recomputed after weight updates. Preserve
   batch isolation and correct graph/group offsets; callers cannot mutate stored cache tensors through a batch.
4. Add memory-aware bounds/observability where useful while retaining existing count bounds. Do not automatically
   expand to the full 10,000-transition replay. Benchmark different bounded capacities explicitly; only adopt a
   larger default with measured memory headroom and benefit. Cache state remains optional and absent from checkpoints.

Acceptance: extend `tests/test_input_cache.py` for all invalidation dimensions, schema changes, nested mutation,
mixed graph batches, cache off/on, eviction and cold restored learners. Inputs, losses, weights and next actions
must equal uncached/reference behavior. Profile changing replay pools below and above the existing 2,048-observation
capacity, including a 10,000-transition fixture; the earlier 17-observation warm-cache run cannot justify capacity.
Report conversion/hash time, hit rate, evictions and peak memory as well as full update time.

## Delivery order and verification

1. **Baseline and resource setup:** C plus repeatable focused timing fixtures, before changing production code.
2. **First delivery:** A and B, with chart/API parity and scratch browser checks. These can be reviewed without an
   optimizer digest change. Do not make their delivery depend on finishing D/E/F.
3. **Second delivery:** D's conservative path, E, then F. Keep individual changes reviewable but record one final
   integrated optimizer source digest. Apply only the implementations that pass equivalence and ownership checks.
4. **Integration:** focused tests after relevant changes, then the project regression suite once the final code is
   ready. Use current tests/fixtures and required browser checks; preserve frozen evidence files. Avoid redundant
   full-suite reruns unless a new change or failure justifies them.

Suggested focused Python suites: `tests/test_graph_sac.py`, `tests/test_input_cache.py`,
`tests/workbench/test_wb_training_series.py`, `tests/workbench/test_wb_engine.py`,
`tests/workbench/test_wb_modes_trajectory.py` and `tests/workbench/test_wb_save_now.py`.
Cover other collectors with `tests/test_parallel_training.py` and persistent replay with the recording tests if
their paths change. Pin dependencies using `constraints.txt`. Use the project's venv and isolated settings.

Windows browser checks launched from WSL require `GATOR_WORKBENCH_URL` in `WSLENV`; confirm they reached the scratch
backend instead of port 8765. Building the frontend in the shared live checkout overwrites served assets, so use the
isolated checkout. No new simulation campaign is required to prove these software contracts.

Use the [earlier synthetic profiling evidence](../artifacts/local/performance-audit-20261005/provenance.json) and
its adjacent scripts as starting fixtures. Record exact code/config/dependency identity, threads, load, cold/warm
state and input size. Report repeated median/tail time and memory, with sampling, update, request and rendering costs
distinguished. Do not add overlapping phase savings or claim simulator/learning improvements from microbenchmarks.
Timing assertions should not make normal unit tests flaky.

## Completion and handoff back to the user

For each of A–F, report implemented/already sufficient/deferred, affected files, tests actually run, before/after
measurements and any remaining limitation. A failed equivalence test is a reason to keep the conservative path,
not to relax semantics. No preset or algorithm change is an acceptable substitute for a performance improvement.

Update changed functionality rows, applicable `workbench.md` sections and a new development record/index entry.
For actual optimizer edits, update the recorded source digest and old-checkpoint recovery instructions in
`decisions.md` and applicable references. Add commit history only if a commit is requested and made.

Provide separate ready-to-review changes for the workbench and optimizer, with an explicit compatibility note:
old checkpoints use old source; new-source checkpoints resume exactly under the new source; payload format and
recovery guarantees are unchanged. Keep original source and run outputs intact. Prepare all tests and artifacts
before any later request to deploy. Do not deploy, restart active services, commit or push without session authorization.

This handoff itself changes documentation only. It does not implement or benchmark A–F.
