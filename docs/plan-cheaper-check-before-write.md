# Plan: the check before each write, kept and made cheaper (2026-10-09, records 7.294 and 7.296)

The user asked for this plan after the fourth audit of 2026-10-09 ("Write a plan"), then said "go on" and allowed its
first step in Virtuoso ("Yes, run it now"). It does not reopen the decision of 2026-10-02 to keep the check ("Keep the
check", `docs/plan-measurement-off-virtuoso.md`, "Other options"). **Status: P0 done; it changed the plan.** The check
stays exactly as it is, and the read it is made of became cheap (record 7.296). What is left is a trial on the simulator
(P2) and the user's decision to land it (P3).

## What the check is

Each candidate's preparation (`VirtuosoBridgeBackend.set_parameters`, `analog_optimizer/backends/virtuoso_bridge.py`)
runs in the one Virtuoso session that every lane shares, one candidate at a time:
1. **reads the whole cell before the write** and checks it (`_verify_restored(before, self._current)`, which the
   workbench's `CdfBridgeBackend` defines as `validate_readback` against the task's reference plus `compare_written`:
   every field of every written instance as in the last read-back);
2. writes the candidate's values with one form write (`CdfBridgeBackend._write_widths`, record 7.66);
3. **reads the whole cell again** and checks it (`verify_transition`: `validate_readback` against the task's reference,
   the written values, and derived geometry that changed with a width);
4. builds the netlist from that read-back (record 7.142; Virtuoso's own export every 5th candidate, compared).

## What P0 found (2026-10-09, read-only, 50 rounds per cell)

**The first version of this plan was wrong twice:**
- **The narrower read does not make the read cheaper.** The bridge's `param_filters` is applied in Python, after Virtuoso
  has produced every value.
- **A narrow read would also weaken the check.** On these cells every instance is written: 34 of 34 on
  `mscr_vco_lin_c`, 6 of 6 on `mscr_ota5t`. Step 1's `compare_written` is where a hand edit of a written instance's other
  fields is caught at once, for example its transistor model, `sa` or `sdMtlWidth`. Step 3 compares only the modes and
  held fields with the task's reference, so it does not catch those edits. The earlier sentence "a hand edit of any other
  value still shows up at step 3" was not true.

What the read's time actually is: inside Virtuoso (SKILL `measureTime`), against the read the adapter makes (W):

| Read | `mscr_vco_lin_c` (34 instances, 1,092 values, 30 kB) | `mscr_ota5t` (6 instances, 204 values, 6 kB) |
|---|---|---|
| W: the bridge's read program, its answer grown with `strcat` | 434 ms (client 498 ms) | 1.3 ms (client 15.5 ms) |
| F: the same program, its answer collected in a list and joined once | 5.7 ms (client 70 ms) | 1.1 ms (client 15.7 ms) |
| P: F's parameters only (no positions, terms, nets, pins, notes) | 4.1 ms (client 60 ms) | 0.8 ms (client 12.9 ms) |
| H: only the fields the write sets again (written + held) | 0.7 ms (client 9.5 ms) | 0.2 ms (client 4.0 ms) |
| C: the floor, cdfGetInstCDF and each value's text, nothing kept | 3.9 ms (client 6.4 ms) | 0.8 ms (client 2.9 ms) |

- In every round F's text was the same as W's, character for character. P's and H's values were the same as the read's.
- 99 % of the read was `strcat` copying the growing answer for every line, which grows with the square of the answer.
- At the client, what is left is mostly the answer's transfer, about 2 ms per kB.
- Script and numbers: `artifacts/local/reviews/check-before-write-2026-10-09/` (`p0_reads.py`, `p0.json`).

## What was built instead (record 7.296)

**F, the same read built once** (`gator_workbench/schematic_read.py`, `read_cell`):
- It is the bridge's own program with every `result = strcat(result X)` made `tconc(out X)` and the answer joined once.
  The text is the same by construction, and the bridge's own parser reads it.
- It is used for every read of the run adapter (`CdfBridgeBackend._read_snapshot`): before and after each write, at
  connect, after an export and at restoration. Save task's fingerprints and the cell import use it too.
- Every check stays as it was: nothing is read less.
- A bridge whose program is not the measured one reads with its own call.
- Checked live, read-only: equal to `client.schematic.read` on both cells, with and without positions (12 of 12).

Expected per evaluation on `mscr_vco_lin_c`: two reads at about 0.07 s instead of about 0.5 s, so about 0.85 s less
preparation in the one Virtuoso session. At 6 lanes this session had started to bind (queue wait 0.46 s). The foundry cells
of record 7.295 gain most: `asz_sys`, a ~100 kB answer, is estimated at 4-5 s per read before.

## Steps left

- **P2, trial (a simulation budget, the user's go):** `mscr_vco_lin_c`, 200 evaluations, 6 lanes, seed 2, with the
  change, against `lanes-vco_lin_c-s2-6lanes` of 2026-10-09 (the same settings, 8.0 min, preparation 2.26 s per
  evaluation). Measure preparation, queue wait and wall time. Best on a quiet Virtuoso: another run in the session
  slows the preparation of both.
- **P3, the user's decision:** land it (commit, page unchanged, 8765 restart; run workers import the live code).
