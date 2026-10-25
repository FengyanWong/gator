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

### SIF-21 Tooltips name the Modes as the buttons do (2026-10-20)

**Changed.** The Runs window's "Can continue" help ("usable for Fine-tune and Evaluate only", it said "fine_tune / frozen")
and Run status's fine-tune offer ("... in Mode Fine-tune, as one Undo step"); `RunList.tsx`, `RunTabs.tsx`.

**Checked.** `tsc` clean; `run_list_check` 119, `run_control_check` 101.

### SIF-22 Matched devices leaves room for the table (2026-10-20; from the survey at 1366 x 768)

**Found.** At 1366 x 768 with a run in the bottom panel, Matched devices' results (capped at 45 % of the window) took the
whole editors' card - 345 px of 389 - and the table went out of view.

**Changed** (`roadster.css`): the panel, and the confirm questions in the same place, take 40 % of the card at most; they scroll
inside. Measured with the user's VCO task (the branch on 5174): the panel 144 px of the 389 px card, the table's heading in
view; entering a cell then folds the bottom panel (record 7.372).

**Checked.** `matched_devices_check` 30, `looks_check` 62, `room_check` 22, `reliability_check` 20, `edit_state_check` 24.

### SIF-23 The Design list sits beside Refresh list (2026-10-20; correcting SIF-10)

**Found.** SIF-10's Design list took the whole line in the RL model window (the window's selects are as wide as their line).

**Changed** (`roadster.css`): at its own width (234 px with the user's designs), beside Refresh list.

**Checked.** `model_chooser_check` 76, `looks_check` 62, `mode_suggestion_check` 20; with the user's models (the branch on
5174): 234 px, on Refresh list's line, eight entries.

### SIF-24 The Tasks list shares its width (2026-10-20)

**Found** (the user's 69 tasks, the branch on 5174). At the window's own 1500 px the Newest run column got 150 px and took
four or five lines a row: the Task column (its folder line), the Cell column (`graphgps/graphgps_ldo1_graphgps_ldo1_t1`)
and the dates never wrapped, so only Newest run could give way. At 1100 px the table was 1149 px in a 850 px space:
Newest run, Runs and Details out of view, 156 px a row. "completed · 1 evaluations".

**Changed** (`TaskList.tsx`, `roadster.css`):
- Saved, Baseline and Newest run's start are to the minute; the tooltip has the full time. Details keep the seconds.
- A task's folder line, the column titles and the cell may take two lines: the cell name moves under its library
  ("agenticsizing/" over "asz_bgr") as a whole and breaks after a "_" only when it is longer than the column; the
  testbench name likewise.
- Under 1250 px a date goes over its time; a date never breaks at its hyphens.
- "1 evaluation".

Measured (69 tasks): 1500 px - Newest run 279 px, two lines; rows 47 px median (none over 63 px but the three
`graphgps_ldo1_t*`, 81 px). 1250 px - fits, 66 px median. 1100 px - the table 834 px fits, every column in view.

**Checked.** `tsc` clean; `task_list_check` 80 (one new: minute, tooltip, unbreakable date, name part), `task_rows_check`
52, `task_run_check` 31, `run_list_check` 119, `ngspice_window_check` 39, `dom_identity_check` 56, `looks_check` 62.

### SIF-25 The Training readout's numbers stand out (2026-10-20)

**Found.** The line above each Training chart ("Newest: Evaluation 800 · Training (recorded) 0.06274 · Training: mean of
last 20 0.05706 · search · episode ...") was one muted 11 px monospace run of text: the numbers - what the line is read
for - looked like the words around them.

**Changed** (`TrainingChart.tsx`, `roadster.css`): the x and each value are `<b>` in the text colour, the words stay muted.
The line's text is the same (every check reads it), and so is its tooltip.

**Checked.** `tsc` clean; `training_tab_check` 89 (one new: three emphasised numbers, not in the muted colour),
`training_data_check` 117, `looks_check` 62; the user's VCO run on the branch (5174).

### SIF-26 The task file fills its window (2026-10-20)

**Found** (the user's VCO task, the branch on 5174). The task file's text box was 70 % of the window's height whatever the
window: at 900 px the bottom 140 px stayed empty. Its title said "Task file of real:mscr_vco_lin_c", where the Tasks list
and the tab line say "mscr_vco_lin_c".

**Changed** (`roadster.css`, `TaskSave.tsx`): the window is a column - title, help line, the text taking the rest, the buttons
at the bottom; a refused file's problems list scrolls inside 35 % of the window, so the buttons stay in view. The title
names the task without "real:".

Measured: 900 px tall - the text 740 px (was about 630), the buttons end 18 px above the window's edge; 600 px - 440 px;
nothing scrolls.

**Checked.** `tsc` clean; `task_save_check` 70 (one new: title, the text fills the window, nothing scrolls),
`virtuoso_source_check` 95, `looks_check` 62.

### SIF-27 Dates stay whole in the Runs window (2026-10-20; correcting SIF-11)

**Found** (the user's 549 runs, the branch on 5174, the window's own 1500 px). The Finished column read "2026-10-" over
"20" over "13:09:11": SIF-11 let the Runs window's wrapping cells go down to 5em, narrower than a date. Task names broke
anywhere ("mscr_otat" over "c").

**Changed** (`RunList.tsx`, `roadster.css`): the dates in Started and Finished (also "(paused)" and "last seen ...") sit in
a `.run-date` that never wraps, so a narrow column puts the time under the date; a task name may break after a "_" or "-"
(as the experiment name does), e.g. "mscr_" over "otatc".

Measured: at 1500 px the table still fits (1234 px in 1234), no date broken.

**Checked.** `tsc` clean; `run_list_check` 120 (one new: two whole dates, one break point in the task name),
`task_run_check` 31, `dom_identity_check` 56, `looks_check` 62.

### SIF-28 The editors' columns share the card by what they hold (2026-10-20)

**Found** (the user's VCO task, the branch on 5174). Every box in the editors had the browser's natural width of 20
characters, so the table gave its columns about the same room whatever they held: at 1680 px the four text columns of
Probes were 229 px each - Probe ID ("m_f1_hz") as wide as Expression, whose six values were all cut; in Specs, Lower and
Upper took 194 px each for "-0.006" while Equation had 185 px and cut five of eight.

**Changed** (`cells.tsx`): a box's natural width (`size`) is 11 characters for a number, 40 for an Expression or Equation,
28 for Notes and 8 for Parameter (w, l, r); the rest keep 20 and the minimum widths stay. Every box still fills its column.

Measured (1680 px): Specs - Equation 185 -> 321 px, Lower/Upper 194 -> 122; Probes - Expression 229 -> 331, Notes
229 -> 248, Probe ID / Output name 229 -> 193; Parameters - Notes 146 -> 218, Lower/Upper 152 -> 114, Parameter 149 -> 101.
1366 px: Expression 166 -> 209, Equation 107 -> 138. No number is cut, no table scrolls sideways.

**Checked.** `tsc` clean; `editor_columns_check` 13 (one new: natural sizes 40 / 11, Equation wider than Lower) and the 19
other checks that use the editor tables - 591 checks (`reward_v21_check` is a stand-alone check for its own scratch
backend on 5191, not run by the runner's default list).

### SIF-29 The Logs and Data tables lists sit on their tool line (2026-10-20)

**Found.** In the bottom panel's Logs and Data tables, the list ("events", "evaluations") took a line of its own across the
whole window - 1600 px for one word - and pushed its buttons and note to a second line: a row of the panel's height lost.
(Every select is as wide as its line; the tool line wraps.)

**Changed** (`RunTabs.tsx`, `roadster.css`): both lists (`select.tab-choice`) keep their own width (140 px) at the start of
their tool line, the buttons and note beside them.

**Checked.** `tsc` clean; `looks_check` 63 (one new: the list's width and line), `export_check` 22, `training_tab_check` 89,
`room_check` 22, `dom_identity_check` 56, `agent_window_check` 28, `reliability_check` 20; the user's VCO run on the branch
(5174). Before it: the full suite on SIF-1..28 - 54/54 scripts, 2,213 checks, none failed, none flaky.

### SIF-30 The RL model window grows with its window (2026-10-20)

**Found** (the user's 411 saved models, the branch on 5174). The window's content stopped at 1060 px whatever the window:
in a 1600 px window the saved models' table had 788 px and empty margins of 270 px each side; its rows were 77 px tall
(names, "Trained on" and "Started from" over two or three lines).

**Changed** (`roadster.css`, `RlModelWindow.tsx`): the content grows to 1440 px; its sentences stop at 120 characters; the
template's size boxes (hidden, heads, layers), its lists and its one-line boxes stop at 640 px ("48" needs no 450 px box).

Measured: the window's own 1180 px - content 1060 -> 1165 px, the models' table 788 -> 893 px, rows 77 -> 59 px (median);
1600 px - content 1440, table 1168 px, rows 46 px. No sideways scrolling.

**Checked.** `tsc` clean; `pdk_check` 36 (its "the list spans the narrow column" now reads "the list spans the column, up
to 640 px" - written when the list sat in the page's narrow column), `model_chooser_check` 76, `network_panel_check` 58,
`encoder_models_check` 24, `graph_view_check` 63, `module_fold_check` 30, `model_structure_check` 29,
`mode_suggestion_check` 20, `network_inputs_check` 8, `dom_identity_check` 56, `looks_check` 63, `reliability_check` 20,
`reward_block_check` 32, `room_check` 22, `task_rows_check` 52, `typing_check` 47.

### SIF-31 No text cut by its box: the Components list and the editors' numbers (2026-10-20; correcting SIF-28)

**Found** (a scan of every visible box on the page and in the windows, the user's VCO task on 5174). The RL model window's
Components list kept the old look's 26 px height: 12 px of room for a 16 px line under the Roadster padding, so "Device
families (any PDK)" was cut through the middle. And with the circuit shown, the editors' numbers gave way before the text
columns: "3.25 ko...", "1.215 G..." - already on the live page (measured at 1366 px), and SIF-28, which gave numbers their
natural width but no minimum, cut "3.25 kohm" at 1680 px too.

**Changed** (`roadster.css`): the Components list and its button take the height their line needs (19 px of room); a
number in the editors keeps at least its 11 characters (105 px), so the text columns give way first. In the narrowest
layout (circuit shown at 1366 px) the table scrolls sideways a little further (Specs 160 -> 271 px; it did before too).

Measured (numbers cut / total, page widths 1680 and 1366, circuit hidden and shown, Parameters and Specs): none of 14 and
16 in every case; the live page cut 1 and 2 at 1366 px with the circuit shown. The box scan finds no other cut box in the
page, the RL model window (three Modes, folds open), Runs or Tasks.

**Checked.** `tsc` clean; `pdk_check` 37 (one new: the list's room against its line; and its "the list read again" now
waits for the list - read at once it failed once in a two-lane run, then passed five times), `editor_columns_check` 14 (one
new: a number's 11-character minimum) and the 19 other editor checks - 687 checks.

### SIF-32 Data tables: numbers right-aligned in figures of one width (2026-10-20)

**Found** (the user's VCO run, the branch on 5174). Data tables showed numbers left-aligned in proportional figures, so a
column of losses or counters ("-0.0262258", "0.000591748", "-1.71668"; "736", "5800") could not be read down by magnitude.

**Changed** (`RunTabs.tsx`, `roadster.css`): a column whose shown values are all numbers (not an id column) is right-aligned
in tabular figures, its title too - as a spreadsheet's. Ids, times, words and JSON cells keep their own look.

Seen: evaluations - episode_step ... policy_version; metrics - raw_value, threshold_lower/upper, violation; learner_updates -
evaluations_collected, actor_loss ... update_seconds.

**Checked.** `tsc` clean; `looks_check` 64 (one new, with a number column added at the end of its fixture row: the cell and
its title right-aligned in tabular figures, an id cell not), `export_check` 22, `training_data_check` 117,
`dom_identity_check` 56.

### SIF-33 Output files: sizes right-aligned (2026-10-20)

**Changed** (`RunTabs.tsx`, `roadster.css`): the Size column of Output files ("159.2 KiB", "580 B") is right-aligned in
figures of one width, its title too - as Data tables' numbers (SIF-32).

**Checked.** `tsc` clean; `files_tab_check` 20 (one new: the sizes and their title right-aligned, tabular), `export_check` 22,
`looks_check` 64; the user's VCO run (508 files) on the branch (5174).

### SIF-34 Numeric cells right-aligned, as they always meant to be (2026-10-20)

**Found.** `td.numeric` asks for right alignment (styles.css), but `table.grid td { text-align: left }` outranks it, so in
every grid table the numbers sat on the left: the Runs window's Duration, Seed, Evaluations ("800 / 800", "0 / 0") and First
feasible; the Tasks list's Rev, Sizes / results and Runs; the saved models' Evaluations and Save points; the model facts,
the circuit picture's and the Issues tables' numbers.

**Changed** (`roadster.css`, `TableView.tsx`; `RunList.tsx`, `TaskList.tsx`, `ModelChooser.tsx` mark their number columns
`numeric`): a numeric cell is right-aligned, and so is the sortable title over such a column.

Measured (the user's runs and tasks, the branch on 5174): both tables still fit the window's 1500 px (1234 px in 1234).

**Checked.** `tsc` clean; `run_list_check` 121 (one new: Seed's title and cell right-aligned), `task_list_check` 80,
`task_run_check` 31, `model_chooser_check` 76, `network_panel_check` 58, `model_structure_check` 29, `graph_view_check` 63,
`blocking_issues_check` 39, `pdk_check` 37, `encoder_models_check` 24, `looks_check` 64, `dom_identity_check` 56.

### SIF-35 Output settings and Research experiments speak words (2026-10-20)

**Found** (the right column with every fold open, the branch on 5174). Lists and facts showed program values: Raw waveform
retention "best_and_failures", Split "unspecified", Generalization level "unseen_circuit_class", the output folder's
"Allowed / writable: true / true"; and that facts table squeezed its names into two or three lines ("Allowed / / writable")
beside room for the values.

**Changed** (`OutputPanel.tsx`, `ResearchPanel.tsx`, `roadster.css`): the lists show words - "None", "Best design and
failures", "Every evaluation"; "Unspecified", "Train", "Unseen circuit class" ... - and store the same values as before;
"Allowed / writable" reads "yes / yes"; the facts table has the run's and model's facts look (each name on one line,
muted), 40 px shorter.

Also: the design-loop look scripts never press Calibration - it starts a calibration run; its confirm dialog blocked one
look (the request filter refused the start; nothing ran).

**Checked.** `tsc` clean; `output_panel_check` 66 (one new: yes / yes, the retention list's words and value, names on one
line), `module_fold_check` 30, `pdk_check` 37, `looks_check` 64, `room_check` 22, `reliability_check` 20.

### SIF-36 A saved model's compatibility reads as a list of problems (2026-10-20)

**Found** (the user's model dffrx1_t2 (30) in the RL model window, the branch on 5174). Its compatibility with the task on
the page listed 20 checks in their backend order, and two of the problems were dumps of two Python dictionaries in red -
"goal/spec input schema: incompatible - saved {'descriptor_version': ..., 'descriptor_columns': [...], ...} != current
{...}" took twelve lines; "network architecture" two. What differs could not be read off. The title said "for fine_tune".

**Changed** (new `CompatibilityList.tsx`, used by the saved model's Details and by the chosen model's facts; `roadster.css`):
the problems come first; a "saved {...} != current {...}" pair is shown as the keys whose values differ - "encoder_type
GraphGPS -> Graph Transformer" (a design by its name), "attention_mode none -> local_port_attention", "layout spec-set-v1 ->
spec-input-v2", "version (not there) -> ...", long values cut at 70 characters with the whole in the tooltip - and the
pair in full behind "Both values in full"; anything else keeps its sentence. The checks that pass are folded under one line
("The other 16 checks pass"). The title names the Mode as its button does: "for Fine-tune".

**Checked.** `tsc` clean; `model_chooser_check` 77 (its "Compatible for fine_tune" now "for Fine-tune"; one new, with D's
answer made incompatible for one look: the summary, the two key lines, the folded passing check),
`network_panel_check` 58, `mode_suggestion_check` 20, `encoder_models_check` 24, `model_structure_check` 29,
`module_fold_check` 30, `graph_view_check` 63, `reward_block_check` 32, `room_check` 22, `looks_check` 64,
`dom_identity_check` 56. (`reward_v2_frontend_check`, stand-alone, reads `li.issue.error` items starting
"reward_settings: incompatible": they are kept.)

### SIF-37 The circuit graph view: its design by name, its tools uncut, its colours as drawn (2026-10-20)

**Found** (the user's model dffrx1_t2 (30), Circuit graph view, the branch on 5174). The title said "graph_gps 48/4/4"; all
twelve tools kept the old look's 26 px with the Roadster padding - 12 px of room for a 16-18 px line, so the lists' words
("Local port edges", "block 1", "mean of 4") were cut through the middle; and the reading line said "Thick blue = much
attention ... Blue border = a device whose size the policy sets" while both are drawn in the page's accent - red since the
Roadster look (record 7.360).

**Changed** (`CircuitGraphView.tsx`, `roadster.css`): the title names the design ("GraphGPS 48/4/4 - save point ...", as
the models' table does); the tools keep their compact 26 px without padding above and below; the reading line says "Thick
red ... Red border ...". (The node colours - blue nmos, red pmos, yellow bipolar - are the picture's own and were right.)

**Checked.** `tsc` clean; `graph_view_check` 64 (one new: the title's design name, no tool shorter than its line),
`model_chooser_check` 77, `network_panel_check` 58, `looks_check` 64; the box scan of the open graph view finds no cut box.

### SIF-38 Run status's facts in the page's words (2026-10-20)

**Found** (the user's VCO run, Run status scrolled through, the branch on 5174):
- "Worst applicable values: f_center_hz=1.28318e+9 Hz; kvco_hz_v=-1.09516e+9 Hz/V; inl1=-0.00179155 1; ..." - six digits,
  exponents, a "1" for a ratio; "Nominal values" listed the same specs in another order;
- "Best design: Full-plan feasible; reward ; hard violation 0" (no reward recorded: an empty clause);
- "worst hard-spec share 0.500000"; "Tightest clearance: 0.0459112 f_center_hz";
- "Connection: unknown 57244 s old"; "last save 2026-10-16T17:20:54.493259+00:00", "Last checkpoint
  2026-10-16T17:21:11.499986+00:00" - UTC where every other time on the page is this computer's;
- "(dispatch #1, 1 completed, 3 in flight, 1 launches)".

**Changed** (`RunTabs.tsx`): values in their units as the editors write them, three digits ("f_center_hz = 1.28 GHz;
kvco_hz_v = -1.1 GHz/V; inl1 = -0.00179; ... power_w = 284 uW"), Nominal values in the order of the row above; the reward
clause only when there is a reward; "share 0.5"; "0.0459, on f_center_hz"; "15 h 56 min old"; local times with the UTC
in the tooltip; "1 launch".

**Checked.** `tsc` clean; `save_now_check` 25 (one new: Last checkpoint in this computer's time, the UTC in its tooltip),
`run_control_check` 101, `calibration_check` 38, `calibration_save_check` 22, `export_check` 22, `training_tab_check` 89,
`run_list_check` 121, `task_run_check` 31, `dom_identity_check` 56, `looks_check` 64, `agent_window_check` 28,
`room_check` 22. (`reward_v2_frontend_check`, stand-alone, reads "Executed reward ... worst hard-spec share 0.5" and "Best
design" starting "Nominal feasible only": both hold.)

### SIF-39 A run's Details in the Runs window: values in their units (2026-10-20; as SIF-38)

**Found.** A run's Details wrote its best design as "gain_db=41.5" without units and its sizes as
"input_pair_width=2.34558e-6 m  load_capacitance=2.5e-13 F"; "First feasibility" said "1 launches".

**Changed** (`RunList.tsx`): results in their units to three digits, sizes to six, as Run status (SIF-38) and the editors
write them, set apart by "; " - real data: "f_center_hz = 1.28 GHz; kvco_hz_v = -1.1 GHz/V; ... power_w = 284 uW",
"wn_main = 4.69 um; ... r1_r = 2.74675 kohm; r2_r = 927.891 ohm"; "1 launch".

**Checked.** `tsc` clean; `run_list_check` 121 (its Details expectations now "gain_db = 41.5" and "input_pair_width =
2.34558 um; load_capacitance = 250 fF"), `task_run_check` 31, `dom_identity_check` 56. Before it: the full suite on
SIF-1..38 - 54/54 scripts, 2,223 checks, none failed, none flaky.

### SIF-40 A task's Details: the searched sizes first, the tied rows folded (2026-10-20)

**Found** (the user's VCO task in the Tasks window, the branch on 5174). Details listed all 66 parameter rows; the 7 sizes
the task searches stood among 59 rows that only follow them ("wn_main_f1 ... Follows wn_main").

**Changed** (`TaskList.tsx`): the table holds the searched rows, each with the rows tied to it ("7: DUT/MNA2, DUT/MNA3,
DUT/MNA4, DUT/MNB1, ..." - every one in its tooltip); the tied rows have their own table in a closed fold, "59 more rows
follow a searched one". The heading still counts both (7 searched, 66 rows).

**Checked.** `tsc` clean; `task_list_check` 80 (its rows check now: 1 searched parameter, its tied row in the closed fold,
1 probe, 1 spec), `task_rows_check` 52, `dom_identity_check` 56; the user's VCO task on the branch (5174).

### SIF-41 The model in use names its reward (2026-10-20)

**Found** (the RL model window, Fine-tune, the user's VCO model). "The model in use" wrote its reward as the stored names:
"Reward: constraint_violation_v2; compressed".

**Changed** (`RlModelWindow.tsx`): "Constraint violation, version 2; violation shape compressed" - an unknown version with its
underscores as spaces, none as "Legacy nominal" as before; the stored names in the tooltip.

**Checked.** `tsc` clean; `network_panel_check` 58, `model_chooser_check` 77, `reward_block_check` 32,
`mode_suggestion_check` 20, `looks_check` 64; the user's VCO model on the branch (5174).

### SIF-42 Run status's Best design tile to three digits (2026-10-20; as SIF-38)

**Found** (a calibration run of the user's, graphgps_ldo1_t3, on the branch on 5174): the Best design tile said "hard
violation 0.309319" above facts that now say three digits. (The calibration table itself reads well.)

**Changed** (`RunTabs.tsx`): "hard violation 0.309".

**Checked.** `tsc` clean; `looks_check` 64, `room_check` 22, `calibration_check` 38, `export_check` 22,
`run_control_check` 101. The look answers a load's "Switch to ...?" question with OK (the preview page's own editors only)
- unanswered, it held a headless page until the look's time ran out.

Full suite on SIF-1..42: 53/54 scripts, 2,222 checks; `save_now_check` failed once on "one press sends exactly one
`checkpoint` command" - it read the command list the moment the button said "Saving...", before the request reached its
intercept (its later "only checkpoint was ever sent" passed). The step now waits for the command; then three runs of
`save_now_check` + `run_control_check`, 126 checks each, none failed.

### SIF-43 The Windows menu sets "Close all" apart (2026-10-20)

**Changed** (`roadster.css`): in the banner's Windows menu a thin line stands between the windows listed (Runs, Tasks ...)
and "Close all", an action on all of them (it was already muted, but looked like one more window).

**Checked.** `task_list_check` 80, `looks_check` 64; the menu with the Runs and Tasks windows open at 1366 px (5174).

### SIF-44 A run's Mode in words everywhere, its best numbers to three digits (2026-10-21; from the readability audit)

**Found.** Four places still wrote a run's Mode as its key while the rest of the page says New model / Fine-tune /
Evaluate only (SIF-6/11/14): the "Running now" card ("real:mscr_ota7t · scratch · model ota7t"), a saved model's Details
in the RL model window ("Saved by ... · fine_tune, seed 0, completed"; History "· scratch · 800 evaluations"), and a run's
Details in the Runs window (History "· scratch ·"; "Runs that started from its model: 2026-10-20 13:09:11 fine_tune
(dffrx1_t2 (3))"). Run status read the Mode alone, so a Baseline or a Calibration said "New model - no weights loaded".
The card wrote the best reward to six digits ("reward -0.0370463"; "reward ," with none recorded), the Runs Details the
best violation too ("violation 0.309319"), where Run status writes three.

**Changed** (`RunBrief.tsx`, `ModelChooser.tsx`, `RunList.tsx`, `RunTabs.tsx`; all through `runMode`): the card reads
"mscr_ota7t · Fine-tune · model ota7t (2)" (the task's name as the Runs window gives it, its key in the tooltip; "Mode
unknown" for none) and "best so far: reward -0.037, meets every spec" ("no reward recorded" for none); "Saved by ... ·
Fine-tune, seed 0, completed"; History "real:mscr_ota7t · New model · 800 evaluations" (the key kept there, as before;
"1 evaluation", "evaluations unknown"); "2026-10-20 13:09:11 Fine-tune (dffrx1_t2 (3))"; "violation 0.309"; Run status
"Baseline", "Calibration" (no model at all, so nothing after it), "Offline training - no weights loaded", "New model - no
weights loaded" as before.

**Checked.** `tsc` clean; `run_list_check` 121 (its "Runs that started from its model" now /Fine-tune \(fixture \(2\)\)/,
its History "synthetic:gpdk045_ota5 · New model · 60 evaluations · fixture"), `run_control_check` 102 (new: the card reads
"fixture_task · New model · no model saved"), `model_chooser_check` 78 (new: "Saved by" reads "New model, seed 1,
completed"), `room_check` 22 ("New model - no weights loaded" holds), `save_now_check` 25, `dom_identity_check` 56; none
flaky.

### SIF-45 The header's blocking issues and the real-run questions count in the right number (2026-10-21; from the readability audit)

**Found.** The header's red button, shown whenever a start is blocked, read "1 blocking issue(s)" (the user, on seeing it:
"whats the problem here"), and its list's head the same; the list said "Start and the baseline simulation stay disabled",
a button now called Calibration. The question before every real Start, Resume and Continue asked "Authorize a budget of
600 candidate evaluation(s)?" ("a total budget of N candidate evaluation(s)", "up to N more candidate evaluation(s)", "Run
a budget of N candidate evaluation(s)" for ngspice). The Start and Calibration tooltip counted errors alone, where the
button counts errors and blockers: with one of each it said "has 1 blocking issue" beside a button that said 2, with a
blocker alone "has a blocking issues: the red button in the header lists them". A configuration the schema rejects
pointed to 'the red "blocking issue(s)" button'.

**Changed** (`format.ts`: `plural`, moved out of `ModelChooser.tsx`; `contract.ts`: `BLOCKING_LEVELS`, which `Issues.tsx`
and `launch.ts` share; `Issues.tsx`, `launch.ts`, `api.ts`): "1 blocking issue", "3 blocking issues"; "Start and
Calibration stay disabled until all of them are resolved."; "Authorize a budget of 600 candidate evaluations?", "a total
budget of 1 candidate evaluation" ("its candidate evaluations" with no number, as before), "up to 40 more candidate
evaluations"; the tooltip "Calibration: The configuration has 3 blocking issues: the red "3 blocking issues" button in the
header lists them." and "... has a blocking issue: the red "1 blocking issue" button in the header lists it."; "the red
blocking-issues button in the header lists it too". `docs/workbench.md` and `docs/functionality-reference.md` quote the
button as "N blocking issues".

**Checked.** `tsc` clean; `blocking_issues_check` 42 (its button counts now "3 blocking issues", "1 blocking issue", "2
blocking issues"; new: the list's head, and the tooltip for 2 errors + 1 blocker and for a blocker alone),
`matched_devices_check` 30 (it looks for "the red blocking-issues button in the header"), `run_control_check` 102,
`consistency_check` 14, `launch_recovery_check` 20, `corner_check_check` 37, `model_chooser_check` 78; none flaky.

### SIF-46 Run configuration says why RL model needs a look, and opens it (2026-10-21; from the readability audit)

**Found.** The only sign on the main page that the next run's model has a problem, red or amber under the model line,
read "Review the settings in RL model." for each of its nine reasons: the saved model NOT compatible, its check failed, a
message of the window's (a template value not saved, the templates or a save point not read), an encoder that is
unavailable, the network taken back to the saved model's, a budget too small to learn, the soft actor-critic values that
learn late, the template's saved values ignored, this run's values not the template's. It never said which, and "RL model"
was plain text beside a button called "RL model...": the window had to be opened and searched every time.

**Changed** (`useRlModel.ts`: `networkReason`, the first reason that applies, the errors first so its words match the
notice's colour; a window message that is an error carries its own few words, `reason`; `RunConfiguration.tsx`;
`styles.css`): "Review the settings in RL model... - the budget is too small for the network to learn.", its "RL
model..." a link at the sentence's size that opens the window. The other reasons: "with 1 update per evaluation and a
starting temperature of 0.2, the network learned late or not at all in tests", "the saved model is NOT compatible with
this run", "the saved model could not be checked", "a template value was not saved in the backend", "the templates could
not be read from the backend", "the chosen save point could not be read", "Graph Transformer is unavailable", "the
network was taken back to the saved model's", "the saved Graph Transformer template values could not be used", "this
run's values differ from the Graph Transformer template". `docs/workbench.md` quotes the new notice. The checks'
`lib/rl_networks.mjs` `openNetworks` can press another "RL model..." than the module's button.

**Checked.** `tsc` clean; `reward_block_check` 32 (its notice now read whole, with the soft actor-critic reason, and the
window opened from the notice's link; the two "no notice" checks match any notice, where the old exact text would have
passed for the wrong reason), `module_fold_check` 30 (a budget of 1: "... - the budget is too small for the network to
learn."), `network_panel_check` 58, `model_chooser_check` 78, `mode_suggestion_check` 20, `room_check` 22; none flaky.

### SIF-47 The Training tab names its run as its chips do, and its readout in words (2026-10-21; from the readability audit)

**Found.** The Training tab's first line named the shown run by its folder, "scratch__seed1__live" (the Mode's key and the
folder's id), while its "(shown)" chip and the chart legends right under it say "fixture_task · seed 1 · 05/10, 11:00"
and the tab strip "... · New model, seed 1 · ...". The line above every chart wrote the row's phase and its design's
status as keys: "Evaluation 81 · episode_reset · episode 0-000017 step 0", "... · warmup · ...", "status invalid_design",
and an Evaluate-only run read "frozen_eval" on every chart. The Compare list counted "· 1 evaluations"; the "Evaluation
success rate" chart said "(a frozen run)" and "only a frozen run does", a Mode the page calls Evaluate only.

**Changed** (`TrainingTab.tsx`, `training/catalog.ts`): the head reads "fixture_task · seed 1 · 05/10, 11:00", the name
its chip and the legends give it (the folder until the run list has the run; the whole path in the tooltip, as before).
The readout reads "random warm-up", "episode start", "evaluation (no learning)", "pre-flight", "AI warm-up", "AI search",
"AI rescue" for those phases, and "result invalid design", "result did not converge", "result timed out" for a design that
was not ok; a phase or status the lists do not know (search, adapt, baseline, measurement_error, the learner's initial and
online) reads with spaces for its underscores. The rows keep their keys: the charts' categories are worked out from them
as before. The Compare list "· 1 evaluation" (`plural`); the chart "(an Evaluate-only run)" and "only an Evaluate-only run
does"; its tooltip's source column keeps the phase key (`frozen_eval`), as the data dictionary names it.

**Checked.** `tsc` clean; `training_tab_check` 90 (its hover line now /search|random warm-up|episode start|baseline/ with
no key left and a timeout as "result timed out"; new: with the run list the head reads "fixture_task · seed 1 · <made>",
the folder in its tooltip), `training_data_check` 117, `looks_check` 64; none flaky.

### SIF-48 Directions that point at buttons and tasks that exist (2026-10-21; from the readability audit)

**Found.** Four messages sent the user to something that is not there. Let go on a paused run asked "... it can still be
continued later (press "Runs..." at the bottom, double click the run, then Run status > Continue).": since record 7.267 a
double click in the Runs window LOADS the run - its task into the editors, its model as the next run's model - so
following the dialog changed the draft. A configuration that still asks for training corners read, in red, "Training
corners require the registered real OTA7 task." (that task was deleted in record 7.128, and no task trains at corners
since), "A positive launch cap is required for training corners." and "Training corners require zero automatic retries."
- none said which control to change, and the two fields sit in the closed Limits fold under other names. "Not now" on
"Calibration ready" said, in its tooltip and in the message after, "The proposals stay under Run status of that run, with
Apply calibration.", a button a task saved from a cell does not have (it gets Apply and save / Apply only). Every visit to
Output files ended its tool line with ""Open local folder" is not offered: no desktop integration is available from a
browser.", about a button that does not exist, and one file counted "1 files".

**Changed** (`RunControl.tsx`, `RewardConditions.tsx`, `page/calibrationOffer.ts`, `App.tsx`, `RunTabs.tsx`): Let go
asks "... it can still be continued later: press "Runs..." at the bottom, open the run's Details, then Continue... (or
Show results, then Continue... under Run status)."; the corner errors read "No task can train at corners now: choose
Nominal only under Training conditions.", "A positive launch cap is required for training corners: set Max Spectre
launches under Limits." and "Training corners require zero automatic retries: set Max retries per evaluation under Limits
to 0."; "Not now" says "... with its Apply buttons."; the Output files line reads "7 files, 8.2 MiB." and the notes alone
("1 file" with `plural`), and Copy run path's tooltip ends "A browser cannot open a folder itself." The audit proposed
"paste it into Explorer to open the folder" there; the path is the server's (a Linux path), which Explorer does not
open, so the tooltip does not say so. The checks' expectations all still hold (`reward_v2_frontend_check` looks for
"zero automatic retries" and "positive launch cap", both kept; it is stand-alone and was not run).

**Checked.** `tsc` clean; `run_control_check` 102, `calibration_check` 38 (its "Nothing was changed. The proposals stay
under Run status of that run" prefix kept), `calibration_save_check` 22, `files_tab_check` 20 (the hint reads "7 files,
8.2 MiB." and nothing after it), `module_fold_check` 30; none flaky.

### SIF-49 A cell names the unit a plain number is in, and says why a text was refused (2026-10-21; from the readability audit)

**Found.** The tooltip of every bound (Parameters' Lower, Upper, Step; Specs' Lower, Upper), of its header and of
the help line a header opens said "Type 450n, 0.45 um or 0.4mA; a plain number is in the unit the row shows." No row has
shown its unit since the Unit column went (record 7.208): a W row stored in m shows "1 um", and a "2" typed there,
meant as 2 um, became "2 m". A word typed into a number without a unit (Ratio, Soft weight) or into a JSON cell
vanished when the cell lost focus, with no word. The formula bar refused it with ""half" is not a number: type it plain,
with an exponent (2.5e-6) or an SI letter (2.5u); the unit column says the unit.", which points at a column that is gone.
A non-number in a bound read "... type it as 400u, 400 uA, 0.4m or 4e-4." in every row, so a length row suggested a
current and then refused it. An unknown unit ended "... or with the unit (400 uA).", and a row without a unit was named
"this row holds a plain number ()". Every empty Lower or Upper of a one-sided spec, and an empty Scale, showed a bare "-".

**Changed** (`Editors.tsx`, `cells.tsx`, `units.ts`): the help reads "... a plain number is in the row's own unit, not
in the prefix the cell shows (each cell's tooltip names that unit).", and a bound's tooltip ends with "A plain number
here is in m." (`plainNumberIn`). It says nothing more for a count, nothing more for a greyed follower field, and for a
row without a unit "This row has no unit yet: a value typed with one (400 uA) gives it that unit." The reading rule
itself is unchanged (record 7.208 chose it). A word left in Ratio, Soft weight or another unitless number now shows
under the formula bar as ""half" in Ratio is not a number: type it plain (0.5), with an exponent (2.5e-6) or an SI
letter (2.5u).". A JSON cell's says "... is not JSON: a list is written as ["a", "b"].", and the formula bar's refusal
ends at "(2.5u).". In a bound, a non-number reads "... type it plain (0.5), with an exponent (2.5e-6), an SI letter
(2.5u) or this row's unit (0.5 m)." (in the row's own unit; a count or a unitless row gets the three forms only). An
unknown unit reads "... this row holds a length (m). Type the number with an SI letter (400u) or with this row's unit
(400 m).", "... this row has no unit. ... with a unit the page knows (400 uA)." or "... this row holds a count. ... or
plain (400).". An empty Lower or Upper on Specs reads "no limit" and an empty Scale "auto"; a follower's greyed field
and every other empty number keep "-". The checks' pinned starts all still hold: unit_text_check's ""abc" is not a
number" and "this row holds a length (m).", sheet_check's "this row holds a count", formula_bar_check's "is not a
number". reward_v21_check reads the Scale's value (still empty), not its placeholder. It is stand-alone and was not run.

**Checked.** `tsc` clean; `unit_text_check` 14 (new: the full refusals in a length row, a count row and a row without a
unit; `plainNumberIn` for m, um, kohm, a count and no unit), `sheet_check` 44 (new: the metre row's Lower tooltip ends
"A plain number here is in m."), `editor_columns_check` 17 (new: a one-sided spec's empty Upper reads "no limit", the
Scale's placeholder "auto", and "half" typed into Ratio is said under the formula bar with the ratio kept),
`formula_bar_check` 19, `typing_check` 47, `find_fill_copy_check` 30, `unsaved_rows_check` 25 (its tooltips still start
with "Saved in the task: ..."); none flaky.

**Review follow-up.** The review found one slip, in this entry only: "Found" listed Specs' Scale among the bounds whose
tooltip, header tooltip and help line carried the stale sentence. It never did: `Editors.tsx` gives normalization_scale
its own guidance ("How far outside its limit a value counts as a miss of 1. ...") after VALUE_HELP is added, which drops
it. The list now reads "Specs' Lower, Upper". "Changed" still holds: the Scale cell's own tooltip does end with
`plainNumberIn`'s sentence. No code changed; nothing to type-check or run.

### SIF-50 The editors say "searched rows", name a new Probe or Spec by its tab, and say what an import needs (2026-10-21; from the readability audit)

**Found.** The fact line over Parameters read "Independent action variables: 7 of 66 rows." ("?" until validation
answered), while the task's Details call the same rows "searched" (SIF-40: "7 searched, 66 rows"). Matched devices said
"Independent action variables now: 5." and headed its review "Tie 2: independent action variables 5 -> 3", which reads like
an order to tie item 2. The Specs hint "The margin also measures the distance to 0. If 0 is only a physical floor, choose
Margin sides: upper." named no row, pointed at a column hidden behind More columns, and stayed after the row's Margin sides
was set to upper. Add on Probes gave a row "measurement_3", Add on Specs "target_4": the section keys, where the page says
Probes and Specs (a Maestro task's new Probe ID is read-only and kept that name until an output name was typed). An import
of a file that is not JSON showed the browser's parser text ("Import failed: Unexpected token 'a', "abc" is not valid
JSON"), and a row without its ID read "Import failed: every Specs row needs its metric_id", a key no header shows. A block
paste over one cell a leader decides said "1 cell that follow another field kept."; fill down already said "that follows".

**Changed** (`Editors.tsx`, `MatchedDevices.tsx`, `docs/workbench.md`): the fact line reads "Searched rows: 7 of 66."
("..." until validation first answers, "?" when it answered without a count), its tooltip starting "The rows the optimizer changes itself; the others follow a tied row
or stay fixed."; Matched devices reads "Searched rows now: 5." and "2 ties: searched rows 5 -> 3" ("1 tie: ..."; the arrow drawn as before). The
zero-floor hint (reward v2.1 B3, kept on purpose) shows only for an interval from 0 whose Margin sides is not upper, and
reads "supply_power_w: the margin also measures the distance to 0. If 0 is only a physical floor, set Margin sides to upper
(More columns)." (several rows: their IDs joined by ", "). New rows are named parameter_N, probe_N and spec_N (`NEW_ID`;
Parameters unchanged). A file that is not JSON reads "Import failed: the file is not JSON. Choose a file written by Export
JSON, or a list of rows."; a row without its ID "Import failed: every Specs row needs its Spec ID ("metric_id" in the
file)" (Parameters: its ID, Probes: its Probe ID); every other import error keeps its text. The paste note says "1 cell that
follows another field kept.", as fill down does. `docs/workbench.md` (Matched devices) says "the count of searched rows
before and after". `reward_v21_check` pinned the old hint: it now expects the fixture's one interval from 0,
"supply_power_w: ...", with the new ending (its row 0 is a ">= lower" row, so the hint names supply_power_w, not row 0). It is
stand-alone and was not run.

**Checked.** `tsc` clean; `matched_devices_check` 30 (its three pins now read "Searched rows now: 5.", a heading that starts
"2 ties: searched rows", and "Searched rows: 3 of 5."), `editor_columns_check` 22 (new: Add names probe_3 and spec_3; an
interval from 0 to 1 V is named in the hint with "(More columns)", and the hint goes once that row's Margin sides is upper),
`spec_equations_check` 34 (new: a file holding "abc" and a Specs row without metric_id are refused in the words above; its
"neither a workbench configuration" pin unchanged), `typing_check` 47 (parameter_N unchanged), `sheet_check` 44 (the plural
"2 cells that follow another field kept." unchanged), `find_fill_copy_check` 30 (fill down's "1 cell that follows"
unchanged); none flaky. The singular paste note has no check of its own: a one-cell block over a follower needs a column
order the sheet check does not set up, and the text now matches fill down's, which is pinned.

**Review follow-up.** The review found one slip: the count placeholder became "..." for every missing count, which reads
as "still counting". App keeps the last validation answer while the next is on its way (`keepPrevious`), so after the first
answer a missing count means validation could not count: a "Tied to" naming a row that does not exist, a ratio that cannot
be used or a tie cycle (`independent_action_count` returns None), a refused configuration, or no answer at all (`rejected()`
gives `facts: {}`). The line then said "Searched rows: ... of 66." for as long as the problem stayed. Matched devices draws
its line only once its answer is here, so "..." there never meant pending: only a route answer with
`independent_before = null`. Now the Parameters line reads "..." only while `validation` is null and "?" when an answer
has no count; Matched devices reads "?" again, as before SIF-50. "Changed" above now says so. `tsc` clean;
`editor_columns_check` 23 (new: its canned report has no count, and the line reads "Searched rows: ? of 5."),
`matched_devices_check` 30; neither flaky. Matched devices' "?" has no pin: its fixture answers always carry a count.

### SIF-51 The import and Matched devices confirmations name the tab, the header and the unit as the editors do (2026-10-21; from the readability audit)

**Found.** The table read just before Apply - the "Confirm import" box after Import JSON, and Matched devices >
Review... - showed the program's values. Matched devices' review read "parameters | w_in_b | modified | binding_group |
| w_in_a", then "lower | 0.000001 |" and "upper | 0.00001 |": the section key where the tab says Parameters, "modified",
the field name where the header says "Tied to", a width as a bare number in m where its cell says "1 um", and a cleared
value as an empty cell. An import of Specs rows read "targets | extra_0 | added | metric_id", and a Probes or Specs
import showed "measurements", "normalization_scale", "direction_after_feasible" where the page says Probes, Scale and
Objective.

**Changed** (`editorRules.ts`, `DiffView.tsx`, `Editors.tsx`, `MatchedDevices.tsx`): the tabs' names (`SECTION_TITLES`)
and the headers' words (`LABELS`, now holding the five words Editors.tsx set apart: Expression, Judged at, Missing value =
failed, Margin sides, Scale) moved from `Editors.tsx` to `editorRules.ts`, so the headers and the confirmations read one
list; the headers are unchanged (the schema sends no labels of its own). The review now reads "Parameters | w_in_b | changed
| Tied to | (empty) | w_in_a", "Lower | 1 um | (empty)", and an import "Specs | extra_0 | new | Spec ID | (empty) |
extra_0", a replaced row "deleted". The tab and the field keep the program's names in their tooltips (parameters,
binding_group); the row's class stays diff-added / diff-removed, so the colours are unchanged. A number of a field that
carries its row's unit (Parameters' Lower, Upper, Step, Initial value; Specs' Lower, Upper, Scale) is written as its cell
writes it, in the row's unit: the one the row has in the editors, or, where the diff adds the row or changes its unit (an
import may), that side's own. An empty value or empty text reads "(empty)". Other values are written as stored (true, >=,
the Notes text). Left as it was: Matched devices' note in the follower's Notes, "Its own range was 1e-06 .. 1e-05 m.", is
written by the backend (`src/gator_workbench`), outside this branch's frontend scope.

**Checked.** `tsc` clean; `matched_devices_check` 32 (new: the review's first rows read exactly as above, with
"parameters" and "binding_group" in the tooltips; its six-cell Row pin unchanged), `spec_equations_check` 35 (new: a
20-row Specs import names Specs (tooltip targets), extra_0 "new", the replaced row "deleted", and "Spec ID" with metric_id
in its tooltip, no bare metric_id), `sheet_check` 44 (its "binding_group" -> "Tied to" header pin still holds after the
move), `editor_columns_check` 23, `edit_state_check` 24; none flaky.

**Review follow-up.** The review found one slip, in words only: the code is right. This entry, the commit message and
three comments (`DiffView.tsx`, `MatchedDevices.tsx`, `matched_devices_check`) said the old table showed "1e-06" and
"1e-05", a width as a bare exponent. The old DiffView wrote `exact(v)`, which is `String(v)`, and JavaScript writes 1e-6
as "0.000001" and 1e-5 as "0.00001" (it keeps an exponent only below 1e-6). "Found" above and the three comments now say
"0.000001" / "0.00001", a bare number in m; the commit message stays as pushed. The backend's Notes sentence "Its own
range was 1e-06 .. 1e-05 m." really is written that way (Python's text), so it stands. No code changed: `tsc` clean,
`matched_devices_check` 32 (only a comment changed in it).

### SIF-52 The ngspice and PDK windows name no other PDK, and count and size things in words (2026-10-21; from the readability audit)

**Found.** The ngspice window's help ("Models the deck does not define (a PDK cell as X1 ... <name>)") and the placeholder
of its kinds box gave as examples two device names from another foundry's PDK library, which the house rule does not allow
(docs/workbench.md named one too). Its Check summary read "2 elements (1 vsource, 1 nmos), 3 nets, 3 values a run can
vary, 1 results.": the program's kind keys, and no singular. Its diagnostics fold read "1 diagnostics", each line starting
with its code ("unknown_device: x1: subcircuit ..."), the pattern SIF-5 removed from the editors' Issues column. Load said
"Loaded /x/ota.cir (2345 bytes).", and the PDK window's "Model files read" gave a model file as "48213337 bytes". The
window's first paragraph said a saved task "stands in the Registered task list", a name no window carries (the window is
"Tasks"). In the RL model window, the Components line for "Device families (any PDK)" said "The list of a new model since
record 7.298.", and the folded "What the component list changes" said a PDK component's parameters "can also be varied
(...) - on the MOCK backend; a real circuit still writes only what its profile allows": the workbench has had no MOCK task
since record 7.128, and "profile" is a retired word.

**Changed** (`Ngspice.tsx`, `Pdk.tsx`, `docs/workbench.md`): the examples are neutral, "(a PDK cell as X1 ... my_nfet)"
and "my_nfet=nmos my_pfet=pmos" (the docs: "a PDK cell such as `my_nfet`"). The Check summary reads "2 elements (1 voltage
source, 1 nmos), 3 nets, 3 values a run can vary, 1 result.": vsource, isource and unknown read voltage source, current
source and unknown part (resistor, capacitor, inductor stay), with an s for more than one; nmos and pmos stay as the
deck's .model lines write them, and a kind the list does not know is shown as sent. Every count there uses `plural`
(format.ts). The diagnostics fold reads "1 diagnostic", and each line is the message alone, with "warning: unknown_device"
on hover. Load says "(1.3 KiB)" for the example deck (`bytes`, as the Output and Runs views write sizes); "Model files read" writes
"46.0 MiB" with "48213337 bytes" on hover. The first paragraph says "It then stands in the Tasks window as
ngspice:<name>". The Components line says "A new model uses this list.", and the help "Its parameters can also be varied
(lengths, counts, resistances, capacitances, inductances, voltages) by a Parameters row; what a real run may write in
Virtuoso is decided by each instance's property form.", as docs/workbench.md says under "Varying more than w, l, m, nf, r,
c, ind, dc". Left for the audit batches that own those files: the same diagnostics fold and "N results:" in the circuit
column (`CircuitBrowser.tsx`, `Left.tsx`), and "the Registered task list" in Delete task's tooltip and confirmations
(`Left.tsx`, `taskActions.ts`).

**Checked.** `tsc` clean; `ngspice_window_check` 43 (new: after Example the green line reads "Loaded
<repo>/examples/circuits/ngspice_ota5_level1.cir (179 B). Check it, then save it as a task."; the kinds box's placeholder
and the help give the neutral names; the summary line reads exactly as above; a canned diagnostic reads "1 diagnostic",
its message alone, "warning: unknown_device" on hover; its "2 elements" and "3 values a run can vary" pins unchanged),
`pdk_check` 39 (new: the device-families line says "A new model uses this list." with no record number, and the help names
no MOCK backend and says what a Parameters row varies and what decides a real run's writes; the fixture's model file is
now 48213337 bytes and reads "46.0 MiB" with the exact count on hover; its /device families of any PDK/ and /loads with
any PDK/ pins unchanged); neither flaky.

**Review follow-up.** The review found one slip, in words only: the code is right. "Changed" above said Load reads
"(179 B)" for the example deck, but 179 B is the length of `ngspice_window_check`'s canned deck (its mocked
/api/ngspice/read answers `size: DECK.length`). The real examples/circuits/ngspice_ota5_level1.cir is 1345 bytes and the
backend sends its `stat().st_size` (`ngspice_tasks.py`), so the real page's green line reads "(1.3 KiB)"; "Changed" now
says so. "Checked" stays: it describes the check, whose fixture deck does read "(179 B)". The commit message stays as
pushed. No code changed: `tsc` clean; no check pins this text, so none was rerun.

### SIF-53 Fixed sentences name the Modes as their buttons do: New model, Fine-tune, Evaluate only (2026-10-21; from the readability audit)

**Found.** Fixed sentences still named the Modes by their keys, although the buttons say New model, Fine-tune and
Evaluate only (`MODE_NAME`; SIF-21 fixed two tooltips). The question on a Start with a model trained on another task
ended "Load this model for a NEW task (fine_tune creates a new run with a parent)?". The page's own reason beside
Continue... for a run saved by older optimizer code ended "Its model still loads in a new run: fine-tune or frozen.", and
the Runs window's Saved state fact for such a run ended "only that version can continue it; fine-tune and frozen still
load its model". An incompatible model's line read "NOT compatible - there is no fallback to scratch for Fine-tune" in a
saved model's Details, and "Compatibility for Fine-tune: NOT compatible - there is no fallback to scratch" under The model
in use in the RL model window. Under "Evaluate only: its own settings" the one setting was "Frozen actions
[deterministic]", with "sampled" as the other choice and nothing to say what either does.

**Changed** (`launch.ts`, `RunList.tsx`, `ModelChooser.tsx`, `RlModelWindow.tsx`, `docs/workbench.md`): the question
reads "Load this model for a NEW task? (Fine-tune makes a new run that starts from this model; the model's own run is not
changed.)". The page's own Continue reason ends "Its model still loads in a new run: Fine-tune or Evaluate only.", and
Saved state "only that version can continue it; Fine-tune and Evaluate only still load its model". The Details line reads
"NOT compatible for Fine-tune - it cannot be loaded, and a run never falls back to New model" (a compatible model still
reads "Compatible for Fine-tune"), and the RL model window "Compatibility for Fine-tune: NOT compatible - it cannot be
loaded, and a run never falls back to New model". Evaluate only's setting is "Actions [Deterministic]", with Sampled as
the other choice, and its tooltip says "Deterministic: each step takes the policy's mean action, so the same state gives
the same design. Sampled: each step draws an action from the policy, as in training." (the actor's `sample` takes `mu`
when deterministic, `rsample()` otherwise); the stored values stay `deterministic` and `sampled`, and the model line
and the header's Next line still write "deterministic actions". docs/workbench.md says the same in its Continue paragraph and its RL model window
section. Left as it was: "this configuration still says resume" (NO_MODE in `launch.ts`, Run configuration's notice and
the model line), record 7.267's chosen words, pinned by `mode_suggestion_check`. The backend's own continuation answer
(`src/gator_workbench/runs.py`, outside this branch's frontend scope) still ends "Its model still loads in a new run:
fine-tune or frozen.", and the page shows that answer as sent once the check has answered; the page's own sentence is
shown only before then, or with a backend that has no continuation check. So `run_control_check`'s fixture keeps the
backend's words (its `OLDER` text and `/fine-tune or frozen/`), and the audit's two updates there were not made.

**Checked.** `tsc` clean; `run_control_check` 102 (its older-code pins unchanged, as said above), `run_list_check` 121
(the Saved state pin now ends "Fine-tune and Evaluate only still load its model"), `model_chooser_check` 79 (the
incompatible summary pin now reads exactly as above; new: in Evaluate only the setting under its heading reads
"Actions", its tooltip starts "Deterministic: each step takes the policy's mean action" and names Sampled, and it offers
Deterministic and Sampled with the values deterministic and sampled, deterministic chosen), `network_panel_check` 58,
`mode_suggestion_check` 20; none flaky.

### SIF-54 Run status says its facts in words: connection, reward, saving, run folder, jobs at once (2026-10-21; from the readability audit)

**Found.** Run status printed the connection's state as the backend's key: "not_applicable 15 h 56 min old" on every MOCK
or ngspice run ("not_ready", "unknown" elsewhere), and an empty badge (class state-undefined) when a status had no
connection, while the header's pill and the Connection window say "n/a", "NOT READY". Its "Executed reward" row began with
a bare "compressed" and never named the reward ("compressed; worst hard-spec share 0.5; objective weight 1; margin weight
1"), where the RL model window says "Constraint violation, version 2; violation shape compressed" and the reward block
"Objective bonus weight" and "Tightest-margin bonus weight". "Persistence: commit 812, flushed 812, 793.3 KiB table data;
last save 2026-10-16 18:21:11" gave the store's sequence counters, with a failure at the end. "Run directory" copied the
path on a click with no tooltip and nothing to say it had; the Runs window's "Run folder" says "Click to copy" and
"copied". The jobs at once had three names: "none (concurrency 4)" here, "Parallel simulations 4" in the Runs window's
Details, "Concurrent Spectre jobs" in Run configuration. "Tightest clearance" was the only place saying "clearance"; the
Training tab's chart of the same number is "Tightest margin". "First feasible design: none yet" stood on runs that had
ended, and so did the Training tab's "First passing design". Data tables' tool line read "5800 rows (snapshot at commit
812); last 25 shown." and "1 rows (snapshot at commit 3); last 1 shown.".

**Changed** (`format.ts`, `Connection.tsx`, `rlModelText.ts`, `RlModelWindow.tsx`, `RunTabs.tsx`, `RunList.tsx`,
`TrainingTab.tsx`): the Connection window's words for a state moved to format.ts as `CONNECTION_STATE` (Connection.tsx
imports it under its old name), and Run status's Connection badge uses them: "n/a", "NOT READY", "not checked"; a state
the list does not know reads with spaces for its underscores, and a status without a connection reads "not reported", no
badge. The badge's class still carries the key, so its colour is unchanged. Executed reward reads "Constraint violation,
version 2; violation shape compressed; worst hard-spec share 0.5; objective bonus weight 1; tightest-margin bonus weight
1": the name from `REWARD_NAME` (moved from RlModelWindow.tsx to rlModelText.ts and shared), the settings by
`REWARD_NAMES`, as the reward block names them. The saving row is "Saved to disk: last save 2026-10-16 18:21:11 · 793.3
KiB of table data", with "last save <UTC> (UTC); commit 812, flushed 812" in its tooltip, and "failed: <error> · " first
when the store failed (the cell stays red then). "Run folder" has "Click to copy" and shows "copied" for 1.5 s after a
click, as the Runs window's Details do. Active workers reads "none; up to 4 concurrent Spectre jobs" ("up to 1 concurrent
Spectre job"), and the Runs window's fact is "Concurrent Spectre jobs". The margin row is "Tightest margin". "First
feasible design" reads "none" once the run has ended (completed, stopped, cancelled or failed, with no worker alive) and
"none yet" before; the Training tab's "First passing design" tile and table cell follow the same rule, the shown run by
its status, a compared run by its row in the run list unless its last read found its worker alive. Data tables reads
"5800 rows; the last 25 shown." ("1 row; ..."), with "Snapshot at commit 812" in the tooltip. Left as they were, as the
audit's verdict said: the feasible / passing / violation words of the Training tab and the Runs window, chosen by records
7.215 and 7.360, the Runs window's "First feasibility: not reached" among them. `reward_v2_real_check` (stand-alone, needs
evidence folders; not run) now looks for "Tightest margin"; `reward_v2_frontend_check`'s pins ("compressed; worst
hard-spec share 0.5") still hold. The docs quote none of these texts.

**Checked.** `tsc` clean; `run_control_check` 106 (new: on the FIXTURE run the facts read Connection "n/a", Active
workers "none; up to 1 concurrent Spectre job", Saved to disk "-" and Run folder with "Click to copy", with no
Persistence or Run directory row; "First feasible design" reads "none yet" while the run works and "none" once it is
cancelled; a click on the run folder, the clipboard stood in for, copies the path and shows "copied", then the path
alone again), `export_check` 27 (new, on a real MOCK run's status: "Saved to disk" reads "last save <local time> · 86.0
KiB of table data" with "commit 12, flushed 12" in its tooltip; Executed reward reads "Constraint violation, version 2;
violation shape capped; worst hard-spec share 0; objective bonus weight 0; tightest-margin bonus weight 0"; "Tightest
margin" stands beside the best design; the ended run's tile reads a count or "none"; Data tables reads "12 rows; the last
12 shown." with "Snapshot at commit N" in its tooltip), `training_tab_check` 91 (new: the failed run, which never passed,
reads "none" for its first passing design), `run_list_check` 122 (new: Details says "Concurrent Spectre jobs 2", no
"Parallel simulations"), `connection_panel_check` 81, `model_chooser_check` 79, `dom_identity_check` 56, `save_now_check`
25, `room_check` 22, `files_tab_check` 20; none flaky.

**Review follow-up.** The review found one slip, in the Training tab: the test "unless its last read found its worker
alive" applied to the shown run too, against what "Changed" above says. That read (`comparedState`) is written only for
compared runs and never cleared, so a run compared while its worker lived and then shown, in the same tab, kept its old
entry: once it ended without a passing design, Run status read "none" and the Training tab's "First passing design" went
on reading "none yet" until the tab was made again - the text this record set out to fix. Now the compared read counts
only for a run compared at that moment (`others`); the shown run goes by its status alone, as "Changed" says.
`training_tab_check` has a new check of that case: the failed run compared while its answers say its worker lives, taken
off, then picked in the run window, reads "none" (without the fix it read "none yet", seen failing first). `tsc` clean;
`training_tab_check` 92.

### SIF-55 The Connection window in words: its parts, its failures, its times (2026-10-21; from the readability audit)

**Found.** Before a real Start, Calibration or Corner check whose connection test could not tell, the page asked
"Connection layers are UNKNOWN: tunnel, session_readiness, spectre_license.\nUnknown is not OK. Proceed anyway?" - the
backend's layer keys, and no word on what to do instead. The Connection window's Details table listed the same keys and
the reason codes as its text ("session_readiness | UNKNOWN | never_checked"). A failed Connect SSH or Set up local bridge
read "Connect failed: ssh_failed - TimeoutError: ...", code first. Every connection error was the browser's own text, so
a backend that had stopped showed "Failed to fetch", in red under the header's Connection pill; that note floats over the
row under the header (record 7.182) and stayed until a later action in the window went well, with no way to close it.
The Folders section did the same with its errors. With a run active, the Details footer printed "last successful bridge
interaction: 2026-10-21T08:14:02.512+00:00".

**Changed** (`format.ts`, `launch.ts`, `Connection.tsx`, `ConnectionFolders.tsx`, `roadster.css`): format.ts has
`LAYER_WORDS` / `layerWords` for the backend's ten layer keys (its two lists in connection.py): bridge package, connection
settings, SSH tunnel, bridge in Virtuoso, Virtuoso session, Spectre, Spectre license, SSH login, ngspice program, test
simulation; a key it does not know reads with spaces for its underscores. The question reads "These parts of the
connection are not known to work: Virtuoso session, Spectre license.\nCancel, then press "+ Spectre / license" in the
Connection window; or OK to go ahead anyway." - "Test connection" when no Spectre part is among them, and "go ahead"
since Resume and Continue ask it too. Details shows each layer and reason in words, the key in its tooltip ("Virtuoso
session | UNKNOWN | never checked"); the state badges keep the pill's words. A failed Connect reads "Connect failed: ssh
failed - TimeoutError: ..." ("Set-up failed: ..." on this machine), the code in the line's tooltip. The audit proposed
the diagnostic alone, without the reason; it stays after the reason here, since the bridge's diagnostic can be as bare as
"installed 1.2.3" (`bridge_version_unverified`) or "missing settings: ['daemon_host']". Errors in the window, under the
pill and in Folders are said as the rest of the page says them (`plainError`): "The workbench backend did not answer: it
may have stopped (start it again with gator_workbench.cli serve), or the connection to it dropped."; the backend's own
refusals read as before. The note under the pill has "Click to close" and a pointer, and a click closes it; the next
failure shows it again. The footer gives the bridge interaction in local time, "2026-10-21 09:14:02", with "UTC: ..." in
its tooltip. Left as they were: api.ts `gateText` ("Virtuoso cannot be reached (tunnel)", pinned by
`virtuoso_source_check` and `working_copy_check`), the badges' mixed case (shared with the pill, pinned throughout
`connection_panel_check`), and "Last test took 0.4 s" (the audit's optional rounding). The other places of XC-11 and XC-13
(Corner check, Output settings, circuit diagnostics) belong to other batches. The docs quote none of these texts.

**Checked.** `tsc` clean; `connection_panel_check` 85 (Details' first column now reads "connection settings", "SSH
login", "ngspice program", "test simulation" with the keys as tooltips; new: a failed set-up reads "Set-up failed: bridge
version unverified - installed 0.0.FIXTURE Next step: FIXTURE next step." with `bridge_version_unverified` in its
tooltip; an old result's reasons read "stale result" with `stale_result` in the tooltip, and an active run's footer reads
the local time with "UTC: ...+00:00" in its tooltip; a page-open test with no answer at all puts "The workbench backend
did not answer ..." under the pill, with "Click to close" and a pointer, and a click takes it away),
`corner_check_check` 37 (its fixture names `spectre_license` now, and the question must read "These parts of the
connection are not known to work: Spectre license." and point at "+ Spectre / license"), `virtuoso_source_check` 95,
`working_copy_check` 29, `looks_check` 64; none flaky.

**Review follow-up.** The review found one slip: the pointer rule took every paragraph straight under the pill
(`header .connection-launcher > p`), and the note "The browser blocked the new window. Allow pop-ups for this page, then
press the button again." is one too (`Blocked`, a `<p class="error">` in the same section). It showed the hand but had no
click and no "Click to close", so pressing it did nothing - against what this record set out to do. The closable note
now has its own class, `connection-note`, and only it gets the pointer; the blocked note keeps the arrow.
`connection_panel_check` finds the note by that class and has a new check: a plain `<p class="error">` under the pill,
as the blocked note is drawn, keeps the arrow (the old rule matched it). `tsc` clean; `connection_panel_check` 86.

### SIF-56 The message line under the header keeps a selection, names the run by its folder, and the first screen says what to do (2026-10-21; from the readability audit)

**Found.** Any click on the message line under the header closed it, and only the pointer said so: no tooltip, no mark.
Dragging across the line to copy it ends in a click on the line, so selecting an error or a run's path took the line
away. After Start the line was the absolute path first, the useful words at its end: "Run directory:
/mnt/d/gator/outputs/real-mscr_ota7t/2026-10-21_09-14-02_scratch_seed0 Virtuoso 2 took it."; after Resume or Continue
"Continuing in the original run directory: <path>", and after Let go "Left paused, nothing deleted: <path>" - while the
page's other messages name a run by its folder. If the backend did not answer as the page opened, the whole page was
"Backend not reachable: Failed to fetch" (the browser's own words), with nothing to press; before that, every page
opened on "Loading schema...".

**Changed** (`App.tsx`, `panels/RunControl.tsx`, `roadster.css`): a click on the line still closes it, but a click that
ends a selection of its text keeps it, and the line's tooltip says both: "Click to close (selecting text keeps it).". A
muted "x" at the end of its first line shows that it closes; it is drawn by CSS (`.banner::after`), so the line's text is
still the message alone, which the checks read whole (the audit's close button would have put "Close" into it). After
Start the line reads "Started fixture_task__scratch__seed0__0001." (the MOCK notice before it, the session note after
it, as before), after Resume or Continue "Continuing <folder> in its own folder.", after Let go "Left paused, nothing
deleted: <folder>"; each carries the full path as its `title`, first in the line's tooltip, and Run status shows it as
before. The task's baseline started by Save task adds "It is the task's baseline simulation." ("The task's baseline
simulation has started." read twice with "Started"). A page whose backend does not answer as it opens reads "The
workbench could not open. The workbench backend did not answer: it may have stopped (start it again with
gator_workbench.cli serve), or the connection to it dropped." with a Reload button (`plainError`, as everywhere else; a
refusal from the backend reads in its own words), and the page opens on "Opening the workbench...". The docs quote none
of these texts.

**Checked.** `tsc` clean; `run_control_check` 108 (the start check now wants the line "FIXTURE MOCK DATA: nothing was
started. Started fixture_task__scratch__seed0__0001." and its tooltip "<the path>\nClick to close (selecting text keeps
it)."; new: after Resume it reads "Continuing <folder> in its own folder.", after Let go "Left paused, nothing deleted:
<folder>" of that step's own run, each with the path first in its tooltip; the first run failed only on that new Let go
check, written against the first run's folder instead of the later start it lets go of), `calibration_check` 38,
`calibration_save_check` 22, `run_list_check` 122, `task_run_check` 31, `launch_recovery_check` 20, `save_now_check` 25,
`consistency_check` 14, `callouts_check` 8 (the MOCK line keeps its frame with the room for the mark); none flaky.

**Review follow-up.** The review found two slips, both real. The tooltip "Click to close (selecting text keeps it)." held
only for a drag: the first click of a double click - the usual way to take one word, and a run's folder name is one word -
comes before anything is selected, so it closed the line before the second. The line now closes 0.5 s after a click
(Windows' default double-click time; the page cannot read the user's own), and only if nothing is selected by then; a
second or third click cancels the close, and a newer message is never closed by an older click. The tooltip stays as it
was, now true. The line's tooltip also showed over its "Technical details", which a click opens without closing the line;
the fold has an empty title of its own now, which keeps the line's tooltip off it. `run_control_check` has two new checks:
a real double click (CDP, clickCount 1 then 2) on the folder's name in the Start line selects
"fixture_task__scratch__seed0__0001" and the line stays, and a single click then closes it; with the old click handler put
back, the first failed (the line was gone). `save_now_check` has one: the refusal line's fold carries `title=""`, the line
"Click to close (selecting text keeps it).". `tsc` clean; `run_control_check` 110, `save_now_check` 26,
`calibration_check` 38, `calibration_save_check` 22, `run_list_check` 122, `task_run_check` 31, `launch_recovery_check`
20, `consistency_check` 14, `callouts_check` 8; none flaky.

### SIF-57 The RL model window has one name for a template, its values and its design (2026-10-21; from the readability audit)

**Found.** In New model the window calls one thing by three names. Its table and buttons say "template" (Templates, Use
template, "The Graph Transformer template, for this run"), but the Advanced fold read "Advanced (stored per encoder, like
the network sizes)" with "...the other settings belong to the selected encoder" (no encoder is chosen any more), the hint
under Templates "...kept per encoder in the backend. Editing a value below saves it for that encoder.", and the box shown
when this run differs "Current run values differ from the saved Graph Transformer defaults (starting preset)." with a
column "Saved default" and the buttons "Use saved defaults" / "Save as defaults". After every edit of a template value the
line under the settings read "Saved in the backend as the graph_transformer setting.", and the model line's tooltip in Run
configuration began "The network in use: graph_transformer, ...". The warning about values that leave the search random
ended "The tested values are 8 updates per evaluation, starting temperature 0.01 and discount 0 (under Advanced).", but
the fields there are "Updates per transition (UTD)", "Initial alpha" and "Discount gamma". The fold "Where the Graph
Transformer values come from" listed "updates_per_transition", "initial_alpha", "hidden_dim" with presets "0.00100000",
"0.0100000" (padded to six digits), and the differences table wrote a structural encoding as "rwse".

**Changed** (`panels/RlModelWindow.tsx`, `panels/useRlModel.ts`, `panels/rlModelText.ts`, `docs/workbench.md`,
`docs/functionality-reference.md`): "template" throughout. The fold reads "Advanced (kept with the template, like the
network sizes)" and "...the other settings belong to the Graph Transformer template."; the Templates hint "...kept per
template in the backend. Editing a value below saves it into that template."; the box "This run's values differ from the
Graph Transformer template (starting preset)." and "This run uses the values shown in the controls. A template's values are
loaded when you use it; they do not replace an existing configuration on page reload.", its columns Setting | This run |
Template, its buttons "Use the template's values" / "Save into the template" (their tooltips name the template). After an
edit: "Saved into the Graph Transformer template." (`DESIGN_NAME`: a template is kept per encoder, so no CircuitGPS
version); the tooltip: "The network in use: Graph Transformer, hidden 48, ..." (`designName`, with CircuitGPS's version).
The warning ends "The tested values are 8 updates per evaluation (Updates per transition), starting temperature 0.01
(Initial alpha) and discount 0 (Discount gamma), under Advanced." - the fields keep their labels, "Initial alpha" being also
the calibration's word. The "Where ... come from" table names each setting as the differences table does ("Updates per
transition (UTD)"), the key in its tooltip, and writes the preset as the Templates table does ("0.001", "0.01"; `num`
padded them, and it is no longer imported there); the differences table writes "RWSE" and on/off. The saved models' Design-cell tooltip keeps the key
(SIF-1). The docs name the new buttons and column.

**Checked.** `tsc` clean; `network_panel_check` 62 (the tooltip must start "The network in use: Graph Transformer,"; the
buttons are found by their new names; new: the box's sentence, columns and buttons as above with no "default" in it, the
message "Saved into the Graph Transformer template." after Save into the template, the Advanced fold's summary and hint
and the Templates hint, and the "Where ... come from" table in words with the key in each tooltip and every preset as
String() of the backend's value), `reward_block_check` 32 (the warning must end with the new sentence; "Use the
template's values" takes it away; the first run stopped after its 22nd check, all the changed ones passed, on "the
DevTools session closed (its window went away)" at the check's own `window.close()`; alone it passed whole: a flake),
`model_chooser_check` 79, `network_inputs_check` 8, `encoder_models_check` 24, `room_check` 22.

**Review follow-up.** The review found one slip, real: `docs/network-presets.md`, which the Templates row of the
functionality reference names as the place to read about the feature, still described the box in the old words - the
"This run / Saved default" table, "Use saved defaults" and "Save as defaults" ("remembers them for this encoder"), in its
paragraph on an existing configuration and again under "The three tested values". Both now name the column "Template"
and the buttons "Use the template's values" / "Save into the template", as `docs/workbench.md` does; the paragraph's
"RL networks..." window and the later "RL networks window" (renamed RL model in 7.265) say RL model. A change to that
doc only: no page code or check text names it, so `tsc` and the checks were not rerun.

### SIF-58 The RL model's facts and limits are counted in words, and the Fine-tune switches say what they do (2026-10-21; from the readability audit)

**Found.** In the RL model window, Fine-tune or Evaluate only with a saved model chosen, "The model in use" read "Training
12000 evaluations, 96000 updates, replay 12000" - no grouping (the warning a little below writes "1,500"), "1
evaluations" for a count of one, and "replay 12000" not saying of what; "Conditions Nominal only; 1 planned" (or "unknown
planned") without saying what was planned; "Operating points enabled" against "off"; and a row "Schema" for the version of
the save point's description. Fine-tune's three switches "Freeze encoder", "Encoder-only transfer" and "Reset critic" had
no tooltip, where every control around them has one, so how the first two differ was said nowhere on the page. In Run
configuration the Limits fold's line, on screen whenever one is set, read "Limits - 1 launches, 1 retries, 86400 s" (the
wall time in raw seconds, a day), and the red line under Concurrent Spectre jobs "This task supports at most 1 jobs."

**Changed** (`panels/RlModelWindow.tsx`, `panels/rlModelText.ts`, `panels/RunConfiguration.tsx`): the facts read
"Training 12,000 evaluations, 96,000 learner updates, 12,000 transitions in replay" (a local `count`: en-US grouping as
ModelStructure writes it, the noun singular at 1, "?" where a model recorded none); "Conditions Nominal only; 1 condition
planned" ("plan not recorded" where the contract holds no plan); "Operating points on" / "off"; and "Metadata version",
its tooltip "The version of the format the save point's description is written in.". The switches have tooltips, worded
from what the backend's `modes.py` does (read only): Freeze encoder "The graph encoders of the actor and the critics keep
their loaded weights; only the actor and critic heads learn." (`EncoderFreeze` freezes the actor's and both critics'
encoders); Encoder-only transfer "Only the encoders' weights are loaded; the actor and critic heads start from new random
weights."; Reset critic "The critics and their target copies start from new random weights; the actor keeps its loaded
ones.". The Limits line reads "Limits - 42 launches, 1 retry, wall time 24 h 00 min" (`plural` with "launches" /
"retries", `durationWhole`); the red line "This task supports at most 1 job: lower Concurrent Spectre jobs.". The
Wall-time field keeps its label ("Wall-time limit (s)", which room_check reads). The docs quote none of these words.

**Checked.** `tsc` clean; `model_chooser_check` 81 (new: the three switches' tooltips; the facts "8 evaluations, 4
learner updates, 8 transitions in replay", "Nominal only; plan not recorded", "off", a "Metadata version" row and no
"Schema"; the incomplete-configuration check's `/10 evaluations, 6 updates/` now reads "6 learner updates" - its first run
failed there, the one pin the audit had not listed), `room_check` 24 (new: with one retry and 86400 s typed, the line reads
"Limits - 42 launches, 1 retry, wall time 24 h 00 min", and "Limits - 42 launches" again once both are cleared),
`network_panel_check` 62, `module_fold_check` 30; none flaky. `reward_v2_real_check` (stand-alone, not run) looked for
"enabled" in the Operating points row: it now reads that row's cells for "Operating points" and "on".

### SIF-60 Output settings in words: the run's paths, the folder list, replay snapshots and the research boxes (2026-10-21; from the readability audit)

**Found.** Under Output settings, "Current run paths" (open whenever a run is shown) listed the backend's keys as row
names ("run", "raw_data", "csv_exports", "simulator_work"; the checks' fixtures "run_dir"), then "bytes written", "last
successful save 2026-10-05T10:21:40+00:00" (raw ISO in UTC, where Run status writes the same save in local time) and
"remote Spectre work dir". The "Replay snapshots (needed for a FULL resume)" box warned, unticked, "Without replay
snapshots checkpoints are weights_only: a full training-state resume of this run will NOT be possible." and the lock hint
said "A resumed run writes back to its original directory." - resume is Continue... since record 7.261, "weights_only" a
raw key, and nothing said Fine-tune and Evaluate only still load the model. "Browse allowed roots..." showed a bare list
("..", "outputs select") that never said which folder it was, its names opened folders but were drawn as plain text, and it
could only be left by choosing one. In Research experiments the Method label and Comparison pair ID boxes held the word
"unspecified" as text: it had to be deleted before typing, and Method label's examples never showed.

**Changed** (`panels/OutputPanel.tsx`, `panels/ResearchPanel.tsx`): the paths' rows read "Run folder", "Raw data", "CSV
exports", "Simulator work folder", any other key in words ("Best designs", "Logs"), the key in the name's tooltip; then
"Bytes written", "Last successful save 2026-10-05 11:21:40" (`stamp`, the ISO with "(UTC)" in its tooltip, as RunTabs
writes it) and "Remote Spectre work folder". The box reads "Replay snapshots (needed to Continue a run exactly)", its
warning "Without replay snapshots this run's checkpoints are weights only: Continue... cannot pick it up exactly; Fine-tune
and Evaluate only can still load its model." ("checkpoints" kept: the "Model checkpoints" box beside it says it), the
lock hint "... A run that is continued writes back to its own folder.". The folder list has a line above it, "The allowed
roots" or "In /that/folder", with a "Close" link; each name is a link ("Open this folder"), the parent "Up one folder", the
button "Use this folder". The backend's reply has no ".." entry (paths.py's browse() sends `parent`), so the audit's
`e.name === '..'` form was not used. The two research boxes show nothing for "unspecified", which is their placeholder
("unspecified - e.g. Scratch, Pretrained-Frozen, Pretrained-Fine-tuned, encoder-only transfer": the research tables'
method labels, kept, not Mode names; "unspecified"); an emptied box stores "unspecified", the backend's default, where it
stored "". XC-11's Corner check and Connection sites belong to SIF-55 and SIF-59; only its Output settings sites are
here. The docs quote none of these words.

**Checked.** `tsc` clean; `output_panel_check` 76 (new: the Replay snapshots label and its warning word for word, gone
when ticked again; the folder list against FIXTURE folders - "The allowed roots Close", a root's name opens "In
/fixture/roots/one Close", "Up one folder" one level down and back, Close leaves the root as it was, "Use this folder" sets
it, and only the folders pressed were asked for), `typing_check` 50 (new: both research boxes start empty with their
placeholders, "Scratch" is stored as typed, an emptied box stays empty and stores "unspecified"), `room_check` 26 (new:
with the run shown, its paths read Run folder (tooltip run_dir), Bytes written, Last successful save, Remote Spectre work
folder, the save as "YYYY-MM-DD hh:mm:ss" with "2026-10-05T00:59:30+00:00 (UTC)" in its tooltip; its fixture status
has a `persistence` now), `module_fold_check` 30; none flaky.

**Review follow-up.** The review found one slip, real: the list's new "Close" only emptied the list. A folder still on its
way (a click on a name, slow on D:) was the newest ask, so its answer opened the list again after Close, and a failed one
showed its error under a closed list; only a change of the root let such an answer go, which is why "Use this folder" had
no such slip. The folder list now asks on its own line (a second `useNewest`): Close lets it go, and so does "Use this
folder" (the same root again changes nothing), as another root still does. Test writability and Measure keep their own
line, so Close drops neither, and a folder click no longer drops a Test writability on its way either (both ran on one line
before, and the later press threw the other's answer away). `output_panel_check` has five new checks: with the folder's
answer held back until after Close, the list stays closed, and Test writability, pressed before and also held, still
answers ("NOT writable"); with a 403 held back the same way, the list stays closed and shows no error. `tsc` clean;
`output_panel_check` 81; none flaky.

### SIF-61 A cell becomes a task, the Tasks window is named as such, and a renamed task is asked about by its name (2026-10-21; from the readability audit)

**Found.** The Virtuoso window, the only place where a task is made from a cell, called what the cell lacked a "circuit
profile". A chosen cell without a task read "Why: it has no circuit profile yet", inside it "the workbench needs a circuit
profile - a checked description of three things:", then "To start a profile for this cell, read it into the workbench";
after the read, the headline said "Read from Virtuoso. Not optimizable yet: it has no circuit profile.". That word was left
over from the "Create profile" button that went on 2026-09-22. Save as, the button that finishes the job, makes a "task",
as the Tasks window and the tab line's tooltip say. Delete task's tooltip and both its questions (Virtuoso and ngspice)
said the task "leaves the Registered task list", a list no window is called any more. A renamed task (record 7.302) was
asked about by its key only: "Delete the task real:fixture_ota?" while the window said "Current task: ota_relaxed" beside
the button.

**Changed** (`panels/VirtuosoWindow.tsx`, `panels/Left.tsx`, `panels/taskActions.ts`, `docs/workbench.md`): the cell's
note reads "Why: it is not a task yet", "the workbench needs a task - a checked description of three things:", "To make
a task of this cell, read it into the workbench ..."; the draft's headline "Read from Virtuoso. Not optimizable yet: Save
as makes it a task." (the prefix most checks look for is kept). Delete task's tooltip and its two questions say "The task
leaves the Tasks window" / "It leaves the Tasks window". A renamed task's question names both: "Delete the task
real:fixture_ota (shown as ota_relaxed)?" (`shownName` from TaskList.tsx, the name the window shows; a task that is not
renamed is asked about as before, "Delete the task real:ota5_v1?"). The ngspice question does the same, as any registered
task can be renamed (the audit named only the Virtuoso one). "Switch to real:...?" and "The workbench follows the task
real:..." keep the key (checks pin them). The ngspice window's own intro already said "Tasks window"; the backend's
blocker under "Technical details" and the matched-devices note keep their "verified circuit profile" (backend words). The
docs' example of a folded line now quotes "Why: it is not a task yet".

**Checked.** `tsc` clean; `project_help_check` 48 (the "Why: ..." line, the folded "needs a task" sentence and no word in
view saying "circuit profile"; "To make a task of this cell"; the draft's headline word for word),
`virtuoso_source_check` 95 ("To make a task of this cell"; "Delete the task real:ota5_v1?" unchanged for a task that is
not renamed), `task_list_check` 81 (new: with fixture_ota renamed ota_relaxed, Delete task asks "Delete the task
real:fixture_ota (shown as ota_relaxed)? It leaves the Tasks window, ...", the window says "Current task: ota_relaxed",
and Cancel sends nothing), `ngspice_window_check` 43, `working_copy_check` 29; none flaky.

**Review follow-up.** The review found one slip, real: a second line of `virtuoso_source_check` was missed. "the limit is
a neutral note in plain words" still asked the window for "circuit profile", and still passed, but no longer on the note:
the window's whole text includes the folded "Technical details", where the fixture's backend blocker says "a native
cellview needs a verified circuit profile". So it tested none of the note's words and wanted the phrase
`project_help_check` now says must not be in view. It now asks for the note's own "it is not a task yet". A change to that
check only: `tsc` clean; `virtuoso_source_check` 95; none flaky.

### SIF-62 Device sizes in units and counts in the right number in the circuit column and the graph view (2026-10-21; from the readability audit)

**Found.** The circuit column's "Instances and parameters" table wrote a device's sizes as JavaScript prints them, "w=0.0000012
l=1.8e-7" (the two spaces between them fold to one), under the heading "Parameters (canonical units)", while the editors
and the run facts write the same sizes as "1.2 um" and "180 nm" (record 7.208). The circuit graph view did the same for a
clicked device: "w = 2e-6, l = 1e-7 - sized by wn", under a Sizes table that says "2 um". Counts kept a fixed plural:
"Hierarchy (1 instances)", "Native schematic ... (1 instances, as read)", "1 diagnostics", and the ngspice task block
"1 results: vout_v". Each diagnostic began with its snake_case code, "unmapped_terminal_role: The terminal ...", the
pattern SIF-5 and SIF-52 removed elsewhere. The graph view's state line said "this save point was written at 20" (or "at
?"), which reads like a clock time though it is the evaluation the save point was written after, and went on "This state
is LATER than the save point". Its block list was labelled "Layer" over options "block 1", "block 2", while the Selected
caption and the connection table say "Block"; Fit was the only layout button without a tooltip.

**Changed** (`panels/CircuitBrowser.tsx`, `panels/CircuitGraphView.tsx`, `panels/Left.tsx`): "Instances and parameters"
has the heading "Parameters" and writes "w = 1.2 um, l = 180 nm, m = 1" (`si` in the unit `kindUnit` gives the parameter,
4 significant digits; a parameter of no known kind keeps its plain number through `short`, an expression stays as it is);
the graph view writes the clicked device as "w = 2 um, l = 100 nm - sized by wn", "c = 1 pF". Counts go through format.ts's
`plural`: "Hierarchy (1 instance)", "(2 instances, as read)", "1 diagnostic", "1 result: vout_v". A diagnostic shows its
words, with "warning: unmapped_terminal_role" on hover, as the ngspice window does since SIF-52. The state line reads
"Evaluation 20 of this run (state before it: ok); this save point was written after evaluation 20." (the clause is left
out when the save point's evaluation is not known), and "This state comes after the save point: the model never saw it
while training." The block list is labelled "Block" ("Readout" for parameter-group attention, as its options), and Fit
says "Fit the whole graph in the view". The status word ("ok") and the Native schematic's raw values as Virtuoso wrote
them ("w=1u") are left as they are. The other parts of these findings were done before: the header's "blocking
issue(s)" in SIF-45, the ngspice window's counts, kinds and diagnostics in SIF-52, the Connection window's failures in
SIF-55. No doc quoted the changed words.

**Checked.** `tsc` clean; `project_help_check` 49 ("Hierarchy (1 instance)" for the saved task; new: the draft's
"Instances and parameters" has the heading "Parameters" and writes "w = 4 um"), `graph_view_check` 66 (new: the state
line word for word with "written after evaluation 20", the block list labelled "Block", Fit's tooltip; a clicked M1 reads
"w = 2 um, l = 100 nm - sized by wn"), `ngspice_window_check` 43 (the circuit column now asked for "1 result: vout_v"),
`circuit_source_check` 15; none flaky.

### SIF-63 Small text at the page's sizes: issues, the toolbar's text buttons, the tie toggle, the task chip, and no help cursor without help (2026-10-21; from the readability audit)

**Found.** The words that say what is wrong with a row were the smallest text on the page. `.issue` kept the old look's
11 px (styles.css), which the Roadster look (record 7.360, "14 px text, readability first") never overrode while it raised
the hints to 13 px: "warning Unit not checked ..." in the editors' Issues column, the "error: ..." lines under the table
and in Matched devices, the level cell of the header's blocking list and a saved model's compatibility problems (smaller
than the 12 px key lines under them) all read at 11 px beside 14 px cells. In the editors' toolbar "More columns (3)" and
"Matched devices..." were 11.5 px fine print among 14 px buttons and fields. The arrow and count beside a leader row's
tick box, the only way to open its tied rows, was 11 px text in about 17 x 11 px of a 36 px row (the old padding
outranked Roadster's). The task chip on the editors' tab line named the task in a 12 px code font, its mark at 11 px,
while the header shows the same name at 18 px and "rev. 3" beside the chip is 12.5 px. And every grid heading showed the
help cursor, also the many with no tooltip: a task's Details (ID / Instance / Parameter), the diff view (Section / Row /
Change), Matched devices, save points (Evaluations / Saved / Kind), the editors' Issues.

**Changed** (`frontend/src/roadster.css`, one block at its end): an issue line reads at 12.5 px wherever it stands (12.5
rather than 13: SIF-5's 40ch cap on the Issues column grows with the font, about 14 % while a row has an issue);
"More columns" / "Fewer columns" and "Matched devices..." at the labels' 13 px; the tie toggle at 12.5 px with 4 px
around it (its mono font and line height kept; the sticky ID column follows the tick-box column's measured width); the
task chip names the task in its button's own font and 14 px (the key stays in `data-task-key`), its mark at 12.5 px; a
grid heading with no tooltip shows the plain pointer (`table.grid th:not([title])`) - a sortable heading always carries
one and keeps the hand, and the calibration table's headings all have theirs and keep the help cursor. The Check now step
list (`.steps-list`, 11.5 px) is left as it is: it is used in fourteen places, and the Connection and Virtuoso
windows already set it to 12.5 px. No words changed; no check or doc pinned the old sizes. `frontend/scripts/looks_check.mjs` pins the new ones.

**Checked.** `tsc` clean; `looks_check` 67 (new: an issue line at 12.5 px, the toolbar's text buttons at 13 px, the tie
toggle at 12.5 px with 4 px padding, the task chip's name in its button's font and size, the "Issues" heading's plain
pointer beside a titled heading's help cursor), `find_fill_copy_check` 30 (the toolbar still on one line at 1366 x 768,
idle and while finding), `editor_columns_check` 23, `sheet_check` 44, `unsaved_rows_check` 25, `blocking_issues_check`
42, `matched_devices_check` 32, `task_list_check` 81, `spec_equations_check` 35, `room_check` 26; and, around the changed
elements, `model_chooser_check` 81 (the compatibility list), `reward_block_check` 32 ("More columns"), `task_rows_check`
52, `output_panel_check` 81; none flaky. `css_order_proof.mjs` was not run: it proves that a regrouped stylesheet adds
nothing, and this change adds rules on purpose.

### SIF-64 Tables and badges at sizes that read: second lines, Details links, state words, and paths that say they copy (2026-10-21; from the readability audit)

**Found.** The Runs, Tasks and saved-models tables are 13 px, but their second lines were 11 px: the design under the
Mode ("Graph Transformer"), the stop reason under the state ("budget used up"), the folder under the date, "(gone)" and a
run's Details facts (the old look's `table.run-table td .hint` outranked Roadster's 13 px hints). "Details" / "Hide
details", the way into every row, was an 11 px word in a hit box about 16 px tall (the old `padding: 0 3px` outranked
Roadster's button padding). The state words - "completed", "failed" in the Runs window and the Training head, the
Connection window's layer states, Run status's connection - were 10.5 px, the "MOCK" and "in use" tags 10 px. Every path
showed the copy cursor: Output settings' "Resolved" and "Mock data root" copy nothing, while "Current run paths" and the
folder in "The model in use is not in this list" copy on a click and did not say so. Measured with the user's runs at
1500 px (the branch's build, its API answered by the live backend, every write refused): at rest the Runs table was
1234 px in its 1234 px, but while a run was live "16 min 33 s so far" on one line made it 1255 to 1262 px, a sideways
scroll.

**Changed** (`frontend/src/roadster.css`, one block at its end; `panels/OutputPanel.tsx`, `panels/ModelChooser.tsx`,
`panels/RunList.tsx`): a list table's second line reads at 12 px; "Details" / "Hide details" at the table's 13 px with
3 px above and below (24 px tall), 6em wide in a table so a toggle moves no column ("Hide details" takes 75.7 px of its
78); a state at 12 px and a tag at 11.5 px, without the old look's letter spacing (as the header's connection pill, the
headings and the tabs since record 7.360: with it the bigger "interrupted" made the State column 9 px wider and the table
4 px wider than its window at rest); the header's pill keeps its 12.5 px. A path reads at 12 px under the text cursor,
the copy cursor only where it says "Click to copy": "Current run paths" and the missing model's folder now say so. A
working run's "so far" may go under its time (a span the cell's nowrap does not hold), the time itself stays whole. With
the user's 605 runs, two of them live: the Runs table 1234 px in 1234, live and at rest (1255 px with the old sizes and
"so far" on one line); the Tasks table 1234 in 1234 (69 tasks). No words changed; no doc quoted the old sizes.

**Checked.** `tsc` clean; `looks_check` 70 (new: a list table's second line, state, tag and Details sizes and padding,
"Details" and "Hide details" the same width, a path's two cursors), `run_list_check` 123 (new: "so far" may go under its
time; the table still fits its 1500 px window), `output_panel_check` 82 (new: "Resolved" shows the text cursor and no
"Click to copy", and a click copies nothing), `room_check` 27 (new: the run folder says "Click to copy" under the copy
cursor), `model_chooser_check` 82 (new: the missing model's folder says "Click to copy"; the table still fits 1100 px),
`task_list_check` 81, `connection_panel_check` 86, `dom_identity_check` 56, `task_run_check` 31; none flaky.

### SIF-65 The Training charts' text at the page's sizes: titles, keys, the readout, the chips and the axis numbers (2026-10-21; from the readability audit)

**Found.** The tab watched through a whole run kept the old look's small sizes on the 14 px page. Each chart's title
("Step reward", the list it is chosen in) was 11.5 px; its series keys ("Training", "Episode start", "limit") 11 px; the
readout line over the plot ("Newest: Evaluation 288 · Training (recorded) -0.05199 · ...") 11 px, the values SIF-25 set
in the text colour among them; the compared runs' chips ("fixture_task · seed 4 · ...") 11.5 px; and the axis numbers
were drawn at 11 px (`TrainingChart.tsx`), none of them overridden by the Roadster look (record 7.360).

**Changed** (`frontend/src/roadster.css`, one block at its end; `panels/TrainingChart.tsx`): a chart's title reads at
13 px, its keys and the compared runs' chips at 12.5 px, the readout at 12 px in its mono font (so its numbers do not
jump about under a moving cursor; it is cut at the chart's width a little sooner, its values first since SIF-7). The axis
numbers and the x axis's word are drawn at 12 px, a whole number of px: uPlot multiplies the digits before "px" by the
screen's pixel ratio, so "12.5px" would draw "12.10px" on a screen of twice the pixels. The y axis keeps its 64 px: the
gain chart's widest number, "400 V/V", ends 12.8 px inside it with eight charts on the page. The "Key numbers" line
keeps its 11.5 px (`.training-keys`, styles.css); the numbers under it already read at the Roadster sizes: one run's
tiles at 12 px labels and 17 px values (record 7.360, user: "make it more compact but keeping the style"), several runs'
`table.grid` at 13.5 px. The "Not on this chart: ..." line already reads at 13 px (a `.hint`: the Roadster `.hint` rule
outweighs its `.training-missing` 11 px) and is left as it is. No words changed; no check or doc pinned the old sizes.

**Checked.** `tsc` clean; `training_tab_check` 95 (new: a chart's title at 13 px, its keys at 12.5 px, the readout and
its values at 12 px in the mono font, the "Key numbers" line still 11.5 px; the compared runs' chips at 12.5 px; every
text the plots draw while six charts are added is 12 px, the markers' 10 px words aside, and no y axis number, "400 V/V"
included, starts left of its canvas - a `fillText` watch in the page), `training_data_check` 117, `looks_check` 70; none
flaky.

**Review follow-up.** The review found two slips, in words only: the code is right. "Changed" above, the `roadster.css`
comment, a comment and a label in `training_tab_check` and the commit message said the key numbers keep their compact
11.5 px. Only the "Key numbers" line over them is 11.5 px (styles.css's `.training-keys`, which the Roadster look leaves
alone), and that line is all the check measures. The numbers themselves already read at the look's sizes: one run's
tiles at 12 px labels and 17 px values (`.key-tile-label`, `.key-tile-value`; record 7.360's compact tiles), several
runs' `table.grid` at 13.5 px. And "Changed" put the "Not on this chart: ..." line at 11 px; it reads at 13 px. It is a
`p.hint.training-missing` (`TrainingTab.tsx`), and roadster.css's `.hint { font-size: 13px }` weighs the same as
styles.css's `.training-missing { font-size: 11px }` and loads after it (`main.tsx`), so it wins. "Changed", "Checked",
the two comments and the label now say so; the commit message stays as pushed. No code changed: `tsc` clean;
`training_tab_check` 95 (only a comment and a label changed in it).

### SIF-66 Text no longer cut short: the header's task name, Continue's "New total", the formula bar's name box and the graph view (2026-10-21; from the readability audit)

**Found.** Four places cut their own text or drawing. The header's task name could not shrink: between about 1201 and
1300 px with a run in the header, the facts' box around it cut it through a letter ("OTA 7T wid"), with no "...", while
the grey facts and the connection's description beside it ended in "..." (record 7.360). Continue...'s "New total" field
was 9ch wide, and the look's padding left room for about six characters, so a used-up run's empty field read "more th" of
"more than 1200". The formula bar's name box was 210 px whatever it held: a column's label and a long Probe or Spec ID
were cut after about 30 characters ("Output name · m_osc_freque..."), and its tooltip gave the column's format only, so
the location could not be read in full. And the circuit graph view's drawing had a fixed `calc(92vh - 118px)`, about 1 px
more than the title and this look's 49 px tool line left: in the RL model window's own 1180 px the tool line takes two
lines, so the dialog scrolled and cut the bottom of the drawing and its tables.

**Changed** (`frontend/src/roadster.css`, one block at its end; `panels/FormulaBar.tsx`). The task name ends in "..." (its
tooltip holds the task) and keeps at least 6 characters. The grey facts give way first: their `flex-shrink` is 1000, not
the audit's 10. Shrinking is weighted by width, so at 10 to 1 a long name (550 px beside 250 px of facts) still took
about a fifth of the shrinking while the facts showed; at 1000 to 1 it gives up less than a pixel before they are gone. The "New total" field is `15ch` plus its
padding and border: "more than 12000" and "1,000,000" fit whole. The name box takes its text's width, 210 px at least and
40 % of the bar at most, and ends a longer location in "...". Its tooltip gives the column's format, then a blank line,
then the whole location; the format stays first, so `formula_bar_check`'s `startsWith('notes (string')` holds. The
error line under the bar keeps its 216 px indent, so beside a wider name box it starts a little left of the text box. The
graph dialog is a column while open: the title, a refusal's line and the tools take their own height, and the drawing
with its tables takes what is left (`flex: 1 1 0`, no fixed height). The title row and the tool line stand 4 px further
apart, because a column's margins add up where a block's overlap. cytoscape 3.34 watches its box with a ResizeObserver,
so the drawing follows when a line above it comes or goes; `CircuitGraphView.tsx` needs no `resize()` call. No words
changed on the page. `docs/workbench.md` (the banner, the formula bar) and `docs/functionality-reference.md` (Title block,
Formula bar) now say how the name and the name box give way.

**Checked.** `tsc` clean. `looks_check` 72 (new: at 1210, 1250, 1300 and 1366 px with the FIXTURE run in the header, the
task's name is never cut by the box around it. The fixture's own name ends in "..." at 1210 px, its facts at 0 px, and is
whole from 1250 px, its facts at 11 to 83 px. A long stand-in name ends in "..." at every width, and only once the facts
are at 0 px). `formula_bar_check` 21 (new: the tooltip ends with the whole location after a blank line. In a 1264 px bar,
"Output name · m_oscillation_frequency_hz" shows whole at 262 px, and a long stand-in stops at 506 px, 40 % of the bar,
with "..."). `run_control_check` 111 (new: the field has 105 px for text; "more than 12000" takes 98 px in its own font,
"1,000,000" 55 px). `graph_view_check` 68 (new: at 1180 x 920 the tools take two lines and the dialog does not scroll,
scrollHeight 844 = clientHeight 844, with the drawing at 711 x 696 px. A refusal's line over the tools takes it to 711 x
654 px, and the drawn canvas follows. At 1680 x 1050 the tools keep one line and the drawing is 850 px tall, close to
the fixed height's 848 px). `find_fill_copy_check` 30 and `reliability_check` 20. None flaky.

**Review follow-up.** The review found two slips, both real, both about the header's task name. Weighting the shrink 1000
to 1 did not make the facts give way first. Once the facts shrank at all, the name gave up a fraction of a pixel, and the
browser draws the "..." for any overflow, less than a pixel too. With the FIXTURE run in the header the name read "OTA 7T
wi..." from 1250 to 1366 px while 11 to 83 px of grey facts showed (0.125 to 0.172 px lost). And `looks_check` could not
see it: it took "cut" from `scrollWidth > clientWidth`, whole pixels both, so "Checked" above wrongly reports the name whole
from 1250 px. The name now never shrinks (`flex: none`); `max-width: 100%` clamps it, with its "...", once the facts' box
is narrower than the name, so the facts are gone by then. Its 6-character floor went with it: a floor wider than the box
is what cut through a letter. `.tb-details`' `flex-shrink: 1000` went too, since the facts are the only part left that
shrinks. The check now compares the name's box with a max-content clone of it, to the 64th of a pixel the layout counts
in, and asks for facts at 0 px wherever a name is cut. Against the old rule it failed (the name cut at 1250 to 1366 px,
facts at 11 to 83 px); now the fixture's name is whole there (0 px lost) and ends in "..." only at 1210 px, its facts at
0 px. A long stand-in ends in "..." at every width, its facts at 0 px. The docs' "first, then the task's name" now holds
as written; the commit message stays as pushed. `tsc` clean; `looks_check` 72, `run_control_check` 111,
`connection_panel_check` 86, `reliability_check` 20; none flaky.

### SIF-67 Save points named by their evaluations in the RL model window (2026-10-21; from the readability audit)

**Found.** The RL model window named a save point by its raw id, zero-padded count and hex tag and all. A saved model's
Details said "With the task on the page - save point ckpt-00000800-003f07c8" under a Save points table that lists the same
point as 800 in its Evaluations column. The same id showed in "Started from" ("(save point ckpt-...)"), in History ("loaded
the one above at its save point ckpt-..."), in the newer save point's note ("the next run loads save point ckpt-..."), in
"Newest model named X: <folder>, save point ckpt-...", in the message after a Use ("The next run fine-tunes X from its save
point ckpt-00000006-a1, with its network ...") and in the headings of the Full layer table and the circuit graph view. The
model line beside the RL model button says "save point 6 evaluations" and "Started from" says "@ 420", so the two could not
be matched by eye.

**Changed.** `frontend/src/lineage.ts`: `pointText(id)` gives "at 420 evaluations" from the id's count, the id itself when it
holds none ("latest"), and "none" for none. `Origin` (`startedFrom`) now also carries `at`, the count its text gives
after "@". `panels/ModelChooser.tsx`: the heading reads "With the task on the page - save point at 800 evaluations", History
"- loaded the one above, its save point at 6 evaluations", and the newer save point's note "the next run loads the save
point at 6 evaluations." "Started from" drops its "(save point ...)" where its "@ 420" already gives the count. It keeps the
hint, in the same words, where it does not: a parent offline model (its text says "(offline)", no "@") or an id without
a count. The audit's fix assumed offline save points' ids hold no count, but they are "ckpt-00000000-...", the 0 that
model's own table shows. `panels/RlModelWindow.tsx`: "Newest model named X: <folder>, save point at 12 evaluations. Use".
`panels/useRlModel.ts`: "The next run fine-tunes X from its save point at 6 evaluations, with its network (one Undo step
takes it back)." `panels/ModelStructure.tsx` and `panels/CircuitGraphView.tsx`: "Graph Transformer 16/2/2 - save point at
20 evaluations". The graph view's heading is not in the audit batch's list of files, but its finding lists it, and it
stands beside the structure dialog with the same form. The id stays on hover everywhere a tooltip can hold it. The message
after a Use is plain text and has no tooltip; the save points table's rows hold the id there. Two save points at the same
count (a pause save and an automatic one) read the same; their ids tell them apart on hover. The Runs window, Run status
and the header's banners are left to their own batch; the model line's tooltip keeps the id. No docs quoted the old words.

**Checked.** `tsc` clean. `model_chooser_check` 83. Its message expectation is now "from its save point at 6 evaluations".
New: the heading reads "With the task on the page - save point at 20 evaluations" with the id "ckpt-00000020-a4" on hover,
and the newer note says "the next run loads the save point at 6 evaluations." Its first run stopped before any check: a new
variable's name clashed with one further down the script. `typing_check` 50 (the suggestion now ends "save point at 12
evaluations. Use", the id on hover). `graph_view_check` 69 (new: "Graph Transformer 16/2/2 - save point at 20 evaluations -
MOCK", the id on hover). `model_structure_check` 30 (new: the Full layer table's heading ends "save point at 20
evaluations", the id on hover). `mode_suggestion_check` 20. None flaky.

### SIF-68 The Tasks window and the editors' tab line say why a control is greyed out, and what a number counts (2026-10-21; from the readability audit)

**Found.** With no connection chosen, Save as on the editors' tab line was greyed out and its tooltip did not say why:
"Save as: Asks for a new task name, with the next available numbered name suggested. Stores the rows ...". The page
already had the reason ("no connection is chosen"), but only Apply and save's request used it; a running save was the only
case the tooltip named ("Waits for the save of ..."). The "Move to…" list above the tables of the Tasks, Runs and RL
model windows stayed greyed out until rows were ticked, with no tooltip; only `docs/workbench.md` said to tick them first.
The Tasks window's All tasks with no task in it (none saved yet, the first read still running, or a list that could not
be read) said "No registered task yet. Save one from ..." and under it "This folder is empty. Select tasks in All tasks,
then use Move to…", to a user already in All tasks. And the Newest run column read "2026-10-09 22:35 · completed · 120
evaluations · first feasible at 34", where the bare 34 after a clock time read like a time.

**Changed.** `panels/TaskSave.tsx`: with no connection, Save as's tooltip reads "Save as: Not available: no connection is
chosen - choose one with the Connection button in the header. Asks for a new task name, ...". A running save's "Waits
for the save of ..." stays first: a save runs only with a connection, so `task_save_check`'s `startsWith('Save as: Waits
for the save of real:ring_osc that is running.')` holds. The audit's fix also gave the rough-frequency case a reason; the
review left it out, since the frequency box and its own Save as stand in view under the toolbar. `panels/Folders.tsx`:
"Move to…" (`FolderMoveBar`, shared by the three windows) has a tooltip: "Tick tasks in the table first, then choose a
folder here." while nothing is ticked ("runs" and "models" in the other two windows), and "Move the 2 selected tasks to a
folder." once rows are ticked ("Move the selected task to a folder." for one; the audit's text said "the 1 selected
tasks"). `panels/TaskList.tsx`: the empty-folder line shows only while there are tasks, as the Runs window's already did
(the RL model window shows no folders at all without a saved model); and the Newest run reads "... · first feasible at
evaluation 34", as the Running now window's "First feasible design at evaluation N" does. No docs quoted the old words.

**Checked.** `tsc` clean. `task_list_check` 85. Its newest-run expectation is now "... · 8 evaluations · first feasible
at evaluation 5". New: in a new, empty folder "Move to…" says "Tick tasks in the table first, then choose a folder here.",
with two tasks ticked "Move the 2 selected tasks to a folder."; with the task list answered empty, All tasks shows "No
registered task yet" and no empty-folder line, and Refresh list brings the four tasks back. `task_save_check` 70 (its
waiting tooltip unchanged). `run_list_check` 123 and `model_chooser_check` 83 (the same "Move to…", found by its
`aria-label`, unchanged). None flaky. The no-connection tooltip has no check: the checks' fixture connection fills an
empty choice by itself, as the page does with the connection file's active profile.

**Review follow-up.** The review found two slips, both real. The edit to Save as's tooltip lost a space: it read "Asks
for a new task name,with the next available numbered name suggested." for every user, though "Found" above quotes it
right; it reads "name, with" again (the same edit's `filter ?'No task matches ...` in `TaskList.tsx` lost one too, in the
source only). And "Move to…" gave a false reason while the folders could not be read: greyed out by `!state.ready` as
well, it still said "Tick tasks in the table first, ...", but the same `ready` greys out every row's checkbox and the
select-all box in all three windows, so the advice could not be followed. While the folders are unread it now says
"Not available: the folders could not be read - press Refresh list." (the alert above the table already says "Press
Refresh list to retry."), or "Not available: the folders are being read." while a read is under way. `tsc` clean.
`task_list_check` 86: new, after the refused folder read, "Move to…" says "Not available: the folders could not be read -
press Refresh list.". `task_save_check` 70, `run_list_check` 123, `model_chooser_check` 83. None flaky.

### SIF-69 Read setup brings a cell's limits in with exact digits, and its help names the Probes columns as their headers do (2026-10-21; from the readability audit)

**Found.** Read setup in the Virtuoso window takes the cell's Maestro specs into Specs, and a limit (Maestro keeps it in
the base unit) is moved into the unit the user chose on the Probe. It was divided by the prefix: 0.7 / 1e-3 is
699.9999999999999, so a 0.7 V spec on a Probe in mV showed Lower "699.9999999999999 mV" (4.5e-7 s into ns:
"449.99999999999994 ns"). The editors write the stored digits as they are, so the long digits reached the Specs cells. The
cell's Scale was divided the same way, and a scale the backend sends as null became 0. `working_copy_check` compared the
limit with a 1e-12 tolerance and its only prefixed case was Hz into GHz, which divides exactly, so it could not see this.
And the fold "How the editors and the cell's Maestro relate" said "Each Maestro output of the cell is a Probes row (source
ade_output, the expression in signal)": `ade_output` is the value of a column the editors never show, and `signal` is the
key of the column whose header reads "Expression".

**Changed.** `frontend/src/panels/WorkingCopy.tsx`: `withSetupRows` moves a limit and the cell's scale with `convert()`
from `units.ts`, which moves the digits rather than computing them, as the editors do when a Probe's unit changes: 0.7 V
is 700 mV, 0.35 V is 350 mV. Division stays for a unit the backend's table does not know (`convert` gives null). A scale
that is not a number stays as it is. The fold reads "Each Maestro output of the cell is a Probes row (its name in *Output
name*, its expression in *Expression*); a Maestro spec is the Specs row on that one probe. ...", the rest unchanged.
`docs/workbench.md` describes the same link by the field keys (`source_name`, `signal`). It is the technical reference,
not a quote of the page, so it stays.

**Checked.** `tsc` clean. `working_copy_check` 31. Its fixture cell has a third output, `vmin`, with a spec of 0.35 ..
0.7 V and a scale of 0.35; the user's Probe for it is in mV. New: that spec arrives as exactly 350 .. 700 mV with a scale
of 350 (the old division gave 349.99999999999994 and 699.9999999999999); the fold names "Output name" and "Expression"
and no longer says `ade_output`. The GHz limit is now compared exactly (`=== 1`, was within 1e-12). Its summary
expectation is now "3 outputs, 3 specs", and it counts three Probes rows more than the starter's, not two.
`virtuoso_source_check` 95. None flaky.

### SIF-70 One name for the last save point in Run status and the Runs window, and Save now says its evaluations once (2026-10-21; from the readability audit)

**Found.** The time a run last saved its model (`last_checkpoint_utc`) had a different name in each place that showed
it. Run status's row was "Last checkpoint", the Runs window's Details said "Last model save", and the rest of the page
(RL model window, Relationships, the Runs window's column help) calls every save a "save point". After Save now, the
line under the header said "Saved at 14 evaluations as save point ckpt-00000014-fixture. The run goes on." and the Run
status row "- Save now: saved at 14 evaluations (ckpt-00000014-fixture)". Both gave the count and then the raw id,
which repeats the count with zero padding and a tag.

**Changed.** `frontend/src/panels/RunTabs.tsx`: the row reads "Last save point". A Save now there reads "- Save now:
saved at 14 evaluations", with "save point ckpt-..." on hover. The row's own tooltip, the time in UTC, is unchanged.
`panels/RunList.tsx`: the Details fact reads "Last save point". `panels/RunControl.tsx`: the line reads "Saved at 14
evaluations. The run goes on.", with "save point ckpt-..." in its tooltip, above "Click to close" (the `title` a message
carries since SIF-56). The ids the audit chose to keep stay as they are: Run status's Mode row ("- from run ..., save
point ckpt-...", SIF-14) and the Runs window's Relationships, History and Saved state (record 7.264). `docs/workbench.md`
(§ Save now): the line "says at how many evaluations, the save point's id in its tooltip". It used to say "and under which
id".

**Checked.** `tsc` clean. `save_now_check` 29. It finds the row by "Last save point" and expects "Saved at 14
evaluations. The run goes on.". New: the line's tooltip starts "save point ckpt-00000014-fixture" and its text holds no
"ckpt-". The row ends " - Save now: saved at 14 evaluations", with "save point ckpt-00000014-fixture" on hover, and no
row is called "Last checkpoint". `run_list_check` 124. New: the Details' "Last save point" gives the run's time, and no
fact is called "Last model save". `run_control_check` 111, `room_check` 27. None flaky.

### SIF-71 The Next line beside Start names the task as the header's title does (2026-10-21; from the readability audit)

**Found.** The header named the same task two ways side by side. Its title gives a task renamed in the Tasks window
(record 7.302) its new name: "ota_relaxed". The grey line beside Start, and the first sentence of Start's tooltip, built
the name from the task's key with "real:" removed, so they kept the old one: "Next: fixture_ota · New model · GT 48/4/4 ·
60 evaluations". Record 7.269 chose "the task without its real: prefix" before tasks could be renamed, and before the
title used the shown name (record 7.360).

**Changed.** `frontend/src/panels/Left.tsx`: the circuit panel says the name its title gives the task through a new
optional prop `onTaskName` (`shownName`, as the title; null while it follows no registered task). `App.tsx` keeps it
(`taskShown`) and hands it to the launcher. `launch.ts` (`useLaunchActions`): the line's task is that name, so a renamed
task reads "Next: ota_relaxed · ...", and the key without "real:" only until the panel has said. A task that is not
renamed reads as before: shownName also keeps "synthetic:" and "ngspice:", so the MOCK stand-in still reads "Next:
synthetic:gpdk045_ota5 · ...". `docs/workbench.md` (§ What Start would start): "the task as the header's title names it
(a saved task without its `real:` prefix, a renamed one by its new name ...)".

**Checked.** `tsc` clean. `task_list_check` 88. New: after the rename the title, the Next line and Start's tooltip all
read "ota_relaxed" ("Next: ota_relaxed · New model · ..."), and when the rename is taken back all three read
"fixture_ota" again. `mode_suggestion_check` 20 and `model_chooser_check` 83 still find "Next: synthetic:gpdk045_ota5 ·
...", unchanged. `run_control_check` 111, `project_help_check` 49. None flaky.

**Review follow-up.** The review found one slip, in words only: the code is right. The new text in `docs/workbench.md`
put the Virtuoso cell under "as the header's title names it", which holds for saved tasks only: for a cell read from
Virtuoso the title shows the project's task name (or "no task chosen"), while the Next line shows library/cell, so the
two still differ there. It now reads "the task (a saved task as the header's title names it: without its `real:` prefix,
a renamed one by its new name - branch record SIF-71; or a Virtuoso cell as library/cell)". The comment over `nextTask`
in `launch.ts` made the same claim ("The task as the title beside it names it"); it reads "A saved task ..." and says
the cell is library/cell, which the title does not show. `tsc` clean. No check reads either text, so none was rerun.

### SIF-59 Times in one local form, temperatures in degC (2026-10-21; from the readability audit)

(Written after SIF-71: this batch's agent finished its edits and its type check, but its time ran out while its checks were
still running, so by the rule it did not commit; the next batches committed only their own files, and the edits were checked
and committed here.)

**Found.** Some times still came in the browser's own form ("16/10/2026, 14:03:22", the Compare list's "20/10, 10:43");
the Corner check's heading wrote "2026-09-22 10:00:00 UTC"; its explainer and corner labels wrote "27 °C", where the page
writes units in English letters.

**Changed** (`format.ts`, `CornerCheck.tsx`, `Pdk.tsx`): the time helpers (timeOrDateTime, dateTimeOrText, dateTimeOrNull,
dateTime, createdAt) write stamp()'s local form "2026-10-16 14:03:22" (a time of today stays time-only; createdAt gives
"10-20 10:43" as runTitle does; the unused savedAt / WHEN went, and CREATED with the old createdAt); the Corner check's heading is the local time with
the UTC in its tooltip, its explainer says "27 degC", "125 degC", "-40 degC", and its corner labels go through cornerLabel()
("SS, 125 degC, 0.9 V"); the PDK window's Loaded cell carries "<time> (UTC)" as its tooltip.

**Checked.** `tsc` clean; `training_tab_check` 95 (its two dates now expected as "MM-DD hh:mm" built in Node),
`connection_panel_check` 86, `run_list_check` 124, `corner_check_check` 39 (the corner label now "ss_hot_low (SS, 125 degC,
0.9 V)"; two new: the explainer in degC with no degree sign, the heading in local time with the UTC tooltip and the grid in
degC), `working_copy_check` 31, `task_run_check` 31, `pdk_check` 40 (one new: the Loaded cell's local time and UTC tooltip),
`training_data_check` 117 - 563 checks, none failed.

**Review follow-up (SIF-59).** The review of bb5107b found the section's claim untrue for one helper: `timeOfDay` (the
Training tab's "last metric ..." and "read ..." times) still used the browser's toLocaleTimeString - "02:03:22 PM" in a
12-hour browser beside the page's "14:03:22". It now writes hh:mm:ss with stamp()'s getters (an unreadable time gives no
text, never "Invalid Date"). The log's "the unused CREATED" was wrong: CREATED went with the old createdAt it served. `tsc` clean;
`training_tab_check` 95, `training_data_check` 117. Before it: the full suite on SIF-1..71 - 54/54 scripts, 2,347 checks, none
failed, none flaky.

### SIF-72 The header's run chip names the run it controls, and the right column says it is for the next Start (2026-10-21; from the real-data survey)

**Found** (survey issues 1, 14, 10 and 3). The page had taken over a live run of graphgps_ldo1 when it opened. The header
read "mscr_vco_lin_c" (the editors' task), the lit "Running", then "running 270 / 800" in borderless mono and "started
elsewhere". After a Load run (1366 px) the bottom tabs' line read "2026-10-16 16:32:51 · mscr_vco_lin_c · New model, seed
0 · completed" under the same header, and no line on the page named graphgps_ldo1: the chip named its run only in its
tooltip, by folder. The chip repeated the strip's word ("Running" beside "running 315 / 800" at 1100 px), and "292 / 800"
named no unit beside the Training tab's 800 and the budget of 200. Run configuration showed "New model ...", budget 200,
while Run status showed the run's Fine-tune and "270 charged / 800": the "Next: ..." line, which says what those settings
are for, is hidden while a run holds the header. And the chip, a button that opens the run brief, read as status text.

**Changed.** `frontend/src/panels/RunControl.tsx`: the chip counts evaluations and leaves the state word to the strip -
"270 of 800 evaluations" while the run works, "at 7 of 60 evaluations" when paused ("interrupted at ... (the worker is
gone)" and "(connection failures)" as before), "completed at 64 of 64 evaluations" or "stopped at ..." once it ended;
"starting", "pausing - waiting ..." and "aborting ..." are unchanged. The lines under the header count the same way ("Paused
at 7 of 60 evaluations: everything is saved.", "The run has ended (cancelled) at 5 of 60 evaluations: ..."). A new
`otherTask` gives the header's run's task when the title names another: by the run list's task key against the followed
task's key, by name where the list gives no key, nothing while the run is not listed. The chip then starts with it in
bold, "graphgps_ldo1 · 270 of 800 evaluations", its tooltip reads "The current run, a run of graphgps_ldo1: <folder>",
and Abort asks "Abort this run of graphgps_ldo1?". `roadster.css`: the chip in the text font with tabular figures and a
1 px outline, as the button it is. `App.tsx` works out that task and whether the header holds a run that works or is
paused. `panels/BottomPanel.tsx`, `panels/RunList.tsx`: while it does and the tabs show another run, the line left of
Runs... reads "Shown: <run>"; beside it (also when the tabs show none) a link "Show the header's run", its folder in the
tooltip, shows that run, as the brief's Show results does. `panels/Right.tsx`, `panels/RunConfiguration.tsx`: then Run
configuration opens with "For the next Start: the run in the header goes on with the settings it was started with." (a
flag through the memoised panel, which changes only when the header's run starts or comes to rest). `docs/workbench.md`
(§ Start, Pause, Resume, Abort): the chip's words and the two cues. Not done: issue 1's third point, "graphgps_ldo1 run,
started elsewhere" on the badge - the chip beside it names the task now, and a longer badge would widen a full header
(issue 14's own review dropped it).

**Checked.** `tsc` clean. `run_control_check` 118 (111 before). Its FIXTURE run is fixture_task's, not the title's task: the
chip is expected as "fixture_task · N of 60 evaluations [MOCK]", "fixture_task · at N of 60 evaluations [MOCK]" when
paused and "fixture_task · cancelled at N of 60 evaluations [MOCK]" when ended; the lines as "Paused at N of 60
evaluations: ..." and "The run has ended (cancelled) at N of 60 evaluations: ..."; both Abort questions as "Abort this run
of fixture_task?". New: the task in bold first, the chip outlined in Segoe UI and its tooltip naming the task; Run
configuration's line absent with no run, there while the run is held, gone once it ended; with the tabs on no run, "Show
the header's run" with the run's folder, and a press shows the run and the link goes; with the tabs on another, paused
run, "Shown: ... · fixture_task · New model, seed 1 · paused · MOCK" and the link naming the live run's folder.
`run_control_live_check` 23: its run is the title's task, so "at N of 20000 evaluations [MOCK]" exactly, no task named,
and "Abort this run?" as before; "stopped at N of 20000 evaluations [MOCK]". `calibration_check` 38 ("completed at 64 of
64 evaluations [MOCK]"). `run_list_check` 124, `looks_check` 72, `room_check` 27, `reliability_check` 20,
`launch_recovery_check` 20, `save_now_check` 29, `task_run_check` 31, `dom_identity_check` 56, `mode_suggestion_check` 20.
None flaky.

**Review follow-up.** The review of 47dc930 found three slips, all real. (1) A Start sets the header's "starting" at once
(launch.ts), but the header holds the run it held before until the backend answers (`launchedRun` -> `control.take`), so
for the whole request an ENDED run counted as held: Run configuration said "For the next Start: the run in the header goes
on ...", the chip read "graphgps_ldo1 · starting" for the new run, and the tab line could offer the ended run. `App.tsx`
now leaves out a launch on its way to another run: a pending Start (it always makes a new run), and a pending Continue
while the header's run has ended (it is of the run the tabs show); Resume of the header's paused run keeps it. (2) The
chip's count wrote "of 1 evaluations" for a budget of 1 (an Evaluate only run, allowed by the schema); `used()` writes it
with plural(), and so do Abort's "Used so far: ..." and Save now's "Saved at 1 evaluation". (3) The tab line's link said
the header's "Pause and Abort act on" its run, also when that run is paused and they read Resume and Let go: it reads
"the one its buttons act on". `tsc` clean. `run_control_check` 120: new, a second Start after the ended run held at
"Starting...": the chip reads "starting [MOCK]", no task, and Run configuration's line is absent; the link's tooltip is
checked whole. `save_now_check` 29. None flaky.

### SIF-73 Matched devices in groups, and the table keeps rows in view (2026-10-21; from the real-data survey)

**Found.** With the user's VCO (mscr_vco_lin_c) the Matched devices box listed "DUT/MNX1 and DUT/MNY1 are a cross-coupled
pair: each gate is on the other's drain." eight times over (MNX1-4, then MPX1-4), so the ties and Review... sat out of
view (survey issue 15). At 1366 x 768 with a run below and the "Loaded run ..." line under the header, the 353 px card
showed four of those bullets, a fifth cut in half, and the table's heading row cut in half with no row under it: SIF-22's
40 % cap was not enough, and record 7.372's fold of the bottom panel only comes with a cell entered, while no cell was in
view to enter (issue 2). And under the empty Find rows box, "Searched rows: 7 of 66." beside the exactly 7 rows the folded
followers leave in view read as the result of a search (issue 20).

**Changed.** `frontend/src/panels/MatchedDevices.tsx`: a kind found three times or more is one line - "8 cross-coupled
pairs, each gate on the other's drain: DUT/MNX1 and DUT/MNY1; DUT/MNX2 and DUT/MNY2; ..." (a mirror as "<reference> into
<copies>") - with each whole sentence in the line's tooltip; a kind found once or twice, and a kind the page has no words
for, keeps its sentences in their places. Once an answer is drawn the box calls `onShown`. `frontend/src/panels/Editors.tsx`:
then, as on a cell entered (one `foldIfCramped` for both), a table left under about four rows on a page wider than 1100 px
folds the bottom panel to its tab line (record 7.372's rule); a tab or the splitter brings it back as before. The fact line
reads "The optimizer searches 7 of 66 rows." - SIF-50's word kept, in a sentence that cannot read as a find result; its
tooltip is unchanged. `frontend/src/roadster.css`: the box (and an import's confirmation in the same place) is capped at
`min(45vh, 40%, max(72px, calc(100% - 340px)))`, so it leaves the table its heading and about three rows where the card
has room for both, and keeps its heading and a line where it has not. `docs/workbench.md` (§ Matched devices): the grouped
line, the cap and the fold. Not done: issue 15's other option, the list folded under the tie table - in one line the ties
come into view as they are; issue 20's move of the line beside More columns - the new words remove the misreading where it is.

**Checked.** `tsc` clean. `matched_devices_check` 37 (32 before): "The optimizer searches 3 of 5 rows." after Apply; new, an
answer with eight cross-coupled pairs added (made up in the backend's sentence) lists four lines, the cross-coupled line
whole with the eight sentences as its tooltip and the three kinds found once as their sentences; at 1366 x 768 with the
bottom panel open the answer folds the panel and the table shows its heading and two whole rows (this card also has the
MOCK line: 575 px, the box 230, the table 127); the panel opened again under the open box, the box keeps 72 px and scrolls
by itself, the table its heading and a whole row (40 % of the 361 px card would leave it none). `editor_columns_check` 23 ("The
optimizer searches ? of N rows."). `room_check` 27, `looks_check` 72, `callouts_check` 8, `edit_state_check` 24,
`reliability_check` 20, `spec_equations_check` 35. None flaky.

**Review follow-up.** The review of 15f2b0a found two slips, both real. (1) The new fact line fixed its noun's number in the
text: a Parameters table of one row read "The optimizer searches 1 of 1 rows." (the old "Searched rows: N of M." had no noun
after the count). `frontend/src/panels/Editors.tsx` now writes `of {plural(rows.length, 'row')}`, as the header's "of N
evaluations" does; the checks' `of \d+ rows` still hold for their 5 and more rows. (2) `docs/workbench.md` said the box
leaves the table its heading and about three rows with no condition, while the cap keeps the box at 72 px at least: on a
card under about 410 px (the bottom panel opened again under the open box, this entry's 361 px case) the table keeps its
heading and about one row. The page now states the condition, as this entry and the CSS comment do. Checked: `tsc` clean,
`matched_devices_check` 37, `editor_columns_check` 23.

### SIF-74 The editors: issue lines, probe chips and tie markers that read (2026-10-21; from the real-data survey)

**Found.** On the user's VCO (mscr_vco_lin_c) the Specs tab's Issues column gave every spec "info 'inl1' is new to the
result registry the netw..." - SIF-5's first clause, cut by the column's 40 characters before its point, which is the
message's second sentence (models saved without the spec do not load) - and its lines touched the cell's left line, left of
the "Issues" heading's text, while f_center_hz's one line sat at the top of its row (survey issue 4): the column took the
editor cells' zero padding and the old look's top alignment. The "Probes: m_f1_hz, m_f2_hz, ... m_power_w" chips, the names
an Equation is typed with, were the old look's 11 px beside the 14 px line (issue 5; SIF-63 raised the other 11 px text and
missed them). On Parameters the tick boxes stood at x 47, 50 and 62 px: the tick-box cell centred the box together with a
leader's count, so "▸7", "▸31" and no count each put the box somewhere else (issues 22, 23 and 33, one defect seen three
times). Not a defect: the warning repeated on every formula row (SIF-5's one line per issue), the empty Tied to of a leader,
and the count's meaning (its tooltip, "7 tied rows follow this one: show them.").

**Changed.** `frontend/src/panels/Editors.tsx`: `ISSUE_HEAD` gives an issue whose first clause the column cuts words of its
own that fit - "info New spec: models without it do not load" for `spec_adds_registry_entry`, and "info The source of this
spec is not recorded" for `basis_not_stated` (the new check found it cut too: "...is not recor..." on a spec with no basis);
every other issue keeps its first clause, and the whole message and the code stay in the tooltip. `frontend/src/roadster.css`
(SIF-74 block): the Issues column is padded 10 px at its sides, as its heading, and centred in the row, nothing added above
or below, so a row with two lines stays as high as the others; the Probe chips are 13 px with 1 px / 6 px around the name
(the line keeps its 1.75 height, so wrapped chips do not touch); the tick-box cell starts at its left, so every box stands
in one column and a count or the tied mark follows it. `docs/functionality-reference.md` (the blocking issues row): the
column's own words where the clause was cut.

**Checked.** `tsc` clean. `spec_equations_check` 36 (35 before): new, the registry line reads "info New spec: models without
it do not load" with its code in the tooltip, no line of the formula row is cut, and the column is padded 10 px at its sides
and centred. `looks_check` 73 (72): new, the Probe chips at 13 px beside the 14 px line. `sheet_check` 45 (44): new, with a
leader's rows open every tick box in view - with a count, the tied mark or nothing after it - stands at the same x.
`task_rows_check` 52, `find_fill_copy_check` 30, `unsaved_rows_check` 25, `blocking_issues_check` 42, `room_check` 27,
`editor_columns_check` 23, `formula_bar_check` 21, `matched_devices_check` 37. None flaky.

**Review follow-up.** The reference's blocking issues row read as if every row issue cut by the column got words of its own;
`ISSUE_HEAD` covers only `spec_adds_registry_entry` and `basis_not_stated`, and other long first clauses (`spec_name_is_a_probe`,
`spec_name_is_a_result`, `metric_not_in_registry`) still end in "...", as this entry says. The row now names the two lines and
says the others are still cut. Docs only: no page changed, so no check was run.

### SIF-75 The Runs window breaks names and links where they read (2026-10-21; from the real-data survey)

**Found.** In the user's Runs window (612 runs, 1500 px) the Task read "graphgps" over "_ldo1" and the Saved model "graphgps_ld"
over "o1 (31)" (survey issue 6): both cells kept `overflow-wrap: anywhere`, so SIF-27's break after "_" lost to a column narrower
than "graphgps_" (60 px in a 55 px cell), and the Saved model had no break points at all. "Started from" showed an underlined link
over four lines ("Round 3 full / archive — / GraphGPS / (offline)") and six ("... CircuitGPS / v3 from / scratch / (offline)"),
rows 84 to 120 px tall and about six in view (issue 7); its tooltip named only the run folder. Measured on the user's list of
2026-10-20 (549 runs, answered by a scratch check): 139 task names broken inside a word, 40 links over three lines. Not a
defect: the lowercase "template CircuitGPS" (the column's documented words).

**Changed.** `frontend/src/panels/RunList.tsx`: Task and Saved model are `wrap-words` cells, so a line breaks only at a space or
after "-", "_" or "." (`breakAt`, now also in the Saved model and the link) - "graphgps_" over "ldo1 (31)". The "." is new: a
baseline's or calibration's task ("agentic_fc_pub.calibration") kept whole made the Task column 99 px and the table, with the
user's 549 runs, 1259 px in its 1234; with it the table is 1234 in 1234 again (1232 at its narrowest). The link's text sits in a
`.run-from-name`, with the same break points, and its tooltip names the whole name first, then the run folder and "Show the run it
started from.". Its cell keeps `wrap`: a run that is not under this output folder is named by its folder, whose 12-character hash
(85 px) would widen the column 11 px and the table past its window; a word the column holds breaks at its break points there too.
`frontend/src/roadster.css` (SIF-75 block): that text takes three lines at most and ends in "..." - "Round 3 full / archive — /
CircuitGPS..." - the height a row's State and Mode take already, keeping the word that tells two archives apart. On the same 549
runs: no word broken in the three columns, rows 67 px (median) and 84 px (90th percentile) as before; the tallest, 120 px (138
before), are the offline trainings themselves, whose own Task and Saved model hold the archive's name. Not done: the survey's
tooltip on the Saved model cell (the cell shows the whole name; the row keeps its run folder as tooltip). No doc quotes the
changed text.

**Checked.** `tsc` clean. `run_list_check` 127 (124 before): new, a section with an offline model, a fine-tune of it
("graphgps_ldo1", "graphgps_ldo1 (31)"), a calibration ("agentic_fc_pub.calibration") and a fine-tune of a model outside the
output folder in a 1000 px window, where every column is at its narrowest - no word of Task, Started from or Saved model is split
over two lines while Task and Saved model take two; the link takes three lines, holds more than it shows and its tooltip starts
with the whole name; the outside run's folder leaves "Started from" as wide as its title. `dom_identity_check` 56,
`training_tab_check` 95, `run_control_check` 120, `looks_check` 73, `task_list_check` 88, `task_run_check` 31,
`reliability_check` 20. None flaky.

### SIF-76 The bottom panel's times, budget words and best design read like the rest of the page (2026-10-21; from the real-data survey)

**Found.** On the user's finished vco run (800 evaluations), Data tables' `proposed_at` column read "2026-10-16T17:17:20.704501+",
cut at the panel's edge and an hour off Logs, which writes this computer's time (18:20:50 for the run's last receipt): SIF-2 and
SIF-59 moved every other time on the page to the local form (survey issue 11). Its hint read "800 rows; the last 25 shown." over rows 736, 737 ... in the order
the backend sends the tail, oldest first, so during a run each new row landed below the fold of a panel six rows tall, while
Logs, the tab beside it, lists newest first (issue 28). Run status's Best design tile read "feasible hard violation 0": always 0
for a feasible design, and no reward, which the run brief gives as "best so far: reward -0.037" (issue 12). The same budget
number was "charged" here ("evaluations charged · 0 in flight · 0 failed", "800 charged / 800 (...)") and in the Runs window's
Details, but "Used 800" in the Continue... form under it and "Used so far" in the Abort question (issue 29). The message after a
Load run read "Fine-tune from mscr_vco_lin_c (6) @ 800." beside the model line's "save point 800 evaluations": SIF-67 left the
Runs window's sentences to a later batch (issue 30). Not changed: the run's short time "10-16 16:32" in that message (SIF-59's
runTitle form) and "real:" (deliberate); "at 4 evaluations" in the First feasible tile (the Runs window's "at 4" column).

**Changed.** `frontend/src/panels/RunTabs.tsx`: a Data tables cell of a time column (`_at`, `_utc`) reads stamp()'s local
"2026-10-16 18:17:20", "2026-10-16T17:17:20.704501+00:00 (UTC)" on hover, as Output files writes its times; a value stamp()
cannot read stays as it was, and the CSV export keeps the raw values. The rows are drawn newest first, and the hint reads "800
rows; the newest 25 shown, newest first." ("12 rows, newest first." when every row is shown). The Best design tile gives the
reward when the design has one and the hard violation only while it misses: "feasible reward -0.037", "infeasible reward -0.25 ·
hard violation 0.125" (a MOCK run's best design has no reward and reads "feasible" alone). The budget is "used": "evaluations
used · 0 in flight · 0 failed", with "A design counts against the budget once it is sent to the simulator, whether it then
completes, fails or is cancelled." on hover; "800 used / 800 (in flight 0, ...)"; "First full-plan feasibility: at 4
evaluations used (dispatch #4, ...)". `panels/RunList.tsx`: Details' Budget "25 used / 60 (...)" and First feasibility "at N
evaluations used (...)". `page/runWindowActions.ts`: "Fine-tune from mscr_vco_lin_c (6), save point at 800 evaluations. Undo
takes it back."; New run like this, in its list, "Fine-tune from fixture (save point at 40 evaluations), 40 evaluations, seed
2, ..."; a save point without a count gives its id, through `pointText` (lineage.ts). The Abort message's "stays charged" and
the header's compact "Next: ... @ 420" line are left as they are. `docs/workbench.md` (the Load run message it quotes; "the
evaluations used as a large number") and `docs/functionality-reference.md` (the same Run status phrase).

**Checked.** `tsc` clean. `export_check` 31 (27 before), on a real MOCK run: the hint "12 rows, newest first."; new, a
`proposed_at` cell reads the browser's local "YYYY-MM-DD hh:mm:ss" with "<UTC value> (UTC)" on hover, the rows' `commit_seq`
falls from 12 to 1, the hero line reads "evaluations used · 0 in flight · 0 failed" with its tooltip and the Budget row "12 used
/ 12", and the Best design tile has a reward when the design has one and "hard violation" only when it is not feasible.
`run_list_check` 128 (127): the Budget "25 used / 60", the Load run messages "Fine-tune from fixture, save point at 60
evaluations." and "... at 40 evaluations.", New run like this "Fine-tune from fixture (save point at 40 evaluations), 40
evaluations, seed 2"; new, its fixture's best design has a reward, and the tile reads "infeasible reward -0.25 · hard violation
0.125". `looks_check` 74 (73): new, the fixture's time cell reads its local time with "2026-10-03T15:15:01.076735+00:00 (UTC)"
on hover. `task_run_check` 31, `room_check` 27, `dom_identity_check` 56. None flaky.

**Review follow-up.** The review of 23ae964 found two slips, both real. (1) `frontend/scripts/reward_v2_frontend_check.mjs`
(stand-alone, not run) still looked for "at N evaluations charged" in the First nominal feasibility row, which `firstCost` now
writes "used": it looks for "used", one as one, as SIF-18 kept its words in step. (2) The rewritten lines built "evaluations"
by hand, so a baseline whose design is feasible read "First full-plan feasibility: at 1 evaluations used". `firstCost`
(RunTabs.tsx), Details' First feasibility (RunList.tsx), `pointWords` (runWindowActions.ts) and `pointText` (lineage.ts, the
same form) now go through `plural()`, and the launches beside them too (the same words as before). Not changed: the First
feasible tile's "at N evaluations" (this entry's "Not changed"). Checked: `tsc` clean, `export_check` 31, `run_list_check` 128,
`model_chooser_check` 83.

### SIF-77 The Training tab's head names the task and is never cut; its times and passing share in words (2026-10-21; from the real-data survey)

**Found.** On a finished run, the Training tab's head read "tx1-vco-gatv2 · seed 0 · 10-16 16:32" while the tab strip on the
same row read "2026-10-16 16:32:51 · mscr_vco_lin_c · New model, seed 0 · completed" and the message line "Loaded run
mscr_vco_lin_c 10-16 16:32": record 7.213 named a run by its experiment whenever it had one, so the name the rest of the page
uses for the run was missing there, and "tx1-vco-gatv2" appeared nowhere else on screen (survey issue 13). At 1366 px the head
was cut twice, "tx1-vco-gatv2 · seed 0..." and "800 evaluations · 6024 learner updates · last metri...", and the name's
tooltip was the folder path, so the cut part could not be read there (issue 19). The counts ended "last metric 18:20:50 · read
20:53:08": the program's words, with the same line again as the tooltip (issue 32). The Key numbers tile "Passing, last 100"
read "95 of 96 99 %", and nothing said why the count was not 100: keys.ts leaves out episode starts and designs without a
verdict (issue 31). Not changed: the head's short date (SIF-59's form, as runTitle); the bare "0" of Best design's worst miss
and the tile's grey "evaluation" before 35 (the tooltip explains the first, the second is the tile's unit layout); the
icon-only + and Follow latest buttons (the user's request for icon buttons; both carry labels).

**Changed.** `frontend/src/panels/TrainingTab.tsx`: a run's name (head, chips, legends and the Key numbers rows) starts with
its task, the experiment in brackets after it only when that has a name of its own (not "experiment" or the task's own name):
"mscr_vco_lin_c (tx1-vco-gatv2) · seed 0 · 10-16 16:32"; runs of the default experiment read as before. The name's tooltip
says "Task (experiment, when it has a name of its own) · seed · when the run was made." with the folder on a second line (the
folder alone until the run list has the run). The counts read "... · last recorded at 18:20:50 · numbers read at 20:53:08"
(" · live" while the worker lives, as before), and their tooltip says what each time is instead of repeating the line. The
passing share reads "95 of 96 judged · 99 %" on the tile and "95 of 96 judged (99 %)" in the several-runs table, and both
tooltips say "... of those judged: episode starts and designs without a verdict (a timeout or a lost link is none) are left
out." `frontend/src/styles.css`: the head wraps instead of cutting - the name, state and counts wrap onto a second line beside
the controls, and the controls go below them only when less than 360 px would be left for them; the 34ch cap and the two
ellipses are gone, and a very long name breaks rather than overflows. `docs/workbench.md` and `docs/functionality-reference.md`:
how a compared run is named, and the "95 of 96 judged" form.

**Checked.** `tsc` clean. `training_tab_check` 100 (95 before): the head's "last recorded at hh:mm:ss" (was "last metric"),
the six tiles' "N of M judged · P %", and with the run list the head "fixture_task (tx1-fixture) · seed 1 · 10-05 11:00" with
"Folder: <dir>" on hover (its fixture runs now carry experiments: a named one on the live and the once run, the default on the
others, whose chips still read "fixture_task · seed 4 · ..."); new, the live run's counts tooltip says what the time is and
that a live run is read every 2 s, a completed run's counts end "· numbers read at hh:mm:ss" with that explained on hover, the
passing tile's tooltip says which designs are left out ("Evaluations 189 to 288."), at 1366 px neither the name nor the counts
is cut and the controls stay beside them (the head two lines tall), and the shown run's table row reads "76 of 78 judged (97
%)". `training_data_check` 117, `dom_identity_check` 56. None flaky.

**Review follow-up.** The review of 6dffc50 found two slips, both real. (1) A read that failed set the read time as a good
one did, so an ended run whose re-read failed (the tab shown again, or Retry read with the backend down) read "numbers read
at <the failed read's time>" above "The training numbers could not be read: ...". A failed read now keeps the last good
read's time (`frontend/src/panels/TrainingTab.tsx`, the shown run's read loop). (2) The counts tooltip always began with
"Last recorded at: ...", also on a live run waiting for its first result, whose line has no such time, and said "Numbers
read at: ..." on a run at rest before any read had a time. It is now built from the line's own conditions: each sentence
only when its words are on the line. Checked: `tsc` clean, `training_tab_check` 103 (100 before; new: a re-read that fails
keeps "numbers read at" the last good read's time and Retry read reads again, and the empty live run's "0 evaluations · 0
learner updates · live" has the tooltip "Live: ..." alone).

### SIF-78 The Running now card names its working time and real data as the rest of the page does (2026-10-21; from the real-data survey)

**Found.** In the Running now window, a live real run's card read "worked 5 min 01 s · about 8 min 04 s left" in lower case,
while the Runs window gave the same number (the run's working time) as Duration "4 min 23 s so far", and the card's other
lines start with a capital ("None feasible yet", "Started from ...") (survey issue 24). The card's title read "graphgps_ldo1 ·
Fine-tune · model graphgps_ldo1 (31) real": every other part of the line is split by " · ", but a real run's word came
straight after the model's name, so "(31) real" read as part of it; a MOCK run's badge reads as separate (issue 25). Not
changed: the MOCK badge, and the card's lower-case state word "running" (the run's state as the Runs window shows it).

**Changed.** `frontend/src/panels/RunBrief.tsx`: the time line reads "Duration 5 min 01 s so far · about 8 min 04 s left"
("so far" only while the run is live, as in the Runs window; not "Running for", since the header's card can be a paused or
ended run), "No working time yet" when there is none, and its tooltip is the Runs window's Duration help ("How long the run
was actually working. The time it sat paused is not counted."). A real run's title ends " · real data" after the line's own
separator, in the same grey; a MOCK run keeps its badge.

**Checked.** `tsc` clean. `run_control_check` 122 (120 before): its fixture status now gives the header's run a working time
while the run brief is open, and a REAL run working elsewhere is listed while the brief reads the list again; new, the
header's card reads "Duration 5 min 01 s so far · about ... left", and after Refresh the real run's card is titled
"fixture_task · New model · no model saved · real data" with no MOCK badge and reads "Duration 2 min 05 s so far · about 4 min
10 s left" (picture `run-4c-brief-real.png`). `dom_identity_check` 56. None flaky.

### SIF-79 The Connection window: its buttons, notes, setup line and folders (2026-10-21; from the real-data survey)

**Found.** In the user's Connection window (connection `lab`, two sessions), step 3 of each card read "Test connection | +
Spectre / license | Details": a label that starts with "+" reads like adding something, nothing on screen said it was the longer,
slower test, and its tooltip read "Adds Spectre and a license SNAPSHOT (can be slow)"; the Start question of SIF-55 points at
this label (survey issue 16). Under Virtuoso 1's UNKNOWN badge the card read "(This connection was written before kinds existed;
it is treated as Virtuoso over SSH unless a test finds Virtuoso on this machine.)": the program's history, not what the user
should know or do, and two more lines, so its steps started lower than Virtuoso 2's (issue 17). The hint over the cards read
"Each Virtuoso window has its own bridge. Connect each session and load its commands in the matching CIW." beside cards headed
"Virtuoso 1 (lab)" and "Virtuoso 2 (lab2)", while "lab" also names the connection in the list (issue 34; the ids stay, the data
model names a connection after its first session). Virtuoso 2's CIW box read `load("/tmp/virtuoso_bridge_minlei/fyworkstation_s2/
virtuoso_bri` over `dge_s2/virtuoso_setup.il")`: `word-break: break-all` split the path inside a word, which looked like the box's
real line break between `setShellEnvVar` and `load` (issue 38). At the foot, a folder sign and "Folders" over one button
"Folders...", and only the button's tooltip said which folders (issue 39). Not changed: "Details" / "Hide" (minor, and its
table names each part), the "Folders..." label (7.170).

**Changed.** `frontend/src/panels/Connection.tsx`: the button reads "Full test (Spectre, license)", with "Test connection, then
also finds Spectre on the simulator host and asks the license server once for free seats (a snapshot: it takes no seat). No
simulation, no budget. Can be slow." on hover (the backend's full scope finds the program and reads its version and the license
server; it runs no simulation). A kind the connection file does not name is said on hover of the bold kind label (help cursor):
"The connection file does not say where Virtuoso runs, so this connection is taken as Virtuoso over SSH until a test finds
Virtuoso on this machine. Nothing to do."; the card shows the same lines as its sibling. The hint reads "This connection has 2
sessions, Virtuoso 1 and Virtuoso 2 below, each a Virtuoso with its own bridge: connect each one and paste its lines into that
Virtuoso's CIW.", and the cards are headed "Virtuoso 1 (session lab)" and "Virtuoso 2 (session lab2)", the name's tooltip saying
what naming it does ("lab" in the list sends the work to whichever session is free; a configuration or queue naming lab2 sends
it to Virtuoso 2 only). Both CIW boxes put a `<wbr>` after each "/" (`breakAfterSlash`, the idiom of RunList's `breakAt`), so a
long path breaks after a slash; Copy and a selection keep the plain line. Under the Folders head: "Where GATOR keeps its files
outside the repository: lock and crash journals, simulator scratch and the virtuoso-bridge checkout on this machine;
initial-condition files and Maestro netlists on the simulator host."; the button's tooltip no longer repeats it ("Shows each
folder at its value in use; a change is kept only by Save folders. Opening it changes nothing."). `panels/ConnectionFolders.tsx`:
the opened section starts with "Each folder starts at the value GATOR has always used; ..." (its "Where GATOR keeps the files of
the simulator connection outside the repository." was the same sentence again). `frontend/src/styles.css`: a CIW box breaks
with `word-break: normal; overflow-wrap: anywhere` (inside a word only when nothing else fits), and the kind label with a
tooltip has the help cursor. `frontend/src/launch.ts`: the Start question says 'press "Full test (Spectre, license)" in the
Connection window'. `docs/workbench.md` and `docs/functionality-reference.md`: the button's name and "Virtuoso 2 (session lab2)".

**Checked.** `tsc` clean. `connection_panel_check` 92 (86 before): the button lists "Full test (Spectre, license)" and the
cards "Virtuoso 1 (session lab)" / "Virtuoso 2 (session lab2)"; the undeclared kind is checked on hover (was "says so" in the
card's text); new, the full test's tooltip says it is Test connection and more, takes no seat and can be slow, and no button
starts with "+"; the kind label's tooltip ends "Nothing to do." with the help cursor and the card says nothing of kinds' history;
the two-session hint reads "This connection has 2 sessions, Virtuoso 1 and Virtuoso 2 below, ..." with no "Virtuoso window", and
each session name's tooltip says where naming it sends the work; both cards' first steps start at the same height although only
Virtuoso 2's kind is named; with Virtuoso 2's CIW box narrowed to about 38 characters, every line break comes after a "/", at a
space or at the line's own end, one of them after a "/", and the box's text is the line Copy copies; the Folders section says
its folders under the head and the button's tooltip does not repeat it; the opened section starts with "Each folder starts
...". `corner_check_check` 39: the connection question names "Full test (Spectre, license)". `dom_identity_check` 56,
`callouts_check` 8. None flaky.

### SIF-80 The model in use explains its facts (2026-10-21; from the real-data survey)

**Found.** In the RL model window, Fine-tune with a saved model chosen (survey picture 06-rl-model.png), "The model in use"
read "Restorable **full state**" with nothing after it, while the Network row beside it says what its fact means and the
saved models table holds the meaning only in its column's help (survey issue 35). "Components **device families (11
kinds)**" and "Network inputs transferable: specs read as a set, sizes relative to the PDK, device model features" began in
lower case, the second with a key-like name and a colon - a second label inside the cell - where New model's line and box
call the same choice "Transferable" / "Transferable 2" (issue 36). "Worst hard-spec share 0.5", "Objective bonus weight 1",
"Margin bonus weight 1" had no tooltip, where the reward block's controls carry one, and the third is called
"Tightest-margin bonus weight" there - one setting, two names; "Conditions Nominal only; 0 conditions planned" said the
empty plan twice, the second time as a zero (SIF-58 fixed "1 planned", not this case; issue 37). Not changed: the Runs
window's Details keep "Saved state" (a run's fact, pinned by run_list_check), the backend's list label (the graph view writes
it inside a sentence).

**Changed.** `frontend/src/panels/ModelChooser.tsx`: `RESTORABLE_MEANS` holds what each kind allows, and the Restorable
column's help is built from it (the same text as before). `panels/RlModelWindow.tsx`: Restorable reads "**full state** - the
run that saved it can be continued exactly." and "**weights only** - missing: replay_snapshot (...); usable for Fine-tune and
Evaluate only." (the meaning as a hint); Components capitalises the list's name in this cell only ("**Standard (8 generic
kinds)**", "**Device families (11 kinds)**"; "PDK ..." as it was); the three weights are "Worst hard-spec share", "Objective
bonus weight" and "Tightest-margin bonus weight", each row with the reward block's tooltip; Conditions (`conditionsText`)
reads "Nominal only" when nothing is planned, "...; no corners planned" for a corner policy with an empty plan, and
"...; N conditions planned" / "...; plan not recorded" as before; New model's line strips the new prefix (it still reads
"Network inputs: Transferable 2 (specs read as a set, ...)"). `panels/rlModelText.ts`: `inputsText` begins with the choice's
own name from `INPUT_NAMES` and a dash - "Transferable - specs read as a set, sizes relative to the PDK, device model
features", "Structured + Transferable 2 - ...", "Custom - ..." for a set no choice makes, "Standard" - which the Run
configuration line's tooltip writes too ("inputs Transferable 2 - specs read as a set, ..."); `REWARD_HELP` holds the three
tooltips. `panels/RewardConditions.tsx`: its three controls take their tooltips from `REWARD_HELP` (text unchanged).

**Checked.** `tsc` clean. `model_chooser_check` 85 (83 before): new, the model in use's facts read "full state - the run that
saved it can be continued exactly.", Network inputs "Standard", Components "Standard (8 generic kinds) - the network of this
run knows the same list.", no "Margin bonus weight" row, and each weight row's tooltip is the reward block control's own; with
the weights-only model (its fixture now records an empty plan), Restorable reads "weights only - missing: replay_snapshot
(disabled in output settings); usable for Fine-tune and Evaluate only." and Conditions "Nominal only".
`network_inputs_check` 9 (8 before): new, the line reads "Network inputs: Transferable 2 (specs read as a set, ...,
operating-point ratios)" and the Run configuration line's tooltip "inputs Transferable 2 - specs read as a set, ...".
`network_panel_check` 62, `reward_block_check` 32, `dom_identity_check` 56. `reward_v2_frontend_check` (stand-alone, not run)
now finds the facts row "Tightest-margin bonus weight". None flaky.

**Review follow-up.** The review of db752c7 found one slip, and it was real. Restorable promised "the run that saved it can
be continued exactly" for every full save point. A full save point written by an older optimizer source cannot be continued:
Continue needs exactly that source (record 7.221; the backend refuses it as `older_code`, and the Runs window's Saved state
reads "model only"). So the one window could make that promise while its own Compatibility list warned that the source
differs, and that covers every model saved before the latest change under src/analog_optimizer/. `panels/RlModelWindow.tsx`
(`restorableMeans`) now reads the compatibility's "optimizer source code digest" check. When it passes, the meaning is said
as before. When it is a warning, Restorable reads "**full state** - written by an older version of the optimizer code: only
that version can continue it; Fine-tune and Evaluate only still load its model." (the Runs window's words). With no
compatibility (still checking, or the configuration is incomplete), no meaning is shown. Weights only always gets its
meaning. `panels/ModelChooser.tsx`: `RESTORABLE_OLDER` holds those words, and the Restorable column's help adds "A full save
point written by an older version of the optimizer code: only that version can continue it; ...". Checked: `tsc` clean.
`model_chooser_check` 86 (85 before): the fixture's compatibility now carries the backend's digest check, a warning for
FIXTURE_opamp_gt. New: with its save point in use, Restorable reads the older-source words beside the digest warning, and
the column's help says it too. The other models still read "full state - the run that saved it can be continued exactly.".
`dom_identity_check` 56, `model_structure_check` 30 and `mode_suggestion_check` 20. None flaky.

### SIF-81 The task file explains its parts in a list, and the Agent window's headline names its two CLIs (2026-10-21; from the real-data survey)

**Found.** In the Task file window of mscr_vco_lin_c (survey picture 10-task-file.png), the `_help` part sat in the
wrapping monospace box with the rest of the file, and its long lines ran back to the box's edge, under the opening "{":
`editors\" checks it and puts the rows into the editors; ...` and `(ring_oscillator only): a rough oscillation frequency;
it sizes the transient.` started at column 0, so one part's text could not be told from the next, and the hint over the box
("The `_help` part says what each part is.") sent the reader to that block (survey issue 9; SIF-26 only made the box fill
the window). In the Agent window (07-agent.png) the row read "In /mnt/d/gator: [Claude Code] [Codex] ... [What's
missing?]" over "Each button opens the CLI in a terminal window of its own, in this folder, as you start it yourself: your
settings, your account, your history.": "each button" took in What's missing?, which opens no CLI, its own job (a free
checklist, no agent) was said only on hover, and "as you start it yourself: your settings, ..." was hard to read (issue
18). Not changed: the button's name "What's missing?" (7.226; the checklist's heading and its "press again" line use it).

**Changed.** `frontend/src/panels/TaskFile.tsx`: `splitHelp` takes the `_help` part out of the file the backend sends. The
backend writes it first, with two-space indents (`task_files.render`), so it is cut out of the text and every number stays as
written (1.0, 5e-06). A file of another shape is written out again without it, and text that is not JSON stays whole. The
part shows over the box as **What each part is** (open; `details.task-file-help`), each part's name in bold and its text after
it, the wrapped lines hanging in under it. The box holds the file without the part; Revert and its "nothing to undo" compare
with that, and Apply sends it so (the backend ignores `_help` anyway). The hint reads "... nothing is saved until you press
**Save as**. **What each part is**, below, says what each part holds." `frontend/src/roadster.css` (SIF-81): the list's look;
it scrolls by itself at 30vh at most, so the box keeps the rest of the window (SIF-26). `frontend/src/panels/Agent.tsx`: the
headline reads "Claude Code and Codex each open in a terminal window of their own, in this folder, as if you had started them
yourself: your own settings, account and history. "What's missing?" asks no agent and runs no simulation: the workbench
itself lists what the run still needs before it can start."; the two CLI buttons' tooltips and the Agent... tab's say "as if
you had started it yourself". `docs/workbench.md`: the task file window's list and the Agent window's headline.

**Checked.** `tsc` clean. `task_save_check` 71 (70 before): the fixture's file is written as the backend writes it, with a
second, long help part and `1200000000.0`; the window is now sized as it asks (760 x 900) and photographed
(`task-file.png`). Changed, the file opens as text without `_help`, starting `{ "format": "gator-task-1",`, its
`1200000000.0` kept. New, the list over the box is open, headed "What each part is", parts "what this is|maestro" in bold,
the maestro text whole on more than one line with its second line hanging in (20 px right of the part's name), the hint
pointing at the list with no `_help`, and Revert closed on a file just opened. `agent_window_check` 29 (28 before): the
headline check reads the new first sentence; new, the headline does not say "Each button", ends with the What's missing?
sentence, and the Codex button's tooltip says "in /mnt/d/gator-fixture, as if you had started it yourself:".
`dom_identity_check` 56. None flaky.

### SIF-82 Run configuration keeps its width at a narrow window (2026-10-21; from the real-data survey)

**Found.** At 1100 px (survey picture 13-page-1100.png), Run configuration read "Concurrent Spectre jobs" at x 24 and its box
"6" at about x 955-1045, and the model line "Fine-tune mscr_vco_lin_c (6) · save point 800 evaluations" sat at the left with
"RL model..." at the far right (survey issue 21). At 1100 px and under, the narrow layout gives the run column the page's
width, and the property sheet of record 7.179 puts each box at the right end of its line (`minmax(0, 1fr) auto`), so a label
and its box were about 930 px apart. Not changed: the nested scroll areas of the narrow layout (its fixed-height rows), a
layout choice of its own.

**Changed.** `frontend/src/styles.css` (SIF-82): under `@media (max-width: 1100px)` the run column's module bodies (Run
configuration and Output settings) are at most 560 px wide, so a label keeps its box near it, the model line its "RL
model..." button, and the hints, the reward fold and the Limits fold the same width. With the circuit shown between 701 and
1100 px (two columns), or above 1100 px, the column is narrower than that and nothing changes.

**Checked.** `tsc` clean. `room_check` 28 (27 before): new, at 1100 x 900, with the run column 1069 px wide, "Concurrent
Spectre jobs" to the right edge of its box and the model line to the right edge of "RL model..." are each 560 px (photographed,
`room-1b-narrow-sheet.png`); the page goes back to 1680 x 1050 for what follows. `looks_check` 74 and `module_fold_check` 30.
None flaky.

**Review follow-up.** The review of acd9fae found one slip, in this entry only, and it was real. "Changed" said that with the
circuit shown the column is always narrower than 560 px. At 700 px and under the layout is one column even with the circuit
shown (`styles.css`, the `@media (max-width: 700px)` rule), the run column takes the page's width, and at 700 px its module
body is about 637 px, so the cap does take effect there; that is wanted too. The sentence now names the two-column range
(701-1100 px). The code was right and is not changed; no check was rerun for a wording fix.

### SIF-83 Pause and Force abort say when a run cannot come back (2026-10-22; from the usability audit)

**Found.** Two presses in the header ended a run for good without a word (audit findings J3-1 and J3-2). Pause on a run
searched by Bayesian optimization (one taken over from the command line, or made by "New run like this" from one) asked
nothing: Pause's question looked only at the run's checkpoint and replay snapshot settings, while the backend never
continues a Bayesian run ("Bayesian optimization cannot be resumed and holds no trained RL model"). After the pause, Resume
was greyed out and only its tooltip said why. Force abort, pressed while a pause waits for the simulation in flight, sends
`cancel`, and the engine then ends the run as `cancelled` rather than `paused`. Neither Resume nor Continue... takes that
state up, but the question spoke only of the evaluation in flight and the schematic. After an Abort it turns a `stopped`
end, which Continue... can pick up, into a `cancelled` one, and the question did not say that either.

**Changed.** `frontend/src/panels/RunControl.tsx` (SIF-83): Pause's check reads `run.optimizer` from the run's own
`effective_config.json`, a file it already fetched. On a Bayesian run Pause asks first: "This run cannot be resumed after a
pause: it is searched by Bayesian optimization, whose search state lives only in its running process." The two older reasons
now carry their own "for it", and the question's frame is unchanged. Force abort's question names the phase it is pressed in.
While a pause waits: "This replaces your Pause: the run ends as cancelled, and a cancelled run cannot be resumed or continued
(a save point it has written can still start a new run in Fine-tune). To keep it resumable, wait for the pause." Its tooltip
says the same in short. After an Abort: "The run ends as cancelled instead of stopped, so Continue... can no longer pick it
up." The rest of the question is word for word as before. Nothing else changed. The same press and the same answer send the
same command, and "no" sends nothing. Save now stays enabled on a Bayesian run: the backend refuses each press in its own
clear words, the pattern `save_now_check` pins, and the page's status carries no optimizer to grey it out with.
`docs/workbench.md` (Abort; Resume) says both.

**Checked.** `tsc` clean. `run_control_check` 128 (122 before). New: while a pause waits, Force abort's tooltip says it
replaces the Pause; pressed and answered "no", it asks "Force abort?" then "This replaces your Pause: ... cannot be resumed or
continued ... To keep it resumable, wait for the pause.", and nothing beyond the pause is sent. After an Abort, its question
says the run ends cancelled instead of stopped and names no Pause. Pause on a run whose configuration says `run.optimizer:
"bayes"` asks first, and "no" sends nothing. The replay snapshot warning is now matched with its new "... switched off for
it." tail. The fixture's pausing phase is one status poll longer, so the extra question fits in it. `save_now_check` 29.
None flaky.

**Review follow-up.** The review of 175f392 found two slips, both real. (1) Force abort's new words said something false for
the very run this record is about. On a Bayesian run the user answers Pause's "This run cannot be resumed after a pause", and
seconds later Force abort said "To keep it resumable, wait for the pause", and its tooltip implied the run could otherwise be
resumed; after an Abort, "so Continue... can no longer pick it up" implied a stopped Bayesian or checkpoint-less run could be
continued. The backend's `continuation()` refuses every Bayesian run (`no_rl_model`) and a run with no save point, so waiting
keeps nothing. Now `RunButtons` reads `cannotResume` once the run waits on a pause or an abort, whoever sent it (this page,
another one or the command line, where Pause's question was never seen). With a reason, the question says only "This replaces
your Pause: the run ends as cancelled instead of paused." (after an Abort: "... instead of stopped.") and "It cannot come back
either way: <reason>.", and the tooltip drops "and cannot be resumed". Until the answer is in, and on any run that can come
back, the words are as before. The press stays synchronous, so the button still asks once and sends one `cancel`. (2)
`docs/workbench.md` quoted "To keep it resumable, wait for the pause" as also in the tooltip, which never said it; it now says
the tooltip names the replaced pause, and the question adds the advice. `tsc` clean; `run_control_check` 132 (128 before): a
Bayesian run paused with "yes" waits, Force abort's tooltip ends "... ends as cancelled. Only for a run that is stuck.", its
question says "It cannot come back either way: it is searched by Bayesian optimization ..." with no "resumable", "continued"
or "Fine-tune", and "no" sends nothing beyond the pause. `save_now_check` 29. None flaky.

### SIF-84 A question from the Tasks or Runs window is asked in that window, and a refusal is said there (2026-10-22; from the usability audit)

**Found.** Choosing another task from a pop-up while the editors held unsaved edits asked the edits question with the
main window's `confirm` (audit findings J6-1 and J4-1). That covers a double click in the Tasks window, and Load run, New
run like this or a double click in the Runs window. The dialog opened behind the pop-up. The pop-up is drawn by the main
page's script, so it stood still too, with "loading..." on the Tasks window's row, and the press looked dead until the
user found the dialog in the other window. After Cancel, or a run model that could not be read, the Runs window stayed
open (by design, record 7.291), but the reason went only to the main page's message line, behind the window.

**Changed.** `frontend/src/panels/taskChoice.ts`: the task load takes the window that holds the press (`owner`) and asks
the edits question with `owner.confirm`, as the Virtuoso window's copy question already does. A window closed meanwhile
falls back to the main window. The words, the answers and what each answer does are unchanged. "Reload saved values"
and the ngspice window's save still ask in the main window. `TaskList.tsx` and `Left.tsx`: the Tasks window's double
click passes its window. `page/runWindowActions.ts`: Load run and New run like this take the Runs window and pass it on.
They now answer `{ loaded, why }`, where `why` is exactly the sentence the page's message gets ("Run alpha.baseline 10-05
18:00 was not loaded: you chose Cancel, so the task and its edits stay as they were. Nothing changed."). A choice
overtaken by a newer one still says nothing, in either place. The page messages are unchanged. `RunList.tsx`: when a
Load run or New run like this does not go through, the window keeps its line (`.run-refused`, `role="status"`). The line
stands beside the run's actions while its Details are open; after a double click it stands where the count of runs
stood. The next press, a Details toggle, Refresh list or closing the window lets it go. The window's hint says it stays
open "saying why". `BottomPanel.tsx`: the types only. Nothing new starts, saves, loads or writes. Every question is asked
on the same press with the same words, and Cancel still changes nothing. `docs/workbench.md` (the Tasks window's double
click; the Runs window's double click and Load run) and `docs/functionality-reference.md` say where the question is
asked and where the reason shows. Checks: `lib/harness.mjs` `taskWindow()` takes `onDialog` and gives it every Tasks window
it opens, and `answerDialogs()` can record which window asked. `task_rows_check` answers the edits question in the Tasks
window. `virtuoso_source_check` and `consistency_check` give their handlers to the Tasks window. Without this,
consistency_check's choice after an edit waited on an unanswered dialog until its 120 s limit.

**Checked.** `tsc` clean. `task_run_check` 39, eight of them new, in section 11: with a size row of real:beta edited, a double
click on real:alpha's run asks "Switch to real:alpha? ..." in the Runs window and nothing in the main window. Cancel
keeps the window open, and its count line reads the page message's sentence word for word. The task, the edited row and
the shown run stay. Opening the run's Details brings the count back. Load run, answered Cancel, puts the line beside the
actions (photographed, `task-run-4-load-cancelled.png`). Answered OK, it loads real:alpha and the window closes.
`task_rows_check` 54, two new: Cancel's question came from the Tasks window, and every edits question in the check did.
`run_list_check` 129, one new: a Load run whose model read fails puts the page's sentence beside the run's actions. No step
there reaches the edits question, because every run it can load has the page's own task. `virtuoso_source_check` 95,
`consistency_check` 14, `task_list_check` 88, `testbench_probes_check` 41, `project_help_check` 49, `ngspice_window_check`
43, `circuit_source_check` 15, `dom_identity_check` 56. One flake: `task_list_check` failed twice on its first run, at
"Rename sends the task's key and the new name, then reads the task list again" and the next step. Rename is untouched
here, and it passed 88 of 88 alone.

### SIF-85 A saved model's Details judge it as Use would load it, and Use shows that it is working (2026-10-22; from the usability audit)

**Found.** A saved model's Details checked the selected save point against the configuration on the page, with the
page's network and component list as they were (audit finding J5-1). The backend treats the network and the input
schema as fatal for Fine-tune and Evaluate only. So every model of another design or size read "NOT compatible for
Fine-tune - it cannot be loaded, and a run never falls back to New model", open and in red. Yet "Use this save point"
brings that model's own network and component list with it, and then the model loads. Across 411 saved models, usable
ones looked unusable. The New model fold for looking judged against the template's network in the same way. Pressing
"Use this save point" gave no sign of working while the save point was read (finding J5-11). A save point that could
not be read was said only above the "Saved models" heading, far from the Details row pressed, so the press looked dead.

**Changed.** `frontend/src/panels/ModelChooser.tsx` (`ModelDetails`): the check first reads the save point as Use reads
it (`readSavePoint`, with the backend's network fields), then sends the page's configuration through `withSavePoint`.
The configuration carries this model's own network and component list, this save point as the source, and a Mode that
loads it: the window's Mode, or Fine-tune while New model is chosen. What a model cannot bring still shows as before:
the task's graph, its specs, MOCK or real data, the save point's version. The heading reads "With the task on the page
and this model's own network". The pressed button reads "Using..." and is off while its save point is read. The other
Use buttons and the row's double click stay on, because a newer choice wins (record 7.278). A Use that could not read
its save point is said again under that model's save points (`p.error.use-error`); the window's own line stays.
`savePoint.ts`: `readSavePoint` takes a signal, and `pointKey` names one save point as a string.
`useRlModel.ts`: `usingPoint` holds the save point being read instead of a flag, and the read error carries `point`.
`RlModelWindow.tsx` passes the network fields, `usingPoint` and that error to `SavedModels`; the suggested model's Use
is off while any save point is read, as before. Nothing is chosen, saved or started by a look: Details make one more read
(the save point's description), and the draft stays as it was. `docs/workbench.md` (Details; "Using one is a press")
and `docs/functionality-reference.md` (Saved models) say both. `model_chooser_check.mjs`: the held and failing reads now
name the save point of the Use, because the Details' own read has no configuration either.

**Checked.** `tsc` clean. `model_chooser_check` 90, five of them new. In New model, Details read A's save point first, then
check it as Fine-tune would load it, with A as the source. With the page on a Graph Transformer, D (an RGCN) is
checked with its RGCN network, and the page keeps its own. The heading carries the new words. While a Use read is held,
its button says "Using..." and is off, and A's other Use buttons stay on. A failing Use puts "That save point could not
be read: ..." straight under A's save points table, and its button reads "Use this save point" again, on.
`network_panel_check` 62, `graph_view_check` 69, `encoder_models_check` 24, `model_structure_check` 30,
`mode_suggestion_check` 20. No flakes.

### SIF-86 The saved models scroll in a box of their own, and the notice's link opens the RL model window at its reason (2026-10-22; from the usability audit)

**Found.** In Fine-tune and Evaluate only, the RL model window's saved models table had no height of its own (audit
finding J5-2). With 411 models at about 46-59 px a row it was about 20,000 px long. "The model in use", its
compatibility, Fine-tune's own switches, Evaluate only's Actions and Advanced all came after it (record 7.265's order),
thousands of pixels down. The main page's notice "Review the settings in RL model... - <reason>" (SIF-46) opened the
window at its top (finding J5-9). The block that says the reason in full was further down, often under the whole table:
the NOT compatible list, the budget warning, the soft actor-critic warning. The user had to search for it.

**Changed.** `frontend/src/roadster.css`: the saved models table scrolls in a box, `min(60vh, 720px)` high at most,
with `scrollbar-gutter: stable` so its columns keep their width. Its titles stay at its top, above the rows
(`z-index: 1`). A model's Details tables have titles that no longer stick over the box's titles. Record 7.265's order
is kept. `frontend/src/panels/ModelChooser.tsx` (`SavedModels`): when the list first arrives, the model in use is
scrolled to the middle of the box if it is out of view. Only the box scrolls, never the window, once per window: a later
sort, filter or Refresh list keeps the place. `frontend/src/panels/useRlModel.ts`: each `networkReason` comes with
`networkAnchor`, the id of the block that says it, in the same order: `net-unavailable`, `net-compat`,
`net-check-error`, `net-message`, `net-starved`, `sac-values`, `template-problem`, `network-differences`. `openAt(anchor)`
opens the window, and once it has drawn, opens the block's folds and scrolls it to the middle, one scroll per press.
`frontend/src/panels/RlModelWindow.tsx` puts those ids on the blocks. `frontend/src/panels/RunConfiguration.tsx`: the
notice's "RL model..." calls `openAt`; the model line's own "RL model..." still opens the window at its top.
`frontend/src/panels/popupWindow.ts`: `styled(win)` waits for a pop-up's copied stylesheets, 2 s at most, so no place is
measured in the unstyled layout of a window just opened (the check harness waits for them for the same reason, record
7.178). Nothing else changed: the link opens a window and scrolls it, and starts, saves or chooses nothing.
`docs/workbench.md` (the Fine-tune paragraph, the notice) and `docs/functionality-reference.md` (RL model..., Saved
models) say both.

**Checked.** `tsc` clean. `model_chooser_check` 95, five of them new. With A's Details open, the table is a 552 px box in
a 920 px window, and it scrolls. Scrolled to its end, its titles are at its top (0 px), and the Details' own titles are
static. In a 480 px window with the list held until then, the model in use (A, the last row) is in the box's view: the
box scrolled 165 px, the window 0. With D in use and answered NOT compatible, the notice reads "... - the saved model is
NOT compatible with this run.", and its link opens the window at the open compatibility, in view (window scrolled
845 px). The model line's button opens it at its top, the compatibility 1,318 px down. `reward_block_check` 33, one new:
the notice's link opens the window at the soft actor-critic warning (scrolled 557 px, the warning in view).
`module_fold_check` 30, `network_panel_check` 62, `looks_check` 74, `encoder_models_check` 24, `graph_view_check` 69,
`model_structure_check` 30, `mode_suggestion_check` 20, `network_inputs_check` 9, `dom_identity_check` 56, `pdk_check`
40, `reliability_check` 20, `room_check` 28, `task_rows_check` 54, `typing_check` 50. No flakes.

**Review follow-up.** The review of 82a439d found one slip, and it was real. The rule that makes the Details' own table
titles static, `.rl-networks-window .saved-models .model-details table.grid th`, also matched the Network structure's
"Full layer table". Its `<dialog>` is rendered inside `.model-details`, and the long `table.structure-layers` scrolls in the
dialog's own box (`.structure-scroll`). Its column titles (#, Section, Layer, ... What it does) had stayed at that box's top
(`table.grid th` is sticky) and now scrolled away; "Changed" above did not say so. The rule now leaves that table out
(`table.grid:not(.structure-layers) th`); the small section tables were static already, and the graph dialog's tables too.
`tsc` clean; `model_structure_check` 31, one new: the layer table's titles are `sticky`, `top: 0px`.
`model_chooser_check` 95 (the Details' own titles still static) and `network_panel_check` 62. No flakes.

### SIF-87 Closing a window keeps what was typed in it (2026-10-22; from the usability audit)

**Found.** The banner's Close all says "Nothing in them is lost; each opens again from its button", but two windows lost
what was typed in them, with no question (audit findings J7-1 and J6-10). The Task file's draft lived inside its window
(`TaskFileWindow`), and every close - its Close, the window's X, Close all - unmounted it (`setFile(null)`). The next
press read the file again from the editors, so hand edits to a long JSON file, or pasted agent text, were gone for good.
The Connection window's typed folders lived in `ConnectionFolders`, inside the window's portal, so closing the window
(or Close all) brought back the values in use. The ngspice window keeps its deck outside the window, so the loss was not
inherent.

**Changed.** `frontend/src/panels/TaskFile.tsx`: the draft is a `FileDraft` (`text`, the `body` it was typed over,
`applied`, `kept`), held by TaskSave and passed in with its setter. `unapplied()` says whether a draft is worth keeping:
typed, and not what was applied. The window lays the draft over the file it read and shows "Your changes from before are
kept, not applied yet. Revert drops them." over the text when the draft came back from a closed window. Revert sets the
draft to nothing (the file as read at this opening), and a successful Apply marks the draft applied.
`frontend/src/panels/TaskSave.tsx`: `closedFile()` is the one close path (Close, the X and Close all through the
pop-up's `pagehide`). It keeps a draft not applied, marked as kept, and drops any other. The next Task file press reads
the file again, as before, so Revert and the title follow the editors and the revision now. Another task, library or
cell still drops the draft with the window. `frontend/src/panels/ConnectionFolders.tsx`: the typed folders (`typed`, by
folder) come from the connection button. The section reads the values in use when it opens, lays the typing over them,
and says "Your changes from before are kept, not saved yet. Undo changes drops them." while typing from before still
differs. Save folders and Undo changes clear it. `frontend/src/panels/Connection.tsx` holds `typedFolders`, as
`Ngspice.tsx` holds its deck, so closing the window or folding the section keeps them. The "Folders..." tooltip now
says a typed value is shown until saved and that only Save folders writes it. No question was added, and no
`beforeunload`: TaskSave closes the file window by script on a task change, and the page's `pagehide` closes every
pop-up. Close all's tooltip is unchanged, and now true for these two windows. Nothing new is sent: the reopened file is
the same read as before, and the folders are the same GET. Nothing is applied, saved or written without the user's
press. `docs/workbench.md` (the task file, Folders, Windows) and `docs/functionality-reference.md` (Task file,
Folders..., Windows) say so.

**Checked.** `tsc` clean. `task_save_check` 76, five of them new. After a refused Apply, Close and a press on Task file
read the file once and show the broken draft with the kept line, Revert on. The same holds after the window's own X
(`Target.closeTarget`, as Close all closes it). Revert shows the file as read now (the applied lower 1250000000, no
"sometimes") and the line goes. A reverted draft is not kept at the next press, and the editors never took the broken
draft. `connection_panel_check` 94, two new. A folder typed and not saved, after the window's X and a reopen: one GET
directories, the typed `~/fixture-typed` over the values in use, the kept line, Save folders on. Undo changes sends
nothing, puts `~/.gator/ic` back and removes the line. `dom_identity_check` 56, `virtuoso_source_check` 95,
`project_help_check` 49, `ngspice_window_check` 43, `task_list_check` 88. No flakes.

### SIF-88 A cell's first read asks for its testbench before the copy question, and the next step and the title say what the page holds (2026-10-22; from the usability audit)

**Found.** Reading a Virtuoso cell for the first time went wrong in three places (audit findings J1-1, J1-2 and J1-8).
With Testbench cell = (none), **Read this cell into the workbench** stayed on and the note said to choose a testbench
"first, if it has one". The press asked the long copy question, and after OK the backend refused at once: "Choose the
cell's Testbench cell first". The page already knew that, before the question. After a read, Parameters stayed empty
with only "The optimizer searches 0 of 0 rows.", and the sentence "Next: fill Parameters, Probes and Specs ... then press
Save as" sat in the closed fold "What you can do with it now". The header's title took `project.task_name` for anything
but a followed task. A fresh page therefore read "task" with "RL model task", from the empty configuration's name. A cell
being read kept the name of the last task loaded.

**Changed.** `frontend/src/panels/VirtuosoWindow.tsx`: Read is off until a testbench is chosen. Its tooltip then says
"Read this cell: Choose the cell's Testbench cell first: a task simulates the testbench and keeps its Maestro test
there." (`NO_TESTBENCH`), and the note says "first: a task needs one". The next step is a visible `p.hint.next-step`
under the draft's headline. The fold keeps what the draft is, and the Agent window as a help. `frontend/src/panels/Left.tsx`:
`importCell` says `NO_TESTBENCH` in the window when a read that declares the cell has no testbench. It does this before
the copy question and sends nothing. This covers **Read the cell again** on a cell read before the question. The
backend's own guard stays. The line goes once a testbench is chosen; another step's error stays. `TitleFacts` names a
followed task as before. A Virtuoso cell is "library/cell (not saved)", or "choosing a Virtuoso cell" before a cell is
chosen. Any other page reads "no task chosen". The RL model fact falls back to the task's name only for a followed task,
otherwise "not set". The title's tooltip no longer shows a stale `task_id`. Export JSON's file name still uses
`task_name`. `frontend/src/panels/Editors.tsx`: an empty Parameters table shows `p.hint.parameters-empty`: "No rows yet:
add one row per size the optimizer may change (Add, the + above)." For a cell it adds "Once the cell is read, its present
sizes are under Hierarchy, Instances and parameters, in the Virtuoso window." It is not shown while no task or cell is
chosen, because the task's lines already say to choose one. The audit's larger option, an "Add to Parameters" button per
instance parameter, was left out: its rows would start with bounds that hold no real size. Nothing new is sent, and no
question was added or removed. The copy question still comes before every declaring read, Cancel still reads nothing,
and no run, save or Virtuoso write changed. `docs/workbench.md` (the title block, Browsing a Virtuoso library) and
`docs/functionality-reference.md` (Title block, Read this cell) say so.

**Checked.** `tsc` clean. `virtuoso_source_check` 98: Read is off with no testbench and its tooltip and note say why. A
press then asks nothing and sends nothing. A testbench turns it on, and the question names the testbench. Cancel reads
nothing, and the dialog count after "Read the cell again" is 2 (it was 3: the refused OK is gone). The header's title is
"choosing a Virtuoso cell", then "FIXTURE_DESIGNS/ota5_v1 (not saved)", with RL model "not set". `working_copy_check`
33: on a cell read before the question with the testbench emptied, Read the cell again asks nothing, sends nothing and
shows the line, and choosing the testbench takes it away. `project_help_check` 50: the next step is in view, the empty
Parameters line is shown after a read, and the browse note says "first: a task needs one". `circuit_source_check` 17:
the removed netlist source titles "no task chosen", RL model "not set", and shows no empty-Parameters line.
`task_list_check` 89: with no task, the title reads "no task chosen". `testbench_probes_check` 41, `looks_check` 74,
`typing_check` 50, `editor_columns_check` 23. No flakes.

**Review follow-up.** The review of 3ffc72e found two slips, both real. (1) The draft's `p.tb-stale` line still said
"Press Read the cell again to read it without one" whenever Testbench cell was empty. On a cell read before the question
(no verified working-copy record), that press declares the cell, and `importCell` now refuses it with `NO_TESTBENCH`: the
line invited the press that the next line refused. `working_copy_check` makes exactly this state. For such a cell the line
now says "Choose its Testbench cell above to read it again: that read declares the cell the task flow works in, which
needs one." A declared cell keeps "to read it without one", since that read is still sent without a question. The
behaviour is unchanged: the backend refused this press before SIF-88 too. (2) The comment above the Next line in
`frontend/src/launch.ts` said the title names a Virtuoso cell by the project's task name. It now says the title names it
as library/cell too, as not saved. `tsc` clean; `working_copy_check` 34, one new: with the testbench emptied, the line
reads "This cell was read through tb_ring_osc_3stage." and asks for a testbench, without "without one".
`testbench_probes_check` 41 (the "read it through other_tb" line unchanged), `virtuoso_source_check` 98,
`project_help_check` 50. No flakes.

### SIF-89 A run that ends says so, and Run status leads with what went wrong and what to do next (2026-10-22; from the usability audit)

**Found.** The line under the header spoke only after the user's own Pause or Abort (audit findings J3-6, J3-7, J4-11).
A run that completed or failed went running, then finishing, then idle with no line: only the chip and the lit state
changed. A failed run's reason was the last of about 20 rows in Run status, and the hero above it showed only the stop
reason. An automatic pause after connection failures (the engine's `infrastructure_failures`, with its error "Continuing
requires the connection gate to pass again") passes through `pausing` while the worker saves. A poll that caught that
state made the page say "Paused at ...: everything is saved. Resume continues from exactly there.", as if the user had
paused, with no word about the connection. The run's next step, Continue... with its reason and the backend's Fine-tune
alternative, sat under the whole facts table, below the fold of a bottom panel that shows about four rows (survey
picture 05).

**Changed.** `frontend/src/panels/RunControl.tsx`: the phase effect remembers the run with the phase and speaks only
when the run is the same. Taking a run over, letting go of one and a reload's lookup ("checking") say nothing. Three
new lines, each with the run's path in its tooltip as after Start (SIF-56). A pause after connection failures, from
`running` or `pausing`, says in red "Paused by itself after connection failures; everything is saved. Test the
connection (Connection button), then Resume." This comes before the user-pause line. A run that completes from
`running` or `finishing` says "Completed at 60 of 60 evaluations (budget used up). Its results are under Run status.",
with the stop reason through `stopWords`. A run that fails says in red "The run failed at N of M evaluations: <its
error>", also after a Pause or an Abort, where it used to read "The run has ended (failed) ...". The user-pause and
user-abort lines keep their words. The abort line also covers a run stopped or cancelled from elsewhere. Nothing is
sent: the effect only writes the line. `frontend/src/panels/RunTabs.tsx` (`StatusTab`): the run's error shows as a red
`p.error.status-error` right under the run at a glance. The table's Error row stays. Under it comes the action row,
moved whole from below the table: Continue..., its reason, the alternative, and Export status (JSON) still last. The
budget form and a refusal follow the row, all inside `.status-grid` and before the facts table. The buttons, their
tooltips and their presses are unchanged. `frontend/src/roadster.css`: the reason sits close under the bar, and the row
(with its form or refusal) keeps 10 px from the table. `docs/workbench.md` (Start, Pause, Resume, Abort; the run
commands) and `docs/functionality-reference.md` (Start → Pause → Resume; Run status) say so. An `interrupted` run
(worker gone) still gets no line: the audit did not ask for one, and the chip already says "(the worker is gone)".

**Checked.** `tsc` clean. `run_control_check` 143 (132 before). The fixture's status now carries `error`. In a new
section 7b, a run pauses by itself (through "Pausing...") and the line reads the connection words in red with the run's
path in its tooltip. Run status shows the hero, then the red reason, then the row with Continue... and Export status
(JSON) last, then the facts with the same Error row. The row is in view at the panel's top. After Resume the reason
goes. Completing reads "Completed at 60 of 60 evaluations (budget used up). Its results are under Run status." (not
red). Failing reads "The run failed at N of 60 evaluations: FIXTURE: ..." in red, and Run status leads with that reason.
The user-pause and user-abort lines pass unchanged. `export_check` 31: on a real MOCK run, Export status (JSON) ends a
row that comes right after the run at a glance and before the facts. `looks_check` 74, `room_check` 28,
`calibration_check` 38, `calibration_save_check` 22, `run_list_check` 129, `save_now_check` 29,
`launch_recovery_check` 20. No flakes.

**Review follow-up.** The review of 9961caa found one slip, and it is real. The red connection-failure line did not
check that the run's state was `paused`. After the failures, the engine sets the stop reason and its error, then keeps
writing `running` while it drains the jobs in flight, cleans up over the dead link and saves. If the worker dies in that
window, `run_status` turns the run into `interrupted` and keeps the stop reason. The page then said "everything is
saved" beside a chip that said "(the worker is gone)", but only acknowledged data is kept there. The same was true from
`pausing`, where the user-pause line ("Paused at ...: everything is saved") spoke for an interrupted run, as it did
before SIF-89. `frontend/src/panels/RunControl.tsx`: both pause lines now need the state `paused`, so an `interrupted`
run gets no line, as the entry above says. `describe()` already told the two apart. Nothing else changed. `tsc` clean;
`run_control_check` 149, six new: from `running` and from `pausing` (through "Pausing..."), a worker gone before the
pause is written leaves "Resume", no line starting "Paused", and a chip ending "(the worker is gone)". Resume then
continues the run. `save_now_check` 29, `launch_recovery_check` 20. No flakes.

### SIF-90 Continue... is offered only where it can go, opens once, and gives focus back (2026-10-22; from the usability audit)

**Found.** The Runs window offered Continue... for any run at rest that kept a save point (audit findings J4-3, J4-2,
J3-14, J4-15). That included failed and cancelled runs and "model only" runs, which Run status refuses. The press closed
the window and landed on an open budget form with a greyed-out Continue. For a failed or cancelled run the reason was
only in a tooltip: the `.continue-why` line was drawn only for a state Continue goes on from. The window's request was
never used up. Run status is drawn anew at each return to its tab, so the budget form opened again every time the user
came back to Run status for that run: after a Cancel, and also after the run had been continued and was live, as a
greyed-out form that took the focus. Cancel or Escape dropped the keyboard focus to the top of the page, because the
focused field went with the form and Continue... was off while the form was open.

**Changed.** `frontend/src/runState.ts`: `CONTINUE_STATES` (paused, stopped, interrupted, completed) is exported beside
`CONTINUABLE`. `frontend/src/panels/RunList.tsx`: a run's Details offer Continue... only for a full save point
(`full_state`) and one of those states. A failed, cancelled or model-only run that kept a save point says why beside the
actions instead, for example "Continue... is not offered: a failed run cannot be continued. Load run brings its model
into the next run (Fine-tune or Evaluate only)." The Load run sentence is left out when Load run is off (its own reason
then says where the model can go). It points to Load run, not New run like this: Load run takes this run's newest save
point, while New run like this repeats the run from its parent's. The "Can continue" column is unchanged.
`frontend/src/panels/RunTabs.tsx` (`StatusTab`): the reason beside Continue... also stands for a failed or cancelled run
whose worker is gone ("A failed run cannot be continued."). The form's request is marked answered as it opens
(`onAsked`). Cancel, Escape and the form's Continue give the focus back to Continue..., or to the Run status tab button
when Continue... is off by then (a run that went on). `frontend/src/panels/BottomPanel.tsx`: the panel stays mounted and
keeps the last request answered, so Run status gets the window's request only once. Typed text is still not kept across
a tab switch (the audit's optional part, left out). Nothing is sent by any of this: the budget form, its question for a
real run and the launcher are unchanged. `docs/workbench.md` (the budget form; the Runs window's actions) and
`docs/functionality-reference.md` (Load run...; Run status) say so. Skipped: J4-15's sortable column titles and the
Enter key on a run's row. They are keyboard work for batch 27 ("Enter and the keyboard work where the mouse does").

**Checked.** `tsc` clean. `run_list_check` 137 (129 before). A new fixture, a failed run with a full save point, is in
section 10's list (nine runs). DONE offers Continue... with no `.continue-not` line. RESUMED (model only) and the failed
run offer Load run, Show results and New run like this, with the lines quoted above. Their rows still read "model only"
and "yes". Show results of the failed run lands on Run status with "A failed run cannot be continued." beside a
greyed-out Continue.... A run with no save point says nothing of Continue.... After the window's Continue..., Cancel
gives the focus to Continue..., and Logs then Run status does not open the form again. Nothing is continued.
`run_control_check` 152 (149 before): Cancel and Escape give the focus back to Continue... and send nothing; after the
form's Continue the focus is on the Run status tab and Continue... is off. `export_check` 31, `launch_recovery_check` 20,
`task_run_check` 39. No flakes.

### SIF-91 Output settings lock to the working run, and their presses show they are working (2026-10-22; from the usability audit)

**Found.** The output root's lock ("The run directory is locked while a run is active") followed the run the bottom tabs
show, not the header's run (audit finding J7-3). With an ended or paused run shown under a live one, the root could be
changed under the live run, and the page's run list (Runs, Running now, the chip's task name) moved to the new root.
"Current run paths" listed the shown run's folders without saying which run they were of, inside settings that SIF-72
calls the next Start's. Test writability, Measure, Browse allowed roots... and a folder of the list showed nothing while
their answers were on the way, which takes seconds on D: (J7-4). A writable root's tested answer read exactly as the
automatic look before it, so a successful test changed nothing on screen. Test writability and Measure shared one
newest-press line, so a Measure press dropped a test on its way, which then never answered. Experiment ID was a bare
text box (J7-10). An existing ID stood only in the Runs window (the Experiment column's tooltip, a run's Details) as
"name__<12 hex>", to be split and retyped with the name matched by hand, and a wrong one was found only at Start.

**Changed.** `frontend/src/App.tsx`: `headerWorks` is true while the header's run has a live worker or a Start or Resume
is on its way (the header still holds the run before then). It goes to `OutputPanel` with the run list.
`frontend/src/panels/OutputPanel.tsx`: the root and Browse lock while the header's run works, and still while the shown
run works, as before. The hint is unchanged. "Current run paths" keeps its title and names its run in a line under it:
"Of the run shown: <folder>", with the path in the tooltip. Test writability, Measure and the folder list each ask on a
line of their own, with their own busy state. Test writability reads "Testing..." and is off only while its own request
is out (a folder listing held does not hold it). Measure reads "Measuring..." and takes no second press. "Reading the
folder..." stands above the list while a folder is read; Close, "Use this folder" and another root let it go. A test's
answer says when it came, in local time: "writable · tested 14:03:22 · 400.00 GiB free". Experiment ID has a list
(`<datalist>`) of the experiments of the runs under the root, each once, with its runs counted and a MOCK one marked
("2 runs", "1 run, MOCK"). A run from before the ID ("__None") adds none. One picked sets Experiment name and Experiment
ID together. An ID typed by hand is kept as typed. When no listed run is in "<name>__<id>", a hint says "No run listed
here is in ...: Start refuses an experiment that is not under the output root." Nothing is started, saved or written by
any of this. `docs/workbench.md` (Room for the tables) and `docs/functionality-reference.md` (Output root; a new
Experiment name and ID row) say so. Skipped: the audit's optional backend check (`validation.py` flagging a missing
`<root>/<name>__<id>/experiment.json` before Start). It is backend Python, outside this branch's frontend work, and
live only after an 8765 restart.

**Checked.** `tsc` clean. `output_panel_check` 92: Measure reads "Measuring...", is off, and a second press asks
nothing until its held answer comes. With a test and a folder held, Test writability reads "Testing..." and is off, and
"Reading the folder..." stands above the list. A folder held alone leaves Test writability on. Close takes the hint
away. The held test then answers "NOT writable · tested hh:mm:ss · ...". A writable test reads "writable · tested
hh:mm:ss · ... free". Experiment ID offers the FIXTURE run list's two experiments as above (`GET /api/runs` answered
here); picking one sets "sweep" and "0123456789ab" in the boxes and the configuration, a hand-typed ID gets the hint,
and an emptied one is new again. `room_check` 29: "Of the run shown: run", the path in its tooltip.
`run_control_check` 155: the output root and Browse are locked with the hint while a Start is on its way, and while
the header's run works with a paused run shown; they unlock once it is paused. `module_fold_check` 30, `looks_check`
74, `export_check` 31. No flakes.

**Review follow-up.** The review of 1d7cb67 found two slips, both real. (1) Experiment ID's list offered every
experiment under the root, MOCK ones included, whatever kind of task was loaded, and the hint looked only at whether the
name was listed. Start looks for a MOCK task's experiment under `<root>/mock` and a real task's under the root itself
(`runs.py`, `paths.py` `data_root`; `layout.py` raises `FileNotFoundError`), so an experiment of the other kind, picked
from the list, was refused at Start, after a real run's question, with no hint. `frontend/src/App.tsx` passes the loaded
task's kind (`circuit.mock` once loaded, as `shownRun.ts` reads it for the Start question) as `taskMock`.
`frontend/src/panels/OutputPanel.tsx` offers only that kind's experiments (both before a task is loaded), and one of the
other kind, typed by hand, says so: "sweep__0123456789ab holds real runs: Start of this MOCK task looks for it in the
output root's mock/ folder and refuses it." (2) "Use this folder" in a folder list opened while idle stayed on after a
Start or Resume was sent, or while the header's run worked, and set the root under the run. It is now off with the root
(`disabled={locked}`). Opening folders in the list still works; it changes nothing. `docs/workbench.md` and
`docs/functionality-reference.md` say both. Nothing is started, saved or written by this. `tsc` clean.
`output_panel_check` 95 (92 before): with the MOCK task's circuit read (a registered task, local files) after a reload,
the list holds only "trial__abcdef012345" ("1 run, MOCK"), the real one typed gets the line above, and the MOCK one
picked gets no hint. `run_control_check` 157 (155 before): a list opened while idle has "Use this folder" on; once
Start is on its way it is off, and a press leaves the root as it was. `room_check` 29, `module_fold_check` 30. No flakes.

### SIF-92 Save as keeps a refused name, and the rough-frequency question has Enter and Cancel (2026-10-22; from the usability audit)

**Found.** After the backend refused a save (a range that does not hold the present value, a grid problem), the next
Save as offered the numbered name again (`<cell>_2`): the name the user had typed was lost at each refusal, and
refusals are frequent while a task is set up (audit finding J1-9). A ring oscillator's save stops to ask for its rough
oscillation frequency under the toolbar. That row had no Cancel, Enter in its box did nothing, and the tab line's Save as
stays off while it asks, so a user who meant another name, or no save, was held there until another task or cell
(J6-13).

**Changed.** `frontend/src/panels/TaskSave.tsx`: Save as proposes the name chosen for the last save when that save was
not made - a chosen name that is valid and not in the task list (another task or cell clears the choice, and a saved
name is listed). Otherwise it proposes the numbered name as before; a cell's first proposal stays `<cell>_2` (record
7.246). The tab line's tooltip says "(after a refused save, the name chosen for it)"; its frequency wording stays as
SIF-68 left it. The frequency row is a form. Enter in the box saves as the row's Save as does, under the same rule (a
frequency that reads, a connection, no save under way); the row's Save as is its submit button. A new **Cancel** (and
Escape in the box) ends the question, its box and its message: nothing is saved, and the tab line's Save as is on again.
Cancel is off while the save with a frequency is under way. Cancel keeps the chosen name, unlike the audit's plan
(`setChoice(null)`): with J1-9 the next Save as offers it, which is what a user who stopped to change the name needs.
Nothing is saved or written to Virtuoso without the same press as before. `docs/workbench.md` (Saving a task) and
`docs/functionality-reference.md` (Save as) say so. Not done: focus moving to the box when the question comes, or back
to Save as after Cancel; that is keyboard work for batch 27.

**Checked.** `tsc` clean. `virtuoso_source_check` 104 (98 before). After the `refuse_me` refusal, the next prompt
offers "refuse_me". The question is a form whose Save as is a submit button with a Cancel beside it, and the tab line's
Save as is off. Cancel sends nothing, takes the row and its message away, and turns Save as on. The next prompt offers
"ota5_v1" and the question comes back with an empty box. Escape in the box does what Cancel does. "fast" and Enter send
nothing and leave the question. "1.2G" and Enter send 1.2e9 Hz, never as_new. Four prompts in all
(`ota5_v1_2`, `refuse_me`, `ota5_v1`, `ota5_v1`). `task_save_check` 76, `project_help_check` 50,
`ngspice_window_check` 43, `calibration_save_check` 22, `unsaved_rows_check` 25. No flakes.

### SIF-93 The task file says when the editors changed and what Apply holds back (2026-10-22; from the usability audit)

**Found.** The Task file window is a snapshot of the editors' rows when it was read. Its hint invites changes "here or
in the editors", but an edit made in the editors after that was replaced without a word by the next **Apply to editors**,
which put back the file's older rows (audit findings J2-8, J6-11; a second Task file press only brings the window
forward, as SIF-87 keeps it). The file's other parts (Maestro analyses, variables, initial conditions, bindings, the rough
frequency, notes) wait in the page for the next save. Nothing showed they were waiting. Undo did not take them back, and
a reload or another task dropped them silently. The message "Applied: the editors now hold these rows ... Undo takes them
back" read as if the whole file were in the editors (J1-10, J6-12).

**Changed.** `frontend/src/panels/TaskSave.tsx` keeps the editors' rows the file was read from. After an Apply, it takes
them from the rows that Apply left, in a layout effect, so rows the backend writes out its own way are no change and
nothing flashes. While the editors differ, it tells the window. A new read (`readFile`) serves both Task file and
**Read again from the editors**. It also keeps `pending`, the parts beside the rows that applied files changed. They are
counted from the first file read since the last save, because the backend returns every part on every Apply. A line
under the toolbar names them: "From the task file, not saved yet: Maestro analyses, notes. Save as stores them; a reload
or another task drops them." A successful save clears the line, unless a file applied during the save added more, and so
does another task or cell. `frontend/src/panels/TaskFile.tsx` adds `otherPartsChanged`, which compares those parts of two
files with keys in one order. While the editors changed, the window shows "The editors changed since this file was read:
Apply replaces those changes too (Undo in the editors takes it back)." with a **Read again from the editors** button. That
button reads the file of the editors as they are now and drops the draft. If changes typed in the window are not applied,
it first asks there: "Read again from the editors? Your changes to this file are dropped." Apply then takes two presses:
the first only turns it into **Apply anyway**, with a tooltip saying what it replaces. "Applied" now says: "the editors
now hold its rows, and Save as will send its other parts. Undo takes back the rows only." Nothing is saved, run or
written to Virtuoso by any of this. `docs/workbench.md` (the task file) and `docs/functionality-reference.md` (Task file)
say so. Not done: keeping the waiting parts across a reload, or making Undo take them back (the audit's larger fix: a
schema field or browser storage). Also not done: counting them in the not-saved summary and the switch-task question.
The line and the Applied message now say what happens to them.

**Checked.** `tsc` clean. `task_save_check` 87 (76 before). The Applied message has the new words. After the Apply,
the window has no "editors changed" line, and the toolbar line names "Maestro analyses, notes". The editors' Undo brings
the line (photographed, `task-file-editors-changed.png`). The first Apply press sends nothing, changes nothing and reads
"Apply anyway". **Read again from the editors** with nothing typed since the Apply asks nothing. It sends one read with
the editors' rows (1.1e9 Hz), and the line goes. With a draft typed and the editors' Redo, it asks in the file window;
Cancel reads nothing and keeps the draft. Apply's first press sends nothing, and **Apply anyway** applies (upper 1.7 in
the editors, the line gone). The waiting parts stay named, every question of the window was planned, and the save sends
them and takes the toolbar line away. `virtuoso_source_check` 104, `project_help_check` 50, `working_copy_check` 34,
`calibration_save_check` 22, `unsaved_rows_check` 25. No flakes.

**Review follow-up.** The review of 2331c35 found two slips, both real. (1) A draft kept from a closed window (SIF-87)
lies over a later reading, so the rows of that reading were compared with the editors. An edit made in the editors while
the window was closed went unsaid, and the first Apply put the draft's older rows back. `frontend/src/panels/TaskSave.tsx`
now keeps `keptRows`, the rows the draft was typed over, taken when it is first kept. While such a draft is in the box the
editors are compared with those. Revert, an Apply or **Read again from the editors** ends the draft, and the reading's
own rows count again. The review's smaller fix, keeping the old rows in `readFile`, would have kept them through Revert
and through the read again too, so the line would have stayed. (2) After a save the base of `pending` went back to null.
The next Apply from the window still open (Calibration's **Apply and save** keeps the task, so the window stays) then
counted from the file read before that save. It named parts just saved as waiting. A save now leaves the base at the
text of the last Apply (`lastApplied`), which is what it sent. `docs/workbench.md` says a kept draft keeps its rows.
Nothing is saved, run or written by this. `tsc` clean. `task_save_check` 91 (87 before): a draft kept while the editors'
Undo ran shows the line when opened again, and its first Apply sends nothing. **Read again from the editors** asks about
it, reads once and the line goes. Applied again after Calibration's save from the window still open, no part is named as
waiting. Each new check fails on the code before its fix. `virtuoso_source_check` 104, `project_help_check` 50,
`unsaved_rows_check` 25, `calibration_save_check` 22, `edit_state_check` 24. No flakes.

### SIF-94 Every copy says "copied", from the window it was clicked in (2026-10-22; from the usability audit)

**Found.** The RL model window's folders (a model's Details, the model in use, a model that left the list) were copied
through the main page's clipboard. The click happens in the pop-up, and a browser refuses a clipboard write from a window
that does not have focus. The refusal was dropped, so a failed copy showed only at the paste (audit findings J7-2,
J5-10). Output settings' **Copy path** and its Current run paths, Output files' **Copy run path** and Data tables' id and
JSON cells copied without a word either way (J7-2, J4-14), while the Run folder in Run status and in the Runs window said
"copied" (SIF-54). `copy()` returned nothing where there was no clipboard, and no caller but Run status handled a refusal.

**Changed.** `frontend/src/api.ts`: `copy(text, from)` writes through the clipboard of `from`, the window clicked in (the
main page's when none is given or it has closed), and always returns a promise; no clipboard rejects too. New
`frontend/src/panels/copied.tsx`, `useCopied(from)`: `copyText` copies, and `word(key)` puts " copied" (the ok colour) or " could
not copy" (amber; its tooltip says to select the text and copy it with Ctrl+C) after what was clicked, for 1.5 s, for
that key only. `ModelChooser.tsx` (Details' Folder; a model that left the list) and `RlModelWindow.tsx` (the model in
use's Folder) use it with the pop-up. `OutputPanel.tsx`: Copy path's word stands just before it (`styles.css`,
`roadster.css` `.field-head .copy-word`: pushed to the right, at the caption's size), so the button keeps its text and its
place at the line's end; a Current run paths cell says it in the cell. `RunTabs.tsx`: Run status's Run folder uses the
same hook, so a refusal is said there too; a Data tables cell says "Copied <column>." on the tool line, or "Could not copy
<column>: the browser refused the clipboard; select the cell's text instead."; Copy run path says "Copied the run path."
or "Could not copy: the browser refused the clipboard. The run path: <path>" (the tab shows the path nowhere else). A
copy starts, saves and writes nothing. Not changed: the Runs, Connection and Agent windows already copy through their own
clipboards and say "Copied" on success; a refusal there stays unsaid. `docs/workbench.md` (a paragraph after Data tables'
one line per row) and `docs/functionality-reference.md` (Output root and Copy path, Saved models, Run status, Data
tables, Output files) say so.

**Checked.** `tsc` clean. `output_panel_check` 98 (95 before): Copy path says " copied" just before the button, at its
size, the button keeping its text and its place at the line's end; the word goes after 1.5 s; a refused copy says " could
not copy" with its tooltip. `model_chooser_check` 98 (95 before): a model's Details Folder and the model in use's Folder
are written to the pop-up's clipboard, never the main page's, and say "copied"; a refused copy of a missing model's
folder says "could not copy", then the path alone again. `files_tab_check` 22 (20 before): "Copied the run path.", and
the refusal note with the path. `looks_check` 75 (74 before): "Copied <column>." for an id cell. `run_control_check` 158
(157 before): Run status's refused copy says "could not copy". `room_check` 30 (29 before): a Current run paths cell says
"copied". Also run, unchanged: `export_check` 31, `calibration_check` 38, `calibration_save_check` 22,
`dom_identity_check` 56, `training_tab_check` 103, `run_list_check` 137, `task_rows_check` 54, `typing_check` 50,
`save_now_check` 29, `task_run_check` 39, `network_panel_check` 62, `reliability_check` 20, `encoder_models_check` 24,
`graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 33, `pdk_check` 40, `model_structure_check` 31,
`agent_window_check` 29, `network_inputs_check` 9 (26 scripts, 1,387 checks, one lane). No flakes.

**Review follow-up.** The review of 140ce51 found two slips, both real. (1) In Output files, "Packing..." is the only busy
state of **Download data-only package**: it disables the button and shows the hourglass. Copy run path's new note
replaced it, so a copy while a package was still zipping freed the button for a second pack, and the first one's
"Downloaded <name>." later replaced the copy's note. `frontend/src/panels/RunTabs.tsx`: the copy's notes now leave
"Packing..." standing. The copy still happens; only its word is not said over the packing. A packing state of its own
would also have worked, but the note is cleared when the shown run changes, and a separate state would have changed when
the button is free again. Not changed: a single file's "Downloaded <name>." still replaces "Packing..." when it lands
during a pack, as it has since 2026-09-26. (2) Output settings' Current run paths keyed their word by the row's name
alone. A copy, then another run shown within 1.5 s, put " copied" on the new run's path, which was never copied.
`OutputPanel.tsx` keys it by the row and its path, so another run's row says nothing, as Run status's Run folder does.
Nothing is saved, run or written by this. `tsc` clean. `files_tab_check` 24 (22 before): with the package request held,
a copy copies the run path, and the hint still says "Packing...", the button disabled with the hourglass; the package
answered, the hint says how it went and the button is ready again. `room_check` 30 and `output_panel_check` 98, unchanged.
No flakes. The second fix has no new check: the checks' fixtures show one run only.

### SIF-95 Blocking issues take you to the row, and each editor tab counts its own (2026-10-22; from the usability audit)

**Found.** The header's blocking-issues list named each issue's place as text only ("targets[3].lower row inl1"). To
fix one, the user switched tab by hand and looked for the row among 66. The Find box could hide it, because a row with
an error is never folded away but Find has no such exemption (audit finding J2-1). A tab not in view never showed its
errors: the rows show theirs on the open tab only. So a Spec that a renamed or deleted Probe broke was told on
Parameters by the header's count alone, which names no tab (J2-2).

**Changed.** `frontend/src/panels/Issues.tsx`: a row issue's Where (the field and " row <key>") is one button with the
same words. It sends `GO_TO_ISSUE` with the table, the row's key and the field. A run or output field and the whole
configuration stay text, and the list stays open (a checklist, record 7.12). `frontend/src/panels/Editors.tsx` listens for
it. It opens the tab the way a tab press does: Matched devices closes and the ticks go only when the tab changes. It finds
the row by its ID, not by the report's index, and clears that tab's Find text if the text hides the row. It opens the
leader's ties if the row is folded (a report older than the rows can leave it so). Then it scrolls the row into view and
focuses the issue's field, so the formula bar names it. The objective goes to the Limit list. A column behind More
columns goes to the row's ID, and a follower's greyed field is chosen without focus, so the bar still says why. The
choice runs after the tab's reset effect, which otherwise let the chosen cell go. Each editor tab counts its blocking
issues (error and blocker, paths `<table>[...]` or `<table>.`) in a small red pill drawn from an attribute of an empty
span (`roadster.css` `.tab-errors::before`), so the tab's words, which several checks read, stay its name and row count;
the button's `::after` was taken by the not-saved dot. Its tooltip gives the first issue after the not-saved line ("2
blocking issues, the first: ... The red button in the header lists them: each one's Where goes to its row."). Nothing is
saved, run, validated anew or written to Virtuoso by a press; it moves the view and the focus only.
`docs/workbench.md` (the blocking-issues paragraph under Tests) and `docs/functionality-reference.md` (N blocking issues;
the editors' tabs) say so.

**Checked.** `tsc` clean. `blocking_issues_check` 49 (42 before): a row issue's Where is a button with its words as
before, a run field and the whole configuration stay text; the Parameters tab counts its issue in a red pill (content "1",
the bad fill) with its words unchanged and the tooltip, Probes none; with a Find text hiding the spec and Parameters
open, Specs counts its two issues and its tooltip gives the first; the spec issue's Where opens Specs, clears the Find
text, focuses the row's Equation and the formula bar reads "Equation · score"; the list stays open; a Parameters issue's
Where goes back to its row's Lower. The new checks fail on the code before the change. Also run, unchanged:
`task_rows_check` 54, `sheet_check` 45, `find_fill_copy_check` 30, `spec_equations_check` 36, `looks_check` 75,
`unsaved_rows_check` 25, `editor_columns_check` 23, `formula_bar_check` 21, `matched_devices_check` 37 (10 scripts, 395
checks, one lane). No flakes.

**Review follow-up.** The review of 719e3c5 found three slips, all real. (1) A tab's tooltip promised "its Where goes to
the row" for every blocking issue it counted, but the tab also counts the table's own issues: `nothing_to_optimize`,
`binding_graph`, `multiple_preferences`, `no_hard_constraint` and `task_not_saved` sit on the bare path "parameters" or
"targets". Their Where is text, and so is the Where of a row with an empty ID. An empty Parameters table read "1 blocking
issue: At least one optimized variable is required. The red button in the header lists it: its Where goes to the row",
with no row and no button. `Editors.tsx` now counts the issues `rowOf` (now exported from `Issues.tsx`) finds a row for.
With none it says "lists it." or "lists them." alone, and with some "a Where that names a row goes to it". (2) The
Where's tooltip named the issue's field, but a field with no column in view chose the row's ID. That covers the Unit of
Parameters and Specs (hidden since 7.208, the place of `unit_mismatch`, `target_unit_mismatch`, `unknown_unit`,
`binding_unit_mismatch` and `parameter_unit_not_variable`), Initial value, and Judged at without corners. It also covered
a column behind More columns, such as the Scale of the blocker `scale_needed_for_zero_limit`. A press on a field behind More
columns now shows them, for this page only, so the field the tooltip names is chosen. The kept choice is not changed,
just as a cleared Find text is not. For a field no column shows, the tooltip names the cell that is chosen: "Specs opens
with its Spec ID chosen, as no column shows its Unit." The rule for which columns a table draws moved to `editorRules.ts`
(`drawsColumn`, `columnOf`), so the tooltip and the table read the same rule. `docs/workbench.md` and
`docs/functionality-reference.md` no longer over-claim. (3) The press found its row by ID alone, so a duplicate ID went
to the first row with that ID. `validation.py` reports `duplicate_variable_id`, `duplicate_measurement_id` and
`duplicate_metric_id` on the later row, so the press went to the wrong row, and so did any other issue of that row.
`GO_TO_ISSUE` now carries the report's index too. The press uses that row while it holds the report's ID (the test
`rowIssues` makes), and finds the row by ID only otherwise. Nothing is saved, run, validated anew or written to Virtuoso
by a press. `tsc` clean. `blocking_issues_check` 60 (49 before): a tab whose one issue is the table's own says "lists it."
and its Where is text; a tab with both kinds says a Where that names a row goes to it; the Unit issue's tooltip names the
Spec ID, which is chosen with More columns left folded; the Scale issue's tooltip names the Scale, and its press shows
More columns and chooses it, the kept choice unchanged; with the last Parameters row's ID typed as the first's, the
duplicate's Where and its Lower issue go to the last row. 7 of the new checks fail on the code before the fix. Also run,
unchanged: `editor_columns_check` 23, `task_rows_check` 54, `typing_check` 50, `sheet_check` 45, `find_fill_copy_check`
30, `spec_equations_check` 36, `looks_check` 75, `unsaved_rows_check` 25, `reward_block_check` 33, `formula_bar_check` 21,
`matched_devices_check` 37, `callouts_check` 8 (13 scripts, 497 checks, one lane). No flakes.

### SIF-96 Add, Delete and the tick boxes do what they say, in view (2026-10-22; from the usability audit)

**Found.** **Add** put the new row at the end of the table, out of view, and left the focus on the Add button. While
Find rows held text, the new row ("parameter_67") usually did not match it and was hidden, so Add seemed to do nothing:
only the tab's count changed (audit finding J2-4). **Delete selected** said nothing at all. It did not say how many rows
went or which. A deleted leader left its tied rows following nothing, which is a blocking error. A deleted Probe broke
every Spec equation using it, on a tab not in view. A ticked tied row that was folded away afterwards was deleted
unseen (J2-3). The tick-box column's header was empty, with no "tick all" and no Shift+click range, so deleting 20 rows
took 20 ticks (J2-9).

**Changed.** `frontend/src/panels/Editors.tsx`: Add still puts the row at the end. If a Find text does not match the new
row, the text is cleared, and the line under the formula bar says "Find rows cleared to show the new row, parameter_6.".
On the render after the press, the new row is scrolled into view and its ID is focused with the text selected, so the name
can be typed at once. A new Maestro-output Probe gets its Output name focused instead, because its Probe ID is read-only and
follows that name. Delete selected removes the same rows as before (record 7.184). The line under the formula bar now
says what went: "Deleted 2 rows (a, b), 1 of them folded under a leader. Undo takes them back." It is amber when it also
names the rows that were tied to a deleted leader and now follow nothing ("<row> was tied to a deleted row and now
follows nothing."), or the Specs whose equation uses a deleted Probe ("Spec <id> uses a deleted Probe."). The focus
then goes to the tick box of the row now in the first deleted row's place. The pressed button turns disabled, which used
to drop the focus to the page. With no row left in view, the focus goes to Add. It goes to the tick box rather than a
text cell, so a key typed next edits nothing. The tick-box header holds a box, "Tick every row in view". It ticks or
unticks every row in view, is half ticked while only some are, and is disabled while no row is in view. A row that a fold
or Find hides keeps its tick. Shift+click on a row's box gives every row in view, from the box clicked last to this one,
the new state. Its mouse press chooses no page text. The tooltips of Add, Delete selected and the header box say so.
`frontend/src/panels/editorRules.ts`: `usesProbe(equation, id)` uses the whole-name rule that the rename of a Maestro
output uses (`renameInEquation`, now built on the same pattern). `frontend/src/styles.css` and `roadster.css`: the
header's box takes the rows' size and padding and stands over the row boxes at the cell's start. The column keeps its
width, which `--sel-w` measures. Nothing here saves, starts a run or writes to Virtuoso. Add and Delete are one Undo step
each, as before; a focused cell on a cramped page folds the bottom panel as a click there does (record 7.372). Not
changed: Undo does not clear the line under the formula bar, so "Deleted ..." stays after an Undo, as a paste's or a
fill's line does. Tied rows are not untied by a Delete (the audit's verdict). `docs/workbench.md` (a bullet after Find
rows) and `docs/functionality-reference.md` (the toolbar row) say so.

**Checked.** `tsc` clean. `find_fill_copy_check` 50 (30 before). Deleting a ticked row under Find says "Deleted 1 row
(...). Undo takes it back." and, with no row left in view, focuses Add. A deleted Probe names its Spec, in amber, and
the focus goes to the row in its place or to Add. Add on Probes with a Find text clears it, says so, and focuses the new
Maestro-output Probe's Output name. The header box ticks the three rows in view and no folded row, is half ticked after
one is unticked, ticks all again, then unticks all. A real Shift+click ticks the span, and a Shift+click on a ticked box
unticks it. A deleted leader names its tied row, in amber, and the focus goes to the tick box in its place. A ticked row
folded away is deleted as before, and the line says it was folded. Add on Parameters with a Find text focuses the new
row's ID, its text all selected, within the table's view. `spec_equations_check` 36: Add pressed while a typed cell has
focus is still its own Undo step, and the focus then moves to the new Spec's ID. Before, the check required the focus to
stay in the cell. `sheet_check` 45: the dark-pixel test of the sticky heads hides the header's own box while it takes
its pictures. On the code before the change, 5 of the new checks fail and the script stops at the missing header
box; the changed `spec_equations_check` assertion fails too. Also run, unchanged: `typing_check` 50,
`editor_columns_check` 23, `reliability_check` 20, `task_rows_check` 54, `unsaved_rows_check` 25, `formula_bar_check` 21,
`blocking_issues_check` 60, `matched_devices_check` 37, `looks_check` 75, `edit_state_check` 24, `dom_identity_check` 56,
`testbench_probes_check` 41, `room_check` 30 (16 scripts, 647 checks, one lane). No flakes.

### SIF-97 Undo works from anywhere, and says what it took back (2026-10-22; from the usability audit)

**Found.** Ctrl+Z and Ctrl+Y worked only while the focus was in an editor cell. After an Import's or Matched devices'
Apply (the box goes away), after a tab press, or after a Delete that left no row in view (the focus on Add), the keys
did nothing, and those are the moments Undo is wanted (audit finding J2-5). Undo is page-wide (rows on any tab, run and
output settings, an applied proposal), but it said nothing about what it took back. A change on another tab, in a folded
tied row or in Run configuration was reverted out of view, and the next press could go one step further than meant
(J2-15). The RL model window says "One Undo step" on every Mode button, Use template and Use this save point, but it had
no Undo; the user had to go to the main window's toolbar and come back, and its learning-rate notice said "Undo in the
main window" (J5-5).

**Changed.** `frontend/src/history.ts`: the history keeps its last Undo or Redo and the two configurations it moved
between (`lastStep`), until the next recorded change. `frontend/src/windows.ts`: `undoKey` says which step a key press
asks for: Ctrl+Z (Cmd+Z), and Ctrl+Y or Ctrl+Shift+Z. It gives none in a box that takes typing (Find rows, the formula
bar, number and name boxes), which keeps the browser's own undo of its text as the formula bar did (record 7.188), for a
key a cell has already handled, or inside a dialog open over the page. `frontend/src/panels/Editors.tsx`: a key listener
on the main window's document does the page's Undo and Redo wherever the focus is; a cell still handles the keys first,
as before. The line under the formula bar names what an Undo or Redo changed, whichever button, key or window it came
from: "Undo: Parameters w1 (Notes)." gives the tab, the row's ID and, when one row changed in up to three fields, their
headers. A table whose length changed reads "Undo: Parameters w3 added."; more than four rows read as a count; the other
sections use the import confirmation's words ("Redo: run settings."). When the rows are on a tab not in view, the line
offers "Show Parameters" (that tab's name) and the tab is not switched by itself. Switching by itself would let the
chosen cell go and fight the tab's own reset. The tab buttons, the not-saved list's links and that button share one
`showTab`. The toolbar's Undo and Redo tooltips name the keys and the line. `frontend/src/panels/RlModelWindow.tsx`, `Right.tsx`,
`App.tsx`: the window's heading has Undo and Redo icon buttons at its right, titled as the toolbar's and disabled as
they are. They are the page's one history, and the window's keys work as in the main window, except in its text boxes
(the model's name, the numbers). The learning-rate notice says "Undo restores the previous value."
`frontend/src/styles.css`: the two buttons sit together at the heading's right. Nothing here saves, starts a run or
writes to Virtuoso: the keys and the window's buttons do what the toolbar's Undo and Redo did. The verdict's other part,
the focus after Delete selected, was done in SIF-96. Not changed: an Undo pressed in the RL model window is named in the
main window's line, not in the pop-up, which shows its result in its own controls. `docs/workbench.md` (a bullet after
Ctrl+Z and Ctrl+Y, and the RL model window's paragraph) and `docs/functionality-reference.md` (the toolbar, keys and Mode
rows) say so.

**Checked.** `tsc` clean. `sheet_check` 54 (45 before): Ctrl+Z in a cell says "Undo: Parameters <id> (Notes).", and
Ctrl+Y says "Redo: ...". With Specs in view and the focus on its tab button, Ctrl+Z takes the Parameters row back. The
line names it, with a "Show Parameters" button, and Specs stays in view; the button shows Parameters with the row taken
back. Ctrl+Y with the focus on the page itself redoes it. Ctrl+Z in Find rows and in the formula bar changes nothing and
says nothing. `find_fill_copy_check` 50: after a Delete that left no row in view, Ctrl+Z on Add brings the row back, and
the line says "Undo: Parameters <id> added." (the toolbar's Undo was pressed there before). `network_panel_check` 69
(62 before): the window's heading holds Undo and Redo and no close button; its Undo takes the last change back, and the
main window's line says "Undo: run settings."; its Redo brings it again. Ctrl+Z on a Mode button and Ctrl+Shift+Z in
the window undo and redo; Ctrl+Z in the model's name box leaves the configuration alone. `edit_state_check` 28 (24
before): the history keeps the last Redo and Undo with the configurations they moved between, keeps them through a Redo
with nothing to redo, and lets them go at the next edit. On the code before the change, 4 of the new `sheet_check`
checks fail and the script stops at the missing button; the changed close-button check and the new heading check of
`network_panel_check` fail and the script stops; and the Ctrl+Z check of `find_fill_copy_check` fails. Also run,
unchanged: `formula_bar_check` 21, `task_rows_check` 54, `typing_check` 50, `model_chooser_check` 98,
`spec_equations_check` 36, `matched_devices_check` 37, `crash_panel_check` 11, `mode_suggestion_check` 20,
`reliability_check` 20, `editor_columns_check` 23, `unsaved_rows_check` 25, `blocking_issues_check` 60, `looks_check` 75,
`network_inputs_check` 9, `reward_block_check` 33, `circuit_source_check` 17, `testbench_probes_check` 41, `room_check` 30,
`dom_identity_check` 56 (23 scripts, 917 checks, one lane). No flakes.

**Review follow-up.** The review of f90ff24 found one slip, real. The RL model window's keys were a React `onKeyDown` on
its section, which `PopupPortal` draws inside a root element in the pop-up's body. A press with the focus on the window's
page itself has the body as its target and never reaches the section: just after the window opens, after a click on
blank space, and after Use template or Use the template's values, whose pressed button goes away with the press (it
becomes "in use", or the comparison closes) and drops the focus to the page. That last one is the J5-5 case of taking a
wrong template back, and Ctrl+Z did nothing there, while `docs/workbench.md` said the keys work anywhere in the window.
`RlModelWindow.tsx` now listens on the pop-up's document, as `Editors.tsx` does on the main window's, with the same
`undoKey` filter, and removes the listener when the window closes. The docs and comments stand as written; they are
now true. Nothing here saves, starts a run or writes to Virtuoso. `tsc` clean. `network_panel_check` 72 (69 before):
Use the template's values pressed with the focus on it leaves the focus on the window's page, Ctrl+Z there brings the
differing values and their comparison back, and Ctrl+Y applies the template's values again with no write. On the code
before the fix, the Ctrl+Z check fails. Also run, unchanged: `model_chooser_check` 98, `typing_check` 50,
`encoder_models_check` 24, `model_structure_check` 31, `network_inputs_check` 9 (6 scripts, 284 checks, one lane). No
flakes.

### SIF-98 The time left and the best design's sizes without opening a window (2026-10-22; from the usability audit)

**Found.** The working time and "about N min left" of a run stood only on its card in the Running now window. Run status
showed the count and the bar, the header's run chip the count, and its tooltip the run folder. The user always asks for
that number, and had to open a window each time to read it (J3-5). Run status listed the best design's state, values,
conditions and margin, but not its variables, the device sizes a sizing run is for, although the same status holds them.
They were in the Runs window's Details alone: open the window, find the run among hundreds, press Details, or download
`best_design/parameters.csv` (J4-4).

**Changed.** `frontend/src/format.ts`: `timeLine(working, used, total, live)` is the run brief's line, moved out of
`RunBrief.tsx` with its wording: "Duration 5 min 01 s so far · about 10 min 02 s left" while the run works, "Duration
29 min 50 s" at rest, nothing before any working time. `TIME_LINE_HELP` is its tooltip. `frontend/src/panels/RunBrief.tsx`
uses it, with the same text as before. `frontend/src/panels/RunTabs.tsx`: Run status says the line under the bar
(`.status-hero-time`), apart from the budget's words above it, live by the brief's rule (`cardLive`), so the two agree
on one status. Its tooltip says how the time left is worked out. `frontend/src/panels/RunControl.tsx`: the run chip's
tooltip ends with the line, from the header's own status of that run; the chip's text stays the count.
`frontend/src/units.ts`: `inUnit`, `pairs` and `variables`, moved from `RunList.tsx` with the same output. A value that
is not a number is written as `short` writes it, inline: `unit_text_check` imports `units.ts` into node as it is, and
an import of `format.ts` does not resolve there. `frontend/src/panels/RunList.tsx` imports them. Run status has a "Best
design variables" row after the best design's values, with the Details' text ("input_pair_width = 2.34558 um;
load_capacitance = 250 fF"). A click copies it and says "copied" (or "could not copy") for 1.5 s, as the Run folder does.
`frontend/src/roadster.css`: the time line is in the hint's grey and size, and the row's cell shows the copy cursor. Not
done: the verdict's optional "searched variables first". The row keeps the Details' order, so the two read alike.
Display only: nothing here starts, pauses or continues a run, saves a task or writes to Virtuoso. `docs/workbench.md`
(the header chip, Run status at a glance, a copy says how it went) and `docs/functionality-reference.md` (Run brief and
Run status rows) describe it.

**Checked.** `tsc` clean. `run_control_check` 160 (158 before): with the live run's status giving 301 s of working time,
Run status reads "Duration 5 min 01 s so far · about N left" under the bar. The chip's tooltip ends with the same line
after "(record 7.264).", it ended there while the status gave no working time, and the chip's text is still the count.
The brief's own time-line checks pass unchanged. `run_list_check` 140 (137 before): the paused run shown in Run status
lists "input_pair_width = 2.34558 um; load_capacitance = 250 fF" after "Recorded values", titled "Click to copy". A click
copies that text and says "copied", then reads it alone again. Under the bar it says "Duration 29 min 50 s", with no "so
far" and no time left. The Details' pinned text passes through the moved helper. `export_check` 33 (31 before): on a real
MOCK run, the hero's budget words still read "evaluations used · 0 in flight · 0 failed", and the time line under the bar
reads "Duration 3 s". "Best design variables" names each of the best design's variables in order and says "Click to
copy". The new checks look for an element and a row that the code before the change does not have, so they fail there.
`unit_text_check` 14: the first run stopped at the import of `format.ts` from `units.ts` (node: module not found). With
the value written inline it passes, and so do `run_list_check` and `export_check` again. Also run, unchanged:
`calibration_check` 38, `run_control_live_check` 23, `dom_identity_check` 56, `save_now_check` 29, `looks_check` 75,
`task_list_check` 89 (imports `format.ts` into node), `room_check` 30 (11 scripts, one lane). No flakes.

### SIF-99 Data tables and Output files follow a live run, say when they were read, and find rows and files (2026-10-22; from the usability audit)

**Found.** Data tables and Output files read the run once, when the tab opened. Logs, Training and Run status followed
the run, but these two stayed at that moment during a live run, and their count lines never said when they were read
(J3-9, J4-10). Refresh kept the old answer until the new one came and showed nothing meanwhile, so a press that found
nothing new looked the same as a press that did nothing. Data tables always asked for the newest 25 rows, although the
route reads up to 500 and from either end. Evaluation #120 of 800 meant Export detailed CSV and a spreadsheet (J4-9). A
run's ~500 output files stood in path order only, with no filter and no sort, in a panel six rows tall (J4-13).

**Changed.** `frontend/src/api.ts`: `api.table(..., tail = true)` sends the route's `tail`. `frontend/src/panels/RunTabs.tsx`:
`useFollow` reads a tab again when the run's mark moves on for the same run, or when its worker ends. It does not
re-read on a timer. A run at rest is read once, as before. While the status is not read, nothing counts as a change.
Data tables' mark is the store's flushed sequence (record 7.280: rows reach the disk every 64 evaluations), so it reads
again only when there are new rows. Output files' mark is the last save point: each read walks the run's files on the
9p-mounted D: drive. `useReadAt` keeps the time an answer came, and both count lines end with "Read at 14:03:22.", after
the sentence the checks pin. Both Refresh buttons show the hourglass and "Reading..." while a read is on its way, and the
rows on screen stay until the new answer arrives. Data tables has two lists after the table list: "25 / 100 / 500 rows"
and "newest first / oldest first". Oldest first shows the table's first rows in the order they were written, not
reversed. The hint reads "the newest|oldest N shown, newest|oldest first"; with the defaults it reads as before. Output
files has a filter box on its tool line (`input.files-filter`): every typed word must stand in the path, in any case,
through `useTableView`'s `arrange` as in the Runs window. The count then reads "4 of 7 files shown, 8.2 MiB in all.", and
the filter clears when the run changes. Its column titles sort by path, size and modified time ("File ▲" at first, as the
backend lists the files), with the Runs window's marks and `aria-sort`. `frontend/src/panels/BottomPanel.tsx` passes
Output files whether the worker lives and its last save point. Both change rarely, so the memoised tab is not redrawn at
each status update (record 7.279). `frontend/src/roadster.css`: the two lists at their own width, the filter box 260 px,
the hand cursor on the sortable titles. Reads only: nothing here starts, continues or stops a run, saves a task or writes
to Virtuoso. `docs/workbench.md` (a new paragraph after "One line per row in Data tables") and
`docs/functionality-reference.md` (Data tables and Output files rows) describe it.

**Checked.** `tsc` clean. `files_tab_check` 42 (24 before). The count line says "Read at hh:mm:ss.". The list opens sorted
by File, A to Z, marked "File ▲". A press on Size sorts it smallest first, a second press reverses it, and File sorts it
back. "design" keeps the four design/ files ("4 of 7 files shown, 8.2 MiB in all."), "JOURNAL jsonl" keeps the two
journal files, and an empty box lists all seven again. The page is then reopened on the same run, now live. Status
updates with nothing new read neither tab again. A new save point reads the folder once. Data tables asks for limit 25,
tail true and lists the rows newest on top. A flush reads the table again. While that read is held, Refresh reads
"Reading..." with the hourglass and the rows stay; then comes the new count. "100 rows" asks for 100, "oldest first"
sends tail false and lists 1, 2, 3, and both lists sit on the table list's line. Back in Output files, the worker's end
reads the folder once more, then nothing. `export_check` 35 (33 before), on a real MOCK run: the pinned "12 rows, newest
first." is followed by "Read at hh:mm:ss.". "oldest first" lists commit_seq 1 to 12 in order and says so. Also run,
unchanged: `looks_check` 75 (Refresh is still the first button after the table list), `room_check` 30,
`run_control_live_check` 23, `training_tab_check` 103 (6 scripts, one lane, all passed the first time). No flakes.

### SIF-100 The Tasks window follows a task from its Details, reads again on a press, says what a delete did, and a rename takes effect (2026-10-22; from the usability audit)

**Found.** In the Tasks window a task could be followed only by a double click on its row. There was no button, the row
took no key, and a user who had opened Details to look at a task had to find the row again (J6-4); the Runs window's
Details have Load run. The task's name on the tab line, pressed while the window was open, only brought it to the front,
although its tooltip says it reads the lists again; Runs... does read again (J6-7). Deleting the task the page followed
said nothing in the window: the row and the "Current task" line just went. The answer was set only when the page had
moved on meanwhile, and the [generatedName] reset wiped any line the same press made (J6-6). After a rename of the
followed task, new runs kept the old name until the task was chosen again. The note sent the user to a double click,
which asks to discard their edits (J6-14).

**Changed.** `frontend/src/panels/TaskList.tsx`: the double click's body is `follow(key)`. It keeps the delete guard,
asks the edits question in this window (SIF-84) and closes the window once the task loaded. Three ways reach it: a
double click on the row (not on its buttons or tick box), Enter on the row (rows take `tabIndex` 0; Enter counts only
on the row itself), and **Follow this task**, first on the Name line of the Details of a task the page does not follow.
The window's hint names all three; the sentence the checks pin stays. Pressing the task's name while the window is
open calls `refresh(false)` before bringing it forward. Another window's link (`OPEN_TASKS`) does not read again, as
in the Runs window. `refresh` returns the task-list read. After a rename, the run label handed on is the one the list
then gives the task (`starter_project.task_name`): the label choosing the task again would bring. The typed name is
used when the list cannot be read. The rename note now reads "New runs of the task are filed under this name." for
every task. `frontend/src/panels/Left.tsx`: `renamedTask` sets `project.task_name` to that label while the page follows
the renamed task, with no Undo step (a label only, no rows). `frontend/src/panels/taskActions.ts`: Delete task always
answers in the window: "Task real:<name> deleted; its files are kept in <folder>. The page now follows its cell
<library>/<cell>." (or "... The page stays on what was chosen meanwhile."). The answer carries `follows`, the task
the delete left the page on, and the ngspice delete sets it too. The [generatedName] reset keeps a delete answer. A
new effect on `ref.task_id` clears it once the page follows another task. The next Check now or Delete press clears it
as before. `frontend/src/styles.css`: a focus ring inside a focused task row. Nothing here starts, continues or stops
a run, saves a task or writes to Virtuoso. Following still goes through the same task load and the same edits
question, Delete through the same confirmation, and a rename through the same route. `docs/workbench.md` (the Tasks
window's double click, Rename, "Nothing in the window updates by itself" and Delete task) and
`docs/functionality-reference.md` (Task-name button, Rename task, Delete task rows) describe it.

**Checked.** `tsc` clean. `task_list_check` 97 (89 before). With the page back on the MOCK task, the fixture OTA's
Details offer "Follow this task", whose tooltip says edits are asked about first. Pressed, it makes the page follow
the OTA and the window closes; opened again, the followed task's Details offer none. After Undo, Enter on the OTA's
focused row follows it too, and the window closes. Details reads its rows once (now counted from the press). Pressing
the task's name with the window open reads `/api/tasks` once more, not the run list. After the rename to "ota_relaxed"
the note reads "New runs of the task are filed under this name.", without "once the page follows it again". The saved
configuration's `project.task_name` and the header's RL model fact read "ota_relaxed", with no question asked. Taking
the rename back brings "fixture_ota" back. The MOCK task's Details start their Name line with an enabled Follow this
task. `virtuoso_source_check` 106 (104 before): after the delete, the Tasks window reads "Task real:ota5_v1 deleted;
its files are kept in /fixture/profiles/.deleted/ota5_v1.20260921T000000Z. The page now follows its cell
FIXTURE_DESIGNS/ota5_v1." The main page's folded note passes unchanged. Once the page follows the MOCK task the line is
gone from the window. The new checks look for a button, a key, a read, a label and a line that the code before does
not have. Also run, unchanged: `task_rows_check` 54, `task_run_check` 39, `ngspice_window_check` 43,
`circuit_source_check` 17, `testbench_probes_check` 41, `dom_identity_check` 56 (8 scripts, one lane, all passed the
first time), `project_help_check` 50. Not run: `consistency_check` (it presses Start against its fixture). No flakes.

**Review follow-up.** The review of baaf1e4 found one slip, real. After deleting the task the page followed, the answer
said "The page now follows its cell <library>/<cell>." and only a change of `ref.task_id` could clear it. Choosing
another library or cell in the Virtuoso window changes only `circuit.library` and `circuit.cell`; `task_id` stays null.
So the Tasks window kept saying the page followed the deleted task's cell after the page had moved to another cell
(the stale line the audit's J6-6 verdict warned of). `taskActions.ts` now keys the answer on `placeOf(ref)`: the task
key while the page follows a task, otherwise the source and library/cell. `follows` holds the place the delete left
the page on: the deleted task's cell, the task the ngspice delete moves to, or where the page already was. The line
goes once the page is anywhere else. A typed PDK id or class leaves it standing, since the page is still on that cell.
The main page's note (`deletedHere`) already compared library and cell and is unchanged. `docs/workbench.md` and the
Delete task row of `docs/functionality-reference.md` now say "another task or another cell". Nothing here starts a
run, saves a task or writes to Virtuoso; the confirmation, the deleting guard and the edits question are as they were.
`tsc` clean. `virtuoso_source_check` 108 (106 before): after a typed PDK id the window's line still stands, and once
another library is chosen in the Virtuoso window it is gone. Against the code before, that last check fails. Also run,
unchanged: `task_rows_check` 54, `ngspice_window_check` 43, `task_list_check` 97 (4 scripts, one lane, all passed the
first time). No flakes.

### SIF-101 Lists keep your place: Runs... opens at the shown run, a link keeps your filter, New folder keeps your ticks (2026-10-22; from the usability audit)

**Found.** Pressing Runs... to act on the run the bottom tabs show opened the window at the top of a newest-first list
(the user's 617 runs), in whatever folder and filter were left. The shown run was only marked, often hundreds of rows
down, so repeating it meant finding it by hand (J4-5). Every "Started from", "Runs that started from its model",
History and recorded-runs link set All runs, cleared the filter and the ticks, and could drop the one-task view - even
when the run was already in view. A filtered comparison was lost to look at one parent run, and nothing brought it
back (J4-7). In the Tasks window, tick, New folder, Move to… failed: New folder jumped into the new, empty folder and
the ticks went with the change of folder (J6-8; the Runs and saved models windows share the component).

**Changed.** `frontend/src/panels/RunList.tsx`: a press of Runs... while the window is closed sets `placeShown`. Once
the list it read is drawn and the window's styles are in (`styled`, SIF-86), the shown run's row is scrolled to the
middle - only when it is out of view, so a row in view stays where a click may be aimed at it. Nothing else happens: no
Details, no folder or filter change, and not through `focus`, which waits for its row and would pull the list to a
hidden run at a later filter change. A link from another window cancels a pending place; a press while the window is
open does not place. When the folder, the one task or the filter hide the shown run, **Go to the shown run** stands
beside the filter and shows it as a link does. `focusRun` now first asks whether the folder, the one task and the
filter show the run (`inView`, the row text moved above it). When they do, it only opens its Details and scrolls to it:
folder, filter, one task and ticks stay. When they hide it, `leaveView` keeps the view that was and sets every folder,
no filter and no ticks as before; **Back to <folder> · "<filter>"** (with "the runs of <task>" when one task was
shown) beside the filter restores that view, ticks cleared, and goes; it is hidden while the view is the one it names
and let go when the window closes. A folder deleted meanwhile restores All runs. The Tasks window's "Runs" count link
(one task's runs only) clears the view through `leaveView` too, so it offers Back as well. The window's hint says it
opens at the shown run. `frontend/src/panels/Folders.tsx`: `useFolders` has `name(id)` (the title uses it). `Folders`
takes `selected`, the number of ticked rows. With rows ticked, New folder opens no folder: the folder shown and the ticks
stay, the new folder is in Move to… at once, and the question reads "New folder name - the 4 ticked tasks stay ticked;
then choose the folder in Move to…". With none ticked it opens the new folder, empty, as before.
`frontend/src/panels/TableView.tsx`: `matches(text)`, the filter's test of one row. `TaskList.tsx` and
`ModelChooser.tsx` pass their tick counts. Nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso: Load run, New run like this and Continue... are pressed as before, a link still chooses nothing, and ticks
still clear whenever the folder or filter change, so a hidden row is never moved (7.250). `docs/workbench.md` (the run
window's opening, the links, the Tasks window's folders) and `docs/functionality-reference.md` (Task folders, Links
between the windows, Runs...) describe it. Skipped: the optional link on the shown run's name left of Runs... (the
press now opens at it).

**Checked.** `tsc` clean. `run_list_check` 151 (140 before). With the filter "budget" (DONE and RESUMED) and RESUMED
ticked, its "Started from" link opens DONE's Details with "budget" and the tick kept and no Back link. With "fine"
(RESUMED only) the same link shows all six runs, DONE's Details open, and "Back to All runs · "fine"", which brings the
filter back and goes. "paused" hides the shown run: "Go to the shown run" appears beside the filter, shows RESUMED with
its Details open and offers "Back to All runs · "paused"", choosing nothing; Back brings "paused" and the Go-to link
back. With forty newer runs listed, Runs... opens the window with DONE (the 41st of 46) in view and the window scrolled,
DONE marked, no Details open, All runs and no filter. `task_list_check` 100 (97 before): with four tasks ticked in
Unfiled, New folder "Later" keeps Unfiled shown and all four ticked, "Later" is in Move to…, and the question says the 4
ticked tasks stay ticked. Each new check looks for what the code before did not do: it cleared "budget" and the tick,
had no Back or Go-to link, opened at the top of the list, and opened "Later". Also run, unchanged: `model_chooser_check` 98,
`dom_identity_check` 56, `training_tab_check` 103, `task_run_check` 39, `looks_check` 75, `network_panel_check` 72 (8
scripts, one lane, all passed the first time). Not run: `run_control_check` (it presses Start against its fixture). No
flakes.

**Review follow-up.** The review of 2b61257 found two slips, both real. First, the Runs window never passed its tick
count to `Folders` (the plan's J6-8 named TaskList, RunList and SavedModels; only TaskList and ModelChooser were changed),
so there New folder with runs ticked still opened the new, empty folder and let the ticks go, while this entry and the
Task folders row of `docs/functionality-reference.md` said all three windows kept them. `RunList.tsx` now passes
`selected={selected.length}`. Second, a lost condition from 7.250. The Tasks window's newest-run link sends a run and its
task. `focusRun` kept the ticks when the run was in view, and the `OPEN_RUNS` handler then narrowed the view to that
task. With the window open on every run, its list read under a minute before, runs of two other tasks ticked: the link
hid them, "3 shown · 2 selected" stood, and Move to… moved the hidden runs. `focusRun` now takes the link's task
(`ofTask`): when it narrows the view (another task than the one shown, or none shown), the ticks go, as a folder or
filter change lets them go; the folder and the filter still stay when they show the run. The handler passes
`at.task_key` instead of setting the task after. Nothing here starts, continues or stops a run, saves a task or writes
to Virtuoso; a link still chooses nothing. `docs/workbench.md` (the links, the Runs window's folders) and the Links row
of `docs/functionality-reference.md` say so. `tsc` clean. `run_list_check` 157 (151 before): with DONE and LOST (a run
of no task) ticked among every run and the list just read, the newest-run link for DONE's task shows its three runs,
DONE's Details open, "3 shown" and Move to… greyed out; New folder "Later" with DONE and PAUSED ticked keeps All runs
and both ticks, "Later" is in Move to…, and the question reads "New folder name - the 2 ticked runs stay ticked; then
choose the folder in Move to…". Against the code before, both fail ("3 shown · 2 selected"; the new folder opened,
empty). Also run, unchanged: `task_list_check` 100, `model_chooser_check` 98, `dom_identity_check` 56,
`training_tab_check` 103, `task_run_check` 39, `looks_check` 75 (7 scripts, one lane, all passed the first time). Not
run: `run_control_check` (it presses Start against its fixture). No flakes.

### SIF-102 The RL model window keeps its view between opens, and a renamed model is renamed everywhere (2026-10-22; from the usability audit)

**Found.** The RL model window closes after every choice (record 7.291), and the saved models table is drawn inside it,
so everything it showed went with it. Each reopen started again at every folder, All designs, no filter, Last saved and
no Details. It also showed "Reading the saved models..." with no row (Refresh list greyed out) until the whole list was
read again from D:. Comparing models meant typing the filter again and waiting at every open (J5-3). The Runs and Tasks
windows keep their view at their buttons. Renaming a model in its Details read only the saved models again. The page's
run list, which is not polled, kept the old `model_label`. The main page's model line ("Fine-tune <old name> · save
point ..."), the header's Next line, and Started from / Models trained from it all kept the old name, beside "Renamed
to ..." (J5-12).

**Changed.** `frontend/src/panels/ModelChooser.tsx`: `useSavedModelsView` holds the table's view: the filter, sort and
ticks (`useTableView`), the folders (`useFolders('models')`), the Design, the model whose Details are open, and the
last list read with its output folder. `useRlModel` calls it, so it stays mounted while the window is closed, as the
Runs and Tasks windows keep theirs at their buttons. `SavedModels` takes it as `view` in place of its own state, so one
table in one window has one view: a reopen, or another Mode, shows the same folder, Design, filter, sort and open
Details. Until the window's own read answers, it shows the rows of the last read under the same output folder. That
read still goes once per open, and in New model still only once the fold is opened. The read now carries the output
folder it was made for, so a kept list is never shown under another folder; after a failed read no kept list is shown.
At each open the folders are read again and the ticks go, as in the Runs and Tasks windows. Details kept open for a
model that has left the list close (they would have opened again by themselves). A kept Design is judged only once a
list is shown. The model in use is brought into the box's view (SIF-86) when the window's own read answers, unless the
box was scrolled meanwhile. A rename now calls the page's `refreshRuns` (App.tsx -> `RunPanel` in `Right.tsx` ->
`useRlModel` -> `RlModelWindow` -> `SavedModels`). If the run list now carries the new name, its change reads the saved
models again by itself (`runsKey`). Otherwise (an older server's run list) they are read once here. `ModelDetails`
passes the new name to `onRenamed`. `refreshRuns` is stable, so `RunPanel`'s memo holds. Nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso. Use this save point, the double click and Use the newer
one choose as before and still close the window. `docs/workbench.md` (choosing which saved model to load, the label's
Rename, when the list is read) and the Saved models row of `docs/functionality-reference.md` describe it.
`frontend/scripts/model_chooser_check.mjs`: its `/api/runs` fixture counts its reads. Once `runsFollow` is set, it
carries the names the renames gave, as the backend's does (`model_label.json`). `reopen` and the read counts wait for
the window's own read, not for the rows, which now show before it.

**Checked.** `tsc` clean. `model_chooser_check` 107 (98 before). In Fine-tune, the Details of A opened in New model's
look are still open, with one read. Renaming D with the static run list reads the run list and the saved models once.
Renaming C, the model in use, with a run list that follows: the model line reads "Fine-tune FIXTURE in use renamed ·
save point 10 evaluations", the Next line "Fine-tune from FIXTURE in use renamed @ 10". The saved models are read once,
by the run list that changed, and renaming it back restores both. The folder GT models, Graph Transformer, "opamp",
sorted by Evaluations, A's Details open and A ticked: after close and reopen, with the read held, all of it is kept
except the tick. A's row shows at once under "Reading the saved models...", with one read asked. After it answers the
view stays, with no second read. C's Details, open while C left the list, are closed when C is listed again. Each new
check looks for what the code before did not do. Also run, unchanged: `network_panel_check` 72, `typing_check` 50,
`graph_view_check` 69, `encoder_models_check` 24, `model_structure_check` 31, `mode_suggestion_check` 20 (7 scripts,
one lane, all passed the first time). No flakes.

**Review follow-up.** The review of d099dfd found one slip, real. A rename could leave the saved models not read again
at all, although the comment said "once either way". The page's run list may already hold the new name: the run was
renamed in another tab, or by a direct `POST /api/runs/model/rename`, and seen here only by the window's read, then renamed
back here. The run list read after the rename is then the same as the one held, so `useRunList` keeps that array and
`runsKey` does not change. The new name is in it, so `renamed` did not read either. The row kept the other name beside
"Renamed to ..." and Rename stayed on. The predicate was the wrong question: the list carrying the new name does not
mean `runsKey` changes. `renamed` now compares the key of the list it got (`runsKeyOf`, which `runsKey` now uses too) with
the key last drawn (`shownKey`, a ref). An equal key means nothing will read the saved models, so it reads them. A
different key means the run list's change will. This is exact also where the reviewer's "had the name before" test would
read twice: another run of the list changed meanwhile. It is read from a ref, not the closure of the press, so a run list
read between the press and the answer does not mislead it. `onRenamed` no longer needs the run or the name. Nothing here
starts, continues or stops a run, saves a task or writes to Virtuoso; Rename, Use and their questions are as before.
`tsc` clean. `model_chooser_check` 108 (107 before): C renamed elsewhere and shown by Refresh list only, then renamed back
here, reads the run list and the saved models once, and the row carries its name again. Against the code before, it
fails with "0 read(s), the run list 1". Also run, unchanged: `encoder_models_check` 24, `graph_view_check` 69,
`model_structure_check` 31 (4 scripts, one lane, all passed the first time). No flakes.

### SIF-103 Fine-tune's switches and the saved model's whole reward are in view before Start (2026-10-22; from the usability audit)

**Found.** Fine-tune's own switches - Freeze encoder, Encoder-only transfer, Reset critic, Continual learning - were said
only in the RL model window's last block, under the saved models table, and that window closes once a save point is
chosen (record 7.291). The model line, the header's Next line and their tooltip never named them, nor the name typed for
the model the run saves; Evaluate only's actions were named. They are kept across Modes and runs, and New run like this
copies them, so a switch left on from an earlier experiment was unseen before Start; checking one tick box meant reopening
the window and scrolling to its bottom (J5-7). In Fine-tune a reward that differs from the saved model's resets its
critics, targets and replay, and the compatibility line says only "Different reward/condition contract". The model's facts
were the one place to compare, and showed four of the reward's six fields: no objective shape, no nominal gate band. So the
model's reward could not be matched even by hand, and matching it meant typing it field by field into the main page's
Reward and conditions > Advanced (J5-14).

**Changed.** `frontend/src/panels/rlModelText.ts`: `FINE_TUNE_SWITCHES` lists the four in the window's order, with the
window's label and a short word. `modelLineText` and `nextModelText` take `adv` and add the switches that are on, in
Fine-tune only (the backend reads them in no other Mode): "Fine-tune ota7t (2) · save point 420 evaluations · encoder
frozen · critics reset", "Fine-tune from ota7t (2) @ 420 · encoder frozen · critics reset". The others are "encoders only"
and "continual". With all off both lines are as before. `networkTitle`, the line's tooltip, adds them by the window's
labels ("Fine-tune's switches on: Freeze encoder, Reset critic.") and, when a name is typed, "It saves the model as ...,
with a number if that name is taken." The line is clamped to two lines, so the long form is there. `REWARD_DEFAULTS`
holds the six reward fields with the backend's `RewardConfig` defaults; `REWARD_NAMES` and `REWARD_HELP` gain the objective
shape and the gate band. `frontend/src/panels/RlModelWindow.tsx`: the facts of the model in use add **Objective shape**
("Clipped" / "Compressed", the reward block's option names) and **Nominal gate band**, with the reward block's tooltips. In
Fine-tune, while the next run's reward differs from the model's in any of the six fields, the Reward row offers **Use this
model's reward**. Its tooltip names each field that differs ("nominal gate band 0.4 instead of 0.5") and says that the
training conditions, which Fine-tune also compares, are not changed. A press sets the six as one Undo step and the offer
goes. `frontend/src/panels/useRlModel.ts` threads `adv` into the three texts and holds `savedReward` (a field a contract
leaves out as the run takes it), `rewardApart` and `useModelReward`, which takes only the six keys by the reward block's
own field names (`pick`); `reward` now starts from `REWARD_DEFAULTS`, the same five defaults plus the gate band.
`frontend/src/panels/RewardConditions.tsx`: Objective shape gets the tooltip it lacked, and the gate band's is the shared
one, unchanged. `frontend/src/contracts.ts`: a saved model's `reward_settings` type has the two fields. Nothing here
starts, continues or stops a run, saves a task or writes to Virtuoso; the link changes only the configuration's reward,
and Undo takes it back. `docs/workbench.md` (the model line, the Next line, the model in use's reward) and the Mode and
Reward and conditions rows of `docs/functionality-reference.md` describe it.
`frontend/scripts/model_chooser_check.mjs`: B's save point now holds a reward that differs from the page's in all six
fields.

**Checked.** `tsc` clean. `model_chooser_check` 116 (108 before). With A in use, Freeze encoder, Reset critic and
Continual learning ticked and "FIXTURE tuned" typed, the model line reads "Fine-tune FIXTURE_opamp_gt · save point 6
evaluations · encoder frozen · critics reset · continual" and the Next line "... @ 6 · encoder frozen · critics reset ·
continual · GT 16/2/1 · N evaluations". The tooltip ends "Fine-tune's switches on: Freeze encoder, Reset critic, Continual
learning. It saves the model as FIXTURE tuned, with a number if that name is taken." Evaluate only says "deterministic
actions" and none of them. With all off and the name cleared, both lines and the tooltip read as before. B's facts show
Objective shape "Compressed" and Nominal gate band "0.4", the shape's tooltip equal to the reward block's. "Use this model's
reward" is on the Reward row, its tooltip naming the fields that differ. A press stores all six of B's values and the
offer goes; one Undo brings the page's reward back and the offer with it. Each new check looks for what the code before
did not do. Also run, unchanged: `looks_check` 75, `network_panel_check` 72, `reward_block_check` 33,
`mode_suggestion_check` 20, `encoder_models_check` 24, `room_check` 30, `graph_view_check` 69, `model_structure_check`
31, `network_inputs_check` 9 (10 scripts, one lane, all passed the first time). No flakes.

**Review follow-up.** The review of 9d820b9 found two slips, both real. First, the switches were said at the end of two
lines that are cut at two lines, so in real use they were hidden. A saved model's name and save point fill the model line
(about 200 px wide; "Fine-tune mscr_vco_lin_c (6) · / save point 800 evaluations" at 1366 px), and the task's and the
model's names fill the header's Next line (200 px at most). In this check's own fixture at 1,680 px, with three switches
on, the model line needed 53 px and showed 35, the Next line 81 and 33; the check read `textContent`, so it passed. The
switches that are on now have a line of their own under the model line, never cut, by the window's labels: "Switches on:
Freeze encoder, Reset critic, Continual learning." (`switchesText` in `rlModelText.ts`; a `p.hint.model-switches` in
`RunConfiguration.tsx`, whose tooltip says where they are ticked; 6 px under the model line in `styles.css`). The model
line reads as before SIF-103, so its save point keeps its room; its tooltip no longer lists them and still names the model
the run saves. The Next line keeps its words: Start's tooltip begins with it and says them whole, and the docs no longer
say the header line shows them. Second, "the backend reads them in no other Mode" was wrong for Continual learning:
`runs.py` `_source_model` reads `run.continual_learning` in Evaluate only too, where it decides whether a source that was
itself fine-tuned on a test task loads or is refused (code `continual_learning`). Evaluate only had no box for it, and
SIF-103 left it out there on that claim, so one left on from a Fine-tune went unseen before Start, and could not be ticked
in that Mode when the refusal asks for it. `switchesOn` now takes Continual learning in Evaluate only: the line says it,
and the Next line adds "· continual". `RlModelWindow.tsx` shows the box in Evaluate only's own settings too, after
Actions, with a tooltip in both Modes (off: such a source is refused; on: it is loaded, as continual learning). The
comment, the docs and the check's label are corrected. Fine-tune's other three stay its own: in another Mode they refuse
the start with a blocking issue that names them (`validation.py` `fine_tune_only_option`). Nothing here starts, continues
or stops a run, saves a task or writes to Virtuoso; the box changes only the configuration, and Undo takes it back.
`docs/workbench.md` (the Next line, the model line, the Modes' own settings) and the Mode row of
`docs/functionality-reference.md` say so. `tsc` clean. `model_chooser_check` 119 (116 before). With three switches on in
Fine-tune, the line under the model line reads them in full and in view (38 px of 38), and the model line is whole (35 px
of 35); the Next line and Start's tooltip name them. In Evaluate only the line reads "Switches on: Continual learning.",
and the Next line adds "· continual"; the box is there, ticked, after Actions, without the other three; unticked there,
the line and the word go. Against the code before, there is no such line and Evaluate only says nothing. New picture:
`models-1b-switches.png`. Also run, unchanged: `dom_identity_check` 56, `task_rows_check` 54, `typing_check` 50,
`task_list_check` 100, `looks_check` 75, `network_panel_check` 72, `reliability_check` 20, `room_check` 30,
`graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 33, `pdk_check` 40, `encoder_models_check` 24,
`model_structure_check` 31, `mode_suggestion_check` 20, `network_inputs_check` 9 (17 scripts with `model_chooser_check`,
832 checks, one lane, all passed the first time). No flakes.

### Merged into workbench and live (2026-10-22; the user: "merge it into workbench and make it live")

**Merge.** workbench (48 commits by other sessions since 8b67d97: frontend speed-ups and checks of 7.377/7.379, backend,
docs, thesis) was merged into this branch in its own worktree: 16 files conflicted (41 hunks), each resolved keeping both
sides (their features and checks, our wording, names, layout and check expectations); the backend and tests are byte-identical
to workbench's. docs/frontend_implementation_status.md keeps workbench's version for now: another session has unsaved edits
in it, and this log's pointer row waits. Merge commit fcc80ed; circuit_layout_check and editor_renames_check (theirs) refused
the runner's evidence-folder argument - fixed in 8aa7213. On the merged tree: `tsc` clean; vite build; full browser suite at
one lane - 58 scripts, 2,680 checks passed; an adversarial review of the resolution found nothing lost. workbench was then
fast-forwarded to 8aa7213 in the shared tree (none of the 116 files it changed had anyone's unsaved edits; theirs stayed as
they were). workbench is not pushed (166 commits ahead of origin, most of them other sessions').

**Live.** Page: the merged build (index-Pf1CbBhz.js, index-CeHnC5t3.css) copied into frontend/dist/assets beside the old
assets, index.html last. Server: workbench holds other sessions' backend changes since 2026-10-19, so 8765 was restarted
with the previous server's 13 environment variables (no CLAUDE/ANTHROPIC/CODEX) - pid 3263967 since 16:45:47.
A slip: after the first restart (16:28) Windows could not reach 8765 until 16:46 - WSL's localhost relay (wslrelay.exe) held
stale connections from this branch's own preview server on 5174 (its /api proxy kept sockets to the old server), so new
connections from Windows hung while WSL's own curl answered. Stopping the preview cleared it; the restart recipe now says to
stop such a proxy first and to test from Windows after a restart.

**Checked live** (read-only headless Edge on 8765, writes refused): the page draws with the user's VCO task, no console
error, no refused write; Tasks window, Windows menu and the 1366 px strip as the 2026-10-19 live check expects; pictures in
artifacts/local/reviews/live-2026-10-22.

### SIF-104 A cell's size becomes a Parameters row with one press (2026-10-23; from the usability audit)

**Found.** After a cell was read from Virtuoso, every Parameters row had to be typed by hand (audit finding J1-2, the part
SIF-88 left out). A read fills Probes only. Add gave a blank row whose Instance and Parameter are free text, and the present
sizes a range must contain were only in the read-only "Instances and parameters" table, under Hierarchy in the Virtuoso
window: another window. Copying each instance path and parameter name across was the slowest step of turning a cell into a
task, and a mistyped one was found only by validation or Save as. SIF-88 gave the empty table a line, and left the button per
size out because its rows would start with bounds that hold no real size. This batch takes it with the bounds left empty for
the user, as the audit's refined fix says.

**Changed.** `frontend/src/panels/editorRules.ts`: `newRow(tab, config, schema)` holds the row Add makes: every field at its
schema default, a free ID in the tab's word, a Probe's way of measuring, a Spec's first equation and scale. It moved out of
`add` in `frontend/src/panels/Editors.tsx` with its comments, and Add uses it, so the two cannot differ. It takes the
configuration, not only the rows (the plan's `newRow(tab, rows, schema)`), because Add also reads the task and the Probes.
`frontend/src/panels/CircuitBrowser.tsx`: `CircuitDetails` takes `adding` (`SizeAdding`: the Parameters rows and the press).
With it, each size with a number in "Instances and parameters" has an icon button after it, labelled "Add to Parameters",
with the tooltip "Add to Parameters: A new row for XU1/M1 w at the end of Parameters. Type its Lower and Upper there, a range
that holds the present 4 um; the workbench's Undo takes it back." The icon adds no text, so the table still reads "w = 4 um".
A size that is a Parameters row already (same instance and parameter) has it off: "Add to Parameters: XU1/M1 w is already the
Parameters row parameter_1." A line under the table names the last row added while that row is there and the cell is shown:
"Added parameter_1 (XU1/M1 w = 4 um): type its Lower and Upper in Parameters, in the workbench." Undo, a rename or a Delete of
the row takes the line with it. A size that is no number (an expression) gets no button. Each size is a `span.size`;
`frontend/src/styles.css` keeps a size with its + on one line and the + small (11 px), and a size without one wraps as before.
`frontend/src/panels/Left.tsx` gives `adding` only to a Virtuoso draft that Save as can make a task of: not to a cell that
has a task already, nor to a task's Hierarchy in the circuit column. The press appends the row `newRow` makes with
`instance_path`, `parameter_name`, `initial_value` (the present value) and `unit` (the parameter kind's: m for w and l), as
one Undo step. Lower and Upper stay empty, so validation marks the row ("An optimized independent variable needs both
bounds") until they are typed. Save as still accepts only rows a real run can write, with a range that holds the present
value. `frontend/src/App.tsx` passes the schema to the circuit panel (an optional prop: the edit_state fixture renders the
panel without one, and then no size has the button). The draft's next-step line (`frontend/src/panels/VirtuosoWindow.tsx`)
now says "the + after a size under Hierarchy, Instances and parameters (at the end of this window) adds it to Parameters".
The empty Parameters line in the editors ends "...in the Virtuoso window: the + after a size adds it as a row." Nothing here
starts, continues or stops a run, saves a task or writes to Virtuoso: the press changes only the configuration, and the
workbench's Undo takes it back. `docs/workbench.md` (Read this cell into the workbench) and `docs/functionality-reference.md`
(the Hierarchy block, Read this cell, the toolbar's Add) describe it. `frontend/scripts/project_help_check.mjs`: the empty
line's new words, and the window's test that "Instances and parameters" is folded now reads its summary line, because the
next step names it in view.

**Checked.** `tsc` clean. `project_help_check` 58 (50 before). A task's 97 sizes in the circuit column have no button. The
draft's next step names the +, and the empty Parameters line ends with it. The size "w = 4 um" has the button: labelled
"Add to Parameters", no text of its own, the tooltip above, the cell's text unchanged. A press gives Parameters (1) with
parameter_1, XU1/M1, w, Lower and Upper empty, and the empty line goes. It is stored with initial_value 4e-6, unit m, no
bounds or step, optimized, continuous, untied, ratio 1. The window names the row, the button is off with the row's name, and
the row is marked `missing_bounds`. One Undo in the workbench takes the row back and says "Undo: Parameters parameter_1
removed."; the button is on again and the line has gone. Each new check looks for what the code before did not do. Its first
run failed one old test: the next step's words meet the window's old "folded" text test in view. That test reads the summary
line now. New picture: `help-4c-draft-size-added.png`. Also run, unchanged: `virtuoso_source_check` 108,
`testbench_probes_check` 41, `find_fill_copy_check` 50, `typing_check` 50 (Add's free IDs), `spec_equations_check` 36,
`working_copy_check` 34, `reliability_check` 20, `circuit_source_check` 17, `editor_columns_check` 23 (Add's Probe and
Spec), `edit_state_check` 28 (11 scripts, 465 checks, one lane, all passed). No flakes.

**Review follow-up.** The review of 3a5289e found two slips, both real. First, the press stored the present size as the
row's `initial_value`, which no row made in the page had carried: Add leaves it empty, meaning the value the circuit has,
and Save task empties it. Nobody can see or type it (a hidden column, `schema.py` HIDDEN_COLUMNS), yet validation compares
a stated one with the circuit (`initial_differs_from_circuit`); `withFollowers` changes only a row's unit when its
Parameter changes, and a read leaves Parameters alone. So after the + on XU1/M1 w (4 um) and a valid Lower and Upper,
typing the Parameter again (l), or Read the cell again after w was changed in Virtuoso, marked the row "Configuration says
4 um but the circuit has 180 nm" (or 5 um), with "as no column shows its Initial value" in the Issues list. Typed bounds
could not clear it and the size's + stayed off: only Delete and a new press helped, so "validation marks the row until they
are typed" was untrue after those steps. The press (`adding` in `frontend/src/panels/Left.tsx`) now gives the row Add makes
with the instance, the parameter and the parameter's unit, and no initial value; the present size stays in the +'s tooltip
and the line under the table, for the range. `withFollowers` is left as it is. With nothing stated, a new Parameter or a
new read finds nothing stale. Clearing a stated value when the Parameter changes would touch the rows that do carry one (a
built-in task's own rows): typing the old name back would then leave a hidden difference from the saved rows, which
`sameRows` counts (the phantom edits of record 7.223), while such a row now heals when its name comes back. A range that
leaves out the present size is now refused by Save as alone, as for every row typed by hand (the stated value had also
marked it in the editors, `initial_out_of_bounds`). Second, the empty Parameters line ended "the + after a size adds it as
a row" on every page that follows a Virtuoso cell. But a cell that has a task already gets no +, and the window still shows
its Hierarchy once an earlier read of it loads (the load names the task). `sizesAddable` in
`frontend/src/panels/CircuitBrowser.tsx` (a Virtuoso cell with no task yet) now decides both: the circuit panel gives the
press by it, and `App.tsx` hands it to the editors as `addsSizes`, so the line names the + only where there is one.
Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso; the press still changes only the
configuration, as one Undo step. `docs/workbench.md` (Read this cell into the workbench) and the Hierarchy and Read rows
of `docs/functionality-reference.md` say so. `tsc` clean. `project_help_check` 61 (58 before): the stored row has
initial_value null, unit m. A new fixture cell, ring_c, was read before and has a task: the window shows its size under
the note that names the task, without a button, and the empty Parameters line ends "...in the Virtuoso window." Back on
ring_a the + is on and the line names it again. On the code before, the stored row had 4e-6 and the line named the + on
ring_c too. Also run, unchanged: `virtuoso_source_check` 108, `testbench_probes_check` 41, `find_fill_copy_check` 50,
`typing_check` 50, `working_copy_check` 34, `spec_equations_check` 36, `reliability_check` 20, `circuit_source_check`
17, `editor_columns_check` 23, `edit_state_check` 28, `editor_renames_check` 8 (12 scripts, 476 checks, one lane, all
passed the first time). No flakes.

### SIF-105 The bottom panel keeps its tab and choices, Calibration ready shows its table, and Compare lists the task's runs first (2026-10-23; from the usability audit)

**Found.** Four audit findings. Data tables and Logs are drawn only while their tab is chosen, and their choices lived
inside them (J4-8, J7-7): a glance at Run status put Data tables back on the newest 25 evaluations, whatever table, row
count and order had been chosen (the last two since SIF-99), and Logs back on events. The bottom tab itself went back to
Run status at every reload, although the panel's height and fold, the module folds, the circuit column, the shown run
and the Training tab's charts were all kept. The "Calibration ready" line said "The table is under Run status" and
offered no way there (J3-11): once the calibration had ended the tab line's "Show the header's run" was gone, so with
the tabs on another run the table was the run chip, Running now and Show results away, or the Runs window, and a folded
panel stayed folded. Training's Compare... was one native list of every run under the output folder, newest first: 612
with the user's data, the task's other seeds and Modes scattered among them (J4-12).

**Changed.** `frontend/src/panels/RunTabs.tsx`: `DataChoice`, the table, the row count and the order (`DATA_CHOICE`:
evaluations, 25, newest first, the old defaults); `DataTab` takes `choice` and `setChoice`, `LogsTab` `kind` and
`setKind`, in place of their own state. `frontend/src/panels/BottomPanel.tsx` holds both (`dataChoice`, `logKind`): the
panel stays mounted, so a choice lasts while the page is open, whichever run is shown, as the table did while its tab
stayed open. The plan named the table alone; the row count and the order are choices of the same kind that reset the
same way, so they are held with it. LogsTab stays memoised (its setter never changes). `useBottomTab` there keeps the
tab in this browser tab (`sessionStorage`, `BOTTOM_TAB_KEY` = `gator-workbench-bottom-tab-v1` in
`frontend/src/contract.ts`): a reload comes back on it, and a page opened anew starts on Run status, as before. Corner
check is not brought back: whether corners can be used is known only after the page opens, and `page/shownRun.ts` turns
that tab to Run status at once. `frontend/src/App.tsx` takes the tab from it. The Calibration ready line with proposals
has **Show table** after its words while the table is out of view: the tabs on another run, on another tab, or the panel
folded. The press does what the run brief's Show results does - the header's calibration run in the tabs, Run status,
the panel open - and nothing else; its tooltip: "Show table: Shows this calibration run under Run status, with its table
of proposals and its Apply buttons. Nothing is applied." The plan's condition had the run and the fold only; with the
tab kept now, Logs over the table is a likely case, so another tab counts too. With the table in view the line's buttons
are as before (`calibration_save_check` pins them exactly). The line that proposes nothing keeps its OK alone.
`frontend/src/panels/TrainingTab.tsx`: the Compare list groups the runs by the run list's `task_key`: "Same task
(<task>)" first, then "Other tasks", each newest first, an empty group left out; a shown run with no key in the list (an
older backend, a run not listed) keeps the one list. Its tooltip ends "the shown run's task first".
`frontend/scripts/fixtures/request_lifecycle.tsx` holds the table and the log above the tabs, as the panel does. Nothing
here starts, continues or stops a run, saves a task or writes to Virtuoso: the choices, the tab and Show table change
only what the bottom panel shows. `docs/workbench.md` (the bottom panel, Several runs on one chart, the Calibration
ready paragraph) and `docs/functionality-reference.md` (the Splitter, Logs, Data tables, Training and Calibration ready
rows) describe it. Skipped: the audit's two optional parts, a link from the tab line to an ended header run (J3-11; Show
table covers the calibration line) and "Compare in Training" in the Runs window (J4-12: the mounted Training tab reads
its compared runs once, so it needs an event of its own; the verdict leaves it for later).

**Checked.** `tsc` clean. `calibration_check` 45 (38 before; real MOCK runs on the check's scratch backend): with the
table in view the line has no Show table; on Logs it has, with its tooltip; the press shows Run status with the table
and the button goes; with the panel folded it is offered and the press opens the panel; with the tabs on the first
calibration run (kept as the shown run, after a reload) it is offered, and the press shows the second run's table, its
Apply on. New picture: `calibration-0c-show-table.png`. `export_check` 37 (35; a real MOCK run): back in Logs the errors
log is still shown, back in Data tables its parameters table, 25 rows, oldest first ("60 rows; the oldest 25 shown,
oldest first."). `training_tab_check` 106 (103): a page opened anew shows Run status, a reload comes back on Training
without a press, and Compare lists "Same task (fixture_task)" with the task's five other runs, then "Other tasks" with a
listed run of another task (the fixture's rows carry a `task_key` now). `room_check` 31 (30): a reload with no run folds
the panel on the tab it showed, Logs. Each new check tests what the code before did not do: no Show table, no groups, a
tab and choices that reset. Also run, unchanged: `calibration_save_check` 22 (the line's buttons exactly as before),
`run_control_check` 160, `dom_identity_check` 56, `files_tab_check` 42, `corner_check_check` 39, `looks_check` 75,
`reliability_check` 20, `matched_devices_check` 37, `request_lifecycle_check` 25 (13 scripts, 695 checks, one lane, all
passed the first time). No flakes.

**Review follow-up.** The review of 08e822d found one slip, real: the Compare select's tooltip always ended "the shown
run's task first", but a shown run the run list names no task for keeps the one list, with nothing put first - a run the
list does not hold (outside the listed output folder, or before the list is read) or a row without a `task_key`
(`run_index.py` takes it from the manifest's `circuit.task_key`). `frontend/src/panels/TrainingTab.tsx` now adds the
clause only with the groups (`task`); over the one list the tooltip ends "(the list of the run window, Runs...)." `tsc`
clean. `training_tab_check` 108 (106 before): over the groups the tooltip says the task comes first, and a shown run the
list does not hold (the calibration run, with the list read) gets the one list, no groups and a tooltip without the
clause - the code before failed that. Also run, unchanged: `dom_identity_check` 56 (2 scripts, 164 checks, one lane, all
passed the first time). The review's other points were found sound (Show table only shows the run, the lifted choices,
the kept tab): nothing to change. Nothing here starts a run, saves a task or writes to Virtuoso.

### SIF-106 A renamed Probe takes its Specs along, and a Probe chip puts its ID into the Equation (2026-10-23; from the usability audit)

**Found.** Two audit findings on the Specs' equations. A Maestro output's Probe ID follows its Output name, and the spec
equations using it follow too (records 7.172, 7.184). But a Probe ID typed in its own cell - an ngspice or MOCK task's
Probe, any Probe its backend measures - left every Spec on the old ID (J2-11). Each one broke with
`equation_unknown_probe` on the Specs tab, which is not in view. The audit's first fix, a rename in `withFollowers`, was
unsafe: a cell writes each key, so an emptied box would have lost the chain, and a step through another Probe's ID would
have taken that Probe's Specs too. The Probe IDs were also listed as chips just above the Specs table, but as plain text
(J2-14). Each one (m_supply_power_w, m_f1_hz ...) was typed into an Equation by hand, and a slip showed as an unknown
probe only after validation.

**Changed.** `frontend/src/panels/editorRules.ts`: `probeRename(c, index, from, to)` says whether the Specs naming the old
ID follow a new one, and if not, why. They follow only between plain names (letters, digits and _, a letter or _ first),
as a renamed output's do: the backend reads an ID with "." or "-" only as a whole equation. They do not follow to an ID
another Probe holds, nor from one another Probe still holds (a duplicate). `renameProbe(c, from, to)` rewrites the
equations with the renamer of record 7.377 (`equationRenamer`, unchanged; `editor_renames_check` pins its text).
`frontend/src/panels/Editors.tsx`: a Probes ID cell that takes typing (not a Maestro output's, which follows its Output
name) remembers the ID it held when it was entered. When it is left with another ID, the Specs naming the old one follow
(`followProbeId`); never per key. They join the ID's own Undo step through `setConfig(..., false)` (history.ts: a change
with no step of its own), so one Undo takes them back with the typed ID. The plan's fallback note ("Undo once takes back
the Specs, twice the ID too") was not needed. An ID written in the formula bar is written with its Specs in one step
(`commitBar`). The line under the formula bar names them, with Show Specs: "2 Specs (score, score_sq) now use m_total, the
Probe's new ID. Undo takes them back with the ID." Where they cannot follow - an emptied ID, one with "." or "-", another
Probe's - it says so in amber: "2 Specs (score, score_sq) still use m_score: "m-total" is not letters, digits and _ alone,
with a letter or _ first. Another ID typed there takes them along; Undo takes this one back." The next ID typed in that
row does take them along from the old one (`refusedId`); the plan had no such note, and without it a second try left the
Specs broken without a word. A block pasted over Probe IDs leaves the Specs as before: following the one row the paste
started in would have been a partial rename. The Specs line's chips are buttons now: each `code.probe-id` sits in a
`button.chip-insert` whose mousedown leaves the focus where it is. With an Equation cell chosen, a press puts the ID at
the cursor of the cell or of the formula bar, in place of the text chosen there, with a space where it would touch the
text beside it. The cell or the bar keeps the focus, with the cursor after the ID. With the focus elsewhere the ID goes at
the end of the chosen Equation. It is written through `commitBar`, one Undo step; in the bar, the bar's own text takes it
too, so Enter writes nothing more. With no Equation cell chosen, a press copies the ID: "Copied m_total. With an Equation
cell chosen, a press puts the ID in at the cursor." Each chip's tooltip says which press it is, and the line's tooltip
says it too. `frontend/src/roadster.css`: `.chip-insert` drops a button's frame, fill and padding and takes the line's
font, so the line reads and measures as before; a hover rings the chip in the Probe colour. Nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso: both change the configuration only (or copy an ID), and
Undo takes them back. `docs/workbench.md` (a new bullet under Tied rows, spreadsheet keys and a pasted block; the formula
bar; each editor's colour) and `docs/functionality-reference.md` (a new row, A Probe renamed, the Probe chips; the tabs'
and the formula bar's rows) describe it.

**Checked.** `tsc` clean. `spec_equations_check` 54 (36 before), on the MOCK task's m_score and the two Specs using it.
While m_total is typed key by key the equations keep m_score. Leaving the cell gives m_total and m_total ** 2, with the
line above and Show Specs, and one Undo takes back the ID and both Specs. "m-total" leaves them on m_score with the amber
line; its Show Specs opens Specs, where the backend reports `equation_unknown_probe`. m_total typed next takes them along
from m_score, and the backend reports nothing unknown. m_sum written in the formula bar takes them along; one Undo
takes both back. The chip is a button holding its code, and the line still reads "Probes: m_total". With no cell chosen
a press copies m_total (the copy is answered in the page) and says so. In the cell "m_total *" a press gives "m_total *
m_total": the cell keeps the focus, the cursor is after the ID, and one Undo leaves "m_total *". In the bar,
"( + m_total) / 2" with the cursor after "(" gives "(m_total + m_total) / 2", written with the bar keeping the focus;
Enter writes nothing more. New picture: `spec_probe_chips.png`. `looks_check` 76 (75): the chip is a button with no
border, padding or fill of its own, at the line's 14 px, the code still 13 px. Each new check looks for what the code
before did not do. Also run, unchanged: `task_rows_check` 54, `formula_bar_check` 21, `testbench_probes_check` 41,
`ngspice_window_check` 43, `typing_check` 50, `find_fill_copy_check` 50, `sheet_check` 54, `editor_columns_check` 23,
`unsaved_rows_check` 25, `blocking_issues_check` 60, `edit_state_check` 28, `working_copy_check` 34,
`editor_renames_check` 8, `reliability_check` 20, `project_help_check` 61, `dom_identity_check` 56,
`matched_devices_check` 37 (19 scripts, 795 checks, one lane, all passed). The new section's first runs failed on the
check itself: a name declared twice, then the backend refusing the whole configuration (422, "No task trains at corners")
once the check's last part plans training corners for the MOCK task, so no row issue could show. The section now runs
before that part. No flakes.

**Review follow-up.** The review of fa054e6 found four slips, all real. First, Enter in the formula bar wrote a Probe ID and
went back to its cell inside the same key press, before React drew the write (react-dom 18 runs the nested focus event
inside the key press's batch, without a render), so the cell was entered with its row as it was before: it held the ID the
bar had replaced. A slip written in the bar (m_totl, the Specs taken along) and fixed in that cell (m_total, Tab) then took
no Spec along and said nothing: the Specs stayed on m_totl, broken on the Specs tab, under the line "now use m_totl", and
typing the old ID back counted as nothing typed. `backToCell` in `frontend/src/panels/Editors.tsx` now lets React draw the
write first (`flushSync`), then focuses the cell. Second, Ctrl+Z or Ctrl+Y pressed in a Probe's ID cell counted as typing:
the cell keeps the focus, and leaving it took the Specs naming the ID from before the step along to the ID the step brought
back. With a Spec typed on an ID no Probe held yet (m_gain), the Probe renamed to it and Ctrl+Z pressed in its cell, leaving
rewrote that Spec to the old ID, with no Undo step of its own, over the state the Undo had brought back. The toolbar's
Undo, whose press leaves the cell first, did not. A new effect on `lastStep` makes the cell hold the ID an Undo or Redo
brings back, as if entered anew. Alone, that would leave an ID typed, undone and redone in the cell without its Specs: the
Redo brings the typing back as it was before the cell was left. So `onTableKey` first lets a typed ID take its Specs along,
as leaving the cell does: Ctrl+Z in the cell now does what the toolbar's Undo does, and Ctrl+Y brings the ID back with its
Specs. Third, a chip pressed into the Equation cell put the ID in with `setRangeText`, which React's change tracking does
not see. A key that brought the cell back to its text from before the press (the ID chosen and deleted, or deleted as a
word) changed nothing: the cell showed that text while the configuration, the formula bar and validation kept the ID,
which came back at the next drawing. `pressProbe` now sets the cell's text through its `value`, which React tracks, with
the cursor after the ID as before; the formula bar's path, an input event, was right. Fourth, a refused rename's memory
(`refusedId`) was kept by the row's place alone: once a row above it was deleted, the next ID typed in the row found no
memory and took no Spec along, again unsaid. `remove` now moves the memory up with its row past the rows deleted above it,
and drops it with the row; an Undo or Redo finds the row by the row itself in the rows the step brought back. Left as it
is, not raised: a Spec that followed a typed ID drops the memory, so an Undo back to the refused ID has none, and the next
ID typed there takes nothing along; keeping memories through such steps is more than this follow-up. Nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso: the configuration only, in the same Undo steps.
`docs/workbench.md` (A Probe renamed) names Ctrl+Z in the cell and a moved row. `tsc` clean. `spec_equations_check` 63
(54 before). m_totl written in the bar, Enter, then m_total typed in the cell it went back to and the cell left: both Specs
follow. A chip pressed into an emptied Equation cell, the ID then chosen and deleted: the cell and the Spec are empty alike.
m_total typed m_gain (score_sq named m_gain first), then Ctrl+Z in the cell and the cell left: m_total with score on it,
score_sq still on m_gain, the line the Undo's. m_x typed, then Ctrl+Z and Ctrl+Y in the cell and the cell left: m_x with
score on it. A second Probe's m_gain refused as m-gain; with the Probe above deleted and the Delete undone, m.gain typed is
still said against m_gain; with that Probe deleted again, m_gain2 typed takes score_sq along. On the code before, the
first of these failed and the rest followed from it; with the bar fixed alone, the chip and Ctrl+Z checks failed (and what
followed); without the moved memory, the last one failed. Also run, unchanged: `looks_check` 76, `task_rows_check` 54,
`formula_bar_check` 21, `testbench_probes_check` 41, `ngspice_window_check` 43, `typing_check` 50,
`find_fill_copy_check` 50, `sheet_check` 54, `editor_columns_check` 23, `unsaved_rows_check` 25,
`blocking_issues_check` 60, `edit_state_check` 28, `working_copy_check` 34, `editor_renames_check` 8,
`reliability_check` 20, `project_help_check` 61, `dom_identity_check` 56, `matched_devices_check` 37, `room_check` 31,
`circuit_source_check` 17, `network_panel_check` 72 (22 scripts, 924 checks, one lane, all passed the first time). No
flakes.

### SIF-107 Import JSON says what it did, and the zero-floor hint sets Margin sides with one press (2026-10-23; from the usability audit)

**Found.** Two audit findings in the editors. After Import JSON...'s Apply the confirmation simply went, and the focus
with it: nothing said what had changed, even when a whole configuration had replaced the run and output settings out of
view, while Matched devices' Apply and the task file both say "Applied ... Undo takes it back" (J2-10). The confirmation
ignored Esc, and a failed import's red line stayed across tab presses until the next import: "every Specs row needs its
Spec ID" stood over the Probes table. The zero-floor hint of Specs names its rows and the fix, "set Margin sides to upper
(More columns)", but that column is behind More columns: the user showed it, scrolled right and changed each named row's
list by hand (J2-12).

**Changed.** `frontend/src/panels/Editors.tsx`. Apply writes the line under the formula bar, as Matched devices' Apply
does: "Imported: 20 changed rows. Undo takes it back."; a whole configuration adds the sections it replaced, in the
confirmation's words ("Imported: replaced the run settings. Undo takes it back."); a file that changed nothing says
"Imported: nothing changed.", where "Undo takes it back" would have pointed at an earlier change (the plan's text read "0
changed rows; replaced ..." there). Rows write their table alone, so their line names no other section; rows applied
after a tab press offer their table with Show Specs, as an Undo's line does (SIF-97). The box opens with Apply in focus,
so Enter applies and Esc cancels at once - but only where the file chooser left the focus, on Import JSON... or the page
(`applyButton`, an effect on `pending`). The plan's `autoFocus` would also have taken the focus from a cell entered while
the diff was on its way, and an Enter typed there would have pressed Apply. Esc in the box is Cancel, also after a click
on its words: the box takes that click's focus (`tabIndex` -1), which fell to the page. Apply, Cancel and Esc pressed in
the box give the focus back to Import JSON... (`closeImport`, `importButton`), where it fell to the page with the box; a
focus put elsewhere while the box was open stays there. Apply and Cancel have tooltips; Cancel's names Esc. A failed
import's line (`div.import-error`) has a close mark beside its words, and the tab reset clears it with the chosen cell
and the line under the formula bar. The zero-floor hint keeps its words; beside them, not inside (`div.zero-floor`, so
the paragraph's text that `editor_columns_check` and `reward_v21_check` pin stays whole), a button reads "Set Margin
sides to upper", or "... on all 2" for several rows. A press sets `margin_sides: 'upper'` on every row the hint names,
through `withFollowers` as one Undo step - the rows by the hint's own test, not by ID, so a duplicated ID cannot take a
row the hint did not name - and says "Margin sides set to upper on half_freq, spec_3. Undo takes it back."; the hint then
goes by itself. Its tooltip says what that does: only the upper limit counts in the tightest-margin bonus and the Corner
check ranking, while feasibility still checks both limits. Whether 0 is only a physical floor stays the user's call:
nothing sets it without the press. `frontend/src/roadster.css`: `.line-act` keeps a line's action beside its words, which
wrap in their own width; `button.line-close` is drawn as the launch refusal's close mark. Nothing here starts, continues
or stops a run, saves a task or writes to Virtuoso: an import still changes nothing before Apply, and each change is one
Undo step. `docs/workbench.md` (a new bullet under Tied rows, spreadsheet keys and a pasted block; the Margin sides
paragraph) and `docs/functionality-reference.md` (the Import JSON and Specs columns rows) describe it.

**Checked.** `tsc` clean. `spec_equations_check` 69 (63 before): the 20-row box opens with Apply in focus; Esc closes it
with nothing imported and the focus on Import JSON...; a Specs cell in focus keeps it when the box opens and after
Cancel; after a click on the box's heading Esc still cancels it; the failed import's line has a close mark whose press
takes the line away, and a tab press takes it away too. New picture: `spec_import_error.png`. `editor_columns_check` 29
(23): beside the hint, not inside it, "Set Margin sides to upper" with its tooltip; a press sets spec_3 alone, the hint
goes and the line says so; one Undo brings it back with the hint; with half_freq an interval from 0 too the button reads
"... on all 2", a press sets both and one Undo takes both back. New picture: `zero_floor_button.png`. `typing_check` 51
(50): a Parameters rows import applied with Probes shown still writes Parameters, says "Imported: N changed rows. Undo
takes it back." with Show Parameters, and the focus is back on Import JSON.... `model_chooser_check` 120 (119): the whole
configuration with another network says "Imported: replaced the run settings. Undo takes it back.". Each new check looks
for what the code before did not have. Also run, unchanged: `task_rows_check` 54, `looks_check` 76, `dom_identity_check`
56, `find_fill_copy_check` 50, `sheet_check` 54, `unsaved_rows_check` 25, `blocking_issues_check` 60,
`network_panel_check` 72, `reliability_check` 20, `room_check` 31, `formula_bar_check` 21, `matched_devices_check` 37,
`edit_state_check` 28 (17 scripts, 853 checks, one lane, all passed the first time; the checks of the import box ran
again once the box took `tabIndex`, `typing_check` once more with its tab press). Not run, by the rules:
`reward_v21_check`, which pins the hint's words; they are unchanged. No flakes.

**Review follow-up.** The review of b602d87 found one slip; it is real. Apply's line took "Imported: nothing changed." from
the diff the backend sent when the file was read. That diff matches rows by ID (`structured_diff`), so it ignores row
order and any edit made after the box opened, while history.ts makes Apply an Undo step whenever the configuration's JSON
changes. The same rows in another order came in as "0 changed rows" and "No differences."; Apply put the table in the
file's order, one Undo step, yet said "Imported: nothing changed." without its Undo. So did the table's own rows applied
over an edit made in that table while the box was open (rows write their whole table). The other way round, rows the
table came back to while the box was open (an Undo pressed meanwhile) said "Imported: 1 changed row. Undo takes it back."
while Apply changed nothing and made no step, so Undo would have taken back an earlier change. `applyImport` in
`frontend/src/panels/Editors.tsx` now decides at Apply, as history.ts does: what Apply writes against the configuration as
it is then. Nothing different: "Imported: nothing changed."; a change the diff counted no row or section for: "Imported.
Undo takes it back."; the other lines as before. Left as it is: the box's own "0 changed rows" and "No differences." for
rows in another order, the backend's diff by ID. Nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso: Apply writes what it wrote before, and only its line's words change. `docs/workbench.md` (Import JSON says what
it did) names the two lines. `tsc` clean. `typing_check` 62 (51 before), on three Parameters rows: the same rows reversed
come in as "0 changed rows", and Apply puts them in that order with "Imported. Undo takes it back."; one Undo brings the
order back. The same rows in the same order say "Imported: nothing changed." and leave the Redo there. An Upper typed
while the table's own rows wait in the box is written over by Apply, with "Imported. Undo takes it back."; one Undo brings
it back. The rows from before it come in as "1 changed row", an Undo while the box is open takes the typed value back, and
Apply says "Imported: nothing changed.", the Redo still there. On the code before, those three Apply lines failed. Also
run, unchanged: `spec_equations_check` 69, `model_chooser_check` 120, `editor_columns_check` 29 (4 scripts, 280 checks,
one lane, all passed the first time). No flakes.

### SIF-108 A line that sends you to the Connection or Tasks window carries the button to it (2026-10-23; from the usability audit)

**Found.** Two audit findings: directions with no way there. The Virtuoso window with no connection said "Press
"Connection" in the workbench and choose a Virtuoso connection: the libraries are read from that Virtuoso.", and with the
link down the gate's refusal said "... Bring the link up in the Connection window (the "Connection" button in the
workbench), then try again." (J1-5). Neither had a button: the user went back to the main window, opened Connection,
connected and came back, and "try again" named no press - nothing reads again by itself after a refusal; Refresh does.
The Agent window's What's missing? list gave each item's step in plain text (J7-8), and three steps point at places that
have gone: "Choose the circuit under "Circuit source" (left)" (record 7.362 took it away; the circuit column is hidden by
default), "Press "Connection" (left)" (in the header since record 7.182) and "Raise "Max evaluations"" (the field reads
Evaluation budget). No control led to any of them.

**Changed.** `frontend/src/openAt.ts`: `OPEN_CONNECTION` and `openConnection(from)`, one page-wide event, as the Runs and
Tasks windows have. `frontend/src/panels/Connection.tsx`: the header's Connection button listens for it and opens its
window from `from`, the window that holds the click (`popupWindow.ts`), as it opens it from the page; opening it checks
nothing. `frontend/src/panels/VirtuosoWindow.tsx`: with no connection the line reads "No connection is chosen: choose a
Virtuoso connection in the Connection window. Choosing one lists its libraries here." with **Connection...** at its end.
Choosing one does list them, as the chain follows the connection (the verdict's correction of the finding). A refusal by
the connection gate carries the same button. The chain's refusal ends "Bring the link up in the Connection window, then
press Refresh."; a refused Read says "then try again", as Refresh does not read the cell; an ngspice connection keeps the
backend's "choose one in the Connection window". `frontend/src/api.ts`: `gateText` takes `then`; a window that puts its
own button beside the words leaves out "(the "Connection" button in the workbench)", and every other panel words it as
before. `frontend/src/panels/CircuitBrowser.tsx` keeps the words of the last refusal by the gate (`gateSaid`) and tells
the window when they are what it shows (`nativeGated`): another line - an older backend, SIF-88's testbench line - has no
button, and the button goes with the refusal. Nothing reads again by itself once the link is up: the verdict found that
part of the audit's fix against the design (explicit reads, `CircuitBrowser.tsx`), and Refresh stays the press.
`frontend/src/roadster.css`: SIF-107's `.line-act` keeps the button beside the words in the Virtuoso window too.
`frontend/src/panels/Agent.tsx`: an item whose step is in another window carries the button to it after what to do
(`GO_TO`): the connection **Connection...**, a circuit not read **Open Tasks** (`openTasksAt`, the Tasks window as it
is), each opened from the Agent window, its tooltip saying where it leads. The audit asked for the buttons to be put to
the user first, as record 7.109 took out buttons that repeat another (the Virtuoso window's Open among them). They were
not asked, on the user's "go on on your own": each opens a window and does nothing else, as record 7.372's Open Tasks
does on the "No task yet" line, and the header's Connection stays the way in from the page. Should the user count them
as repeats, taking the buttons out leaves the new words standing. Nothing here starts, continues or stops a run, saves a
task or writes to Virtuoso: the buttons open a window, which checks nothing. `docs/workbench.md` (the Virtuoso window,
the Connection button, What is missing before the run can start) and `docs/functionality-reference.md` (the Connection,
Library → cell → schematic and What's missing? rows) describe it. Skipped: the three stale steps' words, in
`src/gator_workbench/readiness.py` (the plan's circuit "Open a task in the Tasks window, or make one there: New task.",
connection "Press "Connection" in the header: ...", run "Raise "Evaluation budget" under Run configuration, ..."): backend
Python, outside this branch's frontend work, live only after an 8765 restart, with `test_wb_readiness.py` to run beside
it. Until then the buttons stand beside the old words. Also left: the audit's optional button on the output folder's
item, and two lines that name the header's button without one of their own, the PDK window's "Choose a connection
first" and the working-copy block's gate refusal.

**Checked.** `tsc` clean. `virtuoso_source_check` 112 (108 before): with the link down the line reads "Virtuoso cannot be
reached (tunnel). Bring the link up in the Connection window, then press Refresh." with Connection... to its right, the
tooltip saying what it opens; the press opens the Connection window, whose opener is the Virtuoso window, and reads
nothing from Virtuoso; Refresh with the link back takes the line and its button away; an older backend's line has no
button. The picture `virtuoso-3-link-down.png` shows the button. `pdk_check` 42 (40): without a connection the Virtuoso
window's line has the new words and Connection..., whose press opens the Connection window from it.
`agent_window_check` 33 (29): a real circuit's connection never tested carries Connection... after its step, no other
item a button, and the press opens the Connection window from the Agent window, asking the agent routes nothing; with no
circuit read, the circuit's item carries Open Tasks, whose press opens the Tasks window from the Agent window. New
picture: `agent-5-connection-button.png`. Each new check of a line, a button or a press looks for what the code before
did not have; the two that no button stands by another line pin where it must not be. Also run, unchanged:
`connection_panel_check` 94, `dom_identity_check` 56, `testbench_probes_check` 41, `project_help_check` 61,
`working_copy_check` 34 (its gate refusal still names the header's button), `looks_check` 76, `editor_columns_check` 29
(SIF-107's `.line-act`), `callouts_check` 8 (11 scripts, 586 checks, one lane, all passed the first time). Not run, by
the rules: `test_wb_readiness.py` (no backend change). No flakes.

### SIF-109 Enter and the keyboard work where the mouse does (2026-10-23; from the usability audit)

**Found.** Three audit findings about the keyboard. Enter did nothing in the Add a connection form or in the PDK
window's two boxes: the user typed the new connection's name, or a library, and had to click Create connection or Load,
while the ngspice window's path box reads its file on Enter and a task's or a model's rename takes Enter (J1-12). The
column titles that sort the Tasks, Runs and saved models tables were heading cells only a click could press: Tab went
past them, and Enter or Space did nothing; a run could be chosen from its row by a double click alone (J4-15; its third
part, the focus after the Continue form, was SIF-90's). The banner's Windows list was marked as a menu, with none of a
menu's arrow keys; Esc closed it with the focus in it, and Close all took the whole button away: either way the focus
fell to the page, and the next Tab began at its top (J7-12). A window's name, pressed, moves the focus into that window,
as it should: the verdict's correction.

**Changed.** `frontend/src/panels/Connection.tsx`: Enter in the name box is Create connection when that button can be
pressed (`canCreate`). Only there: an Enter in Bridge profile, typed before the name, would add the connection under the
suggested name. `frontend/src/panels/Pdk.tsx`: Enter in either box is Load; the key and the button share one condition
(`canLoad`), so a library name or a path that Load refuses sends nothing, nor does a window without a connection.
`frontend/src/panels/TableView.tsx`: `sortKeys` puts a sortable title in the Tab order (`tabIndex` 0) and sorts by it on
Enter or Space, as a press does; Space's scroll of the window is prevented. The click stays on the `th` itself, where the
checks press it (a button inside would not get that click); `aria-sort` was there already. `TableHead` - the Tasks, Runs
and saved models tables - takes it, and so do the Output files titles (`RunTabs.tsx`), sortable the same way since SIF-99:
not in the audit's list, but the one table left out would have been the odd one. `frontend/src/panels/RunList.tsx`:
`showRow` holds what the double click does, and a run's row takes Enter (`tabIndex` 0), as a task's row does since
SIF-100: Load run where it is offered, its edits question asked in the Runs window as for the double click, else the run
is shown; the window closes as it does. Enter counts on the row itself only: on Details or a link it presses that alone,
on the tick box nothing. The window's hint and Load run's tooltip name Enter. `frontend/src/panels/WindowsMenu.tsx`: the
list is plain buttons in a labelled group, no `menu` or `menuitem`, so Tab goes through it and nothing promises arrow
keys. Esc gives the focus back to the Windows button when it was in the list; a focus elsewhere stays where it is. Close
all puts the focus on the Windows button, and once the last window has gone, and the button with it, on the banner's
control before it: the run chip, else the Connection button. Each window goes at its own pagehide, not at the press, so
the move waits for the list to empty (the plan's one animation frame could come before); a window that stays open keeps
the button, with the focus on it. `frontend/src/styles.css`: a run row's and a sortable title's focus ring inside them,
as a task row's (SIF-100). Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso: Enter on a
row is Load run or the run shown, with the question they asked; Create connection adds a connection and never changes
one, and Load reads, as their buttons did - a key only where its button can be pressed. `docs/workbench.md` (the Windows
bullet, Output files, the Tasks and Runs windows' sorting, the Runs window's double click, Create connection, the PDK
window) and `docs/functionality-reference.md` (the Windows, Task-name button, Add a connection, PDK window, Runs..., Load
run and Output files rows) describe it. Left: the PDK window's loaded PDKs and the saved models' rows still answer a
double click alone (a saved model's Details have Use; a loaded PDK has no other way in) - not among the audit's findings.

**Checked.** `tsc` clean. `run_list_check` 162 (157 before): a column title is in the Tab order; Enter on "Duration"
sorts the longest run first, then Space the shortest, its default prevented; Enter on a row's Details opens them alone,
the run not chosen and the window open; the row is in the Tab order, and Enter on it shows the run (one that names no
task) and closes the window. `task_list_check` 103 (100): the Windows list is a group, with no menu roles; Esc in it
closes it, the focus back on the Windows button; after Close all the focus is on the banner's control before it (the
Connection button: no run is held there). `connection_panel_check` 96 (94): Enter in a name in use sends nothing; in a
free one it sends one request with the name and the kind, and the window says the connection was added. `pdk_check` 44
(42): Enter in the library box, holding a name Load refuses, sends nothing; Enter in the model file box loads, with both
typed fields. `files_tab_check` 43 (42): Size is in the Tab order; Enter sorts the smallest first, then Space the other
way. Each new check of a key's effect looks for what the code before did not have; the two that a refused value sends
nothing pin the shared condition. Also run, unchanged: `model_chooser_check` 120, `run_control_check` 160,
`dom_identity_check` 56, `training_tab_check` 108, `virtuoso_source_check` 112, `export_check` 37, `corner_check_check`
39, `looks_check` 76, `network_panel_check` 72, `task_run_check` 39, `reliability_check` 20, `agent_window_check` 33,
`callouts_check` 8 (18 scripts, 1,328 checks, one lane, all passed the first time). No flakes.

### SIF-110 Show results in Running now closes it, and a window opens again where you left it (2026-10-23; from the usability audit)

**Found.** Two audit findings about the pop-up windows. Show results in the Runs window closes that window (record
7.291), but the same button in the run brief, "Running now", left its window over the page: the user closed it by hand
to see the tabs it had just changed, and two buttons with one name did two things (J7-11). Every window opened at the size
its code gives it - Runs 1500 x 860, Tasks 1500 x 760, the RL model window 1180 x 920, the Virtuoso and ngspice windows
980 high - in the place the browser chose, so a size or place the user gave one was lost at every opening; since record
7.291 closes the Tasks, Runs and RL model windows after each choice, they are opened, and sized again, often (J7-14). Not
so: that the Runs and Tasks windows open larger than a 1366 x 768 screen - the browser fits a window to the screen (the
verdict's correction).

**Changed.** `frontend/src/panels/RunBrief.tsx`: a card's Show results shows the run, then closes the brief, as Show
results in the Runs window closes that one (RunList's `chosen`); its tooltip ends "The window then closes.". Refresh and
Open in Runs keep it open. The audit asked for this to be put to the user first: record 7.291 named the Tasks, Runs and RL
model windows only, and the brief can stand open as a watch on live runs. It was not asked, on the user's "go on on your
own", as SIF-108 did: the press shows the run as before, the brief shows nothing that is lost when it closes, and the run
chip opens it again with one press, at the size and place it was left at (below). Should the user want it to stay open,
the one click handler goes back. `frontend/src/panels/popupWindow.ts`: every pop-up window - Connection, Virtuoso, PDK,
ngspice, Tasks, Runs, the brief, the RL model window, the task file, Agent - keeps its size and place in this browser,
under `gator-workbench-window-<name>` (`frontend/src/contract.ts` `WINDOW_PLACE_KEY_PREFIX`; `kept.ts` `keep`, so blocked
storage stops nothing): once a resize has come to rest (300 ms), and as the window goes - its own pagehide, the page
leaving, and the PDK and ngspice windows' close when their panel goes -, since a move fires no event. `placed` gives the
next opening that size and place: `width` and `height` from the window's innerWidth and innerHeight, `left` and `top` from
screenX and screenY. The audit's fix kept outerWidth and outerHeight, but window.open's width and height are the size of
the page inside the window: the window would have grown by its frame at every opening. The size is at most the screen's,
and the corner is moved onto the screen of the window the press was in: a place kept on a second screen may be on no
screen now. A size kept for other first features is not used: the Connection window opens 1100 wide for a connection of
two Virtuoso sessions and 660 for one, and a size left at 660 would cramp the two. Nothing kept, a value that is not one,
or a closing window that answers no size (under 100 px): the window's own features, as before. Nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso: Show results in the brief does what it did, and a window's
size and place are the browser's alone. `docs/workbench.md` (the run brief; a paragraph of the page's look and layout,
after the changes of record 7.372) and `docs/functionality-reference.md` (the Windows and Run brief rows) describe it.

**Checked.** `tsc` clean. `run_control_check` 162 (160 before): after Show results in the brief the run is under Run
status and the brief has closed, its tooltip ending "The window then closes."; the chip opens it again, and its Open in
Runs opens the Runs window at the run with the brief still open. `run_list_check` 167 (162): the Runs window given 700 x
500 at (40, 30) by device emulation keeps that size and corner once the resize comes to rest, and again as it closes (the
kept value taken away first); the next press of Runs... asks window.open for "popup,width=700,height=500,left=40,top=30";
a place kept at (50000, -50000), 99999 high, opens at the screen's right edge and top, as high as the screen (800 x 600,
headless); a size kept for other first features is not used ("popup,width=1500,height=860"). A headless window ignores the
size it asks for, so the checks look at what the page keeps and what it asks window.open for (wrapped for one press, as
`lib/rl_networks.mjs` does); each check's browser profile is new and windows are found by their title, so a kept size
changes no other check. Each new check looks for what the code before did not have. Also run, unchanged - every other
check that opens a pop-up window: `dom_identity_check` 56, `connection_panel_check` 96, `virtuoso_source_check` 112,
`task_save_check` 91, `model_chooser_check` 120, `ngspice_window_check` 43, `task_list_check` 103, `pdk_check` 44,
`agent_window_check` 33, `training_tab_check` 108, `testbench_probes_check` 41, `typing_check` 62, `task_rows_check` 54,
`project_help_check` 61, `working_copy_check` 34, `looks_check` 76, `network_panel_check` 72, `task_run_check` 39,
`reliability_check` 20, `graph_view_check` 69, `reward_block_check` 33, `circuit_source_check` 17,
`encoder_models_check` 24, `model_structure_check` 31, `consistency_check` 14, `network_inputs_check` 9 (28 scripts, 1,791
checks, one lane, all passed the first time). `run_list_check`'s new checks were then made stricter - the first version's
1200 x 700 came back as the headless screen's 800 x 600, at the corner (0, 0) -, and one run of it stopped at the check's
own fault (an emulated window position needs an emulated screen around it); with one it passed, 167. No flakes.

**Review follow-up.** The review of 1c3b584 found one slip; it is real. The size kept was the page's, innerWidth x
innerHeight, in its CSS px, which shrink as the window's page zoom grows (innerWidth = the page's width / zoom), while
window.open's `width` and `height` are screen px, as are `left` and `top`, screenX and screenY and the screen's sizes,
which zoom leaves alone. At a page zoom of 125 % - Edge's default page zoom set so, or Ctrl + in the pop-up - each opening
asked for the last size / 1.25: the window came back a fifth smaller every time, one step per choice in the Tasks, Runs
and RL model windows (record 7.291), down to the 100 px guard; under 100 % it grew to the screen's size. Before SIF-110
each window opened at its fixed size. A probe of a headed Edge with a throwaway profile whose default page zoom was 125 %
(a script in the session's scratchpad, not a check) showed it: asked for 700 x 500, the page measured 561 x 400; asked
for that, 449 x 320, then 360 x 256 and 289 x 205, while outerWidth and screenX read the same at 100 % and at 125 %. At
100 %, on this screen's 150 % scaling, the page even came back a pixel wider at each opening (701, 702, 703, 704).
`frontend/src/panels/popupWindow.ts`, the review's fix: `Place` keeps the window's outer size (`ow` x `oh`, outerWidth x
outerHeight) beside its corner and its page's size; `placed` still gives window.open the page's size and the corner - a
window at 100 % zoom opens at its size at once - and now `outer`, the outer size and corner, which `open()` sets with
resizeTo and moveTo right after window.open. The outer size is not asked for as `width`: the window would grow by its
frame at every opening, as the record said. The corner is kept on the screen by the outer width (by the page's, a window
kept at the screen's right edge reached past it by its frame). A place is kept only with an outer size of 100 px or more
and a page size; one kept before, without the outer size, is not used. In the same probe, asked for the page's size and
then resized and moved, the window came back at 716 x 570 at (40, 30) at every opening, at 125 % as at 100 %: a headed
Edge takes resizeTo and moveTo said at once after window.open (within 150 ms); a headless one ignores both, as it ignores
window.open's size. At a zoom other than 100 % the window shows at its page's size first, then takes its own. Nothing
here starts, continues or stops a run, saves a task or writes to Virtuoso: a window's size and place are the browser's
alone. `docs/workbench.md` (the paragraph on window sizes) and `docs/functionality-reference.md` (the Windows row) say it
holds at any zoom, and how. `tsc` clean. `run_list_check` 167 (four checks rewritten): the Runs window, its emulated 1500
x 860 let go and given 700 x 500 at (40, 30) through Browser.setWindowBounds, which a headless window takes, keeps that
outer size and corner and its page's 678 x 411 once the resize rests; with its page's two numbers set to what 125 % makes
of them (542 x 329: a headless page cannot be zoomed, and innerWidth and innerHeight are [Replaceable]) and the window
closed, the outer size and corner kept are unchanged and the page's size is 542 x 329; the next press asks window.open
for "popup,width=542,height=329,left=40,top=30", then resizeTo(700, 500) and moveTo(40, 30) (the window's two wrapped
for the press, as window.open is); a place kept off the screen comes to its right edge by its outer width, 316
("left=484", then resizeTo(316, 600) and moveTo(484, 0)); a size kept for other first features asks for its own and sets
nothing. On the code before, the first four failed (163 passed). Also run, unchanged - every other check that opens a
pop-up window: `run_control_check` 162, `dom_identity_check` 56, `training_tab_check` 108, `connection_panel_check` 96,
`virtuoso_source_check` 112, `task_save_check` 91, `testbench_probes_check` 41, `task_rows_check` 54,
`model_chooser_check` 120, `typing_check` 62, `project_help_check` 61, `working_copy_check` 34, `task_list_check` 103,
`ngspice_window_check` 43, `looks_check` 76, `network_panel_check` 72, `task_run_check` 39, `reliability_check` 20,
`graph_view_check` 69, `pdk_check` 44, `reward_block_check` 33, `circuit_source_check` 17, `encoder_models_check` 24,
`model_structure_check` 31, `consistency_check` 14, `agent_window_check` 33, `network_inputs_check` 9 (28 scripts with
`run_list_check`, 1,791 checks, one lane, all passed the first time). No flakes.

### SIF-111 The task file's help and the readiness checklist name what is on the page (2026-10-23; backend words held back by SIF-81 and SIF-108)

**Found.** Two lots of words the page shows come from the backend, which the frontend records leave alone. The task
file's own help (`task_files.py` HELP, shown as "What each part is" since SIF-81) named Parameters keys that exist
nowhere - "range" and "grouping" (the file says lower/upper and binding_group, the editor Lower, Upper and Tied to) -
gave the Probes and Specs keys without the editor headers a reader knows them by, and told the cell and copy parts by
a code change of 2026-09-23 instead of what matters: `task_files.parse()` reads neither, so editing them there changes
nothing (survey of 2026-10-21, issues 26 and 27; issue 8, the escaped quotes, went with SIF-81). The Agent window's
readiness checklist (`readiness.py`) sent the user to 'Choose the circuit under "Circuit source" (left)', a control
removed in 7.362, to 'Press "Connection" (left)' for the button in the header, and to 'Raise "Max evaluations"' for the
field called Evaluation budget (usability audit J7-8, left out of SIF-108 as backend text).

**Changed** (`src/gator_workbench/task_files.py`, `src/gator_workbench/readiness.py`; words only). The help gives each
key with its editor header: instance_path (Instance), parameter_name (Parameter), lower and upper (Lower, Upper),
binding_group (Tied to: the row this one follows, times its ratio); result_source (Result source), source_name (Output
name), signal (Expression); equation, constraint (Limit), hard, soft_weight, direction_after_feasible (Objective, chosen
in the Limit list), normalization_scale (Scale). cell: the cell the task was read from, shown only - "Apply to editors"
does not change it; read another cell in the Virtuoso window. copy: the cell above, except in a task saved before
2026-09-23 (its <library>_GATOR copy), shown only. The JSON examples of the maestro part stay: they show what to type.
The checklist says "Open a task in the Tasks window, or make one there with "New task"", "Press the connection button in
the header" (the button shows the connection's name; "Connection" is its label) and "Raise "Evaluation budget" under Run
configuration". No page code reads these words (SIF-108's buttons go by item id). A task saved from now on carries the
new help in its file; older files keep theirs, which the page reads but never applies. Live only after a restart of
the server on 8765.

**Checked.** `tests/workbench/test_wb_task_save.py`, `test_wb_readiness.py`, `test_wb_agent_cli.py`: 39 passed (no
test pins these words; `task_save_check` serves its own help text). Made on a side branch (sif-help-text, 43f4960 and
00b9b42) while the usability run held this worktree, then cherry-picked.

### SIF-112 The blocking-issues list and the calibration line close with an X (2026-10-23; from the icon audit)

**Found.** Under the header, one action - take this away, nothing else changes - had three looks. A refused Start's
line ends with an X (LaunchRefusal), Matched devices' box with an X at its head's end, the message line with an x; but
the list the red "N blocking issues" button opens ended its head line with the word "Hide", and the line a calibration
that proposes nothing leaves ("Calibration finished: nothing is proposed. ...") with "OK", which reads as a dialog's
confirm although it only takes the line away (icon audit MAIN-5 / ICON-13, MAIN-9). The audit's first batch also made
Output settings' "Copy path" the copy icon (MAIN-1) and put down, in one CSS block, what the icon buttons of all four
batches need on lines laid out for words.

**Changed.** `frontend/src/panels/Issues.tsx`: the list's Hide is the close mark, the `close` drawing in a button framed
as Matched devices' X; its word stays for screen readers and the checks (`.sr-only`: the button's text is still "Hide"),
and its tooltip reads "Hide: The list folds away; the red "1 blocking issue" button in the header shows it again." - the
button named in its words, as the Start and Calibration tooltips name it (SIF-45). `frontend/src/App.tsx`: the
calibration line's OK is the same X with "Close" as its word - what an X is called, and what the refusal line's X in
this place is called; no check or code looked for "OK" - drawn without a frame or fill by `button.line-close`, the close
mark SIF-107 made after the refusal line's (the plan's new `button.calibration-close` rule would have repeated it). Its
tooltip: "Close: This line goes. The run's numbers stay under Run status." A press does what OK did,
`answerCalibration('no')`, which with nothing proposed only keeps the run as answered in this browser: nothing applied,
no message. `frontend/src/roadster.css`: the one block for every batch of the audit, at the file's end. Measured in
headless Edge under the page's two stylesheets (a scratch probe, the icon's middle against the words'), the plan's rule
for the issue list - the button alone centred - put the X 6 px under the head's words: a flex line's baseline-aligned
words keep to its top while the 31 px button makes it taller. On their shared baseline it stood 2 px over them. The head
now centres its parts (`.issue-list-head { align-items: center }`): the X within 0.7 px of the words, the bold count and
the hint within 0.3 px of one baseline, and at 600 and 700 px, where both wrap to two lines, all three stay centred. The
plan's rule for Running now's Refresh, the second batch's, measured best (0.5 px; 1.5 px on the baseline) and is in the
block; it matches no button until that batch lands. Left out, as the audit's list of buttons that keep their words
(`kept`) says: Copy path (ICON-11: record 7.41 made it plain text at the user's request, "make it plain text no button
style", and record 7.125 kept it so as the user's choice) and the graph view's Fit (ICON-16, the third batch's WIN-10).
So the block has neither the plan's `button.text-link:has(> svg.icon)` nor its `.graph-tools` rule, and `OutputPanel.tsx`
and `output_panel_check` are unchanged. Nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso. `docs/workbench.md` (the calibration line; the blocking-issues paragraph) and
`docs/functionality-reference.md` (the Calibration ready and N blocking issues rows) say it.

**Checked.** `tsc` clean. `blocking_issues_check` 62 (60 before): Hide is the close mark at the head's end, "Hide" for
screen readers and at the start of a tooltip that names the header's "1 blocking issue" button; its X centred on the
head's words within 1 px (0 px; in the probe the plan's rule was 5.4 px off by this measure, the baseline 2.7 px).
`calibration_check` 48 (45 before; real MOCK runs on the check's scratch backend): the second run's status with FIXTURE
values, a calibration that proposed nothing and that this browser has not answered - the line says why, with one
button, an X without a frame or fill, "Close" for screen readers and at the start of its tooltip; a press takes the line
away, the stored configuration and the message line unchanged, the run kept as answered. New picture:
`calibration-0d-nothing-proposed.png`. Each new check looks for what the code before did not have (Hide and OK had no
drawing and no `.sr-only` label). Also run, unchanged: `calibration_save_check` 22, `callouts_check` 8,
`reliability_check` 20, `run_control_check` 162 (6 scripts, 322 checks, one lane, all passed the first time). No flakes.

### SIF-113 The list windows read again with the refresh icon, and Delete task is a waste bin (2026-10-23; from the icon audit)

**Found.** One action - read the list again - had two looks a few centimetres apart. The bottom tabs' Data tables and
Output files and the Corner check draw it as the refresh icon, an arrow around; the Runs, Tasks and RL model windows
started their tool lines with the words "Refresh list" - in the Runs and Tasks windows above the Folders' icons for a
new folder, a rename and a delete - and Running now had "Refresh" beside its heading (icon audit BOT-1 / ICON-4, WIN-1 /
ICON-5, WIN-2 / ICON-6, BOT-2 / ICON-2). The Tasks window's Refresh list had no tooltip at all. Delete task, already an
icon, was a tray struck out - the tray of Load task and Export JSON - so it read as "unload", while Delete folder in the
same window and the editors' Delete selected are a waste bin; and its drawing stood still while its delete was on its
way, where other icon buttons show the hourglass (ICON-19, the drawing's half).

**Changed.** `frontend/src/panels/RunList.tsx`, `TaskList.tsx`, `ModelChooser.tsx`: Refresh list is the `refresh`
drawing, its words in `.sr-only` - the button's text is still "Refresh list" - and at the start of its tooltip: in the
Runs and RL model windows "Refresh list: every run folder is read again from the disk." as before, in the Tasks window
the new "Refresh list: the tasks, their folders and the run list are read again." (what `refresh(true)` reads). Icon and
words stay while the list is read, as the audit's verdict asks: the button is greyed out, and the count on its line says
"Reading the runs..." (the tasks, the saved models). The lines that send the user to the button - "Press Refresh list to
retry", an older server's "press "Refresh list"", Move to…'s "... press Refresh list." - stay word for word: the tooltip
starts with those words. `frontend/src/panels/RunBrief.tsx`: Running now's Refresh is the same icon, "Refresh" for
screen readers and at the start of its tooltip, with nothing beside the drawing (`run_control_check` finds it by its
exact text), centred on the heading by the rule SIF-112 put in roadster.css's icon block for it: no CSS is added. The RL
model window's line keeps its parts at their foot, so its icon button stands beside the Design list as the bottom tabs'
icon buttons stand beside theirs; the Runs and Tasks windows centre their lines. `TaskList.tsx`: Delete task draws the
waste bin (`delete`), and while its delete is on its way the hourglass (`wait`), "Deleting..." for screen readers as
before; its tooltip (`Left.tsx`) is unchanged, and it still asks once more. The struck-out tray, now unused, leaves
`Icons.tsx` with the audit's fourth batch, as the plan orders. Left out: the Rename in a task's and a saved model's
Details (WIN-6, WIN-7). The audit's list of buttons that keep their words holds them (ICON-17): Rename applies the name
typed in the box beside it - a commit, which keeps its words -, a pencil beside a box that can be typed in reads as
"edit" (the Folders' pencil starts a rename in a prompt, another action), and its busy "Renaming..." is in the words.
Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso: each press does what it did.
`docs/workbench.md` (the run brief; the Tasks window's Refresh list and Delete task; the Runs window; the saved models)
and `docs/functionality-reference.md` (the Task-name button, Delete task, Saved models, Run brief and Runs... rows) say
it.

**Checked.** `tsc` clean. `run_control_check` 164 (162 before): Running now's Refresh is the icon, "Refresh" for screen
readers and at the start of its tooltip, its middle 0.3 px from the heading's. `run_list_check` 168 (167) and
`model_chooser_check` 121 (120): Refresh list is the icon, its words for screen readers - the text still exactly
"Refresh list" - and its tooltip as before. `task_list_check` 105 (103): Refresh list the icon, with the new tooltip;
Delete task the waste bin - the drawing of the editors' Delete selected -, "Delete task" for screen readers and at the
start of its tooltip. `virtuoso_source_check` 114 (112): Delete task the editors' bin; while its delete is on its way -
the check's fixture holds the answer until it has looked - greyed out, "Deleting..." and another drawing than the bin
(the log shows the hourglass's). Each new check looks for what the code before did not have (no drawing, no `.sr-only`
label, no tooltip on the Tasks window's button, the tray, a drawing that stood still). Also run, unchanged:
`ngspice_window_check` 43, `graph_view_check` 69, `model_structure_check` 31 (8 scripts, 815 checks, one lane, all
passed the first time); and every other check that opens the Tasks, Runs, RL model or Running now window:
`training_tab_check` 108, `testbench_probes_check` 41, `task_rows_check` 54, `typing_check` 62, `project_help_check` 61,
`reliability_check` 20, `looks_check` 76, `network_panel_check` 72, `task_run_check` 39, `pdk_check` 44,
`reward_block_check` 33, `circuit_source_check` 17, `encoder_models_check` 24, `agent_window_check` 33,
`consistency_check` 14, `network_inputs_check` 9 (16 scripts, 707 checks, one lane). One flake: `reward_block_check`
stopped after 23 checks in that batch - "the DevTools session closed (its window went away)", in the RL model window's
network settings after "Use the template's values", away from the saved models - and passed alone at once (33).

**Review follow-up.** The review of 6f8fe39 found one slip; it is real. `virtuoso_source_check`'s new check of Delete
task while its delete is on its way named the hourglass but asked only for another drawing than the bin, and the tray of
the code before, which stood still until the answer came, is another drawing too: the check passed on the code it was to
tell apart, so what is said above - each new check looks for what the code before did not have, "a drawing that stood
still" among it - was not true of it, and a busy drawing such as the refresh arrow would have passed as well.
`frontend/scripts/virtuoso_source_check.mjs` now asks for the hourglass itself, by its first line (`M4 2.5h8M4 13.5h8`,
as `files_tab_check` tells it), and for the bin just before the press: the hourglass for the bin, as the check says.
Only the check changes; the page and what each press does are as SIF-113 left them. `tsc` clean.
`virtuoso_source_check` 114, all passed the first time (one lane). Two probe runs, `TaskList.tsx` changed for each and
restored after: the code before (the tray throughout) failed both SIF-113 checks of Delete task (112 passed); a bin that
stands still while the delete is on its way failed this one alone (113 passed). No flakes.

### SIF-114 The Virtuoso window's Refresh is the refresh icon, and the CIW lines' Copy the copy icon (2026-10-23; from the icon audit)

**Found.** Two more actions with a plain meaning still had a look of their own. The Virtuoso window's Refresh - read the
libraries, the cells and the schematic again, read-only and zero-cost - was the word "Refresh", where the list windows
(SIF-113), the bottom tabs and the Corner check draw the refresh icon, and its tooltip started "Reads the libraries...",
not with its word. In the Connection window's step 2, "Load the bridge in the Virtuoso CIW", each block of CIW lines - the
load lines, and the reload lines in the "already running" fold - had a word button "Copy" without a tooltip, where Output
files' Copy run path, the same action, is the copy icon (icon audit WIN-3 / ICON-3, WIN-4 / WIN-5 / ICON-9).

**Changed.** `frontend/src/panels/VirtuosoWindow.tsx`: Refresh is the `refresh` drawing, its word in `.sr-only` - the
button's text is still "Refresh", by which the checks press it - and at the start of its tooltip, now "Refresh: Reads the
libraries, the cells and the schematic again, ...", so the gate's refusal "... then press Refresh." still names it. While
a read is on its way it is greyed out and the hint beside it says "Reading the ... from Virtuoso...": icon and word stay,
as Refresh list's do (SIF-113). "PDK window..." beside it opens a window and keeps its words. No CSS: on the window's
line, whose parts keep to its foot, the 31 px icon button stands before the 34 px "PDK window...", the icon's middle
1.3 px under the words'. `frontend/src/panels/Connection.tsx`: both Copy buttons come from one `copyButton` of the session
card - the `copy` drawing, "Copy" for screen readers, the tooltip "Copy: These lines to the clipboard, to paste into the
Virtuoso CIW." - where the word stood, at the code box's top. The 1.5 s "Copied" after a copy that went through is the
`check` drawing with "Copied" as its word; the tooltip stays the action's, as Save now's does while it saves. What a press
does is unchanged (`copyText`: the window's own clipboard; a refused copy shows nothing, as before). The check mark also
draws the Corner check's Check until the audit's fourth batch makes that the play mark (ICON-20), as the plan orders;
that batch also brings `Icons.tsx`'s notes on each drawing up to date, as SIF-112 and SIF-113 left them. Left out: the
graph view's Fit (WIN-10). The audit's list of buttons that keep their words holds it (ICON-16: three letters, so no room
is saved, and the four-corner drawing reads as "full screen" there, as if it enlarged the dialog); SIF-112 left out the
CSS it would have needed for that reason. The Add-a-connection form's Refresh (WIN-9 / ICON-1) and the Agent window's
Copy link (WIN-14 / ICON-10) keep their words too, as the plan says. Nothing here starts, continues or stops a run, saves
a task or writes to Virtuoso: Refresh reads as it did, gated, and Copy writes only to the browser's clipboard.
`docs/workbench.md` (the Virtuoso window's Refresh; Connecting from the panel, step 2) and
`docs/functionality-reference.md` (the CIW commands with Copy and Library → cell → schematic rows) say it.

**Checked.** `tsc` clean. `connection_panel_check` 101 (96 before): the Copy of each CIW block is the copy icon (its
drawing's line), "Copy" for screen readers and at the start of its tooltip, at the code box's top, 6 px to its right;
a press - the window's clipboard stood in for - puts the load lines on the clipboard and shows the check mark with
"Copied", the tooltip and the reload lines' Copy unchanged, nothing sent; 1.5 s later the copy icon and "Copy" again; a
copy the browser refuses shows no check mark. `virtuoso_source_check` 116 (114): Refresh is the refresh icon (its
drawing's line), "Refresh" for screen readers and at the start of the new tooltip, before "PDK window..." on its line,
the icon's middle within 2 px of the words' (1.3 px). A probe run on the code before (both `.tsx` files as at HEAD,
restored after): the four checks that ask for what is new failed (99 and 114 passed); the place, the return after
1.5 s and the refused copy pass on both, as they pin what was already so. Also run, unchanged: `testbench_probes_check`
41 and `project_help_check` 61 (both press Refresh by its word), `pdk_check` 44, `working_copy_check` 34,
`agent_window_check` 33, `callouts_check` 8, `graph_view_check` 69 (Fit as it was) - 9 scripts, 507 checks, one lane,
all passed the first time. No flakes. `dom_identity_check` was not used as a gate: it compares refactors, and the
connection window's scene changes by design.

### SIF-115 The Corner check's Check is the play mark, and the Training tab's × say their names (2026-10-24; from the icon audit)

**Found.** The Corner check's Check starts simulations - REAL Spectre ones, after the budget question - but drew a check
mark, which reads as done or OK, while the page's other starts drawn as icons, the header's Start and Resume and Run
status's Continue..., are the play triangle (the header's Calibration, which starts a run too, keeps its word), and
Stop's square takes Check's place while the check works. Since SIF-114 the same check mark also
said "Copied" in the Connection window, so it meant two things (icon audit ICON-20). In the Training tab, the × on a
compared run's chip and the × in a chart's title had tooltips that did not start with their names, the rule every icon
button keeps so that the tooltip names what the screen does not show: "Remove <run>" read "Remove: take <run> off the
charts", "Remove chart 2" read "Remove chart: take this chart off the page" (ICON-23). And `Icons.tsx` still held the
tray struck out that Delete task drew until SIF-113, unused since (ICON-19, the drawing's half), while its notes named
what each drawing stood for when it was first drawn: the check mark "the corner check", the bin Delete selected alone.

**Changed.** `frontend/src/panels/CornerCheck.tsx`: Check draws `play`, the play mark of Start, Resume and Continue...;
the hourglass while the start is on its way, with "Starting..." for screen readers, as before. Its word, tooltip, place
and colour are unchanged, and so is what a press does (`launchWithConsent`: for a real circuit the budget question, then
the connection question; a no sends nothing). `frontend/src/panels/TrainingTab.tsx`: the tooltips read "Remove <run>:
take it off the charts" and "Remove chart <n>: take this chart off the page"; their labels, classes and presses are as
they were. `frontend/src/panels/Icons.tsx`: `delete-task` leaves the list of drawings, as SIF-113 said it would. So does
`load`, the tray with an arrow into it: Load task, named Reload saved values from record 7.146, drew it until record
7.260 removed that button, and nothing has drawn it since. The plan kept it (the `IconName` list it gives after the
change still holds `load`), and the audit's ICON-24 calls taking it out a separate cleanup; but a note naming the
actions a drawing stands for has nothing to name for it, and `tsc` proves nothing names either. Each drawing's note now
names every button that draws it: the play mark Start, Resume, Continue... and Check; the hourglass Starting...,
Pausing..., Resuming..., Aborting..., Finishing..., Reading..., Exporting..., Deleting... and a download being made
(Save now's and Save as's Saving... keep the floppy and the task document); the stop square
Abort and the Corner check's Stop; the task document Save as, a new task; the plus Add, Add chart and Add to
Parameters; the bin Delete selected, Delete folder and Delete task; the arrow up Export JSON and Export status (JSON);
the arrow around Refresh and Refresh list; the two sheets Copy run path, Copy for Excel and the CIW lines' Copy; the
check mark only Copied; the X Close, Hide, Training's Remove and the header's Let go; the pencil a folder's Rename in
the Runs, Tasks and RL model windows; the four corners Training's Reset zoom. The file's head names what SIF-112 to
SIF-114 made icons and the two drawings changed so that one action has one drawing, and its example label "Load task",
a button that is gone, is "Delete task". Left out: the plan's notes that named Copy path, the Rename of a task or a
saved model, and the graph view's Fit among these drawings: those buttons keep their words (the audit's `kept`, as
SIF-112 to SIF-114 say), so no drawing stands for them. Also left out, as the audit's verdict says: Continue...'s
tooltip starts "Continue:" without the dots, which names it all the same. Nothing here starts, continues or stops a run,
saves a task or writes to Virtuoso: Check asks as it did. `docs/workbench.md` (the Corner check's buttons; the
Training tab's two ×) and `docs/functionality-reference.md` (the Training and Corner check rows) say it.

**Checked.** `tsc` clean; `grep -rn delete-task frontend/src` prints nothing. `corner_check_check` 40 (39 before):
Check draws the play mark (its drawing's line, `M4.5 2.5l8 5.5-8 5.5z`), "Check" for screen readers and at the start of
its tooltip. `training_tab_check` 110 (108): each compared run's × is "Remove <run>" for screen readers, the run named as
its chip names it, its tooltip "Remove <run>: take it off the charts"; with eight charts each chart's × is "Remove chart
1" to "Remove chart 8", its tooltip starting with the same words. A probe run on the code before (both `.tsx` files as
at HEAD, restored after): the three new checks failed (39 and 108 passed), the Check still drawing the check mark. Also
run, unchanged: `task_list_check` 105, `ngspice_window_check` 43 and `virtuoso_source_check` 116 (Delete task, the bin,
by its label), `matched_devices_check` 37 (its X), `connection_panel_check` 101 (the check mark of Copied, by its
drawing's line), `run_control_check` 164 (the header's play mark and Let go's X), `dom_identity_check` 56 (it records
the Corner check and the Training tab with a compared run). With `training_tab_check`: 8 scripts, 732 checks, one lane,
all passed the first time; `corner_check_check` alone, also the first time: the plan's `--only corner_check` names no
script (`run_checks.mjs` adds `_check` only to a name that does not end in it), so it is called by its whole name. No
flakes.

**Review follow-up.** The review of 95a9d69 found three slips, all real, in words only: the code is right. (1) "Changed"
said Load task drew `load` until record 7.146 made that button "Reload saved values", in words. Record 7.146 (d8b8c4f)
renamed it and kept it an icon, `<Icon name="load" label="Reload saved values" />`; record 7.260 (6fa7d6b, 2026-10-07)
removed the button, as `docs/workbench.md` says ("The separate Load task / Reload saved values icon was removed in
7.260"), and no later commit draws the tray (`git log -G` over `frontend/src`). And the plan did name it: its `IconName`
list after the change still holds `load`, and the audit's ICON-24 calls taking it out a separate cleanup. "Changed" now
says both; the drawing stays out, as nothing names it (`tsc`). (2) "Found" and the Corner check's bullet in
`docs/workbench.md` put Continue... in the header, whose run buttons are Save now, Start / Pause / Resume and Abort /
Force abort / Let go (`RunControl.tsx`): the play mark Continue... is the Run status tab's (`RunTabs.tsx`), and its
form's Continue is `ContinueForm.tsx`'s. Both now say "the header's Start and Resume and Run status's Continue...".
"Found" also called them every other start on the page, but the header's Calibration starts a run too and keeps its
word, so it now speaks of the starts drawn as icons (the audit's ICON-20 says "every other start" as well).
(3) "Changed" gave the hourglass to every "...ing" a button shows, but Save now's "Saving..." keeps the floppy
(`RunControl.tsx`) and Save as's the task document (`TaskSave.tsx`). It now lists the labels that `Icons.tsx`'s note on
the hourglass lists, which were right: Starting..., Pausing..., Resuming..., Aborting..., Finishing..., Reading...,
Exporting..., Deleting... and a download being made. The commit message makes none of these claims and stays as pushed.
No code changed: `tsc` clean; no check reads these texts (the scripts name `docs/` only in comments), so none was rerun.

### SIF-116 Training's first passing design and Run status's first feasible design say how they count (2026-10-24; from the survey of 2026-10-23)

**Found.** For one run of mscr_vco_lin_c (seed 0, 10-16 16:32) Run status read "First feasible design at 4 evaluations"
and the Training tab's key numbers "First passing design evaluation 35" (the survey's S10-1, pictures
`05-bottom-run-status.png` and `05-bottom-training.png`). Both were right, and neither said how it counts, so the two read
as a contradiction. Run status gives `first_feasible_eval_count`, the evaluations used when the first feasible design came
back (`budget.py` `mark_first_feasible`: those charged at that moment, in flight included): 4 = 1 completed + 3 in flight,
and that design was dispatch #1, the one the episode started from. The Training tab gives an evaluation number and leaves
the designs episodes start from out, as its charts do (`keys.ts`): its 35 was the first design the run proposed. Run
status's "at 4 evaluations" also looked like an evaluation number, and read "at 1 evaluations" for a baseline feasible at
once: the facts row below it says "at 1 evaluation used" since the review of SIF-76, the tile had kept the old words.

**Changed.** `frontend/src/panels/training/keys.ts`: the key numbers carry `startPassed`, the evaluation number of the
first episode start that met every hard spec when it came before the first passing design (or no design the run proposed
has passed yet), else null; kept up to date as rows arrive by the run's shared preparation (`Prep.first`), as `firstPass`
is, which is unchanged. `frontend/src/panels/TrainingTab.tsx`: the "First passing design" tile and its column in the
table of several runs share one tooltip, "The evaluation number of the first design the run proposed that met every hard
spec. Episode starts (the design each episode begins from) are left out, as on the charts. Run status's "First feasible
design" counts them too, and gives the evaluations used by the time that design came back, those still in flight
included." (it read "The evaluation number of the first design that met every hard spec."). When an episode start passed
first, a grey line under the number says so, "an episode start passed first, at evaluation 1": in the tile, and in the
table under that run's own number. `frontend/src/panels/fields.tsx`: `KeyTile` takes that line as `note`;
`frontend/src/roadster.css` `.key-tile-note` sets it at 12 px in the label's grey, in the table at the table's size under
the value. `frontend/src/panels/RunTabs.tsx`: the "First feasible design" tile reads "at 4 evaluations used", as the facts
row ("at 4 evaluations used (dispatch #1, 1 completed, 3 in flight, 4 launches)") and the budget's "evaluations used"
beside it count, and "at 1 evaluation used" for one (`plural()`); its tooltip: "The evaluations used by the time the first
design that met every hard spec came back: every design sent to the simulator by then counts, those still in flight too,
and so does the design an episode starts from. The facts below give its dispatch number. The Training tab's "First passing
design" is an evaluation number instead, and leaves episode starts out." The plan asked for the tooltip alone; "used" is
this record's, since "at 4 evaluations" beside the Training tab's new "at evaluation 1" would still read as two evaluation
numbers until a hover. Left as they are: the run brief's card ("First feasible design at evaluation 4", `RunBrief.tsx`)
and the Tasks window's newest run ("first feasible at evaluation 34", `TaskList.tsx`, SIF-68) write the same count as an
evaluation number too; they are outside this batch's files, for a later one. Nothing here starts, continues or stops a
run, saves a task or writes to Virtuoso. `docs/workbench.md` (Run status at a glance; Key numbers) and
`docs/functionality-reference.md` (the Run status and Training rows) say it.

**Checked.** `tsc` clean. `training_data_check` 120 (117 before): `startPassed` is 1 for the baseline that passed before
the first proposed design (122), still 1 with no proposed design passed yet, null when the starts passed only after it and
for an empty run; the random runs' "kept up to date = derived at once" compare it too (against the builders before 7.221,
given `--reference`, only where both modules have it). `training_tab_check` 113 (110): the live run's tile says in its
tooltip what it leaves out and what Run status counts, with no line under its number (its starts pass from 71, after 62);
a new fixture run whose episode starts pass from the baseline on shows "evaluation 62" with "an episode start passed
first, at evaluation 1" under it, and compared with the failed run, the table names it under that run's number only, the
column's tooltip the tile's (pictures `training-start-first.png`, `training-start-first-table.png`). `run_control_check`
167 (164): the tile's tooltip; with a first feasible design in the fixture's status, "at 4 evaluations used" beside the
facts row's "at 4 evaluations used (dispatch #1, 1 completed, 3 in flight, 4 launches)", and "at 1 evaluation used". Its
first run failed the "at 4" step: `FIRST_TILE` ended in `?? null`, so `${FIRST_TILE} === 'x'` read `text ?? (null ===
'x')` and a wait for a word was over at once, the tile still "none yet". It is in brackets now, as `NEXT_NOTE` is, which
also makes SIF-54's check that the ended run reads "none" a real one: it passed whatever the tile said, and passes now
because the tile says "none". `export_check` 37 (on a real MOCK run: "at <n> evaluations used", or "none"). A probe run on
the code before (the five source files as at HEAD, restored after): the new or changed checks failed, 3 in
`run_control_check` ("at 4 evaluations", "at 1 evaluations", no tooltip), 3 in `training_tab_check` (no line, the old
tooltip) and 4 in `training_data_check`; the rest passed. Also run, unchanged: `dom_identity_check` 56, `run_list_check`
168, `looks_check` 76, `save_now_check` 29, `room_check` 31. 9 scripts, 797 checks, one lane: all passed the first time
but `run_control_check`'s "at 4" step above, which passed after the fix (with `training_tab_check` again, 113), and once
more alone, 167, after its picture of the tile (`run-2-first-feasible.png`) was framed on the run at a glance. No flakes.

### SIF-117 Counts are written one way, in groups of three from 10,000 up (2026-10-24; from the survey of 2026-10-23)

**Found.** For one model the RL model window's facts read "Training 800 evaluations, 6,024 learner updates, 760
transitions in replay", while the Training tab's head read "800 evaluations · 6024 learner updates" and Run status's
tile "Learner updates 6024": one number, written two ways (the survey's S10-2, pictures `05-bottom-training.png`,
`05-bottom-run-status.png` and `06-rl-model.png`). The model's facts (`RlModelWindow.tsx` `count`, branch record SIF-58)
and its network structure (`ModelStructure.tsx` `n`) grouped every count from 1,000 up with `toLocaleString('en-US')`;
everywhere else the page wrote counts as bare digits. So a model trained for 12,000 evaluations read "12,000" in those
two places and "12000" in the header's run chip, Run status, the Training tab and the Runs window. The warning on the
starting values, in the same window as the facts, wrote "1,500 evaluations" and "evaluation 1,000".

**Changed.** `frontend/src/format.ts`: `count(n)` writes a whole number from 10,000 up in groups of three with the en-US
separator ("12,000") and anything else as `String()` does ("6024"); one `Intl.NumberFormat` serves every call, as record
7.279 taught for dates. `plural()` writes its number with `count`, so every count with its noun follows: the questions
before a real or ngspice run starts, a save point "at 12,000 evaluations", the run chip's total, the Training tab's
Compare list, Data tables' rows, the Limits line's launches. The places that wrote a count of evaluations, learner
updates, launches, transitions or parameters as bare digits use `count` too, or `plural` where the words come out the
same (all under `frontend/src`, the panels in `panels/`): in `RlModelWindow.tsx` the facts' Training row (its `count` is
`plural` now, with "?" for a counter not recorded), and the warning reads "1500 evaluations" and "evaluation 1000"; in
`ModelStructure.tsx` every parameter count, in the summary, the section tables and the layer table; in `RunTabs.tsx`
(Run status) the evaluations used and the budget at a glance with those in flight and failed, the tiles' Spectre
launches, retries, cache hits, learner updates and first feasible design, and in the facts the Budget, Spectre launches,
Launch accounting and Learner updates rows, the first feasibility's completed and in-flight counts and Save now's "saved
at"; in `TrainingTab.tsx` the head's counts and the "Evaluations" key number, as a tile and in the table of several
runs; in `RunControl.tsx` the run chip's evaluations used, before its total ("12,345 of 20,000 evaluations"); in
`RunBrief.tsx` the card's count and its tooltip; in `ContinueForm.tsx` Used and Allows; in `launch.ts` the MOCK
question, the numbers of the question before a run goes on, the budget form's messages, "All N evaluations are used" and
the Next line's budget; in `RunList.tsx` (the Runs window) the Evaluations and First feasible columns, Details' Budget,
Spectre launches, Learner updates and First feasibility, and the evaluations in the history and in an offline model's
recorded runs; in `TaskList.tsx` the newest run's evaluations; in `ModelChooser.tsx` the Evaluations of the saved models
and of the save points, and the newer save point; in `page/runWindowActions.ts` the budget in New run like this's line;
in `rlModelText.ts` the model line's save point, the Next line's "@" and the folded line's budget; in `lineage.ts`
Started from's "@ 12,000"; in `RewardConditions.tsx` the launch cap; in `CornerCheck.tsx` the feasible evaluations and
designs. The plan named Run status and the Training tab beside the two windows; the run chip, the run brief, the Runs
and Tasks windows, the questions and the RL model window's other lines write the same counts, and `plural` alone would
have put "12345 of 20,000 evaluations" in the chip. Left as they are, since they are no counts: a number that names one
thing (an evaluation number - the Training tab's first passing design, the run brief's and the Tasks window's "first
feasible at evaluation N", which SIF-116 left for a later batch, a chart's axis and the line above it -, a dispatch
number, an update number, a seed, a save point's id), a quantity in its unit, and a number in a box one types into: the
Continue... form's field and its "more than 12000", and Output settings' warning, which quotes the two checkpoint
intervals as they were typed. No word changed: where a noun was fixed ("N evaluations") it stays fixed. Nothing here
starts, continues or stops a run, saves a task or writes to Virtuoso: the questions before a run ask as they did, with
the same numbers. `docs/workbench.md` (One way of writing a count, after One way of writing a quantity) and
`docs/functionality-reference.md` (its row) say it.

**Checked.** `tsc` clean. Every check script the runner runs (58; the three reward_v2/v21 ones are never run here), one
lane, in two batches after the memory guard. New assertions: `model_structure_check` 33 (31 before): the fixture's
summary reads "9021 trained parameters = actor 3018 + 2 critics x 3001 + 1" with no separator anywhere in the fold-out
(the section table "1544"), and the second save point's "17,973 trained parameters = actor 6002 + 2 critics x 5985 + 1"
and "2 target copies of the critics (11,970)"; its expected texts are built with the page's rule (they used
`toLocaleString`). `model_chooser_check` 122 (121): the model in use, whose newest save point now carries a long run's
counters (FIXTURE), reads "40 evaluations, 6024 learner updates, 12,000 transitions in replay". `run_control_check` 170
(167): Run status's "Learner updates" tile and row read "6024", then "96,000"; the first feasible design "at 12,001
evaluations used" and its row "(dispatch #12001, 11,998 completed, 3 in flight, 12,001 launches)"; at 12,3xx of 20,000
the run at a glance, the Budget row ("... remaining 76xx") and the header's run chip ("fixture_task · 12,3xx of 20,000
evaluations [MOCK]"). `run_list_check` 170 (168): a long run's Evaluations "12,345 / 20,000" and First feasible "at
10,240", and its Details' Budget, Spectre launches, "96,000" learner updates and First feasibility. `training_tab_check`
115 (113): "288 evaluations · 1792 learner updates" plain; the long run's "20,000 evaluations · 127,952 learner updates"
and its key number "20,000"; its pins "20000", "19010" and the compared table's "20000" read "20,000" and "19,010".
`reward_block_check` 34 (33): the warning's "1500 evaluations" and "evaluation 1000", no separator in it.
`run_control_live_check` 23: the header's chip on a real MOCK run reads "N of 20,000 evaluations" (its five pins said
20000). Also run, unchanged: `calibration_check` 48, `export_check` 37, `dom_identity_check` 56, `typing_check` 62,
`project_help_check` 61, `working_copy_check` 34, `launch_recovery_check` 20, `corner_check_check` 40, `task_list_check`
105, `looks_check` 76, `network_panel_check` 72, `save_now_check` 29, `task_run_check` 39, `room_check` 31,
`graph_view_check` 69, `encoder_models_check` 24, `mode_suggestion_check` 20, `agent_window_check` 33,
`connection_panel_check` 101, `virtuoso_source_check` 116, `task_save_check` 91, `testbench_probes_check` 41,
`output_panel_check` 98, `task_rows_check` 54, `spec_equations_check` 69, `find_fill_copy_check` 50, `sheet_check` 54,
`files_tab_check` 43, `calibration_save_check` 22, `consistency_check` 14, `blocking_issues_check` 62,
`ngspice_window_check` 43, `unsaved_rows_check` 25, `editor_columns_check` 29, `reliability_check` 20,
`module_fold_check` 30, `pdk_check` 44, `circuit_source_check` 17, `network_inputs_check` 9, `formula_bar_check` 21,
`matched_devices_check` 37, `training_data_check` 120, `crash_panel_check` 11, `edit_state_check` 28, `callouts_check`
8, `request_lifecycle_check` 25, `circuit_layout_check` 4, `editor_renames_check` 8, `graph_paint_check` 6,
`table_view_check` 10, `unit_text_check` 14. All passed the first time but `training_tab_check`, twice: first it did not
load (its new check declared a `hovered` the script already had), then its new check read the key number "3568" - the
key numbers follow the charts' frames, a moment after the counts line - and now waits for "20,000" (it also gave up
asserting the hovered evaluation, which nothing here changed); alone after that, 115. Reward and conditions' launch cap
is drawn only by the reward_v2 checks, which are not run. A probe run on the code before (the 17 source files as at
HEAD, restored after, their sums compared): `model_structure_check` failed 6 (the summary, its plain line, the target
copies, the section table's "1,544", the total row, the 17,973 line), `model_chooser_check` 1 ("6,024 learner updates"),
`run_control_check` 2 ("96000", "12353 / 20000"; its "6024" passes there too: Run status wrote it plain),
`run_list_check` its 2 and `reward_block_check` its 1 ("1,500"). That run's `run_list_check` also failed three checks of
the Runs window's first look - the pop-up showed without its styles ("New modelGraph Transformer", the dates not kept
whole, Seed not right-aligned) - and its `reward_block_check` lost its window after 24 checks ("the DevTools session
closed"); on the code after, `run_list_check`, `reward_block_check`, `model_chooser_check` and `model_structure_check`
passed again together (170, 34, 122, 33). `training_tab_check` and `run_control_live_check` were left out of the probe:
their changed pins wait a minute each for "20,000", which the code before never writes. No flakes on the code after.

**Review follow-up.** The review of 0b49f9c found one slip; it is real. Three counts of the run at a glance in Run
status, the total after "/", those in flight and those failed, were bare values, which React draws as nothing when the
status does not give one, and are `count(...)` now, which writes what is not a number as `String()` does: the word
"undefined". An offline-trained model's status gives its budget as the evaluations used and the launches alone
(`{charged: 0, launches: 0}`, `src/gator_workbench/offline_publish.py`, passed on as it is by `runs.status_view`), so
Show results on such a model in the Runs window read "0 / undefined" and "evaluations used · undefined in flight ·
undefined failed" (before SIF-117: "0 / " and blanks). That went against the plan's "non-numbers as today", and the
commit's other new counts drawn that way had their guard ("?" in the run brief, the Continue... form, the saved models
and the Runs window). No check gave a budget like that: `run_list_check` gives every run a whole one, and
`run_control_check`'s run working elsewhere, whose budget has two fields, is read only by its card.
`frontend/src/panels/RunTabs.tsx` now writes a count the status does not give as "?", as the run brief writes one: "0 /
?" and "evaluations used · ? in flight · ? failed". The evaluations used keep no guard: every status with a budget gives
them (`budget.py`'s snapshot and the offline publisher). Left as they are, since they wrote "undefined" for that model
before SIF-117 too (the value inside a string): the Spectre launches tile's retries and cache hits, the facts' Budget
and Spectre launches rows, and the Runs window's Details' Budget and Spectre launches. Nothing here starts, continues or
stops a run. `tsc` clean. `run_control_check` 171 (170): its live MOCK fixture run gives that budget of two counts for a
moment (`sim.budget`), and the run at a glance reads "0 / ?" and "evaluations used · ? in flight · ? failed". Also run,
unchanged: `export_check` 37, `run_list_check` 170, `room_check` 31, `looks_check` 76, `save_now_check` 29,
`calibration_check` 48 (seven scripts, one lane, after the memory guard), all passed the first time. A probe run on the
code before (`RunTabs.tsx` as at 0b49f9c, restored after, its sum compared) failed the new check alone (170 passed): "0
/ undefined | evaluations used · undefined in flight · undefined failed". No flakes.

### SIF-118 A note many rows share is said once, above the table (2026-10-24; from the survey of 2026-10-23)

**Found.** On the user's VCO (mscr_vco_lin_c) the Specs tab's Issues column read "warning The unit of a formula is not
checked" on six of its eight rows and "info New spec: models without it do not load" on seven: 13 lines of the same two
notes (the survey's S10-3, picture `02-tab-specs.png`). Each row listed every issue it had, one line each (SIF-5; SIF-74
had left the repeat as "not a defect"), so the column stopped being read, and a row's own problem would stand among the
repeats.

**Changed.** `frontend/src/panels/Editors.tsx`: in the table shown, an info or a warning in the same words - its level,
its code and what the column shows of it (`issueWords`: `ISSUE_HEAD`'s words, else the message's first clause, as
before) - on three rows or more (`SHARED_NOTE_ROWS`) is named once in a line above the table, after the Probes line and
the zero-floor hint, warnings first: on the VCO "On 6 rows: warning The unit of a formula is not checked" and "On 7 rows:
info New spec: models without it do not load". Its tooltip gives the whole message - the first row's, named ("For
f_center_hz: 'f_center_hz' is new to the result registry ..."), when the rows' messages differ, as the registry note names
its spec -, the code, the rows, and "Each of them shows "info" in its Issues cell, with its own words on hover." Those rows
keep the note's level word, in its colour, on one line after their own issues and in the line's order ("warning info");
each mark's tooltip is its row's own message and code, as its line's was, then "Said once above the table, for the 7 rows
that have it." A row's own issues stay whole and first: every error and blocker, a note fewer rows have, and a note whose
first clause names its row - with the transferable network inputs each Specs row says "The network reads inl1 as: ..."
(`docs/workbench.md`), which grouping by the words, not the code alone, keeps whole. Rows folded under a leader or out of
Find's view count too. Validation is unchanged, and the line is text, as the row lines are; the blocking-issues list, its
Where buttons and the tabs' red counts are about errors and blockers, which stay as they were. `frontend/src/roadster.css`
(SIF-118, after SIF-74's Issues rule): the line's notes side by side while they fit, at the column's 12.5 px in their
level's colour, "On N rows:" in the hint's grey; the marks on one line, 8 px apart, semi-bold. The marks are no line of
their own (`td.issues > .issue`), so SIF-5's 240 px minimum holds only while a row has words of its own: with marks alone
the column is as narrow as they are and the other columns take the room (147 px in the check's table, where it was 277).
One mark per note, not per level: a row with two shared infos reads "info info", told apart by their tooltips, and each
note keeps its own message and code where a hover finds it. `docs/workbench.md` (Tied rows, spreadsheet keys and a pasted
block: Column widths, and a new bullet after it) and `docs/functionality-reference.md` (the N blocking issues row, which
describes the Issues column) say it.

**Checked.** `tsc` clean. `spec_equations_check` 75 (69 before): new, two more formula rows beside score_sq - score_cube
without a lower limit, score_4 with one - give three rows the same three notes, and the line above the table reads "On 3
rows: warning The unit of a formula is not checked", "On 3 rows: info New spec: models without it do not load" and "On 3
rows: info The source of this spec is not recorded", in that order; the registry note's tooltip starts "For score_sq:
'score_sq' is new to the result registry the network reads" and names its code and the rows "score_sq, score_cube,
score_4", the basis note's (the same message on every row) starts with that message; each of the three rows shows
"warning info info", its own message and code on hover; score_cube's own error, "error constraint >= needs lower", stays
whole and first, and no other row has a line of its own (picture `spec_shared_notes.png`); with its lower limit typed the
column's minimum width is 0 and the marks keep one line; the two rows deleted, the line goes and score_sq's three notes are
whole again. Every check script the runner runs (58; the three reward_v2/v21 ones are never run here), one lane, after the
memory guard, 2854 checks, all passed the first time: `calibration_check` 48, `export_check` 37, `run_control_live_check`
23, `run_control_check` 171, `dom_identity_check` 56, `training_tab_check` 115, `connection_panel_check` 101,
`virtuoso_source_check` 116, `run_list_check` 170, `task_save_check` 91, `testbench_probes_check` 41, `output_panel_check`
98, `task_rows_check` 54, `spec_equations_check` 75, `model_chooser_check` 122, `typing_check` 62, `find_fill_copy_check`
50, `sheet_check` 54, `project_help_check` 61, `files_tab_check` 43, `working_copy_check` 34, `task_list_check` 105,
`launch_recovery_check` 20, `blocking_issues_check` 62, `corner_check_check` 40, `ngspice_window_check` 43, `looks_check`
76, `network_panel_check` 72, `save_now_check` 29, `task_run_check` 39, `unsaved_rows_check` 25, `calibration_save_check`
22, `editor_columns_check` 29, `reliability_check` 20, `room_check` 31, `graph_view_check` 69, `pdk_check` 44,
`reward_block_check` 34, `circuit_source_check` 17, `encoder_models_check` 24, `module_fold_check` 30, `formula_bar_check`
21, `matched_devices_check` 37, `model_structure_check` 33, `mode_suggestion_check` 20, `consistency_check` 14,
`training_data_check` 120, `agent_window_check` 33, `crash_panel_check` 11, `callouts_check` 8, `circuit_layout_check` 4,
`edit_state_check` 28, `request_lifecycle_check` 25, `editor_renames_check` 8, `graph_paint_check` 6,
`network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14. A probe run on the code before (`Editors.tsx` and
`roadster.css` as at HEAD, restored after, their sums compared) failed the five new checks of the line, its tooltip, the
marks, the error beside them (each of the three rows showed its three notes whole, score_cube's error among them) and the
column (277 px, its minimum 240 px); the sixth, on the two rows deleted, holds there too. After a comment in `Editors.tsx` changed, `spec_equations_check`
75 and `blocking_issues_check` 62 again. No flakes.

### SIF-119 At 1366 px the Parameters table keeps an instance path whole (2026-10-24; from the survey of 2026-10-23)

**Found.** On the user's VCO (mscr_vco_lin_c) at 1366 x 768 the Parameters table cut every Instance to "DUT/M..."
(DUT/MNA1, 8 characters) while ID ("wn_main") had about 140 px and the empty Tied to about 120; Notes was cut too (the
survey's S10-4, picture `12-page-1366.png`). An instance path is what a reader matches against the circuit. The survey
put it down to `TEXT_SIZE` (`cells.tsx`), which gave `instance_path` no natural size; measured, the minimum widths decide
it: at 1366 px the table stands at its columns' minimums - ID 140 px and Tied to 120 (record 7.180), each number 11
characters (SIF-31), the headings of Parameter, Optimized and Issues - and Instance had the 84 px of every text box, 64 px
for its text, where DUT/MNA1 takes 72 px in the cells' 14 px Segoe UI. A natural size alone changed nothing there
(Instance 91 -> 89 px). On a page like the user's, the rows scrolling beside a scroll bar (37 rows like the VCO's, the
tied ones open): Instance 87 px and every path cut, Notes 88, Tied to 122, ID 142; at 1680 x 1050 Instance 166 px and
Notes 209, cut.

**Changed.** `frontend/src/roadster.css` (SIF-119, after SIF-31's rule): an Instance box keeps at least 14 widths of "0"
and its padding (126 px), about 12 characters of a path - a path's capitals are wider than "0": DUT/XBUF/MP4 is 98 px, 13
widths. The room comes from Notes, which gives way first: its box has no minimum of its own now, so the column goes down
to its heading (58 px beside the scroll bar, 66 without; the formula bar shows a note whole), and from Tied to, whose
minimum is 110 px (record 7.180's 120): beside the scroll bar, Instance and Notes alone left the table 5 px wider than its
box, a sideways scroll the page did not have. 110 px still holds a leader's ID of about 12 characters, and the column is
empty on a leader's row. `frontend/src/panels/cells.tsx`: an instance path's natural size (`TEXT_SIZE`) is 14 characters
where a plain box has 20, about its minimum, so a wide window gives the room to Notes. `variable_id` was checked, as the
plan asked, and keeps the 20 of a plain box: at 1366 px the ID column stands at its 140 px minimum, which a natural size
does not change, and at 1680 px its 180 px cut nothing. Measured after: 1366 x 768 beside the scroll bar, Instance 127
px and nothing cut but Notes (58 px), Tied to 112, ID 142, no sideways scroll; the tied rows folded (no scroll bar),
Instance 128 and Notes 66; at 1100 px Instance 131 and Notes 104 (109, cutting the 12-character paths, and 122); at 1680
x 1050 Instance 140 and Notes 222. With the circuit shown, at 1680 px Instance 128 px (91 and cut before) and Notes 67,
and at 1366 px the table, which scrolled sideways before, scrolls 307 px (305). In Probes Notes gives way first too: at
1366 px Notes 166 -> 157 px, Expression 209 -> 214; at 1680 px nothing changed. Specs has none of these columns. The page
never scrolls sideways. Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso.
`docs/workbench.md` (Tied rows, spreadsheet keys and a pasted block: Column widths) and `docs/functionality-reference.md`
(the Tied rows, keys and pasting a block row) say it.

**Checked.** `tsc` clean. `editor_columns_check` 34 (29 before): new, the page opens again on rows like the VCO's
(FIXTURE: its leaders and their notes, four with seven tied rows each, paths of 6 to 12 characters - DUT/MNA1, DUT/R1,
DUT/I3/MNT12, DUT/XBUF/MP4) and opens their tied rows; at 1366 x 768, the 37 rows beside a scroll bar, every Instance is
whole and nothing else is cut but Notes, Notes is narrower than Instance, and neither the table nor the page scrolls
sideways (picture `parameters_1366.png`); at 1680 x 1050 the Instance box's natural size is 14, Notes is wider than
Instance, nothing is cut but Notes and nothing scrolls sideways. A probe run on the code before (`cells.tsx` and
`roadster.css` as at HEAD, restored after, their sums compared) failed the three new checks (Instance 87 px and every path
cut; at 1680 px the natural size 20, Instance 166 px); the set-up passed. Every check script the runner runs (58; the three
reward_v2/v21 ones are never run here), one lane, after the memory guard, 2858 checks passed: `calibration_check` 48,
`export_check` 37, `run_control_live_check` 23, `run_control_check` 171, `dom_identity_check` 56, `training_tab_check`
115, `connection_panel_check` 101, `virtuoso_source_check` 116, `run_list_check` 170, `task_save_check` 91,
`testbench_probes_check` 41, `output_panel_check` 98, `spec_equations_check` 75, `task_rows_check` 54,
`model_chooser_check` 122, `typing_check` 62, `find_fill_copy_check` 50, `sheet_check` 54, `project_help_check` 61,
`files_tab_check` 43, `working_copy_check` 34, `launch_recovery_check` 20, `corner_check_check` 40, `task_list_check` 104
of 105, `blocking_issues_check` 62, `callouts_check` 8, `ngspice_window_check` 43, `looks_check` 76,
`network_panel_check` 72, `save_now_check` 29, `task_run_check` 39, `unsaved_rows_check` 25, `calibration_save_check` 22,
`editor_columns_check` 34, `reliability_check` 20, `room_check` 31, `graph_view_check` 69, `pdk_check` 44,
`reward_block_check` 34, `circuit_source_check` 17, `encoder_models_check` 24, `module_fold_check` 30,
`crash_panel_check` 11, `formula_bar_check` 21, `matched_devices_check` 37, `model_structure_check` 33,
`mode_suggestion_check` 20, `consistency_check` 14, `training_data_check` 120, `agent_window_check` 33,
`edit_state_check` 28, `request_lifecycle_check` 25, `circuit_layout_check` 4, `editor_renames_check` 8,
`graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14. One flake:
`task_list_check`'s check of a renamed task's row failed once in the Tasks window, which has no editor table, the row's
text it printed being the expected "ota_relaxedinternal name fixture_ota"; alone, after the memory guard, it passed (105).
The widths above were measured with a temporary script, not kept.

### SIF-120 The line over a Training chart reads in the page's font and is never cut (2026-10-24; from the survey of 2026-10-23)

**Found.** On the user's VCO run at 1680 px the line over each Training chart read, in the dense monospace font of the
numbers, "Newest: Evaluation 800 · Training (recorded) 0.06274 · Training: mean of last 20 0.05706 · search · episo..."
(the survey's S10-5, picture `05-bottom-training.png`): words in a code font read slowly, and the line was cut at the
chart's width, so its end was lost - at 1366 px a value too (SIF-7 had put the values first; SIF-65 kept the mono font
so that the numbers would not jump about under a moving pointer). Measured while building it: where the line took two
lines, the legend over the plot had to give way to the plot's 110 px minimum, down to its own 18 px (styles.css), so
the second line ran over the top of the plot - by 7 px with two charts at 1366 px, by 43 px with eight; on the code
before, with eight charts at 1600 px, six of the cut one-line readouts already ran 9 px into their plots, where the line
stood on a row of its own under the keys.

**Changed.** `frontend/src/panels/TrainingChart.tsx`: the line is built of parts - the x, each series with its value, each
fact of the row ("search", "episode 1-000189 step 4") - each a `span.readout-part`, with " · " between them as before, so
its text is the same (every check reads it); the tooltip that repeated the whole line goes, as nothing is cut now. The
line keeps the most lines it has taken at its width, as a minimum height (`steady`), until its width or the chart's
series change: a row with fewer values (an episode start's one line beside a training row's two) does not shorten it
under a moving pointer, so the plot under it does not grow and shrink as the pointer crosses rows.
`frontend/src/roadster.css` (SIF-120, at the end; SIF-65's comment says so now): the line in the body font (12 px, as
SIF-65 set), every figure of one width (`tabular-nums`), so a value does not jump about under the pointer, what the mono
font did; it wraps instead of being cut, between its parts, each an inline box kept whole while it fits a line (a longer
one wraps inside its box), so a value never starts a line apart from its name; the series keys stand level with its
first line (centred, they sat between its two); the legend keeps all its lines (`flex: none`) and the plot gives way,
down to the 60 px in which a chart is still drawn (it was 110). Colours, weights and the order of the series are as
before. Measured: at 1600 px with two charts (and so at the user's 1680) the line fits on one line and nothing changed
(the plots 120 px); at 1366 px it takes two lines and the plots are 103 px (120 before, with the line cut), where the
Step reward chart of the check's run drew no y number ("-0.2" at 120 px) and Meets every hard spec kept its "0" and "1"
- a taller bottom panel (the splitter) gives them the room back; with eight charts at 1600 px the lines take two or three
lines and the plots are 67 to 87 px (at 1366 px down to 60, and the one chart whose line takes four lines ends 6 px below
its box). The cost of a frame of eight live charts stayed as it was (24 to 26 ms; 25.7 with the code before, 23 to 28 in
today's earlier runs). Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso.
`docs/workbench.md` (The Training tab: Hover) and `docs/functionality-reference.md` (the Training row) say it.

**Checked.** `tsc` clean. `training_tab_check` 120 (115 before; SIF-65's size check now asks for the body font and tabular
figures): new, at 1366 x 1000 the newest line takes two lines, every part whole, inside the line's box and above the
plot, the row's facts last ("· search · episode 0-000055 step 3") and the key level with its first line; "111111",
"000000" and "888888" as wide; hovered at 41 places across the plot (41 rows), nothing is cut, each part whole and
nothing over the plot; 8 of them were rows of one line, and the line kept its two, the plot its height (picture
`training-readout-1366.png`); with eight charts each chart's line is whole on its two or three lines, none over its
plot, every plot 60 px or more. A probe run on the code before (`TrainingChart.tsx` and `roadster.css` as at HEAD,
restored after, their sums compared) failed five of the six new checks (the mono font; the line cut to one line; the
hovered lines cut; no line wrapped to keep; with eight charts each line cut and six running 9 px into their plots);
the figures' check passes there too, as the mono font's figures were of one width as well. One lane, after the memory
guard: `training_tab_check` 120, `dom_identity_check` 56, `files_tab_check` 43, `corner_check_check` 40,
`looks_check` 76, `training_data_check` 120, in one run, all passed; no flakes. The plot heights and y numbers above
were measured with temporary scripts, not kept (one of them, a copy of `training_tab_check`, once counted three draws of
one chart within a second at its start, six in all, as every run of the check counts). After comments in `roadster.css`
and the check changed, `tsc` clean and `training_tab_check` 120 again.

**Review follow-up.** The review of 9203cb5 found two slips; both are real. (1) A chart could run out of its card onto
the chart below. A row's least height was a fixed 170 px (`grid-auto-rows: minmax(170px, 1fr)`, `styles.css`), so what a
chart holds never made its row taller; with the legend keeping all its lines (`flex: none`) and the plot stopping at 60
px, a legend taller than the card's room pushed the plot past the card's foot - "ends 6 px below its box" in "Changed"
above was this. Past 15 px (the card's 2 px padding and 1 px border, the 8 px gap, the next card's border and 3 px
padding) the plot reached the next row's title; the plot is positioned, as uPlot's canvas and overlay are, and the
title is not, so the upper chart's canvas was drawn over that title and × and took their clicks. Measured on the code
before, eight charts at 1366 x 1000 with a compared run (its name in the keys and in the line, as every compared run's
is): every card 170 px, seven plots at 60 px, four of them ending 29.4 px below their cards and three 12.6 px; at the
middle of the titles and × of charts 5, 6 and 8 the pointer found the canvas of charts 1, 2 and 4, whose x-axis labels
stood over those titles (chart 7's were clear: chart 3 ran 12.6 px out). The checks did not see it: the two charts at
1366 px stand in one row, and SIF-120's eight charts had no compared run and measured each plot against its legend, not
its card. `frontend/src/roadster.css` (after SIF-120's rules): a row is now as tall as its tallest chart needs, 170 px
at least (`grid-auto-rows: minmax(min-content, 1fr)`, the 170 px a chart's `min-height`), and the rows share any room
left as before, so where everything fits nothing changes. The same scene now: both rows 199 px, every plot inside its
card (60 to 93 px), the second row's titles and × found where they stand (picture `training-eight-compared-1366.png`).
The plot's 60 px floor and the legend's lines stay SIF-120's. (2) A legend key that switched a series off did not reset
`steady`: the line lost a part but kept its taller height, a blank line, and the plot did not get the room back until
the chart's width changed or another chart was chosen. `toggle` in `frontend/src/panels/TrainingChart.tsx` now resets
it before writing the line, and the comment where the height is kept says so. At 1366 px the newest line, two lines
with Training shown, takes one with it hidden and the plot grows from 103 to 119 px (before: two lines, one of them
blank, the plot 103); shown again, two lines. `docs/workbench.md` (The Training tab: Hover) and
`docs/functionality-reference.md` say both. Nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso. `tsc` clean. `training_tab_check` 123 (120): new, at 1366 px the key off and on again, and the eight charts
with a compared run; SIF-120's eight-chart check also asks that each plot end inside its card. A probe run on the code
before (`TrainingChart.tsx` and `roadster.css` as at 9203cb5, restored after, their sums compared) failed the two new
checks of the slips (121 passed); the key on again and the eight charts at 1600 px pass there too. One lane, after the
memory guard: `training_tab_check` 123, `dom_identity_check` 56, `files_tab_check` 43, `corner_check_check` 40,
`looks_check` 76, `training_data_check` 120, in one run, all passed the first time; no flakes.

### SIF-121 Rows that open on a double click open with Enter too: loaded PDKs, templates, corner checks, saved models (2026-10-24; from the survey of 2026-10-23)

**Found.** SIF-109 gave a run's row Enter, as SIF-100 had given a task's, and its record named what it left: four lists
still answered a double click alone (the survey's S10-6). The PDK window's loaded PDKs had no other way in, so a loaded
PDK could not be shown from the keyboard at all; nor could a run's earlier corner checks. A template in the RL model
window was taken by its Use template, but not from its row, and a saved model's newest save point only by the double
click (or its Details, then Use). None of these rows was in the Tab order. The page named the double click on a loaded
PDK's row (its tooltip and the hint under the list) and over the corner checks; on the templates and the saved models,
nowhere.

**Changed.** `frontend/src/panels/Pdk.tsx`: a loaded PDK's row is in the Tab order (`tabIndex` 0) and Enter on it shows
it, as the double click does (`show`, where the newest row asked answers); its tooltip reads "Double click, or Enter, to
show what was read", the hint "Double click a row, or press Enter on it, to show it." `frontend/src/panels/CornerCheck.tsx`:
an earlier check's row the same (`setCheckId`, which reads that check's status only), the hint "Double click a row, or
press Enter on it, to show that check." `frontend/src/panels/RlModelWindow.tsx`: a template's row takes Enter for `onUse`,
as its double click and Use template do (`chooseEncoder`: one Undo step; an edit still waiting is written into its own
template first, as before), and Use template's tooltip begins "Use template (also a double click on its row, or Enter on
it): ...", as Load run's names them since SIF-109. "No saved model is chosen yet" reads "... Use a save point below (a
model's newest: a double click on its row, or Enter on it); this window then closes.": the line that asks for a model,
where the page said neither, and Enter on a row would use one unannounced. `frontend/src/panels/ModelChooser.tsx`:
`chooseRow` holds what the double click did - in Fine-tune and Evaluate only the newest save point used (`useNewest`, one
Undo step; the window closes once it is read, and a save point that cannot be read leaves it open, with the reason), in
New model the Details opened - and a model's row takes Enter for it. As in the Runs window, Enter counts on the row itself
only: on a row's Details or Use template it presses that button alone, on the tick box nothing. `frontend/src/styles.css`:
the three new rows' focus ring is the run row's own rule (SIF-109's selector list: 2 px in the accent colour, inside the
row); a saved model's row is a `run-table`'s and had it already. Nothing here starts, continues or stops a run, saves a
task or writes to Virtuoso: each Enter does only what its row's double click did, with the same Undo step, the same
refusals and the same window closing; a PDK or a corner check shown is only read. `docs/workbench.md` (Corner check, New
model's Templates, Using one is a press, the PDK window) and `docs/functionality-reference.md` (PDK window..., Templates,
Saved models, Corner check) say it. `frontend/scripts/lib/harness.mjs`: `focusOn` (the focus put on an element as Tab
puts it, the window taken as focused by CDP focus emulation - a headless window need not be, and nothing in it then
matches `:focus-visible` -, and the element's tabIndex and ring as drawn) and `pressEnter`, for the four checks.

**Checked.** `tsc` clean. `pdk_check` 46 (44 before): new, with fixload shown, fixpdk's row holds the focus, is in the Tab
order and draws "solid 2px -2px", and its tooltip and the hint name Enter; Enter on it shows "fixpdk: 3 components" and
marks the row. `network_panel_check` 74 (72): with rgcn in use, the Graph Transformer row is in the Tab order with the
ring, and its Use template's tooltip names the row's double click and Enter; Enter on the row makes Graph Transformer the
template in use, with its values, nothing written. `corner_check_check` 42 (40): after the double click showed C0, C1's
row is in the Tab order with the ring and the hint names Enter; Enter shows C1, its status read, nothing started.
`model_chooser_check` 126 (122): in Fine-tune "No saved model is chosen yet" names the double click and Enter; with A in
use, Enter on a filler model's Details button opens its Details alone, A still in use and the window open; the row is in
the Tab order with the ring; Enter on the row pins its newest save point and closes the window. A probe run on the code
before (the five source files as at HEAD, restored after, their sums compared) failed the nine new checks of the rows'
Tab order, ring, words and Enter (279 passed); Enter on the Details button passes there too, as a button always took it.
One lane, after the memory guard: `pdk_check` 46, `network_panel_check` 74, `corner_check_check` 42,
`model_chooser_check` 126, all passed the first time; then those four again with `dom_identity_check` 56,
`run_list_check` 170, `task_list_check` 105, `reliability_check` 20, `graph_view_check` 69, `reward_block_check` 34,
`encoder_models_check` 24, `model_structure_check` 33 (12 scripts, 799 checks, one run), all passed the first time. No
flakes.

### SIF-122 A tick or a Details press in the Runs window draws only the rows it changes (2026-10-24; from the performance audit)

**Found.** While the Runs window was open, each tick, Details press, its "copied" note, sort, filter keystroke or folder
change drew every row of its table again (the performance audit's REN-1, confirmed): with the user's 549 runs some 15,000
to 38,000 React parts each time, more with every run made, and a Details press drew twice - as its Details opened, and
again when the run's status arrived. The memo of record 7.279 (`RunListButton`) kept the page's status polls out of the
window, not the window's own presses. Measured below with 549 runs: 9.7 ms of script per tick, 20 to 21 ms per Details
press.

**Changed.** `frontend/src/panels/RunList.tsx`: a run's row of the table is `RunRow`, memoised. Its props: the run; whether
it is the shown run, ticked, its Details open; its folder's name in All runs ('' elsewhere, where none is drawn); whether
its tick box is greyed out (the folders being read or saved); the run list's lookup that "Started from" reads; and one
ref, `rowAct`, through which its double click, Enter, tick, "Started from" link and Details reach the window's functions of
the latest render, as `latest` beside it does for the links from other windows. A row is drawn again only when one of them
changes: a tick draws its row, a Details press the rows whose Details open and close, the run's status arriving and the
"copied" none; a sort moves the rows without drawing them, a filter draws only the rows it brings in. The row's markup
moved over unchanged but for those props; its Details row stays where it was, in the parent, drawn with every render as
before. Not done, as the audit's verdict said: no deferred filter (the rows and "No run matches" would trail the input by
a render) and no change to the sorting (cheap). Nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso: every press calls the function it called, with the same questions and the same requests.
`docs/workbench.md` (The run window) and `docs/functionality-reference.md` (Runs...) say it.
`frontend/scripts/run_list_check.mjs`: the checks below; its run folders can hold a save back (`holdFolders`).

**Checked.** `tsc` clean. `run_list_check` 177 (170 before). New, section 3b, which rows React drew again, read from the
props it keeps on each row element (`__reactProps$...`; a row drawn again carries new ones): a tick draws only its row, a
Details press only that row (also once its status is read), another run's Details the two rows whose Details close and
open, the "copied" beside its run folder none. Two inputs a memoised row could miss: in 4c, the filter that lets the ticks
go unticks the box of a ticked row it still shows; in 5b, while a Move to... is saved (held back by the check) every row's
box is greyed out, and none once it is saved. A probe run of the new check on the build before failed exactly the four
draw checks (all six rows drawn again each time; 173 passed). One lane, after the memory guard: `run_control_check` 171,
`dom_identity_check` 56 (recording), `training_tab_check` 123, `run_list_check` 177, `task_list_check` 104 of 105,
`task_run_check` 39, `looks_check` 76, `reliability_check` 20. `task_list_check` failed "the row shows the new name with
the internal name under it, under the same key" - the Tasks window's rename: its row was read before the list the rename
reads again was drawn (the line's info, read a moment later, shows the expected text) - and passed 105 alone: a flake, in
code this record does not touch. DOM identity: `dom_identity_check` replayed that recording on the build before (the reference, 56 passed) and on
the build after with `--compare`: 53 of its 56 files identical byte for byte, every file of the runs scene (the window,
the Details, requests.txt, storage.json) and of the eight other scenes among them. The three others, of the tabs scene,
which never opens the window, differ in six lines: the sizes uPlot gives the second Training chart from its plot's height,
100 px against 101 (twice). That height is not this code's: the same build draws either - the tabs scene alone, three
times each, drew 101, 100, 101 px on the build before and 101, 101, 100 on the build after (two runs of the build before
differ in the same six lines), and the recordings of today's earlier records 100, 101 and 100 - since the chart keeps a
size within 1 px of the last it took (`TrainingChart.tsx`) and its readout's tallest height (SIF-120), so the order of
the page's first layouts decides it. With the same height the tabs scenes of the two builds are identical byte for byte
(two such pairs).

**Measured.** A throwaway check (`tmp-measure-runs_check.mjs`, deleted before this commit) run by `run_checks.sh --lanes 1
--build <dist>` on both builds (HEAD 1390ba6 and this change, each built into a temp folder) behind the scratch backend:
`/api/runs` answered with 549 canned runs shaped like the user's (seven tasks, five designs, fine-tunes of earlier runs,
baselines and calibrations, every state at rest), `/api/runs/status` for each, `/api/run-folders` empty. Headless Edge,
the Runs window 1500 x 860, no run shown. After a warm-up (four ticks, two Details presses) and a garbage collection, CDP
`Performance.getMetrics` (training_tab_check's `metrics()`) of the page and of the window before and after 20 ticks, then
10 Details presses (each opening a row's Details and closing the last one's), two frames after each action was drawn (a
press once its status was drawn), three rounds; per action, the median of the rounds. The window's script runs in the
page's realm, so the page's ScriptDuration holds it (the window's own: 0.01 to 0.03 ms per action); TaskDuration is the
renderer thread's (both sessions read the same). Also the page's own clock: performance.now() around a click and React's
flush. Meanwhile the page by itself took 0.2 to 0.5 ms of task time per second. Two runs of each build, before -> after:
a tick's script 9.71 and 9.67 ms -> 0.73 and 0.80 ms, its task time 16.2 and 16.1 -> 5.6 and 5.8 ms; a Details press's
script 20.1 and 20.9 -> 2.3 and 2.2 ms, its task time 70.0 and 71.8 -> 51.2 and 53.1 ms; by the page's clock a tick 9.3 and
9.5 -> 0.9 and 1.0 ms, a press's first drawing 10.0 and 10.2 -> 1.4 and 1.5 ms. What stays: a tick's other 5 ms of task
time (its style and layout 0.06 and 0.1 ms; the frame drawn), and a Details press's 12 ms of style and 8 to 10 ms of
layout, its Details laid into a table of 549 rows. The audit expected 20 to 50 ms per tick before; this machine took 9.7.

### SIF-123 Typing with the RL model window open draws none of its saved models' rows again, and a model's Details check waits 0.5 s (2026-10-24; from the performance audit)

**Found.** While the RL model window was open, each key typed in its own boxes - Name of the model it saves and the
Advanced numbers - or in an editor of the main page, and each tick, Details press or folder change in it, drew every row
of its saved models table again (the performance audit's REN-2, confirmed): `SavedModels` gets the page's configuration,
which only an open model's Details read, and every row ran its name splits and its "Started from" again - with the user's
411 saved models some 15,000 React parts each time by the audit's count, more with every run that saves a model.
Measured below with 411 models: 5.8 ms of script per key in Name of the model it saves, 10.1 to 10.5 ms per key in a
Parameters cell. And with a model's Details open, its check against the task on the page - a compile on the backend, on
the machine that runs the simulations - went 0.25 s after each edit (REN-10, confirmed), so at almost every pause in
typing: 12 checks for 12 keys typed 0.31 to 0.49 s apart. Record 7.275 had moved the model in use's own check to 0.5 s
for exactly that reason; this copy kept 0.25 s.

**Changed.** `frontend/src/panels/ModelChooser.tsx`: a saved model's row of the table is `ModelRow`, memoised, as a run's
row in the Runs window is since SIF-122. Its props: the model; whether it is the model in use, ticked, its Details open;
its folder's name in All models ('' elsewhere, where none is drawn); whether its tick box is greyed out (the folders being
read or saved); the run list's lookup that "Started from" reads; and one ref, `rowAct`, through which its double click,
Enter, tick and Details reach the window's functions of the latest render - `chooseRow` reads the Mode and the window at
the press, as it did, so the Mode needs no prop of its own. A row is drawn again only when one of them changes: a key
typed draws none, a tick its row, a Details press the rows whose Details open and close. The row's markup moved over
unchanged but for those props; its Details row stays where it was, in the parent, drawn with every render as before - the
one part of a model's row that reads the configuration. A model's Details check the task on the page 0.5 s after the last
edit (`delay: 500`, as useRlModel's check of the model in use): the same verdict, asked less often; the first one after
Details open, or after another save point is chosen, shows 0.25 s later than it did. Not done, as the audit's verdict
said: no deferred filter and no memoised sorting (about 1 to 2 ms). Nothing here starts, continues or stops a run, saves a
task or writes to Virtuoso: every press calls the function it called, with the same questions, Undo steps and requests;
only the Details' check is sent less often. `docs/workbench.md` (Choosing which saved model to load) and
`docs/functionality-reference.md` (Saved models) say it. `frontend/scripts/model_chooser_check.mjs`: the checks below;
the time each model request arrives (`at`), and a models' folder save that can be held back (`holdFolders`).

**Checked.** `tsc` clean. `model_chooser_check` 139 (126 before). New, which rows React drew again, read from the props
it keeps on each row element (`__reactProps$...`, as run_list_check since SIF-122): a key in Name of the model it saves
draws none, a tick only its row, a Details press only that row (also once its save point is checked), another model's
Details the two rows whose Details close and open, and an edit in a Parameters cell of the main page, with A's Details
open, none. That edit checks A again 0.5 s after it, never sooner: its save point read 506 ms and its check 510 ms after
the edit here (a timer is never early; the edit's time is taken before it is made, each request's as it arrives). Three
props a memoised row could miss: Undo of a Use, with the window open, takes its row's "in use" away and Redo brings it
back; while a Move to... is saved (held back by the check) every row's box is greyed out, and none once it is saved; the
moved model's row then names its folder in All models. A probe run of the new check on the build before failed exactly
the six draw and timing checks (all seven rows drawn again each time; the check after the edit at 255 and 256 ms; 133
passed). One lane, after the memory guard: `dom_identity_check` 56 (recording), `task_rows_check` 54,
`model_chooser_check` 139, `typing_check` 62, `network_panel_check` 74, `looks_check` 76, `reliability_check` 20,
`room_check` 31, `encoder_models_check` 24, `graph_view_check` 69, `module_fold_check` 30, `pdk_check` 46,
`reward_block_check` 34, `model_structure_check` 33, `mode_suggestion_check` 20, `network_inputs_check` 9 - every check
that opens the RL model window (16 scripts, 777 checks, one run) - all passed the first time. No flakes. DOM identity:
`dom_identity_check` replayed that recording on the build before (the reference, 12 passed) and on the build after with
`--compare`, scenes rl and rl-loaded, each drawing a saved model's row (rl-loaded's the model in use): all 12 files
identical byte for byte - each step's page and window, requests.txt and storage.json (24 passed). A first comparison,
into the folders SIF-122's proof had used, also compared three files of their tabs scene left there at 07:29 by that
proof (the uPlot height its record explains), so it was made again into fresh folders.

**Measured.** A throwaway check (`tmp-measure-models_check.mjs`, deleted before this commit) run by `run_checks.sh
--lanes 1 --build <dist>` on both builds (HEAD 507e20a and this change, each built into a temp folder) behind the scratch
backend: `/api/runs/models` answered with 411 canned saved models shaped like the user's (seven tasks, five designs, 1 to
10 save points, about a third fine-tuned from an older one), `/api/runs` with their runs, `/api/runs/model` for each.
Headless Edge, the RL model window 1180 x 920 in Fine-tune with a model in use, no Details open. After a warm-up and a
garbage collection, CDP `Performance.getMetrics` (training_tab_check's `metrics()`) of the page and of the window around
20 keys (`Input.dispatchKeyEvent`) in Name of the model it saves, then 20 in a Parameters cell of the main page
(alternately "5" and Backspace, so that each key changes the configuration), two frames after each key, three rounds;
per key, the median of the rounds. The window's script runs in the page's realm, so the page's ScriptDuration holds it
(the window's own: 0.01 ms per key); TaskDuration is the renderer thread's. Also the page's own clock: performance.now()
around an input event made in the page and React's flush. Two runs of each build, before -> after: a key in Name of the
model it saves 5.76 and 5.83 ms of script -> 1.84 and 1.93 ms, its task time 11.6 and 11.6 -> 6.6 and 6.8 ms, by the
page's clock 5.25 and 5.15 -> 1.5 and 1.5 ms; a key in the Parameters cell 10.1 and 10.5 ms of script -> 2.5 and 2.5 ms,
its task time 15.0 and 15.4 -> 5.9 and 6.0 ms, by the page's clock 5.15 and 5.2 -> 1.4 and 1.3 ms. Then another model's
Details open and 12 keys in the Parameters cell 0.3, 0.35, 0.4 and 0.45 s apart (the page saw gaps of 310 to 486 ms),
then 2.5 s: that model's save point read and checked 12 and 12 times -> once and once, in both runs; the model in use's
own check went once in both builds. What stays per key: the rest of the window and of the page drawn (1.3 to 1.5 ms by
the page's clock) and the frame. The audit expected 15 to 25 ms per key before; this machine took 5.8 and 10.

### SIF-124 The RL model window, opened again, shows its saved models at once: so since SIF-102, measured here (2026-10-24; from the performance audit)

**Found.** The performance audit's NET-1 (confirmed), its batch 3: each opening of the RL model window mounts the saved
models table anew - so do New model -> Fine-tune and each opening of New model's "Saved models, to look at" - and the
audit found it empty, "Reading the saved models..." and no row, for as long as `GET /api/runs/models` took: about 1 to 2 s
with the user's 411 saved models and 549 run folders on D: (about 1 MB of JSON), even when nothing had changed since the
last opening. Its plan: keep the last list at module level, keyed by the output folder and the run list's key, and show
it while the one read per opening goes. The audit read `ModelChooser.tsx` as it was at 0e8d941 (the review of SIF-80,
2026-10-22 00:13): its line numbers - the read at 156 to 159, the folders at 161, the list at 167, the notes at 194 to
199 - are that file's. SIF-102 (d099dfd and its review follow-up c91693d, the same morning) had done it already:
`useSavedModelsView` keeps the last list read, with the output folder it was read for, in `useRlModel`, and both of the
window's saved models tables take that view (`view={m.savedView}` in `RlModelWindow.tsx`: Fine-tune and Evaluate only,
and New model's fold). So each of those mounts shows the rows of the last read under the same output folder at once, and
its one read still goes and replaces them; `model_chooser_check` pins it since SIF-102 ("its rows are those of the last
read, shown at once, while its one read is still on its way"). Measured below with the read held 1.5 s: opened again,
the first row is there 44 ms after the press, drawn by the press's own update; 1.58 s with the kept rows switched off.

**Changed.** Nothing in the code: what the batch is for is there. Its plan's parts, against SIF-102's code: a
module-level copy would live no longer - `useRlModel` is mounted with Run configuration from the moment the page has
opened until it is left (`App.tsx`); a key with the run list's key (`runsKey`) would bring the empty table back at exactly
the openings after a run came, went, came to rest or a model was renamed, which show the kept rows at once since SIF-102
- it would undo part of it; a constant empty list (`NO_MODELS`) would keep nothing more stable - the kept rows are
`models` itself, the same array until the read answers, and an empty list is made only while no row is shown, where the
Design list's memo is over nothing; and, as the plan says, no read is skipped: one read per opening stays. One difference
from the plan stays as SIF-102 made it: when the last read under the output folder found no model, "No saved model yet
under this output folder" shows while the next read goes, as kept rows would; "The model in use is not in this list"
waits for the read (`!loading`), and the count says "Reading the saved models..." until it answers. Nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (Choosing which saved model to load:
the view kept, the rows of the last read shown while it is read again) and `docs/functionality-reference.md` (Saved
models) say it since SIF-102; this record is the only file changed.

**Checked.** `tsc` clean. `model_chooser_check` 139, five runs (the batch asked for five, to watch the two read counts
that kept rows could race), one lane, after the memory guard, on a build of HEAD 3311a27: all passed, each with "opening
it reads the list once", "Fine-tune reads the list once", "... its rows are those of the last read, shown at once, while
its one read is still on its way", "... and when it answers, the view stays, with no second read", "the list is not
re-read on a timer" and "Refresh list reads the list exactly once". No code changed, so no other check was run. No
flakes.

**Measured.** A throwaway check (`tmp-measure-reopen_check.mjs`) and build script (`tmp-measure-build.mjs`), both deleted
before this commit, run by `run_checks.sh --lanes 1 --build <dist>` on two builds of HEAD 3311a27, each built into a temp
folder: as it is, and with SIF-102's kept rows switched off by a transform at build time (`read?.models ?? null`: no row
until the window's own read answers, the window as the audit saw it; the source untouched). Behind the scratch backend:
`/api/runs/models` answered with 411 canned saved models shaped like the user's (seven tasks, five designs, 1 to 10 save
points - 2256 in all -, a third fine-tuned from an older one; 1.34 MB of JSON), each read held 1.5 s to stand in for the
walk of the run folders on D:; `/api/runs` with their runs, `/api/runs/model` for the model in use. Headless Edge,
Fine-tune with a model in use. The time is the page's own clock: `performance.now()` before the click on "RL model...",
and a MutationObserver on the window's document for the first `tr.model-row`. Per run, eight openings - the first, then
seven again, each closed once its read was answered and drawn - then, in the window, three rounds of New model's fold
opened and of New model -> Fine-tune with the fold closed. Two runs of each build, as it is -> kept rows off: the first
opening 1601 and 1605 ms -> 1601 and 1600 ms (no list read yet: no difference); opened again, median 45.7 and 43.9 ms
(min 43.3, max 48.7), drawn by the click's own update 7 of 7 -> median 1586 and 1578 ms (min 1565, max 1589); the fold
opened 11.4 and 10.9 ms -> 1539 and 1555 ms; New model -> Fine-tune 12.3 and 12.9 ms -> 1539 and 1557 ms. One read per
mount in every case, each answered and drawn; no console errors. What the 44 ms is: a new browser window, its style
sheets copied, and React drawing it with its 411 rows; the fold's and the Mode's 11 to 13 ms are the table alone. Two
runs of a first version of the check, which waited for the count's words only, gave the same: opened again, median 42.8
and 44.4 ms -> 1581 and 1584 ms. The batch expected about 1.5 s before and under 100 ms after.

### SIF-125 Typing no longer draws the Training tab again, nor a status answer its Compare list, and a live read draws it once (2026-10-24; from the performance audit)

**Found.** The performance audit's batch 4 (LEAK-2, NET-4 and LEAK-3, confirmed). The Training tab stays mounted while
another tab is shown or the panel is folded (hidden by a style, record 7.193), and the bottom panel takes the page's
configuration: so each key typed in the editors, and each answer of its validation, drew the whole tab again, hidden or
not - and with it its Compare list, made anew from the run list (an option per run: 548 with the user's 549 runs), and
each chart's list of choices, once per chart. Each status answer of a live run (every 1.5 s) did the same. And each 2 s
read of a live run drew the tab twice: as the read started, for a "busy" mark that nothing showed, and again as its
answer came. Measured below with 549 runs: about 0.4 ms of script per key went to the tab, shown or hidden, and a minute
of a live run took 68 ms of script where 41 do now. The audit read `TrainingTab.tsx` as it was at d19e4ad (the review of
SIF-77, 2026-10-21 23:27): its line numbers are that file's, and its Compare list the one list before SIF-105 grouped it.

**Changed.** `frontend/src/panels/TrainingTab.tsx`: the tab's body is `TrainingTabBody`, and `TrainingTab` is it
memoised (`memo`): drawn again only when one of its props changes - whether it is hidden, the run shown, that run's
status, the run list, which stays the same array until it changes (`page/shownRun.ts`). A key typed changes none of
them; all else the tab shows is its own state, and the unit forms its chart titles use are set before the panel is
first drawn (`App.tsx`). The Compare list - the select with SIF-105's "Same task (...)" and "Other tasks" groups, its
tooltip and its greying - is made in a `useMemo` over the run list, the shown run and the compared runs (`othersKey`,
which `others` goes with; `keepCompare` only sets the list and keeps it), above the tab's early return: a status answer
draws the tab, not the list. The choices in the charts' titles are one memoised list of elements (`chartOptions`), made
with the run's charts and shared by every chart's title. The read loop's `before` and the reading state's `busy` are
gone; the answer's own update (`done`) is as it was, so the counts line, "numbers read at" and its tooltip, the error
line and Retry read are drawn when they were. What the tab shows, reads and keeps is the same, and nothing here starts,
continues or stops a run, saves a task or writes to Virtuoso. Nothing of the batch was left out. `docs/workbench.md`
(The Training tab: When it reads, when it draws) and `docs/functionality-reference.md` (Training: Cost) say it.
`frontend/scripts/training_tab_check.mjs`: the checks below; a request of a given path can be held back and answered
later (`holding`, `release`).

**Checked.** `tsc` clean. `training_tab_check` 127 (123 before). New, with the run's status and its Training reads held
back - each poll waits for its answer - so that nothing else draws the page, read from the props React keeps on each
element (`__reactProps$...`, as run_list_check reads its rows since SIF-122; an element drawn with a handler made anew
carries new ones): a read of the live run draws the tab as its answer comes (the head's Add chart button carries new
props) and nothing as the next read starts; a key typed in a Parameters cell ("5" after its number, then Backspace)
draws the bottom panel again (its splitter) but neither the tab nor its Compare list; a status answer draws the tab but
not its Compare list. A probe run of the new check on the build before failed exactly these three (124 passed). One
lane, after the memory guard, on a build of this tree: `run_control_check` 171, `training_tab_check` 127,
`dom_identity_check` 56 (recording), `run_list_check` 177, `typing_check` 62, `files_tab_check` 43, `task_list_check`
105, `looks_check` 76, `task_run_check` 39, `reliability_check` 20, `room_check` 31, `matched_devices_check` 37,
`training_data_check` 120, `agent_window_check` 33, `calibration_check` 48, `export_check` 37, `run_control_live_check`
23 (17 scripts, 1205 checks, one run: every check that reads the bottom panel, where the tab is mounted, `typing_check`,
and `run_control_live_check`, whose live MOCK run the page follows), and `corner_check_check` 42 - all passed the first
time. One flake, before that run:
the first run of the new `training_tab_check` on the build after failed "a chart redraws at most once a second while
results arrive" - 6 redraws in its window, 3 of one chart within a second. Every run of both builds drew the same 6
there (3 per chart); the check allows 2 of a chart in any second, and once a frame drawn late put 3 in one. It passed in
the four runs since, one of them on the build before. DOM identity: `dom_identity_check` recorded against the scratch
backend (56 passed), replayed on the build before (the reference, 56 passed) and on the build after with `--compare`
(112 passed): all 56 files identical byte for byte - each step's page and window in the ten scenes, requests.txt and
storage.json - among them the tabs scene's Training tab with a compared run.

**Measured.** A throwaway check (`tmp-measure-training_check.mjs`) and build script (`tmp-measure-build.mjs`), both
deleted before this commit, run by `run_checks.sh --lanes 1 --build <dist>` on builds of HEAD 39e8e30 and of this
change, each built into a temp folder, behind the scratch backend: `/api/runs` answered with 549 canned runs shaped like
the user's (SIF-122's: seven tasks, five designs, fine-tunes, baselines and calibrations), the shown one - the newest - a
MOCK run of 400 evaluations and 2512 learner updates whose `/api/runs/status` and `/api/runs/training` are canned as
training_tab_check answers them; no run compared, so the Compare list held the other 548 (78 of its task, 470 of other
tasks). Headless Edge 1600 x 1100, the Training tab open with its two charts. After a garbage collection, CDP
`Performance.getMetrics` (training_tab_check's `metrics()`) around 20 keys (`Input.dispatchKeyEvent`: "5" after the
number of a Parameters cell, then Backspace, so that each key changes the configuration), two frames after each and
1.2 s after the last (its validation, 0.5 s on, answered), three rounds, per key the median; the same with Run status
shown and the Training tab hidden; the page's own clock - performance.now() around an input event made in the page and
React's flush - over 60 keys each; then, after a reload with the run's status turned live (a status answer every 1.5 s,
a Training read every 2 s, nothing new recorded) and 6 s to settle, 60 s measured. Two runs of each build, before ->
after: a key with the Training tab shown 2.01 and 2.05 ms of script -> 1.62 and 1.71 ms, its task time 5.23 and 5.37 ->
4.98 and 5.11 ms, by the page's clock 1.40 and 1.50 -> 1.10 and 1.10 ms; with the tab hidden 1.98 and 2.03 -> 1.62 and
1.53 ms of script, 5.18 and 5.11 -> 4.67 and 4.69 ms of task time, 1.40 and 1.50 -> 1.10 and 1.15 ms by the page's clock;
the live minute (40 status answers and 30 Training reads in every run) 68.7 and 67.7 ms of script -> 40.3 and 41.3 ms,
1.72 and 1.69 -> 1.01 and 1.03 ms per status answer with the reads' share, its task time 119.8 and 118.5 -> 84.5 and
90.1 ms, no style or layout work in either (nothing on screen changed). Drawings, counted on two more builds of the same
trees with a counter at the top of the tab's and of the bottom panel's body put in by a transform at build time (the
source untouched; one run each): per key the tab 1.1 -> 0 times, the bottom panel 1.1 and 1.1 (the keys and their
validation answers); in the live minute the tab 99 -> 68 times and the bottom panel 39 and 40, one per status answer, so
the tab's own drawings per read 2.00 -> 0.93 (28 for 30 reads: two answers were drawn in one render with a status
answer). What stays per key: the page and the bottom panel drawn (1.1 ms by the page's clock) and the frame; per status
answer the tab drawn once for its status, without its Compare list. The audit expected 0.5 to 1.5 ms less per key; this
machine gave 0.4.

### SIF-126 A live run chosen while the Training tab is shown has its history read once, not twice (2026-10-24; from the performance audit)

**Found.** The performance audit's batch 5 (NET-2, confirmed). With the Training tab shown, choosing a live run - in the
Runs window, by Show the header's run, by a task whose newest run it is - read the run's whole recorded history twice.
The tab's first read went out at once, before the run's status was in (the page lets go of the last run's status as the
shown run changes), so it went out as the read of a run at rest; the status, the cheaper read and so back first, then
made the run live, a change that let go of the read in the browser and started it again from cursor 0, nothing having
come in yet. The backend's handler finishes a request whatever the browser does, so it read the history twice, side by
side - up to 30,000 rows a page from the run's parquet parts, on D: of the machine that runs the simulations - and the
first chart waited for the second read, slowed by the first. Measured below with a live MOCK run of 2,000 to 2,750
evaluations: two reads from cursor 0 at every such choice, both served by the backend, and the first chart 402 ms after
Show results, where one read alone took 150 to 194 ms. A run at rest was read once, and is. The audit's line numbers are
those of the file before SIF-125 (the read at 189, its dependencies at 195, the run list's rows at 214: 198, 203 and 222
at d6bd2ce).

**Changed.** `frontend/src/panels/TrainingTab.tsx`: a run that the run list calls live (its row's state one of
`LIVE_STATES`, `runState.ts`) is first read once its status is in. The shown run's read starts when `ready` - this run's
status is in, or its read failed (`statusError`), or the list does not call the run live - and `ready` is one of the
read's dependencies; the run list's rows by folder (`rowOf`) moved up, above that read, which asks them (the names and
the Compare list read them as before). So such a run is read once, as live, one status answer after the choice. A run at
rest is read at once, as before, and so is a run the list does not have yet - after a reload that comes back on this tab,
before the list is in, a live run is still read twice -; a run whose status cannot be read is read once that failure is
in (a status read that never answers fails at its 30 s deadline). A stale row keeps the old order: a run that became live
after the last list read is read twice, as before; one the list still calls live after it ended waits one status answer,
then is read once (at once before). The read when a run ends (`live` turning false), the reads every 2 s, Retry read and
the compared runs' reads are as they were. `frontend/src/panels/BottomPanel.tsx`: the status read's error goes to the
tab. What the tab shows, reads and keeps is the same, and nothing here starts, continues or stops a run, saves a task or
writes to Virtuoso. `docs/workbench.md` (The Training tab: When it reads, when it draws) and
`docs/functionality-reference.md` (Training: Cost) say it. `frontend/scripts/training_tab_check.mjs`: the checks below;
a fixture run that the run list lists as running only for them (`fresh`, `listLive`: never as the page opens, so never
taken over), a status answer that fails (`statusFails`), and `release` takes a held request that the page has let go of
as no failure.

**Checked.** `tsc` clean. `training_tab_check` 131 (127 before). New, in its run window part, with the run's status and
its Training reads held back and let go one after the other, each request counted as it arrives, answered or not: a run
the run list calls live, chosen in the run window while on Training, is not read before its status is in (no Training
request while its status was held back), and then its history is asked for from cursor 0 once and drawn as live; a run
at rest is read at once (its history asked for while its status was still held back); a live one whose status cannot be
read (a 500) is read all the same. A probe run of the new check on the build before failed exactly the first two - a
Training request while the status was held back, then two from cursor 0 - and passed 129. One lane, after the memory
guard, on a build of this tree: `calibration_check` 48, `export_check` 37, `run_control_live_check` 23,
`run_control_check` 171, `training_tab_check` 131, `dom_identity_check` 56 (recording), `run_list_check` 177,
`typing_check` 62, `files_tab_check` 43, `task_list_check` 105, `calibration_save_check` 22, `looks_check` 76,
`task_run_check` 39, `reliability_check` 20, `room_check` 31, `matched_devices_check` 37, `agent_window_check` 33 (17
scripts, 1111 checks, one run: every check that reads the bottom panel, where the tab is mounted, but the reward checks
never run here, with `typing_check` and the three that start MOCK runs), then `corner_check_check` 42 (its name was
mistyped in that run) - all passed the first time. No flakes. A comment of `TrainingTab.tsx` was reworded during that
run: the builds before and after it are the same byte for byte (`index-VZ8c93gW.js`). DOM identity:
`dom_identity_check` replayed that recording on the build before (the reference, 56 passed) and on the build after with
`--compare`: 53 of its 56 files identical byte for byte, requests.txt and storage.json of every scene among them. The
three others, the tabs scene's Training, Corner check and Run status steps, differ in six lines each: the sizes uPlot
gives the second Training chart, 101 px high in the reference against 100, the height SIF-122 explains (the order of the
page's first layouts decides it). The tabs scene alone, three more times on each build, drew 100 px every time, and each
pair of the two builds was identical byte for byte (nine files each).

**Measured.** A throwaway script (`tmp-measure-livepick.mjs`) and build script (`tmp-measure-build.mjs`), both deleted
before this commit, on builds of HEAD d6bd2ce and of this change, each into a temp folder (HEAD's: the two files changed
built from their `git show` text by a load hook, the rest of the tree as it is). Behind a scratch backend started as
run_checks.sh starts one (its own settings and output folder on the WSL disk, the MOCK stand-in registered), a preview of
the build served by the script with /api proxied to it; headless Edge 1600 x 1000. In each run: a MOCK run of 24
evaluations to its end (the run at rest), then one of 20,000, concurrency 1, live, grown for 150 s and held by the
header; the page opened on it, the Training tab pressed with its status in; then eight rounds of the Runs window, the
live run's Details, Show results, 3 s (a 2 s read after the first answer, so that a second read from cursor 0 would be
in), and the run at rest the same way, 1.5 s; the live run stopped at the end. Counted with CDP Network on the page:
every `/api/runs/training` request with its cursor (`flushes`), when it was sent and how it ended (finished, or let go
by the page); every draw of a chart (`clearRect` on a `.training-plot` canvas) with the run its head names; the time from
the press - the page's clock, read in the window as it presses - to the first draw of the chosen run's chart; and the
backend's own log of what it served. Two runs of each build, interleaved, 16 rounds each, before -> after: the live run
read from cursor 0 twice in every round - the first read let go by the page 16 to 112 ms after the press, as its status
came back, and both served by the backend (its log: two per round) -> once in every round, none let go (its log: one per
round); its first chart 402 ms after the press (median; 326 to 452; per run 410 and 392) -> 200 ms (184 to 222; per run
205 and 199); the read that was drawn took 360 ms (median), beside the one let go, -> 178 ms; the status came back 30 ms
after the press (median; 14 to 110) -> 12 ms (10 to 17). The live run had 2,034 to 2,750 evaluations in the rounds before
(answers of 630 to 858 kB) and 2,000 to 2,553 after (620 to 794 kB); its whole history read alone, by the script with
nothing else asking, took 150 to 194 ms at 1,800 to 2,128 evaluations, a status read 4 to 10 ms. The run at rest, the
control: read from cursor 0 once in every round of both builds, its first chart 31 -> 30 ms after the press (medians).
Not measured: the user's D:, where each read takes longer. The batch expected 2 -> 1 and the first chart sooner by the
duplicate read's cost: 202 ms sooner here, about one read alone.

### SIF-127 Logs reads nothing while the bottom panel is folded (2026-10-24; from the performance audit)

**Found.** The performance audit's batch 6 (NET-3, confirmed). With the Logs tab chosen and a run live, the tab read the
run's newest 200 log entries every 2 s - from the tail of `logs/events.jsonl`, on the user's D: over 9p - also while the
bottom panel was folded to its tab line and none of it could be seen; and the panel folds by itself when a cell is
entered with little room (record 7.372), so the reads went on while the user typed. The Training tab reads nothing while
folded (record 7.193); Logs was given only the run and whether its worker lives. Measured below with a live MOCK run: 29
reads in the minute after a fold, of about 64 kB each - 29 of the page's 68 and 69 requests in that minute, where the
audit had put it at up to 40 % of the live traffic. The audit's line numbers are those of the tree at 0e8d941 (the
review of SIF-80, 2026-10-22 00:13), as SIF-124 found for its file: the read at `RunTabs.tsx` 316 and the tab at
`BottomPanel.tsx` 110 stood at 448 and 132 at HEAD 4927786.

**Changed.** `frontend/src/panels/BottomPanel.tsx`: `bodyHidden`, whether the fold puts the tab out of sight - folded,
in a window 1101 px or wider (`window.matchMedia('(min-width: 1101px)')`, the media query of the fold's rule in
`styles.css`, `.layout.bottom-folded .bottom-body { display: none }`). Below that width the stacked layout keeps the
body in view, folded or not (a fold kept in this browser from a wider window), and Logs reads on there: the audit's
verdict found that a gate on the fold alone would freeze a Logs tab in view. It is read as the panel is drawn, which a
live run's status answer does every 1.5 s, and only a live run's log is read on a timer, so a window resized across
1101 px is followed within one status answer. Logs gets it as `hidden`. `frontend/src/panels/RunTabs.tsx`: `LogsTabBody`
reads every 2 s while the worker lives and the tab is not folded out of sight (`alive && !hidden`). The fold changes the
interval, which `useRequest` takes up at once: one more read comes in (the one on its way, or one at once), then none;
opened again, it reads at once, then every 2 s. The read after the worker ends (`before`) is as it was, folded or not,
and a run at rest is read once, as before. What the tab shows is the same: folded, its lines are those of the last read,
out of sight; opened, the read at once brings them up to date. Not done, as the batch said: no gate on Corner check's
1.5 s poll of a running check (rarely usable now); the Training tab's own rule (folded at any width, record 7.193) is
untouched. Nothing here starts, continues or stops a run, saves a task or writes to Virtuoso.
`frontend/scripts/fixtures/request_lifecycle.tsx`: its Logs tab is given `hidden={false}` (the prop is required, so that
no caller leaves it out). `docs/workbench.md` (The page's look and layout: Logs reads nothing while the panel is folded)
and `docs/functionality-reference.md` (Splitter above the bottom panel, Logs) say it.
`frontend/scripts/training_tab_check.mjs`: the checks below; when each /api/runs/logs request came (`logReads`); the
splitter's Enter (`enter`) moved up, shared with the Training tab's fold part.

**Checked.** `tsc` clean. `training_tab_check` 135 (131 before). New, in its Logs part, with its canned live run and the
Logs tab chosen at 1600 px: folded with the splitter's Enter, no Logs read in the 4.5 s after the fold's own (1 as it
folded, 0 after; 2 in those 4.5 s before); opened again, a read within 1 s and another within 3 s; folded at 1000 px,
where the body stays in view, two reads or more in 4.5 s (the freeze the audit's verdict warned of). A probe run of the
new check on the build before failed exactly the first ("0 read(s) as it folded, 2 in the 4.5 s after"; 134 passed); its
"opened again" passed there by chance, a 2 s read falling within the second. One lane, after the memory guard, on the
build of this tree: `calibration_check` 48, `export_check` 37, `run_control_live_check` 23, `run_control_check` 171,
`training_tab_check` 135, `dom_identity_check` 56 (recording), `run_list_check` 177, `typing_check` 62,
`files_tab_check` 43, `task_list_check` 105, `looks_check` 76, `task_run_check` 39, `calibration_save_check` 22,
`reliability_check` 20, `room_check` 31, `matched_devices_check` 37, `agent_window_check` 33, `request_lifecycle_check`
25 (18 scripts, 1140 checks, one run: every check that shows the Logs tab or folds the panel, the others that read the
bottom panel as SIF-126 ran them, and the request_lifecycle fixture, whose Logs tab takes `hidden`), then
`corner_check_check` 42 (left out of that run by its name, as in SIF-126) - all passed the first time. No flakes. DOM
identity: `dom_identity_check` replayed that recording on the build before (the reference, 56 passed) and on the build
after with `--compare` (112 passed): all 56 files identical byte for byte - each step's page and window in the ten
scenes, requests.txt and storage.json - among them the tabs scene's Logs step, whose FIXTURE run at rest is read once in
both (no scene folds the panel).

**Measured.** A throwaway check (`tmp-measure-logs_check.mjs`) and its wrapper script in the session's scratchpad, both
deleted before this commit, on builds of HEAD 4927786 and of this change, each built into a temp folder. The wrapper
started a scratch backend as run_checks.sh starts one (its own settings and output folder, the MOCK stand-in registered,
never 8765); the check served the build with vite preview, /api proxied to that backend, started a MOCK run of 20,000
evaluations at concurrency 1 through the API (as export_check does) and stopped it at the end. Headless Edge
1680 x 1050, the page opened on the run - live, so the header took it, as it takes any live run - with the Logs tab
chosen; every /api request the page sent counted with CDP Network (`Network.requestWillBeSent`), the log answers' sizes
with `Network.loadingFinished`. In each run: A, 60 s with the panel open (the control); B, the 60 s from a real double
click on the splitter, folded; C, 60 s at 1000 px with the fold kept, the body in view; D, back at 1680 px, five rounds
of 3 s folded, then opened again by a double click: the time to the next /api/runs/logs request. Two runs of each build,
interleaved, before -> after: A 30 and 30 log reads -> 30 and 30; B 29 and 29 -> 1 and 1 - the read as it folded, in its
first second, and none in the 59 s after - and all of the page's /api requests in that minute 68 and 69 -> 41 and 41; C
29 and 30 -> 30 and 30; D, opened again, the next read 451 to 1834 ms after the double click (median 470 of 10: the 2 s
timer's next turn, which the rounds' even pace put between 451 and 500 ms in 8 of them) -> 10 to 23 ms (median 15). The
status reads of the shown run were 39 to 40 a minute in every phase of both builds. Each log answer of 200 entries was
63,694 bytes (the median in every run; at most 63,790; the smallest, 4.9 to 7.7 kB, early in the run): about 1.8 MB a
minute read folded before, 64 kB after. The run stood at 2,592 to 2,740 evaluations at the end of each run. Not
measured: the user's D:, where each tail read over 9p takes longer, and the user's runs, whose log entries are of other
sizes. The batch expected about 30 -> 1 folded, and about 30 before and after at 1000 px.

### SIF-128 The stylesheet keeps no rules for parts the page no longer draws (2026-10-24; from the performance audit)

**Found.** The performance audit's batch 7 (BUN-7, confirmed). `styles.css` held nine rules that match nothing the page
or a pop-up window draws, left over from the replaced looks and the old Project column: the grid of that column's two
window launchers (`.launchers`, and `> .row`, `.hint`, `button` and `p` under it, with their comment) - the launchers
left the column in record 7.362 for the Tasks window's New task buttons, and only `.connection-launcher` is drawn now -;
the brand's name and subtitle (`.tb-brand b`, `.tb-brand .tb-sub`) and the look switch (`button.look-switch`), gone in
record 7.360 (the brand holds only the GATOR chip, `GatorChip` in `App.tsx`; the switch went with the day look); and the
revision fact (`.tb-rev .tb-v`), which left the banner in record 7.372 (`TitleFacts`' cells are `tb-cell`, the RL
model's `tb-model` too). No .ts or .tsx file draws these classes or builds them in code: "launchers" stands in three
comments (`taskActions.ts`, `shared.ts`), the other three names nowhere outside the stylesheet. They told a reader of the
stylesheet of a subtitle, a switch and a grid that are not there, and each pop-up window, which copies the page's
stylesheet as it opens (`popupWindow.ts`), read them again. The audit's lines 272-276, 433-435 and 440 stood at 276-280,
444-446 and 451 at HEAD 9386d1d (rules added above them since).

**Changed.** `frontend/src/styles.css`: the nine rules and the launchers' comment deleted (9 lines, 24 declarations).
`.tb-brand`, `.tb-facts`, `.tb-cell`, `.tb-k` and `.tb-v` stay: the title block draws them (`App.tsx`, `Left.tsx`;
`roadster.css` sizes them). What the page shows, reads and writes is the same, and so is the computed style of every
element it and its windows draw (below); nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso. `frontend/scripts/looks_check.mjs`: one check (below), and its list of what it pins no longer has the title block
name the revision (its own check since record 7.372 says it does not). `docs/workbench.md` (The title block): its line of facts
no longer lists the saved task's revision, which left it in record 7.372, as the same document's banner list and its
list of record 7.372's changes say. `docs/functionality-reference.md` names none of these rules: unchanged.

**Checked.** `tsc` clean. `looks_check` 77 (76 before). New, after its checks that the look switch and the revision fact
are not drawn (both pass unchanged): no rule of the page's stylesheets, @media ones included, names the launchers grid,
the brand's text, the look switch or the revision fact. A probe run of the new check on the build before failed exactly
it, naming the nine selectors (76 passed). One lane, after the memory guard, on a build of this tree: `run_control_check`
171, `dom_identity_check` 56 (recording), `connection_panel_check` 101, `virtuoso_source_check` 116, `looks_check` 77,
`project_help_check` 61, `task_list_check` 105, `ngspice_window_check` 43, `room_check` 31, `circuit_source_check` 17
(10 scripts, 778 checks: the title block's readers and the checks around the old launchers' place) - all passed the
first time; `looks_check` again alone, 77, after its list of what it pins was reworded. No flakes. The batch's proof of the computed styles (plan-refactoring C11): `dom_identity_check` recorded
once against a scratch backend on the build before (56 passed), then replayed with `--styles --widths 1680,1000,640` on
the build before (the reference, 276 passed) and on the build after with `--compare` (552 passed): all 276 files
identical byte for byte - at each width, for each of the 36 steps of the ten scenes, the DOM and the computed style of
every element of the page and of each open pop-up window (108 style files: 92,643 elements and 558 ::before / ::after /
::backdrop boxes, 69 window sections, the title block in all 108), and each scene's requests.txt and storage.json.
`css_order_proof.mjs` on `styles.css` before and after, and with `--minified` on the two built stylesheets: as the batch
expected, it fails - it proves a regrouping, not a removal - and names as only in the old text exactly the 24
declarations of the nine rules (old lines 278-280, 444-446 and 451), nothing else lost, added or moved (1,759 atoms in
the old source, 2,470 in the old bundle).

**Measured.** `npx vite build` into a temp folder (the batch's measure), on HEAD 9386d1d and on this change: the
stylesheet `index-*.css` 68.84 kB (gzip 14.97 kB) -> 68.23 kB (gzip 14.84 kB), as Vite reports it; 68,848 -> 68,233
bytes, 615 fewer (0.9 %); with gzip -9, 14,847 -> 14,709. The source `styles.css` 71,550 -> 70,612 bytes (604 -> 595
lines). The batch expected about 1 kB off 65.17 kB (gzip 14.27 kB): records since the audit added rules, and the build
drops comments and spaces, so the nine rules weighed 0.6 kB there against 0.9 kB in the source, their comment included.
The script bundle is the same byte for byte (its name follows the stylesheet's hash), and so are the other chunks and
index.html but for the names. The batch's grep, `frontend/src` .ts and .tsx for `launchers`, `look-switch`, `tb-sub` and
`tb-rev`, before and after: no class use (`className`, `classList`, `class=`), the same three comments for "launchers",
nothing else; the stylesheets' lines naming them 7 -> 0. Not measured: the time a pop-up window takes to read 0.6 kB less
of the stylesheet it copies, under 1 % of the file and far inside the noise of a window opening, so no time is claimed.

### SIF-129 The stylesheet keeps no value that the look always overrides (2026-10-24; from the performance audit)

**Found.** The performance audit's batch 8 (BUN-8, confirmed). `styles.css` still held values of the look before record
7.360 that `roadster.css` always overrides - the same selector and the same property there, at top level or in the same
@media, in the stylesheet the page loads after it (`main.tsx`; each pop-up window copies the two in that order,
`popupWindow.ts`): the headings' 11.5 px grey capitals (`h3`; 15 px white in sentence case on the page), the labels' and
the hints' 11.5 px (13 px), the padding of the fields, the buttons and the icon buttons, the borders and padding of the
header, the message line, the panels and the bottom panel, the tab strips' and the table cells' padding, the formula bar's
name box, the header's Next line and run chip, the links' red (white since record 7.372), and from 1101 px a 19 px margin
round the page (`@media (min-width: 1101px) { .layout { padding: 19px } }`, which `roadster.css`'s `.layout { padding:
12px 16px }`, written at top level, beats at every width). None of them ever applied: an edit of one changed nothing on
the page or in a window, and each window read them again as it opened. The audit counted 118 such declarations and 2 more,
`table.editor th.sel, table.editor td.sel { padding: 0 3px; text-align: center }`, overridden for td.sel only; its line
numbers fit `styles.css` at acd9fae (branch record SIF-82, 2026-10-22). The batch's scan (a throwaway script, deleted
before this commit: each `styles.css` declaration, its selector list split, paired with the `roadster.css` atoms of the
same normalised selector and property, at top level or in the same @media chain; counted when every selector of the list
has one whose value this browser takes, never an !important one) gives exactly 118 and 2 on that tree. On HEAD 76ff39c it
gives 127 and none partial: the 118, each still there and still overridden, between 1 line above and 6 below the audit's,
and 9 values that later records overrode in `roadster.css` instead of changing them here - the "copied" word's size (SIF-94),
the blocking list head's alignment (SIF-112), Tied to's width (SIF-119), and the Training charts' row and chart heights,
the keys' alignment, the readout's font and wrapping and the plot's height (SIF-120 and its review). The th.sel / td.sel
pair is no longer partial: since branch record SIF-96 `roadster.css` styles both cells (`table.editor :is(td, th).sel`,
of the same specificity), which a scan by selector text does not pair (Left, below).

**Changed.** `frontend/src/styles.css`: the 127 declarations deleted, and the 15 rules they left empty - `h3`,
`button:hover:not(:disabled)`, `table.editor td`, Tied to's width, `.toolbar button.text`, `.issue`, `details a`, a
working run chip's colour, the Runs button's hover, `.sort-mark`, `table.run-table td .hint`, Save as' border on the tab
line, the chosen editor tab's colour, `.task-list-current .task-list-mark` and the 1101 px margin's @media block.
Comments that named what went: the header's ("the last two win", of two paddings that went), the content-sized columns'
(a leader's name: `roadster.css`, SIF-119), the Runs table's Details link (its same room: `roadster.css`), the
Components row's (its height: `roadster.css`, SIF-31) and each editor's colour (its table head; its tab until record
7.360); the file's head says no such value stands here. `frontend/src/roadster.css`, comments only: its head says a
`styles.css` value it overrides goes from there; two comments that named a value gone say "kept" and "the old look's".
No selector or class name leaves the two stylesheets (each rule deleted has its winner in `roadster.css`: 882 selectors
and 438 class names before and after). What the page shows, reads and writes is the same, and so is the computed style of
every element it and its windows draw (below); nothing here starts, continues or stops a run, saves a task or writes to
Virtuoso. `frontend/scripts/looks_check.mjs`: one check (below). `docs/workbench.md` (Colours by name) says it;
`docs/functionality-reference.md` names no stylesheet value: unchanged. Left, as outside the batch's scan, which pairs a
property by its name and a selector by its text: 14 more values that never apply either - 12 under a `roadster.css`
shorthand of the same selector (the header's `border-width: 1.5px` under `border: none`, its Connection button's
`border-left`, that button's state word's `font-size: 9.5px` under `font`, `table.grid th`'s `font-weight: 400` and
`font-family` under `font: 500 13px/1.4 ...`, the run chip's `font-family`, the Runs button's `border-bottom`,
`.tb-brand`'s `padding-right`, the tab strips' 1.5 px lines - `.tabs`, its tabs and the chosen one - and the task chip
key's `font-size: 12px` under `font: inherit`) and the th.sel / td.sel pair, which the batch kept for th.sel. A follow-up
can take them with the same proofs.

**Checked.** `tsc` clean. `looks_check` 78 (77 before). New, after SIF-128's: the stylesheets as the page loaded them
(fetched, and parsed as `css_order_proof.mjs` parses them) hold no value that a later rule for the same selector and
property overrides at top level or in the same @media, the later value one this browser takes (`CSS.supports`); a rule's
own second value for a property is its fallback (the message line's close mark, SIF-56) and is not counted. A probe run
of the new check on the build before failed exactly it, naming 125 values among 2,598 atoms (77 passed): the build had
already left out 2 of the 127 - the header's first padding, overridden inside its own rule, and `table.editor td {
padding: 0 }`, written the same in `roadster.css` -; on this change, 0 among 2,467. One lane, after the memory guard, on a
build of this tree: `calibration_check` 48, `export_check` 37, `run_control_live_check` 23, `run_control_check` 171,
`training_tab_check` 135, `dom_identity_check` 56 (recording), `connection_panel_check` 101, `run_list_check` 177,
`virtuoso_source_check` 116, `task_save_check` 91, `testbench_probes_check` 41, `model_chooser_check` 139,
`output_panel_check` 98, `spec_equations_check` 75, `task_rows_check` 54, `typing_check` 62, `find_fill_copy_check` 50,
`sheet_check` 54, `project_help_check` 61, `files_tab_check` 43, `working_copy_check` 34, `launch_recovery_check` 20,
`blocking_issues_check` 62, `corner_check_check` 42, `task_list_check` 105, `looks_check` 78, `network_panel_check` 74,
`ngspice_window_check` 43, `calibration_save_check` 22, `save_now_check` 29, `task_run_check` 39, `unsaved_rows_check`
25, `editor_columns_check` 34, `pdk_check` 46, `reliability_check` 20, `room_check` 31, `graph_view_check` 69,
`reward_block_check` 34, `circuit_source_check` 17, `encoder_models_check` 24, `module_fold_check` 30,
`formula_bar_check` 21, `matched_devices_check` 37, `model_structure_check` 33, `mode_suggestion_check` 20,
`agent_window_check` 33, `consistency_check` 14, `training_data_check` 120, `crash_panel_check` 11, `edit_state_check`
28, `callouts_check` 8, `circuit_layout_check` 4, `request_lifecycle_check` 25, `editor_renames_check` 8,
`graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14 (58 scripts, 2,911 checks,
one run of 1,195 s: every check but the three reward_v2 ones, as the change touches the base rules of every screen) - all
passed the first time. The batch's proofs: `dom_identity_check` recorded once against a scratch backend on the build
before (56 passed), then replayed with `--styles --widths 1680,1000,640` on the build before (the reference, 276 passed)
and on the build after with `--compare` (551 of 552 passed): every style file identical byte for byte - at each width,
for each of the 36 steps of the ten scenes, the computed style of every element of the page and of each open pop-up
window (108 files: 92,643 elements and 558 ::before / ::after / ::backdrop boxes, 69 window sections, the editors' th.sel
in all 108) - and every DOM file and storage.json. One requests.txt (640 px, rl-loaded, its first step) differed by a line
the check itself writes, "ERROR Fetch.fulfillRequest: Invalid InterceptionId" (the harness answering a request already
gone), the page's ten requests the same; that scene replayed alone at the three widths was identical in all 24 files: a
flake of the harness. `css_order_proof.mjs --minified` on the two built stylesheets: as the batch expected, it names as
only in the old one exactly `@media (min-width: 1101px) .layout { padding: 19px }`, cleared above by hand (the top-level
`.layout` padding of `roadster.css` comes later at the same specificity), and nothing else lost, added or moved (2,446
atoms; 150 atoms that a later atom of the same selector overrides dropped from the old side first, 20 from the new); the
same on the source texts of the two stylesheets one after the other (2,370 atoms; 147 and 15).

**Measured.** `npx vite build` into a temp folder (the batch's measure), on HEAD 76ff39c and on this change: the
stylesheet `index-*.css` 68.23 kB (gzip 14.84 kB) -> 65.49 kB (gzip 14.47 kB), as Vite reports it; 68,233 -> 65,496
bytes, 2,737 fewer (4.0 %); with `gzip -9 -n`, 14,690 -> 14,461. The source `styles.css` 70,612 -> 67,881 bytes (595 ->
593 lines, the comments added included). The script bundle is the same byte for byte (its name follows the stylesheet's
hash), and so are the other chunks and index.html but for the names. The batch's scan, before -> after: 127 declarations
(133 atoms) always overridden and 0 partial -> 0 and 0; beside it the same 2 through `:is(td, th).sel` and the same 12
under a shorthand (Left, above). The batch expected about 4.7 kB off 65.17 kB (gzip 14.27 kB), and the scan's 2 partial
ones kept: records since the audit added rules, SIF-96 took the pair out of the scan (both its cells overridden through
`:is()` since), and the values weigh 2.7 kB in the built file, which drops their spaces and had left out 2 of them
already. Not measured: the time a page or a pop-up window takes to read 2.7 kB less of the stylesheet it parses, 4 % of
the file and far inside the noise of a page load or a window opening, so no time is claimed.

### SIF-130 Placeholders read at 4.5 : 1 or more on the dark fields (2026-10-24; from the survey of 2026-10-24)

**Found.** The survey's contrast measurement (S11-2: `contrast.mjs`, the WCAG ratio of every visible text on 14 screens of
the branch build with real data, against the background it sits on) found one kind of text under 4.5 : 1 that a user
needs: placeholders. The page set no colour for them, and the browser's own #757575 read at 3.85 : 1 in a field
(#18181b): "Find rows" on every tab, the Filter boxes of the Runs window, the saved models and Output files, and the
formula bar's "Click a cell to see and edit its whole value here", the bar's instruction while no cell is chosen; and at
4.06 : 1 on a zebra row (#121215): an empty Specs bound's "no limit", which is information, not decoration. The only other
texts under the bar were the disabled Clear (Runs) and Revert (task file) buttons, 4.19 : 1, which WCAG exempts: left as
they are. Checking the batch's colour against every ground a placeholder is drawn on found one more place: a changed
cell's amber (`--unsaved-cell`, record 7.222), where a bound cleared in a saved task says "no limit" - 2.95 : 1 in the
browser's grey, and still 4.22 : 1 in the batch's (4.18 in the grey chosen below).

**Changed.** `frontend/src/roadster.css` (SIF-130, at the end): `::placeholder` in the look's dim grey #8e8e96 - the
colour of the run state's unlit words and a key number's unit, so the page gets no new grey (the survey proposed #8f8f94,
5.50 : 1, a shade away) - at full opacity (Firefox draws placeholders at 0.54 of their colour unless told): 5.45 : 1 in a
field, 5.76 in a disabled one, 5.75 on a zebra row, 5.93 on the editors' card, 5.18 on a row not saved, 5.33 on a new
row, 5.82 on an error row; darker than a hint (`--muted`) and than the typed text, so it still reads as a placeholder. In
a changed cell (`table.editor tr.unsaved-changed > td.unsaved-cell`, the selector that gives it its amber) the
placeholder takes the hint's grey, 5.81 : 1. Only the colour of an empty box's words changes; nothing moves. What the page
shows, reads, writes, asks and stores is the same; nothing starts, continues or stops a run, saves a task or writes to
Virtuoso. `docs/workbench.md` (a paragraph "Placeholders that read" after the drop-down lists') and
`docs/functionality-reference.md` (the page's look row) say it.

**Checked.** `tsc` clean. `looks_check` 81 (78 before): new, with the Specs tab shown every placeholder in view is
measured on the ground it is drawn on - the backgrounds under it laid over each other from the root down, as the survey's
script measured - and reads at 4.5 : 1 or more: "Find rows" 5.45, the formula bar's instruction 5.45, the starter Spec's
"no limit" 5.93 (its card); each is darker than a hint; and the Runs window's Filter box, 5.45. `unsaved_rows_check` 28
(25 before): new, the Spec row not saved shows "no limit" in its empty Upper at 5.18 : 1 on the row's tint, its box with
no colour of its own; its Lower cleared - a bound the saved task holds - says "no limit" in the changed cell in the hint's
grey, 5.81 : 1, once validation names the cell changed (picture `unsaved-rows-specs-cleared.png`); Undo brings the bound
back, and the Spec validated next is the one before. Its Specs picture is taken before that, as it was. The measured
colour is the one drawn: in `looks_check`'s picture the brightest pixels of "Find rows" and of the formula bar's words
are (142, 142, 150), #8e8e96, on the field's (24, 24, 27). One lane, after the memory guard, on a build of this tree:
`connection_panel_check` 101, `run_list_check` 177, `model_chooser_check` 139, `output_panel_check` 98,
`task_rows_check` 54, `spec_equations_check` 75, `typing_check` 62, `find_fill_copy_check` 50, `sheet_check` 54,
`files_tab_check` 43, `unsaved_rows_check` 28, `blocking_issues_check` 62, `task_list_check` 105, `looks_check` 81,
`ngspice_window_check` 43, `editor_columns_check` 34, `task_run_check` 39, `pdk_check` 46, `formula_bar_check` 21 (19
scripts, 1,312 checks: the two changed and every check that renders a box with a placeholder - Find rows, the formula
bar, the Specs bounds, the windows' Filter boxes, the Connection, PDK, ngspice and Output settings fields) - all passed
the first time, no flake. Two comment-only edits (`roadster.css`, `looks_check.mjs`) came after that build;
`looks_check` 81 and `unsaved_rows_check` 28 again on the final tree.

### SIF-131 The Parameters ID is as wide as its values, and at 1366 px the table no longer scrolls sideways (2026-10-24; from the survey of 2026-10-24)

**Found.** On the user's VCO (mscr_vco_lin_c) at 1366 x 768 the Parameters table still needed a sideways scroll bar a
few px wide after SIF-119, with the Matched devices box open and the rows scrolling beside a scroll bar; at 1680 x 1050
with the circuit shown, Notes had about 60 px ("main...", "auxili...") while ID had about 140 px for IDs of 7 characters
and the empty Tied to about 115 (the survey's S11-1, pictures `12-page-1366.png` and `03-circuit-shown.png`). The survey
put it down to `TEXT_SIZE` (`cells.tsx`), which has no entry for `variable_id`, so that the ID box kept the 20
characters of a plain box, and to SIF-119's fixture, which had no follower count of two figures. Measured on rows made
like the VCO's (the check's, below) on the code before: the VCO's leaders count their tied rows up to "▸31" beside their
tick box, where SIF-119's fixture counted "▸7", and the tick box's column grows to 62 px to hold it. At 1366 px the
table stands at its columns' minimums - ID at record 7.180's 140 px (141 with its line), Instance 127, Tied to 111,
Notes 55, beside the 15 px scroll bar - and was 2 px wider than its box, the tied rows folded under the Matched devices
box or open. At 1680 x 1050 ID had 183 px, Tied to 175 (a leader's ID on a tied row, empty on a leader's), Instance 140,
Notes 218; with the circuit shown ID 141, Tied to 111 and Notes 55, the width of its heading.

**Changed.** `frontend/src/roadster.css` (SIF-131, after SIF-119's rules): a Parameters ID keeps 12 widths of "0" -
about 12 characters, as Tied to's 110 px holds a leader's ID - and the 16 px a tied row's ID is indented by:
`calc(12ch + 26px)`, 117 px, where it kept 140. Probes and Specs keep their 140 px (a Probe ID such as m_supply_power_w
is longer). `frontend/src/styles.css`: the Parameters ID leaves record 7.180's 140 px rule, since a `styles.css` value
that `roadster.css` overrides goes from there (SIF-129); its comment says where the ID's width is now.
`frontend/src/panels/cells.tsx`: `TEXT_SIZE` gives `variable_id` and `binding_group` (Tied to, which holds a leader's
ID) a natural size of 12, about their minimum, where a plain box has 20, so that a wider window gives the room to Notes.
Measured after: at 1366 x 768 with the Matched devices box open over the folded rows, ID 118 px, Instance 128, Tied to
112, Notes 70 and no sideways scroll; the tied rows open (70 rows), ID 119 and the rest the same; IDs of 12 characters
whole, a tied row's indented one too, and paths of 12. At 1680 x 1050 ID 144 px, Tied to 137, Instance 151, Notes 248;
with the circuit shown ID 119, Tied to 113, Instance 128 and Notes 71 (55 before). The page never scrolls sideways. Only
column widths change: what each cell shows, and what the page reads, writes and asks, is the same; nothing starts,
continues or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (Tied rows, spreadsheet keys and a
pasted block: Column widths) and `docs/functionality-reference.md` (the Tied rows, keys and pasting a block row) say it.
Left, with why: the finding's "let Tied to keep its 110 px only where it holds a value, if that can be done without a
layout jump" - only a tied row holds one, so each time a leader's tied rows opened or folded the column would move
between its heading's width and 110 px, and every column after it with it: the jump the finding rules out. Tied to's
natural size of 12 (above) gives Notes the room in a wider window instead. And the plan's "the ID cell keeps room for
the follower expander": the "▸31" button is in the tick box's column, which grows to hold it; the ID cell's own extra is
a tied row's indent, which its 117 px holds.

**Checked.** `tsc` clean. `editor_columns_check` 40 (34 before). Its rows like the VCO's are made as the user's are
now - the four widths with seven tied rows each and the length `l` with 31 (`l_f1` ... `l_f31`, so that a leader counts
"▸31"), and two leaders more for IDs of 12 characters, one of them with a tied row (`wn_tail_bias`, `wn_mirror_f1`): 70
rows - and Matched devices is answered with the VCO's eight cross-coupled pairs, each already tied (FIXTURE: nothing can
be applied). New: at 1366 x 768 as the user had it - the tied rows folded, a leader counting "▸31", the Matched devices
box open, the rows beside a scroll bar - neither the table nor the page scrolls sideways and nothing is cut but Notes
(picture `parameters_matched_1366.png`); with the box closed and the tied rows open the longest ID has 12 characters, a
tied row's too, and every ID and Instance is whole; at 1680 x 1050 the ID and Tied to boxes have their natural 12
characters and neither column is wider than Instance; with the circuit shown nothing is cut but Notes, nothing scrolls
sideways and the ID is no wider than Instance. A probe run of the final check on the code before (`cells.tsx`,
`roadster.css` and `styles.css` as at HEAD, restored after, their sums compared) failed four checks - the table 2 px too
wide with the box open and with it closed (SIF-119's check, on these rows), the natural sizes 20 (ID 183 px, Tied to
175), and with the circuit shown ID 141 px beside Instance's 127 - and passed the set-ups. Every check script the runner
runs (58; the three reward_v2/v21 ones are never run here), one lane, after the memory guard, on a build of this tree:
2923 checks passed the first time, no flake - `calibration_check` 48, `export_check` 37, `run_control_live_check` 23,
`run_control_check` 171, `training_tab_check` 135, `dom_identity_check` 56, `connection_panel_check` 101,
`virtuoso_source_check` 116, `run_list_check` 177, `task_save_check` 91, `testbench_probes_check` 41,
`model_chooser_check` 139, `output_panel_check` 98, `spec_equations_check` 75, `task_rows_check` 54, `typing_check` 62,
`find_fill_copy_check` 50, `sheet_check` 54, `project_help_check` 61, `files_tab_check` 43, `launch_recovery_check` 20,
`working_copy_check` 34, `corner_check_check` 42, `task_list_check` 105, `blocking_issues_check` 62,
`editor_columns_check` 40, `network_panel_check` 74, `ngspice_window_check` 43, `unsaved_rows_check` 28,
`calibration_save_check` 22, `looks_check` 81, `save_now_check` 29, `task_run_check` 39, `pdk_check` 46,
`reliability_check` 20, `room_check` 31, `graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 34,
`circuit_source_check` 17, `encoder_models_check` 24, `formula_bar_check` 21, `matched_devices_check` 37,
`model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33, `consistency_check` 14,
`training_data_check` 120, `crash_panel_check` 11, `edit_state_check` 28, `callouts_check` 8, `circuit_layout_check` 4,
`network_inputs_check` 9, `request_lifecycle_check` 25, `editor_renames_check` 8, `graph_paint_check` 6,
`table_view_check` 10, `unit_text_check` 14.

### Merged into workbench and live again (2026-10-24; the user: "merge it into workbench and make it live")

**Merge.** SIF-104..129 at 190d303 (full browser suite 58 scripts, 2,911 checks passed) with workbench at eb7425b: records
and thesis of 10-22..10-23 and record 7.389 (the final save skipped when a run never prepared), which its session committed on
the user's word after asking this branch to hold git writes in the shared tree for a few minutes. This branch's worktree was
busy with SIF-130/131, so the merge was built without a worktree: a private index (`git read-tree -m` of the base b57d1fd,
190d303 and eb7425b); the two files both sides changed, docs/workbench.md and docs/functionality-reference.md, merged line by
line with `git merge-file` (no conflict; each side's changed lines checked present); `write-tree`, `commit-tree`: 7d78d3a.
Against 190d303 it adds exactly workbench's files, against workbench exactly this branch's 75. workbench was fast-forwarded to
it in the shared tree (clean at that moment). 0d5ae76 merges 7d78d3a back into this branch after SIF-130/131. Not pushed
(workbench).

**Live.** Page: the 190d303 build (its frontend is 7d78d3a's: workbench changed no frontend file) - index-BWcjvxn2.js,
index-BHqElxol.css - beside the old assets, index.html last. Server: restarted for SIF-111's backend words and 7.389 - pid
656409 since 15:21:56, the same 13 environment variables; the branch's preview on 5174 had been stopped first, and Windows
reached the new server at once. A read-only live check: no console errors, no refused writes. Then, after the full browser
suite on 0d5ae76 (58 scripts, 2,923 checks passed), the page of SIF-130/131 - index-Cy1uZffg.js, index-C80G9LnF.css - at
16:10 (frontend only, no restart). docs/frontend_implementation_status.md now has this log's pointer row (owed since
2026-10-22, when another session was editing that file).

### SIF-132 A line about an Undo, a refused value or an applied task file goes once a later change makes it untrue, and Import names the rows it deletes (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found three lines that outlived what
they said. The line under the formula bar kept "Undo: ..." or "Redo: ..." through the changes after it (S12-1): in
`task-rows-3-older-backend.png` "Redo: Parameters input_pair_width, input_pair_width__XU1_M2 added, w_in, w_in__M2, w_tail
removed; Probes ...; Specs ..., score removed; project labels, circuit source." stood over ring_demo's Parameters (1),
Probes (2), Specs (0) and its empty Specs table, after typed edits and four task choices; "Undo: Specs score (Limit)."
while score_sq ... score_4 were added and typed (`spec_equation_formula.png`, `spec_shared_notes.png`); "Undo: Specs spec_3
(Margin sides)." over the edits of half_freq that came after it (`zero_floor_button.png`). history.ts ends the step on
every recorded change, typing and task choices included, but the effect that writes the line returned early then, and
only a tab change cleared it. A cell's refusal stayed the same way: '"4 um" is a length; this row holds a count.' under the
row made a length again and 3 nm taken (`sheet-2-scrolled.png`) - a press on the tab already shown changes no tab. The
import confirmation of a file of 20 Specs read "Confirm import: 22 changed rows", Apply in focus (SIF-107), and its list
began with the 20 new rows field by field, "Scale (empty) (empty)" in each; the 2 rows the import deletes, score and
score_sq, came last, out of view, and nothing in view said they would go (S12-10, `spec_import_confirm.png`; Undo brings
them back). The task file's window kept "Applied: the editors now hold its rows, and Save as will send its other parts.
Undo takes back the rows only." under its own "The editors changed since this file was read" line after the editors' Undo
(S12-26, `task-file-editors-changed.png`).

**Changed.** `frontend/src/panels/Editors.tsx`: the line under the formula bar knows where it came from - `step`, an
Undo's or Redo's, and `refusal`, a cell's. A step's line goes with the next recorded change, which ends the step
(history.ts): typing, Add, a task choice, an import. A line written with a change - Deleted, Imported, Filled, Pasted,
Copied, Margin sides set, a Probe renamed - is no step's and stays as before; a write that makes no Undo step of its own
(the Specs that follow a typed Probe ID, the network filled in from a saved model) leaves the step, and its line, as
history.ts leaves the step. A refusal goes once it is untrue - its cell takes a value, its row is read in another unit
(its parameter, its Probe), another row stands at its place - and typing in another cell or row, and Add, leave it (the
review follow-up below); it is told on leaving its cell with nothing written, so never in its own render. Both read the
line as drawn, so a change that finds no such line asks for no render. The import's heading keeps its start, "Confirm
import: 22 changed rows" (`typing_check` reads it so), and when a row is deleted or the rows are of more than one kind
says what they are: " - 20 new, 2 deleted (score,
score_sq)" - new, changed, deleted; up to four IDs, then "..." - the deleted part in amber (`span.warn.import-deletes`).
`frontend/src/panels/DiffView.tsx`: the deleted rows come first (a stable sort, the backend's order by ID within each kind),
and a field empty on both sides is left out - a row whose every field is keeps its first, so it still has its line;
Matched devices' list gets the same. `frontend/src/panels/TaskFile.tsx`: an Apply's line drawn while the editors differ
from the file reads "Applied earlier; the editors changed since. Save as still sends its other parts." - worked out as
drawn, not in an effect: right after an Apply the editors differ from the rows read for one commit, until TaskSave takes
the applied rows before the paint (its layout effect), and an effect would have replaced the fresh line; it reads
"Applied: ..." again once the editors are back at the file's rows. The import box keeps Apply in focus (SIF-107's choice),
now under a heading that names what it deletes. Only words, and when they show, change: nothing is imported, applied,
saved or run without the press it took before, Undo and Redo do what they did, and every question is asked as before;
nothing starts, continues or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (a bullet "A line goes
once it is untrue, and an import names the rows it deletes" after SIF-107's; the task file's paragraph) and
`docs/functionality-reference.md` (the Toolbar, Import JSON and Task file rows) say it. Left, as the audit itself left it:
the raw ">=" in the import's list, which SIF-51 writes as stored on purpose.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree; first every check that renders the
line, the import box, a diff or the task file, all passed the first time. `task_rows_check` 57 (54 before): new, the line names what the Redo brought back, the typed edit after it takes the line
away, and no Undo or Redo line stands under the formula bar at `task-rows-3-older-backend.png`. `sheet_check` 56 (54): new,
no refusal is left once the row is a length again and 3 nm is taken (`sheet-2-scrolled.png`), and a cell typed after the
Redo takes its line away; the Ctrl+Z / Ctrl+Y lines and the own-undo checks of Find rows and the formula bar as before.
`editor_columns_check` 43 (40): the zero-floor Undo's "Undo: Specs spec_3 (Margin sides).", gone with the Margin sides
edit after it, and no Undo line at `zero_floor_button.png`; the '"half" in Ratio' refusal as before.
`spec_equations_check` 79 (75): "Undo: Specs score (Limit)." after its Undo and no line left at
`spec_equation_formula.png`; the heading reads "Confirm import: 22 changed rows - 20 new, 2 deleted (score, score_sq)",
its deleted part in `.warn.import-deletes`; score and score_sq first, then extra_0; no "(empty) (empty)" line; SIF-51's
check of the tab, the changes and the headers as before. `task_save_check` 93 (91): after the editors' Undo the window's
line reads "Applied earlier; ..." (`task-file-editors-changed.png`), and after "Apply anyway" over the editors' Redo the
fresh "Applied: ..." again; the Applied words right after the first Apply as before. Unchanged and passed:
`typing_check` 62 (the heading's "0 changed rows" and "1 changed row"), `find_fill_copy_check` 50,
`network_panel_check` 74 ("Undo: run settings."), `model_chooser_check` 139 ("Imported: replaced the run settings..."),
`matched_devices_check` 37, `reliability_check` 20, `edit_state_check` 28, `formula_bar_check` 21, `unsaved_rows_check`
28, `blocking_issues_check` 62, `looks_check` 81 (16 scripts, 930 checks; the four pictures named above show the new
states). Then every other check script the runner runs, on the same source (42; the three reward_v2/v21 ones are never
run here): `run_control_check` failed one check in that run - "... the focus goes to the Run status tab, since Continue...
is off while the run goes on (SIF-90)", the focus on the page's body, in Run status's Continue... form, which this record
does not touch: its focus hand-back waits a frame and races the status read that turns Continue... off - and passed alone
at once, 171: a flake. The rest passed the first time: `calibration_check` 48, `export_check` 37, `run_control_live_check`
23, `training_tab_check` 135, `dom_identity_check` 56, `connection_panel_check` 101, `run_list_check` 177,
`virtuoso_source_check` 116, `testbench_probes_check` 41, `output_panel_check` 98, `project_help_check` 61,
`save_now_check` 29, `files_tab_check` 43, `working_copy_check` 34, `launch_recovery_check` 20, `corner_check_check` 42,
`task_list_check` 105, `ngspice_window_check` 43, `task_run_check` 39, `calibration_save_check` 22, `pdk_check` 46,
`room_check` 31, `graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 34, `circuit_source_check` 17,
`encoder_models_check` 24, `model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33,
`consistency_check` 14, `training_data_check` 120, `crash_panel_check` 11, `callouts_check` 8, `request_lifecycle_check`
25, `circuit_layout_check` 4, `editor_renames_check` 8, `graph_paint_check` 6, `network_inputs_check` 9,
`table_view_check` 10, `unit_text_check` 14. In all 58 scripts, 2,937 checks: SIF-131's 2,923 and the 14 new ones.

**Review follow-up.** The review of 90603fd found one slip; it is real, and it undid part of SIF-49. A refusal's line
went with every change of the tab's table, not with a change that makes it untrue. "4 um" typed into a count row's
Lower and Enter: `moveFrom` puts the focus in the next row's Lower, the blur tells the amber '"4 um" is a length; this
row holds a count.' and the cell goes back to its stored value. The first key typed in that row writes it (`Typed`,
`patch`, `withFollowers`), `config.parameters` changes, and the line went at once: nothing on the page said any more
that the "4 um" was dropped, which is what SIF-49 added the line for. A cell typed after Tab or a click, and Add, did
the same, and a press on Add that left the refused cell took the line in that same press; before 90603fd the line
stayed until a tab change or another line. "Changed" said "a value taken, an Undo, Add", and the title "once a later
change makes it untrue", while an edit to another row, or Add, leaves the refusal true. The review's smallest fix, the
line tied to its row (gone once that row object is no longer in the table), mends another row and Add but not Tab: Tab
is the browser's (`onTableKey` leaves it be) and goes to the next cell of the same row, Lower to Upper, whose first key
writes that row. `frontend/src/panels/Editors.tsx` ties the line to its cell instead. `tell` keeps the row's place and
the field, the row, and the unit it was read in (`effectiveUnit`); the line goes when the row at that place has
another ID, another value in that field or another unit - a value taken in the cell, the row's parameter or a Spec's
Probe of another quantity, a task choice - and an Undo, Delete selected and an import write lines of their own, as
before. Typing in another cell or row, and Add, leave it: `withFollowers` and Add keep the rows they do not touch as
the same objects, and history.ts keeps each configuration as it is. The title now holds as it stands; "Changed" above,
`docs/workbench.md` (the SIF-132 bullet) and `docs/functionality-reference.md` (the Toolbar row) say what takes a
refusal away and what leaves it. Only when the line goes changes: nothing starts, continues or stops a run, saves a
task or writes to Virtuoso, and every question is asked as before. `tsc` clean. One lane, after the memory guard:
`sheet_check` 61 (56 before): new, the "4 um" refusal stays while another row's Notes is typed and while its own row's
Notes is, and goes with the row a length again, before 3 nm is taken; a voltage refused in that length row goes once
its cell takes 4 nm. With `Editors.tsx` of 90603fd in the tree the two "stays" checks fail; with the review's row-tied
fix the second one does. Unchanged and passed the first time: `dom_identity_check` 56, `task_save_check` 93,
`model_chooser_check` 139, `spec_equations_check` 79, `task_rows_check` 57, `typing_check` 62, `find_fill_copy_check`
50, `blocking_issues_check` 62, `editor_columns_check` 43, `looks_check` 81, `network_panel_check` 74,
`unsaved_rows_check` 28, `reliability_check` 20, `formula_bar_check` 21, `matched_devices_check` 37, `edit_state_check`
28; then the other scripts that draw the editors, with `sheet_check` 61 and `editor_columns_check` 43 again on the file
put back after those two runs: `calibration_check` 48, `training_tab_check` 135, `virtuoso_source_check` 116,
`run_list_check` 177, `testbench_probes_check` 41, `project_help_check` 61, `working_copy_check` 34, `task_list_check`
105, `task_run_check` 39, `calibration_save_check` 22, `room_check` 31, `reward_block_check` 34, `agent_window_check`
33, `consistency_check` 14, `crash_panel_check` 11, `callouts_check` 8. In all 33 scripts, 1,900 checks.

### SIF-133 The Virtuoso window says which testbench Save as writes and which cell a run sizes, and promises nothing a press does not do (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found the Virtuoso window naming the
wrong cell on the very point the copy question is about, two lines that promised more than the page does, and a missing
full stop. Right after OK to "Work in FIXTURE_DESIGNS/ring_a directly?", the window read "Working in
FIXTURE_DESIGNS/tb_ring_a directly: you declared it a copy you made (2026-09-23 11:00:00). Its Maestro test and, in a
run, its device sizes are written here.", the draft's next step "... then press Save as: it writes the rows into this
cell's Maestro view (the copy you declared) and reads it back." and, after the first save, "Saved the new task
real:ring_a_2. It runs in FIXTURE_DESIGNS/tb_ring_a - the cell you declared as your copy." (S12-2, `help-4-draft.png`,
`help-5b-task-lines.png`, `virtuoso-2b-draft.png`; S12-12, `tbprobes-2-brought.png`: "Working in FIXTURE_TB/tb_ring3
directly ... device sizes are written here" a moment after the copy question said "every run sets device sizes in
ring3"). A run sets the sizes in the cell (cdf_write.py writes the design's `core_cell`) and Save as writes the Maestro
test into the testbench (virtuoso_setup.py): the three lines put both into the testbench, against the copy question, the
copy warning and the Tasks window's Cell column. With Probes the user had edited, "This cell was read through tb_ring3.
Press Read the cell again to read it through other_tb: Probes then follow it." stood over rows that read keeps -
followTestbench never replaces edited rows; only Use testbench probes exchanges them (S12-28, `tbprobes-3-kept.png`).
With the link down, "Virtuoso cannot be reached (tunnel). Bring the link up in the Connection window, then press
Refresh." stood over "Browse only: you can look at this cell here, but the workbench cannot optimize it yet.", the copy
warning and "(choose its Testbench cell above first: a task needs one)" above a greyed Read, while Refresh had cleared
the lists and the schematic: nothing of the cell was drawn and the Testbench box was off (S12-29,
`virtuoso-3-link-down.png`). And "This cell already has a registered task: real:ota5_v1 Choose it in the Tasks window
..." had no full stop after the key (S12-34, `virtuoso-2d-cell-has-task.png`).

**Changed.** `frontend/src/panels/WorkingCopy.tsx`: the declared line keeps its first sentence, which three checks read,
and then says where each part is written: "Working in FIXTURE_DESIGNS/tb_ring_a directly: you declared it a copy you
made (2026-09-23 11:00:00). Save as writes the Maestro test GATOR here; a run sets device sizes in FIXTURE_DESIGNS/ring_a
(put back when the run ends)." A record whose testbench is the cell itself keeps the old sentence, which is true there.
`frontend/src/panels/VirtuosoWindow.tsx`: the next step ends "then press Save as: it writes the rows into the Maestro test
of the testbench tb_ring_a (the copy you declared) and reads it back." It names the testbench of the declared record: a
first Save as writes the record's copy (task_save.py `_first_save_target`, `working_copy.draft_target`), and a later read
through another testbench leaves the record as it is (`declare` keeps an existing one). Without a record it names the
testbench the cell was read through, and "its testbench" with neither. The plan named the read's testbench, then the
box's: the box's is not where a save writes, and after a read through another testbench the read's is not either. The
line that asks for a read through another testbench says what that read does to Probes, as followTestbench does it.
While the note says "Probes hold rows you edited": "...: your edited Probes stay; Use testbench probes then takes its
rows, if it fits a circuit type." - the plan's words with a condition, as other_tb in the check's own fixture fits none
and the read after it offers no rows. Otherwise: "...: Probes then follow it, unless you edited them." The read through
other_tb ends with "Probes were left as they were", so no line says rows were kept, and the read back through tb_ring3
keeps the edited rows again: the plan's condition alone left "Probes then follow it" over them there. A read without a
testbench, "Press Read the cell again to read it without one.", says nothing of Probes, as it brings no rows ("Probes
then follow it" stood there too). The browse-only note waits while the gate's refusal stands and no schematic of the
cell is drawn (`!(nativeGated && !native)`; `native`, the schematic as read, is a new prop): with the link down the
window shows the refusal and its Connection... alone, and the first good Refresh brings the note back. The plan's
`!nativeGated` would also have taken the note away after a Read the gate refused, whose "then try again" (SIF-108:
Refresh does not read the cell) means the note's own Read button; such a refusal keeps the note, the schematic and the
button. SIF-108's refusal words and "then press Refresh" stay. `frontend/src/panels/Left.tsx`: the first save's line
names the cell, then its testbench: "Saved the new task real:ring_a_2. It runs in FIXTURE_DESIGNS/ring_a with its
testbench tb_ring_a - the cell you declared as your copy." ("- its working copy" for a task's own copy, as before; the
space before the cell, inside its code box until now, is outside it). The cell-has-task note has a full stop after the
key or the built-in remark, "real:ota5_v1. Choose it in the Tasks window ...", and still no button and no new words
(record 7.109, SIF-108). The window gets `native`. Only words, and when the browse-only note shows, change: nothing is
read, saved or run without the press it took before, every question is asked as before, and nothing starts, continues
or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (the gate's refusal in the Virtuoso window,
Probes follow the testbench, Read this cell into the workbench, the user's own copy, Saving a task) and
`docs/functionality-reference.md` (the Library → cell → schematic, Probes follow the testbench, Read this cell and
Working-copy block rows) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. The four scripts that draw these
lines passed the first time. `virtuoso_source_check` 123 (116 before), new: the next step names "the Maestro test of
the testbench ota5_tb", the declared line names the cell FIXTURE_DESIGNS/ota5_v1 a run sizes (`virtuoso-2b-draft.png`),
and the first save's line reads "It runs in FIXTURE_DESIGNS/ota5_v1 with its testbench ota5_tb - the cell you declared
as your copy."; a full stop after real:ota5_v1 (`virtuoso-2d-cell-has-task.png`) and after the built-in's remark (that
check's own words); with the link down, no "Browse only", no schematic and no Read (`virtuoso-3-link-down.png`); the note
back after the good Refresh; and a Read the gate refuses - its testbench chosen, the copy question answered, the import
refused - says "then try again" and leaves the note, the schematic and an enabled Read. `testbench_probes_check` 43
(41), new: the declared line names FIXTURE_TB/ring3 (`tbprobes-2-brought.png`); over the kept rows the line reads "...:
your edited Probes stay; Use testbench probes then takes its rows, if it fits a circuit type." (`tbprobes-3-kept.png`;
the check now waits for the kept line before it reads); back to tb_ring3 after other_tb it reads "...: Probes then
follow it, unless you edited them.". `project_help_check` 62 (61): the next step's "Maestro test of the testbench
tb_ring_a", and, new, the first save's line in `help-5b-task-lines.png`. `working_copy_check` 35 (34): new, the declared
line's second sentence names GPDK045_RINGOSC/ring_osc_3stage; the first sentence and its time as before. A probe run of
these four on the code before (the three sources as at HEAD, put back after, their sums compared) failed the 12 checks
this record adds or changes and no other: 6 of `virtuoso_source_check`, 3 of `testbench_probes_check`, 2 of
`project_help_check`, 1 of `working_copy_check`. The two that pass there - the note back after the good Refresh, and a
refused Read keeping it - hold the condition in place: with the plan's `!nativeGated` instead, `virtuoso_source_check`
failed the refused-Read check alone (122 of 123). Then every other script the runner runs, on the final source (55 -
`virtuoso_source_check` again, after the detail its full-stop check prints on a failure was corrected; the three
reward_v2/v21 ones are never run here), all passed the first time, no flake: `calibration_check` 48, `export_check` 37,
`run_control_live_check` 23, `training_tab_check` 135, `run_control_check` 171, `dom_identity_check` 56,
`connection_panel_check` 101, `run_list_check` 177, `virtuoso_source_check` 123, `task_save_check` 93,
`model_chooser_check` 139, `task_rows_check` 57, `output_panel_check` 98, `spec_equations_check` 79, `typing_check` 62,
`sheet_check` 61, `find_fill_copy_check` 50, `files_tab_check` 43, `launch_recovery_check` 20, `blocking_issues_check`
62, `corner_check_check` 42, `network_panel_check` 74, `task_list_check` 105, `editor_columns_check` 43, `looks_check`
81, `ngspice_window_check` 43, `task_run_check` 39, `unsaved_rows_check` 28, `calibration_save_check` 22,
`save_now_check` 29, `pdk_check` 46, `reliability_check` 20, `room_check` 31, `encoder_models_check` 24,
`graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 34, `circuit_source_check` 17, `formula_bar_check`
21, `matched_devices_check` 37, `model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33,
`consistency_check` 14, `training_data_check` 120, `crash_panel_check` 11, `edit_state_check` 28, `callouts_check` 8,
`request_lifecycle_check` 25, `circuit_layout_check` 4, `editor_renames_check` 8, `graph_paint_check` 6,
`network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14. In all 58 scripts, 2,953 checks: the 2,942 of
SIF-132 and its review follow-up, and the 11 new ones.

### SIF-134 Every Training key shows its line's colour, the line over a comparison names each run by its swatch, and a mean of zeros reads 0 (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found the Training tab's keys in other
colours than their lines, a comparison's values each repeating its run's whole name, and a mean of zeros in e-notation.
With three runs compared, the chips, the Step reward legend and the Key numbers rows gave seed 1 a red square and both
seed 4 and seed 3 the same white one, while seed 3's line (the frozen run, evaluations 1 to 48) was drawn blue and no key
on the page was blue (S12-3, `training-compare.png`): styles.css keyed `.key-run1` with `--probe` and `.key-run2` with
`--spec`, both #f4f4f5 since record 7.360, and `.key-run3` with the amber `--unresolved`, while TrainingChart.tsx draws
the runs in `--series-1` to `--series-4` - red, #e8e8ec, blue, violet. One run had the same fault: the gradient norms
draw Policy in `--series-3`, blue, under a white `.key-other1` (`--probe`). On a comparison every value in the line over
a chart came after its run's whole name, which the swatched keys just above already give - "fixture_task (tx1-fixture) ·
seed 1 · 10-05 11:00 · live (recorded) -0.04543 · ... · once: mean of last 50 -0.0651", four lines over each chart
(S12-14, `training-learner-by-evaluation.png`); at 1366 px with eight charts "-0.05374", "0.01204" and "2.558e-17" each
stood alone on a line under its "...: mean of last 50", and the plots were strips (`training-eight-compared-1366.png`).
compare.ts named each compared series "<run> (recorded)" or "<run>: mean of last N", and the line wrote the name before
each value. And Worst spec miss (normalized) read "Training (recorded) 0 · Training: mean of last 50 2.558e-17" (S12-18,
`training-eight.png`): the running mean of the last N (prep.ts) adds each value and takes off the one leaving, and a
window of zeros kept the rounding remainder of the values that had left it, which a normalized number prints as it is. A
real run reaches it as soon as every design meets its specs.

**Changed.** `frontend/src/styles.css`: the keys take the chart's own tokens - `.key-run0` to `.key-run3` `--series-1` to
`--series-4`, `.key-other1` `--series-3`, and `.key-training` / `.key-other0` and `.key-evaluation` `--series-1` and
`--series-2` (the same red as before; the evaluation white a shade greyer, #e8e8ec as its line). A run's chip, its legend
keys, its Key numbers row (TrainingTab.tsx) and its swatches in the line over a chart use these classes, so all show the
colour its lines are drawn in. `frontend/src/panels/training/catalog.ts`: a series may carry `short`, its own words
without the run's name; `frontend/src/panels/training/compare.ts` gives every compared series its words - "recorded",
"mean of last 50" ("mean of last 50 evaluations" by evaluation), "each design" and "share so far" on the evaluation
success rate, none for a single line or a series without smoothing. A learner chart of two columns names the column as
one run's chart does, "Critics (recorded)" and "Policy: mean of last 50" (the plan's "Critics recorded" read as a verb
beside "Critics: mean of ..."). The labels stay whole: the legend keys, the series groups and the chart's layout key read
them. `frontend/src/panels/TrainingChart.tsx`: in the line over a chart a compared run's value follows its run's swatch
(`span.readout-run.key-run<n>`, the series' whole name its tooltip and, as an image, its name for a screen reader) and the
series' words: "Newest: Evaluation 322 · [swatch] recorded -0.05506 · [swatch] mean of last 50 -0.05374". One run's line
is as before. `frontend/src/roadster.css` sets the swatch as the keys' 10 px square in the line's text.
`frontend/src/panels/training/prep.ts`: a running mean's state counts the values in its window that are not 0 (`nz`; the
checkpoints carry it, so a zoomed chart that starts from one gets the same numbers), and a window that holds only zeros
sums to 0 - the mean of the last N, and the mean over the updates of the last N evaluations. An empty window (no update
for N evaluations, by evaluation) keeps its sum as before: with the plan's `if (!state.nz)` it was reset too, and the
means after it then differed from the builders before record 7.221 in the 16th digit (`--reference`, below).
`frontend/src/panels/training/series.ts`: `smooth` and `smoothOver` the same, so they stay the charts' numbers (only the
checks use them). Only colours, words and a value shown change: nothing is read, saved or run that was not, and nothing
starts, continues or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (the charts' colours,
Smoothing, Several runs on one chart) and `docs/functionality-reference.md` (the Training row) say it. Seen, not changed:
after a learner restart one run's gradient norms put the "abandoned at a restart" group between Critics and Policy, so
Policy takes the first colour again - drawn and keyed alike, but as red as Critics.

**Checked.** `tsc` clean. `training_data_check` 124 (120 before), new: a window of zeros after 0.1 and 0.2 reads exactly
0 - the mean of the last 2 of Worst spec miss, the mean over the last 2 evaluations of a learner chart, `smooth` and
`smoothOver` - and the means before it are as before; the same worked out from a checkpoint (every 2 positions, a zoomed
view); the compared series' words, one column's and two columns'. Run alone on copies: with the training code at HEAD the
4 fail and the 120 pass; with checkpoints that drop the count, the checkpoint check fails and 4 random runs with it. Its
`--reference` mode (the trainingData.ts of c170802) fails at HEAD already, on two catalog sentences SIF-47 reworded; with
those two aligned in a scratch copy of the reference all 124 pass. `training_tab_check` 139 (135), new: one run's
gradient norms - the Critics and Policy keys in `--series-1` and `--series-3`, each among the colours the plot strokes
its lines in (a stroke hook beside the check's clearRect and fillText ones); a comparison's line - each value after its
run's swatch, the swatch's tooltip and name the series' whole name, then "recorded" or "mean of last 50", no run's name
in the line; three runs - every chip, legend key, Key numbers row and swatch in a line in its token, and the Step
reward's three keys among its strokes, red, #e8e8ec and blue; eight charts at 1366 px with one compared run - each line
on two lines at most, each part whole, every plot over 60 px (64 and 81 px; `training-eight-compared-1366.png`).
Rewritten, as they found a value by its run's name: the hover values of the shown and the compared run, and the
once-per-evaluation run's value by evaluation and its absence by update, now found by the swatch's tooltip. The SIF-120
review's check at 1366 px now has two compared runs: with one, no plot is left only its 60 px any more; with the frozen
run beside it the learner charts' "Not on this chart" grows their rows to 242 px, two plots stand at 60 px, every plot
inside its card, the second row's titles and × in reach. With the seven sources at HEAD (put back by their checksums) 7
fail - the 4 new and the 3 rewritten - and 132 pass. One lane, after the memory guard, on a build of this tree, all
passed the first time: `training_tab_check` 139, `training_data_check` 124, `dom_identity_check` 56,
`corner_check_check` 42, `looks_check` 81 (its SIF-129 stylesheet check included). The other scripts were not run: none
draws the Training tab or uses these classes. In all 5 scripts, 442 checks.

### SIF-135 The bound a spec's Limit uses reads "needed", its error names the box to fill, and the Issues column stays in view (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found a bound a spec needs labelled as
if it were not, its error in the schema's words, and the words that explain a red row cut by the table's box. On Specs the
red row score_cube, Limit "≥ lower", read "no limit" in its empty Lower as in its Upper, and its Issues cell "error
constraint >= needs lower" (S12-8, `spec_shared_notes.png`); a Lower cleared in a saved task, under "≥ lower, then higher
is better", read "no limit" too (`unsaved-rows-specs-cleared.png`). `emptyOf` (Editors.tsx) gave every empty Specs bound
"no limit", though its comment kept the word for a one-sided spec's other side, and the Issues column had no words of its
own for `missing_threshold` (validation.py `_check_limits`), so the backend's sentence stood as it is. A spec made with Add
starts so - `newRow` gives it the first limit, "≥ lower", and no lower -: every spec added showed the bound it needs as "no
limit" beside an error in schema words. At 1680 x 1050 with More columns open the Specs table was wider than its box and
scrolled sideways, and the box cut its last column, Issues: score_sq's red row read "error The equa", "info New spec:",
"info The source" (S12-25, `spec_probe_chips.png`; `spec_import_error.png`: "warning The ur").

**Changed.** `frontend/src/panels/editorRules.ts`: `limitUses(constraint, bound)`, the bounds each limit uses as
`_check_limits` asks for them (≥ lower the Lower, ≤ upper the Upper, an interval both). `frontend/src/panels/Editors.tsx`:
`emptyOf` gives the empty bound a row's Limit uses "needed", the other side "no limit"; an empty Scale's "auto" and a
follower's "-" are as before. `boundWords`: the Issues column names a missing bound by its header and the Limit's words,
"Lower needed: the Limit ≥ lower uses it" (the bound from the path, targets[2].lower, the limit from the message, worded by
`limitLabel`), and a bound the Limit does not use (`unexpected_threshold`) "Upper not used by this Limit: clear it"; a
message in other words keeps its first clause, and the backend's message and code stay in the tooltip, as for every issue.
A tab's tooltip gives its first blocking issue in the column's words too (`blockingTitle`, the plan's optional item): "1
blocking issue: Lower needed: the Limit ≥ lower uses it. The red button in the header lists it: ...". The Issues header
has the class `issues`. `markScrolled` marks the box `pin-issues` from `PIN_ISSUES_PX`, 800 px, of width, and `more-x`
while columns stand to the right of what it shows, beside the ID's `scrolled-x`; a ResizeObserver on the box, the table and
the Issues header marks it again when they change size without a scroll (a window resized, More columns, an issue that
widens the column) and puts the column's width in `--issues-w`. `frontend/src/styles.css`: in a `pin-issues` box the
Issues header and cells stay at the right edge (z-index 2, the header 4, as the ID's); `td.issues` joins the ID's
zero-specificity panel background, so zebra, error and not-saved rows still tint it; a line and a soft shadow mark its left
edge while columns pass under it, the ID's marker mirrored; and `--issues-w` is the box's `scroll-padding-right`. Three
changes from the plan. Its line, an inset box-shadow on the column at all times, is drawn only while columns pass under it,
as the ID's is: always on, it doubled the grid line beside the column whenever nothing passed under, and on the header the
header's own accent line outranks a box-shadow. The narrow-box limit is a class the page sets, not a container query - the
box would have been the stylesheet's first container, and the page already marks it for the ID's line -, and it is 800 px,
not about 760: at 1680 px the tick box and a Spec ID take about 210 px, an Issues column with a row's words about 270 px,
an Equation about 310 px. At 1366 px with the circuit shown the box is about 640 px and the column stays in the table's
flow (pinned, it and the ID would leave the other columns about 150 px); at 1366 px without the circuit it is about 950 px
and at 1680 px 1264 px, both pinned. And the scroll padding is new: without it a cell under the pinned column counted as in
view, so Basis, focused as Tab focuses it, stayed under the column (1114 to 1198 px, the column from 1023 px), and a Where
to the Scale left it partly under (to 1057 px, the column from 1041 px). `frontend/src/panels/cells.tsx`: the placeholder's
comment names "needed". Only words, a placeholder and where a column stands change: nothing is read, saved or run that was
not, every question is asked as before, and nothing starts, continues or stops a run, saves a task or writes to Virtuoso.
`docs/workbench.md` (Placeholders that read; The ID in view; "A spec's limit in words, and the Issues column in view" in
Tied rows, spreadsheet keys and a pasted block) and `docs/functionality-reference.md` (the N blocking issues, Tied rows,
keys and pasting a block, and Specs columns rows) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. The five scripts that draw these
lines passed the first time: `spec_equations_check` 88 (79 before), new: score_cube's empty Lower reads "needed" and its
Upper "no limit", its error is whole with "constraint >= needs lower" and its code on hover, and the Specs tab's tooltip
gives it in the column's words (`spec_shared_notes.png`); an Upper typed into score_4, "≥ lower", reads "error Upper not
used by this Limit: clear it" and goes once cleared; at 1680 x 1050 with More columns, the table 176 px wider than its
box: every Issues cell inside the box at its right edge, score_sq's error in view and on top, the edge line while columns
pass under the column and none at the table's right end (`spec_probe_chips.png`), and Basis, focused there, comes into
view beside the column (the box scrolled 176 px for it); changed: the error's words in the shared-notes check.
`editor_columns_check` 45 (43), new: a spec made with Add reads "needed" in its Lower and "no limit" in its Upper, and an
interval's two empty bounds "needed"; changed: freq's Lower reads "needed". `unsaved_rows_check` 28, changed: the Lower
cleared in a saved task reads "needed", at 5.81 : 1 on the amber as before. `sheet_check` 63 (61), new: on Parameters
and on Specs the Issues column is pinned in the 1264 px box and in the table's flow in the 420 px one; the tick box, the
ID and their edge line as before. `blocking_issues_check` 63 (62), new: the Scale a Where chooses comes into view beside
the pinned column. A probe run of these five on the code before (the three sources as at HEAD, put back after, their
sums compared) failed 13 checks and no other: 6 of `spec_equations_check`, 2 of `sheet_check`, 3 of
`editor_columns_check`, 1 of `unsaved_rows_check`, 1 of `blocking_issues_check`; its first try stopped three scripts at
the `issues` class the old header lacks, so the new checks find the Issues header as the row's last and fail instead. A
probe without the scroll padding failed the Basis and the Scale checks alone (87 of 88, 62 of 63). Then every script the
runner runs (58; the three reward_v2/v21 ones are never run here), all passed the first time but one: `calibration_check`
48, `export_check` 37, `run_control_live_check` 23, `run_control_check` 171, `dom_identity_check` 56,
`connection_panel_check` 101, `virtuoso_source_check` 123, `run_list_check` 177, `task_save_check` 93,
`testbench_probes_check` 43, `spec_equations_check` 88, `model_chooser_check` 139, `output_panel_check` 98,
`task_rows_check` 57, `typing_check` 62, `sheet_check` 63, `find_fill_copy_check` 50, `project_help_check` 62,
`working_copy_check` 35, `files_tab_check` 43, `launch_recovery_check` 20, `consistency_check` 14,
`editor_columns_check` 45, `task_list_check` 105, `blocking_issues_check` 63, `corner_check_check` 42,
`network_panel_check` 74, `ngspice_window_check` 43, `looks_check` 81, `task_run_check` 39, `unsaved_rows_check` 28,
`calibration_save_check` 22, `save_now_check` 29, `room_check` 31, `pdk_check` 46, `reliability_check` 20,
`graph_view_check` 69, `module_fold_check` 30, `reward_block_check` 34, `circuit_source_check` 17,
`encoder_models_check` 24, `crash_panel_check` 11, `formula_bar_check` 21, `matched_devices_check` 37,
`model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33, `training_data_check` 124,
`edit_state_check` 28, `callouts_check` 8, `request_lifecycle_check` 25, `circuit_layout_check` 4,
`editor_renames_check` 8, `graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14.
`training_tab_check` failed 1 of 139 - "...a run at rest is read at once" (SIF-126) counted the run's history read before
its held-back status request had come in - and passed all 139 run alone: a flake, in a tab this record does not touch.
After the full run the edge check of `spec_equations_check` also asks that score_sq's lines be whole, none cut by its
ellipsis; run alone it passed, 88 again. In all 58 scripts, 2,975 checks: the 2,953 of SIF-133, the 8 SIF-134 added and
the 14 new ones.

**Review follow-up.** The review of 208e75f found one slip; it is real. A Where pressed while another tab is shown could
leave its cell under the pinned Issues column. `--issues-w`, the box's scroll padding, was written by the ResizeObserver
alone, and the browser calls an observer after the frame's animation callbacks. A Where on another tab switches the tab
and, in the same click (React runs the effects of a click's render before the next frame), asks for the animation frame
that scrolls its cell into view: that frame scrolled with the padding of the tab the Where was pressed on, and nothing
scrolled again once the observer had measured. In `blocking_issues_check`'s scene, 1680 x 1050 with More columns shown:
on Parameters, no row issue of its own, the padding was 59 px, the Specs' column is 255 px, and the Scale's Where left
the Scale at 951 to 1057 px, the column from 1041 px, the box not scrolled - the state "Changed" above measured without
the padding. The check pressed that Where only with Specs open, where the stale padding was the wider one (More columns
still folded): the box scrolled 24 px and the Scale ended 8 px short of the column. `frontend/src/panels/Editors.tsx`:
`fitIssues` puts the Issues header's width in `--issues-w` and marks the box (`markScrolled`); the observer calls it as
before, and the Where's animation frame calls it just before `scrollIntoView`. Measured there, not in a layout effect on
the tab and More columns, the review's other way: a Where that clears a Find text or opens a fold draws the table again
before that frame too, and the frame measures the table it scrolls, with no layout of its own (`scrollIntoView` lays the
page out anyway); not in `markScrolled` either, which every scroll calls, while a scroll never changes the column. Both
Wheres now scroll the box 16 px, the Scale at 935 to 1041 px, beside the column. `docs/workbench.md` and
`docs/functionality-reference.md` already say so and stand. Only where a Where scrolls changes: nothing starts,
continues or stops a run, saves a task or writes to Virtuoso, and every question is asked as before. `tsc` clean.
`blocking_issues_check` 65 (63 before), new: on Parameters with More columns shown and the box at its start the padding
is that tab's column, narrower than the Specs' (59 against 255 px), and the Scale's Where pressed there chooses the Scale
beside the pinned column (picture `issues-4d-scale-from-parameters.png`, of the table). A probe run of the new checks on
`Editors.tsx` of 208e75f failed the second alone (64 of 65). One lane, after the memory guard, all passed the first
time: `dom_identity_check` 56, `testbench_probes_check` 43, `spec_equations_check` 88, `task_rows_check` 57,
`typing_check` 62, `sheet_check` 63, `find_fill_copy_check` 50, `project_help_check` 62, `blocking_issues_check` 65,
`editor_columns_check` 45, `looks_check` 81, `unsaved_rows_check` 28, `formula_bar_check` 21, `matched_devices_check`
37, `crash_panel_check` 11, `edit_state_check` 28; and `blocking_issues_check` 65 again once its new picture showed the
table. In all 16 scripts, 797 checks; no flakes.

### SIF-136 The header keeps Start and Abort on its first row, the connection pill says what is missing, and a budget of 1 reads "1 evaluation" (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found the header's run buttons broken
apart, a connection pill with nothing readable left in it, and "1 evaluations". With Calibration ready open at 1680 px
the header's first row ended with the Next line and Start, and Abort stood alone on a second row under the GATOR chip,
above the line (S12-7, `calibration-save-0-line.png`); in `calibration-0b`, `0c` and `0d` the Next line, Start and Abort
dropped to a second row at the left while Save now stayed at the right end of the first. roadster.css lets the header
wrap while a full-width line is open under it (blocking issues, a refusal, a settings problem, Calibration ready), and
its items then broke into rows at their full widths before the task's facts gave way: the title block at its full width
pushed the last ones down. RunButtons returned a fragment, so Save now, the Next line, Start and Abort were four items
of the header, free to part; at 640 px Save now ended one row and the Next line, Start and Abort began the next.
Calibration ready always comes with a held calibration run, so at 1680 px this happened at every calibration's end. With
no connection the pill's only words were "none set up yet" or "none selected" - the word "Connection" for screen readers
only, and no state word - and the header cut them to "none s..." at 1680 px (S12-17, `looks-roadster.png`) and to "none
set u..." at 1366 px (S12-27, `matched_devices_1366_folded.png`). And with a budget of 1 the folded Run configuration
line read "New model - 1 evaluations - Graph Transformer 4..." (S12-23, `fold-2-run-folded-warning.png`): `foldedText`
and the header's Next line wrote "evaluations" after any count, and the schema allows a budget of 1.

**Changed.** `frontend/src/panels/RunControl.tsx`: RunButtons draws Save now, the Next line, Start (Pause, Resume) and
Abort (Force abort, Let go) in one `span.run-buttons` - the same buttons, with the same handlers and the same questions.
`frontend/src/roadster.css`: the group is a row of its own, its parts 14 px apart as the header's items are, its buttons
never shrink, and in it only the Next line gives way, as it did beside them (to its longest word, 130 px here, where it
went to 120 px and cut that word); the header wraps the group whole, so Start and Abort are never apart. The Next line
is at most its basis, 200 px (220 before): the group is as wide as its parts can be, and the other 20 px stood empty at
its end. From 1201 px, while a full-width line is open, the title block and the group grow from no width, each up to its
own, the title block by four shares to the group's one, and the room left goes to the spacer's auto margin: the first
row stands as on one line. A probe (a throwaway check, not kept) measured the header at 1210 to 1680 px with and without
a line open, a connection and a run: the title block and the group were as wide with a line open as without one (522,
407 and 251 px of title block at 1680, 1366 and 1210 px with a run held and no connection), all on the first row. Two
changes from the plan. Its `flex: 1 1 0` on the title block alone left the spacer growing beside it, and the two split
the room: at 1680 px the title block had 226 px, "synthetic:gpdk045_ota5" cut to 79 px, beside 226 px of nothing. And
its group at `flex: none` held the Next line at 200 px on the one-line banner too, where it gave way to 120 px before;
with the title block's zero basis alone, the group never gave way while a line was open, and the title block had 182 px
at 1210 px against 251 px on one line. `frontend/src/panels/Connection.tsx`: with no connection the pill reads
"Connection" (the hidden name left out, so that a screen reader hears it once) and, where a connection's state stands,
"not set up" (the connection file has none) or "none chosen" (the configuration names none), in the muted colour of a
state not known, its tooltip saying what to press and what works without one. With a connection nothing changes.
`roadster.css`: the state word never gives way, as a connection's state never does (record 7.361); from 1201 px the
task's facts and the pill share the room beside the chip equally, each from no width up to its own, so the grey facts
give way first, then the task's name and the word "Connection" together, with "..."; and the pill keeps 108 px, the room
of its longer state word ("none chosen", 70.5 px, with the gap and the padding). A change from the plan: its `flex:
none` on the word alone let the pill shrink under its words - at 1680 px the pill was 91 px wide, its 160 px of words
running past its end -, and a pill held at its full width took the task's name to 4 px at 1440 px and put the pill over
the run's state at 1210 px. In the probe, with a run held: at 1680 px "Connection not set up" whole beside the whole
task name; at 1366 px "Conne... not set up" beside "synthetic:gpdk0..." (145 px each); at 1440 and 1210 px "not set up"
beside what is left of the name; without a run, at 1210 to 1680 px, the pill whole. `frontend/src/panels/rlModelText.ts`
(`foldedText`) and `frontend/src/launch.ts` (the Next line): the budget through `plural`, "1 evaluation". Only where the
header's parts stand, and words: nothing is read, saved or run that was not, every question is asked as before, and
nothing starts, continues or stops a run, saves a task or writes to Virtuoso. `docs/workbench.md` (the banner in The
page's look and layout; "Connection": one button...; Folding the right column's modules) and
`docs/functionality-reference.md` (the Title block, Start → Pause → Resume, One button, a window, four kinds and Folding
the module rows) say it. Seen, not changed: with a connection, at 1210 to 1440 px with a run held, the pill is narrower
than its state word, which runs past its end over the run's state ("unknown" over "Ready"), as before this record - the
plan leaves the connected pill as it is. And more counts are written "evaluations" after any number: the model line's
"save point N evaluations" (rlModelText.ts), the Continue... form's "All N evaluations are used" and "N evaluations are
used already" (launch.ts), the Runs window's load message (runWindowActions.ts), the RL model window's newer save point
(ModelChooser.tsx), the run brief's progress tooltip (RunBrief.tsx) and Run status's "saved at N evaluations"
(RunTabs.tsx).

**Checked.** `tsc` clean. `calibration_save_check` 23 (22 before), new: with Calibration ready open at 1680 px the title
block, Save now, the Next line, Start and Abort have one vertical centre, above the line. `calibration_check` 52 (48):
the same in its four header pictures - before the run, Calibration ready, Show table, nothing proposed.
`blocking_issues_check` 66 (65): with the list open, the title block, the issues button, Save now, the Next line, Start
and Abort on one row above it. `reliability_check` 22 (20): at 960 and 640 px Save now, the Next line, Start and Abort
on one row, inside the window. `looks_check` 83 (81): with no connection the pill reads "Connection not set up" at 1680
px, the word whole and said once, the state inside the pill with its tooltip; at 1210 to 1366 px the state word whole
inside the pill, clear of the run's state. `matched_devices_check` 38 (37): "Connection" and "not set up" whole at 1366
px. `run_control_check` 172 (171): after a pause for connection failures, the button its line names reads "Connection
not set up" in full. `module_fold_check` 31 (30): a budget of 1 reads "1 evaluation" on the folded line and on the
header's Next line. `testbench_probes_check` and `virtuoso_source_check` wait for the pill to name a connection - not
"Connection" with "not set up" or "none chosen" - instead of stripping its old empty words. A probe run of the new
checks on the five sources as at HEAD (put back by their checksums) failed 10 of the 13 new checks: 3 of
`calibration_check` (0b, 0c, 0d), 2 of `looks_check`, and 1 each of `calibration_save_check`, `reliability_check` (640
px), `module_fold_check`, `matched_devices_check` and `run_control_check`; the header before the run, the issue list's
header at 1680 px and the 960 px header held before too. One lane, after the memory guard, on a build of this tree: the
ten scripts above first, all passed but one check of `run_control_check` (below); then every script the runner runs (58;
the three reward_v2/v21 ones are never run here), all passed the first time but two: `calibration_check` 52,
`export_check` 37, `run_control_live_check` 23, `training_tab_check` 139, `dom_identity_check` 56,
`connection_panel_check` 101, `virtuoso_source_check` 123, `run_list_check` 177, `task_save_check` 93,
`testbench_probes_check` 43, `spec_equations_check` 88, `model_chooser_check` 139, `output_panel_check` 98,
`task_rows_check` 57, `typing_check` 62, `find_fill_copy_check` 50, `sheet_check` 63, `project_help_check` 62,
`files_tab_check` 43, `working_copy_check` 35, `launch_recovery_check` 20, `blocking_issues_check` 66,
`corner_check_check` 42, `task_list_check` 105, `editor_columns_check` 45, `looks_check` 83, `network_panel_check` 74,
`ngspice_window_check` 43, `unsaved_rows_check` 28, `calibration_save_check` 23, `save_now_check` 29, `pdk_check` 46,
`reliability_check` 22, `room_check` 31, `graph_view_check` 69, `module_fold_check` 31, `reward_block_check` 34,
`circuit_source_check` 17, `encoder_models_check` 24, `formula_bar_check` 21, `matched_devices_check` 38,
`model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33, `consistency_check` 14,
`training_data_check` 124, `crash_panel_check` 11, `edit_state_check` 28, `callouts_check` 8, `network_inputs_check` 9,
`request_lifecycle_check` 25, `circuit_layout_check` 4, `editor_renames_check` 8, `graph_paint_check` 6,
`table_view_check` 10, `unit_text_check` 14. `run_control_check` failed 1 of 172 in both runs - "... the focus goes to
the Run status tab, since Continue... is off while the run goes on (SIF-90)", the focus on the page's body: Run status's
Continue... form, which this record does not touch, gives the focus back a frame after it closes, a race with the status
read that turns Continue... off, as in SIF-132's full run - and passed all 172 run alone, twice: a flake.
`task_run_check` stopped after 10 of its 39 checks when the Runs window's DevTools session closed under it, and passed
all 39 run alone: a flake. In all 58 scripts, 2,990 checks: the 2,977 of SIF-135 and its follow-up, and the 13 new ones.

### SIF-137 A failed run says where its cause is written and what to do next, connection failures have one name, and a run that does not train waits for no update (2026-10-24; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found a failed run that said only what
could not be done, one pause called by two names, and a steering line waiting for an update that never comes. A failed
run read in red under the header "The run failed at 0 of 60 evaluations: FIXTURE: 3 consecutive failed evaluations;
stopped safely", and Run status "failed · too many failures in a row", the reason in red, a greyed Continue... with "A
failed run cannot be continued." and Export status (S12-6, `run-6c-failed.png`): nothing said where the failures were
written or what to do next, while the Runs window's Details of the same run say that Load run brings its model into the
next run (SIF-90). Every real failure ends there. The plan pointed both places at the errors log, but a run stopped by its
failed evaluations - the picture's, the end "Stop after N consecutive failed evaluations" makes - writes nothing there:
each evaluation's status, failure type and diagnostics go into the evaluations table, and the errors log holds only what
raised (engine.py `_log_error`: a crash, an evaluation that raised, a save that failed), so the plan's Show errors would
have opened an empty log for that run. After the engine's own pause (S12-19, `run-6b-paused-by-itself.png`) the chip and
the line said "connection failures" and Run status "paused · infrastructure failures", its State row "paused
(infrastructure failures)": STOP_WORDS had no words for the reason. The line said "Test the connection (Connection
button), then Resume.", but with a connection chosen the pill shows the connection's name, its word "Connection" for
screen readers only (roadster.css). And the steering line read "exploration bonus (latest update): no update yet." on a
completed Calibration (`calibration-1-proposals.png`), which never makes one - nor do a Baseline and an Evaluate only run
-, and on a completed run the backend's verdict, "The network is still choosing close to random: ...", stood in orange in
the present tense, with nothing to act on (S12-20, `export-1-status.png`).

**Changed.** `frontend/src/format.ts`: STOP_WORDS reads `infrastructure_failures` "connection failures", so Run status's
state and State row, the Runs window and the Training tab's badge say what the chip and the line say. `failedWhere` gives,
by stop reason, where a failed run wrote what went wrong - the evaluations table for `consecutive_failures`, the errors
log for the rest, nothing more for a full disk or a launch not confirmed, which the run's error says alone - and
`FAILED_WHERE` its words, one sentence for both places: "Why each evaluation failed is in Data tables (evaluations: status
and diagnostics)." or "The details are in the errors log (Logs, errors)." `frontend/src/panels/RunControl.tsx`: the
failure's line ends with that sentence; the pause's line reads "Test the connection - its name in the header opens the
Connection window - then Resume." `frontend/src/panels/RunTabs.tsx`: after "A failed run cannot be continued." Run status
says the same sentence, then "Fix the cause, then Start a new run" - with "; Load run in Runs... brings this run's model
into it (Fine-tune or Evaluate only)." when the run kept a save point -, "press Calibration again." for a Calibration and
"run the baseline again (Retry baseline, shown with its task)." for a baseline (Start makes neither, and they have no
model for Load run to bring), with **Show evaluations** or **Show errors** beside it (`onShowCause`). `SteeringCheck`
takes the run's status: a run that does not train (`runTrains`, `frontend/src/panels/rlModelText.ts`, beside `runMode`)
reads "exploration bonus: none (this run does not train)." with no verdict; an ended run "no update was made", and its
verdict, the backend's words as they are, in grey: "At its end: <verdict> A larger Evaluation budget, or the Initial alpha
a Calibration proposes, gives the next run room to learn."; a live or paused run's stays in orange.
`frontend/src/panels/BottomPanel.tsx`: the press opens Logs on the errors log, or Data tables on the evaluations, newest
first, and puts the keyboard on that tab, as Continue...'s form gives it back (SIF-90). `frontend/src/styles.css`: the
next step takes the row's room after the reason, so its button and Export status stand at the row's end. Changes from the
plan: the place by stop reason, with Show evaluations beside Show errors; the line's ending in Run status's words, not
"Why: the errors log (Logs, errors)."; the next run by the run's kind; the spread's "not enough scored designs yet"
without "yet" on an ended run, the same slip one line up; and the keyboard on the tab shown. Only words, and where the
bottom panel looks: the two buttons choose its tab, log and table as presses on them do; nothing starts, continues or
stops a run, saves a task or writes to Virtuoso, and every question is asked as before. `docs/workbench.md` (in Start,
Pause, Resume, Abort: the line under the header, the Run status tab and Continue...'s reason before the press; in Reward
v2.1 controls and checks: the steering line) and `docs/functionality-reference.md` (Start → Pause → Resume, Steering
warning, Run status) say it. Seen, not changed: a run searched by Bayesian optimization trains no network either, but
its status does not name its optimizer, so its line still reads "no update yet" while it works and "no update was made"
at its end; and Run configuration's setting keeps its name, "Pause after N consecutive infrastructure failures".

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. First the 21 scripts that draw Run
status, Data tables, the line under the header or the Runs window, before the keyboard move was added: all passed the
first time, 1,392 checks. Then every script the runner runs (58; the three reward_v2/v21 ones are never run here), all
passed the first time, no flakes: `calibration_check` 53, `export_check` 38, `run_control_live_check` 23,
`run_control_check` 178, `training_tab_check` 139, `dom_identity_check` 56, `connection_panel_check` 101,
`virtuoso_source_check` 123, `run_list_check` 180, `task_save_check` 93, `testbench_probes_check` 43,
`spec_equations_check` 88, `model_chooser_check` 139, `output_panel_check` 98, `task_rows_check` 57, `typing_check` 62,
`sheet_check` 63, `find_fill_copy_check` 50, `project_help_check` 62, `files_tab_check` 43, `working_copy_check` 35,
`agent_window_check` 33, `corner_check_check` 42, `launch_recovery_check` 20, `blocking_issues_check` 66,
`task_list_check` 105, `editor_columns_check` 45, `looks_check` 83, `network_panel_check` 74, `ngspice_window_check` 43,
`unsaved_rows_check` 28, `calibration_save_check` 23, `save_now_check` 29, `task_run_check` 39, `pdk_check` 46,
`reliability_check` 22, `room_check` 31, `graph_view_check` 69, `module_fold_check` 31, `reward_block_check` 34,
`circuit_source_check` 17, `encoder_models_check` 24, `matched_devices_check` 38, `formula_bar_check` 21,
`model_structure_check` 33, `mode_suggestion_check` 20, `consistency_check` 14, `training_data_check` 124,
`crash_panel_check` 11, `callouts_check` 8, `edit_state_check` 28, `request_lifecycle_check` 25, `circuit_layout_check`
4, `editor_renames_check` 8, `graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check`
14. New: `run_control_check` 178 (172 before): after the pause for connection failures Run status reads "paused ·
connection failures" and its State row "paused (connection failures)" (`run-6b-paused-by-itself.png`); the failure's
line ends with "Why each evaluation failed is in Data tables (evaluations: status and diagnostics)."; beside "A failed
run cannot be continued." stand that sentence, "Fix the cause, then Start a new run." and Show evaluations, Export status
still last (`run-6c-failed.png`); with Data tables left on the parameters, oldest first, Show evaluations opens it on the
evaluations, newest first, the keyboard on its tab, and sends nothing (three set-up steps around it); changed: the
pause's line in its new words. `run_list_check` 180 (177): a failed run that kept a save point, shown from its Details,
says "The details are in the errors log (Logs, errors). Fix the cause, then Start a new run; Load run in Runs... brings
this run's model into it (Fine-tune or Evaluate only)." beside the reason SIF-90 pins, unchanged, and Show errors opens
Logs on the errors log, the keyboard on its tab (and a set-up step back). `export_check` 38 (37): on its real MOCK run of
12 evaluations, whose steering check gave the verdict (spread 0.144, bonus 0.401), the line reads "exploration bonus
(latest update): 0.401." and "At its end: The network is still choosing close to random: ... gives the next run room to
learn." in grey, nothing in orange (`export-1-status.png`). `calibration_check` 53 (52): the Calibration's line reads
"...; exploration bonus: none (this run does not train)." with no verdict (`calibration-1-proposals.png`). The new checks
ask for words and elements the code before did not draw (the next step, its button, "connection failures" in Run
status, "At its end:", "none (this run does not train)"); they were not run on it. `reward_v21_check`, stand-alone and
never run here, asks that `.steering-check` include "The network is still choosing close to random:", which a live and
an ended run's line both do. In all 58 scripts, 3,001 checks: the 2,990 of SIF-136 and the 11 new ones.

**Review follow-up.** The review of ad784b6 found three slips; all three are real. (1) `failedWhere` sent a failed run
to the errors log for every stop reason but three, and for none at all, while the backend writes nothing there in two
real cases. A start that failed - a task blocked, or `_record_failed_start` (worker.py: an import or a schema error,
"effective_config.json no longer matches the task this run was created for") - writes `status.json` as failed with its
error and no stop reason, before the engine opens its logs; the traceback goes to `logs/worker.log`. And a run that used
its budget but whose lanes or schematic were not restored at its end is turned failed there (engine_finalization.py),
the problems in its error alone, its stop reason still `budget_exhausted`. Run status read "The details are in the
errors log (Logs, errors). Fix the cause, then Start a new run." beside a Show errors that opened an empty list, and the
line under the header ended with the same sentence: the empty log this entry says it spared a run stopped by its failed
evaluations. `frontend/src/format.ts`: the errors log only for the four stop reasons the engine gives a run as it logs
what raised - `exception`, `evaluation_exception`, `persistence_failure`, `checkpoint_incompatible` -, the evaluations
table for `consecutive_failures` as before, and nothing more for any other failure, which its error says alone, with no
Show button. (2) Run status promised "; Load run in Runs... brings this run's model into it (Fine-tune or Evaluate
only)." for every failed run that kept a save point, while the Runs window greys Load run out for a run whose task is no
longer registered, or that names none (`loadBlocked`), and the Details beside Run status say "Not offered" - SIF-90's
own sentence there leaves the promise out. `frontend/src/panels/RunTabs.tsx`: `StatusTab` takes the run's line of the
run list (`row`; `frontend/src/panels/BottomPanel.tsx` looks it up while Run status is shown) and, for a failed run that
kept a save point, reads the registered tasks as the Runs window does (`tasksShared`: one read within 10 s); Load run is
named only where `loadBlocked` offers it - not before the tasks are read, nor for a run the list does not hold. (3) An
ended run that trains read "no update was made" whenever its steering check had no bonus, and the backend leaves the
bonus out for updates made and not recorded too: the Learner-update log off in Output settings (engine_preparation.py
then makes no learner_updates table), a latest update whose temperature or log-probability is not finite, rows not
flushed yet. The Learner updates tile under the line gives the engine's own count, thousands. `SteeringCheck` says "no
update" only while that count is 0 - "no update was made" at the end, "no update yet" before - and otherwise "none
recorded", "none recorded yet" while the run can go on: a live run with the log on read "no update yet" beside a
counting tile until its first flush (every 64 evaluations by default). `docs/workbench.md` (the line under the header,
the Run status tab, the steering line) and `docs/functionality-reference.md` (Start → Pause → Resume, Steering warning,
Run status) say the three rules. Only words, and one read of the registered tasks: nothing starts, continues or stops a
run, saves a task or writes to Virtuoso, and every question is asked as before. `tsc` clean. `run_list_check` 184 (180
before), new: CRASHED's steering line, no update counted, reads "...: no update was made."; ORPHAN, a failed run that
kept a save point, its task no longer registered: Load run and New run like this off, no Continue..., and after Show
results Run status reads "The details are in the errors log (Logs, errors). Fix the cause, then Start a new run.", still
so a second later, with "...: none recorded." beside its 36 updates; changed: CRASHED's stop reason is the engine's for
a crash, `exception` (`error`, its reason before, is none the engine gives and now names no place), its next step is
waited for until the tasks are read, and the window lists ten runs. `run_control_check` 181 (178): a live run's steering
check with no bonus reads "none recorded yet" beside 6024 updates and "no update yet" with none counted. `export_check`
38: its expectation follows the rule (its MOCK run made 2 updates, bonus 0.401). A probe run of the new checks on the
source of ad784b6 failed the three that read the changed words - ORPHAN's two and the live "none recorded yet" - and
passed CRASHED's, which reads as before; there the SIF-90 focus check after the form's Continue in section 9, which
waits 2 s, failed once too, a timing flake: it passed on this tree. One lane, after the memory guard, all passed the
first time: `calibration_check` 53, `export_check` 38, `run_control_check` 181, `run_list_check` 184,
`request_lifecycle_check` 25; then every other script the runner runs (the three reward_v2/v21 ones are never run here):
`run_control_live_check` 23, `training_tab_check` 139, `dom_identity_check` 56, `connection_panel_check` 101,
`virtuoso_source_check` 123, `task_save_check` 93, `testbench_probes_check` 43, `spec_equations_check` 88,
`model_chooser_check` 139, `output_panel_check` 98, `task_rows_check` 57, `typing_check` 62, `sheet_check` 63,
`find_fill_copy_check` 50, `project_help_check` 62, `working_copy_check` 35, `files_tab_check` 43,
`launch_recovery_check` 20, `blocking_issues_check` 66, `corner_check_check` 42, `task_list_check` 105,
`editor_columns_check` 45, `looks_check` 83, `network_panel_check` 74, `ngspice_window_check` 43, `unsaved_rows_check`
28, `calibration_save_check` 23, `save_now_check` 29, `task_run_check` 39, `pdk_check` 46, `reliability_check` 22,
`room_check` 31, `graph_view_check` 69, `module_fold_check` 31, `reward_block_check` 34, `circuit_source_check` 17,
`encoder_models_check` 24, `agent_window_check` 33, `formula_bar_check` 21, `matched_devices_check` 38,
`model_structure_check` 33, `mode_suggestion_check` 20, `consistency_check` 14, `training_data_check` 124,
`crash_panel_check` 11, `callouts_check` 8, `edit_state_check` 28, `circuit_layout_check` 4, `editor_renames_check` 8,
`graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14. In all 58 scripts, 3,008
checks: the 3,001 of SIF-137 and the 7 new ones; no flakes.

### SIF-138 The calibration line calls each proposal a Scale, the page says how to update the task once it holds the Scale, and a Scale Apply could not write is named (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found the calibration's words naming
the wrong thing, or a button that was not there. The "Calibration ready" line read "Calibration ready for real:ring_osc:
osc_frequency_hz 100 MHz. Proposed from 64 random designs; nothing has changed yet." beside a Specs row of 1.1 to
1.3 GHz: only the alpha was named ("Initial alpha 0.029"), so the Scale read as a measured frequency, and "score 0.087"
as a score (S12-4, `calibration-save-0-line.png`, `calibration-0b-ready-line.png`). Once the page holds the Scale -
after Apply only, or after an Apply and save whose save could not start - Apply and save is no longer offered (`saves`,
calibrationPlan.ts) and a greyed Apply calibration stands alone, yet the block said "Saving could not be started from
here (the save of real:ring_osc is still running): try Apply and save again when ready, or use Save as above the
editors." and, after Apply only, "The page holds these values. Use Apply and save to update this task and keep its
recorded baseline, or Save as to create a new task." (S12-5, `calibration-save-3-busy.png`). Save as always makes a new
task (TaskSave.tsx: `as_new` whenever a task is open), so the one way to update the open task is Undo, then Apply and
save, and no line said so. With the limits of a row edited after the run and the Initial alpha applied, the hint read
"The page holds these values." beside "0.087 not applied: the limits of this row were changed after the run", and
nothing said how to get a Scale for the new limits (S12-21, `calibration-2-row-changed.png`). The plan, checked against
the code, missed two more of the same. The block added its "Use Apply and save" sentence whenever the page held the
values and the block itself had not pressed Apply and save: also right after the line's Apply and save had saved the
task with them (`calibration_save_check` read only the hint's first sentence there), after a reload and for values held
before. And Apply calibration, which a saved task gets only while the page holds every Scale (an Initial alpha still to
apply), named Apply and save in the line's tooltip and in the block's hint.

**Changed.** `frontend/src/panels/calibrationPlan.ts`: each Scale on the line says it is one, "Calibration ready for
real:ring_osc: Scale of osc_frequency_hz 100 MHz.", the Initial alpha as before. A new `afterApplied(where)`: " To
update this task with them, press Undo, then Apply and save (it keeps the recorded baseline); Save as makes a new task."
A save that could not start (`savingText`): " Saving could not be started from here (the save of real:ring_osc is still
running). The Scale stays applied: once the save can start, press Undo, then Apply and save; Save as above the editors
makes a new task instead." `afterwards` stays for the line's Apply only tooltip, before the press.
`frontend/src/panels/RunTabs.tsx` (the Calibration block of Run status): the hint gives `afterApplied` after the block's
own Apply only, while the page holds the values - not after an Apply and save (its own line says what happened), a
reload (the Undo history does not outlive one), values held before, or once something is pending again (an effect
forgets the press: an Undo, then the line's Apply and save, would otherwise bring the sentence back beside a saved
task). The plan's `${said ? '' : afterApplied}` would have put "press Undo, then Apply and save" beside the task the
line had just saved. When the page holds all Apply can write and a row's Scale could not be written: "The page holds the
values Apply can write. The Scale of score is not applied: its limits changed after the run; a new Calibration proposes
one for them." (several rows: "a, b and c ... their limits changed after the run; a new Calibration proposes one for
each"). The hint "Sets ..., as one Undo step." loses `afterwards`: there it always named an Apply and save that was not
offered. `frontend/src/page/calibrationOffer.ts` (the line's answers): Apply only says `afterApplied`, a save that could
not start `savingText`, both with " under Run status of that run" after Apply and save, as the line goes with any answer
(Not now's words name the same place); after the line's Apply calibration, which writes no Scale this task lacks,
nothing more. `frontend/src/App.tsx`: the line's Apply calibration tooltip loses the sentence too. Only words, and one
press remembered for them: nothing starts, continues or stops a run, saves a task or writes to Virtuoso without the
press and question it took before; Apply and save saves only on its press, and every Undo step is as before.
`docs/workbench.md` (Apply and save, the line under the header, Apply writes only what still fits) and
`docs/functionality-reference.md` (the Calibration and Calibration ready rows) say it. Left out, as the plan left them:
S12-5's best fix, a button that saves the task with the values the page holds (a new press that saves), and S12-22,
whose contradiction is in the backend's note (calibration.py `too_few`), for a backend round.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. `calibration_save_check` 33 (23
before). Changed: the line reads "Scale of osc_frequency_hz 100 MHz" (`calibration-save-0-line.png`); after the line's
Apply and save saved the task, the hint is "The page holds these values." and no more; after the block's Apply only it
reads "... To update this task with them, press Undo, then Apply and save (it keeps the recorded baseline); Save as
makes a new task." beside the lone Apply calibration; the block's Apply and save during another save reads the new
refusal, with "The page holds these values." alone beside the button (`calibration-save-3-busy.png`). New: the page
loaded during that save, the line's answer removed, offers the line too: its Apply and save applies and sends nothing,
and the page says why and "press Undo, then Apply and save under Run status of that run", the line gone; one Undo then
takes the Scale back and Apply and save is offered again; after the save has ended, the line's Apply only writes the
Scale, sends nothing and says how the task is updated and where, the block saying only that the page holds the values;
and with a FIXTURE Initial alpha of 0.02 beside the held Scale, the line's Apply calibration tooltip and the block's
"Sets the Scale of 1 Specs row and Initial alpha, as one Undo step." name no Apply and save. `calibration_check` 54
(53): its two lines read "Scale of score ..." (`calibration-0b-ready-line.png`), and, new, after the edited row's Apply
the hint names score (`calibration-2-row-changed.png`). A probe run of both on the code before (the sources as at HEAD,
put back after, their sums compared) failed exactly the checks that read the changed words: 10 of 33 in
`calibration_save_check` - its four new set-up steps (the line's presses apply and send nothing, one Undo, the line back
after a reload) pass there - and 3 of 54 in `calibration_check`. Then the scripts that draw a calibration run's Run
status or the line, on the final source, all passed the first time: `calibration_check` 54, `run_control_check` 181 (its
live Calibration, whose block now works out the plan before it returns early), `training_tab_check` 139,
`run_list_check` 184, `task_save_check` 93, `calibration_save_check` 33, `callouts_check` 8. One flake, in a run of the
same seven on the first form of the change: `task_save_check` stopped after 33 checks with "the DevTools session closed
(its window went away)" in its task file window (SIF-93's part, not touched here), and passed 93 alone. The other
scripts draw neither the line nor the block and were not run.

**Review follow-up.** The review of 2cdcb5b found four slips; all four are real. (1) A save that could not start said
"once the save can start, press Undo, then Apply and save", and one of the two reasons the docs name, no connection
chosen, ends with a choice that is an Undo step of its own (Connection.tsx `setProfileId`, App.tsx's `setConfig`,
history.ts records by default): the Undo as told took back that choice, the Scale stayed, Apply and save stayed away,
and the next one was refused again. `savingText` puts Undo first: "The Scale stays applied: press Undo, then, once the
save can start, Apply and save; ...", true for every reason. (2) Those words, and Apply only's "press Undo, then Apply
and save", outlived the Undo they ask for - the block's `said` line, which only another press or run took away, and the
message line under the header: "The Scale stays applied" was untrue there, and a second Undo would take back an earlier
edit (SIF-132's rule). `frontend/src/panels/RunTabs.tsx` forgets `said` with the Apply only press once something is
pending again; `frontend/src/page/calibrationOffer.ts` keeps the message of an answer that asks for an Undo with the
result it applied, and takes it away once the page no longer holds that result's values, a newer message left alone.
Both stay while the page holds the values, so an edit made between the press and the Undo still takes the first Undo,
as any Undo does. (3) The block tested "There is nothing to apply." before the rows Apply cannot write, and `proposals`
counts only rows still as the run simulated: a run whose only proposal was the Scale of a row edited since - a second
Calibration often proposes no Initial alpha (7.217) - said only that. `held` now covers it and names the row. (4) "a new
Calibration proposes one for them" promised what calibration.py does not always do: a row fewer than 8 random designs
miss gets no Scale (MIN_MISSES), and a loosened limit is missed less. It reads "a new Calibration works one out for the
new limits when enough random designs miss them" ("for each row's new limits" for several). `docs/workbench.md` and
`docs/functionality-reference.md` say all four. Only words, and when they go: nothing starts, continues or stops a run,
saves a task or writes to Virtuoso, and every Undo step and question is as before. `tsc` clean. One lane, after the
memory guard: `calibration_save_check` 38 (33 before): both refusals in the new order; new, the message line goes with
the Undo after the line's refused Apply and save and after its Apply only, the block's line with the Undo after its
refused save (the check reloaded there before, so never saw it), and with the row's Lower made 1 GHz the hint reads
"There is nothing to apply. The Scale of osc_frequency_hz is not applied: ..."; an Undo and the block's Apply only
(nothing sent) then hold the Scale again for the part after. `calibration_check` 54: the new words. A probe run on the
sources of 2cdcb5b (put back after, their sums compared) failed exactly those, 6 of 38 and 1 of 54. On the final
source all passed the first time: `calibration_check` 54, `run_control_check` 181, `training_tab_check` 139,
`run_list_check` 184, `task_save_check` 93, `calibration_save_check` 38, `callouts_check` 8 (7 scripts, 697 checks).

### SIF-139 A blocked task says why in the Tasks list, the ngspice task's line has a button to the Connection window, and a page with no task reads plainly (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found four places where the page had
the words the user needed and did not show them, or showed the wrong ones. The Tasks list marked an unavailable task
with a bare "[blocked]" in amber and no tooltip (S12-9, `task-list-2-window.png`), though the Task column's help says "A
mark says what keeps it from running now", the ngspice row's mark does say it ("[ngspice: choose its connection]"), and
the list answer holds the reason (`blocker`), shown only in Details ("Blocked by"). What blocks a saved Virtuoso task is
the connection's problem, one for all of them (tasks.py `list_tasks`): with a connection problem every such row read
"[blocked]" and no reason was in view. The ngspice task's line under the editors' toolbar read "This task runs on
ngspice. Choose an ngspice connection in the Connection window." with no button (S12-13, `ngspice-3-task.png`), while in
the Roadster look the header's pill shows a chosen connection's name, its word "Connection" for screen readers only:
nothing on the page carried the name the line used. SIF-108 gave such lines Connection... in the Virtuoso and Agent
windows; this one was not on its list. A fresh page's header read "no task chosen   unspecified · unspecified · not set"
(S12-30, `connection-1-header.png`): the configuration's default labels, their keys "Class · PDK" and "RL model" hidden
by the look. And a configuration saved with the removed Spectre netlist source - Import JSON of one exported before
record 7.53 still brings it - said "The workbench no longer imports netlists: choose a task, or a Virtuoso cell, in the
Tasks window ..." (S12-32, `source-1-saved-netlist.png`), while the Tasks window offers "New task: From an ngspice
netlist...".

**Changed.** `frontend/src/panels/TaskList.tsx`: `taskMark` takes `withReason`, which the Tasks list's rows and its
filter pass: a blocked task's mark reads "[blocked: <its blocker>]" - "[blocked: FIXTURE: the connection file names no
library for it]" -, and a mark's tooltip is the whole blocker, an ngspice task's too. The Task column's help says "(the
whole reason on hover)". `TaskListButton` takes `currentMarkTitle`, the tooltip of the tab line's mark, which keeps
"[blocked]": for a task that cannot be loaded, the "Blocked: <reason>" line under the toolbar says why in view (the
review follow-up below). `frontend/src/roadster.css`: the list's
amber mark takes two lines at most, cut with "...", and 32 characters' width at most, so a reason as long as a
connection file's path leaves the Task column as wide as the fixture's does (about 200 px; 175 px before); the
SIF-107/108 rules for a line with its action at its end cover `.task-status > .line-act`, the task's lines being drawn
into `.task-status` (Editors.tsx), not straight under `.editors`, and its words keep the 4 px above and below that the
task's other lines have. `frontend/src/panels/Left.tsx`: the tab line's mark gets the followed task's blocker as its
tooltip; the ngspice line is `div.line-act.connection-problem`, the backend's words with **Connection...** at their end,
which opens the Connection window from the page as the header's button does (`openConnection`, openAt.ts) and checks
nothing; `TitleFacts` draws no facts while the page follows neither a task nor a cell, so "no task chosen" stands alone,
and a label left "unspecified" reads "no class" or "no PDK" ("opamp · no PDK" for the saved ngspice task); the netlist
note reads "The workbench no longer imports Spectre netlist files (.scs): choose a task or a Virtuoso cell in the Tasks
window (the task's name on this tab line)." and, while the ngspice way is offered, "A SPICE deck for ngspice can become
a task there: New task, From an ngspice netlist...". Changes from the plan: "imports", the word of the backend's own
refusal (task_registry.py `NETLIST_SOURCE_REMOVED`), where the plan had "reads"; the clamp's width, which the plan had
not: a table gives a column room by its widest line, so two lines alone would have let a long reason widen the Task
column; the filter, which reads the reason as the row shows it; and Connection...'s tooltip, "as the connection button
in the header does", true with no connection too, where the pill reads "Connection none chosen". Only words, tooltips
and a button that opens a window: nothing starts, continues or stops a run, saves a task or writes to Virtuoso, and
every question is asked as before. `docs/workbench.md` (the title block; the Tasks window's mark and its Task column;
the removed netlist source; how an ngspice run works, whose sentence said "the column" and that the Task list leaves the
ngspice tasks out, untrue since records 7.362 and 7.227) and `docs/functionality-reference.md` (Title block, Task,
Task-name button, the Connection button's row, Real runs on ngspice) say it. Seen, not changed: workbench.md's "Which
way to a new task the Tasks window offers" still says the Registered task list leaves the ngspice tasks out while a
Virtuoso connection is in use (since record 7.227 the Tasks window lists every task, marked), and the backend's refusal
still sends the user to "Circuit source".

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. First the six scripts that draw
what changed, all passed the first time: `connection_panel_check` 101, `virtuoso_source_check` 123,
`ngspice_window_check` 46 (43 before), `task_list_check` 106 (105), `looks_check` 83, `circuit_source_check` 17. New:
`task_list_check`: the blocked row reads "fixture_ldo[blocked: FIXTURE: the connection file names no library for it]"
(`task-list-2-window.png`), its mark's tooltip is the blocker, and a far longer reason written into the mark takes two
lines, cut, the Task column as wide; with no task the header's title block holds "no task chosen" and no facts.
`ngspice_window_check`: the line reads the backend's words with Connection... beside them, its tooltip saying what it
opens and that opening checks nothing (`ngspice-3-task.png`); the tab line's mark has the blocker as its tooltip and the
header reads "opamp · no PDK"; the press opens the Connection window from the page and sends nothing. Changed:
`task_list_check`'s blocked mark and its no-task title; `circuit_source_check`'s title, no facts beside "no task
chosen", and its note's sentence, now with the ngspice way, offered as no connection is chosen
(`source-1-saved-netlist.png`). Then every other script the runner runs (52; the three reward_v2/v21 ones are never run
here), all passed the first time, no flakes: `calibration_check` 54, `export_check` 38, `run_control_live_check` 23,
`run_control_check` 181, `training_tab_check` 139, `dom_identity_check` 56, `run_list_check` 184, `task_save_check` 93,
`testbench_probes_check` 43, `spec_equations_check` 88, `model_chooser_check` 139, `output_panel_check` 98,
`task_rows_check` 57, `typing_check` 62, `sheet_check` 63, `find_fill_copy_check` 50, `project_help_check` 62,
`unsaved_rows_check` 28, `calibration_save_check` 38, `working_copy_check` 35, `files_tab_check` 43,
`launch_recovery_check` 20, `blocking_issues_check` 66, `corner_check_check` 42, `editor_columns_check` 45,
`network_panel_check` 74, `save_now_check` 29, `task_run_check` 39, `pdk_check` 46, `reliability_check` 22, `room_check`
31, `graph_view_check` 69, `module_fold_check` 31, `reward_block_check` 34, `encoder_models_check` 24,
`formula_bar_check` 21, `matched_devices_check` 38, `model_structure_check` 33, `mode_suggestion_check` 20,
`agent_window_check` 33, `consistency_check` 14, `training_data_check` 124, `crash_panel_check` 11, `callouts_check` 8,
`circuit_layout_check` 4, `edit_state_check` 28, `request_lifecycle_check` 25, `editor_renames_check` 8,
`graph_paint_check` 6, `network_inputs_check` 9, `table_view_check` 10, `unit_text_check` 14. In all 58 scripts, 3,028
checks: the 3,008 of SIF-137, the 16 that SIF-138 added and the 4 new ones. A probe run of the three changed scripts on
the sources as at HEAD (put back after, their sums compared) failed exactly the 8 checks that read the changed words, 3
of 106, 3 of 46 and 2 of 17; there the Task column was 175 px wide and the long reason took five lines. After the probe
the ngspice press reads the line with `?.`, so a missing line fails its check instead of stopping the script, and two
comments were reworded: the six scripts again on the final source, all passed the first time, the same counts.

**Review follow-up.** The review of 0d6db53 found two slips; both are real. (1) The reason given here for the tab line's
bare "[blocked]" - the "Blocked:" line under the toolbar says why - holds only for a task that cannot be loaded: that line
(Left.tsx) is drawn only when the load fails. A Maestro task saved before such tasks could run is listed blocked (tasks.py
`list_tasks`, `MAESTRO_NOT_RUNNABLE`) and loads all the same (`_generated_runtime`; only a run of it is refused), so its
reason was on the mark's hover and among the circuit's notes, folded in the circuit column, and nowhere else. The comment
(TaskList.tsx `taskMark`), `docs/workbench.md` and "Changed" above now say so. The chip keeps its bare mark: it is one
line of 420 px at most, cut with "...", where the reason would end after a few words; it is whole on hover. (2) The
netlist note named "a Virtuoso cell" whatever the connection, while with an ngspice connection in use the Tasks window's
New task row has no "From a Virtuoso cell..." (taskActions.ts `showVirtuoso`): `frontend/src/panels/Left.tsx` names it
only while that window offers it, as the note already did for the ngspice way; `docs/workbench.md` says it. Only words:
nothing starts, continues or stops a run, saves a task or writes to Virtuoso, and every question is as before. `tsc`
clean. One lane, after the memory guard: `circuit_source_check` 19 (17 before). New: the page loaded again with the saved
configuration and a fixture connection in use - with an ngspice one the note reads "... choose a task in the Tasks window
(the task's name on this tab line). A SPICE deck for ngspice can become a task there: New task, From an ngspice
netlist..." and names no Virtuoso cell (`source-3-ngspice-connection.png`); with a Virtuoso one it names the Virtuoso
cell and not the deck; neither page asks to load a circuit. A probe run on Left.tsx as at 0d6db53 (put back after, its sum
compared) failed exactly the ngspice one, 1 of 19. On the final source, before the probe and again after it, all passed
the first time: `circuit_source_check` 19, `task_list_check` 106, `ngspice_window_check` 46.

### SIF-140 The RL model window offers no Use for a save point it says cannot be loaded, says what to do when there is no saved model, and marks a template whose values this run changed (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found three places where the RL
model window said one thing and offered or marked another. In a model's Details, the save point checked against the
task on the page read "NOT compatible for Fine-tune - it cannot be loaded, and a run never falls back to New model" in
red under an enabled "Use this save point" (S12-15, `models-2-details.png`): ModelChooser.tsx turned Use off only in New
model and while a Use was reading, never by the check's answer. That picture's network keys are the fixture's (since
SIF-85 the Details check a model with its own network), but a real check still answers NOT compatible on what a model
cannot bring along - the circuit graph schema, the goal/spec input schema, the preprocessing, real or synthetic origin,
an older save's checkpoint version (checkpoints.py) - a MOCK model with a real task, say. Use then chose the model and
closed the window, and the main page said "Review the settings in RL model... - the saved model is NOT compatible with
this run". With an empty output folder - a first Fine-tune or Evaluate only - the amber line still read "No saved model
is chosen yet: Evaluate only needs one. Use a save point below (...)" over no rows, and the empty list's hint said a run
saves one "every N evaluations while it runs ("Model checkpoints" in the output settings must be on)", a literal N,
while the interval is in the configuration (S12-16, `models-3-real.png`). And in New model, after a restored
configuration or a New run like this from an older run, the templates table marked the Graph Transformer row "in use"
beside the template's own values, 48/4/4 and alpha 0.01, while the box under its settings said "This run's values differ
from the Graph Transformer template (starting preset)" and the "In use" line read "current run settings" (S12-38,
`network-5-restored-differences.png`).

**Changed.** `frontend/src/panels/ModelChooser.tsx`: in a model's Details the Use of the save point checked is off while
that check answers NOT compatible, its tooltip "Use this save point: it cannot be loaded with the task on the page - see
NOT compatible below."; the answer is that one save point's - useRequest drops it at another save point or an edit, and
the check runs again 0.5 s after the edit - so the save points not checked keep their Use, as does one the check could
not compare with an incomplete configuration. `SavedModels` takes `noneChosen`, the line asking for a model, and draws
it where RlModelWindow drew it, above the list's toolbar; once the list has answered empty it draws instead, under the
count, "No saved model yet under this output folder: run New model first, or set Output root in Output settings to the
folder that holds your models." and when a run saves one. That sentence, also the empty list's hint while a model is
chosen and in New model's look, is written from the Output settings a run started now gets, the interval read as Output
settings reads it (an absent field is 200 evaluations): "A run saves one when it is paused, stopped or finished, and
every 200 evaluations while it runs.", "every 600 seconds" in seconds, the clause left out with no interval, and with
Model checkpoints off '"Model checkpoints" is off in Output settings: a run saves a model only with it on.'.
`frontend/src/panels/RlModelWindow.tsx`: passes that line to SavedModels in Fine-tune and Evaluate only while no model is
chosen (New model's look passes none); `TemplatesTable` takes `differs`, useRlModel's, which draws the comparison box
(#network-differences): the template chosen reads "chosen - this run's values differ (see below)" in amber while it
holds, "in use" only while this run's values are the template's, and "see below" scrolls the box to the middle of the
window's own document. Changes from the plan: the next-step line names the field, Output root, and leaves when a run
saves to the shared sentence, as the plan's "(it saves one when it pauses, stops or ends)" is untrue with Model
checkpoints off - such a run saves no model at all, at its end neither (engine.py `_checkpoint`; runs.py: "it keeps no
saved model") -, and for the same reason the off sentence is not the plan's "so a run saves none while it runs"; a
configuration holding both intervals (only from a file, and validation refuses it) reads "every 200 evaluations or every
600 seconds"; and the link's double click stays its own, as on the row it would put the template's values back
(chooseEncoder of the template in use applies its values, one Undo step). Not changed, as the plan says: a double click
or Enter on a model's row still takes its newest save point whatever its Details' check says; Use the newer one and
SIF-36's key lines are as they were. Only a button turned off, words and a link that scrolls: nothing starts, continues
or stops a run, saves a task or writes to Virtuoso, and every question is asked as before. `docs/workbench.md` (New
model's templates, the comparison, "Using one is a press" and nothing filled in by itself) and
`docs/functionality-reference.md` (Templates, Saved models) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. The three scripts of the plan, all
passed the first time: `model_chooser_check` 145 (139 before), `network_panel_check` 78 (74), `output_panel_check` 98 (its
panel still has no "every N evaluations"). New: `model_chooser_check`: with D's newest save point answered NOT
compatible its Use is off with the tooltip, the older one's on (`models-2-details.png`); the empty list with C in use
reads the hint with "every 200 evaluations", then, changed in the main page's Output settings, "every 200 seconds", no
interval, and Model checkpoints off, and back; on the real route of the scratch backend (Evaluate only, none chosen,
none listed) the one line asking for a model reads the next step (`models-3-real.png`). Changed there: the notice's
set-up chooses D by a double click on its row, its Use being off once its check answers. `network_panel_check`: the
restored configuration's template row reads "chosen - this run's values differ (see below)", the box out of view at the
window's top comes into view at "see below" with nothing written, and the row reads "in use" again after Use the
template's values (`network-5-restored-differences.png`). Then the other scripts that draw the RL model window's
templates or saved models, all passed the first time, their counts as in SIF-139: `dom_identity_check` 56,
`task_rows_check` 57, `typing_check` 62, `looks_check` 83, `pdk_check` 46, `reliability_check` 22, `graph_view_check`
69, `reward_block_check` 34, `encoder_models_check` 24, `model_structure_check` 33, `network_inputs_check` 9. A probe
run of the two changed scripts on ModelChooser.tsx and RlModelWindow.tsx as at HEAD (put back after, their sums
compared) failed exactly the new checks, 7 of 145 and 2 of 78. After it the link's press in `network_panel_check` reads
`?.`, so a missing link fails its check instead of stopping the script, and the three scripts of the plan passed again
on the final source, the same counts. No flakes.

### SIF-141 The blocking-issues list names each place in the editors' and windows' words, and "validating..." has no tick (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found the header's list of blocking
issues naming its places in the configuration's own notation (S12-11, `issues-2-open.png`): the check's code had a
column of its own ("range_inverted", "heads_divisibility", "schema"), and Where was the path - "parameters[0].lower row
input_pair_width" (the button SIF-95 made of it, in "the words it had"), "run.network", "(whole configuration)"; with the
tables' own issues (`issues-4c-scale.png`) "targets[0].normalization_scale row score" and a bare "parameters" and
"targets". SIF-5 and SIF-51 had moved the same codes, table keys and field names into the tabs' and confirmations' words.
An issue of a run setting - a real heads_divisibility, pdk_not_loaded or encoder_spec_input_mismatch - named no window to
go to. A refusal of a configuration the backend cannot read wrote the same paths: Matched devices said
"run.max_evaluations: max_evaluations is missing: this field needs a value." (`matched_devices_invalid.png`; api.ts
`schemaProblem`, which Save task and the other refusals use too). And on every page open the header read "Validating..."
with the done tick before it until the first validation answered (S12-24, `run-7-taken-over.png`, and the calibration
checks' header pictures): Issues.tsx drew the busy word as span.ok, and the look draws its tick before every span.ok of
the header.

**Changed.** `frontend/src/panels/editorRules.ts`: `placeOf(path, config, keys)`, with no React, so the list and the
refusals share it. A row reads as its tab's name, the row's ID in the configuration the report is about - "row N" where
no ID names it, both where another row of the table holds the same ID, as a duplicate does ("Parameters ·
input_pair_width (row 5)") - and its field by the header of the column it is chosen in (`fieldLabel(columnOf(...))`):
"Parameters · input_pair_width · Lower", "Specs · score · Scale", a Spec's objective as its Limit. A table's own issue
reads "the Specs table", no path "the whole configuration". A run, output or research setting reads as the place that
sets it, the first of a list of patterns: in the RL model window Components (run.network.vocabulary), Network inputs (the
six transferable-input fields), Network (any other run.network), "Fine-tune: its own settings" (a bare run.advanced -
fine_tune_only_option, the one check that names it - and Freeze encoder, Encoder-only transfer, Reset critic), Advanced,
Mode, Saved models, and the window alone for the model's name, Evaluate only's actions and Continual learning; in Run
configuration Reward and conditions, Training conditions, Concurrent Spectre jobs, Evaluation budget, Random seed, Stop at
the first feasible design and the five Limits by their labels ("Run configuration · Limits · Max retries per
evaluation"), any other run setting "Run configuration"; then "Output settings", "Research experiments", and "Tasks
window" for the task's own fields. A path none of these knows stays as written; pydantic's dotted index
(parameters.3.variable_id, from an older backend) reads as the report's. `frontend/src/panels/Issues.tsx`: the list has
four columns - #, Level, Where, Message - and Where is placeOf's words, a row's still the button that goes there (SIF-95);
the field and the check's code are on the Where's hover ("Field run.network, check heads_divisibility.", after a row's "Go
to ..." sentence), the code also the row's `data-code`, and the column's header says so. Until the first validation
answers the header's words are `span.hint.validating`: grey, with no tick. `frontend/src/api.ts`: `schemaProblem` names
each field with placeOf, a row by its number, as a refusal holds no configuration ("Run configuration · Evaluation budget:
max_evaluations is missing: this field needs a value; Parameters · row 2 · ID: ..."); editorRules.ts imports api.ts for
its types only, so no import goes round at run time. `frontend/src/roadster.css`: "validating..." keeps its width in the
header as "configuration valid" does and is capitalised as it is; the tick stays on span.ok alone. Changes from the plan:
Components and Network inputs for the run.network fields the window shows under those labels (the backend's own warning
says "RL model window, Components"); a bare run.advanced as "Fine-tune: its own settings", its one check being of
Fine-tune's switches, which are ticked there and not in the Advanced fold; the reward and the training conditions under
"Run configuration", the module that holds them; the window alone for its three settings with no heading of their own,
and "Tasks window" for the task, where the plan left circuit.* as written; the row's number after a shared ID, which the
path gave by its index and the ID alone would not; no wait icon; and the page-open check in `blocking_issues_check`,
which answers every validation itself and so can hold the first, where the plan named `run_control_check` and the
calibration checks, whose validation goes to the scratch backend and lasts only as long as its answer takes. Not
changed, as the plan says: no button opens the window a run setting names - no page-wide event opens the RL model
window -; the Where names it. Seen, not changed: while "validating..." shows, Start and Calibration are enabled
(`startReadiness` holds them back only on an answer that blocks); a start is validated again by the backend, which
refuses one with blocking issues (runs.py, `RunRejected` "The configuration has blocking issues"), and a real run still
asks first. Only words, a tooltip and a column: nothing starts, continues or stops a run, saves a task or writes to
Virtuoso, and every question is asked as before. `docs/workbench.md` (the blocking-issues paragraph) and
`docs/functionality-reference.md` (N blocking issues) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. First the three scripts that pin the
changed words, all passed the first time: `blocking_issues_check` 69 (66 before), `matched_devices_check` 38,
`editor_renames_check` 8 (it loads editorRules.ts with a RegExp and a require of its own: placeOf's patterns are literals,
and it imports nothing more). New: `blocking_issues_check`: with the page's first validation held unanswered, the header
reads "validating..." in the hint's grey, with no tick and no "configuration valid" (`issues-0-validating.png`); the list
has the four columns, and each Where's tooltip gives the field and the code (`issues-2-open.png`); the tables' own issues
read "the Parameters table" and "the Specs table", a spec's "Specs · score · Unit" and "Specs · score · Scale"
(`issues-4c-scale.png`). Changed there: the rows' cells (the code read from `data-code`); the Wheres in words -
"Parameters · <ID> · Lower", "RL model window · Network", "the whole configuration", the rejected IDs' "Parameters · <ID> ·
ID", the older backend's "Run configuration · Evaluation budget" with its tooltip -; the duplicate's "Parameters · <ID>
(row 5)" and its Lower; and the go-to tooltips with their second line. `matched_devices_check`: its refusal has a second
field, a row's, and reads "Run configuration · Evaluation budget: ...; Parameters · row 2 · ID: ..."
(`matched_devices_invalid.png`). Then every other script the runner runs (55; the three reward_v2/v21 ones are never run
here), all passed the first time, no flakes: `calibration_check` 54, `export_check` 38, `run_control_live_check` 23,
`run_control_check` 181, `training_tab_check` 139, `dom_identity_check` 56, `connection_panel_check` 101,
`virtuoso_source_check` 123, `run_list_check` 184, `task_save_check` 93, `testbench_probes_check` 43,
`spec_equations_check` 88, `model_chooser_check` 145, `output_panel_check` 98, `task_rows_check` 57, `typing_check` 62,
`sheet_check` 63, `find_fill_copy_check` 50, `project_help_check` 62, `calibration_save_check` 38, `files_tab_check` 43,
`launch_recovery_check` 20, `working_copy_check` 35, `corner_check_check` 42, `task_list_check` 106,
`editor_columns_check` 45, `looks_check` 83, `network_panel_check` 78, `ngspice_window_check` 46, `unsaved_rows_check` 28,
`save_now_check` 29, `task_run_check` 39, `pdk_check` 46, `reliability_check` 22, `room_check` 31, `graph_view_check` 69,
`module_fold_check` 31, `reward_block_check` 34, `circuit_source_check` 19, `encoder_models_check` 24,
`formula_bar_check` 21, `model_structure_check` 33, `mode_suggestion_check` 20, `agent_window_check` 33,
`consistency_check` 14, `training_data_check` 124, `crash_panel_check` 11, `callouts_check` 8, `edit_state_check` 28,
`request_lifecycle_check` 25, `circuit_layout_check` 4, `graph_paint_check` 6, `network_inputs_check` 9,
`table_view_check` 10, `unit_text_check` 14. In all 58 scripts, 3,043 checks: the 3,028 of SIF-139, the 2 of its review
follow-up, the 10 of SIF-140 and the 3 new ones. After the full run the Where column's header tooltip was reworded (no
check reads it). A probe run of the three scripts on the four sources as at HEAD (put back after, their sums compared)
failed exactly the checks that read the changed words, columns and tooltips and the page-open state, 16 of 69 and 1 of
38; `editor_renames_check` passed. After it, `tsc` and the three scripts again on the final source, all passed the first
time, the same counts.

**Review follow-up.** The review of b10d9d0 found three slips; all three are real. (1) The older backend's line in
`blocking_issues_check` had lost what it held. It read the Where's words, "Parameters · <ID> · ID", and placeOf reads
pydantic's dotted index by itself, so the line would have passed had App.tsx `rejected()` stopped writing
parameters.3.variable_id as parameters[3].variable_id - while rowOf, which makes the go-to button, and the editors' row
marks and tab pills (Editors.tsx) read the brackets alone: the row would have lost both unseen, and no other check sends
a dotted path. Before SIF-141 it read "parameters[3].variable_id row <ID>", which held both. The line now reads that
row's tooltip too, the go-to button's, with the field as `rejected()` writes it ("Go to <ID>: Parameters opens with its
ID chosen. The list stays open." and "Field parameters[3].variable_id, check schema."). (2) The last of the places, "Run
configuration" for any run setting, named it for settings no box there sets: run.rehearsal, the path of the blocker
rehearsal_with_transfer_inputs (validation.py), which New run like this can bring in (runWindowActions.ts copies
`rehearsal`) and no control on the page sets; run.optimizer and run.cache_policy; a bare run, where the schema refuses a
rehearsal; and the connection, which the Connection window chooses. "RL model window · Advanced" took every other
run.advanced field, and the Advanced fold has no box for spec_registry (invalid_spec_registry, unknown_unit),
simulation_timeout_seconds, episode_terminates_on_success or reset_temperature; "Output settings", the same way, every
output field, and the panel has none for keep_last_checkpoints, learner_update_log_every, flush_every_evaluations,
keep_simulator_host_folders or min_free_bytes. The Where sent the user to a place with no such control, where the path
had at least named the field, while this entry and the docs promised a setting by the panel or window that sets it and a
path the page does not know as written. The last pattern is gone; Advanced and Output settings take only the fields they
have a box for - the fold's from ADVANCED_ROWS with the alpha learning rate and the tick box, Output settings' twelve in
a list -; the connection reads "Connection window"; any other setting stays as written. (3) "Fine-tune" was written out
in the new place, where the house rule names a Mode by rlModelText.ts's MODE_NAME, and `editor_renames_check` lets
editorRules.ts load ../units alone: placeOf and its places moved into a file of their own,
`frontend/src/panels/issuePlace.ts` (no React), which builds the place from `MODE_NAME.fine_tune` and the Advanced
fields from ADVANCED_ROWS. editorRules.ts is again as it was before SIF-141; Issues.tsx and api.ts import placeOf from
the new file, which, with what it loads, imports api.ts for its types alone, if at all. The heading the place names,
RlModelWindow.tsx's "Fine-tune: its own settings", wrote its Mode out too, as "Evaluate only: its own settings" did:
both take MODE_NAME now, so the place and the heading cannot part; the window reads as before. `docs/workbench.md` and
`docs/functionality-reference.md` say it. Only words and the file that makes them: nothing starts, continues or stops a
run, saves a task or writes to Virtuoso, and every question is asked as before. `tsc` clean. One lane, after the memory
guard: `blocking_issues_check` 70 (69 before) - the older backend's row's tooltip; new, the Wheres of seven settings,
"run.rehearsal", "run.advanced.spec_registry", "Connection window", "RL model window · Advanced" for batch_size, "RL
model window · Fine-tune: its own settings" for a bare run.advanced, "output.min_free_bytes", "Output settings" for
checkpoint_every_seconds (`issues-4e-settings.png`). A probe run with `rejected()` passing the path on as it came
(App.tsx put back after, its sum compared) failed exactly the older backend's line, 1 of 70; one on the four sources as
at b10d9d0 (put back the same way) exactly the new line, 1 of 70. On the final source these passed the first time:
`blocking_issues_check` 70, `matched_devices_check` 38, `editor_renames_check` 8, and the scripts that open the RL model
window, `model_chooser_check` 145, `network_panel_check` 78, `mode_suggestion_check` 20, `network_inputs_check` 9,
`module_fold_check` 31, `reliability_check` 22, `reward_block_check` 34, `room_check` 31, `typing_check` 62,
`dom_identity_check` 56; then every other script the runner runs (45) passed the first time but `task_save_check`, which
stopped twice after 33 checks - the second time alone - at the step that presses Close inside the task file window it
closes (the harness: such a click may never be acknowledged, and the closing session rejects what still waits); alone it
then passed three times on this source, 93, and twice on the sources of b10d9d0: a timing flake of a step this follow-up
does not touch. 58 scripts, 3,044 checks: the 3,043 of SIF-141 and the one new. Two comments were reworded after the run
of the 45; `tsc` and the first three scripts passed again after it.

### SIF-142 The PDK window counts its ideal parts alike, What's missing? draws only a blocker's step in red, and one device reads "1 device" (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found three small slips of words and
colour in three windows. The PDK window headed a shown PDK's ideal parts "Ideal parts: 3 from analogLib" - the parts a
circuit can hold, the number of the Loaded PDKs column -, while their fold read "The ideal parts (4)" and its table gave
the fourth, mutual_inductor, a component analogLib states no pin order for, the kind "unknown", as if the network read it,
under a sentence saying that a circuit holding one is refused (S12-31, `pdk-window-1-shown.png`). The backend counts the
two apart (pdk_record.py `build_ideal_parts`: recognized, without_pins), so the heading, the fold and the table disagree
whenever analogLib has such a part, and IC23.1's has five. The same sentence said "the other 1 reach it as "unknown", with
their pins named" for one part. What's missing? in the Agent window drew every item's step in the accent, which in the
Roadster look is the red of an error (#f5434f beside the error's #ff4f61), so the optional step of a connection not tested
yet read like a blocker's right under "Nothing blocks a start." (S12-33, `agent-5-connection-button.png`). The backend
sends that step for every connection not tested since it started (readiness.py), the usual state after a restart. And the
circuit column's Circuit picture read "1 devices · 0 nets" for the ngspice window's one-transistor deck, its picture's
screen-reader label the same (S12-35, `ngspice-3-column.png`), where SIF-62 and SIF-117 had put every other count of the
column in the right number.

**Changed.** `frontend/src/panels/Pdk.tsx` (`IdealParts`): the heading keeps its count; the fold counts the same parts
and those with no pin order apart, "The ideal parts (3, and 1 refused)"; such a component reads "refused: no pin order"
under "Kind for the network" (its Pins "-" and its hover, the backend's "the library states no pin order for it", as
before). The sentence takes each count's number: "1 has a kind of its own" or "N have a kind of their own" (plural()),
and "the other one reaches it as "unknown", with its pins named" or "the other N reach it ..., with their pins named".
`frontend/src/styles.css`: a step (`.check-action`) is in the hint's grey, under an item that blocks a start
(`.check-missing`) in the red of an error and under a warning (`.check-warning`) in amber, as `.check-detail` already
told a blocker apart; the ▶ of the budget asked for at Start (Agent.tsx) stays, as the plan says.
`frontend/src/panels/CircuitPicture.tsx`: the line and the picture's aria-label count with plural(), "1 device · 0 nets"
and "1 device and 0 nets". Beyond the plan: "with its pins named" for one part, and a warning item in the check's third
answer, which pins the amber. Only words and a colour: nothing starts, continues or stops a run, saves a task or writes to Virtuoso,
and every question is asked as before. `docs/workbench.md` (the ideal parts, What is missing before the run can start,
the circuit picture) and `docs/functionality-reference.md` (Circuit picture, PDK window..., What's missing?) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. First the three scripts that pin
the changed words and colours, all passed the first time: `pdk_check` 47 (46 before), with the sentence's "the other one
reaches it as "unknown", with its pins named." and the fold's "The ideal parts (3, and 1 refused)" (they pinned "the other
1 reach it" and "(4)"); new, mutual_inductor's kind reads "refused: no pin order" while mtline keeps "unknown"
(`pdk-window-1-shown.png`), and the "-" of its pins still passes. `agent_window_check` 35 (33): new, the steps of the two
items that block a start are in the colour of --bad (`agent-4-missing.png`); the third answer holds a warning now
(Corner targets, "FIXTURE: open Corner check."; six items where the check counted five), and under "Nothing blocks a
start." the connection's step is in the colour of --muted and the warning's in that of --warn
(`agent-5-connection-button.png`). `ngspice_window_check` 47 (46): new, the picture's line reads "Circuit picture 1
device · 0 nets" and its aria-label "1 device and 0 nets" (`ngspice-3-column.png`). Then the scripts that also render the
three screens, all passed the first time, no flakes: `dom_identity_check` 56, `virtuoso_source_check` 123,
`task_rows_check` 57, `typing_check` 62, `project_help_check` 62, `editor_columns_check` 45, `looks_check` 83 (it reads
every rule of the stylesheet), `circuit_source_check` 19. In all 11 scripts, 636 checks. A probe run of the first three
on the three sources as at 645586c (put back after, their sums compared) failed exactly the new and changed checks, 1 of
47, 3 of 47 and 2 of 35. The memory guard tripped once, after the first run: the host had 0.3 GB free while WSL held 13
GB of file cache; the user's own relief (6 x 1 GB touched and freed in Python) gave the host 5.1 GB back, and the guard
passed. The runner's other scripts were not run: none renders these screens. The page with real data was not looked at:
the live backend (8765) is down since the PC restart, and stays so.

### SIF-143 Output settings' tick boxes keep their size and a size never splits, the Runs window's first column says Created, and the graph view fits its drawing again when a line appears above it (2026-10-25; from the states audit of 2026-10-24)

**Found.** The states audit - the browser checks' own pictures of FIXTURE states - found three slips of layout and words.
In Output settings the tick boxes of the two options whose words take two lines, "Replay snapshots (needed to Continue a
run exactly)" and "Complete transition archive (independent of replay snapshots)", were drawn smaller than the other
three, and their words began left of the others' (S12-36, `output-1-panel.png`; 12.2 and 10.4 px wide where the others
are 13): a `label.check` is a flex row and every input has `min-width: 0`, so the box gave its words room. Above them the
facts' Free space cell read "400.00 GiB; used here 3.00" with "GiB" alone on the next line: bytes() joins number and unit
with a plain space, and a small grid's cells wrap. The Runs window titled its first column "Started" but filled it with
the creation time - its own help said "When the run was created" - so a run with no state read "Started 2026-09-18
09:00:00" beside "not started", that badge alone where a stopped run's reason stands under its state (S12-37,
`runs-2-window.png`). The plan's line for it, "its worker never began", does not hold: prepare_run (runs.py) writes
status.json ("created") together with the manifest, and the worker writes it after, so run_index.py lists a run with no
state only for a folder that holds no status.json - lost (a copy made without it, a deleted file), or in the moment
between the two writes. In the circuit graph view at the RL model window's 1180 px, a refused "<" put its red line over
the tools and the drawing gave that height up (SIF-66), but cytoscape kept its zoom and pan: the ground net "0" at the
foot of the drawing was cut in half by the box's lower edge (S12-39, `graph-4-window-width.png`), until Fit.

**Changed.** `frontend/src/styles.css`: a tick box in a `label.check` (or in a table cell) is `flex: none`, so it keeps
its 13 px and its words start where the others' do; `.output-facts .bytes` does not wrap.
`frontend/src/panels/OutputPanel.tsx`: both sizes of the Free space cell, and the free space on the line above the table,
stand in a `span.bytes`, so a size never splits from its unit; bytes() itself is unchanged, as the plan says
(export_check, files_tab_check and output_panel_check read its plain space). `frontend/src/panels/RunList.tsx`: the first
column is "Created", its help and its sort key as before; under "not started" stands "no status file", its tooltip saying
that the run folder holds the run's manifest but no status.json, which a run writes when it is created - a copy made
without it, or it was deleted, so its state is not known - and that a run being created that very moment reads so too
until Refresh list; the State column's help says it in short. Not the plan's words: they named a cause the backend cannot
produce. `frontend/src/panels/CircuitGraphView.tsx`: the view keeps the padding of the fit it shows (30 after a layout, 24
after Fit), and while it shows one, a new size of its box - cytoscape's own resize event, debounced by 100 ms, for a
refusal's line that comes or goes, a tool line that wraps again or a resized window - fits the drawing again; a pan, a
wheel or pinch zoom or a dragged node makes the view the user's until Fit or a layout button, and a resize that arrives
after the drawing was let go does nothing. Only layout, words and the drawing's zoom and pan: nothing starts, continues or
stops a run, saves a task or writes to Virtuoso, and every question is asked as before. `docs/workbench.md` (the run
window's Created and State rows - the State row still gave the stop reason as a key, `budget_exhausted`, which the cell
has written in words since SIF-15 - and the circuit graph view) and `docs/functionality-reference.md` (Runs..., Circuit
graph view) say it.

**Checked.** `tsc` clean. One lane, after the memory guard, on a build of this tree. First the three scripts that render
the changed screens and `looks_check` (it reads every rule of the stylesheet), all passed the first time:
`run_list_check` 185 (184 before): the column list, the finished run's time, the column after the tick box, the two sorts
back to newest first and a folder's name under the date read "Created" (they pinned "Started"); new, the run with no
state reads "not started no status file", the hint with its tooltip on that row only (`runs-2-window.png`).
`output_panel_check` 100 (98): new, the five tick boxes share their size, their left edge and the x their words start at,
the two of two lines among them, and the Free space cell reads "400.00 GiB; used here 3.00 GiB" with each size on one
line, the free space on the line above it kept whole too (`output-1-panel.png`); its two checks of "used here 3.00 GiB"
pass as before. `graph_view_check` 72 (69): new, after the refusal's line at 1180 px the view is cytoscape's fit of the
new box and the ground net's bottom (624 px) lies inside the 654 px canvas (`graph-4-window-width.png`); a wheel turn over
the drawing, then an 860 px window, leaves the zoom and pan as they were; Fit, then the window back at 920 px, fits the
drawing to its box again. `looks_check` 83. Then the scripts that also render the Runs window, the graph view, Output
settings or tick boxes, all passed the first time: `run_control_check` 181, `dom_identity_check` 56,
`model_chooser_check` 145, `blocking_issues_check` 70, `task_list_check` 106, `network_panel_check` 78,
`task_run_check` 39, `room_check` 31, `module_fold_check` 31, `encoder_models_check` 24, `agent_window_check` 35,
`graph_paint_check` 6 - except `training_tab_check`, which failed one timing check in that run ("a chart redraws at most
once a second while results arrive": 6 redraws where 3 are allowed) and passed alone, 139: a flake, its charts untouched
here. In all 17 scripts, 1,381 checks. A probe run of output_panel_check and graph_view_check on the four sources as at
bf0d7c9 (put back after, their sums compared) failed exactly the new layout checks: the two of Output settings (the boxes
12.2 and 10.4 px wide, no size kept whole) and two of the graph view (the ground net's bottom at 666 px in the 654 px
canvas; no fit after Fit and a taller window); the user's zoom kept passed there too, as it must. The page with real data
was not looked at: the backend on 8765 serves another tree, and no check runs against it.
