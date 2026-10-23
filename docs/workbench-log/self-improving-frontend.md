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
