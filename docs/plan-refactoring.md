# Refactoring plan: the same behaviour, a structure that is easier to change

Date: 2026-10-09 (session "Refactoring plan"; user: "Make a refactoring plan"). **Plan only: nothing in the code was
changed, nothing was built, and no run, backend, Virtuoso, Spectre or agent CLI was touched.** Measured on HEAD `4323753`
(branch `workbench`; the working tree was clean at the measurement and holds a peer's uncommitted record-7.286 edits
since about 04:20). The two measuring scripts and the two proof scripts are in the session's
scratchpad and are reproduced in section 7 so that the executing session can rebuild them.

## 0. In plain words

A refactoring moves and splits code so that each file does one job and each job sits in one place. **Nothing the page
or a run does changes:** the same buttons with the same captions, the same messages, the same HTTP routes and status
codes, the same files in a run folder, the same numbers in them. Every package below is a *move*, and a move is proved
by machines, not by reading: the function bodies before and after are compared as syntax trees, the list of routes is
compared byte for byte, the full test suite and all browser checks run on a clean copy, and for the run engine a seeded
MOCK run before and after must write the same tables.

Why it is worth doing now:

- **Seven sessions edit one tree.** The biggest files (`engine.py` 1,694 lines, `pdk.py` 1,477, `runs.py` 1,114,
  `profiles.py` 1,053, `Right.tsx` 824, `Editors.tsx` 811, `trainingData.ts` 1,306) each hold four to six unrelated jobs,
  so two sessions working on different features meet in the same file and the hunk-exact commit recipe is needed
  again and again. Smaller files with one job each make most commits plain.
- **The backend's modules import each other in a circle**, and the circle is hidden: 173 imports are written inside
  functions instead of at the top of the file, and 45 of them exist only because a top-level import would fail to
  load. Twenty modules (`profiles`, `tasks`, `validation`, `compile`, `engine`, `runs`, ... see 1.3) form one knot. A
  knot of this kind has two costs: a change in one module can break an import somewhere else *while a run is going*
  instead of when the backend starts, and nobody can say which module is "below" which. The live tree has a CLI run in
  flight at this moment (encoder stage D, pid 2800619): its engine will import `profiles`, `calibration` and
  `ngspice_tasks` for the first time when the run *ends* (`engine.py:1599, 1616, 1638`). That is exactly why section 5
  says: build in a copy, land between runs.
- **Every HTTP route is a closure inside one function** (`circuit_routes.register` 352 lines, `run_routes.register`
  338 lines, `settings_routes.register` 152 lines). A route cannot be read, tested or moved on its own.
- **Reading cost.** Each new session reads the file of the feature it touches; a 1,700-line file costs a session
  several minutes and much of its context before it has done anything.

What is *not* in this plan: no change under `src/analog_optimizer/` (the digest, section 6 lists what a digest step
would take if the user ever chooses one), no edit of a pinned evidence file, no renamed route, caption, message or
file in a run folder, no deleted function, no behaviour change "while we are at it", and nothing that goes live
while the encoder queue runs.

Recommended order and size: **A** (mechanical, one session-day) then **B1** (the import knot, one day) first, because
every later move is safer once imports are honest; then B2-B5 one file at a time, C and D as separate increments. Each
package is one commit, proved and recorded on its own, so the user can stop after any of them.

## 1. What was measured (HEAD 4323753, 2026-10-09)

### 1.1 Size

| Area | Files | Lines | Notes |
|---|---|---|---|
| `src/gator_workbench/` | 87 | 28,509 | 1,324 functions and classes in the two Python packages, 1,915 functions in all |
| `src/analog_optimizer/` | 68 | 10,210 | digest-gated (CLAUDE.md hard rule) |
| `frontend/src/` | 52 | 11,097 | React + TypeScript |
| `frontend/scripts/` | 66 | 13,999 | browser checks; all but two use `lib/harness.mjs` |
| `tests/` | 152 | 29,562 | 1,798 passed + 21 skipped on a clean copy of HEAD (record 7.284) |
| `examples/` | 51 | 7,647 | mostly pinned milestone scripts |
| `docs/` | 71 | 31,367 | |

### 1.2 Long functions (Python, both packages)

44 functions are 80 lines or longer, 13 are 150 or longer. The workbench ones:

| Lines | Where | Function | Package |
|---|---|---|---|
| 352 | `api/circuit_routes.py:20` | `register` | 25 routes as closures |
| 338 | `api/run_routes.py:111` | `register` | 26 routes as closures |
| 304 | `ngspice_netlist.py:459` | `parse_text` | parser (B6: leave) |
| 228 | `engine.py:845` | `RunEngine._commit` | B2 |
| 192 | `profiles.py:649` | `save_task` | B3 |
| 159 | `runs.py:344` | `prepare_run` | B5 |
| 155 | `ngspice_netlist.py:594` | `expand` | parser (leave) |
| 152 | `api/settings_routes.py:16` | `register` | 17 routes |
| 147 | `calibration.py:109` | `calibrate` | B6 |
| 134 | `connection.py:383` | `run_layers` | B6 |
| 131 | `pretrain.py:73` | `prepare_pool` | B6 |
| 128 | `readiness.py:33` | `build` | B6 |
| 121 | `validation.py:177` | `_check_parameters` | B6 |
| 121 | `cli.py:23` | `main` | A5 |

The optimizer package's long functions (`envs/sizing.py::_evaluate` 365, `training/parallel.py::collect_parallel_episodes`
222, `evaluation/benchmark.py::run_benchmark` 190, `netlist/spectre_parser.py::parse_text` 186,
`measurements/specs.py::evaluate_conditions` 153) are listed in section 6 only.

### 1.3 Imports

- **413** imports of package modules are written inside functions; **173** of them import another `gator_workbench`
  module. Of those 173, **128** close no cycle and could stand at the top of their file today; **45** exist because a
  top-level import would not load.
- With the in-function imports counted as edges, the workbench has two knots (strongly connected components):
  - **20 modules:** `calibration, cdf_factory, cdf_rules, cdf_write, checkpoints, compile, consistency, engine,
    generic_profile, modes, ngspice_tasks, pretrain, profile_preflight, profiles, recipes, rehearsal, runs,
    save_point_compression, tasks, validation`;
  - **5 modules:** `connection, directories, layout, ngspice_link, paths`.
- What the 45 cycle-closing imports actually fetch is small and always the same kind of thing: **constants and tiny
  pure helpers**. `tasks.py`'s `REAL_PROFILES`, `REMOVED_REAL_TASKS`, `RESULT_ANALYSIS`, `REAL_AUTHORIZATION_REQUIRED`,
  `TaskBlocked`, `TaskRuntime`, `CORNER_TASKS`, `MOCK_TASK_REMOVED`, `SYNTHETIC_FIXTURES`, `NATIVE_DRAFT_NOT_EXECUTABLE`,
  `starter_project`, `real_task_removed`, `verified_spec_registry` (imported lazily by `profiles`, `validation`,
  `compile`, `runs`, `ngspice_tasks`, `engine`, `profile_preflight`); `profiles.py`'s `HISTORY`, `TASK_FILE`,
  `ProfileError`, `profile_dir`, `task_spec_registry` (by `consistency`, `compile`, `validation`); `connection.py`'s
  `load_profiles`, `KINDS`, `family_of`, `profile_kind`, `connection_file` (by `tasks`, `profiles`, `ngspice_tasks`,
  `runs`, `directories`); `compile.py`'s `grid_top`, `group_unit`, `normalization_scale` and `validation.py`'s
  `resolve_leaders` (by `generic_profile`, `cdf_rules`, `profiles`, `calibration`); `engine.py`'s `RunLock` (by
  `save_point_compression`, `bridge_connect`, `worker`). Package B1 moves exactly these into leaf modules.
- Two of the in-function imports are deliberate and documented, and stay: `cdf_write -> cdf_factory` (its base class
  comes from `analog_optimizer.training.parallel`, which imports torch and PyG: about 2 s at every start of a
  process that only prepares or checks a cell; `cdf_factory.py:3-7`) and `connection -> ngspice_link` (what the
  connection module may do is pinned by its own test; `connection.py:541`). The 99 in-function imports of
  `analog_optimizer` modules defer torch on purpose and stay too.
- One layer inversion: `task_baseline.py:86` imports `start_run` from the API layer (`api/run_routes.py`). With it,
  `api/__init__.py` imports `app`, so importing *any* `api.*` module (even `api/models.py`, the request bodies) loads
  the whole API, `circuit_routes` and `task_baseline`: a 9-module cluster of its own. `api/models.py:4-7` imports
  `corner_check` (which pulls in `engine` and the optimizer) and `ngspice_tasks` for a few constants. `cli.py:83`
  importing `create_app` is the CLI's job and stays.
- `profiles` is the hub of the big knot: its two-way pairs are `tasks <-> profiles`, `profiles <-> compile`,
  `profiles <-> validation`, `profiles <-> consistency`, and `tasks <-> ngspice_tasks`. Moving `RunLock` and the
  three helpers beside it out of `engine.py` alone shrinks the knot from 20 modules to 14 (seven modules import
  `engine` only for them); after the task registry and the run index are leaves, one edge holds the remaining 13
  together, `validation.py:690 -> consistency`, and the pure half of `consistency` as a leaf cuts it (the survey's
  measurement; B1 repeats it step by step).
- No workbench module imports torch at the top of its file (the optimizer is loaded once by `preload()` before any
  request); 19 modules import `analog_optimizer` at the top. Hoisting a workbench-internal import therefore never
  changes *when* torch loads, with the exceptions named in A1.
- Most imported: `storage.atomic` (31 modules), `storage.dataset` (23), `paths` (22), `security` (15). Those are
  the honest leaves; the plan keeps them as they are.

### 1.4 Routes

90 routes. `app.openapi()` of `create_app(serve_frontend=False, auto_check_on_start=False)` is 71,764 bytes with
sha256 `9eb4e5b0a052d419…` (sorted keys; 4.5 s offline, nothing written: the proof of section 4.2). Every path is a
literal (no path parameters), so the order of registration changes no match; it is preserved anyway so that the
OpenAPI document stays byte-identical.

### 1.5 Duplicated code

Across files, only 20 six-line windows are duplicated in the two packages together. Thirteen of them are the workbench
copying code it cannot edit: `cdf_write.py` ~ `backends/native_preparation.py` (7 windows) and `ngspice_backend.py` ~
`backends/synthetic_sizing.py` (5). That is the digest rule at work, not carelessness; it belongs to section 6, not to
this plan.

Shorter repetitions, below the six-line window, are the backend's real duplication, and they are *patterns*, not
copies: `try: json.loads(p.read_text()) except (OSError, ValueError)` about 30 times (`profiles` 12, `working_copy` 5,
`checkpoints` 3, `native_cells` 3, with local helpers at `consistency._read_json:149` and
`working_copy._json_or_empty:86`); `read_json(p, default=None) or {}` 26 times; `control / 'run.lock'` 8 times
(`engine.py:187`, `runs.py:513, 755, 825, 835, 1064`, `save_point_compression.py:153`, `worker.py:60`);
`'command.json'` 4 times; `bridge_state_dir() / 'session.lock'` 4 times; "the named connection, else the active one"
3 times; the profile kind/family check 6 times; the same regex for a Cadence name 6 times, a profile id 3 times, a
task name 3 times; the live-run-state tuple 4 times; the loopback hosts and the clean exit states twice each. HTTP
errors are already built in one place (`api/support.fail`, 71 calls). Package B8 takes these one pattern at a time.

### 1.6 Frontend

| File | Lines | What it holds |
|---|---|---|
| `panels/trainingData.ts` | 1,306 | 43 exports: table store (`TrainingStore`, `Table`, `Words`), series maths (`smooth`, `decimate`, `visibleRows`), chart building (`ChartSpec`, `Built`, learner chart definitions) |
| `panels/Right.tsx` | 824 | the widgets `Num`, `ByteSize`, `Module`, `Check`, `LookFold`, `TemplatesTable`, then `RunPanelBody` (517 lines, 14 `useState`, 12 `useEffect`), `OutputPanel`, `ResearchPanel` |
| `panels/Editors.tsx` | 811 | `Cell`, `QuantityBox`, `UnitSelect`, `FormulaBar`, `LimitSelect`, `DiffView`, then `EditorsView` (580 lines) |
| `panels/Left.tsx` | 655 | `CircuitClass`, `TitleFacts`, then `CircuitPanelBody` (560 lines, 16 `useState`) |
| `App.tsx` | 632 | `Page` (21 `useState`, 11 `useEffect`): layout, status polling, run selection, calibration question, header slots, bottom tabs |
| `store.ts` | 368 | config store + Undo, `usePolling`, `useRequest`, `useAsyncAction`, `migrateConfig` |

39 of the 52 files import `api.ts`, 19 import `store.ts`. The check scripts match on `textContent` and on CSS
classes (`.left .panel h3` ...), not on component names, so splitting a file changes no check.

### 1.7 Tests

`tests/workbench/helpers.py` (202 lines, imported by 75 workbench test modules) and the two `conftest.py` files carry
the shared fixtures (`workbench_app`, `workbench_server`, `ScriptedBackend`, `make_config`, `execute`,
`run_prepared`, `rows`, the settings-folder redirect per process and per xdist worker, the four autouse guards). But
**test modules are used as helper libraries:** `test_wb_api` is imported by 18 other modules (`probe`, `wait_for`),
`test_wb_profiles` by 7 (`read_cell`, `config`, `connection_file`, `ROWS`, `CIRCUIT`, `FIXTURE`), `test_wb_task_save`
by 5, `test_wb_virtuoso_setup` by 5, `test_wb_working_copy` by 4, `test_wb_connection` by 3 (`FakeBridge`,
`monitor_for`), `test_wb_cdf_write` by 2 (its 175-line `FakeVirtuoso` SKILL interpreter); importing
`test_wb_own_copy` loads seven other test modules. Helpers are written out again: the fake connection probe three
times (`test_wb_api.py:24`, `test_wb_ngspice.py:54`, `test_wb_connection_kinds.py:243`), the `client` fixture five
times, the ring-oscillator reader (`test_wb_cdf_write.py:23-63` and `test_wb_profiles.py:20-52`, near-identical), the
fake run folder `fabricate` in three shapes, the engine built by hand in four places, identical pairs
(`edit_json`/`prepared`, `write_profiles`, `_no_save_yet`, `wait_for`), and the research side's single-thread torch
autouse fixture four times (the same as the workbench's `_single_torch_thread`). Eight modules import through a second
root (`from tests....`) while the rest use bare names; with no `tests/__init__.py` the same file loads twice under two
names. Test modules named after review rounds and dates (`test_wb_round5_*`, `test_wb_review_fixes.py`,
`test_wb_faster_calls.py`, `test_wb_run_speedups.py`, `test_optimizer_round5.py`, `test_reward_v2_audit_fixes.py`)
hold tests that belong to feature modules: finding "the tests of `runs.py`" takes a grep. Markers: `xdist_group` is a
`pytestmark` in 11 modules, pinning whole modules to one worker where only a few tests use the module fixture
(`test_wb_pdk`: 4 of 21; `test_wb_training_series`: 5 of 22) and once where no module fixture exists
(`test_wb_learner_step`); `requires_evidence` sits on 8 of 9 tests of `test_reward_v2_real_data` and as a
`pytestmark` in `test_reward_v2_workbench`, which imports the module-scoped `real_transition` fixture and so builds it
twice.

### 1.8 Examples: pinned, not refactorable in place

`examples/freeze_reward_v2_baseline.py:52` hashes every top-level `examples/*.py` (with `configs/*.json` and the
fixture `.scs` files); `report_reward_v2_acceptance.py:49` and `report_reward_v2_real_acceptance.py:87` re-hash those
paths by absolute path; the M5/M6 audits re-hash examples; `evaluation/real_category.py:201` writes the hash of
`benchmark_real_cross_category.py` into the M6 real plan; `docs/m6-vco-requalification.md:147` pins
`vco_requalification.py` by path and SHA-256; seven tests run example scripts by path; and the scripts import each
other (`opamp_connection` 11 importers, `save_recording_summary` 4, `build_opamp_baseline` 3, the `verify_*_baseline`
scripts 5), so even the helper-like ones are load-bearing. Only four scripts postdate the freeze
(`calibrate_analoggym`, `check_analoggym`, `import_analoggym`, `benchmark_encoders`), and moving them to a `tools/`
folder would still touch docs and `test_analoggym_calibration.py` for a few tiny duplicated helpers (2-4 lines each).
**Verdict: no package for `examples/`.** A future script can use an `examples/_lib/` (outside the freeze glob); the
existing copies stay.

## 2. Rules every package follows

1. **Behaviour-identical, byte for byte.** Same exceptions, status codes, message texts, file names, JSON keys,
   captions, DOM text. A helper that "also fixes" an edge case is a behaviour change and is left out (record 7.70's
   lesson). No function is deleted, even one only tests call. No message is reworded, not even to improve it.
2. **Nothing under `src/analog_optimizer/`.** The digest `0b0808bc…` (set by `40d1249`) is what the running encoder
   comparison and every save point since 7.228 pin. Section 6 is advice for a *separate*, user-chosen digest step.
3. **Pinned evidence untouched:** `configs/*.json`, the pinned `examples/*.py`, `tests/fixtures/synthetic/*.scs`
   (absolute path + hash in frozen plans). No reformatting, renaming or moving.
4. **Old names keep working.** When a symbol moves, the old module re-exports it (`from .task_registry import
   REAL_PROFILES`) so that every `tasks.REAL_PROFILES`-style reference (27 files, tests included) is unchanged. A
   later package may drop re-exports once their last user is updated; that is a separate, grep-proved step.
5. **Patch targets move with the code.** The tests replace module attributes with `monkeypatch.setattr`: 25 patches on
   `runs.*`, 17 on `tasks.*`, 12 on `profiles.*`, 6 on `engine` (as `engine_module`), 5 on `layout`, 2 on `pdk`;
   among the names `runs.current_source_digest` (6 tests), `runs.read_json`, `runs._RUN_CACHE`, `runs._CONTRACTS`,
   `runs._SOURCE_DIGEST`, `tasks.starter_config`, `tasks.load_task`, `profiles.save_task`, `layout.filesystem_type`,
   `engine_module.read_json` (`test_wb_round5_perf.py:327`, which counts reads of `index.json`). A re-export keeps the
   *name* valid but not the *patch*: a function that moved to `run_index.py` reads `run_index.read_json`, and a test
   that patches `runs.read_json` then silently patches nothing. So every package lists the patched names of the code
   it moves and changes those tests in the same commit, and the proof includes `grep -n "monkeypatch.setattr(<old
   module>"` against the moved names: zero left.
6. **One package, one commit, one record entry.** Private-index commit of exactly the tested tree
   (the private-index recipe of CLAUDE.md step 2 and record 7.117), peers told before and after; the user says "commit
and push".
7. **Docs move with the code:** `docs/functionality-reference.md` rows (the code column names files and functions:
   15 rows name `engine.py`, 13 `runs.py`, 10 `validation.py`, 9 `tasks.py`, 6 `connection.py`, 5 `profiles.py`), the
   "Code organization" section of `docs/workbench.md`, the record entry with the before/after numbers of section 4.4.
8. **Build and test in a clean copy on the Linux disk** (`git archive HEAD | tar -x -C <ext4 scratch>`), never in
   the live tree while a run is in flight (section 5). Regression with `-n 4` and browser checks with `--lanes 2`
   while the queue simulates (CLAUDE.md).
9. **No new dependency, no new tool in the venv** (no ruff/black reformat: a reformat would touch pinned files and
   hide the moves in noise).

## 3. Work packages

Effort: S = under half a session-day, M = about one, L = more than one. "Covered by" names the tests and browser
checks that already exercise the area; every package also runs the whole suite.

### Group A: mechanical, lowest risk (backend)

| # | Package | What moves | Proof | Effort | Covered by |
|---|---|---|---|---|---|
| A1 | **Honest imports** | Hoist the 128 in-function `gator_workbench` imports that close no cycle to the top of their files. Kept lazy, each with a one-word reason comment: the subprocess entry points (`cli.py` subcommands, `worker.py`, `connection._probe_main`, `bridge_read._main`), the two documented ones (`cdf_write -> cdf_factory`, `connection -> ngspice_link`), every `analog_optimizer` import, and any import whose target brings `analog_optimizer` into a module that had none at the top (the 19 heavy modules of 1.3). The 45 cycle-closing imports stay until B1 and get a `# cycle: <module>` comment each, so the next reader knows why. | AST identity (4.1): an import line inside a body is a difference, so the proof's list must equal the hoisted set. `python -X importtime -c "import gator_workbench.api"` before and after: torch loads at the same point (`preload`). | S | whole suite |
| A2 | **Layer inversion and the API cluster** | `start_run`, `once`, `worker_started` (`run_routes.py:25-108`) move to a new non-API module `launching.py`; `run_routes.py`, `app.py` (`run_routes.worker_started`) and `task_baseline.py:86` import from there. The constants `api/models.py:4-7` fetches from `corner_check` and `ngspice_tasks` move to leaf modules (or `models.py` takes the literal values with a comment naming the source) so that the request bodies import nothing heavy. | AST identity; OpenAPI identical; `python -X importtime -c "import gator_workbench.api.models"` no longer loads `engine`. | S | `test_wb_launch.py`, `test_wb_task_baseline.py`, `test_wb_api.py`, `test_wb_corner_check.py`; `launch_recovery_check.mjs` |
| A3 | **Routes readable one at a time** | Each `register(app, context)` is split, *in the same file and in the same order*, into per-concern functions that `register` calls in turn: `run_routes` -> list/models, launch, commands+status, corner check, files+tables+logs+training, exports; `circuit_routes` -> tasks, Virtuoso browse/read, profiles, ngspice, working copy + task files, validate/diff/matched; `settings_routes` -> settings, connections, folders. Each under ~100 lines. (Converting to `APIRouter` per file is a possible later step, not this one: it changes how `context` reaches a handler.) | OpenAPI identical (paths, methods, models, order). AST identity per handler body. | S | `test_wb_api.py` and every route test; all browser checks |
| A4 | **`run_lock.py`** | `RunLock`, `iso`, `decode_action`, `learner_experiment` and `INFRASTRUCTURE_FAILURES` (`engine.py:47-167`) move to a leaf `run_lock.py`; `engine` re-exports them. Seven modules import `engine` only for these (`save_point_compression`, `bridge_connect`, `worker`, `corner_check`, `graph_view`, `summary`, `runs`); the 20-module knot becomes 14 by this move alone. Do **not** merge `engine.iso` (`:61`) with `corner_check.iso` (`:85`): only the engine's calls `astimezone`. | AST identity. | S | `test_wb_run_lock.py`, `test_wb_engine.py`, `test_wb_launch.py`, `test_wb_save_point_compression.py`, `test_wb_bridge_connect.py`, `test_wb_corner_check.py`, `test_wb_graph_view.py` |
| A5 | **CLI subcommands** | `cli.main` (121 lines, one `if args.command == ...` chain) -> one function per subcommand wired with `set_defaults(func=...)`; the lazy imports inside each stay (they keep `--help` cheap). | AST identity of the bodies; `gator-workbench --help` and every subcommand's `--help` byte-identical. | S | `test_wb_api.py` (serve), `test_wb_round5_followup.py`, `test_wb_round5_safety.py`, `test_wb_save_point_compression.py` (the CLI tests live there) |

### Group B: backend structure (medium risk, biggest gain)

| # | Package | What moves | Proof | Effort | Covered by |
|---|---|---|---|---|---|
| B1 | **Untie the 20-module knot**, measured after each step | In this order, the cycle script run after each: **(1)** A4 (20 -> 14). **(2)** `task_registry.py`, a leaf: the `tasks.py` constants (`37-127`, `245`, `501-510`: `REAL_PROFILES`, `REMOVED_REAL_TASKS`, `RESULT_ANALYSIS`, `REAL_AUTHORIZATION_REQUIRED`, `CORNER_TASKS`, `MOCK_TASK_REMOVED`, `SYNTHETIC_FIXTURES`, `NATIVE_DRAFT_NOT_EXECUTABLE`, `NETLIST_SOURCE_REMOVED` ...), `TaskBlocked`, `TaskRuntime`, `_verified_profile`, `verified_spec_registry`, plus `profiles.task_spec_registry` and the profile-store reads it needs (`profiles.py:56-98, 163-170`); the spec-registry fallback chain that `compile.py:191-208` and `validation.py:629-643` both spell out (the comment admits it) becomes one resolver there. **(3)** `saved_rows.py`: the pure saved-row comparison of `consistency.py:30-290`; the live Virtuoso check (`291-428`) stays in `consistency`; `validation.py:690` then imports only `saved_rows`: that one edge held the remaining 13 modules together. **(4)** `paths.py` takes `connection_file()` (`connection.py:185`) and `filesystem_type` / `SLOW_FILESYSTEMS` (from `layout`; 5 tests patch `layout.filesystem_type`: rule 5): the 5-module infrastructure knot (`paths -> directories -> connection -> paths`, `layout <-> directories`) goes. **(5)** `checkpoint_codec.py`: the codec half of `save_point_compression.py:32-80` that `checkpoints.py:35` uses (after the peer's 7.286 edit of that file has landed). **(6)** B5's `run_index.py`, so `api/support.py:77` and `profiles.py:987` stop importing `runs` lazily. **(7)** if a knot of `profiles`, `compile`, `validation`, `cdf_rules`, `generic_profile` remains: `quantities.py` with `compile.grid_top`, `normalization_scale`, `group_unit`, `_group_kind`, `KIND_UNITS`, `UNIT_KINDS` and `validation.resolve_leaders`, `_integral` (pure row maths). **(8)** hoist the imports that are no longer cyclic. Every old name re-exported (rule 4), every patched name moved with its tests (rule 5). **Target: no strongly connected component larger than 3 modules**, and a new `tests/workbench/test_wb_structure.py` that fails on a new cycle or on an in-function package import without a reason comment (pure AST, under a second). | AST identity; OpenAPI identical; the structure test; the cycle script's numbers after each step in the record entry. | M | 44 test modules import `tasks`, 32 `runs`, 17 `profiles`, 14 `validation`: the whole suite is the cover; closest: `test_wb_profiles.py`, `test_wb_real_starter.py`, `test_wb_real_bindings.py`, `test_wb_mock_task.py`, `test_wb_task_view_cache.py`, `test_wb_schema_validation.py`, `test_wb_consistency.py`, `test_wb_unsaved_rows.py`, `test_wb_older_rows.py`, `test_wb_directories.py`, `test_wb_local_scratch.py`, `test_wb_storage_budget_paths.py`, `test_wb_spec_equations.py` |
| B2 | **`engine.py` by job, as mixins** | `RunEngine` (1,526 lines) keeps scheduling, lanes, control and limits (`604-669`), dispatch (`671-844`), learner updates (`1077-1133`), save points (`1432-1492`) and finish (`1513-1654`). Out, as mixin classes `RunEngine` inherits, **method names unchanged** so that `monkeypatch.setattr(RunEngine, '_apply_retention')` and `build_run_summary(engine)` (`summary.py:37`, which reads about 25 engine attributes) keep working: `engine_host.py` (simulator-host maintenance `541-603`), `engine_rows.py` (the row builders `1135-1357`: `_candidate`, `_source_name`, `_parameter_rows`, `_metric_rows`, `_job_rows`, `_transition_rows`), `engine_retention.py` (`1358-1431`). `_commit` (228 lines) is split in place along its own comment headers into `_outcome` (validity, feasibility, infrastructure class, receipts: lines 1-90 of it), `_learn_from` (replay admission and the updates: 91-110), `_first_feasibility` (111-125), `_evaluation_row` (151-208) and a `_commit` that calls them in the same order. The 8+-parameter functions (`_candidate` 10, `_metric_rows` 9) keep their signatures in this package. | AST identity for the moved methods; the seeded MOCK differential run (4.3) for the split ones; `test_wb_engine.py`. | M | `test_wb_engine.py`, `test_wb_engine_preparation.py`, `test_wb_host_cleanup.py`, `test_wb_run_speedups.py`, `test_wb_update_rows_persisted.py`, `test_wb_reset_reuse.py`, `test_wb_storage_budget_paths.py`, `test_wb_round5_perf.py`; `run_control_live_check.mjs`, `export_check.mjs` |
| B3 | **`profiles.py` by job** | After B1's registry: `profile_store.py` (`56-180`), `profile_generate.py` (the cell -> profile generator, `183-616`), `task_save.py` (`save_task`, `649-843`, 14 parameters, split into one function per step it already names: `copy`, `setup`, `deck`, `read`, `files` at `profiles.py:701`, called in the same order with the same `progress` marks), `baseline_reference.py` (`844-1004`: what `engine` and `circuit_load` call); `profiles.py` keeps deletion (`1006-1053`) and re-exports everything (`profiles.save_task` is patched by 4 tests, `adopt_baseline_run` by 2, `reference_metrics` by 2, `record_reference` and `profile_entry` by 1: rule 5). | AST identity; `test_wb_task_save.py` (428 lines), `test_wb_profiles.py` (558), `test_wb_task_saving.py`; `task_save_check.mjs`, `unsaved_rows_check.mjs`, `testbench_probes_check.mjs`. | M | as named, plus `test_wb_generic_profile.py`, `test_wb_task_baseline.py`, `test_wb_model_library.py` |
| B4 | **`pdk.py` by job** | Five seams: `pdk_remote.py` (the SKILL programs and the Virtuoso read, `105-185`, `1314-1477`; callers `bridge_read`, `model_library`); `cdf_text.py` (CDF text, `192-345`, `678-750`; `_number`, `_fields`, `_write_source` get public names and keep the underscore aliases that `cdf_facts.py:23, 105` and `cdf_rules.py:27` use); `model_scan.py` (Spectre model scanning, `347-680`); `vocabulary.py` (`1159-1312`; callers `runs`, `engine`, `modes`, `checkpoints`, `trajectory`, `graph_view`, `api`); `pdk.py` keeps the record build and the store (`753-1160`) and re-exports the rest as a facade. | AST identity; `test_wb_pdk.py` (541 lines) and its follow-ups; `pdk_check.mjs`. | M | `test_wb_pdk.py`, `test_wb_native_cells.py`, `test_wb_model_library.py`, `test_wb_cdf_write.py`, `test_wb_review_fixes.py`, `test_wb_faster_calls.py` |
| B5 | **`runs.py` by job** | Seven jobs in one file: the settings store (`56-92`), the learner-contract cache (`206-257`), prepare and resume (`344-597`), continuation (`601-675`), the experiment registry (`677-750`), worker launch (`752-830`), status and lineage (`832-873`), the source-digest cache (`900-935`), the run-list cache and read pool (`962-1108`). Out: `settings_store.py` (used by `api/*` and `reachability`), `run_index.py` (`_fingerprint`, `_run_facts`, `list_runs`, `read_many`, `checkpoint_listing(s)`, the source digest, `_resumability`; used by `api` and `profiles`), `experiments.py`. `runs.py` keeps prepare, resume, continuation, launch, commands, status and the contract cache. Patched names here are the most numerous (rule 5: `current_source_digest` 6 tests, `read_json` 2, `_RUN_CACHE`, `_RUN_CACHE_LOCK`, `_CONTRACTS`, `_SOURCE_DIGEST`, `CONTRACT_CACHE_MAX`, `launch_worker` 3, `load_task` 2, `list_runs`, `run_status`, `write_json`, `_check_consistency`): the functions that read those names stay in the module the tests patch, or the tests move in the same commit. `prepare_run` (159 lines) is split along its steps (consistency, connection gate, provenance, manifest, layout) only with the differential run of 4.3 in place. | AST identity; OpenAPI identical; the differential run if `prepare_run` is split. | M | `test_wb_run_list.py`, `test_wb_run_list_cache.py`, `test_wb_faster_calls.py`, `test_wb_contract_cache.py`, `test_wb_can_continue.py`, `test_wb_launch.py`, `test_wb_model_chooser.py`, `test_wb_lineage.py`, `test_wb_api.py`; `run_list_check.mjs`, `model_chooser_check.mjs` |
| B6 | **Long functions, where B2-B5 pass anyway** | `calibrate` (147), `connection.run_layers` (134), `pretrain.prepare_pool` (131), `readiness.build` (128), `validation._check_parameters` (121), `_check_run` (91): extract the named steps each already has as comments, same order, same variables. The 8+-parameter functions (`save_task` 14, `modes.build` 13, `task_files.build` 12, `checkpoints.save` 10, `best_design.write_outputs` 9) get a parameter object only when their package splits them anyway: call sites and patches multiply the risk. **Not** `ngspice_netlist.parse_text` / `expand` (a parser; its length is its grammar) unless a bug brings a session there. | Tests of each area; AST identity does not apply (bodies split), so each gets a before/after check on recorded inputs: `calibrate` on a recorded calibration run folder, `run_layers` on the fake bridge of `test_wb_connection.py`, `_check_parameters` on the saved tasks' `task.json` files (every `Report` identical). | M | `test_wb_calibration.py`, `test_wb_connection.py`, `test_wb_readiness.py`, `test_wb_pretrain.py`, `test_wb_schema_validation.py` |
| B7 | **Route bodies into the modules they belong to** | The route becomes a one-line call; the body moves verbatim into a named function of its module: `run_routes.describe_model` (`120-163`: compiles, builds the learner contract, calls the private `runs._vocabulary_for`, assembles the vocabulary block) -> `runs` / `checkpoints`; `status` (`286-319`: manifest view, pretraining sources, calibration block) -> `runs.status_details`; `default_model` (`165-183`) -> `runs`; the row cleaning in `table` (`371-390`) -> `DatasetReader`; `circuit_routes.circuit_load` (`52-99`: baseline-adoption retries `61-72`, the hierarchy tree `85-90`, a 20-field answer) -> `tasks`; the "verified" rule (`351-360`) -> `structures`; the cell/copy/state-folder resolution (`279-300`) -> `working_copy`; `context.py:76-81` (compile plus `graph_contract`) -> `readiness`. | OpenAPI identical; AST identity of the moved bodies; route tests. | M | `test_wb_api.py`, `test_wb_model_chooser.py`, `test_wb_lineage.py`, `test_wb_matched_devices.py`, `test_wb_working_copy.py`, `test_wb_readiness.py`; `model_chooser_check.mjs`, `task_run_check.mjs`, `working_copy_check.mjs`, `matched_devices_check.mjs` |
| B8 | **One helper per repeated pattern, messages unchanged** | `storage.atomic.read_json_quiet` for the ~30 `try: json.loads(p.read_text()) except (OSError, ValueError)` sites (it keeps `read_text()` *without* an encoding argument: `read_json` reads UTF-8, so swapping `read_json` in would change behaviour); `read_dict(p)` for the 26 `read_json(p, default=None) or {}`; `run_lock` and `command` in `RunLayout`'s name table (`layout.py:52`) for the 8 + 4 spelled-out paths; `paths.bridge_session_lock()` for the 4; `connection.named_or_active()` for the 3 "named connection, else the active one" (`tasks.py:297-301`, `ngspice_tasks.py:246-248, 262-264`); `connection.family_of_profile()` for the 6 kind/family checks **only where the guard is the same** (`tasks.py:308` does not guard against a non-dict profile, the others do: it keeps its own line unless the non-dict case is proved unreachable); two private helpers for the connection-file read-or-refuse, backup, write of `bridge_connect.create_profile` (`291-330`) and `save_directories` (`355-402`), which share their refusal text; `tasks.bridge_config_of(connection)` for `tasks.py:652-655` and `corner_check.py:643-645` (the pair kept in step by a comment today); `learner_contract` called from `_resume_checks` (`585-588`) instead of a second assembly that also reads `run_vocabulary` twice; `paths.inside(path, roots)` for `api/context.py:42`, `circuit_routes.py:173`, `ngspice_tasks.py:232`. **Not merged:** the "is a run of this task working, then move the folder into `.deleted`" pair (`profiles.py:1010-1052`, `ngspice_tasks.py:205-224`): `profiles` skips mock rows, `ngspice_tasks` skips rows without `run_dir`; they can share the `TRASH` constant and the timestamp format (spelled three times) and nothing else. | AST identity does not apply (bodies change): each pattern gets a table of inputs -> outputs generated from the old code and replayed on the new (the differential-fuzzer recipe of record 7.144), plus the tests. | S to M | `test_wb_profiles.py`, `test_wb_working_copy.py`, `test_wb_run_lock.py`, `test_wb_bridge_connect.py`, `test_wb_connection_kinds.py`, `test_wb_corner_check.py`, `test_wb_ngspice.py`, `test_wb_contract_cache.py` |
| B9 | **Names and constants** | Private names used from other modules get a public name and keep the underscore alias: `runs._vocabulary_for` (`run_routes.py:150`), `runs._run_facts` (`profiles.py:991`), `tasks._verified_profile` (`compile.py:220`, `corner_check.py:109, 133`), `tasks._profile_settings` (`corner_check.py:642`), `tasks._member_variable_id` (`structures.py:296`), `ngspice_tasks._clean_kinds` (`circuit_routes.py:163`), `units._LOOKUP` (`settings_routes.py:34`), `model_structure._rebuild` / `_same_tensors` (`graph_view.py:38, 42`), `pdk._number` / `_fields` / `_write_source` (B4), `generic_profile._same` (`cdf_write.py:44`), `spec_equations._finite` (`reward_diagnostics.py:5`), `validation._check_equation` (`profiles.py:687`), `engine._clock` / `_segment_started` (`summary.py:37`). The word `settings` means three things (the `settings.json` dict, `runs.py:62`; a connection-profile dict, `connection.py:105, 124, 311`, `tasks.py:304, 319`; rehearsal settings, `rehearsal.py:78`): internal parameter names become `profile` / `remembered` where no caller passes them by keyword (grep-proved). Duplicated constants go to one leaf `names.py`, merged **only where the strings are byte-equal** (printed and compared first): the Cadence-name regex (6: `bridge_read.py:29`, `bridge_setup.py:34`, `cdf_facts.py:27`, `cdf_write.py:48`, `native_cells.py:37`, `api/models.py:11`), the profile-id regex (3), the task-name regex (3), the live-run-state tuple (4: `runs.py:836, 981`, `profiles.py:1007`, `ngspice_tasks.py:212`), the loopback hosts (`cli.py:84`, `api/app.py:18`), the clean exit states (`cli.py:129`, `worker.py:74`), and `tasks.py:468`, which re-spells `connection_file()`. | AST identity (an alias is an addition, not a change); a printed table of the merged constants' values. | S | the whole suite |
| B10 | **Caches and locks get an owner** (decision items inside) | About 20 module-level caches with no single reset and six different file-fingerprint recipes (`runs` x4, `tasks._view_cache`, `consistency._FILES`, `reachability`: 2 dicts + 3 `lru_cache`, `reward_diagnostics._STEERING`, `corner_check._TABLES`, `training_series` x3, `calibration._AGAIN`, `ocean._CLIENTS`): a small `caches.py` registry (`register(name, clear)`, `clear_all()`) that each cache joins **keeping its own recipe and its name** (tests clear five of them by their private names); the two global read pools (`runs.py:1029`, `training_series.py:60`) become one. Logic kept in step only by comments becomes one function: `training_series._learner:607` with `engine.py:252`; `corner_check._bridge_parts:638` with `tasks._real_runtime` (B8's `bridge_config_of`); `compile` with `validation` (B1 step 2). **Decision item:** the locks handed over through module globals (`runs._HELD_LOCKS`, taken back at `run_routes.py:71`; `corner_check._STARTING`): having `prepare_run` return the lock is the honest design, but it changes a signature that 18 test files call: do it with B5 or not at all. | AST identity where bodies move; `test_wb_task_view_cache.py`, `test_wb_run_list_cache.py`, `test_wb_contract_cache.py`, `test_wb_round5_perf.py`; the differential run. | M | as named, plus `test_wb_training_series.py`, `test_wb_corner_check.py` |

### Group C: frontend (independent of A and B: another session can do it alongside)

Frontend rules on top of section 2: the DOM stays the same (the checks match `textContent`, the classes `.status-grid`,
`.banner`, `.training-chart`, `.bottom-body`, `.task-list-key`, the ids `#output-root`, `#blocking-issues`, the
`data-field` / `data-editor` / `data-task-key` / `data-mode` / `data-encoder` attributes, the window titles
"GATOR - runs" (13 references), "GATOR - RL model" (8), "GATOR - Virtuoso cell" (7), and the storage keys: the config
key alone is named 68 times in the scripts). The source fixtures import `src/store`, `panels/Left` and
`panels/RunTabs` by path: those files stay, as barrels if their content moves. No React context is introduced: the
`memo` boundaries (`Right.tsx:699`, `Left.tsx:655`, `RunList.tsx:336`, `RunTabs.tsx:267`, `Editors.tsx:811`) rely on
App's stable callbacks, and a context would change what re-renders. Known hazards that a move must carry over
unchanged, not "fix": writes during render (`App.tsx:174-175, 260-261, 298-299, 497-498`, `Left.tsx:374`,
`RunControl.tsx:129-132`, `TrainingTab.tsx:131`), the effect order around the status poll (`App.tsx:248` after
`useRunControl`), the `followedTask` ref that silences an effect (`App.tsx:433`), the effects that write the config
without an Undo step (`Right.tsx:334, 388, 393`, `App.tsx:164`), and the window events (`openAt.ts`;
`SAVE_TASK_REQUEST` answered by mutating the event's `detail`, `TaskSave.tsx:45-50, 187`; `TASK_BASELINE_STARTED`,
`App.tsx:336`).

| # | Package | What moves | Proof | Effort | Covered by |
|---|---|---|---|---|---|
| C1 | **`runState.ts`** | The run-state lists, `isLive`, `phaseOf` and `useRunControl` out of `RunControl.tsx:18-148`: `App`, `RunList`, `RunTabs`, `RunBrief` and `TrainingTab` import that component file only for its constants. The "resting" rule is written twice (`launch.ts:132`, `RunTabs.tsx:119`) and the "live" rule three times (`App.tsx:248`, `RunBrief.tsx:34`, `TrainingTab.tsx:113`): merged only where the expressions are identical token for token; a variant that differs stays as its own named function in the same file. The header-run storage key written out twice (`App.tsx:87`, `RunControl.tsx:18`) becomes one constant. | DOM snapshot (4.7); `tsc`. | S | `run_control_check`, `run_control_live_check`, `launch_recovery_check`, `save_now_check`, `training_tab_check` |
| C2 | **`contract.ts`** | One import-free module with the storage keys, the pop-up window titles and the root ids that the page and the check scripts both name. The harness imports it the way `unit_text_check` imports `units.ts` today, so a key renamed in the page fails the checks at import time instead of silently. | `tsc`; every check. | S | all |
| C3 | **`store.ts` by concern** | Six concerns in one file (rows-from `5-17`, the task-save signal `18-27`, the config migrations `47-171`, the pop-up/visibility registry `173-202`, Undo history `204-283`, the request hooks `285-368`) become `migrations.ts`, `windows.ts`, `history.ts`, `requests.ts`; `store.ts` stays as the barrel the fixtures import. The four hand-made subscribable stores (`theme.ts:14-38`, `store.ts:21-27`, `CircuitPicture.tsx:13-20`, `Pdk.tsx:31`) share one `signal()` helper only if each keeps its exact semantics (same listeners, same timing). | DOM snapshot; `tsc`. | S | `request_lifecycle_check`, `edit_state_check`, `typing_check`, `reliability_check` |
| C4 | **`Right.tsx` by panel** | First `fields.tsx` (`Num` 14-28, `ByteSize` 46-63, `Module` 71-96, `Check` 100, `LookFold` 173), `OutputPanel.tsx` (701-794), `ResearchPanel.tsx` (796-824). Then the RL model window out of `RunPanelBody` (182-695): a `useRlModel()` hook that stays mounted in `RunPanel` (the state lives on while the window is closed, `Right.tsx:192`) and returns one object that `RunConfiguration.tsx` (494-527), `RewardConditions.tsx` (528-576) and `RlModelWindow.tsx` (578-692) read; the advanced-fields fragment (468-486) rendered twice (606, 688) becomes one component; the model text helpers a pure `rlModelText.ts`. | DOM snapshot in both looks with the RL model window open; `tsc`. | S then L | `network_panel_check`, `model_chooser_check`, `mode_suggestion_check`, `module_fold_check`, `output_panel_check`, `reward_block_check`, `pdk_check`, `encoder_models_check`, `model_structure_check`, `graph_view_check` |
| C5 | **`App.tsx` into hooks** | `Page` (110-632: 20 `useState`, 13 `useRef`, 10 effects) loses, in this order and one commit each: `BottomPanel.tsx` (69-74, 119-131, 506-534, 605-629); `useCalibrationOffer` (224-240); `useRunWindowActions` (407-504); `useLaunchActions` (345-405, into `launch.ts` beside `useLauncher`); `useRunList` (115-116, 167-184) and `useShownRun` (82-93, 117, 197-223, 241-249); `useLiveRunAdoption` (259-284); `useTaskRunFollow` (285-311 with the writes at 433-436). Each hook takes and returns exactly the values the component used, so the effect order inside `Page` is unchanged (hooks run in call order). | DOM snapshot; the request log (4.7) of a page open + task choice + Runs window identical; `tsc`. | M to L | `looks_check`, `room_check`, `calibration_check`, `calibration_save_check`, `run_list_check`, `task_run_check`, `run_control_check`, `run_control_live_check`, `launch_recovery_check`, `export_check` |
| C6 | **`Editors.tsx` by part** | `editorRules.ts` (the pure rules 17-59, `readNumber` 82, `withFollowers` 330-364), `cells.tsx` (`Cell` 92, `QuantityBox` 131, `UnitSelect` 148, `LimitSelect` 65), `FormulaBar.tsx` (163), `DiffView.tsx` (218); `EditorsView` keeps JSON import (403-433), fill/copy/paste (542-665) and the unsaved-row marks (667-711) as three named inner functions. Removes the `Editors` <-> `MatchedDevices` import cycle (`MatchedDevices.tsx:3`). | DOM snapshot with each editor tab; `tsc`. | M | `sheet_check`, `find_fill_copy_check`, `formula_bar_check`, `editor_columns_check`, `spec_equations_check`, `unsaved_rows_check`, `typing_check`, `matched_devices_check` |
| C7 | **Shared primitives that reproduce today's DOM exactly** | A pop-up window component for the 10 `usePopupWindow` callers (8 `popup && root && createPortal` blocks; 9 "pop-up blocked" lines in 6 tag/class variants: the component takes tag, class and role so each caller's DOM stays byte-identical); `useNewest()` for the 14 hand-written "newest answer wins" guards (`mine = ++x.current`; `App.tsx:177, 445, 467`, `Left.tsx:124, 292, 334`, `Right.tsx:286, 302, 411, 720` ...); `oncePerBrowser()` (`App.tsx:139-152`, `Right.tsx:307-324`); `kept.ts` for the ~32 `try { localStorage... } catch` sites. The 12 "Copy" sites keep their 4 mechanisms (the RL model window copies through the main window's clipboard, `Right.tsx:672`; `RunList.tsx:257` and `Connection.tsx:100` do not): choosing one is a behaviour decision, not this plan. The 9 message-level-to-class mappings stay per site (`Left.tsx:418` maps warn to `error`). | DOM snapshot with every window open; `tsc`. | M | `callouts_check`, `connection_panel_check`, `agent_window_check`, `crash_panel_check`, `module_fold_check`, `ngspice_window_check`, `task_list_check` |
| C8 | **Formatters in `format.ts`** | The date formatters (`Connection.tsx:16`, `Pdk.tsx:26`, `WorkingCopy.tsx:59`, `ModelChooser.tsx:27`, `TrainingTab.tsx:70, 90`, `App.tsx:46, 441`), the two duration formatters (`RunList.tsx:36`, `RunBrief.tsx:18`: they differ under 60 s, so two named variants), the three SI prefix tables (`units.ts:40`, `Editors.tsx:80`, `WorkingCopy.tsx:14`), `taskOf` (`RunList.tsx:45` vs `TrainingTab.tsx:67`) and the state-to-class maps (`RunList.tsx:48` vs `TrainingTab.tsx:95`, `interrupted` differs): moved, named, **never merged where the output differs**. `TrainingTab`'s `clock(seconds)` shares its name with `format.ts`'s `clock()`: renamed at the import, no caption changes. The scripts' own `stamp`/`two` copies (`run_list_check:28`, `task_list_check`, `task_run_check`) can import `src/format.ts` afterwards. | A table of inputs -> outputs per formatter, generated from the old code, replayed on the new. | S | `unit_text_check`, `run_list_check`, `task_list_check`, `training_tab_check` |
| C9 | **`Left.tsx` by job** | `VirtuosoWindow.tsx` (516-640), `useTaskChoice` (319-374), `useTestbenchProbes` (280-317), `useTaskActions` (182-249); `CircuitPanelBody` keeps the circuit load (108-154) and the cell import (254-278). | DOM snapshot with the Virtuoso window open; request log of a task choice. | M to L | `task_list_check`, `task_rows_check`, `virtuoso_source_check`, `testbench_probes_check`, `working_copy_check`, `project_help_check`, `circuit_source_check`, `consistency_check`, `ngspice_window_check`, `task_save_check`, `edit_state_check` |
| C10 | **`TrainingTab`'s two read loops** | One `useTrainingReads` for the two near-identical loops (154-177, 188-212), parameterised by what differs. `api.ts` loses what is not a request: the formatters (189-191, 235-245) go to `format.ts`, the shared caches (216-234) to `shared.ts`; the one direct `fetch` in a panel (`RunControl.tsx:166`, the same URL as `api.runConfig`) is left as it is unless its error handling is proved equal. | DOM snapshot of the Training tab on a recorded run; `tsc`. | S to M | `training_tab_check`, `training_data_check` |
| C11 | **`styles.css` regrouped by component** (optional) | The file grows in record order, so selectors are restated (`table.editor td.sel` at 108/126/160, `header` 34/442, `.tabs` 82/443). Regrouping changes the cascade order: allowed only with the computed-style proof below. The 5 monospace stacks that differ from `--f-mono` and the 10 bare-button resets stay as they are (merging them would change rendering). | Computed-style snapshot: every element's `getComputedStyle` on the page and in each window, both looks, before and after; byte-identical. | M | `looks_check`, `room_check`, `callouts_check` |
| C12 | **`trainingData.ts` split** (last, optional) | `training/{store,series,prep,catalog,build,compare,keys}.ts` behind a `trainingData.ts` barrel (storage classes 64-169, `TrainingStore` 170-361, series maths 363-480, chart types and the caption catalogue 481-530 + 927-981, incremental preparation 531-926, builders 983-1120, run comparison 1121-1258, key numbers 1259-1306). **The risk:** the file's header promises no imports because `training_data_check.mjs:29` and `training_chart_profile.mjs:37` load it under Node's type stripping, and both copy that one file to a temporary folder to load a reference version (`training_data_check:411-418`, `training_chart_profile:28-35`). A split needs `.ts` import suffixes and `allowImportingTsExtensions` in `tsconfig.json`, and both loaders copying a folder. | `training_data_check` (the pure functions) and the chart profile's numbers identical. | L | `training_data_check`, `training_tab_check`, `training_chart_profile` |

Frontend proofs: section 4.7 (DOM snapshot and request log), with `tsc --noEmit`, `vite build` of the copy, then
`run_checks.sh --lanes 2`.

### Group D: tests and browser checks

| # | Package | What moves | Proof | Effort | Covered by |
|---|---|---|---|---|---|
| D1 | **Shared test helpers** (the test-modules-as-libraries problem of 1.7) | `probe` is imported from `test_wb_api` by 18 test modules (a test module used as a library): it moves to `helpers.py`; `ngspice_probe` is defined twice (`test_wb_connection_kinds.py:243`, `test_wb_ngspice.py:54`); the `client` fixture is defined in 5 modules, `config` in 4, `rows` in 4, `prepared` / `learner` / `finished` / `fake_reader` in 3 each: one definition each in `tests/workbench/conftest.py` or `helpers.py` **where the bodies are identical** (compared first; a variant keeps its own name). `create_app(...)` is spelled out 51 times in 34 files: about 28 of them say exactly what `helpers.workbench_app` does and can call it; the other 21 (15 modules) leave `auto_check_on_start` on, which starts the background connection-check thread (`api/app.py:77`), so they call `workbench_app(..., auto_check_on_start=True)` and keep that behaviour. `test_wb_reward_v21.py:14 ota()` bypasses `make_config` on purpose (pinned hashes) and stays. The library imports of 1.7 (`probe`, `wait_for`, `read_cell`, `FakeBridge`, `monitor_for`, `SETUP`, `setup_writer`, the cell constants) move to `helpers.py` / the fakes modules of D6, and the test modules import them from there. | The suite; the count of tests collected unchanged. | S | the suite |
| D2 | **Test modules named after the feature** (renames and moves of tests only; a `tests/fixtures/synthetic/*.scs` file never moves) | Each round-named module's tests join the module of the feature they test, by the line numbers of the survey: `test_wb_round5_integration` (3 tests: `:28` -> `test_wb_launch`, `:43` -> a new `test_wb_settings`, `:55` -> `test_wb_api`); `test_wb_round5_followup` (5: api, ngspice, engine x2, run_lock); `test_wb_round5_reward` (5: reward_v21 x2, corner_check x3 with its helpers at lines 1-76); `test_wb_round5_safety` (20: worker start and manifest wording -> launch; settings `:79-173` -> `test_wb_settings`, the atomic-write tests `:109`, `:123` -> storage_budget_paths; `:201-239` -> api; `:269`, `:329` -> storage_budget_paths; `:309` with `two_runs` -> run_list_cache); `test_wb_round5_perf` (13: decimal ranges `:34-99` -> schema_validation; `:141-191` -> generic_profile / cdf_write; then graph_view, read_efficiency, pdk, matched_devices, engine, mock_task); `test_wb_review_fixes` (7: profiles, save_now x3, storage_budget_paths, read_efficiency, pdk); `test_wb_run_speedups` (5: engine x2, update_rows_persisted x3); `test_wb_faster_calls` (12: profiles x3, connection x2, run_list_cache `:92-141`, read_efficiency, pdk x2); `test_optimizer_round5` (10: actions x3, corner_summary, runtime_recovery x2, sizing_env x2, graph_sac, input_cache); `test_reward_v2_audit_fixes` (3: sizing_env x2, reward_v2). The retirement contracts (`test_wb_retired_*`, `test_wb_search_removed`, `test_wb_tested_defaults`) stay as they are. Every moved test keeps its name and body; the record entries that name the old module get one line saying where its tests went. | The number of tests collected unchanged (the last line of `pytest --collect-only -q`); every moved test found by name in its new module. | M | the suite |
| D3 | **Markers where they do work** | `xdist_group` only on the tests that use a module-scoped fixture: `test_wb_pdk`'s four `pdk_run` tests move to `test_wb_pdk_run.py` and un-pin the other 17; `test_wb_training_series`'s five; `test_wb_learner_step` (no module fixture) loses the mark; `test_wb_round5_safety:301 two_runs` is function-scoped. `requires_evidence` as a `pytestmark` in `test_reward_v2_real_data` (8 of 9 tests carry it by hand) and the `real_transition` fixture shared from a support module instead of built twice. | Suite time with `-n 12 --dist loadgroup` not worse; the same tests collected. | S | the suite |
| D4 | **Big test modules by concern** | `test_wb_training_series.py` (946 lines): the frozen-oracle reader (`:82-455`, the oracle copy into its own file) apart from the record-7.221 cache layer (`:456-946`, its `SyntheticRun`/`Page` harness `:481-564`); `test_graph_sac.py` (664): encoders, SAC update and temperature, replay, checkpoints, collector, zero-gamma, with `observation`, `transitions`, `learner` in a support module; `test_wb_cdf_write.py` (635): its 175-line `FakeVirtuoso` SKILL interpreter (`:197-383`) becomes `fakes_virtuoso.py` (its `make` / `config` are imported by `test_wb_ngspice:350` and `test_wb_round5_perf:170`); `test_wb_profiles.py` (558): create profile, first baseline, one task per cell, baseline records itself, and its library part into `fakes_virtuoso.py`. The shared fakes get homes: `tests/workbench/fakes_virtuoso.py`, `fakes_connection.py`, `tests/support/` for the research tests; `tests/__init__.py` and `tests/workbench/__init__.py` so that one root (`tests.workbench.helpers`) replaces the two spellings (a decision: it changes how pytest names modules, so `--deselect` paths in scripts and docs are checked). | The same tests collected; `pytest --collect-only` names compared before and after. | M | the suite |
| D5 | **Check-script library** | Pieces re-implemented per script move into `lib/`: the route-answer ladders (32 scripts), `shot` (24), `until` (15), `press` (13), the run-status fixture factory `statusOf` (5: `launch_recovery`, `run_control`, `run_list`, `save_now`, `task_run`); the 8 checks that hand-write their ending (`edit_state`, `project_help`, `request_lifecycle`, `testbench_probes`, `virtuoso_source`, `reward_v21`, `reward_v2_frontend`, `reward_v2_real`) end through `runChecks`; the three `reward_*` checks' `browser-report.json` (special-cased at `run_checks.mjs:128`) is folded into the same ending; the runner's expected-duration table (`run_checks.mjs:37`, 20 of 55 checks) is derived from the last run's log instead of kept by hand; the stale storage-key seed at `calibration_check.mjs:50` (a key the page no longer reads) goes. Boilerplate is only 10-15 % of the 12,157 check lines (about 1,470 comment lines, 530 setup/teardown, 325 route answers, 450 fixture data); the rest is real checking and stays as it is. | Every check's PASS count unchanged (2,025 at HEAD); `run_checks.sh --lanes 2`. | M | all checks |
| D6 | **Structure tests** | `tests/workbench/test_wb_structure.py` (B1): no strongly connected component above the agreed size, no in-function package import without a reason comment, no module outside `api/` importing `api.*`, and the patched-name check of rule 5 (every `monkeypatch.setattr(<module>, '<name>')` names an attribute the module defines). | The test itself. | S | - |


## 4. Proofs, the same for every package

### 4.1 AST move-identity

Every function and class of the old tree, by name, has a syntax-tree-identical twin in the
new tree and vice versa (docstrings and line numbers ignored); the script prints the names whose bodies differ and
that list must equal the package's declared splits. Verified on HEAD against itself: 1,324 names, 0 differing.

### 4.2 Route identity

`json.dumps(create_app(serve_frontend=False, auto_check_on_start=False).openapi(), sort_keys=True)`
with `GATOR_WORKBENCH_SETTINGS_DIR` pointed at a scratch folder: 71,764 bytes, sha256 `9eb4e5b0a052d419…` at HEAD;
the same bytes after every backend package.

### 4.3 Seeded MOCK differential run

(packages B2, B5, B6 and any split of a function on the run path): the same
configuration (`tests/workbench/helpers.make_config`, the synthetic OTA5 stand-in, seed fixed, 1 lane, 30
evaluations, save point at 10) run under the old and the new tree into two scratch output roots; every Parquet
table read through `DatasetReader`, the manifest, the status file and `summary.json` compared after normalising
paths, timestamps, pids and the `code_provenance` block. The round-5 optimizer fixes were proved the same way.

### 4.4 Structure metrics

before and after, in the record entry: long functions, in-function imports, the largest
strongly connected component, the biggest file. Both scripts live in the executing session's scratchpad; B1 turns
the cycle check into a test.

### 4.5 Full regression on a clean copy

of the exact tree to be committed: `pytest -q -n 4 --dist loadgroup` while
the queue runs (`-n 12` on a quiet machine), `tsc --noEmit`, `vite build`, `frontend/scripts/run_checks.sh --lanes 2`
(52 scripts, 2,025 checks at HEAD; `model_structure_check`'s known data failure aside).

### 4.6 Reversal grep

after the commit (the shared-index recipe): no committed line missing from the working tree.

### 4.7 DOM snapshot and request log (frontend)

A new hermetic check
`dom_identity_check.mjs` (harness, fixtures, `readOnly`) opens the page against canned answers, in both looks, with
each window opened in turn (Runs, RL model, Virtuoso cell, Connection, Agent, Folders), and writes `#root`'s
`outerHTML` (React's internal attributes stripped) and the ordered list of requests the page made, to a folder; the
reference is taken from HEAD once, and each package's build must reproduce it byte for byte. `tsc --noEmit` and
`vite build` of the copy, then `run_checks.sh --lanes 2`.

## 5. The live tree, the running queue, and going live

- 8765 (pid 2603654, started 2026-10-08 23:14 by the "Frontend workbench layout design" session) serves the page; a
  CLI run of the encoder comparison's stage D (pid 2800619) is in flight and the queue starts the next one by itself.
- **Python modules a live process has not imported yet are read from disk when first used.** The engine imports
  `profiles`, `calibration` and `ngspice_tasks` inside its finish (`engine.py:1599, 1616, 1638`), and the queue's next
  run imports everything afresh. So: no file under `src/gator_workbench/` is renamed, removed or made to import a
  module that does not exist yet while a run is live. *Adding* a module is safe; *moving* a function to a new module
  with a re-export in the old one is safe for a process that has already imported the old module, and for the next
  run it is the tested tree. The executing session checks `ps -eo pid,args | grep "gator_workbench.cli run"` before
  copying anything into the live tree and lands a package only between runs, or after the queue has exited.
- The page: A-B change no request and no bundle. C changes the bundle: `npm run build` only on the user's word and
  never while a real run is watched in the browser (CLAUDE.md); 8765 restart only on the user's word.
- Tests: `-n 4` and `--lanes 2` while the queue simulates.

## 6. The optimizer package: advice only, for a digest step the user may choose

Any edit under `src/analog_optimizer/` changes `source_digest()`, so the running encoder comparison's save points
and every model saved since 7.228 would resume only from the old commit, and the M5/M6 audits run only from their
own commits anyway (CLAUDE.md). **Recommendation: no digest step now.** If the user chooses one later (after the
encoder comparison and its reports are closed), these are the structural items worth taking in that one step, in
order of value; each keeps every public import path and signature, because the pinned `examples/*.py` import about
100 package names from some 45 modules.

| # | Smell | Effort | Covered by |
|---|---|---|---|
| E1 | `CircuitSizingEnv._evaluate` (`envs/sizing.py:306-670`): 365 lines and seven nested closures (`launch` :404, `settle` :436, `keep` :496, `halt` :503, `coordinator_stop` :519, `one_at_a_time` :527, `side_by_side` :540) mixing export and apply, condition scheduling, observation building, reward and the record commit | L | `test_sizing_env`, `test_parallel_corners`, `test_reset_recheck`, `test_reward_v21_episodes`, `test_reward_v2_audit_fixes`, `test_recording`, `test_runtime_recovery`, every workbench run test |
| E2 | No public environment operations for what the workbench lane does: `lanes.py:124-157` writes `env._done`, `env._recording_observation`, `env.steps`, `env.episode` and calls `env._evaluate` directly (continue, calibration, retry). Public `continue_from` / `evaluate_only` methods would let the workbench stop reaching in | M (package and workbench) | `test_wb_engine`, `test_wb_launch`, `test_wb_calibration`, `test_wb_reset_reuse` |
| E3 | The training-step block written three times: `training/runner.py:88-125`, `training/parallel.py:232-300`, `evaluation/benchmark.py:205-245` (and a fourth in the workbench's `lanes.py` / `engine.py`). The random-number draw order must stay exactly the same | M | `test_graph_sac`, `test_recording`, `test_reward_v2_budget`, `test_reward_v21_episodes`, `test_parallel_training`, `test_runtime_recovery`, `test_native_preparation`, `test_transfer`, `test_cross_category`, `test_benchmark_runtime` |
| E4 | Very long orchestration: `collect_parallel_episodes` (`parallel.py:124`, 222 lines, 17 parameters), `run_benchmark` (`benchmark.py:289`, 190), `run_episode` (`:157`, 130) | L | as E3 |
| E5 | `recording/store.py`: one class with 37 `_op_*` handlers reached by string dispatch (`call`, `:147`), mixing schema and the writer thread, the evaluation lifecycle (`:214-370`), state dedup (`:300-418`), `_summary` (`:419`) and workspace retention (`:548-746`); the op names are a public interface used about 30 ways | M | `test_recording`, `test_recording_overhead` (calls `_op_asset`, `_state`, `_op_finalize_workspace`), `test_runtime_recovery` |
| E6 | `backends/virtuoso_bridge.py` mixes generic utilities (`digest` :31, `write_json` :35, `parameter_rows` :42, delegation :54-89, deck text :91-112) with the adapter (`run_simulation` :540, 93 lines); moving the utilities needs re-exports | S to M | `test_bridge_adapter`, `test_native_preparation`, `test_parallel_corners`, `test_raw_format`, `test_vco`, `test_wb_cdf_write`, `test_wb_connection` |
| E7 | `native_preparation.py:257-297` repeats `VirtuosoBridgeBackend._attach` / `_require_connection` (`:148`, `:225`): only the owner identity and the error messages differ, and the messages must be kept | M | `test_native_preparation:65-67`, `test_parallel_corners:185` |
| E8 | Small duplicates: `parameter_rows` in `sizing.py:36` and `virtuoso_bridge.py:42`; identical Mock/Synthetic `connect` / `close`; `_require_connection` (`mock.py:40`) vs `_check` (`synthetic_sizing.py:39`); `SyntheticSizingBackend.generate_netlist` (`:57`) lacks the base class's `condition` keyword (`backend.py:128`); `digest` means file bytes in one place and JSON in another (`transfer.py:15`) | S | `test_backend`, `test_conditions`, `test_recording` |
| E9 | The `analyze()` start-up code repeated in `ldo.py:73`, `opamp.py:11`, `vco.py:101`; **`opamp.analyze` has no test**, so it gets one first | S to M | `test_ldo`, `test_vco` |
| E10 | Other long functions: `parse_text` (`spectre_parser.py:159`, 186 lines), `evaluate_conditions` (`specs.py:197`, 153), `RunReader.overview` / `export` (`reader.py:49`, `:158`), `summarize_corners` (`corners.py:103`) | M each | `test_parser`, `test_reward_v2`, `test_reward_v21_properties`, `test_recording`, `test_corner_summary` |

No dead parameters are worth a step: the unused ones are required by interfaces (`backend.py:134, 153, 160`, the
`__exit__` arguments, `forward` in `models/encoders.py`).

**Coupling the step must keep stable** (what the workbench relies on today):

- the private environment internals of E2 (`lanes.py:124-157`);
- `connection.py:359` calls `VirtuosoBridgeBackend._check_windows(SimpleNamespace(client=...))` unbound, on a stand-in;
- `cdf_write.py:534-547` overrides the private hooks `_write_widths` and `_verify_restored` (`virtuoso_bridge.py:270,
  277`), and `backend_class()` looks `virtuoso_bridge.VirtuosoBridgeBackend` up through the module at call time;
- `generic_profile.py:106, 140, 182` inherits `_on_width_grid`;
- `checkpoints.py:162-165` reads `replay._items` and `_position`; `checkpoints.py:63-75` replaces `sac.source_digest`
  for the duration of a save, which works only because `sac.py:226` calls the module-level name;
- the workbench keeps its own cached, threaded copy of the source digest (`runs.py:904-938`) and wraps
  `weight_digest` (`checkpoints.py:108`); `ngspice_backend.py:141` copies the Synthetic backend's connect/close
  pattern;
- the pinned examples write `env._done` (`benchmark_recording.py:104`, `benchmark_recording_overhead.py:111`);
- tests that read package privates and would need updating with the step: `test_graph_sac`, `test_native_preparation`,
  `test_parallel_corners`, `test_raw_format`, `test_recording_overhead`, `test_bridge_adapter`, `test_optimizer_round5`,
  `test_wb_learner_step`, `test_wb_schema_validation:162`, `test_wb_cdf_write:579`.

The 13 duplicated six-line windows of 1.5 (`cdf_write` ~ `native_preparation`, `ngspice_backend` ~
`synthetic_sizing`) would go in the same step: the workbench copies would then import the package's helpers.

## 7. Scripts and HEAD's measurements

`artifacts/local/reviews/refactoring-plan-2026-10-09/` (git-ignored evidence, kept by the user's backup rule) holds:

| File | What |
|---|---|
| `pystats.py` | long functions, in-function package imports, top-level import cycles, fan-in/out, duplicated six-line windows: `python -I pystats.py /mnt/d/gator src/gator_workbench src/analog_optimizer` |
| `cycles.py` | the workbench import graph with in-function imports as edges: every strongly connected component with the lazy and the top-level edges inside it, and the lazy edges that close no cycle: `python -I cycles.py /mnt/d/gator` |
| `ast_identity.py` | the move proof of 4.1: `python -I ast_identity.py <old>/src/gator_workbench <new>/src/gator_workbench`, exit 1 and the names whose bodies differ |
| `openapi_dump.py` | the route proof of 4.2: `GATOR_WORKBENCH_SETTINGS_DIR=<scratch> GATOR_AGENT_CLI_LAUNCH=off PYTHONPATH=src python openapi_dump.py > openapi.json`, then `sha256sum` against `openapi-4323753.json` |
| `metrics-4323753.txt`, `cycles-4323753.txt`, `openapi-4323753.json` | the three outputs at HEAD `4323753` |

The seeded MOCK differential run (4.3) and the DOM snapshot check (4.7) are written by the executing session on its
first package that needs them, and kept in the same folder. The scratchpad copies of the scripts die with the next
WSL restart; the folder above does not.

## 8. Decisions for the user

1. **Which groups** to execute, and in which order. Recommended: A, then B1, then B2-B5 one at a time, then C, then D.
2. **No digest step now** (section 6 waits until the encoder comparison and its save points are done).
3. **A3's shape:** split `register` in place (recommended, no behaviour surface touched) or convert to `APIRouter`
   per file (a later package if wanted).
4. **D's renames** of record-named test modules (D2): yes or no; and whether `tests/` gets `__init__.py` files so
   that one import root replaces the two spellings (D6).
5. **B10's lock hand-over** (`prepare_run` returning its lock instead of parking it in a module global): with B5, or
   not at all.
