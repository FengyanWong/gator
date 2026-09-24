# Frontend / run-control / data-output implementation status

The INDEX of the workbench's development record (specification: `gator_claude_code_fable51_frontend_data_outputs_en.md`).
After a context compaction or in a resumed session, read this index, `git status` / `git diff`, `docs/workbench.md`
(what every feature does NOW; it is maintained in place) and the entries of the area you are about to touch - not the
whole record. Do not redo completed modules from conversational memory. This is a development record, not a research
output or analysis report.

The record itself moved, unchanged, into `docs/workbench-log/` on 2026-09-22 (entry 7.64): as one file it had reached
330 kB (about 80k tokens), and a default read stopped at entry 7.43, so a session saw nothing of the newest twenty.

| File | Holds |
|---|---|
| [`first-build.md`](workbench-log/first-build.md) | sections 1-6 and the first three next steps of the first build (`bcf7c5e`, 2026-09-20), never rewritten |
| [`7.01-7.20.md`](workbench-log/7.01-7.20.md) | entries 7.1-7.20 |
| [`7.21-7.40.md`](workbench-log/7.21-7.40.md) | entries 7.21-7.40 |
| [`7.41-7.60.md`](workbench-log/7.41-7.60.md) | entries 7.41-7.60 |
| [`7.61-and-later.md`](workbench-log/7.61-and-later.md) | entries 7.61 onwards: the OPEN file |

**Adding an entry:** append `### 7.N <title> (<date>, <session>, <request>)` at the end of
`docs/workbench-log/7.61-and-later.md`, with the next free number (look at the table below AND at that file: sessions
work in parallel), and add its row at the end of the table below. Entries are append-only; a later entry supersedes an
earlier one without editing it.

**Rolling the open file over:** when the open file passes entry 7.80 or 80 kB (whichever comes first), move its
entries unchanged into `docs/workbench-log/7.61-7.80.md`, start `7.81-and-later.md` as the new open file, and change
the two rows in the table above. The split exists so that a default read reaches the newest entries; a file that grew
past ~80 kB stopped doing that (7.64).

## 0. Reading guide (written 2026-09-22 ~00:05 for an outside review; updated for the split, 7.64)

`first-build.md` describes the FIRST build (commit `bcf7c5e`, 2026-09-20 ~17:44) and was never rewritten; the entries
7.1 onwards, newest last, are everything since. A later entry supersedes an earlier one without editing it, so the
entries - not sections 3-6 of the first build - say what is true now. Elsewhere: `docs/workbench.md` (the user-facing
description), `CLAUDE.md` (rules), the specification `gator_claude_code_fable51_frontend_data_outputs_en.md` (untracked
on purpose), and the research history of the optimizer package (M1-M6) in `docs/decisions.md` and `docs/m*-*.md`.

Outdated in `first-build.md`, and the entry that changed it:

* 6.1 "no real Virtuoso/Spectre evaluation": ONE authorized real Spectre evaluation ran through the workbench - a
  generated ring-oscillator profile's baseline, which also found and fixed the bug that had made every real task
  unrunnable (7.24).
* 6.2 "agent CLIs absent": `claude` is on the PATH and used for real since 7.6 (live answers 7.48). The Codex provider
  has never run against a real CLI (built from its documentation and fake-CLI fixtures; live answers 7.50).
* 6.4 "no call lists cells": cells are listed with SKILL taken from the bridge's own examples (7.15).
* 6.5 "not implemented": Maestro outputs, specs and design variables are read from and written to a working COPY (7.55);
  a task measured by Maestro runs (7.63). PVT: a run's best designs can be simulated again at five corners (7.62).
  Monte Carlo: still none.
* 6.7 "not exercised in a browser": headless-Edge checks since 7.8; on 2026-09-23, 28 check scripts in
  `frontend/scripts/*.mjs` plus the shared harness `frontend/scripts/lib/harness.mjs` (7.64). Most of them drive the
  LIVE backend on 8765 unless `GATOR_WORKBENCH_URL` is exported through `WSLENV`.
* 5.1 test counts: the newest entry that reports a full `tests/workbench` run has the current count.
* Section 7, steps 1-3: done, the first one differently - the first real run was a generated profile's baseline, not
  `real:gpdk045_ota5` (7.24); browser checks from 7.8 on; a real `claude` request in 7.6.
* Section 4 lists the first build's modules only. Added later, with the entry that introduced each:
  `bridge_connect.py` 7.3, `network_presets.py` 7.7, `agents/catalog.py` 7.10, `preload.py` 7.11,
  `agents/readiness.py` + `agents/run_readiness.md` 7.16, `native_cells.py` 7.17, `profiles.py` / `generic_profile.py`
  / `recipes.py` 7.19, `profile_preflight.py` 7.21, `model_structure.py` 7.26, `ngspice_link.py` 7.32,
  `graph_view.py` 7.33, `agents/settings_review.py` 7.36, `agents/run_digest.py` 7.39, `agents/live.py` 7.48,
  `spec_equations.py` 7.52, `pdk.py` 7.54, `working_copy.py` / `virtuoso_setup.py` / `bridge_setup.py` 7.55,
  `task_files.py` 7.57, `consistency.py` 7.61, `corner_check.py` 7.62, `ocean.py` 7.63,
  `cdf_facts.py` / `cdf_rules.py` / `cdf_write.py` 7.66, `agent_tools.py` + `agents/tools.py` 7.68,
  `ngspice_netlist.py` / `ngspice_backend.py` / `ngspice_tasks.py` 7.74; panels `Issues.tsx` 7.12,
  `RunControl.tsx` 7.18, `ModelChooser.tsx` 7.20, `ModelStructure.tsx` 7.26, `Connection.tsx` 7.32,
  `CircuitGraphView.tsx` + `circuitLayout.ts` 7.33, `RunList.tsx` 7.38, `Pdk.tsx` 7.54, `WorkingCopy.tsx` 7.55,
  `TaskSave.tsx` + `TaskFile.tsx` 7.57, `Consistency.tsx` 7.61, `CornerCheck.tsx` 7.62, `Typed.tsx` 7.64, `Ngspice.tsx` 7.74.

An entry that a later one REVERSED (both stand as written; the later one is what is true):

* the four toy MOCK tasks of the first build -> ONE MOCK task on a real netlist, `synthetic:gpdk045_ota5` (7.59).
* "Import Spectre netlist" as a circuit source (7.13 fixed its form) -> the source was removed on the user's request
  (7.53): the UI is gone and the backend refuses it, the schema keeps the field so that old configs still hash.
* "Create profile" (7.19 / 7.21 built it, 7.47 gave it one task per cell) -> replaced by the task file with
  "Save task" / "Save task as" (7.57).
* centre tab order Parameters | Specs | Probes (7.34) -> Probes before Specs (7.51).
* "Ask the agent for suggestions" (7.60), "Write to Virtuoso" / "Use in editors" / the browser's own Save (7.55, 7.57)
  and "Check against Virtuoso" (7.61) -> removed or merged into the flow's own buttons (7.61, 7.65).
* "the tab's agent has no write tool" (7.36, 7.39) -> request kind `virtuoso_work` gives it the workbench's own tools
  (7.68).

Known slips inside the entries (left as written):

* 7.40's heading says 2026-09-22; it was written on 2026-09-21 (committed in `c3b9691` at 17:57).
* 7.50 says `codex` "is installed neither in WSL nor on Windows". The Codex desktop app on this machine ships a CLI
  (`codex-cli 0.155.0-alpha.9.2`, a Linux build inside the app's settings folder, not on the PATH), so the provider
  could be tried for real - a request costs usage, so that is the user's decision.
* Commit `155c261`'s message names only 7.18, but it holds the code of 7.18 AND of 7.19 / 7.21 (the shared git index
  swept a peer's work in); the empty commit `9cf670b` carries the message for the 7.19 / 7.21 part; `6ac02b9` holds
  7.18's entry.

Not recorded here: the ring oscillator `GPDK045_RINGOSC/ring_osc_3stage` + `tb_ring_osc_3stage`, which 7.17 onwards
read, turn into a profile and simulate, was built on 2026-09-20 by a separate session outside this repository (scripts
in `~/ring_osc_gpdk045`; 3 stages, MIM-cap loads, 1.209 GHz in one standalone Spectre transient outside every GATOR
budget).

| Commit | Committed | Entries | Note |
|---|---|---|---|
| `bcf7c5e` | 09-20 18:04 | first build, 7.1, 7.2 | branch `m6-cross-category`; stages 1-5 |
| `dec6ef6` | 09-21 02:34 | 7.3-7.17 | |
| `b1ae11a` | 09-21 03:44 | 7.20 | |
| `155c261` | 09-21 03:51 | 7.19, 7.21 + the code of 7.18 | see the slips above |
| `9cf670b` | 09-21 03:52 | - | empty commit |
| `6ac02b9` | 09-21 03:53 | 7.18 | the entry + `workbench.md` only |
| `b59daeb` | 09-21 04:10 | 7.22 | |
| `1772b8a` | 09-21 04:19 | 7.23 | |
| `149e3ab` | 09-21 13:26 | 7.26 | |
| `5c294a0` | 09-21 15:37 | 7.25, 7.27-7.29, 7.34, 7.36, 7.37 | |
| `c3b9691` | 09-21 17:57 | 7.24, 7.30-7.33, 7.35, 7.38-7.47 | last commit on `m6-cross-category` |
| `ec0282b` | 09-21 21:09 | 7.48-7.52 | first commit on branch `workbench` |
| `d498c59` | 09-21 23:44 | 7.55 | |
| `9b1a9ce` | 09-22 14:58 | 7.57, 7.60 | |
| `e1103a7` | 09-22 15:11 | 7.58 | |
| `38c0eb4` | 09-22 15:47 | 7.61 | |
| `12ea4f4` | 09-22 16:02 | 7.62 | |
| `80f18d2` | 09-22 16:15 | 7.56, 7.59 | |
| `a662753` | 09-22 16:43 | 7.63 | |
| `f283c78` | 09-22 16:47 | - | this split: the index + `docs/workbench-log/` (docs only; described in 7.64) |
| `8a4b363` | 09-22 17:27 | 7.65 | also the 7.63 note on the settings slip |
| `0f7c944`, `64ac955` | 09-22 18:46, 18:47 | 7.64 | the second one carries the text of two assets the first removed |
| `f713cea` | 09-22 19:12 | 7.54, 7.66 | |
| `34ef5e2` | 09-22 19:15 | - | names the commits of 7.64 inside that entry |
| `4231a8f` | 09-22 19:51 | 7.67 | |
| `00fc084` | 09-22 19:56 | 7.68 | |
| `0fea6b1` | 09-23 02:07 | 7.53 | the departed session's netlist removal, committed on the user's decision |
| `bfcfb2d` | 09-23 03:10 | 7.69 | review round 2; also the rollover rule and the lists in this file |
| `e4ef6b4` | 09-23 03:54 | 7.70 | review round 3: identical code merged only; nothing under `src/analog_optimizer` |

## Entries

Newest last. The date, the session and the request are in each title.

| Entry | Title | File |
|---|---|---|
| 7.1 | Resolved: Virtuoso bridge connection request (2026-09-20) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.2 | Coordination with the parallel "Project directory setup" session | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.3 | Connect flow in the panel (2026-09-20 late evening, separate session, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.4 | Per-circuit bindings in a connection profile (2026-09-20 late evening, same session as 7.3) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.5 | Real tasks could never be authorized from the UI (2026-09-20 late evening, same session) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.6 | Agent tab: "was my request even sent?" (2026-09-20 ~21:00, separate session, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.7 | Per-encoder network settings from publications (2026-09-20 ~21:20, separate session, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.8 | Agent tab: warnings / unresolved in a side window + a real browser check (2026-09-20 ~21:30, same session as 7.6) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.9 | Connection panel: renamed, and a check only on a button press (2026-09-20 ~21:50, separate session, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.10 | Agent tab: model and effort lists per provider (2026-09-20 ~22:00, same session as 7.6 / 7.8, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.11 | `/api/config/validate` returned 500: concurrent first import of `torch_geometric` (2026-09-20 ~21:55, separate session, user-reported traceback) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.12 | Header: the blocking-issues notifier is a button that lists them (2026-09-20 ~22:15, same session as 7.11, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.13 | Circuit source "Import Spectre netlist" answered "Blocked" before anything was typed (2026-09-20 ~22:40, same session as 7.9, user report) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.14 | Agent conversation: detachable window, readable messages, model and effort in use (2026-09-20 ~22:30, same session as 7.6 / 7.8 / 7.10, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.15 | Circuit source "Virtuoso library / cell / view": libraries, cells and schematic without buttons (2026-09-20 ~23:10, same session as 7.9 / 7.13, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.16 | Agent tab: "What's missing to start?" - a free checklist, an editable brief, a `readiness` request (2026-09-21 early, same session as 7.6 / 7.8 / 7.10 / 7.14, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.17 | Profile from a Virtuoso cell, increment 1 of 3: read the cell INTO the workbench, agent hand-off (2026-09-21 ~01:15, same session as 7.9 / 7.13 / 7.15, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.18 | Header: one run button Start -> Pause -> Resume, and Abort next to it (2026-09-21 ~03:40, separate session, explicit user request) | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.19 | Profile from a Virtuoso cell, increment 2 of 3: Create profile -> a registered `real:<name>` task (2026-09-21 ~03:30, same session as 7.17, user: "go on with stage 2") | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.20 | Choosing which saved RL model to load (2026-09-21 morning, separate session, user: "can you choose which model to load?" / "what is a source run") | [7.01-7.20.md](workbench-log/7.01-7.20.md) |
| 7.21 | Profile from a Virtuoso cell, increment 3a: everything up to the first costed run (2026-09-21 ~04:40, same session as 7.17 / 7.19, user: "go on") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.22 | Profile from a Virtuoso cell, increment 3b: a blocker found before the first baseline, and the measurement checked on real result files (2026-09-21 ~06:00, same session as 7.17 / 7.19 / 7.21, user: "leave it, go on") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.23 | "Save now": save the running run's model without pausing (2026-09-21 ~04:20, same session as 7.20, user: "add a save now button") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.24 | FIRST REAL SIMULATION through the workbench: a generated profile's baseline - and the bug that had made every real task unrunnable (2026-09-21 ~05:20 local, same session as 7.17-7.22) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.25 | Agent: "Make it startable with the fewest changes" + a truthful start check for verified real circuits (2026-09-21, same session as 7.16, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.26 | Network structure of a saved model, as a table (2026-09-21 ~05:30, same session as 7.20 / 7.23, user: "go, build the structure table") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.27 | Agent conversation: the detach control moved onto the tab (2026-09-21, same session as 7.14, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.28 | Agent tab wording (2026-09-21, same session as 7.27, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.29 | Agent tab: the selected rows on a click; the send button removed (2026-09-21, same session as 7.28, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.30 | Project panel: long explanations folded into "details" lines; "Native schematic" closed by default (2026-09-21 ~14:00, separate session, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.31 | Exports of the four run tabs: five gaps closed (2026-09-21 ~14:00, separate session, user: "close all five gaps") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.32 | "Connection": one button that opens a window; four kinds of connection - Virtuoso over SSH / on this machine, ngspice on this machine / over SSH (2026-09-21 ~14:15, separate session, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.33 | Circuit graph view - the ONE on-screen picture - and a red Abort button (2026-09-21 afternoon, same session as 7.20 / 7.23 / 7.26, user: "go, make the abort button red and build the circuit graph view") | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.34 | Editor tabs renamed: Parameters, Specs, Probes (2026-09-21 ~14:10, separate session, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.35 | Project panel: the whole Hierarchy block is one closed line (2026-09-21 ~14:15, same session as 7.30, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.36 | Agent: "Review settings" over the whole workbench, optionally with publications read online (2026-09-21, same session as 7.25, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.37 | Agent tab: two buttons swapped places (2026-09-21, same session as 7.36, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.38 | Bottom tab strip: the drop-down list of runs became a "Runs..." button that opens the run window - finish time, duration and every fact of each run (2026-09-21 ~14:40, two sessions, explicit user requests) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.39 | Agent: "Review run results" - the agent is given a digest of a run's output (2026-09-21, same session as 7.36, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.40 | Virtuoso source: the browse-only note no longer suggests the existing real tasks (2026-09-22, same session as 7.15 / 7.17-7.24, explicit user request) | [7.21-7.40.md](workbench-log/7.21-7.40.md) |
| 7.41 | Output settings: "Copy path" as text on the "Output root" line; the waveform storage limit typed with a unit (2026-09-21 ~16:05, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.42 | Agent tab: two shorter button captions (2026-09-21, same session as 7.39, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.43 | Run panel: no block for a NEW network while a saved model is loaded; the network comes with the model (2026-09-21 evening, same session as 7.20 / 7.23 / 7.26 / 7.33, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.44 | Choosing a real task brings ITS rows: targets of record instead of the MOCK "score" (2026-09-21 ~16:45, separate session, user report) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.45 | Right column: "Run configuration" and "Output settings" fold into one line (2026-09-21 evening, same session as 7.43, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.46 | Agent brief and start checklist: "Load starter configuration" comes first (2026-09-21, same session as 7.39; prompted by the session of 7.44) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.47 | One cell, one task: a cell that already has a registered task says so; "Delete profile" (2026-09-21 evening, same session as 7.15 / 7.17-7.24 / 7.40, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.48 | Agent tab: the answer is shown while it is written (thinking summary, then the reply); no time limit (2026-09-21 evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.49 | Virtuoso source: the testbench is found by its name, and Probes follow the testbench (2026-09-21 evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.50 | Agent tab: the live answer for the Codex provider too (2026-09-21 evening, same session as 7.48, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.51 | Editor tabs: Probes before Specs (2026-09-21 ~18:35, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.52 | Specs are equations over Probes (2026-09-21 evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.53 | Circuit source: "Import Spectre netlist" removed (2026-09-21 evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.54 | Load PDK: the network understands every component of one PDK (2026-09-21 late evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.55 | Virtuoso task flow, part 1: the working copy and the Maestro setup of the copy (2026-09-21 late evening, separate session, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.56 | A configuration the schema rejects is listed field by field in plain words; synthetic:vco starts valid (2026-09-22 ~00:10, separate session, user report) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.57 | Virtuoso task flow, part 2: the task file, "Save task" and "Save as" (Create profile removed) (2026-09-22 ~00:30, same session as 7.55, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.58 | Output settings: ONE checkpoint interval (evaluations OR seconds), also in the backend; the storage limit converts with its unit; the closing line deleted (2026-09-22 ~00:45, same session as 7.41, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.59 | One MOCK task, on a real circuit: synthetic:gpdk045_ota5 replaces the four toy-fixture tasks (2026-09-22 ~01:00, same session as 7.56, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.60 | Virtuoso task flow, part 3: the agent sets the task up - one proposal, written into the working copy ("Ask the agent for suggestions" removed) (2026-09-22 ~01:20, same session as 7.55 / 7.57, explicit user request) | [7.41-7.60.md](workbench-log/7.41-7.60.md) |
| 7.61 | Virtuoso task flow, part 4: the check before every run ("Check against Virtuoso" removed) (2026-09-22 afternoon, same session as 7.55 / 7.57 / 7.60, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.62 | Corner check: a run's best designs simulated again at five corners (2026-09-22, separate session, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.63 | Virtuoso task flow, part 5: running a task measured by Maestro - Maestro's own deck, OCEAN on each run's results (2026-09-22 afternoon, same session as 7.55 / 7.57 / 7.60 / 7.61, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.64 | Repository review: bugs fixed, speed-ups, dead code removed, the record split (2026-09-22, separate session "Project repo optimization review", user: "Check the project repo, is there anything to be optimized or deleted", then chose every proposed action) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.65 | Save task moves up to the editors' tab line; fewer buttons, as the flow has them (2026-09-22 ~17:10, same session as 7.55 / 7.57 / 7.60 / 7.61 / 7.63, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.66 | Real runs write any value the PDK's property form lets you type, not only transistor widths (2026-09-22 evening, same session as 7.54, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.67 | A task can start a circuit that does not start by itself: initial conditions (2026-09-22 evening, same session as 7.55 / 7.57 / 7.60 / 7.61 / 7.63 / 7.65, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.68 | The agent works in Virtuoso itself: the workbench's own tools, granted per request kind (2026-09-22 evening, same session as 7.48 / 7.50, explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.69 | Repository review, round 2: nine correctness fixes, four speed-ups, one formatter, one pop-up window (2026-09-23, same session as 7.64, user: "Check another round", then chose every proposed group) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.70 | Repository review, round 3: identical code merged, nothing else changed (2026-09-23, same session as 7.64 / 7.69, user: "recheck the repo ... shorten code without affecting any functionality") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.71 | A task keeps its initial conditions when it is saved again - the ring task had lost them (2026-09-23 early morning, same session as 7.67, found while restarting the backend on the user's request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.72 | The Virtuoso cellview import moves into a window; the workbench makes no working copy - the user's copy is declared on the read; the column keeps the registered task (2026-09-23 afternoon, session "Virtuoso cellview import workflow", explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.73 | The OTA5 and VCO examples removed: their Virtuoso cells deleted (backup kept), their built-in tasks withdrawn; OTA7, LDO and the MOCK task stay (2026-09-23 afternoon, session "whole flow", explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.74 | ngspice netlist tasks: a SPICE deck becomes a task in the ngspice window and runs on an ngspice connection (on this machine or over SSH); ngspice-47 built and installed on this WSL (2026-09-23 evening, session "ngspice netlist input and SSH support", explicit user request) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.75 | Project column: the two window launchers (Virtuoso cell..., ngspice netlist...) arranged as one aligned grid; the Virtuoso browser check repointed from the withdrawn VCO task (2026-09-23 evening, same session as 7.74, user: "arrange this part to make it more readable") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.76 | Project column: the launcher follows the connection in use - a Virtuoso connection shows "Virtuoso cell..." only, an ngspice connection "ngspice netlist..." only, none shows both (2026-09-23 evening, same session as 7.74 / 7.75, user: "if it is connected to virtuoso then hide the ngspice netlist, if it connected to ngspice then show the ngspice load") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.77 | Project column: the ngspice tasks in the Task list follow the connection in use as the launcher does - under a Virtuoso connection the example `ngspice:ota5_level1` is no longer listed, except while the page follows it (2026-09-24, session "ngspice 5tota example visibility", user: "make the ngspice 5tota example show only when ngspice is connected") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.79 | Connection module: "Virtuoso on this machine" and "ngspice over SSH" added to the user's connection file by hand (backup kept); the ngspice note in the window says the ngspice agent aid is under construction; the connection check brought up to date after 7.74 / 7.76 (2026-09-24, session "ngspice 5tota example visibility", user: "add ngspice over ssh, virtuoso local connected in the connection module. With comment says the ngspice agent aid is under construction") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.78 | Project column: "Load task" (was: Load starter configuration) with "Delete task" at its right in one row; a finished Single baseline simulation records itself as the task's reference - the worker at the end of the run, the task's next load for a run made before; record_reference had refused every Maestro-measured task ("unexpected metrics freq, vmax") (2026-09-24, session "project module buttons + baseline prompt", explicit user request + user report) | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.80 | Connection: one test of the connection in use when the page opens - the same as "Test connection", once per page; still no timer and nothing when the window opens or a connection is chosen; reverses the 2026-09-20 rule for this one case (2026-09-24, session "project module buttons + baseline prompt", user: "when opening the frontend page, make the connection test once") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
| 7.81 | Project Python environment rebuilt at `~/analog-optimizer-venv` after a WSL restart emptied `/tmp` (the old `/tmp/analog-optimizer-venv` is gone); exact `constraints.txt` pins reproduced and verified, 1256 tests pass; path swapped in CLAUDE.md, README, docs/workbench.md (with the no-sudo rebuild recipe), constraints.txt and three check scripts (2026-09-24, session "前端启动指南", user: "what if after reboot the /tmp/ disappeared? What other files are in the tmp?") | [7.61-and-later.md](workbench-log/7.61-and-later.md) |
