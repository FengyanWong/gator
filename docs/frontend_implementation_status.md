# Frontend / run-control / data-output implementation status

Short working record for `gator_claude_code_fable51_frontend_data_outputs_en.md`.
After context compaction or a resumed development session: reread **this file**, the
code diff (`git status`, `git diff`) and the specification before continuing. Do not
redo completed modules from conversational memory. This is a development record, not a
research output or analysis report.

Last updated: 2026-09-20 (~21:25: section 7.7, per-encoder network settings from publications; ~21:35: section 7.8, Agent tab side window + browser check; ~21:50: section 7.9, connection panel; ~22:00: section 7.10, agent model / effort lists; ~22:00: section 7.11, validate 500 from a concurrent first import of torch_geometric; ~22:15: section 7.12, blocking-issues button in the header; ~22:40: section 7.13, netlist import form; ~22:30: section 7.14, detachable agent conversation; ~23:10: section 7.15, Virtuoso source dropdowns; 2026-09-21 early: section 7.16, start checklist + readiness request; 2026-09-21 ~01:15: section 7.17, read a Virtuoso cell into the workbench (profile creation, increment 1)).

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
