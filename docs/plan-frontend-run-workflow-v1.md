> **Superseded** by [plan-frontend-run-workflow.md](plan-frontend-run-workflow.md), revised 2026-10-07 (record 7.254). This is the first draft of record 7.252 (Codex), kept unchanged below for comparison.

# Frontend task model and run workflow

Status: proposed implementation plan, 2026-10-07. Record 7.252.

Make the current frontend follow one order for a new run: **Task → Mode → Model / RL network → Run settings → Start**. Loading an existing run restores that setup automatically; the user then resumes or continues it. Resume becomes a run action and disappears from the Mode selector.

## User flows

Keep the current Tasks, Runs and RL networks windows. Use **Manager** if a shared entry point is introduced. Avoid a new wizard: use a compact setup summary, the existing editors and one clear primary action.

| Starting point | Sequence | Result |
|---|---|---|
| New training | Select task → Train from scratch → configure network → run settings → Start | New run and model history |
| Fine-tuning | Select target task → Fine-tune → select model and checkpoint → review inherited network and training settings → Start | New run linked to its source checkpoint |
| Evaluation | Select target task → Evaluate only → select model and checkpoint → evaluation settings → Start | New evaluation run; no learning |
| Paused run | Load run → restore saved setup → Resume | Same run, another execution segment |
| Finished run | Load run → restore saved setup → Continue… → review total budget | Same run, another execution segment, if resumable |

The visible modes are **Train from scratch**, **Fine-tune** and **Evaluate only**, mapped to existing API values `scratch`, `fine_tune` and `frozen`. The run retains its original mode through every continuation: a resumed fine-tune still displays **Fine-tune**, with execution status shown separately.

Fine-tuning is appropriate on the same task as well as another compatible task. Changing the target task, reward, network or training recipe is a new experiment; it must not silently alter an existing run.

## Task run and model relationships

A task defines a circuit optimization problem. A run records one experiment against a saved task definition and may contain several execution segments. A checkpoint is a saved model state produced by that run. The model name is a display label; IDs and checkpoint references establish identity.

| Entity | Relationship and display |
|---|---|
| Task | Has many runs. Show its saved revision or definition identity in run details. Folder membership only organizes the Tasks window. |
| Run | Has one original mode, a task snapshot, settings, execution segments and saved checkpoints. Continuing adds a segment without creating another run row. |
| Model checkpoint | Belongs to a producing run and can initialize many later runs. Fine-tuning creates a descendant; it does not move the source model into the target task. |
| Training history | Follows exact source checkpoints across runs and tasks. Offline models may also have several recorded training-data sources. Distinguish these from the checkpoint used to initialize weights. |

Keep ordinary rows compact: name, task, mode, status and progress. Put checkpoints, segments and ancestry in expandable Details. A model trained across tasks has one linked history, without duplicating it into each task folder.

## Loading an existing run

Give the Runs window explicit **View run** and **Load setup** actions. Double-click keeps its current view behavior.

**View run** only changes the results shown in the bottom tabs. It does not change the task editors, draft configuration or the run controlled by the header.

**Load setup** restores the archived task snapshot, original mode, network, training settings and run settings together. It shows the latest resumable checkpoint separately from the original source model. It does not launch a worker. Preserve the previous new-run draft so **Back to new run** restores it.

In this existing-run context, task, mode, model source, network, reward, seed and training settings are read-only. Show one compact line such as **Existing run · Fine-tune · Paused · 420 / 800 evaluations**, followed by the appropriate Resume or Continue action. Explain locked fields once: **These settings belong to this run. Fine-tune from a checkpoint to change them.**

Restore the archive directly; do not select today's registered task and let its current preset overwrite the saved configuration. If the task has changed, a checkpoint is missing or the archive cannot be restored, retain the inspection view and show the reason continuation is unavailable. Backend compatibility checks remain authoritative.

Loading a setup while another run is live can show its configuration, but cannot take control or start it. The active run keeps its Pause and Abort controls. When the loaded run is explicitly resumed or continued, the existing run-control hook takes control of that exact run.

## Continuation and new-run rules

| Action | Identity and state | Editable settings |
|---|---|---|
| Resume | Same run and directory; restore latest full state, optimizer, replay, random state and counters | No setup changes |
| Continue… | Same restoration, with another segment and cumulative results/cost | Initially only total evaluation budget, as supported by the current continuation API |
| Fine-tune from checkpoint… | New run; selected weights and existing transfer options; fresh optimizers, target replay and task counters | Target task and compatible training/run settings; architecture follows the source |
| Evaluate from checkpoint… | New run using the selected policy; no learning updates | Target task and evaluation settings |
| Branch full state… | New run preserving full training state from a pinned checkpoint | Requires backend work described below |

Resuming a fine-tune restores its own checkpoint. It does not repeat initial weight transfer or reset its learning. Preserve its encoder-freeze and rehearsal settings; fine-tuning's optional rehearsal can use recorded source experience even though its new target replay starts empty.

Same-run continuation always uses the latest safe checkpoint. An older checkpoint can initialize a new experiment but cannot rewind an existing archive.

Replace the free-text Continue prompt with a small validated budget form: **Used 800 · New total 1,200 · Additional allowance 400**. Reject non-finite, fractional or insufficient totals explicitly. A paused run with remaining budget resumes unchanged. An exhausted run needs a larger total. Other exhausted limits or terminal states must produce a specific eligibility reason.

Keep existing simulation-budget consent and connection checks. Prevent duplicate submissions and recheck worker/save-point eligibility at launch. Do not silently turn a failed resume into fine-tuning.

## Frontend state and selection

Introduce an explicit workspace intent, `new_run` or `existing_run`, alongside the configuration. Keep three separate references: the setup being edited or inspected, the run viewed in the bottom tabs, and the run held by `useRunControl`.

The existing-run context stores its run reference and proposed continuation budget outside `WorkbenchConfig`. Its primary action must dispatch continuation for that run; the restored original mode must never accidentally cause `/api/runs/start` to create another run. Reuse the current run-control state machine for pending, running, pausing and resuming states.

Apply setup and context atomically, including Undo/Redo and browser persistence. Reload restores the context and revalidates it without launching anything. Ignore stale async responses after a task, source or context change. Model defaults, encoder presets and remembered concurrency must not overwrite a restored archive or an explicitly selected checkpoint.

For a new draft:

- Scratch exposes architecture choices and uses no model source.
- Fine-tune and Evaluate only select a source first, restore its architecture and validate it against the target task. Fine-tune's editable training recipe remains explicit; selecting a model must not silently replace it with unrelated presets.
- Separate **Source model** from **Output model name**. Renaming the output must not silently choose different input weights. An automatic source suggestion may fill an empty new draft, but must be visible and checked.
- Resolve Latest or Best to a concrete checkpoint for new-run review and submission. Display that ID, and require a fresh check if it disappears. Continuation instead follows the existing run's latest safe checkpoint.
- Keep controls visible in the established order. Disable Start while a required task, source or compatibility check is missing or pending, with a short reason beside the action.

Migrate browser configurations containing `mode: resume` into an existing-run context by reading their source run and original mode. If the source cannot be resolved, show an unresolved state with recovery actions; do not silently switch to scratch. Retain backend support for legacy `resume` requests and existing archive formats.

## Compact history and large collections

Use the existing task folders, list search and detail windows. Add explicit **This task / All tasks** scope to run and model selection where useful. Source model selection must allow other tasks, with compatibility shown separately from origin. A filtered list must still identify a selected source outside that filter.

In model Details, provide a collapsed **Training history** showing producing runs, tasks, exact parent checkpoints, modes and continuation segments. Load ancestry on demand. Shared ancestors appear once; unresolved parents are marked missing rather than omitted. Offline training-data sources have a separate expandable list. Show the selected checkpoint's history boundary, not later work performed by its source run.

Display this run's charged evaluations separately from inherited training exposure. Continuing must not count the original run again. Reuse archived provenance and existing accounting; do not infer ancestry from names, folder paths or encoder labels. If current model metadata lacks complete ancestry, add a read-only history response before claiming the history is complete.

Paginate long lists and checkpoint histories as collection size warrants, keeping filters and selection stable. Fetch summary metadata for rows and detailed history only when opened. No checkpoint tensor loading is needed merely to browse a list.

## Implementation sequence

### 1 Establish context and restore setup

Add workspace intent and draft preservation to [store.ts](../frontend/src/store.ts), then coordinate it in [App.tsx](../frontend/src/App.tsx). Build one setup-loading adapter using existing run status and archived `effective_config.json` reads through [api.ts](../frontend/src/api.ts). Guard the combined response against stale selection and revalidate before launch.

This step is complete when View is read-only, Load setup restores the archive atomically, Back to new run recovers the draft, and reload/Undo cannot mix one run's identity with another setup.

### 2 Simplify mode and model setup

Update [Right.tsx](../frontend/src/panels/Right.tsx) and [ModelChooser.tsx](../frontend/src/panels/ModelChooser.tsx) with the three readable modes and the new-run order. Update every mode-dependent help text, summary and model suggestion. A backend suggestion of `resume` becomes **Continue source run…**, routed through the existing-run loader, rather than writing `resume` into the Mode selector.

Separate source selection from output naming, pin new-run source checkpoints and protect restored settings from preset effects. Existing-run controls become read-only except the supported continuation budget.

### 3 Unify resume and continue actions

Wire Runs details and Run status through [RunControl.tsx](../frontend/src/panels/RunControl.tsx), [RunList.tsx](../frontend/src/panels/RunList.tsx) and [RunTabs.tsx](../frontend/src/panels/RunTabs.tsx). Keep one launch path for continuation and one pending state; use `/api/runs/continue` for existing runs.

The backend already preserves the original mode, run identity and execution segments. Its public continuation body currently accepts only a total evaluation budget override. Do not enable concurrency, stopping-rule or other overrides in this release merely because `runs.py` has a broader internal allowlist. A later API extension must validate each supported override and record it in segment history.

### 4 Connect selection and history

Add task scope, links among run/task/model Details, and the expandable history described above. Reuse the present windows and task-folder persistence. Extend metadata routes only for missing history or list pagination; keep folder changes independent of model provenance.

### 5 Add full-state branching separately

Ship Fine-tune from checkpoint and Evaluate from checkpoint using existing new-run support. **Branch full state** needs a distinct backend contract: a new archive with an exact source checkpoint, preserved learner state, and unambiguous new-run cost/budget accounting. Copying a run directory or calling fine-tune does not provide this behavior.

Before enabling it, specify inherited learner/replay counters versus the branch's own evaluation IDs and charges, source immutability, checkpoint compatibility and continuation of the resulting branch. Implement through workbench adapters without changing `src/analog_optimizer/` or invalidating checkpoints. Keep this action unavailable until its restoration and accounting tests pass. Do not present it as part of the frontend-only delivery.

## Validation and completion

Extend the existing run-control, run-list, task-run, model-chooser, network-panel and edit-state browser checks. Cover these behaviors with synthetic fixtures:

1. Scratch, fine-tune and evaluation follow the displayed order and send the correct new-run payload.
2. View leaves editors and header control untouched; Load setup restores the archived task and original mode without launching.
3. Resume keeps the run ID, restores full state and appends exactly one segment. Resuming a fine-tune preserves its optimizer, replay, freeze/rehearsal settings and original parent.
4. Continue validates total budget and reports additional allowance. Duplicate clicks, another live run, missing checkpoints and incompatible code cannot launch a worker.
5. Task/source changes, slow model responses, preset effects, Undo/Redo and reload cannot overwrite the chosen setup or cause accidental scratch starts.
6. Old browser `resume` configurations recover safely. New-run checkpoint selection stays pinned even if the source run advances.
7. Cross-task ancestry, shared parents, missing archives and several source datasets remain readable and do not duplicate charged cost.
8. Task folders and icons, baseline creation, Calibration and ordinary task selection retain their current behavior.

Run focused backend regression for continuation/locking and any changed metadata route, TypeScript, and an isolated frontend build. Use isolated settings and fixture services; no real simulation is required. Update the functionality reference and workbench instructions when behavior is implemented, then publish only the checked build under the repository's existing procedure.

The first delivery is complete after steps 1–4: three visible modes, explicit existing-run restoration, one continuation path, and connected task/run/model history. Full-state branching has its own backend completion criteria in step 5.
