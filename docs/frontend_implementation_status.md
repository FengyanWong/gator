# Frontend / run-control / data-output implementation status

The INDEX of the workbench's development record (specification: `gator_claude_code_fable51_frontend_data_outputs_en.md`,
untracked at the repository root). This is a development record, not a research output or analysis report.

**How to use it.** `docs/workbench.md` says what every feature does NOW and is maintained in place: look at its heading
map (`grep -n '^##' docs/workbench.md`) and read only the section of the feature you touch. The record says how each
feature got there: entries 7.1 onwards, newest last, append-only; a later entry supersedes an earlier one without editing
it. Read only the entries of your area: find them in the table below, or search the log, for example
`grep -n 'Matched devices' docs/workbench-log/*.md` (`grep -n '^### 7\.' docs/workbench-log/*.md` lists every entry).
Where each function lives (its button, code, route, entries, tests and browser checks) is listed in
[`functionality-reference.md`](functionality-reference.md), kept current in place. Do not redo completed modules from
conversational memory. The record's history (what the first build got wrong, entries a later one reversed, the modules
each entry added, known slips) and the commit table are in [`record-history.md`](workbench-log/record-history.md).

| File | Holds |
|---|---|
| [`first-build.md`](workbench-log/first-build.md) | sections 1-6 and the first three next steps of the first build (`bcf7c5e`, 2026-09-20), never rewritten |
| [`7.01-7.20.md`](workbench-log/7.01-7.20.md) | entries 7.1-7.20 |
| [`7.21-7.40.md`](workbench-log/7.21-7.40.md) | entries 7.21-7.40 |
| [`7.41-7.60.md`](workbench-log/7.41-7.60.md) | entries 7.41-7.60 |
| [`7.61-7.80.md`](workbench-log/7.61-7.80.md) | entries 7.61-7.80 |
| [`7.81-7.100.md`](workbench-log/7.81-7.100.md) | entries 7.81-7.100 |
| [`7.101-7.118.md`](workbench-log/7.101-7.118.md) | entries 7.101-7.118 |
| [`7.119-and-later.md`](workbench-log/7.119-and-later.md) | entries 7.119 onwards: the OPEN file |
| [`record-history.md`](workbench-log/record-history.md) | the record's history and the commit table |

`7.61-and-later.md`, `7.81-and-later.md` and `7.101-and-later.md` are pointers kept for old links.

**Adding an entry:** append `### 7.N <title> (<date>, <session>, <request>)` at the end of the open file, with the next
free number (look at the table below AND at that file: sessions work in parallel), and add a one-line row at the end of
the table below: `| 7.N | <short title, at most about 110 characters> |`. A commit gets its row at the end of the commit
table in `record-history.md`.

**Rolling the open file over:** when the open file passes entry 7.140 or 60 kB, whichever comes first, move its entries
unchanged into `docs/workbench-log/7.119-7.<last>.md`, start `7.<last + 1>-and-later.md` as the new open file, leave
the old name as a pointer (like the two above), change the file table above, and then update `CLAUDE.md`, which names
the open file. One Read returns about 68 kB of text: a larger open file hides its newest entries from a default read
(7.64).

## Entries

Newest last. Each entry's heading in the log also gives its date, its session and the request.

| Entry | Title |
|---|---|
| 7.1 | Resolved: Virtuoso bridge connection request |
| 7.2 | Coordination with the parallel "Project directory setup" session |
| 7.3 | Connect flow in the panel |
| 7.4 | Per-circuit bindings in a connection profile |
| 7.5 | Real tasks could never be authorized from the UI |
| 7.6 | Agent tab: "was my request even sent?" |
| 7.7 | Per-encoder network settings from publications |
| 7.8 | Agent tab: warnings / unresolved in a side window + a real browser check |
| 7.9 | Connection panel: renamed, and a check only on a button press |
| 7.10 | Agent tab: model and effort lists per provider |
| 7.11 | `/api/config/validate` returned 500: concurrent first import of `torch_geometric` |
| 7.12 | Header: the blocking-issues notifier is a button that lists them |
| 7.13 | Circuit source "Import Spectre netlist" answered "Blocked" before anything was typed |
| 7.14 | Agent conversation: detachable window, readable messages, model and effort in use |
| 7.15 | Circuit source "Virtuoso library / cell / view": libraries, cells and schematic without buttons |
| 7.16 | Agent tab: "What's missing to start?" - a free checklist, an editable brief, a `readiness` request |
| 7.17 | Profile from a Virtuoso cell, increment 1 of 3: read the cell INTO the workbench, agent hand-off |
| 7.18 | Header: one run button Start -> Pause -> Resume, and Abort next to it |
| 7.19 | Profile from a Virtuoso cell, increment 2 of 3: Create profile -> a registered `real:<name>` task |
| 7.20 | Choosing which saved RL model to load |
| 7.21 | Profile from a Virtuoso cell, increment 3a: everything up to the first costed run |
| 7.22 | Profile from a Virtuoso cell, 3b: a blocker before the first baseline; the measurement checked on real results |
| 7.23 | "Save now": save the running run's model without pausing |
| 7.24 | FIRST REAL SIMULATION through the workbench: a generated profile's baseline; the bug blocking every real task |
| 7.25 | Agent: "Make it startable with the fewest changes" + a truthful start check for verified real circuits |
| 7.26 | Network structure of a saved model, as a table |
| 7.27 | Agent conversation: the detach control moved onto the tab |
| 7.28 | Agent tab wording |
| 7.29 | Agent tab: the selected rows on a click; the send button removed |
| 7.30 | Project panel: long explanations folded into "details" lines; "Native schematic" closed by default |
| 7.31 | Exports of the four run tabs: five gaps closed |
| 7.32 | "Connection": one button that opens a window; four kinds (Virtuoso or ngspice, on this machine or over SSH) |
| 7.33 | Circuit graph view - the ONE on-screen picture - and a red Abort button |
| 7.34 | Editor tabs renamed: Parameters, Specs, Probes |
| 7.35 | Project panel: the whole Hierarchy block is one closed line |
| 7.36 | Agent: "Review settings" over the whole workbench, optionally with publications read online |
| 7.37 | Agent tab: two buttons swapped places |
| 7.38 | Bottom tab strip: the run drop-down became "Runs...", a run window with finish time, duration and every fact |
| 7.39 | Agent: "Review run results" - the agent is given a digest of a run's output |
| 7.40 | Virtuoso source: the browse-only note no longer suggests the existing real tasks |
| 7.41 | Output settings: "Copy path" as text on the "Output root" line; the waveform storage limit typed with a unit |
| 7.42 | Agent tab: two shorter button captions |
| 7.43 | Run panel: no block for a NEW network while a saved model is loaded; the network comes with the model |
| 7.44 | Choosing a real task brings ITS rows: targets of record instead of the MOCK "score" |
| 7.45 | Right column: "Run configuration" and "Output settings" fold into one line |
| 7.46 | Agent brief and start checklist: "Load starter configuration" comes first |
| 7.47 | One cell, one task: a cell that already has a registered task says so; "Delete profile" |
| 7.48 | Agent tab: the answer is shown while it is written (thinking summary, then the reply); no time limit |
| 7.49 | Virtuoso source: the testbench is found by its name, and Probes follow the testbench |
| 7.50 | Agent tab: the live answer for the Codex provider too |
| 7.51 | Editor tabs: Probes before Specs |
| 7.52 | Specs are equations over Probes |
| 7.53 | Circuit source: "Import Spectre netlist" removed |
| 7.54 | Load PDK: the network understands every component of one PDK |
| 7.55 | Virtuoso task flow, part 1: the working copy and the Maestro setup of the copy |
| 7.56 | A configuration the schema rejects is listed field by field in plain words; synthetic:vco starts valid |
| 7.57 | Virtuoso task flow, part 2: the task file, "Save task" and "Save as" (Create profile removed) |
| 7.58 | Output settings: ONE checkpoint interval (evaluations OR seconds); the storage limit converts with its unit |
| 7.59 | One MOCK task, on a real circuit: synthetic:gpdk045_ota5 replaces the four toy-fixture tasks |
| 7.60 | Virtuoso task flow, part 3: the agent sets the task up - one proposal, written into the working copy |
| 7.61 | Virtuoso task flow, part 4: the check before every run ("Check against Virtuoso" removed) |
| 7.62 | Corner check: a run's best designs simulated again at five corners |
| 7.63 | Virtuoso task flow, part 5: running a task measured by Maestro - Maestro's deck, OCEAN on each run's results |
| 7.64 | Repository review: bugs fixed, speed-ups, dead code removed, the record split into `docs/workbench-log/` |
| 7.65 | Save task moves up to the editors' tab line; fewer buttons, as the flow has them |
| 7.66 | Real runs write any value the PDK's property form lets you type, not only transistor widths |
| 7.67 | A task can start a circuit that does not start by itself: initial conditions |
| 7.68 | The agent works in Virtuoso itself: the workbench's own tools, granted per request kind (`virtuoso_work`) |
| 7.69 | Repository review, round 2: nine correctness fixes, four speed-ups, one formatter, one pop-up window |
| 7.70 | Repository review, round 3: identical code merged, nothing else changed |
| 7.71 | A task keeps its initial conditions when it is saved again - the ring task had lost them |
| 7.72 | Virtuoso cellview import in a window; the workbench makes no copy - the user's copy is declared on the read |
| 7.73 | The OTA5 and VCO examples removed: their Virtuoso cells deleted, their built-in tasks withdrawn |
| 7.74 | ngspice netlist tasks: a SPICE deck becomes a task and runs on an ngspice connection; ngspice-47 installed |
| 7.75 | Project column: the two window launchers arranged as one aligned grid |
| 7.76 | Project column: the launcher follows the connection in use |
| 7.77 | Project column: the ngspice tasks in the Task list follow the connection in use, as the launcher does |
| 7.78 | Project column: "Load task" + "Delete task" in one row; a finished Single baseline records itself as reference |
| 7.79 | Connections "Virtuoso on this machine" and "ngspice over SSH" added; the ngspice agent aid "under construction" |
| 7.80 | Connection: one test of the connection in use when the page opens |
| 7.81 | Project Python environment rebuilt at `~/analog-optimizer-venv` after a WSL restart emptied `/tmp` |
| 7.82 | Icon-only buttons: header run buttons, Save task / Task file, the editors' toolbar, Load task / Delete task |
| 7.83 | `port_gnn` removed from the encoder list AND from the optimizer package, so the source digest changed |
| 7.84 | Icon-only buttons in the bottom tabs: Run status, Logs, Data tables, Output files, Corner check |
| 7.85 | Workbench refactoring: shared fixtures, async state, smaller feature modules (the API split, AgentTab / RunTabs) |
| 7.86 | Remove MLP and GCN encoders |
| 7.87 | Replace GATv1 with GATv2 |
| 7.88 | Reward v2 preflight stopped on conflicting requirements |
| 7.89 | Reward v2 replacement plan using the real flow |
| 7.90 | The suggested Mode is the clickable word itself; the "Use" button is gone |
| 7.91 | Output files: an icon button per file instead of the "download" text link |
| 7.92 | Fourteen columns deleted from Parameters and Probes, with a migration; "More columns"; initial_value read-only |
| 7.93 | Live frontend build on the user's "build it" |
| 7.94 | Reward v2 code integrated; real acceptance stopped at license visibility |
| 7.95 | Reward v2 real A/B/C qualification (73 Spectre calls) and read-side repair |
| 7.96 | Frontend aligned with reward-v2 optimizer contracts |
| 7.97 | Reward-v2 audit: correct in what it does, but breaks the MOCK path and the M6 modules - not ready to commit |
| 7.98 | Reward v2 audit fixes: MOCK path and M6 registries work again, MOCK runs use their reward settings |
| 7.99 | Reduce repeated frontend requests and backend reads/exports |
| 7.100 | The cell's PDK is read with the cell; "Load PDK..." moved to the Virtuoso window ("PDK window...") |
| 7.101 | Repository review, round 4: repeated code merged, behaviour unchanged; the record file rolled over |
| 7.102 | Loose ends of round 4: `task_rows_check` passes again, stale comments corrected |
| 7.103 | Bridge updated; Matched devices (netlist-crawler's ideas); plan for a gm/ID start and a finalist Monte Carlo |
| 7.104 | The Monte Carlo plan without the gm/ID start (`docs/plan-finalist-monte-carlo.md`) |
| 7.105 | Probes lose `conditions` and `aggregation`, with the migration |
| 7.106 | Reward v2.1: continuing failures, nominal gate and workbench diagnostics (Astra) |
| 7.107 | Reward v2.1 real-check preflight stopped (license status unknown) |
| 7.108 | Reward v2.1 physical gate check completed (10 of 30 launches) |
| 7.109 | Frontend entries without repeats: four duplicate buttons and four dead entries gone, faults fixed |
| 7.110 | OTA7 current-reference variant plan (plan only) |
| 7.111 | Reward v2.1 commit validation (package `8cf53ae`, workbench `8db46b8`) |
| 7.112 | Reward v2.1 audit fixes: the Specs scale suggestion follows the limits; equation specs survive a missing probe |
| 7.113 | The Specs equations' old-configuration hash test reads a frozen pre-equations configuration |
| 7.114 | Formula specs marked at training corners; a warning for "Missing value = failed" on a soft spec |
| 7.115 | Optimization review of what round 5 left: faster Check/Start children, reused connection checks, parallel checks, a status poll that follows the run |
| 7.116 | Four sizing methods with shared frontend/backend contracts: SAC, LLM warm start, LLM only, LLM rescue (Astra) |
| 7.117 | Repository review, round 5: bugs, speed-ups, session-start docs and test fixes |
| 7.118 | Audit of the LLM-sizing build (7.116): sound, four small fixes before its commit; report under artifacts/local/reviews |
| 7.119 | Fixed-bias feasibility calibration: 80 runs, zero passes; full suite passes; current/schema findings recorded |
| 7.120 | Audit finding F1 fixed: the LLM duplicate check compares sizes to a tolerance; optimizer digest 27a36b2b → 100945fb |
| 7.121 | Audit of the fixed-bias calibration: the zero passes come from the settling-time target, made worse by fixed low bias currents; tree green |
| 7.122 | Comparison protocol: equal 2,000-candidate planning budget, violation progress, every-pass verification |
| 7.123 | Committed duplicate fix verified; sizing UI deployed on 8765; live model and comparison still unapproved |
| 7.124 | Specs: compact tick-box column, the objective inside the Constraint list, Judged at only with training corners |
| 7.125 | Frontend audit and its fixes: honest real-run question, Agent message box, Import JSON, Save task without the Virtuoso window, stale answers, fewer requests; Undo per typed value |
| 7.126 | Optimization review's package changes landed: corners two at a time, every 5th reset simulated, Maestro results not parsed; optimizer digest 100945fb → f42a3098 |
| 7.127 | The form writer types a transistor's length before its width, so GPDK045's well-proximity values follow the final length; MScR ring3 mended and re-saved |
| 7.128 | The MOCK task and the real OTA7 and LDO tasks deleted, with the OTA7/LDO example files; the tests keep a MOCK stand-in; no task trains at corners |
| 7.129 | Optimizer fixes held back from round 5: top grid point, corner summary, late worker result, copies, MOCK fsync |
| 7.130 | Frontend reliability: autosave recovery, encoder races, bounded reads, narrow layouts and isolated tests |
| 7.131 | Review after the audit: the page's loads keep a saved task while its files are unchanged (MScR validation 0.64-0.96 s → 46-71 ms), repository path resolved once; its 10 frontend findings fixed on top of 7.130 (Undo merge follows the input event, a new AI run's thread, Continue during Resume, Read vs a task choice) |
| 7.132 | Five limits from the MScR build fixed: noise statement, analogLib and PDK resistors, iprobe, PWL in the package parser, Save task refuses equations naming no Probe; MScR noise specs and optimized resistors; optimizer digest 0d045b8e → 46327861 |
| 7.133 | Follow-ups: the other five MScR tasks run cleanly with the fixed form writer; the ngspice refusal test back; the warm-start note counts only paid resets |
| 7.134 | The header's flip-back after Abort: the run lock's liveness test took the lock exclusively and was seen as a worker by a test at the same moment; tests now share the lock, acquire waits 0.2 s |
| 7.135 | Round 5 open items: agent CLIs stop with the backend, infrastructure pauses resumable, Apply once; random test failures explained |
| 7.136 | Several designs at once on Spectre (mscr_ota7t): 2 lanes 1.8× faster, 4 lanes 2.3×; the one Virtuoso preparation process (about 0.6 s per candidate) is the limit |
| 7.137 | Lanes open side by side; the native preparation reads the cell 3 times per candidate, not 5 (digest 66ce02ab); working-copy folder read under the settings folder in use; checked on Spectre: 0.70 s per evaluation at 4 lanes |
| 7.138 | Investigation: the netlist export is 0.25 s of SKILL per candidate (OCEAN set up, libraries refreshed, everything re-netlisted each time); decks differ only in values; options A-D with estimates |
| 7.139 | Check of the work so far, and `docs/functionality-reference.md`: every function with its code, route, entries, tests, checks |
| 7.140 | Export variants timed (OCEAN set up once saves 0.09 s); netlists built from the readback, checked against every native export (GATOR_NETLIST_BUILD=check): matched on 3 MScR tasks on Spectre; a value at its bound no longer stops a run (digest c3a340b9) |
| 7.141 | A parameter bound to a Maestro variable gets its own value back, even after its cell was read again while bound |
| 7.142 | Real runs build most netlists from the readback, with Virtuoso export + comparison every 5th candidate (default; GATOR_NETLIST_BUILD=check/native); OCEAN set up once (not for Maestro tasks); ota7t 0.70 -> 0.54 s/eval at 4 lanes (digest e3f8c5b8) |
| 7.143 | Spectre job time measured (analyses ~5% of an ota7t job); up to 6 lanes for a real task (MAX_SPECTRE_WORKERS, tasks.REAL_LANES): ota7t 0.54 -> 0.41 s/eval, vco_lin 2.03 -> 1.40, no licence error (digest efa93649) |
| 7.144 | GPDK045 profiles: copied checks merged into one shared class, every message kept; dead cache branches gone; optimizer digest moves |
| 7.145 | Investigation: cell reads without positions save 7-10% (not done); the one Virtuoso session (preparation + OCEAN measurements) is the limit; staying-alive Spectre possible (+interactive) but little gain now |
| 7.146 | Project name stays; task label derives from selection; rows switch atomically, edits protected; Load becomes Reload saved values |
| 7.147 | Matched devices is the single open/refresh control; Find again removed; Close becomes an accessible × icon |
| 7.148 | Per-lane OCEAN on the simulator host for Maestro outputs: built, values identical on Spectre (43 comparisons), no speed gain (the preparation limits, not the measurement; 7.145 corrected), removed (user); before-write read kept (user) |
| 7.149 | Where a candidate's time goes (Spectre start + model reading ~0.9 s of a 1.47 s job); saved concurrency 1 -> 6; job folders on the WSL disk for runs on D: (`GATOR_LOCAL_SCRATCH`; Spectre: 0.84 -> 0.50 s/eval); window check before exports only (optimizer digest step); persistent Spectre: rule lifted by the user, plan + G0 (reruns 0.02-0.05 s vs ~1 s; values depend on the previous candidate at ~1e-6) |
| 7.150 | Mode first, Search method second; RL networks button below Mode opens a separate window; edits and cross-window Undo preserved |
| 7.151 | RL settings mismatch: correct In use label; exact This run / Saved default table; explicit apply/save-default actions |
| 7.152 | A Spectre that stays running in each lane: built (fresh check every 5th, fallback), smoke test passed, trial 1 found reruns far off fresh runs: a running Spectre ignores l and m changes (set or alter); removed at the user's decision, digest back to 7.149's |
| 7.153 | Investigation: a trimmed GPDK045 model library (only the sections ota7t uses) is exact; model reading 0.73 -> 0.47 s median per Spectre job, host noise +-0.5 s; nothing built |
| 7.154 | A trimmed model library for any circuit: at a real run's start the library's layout is read on the simulator host by names only and each section keeps the parts the circuit's devices need (MScR: 2-3 of GPDK045's 23); only for tasks with a recorded baseline (the 1e-6 reset comparison guards it); workbench code only, no digest step. Spectre: all 7 tasks identical, ~0.25 s less model reading per job; ota7t 6 lanes 0.43 vs 0.41 s/eval (Virtuoso session is the limit); no live MScR task has a baseline yet |
| 7.155 | Agent tab model lists: Codex's read from the Codex app's own `models_cache.json` (account's models, "Re-read list"), hand table as fallback; Claude Code table re-checked (older pinned IDs) |
| 7.156 | The "REAL evaluation backend ... authorize the budget first" banner under a loaded real task removed (it repeated what Start asks); budget question on Start unchanged |
| 7.157 | Maestro's six unread info outputs left out of run decks (`recipes.without_unread_info`; kept when an output uses VAR or names one; `GATOR_INFO_OUTPUTS=keep`): 0.36 s less per Spectre job (1.13 -> 0.76 s), results byte-identical, OCEAN outputs identical (10 of 10, = recorded values); real 1-lane ota7t run: 20/20 valid, baseline matched, 1.30 s/eval (1.99 in 7.136); also one evaluation step by step (1.9 s at 6 lanes) |
| 7.158 | The page's two looks and layout moves (user's choices of 2026-10-03: A + B, switch, title block, splitter, circuit picture, Windows fonts): Whiteprint (light, default) and Silicon Night (dark) by a header icon, every colour named first (pixel-identical proof), title-block header, bottom-panel splitter, one-line ids in Data tables, a colour per editor, circuit picture in the Project column |
| 7.159 | Project name box removed (user); the RL model gets its own label (`run.model_label`, Run configuration below Search method; empty = the task's run label): runs that save a model are remembered under it, the default model follows it, older project-name entries still answer; label in the manifest and on the model cards; hashed as absent while empty |
| 7.160 | The network in use, in short, beside RL networks... in Run configuration (e.g. `GT 48/4/4`, plus op. points / component list / saved model; "no saved model chosen", "not used (LLM only)"); the whole of it in the tooltip |
| 7.161 | Preparation in one Virtuoso call (option C) saves only about 0.01 s per candidate; every Virtuoso call waited about 44 ms in the bridge's SSH tunnel (`ssh -N`: Nagle on): the bridge checkout now starts it with a terminal (`-tt` + sleep), tunnel restarted; a short call 2.5 ms, the window check 4 ms |
| 7.162 | The two looks share every size: page margin, header border and padding, tab borders and the editor tabs' marks moved into one shared rule; the Silicon seal ring drawn inside the header's edge. Switching moves no box (measured on the live page) |
| 7.163 | RL networks window without its own close button; the repeated "Search method" heading gone; Research experiments: Experiment group and Test tasks retired (nothing read them; old configurations load and keep their hashes), the six transfer-study labels folded under "Transfer study" |
| 7.164 | One tab style in both looks: Whiteprint's editor tabs take Silicon Night's layer swatches and every tab strip its raised, underlined active tab (each look keeps its colours) |
| 7.165 | Investigation: a six-lane run's time besides Spectre - the preparation's queue +0.44 s per evaluation (the one preparation process ~70% busy; native exports of every 5th candidate are 44% of its work), around-Spectre time +0.46 s (shells, start/exit, transfers on 8 cores), OCEAN/hand-back/idle +0.3 s; levers listed, nothing built |
| 7.166 | Research experiments' heading in the modules' heading style; its note (optional for a single run; missing labels stay "unspecified") is the name's tooltip |
| 7.167 | The run adapter's session lock and crash journals moved off D: to `~/.local/state/gator/bridge-state` (`paths.bridge_state_dir()`, `GATOR_BRIDGE_STATE_DIR`): a journal written twice 0.95 ms instead of 16.2 ms; tests use a folder of their own |
| 7.168 | Folder settings in the connection window (**Folders...**): adapter state, simulator scratch, bridge checkout, and the simulator host's initial-condition and Maestro-netlist folders; defaults = the values used before; stored in the connection file's "directories" block, each checked before saving |
| 7.169 | Research experiments' name shows the hand pointer (it opens and closes the fold), not the help question mark; its note stays the name's tooltip |
| 7.170 | Connection window: Folders is a section of its own, headed like steps 1-3 (a folder sign where they have a number); each folder's comment is its name's tooltip, no text under it |
| 7.171 | The three 0-to-1 reward boxes (Worst hard-spec share, Objective bonus weight, Tightest-margin bonus weight) without the browser's up/down arrows; still number boxes with the 0..1 range |
| 7.172 | Editor columns: Specs target/tolerance and Probes expression retired (identities kept); initial_value and result_source hidden; value_type/step/scale/ratio behind More columns; probe ID and spec unit follow; six faults fixed (Read setup analysis and citations, Add probe source, digest units, fixed rows, a note dropping the baseline) |
| 7.173 | A drop-down's open list in the look's own colours: every option on the field colour in the text colour (in Silicon Night an editor cell's list was light under light text) |
| 7.174 | Audit fixes: torn journals repaired before append; late task saves preserve newer edits and task selection; legacy computed-probe references migrate in order; Codex strict proposals decode to the shared contract; Undo/Redo uses a pure reducer under StrictMode |
| 7.175 | The editors' formula bar: the chosen cell's whole value in a box as wide as the table, typed there and written by Enter (Esc keeps the cell); lists, tick boxes and following values shown, not typed |
| 7.176 | The lines above Parameters and Specs cut to their fact - "Independent action variables: 16 of 24 rows.", "Probes: <chips>" - their explanations in the line's tooltip |
| 7.177 | The saved task's run-check note cut to one line ("Before every run: the editors, the task and its cell must agree."), the explanation in its tooltip |
| 7.178 | Browser checks: a pop-up is handed over once its copied stylesheets are in (harness `attach`), and pdk_check reads the PDK window's list once it has arrived - the two timing failures of pdk_check |
| 7.179 | Room for the tables (design advice 1-3): the bottom panel folded while no run is shown; Run configuration a property sheet (a number's label and box on one line, the run limits in one "Limits" fold); Output settings' long lines folded into one-line summaries |
| 7.180 | The editor tables as a spreadsheet (design advice 4 and 6): tied Parameters rows folded under their leader; Up / Down / Enter move between rows; a block pasted from Excel fills the cells as one Undo step |
| 7.181 | Readable small and large numbers: a bound, limit or scale of a row in an unprefixed base unit reads in engineering notation (0.0004 A as 400µ), typed either way; the formula bar keeps the exact number |
| 7.182 | The Connection button in the header's title block (user), the task name out of it (user); Corner check and the corner training choices only where corners can be used; the tick box and ID column stay in view while a table scrolls sideways; two labels without internal names |
| 7.183 | The tested defaults (175 ngspice runs, 5 Spectre runs): the GATOR baseline holds starting temperature 0.01, 8 updates per evaluation and discount 0 - with the old values soft actor-critic is a random search and no reward setting matters; a new configuration's reward said in one sentence (share 0.5, both bonuses 1), its controls in an Advanced fold, other values named with a button back; Specs scale = the size of the limit (6 dB for dB), `hard` and Scale behind More columns; validation warns of values and budgets that do not learn and blocks a limit of 0 without a scale. Schema defaults, digest and hashes unchanged |
| 7.184 | The editor tables' last spreadsheet pieces (design advice 4, the user's "go on"): a find box that shows only the rows whose text matches; Ctrl+D fills down; Ctrl+C and a Copy button take a block out for Excel, with a header line that a paste back skips |
| 7.185 | The editors' toolbar on one line at 1366 px again: the find box shrinks with the window (80 to 170 px) and its count sits inside it, so a find never wraps the toolbar |
| 7.186 | The Agent tab's agent starts with a named list of built-in tools (no messages to other sessions, claude.ai routines, notifications, artifacts or workflows any more); claude.ai documents read-only; Virtuoso tools kept |
| 7.187 | Save task refused every cell holding an ideal current source or resistor since the example circuits were deleted (7.128): the two device definitions, lost with the LDO example's mapping file, are the workbench's own now - found by the user's "fill them with 6" for the 13 dB rows; the Scale column's explanation in 54 words instead of 74 |
| 7.188 | A crash panel instead of a blank page (what broke; Undo, Export JSON, Reload); Ctrl+Z / Ctrl+Y in the editor tables; the "no real baseline yet" note in one line; the editor tables' headers in plain words (the field names in their tooltips) |
| 7.189 | Lighter page opening: the output folder is no longer walked for its size on every page open (0.7 to 2 s of disk work on D:); the size is measured on a Measure button; the page's weight measured |
| 7.190 | Load PDK reads the ideal parts too (user: "it should be recognizing all the loaded components ... build it, read analogLib with the PDK"): analogLib's own description - which Spectre component each cell netlists as, with which pins - is read in the same press as the PDK and stored with it; sources, ideal R / C / L, probes and controlled sources in a cell are recognized from it, a part with no kind of its own as "unknown" with its pins named; the PDK is read before a cell's device mapping is built; the PDK window lists the ideal parts; saved tasks unchanged |
| 7.191 | The GATOR baseline deleted from RL networks, the publication preset kept, and both preset buttons gone (user: "Delete the gator baseline in RL networks and keep the publication preset, delete two buttons"); an encoder that was on the baseline reads as its publication preset; the reset route removed |
| 7.192 | The starting preset: every encoder keeps its published network size and takes every training number of the runs that learned on GATOR circuits (user: "merge the publication preset and overwrite those settings with the previous learned settings, keep this as the starting preset"; chose "All training numbers"); the page says "starting preset" |
| 7.193 | The Training tab beside Output files: live uPlot charts of what a run records; nothing invented, nothing added to training |
| 7.194 | Scale 6 back in mscr_ldo2_rgcn's three dB rows (revision 6, through the live Save task: Specs only, baseline kept). Two presses of Save task from a page holding the rows from before record 7.187 had emptied them. The page did not freeze, but a save shows no sign of working for its ~30 s ("Saving..." is screen-reader text since the icon buttons of 7.82) |
| 7.195 | The Advanced fold of the RL networks window directly below "Nominal device operating points" (user: "move the advanced setting to beneath the nominal device op checkbox"), with the slow-learning warning above it; in a Mode that loads a model it still closes the window |
| 7.196 | Load PDK sees through a diode wrapped with its series resistance (one diode, only resistors beside it on every path between the first two pins = a diode, roles through the series resistor). A second foundry PDK's nine wrapped diodes now read as diodes; GPDK045 rebuilds to the very same version (fa5c3946). That PDK's record and every copy of its files deleted on the user's request |
| 7.197 | Calibration with the baseline run (user: "shouldnt each task run the baseline run? can you add the calibration functionality to that"): a tick "+ calibration" beside Single baseline simulation, on by default - the run goes on with 64 random designs (64 + lanes evaluations) and proposes a Scale per Specs row (the median miss among the designs that miss it) and the Initial alpha (0.1 x the reward's spread); nothing is applied by the run, Run status shows the proposals and Apply calibration writes them as one Undo step. No proposal for the objective row, a row few designs miss or the capped shape; an invalid baseline ends the run before any random design. Measured in training on ngspice only: 99.1 % against 97.0 % passing designs with the tested reward, at about 7 % more power; the run itself checked once on Spectre (real:mscr_ota7t, 65 simulations) |
| 7.198 | Save task shows its steps while it works (a bar and "step 2 of 4: Virtuoso netlists the Maestro test (12 s)" under the toolbar) and allows one save at a time: the backend keeps the running save (GET /api/tasks/saving, memory only) and refuses a second one; the page asks when Save task appears, also after a reload, follows a running save every second, keeps Save task closed and says how a save it did not send ended (user: "show saving ... dont allow another save task press even after refreshing page") |
| 7.199 | Learning rate 1e-3 in every starting preset (user: "use learning rate 1e-3 in the starting preset"; calibration study: learning about 100 designs earlier, about 5 % more power); the three presets measured as a whole on ngspice: all learn, about as early as 32 / 4 / 2; the Graph Transformer preset on Spectre (real:mscr_ota7t, 800 launches): 469 of 760 designs passing, the first at 202, against 36 and 591 before |
| 7.200 | Several runs on one Training chart: Compare... puts up to three other runs beside the shown one, each its own colour |
| 7.201 | Training audit fixes: best feasible objective excludes infeasible/unknown designs; live journal data uses bounded cursor pages; browser row limits cover the unflushed tail, preserving counts and flush deduplication |
| 7.202 | One "Baseline simulation" button (user: "can we meege single baseline simulation and calibration to baseline simulation"): the "+ calibration" tick gone, every baseline run calibrates; the baseline alone = Abort once the random designs begin; Check now stays the free check (user's choice after advice). Page + wording only |
| 7.203 | Save task asks before rows older than the saved task replace it (user: "yes build it"): the page notes which saved revision its rows came from; a save that would undo what was saved since is refused before any step (409 saved_task_newer) and the page offers Reload saved values or Save anyway; the check while editing points to Reload saved values for such rows |
| 7.204 | "Calibration ready" (user: "build the prompt when the run finishes"): when the Baseline simulation the header holds has ended, a line under the header names the proposed values with Apply calibration and Not now - the same code as the Run status button, one Undo step, answered once per run, nothing applied by itself. Also: a run without random designs says why in plain words, and "What's missing?" no longer advises Reload saved values for rows the user has just changed (it gives the issue whole: Save task) |
| 7.205 | Up to eight Training charts at once: each chooses its content in its title, + adds one, × takes one off |
| 7.206 | The Abort question of a Baseline simulation says the baseline is kept, a task saved from a cell without a reference still gets it, and the calibration proposes only from the random designs simulated so far (at least 16); the tooltip of 7.202 sends you to Abort for the baseline alone. Page only |
| 7.207 | Check now says when another real run holds Virtuoso (user: "yes fix the message"): a command-line run held the adapter's session lock and the check said "BlockingIOError" with the advice for a changed working copy (Save task); now one step "Another real run is using Virtuoso" names the holder from /proc/locks (without taking the lock), reads nothing, and says the task needs no change; Start / Baseline simulation / Resume are refused with the same words. Backend only (`consistency.py`) |
| 7.208 | One way of writing a quantity (user: "a unified way of unit representation ... considering the convenience usage of users", chose "Prefix per value"): every bound, limit and scale written as Virtuoso writes it, in English letters (1.205 um, 400 uA, 9.535 kohm, 100 MHz, -30 dB, 60 deg; user: "dont use greek characters for unit"), exact digits; any form typed, a plain number in the row's unit, another quantity refused; no Unit column in Parameters and Specs (user: "delete the unit column but keep the rules for value"), the Probes' Unit a list; Run status, Corner check, graph view, Training and the check's messages alike; one unit table from the backend |
| 7.209 | The RGCN and GATv2 starting presets on Spectre (user: "run the rgcn preset on Spectre", "run gatv2 on Spectre too"): `real:mscr_ota7t`, 800 launches each, as 7.199's Graph Transformer run except the network; first passing design 218 / 289 (Graph Transformer preset 202, 7.183's 32 / 4 / 2 run 591), last third 88 / 93 % passing (Graph Transformer 98 %); one seed each. No code change |
| 7.210 | The short-budget warning (`budget_below_sac_learning`) and three texts give the starting presets' learning point (about 150 to 300 evaluations, record 7.199) beside 7.183's 250 to 600; the threshold stays 300 |
| 7.214 | The Calibration of a run of another task than the page holds (user: "yes fix the panel"): it showed the page's Specs rows of the same ID - "no such row on the page" for three rows of an OTA run and an LDO's own pm_deg as "Scale now" - and the page's Initial alpha; now a line names both tasks and where to choose the run's task, the table shows "Scale in the run" and the run's Initial alpha, nothing is marked "not applied", and Apply says which task it waits for. Page only |
