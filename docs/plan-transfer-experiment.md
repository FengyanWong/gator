# Plan: the transfer experiment - networks with the new inputs, new targets (a logic cell first), SAC against Bayesian optimization, a second PDK, one general model on unseen circuits

Written 2026-10-10 (Europe/London), record 7.301, session "Encoder experiment plan setup". User: "let us discuss and set
up new experiment plan: read encoder run plan revision, assume all changes are landed. Give an overall plan of the
experiment. try to reduce the number of circuits ... Things to compare if not already: different network on all circuits,
different opt on one circuit from scratch (sac bayesian), different spec settings on three circuits (so I can make a
circuit with different target), test pdk transfer on two/three circuits, and then use general trained network to test on
agentic sizing for hopefully better performance."; settled in the conversation that followed (section 12 lists each
decision in the user's words), then "yes save the plan now".

Status: **plan only; nothing built, no task changed, no run queued.** Every simulation waits for the user's word.

**Revised 2026-10-10 (record 7.305, session "Trained model spec change topology proof"; user: "make the stdcell plan
first part of the step 3(the spec change) and exchange current plan step 2 with step 3 so after step 1 it runs stdcells
first"):** the old steps 2 and 3 changed places - the new targets are step 2, SAC against Bayesian optimization is step
3 - and the new-target step begins with a logic cell, the flip-flop DFFRX1 (section 6.2.1). Records 7.301 to 7.304
carry the old numbers; the windows' folders and the run names of section 13 were renamed the same evening.

It follows [the encoder comparison](plan-encoder-comparison.md) and [its additions](plan-encoder-comparison-additions.md)
(records 7.256, 7.273-7.289, 7.293, 7.295) and rests on the three changes landed on 2026-10-10: the transferable network
inputs (7.298), a missing value counted as a failed row (7.299) and the four AgenticSizing circuits rebuilt from their
published netlists (7.300). It **replaces** the AgenticSizing restart that 7.299 and 7.300 left open (the 24 runs of
stages A and B on those circuits): none of those runs is part of this plan. The old stages A to E are not run again;
their recorded runs are the references.

## 1. In plain words

Six questions, one step each. Round 1 runs every comparison once; round 2 repeats only what showed an effect.

| Step | Question | Circuits | Network | Runs | Time |
|---|---|---|---|---|---|
| 1 | Do GT and GraphGPS differ with the new network inputs, and do the new inputs learn as well as the old ones? | 4 core + 4 AgenticSizing | GT and GraphGPS | 20 | about 7 h |
| 2 | Does a trained model reach a new target faster than starting over? | logic cell DFFRX1 first, then OTA5t, RING3, LDO1 | GraphGPS | 19 + 3 probes | about 4.3 h |
| 3 | Is SAC better than Bayesian optimization, from scratch? | AgenticSizing LDO | GT (SAC) | 9 | about 1.7 h |
| 4 | Does a gpdk045 model help on the same circuit in a second PDK? | OTA5t, RING3, LDO1, ported | GraphGPS | 9 + 3 probes | about 2.5 h |
| 5 | Does one general model beat starting over on an unseen circuit in the known PDK? | telescopic cascode | GraphGPS | 2 + 1 probe | about 0.75 h |
| 6 | Does the same general model beat starting over on the AgenticSizing circuits? | 4 AgenticSizing | GraphGPS | 4 + 4 probes | about 2 h |

Round 1: **63 runs and 11 probes, about 54,400 simulated designs, about 18.2 h** of simulation (section 9). The times of
the published and the ported circuits and of the logic cell are estimates until their first runs.

## 2. Words used

- **Design:** one set of sizes, simulated once. A run is 800 designs.
- **Pass:** a design that meets every Specs row.
- **From scratch:** a fresh network, trained on this one task only.
- **Fine-tune:** start from a trained network and keep training on the new task.
- **Probe:** a trained network proposes 300 designs with no further training (mode `frozen`, sampled actions).
- **General model:** one network trained offline on the recorded designs of many circuits; no new simulation.
- **Seed:** the number that fixes a run's random choices; a repeat is the same run with another seed.

## 3. Circuits: from twelve to eight with new runs, and one logic cell

| Group | Circuit, task | Why |
|---|---|---|
| Core, gpdk045 | OTA5t, `mscr_ota5t` | 9-13 min per 800 designs; 95 % late passes for every network; built on the PDK's 1.8 V transistors, so the cleanest port |
| Core, gpdk045 | RING3, `mscr_ring3` | from scratch only 10-34 % late passes: room to show a gain |
| Core, gpdk045 | LDO1 at HF PSRR <= -3 dB, `ldo1_relaxed` (key `graphgps_ldo1`) | 0 to 3 passes of 800 from scratch for every network; 34 to 55 with a general model |
| Core, gpdk045 | VCO, `mscr_vco_lin_c` | kept on the user's word; 36-99 min a run; step 1 only |
| Logic cell, gpdk045 | flip-flop DFFRX1, a copy of `gsclib045/DFFRX1` (to build) | step 2, first: delay, energy and area trade over a wide range, so a new goal lies far from the old one (6.2.1) |
| Unseen, gpdk045 | telescopic cascode, `mscr_otatc` | step 5; out of every training pool of this plan |
| AgenticSizing, second foundry's 0.18 um PDK | `agentic_ldo_pub`, `agentic_bgr_pub`, `agentic_fc_pub`, `agentic_sys_pub` (7.300) | the paper's netlists, size ranges and limits; steps 1, 3 and 6 |
| No new runs | OTA7t width, LDO2, folded cascode `mscr_otafc` | their recorded designs train the general model |

Why the three are dropped: OTA7t width gave the same verdicts as OTA5t in every table (single lane, 24-37 min a run);
LDO2 tells LDO1's story at three times the time (the two differ in the error amplifier only: five transistors against a
folded cascode); the folded cascode is no longer needed as an unseen circuit. One pass over OTA5t, RING3 and LDO1 takes
about 40 min; the six circuits of the encoder comparison took about 2.6 h.

LDO1 with the relaxed row from start A is the registered task `graphgps_ldo1` (the same circuit, start and rows as
`mscr_ldo1_rgcn` but for HF PSRR <= -3 dB, record 7.231; the stage-E task `mscr_ldo1_rgcn_a` was deleted on
2026-10-09). On the user's word ("rename the task and run both on it", record 7.302) it is shown as **`ldo1_relaxed`**
and both networks run on it: a task does not force a network. The rename changes the shown name only; a
configuration file names the task by its key, `real:graphgps_ldo1`, and its recorded GraphGPS run stays its run.

The published circuits as they stand (record 7.300):

| Task | Transistors, variables | Rows the start meets | Note |
|---|---|---|---|
| `agentic_ldo_pub` | 22, 27 | 2 of 5 | - |
| `agentic_bgr_pub` | 25, 26 | 3 of 4 | the temperature row starts near 1,000 ppm/C where the paper's own recorded designs say 4 to 36: the published sizes were balanced for the paper's process, so this row is a harder problem here |
| `agentic_fc_pub` | 29, 19 | 11 of 11 | the published start passes on our bench, so "simulations to the first pass" would be 1: a second starting design was made (section 8, item 5; record 7.303): task `agentic_fc_pub_far`, the lowest-reward fully measured design of 64 random ones, which misses ten of the eleven rows; every run of this plan on the amplifier uses it |
| `agentic_sys_pub` | 55, 50 | 2 of 6 | - |

## 4. Fixed settings

- **Networks:** GT and GraphGPS only (user). Step 1 runs both; step 3 uses GT; steps 2 and 4 to 6 use GraphGPS.
- **Network inputs:** every new model is made with Network inputs **Transferable** (`spec_input` set, `size_features`
  pdk_relative, `device_model_features` true) and the family component list. Steps 2 and 4 to 6 need them: a model with the old
  inputs loads only on a task with the same spec names and reads sizes in micrometres. One arm of step 4 differs on
  purpose (absolute sizes, no device numbers).
- **A run:** 800 designs; the presets' training numbers (learning rate 1e-3, initial alpha 0.01, 8 updates per design,
  gamma 0, batch 8, warm-up 8, replay 10,000, episode 4); the page's reward; the lanes each task ran with before (4).
- **A loaded run:** the same numbers, target-only replay, the loaded temperature carried (the recipe of record 7.262).
- **Seeds:** 0 for every single run; repeats take seeds 1 to 4.
- **One code version:** a frozen copy of HEAD taken when round 1 is frozen; the optimizer digest (`94e7dd4f...` today)
  is checked before every run. Nothing in `src/analog_optimizer/` changes for this plan.
  **Changed on 2026-10-11 (record 7.309, user decision):** step 1 ran on that copy (`94e7dd4f...`); from step 2 on the
  runs use a second frozen copy with the digest `6724e52b...`. The one change in the package is the netlist comparison
  of a real run (a number spelled in two ways is one value): no network, reward or learning code, so the steps stay
  comparable; a model saved in step 1 fine-tunes and evaluates under the new digest, an exact resume of one needs the
  first copy.

## 5. How a run is judged

Read from the recorded tables, with the script of the encoder comparison (`compare_runs.py`):

- **Early passes:** the share of passes among the first 100 designs the network proposes itself (designs 9-108).
- **Late passes:** the share of passes in the last third (266 designs).
- **Passes of 800**, and the design at which half / three quarters of a 100-design window pass.
- **First pass:** the number of the first passing design, and the clock time to it (the paper's measure, section 6.6).

Rules, the ones of the earlier studies, fixed here before any result:

- **The new inputs are accepted** on a circuit when late passes stay within 10 points of the recorded old-input run of
  the same network and the 50 % point comes no more than 100 designs later.
- **A loaded model helps** when its early passes are at least 30 points above scratch; it **ends as well** when its late
  passes are no more than 5 points below scratch; it **does not deteriorate** when its late passes are at least its early
  passes minus 10 points.
- On circuits where scratch finds no pass at all, any pass of the loaded model is reported as measured, with no bar.

## 6. The steps

### 6.1 Step 1: the two networks with the new inputs (20 runs)

- **Runs:** GT and GraphGPS from scratch on the four core and the four AgenticSizing circuits, seed 0 (16 runs);
  GraphGPS four more times on the AgenticSizing LDO, seeds 1-4, so that circuit has five runs against five (GT's other
  four are step 3's SAC runs).
- **New inputs against old:** each core run against the recorded old-input run of the same network (rule of section 5):

  | Circuit | GT, old inputs (passes of 800, late, 50 % by) | GraphGPS, old inputs |
  |---|---|---|
  | OTA5t | 629, 95 %, 191 | 646, 95 %, 176 |
  | RING3 | 82, 15 %, never | 194, 29 %, never |
  | LDO1 at -3 dB | 0 (stage E) | 3, 1 %, never |
  | VCO | 540, 94 %, 291 | 603, 98 %, 222 |

- **GT against GraphGPS:** on the core circuits one run each, so only a large difference counts; on the AgenticSizing
  LDO five against five.
- **Conditional, one run each:** a control (GT, old inputs, today's code, LDO1) if the new LDO1 run differs from the
  recorded one - LDO1 is the only core circuit where designs had missing values (1-2 %), the rule 7.299 changed; and, on
  an AgenticSizing circuit where a from-scratch run finds no pass, one continuation of that run from its own network for
  another 800 designs (this stands in for stage B, which is not part of the plan).
- **Produces:** the GraphGPS models of OTA5t, RING3 and LDO1 that step 2 starts from, and the from-scratch side of step 6.

### 6.2 Step 2: new targets on a known circuit - a logic cell first, then three analog circuits (40 runs)

- **A new target** is a Save as copy of the task with new limits. The limits are chosen from the designs already
  simulated on that circuit so that about 2-10 % of them pass - reachable, not trivial - and are frozen, with the
  copy's baseline and a 64-design Calibration, before any model sees them.
- **Runs per circuit, on the new-target task:**

  | Run | Starts from |
  |---|---|
  | Scratch | a fresh GraphGPS network |
  | Fine-tune, old-target model | step 1's GraphGPS model of the circuit, which knows only the old target |
  | Fine-tune, multi-target model | a GraphGPS model trained offline on the circuit's recorded designs, re-scored under many different targets but never the tested one |
  | Probe | the multi-target model, no training |

- **What it tells:** whether "Save as, new limits, load the model, run" needs fewer simulations than starting over, and
  whether the model must have seen several targets for that.
- **Order (user, 2026-10-10):** after step 1 the logic cell runs first (6.2.1; it has ten runs of its own, not the
  arms above), then OTA5t, RING3 and LDO1 (6.2.2).

#### 6.2.1 First part: a logic cell, the flip-flop DFFRX1 (10 runs)

User: "i think in the same topology spec change part pure analog circuit wont [excel]. Can you use it for standard cell
optimization like for one logic cell to modify its ppa?", then "yes add DFFRX1 for step 3 as a task" (3 was this step's
number then), then "make the stdcell plan first part of the step 3(the spec change) and exchange current plan step 2
with step 3 so after step 1 it runs stdcells first". Session "Trained model spec change topology proof", record 7.305.
**Status: run on 2026-10-11 (record 7.310), nine of the ten runs complete.** From scratch no run finds a passing design in 800 (five
runs: speed, power, and the in-between speed with three seeds). From the both-goals model: speed 388 passes (first at design 16),
power 309 (16), in-between speed 264 (40) and 409 (91) for seeds 0 and 1; the third seed's run from the model died at design 93 when
the second Virtuoso session stopped answering (one pass, at design 85) and is not repeated yet. Results:
`artifacts/local/reviews/stdcell-dffrx1-2026-10-10/results-dffr.md`. What follows is the plan as it was run; the bench numbers the
rule gave are 20 fF, 40 ps and 10 ps, and the energy row is the cell's own switching energy (the supply energy less the loads' share).

- **Why a logic cell:** in step 1's GraphGPS run the passing OTA5t designs sit in a narrow band (power 0.26-0.31 mW,
  UGB 100-128 MHz, gain 30.1-31.7 dB), so a new target has little distance to cover; RING3 has room (power of passing
  designs 55-135 uW). A logic cell trades delay against power and area over a wide range, and a library holds the same
  cell at several drive strengths: the same topology under different targets.
- **The cell:** `gsclib045/DFFRX1`, a D flip-flop with reset: 32 transistors of the known PDK's 1 V kind, all 45 nm
  long, NMOS 145 or 260 nm and PMOS 215 or 390 nm wide. It is copied into the user's own library; the vendor library is
  not edited. The library's own X1, X2 and X4 (real outlines 4.0, 4.4 and 5.6 um wide, 1.71 um high) are the reference.
  A cell of 2 or 4 transistors was not chosen: a plain sweep solves it, so starting over leaves nothing to gain.
- **What is varied:** widths only; every length stays 45 nm, as in the library. 22 widths: the cell has 11 stages, each
  with an NMOS and a PMOS width, and transistors stacked in series follow one leader (`binding_group`). The start is the
  library's X1 sizes; each width may go from the PDK's minimum to about four times its X1 value (settled at the build).
- **The bench:** one timed simulation of eight clock cycles at 1.0 V with the typical models, one input slope (40 ps)
  and one load on both outputs. The data pattern captures a 1 and a 0 with the data early, captures them again with the
  data late, and then tries to disturb each just after the clock edge. Leakage is read from the operating point.
- **The bench's numbers, by rule** (user, 2026-10-11: suggestion 5 taken; fixed before any run, from simulations of the
  library's own three cells with their sizes typed into the copy):
  - the **load** is the smallest of 2, 5, 10, 20 and 50 fF at which the X4's mean clock-to-output delay is at most
    three quarters of the X1's - a load at which drive strength matters;
  - the **setup time** of the check is the smallest multiple of 10 ps at which the X1, the X2 and the X4 all pass the
    10 % check on both edges;
  - the **hold time** of the check is the smallest multiple of 10 ps, from 0, at which all three keep the captured value.

  The bench as built carries 10 fF, 60 ps and 30 ps as placeholders until then.
- **Rows:**

  | Row | How it is measured |
  |---|---|
  | Clock-to-output delay, rising and falling | the data arrives early |
  | Mean clock-to-output delay | (rising + falling) / 2: the one row the speed task improves |
  | Setup check | the delay with the data only a short fixed time before the clock, divided by the early-data delay: at most 10 % slower |
  | Hold check | the output is still right when the data changes a short fixed time after the clock |
  | Energy per clock cycle | the supply power averaged over the pattern |
  | Leakage | the supply current in the quiet stretch |
  | Clock pin capacitance | the charge drawn from the clock source per edge |
  | Cell width, which is the area at a fixed row height | estimated from the sizes (below); not simulated |

  A true setup time is a search of many simulations per design; the 10 % check answers pass or fail from one simulation,
  with the criterion a library's own characterisation commonly uses. The two short fixed times, the slope and the load
  are set after the first check. The clock pin capacitance and the hold check are rows so that a design cannot buy speed
  by loading the clock or by losing data.
- **The two tasks: one set of limits, two goals** (user, 2026-10-11: "change speed leaning to maximize speed run from
  scratch and train the graph gps model. And new runs to minimize power consumtion, compare the scratch run with trained
  models power minimizing performance", then "also the trained model's speed maximizing performance"). Both tasks hold
  the same cell, bench and limits. They differ in one thing, the row that keeps improving after a pass
  (`direction_after_feasible`):

  | Task | Keeps improving | Printed beside it |
  |---|---|---|
  | Speed, `dffrx1` | the mean clock-to-output delay, as low as it goes | the library's X4 sizes on the same bench |
  | Power, `dffrx1_t1` | the energy per clock cycle - the supply power at the bench's clock rate - as low as it goes | the library's X2 sizes on the same bench |
  | Power at a speed between the X2's and the X4's, `dffrx1_t2` | the energy per clock cycle, as low as it goes | the library's X2 and X4 sizes on the same bench |

  The limits come from the library's own cells, simulated once each on the bench, by a rule fixed here before any run:
  every delay at most the X2's plus 2 % (at least as fast as the library's X2); energy, leakage, clock pin capacitance
  and estimated area at most the X4's plus 2 % (inside the X4's budget); the setup and the hold check pass. So the X2
  and the X4 are two designs known to pass, the X1 start fails the delay rows, and a run must first find a pass and then
  improve its goal. The third task (user, 2026-10-11: "add :minimize power at the library X4's speed instead of the
  X2's, run from scratch and from the both-goals model", then suggestion 1 taken) is the power task with one limit
  moved: every delay at most halfway between the X2's and the X4's. At the X4's own speed the X4 might have been the
  only design to pass inside its own budget; halfway is still a limit no model was trained with, the X4 passes it with
  room and the X2 does not. The rank rule on random designs and this step's 2-10 % rule
  are not used for the cell. The reward is
  the page's, as for every run of the plan (objective and margin weights 1). The X2 and X4 sizes must fit the 22 widths;
  that is checked at the build, and a size that does not fit is replaced by the nearest that does, and said.
- **Area before layout:** height is fixed, so area = 1.71 um x width, and the width follows the number of gate columns:
  each transistor folded into fingers of at most 400 nm (NMOS) or 630 nm (PMOS), columns = the larger of the two rows'
  finger counts, width = 0.25 um + 0.29 um x columns. Checked against the real outlines of 513 cells of the library:
  typical error 9 % (26 % for total transistor width alone); on the DFFR family 17-23 % high with the right trend. It
  moves in steps: a wider transistor costs nothing until it needs one more finger. The workbench measures it since
  record 7.308: a Probes row with the source `size_estimate` and the formula
  `0.253u + 0.288u * larger(fingers("mn*", 400n), fingers("mp*", 630n))`, worked out per design from its own sizes
  (X1 4.86 um, X2 5.44 um, X4 6.59 um; times 1.71 um = 8.3, 9.3 and 11.3 um2 - the estimate, not the real outlines).
- **First check, before any training:** the bench on the library's post-layout netlist of DFFRX1 (the same 32
  transistors with 120 wiring capacitors and 157 wiring resistors) and on the schematic, both at the library's slow
  corner (0.9 V, 125 C), against the 0.38 ns clock-to-output delay the library states there for a 10 fF load and an 8 ps
  input slope: whether the bench measures as the library does, and how optimistic a simulation before layout is. Two
  Spectre runs. A resized cell has no layout, so the runs see pre-layout numbers only.
- **Runs (10, GraphGPS, 800 designs each) and one model trained between them** (user, 2026-10-11: "please train the
  model with both power and speed scratch runs then run them", then the third task, then suggestion 2 taken: its two
  runs with three seeds each):

  | Run | Task | Starts from | Name |
  |---|---|---|---|
  | 1 | Speed | a fresh network | `tx2-dffr-speed-scratch` |
  | 2 | Power | a fresh network | `tx2-dffr-power-scratch` |
  | - | both | the both-goals model: one network trained offline on the recorded designs of runs 1 and 2, each design with the reward of its own task; no simulation, no re-scoring | `tx-offline-dffr-both` |
  | 3 | Power | the both-goals model, fine-tuned | `tx2-dffr-power-both` |
  | 4 | Speed | the both-goals model, fine-tuned | `tx2-dffr-speed-both` |
  | 5 | Power at the in-between speed | a fresh network, seeds 0, 1 and 2 | `tx2-dffr-powermid-scratch`, `-s1`, `-s2` |
  | 6 | Power at the in-between speed | the both-goals model, fine-tuned, seeds 0, 1 and 2 | `tx2-dffr-powermid-both`, `-s1`, `-s2` |

  Run 3 against run 2 and run 4 against run 1: the trained model against starting over, on each goal it was trained
  for. Runs 3 and 4 against each other: the same network asked for two goals. **Run 6 against run 5, three runs each:
  the trained model against starting over on a task it has not met.** The multi-target model and the probe of this step
  are not among the cell's runs (they stay for the three analog circuits).
- **What each comparison can show.** Runs 1 to 4 can show that one model holds both goals of the cell and gives each on
  request - if the first designs of run 3 carry less energy and those of run 4 less delay, the model reads the goal it
  is given. They cannot show help on something new: the both-goals model has already seen the designs of both tasks, so
  being ahead of a fresh network at the start is expected and is close to continuing the scratch run. Runs 5 and 6 are
  the test of a changed target: the model was never trained with that speed as its limit. One thing to say with the
  result: the speed run will have simulated designs in that fast region, so the model has seen sizes that pass the new
  limit, though never scored for power under it. If no run of either kind finds a pass, the task says nothing.
- **Judged by** (fixed before any result; the goal row, over passing designs only):
  - the best passing value of the goal row after 100, 200, 400 and 800 designs;
  - its median over the passing designs among the first 100 the network proposes itself, and in the last third;
  - the share of passing designs, early and late;
  - the design at which the fine-tuned run first reaches the scratch run's best value of all 800;
  - runs 3 and 4 side by side over their first 100 own designs: the median energy and the median delay of each;
  - for runs 5 and 6 also the first passing design and the share of passes, as section 5 judges a loaded model.

  Proposed bars, not yet confirmed by the user: the trained model **helps** when it reaches the scratch run's final best
  value within 400 designs; it **ends as well** when its own final best is no more than 2 % worse. For runs 5 and 6,
  with three seeds each: the scratch value is the median of the three scratch runs, and the model helps when at least
  two of its three runs reach it within 400 designs; every seed is printed. Runs 1 to 4 have one seed each: there a
  difference of a few percent says nothing.
- **Preparation:** the two Spectre runs of the first check; the simulations of the library's X1, X2 and X4 sizes
  that the bench's rule above needs (a sweep over the five loads, then over the setup and the hold time: some tens of
  short simulations, none of them a run) and from which the limits of all three tasks follow; a 64-design Calibration
  for each task (192 designs). The area row is built first (suggestion 6 taken; section 8, item 9).
- **Limits:** schematic only (no wiring inside the cell); one load and one input slope; existing work on learned
  standard-cell sizing has not been surveyed.

#### 6.2.2 Second part: OTA5t, RING3 and LDO1, built like the logic cell's part (30 runs)

**Changed 2026-10-11 04:31 (user: "for the analog spec change. I want something similar to the stdcell. with changed
spec to see if that spec converge faster in trained network"; record 7.312).** Until then: one new-target copy per
circuit and the four arms at the top of 6.2 (scratch, the old-target model, a multi-target model, a probe); nothing of
that was saved or run. Now, per circuit, three tasks - Save as copies of the saved task with the same cell and bench:

| Circuit | Goal 1 (`_t1`) | Goal 2 (`_t2`) | Changed spec, no model trained with it (`_t3`) |
|---|---|---|---|
| OTA5t | the unity-gain bandwidth, as high as it goes | the power, as low as it goes | the power, with the bandwidth at least 120 MHz (saved task: 100 MHz) |
| RING3 | the power at 0.95-1.05 GHz (the saved band) | the power at 1.33-1.47 GHz | the power at 1.14-1.26 GHz |
| LDO1 | the quiescent current | the PSRR at 10 kHz | the quiescent current, with the PSRR at 10 kHz at most -33 dB (saved task: -30 dB) |

- Every limit not named stays as saved, except on LDO1: all three of its tasks take PSRR at high frequency at most
  -1.7 dB instead of -3 dB. Of 2,400 recorded designs 3 pass the saved limit and 119 this one; with the saved limit no
  run finds a pass (step 1: none in 1,600 designs) and a goal that only counts after a pass says nothing.
- An oscillator has no direction of "speed": RING3's two goals are the same goal at two frequencies, and its changed
  spec is a third frequency between them.
- The limits were read off every recorded design of each circuit before any of these runs (`choose_targets.py`): the
  goal tasks are passed by 70 % (OTA5t), 15 % and 2.4 % (RING3) and 5 % (LDO1) of them, the changed specs by 9.2 %,
  6.3 % and 2.3 %. OTA5t has little room: its passing designs lie between 0.26 and 0.31 mW and between 100 and
  132 MHz, so a difference in power will be hard to see there.
- **Runs per circuit (10, GraphGPS, 800 designs, the run settings of step 1's GraphGPS run of the circuit):** goal 1 and
  goal 2 from a fresh network; the both-goals model, one network trained offline on the recorded designs of those two
  runs, each design with the reward of its own task (no re-scoring, no simulation); goal 2 and goal 1 from that model;
  the changed spec from a fresh network and from the model, seeds 0, 1 and 2 each. Names: `tx2-<circuit>-<label>-scratch`,
  `-both`, with `-s1`, `-s2`; labels `speed`, `power`, `powermid` (OTA5t), `p1000`, `p1400`, `p1200` (RING3), `iq`, `psrr`,
  `iqmid` (LDO1); the models `tx-offline-<circuit>-both`.
- **Judged as the logic cell's runs** (6.2.1): the best passing value of the goal row after 100, 200, 400 and 800
  designs, the design at which the run from the model first reaches the from-scratch run's best value of all 800, the
  share of passing designs early and late, and for the changed spec the first passing design, three seeds each.
- **Preparation:** nine Save as copies with their baselines, a 64-design Calibration each (576 designs).

### 6.3 Step 3: SAC against Bayesian optimization (9 new runs)

- **Circuit:** the AgenticSizing LDO (27 variables, 5 rows): the one circuit where the paper gives numbers for a Bayesian
  optimizer that worked (4 of 5 runs, about 524 simulations).
- **Runs:** SAC = GT from scratch, five repeats (seed 0 is step 1's run); Bayesian optimization, five repeats. No
  random-search arm (user).
- **Fairness:** the same first 9 designs per seed (the start and the 8 warm-up designs), the same score (the run's
  reward), 800 designs, 4 simulated at a time.
- **Judged by:** how many of five runs find a pass, the first passing design and the clock time to it, passes of 800,
  the best score against the number of designs.
- The Bayesian optimizer exists since record 7.304 (section 8, item 1): `run.optimizer: "bayes"` in the run's
  configuration file; its full regression and browser batch are owed before this step starts.

### 6.4 Step 4: the same circuit in a second PDK (9 runs, 3 probes)

- **Build:** OTA5t, RING3 and LDO1 with the second foundry's 1.8 V transistors: the same schematic and bench, the size
  ranges as the same multiples of the minimum size, one Spectre check per bench (it converges, the probes compute), no
  size tuned (the user's rule of 7.295). The limits of each ported task come from a fixed rank rule on its own 64 random
  designs (as the held-out cascodes' goals, record 7.262), before any model sees it: a 0.18 um circuit cannot meet
  numbers set for 45 nm.
- **Runs per circuit, on the ported task:**

  | Run | Starts from |
  |---|---|
  | Scratch | a fresh GraphGPS network |
  | Fine-tune, relative sizes | a gpdk045 model of the circuit that reads sizes relative to the PDK's minimum, with the device numbers |
  | Fine-tune, absolute sizes | the same model made with sizes in micrometres and no device numbers |
  | Probe | the relative-sizes model, no training |

  Both start models are trained offline from the same recorded gpdk045 designs of the circuit, so the size input is the
  only difference between them: that difference is what the PDK-relative inputs are worth.
- **Limit:** the simulator machine holds two PDKs, so the device numbers have four transistor models to learn from.

### 6.5 Step 5: the general model on an unseen circuit in the known PDK (2 runs, 1 probe)

- **The general model:** GraphGPS, new inputs, trained offline on the recorded designs of OTA5t, OTA7t width, RING3, VCO,
  LDO1, LDO2 and the folded cascode, plus step 4's runs in the second PDK. Left out: the telescopic cascode and every
  AgenticSizing circuit, the published ones and the rebuilt ones of 7.295.
- **Runs on `mscr_otatc`:** GraphGPS from scratch, GraphGPS fine-tuned from the general model, a probe.
- **Mark to reach:** with the old inputs GraphGPS had 59 % early passes from its general model against 23 % from scratch
  on this circuit, 100 % late passes both ways (GT: 73 % against 8 %).
- **Why before step 6:** if the general model helps here and not on AgenticSizing, the model is sound and those circuits
  are too different; if it does not help here either, step 6 says nothing about AgenticSizing.

### 6.6 Step 6: the same general model on the AgenticSizing circuits (4 runs, 4 probes)

- **Runs per circuit:** a probe, and a fine-tune run from the general model, against step 1's GraphGPS from-scratch runs
  (five on the LDO).
- **Reported beside the paper** (arXiv 2609.25873; a run of theirs succeeds when a design meets every spec within its
  clock budget; their simulation counts are averages over the successful runs):

  | Circuit | The paper's LLM agent | Its time for one run | Budget | Its best other method |
  |---|---|---|---|---|
  | LDO | 4 of 5, 64-103 simulations (79 on average) | 2 h 37 min | 4 h | Bayesian 4 of 5, about 524 |
  | Reference | 4 of 5, about 23 | 1 h 11 min | 4 h | differential evolution 5 of 5, about 936 |
  | Amplifier | 4 of 5, 11-29 | 1 h 38 min | 2 h | none passed |
  | System | 3 of 5, 83-94 (90 on average) | 4 h 59 min | 6 h | none passed |

  The counts are the paper's tables (reference 4-45 simulations, system runs of 94, 83 and 92); its running text says
  "64-94" for the system and its abstract "83 on average", which the tables contradict. Checked on the paper's page by
  two sessions on 2026-10-10.

  Both numbers are reported for our runs: simulations to the first pass and clock time to the first pass. The agent
  needs few simulations and a long time; a run of ours is the opposite.

## 7. Round 2: repeats, only where round 1 shows an effect

- **Step 2:** a second new target per circuit, in the other direction (9 runs, 3 probes, about 2.5 h for the three analog
  circuits); for the logic cell its runs 1 to 4 again with a second seed.
- **Step 6:** repeats so the result reads "k of 5" as the paper's: five trials on the LDO and the reference, three or
  five on the amplifier and the system (20 or 28 runs, at most about 7 or 12 h; a repeat stops at its first passing
  design, `stop_at_first_feasible`). Three or five is decided when round 1 is in.

## 8. To prepare first

No simulation except where said.

1. **A Bayesian optimizer** outside the optimizer package (the source digest stays): the same environment, reward,
   lanes and recording as a SAC run; a trust-region Gaussian-process method for some tens of variables; written with
   what the environment holds (numpy, torch, PyG; no package is added to the pinned environment); checked on standard
   test functions before any simulation. **Built 2026-10-10, record 7.304:** `run.optimizer: "bayes"` in a configuration
   file, `gator_workbench/bayes.py` (TuRBO-1, one design per free lane); its checks on test functions are in that record.
   Step 3 needs a frozen copy of the code that holds it (the copy step 1 runs from does not).
2. **Re-scoring recorded designs under new limits** in offline training: `pretrain` re-scores only upper limits of
   "at most" rows today (`relabel_upper`); the multi-target model needs any limit and several target sets per source.
   **Built 2026-10-11, record 7.312:** `relabel_targets` in a pretrain request.
   Workbench only.
3. **The three ports** to the second foundry's PDK, with tasks, baselines and Calibrations (3 Spectre checks, then
   3 x 65 designs).
4. **The three new-target copies** of the core tasks (their baselines are automatic; 3 x 64 Calibration designs).
5. **The amplifier's second starting design** (user: "find a starting point further away from target"): 64 random
   designs of `agentic_fc_pub`; of those that still work as an amplifier (every row measurable) the lowest-scoring one
   becomes the start of a new task, fixed before any network sees it; the number of rows it misses is recorded (65 designs).
6. **Offline training** (CPU only). It learns from designs that were already simulated and recorded - a record holds
   the sizes and what was measured, so any network can be trained on it afterwards - which is why it needs none of this
   plan's from-scratch runs. `pretrain --audit-only` on each pool first (archive hashes, the exact reward reproduction
   under today's rule, one reward setting, the counts of usable designs). **In preparation:** the three multi-target
   models and the two start models per ported circuit, each from the recorded gpdk045 designs of its circuit. **After
   step 4, not before:** the general model, because its pool also holds step 4's runs in the second PDK. Each model
   with the offline checks and a recorded review.
7. **Before the long queue:** the backend on 8765 runs today's code since its restart of 2026-10-10 19:09 (record
   7.302; the process of 15:48 predated the committed conditions template and PDK facts of 7.295, so no task of the
   second PDK was to be saved through it) - after any later change of the backend's code it is restarted again before a
   port is saved; Virtuoso restarted; the PDKs read again for the two new component rules of 7.298; the
   frozen copy of HEAD taken.
8. **Tools that exist** (the queue session's review folder `artifacts/local/reviews/encoder-comparison-2026-10-07/`,
   reused, changed only with that session's word): `queue_cd.sh`, `compare_runs.py`; for the four `_pub` tasks
   `make_configs_asz.py` with `ASZ_SUFFIX=_pub`, `ASZ_INPUTS=transferable` and `ASZ_VOCABULARY=families`, and
   `calibrate_asz.py` / `compare_asz.py` with the suffix. Its prepared `ASPUB-*` configurations use the standard inputs:
   they are not step 1 as they stand. Its `stage_pub.sh` (the superseded 24-run queue) refuses to start.
9. **The logic cell, first of all for step 2** (6.2.1): the copy of `gsclib045/DFFRX1` in the user's own library and its
   bench, built by script as the MScR circuits were (done, record 7.307); the workbench addition for the area row - a
   Probe that measures the sizes (done, record 7.308; it is live after the next backend restart and frozen copy); the
   first check (two Spectre runs);
   the three reference simulations of the library's X1, X2 and X4 sizes, from which the limits follow; the three
   tasks `dffrx1`, `dffrx1_t1` and `dffrx1_t2`, each with a 64-design Calibration (192 designs, beside the library-cell
   simulations of the bench's rule); after the two scratch runs the
   both-goals model, trained offline on their recorded designs (item 6's checks; CPU only). The cell, the bench and the
   area row exist; no task is saved and nothing is simulated yet.

## 9. Budget and time

| Step | Runs | Probes | Other designs | Designs | Time |
|---|---|---|---|---|---|
| 1 | 20 | - | 65 (amplifier start) | 16,065 | about 7 h |
| 2 | 40 | - | 777 | 32,777 | about 7.8 h |
| 3 | 9 | - | - | 7,200 | about 1.7 h |
| 4 | 9 | 3 | 195 | 8,295 | about 2.5 h |
| 5 | 2 | 1 | - | 1,900 | about 0.75 h |
| 6 | 4 | 4 | - | 4,400 | about 2 h |
| **Round 1** | **84** | **8** | **1,037** | **70,637** | **about 21.7 h** |

Step 2 as changed on 2026-10-11 (6.2.2): the logic cell's 10 runs and 192 Calibration designs, and the three analog
circuits' 30 runs, 9 baselines and 576 Calibration designs (about 6 h of the first Virtuoso session; the logic cell runs
beside them in the second). Not in the table: the conditional runs of step 1 (800 designs each), round 2 (step 2: 8,295, and 3,200 for the logic cell; step 6: at most 16,000 or
22,400), offline training (CPU hours, no simulation). Times come from the recorded runs per 800 designs: OTA5t 9-13 min,
RING3 10-24, LDO1 10-16, VCO 36-99, telescopic cascode 17-25 (the upper values are from days the simulator machine ran
slowly); for the published circuits from the rebuilt cells of 7.295 (LDO and reference 10-13 min, system about 27,
amplifier 37-55) - their own 12-design runs took 1.8 to 2.9 s per design on one lane, so these are upper figures. The logic cell is
unmeasured: about 10 min per 800 designs is assumed, 1.8 h for its part of step 2 (10 runs, 192 designs; the library-cell
simulations of its bench rule are single short simulations and are not counted as designs).

## 10. Order and gates

Preparation -> step 1 -> step 2, the logic cell first and then the three analog circuits (user, 2026-10-10) -> step 3 ->
step 4 -> the general model trained offline -> steps 5 and 6 -> round 2. Step 3 depends only on step 1's LDO run and
item 1 of section 8, so it can move if the queue needs it. In step 2 the logic cell needs none of step 1's models (it
makes its own ten runs, with an offline training between the second and the third) and of section 8 only item 9; the three analog circuits need step 1's GraphGPS
models; the general model of steps 5 and 6 needs step 4's runs. One run at a
time on the one Virtuoso session; Check now before and after every run; no test suite or browser batch on the machine
while the queue runs (the stall of 2026-10-10). Virtuoso still grows by about 235 KB per simulated design (measured
after record 7.294's fix), about 12 GB over round 1: it is restarted at three step boundaries - before step 1, before
step 2 and before step 4 - so no session takes more than about 4.5 GB of growth, with the bridge loaded again, the
nonce-cache setting applied and Check now on the tasks after each restart. Each step's start is the user's word.

## 11. What is expected, written before any result

- **Step 1:** no network difference beyond what one seed can show; the new inputs within the rule on OTA5t and the VCO.
- **Step 2:** the multi-target model helps; the old-target model helps only for a small shift. On the logic cell the both-goals
  model has seen both tasks, so it should be ahead of a fresh network from its first designs on each goal; what is open
  is whether one network keeps the two goals apart - whether its power run and its speed run propose different designs
  from the start. On the task it has not met, the power goal at the in-between speed, it should find a pass sooner than a
  fresh network, because the speed run has been in that fast region; whether a fresh network finds a pass there within
  800 designs at all is open.
- **Step 3:** SAC ahead in passes of 800; which finds the first pass sooner is open.
- **Step 4:** most likely on OTA5t, which already runs at 1.8 V in gpdk045; least likely on RING3.
- **Step 5:** the mark of 59 % against 23 % is reached or nearly.
- **Step 6:** a gain over scratch is plausible on the LDO and the amplifier, unlikely on the reference (no similar
  circuit in the pool, and its temperature row) and on the system. Reaching the agent's simulation counts is a stretch.

## 12. Decided, and open

Decided by the user in the conversation of 2026-10-10: keep LDO1, not LDO2 ("keep LDO1"); "Keep the VCO_lin also" (read
as `mscr_vco_lin_c`, the task the six-circuit study used, and said so); "On new runs only use the graphgps and gt"; the
optimizer comparison on the AgenticSizing LDO ("use agenticsizing LDO"); "delete random search in step 2"; "add a step to
use trained new general network on one unseen circuit see how it works compared with scratch"; "in step 5 use
GraphGPS", "and step 6 also use graph GPS", "2 3 4 also use graphGPS", then "step 2 use gt"; for the amplifier "find a
starting point further away from target"; for LDO1 "rename the task and run both on it" (`ldo1_relaxed`, section 3).
Stage B (the same circuit again from its own trained network) is left out on
the advice given, with the continuation run of 6.1 in its place.

Added later on 2026-10-10 (session "Trained model spec change topology proof", record 7.305): a logic cell in the
new-target step ("Can you use it for standard cell optimization like for one logic cell to modify its ppa?", "yes add
DFFRX1 for step 3 as a task"), then "make the stdcell plan first part of the step 3(the spec change) and exchange current
plan step 2 with step 3 so after step 1 it runs stdcells first". **The steps were renumbered by that. Every quote above
keeps the number its step had when it was said: "step 2" in them is SAC against Bayesian optimization, now step 3, and
"3" is the new targets, now step 2.**

On 2026-10-11 (same session and record) for the logic cell: "change speed leaning to maximize speed run from scratch and
train the graph gps model. And new runs to minimize power consumtion, compare the scratch run with trained models power
minimizing performance", then "also the trained model's speed maximizing performance" - read as a cross of four runs
(6.2.1): each goal from scratch, and each goal from the model trained for the other one. Then, on those last two runs:
"please train the model with both power and speed scratch runs then run them" - one both-goals model, trained offline
on the two scratch runs, is what runs 3 and 4 start from. Then "add :minimize power at the library X4's speed instead
of the X2's, run from scratch and from the both-goals model": the third task and runs 5 and 6. Then "take 1,2,5,6" of
seven suggestions: the third task's delay limit halfway between the X2's and the X4's (1); runs 5 and 6 with three
seeds each (2); the bench's load, setup time and hold time by a rule on the library's own cells (5); the area row built
first (6). Not taken: a probe of the trained model on each goal (3), the margin bonus off for the cell (4); to state
every result against the library's cells and as pre-layout (7) is done in any case.

Open: three or five repeats on the amplifier and the system in round 2 (after round 1); the library name of the three
ports; for the logic cell the library its copy goes into, the load, the input slope and the two fixed times of its
bench, and the two bars of its judgement (proposed, 6.2.1).

Limits to state with every result: one seed in round 1; the AgenticSizing benches and PDK are ours (the paper publishes
neither), its netlists, ranges and limits are the paper's; the recorded old-input references ran on earlier code
versions (behaviour-identical for these circuits but for the 7.299 rule, hence the control).

## 13. What goes on record

**Where to browse it (record 7.302; user: "Categorize task runs and models in each windows again according to experiment
stages. Older ones not used by the plan goes into a folder").** The Tasks, Runs and RL model windows have one folder per
part of this plan; folder names start with a digit because the windows list folders by name:

| Window | Folders |
|---|---|
| Tasks | 1 Core circuits (steps 1, 2, 4) / 2 AgenticSizing, published netlists (steps 1, 3, 6) / 3 New targets (step 2) / 4 Second PDK ports (step 4) / 5 Unseen circuit (step 5) / 9 Older (not used by the plan) |
| Runs, RL models | 1 Networks with the new inputs (step 1) / 2 New targets (step 2) / 3 SAC against Bayesian (step 3) / 4 Second PDK (step 4) / 5 General model, unseen circuit (step 5) / 6 General model, AgenticSizing (step 6) / 7 Baselines, calibrations, offline models (plan) / 8 References: recorded runs the plan compares with / 9 Older (before the transfer experiment) |

`artifacts/local/reviews/transfer-experiment-2026-10-10/categorize.py` files everything (idempotent; run again whenever
runs appear). It files the plan's runs by their experiment names, which are therefore fixed here: `tx1-<circuit>-<gt|gps>`
(with `-s<seed>`, `-control`, `-cont`, or `-r` for the rerun of a run a fault of the machine ended),
`tx2-<circuit>-<target>-<scratch|old|multi|probe>` (the logic cell as `dffr`: `tx2-dffr-speed-scratch`, `tx2-dffr-power-scratch`, then `tx2-dffr-power-both` and `tx2-dffr-speed-both` from the offline model `tx-offline-dffr-both`),
`tx3-asz-ldo-<sac|bo>-s<seed>`, `tx4-<circuit>-<scratch|rel|abs|probe>`, `tx5-otatc-<scratch|general|probe>`, `tx6-asz-<circuit>-<general|probe>`,
`tx-offline-*` and `tx-prep-*`. The recorded runs the general model trains on stay in "9 Older" until its request is
frozen.

**The renumbering of record 7.305 is applied** (2026-10-10 23:5x, by the session that owns the folders, on that
record's request): the table and the run names above are the new ones. `categorize.py` carries them and was run - the
folders of the old numbering held no run, model or new-target task yet, so nothing but names moved. It files the logic
cell's first task (a name beginning `dffr`) beside the core circuits and its new-target copy (the same name with
`_t<number>`) among the new targets. No run of step 2 or 3 exists yet.


This plan; record 7.301; per step the configurations, compatibility proofs, queue log, `results-<step>.md` / `.json` and
a record entry, in `artifacts/local/reviews/transfer-experiment-2026-10-10/`; the definitions of the new tasks in
`~/mscr_circuits`; the offline models' `pretraining` blocks; the Bayesian optimizer's own record.
