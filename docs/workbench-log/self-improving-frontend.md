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
