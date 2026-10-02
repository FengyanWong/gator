# Plan: Maestro measurements off the Virtuoso session (2026-10-02, record 7.148)

The user asked to "go on" after records 7.136-7.145 were pushed (`bb1aadb`). Record 7.148.

**Outcome:** built (G1), tried on Spectre (G2): identical values, but no faster, because the preparation and not the
measurement limits a run. Removed at the user's decision ("Remove it", 2026-10-02); the code is no longer in the
tree. This file keeps what was measured, in case a task with heavier measurements ever needs it.

## Why

At 6 lanes the one Virtuoso session is the limit (7.145): its SKILL interpreter takes, one at a time,
- the preparation of every candidate: reads, form write, a native export every 5th; about 0.3 s on `mscr_ota7t`;
- the OCEAN measurement of every candidate of a Maestro task (every MScR task): about 0.1-0.15 s each, sent by the lanes
  (`ocean.measure`, one SKILL program per candidate: `openResults` on the run's folder, then each output expression).

Measured on `mscr_ota7t` at 6 lanes: 0.41 s per evaluation, the preparation thread busy 79% (part of it waiting behind
the lanes' measurements).

## Idea

Each lane keeps its own OCEAN process on the simulator host and sends it the same SKILL program it now sends to
Virtuoso. The program is pure OCEAN, its signal names already translated at Save task (`ocean.Names`), and the result
folder stays on the host. Then only the preparation uses the Virtuoso session.

- Executable: `/opt/cadence/IC231/tools/dfII/bin/ocean`, a 592-byte wrapper, started with `-nograph` under the bridge's
  Cadence set-up (`csh -fc 'source $VB_CADENCE_CSHRC; ...'`), over ssh with the bridge's options (as built: a
  connection of its own per lane, not the bridge's shared one).
- One process per lane for the whole run. Each program is followed by a sentinel line, so the lane knows where the answer
  ends. A dead or hung process is restarted once, then the run stops in words.
- Values: the same program in another OCEAN interpreter. As with the built netlists (7.142), every 5th candidate is also
  measured in the Virtuoso session, and a difference stops the run.

## Expected gain

The measurement leaves the session's queue, so `mscr_ota7t` at 6 lanes should go from 0.41 s towards the preparation
floor, about 0.3 s per evaluation. `mscr_vco_lin` gains little: its transient jobs and its large-cell reads dominate.

## Unknowns, to settle first

1. **Licence.** Whether `ocean -nograph` needs a licence feature of its own, and whether 6 can run beside the Virtuoso
   session. The licence server is not queried directly (CLAUDE.md); starting one process answers it.
2. **Start-up time** of one OCEAN process (paid once per lane per run).
3. **Memory**: the session's Virtuoso uses about 1.7 GB; the host has about 8 GB free.

## G0 result (2026-10-02, the user's "Yes, start one")

`ocean -nograph -replay`, run under the bridge's Cadence set-up:
- It starts and evaluates: a replay wrote `GATOR_RESULT=2` for `1+1`.
- It exits 0 and took 5.3-7.5 s with about 480 MB peak, so six would take about 2.9 GB of the host's 8 GB free.
- No licence error for one process.
- Its log needs `-log <file>`: the session's Virtuoso holds `~/CDS.log`.

Whether six can run at once beside Virtuoso shows only in G2.

## G1 result (2026-10-02, offline, plus OCEAN starts without simulation)

Protocol, measured on the host first (five OCEAN starts in all, no simulation, no cell write, the Virtuoso session not
used):
- Over a pipe, `ocean -nograph` answers on its standard output, after a `> ` prompt, and echoes no input. Each request
  is the measurement program under `errset`, its answer printed between two markers carrying a random tag.
- OCEAN keeps running at the end of its input. A TERM starts Cadence's crash reporter (`cdsPstack`, gdb on the process),
  so the host script ends it with `exit()` and, after a grace time, kills what is left of its process session. One
  probe left an OCEAN tree (about 660 MB) running when its input was closed without `exit()`; it was removed by hand.
- The first measurement takes 1.3-3.6 s (OCEAN loads its results reader), each later one about 0.03-0.05 s.

Built (`gator_workbench/ocean.py`, workbench code only, off by default):
- `host_script`: the one-line bash program run on the host. OCEAN runs in a fresh folder and its own session, reading a
  named pipe the script fills with the lane's input. When that input ends, after 15 minutes without any, or when the
  connection drops, the script sends `exit()`, waits up to 10 s, kills the session's leftovers and removes the folder.
  The lane hears at once when OCEAN ends.
- `worker_argv`: ssh with the bridge's own options for the Spectre host (key, config, jump host) but a connection of its
  own, under the Cadence set-up the bridge sources for Spectre.
- `OceanWorker`: one process, one request at a time, a timeout of 120 s per answer.
- `LaneMeasurer`, chosen by `GATOR_OCEAN_MEASURE` (`session` by default, `worker`, `check`). The lane's first candidate
  is measured in Virtuoso while its OCEAN starts in the background; that OCEAN's first answer is the same candidate
  again, compared. Then every 5th candidate (every one in `check`) is measured both ways. A difference, or a folder
  only Virtuoso can read, stops the lane: every later evaluation fails as an infrastructure failure, so the run pauses
  after its limit of those. A lost OCEAN is replaced once.
- `recipes.GenericMaestroProfile.analyze` now calls `ocean.measure_lane` and records who measured (`measured_by` in
  `measurements.json`).
- Tests: `tests/workbench/test_wb_ocean_worker.py` with a stand-in OCEAN (`fake_ocean.py`) that keeps running at the
  end of its input like the real one; the host script runs under bash on this machine.

Checked on the host as a run would start it (two lane OCEANs at once, the 12 result folders that 7.143's 6-lane trials
left there):
- both started in 4.1 s, side by side;
- 12 of 12 folders measured to exactly the values the Virtuoso session recorded during the trials;
- first request 1.3 s, later ones 0.03 s;
- one closed normally (2.1 s), the other's local ssh killed: within 2 s the host had no OCEAN, no script, no message
  server and no folder left.

## G2 result (2026-10-02, the user's "Yes, 2 tasks, 120 sims"): correct, but no faster

Spectre, 6 lanes, scratch settings, the seed of 7.143's 6-lane runs (which measured in the session only):

| run | evaluations | s/eval, whole run | s/eval once every lane's OCEAN was ready |
|---|---|---|---|
| `mscr_ota7t`, session only (7.143) | 20 | 0.41 | - |
| `mscr_ota7t`, `check` | 20 | 0.90 | - |
| `mscr_ota7t`, `worker` | 40 | 0.64 | 0.39 (from 18.6 s) |
| `mscr_vco_lin`, session only (7.143) | 20 | 1.40 (1.11 from 8 s) | - |
| `mscr_vco_lin`, `check` | 20 | 1.86 | - |
| `mscr_vco_lin`, `worker` | 38 | 1.57 | 1.10 (from 34.3 s) |

- **Values:** every comparison was identical: 25 candidates in the `check` runs, 6 every-5th checks and 12 first answers in
  the `worker` runs. The same design gave the same values to the last digit, a missing `f5_hz` included, whichever OCEAN
  measured it. Every cell equalled its record afterwards, and the host had nothing left after each run.
- The `mscr_vco_lin` `worker` run stopped at 38 evaluations on the run's own rule (5 failed evaluations in a row): designs
  without an `f5_hz` (sometimes `f4_hz`), as in the session-only runs (9-10 of 20 invalid there).
- **Speed:** none gained. Once ready, a lane's OCEAN measured in 0.03 s, but the throughput stayed what it was (0.39 vs
  0.41 and 1.10 vs 1.11 s/eval). Spectre jobs took as long as before (median 1.37 vs 1.50 s and 4.41 vs 4.86 s), and the
  wait for the preparation did not shrink (0.72 vs 0.60 s and 1.78 vs 1.58 s). So the session's measurements were not
  what held the lanes back: 7.145's reading was wrong. The preparation itself, about 0.3 s per candidate one at a time,
  is the limit.
- **Start cost:** six OCEANs starting at once beside six Spectre jobs made those jobs 3-4 times slower for 10-20 s; every
  lane's OCEAN was ready only after 18.6 s (`mscr_ota7t`) and 34.3 s (`mscr_vco_lin`). That made the short runs slower.

## Stages, each with its gate

- **G0 (needs the user's go):** start one `ocean -nograph` on the host, evaluate `1+1`, quit. No simulation, about a
  minute. It answers unknowns 1-3.
- **G1 (offline):** an `OceanWorker` in the workbench beside `ocean.measure` (`gator_workbench/ocean.py`), chosen per lane
  for Maestro tasks. Tests with a fake worker (protocol, restart, sentinel, the every-5th comparison).
- **G2 (needs a simulation budget):** a Spectre trial on two MScR tasks at 6 lanes, comparing every candidate's values
  between the worker and the session (check mode), then speed with the every-5th check.
- **G3 (the user's decision):** on by default for Maestro tasks.

No optimizer file changes: the measurement is workbench code (`recipes.GenericMaestroProfile.analyze` calls
`ocean.measure_lane`, which calls `ocean.measure` in mode `session`).

## Other options (from 7.145), not part of this plan

- Leave out the read before each write: one of three reads, 0.3-0.4 s per candidate on large cells. A hand edit of a
  written value during a run would be overwritten unseen. The user chose to keep the read (2026-10-02, "Keep the
  check").
- A Spectre that stays running between jobs (`+interactive`): little gain while the Virtuoso session is the limit.
