# Frontend task model and run workflow

Status: plan, revised twice on 2026-10-07. Nothing is built yet.

| Record | Version |
|---|---|
| 7.252 (Codex) | First draft, kept as [plan-frontend-run-workflow-v1.md](plan-frontend-run-workflow-v1.md). |
| 7.254 | Revised around one Manager window. |
| 7.257 | This version. The user: "forget about the manager. renew the load model window so it shows content similar to tasks window and runs window. Add category functionality to model load window and runs window. For model and runs, you should be able to see relationships and model history. Mode selection should be merged in to load model. Scratch mode will ask you to create a new model from the default templates. fine-tune and evaluate load existing ones", then "add these to update the plan". |

## The idea

The **Tasks**, **Runs** and **RL model** windows stay separate. The RL model window is today's RL networks window, where
a model is loaded.

- **The RL model window** becomes a table with details, like the other two, and holds the Mode:
  - **New model** creates a model from one of the default templates;
  - **Fine-tune** and **Evaluate only** load a saved model.
- **Runs and models get categories** (folders), as tasks have.
- **Both show their relationships and a model's history:** which run trained a model, which model and save point a run
  started from, and what came of it later.

The page's configuration stays what it is today: the draft of the next run. Four things never change each other by
accident:

- what you browse (the three windows);
- what Start will start (the draft);
- which run the bottom tabs show;
- which run the header controls.

Only Start, Baseline simulation, Resume and Continue start work, each after the questions the backend asks today.

## Four things, one owner each

| Thing | What it is | Owner in the code | Changed only by | Never changed by |
|---|---|---|---|---|
| Browsing | each window's selection, filter, sort, folder and open details | the window's own state | clicks in that window | anything outside it; it changes nothing outside it |
| Next run (the draft) | the editors and Run configuration, with the Mode and the model chosen in the RL model window | `useConfig` (store.ts): persisted, Undo / Redo | edits; **Load task**; **Use template**; **Use this save point**; **New run like this**; Apply calibration | browsing, showing results, launches, status polling |
| Shown run | the run the bottom tabs show | `runDir` (App.tsx) | **Show results**; choosing a task (its newest run, record 7.212); a launch from this page | browsing, draft edits |
| Running job | the run the header's buttons act on | `useRunControl` (RunControl.tsx) | a launch from this page; adopting a run started elsewhere (always said); **Let go** | browsing, showing results, draft edits |

## What the three windows share

The Tasks window already works this way (records 7.227, 7.250, 7.251), and the other two follow it:

- A table with sortable columns, a filter, **Details** under a row, "read at" and **Refresh list**. Nothing updates on a
  timer, and each window is one pop-up.
- A folder list on the left: **All**, **Unfiled** and the user's folders, with counts, create / rename / delete icons,
  and rows selected with a tick and moved with **Move to…**.
- **A click only inspects.** Selecting, filtering, sorting, changing folder and opening Details change nothing outside
  the window.
- **A double click does the window's one action:**
  - Tasks: follow the task (its rows come into the editors, edits are asked about first, as today);
  - Runs: show its results;
  - RL model: use that template or save point for the next run.
- **Links between windows.** A task, run or model named in another window's Details is a link: it opens that window at
  the item (selected, scrolled to, Details open). Each window can be opened "at" an item. Following a link changes no
  draft, no shown run and no running job.

## Tasks window

Unchanged, except that its **Newest run** and **Runs** cells become links into the Runs window, filtered to that task.

## Runs window

- **Categories:** folders, as above. **All** shows each run's folder under its date.
- **New columns:**
  - **Started from:** "template GT", "ota7t (2) @ 420", "offline: 12 runs", or "-" for a baseline.
  - **Saved model:** today's Model column, as a link.
- **Relationships in Details** (new):
  - **Task:** the task and the exact version the run used (its definition hash and revision), a link. When the task has
    been saved again since, Details says so.
  - **Started from:** the model and save point it loaded, or the template it was made from, or "trained offline on N
    recorded runs"; a link.
  - **Saved model:** the model this run saved, with its save points; a link.
  - **Runs that started from this run's model:** a list of links.
  - **History:** the chain of models behind this run, oldest first, folded.
- **Actions in Details:** **Show results** (also a double click), **Continue…** (when the continuation check allows it),
  **New run like this**.

## RL model window: the load-model window, renewed

**Opening it.** The button in Run configuration opens the window. It is renamed from "RL networks…" to "RL model…", and
beside it the next run's model is named in one line, for example:

- "New model · Graph Transformer template · GT 48/4/4";
- "Fine-tune ota7t (2) · save point 420 evaluations";
- "Evaluate ota7t (2) · save point 420 evaluations · deterministic actions".

The **Mode** select leaves Run configuration.

**The Mode, at the top of the window**, as three choices:

- **New model** (`scratch`);
- **Fine-tune** (`fine_tune`): a saved model keeps learning in a new run;
- **Evaluate only** (`frozen`): a saved model is used as it is, with no learning.

Choosing one sets the draft's mode as one Undo step, and the window shows that mode's part. `resume` is not a choice:
continuing a run is an action on the run (Runs window, Run status, the header's Resume).

### New model: from a template

- **Templates table.** One row per encoder: Graph Transformer, RGCN, GATv2, GraphGPS, Group cross attention. Each row
  shows the network sizes, the training values (updates per evaluation, starting temperature, discount, learning rate),
  where the values come from (starting preset, or edited and saved in the backend), and how many saved models were made
  from it.
- **Using one.** A double click or **Use template** fills the draft's network and training values from it, as one Undo
  step. This is what choosing an encoder does today (`applyEntry`).
- **Its settings, editable as today:** sizes, structural encoding, nominal operating points, the component list and
  Advanced. Today's "Use saved defaults" and "Save as defaults" stay as they are, shown when the draft's values differ
  from the template's saved values. No preset button comes back: record 7.191 deleted them at the user's request.
- **Name of the new model:** the RL model label, moved here from Run configuration.

### Fine-tune and Evaluate only: a saved model

- **Models table.** One row per saved model, which is the RL model one run saved. Columns:
  - Name and Trained on (the task, or "multi-task" for an offline model);
  - Network and Trained evaluations;
  - Save points and Last saved;
  - Started from;
  - Data (MOCK or real) and Restorable (full state or weights only).

  The table has the filter and folders like the other windows.
- **Compatibility with the draft's task** is shown for the selected model, from today's model check, apart from where
  the model comes from.
- **Details:**
  - **Save points:** evaluations, time, and kind (automatic, Save now, pause, end, best policy). **Use this save point**
    sets the draft's source to exactly that save point (`model_source.checkpoint_id` is a concrete id, never "latest"),
    together with the model's network and component list, as one Undo step. A double click on a model row uses its
    newest save point, pinned the same way.
  - **Rename** (today's), **Network structure** and **Graph view** (today's ModelStructure and CircuitGraphView).
  - **Relationships:** the run that produced it, what it started from (a parent model and save point, a template, or
    offline sources), the models trained from it, and the runs that loaded it. Every one is a link.
  - **History**, folded: the chain of ancestors back to its root (a template, or the recorded runs of offline training).
    Each step shows its task, mode, evaluations and save point. Shared ancestors appear once, and a parent outside the
    output folder is marked missing, never left out.
- **Settings of the mode,** under the table:
  - Fine-tune: freeze encoder, encoder-only transfer, reset critic, continual learning; the name of the model the run
    saves.
  - Evaluate only: frozen actions (deterministic or stochastic).
- **No look-only list.** Today's "Look at a saved model" in scratch goes: any model can be inspected in this table, in
  any mode, without being used.
- **The source is chosen, never filled in.** Today a Mode that loads a model fills the source by itself with the newest
  model saved under the RL model label (Right.tsx, the `defaultModel` effect). That becomes a visible suggestion,
  "Newest model named ota7t: Use".
- **A newer save point** of the source run is offered ("Newer save point 520 evaluations: Use"), never followed by itself.

## Categories for runs and models

- **Storage** follows the task folders of record 7.250. `task_folders.py` is generalized to a kind (tasks, runs,
  models), with one file per kind in `configs/local/workbench`: `task_folders.json` as it is, plus `run_folders.json` and
  `model_folders.json`. They share the same lock and checks. The routes `/api/run-folders` and `/api/model-folders`
  mirror `/api/task-folders`.
- **Keys:** a run's folder path, for runs and for models alike (a model is one run's saved model). A run's category and
  its model's category are separate, because the two windows serve different purposes.
- **Gone runs:** an assignment of a run that is no longer listed stays in the file and is not shown. Counts count listed
  rows.
- **Frontend:** `useTaskFolders` and `TaskFolders` become `useFolders(kind)` and one `Folders` component, used by all
  three windows.

## Relationships and history: data

The records exist already. Every fine-tune or evaluate run's manifest holds `parent` (run id, run folder, save point,
relation) and `source_model`, and a published offline model holds `pretraining.sources`. The plan only passes them
through:

- **Run list:** `runs.list_runs` rows gain `parent`, `run_kind` and, for an offline model, the number of its
  `pretraining.sources`. Each row's manifest is read already, so this costs nothing extra.
- **Model list:** `checkpoints.saved_models` rows extend the run rows, so they get the same fields.
- **Status route:** its `manifest` part gains `parent` and `pretraining`, for Details (the offline source list).
- **On the page:** a run's children are the runs whose `parent` names it. A model's history follows `parent` up through
  the listed runs, guarded against cycles, and ends at a template (a scratch run's architecture) or at offline sources.
- **Never inferred** from names, folder paths or encoder labels.
- **Pagination** waits until the lists are long enough to need it.

## The draft: the next run

- **Modes and model** are set in the RL model window, as above. Run configuration shows the model line and the "RL model…"
  button.
- **Automatic writes are guarded.** A few effects write into the draft without a press:
  - the remembered concurrency on a fresh browser;
  - missing network and training values, filled from the template's saved values;
  - the one-time preset learning-rate upgrade (record 7.199);
  - the network and component list following the chosen model.

  Each writes only if the draft still holds what it was computed from, is never an Undo step, and never changes task,
  mode, source, budget or seed. The network follows the chosen model inside **Use this save point**. The effect stays
  only as a guard for an imported configuration, and says what it did.
- **What Start will start** is one line beside it: "Next: ota7t · Fine-tune from ota7t (2) @ 420 · GT 48/4/4 · 800
  evaluations". It is also Start's tooltip, with the reason when Start is disabled.
- **An old saved draft with `mode: resume`** (browser storage, an imported file): `migrateConfig` turns it into "no mode
  chosen". A one-time note names the run and offers **Show results** and **Continue…**. Start stays disabled with "Choose
  a mode in the RL model window" until one is chosen: never a silent scratch or fine-tune. The backend keeps accepting
  a legacy `resume` start (CLI, older pages).

## Existing runs: continued in place

- **Continuing never uses the draft.** `POST /api/runs/continue` continues the run with its own `effective_config.json`,
  as it does today: the same run, a new segment, from its newest safe save.
  - The header's **Resume** is Continue with the total unchanged, for a paused or interrupted run with budget left.
  - **Continue…** in Run status and in the Runs window also continues a stopped run and can raise the total. Today the
    page offers it for paused, stopped and interrupted runs. A completed run whose total is raised joins them where the
    continuation check allows it.
- **One continuation semantics.** Today the model check's suggestion "resume" (`runs.suggest_mode`) puts `resume` into
  Mode. Start then continues the source run with the page's budget, concurrency and limits merged in
  (`RESUMABLE_RUN_FIELDS`), which is a second kind of continuation. The suggestion becomes a link to that run in the
  Runs window.
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
    example, the task changed since the run: **Fine-tune from its newest save point (a new run)**, which opens the RL
    model window at that save point.
  - The press checks everything again under the lock.
- **New run like this** (Runs window) copies the run's settings into the draft: mode, source save point, network,
  training values, reward, conditions, budget, seed and limits. The name of the model it saves is made unique. The run's
  task is chosen through the guarded task load, and the task rows are never taken from the run's archive. Details says
  so when the task has changed since that run.
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
2. **One pending state** (`useRunControl.setPending`) for every launch, so a second press anywhere finds "Starting…".
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

## Not in this delivery

**Branch full state** (a new run from a full training state) needs its own backend contract, as the first draft's step 5
describes. It stays unavailable. `src/analog_optimizer/` and saved checkpoints are not touched by any step here.

## Build order

Each step is shippable on its own and checked before the next.

1. **Launcher and readiness, no new window.**
   - One pending state, the budget form and the continuation check.
   - The Let go label, adoption notices and request ids.
   - Checks: `run_control`, `run_control_live`, `save_now`, `run_list`, `task_run`, `calibration`, and backend tests for
     the check and request ids.
2. **Categories.**
   - Backend: the generalized folders, with the run and model routes.
   - Frontend: one `Folders` component, used first by the Runs window.
   - Checks: `task_list` unchanged, `run_list` with folders, and backend folder tests for each kind.
3. **Relationships.**
   - The list and status fields, then the Runs window's columns and relationship Details.
   - Opening a window at an item, and the Tasks window's links.
4. **The RL model window.**
   - The three Mode choices, the templates (New model), and the models table with Details, folders, relationships and
     history (Fine-tune / Evaluate only).
   - Pinned save points and the suggestion instead of the silent default.
   - The model line in Run configuration. The Mode select and the look-only list go.
   - Checks: `model_chooser`, `network_panel`, `mode_suggestion`, `model_structure`, `graph_view`, rewritten for the window.
5. **Run actions and old drafts.** New run like this, the old-draft migration, and the suggestion's link.
6. **Branch full state**, separately, under its own backend criteria.

## Acceptance

Browser checks with fixtures, and backend tests:

1. **Browsing changes nothing.** Clicking, filtering, sorting, changing folder, opening Details and following links in
   all three windows leaves the draft, the shown run and the running job exactly as they were.
2. **Each double click and each action changes exactly its target,** and each draft change is one Undo step.
3. **Categories in the Runs and RL model windows** behave as the task folders do: create, rename, delete, Move to,
   counts. They survive a reload and are shared by browser tabs.
4. **Relationships.** A fine-tune's parent, a model's children, an offline model's sources, a missing parent and a shared
   ancestor are shown correctly, and every link opens the right window at the right item.
5. **The Mode in the RL model window:**
   - New model fills the draft from the template chosen;
   - Fine-tune and Evaluate only pin the save point chosen; the source run training on does not change the draft; the
     network and component list arrive in the same step;
   - the Mode select is gone from Run configuration.
6. **Nothing else launches.** Only Start, Baseline simulation, Resume and Continue start work. A double press, or a
   reload during a launch, makes one run.
7. **Continue:**
   - the form refuses a comma typo, a fraction, a total below the evaluations used, and an exhausted budget left
     unchanged;
   - each refusal code shows its reason before the press: task changed, reward contract changed, no save point, saved by
     older code, incompatible save point, removed search method, already running, mock / real mismatch, another run live
     in the header;
   - the offered alternatives are buttons, never automatic.
8. **Old resume drafts** never start anything by themselves, and offer the run.
9. **Adoption:** a task-creation baseline while a run is paused in the header names that run in its message.
10. **Unchanged:** Calibration and its Apply, task folders, the task-run link (record 7.212), Save task, the header's
    single main button and the red Abort.

## What changed, and why

**Record 7.257 (this version), on the user's words:**

- **No Manager.** The Tasks, Runs and RL model windows stay separate and link to each other.
- **The RL model window** (today's RL networks window) becomes a table with Details, like the other two, and holds the
  Mode. New model chooses a template; Fine-tune and Evaluate only choose a saved model and save point. The Mode select
  leaves Run configuration.
- **Categories for runs and models,** stored like the task folders.
- **Relationships and model history for runs and models,** from records that already exist (`parent`, `source_model`,
  `pretraining.sources`).

**Record 7.254, from the first draft (7.252):**

- **"Load setup" and the existing-run context are gone, with "Back to new run" and the draft stash.**
  - Continuing never needed the draft: the backend continues a run from its own saved configuration.
  - Putting a run's archived task rows into the editors invited Save task, Apply calibration or an import to act on an
    archive. It also needed special rules for Undo, browser storage and reload, and a mode the user must notice and
    leave.
  - Replaced by Continue in place and New run like this, which copies run settings only and chooses the task through the
    guarded task load.
- **Resume and Continue are one path.** The header's Resume is Continue with the total unchanged, and the suggestion
  "resume" no longer writes a Mode.
- **New in 7.254:**
  - one launcher with stated reasons, one pending state, idempotent requests and a read-only continuation check;
  - guarded automatic writes, and no silent source model;
  - the Let go label and adoption notices;
  - refusal reasons that stay, with explicit alternatives.
- **Kept from the first draft:** the three modes and their mapping, pinned save points, the budget form, the old-draft
  migration (now "no mode chosen"), connected history (now inside the windows), and full-state branching as separate
  backend work.
