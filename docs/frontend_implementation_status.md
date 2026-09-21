# Frontend / run-control / data-output implementation status

Short working record for `gator_claude_code_fable51_frontend_data_outputs_en.md`.
After context compaction or a resumed development session: reread **this file**, the
code diff (`git status`, `git diff`) and the specification before continuing. Do not
redo completed modules from conversational memory. This is a development record, not a
research output or analysis report.

Last updated: 2026-09-20 (~21:25: section 7.7, per-encoder network settings from publications; ~21:35: section 7.8, Agent tab side window + browser check; ~21:50: section 7.9, connection panel; ~22:00: section 7.10, agent model / effort lists; ~22:00: section 7.11, validate 500 from a concurrent first import of torch_geometric; ~22:15: section 7.12, blocking-issues button in the header; ~22:40: section 7.13, netlist import form; ~22:30: section 7.14, detachable agent conversation; ~23:10: section 7.15, Virtuoso source dropdowns; 2026-09-21 early: section 7.16, start checklist + readiness request; 2026-09-21 ~01:15: section 7.17, read a Virtuoso cell into the workbench (profile creation, increment 1); ~03:40: section 7.18, header Start -> Pause -> Resume + Abort; ~03:30: section 7.19, Create profile -> registered real:<name> task (increment 2); ~04:40: section 7.21, no-simulation check of a generated profile + baseline reference; ~06:00: section 7.22, result registry of generated profiles + measurement replayed on real result files; ~05:20: section 7.24, FIRST REAL SIMULATION through the workbench (generated profile baseline) + the preparation-service bug; 2026-09-21: section 7.25, fewest-changes start + profile check; section 7.27, detach control on the agent tab).

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
| `tasks.py` | Task providers: `synthetic:*` (MOCK), netlist import, `real:*` GPDK045 profiles with blocker + interface contract |
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

### 7.1 Resolved: Virtuoso bridge connection request (2026-09-20)

The user said the specification was changed to add "functionality of virtuoso bridge connection" and
left the timing to the agent. **At that moment the file on disk was unchanged** (440 lines, 46,499
bytes, mtime 15:25:58, identical headings; only one copy exists), so the new text had not been saved
to `/mnt/d/gator/`. The user was asked to save it.

Outcome: the saved text (spec section 2.1, saved 16:17:37) was read at the start of stage 2 and implemented (`connection.py`, gate in `runs.py`, in-run safe pause in `engine.py`, automatic cheap check at backend start / profile change, UI panel, 50+ tests); the optional periodic interval check was NOT implemented. Original plan: **Re-read the spec file immediately before
implementing**; follow the saved text if present, otherwise build a conservative version and label it
as derived from the one-line description. Guardrails that hold either way: existing connection
profiles only (no hard-coded hosts/accounts), never auto-start a tunnel or deploy a daemon, never
display tokens, real connection tests only on an explicit user click.

### 7.2 Coordination with the parallel "Project directory setup" session

That session owns the VCO requalification files and its uncommitted edits to `README.md`,
`docs/decisions.md`, `docs/m6-cross-category.md`; this work does not touch them (workbench docs go in
new files only). It had a live real Spectre run until ~16:35 on 2026-09-20 and asked for no bridge
writes / baseline simulations meanwhile. It will relocate `vco_requalification.py` out of
`src/analog_optimizer/` (~17:00), which changes `source_digest()` from `2b21a5128fb7...` back to
`02127bc39140...`; workbench checkpoints written before that stop passing a strict `resume`
(visible `code digest` incompatibility) but still load for `fine_tune`/`frozen`.

### 7.3 Connect flow in the panel (2026-09-20 late evening, separate session, explicit user request)

Request: "fix the virtuoso bridge connection part on front end so it connects target ssh then give the
command of connection for virtuoso CIW use, then leave a button for testing the connection prompting
back status". Root cause of the dead panel: `configs/local/workbench/bridge_connection.json` never
existed, so the panel had no profile and every button was disabled.

This **relaxes one guardrail of 7.1 on the user's instruction**: the tunnel may now be started by the
application, but only by the explicit "Connect SSH" click. Spec 2.1 forbids starting it "as a side
effect of a check, on page load, or on a timer"; all three still hold.

| Piece | Where |
|---|---|
| Explicit connect (`SSHClient.from_env(keep_remote_files=True).warm()`, as `virtuoso-bridge start`), one-click profile creation from the bridge setup found on the host, CIW command text, one-sentence status | new `src/gator_workbench/bridge_connect.py` (kept OUT of `connection.py`; `RealBridge` still has no starting method) |
| Tunnel layer now reports the bridge's saved `setup_path`; next-step hints mention the button | `connection.py` (observation only; forbidden-string guard still passes) |
| `GET /api/connection/setup`, `POST /api/connection/profile`, `POST /api/connection/connect`; `summary` + `ciw` on check/status answers | `api/app.py` |
| Three-step panel: 1 Connect SSH, 2 CIW command with Copy, 3 Test connection with a status line | `frontend/src/panels/Left.tsx`, `api.ts`, `styles.css` |
| 25 tests, fake bridge + fake connect process | `tests/workbench/test_wb_bridge_connect.py` |

Also in this session: the Agent tab now lists the failing fields of a rejected configuration/proposal
(`frontend/src/panels/Bottom.tsx`), which the UI used to hide behind "does not match the schema".

Never done by this code: stop/restart of a tunnel, daemon restart, sending `load(...)` to the CIW
(upstream's `bootstrap`/`load` commands are not used), accepting a host/port/path/command from the
browser, overwriting an existing connection file.

**Real verification (2026-09-20, scratch settings dir, second backend on port 8766, the user's own
backend and real `configs/local/workbench/` untouched):** setup detection found the real env file and
bridge site-packages; profile creation wrote a valid file; Connect returned `already_running` in 0.4 s
(the user's tunnel had been up for ~23 h, so **no SSH connection was opened - the `started` path has
only been exercised with the fake bridge**); the CIW line was read from the real bridge state; one
interactive test passed for real: `bridge_package`, `connection_profile`, `tunnel`, `daemon`,
`session_readiness` all `ok` in 1.1 s, zero evaluations, zero Spectre launches. This is the first real
run of layers 4-5. Layers 6-7 (Spectre, license) remain unexercised against the real host. The panel
was type-checked and built, **not clicked through in a browser**.

Tests after the change: `pytest tests/workbench -q` -> **253 passed, 0 failed** (3 m 52 s) = 228 earlier + 25 new.
The 574 non-workbench tests were not re-run: nothing under `src/analog_optimizer/` changed (source digest untouched).
Frontend: `npm run build` (strict `tsc --noEmit` + `vite build`) passes, 206 kB JS.

### 7.4 Per-circuit bindings in a connection profile (2026-09-20 late evening, same session as 7.3)

The user started a real task and was blocked: "The connection profile lacks ['library', 'creation_receipt',
'model_file', 'reference_measurements']". Design gap found on the way: a profile had ONE receipt and ONE baseline,
although both describe a single circuit - four real tasks would have needed four profiles, with nothing stopping
the opamp receipt from being selected for the LDO.

* `tasks.py`: `real_bindings()` reads `"circuits": {"<task name>": {creation_receipt, reference_measurements}}`
  first (flat keys = fallback); `real_backend_blocker(profile_id, name)` names the task and the missing keys, and
  compares the receipt with the circuit's design file + requires an `origin: real` baseline (local reads, zero cost);
  `list_tasks()` reports availability per circuit. `tests/workbench/test_wb_real_bindings.py` (8 tests).
* The user's real `configs/local/workbench/bridge_connection.json` (created by the panel button) was completed from
  evidence of record, not guessed: `library` / `model_file` / ota5, ldo, vco from the frozen
  `artifacts/local/m6-real-protocol/bindings.json`; ota7 from the qualification named by
  `m5-topology-acceptance-summary.json` (`passed: true`, `origin: real`) with receipt `m5-ota7-v2-baseline`
  (cells match `configs/gpdk045_ota7_design.json`). The ota7 pair could NOT be cross-confirmed by hash against the
  M5 run report; the adapter's receipt check and the first baseline comparison remain the safety net.
* Verified for real, zero cost: all four `real:gpdk045_*` tasks pass the blocker and assemble their runtime
  (`load_task(..., allow_real=True)`: profile class, design, mapping, graph; no bridge contact). Without the
  explicit authorization they are still refused. **No real simulation was started.**
* Tests after 7.4: `pytest tests/workbench -q` -> **261 passed, 0 failed** (3 m 47 s) = 253 + 8 new. Non-workbench tests not re-run (`src/analog_optimizer/` untouched).

### 7.5 Real tasks could never be authorized from the UI (2026-09-20 late evening, same session)

With the profile complete (7.4) the user met the next refusal on loading the circuit: "Real Virtuoso/Spectre
execution requires an explicit user action with an authorized budget". This was a deadlock, hidden until now
because the missing-profile blocker always fired first: the UI shows the budget-authorization dialog only when the
LOADED circuit is real (`isReal`), but `load_task(allow_real=False)` refused to load a real circuit at all - so
`authorize_real_simulation` could never be sent, from any button.

Fix - loading is not executing; the gate moved to where execution begins, in three places:
* `tasks.py`: an unauthorized real task loads as a describe-only runtime (`authorized=False`, a note says so). It is
  assembled from local files only - no bridge contact. Its environment builder raises `TaskBlocked`.
* `runs.prepare_run`: a real task without `allow_real` is refused FIRST (before validation, gate, directories) with
  the new code `real_authorization_required`; nothing is created.
* `worker.py`: refuses a real run launched without `--allow-real`; it also now passes the run's own
  `connection_profile_id` (it used the ACTIVE profile before - a silent-other-profile risk with several profiles).
* UI: Start asks for the authorization up front when the loaded circuit is real, and also when the backend answers
  `real_authorization_required` (circuit not loaded in the panel first). The circuit panel marks a REAL backend.

Verified for real through the API with the user's profile (second backend, port 8766, since stopped):
`real:gpdk045_ota5` loads (`mock: false`, 10 devices, 9 metrics); a baseline start WITHOUT the authorization flag
-> HTTP 409 `real_authorization_required`, real runs before/after 0/0. **The authorized path was deliberately not
exercised: no real simulation was started; that budget decision is the user's.**

Tests after 7.5: `pytest tests/workbench -q` -> **263 passed, 0 failed** (3 m 52 s) = 261 + 2 new. Frontend `npm run build` passes. Non-workbench tests not re-run (`src/analog_optimizer/` untouched).

### 7.6 Agent tab: "was my request even sent?" (2026-09-20 ~21:00, separate session, explicit user request)

User report, first real use of the Agent tab (provider `claude_code`, CLI now installed and logged in):
`user hello` -> 17 s later `error cancelled: HTTP 409 (your configuration is unchanged)`, twice. Findings:

* Both requests WERE sent and the CLI was running. `cancelled` has exactly one source: `/api/agent/cancel`, i.e. the
  "Cancel request" button. Nothing on screen said a request was in flight (only a disabled button), so waiting
  looked like a hang, and the cancel itself was then reported as a red error.
* **Every agent error read "`<code>`: HTTP 409".** Agent errors are `{code, meaning, detail}`; `ApiError` only read
  `detail.message`, so the actual reason was dropped for ALL agent error codes, not just `cancelled`.
* Switching the bottom tab unmounted `AgentTab`: chat, pending state and the proposal that later arrived were lost
  while the backend kept working on the request.

Changes (frontend only; no Python touched, no backend restart needed, `dist` is served from disk):
* `api.ts` `ApiError`: message falls back to `detail.detail` / `detail.meaning` / a string detail before `HTTP <status>`.
* `Bottom.tsx` `AgentTab`: Enter sends, Shift+Enter breaks the line, an Enter that confirms an IME candidate
  (`isComposing` / keyCode 229) does not send; the text box clears on send and gets the text back if the request fails
  or is cancelled; a pending row ("Sent. Waiting for the agent's reply... N s", live counter, also on the button);
  a cancel is a neutral `system` line ("Cancelled by you after N s ... nothing was changed"); a cancel that finds no
  process says so; a network failure says the backend did not answer; Enter with provider `disabled` explains why
  nothing was sent; the chat scrolls to the newest line.
* `App.tsx`: `AgentTab` stays mounted and is hidden with `display: none` (`hidden` prop). `styles.css`: `.msg.system`, `.msg.pending`.

Verified: strict `tsc --noEmit` + `vite build` pass (217 kB JS); the running backend (port 8765) serves the new bundle;
the free `import-result` error path returns `{code, meaning, detail, problems, configuration_unchanged}` with no `message`
key, confirming the cause. **First real `ClaudeCodeProvider` round trip ever** (one request, `synthetic:opamp`, kind
`targets`, through the running backend): HTTP 200 in 5.7 s, `origin: claude_code`, empty patch as asked, 2 turns,
~24 k prompt tokens (almost all the CLI's own system prompt), CLI-reported notional cost $0.30 against the user's
subscription. So the documented flags (`-p --output-format stream-json --verbose --json-schema --permission-mode
dontAsk --disallowedTools`) work with CLI 2.1.278; this closes next-step 3 above and the "fixtures only" caveat of
blocker 2 for Claude Code (Codex is still not on the PATH). A `draft_config` request on a real circuit will take
longer than this 6 s. NOT verified: no browser click-through of the new key handling / pending row (no browser
automation on this host); there is no frontend test runner in the project. Not done: streaming partial output to
the chat (the backend reads the CLI with one `communicate()`; needs SSE or a per-request log to poll).


### 7.7 Per-encoder network settings from publications (2026-09-20 ~21:20, separate session, explicit user request)

Request: "find and set all the settings of each network (including advanced) from analog circuit design
publications. Changing the drop down will read the backend parameter of each type of network. Changing the
parameter will change the backend network setting. Grey out the heads box with an 'ignored by this encoder'
hint when the encoder isn't graph_transformer or gat." Starting point: the RL-network boxes showed numbers typed
into `Right.tsx` (32 / 4 / 2) and read nothing from the backend; one value set served all six encoders.

| Piece | Where |
|---|---|
| Publication presets with per-field provenance (`paper` / `official_code` / `adapted` / `gator_default` / `not_used`, plus `closest` when no publication uses that network), the GATOR baseline (= schema defaults), the operator's saved values (`configs/local/workbench/network_settings.json`), whole-set validation with the run schema | new `src/gator_workbench/network_presets.py` |
| `GET /api/network-settings`, `PUT /api/network-settings/{encoder}`, `POST /api/network-settings/{encoder}/reset` | `api/app.py` (placed after `get_schema`; separate `from .. import network_presets` line) |
| Drop-down loads the backend values; edits are saved per encoder (700 ms debounce, complete value set); `heads` greyed out + hint; "Publication preset" / "GATOR baseline" buttons; "differs from the backend" prompt; provenance table with links; budget-vs-warm-up/batch warning; "Use the checkpoint's network" when a selected source checkpoint has another `model_config`; gamma, tau, initial alpha, target entropy, max grad norm now visible under Advanced; number boxes keep typed text (`0.005`, `3e-4` were impossible to type) | `frontend/src/panels/Right.tsx`, three lines in `api.ts`, two lines in `styles.css` |
| Warning `budget_within_warmup` (the whole budget is random warm-up; applies to `fine_tune` too, where it stops the pretrained policy from ever acting) | `validation.py` |
| 16 tests incl. one end-to-end MOCK run with the default encoder's preset and a pin on the verified numbers | `tests/workbench/test_wb_network_presets.py` |
| Verbatim quotes, sources, limits, measured parameter counts | new `docs/network-presets.md` |

Presets (hidden / heads / layers; lr, gamma, batch, warm-up, replay, episode): `graph_transformer` 48/4/4 and `gat`
192/3/4 with 1e-3, 0.9, 32, 8, 50, 30; `gcn` 32/-/7, `rgcn` 32/-/4, `port_gnn` 32/-/5 with 3e-4, 0.99, 128, 1000,
100000, 50; `mlp` 256/-/4 with 3e-3, 0.8, 256, 120, 1000000, 30. Sources: GCN-RL (DAC 2020), Li & Chan Carusone
(ICCAD 2023, R-GCN + DDPG), Cao et al. (DAC 2022, code only), Lighthouse RL (arXiv:2607.14008, SAC + GAT), CAN
(MLCAD 2021), GTN (DAC 2024), PPAAS (ICCAD 2025, SAC), ParaGraph (DAC 2020). Every number was read in the primary
text or the authors' code, not in a summary.

Stated bluntly: **no publication uses a graph transformer as the RL sizing agent** and none uses the `port_gnn`
network, so their training numbers are borrowed from the closest published networks and labelled so. The cited
studies spent 300 to ~50,000 simulations per run; with GATOR's tens of evaluations a published batch size of 128
and 1,000 warm-up steps mean no learning at all, which the panel and the validation warn about. **No preset has
been evaluated on a GATOR circuit**, and presets differ 32-fold in parameter count (160 k to 5.2 M), so they must
not be used for the equal-size encoder comparison. The GATOR baseline button restores 32 / 4 / 2 + batch 8.

Compatibility kept: a configuration WITHOUT a network block (CLI, tests, older JSON) still gets the schema
defaults; `src/analog_optimizer/` untouched, `source_digest()` = `02127bc39140...` (the M6 pin) after the change.

Verification: `pytest tests/workbench -q` -> **279 passed, 0 failed** (no other run active; includes the other
sessions' new tests). Non-workbench tests not re-run (package untouched). `npm run build` passes, 217 kB JS. Real
HTTP check on a scratch backend (port 8767, scratch settings dir): presets served, an edit stored in the scratch
file, the built page served with the new panel strings. The user's own backend had been restarted at 21:17:37,
after the last Python edit, and already served the final presets. At that point the panel had only been
type-checked and built. Not done: per-encoder presets in the CLI (`gator-workbench run` takes the configuration
as written).

**Browser check added afterwards (same evening, user request "align the button of GATOR baseline and publication
preset").** `frontend/scripts/network_panel_check.mjs` drives a headless Edge against the running backend, in the
same way as `agent_tab_check.mjs` (7.8): 16 checks + 4 screenshots of the RL-network block. `GET
/api/network-settings` is the real backend; every `PUT`/`POST` below it is intercepted and answered with a canned
entry, so the check never writes `network_settings.json`. Its first run reproduced the report (the "In use" text
shared a line with one button, the other wrapped below it: y 708 vs 740, widths 119 vs 107) and found a defect in
the new number box: text typed into a focused box hid a value that changed from outside (reset button, undo).
Fixes: the "In use" line stands alone and the two buttons are one equal-width pair spanning the panel (`.row.pair`,
149 x 26 each, same y); typed text is dropped once it no longer stands for the current value. After the fix:
**16/16 checks pass**, no console errors; verified there: backend values on a fresh page, drop-down loads the
chosen encoder, `heads` greyed out with its hint, no write on a mere selection, an edit sends the COMPLETE value
set for that encoder, GATOR baseline posts the reset and shows 32 / 4 / 2. `npm run build` passes (218 kB JS).
Still not covered by the browser check: the Advanced boxes, the "differs from the backend" prompt and "Use the
checkpoint's network" (type-checked only).

### 7.8 Agent tab: warnings / unresolved in a side window + a real browser check (2026-09-20 ~21:30, same session as 7.6)

Request: "separate warnings and unresolved etc to another side window next to user message box". Frontend only.

* `Bottom.tsx` `AgentTab`: the chat shows a reply's text plus a count link ("3 unresolved, 2 warnings"); the lists
  themselves (`errors`, `problems`, `unresolved`, `warnings` of a line's `extra`, table `NOTE_GROUPS`) moved to an
  `<aside class="notes">` to the right of the message box, grouped with counts. It follows the newest REPLY
  (`user`/`system` lines do not take it over; a clean reply shows "Nothing listed"), a count link on an older line
  shows that line's notes ("back to the latest reply" returns). Layout: chat on top, then a two-column `.compose`
  grid - left = proposal under review + message box, right = the side window, as tall as both; its inner box is
  absolutely placed so a long list scrolls instead of stretching the row. The request-kind selector moved onto the
  button row: with a proposal open the send button used to fall below the 34vh panel edge.
* **`frontend/scripts/agent_tab_check.mjs`** (new): drives a throwaway headless Edge over the DevTools protocol
  against the running workbench - Windows node >= 22 (built-in WebSocket), no new dependency, run line in its
  header. `/api/agent/propose` and `/api/agent/cancel` are intercepted and answered with canned data labelled
  `fixture`, so no CLI starts and no usage is spent. 34 checks + 7 screenshots: Enter sends / Shift+Enter breaks
  the line / an IME-composition Enter is left alone, box clears and refills, pending row and button count seconds,
  cancel is a neutral line, errors show the reason, side-window placement and content, older-line notes, chat
  survives a tab switch, no console errors. **All pass - this also closes the "no browser click-through" caveat of
  7.6 for the Agent tab** (not for the rest of the UI; the same technique would work there).

`npm run build` passes (218 kB JS). No Python touched, so no pytest run and no backend restart; refresh the page.

### 7.9 Connection panel: renamed, and a check only on a button press (2026-09-20 ~21:50, separate session, explicit user request)

Request: "change the name of virtuoso/bridge connection to virtuoso bridge connection and remove the timer function
only check connection when I press the button". This deliberately drops two automatic checks that spec section 2.1
allows (line 102: "once at backend start or profile change") and that 7.1 had implemented; the user's instruction
takes precedence.

* `Left.tsx` `ConnectionPanel`: heading "Virtuoso bridge connection". Removed the automatic cheap check on profile
  change / page load and the 15 s `setInterval` that re-read the cached status. On load the panel now reads
  `GET /api/connection/status` ONCE (a cache read; it probes nothing). A check runs only on Connect SSH (the cheap
  check that follows it), Test connection and + Spectre / license.
* Consequence, stated plainly: without a timer the panel cannot turn an old `ok` into `unknown` by itself, so the
  age line changed from a running "tested N s ago" to the clock time of the test ("tested at 21:50:41"). The shown
  result is the result of the last press, not a live indicator. The backend's staleness rule is unchanged: a page
  reload shows a result older than `--connection-stale-seconds` as `unknown` ("too old to trust").
* `cli.py`: `serve` no longer runs the cheap check at backend start; `--connection-check-on-start` brings it back.
  `create_app(auto_check_on_start=True)` and the API's `trigger: "auto"` are untouched (their tests still hold);
  only what `serve` passes changed. New test `test_serve_checks_the_connection_at_start_only_when_asked`.
* NOT changed, on purpose: the pre-dispatch gate still probes the link afresh before every real action (read/write
  a cellview, real simulation), whatever the panel shows - it is the protection of the real-simulation budget, not
  a display timer.
* `frontend/scripts/connection_panel_check.mjs` (new, same technique as 7.8): every `/api/connection/*` request is
  intercepted, logged and answered with a canned FIXTURE answer, so no probe starts and Virtuoso is never
  contacted. 16 checks + 3 screenshots, all pass: heading; page load = one `GET profiles` + one `GET status` and no
  `POST`; no request during 17 s (the old poll was 15 s); one press = exactly one user-triggered interactive check;
  clock time shown; result unchanged after another 17 s; reload reads the cache once and labels an old result.

`npm run build` passes (220 kB JS); `test_wb_api.py` + `test_wb_connection.py` + `test_wb_bridge_connect.py`: 90
passed. The UI change needs a page refresh only (the running backend serves the new `frontend/dist`); the `serve`
change takes effect at the next backend restart - the running backend was NOT restarted (other sessions use it).
`docs/workbench.md` updated. Uncommitted.

### 7.10 Agent tab: model and effort lists per provider (2026-09-20 ~22:00, same session as 7.6 / 7.8, explicit user request)

Request: "does loading the agent model and effort cost a lot? if not, add the list of supported models for each
provider, and the supported effort levels." It costs nothing: neither CLI can list its models and the vendors'
model endpoints need an API key this application never holds, so the lists are a hand-maintained table plus one
local file read. No CLI is started and no model is called to show them.

| Piece | Where |
|---|---|
| Table per provider: models (id, label, note, effort levels), provider effort levels, `verified` date + `source`; `supports_effort`, `efforts_for`; `claude_cli_default()` = what `claude` will use when nothing is passed, read from ONLY the `model` / `effortLevel` / `modelSettings` keys of `~/.claude/settings.json` (`CLAUDE_CONFIG_DIR` honoured) plus `ANTHROPIC_MODEL` / `CLAUDE_CODE_EFFORT_LEVEL` of the backend process, incl. the effort each listed model would get | new `src/gator_workbench/agents/catalog.py` (imports nothing from the package) |
| Effort validation is per provider (Claude `low..max`, Codex `minimal..xhigh`); a level kept from the other provider or a hand-edited file is read as "CLI default" instead of a 500 on every agent endpoint | `agents/base.py`, `agent_settings()` in `api/app.py` |
| `GET /api/agent/settings` also returns `catalog` | `api/app.py` |
| `--effort` is not passed for a listed model that takes none (Haiku) | `agents/claude_code.py` |
| Codex effort, ignored until now, is passed as `--config model_reasoning_effort="<level>"`, and only if `codex exec --help` lists `--config` (else `unsupported_cli`) | `agents/codex.py`, fake CLI help + scenario `codex_without_config` |
| Model drop-down (CLI default with the detected model, the provider's models, "Custom..." + text box), effort drop-down (CLI default with the detected level for the chosen model; greyed out with "ignored by this model"), hint with the model's note and the list's date; a provider change resets both; the left column scrolls by itself (its new length pushed the message box out of the 34vh panel) | `frontend/src/panels/Bottom.tsx`, `styles.css` |

Lists (checked 2026-09-20 against the vendors' pages, not from memory - the Codex line-up had changed completely):
Claude Code `fable`, `opus`, `sonnet`, `haiku` + pinned `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5`,
`claude-haiku-4-5-20251001`; effort `low medium high xhigh max`, none on Haiku ("Models not listed here do not
support effort"). Codex `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, legacy `gpt-5.5` (retires
2026-10-14), `gpt-5.4`, `gpt-5.4-mini`; `model_reasoning_effort` `minimal low medium high xhigh`. **Codex has never
been installed on this host: its list and its effort argument are from documentation only and were never exercised**
(the UI says so). The table is a convenience, not a gate: any other single-line model name is still accepted.

Measured on the user's three real requests (audit log + CLI transcripts; the CLI's cost figure reproduced to the
cent from list prices): Fable 5.1 at effort `high` (the CLI default from the user's settings - per-model `high`
overrides the general `xhigh`), $0.30 / $0.52 / $0.53 notional against the subscription. **About 88 % of that is
writing ~14-23 k prompt tokens to the 1-hour cache on every request** ($20 per million); thinking + answer is ~11 %,
so the effort level barely moves the cost here while the model choice scales it 1 : 0.5 : 0.2 : 0.1 (Fable : Opus :
Sonnet : Haiku). Only ~2.6-7.9 k of those tokens are the workbench's own prompt; the rest is the CLI's system
prompt, re-written each time. Not investigated: whether the per-request scratch directory is what defeats cache
reuse between requests (testing it costs real requests).

Verification: `test_wb_agent_catalog.py` (6 new) + agents + API tests: 57 passed. Full `pytest tests/workbench -q`:
**284 passed, 1 failed** - `test_wb_engine.py::test_forced_cancel_records_unfinished_evaluations_as_charged`, NOT from
this work: run alone it failed 3 times in 8 with `cancelled == []` (the forced cancel found nothing in flight; a
timing race in the test), `engine.py` / `lanes.py` / the test are unmodified since the commit, and the run shared
the machine with a headless browser and a second backend. It needs a fix of its own. Browser check
`frontend/scripts/agent_tab_check.mjs` extended to 46 checks (lists, greyed effort, save, Custom..., provider
switch, settings restored at the end) and run against a SCRATCH backend (port 8768, own settings directory,
stopped afterwards): all pass. Two defects it found and that were fixed: "Custom..." pre-filled the box with the
previous model's name, and the longer left column pushed the message box below the panel edge.
`npm run build` passes (220 kB JS). Python changed: the backend needs a restart to serve the lists (until then
the tab falls back to the old text box and says so). Uncommitted.

### 7.11 `/api/config/validate` returned 500: concurrent first import of `torch_geometric` (2026-09-20 ~21:55, separate session, user-reported traceback)

Report: the backend log showed `POST /api/config/validate` 500 with `AttributeError: partially initialized module
'torch_geometric' has no attribute 'typing' (most likely due to a circular import)`. The configuration was not at
fault.

* Cause, reproduced in fresh interpreters (no backend, no simulator): a single-threaded import of
  `analog_optimizer.models.inputs` works (2.0 s). Two threads - `__import__('torch_geometric')` as in
  `layout.environment_versions()` and `from analog_optimizer.models.inputs import SpecSchema` as in
  `validation.default_registry()` - started 0 / 0.5 / 1.0 s apart BOTH fail with `cannot import name 'Data' from
  partially initialized module 'torch_geometric.data'`; 1.5 s and 2.0 s apart both succeed (the first import has
  finished). A failure poisons the process: `torch_geometric` is dropped from `sys.modules` while 61 of its
  submodules stay cached, so a retry finds `torch_geometric.typing` already loaded and never sets it on the new
  package object - the reported message, on every later request. The browser produces exactly this timing:
  `api.meta()` at mount, the debounced validation 500 ms later. It needs a page LOAD against a backend that has
  not imported the stack yet; a backend whose first heavy request came alone is safe for good, which is why it
  looked intermittent.
* Fix: new `src/gator_workbench/preload.py` (`MODULES`, `preload()`: idempotent, locked, import errors
  propagate); `create_app` calls it first, before any thread or request exists. Cost: 2.3 s once per process, no
  thread started, `virtuoso_bridge` not imported (optional package; finding it is layer 1 of the connection
  check). No lazy import was moved and no endpoint changed. Zero edits under `src/analog_optimizer/`:
  `source_digest()` is still `02127bc3...` (the M6 pilot pin).
* Tests: `tests/workbench/test_wb_preload.py` (new, 3). (1) A subprocess builds the real app and sends `/api/meta`
  and `/api/config/validate` through a barrier as its first two requests, then validates again. One-off control
  with `preload` disabled: meta 200 but `torch_geometric: unavailable`, validate 500, later validate 500; with the
  fix 200 / 200 / 200. The control is not a test: asserting that the defect still exists would pin a CPython/PyG
  timing detail. (2) An `ast` scan of the package fails on a function-level import of `analog_optimizer`, `torch`,
  `torch_geometric`, `numpy` or `pyarrow` that is missing from `MODULES`. (3) `virtuoso_bridge` is never preloaded.
* Verified: `pytest tests/workbench -x` exit 0 (289 collected; the count line was lost to a doubled `-q`; the
  flaky forced-cancel test of 7.10 happened to pass). The user's backend on 8765 had been restarted at 21:52:52,
  after the edit: one static validation of the `synthetic:opamp` starter config returned 200
  (`blocks_run=false`). A second session that received the same report checked independently without editing
  anything: 4 of 4 reproductions, 3 of 3 clean with `preload()`, and 8 concurrent validations against the live
  backend all 200.
* Limits: the 574-test optimizer regression was not run (no file of that package changed). Run workers are
  separate processes that import single-threaded (`runs.py` Popen; `worker.py` imports torch first) and were left
  alone. `environment_versions()` still reports a failed import as `unavailable` instead of raising - harmless
  now, but it is what hid the first failure.

Python changed: a backend started before 21:52 gets the fix at its next restart. Uncommitted.

### 7.12 Header: the blocking-issues notifier is a button that lists them (2026-09-20 ~22:15, same session as 7.11, explicit user request)

Request: "change the blocking issues notifier to a button. After the button is released, it shows the all the
blocking issues". Frontend only. It also closes a gap: the header only COUNTED blocking issues, the editor tables
show `level: code` with the message as a tooltip, and an issue that belongs to none of the three tabs (`run.*`,
`output.*`, `research.*`, or a configuration the backend rejected as a whole) was shown nowhere in full.

* New `frontend/src/panels/Issues.tsx` `ValidationStatus` (a separate file, because several sessions edit
  `App.tsx` and the panels): "validating..." / "configuration valid" stay text; with `blocks_run` the header shows
  a red button "N blocking issue(s)" (`aria-expanded`, `aria-controls`). A press (click, i.e. on release; Enter /
  Space work as for any button) opens a table of EVERY `error` and `blocker`, in report order: #, level, code,
  where (the field path plus the key of its editor row, e.g. `parameters[0].lower row input_pair_width`; an empty
  path reads "(whole configuration)"), and the message in full. Warnings, unresolved and info lines are not
  listed (they do not block).
* Behaviour chosen on purpose: the list is a full-width second line of the header (`flex-wrap`, `order`), so it
  pushes the page down instead of covering the editors it is used with, scrolls by itself above 30vh, follows
  every validation while open (a checklist while fixing), closes on a second press or "Hide", closes when nothing
  blocks any more, and a later problem brings back the button CLOSED - it never opens by itself. No click-outside
  close: the first click into an editor would close the list one is working from.
* `App.tsx`: the `<span>` became `<ValidationStatus .../>` (import + one line; the unused `blocking` constant
  removed). `styles.css`: `header` wraps; `button.issues-button`, `.issue-list*`.
* `frontend/scripts/blocking_issues_check.mjs` (new, same technique as 7.8 / 7.9): every
  `/api/config/validate` is answered with a canned FIXTURE report (3 blocking among 6 issues), GETs pass through and
  EVERY other writing request is refused, so the check can start, save or probe nothing (the page itself sent
  `POST /api/circuit/load` and `POST /api/output/check` on load; both refused). A temporary browser profile is
  seeded with the MOCK starter configuration; the user's saved configuration is not touched. 26 checks + 4
  screenshots, all pass: it is a `<button>`; counts blocking issues only; nothing listed before a press; with the
  mouse button HELD DOWN nothing is listed, on RELEASE the list appears; all 3 listed in full and no other; row
  key / outside-the-tabs field / whole-configuration wording; full-width second header line that does not cover
  `main`; an open list follows the next validation (3 -> 1); second press and "Hide" close it; valid = text, no
  button, list closed, Start enabled; a new problem returns the button closed; Enter opens it; no console errors.
  A defect it found: the page goes blank on a configuration without an `output` section (the first seed lacked
  it; `config.output.output_root` in `App.tsx`). Pre-existing and NOT fixed here. Read from the code, not tried:
  "Import JSON..." of a file that has `schema_version` but no `output` takes the file as the whole configuration
  (`Editors.tsx` `importJson`) and would hit the same crash; an exported file always has the section.

`npm run build` passes (222 kB JS). No Python touched: no pytest run, no backend restart; refresh the page.
Uncommitted.

### 7.13 Circuit source "Import Spectre netlist" answered "Blocked" before anything was typed (2026-09-20 ~22:40, same session as 7.9, user report)

Report: choosing the source showed "Blocked: A netlist source needs netlist_path and parser_config_path; device port
order and parameter semantics are never guessed."

* Cause: not a loader defect (three netlists load through `/api/circuit/load`, relative or absolute paths).
  `CircuitPanel` reloaded on EVERY change of the circuit reference, so choosing the source asked the backend with
  both paths still empty, and the ordinary "fill in two boxes" state came back as a red blocker that named schema
  fields (`netlist_path`, `parser_config_path`) instead of the form's labels. The same effect sent one request per
  typed character.
* `Left.tsx` `CircuitPanel` (frontend; refresh the page): for a netlist the panel asks the backend only on
  **Load netlist** (or Enter, IME-safe) - never while a path is typed or missing. Until both boxes are filled it
  shows a plain explanation (what the two files are, that nothing is uploaded, the allowed input roots from
  `/api/meta`, `--allow-input-root`) and the button stays disabled; with both filled, "Not loaded yet". An edit
  clears the circuit loaded before (it no longer belongs to the reference; `App`/`RunPanel` read it). A complete
  reference that arrives from outside the panel (imported configuration, approved proposal) still loads by itself,
  like a registered task - registered tasks are unchanged. **Try the example** fills and loads the opamp fixture
  (absolute paths from `repo_root`). A Windows path (`D:\gator\x.scs`) is converted to its WSL path when the
  backend's own paths are POSIX, and the box shows what was sent. Backend messages shown in this panel have the two
  field names replaced by the labels. A request counter lets only the newest load answer (a slow older answer
  could overwrite a newer one, also for registered tasks). `App.tsx`: passes `meta` to the panel.
* `tasks.py` (Python; next backend restart): the blocker names only what is missing - "An imported netlist still
  needs a device mapping JSON (parser_config_path). ..." - because the API, the CLI and static validation show it
  too. New test `test_an_incomplete_netlist_reference_names_the_file_that_is_missing`.
* Unchanged on purpose: source "Virtuoso library / cell / view" still answers Blocked at once - that one is a real
  blocker (no verified profile for an arbitrary cellview), not an unfilled form.
* `frontend/scripts/circuit_source_check.mjs` (new, same technique as 7.8 / 7.9): load requests are logged and
  passed on to the REAL backend (a netlist load only parses two local files; MOCK, nothing simulated or written).
  21 checks + 2 screenshots, all pass: choosing the source sends nothing and shows no blocker; typing (several
  input events per box) sends nothing; one press = one load with both paths, 7 instances shown; an edit unloads
  without a request; Enter loads; a missing file is a readable blocker; a Windows path is sent converted, once; a
  path outside the roots is refused with the form's label; the example loads; a registered task still loads by
  itself; no console errors.

`npm run build` passes (228 kB JS); `test_wb_api.py` + `test_wb_schema_validation.py` + `test_wb_real_bindings.py`:
76 passed before the new test, which passes. Not done: a file picker - paths are still typed (or pasted).
Uncommitted.

### 7.14 Agent conversation: detachable window, readable messages, model and effort in use (2026-09-20 ~22:30, same session as 7.6 / 7.8 / 7.10, explicit user request)

Requests: "is it possible to detach the agent conversation tab and make it more readable?" and, while that was
being built, "show what is the current model and effort". Frontend only (`Bottom.tsx`, `styles.css`).

* **Detach.** "Detach into its own window" opens a browser window (`window.open`, 1180 x 900) and draws the SAME
  `AgentTab` into it through a React portal: chat, pending request, proposal and settings are one component state, so
  nothing is synchronised between windows and nothing restarts. The page's stylesheets are copied into the new
  document (absolute `href`, the window is `about:blank`). While detached the tab shows a note with "Show that
  window" / "Bring it back here" and the bottom panel is free for the other tabs. Back again by the button in either
  window or by closing the window (`pagehide`); the workbench page leaving closes the window instead of orphaning
  it. A blocked pop-up is reported in the chat. `confirm()` for a circuit working copy is asked in the window the
  user is looking at.
* **Readable.** One bubble per message: the user's right-aligned (line breaks kept), the agent's left with an accent
  edge, errors red, workbench remarks small and centred; "You / Agent (provider) / Workbench / Error" instead of
  raw role names; LOCAL clock time (it was UTC). Replies are shown as light Markdown - paragraphs, bullet / numbered
  lists, `code`, **bold** - built as React text nodes only (`RichText`); a reply is never parsed as HTML.
  Detached: 14.5 px type, conversation over the message box, notes as a full-height column. **Attached layout changed
  too:** the bottom panel is wide and short, so conversation | proposal + message box | notes now stand side by
  side at the full panel height (before, an open proposal squeezed the conversation to a 60 px strip, which bubbles
  made worse). The notes are still next to the message box.
* **Model and effort in use.** A line above the conversation: "Next request: <provider>, model <m>, effort <e>";
  a value the CLI picks itself is the one read from the user's CLI settings and is labelled "(CLI default)" (7.10;
  not confirmed by a request), Haiku shows "not used by this model". Every agent reply keeps what ITS request was
  sent with in its header, whatever is chosen afterwards.

Verification: `npm run build` passes (229 kB JS). `frontend/scripts/agent_tab_check.mjs` now 58 checks, all pass,
against a scratch backend (port 8768, own settings directory, stopped afterwards; the user's settings file
untouched): formatting without raw marks, bubbles, the in-use line following the drop-downs, detach (second
DevTools session on the new window: same conversation, styles applied, Enter there sends, reply + notes arrive
there, other tabs usable meanwhile), back by button, back by closing the window, no console errors. Test-only
findings: a headless pop-up ignores the requested size (the check sets 1180 x 900 itself), and Edge opens a
"syncing your data" page in a fresh profile, so the window is looked up by its title. No Python touched: a page
refresh is enough. NOT verified: a real (non-headless) pop-up on the user's desktop - pop-up blocking and window
placement are the browser's. Uncommitted.

### 7.15 Circuit source "Virtuoso library / cell / view": libraries, cells and schematic without buttons (2026-09-20 ~23:10, same session as 7.9 / 7.13, explicit user request)

Request: "could it automatically list the library with no button, then cell then etc, why does it need to select
views? what does class and pdk id stands for?"

* Correction of an earlier finding: `bridge_read.py` said the bridge cannot list cells or views and that SKILL is
  not written from memory. The first half is true of the package API, but the bridge checkout ships the listing
  as an example, `examples/01_virtuoso/basic/04_list_library_cells.py` (one `execute_skill`: `ddGetObj(lib)`,
  `lib~>cells`, `cell~>views`; the package itself uses `vbLib~>cells~>name` in `library/category.py`). That SKILL
  is copied unchanged as `bridge_read.CELLS_SKILL`. Read-only `dd` calls: no cellview is opened, no window touched.
* Backend (Python; NEXT BACKEND RESTART): `bridge_read` op `cells` -> `client.library.get(name)` (an unknown
  library raises instead of listing nothing; gives the technology library) + the listing ->
  `{library, technology_library, cells: [{name, views, has_schematic}], truncated}` (names that are not plain
  Cadence names are dropped; cap 5000). `POST /api/virtuoso/cells`, gated like the other native reads
  (`read_cellview`). New test `test_cells_of_a_library_are_listed_with_their_views` (parser, SKILL text pinned
  read-only, argv of the reader process, name validation, 409 from a blocked gate).
* Frontend (`Left.tsx` `CircuitPanel`, `api.ts`; page refresh): choosing the source lists the libraries; choosing
  a library lists its cells; choosing a cell reads its schematic. Each step waits for the one before it, so there
  are never two bridge calls at once, and each starts from an explicit choice. A configuration that is already on
  this source does the same when the page loads (the user asked for "no button"; it is three gated, read-only,
  zero-cost calls). Library / Cell / Testbench cell are dropdowns; a cell without a schematic view is listed but
  cannot be chosen. **Refresh** repeats the chain (after the link came up, or after the design changed). A blocked
  gate is reported in one sentence that points to the connection panel; against a backend without the new route
  the panel says so and falls back to a typed cell + "Read native schematic".
* The View box is gone. Finding: it never did anything - `schematic.read(lib, cell)` takes no view and always
  opens the view named `schematic` (read-only, closed again), and nothing in the backend reads
  `CircuitReference.view`. The panel now states "View: schematic" and lists the cell's other views; `view` is set
  to `schematic` in the configuration when a cell is chosen.
* Class / PDK id: relabelled "Circuit class" (with suggestions) and "PDK id", each with a tooltip and one line
  under them: labels saved with every run (run manifest, research CSV grouping, the unseen-class validation
  warning); they change neither simulation nor optimization. The PDK id is offered from the library's technology
  library (`techGetTechLibName`, e.g. `GATOR_TESTS` -> `gpdk045`) and never overwrites a typed value.
* For this source the box under the form reads "Browse only:" instead of "Blocked:" - the statement (an arbitrary
  cellview cannot be optimized without a verified circuit profile) is unchanged; it is a limit, not a fault.
* Verified REAL (read-only, zero-cost, no run active, user's tunnel): the reader process for `GATOR_TESTS` (9 cells,
  tech `gpdk045`) and `analogLib` (180 cells, 22 with a schematic, 19 kB) in 0.8 s each; the new route end to end
  through a temporary backend on port 8766 (gate probe + listing 1.6 s; unknown library -> readable 502), stopped
  afterwards. The user's backend on 8765 (their own terminal, started 22:27) was not touched and answers 405 on the
  new route until they restart it.
* `frontend/scripts/virtuoso_source_check.mjs` (new; every `/api/virtuoso/*` call answered by FIXTURES, Virtuoso
  never contacted): 28 checks + 3 screenshots, all pass. It found a real defect first: `cells?.library ===
  ref.library` is true when both are undefined, and the page went blank on load for about two minutes of builds
  (fixed; `circuit_source_check.mjs` re-run, 21 pass).

* Follow-up ~00:10 (the user pasted the box text back without a question): for this source the red box with the
  backend sentence ("verified circuit profile (writable parameters, CDF rules, analyses, measurements)",
  "Interface contract") became a neutral `.note` in plain words - what a circuit profile is (which sizes may
  change and in which steps, which testbench, how results are read), that a new circuit needs one first
  (development + a few real simulations, not a setting), and one button per `real:*` task from `/api/tasks` that
  switches the source to that registered task. The backend sentence and the contract moved under "Technical
  details". Backend text and its test are unchanged. `virtuoso_source_check.mjs`: 31 checks pass.

`npm run build` passes (235 kB JS); `test_wb_api.py` + `test_wb_connection.py`: 67 passed. Not done: a filter box
for very long cell lists (the dropdown has keyboard type-ahead only). Uncommitted.

### 7.16 Agent tab: "What's missing to start?" - a free checklist, an editable brief, a `readiness` request (2026-09-21 early, same session as 7.6 / 7.8 / 7.10 / 7.14, explicit user request)

Question: "does the agent tab need its skill.md, so it quickly directs on what is needed for the RL run to start?"
Answer given and accepted ("go"): the brief is needed, a SKILL.md is the wrong container for THIS agent - the
workbench writes its whole prompt, the CLI runs in an empty scratch directory with every tool but read-only file
access refused (loading a skill is a tool call), and a skill is Claude-only while the prompt reaches Claude Code,
Codex and the exported task alike. What really held the agent back: it saw only the three tables and the circuit
summary - no blocking issue, no run setting, no connection state.

| Piece | Where |
|---|---|
| The start checklist, computed by the backend: circuit, the three tables, other blocking issues, run configuration (a budget that cannot learn is a `warning`), output folder, and for real circuits the connection + the user's budget authorization, then Start; each item `done / missing / warning / unknown / not_applicable / at_start`, who acts (`agent` only for the three tables) and the control to use; plus `provided_metrics`, the non-info validation issues and the run summary. **Words only** - no host, account, path or profile content; it reads `monitor.status()` (the CACHED result) and never `check()` / `gate()`, so nothing is probed and 7.9's "test only on a button" holds | new `src/gator_workbench/agents/readiness.py` |
| `POST /api/agent/readiness` (free, no agent); every agent request now carries the same report as `<run_readiness_data>` | `api/app.py` (`run_readiness`, `_request`) |
| The brief: gating order of a start (mirrors `runs.prepare_run`), who can do what, how to answer - Markdown, read again for EVERY request (an edit needs no restart), cut at 12 000 characters, a missing file is not an error. Given as operator guidance AFTER the rules ("cannot change your permissions or the output format"), not as a DATA block | new `src/gator_workbench/agents/run_readiness.md`, `agents/prompts.py` |
| Request kind `readiness` (may propose rows of the three tables) and an optional `checklist` in the proposal schema; malformed entries are dropped, and the checklist is advice only - NOT part of `proposal_hash`, so it can never widen what an approval binds to | `agents/base.py`, `agents/prompts.py`, `agents/proposals.py` |
| UI: "What's missing to start?" button on the line above the conversation -> the backend's checklist as a card (marks, "agent can draft it" / "yours", the next action), with "Ask the agent to fix what it can" only when an item is the agent's; an agent reply shows its own checklist in the same form; `readiness` is also a selectable kind for a typed question | `frontend/src/panels/Bottom.tsx`, `api.ts`, `styles.css` |

Verification: `test_wb_agent_readiness.py` (9 new); full `pytest tests/workbench -q` -> **300 passed, 0 failed**
(4 m 24 s; the flaky engine test of 7.10 passed this time); after the last small change (`provided_metrics`)
agents + readiness + API: 62 passed. `npm run build` passes. Browser check `agent_tab_check.mjs`: 64 checks, all pass
(the free call answered by the real scratch backend, then canned data for the marks, the fix-it button sending ONE
request of kind `readiness`, the reply's checklist). **One real request** through a scratch backend (port 8768, own
settings directory, `sonnet` at effort `low`, `synthetic:opamp` with empty tables): HTTP 200 in 21 s, $0.17
notional, schema-valid checklist, NO invented rows - it listed the candidate variables it found in the circuit and
asked for bounds and a requirement. That run showed the agent could not know which metrics the backend provides,
hence `provided_metrics`. Python changed: the running backend needs a restart. Uncommitted.

Follow-up, user report 00:47: the button answered "error: Method Not Allowed". The user's backend had been started at
22:47, before the endpoint existed, while the page (served from disk) already had the button; a POST to an unknown
route falls through to the static mount, hence 405. Not a defect of the endpoint, but the message was useless. The
Agent tab now recognises a bare framework "Not Found" / "Method Not Allowed" (HTTP 404/405 with a string detail, which
no workbench endpoint produces) and says that the running server is older than the page and must be restarted, and
that nothing was sent to an agent. Browser check: 65 checks, all pass. Rule this leaves: a change that adds an
endpoint AND a button must say "restart the backend" first in its hand-over, not last.

### 7.17 Profile from a Virtuoso cell, increment 1 of 3: read the cell INTO the workbench, agent hand-off (2026-09-21 ~01:15, same session as 7.9 / 7.13 / 7.15, explicit user request)

**RESTART THE BACKEND FIRST** (new Python: a module, a reader op, an endpoint). Against an older backend the new
button answers "this backend is older than the page".

The user's plan (their words, 2026-09-21): pick a cell -> the workbench reads it -> **the agent reads the circuit,
says what it is and suggests which sizes to vary, how they are grouped, the ranges and the targets; approved in
the Agent window, it fills the three editors** -> **"Create profile" registers the result as a new `real:<name>`
task that appears under Registered task, and the cell stops being browse-only.** Agreed consequences of that
shape: no separate "probe the step sizes" step (the verified 5 nm MOS-width grid plus the adapter's strict
readback check at run time cover it), and the baseline is the existing, budget-authorized "Single baseline
simulation" button of the registered task, not a step of profile creation.

Increment 1 (this section) = everything up to the filled editors. Increment 2 = Create profile: a file-driven
generic profile class OUTSIDE `src/analog_optimizer/` (the real path is duck-typed on the profile object - no
`isinstance` in `training/parallel.py` / `backends/native_preparation.py`; it uses `design`, `reference`,
`writable_keys`, `mos_names`, `nominal_corner`, `instances`, `optimization_graph`, `validate_*`,
`verify_transition`, `structure_for_condition`, `analysis_settings`, optional `deck_name` / `analyze`), to be
proven OFFLINE first by generating profiles from the recorded artefacts of the four existing circuits and
comparing with their hand-written classes; then registration. Increment 3 = the first real baseline, which needs
the user's budget authorization. Known limit carried forward: the adapter writes MOS widths only
(`set_gpdk_mos`).

* `native_cells.py` (new): the local copy of an imported cell under
  `configs/local/workbench/native_cells/<library>/<cell>/` (`netlist.scs`, `core_readback.json`,
  `testbench_readback.json`, `mapping.json`, `meta.json`, the netlister `package/`, `bridge.log`). The mapping
  holds only device models this project already verified - collected at run time from the `models` of
  `configs/gpdk045_*.json` (six today; a model defined differently in two files is dropped) - and only net `0`
  gets a role (ground). Any other model stays `unknown` and is named in a note. A directory whose netlist or
  mapping no longer matches its recorded hash is treated as absent. A second import replaces the first only after
  it parsed; a failed one leaves nothing behind.
* `bridge_read.py` op `import_cell`: `schematic.export_netlist` of the testbench (or of the cell when none is
  named) + `schematic.read` of the cell (and testbench) - the same two read-only calls the run adapter makes for
  every candidate; nothing is edited, nothing simulated. `POST /api/virtuoso/import`
  `{profile_id, library, cell, testbench?}`, gated like the other native reads.
* `tasks.load_task`, source `virtuoso`: with a stored import the cell LOADS from the local copy (no bridge, no gate)
  as `virtuoso:<lib>/<cell>` with `native_draft=True`, so the circuit panel, the editors' circuit-aware checks,
  the static validation and the agent's circuit summary all work. It can never execute: `allow_real=True` (a run
  start) raises, the builder raises, `runs.prepare_run` refuses before any authorization question, and the static
  validation carries the blocker `circuit_profile_missing` (metrics are "not checked" for a draft, because which
  ones it will provide is not known yet). Without an import the old browse-only blocker is unchanged.
* Frontend: the browse-only note gained **Read this cell into the workbench** (explicit press: it exports on the
  VM and takes seconds). A loaded draft shows a neutral note instead of "REAL evaluation backend", with **Ask the
  agent for suggestions** (opens the Agent tab with `draft_config` and a written-out, editable request - nothing is
  sent by itself; `AgentTab` accepts an optional `prompt` in its hand-over and keeps text already typed) and
  **Read the cell again**. The note says plainly that Create profile is not built yet - no dead button.
* Tests: `tests/workbench/test_wb_native_cells.py` (new, 4; fake reader process + the recorded REAL ota5 export):
  verified-only mapping, unverified model flagged, load from the local copy, every execution path refused, tamper
  detection, replace / failed import, name validation, API load + validation blocker + start refused with and
  without authorization + no run directory, 409 from a blocked gate.
* Verified REAL (read-only, zero-cost, no run active, temporary backend on 8766, stopped afterwards): import of
  the user's `GPDK045_RINGOSC/ring_osc_3stage` through `tb_ring_osc_3stage` in 2.8 s -> 10 devices, 5 nets, tech
  `gpdk045`, `g45cmim` (the MIM caps) unverified; `/api/circuit/load` loads it as a draft; validation blocks the run
  with `circuit_profile_missing`; `/api/agent/export-task` (no CLI call) carries the devices in the task text. The
  import was left in place in the user's settings folder. NOT done for real: an actual agent request on the draft
  (it would spend the user's usage; the agent path itself is unchanged).
* `virtuoso_source_check.mjs` now also covers the import press, the draft view, re-import through a testbench and
  the agent hand-off (nothing sent by itself); `circuit_source_check.mjs` re-run. All pass.

Open points for increment 2: `g45cmim` needs a verified mapping entry before a graph with it counts as complete;
net roles (supply / input / output) are not set for a draft; the three editors must be turned into the profile's
rule file.

### 7.18 Header: one run button Start -> Pause -> Resume, and Abort next to it (2026-09-21 ~03:40, separate session, explicit user request)

Request: "add pause and continue functionality for the current run. after start it becomes pause, press pause it
becomes resume also add a abort button next to the start. I think it has nothing to do with the resume mode but it is
similar." **Frontend only: no Python touched, no backend restart, a page refresh is enough.**

Finding first: the backend could do all of it since stage 3; only the header could not. `pause` / `stop` / `cancel`
through the control file, `POST /api/runs/continue`, and four small buttons in the Run status tab that the user had
not found. About the user's guess: Resume IS the machinery of Mode = resume (a pause saves the full state and the
worker EXITS; continuing adds a `resume` segment to the SAME run directory and a new worker restores network, replay
memory, counters and budget) - but the Mode box is not involved: `/api/runs/continue` takes the run's own
`effective_config.json`. Consequence, stated in the button's tooltip: edits made on the page while a run is paused
are NOT used by Resume (a changed task could not continue the same run anyway).

| Piece | Where |
|---|---|
| `useRunControl` (which run the header holds, its status, pending requests), `phaseOf`, `RunButtons`, `launchWithConsent`, `resumeRun` | new `frontend/src/panels/RunControl.tsx` (a separate file, as 7.12: several sessions edit `App.tsx` and the panels) |
| Header: `<RunButtons>` replaces the Start button; `start` / `continueRun` rewritten on `launchWithConsent`; the baseline button is available only while the header is idle; the Run status tab's buttons report errors and tell the header | `frontend/src/App.tsx` |
| `.run-main`, `.run-abort`, `.run-chip` (fixed widths: the header does not shift when a label changes) | `frontend/src/styles.css` |

Behaviour, each point chosen on purpose:
* **The main button** reads Start -> (Starting...) -> Pause -> (Pausing...) -> Resume -> (Resuming...) -> Pause ...;
  the labels in brackets are disabled. "Pausing..." appears at the press, before the run has answered. Pause =
  command `pause`: no new simulation is dispatched, the one in flight finishes and is recorded, checkpoint, worker
  exits. Resume sends `continue` for the same directory with the budget unchanged and asks nothing for a MOCK run.
* **Abort is the graceful `stop`, not the forced `cancel`.** Read from the code before deciding: on a forced cancel
  the lane's `close` (which restores the schematic) queues behind the running simulation with a 10 s deadline, then
  the lane process is terminated; a Spectre job already running on the server is never killed. On a real circuit a
  forced abort can therefore leave the testbench with the candidate's sizes and an orphan remote job, and the
  evaluation is charged but lost. So: Abort asks first (plain words, "use Pause to continue later"), sends `stop`,
  and only while a pause or an abort is WAITING for the simulation in flight the second button reads **Force abort**
  (= `cancel`, asked again with its cost, usable once). The engine ignores a `stop` that follows a `pause`, which is
  the other reason the waiting states offer only the forced variant.
* **Abort on a paused run sends nothing**: it lets go of the run ("Nothing is deleted ... can still be continued
  later: Run status > Continue") and the button returns to Start. There is no backend operation that turns `paused`
  into `stopped` without starting a worker, and none was added.
* **The header holds ONE run, the "current run", which is not the run the bottom tabs show.** Reason: with one
  shared selection, looking at an older run's data would have replaced Pause by Start (or by the Resume of that
  older run) while a simulation is running - on the real backend a second start on the same testbench. The current
  run is the one started / resumed from this page, remembered in `localStorage`
  (`gator-workbench-current-run-v1`); a small text button in the header shows it ("running 12 / 60",
  "paused at 35 / 20000 [MOCK]", "stopped 41 / ...") and brings it back under Run status when pressed.
* **"Start" is never offered on a guess.** After a reload the button is disabled until the remembered run has
  answered; with nothing remembered, until the run list (already read on page load) is in: a run that is live
  although this browser does not remember it (CLI, another browser) is taken over. Single baseline simulation is
  available only while the header is idle.
* **Polling (the user's "no timers" preference, 7.9):** no new timer at rest. The header uses the status the page
  already polls for the run in the bottom tabs when that is the same run; otherwise it polls its run itself, and only
  while that run is live. A paused or ended run is asked once.
* Two timing traps, both found by reading `run_status` and confirmed live: `status.json` says `paused` while the old
  worker still writes its last files (alive), and it STILL says `paused` for 2-3 s after a Resume while the new
  worker imports (alive again). The same pair of values means "almost paused" once and "running again" the other
  time; the hook tells them apart by knowing that this page has just launched a worker, and ignores answers asked
  for before the launch. Without that the button flickered Resume -> Pausing... -> Pause.
* Pause asks BEFORE, not after, when the run's own saved configuration has checkpoints or replay snapshots switched
  off ("cannot be resumed after a pause ... Pause anyway?"); it reads `effective_config.json` through the existing
  download route.
* Real runs: Resume asks for the budget again ("up to N more candidate evaluation(s)? (M of T are used.)").
  **Fixed on the way:** "Continue" in the Run status tab sent `authorize_real_simulation` WITHOUT asking whenever the
  circuit loaded in the panel was real, and Cancel in its budget prompt continued the run anyway. Both buttons now go
  through `resumeRun`; realness is taken from the RUN's status, not from the circuit panel. Start's three backend
  questions (real budget, model from another task, unknown connection layers) are now answered in a loop, so two of
  them in a row no longer end in an error banner.

Verification (no Python changed, so no pytest run):
* `npm run build` (strict `tsc --noEmit` + `vite build`) passes, 258 kB JS (includes 7.19 / 7.20 of the other sessions).
* `frontend/scripts/run_control_check.mjs` (new; hermetic like 7.12: every `/api/runs/*` call and the validation are
  answered by a small simulated run labelled FIXTURE, other writes refused, so it is safe next to a live run): **60
  checks + 7 screenshots, all pass** (the final version twice in a row). It pins: labels and order with nothing in between (a
  `MutationObserver` records every label the button ever shows), Abort directly right of the main button, one
  request per press, no question for a MOCK pause / resume, the three confirmation texts, Force abort only while
  waiting and only once, no header polling at rest, the live run keeps Pause with the bottom tabs on another / no
  run, reload and take-over never show an enabled Start, the no-replay-snapshots warning, real-run authorization
  sent only after a yes, a backend refusal shown with its reason, the Run status tab's own buttons still work and
  the header follows them. Its first run failed once on a fixed 1.8 s wait in the check itself (replaced by a
  condition); no product defect.
* `frontend/scripts/run_control_live_check.mjs` (new): the same presses with NOTHING intercepted, against a scratch
  backend (port 8769, own settings directory and output root in the session scratchpad, stopped and deleted
  afterwards) and the synthetic MOCK task - a real detached worker. **23 checks, all pass** (run twice; the whole-sequence check was
  added for the second run): the backend
  agreed at every step (`paused` + `full_state`, nothing charged while paused, `entry: resume` with counters kept,
  `stopped` / `user_stop`, event log `pause > ended:paused > resumed > stop > ended:stopped`), the button showed
  `Start > Starting... > Pause > Pausing... > Resume > Resuming... > Pause > Aborting... > Start` and nothing else,
  and a Pause pressed while the worker was still importing was not lost (paused at 0 evaluations, `full_state`,
  resumed). The script refuses port 8765. `blocking_issues_check.mjs` re-run: 26 pass.
* NOT verified: anything on the REAL backend (no real simulation was started: that budget is the user's). There a
  pause or an abort waits for the rest of ONE real simulation, which the labels and the text button say. Force abort
  was exercised with fixtures only (a MOCK evaluation is too short to be caught in flight).

Not done: the Run status tab keeps its four buttons and wording ("Pause and save", "Stop and save", "Force cancel",
"Continue" with the new-budget question) - they act on the run shown there; a paused run that was let go stays
`paused` on disk; no backend guard against two live runs on one real testbench (the header avoids offering it, the
API would still accept it). Uncommitted.

### 7.19 Profile from a Virtuoso cell, increment 2 of 3: Create profile -> a registered `real:<name>` task (2026-09-21 ~03:30, same session as 7.17, user: "go on with stage 2")

**RESTART THE BACKEND FIRST** (new Python modules, a new endpoint). Section 7.18 is left to the parallel
"pause/resume controls" session, which announced it.

* **`generic_profile.py` (new) - one file-driven profile class instead of one hand-written class per circuit.**
  `GenericMosWidthProfile` subclasses the verified `Gpdk045OtaProfile` from OUTSIDE the protected package
  (nothing under `src/analog_optimizer/` changed; the real-run code is duck-typed on the profile object) and
  reads from `rules.json` what the four hand-written classes hard-code: the core instance, which MOS widths are
  writable and inside which bounds, the transistor set, the instances that must never change. The checks repeat
  `Gpdk045TwoStageProfile` line for line; group members keep their ratio; a group step must keep every member on the
  5 nm grid (the verified 1 : 0.25 pair needs 20 nm). Limits, because they are the limits of what was verified: MOS
  widths only (`set_gpdk_mos` is the adapter's single write path and forces fingers = m = 1, so a writable
  transistor recorded otherwise is refused), the 5 nm grid, nominal condition only, GPDK045 only.
* **Offline proof** - `tests/workbench/test_wb_generic_profile.py`: each of the four verified circuits is
  regenerated as a rule file over its RECORDED artefacts, and both forms are asked the same questions. They agree
  on every sampled assignment (corners and centre of the action space, off-grid, out of bounds, broken matching /
  ratio, missing / extra key, NaN, bool), on ten tampered readbacks (fixed parameter, frozen width, stale finger
  width, zero geometry, fingers, terminal net, master, missing / extra instance, fixed capacitor / resistor), on a
  width transition with fresh vs. stale derived geometry, on the export check, on `graph_contract`, and the
  generated form pickles (workers receive it pickled) and hashes (`profile_contract`). Rules the backend cannot
  honour are refused.
* **`recipes.py` (new)** - measurement recipes belong to a circuit TYPE. `opamp_ac` = the adapter's own deck and
  `measurements.opamp.analyze` (needs the verified OTA testbench conventions). `ring_oscillator` is new, for a
  free-running ring: the verified VCO recipe sweeps a control source such a cell does not have. It reuses the VCO's
  verified waveform contract (`measurements.vco.oscillation_metrics`, fixed values) and mirrors its deck and result
  handling: `dcOp`, `ic` on the stage nets, one conservative transient, metrics `osc_frequency_hz`,
  `supply_power_w`, `supply_current_a`, swing, duty, period spread, window drift, startup. The window comes from a
  ROUGH expected frequency (60 periods long, measured after 20, 100 points per period) so the contract still holds
  between about 0.6x and 1.5x. One-off check on REAL data: on the waveform of the user's standalone ring-oscillator
  run the measurement returns 1.209225e9 Hz, exactly the recorded value (that run is only 12 periods long, so the
  contract had to be relaxed to 3 cycles for this check; a generated profile simulates 60).
* **`configs/gpdk045_devices.json` (new) - the MIM capacitor `g45cmim` is a verified model now**, with its
  evidence: the PDK model file on the simulator host (`gpdk045_mimcap.scs:89 inline subckt g45cmim (n1 n2 body)`;
  control: `g45n1svt ( d g s b )` = the order already verified), plus the real export and readback of the same
  instance. A CDF `simInfo` query was tried first and abandoned: it failed even for the transistors, and SKILL is
  not written from memory here.
* **`profiles.py` (new) - Create profile.** Input: the local copy of the cell (7.17) + the rows of the parameter
  editor + circuit type (+ rough frequency). Output under `configs/local/workbench/profiles/<name>/`: `design.json`,
  `mapping.json` (verified models, net roles, the parameter groups exactly as compiled from the rows),
  `structure.scs`, `readback.cdf.json`, `rules.json`, `creation.json` (the receipt the adapter checks at connect),
  `profile.json`. Refused in plain words: anything but transistor widths of the core cell, log scale, missing bounds,
  a range that misses the present width, a step off the grid, multi-finger / m > 1, an unverified device, no
  testbench, a second profile for the same cell, an unknown type, an old copy of the cell. The ring recipe reads the
  supply (the one DC source), the ring order (gate -> drain chain, output first) and alternating start voltages off
  the netlist - for the user's cell `ic OUT=0 XU1.N1=1 XU1.N2=0`, the line their standalone run used. The rows come
  back ADJUSTED (bounds snapped inward onto the grid, step filled in, followers without clamps): a real run requires
  `graph_contract(configured) == graph_contract(profile)`. The finished folder must pass the profile's constructor
  (every check of the verified classes against the recorded files) or nothing is kept.
* **Registration (`tasks.py`)**: generated profiles are listed as `real:<name>` (`generated`, `verified`), load
  describe-only, execute only with the explicit authorization, use the cell's OWN library and the receipt of their
  folder, and need only `env_file` + `model_file` of the connection profile. No real baseline yet ->
  `reference_metrics=None` (the factory's comparison is optional); a recorded
  `reference_measurements.json` (`origin: real`) is picked up. A changed row is refused at run time. `POST
  /api/virtuoso/profile`; `circuit/load` answers `profile_task` / `profile_recipes`, so a cell with a profile is no
  longer browse-only. Bug fixed on the way: the reader now records `include_positions=True` like the adapter's
  `_read_snapshot` - without it instances have no `view` and no generated profile could pass `validate_readback`.
* **Frontend**: the draft note gained name / circuit type / expected frequency ("1.2G") and **Create profile**; on
  success the editor rows are replaced by the registered ones, the source switches to the new registered task, a
  note says nothing was simulated, and a warning asks for "Single baseline simulation" first. A cell that already
  has a profile shows "Open real:<name>".
* Tests: `test_wb_generic_profile.py` (5), `test_wb_profiles.py` (14; fixture = the recorded REAL export and
  readbacks of the user's ring oscillator, `tests/workbench/fixtures/ring_osc/`), `test_wb_native_cells.py`
  adapted (an invented model name plays the unverified device). The environment factory of the REAL backend is
  assembled from the generated profile offline. `virtuoso_source_check.mjs` covers refusal, creation, the opened
  task, the replaced rows and "already has the profile". Verified REAL (read-only, zero-cost): the ring oscillator
  was read again with the corrected reader (all models verified, `view` present), and the PDK model header was read.

**NOT done, and not claimable: no generated profile has run a real simulation.** Increment 3 = the user's
budget-authorized "Single baseline simulation" of their new task, then recording that result as the profile's
reference. The user's real profile was deliberately NOT created here: its rows should be the ones they approve
from the agent. To redo a profile, delete its folder under `configs/local/workbench/profiles/`.

### 7.20 Choosing which saved RL model to load (2026-09-21 morning, separate session, user: "can you choose which model to load?" / "what is a source run")

**RESTART THE BACKEND FIRST** (one new read-only route). Until then the block reads "The list of saved models
could not be read".

**What was wrong.** Saving and loading already existed (automatic checkpoints, "Pause and save" / "Stop and
save", "RL model to load" with a compatibility report), but choosing was poor: the block was hidden while Mode
was `scratch`; "Source run" listed EVERY run as `task_id | mode seedN | state`, including runs that hold no model
(selecting one answered 404); "Checkpoint" offered only `latest` and `best_policy` although the backend accepts
any checkpoint id - and `best_policy` can never resolve today, because nothing in the workbench calls
`select_best_policy`. The user did not know what a "source run" is.

**What changed.**
* **Backend** (`checkpoints.py`; nothing under `src/analog_optimizer/`): `list_checkpoints(run_dir)` = every
  complete save point of a run, oldest first, from the small `metadata.json` files only (nothing is hashed, no
  tensor is loaded; a directory without readable metadata is never offered). `saved_models(run_entries)` = the
  rows of `runs.list_runs` that hold at least one save point, most recently saved first, with task name, circuit,
  network, evaluations, capability and all save points. New read-only route `GET /api/runs/models`
  (`output_root`, `include_mock`; same path restriction as `/api/runs`). The selected model is still described and
  checksum-verified by `/api/runs/model`, unchanged.
* **Frontend**: new `frontend/src/panels/ModelChooser.tsx`, used by `RunPanel` in place of the two selects. One card
  per run that holds a model (task name, circuit, network `encoder hidden/heads/layers`, evaluations of training,
  number of save points, last save in LOCAL time, run state; tags `MOCK` / `other network` / `weights only`), then a
  "Save point" select: "Latest save (default)", "Best policy" only where one was selected, and every save point as
  "N evaluations - time - automatic save | saved at pause | saved at stop | saved at the end of the run". The block
  says in plain words what a run and a saved model are; in `scratch` it stays visible and says that no model is
  loaded and which Mode loads one. A selection that is not in the list (other output folder, save points gone) is
  said, with its folder and "Clear the selection". A filter box appears above 5 models. The facts table under it
  reads "Trained on / Saved (UTC) / Schema / Training / Restorable / Folder" and no longer breaks its labels
  mid-word.
* **Nothing on a timer.** The list is read when the block opens (Mode leaves `scratch`), when the application
  refreshes its run list (a run started / continued, output folder changed) and on "Refresh list". It is a read
  of local files; no connection, tunnel or simulator is touched.
* **Pruning fix.** `output.keep_last_checkpoints` promises "latest, final and best are kept", but `_prune` would
  have removed a best policy that is a periodic save. It now skips the selected best policy. Latent only: the
  setting is empty by default (no model is ever deleted automatically), no panel exposes it, and no best policy is
  ever selected yet.

**Verified.** `tests/workbench/test_wb_model_chooser.py` (5): the list is built without hashing a file; a frozen
run started from the OLDEST save point records that id and ends with exactly that save point's weight digest
(which differs from `latest`), i.e. the chosen model is the one that gets loaded; a run without a model, a
`.staging-` directory and a save point with unreadable metadata are never offered; the route, its 403 outside the
allowed roots and `include_mock=false`; pruning keeps the selected best policy.
`frontend/scripts/model_chooser_check.mjs` (headless Edge, 42 checks, 4 screenshots; the chooser's routes are
answered by FIXTURE data and every other writing request is refused, so it is safe against the live backend;
`GATOR_WORKBENCH_OUTPUT_ROOT` optionally names the folder for its last section) was run against a throwaway
backend on port 8766 that served a scratch build and three REAL MOCK runs with saved models: the last section
compares the cards with the real `GET /api/runs/models` (3 of 3; the run without a model is absent).
`tsc --noEmit` clean.

**Limits, stated plainly.** Only runs created by the workbench are listed: the M6 pilot checkpoints are bare
`SACLearner.save` files in another layout and still cannot be chosen (adopting them would be a separate,
read-only import). There is no browser upload of a model and none is planned: `training_state.pt` is a pickle and
is only ever loaded from a trusted local output root. The `other network` tag compares encoder / hidden / heads /
layers only; the compatibility report after selection remains the authority. No real (non-MOCK) model was loaded
by any of this.

### 7.21 Profile from a Virtuoso cell, increment 3a: everything up to the first costed run (2026-09-21 ~04:40, same session as 7.17 / 7.19, user: "go on")

"go on" does not authorize real simulator budget (project rule), so this increment is what stage 3 needs EXCEPT the
costed run itself. **RESTART THE BACKEND FIRST** (new module, two endpoints).

* **`profile_preflight.py` (new) - "Check against Virtuoso (no simulation)".** Everything the first real evaluation
  does before Spectre starts: the run adapter `connect()`s (creation receipt, existing tunnel, no ADE/Maestro
  window, the live cell == the recorded sizes), `generate_netlist()` exports the testbench, compares topology and
  every parameter with the record and writes the deck; then `close()`. Nothing is written to the cell (so nothing is
  restored), no simulator starts, no budget. Short-lived process; it takes the project's session lock
  (`artifacts/local/bridge-state/session.lock`), so it and a real run exclude each other; gate = the layer set of
  `write_cellview` (1-5). A failure is reported as the step that failed, never raised. `POST
  /api/virtuoso/profile/preflight {name, profile_id}`; results kept under `<profile>/preflight/<time>/`.
  **Run for REAL (read-only, zero-cost, no run active)** on a throw-away profile of the user's ring oscillator in
  a scratch settings folder: profile / connect / export / deck all passed in 1.5 s - the first time a GENERATED
  profile went through the real run adapter against the live cell. The deck is complete (`include
  .../gpdk045.scs section=tt`, the exported structure, `ic OUT=0 XU1.N1=1 XU1.N2=0`, `save VDD OUT XU1.N1 XU1.N2
  V0:p`, `tranNom tran stop=5e-08 maxstep=8.33333e-12 errpreset=conservative`). Not covered by it: Spectre itself,
  the license, the result files and the measurement on them.
* **`profiles.record_reference` - the finished baseline becomes the reference.** Read from the run's OWN tables:
  the raw backend metrics (`measurement_id` null) of the evaluation with phase `baseline`, only if it is real, came
  from a simulation, and every metric of the recipe is present and valid; the run must be one of `real:<name>`.
  Written to `<profile>/reference_measurements.json` (`origin: real`), after which `_generated_runtime` passes it
  to `NativeEnvironmentFactory` like the references of the four verified profiles, and the task lists as
  `verified`. Never replaced once recorded. `POST /api/virtuoso/profile/reference {name, run_dir?}` (without
  `run_dir`: the newest run of the task under the output root). Tested against crafted table rows; **never run on
  a real baseline, because none exists yet.**
* **The agent is told what a real backend measures and writes** (`api/app.py::_request`, no change in `agents/`):
  a draft's circuit data carries `results_by_circuit_type` and the limits (transistor widths only, single finger,
  m = 1, 5 nm grid, linear range containing the present width, leaders / followers for matched devices); a
  registered real task carries `results_provided`. Before this, the agent had to invent metric names and a profile
  made from its proposal failed validation. `create_profile` also refuses a measurement whose `source_name` the
  chosen circuit type does not produce, listing what it does.
* `tasks.generated_bridge_config` is the one place that builds the bridge configuration of a generated profile
  (runtime and preflight share it). `preload.MODULES` gained the four optimizer modules the new files import
  lazily (the guard of 7.11 caught it).
* Frontend: a generated task shows **Check against Virtuoso (no simulation)** with its four steps and the verdict,
  and - until a baseline is recorded - **Record the baseline run as reference**. `virtuoso_source_check.mjs`: 48
  checks pass (both buttons, the "run the baseline first" refusal, the recorded message).
* Tests: `test_wb_profiles.py` now 18 (measurement sources, agent hints on a draft and on a registered task, the
  check's gate / failed step / offline adapter refusal, the reference from a baseline and its four refusals).

**Still open, and only the user can open it:** one budget-authorized **Single baseline simulation** of their own
`real:<name>` task. Expected then: a transient of 60 expected periods, metrics `osc_frequency_hz` etc.; afterwards
"Record the baseline run as reference". If the measurement contract refuses the waveform (no sustained full-swing
oscillation in the window, or a frequency far from the expected one) the evaluation fails as a measurement error -
by design, never a made-up number.

### 7.22 Profile from a Virtuoso cell, increment 3b: a blocker found before the first baseline, and the measurement checked on real result files (2026-09-21 ~06:00, same session as 7.17 / 7.19 / 7.21, user: "leave it, go on")

Still no simulator budget (a bare "go on" does not authorize one). **RESTART THE BACKEND FIRST** (Python only; no
frontend change).

* **Blocker found and fixed: the RL specification registry.** A target's `metric_id` must be in the registry that
  lays out the policy's goal input; the default one (`SpecSchema()`) holds the six op-amp results and `score`. A
  target on `osc_frequency_hz` was therefore a `metric_not_in_registry` blocker whose advice ("add it under Run >
  Advanced > spec_registry") cannot be followed: the UI has no editor for the registry. The user's first baseline
  would have stopped there. Now a generated profile brings its registry: `recipes.spec_registry` (the results of the
  circuit type with fixed references of the right order - the expected frequency, 1e-4 W / A, the supply, the
  contract limits, the measurement start) is stored in `profile.json`, and `validation.registry_for` /
  `compile.build_spec_schema` use it when the configuration states none (`SpecSchema` version
  `spec-input-generated-profile-v1`). An explicit `spec_registry` still wins; other tasks keep the default; a cell
  without a profile skips the registry check (its registry comes with the profile). The agent is told that a
  target's `metric_id` must be one of the result names. Test
  `test_a_generated_profile_brings_the_result_registry_its_targets_need`: a generated ring-oscillator task with a
  frequency target in GHz and a power target in uW validates without blockers and compiles to two `MetricSpec`s.
  **The same gap exists for the verified `real:gpdk045_ldo` and `real:gpdk045_vco` tasks** (their results are not in
  the default registry either; the M6 experiment used its own registry from `configs/m6_real_cross_category.json`).
  Deliberately NOT changed here: those are verified tasks, and which registry they should share is a research
  decision (it fixes checkpoint compatibility).
* **The measurement, checked on REAL Spectre output (read-only, one-off, not a test: the files are local
  evidence).** (1) `GenericRingOscillatorProfile.analyze` replayed on the result files of a recorded real VCO
  simulation made through the same adapter (`artifacts/local/m6-vco-runtime/trial/1aaec733.../simulations/
  7ec6a755...`: `dcOp.dc`, `dcOpInfo.info`, `tranNom.tran.tran`, `spectre.out`; the evidence folder was only read,
  `measurements.json` went to a scratch copy): frequency 1.711607e8 Hz, supply power 2.661101e-5 W and duty cycle
  are IDENTICAL to what the verified VCO recipe recorded for the nominal transient; the nine operating points and
  the completion evidence were read. Swing and startup differ by design: the VCO recipe takes the worst of three
  control voltages, this recipe has one transient. (2) The PSF transient of the user's standalone ring-oscillator
  run, read with the same reader: 1.209225e9 Hz; the real `V0:p` current is negative when the source delivers
  power, as the recipe assumes (196.9 uW over the window).

What is verified on real data now: connect / export / deck against the live cell (7.21), result reading and
measurement (this section). **What is not: Spectre actually running the generated deck, and the license.**

### 7.23 "Save now": save the running run's model without pausing (2026-09-21 ~04:20, same session as 7.20, user: "add a save now button")

**RESTART THE BACKEND FIRST** (the API must accept the new command; workers start with the new engine anyway).

**Why.** A model was saved every N evaluations, at pause, at stop and at the end - but there was no way to keep
the model "as it is right now" without pausing the run.

**What changed.**
* **One new run command, `checkpoint`** (`runs.send_command`, `CommandBody`). The engine (`engine.py`,
  `_poll_control`) marks a save as due with kind `manual`; the scheduler then does what it already does for an
  automatic save: no new dispatch, wait until nothing is in flight, write the complete save point
  (`training_state.pt` + `model_weights.pt` + metadata, the same consistency boundary), go on. Nothing is charged.
  The request is answered in `status.json`: `manual_save = {id, state: waiting | saved, requested_utc,
  checkpoint_id, saved_utc, evaluations}`. ANY save written after the request answers it, so a pause that
  overtakes it leaves no request hanging. Events: `control` (command `checkpoint`) and `checkpoint_saved`
  (kind `manual`). Pruning only ever removes `periodic` saves, so a save made on request stays.
* **Refused with the reason (HTTP 409, `code`)** instead of silently doing nothing: `not_running` (a paused or
  ended run has saved everything), `already_stopping` (pausing / stopping saves by itself; the control file has ONE
  slot, so a pending pause, stop or cancel is never replaced by a save request), `checkpoints_off` (the run's own
  `effective_config.json` has "Model checkpoints" off). `/api/runs/command` now turns `RunRejected` into that 409.
* **Frontend.** Header (`RunControl.tsx`): "Save now" LEFT of the main button - Abort stays directly right of it, as
  7.18 pins - always rendered with a fixed width, enabled only while the phase is `running`; one press = one
  command, the phase and `pending` are not touched (the main button keeps reading Pause); it reads "Saving..." until
  the RUN reports this request's id as saved, then the line under the header says "Saved at N evaluations as save
  point <id>. The run goes on."; a refusal is shown as the backend worded it. Run status tab (`Bottom.tsx`): the
  same button next to "Pause and save", and the request in the "Last checkpoint" row. The model chooser (7.20)
  names the new kind: `saved with "Save now"`. No new polling: both places read the status the page already polls
  while a run is live.

**Verified.** `tests/workbench/test_wb_save_now.py` (6): a save requested at 8 of 30 evaluations is a complete
`manual` save point at one consistency boundary (ledger = data cursor = counters, files verify) and the run still
completes all 30; it survives `keep_last_checkpoints=1`; a pause sent right after it still pauses and answers the
request; the three refusals, with the pending pause / stop / cancel left in place; the 409 over HTTP and 422 for an
unknown command; and the whole path with a REAL detached MOCK worker over HTTP (saved while `running` and
`worker_alive`, evaluations keep rising afterwards, `/api/runs/models` lists the `manual` save point, then
`manual` + `stop`). The three timing-dependent tests were repeated 6 times: 18 of 18. Browser:
`frontend/scripts/save_now_check.mjs` (headless Edge, 24 checks, 5 screenshots, FIXTURE run, safe next to a live
run); `run_control_check.mjs` (7.18) and `model_chooser_check.mjs` (7.20) still pass unchanged. `tsc --noEmit` clean.

**Limits, stated plainly.** The save waits for the simulation in flight - on a real circuit up to one simulation
(about a minute), and with several jobs in parallel the idle lanes wait for the slowest one. A run started with
"Model checkpoints" off cannot be saved at all. MOCK backend only: no real run was saved this way yet. Nothing
under `src/analog_optimizer/` changed.

### 7.24 FIRST REAL SIMULATION through the workbench: a generated profile's baseline - and the bug that had made every real task unrunnable (2026-09-21 ~05:20 local, same session as 7.17-7.22)

Budget: the user authorized **exactly one** real Spectre evaluation (asked explicitly; a bare "go on" had been
refused three times). Spent: **1 evaluation, 1 simulator launch, 0 retries.**

* **Bug found by the first attempt, fixed, tested: no real task could ever run from the workbench.** A real lane's
  backend (`NativeCandidateBackend`) needs the optimizer's preparation service - the ONE owner of the Virtuoso
  session - which `NativeEnvironmentFactory.preparation_context` starts and which the optimizer's own training
  loop enters before it opens a lane. `engine.py` called `open_lanes(factory, ...)` directly, so the first lane
  died in `connect()` with `'NoneType' object has no attribute 'baseline'`. This concerns ALL real tasks, the four
  verified ones included ("real backend wired" in section 3 was never exercised). The attempt failed BEFORE
  anything touched Virtuoso or Spectre: ledger `charged 0, launches 0`. Fix: `RunEngine._prepare` enters
  `factory.preparation_context(WorkerLimits(), report)` when the factory has one (exactly as
  `training/parallel.py` does) and `_finalize` closes it AFTER the lanes, reporting a restoration state other than
  `restored` as a problem. `tests/workbench/test_wb_engine_preparation.py` (new, 3): the context brackets the lanes;
  an unrestored schematic is reported; a factory without the context runs as before.
* **Correction of a statement made to the user.** "A baseline writes nothing to the cell" was WRONG: every
  candidate, the baseline included, goes through `preparation.prepare` -> `set_parameters` -> `set_gpdk_mos`, which
  opens the core cellview for edit, re-applies the widths through the PDK callbacks, runs `schCheck` and `dbSave`;
  at the end the owner writes the initial widths back. For the four verified profiles that is by design (their
  cells were created for this). **A generated profile writes into the user's ORIGINAL cell.** The user was asked
  again with the corrected facts and chose to run on the original cell. Working-copy mode (profile creation copies
  cell + testbench and runs touch only the copies, as the spec's "never overwrite the original design" asks) is
  NOT built; it is the main open design point of generated profiles.
* **The run** (throw-away profile `ring_osc_trial` of `GPDK045_RINGOSC/ring_osc_3stage` in a scratch settings
  folder; `max_evaluations = 1`, `max_spectre_launches = 1`, `max_retries = 0`; `cli run --authorize-real
  --acknowledge-unknown-connection`): **completed in 17 s.** Baseline evaluation real / simulation / valid / 1
  attempt, 7.1 s execution: `osc_frequency_hz` 1.2091976e9 (the user's standalone run: 1.209225e9),
  `supply_power_w` 1.9632e-4, `supply_current_a` 1.9632e-4, swing 0.99917 V, duty 0.50790, period spread 1.3e-6,
  window drift 7.7e-8, startup 7.2e-9 s. Both targets (>= 1 GHz hard, <= 400 uW soft) satisfied; event
  `first_feasible`. Events: `preparation_service_started`, `segment_started`, `first_feasible`, `segment_ended`.
* **Safety, checked around it:** before the run only the CIW log window was open (the cell was in no window); a
  full readback of the cell before and after is IDENTICAL (masters, nets, every CDF parameter, positions); the
  adapter's session journal ends with `restoration.json: restored`.
* **`record_reference` on REAL tables:** the baseline became the trial profile's reference
  (`reference_measurements.json`, `origin: real`), and the task then lists as `verified`.
* **Connection gate, first real use of layers 6-7:** `spectre` ok; `spectre_license` is `unknown /
  license_not_checkable` on this host ("lmstat missing or no matching feature listed"), so every real start needs
  the explicit acknowledgement of the unknown layer (the UI asks; the CLI has `--acknowledge-unknown-connection`).
* Evidence (git-ignored): `artifacts/local/generated-profile-first-baseline/` - both run directories (the failed
  first attempt and the run), the trial profile, the configuration, the before/after readbacks, a README.

With this, the chain "cell in Virtuoso -> read into the workbench -> Create profile -> check without simulating
-> real baseline -> recorded reference" has run end to end once, for one circuit type (free-running ring
oscillator). Not done: an optimization run (more than one evaluation, i.e. widths that actually change) of a
generated profile; the op-amp recipe on a real cell; working-copy mode.

### 7.25 Agent: "Make it startable with the fewest changes" + a truthful start check for verified real circuits (2026-09-21, same session as 7.16, explicit user request)

Request: "can the agent help modify everything as few as possible for the whole run to be able to start?" Until now the
`readiness` request assumed nothing, so with empty tables it answered with questions instead of rows.

| Piece | Where |
|---|---|
| Request kind `minimal_start`: the smallest edit of the three tables after which the run can start. **Enforced, not just asked for:** `proposals.normalize()` rejects a replace/remove of any row that carries no blocking issue (`changeable_rows` in the readiness report, worked out from the complete issue list; `'*'` for a section-level issue). Adding stays allowed; whether a row was NEEDED is the brief's rule | `agents/base.py`, `agents/proposals.py`, `agents/readiness.py` |
| Provisional values, only from data the agent was given: a variable's range around the present value in the circuit data; a hard threshold as "no worse than the design as it stands" from `initial_design_results` - the verified REAL baseline, now exposed as `TaskRuntime.reference_metrics` (hand-written profiles: metrics + units; generated profiles: their recorded reference) and added to the circuit summary. Never a typical value from general knowledge; without such a number the target stays missing. Every such row: `basis` starts with `PROVISIONAL:` and a warning names it | `tasks.py`, `api/app.py` (`_request`), `agents/run_readiness.md`, `agents/prompts.py` |
| `readiness_after` on EVERY proposal (agent or manual import): the backend applies the patch to a copy, re-runs the start checklist and reports `ready`, what it resolves, what remains, rows changed. The workbench's verdict, never the agent's claim | `api/app.py` (`readiness_after`) |
| UI: on the checklist card "Make it startable with the fewest changes" (primary) and "Fix only what needs no assumption" (the old strict request); next to the diff a yellow box listing every PROVISIONAL row and the line "After you approve: nothing blocks a start" / "still missing: ..." ("Checked by the workbench, not by the agent"); `minimal_start` is a selectable kind | `frontend/src/panels/Bottom.tsx`, `styles.css` |

**Defect found by the first real request and fixed here (it predates this work).** For `real:gpdk045_ota5` the agent proposed
one provisional variable; static validation and `prepare_run` accept that, but a verified real profile fixes its
parameter groups and `engine.py` compares `graph_contract(compiled.graph)` with the profile only when the WORKER starts -
after the budget authorization - and refuses ("A real profile fixes its writable parameters and legal grid"). So the
checklist (and the new verdict) would have said "ready" for a run that dies at once. Now: `tasks.profile_parameter_rows()`
writes the rows a real profile fixes from its own parameter groups (same mapping as `starter_config`; they compile to an
identical contract for all four verified circuits: ota5 5 rows, ota7 7, ldo 3, vco 3), `run_readiness` compiles offline and
compares, the checklist reports a mismatch or an uncompilable configuration as missing ("would be refused the moment it
starts"), and the rows go to the agent as `required_parameter_rows` to be copied unchanged (not provisional). No bridge
contact in any of this.

Verification: `test_wb_agent_readiness.py` 16 tests (7 new). Full `pytest tests/workbench -q`: 357 passed, 1 failed -
`test_wb_preload.py::test_every_lazy_optimizer_import_is_preloaded`, caused by another session's import that was being
added to `preload.MODULES` while the run was in flight (the import this work adds, `analog_optimizer.envs.sizing`, was
already listed); re-run afterwards together with the agent and API files: all pass. Browser check `agent_tab_check.mjs` 68 checks, all pass (both
buttons, one request of kind `minimal_start`, verdict line, provisional box). **Two real requests** through a scratch
backend (port 8768, own settings directory + a copy of the connection file, `sonnet` / effort `low`, `real:gpdk045_ota5`
read from local files only - no bridge contact, no simulation): before the fix 3 rows incl. a made-up variable ($0.23);
after it 7 rows = the profile's 5 variable rows copied exactly + ONE provisional target (`gain_db_at_start >=` the recorded
baseline 25.0 dB) + its measurement, `readiness_after.ready = true` with the profile comparison included ($0.25, 42 s).
NOT verified: that such a run then really starts - that needs the user's connection test and budget authorization.
Python changed: the running backend needs a restart. Uncommitted.

### 7.26 Network structure of a saved model, as a table (2026-09-21 ~05:30, same session as 7.20 / 7.23, user: "go, build the structure table")

**RESTART THE BACKEND FIRST** (one new read-only route; two more modules in the preload list).

**Why a table.** The user asked whether the model can be visualized. The specification forbids plots and plotting
libraries, so the first step is the one that needs neither: what the saved network consists of, layer by layer. A
picture of the circuit graph with attention on it stays a separate decision of the user (it would relax that rule).

**What changed.**
* **`src/gator_workbench/model_structure.py` (new)**, `POST /api/runs/model/structure` (`run_dir`, `checkpoint_id`;
  403 outside the allowed roots, 404 unknown save point, 409 when `model_weights.pt` does not match its recorded
  checksum). Tensor-only: `model_weights.pt` is loaded with `weights_only=True` after the checksum matched. One row per
  layer that owns tensors: section (Inputs / Block n / Read-out / Output), path, type, shape ("in -> out", "entries x
  width", "over n"), parameters, share, a plain line on what the layer does (written from
  `CircuitEncoder.forward`), for the actor and for one critic (both critics and both target copies are checked to have
  the same tensors). Totals: trained = actor + 2 critics + 1 (entropy temperature); saved = trained + 2 target copies.
* **Nothing is guessed.** Types and the never-used flag come from REBUILDING the network from the contract recorded in
  the save point (feature schema, goal/spec schema, model config) and are reported only when the rebuilt network holds
  exactly the saved tensors, names and shapes (`types_verified`); otherwise every tensor is still listed, without
  types, and the reason is said. "Never used" is decided on the rebuilt module (`TransformerConv` with
  `root_weight=False` still owns `lin_skip`), never on a name.
* **Preload.** The new lazy imports (`analog_optimizer.models.encoders`, `.graph_transformer`, `torch_geometric.nn`)
  were added to `preload.MODULES`; the guard of 7.11 (`test_wb_preload.py`) had caught them - reported by the parallel
  "Connction Module" session from a full-suite run.
* **Frontend**: `frontend/src/panels/ModelStructure.tsx` (new), in `RunPanel` under the facts of the chosen model. A
  fold-out that reads nothing until it is opened, stays open while another save point or model is chosen (and then
  re-reads), asks for the RESOLVED save point, and shows: the trained / saved totals in plain words, a note when
  parameters are never used, one small section table per network (fits the 340 px panel) and **Full layer table**, a
  native `<dialog>` 1180 px wide with every layer, the never-used row marked and a total row. Tables only: no canvas,
  svg or image, no new dependency.

**Found on the way.** For graph_transformer 16/2/1: 272 of the actor's 7,314 and of each critic's 8,369 parameters are
`lin_skip` weights that are never read (816 of 24,053 trained) - the same effect `docs` already note for the equal-size
ablations, now visible per model. And `encoder.binding_ratio` gets a gradient that is exactly ZERO on the MOCK opamp,
because every group ratio there is 1 and the layer multiplies log(ratio): used, but without effect on such a circuit.
It is deliberately NOT flagged (data-dependent, not structural); the test documents the difference.

**Verified.** `tests/workbench/test_wb_model_structure.py` (9): the rows are exactly the saved tensors of a real MOCK
save point, with types, shapes and sums; for ALL six encoders one real forward + backward pass of policy and critic
on a real observation - the layers whose weights get no gradient object are exactly the flagged ones (`lin_skip` x
blocks for graph_transformer, none elsewhere) and every layer has a section and a plain line; types are dropped when
the rebuild fails or has another size; a changed weights file is refused; the route with 404 / 403 / 422.
`frontend/scripts/model_structure_check.mjs` (headless Edge, 34 checks, 5 of them against the real route, 3 screenshots;
FIXTURE data, every other writing request refused, safe against the live backend) was run against a throwaway
backend on 8766 with a scratch build and REAL MOCK save points: the page's numbers equal the real route (24,053
trained = 7,314 + 2 x 8,369 + 1; 25 + 27 layers, all typed and explained). `model_chooser_check.mjs` still passes;
`tsc --noEmit` clean.

**Limits, stated plainly.** It describes what is SAVED, not what the network does on a circuit: no activations, no
attention, no comparison between save points. Counts are of the workbench's networks as built today; a save point
written by another source version may come without types. MOCK save points only were read; a real one has the same
file format. Nothing under `src/analog_optimizer/` changed.

### 7.27 Agent conversation: the detach control moved onto the tab (2026-09-21, same session as 7.14, explicit user request)

Request: "move the detach to its window button onto the tab 'agent conversation' button, like closing browser tab style".
Frontend only. The "Agent conversation" tab of the bottom strip is now one tab shape (`.tab-group`) holding two SIBLING
buttons - its label and, at the right end where a browser tab has its close button, a 13 px pop-out icon (`.tab-detach`,
inline SVG, `aria-label` + tooltip). A button inside a button is not valid HTML, hence siblings. `App.tsx` only offers a
slot (`<span class="tab-slot">`, handed over as `tabSlot`) and keeps a `detached` flag for the tab's look
(`onDetached`); `AgentTab` draws the control into the slot through a portal, so all detach logic stays in one place.
Pressing it detaches WITHOUT switching the bottom tab; while detached the label is italic/muted and the same control
reads "Bring the conversation back into this tab" (a fourth way back besides the button inside the detached window, the
note in the panel, and closing that window). The old full-width button in the left column is gone; inside the detached
window, which has no tab strip, "Bring back into the workbench" stays.

Verification: `npm run build` passes; `agent_tab_check.mjs` 71 checks, all pass on a scratch backend (control is on the
tab, right of its label, not nested in another button, old button gone; detaching from "Run status" leaves that tab
selected; the tab shows the detached state; the control brings the conversation back complete). Test-only finding: the
editors have a `.tabs` strip too, so bottom-strip selectors must start at `footer`. Page refresh only. Uncommitted.

### 7.28 Agent tab wording (2026-09-21, same session as 7.27, explicit user request)

Three text changes, frontend only: the bottom tab "Agent conversation" is now "Agent"; the message box no longer says
"Enter sends, Shift+Enter starts a new line" (the keys work as before); the notes side window no longer explains itself
before the first reply ("What a reply lists besides its text appears here instead of in the chat") - it shows its
heading only. The detached window keeps its title "GATOR - agent conversation". `npm run build` passes;
`agent_tab_check.mjs` 72 checks, all pass on a scratch backend. The check script now retries its settings snapshot and
refuses to start without one (a run had silently skipped the restore step when that first read failed once). Page
refresh only. Uncommitted.

### 7.29 Agent tab: the selected rows on a click; the send button removed (2026-09-21, same session as 7.28, explicit user request)

Frontend only (`Bottom.tsx`, `styles.css`; one tooltip in `Left.tsx`).

* **`modify_fields`: "N selected row(s)" is now a control.** A press lists the rows the request may change, one line
  each: row ID, its table, what the row is now (a handful of identifying fields per table - `ROW_FACTS` - with short
  numbers, `1e-6` instead of `0.00000100000`) and what may change (the chosen fields, or "the whole row"); a row that
  has since been deleted says so. A second press closes it; with no selection it says how to make one. The list
  scrolls itself into view, because the message-box column scrolls. It belongs to `modify_fields` only.
* **"Ask agent for a proposal" is gone.** Enter in the message box sends (unchanged, IME-safe); while a request is
  out the row still offers "Cancel request" and the conversation shows the waiting line. The tooltip of "Ask the agent
  for suggestions" in the circuit panel said "until you press Send there"; it now says "press Enter in its message box".

Verification: `npm run build` passes; `agent_tab_check.mjs` 76 checks, all pass on a scratch backend. The check now
seeds the page with the `synthetic:opamp` starter (through `Page.addScriptToEvaluateOnNewDocument`), so rows can be
ticked in the editors and brought over with "Modify selected with agent..." as a user would. Page refresh only.
Uncommitted.

### 7.30 Project panel: long explanations folded into "details" lines; "Native schematic" closed by default (2026-09-21 ~14:00, separate session, explicit user request)

User request: "hide the long comments or assisting texts into a collapsing notation text just like the Hierarchy
module instances and parameters and native schematic", and "the native schematic sector is expanded by default,
change that to collapsed by default". Frontend only (`Left.tsx` `CircuitPanel`, two lines at the end of `styles.css`).
The column is 300 px wide, so every sentence ran over three to five lines and the fields and buttons were pushed out
of view; the Virtuoso browse state is now 912 px tall folded against 1324 px with everything unfolded.

* **The rule:** an explanation becomes a closed `<details className="more">` line - the same notation as "Instances and
  parameters" - directly under the sentence it explains. Headlines, warnings, errors, results and every button stay in
  view; nothing was deleted, only folded. Deliberately left in view: the MOCK / REAL backend banner (the REAL one is
  the cost statement), "Profile ... created", the missing-baseline warning, all `error` / `blocker` texts.
* **The nine lines:** "Which two files, and where they may be" (netlist source; one short line stays: "Two files are
  needed: fill in both paths, then press Load netlist."), "View: schematic" (why there is no view to choose), "What
  circuit class and PDK id are for", "Why: it has no circuit profile yet" and "What reading the cell does" (browse-only
  note; "N circuits have a profile today" + the task buttons + "Read this cell into the workbench" stay), "What you can
  do with it now" and "What Create profile does" (draft note; both buttons and the profile form stay), "What the check
  does" (generated profile; both buttons stay), and the backend's `circuit.notes` as one line "N note(s) on this
  circuit".
* **Native schematic** is closed by default. It is controlled (`nativeOpen`, the `ModelStructure.tsx` idiom) because a
  new cell or Refresh re-mounts it: once the user opens it, it stays open from cell to cell, and stays closed once
  closed. The folded help lines are plain uncontrolled `<details>`: a line keeps its state while it is on screen.
* `styles.css`: `details.more` (small margins, content indented under its line) and a pointer cursor for every
  `summary` of the left column.

Verification: `tsc --noEmit` and `vite build` pass. New `frontend/scripts/project_help_check.mjs` (headless Edge,
port 9393, 35 checks, 5 full-height screenshots): "folded" means the words are in the page but `checkVisibility()` is
false, "in view" means it is true - `textContent`, which the two older checks read, cannot tell the difference. It is
hermetic and safe against the live backend: every `/api/virtuoso/*` call is a canned FIXTURE, GETs, the circuit load of
a registered task and static validation pass through, every other writing request is refused (the page's own
`POST /api/output/check` is the only one and is reported as INFO). The connection profile is seeded into the
temporary browser profile's configuration (`run.connection_profile_id`), so the check does not depend on the
connection UI, which a parallel session was rebuilding at the time. It passed against a scratch build served by
`vite preview` on a side port (API proxied to 8765; the build must sit on a Windows path, a `\\wsl.localhost` out-dir is
served empty) and against the live page. `circuit_source_check.mjs` 21 of 21; `virtuoso_source_check.mjs` 47 of 48 -
the one failure ("and says what to do") expects the words 'connection panel', which the parallel connection refactor
reworded to 'Connection window'; that session was told. Page refresh only, no backend restart. Uncommitted.

### 7.31 Exports of the four run tabs: five gaps closed (2026-09-21 ~14:00, separate session, user: "close all five gaps")

The user asked whether Run status, Logs, Data tables and Output files can export. Answer of record before this
change: Data tables and Output files could, Run status and Logs could not, and three of the existing exports were
awkward. The five gaps, all closed:

1. **Logs had no download.** New button "Download full log (events.jsonl)" (or `errors.jsonl`, following the
   selector) next to the list, and a hint that the list is only the newest 200 entries. A healthy run keeps an
   EMPTY `errors.jsonl`: the tab then says "Nothing to download: this run has logged no errors so far." instead of
   saving an empty file (decided from the entries the tab already holds, checked to be of the selected kind; a 404
   reads the same).
2. **Run status had no export.** New button "Export status (JSON)" at the end of the tab's button row: the status
   object the tab is drawn from (state, budget, best design, connection, manifest, summary) plus `exported_utc`, saved
   as `<run folder>__status.json`. Frontend only, no request.
3. **"Export detailed CSV" only wrote a file on the backend's disk** and showed its path; the user had to go to
   Output files, Refresh and download it. It now does both: writes `exports/<table>__seq<N>.csv` (+ `.meta.json`) as
   before and hands the browser the same file at once. The note reads "Downloaded ... Also kept in the run folder: ...".
4. **"Export research CSVs" could not be reached from the browser at all**: the aggregates lie in
   `<experiment>/aggregates`, ABOVE the run directory, where `/api/runs/download` (rightly) cannot reach. New route
   `GET /api/aggregates/download?run_dir=...`: one zip `<experiment>__aggregates.zip` of exactly the files the exporter
   writes (`<table>.csv` + `<table>.meta.json` for the six tables of `aggregates.COLUMNS`; a stray file in that folder
   is not packed, a symlink neither), 404 "No research CSVs have been exported for this experiment yet" before the
   first export. The button writes (existing `POST /api/aggregates/export`) and then downloads.
5. **Every data-only package was saved as `run__data.zip`**: the frontend hard-coded the name and so discarded the
   backend's `<run folder>__data.zip`. All downloads now go through one helper, `download()` in `api.ts`, which saves
   under the name of the backend's Content-Disposition (plain and RFC 5987 `filename*=` form), throws the backend's
   readable message on an error (the old `downloadPackage` lost it and its caller did not catch at all) and returns the
   name for the tab's note. The per-file `download` links of Output files stay plain links on purpose: they stream to
   disk, and a saved model can be hundreds of MB, which a fetch-into-memory download should not hold.

**A defect found on the way and fixed: a file that grows while it is downloaded.** `/api/runs/download` answered with
starlette's `FileResponse`, which announces the size first and then reads to the end of the file. A live run appends
to `logs/events.jsonl` all the time, so the body no longer matched the announced length and the transfer broke -
exactly the case the new Logs button is for. New `file_snapshot()` in `api/app.py`: the size is taken once from the
open file, exactly that many bytes are sent, and a `.jsonl` is cut back to its last complete line (the project's own
rule: a torn tail is not part of the record, see `read_jsonl`). Measured over real HTTP (uvicorn) against a log that
was being appended to ~2000 times per second: new route 922 of 922 downloads complete, none ending mid-line;
`FileResponse` on the same file 0 of 52 (`IncompleteRead`). What was given up: ETag / Last-Modified / Range support of
`FileResponse`, none of which the workbench uses. `attachment()` next to it builds the Content-Disposition for all
three download answers' names (non-ASCII experiment names included).

Files: `src/gator_workbench/api/app.py` (`attachment`, `file_snapshot`, the download route, the new aggregates
route; the `FileResponse` import went), `frontend/src/api.ts` (`save`, `download`, `aggregatesUrl`;
`downloadPackage` / `saveJson` are now one-liners over them), `frontend/src/panels/Bottom.tsx` (`StatusTab`,
`DataTab`, `FilesTab`, `LogsTab`, `runName`; the Agent tab above them is another session's and was not touched),
`tests/workbench/test_wb_api.py`, `docs/workbench.md` ("Getting a run's data out of the browser"). Nothing under
`src/analog_optimizer/`. Nothing happens on its own: every export is a button press; the exports show "Exporting..." /
"Packing..." and cannot be pressed twice.

Verification: `tests/workbench/test_wb_api.py` - two new tests (`test_a_download_is_the_file_as_it_was_when_the_
download_started`: snapshot taken, file appended to, body still the earlier complete lines; torn tail longer than one
64 KiB scan block; no complete line = empty body; a non-JSONL is not cut; missing file 404; the `filename*=` form;
`test_research_csvs_are_downloadable_as_one_zip`: 404 before the export, 12 members after it, a stray file left
out, the experiment's name in the header, 403 outside the roots) and three assertions added to the existing run test
(the exported CSV comes back through the download route with its header row; the package is named after its run).
Full workbench suite: 428 passed. `tsc --noEmit` and `vite build` pass; `save_now_check.mjs` and `run_control_check.mjs` (same Run status tab) still pass. New `frontend/scripts/export_check.mjs` (headless Edge, port 9391, 22
checks, 4 screenshots): NOT hermetic on purpose - it starts one 12-evaluation synthetic MOCK run on a SCRATCH backend
(it refuses port 8765), presses every export button with a real user gesture, and reads the files the browser SAVED
back from its download folder (`Browser.setDownloadBehavior`): names, the status JSON's content, one JSON object per
log line and as many lines as the API lists, header + every row in the CSV, the 12 members of the aggregates zip (zip
names read from the central directory; node has no zip reader), the package's name and members, "Nothing to download"
with no file saved and the page still the workbench. It caught two things type-checking could not: the empty
`errors.jsonl` of a healthy run (gap 1 above), and that the hidden-but-mounted Agent tab owns the first `<select>` /
`.hint` of `.bottom-body` - the check finds everything from the visible tab's own button.
Live page: `frontend/dist` rebuilt, a page reload shows the buttons. **The backend on 8765 must be restarted** for the
research-CSV download (new route; until then that button says "Not Found" after writing the files) and for the
growing-file fix; the other four work against the old backend. Uncommitted.

### 7.32 "Connection": one button that opens a window; four kinds of connection - Virtuoso over SSH / on this machine, ngspice on this machine / over SSH (2026-09-21 ~14:15, separate session, explicit user request)

User: "Change the virtuoso bridge connection to connection. Consider the possibility of connecting virtuoso locally and
connecting ngspice input locally or on ngspice ssh", then: "reduce the connection block to one button. Pressing it open
the current connection block as a new window".

**What changed for the user.** The block of the left column is ONE button, "Connection": first line the name and the
state of the last test, second line the connection in use and its kind ("lab - Virtuoso over SSH"). Pressing it opens the
connection window (a browser window of its own, drawn through a React portal - the mechanism of the detached Agent
conversation, 7.14 - so all state stays in the always-mounted button component and nothing is synchronised between
windows). Pressing again brings the window to the front; closing it loses nothing; a page reload closes it. The window
holds what the panel held, worded after the KIND of the chosen connection, plus "Add a connection...".

**Kinds** (`"kind"` of a profile in `bridge_connection.json`; absent = `virtuoso_ssh`, so existing files are untouched
and keep working):

| kind | layers | steps |
|---|---|---|
| `virtuoso_ssh` | the seven of section 2.1 | 1 Connect SSH, 2 CIW line, 3 Test |
| `virtuoso_local` | the same seven, `tunnel` = `not_applicable` | 1 Set up local bridge, 2 CIW line, 3 Test |
| `ngspice_local` | `connection_profile`, `ssh` (n/a), `ngspice`, `trial_run` | Test |
| `ngspice_ssh` | the same four | Test |

* **Virtuoso on this machine was already half there** (the bridge's local mode; `run_layers` and `perform_connect` handled
  it since 7.3) but the UI and every sentence said SSH. Now: a declared kind must agree with the bridge env file
  (`connection.kind_problem` -> `kind_mismatch` at layer 2 and in the connect process BEFORE anything is started: a profile
  that says "this machine" can never open a tunnel to another one); a profile without a kind is not second-guessed and
  the window words itself after what the test found (`describe()` -> `transport`). A local bridge that was never set up
  is `local_bridge_not_set_up` ("click Set up local bridge"), no longer `no_response` ("load the line" - there is none
  yet). `summarize` has local sentences without the word SSH.
* **ngspice** lives in the new `ngspice_link.py`, so `connection.py` keeps the guarantees its test pins. Same contract:
  dependency order, the broken link named, downstream `not_checked`, observe only. The `trial_run` layer solves ONE fixed
  divider (v(out) = 0.5 V) - to ngspice what the `1+1` round trip is to the CIW; never a user circuit, no budget, no
  license; local run in a temporary folder, remote run through `mktemp` + `rm` in one fixed command. `ssh_host` /
  `ngspice_bin` come from the operator's file only, must match a strict pattern before anything runs (an ssh OPTION such
  as `-oProxyCommand=...` in place of a host is refused at layer 1), travel as argv entries after `--`, and are scrubbed
  from ssh's own error lines. BatchMode; no ControlMaster, nothing left running.
* **Monitor and gate work per family** (`FAMILY_LAYERS` / `FAMILY_SCOPES` / `FAMILY_ACTIONS`): never-checked, stale,
  timeout and unparseable results carry the layers of the profile's own family; a result of another kind is not shown
  for a rewritten profile; an unknown kind is named by the probe without probing anything. **An ngspice connection can
  only be tested today** - there is no ngspice evaluation backend - so the gate refuses `real_simulation`,
  `read_cellview` and `write_cellview` on it WITHOUT a probe (`blocking: ["connection_kind"]` + the sentence to show; the
  refusal is logged), `tasks.real_backend_blocker` / `generated_backend_blocker` name the wrong kind instead of listing
  missing Virtuoso settings, `POST /api/connection/connect` answers `409 nothing_to_connect`, and the window says it in a
  neutral note. The switch for the later increment is one line: `FAMILY_ACTIONS['ngspice']['real_simulation']`.
* **Add a connection.** `detect_setup()` reports per kind what is on the backend machine (bridge env file + package,
  `ngspice`, `ssh`, the Host NAMES of `~/.ssh/config` - names only). `POST /api/connection/profile` takes
  `{profile_id, kind, ssh_host?, bridge_profile?}`; `ssh_host` must be one of those Host names, so section 2.1's "no host
  from the browser" still holds (an address, port, path or command is a 422; a well-formed name that is not in the file a
  409). **Deliberately relaxed promise:** the connection file was "never overwritten" (7.3); now a connection can be
  ADDED. Existing connections are never changed or removed, all other keys and `active` are written back as they were,
  the previous file is kept as `bridge_connection.json.before-<UTC>-<name>`, an existing name is `409 profile_exists`, a
  file that cannot be read is never replaced. The user's real `lab` file was not touched by any of this work.

**Files.** New: `src/gator_workbench/ngspice_link.py`, `frontend/src/panels/Connection.tsx`,
`tests/workbench/test_wb_connection_kinds.py`. Changed: `connection.py`, `bridge_connect.py`, `api/app.py` (body
`CreateConnectionBody`, the three routes), `tasks.py` (two blockers), `agents/readiness.py` + `agents/run_readiness.md`
(the checklist item is called "Connection"), `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/panels/Left.tsx`
(the panel moved out; three messages now point at the Connection window; a gate blocked by `connection_kind` shows the
backend's sentence), `frontend/src/styles.css`, `frontend/scripts/connection_panel_check.mjs` (rewritten),
`frontend/scripts/virtuoso_source_check.mjs` + `agent_tab_check.mjs` (two expectations / one fixture label),
`tests/workbench/test_wb_connection.py` + `test_wb_bridge_connect.py` (the three assertions whose behaviour changed on
purpose), `docs/workbench.md`. Zero edits under `src/analog_optimizer/`.

**Verification.** Fixture tests: `test_wb_connection_kinds.py` (kinds, mismatch, local wording, every broken ngspice
link, hostile settings, monitor/gate per family, creation, API) with the two older connection files, all passing.
REAL, reported apart from fixtures: (a) `ngspice_link` against a real **ngspice-36** - an Ubuntu package unpacked into
the session scratchpad, NOT installed on this machine - all four layers ok, and the remote command line executed under
a real `sh` with that ngspice (no temp file left behind); (b) this host as it is: `ngspice_not_found`, and an ssh target
that does not resolve: `ssh_failed` with the host scrubbed; (c) browser: `connection_panel_check.mjs` against a scratch
backend on another port with its own settings folder - one button, the window, the four kinds, names-only creation, no
request on page load / on opening the window / in two 17 s quiet periods, one check per press - plus its LIVE section:
real routes, real probe process, real ngspice-36 -> "Connected: ngspice 36 on this machine answered and solved the
built-in test circuit". NOT verified for real: `ngspice_ssh` over an actual SSH connection (this host has no
`~/.ssh/config` and nothing was contacted), and `virtuoso_local` against a Virtuoso on this machine (there is none; the
user's link is remote) - both rest on fakes plus the real pieces named above.

**Open.** An ngspice evaluation backend (decks, parameter substitution, measurements, budget rows) is a separate
increment and needs a user decision first: the GPDK045 models are Spectre-format files, so ngspice needs circuits whose
models it can read. Editing/removing a connection is still a hand edit. The pop-out code is now in two places
(`Bottom.tsx`, `Connection.tsx`); `Bottom.tsx` carried another session's uncommitted work, so it was not refactored into
a shared helper. Live page: `frontend/dist` rebuilt. **The backend on 8765 must be restarted** for the kinds (until then
the window works as Virtuoso over SSH with the old routes and says so under "Add a connection..."). Uncommitted.

### 7.33 Circuit graph view - the ONE on-screen picture - and a red Abort button (2026-09-21 afternoon, same session as 7.20 / 7.23 / 7.26, user: "go, make the abort button red and build the circuit graph view")

**RESTART THE BACKEND FIRST** (one new read-only route).

**A user decision that relaxes the specification, recorded as such.** The specification says "Do not introduce
plotting libraries ... Do not plot." The user was told exactly that (7.26: the graph picture "stays a separate
decision of the user") and decided: build it. Scope of the exception, kept narrow on purpose: ONE diagnostic picture,
ON SCREEN only. Nothing drawn is written into a run folder, an export or a report (the API test compares every file
of the run before and after); the OUTPUTS stay data-only and the page header still says so truthfully. No charting
library: cytoscape 3.34.3 draws node-link graphs (MIT, exact pin, no transitive dependencies, frontend only). It is a
separate 444 KB file that the browser fetches when the view is opened; the page itself does not grow by it.
`frontend/package.json` and the first paragraph of `docs/workbench.md` no longer claim "no library": they state the
exception.

**What it shows.** Devices as boxes, nets as circles (supply on top, ground at the bottom), every connection as a line
labelled with its terminal. Line thickness = attention on that connection for the chosen block / head / direction;
a device whose size the policy sets has a blue border and reads "w 1.768 um -> 3.115 um" (now -> proposed). Tables
beside it: sizes now / proposed by this save point / really tried by the run; the connections of a clicked device
with attention and uniform share; the metrics of that state.

**Where the numbers come from - nothing is simulated.** `src/gator_workbench/graph_view.py` (new),
`POST /api/runs/model/graph-view` (`run_dir`, `checkpoint_id`, `evaluation`): the chosen save point (tensor-only read
after the checksum matched; network rebuilt from the recorded contract and required to hold exactly the saved
tensors, as in 7.26) is REPLAYED on a state its own run ARCHIVED - the exact observation before evaluation N,
rebuilt by `TrajectoryLoader`. One forward pass of the actor on the CPU. So it costs no budget and works for MOCK and
REAL runs alike; a run without a transition archive is refused in plain words (409). Default N = the last evaluation
the save point had seen.
* **Attention without touching `src/analog_optimizer/`**: a forward hook on each `TransformerConv` / `GATConv` repeats
  that layer's own computation on its own inputs with `return_attention_weights=True` (dropout 0: deterministic). The
  network's directed edge list is folded back onto physical connections by (device, net, terminal role, ordinal), both
  directions kept: "what the device takes from the net" and "what the net takes from the device".
* **Honest reading, built in.** Attention is a softmax PER RECEIVING NODE, so a node with one connection always reads
  1.0: such lines are drawn thin and dashed, and every value is shown with its uniform share 1/k. The text next to the
  picture says that attention shows where the network looked, not why it chose an action - a debugging aid, not
  evidence. Nothing here supports or weakens any claim about graph transformers.
* **Frontend**: `frontend/src/panels/CircuitGraphView.tsx` (new), a button under the structure fold-out, a large native
  `<dialog>`. Nothing is asked and cytoscape is not loaded until it is opened; another block / head / direction or
  hiding the bulk ties repaints without a request; another evaluation (box + Show, `<`, `>`) is one request. Layout:
  breadth-first from the supply nets, then ground moved below everything; "Spread out" (force-directed from the current
  positions) and dragging for the rest. SI prefixes only for physical units (the MOCK score is not "855 mfixture").
* **Findable in every Mode (user: "where is the circuit graph view").** The button sat inside the block that only
  exists when Mode loads a model, so in `scratch` - the default - it was invisible. Now `scratch` shows **Look at a saved
  model**: the same chooser, headed "Saved models (look only)", with the structure fold-out and the graph view for the
  chosen model. The selection lives in the component, NOT in the configuration (a `model_source` in scratch would be the
  validation warning `source_ignored_in_scratch`); "Done looking" puts it away. Pinned in `model_chooser_check.mjs`
  (nothing read before the press, Mode and configuration unchanged) and `graph_view_check.mjs` (scratch -> look -> view).
* **Fixed on the way (user report: every chosen save point answered "CompileError: mp1_w: bounds are required").**
  `/api/runs/model` also compares the model with the configuration ON THE PAGE, and compiled that configuration without
  catching `CompileError`: an optimized parameter row without bounds became a 500 that hid the model's facts as well - for
  EVERY save point, because the fault was never the model. Now the facts are always returned; an uncompilable
  configuration gives `compatibility_unchecked = {title, what, note, technical}` instead of `compatibility`. The page shows
  it as a neutral note in plain words (which row, what to fill in, that the saved model is unaffected), with the developer
  text under "Technical details". `test_wb_model_chooser.py::test_an_incomplete_configuration_never_hides_the_saved_model`
  reproduces the report; three checks in `model_chooser_check.mjs`; reproduced over HTTP before / after (500 -> 200).
* **Arrangement: a node-link graph with circuit hints - NOT a schematic (three user messages, in order: "is the structure
  generated directly from the package? not very beautiful"; "hard code or agent judgement?"; "No don't generate schematic,
  rewind the code. I want readable graph neural network style like the cytoscape original but with some hints from the
  circuit information").** The first version used the package's `breadthfirst` layout: long diagonals, crossings, inputs
  dangling at the bottom. A schematic-style attempt (SVG symbols, supply / ground rails, right-angle wires through invisible
  pin and tap nodes) was built, shown and REWOUND on the user's word: the view shows the graph the NETWORK sees, and a
  schematic is a different picture. What stayed is the placement, as hints only: `frontend/src/panels/circuitLayout.ts`
  `hintedLayout()` - HARD-CODED rules, no agent, no model call, deterministic - supply on top, ground at the bottom, heights
  = place on the DC current path (not through gates, bulk ties, rails or capacitors), gate-only nets beside the devices
  they drive, their sources next to them, supply sources at the side, capacitors on a shelf near their net, inverter pairs
  (two shared nets) above each other, barycentre sweeps, collision checks, and no link through a foreign node (the node
  with the fewest links steps aside). Drawing: one node per device / net, straight `bezier` links, shape = family
  (rounded box / barrel / cut corners / circle), colour = kind or net role, a dot where a link enters a gate and a bar
  where it enters a bulk, bulk ties hidden at first, a legend beside the picture. Judged on screenshots of the MOCK OTA,
  two-stage op-amp, LDO and a 3-stage ring oscillator; `graph_view_check.mjs` pins: exactly one node per device / net and
  one link per connection (no helper nodes, no SVG), straight links, the shape / colour / mark hints, PMOS above NMOS, an
  inverter pair aligned with its output between, a gate-only net beside its devices, no link through a foreign node. The
  check's fixture first carried invented terminal roles, which let the gate-mark check pass vacuously and hid a real
  link-through-node case - it now uses real roles. Limits: a drawing rule, not electrical analysis; hub nets (supply,
  ground) still draw long links in a large circuit; drag, "Spread out" and hiding bulk ties help.
* **Toolbar on one line, and a close cross (user, with a screenshot: "the show button and left right arrow are not aligned
  with other boxes. change the close button to a closing cross button in browser style").** A labelled box carries the
  global 4 px `label` margin and a bare button does not, so Show, `<`, `>` and the layout buttons stood 4 px low. In
  `.graph-tools` every input, select and button is now 26 px high on one bottom edge and the tick box is centred on that
  line (pinned to < 1 px in `graph_view_check.mjs`). "Close" is a frameless `x` at the top right of BOTH dialogs (graph
  view and layer table; `button.dialog-close`, `aria-label="Close"`, red when pointed at, Esc still closes).
* **"No link through a node" is judged by the node's BOX.** The same screenshot showed a thick link clipping the corner
  of a device box: the rule measured the distance to a node's CENTRE, and a device box is wide. `through()` in
  `circuitLayout.ts` now clips the link against the box (Liang-Barsky); supply and ground are placed BEFORE what hangs
  on a shelf, and a supply source is placed with the same test, so their links are avoided too. Measured on the four
  circuit drawings (OTA, two-stage, LDO, ring oscillator): 0 overlapping nodes, 0 links through a foreign box (before:
  2 in the ring oscillator, then 1 in the two-stage op-amp). The check tests the DRAWN boxes. Cost: loosely attached
  parts (the ring's load capacitors) end up further from their net than one would draw them by hand; they can be dragged.
* **Abort is red**: solid `--bad` background, white text, faded while there is nothing to abort (`styles.css` only).
* **When it runs, and what it costs (measured, user question "is it frequent and resource consuming?").** Only on a
  press: opening the view is one request, another evaluation is one request; block / head / direction / bulk ties are
  repainted in the browser. Never on a timer, never on page load, never by a training run (the worker does not know the
  view exists). One request in a warm backend: 0.3-0.5 s and +5 MiB for the user's model on the slow `D:` drive (a few
  small files; the forward pass itself is milliseconds), answer 20 KiB. The first version re-read the WHOLE archive per
  request: 1.2 s and +40 MiB on a 2,900-evaluation run. Now only the column of evaluation numbers is read in full and
  the chosen transition and its state are single-row parquet reads: 0.09 s on that run, no longer growing with its
  length. Nothing is cached or kept between requests; closing the view destroys the drawing. There is no separate on/off
  switch because nothing happens unless the button is pressed.

**Verified.** `tests/workbench/test_wb_graph_view.py` (6): nodes and connections are exactly the task's graph; for both
blocks and both heads the attention arriving at EVERY device and EVERY net sums to 1 and the uniform share is 1/k - the
proof that the edge mapping is right; the policy's proposal is identical with and without the hooks, the hooks are
removed again, the recorded action is the run's own; for EVERY archived evaluation the sizes shown are the archive's;
an encoder without attention; no archive / a changed weights file refused; the route (200 / 409 / 404 / 403 / 422)
and **no file of the run changes**. `frontend/scripts/graph_view_check.mjs` (headless Edge, FIXTURE data, safe
against the live backend, 3 screenshots) against a throwaway backend on 8766 with a scratch build and REAL MOCK
runs: the last section draws the first real model (5-transistor OTA: 7 devices + 7 nets, 22 connections) and
compares every line's attention with the real route. The preload guard passes; `tsc --noEmit` clean.

**Limits, stated plainly.** It replays the model on its OWN run's states: it does not show what the model would do
on another circuit (that state would need a simulation). Only the actor is shown, not the critics. The layout is
automatic and knows nothing of the user's schematic; on a large circuit it will need dragging. Attention maps of a
policy trained for tens of evaluations mostly show initialization. MOCK runs only were drawn; a real run uses the same
archive format. Nothing under `src/analog_optimizer/` changed.

### 7.34 Editor tabs renamed: Parameters, Specs, Probes (2026-09-21 ~14:10, separate session, explicit user request)

Request: "Change Tab names as follows, optimization parameters to Parameters, performance targets to Specs,
Measurement Definitions to Probes."

Names only. The configuration sections, JSON keys, request kinds and column names stay `parameters`, `targets`,
`measurements` (`measurement_id`, ...), so saved configurations, exports, run directories and agent proposals are
untouched. What NAMES these tabs to the user follows them, so that nothing points at a tab that no longer exists:

* the tab strip itself (`Editors.tsx`, `TITLES`);
* the start checklist (`agents/readiness.py`, `TITLES` - it must stay equal to the frontend's). Its action line now
  reads `Fill in the "Probes" tab, ...`: a one-word name in quotes alone did not say what to fill in;
* the agent's brief (`agents/run_readiness.md`): items 2-4 carry the tab name and the table it fills, and the agent is
  told to use the tab names when it talks to the user;
* the empty-conversation hint of the Agent tab ("a draft of the Parameters, Specs or Probes tab"); `docs/workbench.md`.

Left alone on purpose: the request-kind list of the Agent tab (raw identifiers such as `draft_config`, `targets`,
`measurements`), the validation messages (they speak of a "target" / "measurement definition" as concepts and name
fields by their path), and the specification file, which is the user's document and still says the long names.

Verification: `test_wb_agent_readiness.py` 16 passed (two assertions follow the new titles); full workbench suite
413 passed; `npm run typecheck` passes; `agent_tab_check.mjs` 78 checks, all pass on a scratch backend - two new
ones (the tab strip reads "Parameters (3) | Specs (1) | Probes (1)"; the empty conversation uses the same names), and
its canned checklist data follows the backend's titles. Real backend, free endpoint: the checklist of an emptied
`synthetic:opamp` lists Parameters / Specs / Probes as missing, in that order.
Live page: `frontend/dist` already holds the change (a parallel session's build at 14:04 picked it up from the shared
working tree), so a page reload shows the tabs. **The backend on 8765 must be restarted** for the checklist titles
(`readiness.py` is loaded at start); the brief is read again for every request and needs nothing. Uncommitted.

### 7.35 Project panel: the whole Hierarchy block is one closed line (2026-09-21 ~14:15, same session as 7.30, explicit user request)

User request: a screenshot of the block - the heading "Hierarchy (10 instances)", its tree, "Instances and parameters"
and "Native schematic ..." - with the words "hide this part". Read as in 7.30 (fold, do not delete): the block is now
ONE closed line, "Hierarchy (N instances)", and everything in the screenshot is inside it. Frontend only (`Left.tsx`
`CircuitPanel`, one more line at the end of `styles.css`).

* `<details className="section">` with the `<h3>` inside its `<summary>` (`display: inline`), so the fold line keeps the
  look of the panel's other headings. Inside: the tree, "Instances and parameters" and "Native schematic", in the old
  order and each still its own closed line. Opened, the block looks exactly as it did before.
* **Left outside, in view:** the warning "Unmapped devices need confirmation" and the "N diagnostics" line. They appear
  only when there is something to say, and a fold must not swallow that.
* **Native schematic has two places.** With a circuit loaded it is a line of the Hierarchy block; while none is loaded
  (browse only) there is no such block and it stands alone at the end of the panel, as in 7.30. One JSX value
  (`nativeSchematic`) rendered in either place; its open state is `nativeOpen`, so moving between the two loses nothing.
* **Controlled like Native schematic** (`hierarchyOpen`): closed by default, and it stays as the user left it across
  circuits - the block un-mounts whenever no circuit is loaded, which would otherwise close it again. React's
  `onToggle` BUBBLES from an inner `<details>` although the DOM event does not; the handler therefore reads
  `e.currentTarget.open` (the block's own state), never `e.target`.

Verification: `tsc --noEmit` and `vite build` pass. `project_help_check.mjs` now has 42 checks and 7 screenshots: the
block is one closed line that still looks like a heading, the tree and "Instances and parameters" are folded inside
it, a click opens it, opening the inner line leaves the block open (the bubbling case above), the state survives two
circuit changes with an un-mount in between, in the draft state "Native schematic" is inside the block and folds with
it, and browse-only has no block. Passed against a scratch build on the side port and against the live page
(a parallel session's 14:12 build already contained the change). `circuit_source_check.mjs` 21 of 21 and
`virtuoso_source_check.mjs` 48 of 48 on the live page - the failure noted in 7.30 was fixed by the connection
session. Page refresh only, no backend restart. Uncommitted.

Later the same day: 7.40 removed the row of `real:*` shortcut buttons from the browse-only note (user request), which
left one assertion of `project_help_check.mjs` stale ("... stay in view as buttons", reported by the 7.44 session). The
check now pins the new behaviour instead - no such buttons, and the sentence that points to "Source: Registered
task" is folded under "Why: ..." with the rest of that explanation. 42 of 42 on the live page again.

### 7.36 Agent: "Review settings" over the whole workbench, optionally with publications read online (2026-09-21, same session as 7.25, explicit user request)

Request: "can the agent check publications online and give suggestions on how to change settings over the whole frontend?
including adding a new network encoder". Until now a proposal could only patch the three tables, and the two web tools
were on the provider's deny list.

| Piece | Where |
|---|---|
| Request kind `settings_review`. It patches NO table (`SECTIONS_BY_KIND` = none). Reply: `suggestions` (path, value as JSON text, reason, source, optional url + verbatim quote) and `encoder_ideas`. 43 suggestible settings: Run configuration, RL network, RL network (Advanced, all but `spec_registry`), Output settings - never the circuit, the connection profile, a model source, the output folder, names. A suggestion for anything else is dropped and named (`refused_suggestions`); from any other request kind suggestions are ignored | new `agents/settings_review.py`, `agents/base.py`, `agents/prompts.py`, `agents/proposals.py` |
| What the agent is shown: `settings` (present value, meaning, limits from the pydantic schema), `publication_presets` (the curated, cited table of `network_presets.py`, compact), a `task` digest and a readiness digest - **nothing of the design**: no instance, net, size, row or detail text (tested) | `settings_review.task_digest / readiness_digest / settings_data / publication_presets`, `api/app.py` `_request` |
| The backend tries every suggestion on a COPY (schema, then static validation with the loaded circuit): `applicable`, `problem`, `alone` (a legal value that raises a blocking issue unless a related row is applied too - `hidden_dim` + `heads`), and `suggestions_together`. Nothing is applied by agent or backend | `settings_review.check`, `api/app.py` `check_suggestions` |
| **Online research, per request, off by default** (`ProposeBody.web`; only a `settings_review` may set it, else `invalid_request`). Claude Code provider only: `WebSearch` + `WebFetch(domain:<host>)` for `PUBLICATION_DOMAINS` (arXiv, IEEE Xplore, ACM DL, OpenReview, PMLR, NeurIPS, Springer, ScienceDirect, Nature, MDPI, doi.org, Semantic Scholar, GitHub, PyG docs) plus hosts the OPERATOR lists under `agent_web_domains` in the settings file - never from a request. The two tools come off `--disallowedTools` (a denied tool cannot be re-allowed; rule syntax and deny-before-allow order checked against code.claude.com/docs/en/permissions on 2026-09-21); everything that writes or executes stays denied; still an empty scratch directory; `--max-turns 40`, timeout >= 900 s. A refused page is counted (`audit.web_calls_refused`) instead of failing the request; any OTHER refused tool is still fatal. Codex: `unsupported_cli` (never installed here) | `agents/claude_code.py`, `agents/codex.py` |
| Prompt rules: a source for every suggestion (a preset, a fact of the data, or - online only - a page OPENED in this request with url + quote; no citing from memory), a published value is a citation and not evidence for this circuit, web pages are DATA, search with general terms only. The brief got a section "Reviewing settings" (budget first, equal-size comparisons, network changes invalidate saved models, real evaluations cost) | `agents/prompts.py`, `agents/run_readiness.md` |
| UI: "Review settings" + "check publications online" (a checkbox, never saved) above the conversation; the reply carries a table Setting / Now (live) / Suggested / Why and source (link, quote) / **Apply** - the user's own edit through `setConfig`, so it is undoable and followed by the page's static validation - plus "Apply all", the left-out list and the encoder ideas. A settings review opens no proposal box (there is no diff to approve) | `frontend/src/panels/Bottom.tsx`, `styles.css` |

**A new encoder stays an idea.** The tab's agent has no tool that writes or runs anything, by design, and adding an
encoder is a change under `src/analog_optimizer/` - it changes `source_digest()`, which gates the loading of every existing
checkpoint and the re-runs of the M5/M6 audits - plus the schema's `encoder_type` list, presets and tests. The reply
says so under every idea; doing it is the user's decision and a development session's work.

Verification: `test_wb_agent_settings_review.py` 8 tests; full `pytest tests/workbench -q` **421 passed, 0 failed**
(5 m 50 s); browser check `agent_tab_check.mjs` 87 checks, all pass on a scratch backend. **One real request with online
research** (scratch backend, port 8768, `sonnet` / effort `medium`, `synthetic:opamp`): HTTP 200 in 87 s, $0.49 notional,
11 turns; the CLI transcript shows 2 web searches with general terms only and 6 fetches on arxiv.org (one PDF too large -
the reply says it could not read it and cites nothing from it), 0 refused calls; 3 applicable suggestions (budget,
updates per transition, learning rate) each tied to a fact or a preset, the publication presets deliberately NOT pushed
onto a 60-evaluation budget, and no encoder idea ("none of the publications I could read uses an encoder we lack").
NOT verified: a refused host in a real run (none occurred), Codex. Python changed: the backend needs a restart. Uncommitted.

### 7.37 Agent tab: two buttons swapped places (2026-09-21, same session as 7.36, explicit user request)

Frontend only (`Bottom.tsx`). "What's missing to start?" moved from the line above the conversation into the row under
the message box, right after "Export task description". "Review settings" took its old place at the right end of the line
above the conversation, with its option "check publications online" in front of it. No behaviour changed.
`npm run build` passes; `agent_tab_check.mjs` 88 checks, all pass on a scratch backend (one new check for the two
positions). Page refresh only. Uncommitted.

### 7.38 Bottom tab strip: the drop-down list of runs became a "Runs..." button that opens the run window - finish time, duration and every fact of each run (2026-09-21 ~14:40, two sessions, explicit user requests)

User request (session "Run selection window redesign"): "In the frontend bottom change the select run collapsing menu
to a button to open a new windows for different run list with finished time and duration information", then "and with
all the run information". After the first build the user asked the session "Run status logs export functionality"
(14:28) for three changes, which that session made in the same files: the button reads only "Runs..." with the run's
description to its LEFT, no "Show" column - a double click shows a run -, and "Show no run" is called "Clear". What
follows is the final state.

**Frontend** (`frontend/src/panels/RunList.tsx` new, three lines of `App.tsx`, one block in `styles.css`):

* The `<select>` at the right end of the bottom tab strip is gone. In its place: plain text naming the run the bottom
  tabs show (start time | task | mode seed | state [MOCK]; "No run selected") and, right of it, ONE button,
  **Runs...**. Pressing it reads the run list and opens the **run window**: a browser window of its own
  (`window.open` + a React portal, the mechanism of the connection window and the detached Agent conversation, so
  all state stays in the one page and nothing is synchronised between windows). Pressing it again brings the window
  to the front; leaving the page closes it. While it is open the button carries the class `open` - not `active`,
  which in this strip means "the chosen tab" (`footer .tabs > button.active` is used by the browser checks).
* The window is one table, newest run first: Started, Finished, Duration, State (+ stop reason), Task, Mode, Seed,
  Evaluations (`25 / 60`), First feasible, Experiment, Data (MOCK / real), Can continue. **A double click on a row**
  shows that run in the bottom tabs (not when it lands on the row's Details button; the word the double click
  selected is let go); the row is marked blue with a bar at its left edge and `aria-current`. **Clear** shows no
  run. The window stays open. **Details** opens everything else under the row, read at that moment from the
  existing `GET /api/runs/status`: folder (a click copies, through the WINDOW's clipboard), ids, created / worker
  began / came to rest / last sign of life, working time, pause time, summed simulator job time, stop reason,
  error, budget, launches, learner updates, first feasibility, best design and its variables, model loaded and last
  save, saved state, parallel simulations, connection, bytes written, and one line per SEGMENT. Empty facts are
  left out. Column titles sort (empty cells always last); a filter box narrows by any word of a row.
* **Wording of "Finished"**, because "finished" is not one thing: a run at rest shows the end of its last segment; a
  PAUSED run shows it with "(paused)" so that it is not taken for finished; a working run reads "still running" and
  its duration "... so far"; a run whose worker died wrote no end and reads "last seen <its last heartbeat>"; a run
  that never began shows dashes, not zeros. All times are local time, written `2026-09-21 14:03:22` (sorts by eye).
* **Duration = working time**, the project's own definition (`summary.durations`): the pauses between segments are
  not part of it; the cell's tooltip and the details name them. End minus start would make a run that sat paused
  overnight look like a twelve-hour run.
* **Nothing updates by itself** (user preference, 7.9): the list is read on the button press and by "Refresh list",
  the details when they are opened; the window prints when the list last arrived. No timer, no poll.
* Compact (user preference, 7.30): the column explanations are one closed "What the columns mean" line.
* An older server lists runs without times: the cells read "-" and ONE line says in plain words that the server has
  to be restarted. A blocked pop-up is said next to the button.
* The header's "let go of this paused run?" question pointed to "the run list"; it now says: press "Runs..." at the
  bottom, double click the run, then Run status > Continue (`RunControl.tsx`, wording only).
* Pitfall for the next pop-up: a window opened as `about:blank` is in QUIRKS mode, where a `<table>` does not
  inherit the font and falls back to 16px. `.run-window table { font: inherit; }` fixes it for this window; the
  connection window's "Details" table has the same quirk.

**Backend** (`src/gator_workbench/runs.py`; nothing under `src/analog_optimizer/` is touched):

* `run_timing(manifest, status)` and new keys in every row of `list_runs` / `GET /api/runs`: `started_utc`,
  `ended_utc`, `last_seen_utc`, `active_seconds`, `paused_seconds`, `segments` (seven facts per segment; the load
  policy stays in the manifest), plus `task_name`, `stop_reason`, `error`, `max_evaluations`. All of it comes from the
  three small files `list_runs` was already reading for each run, so the list costs no extra file access.
* `ended_utc` is the end of the LAST segment, `None` while a worker is on the run. `active_seconds` is
  `summary.durations(manifest)`; for an open segment (working, or the worker died) it is the worker's own running
  total from `status.json`; `None` for a run whose worker never began.
* `evaluations` of a row now prefers the live ledger (`status.json` budget) over the summary: a run that was working
  listed `None`, and one resumed after a pause the count at the pause.
* Existing keys are unchanged; `saved_models` spreads the rows, so `/api/runs/models` carries the new keys too.

**Verification.** `tests/workbench/test_wb_run_list.py`, 8 tests: one go, pause not counted, open segment, never
begun, a dead worker listed as `interrupted` with its last heartbeat (fabricated run folder), a finished MOCK run
equal to its manifest, the API serving the same rows, and a real DETACHED MOCK run listed while it works, after a
pause and after it continued (two segments, the pause not in the working time, the live evaluation count).
The whole `tests/workbench` suite (429 tests collected, run with `-x`) reached 100 % without a failure, with every
session's uncommitted work in the tree. `tsc --noEmit` and `vite build` pass. Browser: `frontend/scripts/run_list_check.mjs`, 60 checks on the live page
(headless Edge, the window as a second DevTools target found by its title, real double clicks through
`Input.dispatchMouseEvent`; every `/api/runs*` request answered by FIXTURE runs of every kind - finished,
paused-and-continued, paused, dead worker, never begun, failed real, working - so it is safe on the live backend).
`run_control_check.mjs` used the old `<select>` to put the bottom tabs on no run; it now opens the run window and
presses "Clear" there: 60 of 60. End to end WITHOUT fixtures: a scratch backend on 8769 with the new `runs.py` and
the new page showed the one real run under `outputs/` with its finish time, 17.8 s and full details - and exposed
that the real `best_design.variables` is a LIST of `{variable_id, value, unit}` while the fixture had a map (the
details printed `[object Object]`). Fixed (`input_pair_width=2.34558e-6 m`), and the fixture now has the real shape.
The live `frontend/dist` is rebuilt; the user's backend on 8765 was NOT restarted: until it is, the window shows its
"older server" line instead of finish times and durations. Uncommitted.

### 7.39 Agent: "Review run results" - the agent is given a digest of a run's output (2026-09-21, same session as 7.36, explicit user request)

Request: "can the agent tab agent read output results?" It could not: it saw the circuit, the three tables, the start
checklist and, for a settings review, the settings - never what a run produced. It still reads no file.

| Piece | Where |
|---|---|
| The digest of ONE run, built by the backend from the run's own records (status, effective configuration, the `evaluations` / `parameters` / `metrics` / `learner_updates` tables, the error log): outcome and budget; first feasibility; every target against what was reached and against the best design (incl. invalid measurements and why); per optimized variable the range tried, the value at the best design and the share of evaluations within 2 % of a bound; failures by status and type with the typical diagnostics; how the evaluations were chosen, learner updates and first-third / last-third trends (`null` under 9 points); a ~20-point best-so-far curve; the 8 best and 5 last evaluations; caveats (MOCK, one run = an anecdote, still running). The best design is the RUN'S OWN choice (`status.best_design`). Bounded (~1.9 k tokens for the 60-evaluation example run), plain JSON, never a NaN | new `src/gator_workbench/agents/run_digest.py` (`build` on plain rows, `load` for a run directory) |
| Request kind `run_review` (needs a run, never online): `reasoning` explains the run, changes come as `suggestions` for settings (same check-on-a-copy as 7.36, `source` = a number of the run) and/or as a `patch` of the three tables. `ProposeBody.run_dir` goes through `run_path` (allowed roots, must be a run directory) | `agents/base.py`, `agents/prompts.py`, `agents/proposals.py`, `api/app.py` |
| Brief: section "Reviewing a run" (plain language first; a fixed diagnosis order - failed simulations, invalid measurements, a learner that never started, a search hitting a bound, a target nothing came near; every statement names its number; no conclusion about an encoder, transfer or an algorithm from one run; a MOCK score is not a circuit quantity). **The brief is now cut per request kind** (`GUIDE_SECTIONS`): the two general sections always, a kind's own section only for that kind - it had grown to ~10 k characters paid on every request; a request now carries 3.5-6.5 k | `agents/run_readiness.md`, `agents/prompts.py` |
| UI: "Review run results" in the row under the message box, after "What's missing to start?"; disabled until a run is chosen with "Runs..." (it says so), names the run in its tooltip and in the request. The reply shows the explanation (lists / code formatted) and the suggestions table; a proposal box opens only when there is a diff. `run_review` is also a selectable kind | `frontend/src/panels/Bottom.tsx`, `App.tsx` (passes `runDir`) |

Verification: `test_wb_agent_run_review.py` 4 tests (digest on plain rows, too-little-data, the request, and a REAL MOCK run
executed in the test, condensed and handed to the fake CLI over HTTP; a run outside the allowed roots is refused); full
`pytest tests/workbench -q` **434 passed, 0 failed** (6 m 18 s). Browser check `agent_tab_check.mjs` 92 checks, all pass
on a scratch backend (button disabled without a run; with a canned run one request of kind `run_review` naming it;
explanation + suggestion; no proposal box without a diff). The script now answers the page's own repeated requests
(`/api/runs/status`) automatically. **One real request** (scratch backend, `sonnet` / `medium`) on the example run
`outputs/mock/delivery_example__aa693365859f/...`: HTTP 200 in 40 s, $0.22, 2 turns; it followed the diagnosis order, named
its numbers, said MOCK and "one seed is an anecdote", noticed by itself that the reported best design is the FIRST
feasible one (score 0.952 at evaluation 6) and not the highest-scoring (0.9958 at 57) because nothing ranks feasible
designs, and suggested no change. NOT verified: a run of a real circuit, a run with failures. Python changed: the
backend needs a restart. Uncommitted.

### 7.40 Virtuoso source: the browse-only note no longer suggests the existing real tasks (2026-09-22, same session as 7.15 / 7.17-7.24, explicit user request)

Request (with a screenshot of the block): "if I work with previous tasks I would choose registered tasks. Maybe
don't show this part as suggestions?" Frontend only; refresh the page.

* `Left.tsx` `CircuitPanel`: the sentence "N circuits have a profile today. Click one to work with it:" and its row
  of `real:*` buttons (added in the 7.15 follow-up) are gone from the note shown for a Virtuoso cell without a
  profile. The note now goes straight from "Browse only ..." to "To start a profile for this cell ...". Nothing is
  lost: the existing profiles are under Source: Registered task (one folded sentence in the "Why" details says
  so), and the backend's sentence under "Technical details" still names them.
* `virtuoso_source_check.mjs`: the two checks that pressed such a button now assert that the note offers NO
  `real:*` button and still offers "Read this cell into the workbench". All checks pass; `npm run build` passes.

### 7.41 Output settings: "Copy path" as text on the "Output root" line; the waveform storage limit typed with a unit (2026-09-21 ~16:05, separate session, explicit user request)

Request: "move the copy path button to the right of same line of output root and make it plain text no button
style. make the waveform storage limit box with unit choice". Frontend only (`Right.tsx` `OutputPanel`,
`styles.css`); refresh the page, no backend restart. The configuration format did not change.

* **Copy path.** It left the row of buttons under the path box ("Browse allowed roots..." and "Test writability"
  remain there) and sits at the right end of the caption line: `Output root ................ Copy path`. It is text
  in the accent colour (`button.text-link`: no border, no background, no padding; underlined under the mouse,
  darker while pressed), still a `<button>` for the keyboard, and copies the same path as before. It is a SIBLING of
  the caption's `<label htmlFor="output-root">`, not a child: a button inside a label becomes the control that a
  click on the label's text activates, so "Output root" would have copied instead of putting the cursor in the box.
* **Waveform storage limit.** A number box plus a unit list: bytes, KiB, MiB, GiB, TiB - the binary units the
  panel already uses for "Free space", so the two can be compared. New `ByteSize` next to `Num` in `Right.tsx`.
  The configuration still holds `output.waveform_storage_limit_bytes` as WHOLE bytes (the schema field is an `int`;
  1.3 GiB is saved as 1395864371 and still reads 1.3); the unit is only how the number is typed and shown, and the
  tooltip names the exact bytes. Choosing another unit KEEPS THE NUMBER and changes what it means (2 GiB -> 2 MiB):
  that way "type 500, then choose MiB" and "choose MiB, then type 500" both end at 500 MiB, which converting the
  display (2 GiB -> 2048 MiB) would not. A value that did not come from the box (loaded configuration, Undo) is
  shown in the largest unit that gives it back exactly with at most 3 decimals - 2147483648 -> "2 GiB",
  524288000 -> "500 MiB", 1500000000 -> "1464843.75 KiB" - so what is shown is never a rounded version of what
  is saved. Half-typed text ("0.") is kept while the box has focus, as in `Num`; letters change nothing.
* **Fault found on the way, fixed in both boxes that had it.** `value={x ?? default}` cannot tell "field absent"
  from `null`, and for these two fields `null` is a real setting (the schema has `Optional[int]`): emptying the box
  saved `null` - no limit / no evaluation-based checkpoints - while the box jumped back to the default, so the
  screen said "2147483648" or "50" and the run would have had neither. Confirmed in the browser before the fix
  (`{"box":"50","saved":null}`). Both boxes now show the default only when the field is absent; an emptied box
  stays empty, and the limit box says what that means (placeholder "no limit"). "Checkpoint every N evaluations"
  was the only other clearable box with a default.

Verification: `tsc --noEmit` and `vite build` pass. New `frontend/scripts/output_panel_check.mjs`, 36 checks, all
pass (headless Edge; hermetic like `blocking_issues_check.mjs`, so it is safe on the live backend: `POST
/api/output/check` and the validation are answered by FIXTURES, GETs pass, every other writing request is refused;
the clipboard is replaced by a recorder in the page; saved values are read back from the page's own stored
configuration): position and look of "Copy path", that it copies, that the caption still focuses the box, that
opening the page only looks at the root (`create: false`); units both ways round, rounding to whole bytes, empty =
`null` and stays empty, letters, Undo, an odd loaded value, an absent field. `network_panel_check.mjs` still
passes. Run on a private build first (`vite build --outDir <Windows temp>` + `vite preview` on 5174); the live
`frontend/dist` was then rebuilt and has the same content hash as the build that was checked. Uncommitted.

### 7.42 Agent tab: two shorter button captions (2026-09-21, same session as 7.39, explicit user request)

"What's missing to start?" is now "What's missing?" and "Review run results" is "Review results" (button text, the empty-
conversation hint, the brief's "Asked for with ...", `workbench.md`). Nothing else changed. `npm run build` passes;
`agent_tab_check.mjs` 92 checks, all pass on a scratch backend; the three agent test files that read the brief: 28 passed.
One run of the check hung at "Bring back" inside the detached window: the click closes the very window whose DevTools
session would acknowledge it, so the script waited for ever. Fixed in the script (a closing session rejects what is still
waiting; that click no longer waits for its own acknowledgement); the stuck node + headless Edge were stopped by their
command line (`remote-debugging-port=9377`) and their temporary profiles removed. Page refresh only. Uncommitted.

### 7.43 Run panel: no block for a NEW network while a saved model is loaded; the network comes with the model (2026-09-21 evening, same session as 7.20 / 7.23 / 7.26 / 7.33, explicit user request)

Request: "When the mode selection is not scratch, dont show the RL NETWORK part for new encoder settings. Only the list
of existing model encoders". Frontend only (`Right.tsx`, `ModelChooser.tsx`); no backend change, no restart for this.

* **Shown in `scratch` only:** the whole "RL network" block - heading, Encoder list, hidden / heads / layers, "In use" with
  the two preset buttons, the "differs from the backend's saved setting" line, the preset problem, "Where the values come
  from". In `resume`, `fine_tune` and `frozen` the panel goes from the run settings straight to "RL model to load"; every
  card there names the model's network, now in bold (`b.model-net`) - that is the list of existing model encoders.
* **The network follows the chosen model.** Backend fact: `check_compatibility` marks another `model_config` as
  incompatible in all three Modes, so there is nothing to choose. `run.network` takes the chosen model's network by itself
  once its description arrives (an unrecorded `setConfig`, like the fill-in of missing values; the act is the choice of the
  model). The model's facts start with a new row "Network ... - this run uses it as it is". Gone: the warning "This
  checkpoint was trained with ..." with the button "Use the checkpoint's network", the "other network" tag, the chooser's
  `network` prop. A compatibility answer that was computed with the network being replaced is not shown (no red "NOT
  compatible" for one frame).
* **Only the network follows.** The old button also overwrote the numbers under "Advanced" with the checkpoint's; that is
  no longer done. A difference there is allowed for `fine_tune` / `frozen`, and a real `resume` uses the run's own saved
  configuration anyway (`_prepare_resume_locked` takes only `RESUMABLE_RUN_FIELDS` from the page). An "Advanced" edit made
  while a model is loaded stores the sizes ALREADY stored for that encoder, not the loaded model's sizes, as the
  per-encoder backend setting.
* **Not silent when it comes from elsewhere.** A network that arrives while the same model stays loaded (an imported
  configuration, an applied `run.network.*` suggestion of "Review settings") is taken back as well, and a warn line says
  so: "The network stays gat 16/2/1: this run loads a saved model ... A new network needs Mode scratch." Known limit:
  "Review settings" can still list such a suggestion as applicable in a loading Mode (its trial validates the configuration,
  not the chosen model; the brief already tells the agent to warn). Those files belong to another session and were not touched.
* The "budget is starved" warning stays in every Mode; while a model is loaded it no longer points at the hidden
  "GATOR baseline" button. Back in `scratch` the block returns with the network last in use, and the existing "differs from
  the backend's saved setting" line offers the stored values back.

Verified in a real browser on a scratch backend (8766) with a scratch build: `model_chooser_check.mjs` 62 checks (new: block
present in scratch and absent in fine_tune, "Advanced" stays, the chooser's note, every card names its network, no "other
network" tag, the "Network" row, the configuration follows without a button - gat, then back to graph_transformer - and the
backend is asked again with the followed network, a WHOLE imported configuration with another network is taken back and said,
the block is back in scratch showing rgcn), `network_panel_check.mjs` 16, `model_structure_check.mjs` 34,
`graph_view_check.mjs` 59: all pass on the final build. `tsc --noEmit` clean. The live `frontend/dist` was rebuilt
afterwards. Page refresh only. Uncommitted.

### 7.44 Choosing a real task brings ITS rows: targets of record instead of the MOCK "score" (2026-09-21 ~16:45, separate session, user report)

Report (with a screenshot): "after choosing real ota5 it still gives score metric as spec target". The screenshot showed
more than that: Task `real:gpdk045_ota5`, Specs = `score >= 0.95` (unit `fixture`), and PDK id `synthetic-fixture`.
Cause: the rows of Parameters / Specs / Probes are part of the CONFIGURATION, and the Task drop-down changed nothing but
`circuit.task_id`. Whatever "Load starter configuration" had put there for the MOCK task stayed - rows, labels and the
project name `mock_opamp`, under which a real run would have been filed (`runs/<task_name>/`). And a real task had no
starter at all: `GET /api/tasks/starter` answered 404 for anything but `synthetic:*`, the button was hidden.

* **Backend: a real task has starting rows** (`tasks.real_starter_config`, served by the same `GET /api/tasks/starter`).
  Local files only - no connection, no bridge, no simulation (the verified profile object is built from its repository
  files by the new `_verified_profile`, which `_real_runtime` now uses too). Parameters: the rows the profile fixes
  (`_graph_parameter_rows`, the body of `profile_parameter_rows`; a follower now carries its group's `optimized` flag -
  a frozen group used to raise `follower_flag_ignored`). Specs: the circuit's TARGETS OF RECORD
  (`REAL_TARGETS_OF_RECORD`): `configs/m6_real_cross_category.json` classes / opamp | ldo | vco / specs / `train` - the
  partition a run from scratch belongs to - and `configs/gpdk045_ota7_transfer.json` for the OTA7. `min` / `max` /
  `range` become `>=` / `<=` / `interval`, `scale` becomes `normalization_scale`, and every row says in `basis` which file
  it comes from and that it is a pilot goal near the measured baseline, not a product specification. Probes: one per
  target, labelled with the analysis that produces the result (`RESULT_ANALYSIS`; an oscillator: all `tran`). No `run`
  key: a real budget is never suggested. Project `gpdk045-ota5` / `gpdk045_ota5`, labels `opamp` / `gpdk045`.
  A profile GENERATED from a cell gets its parameters and a probe per result its registry knows, and NO target:
  requirements are never inferred from a circuit. `synthetic:*` starters are byte-for-byte what they were (many checks
  seed themselves from them). A generated profile that no longer passes its own checks answers 409 with the reason.
* **Backend: the LDO and VCO could not be given a target at all.** Their results are not in the default result registry
  (`score` + six op-amp results) and the UI has no registry editor; two of the LDO's units (`V/V`, `V/A`) were unknown to
  `units.py`. `real:gpdk045_ldo` and `real:gpdk045_vco` now bring the registry of record of the real cross-category
  experiment (`tasks.verified_spec_registry`, consulted by `validation.registry_for` and `compile.build_spec_schema`
  after the generated-profile registry, before the default; compiled under its own version
  `m6-physical-spec-input-v1`, 23 results - identical to the experiment's schema). The OTA tasks deliberately stay on the
  default registry, so their models remain interchangeable with the MOCK tasks' and with earlier workbench runs. A
  registry stated in the configuration still wins. `units.py`: `V/V` (`mV/V`) and `V/A` (`mV/mA`, `mV/A`), kept apart
  from ohm. `/api/tasks` rows carry `pdk_id`.
* **Frontend** (`Left.tsx` `CircuitPanel`): the Task drop-down calls `chooseTask`. The class / PDK labels follow in the
  same change as the task (from the task list, so the circuit is loaded once, not twice). The starters of the task
  before and of the new task are fetched; the three editors are exchanged ONLY while their rows are nobody's work -
  all empty, or still exactly what the task before had brought (JSON-equal). Edited rows stay, and one `warn` line
  says so and names the button. A project name nobody typed follows - the untouched default, or a name some task's
  starter gives (`/api/tasks` rows carry `starter_project`, from the one helper `tasks.starter_project` both starters
  use); a typed one stays, on the button too (it used to be overwritten there). The exchange is written without a
  history step of its own (`setConfig(..., false)`), so ONE Undo takes back the task choice and everything it
  brought, and Redo returns it. Run settings are never touched. "Load starter configuration" is now there for every
  registered task; it replaces the rows and labels a starter states (and, for a MOCK task, budget and seed as
  before). One hint line reports what happened and disappears with the first edit. A backend that was not restarted answers 404 for a
  real task: the panel says "older than the page ... restart it", and nothing is exchanged. Nothing happens on page
  load, on an imported configuration or on an approved proposal - only on the explicit choice in the drop-down.
* **Fault found on the screenshot of the result, fixed in the editor** (`Editors.tsx`, one expression): a field a row
  does not STATE was drawn as empty / unchecked, so the six real targets looked "not hard" although `hard` defaults to
  on (the MOCK starter's row had always looked that way too). An absent field is now shown with the schema default the
  backend will use (`hard` on, `tolerance` 0, `optimized` on ...). Only `undefined` is treated so: a box the user
  cleared is `null` and stays empty (the trap of 7.41).

Verification. `tests/workbench/test_wb_real_starter.py`, 10 tests: for each of the four verified circuits the starter
validates against the profile's own graph with no error, blocker OR warning, its parameter rows compile to exactly the
profile's `graph_contract`, and its compiled `MetricSpec`s equal the specs of record field by field; analysis labels;
the two registries and their precedence; the two units; the MOCK starter unchanged; a generated ring-oscillator profile
(created in the test from the fixture cell) gets 8 probes, no target, and `no_hard_constraint` as the one thing left to
the user; the API route and `pdk_id`. Whole `tests/workbench` suite on the final code: 446 passed, 1 failed -
`test_wb_profiles.py::test_a_generated_profile_is_deleted_by_moving_it_aside`, another session's NEW test, reached while
that session was still writing its delete-profile feature; re-run alone a few minutes later it passes, and the run
before it (without that test) had passed completely. `tsc --noEmit` clean at the time of the build. New `frontend/scripts/task_rows_check.mjs` (headless Edge): HERMETIC by default - task list, starters, circuit
loads and validations are FIXTURES, other GETs pass, writing requests are refused, so it is safe on the live backend
and independent of its version (32 checks: the reported case, labels, names, one load, ONE Undo / Redo, edited rows
kept + the button, a typed name kept by the drop-down and by the button, a circuit without targets of record, an older
backend, `hard` shown on); with `--live` the same steps read the REAL starters from a restarted or scratch backend and
check the numbers of record (25.01 dB, 2.1 uW, 53.3 dB for the OTA7; 29 checks). Both modes pass, the live one against a
scratch backend on 8767 with a copy of the connection file (8766 was another session's scratch server; it was only ever
sent GETs by mistake and not touched). Run on a private build first (`vite build --outDir <Windows temp>`, served by a
throwaway node static server that passes `/api` on, because `vite preview` is pinned to 8765); the live `frontend/dist`
was then rebuilt (16:43), the hermetic mode passes on the LIVE page of 8765 (32 checks) and the live mode on that same
build against the scratch backend (29). Neighbours on the private build: `circuit_source_check` 21,
`blocking_issues_check` 26, `virtuoso_source_check` 48, `agent_tab_check` 92, `run_control_check` 60 - all pass.
`project_help_check` had ONE stale failure that predates this change (line 176 still expected the `real:*` shortcut
buttons that 7.40 removed); its owning session was told and fixed it the same hour (42 of 42). The agent session was
told as well and made "Load starter configuration" the first advice of its checklist and brief (its own files). The
scratch servers were stopped and the temporary Windows folders removed.

Limits, said plainly. The targets of record are PILOT goals a hair above each measured baseline (OTA5: 25.0009 dB
measured, 25.01 dB asked) - they show what a real target row looks like and make the task startable; they are not what
a designer would ask of the circuit, and nothing here pretends otherwise. No real simulation was run. A `BACKEND
RESTART` on 8765 is needed for the real starters, the LDO / VCO registry and `pdk_id` (until then the page says so);
the editor fix and the labels need a page refresh only. Uncommitted.

### 7.45 Right column: "Run configuration" and "Output settings" fold into one line (2026-09-21 evening, same session as 7.43, explicit user request)

Request: "Make the run configuration module and output settings module able to collapse from expanded". Frontend only
(`Right.tsx`, `styles.css`); page refresh only.

* One small component, `Module`, wraps both panels: the heading is the fold line (the existing `details.section` look of
  the Project panel's Hierarchy block, heading text unchanged so every check that finds a panel by its `h3` still does).
  **Open at first** - the request says "from expanded", and these are the settings a run needs; the rule "new collapsibles
  start closed" was about long help, not about a whole module. The choice is kept in this browser
  (`localStorage` `gator-workbench-module-run` / `-output`, wrapped in try/catch; a private window just does not remember).
  The third panel, "Research experiments", already was a fold; it was not touched.
* It is a `<details>`: a folded module stays MOUNTED. Everything in the run panel keeps working while folded (the network
  still follows a chosen model - 7.43 -, the per-encoder settings are still read and saved, the output root is still looked at).
* Folded, the line says the main values on a second row: `fine_tune - 200 evaluations - gat 16/2/1`, and
  `<experiment name> - .../<last two folders of the output root>` (one line, ellipsis, full text as tooltip).
* **An error or a warning is never just hidden.** While folded, the line carries a mark "error inside" (red) or "warning
  inside" (amber) when the module's content holds an `.error` / `.warn` element. It is watched with a `MutationObserver` on
  the content, not per render: parts inside keep their own state (model list, graph view) and can raise an error without
  the panel rendering again - so the mark also appears when the problem arises while the module is folded. Blunt limit:
  the mark says THAT something asks for attention, not what; "warn" covers mild notes too (for example "these values differ
  from the backend's saved setting").

Verified in a real browser on a scratch backend (8766) with a scratch build: new `frontend/scripts/module_fold_check.mjs`,
29 checks (fixtures only, safe against the live backend): both start open, a real mouse click on the heading folds one and
leaves the other, 1014 px -> 54 px, the summary line and that it follows the configuration while folded, still mounted,
remembered across a reload, the warning mark (a budget of 1) and that it goes away, an error that appears WHILE folded is
marked at once, the two colours, unfolded the error itself is in view, Enter on the fold line, no side scroll. The checks
that touch the right column still pass on the same build: `output_panel_check` 36, `network_panel_check` 16,
`model_chooser_check` 62, `model_structure_check` 34, `graph_view_check` 59, `run_control_check` 60, `run_list_check` 60,
`agent_tab_check` 92. `tsc --noEmit` clean.

Trap met while rebuilding the live `frontend/dist`: another session was in the middle of an edit of `Left.tsx` (a name used
before it was defined). `vite build` does not type-check, so that first live build carried a bare `taskNote` - a
ReferenceError as soon as a Virtuoso source is shown. It was replaced within a minute, once `tsc` was clean again, and the
LIVE page (8765) was then verified with the two fixture-only checks (`module_fold_check` 29, `model_chooser_check` 62: all
pass). Rule for every session: `tsc --noEmit` immediately before a live build, and no live build on a failing tree - the
scratch build is for that. Uncommitted.

### 7.46 Agent brief and start checklist: "Load starter configuration" comes first (2026-09-21, same session as 7.39; prompted by the session of 7.44)

The session of 7.44 reported that every registered task now has starter rows and a visible "Load starter configuration"
button. Checked before relying on it: for ota5 / ota7 / ldo / vco the starter's parameter rows equal
`tasks.profile_parameter_rows()` and compile to a `graph_contract` identical to the verified profile; the targets carry
their stated source ("Pilot target of record ..."). Then, in this session's own files only:

* `agents/run_readiness.md`: a general section (sent with every request kind) - when the tables are empty or hold rows
  of another task, advise that button first: it costs no request and cannot be wrong; draft rows only for what it cannot
  give; targets of record are not provisional and are not relabelled or replaced unless the user asks.
* `agents/readiness.py`: for a registered task the free checklist's action for missing rows, and for variables that
  differ from a verified profile, now starts with 'Press "Load starter configuration" in the Project panel (left)'. An
  imported netlist keeps the old text (it has no starter).
* `test_wb_agent_readiness.py`: three assertions. Agent test files: 28 passed. Python changed (one text): restart the
  backend. Uncommitted.

### 7.47 One cell, one task: a cell that already has a registered task says so; "Delete profile" (2026-09-21 evening, same session as 7.15 / 7.17-7.24 / 7.40, explicit user request)

User: "Close the gap to be able to say this cell has a registered task and add the delete profile functionality."
The gap: "one profile per cell" only looked at GENERATED profiles. `vco_m6_v1`, the cell of the verified built-in
`real:gpdk045_vco`, was offered the Create profile form (user screenshot); once a circuit type fits such a cell, a second
profile would write into a cell the experiments of record depend on. And a generated profile could only be redone by
deleting its folder by hand.

* `profiles.task_for_cell(library, cell)`: the generated profile of the cell, else the built-in whose design file names
  it as `core_cell` - only when `library` is one a Virtuoso connection states (`bridge_connection.json`), so a copy of
  the cell in another library is another cell. Local reads only. `create_profile` refuses such a cell ("already has the
  registered task real:gpdk045_vco (a verified built-in circuit): choose it under Source: Registered task").
  `/api/circuit/load` answers `profile_task` from it plus `profile_task_generated` - also for a cell that was NOT read
  into the workbench, where the note used to say "Browse only ... cannot optimize it yet".
* `profiles.delete_profile(name, run_rows=)` + `POST /api/virtuoso/profile/delete`: the folder is MOVED to
  `profiles/.deleted/<name>.<utc>/` (a recorded baseline cost a real simulation; runs refer to these files), so the name
  and the cell are free again. Refused while a worker is on a run of the task (`working_run_of`: a row of
  `runs.list_runs` in starting / running / pausing / stopping whose manifest names the task), for an unknown name and
  for the four built-in circuits (they are not in this store). Contacts nothing. The copy of the cell that was read
  from Virtuoso stays, so the form can go straight back to it.
* `Left.tsx`: ONE note for both states of such a cell (read in or not): "This cell already has a registered task:
  `real:<name>` (a verified built-in circuit)" + a short **Open** button - the task name is text beside it; it is about
  THIS cell, unlike the list of tasks removed in 7.40 - and a folded "What this means". No "Read this cell" and no
  profile form there. Open does what choosing the task does (`chooseTask`, one history step). The generated task's
  block ends with a separated line: what it is for as text, then **Delete profile** (`window.confirm`, like the run
  buttons; it names the baseline if one is recorded). Afterwards: the task list is re-read, the form returns to the
  profile's cell (Source: Virtuoso, its library / cell / testbench), one green line says what happened, the path of the
  kept files is a folded line, and Create profile is offered again. "Profile ... created" is now tied to its own task.
* Tests: `test_wb_profiles.py` 22 passed (3 new: built-in cell lookup + refusal, deletion by moving aside incl. the
  working-run refusal and re-creation, the API incl. 422 for bad names). `virtuoso_source_check.mjs`: 66 checks
  (fixtures + planned confirm answers; "Cancel" deletes nothing, a refusal keeps the task), run against a temp build
  on 5174 with the live backend behind it. `tsc` clean. Whole `tests/workbench`: 447 collected, no failure (`-x` run).
  Against the real local settings: `GATOR_TESTS/vco_m6_v1` -> `real:gpdk045_vco`, likewise ota5 / ota7 / ldo; a
  testbench cell and the ring oscillator -> none. Live `dist` rebuilt.
* Python changed (new endpoint, wider lookup): restart the backend; until then the page says "This backend is older
  than the page" on Delete profile. Uncommitted.
* Re-checked after 7.49 (the testbench box finds `tb_<cell>`, Probes follow the testbench - another session, same
  files): `virtuoso_source_check.mjs` 66/66 on the live `dist`; `test_wb_profiles.py` + `test_wb_testbench_probes.py`
  29 passed. The testbench that comes back with a deleted profile's cell is not overwritten by the name lookup.

### 7.48 Agent tab: the answer is shown while it is written (thinking summary, then the reply); no time limit (2026-09-21 evening, separate session, explicit user request)

User: "Considering the agent tab, is it possible for the agent chat box to reply real time thinking and real time reply
but not as a whole message back?", then: "if you can show real time reply at the agent tab, remove the time limit of 300s".

Found (verified, not assumed):
* The CLI already ran with `--output-format stream-json --verbose` (setting `stream: true`), but `run_cli` waited in
  `communicate()` and `/api/agent/propose` answered once, so nothing could reach the page before the end.
* The thinking of every earlier Agent-tab request came back EMPTY: the CLI transcripts
  (`~/.claude/projects/-tmp-gator-agent-*/`) hold thinking blocks of length 0 with a signature. Current models
  default to `thinking.display: "omitted"`. In `-p` mode, `claude` 2.1.278 asks for nothing else: its `showThinkingSummaries`
  setting only applies to interactive sessions. The option `--thinking-display summarized` is hidden from `--help`,
  but it is what the embedded Agent SDK passes for `thinking.display` (choices summarized / omitted / highlights), and it
  returns a readable summary. The display does not change billing (claude-api reference: "billed the same under every
  setting").
* The chat text is the `reasoning` field of the `StructuredOutput` tool call. The CLI sets `eager_input_streaming` on
  its tools only behind a server flag, or with `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING=1`; with it the input
  arrives a few words at a time.
* Two real requests (claude-sonnet-5, $0.08 + $0.27 notional on the Max subscription, 12 s and 211 s): reply pieces
  about every 50 ms; at effort max, 1,390 thinking pieces (17,365 characters of summary) over 3.5 minutes. The model
  wrote the fields in the order the schema lists them. The user's saved setting was opus at effort max: 300 s was
  within reach.

Backend:
* `agents/live.py` (new). `PartialAnswer` makes one pass per character over the JSON of the answer as it arrives: it
  reports each top-level field as it starts and decodes the `reasoning` string (escapes, `\uXXXX`, surrogate pairs cut
  between pieces). `LiveTranslator` turns CLI lines into the events `model`, `thinking`, `step` (WebSearch / WebFetch /
  Read..., API retries; `ToolSearch` skipped), `say`, `writing`, `reply` and `restart` (the CLI asked for the answer
  again). Subagent lines and anything unreadable are ignored. Display only.
* `base.run_cli(on_line=)`: stdout is read line by line while the CLI runs, with stdin and stderr on threads of their
  own. `timeout` None means no limit (a caller may still set one: a Timer stops the process group).
  `AgentSettings.timeout_seconds` now defaults to None; `AgentProvider.propose(request, on_event=None)`.
* `claude_code.py`: a live request uses stream-json with `--include-partial-messages --thinking-display summarized`
  and the environment variable above. `stream_event`, `rate_limit_event` and system `thinking_tokens` / `status` lines
  are no longer kept as logs (a long request has thousands). If stderr says a live option is unknown or invalid, the
  request runs once more without the options (no model call had happened) and a `step` says so. Codex and Disabled
  accept `on_event` and ignore it (Codex: superseded the same evening by 7.50).
* `prompts.PROPOSAL_SCHEMA`: `reasoning` moved right after `kind` (required list and properties), so the text streams
  before the rows.
* `api/app.py`: `POST /api/agent/propose` with `Accept: text/event-stream` goes to `live_answer`. The provider runs on
  a thread of its own and its events cross into the event loop (`call_soon_threadsafe`). The stream is SSE `progress`
  events, then ONE `result` (the same proposal as the JSON answer, incl. `readiness_after` and the checked
  suggestions) or ONE `error` (the same dict as the 409 detail; an unexpected exception gives `internal_error`). A
  comment line goes out every 10 s. A stream that ends before its verdict (page closed or reloaded) cancels the request.
  A request that fails validation is still a plain 409, and a request without the header is unchanged. The time limit
  is gone: `agent_settings()` drops a saved `timeout_seconds` (the user's file had 300), PUT accepts and ignores it
  (older pages send it), and nothing saves it. `WEB_TIMEOUT_SECONDS` removed.

Frontend:
* `api.proposeLive(body, onProgress)`: a fetch with a ReadableStream SSE reader. `result` resolves; `error` throws
  `ApiError(409, detail)`, so `fail()` and the neutral cancel line work unchanged. A JSON answer (an older server, or
  the canned answers of `agent_tab_check.mjs`) is taken as is. A stream that ends without a verdict becomes an error line.
* `Bottom.tsx` `AgentTab`: events go into a ref and are drawn at most every 150 ms. The pending bubble shows:
  * the model the CLI runs;
  * a "Thinking" box that follows the newest line unless scrolled up;
  * the steps;
  * the reply (RichText);
  * a status line ("Sent. Waiting..." / "Thinking..." / "Looking things up..." / "Writing the reply / the proposed
    rows / the warnings...") with the seconds.
  The hint is 'No time limit. "Cancel request" below stops it; what has arrived stays in the chat.' The finished reply
  carries `thinking` + `thinking_seconds`, shown as a closed `<details>` "Thinking - N s" above its text (component
  `Thought`). An error line keeps its thinking the same way; a cancel line keeps "Thinking" and "Reply so far" folded
  under it. The chat follows a growing answer only while scrolled to the bottom. `save()` no longer sends
  `timeout_seconds`; `WEB_TIMEOUT_SECONDS` removed.
* `styles.css`: `.thinking-live`, `.thought-text`, `details.thought`, `.live-steps`, `.live-reply`.

Checks:
* `tests/workbench/test_wb_agent_live.py`, 19 tests:
  * decoding under every cut (char / random / whole; as written or reply first; raw or `\u`-escaped, incl. a surrogate
    pair), with nested "reasoning" keys ignored;
  * the RECORDED real stream (`fixtures/claude_live_recorded.ndjson`: request 2 above, trimmed to its first 60 thinking
    pieces, ids replaced) rebuilds the thinking and the reply exactly;
  * steps, retry, say and restart;
  * the provider: argv and environment, a plain request unchanged, progress more than 1 s before the end, the fallback
    for a CLI without the options, cancel mid-stream, no default limit;
  * the API: progress then the same proposal as the JSON path, error shape, cancel, a saved limit ignored;
  * a real uvicorn socket: events spread over time, and a closed connection cancels the agent;
  * `live_answer` closed early cancels.
* `fake_cli.py`: scenarios `live`, `live_slow`, `live_hang`, `live_demo` (`FAKE_CLI_PAUSE`; a prompt containing
  FAKE-HANG hangs) and `live_refused`; it records the environment variable.
* `frontend/scripts/agent_live_check.mjs` (new):
  * hermetic, 14 checks: SSE fixtures, one JSON answer and a cut stream; safe on 8765;
  * `--live`, 12 checks against a scratch backend with the fake CLI: the thinking grows over 4 samples and the reply
    over 13, the statuses, the folded thinking, and a cancel keeps the thinking.
* `agent_tab_check.mjs`: only the online waiting-line check changed (it now expects "No time limit" instead of
  "900 s"); all its checks pass against the new build.
* `tsc` clean. Whole `tests/workbench`: no failure (`-x` run, exit 0; 473 tests collected afterwards).
* Live `dist` rebuilt at 18:11 by the session "Virtuoso cells optional fields", together with its own `Left.tsx`
  work (checked: the build contains the live answer). Restart the backend (8765) for the live answer and the removed
  limit. Until then the new page gets one JSON answer as before, and the old server still stops a request at 300 s.
  Uncommitted.

### 7.49 Virtuoso source: the testbench is found by its name, and Probes follow the testbench (2026-09-21 evening, separate session, explicit user request)

User: "for the testbench cell, add the functionality of detecting the name in format tb_cell_name with the same name
as the original cell. The probes should be updated according to the testbench cell". Owner sessions of the files
(7.47 profile-from-cell, 7.44 task starter rows) were told before the edit.

* **Found by its name** (`Left.tsx`, `namedTestbench`): choosing a cell chooses `tb_<cell>` when the library has it
  (the `tb_` prefix in any case, the cell name exact, a schematic view required; `tb_` beats `TB_`). A hint says
  "Found by its name: tb_ + the cell's name". Without a `tb_` of its own, a new cell drops the old cell's `tb_` but
  keeps a testbench chosen by hand. When the cell list ARRIVES (page load, Refresh) an EMPTY box is filled the same
  way, like the PDK id - never over a chosen testbench, and a testbench that comes with a Delete-profile answer is
  untouched. The box's tooltip no longer says "Optional": Create profile has always refused a cell read without one.
  Not found by this rule: the verified OTAs' `tb_ota5_ac_v1` / `tb_ota7_m5_ac_v2` (those cells are registered tasks).
* **Probes follow the testbench** - backend `profiles.testbench_probes(imported)`: from the COPY that was read
  (`native_cells`), which of the circuit types the testbench fits (the same readings Create profile makes: `_supply`
  + `_ring` for the ring oscillator, new `_opamp_fit` for the op-amp - `create_profile` now calls it, same message)
  and one Probes row per result of that type (`probe_results`: the registry the profile will bring, else the default
  one), each with `signal` = where in THIS testbench it is read (`OUT`; the ring nets `OUT XU1.N1 XU1.N2`; `V0:p`)
  and a note "Testbench <tb>, circuit type <label>: <meaning>". Nothing when read without a testbench, or when the
  testbench fits no type (or both) - with the reasons per type. `POST /api/circuit/load` answers it as
  `testbench_probes` for a Virtuoso draft (`load_cell_import` alias: `native_cells` is a route name in `create_app`).
  `signal` is documentation for a `backend_profile` row: the circuit type measures fixed nets; the folded help says
  so. **A generated profile's starter (`tasks.real_starter_config`) now builds its Probes with the same function**
  from its `design.json`, so after Create profile the rows are still "the task's own" for `chooseTask`'s JSON
  comparison (key order included). The four verified and all synthetic starters are unchanged.
* Frontend (`Left.tsx`, `followTestbench`): only after an own choice of library / cell / testbench (exchanged inside
  that choice's Undo step) or a Read press (a step of its own); never on page load. Rows are exchanged only while
  nobody's work - empty, brought by an earlier testbench in this page session, or JSON-equal to the starter of the
  config's `task_id` (the last registered task); that task's untouched targets leave Specs with them (they point at
  its probes) and the line says so. Edited rows stay: "Probes hold rows you edited, not the ones of the testbench
  <tb>." + **Use testbench probes**. No fitting type: "Probes were left as they were. <reason>" + folded "Why no
  circuit type fits". Create profile's Circuit type follows the detected type. When the box and the copy differ:
  "This copy was read through <tb> (without a testbench). Press Read the cell again to read it through <tb>: Probes
  then follow it." A cell that already has a registered task gets nothing. Own state `probeNote`, not `taskRows`.
* Not handled: Parameters rows name the testbench's core instance (`XU1/MN1`); a testbench with another instance
  name makes them stale. Only the two circuit types exist, so e.g. `rfExamples/lna300` brings no probes.
* Checks: `tests/workbench/test_wb_testbench_probes.py` (7: ring and verified-OTA exports, no testbench, fits no type,
  cell missing from the testbench, the API answer + validation, starter rows == testbench rows as JSON text).
  `frontend/scripts/testbench_probes_check.mjs` (new, 39 checks, hermetic: all Virtuoso calls and Virtuoso-source
  loads are fixtures, safe on 8765), plus `virtuoso_source_check` (66), `project_help_check` (42), `task_rows_check`
  (31), `circuit_source_check` (21) - all pass on a scratch build served on 5174. `tsc --noEmit` clean. Whole
  `tests/workbench`: 480 passed. The live `frontend/dist` was rebuilt afterwards (the 7.48 session said its frontend
  was ready; `tsc` right before), and `testbench_probes_check` + `virtuoso_source_check` pass on it at 8765.
* **Restart the backend (8765)** for `testbench_probes`; until then the auto-find works and Probes simply do not
  follow. Uncommitted.

### 7.50 Agent tab: the live answer for the Codex provider too (2026-09-21 evening, same session as 7.48, explicit user request)

User, after 7.48: "also do this for the codex if havent". It had not been done: `CodexProvider.propose` ignored `on_event`.

Found (verified against documentation, NOT against a real CLI - `codex` is installed neither in WSL nor on Windows):
* `codex exec --json` prints JSON lines: `thread.started`, `turn.started`, `item.started` / `item.updated` /
  `item.completed`, `turn.completed` (usage), `turn.failed`, `error`. The items are `agent_message`, `reasoning`
  (`text`), `command_execution` (`command`, `aggregated_output`, `exit_code`, `status`), `file_change` (`changes[].path`),
  `mcp_tool_call` (`server`, `tool`), `web_search` (`query`), `todo_list` (`items[].text`), `error` (`message`).
  Sources: learn.chatgpt.com/docs/non-interactive-mode (redirect from developers.openai.com/codex/noninteractive) and
  github.com/openai/codex `sdk/typescript/src/events.ts`, `items.ts`, `exec.ts`, read 2026-09-21.
* There are NO text pieces: an item arrives whole. So Codex can show its reasoning summaries paragraph by paragraph and
  its steps, but the reply only in one piece. The SDK itself passes `--experimental-json` together with
  `--output-schema`.
* Reasoning summaries: `model_reasoning_summary` (auto | concise | detailed | none) defaults to auto; `hide_agent_reasoning`
  suppresses them in `codex exec` output. The workbench leaves both to the user's Codex configuration.

Built:
* `agents/live.py` `CodexTranslator` emits the same events as the Claude translator:
  * `turn.started` -> `thinking ''` ("Thinking...");
  * `reasoning` -> `thinking`, a new paragraph per item; an `item.updated` that extends an item adds the rest;
  * command / web search / MCP call / file change / plan / item error -> one `step` each; a failed command adds one more;
  * `turn.failed` and `error` -> a `step`;
  * the final `agent_message` -> `writing reasoning` + `reply` when it is the JSON answer, otherwise `say`.
  It keeps `last_message`.
* `codex.py`: with `on_event`, the first of `--json` / `--experimental-json` that `codex exec --help` lists as a whole
  word (`listed()`) is added, and stdout is read line by line (`run_cli(on_line=)`). Neither listed: a `step` says the
  answer will arrive in one piece. The proposal is still the `--output-last-message` file, or the stream's last agent
  message if a CLI version writes none (the SDK reads it from the stream). Online research stays refused for Codex.
* The page is unchanged: the pending bubble is provider-agnostic.

Checks:
* `test_wb_agent_live.py`: 7 new, 26 in all.
  * argv `exec --json`, and the proposal from the file;
  * events in documented order, the steps, and the reply;
  * items more than 1 s before the end;
  * a CLI without `--json`: one piece, plus the note;
  * the answer from the stream when no file is written;
  * cancel mid-stream;
  * every documented item type, `item.updated` growth, junk lines;
  * the API streams a Codex answer.
* `fake_cli.py` (codex part):
  * `--json` in its help (except scenarios `old_codex` / `codex_without_json`);
  * `codex_events()` in the documented shape;
  * scenarios `codex_live`, `codex_live_slow`, `codex_live_hang`, `codex_live_nofile`, and `codex_demo`
    (`FAKE_CLI_PAUSE`, FAKE-HANG).
* `agent_live_check.mjs --live --codex`: 12 checks against a scratch backend (fake `claude` and `codex`, scenario
  `codex_demo`; the check saves provider = codex there).
  * the reasoning appears item by item (72 then 134 characters);
  * "Running: ls" and the web search appear as steps; the status goes "Thinking..." then "Looking things up...";
  * the reply, with its thinking folded;
  * cancel keeps the first paragraph.
* The agent/API test files pass (89); whole `tests/workbench`: 480 passed (5 min 31 s).
* No frontend source changed, so no build. Restart the backend (8765) - the same restart as 7.48. Uncommitted. Untested
  with a real `codex`: the first real Codex request will show whether its stream matches the documentation. If it does
  not, only the live display is affected; the proposal path is the one of before.

### 7.51 Editor tabs: Probes before Specs (2026-09-21 ~18:35, separate session, explicit user request)

Request: "change the order of the Spec tab and the Probes tab, probes at front and spec follows it".

The centre strip now reads **Parameters | Probes | Specs** (a Spec row is written on a Probe's result, so the strip
now follows the order in which the rows build on each other). Order only: the names, the configuration keys
(`parameters`, `measurements`, `targets`), saved configurations, exports and agent proposals are unchanged, and
Parameters is still the tab that opens first.

* the strip: `Editors.tsx` `TITLES` - its key order IS the tab order (the strip is `Object.keys(TITLES)`);
* the start checklist: `agents/readiness.py` `TABLES` (and `TITLES`, kept equal to the frontend's) - the checklist now
  lists circuit, Parameters, Probes, Specs, ... in tab order. With all three tables empty the first missing item is
  still Parameters. `changeable_rows` is keyed by name, so a `minimal_start` proposal is unaffected;
* texts that list the three tabs list them in the new order: the agent's brief (`run_readiness.md`, together with the
  keys it maps them to), the "Load starter configuration" tooltip and the two task-rows notes (`Left.tsx`), the
  empty-conversation hint of the Agent tab (`Bottom.tsx`), and `docs/workbench.md`, including the column order of the
  "whose rows" task table.

Left alone: validation messages and request kinds (config vocabulary), `ROW_SECTIONS` in `Left.tsx` (used only as an
order-free list), the entry 7.34 above (a record of its time) and the specification file (the user's document).

Verification:
* `test_wb_agent_readiness.py`: the order assertion now expects `circuit, parameters, measurements, targets`; with
  `test_wb_agent_settings_review.py`, 24 passed. `tsc --noEmit` clean.
* `task_rows_check.mjs` (hermetic) on a scratch build (`vite build --outDir <Windows temp>` + `vite preview`, API proxied
  to 8765): 32/32 pass. Its four strip assertions now expect, for example, "Parameters (2) | Probes (3) | Specs (3)";
  the notes read "Parameters, Probes and Specs now show this task's rows".
* `agent_tab_check.mjs`: its strip check now checks the order as well, and its empty-conversation text follows
  `Bottom.tsx`. Not run this time: it needs a scratch backend, and the Python tree was being edited by the session of
  the Specs-equation work. Its strip assertion is the same one `task_rows_check.mjs` passed.
* Live page: `frontend/dist` rebuilt at 18:38 (after `tsc --noEmit`, with the go-ahead of the busy peer session). Its
  bundle `index-D6Fe8gKs.js` is byte-identical to the scratch build checked above, and `task_rows_check.mjs` (hermetic)
  against 8765 passes 32/32, so a page reload shows the new order.
* Restart the backend (8765) for the checklist order (`readiness.py` is loaded at start); the brief is read again for
  every request. Uncommitted.

### 7.52 Specs are equations over Probes (2026-09-21 evening, separate session, explicit user request)

Request: "each spec should be equation of probes", in reply to a gap found while explaining how the three tabs reach
Virtuoso. A Specs row named ONE probe (`measurement_id`), and the two scorers took different roads. The environment's
reward looked the spec's NAME (`metric_id`) up in the simulation result. The workbench's pass/fail check went through
the probe's `source_name`. Nothing tied the two together: pointing the OTA5 target `unity_gain_hz` at a probe that
reads `bandwidth_3db_hz` passed validation with only an "unused measurement" warning. The reward would then judge the
unity-gain frequency while pass/fail judged the bandwidth.

Now each Specs row has an `equation` over Probe IDs, in place of `measurement_id`. The simplest equation is one Probe
ID, and every starter row is of that kind. A formula works too, for example `m_supply_power_w / m_osc_frequency_hz`.
The syntax is the whitelist evaluator the Probes' expressions already use (numbers with SI suffixes, `+ - * / **`,
brackets, no calls). ONE value per spec goes everywhere: the reward, the goal input of the network, the independent
feasibility check, the best-design choice and the tables.

* `spec_equations.py` (new, workbench package; `src/analog_optimizer/` untouched, digest still `02127bc3...`):
  * `parse` reads an equation's form (AST). It never evaluates, so `(m_a - m_b) / (m_c - m_d)` is judged by its form.
    The Probes' expression check used a trial evaluation with every symbol at 1.0, which divided by zero on such
    formulas and rejected them; it now uses `parse` too.
  * `SpecPlan` (picklable, compiled with the task) gives the probe values and spec values.
  * A spec is "result-backed" when its equation is the probe of the simulator result of the same name. The environment
    finds that value in the result itself, exactly as before. Every other spec is "computed": `SpecPlan.wrap` makes the
    lane's backend add its value to each simulation result under the spec's name (canonical unit, validity), and a
    request asks the simulator for the raw results the formula reads instead of the spec's name. The engine takes the
    added keys back out, so raw rows, probes and the independent check use the simulator's own results only.
  * The synthetic factory wraps its backend (`plan` field). The real factories are wrapped by `EquationNativeFactory`
    ONLY when a computed spec exists (`tasks._with_computed_specs`); otherwise the verified path is unchanged. The
    wrapper keeps the worker's first-evaluation check against the recorded real baseline on the simulator's results
    only: a formula's rounding would only make that check stricter than the measurement.
* Result registry (the network input): a spec name the registry lacks adds one entry
  (`compile.build_spec_schema`, version `<base>+spec-equations-v1`). The entry's reference magnitude comes from what
  the spec computes: its formula evaluated on its inputs' registry references, else on the size of each probe's unit.
  It never depends on thresholds, so changing a limit keeps saved models loadable (the checkpoint contract compares
  the registry exactly). Adding, removing or renaming such a spec changes the network input. A registry stated in the
  configuration is taken as given, and an unknown name there is still the `metric_not_in_registry` blocker. As a
  consequence, a spec on a simulator result the default registry lacks (for example the OTA's `bandwidth_3db_hz`) is
  no longer blocked; it adds an entry and an info line says so (`spec_adds_registry_entry`).
* Validation: `equation_rejected`, `equation_without_probe`, `equation_unknown_probe` (errors);
  `equation_unit_unchecked` (warning: a formula's unit cannot be checked; one probe's still is, `target_unit_mismatch`);
  `spec_name_is_a_result` (a spec may carry a simulator result's name only when its equation IS that result's probe:
  this closes the gap); `spec_name_is_a_probe` (a Probe ID as a spec name only when the equation is that probe: keeps
  the metrics table's keys unique). `unused_measurement` now counts probes used inside formulas. `J` / `pJ` / `fJ`...
  added to the unit registry (power / frequency = energy per cycle).
* Tables: a result-backed or single-probe spec keeps the metrics row it always had (`measurement_id` = the probe, the
  same fields). A formula's row has `measurement_id` null and `aggregation = equation`. Probes no spec shows whole get
  rows of their own, as unused probes did. `profiles.record_reference` now reads only `aggregation_level = condition`
  rows (a formula's row has no `measurement_id` either and would have been taken for a raw result).
* Older configurations: `measurement_id` is read as the equation (a pydantic before-validator in the backend,
  `migrateConfig` in the browser's saved copy and in "Import JSON"). The key keeps its position, so JSON-text row
  comparisons still match the backend's starters. `config_hash` and `task_definition_hash` hash a one-probe equation
  under the old key, so every earlier configuration keeps its hashes: runs still resume, checkpoints still load,
  approvals and proposals still bind (tested against the old algorithm).
* UI: the Specs table's second column is `equation` (schema-driven). A one-line fact above the table names the Probe
  IDs an equation can use. The Agent tab's row facts show `equation`.
* Pre-existing bug fixed on the way: the editors' **Add** gave every required field without a default the schema's
  `default: null` (a Specs row got constraint = null and normalization_scale = null; a Probes row got analysis = null).
  The whole configuration then failed validation with a schema error that no row showed. Now such a field gets the
  first option / 1 / "". A new Specs row starts as the first probe, in its unit.
* Agent: the brief (`run_readiness.md`) lists Probes before Specs in the gating order, as the checklist does since 7.51,
  and says what an equation is and when a spec may carry a result's name. The run digest gives each target's
  `equation`. The checklist's empty-Probes line is reworded.

Verification:
* `tests/workbench/test_wb_spec_equations.py` (17, new): parsing; failed operations invalid; old configurations with
  both hashes equal to the pre-change algorithm; each validation code; registry entry sized by what the spec computes
  and unchanged by its limits; `extend` / `request_names` / no-op `wrap`; `EquationNativeFactory` baseline check on raw
  results; and a whole MOCK run in which `score_sq = m_score ** 2 >= 0.8` alone decides feasibility. There, every
  evaluation's feasibility equals score^2 >= 0.8, the environment's success always agrees (no
  `feasibility_disagreement`), the manifest's registry ends with `['score_sq', 'fixture', 1.0]`, and raw rows never
  contain `score_sq`. Updated: `test_wb_schema_validation.py`, `test_wb_profiles.py`, `test_wb_real_starter.py`,
  `fixtures/fake_cli.py`. Full `tests/workbench` on the final tree: 497 passed (the run before had 1 failure: a fake
  metrics table without `aggregation_level`; fixed, with a formula row added to prove it is kept out of a baseline).
* `tsc --noEmit` clean. Browser, on a scratch build (`vite build --outDir <Windows temp>`) served with `/api` passed to a
  scratch backend on 8768 (settings: first an empty folder, then a copy of `configs/local/workbench`):
  `task_rows_check.mjs` hermetic 34/34 and `--live` all pass (2 new checks: the equation column, the probe list);
  `spec_equations_check.mjs` (new, 15 checks: an old saved row migrates in place, **Add**, a formula's info and
  warning, unknown probe, function call, probe name, result name; only reads and validations pass through) all pass;
  `testbench_probes_check.mjs` all pass (on the settings copy: it needs the connection profile); `agent_tab_check.mjs`
  all pass.
* Live: backend 8765 NOT restarted and live `frontend/dist` NOT rebuilt. ORDER MATTERS: restart 8765 first, then
  rebuild `dist`. The new page saves `equation` rows, which the old backend's schema rejects (extra key, missing
  `measurement_id`). The old page on a new backend works (rows are migrated server side), though its Specs table shows
  an empty `equation` cell for an old saved row until the rebuild. Uncommitted.

### 7.55 Virtuoso task flow, part 1: the working copy and the Maestro setup of the copy (2026-09-21 late evening, separate session, explicit user request)

Request: after a feasibility check of the user's flow plan (pick cell + testbench -> read -> the agent sets up parameters,
probes and specs ON the Virtuoso side -> read back, editable in the workbench by user or agent -> a manual "Save task" ->
"frontend, backend and Virtuoso side consistency"), "start building the mentioned flow; delete existing repetitive
similar functionalities with my approval" - taking the chat of the session "Parameters, specs, and probes linking in
Virtuoso" into account (Maestro limits fill the Specs rows; a workbench edit is written back; the Specs tab keeps the
optimizer's own columns; measuring in the one shared Virtuoso session queues the 4 lanes). Decisions asked with
AskUserQuestion: all four proposed removals approved ONCE THEIR REPLACEMENT WORKS (Create profile form -> Save task;
circuit types + auto probes -> Maestro outputs, after the new run path; "Ask the agent for suggestions" -> the agent's
setup request; "Check against Virtuoso" -> the new consistency check) - none is removed yet, no replacement is finished;
the first Virtuoso write approved exactly as asked (a new library `GPDK045_RINGOSC_GATOR`, gpdk045, under `/home/minlei`,
copying `ring_osc_3stage` + `tb_ring_osc_3stage`); saving a task again "won't generate a new task, but add task save as"
(the same task is updated; "Save task as" makes another) - for part 3.

Facts established on the live installation (read-only unless said, zero simulations): Virtuoso `IC23.1-64b.ISR3.27`;
every mae*/OCEAN/copy function the flow needs is callable; exact syntax read from the installation's own Cadence docs
with the bridge's `find_skill` (`ccpCopy`, `dbCopyCellView`, `dbSetInstHeaderMasterName`, `maeSetSpec` (`?gt ?lt ?range
?minimum ?maximum ?tolerance ?weight`), `maeGetTestOutputs`, `maeOpenSetup` (creates a missing view), `maeCloseSession`,
`maeCreateNetlistForCorner`, `maeGetSetup`, `maeSaveSetup`, `maeDeleteOutput`, `maeDeleteVar`, `axlGetSpecData` ...).
An exploration IN THE COPY ONLY (restored afterwards: width back, probe view deleted, copy netlist = original again):
(1) a GPDK045 transistor width set to a Maestro variable leaves the 12 side values the PDK derives from it (as, ad, ps,
pd, nrd, nrs, sa, sb, sd, sca, scb, scc) at their old numbers (`w=(W_N) ... as=140f ad=140f`) - transistor sizes can NOT
be design variables; they keep the verified write-the-number-through-the-callbacks path; (2) a Maestro setup (test,
model file, tran options, point outputs, specs, variables) is written and read back in a background session with no
window; the output struct has no spec field - specs read back with `axlGetSpecData(axlGetMainSetupDB(session) output
test)` as `("gt" "1e+09")` / `("range" "0.9" "1.1")`; `?range` wants a SKILL list, not a string; the nominal corner is
`Nominal`; `maeCreateNetlistForCorner` writes a complete runnable deck (`parameters temperature=27 W_N=1e-06`, the model
include with `section=tt`, the circuit, `simulatorOptions`, `tran ...`, `saveOptions save=allpub`) - the deck of the
planned run path.

Built:
* `src/gator_workbench/bridge_setup.py` (new): the write process (short-lived, like `bridge_read`; takes
  `artifacts/local/bridge-state/session.lock` - the lock every real run and the no-simulation check take - so it never
  interleaves with a simulation's own edits; cellviews opened by library/cell, never through a window). Op `make_copy`:
  hierarchy of the testbench's library under it (read-only), refusal for cells without schematic/symbol or with a CDF of
  their own (parameterized cells: not copied yet), fingerprints of the original schematics BEFORE, `cds.lib` downloaded
  before and after `library.create`, `dbCopyCellView` per view (never over an existing cellview unless a failed attempt
  of the same copy wrote it), `dbSetInstHeaderMasterName` + `schCheck` + `dbSave` per copied schematic, netlist export
  of the copied testbench, fingerprints AFTER; `progress.json` after every step. Ops `read_setup` / `write_setup`: the
  copy's Maestro test `GATOR` (background session, always `maeCloseSession ?forceClose t`), outputs deleted and added
  again so no stale spec survives, other tests left alone; instance parameters set to variable names via
  `cdfFindParamByName(...)~>value` and put back to the ORIGINAL value when no longer bound.
* `src/gator_workbench/working_copy.py` (new): records (`configs/local/workbench/working_copies/<lib>/<cell>/copy.json`,
  `libraries.json` = the only libraries the workbench writes into), the gate (`write_cellview` / `read_cellview`), the
  acceptance checks (per-block statement sets of the two netlists, continuation lines joined - statement order means
  nothing to Spectre; every copied cell from the copy library in the netlister's `// Library name:` comments; originals
  unchanged; technology binding equal), `reverify` (the verdict again from the stored files, no Virtuoso), a failed
  attempt keeps its library as the workbench's and lists what it wrote; `read_setup` / `write_setup` with the bindable
  set = analogLib `res/cap/ind/vdc/idc/vsource/isource` instances of the testbench and the cell (CDF names from the
  import's readbacks: `V0.vdc`, not the netlist's `dc`), the default model file = the connection's in section `tt`, and
  what was left to the copy (analyses not sent, model files not chosen) compared with what the copy has.
* `src/gator_workbench/virtuoso_setup.py` (new): the setup model, `check_expression` (tokenizer; calls of an allowed
  list of calculator functions, strings, numbers, the setup's variables, arithmetic, `?keyword` - `system()`, `;`,
  backquotes refused; nothing evaluated), `normalize` (numbers in one spelling: `1G` = `1e+09` = `1000000000`),
  `fingerprint`, `validate`, `differences` (plain sentences; analysis options Maestro adds by itself are not
  differences), `from_rows` (ade_output probes -> outputs with the expression in `signal`; active Specs rows whose
  equation is exactly one such probe -> gt / lt / range in canonical units; a formula over several probes and every
  optimizer-only field stay in the workbench), `to_rows` (unit and analysis SUGGESTED from the expression and marked).
* API (`api/app.py`): `POST /api/virtuoso/copy`, `POST /api/virtuoso/setup/read` (with `config`: `editor_differences`),
  `POST /api/virtuoso/setup/write` (the rows, or a whole `setup` = the agent's approved proposal later; without
  `analyses` the copy's are kept); `/api/circuit/load` carries `working_copy` (local record) for Virtuoso sources.
* Frontend: `frontend/src/panels/WorkingCopy.tsx` (new) in the "Read from Virtuoso" note of `Left.tsx`: "Make a working
  copy" (explanation folded), then the copy named + "Read setup" / "Write to Virtuoso", a one-line summary of the copy's
  test, "The editors match the copy" / "differ in N places" (list folded), "Use in editors" (keeps a unit / optimizer
  setting chosen on a row of the same name and converts the copy's base-unit limit into that unit by SI prefix - found
  by the browser check: 1e9 Hz had first landed as 1e9 GHz; one Undo step), writing with no Maestro probe asks first;
  nothing on load. `api.ts`: `workingCopy`, `setupRead`, `setupWrite` (next to the other Virtuoso calls).

Live (the approved first write, 2026-09-21 ~22:55-23:05): `GPDK045_RINGOSC_GATOR` created at
`/home/minlei/GPDK045_RINGOSC_GATOR` (gpdk045; `cds.lib` +1 line `DEFINE GPDK045_RINGOSC_GATOR
/home/minlei/GPDK045_RINGOSC_GATOR`, backup kept), 3 cellviews copied, testbench re-pointed (1 header, `schCheck` 0/0),
originals unchanged, 3 s. The first verdict said "does not netlist like the original" only because `XU1` now comes after
`V0` - the comparison was made order-insensitive per block and the stored copy re-verified: VERIFIED. Then a sample setup
(tran 50n, outputs `frequency(VT("/OUT"))` / `ymax(VT("/OUT"))`, specs `> 1e+09` / range 0.9..1.1, variable `VSUP` on
`V0.vdc`) written in 12.3 s, read back in 6.4 s: no difference, same fingerprint, rows as expected; then an empty setup
(put `V0.vdc` back to `1.0` through the restore path) and the probe Maestro view deleted: the copy is again exactly the
original (netlist compared). No simulation anywhere.

Verification: `tests/workbench/test_wb_working_copy.py` (8) and `test_wb_virtuoso_setup.py` (10, incl. the routes) pass;
full `tests/workbench` on the shared tree (with the peers' uncommitted 7.53 / 7.54): 529 collected, all passed (`-x`, exit 0). `tsc --noEmit` clean. Browser: `frontend/scripts/working_copy_check.mjs` (new,
hermetic, fixtures for every `/api/virtuoso/*` and `/api/circuit/load`, seeded from the page's own saved configuration)
23/23 on a scratch build served on 5176 with `/api` passed to the live 8765 (not restarted); on the same build
`virtuoso_source_check.mjs` and `testbench_probes_check.mjs` (the checks of the note the block sits in) all pass. The live `frontend/dist` was
NOT rebuilt by this session; the backend needs a restart for the new routes. `src/analog_optimizer/` untouched.

Not built yet (parts 2-5): the task file + its pop-up editor + "Save task" / "Save task as" (replacing Create profile),
the agent's whole-setup proposal (replacing "Ask the agent for suggestions" for read cells), the pre-run consistency
check (replacing "Check against Virtuoso"), the run path that measures `ade_output` probes (Maestro netlist once,
Spectre per evaluation with transistor sizes written into the COPY, OCEAN on that run's results; one Maestro run to
prove equality - needs the user's budget) and then the removal of the two fixed circuit types. Until then static
validation keeps `ade_output` probes and design variables blocked for runs.
