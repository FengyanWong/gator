# Workbench development record: the record's history

Moved here unchanged from the index (`docs/frontend_implementation_status.md`) on 2026-09-30, so that the index
every session reads first stays short: the reading guide written on 2026-09-22 (section 0) and the commit table.
Additions made since are marked "(2026-09-30)". **A new commit row goes at the end of the commit table below.**

## How the record was split

The record itself moved, unchanged, into `docs/workbench-log/` on 2026-09-22 (entry 7.64): as one file it had reached
330 kB (about 80k tokens), and a default read stopped at entry 7.43, so a session saw nothing of the newest twenty.

(2026-09-30) The open file was rolled over twice since, under the index's rule: `7.61-7.80.md` was closed on
2026-09-26 (7.85) and `7.81-7.100.md` on 2026-09-29 (7.101); `7.61-and-later.md` and `7.81-and-later.md` stay as
pointers for old links. On 2026-09-30 the index's rows were cut to one short title per entry and this history moved
here. The longer rows, summaries of each entry whose details are in the entries themselves, are in the index as of
commit `6080079`.

## 0. Reading guide (written 2026-09-22 ~00:05 for an outside review; updated for the split, 7.64)

`first-build.md` describes the FIRST build (commit `bcf7c5e`, 2026-09-20 ~17:44) and was never rewritten; the entries
7.1 onwards, newest last, are everything since. A later entry supersedes an earlier one without editing it, so the
entries - not sections 3-6 of the first build - say what is true now. Elsewhere: `docs/workbench.md` (the user-facing
description), `CLAUDE.md` (rules), the specification `gator_claude_code_fable51_frontend_data_outputs_en.md` (untracked
on purpose), and the research history of the optimizer package (M1-M6) in `docs/decisions.md` and `docs/m*-*.md`.

Outdated in `first-build.md`, and the entry that changed it:

* 6.1 "no real Virtuoso/Spectre evaluation": ONE authorized real Spectre evaluation ran through the workbench - a
  generated ring-oscillator profile's baseline, which also found and fixed the bug that had made every real task
  unrunnable (7.24). (2026-09-30) Many real simulations have run through the workbench since, e.g. 7.63 and the 73
  Spectre calls of reward v2's qualification (7.95).
* 6.2 "agent CLIs absent": `claude` is on the PATH and used for real since 7.6 (live answers 7.48). The Codex provider
  has never run against a real CLI (built from its documentation and fake-CLI fixtures; live answers 7.50).
* 6.4 "no call lists cells": cells are listed with SKILL taken from the bridge's own examples (7.15).
* 6.5 "not implemented": Maestro outputs, specs and design variables are read from and written to a working COPY (7.55);
  a task measured by Maestro runs (7.63). PVT: a run's best designs can be simulated again at five corners (7.62).
  Monte Carlo: still none. (2026-09-30) The OTA7 task can also train at corners (reward v2, 7.94-7.95; `after_nominal`,
  7.106); for Monte Carlo there is a plan only (7.103 / 7.104, `docs/plan-finalist-monte-carlo.md`).
* 6.7 "not exercised in a browser": headless-Edge checks since 7.8; on 2026-09-23, 28 check scripts in
  `frontend/scripts/*.mjs` (2026-09-30: 36) plus the shared harness `frontend/scripts/lib/harness.mjs` (7.64). Most
  of them drive the LIVE backend on 8765 unless `GATOR_WORKBENCH_URL` is exported through `WSLENV`.
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
  (2026-09-30) Added after 7.74: `api/models.py`, `api/context.py`, `api/support.py` and the four route modules
  `api/settings_routes.py` / `circuit_routes.py` / `run_routes.py` / `agent_routes.py` 7.85 (the split of `api/app.py`,
  now their composition root), `structures.py` 7.103, `reachability.py` + `reward_diagnostics.py` 7.106; panels
  `popupWindow.ts` 7.69, `Icons.tsx` 7.82, `AgentTab.tsx` + `RunTabs.tsx` (the split of `Bottom.tsx`) and
  `CircuitBrowser.tsx` 7.85, `MatchedDevices.tsx` 7.103.

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
* The Run status tab's own run commands (with the header's questions since 7.64), "Bring it back here" (7.14),
  "Record the baseline run as reference" (7.21), the header's "Static validation", the Virtuoso window's "Open" and
  old-backend fallback, and `run.threads_per_job` ("recorded, applied by no task" since the first build) -> removed on
  the user's choice (7.109). Old configurations still load, with both hashes unchanged.
* (2026-09-30) Per-encoder settings for six encoders (7.7) -> `port_gnn` removed (7.83), MLP and GCN removed (7.86),
  GATv1 replaced by GATv2 (7.87): Graph Transformer, RGCN and GATv2 remain.
* (2026-09-30) The connection checked only on a button press, nothing on page load (7.9) -> one test of the
  connection in use when the page opens; still no timer (7.80).
* (2026-09-30) "Load PDK" in the RL network block (7.54) -> the cell's PDK is read with the cell, and "PDK window..."
  sits in the Virtuoso window; the RL network block only chooses the component list (7.100).
* (2026-09-30) The working copy the workbench made, `<library>_GATOR` ("Make a working copy", 7.55) -> the workbench
  makes no copy: the user copies the cell in Virtuoso and declares it a copy on the read (7.72). Tasks saved on a made
  copy keep running on it.

Known slips inside the entries (left as written):

* 7.40's heading says 2026-09-22; it was written on 2026-09-21 (committed in `c3b9691` at 17:57).
* 7.50 says `codex` "is installed neither in WSL nor on Windows". The Codex desktop app on this machine ships a CLI
  (`codex-cli 0.155.0-alpha.9.2`, a Linux build inside the app's settings folder, not on the PATH), so the provider
  could be tried for real - a request costs usage, so that is the user's decision.
* Commit `155c261`'s message names only 7.18, but it holds the code of 7.18 AND of 7.19 / 7.21 (the shared git index
  swept a peer's work in); the empty commit `9cf670b` carries the message for the 7.19 / 7.21 part; `6ac02b9` holds
  7.18's entry.
* (2026-09-30) Entries 7.107, 7.108, 7.110, 7.111 and 7.112 were written with `##` headings instead of `###`. Only their
  heading markers were changed, so that `grep -n '^### 7\.' docs/workbench-log/*.md` finds every entry.

Not recorded here: the ring oscillator `GPDK045_RINGOSC/ring_osc_3stage` + `tb_ring_osc_3stage`, which 7.17 onwards
read, turn into a profile and simulate, was built on 2026-09-20 by a separate session outside this repository (scripts
in `~/ring_osc_gpdk045`; 3 stages, MIM-cap loads, 1.209 GHz in one standalone Spectre transient outside every GATOR
budget).

## Commit table

One row per commit, newest last.

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
| `715aaa2` | 09-23 03:11 | - | record only: names the commit that carries review round 2 (7.69); its row was added on 2026-10-02 (7.139) |
| `e4ef6b4` | 09-23 03:54 | 7.70 | review round 3: identical code merged only; nothing under `src/analog_optimizer` |
| `8bb464e` | 09-23 03:55 | - | record only: names the commit of 7.70 |
| `043386a` | 09-23 16:25 | 7.72 | Virtuoso cellview import in a window; the user's copy declared on the read |
| `cbace5b` | 09-23 16:34 | 7.71 | a task keeps its initial conditions when saved again |
| `a9d84f1` | 09-23 16:41 | 7.73 | OTA5 and VCO examples removed |
| `30a3ac7` | 09-23 18:28 | 7.74 | ngspice netlist tasks |
| `eb51e05` | 09-23 19:36 | 7.75, 7.76 | Project column launchers |
| `bfc624d` | 09-24 00:32 | 7.77, 7.78, 7.79 | baseline records itself; Load task / Delete task; ngspice tasks follow the connection |
| `9ea7f44` | 09-24 13:34 | 7.80 | one connection test when the page opens |
| `b7aa607` | 09-24 13:34 | 7.81 | venv at ~/analog-optimizer-venv |
| `bbdfe36` | 09-24 14:22 | 7.82 | icon-only buttons (header, toolbar, task row); last commit with the M6 digest `02127bc3...` |
| `8d647cd` | 09-24 15:46 | 7.83 | `port_gnn` removed from the package; digest `aa987cf0...` |
| `9bc488f` | 09-24 19:04 | 7.84 | icon-only buttons in the bottom tabs |
| `134a4a5` | 09-26 18:38 | - | docs only: the robust-reward plan and the Astra brief with the reward's shape |
| `db8a966` | 09-26 19:53 | 7.92 | fourteen columns deleted from Parameters and Probes |
| `59245dd` | 09-26 20:03 | 7.90, 7.91, 7.93 | clickable Mode suggestion; per-file download buttons; live build |
| `1135b8b` | 09-27 04:25 | 7.85-7.89, 7.94-7.98 | three authors in one commit (their hunks interleaved): MLP/GCN removed, GATv2, API/frontend split (Codex); reward v2 + real qualification (Astra); audit and fixes (Claude); package digest `75c7cfac...` -> `5e8a1bc1...` -> `3473ed9c...` -> `f087a4ce...` |
| `eedbb3f` | 09-27 04:26 | - | record only: names the commit of 7.85-7.89 and 7.94-7.98, and the table rows since 7.70 |
| `ce4cc4a` | 09-28 14:30 | 7.100 | a cell's PDK is read with the cell; "Load PDK..." moves to the Virtuoso window |
| `c8fdc5c` | 09-29 15:45 | 7.101, 7.102 | review round 4: repeated code merged, behaviour unchanged (nothing under `src/analog_optimizer`, no test changed); `task_rows_check` fixed; the record file rolled over to `7.101-and-later.md` |
| `73f1668` | 09-29 15:46 | - | record only: names the commit of 7.101 and 7.102, and the table rows since 1135b8b |
| `2835ba3` | 09-29 17:59 | - | docs only: the Astra brief for reward v2.1 (`docs/brief-reward-v2.1-for-astra.md`) |
| `f3fc5af` | 09-29 20:34 | - | docs only: the Astra brief for LLM-driven sizing (`docs/brief-llm-sizing-for-astra.md`) |
| `6238dda` | 09-29 22:53 | - | docs only: the finalist Monte Carlo plan of 7.103 / 7.104 (`docs/plan-finalist-monte-carlo.md`); their entries went in with `5a39f89` |
| `8cf53ae` | 09-29 23:00 | 7.106 | reward v2.1, the optimizer part (`src/analog_optimizer/`, digest `3f00832c...`) and its tests (Astra) |
| `8db46b8` | 09-29 23:03 | 7.106-7.108, 7.111 | reward v2.1, the workbench part: controls, diagnostics, reachability warning, `reward_v21_check` (Astra) |
| `8838dd7` | 09-29 23:10 | 7.105 | Probes lose `conditions` and `aggregation` with the migration (the hashes of all 14 runs unchanged); only this session's hunks, on top of reward v2.1 |
| `d5087c2` | 09-29 23:12 | - | record only: names the commit of 7.105, and its table row |
| `5a39f89` | 09-29 23:13 | 7.103, 7.104, 7.109, 7.110 | all shared work still uncommitted, in one commit "before LLM sizing" (another session): Matched devices, the frontend clean-up of 7.109 (duplicate and dead entries, `threads_per_job` retired), the OTA7 variant plan |
| `63883d3` | 09-29 23:16 | - | record only: names the commit of 7.109, and the table rows since c8fdc5c |
| `7d365c3` | 09-29 23:49 | 7.112 | audit fixes to reward v2.1: the Specs scale suggestion follows the limits; equation specs keep their values on a measurement_error row (session "Analog design bench review and reward improvements") |
| `5ee0c1f` | 09-29 23:49 | - | record only: names the commit of 7.112, and the table row for 63883d3 |
| `7359287` | 09-29 23:55 | 7.112 | follow-up: `spec_equations_check` expects an empty scale for a new row with no limit, and 0.5 once the limit is typed |
| `6c6cc3e` | 09-29 23:55 | - | record only: names the commit of the 7.112 follow-up, and the table row for 5ee0c1f |
| `6080079` | 09-29 23:56 | - | record only: corrects the time of 5ee0c1f in this table (23:49, not 23:52) |
| `9dedc81` | 09-30 00:39 | 7.113 | the Specs equations' old-configuration hash test reads a frozen configuration written by the pre-equations code, with its hashes (session "Parameters, specs, and probes linking in Virtuoso") |
| `44a48a2` | 09-30 00:40 | - | record only: names the commit of 7.113, and the table rows for 6c6cc3e, 6080079 and 9dedc81 |
| `d88b247` | 09-30 00:52 | 7.114 | formula specs marked at training corners, a warning for "Missing value = failed" on a soft spec, save tracking in `spec_equations_check` (only this session's hunks of engine.py / tables.py; Astra's stay uncommitted) |
| `dc33d7e` | 09-30 00:53 | - | record only: names the commit of 7.114, and the table rows for 44a48a2 and d88b247 |
| `1a3f4a7` | 09-30 02:52 | 7.117 | repository review round 5: bugs, speed-ups, session-start docs, test fixes (this review's hunks only; the uncommitted work of 7.115 and 7.116 in the same files left in the working tree) |
| `1fe32c0` | 09-30 02:54 | - | record only: names the commit of 7.117, and the table rows for dc33d7e and 1a3f4a7 |
| `4634200` | 09-30 17:57 | 7.116, 7.120 | LLM sizing, the optimizer part: the `search` package and `ActionMapper.encode` (Astra) with the audit's duplicate-check fix, and the package tests (digest `100945fb...`) |
| `7c7a0ff` | 09-30 17:57 | 7.116, 7.118-7.120 | LLM sizing, the workbench part: the four search methods, the sizing CLI client, the page, ngspice operating points, the AnalogGym harness and calibration drivers (Astra), the audit and the tests of its fixes; the log rolled over to `7.119-and-later.md` (only these records' hunks; 7.115, a third session's Virtuoso fixes and 7.121 left in the working tree) |
| `ad90a45` | 09-30 17:58 | - | record only: names the commits of records 7.116 and 7.118-7.120, and the table rows for 1fe32c0, 4634200 and 7c7a0ff |
| `6e95547` | 09-30 23:11 | 7.121 | record only: the audit of the fixed-bias calibration (7.119) and the final LLM-sizing tree |
| `54153dd` | 09-30 23:40 | 7.124, 7.125 | the Specs constraint list with the objective in it, a narrow tick-box column, "Judged at" only with training corners; the frontend audit's fixes: an honest real-run question, the Agent tab's message box, Import JSON, Save task without the Virtuoso window, Pause/Abort after one failed read, plain banners and field-by-field schema errors, stale answers, fewer requests, Undo per typed value (only this session's hunks; 7.115's poll-rate hunks and other sessions' docs and records left in the working tree) |
| `76b7f26` | 09-30 23:42 | - | record only: names the commit of records 7.124 and 7.125, and the table rows for ad90a45, 6e95547 and 54153dd |
| `898b134` | 10-01 02:32 | 7.126 | the optimizer part of the optimization review's package changes: corner jobs two at a time, `CircuitSizingEnv.reset_reused`, Maestro results not parsed (digest `f42a3098...`; only this record's hunks, the uncommitted optimizer work of 7.129 and 7.132 left out) |
| `e2584fa` | 10-01 02:41 | 7.115, 7.126-7.128 | the workbench part: torch-free Check/Start children, reused connection checks, the parallel browser-check runner, a status poll that follows the run, every 5th reset simulated, the form writer types lengths first, the MOCK task and real OTA7/LDO deleted with their files (only these records' hunks) |
| `8d65727` | 10-01 02:43 | - | record only: names the commits of records 7.115 and 7.126-7.128, and the table rows for 76b7f26, 898b134 and e2584fa |
| `eb46c30` | 10-01 02:54 | 7.131 | the review after the frontend audit: the page's task loads keep a saved task while its files are unchanged (`tasks.load_task_view`), the repository path resolved once, the saved-model check's second task load gone; ten frontend fixes (the Undo merge follows the input event, a new AI run's thread, a refused hint, Continue during the header's Resume, Read against a task chosen meanwhile, the Cell settle, the Mode suggestion in scratch, "(not set)", one more Logs read, busy per connection) |
| `5674ecb` | 10-01 02:55 | - | record only: names the commit of record 7.131, and the table rows for 8d65727 and eb46c30 |
| `5362ebb` | 10-01 02:58 | 7.129 | the optimizer fixes held back from review round 5, digest `0d045b8e...`: the top grid point clamped, a corner summary without a flagged value, a late worker result, three copies and the MOCK journal fsync removed, 10 unused imports |
| `5b3da95` | 10-01 02:59 | - | record only: names the commit of record 7.129, and the table rows for 5674ecb and 5362ebb |
| `26793a4` | 10-01 03:14 | 7.133 | the follow-ups of 7.126-7.128: the warm-start budget note counts only the resets a run pays for (`runs.warm_start_resets`), the ngspice refusal test back on a saved task, the five other MScR tasks run on the simulator with the fixed form writer |
| `5451d65` | 10-01 03:15 | - | record only: names the commit of record 7.133, and the table rows for 5b3da95 and 26793a4 |
| `8edbf6d` | 10-01 03:21 | 7.132 | the optimizer part of record 7.132: the Spectre parser pairs `[ ]` like `( )`, so a PWL `wave=[...]` source parses (digest `46327861...`; only this record's hunks) |
| `39401ba` | 10-01 03:21 | 7.132 | the workbench part: noise statements with terminals, analogLib `res` rows (`cdf_facts.TOOL_DISPLAY`), pcell subckts numbered by definition order, `iprobe` a verified device, Save task refuses equations naming no Probe; MScR noise specs and optimized resistors |
| `a083a11` | 10-01 03:21 | - | record only: names the commits of record 7.132, and the table rows for 5451d65, 8edbf6d and 39401ba |
| `f3fe825` | 10-01 03:25 | 7.130 | Codex's frontend reliability follow-up, committed on the user's request by session "Parameters, specs, and probes linking in Virtuoso": autosave failures kept unsaved with Retry save / Export JSON, encoder replies tied to the current choice, 30 s read deadlines with cancellation, a memoized validation key, narrow-window layouts, reliability_check; the index's 7.129 row moved to its place |
| `871cb25` | 10-01 03:26 | - | record only: names the commit of record 7.130, and the table rows for a083a11 and f3fe825 |
| `20ccdac` | 10-01 13:56 | 7.134 | the run lock's liveness test takes a shared lock: a test at the same moment was taken for a worker, so the header's "Start" went back to "Aborting..." and a Start or Resume could be refused as "already running"; acquire waits 0.2 s for a test; test_wb_run_lock |
| `4652209` | 10-01 13:56 | - | record only: names the commit of record 7.134, and the table rows for 871cb25 and 20ccdac |
| `d71323f` | 10-01 14:10 | 7.135 | review round 5's open items: agent CLIs stop with the backend (a 5 s shutdown grace, a lifespan that cancels them), a run paused for infrastructure failures resumes, a candidate stopped before its launch is cancelled, Apply once, an atomic ngspice deck, no proxy for the tool relay, the resume lock given back; the random test failures explained (only this record's hunks) |
| `87f4dd8` | 10-01 14:11 | - | record only: names the commit of record 7.135, and the table rows for 4652209 and d71323f |
| `d3f72e7` | 10-02 19:05 | 7.139 | `docs/functionality-reference.md` (every function with its code, route, entries, tests and checks) and the check of 2026-10-02; docs only, this entry's hunks only |
| `4597fc6` | 10-02 19:06 | - | record only: names the commit of record 7.139, and the table rows for 87f4dd8 and d3f72e7 |
| `cd8f68a` | 10-02 19:08 | 7.141 | a parameter bound to a Maestro variable gets its own value back: kept when the workbench binds it (`values_before_binding.json`), and a binding whose value is not known is refused instead of writing the variable's name back (only this record's hunks; the new line in HEAD's `Path(target['state_dir'])` form) |
| `f5da116` | 10-02 19:09 | - | record only: names the commit of record 7.141, and the table row for cd8f68a |
| `c700032` | 10-02 19:37 | 7.144 | the GPDK045 profiles' copied checks merged into one shared class (`Gpdk045MappedProfile`), every message kept; two dead cache branches and an in-loop import gone; behaviour identical, digest `4632786135d1...` -> `41983cc79771...` (only this record's hunks) |
| `6b61967` | 10-02 19:38 | - | record only: names the commit of record 7.144, its digest in decisions.md, and the table rows for f5da116 and c700032 |
| `1c308a5` | 10-02 20:06 | 7.137, 7.140, 7.142, 7.143 | the optimizer part: three cell reads per candidate; netlists built from the readback with a native export and comparison every 5th candidate (`GATOR_NETLIST_BUILD`, default `skip`); OCEAN set up once per export session (not for Maestro tasks); a value one float step past its bound accepted (`ParameterGroup.validate`, `ActionMapper.encode`); up to 6 Spectre lanes; digest `34bc85f4...` |
| `8043c07` | 10-02 20:06 | 7.136-7.138, 7.140, 7.142, 7.143, 7.145 | the workbench part: lanes open side by side, `CdfWritableProfile.render_export`, `working_copy.state_path`, `tasks.REAL_LANES`; the concurrency, export and Spectre measurements and the two investigations |
| `bb1aadb` | 10-02 20:08 | - | record only: names the commits of records 7.136-7.145, their digest in decisions.md, and the table rows for 6b61967, 1c308a5 and 8043c07 |
| `362f447` | 10-02 21:24 | 7.139 | the functionality reference follows records 7.140-7.145 (committed rows lose their "uncommitted" mark, 6 Spectre jobs, 7.144, 7.145; no digest in its state line); Astra's 7.146/7.147 rows left in the tree |
| `21c0334` | 10-02 21:24 | - | record only: the table rows for 4597fc6, bb1aadb and 362f447 |
| `d8b8c4f` | 10-02 21:46 | 7.122, 7.123, 7.146-7.148 | every finished change in the tree, on the user's "commit everything and push" (session "Work review and functionality references"): Astra's LLM-sizing comparison protocol, its task selection with Reload saved values and its Matched devices button, and the lane-OCEAN trial's note and plan; left in the tree: 7.149's unfinished local scratch and a new RL-network window in progress; three browser checks updated for 7.146's page |
| `1cfb08b` | 10-02 21:47 | - | record only: names the commit of records 7.122, 7.123 and 7.146-7.148, and the table rows for 21c0334 and d8b8c4f |
| `60087c7` | 10-03 17:24 | 7.156 | the "REAL evaluation backend" banner under a loaded real task removed (Start's budget question unchanged); project_help_check asserts it is gone; the other sessions' 7.149-7.155 left in the tree |
| `3fb0d9e` | 10-03 17:24 | - | record only: names the commit of record 7.156, and the table rows for 1cfb08b and 60087c7 |
| `94d100d` | 10-03 17:33 | 7.155 | Agent tab model lists: Codex's read from the Codex app's own models_cache.json (the account's models, "Re-read list"), hand table as fallback; Claude Code table re-checked (older pinned versions); only this session's hunks, the other sessions' 7.149-7.154 left in the tree |
| `423f3c9` | 10-03 17:34 | - | record only: names the commit of record 7.155, and the table rows for 3fb0d9e and 94d100d |
| `c5287e1` | 10-03 18:07 | 7.154, 7.157 | a trimmed model library for any circuit (the parts of the model file a circuit's devices need, read on the simulator host by names only; for tasks with a recorded baseline) and Maestro's six unread info outputs left out of run decks (about 0.36 s less per Spectre job); both verified on Spectre; this session's 7.149, 7.152 and 7.153 and the other sessions' work stay uncommitted |
| `2a6a0a2` | 10-03 18:08 | - | record only: names the commit of records 7.154 and 7.157, and the table rows for 423f3c9 and c5287e1 |
| `ab34f03` | 10-03 18:26 | 7.149 | optimizer: the window check before each native export only, not before every write (one Virtuoso call less per built candidate); digest 34bc85f4 -> f83342bc |
| `a16bdd1` | 10-03 18:26 | 7.149, 7.152, 7.153 | simulator scratch on the local disk for runs on a slow mount (D: 0.84 -> 0.50 s per evaluation); records 7.149, 7.152 (a Spectre that stays running: built, tried, removed) and 7.153 (a trimmed model library, investigation); docs/plan-persistent-spectre.md; the other sessions' work stays uncommitted |
| `84ced3d` | 10-03 18:27 | - | record only: names the commits of records 7.149, 7.152 and 7.153, the optimizer digest set by ab34f03, and the table rows for 2a6a0a2, ab34f03 and a16bdd1 |
| `2608f4e` | 10-03 19:46 | 7.150, 7.151 | Codex's RL networks window (Mode first, Search method second; network settings, saved models, model views and Advanced in a separate window; both failure limits in a fold-out; cross-window Undo) and the saved-default comparison (This run / Saved default table, Use saved defaults, Save as defaults); committed hunk-exact by the session "Frontend workbench layout design", whose 7.159, 7.160 and 7.163 build on it |
| `2ae2ad2` | 10-03 19:46 | 7.158-7.160, 7.162-7.164, 7.166 | two looks (Whiteprint, Silicon Night) by a header switch, a title block, the bottom panel's splitter, one-line ids, a colour per editor, the circuit picture, Windows' fonts; the Project name box removed and the RL model's own label (`run.model_label`); the network in short beside RL networks...; the looks share every size and one tab style; the RL networks window without its own close button, one "Search method", Research experiments trimmed (experiment_group, test_tasks retired) and headed like the modules; the other sessions' 7.161, 7.165, 7.167 and 7.168 left in the tree |
| `ae695a8` | 10-03 19:49 | - | record only: names the commits of records 7.150, 7.151, 7.158-7.160, 7.162-7.164 and 7.166, and the table rows for 84ced3d, 2608f4e and 2ae2ad2 |
| `0a0f5e3` | 10-03 20:05 | 7.161, 7.165, 7.167-7.169 | every change in the tree, on the user's "commit everything and push" (session "Work review and functionality references"): the run adapter's lock and journals on the WSL disk, the Connection window's folder settings, the Research heading's hand pointer, two investigations' records, and the reward-settings simplification plan |
| `f5ab182` | 10-03 20:06 | - | record only: names the commit of records 7.161, 7.165 and 7.167-7.169, and the table rows for ae695a8 and 0a0f5e3 |
| `a127c97` | 10-04 05:07 | 7.170, 7.171 | the connection window's Folders as a section of its own, headed like the steps (a folder sign in the circle; a zero-width character against the pop-ups' quirks mode), each folder's comment in its name's tooltip; the three 0-to-1 reward boxes without the browser's up/down arrows; 7.172 (editor columns, another session) left in the tree |
| `e1e2974` | 10-04 05:08 | - | record only: names the commit of records 7.170 and 7.171, and the table rows for f5ab182 and a127c97 |
| `7a3a603` | 10-04 06:38 | 7.172 | the editor columns that repeated another: Specs target/tolerance and Probes expression retired with a migration (identities kept), initial_value and result_source hidden, four Parameters columns behind More columns, three filled for you; six faults fixed (Read setup's analyses and spec settings, Add in a Maestro task, the run digest's units, fixed rows, notes-only edits) (session "Parameters, specs, and probes linking in Virtuoso", committed by "Virtuoso read whole flow") |
| `82544af` | 10-04 06:39 | - | record only: names the commit of record 7.172, and the table rows for e1e2974 and 7a3a603 |
| `6ff869d` | 10-05 01:28 | 7.173 | a drop-down's open list in the look's own colours: every option on the field colour in the text colour (in Silicon Night an editor cell's list had come out light under light text); 7.174 (audit fixes, another session) left in the tree |
| `63541b8` | 10-05 01:29 | - | record only: names the commit of record 7.173, and the table rows for 82544af and 6ff869d |
| `5ff6a3e` | 10-05 02:15 | 7.175-7.177 | the editors' formula bar (a chosen cell's whole value in a box as wide as the table, written by Enter as one Undo step, Esc keeps the cell; lists, tick boxes and following values shown, not typed); the lines above Parameters and Specs and the saved task's run-check note cut to their fact, the explanations in tooltips; 7.174 (audit fixes, another session) left in the tree |
| `09fe0b4` | 10-05 02:16 | - | record only: names the commit of records 7.175-7.177, and the table rows for 63541b8 and 5ff6a3e |
| `8d2c5a0` | 10-05 02:45 | 7.178 | checks only: the harness hands a check its pop-up once the pop-up's copied stylesheets are in (about one RL networks window in five was unstyled for ~100 ms when found), and pdk_check reads the PDK window's list once it has arrived - pdk_check's two timing failures; 7.174 (another session) left in the tree |
| `82003e7` | 10-05 02:46 | - | record only: names the commit of record 7.178, and the table rows for 09fe0b4 and 8d2c5a0 |
| `a067643` | 10-05 03:49 | 7.179, 7.180 | from the design advice: the bottom panel folded while no run is shown, Run configuration as a property sheet with one Limits fold, Output settings in one-line summaries; tied Parameters rows folded under their leader, Up / Down / Enter between rows, a block pasted from Excel as one Undo step, content-sized columns; 7.174 (another session) left in the tree |
| `da5b962` | 10-05 03:49 | - | record only: names the commit of records 7.179 and 7.180, and the table rows for 82003e7 and a067643 |
| `bc644b1` | 10-05 04:32 | 7.181 | readable small and large numbers in the editor tables: a bound, limit or scale of a row in an unprefixed base unit in engineering notation (0.0004 A as 400µ), SI letters taken when typed or pasted, the formula bar exact; the rest of the design advice weighed (red Abort and pop-ups are the user's requests, the status strip waits for an answer); 7.174 (another session) left in the tree |
| `bbd7e6a` | 10-05 04:32 | - | record only: names the commit of record 7.181, and the table rows for da5b962 and bc644b1 |
| `cac885f` | 10-05 06:14 | 7.182 | the Connection button in the header's title block and the task name out of it (user); Corner check and the corner training choices only where corners can be used; the tick box and the row's ID stay in view while a table scrolls sideways (measured offset with a ResizeObserver, per-cell lines so nothing shows through); two labels without internal names; 7.174 and 7.183 (other sessions) left in the tree |
| `d1e51ff` | 10-05 06:15 | - | record only: names the commit of record 7.182, and the table rows for bbd7e6a and cac885f |
| `40d5f61` | 10-05 06:33 | 7.174 | five frontend/backend audit fixes: torn-journal repair, late Save task replies, legacy computed-probe migration, Codex strict proposals, pure Undo/Redo; regression coverage and deployment checks; only this audit's hunks |
| `a09cd40` | 10-05 06:35 | - | record only: the Commit paragraph of record 7.174, and the table rows for d1e51ff and 40d5f61 |
| `4a106f5` | 10-05 06:43 | 7.183 | the tested defaults: the GATOR baseline holds starting temperature 0.01, 8 updates per evaluation and discount 0 (with the old values soft actor-critic is a random search and no reward setting matters); validation warns of values that do not learn and of a from-scratch SAC budget below 300; a new configuration's reward in one sentence, its controls in an Advanced fold, other values named with "Use the tested reward"; Specs scale = the size of the limit (6 dB for dB), `hard` and Scale behind More columns; the schema's defaults unchanged; the entry also records the bridge daemon's request list set to 32768 in the running Virtuoso; only this record's hunks, carried onto a09cd40 by a three-way merge; 7.184 (another session) left in the tree |
| `9575233` | 10-05 06:46 | - | record only: names the commit of record 7.183, and the table rows for a09cd40 and 4a106f5 |
| `ef0f2b0` | 10-05 14:01 | 7.184 | the editor tables' last spreadsheet pieces: a find box (only the rows whose text cells hold every word stay in view), Ctrl+D fills down, Ctrl+C and a Copy for Excel button take a block out with a header line that a paste back skips; one write path for typed, pasted and filled cells (a pasted output name renames its Probe ID; a limit keeps only an objective that pairs) |
| `5c5d127` | 10-05 14:02 | - | record only: names the commit of record 7.184, and the table rows for 9575233 and ef0f2b0 |
| `ad8750a` | 10-05 14:31 | 7.187 | "Save task" refused every cell holding an ideal current source or resistor since the example circuits were deleted (7.128): the two device definitions, lost with the LDO example's mapping file, are the workbench's own now (`native_cells.ANALOGLIB_VERIFIED`), found by the user's "fill them with 6"; the Scale column's explanation in 54 words instead of 74; only this record's hunks, 7.185, 7.186 and 7.188 (other sessions) left in the tree; the four saves wait for a restart of 8765 |
| `4f3f01d` | 10-05 14:31 | - | record only: names the commit of record 7.187, and the table rows for 5c5d127 and ad8750a |
| `0857ecf` | 10-05 14:34 | 7.186 | the Agent tab's agent starts with a named list of built-in tools (no messages to other sessions, claude.ai routines, notifications, artifacts or workflows); claude.ai documents read-only to it; Virtuoso tools kept |
| `08b60ca` | 10-05 14:35 | - | record only: names the commit of record 7.186, and the table rows for 4f3f01d and 0857ecf |
| `6f75c3d` | 10-05 14:57 | 7.185, 7.188 | the editors' toolbar on one line at 1366 px (the find box shrinks, its count inside it); a crash panel instead of a blank page (Undo the last change, Export JSON, Reload; an empty start without Undo); Ctrl+Z / Ctrl+Y in the tables; the editor tables' headers in plain words, the field names in their tooltips; the "no real baseline yet" note in one line |
| `f388bd2` | 10-05 14:58 | - | record only: names the commit of records 7.185 and 7.188, and the table rows for 08b60ca and 6f75c3d |
| `358cc85` | 10-05 15:02 | - | record only: the four saves of record 7.187 (13 dB rows hold Scale 6), and the table row for f388bd2 |
| `f185152` | 10-05 15:26 | 7.189 | a lighter page opening: the output folder no longer walked for its size at every page open (0.7 to 2 s on D:), a Measure button asks for it; the page's weight measured (128 ms, 6 MB, a 504 KB script; the graph library already loaded on demand) |
| `43bfcc8` | 10-05 15:27 | - | record only: names the commit of record 7.189, and the table rows for 358cc85 and f185152 |
| `661aca8` | 10-05 15:35 | 7.190 | Load PDK reads the ideal parts too: analogLib's own description - the Spectre component and pin order of each cell - read with every PDK and stored in its record; a cell's sources, ideal R / C / L, probes and controlled sources recognized from it (verified definitions first, so saved tasks keep their pin names; the pin order chosen by the netlist's node count; no kind of its own = "unknown" with pins named); the PDK read before a cell's device mapping; the PDK window lists the ideal parts; only this record's hunks, 7.191 (another session) left in the tree |
| `5da9613` | 10-05 15:35 | - | record only: names the commit of record 7.190, and the table rows for 43bfcc8 and 661aca8 |
| `f2562ef` | 10-05 16:11 | - | record only: record 7.190 is live (the page, one restart of 8765, one read of the PDK), and the table row for 5da9613 |
| `b3a00a2` | 10-05 16:26 | 7.191, 7.192 | the GATOR baseline and both preset buttons deleted (and the reset route behind them); one starting preset per encoder: the published network size with every training number of the runs that learned on GATOR circuits (temperature 0.01, 8 updates per evaluation, discount 0, batch 8, learning rate 3e-4, warm-up 8, replay 10,000, episode 4); an encoder that was on the baseline reads as its starting preset |
| `aee45aa` | 10-05 16:27 | - | record only: names the commit of records 7.191 and 7.192, and the table rows for f2562ef and b3a00a2 |
| `7f52cfe` | 10-05 16:54 | 7.196 | Load PDK sees through a diode wrapped with its series resistance: one diode with only resistors beside it on every path between a subcircuit's first two pins is a diode, its pins anode / cathode through the series resistor; GPDK045's version unchanged (fa5c3946) |
| `a932948` | 10-05 16:55 | - | record only: names the commit of record 7.196, and the table rows for aee45aa and 7f52cfe |
| `e1e9018` | 10-05 17:03 | 7.195 | the Advanced fold of the RL networks window directly below "Nominal device operating points", with the slow-learning warning above it; in a Mode that loads a model it still closes the window |
| `c7b00c5` | 10-05 17:04 | - | record only: names the commit of record 7.195, and the table rows for a932948 and e1e9018 |
| `6c4e8eb` | 10-05 18:00 | 7.193 | the Training tab beside Output files: live uPlot charts of what a run records - step reward (no episode return is recorded), share meeting every hard spec, evaluation success rate of frozen runs, specs against their limits, best design, SAC losses, temperature, entropy - read from the run's tables and the journal's unpublished tail (`GET /api/runs/training`), at most one redraw a second, nothing while hidden; values checked equal to recorded Spectre runs; `uplot` 1.6.32 added; only this record's hunks |
| `2f66279` | 10-05 18:01 | - | record only: names the commit of record 7.193, and the table rows for c7b00c5 and 6c4e8eb |
| `1296bfe` | 10-05 18:16 | 7.194, 7.198 | Save task shows its steps while it works (a bar and "step N of M" under the toolbar) and allows one save at a time, also after the page is loaded again (GET /api/tasks/saving, 409 save_running, Delete refused while that task saves); why two presses of Save task from a page with older rows took mscr_ldo2_rgcn's Scale 6 out, and its restore through the live Save task |
| `5a7500d` | 10-05 18:19 | - | record only: names the commit of records 7.194 and 7.198, and the table rows for 2f66279 and 1296bfe |
| `5f5fbd2` | 10-05 18:26 | 7.197 | calibration with the baseline run: a tick "+ calibration" beside Single baseline simulation, on by default - the run goes on with 64 random designs and proposes a Scale per Specs row (the median miss among the designs that miss it) and the Initial alpha (0.1 x the reward's spread); nothing is applied by the run, Run status shows the proposals and Apply calibration writes them as one Undo step; an invalid baseline ends the run before any random design. In training measured on ngspice only (99.1 % against 97.0 % passing designs, about 7 % more power); the run itself checked once on Spectre (real:mscr_ota7t, 65 simulations) |
| `d83b308` | 10-05 18:27 | - | record only: names the commit of record 7.197, and the table rows for 5a7500d and 5f5fbd2 |
| `a0bce06` | 10-05 18:46 | 7.202 | one "Baseline simulation" button: the "+ calibration" tick gone, every baseline run calibrates (the baseline alone = Abort once the random designs begin); "Single baseline simulation" renamed in every text; Check now stays the free check (the user's choice after advice) |
| `d47f72c` | 10-05 18:48 | - | record only: names the commit of record 7.202, and the table rows for d83b308 and a0bce06 |
| `74e015d` | 10-05 18:49 | 7.202 | follow-up: typing_check finds the Baseline simulation button by its name (it looked for the old tooltip "ONE costed"); the entry says so; the table row for d47f72c |
| `55e47aa` | 10-05 19:00 | 7.206 | the Abort question of a Baseline simulation says the baseline is kept, a task saved from a cell without a reference still gets it, and the calibration proposes only from the random designs simulated so far (at least 16) |
| `dfef323` | 10-05 19:00 | - | record only: names the commit of record 7.206, and the table rows for 74e015d and 55e47aa |
| `f97bc6e` | 10-05 19:21 | 7.200, 7.201 | several runs on one Training chart (session "Training tab with live graphs"); the Training tab's audit fixes - best feasible objective only when feasible, live journal rows paged with their own cursor (the user's Codex session); one commit, the two share their lines |
| `aa5e3f9` | 10-05 19:21 | 7.203 | Save task asks before rows older than the saved task replace it; the check points to Reload saved values (session "Parameters, specs, and probes linking in Virtuoso") |
| `d711528` | 10-05 19:21 | 7.199 | learning rate 1e-3 in the starting presets, the presets measured as a whole with one Spectre run (session "Gator baseline deletion in RL networks") |
| `47f43cf` | 10-05 19:21 | 7.205 | up to eight Training charts at once (session "Training tab with live graphs") |
| `e5cbcb9` | 10-05 19:21 | 7.204 | "Calibration ready": a line under the header when a Baseline simulation has ended, with Apply calibration and Not now (session "RL reward design") |
| `dba040c` | 10-05 19:22 | - | record only: names the commits of records 7.199-7.201 and 7.203-7.205, and the table rows for dfef323, f97bc6e, aa5e3f9, d711528, 47f43cf and e5cbcb9 |
| `d817f9a` | 10-05 21:02 | 7.209 | the RGCN and GATv2 starting presets on Spectre: first passing design 218 / 289 (Graph Transformer preset 202), last third 88 / 93 % passing; docs only (session "Reward module scoring design") |
| `38defd1` | 10-05 21:02 | - | record only: names the commit of record 7.209, and the table rows for dba040c and d817f9a |
| `1dd5079` | 10-05 21:11 | 7.207 | Check now says when another real run holds Virtuoso (the holder named from /proc/locks, no lock taken) instead of advising Save task (session "Run adapter working copy sync issue", committed by "Virtuoso read whole flow") |
| `349bae4` | 10-05 21:12 | - | record only: names the commit of record 7.207, and the table rows for 38defd1 and 1dd5079 |
| `fd82665` | 10-05 21:15 | 7.210 | the short-budget warning gives the starting presets' learning point (about 150 to 300 evaluations) beside 250 to 600 for the values before them; the threshold stays 300 |
| `61f1ea4` | 10-05 21:16 | - | record only: names the commit of record 7.210, and the table rows for 349bae4 and fd82665 |
| `fb65f76` | 10-05 21:27 | 7.214 | the Calibration of a run of another task than the page holds shows that run's own Scales ("Scale in the run") and Initial alpha, never the page's Specs rows of the same ID (an LDO's pm_deg had stood as an OTA's "Scale now"); Apply says which task it waits for. Page only (session "OTA7 calibration panel spec misses") |
| `9e40a1b` | 10-05 21:28 | - | record only: names the commit of record 7.214, and the table rows for 61f1ea4 and fb65f76 |
| `53ae0f9` | 10-05 21:37 | 7.208 | one way of writing a quantity: the number, an SI prefix and the unit in English letters (1.205 um, 400 uA, 9.535 kohm, 60 deg) in the editors, the read-only views and the backend's messages; any typed form read, another quantity refused in words; no Unit column in Parameters and Specs (a row's quantity from its parameter kind or its Probe), the Probes' Unit a list |
| `7dfd997` | 10-05 21:44 | - | record only: names the commit of record 7.208, and the table rows for 9e40a1b and 53ae0f9 |
| `8d90167` | 10-05 21:46 | - | record only: the Live line of record 7.214, and the table row for 7dfd997 |
| `7df7728` | 10-05 21:59 | 7.212 | choosing a registered task shows its newest run in the bottom tabs, or none (session "Task-run linking in frontend") |
| `c928f9d` | 10-05 21:59 | 7.213 | learner charts by evaluation, units in the chart titles, the day's Spectre runs in the Training tab (session "Training tab with live graphs") |
| `d34573c` | 10-05 22:13 | 7.215 | key numbers per run in the Training tab; "Can continue" checks that a save point exists (session "Training tab with live graphs") |
| `223cca9` | 10-05 22:14 | - | record only: names the commits of records 7.212, 7.213 and 7.215, the Live line of 7.212, and the table rows for 8d90167, 7df7728, c928f9d and d34573c |
| `372c8da` | 10-05 23:00 | 7.218 | fewer boxes inside boxes: a callout inside a panel, the header or a window drawn by a rule at its left without a frame, only a status keeping its faint fill, no rule for a callout inside a callout; 3 nested boxes on the page -> 1 (a field) |
| `7bafccd` | 10-05 23:01 | - | record only: names the commit of record 7.218, and the table rows for 223cca9 and 372c8da |
| `4258714` | 10-05 23:21 | 7.211 | calibration on Spectre did not help on mscr_ota7t (Graph Transformer starting preset, two seeds per arm); a Baseline simulation on the six other MScR tasks; docs only (session "Single baseline simulation merge", committed by "Virtuoso read whole flow") |
| `c170802` | 10-05 23:21 | - | record only: names the commit of record 7.211, and the table rows for 7bafccd and 4258714 |
| `962731e` | 10-05 23:50 | 7.217 | calibration: "Apply and save" for a task saved from a cell, Scales written as quantities, a narrower window rule, no Initial alpha near the one in use (session "RL reward design", committed by "Virtuoso read whole flow") |
| `3ce9717` | 10-05 23:51 | - | record only: names the commit of record 7.217, 7.215's Live lines, and the table rows for c170802 and 962731e |
| `96d2225` | 10-06 02:26 | 7.216 | one setting on every MScR circuit: the Graph Transformer starting preset learns on three of seven on Spectre, not on two LDOs that miss one PSRR row; a new VCO task learns; docs only (session "Gator baseline deletion in RL networks", committed by "Virtuoso read whole flow") |
| `98e0a99` | 10-06 02:27 | - | record only: names the commit of record 7.216, 7.217's Live line, and the table rows for 3ce9717 and 96d2225 |
| `36ed2af` | 10-06 03:11 | 7.219, 7.220 | performance plans: the 13 proposals reviewed for functionality, and the lower/moderate-risk handoff; docs only (session "Project audit", committed by "Virtuoso read whole flow") |
| `2825305` | 10-06 03:11 | 7.222 | rows not saved in the task highlighted in Parameters, Probes and Specs (session "Parameters, specs, and probes linking in Virtuoso") |
| `510ba0e` | 10-06 03:11 | 7.221 | optimizer: lent replay samples, no next-state work at discount 0, input-cache keys worked out once; digest f83342bc -> 4aebbfab (session "Time consumption analysis") |
| `a39bc5b` | 10-06 03:11 | 7.221 | workbench part of the six speed items: replay call sites, shared chart work, cheaper training reads, "Can continue" for older sources, timing rules (session "Time consumption analysis") |
| `105465f` | 10-06 03:18 | 7.223 | switching task no longer asks to discard edits nobody made; its fixed version (session "Unsaved changes blocking task switch") |
| `9b6f30e` | 10-06 03:19 | - | record only: names the commits of records 7.219-7.223, 7.221's digest and Live line, and the table rows for 98e0a99, 36ed2af, 2825305, 510ba0e, a39bc5b and 105465f |
| `5560c01` | 10-06 04:02 | - | record only: 7.221's backend Live line (8765 restarted at 04:00), and the table row for 9b6f30e |
| `71f95c3` | 10-06 08:32 | 7.226, 7.224 | the Agent tab minimal: Claude Code or Codex in a terminal window of its own, What's missing? in a window; the tab's own agent and the LLM search methods removed, SAC the only search method; optimizer digest 4aebbfab -> aafdd71d (search/ and ActionMapper.encode out) (session "Agent tab minimal redesign"); with 7.224's row and entry, which it superseded (session "LLM 1/8 banner meaning") |
| `0a07f87` | 10-06 08:32 | 7.225 | saved RL models get names of their own, numbered when a name is taken, and Rename (session "Random seed explanation") |
| `dc1a9fd` | 10-06 08:32 | 7.227 | the Project column's task as text + a Tasks... window; six start-B tasks; the fine-tuning comparison plan (session "Task button and fine-tuning comparison plan") |
| `40d1249` | 10-06 08:32 | 7.228 | GraphGPS and parameter-group cross-attention in the optimizer, settings, run modes, checkpoints, model inspection and frontend; optimizer digest aafdd71d -> 0b0808bc (the user's Codex session) |
| `e384014` | 10-06 08:34 | - | record only: names the commits of records 7.224-7.228, the two optimizer digests they set, and the table rows for 5560c01, 71f95c3, 0a07f87, dc1a9fd and 40d1249 |
| `57a191c` | 10-06 12:49 | - | the user's original workbench specification of 2026-09-20 (`gator_claude_code_fable51_frontend_data_outputs_en.md`), added as is at the root on the user's "Commit it as is" |
| `3a95417` | 10-06 12:57 | 7.229 | the fine-tuning comparison's twelve runs: the loaded model ahead early on all six circuits, the fixed rule's bar met on three; docs only (session "Task button and fine-tuning comparison plan") |
| `2cba8c6` | 10-06 12:57 | - | record only: names the commit of record 7.229, and the table rows for e384014, 57a191c and 3a95417 |
| `cbf56a3` | 10-06 13:32 | 7.230 | plan: one general network from all saved experience, the six circuits from a third start, and policy drift; plan only, docs only (session "Task button and fine-tuning comparison plan") |
| `c317e18` | 10-06 13:33 | - | record only: names the commit of record 7.230, and the table rows for 2cba8c6 and cbf56a3 |
| `6a4f6ee` | 10-06 14:15 | 7.231 | encoder libraries graphgps and xatten: the six circuits as twelve new tasks for the two new encoders; twelve runs prepared, none started; docs only (session "GraphGPS and XAtten encoder tasks") |
| `de3f995` | 10-07 06:41 | 7.232 | the general-network plan rewritten: arm O on ota5t only, a held-out two-stage op-amp instead of leave-one-out; docs only (session "Task button and fine-tuning comparison plan") |
| `bee0bae` | 10-07 06:41 | 7.233-7.244 | the general-network experiment: offline pretraining, qualification and publication, source rehearsal in fine-tuning, the experiment's records (14,556 + 1,388 Spectre launches), the encoder A/B/C runbook (the user's Codex session) |
| `edf2de7` | 10-07 06:41 | 7.243, 7.245-7.251 | a new task runs its own baseline, Calibration only random designs, Save as with numbered names, task folders, names without real:, no DUT box, the preset learning-rate upgrade (the user's Codex session) |
| `8b2d29e` | 10-07 06:42 | - | record only: names the commits of records 7.231-7.251, and the table rows for c317e18, 6a4f6ee, de3f995, bee0bae and edf2de7 |
| `ea5cd17` | 10-07 07:05 | 7.252, 7.254 | plans: the frontend task-model and run-workflow plan and its revision around one Manager window; docs only (the user's Codex session) |
| `de810e3` | 10-07 07:05 | 7.253 | the Agent window: the "Agent..." tab opens Claude Code or Codex in a window of its own, no tab view (session "Agent tab minimal redesign") |
| `c0a50ed` | 10-07 07:05 | 7.255 | four browser checks follow the interface changes of 7.245, 7.248 and 7.249; test code only (session "Virtuoso read whole flow") |
| `b534719` | 10-07 07:05 | - | record only: names the commits of records 7.252-7.255, and the table rows for 8b2d29e, ea5cd17, de810e3 and c0a50ed |
| `900fcec` | 10-07 07:13 | 7.256 | plan: the other encoders on the six circuits, the comparison plan revised around the A/B/C runbook; docs only (session "Encoder run plan revision") |
| `bc2f7d1` | 10-07 07:13 | - | record only: names the commit of record 7.256 (900fcec), and the table rows for b534719 and 900fcec |
| `2ca0ef4` | 10-07 07:16 | 7.257 | plan: the frontend workflow without the Manager - Tasks, Runs and RL model windows with categories, relationships and model history; the Mode inside the RL model window (New model from a template, Fine-tune / Evaluate only from a pinned save point) |
| `2704ed5` | 10-07 07:17 | - | record only: names the commit of record 7.257 (2ca0ef4), and the table rows for bc2f7d1 and 2ca0ef4 |
| `094aa70` | 10-07 07:33 | 7.258 | plan: Load run - loading a run brings its task, its model and its results onto the page, as one Undo step; nothing built |
| `08f0b22` | 10-07 07:33 | - | record only: names the commit of record 7.258, and the table rows for 2704ed5 and 094aa70 |
| `13223d8` | 10-07 07:36 | 7.256 | revision 2: stage D, the held-out test on the folded cascode only; OTA8m does not count; docs only (session "Encoder run plan revision") |
| `1cc461d` | 10-07 07:36 | - | record only: names the commit of record 7.256's revision 2 (13223d8), and the table rows for 08f0b22 and 13223d8 |
| `9243300` | 10-07 07:53 | 7.259 | plan: the run brief - the header's run chip opens a small pop-up with a brief of every live run; nothing built |
| `3e47161` | 10-07 07:54 | - | record only: names the commit of record 7.259, and the table rows for 1cc461d and 9243300 |
| `6fa7d6b` | 10-07 08:41 | 7.260 | the task name is the button that opens the Tasks window; Delete task inside it; the load icon removed (the user's Codex session) |
| `85dcfa7` | 10-07 08:42 | - | record only: names the commit of record 7.260, and the table rows for 3e47161 and 6fa7d6b |
| `d845cf9` | 10-07 08:53 | 7.261 | frontend plan build step 1: one launcher for Start, Calibration, Resume and Continue, request ids answered once, the continuation check, the budget form, Let go, adoption notices (session "Frontend workbench layout design") |
| `87b74c8` | 10-07 08:54 | - | record only: names the commit of record 7.261, and the table rows for 85dcfa7 and d845cf9 |
| `b12c3be` | 10-07 09:10 | 7.263 | frontend plan build step 2: folders for runs and saved models, stored like the task folders, one folder sidebar (session "Frontend workbench layout design") |
| `143505f` | 10-07 09:10 | - | record only: names the commit of record 7.263, and the table rows for 87b74c8 and b12c3be |
| `f4fc5f2` | 10-07 09:37 | 7.264 | frontend plan build step 3: relationships between runs and models, links between the windows, the run brief (session "Frontend workbench layout design") |
| `e067135` | 10-07 09:37 | - | record only: names the commit of record 7.264 (f4fc5f2), and the table rows for 143505f and f4fc5f2 |
| `0437262` | 10-07 10:18 | 7.256 | plan 7.256 revision 3: the telescopic cascode joins stage D as the second held-out circuit; docs only, nothing started (session "Encoder run plan revision") |
| `853077e` | 10-07 10:19 | - | record only: names the commit of record 7.256's revision 3, and the table rows for e067135 and 0437262 (session "Encoder run plan revision") |
| `cacfc9d` | 10-07 11:02 | 7.265 | frontend plan build step 4: the RL model window - the Mode in the load-model window, a New model template per encoder, a pinned save point (session "Frontend workbench layout design") |
| `7740467` | 10-07 11:02 | - | record only: names the commit of record 7.265 (cacfc9d), and the table rows for 853077e and cacfc9d |
| `a18903d` | 10-07 11:25 | 7.268 | Astra's review of 2026-10-07 fixed: launch answer before the worker starts, failed lookups keep the launch id, failed status reads keep "checking", half-written records pending, checkpoint pruning by save time, the CLI test's PATH, the skill's five encoders, the record file rolled over to 7.119-7.265.md / 7.266-and-later.md; new launch_recovery_check (session "Launch recovery and checkpoint retention bugs") |
| `deffde4` | 10-07 11:26 | - | record only: names the commit of record 7.268 (a18903d), and the table rows for 7740467 and a18903d (session "Launch recovery and checkpoint retention bugs") |
| `0ff74d3` | 10-07 12:07 | 7.267 | frontend plan build step 5: Load run, Show results, Continue... and New run like this in the Runs window; one way to take a saved model; a draft that still says resume has no Mode (session "Frontend workbench layout design") |
| `7579406` | 10-07 12:07 | - | record only: names the commit of record 7.267 (0ff74d3), and the table rows for deffde4 and 0ff74d3 (session "Frontend workbench layout design") |
| `f993a98` | 10-07 12:09 | - | record only: the Live line of record 7.268 (backend restarted and the page built at 11:58), and the table row for 7579406 (session "Launch recovery and checkpoint retention bugs") |
| `acffe49` | 10-07 13:43 | 7.271 | Astra's follow-up on 7.268: the continue's run lock let go of on a failed launch record write; the record before the spawn is "launching" - the run once its worker is there, pending until then, let go of once stale with no worker (session "Launch recovery and checkpoint retention bugs") |
| `e341fcd` | 10-07 13:45 | - | record only: names the commit of record 7.271 (acffe49), and the table rows for f993a98 and acffe49 (session "Launch recovery and checkpoint retention bugs") |
| `74d6e6e` | 10-07 13:53 | 7.271 | addendum: at the backend's start a launch request left on its way is let go of at once unless its worker is there (launch_requests.reconcile in create_app) (session "Launch recovery and checkpoint retention bugs") |
| `558dbec` | 10-07 13:53 | - | record only: names the addendum commit of record 7.271 (74d6e6e), and the table rows for e341fcd and 74d6e6e |
| `8751d21` | 10-07 14:18 | 7.262 | held-out circuits built for the purpose (folded cascode; telescopic cascode from the Analog Design Bench, CC BY-NC), the equal-recipe arms on the six C tasks, OTA8m retired; docs only (session "Task button and fine-tuning comparison plan") |
| `543eb04` | 10-07 14:18 | - | record only: names the commit of record 7.262, and the table rows for 558dbec and 8751d21 |
| `7df2579` | 10-07 21:34 | 7.266 | plan: the general model over several starting designs and seeds, against scratch; docs only (session "Task button and fine-tuning comparison plan") |
| `9bcaecf` | 10-07 21:34 | - | record only: names the commit of record 7.266, and the table rows for 543eb04 and 7df2579 |
| `0b85fd4` | 10-07 21:39 | 7.269, 7.270 | the header's Next line; Load run stops on an unreadable model and only the newest load lands (session "Frontend workbench layout design") |
| `5c261bf` | 10-07 21:39 | - | record only: names the commit of records 7.269 and 7.270, and the table rows for 9bcaecf and 0b85fd4 |
| `6016bbd` | 10-07 21:49 | 7.272 | report of the Graph Transformer experiments of 2026-10-07; docs only (session "Task button and fine-tuning comparison plan") |
| `616c153` | 10-08 08:14 | 7.274-7.276 | the audit of 2026-10-07: faster run-list and saved-model reads, fewer page reads and redraws, shared table code and clean-up; with 7.269/7.270's Live lines (session "Frontend workbench layout design") |
| `dd52d67` | 10-08 08:15 | 7.273 | plan 7.256 revision 4: the lean encoder comparison started overnight; docs only (session "Encoder run plan revision") |
| `98bec37` | 10-08 08:15 | - | record only: names the commits of records 7.272, 7.273 and 7.274-7.276, and the table rows for 5c261bf, 6016bbd, 616c153 and dd52d67 |
| `81250f7` | 10-08 10:49 | - | record only: the Live lines of records 7.274-7.276, and the table row for 98bec37 |
| `0da08fe` | 10-08 13:24 | 7.277 | encoder comparison stage A complete; with 7.273's missing index row; docs only (session "Encoder run plan revision") |
| `af45f1c` | 10-08 13:24 | - | record only: names the commit of record 7.277, and the table rows for 81250f7 and 0da08fe |
| `eb8eb1c` | 10-08 13:39 | 7.278 | Astra's review of 7.274-7.276: the run-list cache under a lock, only the newest "Use this save point" lands, the compatibility check keeps the page configuration's contract (session "Concurrent cache and stale selection bugs") |
| `5c49b66` | 10-08 13:39 | - | record only: names the commit of record 7.278, and the table rows for af45f1c and eb8eb1c |
| `2e44685` | 10-08 15:05 | 7.279-7.282 | the audit of 2026-10-08: the same answers faster, run speed-ups with identical results, learning after the dispatch (a switch, off by default), the simulator host's job folders removed as a run goes; the record rolled over to `7.279-and-later.md`, with record 7.278's Live line (session "Frontend workbench layout design") |
| `85af5cc` | 10-08 15:14 | - | record only: names the commit of records 7.279-7.282 and their Live lines, and the table rows for 5c49b66 and 2e44685 (session "Frontend workbench layout design") |
| `9059528` | 10-08 15:59 | - | docs: the GT report's section 9, the other encoders through the same stages (no record entry) |
| `3b9dafa` | 10-08 16:01 | - | record only: the table rows for 85af5cc and 9059528, and two stale "uncommitted" marks of 7.221 dropped |
| `774d2f3` | 10-08 16:23 | 7.283 | Astra's review of 7.279-7.282: deferred learner-update rows kept, PDK model-file copies per host, the storage-limit deletion remembers the host folder (session "Concurrent cache and stale selection bugs") |
| `1f64a2b` | 10-08 16:23 | - | record only: names the commit of record 7.283 (774d2f3), and the table rows for 3b9dafa and 774d2f3 |
| `cf842b1` | 10-08 17:47 | - | docs: the GT report's section 10, the time to the first passing design, and section 9's encoder tables with the same column; the two report pages republished (session "Time to first feasible design", no record entry) |
| `5356b3f` | 10-08 17:47 | - | record only: the table rows for 1f64a2b and cf842b1 (the GT report's section 10) |
| `72f0145` | 10-08 17:49 | - | record only: the Live line of record 7.283 (8765 restarted at 16:48) (session "Concurrent cache and stale selection bugs") |
| `d4091ab` | 10-08 17:51 | - | record only: the table rows for 5356b3f and 72f0145 |
| `bba4486` | 10-08 23:08 | 7.284 | save points written compressed, losslessly (each zip entry byte-identical, read by torch.load as before), and `compress-save-points` for the older ones (628 compressed, 26.56 -> 8.89 GB); with the third audit's findings (session "Frontend workbench layout design") |
| `aa132c1` | 10-08 23:15 | - | record only: names the commit of record 7.284 and its Live line, and the table rows for d4091ab and bba4486 (session "Frontend workbench layout design") |
| `ff2a13f` | 10-09 04:00 | 7.285 | encoder comparison stage C complete: the three general models transfer alike; docs only (session "Encoder run plan revision") |
| `4323753` | 10-09 04:00 | - | record only: names the commit of record 7.285, and the table rows for aa132c1 and ff2a13f |
| `ae20306` | 10-09 05:32 | 7.288 | encoder comparison stage D complete: the two held-out cascodes; docs only (session "Encoder run plan revision") |
| `8bfb034` | 10-09 05:33 | - | record only: names the commit of record 7.288, and the table rows for 4323753 and ae20306 |
| `b79198e` | 10-09 05:40 | 7.286 | Astra's review of 7.284: the compression pass refreshes the artifact manifest once per run, the Data tab reads only the shown columns (session "Compression integrity and manifest issues") |
| `099defa` | 10-09 05:40 | 7.287 | plan: refactoring - the same behaviour, a structure that is easier to change; docs only (session "Refactoring plan") |
| `40d5f4b` | 10-09 05:41 | - | record only: names the commits of records 7.286 and 7.287, and the table rows for 8bfb034, b79198e and 099defa |
| `e18b9a9` | 10-09 11:08 | 7.289 | the encoder comparison closed: stage E and the study's verdict; docs only (session "Encoder run plan revision") |
| `564928e` | 10-09 11:08 | - | record only: names the commit of record 7.289, and the table rows for 40d5f4b and e18b9a9 |
| `7410f6f` | 10-09 11:26 | 7.290 | A4: RunLock to run_lock.py, the run definitions to run_definitions.py (the first of the refactoring's 48 commits, session "Refactoring plan") |
| `23337ee` | 10-09 11:26 | 7.290 | A4: blank lines |
| `9e71bb0` | 10-09 11:26 | 7.290 | A2: task_baseline.py into the api package |
| `6703448` | 10-09 11:26 | 7.290 | A3: the routes modules' register() split into per-concern functions |
| `b433faa` | 10-09 11:26 | 7.290 | A5: cli.main as _parser() and one function per subcommand |
| `e807add` | 10-09 11:26 | 7.290 | B1 step 2: task_registry.py - the registered tasks' facts out of tasks.py |
| `0eda4ee` | 10-09 11:26 | 7.290 | B1 steps 3-6: profile_store, saved_rows, settings_store, run_index, checkpoint_codec |
| `687831d` | 10-09 11:26 | 7.290 | A1: honest imports - 136 in-function imports moved to the top of their modules |
| `0ca4834` | 10-09 11:26 | 7.290 | B1 step 8 + D6: test_wb_structure.py, the package's structure rules as tests |
| `4a9f3e9` | 10-09 11:26 | 7.290 | B2: engine.py by job - three mixins, _commit 228 -> 158 lines |
| `00b0b1e` | 10-09 11:26 | 7.290 | B3 part 1: profiles.py by job, layered without cycles |
| `26ee4fc` | 10-09 11:26 | 7.290 | B3 part 2: save_task 191 -> 121 lines; A1 completed |
| `9ec81e5` | 10-09 11:26 | 7.290 | B4: pdk.py by job, layered, in five modules |
| `5ca670a` | 10-09 11:26 | 7.290 | B5: runs.py by job; prepare_run 159 -> 95 lines |
| `a16dd72` | 10-09 11:26 | 7.290 | B6: long functions split along their own steps |
| `717fa35` | 10-09 11:26 | 7.290 | B7: route bodies become named functions of their modules |
| `0350683` | 10-09 11:26 | 7.290 | B8: one helper per repeated pattern, every message unchanged |
| `44aa1ee` | 10-09 11:27 | 7.290 | B9: public names and shared constants |
| `1533b86` | 10-09 11:27 | 7.290 | B10: every process-lifetime cache joins caches.py |
| `65c2f4a` | 10-09 11:27 | 7.290 | dom_identity_check: the page's DOM and request log, for refactorings (plan 4.7) |
| `ae42979` | 10-09 11:27 | 7.290 | C1: runState.ts - the run states, their rules and useRunControl out of RunControl.tsx |
| `476a23a` | 10-09 11:27 | 7.290 | C2: contract.ts - the names the page and its checks share |
| `bad1a25` | 10-09 11:27 | 7.290 | C3: store.ts by concern, and one signal() for the four hand-made stores |
| `9a6770b` | 10-09 11:27 | 7.290 | C4 step 1: the right column's fields, OutputPanel and ResearchPanel out of Right.tsx |
| `1a1c907` | 10-09 11:27 | 7.290 | C4 step 2: the RL model window out of RunPanelBody |
| `8a851e0` | 10-09 11:27 | 7.290 | C6: Editors.tsx by part |
| `093c30f` | 10-09 11:27 | 7.290 | C8: the formatters in format.ts, the SI prefix tables in units.ts |
| `5ab45ef` | 10-09 11:27 | 7.290 | C10: the Training tab's two read loops as one useTrainingReads; api.ts keeps only requests |
| `4037e5b` | 10-09 11:27 | 7.290 | C7: shared primitives that draw today's DOM - Blocked, PopupPortal, useNewest, kept.ts |
| `de6a681` | 10-09 11:27 | 7.290 | C5 step 1: BottomPanel.tsx - the bottom panel out of Page |
| `8c7f159` | 10-09 11:27 | 7.290 | C5 step 2: useCalibrationOffer out of Page |
| `d6bf5ea` | 10-09 11:27 | 7.290 | C5 step 3: useRunWindowActions out of Page |
| `3824deb` | 10-09 11:27 | 7.290 | C5 step 4: useLaunchActions out of Page, into launch.ts beside useLauncher |
| `abf744a` | 10-09 11:27 | 7.290 | C5 step 5: useRunList and useShownRun out of Page |
| `9f4ef4b` | 10-09 11:27 | 7.290 | C5 step 6: useLiveRunAdoption out of Page |
| `3a920ae` | 10-09 11:27 | 7.290 | C5 step 7: useTaskRunFollow out of Page |
| `f75a921` | 10-09 11:27 | 7.290 | C9: Left.tsx by job |
| `3672e85` | 10-09 11:27 | 7.290 | D5: check-script library - one ending for every check, durations from the runs |
| `eb06dd6` | 10-09 11:27 | 7.290 | C12: trainingData.ts in parts - training/{store,series,prep,catalog,build,compare,keys}.ts behind it |
| `9a59f00` | 10-09 11:27 | 7.290 | docs: the frontend's new files in the functionality reference and in Code organization |
| `014b062` | 10-09 11:27 | 7.290 | D1: shared test helpers - no test module is a library any more |
| `97175d5` | 10-09 11:27 | 7.290 | D2: test modules named after the feature - the ten round-named modules are gone |
| `fc75596` | 10-09 11:27 | 7.290 | D3: markers where they do work |
| `3d48a55` | 10-09 11:27 | 7.290 | D4: big test modules by concern; every moved test keeps the fixtures it ran with |
| `000a212` | 10-09 11:27 | 7.290 | Docs: the refactoring in the docs - record 7.290, Code organization, the reference's code and test cells |
| `e76d057` | 10-09 11:27 | 7.290 | Record 7.290: the browser checks against the refactored backend and page together |
| `2b79f78` | 10-09 11:27 | 7.290 | Docs: the refactoring plan's row in the plans table - executed (7.290), not landed |
| `ef1cc42` | 10-09 11:27 | 7.290 | the refactoring landed: the landed-state texts of record 7.290, its index row, the plan and the reference; the 47 above are the clean copy's commits replayed on 564928e (session "Refactoring plan") |
| `7614718` | 10-09 11:48 | - | record only: record 7.290's Commit and Live lines, and the table rows for 564928e and the landing commits 7410f6f..ef1cc42 (session "Refactoring plan") |
| `088584d` | 10-09 16:02 | 7.289 | record only: 7.289 amended - the two `_a` LDO tasks and their four MScR cells deleted on the user's word; and the table row for 7614718 |
| `0be5b18` | 10-09 18:56 | 7.291 | the Tasks, Runs and RL model windows close once a task, run or saved model is chosen (a choice that does not go through leaves them open); the record file rolled over to `7.291-and-later.md` (session "Frontend workbench layout design") |
| `1f5382d` | 10-09 18:57 | - | record only: names the commit of record 7.291 (0be5b18) and its Live line, and the table rows for 088584d and 0be5b18 (session "Frontend workbench layout design") |
| `28202f7` | 10-09 18:59 | 7.292 | Tests: the two-lane learner-switch test compares the runs through their transitions (the first of the refactoring follow-up's 23 commits, session "Refactoring plan") |
| `5307a3b` | 10-09 18:59 | 7.292 | Workbench: the Training tab says why a Baseline simulation or a Calibration run has no learner charts |
| `dd5f3b2` | 10-09 18:59 | 7.292 | Docs: the reference's Run engine row names the update functions that exist |
| `ce1cd8e` | 10-09 18:59 | 7.292 | Tests: the OTA measurement reader opamp.analyze gets its first test |
| `cd64e2e` | 10-09 18:59 | 7.292 | Checks: run_checks.sh chooses its scratch backends' ports outside the ranges Windows reserves |
| `4089688` | 10-09 18:59 | 7.292 | Checks: run_checks.mjs keeps Vite's cache in the temp folder, one per checkout |
| `8c6d2d7` | 10-09 18:59 | 7.292 | Checks: run_checks makes the two saved MOCK models encoder_models_check reads, so it runs in every batch |
| `2025d91` | 10-09 18:59 | 7.292 | Optimizer E9: the three measurement readers share one reading of a Spectre job folder |
| `5becc4d` | 10-09 18:59 | 7.292 | Optimizer E6: the bridge adapter's generic helpers in modules of their own, still exported by virtuoso_bridge |
| `eadf02f` | 10-09 18:59 | 7.292 | Optimizer E7: one bridge-binding check for the adapter and its lane backend; one preparation session for both owners |
| `13dd913` | 10-09 18:59 | 7.292 | Optimizer E8: the local backends share their connection and held parameters; each digest says what it hashes |
| `c316f82` | 10-09 18:59 | 7.292 | Optimizer E10: SpectreParser.parse_text along its three phases |
| `dd6f554` | 10-09 18:59 | 7.292 | Optimizer E10: SpecificationEvaluator.evaluate_conditions along its five phases |
| `1d436d8` | 10-09 18:59 | 7.292 | Optimizer E10: RunReader.overview and export along their steps |
| `7d90954` | 10-09 18:59 | 7.292 | Optimizer E10: summarize_corners along its three steps |
| `b9b2b63` | 10-09 18:59 | 7.292 | Optimizer E5: the recording store by concern |
| `c3965e4` | 10-09 18:59 | 7.292 | Optimizer E3: one random proposal and one timed update for every collector of training data |
| `237522d` | 10-09 18:59 | 7.292 | Optimizer E4: the long orchestration functions name their phases |
| `6a91673` | 10-09 18:59 | 7.292 | Optimizer E1: CircuitSizingEnv._evaluate as the sequence it is |
| `980d86b` | 10-09 18:59 | 7.292 | Optimizer E2: public environment operations for the workbench's continue, calibration and retry |
| `7317923` | 10-09 18:59 | 7.292 | C11: proof tools for regrouping styles.css (css_order_proof.mjs, dom_identity_check --styles) |
| `ad47d17` | 10-09 18:59 | 7.292 | C11: styles.css regrouped where the cascade allows, restated selectors merged |
| `4d2eff0` | 10-09 18:59 | 7.292 | Docs: record 7.292 - the refactoring's follow-up: the small fixes, the optimizer's clean-up (group E) and styles.css (C11) |
| `f3e0dfd` | 10-09 19:24 | - | record only: names the commits of record 7.292 and its Live line (session "Refactoring plan") |
| `764fd63` | 10-09 19:48 | 7.293 | encoder study follow-ups: the cross-attention VCO rerun, the additions plan draft; a 7.289 amendment; docs only (session "Encoder run plan revision") |
| `5d34318` | 10-09 19:48 | - | record only: names the commit of record 7.293 (764fd63) and adds the table rows for f3e0dfd and 764fd63 |
| `44881d8` | 10-09 22:03 | 7.294 | audit of 2026-10-09: OCEAN's results let go after each measurement (`ocnResetResults()`), the learn-while-simulating switch on by default after its check, a plan for a cheaper check before each write (session "Frontend workbench layout design") |
| `9e7cbf3` | 10-09 22:11 | - | record only: names the commit of record 7.294 (44881d8) and its Live line, corrects "every run recorded before" (runs recorded before 7.281 never stated the switch), table rows for 5d34318 and 44881d8 (session "Frontend workbench layout design") |
| `e7e6907` | 10-09 23:50 | 7.296 | the whole-cell read built once instead of line by line (`schematic_read.read_cell`): the same answer, 434 -> 6 ms inside Virtuoso on mscr_vco_lin_c; landed before the encoder queue's nine runs (session "Frontend workbench layout design") |
| `0803c7f` | 10-10 16:38 | - | docs: three lines of record 7.296 say "the 180 nm process cells" |
| `f538535` | 10-10 17:01 | 7.295 | the AgenticSizing circuits on a second 0.18 um PDK; PDK quirks and conditions from local settings (session "Encoder run plan revision") |
| `19e909a` | 10-10 17:01 | 7.297 | tests/test_parser.py fixture path; no test module imports a conftest (session "Refactoring plan") |
| `7695b7e` | 10-10 17:01 | 7.298 | transferable network inputs: specs as a set, device families; digest 8f100145 (session "Agentic sizing agent circuit runs") |
| `b231eb3` | 10-10 17:01 | 7.299 | a missing value of a hard spec is a failed row; digest 94e7dd4f (session "Encoder run plan revision") |
| `70bed2d` | 10-10 17:01 | 7.300 | the AgenticSizing circuits rebuilt from published netlists; a computed field written through its typed twin (session "Agenticsizing encoder restart and LDO comparison") |
| `fe3028a` | 10-10 19:43 | 7.301 | plan only: the transfer experiment (networks with the new inputs, SAC against Bayesian optimization, new targets, a second PDK, one general model on unseen circuits); the record file rolled over to `7.301-and-later.md` (session "Encoder experiment plan setup") |
| `29ce8ad` | 10-10 19:43 | 7.302 | a task can be renamed: the name it is shown under; its key, files, cell, runs and models unchanged (session "Encoder experiment plan setup") |
| `56b2efc` | 10-10 17:01 | - | record only: names the commits of records 7.295 and 7.297-7.300, and the table rows for 0803c7f and the chain |
| `714b6a1` | 10-10 19:43 | - | record only: names the commits of records 7.301 and 7.302, and their table rows |
| `52b9bc6` | 10-11 20:21 | 7.303-7.316 | the transfer experiment's steps 1 and 2 with first readings; Bayesian optimization (TuRBO-1); a run binds its own copy of the bridge's settings file; a Probe that measures the sizes; the netlist comparison reads numbers (optimizer digest 94e7dd4f -> 6724e52b); a lock per Virtuoso session and per cell; offline re-scoring under several target sets; Maestro helpers removed; OCEAN closes its result folder (sessions "Encoder experiment plan setup" and "Trained model spec change topology proof") |
| `da1504a` | 10-11 20:21 | - | record only: names the commit of records 7.303-7.316, and the table rows for 56b2efc, 714b6a1 and 52b9bc6 |
| `1dfeae4` | 10-12 00:05 | 7.317 | a second build of the network inputs: bench sources on their own scales, net tags by one rule, operating-point ratios; offline pools take them; the transfer plan's step 3b (session "Circuit training and SAC RL graph transformer", committed by the session "Model continuation and input fingerprint bugs" beneath its own records) |
| `7bfa48b` | 10-12 00:05 | 7.319 | four review findings: Continue asks for a run's view with its own component list; an offline pool pins what each source was shown; a published model keeps its component list; test variables keep their case (session "Model continuation and input fingerprint bugs") |
| `4222238` | 10-12 00:05 | 7.322 | five more review findings: a run continued after a crash counts what it committed after its save point; one ngspice net per node name; a relabelled copy keeps a stated scale; New run like this takes the run's optimizer; a late Delete task answer leaves a newer choice alone (session "Model continuation and input fingerprint bugs"; no browser check run) |
| `7c12d1b` | 10-12 00:05 | - | record only: names the commits of records 7.317, 7.319 and 7.322, and the table rows for da1504a and the three commits |
| `75f6dda` | 10-12 17:03 | 7.318, 7.320, 7.321, 7.323-7.332 | the transfer experiment's steps 3 to 6 and the port history; audit fixes and a refactor (model-input contracts, engine phases, ngspice helpers); CircuitGPS in the optimizer package (digest 6724e52b -> e29b39e1) with its import guards; a new model's network inputs come with its encoder's template (sessions "Encoder experiment plan setup", "Circuit training and SAC RL graph transformer", Codex "Project audit" and "Build the new encoder") |
| `cfdffaa` | 10-12 17:05 | - | record only: names the commit of records 7.318, 7.320, 7.321 and 7.323-7.332 in their entries |
| `7ae9e60` | 10-12 17:04 | - | record only: the table rows for 7c12d1b, 75f6dda and cfdffaa; five index rows name their commit |
| `0b0778d` | 10-12 17:51 | 7.333 | a starting size the optimizer's grid does not hold is named before a task is saved or a run is tried; workbench only (session "Encoder experiment plan setup") |
| `73c121a` | 10-12 17:52 | - | record only: names the commit of record 7.333, and the table rows for 7ae9e60 and 0b0778d |
| `42eac2e` | 10-12 19:42 | 7.334, 7.335 | the published reference and system read by their reward, a correction in 7.330; the transfer experiment's full step 1 comparison, 7.313's tables and the plan's results replaced; docs only (session "Encoder experiment plan setup") |
| `a01cca0` | 10-12 19:44 | - | record only: names the commit of records 7.334 and 7.335, corrects two statements of its message, and the table rows for 73c121a and 42eac2e |
| `b80b08b` | 10-15 02:51 | 7.336-7.352 | Round 3 archive training (GraphGPS, CircuitGPS), CircuitGPS v2 and its CPU speed-up (optimizer digest e29b39e1 -> ba551575), two Virtuoso sessions under one connection and the work sent to whichever is free, Round 2 runs, the reading guide, review fixes (the user's Codex session; session "check codex work") |
| `f8ff5ce` | 10-15 02:51 | - | record only: names the commit of records 7.336-7.352, and the table rows for a01cca0 and b80b08b |
| `9d87ccb` | 10-17 01:21 | 7.353-7.359 | Round 3 seed 0 with an RGCN arm and its session-2 recovery; Step 1's GATv2 arm; CircuitGPS version 3, opt-in (optimizer digest ba551575 -> 6ebf5ba5), its offline training and its Round 3 arms; the log rolled over (sessions "check codex work" and "Weekly experiments summary") |
| `d0938bc` | 10-17 01:22 | - | record only: names the commit of records 7.353-7.359, and the table rows for f8ff5ce and 9d87ccb |
| `342b77a` | 10-17 02:28 | 7.356, 7.357 | the index rows of the two CircuitGPS version 3 records, written from their entries (their session had ended) |
| `dd6398a` | 10-17 02:38 | 7.360 | the Roadster look: dark only, red, white and black, Draft A built into the workbench (session "Frontend workbench layout design") |
| `72f8a1d` | 10-17 02:38 | - | record only: names the commit of record 7.360, and the table rows for d0938bc, 342b77a and dd6398a |
| `5edbd37` | 10-17 05:21 | 7.361 | the Roadster look made live (page published, 8765 restarted 02:35, bringing 7.351/7.352 live); the connection pill keeps its state word (session "Frontend workbench layout design") |
| `ccd1d3f` | 10-17 05:21 | - | record only: names the commit of record 7.361, the table rows for 72f8a1d and 5edbd37, and d0938bc's time corrected |
| `705d43d` | 10-17 13:46 | 7.362 | the task's card: the task across the left and the centre, the circuit on request - the user's Option D (session "Frontend workbench layout design") |
| `8b67d97` | 10-17 13:47 | - | record only: names the commit of record 7.362, and the table rows for ccd1d3f and 705d43d |
| `a481619` | 10-19 05:08 | 7.372, 7.376, 7.380 | nine page changes; the page's words name its buttons (Save as, not "Save task"); 8765 live again after the PC restarted (session "Frontend workbench layout design") |
| `8d43a00` | 10-19 05:09 | - | record only: names the commit of records 7.372, 7.376 and 7.380, and the table rows for 8b67d97 and a481619 |
| `c6f172c` | 10-19 16:49 | 7.363, 7.381, 7.383 | Round 4 offline: the plan (section 7b) and its results - LOADBench does not help the Round 3 models, option 1 neither (session "Training encoders with Zenodo dataset") |
| `a5d3c5c` | 10-19 16:49 | - | record only: names the commit of records 7.363, 7.381 and 7.383, and the table rows for 8d43a00 and c6f172c |
| `f6a989e` | 10-19 19:50 | 7.382 | TuRBO against transfer-learned SAC on three tasks (a trained model wins only near its training; TuRBO wins on the amplifier); TuRBO's memory growth fixed with malloc_trim after each proposal |
| `c2177fa` | 10-19 19:59 | - | record only: names the commit of record 7.382, and the table rows for a5d3c5c and f6a989e |
| `f87b8ce` | 10-20 13:20 | 7.384 | TuRBO and transfer-learned SAC combined: neither a TuRBO-data model nor a TuRBO warm start helps; three seeds on every row (session "Zenodo dataset encoder performance") |
| `d6f6d81` | 10-20 13:21 | - | record only: names the commit of record 7.384, and the table rows for c2177fa and f87b8ce |
| `9f761f7` | 10-20 14:10 | 7.364-7.371, 7.373-7.375, 7.377-7.379 | less work for the same results: streamed CSVs, projected and bounded reads, leaner inventories and ZIP exports, repeated parsing and sorting removed; the log rolled over twice (the user's Codex session) |
| `694d9a1` | 10-20 14:10 | - | record only: names the commit of Codex's records 7.364-7.379, and the table rows for d6f6d81 and 9f761f7 |
| `286deaf` | 10-23 11:45 | 7.385, 7.388 | Round 3 seeds 1 and 2: the seed-0 matrix twice more, 72 real runs, two same-run resumes (7.385); all 72 complete, audited with seed 0, feasible designs per arm for seeds 0/1/2 (7.388) (session "Training encoders with Zenodo dataset") |
| `ec2e163` | 10-23 11:45 | - | record only: names the commit of records 7.385 and 7.388, and the table rows for 694d9a1 and 286deaf |
| `5e25dd7` | 10-23 11:47 | 7.386, 7.387 | plan for Claude: matched-archive comparison of TuRBO transfer, Pareto MOBO and SAC (docs/plan-bo-mobo-rl-archive-comparison.md, transfer-plan section 16), refined from the random-forest calibration chat (Codex's records, committed on the user's word by the session "Training encoders with Zenodo dataset") |
| `8c04206` | 10-23 11:48 | - | record only: names the commit of records 7.386 and 7.387, and the table rows for ec2e163 and 5e25dd7 |
| `2b0f47b` | 10-24 15:15 | 7.434 | archive comparison steps 2-6 (branch `bo-mobo-rl`): goal views, `turbo_archive`/`mobo` searches in the engine with exact save/continue and crash re-tell, pretrain pool settings, the goal-view rule of a comparison run; frozen runtime gator-runtime-bmr-f143d691 (session "Training encoders with Zenodo dataset") |
| `d9d5ba0` | 10-24 15:16 | - | plan only: the transfer experiment's journal track is dropped (user, 2026-10-23: "I am not publishing") - the status table's Journal row and sections 14-15 say J0-J5 and the manuscript milestones will not be run, kept for reference |
| `e4d295c` | 10-24 15:19 | 7.389 | a run that stops while it is being prepared, before its save points are opened, skips its final save: the original error alone, the summary's `output.note` says why, a crash test of the unresolved-launch refusal; the log rolled over (session "Skip the final save when a run never prepared") |
| `da05b8b` | 10-26 12:58 | 7.436 | Merge completed readability packages into latest integration |
| `7ef598b` | 10-26 13:00 | 7.436 | Merge archive comparison implementation and preserve its development record |
| `5a38798` | 10-26 13:00 | 7.436 | Preserve codex/readability-before-refresh-2026-10-26 history; equivalent changes already integrated |
| `e513bc0` | 10-26 13:00 | 7.436 | Preserve sif-backend-words-2 history; equivalent changes already integrated |
| `de54083` | 10-26 13:00 | 7.436 | Preserve sif-help-text history; equivalent changes already integrated |
| `9192e9b` | 10-26 13:14 | 7.436 | Integrate pending work and remove the frontend Agent interface |
| `8694d05` | 10-26 13:48 | 7.437 | T2-BO: document archive-comparison test helpers |
| `871213a` | 10-26 14:04 | 7.437 | P1-06: document api/models.py |
| `68d934d` | 10-26 14:08 | 7.437 | P1-07: document api/run_routes.py |
| `4ada3b2` | 10-26 14:12 | 7.437 | P1-08: document api/settings_routes.py |
| `3066e96` | 10-26 14:16 | 7.437 | P1-09: document Task API operations |
| `f16ec90` | 10-26 14:20 | 7.437 | P1-10: document bayes.py |
| `d9cc6e3` | 10-26 14:24 | 7.437 | P1-11: document best_design.py |
| `7a55fd7` | 10-26 14:28 | 7.437 | P1-12: document bridge_connect.py |
| `4f7d6f6` | 10-26 14:32 | 7.437 | P1-13: document bridge_setup.py |
| `1b8e302` | 10-26 14:35 | 7.437 | P1-14: document budget.py |
| `9a1da30` | 10-26 14:39 | 7.437 | P1-15: document caches.py |
| `afeb28b` | 10-26 14:43 | 7.437 | P1-16: document CDF preparation ownership |
| `9edf91c` | 10-26 14:46 | 7.437 | P1-17: document cdf_facts.py |
| `87e355a` | 10-26 14:50 | 7.437 | P1-18: document cdf_text.py |
| `d70d0b9` | 10-26 14:54 | 7.437 | P1-19: document cdf_write.py |
| `78fd7b9` | 10-26 14:58 | 7.437 | P1-20: document checkpoints.py |
| `71c050b` | 10-26 15:02 | 7.437 | P1-21: document Native circuit import |
| `2d427f8` | 10-26 15:07 | 7.437 | P1-22: document compile.py |
| `e0d1da2` | 10-26 15:11 | 7.437 | P1-23: document connection.py |
| `ecaa255` | 10-26 15:15 | 7.437 | P1-24: document Task readiness evidence |
| `c8cb99e` | 10-26 15:19 | 7.437 | P1-25: document corner_check.py |
| `2e4e7f2` | 10-26 15:22 | 7.437 | P1-26: document deck_ops.py |
| `0d059a6` | 10-26 15:27 | 7.437 | P1-27: document device_models.py |
| `b5adea9` | 10-26 16:45 | 7.437 | P1-28: document diffs.py |
| `3016b88` | 10-26 16:49 | 7.437 | P1-29: document Remembered directories |
| `d4e3677` | 10-26 16:54 | 7.437 | P1-30: document engine.py |
| `41ca01f` | 10-26 16:59 | 7.437 | P1-31: document engine_commit.py |
| `a0d835b` | 10-26 17:04 | 7.437 | P1-32: document Run preparation and finalization |
| `acb5d0b` | 10-26 18:25 | 7.437 | P1-33: document experiments.py |
| `1051fa4` | 10-26 18:28 | 7.437 | P1-34: document Device vocabularies |
| `2804e5b` | 10-26 18:33 | 7.437 | P1-35: document generic_profile.py |
| `4bd5702` | 10-26 18:36 | 7.437 | P1-36: document graph_view.py |
| `acb5cae` | 10-26 18:41 | 7.437 | P1-37: document lanes.py |
| `cac1cca` | 10-27 00:06 | 7.437 | P1-38: document layout.py |
| `538a373` | 10-27 00:11 | 7.437 | P1-39: document model_library.py |
| `efdbed5` | 10-27 00:15 | 7.437 | P1-40: document model_scan.py |
| `ffbd9af` | 10-27 00:20 | 7.437 | P1-41: document model_structure.py |
| `3e50e19` | 10-27 00:25 | 7.437 | P1-42: document modes.py |
| `d75a139` | 10-27 11:57 | 7.437 | P1-43: document network_inputs.py |
| `cfffb64` | 10-27 12:02 | 7.437 | P1-44: document network_presets.py |
| `55fc985` | 10-27 12:07 | 7.437 | P1-45: document ngspice instrumentation |
| `73243e5` | 10-27 16:32 | 7.437 | P1-46: document ngspice_backend.py |
| `facaeb0` | 10-27 16:37 | 7.437 | P1-47: document ngspice_link.py |
| `e2dc80d` | 10-27 17:35 | 7.437 | P1-48: document ngspice_netlist.py |
| `a27ce84` | 10-27 18:19 | 7.437 | P1-49: document ngspice_syntax.py |
| `6e85da9` | 10-27 18:27 | 7.437 | P1-50: document ngspice_tasks.py |
| `60a97de` | 10-27 18:35 | 7.437 | P1-51: document ocean.py |
| `9883c72` | 10-27 18:43 | 7.437 | P1-52: document Offline replay support |
| `e1a9cca` | 10-27 18:51 | 7.437 | P1-53: document paths.py |
| `ba5f235` | 10-27 18:59 | 7.437 | P1-54: document pdk_record.py |
| `066d815` | 10-27 19:08 | 7.437 | P1-55: document pdk_remote.py |
| `78698ca` | 10-27 19:16 | 7.437 | P1-56: document pretrain.py |
| `025ba19` | 10-27 19:23 | 7.437 | P1-57: document Saved-task documents |
| `31409f1` | 10-27 23:27 | 7.437 | P1-58: document psf_binary.py |
| `0edbb43` | 10-27 23:35 | 7.437 | P1-59: document recipes.py |
| `a8e5c57` | 10-27 23:46 | 7.437 | P1-60: document Run ownership |
| `bdef87c` | 10-28 06:56 | 7.437 | P1-61: document runs.py |
| `fe02dd1` | 10-28 07:05 | 7.437 | P1-62: document saved_rows.py |
| `d5260c0` | 10-28 09:04 | 7.437 | P1-63: document schema.py |
| `de0b5ab` | 10-28 09:43 | 7.437 | P1-64: document security.py |
| `3d8be8b` | 10-28 10:35 | 7.437 | P1-65: document session_routing.py |
| `6b33bb3` | 10-28 10:42 | 7.437 | P1-66: document simulation_artifacts.py |
| `e2d7ee3` | 10-28 10:49 | 7.437 | P1-67: document spec_descriptors.py |
| `ffc1148` | 10-28 11:35 | 7.437 | P1-68: document spec_equations.py |
| `48a10e8` | 10-28 11:42 | 7.437 | P1-69: document spec_programs.py |
| `6363e80` | 10-28 11:50 | 7.437 | P1-70: document storage/atomic.py |
| `5442531` | 10-28 11:58 | 7.437 | P1-71: document storage/dataset.py |
| `ef38073` | 10-28 12:09 | 7.437 | P1-72: document storage/tables.py |
| `ad639a9` | 10-28 12:17 | 7.437 | P1-73: document structures.py |
| `858c085` | 10-28 13:02 | 7.437 | P1-74: document Task organization |
| `ae07dcd` | 10-28 13:11 | 7.437 | P1-75: document task_registry.py |
| `cdac340` | 10-28 13:18 | 7.437 | P1-76: document tasks.py |
| `522849d` | 10-28 13:28 | 7.437 | P1-77: document trajectory.py |
| `5495a9a` | 10-28 13:35 | 7.437 | P1-78: document units.py |
| `ad8aa6a` | 10-28 13:44 | 7.437 | P1-79: document validation.py |
| `3c0fded` | 10-28 13:52 | 7.437 | P1-80: document virtuoso_setup.py |
| `71d547f` | 10-28 14:03 | 7.437 | P1-81: document worker.py |
| `9fab5a2` | 10-28 14:13 | 7.437 | P1-82: document working_copy.py |
| `8089170` | 10-28 14:25 | 7.437 | P1-83: document archive_compare/views.py |
| `a02a1b7` | 10-28 15:02 | 7.437 | P1-84: document archive_compare/mobo.py |
| `e175ccb` | 10-28 15:13 | 7.437 | P1-85: document archive_compare/turbo_archive.py |
| `575a1a1` | 10-28 15:30 | 7.437 | P1-86: document archive_compare/contract.py |
| `443722a` | 10-28 15:44 | 7.437 | P1-87: document archive_compare/coords.py |
| `3765be0` | 10-28 15:58 | 7.437 | P1-88: document archive_compare/runtime.py |
| `42786e5` | 10-28 17:28 | 7.437 | P2-parse-text-outer: extract reviewed named steps |
| `0a17074` | 10-28 17:48 | 7.437 | P2-engine-commit: extract reviewed named steps |
| `916b1dd` | 10-28 17:56 | 7.437 | P2-pretrain-prepare-pool: extract reviewed named steps |
| `c4bce98` | 10-28 18:02 | 7.437 | P2-ngspice-expand: extract reviewed named steps |
| `5f0997a` | 10-28 18:11 | 7.437 | P2-connection-run-layers: extract reviewed named steps |
| `fb74811` | 10-28 18:33 | 7.437 | P2-ngspice-link-run-layers: extract reviewed named steps |
| `9e2cf72` | 10-28 18:42 | 7.437 | P2-virtuoso-task-routes: extract reviewed named steps |
| `00bf473` | 10-28 18:54 | 7.437 | P2-run-list-model-routes: extract reviewed named steps |
| `0a03dd3` | 10-28 19:27 | 7.437 | P2-task-routes: extract reviewed named steps |
| `8131552` | 10-28 21:07 | 7.437 | TF-commit-json-test: follow the live commit step into its module in a structural test |
| `0b347b2` | 10-28 21:18 | 7.437 | P2-task-save: extract reviewed named steps |
| `be23e36` | 10-28 21:28 | 7.437 | P2-engine-preparation: extract reviewed named steps |
| `f7a32a1` | 10-28 21:38 | 7.437 | P2-structures-recognize: extract reviewed named steps |
| `4516bc9` | 10-28 21:47 | 7.437 | P2-profile-generate: extract reviewed named steps |
| `bbb1606` | 10-28 22:01 | 7.437 | P2-pretrain-execute: extract reviewed named steps |
| `00c3ea5` | 10-28 22:11 | 7.437 | P2-cdf-rules: extract reviewed named steps |
| `411d2bc` | 10-28 22:35 | 7.437 | P2-runs-prepare-run: extract reviewed named steps |
| `08126cf` | 10-29 01:00 | 7.437 | P2-modes-build: extract reviewed named steps |
| `fa935f0` | 10-29 01:42 | 7.437 | P2-graph-view: extract reviewed named steps |
| `2e13a00` | 10-29 01:55 | 7.437 | P2-pdk-record: extract reviewed named steps |
| `95144b1` | 10-29 02:07 | 7.437 | P2-validation-network-inputs: extract reviewed named steps |
| `20903f1` | 10-29 02:18 | 7.437 | P2-checkpoints-save: extract reviewed named steps |
| `b44d618` | 10-29 02:29 | 7.437 | P2-schema-hashed: extract reviewed named steps |
| `5d950fc` | 10-29 02:38 | 7.437 | P2-cdf-write: extract reviewed named steps |
| `10e4e29` | 10-29 02:45 | 7.437 | P2-summary-build: extract reviewed named steps |
| `de1b9fe` | 10-29 02:55 | 7.437 | P2-bridge-read-main: extract reviewed named steps |
| `8f0cd93` | 10-29 03:01 | 7.437 | P2-start-run: extract reviewed named steps |
| `5c4e1af` | 10-29 03:07 | 7.437 | P2-model-classify: extract reviewed named steps |
| `830da7e` | 10-29 03:14 | 7.437 | P3-calibration-scale: simplify reviewed nested control flow |
| `00b3d78` | 10-29 03:20 | 7.437 | P3-probe-facts: simplify reviewed nested control flow |
| `a9c76ab` | 10-29 03:25 | 7.437 | P3-model-structure: simplify reviewed nested control flow |
| `12994d2` | 10-29 03:31 | 7.437 | P3-ngspice-result: simplify reviewed nested control flow |
| `9dbf1cb` | 10-29 03:37 | 7.437 | P3-measurement-checks: simplify reviewed nested control flow |
| `28687ea` | 10-29 03:43 | 7.437 | P3-export-cells: simplify reviewed nested control flow |
| `ae07b99` | 10-29 03:48 | 7.437 | P3-token-scanner: simplify reviewed nested control flow |
| `5adec8d` | 10-29 03:54 | 7.437 | P3-directory-bytes: simplify reviewed nested control flow |
| `aaab8c9` | 10-29 04:00 | 7.437 | P4-engine-preparation: clarify private local names |
| `d1ab080` | 10-29 04:06 | 7.437 | P4-schema: clarify private local names |
| `84c0098` | 10-29 04:12 | 7.437 | P4-cdf-write: clarify private local names |
| `d0f3561` | 10-29 04:18 | 7.437 | P4-consistency: clarify private local names |
| `777d787` | 10-29 04:23 | 7.437 | P4-pdk-remote: clarify private local names |
| `4548bf9` | 10-29 04:30 | 7.437 | P4-bridge-setup: clarify private local names |
| `63a3f1b` | 10-29 04:36 | 7.437 | P4-cell-hold: clarify private local names |
| `eef5a5c` | 10-29 04:42 | 7.437 | P4-lanes: clarify private local names |
| `4685d75` | 10-29 04:50 | 7.437 | P4-psf-binary: clarify private local names |
| `33fff8d` | 10-29 04:56 | 7.437 | P4-spec-programs: clarify private local names |
| `a4d5f16` | 10-29 05:02 | 7.437 | P4-training-series: clarify private local names |
| `a722733` | 10-29 05:34 | 7.437 | P4-validation: clarify private local names |
| `917307d` | 10-29 05:42 | 7.437 | P4-working-copy: clarify private local names |
| `952ab6b` | 10-29 05:49 | 7.437 | P5-signature-hints: add reviewed signature type hints |
| `d6b19d3` | 10-29 05:58 | 7.437 | P6-comments-constants: explain steps and name repeated constants |
| `7d3f628` | 10-29 06:06 | 7.437 | P7-line-wrapping: wrap previously edited source to 120 columns |
| `acab2cc` | 10-29 06:16 | 7.437 | P1R-docstring-revision: revise P1 docstrings after review |
| `216f7a1` | 10-29 06:23 | 7.437 | P8-paths: name the values that steps share |
| `89b13ca` | 10-29 12:05 | 7.437 | P8-ngspice-backend: name the values that steps share |
| `b20f32a` | 10-29 12:11 | 7.437 | P8-ngspice-netlist: name the values that steps share |
| `f921d41` | 10-29 12:17 | 7.437 | P8-structures: name the values that steps share |
| `b9c6515` | 10-29 12:23 | 7.437 | P8-task-save: name the values that steps share |
| `febae89` | 10-29 12:29 | 7.437 | P8-graph-view: name the values that steps share |
| `679555c` | 10-29 12:35 | 7.437 | P8-runs: name the values that steps share |
| `d948a81` | 10-29 12:40 | 7.437 | P8-profile-generate: name the values that steps share |
| `8dac847` | 10-29 12:46 | 7.437 | P8-modes: name the values that steps share |
| `c2003d8` | 10-29 12:52 | 7.437 | P8-pretrain: name the values that steps share |
| `99022ca` | 10-29 12:58 | 7.437 | P8-engine-commit: name the values that steps share |
| `27f30d9` | 10-29 13:06 | 7.437 | P8-engine-rows: name the values that steps share |
| `7c6cfe2` | 10-29 13:12 | 7.437 | P8-runs-resume: name the values that steps share |
| `2a6dd42` | 10-29 13:50 | 7.437 | P8-start-directory: name the values that steps share |
| `c3775ba` | 10-29 13:56 | 7.437 | P8-model-scan: name the values that steps share |
| `f8dd00f` | 10-29 14:01 | 7.437 | P8-cdf-rules: name the values that steps share |
| `88133e0` | 10-29 14:42 | 7.390-7.433 | Records 7.390-7.433 as written in the live checkout: the readability plan, Codex's seed-0 campaign and M0, and the log rollovers |
| `0e6802f` | 10-29 16:00 | 7.438 | Land codex/latest on workbench: the readability plan, the Agent-window removal and the archive-comparison steps (record 7.438) |
| `22c1a69` | 10-29 16:04 | 7.438 | Record: workbench fast-forwarded to the landing merge 0e6802f (record 7.438), and its table row |
| `6288fbc` | 10-29 16:29 | 7.439 | Model scan: a subcircuit that places itself stops at the nesting limit (record 7.439) |
| `7bd2115` | 10-29 15:35 | 7.441 | Add local NVIDIA Agent with verified lifecycle and undoable proposals |
| `d5a2126` | 10-29 15:43 | 7.442 | Integrate verified local Bolt 74B profile on 74B-latest |
| `199bb93` | 10-29 15:39 | 7.441 | Record local Agent implementation commit |
| `64ff8f1` | 10-29 15:43 | 7.442 | Record verified 74B profile commit |
| `3f88952` | 10-29 16:34 | 7.440 | Record 7.440: live again (page built, 8765 restarted), workbench pushed, merged old branches deleted |
| `048905b` | 10-29 17:20 | 7.443 | Land Codex's local Agent (74B-latest) on workbench (record 7.443) |
| `e150d3c` | 10-30 17:53 | 7.445 | Separate private thesis repository and record authorized history purge |
| `f07d391` | 10-30 17:54 | 7.445 | Record thesis separation commit |
| `87e2ce2` | 10-30 21:28 | - | Plans of 2026-10-30, written before any seed-1/2 or reverse-port run (Amendment A2, transfer plan Section 17, follow-up plan) |
| `ebbe3a8` | 10-30 21:35 | 7.446, 7.447 | Shared graph/search primitives and typed editor operations (Codex's work, committed on codex/reduce-duplication) |
| `7444c04` | 10-30 21:39 | 7.446, 7.447 | Merge codex/reduce-duplication into workbench |
| `e571e6b` | 10-30 21:39 | 7.448 | Record 7.448: Codex's reduce-duplication work merged into workbench |
| `89e2106` | 10-30 23:01 | 7.449 | Amendment A1's M0 code on workbench, as it ran (record 7.449) |
| `3a9380f` | 10-31 00:52 | 7.450, 7.451 | After a crash only an M0 search reads the event log (record 7.451); record 7.450 (seeds 1-2 launch) |
| `2903f0a` | 11-02 03:36 | 7.452 | The M+ search gives each proposal's memory back to the system (record 7.452) |
| `4a2af53` | 11-02 04:46 | 7.453 | Archive comparison seeds 1-2 complete: 102 searches, 144 confirmations, three-seed decision (record 7.453) |
| `22744f6` | 11-02 09:00 | 7.454 | Reverse port complete: 12 runs, independent check, thesis revision 26 (record 7.454) |
| `adcff22` | 11-02 15:45 | 7.455 | GitHub tidy-up: main level with workbench, merged Codex branch deleted on GitHub (record 7.455) |
| `d563e24` | 11-02 16:53 | 7.456 | Pre-registrations of 2026-11-02, written before any run: the next held-out circuit for RQ5 (not run) and Amendment A3, the rehearsal arm |
| `14ddd1b` | 11-02 18:23 | 7.456 | Amendment A3 revision 2, before any RA+R evaluation: the first queue's three zero-cost stops and runtime gator-runtime-bmr-429e3df7 |
| `e778bda` | 11-04 04:18 | 7.457 | Load optional workbench panels on demand |
| `262db32` | 11-04 04:20 | 7.458 | Compact frontend controls and release temporary Agent output |
