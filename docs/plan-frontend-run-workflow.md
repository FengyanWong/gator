# Frontend task model and run workflow

Status: revised plan, 2026-10-07, record 7.254 (session "Frontend workbench layout design"; user: "read frontend logic
change plan, revise it so frontend control flow is more intuitive and robust"). It follows the Manager design agreed
earlier that night (one window with Tasks, Runs and RL models; a click only inspects; explicit actions) and replaces the
first draft of record 7.252, kept as [plan-frontend-run-workflow-v1.md](plan-frontend-run-workflow-v1.md). The last section
says what changed and why. Nothing is built yet.

## The idea

One **Manager** window holds Tasks, Runs and RL models. Clicking in it only inspects. The page's configuration stays
what it is today: the draft of the next run. Four things never change each other by accident:

- what you browse (the Manager);
- what Start will start (the draft);
- which run the bottom tabs show;
- which run the header controls.

Every move from one to another is an explicit action that names its target. Only Start, Baseline simulation, Resume and
Continue start work, each after the questions the backend asks today.

## Four things, one owner each

| Thing | What it is | Owner in the code | Changed only by | Never changed by |
|---|---|---|---|---|
| Browsing | Manager tab, filters, the inspected task, run or model | App state (new), not persisted beyond the tab choice | clicks in the Manager | anything outside the Manager; it changes nothing outside it |
| Next run (the draft) | the editors and Run configuration | `useConfig` (store.ts): persisted, Undo / Redo | edits; **Load task**; **Use for next run**; **New run like this**; Apply calibration | browsing, showing results, launches, status polling |
| Shown run | the run the bottom tabs show | `runDir` (App.tsx) | **Show results**; choosing a task (its newest run, record 7.212); a launch from this page | browsing, draft edits |
| Running job | the run the header's buttons act on | `useRunControl` (RunControl.tsx) | a launch from this page; adopting a run started elsewhere (always said); **Let go** | browsing, showing results, draft edits |

These are the four concepts of the Manager design. The first draft added a fifth, an "existing-run context" that put an
archived run into the editors; it is gone (see the last section).

## The Manager

One pop-up window (`usePopupWindow`, which already follows the page's look) with three tabs:

- **Tasks:** the Tasks window's table, details and folders (records 7.227, 7.250, 7.251), moved in.
- **Runs:** the Runs window's table and details, moved in, plus links to the task and to the input and output models.
- **RL models:** saved models and their save points, global across tasks, moved out of the RL networks window's "RL model
  to load" (ModelChooser.tsx) together with Rename. Compatibility with the draft's task is shown apart from a model's origin.

Details:

- **Opening it:** a **Manager…** button opens it. The existing **Tasks…** and **Runs…** buttons and the source line in
  Run configuration open the same window on their tab, never a second window.
- **Inspecting:** selecting a row opens its details with links (task ↔ its runs ↔ input model and save point ↔ output
  model). Following a link changes the tab and the selection only.
- **Scope:** Runs and RL models have **This task / All tasks**. A selected model outside the filter stays listed and marked.
- **The running job** is pinned on one line at the top of the window (name, state, progress, Show).
- **Reading:** lists are read when the window opens and on Refresh, never on a timer, as today. Details are read when opened.

### Actions

Each action names its target ("Load task ota7t", "Use save point 420 ev for the next run"). Draft changes are one Undo step.

| Action | Where | Effect | Draft Undo step | Starts work |
|---|---|---|---|---|
| **Load task** | Tasks | the guarded task load of Left.tsx (`chooseTask`: unsaved-edit question, one Undo step) | yes | no |
| **Show results** | Runs (double click too) | `runDir` := that run; the bottom panel opens | no | no |
| **Continue…** | Runs, Run status | budget form, then the launcher (below) | no | yes, after the questions |
| **New run like this** | Runs | the run's settings into the draft: mode, source save point, network, training values, reward, conditions, budget, seed, limits; output model name made unique; its task chosen through Load task. Says so when the task changed since that run (another revision). The task rows are never taken from the run's archive. | yes | no |
| **Use for next run: Fine-tune / Evaluate only** | RL models (a save point); Runs (a run's output model) | draft mode and `model_source` = that exact save point, with the model's network and component list, together | yes | no |
| **Rename** | RL models | the model's name (`POST /api/runs/model/rename`) | no | no |
| Task folders, Delete task | Tasks | as today | no | no |

## The draft: the next run

- **Modes.** **Train from scratch**, **Fine-tune** and **Evaluate only** map to `scratch`, `fine_tune` and `frozen`.
  `resume` leaves the Mode list: continuing is an action on a run, not a kind of new run. Every mode-dependent text
  follows (Right.tsx, ModelChooser.tsx).
- **Source model: chosen, never filled in.** Today a Mode that loads a model fills `model_source` by itself with the
  newest model saved under the RL model label (Right.tsx, the `defaultModel` effect). That becomes a visible suggestion:
  "Newest model named ota7t: Use". Run configuration shows the chosen source on one line with **Choose…**, which opens
  the Manager on RL models.
- **Source pinned.** Choosing "Latest" or "Best" stores the concrete save point it means at that moment, and the line
  names it. Today "Latest save" follows the source run, so a run that trains on changes what a later Start loads. A newer
  save point is offered, not followed: "Newer save point 520 ev: Use". Continuing a run is different: it always goes on
  from that run's own newest safe save.
- **Output model name** (`model_label`) only names what the next run saves. It no longer picks the source.
- **What Start will start** is one line beside it: "Next: ota7t · Fine-tune from ota7t (2) @ 420 ev · GT 48/4/4 · 800
  evaluations". It is also Start's tooltip, with the reason when Start is disabled.
- **Automatic writes are guarded.** A few effects write into the draft without a press:
  - the remembered concurrency on a fresh browser;
  - missing network and training values, filled from the encoder's saved setting;
  - the network and component list following the chosen source;
  - the one-time preset learning-rate upgrade (record 7.199).

  Each writes only if the draft still holds what it was computed from, is never an Undo step, and never changes task,
  mode, source, budget or seed. Following the source happens inside **Use for next run**. The effect stays only as a
  guard for an imported configuration, and says what it did.
- **An old saved draft with `mode: resume`** (browser storage, an imported file): `migrateConfig` turns it into "no mode
  chosen". A one-time note names the run and offers **Show results** and **Continue…**. Start stays disabled with "Choose
  a mode" until one is chosen: never a silent scratch or fine-tune. The backend keeps accepting a legacy `resume` start
  (CLI, older pages).

## Existing runs: continued in place

- **Continuing never uses the draft.** `POST /api/runs/continue` continues the run with its own `effective_config.json`,
  as it does today: the same run, a new segment, from its newest safe save.
  - The header's **Resume** is Continue with the total unchanged, for a paused or interrupted run with budget left.
  - **Continue…** in Run status and in the Runs tab also continues a stopped run and can raise the total. Today the page
    offers it for paused, stopped and interrupted runs. A completed run whose total is raised joins them where the
    eligibility check allows it.
- **One continuation semantics.** Today the model check's suggestion "resume" (`runs.suggest_mode`) puts `resume` into
  Mode. Start then continues the source run with the page's budget, concurrency and limits merged in
  (`RESUMABLE_RUN_FIELDS`), which is a second kind of continuation. The suggestion becomes a link to that run (Show
  results, Continue…).
- **The budget form** replaces `window.prompt`: "Used 800 · New total [1,200] · Allows 400 more".
  - Whole numbers only; "1,200" reads as 1200. Today `Number("1,200")` is not a number, and the budget silently stays as
    it was.
  - The total must be at least the evaluations used, and more than them when the budget is exhausted. Refusals are said
    on the form.
  - The consent question uses the form's numbers.
- **Eligibility before the press.** A new read-only `GET /api/runs/continuation?run_dir=` runs the checks of
  `_prepare_resume_locked`, without the run lock and without writing anything.
  - It answers: eligible, the refusal code and its reason, used / total / remaining, the minimum new total, and an
    alternative.
  - Continue shows the reason beside itself. Where the backend names an alternative, Continue offers it as a button. For
    example, the task changed since the run: **Fine-tune from its newest save point (a new run)**, which is Use for next
    run.
  - The press checks everything again under the lock.
- **A paused run in the header.** The main button reads Resume (the user's design, kept). The second button reads **Let
  go** in that state: today it reads Abort but only lets go. A new run starts once the header is free.

## One launcher

Start, Baseline simulation, Resume and Continue go through one module (`frontend/src/launch.ts`). A Corner check stays its
own job on a run, but uses steps 1, 3 and 6. Today four places do each step their own way: `App.start`,
`App.continueRun`, `RunButtons.resume` and the task-creation baseline event.

1. **Readiness.** One pure function of the draft, the validation report, the header's phase and the backend's
   eligibility says whether each action can run and why not. Buttons are disabled with that reason as their text or
   tooltip. One live run at a time on this page: a launch waits while the header's run is starting, running, pausing or
   aborting, and says so. The backend's session lock stays the real guard for real simulations.
2. **One pending state** (`useRunControl.setPending`) for every launch. The header and the Manager read it, so a second
   press anywhere finds "Starting…".
3. **The questions** (`launchWithConsent`): the real budget, a model from another task, unknown connection layers, as today.
4. **Idempotent requests.** Each launch carries a `request_id`, kept in `sessionStorage` until it is answered. Start and
   continue answer a repeated id with the same run. After a reload during a launch the page asks for that id instead of
   sending again.
   - Backend: a small table of request ids under the output root.
   - Today Start carries no such id: after a reload during a slow start (the check before every run can take seconds),
     a second Start can create a second run.
5. **On success** the run becomes the header's run and the shown run, in one place, and the message names it.
6. **On refusal** the backend's reason stays beside the action, not only in a passing line, until something it depends on
   changes. There is no fallback: a failed resume is never turned into a fine-tune, nor a fine-tune into a scratch run.

**Adopting a run started elsewhere** (a task-creation baseline, another tab, the CLI): it is taken into the header only
when the header is free or holds a run at rest, and the message names a paused run it lets go: "ota7t stays paused;
continue it from Runs". Today the task-creation baseline replaces a paused run in the header without a word.

## Connected history (after the workflow)

As in the first draft, condensed, and reached through the Manager's links:

- **Run details:** the exact task version (definition hash and revision), the input model and save point, the output
  model, and the segments with what each changed.
- **Model details:** the producing run, and a training history loaded when opened. Shared ancestors appear once; missing
  parents are marked, never left out.
- **Evaluations:** a run's charged evaluations are shown apart from the training it inherited, and continuing never
  counts the original run again.
- **Data:** metadata routes are extended only where a link is missing (the source model of a run, a model trained on
  several tasks). Records are joined by run ids and save point ids, never by names or folder paths. Lists are paginated
  when they grow.

## Not in this delivery

**Branch full state** (a new run from a full training state) needs its own backend contract, as the first draft's step 5
describes. It stays unavailable. `src/analog_optimizer/` and saved checkpoints are not touched by any step here.

## Build order

Each step is shippable on its own and checked before the next.

1. **Launcher and readiness, no new window.**
   - One pending state, the budget form and the continuation endpoint.
   - The Let go label, adoption notices and request ids.
   - Checks: `run_control`, `run_control_live`, `save_now`, `run_list`, `task_run`, `calibration`, and backend tests for
     the endpoint and request ids.
2. **The Manager shell.**
   - One pop-up with tabs; App owns open / tab / inspected item / filters. Tasks… and Runs… open it on their tab.
   - The Tasks and Runs views move in unchanged. Their checks must pass with only selectors changed: `task_list`,
     `run_list`, `task_save`, `task_rows`.
3. **RL models and the draft's source.**
   - ModelChooser's browsing, Rename and save points move in.
   - Use for next run (one step, pinned); the suggestion instead of the silent default; the output name on its own; the
     next-run line beside Start.
   - Checks: `model_chooser`, `network_panel`, `mode_suggestion`, `model_structure`, `graph_view`.
4. **Modes and run actions.**
   - The three modes and the old-draft migration; the suggestion links.
   - New run like this; cross-links; Continue… in the Runs tab with eligibility and alternatives.
5. **Connected history.** The metadata additions, then the links.
6. **Branch full state**, separately, under its own backend criteria.

## Acceptance

Browser checks with fixtures, and backend tests:

1. **Browsing changes nothing.** Clicking, filtering and following links in all three tabs leaves the draft, the shown
   run and the running job exactly as they were.
2. **Every action changes exactly its target** in the table above, and each draft change is one Undo step.
3. **Load task** keeps the unsaved-edit question and Undo.
4. **Use for next run** pins the save point. The source run training on does not change the draft. The network and
   component list arrive in the same step.
5. **Nothing else launches.** Only Start, Baseline simulation, Resume and Continue start work. A double press, or a
   reload during a launch, makes one run.
6. **Continue:**
   - the form refuses a comma typo, a fraction, a total below the evaluations used, and an exhausted budget left
     unchanged;
   - each refusal code shows its reason before the press: task changed, reward contract changed, no save point, saved by
     older code, incompatible save point, removed search method, already running, mock / real mismatch, another run live
     in the header;
   - the offered alternatives are buttons, never automatic.
7. **Old resume drafts** never start anything by themselves, and offer the run.
8. **Adoption:** a task-creation baseline while a run is paused in the header names that run in its message.
9. **Unchanged:** Calibration and its Apply, task folders, the task-run link (record 7.212), Save task, the header's
   single main button and the red Abort.

## What changed from the first draft (record 7.252), and why

- **"Load setup" and the existing-run context are gone, with "Back to new run" and the draft stash.**
  - Continuing never needed the draft: the backend continues a run from its own saved configuration.
  - Putting a run's archived task rows into the editors invited Save task, Apply calibration or an import to act on an
    archive. It also needed special rules for Undo, browser storage and reload, and a mode the user must notice and
    leave.
  - Replaced by Continue in place and New run like this, which copies run settings only and chooses the task through the
    guarded Load task.
- **View run / Load setup** became Show results plus the Manager's explicit actions, as agreed for the Manager.
- **Three references became four things with one owner each:** browsing was added, and the "setup" reference is gone.
- **Resume and Continue are one path.** The header's Resume is Continue with the total unchanged, and the suggestion
  "resume" no longer writes a Mode.
- **New in this revision:**
  - one launcher with stated reasons, one pending state, idempotent requests and a read-only continuation check;
  - guarded automatic writes, and no silent source model;
  - the Let go label and adoption notices;
  - refusal reasons that stay, with explicit alternatives.
- **Kept from the first draft:** the three modes and their mapping, pinned save points, a separate output name, the budget
  form, the old-draft migration (now "no mode chosen" instead of an unresolved context), connected history, and full-state
  branching as separate backend work.
