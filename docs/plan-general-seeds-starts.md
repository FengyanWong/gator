# Plan: the general model on the six circuits over several starting designs and seeds, against scratch (2026-10-07, compact form)

User: "write a plan to use the general model and try the six circuits with different starting seeds and starting design
parameters. Check the passing rate and compare with scratch start. You decide how many different seeds to have."

Status: plan only, in its compact form (user, 2026-10-07: "reduce the time needed by the seeds and start plan").
Nothing is registered or started by this plan. The simulator is busy today with the equal-recipe arms
and the two held-out circuits (record 7.262); the runs below start only on the user's word, after those.

---

## 1. The question, in plain words

Every comparison so far had ONE seed per arm and ONE starting design per circuit: start B with seed 1 (record 7.229,
the own models), start C with seed 2 (records 7.237-7.239, the general model with the anti-drift recipe; and today's
equal-recipe arms, record 7.262). A head start of 80-90 points on three circuits is far outside any seed spread, but the
"no" on ring3 and the LDOs, and the size of the head start, rest on single draws. This plan asks: over several starting
designs and several seeds, what passing rate does the general model reach on each circuit, and how much higher is it than
scratch at the same budget? The answer is a distribution per circuit, not one number.

## 2. What is fixed, and what exists

- **The general model:** the published offline checkpoint `ckpt-00000000-9b48fb98` (run `offline-network__c8c3531a0d78`),
  trained on the 22 archived runs of the A and B starts (17,124 evaluations, record 7.233). It never saw the C start, and
  it never saw any baseline's random designs (baselines hold no transitions).
- **The recipe:** the scratch recipe for BOTH arms (learning rate 1e-3, eight updates per transition, batch 8, target-only
  replay, no rehearsal, alpha 0.01, gamma 0). Today's equal-recipe arms showed it gives the general model the same head
  start as the anti-drift recipe on the circuits in the pool and a far better result on OTA8m (491 against 24 of 800); with
  one recipe the two arms differ only in the loaded weights.
- **The tasks:** the six circuits with the C goals (the A goals, the LDO HF PSRR rows relaxed to -3 / -2.3 dB), Scale 6 on dB
  rows, the shared 41-slot registry, 800 launches, the lane counts of the C arms (four lanes; one lane on ota7t_w and
  ldo2_rgcn, as their A runs).
- **Existing runs that count:** on start C with seed 2, the scratch arm (records 7.237-7.239) and the equal-recipe general
  arm (record 7.262) on all six circuits. The anti-drift G arms do not count (another recipe).
- **Measured wall time** (today's C arms, 800 launches): ota5t 8-11 min, ring3 9-11, ldo1_rgcn 9-13, ota7t_w 22-27 (one
  lane), ldo2_rgcn 26-28 (one lane), vco_lin_c 35-42. One arm over the six circuits: about 2 hours; one start-seed pair
  of both arms: about 4 hours.

## 2a. The six circuits

The six MScR circuits of records 7.229 and 7.233-7.239, each on its start-C task (`real:mscr_<name>_c`, the 25th-percentile
random design of record as the starting point, the A goals with the LDO HF PSRR rows relaxed):

| Key | Cell | Circuit | Specs rows | Parameter rows | Lanes |
|---|---|---|---|---|---|
| ota5t | mscr_ota5t | 5-transistor OTA (NMOS pair, PMOS mirror, tail + bias diode), GPDK045 1.8 V devices | 6 | 6 | 4 |
| ota7t_w | mscr_ota7t_w | two-stage Miller OTA ("7T" + bias diode), widths and lengths sized, 1.0 V devices | 4 | 14 | 1 |
| ring3 | mscr_ring3 | 3-stage inverter ring oscillator with MIM load capacitors, 1.0 V devices | 5 | 5 | 4 |
| vco_lin_c | mscr_vco_lin_c | highly linear ring VCO (the `_c` variant with the resistor divider rows) | 8 | 7 | 4 |
| ldo1_rgcn | mscr_ldo1_rgcn | Li & Chan Carusone ICCAD 2023 LDO1: 5T error amplifier, PMOS pass, Rfb-Cfb network, on-chip CL; HF PSRR <= -3 dB | 7 | 12 | 4 |
| ldo2_rgcn | mscr_ldo2_rgcn | the same authors' LDO2: folded-cascode error amplifier, PMOS pass, Rfb-Cfb network, on-chip CL; HF PSRR <= -2.3 dB | 7 | 16 | 1 |

Not in this plan: ota7t without width rows (old reward settings), vco_lin, ldo_basic and ldo2_rgcn_gt (pooled, no C start),
and the two held-out circuits (otafc, otatc), which have their own test.

## 3. The design (compact form)

**Where the time goes, and the three levers.** In the full form (three starts, three seeds, 800 launches) one start-seed
pair of both arms over the six circuits costs about 4 hours and the design needs eight new pairs: 33 hours. The levers,
in order of what they cost in evidence:

1. **400 launches per run instead of 800** halves everything. The early measures (designs 9-108, passes by 100 / 200 / 400)
   are identical; only the end measure moves from the last third of 800 to the last quarter of 400 (designs 301-400).
   The existing 800-launch arms on C (seed 2) are reused by truncation: the first 400 evaluations of a run do not depend
   on its budget (the budget only ends the run), so they are the same run at 400. The verdict then speaks of a 400-launch
   budget, which favours a head start over slow convergence; that is said in the record.
2. **Two starts instead of three** (C, which exists, and D, the 75th-percentile design close to passing): the easy and
   the hard start of the three; E (the 10th percentile) stays optional as a later block.
3. **Three seeds are kept.** Two cannot tell a seed spread from a difference, and the spread is the point of the plan.

**Starting designs: C and D.** C exists on every circuit. D by the start-B rule from the same 64 random designs of each
circuit's A baseline (ota7t_w: the 8 warm-up draws of its run): the valid design at the 75th percentile of reward among
those that failed at least one row. B (the median) is not used: the pool holds the B runs. D is a cell of its own
(`real:mscr_<name>_d`), built by the start-B writer with a percentile argument, saved through the workbench, Check now,
and a required Baseline simulation (65 launches, seed 2) that never enters training.

**Seeds 2, 3 and 4** per arm and start. C has seed 2 for both arms already (the scratch arms of records 7.237-7.239 and
the equal-recipe general arms of record 7.262), so C needs seeds 3 and 4 only.

**Arms:** S = scratch; G = the general model loaded, fine_tune, the same recipe (1e-3, eight updates, target-only, no
rehearsal). 400 launches each; the configuration of the equal-recipe arms with the task, the seed and the budget changed.

| Block | Runs | Launches | Simulator time |
|---|---|---|---|
| D cells, tasks, baselines | 6 baselines | 390 | about 30 min, plus the cells (about 30 min) |
| C, seeds 3 and 4, both arms | 24 | 9,600 | about 4 h |
| D, seeds 2, 3 and 4, both arms | 36 | 14,400 | about 6 h |
| **Total** | **60 + 6** | **24,390** | **about 11 h** |

Optional later blocks, each a complete slice: E (10th percentile) with three seeds, 36 runs, 14,400 launches, about 6 h;
or the 800-launch end measure on C and D for seed 2 only (the C pairs exist; D seed 2 at 800: 12 runs, about 4 h).

The queue runs one arm at a time in the order C-3, C-4, D-2, D-3, D-4 (each: the six circuits, S then G); it is
restart-safe and can be stopped between runs; every finished block is a complete slice.

## 4. Measures and criteria (fixed before any run)

Per run, the definitions of record 7.229 at a 400-launch budget: **passing rate** = passing designs of 400; **early
share** = passing share of designs 9-108; passes by 100 / 200 / 400; **last-quarter share** (designs 301-400); the first
75-of-100 window ("acceptable", record 7.242). Per circuit and start: mean, minimum and maximum over the three seeds for
S and for G, and the paired difference G - S per seed. Per circuit: the six pairs (two starts x three seeds).

- **P1 passing rate:** G's mean passing rate exceeds S's on at least four circuits, and in at least five of the six
  pairs on each of those circuits.
- **P2 head start:** G's mean early share is at least 30 points above S's on at least four circuits, AND the difference
  exceeds the seed range of both arms on those circuits (the head start is larger than the noise).
- **P3 end:** G's mean last-quarter share is within 5 points of S's or above on all six circuits.
- **P4 start dependence, reported, no bar:** the spread of G's passing rate across the two starts against the spread
  across the three seeds. If the start matters more than the seed, the transfer is start-dependent and a single-start
  verdict (like 7.229's) is the wrong instrument.
- **Verdict rule:** "at a 400-launch budget the general model raises the passing rate over scratch" if P1 and P3 hold;
  "and gives a head start" if P2 holds as well. Anything else is reported as measured, with the per-circuit distributions.

The LDOs are judged at their relaxed rows; ring3's low passing rates are reported as they come.

## 5. Procedure

1. D starts: the writer with the percentile rule, six cells, Save task, Check now, the six baselines (seed 2) through the
   C-task baseline recipe; their random designs of record are kept with the qualification.
2. Configurations: from the equal-recipe G2 configuration and the C scratch configuration, the task, the seed and the
   budget replaced, validated against the schema; a compatibility proof of the general model on each D task.
3. The queue, on the user's word, through the same runner, frozen runtime and private settings copy as today's arms, one
   run at a time, Check now before and after each run.
4. `compare.py` after every finished block: the per-circuit table and the criteria (the C seed-2 pairs truncated at 400),
   so the user can stop after any block.
5. The record: per-block tables, the final distributions, P1-P4, and the plan's verdict.

## 6. Decisions for the user

1. **The compact form as stated** (C + D, seeds 2-4, 400 launches: about 11 h), or the full form of the first draft
   (C + D + E, 800 launches: about 33 h), or a mix (the optional blocks of section 3).
2. **D at the 75th percentile** as proposed, or another percentile.
3. **Budget:** 24,390 launches, approvable block by block (D baselines, C seeds, D seeds).
4. **Lanes:** ota7t_w and ldo2_rgcn run one lane as their A runs did (22-28 min per 800); four lanes would save about a
   quarter of the queue time but would make those two circuits' new arms differ from their existing seed-2 pairs. Not
   proposed; the user may choose it for a fresh C seed-2 pair as well.

Parked, as every further plan must say: the SKY130 benchmark stays untouched; the MScR circuits on Spectre are the test bed.

## 7. What goes on record

This plan; the D task definitions in `~/mscr_circuits` (outside the repository); the queue folder under
`artifacts/general-network-20261006/` with configurations, logs, checks and `compare.py` outputs; a record entry per
finished block or at the end; the verdict in `docs/decisions.md`. Nothing in `src/` changes.
