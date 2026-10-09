# Plan: the check before each write, kept and made cheaper (2026-10-09, record 7.294)

The user asked for this plan after the fourth audit of 2026-10-09 ("Write a plan"). Nothing is built until the user
agrees. It does not reopen the decision of 2026-10-02 to keep the check ("Keep the check",
`docs/plan-measurement-off-virtuoso.md`, "Other options"). It keeps the check's protection and makes the check cheaper.

## What the check is

Each candidate's preparation (`VirtuosoBridgeBackend.set_parameters`, `analog_optimizer/backends/virtuoso_bridge.py`)
runs in the one Virtuoso session that every lane shares, one candidate at a time:
1. **reads the whole cell before the write** (`_read_snapshot`: every instance, every parameter, every position), and
   checks it against the read that ended the lane's previous write (`_verify_restored(before, self._current)`);
2. writes the candidate's values with one form write (`CdfBridgeBackend._write_widths`, record 7.66);
3. **reads the whole cell again** and checks that exactly the written values changed
   (`verify_transition(before, after, parameters)`);
4. builds the netlist from that read-back (record 7.142; Virtuoso's own export every 5th candidate, compared).

Step 1 protects one thing that step 3 cannot see: a hand edit, during a run, of a value the lane writes. Step 3 compares
against the cell as it was before this write, so a hand-edited written value would be overwritten unseen. That is why
the check was kept on 2026-10-02. A hand edit of any other value still shows up at step 3 as an unexpected change.

## What it costs (measured 2026-10-09)

Each run's `logs/timings.jsonl` (record 7.280), medians per evaluation, on the fast VM. The read before the write runs
before the adapter's own stopwatch starts, so it shows only as preparation time that no listed stage accounts for.

| Run | Lanes | Preparation | Unaccounted (the read before) | Write + read after | Queue wait |
|---|---|---|---|---|---|
| mscr_ota5t | 4 | 0.36 s | 0.03 s | 0.05 s | 0.08 s |
| mscr_ring3 | 4 | 0.30 s | 0.03 s | - | - |
| mscr_vco_lin_c | 4 | 1.37 s | 0.53 s | 0.55 s | 0.00 s |
| mscr_vco_lin_c | 6 | 2.26 s | - | 0.58 s | 0.46 s (p90 2.55 s) |

On the VCO's large cell each whole-cell read costs about half a second. At 6 lanes the session's queue starts to bind:
6 lanes were 23 % faster than 4, where Spectre alone would allow more.

## The change

Before the write, read **only the values the lane is about to write** - the writable parameters of the writable
instances, with no positions - and compare them with the same values of the previous read-back (`self._current`).
- A hand edit of a written value is refused before the write, as now: the protection kept on 2026-10-02.
- Everything else is still checked after the write: `verify_transition(self._current, after, parameters)`, against
  the last whole read-back. A hand edit of any other value since then shows as an unexpected change, as now.
- The whole read after the write stays: the netlist is built from it (7.142), and it is what step 3 compares.

Where: the workbench's own adapter, `CdfBridgeBackend` in `gator_workbench/cdf_write.py`, which already overrides the
write and the comparison (7.66). It would override `set_parameters` with the narrow read, and nothing in
`analog_optimizer/` changes. The optimizer's source digest stays, so old save points still continue and the M5/M6
evidence is untouched. The bridge's `schematic.read` already takes `param_filters` and `include_positions`.

## Steps

- **P0, measure (needs the user's go: read-only calls in Virtuoso, no simulation):** time the narrow read against the
  whole read on the VCO's and the OTA's cells, 50 times each. Does the narrow read cost about 0.05 s on the VCO? If it
  costs nearly as much, stop here.
- **P1, build (offline):** the override, and tests with a fake bridge:
  - a hand edit of a written value is refused before the write, with the same words as now;
  - a hand edit of another value is refused after it;
  - the read-back, the netlist built from it and the journal are unchanged.
- **P2, trial (a simulation budget):** `mscr_vco_lin_c`, 200 evaluations, 6 lanes, with and without the change: the
  preparation time, the queue wait and the wall time.
- **P3, the user's decision:** keep it or not. Expected, if P0 holds: the VCO's preparation drops from about 1.37 to
  about 0.9 s per evaluation at 4 lanes, and the 6-lane runs gain what the queue now takes. The OTAs gain about 0.03 s.
