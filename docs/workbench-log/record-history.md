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
