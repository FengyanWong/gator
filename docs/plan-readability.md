# Readability plan: the same behaviour, code and documents a person can read

Date: 2026-10-25 (session "Readability plan for Codex"; user: "write a plan for codex to refactor the project for better
human readability", "also give the prompt"). **Plan only: nothing in the code was changed, nothing was built, and no run,
backend, Virtuoso, Spectre or agent CLI was touched.** Measured on HEAD `a82f950` (branch `workbench`, working tree clean;
only the live backend on 8765 was running). Optimizer source digest at HEAD:
`6ebf5ba532b279aa83b7b9b63d7e7c2573551691384575336bd24f91bc195da3` (it must read the same after every package).
The plan is written for Codex to execute; appendix A is the prompt to give it.

**State (2026-10-29, record 7.394):** carried out on `codex/latest` - D, T and P1 by Codex; P2-P7 by Claude with Codex's frozen proof kit (51 packages, one commit each), the P1 docstrings revised (P1R) and P8 (16 packages: wide parameter lists bundled into small named records); F by the frontend session (SIF-146..162, on the live `workbench` branch); E not chosen. Not landed or pushed.

## 0. In plain words

The 2026-10-09 refactoring (`docs/plan-refactoring.md`, records 7.290 and 7.292) gave the code a structure that is easier
to change: smaller files, one job each, imports at the top. This plan is the next layer: code and documents that a
**person** can read without running anything. "Readable" means five things here:

1. **A newcomer finds the right file from the documents.** Today the README is a pile of milestone paragraphs, half of
   them in Chinese, with no map of the repository; `docs/` has 63 files and no index; there is no glossary, so the page
   says "save point" while the code says `checkpoint`, and "task", "profile", "configuration" and "settings" each mean
   something precise that no document states in one place.
2. **Each file says what it is for in its first lines.** Every Python module already has a docstring (134 of 134 in the
   workbench). 48 of the 94 page files have no header comment, 14 test modules and 5 optimizer modules have none.
3. **Each function fits on a screen and is named for what it does.** 63 functions are 80 lines or longer (one is 309
   lines and nests ten deep); 78 nest five levels or deeper; 47 take eight or more parameters; 108 parameters have one-
   or two-letter names.
4. **The same thing has the same name everywhere**, and public things say what they do: 42% of the workbench's public
   functions and classes have no docstring (73% in the optimizer, 88% in the tests); `ckpt` appears 156 times for a
   checkpoint; `cfg`, `ctx`, `proc`, `tmp` stand in for words.
5. **A reader knows what goes in and comes out without running the code.** 8% of the workbench's function parameters
   and 31% of its return values carry a type; the optimizer has 7% and 8%.

**Nothing the page or a run does changes:** the same buttons with the same captions, the same messages byte for byte, the
same routes and status codes, the same files in a run folder with the same numbers in them, the same test names. Every
package is a *rewording of the code for people*, and it is proved by machines, not by reading (section 4): the function
bodies before and after compare equal as syntax trees once docstrings and type hints are stripped; the set of string
literals in each module is identical (so no message or field description changed); the optimizer digest is unchanged;
the test suite collects the same names and passes; routes, OpenAPI document and the page's DOM are byte-identical.

Why it is worth doing now: three branches are live (`workbench`, `self-improving-frontend`, `bo-mobo-rl`), several
sessions and Codex re-read the same code every day, and the thesis is being written from it. Each hour a reader spends
working out what `busy['op']` or `pa` means is spent again by the next reader. Documents first (group D: zero code risk,
biggest gain), then docstrings, then the long functions.

## 1. What was measured (HEAD `a82f950`, 2026-10-25)

Read-only scripts, nothing run against 8765, Virtuoso, Spectre or an agent CLI. Scripts and this output: section 7.

### 1.1 Size and the five measures, per tree

| Tree | Files | Lines | Functions >= 80 lines | Public defs without docstring | Module docstrings | Parameters / returns typed | Comment lines (% of code) | Lines > 120 chars |
|---|---|---|---|---|---|---|---|---|
| `src/gator_workbench` | 134 | 34,856 | 27 | 562 of 1,328 (42%): 105 classes, 27 functions of 25+ lines, the rest short | 134 / 134 | 8% / 31% | 1,060 (3.6%) | 1,811 |
| `src/analog_optimizer` | 79 | 11,367 | 11 | 363 of 496 (73%): 79 classes, 49 functions of 25+ lines | 74 / 79 | 7% / 8% | 209 (2.1%) | 156 |
| `tests` | 187 | 34,528 | 3 | 2,150 of 2,457 (88%; test functions have sentence names, so only helpers and fixtures count: 75 classes, 136 functions of 25+ lines) | 173 / 187 | 0% / 0% | 575 (2.0%) | 2,074 |
| `examples` | 46 | 6,579 | 22 | 172 of 191 (90%) | 46 / 46 | - | 34 (0.6%) | - |
| `frontend/src` (.ts/.tsx) | 94 | 14,355 | 15 top-level blocks > 140 lines | 48 files without a header comment | - | `any` casts: 42 | 2,806 | 1,741 > 140, 983 > 160 |

Other counts over the four Python trees: 78 functions nest five levels or deeper (10 in the workbench nest 7-10 deep);
47 functions take 8 or more parameters; 108 parameters have one- or two-letter names (`op` 13, `a` 13, `b` 13, `t` 8,
`p` 8, `at` 7, `ok` 6, `pa` 3, `pq` 3, `ic` 3 ...); in-function imports: workbench 318, optimizer 100, tests 370 (each
workbench one carries a reason, enforced by `test_every_import_of_a_workbench_module_inside_a_function_says_why`).
14 workbench modules have no `from __future__ import annotations`.

### 1.2 The long functions (every one of 80 lines or more, outside `examples/`)

Workbench (27): `ngspice_netlist.parse_text` 309 (nesting depth 10), `engine_commit.commit` 165, `pretrain._prepare_pool`
157, `ngspice_netlist.expand` 155, `connection.run_layers` 134, `api/circuit_routes._virtuoso_task_routes` 123,
`task_save.save_task` 120 (14 parameters), `engine_preparation.prepare` 115, `structures.recognize` 113 (depth 7),
`profile_generate.write_profile_files` 113, `pretrain.execute` 109, `cdf_rules.adjust` 109, `ngspice_link.run_layers` 106,
`runs.prepare_run` 104, `api/run_routes._run_list_and_model_routes` 104, `modes.build` 102 (14 parameters),
`graph_view.graph_view` 102, `pdk_record.build_record` 98, `validation._check_network_inputs` 91, `checkpoints.save` 91
(11 parameters), `schema._hashed` 87, `cdf_write.write_skill` 86, `summary.build_run_summary` 85,
`api/circuit_routes._task_routes` 84, `bridge_read._main` 82 (depth 7), `api/run_routes.start_run` 82,
`model_scan.classify_model` 80.

Optimizer (11, advice only - section 3, group E): `envs/sizing._run_conditions` 198 (depth 8),
`training/parallel.collect_parallel_episodes` 161 (depth 8, 17 parameters), `evaluation/benchmark.run_benchmark` 155 (13
parameters), `evaluation/benchmark.run_episode` 115 (14 parameters), `models/measurement_program.prepare_programs` 93,
`backends/virtuoso_bridge.run_simulation` 93, `netlist/spectre_parser._expand` 91, `backends/native_preparation._serve`
84, `evaluation/parallel.run_seeds` 83, `envs/sizing.CircuitSizingEnv.__init__` 82 (15 parameters),
`recording/store_summary._summary` 80.

Tests (3): `fixtures/reward_v21_preedit_specs.evaluate_conditions` 129 (a frozen fixture: untouched),
`test_wb_training_series_cache.test_replaced_cut_or_remade_logs_are_read_again` 81,
`test_wb_session_routing.test_start_records_the_chosen_session_and_lets_it_go_when_the_start_is_refused` 80 (tests stay).

Deepest nesting in the workbench besides `parse_text`: `calibration._propose_scale` 8, `spec_descriptors.probe_facts` 8,
`model_library.parse_structure` 8, `structures.recognize` 7, `bridge_read._main` 7, `ngspice_backend.run_simulation` 7,
`validation._check_measurements` 7, `aggregates.export_table_csv` 7, `ngspice_syntax.tokenize` 7,
`paths.directory_bytes` 7.

A concrete example of what the reader meets: `engine_commit.commit` receives an `Outcome` (a NamedTuple with twelve
named fields) and at once unpacks it into twelve local names
(`(status, raw_metrics, raw_validity, raw_units, derived, ...) = outcome`), then reads a dict of lane state by string
keys (`busy['op']`, `busy['phase']`, `busy['previous']`) for 160 lines. The same function with `outcome.feasible` and a
few named steps (`_admit_to_replay`, `_first_feasibility_rows`, `_evaluation_row`) is the same behaviour and half the
reading.

### 1.3 Names and words

- `ckpt` 49 times in the workbench, 107 in the tests; `cfg` 10 / 25 / 68 (workbench / optimizer / tests); `ctx` 6,
  `proc` 8, `tmp` 3. The page says **save point**; the code, the tables and the records say **checkpoint**.
- The workbench uses `task` 1,062 times, `record` 913, `config` 751, `profile` 449, `settings` 317: a saved task
  (`real:<name>`) has a profile (its circuit on the real backend), a configuration (the editors' rows, `WorkbenchConfig`)
  and settings (the remembered values in the settings folder, and the connection's settings). Every one of these is
  precise and none is defined for a reader in one place. The refactoring's B9 (`names.py`) gathered shared constants,
  not words.
- One- and two-letter parameters live mostly in private helpers and lambdas (`op`, `a`, `b`, `t`, `p`, `at`, `pa`, `pq`,
  `ic`, `fd`); on the page, `Editors.tsx` names rows `r`, sections `s`, the saved row `w`, the model `m`.

### 1.4 Documents

- `README.md` (137 lines): five English paragraphs (M6 closure, encoders, the workbench, install), then fourteen Chinese
  paragraphs of milestone history (lines 21-48: M1-M6 acceptance numbers, each paragraph one increment) and four Chinese
  reference sections (lines 49-137: install and run, folders and interfaces, the supported Spectre subset, graph /
  parameter groups / PyG - written for the optimizer package before the workbench existed). No map of the repository,
  no "where do I look for X". The user asked for English on 2026-09-19.
- `docs/`: 63 documents and 33 log files, no index. The reader cannot tell which are living (kept current in place:
  `workbench.md`, `functionality-reference.md`, `decisions.md`), which are plans (21 `plan-*.md`, each with a State
  line), which are frozen evidence of a milestone (`m4-*`, `m5-*`, `m6-*`, `opamp-*`, `recording-*`), and which are
  briefs for a reviewer.
- `docs/workbench.md`: 145 kB, 14 sections, read by heading map (`grep -n '^##'`); no table of contents inside the file.
- No glossary. `CLAUDE.md` and `functionality-reference.md` are good maps of *where*, not of *what the words mean*.
- `.agents/skills/analog-optimizer/SKILL.md` (Codex's skill) is in Chinese with English identifiers.
- `examples/`: 46 scripts, no README; several are hash-pinned evidence and must never be edited (CLAUDE.md), which a
  reader cannot see from the folder.
- Page: 46 of 94 source files open with a one- or two-line header saying what the file is (the ones the 2026-10-09
  refactoring created or moved); 48 do not (`App.tsx`, `store.ts`, `Connection.tsx`, `Editors.tsx`, `Left.tsx`, ...).
  The 74 browser checks in `frontend/scripts/` share a harness with a long header; the per-check headers vary.

### 1.5 What is already good, and stays

Module docstrings in the workbench are sentences that say what the module is for and which record built it (section 1
of every file). Test names are sentences. Long comments explain *why* where it matters (the settings-folder trap in
`tests/workbench/helpers.py`, the retired fields in `schema.py`). Public API names, route paths, JSON keys and table
columns are stable and documented in `functionality-reference.md`. None of this is touched.

## 2. Rules every package follows

1. **Behaviour identical, proved.** No message, caption, `Field(description=...)`, route path, status code, JSON key,
   table column, file name, environment variable or public name changes. Proofs of section 4 run before each commit;
   a package that fails one is not committed. The three module docstrings that argparse prints as help stay byte for
   byte (`gator_workbench/cli.py`, `gator_workbench/worker.py`, `analog_optimizer/demo.py`: `description=__doc__`).
2. **`src/analog_optimizer/` is not edited** (digest `6ebf5ba5...` gates every saved model and audit, CLAUDE.md). Group E
   lists what would be done there and runs only on the user's explicit "include E" (section 6, decision 3).
3. **Pinned evidence is not edited:** `examples/*.py`, `configs/*.json`, `tests/fixtures/synthetic/*.scs`,
   `tests/fixtures/*.py`. A *new* file beside them (`examples/README.md`) is allowed: the audits hash named files.
4. **History is not rewritten:** `docs/workbench-log/*` (except the new entry appended to the open file),
   `record-history.md`, `decisions.md` below its "Current state", `thesis/`, `thesis-phd/`, `frontend/dist/`.
5. **The second foundry's PDK is never named** in a tracked file (foundry, technology library, model file, callback
   names; a file NAME counts). The words to grep for are not written here on purpose: `ls configs/local/workbench/pdks/`
   (git-ignored, this machine only) gives the library name, and the user gives the rest. Before each commit:
   `git diff --name-only <base> | xargs grep -il <each word>` lists nothing.
6. **Docstrings** are one sentence (two at most) in the project's plain words, saying what the thing is or does and
   what the caller gets - not how, not the signature again, no "This function ...". English. A docstring that would
   only repeat the name is not written. Adding a docstring changes the syntax tree by one `Expr` node and nothing else
   (proof 4.1 strips them).
7. **Type hints** go on function parameters and return values only, never on class bodies (a dataclass or pydantic
   field is created by its annotation), never on FastAPI route handlers (FastAPI reads them to parse the request), and
   only where the type is **true** - `Any`, a guess or a union written to make a checker quiet is not a hint and is
   left out. A module gets `from __future__ import annotations` first when it lacks it (14 workbench modules), unless
   it defines a pydantic model or dataclass whose field types are not importable at module level - then the module is
   skipped. A hint that needs a new import adds it under `if TYPE_CHECKING:` only when a top-level import would create
   a cycle (`test_no_import_cycle_beyond_the_known_ones`).
8. **Renames are private only:** locals, parameters of private functions, private module names (`_x`). Public functions,
   methods, module names, keyword parameters of public functions, route paths, JSON keys, table columns, CSS classes,
   `data-*` attributes, browser-check names and test names stay. Before renaming anything, `grep -rn` the old name over
   `src`, `tests`, `frontend`, `docs`, `examples`; `test_every_name_a_test_patches_exists_where_it_is_patched` guards
   the patched ones. A public parameter is renamed only when every call in the repository is positional.
9. **Splitting a long function** extracts named steps into private functions of the same module, each with a verb name
   and a docstring; a step takes what it reads and returns what it writes; the caller's body then reads as the list of
   steps. The order of every side effect (file writes, counters, lock acquisition, logging) is unchanged; no early
   return moves a side effect. Proof: `inline_proof.py` (the step inlined back equals the original tree), 4.4-4.6.
10. **Formatting (line wrapping) only inside files the package already edits.** No repository-wide reformat, no
    formatter added to `~/analog-optimizer-venv` (it must stay as it is), no `ruff --fix`. Width 120 as the code uses.
11. **In-function imports stay** where the structure tests want them and keep their "why" comment; hoisting is not
    this plan's job (7.290 did it).
12. **Page:** behaviour is preserved by extracting *hooks* (called unconditionally, same order) and *render helpers*
    (plain functions returning JSX, called inline) - not new component boundaries around stateful subtrees, which reset
    state on re-render. `styles.css` and `roadster.css` get comments only (the cascade-order proof of C11 is not
    repeated). `dom_identity_check.mjs --compare` must be byte-identical.
13. **Tests:** names, IDs, fixture names and `xdist_group` marks unchanged (records and `-k` commands cite them); autouse
    fixtures stay where they are (7.290's lesson).
14. **One package = one commit** on the `readability` branch of a worktree on the Linux file system (section 5); the
    commit message names the package and pastes the proof results. Nothing lands in `/mnt/d/gator` while a run is in
    flight; no push; no 8765 restart; no `npm run build` into the live `dist/` - each only on the user's word.
15. **Scratch scripts** that import `gator_workbench` set `GATOR_WORKBENCH_SETTINGS_DIR` to a temporary folder first
    (`tests/workbench/helpers.py` does; a bare script rewrites the user's live settings). Proof imports never run with
    `python -I` (the venv's editable install would then import the live tree instead of the worktree).

## 3. Work packages

Sizes are what the measurement found; each package is one commit unless it says "one per file/function".

### Group D: documents (no code, zero behaviour risk, the biggest gain for a newcomer) - first

- **D1 README in English and in order.** Sections: what GATOR is (three sentences), start (the five commands), a map of
  the repository (one line per top-level folder and per package, pointing at `docs/README.md`, `workbench.md`,
  `functionality-reference.md`, `decisions.md`), the current state (the "Current state" of `decisions.md`, one
  paragraph), and a pointer to the history. The fourteen Chinese milestone paragraphs move **unchanged** into
  `docs/history-readme-milestones.md` under a line that says where they came from; above them a one-line-per-milestone
  English table whose numbers are copied, not retyped (decision 1 says whether they are also translated). The four
  Chinese reference sections (install and run, folders and interfaces, the supported Spectre subset, graph / parameter
  groups / PyG): each statement is checked against HEAD; what is still true is written in English into the README's map
  (install) or into `docs/optimizer-package.md` (folders, parser dialect, graph contract - one page, the optimizer's
  counterpart of `workbench.md`); what is no longer true moves unchanged to the history page with its date. Every link
  in the old README keeps working (same targets).
- **D2 `docs/README.md`: the index.** One row per document and log file: name, one line of what it holds, kind (living
  / plan / evidence of milestone N / brief / record), and whether it is kept current or frozen. Grouped by kind. Plans
  show their State line's first words.
- **D3 `docs/glossary.md`.** One row per word: the word on the page | in the code | in the records | one sentence of
  meaning | where it is defined. At least: task, saved task (`real:<name>`, `ngspice:<name>`), profile, configuration
  (`WorkbenchConfig`), settings (settings folder, connection settings), run, launch, evaluation, design, candidate,
  proposal, episode, step, lane / worker, save point = checkpoint, Baseline, calibration, Check now, working copy, cell,
  Maestro setup, Parameters / Probes / Specs, hard and soft spec, MOCK vs real vs synthetic, output root, run folder,
  experiment, model (saved RL model) vs network vs encoder, PDK and "a second foundry's 0.18 um PDK" (how it is to be
  written), bridge, session (Virtuoso session), record / entry / index. `CLAUDE.md` step 1 and the "Code organization"
  section of `workbench.md` point at it.
- **D4 `docs/workbench.md` table of contents** under the title: each `##` section with one line of what it holds and
  the records it came from. The file is not split: CLAUDE.md's `grep -n '^##'` workflow and hundreds of references
  depend on it.
- **D5 `examples/README.md` (new file).** The 46 scripts in groups (training, benchmarks, audits, baselines, reward
  qualification, imports), one line each, and the list of the ones the M5/M6 audits hash (from
  `benchmark_real_topology.py:79-84`, `cross_category.py:48-57`, `real_category.build_plan`) marked "pinned: never edit".
- **D6 Browser checks:** every `frontend/scripts/*_check.mjs` without a header gets one or two lines: what it checks,
  which window, hermetic or writing, which record built it. `run_checks.mjs`'s list gets the same one line per check.
- **D7 `docs/functionality-reference.md`:** a row for the glossary in section 10 and this plan's row in section 9;
  structure unchanged.
- **D8 (decision 2)** `.agents/skills/analog-optimizer/SKILL.md` and its `references/` in English, identifiers kept.

### Group T: tests (documents of a kind; no test changes)

- **T1** Module docstrings for the 14 modules without one (`tests/conftest.py`, `tests/workbench/conftest.py`,
  `test_ac_measurements`, `test_actions`, `test_backend`, `test_conditions`, `test_corner_summary`, `test_groups`,
  `test_parser`, `test_pyg`, `test_real_export`, `test_specs`, `test_spectre_validation`,
  `test_llm_operating_points`): what the module covers and what it never touches (simulator, network, settings).
- **T2** One-line docstrings on every helper, fake and fixture in `tests/workbench/helpers.py`, `fakes_virtuoso.py`,
  `tests/research_support.py` and the per-module helpers (75 public classes, 136 functions of 25+ lines, 0% typed):
  what the fake pretends to be and which real thing it stands in for.
- **T3** Section comments (`# ---- what this group of tests covers`) in the modules of 300+ lines with no comment line
  (`test_runtime_recovery`, `test_transfer`, `test_wb_model_library`, `test_recording`, `test_native_preparation`,
  `test_wb_dataset_streaming`, `test_wb_package_inventory`), the way `test_wb_engine.py` already does it.
- Test function docstrings are **not** added: the names are the sentences. In-function imports in tests stay.

### Group P: the Python workbench (behaviour-preserving, proved per module)

- **P1 Docstrings** for the 562 public definitions without one: 105 classes first (a class docstring says what one
  instance *is*), then the 27 public functions of 25+ lines, then the short ones where the name does not already say
  it. One commit per module or group of small modules. Proof 4.1 (docstrings stripped), 4.2, 4.4.
- **P2 The 27 long functions**, one commit each, longest first: `ngspice_netlist.parse_text` (309 lines, depth 10:
  one step per statement kind - element, subcircuit, control, parameter line - and a small `_ParseState` for what the
  loop carries), `engine_commit.commit` (`Outcome` attributes instead of the twelve-name unpacking; steps
  `_admit_to_replay`, `_first_feasibility_rows`, `_evaluation_row`, `_retention`), `pretrain._prepare_pool`,
  `ngspice_netlist.expand`, `connection.run_layers` and `ngspice_link.run_layers` (one private function per layer),
  the two route-group functions in `circuit_routes` / `run_routes` (one private function per route, the `register`
  call list unchanged - the routes' order in the OpenAPI document must not move), `task_save.save_task` (its 14
  parameters as a `SaveRequest` NamedTuple built by the one caller, if every call site is in the repository),
  `engine_preparation.prepare`, `structures.recognize`, `profile_generate.write_profile_files`, `pretrain.execute`,
  `cdf_rules.adjust`, `runs.prepare_run`, `modes.build`, `graph_view.graph_view`, `pdk_record.build_record`,
  `validation._check_network_inputs`, `checkpoints.save`, `schema._hashed` (**careful: this is the identity hash of every
  run, task file and approval - its byte output is proved by 4.6 and by hashing the test fixtures before and after**),
  `cdf_write.write_skill`, `summary.build_run_summary`, `bridge_read._main`, `run_routes.start_run`,
  `model_scan.classify_model`. Proofs 4.1 (inline), 4.2, 4.4, 4.5 for the route modules, 4.6 for everything the run
  engine imports.
- **P3 Deep nesting** in the ten functions of depth 7+ that P2 does not already flatten (`calibration._propose_scale`,
  `spec_descriptors.probe_facts`, `model_library.parse_structure`, `ngspice_backend.run_simulation`,
  `validation._check_measurements`, `aggregates.export_table_csv`, `ngspice_syntax.tokenize`, `paths.directory_bytes`):
  guard clauses and extracted predicates, never a change in the order of side effects. Same proofs as P2.
- **P4 Names:** `ckpt` -> `checkpoint` (49), `cfg` -> `config`, `ctx` -> `context`, `proc` -> `process`, `tmp` -> what it
  holds, in locals and private parameters; the one- and two-letter parameters of private functions and lambdas
  (`op`, `a`, `b`, `t`, `p`, `at`, `pa`, `pq`, `ic`, `fd`) -> words, except the conventional `i`, `n`, `x`, `y` in
  arithmetic and the `a`/`b` of a comparison helper. Rule 8 for anything public. One commit per module. Proof 4.1
  with a rename map (`rename_ids.py` of 7.290 does the alpha-renaming check), 4.2, 4.4.
- **P5 Type hints on signatures**, leaf modules first (`storage/`, `names.py`, `units.py`, `paths.py`, `run_lock.py`,
  `task_names.py`, `task_folders.py`, `security.py`, `budget.py`, `layout.py`, `families.py`, `vocabulary.py`,
  `checkpoint_codec.py`, `psf_binary.py`, `ngspice_syntax.py`), then whatever P2 touched. Rule 7. Proof 4.1 (hints
  stripped), 4.4, and the import-cycle structure test. A `mypy` run in a **throwaway** venv is a reader's aid, not a gate
  and not installed in the project venv.
- **P6 Comments:** a `# ---- step` marker before each step of a function that stays over 40 lines; a "why" comment on
  every non-obvious branch (the code already does this well where it does it at all); a literal that appears three or
  more times with the same meaning in one module becomes a named constant at the module top (same value, same type;
  proof: 4.2's number multiset counts the constant's definition, so the reviewer checks each by hand). No comment
  that says what the next line says.
- **P7 Line wrapping** to 120 columns in files P1-P6 already edit (1,811 lines over 120 today). Proof 4.1. Repository-wide
  is decision 4.
- **P8 (optional, last)** The private functions with 8+ parameters (`engine_rows._candidate` 11,
  `engine_rows._metric_rows` 10, ...) take a small NamedTuple built by their one caller. Public ones (`modes.build` 14,
  `checkpoints.save` 11, `task_files.build` 12, `network_inputs.NetworkInputs.__init__` 12, `bayes.*.__init__` 12,
  `ngspice_backend.*.__init__` 10) stay: their keywords are the interface.

### Group F: the page (TypeScript)

- **F1 Header comments** on the 48 files without one: what the file is, which window or panel, which record built it
  (the style of `requests.ts`, `shared.ts`, `OutputPanel.tsx`). One commit.
- **F2 The long components** -> hooks and render helpers inside the same file (rule 12): `Connection.tsx`
  `ConnectionButton` 390 lines, `useRlModel.ts` 332, `TrainingTab.tsx` `TrainingTabBody` 320, `App.tsx` `Page` 246
  (the file holds 17 `useState`), `TaskSave.tsx` `TaskSave` 243, `RunList.tsx` `RunListButtonBody` 226, `RlModelWindow.tsx` 206,
  `TrainingChart.tsx` 198, `circuitLayout.ts` `hintedLayout` 196 (pure: steps as functions), `training/store.ts`
  `TrainingStore` 192, `CircuitGraphView.tsx` 178, `TaskList.tsx` 169, `VirtuosoWindow.tsx` 162, `RunTabs.tsx`
  `StatusTab` 157, `training/prep.ts` `Prep` 144. One commit per file. Proofs 4.7.
- **F3** The 42 `any` casts -> the real type where it is known (`Json` is already the project's word for untyped JSON);
  `tsc` proves it. **F4** Single-letter locals in `Editors.tsx` (1,065 lines, 15 `useState`) and the other long files:
  `r` -> `row`, `s` -> `section`, `w` -> `savedRow`, `m` -> `model`, inside the function only. **F5** Line wrapping
  (983 lines over 160 columns) in files F1-F4 edit. **F6** `styles.css` / `roadster.css`: a comment per block saying
  which panel it styles; no rule moves (the Roadster look's CSS traps, record 7.360).
- Timing: `Editors.tsx` and the panels are the `self-improving-frontend` branch's daily files (SIF-131 touched the
  Parameters table on 2026-10-24). Decision 5 says who does F and when.

### Group E: the optimizer package - advice only, for a digest step the user may choose

If the user says "include E" (one digest change, recorded in `docs/decisions.md` with the old and new digest, as 7.292
did): module docstrings for `backends/backend.py`, `envs/sizing.py`, `netlist/config.py`, `parameters/actions.py`,
`recording/__main__.py`; docstrings on the 79 classes and 49 functions without one; the 11 long functions of 1.2
(`_run_conditions` 198 lines first, `collect_parallel_episodes` with its 17 parameters as a NamedTuple only if every
caller is in the repository - `examples/` callers are pinned and cannot be edited, so check them first); type hints on
signatures (7% today). Rules 1, 6-10 and proofs 4.1-4.6 apply; `source_digest()` is recomputed and written into the
record and `decisions.md`. **Cost:** every saved model and audit loads only from the source commit before the change
(`fine_tune` / `frozen` still load; `resume` needs the old tree), the live backend serves the new digest after its
restart, and the next command-line run writes it. The Round 3 and archive-comparison runs use frozen runtime copies
(`~/gator/runtimes/`, `~/gator/worktrees/bo-mobo-rl`) and are unaffected. **Default: not now** (decision 3).

## 4. Proofs, the same for every package

Tools: the 2026-10-09 kits in `~/gator/work-logs/gator-refactor/tools/` (`ast_identity.py`, `openapi_dump.py`,
`routes_dump.py`, `diffrun.sh` + `diffrun.py`, `diffvalidate.sh`, `diffhttp.sh`, `diffcalib.sh`, `pystats.py`,
`rename_ids.py`) and `~/gator/work-logs/gator-followup/tools/` (`inline_proof.py`, `extract_step.py`, `rewrap.py`,
`import_surface.py`, `land2.py`, `wincopy.sh`); their gotchas are in record 7.290 and 7.292 (pass ABSOLUTE output paths to
the `diff*.sh` scripts and delete old outputs first; `inline_proof` is class-aware and checks definite assignment).
Two small new scripts are this plan's (Codex writes them at the start, in section 7's folder):

- **4.1 Normalized AST identity** (`ast_normalized.py BEFORE AFTER`): parse both files; drop every docstring `Expr`;
  set every `annotation` and `returns` to `None`; drop `from __future__ import annotations` and `if TYPE_CHECKING:`
  blocks; apply the package's rename map (old -> new) to `Name`, `arg` and `Attribute.attr` of private names; compare
  `ast.dump(tree, include_attributes=False)`. Equal, or the package is not a rewording. For extracted steps, run
  `inline_proof.py` first (inlines the steps back), then this.
- **4.2 String and number identity** (`literals_identity.py BEFORE AFTER`): the multiset of `str`, `bytes`, `int` and
  `float` constants per module with docstrings removed must be identical. This is the machine proof that no message,
  caption, field description, route path, key, column or default changed. A named constant (P6) is the one allowed
  difference, listed in the commit message.
- **4.3 Optimizer digest unchanged:** `PYTHONPATH=<worktree>/src ~/analog-optimizer-venv/bin/python -c "import
  analog_optimizer, sys; print(analog_optimizer.__file__); from analog_optimizer.training.sac import source_digest;
  print(source_digest())"` prints the worktree's path and `6ebf5ba5...` before and after every package (never `-I`).
- **4.4 Tests:** `pytest --collect-only -q` lists the same IDs before and after (diff empty); the full suite passes in the
  worktree: `OMP_NUM_THREADS=1 PYTHONPATH=<worktree>/src ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist
  loadgroup` (`-n 4` while a peer measures or simulates; 2,752 passed, 1 skipped on 2026-10-23); the structure tests
  (`tests/workbench/test_wb_structure.py`) pass.
- **4.5 Routes and OpenAPI byte identity** (`openapi_dump.py`, `routes_dump.py`) for every package touching `api/`.
- **4.6 Seeded MOCK differential run** (`diffrun.sh`) for every package touching `engine*`, `runs`, `lanes`, `modes`,
  `pretrain`, `checkpoints`, `schema`, `validation`, `compile`, `summary`, `storage/`: the run folders' tables, summary
  and save points byte-identical (save-point zips compared entry by entry); `diffvalidate.sh` and `diffcalib.sh` for
  `validation` / `calibration`.
- **4.7 Page:** `npx tsc --noEmit`; `dom_identity_check.mjs` reference taken from the branch base once, then
  `--build <worktree build> --compare` byte-identical per package; `run_checks.sh` against a scratch backend
  (`GATOR_WORKBENCH_URL` + `WSLENV`, `--lanes 2` while a peer runs); per-script pass counts equal to the base's.
- **4.8 Scope and words:** `git diff --name-only <base>` shows only paths the package allows (rules 2-4); the PDK grep of
  rule 5 lists nothing; the reversal grep of 7.290 after landing (no committed line missing from the live tree).
- **4.9 Metrics:** section 7's scripts re-run after each group; the before/after table goes into the record entry.

## 5. Order, worktree and landing

1. **Worktree on the Linux file system**, branched from `workbench`:
   `git -C /mnt/d/gator worktree add ~/gator/worktrees/readability -b readability workbench`. Edit there only. The
   venv's editable install points at `/mnt/d/gator/src`: every command sets `PYTHONPATH=<worktree>/src`, and 4.3 checks
   `analog_optimizer.__file__`. For the page, `wincopy.sh` (junctioned `node_modules`, Windows node) is the worked way;
   `npm run build` in the worktree writes the worktree's `dist/`, never the live one.
2. **Order:** D1-D7 (one commit each; D8 on decision 2), T1-T3, P1 module by module, F1, P2 then P3 one function per
   commit, P4, P5, P6, F2-F4, then P7/F5 in the touched files only; P8 and E only if chosen.
3. **Rebase** `readability` onto `workbench` before each landing (peers commit daily; the SIF branch merges into
   `workbench` as well).
4. **Landing into `/mnt/d/gator`** only on the user's "land", only between runs: `pgrep -af 'gator_workbench.worker|gator_workbench.cli run'`
   empty and no queue script running (a live process reads modules from disk when it first imports them - plan-refactoring
   section 5). The live tree holds peers' uncommitted edits: land as 7.292 did (`land2.py`: compare-and-swap fast-forward,
   peers' uncommitted files kept on top), then run the suite and the browser checks in the live tree, then the record
   follow-up. Commit from explicit paths or a private index (`CLAUDE.md`), never `git add -A`; `git show --stat HEAD`
   before any push, and push only on the user's word.
5. **After landing:** 8765 restart and the page build only on the user's word (the page's `dist/` is what the live backend
   serves; F packages change the bundle, D/T/P do not).
6. **The record:** one entry at the end of the open log (CLAUDE.md names it; today `docs/workbench-log/7.389-and-later.md`)
   with the before/after metrics, the proofs' results and what was left out; its row in
   `docs/frontend_implementation_status.md`; this plan's State line and its row in `functionality-reference.md` section 9;
   `CLAUDE.md` step 1 points at the glossary. The entry number is computed **at write time** (other sessions append
   too); the open log rolls over at 60 kB.

## 6. Decisions for the user

1. **README history (D1):** move the fourteen Chinese milestone paragraphs unchanged with an English table above them
   (recommended: nothing can be mistranslated), or translate them as well.
2. **Codex's skill (D8):** translate `SKILL.md` and `references/` to English (recommended, after D1-D7), or leave them.
3. **Group E (the optimizer, one digest change):** not now (recommended: the CircuitGPS v3 digest `6ebf5ba5...` is the
   one the Round 3 results and the archive comparison were run under), or "include E".
4. **Line wrapping repository-wide** (1,811 + 2,074 Python lines, 983 page lines): no (recommended: it turns every
   peer's pending diff into a conflict), or yes, as the last package of all.
5. **Group F and the `self-improving-frontend` branch:** F after that branch's SIF-104..110 land, done by its session or
   coordinated with it (recommended), or now on `readability`.
6. **Type hints (P5) breadth:** leaf modules plus what P2 touches (recommended), or the whole workbench.
7. **Words:** code keeps `checkpoint`, the page keeps "save point", the glossary maps them (recommended); or one rename
   across code, tables and page (not behaviour-preserving in the tables: ruled out by this plan).

## 7. Scripts and HEAD's measurements

`artifacts/local/reviews/readability-plan-2026-10-25/` (not in git): `pymetrics.py` (sizes, long functions, nesting,
parameters, docstrings, module docstrings, in-function imports, comment ratio), `pymetrics2.py` (type hints,
abbreviations, vocabulary counts, module one-liners), `femetrics.py` (page files: header comments, `useState`,
`useEffect`, `any`, longest top-level block), `longlist.py` (every function of 80+ lines), and
`metrics-a82f950.txt`, their output at HEAD. Re-run: `cd /mnt/d/gator && ~/analog-optimizer-venv/bin/python -I
<folder>/pymetrics.py src/gator_workbench src/analog_optimizer tests examples` (these scripts import only the standard
library, so `-I` is right here; it is wrong for anything that imports the package, rule 15).

## Appendix A: the prompt for Codex

Paste as the first message of a Codex session opened on `/mnt/d/gator` (its `.agents/skills/analog-optimizer` skill may
load by itself; this prompt and `CLAUDE.md` take precedence over the skill's scope rules).

```text
You are working in the GATOR repository at /mnt/d/gator (branch `workbench`): a research workbench for analog circuit
sizing - Python backend in src/gator_workbench, React/TypeScript page in frontend/src, tests in tests/, a protected
optimizer package in src/analog_optimizer. Your task is to EXECUTE docs/plan-readability.md: a refactoring for human
readability whose one rule is that nothing the code does changes.

Read first, in this order: CLAUDE.md; docs/plan-readability.md in full (sections 2 Rules, 3 Work packages, 4 Proofs,
5 Order and landing, 6 Decisions); docs/plan-refactoring.md sections 4 and 5 (the 2026-10-09 refactoring this plan
follows) and its records 7.290 and 7.292 (docs/workbench-log/7.279-7.290.md, 7.291-7.300.md: the worked examples and
the traps met); docs/functionality-reference.md section 9.

Hard rules (details in the plan's section 2):
1. Behaviour identical and PROVED. No message, caption, Field description, route, status code, JSON key, table column,
   file name or public name changes. Every package passes the plan's section 4 proofs before it is committed; a package
   that fails a proof is not committed and not "fixed" by hand around the failure.
2. Never edit src/analog_optimizer/ (its source digest 6ebf5ba532b279aa83b7b9b63d7e7c2573551691384575336bd24f91bc195da3
   gates every saved model and audit; check it before and after each package), examples/*.py, configs/,
   tests/fixtures/, docs/workbench-log/ (except appending the one record entry), thesis/, thesis-phd/, frontend/dist/.
   Group E runs only if the user writes "include E".
3. Never write the second foundry's name, technology library, model file or callback names into any tracked file
   (write "a second foundry's 0.18 um PDK"). The words are deliberately not in the plan: `ls configs/local/workbench/pdks/`
   (git-ignored) gives the library name; ask the user for the others once. Before each commit:
   `git diff --name-only <base> | xargs grep -il <each word>` must print nothing.
4. Work in a git worktree on the Linux file system, never in /mnt/d/gator directly:
   `git -C /mnt/d/gator worktree add ~/gator/worktrees/readability -b readability workbench`. Every Python command
   sets PYTHONPATH=<worktree>/src (the venv's editable install points at the live tree). Never run proof or test
   imports with `python -I`. Land into /mnt/d/gator only when the user says "land", only between runs, as the plan's
   section 5 says; never `git add -A`, never push, never restart the backend on 8765, never `npm run build` in the live
   tree - each only on the user's word.
5. One work package = one commit on `readability`. The commit message names the package (D1, P2 parse_text, ...) and
   pastes the proof results: normalized AST identity, literal identity, digest unchanged, collected test IDs unchanged
   and the pass count, OpenAPI hash where api/ changed, DOM identity where the page changed.
6. Tests: `OMP_NUM_THREADS=1 PYTHONPATH=<worktree>/src ~/analog-optimizer-venv/bin/python -m pytest -q -n 12 --dist loadgroup`;
   use `-n 4` while another session measures or simulates (look at the load and `pgrep -af gator_workbench` first).
   A scratch script that imports gator_workbench sets GATOR_WORKBENCH_SETTINGS_DIR to a temporary folder first.
7. Test names, test IDs, fixture names and xdist_group marks are unchanged. Public names, keyword parameters of public
   functions, routes, keys, columns, CSS classes and data-* attributes are unchanged; renames are private names and
   locals only, after a grep over src, tests, frontend, docs and examples.
8. English, plain words, the project's vocabulary (docs/glossary.md once D3 exists). A docstring is one sentence that
   says what the thing is or does, never how and never the signature again. A type hint is written only where it is
   true; never on class bodies or FastAPI route handlers. Nothing is reformatted outside the files a package edits.

Order: group D (documents) in full, then T1-T3, then P1 module by module, then F1, then P2 and P3 one function per
commit, then P4, P5, P6, then F2-F4, then P7/F5 only in files already touched. P8 and E only if the user chooses them.
Start by writing the two proof scripts of section 4 (ast_normalized.py, literals_identity.py) into
artifacts/local/reviews/readability-plan-2026-10-25/ and self-testing each on a file you edit both ways (a docstring
added: equal; a message reworded: unequal).

After each group: re-run the metric scripts of section 7, keep the before/after numbers for the record, and report to
the user in a few plain lines: what is on the branch, the proof results, what comes next, and any decision of section 6
you need (ask with the recommended option first). Stop and ask when a proof fails and the cause is not plainly your
edit, when a rename would touch a public name, when a package needs a file outside the allowed trees, when the base
branch moved under you in a file you edit, and when landing is due.

Record, when the chosen groups are done: one entry at the end of the open log (CLAUDE.md names the file; compute the
next 7.N at write time from the open log's headings and the index's rows, since other sessions append too), its row in
docs/frontend_implementation_status.md, the plan's State line, and its row in docs/functionality-reference.md section 9;
CLAUDE.md step 1 gets one sentence pointing at docs/glossary.md. Commit those in the worktree; nothing in the live tree
is committed or pushed unless the user asks.
```
