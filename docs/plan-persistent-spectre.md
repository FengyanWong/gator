# Plan: a Spectre that stays running in each lane (2026-10-02, record 7.149)

**Outcome:** built (G1), tried on Spectre (G2): not usable for this PDK, because a running Spectre does not follow
changes of `l` or `m`. Removed at the user's decision ("Remove it", 2026-10-03; records 7.149 and 7.152). This file keeps
what was measured.

G0 done (below). The user lifted the optimizer's rule "No ... Spectre runner ... is reimplemented here" for this
("Spectre that stays running", 2026-10-02), asking for a staged plan first, like the OCEAN one
(`docs/plan-measurement-off-virtuoso.md`).

## Why

Measured at 6 lanes on `mscr_ota7t` (7.143's runs, the run tables, Spectre's own log, stack samples):

| part of a lane's cycle | seconds |
|---|---|
| before Spectre starts: the preparation (about 0.3) and its queue | 0.62 |
| the Spectre job | 1.47 |
| - Spectre itself (its log: "Time used ... elapsed = 991 ms") | about 1.0 |
| -- of which reading the netlist and the PDK models ("Time for NDB Parsing") | 0.43 |
| -- of which the analyses (dc, stb) | 0.02 |
| -- of which licensing ("Time spent in licensing") | 0.03 |
| - upload, downloads (the results folder and three log files, each its own transfer) | about 0.25 |
| - the OCEAN measurement | about 0.1 |
| after the job, and handing the lane its next candidate | under 0.1 |

So about 0.9 s of each 1.5 s job is Spectre starting, reading the models and stopping. Every candidate's deck differs
from the last only in parameter values (7.138). A Spectre that keeps its circuit and models loaded could change those
values and run the analyses again.

## Idea

Each lane starts one Spectre for the run, in interactive mode (Spectre 23.1 offers `+interactive`,
`+interactive=skill` and `+interactive=mpsc`, 7.145), with the first candidate's deck. For each next candidate the lane
sends one `alter` per changed instance parameter, taken from the netlist built from the readback (7.142), including the
values the PDK callbacks derive, then runs the analyses again into a results folder the measurement reads.

## Unknowns, to settle first (G0)

1. **Protocol:** how interactive Spectre takes commands over a pipe, how it says an analysis finished, where it writes
   the results of each rerun, and whether `alter` reaches every parameter the decks differ in (`w`, `l`, `m`, `r`,
   `as`/`ad`/`ps`/`pd`, `nrd`/`nrs`, `sca`/`scb`/`scc`).
2. **Values:** whether a rerun after `alter` gives exactly what a fresh Spectre gives on the same deck. A rerun may start
   from the previous operating point; a circuit with more than one (a ring oscillator, a VCO) may then settle
   elsewhere.
3. **Time:** what a rerun costs (the analyses are 0.02 s on `mscr_ota7t`; the rest is bookkeeping).
4. **Licence:** one Spectre licence held per lane for the whole run, six at once beside the user's session.
5. **Where the code goes:** the lane's simulation is the optimizer's `VirtuosoBridgeBackend.run_simulation`, which
   makes a bridge `SpectreSimulator` per job (`_new_simulator`). A lane-held Spectre needs a hook there (a source digest
   step) and the runner itself in the workbench.

## Expected gain (estimate)

`mscr_ota7t`: the job from about 1.5 s to about 0.5 s, a cycle of about 1.2 s instead of 2.2 s. The one-at-a-time
preparation (about 0.3 s per candidate) then sets the pace: about 0.3 s per evaluation instead of 0.41. `mscr_vco_lin`
(5-7 s jobs, its transient analysis 2-4 s): about 15% less per job.

## G0 result (2026-10-02, the user's "Yes, ~10 Spectre starts")

Ten Spectre starts on the simulator host, on a copy of a deck that 7.149's check run kept (`mscr_ota7t`: stb and dc,
8 MOSFETs inside the `DUT` instance), in a temporary folder removed afterwards. No cell write; the Virtuoso session was
not used. Results in Spectre's text format (`-format psfascii`) so that they could be compared.
- **Protocol:** `spectre -64 +interactive=skill <deck>` reads the deck and waits. It answers over a pipe after a `> `
  prompt and echoes no input. `sclHelp()` lists its commands; the ones a lane needs are:
  - `sclGetInstance("DUT.M7")` and `sclGetParameter(inst "w")`, then `sclSetAttribute(param "value" 2.2e-6)`;
  - `sclRun("all")`, and `sclSetResultDir("<folder>")` to name each run's results folder;
  - `sclQuit()`, which ends it cleanly.

  It runs nothing until asked.
- **Time:** a run of both analyses inside the session took 0.047 s, 0.043 s after a width change, and 0.017 s when
  repeated. A fresh Spectre on the same deck took about 2.5 s here (about 1.0 s inside a run's jobs).
- **Values, first run:** identical to a fresh Spectre, byte for byte, in every results file.
- **Values after a change:** the rerun starts its DC solution from the previous candidate's, so it differs slightly
  from a fresh Spectre on the changed deck:
  - DC values within 5e-11 relative (values above 1e-6; values near zero, about 1e-10, differ more);
  - the stb loop gain within 1.3e-6 relative. This design's loop gain was tiny (output near 0 V), which magnifies
    relative differences.

  Setting the width back did not bring the first run's values back. Two sessions with the same history gave identical
  results, so this is history, not chance.
- **Two at once:** two interactive sessions ran side by side, both without error.
- **Left open:** the dc analysis lists a parameter `noPrevSolution` (and `restart`, `readns`, `write`). It may make each
  rerun start fresh, and so match a fresh Spectre exactly; the stb analysis computes its own DC too. Not tried: the
  approved ten starts were used.

Follow-up (the user's "Try noPrevSolution", four more starts):
- With the dc analysis's `noPrevSolution` set to `yes`, the differences were exactly the same.
- The stb analysis has no such parameter; its `prevoppoint` ("Use the operating point computed on the previous
  analysis", default `no`).
- Running dc first from scratch, then stb with `prevoppoint=yes`, left stb exactly as before and moved the DC values
  further from a fresh Spectre's: 7.4e-5 relative. A DC solved from scratch converges to a slightly different point
  than a fresh Spectre's stb-then-dc sequence, within the deck's `reltol=1e-3`.

So with the commands Spectre offers, a rerun cannot reproduce a fresh Spectre exactly. Its stb results carry about
1e-6 relative differences that depend on the candidates run before it.

What this means for the plan:
- the gain is real: about 1 s of each `mscr_ota7t` job;
- exactness is not available: a candidate's values would depend, in about the sixth digit, on the candidates its lane
  ran before it, where today every candidate is simulated afresh. Building it means accepting that, checked against
  a fresh Spectre within a tolerance; that is the user's call.

## G1 result (2026-10-02, the user's "build it", offline)

Built, off by default (`GATOR_SPECTRE_SESSION`; record 7.152):
- the hook in the optimizer's adapter, `VirtuosoBridgeBackend._new_simulator`, which takes a circuit profile's own
  simulator for the lane (a source digest step);
- `host_process.py`, the host script and process handling learned from the OCEAN and Spectre probes;
- `spectre_session.py`, the deck comparison, the SKILL of a run, the lane's rules, the completion evidence and the
  fresh check;
- `recipes.GenericMaestroProfile.lane_simulator` and its `analyze`.

Tests: `tests/workbench/test_wb_spectre_session.py`, with a stand-in interactive Spectre that keeps running at the end of
its input like the real one. Not yet run against the real Spectre: a smoke test and G2 need the user's budget.
Unknowns the smoke test settles:
- whether Spectre's SKILL front end has `drain` (it is wrapped in `errset`);
- whether a run's analysis lines reach its output before the answer (otherwise its results files are the evidence);
- what `sclRun` returns.

## G2 result (2026-10-02, the user's "Smoke test + trials"): not usable for this PDK

- The smoke test passed on the real Spectre: prompt answers, each run's own output, 0.05-0.06 s per run, results copied
  back, the host clean afterwards.
- Trial 1 (`mscr_ota7t`, every design also fresh): every session's second design was far from its fresh run (gain 263
  against 342; bias current up to 98%). Each lane fell back to fresh runs at its first check, keeping the fresh values.
- Probes on trial 1's decks found the cause. A running Spectre follows changes of `w` and `sca`/`scb`/`scc`, but not of
  `l` (DC up to 1% off) or `m` (up to 98%). That holds with `sclSetAttribute`, with one re-elaborating alter, and with
  one alter per value; one long sequence of alters crashed Spectre.

Sizing changes `l` and `m`, so the session cannot give correct values here. Trials 2 and 3 were not run.

## Follow-up (2026-10-03): width writes do not help

This task varies width only through `m` (w fixed), so G0's working `w` change was not the case the runs needed. Re-writing
each changed device's `w` after the `m`/`l` changes, and nudging it by 1% and back, both left the session as far from a
fresh Spectre as before (loop gain -25.4 against -61.6). Four Spectre runs, no cell write.

## Follow-up (2026-10-03): design variables do not help

With the sized values as netlist parameters (`l=gl_M7`; the rewrite verified identical on a fresh Spectre):
- set directly in a running Spectre, the variables took their values, but the circuit stayed the old design;
- changed through alter (re-elaborating each time, or only at the last), Spectre crashed (segmentation fault).

Spectre listed each transistor as a subcircuit (`g45n1svt`) with a gate-resistor subcircuit inside. Nine Spectre runs.

## Stages, each with its gate

- **G0 (needs the user's go: Spectre starts, no cell writes):** on the simulator host, with the bridge's Cadence set-up,
  start interactive Spectre on a deck a trial kept (`waveforms/*/attempt-1/input.scs`), alter values, rerun, compare
  with a fresh Spectre on the altered deck; time it; then two at once. About 10 Spectre runs.
- **G1 (offline):** the hook in `run_simulation` (digest step), a lane runner in the workbench, tests with a fake
  interactive Spectre (protocol, restart, every value of the built netlist reaching an `alter`).
- **G2 (needs a simulation budget):** a Spectre trial on two MScR tasks at 6 lanes: every candidate also run fresh and
  compared (check mode), then speed with a fresh run every 5th candidate.
- **G3 (the user's decision):** on by default.

## Constraints kept

No change to the reward, the actions or SAC. The deck simulated must stay the one recorded for the candidate: each
`alter` comes from that candidate's own netlist, and a difference from a fresh run stops the lane, as with built
netlists (7.142).
