# Plan: the transfer experiment - networks with the new inputs, SAC against Bayesian optimization, new targets, a second PDK, one general model on unseen circuits

Written 2026-10-10 (Europe/London), record 7.301, session "Encoder experiment plan setup". User: "let us discuss and set
up new experiment plan: read encoder run plan revision, assume all changes are landed. Give an overall plan of the
experiment. try to reduce the number of circuits ... Things to compare if not already: different network on all circuits,
different opt on one circuit from scratch (sac bayesian), different spec settings on three circuits (so I can make a
circuit with different target), test pdk transfer on two/three circuits, and then use general trained network to test on
agentic sizing for hopefully better performance."; settled in the conversation that followed (section 12 lists each
decision in the user's words), then "yes save the plan now".

Status: **plan only; nothing built, no task changed, no run queued.** Every simulation waits for the user's word.

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
| 2 | Is SAC better than Bayesian optimization, from scratch? | AgenticSizing LDO | GT (SAC) | 9 | about 1.7 h |
| 3 | Does a trained model reach a new target faster than starting over? | OTA5t, RING3, LDO1 | GraphGPS | 9 + 3 probes | about 2.5 h |
| 4 | Does a gpdk045 model help on the same circuit in a second PDK? | OTA5t, RING3, LDO1, ported | GraphGPS | 9 + 3 probes | about 2.5 h |
| 5 | Does one general model beat starting over on an unseen circuit in the known PDK? | telescopic cascode | GraphGPS | 2 + 1 probe | about 0.75 h |
| 6 | Does the same general model beat starting over on the AgenticSizing circuits? | 4 AgenticSizing | GraphGPS | 4 + 4 probes | about 2 h |

Round 1: **53 runs and 11 probes, about 46,200 simulated designs, about 16.5 h** of simulation (section 9). The times of
the published and the ported circuits are estimates until their first runs.

## 2. Words used

- **Design:** one set of sizes, simulated once. A run is 800 designs.
- **Pass:** a design that meets every Specs row.
- **From scratch:** a fresh network, trained on this one task only.
- **Fine-tune:** start from a trained network and keep training on the new task.
- **Probe:** a trained network proposes 300 designs with no further training (mode `frozen`, sampled actions).
- **General model:** one network trained offline on the recorded designs of many circuits; no new simulation.
- **Seed:** the number that fixes a run's random choices; a repeat is the same run with another seed.

## 3. Circuits: from twelve to eight with new runs

| Group | Circuit, task | Why |
|---|---|---|
| Core, gpdk045 | OTA5t, `mscr_ota5t` | 9-13 min per 800 designs; 95 % late passes for every network; built on the PDK's 1.8 V transistors, so the cleanest port |
| Core, gpdk045 | RING3, `mscr_ring3` | from scratch only 10-34 % late passes: room to show a gain |
| Core, gpdk045 | LDO1 at HF PSRR <= -3 dB, `ldo1_relaxed` (key `graphgps_ldo1`) | 0 to 3 passes of 800 from scratch for every network; 34 to 55 with a general model |
| Core, gpdk045 | VCO, `mscr_vco_lin_c` | kept on the user's word; 36-99 min a run; step 1 only |
| Unseen, gpdk045 | telescopic cascode, `mscr_otatc` | step 5; out of every training pool of this plan |
| AgenticSizing, second foundry's 0.18 um PDK | `agentic_ldo_pub`, `agentic_bgr_pub`, `agentic_fc_pub`, `agentic_sys_pub` (7.300) | the paper's netlists, size ranges and limits; steps 1, 2 and 6 |
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
| `agentic_fc_pub` | 29, 19 | 11 of 11 | the published start passes on our bench, so "simulations to the first pass" would be 1: a second starting design is made (section 8, item 5) and every run of this plan on the amplifier uses it |
| `agentic_sys_pub` | 55, 50 | 2 of 6 | - |

## 4. Fixed settings

- **Networks:** GT and GraphGPS only (user). Step 1 runs both; step 2 uses GT; steps 3 to 6 use GraphGPS.
- **Network inputs:** every new model is made with Network inputs **Transferable** (`spec_input` set, `size_features`
  pdk_relative, `device_model_features` true) and the family component list. Steps 3 to 6 need them: a model with the old
  inputs loads only on a task with the same spec names and reads sizes in micrometres. One arm of step 4 differs on
  purpose (absolute sizes, no device numbers).
- **A run:** 800 designs; the presets' training numbers (learning rate 1e-3, initial alpha 0.01, 8 updates per design,
  gamma 0, batch 8, warm-up 8, replay 10,000, episode 4); the page's reward; the lanes each task ran with before (4).
- **A loaded run:** the same numbers, target-only replay, the loaded temperature carried (the recipe of record 7.262).
- **Seeds:** 0 for every single run; repeats take seeds 1 to 4.
- **One code version:** a frozen copy of HEAD taken when round 1 is frozen; the optimizer digest (`94e7dd4f...` today)
  is checked before every run. Nothing in `src/analog_optimizer/` changes for this plan.

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
  four are step 2's SAC runs).
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
- **Produces:** the GraphGPS models of OTA5t, RING3 and LDO1 that step 3 starts from, and the from-scratch side of step 6.

### 6.2 Step 2: SAC against Bayesian optimization (9 new runs)

- **Circuit:** the AgenticSizing LDO (27 variables, 5 rows): the one circuit where the paper gives numbers for a Bayesian
  optimizer that worked (4 of 5 runs, about 524 simulations).
- **Runs:** SAC = GT from scratch, five repeats (seed 0 is step 1's run); Bayesian optimization, five repeats. No
  random-search arm (user).
- **Fairness:** the same first 9 designs per seed (the start and the 8 warm-up designs), the same score (the run's
  reward), 800 designs, 4 simulated at a time.
- **Judged by:** how many of five runs find a pass, the first passing design and the clock time to it, passes of 800,
  the best score against the number of designs.
- GATOR has no Bayesian optimizer today (section 8, item 1).

### 6.3 Step 3: new targets on a known circuit (9 runs, 3 probes)

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

- **Step 3:** a second new target per circuit, in the other direction (9 runs, 3 probes, about 2.5 h).
- **Step 6:** repeats so the result reads "k of 5" as the paper's: five trials on the LDO and the reference, three or
  five on the amplifier and the system (20 or 28 runs, at most about 7 or 12 h; a repeat stops at its first passing
  design, `stop_at_first_feasible`). Three or five is decided when round 1 is in.

## 8. To prepare first

No simulation except where said.

1. **A Bayesian optimizer** outside the optimizer package (the source digest stays): the same environment, reward,
   lanes and recording as a SAC run; a trust-region Gaussian-process method for some tens of variables, four designs a
   round; written with what the environment holds (numpy, torch, PyG; no package is added to the pinned environment);
   checked on standard test functions before any simulation. A record of its own.
2. **Re-scoring recorded designs under new limits** in offline training: `pretrain` re-scores only upper limits of
   "at most" rows today (`relabel_upper`); the multi-target model needs any limit and several target sets per source.
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

## 9. Budget and time

| Step | Runs | Probes | Other designs | Designs | Time |
|---|---|---|---|---|---|
| 1 | 20 | - | 65 (amplifier start) | 16,065 | about 7 h |
| 2 | 9 | - | - | 7,200 | about 1.7 h |
| 3 | 9 | 3 | 195 | 8,295 | about 2.5 h |
| 4 | 9 | 3 | 195 | 8,295 | about 2.5 h |
| 5 | 2 | 1 | - | 1,900 | about 0.75 h |
| 6 | 4 | 4 | - | 4,400 | about 2 h |
| **Round 1** | **53** | **11** | **455** | **46,155** | **about 16.5 h** |

Not in the table: the conditional runs of step 1 (800 designs each), round 2 (step 3: 8,295; step 6: at most 16,000 or
22,400), offline training (CPU hours, no simulation). Times come from the recorded runs per 800 designs: OTA5t 9-13 min,
RING3 10-24, LDO1 10-16, VCO 36-99, telescopic cascode 17-25 (the upper values are from days the simulator machine ran
slowly); for the published circuits from the rebuilt cells of 7.295 (LDO and reference 10-13 min, system about 27,
amplifier 37-55) - their own 12-design runs took 1.8 to 2.9 s per design on one lane, so these are upper figures.

## 10. Order and gates

Preparation -> step 1 -> steps 3 and 4 -> the general model trained offline -> steps 5 and 6 -> round 2. Step 2 runs any time after step 1's LDO run and item 1 of
section 8. Step 3 needs step 1's GraphGPS models; the general model of steps 5 and 6 needs step 4's runs. One run at a
time on the one Virtuoso session; Check now before and after every run; no test suite or browser batch on the machine
while the queue runs (the stall of 2026-10-10). Virtuoso still grows by about 235 KB per simulated design (measured
after record 7.294's fix), about 11 GB over round 1: it is restarted at three step boundaries - before step 1, before
step 3 and before step 4 - so no session takes more than about 4 GB of growth, with the bridge loaded again, the
nonce-cache setting applied and Check now on the tasks after each restart. Each step's start is the user's word.

## 11. What is expected, written before any result

- **Step 1:** no network difference beyond what one seed can show; the new inputs within the rule on OTA5t and the VCO.
- **Step 2:** SAC ahead in passes of 800; which finds the first pass sooner is open.
- **Step 3:** the multi-target model helps; the old-target model helps only for a small shift.
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

Open: three or five repeats on the amplifier and the system in round 2 (after round 1); the library name of the three
ports; how the Bayesian optimizer joins a run (item 1 of section 8).

Limits to state with every result: one seed in round 1; the AgenticSizing benches and PDK are ours (the paper publishes
neither), its netlists, ranges and limits are the paper's; the recorded old-input references ran on earlier code
versions (behaviour-identical for these circuits but for the 7.299 rule, hence the control).

## 13. What goes on record

**Where to browse it (record 7.302; user: "Categorize task runs and models in each windows again according to experiment
stages. Older ones not used by the plan goes into a folder").** The Tasks, Runs and RL model windows have one folder per
part of this plan; folder names start with a digit because the windows list folders by name:

| Window | Folders |
|---|---|
| Tasks | 1 Core circuits (steps 1, 3, 4) / 2 AgenticSizing, published netlists (steps 1, 2, 6) / 3 New targets (step 3) / 4 Second PDK ports (step 4) / 5 Unseen circuit (step 5) / 9 Older (not used by the plan) |
| Runs, RL models | 1 Networks with the new inputs (step 1) / 2 SAC against Bayesian (step 2) / 3 New targets (step 3) / 4 Second PDK (step 4) / 5 General model, unseen circuit (step 5) / 6 General model, AgenticSizing (step 6) / 7 Baselines, calibrations, offline models (plan) / 8 References: recorded runs the plan compares with / 9 Older (before the transfer experiment) |

`artifacts/local/reviews/transfer-experiment-2026-10-10/categorize.py` files everything (idempotent; run again whenever
runs appear). It files the plan's runs by their experiment names, which are therefore fixed here: `tx1-<circuit>-<gt|gps>`
(with `-s<seed>`, `-control` or `-cont`), `tx2-asz-ldo-<sac|bo>-s<seed>`, `tx3-<circuit>-<target>-<scratch|old|multi|probe>`,
`tx4-<circuit>-<scratch|rel|abs|probe>`, `tx5-otatc-<scratch|general|probe>`, `tx6-asz-<circuit>-<general|probe>`,
`tx-offline-*` and `tx-prep-*`. The recorded runs the general model trains on stay in "9 Older" until its request is
frozen.


This plan; record 7.301; per step the configurations, compatibility proofs, queue log, `results-<step>.md` / `.json` and
a record entry, in `artifacts/local/reviews/transfer-experiment-2026-10-10/`; the definitions of the new tasks in
`~/mscr_circuits`; the offline models' `pretraining` blocks; the Bayesian optimizer's own record.
