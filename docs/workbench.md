# GATOR workbench: frontend, run control and data-only outputs

Local web workbench around the existing optimizer. It reads circuits, lets you define
optimization problems by hand or with agent assistance, runs the existing SAC backend, and
saves the raw data and model state needed for research analysis.

It produces **data, configurations, models, netlists and logs only**: no plots, images, PDFs,
spreadsheets or analysis reports are ever written, and the backend installs and imports no plotting library.
One exception ON SCREEN, by user decision of 2026-09-21: the **circuit graph view** (see "Circuit graph view"
below), drawn in the browser with cytoscape (MIT, frontend only, loaded when the view is opened). It is a
diagnostic picture; nothing drawn is written into a run folder or an export, so the outputs stay data-only.

**Where things are described** (this file is long; a section says what its feature does NOW):
[Start](#start) ·
[Start, Pause, Resume, Abort](#start-pause-resume-abort-added-2026-09-21-user-request) ·
[What is real and what is mock](#what-is-real-and-what-is-mock) ·
[Connection profiles](#connection-profiles-section-21) ·
[Output layout](#output-layout) ·
[The right column](#the-right-column-settings-saved-models-and-the-graph-view) ·
[The PDK and what a run writes back](#the-pdk-and-what-a-real-run-writes-back-into-virtuoso) ·
[A task's Virtuoso side](#a-tasks-virtuoso-side-the-working-copy-saving-the-agent-the-run) ·
[Reload saved data](#reload-saved-data) ·
[Agent providers](#agent-providers) ·
[Tests](#tests)

All code lives in `src/gator_workbench/` and `frontend/`. **Nothing under
`src/analog_optimizer/` is modified**, because `training/sac.py::source_digest()` hashes that
package and gates checkpoint loading and the M5/M6 audits.

## Start

```bash
# once: backend dependencies into the project environment
/tmp/analog-optimizer-venv/bin/python -m pip install -c constraints.txt -e '.[graph,test,web,webtest]'
# the pin file is not optional: a saved model loads only under the torch / torch-geometric it was saved with

# once (and after UI changes): build the UI. This machine has no Linux node; the Windows
# toolchain works through WSL interop. A native Linux node works the same way.
cd frontend && npm install && npm run build && cd ..

# run (local-only listening by default)
PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8765
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
  While a run is active or paused in the header, "Single baseline simulation" is not available.
* A real run asks for the budget again at Resume (what is left of it). A run that was started with checkpoints or
  replay snapshots switched off cannot come back from a pause; Pause says so before it pauses.
* The Run status tab keeps its own buttons (Pause and save, Stop and save, Force cancel, Continue with a new total
  budget). They act on the run shown there, and ask what the header asks: Pause and save says first when the run
  cannot come back from a pause, Stop and save asks before it ends the run, and Force cancel is offered only while
  a pause or a stop is waiting for the simulation in flight - for a run that is stuck (entry 7.64; before, all three
  acted on one click and Force cancel was offered while the run was simply running).

Browser checks: `frontend/scripts/run_control_check.mjs` (fixtures only, safe next to a live run) and
`frontend/scripts/run_control_live_check.mjs` (real MOCK worker; needs a scratch backend, refuses port 8765).

### Save now (added 2026-09-21, user request)

**Save now** (header, left of the main button; also in the Run status tab) saves the model of the RUNNING run
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
| `synthetic:gpdk045_ota5` (the one MOCK task) | **MOCK**: the optimizer's analytic toy backend (`origin=synthetic`) on a REAL circuit - the netlist and device mapping of the verified GPDK045 OTA5 (`examples/circuits/gpdk045_ota5.scs`, `configs/gpdk045_opamp.json`). Free: no Virtuoso, no Spectre. Every row says `provenance=mock`, data lives under `<output_root>/mock/`, and it is excluded from real-experiment aggregates. The `score` is not a circuit metric, and a model it trains never loads into a real run. Until 2026-09-22 there were four MOCK tasks on toy netlists (`synthetic:opamp`, `_opamp_two_stage`, `_ldo`, `_vco`); they were removed (status record 7.59). A configuration that still names one opens with a plain note and cannot start. |
| `real:gpdk045_*` tasks | The verified bridge profiles through the existing `NativeEnvironmentFactory`. Need virtuoso-bridge 0.8.0 importable by the backend interpreter, a connection profile, a passing connection gate and an explicit budget authorization. **Not exercised in this delivery** (see the status record). Nothing ever falls back to mock. Two of the four were removed on user request on 2026-09-23 (status record 7.73): `real:gpdk045_ota5` and `real:gpdk045_vco`, whose example cells were deleted from Virtuoso (a backup is kept). Left: `real:gpdk045_ota7` and `real:gpdk045_ldo`. A configuration that still names a removed one opens with a plain note and cannot start. |
| Arbitrary native cellviews | Read-only browsing through the bridge. Optimizing one needs a saved task, which runs on a WORKING COPY of the cell: a run writes instance values into that copy (the form writer since 7.66), never into the cell you drew, and no cellview is created or redrawn. |

### Choosing a registered task: whose rows Parameters, Probes and Specs show

The three tabs hold rows of the *configuration*, so they belong to a task. Choosing another task in **Circuit
source -> Task** brings that task's rows:

| Task | Parameters | Probes | Specs |
|---|---|---|---|
| `synthetic:gpdk045_ota5` (MOCK) | the three width groups of the OTA5's device mapping: input pair (M1 + M2), mirror pair (M3 + M4), tail (M5) - 5 rows, 3 action variables | `m_score` | one toy row, `score >= 0.95` (unit `fixture`): the analytic backend computes no gain, bandwidth or power, so there is nothing else to aim at |
| `real:gpdk045_ota7`, `_ldo` | exactly the rows the circuit's profile fixes (a real run accepts no others) | one per target | the circuit's **targets of record**: the frozen specification files of the real experiments (`configs/m6_real_cross_category.json`, partition `train`; `configs/gpdk045_ota7_transfer.json` for the OTA7). For the OTA7: gain >= 53.3 dB, unity-gain frequency >= 3.24 MHz, phase margin >= 30 deg, supply power <= 3.24 uW, output DC 0.3-0.5 V, exactly one unity-gain crossing. Every row states this source in `basis`. They are pilot goals near the measured baseline, **not product specifications**: edit them to your own requirements |
| a profile created from your own cell | the rows the profile fixes | one per result its circuit type produces, ready to carry a target | **none**: requirements are never inferred from a circuit. State yours, or press "Draft with agent..." |

* The **Circuit class / PDK id** labels follow the task at once, and so does a project name that a starter had given
  (`mock-gpdk045-ota5` -> `gpdk045-ota7`), so a real run is not filed under `runs/mock_gpdk045_ota5/`. A name you typed
  stays. Choosing a task after one of the removed MOCK tasks brings the new task's rows and name at once: no task can run
  the old rows any more (one Undo brings them back).
* Rows are exchanged only while they are nobody's work: empty, or still exactly what the task before had brought.
  **Rows you edited stay**; the panel says so, and **Load starter configuration** (there for every task) exchanges
  them when you want it. One **Undo** takes back a task choice together with everything it brought.
* Run settings are never touched by a task choice, and a real budget is never suggested.
* The LDO and VCO results are not in the optimizer's default result registry, and the UI has no editor for it. These
  two tasks therefore bring the registry of record of the real cross-category experiment (`m6-physical-spec-input-v1`,
  23 results), as a profile created from a cell brings its own. The OTA tasks keep the default registry, so their
  models stay interchangeable with the MOCK tasks' and with earlier runs. A registry stated in the configuration
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
  cell and the device sizes are read. The export is kept under
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
  former **Create profile** form on 2026-09-22 - see "Saving a task" below. What the form checked still holds: only what the verified real
  backend can do is accepted as a Parameters row - **widths of single-finger, m = 1 transistors directly
  inside the cell**, linear ranges that contain the present width, snapped onto Virtuoso's 5 nm width grid
  (the editor then shows them exactly as registered); anything else is refused with the reason. The cell
  becomes the task `real:<name>` under **Registered task** (files in
  `configs/local/workbench/profiles/<name>/`) and stops being browse-only.
  A cell that already has a registered task - one saved from it, or one of the verified built-in
  circuits (`real:gpdk045_ldo` for `ldo_m6_v1`, ...; the library is the one the Virtuoso connection
  states) - shows "This cell already has a registered task: `real:<name>`" with an **Open** button; open
  it to change it (Save task); another task needs another copy of the cell, made in Virtuoso and read in
  the window. A built-in circuit gets no second task.
  **Delete task** (last line of a saved task's block in the column; asks once more; was: Delete profile):
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
  2. **Single baseline simulation** in the header - one real Spectre run; asks for your budget.
  3. **Record the baseline run as reference** - from then on every run compares its first evaluation
     with that result, as the four verified profiles do. Recorded once, never replaced.

`POST /api/virtuoso/libraries | cells | read | import`, body `{"profile_id", "library"?, "cell"?, "testbench"?}` (import:
`"work_here"?` - the user said the cell is a copy they made; the answer then carries the `working_copy` record);
`POST /api/virtuoso/profile/reference` `{"name", "run_dir"?}`; `POST /api/virtuoso/profile/delete` `{"name"}` (answers
with the task's own cell - never its working copy - for the Circuit source). A task is saved with
`POST /api/virtuoso/task/save` (section "Saving a task"); the older `POST /api/virtuoso/profile` (Create profile) and
`/profile/preflight` routes are gone (entries 7.57, 7.64).

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
* **What an ngspice connection can do today: be tested.** There is no ngspice evaluation backend yet,
  so the gate refuses real runs and Virtuoso reads on it without probing (`blocking:
  ["connection_kind"]`, with the sentence to show), and a real circuit names the wrong kind instead of
  listing missing Virtuoso settings. Building that backend is a separate increment; the one place to
  switch it on is `connection.FAMILY_ACTIONS`. Note that the GPDK045 models are Spectre-format files:
  ngspice will need circuits with models it can read.
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

### Getting a run's data out of the browser (added 2026-09-21, user request)

Each of the four run tabs at the bottom has its own export. Every one of them is a button press; the browser saves
the file into its normal download folder, under a name that says which run (or experiment) it came from.

| Tab | Button | What the browser saves |
|---|---|---|
| Run status | **Export status (JSON)** | `<run folder>__status.json`: everything the tab shows at that moment (state, budget, best design, connection, the run's manifest and summary) plus `exported_utc`. |
| Logs | **Download full log (events.jsonl / errors.jsonl)** | The whole log file, one JSON record per line. The list on screen is only the newest 200 entries. A healthy run has an empty errors log: the tab then says "Nothing to download" instead of saving an empty file. |
| Data tables | **Export detailed CSV** | `<table>__seq<N>.csv`: the WHOLE selected table, not only the rows shown. The same file (with a `.meta.json` description) stays in the run folder under `exports/`. |
| Data tables | **Export research CSVs** | `<experiment>__aggregates.zip`: the six summary tables over every run of the experiment, each with its `.meta.json`. The files themselves stay in `<experiment>/aggregates/`. |
| Output files | **Download data-only package (.zip)** | `<run folder>__data.zip` (JSON, Parquet, CSV, JSONL, netlists; no waveforms, work files or models). Every single file also has its own **download** link. |

A log can be downloaded while the run is still writing it: the download is the file as it was at the moment of the
press, cut at the last complete line. Parquet stays the source of truth; every CSV is a derived copy.
Browser check: `frontend/scripts/export_check.mjs` (real MOCK run; needs a scratch backend, refuses port 8765).

### Corner check: a run's best designs at five corners (added 2026-09-22, user request)

The **Corner check** tab (after Output files) simulates the shown run's best designs again at five fixed conditions and
says, per design, whether it holds up. It is a check AFTER the optimization: nothing of it goes back into the run, its
replay, its model or its best design.

* **Which designs.** Only designs that met every hard spec at the normal condition (a design that fails there would
  only fail again), identical widths counted once, the SAFEST first: the largest smallest margin, i.e. the distance to
  the nearest limit divided by that spec's scale. (The optimizer's reward is 0 for every feasible design, so ranking by
  reward would pick at random.) **Designs** chooses 1 to 3; the text beside it says what a press costs: designs x 5
  corners.
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
* **Which circuits.** The op-amp `real:gpdk045_ota7` and the MOCK task (the OTA5 task was removed, status record
  7.73). The LDO and generated profiles are qualified at their normal condition only: the tab says so in a neutral note and Check
  stays off.
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
  current more than a real bias circuit would; passing all five says nothing about mismatch (no Monte Carlo). The real
  path has so far run only against a fake adapter in the tests: no real Spectre simulation of a corner has been made.

Backend: `src/gator_workbench/corner_check.py`; tests `tests/workbench/test_wb_corner_check.py`. Browser check:
`frontend/scripts/corner_check_check.mjs` (fixtures only; safe against the live backend).

## The right column: settings, saved models and the graph view

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
"Refresh list" - never on a timer. Nothing is deleted automatically: `output.keep_last_checkpoints` is empty by
default, and when set it prunes older periodic saves only (never the latest, a pause / stop / final save or a
selected best policy). Models from outside the workbench (the M6 pilot checkpoints) cannot be chosen, and there
is no upload: `training_state.pt` is a pickle and is only loaded from a trusted local output root.

**The network comes with the model (2026-09-21, user request).** The "RL network" block - encoder list, sizes,
presets - sets up a NEW network and is shown in Mode `scratch` only. In `resume`, `fine_tune` and `frozen` it is not
shown: a saved model only loads into the network it was trained with (the backend refuses any other one in all three
Modes), so the configuration takes the network of the chosen model by itself and the model's facts start with a
"Network" row. Only the network follows; the training numbers under "Advanced" stay yours. A network that arrives
from elsewhere while a model is loaded (an imported configuration, an applied agent suggestion) is taken back too,
and the panel says so. Back in `scratch` the block returns and shows the network that was last in use.

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
all six encoders; a layer whose gradient is merely zero for the DATA at hand (`binding_ratio` when every ratio is 1)
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
(`rgcn`, `gcn`, `mlp`, `port_gnn`) show the circuit and the proposed sizes only. Bulk ties can be hidden to tidy the
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
is built by the workbench (`src/gator_workbench/pdk.py`) and handed to the unchanged package. So the source digest stays
`02127bc3...`, every model saved so far keeps its standard list and still loads, and the M6 audit re-runs unchanged. A
model trained with a PDK list loads only with that same list, and a standard model not with a PDK list: the package's
own contract check refuses the mix, and the compatibility report says it in words ("this model knows the PDK gpdk045
(54 components, version fa5c3946) component list; this run uses the standard list").

**Where.** Run configuration > RL network (Mode `scratch`): under the encoder, **Components** (standard / every loaded
PDK) and the button **Load PDK...**, which opens the PDK window. The window loads and shows; the choice is the list in
the RL network block. In `resume` / `fine_tune` / `frozen` the list follows the chosen model by itself, as its network
does, and the model's facts gain a "Components" row. Saved as `run.network.vocabulary` = `standard` (written as no field
at all, so every existing configuration keeps its hashes) or `pdk:<technology library>`.

**What "Load" reads - explicit click, read-only, no simulation** (`POST /api/pdks/load`, connection gate
`read_cellview`, reader op `pdk`; about 3 s for GPDK045):
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

**When reading a Virtuoso cell** (Circuit source "Virtuoso library / cell / view"), a loaded PDK of the cell's
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
finger count is typed back, as a user would. Then the form's done procedure, `schCheck`, `dbSave`. The checks after it are
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
that reaches the backend.

**Where.** At the right end of the editors' tab line (Parameters | Probes | Specs), above "Modify selected with
agent..." - the save sits with the rows it stores (user request 2026-09-22; it used to be in the note "Read from
Virtuoso", which now only says "Then save it as a task: Save task is above the editors" with "What Save task does"
folded). For a cell read from Virtuoso: a New task name (the cell's name when left empty), **Save task** and **Task
file**. On an open task (Registered task): "Task real:<name>, revision N", **Save task** and **Task file**. Their
messages and questions (the saved revision, a refusal, the ring oscillator's rough frequency) appear under the editors'
toolbar. "Delete task" (was: Delete profile) stays at the end of the task's block in the Project column. The editors'
own **Save** button went at the same
time: it kept the configuration in the browser, which the page already does by itself 0.8 s after every change, and a
second "Save" beside "Save task" only confused.

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
the file of the CURRENT editors in a window of its own; **Apply to editors** checks every row with the editors' schema
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
   only specs or notes changed) or **Load starter configuration** takes the saved rows back. A resume runs the run's own
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

Not compared: your own cell against the working copy. A copy is made once, and a change of your cell after it is not
taken over.

`POST /api/virtuoso/task/check`, body `{"profile_id", "config"}`: `{ok, task, revision, steps: [{step, ok, title, detail,
fix}], simulated: false}`; 409 `not_a_saved_task` for anything else. Tests: `tests/workbench/test_wb_consistency.py`.
Browser checks: `frontend/scripts/consistency_check.mjs` (hermetic), `virtuoso_source_check.mjs`,
`project_help_check.mjs`.

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
  the folder); OCEAN in the Virtuoso session opens them and evaluates every output expression - the calculator Maestro
  itself uses. Maestro writes signal names as the schematic does (`VT("/OUT")`, `IT("/V0/PLUS")`), a plain Spectre result
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
"Bring it back here" in the panel, or simply closing the window. The browser must allow pop-ups for this page.

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
off. This is built from the Codex documentation and has not been tried with a real `codex`, which was never
installed here. It needs `--json` in `codex exec --help` (the SDK's older name `--experimental-json` also works);
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

## Tests

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q
```

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
