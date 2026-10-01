# Frontend / run-control / data-output implementation status

The INDEX of the workbench's development record (specification: `gator_claude_code_fable51_frontend_data_outputs_en.md`,
untracked at the repository root). This is a development record, not a research output or analysis report.

**How to use it.** `docs/workbench.md` says what every feature does NOW and is maintained in place: look at its heading
map (`grep -n '^##' docs/workbench.md`) and read only the section of the feature you touch. The record says how each
feature got there: entries 7.1 onwards, newest last, append-only; a later entry supersedes an earlier one without editing
it. Read only the entries of your area: find them in the table below, or search the log, for example
`grep -n 'Matched devices' docs/workbench-log/*.md` (`grep -n '^### 7\.' docs/workbench-log/*.md` lists every entry).
Do not redo completed modules from conversational memory. The record's history (what the first build got wrong, entries
a later one reversed, the modules each entry added, known slips) and the commit table are in
[`record-history.md`](workbench-log/record-history.md).

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
