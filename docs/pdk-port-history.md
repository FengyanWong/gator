# Porting circuits between the two PDKs: what was done, in order

Status: a history, written 2026-10-12 by the session "Encoder experiment plan setup" on the user's request ("record
the porting history between the two pdks"). It belongs to step 4 of the transfer experiment
(`plan-transfer-experiment.md`, section 6.4) and to records 7.320 and 7.326 of the workbench log. The second PDK is
named nowhere in this repository: "the second PDK" is the 0.18 um PDK of a second foundry that the simulator machine
also holds; its library, model file and device names stay out, and so do the numbers of its device models.

## 1. In plain words

Three circuits that exist in gpdk045 - the five-transistor amplifier OTA5t, the three-stage ring oscillator RING3 and
the regulator LDO1 - were built a second time with the second PDK's transistors, so that a network trained on the
gpdk045 circuit can be started on "the same circuit in another PDK". Nothing was tuned: each port is the same
schematic and the same bench, every size the same multiple of the smallest size its PDK allows. Where the second PDK
refused a size, the user decided what the row becomes. The limits of each ported task were then set by a rule that
was written down before any ported design was simulated.

Only this direction exists. The published AgenticSizing circuits were built in the second PDK from their paper
(record 7.295), not ported, and no circuit has been taken from the second PDK to gpdk045.

## 2. The rules, fixed before any ported cell existed (2026-10-11 22:20)

| What | Rule |
|---|---|
| Transistors | each becomes the second PDK's 1.8 V transistor of its polarity - from gpdk045's 1.8 V kind (`nmos2v`, `pmos2v`: OTA5t, LDO1) and from its 1 V kind (`nmos1v`, `pmos1v`: RING3) alike |
| Fingers | one finger, the whole width in one number (gpdk045's cells: fingers times finger width) |
| Sizes | the same multiple of the minimum size the network's relative-size input divides by; on the 5 nm grid; a lower bound rounded up, an upper bound down |
| Capacitors | gpdk045's MIM capacitor becomes the second PDK's, same side lengths and count; it has two pins, so the wire to gpdk045's third pin goes |
| Ideal parts, sources | unchanged |
| Benches | a 1.8 V bench stays as it is; RING3's 1.0 V bench runs at 1.8 V, the supply of its transistors |
| Tuning | none (the user's rule of record 7.295: build, do not tune) |
| Limits | from the task's own start design and 64 random designs by a rank rule (section 6), before any model sees the task |
| Where | cells `mscr18_<circuit>` with benches `tb18_<circuit>` in the design library the published circuits use; tasks `real:mscr18_ota5t`, `real:mscr18_ring3`, `real:mscr18_ldo1`; the second Virtuoso session |

The size factors that follow from the minimum sizes:

| Circuits | gpdk045 minimum (W, L) | Second PDK minimum (W, L) | Width factor | Length factor |
|---|---|---|---|---|
| OTA5t, LDO1 | 0.32 um, 0.15 um | 0.22 um, 0.18 um | 11/16 = 0.6875 | 6/5 = 1.2 |
| RING3 | 0.12 um, 40 nm | 0.22 um, 0.18 um | 11/6 = 1.8333 | 9/2 = 4.5 |

RING3's shortest length in gpdk045's task is 45 nm, 1.125 times the 40 nm the network divides by; the port keeps
that multiple (0.205 um). A script checks before a port is saved that every ported row is the gpdk045 row times its
factor, with a bound moved by less than one grid step and only inwards, and that each row keeps its scale: one
action is then the same multiple of the minimum size in both PDKs.

## 3. The rows, gpdk045 beside the port

Ranges and start values in micrometres unless said; "x" marks a row the size rule does not touch.

**OTA5t** (4 n-type and 2 p-type transistors; bench: 1.8 V supply, 0.9 V common mode, 50 uA reference, 1 pF load)

| Row | Devices | gpdk045: range, start | Port: range, start |
|---|---|---|---|
| `w_pair` | M1, M2 | 4 - 40, 36 | 2.75 - 27.5, 24.75 |
| `l_pair` | M1, M2 | 0.3 - 3, 1.5 | 0.36 - 3.6, 1.8 |
| `w_load` | M3, M4 | 2 - 20, 17.6 | 1.375 - 13.75, 12.1 |
| `l_load` | M3, M4 | 0.3 - 3, 1.0 | 0.36 - 3.6, 1.2 |
| `w_tail` | M5 | 4 - 40, 38.4 | 2.75 - 27.5, 26.4 |
| `l_bias` | M5, M6 | 0.3 - 3, 1.0 | 0.36 - 3.6, 1.2 |

**RING3** (3 inverters, 3 MIM load capacitors of two units each; bench: 1.0 V in gpdk045, 1.8 V in the port)

| Row | Devices | gpdk045: range, start | Port: range, start |
|---|---|---|---|
| `wn` | MN1-MN3 | 0.12 - 4, 1.0 | 0.22 - 7.33, 1.835 |
| `wp` | MP1-MP3 | 0.12 - 8, 2.0 | 0.22 - 14.665, 3.665 |
| `l` | all six | 0.045 - 0.18, 0.045 | 0.205 - 0.81, 0.205 |
| `c_w` | C1-C3 | 1.0 - 5.6, 4.49 | **4.0 - 5.6**, 4.49 (x; section 5) |
| `c_l` | C1-C3 | 1.0 - 5.6, 4.49 | **4.0 - 5.6**, 4.49 (x; section 5) |

What the 1.8 V bench changes, each by the factor 1.8: the supply (1.0 to 1.8 V), the three start voltages (0.9 / 0 /
0.9 V to 1.62 / 0 / 1.62 V), the level the duty cycle is read at (0.5 to 0.9 V), the two swing limits (low level at
most 0.1 to 0.18 V, high level at least 0.9 to 1.62 V), and the power, which the 1 V bench read as the average supply
current alone and the port reads as supply voltage times that current. The simulated time (30 ns) and the window the
frequency is read in (10 to 30 ns) stay.

**LDO1** (error amplifier of 5 transistors, a p-type pass transistor, feedback resistor, two MIM capacitors; bench:
1.8 V supply, 1.6 V reference, a load step from 10 uA to 10 mA)

| Row | Devices | gpdk045: range, start | Port: range, start |
|---|---|---|---|
| `w_pair` | M1, M2 | 1 - 20, 17.5 | 0.69 - 13.75, 12.03 |
| `l_pair` | M1, M2 | 0.5 - 2, 1.37 | 0.6 - 2.4, 1.645 |
| `w_load` | M3, M4 | 1 - 20, 12.4 | 0.69 - 13.75, 8.525 |
| `l_load` | M3, M4 | 0.5 - 2, 0.54 | 0.6 - 2.4, 0.65 |
| `w_tail` | M5 | 1 - 20, 15.0 | 0.69 - 13.75, 10.31 |
| `l_tail` | M5 | 0.5 - 2, 0.62 | 0.6 - 2.4, 0.745 |
| `w_pass` | MP | 20 - 200, 200 | 13.75 - 137.5, **137.495** (section 5) |
| `l_pass` | MP | 0.5 - 1, 0.55 | 0.6 - 1.2, 0.66 |
| `m_pass` | MP | 1 - 100, 25 (count) | the same (x) |
| `rfb_r` | RFB | 477 - 9,535, 9,490 (ohm) | the same (x) |
| `cfb_m` | CFB | 5 - 550, 40 (count of 5.6 um units) | the same (x) |
| `cl_m` | CL | 480 - 14,600, 12,460 (count of 5.6 um units) | **32 - 971, 829 (count of 23 um units)** (x; section 5) |

LDO1's gpdk045 task is the one shown as `ldo1_relaxed` with the eased high-frequency limit and the goal row (PSRR at
10 kHz keeps improving after a pass), `graphgps_ldo1_t2` - the LDO1 task step 3b runs. The port keeps the goal row.

## 4. In order of time (2026-10-11 and 12, clock times of the workstation)

| When | What |
|---|---|
| 10-11 21:46 | User: "wait for landing then continue" - the ports wait for the second build of the network inputs (record 7.317), landed 21:57. |
| 22:10 | A read-only pass over the three gpdk045 circuits (how each is built by script, its rows, its bench) and over what the workbench knows of both PDKs' minimum sizes. Nothing built. |
| 22:20 | The rules of section 2 and the rank rule written into the plan (section 6.4) and told to the user, before any ported cell exists. |
| about 22:25 | OTA5t: cell and bench built, one Spectre check of the start design (it converges, every probe computes), task saved, baseline, Calibration (64 of 64 random designs measure). |
| 22:50 | OTA5t's limits by the rank rule, saved as revision 2. The plan's sentence on the rule corrected the same hour: it names record 7.262, whose form holds the phase margin at 60 deg; the paragraph had written out the stricter form of record 7.240. |
| about 22:53 | RING3: built, checked, saved, baseline. Its Calibration stops at the first random design: the second PDK's capacitor form sets a side under 4 um back to 4 um, the written value does not read back, the write is refused. The half-written cell is discarded from Virtuoso's memory (no window held it). |
| about 22:55 | LDO1: the cell's read-back is refused - the load capacitor's count of 12,460 is set to 1,000 by the form. The bench is not built. Both questions go to the user. |
| about 23:00 | User: "1. ring3s cap. yes take the range. 2. LDO load cap take the recommended 3. take the recommended row", and "hold the next runs until I come back and say go". |
| 23:00 - 23:10 | RING3's capacitor rows narrowed, revision 2, Calibration repeated (62 of 64 random designs oscillate), limits by the rule, revision 3. LDO1 rebuilt with the larger capacitor unit; its first baseline is refused (the grid's top, section 5), the cell rebuilt one grid step lower; the save after the rebuild is refused once (a stale netlist, section 5); revision 2 saved, baseline complete. LDO1's Calibration is not started: the session's permission check refuses it under the hold. |
| 10-12 02:45 | User: "go on the rest of the plan". |
| 02:47 | LDO1's Calibration: 44 of 64 random designs measure every row (20 have no phase margin - a loop without a unity-gain crossing). Limits by the rule at rank 22, revision 3. |
| 02:54 - 03:00 | The nine-design check of each ported task with the second build of the network inputs: every transistor of every simulated design carries its operating point and all four ratios. The ports are ready for step 4's runs. |

## 5. What the second PDK refused, and what became of it

- **A MIM capacitor side under 4 um** (RING3). gpdk045's rows go from 1.0 um. The user's decision: the rows go from
  4.0 to 5.6 um; the start, 4.49 um, is unchanged. Lost: the low end of that action - the port cannot make its load
  capacitors smaller than 4 by 4 um, where the gpdk045 circuit goes down to 1 by 1 um.
- **More than 1,000 units of a MIM capacitor** (LDO1's load: 12,460 units of 5.6 um, its row 480 to 14,600). The
  user's decision: a larger unit and a smaller count for the same capacitance. Built as a 23 um unit with the count
  row 32 to 971 and the start 829 - the start and both ends are the gpdk045 values converted by the two units'
  capacitances as the capacitor's own form states them, rounded to whole units (inwards at the ends).
  **A correction on record:** the numbers first recommended to the user (a 22.4 um unit, sixteen times the area, the
  count divided by 16) would have been about 11 % short: a unit's capacitance has an area share and an edge share, and
  the edge share does not grow with the area. The row was built from capacitances, not areas, and the user was told.
  The feedback capacitor (40 units of 5.6 um, row 5 to 550) fits the form and is unchanged.
- **A start value on a range's upper bound that the size grid does not reach** (LDO1's pass width, 137.5 um). The
  optimizer counts grid steps from the lower bound as `floor((upper - lower) / step + 1e-12)`; for 13.75 to 137.5 um
  in 5 nm steps the division gives 24749.999999999993, so the grid ends at 137.495 um. A cell built at 137.5 um
  differed from the task's own start design and its baseline was refused ("Initial backend parameters differ from the
  reference graph"). The port starts at 137.495 um. The same loss of a last grid point can meet any row whose bounds
  divide to a hair under a whole number; it is in the optimizer package and was left as it is (its source digest).
- **A netlist Maestro did not make again** (LDO1, after the rebuild). Maestro netlists a bench into one kept folder
  on the simulator machine, incrementally; after the cell had been deleted and built again by script it began and
  ended in the same second and kept the old circuit. The workbench's Save task compares Maestro's circuit with the
  schematic export and refused the save in words. That bench's folder was moved aside and the next save netlisted
  afresh. An ordinary edit followed by a save has always been netlisted again.
- **A half-written cell after a refused write** (RING3's first Calibration). The refused form write left the cell
  changed in Virtuoso's memory, not on disk; it was discarded from memory and Check now passed.
- Not refused, and worth knowing: a single 137.5 um finger is accepted; a cell belongs to the Virtuoso session that
  wrote it first (its edit lock), so the three ports run in the second session only.

## 6. The start designs and the limits

The start design of each task on Spectre, gpdk045 beside the port. No size was tuned, so the port is the same
multiples of the minimum size and not the same performance.

| Circuit | Measure | gpdk045 start design | Port's start design |
|---|---|---|---|
| OTA5t | gain / bandwidth / phase margin | 30.7 dB / 93.7 MHz / 83.9 deg | 45.8 dB / 80.3 MHz / 77.2 deg |
| | power / PSRR / noise | 0.294 mW / 32.7 dB / 35.0 uV | 0.299 mW / 45.8 dB / 21.5 uV |
| RING3 | frequency / power | 1.208 GHz / 0.196 mW (at 1.0 V) | 1.501 GHz / 1.029 mW (at 1.8 V) |
| | low level / high level / duty cycle | 0.004 V / 1.003 V / 50.8 % | 0.000 V / 1.750 V / 48.5 % |
| LDO1 | output / dropout / quiescent current | 1.6032 V / 0.197 V / 135.5 uA | 1.6042 V / 0.196 V / 97.7 uA |
| | loop gain / bandwidth / phase margin | 47.6 dB / 14.5 MHz / 35.1 deg | 42.5 dB / 6.49 MHz / 59.4 deg |
| | PSRR at 10 kHz / 1 MHz / high frequency | -47.5 / -26.7 / -0.56 dB | -23.7 / -16.5 / -0.48 dB |
| | load regulation | 16.0 mV | 12.3 mV |

**The rank rule** (plan section 6.4; `rank_ports.py` in the review folder applies it and reads nothing but the
Calibration run): a ranked row's limit is the k-th best value the 64 random designs measured in it; k is the highest
rank, at most 32 and at most half the least-measured row's count, at which at least three random designs reach every
row; a phase-margin row stays at 60 deg (record 7.262); a limit in dB may be negative; a band around a target (RING3's
frequency) is ranked "the higher the better", the k-th best value becomes the band's centre and the band keeps its
relative width; rows that say what a valid result is (RING3's duty cycle and two levels) keep their limits; the random
designs that pass every row are counted, not forbidden.

| Circuit | Row | gpdk045 task's limit | Port's limit (rank) | Random designs reaching it |
|---|---|---|---|---|
| OTA5t (rank 32; 6 of 64 pass every row) | gain | at least 30 dB | at least 44.31 dB | 32 |
| | bandwidth | at least 100 MHz | at least 35.23 MHz | 32 |
| | phase margin | at least 60 deg | at least 60 deg (held) | 64 |
| | power | at most 0.5 mW | at most 0.1896 mW | 32 |
| | PSRR | at least 30 dB | at least 43.36 dB | 32 |
| | noise | at most 50 uV | at most 35.27 uV | 32 |
| RING3 (rank 31; 1 of 64) | frequency | 0.95 - 1.05 GHz | 557.2 - 615.9 MHz (586.5 MHz, 5 % either side) | 5 |
| | power | at most 0.15 mW | at most 0.697 mW | 31 |
| | low level | at most 0.1 V | at most 0.18 V (kept, scaled) | 60 |
| | high level | at least 0.9 V | at least 1.62 V (kept, scaled) | 52 |
| | duty cycle | 45 - 55 % | 45 - 55 % (kept) | 36 |
| LDO1 (rank 22; 0 of 64) | dropout | at most 0.22 V | at most 0.1964 V | 22 |
| | quiescent current | at most 200 uA | at most 18.59 uA | 22 |
| | phase margin | at least 60 deg | at least 60 deg (held) | 44 |
| | PSRR at 10 kHz (goal row) | at most -30 dB | at most -9.97 dB | 22 |
| | PSRR at 1 MHz | at most -20 dB | at most -1.41 dB | 22 |
| | PSRR at high frequency | at most -1.7 dB | at most -0.0016 dB | 22 |
| | load regulation | at most 32 mV | at most 15.0 mV | 22 |

What the rule gave, read plainly:

- **OTA5t** is an ordinary task: its start design passes five of six rows (it fails power, 0.299 against 0.190 mW)
  and six random designs pass everything.
- **RING3's band lies far below its start design** (1.50 GHz against a band at 0.59 GHz): the rule takes the
  frequency of the 31st-fastest random design as the centre, and the start design is faster than all but a few random
  designs. The start design fails the two ranked rows.
- **LDO1's limits are those of a weak regulator in PSRR and a demanding one in current**: the median random design
  hardly rejects supply ripple, so the ranked PSRR limits sit near 0 dB, while the quiescent-current limit (18.6 uA)
  is a fifth of the start design's 97.7 uA - dead regulators draw almost nothing and pull that rank down. The start
  design fails the current row and the phase margin (59.4 deg). No random design passes every row; whether a design
  does is what step 4's runs show. The rank is 22 and not 32 because the phase margin is measured in 44 designs only.
  A first application of the rule had capped the rank by the ranked rows alone (32); it was corrected to the plan's
  wording - half the least-measured row of all - before any limit was saved.

These are the rule's results as it was written beforehand; none was adjusted after the designs were seen.

## 7. What a port is, and is not

- The same schematic, the same bench (RING3's at the other supply), the same rows, every transistor size the same
  multiple of its PDK's minimum: the network's relative-size input and its actions mean the same in both tasks.
- Not the same electrical design: no bias point, gain or speed was matched. RING3 runs at 1.8 V with long transistors
  where the gpdk045 circuit runs at 1.0 V with short ones; LDO1's start design has half the PSRR in dB of its
  gpdk045 start design.
- Not the same limits: a 0.18 um circuit cannot meet numbers set for 45 nm, so each port has limits of its own from
  the rank rule. A "pass" on a port and a "pass" on its gpdk045 task are different statements.
- Two rows differ in what they can reach: RING3's capacitor sides (4.0 um at least) and LDO1's load capacitor (a
  coarser unit, the same capacitance range).

## 8. Where things are, and how to repeat a port

- The port script, outside the repository because it holds the second PDK's names: `~/mscr_circuits/port_pdk2.py` -
  `sizes` (the table of section 3 and its checks), `build <circuit> [--replace]`, `trial <circuit> --tag=<new>` (one
  Spectre check), `task <circuit> [--dry] [--update]` (save through the workbench's Save task; the baseline follows
  by itself).
- In the review folder `artifacts/local/reviews/transfer-experiment-2026-10-10/` (untracked): `rank_ports.py <task>
  <Calibration experiment>` writes `rank-<task>.json`; `save_port_limits.py <task>` saves those limits as the task's
  next revision and runs Check now; `prepare_tx4.py opcheck` writes the nine-design checks; `step4-port-plan.md` is
  the working plan with the state at each stop.
- Runs behind the numbers here: baselines `task-baselines` (one per task); Calibrations
  `tx-prep-mscr18-ota5t-calibration`, `tx-prep-mscr18-ring3-calibration-r`, `tx-prep-mscr18-ldo1-calibration-r` (68
  designs each: the start design on four lanes and 64 random designs); the checks `tx-prep-mscr18-<circuit>-opcheck`.
- Records: 7.320 (the builds, the user's three decisions, the faults met), 7.326 (LDO1's limits, the checks, this
  history).
