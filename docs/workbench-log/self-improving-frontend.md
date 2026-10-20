# Branch `self-improving-frontend`: its own records

The branch `self-improving-frontend` (2026-10-20, Claude session "Frontend workbench layout design"; user: "keep checking and
improve the frontend design. Limit is until usage reaches 80% or I command stop", then "branch out and do commit and push
yourself so I can check. Branch name self improving frontend"). It starts at `origin/workbench` (8b67d97) with records
7.372, 7.376 and 7.380 cherry-picked (their commits on `workbench`: a481619 and 8d43a00), so nothing of other sessions'
unpushed work goes out with it. The session commits and pushes here by itself; whether it is merged is the user's call.

The main log's numbers (7.NNN) are taken within minutes by other sessions, so this branch numbers its own entries SIF-1,
SIF-2, ... Nothing here is live: the live page (8765) serves `workbench`'s working tree. Each entry is checked on a build of
this branch - `tsc`, the browser checks it touches, and the page with the user's real data through `vite preview` (port 5174,
its API answered by the live backend, every write refused).

### SIF-1 Every saved model says its design: Graph Transformer, RGCN, GATv2, GraphGPS, CircuitGPS v2 / v3 (2026-10-20; user: "particularly, in models panel, show what is each models original shape design(rgcn ro graphgps or circuit gps etc)")

**Found.** The saved models' table (RL model window, Fine-tune and Evaluate) named a model's network by its encoder key and
size in short - "GPS 48/4/4 · rwse", "CircuitGPS 48/4/4 · rwse" - and CircuitGPS v2 and v3, two different networks (record
7.356), looked the same. Of the user's 411 saved models: 212 GraphGPS, 109 Graph Transformer, 27 RGCN, 24 parameter-group
attention, 13 GATv2, 13 CircuitGPS v3, 13 CircuitGPS v2.

**Changed.**
- `lineage.ts`: `DESIGN_NAME` and `designName(network)` - the names the RL model window's chooser uses, CircuitGPS with its
  version - and `designShort`, the short form (GraphGPS, not "GPS"; "CircuitGPS v3").
- `ModelChooser.tsx`: the column "Network" is **Design**: the design by name, its size under it ("48/4/4 · RWSE"); sorted and
  filtered by both (the filter's hint says "design"). Its tooltip keeps the full key ("graph_gps 48/4/4 · rwse").
- The same names where a saved model's network is described: the model's facts in the RL model window (`RlModelWindow.tsx`:
  "Network GATv2, hidden 16, ..."), the notes when a loaded model brings its network (`useRlModel.ts`: "The network stays
  GATv2 16/2/1 ..."), its structure (`ModelStructure.tsx`), Run configuration's model line (`rlModelText.ts`) and "Started
  from" (`lineage.ts`: "template GraphGPS").
- `roadster.css`: the size on a line of its own under the name.
- Checks: `model_chooser_check` (the columns, a row's design and size, the model's network line, the note).
- Docs: `docs/workbench.md` (§ The network comes with the model: "Every model says its design"),
  `docs/functionality-reference.md` (Saved models).

**Checked.** `tsc` clean. Browser checks of this branch: `model_chooser_check` 70 (the table still fits the window at
1100 px: its first try with a separate Size column did not, 842 > 788 px, so the size went under the name),
`encoder_models_check` 24, `run_list_check` 119, `network_panel_check` 57, `model_structure_check` 29,
`mode_suggestion_check` 20. With the user's real models (the branch built and served on 5174): 411 models, the column
"Design" reading "GraphGPS 48/4/4 · RWSE" and "CircuitGPS v3 48/4/4 · RWSE", "Started from" reading "template GraphGPS", the
table exactly its room (788 px, no sideways scroll), no console error. Pictures:
`artifacts/local/reviews/design-loop-2026-10-20/sif1/`.

### SIF-2 Numbers and times read plainly: the model's facts, the reward spread, file and log times (2026-10-20; from the design survey of the live page)

**Found** (a survey of every tab and window with the user's real data, `artifacts/local/reviews/design-loop-2026-10-20/
survey1/`): the RL model window's facts of the model in use wrote "Saved (UTC) 2026-10-16T17:21:11.461929+00:00", "Worst
hard-spec share 0.500000", "Restorable full_state" (the table beside it says "full state") and "Trained on
mscr_vco_lin_c:4fd0a8f9303827bd" (the task and its definition's hash); Run status's steering line "Reward spread ...
0.0370463; exploration bonus ... -0.0247834"; Output files "Modified (UTC) 2026-10-16T17:21:18"; and the Logs tab its
times of day in UTC without saying so, while every other time on the page is this computer's.

**Changed.**
- `format.ts`: `sig` (three significant digits, no padding) and `taskNameOf` (a task's name from a recorded task id).
- `RlModelWindow.tsx`: Trained on - the task's name, the id in its tooltip; **Saved** - this computer's time as the Runs and
  Tasks windows write it (2026-10-16 18:21:11), the UTC stamp in its tooltip; the reward numbers without padding (0.5);
  Restorable in the table's words (`ModelChooser.tsx` exports `RESTORABLE`).
- `RunTabs.tsx`: the reward spread and the exploration bonus to three significant digits (0.037, -0.0248); Output files'
  **Modified** in this computer's time, its UTC in the tooltip; the Logs' times of day in this computer's time.
- Checks: `files_tab_check` (the Modified column), `model_chooser_check` (the facts). Docs: `docs/functionality-reference.md`
  (Logs, Output files).

**Checked.** `tsc` clean. Browser checks of this branch: `export` 22, `looks` 60, `reliability` 20, `model_chooser` 71,
`graph_view` 63, `encoder_models` 24, `model_structure` 29, `mode_suggestion` 20, `files_tab` 19, `run_control_live` 23. With
the user's real data (the branch on 5174, a VCO run loaded from the Runs window): "Reward spread ... 0.037; exploration
bonus ... -0.0248"; "artifact_manifest.json / 159.2 KiB / 2026-10-16 18:21:18"; the facts "Trained on mscr_vco_lin_c",
"Saved 2026-10-16 18:21:11", "Worst hard-spec share 0.5", "Restorable full state"; the log's newest line at 18:21:12 (it
said 17:21:12); no console error. Pictures: `artifacts/local/reviews/design-loop-2026-10-20/sif2/`.

### SIF-3 The page never scrolls as a whole; a completed run's bar is not red; the model line reads whole (2026-10-20; from the design survey)

**Found.** With a run in the bottom panel the whole page scrolled about 500 px past the window: two icon buttons'
screen-reader labels (`.sr-only`, absolutely placed) at the end of a long Run status were placed by the footer - the bottom
panel's scroll area was not a positioned box - so they reached y = 1577 in a 1050 px window (found by measuring every box's
scroll height: `artifacts/local/reviews/design-loop-2026-10-20/probe_scroll.mjs`). Run status's bar was red for every run,
red that since record 7.372 means "look here": a completed run's bar read as an error. Run configuration's model line was
cut to one line in a monospace font ("New model · Graph Transform...").

**Changed** (`roadster.css`, `RunTabs.tsx`): the bottom panel's and the run column's scroll areas are positioned, so they hold
what is placed in them; the bar is red while the run runs, white once completed, grey paused or stopped, the error red when it
failed; the model line in the body font, two lines at most (its tooltip keeps the whole). Check: `room_check` (the page does
not scroll and the scroll areas are positioned; a completed run's bar is white; the model line's font and lines). Docs:
`docs/workbench.md` (§ The page's look and layout), `docs/functionality-reference.md` (Run status).

**Checked.** `tsc` clean. The whole browser suite of this branch with SIF-3 in it: 54 scripts, 2,197 checks passed;
the one that failed, `looks_check`'s "no light box is left", took the white bar of a completed run for a left-over of the light
look - a bar's fill is now let through as a primary button's is. `room_check` 21 with the new checks: the page 1050 px in a
1050 px window, both scroll areas positioned, the bar "status-hero-bar done" in the text's white, the model line in Segoe UI
on two lines. With the user's real data (branch on 5174, a VCO run loaded): the page 1050 px tall where it was 1578; the model
line "Fine-tune mscr_vco_lin_c (6) · save point 800 evaluations" on two lines; the bar white. Pictures:
`artifacts/local/reviews/design-loop-2026-10-20/sif3/`.

### SIF-4 Tables keep one line per row: experiment names, JSON values (2026-10-20; from the design survey)

**Found.** The Runs window's Experiment column broke names anywhere ("r5-dffr- / powermid- / bodata- / s2_ae6e1a /
e24977"), making each row five lines tall; its folder's 12-letter hash was most of the text. The Data tables wrapped JSON
values (`best_so_far_metrics`, `reward_components`) into blocks up to 200 px tall, so a row filled the panel.

**Changed.** `RunList.tsx`: the experiment by its name, the hash ("__ae6e1ae24977") only in the tooltip, a line broken only
after "-" or "_". `RunTabs.tsx` + `roadster.css`: a JSON cell is one line with "...", its whole value on hover, a click copies
it - as id cells already were (record 7.158). Docs: `docs/functionality-reference.md` (Runs..., Data tables).

**Checked.** `tsc` clean; `run_list_check` 119, `looks_check` 61 (with a new check: a JSON cell keeps to one line, "..." and
its whole value on hover). With the user's real data: the Runs window's experiments "r5-dffr-powermid-bodata-s2" (the folder
with its hash in the tooltip), those rows 66 px tall where they were about 100; the Data tables' rows 32 px each where the
first was 213. Pictures: `artifacts/local/reviews/design-loop-2026-10-20/sif45/`.

### SIF-5 An issue in a row says what it is, not its code (2026-10-20; from the design survey)

**Found.** The editors' Issues column wrote each issue as its level and code - "warning: equation_unit_unchecked",
"info: spec_adds_registry_entry" on every formula row of the VCO task's Specs - the words only in the tooltip.

**Changed.** `Editors.tsx` (`issueHead`): the level, then the first clause of the message ("warning The unit of a formula
is not checked"), one line with "..." (`roadster.css`); the whole message and "(warning: equation_unit_unchecked)" on hover;
the code stays in the issue's `data-code`. Checks: `spec_equations_check` (reads the level and the code from the issue; the
words and the tooltip), `blocking_issues_check`. Docs: `docs/functionality-reference.md` (N blocking issue(s)).

**Checked.** `tsc` clean; `spec_equations_check` 32 (a new check: the words, and the code only in the tooltip),
`blocking_issues_check` 39, and `editor_columns`, `reliability`, `room`, `sheet`, `find_fill_copy`, `typing`,
`unsaved_rows`, `task_rows` - 501 checks in the twelve scripts SIF-3 to SIF-5 touch. With the user's real data (the VCO
task's Specs): "warning The unit of a formula is not checked", "info 'f_center_hz' is new to the result registry ...";
the Issues column takes 240 px while a row has an issue, so the first clause shows whole.

### SIF-6 The run shown is named as the rest of the page writes (2026-10-20; from the design survey)

**Found.** Left of **Runs...** the bottom tab line named the run shown as "2026-10-16 16:32:51 | mscr_vco_lin_c | scratch
seed0 | completed [MOCK]": "|" where every other line of the page sets parts apart with "·", the Mode by its key
(`scratch`, `fine_tune`) where the RL model window names it (New model, Fine-tune, Evaluate only), "seed0" as one word.

**Changed.** `RunList.tsx` (`label`): "2026-10-16 16:32:51 · mscr_vco_lin_c · New model, seed 0 · completed", MOCK as one more
part. Checks: `run_list_check` (the label), `task_run_check` (finds the run by its task between the dots).

**Checked.** `tsc` clean; `run_list_check` 119, `task_list_check` 79, `task_run_check` 31, `run_control_check` 101.

### SIF-7 A Training chart's line says its values first (2026-10-20; from the design survey)

**Found.** The line over each Training chart - the newest values, or those under the pointer - is cut at the chart's width,
and its values came last: "Newest: Evaluation 800 · search · episode 1-000189 step 4 · Training (recorded) 0.06274 ·
Training: me...", so at 1366 px only the phase and the episode showed.

**Changed.** `TrainingChart.tsx`: the evaluation (or update), then the values, then the row's phase and episode ("Newest:
Evaluation 800 · Training (recorded) 0.06274 · Training: mean of last 20 0.061 · search · episode 1-000189 step 4"); the
whole line stays in its tooltip. Check: `training_tab_check` (three patterns follow the order).

**Checked.** `tsc` clean; `training_tab_check` 88, `training_data_check` 117, `graph_view_check` 63.

### SIF-8 The RL model window's templates say each thing once, in words (2026-10-20; from the design survey)

**Found.** In New model the templates table read "Parameter-group attention — experimental (experimental)" (the backend's
label says it, and the page added it again), its sizes wrote "rwse" where the saved models' table now writes "RWSE"
(SIF-1), and the fold under the template in use read "Where the graph_transformer values come from" - the encoder's key.

**Changed** (`RlModelWindow.tsx`): "(experimental)" only where the label does not say it; RWSE in capitals; the fold names
the design ("Where the Graph Transformer values come from"). Check: `network_panel_check` (58: the six rows, the fold).

**Checked.** `tsc` clean; `network_panel_check` 58, `encoder_models_check` 24, `model_chooser_check` 71,
`model_structure_check` 29, `network_inputs_check` 8, `mode_suggestion_check` 20.

### SIF-9 A cell that holds more than it shows says so (2026-10-20; from the design survey)

**Found.** The editors' text cells cut their text at the cell's edge with nothing to tell it goes on ("main-inverter NMO",
"auxiliary (cross-coup" in Notes).

**Changed** (`roadster.css`): a text cell that is not being edited ends in "..." where it is cut; entered, it shows all of it,
as the formula bar does. Check: `looks_check` (62).

**Checked.** `looks_check` 62, `sheet_check` 43, `typing_check` 47, `find_fill_copy_check` 30, `formula_bar_check` 19.

### SIF-10 The saved models of one design, with how many there are of each (2026-10-20; continuing SIF-1, the user's "models panel")

**Changed** (`ModelChooser.tsx`): a **Design** list beside Refresh list - "All designs", then each design with its count, the
most models first - keeps the table to one design; the folder's count and the empty-table note follow it. Check:
`model_chooser_check` (74: the list for the fixture's seven models - "Graph Transformer (5) | GATv2 (1) | RGCN (1)" -
choosing RGCN keeps its one model, All designs brings the seven back). Docs: `docs/functionality-reference.md`.

**Checked.** `tsc` clean; `model_chooser_check` 74, `mode_suggestion_check` 20, `graph_view_check` 63. With the user's real
models (the branch on 5174): "All designs | GraphGPS (212) | Graph Transformer (109) | RGCN (27) | Parameter-group attention
(24) | CircuitGPS v2 (13) | CircuitGPS v3 (13) | GATv2 (13)"; CircuitGPS v2 chosen, 13 rows, each "CircuitGPS v2 48/4/4 ·
RWSE". Pictures: `artifacts/local/reviews/design-loop-2026-10-20/sif10/`.

### SIF-11 The Runs window says what each run was, and its design (2026-10-20; continuing SIF-1 for runs)

**Found.** The Runs window's Mode column wrote the configuration's keys - "scratch", "fine_tune", "frozen" - where the RL
model window says New model, Fine-tune, Evaluate only, and a baseline simulation (mode "scratch") read as a new model; no
column said which network design a run trained, though the encoders are what the experiments compare. With the user's 549
runs the table was 1302 px wide in its 1234 px at a 1500 px window (it scrolled sideways before this record too, by about
40 px).

**Changed** (`RunList.tsx`, `roadster.css`): the Mode cell - "New model", "Fine-tune", "Evaluate only", "Resume", or
"Baseline", "Calibration", "Offline training" by the run's kind - with the design of the run's network under it (not for a
baseline or a calibration; a run does not say CircuitGPS's version); the same words in the filter and in the label of the run
shown (SIF-6); a stop reason may break after "_" and the window's wrapping cells may be 5em wide, so the table fits.

**Checked.** `tsc` clean; `run_list_check` 119 (the fixture's row: "New model Graph Transformer"), `task_run_check` 31,
`task_list_check` 79, `run_control_check` 101, `looks_check` 62. With the user's real runs (the branch on 5174): Baseline 85,
Calibration 17, New model GraphGPS 129, Fine-tune GraphGPS 81, New model Graph Transformer 78, ... Offline training 23; the
table 1234 px in its 1234 px.

### SIF-12 The Training tab's Compare list names runs as the rest of the page does (2026-10-20; following SIF-6 and SIF-11)

**Found.** The Compare list wrote each run as the run label did before SIF-6: "10-16 16:32 | mscr_vco_lin_c | scratch seed0 |
completed | 800 eval. [MOCK]".

**Changed.** `TrainingTab.tsx`: "10-16 16:32 · mscr_vco_lin_c · New model, seed 0 · completed · 800 evaluations · MOCK".
`runMode` and `runDesign` (SIF-11) move from `RunList.tsx` to `rlModelText.ts`, beside the Mode names, so the Runs window,
the run shown and the Compare list say a run the same way. And the RL model window's facts name the model's training conditions as Reward
and conditions does ("Nominal only; 0 planned", where they said "off; 0 planned"; `RlModelWindow.tsx`).

The folded Run configuration line and two notes of the RL model window name the design too ("New model - 200
evaluations - Graph Transformer 48/4/4", where it said "graph_transformer 48/4/4"; `rlModelText.ts` `foldedText`,
`RlModelWindow.tsx`); `module_fold_check` follows.

**Checked.** First the whole browser suite on SIF-1 to SIF-11: 54 scripts, 2,205 checks, none failed. Then, `tsc` clean;
`run_list_check` 119, `model_chooser_check` 74, `network_panel_check` 58, `task_run_check` 31, `training_tab_check` 88,
`module_fold_check` 30. With the user's real data (the branch on 5174): the Compare list "20/10, 10:43 · dffrx1_t2 ·
Fine-tune, seed 2 · completed · 800 evaluations".

### SIF-13 The saved models' "Trained on" without "real:" (2026-10-20; from the real-data look at the models table)

**Found.** "Trained on" wrote a real task's key - "real:dffrx1_t2", "real:agentic_fc_pub_far" - where every other place
gives a task's name without "real:" since record 7.249.

**Changed** (`ModelChooser.tsx`): the name without "real:" (MOCK tasks keep their "synthetic:" key, so they still read as
such); the key on hover. Check: `model_chooser_check` (75: the real fixture model reads "gpdk045_ota5", its key in the
tooltip).

**Checked.** `tsc` clean; `model_chooser_check` 75, `mode_suggestion_check` 20, `graph_view_check` 63.

### SIF-14 Run status names the Mode in words (2026-10-20; from the design survey)

**Found.** Run status's facts wrote "Mode / model: scratch (no weights loaded)", a fine-tune "fine_tune from 1a2b3c4d5e6f /
ckpt-...": the configuration's key.

**Changed** (`RunTabs.tsx`): "New model - no weights loaded"; "Fine-tune - from run 1a2b3c4d5e6f, save point ckpt-...", the
Mode as the RL model window names it. Check: `room_check` (22: the fixture run's row).

**Checked.** `tsc` clean; `room_check` 22, `looks_check` 62, `calibration_check` 38, `run_control_live_check` 23.

### SIF-15 Why a run stopped, in words (2026-10-20; from the design survey)

**Found.** A stopped run said why by its key - "completed · budget_exhausted" in Run status, "budget_exhausted",
"offline_update_budget", "unresolved_launch_intent" under the state in the Runs window - though the page says everything
else in words.

**Changed.** `format.ts` (`STOP_WORDS`, `stopWords`): "budget used up", "update budget used up", "first feasible design
found", "an evaluation failed", "launch not confirmed", "too many failures in a row", "stopped by you", ... (a key the list
does not know reads with spaces); the key on hover. In Run status's first line and its State row (`RunTabs.tsx`) and under the
state in the Runs window (`RunList.tsx`; the cell may wrap now, so the table still fits; the filter finds the words too).
Check: `run_list_check` ("completed budget used up").

**Checked.** `tsc` clean; `run_list_check` 119, `room_check` 22, `task_run_check` 31, `task_list_check` 79, `looks_check` 62,
`calibration_check` 38, `run_control_live_check` 23. With the user's 549 runs: "budget used up" 483, "update budget used up"
23, "an evaluation failed" 13, "first feasible design found" 11, "stopped by you" 6, "launch not confirmed" 5, ...; the
table 1234 px in its 1234 px.

### SIF-16 Stop reasons in words everywhere a run is described (2026-10-20; completing SIF-15)

**Changed.** The Runs window's Details - the fact "Stop reason" reads "paused by you (user_pause)", the segments' table "paused
by you", "budget used up" (the key on hover) - and the Training tab's state badge ("completed (budget used up)"); `RunList.tsx`,
`TrainingTab.tsx`. Check: `run_list_check` (the Details facts and the segments).

**Checked.** `tsc` clean; `run_list_check` 119, `task_run_check` 31, `training_tab_check` 88.

### SIF-17 The saved models' times as the other windows write them (2026-10-20)

**Found.** The saved models' table wrote "Last saved" as "20 Oct, 13:09:10" (and its save points and the "newer save point"
note so), where the Runs and Tasks windows, and since SIF-2 the model's facts, write "2026-10-20 13:09:10".

**Changed** (`ModelChooser.tsx`): one way of writing a time. Check: `model_chooser_check` (76: the cell's form).

**Checked.** `tsc` clean; `model_chooser_check` 76 (the table still fits 1100 px), `mode_suggestion_check` 20,
`graph_view_check` 63.

### SIF-18 "Compatibility for Fine-tune", not "fine_tune" (2026-10-20)

**Changed** (`RlModelWindow.tsx`): the compatibility line under the model in use names the Mode as the window's buttons do
("Compatibility for Fine-tune: compatible"; a legacy resume reads "Resume"). `reward_v2_frontend_check` (skipped without its
evidence folders) follows.

**Checked.** `tsc` clean; `model_chooser_check` 76, `mode_suggestion_check` 20, `network_panel_check` 58.

### SIF-19 A run's best design, not shouted (2026-10-20)

**Changed** (`RunList.tsx`): the Runs window's Details write the best design as "feasible · gain_db=41.5 · violation 0.125"
where they wrote "FEASIBLE  gain_db=41.5  violation 0.125" in capitals beside a lower-case "infeasible", parts set apart by
two spaces. Check: `run_list_check` (119).

**Checked.** `tsc` clean; `run_list_check` 119.

### SIF-20 A run's saved state in the saved models' words (2026-10-20)

**Changed** (`RunList.tsx`): the Runs window's Details write "Saved state: full state (complete output, latest save ...)",
where they wrote the key "full_state"; "weights only" likewise - as the saved models' table and the model's facts do (SIF-2).
Check: `run_list_check` (119).

**Checked.** `tsc` clean; `run_list_check` 119.
