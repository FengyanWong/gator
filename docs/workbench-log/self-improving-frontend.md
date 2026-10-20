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
