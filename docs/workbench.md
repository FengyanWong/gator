# GATOR workbench: frontend, run control and data-only outputs

Local web workbench around the existing optimizer. It reads circuits, lets you define
optimization problems by hand or with agent assistance, runs the existing SAC backend, and
saves the raw data and model state needed for research analysis.

It produces **data, configurations, models, netlists and logs only**: no plots, images, PDFs,
spreadsheets or analysis reports, and no plotting library is installed or imported.

All code lives in `src/gator_workbench/` and `frontend/`. **Nothing under
`src/analog_optimizer/` is modified**, because `training/sac.py::source_digest()` hashes that
package and gates checkpoint loading and the M5/M6 audits.

## Start

```bash
# once: backend dependencies into the project environment
/tmp/analog-optimizer-venv/bin/python -m pip install -e '.[graph,web,webtest]'

# once (and after UI changes): build the UI. This machine has no Linux node; the Windows
# toolchain works through WSL interop. A native Linux node works the same way.
cd frontend && npm install && npm run build && cd ..

# run (local-only listening by default)
PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8765
# then open http://127.0.0.1:8765 in the Windows browser
```

Options: `--allow-root DIR` adds an allowed **output** root, `--allow-input-root DIR` an allowed
**netlist input** root. Roots can only be added by the operator here (or with
`GATOR_WORKBENCH_ALLOWED_ROOTS`), never from the browser, an imported file or an agent.
`--host` other than localhost prints a warning: there is no authentication layer.
`--connection-check-on-start` runs one cheap connection check at start (off by default, see
"Connecting from the panel").

Start-up takes about 2 s before the port opens: the backend imports torch / torch_geometric once,
in one thread, before it serves anything (`gator_workbench.preload`). Importing them on first use
let two parallel first requests corrupt the import, and every later static validation then
answered 500 until a restart.

UI development: `cd frontend && npm run dev` (Vite on 127.0.0.1:5173, proxying `/api`).

Without the UI:

```bash
PYTHONPATH=src python -m gator_workbench.cli validate  my.config.json
PYTHONPATH=src python -m gator_workbench.cli run       my.config.json      # foreground run
PYTHONPATH=src python -m gator_workbench.cli aggregates outputs/mock/<experiment>
PYTHONPATH=src python -m gator_workbench.cli check     <profile-id> [--scope full]
```

## What is real and what is mock

| Path | Status |
|---|---|
| `synthetic:*` tasks, imported netlists | **MOCK**: the optimizer's analytic toy backend (`origin=synthetic`). Every row says `provenance=mock`, data lives under `<output_root>/mock/`, and it is excluded from real-experiment aggregates. The `score` is not a circuit metric. |
| `real:gpdk045_*` tasks | The verified bridge profiles through the existing `NativeEnvironmentFactory`. Need virtuoso-bridge 0.8.0 importable by the backend interpreter, a connection profile, a passing connection gate and an explicit budget authorization. **Not exercised in this delivery** (see the status record). Nothing ever falls back to mock. |
| Arbitrary native cellviews | Read-only browsing through the bridge. Optimizing one needs a verified circuit profile; writing a native schematic is not implemented (contract returned by the API). |

### Importing a Spectre netlist

Project panel, **Circuit source -> Import Spectre netlist**. Two files are needed, both read on the
machine that runs the backend (nothing is uploaded from the browser):

* **Netlist path** - the Spectre netlist (`.scs`).
* **Device mapping (JSON)** - for each device type in the netlist: which pin is which and what its
  parameters mean. It is never guessed. The project's mappings are in `configs/` (`opamp.json`,
  `ldo.json`, `vco.json`, `gpdk045_opamp.json`, ...).

Both must lie inside an allowed input root (the repository; more with `--allow-input-root DIR`). A
Windows path (`D:\gator\my.scs`) is converted to its WSL path. Fill in both and press **Load
netlist** (or Enter) - the panel asks the backend only then, not while you type. **Try the example**
loads `tests/fixtures/synthetic/opamp.scs` with `configs/opamp.json`. An imported netlist runs on the
MOCK backend only: the repository has no generic real simulator runner for arbitrary netlists.

### Browsing a Virtuoso library

Project panel, **Circuit source -> Virtuoso library / cell / view** (needs a connection profile and
a link that is up). There is nothing to press: choosing the source lists the libraries, choosing a
library lists its cells, choosing a cell reads its schematic. Each step is a gated, read-only,
zero-cost bridge call and waits for the one before it. **Refresh** repeats the chain, for example
after the link came up or the design changed in Virtuoso.

* No view is asked for: the bridge reader always opens the view named `schematic` (read-only, and
  closes it again). A cell without a schematic view is listed but cannot be chosen; the panel shows
  which other views the chosen cell has.
* **Circuit class** (opamp, ldo, vco, ...) and **PDK id** (e.g. `gpdk045`) are labels saved with
  every run: they group the research tables and let the validator check a claim such as "unseen
  circuit class". They change neither the simulation nor the optimization, and `unspecified` is fine
  for a single run. The PDK id is filled in from the library's technology library unless you typed
  one.
* This source is **browse only**: optimizing a native design needs one of the verified circuit
  profiles (the `real:gpdk045_*` registered tasks).
* **Read this cell into the workbench** (first step towards a profile for your own cell; explicit
  press, read-only, some seconds): Virtuoso exports the netlist of the testbench cell (or of the cell
  when none is chosen) and the device sizes are read. The copy is kept under
  `configs/local/workbench/native_cells/<library>/<cell>/`, and the cell then loads from it without
  contacting Virtuoso: you can look at it, fill the three editors, and **Ask the agent for
  suggestions** - the Agent tab opens with the request written out; its proposal, once approved
  there, fills the editors. Device types this project has not verified (for example the MIM
  capacitor `g45cmim`) are shown with unnamed pins. Such a cell still cannot run: Start stays
  disabled (`circuit_profile_missing`) until the profile is created - that step is not built yet.

`POST /api/virtuoso/libraries | cells | read | import`, body `{"profile_id", "library"?, "cell"?, "testbench"?}`.

## Connection profiles (section 2.1)

`configs/local/workbench/bridge_connection.json` (git-ignored; operator-owned):

```json
{"active": "lab",
 "profiles": {"lab": {"env_file": "/home/me/.virtuoso-bridge/.env", "profile": null,
                      "bridge_site_packages": "/home/me/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages",
                      "library": "MY_LIB",
                      "model_file": "/remote/pdk/models/spectre/model.scs",
                      "circuits": {
                        "gpdk045_ota5": {"creation_receipt": "/path/ota5/creation.json",
                                         "reference_measurements": "/path/ota5/measurements.json"},
                        "gpdk045_ldo":  {"creation_receipt": "/path/ldo/creation.json",
                                         "reference_measurements": "/path/ldo/measurements.json"}}}}}
```

The first three keys are the link (enough to connect and test). `library` and `model_file` are
shared by every real task. A creation receipt and a baseline describe ONE circuit, so they sit
under `circuits`, keyed by the task name without the `real:` prefix; a task without an entry is
reported as blocked with the keys it lacks. The older flat form (`creation_receipt` and
`reference_measurements` at the top level) still works for a single circuit. Before anything is
prepared, the backend compares the receipt's `library`, `core_cell` and `testbench_cell` with the
circuit's design file (the adapter repeats this at connect) and requires the baseline to be
`origin: real` with a metrics table - so a receipt can never reach the wrong circuit silently.
Verified values for the four GPDK045 circuits are recorded in
`artifacts/local/m6-real-protocol/bindings.json` (ota5, ldo, vco) and
`artifacts/local/m5-ota7-qualification/<id>/verification.json` (ota7).

The browser only ever sends the profile **identifier**. The check is read-only and zero-cost,
runs in a short-lived process with the same interpreter and environment as a run worker, names
the broken layer, and never starts, restarts or stops the tunnel, the daemon or Virtuoso.
Results go to `configs/local/workbench/connection_checks.jsonl`, never into research tables.

### Connecting from the panel (added 2026-09-20, user request)

The left panel walks through the three steps of bringing the link up:

1. **Connect SSH** - an explicit click starts the SSH tunnel of the selected profile exactly the
   way `virtuoso-bridge start` does (`SSHClient.from_env(keep_remote_files=True).warm()`, in a
   short-lived process). A tunnel that is already running is left untouched. Like the upstream
   command, a first start deploys the bridge setup files to the remote host. SSH runs in batch
   mode: it needs key-based login and cannot ask for a password.
2. **Load in the Virtuoso CIW** - the panel shows the `load("...virtuoso_setup.il")` line the
   bridge saved in its state, with a Copy button, plus the `RBStop()` + `load(...)` pair for a CIW
   that answers "already running". Loading it stays a manual step in your own Virtuoso; the
   workbench never sends it to the CIW.
3. **Test connection** - the zero-cost check above. The answer is one plain sentence (for example
   "SSH is connected, but the Virtuoso CIW does not answer - load the command below...") with the
   next step; **Details** lists every layer.

With no connection file, the panel offers **Create profile "lab" from this bridge setup**: it
locates `~/.virtuoso-bridge/.env` and the bridge's site-packages on the backend host and writes the
file (`env_file`, `profile: null`, `bridge_site_packages`). The env file is located, never read;
the browser sends only the profile name; an existing connection file is never overwritten.
Real-simulation tasks also need `library`, `model_file` and the per-circuit `circuits` entries
shown above, added by hand.

**A check runs only when you press a button** (user request, 2026-09-20 night): Connect SSH,
Test connection or + Spectre / license. The panel no longer checks on page load or profile change
and no longer polls every 15 s; on load it reads the backend's last result once (a cache read, no
probe). `serve` no longer checks at start either (`--connection-check-on-start` brings that one
cheap check back). A result stays on screen with the clock time of its test ("tested at 21:04:13")
until the next press - it is the result of that moment, not a live indicator, and it no longer
turns to `unknown` by itself after `--connection-stale-seconds` (a page reload still shows an old
result as `unknown`). Unchanged and independent of the panel: the gate probes the link afresh
before every real action (read/write a cellview, real simulation), whatever the panel shows.

What did NOT change: a check still never starts anything (`connection.py` cannot, and a test pins
it); nothing ever stops or restarts a tunnel, the daemon or Virtuoso. The starting code lives apart in
`bridge_connect.py`. Connect attempts are logged to `configs/local/workbench/connection_actions.jsonl`.
Endpoints: `GET /api/connection/setup`, `POST /api/connection/profile`, `POST /api/connection/connect`
(each body is `{"profile_id": ...}` and nothing else).

## Output layout

Default root `<repo>/outputs` (remembered; selectable among allowed roots; writability is tested;
a Windows path is shown only after a token written through Linux was read back through Windows).

```text
<output_root>/[mock/]<experiment_name>__<experiment_id>/
  experiment.json  split_manifest.json  data_dictionary.json
  aggregates/{run_summary,budget_success,budget_success_grouped,paired_runs,transfer_summary,cumulative_cost}.csv (+ .meta.json)
  runs/<task_name>/<mode>__seed<seed>__<run_id>/
    run_manifest.json  effective_config.json  run_summary.json  artifact_manifest.json  status.json
    input_snapshot/{circuit.json, netlist.scs, hierarchy.json, parameter_mapping.json, pdk_reference.json}
    data/{evaluations,parameters,metrics,simulator_jobs,learner_updates,transitions,states}/part-*.parquet
    data/states/static/*.json      de-duplicated graph/spec templates
    data/_journal/                 wal.jsonl (acknowledgement), flushes.jsonl (visible parts), dispatch.jsonl
    best_design/{best_feasible.json, best_infeasible.json, parameters.csv, optimized_dut.scs}
    checkpoints/<id>/{training_state.pt, model_weights.pt, metadata.json, replay_buffer/manifest.json}
    checkpoints/{latest.json, best_policy.json}
    waveforms/  logs/{events,errors}.jsonl  exports/  control/  work/
```

Mapping to the recommended layout of the specification:

* `input_snapshot/dut.scs` + `testbench.scs` -> **`netlist.scs` + `hierarchy.json`** when the source is
  one combined netlist. No empty placeholder files are created; the manifest says so.
* `checkpoints/<id>/replay_buffer/...` -> the replay snapshot is **embedded in `training_state.pt`**
  (written by the existing `SACLearner.save`), so weights, replay and counters can never come from
  different moments. `replay_buffer/manifest.json` lists its members so it can be checked against
  the complete `transitions` archive without unpickling.
* A part file belongs to the dataset only if `data/_journal/flushes.jsonl` lists it.

Three things that are deliberately not the same:
`latest` (most recently safely saved state) / `best_policy` (only by an explicit validation-set
rule, otherwise explicitly `not_selected`) / `best_design` (a circuit parameter set, not a model).
And: first-feasibility cost vs. final run cost; the complete `transitions` archive vs. the finite
replay snapshot; an agent conversation `--resume` vs. an RL training `resume`.

## Reload saved data

```python
from gator_workbench.storage import DatasetReader
from gator_workbench.trajectory import TrajectoryLoader
rows = DatasetReader('<run>/data').rows('evaluations')            # fixed snapshot
transitions = TrajectoryLoader('<run>').transitions()             # optimizer Transition objects, validated
```

## Agent providers

`ClaudeCodeProvider` (default when `claude` is on the backend PATH), `CodexProvider`,
`DisabledProvider` (task-description export + structured-result import). Proposals only:
prompt on stdin, argv array, no shell, no write/exec tools, no permission bypass; applying needs an
approval bound to the proposal, configuration and circuit hashes. Agent model/effort/timeout are
independent of RL checkpoints and simulation budgets, and agents are never in the SAC loop.

Bridge skills exist in `~/virtuoso-bridge-lite/skills/` and the project's Codex-style
`.agents/skills/`, but **not** in a Claude Code discovery location. `GET /api/agent/diagnostics`
reports this and proposes (never executes) symlinks into `.claude/skills/`.

### What is missing before the run can start

"What's missing to start?" (above the conversation) is answered by the backend, free: no agent request,
nothing probed. It lists, in the order a start is gated: circuit, Optimization Parameters, Performance
Targets, Measurement Definitions, other blocking issues, run configuration, output folder and - for a real
circuit - the bridge connection (the LAST test result; it does not test again) and the budget authorization
that only you can give. Each line says who acts. "Ask the agent to fix what it can" appears only when a
line is the agent's (the three tables); it sends ONE request of kind `readiness`, and the reply carries its
own checklist plus, where it had everything it needed, rows to review as a diff.

The agent's brief on what a run needs is a plain file, `src/gator_workbench/agents/run_readiness.md`. It is
added to every agent request of every provider and to the exported task description, and it is read again
for each request, so an edit needs no restart. Keep it short (it is paid for on every request) and true to
what the workbench does. It is guidance below the fixed rules: it cannot widen what an agent may change.
This is deliberately not a Claude `SKILL.md`: the agent runs in an empty directory with no tool that could
load one, and a skill would not reach Codex or the exported task.

## Tests

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q
```

Provider tests use a fake CLI fixture; connection tests use fake bridge clients and a fake probe
process. No test starts a real agent session or contacts a real Virtuoso.

The header shows blocking issues as a red button, "N blocking issue(s)": a press lists every one of
them in full (level, code, field and editor row, message), including those that belong to no editor
tab; the list follows each validation and closes when nothing blocks. Its browser check is
`frontend/scripts/blocking_issues_check.mjs` (headless Edge against the running workbench; the
validation is answered with canned FIXTURE reports and every other writing request is refused, so
it is safe against the live backend; run line in its header).
