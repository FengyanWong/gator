# GATOR workbench: frontend, run control and data-only outputs

Local web workbench around the existing optimizer. It reads circuits, lets you define
optimization problems by hand or with agent assistance, runs the existing SAC backend, and
saves the raw data and model state needed for research analysis.

It produces **data, configurations, models, netlists and logs only**: no plots, images, PDFs,
spreadsheets or analysis reports are ever written, and the backend installs and imports no plotting library.
Two exceptions ON SCREEN, by user decision: the **circuit graph view** (2026-09-21, see "Circuit graph view"
below), drawn in the browser with cytoscape (MIT, frontend only, loaded when the view is opened), and the **circuit
picture** in the circuit column (2026-10-03; shown by **Show circuit** since record 7.362, see "The page's look and layout"), drawn as plain SVG. Both are diagnostic
pictures; nothing drawn is written into a run folder or an export, so the outputs stay data-only.

**Where things are described** (this file is long: read only the section you need - `grep -n '^##' docs/workbench.md`
lists every section with its line number; a section says what its feature does NOW):
[Start](#start) ·
[Start, Pause, Resume, Abort](#start-pause-resume-abort-added-2026-09-21-user-request) ·
[The page's looks and layout](#the-pages-looks-and-layout-2026-10-03-record-7158) ·
[What is real and what is mock](#what-is-real-and-what-is-mock) ·
[Connection profiles](#connection-profiles-section-21) ·
[Output layout](#output-layout) ·
[Reward and training conditions](#reward-and-training-conditions) ·
[The right column](#the-right-column-settings-saved-models-and-the-graph-view) ·
[The PDK and what a run writes back](#the-pdk-and-what-a-real-run-writes-back-into-virtuoso) ·
[A task's Virtuoso side](#a-tasks-virtuoso-side-the-cell-it-works-in-saving-the-run) ·
[Reload saved data](#reload-saved-data) ·
[The Agent window](#the-agent-window-claude-code-or-codex-in-a-window-of-its-own-2026-10-06-record-7226-2026-10-07-record-7253) ·
[Code organization](#code-organization) ·
[Tests](#tests)

Where each function lives - its button, code, route, record entries, tests and browser checks - is listed in
[functionality-reference.md](functionality-reference.md) (2026-10-02, record 7.139).

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
`GATOR_WORKBENCH_ALLOWED_ROOTS`), never from the browser, an imported file or an agent. The default output root is
the repository's `outputs/`; `GATOR_WORKBENCH_DEFAULT_OUTPUT_ROOT` names another folder (the browser checks' scratch
backends use an empty one, record 7.276).
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

The header has one main run button and **Abort** next to it (it reads **Let go** on a paused run, record 7.261). The
main button changes with the run:

| It reads | Pressing it | What happens in the backend |
|---|---|---|
| **Start** | starts a new run with the configuration on the page | new run directory, detached worker |
| **Pause** | pauses the run | no new simulation is started, the one in flight finishes and is recorded, everything is saved (checkpoint with the full training state), the worker exits |
| **Resume** | continues the paused run | the SAME run directory gets a new segment; network, replay memory, counters and budget are restored and the run goes on where it stopped |

`Starting...`, `Pausing...`, `Resuming...`, `Aborting...` are the waiting states in between. On a real circuit
`Pausing...` lasts as long as the rest of the simulation that is running.

The line under the header says how a pause or an end came out, also when nobody pressed anything (branch record
SIF-89; before, a run that completed, failed or paused by itself changed only the chip and the lit state): "Completed
at 800 of 800 evaluations (budget used up). Its results are under Run status."; in red, "The run failed at 12 of 800
evaluations: <its error>"; in red, "Paused by itself after connection failures; everything is saved. Test the
connection (Connection button), then Resume." - never the user's "Resume continues from exactly there", which a pause
after **Pause after N consecutive infrastructure failures** used to borrow while it saved. A user's Pause and Abort keep
their own words. Only a change of the run the header already holds is said: taking a run over, letting go of one and
the lookup after a reload say nothing.

**What Start would start** stands beside it while it reads Start, in one line (record 7.269; plan
[frontend run workflow](plan-frontend-run-workflow.md), "The draft"), and is the first sentence of its tooltip:
"Next: mscr_ota7t · Fine-tune from ota7t (2) @ 420 · GT 48/4/4 · 800 evaluations" - the task (a saved task as the
header's title names it: without its `real:` prefix, a renamed one by its new name - branch record SIF-71; or a Virtuoso
cell as library/cell), the Mode with its model and save point ("New model", "Evaluate ...
(deterministic actions)", "no Mode chosen"), the network in short, and the budget. When Start is off, the tooltip adds
why. The line only says: it starts nothing, and it is not shown while a run holds the header (the run chip says what
runs then, and Run configuration opens with "For the next Start: the run in the header goes on with the settings it was
started with." - branch record SIF-72). Run configuration's model line and this line come from the same values
(`RunPanel` passes them up).

* **Resume and Continue... are the same machinery, used differently.** Resume is the one-press way for the run in the
  header and does not touch the Mode. It continues with the settings the run was STARTED with (its own
  `effective_config.json`); edits made on the page while it was paused are not used. **Continue...** in the Runs window
  (record 7.261) is for picking up an older run, in its own folder, with a new total budget. `resume` is no Mode since
  record 7.265.
* **Abort** ends the run for good, but gently: it asks first, then lets the simulation in flight finish, saves
  everything and ends the run (`stopped`). Only while a pause or an abort is waiting for that simulation the button
  reads **Force abort**: it waits for nothing, the evaluation in flight is recorded as cancelled and stays charged,
  and on a real circuit a Spectre job already running on the server is not stopped and the schematic can be left
  with the sizes that were being tried. It is for a run that is stuck. It ends the run as `cancelled`, which neither
  Resume nor Continue... takes up, and its question says what that gives up (branch record SIF-83): pressed while a
  pause waits, it replaces the pause (its tooltip says so too), and the question adds "To keep it resumable, wait for
  the pause"; after an Abort, the run ends cancelled instead of stopped. On a run that could not come back anyway (one
  Pause warns about, whoever paused it), the question says only that it ends cancelled instead of paused or stopped,
  and why it cannot come back either way. A candidate handed out just before a pause or
  an abort, and stopped by it before its first simulation, is recorded the same way: cancelled, charged, nothing
  simulated, not counted as a failure of the link.
* **Let go** on a paused run deletes nothing and sends nothing: the header lets go of the run and returns to Start.
  The run stays paused on disk and can still be continued from Run status > Continue.... The button read "Abort" in that
  state until record 7.261, although it only let go.
* The header controls ONE run - the one started or resumed from this page, remembered across a reload - and shows
  it as a small outlined button beside the lit state ("12 of 60 evaluations", "at 12 of 60 evaluations" when paused,
  "completed at 60 of 60 evaluations"; press it for the run brief, below). When the run is of another task than the one
  the title names - a run taken over when the page opened - the chip names that task first ("graphgps_ldo1 · 270 of 800
  evaluations"), and so does Abort's question (branch record SIF-72). Its tooltip ends with the run's working time and,
  while it works, the time left - "Duration 5 min 01 s so far · about 10 min 02 s left", the run brief's line - so the
  number is read by hovering, without opening a window (branch record SIF-98). It is not the run chosen
  in the list of the bottom tabs: looking at an older run's data never takes Pause and Abort away from a live run. While
  the header's run works or is paused and the tabs show another, their line says "Shown: ..." and offers "Show the
  header's run" beside it.
  While a run is active or paused in the header, "Calibration" is not available. A finished
  Baseline simulation of a task saved from a cell records its result as the task's reference by itself
  (status record 7.78): once the run has come to rest the page reads the task again and no longer
  says "No real baseline yet" (one line since record 7.188, its explanation in the line's tooltip). Until the run the
  header remembers has answered its first status read, the main button is not offered ("Looking up the run..."); a read
  that gets no answer at all (the backend restarting, a failed read on the mounted drive) is asked again every 3 s for a
  minute instead of being taken for a run at rest, which used to show Start on a live run (review of 2026-10-07).
* A real run asks for the budget again at Resume (what is left of it). A run that was started with checkpoints or
  replay snapshots switched off, or one searched by Bayesian optimization (its `run.optimizer`, branch record SIF-83),
  cannot come back from a pause; Pause says so before it pauses.
* The run commands are in the header only (status record 7.109, 2026-09-29, user decision): the Run status tab's
  copies - Save now, Pause and save, Stop and save, Force cancel - went, as they did what Save now, Pause, Abort and
  Force abort do there. The tab keeps **Continue...** (a paused, stopped or interrupted run, with a new total budget) and
  **Export status**, in one row right under the run at a glance, above the facts, with the budget form or a refusal under
  them; a run's error stands in red between the run at a glance and that row, and stays the facts' last row too (branch
  record SIF-89: both came after about 20 facts, out of sight in a panel that shows about four). Continue waits, and says why, when the run folder holds no save point to go on from - a copy made
  without its save points, or deleted ones (record 7.215: `GET /api/runs/status` names it as `save_point`) - and when
  that save point was written by an older version of the optimizer code: continuing needs exactly that version, while
  Fine-tune and Evaluate only still load its model (record 7.221: `save_point_code` `older`). A run that is live when the page opens - started from another browser or the CLI - is taken into
  the header, and the message says so; a second run live at the same time as the header's own has no run buttons on this page.
* **The run brief** (record 7.264; plan [frontend run workflow](plan-frontend-run-workflow.md), "The run brief", added by
  record 7.259 - user: "pressing the green running text on banner will show you small popup window showing the running
  runs brief"). Pressing the header's run text opens a small window, "Running now": a card for the header's run, in any
  state, then one for every other live run under the output folder (another tab, the command line, a task's baseline).
  - Each card gives the task, mode, model name and MOCK or real; the evaluations used of the total, as a bar and in
    numbers, with the working time and, once the rate is known, the time left; the first feasible design and the best
    so far; where the model came from and the last save point.
  - Its two buttons: **Show results** (the bottom tabs show the run - what pressing the run text did until then) and
    **Open in Runs** (the Runs window at the run, its Details open). It has no run controls: the header keeps them.
  - It only shows, and has no timer of its own. The header's card follows the header's status reads; the other cards
    are read when the window opens and by **Refresh**, with the time they were read.
* **One launcher** (record 7.261, `frontend/src/launch.ts`; plan [frontend run workflow](plan-frontend-run-workflow.md),
  build step 1). Start, Calibration, Resume and Continue... go one way:
  - **Each says why it cannot go**, in its tooltip, before any press: the header's run is live or still being looked
    up, the configuration has blocking issues, the run cannot be continued.
  - **One launch at a time on this page.** A second press anywhere finds "Starting..." or "Resuming...".
  - **A launch is never sent twice.** Each carries a request id that the tab keeps until the answer has arrived. The
    backend answers the same id again with the run the first one made (`/api/runs/start` and `/api/runs/continue` take
    `request_id`). After a reload during a slow start the page asks what became of it (`GET /api/runs/request`)
    instead of sending it again, and says "sent before the page was reloaded". The backend writes that answer as soon
    as the run exists and before it starts the worker, so a launch whose acknowledgement was lost on the way (a failure
    inside the backend, a restart) is still found: after such an answer the page keeps the id and asks at once. Until
    the worker is there that record counts as "on its way", and a record whose worker never came (the backend died
    between the two) is let go of after a quarter of an hour: the launch is sent anew, and the run folder it had made
    stays as it is, `created` (record 7.271; the page never takes an unstarted run as launched) - and a backend that
    starts lets go of every launch the previous one left on its way at once, unless its worker is there. When the
    question itself gets no answer (the backend restarting) the id stays kept and the page asks again - for five
    minutes, then again at the next press or reload - and until that is known a press sends nothing new (review of
    2026-10-07; a failed question used to count as "unknown", and the run was forgotten).
  - **A refusal stays** on a line of its own - under the header for Start, Calibration and Resume, under Continue...
    in Run status - until what it depends on changes (the configuration, or the run), or its close button is pressed.
    It used to be the passing line under the header that any click took away. Nothing falls back to another kind of run.
  - **Continue... opens a budget form** instead of the browser's prompt: "Used 800 · New total [1,200] · Allows 400
    more". Whole numbers only: 1,200 reads as 1200, but 12,00 or a fraction is said to be wrong, and so is a total that
    is not more than the evaluations used. Empty, or the run's own total, = unchanged. A completed run can go on with a
    higher total too. Cancel, Escape or the form's Continue gives the keyboard focus back to Continue... - or to the
    Run status tab, when the run went on and Continue... is off - instead of the top of the page (branch record SIF-90).
  - **Before the press** the page asks the backend's continuation check (`GET /api/runs/continuation`, read-only:
    the press's own checks on the run's saved configuration, without the run lock or Virtuoso). The reason stands
    beside Continue..., and the header's Resume waits with it; a failed or cancelled run says "A failed (cancelled) run
    cannot be continued." there too (branch record SIF-90). Where the backend names an alternative - the task was
    saved again, the save point is from older optimizer code - a button offers it: **Fine-tune from its newest save
    point (a new run)** makes the next run on the page a fine-tune from exactly that save point, as one Undo step.
  - **Taking over is said.** A live run found when the page opens, or a task's baseline simulation started by Save task,
    becomes the header's run only when the header is free or holds a run at rest. A run found when the page opens gets a
    badge beside the run chip - "started elsewhere", or "recovered" for this tab's own launch found after a reload (record
    7.372; a line under the header until then) - whose tooltip says so and names a paused run the header lets go of, which
    stays paused: "... stays paused; continue it from Runs."; the baseline's message names it the same way. A task's
    baseline started while the header's run is live stays under Runs, and the header keeps its own.
  - The page sends request ids and asks the continuation check only where `GET /api/meta` lists them under
    `features`. A page newer than its backend works as before until the backend is restarted.
* The run shown is read every 1.5 s while it can change by itself: a worker is alive, its state is a live one, or the
  header is starting, resuming, pausing or ending a run and it is the run shown (status record 7.115, 2026-09-30; the
  last condition since 7.125 - a finished run in the tabs was read every 1.5 s while the header paused another run). A paused, stopped or
  interrupted run is read every 15 s (another browser may continue it), and an ended one once a minute. Until then a
  paused or stopped run was read every 1.5 s, and each read re-reads its tables.
* No poll reads while no window of the page can be seen - the page's tab is hidden or minimized and no pop-up window of
  it is in view - and each reads at once when one is seen again (record 7.279; a hidden tab went on with 30-50 requests a
  minute). A pop-up counts: Edge also calls the page hidden when its window is covered while a pop-up of it is in view.
* Whether a run's worker is alive is read from its lock at every status read (`RunLock.held`). The test asks for a
  shared lock, so reads at the same moment never take each other for a worker (record 7.134). An exclusive test did:
  for an instant after an Abort the header went back from "Start" to "Aborting...", and a Start or Resume could be
  refused as "already running". Starting or resuming waits up to 0.2 s for such a read to let go.

Browser checks: `frontend/scripts/run_control_check.mjs` (fixtures only, safe next to a live run) and
`frontend/scripts/run_control_live_check.mjs` (real MOCK worker; needs a scratch backend, refuses port 8765).

### Save now (added 2026-09-21, user request)

**Save now** (header, left of the main button; the Run status tab's copy went on 2026-09-29) saves the model of the RUNNING run
without pausing it. It is the run command `checkpoint`: the worker starts no new simulation, lets the one in
flight finish (with several in parallel: all of them), writes a complete save point exactly like an automatic one
(full training state, kind `manual`) and goes on by itself. Nothing is charged and nothing is lost; on a real
circuit the wait is at most the rest of the simulation that is running. The button reads "Saving..." until the run
itself reports that request as written (`manual_save` in `status.json`), then the line under the header says at how
many evaluations, the save point's id in its tooltip (branch record SIF-70; Run status's "Last save point" row says the
same). The save point appears in its model's Details (RL model window) as `saved with "Save now"`,
and pruning (`output.keep_last_checkpoints`) never removes it.

It is refused, in plain words, when nothing would come of it: the run is not running (a paused or ended run has
already saved everything), it is already pausing / stopping (that saves by itself; a pending pause, stop or cancel
is never replaced), or it was started with "Model checkpoints" switched off. Browser check:
`frontend/scripts/save_now_check.mjs` (fixtures only, safe next to a live run).

## The page's look and layout (record 7.158; one look since record 7.360)

On 2026-10-03 the user chose two looks for the page and five layout changes from a set of pictured ideas (answers "1 A+B,
2 yes, 3 yes, 4 yes, 5 yes, 6 Windows"): *Whiteprint*, ink on drawing paper, and *Silicon Night*, dark like Virtuoso's
canvas, with a switch in the header. On 2026-10-17 the user asked for new drafts - "dark mode only delete the day mode",
"use red, white and black as main colour", "improve readability", after a Tesla Roadster's screen - and chose Draft A
("go with draft A, build it into the workbench"; the drafts: private artifact "GATOR Roadster look"). Both looks and the
switch are gone; every panel, button and field stands where it stood.

**One look: the Roadster look** (record 7.360). Black ground, white type, one red.
- White is what is chosen, on or ready: Start, a ticked box, the chosen tab, a chosen or pressed button's outline, and a
  link, which is underlined (record 7.372; links and outlines were red until then). Red marks where the eye goes - the short
  bar under a chosen tab, keyboard focus, the active cell, the current run, a chart's line - fills Abort (red, the user's
  request of 2026-09-21) and colours an error, which always comes with its words. Amber is kept for rows not saved in the task and for warnings; a note's rule at
  its left is grey.
- Readability: text at 14 px (12.5 before), headings in sentence case instead of small capitals, roomier rows and fields
  (the list tables of the Runs and RL model windows a step tighter, so that each still fits its window), and cards told
  apart by their tone instead of boxes inside boxes. Every text colour reads at 4.5 : 1 or more on the surfaces it sits on.
  The columns keep their widths, the narrow layouts under 1101 px theirs, and the editors' toolbar its one line at
  1366 x 768.
- The banner: the name GATOR as a chip - a package outline with five pins along each long edge and the red dot that marks
  pin 1 (its tooltip holds the version) - then the task by the name the Task window gives it, with one grey line of its
  facts (class and PDK, the RL model's label; the revision is the tab line's since record 7.372); the connection as a pill;
  the run's state as four words, Ready, Running, Paused, Ended, the one that holds lit as a gear selector shows its gear
  (under 1400 px only that one, record 7.372), beside the run chip (its press opens the run brief, record 7.264) and, while
  windows are open, a button with their count (record 7.372); then "Configuration
  valid", Calibration, Save now, the "Next:" line and Start (white) and Abort (red), both round. From 1201 px the banner keeps
  one line - the task's facts and the connection's description give way with "..." first, then the task's name (branch
  record SIF-66: it was cut through a letter) - and a narrower window wraps it.
- Tabs: the chosen tab of every strip is white with a short red bar under its name; the three editors' tabs are one
  segmented control. An editor is told by its tab, not by a colour (the per-editor colours and layer swatches went).
- Output settings starts folded (user: "by default make output settings collapsible and collapsed so I can see training
  tab directly"), its line naming the experiment and the end of the output root; a fold or unfold is kept in this browser.
- The Training tab shows one run's key numbers as six compact tiles (two runs or more: the table, a row each), and Run
  status opens with the run at a glance: its state, the evaluations used as a large number with a bar, and four numbers
  (Spectre launches, learner updates, the first feasible design, the best design); the table below holds them all. The bar
  is red while the run runs (the current run), white once it completed, grey paused or stopped, the error red when it
  failed (branch record SIF-3; a completed run's red bar read as an error). Under the bar stands the run's working time,
  "Duration 29 min 50 s", with "so far" and the time left while the run works, as the run brief's card says it (branch
  record SIF-98: it stood only there). Below the best design's values, the table lists its variables - the device sizes -
  as the Runs window's Details do ("input_pair_width = 2.34558 um; load_capacitance = 250 fF"); a click copies them and
  says "copied" (branch record SIF-98: they were in the Details alone).
- The page never scrolls as a whole (SIF-3): the bottom panel's and the run column's scroll areas hold what is placed in
  them - an icon button's screen-reader label at the end of a long Run status had been placed by the footer, below the
  window, and the whole page scrolled about 500 px. Run configuration's model line is in the body font on two lines at
  most (it was cut to one line in a monospace font); its tooltip keeps the whole.
- Every pop-up window takes these colours from the page's stylesheet, which it copies when it opens. The Training charts
  draw the shown run in red, then white, blue and violet for compared runs (`--series-1` to `--series-4`); limits stay
  amber. The browser draws its own parts dark too (`color-scheme: dark`): scroll bars and the open list of a drop-down.

**The task's card** (record 7.362; from a preview of four arrangements the user chose Option D: "go with D, build it into
the workbench"). The task stretches across the left and the centre. Its name starts the editors' tab line - the button that
opens the Tasks window - then its revision and whether the rows are saved; **Show circuit**, **Check now** (its tooltip says
what the check compares), **Save as** and **Task file** end it. What the task says about itself - loading, Blocked, MOCK,
its baseline, the check's result - stands under the toolbar. The circuit - labels, picture, notes, hierarchy - is a column
of its own, folded away by default so that the rows take the width (1264 px instead of 952 at 1680 x 1050; at 1366 x 768
every column of Parameters in view instead of 7 of 10), and **Show circuit** brings it back beside them, kept in this
browser. The two ways to a new task are in the Tasks window, **New task: From a Virtuoso cell...** and **From an ngspice
netlist...**; while the page follows a Virtuoso cell or an ngspice task, **Virtuoso cell...** or **ngspice netlist...** on
the tab line goes back to its window. Under 1101 px the editors come first and the run settings under them.

**Nine changes of record 7.372** (user: "give improvement ideas of the frontend", then "fix everything"):
- Red stays for attention: links are white and underlined, a chosen or pressed button is outlined in white, Save as and the
  sort marks lost their red (above).
- The banner's facts leave the revision to the tab line's task chip.
- "not saved" beside the task's name is a button: it opens what differs from the saved task, table by table (each table's
  name shows it), with **Reload saved values** (it asks first, as choosing another task does; Undo takes it back) and **Save as...**.
- A cell entered while the table has room for under about four rows - a small screen with the bottom panel open - folds the
  bottom panel to its tab line; a tab brings it back, as before.
- A run the header took over when the page opened is a badge beside the run chip - "started elsewhere", or "recovered" for
  this tab's own launch found after a reload - its sentence (and a paused run's "continue it from Runs") in the tooltip; it
  was a line of its own under the header.
- The reward in Run configuration is one line - "Reward: the tested one - <objective>" - its sentence folded behind it; a
  configuration with other values says how many on one line, which ones folded, "Use the tested reward" in view.
- Under 1400 px the run's state shows only the word that holds.
- With no task yet, the task's lines under the toolbar offer **Open Tasks** and the ways to a new task.
- **Windows**: while pop-up windows are open, a button in the banner with their count lists them; a press brings one to the
  front, **Close all** closes them. A task file not applied and folders not saved are kept for the next opening (SIF-87).

**Research experiments** (record 7.163; user: "Check the research experiments module and see which should be kept",
then "Remove both" and "Fold them"). Since record 7.166 its heading looks like the other modules' headings, and its note
("Optional for a single run; missing labels stay unspecified") is the tooltip of its name; over the name the pointer is
the hand, as over the rest of the line, since a press opens or closes the module (record 7.169). The module shows the three labels every research table uses - **Method label**,
**Comparison pair ID**, **Budget checkpoints** - and folds the six that only a transfer study uses (Split, Generalization
level, Training sources, Task order K, Pretrain seed, Ablation labels) into a closed "Transfer study" line. Experiment
group and Test tasks were removed: nothing read them (Output settings' experiment name groups a run's folder). A
configuration saved with them still loads without them, and keeps its configuration hash (`RETIRED_RESEARCH_FIELDS`).

**One tab style** (record 7.164, user: "day and night tab style different, change the day style to night one"): every tab
strip is drawn alike; since record 7.360 the chosen tab is white with a short red bar under its name. Records 7.162 and
7.164 made both looks share every size and one tab style; with one look that holds by itself.

**Room for the tables** (record 7.179, the user's "go on" after design advice 1-3). The bottom panel starts folded while no
run is shown (see the splitter above). Run configuration reads as a property sheet: a number's label and its box share one
line, the box at the right; the caps on launches, retries and wall time and the two consecutive-failure rules sit in one
closed **Limits** fold whose line names the limits that are set ("Limits - 42 launches"). In Output settings the list of
what is always saved is one line with the whole list in its tooltip, and what the backend found for the output root is one
line ("writable · 270 GiB free · D:\gator\outputs") with its table folded behind it, open at once when the root cannot be
written. The folder's own size ("used here") is measured on its **Measure** button only (record 7.189): adding up the
files under the root took 0.7 to 2 s of disk work on D: at every page open, for this one number. Since branch record
SIF-91 each of these presses says while its answer is on its way ("Testing...", "Measuring...", "Reading the folder..."),
and a test's answer says when it came ("writable · tested 14:03:22"): a writable root's answer read as the look before it.
The output root (and "Use this folder" in an open folder list) locks while the header's run works or a Start or Resume is on its way (it followed only the run the bottom
tabs show), and "Current run paths" names the run shown ("Of the run shown: <its folder>"). Experiment ID's list holds the
experiments of the runs under the root of the loaded task's kind (Start looks for a MOCK task's under `<root>/mock`); one
picked sets the experiment name with it. Browser checks:
`frontend/scripts/room_check.mjs`, `frontend/scripts/output_panel_check.mjs`, `frontend/scripts/run_control_check.mjs`.

**Drop-down lists in the page's colours** (record 7.173, user: "fix the color issue of the drag down menu in night mode, it
is hard to read"): the browser draws a select's open list from its options, and a select in an editor cell (Probes'
analysis, for one) has no background of its own. Every option has the field colour and the text colour (a disabled one the
muted colour); `looks_check.mjs` measures every option of the page, Probes cells included, at 4.5 : 1 or more.

**Colours by name.** Every colour of the page is a named value in `styles.css` (`:root`); `roadster.css`, loaded after it,
holds what the look adds: shapes, sizes, the banner, the tabs (until record 7.360 `themes.css` held the two looks' values
and drawings). Before the looks came, the 86 colour values written into 69 rules were replaced by names carrying exactly the old values; screenshots of six views of the live page were identical before
and after, pixel for pixel (the seventh, the Runs window, differs only in its "read at" time, as two shots of one build
do). The fonts are Windows' own, so nothing is downloaded: Bahnschrift for headings, tabs and table heads, Segoe UI for
text, Consolas for numbers and ids. Another system shows its own fallbacks.

**The title block.** The header names what the page works on: since record 7.360 the task, by the name the Task window
gives it, then one grey line of facts - Class · PDK, the saved task's revision and the RL model's label (record 7.159; its
first cell was the project name until the user removed that box). They are read-only; the fields stay in their panels, and
the circuit panel puts them in the header. The version and environment line is in the tooltip of the GATOR chip. Since
record 7.182 the **Connection** button is the block's last cell (user: "move the conection button to the header"). Record
7.182 also took the task name out (user: "remove the current task name on the header"); Draft A of the Roadster look,
which the user chose on 2026-10-17, brings it back. Only a followed task is named so (branch record SIF-88): a cell read
from Virtuoso is "library/cell (not saved)" ("choosing a Virtuoso cell" before a cell is chosen), and a page that follows
no task reads "no task chosen". The RL model fact falls back to the task's name for a followed task only, and reads "not
set" otherwise. Until then a fresh page titled itself "task" (the empty configuration's name), and a cell kept the name of
the last task loaded.

**When the page cannot be drawn** (record 7.188, design advice). A failure while drawing the page used to leave it blank.
Now a panel names the error and offers the ways out. **Undo the last change** draws the page again from the configuration
before the last change: the configuration and its Undo history sit above the panel, so they outlive the failure. **Export
JSON** downloads the configuration as it is, and **Reload** opens the page again. When there is nothing to undo - the
configuration saved in this browser already fails when the page opens - **Start from an empty configuration...** downloads
the saved one first and opens the page empty. "Details for a bug report" holds the error's stack. A second panel around
everything catches a failure above that one, without an Undo. Browser check: `frontend/scripts/crash_panel_check.mjs`.

**Callouts without frames** (record 7.218, user: "work on fewer boxes inside boxes"). Inside a panel, the header or a
window, a callout has no frame of its own. A rule at its left sets it off: grey for a note, a confirmation and a group (Add
a connection, Matched devices; the accent colour until record 7.360, red since, would have read as a warning), white for
Calibration ready, the status colour for a status. Only a status that must not be missed
keeps its faint fill: a blocking issue, a warning, MOCK / REAL, a connection test result, the settings problem. A callout
inside another one, such as the review inside Matched devices, has no rule of its own; its heading sets it off. Fields,
buttons, tables, chat areas, charts and the panels keep their frames, and the MOCK banner between the header and the
columns keeps its frame too. Browser check:
`frontend/scripts/callouts_check.mjs`.

**The splitter above the bottom panel.** Drag the top edge of the bottom panel to give it more or less room;
double-click it to fold the panel down to its tab line, and again to open it. From the keyboard: Tab to it, then the
arrow keys (24 px a press) or Enter. A press on one of its tabs or on the header's run line opens it
again, and since record 7.179 so do Start, Resume and a run chosen in Runs.... While no run is shown (a fresh page, a run
that is gone) it starts folded to its tab line: its tabs show a run, and with none it took a third of the page saying "No
run selected"; opened by hand it stays open for that page. The height and the fold are kept in this browser (`gator-workbench-bottom-v1`), and the
editors always keep the window height less 280 px. Windows narrower than 1100 px keep their own stacked layout and have
no splitter.

**One line per row in Data tables.** An id (a column ending in `_id`) is written in Consolas and ends in "..." when it
is long; hovering shows the whole value and a click copies it. A time keeps its full width, no word is cut in two, and
a JSON value has a column of bounded width of its own.

**Data tables and Output files follow a live run** (branch record SIF-99). Both were read once, when they opened, and
went stale without a word while Logs and Training followed the run. Now Data tables reads its table again each time the
run writes its rows to disk (a flush, every 64 evaluations by default), and Output files reads the run folder again at
each new save point and once more when the worker ends; a run at rest is read once, as before, and nothing is read on a
timer. Both count lines end with when they were read ("Read at 14:03:22."), and Refresh shows the hourglass ("Reading...")
while a read is on its way; the rows on screen stay until the new ones come. Data tables has two lists beside the table
list: **25 / 100 / 500 rows** and **newest first / oldest first** - the oldest are the table's first rows, in the order
they were written, so an early evaluation no longer needs the CSV; the defaults are the newest 25, as before. Output files
has a filter box (every word typed must stand in the file's path, in any case; the count then says "4 of 508 files shown,
320 MiB in all.") and its column titles sort, as the Runs window's do: File (A to Z at first), Size and Modified.

**A copy says how it went** (branch record SIF-94). Run status's Run folder and best design variables (SIF-98), Output settings' **Copy path** (the word just
before it) and its Current run paths, and the folders of the RL model window say "copied" where they were clicked, for
1.5 s, or "could not copy" when the browser refused the clipboard (its tooltip: select the text and copy it with Ctrl+C).
Data tables' cells and Output files' **Copy run path** say it on their tool line ("Copied run_id.", "Copied the run
path."; a refused run path is written there, to select). A click in a pop-up window copies through that window's own
clipboard, as the Connection, Agent and Runs windows did already: a browser refuses a write from a window that does not
have focus, and the RL model window's folders went through the main page's, failing unsaid.

**Each editor's colour.** Parameters, Probes and Specs each have a colour, used on their tab and on their table's header
row. The Specs line lists the Probe ids as Probe-coloured chips; its words are the same as before.

**The circuit picture.** A second on-screen picture by user decision, on the graph view's terms (drawn in the browser,
nothing written). In the circuit column (**Show circuit** on the editors' tab line, record 7.362), the circuit appears as a small node-link drawing in the
graph view's manner: devices as boxes (nmos blue, pmos rose, passives green), nets as dots, supply on top and ground at
the bottom. It is placed by the graph view's own hard-coded hints (`circuitLayout.ts`) and drawn from the circuit summary
the task's load already returns, so nothing more is asked of the backend. It shows:
- the DUT's devices when the circuit names its DUT, else every device but the testbench's sources;
- as the supply, if the circuit marks none, the net a voltage source holds against ground and devices conduct from;
- names without their hierarchy where that stays unambiguous (DUT/M1 reads M1).

Pointing at a Parameters row, or tabbing into it, lights the devices that row sizes: its own and those of the rows tied
to it by `binding_group` (`w_pair` lights M1 and M2). The block folds into its heading line, and the fold is kept in
this browser (`gator-workbench-circuit-picture-v1`).

Browser check: `frontend/scripts/looks_check.mjs` (47 checks, hermetic).

## What is real and what is mock

| Path | Status |
|---|---|
| MOCK tasks: none since 2026-09-30 | The workbench offers no MOCK task since the user's request of 2026-09-30 (record 7.128). The last one, `synthetic:gpdk045_ota5` - the analytic toy backend (`origin=synthetic`) on the netlist and device mapping of the GPDK045 OTA5 - is refused with a plain note, as are the four toy tasks it had replaced on 2026-09-22 (status record 7.59). The toy backend stays for the tests: they register that circuit as their stand-in through `GATOR_WORKBENCH_SYNTHETIC_FIXTURES` (`tests/workbench/fixtures/synthetic_fixtures.json`, set in `tests/conftest.py`), and so do the browser checks' scratch backends (`frontend/scripts/run_checks.sh`). MOCK data stays labelled `provenance=mock`, under `<output_root>/mock/`, out of real aggregates; a model it trains never loads into a real run. |
| `real:gpdk045_*` tasks: none left | The four verified built-in circuits were removed on user request: `real:gpdk045_ota5` and `real:gpdk045_vco` on 2026-09-23 (status record 7.73, their example cells deleted from Virtuoso), `real:gpdk045_ota7` and `real:gpdk045_ldo` on 2026-09-30 (record 7.128, with their example netlists and configurations - so the M5/M6 audits and the frozen M6 plan re-validate from a checkout before that commit). A configuration that names one opens with a plain note and cannot start; the names stay reserved. The real tasks are the ones saved from a Virtuoso cell (next row) and the ngspice ones. |
| `ngspice:<name>` tasks (added 2026-09-23) | A SPICE deck pasted or loaded in the **ngspice netlist...** window and saved as a task. **REAL** circuit simulations by ngspice (`origin=real`, `provenance=real`), on this machine or over SSH through an ngspice connection - no license, no Virtuoso, but counted, authorized (Start asks) and recorded exactly like every real run, so the data is never mistaken for mock data. Its models never load into a MOCK run and the other way round; they are interchangeable with Virtuoso real runs as far as the network contract allows. |
| Arbitrary native cellviews | Read-only browsing through the bridge. Optimizing one needs a saved task, which runs on a WORKING COPY of the cell - since 2026-09-23 the copy you made in Virtuoso and declared on the read; the first save uses that declared copy; Save as on a saved task makes a separate copy (record 7.246): a run writes instance values into that copy (the form writer since 7.66), never into your original design, and no cellview is created or redrawn. |

### Choosing a registered task: whose rows Parameters, Probes and Specs show

The three tabs hold rows of the *configuration*, so they belong to a task. Choosing another task (a double click in the
Tasks window, opened by the task's name at the start of the editors' tab line, record 7.362) brings that task's rows. A fresh page has no task until you choose one (the MOCK task
that used to open there, and the verified OTA7 and LDO circuits with their targets of record, were removed on 2026-09-30,
record 7.128):

| Task | Parameters | Probes | Specs |
|---|---|---|---|
| a profile created from your own cell | the rows the profile fixes | one per result its circuit type produces, ready to carry a target | **none**: requirements are never inferred from a circuit. State yours, or press "Draft with agent..." |

* There is no **Project name** box any more (record 7.159, user: "remove the project name box in the Project module"): it
  only filed a run's model for the next resume / fine_tune / frozen, which the RL model's own label does now (see "The RL
  model's label"). The separate editable **Task name** field went earlier (record 7.146): the run-folder and export label
  (`project.task_name`) comes from the selected task. A configuration keeps its old `project.name`, unshown.
* Selecting a task automatically reads its saved rows. The selected task, **Circuit class / PDK id**, run label and all
  three tables change together after that read succeeds. While loading, the previous task remains selected with its
  own rows; a loading message names the requested task. A failed or superseded read cannot replace the current task.
* Edited rows prompt **before** switching: OK discards those edits and loads the chosen task; Cancel keeps both the
  current task and its edits, so they can be saved first. Edits made during the read are protected too. One **Undo**
  takes back the whole task choice, including its rows and run label.
* The separate **Load task / Reload saved values** icon was removed in 7.260. Double-clicking the current task in the
  Tasks window reloads its saved rows, with the same edit-discard confirmation. The explicit **Reload saved values**
  action remains in the save-conflict message.
* Run settings (the RL model's label included), output and research settings stay unchanged during switching and reloading. No real budget is
  suggested and no simulation, task save or Virtuoso write is triggered by selecting a task (record 7.146).
* The bottom tabs follow the choice (record 7.212): they show the chosen task's newest run, or no run when it has none
  (see "The run window" below).
* A profile created from a cell brings its own result registry (the built-in LDO and VCO tasks brought the registry of
  record of the real cross-category experiment until they were removed). A registry stated in the configuration
  (`run.advanced.spec_registry`) still wins. Units `V/V` and `V/A` (line / load regulation) are accepted.
* In the three editors a field a row does not state is shown with the value the backend uses for it (`hard` on,
  `active` on, ...), not as an empty or unchecked box.

Browser check: `frontend/scripts/task_rows_check.mjs` (fixtures, safe on the live backend; `--live` reads the real
starters from a restarted or scratch backend). Tests: `tests/workbench/test_wb_real_starter.py`.

### The Tasks window: the task-name button (2026-10-07, record 7.260, user request)

User: "make the loaded task a button similar to the runs... button style. It opens a new window showing all the tasks."

The task's name starts the editors' tab line, one button followed by its revision and whether the rows are saved (record
7.362; until then the Project column's **Task** row) (`mscr_ota5t`,
with a mark when something keeps it from running: `[blocked]`, `[ngspice: choose its
connection]`, `[MOCK]`; or a placeholder: "(choose a task)", "(none: MScR/x is read from Virtuoso)", "(none: the saved
source was removed)", "synthetic:vco (removed)"). There is no separate **Tasks...** button beside the name.
Pressing the name opens the **task window**, a browser window of its own that can stay open next
to the workbench (allow pop-ups for the page if the browser blocks it). It lists every registered task, one row each:

| Column | What it says |
|---|---|
| Task | The name the task is shown under: its own name, without the `real:` prefix for saved Virtuoso tasks (ngspice names retain `ngspice:`), or the name it was renamed to, with "internal name ..." under it (record 7.302, **Rename** below). Availability marks and the MOCK badge appear beside the name. There is no Kind column or Kind detail (7.249). |
| Class | The circuit class label. |
| Cell | The library and cell the task runs in (the copy you declared), and its testbench cell. |
| Rev | The saved revision. |
| Saved | When the task was last saved (local time of this computer), to the minute; the tooltip has the seconds (branch record SIF-24). |
| Baseline | When the task's reference was recorded by a finished Baseline simulation; "none" until then. |
| Sizes / results | How many sizes the task varies, how many results its testbench measures. |
| Newest run | The task's newest run under the output folder: started, state, evaluations, first feasible - the run the bottom tabs show when the task is chosen (record 7.212). A link (record 7.264): it opens the Runs window at that run, with this task's runs only. |
| Runs | How many runs the task has, Baseline simulations included. A link (record 7.264): it opens the Runs window with this task's runs only ("Only the runs of ..."; **Show every run** takes that back). Neither link chooses the task. |

* **A double click on a row** makes the page follow that task - so do **Enter** on the row and **Follow this task** at
  the start of the Details of a task the page does not follow (branch record SIF-100: a keyboard could not follow a task,
  and the Runs window's Details have Load run): exactly what choosing it in the old list did - its
  Parameters, Probes and Specs come into the editors (edits you made are asked about first, Cancel keeps them), the run
  label follows, the bottom tabs show its newest run, one Undo takes the whole choice back. The row of the task the page
  follows is marked. Then the window closes (record 7.291, user request 2026-10-09: "after selecting one target task,
  model or run, close the pop up window"); it stays open when the edits question is answered Cancel or the task cannot
  be read. The edits question is asked in the Tasks window itself (branch record SIF-84): asked by the main window, it
  opened behind the Tasks window, which stood still with "loading..." on the row until the question was found.
* **Details** opens everything else under the row: what the task is, the cell it runs in and the cell it was saved from,
  its netlist of record, how it is measured, created / saved / baseline times, its state, the run label, its runs - and
  its rows: the Parameters it varies (searched rows with their ranges, follower rows), its Probes and its Specs with
  their limits, read from the starter route when the details open.
* **Rename** (record 7.302, user request 2026-10-10: "add rename functionality to tasks"): the first line of a task's
  Details is a **Name** box with a **Rename** button, as a saved model has. It changes the name the task is SHOWN under -
  in this window, on the task's name on the editors' tab line, in the Runs window's task link ("ldo1_relaxed
  (real:graphgps_ldo1)") - and the label new runs of the task are filed under (the run label). The page that follows the
  task takes the new label at once, with no Undo step (branch record SIF-100: it waited until the task was chosen again,
  a double click that asks to discard edits). Nothing else changes: the task's key, its files, its Virtuoso cell and every run and saved model made on
  it keep the internal name, so each run still belongs to its task and a model still loads on it; a configuration file
  and the command line name the task by its key as before. A name is a task name (a lower-case letter first, then
  lower-case letters, digits and underscores, 2 to 40 characters); a name another task has, or is shown under, is
  refused. Typing the internal name takes a rename back. The names are kept in the settings folder
  (`task_names.json`); deleting a task forgets its shown name. A server older than this page lists no shown names: the
  Name box is off and the button says so.
* A press on a column title sorts by it (again: the other way; rows without a value stay last). The filter box narrows
  the list by any word of a row: name, class, cell, a date. Task names sort as displayed; canonical task IDs stay unchanged for selection, saved configurations, runs and models (7.249).
* **Nothing in the window updates by itself.** The task list is read when the button is pressed - also while the window
  is open: the press brings it to the front and reads the list again (branch record SIF-100) - and by **Refresh list**
  (which reads the run list again too; otherwise the run columns show the page's own run list - read when the page
  opened and after every task choice). A workbench server started before this was added lists runs without their task:
  the run columns then stay empty and the window says so.
* The task row's facts (`testbench`, `saved_utc`, `created_utc`, `baseline_recorded_utc`, `status`, `variables`,
  `results`) come with `GET /api/tasks`, all from the task's own entry file - no other file is read. A server older than
  the page leaves those cells empty ("-").
* **Delete task** is inside this window, beside **Current task: <name>**, for a deletable task. It acts on the task the
  page follows; double-click another row to change that task. Confirmation opens in this window, and failures are shown
  beside the action. So is what a delete did (branch record SIF-100): "Task real:<name> deleted; its files are kept in
  <folder>. The page now follows its cell <library>/<cell>." The line stays while the page stays there: it goes once the page follows another task or another cell (chosen in the Virtuoso window). The module outside has no delete or reload icon. The backend still keeps deleted files aside and
  refuses deletion while the task is running.

**Folders** (7.250): the sidebar lists **All tasks**, **Unfiled**, and named folders with task counts.
Use the **New folder** icon (folder with a plus) to create one; it opens, empty - unless tasks are ticked (branch record
SIF-101): then the folder shown and the ticks stay, its question says so, and the new folder is in **Move to…** at once,
so tick, New folder, Move to… works in that order (opening the empty folder let the ticks go). **Rename** uses a pencil and **Delete folder**
uses a bin; all three retain tooltips and screen-reader labels (7.251). Tick tasks (or the header checkbox for all shown rows), then choose **Move to…**.
A folder filters the table; search and sorting apply inside it. Changing the filter or folder clears selection, so
hidden tasks cannot be moved accidentally. In All tasks, a task's folder appears below its name. Double click still
loads the task; checkboxes only select it for a move. **Rename** keeps membership; **Delete folder** sends its tasks
to Unfiled without deleting any task, run or model. New tasks start in Unfiled.

Folders are saved in the backend's `task_folders.json`, shared across windows and browser reloads; **Refresh list**
reads them again. Runs and saved models have folders of their own since record 7.263 (`run_folders.json`,
`model_folders.json`, the same lock and checks; the Runs window below), drawn by the same component (`Folders.tsx`). Failed reads/saves are shown and can be retried. Organization changes neither task IDs nor encoder
settings, saved circuit files, revisions or run/model provenance. The initial organization uses the verified encoder
of existing runs, plus the declared GraphGPS and Group Cross Attention task copies; historical `_rgcn` names alone
are not encoder evidence. The initial folders contain Graph Transformer (22), GraphGPS (6), and Group Cross Attention
(6) tasks. API: `GET/POST /api/task-folders`, `PUT /api/task-folders/assign`, and
`PATCH/DELETE /api/task-folders/{folder_id}`. Names are unique ignoring case. Updates merge atomically under a file
lock; removing a folder clears only its assignments.

Browser checks: `frontend/scripts/task_list_check.mjs` (the window, double click, Details, filter, sort, Refresh, an
older server; fixtures, safe on the live backend); the checks that used to choose a task through the drop-down
(`task_rows_check`, `task_run_check`, `virtuoso_source_check`, `circuit_source_check`, `ngspice_window_check`) choose it
through the window with the harness's `taskWindow`. Backend test: `tests/workbench/test_wb_task_save.py` (the facts).

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

### A Probe that measures the sizes (added 2026-10-11, record 7.308, user request)

Some of what a design is judged by is not simulated at all: how much room it takes follows from its sizes. A Probes row
with the source **`size_estimate`** holds such a value. Its `signal` is not a Maestro expression but a formula over the
widths the task varies; the value is worked out for every design from that design's own sizes and stands in the result
beside the simulated ones, under the row's source name. A Specs row reads it through the Probe like any other value,
alone (`m_cell_width`) or inside an equation, and it is recorded, judged and shown as every Probe is.

| In the formula | Value |
|---|---|
| `fingers("pattern", limit)` | the fingers the matching transistors fold into: the sum of ceil(width / limit) |
| `width("pattern")` | the sum of the matching transistors' widths |
| `count("pattern")` | how many transistors match |
| `larger(a, b)`, `smaller(a, b)` | the larger and the smaller of two values |

with numbers (SI suffixes), `+ - * / **` and brackets. A pattern is written in double quotes and uses `*`, `?` and
`[...]` as file names do; it is tried on the instance as the Parameters rows write it (`DUT/mn20`) and on its last part
(`mn20`). Unsupported quoting, including single quotes, is reported as `size_formula_rejected` before a run rather
than crashing validation (record 7.323). The first use is the width of a standard cell before layout: the row height is fixed, so the area follows the
number of gate columns - `0.253u + 0.288u * larger(fingers("mn*", 400n), fingers("mp*", 630n))` for the gsclib045
flip-flop of the transfer plan (a typical error of 9 % against the real outlines of 513 cells of that library).

Limits: only widths (the parameter `w`) that the task varies are seen - a transistor of fixed size adds a constant,
which the formula can state itself; a pattern that names no varied width is refused before a run; a value that cannot
be worked out (a limit that is not positive, arithmetic that fails) is missing, never a number. Such a row may stand
beside Maestro outputs or beside a circuit type's results; a task with nothing but size estimates cannot be saved. The
row is not written into the Maestro test and costs no simulation. Tasks measured by ngspice do not hand it the sizes yet.
The page shows it in the Probes table with the source it has; there is no button for it - the row is written in a task's
file or its JSON.

### Fewer columns in Parameters, Probes and Specs (2026-09-26, user request)

Fourteen columns went, because no run ever read them - and for several the only value besides the default was a run
blocker. Parameters lost `name`, `target_kind` (its other value, a design variable, blocked the run), `candidates` with the
`discrete` value type (a candidate list ran only when it was a uniform grid, which is `lower`, `upper` and `step`), and
`relation` with `expression` (an expression ran only when it equalled a constant times the leader, which is `ratio`).
Probes lost `function`, `window`, `at_frequency_hz`, `integration_band_hz`, `branch_direction`, `loop_definition` and
`crossover` (no backend extracts anything from them; a filled `function` blocked the run), `on_failure` (one allowed value)
and `validity` (checked for form only; run-time validity comes from the simulator's own flags). Specs kept every column.

What stays but steps back: `soft_weight`, `active`, `basis` and **Margin sides** of Specs (**Missing value = failed** was
among them until record 7.299: the optimizer does it for every hard spec now, and the column is not shown),
(since record 7.172) `value_type`, `step`, `scale` and `ratio` of Parameters, and (since record 7.183) `hard` and the
scale of Specs, headed **Scale**, are shown after **More columns** at the right of the toolbar (the choice is kept in the
browser). They keep their values either way: Add fills them, the agent may set them, a task file stores them. The scale
(`normalization_scale`) may be left empty: a miss is then measured against the size of the limit (the larger of |lower|
and |upper|). A limit of 0 has no size, so such a row needs a typed scale and blocks a run without one.

Old rows still load. A task file, a run's `effective_config.json` or an imported JSON written with the retired columns is
read as before: the schema drops them when it reads a row (`schema.RETIRED_PARAMETER_FIELDS`,
`RETIRED_MEASUREMENT_FIELDS`), keeps what they meant (an expression relation becomes the ratio, a uniform candidate grid
becomes lower/upper/step) and refuses in plain words what the run refused before (a design variable, a non-uniform candidate
list, any other expression). Both hashes see the retired columns at their old defaults (`schema._hashed`), so every earlier
run resumes, its checkpoints load, its task keeps its `task_id` and approvals still bind - checked against the three runs on
this machine and the MOCK starter's documented task hash (`5f181ef3...`). The browser's copy of the rows is migrated the
same way when the page loads (`store.ts migrateConfig`), so the editors' rows equal the rows the backend serves; a value the
browser cannot keep is written into the row's notes. Legacy spec `measurement_id` references are converted to
equations before computed probes are inlined and removed; an explicit equation still wins (record 7.174).

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

**Fewer columns again (2026-10-03, user: "check the current tabs are there any columns redundant?", record 7.172).** The
seven saved MScR tasks showed which columns repeat what another already says:
- Retired, like the columns above: Specs' `target` and `tolerance` with the "target ± tolerance" choice (it was exactly the
  interval [target - tolerance, target + tolerance], and a tolerance on any other spec only loosened its limit), and the
  Probes' `expression` with its `result_source` "expression" (a probe computed from other probes: that is a spec equation's
  job since record 7.52). An older row loads with what they meant - the limits they made, the arithmetic written in
  parentheses into the equations of the specs that used the probe - and both hashes see them at their defaults, so the
  seven tasks and every run on this machine keep their identities (checked).
- Not shown, kept in the rows (the parked AnalogGym import and the task files still write them): Parameters'
  `initial_value` (Save task empties it, so it showed nothing) and Probes' `result_source` (a task measures one way: a new
  probe takes the way of the rows there, where it used to get "backend_profile" in a Maestro task too).
- Filled for you: a Maestro output's Probe ID is `m_` + its output name, shown and not typed; it follows a renamed output,
  and so do the spec equations that use it, in one Undo step. A spec whose equation becomes one probe takes that probe's
  unit while it has no limits yet. The Probes column that holds a Maestro output's expression reads **Expression**.
- On a follower row (one with `binding_group`) the fields its leader decides - `optimized`, `value_type`, the bounds,
  `step`, `scale` - are greyed, with why in their tooltip: the written value is the leader's times the ratio.

### The formula bar: a cell's whole value (2026-10-05, record 7.175)

User: "add excel like single cell whole row text edit somewhere for long text editing which cant show everything in the
cell". Above each table of Parameters, Probes and Specs stands a formula bar, as in a spreadsheet. A click on a cell (or
reaching it with Tab) marks the cell and shows, in the bar, where it is - the column and the row's ID, e.g. `notes ·
input_pair_width` - and its whole value, in a box as wide as the table that grows to a few lines for a long text. The
column's format is the tooltip of that name, the whole name under it: the name's box takes its text's width, 210 px to 40 %
of the bar, and ends a longer one in "..." (branch record SIF-66).

Typing in the bar changes nothing until **Enter** (or Tab, or a click elsewhere) writes the text into the cell, as one Undo
step, and goes back to the cell; **Esc** keeps the cell as it was. A number is read as its cell reads it (plain or with an
exponent, 2.5e-3; a word is refused in words and the cell stays). A list (analysis, constraint, ...), a tick box and a value
that follows another field (a Maestro output's Probe ID, a follower's bounds) are shown in the bar and not typed there: its
tooltip says why, and for a list names its choices. Typing in the cell shows at once in the bar. The bar writes through the
same path as the cell, so what follows a cell follows a typed bar too (a renamed output's Probe ID and the equations using
it; a spec's unit from its one Probe). Browser check: `frontend/scripts/formula_bar_check.mjs`.

### Tied rows, spreadsheet keys and a pasted block (2026-10-05, record 7.180)

The editor tables behave more like a spreadsheet (design advice 4 and 6, the user's "go on").
- **Tied rows.** A Parameters row whose `binding_group` names a row of the table follows that leader - the leader decides
  its size - and is folded under it; the rows keep their order. The leader's first cell, next to its tick box, counts its
  tied rows (`▸2`) and opens and folds them; an open tied row is marked `↳` and its ID indented. A tied row with an error
  report, or with the chosen cell, is never folded away. The LDO task shows 16 of its 24 rows.
- **Keys.** Up and Down go to the same column of the row above or below, passing folded rows; Enter goes down and
  Shift+Enter up, as in Excel. A list keeps its own keys.
- **Pasting a block.** Tab-separated lines (what Excel copies) pasted into a cell fill the rows in view from that cell down
  and the columns in view from it right, as one Undo step. Each text is read as its column takes it (numbers plain or with
  an exponent, a list's choices, true/false or x for a tick box, `>=`/`<=`/`interval` for a limit); a text that cannot be
  read is named and its cell left as it was; lines below the last row are named, not added; cells a leader decides, or
  that follow another field, are kept. A line under the formula bar says what happened. One value pastes as before.
- **Column widths.** An ID column is wide enough to read (140 px), a leader's name 120 px, a unit 52 px; a tick box no longer
  takes the 84 px of a text box; the Issues column is narrow while no row has an issue. At 1680 x 1050 the LDO task's
  Parameters table fits without scrolling sideways.

- **One way of writing a quantity** (record 7.208, user: "a unified way of unit representation in the parameters probes
  and specs windows considering the convenience usage of users", chose "Prefix per value"; then "dont use greek characters
  for unit, use english letters instead"; it replaces record 7.181's readable numbers). Every bound, limit and scale is
  written as Virtuoso's forms write it - the number, an SI prefix and the unit, in English letters: a width `1.205 um`, a
  length `45 nm`, a resistor `9.535 kohm`, the LDO's quiescent-current limit `400 uA`, a bandwidth `100 MHz`, a PSRR
  `-30 dB`, a phase margin `60 deg`; a count and a plain number without a unit. The digits are the stored number's own,
  moved and never computed, so what is shown is exactly what is stored; no stored number or unit changes by being shown
  (tasks, baselines and hashes are untouched).
  - **Typing.** A cell, the formula bar and a pasted block read `450n`, `450 nm`, `0.45 um`, `4.5e-7`, `400 uA`, `0.4mA`,
    `2.2 kohm`, `60 deg` - and the Greek spellings `µm`, `kΩ`, `°` too. A plain number is in the row's unit; a prefix or a
    unit says its own. Another quantity (`200 mV` in a current row) or an unknown unit is left unread, and a line under the
    formula bar says why in words.
  - **No Unit column in Parameters and Specs** (user: "can you delete the unit column but keep the rules for value";
    the rows keep their unit). A row's quantity comes from what it is: a parameter of a known kind (w and l lengths, m and
    nf counts, r a resistance, c a capacitance), a Spec on one Probe from that Probe; otherwise the unit the row has. A
    value must be of that quantity: a length takes `m`, `mm`, `um`, `nm` ..., and `5 mV` is refused in words. A row whose
    parameter changes (w -> m) takes the new kind's unit; a row without a unit takes the one its first typed value says.
    Ctrl+C copies a value as the cell writes it (`2 um`), and a paste reads it back; Ctrl+D fills a value converted into
    the target row's unit, and a row of another quantity is kept.
  - **Probes keep their Unit column** - they have no values: it says what the probe measures, chosen from a list like the
    page's other lists, in English letters (V, A, Hz, dB, deg ...). A Spec on the Probe follows a change of quantity, its
    Scale as a typed unit made it before.
  - **Everywhere the same.** Run status, Corner check, the graph view and the Training tab write quantities this way too
    (four significant digits there), and the check's messages do: "osc_frequency_hz: lower 1.3 GHz here, 1.1 GHz saved".
    The page and the backend use one unit table (`units.py`, sent with `/api/schema`); `unit_text_check.mjs` checks that
    both write the same 34 cases alike. Copy and Ctrl+D fill still carry the stored numbers, which Excel reads.
- **Rows not saved in the task** (record 7.222, user: "In the parameter probe and spec windows, highlight the rows that
  are unsaved"). For a saved task (`real:<name>`), every row of Parameters, Probes and Specs that differs from what **Save
  task** stored is marked: a changed row is tinted amber with a bar at its start, the cells that changed a darker amber; a
  new row is tinted green with a green bar. The tick-box cell's tooltip says what changed and what the task holds ("Changed
  since the task was saved: Upper (saved: 1.5 um)") - also of a column not in view, such as Scale behind More columns; a
  changed cell's tooltip starts with its saved value ("Saved in the task: 1.5 um."). A tab holding such rows carries a dot,
  and its tooltip counts them and names the saved rows deleted here ("Not saved in the task: 3 changed, 1 new"); a tied
  row folded under its leader colours the leader's count. An error row keeps its red; its changed cells are still marked.
  The rows are compared by the backend as the check before every run compares them (the blocking issue "... differ from
  the saved task"), so a mark is exactly what Save task would store or Reload saved values would undo; they follow an
  edit half a second later, with the rest of validation. Typing the saved value back takes the mark away. After **Save
  task** - or a save from elsewhere that the page followed to its end - the rows are compared again even when they did not
  change, so the marks go (or come, when the other save left the rows here behind). A cell read from Virtuoso without a
  task, an ngspice task and a test task have no saved rows to compare with: nothing is marked.
- **The ID in view** (record 7.182, design advice). While a table scrolls sideways the tick box and the row's ID stay at
  the left and the other columns pass under them, a line marking the ID's edge while they do. The ID sits right beside the
  tick-box column, whose width the page measures, also when a narrower window changes it: a tie toggle widens it on
  Parameters, and on Probes and Specs it stays as narrow as the box. The editor tables draw their lines cell by cell
  (each cell its right and bottom line), so the tick box and the ID carry theirs along and cover what passes under them.
- **Find rows** (record 7.184, design advice 4). The box in the toolbar keeps in view only the rows whose text cells in view
  hold every word typed, not case-sensitive, folded or not: the ID, instance path, parameter, unit, leader and notes; a
  Probe's output name and expression; a spec's equation. Inside its right end, how many of the table's rows that is (3/16).
  The box shrinks with the window, from 170 px down to 80 px, so the toolbar stays on one line at 1366 px (record 7.185).
  Enter goes to the first of them, Esc clears the box, and each table keeps its own text. The keys, a pasted block, Ctrl+D, Ctrl+C, Copy and
  Delete selected work on the rows in view: a ticked row out of view stays ticked and is not deleted, and a chosen cell whose
  row went out of view is let go.
- **Add, Delete selected and the tick boxes** (branch record SIF-96, from the usability audit). **Add** puts the new row at
  the end as before, then scrolls it into view and chooses its ID with the text selected, so its name is typed at once; a
  new Maestro-output Probe gets its Output name chosen instead, since its Probe ID follows the name. A Find text the new row
  does not hold is cleared, and the line under the formula bar says so ("Find rows cleared to show the new row,
  parameter_67."). **Delete selected** deletes the same rows as before (the ticked ones; only those in view while Find holds
  text, and without a Find text also a ticked row since folded under its leader). The line under the formula bar now says
  what went: "Deleted 3 rows (wn_aux, ...), 1 of them folded under a leader. Undo takes them back." In amber, it adds the
  rows that were tied to a deleted leader and now follow nothing, and the Specs whose equation uses a deleted Probe, which
  are on a tab not in view. The focus goes to the tick box of the row now in the first deleted row's place, or to Add when
  no row is left in view. The tick-box header holds a box, **Tick every row in view**: it ticks or unticks every row in
  view, is half ticked while only some are, and leaves a row that a fold or Find hides as it was. **Shift+click** on a
  row's box gives every row in view from the box clicked last the same state. Nothing here saves, runs or writes to
  Virtuoso; Undo takes an Add or a Delete back as before.
- **Fill down** (Ctrl+D, record 7.184). In a ticked row, with more rows ticked, the column takes the value of the topmost
  ticked row in view in every ticked row in view; in any other row the cell takes the value of the row above in view. One
  Undo step. A cell that follows another field, or that its leader decides, is kept; an ID is not filled, since each row
  needs its own. The line under the formula bar says what was filled.
- **Copy out** (Ctrl+C and the Copy button, record 7.184). In a ticked row, Ctrl+C copies the ticked rows in view - every
  column in view, a header line first - as tab-separated lines that Excel takes; in any other row, the cell alone. With
  text chosen inside the cell the browser copies that text, as ever. The Copy button takes the ticked rows in view, or
  every row in view. Numbers are copied as stored (4.5e-7, which Excel reads), a limit as its sign (`>=`, `<=`,
  `interval`). Pasted back, a first line that names the columns it lands on is skipped, so a block can go to Excel and
  come back.
- **One write path** (record 7.184). A typed cell, a pasted block and a fill follow the same rules: a Maestro output's
  Probe ID follows its output name, and the spec equations follow the ID (a pasted name used to leave the ID behind); a
  spec whose equation becomes one Probe takes its unit while it has no limits; an untouched scale follows its limits; a
  limit written without its objective keeps the objective only where the two still pair (≥ with "higher is better", ≤
  with "lower is better", an interval with either), and otherwise has none.
- **Headers in plain words** (record 7.188). The editor tables' headers read ID, Instance, Parameter, Unit, Optimized, Lower,
  Upper, Tied to and Notes; Probe ID, Analysis, Output name and Expression; Spec ID, Equation, Limit, Hard and the rest. The
  field names - what the task files, Export JSON and the agent use - stay in each header's tooltip, in the formula bar's
  format note and on the help line a header press opens. A copied block's header line reads as the headers do, and a paste
  back skips a header line of either kind.
- **Ctrl+Z and Ctrl+Y** (record 7.188). In a cell, Ctrl+Z and Ctrl+Y (or Ctrl+Shift+Z) are the toolbar's Undo and Redo, as
  in a spreadsheet: a cell's typing is one Undo step, so the whole entry goes back at once. The formula bar keeps the
  browser's own undo of its text.
- **Undo from anywhere, and what it took back** (branch record SIF-97, from the usability audit). The keys are the page's
  Undo and Redo wherever the focus is in the main window - a tab's button, Add, a Run configuration list, the page itself -
  not only in a cell: after an Import's or Matched devices' Apply, a tab press or a Delete that left no row in view they did
  nothing. A box that takes typing (Find rows, the formula bar, a number or a name box) keeps the browser's own undo of its
  text, a cell handles the keys first as before, and a dialog open over the page (the graph view) is left be. Undo is
  page-wide and used to say nothing; now the line under the formula bar names what an Undo or Redo changed, from whichever
  button, key or window it came: "Undo: Specs inl1 (Lower)." - the tab, the row's ID and, when one row changed in up to
  three fields, their headers - or "Undo: Parameters w3 added.", "Redo: run settings." (the other sections by the import
  confirmation's words). When it changed rows of a tab not in view, the line offers **Show Specs** (that tab's name); the
  tab is not switched by itself. Nothing here saves, runs or writes to Virtuoso: the keys do what the toolbar's Undo and
  Redo did.

Browser checks: `frontend/scripts/sheet_check.mjs`, `frontend/scripts/find_fill_copy_check.mjs`.

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
structures in plain sentences (a kind found three times or more in one line, "8 cross-coupled pairs, each gate on the other's
drain: ...", each sentence in its tooltip; branch record SIF-73) and one line per row it would change. It takes 40 % of the
editors' card at most and leaves the table its heading and about three rows where the card has room for both (on a card
under about 410 px, as when the bottom panel is opened again under the open box, the box keeps 72 px, its heading and a
line, and scrolls, and the table keeps its heading and about one row); on a wide page whose bottom panel is open, an
answer that leaves the table under about four rows folds the panel to its tab line, as entering a cell does (record 7.372).
**Review...** shows the diff, the count of
searched rows before and after, and any validation error; only **Apply** changes the rows, and **Undo** in
the toolbar takes it back. **Matched devices...** stays enabled while the box is open; each press reads the current
rows again and replaces the previous results and unapplied review. The separate **Find / Find again** button is
removed. An answer about rows that changed since directs you to the toolbar button. The **Close** control is an ×
icon with a tooltip and an accessible label; it dismisses the box without changing rows. Nothing is simulated or stored.

Where it applies: a cell read from Virtuoso (the ties go into the task at **Save task**), a task you saved (save it again
afterwards: a task runs with the rows it was saved with), an ngspice task (its rows start one per size, so the pair and the
load of the example OTA go from 7 to 5 independent variables), the MOCK task. A **verified** built-in task
(there is none left since 2026-09-30) fixed its rows: the structures were listed for information and nothing offered.
The circuit panel's summary carries the same sentences: `circuit_summary` holds them as `structures`.

Backend `structures.py` (`recognize`, `plan_ties`, `apply_ties`), route `POST /api/parameters/matched` (`{config, apply}`;
local files only). Tests: `tests/workbench/test_wb_matched_devices.py` (the circuits of record, hand-made netlists with
non-M names and unlabelled rails, a folded cascode, a 2:1 bias mirror, kept and foreign ties, the route). Browser check:
`frontend/scripts/matched_devices_check.mjs` (hermetic, answered with `frontend/scripts/fixtures/matched_devices.json`
= the real route's answers for its seed).

### Spectre netlist import: removed

The Tasks window lists the registered tasks; a Virtuoso cell is read in the Virtuoso cell window, opened by **New task:
From a Virtuoso cell...** in the Tasks window (record 7.362; from 2026-09-23 a **Virtuoso cell...** button in the Project
column, by user request; until then a **Circuit source** list offered both). A third source,
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
run's `artifact_manifest.json` says why; `parameters.csv` always holds the values.

### An ngspice netlist as a task: the ngspice window (added 2026-09-23, user request)

The second way to a new task, **From an ngspice netlist...** in the Tasks window (record 7.362; until then the Project
column's **ngspice netlist...** button), opens a window that takes a SPICE deck - pasted into its text box,
or loaded from a file on the backend machine (a path under the allowed input roots, `--allow-input-root`; a Windows
path is converted for the WSL backend; **Example** loads `examples/circuits/ngspice_ota5_level1.cir`, a
five-transistor OTA on textbook level-1 models with no PDK at all) - and saves it as the task `ngspice:<name>`.
The page then follows that task: Parameters and Probes show its rows, Specs is yours to fill; **ngspice netlist...** on the
editors' tab line opens its deck again. Saving the
same name again stores the next revision (the deck before is kept as `history/r<N>.cir`); runs made before keep
their own copy of the deck in `input_snapshot/netlist.cir`, and a changed deck is a changed task. **Check** reads
the deck on the backend without keeping it and says what it found: elements by kind, the values a run can vary,
the results it measures (with a unit guessed from the result's name or its expression: `gain_db`, `ugf_hz`,
`v(out)` -> V, `i(vdd)` -> A - edit the Probes row when the guess is wrong), the analyses, includes, diagnostics
and, in plain words, what would stop a run. **Delete task** (in the Tasks window, beside the current task name,
for the task the page follows) takes
it out of the list; its folder is kept aside on the backend machine. Nothing in the window runs a simulation.

**Which way to a new task the Tasks window offers follows the connection in use** (user request 2026-09-23): with a
Virtuoso connection chosen (the "Connection" button) **From a Virtuoso cell...** only, with an ngspice connection
**From an ngspice netlist...** only; with no connection chosen, or one of a kind the page does not know, both. The family is
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
  over parameters (a whitelist evaluator with ngspice's arithmetic functions, never `eval`), and `.end`. A
  node's name is read without regard to case, as ngspice reads it: `IN` and `in` are one net, under the spelling
  the deck gives first (record 7.322; each spelling used to be a net of its own).
* **Results**: `.meas` statements, or in a `.control` block `meas ...`, `let x = ...` + `print x`. Their names are the
  Probes rows (`source_name`); a run reads the `name = value` lines ngspice prints (`.meas` names come back in
  lowercase; a failed measurement is missing, never a number). ngspice has no `.meas op`: read operating-point
  values in a control block (`op`, `let`, `print`). The example does exactly that, plus `set units=degrees` so
  that `vp()` gives degrees.
* **What the network sees**: the standard vocabulary (nmos, pmos, resistor, capacitor, inductor, vsource,
  isource, unknown). The kind of a MOS comes from its `.model` line - in the deck or in the files it includes,
  which are read for their `.model` and `.subckt` lines only (never copied, shown or sent anywhere; up to 48 MB
  of them). A diode, a bipolar, a behavioural source, or an instance of a subcircuit the deck does not define (a
  PDK cell such as `my_nfet`) is `unknown`, a warning, not an error: ngspice simulates it either
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
deck. Each attempt keeps its own copy of the exported deck in its result folder. On this machine, files written there
by `write` or `wrdata` stay with its logs and follow the raw-output retention policy; a retry has a fresh folder.
Previously those files landed in the export folder and the default cleanup deleted even the best design's raw files
(record 7.323). Outcomes: the results it prints are the evaluation; a solver failure (timestep too small, singular matrix,
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

**New task: From a Virtuoso cell...** in the Tasks window (record 7.362; until then one short button, **Virtuoso
cell...**, in the Project column) opens the **Virtuoso window**, a browser window of its own like the connection window (needs a connection profile and a link
that is up; allow pop-ups if the browser blocks it). There is nothing to press: opening the window lists
the libraries, choosing a library lists its cells, choosing a cell reads its schematic. Each step is a
gated, read-only, zero-cost bridge call and waits for the one before it. **Refresh** repeats the chain, for
example after the link came up or the design changed in Virtuoso. A library chosen in the window makes
the page follow the Virtuoso cell instead of the task: the task's place on the tab line then names the cell, and
**Virtuoso cell...** on the tab line opens the window again. Choosing a task makes the page follow the task again, and the
window then starts from a blank library. Closing the window loses nothing.

The column and the window keep their explanations folded: a line with a small triangle ("Labels: class
..., PDK ..." - the column's circuit class and PDK id boxes are one closed line naming their
values -, "Why: it is not a task yet", "What the check compares", "2 notes on this circuit", ...)
opens on a click. Headlines, warnings and buttons are always in view.

The **DUT hierarchy / subcircuit** input and its DUT summary value were removed from this line on
2026-10-07 (record 7.245): saved Virtuoso tasks already determine the DUT and do not use this input.
Existing configurations retain their hierarchy data; the circuit's hierarchy viewer remains available.
**Circuit class** uses the same themed dropdown as the other controls; **Custom...** opens a text box
for a class outside the suggested list. A saved custom class remains editable (record 7.245).

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
  read-only, some seconds). It is off until a **Testbench cell** is chosen, and its tooltip says why (branch record
  SIF-88): the first read declares the cell, which needs the testbench, and the backend refuses it before any export.
  It used to ask the copy question first and then show that refusal; **Read the cell again** on a cell read before the
  question now says it in the window, with nothing asked or sent. The first read of a cell ASKS whether it is a copy you made (the workbench makes
  no copy of its own since 2026-09-23 - see "The cell the task flow works in" below): Cancel reads nothing,
  OK reads it and makes it the cell the task flow works in. Virtuoso exports the netlist of the testbench
  cell and the device sizes are read. The cell's PDK is read in the same press (since 2026-09-27; see "The
  components the network knows" below): a line under the buttons says what came of it, and the PDK's component
  list can then be chosen in the RL model window (New model, the template's Components). The export is kept under
  `configs/local/workbench/native_cells/<library>/<cell>/`, and the cell then loads from it without
  contacting Virtuoso: you can look at it, fill the three editors (the centre tabs, in this order:
  **Parameters** = what may vary, **Probes** = what is measured and how, **Specs** = equations over
  those probes and the limits they must meet; **Read setup** takes what the cell's Maestro test already holds) and
  save it with **Save task**, which writes the rows into that cell's Maestro view. (Until 2026-10-06 "Ask the agent
  to set up" had the Agent tab's agent propose them; record 7.226.) That next step stands in view under the draft's
  headline (branch record SIF-88; it was folded under "What you can do with it now"). A read brings no Parameters rows,
  so an empty Parameters table says "No rows yet: add one row per size the optimizer may change (Add, the + above)" and,
  for a cell, that its present sizes are under Hierarchy, Instances and parameters, in the Virtuoso window - not while
  no task or cell is chosen. Device types this project has not verified (for example the MIM invented model) are shown
  with unnamed pins. Such a cell still cannot run: Start stays disabled (`circuit_profile_missing`) until
  it is saved as a task.
* **Save task** (at the right end of the editors' tab line since 2026-09-22; the note points there) replaced the
  former **Create profile** form on 2026-09-22 - see "Saving a task" below. A Parameters row is accepted only
  when a real run can write it, for instances directly inside the cell: widths of single-finger, m = 1
  transistors keep the verified width writer, and since 2026-09-22 (status record 7.66) any other value the
  PDK's property form lets a user type goes to the form writer (see "What a real run writes" below). A range
  must contain the present value and is snapped onto the grid the PDK keeps (the editor then shows it exactly
  as registered); anything else is refused with the reason. The cell
  becomes the task `real:<name>` in the Tasks window (files in
  `configs/local/workbench/profiles/<name>/`) and stops being browse-only.
  A cell that already has a registered task - one saved from it, or one of the verified built-in
  circuits (`real:gpdk045_ldo` for `ldo_m6_v1`, ...; the library is the one the Virtuoso connection
  states) - shows "This cell already has a registered task: `real:<name>`" and says to choose it under
  in the Tasks window (the task's name on the editors' tab line; its **Open** button went on 2026-09-29, 7.109); change it there
  (Save as); another task gets its own copy through that save, or from another copy made in Virtuoso and read in
  the window. A built-in circuit gets no second task.
  **Delete task** (in the Tasks window beside the current task name since 7.260; asks once more; was: Delete profile):
  the task leaves the list, its name is free again and the cell is free for the next Save task. The page then
  follows the task's cell - unless something else was chosen while the deletion ran: then the page stays as it
  is and a line says the task was deleted (record 7.322).
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
  2. **Save as** creates the task and starts its baseline automatically (record 7.248): the saved starting
     design, one nominal evaluation, one simulator launch maximum, one lane, seed 0, no retries, no training or
     calibration. Its configuration comes from the saved task, independently of the page's run controls. The
     header follows that worker. A valid completed Virtuoso baseline becomes the task's reference automatically.
     A failed or blocked baseline leaves the task saved, reports why and offers **Retry baseline** in the Project
     column. The launch is recorded in the task's `baseline_launch.json` so reloads retain its status.
  3. **Calibration** in the header is optional: 64 random designs, no baseline or episode-reset simulations.
     Its proposals stay unapplied until **Apply calibration** or **Apply and save**. Existing combined runs remain
     readable; scripts can still request the historical combined `baseline_only` + `calibration_designs` operation.

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
Whether a run is working on the connection (the third condition) is asked only for a result that could be reused, and
one answer serves 3 s (record 7.279): the look reads the run list and up to 20 status files on the D: drive, 1-2.4 s,
and it was asked first, at every gate - about ten times in one Save task.

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
Connect SSH, Test connection or Full test (Spectre, license) - runs a check as before. `serve` does not
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
Closing the window loses nothing, and the button opens it again. Since record 7.182 the button is the last cell of the
header's title block (user: "move the conection button to the header"), in view whatever the columns show; the left
column has none.

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

### Multiple Virtuoso sessions in one connection (2026-10-14, record 7.345)

A connection can show several Virtuoso sessions together. Select **lab** once: **Virtuoso 1** and **Virtuoso 2**
each have their own Connect SSH, CIW commands, Test connection, Spectre/license check, details and result. There is
no session selector. The window widens for the two cards; smaller windows stack them. A slow or failed action on one
card does not disable the other card or replace its result. Each Copy button copies only that session's commands,
including `setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")` before its own setup file is loaded.

The connection file associates an existing secondary entry with its main connection using `"session_group": "lab"`.
The grouped entries must name the same kind, bridge env file, bridge package location, library and model file, and
different bridge profiles. The public profile response adds `groups` with ordered `session_profile_ids`; its original
`profiles` list is retained. Invalid, missing or cyclic group links remain individually visible. No host, credential,
model contents or circuit bindings are included in the grouping response.

The current `lab2` and `asz2` entries are grouped under `lab` and `asz`. Their identifiers remain valid for recorded
configurations and queues. The page-open test still checks only the configured session once; sibling cards read cached
status. Opening the panel starts no tunnel and performs no extra probe.

**The work goes to whichever session is free** (2026-10-15, record 7.351; user: "send it to whichever is free"). The page
names the connection (`lab`); a run (Start, Baseline simulation, Calibration, Continue), a Check now or a Save task goes
to one of its sessions, chosen by the backend (`session_routing`) - see "Two Virtuoso sessions carry a run each" below.
The run's message, the run's record and Check now say which session and why. A configuration that names one session by
its own name (`lab2`, as queues do) keeps exactly that session: the list then shows it as its own entry, "lab2 - Virtuoso
2 only", the button says "lab2 (Virtuoso 2 only)" and a warning offers "lab" instead. The button's badge counts the
sessions whose last test passed ("1 of 2 OK"); with none, it shows the connection's own session's state. Each card names
its session (`Virtuoso 2 (session lab2)`). A cached read never makes a test or Connect still on its way stale, and never puts an
older result back over a newer one (`checked_utc`); a failed Connect line goes once a later test passes.

### Folders: where the connection keeps its files (2026-10-03, record 7.168)

User: "I realized the project might be used by others. Add directory settings for necessary files in the connection
module with current setting as default". **Folders...** sits at the foot of the connection window; it is there even
when no connection is set up. It lists five folders, each filled in with the value in use. Nothing is kept until
**Save folders** is pressed. **Use defaults** fills the defaults in and **Undo changes** puts back the values in use;
neither sends anything. What is typed and not saved outlives the window's close and the section's fold (branch record
SIF-87): opened again, the section reads the values in use and lays the typing over them, with the line "Your changes
from before are kept, not saved yet. Undo changes drops them."; Save folders and Undo changes clear it.

Since record 7.170 (user: "separate the folders section with other section with similar style", and "if comments can be
seen floating over name then delete the comment text underneath it") Folders is a section of its own under the steps,
headed like them: the same rule above it and a folder sign where a step has its number, since setting the folders is no
step of connecting. Each folder's comment - what it holds and when a change takes effect - is the tooltip of its name,
with no text under it; under a folder only what is the case now shows: that an environment variable of the backend
decides it, or its default while the typed value differs. The pop-up windows are `about:blank` documents in quirks mode,
where a line holding only a picture ignores the line height: a zero-width character before the sign keeps its circle
where the numbered ones sit.

| Folder | Default (the value before 7.168) | Where | What GATOR keeps there | A change takes effect at |
|---|---|---|---|---|
| Adapter state | `~/.local/state/gator/bridge-state` | this machine | the session lock that runs, corner checks and Save task take, and the crash journal of every write to a cell (7.167) | the next run, corner check or Save task |
| Simulator scratch | `/tmp/gator-work` | this machine | export packages and Spectre job folders of a run whose output folder is on a slow mount (7.149) | the next run |
| virtuoso-bridge checkout | `~/virtuoso-bridge-lite` | this machine | where "Add a connection" looks for the bridge's `.venv` when the backend cannot import the bridge; the agent diagnostics look for the bridge's skills there | the next "Add a connection" |
| Initial-condition files | `~/.gator/ic` | simulator host | the file of a Maestro test's initial conditions that saving a task writes | the next task save |
| Maestro netlists | `/tmp/gator_maestro_netlist` | simulator host | the netlist Maestro writes for a saved task, which GATOR then downloads | the next task save |

The values are stored as a `"directories"` block of `bridge_connection.json`, only those that differ from the defaults:

```json
{"active": "lab", "profiles": {"lab": {"kind": "virtuoso_ssh", "...": "..."}},
 "directories": {"maestro_netlist": "~/gator/netlists", "local_scratch": "/scratch/gator-work"}}
```

* `~` on this machine is the backend user's home. On the simulator host it is the home of the user Virtuoso runs as,
  read from Virtuoso when the folder is used.
* Precedence: an environment variable, then the file, then the default. Only Adapter state has a variable,
  `GATOR_BRIDGE_STATE_DIR`, which the tests use. A folder the variable decides is greyed out, shows the variable's
  name, and cannot be saved (409 `folder_busy`).
* Every changed folder is checked before anything is written. Nothing is stored unless all pass; a refusal (422
  `invalid_folder`) names the folder. The checks:
  - a full path (`/` or `~/`) on one line, with no `..`, and neither `/` nor the home folder itself;
  - on the simulator host, only letters, digits and `_ . + -`, because the value goes into SKILL and shell commands;
  - Adapter state and Simulator scratch are made when missing and written once;
  - the scratch must not be on a slow mount (9p, drvfs, ...);
  - the bridge checkout must exist.
* Adapter state does not move while its session lock is held, in the old or the new folder (409 `folder_busy`). Every
  GATOR process must use the same folder. A process started with other settings (`GATOR_WORKBENCH_SETTINGS_DIR`) reads
  its own connection file, so give it the same block or set the variable.
* How the file is written:
  - the previous file is kept as `bridge_connection.json.before-<UTC>-folders`;
  - a file that cannot be read is never replaced, and a missing one is made with no connection in it;
  - connections are never changed here;
  - names this backend does not know are kept;
  - a value that fails its check is not used: the default applies, the window says why, and the next save drops it.
* Initial-condition files already registered in a Maestro test are recognized in the configured folder and in the
  default one, so tests saved before a change still work. The next Save task with conditions writes the file into the
  new folder; old files stay on the host.
* Not set here:
  - Spectre's job folders on the simulator host: the bridge's own `VB_REMOTE_SCRATCH_ROOT` in the bridge env file,
    `/tmp` when unset;
  - the settings folder, which holds the connection file: `GATOR_WORKBENCH_SETTINGS_DIR`;
  - the output folder: the output panel.
* This is the one connection route that takes paths. They are checked as above, and a host or a command cannot be
  given here.

Routes:
- `GET /api/connection/directories`: each folder's default, the value in use, where it comes from, and why a saved
  value is not used;
- `PUT /api/connection/directories` with `{"values": {folder: path or null}}` (null = the default).

A server started before 7.168 answers 404; the window then asks for a restart.

Code: `directories.py` (the folders, reading, checks), `bridge_connect.save_directories`, and where the folders are used:
`paths.bridge_state_dir`, `layout.local_scratch`, `bridge_connect.detect_setup`,
and `bridge_setup` (`_remote_path`, `_ic_folders`, `maestro_netlist`). The window is
`frontend/src/panels/ConnectionFolders.tsx`. Tests: `tests/workbench/test_wb_directories.py`; browser check
`connection_panel_check.mjs` ("Folders").

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
    waveforms/  logs/{events,errors,timings}.jsonl  exports/  control/  work/
```

Mapping to the recommended layout of the specification:

* `input_snapshot/dut.scs` + `testbench.scs` -> **`netlist.scs` + `hierarchy.json`** when the source is
  one combined netlist. No empty placeholder files are created; the manifest says so.
* `checkpoints/<id>/replay_buffer/...` -> the replay snapshot is **embedded in `training_state.pt`**
  (written by the existing `SACLearner.save`), so weights, replay and counters can never come from
  different moments. `replay_buffer/manifest.json` lists its members so it can be checked against
  the complete `transitions` archive without unpickling.
* `training_state.pt` is **compressed** (record 7.284): its zip entries are deflated, each byte-identical
  to what `torch.save` wrote, and `torch.load` reads it as before - so every reader, an older checkout
  and a queue's frozen runtime included, opens it unchanged. The replay inside is plain pickle (each
  stored step carries its circuit graph twice) and shrinks about three times (41.6 MB -> 14.4 MB at
  level 3). The package writes the file on the local disk, where its own read-back check runs; only the
  compressed copy, checked entry by entry against it, goes to the run folder (3.6-3.9 s per 42 MB save
  point against 4.1-5.7 s, 14.4 MB written to the D: drive instead of 42.3 MB). `metadata.json` holds the
  compressed file's checksum. Save points written before are compressed by
  `gator-workbench compress-save-points [--root DIR] [--exclude PATTERN] [--apply]` (a dry run without
  `--apply`): it checks each original against its recorded checksum (a mismatch is reported, never
  touched), compares every entry after compressing, keeps the original's size and checksum under
  `compressed_from` in `metadata.json`, leaves alone a run a worker holds, and completes a pass stopped
  between its two writes (the original it left still verifies). The run's `artifact_manifest.json` it
  refreshes once per run, after all of the run's save points and never from a worker (record 7.286): the
  rows of the two files it rewrites, `training_state.pt` (size) and `metadata.json` (size and checksum),
  and the total; a later pass repairs rows an earlier one left stale, and a manifest that is right is not
  rewritten.
* A part file belongs to the dataset only if `data/_journal/flushes.jsonl` lists it.
* The default `best_and_failures` raw-output policy follows the overall selected best design. An improvement only
  within the infeasible or nominal-feasible class cannot replace the output of a better class; the class's design
  record still updates. A new overall best replaces the preceding best's raw output (record 7.321).
* `cumulative_cost.csv` counts a run once across target costs and source provenance chains. An earlier fine-tuning
  target used as the next model's source stays in the target total; only additional source runs enter the source
  total. The per-run `source_pretraining_cost` still describes that run's entire source chain. Exporter v2 records
  this correction; unknown source costs remain non-computable (record 7.321).
* Exporter v3 records the optimizer in every research table (record 7.325). Budget and transfer groups and
  cumulative cost streams keep SAC and Bayesian runs separate even when their research labels match. Paired
  rows name both optimizers; a mismatch is an uncontrolled difference. Historical manifests without
  `architecture.optimizer` mean SAC. Re-export an experiment to rebuild its derived CSVs.
* When a writer reopens a journal after a crash, it truncates only the incomplete final line before appending.
  Complete corrupt records stop recovery with a persistence error; they never silently hide later records.
  A healthy journal needs only its final byte checked (record 7.174).
* A run continued after a crash starts from its last save point, and what it committed after that save point is
  in its tables: the budget is brought up to it, and (record 7.322) so are the run's own counts - failures in a
  row, valid and passing designs, the first passing design with the numbers of that moment, the episode numbers.
  Until then the save point's older counts stood: a row of failures that a success had ended still counted, so
  one more failure stopped the run; a first passing design found after the save point was forgotten. The
  `resumed` event says what was counted (`counters_after_checkpoint`).

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
it). It opens at the run the tabs show (branch record SIF-101; it opened at the top of the list, the shown run - with the
user's 600 runs often hundreds of rows down - only marked): once the list is read, that run's row is brought to the
middle when it is out of view. Nothing else changes: no Details open, the folder and the filter stay. When the folder or
the filter hide it, **Go to the shown run** stands beside the filter and shows it as a link does (below). The window
lists every run under the output folder, newest first, one row per run:

| Column | What it says |
|---|---|
| Started | When the run was created. All times are the local time of this computer. |
| Finished | When the run came to rest: completed, stopped, failed. A paused run shows the time with "(paused)"; a run that is working reads "still running"; a run whose worker died wrote no end, so it reads "last seen ..." (its last sign of life). |
| Duration | How long the run was actually WORKING. The time it sat paused is not counted (the cell's tooltip and the details name it); a working run reads "... so far". |
| State | The state, and under it why the run stopped (`budget_exhausted`, `user_pause`, ...). |
| Task, Mode, Seed, Experiment | What the run was. |
| Started from | Where the run's model came from (record 7.264): "template GT" for a new model made from an encoder's template; "ota7t (2) @ 420" for a run that loaded a saved model - its name and the save point's evaluations, a link to the run that saved it ("(gone)" when that run is not under the output folder); "offline: 22 runs" for a model trained offline on recorded runs; "-" for a Baseline simulation or a calibration, which load none. |
| Saved model | The name of the RL model the run saves (record 7.225; "Model" until record 7.264); empty for a Baseline simulation or an LLM-only run. |
| Evaluations | Candidate designs simulated, of the budget: `25 / 60`. |
| First feasible | The number of evaluations spent when the first design met every target; "none" if no design has. |
| Data | MOCK (synthetic backend, not a circuit result) or real. |
| Can continue | yes (full saved state), model only (usable for fine_tune / frozen), no. "no" also when the run folder no longer holds the save point its summary names - a copy made without its save points, deleted ones (record 7.215); Details says so under "Saved state". "model only" also for a full save point written by an older version of the optimizer code, which only that version can continue (record 7.221); Details says so too. |

* **A double click on a row** is **Load run** (record 7.267; plan [frontend run workflow](plan-frontend-run-workflow.md),
  "Load run"): the run's task comes into the editors, the model it ended with becomes the next run's model, and the
  bottom tabs show the run - below. Where Load run is not offered, the double click only shows the run. The shown run's
  row is marked (blue, with a bar at its left edge), and the window closes once the run is chosen (record 7.291): after
  Show results and Continue... at once, after Load run and New run like this once they went through - Cancel at the edits
  question or a model that cannot be read leaves it open, with the reason on the page and, in the same words, in the
  window (branch record SIF-84): beside the run's actions while its Details are open, else where the window's count of
  runs stands (a double click). The next press, a Details toggle, Refresh list or closing the window lets that line go.
  **Clear**, **Details**, the folders and the links inside the window keep it open. **Clear** empties the tabs again. Nothing
  here stops, starts or deletes anything: the header's Start / Pause / Abort keep acting on their own run.
* **The actions**, at the top of a run's Details (record 7.267):
  - **Load run** (also the double click) sets three things together, as ONE Undo step for the draft:
    - **its task**, through the Tasks window's task load: the saved rows as they are now, never the run's archive, and
      unsaved edits are asked about first - in the Runs window, where the press was (branch record SIF-84). When it is
      already the page's task, the editors stay as they are, edits included.
    - **the model it ended with**, pinned as "Use this save point" pins one, with its network and component list:
      - a run that trained, its newest save point;
      - an Evaluate-only run, the save point it evaluated (its weights never changed), else its own;
      - a run without a save point (a baseline, a run stopped before its first save), the save point it started from.
      - With none of these, the model stays as it was, and the message says so. The Mode stays Fine-tune or Evaluate
        only; New model becomes Fine-tune.
    - **its results** in the bottom tabs. The task-run link below gives way: the loaded run stays shown, not the task's
      newest.

    All or nothing: Cancel on the edits question, or a task that cannot be read, changes nothing, and the message says
    why. So does a model that cannot be read (record 7.270, Astra's review of 2026-10-07): only a save point that is not
    there (or not under the allowed output folders) makes Load run go on to the next one - a passing failure (the server
    busy, a timeout) stops it, where it used to load the model the run started from and say it had worked. And only the
    newest Load run or New run like this lands: one still on its way when another is pressed, or when a task is chosen
    elsewhere, changes nothing. The message names what came in - "Loaded run ota7t 10-06 14:02: task real:ota7t, Fine-tune from ota7t (2),
    save point at 420 evaluations. Undo takes it back." - and says when the task was saved again since the run (the RL model window's check then
    says whether the model still fits).
  - **Show results**: only the bottom tabs show the run, as the double click did until record 7.267.
  - **Continue...** (a paused, stopped, interrupted or completed run with a full save point; branch record SIF-90): Run
    status shows the run with its budget form open, once - a later return to the Run status tab does not open it again;
    the run goes on in its own folder from there (record 7.261). A failed or cancelled run, or one whose save point is
    model only, gets no Continue...: "Continue... is not offered: a failed run cannot be continued. Load run brings its
    model into the next run (Fine-tune or Evaluate only)." stands beside the actions (without the Load run sentence when
    Load run is off). Until SIF-90 the press closed the window on a greyed-out budget form. "Can continue" is unchanged.
  - **New run like this**: the next run repeats the run - its task (through the same task load), its Mode, the save
    point it started from (from its lineage, pinned: never the "latest" its configuration may have recorded), its
    network, training values, reward, conditions, budget, seed, limits and the name of the model it saves (numbered at
    the start when that name is taken). Read from the run's own `effective_config.json`; one Undo step; the shown run
    stays. The optimizer is the run's own as well (record 7.322): a run searched by Bayesian optimization repeats as
    one and the message says so, a SAC run as a SAC run - whatever the draft was. The page has no control for the
    optimizer: a Bayesian draft stays one until Undo or until a SAC run is repeated.
  - Load run and New run like this need the run's task registered now: for a run of a deleted task, or one that names
    none, they are off and the reason stands beside them. Show results still works, and its model can still be used
    from the RL model window.
* **Details** open with the run's **Relationships** (record 7.264; plan, "Runs window"), from what each run's manifest
  recorded - never from names or folder paths:
  - **Task**: the task and its definition hash, a link that opens the Tasks window at it; "saved again since this run"
    when the task was saved after the run began, "no longer registered" when it is gone.
  - **Started from**: the run and save point it loaded (a link), the template of a new model, or the recorded runs an
    offline model was trained on (each a link, folded).
  - **Saved model**: its name and latest save point. **Runs that started from its model**: links.
  - **History**, folded: the chain of models behind the run, oldest first, from its template or offline sources; a
    parent that is not under the output folder is said, never left out.
  - Every run named is a link that shows it in this window: selected, scrolled to, its Details open. The folder, the
    filter, the one task and the ticks stay when they show the run (branch record SIF-101; a link cleared them every
    time, and nothing brought them back); when they hide it, every folder and no filter are set, and **Back to <folder>
    · "<filter>"** beside the filter brings them back. Following a link
    chooses nothing on the page. The Tasks window and the run brief open this window the same way (at a run, or with one
    task's runs only).
* **Details** also open everything else the run recorded, under its row: run folder (click to copy) and ids, created /
  worker began / came to rest, working time, time paused, summed simulator job time, stop reason and error, budget
  and Spectre launches, learner updates, first feasibility, best design with its variables, the model it loaded and
  its last save, what can be restored, parallel simulations, connection, bytes written - and one line per
  **segment** (each Start or Resume: when it began and ended, how it ended, how long it worked).
* A press on a column title sorts by it (again: the other way; rows without a value stay last). The filter box
  narrows the list by any word of a row: task, mode, state, `mock` / `real`, a date.
* **Folders** (record 7.263; plan [frontend run workflow](plan-frontend-run-workflow.md), build step 2), as in the
  Tasks window: **All runs**, **Unfiled** and named folders with counts on the left, the same New folder, Rename and
  Delete folder icons. Tick runs (or the header box for every run shown), then **Move to...**; in All runs a run's folder
  is named under its date. A folder filters the table, and the filter and sorting work inside it. Organization only:
  no run is moved, renamed or deleted on disk, and deleting a folder sends its runs back to Unfiled. Run folders are
  stored by run folder in `run_folders.json`: an assignment of a run that is gone stays in the file and is not counted.
  API: `GET/POST /api/run-folders`, `PUT /api/run-folders/assign` (`run_dirs` - each must be a run under the allowed
  output roots), `PATCH/DELETE /api/run-folders/{folder_id}`; the saved models' folders the same under
  `/api/model-folders`, used by the RL model window's saved models table (record 7.265).
* **Nothing in the window updates by itself.** The list is read when the button is pressed and by **Refresh list**
  (the window says when it was read); a run's details are read when they are opened. A working run therefore shows
  its state and duration as of that time. A link from another window (the Tasks window, the run brief, a model's
  Relationships) only opens this window at its run: the list is read again only when the window was closed or its list
  is more than a minute old (record 7.275).
* **The backend keeps what it read of each run** (record 7.274): a run folder is read again when it changed - every file
  the list reads is written whole, a temporary file renamed over the old one, which changes its folder - when its save
  points changed (a new one arrives complete, then `latest.json` is replaced); the lock of a run whose status says it
  works is looked at every time. Nothing expires by age any more (record 7.279: every entry expired together after ten
  minutes, and the saved models took 12.9 s again). **Refresh list** reads every run folder anew
  (`GET /api/runs?fresh=true`), for a file another tool edited in place. The runs are read 16 at a time (record 7.279:
  file operations on the D: drive overlap well), the first read after a backend start too. The backend answers several
  requests at once, so the cache is touched under a lock (record 7.278).
* The times come from the run's own files (`run_manifest.json` segments, `status.json`); `GET /api/runs` carries them
  as `started_utc`, `ended_utc`, `last_seen_utc`, `active_seconds`, `paused_seconds`, `segments`. A workbench server
  started before this was added lists runs without them: the window says so and asks for a restart of `serve`.
* **Details** also names the run's **Registered task** (`real:<name>`, `ngspice:<name>`), and the filter box finds a
  task's runs by that name. A Baseline simulation is one of its task's runs, although its folder reads `<name>.baseline`.

**The run that follows the task** (2026-10-05, record 7.212, user: "after selecting specific task, it automatically load
the most recent corresponding run of the registered task. If there is no recent run, then leave run selection and run
status default blank unless you choose other runs"):

* When the page's registered task changes, the run list is read again and the bottom tabs show that task's **newest run**
  (by its start), whatever state it is in; a task without a run shows **none** ("No run selected"). The task changes when
  it is chosen under **Task**, when **Undo** or **Redo** takes that choice back or forward, and when a first **Save task**
  makes the page follow the new task. Reload saved values keeps the task, so it keeps the run shown too.
* Opening the page follows nothing: it shows the run it showed before. The page keeps the run shown in the browser
  together with the header's run of that moment; when the header holds another run by the next opening (a run started in
  another tab of the page), the page opens on the header's run, as it always did. A browser that never kept one opens on
  the header's run.
* A run chosen in the run window always counts: also when it is chosen while the list is still being read for a task,
  and it stays until another task is chosen. **Load run** changes the task WITH its run: the loaded run stays shown, not
  the task's newest; one Undo takes the task back, and the bottom tabs follow it again (record 7.267). A list that cannot
  be read, a server older than the page (its runs carry no task; restart `serve`), and a page that leaves its tasks for a
  Virtuoso cell all leave the run shown as it is.
* Only the bottom tabs follow. The header's Start / Pause / Abort keep acting on their own run: a live run of another task
  keeps its Pause and Abort, and choosing its task shows it again.
* `GET /api/runs` carries each run's task as `task_key`, read from `run_manifest.json` (`circuit.task_key`, written
  there by every run since the first build).

Browser checks: `frontend/scripts/run_list_check.mjs` (every run request answered by FIXTURE runs; safe against the
live backend; the actions of record 7.267 in its section 10) and `frontend/scripts/task_run_check.mjs` (the run that
follows the task, and Load run's run that stays; fixtures, safe against the live backend). Backend tests:
`tests/workbench/test_wb_run_list.py`, `tests/workbench/test_wb_run_list_cache.py` (the cache: what it sees and when).

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

### The Training tab: charts of a run's recorded numbers (2026-10-05, record 7.193, user request)

The user asked for "a Training tab beside Output in the workbench's existing bottom panel, using uPlot for live training
graphs. Keep Output available for logs and errors." The **Training** tab sits right after **Output files**; Logs, Data
tables and Output files are unchanged (the log and the errors stay in **Logs**). It draws charts of the run
shown in the bottom tabs, live while the run works. The charts exist on screen only: nothing drawn is written anywhere,
and the run's data stay the data-only files listed above (export them with Data tables). By user decision this is the
second kind of on-screen picture after the circuit pictures (7.33, 7.158): see the hard rule in CLAUDE.md.

**Where the numbers come from.** Only from what the run records - never from console text, and nothing is computed into
them. `GET /api/runs/training` (`training_series.py`) reads the run's own tables, the Parquet parts listed in
`data/_journal/flushes.jsonl`, and then the bundles of `data/_journal/wal.jsonl` that no flush has published yet: the same
rows, journaled before the next part is written (every 16 evaluations by default), so a live run is drawn up to its newest
result. The training loop was not touched for it: no event, no file and no simulation was added. Columns keep their
recorded names (`evaluations.reward`, `learner_updates.actor_loss`, ...): a chart title's tooltip names its source column.

| Chart | Recorded as | Along | What it is |
|---|---|---|---|
| Step reward | `evaluations.reward` | evaluation | The learning reward of each evaluation (one environment step). The run records no episode return, so none is drawn. |
| Meets every hard spec | `evaluations.all_hard_constraints_satisfied`, `status` | evaluation | 1 = every hard spec met, 0 = not; the smoothed line is the share of the last N designs that did. A timeout, a lost link, a cancelled or interrupted evaluation is no verdict on the design: a gap. |
| Evaluation success rate | the same, phase `frozen_eval` | evaluation | Only a frozen run evaluates a policy apart from training: the share of its designs so far that met every hard spec. |
| Worst spec miss | `normalized_constraint_violation` | evaluation | How far a design misses its worst hard spec, over the spec's scale; 0 = met. |
| Tightest margin | `clearance_margin` | evaluation | Signed margin of the binding hard spec (older runs: not recorded). |
| Best design so far: worst spec miss | `best_so_far_violation` | evaluation | The design the run keeps as best at each evaluation; 0 from the first design that meets every hard spec. |
| Best feasible \<objective\> | `best_so_far_metrics` + `best_so_far_feasible` | evaluation | Only when a Specs row says "then lower/higher is better": that row's value of the best feasible design (best_design.py's rule). An infeasible or unknown best design is a gap; until a feasible value exists the chart says why it is unavailable (7.201). |
| \<each spec\> | the `metrics` table's aggregate row of the spec | evaluation | The spec's value per evaluation, with its lower and/or upper limit as dashed lines, in the spec's canonical unit. |
| Simulation time per evaluation | `execution_seconds` | evaluation | Start to result, every attempt included. |
| Actor loss, Critic loss, Temperature loss, Mean TD target, Gradient norms | `learner_updates.*` | learner update or evaluation | The SAC learner's own diagnostics at each recorded update. |
| Temperature α | `learner_updates.alpha` | learner update or evaluation | The entropy coefficient. |
| Entropy estimate | `−learner_updates.mean_log_prob` | learner update or evaluation | The data dictionary's definition of the entropy estimate. |

"Along evaluation" = the evaluation's number in the order the run recorded it (1, 2, 3 ...; equal to `completion_index`
except where a crash-resume re-used one, which the hover line names). "Along learner update" = `cumulative_updates`;
with **Learner by: evaluation** (record 7.213) the learner's charts are drawn along `learner_updates.evaluations_collected`
instead - the number of evaluations collected when the update ran, the evaluation charts' x - and the updates that ran
after one evaluation (8 with the starting presets, 1 with the SAC defaults before record 7.183) share its x.
What a run does not record is listed under the controls ("Not in this run: ...", a closed line), and a chosen chart the
run cannot draw says why in its place: a frozen run has no learner updates, a run started with "save learner updates" off
has none either, an LLM-only run (a search method removed on 2026-10-06) has no learner, no Specs row may be marked
lower/higher is better.

**Training and evaluation apart.** Each evaluation's phase decides its series: **Training** (random warm-up, the SAC
policy, and the AI proposals of runs made before 2026-10-06), **Evaluation** (a frozen policy: `frozen_eval`, `validation`) and **Episode start** (the reset
design an episode begins from: no action, no reward). Each has its own colour and legend key. A Baseline simulation,
which calibrates (records 7.197 and 7.202; the run's status carries `calibration`), records its random designs as warm-up
draws, but nothing learns from them: the tab calls them **Calibration (random designs)**, and its learner charts say why
they are empty.

**Using it.**
* **Charts** (record 7.205, user: "add multiple charts same page support. more than the current 2"): up to eight on the
  page. Each chart chooses what it shows in its own title (a list that reads as the heading); **Add chart** (+, among the
  controls) adds the first chart the run can draw that is not on the page yet; × in a chart's title takes it off (one
  always stays). One to three charts stand side by side, four as two by two, more in rows of three or four; when the
  bottom panel is too short for them all it scrolls (the splitter gives it room). Metrics of different units never share
  a chart. A chart chosen for another run that this one lacks (a spec of another task) says so in its place and keeps the
  choice. Taking one chart off leaves the others' charts as they are, and a chart is only drawn again when its own data,
  zoom or width changed.
  **Smoothing**: off, or the mean of the last 10 / 20 / 50 / 100 / 200 recorded values of each series (default 20); the
  recorded values stay as faint points under the line, and a gap stays a gap in both. A chart's unit is written in its
  title the way the rest of the page writes units (`units.ts`, record 7.208: English letters - "uA", "ohm", "deg").
* **Key numbers** (record 7.215, the user's choice of "what next"): a table above the charts, one row per run on them
  (each in its chart colour when runs are compared): evaluations recorded, the **first passing design** (its evaluation
  number), the **passing share of the last 100 evaluations** (designs with a verdict: a timeout or a lost link is none;
  written "95 of 96 judged", branch record SIF-77),
  the **best design's worst-spec miss** now (0 = it has a passing design), and how the **entropy estimate** and the
  **temperature α** moved - the mean of the learner's updates of the first 50 evaluations it learned at, then of the last
  50 ("6.15 → -8.71": the policy settled; level: it still explores). Episode starts are left out, as on the charts; all
  of it is read from the recorded rows. It folds to its one line, and stays as left in this browser.
* **Learner by** (record 7.213, the user's choice of "what next": "Learner charts by evaluations"): **update** (the
  default) draws the learner's charts along its update count; **evaluation** along the evaluations collected, so that runs
  learning 1 and 8 times per evaluation line up with each other and with the evaluation charts. By evaluation the
  smoothing averages the updates of the last N evaluations ("mean of last 50 evaluations"), however many updates each
  had, and the hover line names the update under the pointer. Changing it lets go of the learner charts' zoom (it was in
  the other unit). Kept in this browser with the chart choices.
* **Hover**: the line above a chart says the evaluation (or update) under the pointer, its phase, episode and status, and
  the recorded value - without a pointer, the newest one. **Legend keys** switch a series off and on.
* **Zoom**: drag across a chart. A zoomed chart holds still while new results arrive (**Follow latest** goes off).
  **Follow latest** slides back to the newest results with the same zoom width; **Reset zoom** (or a double click on a
  chart) shows the whole run.
* The plots follow the bottom panel's height (the splitter) and the window's width.

**Several runs on one chart** (record 7.200, the user's choice of "what next"). **Compare...** (in the controls) lists the
runs of the run window; a chosen run is drawn on both charts beside the shown one, up to four runs, each in its own colour
(the shown run in the accent colour), with a line of chips above the charts naming them - × takes one off. A run is
named as the run window shows it (record 7.213): its task, its experiment in brackets when that has a name of its own
(not the default "experiment"; branch record SIF-77: the experiment alone, "tx1-vco-gatv2", stood beside a tab strip
naming the task), its seed and when it was made; the start of its folder's id is added only when two compared runs would
read the same. The runs share one x axis: the evaluation's number in each run's recorded order, or for the learner's
charts its update count or the evaluations collected (**Learner by**); at an evaluation where one run learned 8 times and
another once, each keeps its own updates in order and the hover line gives both. A run's designs are one
series (a training run's training designs, a frozen run's evaluated ones); episode starts are left out, so are a
learner's updates abandoned at a restart. The hover line gives each run's recorded value at that evaluation. A run that
cannot be drawn on a chart (it has no such spec, the spec's unit differs, it records no learner updates) is named on that
chart with the reason; a spec's limits are the shown run's. Each compared run is read like the shown one - its history in
pages, then every 2 s while its worker lives (the answer of `/api/runs/training` says so since 7.200: `state`,
`worker_alive`) - and kept in this browser like the chart choices. Checked on three recorded Spectre runs of the defaults
study: the learning run's pass share rises from about evaluation 600 while the two runs with the old defaults stay flat.
Record 7.213 put viewing copies of the day's eight recorded `real:mscr_ota7t` Spectre runs (the three starting presets
of records 7.199 and 7.209 and the defaults study's five) into the page's output folder, so that Runs... and Compare...
list them: the folders `outputs/<experiment>__<id>/` with a `COPY-README.txt`; the originals stay in
`artifacts/local/reviews/`. The copies were made without their save points; on 2026-10-05 (23:17-23:22) each got its
last save point back (session "Previous run model encoder saving", on the user's request "make it able to read todays
real spectre training run models"): the three presets and the defaults study's learning run from the study archives, the
other four defaults-study runs from the study session's temporary run folders, which no archive holds (the seed-1 run's
is the safety save at its design 226). So the model chooser offers them, and Continue would simulate into the copy. Each
copy's `COPY-README.txt` names its exact source.

**When it reads, when it draws.** Nothing while another tab is shown or the browser tab is in the background. Opened, it
asks for what is new since its last answer (a cursor of flush records; history pages target 30,000 rows, keeping each
published flush whole). Live journal rows share the remaining page budget and have a separate byte/row cursor, so
later polls fetch only new rows (7.201). Even one large bundle can span pages; its spec values still join to their
evaluation. A new flush or journal replacement resets the provisional rows before they are loaded again, without
double-counting. More pages are fetched immediately,
then every 2 s while the run's worker lives, once more when it ends, and never for a run at rest. A chart is redrawn at
most once a second and only when something changed; the chart objects are reused. New numbers never change the chosen
tab. Another run starts from nothing (runs are never mixed); a run continued after a pause or a crash gets a dashed
"continued" line where its new segment began. Since record 7.221 an answer reads the run's configuration and manifest
once each, and its flush log only from where the previous answer stopped, after checking that it is still the same
file with the same bytes (the same file, not shorter, its first 4 kB and last record unchanged; anything else is read
whole again); the configuration's objective is kept while its text is unchanged. The worker's state, the manifest,
the journal's tail and the Parquet parts are read for every answer. The caches are bounded and change what an answer
costs, never what it says: an unchanged poll of an 800-evaluation run on D: took 30 ms instead of 57.

**Counter resets.** After a crash the run resumes from its last save point, and its learner from that save point's
update count: the updates recorded between the save point and the crash are repeated by number. The charts keep both:
the abandoned updates as a dashed series of their own ("abandoned at a restart") and a red line where the learner went
on.

**Memory and long runs.** A chart gets a few points per pixel column of its width: in each, the first and the last row
and every series' smallest and largest value and its first gap, so spikes and gaps stay visible; every point drawn is a
recorded one. The page retains at most 50,000 evaluations and 200,000 learner updates per run, counting both published
and unflushed rows (7.201); past that the oldest half is thinned the same way, the thinned stretch is shaded and said
in a line, no mean is drawn over it, and the counts and evaluation numbers stay the recorded ones. Oversized buffers
and unused word entries are released after thinning. If independent extremes outnumber the available slots, the row
bound takes precedence. The run's tables keep every row. (Measured with 20,000 evaluations and 128,000 updates:
0.6 s to read, JS heap about 54 MB.) Since record 7.221 the charts of a run share what they derive from its rows -
categories, pass flags, the learner's restarts and its rows in the order of each x axis, running means kept as
checkpoints - and bring it up to date as rows arrive (after a new flush, thinning or a learner restart only from the
first changed row); a chart then works out only the rows in view. The values are the same numbers as before
(`training_data_check.mjs` compares them with the earlier builders), and the shared part goes with the run's store.
A changed frame of eight charts on a live run of 121,712 updates took 25-31 ms of the browser's main thread
instead of 110 ms.

Limits: a backend started before this tab has no `/api/runs/training`: the tab then asks for a restart of `serve`. The
journal's tail can be missing for one read while the journal is rewritten at a save point (said in a line);
for a run that trains at corners a spec's value is the worst over the corners, as the run records it; the charts have
no export (the numbers are in Data tables / Output files).
Backend tests: `tests/workbench/test_wb_training_series.py`. Browser checks: `frontend/scripts/training_tab_check.mjs`
(hermetic, canned answers), `frontend/scripts/training_data_check.mjs` (the arithmetic, under node).

### Corner check: a run's best designs at five corners (added 2026-09-22, user request)

The **Corner check** tab (after Output files) simulates the shown run's best designs again at five fixed conditions and
says, per design, whether it holds up. It is a check AFTER the optimization: nothing of it goes back into the run, its
replay, its model or its best design.

Since record 7.182 the tab is offered only where corners can be used (design advice: hide what the loaded task cannot
use): the loaded circuit simulates at corners (the backend's `training_capabilities.corners`), or the shown run is a MOCK
run. No saved real task does since 2026-09-30, so a real circuit shows no Corner check tab; the tab chosen when it goes
away gives way to Run status. Run configuration's **Training conditions** choice and its launch table follow the same
rule, and stay while a saved configuration still asks for corners, so that it can be set back to Nominal only.

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

Reward coefficients have the backend's 0..1 bounds (number boxes, drawn without the browser's up/down arrows since
record 7.171); training conditions include a fixed nominal entry, at least one
selected corner in `always`, and separate step/reset launch costs with one shared cap. Missing caps and nonzero robust
retries are explicit errors. Specs keeps the objective inside the **Constraint** list ("≤ upper, then lower is better";
only pairs that can work are offered) and shows **Judged at** only while training corners are planned (record 7.124);
both keep the backend's enum and boolean field types. Saved-model facts show all coefficients and condition
identities. Compatibility rechecks the entire current configuration (debounced), including reward, conditions and
probe edits; an old compatible result is cleared while checking. The contract the page's configuration gives a learner
is kept between checks - by its network, training settings, spec schema, component list, reward and condition settings
and the source digest of now - so a recheck builds no learner and hashes no source file for the same settings; a start
builds it anew (record 7.278). The status table separates first nominal from full-plan feasibility, nominal from adverse
values, and draft settings from the executed reward in the saved summary. Historical missing coverage stays unknown.

### Reward v2.1 controls and checks (2026-09-29, record 7.106)

New configurations start with compressed violations and worst-spec share 0.5 (since record 7.183 also with both bonus
weights at 1 and the compressed objective: "The reward as one sentence" below); saved ones retain their settings.
Training conditions offers Nominal only, Corners after nominal passes, and Every planned corner. The backend reports
whether the task supports corners (none since 2026-09-30). For after_nominal, a nominal failure costs one launch, a
pass costs 1 + K, and a reset costs one; the full step plan must fit the launch ceiling before preparation.

A hard spec whose value is missing after a completed simulation is a FAILED row, in every task (record 7.299, 2026-10-10):
the full miss on that row, the measured rows on their own values, the design replayed and learned from, the episode going
on - what a design that did not converge always got. Until then **Missing value = failed** under More columns switched
this on per row; the column is gone, the rows keep the value they stored and nothing reads it. In the workbench's own
books such a design stays not valid, never feasible and counted by "stop after N failed evaluations in a row": a task
whose random designs often lose a value needs that limit raised. Wrong units, a simulation that never judged the
candidate and infrastructure faults stay errors. A spec computed by an equation is missing only
when a probe it reads is missing; the other equation specs keep their values (record 7.112). **Margin sides** selects
the limits counted by clearance and Corner check ranking; feasibility still checks all limits. The zero-floor hint
explains the upper-only choice. A new row, and an edit of its unit, limits or constraint, suggests a scale:
6 dB for a dB row, else the size of the limit - which is what an empty scale means too (until record 7.183: 3 dB,
10 degrees, half an interval; a row still holding one of those follows its next edit). The suggestion follows later
edits until you type a scale of your own; a row with nothing to size it by yet (no dB/deg unit or limit)
keeps an empty scale, which the backend sizes from the threshold. Saved empty scales are not filled on load. (Record
7.112 fixed a suggestion that froze at 1 - e.g. 1 W - when a row was added before its limits were typed.)

Reward and conditions holds the nominal gate band and objective shape in its Advanced fold (record 7.183, below). **RL model... → Advanced** exposes **Alpha learning rate**,
stored per configuration; empty inherits the actor learning rate. Beside it, **Send the next design before learning**
(`run.advanced.update_after_dispatch`, record 7.281, ON by default since record 7.294, stored per configuration): a lane
gets its next design before the learner's updates of the result it brought, so it simulates while the learner learns. The number of updates and what every save point holds stay as without it (the
rows of updates run after the last commit go into the data as a record of their own before a save point and at the end,
so a pause right after them loses none: record 7.283); each design comes from a policy a few updates older, and the
evaluations table's `policy_version` says which. The check on real tasks (record 7.294: mscr_ota5t and mscr_ring3, seeds 2
and 3, 400 evaluations, off against on): the feasible designs of the last third were 273 off and 332 on - not worse, the
criterion written before the runs - and the runs were 18 % shorter (12-22 %). A configuration that never stated the switch
runs with it on since, one written before record 7.281 included (a run of then, loaded and started again); one that
turned it off, every run recorded from 7.281 to 7.294 included, keeps it off and its hash. No separate starting rate passed the extended
1,000-update unit check, so new configurations leave it empty. Attributed failures continue the episode, while its normal
horizon and configured success ending still apply.

Run status and Data tables show the last 50 scored designs' p90−p10 reward spread
and latest exploration bonus. When the spread is smaller, they show the brief's plain-language steering warning.
The start checklist also warns when recorded evidence has no design meeting all hard specs at all planned conditions,
names the best recorded design's worst misses and points to Corner check. This is a warning, not a start blocker or
proof that the targets are impossible. It reads existing tables/checks and explicitly named historical OTA7 qualification
folders; it never launches a simulation or changes targets.

Code: the steering check is `src/gator_workbench/reward_diagnostics.py` (`steering`, over the evaluations and learner
updates tables; `load` feeds `steering` in `GET /api/runs/status`). The
corner warning is `src/gator_workbench/reachability.py` (`check`, then `assess`): static validation runs it when the
training conditions are not Nominal only and nothing else blocks the start, so the page and the start checklist see the
same warning (code `corner_reachability`). It rejudges recorded
designs against the current hard specs: those of earlier runs of the same task with unchanged probes under the output
root (the configured one, else the remembered one), their Corner check results, and for `real:gpdk045_ota7` the
reference and designs of reward v2's qualification (folders named in the code, never a scan of `artifacts/`).

**Failure limits.** Run configuration's **Limits** fold (record 7.179; until then "Failure limits", which held only these two rules) has a field **Stop after N consecutive failed evaluations**
(`run.max_consecutive_failures`, default 5). A design the simulator reports as invalid or not converging is still
scored (reward -1) and kept in replay, and since reward v2.1 the episode goes on, so the network learns where the
circuit breaks. The stop rule counts it as a failed evaluation all the same: 5 in a row end the run as `failed`
(stop reason `consecutive_failures`), so a run that explores a region where many designs break may need a higher
limit. A dead backend has its own limit, **Pause after N consecutive infrastructure failures** (default 3, in the same
fold-out): it pauses the run, resumable once the connection gate passes again, instead of failing it. A resume starts
that count over (before record 7.135 it was restored at the limit, and every Resume paused again at once).

[Reward contract and validation](reward-v2.md#reward-v21-2026-09-29). These controls were checked on source previews
only: the user's live frontend/backend were not rebuilt or restarted. The subsequent fixed-action physical check used
10 of the approved 30 launches, exercised both gate paths and restored the starting design (record 7.108).

### The reward as one sentence, and the tested defaults (2026-10-05, record 7.183)

**In plain words.** A new configuration's reward is said in one sentence in Run configuration, under Reward and
conditions - folded since record 7.372 behind one line, "Reward: the tested one - objective minimize phase_noise" (or "no
objective in Specs"): *minus half the average miss, minus half the worst miss; a design that meets every Specs row scores
above 0 - up to +1 for the room it leaves on its tightest row, and up to +1 more for improving the row marked as the objective.*
A miss is how far a value sits outside its limit, as a fraction of the limit, compressed to between 0 and 1 (10 %
outside costs 0.09, 50 % costs 0.33, 100 % costs 0.5). You set the limits in Specs and, on one row at most, "then lower /
higher is better". Nothing else needs setting.

- **The five settings behind the sentence** sit in the **Advanced** fold below it: violation shape compressed, worst
  hard-spec share 0.5, objective bonus weight 1 with the compressed shape, tightest-margin bonus weight 1 (the nominal gate
  band joins them while corners are planned). They were compared in training on 2026-10-05; the reasons are in
  [decisions.md](decisions.md), "The tested defaults".
- **A configuration that holds other values** - every one saved before this record - is not changed. In place of the
  sentence one line counts them ("Reward: 2 settings not as tested."; record 7.372), a fold **Which** names each value
  that differs ("worst hard-spec share 0 instead of 0.5") and **Use the tested reward** stays in view; it sets the five
  and nothing else. The fold's line counts them ("Advanced - 2 not as tested").
- **No warning for a bonus without an objective row:** the weight is 1 in every new configuration, and without an
  objective row the bonus is simply 0; the sentence says that no row is marked.
- **The schema's own defaults are unchanged** (capped, share 0, no bonus): a configuration file without these fields means
  what it meant.

**The three training values that had to change first.** With the values every earlier run used - starting temperature
0.2, one update per evaluation - soft actor-critic is a uniform random search, and no reward setting changes what it does
(on Spectre, two very different reward settings gave the same design in 147 of 150 positions). Every starting preset in
the RL model window trains with starting temperature 0.01, 8 updates per evaluation and discount 0, with the other training
numbers those runs were made with - batch 8, warm-up 8, replay 10,000, episode length 4 (record 7.192) - and with
learning rate 1e-3, which learned about 100 evaluations earlier than those runs' 3e-4 (record 7.199); only its network
size is the published one. The GATOR baseline that held the measured setting was deleted with
its button on 2026-10-05, record 7.191 ([network-presets.md](network-presets.md), "The three tested values"). Where it
shows:

- **RL model...** names values with which the search stays random ("With 1 update per evaluation and a starting
  temperature of 0.2, soft actor-critic learned late or not at all ..."), and Run configuration then says "Review the
  settings in RL model."
- **Static validation** warns the same (`sac_values_random_search`) for any run that trains, also from the command
  line, and warns a from-scratch SAC run below 300 evaluations (`budget_below_sac_learning`): learning started after 250
  to 600 evaluations in the tests, and after about 150 to 300 with the starting presets (record 7.199; the warning says
  so since record 7.210). The page's starting budget stays 60 - every evaluation of a real task is a simulation
  you authorize - so a new SAC configuration carries that warning until the budget is raised.
- **An encoder you had put on the GATOR baseline** reads as its starting preset since record 7.191 (the settings file
  is not rewritten). A configuration already open keeps its own numbers; the window's This run / Template table
  shows the differences, and **Use the template's values** applies the preset. There are no preset buttons any more: typing a
  preset number back is the way to it, and the window then says **In use: starting preset**.

**Specs.** `hard` and the scale (headed **Scale**) are behind **More columns**. A new row's scale is the size of its
limit, which is what an empty scale means, and 6 dB for a dB row; the page no longer writes 10 degrees into a phase row
or half the width into an interval. (Record 7.217 tested both again, in training runs, and left the page's
suggestion as it is: 10 degrees changed nothing measurable, and half a window is right only for a window most designs
already hit - which a Baseline simulation can tell and the page cannot. See "What a Scale does to the margin bonus"
in [decisions.md](decisions.md).) A row whose limit is 0 needs a typed scale and blocks a run without one
(`scale_needed_for_zero_limit`): it was silently measured against 1 of its unit.

**Checks.** `tests/workbench/test_wb_tested_defaults.py` (11) and `test_wb_network_presets.py`;
`frontend/scripts/reward_block_check.mjs` (28: the sentence, the fold, the button, the RL model warning and the GATOR
baseline press, the Specs scale). The measurement: `artifacts/local/reviews/defaults-study-2026-10-05/README.md`.

### Calibration: random designs only; automatic task baseline (2026-10-07, record 7.248)

**Baseline belongs to task creation.** Save as saves the task and starts one fixed evaluation of its own starting
circuit automatically. The task supplies the saved parameters, measurements and specs; the baseline fixes scratch mode,
seed 0, one lane, nominal only, one evaluation/launch maximum and zero retries. It saves no model and learns nothing.
Connection/readiness failures are reported without undoing the save. Unknown probe results permit the one bounded
attempt; known failures still refuse it. A missing/failed baseline can be retried from the task's lines under the editors' toolbar. In-place
Virtuoso updates that invalidate a reference also start a new baseline; specs-only updates retain their reference.
New ngspice tasks run their saved deck too. Before optimization specs exist, the baseline checks measurement presence
with `probe - probe >= 0`, using an explicit Scale of 1; these run-only checks never become task specs or performance
claims. Current-source rows unsupported by SAC stay fixed in the saved deck, outside the baseline's action groups.

**Calibration** in the header simulates **64 random designs only**, uniform draws over the Parameters ranges, and
works out two settings from their measurements. There is no starting-design simulation, no per-lane reset simulation,
no replay insertion and no learner update. The ordinary training path retains its existing reset checks. Older
combined baseline/calibration runs retain their recorded meaning and remain readable.

- **Scale, for each Specs row:** the typical miss - the median distance outside the limit among the random designs that
  miss the row, in the row's own unit. One example, from the free ngspice test circuit: the output-voltage row allows
  0.7 to 1.2 V, so an empty Scale box means 1.2 V; the random designs that miss the row miss it by 0.042 V. With Scale
  0.042 such a miss counts as 1; with the empty box it counted as 0.035 and the reward hardly saw the row.
- **Initial alpha** (the starting temperature in the RL model window): 0.1 x the spread of the reward among the random designs,
  worked out with the proposed scales.

**The run changes nothing.** Run status of that run shows the proposals: one line per Specs row - its limit, how many
random designs miss it, the typical miss, the Scale the page holds now, the proposed Scale - then the Initial alpha, and
**Apply calibration**. One press writes the proposed scales into the Specs rows and the Initial alpha into the RL model's Advanced,
as one Undo step. Scales are written as every quantity of the page is (20 mV, 11 MHz, 9.6 deg; record 7.217).

**A task saved from a Virtuoso cell: Apply and save** (record 7.217). Such a task starts only with the rows it has
saved, so after Apply the page differed from its task and every start was blocked until Save task - two presses, and a
page that looked broken in between (the user, on seeing "1 blocking issue(s)": "whats the problem here"). For such a
task the button is now **Apply and save**: it applies, then runs Save task as a press on it would - the rows become the
task's next revision, the cell in Virtuoso is written to match and read back (about half a minute, no simulation); its
progress and its answer are where Save task's always are, under the editors' tabs. A change of Scale alone keeps the
recorded baseline. **Apply only** beside it applies and leaves the save to you. When Save task cannot start - another
save is running, no connection is chosen - Apply and save still applies and says why. A task that is not saved from a
cell (an ngspice task) keeps the one button, Apply calibration.

**When the run has ended, the header says so** (record 7.204, user: "build the prompt when the run finishes"). A line
of its own under the header reads, for example, *Calibration ready for real:mscr_ota7t: gain_vv 260 V/V · ugbw_hz
11 MHz · pm_deg 9.6 deg · ibias_a 280 uA*, with **Apply and save**, **Apply only** and **Not now** (a task not saved
from a cell: **Apply calibration** and **Not now**). The buttons there do what those in Run status do - the same code,
one Undo step - and the page then says what was applied and that the save is running, or why it could not start.
Not now changes nothing; the proposals stay in Run status. The line belongs to the run
the header holds. It goes when it is answered (kept in this browser, so a reload does not ask again), when the page
already holds the values, and when the next run starts; the next Baseline simulation asks again. A calibration that
proposes nothing says why on the same line. Nothing is applied by itself.

- **What it costs.** 64 candidate evaluations at any lane count. Each is a real simulation on a real task. The
  budget question states 64. Passing a spec or an invalid random design does not add a baseline/reset evaluation.
  Infrastructure failures and the ordinary launch/wall-time limits can still stop the run early.
- **Stopped among the random designs** (Abort): proposes from the completed designs if at least 16 gave a reward.
  Calibration does not record or replace the task's starting-design reference.
- **What is not proposed, and said in the table instead:**
  - a row fewer than 8 random designs miss (or fewer than one in eight): too few to name a typical miss (a window
    whose Scale is wider than half of it is proposed half its width instead, below);
  - the row that carries the objective: its Scale also measures the objective bonus, so it is left as it is (in the
    test it made no measurable difference whether that row was calibrated too);
  - any Scale while the reward uses the capped shape: a typical miss at 1 would sit on the cap. The calibration is
    made for the compressed shape (**Use the tested reward**);
  - the Initial alpha when the reward code cannot give the recorded rewards again from the recorded values, when
    every random design has the same reward, or (record 7.217) when the estimate is within a factor of 2 of the value
    the run had. On `real:mscr_ota7t` the estimate was 0.011 against 0.01 in use; in the tests 0.011 to 0.014 against
    0.01 made no measurable difference while a factor of 4 did, so such a proposal only made the page differ from the
    saved default. The line names the estimate and says that the value in use stays.
- **A window most random designs are inside gets at most half its width** (record 7.217). A row with a lower and an
  upper limit: a design inside it has at most half its width of room. The margin bonus is paid on the row with the
  least room measured in its Scale, so a window with a wide Scale always is that row, and the bonus pays for no other
  row. The output row of the LDO task `mscr_ldo_basic` is 1.18 to 1.22 V, and 51 of 57 random designs are inside it:
  with 1.22 V as its Scale (the empty box) the middle of the window is 0.016 of a Scale away from its limits, and the
  margin bonus of the whole task cannot pay for more room than that. Its proposal is half the window, 20 mV. The same
  holds when enough designs miss such a window to name a typical miss and that miss is wider than half of it.
  **A window most random designs miss keeps the typical miss:** it has to be found first. The ring oscillator's
  frequency row (0.95 to 1.05 GHz) is missed by 63 of 64 random designs, typically by 1.5 GHz; half its width, 50 MHz,
  would make nearly all of them count the same. The table then says what that Scale costs: a design inside the window
  counts as at most 0.033 of a Scale clear, and the margin bonus of that task stays that small.
- **Limits of a proposal.** A Scale stays within 0.01 to 10 times the size of the limit, the Initial alpha within 0.0001
  to 0.05, and both are rounded to two digits (half a window is exact): they are estimates from a few dozen designs.
- **A run recorded under another rule is worked out again when it is read** (record 7.217). Its random designs are
  simulated and paid for; only the arithmetic changed. The page then shows the proposals of today's rule with a line
  saying so; the run's own `calibration.json` keeps what the run said at its end, and nothing is written into a run
  folder. (The seven Baseline simulations of 2026-10-05 are such runs: one under record 7.197's rule, six under an
  unreleased state of this record that cut every window to half its width.)
- **Apply writes only what still fits.** A Specs row whose limits or unit were changed after the run is marked "not
  applied", and a run of another task than the one on the page offers nothing. Such a run is not compared with the
  page's rows at all (record 7.214: an LDO's `pm_deg` used to stand as the "Scale now" of an OTA's): a line names both
  tasks, the table shows **Scale in the run** and the Initial alpha the run had, and Apply waits until the page holds
  the run's task (choose it in the Tasks window).
- **From a script:** `POST /api/runs/start` takes `calibration_only: true` with `calibration_designs` (1 to 500).
  The result is `calibration.json` and `calibration` in run status, with `random_only: true` in its request. It cannot
  also request `baseline_only`. The historical combined API remains available for existing scripts.
- **Retry baseline:** `POST /api/tasks/baseline` takes the saved `task_key`, connection `profile_id` and optional
  `output_root`, and always uses the fixed single-evaluation recipe. Concurrent retries reuse a live baseline.

**What was measured** (free ngspice circuit `ota5`, 1,000 evaluations per run, 3 seeds per setting; on Spectre one task,
`real:mscr_ota7t`, two seeds per arm - record 7.211, below).
The scales of 64 random designs agreed with those of 4,153: gain 7.7 to 11 dB against 10, bandwidth 64 to 73 MHz against
70, output voltage 0.026 to 0.043 V against 0.04 (six seeds). In training, calibrated scales did not make learning
faster. They raised the share of passing designs in the last third of the run: 93 % to 98 % without bonuses (six seeds
in two rounds), 97.0 % to 99.1 % with the page's tested reward. **They have a price:** with the tested reward the
passing designs then drew about 7 % more power (median 80 uW against 75 uW) - a miss costs more, so the search keeps
more distance from the limits. The Initial alpha matters when the reward is flat: with scales ten times too large,
64 % passing with 0.01 and 91 % with the calibrated 0.0025; with calibrated scales its proposal (0.014) made no
difference against 0.01. Network size and encoder made no difference to the result, so nothing about them is
calibrated. The one Spectre run (`real:mscr_ota7t`, 65 simulations in 114 s) proposed gain 260 V/V where an empty box
means 400, bandwidth 11 MHz (25 MHz), phase margin 9.6 deg (60 deg), current 0.28 mA (1 mA) and Initial alpha 0.011.
**On Spectre the calibrated scales did not help** (record 7.211: `real:mscr_ota7t`, the Graph Transformer starting
preset, one lane, 800 launches, the plain reward without bonuses; the empty boxes against those four proposals plus
Initial alpha 0.011, seeds 0 and 1). First passing design 202 and 146 with the empty boxes, 455 and 177 calibrated;
passing designs in the last third 97.0 % against 93.5 %; their median bias current 705 uA against 682 uA (the seeds alone
spread from 619 to 746 uA); designs still failing after learning 5.1 % against 5.9 %. One task and two seeds: the
calibration stays a proposal to look at, not a habit. The numbers:
`artifacts/local/reviews/calibration-spectre-2026-10-05/README.md`. On ngspice:
`artifacts/local/reviews/calibration-study-2026-10-05/README.md`; the reasons: [decisions.md](decisions.md),
"Calibration with the baseline run".

**What the window rule rests on** (record 7.217): free ngspice runs with the page's starting reward, in which the
Scale of a window decided which row the margin bonus was paid on, and with it the share of passing designs (95.7 % to
98.7 % on one circuit in every seed; 91.7 % to 96.0 % on a second, inside the spread between its seeds). Nothing of it
was run on Spectre. The reasons: [decisions.md](decisions.md), "What a Scale does to the margin bonus"; the numbers:
`artifacts/local/reviews/reward-review-2026-10-05/README.md`.

**Checks.** `tests/workbench/test_wb_calibration.py` (13: the arithmetic, a window most designs are inside and one
most designs miss, the Initial alpha only when it differs by a factor of 2, the run with one and with three lanes, a
result of another rule worked out again when read, an invalid baseline, a stopped run's reference, the route);
`frontend/scripts/calibration_check.mjs` (38: one button and no tick, a real MOCK run of 65 evaluations in a browser
that had unticked the old tick, the line under the header and Not now, the proposals, Apply as one Undo step, an edited
row left alone, a second run that proposes an Initial alpha only by the factor-of-2 rule and whose line is answered
with Apply calibration, one Undo, a reload, and a run of another task than the page holds, record 7.214);
`frontend/scripts/calibration_save_check.mjs` (22, hermetic, a task saved from a cell: Apply and save, Apply only and
Not now with the Scales written as quantities, the save that holds the applied rows, one Undo, Apply only, and Apply
and save while another save runs).

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

**Several designs at once** ("Concurrent Spectre jobs", `run.concurrency`). A real task allows at most 6 since record
7.143 (4 before): the simulator host has 8 cores, and 6 jobs at once ran with no licence error, though jobs sometimes
waited up to 0.8 s for a licence. With the netlist built from the readback (7.142), 6 lanes against 4 took
`mscr_ota7t` from 0.54 to 0.41 s per evaluation (4.9× one lane) and `mscr_vco_lin` from 2.03 to 1.40 s. Each job ran
10-15% slower on the shared CPUs, and the preparation process was busy 71-79% again. Measured on Spectre on
2026-10-01 (record 7.136), before those changes, `real:mscr_ota7t`, 20 evaluations per run:

| at once | per evaluation | faster | lanes starting (before the first evaluation) |
|---|---|---|---|
| 1 | 1.99 s | 1× | 2.1 s |
| 2 | 1.10 s | 1.8× | 4.3 s |
| 4 | 0.87 s | 2.3× | 8.7 s |

Each lane runs its own Spectre jobs, but every candidate's sizes are written into the one Virtuoso cell and netlisted
by one preparation process, one candidate at a time. On this cell that takes about 0.6 s per candidate:
- five reads of the whole cell, 0.23 s;
- the netlist export, 0.22 s;
- two window checks, 0.06 s;
- the write, 0.06 s.

With 4 lanes that process is busy 90% of the time, so about 0.6 s per evaluation is the floor whatever the lane count.
Since record 7.137 a candidate takes three of those reads and one window check: the two reads that repeated a check made
a moment earlier are gone (user decision; optimizer digest step, `docs/decisions.md`).
Checked on Spectre with both changes of 7.137 (one run, the same settings): 4 at once took 0.70 s per evaluation
(2.8× one at a time), and the lanes started in 2.6 s.
A cell with more instances reads more slowly: `mscr_vco_lin`, 34 instances, takes about 0.4 s per read. In these runs the
lanes opened one after another, about 2 s each, which is why more lanes started later. Since record 7.137 they open side
by side (`lanes.open_lanes`). Other findings:
- One 4-lane run stalled for about 12 s once the policy took over (1.59 s per evaluation). A repeat with a stack
  sampler did not stall, so the cause is unknown.
- One CPU thread per process (`OMP_NUM_THREADS=1`) made a 4-lane run slower: 1.10 s per evaluation and a 21 s
  longer start.
- Results come back in a varying order, so two multi-lane runs with the same seed can differ.

**The read built once** (record 7.296, 2026-10-09). Those 0.4 s were almost all string handling. The bridge's read program
(virtuoso-bridge 0.8.0, `read_schematic`) grows its answer a line at a time with `strcat`, which copies the whole answer
for every line, so the time grows with the square of the answer. Inside Virtuoso, on `mscr_vco_lin_c` (34 instances,
1,092 values, a 30 kB answer), the bridge's read took 434 ms, of which reading the values took about 4 ms. Since 7.296
the workbench runs the same program with each line appended to a list and the list joined once
(`schematic_read.read_cell`): the same text, parsed by the bridge's own parser, in 5.7 ms inside Virtuoso and 70 ms at
the client instead of 498 ms. Most of what is left is the answer's transfer. Every candidate's read before and after its
write uses it (`CdfBridgeBackend._read_snapshot`), as do Save task's fingerprints of the original cells and the cell
import. A small cell gains nothing (`mscr_ota5t`, a 6 kB answer: about 16 ms either way). The 180 nm process cells of record 7.295
gain most: `asz_sys` answers about 100 kB, an estimated 4-5 s per read before. If the bridge's read program is ever not
the one measured, the workbench reads with the bridge's own call. On Spectre (`mscr_vco_lin_c`, 6 lanes, 200
evaluations, record 7.296), a candidate's preparation fell from 2.26 to 0.47 s and stopped queueing; the run, bound by
Spectre, took 7.2 instead of 8.0 min.

**Netlists built from the readback** (records 7.140 and 7.142). The decks of different candidates differ only in
values: the written ones and those the PDK callbacks derive, which the readback after each write already holds (7.138).
Since 7.142 (user decision of 2026-10-02) a real run works like this:
- The session's first candidate and every 5th after get Virtuoso's native export, which is the one simulated.
- Each of those is compared, statement by statement, with the netlist built from its readback; a difference stops the
  run.
- The candidates in between get the built netlist: the session's first native export with the readback's values filled
  in (`CdfWritableProfile.render_export`), held to the cell by `validate_export` like an export. No export and no read
  after the write.
- Each candidate's manifest says which it got (`netlist_source`).

The built netlist has the same statements as Virtuoso's export: same devices, connections and values. Only the line
breaks and a date comment can differ, which Spectre ignores, so the simulation results are the same. Since record 7.309
(2026-10-11; user: "14.05 is the same as 14.050") the comparison reads a parameter's number as a number: one netlister
prints the form's `14.05u` as `14.050u`, another an exponent as `1.0E-12` for `1e-12`, and both spellings are one value.
The numbers are compared exactly, as decimals, never rounded; the parameter's name, its brackets, its scale letter and
every other word of a statement must still be the same text (`native_preparation.same_statement`). Before, a second
foundry's PDK - whose netlister re-spells typed sizes - had every candidate exported natively, 0.36 s instead of 0.07 s
per candidate in Virtuoso; now its tasks build their netlists like every other task. The variable `GATOR_NETLIST_BUILD`, set in the environment the server or run starts from, chooses:
- `skip`, the default;
- `check`: every candidate native, each compared (7.140);
- `native`: every candidate native, nothing built.

On Spectre at 4 lanes (20 evaluations each), the default against the check-only runs:
- `mscr_ota7t` went from 0.70 to 0.54 s per evaluation (3.7× one lane);
- `mscr_ring3` from 0.71 to 0.64 s;
- `mscr_vco_lin` stayed at 2.0 s, since its 5 s transient jobs set its pace.

The preparation process is no longer the limit there: busy 62% instead of 92%, about 0.29 s per candidate. A value one
float step past its bound counts as that bound, in the group check and in `ActionMapper.encode`. "180n" parses to
1.8000000000000002e-07, and a policy design at the 180 nm top of a length range had stopped `mscr_ring3` and
`mscr_vco_lin`.

The native export itself sets OCEAN up once per session and then only netlists (`VirtuosoBridgeBackend._export_netlist`,
7.142), about 0.09 s less per export. If the netlist returned is not this testbench's, it sets up again. A task
measured inside Virtuoso (the Maestro recipe, which every MScR task uses) keeps the bridge's export, which sets up
every time.

Tried and removed (record 7.148): each lane measuring its Maestro outputs with an OCEAN of its own on the simulator
host, so that the Virtuoso session only prepares. On Spectre at 6 lanes the values were identical, but runs were no
faster (0.39 vs 0.41 s per evaluation on `mscr_ota7t` once every lane's OCEAN was up), and starting six OCEANs slowed
the first 10-20 s. The preparation, not the measurement, is what limits a run (`docs/plan-measurement-off-virtuoso.md`).

**Where a candidate's time goes now** (record 7.149, 7.143's 6-lane `mscr_ota7t` run). A lane's cycle is about 2.2 s:
- 0.62 s before Spectre starts: the preparation, about 0.3 s, and its queue;
- 1.47 s of Spectre job: Spectre about 1.0 s (reading the PDK models 0.43 s, the analyses 0.02 s), transfers about
  0.25 s, the measurement about 0.1 s;
- under 0.1 s after it: lanes wait 0.03-0.07 s for their next candidate.

**Job folders on the WSL disk** (record 7.149). A run whose folder is on a slow mount - D: seen from WSL is 9p, about
100 times slower per file operation - keeps its lanes' export packages and per-job folders in
`/tmp/gator-work/<experiment>/<run>`, on the WSL disk (`layout.local_scratch`; WSL empties `/tmp` at every boot):
- Each lane's `exports` and `simulations` folders are links there (`lanes.ScratchLinked`). The lane's own folder stays in
  the run folder, with its launch journals, candidate records and restoration record, and so does the preparation's
  journal (`~/.local/state/gator/bridge-state` since record 7.167, `paths.bridge_state_dir()`).
- Retention moves each kept job folder into the run folder when its result is durable, as before; the rest are deleted
  in the scratch.
- When the run ends, the links and the scratch are removed (`RunEngine._clear_scratch`). The event `simulator_scratch`
  names the folder.
- `GATOR_LOCAL_SCRATCH=off`, set like `GATOR_NETLIST_BUILD`, turns it off.

Runs from the page write to the output root of the settings (`/mnt/d/gator/outputs` here); the Spectre trials above
wrote to the WSL disk. On Spectre with the run folder on D: (`mscr_ota7t`, 6 lanes, 40 evaluations each), the run
took 0.84 s per evaluation with its job folders on D: and 0.50 s with the scratch. On D: the one-at-a-time preparation
queued every lane: a built candidate took 0.46 s there instead of 0.23 s. The rest of the gap to the all-local trials
(0.41 s) is the run's own records on D: (tables, launch journals, candidate records), which stay there. An output root
on the WSL disk removes that part too.

The windows are checked before each native export only (record 7.149): an open ADE/Maestro window conflicts with
OCEAN's export, not with a write, and a netlist built from the readback runs no OCEAN. That is one Virtuoso call less
for 4 of every 5 candidates, about 0.03 s of the one-at-a-time preparation.

**A trimmed model library** (record 7.154). A fresh Spectre spends about 0.25 s of each job reading the model file
(7.153), and GPDK045's corner section loads 23 parts - every transistor family, diodes, bipolars, capacitors, resistors,
an inductor - where a circuit uses two or three. At the start of a real run of a task with a recorded baseline,
`model_library.attach`:
- reads the library's layout on the simulator host by names only: its sections, the includes in each, the subcircuits
  and models each part defines and what their subcircuits use (an awk script through the bridge's own SSH runner; two
  calls, 0.7 s for GPDK045). No model text leaves the host;
- lists the circuit's devices and keeps, for every section, the parts that define them, the parts those parts'
  subcircuits use, and every part that defines no device (GPDK045's SOA switch), in the library's order. A section with
  statements of its own besides its includes is left whole.

The decks then include those parts of the PDK's own files in place of the one model include, after a comment line that
says so; a corner deck gets its corner's parts. The MScR tasks keep 2 or 3 of the 23:
- `mscr_ota7t`, `mscr_ring3`: the 1.0 V transistors, the MIM capacitor and the SOA switch;
- `mscr_vco_lin`: the 1.0 V transistors and the SOA switch;
- `mscr_ota5t`, `mscr_ldo_basic`: the 1.8 V transistors and the SOA switch; `mscr_ldo1_rgcn`, `mscr_ldo2_rgcn`: also
  the MIM capacitor.

What guards it: such a run compares every simulated reset of the start design with the task's recorded baseline, which
was simulated with the whole file, at 1e-6, and stops on a difference (`NativeEnvironmentFactory`). A part left out that
a device needs makes Spectre stop with an undefined-subcircuit error. So a task without a baseline yet (its Single
baseline simulation) and the corner check include the whole file. Anything that fails while reading or planning leaves
the whole file in place and says why; the run event `model_library` names the parts kept. `GATOR_MODEL_LIBRARY=full`,
set like `GATOR_NETLIST_BUILD`, turns it off.

On Spectre (record 7.154) every result value of all seven MScR tasks was identical with the trimmed library, and a job's
model reading was about 0.25 s shorter (Spectre's total in a 6-lane `mscr_ota7t` run: 0.72-0.79 s instead of 0.99-1.10
s). That run was no faster (0.43 s per evaluation against 0.41), because the one Virtuoso session, which prepares every
candidate and measures every Maestro result, is the limit at 6 lanes. On 2026-10-03 none of the MScR tasks had a recorded
baseline, so their runs still include the whole file until a Baseline simulation of each records one.

**Maestro's unread info outputs left out** (record 7.157). A Maestro test's netlist asks Spectre for six info outputs
after the analyses - `modelParameter`, `element`, `outputParameter`, `designParamVals`, `primitives`, `subckts` - which
no output and no part of GATOR reads. They cost about 0.36 s of every Spectre job (1.13 s against 0.76 s on
`mscr_ota7t`) and were 232 of the 268 kB a job downloaded. The Maestro recipe's deck leaves them out
(`recipes.without_unread_info`) and puts a comment line where they were; the operating points (`dcOpInfo`,
`finalTimeOP`, which OP and OPT read) stay. A task whose output expressions use `VAR` or name one of the six keeps all of
them. With and without them, Spectre's analysis results were byte-identical apart from their headers, and GATOR's own
OCEAN measurement gave the same value for all 10 outputs of `mscr_ota7t` and `mscr_vco_lin`, equal to the values their
runs had recorded. Kept job folders no longer carry the parameter tables ADE's results browser shows.
`GATOR_INFO_OUTPUTS=keep` keeps them.

With both, a one-lane `mscr_ota7t` run took 1.30 s per evaluation (20 evaluations, record 7.157), against 1.99 s in record
7.136: preparation 0.22 s, upload 0.02 s, the remote shell and Spectre 0.58 s, download 0.05 s, OCEAN 0.10 s.

**The bridge's SSH tunnel** (record 7.161). Every Virtuoso call goes through the bridge's tunnel to its service on the
simulator host. Started with `-N` (no terminal), OpenSSH left Nagle's algorithm on, and every call with a short answer
waited about 40 ms for a delayed acknowledgement: 44 ms for `1+1`, against 2-3 ms without SSH or through a tunnel with
a terminal. The bridge checkout `~/virtuoso-bridge-lite` (outside this repository, uncommitted there) now starts the
tunnel with `-tt` and a remote `sleep`: a short call takes 2.5 ms and the run adapter's window check 4 ms instead of
about 30 ms. A bridge update has to keep that change.

**The adapter's lock and crash journals on the WSL disk** (record 7.167). The preparation writes a crash journal before
and after each write to the cell. Under `artifacts/local/bridge-state` on D: the two writes took 16.2 ms per candidate;
in `~/.local/state/gator/bridge-state` (`paths.bridge_state_dir()`, `GATOR_BRIDGE_STATE_DIR`) they take about 1 ms. The
same folder holds the session lock that runs, checks and Save task take, so every GATOR process names it the same way,
whatever its settings folder.

**A run binds its own copy of the bridge's settings file** (2026-10-11, record 7.306; user: "can you fix this when
opening two virtuosos?"). The run adapter binds the settings file (`~/.virtuoso-bridge/.env`) when it attaches and checks
it at every call, so that a run cannot go on against a link somebody re-pointed; any change of the file therefore ended
a run in the middle of a write ("Bridge configuration changed during an active worker"), with its cell left
half-written. That happened on 2026-10-10 when the keys of a second Virtuoso session were added to the shared file.
Since this record the bridge configuration of a real task names a copy of the file as it is when the run starts -
`env-snapshots/<the file's checksum>.env` in the adapter's state folder, readable by its owner only
(`paths.bridge_env_snapshot`). What is written to the shared file afterwards does not reach a running run; a run started
later takes the file as it is then; the adapter's own check is unchanged and as strict as before on the copy. Copies
older than 30 days are removed when a new one is written; a settings file that cannot be read is named as before, and
the attach fails in its own words. So a second Virtuoso session can be added to the settings while a run works.

**Two Virtuoso sessions carry a run each** (2026-10-11, record 7.311; user, of a second Virtuoso opened beside the
first: "do you think second virtuoso can be used for sizing? to accelerate", then "build that once B has landed").
Until this record ONE lock stood for "Virtuoso": while a run held it, a Save task, a Check now, a baseline or a second
run was refused through any connection. Now there are two kinds of lock in the adapter's state folder:
- **A lock per Virtuoso session.** A connection names the bridge's settings file and a bridge profile; the keys
  `VB_REMOTE_HOST_<profile>` and `VB_REMOTE_PORT_<profile>` say where that session's daemon listens. A connection without
  a profile, or one whose host and port are the first session's, or one that cannot be told apart from it (no port, an
  unreadable file) is the FIRST session and keeps the lock it always had, `session.lock` in the folder itself. Any other
  is a further session with `sessions/<name>/session.lock` and its crash journals beside it; two profiles that reach
  one daemon are one session (`paths.bridge_session_key`, `bridge_session_dir`). One process at a time drives a
  session.
- **A lock per cell**, `cells/<library>/<cell>.lock`. Each Virtuoso session keeps its own copy of an open cell in
  memory, and the second to save would write over the first, so a cell is worked on by one process at a time whatever
  the session. The adapter of a form-written task holds it from before its connect to after its close
  (`cdf_write.CdfBridgeBackend`, `cell_lock`); Save task's write process holds the locks of the cell, of its copy's
  name and of the bench.
So a run through a connection of the second session starts while the first session is running another circuit, and is
refused - in words, before anything is read or written - when its own session or its own cell is in use: Check now's
step "Another real run is using Virtuoso" names the lock that is held and the process holding it, the corner check
and Save task say the same. A task written by the older adapter of the optimizer package (none is registered today),
which takes no lock of its cell, runs in the first session only. The optimizer package is not touched: its adapter
takes the lock of the state folder it is handed. What a second session needs besides: its own connection in the
connection file (the same link and model file, the session's bridge profile), its daemon loaded in that Virtuoso with
the nonce cache raised like the first, and for a queue the copy of the queue script that watches that session's lock.

**Whichever session is free** (2026-10-15, record 7.351; user: "send it to whichever is free"). Since record 7.345 a
connection's sessions sit under one name (`session_group`); what the page starts there goes to one of them
(`session_routing.choose`, called by `start_run` and by the Check now and Save task routes):
- **Free** = nobody holds the session's lock (`consistency.lock_holder`, read from `/proc/locks` without taking it), no
  queue holds its queue lock, and no run this backend started a moment ago is still on its way to taking it: a choice
  reserves its session until the run's worker holds the lock or has ended, or the start is refused (at most 10 minutes
  for the start's own checks, then 5 for the worker; a reservation is let go only by its own choice).
  With no session free the start is refused in words, naming who holds each one; Check now then runs as before and its
  "busy" step says the same.
- **A queue keeps its session** (`paths.bridge_queue_lock`, `<session folder>/queue.lock`): between two runs of a queue
  the session lock is free for a moment, and work from the page sent there would make the queue's next run fail. A
  queue holds its session's queue lock for its whole life (a shell queue: `exec 9>>"$QUEUE_LOCK"; flock -n 9`). Round 2's
  queue of 2026-10-14 is older than this lock and holds none: until it ends, page work on `lab`/`asz` can still meet it.
- **Virtuoso's own lock.** A cell one Virtuoso holds open for editing cannot be written through another (record 7.311;
  record 7.350 met it on the published reference). Before choosing, the sessions whose answer can change the choice - a
  busy one, and the free ones when more than one is free - are asked how they hold the task's cell (`cell_hold.look`,
  read-only and without the connection gate's probe: open, open for editing, unsaved edits, shown in how many windows;
  side by side, with the choice's lock let go meanwhile). A free session that holds it open for editing takes the work.
  A busy one lets go of it - reopens it read-only, `dbReopen`, gated like a write - when nothing can be lost (saved, in
  no window; `cell_hold.release`), and only once the work's own refusals have passed (`session_routing.release_pending`:
  `prepare_run(before_write=)`, Save task's `task_save.check_saveable`), so a refused start changes nothing in
  Virtuoso; otherwise the start is refused in words. A session that does not answer within 20 s, or whose last test
  failed, is said in the record and left out of that question.
- Otherwise the free session whose last connection test passed, the connection's own session first among equals.
- **A run lets go of its cell when it ends** (`cdf_write.CellLocked.close`): once the cell is back at its recorded sizes,
  under both locks and before the client closes, a connection that wrote the cell reopens it read-only - not when it has
  unsaved edits or is in a window - so the next run can write it from either session. A check that only reads (Check now,
  the check before a start) leaves it as it was. Never raised: a failure leaves the cell as before.
- **Save task** goes to the chosen session after its own refusals, and the baseline it starts gets the same session.
- **Continue** goes to whichever session of the run's own connection is free (`runs.resumed_session`; the segment's
  `changed_run_settings` names a new session), never to another connection.
- Nothing is chosen for a session named by its own name, for a connection of one session, for a built-in task of the
  older adapter (first session only), or for a command-line run. The corner check stays on the run's own session.
The choice and its reasons are in the run's manifest (`segments[-1].virtuoso_session`, one more line in `notes`) and in
the start's answer (`virtuoso_session.said`), which the page's run message shows.

**The scheduler, 2026-10-08** (records 7.280-7.282; measured on the twelve 800-evaluation runs of the night before: at
4 lanes the scheduler thread was busy 49-62 % of the time - the learner's 8 updates per result alone 34-48 % - and only
1.2-2.1 of the 4 lanes simulated on average):
- A save point every 200 evaluations by default (50 before): a save waits until every lane is idle, which cost 8-10 % of
  a 4-lane run. The data tables are written every 64 evaluations (16 before; each write took 0.35-0.94 s). Neither
  changes a result.
- The scheduler is woken by a lane's result instead of looking every 50 ms.
- `logs/timings.jsonl`: what each evaluation's stages took (preparation, queue wait, parameter update, netlisting,
  graph, simulation), written 16 at a time. The environment measured them before, and they went with each
  evaluation's journal.
- **Send the next design before learning** (Advanced, record 7.281, on by default since record 7.294; see the RL model window).
- **The simulator host's job folders** (record 7.282): the bridge keeps every Spectre job's folder on the host, and a
  night of runs left 58,000 of them while Virtuoso grew to 10.5 GB (68,871 folders, 49 GB, again by the next noon). A
  run now removes the host folders of the designs whose raw output it does not keep - each folder named by that
  design's own measurement (`results_on_host`), never a pattern - at each save point (the lanes are idle then) and at
  its end, through the bridge's own SSH runner, and says `simulator_host_folders_removed` in its events. The kept
  designs (best and failures) keep their host folders, so they can still be measured again there; a failure let go of
  later for the storage limit has its host folder remembered before its copy goes, like the others (record 7.283).
  `output.keep_simulator_host_folders` keeps everything. At its start and end a run says Virtuoso's memory on the host
  (`virtuoso_memory`).

Tried and removed (records 7.149 and 7.152): a Spectre that stays running in each lane, sent only each candidate's changed
values. Its reruns took 0.05 s, but a running Spectre does not follow changes of `l` or `m` (DC up to 98% off a fresh
Spectre on the same values), so it could not give correct values; `docs/plan-persistent-spectre.md`.

## The right column: settings, saved models and the graph view

### Search: SAC only (2026-10-06, record 7.226)

SAC is the only search method. The **Search method** box and the four methods it offered - SAC, LLM warm start → SAC, LLM
only, SAC with LLM rescue (record 7.116) - were removed on the user's request of 2026-10-06 ("SAC is the only default and
other methods should be launched through agent tab opened agent cli"), together with everything that served them: the AI
call and cost ceilings, the AI thread and hints of a run, the header's "LLM n / m", the run engine's search session, the
sizing CLI clients and, with the user's approval, the optimizer package's `search/` and `ActionMapper.encode` (one
fingerprint step, `docs/decisions.md`). Help from a language model during an optimization - a run that is stuck, a design
to look at - is asked of Claude Code or Codex from the Agent window, in words (below, "The Agent window").

What stays readable: a run made with one of the methods keeps its folder, tables (`llm_calls` included, with its
`llm_call_id` and phases in the evaluations) and its data dictionary; the Training tab, Data tables, Output files and
Corner check read it as before. It is not continued: Continue and Resume refuse it in words (`search_method_removed`)
rather than going on as SAC, because a run keeps the method it started with; its RL model (every method but LLM only has
one) can start a new run in Mode fine_tune. A configuration saved with the box still loads: the schema drops `run.search`,
and both hashes are unchanged for SAC (the block was hashed as absent at its default). A page older than the server that
still sends a removed method is refused at Start with "reload the page", and the page drops the block from the
configuration it keeps when it loads (`store.ts` `migrateConfig`). See [LLM sizing](llm-sizing.md) for the methods as
they were.

**A comparison method: Bayesian optimization (2026-10-10, record 7.304).** SAC stays the search method of the page. For
the transfer experiment's question "is SAC better than Bayesian optimization, from scratch" (user: "different opt on one
circuit from scratch (sac bayesian)") a configuration file may say `run.optimizer: "bayes"`; the page has no box for it.
Such a run is the same run in everything but who proposes the designs: the same task, environment, reward, lanes, budget
and recorded tables, and the same random warm-up designs for the same seed. After the warm-up each design comes from
`gator_workbench/bayes.py` instead of the policy, every finished design and its reward is told to it (a design whose
simulation failed counts as the worst seen), and the network is neither asked nor trained - the run records no learner
update and saves no RL model (record 7.325), regardless of the checkpoint setting. Older Bayesian save points
held the untrained start: they stay on disk, but are excluded from the model chooser and label suggestions,
report no resumability, and cannot be selected or loaded for resume, fine-tune or frozen evaluation.
The method is TuRBO-1 in its one-design-at-a-time form: a Gaussian
process (Matern-5/2, one length scale per variable) fitted on the designs so far, a trust region around the best design
that doubles after 3 improvements in a row and halves after max(4, variables) designs without one, a fresh start from
random designs when it has shrunk to nothing (event `bayes_region_restarted`), and Thompson sampling inside it; its own
first designs are 2 x the number of variables in all, the run's warm-up designs counted. Written with torch only: no
package was added. In the tables its designs carry the action source `bayes_opt`; the run's manifest says
`architecture.optimizer`. Limits, on purpose: from scratch only (`bayes_needs_scratch` otherwise), and the run cannot be
resumed, because the search state lives in the run's process. A configuration that does not name an optimizer is a SAC
run and keeps its hashes. Checked on functions whose optimum is known before any simulation (Hartmann-6: 3.20 to 3.32 of
3.32 in 150 designs, random search 1.4 to 2.8; a 20-variable Ackley: -2.0 to -2.3 of 0 in 400 designs, random search
about -10.5; 0.34 s per design at 27 variables and 800 designs).

### Run configuration and the RL model window (2026-10-02, record 7.150; renewed 2026-10-07, record 7.265)

Record 7.327 adds **CircuitGPS — joint spec and parameter attention**, a sixth template.
Selecting it chooses **Structured** measurement inputs while keeping the current physical inputs.
**Structured + Transferable 2** combines the ordered measurement programs and circuit bindings with
the existing PDK/bench/operating-point features. Both inputs are available for CircuitGPS; other encoders
keep Standard/Transferable/Transferable 2. The saved-model chooser restores the structured contract,
and the structure/graph inspectors support its repeated attention blocks. See [CircuitGPS](circuit-gps.md)
for the computation, supported expression subset, missing-value rules and checkpoint boundary.

Record 7.298 added one choice above "Nominal device operating points" (the Advanced fold stays directly below that box): **Network inputs** Standard / Transferable (the
section "Transferable network inputs" below). Record 7.317 added a third choice, **Transferable 2** (the section "The second
build of the network inputs" below). Since record 7.332 a new model's inputs come with its encoder's template and the window
shows one line of text where the box was (same section, "Which inputs a new model gets").

Since record 7.228, the templates also offer **GraphGPS — port-aware** and
**Parameter-group attention — experimental**. Both have per-encoder structural
input settings (`none` / random-walk returns at 2, 4, 8, 16 steps), preserved in
configuration, saved defaults and checkpoints. Their 48/4/4 starting presets and
inherited SAC settings are experimental. A loaded model restores the structural
setting along with its sizes. See [architecture and compatibility](global-encoders.md).

Run configuration names the next run's model in one line, beside the **RL model...** button (record 7.265, build step 4
of the [frontend run workflow plan](plan-frontend-run-workflow.md), "RL model window"; until then the button read "RL
networks..." and a **Mode** select stood above it, with the RL model label below):
- "New model · Graph Transformer template · GT 48/4/4": the template, then the network in short (record 7.160, user:
  "show the current network selection next to the RL network button in short"; GT = graph_transformer, `–` where an
  encoder has no heads, then "op. points" and the component list when they are on);
- "Fine-tune ota7t (2) · save point 420 evaluations" or "Evaluate ota7t (2) · save point 420 evaluations · deterministic
  actions": the saved model by its name, and the save point the run loads;
- "Fine-tune · no saved model chosen" until one is chosen.

The tooltip says it in full. Under the line stays the model check's suggestion of another Mode ("Suggested: Fine-tune -
..."); where the saved model's own run can be continued exactly, it links to that run in the Runs window instead
("This model's own run can be continued exactly: open it in Runs"). Budgets, concurrency, seed, the run limits (one
Limits fold since record 7.179), reward and training conditions stay in Run configuration.

The button opens the **RL model** window. At its top is the **Mode**, as three buttons, each press one Undo step:
- **New model** (`scratch`): a new RL model, made from one of the templates; it starts from random weights;
- **Fine-tune** (`fine_tune`): a saved model keeps learning, in a new run;
- **Evaluate only** (`frozen`): a saved model is used as it is, with no learning.

`resume` is not a choice: continuing a run is an action on that run (the header's Resume, Continue... in the Runs
window). A configuration that still holds `resume` - saved before record 7.265, or imported - has **no Mode chosen**
(record 7.267; plan "The draft"): the model line reads "No Mode chosen", Run configuration and the window say so and name
the run it continued, a link to it in the Runs window (Continue... and Show results are there), and **Start** and
**Calibration** wait until a Mode is chosen - never a silent New model or Fine-tune. The configuration keeps the value
`resume`, which every backend route still reads (the command line still starts one); the page only shows it as no Mode
chosen. A configuration without any Mode (a task's starter rows, an old file) is New model, as the backend reads it.

**New model** shows:
- **Templates**: one row per encoder, with its sizes, its training values (updates per evaluation, starting temperature,
  discount, learning rate), where they come from (the starting preset, or edited and saved in the backend) and how many
  saved models were made from it. **Use template** or a double click fills the next run's network and training values
  from it, as one Undo step - what choosing an encoder did before. The template in use is marked.
- **The ... template, for this run**: its sizes, structural input, the operating-point input, Advanced (record 7.195),
  the Components list, the "In use" line with Use the template's values and Save into the template (below), and where
  the values come from. No preset buttons (record 7.191).
- **Name of the new model**: the RL model label (below).
- **Saved models, to look at**, folded: the saved models table of Fine-tune (next sections), read only once the fold is
  opened, for looking - Details, structure, graph view. Its "Use this save point" buttons are off, and looking changes
  nothing in the configuration.

**Fine-tune** and **Evaluate only** show the saved models table, then **The model in use** - its facts (network,
components, task, reward, conditions, training, restorable, folder), a note when the configuration on the page is too
incomplete to compare it with, and its compatibility - then the Mode's own settings: for Fine-tune, Freeze encoder,
Encoder-only transfer, Reset critic, Continual learning and the name of the model it saves; for Evaluate only,
Actions - Deterministic (the policy's mean action at each step) or Sampled (drawn from the policy, as in training); then
Advanced. They have no block for a new network: a saved model only loads
into the network it was trained with. Since branch record SIF-86 the saved models table scrolls in a box of its own -
60 % of the window's height at most (720 px), its column titles staying at its top - so what follows it is in reach
with hundreds of models (411 made it about 20,000 px long). When the list arrives, the model in use is brought to the
middle of the box if it is out of its view; the box scrolls, never the window.

Pressing the button again focuses the existing window. It has no close button of its own (record 7.163, user: "delete
the cross button in RL network window"): the browser's close keeps all configuration edits; pending settings saves and model compatibility checks continue in the main page. Undo/Redo also
work for typing in the window. Its heading has **Undo** and **Redo** of its own, at the right (branch record SIF-97: every
Mode button, Use template and Use this save point said "One Undo step", and the only Undo was in the main window's editors);
they are the page's one history, as the toolbar's, and Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) work anywhere in the window but in a
text box, which keeps its own undo. The line under the main window's formula bar names what they changed. A blocked popup is explained beside the launcher. Reloading or leaving the workbench closes
its window.

Settings in the window that need attention leave a notice in Run configuration, including its folded warning/error mark. Since
branch record SIF-46 it says the first reason that applies, and its "RL model..." opens the window ("Review the settings in
RL model... - the budget is too small for the network to learn."). Since branch record SIF-86 it opens the window at the
place that says that reason in full, scrolled to the middle with its fold open: the compatibility under The model in use
(or why it could not be checked), the window's message line, the budget warning, the soft actor-critic warning, the
differences from the template, or the template that is unavailable or could not be used. The model line's own
"RL model..." still opens the window at its top.
Browser checks: `frontend/scripts/network_panel_check.mjs`, `model_chooser_check.mjs`, `mode_suggestion_check.mjs`, `model_structure_check.mjs`,
`graph_view_check.mjs`, `pdk_check.mjs`, `module_fold_check.mjs`, `typing_check.mjs` and `reliability_check.mjs`.

### The RL model's label (2026-10-03, record 7.159)

User: "remove the project name box in the Project module. Give the RL model its own label, independent of the project
name." The project name did one thing: the backend remembered each project's newest run, and a Mode that loads a model
(resume, fine_tune, frozen) started from that run's `latest` save by itself. That job is now the **RL model label**'s, a
box in the RL model window since record 7.265 - "Name of the new model" in New model, "Name of the model it saves" in
Fine-tune (until then in Run configuration, below the Mode):
- empty, the label is the task's run label (`project.task_name`, shown as the box's grey placeholder);
- a run that saves an RL model is remembered under its label (`settings.json` `last_run`); a Baseline simulation
  saves none and leaves the label alone (before, a baseline under the same project name pushed its
  project's model out);
- the newest model saved under the label (`GET /api/runs/default-model?label=`) is offered in Fine-tune and Evaluate
  only, "Newest model named ...: Use", and loaded only by that press, at its newest save point, pinned (record 7.265;
  until then a Mode that loads a model took it by itself, at `latest`); runs remembered under a project name before
  still answer through the configuration's unshown old `project.name`;
- the label is written into the run's manifest (`model_label`), names the model in the saved models table (before: the
  task name) and can be typed into its filter; the header's title block shows it; a folded Run configuration shows a
  typed one.

`run.model_label` is part of the configuration; it is hashed as absent while it is empty, so configurations and runs
from before keep their hashes, and it changes no task hash. Tests: `tests/workbench/test_wb_model_label.py`.

**Names of their own, and renaming (2026-10-06, record 7.225).** No two models under one output root carry the same
name. At a start, a label a model carries already gets the first free number - `mscr_ota7t`, `mscr_ota7t (2)`,
`mscr_ota7t (3)` - and the run manifest holds the name given; the label itself stays what the run is remembered under,
so the Modes that load a model still start from the newest model saved under the label. Models saved before this
record are numbered the same way when they are listed, oldest first. The Runs window shows the name in its **Saved
model** column. In a saved model's Details (RL model window) a **Name** box and **Rename** give the model a new name (`POST /api/runs/model/rename`, kept in the run folder's `model_label.json`; the manifest
keeps the name given at the start, and a live run can be renamed too). A name another model under the output folder
carries is refused and said under the box. A renamed model is offered as "Newest model named ..." when its name is
typed into the RL model label box: the default model is the model that carries the label when no run was started under
it.

### Folding the right column's modules (added 2026-09-21, user request)

"Run configuration" and "Output settings" fold into one line with a click on their heading (the "Research
experiments" panel below them already did). Both start open; the choice is kept in this browser. A folded module is
only put out of view, not switched off: its settings stay in force and keep working. Its line says the main values
(Mode, evaluation budget and network; experiment name and the end of the output root), and carries a mark - "warning
inside" or "error inside" - while something in it asks for attention, also when that appears while it is folded.
Browser check: `frontend/scripts/module_fold_check.mjs` (fixtures only; safe against the live backend).

### Choosing which saved model to load (added 2026-09-21, user request; a table since 2026-10-07, record 7.265)

A **run** is one training session (one press of Start) with its own folder; the models it saved are its **save points**
(`checkpoints/<id>/`). A **saved model** is the RL model one run saved. In Fine-tune and Evaluate only, the RL model
window lists the saved models in a table (`SavedModels` in `frontend/src/panels/ModelChooser.tsx`), one row each, the
most recently saved first:
- **Name**: the model's own name (see "The RL model's label");
- **Trained on**: its task, or "multi-task (offline)" for an offline model;
- **Network**, in short (GT 16/2/1; in full on hover), and the **Evaluations** of training behind its newest save point;
- **Save points** and **Last saved**;
- **Started from**: a template, the saved model it was fine-tuned from, or recorded runs (record 7.264);
- **Data** (MOCK or real) and **Restorable** (full state, or weights only).

Every column sorts; the filter finds any word of a row, its folder's name included; folders (All models, Unfiled and
your own, with Move to...) work as in the Tasks and Runs windows and are stored in `model_folders.json` (record 7.263).
Runs without a save point are not listed. Bayesian runs are excluded even when an older version wrote a
save point: their learner was never trained. Selecting such a saved path returns a clear refusal (record 7.325).

**A click only inspects.** **Details** opens under a row, with:
- its **Save points**, newest first: evaluations, time and kind (automatic, Save now, pause, stop, end of the run,
  safety), with the best policy and the newest marked. A click on one selects it for the next part.
- **Name** and **Rename** (record 7.225);
- **With the task on the page and this model's own network**: the selected save point checked against the configuration
  on the page as **Use this save point** would load it, an inspection. The save point is read first, as Use reads it,
  and the check gets the page's task with that model's own network and component list, in Fine-tune or Evaluate only
  (Fine-tune while New model is chosen). Until branch record SIF-85 it got the page's network, so every model of another
  design or size read "NOT compatible ... it cannot be loaded", although Use brings its own network. What a model cannot
  bring - the task's graph, its specs, MOCK or real data - is still checked. The problems come first, a "saved {...} !=
  current {...}" pair shown as the keys whose values differ, and the checks that pass are folded under one line (branch
  record SIF-36);
- **Relationships**: the run that saved it, what it started from, the models trained from it and the runs that loaded
  it - each a link: a model is shown in this table, a run opens the Runs window at it - then its history, folded, oldest
  first, and its folder;
- its **Network structure** and **Circuit graph view** (below), for the selected save point.

**Using one is a press.** **Use this save point** makes exactly that save point the next run's model - a concrete id,
never "latest" - with the model's network and component list, as ONE Undo step, and says so ("The next run fine-tunes
... (one Undo step takes it back)"). A double click on a row uses its newest save point the same way. While the save point
is read, the button pressed says **Using...**; the other Use buttons stay on, and a newer choice wins (record 7.278). The
RL model window then closes (record 7.291; as do "Use the newer one" and the suggested model's Use) - a save point that
cannot be read leaves it open, with the reason: above the saved models, and under that model's save points when its
Details are open (branch record SIF-85). Opened again, the row is marked **in use**, and the model line beside the button names
it. When the run of the model in use has saved a newer
save point, "The model in use has a newer save point: ... Use the newer one" offers it; nothing follows by itself. A
model in use that is no longer listed (outside the output folder, or without a complete save point) is said, with its
folder. Nothing is filled in by itself either: until a save point is used, the window says "No saved model is chosen
yet", and the newest model saved under the RL model label is offered (above). Load run and New run like this in the
Runs window take a saved model the same way, pinned with its network and component list (`frontend/src/savePoint.ts`,
record 7.267).

The list is `GET /api/runs/models`: small metadata files only, read when the table is shown, when a run of the page's run
list changed (a run came or went, came to rest or was renamed), for another output folder, and by **Refresh list** (every
run folder read anew, as in the Runs window) - never on a timer. A working run's newer save points show at Refresh list
or once it rests; the backend reuses what it read of a run that did not change (record 7.274). Older periodic save points
are pruned: `output.keep_last_checkpoints` keeps the newest 10 periodic ones by default, and empty keeps every one. Save
now, pause, stop and final save points, the latest one and a selected best policy are never removed. Models from outside
the workbench (the M6 pilot checkpoints) cannot be chosen, and there is no upload: `training_state.pt` is a pickle and is
only loaded from a trusted local output root.

The model in use is compared again when a contract field changes (including circuit, rows, seed, network,
learning settings, reward or conditions). Editing project labels, output options or the evaluation budget does not
repeat that inspection. Display checksums are reused while the resolved file identity, size and modification/change
timestamps match; `latest` is resolved on each description. Actual model loading always verifies fresh checksums.

**Available encoders (2026-09-26):** Graph Transformer, RGCN and GATv2 (`gatv2`). GATv1 (`gat`) was replaced on this date; old configurations are rejected explicitly and old GAT weights cannot load into GATv2. MLP and GCN were deleted from the optimizer and workbench by user request; port-GNN was removed earlier. An old configuration naming a removed encoder is rejected explicitly. Exact resume of checkpoints saved before this package change needs matching historical optimizer source and dependencies (`9bc488f` for the preceding five-encoder version, `bbdfe36` for the recorded six-encoder physical M6 pilot). Workbench `fine_tune` and `frozen` retain their existing compatibility checks: a source-digest difference is a provenance warning if the retained architecture and all other required contracts match; this does not make deleted encoders loadable. The package changed again since (reward v2 in `1135b8b`, reward v2.1 in `8cf53ae`): the current digest, and which commit loads which older checkpoint, are at the top of `docs/decisions.md`.

**The network comes with the model (2026-09-21, user request; in the same step since record 7.265).** The block that
sets up a NEW network - templates, sizes - is in New model only. A saved model only loads into the network it was
trained with (the backend refuses any other one in `fine_tune`, `frozen` and a legacy `resume`), so **Use this save
point** sets the model's network and component list with it, and the model's facts start with a "Network" row. Only
the network follows; the training numbers under "Advanced" stay yours. A network that arrives from elsewhere while a
model is loaded (an imported or opened configuration, an old draft) is taken back, and the window says so: "The network
stays GATv2 16/2/1: this run loads a saved model ...". Back in New model the saved model chosen is cleared in the same
step, and the template in use is the network that was last in use.

**Every model says its design** (branch `self-improving-frontend`, record SIF-1; user: "show what is each models original
shape design (rgcn or graphgps or circuit gps etc)"). The saved models' table names each model's network design in its
**Design** column - Graph Transformer, RGCN, GATv2, GraphGPS, CircuitGPS v2 or v3 (two different networks, record 7.356),
parameter-group attention - with its size under it ("48/4/4 · RWSE"); the column was "Network", in the encoders' keys
("graph_gps 48/4/4 · rwse"), where CircuitGPS v2 and v3 looked the same. A fine-tuned model keeps the design of the model
it started from. The model's facts, its structure, the notes about its network and Run configuration's model line use the
same names; the short form says GraphGPS, not "GPS".

Using a template loads its remembered settings. A delayed reply or preset reset only changes the configuration
while that choice and its network values are still current; later choices, edits, Undo and imports take precedence.
Preference writes and resets are ordered so an older save cannot overwrite a newer reset (record 7.130).

An existing configuration keeps its explicit network and Advanced values when the page reloads. If they differ from
the template's values, **In use** says **current run settings**, and a comparison table lists each differing
setting with **This run** and **Template** values. The run uses the current values. **Use the template's values**
replaces this run's settings (one Undo step) without writing preferences; **Save into the template** keeps this run's
settings and saves them into that template (branch record SIF-57; the box said "saved defaults" until then). The publication/baseline label is shown as in use only while the values match.

One browser upgrade handles the old starting preset's learning rate (record 7.243): on the first page load after this
fix, a scratch configuration for GT, RGCN or GATv2 that exactly matches the starting preset except for learning rate
`0.0003` takes the preset's `0.001`. The window says what changed, and one Undo restores the previous rate. A browser
marker prevents subsequent reloads from repeating this upgrade, including after Undo or a deliberate edit. Other
custom values, custom saved defaults and modes that load a model keep their rates. Imports or edits made while the
initial settings request is pending take precedence. No backend preference is written; unavailable browser storage
leaves the existing values and comparison intact.

### Network structure of a saved model (added 2026-09-21, user request)

In a saved model's Details (RL model window), the fold-out **Network structure** shows what the network saved at the
selected save point consists of -
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
all five supported encoders; a layer whose gradient is merely zero for the DATA at hand (`binding_ratio` when every ratio is 1)
is used and is not flagged. Browser check: `frontend/scripts/model_structure_check.mjs`.

### Circuit graph view (added 2026-09-21, user decision: one on-screen diagnostic picture)

Record 7.228 adds attention scopes for the two new encoders: **Local port edges**,
**Global node attention** (choose a receiving node), and **Parameter-group attention**
(choose a group). Global/group modes color device/net nodes and show their normalized
weights in a table; they do not add physical connections. The structure table also
explains the new attention and structural-input layers. All of this remains a
read-only replay on an archived state, with policy-output equivalence checked.

**Where it is.** RL model window > a saved model's **Details**, in any Mode (in New model under the folded "Saved
models, to look at"): last in Details are the "Network structure" fold-out and the **Circuit graph view** button, for
the save point selected there. Looking changes nothing about the run (record 7.265; until then the view was under the
chosen model's card, and New model had "Look at a saved model").

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
read. The CHOICE is in the RL model window: in New model, under the template's sizes, **Components** (standard /
every loaded PDK) - a network setting like the encoder; the window says when the chosen PDK is not loaded on this
machine and points to the Virtuoso window. In Fine-tune and Evaluate only the list comes with the saved model, as its
network does ("Use this save point"), and the model's facts gain a "Components" row. Saved as `run.network.vocabulary` =
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
   bridge into a temporary folder OUTSIDE the repository, scanned and deleted. They say what each model is. A copy of
   each is kept in `configs/local/workbench/pdk-model-files/<user@host>/<library>/` (record 7.279; one folder per host
   since record 7.283: the same path on two hosts can carry the same size and time with different files): every cell read and Save task
   read the PDK again, nine downloads and 5.3 MB, 2.5-5 s, for files that do not change. One read-only query asks the
   simulator host for each file's size and modification time, and a file is taken from the copy only when both are
   those recorded when it was downloaded AND the copy still has its SHA-256; anything else is downloaded, as before,
   and so is everything when that query gets no answer.
Empty boxes = the technology library of the connection's design library and the connection's model file. The result is
kept under `configs/local/workbench/pdks/<id>/` (git-ignored): the extracted facts and the files' SHA-256 - never the
PDK files. Every version ever loaded stays in `versions/<sha256>.json`; a run keeps its own copy of the list it was
started with (`network_vocabulary.json`), so loading the PDK again never changes an existing run or model.

**How each fact is decided - by rule, nothing guessed from a name.** A device's family comes from the Spectre
primitive of its model (`bsim4` -> MOS with the card's `type=n|p`, `bjt` -> bipolar `npn|pnp`, `diode`, `resistor`,
`capacitor`, `inductor`); for a wrapping subcircuit from its own element (an `inline subckt`), from the one MOS / bipolar
element it holds, or from what lies between its first two pins (resistive only = resistor; one diode with nothing but
resistance in series = diode, the way some foundry PDKs wrap theirs; an inductor there = inductor, its parallel capacitor and
series resistor being parasitics; a declared resistance / capacitance unit of the cell decides between passive
candidates). A pin's role is the primitive terminal it reaches, directly or through one
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

### Transferable network inputs: any spec list, any PDK (added 2026-10-10, record 7.298)

**In plain words.** Until now the network read the specs through a fixed registry - one place per spec name, so a model
loaded only on a task with the same names - and transistor sizes in micrometres, so what it learned about sizes belonged
to one PDK. **Network inputs: Transferable** (RL model window, New model, above "Nominal device operating points") changes
three things together (`run.network.spec_input` = `set`, `size_features` = `pdk_relative`, `device_model_features` =
true; a configuration file may set them one by one, and the window then shows "Custom"):

1. **Specs as a set.** Every active spec is one item, described by what it measures - its unit; its analysis; the
   signals its probe reads (node voltages, a source's current, the stb loop gain, an xf transfer, noise); how the probe
   reduces them (a value at a point, a crossing, a phase margin, an extreme, a window, an integral, a waveform measure; a
   magnitude, decibels, a root); whether it is a ratio, a difference of two nodes, negated, scaled or offset; WHERE it is
   read - the point (`value(x f)`) or the window (`clip`, `integ`) in frequency or time, as its position (log10 of the point
   or of the window's centre) and its span (log10 of the window's stop over its start), so PSRR read up to 10 kHz and
   above 1 MHz, two noise bands, or the members of a series (the first probe an equation names sets its place) differ;
   whether it comes from the supply or from another source - and by where it stands: its distance to its
   limits in its own scale (the reward's own measure, so a pass and a miss lie clearly apart), the reward's violation,
   pass flags at nominal and at the worst corner, its weight, and its value and limits against a reference per unit. No
   item carries the spec's name. One shared network reads every item and the run's own numbers attend over them, so a
   model reads any spec list and loads on any task built with the same inputs.
2. **Sizes relative to the PDK.** Each MOS width and length is divided by its model's minimum - the smallest bin of the
   PDK's nominal model section (`lmin` / `wmin`), else the cell's CDF default size - so a minimum-length transistor
   reads the same in gpdk045 and in a second foundry's 0.18 um PDK. Other devices keep micrometres.
3. **Device model features.** Four numbers more per MOS device: threshold voltage `vth0`, mobility `u0`, saturation
   velocity `vsat` and oxide thickness `toxe` / `tox` of its model at that smallest bin. They teach the network something
   only once it trains on more than one PDK.

Operating points keep their own switch; a Maestro task now reads them for such a run (last paragraph).

**What does not change.** The reward, the actions, the environment, the replay and every recorded table: everything happens
at the network's input (`network_inputs.NetworkView`, applied in the learner's `batch`, as the PDK component list's view
is), and a viewed state is kept by the replay's own digest, so a learner step views each distinct state once. A
configuration without these settings is what it was: the three are dropped from its hash at their defaults, and its
learner, contract and model are the same.

**Where the descriptions and numbers come from - by rule, nothing guessed from a name.**
- The probes a spec's equation uses; each probe's OCEAN expression parsed into a small tree (`spec_descriptors.py`). An
  expression it cannot read leaves its columns at 0; a built-in analyzer's probe is described by its analysis only.
- The testbench netlist the task was saved with (`structure.scs`): the supply is the source `design.json` declares, else
  the largest ground-referenced DC voltage source (Save task's rule); the AC stimulus is wherever `mag=` is set.
- The PDK's Spectre model library, read from the copy "Load PDK" keeps (`pdk-model-files/`), never from the simulator
  host (`device_models.py`): `library` / `section` / `include ... section=` / `parameters` (also "+" lines) / `model` cards
  and brace bins / `inline subckt` wrappers, in the nominal section `tt`; expressions evaluated with the section's
  parameters, Spectre's `temp` (27 C) and a subckt's implicit `m` (1) by a small arithmetic evaluator - no code is run.
  The numbers are kept beside the record (`pdks/<id>/device_models.json`) and read again when the PDK is loaded again;
  no route returns them and no message shows them (CLAUDE.md: PDK models are never shown).
- Read on 2026-10-10 (counts only): gpdk045 14 of 14 MOS models, all four numbers for its 10 transistor models (its 4 MOS
  capacitors: sizes only); a second foundry's 0.18 um PDK (its name is kept out of the repository) 13 of 25 (its 12 RF models lie outside the nominal section the task's wrapper
  includes). Every model a saved task uses - GPDK045's `g45n1svt`, `g45p1svt`, `g45n2svt`, `g45p2svt` and the second PDK's four transistor models - has
  all four numbers and its minimum size from its bins.

**Checks.** With the spec set, each Specs row's Issues cell says what the network reads ("The network reads cmrr_db as:
dB; ac analysis; reads node voltages, an xf transfer; from another source; a difference of two nodes; a ratio; offset by a
constant; as value at a point, in decibels; at 10 Hz"), and a line under the table says how the set works. Blocked:
sizes or device features with the task's PDK not loaded (`pdk_numbers_unavailable`), relative sizes when a MOS model of
the circuit has no minimum size (`pdk_sizes_missing`), device features when none of its MOS models has the numbers (a
warning under Parameters when only some lack them: those inputs are then missing on those devices), and rehearsal with
these inputs (`rehearsal_with_transfer_inputs`: its pools hold other tasks' states, which would need their own view).
An exact resume refuses a change of these settings, and a run whose task descriptions or PDK numbers changed since it
started (`network_inputs_changed`): Fine-tune from its model. The check rebuilds the run's view as its start made
it, with the run's own component list (record 7.319: until then it left the list out, and so refused every
unchanged run that had the family list or a PDK's list).

**A run's own record**, `network_inputs.json` in its folder: the settings, the spec descriptions, the PDK and its record's
checksum and the view's key - never the device numbers.

**Saved models.** The contract records the spec set (`spec_schema.layout` = `spec-set-v1`, its description columns and
unit table), and the feature schema's version names the inputs (`+pdk-relative-sizes-v1`, `+device-model-features-v1`):
such a model loads on any task and any PDK with the same inputs, and nowhere else (the compatibility list says which
part differs). The RL model window's model facts gain a "Network inputs" row; Fine-tune and Evaluate only take the inputs
with the saved model. The circuit graph view shows the network its view and draws the circuit as recorded: its sizes as
simulated, never a PDK number.

**Operating points of Maestro tasks.** A Maestro-measured task gave none until now. For a run whose network reads them,
every evaluation reads them from the run's own downloaded results, without Virtuoso: Spectre's binary PSF info result
`dcOpInfo.info` (the DC equilibrium), else `finalTimeOP.info` (the end of the transient), with a reader of the binary
format (`psf_binary.py`; results without a sweep only, anything else refused). None of the saved tasks' Maestro tests
saves the DC one (six save only the end-of-transient point, six none at all), so for such a run GATOR adds it to the
deck (`deck_ops.with_dc_operating_point`: Maestro's own `dcOp dc` + `dcOpInfo info what=oppoint where=rawfile`, the info
right after its solve): one short DC solve more per evaluation, every other analysis and output as the test has it; the
run's analysis settings say so, and validation tells it on the Parameters tab (`dc_operating_point_added`).

**Offline pretraining** takes `inputs` in its request (`spec_input`, `size_features`, `device_model_features`; no
operating points - no archive holds them): every source archive is read through its own view, its own specs described
and its own PDK's numbers, and the model trains with those inputs. The qualification's specialist comparison is not
offered for such a pool yet (it would need the pool as the specialists saw it).

**The optimizer package changed for this** (user: "build all this"): `models/inputs.py` gained the spec set input
(`SpecSetSchema`, `spec_set_features`, `GraphBatch.spec_items` / `spec_batch`) and `models/encoders.py` its reader
(`SpecSetReader`: one shared network per item, attention with the run's row as the query, then the run row, that
attention and the items' mean into the context every encoder already took). The slot input is unchanged in behaviour;
the source digest moved from `ad4ddcbe...` to `94e7dd4f...` (with record 7.299's change of the same day; this one alone gives `8f100145...`), so every model saved before still fine-tunes and
evaluates, and an exact resume of one needs its own commit (`docs/decisions.md`).

**Not shown yet:** that these inputs make a general model help on a new PDK or with new spec kinds. That is an
experiment of its own (record 7.298: set against slots from scratch, a held-out spec kind, the AgenticSizing circuits).

### The second build of the network inputs: bench sources, net tags by rule, operating-point ratios (added 2026-10-11, record 7.317)

**In plain words.** The transferable inputs above made the specs and the sizes read the same on every task and PDK.
Three things were still read in a way that did not carry over, and the third choice of **Network inputs**,
**Transferable 2**, changes them together (`run.network.bench_features` = `relative`, `net_roles` = `rule`,
`operating_point_ratios` = true, with the three settings of Transferable; a configuration file may set them one by
one, and the window then shows "Custom"):

1. **The testbench's sources, on scales of their own.** The network always saw the testbench: a task's graph is its
   circuit AND its bench, so the supply, the bias and load sources and the load capacitor are nodes. But every DC value
   went into one column divided by 1, so a 50 uA bias current read as 0.00005 and 10 uA as 0.00001 - invisible beside
   a 1.8 V supply reading 1.03. Now a current source's DC value is read in microamperes in a column of its own
   (`idc`); a voltage source's DC value is also given as a share of the supply (`vrel`: the supply reads 1, a 0.9 V
   common-mode level under a 1.8 V supply 0.5); a source's AC magnitude (`ac`) and the two levels of a step (`ilow`,
   `ihigh` in microamperes; `vlow`, `vhigh` as shares of the supply) are columns; and a DC value the netlist gives as
   a design variable of the test (`dc=il`) is read from the test's variables, unless an analysis sweeps it - by
   its name as written, as Spectre reads it (`BIAS` and `bias` are two variables; record 7.319).
2. **Net tags by one rule.** A task tags its nets when it is saved: ground on every task, the supply on a third of
   them, nothing else - so the same supply net is marked on one task and plain on the next. With `rule` every net is
   tagged from the graph alone, the same way on every task:

   | Tag | A net gets it when |
   |---|---|
   | ground | the task tags it as ground, or it is named `0` or `gnd!` |
   | supply | the supply source drives it |
   | input | a source that carries a signal drives it: an AC magnitude, a waveform (pulse, sine, ...), or two different step levels |
   | output | the probe of an active spec reads its voltage |
   | bias | a DC source other than the supply drives it: a reference, a common-mode level, a bias or load current. A voltage source of 0 V is a probe and tags nothing |

   A net may carry several tags (a supply with the AC stimulus on it is supply and input); every other net is a
   plain one. **The supply** is found by one rule too: among the voltage sources at the top level with one pin on
   ground and a DC value other than 0, the one on a net the task itself tags as the supply; else the one with the
   largest DC value; of equals the one whose net touches the most pins (a supply rail feeds many devices, a reference
   one gate). Nothing is read from a name.
3. **Operating-point ratios.** The four numbers of a transistor's model (threshold voltage, mobility, saturation
   velocity, oxide thickness) are the same for every design of a PDK: with two PDKs they tell the network which PDK it
   is on and little more. With the ratios every MOS device also gets four numbers of the DESIGN, read at its simulated
   operating point: gm/Id, gm/gds, |Vgs| - |Vth| and |Vds|/|Vdsat|. They mean the same in every PDK, and they change
   with every design. The simulator's region comes with them (the optimizer's own operating-point input, its five
   region columns only; all twelve when "Nominal device operating points" is on as well). A run with the ratios reads
   every design's operating point, as a run with the operating points box does: for a Maestro task whose test saves
   none, one short DC solve more per design. A design without an operating point (a failed simulation, a simulator
   that gives none) shows the ratios as missing.

**Which inputs a new model gets (record 7.332; user: "Yes, no box").** The transfer experiment's step 3b (record 7.328)
accepted Transferable 2, so a new model no longer chooses: its encoder's template brings the inputs - Transferable 2 for
the existing encoders, Structured + Transferable 2 for CircuitGPS - and so does choosing New model. The RL model window
shows one line, "Network inputs: Transferable 2 (...)", where the box was. A box is drawn only while a configuration
still holds another choice (a configuration made before, the first build loaded from a file, plain Structured on
CircuitGPS, a custom set): it offers that choice and the encoder's own, nothing else. Standard and Transferable can no
longer be chosen on the page; a configuration file can still name them, and Fine-tune and Evaluate take the inputs from
the saved model as before. A new model on a task whose PDK is not loaded is refused by the check ("load that PDK in the
PDK window"), where Standard used to be one choice away.

**Where it happens.** At the network's input only, as the first build: `network_inputs.NetworkView` shows the network
a view of each observation; the environment, the simulator, the replay and every recorded table keep the circuit as it
was simulated. `bench_of_graph` reads the bench, `ruled_roles` the tags, `spec_descriptors.measured_nets` the nets the
active specs' probes read, `bench_variables` the test's variables. The page's check says per task what the rule found
("Bench sources on their own scales: ...", "Net tags by rule: ..."), with a warning when no supply or no output is
found or a source's value cannot be read.

**A model and its inputs.** The feature schema's version names each of the three (`+bench-features-v1`,
`+net-roles-by-rule-v1`, `+op-ratios-v1`), so a model made with them loads only with them, and a model of the first
build does not load with them; the saved-model facts and the next run's line say "transferable 2". All three are off
by default and left out of a saved configuration while they are (its hashes are unchanged), and a view without them
keeps the key it had, so every earlier run still resumes. Nothing under `src/analog_optimizer/` changed: the optimizer
digest stays as it was.

**Offline training** (`pretrain`): a request's `inputs` take the three settings. For the ratios every source must be a
run that read operating points; one that did not is refused in words, unless the request says
`"missing_operating_points": "mask"` - its designs then show the ratios as missing. A source that read operating
points is no longer refused by a pool that does not use them (it was, until this record). The raw operating-point
input is still not offered to a pool.

**Not changed, on purpose.** What an action means: a position between a parameter row's own limits (CLAUDE.md: the
action semantics are not changed to make a feature easier). Making an action mean the same size on two tasks is done
where the tasks are made - a ported task keeps its ranges as the same multiples of the minimum size - not in the
network. The parameter rows' own inputs (value, lower, upper, step) are unchanged; with sizes relative to the PDK they
already read in multiples of the minimum.

**Not built.** For ngspice tasks on another PDK: that PDK's minimum sizes and model numbers (its model library is not
in Spectre's language, which the reader follows), and a description of a spec whose value comes from a benchmark's own
evaluator. They belong to the parked SKY130 benchmark.

**Not shown yet:** that the second build learns as well as the first from scratch, or carries over better. The
transfer plan's step 3b measures both (`docs/plan-transfer-experiment.md`, section 6.3b).

### Device families: the component list of a new model (added 2026-10-10, record 7.298)

**In plain words.** The network has to know which kind of part each node of the circuit is. The standard list knew eight
kinds (MOS, R, C, L, sources: bipolars and diodes were "unknown"); a PDK's own list knows every part of ONE PDK, under
names no other PDK has. The **device-family list** is one fixed list that every PDK maps into: unknown, nMOS, pMOS, npn,
pnp, diode, varactor, resistor, capacitor, inductor, voltage and current source; pin roles drain, gate, source, bulk,
collector, base, emitter, anode, cathode, positive, negative; parameters w, l, m, nf, r, c, ind, dc and a junction
device's area. A second foundry's nMOS model and GPDK045's `g45n1svt` are both an nMOS, so a model trained with the family list loads with
any PDK, and loading a new PDK never changes the list (the network's first layer holds one entry per kind: a growing
list would break every saved model). What tells variants apart (threshold flavour, 1.8 V or 3.3 V device) is numbers,
not names: the device model features above.

**The list of a new model (user, 2026-10-10: "replace the standard list ... new models only").** In the RL model window,
Components offers the device families first, then each loaded PDK's list; New model (and a template used in it) takes the
families. The standard list is no longer offered to a new model: it is kept to continue the models trained with it -
every model saved before - which Fine-tune and Evaluate only load with their own list, as before. A configuration file
that still starts a new model on the standard list runs, and validation says so (`standard_list_new_model`). The
schema's default stays `standard`, so every configuration and queue written before means what it meant.

**How a component gets its family - by rule, nothing guessed from a name.** From its PDK record (`model_scan.classify_model`,
when the PDK was loaded): the Spectre primitive of its model (bsim -> MOS with its type, bjt -> npn/pnp, diode, resistor,
capacitor, inductor), a wrapping subcircuit's own element, or what lies between its first two pins. Two rules were added
with the list: Spectre's own `resistor` / `capacitor` / `inductor` used without a model take that family, and a subcircuit
whose first two pins are joined only by resistive behavioural sources (`bsource ... r=`, the second PDK's diffusion resistors) is a
resistor (a chain of other behavioural sources counts only when the cell's CDF declares exactly one passive quantity).
The added rules apply when the PDK is loaded again. A part of no PDK keeps its own kind when that is a family (an ideal
source, an analogLib resistor); what no rule can classify is "unknown", and validation names it under Parameters
(`family_list_unknown_parts`). Counted on 2026-10-10: GPDK045 all 54 components (its 10 diodes and 6 bipolars were
"unknown" in the standard list); the second foundry's 0.18 um PDK 67 of 78 as loaded, 74 of 78 once loaded again - the four left are well and
substrate contact cells, connections rather than devices.

**Where it lives.** `families.py` (`FamilyList`: the same contract as a PDK list - name, label, schema `families-v1`,
view); a run keeps its own copy of the mapping its PDK gave at its start (`network_vocabulary.json`); offline pretraining
takes `inputs.vocabulary = "families"` and maps every source archive through its own PDK. Like every list, it changes only
what the network sees: the graph, the actions and the recorded data stay as simulated.

### The ideal parts, read with the PDK (2026-10-05, record 7.190, user request)

**In plain words.** A circuit holds parts that belong to no PDK: voltage and current sources, ideal resistors,
capacitors and inductors, current probes, controlled sources. They come from Cadence's generic library `analogLib`.
Until this record the workbench knew five of them from definitions written by hand into the example circuits' files -
and lost two when the examples were deleted (record 7.187). Now **every read of a PDK also reads analogLib's own
description**: which Spectre component each of its cells netlists as, and with which pins, in which order. A cell read
from Virtuoso is recognized from that, as its PDK components are (user: "it should be recognizing all the loaded
components").

- **What is read.** One more read-only query in the same press (`pdk.IDEAL_SKILL`: one line per cell, nothing opened,
  no parameter read): about a second for the 180 cells of IC23.1's analogLib. It is stored inside the PDK's record
  (`ideal_parts`), so it is read whenever the PDK is: with every cell read in the Virtuoso window, with every Save task,
  and by **Load** in the PDK window. If the query fails, the PDK is read and stored all the same, the reason is shown, and
  what an earlier read brought is kept.
- **What it gives.** 50 Spectre components from those 180 cells, 45 of them with a pin order. Six have a kind of their
  own in the optimizer's standard list - `vsource`, `isource`, `resistor`, `capacitor`, `inductor`, and `iprobe` (read
  as a 0 V source in series) - each with the one value its line carries (`dc`, `r`, `c`, an inductor's `l` as an
  inductance). The other 39 (controlled sources, ports, switches, transmission lines ...) reach the network as
  "unknown" with their pins named, as a PDK's diode does under the standard list: the cell can be saved and run.
- **One component, several pin orders.** `vdc`, `vpulse` and `vsin` netlist a `vsource` with two nodes; `vprbs` and the
  cell called `vsource` itself netlist one with six. Each component keeps every pin order its cells state, and a
  circuit is read with the order that has as many pins as its netlist lines have nodes. Lines of two lengths under one
  component, or of a length no cell states, leave that component unrecognized - said by name - instead of stopping
  the reader.
- **What stays as it was.** A part the project had verified before keeps its definition, pin names included: a current
  source's pins are `p` and `n` in every saved task, whatever the library calls them, and the optimizer's description of
  a circuit holds pin names. All seven saved tasks come out with the very mapping they were saved with. Only a part
  that had no definition takes the library's.
- **Read first.** The PDK - and analogLib with it - is read before the cell's device mapping is built, so a part that
  this very press describes for the first time is recognized at once; it took a second read before.
- **Where you see it.** The line under the Virtuoso window's buttons ("PDK gpdk045 read with the cell: 54 components
  ... and 45 ideal parts of analogLib"), and the **PDK window**: an "Ideal parts" column in the list of loaded PDKs, and
  under a shown PDK how many were read, which have a kind of their own, and a folded list of every component with its
  kind, its pin orders and its cells. A PDK loaded before this record says that its ideal parts were not read.
- **Not read:** generic libraries other than analogLib; a part from one stays unrecognized, and the refusal says so.
  Five components state no pin order (a mutual inductor has no nodes of its own) and stay unrecognized too.

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
as for widths. Where the netlister takes a value from a field the form only computes and the form has a typed field of the
netlist parameter's own name - the second foundry PDK's transistors: Spectre's `m` comes from `simM` (fingers x m), a user types
`m` - the row types that field, and only while the two hold the same number, that is with one finger; with two fingers Save
task says "the PDK computes one from the other" (record 7.300).

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

## A task's Virtuoso side: the cell it works in, saving, the run

### The cell the task flow works in: the user's own copy (2026-09-23, user request) and its Maestro setup

The first part of the task flow the user asked for on 2026-09-21 (cell + testbench -> parameters, probes and specs set
up IN Virtuoso -> read back -> edited anywhere -> "Save task"; until 2026-10-06 the Agent tab's agent could do the setting
up, record 7.226). It lives in the note "Read from Virtuoso"
of the Virtuoso window, under the buttons of a cell read into the workbench, and every step is a button.

**The user's own copy on first read (since 2026-09-23).** Reading a cell does not make a copy. Copy the cell and its
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
Since 2026-10-07, **Save as** on an existing saved task explicitly creates a new task with its own DUT/testbench
copies in the same working library, using `working_copy.make_task_copy` (record 7.246).

Until 2026-09-23 the button **Make a working copy** did this instead: it copied the testbench the cell was read through
and every cell of the same library under it into `<library>_GATOR` - a library the workbench added itself, bound to the
same technology library - and pointed the copied testbench at the copied cells (gated, under the session lock, `cds.lib`
backed up; accepted only when the copy netlisted like the original, every copied cell came from the copy library and the
originals read back unchanged; records under `configs/local/workbench/working_copies/<library>/<cell>/` and
`working_copies/libraries.json`). Tasks saved on such a copy keep running on it: their records name it, their line in the
window says "made by the workbench before 2026-09-23", and nothing migrates them. `working_copy.make` remains for
the tests; Save as uses `make_task_copy`. That operation renames copied cells while retaining device instance names, so every
Parameters row and every probe names the same instance path either way.

A saved task stores its copy's record folder (`copy_target.state_dir` in `profile.json`) as an absolute path into the
settings folder that saved it. Since record 7.137 it is read as the same `<library>/<cell>` (or `_tasks/<task>`) under
the `working_copies` folder of the settings folder in use (`working_copy.state_path`). This matters in two cases:
- A run from a scratch settings folder holding copies of the task files used to write its setup-read logs into the live
  folder.
- After the repository moves, the stored path names the old place.

**Read setup.** One Maestro test, `GATOR`, on the cell's testbench holds what the
simulation needs and measures: the model file (the connection's, section `tt`), the analyses, the outputs (Cadence
calculator expressions on testbench nets and branches) and a spec per output (`>`, `<` or a range), plus design variables
and the instance parameters set to them. A Maestro output is a Probes row with source `ade_output` (the output name in
*source_name*, the expression in *signal*); a Maestro spec is the Specs row whose equation is that one probe. **Save task**
writes the copy and reads it back. **Read setup** ("Changed its
Maestro test yourself?") goes the other way in one press: it shows a one-line summary and takes the outputs and specs into
Probes and Specs (units are suggested from the expression and marked so; a unit or an optimizer setting already chosen on
a row of the same name stays, and a limit - Maestro keeps plain numbers in base units - is converted into that unit; one
Undo reverts it), with what differed folded under it. A test without outputs, or a copy without a Maestro view, takes
nothing and says how the copy gets one. Analyses and variables changed in Maestro are NOT taken over - the next Save task
writes the task's own again; change those in the task file. A spec over several probes, and every optimizer-only field
(scale, weight, hard/soft, keep improving, ranges), stays in the workbench. Nothing is synchronized on its own.
Until 2026-09-22 the block had three buttons, **Read setup**, **Use in editors** and **Write to Virtuoso**; the user
asked for fewer, as the flow has it: Save task writes the copy anyway, and reading now takes over in the same press.

**The helper process a Maestro session leaves behind** (record 7.315, user request 2026-10-11). Reading or writing
the Maestro test, and netlisting it at Save task and before a run, opens the testbench's Maestro setup in a background
session and closes it again. For every such session Virtuoso starts a helper process of its own on its host - a second,
windowless `virtuoso` of 0.3 to 0.5 GB - and the close should end it. Mostly it does, within a second. But some helpers
are never told to end and stay, with their memory, until somebody removes them by hand or Virtuoso exits: of 204 helpers
one Virtuoso started in a day, 12 were still there the next day, and with a second session's they were 14 processes
holding 4.7 GB on a 24 GB simulator machine that ran out of memory twice that day (2026-10-11). So every close is
followed by a look at these helpers, made by Virtuoso itself on its own host. A helper is removed only when Virtuoso has
**no Maestro session and no ADE window open** - then no helper can be in use - and the helper belongs to this Virtuoso
(or to one that no longer runs), was there right after the close and is still there 3 seconds later; one that is ending
by itself is left to end. While you keep a Maestro window open, nothing is looked at and nothing is removed. No other
process is ever touched. What was removed, and how much memory it gave back, is one line in the step's `bridge.log`.
The look cannot fail the read or write it follows: if it cannot be made, nothing is removed and the work goes on. It
costs half a second after a close, three when a helper has to be removed, and it runs only when the workbench closes a
Maestro session - a run started from an older copy of the code does not make it.

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
because what is simulated changed. A net name or a value that is not a voltage is refused before anything is written. A circuit that settles by itself needs none.

**What may be a Maestro variable.** Only values of analogLib's own resistor, capacitor, inductor and sources. A PDK
device derives other values from its parameters or clamps them: on the live GPDK045 a transistor width set to a variable
left the 12 side values the PDK computes from it (as, ad, ps, pd, nrd, nrs, sa, sb, sd, sca, scb, scc) at their old
numbers, which would simulate a different transistor. Transistor sizes therefore keep the verified path of writing the
number through the PDK callbacks - into the copy. A value bound to a variable is remembered when the workbench binds it,
and goes back when the binding is dropped (record 7.141; before, a cell read again while bound got the variable's
name back). A binding from before then whose value is not known is refused in words, never written back as a name.

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

### Saving a task: Save as and the task file (2026-10-07, record 7.246)

The button above the editors is **Save as**. Each press reads the current task list and prompts for a new name,
starting with the original task name plus numbering: `ota` → `ota_2`, then `ota_3`, skipping occupied names.
A numbered copy continues the sequence when its original is still listed. The first save of an unsaved cell uses
its cell name with numbering too. Names use 2–40 lowercase letters, digits and underscores, beginning with a letter;
the suggestion leaves room for its suffix. Invalid or occupied names are explained in the prompt. Cancel writes
nothing. If the task list cannot be read, the error is shown and no save is sent. After a save the backend refused
(a range, the grid, the probes), the next press offers the name chosen for that save, not a numbered one (branch
record SIF-92); another task or cell, or a name now in the list, brings the numbered name back.

On a saved task, the existing `as_new` API creates a separate task at revision 1, with renamed DUT/testbench copies
inside its working library; the source task and its recorded baseline remain unchanged. A first save from a cell
uses the copy the user declared when reading it. The successful new task is selected automatically. The prompt
explains the copy, and the existing save progress includes that step. A frequency retry retains the chosen name:
a ring oscillator's save asks for its rough oscillation frequency under the toolbar, the tab line's Save as off
meanwhile. Enter in the box, or the row's own Save as, saves with it under the chosen name; **Cancel** (or Escape)
ends the question with nothing saved, and the next Save as offers that name again (branch record SIF-92).

**Where.** At the right end of the editors' tab line (Parameters | Probes | Specs), beside **Task file**. An open task
also shows "Task real:<name>, revision N". The former inline **New task name** box is gone: naming happens in the
prompt. Messages, progress and follow-up questions appear under the toolbar. The task file's window applies rows
and extras to the editors; **Save as** stores them as a new task.

The page still keeps its configuration in the browser after edits. Browser-storage failures offer **Retry save**
and **Export JSON**; this is separate from saving a task. Calibration's explicit **Apply and save** still updates
the current task in place, with its existing revision and baseline rules.

**The words that send you to it** (record 7.376, user: "fix things"). The backend's messages kept the button's old name,
"Save task", and some pointed to parts of the page that are gone (the Project column, Read setup and Use in editors,
Source: Registered task). They name what the page shows now: **Save as** to keep rows - a new task, which undoes
nothing of the saved one, so rows older than the saved task no longer warn that saving would undo what was saved since;
**Reload saved values** under "not saved" beside the task's name (record 7.372); a double click on the task in the Tasks
window for its own rows; "From an ngspice netlist..." in the Tasks window. A message that asked for "Save task once" to
bring an older task up to date (no Maestro deck yet, a mapping that still records a fixed value per variable, files
that disagree with the creation record) says to save it as a new task: the only other save is Apply and save. Locks and folders speak
of "a task save". The Save as of "not saved"'s summary says why it cannot start - a save under way, no connection - where
it did nothing.

Editing stays available while a save is in flight. The reply applies normalized parameters only when those rows
have not changed since the press; newer edits stay in the editors and the message says they are not saved yet. A reply
for a task, cell or connection that is no longer selected cannot change the current rows, circuit or save message
(record 7.174).

**While a save runs** (record 7.198, user: "show saving (is it possible to show progress?) and if the backend is saving
dont allow another save task press even after refreshing page"). A save of a Maestro task takes about half a minute,
almost all of it in Virtuoso. A line under the editors' toolbar shows it: a short bar and "Saving real:<name> - step 2
of 4: Virtuoso netlists the Maestro test (12 s; its last save took 34 s)". The steps are the ones the save takes
(`task_saving.TITLES`): Virtuoso writes the Maestro test into the cell and reads it back, netlists it, reads the cell
into the workbench, then the task files are written and checked; a task the workbench measures itself has the last two.
The backend keeps the save that is running (GET `/api/tasks/saving`, memory only), so:
- Save as is disabled while any save runs, and its tooltip says which save it waits for. The page asks when the button
  appears - also after the page is loaded again - and then every second, only while a save runs.
- A second save is refused by the backend while one runs (409 `save_running`), whichever page or tab sends it; the
  page then follows the running one. Delete task is refused for the task being saved.
- A save the page did not send (one sent before the page was loaded again, or from another tab) says how it ended -
  "The save that was running has ended. Saved real:<name>, revision N." or why it failed - and the task list is read
  again. The rows on the page stay as they are; the check says if they differ from the saved task.
- A backend started again during a save forgets it; the page then says the save ended without an answer.
Before, the only sign was a greyed icon (its "Saving..." is screen-reader text since the icon buttons of 7.82), and on
2026-10-05 the user loaded the page again during two saves (record 7.194).

**In-place updates with rows older than the saved task** (record 7.203, user: "yes build it"). Calibration's **Apply and save** and the update API retain this protection. Save as creates a different task and
does not overwrite newer source revisions. The page notes which saved revision its rows came from: when a task's rows are loaded (choosing the task, Reload saved values) and after each Save task. The note is
kept in the browser, so it outlasts a reload of the page. When the task was saved again after that - from another tab,
by another session, or while the page still held older rows - saving the rows here would undo what was saved since:
- Save task asks first, under the toolbar, naming what would be undone ("real:mscr_ldo2_rgcn was saved again after these
  rows were loaded: it is revision 6 now, the rows here are revision 5's. Saving them would undo what was saved since:
  Specs psrr_10k_db: normalization_scale 6 saved, (none) here; ..."), with **Reload saved values** and **Save anyway**.
  The backend refuses such a save before anything is written or read in Virtuoso (409 `saved_task_newer`), so no other
  tab saves over it unasked either; Save anyway sends it again (`replace_newer`).
- While editing, the blocking issue ("Specs differ from the saved task ...") then ends with "These rows are older than
  the saved task ... Press Reload saved values (under "not saved", beside the task's name) to take the saved rows; Save
  as keeps these rows as a new task and leaves the saved one as it is." (record 7.376; until then it said that Save task
  would undo that change, which Save as, a new task, never does).
- Only what was saved since counts, not the user's own edits. Rows exactly like an earlier revision are recognized
  without the page's note too (a page from before this change, rows brought back by Undo); edits on top of an earlier
  revision need the note. The saved revisions are the task's `history/r<N>/task.json`.
This is what happened on 2026-10-05 (record 7.194): the page held the rows of revision 2, the saved task was revision 3.

**What saving does.** It reads from the Probes how the task measures: all Maestro outputs (`ade_output`) = measured
by Maestro; all results of one circuit type (`backend_profile`, e.g. what the testbench brought) = that type - the
ring oscillator or the op-amp, measured by the workbench as before. Mixed probes, or probes that fit both types, are
refused in plain words. Saving first performs these preparation steps:
1. a task measured by Maestro writes its outputs, specs (from the rows) and analyses, variables and bindings (from a task
   file applied on the page, else as the copy was last written -
   by the last save) into its working copy and reads them back - they must match;
2. the working copy is read into the workbench again (netlist export + CDF readback, read-only): the reference every run
   of the task is compared with;
3. the task's files are generated from that copy (the same generator Create profile used, with its checks), next to
   `task.json` in `configs/local/workbench/profiles/<name>/`, and the task is registered as `real:<name>`.
4. a new task starts its fixed one-evaluation baseline automatically; an in-place update that invalidates its reference
   also starts a replacement (record 7.248). A specs-only update retaining the reference simulates nothing.

The ring oscillator's measurement needs a rough expected frequency (it sizes the transient): the first save asks for it
once, in one line under the buttons; the task file keeps it. The task's files name the cell the flow works in (the copy
you declared, or the made copy of an older task), so the real run adapter opens that cell - never a cell you did not
declare or copy.

**Saving again.** The main button always prompts for a new task. **Apply and save** and explicit API updates keep
making the current task's next revision: previous revisions remain in `history/r<N>/`, with the previous folder
under `profiles/.deleted/`. Those updates preserve a baseline only while parameters, probes, measurement, analyses,
variables, bindings, initial conditions and model files (including their corner sections) are unchanged; specs-only
and notes-only changes keep it. A model-file or corner change archives the old reference with its revision and
invalidates the current baseline (record 7.321). A new task from Save as starts its own baseline automatically.
This restores Save as to the page by the user's request, superseding its removal in 7.72.

**The task file.** One readable JSON file: the cell, the copy, the measurement, the Maestro part, the Parameters /
Probes / Specs rows and notes, with a `_help` part that explains every part (JSON has no comments). **Task file** opens
the file of the CURRENT editors in a window of its own (opened within the press; a blocked pop-up is said, and the next
press tries again; a window already open is brought forward with its draft). The window shows the `_help` part as a list
over the text, **What each part is** (open; each part's name in bold, its lines hanging in under it), and the text without
that part, every number as the backend wrote it (branch record SIF-81); **Apply to editors** checks every row with the editors' schema
and fills the editors (one Undo step) - a broken file is refused with its problems and changes nothing. What the file
adds beside the rows (analyses, variables, bindings, the rough frequency, notes) is sent with the next save; "Applied"
says so, and that Undo takes back the rows only. Until a save sends them, a line under the toolbar names the parts an
Apply changed: "From the task file, not saved yet: Maestro analyses, notes. Save as stores them; a reload or another task
drops them." (branch record SIF-93). The file is the editors' rows of the moment it was read: when they change in the
editors after that, the window says "The editors changed since this file was read: Apply replaces those changes too",
**Apply to editors** takes two presses (the first turns it into **Apply anyway**), and **Read again from the editors**
reads the file of the editors as they are now - asking first, in the window, when changes typed there are not applied.
Nothing is saved or written to Virtuoso from the window. A close - its Close, the window's X, the banner's **Close all** -
keeps a draft not applied (branch record SIF-87; it used to go with no question): the next **Task file** press reads the
file again and lays the draft over it, with the line "Your changes from before are kept, not applied yet. Revert drops
them." **Revert** goes back to the file as read then. A draft applied or reverted is not kept, and another task or cell
drops it. A kept draft still holds the rows it was typed over: changed in the editors while the window was closed, the
window says so as above (review of SIF-93).

**Running a task measured by Maestro:** see "Running a task measured by Maestro" below - Save task also has Maestro
netlist the task's test once. A Maestro-measured task saved before that part is listed as not runnable until it is saved
once more. Tasks saved before this part (Create profile) have no working copy; they still run on the original cell, and
Save task refuses them with the way forward.

Tests: `tests/workbench/test_wb_task_save.py` (fake bridge processes, the recorded ring-oscillator export). Browser
check: `frontend/scripts/task_save_check.mjs` (hermetic; the task file window, Apply, numbered Save as, cancellation, invalid/duplicate names, and in-place calibration updates);
`virtuoso_source_check.mjs`, `project_help_check.mjs` and `testbench_probes_check.mjs` follow the window.

### The check before every run: editors, saved task and working copy agree (added 2026-09-22, user request)

The fourth part of the flow. A run runs exactly one saved task on its working copy, so before any costed simulation
three things must say the same thing:

1. **The editors and the saved task.** The rows of Parameters, Probes and Specs must be the rows of the task file,
   compared as the schema reads them (a field shown with its default equals one left out). This is offline: static
   validation says it while you edit - a blocking issue `task_not_saved` per editor that differs, naming the rows and
   fields ("Specs differ from the saved task real:ring_osc (revision 1): osc_frequency_hz: lower 1.3e+09 here, 1.1e+09
   saved") - so Start is not offered until **Save task** stores them (it keeps the recorded baseline when
   only specs or notes changed) or **Reload saved values** takes the saved rows back. A resume runs the run's own
   saved rows and is not compared.
2. **The saved task and its working copy in Virtuoso.** The run adapter does everything a real evaluation does before
   Spectre starts, and nothing after: it connects (the creation record matches, no ADE/Maestro window is open on the copy,
   the copy still has the recorded sizes), Virtuoso exports the testbench netlist, the export is compared with the saved
   one - topology and every parameter - and the simulation deck is written. Read-only; it takes the project's Virtuoso
   session lock like a run.
3. **A task measured by Maestro: its Maestro test.** The copy's test is read back and compared with the task file's
   `maestro` part (outputs, specs, analyses, variables, bindings, simulator mode). Its deck is Maestro's own deck around
   the export (see "Running a task measured by Maestro"); the deck step writes it.

**Start, Calibration and Resume** run parts 2 and 3 by themselves, right after the connection gate and
before anything is created (`runs.prepare_run`). A difference starts nothing: the banner under the header lists each step
- passed / FAILED, what differs, and what to do (for example "The working copy was changed in Virtuoso after the task was
saved: undo the change in Virtuoso, or press Save as to make a new task from the copy as it is now", or which ADE/Maestro windows to
close). A passed check is kept in the run's manifest (`consistency_check`, for a resume in its segment).

**Check now** (on the editors' tab line since record 7.362, before Save task; its tooltip says what it compares; until then
in the task's block, where "Check against Virtuoso" was - that button and its route are gone: it was part 2 alone) runs all
three parts on its own; its result stands under the editors' toolbar: free, read-only, no simulation. Its result goes as soon as a row changes.
Without a connection it compares the rows and says the rest needs one.

**A size the optimizer's grid does not hold as a start** (record 7.333). A run starts from the circuit as it stands,
and the optimizer first compares what the cell holds with what its own size grid makes of it. That grid is counted in
steps from a row's lower bound, and for some bounds the count comes out one short: 13.75 to 137.5 um in 5 nm steps ends
at 137.495 um, not at 137.5 um (34 of the 842 stepped rows of the tasks saved on 2026-10-12 are of this kind). The
search loses one step at the top of such a row and nothing else - but a cell that sits exactly ON such a bound differs
from its own start design, and every run of the task, its baseline first, was refused with "Initial backend parameters
differ from the reference graph". The workbench now says it in words wherever the rows are compiled against the circuit
- the validation marks the row (`start_off_grid`), Save task refuses before anything is written, Start and Check now
say the same: "w_pass: the circuit has 137.5 um on DUT/MP.w, which is this row's upper bound, but the optimizer's grid
for the row (5 nm steps from 13.75 um) ends at 137.495 um, one step under that bound. A run starts from the circuit as
it stands and would be refused: set this size to 137.495 um in the cell, or move the bound." The count itself is the
optimizer package's and is unchanged (its source digest); the check asks the package's own legalization, so it says
exactly what a run would do.

**When another real run holds Virtuoso** (record 7.207). Only one process works in a Virtuoso session at a time, and
one on a cell: every real run, Corner check and check takes the run adapter's session lock (`session.lock` in the folder
"Adapter state"; a second Virtuoso session has its own, and every cell has one - record 7.311). When one of them is
taken, the check reads nothing from Virtuoso and says so in one step, "Another real run is using Virtuoso": who holds
the lock (a run started from a workbench page, from a command line, a Corner check, or another check; its process
number, start time and command line, read from `/proc/locks` without taking the lock) and that nothing in the task needs
changing - check again when that run has ended. A Start, Baseline simulation or Resume is refused with the same words.
Before 7.207 this read "The run adapter could not use the working copy ... BlockingIOError" with the advice for a changed
copy (press Save task), which was wrong: a run started from a command line or another session is not shown on the page.

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
task - Start, Baseline simulation, the optimizer writing transistor widths into the copy through the PDK
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
  in base units (Hz, V, A), what the compiled specs compare with. After the last output the measurement lets the folder's
  results go with `ocnResetResults()` (record 7.294): every folder opened stayed in Virtuoso's memory, about 260 KB per
  evaluation (76.5 MB over 300 folders, nothing given back by `gc()`; Virtuoso had reached 10.2 GB after a day of runs).
  With the reset the same test grew it by nothing and measured faster (35 ms against 50 ms), the values identical on
  20 folders. That reset frees the waveforms, not the folder: OCEAN kept every result folder it had opened, and a run
  opens a new one per design. Measured on 2026-10-11 on folders earlier runs had left (record 7.316): 284 KB per design
  on the flip-flop's one transient and 475 KB on a folded-cascode amplifier's six analyses, steady over 300 new folders
  each, nothing for a folder opened a second time - the growth that took a Virtuoso from 0.5 to 12.8 GB in a day of
  runs. The measurement therefore closes the folder as its last step (`closeResults(dir)`, after the values are read and
  inside `errset`): 1 and 6 KB per design, every value identical on 280 folders of three circuits, 1 to 15 ms a design.
  Writing sizes (open, PDK callbacks, check, save), the whole-cell read and the netlisting were measured the same way
  and do not grow Virtuoso.
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

### Offline archive pretraining (2026-10-06, record 7.233)

Since record 7.298 a request may train with the transferable network inputs (`inputs`), each source read through
its own view: see "Transferable network inputs". Since record 7.317 `inputs` also takes the second build's three
settings, and a source that read operating points is accepted (for the operating-point ratios every source must have
read them, or the request says `"missing_operating_points": "mask"`): see "The second build of the network inputs".

Since record 7.319 a pool with these inputs pins what each source was shown. A source is read through a view made
from what is loaded when the pool is built - its PDK's device numbers and family mapping, its task's spec
descriptions and test variables - which the request's archive checksums do not cover. Every source's entry in
`pool.json` now carries `inputs_sha256`, the key of that view, so two builds that showed different inputs have
different audits. A request may pin it per source, beside `archive_sha256` (`pretrain.inputs_identity(run_dir,
inputs)` gives it, as does an `--audit-only` run), and is then refused once the view is another: "Network inputs
changed after selection" (the PDK was loaded again, or the task was saved again). `offline_diagnostics.qualify`
compares the frozen audit with the pool it rebuilds. A pool without these inputs has no such field. A published
model keeps the component list it was built with, as a run does (`network_vocabulary.json`, and
`architecture.vocabulary` in its manifest): the model window then names a family-list model as one, where it had
said "standard" and the compatibility check then refused the model. A folder published before is read from its
save point's own contract.

`python -m gator_workbench.cli pretrain REQUEST.json --output NEW_DIRECTORY` audits an explicitly pinned set of
archives and trains the existing SAC learner without a simulator. `--audit-only` writes the pool inventory, shared
registry and deterministic episode split without updating a network. The JSON request contains `origin`, `runs`
(`run_dir`, `archive_sha256`), `reference_overrides`, optional `relabel_upper` by task/metric (one more copy of each design of
the task under other upper limits) or `relabel_targets` by task (record 7.312: a list of target sets, each
`{metric: {"lower": x, "upper": y}}`; one more copy per set, re-scored under its limits - the multi-target models; a
row whose Scale box is empty gets the size of its new limit, a scale the task states stays, read from the source's own
configuration since record 7.322), `seed`,
`holdout_fraction`, `model`, `sac` (gamma 0), `updates`, `batch_size` and `checkpoint_every`.
Training and publication share the omitted-field defaults: seed 0 and 20,000 updates (record 7.325).
Publication resolves these defaults without rewriting the saved request or changing its identity hash.

Since record 7.336, `pool_storage: disk` stores validated transitions with the recording codec and checksums in
SQLite, retaining only a bounded cache of reconstructed objects. Episode splits, task-balanced samples and SAC
updates match the default in-memory pool. `migrate_reward_settings` explicitly supplies a common `RewardSettings`
configuration for mixed historical sources: first validate the recorded reward, then rescore a derived copy of
both observations and the transition. The audit records original settings and migrated counts; source archives
remain unchanged. Omission retains the strict rejection of mixed reward settings.
`sampling.json` records actual per-task/per-run draws, unique training-candidate coverage and candidate counts so
matched archive trainings can verify that they consumed the same samples.

Since record 7.340, preparation writes its current phase to `status.json`: `loading_sources` counts completed
archives, `validating_pool` counts transitions whose two observations passed the shared-schema check, and
`saving_pool` identifies audit publication. Validation reports at least every 1,000 completed transitions or after
30 seconds at the next completed transition, plus its start and finish. These counters are persisted even without
a CLI log callback. The initial and later checkpoint evaluations announce `evaluating_validation` with the current
update count and held-out row count before evaluating; zero updates still means no weight update has occurred.
Already running jobs using a frozen runtime retain their original logging until a separately authorized new run.

Record 7.341 fixes CircuitGPS's recursive tree amplification as architecture version 2: normalize each base and
combined parent state, retaining the existing learned root normalization. Version 1 remains explicit for historical
inference. The authorized Round 3 recovery uses a separate frozen runtime and an audited migration from the saved
10,000-update state; the generic pretrain CLI and strict checkpoint loader are unchanged. Saved weights, all optimizer
states, temperature and RNG state are retained; the original sampler position is reconstructed and checked against
its candidate ledger. The existing SQLite pool is read-only. Recovery checkpoints are saved every 500 updates, with
full held-out evaluation at the final budget and numerical guards on actor/critic LayerNorm inputs. The planned recovered
model is labelled 10,000 v1 updates plus 10,000 v2 updates. See `docs/circuit-gps.md` and the Round 3 plan record.

Record 7.342 supersedes that continuation at the user's request. The separate `circuitgps-v2-fresh/` experiment
starts at update zero with new seed-0 weights, empty optimizer states and reset temperature/sampler, using the same
read-only validated data and fixed runtime. It preserves the failed run and stopped recovery, and retains the
completed GraphGPS model. Initial/10,000/20,000 checkpoints support full held-out diagnostics; routine checkpoints
every 500 updates preserve offline sampler state. The RGCN queue now requires the fresh run, v2 and zero legacy
updates, in addition to completion, reload/proposal review and publication. These are experiment-local scripts;
the generic CLI, strict loader and optimizer digest are unchanged by this restart.

Sources remain read-only. Mixed origins, reward settings, conflicting units, duplicate runs/candidates, changed
archives and non-reproducible rewards fail explicitly. The first version accepts standard features without OP and
nominal-only data. Whole episodes are split before relabelling; original/derived samples stay together. Training
draws tasks equally across shuffled cycles. Outputs are `request.json`, `pool.json`, `spec_registry.json`,
`status.json`, `validation.json` and integrity-checked checkpoints. Synthetic output must live beneath `mock/`.

These training artifacts are provisional: `trained_unqualified` means the configured offline updates finished.
`offline_diagnostics.qualify` records per-task general/specialist critic error, deterministic actor proposals and the
validation curve review inputs. Specialists may overlap the source holdout; their errors are descriptive references.
`offline_publish.publish` requires an explicit recorded review and writes a separate model-only run. The chooser can
load its weights for fine_tune/frozen; online Continue cannot resume the offline sampler. Its target cost is zero,
while `modes.source_cost` includes every distinct source archive's evaluations once (record 7.234). Empty evaluation
tables are supported by the run list, status and Training tab. Checkpoints declare weights-only transfer capability.
An optional explicit `spec_registry` lets an own-circuit control use exactly the general model's slots.
The general-network experiment's source request and progress are in
`artifacts/general-network-20261006/`; its baseline gates and launch budget are in `docs/plan-general-network.md`.

`rehearsal.build_snapshot` freezes a bounded selection from that pool's **training** partition, including its original
LDO relabel decisions, in checksummed compressed JSON using the recording codec. `run.rehearsal` takes a
`pool_manifest`, its `pool_sha256`, and `fraction` (default 0.5). Only fine_tune and its resume accept it. Runtime checks
origin, reward, registry, data checksum, training membership and capacity before opening simulator lanes. Each update
borrows target transitions from the ordinary replay and appends task-balanced source draws. Source transitions never
enter target replay or the launch ledger. Checkpoints retain the source sampler's RNG, pending task cycle and counts;
resume requires the same pool. Absent rehearsal preserves old configuration and learner-contract hashes.

## The Agent window: Claude Code or Codex in a window of its own (2026-10-06, record 7.226; 2026-10-07, record 7.253)

There is no Agent tab view since 2026-10-07 (record 7.253, user: "make the agent tab pop out window only (no tab view)",
then "make it still a tab style but not button style"): **Agent...**, first in the bottom panel's tab line and still drawn
as a tab (never the active one; underlined while its window is open), opens the Agent window instead of showing anything
in the panel. The window holds, on one line, the folder the CLIs open in, **Claude Code**, **Codex** and, at the right end, **What's
missing?**; under it one headline (how Claude Code and Codex start, and that "What's missing?" asks no agent and runs no
simulation; branch record SIF-81) and one closed line, "What to ask it"; and under those, once asked for, the start
checklist. Opening the window asks the backend which CLIs are installed (free) and nothing else; the page itself never
asks about agents. Pressed while the window is open, **Agent...** brings it to the front and looks for the CLIs again; a
reload of the page closes the window, and one opened anew starts clean. The line itself is record 7.226's (user: "rewrite
the whole agent tab to minimal. Have two buttons to open claude code cli or codex cli in local shell targeting the current
workbench working directory with the permission of a usual agent launch"), when it was the first bottom tab.

**A press opens the CLI in a terminal window of its own, in the workbench's folder** (the repository the backend serves,
where CLAUDE.md and the docs are). The CLI starts as you would start it yourself: the workbench passes no permission
option, no settings file, no model and no prompt, so what it may do is what your own settings say (Claude Code:
`~/.claude/settings.json` and the folder's `.claude/`; Codex: `config.toml` in its home), it is signed in with your own
account, and the session is in your history like any other. The workbench sends it nothing, reads nothing it says and does
not wait for it. Describe what you need there: "the run shown in the workbench is stuck on the gain spec: look at its
designs and suggest what to change", "draft the Specs rows from these requirements". Claude Code reads the project's
rules (CLAUDE.md) by itself; tell Codex to read CLAUDE.md first.

How (`src/gator_workbench/agent_cli.py`, routes `GET /api/agent/clis`, `POST /api/agent/open` with `{cli}` only):
- **Claude Code** is the `claude` on the backend's PATH, else the standalone install `~/.local/bin/claude`; its home is
  `~/.claude`, so `claude --resume` in the folder lists the session.
- **Codex** is a `codex` on the PATH, else the newest Linux build the Codex desktop app ships for its WSL agent
  (`<home>/bin/wsl/<build>/codex`). The start sets the environment that app gives its own WSL agent: `CODEX_HOME` = the
  Windows user's `.codex` (sign-in, `config.toml`, sessions) and `CODEX_SQLITE_HOME` = `~/.codex/sqlite`, with the app's
  build folders first on the PATH (one holds the `rg` Codex searches with) - so the session is in the app's history. A
  `$CODEX_HOME` the backend has wins.
- The backend writes a short start script to `~/.local/state/gator/agent-cli/<cli>.sh` (into the folder, the CLI exactly
  as typed, then your own login shell, so the window stays open when the CLI ends) and opens a window for it: from WSL
  Windows Terminal (`wt.exe -w new new-tab --title ... wsl.exe -d <distro> -- bash -l <script>`), else a console through
  PowerShell's Start-Process, else a Linux desktop's terminal. The window owns nothing of the backend: its own session, no
  inherited streams, and no variable of the backend travels into it (from WSL `WSLENV` is emptied; on a Linux desktop the
  markers a Claude Code session sets for its children are taken out), so stopping the server leaves the CLI running.
  Windows programs start through the WSL interop socket the server inherited; a server that outlived the session that
  started it uses the distro's own socket (`/run/WSL/1_interop`) instead.
- A CLI that is not installed is a disabled button with the reason; a window that cannot be opened says why, with the
  command to type in a terminal of your own (and Copy).
- `GATOR_AGENT_CLI_LAUNCH=off` makes every launch a dry run that says what it would open and writes nothing: the test suite
  (`tests/conftest.py`) and the browser checks' backends (`run_checks.sh`) set it, so no test opens a window.

What went with the tab's own agent on 2026-10-06 (records 7.6-7.186 built it): the conversation and its window, the
provider, model and effort lists, the live answer, proposals with diff and approval, "Review settings" (with publications
online), "Review results", the export and import of a task description, the kinds `virtuoso_setup` ("Ask the agent to set
up" in the Virtuoso window) and `virtuoso_work` (the agent's own Virtuoso tools, `agent_tools.py`), and the editors' "Draft
with agent..." and "Modify selected with agent...". Every one of them was a request to the in-tab agent; the CLIs do the same
from a description, with the access your own settings give them. The saved `agent` block in `settings.json` is no longer
read. Two pieces other functions use moved: the row diff (`diffs.py`, Matched devices, Import JSON, rows not saved) and the
circuit summary (`circuit_summary.py`, the circuit panel).

### What is missing before the run can start

"What's missing?" is answered by the backend, free: no agent, nothing probed (`readiness.py`, `POST /api/agent/readiness`).
It fills the lower part of the Agent window with the verdict ("Nothing blocks a start", or how many items block it and which
is next) and the list, in the order a start is gated: circuit, Parameters, Probes, Specs (the three editor tabs, in tab order), other
blocking issues, run configuration, output folder and - for a real circuit - the connection (the LAST test result; it does
not test again) and the budget authorization that only you can give. Each line says whose step it is ("yours", or "an agent
can help" for the three tables) and what to do; for the tables that includes Reload saved values for a saved task and that
Claude Code or Codex (the Agent window) can draft the rows from your description. It is worked out when the button is
pressed, from the configuration on the page, and never by itself: press it again after a change (it fills the list anew; a
window opened anew starts without it).

Rows that are there but differ from the saved task - an edit, an applied calibration, an older page - are your press: the
line gives the issue whole, its last sentence included (Save task, or Reload saved values), and says where the two buttons
are (record 7.204). For a verified real circuit the optimized variables are not a choice: the profile fixes them, and the
checklist reports any other set as missing, since the run would be refused the moment it starts.

## What the frontend audit changed (2026-09-30, record 7.125)

The user chose all four groups of `artifacts/local/reviews/frontend-audit-2026-09-30.md`. What a user notices (the Agent
tab's conversation, the AI threads and the AI sizing settings named here went on 2026-10-06, record 7.226):

* **A real run is never authorized with MOCK wording.** When the backend says a run is real although the page still
  took it for MOCK (a task chosen a moment before its circuit was read), the question is built from the backend's own
  report: "This runs REAL simulations of real:<task> ... Authorize a total budget of N candidate evaluations?".
* **Undo while typing:** keys typed into one field less than 1.5 s apart are one Undo step (user choice); leaving the
  field ends it, and a change that was not typed there - a button, an applied proposal, rows read from Virtuoso - is a
  step of its own even while the field has focus (7.131). An edit made less than 0.8 s before the page is closed or
  reloaded is saved - unless another tab stored the configuration meanwhile. Configuration and Undo/Redo history
  now move together in a pure reducer, including under development StrictMode (7.174).
* **The Agent tab keeps its message box** while an AI run's thread is shown (the thread scrolls in a row of its own).
* **Import JSON:** only a file this workbench exported replaces the whole configuration; other files are rows for the
  open tab (every row with its ID) or are refused in words. The confirmation shows Apply / Cancel first and scrolls.
* **The first Save task of a cell** lives with the circuit panel (`Left.tsx`): closing the Virtuoso window keeps Save task, Task
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
`api/context.py` shares input/output authorization, configuration loading and the start checklist; `api/support.py`
shares response helpers. The agent module (`api/agent_routes.py`) has three routes since 2026-10-06: the CLIs found, a CLI
opened (`agent_cli.py`) and the checklist (`readiness.py`).
The page's task loads (`support.load_runtime`: validation, the task, Matched devices, the saved-model check, the checklist)
go through `tasks.load_task_view`, which keeps a saved task (`real:<name>`) while its folder, its files, the connection
file and the conditions file are unchanged; the link is checked at every call. A run, the corner check and the command
line load it from the files (7.131).
The legacy copy route still refuses copying; Save-as remains a supported backend request.

The backend by module since the refactoring of 2026-10-09 (`docs/plan-refactoring.md` Groups A and B; routes, answers,
files and messages unchanged, old names kept): `runs.py` keeps a run's start, resume and status and passes on what moved
out of it - the run list and what it reads from a run folder (`run_index.py`), the remembered settings
(`settings_store.py`), the run lock (`run_lock.py`), the definitions other modules need without the engine
(`run_definitions.py`), an experiment's registry (`experiments.py`); `engine.py`'s `RunEngine` takes the simulator host's
side, the committed rows and the raw-output retention from the mixins in `engine_host.py`, `engine_rows.py` and
`engine_retention.py`. `tasks.py` passes on the registered tasks' facts (`task_registry.py`); `profiles.py` the profile
store (`profile_store.py`), a configuration's rows against its saved task (`saved_rows.py`), the saved tasks around a cell
(`saved_tasks.py`), the circuit types (`circuit_types.py`), profile generation (`profile_generate.py`), a task's real
baseline (`baseline_reference.py`) and Save task (`task_save.py`); `pdk.py` the CDF text (`cdf_text.py`), the model files
(`model_scan.py`), a PDK's record (`pdk_record.py`), the network's component list (`vocabulary.py`) and the reads out of
Virtuoso (`pdk_remote.py`); `api/task_baseline.py` is the automatic baseline (it calls `start_run`). A module imports
others at its top; an import inside a function says why in a comment, only three small import cycles remain, and only
`api/` and the command line import the API (`tests/workbench/test_wb_structure.py`, which also refuses a test patching
a name its module does not define or only keeps as an alias, and a test importing a `conftest`: pytest names every
`conftest.py` `conftest`, so the import reaches whichever was loaded last, record 7.297). Constants several modules
share are in `names.py`; the quiet JSON reads in `storage/atomic.py` (`read_json_quiet`, `read_dict`); every cache a
process keeps for its lifetime registers in `caches.py`, whose `clear_all()` empties them all
(`tests/workbench/test_wb_caches.py`).

The follow-up refactor of 2026-10-12 (record 7.324) keeps the scheduler in `engine.py` and puts its lifecycle
operations in `engine_preparation.py`, `engine_recovery.py`, `engine_commit.py` and `engine_finalization.py`.
They receive the scheduler's context explicitly; existing method hooks still call them, and the scheduler keeps the
order of dispatch, learning, saves and retention. `model_inputs.py` composes the shared feature schema and learner
input keywords, chooses and records vocabulary metadata, and resolves offline request/source input views. Online
runs, resume, offline pools and publication retain their distinct policies. `network_inputs.py` still implements the
observation view. `ngspice_netlist.py` keeps graph construction and the existing import names; `ngspice_syntax.py`
holds tokens and expressions, `ngspice_results.py` measurement/result reading, and `ngspice_writer.py` deck writing.
`simulation_artifacts.py` names the verified export, attempt's result directory and working deck, and types the
engine's retention decisions without changing their stored dictionaries. Dependency guards in `test_wb_structure.py`
keep these helpers below their consumers. The optimizer source digest and pinned research files are unchanged.

The optimizer package by module since its clean-up of 2026-10-09 (`docs/plan-refactoring.md` section 6, record 7.292; every
public name still where it was, every message kept): `backends/virtuoso_bridge.py` keeps the adapter and passes on its
generic helpers (`backends/common.py`: a file's digest, `write_json`, `parameter_rows`; `backends/delegation.py`;
`backends/spectre_deck.py`); the MOCK, synthetic and the workbench's ngspice backends share `LocalConnection` and
`HeldParameters` (`backends/backend.py`); `recording/store.py`'s `ExperimentStore` is made of `store_evaluations.py`,
`store_states.py`, `store_summary.py` and `store_workspaces.py`; `training/collect.py` holds the warm-up's random
proposal and a timed update for every collector, the workbench's engine included; `measurements/spectre_job.py` the
measurement readers' reading of a job folder. `CircuitSizingEnv._evaluate` reads as `_begin_candidate`,
`_candidate_output`, `_export_candidate`, `_run_conditions` and `_outcome`, and the workbench's lanes continue an
episode, start a calibration design and retry through the environment's `continue_from`, `independent_episode` and
`retry` instead of writing its private attributes.

The frontend keeps the Agent window and its "Agent..." button in `panels/Agent.tsx` and the run tabs in `panels/RunTabs.tsx`.
`CircuitBrowser.tsx` owns the Virtuoso browsing chain and circuit details; `Left.tsx` coordinates task selection, with
its jobs in `taskChoice.ts` (choosing a registered task), `taskActions.ts` (Check now, Delete task), `testbenchProbes.ts`
and `taskRows.ts`, and the Virtuoso window in `VirtuosoWindow.tsx`. Shared async actions and stale-response handling live
in `requests.ts` (`useRequest`, `usePolling`, `useAsyncAction`); `store.ts` is the module the page and the browser
checks' source fixtures import, and passes on what `requests.ts`, `history.ts` (the configuration and its Undo),
`migrations.ts` and `windows.ts` (the pop-up windows' typing and visibility) hold. Ordinary advanced numeric fields use
one descriptor list and defaults from the backend schema; byte units and checkpoint intervals retain their
specialized controls. The save point interval's default is 200 evaluations and the data tables are written every 64
(record 7.280; 50 and 16 before): once per browser, a draft that still holds an old default exactly gets the new one,
as one Undo step, and says so. The Training tab stays mounted when another tab is selected (its charts survive a look at another tab).

The frontend by file since the refactoring of 2026-10-09 (`docs/plan-refactoring.md` Group C; the page, its requests and
its storage unchanged): `App.tsx` keeps `App` and `Page`, and Page's state lives in hooks of its own, called where Page
held it - in `page/` (`useCalibrationOffer`, `useRunWindowActions`, `useRunList` and `useShownRun`, `useLiveRunAdoption`,
`useTaskRunFollow`) and in `launch.ts` (`useLaunchActions` beside `useLauncher`); the bottom strip is
`panels/BottomPanel.tsx`. The right column is `Right.tsx` with its form pieces in `fields.tsx`, `OutputPanel.tsx`,
`ResearchPanel.tsx`, and the RL model window: `useRlModel.ts` (its state, which stays while the window is closed),
`RunConfiguration.tsx`, `RewardConditions.tsx`, `RlModelWindow.tsx` and `rlModelText.ts` (its words). The editors are
`Editors.tsx` with `editorRules.ts`, `cells.tsx`, `FormulaBar.tsx` and `DiffView.tsx`. The Training tab's numbers are
`trainingData.ts`, which passes on its parts in `panels/training/` (store, series, prep, catalog, build, compare, keys,
imported with their `.ts` suffix so that Node runs them as they are); its two read loops are one `useTrainingReads`. The
run states and their rules are in `runState.ts`; the names the page and the browser checks share (storage keys, window
titles, element ids) in `contract.ts`, which `scripts/lib/harness.mjs` loads; the formatters in `format.ts` and the SI
prefixes in `units.ts` (both import-free, so checks load them too); the shared cached reads in `shared.ts`; a value
held outside React in `signal.ts`; the guarded browser storage in `kept.ts`; the newest-answer guard in `newest.ts`; a
pop-up's "blocked" line and its portal in `panels/popupParts.tsx`.

`contracts.ts` types task/run configurations and saved-model metadata at the page's transfer boundaries (record 7.324).
It is separate from `contract.ts`, which owns shared UI names. `newest.ts` also provides `inScope` and `sameScope` for
entity/revision checks; task reads, task checks and network preset replies keep their existing invalidation rules,
including edits made by Undo. These types add no runtime validation, serialization or storage format.

Reads managed by `useRequest` and direct JSON GETs have a 30-second deadline. Changing a selection, disabling a read
or leaving its view cancels the hook's owned transport; shared cached reads keep their own bounded lifetime.
Refresh replaces an outstanding hook read. Polling still allows one read at a
time and interval changes retain the current result and outstanding request. Late replies from callbacks that ignore
cancellation are discarded too. Writes keep their own lifecycle and are not retried by
this mechanism. Log, output-folder and model-structure read errors offer a retry; failed validation blocks starting.

The configuration validation key is serialized only when the configuration changes. The editors skip renders when
their inputs are unchanged, and validation issues are grouped once by row rather than filtered for every row (7.130).

Tests share isolated HTTP servers and the MOCK helpers in `tests/workbench/helpers.py`, plus controlled
browser input, passing validation replies, and optional connection fixtures in `frontend/scripts/lib/harness.mjs`.
Test modules are named after the feature they test (refactoring Group D: the round-named modules are gone) and none
imports another: the fakes and helpers several share are in `tests/workbench/helpers.py`, `fakes_connection.py`,
`fakes_virtuoso.py`, `ring_cell_support.py`, `cdf_write_support.py`, `task_save_support.py`, `pdk_support.py` and
`training_series_support.py`, and for the research tests in `tests/research_support.py` (an autouse fixture there acts
only in a module that imports it). `xdist_group` marks only the tests that share a module-scoped fixture.
`run_checks.mjs` keeps each check's measured duration in the OS temp folder (`gator-checks-durations.json`) and orders
and limits the next run by it. `run_checks.sh` makes the two saved MOCK models `encoder_models_check` reads
(`frontend/scripts/fixtures/encoder_models.py`) and picks its scratch backends' ports outside the TCP ranges Windows
reserves; `run_checks.mjs` keeps Vite's cache in `%TEMP%\gator-checks-vite\`, never in a checkout's `node_modules`
(7.292). `frontend/scripts/dom_identity_check.mjs` shows that a refactoring leaves the page as it
was: `#root` and each open pop-up per step, in both looks, with the page's requests and storage - recorded once, then
replayed without a backend (`--replay`) against another build (`--build`) and compared byte for byte (`--compare`).
`frontend/scripts/request_lifecycle_check.mjs` runs against a Vite source preview with controlled in-memory replies
and React StrictMode; it checks slow polls, reversed replies, cancellation, deadlines, hung-read replacement, retries,
run/table changes and export identity. `reliability_check.mjs` covers failed browser persistence and recovery, unsaved
JSON export, encoder selection/reset races, Undo during reset, narrow layouts and redundant serialization.
`tests/workbench/test_wb_read_efficiency.py` covers tail-read bounds, excluded directories, archive cleanup and
display-cache invalidation separately from execution integrity checks.

A pop-up window of the page is an `about:blank` window into which the page's stylesheet links are copied; they load after
it opens. The harness's `browser.attach` hands a check its pop-up only once every link has its sheet (5 s at most), so
nothing is measured in the browser's unstyled layout - measured: about one RL networks window in five was still unstyled
when it was found, for about 100 ms (record 7.178).

## Tests

```bash
~/analog-optimizer-venv/bin/python -m pytest tests/workbench -q
```

All browser checks at once (added 2026-09-30, status record 7.115):

```bash
bash frontend/scripts/run_checks.sh
```

What it does:
- It starts two scratch backends with empty temporary settings folders; it never touches the backend on 8765. Their
  default output folders are empty temporary ones too (`GATOR_WORKBENCH_DEFAULT_OUTPUT_ROOT`, record 7.276): with the
  repository's `outputs/` the page took over a run working there, in the middle of the checks.
- It waits until Windows can reach those backends too: WSL's first successful response can precede localhost forwarding.
- It builds this tree's frontend into a temporary folder and serves it.
- It runs every `frontend/scripts/*_check.mjs` in 4 parallel lanes (`--lanes N`). Each check gets its own log and
  screenshot folder under the folder it prints, and a summary follows at the end.
- Options: `--only a,b`, `--skip a,b`, and `--retry-failed`, which reruns a failed check alone and reports it as flaky
  if it then passes.

Some checks get special handling:
- The two that start real MOCK runs (export, run_control_live) share a backend of their own and run one after the other.
- Both backends run with `GATOR_AGENT_CLI_LAUNCH=off`: whatever a check presses, no terminal window opens (agent_tab
  answers its own requests anyway).
- request_lifecycle gets Vite's source preview.
- reward_v21 runs only when its fixture exists and its fixed port is free.
- The reward_v2 real/frontend checks read recorded evidence and are skipped.

The whole batch took 198 s, instead of about 9 minutes one check after another.

Connection tests use fake bridge clients and a fake probe process. No test opens an agent CLI or contacts a real
Virtuoso: the Agent window's launcher is tested with fake CLIs and fake terminals (`test_wb_agent_cli.py`, which also runs a
start script for real with a fake CLI), and the suite runs with `GATOR_AGENT_CLI_LAUNCH=off`.

The header shows blocking issues as a red button, "N blocking issues": a press lists every one of
them in full (level, code, field and editor row, message), including those that belong to no editor
tab; the list follows each validation and closes when nothing blocks. A configuration the schema
cannot even read (for example an ID with a `/` in it) is listed the same way, one issue per field:
the field and its editor row, what is wrong in plain words (for an ID: which characters, an ID that
works, and what else must be renamed with it), and the schema's own text under a closed
"Technical details" line; the editor marks the row (backend `schema.describe_errors`, status record
7.56). A row's place ("targets[0].equation row inl1") is a button (branch record SIF-95): it opens
that editor tab and brings the row the report names into view - clearing a Find text that hid it,
showing More columns for a field behind them - with the issue's field chosen, so the formula bar
names it; a field no column shows (the Unit of Parameters and Specs, Initial value) chooses the
row's ID instead, and the button's tooltip says which cell it chooses. The list stays open. An issue
of a table itself ("parameters": nothing to optimize) or of a row without an ID stays text. Each
editor tab counts its own blocking issues in a small red pill, its tooltip giving the first, so a
Spec a renamed Probe broke shows on Specs while Parameters is open. Its browser check is
`frontend/scripts/blocking_issues_check.mjs` (headless Edge against the running workbench; the
validation is answered with canned FIXTURE reports and every other writing request is refused, so
it is safe against the live backend; run line in its header).
