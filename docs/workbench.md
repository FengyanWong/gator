# GATOR workbench: frontend, run control and data-only outputs

Local web workbench around the existing optimizer. It reads circuits, lets you define
optimization problems by hand or with agent assistance, runs the existing SAC backend, and
saves the raw data and model state needed for research analysis.

It produces **data, configurations, models, netlists and logs only**: no plots, images, PDFs,
spreadsheets or analysis reports are ever written, and the backend installs and imports no plotting library.
One exception ON SCREEN, by user decision of 2026-09-21: the **circuit graph view** (see "Circuit graph view"
below), drawn in the browser with cytoscape (MIT, frontend only, loaded when the view is opened). It is a
diagnostic picture; nothing drawn is written into a run folder or an export, so the outputs stay data-only.

**Where things are described** (this file is long: read only the section you need - `grep -n '^##' docs/workbench.md`
lists every section with its line number; a section says what its feature does NOW):
[Start](#start) ·
[Start, Pause, Resume, Abort](#start-pause-resume-abort-added-2026-09-21-user-request) ·
[What is real and what is mock](#what-is-real-and-what-is-mock) ·
[Connection profiles](#connection-profiles-section-21) ·
[Output layout](#output-layout) ·
[Reward and training conditions](#reward-and-training-conditions) ·
[The right column](#the-right-column-settings-saved-models-and-the-graph-view) ·
[The PDK and what a run writes back](#the-pdk-and-what-a-real-run-writes-back-into-virtuoso) ·
[A task's Virtuoso side](#a-tasks-virtuoso-side-the-cell-it-works-in-saving-the-agent-the-run) ·
[Reload saved data](#reload-saved-data) ·
[Agent providers](#agent-providers) ·
[Code organization](#code-organization) ·
[Tests](#tests)

Workbench code lives in `src/gator_workbench/` and `frontend/`. Optimizer edits require explicit
permission because `training/sac.py::source_digest()` gates checkpoint loading and the M5/M6 audits.
The user granted it for reward v2 (2026-09-26, [plan](plan-reward-v2-real-flow.md)) and reward v2.1
(2026-09-29): their status and evidence are in [reward-v2.md](reward-v2.md), what the page offers is under
"Reward and training conditions" below.

## Start

```bash
# once: the project environment. It lives in the HOME folder (persistent, ext4): /tmp is emptied at every WSL
# boot - on 2026-09-24 that deleted the previous /tmp/analog-optimizer-venv - and /mnt/d would pay the 9p per-file
# toll on torch's thousands of files at every start. This host has no ensurepip and no sudo, so pip is bootstrapped.
python3 -m venv --without-pip ~/analog-optimizer-venv
curl -sS -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && ~/analog-optimizer-venv/bin/python /tmp/get-pip.py
~/analog-optimizer-venv/bin/python -m pip install -c constraints.txt 'torch==2.14.0+cpu' --index-url https://download.pytorch.org/whl/cpu
~/analog-optimizer-venv/bin/python -m pip install -c constraints.txt -e '.[graph,test,export,web,webtest]'
# the pin file is not optional: a saved model loads only under the torch / torch-geometric it was saved with
# (check: torch 2.14.0+cpu, torch-geometric 2.8.0.post1, numpy 2.2.6, networkx 3.4.2 - constraints.txt)

# once (and after UI changes): build the UI. This machine has no Linux node; the Windows
# toolchain works through WSL interop. A native Linux node works the same way.
cd frontend && npm install && npm run build && cd ..

# run (local-only listening by default)
PYTHONPATH=src ~/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8765
# then open http://127.0.0.1:8765 in the Windows browser
```

Options: `--allow-root DIR` adds an allowed **output** root, `--allow-input-root DIR` an allowed
**input** root (it was for the removed netlist import; now it only limits the two file paths an older
configuration may still carry). Roots can only be added by the operator here (or with
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

## Start, Pause, Resume, Abort (added 2026-09-21, user request)

The header has one main run button and **Abort** next to it. The main button changes with the run:

| It reads | Pressing it | What happens in the backend |
|---|---|---|
| **Start** | starts a new run with the configuration on the page | new run directory, detached worker |
| **Pause** | pauses the run | no new simulation is started, the one in flight finishes and is recorded, everything is saved (checkpoint with the full training state), the worker exits |
| **Resume** | continues the paused run | the SAME run directory gets a new segment; network, replay memory, counters and budget are restored and the run goes on where it stopped |

`Starting...`, `Pausing...`, `Resuming...`, `Aborting...` are the waiting states in between. On a real circuit
`Pausing...` lasts as long as the rest of the simulation that is running.

* **Resume and "Mode = resume" are the same machinery, used differently.** Resume is the one-press way for the run in
  the header and does not touch the Mode box. It continues with the settings the run was STARTED with (its own
  `effective_config.json`); edits made on the page while it was paused are not used. Mode = resume + "RL model to
  load" is for picking up an older run, and lets the budget and a few run settings change.
* **Abort** ends the run for good, but gently: it asks first, then lets the simulation in flight finish, saves
  everything and ends the run (`stopped`). Only while a pause or an abort is waiting for that simulation the button
  reads **Force abort**: it waits for nothing, the evaluation in flight is recorded as cancelled and stays charged,
  and on a real circuit a Spectre job already running on the server is not stopped and the schematic can be left
  with the sizes that were being tried. It is for a run that is stuck.
* **Abort on a paused run** deletes nothing and sends nothing: the header lets go of the run and returns to Start.
  The run stays paused on disk and can still be continued from Run status > Continue.
* The header controls ONE run - the one started or resumed from this page, remembered across a reload - and shows
  it as a small text button ("running 12 / 60"; press it to see the run under Run status). It is not the run chosen
  in the list of the bottom tabs: looking at an older run's data never takes Pause and Abort away from a live run.
  While a run is active or paused in the header, "Single baseline simulation" is not available. A finished
  Single baseline simulation of a task saved from a cell records its result as the task's reference by itself
  (status record 7.78): once the run has come to rest the Project column reads the task again and no longer
  says "no real baseline yet".
* A real run asks for the budget again at Resume (what is left of it). A run that was started with checkpoints or
  replay snapshots switched off cannot come back from a pause; Pause says so before it pauses.
* The run commands are in the header only (status record 7.109, 2026-09-29, user decision): the Run status tab's
  copies - Save now, Pause and save, Stop and save, Force cancel - went, as they did what Save now, Pause, Abort and
  Force abort do there. The tab keeps **Continue** (a paused, stopped or interrupted run, with a new total budget) and
  **Export status**. A run that is live when the page opens - started from another browser or the CLI - is taken into
  the header; a second run live at the same time as the header's own has no run buttons on this page.
* The run shown is read every 1.5 s while it can change by itself: a worker is alive, its state is a live one, or the
  header is starting, resuming, pausing or ending a run and it is the run shown (status record 7.115, 2026-09-30; the
  last condition since 7.125 - a finished run in the tabs was read every 1.5 s while the header paused another run). A paused, stopped or
  interrupted run is read every 15 s (another browser may continue it), and an ended one once a minute. Until then a
  paused or stopped run was read every 1.5 s, and each read re-reads its tables.

Browser checks: `frontend/scripts/run_control_check.mjs` (fixtures only, safe next to a live run) and
`frontend/scripts/run_control_live_check.mjs` (real MOCK worker; needs a scratch backend, refuses port 8765).

### Save now (added 2026-09-21, user request)

**Save now** (header, left of the main button; the Run status tab's copy went on 2026-09-29) saves the model of the RUNNING run
without pausing it. It is the run command `checkpoint`: the worker starts no new simulation, lets the one in
flight finish (with several in parallel: all of them), writes a complete save point exactly like an automatic one
(full training state, kind `manual`) and goes on by itself. Nothing is charged and nothing is lost; on a real
circuit the wait is at most the rest of the simulation that is running. The button reads "Saving..." until the run
itself reports that request as written (`manual_save` in `status.json`), then the line under the header says at how
many evaluations and under which id. The save point appears under "RL model to load" as `saved with "Save now"`,
and pruning (`output.keep_last_checkpoints`) never removes it.

It is refused, in plain words, when nothing would come of it: the run is not running (a paused or ended run has
already saved everything), it is already pausing / stopping (that saves by itself; a pending pause, stop or cancel
is never replaced), or it was started with "Model checkpoints" switched off. Browser check:
`frontend/scripts/save_now_check.mjs` (fixtures only, safe next to a live run).

## What is real and what is mock

| Path | Status |
|---|---|
| MOCK tasks: none since 2026-09-30 | The workbench offers no MOCK task since the user's request of 2026-09-30 (record 7.128). The last one, `synthetic:gpdk045_ota5` - the analytic toy backend (`origin=synthetic`) on the netlist and device mapping of the GPDK045 OTA5 - is refused with a plain note, as are the four toy tasks it had replaced on 2026-09-22 (status record 7.59). The toy backend stays for the tests: they register that circuit as their stand-in through `GATOR_WORKBENCH_SYNTHETIC_FIXTURES` (`tests/workbench/fixtures/synthetic_fixtures.json`, set in `tests/conftest.py`), and so do the browser checks' scratch backends (`frontend/scripts/run_checks.sh`). MOCK data stays labelled `provenance=mock`, under `<output_root>/mock/`, out of real aggregates; a model it trains never loads into a real run. |
| `real:gpdk045_*` tasks: none left | The four verified built-in circuits were removed on user request: `real:gpdk045_ota5` and `real:gpdk045_vco` on 2026-09-23 (status record 7.73, their example cells deleted from Virtuoso), `real:gpdk045_ota7` and `real:gpdk045_ldo` on 2026-09-30 (record 7.128, with their example netlists and configurations - so the M5/M6 audits and the frozen M6 plan re-validate from a checkout before that commit). A configuration that names one opens with a plain note and cannot start; the names stay reserved. The real tasks are the ones saved from a Virtuoso cell (next row) and the ngspice ones. |
| `ngspice:<name>` tasks (added 2026-09-23) | A SPICE deck pasted or loaded in the **ngspice netlist...** window and saved as a task. **REAL** circuit simulations by ngspice (`origin=real`, `provenance=real`), on this machine or over SSH through an ngspice connection - no license, no Virtuoso, but counted, authorized (Start asks) and recorded exactly like every real run, so the data is never mistaken for mock data. Its models never load into a MOCK run and the other way round; they are interchangeable with Virtuoso real runs as far as the network contract allows. |
| Arbitrary native cellviews | Read-only browsing through the bridge. Optimizing one needs a saved task, which runs on a WORKING COPY of the cell - since 2026-09-23 the copy you made in Virtuoso and declared on the read; the workbench makes no copy of its own (status record 7.72): a run writes instance values into that copy (the form writer since 7.66), never into your original design, and no cellview is created or redrawn. |

### Choosing a registered task: whose rows Parameters, Probes and Specs show

The three tabs hold rows of the *configuration*, so they belong to a task. Choosing another task in the Project
column (**Registered task -> Task**) brings that task's rows. A fresh page has no task until you choose one (the MOCK task
that used to open there, and the verified OTA7 and LDO circuits with their targets of record, were removed on 2026-09-30,
record 7.128):

| Task | Parameters | Probes | Specs |
|---|---|---|---|
| a profile created from your own cell | the rows the profile fixes | one per result its circuit type produces, ready to carry a target | **none**: requirements are never inferred from a circuit. State yours, or press "Draft with agent..." |

* The **Circuit class / PDK id** labels follow the task at once, and so does a project name that a starter had given
  (`mock-gpdk045-ota5` -> `mscr-ota5t`), so a real run is not filed under `runs/mock_gpdk045_ota5/`. A name you typed
  stays. Choosing a task after a removed MOCK task brings the new task's rows and name at once: no task can run the old
  rows any more (one Undo brings them back).
* Rows are exchanged only while they are nobody's work: empty, or still exactly what the task before had brought.
  **Rows you edited stay**; the panel says so, and **Load task** (there for every task; was "Load starter
  configuration" until 2026-09-24, status record 7.78) exchanges
  them when you want it. One **Undo** takes back a task choice together with everything it brought.
* Run settings are never touched by a task choice, and a real budget is never suggested. Load task keeps them too
  since 2026-09-29 (7.109); before, it reset the MOCK task's budget to 60 and its seed to 17 without saying so.
* A profile created from a cell brings its own result registry (the built-in LDO and VCO tasks brought the registry of
  record of the real cross-category experiment until they were removed). A registry stated in the configuration
  (`run.advanced.spec_registry`) still wins. Units `V/V` and `V/A` (line / load regulation) are accepted.
* In the three editors a field a row does not state is shown with the value the backend uses for it (`hard` on,
  `tolerance` 0, ...), not as an empty or unchecked box.

Browser check: `frontend/scripts/task_rows_check.mjs` (fixtures, safe on the live backend; `--live` reads the real
starters from a restarted or scratch backend). Tests: `tests/workbench/test_wb_real_starter.py`.

### Specs are equations over Probes (added 2026-09-21, user request)

**Probes** say what is measured. **Specs** say what is required, and each one judges ONE value: its
`equation`, written with Probe IDs. The simplest equation is one Probe ID (`m_unity_gain_hz`), and every
starter row is of that kind. A formula works too: `m_supply_power_w / m_osc_frequency_hz` is the energy per
cycle, in J. Allowed: Probe IDs, numbers (with SI suffixes such as `2u`), `+ - * / **` and brackets. There
are no functions (`abs`, `log10`...) yet. A missing or invalid probe, or an operation that fails (for
example a division by zero), makes the spec invalid; it never becomes a number, and an invalid hard spec
means the evaluation is not feasible.

That one value is what everything sees, under the spec's name (`metric_id`): the reward, the network's
goal input, the independent pass/fail check, the best-design choice and the tables. This closes a gap found
the same day: a spec named `unity_gain_hz` could point at a probe that read the 3 dB bandwidth. The reward
then read the unity-gain frequency while pass/fail read the bandwidth, and validation let it through.

* **Names.** A spec may carry the name of a result the simulation returns only when its equation is exactly
  the probe of that result (`spec_name_is_a_result`), and the name of a Probe only when its equation is
  that probe (`spec_name_is_a_probe`). Give a formula its own name, such as `energy_per_cycle`.
* **Units.** When the equation is one probe, its unit is checked against the probe's. A formula's unit
  cannot be checked (`equation_unit_unchecked`, a warning): the probes enter in their canonical units (W,
  Hz, V, A, s), so `W / Hz` gives `J`. Energy units (`J`, `pJ`, `fJ`...) are accepted.
* **The network's result registry.** A spec name the registry does not know adds one entry to it
  (`spec_adds_registry_entry`, info). Its reference magnitude, which only scales the network input, is the
  formula evaluated on the reference sizes of its inputs, so changing a limit keeps saved models loadable.
  Adding, removing or renaming such a spec changes the network's input: models saved without that spec do
  not load into the run, and its models do not load into one without it. A registry stated in the
  configuration (`run.advanced.spec_registry`) is taken as given; there, an unknown name is still a blocker.
* **Tables.** A spec whose equation is one probe keeps the metrics row it always had (`measurement_id` =
  the probe). A formula's row has no `measurement_id` and `aggregation = equation`. Probes that no spec
  shows whole get rows of their own. The simulator's own results (`aggregation_level = condition`) are
  unchanged; recording a baseline reads only those.
* **Real runs.** When every spec is a simulator result itself, the verified real factory runs exactly as
  before. Otherwise `spec_equations.EquationNativeFactory` wraps it: the same environment and backend, and
  the formulas' values are added to each simulation result inside the lane. The worker's first-evaluation
  check against the recorded real baseline still compares the simulator's own results only.
* **Older configurations** named one probe in `measurement_id`. They load with that probe as the equation,
  in the backend and in the browser's saved copy, and their configuration and task hashes are unchanged,
  so earlier runs still resume and their checkpoints still load.

Code: `src/gator_workbench/spec_equations.py`; tests: `tests/workbench/test_wb_spec_equations.py`.

### Fewer columns in Parameters, Probes and Specs (2026-09-26, user request)

Fourteen columns went, because no run ever read them - and for several the only value besides the default was a run
blocker. Parameters lost `name`, `target_kind` (its other value, a design variable, blocked the run), `candidates` with the
`discrete` value type (a candidate list ran only when it was a uniform grid, which is `lower`, `upper` and `step`), and
`relation` with `expression` (an expression ran only when it equalled a constant times the leader, which is `ratio`).
Probes lost `function`, `window`, `at_frequency_hz`, `integration_band_hz`, `branch_direction`, `loop_definition` and
`crossover` (no backend extracts anything from them; a filled `function` blocked the run), `on_failure` (one allowed value)
and `validity` (checked for form only; run-time validity comes from the simulator's own flags). Specs kept every column.

What stays but steps back: `soft_weight`, `active` and `basis` of Specs are
shown after **More columns** at the right of the toolbar (the choice is kept in the browser). They keep their values either
way: Add fills them, the agent may set them, a task file stores them. `initial_value` is shown and not typed: the circuit
read fills it, and a typed value could only differ from the circuit. `normalization_scale` may be left empty: the violation
is then divided by the size of the threshold (the largest of |lower|, |upper| and |target|, or 1).

Old rows still load. A task file, a run's `effective_config.json` or an imported JSON written with the retired columns is
read as before: the schema drops them when it reads a row (`schema.RETIRED_PARAMETER_FIELDS`,
`RETIRED_MEASUREMENT_FIELDS`), keeps what they meant (an expression relation becomes the ratio, a uniform candidate grid
becomes lower/upper/step) and refuses in plain words what the run refused before (a design variable, a non-uniform candidate
list, any other expression). Both hashes see the retired columns at their old defaults (`schema._hashed`), so every earlier
run resumes, its checkpoints load, its task keeps its `task_id` and approvals still bind - checked against the three runs on
this machine and the MOCK starter's documented task hash (`5f181ef3...`). The browser's copy of the rows is migrated the
same way when the page loads (`store.ts migrateConfig`), so the editors' rows equal the rows the backend serves; a value the
browser cannot keep is written into the row's notes.

**The Probes' `conditions` and `aggregation` went too (2026-09-29, user request, record 7.105).** They were to name the
test conditions a probe is measured under and how its values there combine (nominal only, worst case, mean, min, max).
No run ever used them: anything but `["nominal"]` / `nominal_only` was refused before the run (`nominal_only_backend`),
and since reward v2 the test conditions are chosen for the whole run (**Training conditions**) and per spec (**Judged
at**: nominal, or every planned corner with the worst one counting). They are retired like the fourteen above (in
`RETIRED_MEASUREMENT_FIELDS`, dropped whatever they say, hashed at their old defaults), so the Probes tab has no **More
columns** any more; a probe's aggregate row in the results tables still reads `aggregation = nominal_only`
(`engine.PROBE_AGGREGATION`). The task and configuration hashes of all 14 workbench runs on this machine (5 in
`outputs/`, 9 kept as evidence in `artifacts/local`), of the 4 saved task files, of the old-format fixture and of the
registered tasks' starters are the same before and after.

### Matched devices: ties suggested from the circuit (added 2026-09-29, user request)

**Matched devices...** in the Parameters toolbar reads the loaded circuit for the structures whose devices must be
sized together, and suggests tying their rows: the follower row gets `binding_group` = the leader and the `ratio` the
circuit has now. The idea comes from netlist-crawler (Token Zhang's MIT tool that labels differential pairs, mirrors, tails,
loads and cascodes for an LLM); the rules run on the workbench's own circuit graph instead. There, the kind (nmos / pmos)
and every pin's role come from the verified device mapping, never from an instance name, so an instance called `TAIL` or
Virtuoso's `NM0` is read like any other. And a pair has to share a tail node, not a rail: a PMOS pair that only shares
VDD is no differential pair. That is the mistake netlist-crawler made on the OTA7 (M6 with M3 and M4), the LDO (MP with M3
and M4) and the VCO (three ring PMOS). Found:

| Structure | Rule | Tie ticked? |
|---|---|---|
| differential pair | same type and model, one source, two gates, two drains; on the shared source only the pair and what is below it (a drain of the pair's type, a current source, a resistor) | yes |
| cross-coupled pair | the same, each gate on the other's drain; may sit on a rail | yes |
| tail current source | the transistor below a differential pair | listed only |
| current-mirror load, matched loads | two devices sharing a gate (and a source) whose drains are the two branches of a matched pair; a mirror when one is diode-connected | yes |
| matched cascodes | two devices sharing a gate whose sources (or, above loads, drains) are the two branches; followed on to the far side | yes |
| bias mirror | a diode-connected reference and its copies (one gate, one source) that load no pair | offered, not ticked: its ratio sets a current, which may be a design variable |

A width follows in the ratio the circuit has (a 2:1 mirror stays 2:1); a length, finger or multiplier row is tied only where
the circuit's values are equal. A device of a pair that has no row gets a follower row right after its leader's group; a row
that already follows the same leader is shown as kept, and one tied elsewhere by you is left alone. The box lists the
structures in plain sentences and one line per row it would change. **Review...** shows the diff, the count of
independent action variables before and after, and any validation error; only **Apply** changes the rows, and **Undo** in
the toolbar takes it back. The box asks once per press: an answer about rows that changed since says so and offers **Find
again**. Nothing is simulated or stored.

Where it applies: a cell read from Virtuoso (the ties go into the task at **Save task**), a task you saved (save it again
afterwards: a task runs with the rows it was saved with), an ngspice task (its rows start one per size, so the pair and the
load of the example OTA go from 7 to 5 independent variables), the MOCK task. A **verified** built-in task
(there is none left since 2026-09-30) fixed its rows: the structures were listed for information and nothing offered.
The agent sees the same sentences: `circuit_summary` carries them as `structures`.

Backend `structures.py` (`recognize`, `plan_ties`, `apply_ties`), route `POST /api/parameters/matched` (`{config, apply}`;
local files only). Tests: `tests/workbench/test_wb_matched_devices.py` (the circuits of record, hand-made netlists with
non-M names and unlabelled rails, a folded cascode, a 2:1 bias mirror, kept and foreign ties, the route). Browser check:
`frontend/scripts/matched_devices_check.mjs` (25 checks, hermetic, answered with `frontend/scripts/fixtures/matched_devices.json`
= the real route's answers for its seed).

### Spectre netlist import: removed

The Project column offers the **Registered task** list; a Virtuoso cell is read in the **Virtuoso cell...**
window (since 2026-09-23, user request; until then a **Circuit source** list offered both). A third source,
"Import Spectre netlist" (a `.scs` file plus a device-mapping JSON, MOCK runs only), was removed on user
request (2026-09-21, status record 7.53).

A configuration saved before still says `source: netlist` (the browser's saved copy, an imported
JSON file, a run's `effective_config.json`). It still opens, with the same hashes. The Task list
then shows no task ("the saved source was removed") and a note names the saved file; nothing is loaded
from it and a run cannot start from it (the backend answers "The workbench no longer imports Spectre
netlist files..."). Choosing a task also drops the two file paths from the configuration.

Netlists as such are still used: the MOCK task is the OTA5's netlist, and a Virtuoso cell is read
through Virtuoso's own netlist export. The best design is written as `optimized_dut.scs` only when
every varied device is a top-level instance: a device inside a subcircuit (the OTA5's `XU1/M1`, real
or MOCK) would mean editing a definition every instance shares, so the file is not created and the
run's `artifact_manifest.json` says why; `parameters.csv` always holds the values. The agent's circuit-modification working copy is still written, but only as a
file for your records: the workbench cannot load it as a circuit any more.

### An ngspice netlist as a task: the ngspice window (added 2026-09-23, user request)

The Project column's second one-button window, **ngspice netlist...**, takes a SPICE deck - pasted into its text box,
or loaded from a file on the backend machine (a path under the allowed input roots, `--allow-input-root`; a Windows
path is converted for the WSL backend; **Example** loads `examples/circuits/ngspice_ota5_level1.cir`, a
five-transistor OTA on textbook level-1 models with no PDK at all) - and saves it as the task `ngspice:<name>`.
The Project column then follows that task: Parameters and Probes show its rows, Specs is yours to fill. Saving the
same name again stores the next revision (the deck before is kept as `history/r<N>.cir`); runs made before keep
their own copy of the deck in `input_snapshot/netlist.cir`, and a changed deck is a changed task. **Check** reads
the deck on the backend without keeping it and says what it found: elements by kind, the values a run can vary,
the results it measures (with a unit guessed from the result's name or its expression: `gain_db`, `ugf_hz`,
`v(out)` -> V, `i(vdd)` -> A - edit the Probes row when the guess is wrong), the analyses, includes, diagnostics
and, in plain words, what would stop a run. **Delete task** (in the column's task row, at the right of Load task,
for the task the page follows) takes
it out of the list; its folder is kept aside on the backend machine. Nothing in the window runs a simulation.

**Which launcher the column shows follows the connection in use** (user request 2026-09-23): with a Virtuoso
connection chosen (the "Connection" button) the column offers **Virtuoso cell...** only, with an ngspice connection
**ngspice netlist...** only; with no connection chosen, or one of a kind the page does not know, both. The family is
read from the connection list (the workbench's own file, no probe) when the connection changes. The Registered task
list follows the same rule for the ngspice tasks (user request 2026-09-24: the ngspice OTA example is to show only
while ngspice is connected): while a Virtuoso connection is in use they are left out of the list, except the task the
page follows, which stays listed and chosen (marked `[ngspice: choose its connection]`). An ngspice task the
page follows keeps its block in the column either way; its deck is edited through the ngspice window, so switch to
an ngspice connection to edit or run it.

What the deck must contain, and what the workbench makes of it (`src/gator_workbench/ngspice_netlist.py`):

* SPICE syntax as ngspice reads it: the title line first, elements `R C L M X D Q J V I E G F H B S`, `+`
  continuation lines, `*` / `$` / `;` comments, `.subckt`/`.ends` with `params:`, `.param` (also inside a
  subcircuit), `.global`, `.include` / `.lib`, SPICE numbers (`4u`, `1Meg`, `1M` = milli, `10uF`), `{expressions}`
  over parameters (a whitelist evaluator with ngspice's arithmetic functions, never `eval`), and `.end`.
* **Results**: `.meas` statements, or in a `.control` block `meas ...`, `let x = ...` + `print x`. Their names are the
  Probes rows (`source_name`); a run reads the `name = value` lines ngspice prints (`.meas` names come back in
  lowercase; a failed measurement is missing, never a number). ngspice has no `.meas op`: read operating-point
  values in a control block (`op`, `let`, `print`). The example does exactly that, plus `set units=degrees` so
  that `vp()` gives degrees.
* **What the network sees**: the standard vocabulary (nmos, pmos, resistor, capacitor, inductor, vsource,
  isource, unknown). The kind of a MOS comes from its `.model` line - in the deck or in the files it includes,
  which are read for their `.model` and `.subckt` lines only (never copied, shown or sent anywhere; up to 48 MB
  of them). A diode, a bipolar, a behavioural source, or an instance of a subcircuit the deck does not define (a
  PDK cell such as `sky130_fd_pr__nfet_01v8`) is `unknown`, a warning, not an error: ngspice simulates it either
  way, only an unknown device cannot be sized. The window's "Models the deck does not define" box declares kinds
  for those (`name=nmos name2=pmos`), saved with the task.
* **Sizes a run can vary**: a numeric value of a top-level element (W, L, M, NF of a transistor; the value of an
  R, C, L, the DC value of a source), and of an element inside a subcircuit the deck instantiates **exactly once**
  (a testbench around one DUT). Inside a subcircuit used twice the value is shown but not offered - writing the
  definition would change every instance. The starter rows: widths, resistances, capacitances and inductances
  optimized within half..twice their present value, lengths, counts and sources fixed; all editable, as always.
* **Writing back**: each evaluation replaces the value's own token in the deck (`W=4u` -> `W=4.5e-06`, `{wn}` ->
  the number, `1k` -> `1500`) and nothing else, then reads the deck again to prove the write (the environment's
  usual contract check). The best design is written as `best_design/optimized_dut.cir` the same way - also for
  values inside the once-used subcircuit, which the Spectre exporter refuses.
* **Files**: on this machine, relative `.include` / `.lib` paths are resolved from the folder the deck was loaded
  from (ngspice itself resolves them from ITS working directory, so the run makes them absolute in the deck); a
  pasted deck has no folder, so write absolute paths. Over SSH the deck is sent in on stdin and every path in it is
  a path on that machine. The workbench copies no model file anywhere.

How a run works (`src/gator_workbench/ngspice_backend.py`, `ngspice_tasks.py`): the task is a **real** task of the
connection family `ngspice`. Start needs an ngspice connection chosen in the Connection window ("ngspice on this
machine" or "ngspice over SSH"; the column says so when the connection in use is a Virtuoso one, and the Task list then
lists no ngspice task but the one the page follows, marked "choose its connection"),
its four-layer test as the gate (the program answers, the built-in divider solves), and the confirmation of the
number of simulations that Start asks for (the same consent as for every real run; no license or budget is spent,
but every evaluation is counted as real). Each evaluation is one `ngspice -b` process on the written deck: on this
machine in the job's own folder; over SSH through `ssh -o BatchMode=yes -- <host> '<fixed command>'` with the deck
on stdin into a `mktemp -d` folder that the same command removes. Its output is kept as `ngspice.log` next to the
deck. Outcomes: the results it prints are the evaluation; a solver failure (timestep too small, singular matrix,
no convergence) is a NONCONVERGED design that was evaluated (reward -1); a deck error, a missing program or a
broken ssh link is an infrastructure failure that evaluated nothing; a timeout is retryable within
`max_retries`. The nominal condition recorded with every evaluation is what the deck states: its temperature
(`.temp` / `.option temp`, else 27 C) and its largest DC voltage source. Concurrency: up to half the CPU cores
(8 at most) on this machine, 4 ssh sessions. Corner checks are not available for these tasks (the Corner check
tab says so): they simulate through the Virtuoso profiles.

Where things are: the task store `configs/local/workbench/ngspice/<name>/` (`netlist.cir`, `task.json`,
`history/`, deleted tasks under `.deleted/`); routes `POST /api/ngspice/read` (a file inside the input roots),
`POST /api/ngspice/check`, `POST /api/ngspice/task/save`, `GET /api/ngspice/task?name=`, `POST
/api/ngspice/task/delete`; the window `frontend/src/panels/Ngspice.tsx`. Tests: `tests/workbench/test_wb_ngspice.py`
(fakes, plus two tests marked REAL that run the ngspice installed on this machine on the example deck - skipped
without one). Browser check: `frontend/scripts/ngspice_window_check.mjs` (fixtures, safe on the live backend).

**Installing ngspice on this WSL** (2026-09-23): Ubuntu 22.04's package is ngspice-36; the latest release,
ngspice-47, was built from source into `~/.local/opt/ngspice-47` with a user-local conda-forge C/C++ toolchain
(`~/.local/share/gator-ngspice/toolchain`, needed at run time for `libgomp` / `libreadline`) and linked as
`~/.local/bin/ngspice` - no root, nothing system-wide. `sudo apt install ngspice` gives the older 36 instead.

### Browsing a Virtuoso library: the Virtuoso window

The Project column holds the project fields and the registered task only (user request 2026-09-23). Its
**Virtuoso cell...** button - one short button, with what it is for as text beside it - opens the **Virtuoso
window**, a browser window of its own like the connection window (needs a connection profile and a link
that is up; allow pop-ups if the browser blocks it). There is nothing to press: opening the window lists
the libraries, choosing a library lists its cells, choosing a cell reads its schematic. Each step is a
gated, read-only, zero-cost bridge call and waits for the one before it. **Refresh** repeats the chain, for
example after the link came up or the design changed in Virtuoso. A library chosen in the window makes
the page follow the Virtuoso cell instead of the task: the column's Task list then shows none and names
the cell beside the button. Choosing a task in the column makes the page follow the task again, and the
window then starts from a blank library. Closing the window loses nothing.

The column and the window keep their explanations folded: a line with a small triangle ("Labels: class
..., PDK ..." - the column's circuit class, PDK id and DUT hierarchy boxes are one closed line naming their
values -, "Why: it has no circuit profile yet", "What the check compares", "2 notes on this circuit", ...)
opens on a click. Headlines, warnings and buttons are always in view.

The **Hierarchy** block at the end of the column (of the window, for a cell read from Virtuoso) is folded
the same way: one closed line, "Hierarchy
(N instances)". A click shows the instance tree and, under it, two more closed lines: **Instances
and parameters** (the sizes as the workbench uses them) and **Native schematic** (what was read
straight from Virtuoso, as read). While no circuit is loaded - the browse-only case - there is no
Hierarchy block and Native schematic stands alone. Hierarchy and Native schematic stay as you left
them, open or closed, from circuit to circuit. A warning about unmapped devices and the "N
diagnostics" line are not folded away: they appear under the Hierarchy line when there is something
to say.

* No view is asked for: the bridge reader always opens the view named `schematic` (read-only, and
  closes it again). A cell without a schematic view is listed but cannot be chosen; the panel shows
  which other views the chosen cell has.
* **Circuit class** (opamp, ldo, vco, ...) and **PDK id** (e.g. `gpdk045`) are labels saved with
  every run: they group the research tables and let the validator check a claim such as "unseen
  circuit class". They change neither the simulation nor the optimization, and `unspecified` is fine
  for a single run. The PDK id is filled in from the library's technology library unless you typed
  one.
* A cell is **browse only** until it is saved as a task (below). The note above **Read this cell into the
  workbench** warns, in view, that the workbench writes into the cell it reads: work on a copy.
* **Testbench cell**: a cell named `tb_<cell>` (the `tb_` prefix in any case, the cell name exact, with
  a schematic) is chosen by itself when you pick the cell, or when the cell list arrives while the box
  is empty ("Found by its name"); choose another one or (none) at any time. A testbench chosen by hand
  stays when the next cell has no `tb_` of its own. A task needs one: it simulates the testbench, not
  the bare cell, and keeps its Maestro test there.
* **Probes follow the testbench**: once the cell was read through a testbench, the **Probes** tab gets
  the results of the circuit type that testbench fits, each with its `signal` - where in THIS testbench
  it is read: the output net (`OUT`), the ring nets, or the supply branch (`V0:p`, the current through
  the supply source `V0`) - and Save task measures the task by that circuit type. This happens only after your own
  choice of library / cell / testbench or a Read press, never on page load, and only over rows that are
  nobody's work: empty, brought by an earlier testbench, or still exactly the rows the last registered
  task brought (that task's untouched targets then leave **Specs** with them). Rows you edited stay,
  and the note offers **Use testbench probes**. Undo takes an exchange back. A testbench that fits no
  circuit type brings nothing; the note says why. The rows describe the copy that was read: after
  choosing another testbench, press **Read the cell again**. The circuit type decides how each result
  is measured, so editing `signal` does not move it.
* **Read this cell into the workbench** (first step towards a task for your own cell; explicit press,
  read-only, some seconds). The first read of a cell ASKS whether it is a copy you made (the workbench makes
  no copy of its own since 2026-09-23 - see "The cell the task flow works in" below): Cancel reads nothing,
  OK reads it and makes it the cell the task flow works in. Virtuoso exports the netlist of the testbench
  cell and the device sizes are read. The cell's PDK is read in the same press (since 2026-09-27; see "The
  components the network knows" below): a line under the buttons says what came of it, and the PDK's component
  list can then be chosen in the RL network block. The export is kept under
  `configs/local/workbench/native_cells/<library>/<cell>/`, and the cell then loads from it without
  contacting Virtuoso: you can look at it, fill the three editors (the centre tabs, in this order:
  **Parameters** = what may vary, **Probes** = what is measured and how, **Specs** = equations over
  those probes and the limits they must meet) and
  **Ask the agent to set up** - the Agent tab opens with the request written out; its proposal, once
  approved there, fills the editors and is written into that cell's Maestro view (see "The agent sets the
  task up" below). Device types this project has not verified (for example the MIM invented model) are shown
  with unnamed pins. Such a cell still cannot run: Start stays disabled (`circuit_profile_missing`) until
  it is saved as a task.
* **Save task** (at the right end of the editors' tab line since 2026-09-22; the note points there) replaced the
  former **Create profile** form on 2026-09-22 - see "Saving a task" below. A Parameters row is accepted only
  when a real run can write it, for instances directly inside the cell: widths of single-finger, m = 1
  transistors keep the verified width writer, and since 2026-09-22 (status record 7.66) any other value the
  PDK's property form lets a user type goes to the form writer (see "What a real run writes" below). A range
  must contain the present value and is snapped onto the grid the PDK keeps (the editor then shows it exactly
  as registered); anything else is refused with the reason. The cell
  becomes the task `real:<name>` under **Registered task** (files in
  `configs/local/workbench/profiles/<name>/`) and stops being browse-only.
  A cell that already has a registered task - one saved from it, or one of the verified built-in
  circuits (`real:gpdk045_ldo` for `ldo_m6_v1`, ...; the library is the one the Virtuoso connection
  states) - shows "This cell already has a registered task: `real:<name>`" and says to choose it under
  **Task** in the Project column (its **Open** button went on 2026-09-29, 7.109); change it there
  (Save task); another task needs another copy of the cell, made in Virtuoso and read in
  the window. A built-in circuit gets no second task.
  **Delete task** (in the column's task row, at the right end next to Load task since 2026-09-24 - before
  that the last line of the task's block; asks once more; was: Delete profile):
  the task leaves the list, its name is free again and the cell is free for the next Save task.
  Nothing is erased: the folder moves to `configs/local/workbench/profiles/.deleted/<name>.<time>/`,
  its recorded baseline included (a new task needs a new real baseline). Runs already made keep their
  data, but a paused one can no longer be resumed. Refused while a run of the task is working, and for
  the built-in circuits.
  Circuit types (how a task measured by the workbench itself measures; they go once tasks measured by
  Maestro can run): *Ring oscillator (free-running)* - a transient from declared start voltages, metrics
  `osc_frequency_hz`, `supply_power_w`, `supply_current_a`, swing, duty cycle, period spread, startup;
  *Op-amp / OTA (AC gain)* - only for a testbench that follows the verified OTA's net names.
  Targets of a generated task use the result names as `metric_id` (`osc_frequency_hz`, ...): the profile
  registers exactly these results for the optimizer's goal input, so nothing has to be added under
  `run.advanced.spec_registry`.
  **Where a real run writes.** A task saved with Save task names the cell the flow works in - since
  2026-09-23 the copy YOU made and declared when it was read; before that a copy the workbench made
  (`<library>_GATOR`) - so its runs write into that cell (every evaluation, the baseline included, re-applies
  the sizes through the PDK callbacks, checks and saves the cellview; the original sizes are written back when
  the run ends; a forced abort can leave them changed) - keep that cell closed in Virtuoso during a run. A task
  made with the former Create profile has no working copy: its runs write into the cell it was made from.
  First real simulation of a generated profile: 2026-09-21, one authorized baseline of the 3-stage ring
  oscillator, 1.2092 GHz, cell identical before and after (status record 7.24). In this order:
  1. **Check now** - the check before every run (below): the editors against the saved task, and
     everything a real evaluation does before Spectre starts (connect through the run adapter, export,
     compare with the record, write the deck). Free, read-only; needs the link up and no ADE/Maestro
     window open on the design. Start runs it by itself as well.
  2. **Single baseline simulation** in the header - one real Spectre run; asks for your budget. When it
     finishes, its result is recorded as the task's reference BY ITSELF (status record 7.78, 2026-09-24):
     from then on every run compares its first evaluation with that result, as the verified profiles do.
     Recorded once, never replaced. A refused measurement (incomplete, invalid) is named in the column
     with its reason instead of the standing advice. A baseline made before 7.78 - or one whose worker
     could not record it - is adopted when the task is next loaded: the newest completed one of the
     task under the remembered output root, provided the task was not saved again after it.
     The former third step, a **Record the baseline run as reference** button for a run made another way,
     went on 2026-09-29 (status record 7.109); the route below stays for scripts.

`POST /api/virtuoso/libraries | cells | read | import`, body `{"profile_id", "library"?, "cell"?, "testbench"?}` (import:
`"work_here"?` - the user said the cell is a copy they made; the answer then carries the `working_copy` record);
`POST /api/virtuoso/profile/reference` `{"name", "run_dir"?}`; `POST /api/virtuoso/profile/delete` `{"name"}` (answers
with the task's own cell - never a working copy the workbench made - and the page then follows that cell). A task is
saved with `POST /api/virtuoso/task/save` (section "Saving a task"); the older `POST /api/virtuoso/profile` (Create
profile) and `/profile/preflight` routes are gone (entries 7.57, 7.64).

## Connection profiles (section 2.1)

`configs/local/workbench/bridge_connection.json` (git-ignored; operator-owned):

```json
{"active": "lab",
 "profiles": {"lab": {"env_file": "/home/me/.virtuoso-bridge/.env", "profile": null,
                      "bridge_site_packages": "/home/me/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages",
                      "library": "MY_LIB",
                      "model_file": "/remote/pdk/models/spectre/model.scs",
                      "circuits": {
                        "gpdk045_ota7": {"creation_receipt": "/path/ota7/creation.json",
                                         "reference_measurements": "/path/ota7/measurements.json"},
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

The check guarding a cell read or write (the gate before an import, a Save task or a Check now) reuses a passing check
of the same connection from the last 30 s instead of testing again (status record 7.115). Before, a single Save task
tested the connection two or three times, about 0.9 s each. Conditions for the reuse:
- every layer that gate needs was ok;
- the connection kind is the same;
- no run has started or ended in between.

A failed or uncertain result is never reused, and a real simulation always tests afresh. If the link is lost within
those seconds, the step that then works on the cell reports the bridge's own error instead of the gate's.

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

With no connection yet, the connection window opens with its **Add a connection** form (the same form
**Add a connection...** opens later; see the kinds below). For a Virtuoso kind it locates
`~/.virtuoso-bridge/.env` and the bridge's site-packages on the backend host (the name it suggests for
"Virtuoso over SSH", the preselected kind, is `lab`), and **Create connection** writes
the profile (`kind`, `env_file`, `profile` - `null` unless a bridge profile is named - and
`bridge_site_packages`). The env file is located, never read; the browser sends only names; connections that
exist are never changed (see "Changed promise" below). Real-simulation tasks also need `library`,
`model_file` and the per-circuit `circuits` entries shown above, added by hand.

**One test when the page opens, then only on a press** (user request 2026-09-24, status record
7.80; from 2026-09-20 until then nothing ran on load - "only check connection when I press the
button"): when the page opens it tests the connection in use once, as soon as the connection list is
read and names it - the same test as **Test connection** (read-only, zero-cost, one SKILL round
trip; for ngspice the built-in test circuit; with a run active the probe does not touch Virtuoso) -
and the button in the column reads "testing..." meanwhile, then the result. Nothing else runs on
its own: a connection chosen later shows the backend's last result once (a cache read, no probe),
opening the window checks nothing, and no timer polls (the old panel polled every 15 s). A press -
Connect SSH, Test connection or + Spectre / license - runs a check as before. `serve` does not
check at start either (`--connection-check-on-start` brings that one cheap check back). A result
stays on screen with the clock time of its test ("tested at 21:04:13")
until the next press - it is the result of that moment, not a live indicator, and it no longer
turns to `unknown` by itself after `--connection-stale-seconds` (a page reload still shows an old
result as `unknown`). Unchanged and independent of the panel: the gate probes the link afresh
before every real action (read/write a cellview, real simulation), whatever the panel shows.

What did NOT change: a check still never starts anything (`connection.py` cannot, and a test pins
it); nothing ever stops or restarts a tunnel, the daemon or Virtuoso. The starting code lives apart in
`bridge_connect.py`. Connect attempts are logged to `configs/local/workbench/connection_actions.jsonl`.
Endpoints: `GET /api/connection/setup`, `POST /api/connection/profile`, `POST /api/connection/connect`
(the body of `connect` is `{"profile_id": ...}` and nothing else; `profile` is described below).

### "Connection": one button, a window, four kinds of connection (2026-09-21, user request)

The block is no longer called "Virtuoso bridge connection" and no longer fills the left column: it
is **one button, "Connection"**, which names the connection in use, its kind and the state of the
last test. Pressing it opens the **connection window** - a browser window of its own that holds
everything described above (allow pop-ups for the page if the browser blocks it; the button then
says so). Opening the window checks nothing; every rule above about button presses still holds.
Closing the window loses nothing, and the button opens it again.

A profile now says WHAT it connects to and HOW, with `"kind"`:

| `kind` | What it is | Steps in the window |
|---|---|---|
| `virtuoso_ssh` (the default when `kind` is absent) | Virtuoso + Spectre on another machine, through the bridge's SSH tunnel | 1 Connect SSH, 2 load the line in the CIW, 3 Test |
| `virtuoso_local` | Virtuoso + Spectre on the **same machine as the workbench backend**: the bridge's local mode, no SSH, no tunnel | 1 Set up local bridge, 2 load the line in the CIW, 3 Test |
| `ngspice_local` | the `ngspice` program on the backend's own machine | Test |
| `ngspice_ssh` | `ngspice` on another machine, run through `ssh` | Test |

```json
{"active": "lab",
 "profiles": {"lab":  {"kind": "virtuoso_ssh", "env_file": "...", "profile": null, "...": "..."},
              "here": {"kind": "virtuoso_local", "env_file": "/home/me/.virtuoso-bridge/.env", "profile": "local"},
              "sim":  {"kind": "ngspice_local", "ngspice_bin": "/opt/ngspice/bin/ngspice"},
              "far":  {"kind": "ngspice_ssh", "ssh_host": "simhost"}}}
```

* **Virtuoso on this machine.** Where Virtuoso runs is decided by the bridge env file, as before
  (`VB_REMOTE_HOST=localhost`, or `VB_REMOTE_HOST_<name>=localhost` for a named bridge profile, means
  this machine). A DECLARED kind must agree with it: if the profile says "this machine" and the env
  file names another one (or the reverse), both the test and the set-up button stop at the profile
  layer with `kind_mismatch` and start nothing - "this machine" can never open a tunnel somewhere
  else. A profile without `kind` is not second-guessed; the window then words itself after what the
  test found. A local bridge that was never set up is reported as such (`local_bridge_not_set_up`,
  "click Set up local bridge"), no longer as a CIW that does not answer.
* **ngspice.** Four layers: `connection_profile` -> `ssh` (`not_applicable` on this machine) ->
  `ngspice` (the program is found and answers `--version`) -> `trial_run` (it really solves ONE fixed
  three-element divider written by the workbench: v(out) = 0.5 V). That trial is to ngspice what the
  `1+1` SKILL round trip is to the CIW; it is never one of your circuits, costs no budget and needs no
  license. Nothing is installed, started or left running; over SSH the deck goes to a `mktemp` file
  that the same command removes. `ngspice_bin` (optional) is a program name or path; `ssh_host` is a
  Host name from `~/.ssh/config` (recommended: port, user, key and jump host stay in that file) or
  `user@host`. Both are checked against a strict pattern before anything runs, are passed as argv
  entries (`ssh -o BatchMode=yes -o ConnectTimeout=8 -- <host> <fixed command>`, no local shell) and
  never appear in a result or a log. SSH is batch mode: key-based login and an accepted host key.
* **What an ngspice connection runs: the ngspice netlist tasks** (since 2026-09-23; see "An ngspice
  netlist as a task" above). A real run of such a task probes the four layers as its gate. Reading or writing a
  Virtuoso cell on an ngspice connection is still refused without probing (`blocking: ["connection_kind"]`, with
  the sentence to show), a Virtuoso task started on an ngspice connection is refused in words before anything is
  probed, and so is an ngspice task on a Virtuoso connection. The GPDK045 models are Spectre-format files: an
  ngspice deck needs models ngspice can read (its own `.model` lines, or an open PDK's files).
* **The ngspice agent aid is under construction** (a note under the ngspice steps, user request 2026-09-24):
  the agent's setup help - reading a circuit and proposing its parameters, probes and specs - works for Virtuoso
  cells only so far; an ngspice deck is set up by hand in the ngspice window.
* **Add a connection** (in the window). `GET /api/connection/setup` reports, per kind, what was found
  on the backend machine (bridge env file and package; the `ngspice` and `ssh` programs; the Host
  NAMES of `~/.ssh/config` - names only, the rest of that file is never read out).
  `POST /api/connection/profile` takes `{"profile_id", "kind", "ssh_host"?, "bridge_profile"?}` -
  names only. `ssh_host` must be one of those Host names, so the browser can never point the backend
  at a machine this host does not already name; an address, a port, a path or a command is rejected
  (422). **Changed promise:** the connection file used to be "never overwritten"; now a new connection
  can be ADDED to it. Connections that exist are never changed or removed, every other key is written
  back as it was, `active` is kept, the previous file is kept next to it as
  `bridge_connection.json.before-<UTC>-<name>`, an existing name is refused (`profile_exists`) and a
  file that cannot be read is never replaced. Editing or removing a connection stays a hand edit.
* `POST /api/connection/connect` answers `409 nothing_to_connect` for an ngspice connection.

Code: kinds, per-family layers, monitor and gate in `connection.py`; the ngspice layers in
`ngspice_link.py` (kept apart so that what `connection.py` may do stays pinned by its own test);
creation and the sentences in `bridge_connect.py`; the button and the window in
`frontend/src/panels/Connection.tsx`. Tests: `tests/workbench/test_wb_connection_kinds.py`; browser
check `frontend/scripts/connection_panel_check.mjs` (fixtures; `GATOR_CONNECTION_LIVE=1` adds a live
section for a scratch backend only).

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

### The run window: which run the bottom tabs show (added 2026-09-21, user request)

At the right end of the bottom tab strip there is one button, **Runs...**. It replaced the drop-down list of runs. To
its left, as plain text, stands the run that Run status, Logs, Data tables and Output files are showing (start time |
task | mode and seed | state; "No run selected" when there is none). Pressing the button opens the **run window**, a
browser window of its own that can stay open next to the workbench (allow pop-ups for the page if the browser blocks
it). The window lists every run under the output folder, newest first, one row per run:

| Column | What it says |
|---|---|
| Started | When the run was created. All times are the local time of this computer. |
| Finished | When the run came to rest: completed, stopped, failed. A paused run shows the time with "(paused)"; a run that is working reads "still running"; a run whose worker died wrote no end, so it reads "last seen ..." (its last sign of life). |
| Duration | How long the run was actually WORKING. The time it sat paused is not counted (the cell's tooltip and the details name it); a working run reads "... so far". |
| State | The state, and under it why the run stopped (`budget_exhausted`, `user_pause`, ...). |
| Task, Mode, Seed, Experiment | What the run was. |
| Evaluations | Candidate designs simulated, of the budget: `25 / 60`. |
| First feasible | The number of evaluations spent when the first design met every target; "none" if no design has. |
| Data | MOCK (synthetic backend, not a circuit result) or real. |
| Can continue | yes (full saved state), model only (usable for fine_tune / frozen), no. |

* **A double click on a row** puts that run into the bottom tabs; the row is marked (blue, with a bar at its left
  edge) and the window stays open. **Clear** empties the tabs again. Neither stops, changes or deletes anything. The
  header's Start / Pause / Abort keep acting on their own run, whatever is shown here.
* **Details** opens everything else the run recorded, under its row: run folder (click to copy) and ids, created /
  worker began / came to rest, working time, time paused, summed simulator job time, stop reason and error, budget
  and Spectre launches, learner updates, first feasibility, best design with its variables, the model it loaded and
  its last save, what can be restored, parallel simulations, connection, bytes written - and one line per
  **segment** (each Start or Resume: when it began and ended, how it ended, how long it worked).
* A press on a column title sorts by it (again: the other way; rows without a value stay last). The filter box
  narrows the list by any word of a row: task, mode, state, `mock` / `real`, a date.
* **Nothing in the window updates by itself.** The list is read when the button is pressed and by **Refresh list**
  (the window says when it was read); a run's details are read when they are opened. A working run therefore shows
  its state and duration as of that time.
* The times come from the run's own files (`run_manifest.json` segments, `status.json`); `GET /api/runs` carries them
  as `started_utc`, `ended_utc`, `last_seen_utc`, `active_seconds`, `paused_seconds`, `segments`. A workbench server
  started before this was added lists runs without them: the window says so and asks for a restart of `serve`.

Browser check: `frontend/scripts/run_list_check.mjs` (every run request answered by FIXTURE runs; safe against the
live backend). Backend test: `tests/workbench/test_wb_run_list.py`.

Changing the selected run immediately hides the previous run's status, table and file list. Replies arriving late
cannot put them back, and status commands carry the identity of the run whose status was displayed. Polling waits
for each response before scheduling the next read; a slow backend cannot accumulate overlapping timer requests.

### Getting a run's data out of the browser (added 2026-09-21, user request)

Each of the four run tabs at the bottom has its own export. Every one of them is a button press; the browser saves
the file into its normal download folder, under a name that says which run (or experiment) it came from.

| Tab | Button | What the browser saves |
|---|---|---|
| Run status | **Export status (JSON)** | `<run folder>__status.json`: everything the tab shows at that moment (state, budget, best design, connection, the run's manifest and summary) plus `exported_utc`. |
| Logs | **Download full log (events.jsonl / errors.jsonl)** | The whole log file, one JSON record per line. The list on screen is only the newest 200 entries. A healthy run has an empty errors log: the tab then says "Nothing to download" instead of saving an empty file. |
| Data tables | **Export detailed CSV** | `<table>__seq<N>.csv`: the WHOLE selected table, not only the rows shown. The same file (with a `.meta.json` description) stays in the run folder under `exports/`. |
| Data tables | **Export research CSVs** | `<experiment>__aggregates.zip`: the six summary tables over every run of the experiment, each with its `.meta.json`. The files themselves stay in `<experiment>/aggregates/`. |
| Output files | **Download data-only package (.zip)** | `<run folder>__data.zip` (JSON, Parquet, CSV, JSONL, netlists; no waveforms, work files or models). Every single file also has its own **Download** button at the end of its row (the arrow icon; the hint then says "Downloaded <name>."). |

A log can be downloaded while the run is still writing it: the download is the file as it was at the moment of the
press, cut at the last complete line. Parquet stays the source of truth; every CSV is a derived copy.
The on-screen log reads backwards only far enough to collect the requested entries, skipping malformed lines and
an unfinished final line. The journal reader used for recovery still stops at its first malformed record.
ZIP downloads spill beyond 1 MiB to a temporary file, send 1 MiB chunks, and close the file on completion or
disconnect. File listings and packages prune excluded work directories before descending into them.
Browser check: `frontend/scripts/export_check.mjs` (real MOCK run; needs a scratch backend, refuses port 8765).

### Corner check: a run's best designs at five corners (added 2026-09-22, user request)

The **Corner check** tab (after Output files) simulates the shown run's best designs again at five fixed conditions and
says, per design, whether it holds up. It is a check AFTER the optimization: nothing of it goes back into the run, its
replay, its model or its best design.

* **Which designs.** Recorded feasible designs first, identical widths counted once, ranked by the largest smallest
  margin under each spec's **Margin sides** setting. The real task reference is also eligible even when it fails nominal,
  after the feasible recorded designs; when none passes, the reference can still be checked. Its sizes are shown and
  no nominal reward is invented before measurement. **Designs** chooses 1 to 3; the cost is designs x 5 corners.
* **Which corners.** The project's screening set, `configs/gpdk045_conditions.json`: TT 27 °C 1.0 V (the normal one,
  simulated again), SS 125 °C 0.9 V, FF -40 °C 1.1 V, FS and SF at 27 °C 1.0 V. The testbench's supply changes with the
  corner; its input common mode (0.6 V), bias (0.4 V) and load stay as they are.
* **The verdict** is the optimizer's own grading (`evaluation.corners.summarize_corners`, M3): **accepted** = every hard
  spec met at all five corners; **rejected** = at least one corner failed (a spec missed, or the simulator reported the
  design invalid or not converging); **inconclusive** = nothing failed, but at least one corner has no usable answer (a
  timeout, the connection, a measurement that did not validate) - never blamed on the design. Each cell of the grid
  says pass, FAIL with the worst spec and its value, or unknown with the reason; the verdict column adds the pass count.
  Folded below: the worst value of each spec and the corner it came from. The normal corner is simulated again and
  compared with the run's own result; a difference is said.
* **Which circuits.** None at the moment: the two it worked on, the op-amp `real:gpdk045_ota7` and the MOCK task, were
  removed on 2026-09-30 (record 7.128; the OTA5 task before them, status record 7.73). A task saved from a cell is
  qualified at its normal condition only: the tab says so in a neutral note and Check stays off.
* **A real circuit** costs real Spectre simulations. Check first asks for exactly that budget ("Authorize 15
  simulations?"; no = nothing is created), then, as Start does, the connection gate (unknown layers are asked about).
  The check writes each design's widths into the cell with the same adapter a run uses, simulates its five corners,
  and at the end writes the recorded widths back and reads them back; the tab says whether that worked. It is refused
  while a real run or another check holds Virtuoso. Two failures in a row that are not the design's (timeout, transport,
  license, simulator) stop it, so no more budget is spent on a broken link; the cell is restored then too.
* **MOCK** is free: the toy score has its optimum moved at each corner. It exercises the check, not a circuit.
* It runs in a process of its own, like a run's worker, so a page reload or a backend restart does not cut it. **Stop**
  ends it after the simulation in flight. While it works the tab reads its progress every 1.5 s; otherwise nothing
  updates by itself (**Refresh** reads again). Earlier checks of the run are a folded list; a double click shows one.
* Files: `<run>/corner_checks/<check_id>/` - `request.json` (the designs, corners and authorization), `status.json`,
  `results.jsonl` (one line per simulation, with every value), `summary.json` (the verdicts), `work/`, `worker.log`.
  API: `GET /api/runs/corner-check/plan` (free, local files only), `POST .../start`, `GET .../status`, `POST .../stop`.
* Limits, bluntly: five corners are an engineering sample, not a proven worst case; 0.9 V is a project choice (-10 %),
  not a PDK minimum; the OTA testbenches set the tail current with a fixed 0.4 V gate voltage, so corners move that
  current more than a real bias circuit would; passing all five says nothing about mismatch (no Monte Carlo). This
  tab's real path has so far run only against a fake adapter in the tests: the Corner check itself has not yet
  simulated a real corner. Real OTA7 corners have been simulated outside this tab: in reward v2's qualification
  (status record 7.95) and in the reward v2.1 gate check (7.108).

Backend: `src/gator_workbench/corner_check.py`; tests `tests/workbench/test_wb_corner_check.py`. Browser check:
`frontend/scripts/corner_check_check.mjs` (fixtures only; safe against the live backend).

## Reward and training conditions

The reward and its settings belong to the optimizer package: reward v2 (2026-09-26) and reward v2.1 (2026-09-29), both
made under the user's explicit permission to change `src/analog_optimizer/`. Their contract, qualification and evidence
are in [reward-v2.md](reward-v2.md); this section says what the page offers. The schema defaults keep the old
arithmetic (Nominal only, capped violations, no worst-spec share, no bonuses), so saved configurations and task hashes
are unchanged. No task trains at corners since 2026-09-30: the only one, `real:gpdk045_ota7`, was removed (record
7.128). Training at corners needed a finite launch cap and zero automatic retries.

### Reward, conditions and the saved model on the page (record 7.96)

Reward coefficients have the backend's 0..1 bounds; training conditions include a fixed nominal entry, at least one
selected corner in `always`, and separate step/reset launch costs with one shared cap. Missing caps and nonzero robust
retries are explicit errors. Specs keeps the objective inside the **Constraint** list ("≤ upper, then lower is better";
only pairs that can work are offered) and shows **Judged at** only while training corners are planned (record 7.124);
both keep the backend's enum and boolean field types. Saved-model facts show all coefficients and condition
identities. Compatibility rechecks the entire current configuration (debounced), including reward, conditions and
probe edits; an old compatible result is cleared while checking. The status table separates first nominal from full-plan feasibility, nominal from adverse
values, and draft settings from the executed reward in the saved summary. Historical missing coverage stays unknown.

### Reward v2.1 controls and checks (2026-09-29, record 7.106)

New configurations start with compressed violations and worst-spec share 0.5; saved ones retain their settings.
Training conditions offers Nominal only, Corners after nominal passes, and Every planned corner. The backend reports
whether the task supports corners (none since 2026-09-30). For after_nominal, a nominal failure costs one launch, a
pass costs 1 + K, and a reset costs one; the full step plan must fit the launch ceiling before preparation.

Under Specs → More columns, **Missing value = failed** opts a required spec into treating its absence after a completed
simulation as failure; wrong units and infrastructure faults stay errors. A spec computed by an equation is missing only
when a probe it reads is missing; the other equation specs keep their values (record 7.112). **Margin sides** selects
the limits counted by clearance and Corner check ranking; feasibility still checks all limits. The zero-floor hint
explains the upper-only choice. A new row, and an edit of its unit, limits, constraint or tolerance, suggests a scale:
3 dB, 10 degrees, a target's tolerance, half an interval, else the size of the threshold. The suggestion follows later
edits until you type a scale of your own; a row with nothing to size it by yet (no dB/deg unit, tolerance or limit)
keeps an empty scale, which the backend sizes from the threshold. Saved empty scales are not filled on load. (Record
7.112 fixed a suggestion that froze at 1 - e.g. 1 W - when a row was added before its limits were typed.)

Reward and conditions exposes the nominal gate band and objective shape. Advanced exposes **Alpha learning rate**,
stored per configuration; empty inherits the actor learning rate. No separate starting rate passed the extended
1,000-update unit check, so new configurations leave it empty. Attributed failures continue the episode, while its normal
horizon and configured success ending still apply.

Run status, Data tables and the agent's reward-review digest show the last 50 scored designs' p90−p10 reward spread
and latest exploration bonus. When the spread is smaller, they show the brief's plain-language steering warning.
The start checklist also warns when recorded evidence has no design meeting all hard specs at all planned conditions,
names the best recorded design's worst misses and points to Corner check. This is a warning, not a start blocker or
proof that the targets are impossible. It reads existing tables/checks and explicitly named historical OTA7 qualification
folders; it never launches a simulation or changes targets.

Code: the steering check is `src/gator_workbench/reward_diagnostics.py` (`steering`, over the evaluations and learner
updates tables; `load` feeds `steering` in `GET /api/runs/status`, and `agents/run_digest.py` uses `steering` too). The
corner warning is `src/gator_workbench/reachability.py` (`check`, then `assess`): static validation runs it when the
training conditions are not Nominal only and nothing else blocks the start, so the page, the start checklist, the
settings review and an applied proposal all see the same warning (code `corner_reachability`). It rejudges recorded
designs against the current hard specs: those of earlier runs of the same task with unchanged probes under the output
root (the configured one, else the remembered one), their Corner check results, and for `real:gpdk045_ota7` the
reference and designs of reward v2's qualification (folders named in the code, never a scan of `artifacts/`).

**Failure limits.** Run configuration has a field **Stop after N consecutive failed evaluations**
(`run.max_consecutive_failures`, default 5). A design the simulator reports as invalid or not converging is still
scored (reward -1) and kept in replay, and since reward v2.1 the episode goes on, so the network learns where the
circuit breaks. The stop rule counts it as a failed evaluation all the same: 5 in a row end the run as `failed`
(stop reason `consecutive_failures`), so a run that explores a region where many designs break may need a higher
limit. A dead backend has its own limit, **Pause after N consecutive infrastructure failures** (default 3, under
Advanced): it pauses the run, resumable once the connection gate passes again, instead of failing it.

[Reward contract and validation](reward-v2.md#reward-v21-2026-09-29). These controls were checked on source previews
only: the user's live frontend/backend were not rebuilt or restarted. The subsequent fixed-action physical check used
10 of the approved 30 launches, exercised both gate paths and restored the starting design (record 7.108).

### How a real run spends its simulations: corners two at a time, reused resets (2026-09-30, record 7.126)

Three changes of the optimizer package (user decisions of 2026-09-30) stop a real run from spending time and budget on
simulations that tell it nothing new. MOCK runs are unchanged.

* **Corners two at a time.** After a candidate's nominal simulation, its corner simulations run two at once when the
  circuit is measured from Spectre's own results (no task since 2026-09-30: `real:gpdk045_ota7`, the only one with
  training corners, was removed). Rows,
  the stop after a failing corner and the launch accounting are those of one-at-a-time: results are taken in plan
  order, and a corner already started when an earlier one fails is counted as launched but adds no row. A task measured
  inside the Virtuoso session (a Maestro task, measured by OCEAN) keeps one at a time. Code: `CircuitSizingEnv`
  (`condition_jobs`) in `envs/sizing.py`, `delegated` and the per-thread output capture in
  `backends/virtuoso_bridge.py`, `NativeEnvironmentFactory.condition_jobs = 2` in `training/parallel.py`.
* **Every 5th reset simulated.** A reset used to simulate the unchanged starting design again (with episode length 4,
  one evaluation in five). Now each lane simulates it at its first reset, at every 5th reset and after any failure; the
  other resets start from the lane's last simulated one and reserve, charge, launch and record nothing (event
  `episode_reset_reused` in `logs/events.jsonl`), so the budget buys more steps. "A reset costs one" above holds for
  the simulated resets, and the warm-start budget note counts only those (`runs.warm_start_resets`, record 7.133). An
  AI-only run has a single episode and never resets again; warm start and rescue keep their schedules, which never
  count resets. Code: `RESET_RECHECK_EVERY` and `_dispatch_reused_reset` in `engine.py`, lane operation `reset_reused`
  in `lanes.py`, `CircuitSizingEnv.reset_reused`.
* **Maestro tasks skip the text parse.** For a task OCEAN measures, Spectre now writes its own binary results; the bridge
  still downloads the folder but no longer converts a text copy nobody reads (`VirtuosoBridgeBackend._raw_format`).
  Other real tasks still get PSF text, which they read. OCEAN's values agree with those of the text results to within
  2 units in the last place (4e-16 relative: the binary results are exact where the text copy was rounded). Fetching
  the results only when a design's waveforms are kept would need a rewrite of the bridge's Spectre runner, so it was
  not done.

Optimizer digest `100945fb…` → `f42a3098…`, one step for all three. Tests: `tests/test_parallel_corners.py`,
`tests/test_reset_recheck.py`, `tests/test_raw_format.py`, `tests/workbench/test_wb_reset_reuse.py`. Checked on the
simulator on 2026-09-30 (record 7.126): on `real:mscr_ota7t` the same 10 evaluations bought 8 steps instead of 5 at the
same pace (2.0 s against 2.1 s per evaluation), and the designs both codes proposed measured the same to within 2 ulp.

## The right column: settings, saved models and the graph view

### SAC and LLM search methods (2026-09-30, record 7.116)

**Search method** offers exactly SAC, LLM warm start → SAC, LLM only, and SAC with LLM rescue.
The schema supplies the method identifiers; the page and API enforce the same model-loading and concurrency rules.
Warm start collects simulated starting experience, completes initial SAC updates, then hands over without another
random warm-up. LLM only uses one baseline and one lane, saves search progress without policy weights, and has no
numeric fallback. Rescue leaves SAC running while a stall-triggered AI request is pending. SAC remains the default.

Each AI run freezes its provider/model/effort, has explicit call/cost ceilings, and owns a sizing thread in the Agent
tab. The thread is read while the Agent tab (or its own window) shows it, and followed every second only while an AI
run is live - a SAC run has none (record 7.125); it has a scrolling row of its own above the conversation. Hints apply
to a future eligible call and mark the run steered. Phase, call and rescue counts are saved and shown
consistently. See [LLM sizing](llm-sizing.md) for settings, failure behavior, recovery and the benchmark limits.

The source implementation and scratch browser checks are complete; this work did not rebuild the live page or restart
8765. The free SKY130 benchmark uses the user's feasibility-only decision: upstream pass targets, all metrics as
descriptive Probes, and bias currents fixed at upstream starting values in every arm. Calibration independently
rechecks every passing design against the original evaluator at 1e-9 relative tolerance, stopping on disagreement.
SAC's general current-group limitation remains; a read-only FeatureSchema experiment confirmed that a static current
column works, while a tunable current group still fails unit validation. No optimizer current-unit implementation was added.
The development record also documents one accidentally launched, server-rejected Codex request; the no-calls gate failed.

### Folding the right column's modules (added 2026-09-21, user request)

"Run configuration" and "Output settings" fold into one line with a click on their heading (the "Research
experiments" panel below them already did). Both start open; the choice is kept in this browser. A folded module is
only put out of view, not switched off: its settings stay in force and keep working. Its line says the main values
(Mode, evaluation budget and network; experiment name and the end of the output root), and carries a mark - "warning
inside" or "error inside" - while something in it asks for attention, also when that appears while it is folded.
Browser check: `frontend/scripts/module_fold_check.mjs` (fixtures only; safe against the live backend).

### Choosing which saved model to load (added 2026-09-21, user request)

A **run** is one training session (one press of Start) with its own folder; the models it saved are its
**save points** (`checkpoints/<id>/`). With Mode `resume`, `fine_tune` or `frozen`, the run panel's "RL model to
load" block lists every run that holds a model as a card (task, circuit, **network**, evaluations of training, last
save; tags `MOCK`, `weights only`) and then offers every save point of the chosen run: "Latest
save" (follows the run) or a dated one (always the same model). Runs without a save point are not listed. The list
is `GET /api/runs/models`: small metadata files only, read when the block opens, when a run starts and on
"Refresh list" - never on a timer. Older periodic save points are pruned: `output.keep_last_checkpoints` keeps the
newest 10 periodic ones by default, and empty keeps every one. Save now, pause, stop and final save points, the latest
one and a selected best policy are never removed. Models from outside the workbench (the M6 pilot checkpoints) cannot
be chosen, and there is no upload: `training_state.pt` is a pickle and is only loaded from a trusted local output root.

The selected model is compared again when a contract field changes (including circuit, rows, seed, network,
learning settings, reward or conditions). Editing project labels, output options or the evaluation budget does not
repeat that inspection. Display checksums are reused while the resolved file identity, size and modification/change
timestamps match; `latest` is resolved on each description. Actual model loading always verifies fresh checksums.

**Available encoders (2026-09-26):** Graph Transformer, RGCN and GATv2 (`gatv2`). GATv1 (`gat`) was replaced on this date; old configurations are rejected explicitly and old GAT weights cannot load into GATv2. MLP and GCN were deleted from the optimizer and workbench by user request; port-GNN was removed earlier. An old configuration naming a removed encoder is rejected explicitly. Exact resume of checkpoints saved before this package change needs matching historical optimizer source and dependencies (`9bc488f` for the preceding five-encoder version, `bbdfe36` for the recorded six-encoder physical M6 pilot). Workbench `fine_tune` and `frozen` retain their existing compatibility checks: a source-digest difference is a provenance warning if the retained architecture and all other required contracts match; this does not make deleted encoders loadable. The package changed again since (reward v2 in `1135b8b`, reward v2.1 in `8cf53ae`): the current digest, and which commit loads which older checkpoint, are at the top of `docs/decisions.md`.

**The network comes with the model (2026-09-21, user request).** The "RL network" block - encoder list, sizes,
presets - sets up a NEW network and is shown in Mode `scratch` only. In `resume`, `fine_tune` and `frozen` it is not
shown: a saved model only loads into the network it was trained with (the backend refuses any other one in all three
Modes), so the configuration takes the network of the chosen model by itself and the model's facts start with a
"Network" row. Only the network follows; the training numbers under "Advanced" stay yours. A network that arrives
from elsewhere while a model is loaded (an imported configuration, an applied agent suggestion) is taken back too,
and the panel says so. Back in `scratch` the block returns and shows the network that was last in use.

Choosing an encoder loads its remembered settings. A delayed reply or preset reset only changes the configuration
while that choice and its network values are still current; later choices, edits, Undo and imports take precedence.
Preference writes and resets are ordered so an older save cannot overwrite a newer reset (record 7.130).

### Network structure of a saved model (added 2026-09-21, user request)

Under the facts of the chosen model, the fold-out **Network structure** shows what the saved network consists of -
as tables, in keeping with "no plots". Nothing is read until it is opened (`POST /api/runs/model/structure`,
a tensor-only read of `model_weights.pt` after its checksum matched). The summary says how many parameters are
trained (actor + 2 critics + the entropy temperature), that 2 target copies are saved as well, and gives one small
table per network (Inputs / Block n / Read-out / Output). **Full layer table** opens a wide dialog with every layer:
section, name, type, shape ("inputs -> outputs"), parameters, share, and one plain line on what the layer does.

Two things are never guessed. Layer TYPES are shown only when the backend could rebuild the network from the
settings recorded in the save point and found exactly the saved tensors (same names, same shapes); otherwise every
tensor is still listed, without types. A layer is marked **never used** only when the forward pass never touches
its weights - today that is `lin_skip` of PyG's `TransformerConv`, which the graph transformer allocates but switches
off (`root_weight=False`): 272 of 7,314 actor parameters at 16/2/1. A test pins the flag against real gradients for
all three supported encoders; a layer whose gradient is merely zero for the DATA at hand (`binding_ratio` when every ratio is 1)
is used and is not flagged. Browser check: `frontend/scripts/model_structure_check.mjs`.

### Circuit graph view (added 2026-09-21, user decision: one on-screen diagnostic picture)

**Where it is.** Run panel (right) > "RL model to load". With Mode `resume` / `fine_tune` / `frozen`: pick a model, and
under its facts are the "Network structure" fold-out and the **Circuit graph view** button. With Mode `scratch` (the
default) the same block has **Look at a saved model**: it lists the saved models for LOOKING only - structure table and
graph view - and changes nothing about the run (the selection is kept outside the configuration; Mode stays scratch).

**Circuit graph view** (button under the structure fold-out) draws the GRAPH THE NETWORK SEES, as a node-link picture:
one node per device (rounded box = transistor, barrel = R / C / L, cut corners = source; coloured by kind) and one per
net (circle; supply, ground, input, output tinted), one straight link per connection, labelled with its terminal. It is
deliberately NOT a schematic - no symbols, no rails, no routed wires (user decision 2026-09-21, after a schematic-style
attempt: "graph neural network style like the cytoscape original but with some hints from the circuit information").

**The circuit only gives hints, by hard-coded rules - no agent, no model call, the same circuit always gives the same
picture** (`frontend/src/panels/circuitLayout.ts`; the drawing package only draws, its own layouts know nothing about
circuits and gave long diagonals and crossings): supply at the top and ground at the bottom; a net's height is its
place on the DC current path between them (device steps from the supply / steps from supply + ground; never through a
gate, a bulk tie, a rail or a capacitor), a device stands between the nets it conducts between; nets that only drive
gates stand beside the devices they drive, a source feeding such a net next to it, a supply source at the side, a
capacitor on a shelf near the net it loads; two devices that share two nets (an inverter) stand above each other;
left-to-right order by barycentre sweeps; nothing is put where something stands, and no link may run through a node
it does not belong to (the loosest node steps aside). A link that enters a device at its gate ends in a dot there, one
at its bulk in a bar. Bulk ties are hidden at first (tick "Bulk connections"; the tables list them anyway). A graph
without a supply AND a ground net has no hints: the package's layered layout is used and the view says so. "Layered"
and "Spread out" remain as buttons; nodes can be dragged.

**Line thickness is the attention** on that connection for the
chosen block, head and direction ("what a device takes from its nets" or "what a net takes from its devices");
a device whose size the policy sets has a blue border and reads `w 1.768 um -> 3.115 um` = now -> proposed.
Beside the picture, as tables: the sizes now / proposed by the policy / really tried by the run, the connections of
a clicked device with their attention and the uniform share, and what was measured in that state.

Where the numbers come from: the chosen save point is REPLAYED on a state its own run archived (the observation
the network saw before evaluation N, from the complete transition archive) - `POST /api/runs/model/graph-view`,
one forward pass on the CPU. **Nothing is simulated and nothing is written**, so it costs no budget and works for
MOCK and real runs alike. The evaluation can be chosen (box + Show, `<`, `>`); by default it is the last one the
save point had seen. Attention is read by forward hooks on the attention layers, without any change under
`src/analog_optimizer/`; a test compares the policy's output with and without the hooks.

How to read it - and how not to: attention is normalized per RECEIVING node (over all connections arriving at one
node a head's values sum to 1), so a node with a single connection always shows 1.0; such lines are drawn thin and
dashed, and every value comes with the uniform share 1/k. Attention shows where the network looked, not why it
chose an action: **a debugging aid, not evidence** of anything about graph transformers. Encoders without attention
(`rgcn`) show the circuit and the proposed sizes only. Bulk ties can be hidden to tidy the
picture (the numbers do not change); nodes can be dragged, "Spread out" and "Fit" rearrange. A run that kept no
transition archive cannot be shown. The drawing library (cytoscape 3.34.3, MIT, no further dependencies) is a
separate file that the browser fetches only when the view is opened. Browser check:
`frontend/scripts/graph_view_check.mjs`.

## The PDK, and what a real run writes back into Virtuoso

### The components the network knows: "Load PDK" (added 2026-09-21, user request)

**In plain words.** The RL network turns every part of a circuit into a node with a *kind*, every pin into a link with
a *role* (drain, gate, ...), and reads a fixed set of parameter *columns*. It can only tell apart what its list names.
The optimizer's own list ("standard") has 8 kinds - unknown, nmos, pmos, resistor, capacitor, inductor, vsource,
isource - and 8 parameters (w, l, m, nf, r, c, ind, dc); anything else (bipolar transistors, diodes, S-parameter
blocks, ports) is "unknown" and stays fixed. **Load PDK** reads one PDK and gives the network a list with EVERY
component of that PDK: for GPDK045, 54 components (14 MOS incl. MOS capacitors, 6 bipolar, 10 diodes, 21 resistors, 1
MIM capacitor, 2 inductors), each with its own kind, its pins with their real roles (collector / base / emitter,
anode / cathode, ...) and all its numeric parameters (28 columns).

**Why this does not touch the protected package.** The list is not code in `src/analog_optimizer/`: it is the
`FeatureSchema` the package's `SACLearner` takes as an argument and records in every saved model's contract. A PDK list
is built by the workbench (`src/gator_workbench/pdk.py`) and handed to the unchanged package. So loading a PDK changes no
source digest and no saved model's list. (The digest has moved since for other reasons: `02127bc3...`, the M6 pin, until
entry 7.83 removed `port_gnn` on 2026-09-24 - models and audits from before load only from source commit bbdfe36 - and
`3f00832c...` since reward v2.1, commit `8cf53ae`; see the top of `docs/decisions.md`.) A
model trained with a PDK list loads only with that same list, and a standard model not with a PDK list: the package's
own contract check refuses the mix, and the compatibility report says it in words ("this model knows the PDK gpdk045
(54 components, version fa5c3946) component list; this run uses the standard list").

**Where (since 2026-09-27, user: "when loading a schematic from Virtuoso, shouldn't the PDK be loaded at the same
time?").** The read happens in the Virtuoso window: **Read this cell into the workbench** (and **Read the cell again**)
reads the cell's PDK in the same press - the technology library its design library is attached to, through the same
connection and gate - and a line under the window's buttons says what came of it ("PDK gpdk045 read with the cell: 54
components (version ...)", or why it was not read; a PDK that will not read never fails the cell). The window's button
**PDK window...** opens the PDK window to read one by name (another library, another model file) and to see what was
read. The CHOICE stays in the RL network block: under the encoder, **Components** (standard / every loaded PDK) - a
network setting like the encoder, shown in Mode `scratch`; the block says when the chosen PDK is not loaded on this
machine and points to the Virtuoso window. In `resume` / `fine_tune` / `frozen` the list follows the chosen model by
itself, as its network does, and the model's facts gain a "Components" row. Saved as `run.network.vocabulary` =
`standard` (written as no field at all, so every existing configuration keeps its hashes) or `pdk:<technology
library>`. Backend: `bridge_read.pdk_with_import` (states `read` / `not_read` / `skipped`, in the import's answer as
`pdk`); the same reader op as the window's Load, so a PDK read again unchanged makes no new version.

**What is read - with the cell, or on the window's "Load"; read-only, no simulation** (`POST /api/virtuoso/import` and
`POST /api/pdks/load`, connection gate `read_cellview`, reader op `pdk`; about 3 s for GPDK045):
1. Virtuoso's own description of every cell of the technology library, in ONE query: the Spectre model a cell netlists
   to, the pin order and the Spectre pin each pin is, the parameters written on each instance line, their declared
   units and defaults (CDF `simInfo` / parameters). A cell with no Spectre entry of its own (GPDK045's resistors) is
   looked into: its schematic is opened read-only and closed again, as the bridge's reader does, and the primitive it
   places names the model (`resm1` -> `primRes2` with model `g45rm1`).
2. The PDK's Spectre model files (the connection's `model_file` and everything it includes), downloaded through the
   bridge into a temporary folder OUTSIDE the repository, scanned and deleted. They say what each model is.
Empty boxes = the technology library of the connection's design library and the connection's model file. The result is
kept under `configs/local/workbench/pdks/<id>/` (git-ignored): the extracted facts and the files' SHA-256 - never the
PDK files. Every version ever loaded stays in `versions/<sha256>.json`; a run keeps its own copy of the list it was
started with (`network_vocabulary.json`), so loading the PDK again never changes an existing run or model.

**How each fact is decided - by rule, nothing guessed from a name.** A device's family comes from the Spectre
primitive of its model (`bsim4` -> MOS with the card's `type=n|p`, `bjt` -> bipolar `npn|pnp`, `diode`, `resistor`,
`capacitor`, `inductor`); for a wrapping subcircuit from its own element (an `inline subckt`), from the one MOS / bipolar
element it holds, or from what lies between its first two pins (resistive only = resistor; an inductor there =
inductor, its parallel capacitor and series resistor being parasitics; a declared resistance / capacitance unit of the
cell decides between passive candidates). A pin's role is the primitive terminal it reaches, directly or through one
series element (GPDK045's gate resistor); a passive's first two pins are its two ends, further pins its body. The CDF's
pin mapping is cross-checked against the model file's pin order. A parameter's scale is the standard scale of its
declared unit (length 1 um, capacitance 1 pF ...), else the power of ten of the PDK's own default value. One column per
name, except where families disagree on its scale (a bipolar `area` factor of 25 vs a diode `area` of 40 fF become
`bjt.area` and `diode.area`); a name that means something else in the standard list keeps the PDK's own name (an
inductor's netlist `r` is its inner RADIUS, so it is `rad`, never the resistance column). What cannot be established
stays "unknown" and is listed; for GPDK045 nothing was.

**How a circuit reaches the network.** The task's circuit graph is left exactly as it is: the environment, the backend,
the replay, the archive and every table keep the graph the simulator saw. Only at the network's input
(`pdk.learner_class`: the package's `SACLearner` with its `batch` shown the PDK's view) each device whose Spectre model
belongs to the PDK takes its PDK kind and pin roles and its parameters move into the PDK's columns; sources and ideal
parts keep their standard kinds. The circuit graph view draws that view (PDK model names, shaped by family).

**Varying more than w, l, m, nf, r, c, ind, dc.** With a PDK list a Parameters row may vary any numeric parameter the
PDK gives a component - an inductor's `rad`, a bipolar `area`, a diode's `pj` ... - when its unit is a length, a count, a
resistance, a capacitance, an inductance or a voltage: the package varies a group only in one of its eight kinds, so
such a parameter is varied as the kind of its unit (a radius as a length) while its binding keeps its own name, which is
what the network's column follows. The unit is checked against the PDK's declared unit; a parameter the PDK declares
no unit for takes the unit its row states, with a warning. With the standard list such a row stays blocked, and the
message names the loaded PDK that would allow it. The PDK list changes what the network understands; what a real run
may WRITE in Virtuoso is decided by the property form of each instance (next section).

**Also fixed on the way:** a row varying `m` or `nf` could never run. The form demanded the unit `count`, while the
network input accepts a count only as `1`; a group in `count` failed at the first action. Counts are now handed to the
optimizer as `1`.

**When reading a Virtuoso cell** (in the Virtuoso window), a loaded PDK of the cell's
technology library also names the pins of the PDK components the repository has no verified mapping for (bipolar,
diodes, all resistor types ...): the copy parses completely instead of listing them as unverified. "Save task" takes
them too (since 2026-09-22): pins as the PDK itself states them.

Tests: `tests/workbench/test_wb_pdk.py` (invented `demo045` PDK in `tests/workbench/fixtures/pdk_demo/`). Browser check:
`frontend/scripts/pdk_check.mjs` (hermetic, fixtures only, safe against the live backend).

### What a real run writes: any value the property form lets you type (added 2026-09-22, user request)

**In plain words.** A real run used to change transistor widths only. It now changes any value the PDK's property form
(the "Edit Object Properties" form of an instance) lets a user type: a transistor's width, length, finger count or
multiplier, a MIM capacitor's sides or multiplier, a resistor's segment length ... - and nothing the form greys out or
computes (a transistor's diffusion areas, a MIM capacitor's capacitance while it is computed from its sides). The protected
package is untouched (source digest unchanged); everything is in the workbench (`cdf_facts.py`, `cdf_rules.py`,
`cdf_write.py`).

**Where the rules come from - read, never assumed.** Reading a cell (and "Save task", which reads the working copy again)
now also runs one read-only query: for every instance of the core cell, the description (CDF) of its cell - which form
field feeds which netlist parameter (GPDK045's netlist `w` is `simW` = the field `w`; `nf` is the field `fingers`), each
field's type, the form's "may be typed" and "is shown" rules, its callback, its choice list, the form's init and done
procedures - and each rule that is an expression, evaluated on the instance as it is now (a MIM capacitor's `w` is
typeable while "Calculate Parameter" is not `width`). A rule only the open form can decide (GPDK045's
`gpdk045_mosEditable` reads the form's widgets) is trusted as the form would be. Kept beside the copy as `core_cdf.json`;
nothing is written, and the query reports whether the cell was modified (it never was).

**What Save task accepts.** Widths of single-finger, m = 1 transistors keep the verified width writer (as before, rules of
format 1). Any other row goes to the form writer (rules of format 2) when the form lets a user type it; otherwise Save task
says why, in words ("the form greys it out in the setting C1 has now (its rule: ...)", "its form field fingers holds a
count; give the row that unit"). Grids, because a run stops at the first value the PDK does not keep as written: lengths on
the 5 nm grid the GPDK045 readbacks confirmed (a transistor's total width on fingers x 5 nm, so its finger width stays on
it), counts in whole numbers from 1 (a finger count only where the finger width stays on the grid: 1 um allows 1, 2, 4, 5
... fingers, not 3), a choice list on its own evenly spaced values; the range must contain the present value. A transistor
varies its total width or its finger count, not both. The rows come back adjusted (snapped inward, the step filled in),
as for widths.

**What a run does with each candidate** (`cdf_write.write_skill`, one SKILL transaction, one save): for every instance with
a value to change - and only those - the form's init procedure, then per field: its rule, the value, its callback; repeated
(at most three rounds) until every requested value AND every value the task keeps as recorded reads back as it should. The
second part matters: GPDK045 folds a wide transistor into more fingers when its total width is typed, so the recorded
finger count is typed back, as a user would. A length is typed before everything else of its instance (record 7.127):
GPDK045's width callback computes the well-proximity values `sca`/`scb`/`scc` from the length the transistor has at
that moment, and the length callback leaves them alone, so a width typed first kept the previous length's values -
each candidate was simulated with its predecessor's, and a restoration left them wrong. For the same reason a round
that types a length types the width again at its own value, when the task holds the width instead of writing it.
Then the form's done procedure, `schCheck`, `dbSave`. The checks after it are
the verified profiles' checks, generalized: an instance that is not written is compared field by field with the record; a
written one may change what its callbacks compute, never a mode setting (a cyclic / boolean field) or a held value, and a
transistor keeps total width = fingers x finger width with fresh areas; the exported netlist carries exactly the values the
form reads back, and for what the form computed from them (the areas, the MIM capacitance) exactly what the form now holds. A value the PDK does not keep (a clamped capacitor side) fails the write, the candidate is rolled back,
and the run stops with that message - no simulation of a design the optimizer did not ask for. The no-simulation check
before every run, the corner check and the run itself use the same writer.

**Checked live (2026-09-22, no simulation):** read-only, the query on the ring oscillator's working copy
(`GPDK045_RINGOSC_GATOR`) and the no-simulation check of a task varying transistor widths and lengths, the MIM capacitor
sides and a multiplier through the new adapter - connect, export, deck: all pass. Then, with the user's go-ahead, three
candidates written into the copy through the run's own adapter (transistor w 1.2 um + l 60 nm; MIM w 3 um + m 3; the range
ends w 1.6 um, l 45 nm, MIM w 5.6 um, m 1): each read back exactly as asked, GPDK045's callbacks recomputed what they own
(finger width, areas, `nrd`, the MIM capacitance 25.0194f -> 17.4394f), every held value stayed, each export passed; about
0.2-0.4 s per write, 0.5 s per export. The restore brought every field back, and a fresh export of the copy equals the one
it was verified with, statement for statement; the original cell and the protected `vco_m6_v1` were unchanged.

**Also fixed on the way:** the mapping of every saved task pinned each group's recorded value, so the export of any
candidate that changed a value failed the graph's own check ("Binding/current value mismatch"): a run of a saved task could
never get past its first change - only the one-evaluation baseline ever ran. The group values now come from the netlist,
as in the verified mappings. Tasks saved before keep the old mapping until they are saved again.

Tests: `tests/workbench/test_wb_cdf_write.py` (recorded REAL form rules of the ring oscillator, `fixtures/ring_osc/
core_cdf.json`; a fake Virtuoso that runs the writer's SKILL with emulated callbacks - folding, clamping, bookkeeping).

## A task's Virtuoso side: the cell it works in, saving, the agent, the run

### The cell the task flow works in: the user's own copy (2026-09-23, user request) and its Maestro setup

The first part of the task flow the user asked for on 2026-09-21 (cell + testbench -> the agent sets up parameters,
probes and specs IN Virtuoso -> read back -> edited anywhere -> "Save task"). It lives in the note "Read from Virtuoso"
of the Virtuoso window, under the buttons of a cell read into the workbench, and every step is a button.

**The user's own copy (since 2026-09-23).** The workbench makes NO copy of a cell any more. Copy the cell and its
testbench in Virtuoso yourself (Library Manager), choose the copy in the window and press **Read this cell into the
workbench**: the press asks (a confirm) whether the cell is a copy you made, and the warning above the button says why -
saving a task writes the Maestro test `GATOR` into the testbench, and every run sets device sizes in the cell (put back
when the run ends; a forced abort can leave them changed). Cancel reads nothing. OK reads the cell with `work_here`, and
the backend records the cell that was read as the flow's working copy (`working_copy.declare`: a record with
`copy == original` and `declared: true`; `verified` there means "the user said so", not a netlist comparison - nothing is
contacted beyond the read, and the check before every run keeps comparing the cell's export with the saved task). The
window then says "Working in `<library>/<testbench>` directly: you declared it a copy you made (when)", and reading a
declared cell again asks nothing. Refused in words: a cell read without its testbench (before any export), the PDK's own
library, an export that does not name the cell. `POST /api/virtuoso/copy` refuses (`copies_not_made`).

Until 2026-09-23 the button **Make a working copy** did this instead: it copied the testbench the cell was read through
and every cell of the same library under it into `<library>_GATOR` - a library the workbench added itself, bound to the
same technology library - and pointed the copied testbench at the copied cells (gated, under the session lock, `cds.lib`
backed up; accepted only when the copy netlisted like the original, every copied cell came from the copy library and the
originals read back unchanged; records under `configs/local/workbench/working_copies/<library>/<cell>/` and
`working_copies/libraries.json`). Tasks saved on such a copy keep running on it: their records name it, their line in the
window says "made by the workbench before 2026-09-23", and nothing migrates them. `working_copy.make` remains for Save as
through the API and for the tests. Cell and instance names are the same in a copy as in the original, so every
Parameters row and every probe names the same instance path either way.

**Read setup.** One Maestro test, `GATOR`, on the cell's testbench holds what the
simulation needs and measures: the model file (the connection's, section `tt`), the analyses, the outputs (Cadence
calculator expressions on testbench nets and branches) and a spec per output (`>`, `<` or a range), plus design variables
and the instance parameters set to them. A Maestro output is a Probes row with source `ade_output` (the output name in
*source_name*, the expression in *signal*); a Maestro spec is the Specs row whose equation is that one probe. Two presses
write the copy, and both read it back: approving the agent's setup and **Save task**. **Read setup** ("Changed its
Maestro test yourself?") goes the other way in one press: it shows a one-line summary and takes the outputs and specs into
Probes and Specs (units are suggested from the expression and marked so; a unit or an optimizer setting already chosen on
a row of the same name stays, and a limit - Maestro keeps plain numbers in base units - is converted into that unit; one
Undo reverts it), with what differed folded under it. A test without outputs, or a copy without a Maestro view, takes
nothing and says how the copy gets one. Analyses and variables changed in Maestro are NOT taken over - the next Save task
writes the task's own again; change those in the task file. A spec over several probes, and every optimizer-only field
(scale, weight, hard/soft, keep improving, ranges), stays in the workbench. Nothing is synchronized on its own.
Until 2026-09-22 the block had three buttons, **Read setup**, **Use in editors** and **Write to Virtuoso**; the user
asked for fewer, as the flow has it: Save task writes the copy anyway, and reading now takes over in the same press.

**Starting a circuit that does not start by itself: initial conditions** (added 2026-09-22, user request). An
oscillator has a symmetric DC operating point and stays in it for the whole simulation, so a ring oscillator measured
through Maestro reported "eval err" for its frequency until now. A task can therefore carry **initial conditions**: a
start voltage per net (`maestro.initial_conditions` in the task file, `{"OUT": "0.9", "XU1.N1": "0", "XU1.N2": "0.9"}`;
a net inside an instance is addressed as Spectre spells it, `XU1.N1`). Save task writes them into a small file on the
simulator host (`~/.gator/ic/<library>__<testbench>__<test>.scs`, one `ic` statement, written by SKILL - nothing is
uploaded) and registers that file with the Maestro test as a model file **without a section**. Maestro then netlists
`include "<that file>"` above the PDK model include, so Maestro's own runs and every deck the optimizer builds from
that netlist start the circuit the same way. Reading the setup back reads the file too, so a start voltage changed or a
file deleted in Virtuoso is a difference the check before every run reports; changing them drops a recorded baseline,
because what is simulated changed. The agent may propose them (`setup.initial_conditions`), and a net name or a value
that is not a voltage is refused before anyone can approve it. A circuit that settles by itself needs none.

**What may be a Maestro variable.** Only values of analogLib's own resistor, capacitor, inductor and sources. A PDK
device derives other values from its parameters or clamps them: on the live GPDK045 a transistor width set to a variable
left the 12 side values the PDK computes from it (as, ad, ps, pd, nrd, nrs, sa, sb, sd, sca, scb, scc) at their old
numbers, which would simulate a different transistor. Transistor sizes therefore keep the verified path of writing the
number through the PDK callbacks - into the copy.

**Expressions** run inside the user's Virtuoso session when they are measured, so an output must pass an allowed list:
calls of listed calculator functions (`VT`, `VF`, `IT`, `frequency`, `bandwidth`, `phaseMargin`, `ymax` ...), strings,
numbers, the setup's variable names, arithmetic and `?keyword` arguments; anything else (`system(...)`, `;`, backquotes)
is refused before anything is written. Nothing is evaluated by the workbench itself.

The rest of the flow was built afterwards: the check before every run and the run path that measures Maestro outputs
(Maestro's netlist once, Spectre per evaluation, OCEAN on that run's results; proven once against one Maestro run) - see
"The check before every run" and "Running a task measured by Maestro" below.

Tests: `tests/workbench/test_wb_working_copy.py`, `tests/workbench/test_wb_virtuoso_setup.py` (fake write process; the
answer shapes are the live installation's). Browser check: `frontend/scripts/working_copy_check.mjs` (hermetic, fixtures
only, safe against the live backend).

### Saving a task: Save task and the task file (added 2026-09-22, user request; Save as removed 2026-09-23)

The second part of the flow. **Save task** replaces the former Create profile form (user decision: the form, its Circuit
type box and its expected-frequency field went once Save task worked). Only a person presses it: the agent has no tool
that saves a task (its `virtuoso_work` tools, relayed through `POST /api/agent/tools`, read Virtuoso and write the
working copy's Maestro setup only; see "The agent works in Virtuoso itself").

**Where.** At the right end of the editors' tab line (Parameters | Probes | Specs), above "Modify selected with
agent..." - the save sits with the rows it stores (user request 2026-09-22; it used to be in the note "Read from
Virtuoso", which now only says "Then save it as a task: Save task is above the editors" with "What Save task does"
folded). For a cell read from Virtuoso: a New task name (the cell's name when left empty), **Save task** and **Task
file**. On an open task (Registered task): "Task real:<name>, revision N", **Save task** and **Task file**. Their
messages and questions (the saved revision, a refusal, the ring oscillator's rough frequency) appear under the editors'
toolbar. "Delete task" (was: Delete profile) stayed at the end of the task's block in the Project column until
2026-09-24; it is in the column's task row now, at the right of Load task (7.78). The editors'
own **Save** button went at the same
time: it kept the configuration in the browser, which the page already does by itself 0.8 s after every change (and,
since 7.125, when the page is closed or reloaded sooner), and a second "Save" beside "Save task" only confused.
If browser storage is full or blocked, a persistent header warning offers **Retry save** and **Export JSON** for the
current in-memory configuration. Failed writes remain unsaved, including for the page-close retry. A successful write
clears the warning; page-close saving still avoids replacing another tab's stored configuration (record 7.130).

**What Save task does.** It reads from the Probes how the task measures: all Maestro outputs (`ade_output`) = measured
by Maestro; all results of one circuit type (`backend_profile`, e.g. what the testbench brought) = that type - the
ring oscillator or the op-amp, measured by the workbench as before. Mixed probes, or probes that fit both types, are
refused in plain words. Then, with no simulation:
1. a task measured by Maestro writes its outputs, specs (from the rows) and analyses, variables and bindings (from a task
   file applied on the page or an approved agent setup that could not be written, else as the copy was last written -
   by the last save or the agent's approved setup) into its working copy and reads them back - they must match;
2. the working copy is read into the workbench again (netlist export + CDF readback, read-only): the reference every run
   of the task is compared with;
3. the task's files are generated from that copy (the same generator Create profile used, with its checks), next to
   `task.json` in `configs/local/workbench/profiles/<name>/`, and the task is registered as `real:<name>`.

The ring oscillator's measurement needs a rough expected frequency (it sizes the transient): the first save asks for it
once, in one line under the buttons; the task file keeps it. The task's files name the cell the flow works in (the copy
you declared, or the made copy of an older task), so the real run adapter opens that cell - never a cell you did not
declare or copy.

**Saving again.** Save task on an open task makes its next revision under the same name (the user's decision:
saving again never makes a new task). The previous revision is kept in `history/r<N>/` inside the task's folder, the
old folder aside in `profiles/.deleted/`. A recorded baseline is kept only if parameters, probes, measurement, analyses,
variables and bindings are unchanged; changing only specs or notes keeps it. **Save as** went on 2026-09-23 with the
copies the workbench made: another task is another copy you make in Virtuoso, read in the window and saved from there
(the backend still answers `as_new` for the API, with a renamed copy inside the same library). The first save of a cell
takes the cell (or, for an older task, its made copy); a cell that has a task is opened through it (its note says so),
and Delete task frees the cell again.

**The task file.** One readable JSON file: the cell, the copy, the measurement, the Maestro part, the Parameters /
Probes / Specs rows and notes, with a `_help` part that explains every part (JSON has no comments). **Task file** opens
the file of the CURRENT editors in a window of its own (opened within the press; a blocked pop-up is said, and the next
press tries again; a window already open is brought forward with its draft); **Apply to editors** checks every row with the editors' schema
and fills the editors (one Undo step) - a broken file is refused with its problems and changes nothing. What the file
adds beside the rows (analyses, variables, bindings, the rough frequency, notes) is sent with the next Save task.
Nothing is saved or written to Virtuoso from the window.

**Running a task measured by Maestro:** see "Running a task measured by Maestro" below - Save task also has Maestro
netlist the task's test once. A Maestro-measured task saved before that part is listed as not runnable until it is saved
once more. Tasks saved before this part (Create profile) have no working copy; they still run on the original cell, and
Save task refuses them with the way forward.

Tests: `tests/workbench/test_wb_task_save.py` (fake bridge processes, the recorded ring-oscillator export). Browser
check: `frontend/scripts/task_save_check.mjs` (hermetic; the task file window, Apply, Save task; no Save as);
`virtuoso_source_check.mjs`, `project_help_check.mjs` and `testbench_probes_check.mjs` follow the window.

### The agent sets the task up: one proposal, written into the working copy (added 2026-09-22, user request)

The third part of the flow. **Ask the agent to set up** (in the Virtuoso window's note, beside Read the cell again)
replaced "Ask the agent for suggestions" (user decision 2026-09-21: removed once this worked). It waits until the cell is
declared the one the flow works in (or, for an older task, has its made copy), then opens the Agent tab with the request
kind `virtuoso_setup` and the request written out: say in two or three
sentences what the circuit is and how it works, then set it up for optimization in its working copy - which transistor
widths to vary (grouped where devices must match), what to measure as Maestro outputs with the analyses they need, and
specs. Add your own requirements to the words ("more than 1.1 GHz"); nothing is sent until you press Enter.

**What the agent is given.** Besides the circuit (read from your cell; instance paths and nets are the same in the copy)
and the three editors, the copy as data: its library, cells and Maestro test `GATOR`, what the workbench last wrote
into that test, which instance values may be Maestro variables (see "What may be a Maestro variable" above), the
calculator functions an output may call, and the connection's model file. It answers with rows for Parameters, Probes
and Specs plus a `setup` part - analyses with their options, design variables, and the instance values set to them. A
part it leaves out stays in the copy as it is.

**Checked before anyone can approve it.** The backend refuses a proposal whose setup could not be written as it stands:
an output calling a function outside the allowed list, a variable on a PDK device, an output reading an analysis the
setup does not set, a malformed part. The Agent tab shows the reasons; there is nothing to approve.

**Approve, apply and write the copy.** The proposal shows its row changes and, under them, the Maestro setup and where it
goes ("Maestro setup of the working copy `<library>/<testbench>`" - the cell you read as your copy). One approval covers both, bound to
the proposal's content with the setup. The press fills the editors (one Undo step) and writes the setup - with the
outputs and specs of the rows - into the copy's test (gated, under the Virtuoso session lock), reads it back and says
whether the copy now matches. If Virtuoso cannot be reached, the rows are applied all the same and the message says to
press **Save task** once it can be: the page keeps the approved analyses, variables and bindings for that save, which
writes them into the copy (until 2026-09-22 the message pointed to the removed "Write to Virtuoso", which wrote only
the outputs and specs). No simulation either way, and nothing becomes a task until you press **Save task**,
which takes the analyses, variables and bindings written into the copy over (on an open task too: they are newer than
the ones saved with it). The same parts applied earlier from a task file are dropped on the page when the write
succeeds; a failed write replaces them with the approved ones.

Tests: `tests/workbench/test_wb_agent_setup.py` (what the request tells the agent, the proposal and its bound approval,
the refusals, apply writing into the copy through a fake write process, the rows applied when Virtuoso is down, no copy
yet). Browser check: `frontend/scripts/agent_setup_check.mjs` (hermetic: canned agent and Virtuoso answers, every other
writing request refused - safe against the live backend).

### The agent works in Virtuoso itself: the kind `virtuoso_work` (added 2026-09-22, user request)

The same job, with the agent doing the Virtuoso side itself instead of handing over one proposal. Choose the kind
**virtuoso_work** in the Agent tab (next to the message box) and ask for what you want; it needs a working copy, like
the setup proposal above.

**What it may do.** While it works it can:

* read from Virtuoso: the libraries, the cells of a library, and any schematic with its instances, parameters and nets;
* look at the working copy of this task: its names, which instance values may be a Maestro variable, the calculator
  functions an output may call, the model file, and what the workbench last wrote into it;
* read the copy's Maestro test as it stands;
* **write the Maestro setup into that working copy** - analyses, outputs, specs, variables, bindings and initial
  conditions - and read it back, correcting what did not land, as often as it needs (twelve writes at most).

**What it may not do, by construction.** There is no tool for anything else, and the workbench refuses a call for one:
it cannot touch any cell but the task's working copy (since 2026-09-23 the cell you declared as your copy), write device
sizes (those are the optimizer's, written inside a run and restored
afterwards - a size written between runs would make every run refuse to start until you save the task again), start a
simulation, run a command, read a file or read the web. A request that may read publications is never a request that may
write into Virtuoso, so nothing a web page says can reach your design.

**What you still approve.** The answer is the same proposal as ever: the rows for Parameters, Probes and Specs, which
change nothing until you approve the diff. What the agent wrote in Virtuoso went into the copy while it worked - so if
you reject the rows, press **Read setup** to take the copy's own setup back into the editors, or write the copy again.
Under the reply, one folded line says how many steps it took in Virtuoso, whether the copy was written, and which calls
the workbench refused; while it works, each step appears in the chat as it happens ("Virtuoso: listing the cells of
GPDK045_RINGOSC", "Writing into the working copy: analyses, outputs, specs").

**How it works.** The workbench starts its own tool server (`gator_workbench/agent_tools.py`) beside the agent CLI and
grants that one request exactly the tools of its kind (`--mcp-config` with `--strict-mcp-config`, so no other tool server
exists, and each tool named in `--allowedTools`). The server itself decides nothing: it relays every call to
`POST /api/agent/tools` of the workbench with a one-time token that stops working the moment the request ends. The
backend (`agents/tools.py`) checks the grant and the budget, resolves WHICH working copy from your configuration - never
from the agent's arguments - and then calls the very functions the buttons use, with the connection gate, the Virtuoso
session lock, the name checks and the records unchanged. Every call is written to
`configs/local/workbench/agent_tool_calls.jsonl`.

Tests: `tests/workbench/test_wb_agent_tools.py` (what each tool does and refuses, the budget, the closed session, the
protocol, the flags the CLI is given, the settings file that can neither widen nor add a tool, and the whole chain over
a real socket with the fake CLI driving the real tool server). The protocol and the flags were also tried once against
the real `claude` CLI with a stub backend (2026-09-22): it listed the granted tools, called them with the request's
token, and never saw the one it was not granted.

### The check before every run: editors, saved task and working copy agree (added 2026-09-22, user request)

The fourth part of the flow. A run runs exactly one saved task on its working copy, so before any costed simulation
three things must say the same thing:

1. **The editors and the saved task.** The rows of Parameters, Probes and Specs must be the rows of the task file,
   compared as the schema reads them (a field shown with its default equals one left out). This is offline: static
   validation says it while you edit - a blocking issue `task_not_saved` per editor that differs, naming the rows and
   fields ("Specs differ from the saved task real:ring_osc (revision 1): osc_frequency_hz: lower 1.3e+09 here, 1.1e+09
   saved") - so Start is not offered until **Save task** stores them (it keeps the recorded baseline when
   only specs or notes changed) or **Load task** takes the saved rows back. A resume runs the run's own
   saved rows and is not compared.
2. **The saved task and its working copy in Virtuoso.** The run adapter does everything a real evaluation does before
   Spectre starts, and nothing after: it connects (the creation record matches, no ADE/Maestro window is open on the copy,
   the copy still has the recorded sizes), Virtuoso exports the testbench netlist, the export is compared with the saved
   one - topology and every parameter - and the simulation deck is written. Read-only; it takes the project's Virtuoso
   session lock like a run.
3. **A task measured by Maestro: its Maestro test.** The copy's test is read back and compared with the task file's
   `maestro` part (outputs, specs, analyses, variables, bindings, simulator mode). Its deck is Maestro's own deck around
   the export (see "Running a task measured by Maestro"); the deck step writes it.

**Start, Single baseline simulation and Resume** run parts 2 and 3 by themselves, right after the connection gate and
before anything is created (`runs.prepare_run`). A difference starts nothing: the banner under the header lists each step
- passed / FAILED, what differs, and what to do (for example "The working copy was changed in Virtuoso after the task was
saved: press Save task to take the copy as it is now, or undo the change in Virtuoso", or which ADE/Maestro windows to
close). A passed check is kept in the run's manifest (`consistency_check`, for a resume in its segment).

**Check now** (in the task's block, where "Check against Virtuoso" was - that button and its route are gone: it was
part 2 alone) runs all three parts on its own: free, read-only, no simulation. Its result goes as soon as a row changes.
Without a connection it compares the rows and says the rest needs one.

Not compared: an original cell against a copy the workbench made of it before 2026-09-23. Such a copy was made once,
and a later change of the original is not taken over. Since then the working copy is the cell you declared, so there
is nothing else to compare.

`POST /api/virtuoso/task/check`, body `{"profile_id", "config"}`: `{ok, task, revision, steps: [{step, ok, title, detail,
fix}], simulated: false}`; 409 `not_a_saved_task` for anything else. Tests: `tests/workbench/test_wb_consistency.py`.
Browser checks: `frontend/scripts/consistency_check.mjs` (hermetic), `virtuoso_source_check.mjs`,
`project_help_check.mjs`.

**What a task may hold since record 7.132** (limits found while building the MScR library):
- A noise analysis: Maestro writes it with its terminals, `noise ( VOUT 0 ) noise ...`, and the deck check reads that form.
- An analogLib resistor's `r` as a row: its display rule `artParameterInToolDisplay('r)` asks whether the simulator lists the
  field and reads "no" outside ADE; every field a run writes is one of Spectre's instance parameters, so it counts as shown.
- A GPDK045 poly resistor: each netlister numbers pcell subckts on its own (Maestro `resnsppoly_pcell_0`, the export
  `resnsppoly_pcell_01`), so the circuit comparison numbers pcells by the order they are defined.
- analogLib `iprobe` (a verified 0 V source, pins PLUS and MINUS, in `configs/gpdk045_devices.json`) and PWL sources
  (`wave=[...]`: the netlist parser in the optimizer package pairs brackets like parentheses).
- Save task refuses a spec whose equation names no Probe, with the Probes the task has, before anything reaches Virtuoso.

### Running a task measured by Maestro (added 2026-09-22, user request)

The fifth part of the flow. A task whose Probes are the Maestro outputs of its working copy runs like every other saved
task - Start, Single baseline simulation, the optimizer writing transistor widths into the copy through the PDK
callbacks - and differs only in the deck each evaluation simulates and in how its results are measured:

* **The deck: Maestro's own, netlisted once.** Save task has Maestro netlist the copy's test at its nominal corner
  (`maeCreateNetlistForCorner`, nothing in the design is written) and keeps the result split around its circuit:
  `maestro_deck.json` in the task's folder holds the head (header, design variables, Maestro's model include) and the
  tail (simulator options, analyses, info statements, saves). Every evaluation puts the circuit the run adapter just
  exported - with that evaluation's widths - between the two. Save task refuses when Maestro's circuit part and the export
  are not the same circuit, when an output reads an analysis the test does not run, and when the model include is not
  the connection's model file (one deck, one model).
* **The measurement: OCEAN on the run's own results.** Spectre leaves its results on the simulator host (the bridge keeps
  the folder; since record 7.126 in Spectre's own binary format, with no text copy parsed); OCEAN in the Virtuoso
  session opens them and evaluates every output expression - the calculator Maestro itself uses. Maestro writes signal
  names as the schematic does (`VT("/OUT")`, `IT("/V0/PLUS")`), a plain Spectre result
  folder as Spectre does (`OUT`, `XU1.N1`, `V0:p`); the names are translated once, at Save task, with the name maps
  Maestro's netlister writes (`amap/`, the maps ADE uses). A name the maps do not translate plainly - a terminal whose
  current is derived from another (a source's MINUS), an instance not in the maps - is refused then, in words. Values are
  in base units (Hz, V, A), what the compiled specs compare with.
* **The simulator mode: plain Spectre.** The optimizer's runs use plain Spectre; Maestro's default is APS, a faster engine
  that takes other time steps (448 against 575 on the ring oscillator), so its numbers differ in the last digits and more
  in fast transients. Writing a task's Maestro test therefore also sets plain Spectre, reads it back and compares it;
  Maestro runs of the copy then compute exactly what the optimizer's runs compute.
* The network's result registry of such a task is exactly its outputs, each with the scale its spec normalizes by.

Proven live (2026-09-22, three user-authorized simulations): a throwaway task on the ring oscillator's working copy -
one baseline through the real run path (Maestro's deck in Spectre, OCEAN on the remote results), then one Maestro run in
APS mode (vmax 1.9e-6 apart, the start-up minimum clearly apart) and one in plain Spectre mode: vmax, vmin and the
average supply current equal to 17 digits, 575 time steps in both.

Initial conditions were the missing piece here and are built since 2026-09-22 (see "Starting a circuit that does not
start by itself" above): a task carries a start voltage per net, Save task writes them into a small file on the
simulator host and every evaluation includes it, so a ring oscillator measured through Maestro oscillates. The
ring-oscillator circuit type remains for a task measured by the workbench itself. Side effect, stated: OCEAN's current results in the Virtuoso
session point at the last run's folder (ADE and Maestro windows keep their own).

Tests: `tests/workbench/test_wb_maestro_run.py` (translation with name maps, the OCEAN program and its answer, the bridge
variables left as they were, the deck split, the profile's deck and measurement, a task saved before part 5, outputs as
results for validation and specs, the simulator mode), `test_wb_task_save.py` (Save task netlists once; a netlist that does
not fit saves nothing).

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
approval bound to the proposal, configuration and circuit hashes. Agent model/effort are
independent of RL checkpoints and simulation budgets, and agents are never in the SAC loop. A request
has no time limit (since 2026-09-21): "Cancel request" stops it. One request kind goes further, and
only in one direction: `virtuoso_work` (2026-09-22) is granted the workbench's own Virtuoso tools -
reads, and the Maestro setup of the task's working copy - for as long as it runs; see "The agent works
in Virtuoso itself". The tables it proposes still need the user's approval.

Bridge skills exist in `~/virtuoso-bridge-lite/skills/` and the project's Codex-style
`.agents/skills/`, but **not** in a Claude Code discovery location. `GET /api/agent/diagnostics`
reports this and proposes (never executes) symlinks into `.claude/skills/`.

### The conversation in a window of its own

The "Agent" tab carries a small pop-out control at its right end, where a browser tab has its close
button. It moves the conversation - chat, a request in flight, an open proposal, the settings - into a browser
window of its own, with larger type and the notes as a full-height column; nothing restarts, and the bottom panel
stays free for the other tabs. Back again: the same control, "Bring back into the workbench" inside that window,
or simply closing the window (the panel's own "Bring it back here" went on 2026-09-29, 7.109). The browser must
allow pop-ups for this page.

### Watching the answer being written (added 2026-09-21, user request)

With the Claude Code provider an answer is no longer held back until it is complete. While the agent works, its
bubble shows:

- **Thinking**: a readable summary of the model's thinking, in a small box that follows the newest line. Scroll up in
  it to read, and it stays where you are until you scroll back to the bottom. It is a summary the model service
  writes, not the raw thoughts, and a question that needs little thought may show none;
- steps such as "Searching the web: ..." or "Opening <address>" during an online settings review, and a line when the
  model service is busy and the CLI retries;
- the reply itself, growing a few words at a time, then "Writing the proposed rows...", "Writing the warnings...".

When the answer is complete it replaces the bubble exactly as before (diff, suggestions, checklist, side window), and
the thinking stays with it, folded into one line, "▸ Thinking - 1 min 20 s", one click away. The diff, the checked
suggestions and "After you approve: ..." still appear only at the end, because the workbench works them out on the
complete answer. The explanation is written before the rows now, so it can be read while the rows are produced.

**There is no time limit any more.** It used to be 300 s (900 s with publications online), and an effort-max request
can take longer. The seconds keep counting in the bubble. "Cancel request" stops the agent, and what had arrived
stays in the chat under the cancel line, folded ("Thinking", "Reply so far"). Closing or reloading the page also stops
the request, since nobody would see its answer.

It costs nothing extra: the same request, and the thinking is billed the same whether it is shown or not. A workbench
server started before this change answers in one piece (the page accepts both) and still stops a request after
300 s: restart `serve` once.

**With the Codex provider** (added the same evening) the bubble shows what Codex reports while it works, in the same
places: each reasoning summary as its paragraph is done, commands it runs and web searches as steps, and the reply when
the answer is complete. Codex reports whole steps, not words, so its reply appears in one piece at the end.
Reasoning summaries are Codex's default; a `model_reasoning_summary = "none"` in your Codex configuration switches them
off. This is built from the Codex documentation and has not been tried with a real `codex`: none is on the
backend's PATH. (The Codex desktop app on this machine ships a Linux CLI inside its settings folder, so the provider
could be tried for real; a request costs usage, so that is the user's decision.) It needs `--json` in
`codex exec --help` (the SDK's older name `--experimental-json` also works);
otherwise the answer arrives in one piece, as before, and the bubble says so. Online research stays Claude Code only.

How it works: the page asks `POST /api/agent/propose` for a stream (`Accept: text/event-stream`, Server-Sent Events:
`progress` events, then one `result` or one `error` with exactly the JSON answer or the 409 detail of a plain
request). The backend reads the CLI's output line by line (`--include-partial-messages`, `--thinking-display
summarized`, environment `CLAUDE_CODE_ENABLE_FINE_GRAINED_TOOL_STREAMING=1`; `agents/live.py`). The pieces are for
display only: the proposal still comes from the CLI's final result and goes through the same checks. If a CLI version
refuses one of these options, the request is repeated once without them (an unknown option fails before any model
call) and the answer arrives in one piece. Codex: `codex exec --json` prints its events as JSON lines (thread / turn /
item events carrying whole reasoning, command, web-search and message items), read by `CodexTranslator` in the same
file. The proposal is still the output file (`--output-last-message`), or the last agent message of the stream if a
CLI version wrote no file.

### What is missing before the run can start

"What's missing?" (under the message box) is answered by the backend, free: no agent request,
nothing probed. It lists, in the order a start is gated: circuit, Parameters, Probes, Specs (the three
editor tabs, in tab order), other blocking issues, run configuration, output folder and - for a real
circuit - the bridge connection (the LAST test result; it does not test again) and the budget authorization
that only you can give. Each line says who acts. "Ask the agent to fix what it can" appears only when a
line is the agent's (the three tables); it sends ONE request of kind `readiness`, and the reply carries its
own checklist plus, where it had everything it needed, rows to review as a diff.

"Make it startable with the fewest changes" (on that checklist) asks the agent for the SMALLEST edit of the three
tables that lets the run start. Rows that are already valid cannot be touched - the backend rejects such a proposal.
Where you gave no number it may use a PROVISIONAL one, but only from data it can point to: a range around a device's
present size, or "no worse than the design as it stands" from the recorded baseline of a real circuit. Those rows
are listed in a yellow box next to the diff and say PROVISIONAL in their basis; replace them with your requirements
when you have them. For a verified real circuit the optimized variables are not a choice: the profile fixes them, the
agent copies them exactly, and the checklist reports any other set as missing (the run would be refused the moment it
starts). Under every proposal the workbench itself says whether the run would start after approval. "Fix only what
needs no assumption" is the strict variant: it writes nothing you did not give every number for.

### Reviewing the settings, with or without publications read online

"Review settings" (above the conversation) asks the agent to look at the run configuration, the RL network, the RL
training settings and the output settings - not at your circuit - and to suggest values, each with its source. The
reply is a table: setting, its value now, the suggested value, why and where it comes from, and **Apply**. Applying
is your own edit of that one setting (undoable like any edit); the agent and the backend apply nothing. Every row was
tried on a copy of your configuration first, so an illegal value cannot be applied, and a value that only works
together with another row says so. An agent may never suggest the circuit, the connection, a model to load, the
output folder or a name.

Tick "check publications online" for ONE review that may search the web and open publication sites (arXiv, IEEE
Xplore, ACM, OpenReview, GitHub and a few more; add hosts under `agent_web_domains` in
`configs/local/workbench/settings.json`). It takes minutes and more usage, works with the Claude Code provider only,
and the agent is then told the kind of circuit and your settings but nothing of the design itself. It must cite
what it opened, with a quote. A published value is a starting point with a citation, not evidence that it is better
on your circuit. If a publication uses a network that does not exist here, it is listed as an idea: adding an
encoder is a change of the optimizer's code that a development session has to make, and it changes the fingerprint
that every saved model and the recorded audits are checked against.

### Letting the agent read a run's results

"Review results" (under the message box; choose the run with "Runs..." first) asks the agent what happened in
that run and what to change next. The agent reads no file: the workbench condenses the run's own records - outcome and
budget, when the first feasible design came, every target against the best design, where the search spent its
evaluations and whether it kept hitting a bound, what failed and why, whether the learner moved - and hands that over
as data. The reply explains the run in plain language with the numbers it rests on. Changes come as rows you apply one
by one (settings) or as a diff to approve (the three tables). It is told not to draw conclusions about an encoder,
transfer or an algorithm from one run, and that the score of a MOCK run is not a circuit quantity.

The agent's brief on what a run needs is a plain file, `src/gator_workbench/agents/run_readiness.md`. It is
added to every agent request of every provider and to the exported task description, and it is read again
for each request, so an edit needs no restart. Keep it short (it is paid for on every request) and true to
what the workbench does. It is guidance below the fixed rules: it cannot widen what an agent may change.
This is deliberately not a Claude `SKILL.md`: the agent runs in an empty directory with no tool that could
load one, and a skill would not reach Codex or the exported task.

## What the frontend audit changed (2026-09-30, record 7.125)

The user chose all four groups of `artifacts/local/reviews/frontend-audit-2026-09-30.md`. What a user notices:

* **A real run is never authorized with MOCK wording.** When the backend says a run is real although the page still
  took it for MOCK (a task chosen a moment before its circuit was read), the question is built from the backend's own
  report: "This runs REAL simulations of real:<task> ... Authorize a total budget of N candidate evaluation(s)?".
* **Undo while typing:** keys typed into one field less than 1.5 s apart are one Undo step (user choice); leaving the
  field ends it, and a change that was not typed there - a button, an applied proposal, rows read from Virtuoso - is a
  step of its own even while the field has focus (7.131). An edit made less than 0.8 s before the page is closed or
  reloaded is saved - unless another tab stored the configuration meanwhile.
* **The Agent tab keeps its message box** while an AI run's thread is shown (the thread scrolls in a row of its own).
* **Import JSON:** only a file this workbench exported replaces the whole configuration; other files are rows for the
  open tab (every row with its ID) or are refused in words. The confirmation shows Apply / Cancel first and scrolls.
* **The first Save task of a cell** lives with the Project column: closing the Virtuoso window keeps Save task, Task
  file and an agent setup that waits for the save.
* **Pause and Abort stay** when one read of the run fails for a moment (two misses in a row are needed, as for the
  tabs). Banners lead with the backend's sentence; its code is under "Technical details". A configuration the backend
  cannot read is said field by field wherever it stops something (Matched devices, Save task, a banner), with a
  pointer to the header's blocking issues. Run status says "Reading
  the run..." or why it cannot be read, and the Runs window says when the list could not be read.
* **Stale answers:** the saved-model facts stay while the same model is checked again (only the verdict waits); the AI
  sizing settings follow a model saved in the Agent tab; a Check now, Read, Load task or PDK answer for something left
  meanwhile is not shown as current; connection tests show "testing..." only on the connection being tested.
* **Fewer requests:** no AI-thread reads for SAC runs or a hidden Agent tab, the Agent settings and the connection list
  read once, no task reload per keystroke in the Labels, a Virtuoso schematic read only once a Cell choice settles
  (0.4 s), no model check in scratch, no minute-by-minute log re-reads of an ended run.

Browser checks added: run_control (the real-run question), llm_sizing (the message box keeps its room),
spec_equations (one Undo per typed value, an edit before a reload, a long import, a foreign JSON file).

**Narrow windows (record 7.130).** At widths of 1,100 px or less the settings columns sit above full-width editors;
at 700 px or less they stack around the editors. The page scrolls vertically, tables keep their own horizontal scroll,
and the Agent conversation and message box stack with usable heights instead of squeezing the editor to zero width.

**Review fixes (record 7.131).** A new AI run's sizing thread appears in the open Agent tab once its search starts, and
a refused hint stays said until the next press. Continue waits while the header starts or resumes a run. In scratch no
Mode suggestion is left over from an earlier model check. A Specs row without a constraint reads "(not set)". Choosing
a registered task while a cell is read keeps the task, and a cell's previous load is not shown under the next one. An
ended run's log is read once more after its worker ended. Overlapping tests of two connections each show "Testing...".

## Code organization

`src/gator_workbench/api/app.py` initializes the app and registers four feature modules: settings and
connections, circuits and tasks, runs and exports, and agents. `api/models.py` owns HTTP request schemas;
`api/context.py` shares input/output authorization, configuration loading and the cached readiness
checklist; `api/support.py` shares response and streaming helpers. The HTTP routes and schemas are unchanged.
The page's task loads (`support.load_runtime`: validation, the task, Matched devices, the saved-model check, the agent)
go through `tasks.load_task_view`, which keeps a saved task (`real:<name>`) while its folder, its files, the connection
file and the conditions file are unchanged; the link is checked at every call. A run, the corner check and the command
line load it from the files (7.131).
The legacy copy route still refuses copying; Save-as remains a supported backend request.

The frontend keeps the agent conversation in `panels/AgentTab.tsx` and the run tabs in `panels/RunTabs.tsx`.
`CircuitBrowser.tsx` owns the Virtuoso browsing chain and circuit details; `Left.tsx` coordinates task selection.
Shared async actions and stale-response handling live in `store.ts`. Ordinary advanced numeric fields use
one descriptor list and defaults from the backend schema; byte units and checkpoint intervals retain their
specialized controls. The Agent tab stays mounted when another tab is selected.

Reads managed by `useRequest` and direct JSON GETs have a 30-second deadline. Changing a selection, disabling a read
or leaving its view cancels the hook's owned transport; shared cached reads keep their own bounded lifetime.
Refresh replaces an outstanding hook read. Polling still allows one read at a
time and interval changes retain the current result and outstanding request. Late replies from callbacks that ignore
cancellation are discarded too. Writes and streaming agent responses keep their own lifecycle and are not retried by
this mechanism. Log, output-folder and model-structure read errors offer a retry; failed validation blocks starting.

The configuration validation key is serialized only when the configuration changes. The editors skip renders when
their inputs are unchanged, and validation issues are grouped once by row rather than filtered for every row (7.130).

Tests share fake CLI installation and isolated HTTP servers in `tests/workbench/helpers.py`, plus controlled
browser input, passing validation replies, and optional connection fixtures in `frontend/scripts/lib/harness.mjs`.
`frontend/scripts/request_lifecycle_check.mjs` runs against a Vite source preview with controlled in-memory replies
and React StrictMode; it checks slow polls, reversed replies, cancellation, deadlines, hung-read replacement, retries,
run/table changes and export identity. `reliability_check.mjs` covers failed browser persistence and recovery, unsaved
JSON export, encoder selection/reset races, Undo during reset, narrow layouts and redundant serialization.
`tests/workbench/test_wb_read_efficiency.py` covers tail-read bounds, excluded directories, archive cleanup and
display-cache invalidation separately from execution integrity checks.

## Tests

```bash
~/analog-optimizer-venv/bin/python -m pytest tests/workbench -q
```

All browser checks at once (added 2026-09-30, status record 7.115):

```bash
bash frontend/scripts/run_checks.sh
```

What it does:
- It starts two scratch backends with empty temporary settings folders; it never touches the backend on 8765.
- It waits until Windows can reach those backends too: WSL's first successful response can precede localhost forwarding.
- It builds this tree's frontend into a temporary folder and serves it.
- It runs every `frontend/scripts/*_check.mjs` in 4 parallel lanes (`--lanes N`). Each check gets its own log and
  screenshot folder under the folder it prints, and a summary follows at the end.
- Options: `--only a,b`, `--skip a,b`, and `--retry-failed`, which reruns a failed check alone and reports it as flaky
  if it then passes.

Some checks get special handling:
- The two that start real MOCK runs (export, run_control_live) and agent_tab, which saves provider preferences, share
  a backend of their own and run one after the other. agent_tab explicitly seeds its provider and restores settings.
- request_lifecycle gets Vite's source preview.
- reward_v21 and llm_sizing run only when their fixtures exist and their fixed ports are free.
- The reward_v2 real/frontend checks read recorded evidence and are skipped.

The whole batch took 198 s, instead of about 9 minutes one check after another.

Provider tests use a fake CLI fixture; connection tests use fake bridge clients and a fake probe
process. No test starts a real agent session or contacts a real Virtuoso. The live answer is also
checked against a recorded REAL stream of the `claude` CLI (`tests/workbench/fixtures/claude_live_recorded.ndjson`,
see `test_wb_agent_live.py`), and in a browser by `frontend/scripts/agent_live_check.mjs` (hermetic by default;
`--live` watches a scratch backend stream from the fake CLI; run lines in its header).

The header shows blocking issues as a red button, "N blocking issue(s)": a press lists every one of
them in full (level, code, field and editor row, message), including those that belong to no editor
tab; the list follows each validation and closes when nothing blocks. A configuration the schema
cannot even read (for example an ID with a `/` in it) is listed the same way, one issue per field:
the field and its editor row, what is wrong in plain words (for an ID: which characters, an ID that
works, and what else must be renamed with it), and the schema's own text under a closed
"Technical details" line; the editor marks the row (backend `schema.describe_errors`, status record
7.56). Its browser check is
`frontend/scripts/blocking_issues_check.mjs` (headless Edge against the running workbench; the
validation is answered with canned FIXTURE reports and every other writing request is refused, so
it is safe against the live backend; run line in its header).
