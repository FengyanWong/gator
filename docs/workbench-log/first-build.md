# Workbench development record: the first build (2026-09-20)

Sections 1-6 and the first three next steps, written for the first build (commit `bcf7c5e`, 2026-09-20 ~17:44) and
never rewritten since: the entries in the other files of this folder say what changed. Moved here unchanged from `docs/frontend_implementation_status.md` on 2026-09-22 (entry 7.64); that file is now the index of
this record. Entries are append-only: a later entry supersedes an earlier one without editing it.

## 1. Inspection facts (verified 2026-09-20, not assumed)

| Item | Finding |
|---|---|
| `CLAUDE.md`, `AGENTS.md`, `PROJECT_SPEC.md`, `.claude/` | **Missing** at session start. Nothing fabricated. A concise `CLAUDE.md` was added by this work. |
| Project rules that do exist | `.agents/skills/analog-optimizer/SKILL.md` + `references/*.md` (Codex/agents convention, has `agents/openai.yaml`), `docs/decisions.md`, `README.md`. Read and followed. |
| Git | Branch `m6-cross-category`. **Owned by the user / the parallel session and never touched here:** `docs/m6-vco-requalification.md`, `examples/requalify_vco_designs.py`, `examples/vco_requalification.py` (moved there from `src/analog_optimizer/evaluation/` by that session at ~16:50), `tests/test_vco_requalification.py`, its uncommitted edits to `README.md`, `docs/decisions.md`, `docs/m6-cross-category.md`, and the specification file. |
| Existing web stack | None. Chosen per spec: React + TypeScript + Vite, FastAPI backend. |
| Python env | `/tmp/analog-optimizer-venv` (Python 3.10.12, torch 2.14.0+cpu, torch-geometric 2.8.0.post1, pyarrow 23.0.1, pytest 9.1.1). No system pip. `/tmp` venvs can be cleaned by the OS. |
| Node | No native Linux `node`. Windows `node.exe` v24.21.0 / npm 11.19.0 reachable through WSL interop at `/mnt/c/Program Files/nodejs/`. |
| Bridge package | Genuine `Arcadia-1/virtuoso-bridge-lite` checkout at `~/virtuoso-bridge-lite`, package `virtuoso-bridge` **0.8.0** (matches the pin in `backends/virtuoso_bridge.py`). Installed only in `~/virtuoso-bridge-lite/.venv`; **not importable** from the project venv or system Python. |
| Bridge API confirmed from local source | `VirtuosoClient.from_env`, `.library.list()/.get()`, `.schematic.read()/.export_netlist()/.create()/.modify()/.edit()/.plan()/.create_from_plan()/.import_netlist()`, `.maestro.*`, `.list_windows()`, `SpectreSimulator.from_env`, `SSHClient.is_running`. No methods invented. |
| Bridge skills (actual names and source) | `virtuoso`, `spectre`, `netlist`, `optimizer` at `~/virtuoso-bridge-lite/skills/<name>/SKILL.md`. |
| Bridge skill visible to Claude Code? | **No.** `~/.claude/skills/` and `~/.claude/plugins/` do not exist, the project has no `.claude/skills/`, and the development session's loaded skill list contains no Virtuoso skill. A skill present for Codex / inside another repo is not evidence of Claude visibility. No fake `/virtuoso-bridge` command was created. See section 6 for a non-destructive install proposal. |
| `claude` / `codex` CLI | **Neither is on the backend host `PATH`** of this WSL shell (the development session runs inside the desktop app). Real provider diagnostics therefore report `cli_missing` here; that is the honest result. |
| Output filesystem | `/mnt/d` is 9p/drvfs. Probed: atomic replace, directory fsync, `flock`, `O_EXCL`, Parquet round-trip all work. The legacy SQLite `ExperimentStore` refuses drvfs by design; the new Parquet layer does not use SQLite. |

## 2. Binding design decisions

1. **No edits inside `src/analog_optimizer/`.** `training/sac.py::source_digest()` hashes every
   `*.py` under that package; `SACLearner.load` and the M5/M6 audit scripts require an exact
   match. Adding files there would invalidate existing checkpoints and the physical-experiment
   audits. All new code lives in the separate package **`src/gator_workbench/`** and composes the
   existing `CircuitSizingEnv`, `SACLearner`, `ReplayBuffer`, `Transition`, `ActionMapper`,
   `SpecificationEvaluator`, `transfer_weights`, `SpectreParser`.
2. **SAC algorithm unchanged.** One update per newly admitted eligible transition once a batch
   is available (the existing `collect_episode` rule). Defaults mirror existing entry points.
3. **One versioned schema** (`gator-workbench-config-v1`, pydantic) drives forms, agent
   `--json-schema`, JSON import/export and backend execution.
4. **Raw tables are Parquet**, acknowledged through an fsynced write-ahead journal and published
   as closed part files listed in an append-only flush log. CSV is derived only.
5. Runs execute in a **detached worker process** controlled through files in the run
   directory; the HTTP server and any agent CLI session can exit without affecting a run.

## 3. Stage status

| Stage | Scope | Status |
|---|---|---|
| 1 | Repo inspection, unified schema, manual editing, output-directory settings | **done + tested** (backend, API, UI) |
| 2 | Connection check (2.1), circuit reading, static validation, one baseline simulation | **done + tested with fixtures**; netlist/registered-task reading real; native reading and the connection check implemented against the confirmed bridge 0.8.0 API but **never run against a live Virtuoso** |
| 3 | Optimization backend, shared budget, four modes, checkpoints | **done + tested** on the MOCK backend; real backend wired but blocked here |
| 4 | Raw Parquet tables, experience archive, best designs, five CSV exports | **done + tested** |
| 5 | Agent providers (Claude Code first), proposals/approvals, FastAPI, React frontend | **done**; providers tested with fake CLI fixtures only; UI type-checks and builds, exercised through the HTTP API, **not clicked through in a browser** |

## 4. Changed / added files

Tracked file modified: `pyproject.toml` (additive: `web`, `webtest` extras, `gator-workbench` script).
Nothing under `src/analog_optimizer/` was touched. New package `src/gator_workbench/`:

| Module | Responsibility |
|---|---|
| `schema.py` | The one versioned config schema (`gator-workbench-config-v1`); field guidance; JSON Schema; hashes |
| `units.py` | Explicit unit registry; unknown units rejected |
| `validation.py` | Semantic validation; `error` / `blocker` (valid but not executable by the backend) / `warning` / `unresolved` |
| `compile.py` | Config -> existing `ParameterGroup` / `MetricSpec`; independent hard-constraint check; restricted expressions |
| `tasks.py` | Task providers: `synthetic:*` (MOCK), `real:*` GPDK045 profiles with blocker + interface contract; the netlist import was removed (7.53) |
| `paths.py` | Output-root allowlist, tested writability, Windows path verified by read-back, mock root isolation |
| `storage/` | Atomic JSON, fsynced JSONL, journaled Parquet dataset (WAL + flush log + quarantine), table/data-dictionary definitions |
| `budget.py` | Shared budget ledger: reserve/charge/release, retries, launch cap, first-feasibility snapshot |
| `lanes.py` | Thread / process lanes around the existing `CircuitSizingEnv`; same-evaluation retry |
| `engine.py` | Asynchronous scheduler, commit path, retention, pause/stop/cancel, crash recovery, status |
| `checkpoints.py`, `modes.py` | Consistent checkpoints, capability metadata, compatibility report, scratch/resume/fine_tune/frozen |
| `trajectory.py` | State encoding (static template + exact patch) and loader back to optimizer `Transition`s |
| `best_design.py` | Best-design selection, JSON/CSV, optimized netlist verified by re-parsing |
| `summary.py`, `aggregates.py` | `run_summary.json`; five research CSVs + meta sidecars; on-demand table CSV |
| `layout.py`, `runs.py`, `worker.py`, `security.py` | Directory layout/manifests, run preparation/control + connection gate, detached worker (inherits the run lock), redaction |
| `connection.py` | Section 2.1: seven layers in dependency order, probe in a short-lived process, coalescing, staleness, gate, diagnostics log, infrastructure-failure classification |
| `bridge_read.py` | Gated read-only native access (`library.list`, `schematic.read`) |
| `agents/` | `base` (safe subprocess, error taxonomy), `claude_code`, `codex`, `disabled`, `prompts`, `proposals` (scope + hash-bound approval), `diagnostics` |
| `api/app.py`, `cli.py` | FastAPI backend (127.0.0.1), `gator-workbench serve / validate / run / aggregates / check` |

Other new files: `frontend/` (React + TypeScript + Vite; `src/App.tsx`, `src/api.ts`, `src/store.ts`,
`src/panels/{Left,Editors,Right,Bottom}.tsx`, `src/styles.css`), `docs/workbench.md`, `CLAUDE.md`,
this file. Modified tracked files: `pyproject.toml` (additive extras + script), `.gitignore`
(`outputs/`, `frontend/node_modules/`).

Tests: `tests/workbench/` (`helpers.py`, `conftest.py`, `fixtures/fake_cli.py`, `test_wb_*.py`).

## 5. Test commands and results

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q     # workbench only
/tmp/analog-optimizer-venv/bin/python -m pytest -q                      # full regression
```

### 5.1 Results

| When | Command | Result |
|---|---|---|
| Before any change | full suite | 574 passed, 0 failed (5 m 15 s) |
| After stages 1/3/4 | `tests/workbench` (5 files at that point) | 127 passed, 0 failed |
| First full run after all stages | full suite | 796 passed, **1 failed** - NOT a product failure: `connection.py` and its test were edited while that run was executing, so the already-imported old test met the new probe. Not reported as a result. |
| Clean full run (no edits in flight) | full suite | 799 passed, 0 failed (8 m 55 s). It exposed a test-isolation leak (section 5.3). |
| **Final full run** (2026-09-20 17:36-17:44; afterwards only a `--connection-stale-seconds` option + 1 test were added, API+connection tests re-run: 64 passed) | `/tmp/analog-optimizer-venv/bin/python -m pytest -q` | **801 passed, 0 failed, 0 skipped** (8 m 37 s) = 574 pre-existing + 227 workbench. Real settings file untouched. |
| Frontend | `cd frontend && npm run build` (`tsc --noEmit` strict + `vite build`) | passes; 201 kB JS, no charting dependency |

All workbench runs in tests use the MOCK analytic backend (`origin=synthetic`). They verify accounting,
persistence and plumbing. They establish nothing about algorithmic generalization.

Bugs the tests caught and that were fixed (kept here so they are not reintroduced):
`read_json(default=None)` treated as "no default"; task hash computed before the circuit content hash was
stamped; saved-vs-live contract compared list against tuple (every resume looked incompatible); bindings
were only checked against configured initial values, not the values read from the circuit; several editor
fields had no guidance text.

### 5.2 Real (non-fixture) verification performed

Real (non-fixture) checks performed on the development host, each zero-cost and read-only:

* output root `/mnt/d/gator/outputs` -> allowed, writable, 9p, Windows path `D:\gator\outputs` **verified by read-back**;
* connection check with NO profile -> `bridge_package: failed / bridge_not_importable`, everything downstream `not_checked`;
* connection check, cheap layers, against the user's REAL setup (2026-09-20 evening; scratch settings dir pointing at the
  existing `~/.virtuoso-bridge/.env` and the bridge venv's site-packages; env contents never read or printed):
  `bridge_package ok (0.8.0 = verified)`, `connection_profile ok (remote, default profile, required settings present)`,
  `tunnel ok (running)`, layers 4-7 `not_checked` by design, 0.3 s, zero cost. Layers 4-7 (one read-only SKILL round
  trip, readiness, Spectre, license snapshot) are user-triggered and have NOT been run against the live Virtuoso;
* agent diagnostics -> `claude` and `codex` not on the backend PATH, provider `disabled`, nested session suspected
  (the backend had been started from inside a Claude Code session), no bridge skill in a Claude discovery location;
* starting `real:gpdk045_ota5` -> refused (`task_blocked`), nothing created.

Genuinely generated example (MOCK backend, through the real HTTP API and a detached worker):
`outputs/mock/delivery_example__aa693365859f/` - 60 evaluations, 2 lanes, first feasible at 6 charged,
89 files, 9.5 MB, no image/report files.

### 5.3 Defects found late, and the rule each one leaves behind

* **Tests wrote into the user's real `configs/local/workbench/` twice.** First because modules imported
  `local_settings_dir` by name (a per-module monkeypatch missed one); then because the fail-closed hook was a
  `pytest_sessionstart` in a sub-directory conftest, which a full-suite run loads lazily, while module-scoped
  fixtures run before function-scoped overrides. Both times the polluted files were restored. Rule: the
  override is `GATOR_WORKBENCH_SETTINGS_DIR`, set at conftest IMPORT time (it also reaches worker and probe
  subprocesses); `tests/workbench/test_wb_isolation.py` guards every fixture scope.
* **Duplicate-worker race.** A worker needs 2-3 s (torch import) before it could take the run lock, so a
  double-clicked Continue could append a second resume segment and spawn a second worker. Rule: preparation
  takes the lock BEFORE touching the manifest and hands the locked descriptor to the worker (`--lock-fd`).
* **Probe violated dependency order** when no profile existed (reported a downstream layer failed while the
  upstream one said `not_checked`). Found only by the real check on this host. Rule: layer 1 is always checked first.
* **Two first requests corrupted `torch_geometric` for the life of the backend.** Every heavy import is lazy and
  endpoints run in a thread pool, so a fresh page load made `/api/meta` (version report) and the debounced
  `/api/config/validate` import `torch_geometric` for the first time at once. CPython hands one thread a partially
  initialized package; `/api/meta` swallowed its failure (`torch_geometric: unavailable`) and every later
  validation returned 500 until a restart. Never seen by the suite: conftest imports torch first. Rule: whatever
  the workbench imports lazily from the optimizer stack is imported once, single-threaded, in `create_app`
  (`gator_workbench.preload`); `test_wb_preload.py` replays the first page load in a fresh interpreter and fails
  on an unlisted lazy import. Details: 7.11.
* Never edit source or tests while a verification run is executing; re-run cleanly instead of explaining a failure away.

## 6. Blockers and honest limitations

1. **No real Virtuoso/Spectre evaluation was run by this work.** `virtuoso_bridge` is not importable from the
   project interpreter, no connection profile exists, and no real budget was authorized. The real path
   (`tasks._real_runtime` -> `NativeEnvironmentFactory`, `ProcessLane`) is wired and guarded but unexercised.
   To enable: create `configs/local/workbench/bridge_connection.json` (format in `docs/workbench.md`) with
   `bridge_site_packages`, start the tunnel yourself, run `gator-workbench check <profile> --scope full`.
2. **Agent CLIs absent.** `ClaudeCodeProvider`/`CodexProvider` were verified only against fake CLI fixtures built
   from the documented result shapes (docs checked 2026-09-20). Unverifiable here and therefore not relied on:
   a non-billable auth check (auth is reported `unknown`), `--disable-slash-commands`, a nested-session variable,
   skill listing in the init event. Codex options are verified at run time against `codex exec --help`.
   Model availability of `claude-fable-5-1` for the runtime provider was not probed (it would cost money).
3. **Bridge skill not visible to Claude Code.** Proposal only (symlinks into `.claude/skills/`); not executed.
4. Bridge 0.8.0 has no "list cells/views of a library" call; cell and view names are typed and verified by a read.
5. Not implemented, reported as blockers by validation/API instead of being faked: design-variable writeback,
   non-uniform discrete candidates, non-linear binding expressions, ADE/Maestro outputs and generic waveform
   extraction during optimization, PVT/Monte-Carlo conditions, native schematic writes, prompt-driven TOPOLOGY
   changes (only parameter-value changes on a netlist working copy), `threads_per_job` (recorded, applied by no
   existing backend), validation-set `best_policy` selection inside a run (API exists; single-task runs never call it).
6. Remote Spectre temp directories: the existing adapter does not return the remote path, so only the local
   result directory and `sync_status` are tracked.
7. The UI was built and its API contract tested, but not exercised interactively in a browser.
   There is also no explicit output-directory MIGRATION tool: a run's directory is fixed when it starts and
   a resumed run writes back to it, so output is never split, but moving a run is a manual copy while no
   worker is active. No feature re-runs a simulation to recover a deleted waveform.
8. `/tmp/analog-optimizer-venv` can be cleaned by the OS; reinstall with `pip install -e '.[graph,web,webtest]'`.

## 7. Next steps

1. With the user: configure a connection profile, run the zero-cost check against an already-started tunnel,
   then one authorized baseline on `real:gpdk045_ota5` (1 evaluation) as the first real smoke test.
2. Click through the UI in a browser; fix what only interaction reveals.
3. Install `claude` on the backend PATH and run one authorized proposal request to confirm the documented flags.

