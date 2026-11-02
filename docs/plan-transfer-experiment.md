# Plan: the transfer experiment - networks with the new inputs, new targets (a logic cell first), SAC against Bayesian optimization, a second PDK, one general model on unseen circuits

Written 2026-10-10 (Europe/London), record 7.301, session "Encoder experiment plan setup". User: "let us discuss and set
up new experiment plan: read encoder run plan revision, assume all changes are landed. Give an overall plan of the
experiment. try to reduce the number of circuits ... Things to compare if not already: different network on all circuits,
different opt on one circuit from scratch (sac bayesian), different spec settings on three circuits (so I can make a
circuit with different target), test pdk transfer on two/three circuits, and then use general trained network to test on
agentic sizing for hopefully better performance."; settled in the conversation that followed (section 12 lists each
decision in the user's words), then "yes save the plan now".

Status checked **2026-10-15, 13:55 Europe/London** (records 7.353, 7.354): **Round 1 and all 24 Round 2 repeats are complete.
Round 3's GraphGPS, CircuitGPS v2 and RGCN source models have each completed 20,000 offline updates and passed qualification.
Round 3 seed 0 is running on both Virtuoso sessions: 14 of 36 arms complete at this snapshot; the journal experiments have not started.**
Completion means the run reached its configured budget or stopping condition; completion alone does not establish feasibility.

| Block | Verified status |
|---|---|
| Round 1, Step 1 | 32 scratch runs complete: 20 original and 12 RGCN; the additional four GT LDO seeds are reused from Step 3. 12 GATv2 runs complete 2026-10-16 18:22 (section 6.1.2, records 7.355, 7.358) |
| Round 1, Steps 2 / 3 / 3b | 40 / 9 / 24 new runs complete; Step 3 also reuses Step 1's GT seed 0 |
| Round 1, Steps 4 / 5 / 6 | 12 runs + 3 probes / 2 runs + 1 probe / 4 runs + 4 probes complete |
| Round 2 | All 24 repeats complete: 15,893 charged attempts and 15,889 simulator launches, including the retained four-attempt BGR preparation failure (section 7) |
| Round 3, offline | GraphGPS, fresh CircuitGPS v2 and RGCN complete and qualified; RGCN's 12 online arms are admitted |
| Round 3, online | Seed 0: all 36 arms complete (2026-10-16 02:32 Europe/London; 22,800 evaluations, no failed run; numbers in the thesis audit, record 7.385); seeds 1 and 2: all 72 runs complete 2026-10-22 10:39 (45,600 evaluations; two runs resumed in the same run from their save points; folder online-seeds12-2026-10-20; dispatch and incidents record 7.385, audited results record 7.388) |
| Round 4 | Done offline 2026-10-17 to 2026-10-19 (sections 7b.7-7b.8, records 7.363, 7.381 and 7.383): LOADBench did not help the Round 3 models - stage 1 + stage 2, the predictor transplant (option C) and the pretrained input layers (option 1) all end at the control's error; online test not run |
| Journal | Dropped (user, 2026-10-23: "I am not publishing"): no journal experiment J0-J5 and no manuscript milestone will be run; sections 14-15 are kept for reference only |

Evidence: `artifacts/local/reviews/transfer-experiment-2026-10-10/plan-status-audit-2026-10-14.json`, the RGCN
`completed-comparison.json` and `dual-session-2026-10-14/completion-verification.json`, and Round 3's `pair-status.json`.
Historical preparation, interrupted attempts and conditional continuations remain in their original ledgers.

**Step 1 extension (2026-10-13, record 7.339):** the user requested the existing **RGCN + SAC** encoder
("dont use plain gcn, use what my code have") and "queue it after the circuit gps training". Section 6.1.1 adds
12 from-scratch runs after CircuitGPS training and checkpoint review. **All 12 finished on 14 October at 20:04
Europe/London.** They are separate from Round 3's still-planned online comparison. No plain GCN implementation is added.

**Step 1 extension (2026-10-16, record 7.355):** the user asked to "add gatv2 to round 1 step 1". Section 6.1.2 adds
12 from-scratch GATv2 runs matched to the RGCN extension, run on both Virtuoso sessions 14:45-18:22 Europe/London.

**Journal extension (2026-10-13, record 7.338):** [section 14](#14-journal-experiments) adds the prospective
experiments needed to assess a CircuitGPS paper; [section 15](#15-timeline-to-august-2027-publication) gives a dated
schedule targeting submission by 31 January 2027 and online journal publication by 31 August 2027. These are
planning targets, not a promise of acceptance. The user requested this plan addition; the new journal experiments
are proposed, not launched. Earlier results, Round 2 rules and the authorized Round 3 offline jobs retain their scope.

**Revised 2026-10-10 (record 7.305, session "Trained model spec change topology proof"; user: "make the stdcell plan
first part of the step 3(the spec change) and exchange current plan step 2 with step 3 so after step 1 it runs stdcells
first"):** the old steps 2 and 3 changed places - the new targets are step 2, SAC against Bayesian optimization is step
3 - and the new-target step begins with a logic cell, the flip-flop DFFRX1 (section 6.2.1). Records 7.301 to 7.304
carry the old numbers; the windows' folders and the run names of section 13 were renamed the same evening.

**Revised 2026-10-11 (record 7.317, session "Circuit training and SAC RL graph transformer"; user: "fix everything this
chat mentioned for the encoder networks input. update the experiment plan, add a new section step for comparing new and
old encoder input builds. use the new encoder in the next coming experiment step"):** a second build of the network
inputs exists (section 4); a new step 3b compares it with the first build, before step 4 (section 6.3b); from step 3b
on every new model is made with it. The step is numbered 3b so that steps 4 to 6, their run names and their folders
keep their numbers.

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
| 1 | How do GT, GraphGPS, RGCN and GATv2 compare with matched inputs and SAC settings? | 4 core + 4 AgenticSizing | GT, GraphGPS, RGCN, GATv2 | 44 (20 original + 12 RGCN + 12 GATv2) | original estimate about 7 h; RGCN measured 3 h 59 min elapsed; GATv2 estimated 3-4 h |
| 2 | Does a trained model reach a new target faster than starting over? | logic cell DFFRX1 first, then OTA5t, RING3, LDO1 | GraphGPS | 40 | about 7.8 h |
| 3 | Is SAC better than Bayesian optimization, from scratch? | AgenticSizing LDO | GT (SAC) | 9 | about 1.7 h |
| 3b | Does the second build of the network inputs learn as well as the first, and what do the operating-point ratios add? | OTA5t, RING3, LDO1 at an eased limit | GraphGPS | 24 | about 5.2 h |
| 4 | Does a gpdk045 model help on the same circuit in a second PDK, and does the second input build carry over better than the first? | OTA5t, RING3, LDO1, ported | GraphGPS | 12 + 3 probes | about 3.2 h |
| 5 | Does one general model beat starting over on an unseen circuit in the known PDK? | telescopic cascode | GraphGPS | 2 + 1 probe | about 0.75 h |
| 6 | Does the same general model beat starting over on the AgenticSizing circuits? | 4 AgenticSizing | GraphGPS | 4 + 4 probes | about 2 h |

Round 1 including the RGCN and GATv2 extensions: **135 runs and 8 probes, 111,464 planned charged design evaluations** (section 9).
The previous planning estimate was about 27.6 h before the extra RGCN runs. The RGCN campaign took 3 h 59 min
elapsed, with 5 h 35 min summed active run time across both sessions. These are cumulative plan totals, not counts
of work still outstanding or a full actual-cost ledger. They include the revised step 2,
step 3b and step 4 additions, and supersede the early 63-run summary.

## 2. Words used

- **Design budget:** normally 800 charged candidate evaluations per run. A preparation failure can consume a slot
  without a simulator launch; record charged attempts and actual launches separately.
- **Pass:** a design that meets every Specs row.
- **From scratch:** a fresh network, trained on this one task only.
- **Fine-tune:** start from a trained network and keep training on the new task.
- **Probe:** a trained network proposes 300 designs with no further training (mode `frozen`, sampled actions).
- **General model:** one network trained offline on the recorded designs of many circuits; no new simulation.
- **Seed:** the number that fixes a run's random choices; a repeat is the same run with another seed.

## 3. Circuits: from twelve to eight with new runs, and one logic cell

| Group | Circuit, task | Why |
|---|---|---|
| Core, gpdk045 | OTA5t, `mscr_ota5t` | 8-9 min per 800 designs; 95-96 % late passes for both networks; built on the PDK's 1.8 V transistors, so the cleanest port |
| Core, gpdk045 | RING3, `mscr_ring3` | from scratch only 15 % (GT) and 30 % (GraphGPS) late passes: room to show a gain |
| Core, gpdk045 | LDO1 at HF PSRR <= -3 dB, `ldo1_relaxed` (key `graphgps_ldo1`) | no pass of 800 from scratch for either network (with the old inputs: 0 to 3, and 34 to 55 with a general model - no run with the new inputs stands for that one) |
| Core, gpdk045 | VCO, `mscr_vco_lin_c` | kept on the user's word; 38-42 min a run; 92 % (GT) and 99 % (GraphGPS) late passes; step 1 only |
| Logic cell, gpdk045 | flip-flop DFFRX1, a copy of `gsclib045/DFFRX1` (built; ten runs complete) | step 2, first: delay, energy and area trade over a wide range, so a new goal lies far from the old one (6.2.1) |
| Unseen, gpdk045 | telescopic cascode, `mscr_otatc` | step 5; out of every training pool of this plan |
| AgenticSizing, second foundry's 0.18 um PDK | `agentic_ldo_pub`, `agentic_bgr_pub`, `agentic_fc_pub`, `agentic_sys_pub` (7.300) | the paper's netlists, size ranges and limits; steps 1, 3 and 6 |
| No new runs | OTA7t width, LDO2, folded cascode `mscr_otafc` | their recorded designs train the general model |

The numbers of the four core rows are step 1's, with the new inputs (replaced on 2026-10-12, user: "replace old result
with new results"; this table gave the old-input studies' numbers before - they are in record 7.313 beside the new).

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

- **Networks:** Step 1 compares GT, GraphGPS and the existing RGCN, all with SAC. RGCN was added by the user on
  2026-10-13 (6.1.1); the original GT/GraphGPS results remain recorded. Step 3 uses GT; steps 2 and 4 to 6 use GraphGPS.
- **Network inputs:** every new model is made with Network inputs **Transferable** (`spec_input` set, `size_features`
  pdk_relative, `device_model_features` true) and the family component list. Steps 2 and 4 to 6 need them: a model with the old
  inputs loads only on a task with the same spec names and reads sizes in micrometres. One arm of step 4 differs on
  purpose (absolute sizes, no device numbers).
  **Changed on 2026-10-11 (record 7.317, user: "use the new encoder in the next coming experiment step"): from step 3b
  on every new model is made with Network inputs Transferable 2** - the three settings above and three more:
  `bench_features` relative (a bias current is read in microamperes in a column of its own, where it read as 0.00005
  in the column of volts; a voltage source also as a share of the supply; a source's AC magnitude and a step's two
  levels), `net_roles` rule (ground, supply, input, output and bias tagged by one rule on every task, where the tasks
  themselves tag ground everywhere and the supply on a third of them) and `operating_point_ratios` true (gm/Id,
  gm/gds, overdrive and Vds/Vdsat of every transistor at the simulated operating point, with its region). Steps 1 to
  3 ran with the first build and stay as recorded. Arms that differ on purpose: the first-build arms of step 3b and of
  step 4 (the comparison), step 3b's arm without the ratios, step 4's absolute-sizes arm, and the general model of
  steps 5 and 6 as section 6.5 says.
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
  **Step 3b and later (record 7.317):** a third frozen copy, made after that record has landed (it also holds
  records 7.315 and 7.316, without which Virtuoso grows with every design). The second build is workbench code only:
  the digest stays `6724e52b...`. A configuration written by the new code names the three new settings, and an older
  copy refuses them - the new runs go from the new copy only.

## 5. How a run is judged

Read from the recorded tables, with the script of the encoder comparison (`compare_runs.py`):

- **Early passes:** the historical 100-record window, evaluations 9-108 in commit order. This preserves the existing
  comparison script's definition; resets or failed attempts inside that window are included, so it is not exactly
  the first 100 policy-only proposals.
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

### 6.1 Step 1: GT, GraphGPS and RGCN with matched inputs (32 runs)

- **Original runs:** GT and GraphGPS from scratch on the four core and the four AgenticSizing circuits, seed 0 (16 runs);
  GraphGPS four more times on the AgenticSizing LDO, seeds 1-4, so that circuit has five runs against five (GT's other
  four are step 3's SAC runs).
- **New inputs against old:** each core run against the recorded old-input run of the same network (rule of section 5).
  **The table was replaced on 2026-10-12** (user: "replace old result with new results"). It held the recorded
  old-input runs step 1 was judged against; the full comparison accepted the new inputs on every circuit and both
  networks (records 7.313 and 7.335, where old and new stand side by side), and what later results are read against is now step
  1's own runs with the new inputs:

  | Circuit | GT, new inputs (passes of 800, late, 50 % by) | GraphGPS, new inputs | RGCN, same input build |
  |---|---|---|---|
  | OTA5t | 617, 96 %, 205 | 636, 95 %, 185 | 628, 95 %, 200 |
  | RING3 | 94, 15 %, never | 182, 30 %, never | 183, 34 %, never |
  | LDO1 at -3 dB | 0 | 0 | 0 |
  | VCO | 466, 92 %, 374 | 546, 99 %, 310 | 539, 99.6 %, 254 |

- **Encoder comparison:** one seed per core circuit is exploratory; on the AgenticSizing LDO all three encoders
  have five seeds. The RGCN completion and published-circuit tables are in 6.1.1.
- **Conditional, one run each:** a control (GT, old inputs, today's code, LDO1) if the new LDO1 run differs from the
  recorded one - LDO1 is the only core circuit where designs had missing values (1-2 %), the rule 7.299 changed; and, on
  an AgenticSizing circuit where a from-scratch run finds no pass, one continuation of that run from its own network for
  another 800 designs (this stands in for stage B, which is not part of the plan).
- **Produces:** the GraphGPS models of OTA5t, RING3 and LDO1 that step 2 starts from, and the from-scratch side of step 6.

#### 6.1.1 RGCN + SAC extension (12 runs, completed 2026-10-14)

Added 2026-10-13, record 7.339. Use `encoder_type: rgcn`, the existing port-relational encoder, with the common
SAC learner. This is an internal encoder baseline, not a reproduction of GCN-RL or Li's optimizer.

| Tasks | Seeds per task | New runs | Design budget |
|---|---|---:|---:|
| `mscr_ota5t`, `mscr_ring3`, `graphgps_ldo1` (shown as `ldo1_relaxed`), `mscr_vco_lin_c` | 0 | 4 | 3,200 |
| `agentic_ldo_pub`, `agentic_bgr_pub`, `agentic_fc_pub_far`, `agentic_sys_pub` | 0 | 4 | 3,200 |
| `agentic_ldo_pub`, additional repeats | 1, 2, 3, 4 | 4 | 3,200 |
| **Extension total** | | **12** | **9,600** |

- **Question:** does a port-relational message-passing encoder provide comparable sizing performance to GT or
  GraphGPS under the same SAC recipe? Report quality, simulation efficiency and compute cost. RGCN uses terminal
  role/direction relations without attention; an outcome does not isolate attention from every other architecture
  difference, including GraphGPS's structural encoding and model capacity.
- **Configuration:** scratch only, 800 designs, four simulator lanes, the recorded task/start/bench/parameter bounds,
  reward and SAC settings of the corresponding Step 1 run. Explicitly use the **first Transferable input build**
  (`spec_input: set`, `size_features: pdk_relative`, device-model features and family vocabulary; operating points,
  second-build bench features and rule-based net roles off). This is a matched historical extension and an explicit
  exception to the newer-model Transferable 2 default. No pretrained model or source replay is loaded.
- **Network:** hidden width 48, four layers, `structural_encoding: none`; the serialized head count is unused by
  RGCN. Width/depth match the recorded GT/GraphGPS configuration rather than RGCN's width-32 starting preset.
  Record actual actor/critic parameter counts; equal width/depth does not mean equal parameter count.
- **Runtime:** use the existing frozen Step 1 runtime and its implemented RGCN. Pin source/config hashes and verify
  schema, task and backend compatibility before dispatch. Preserve the current offline training runtime and package
  digest. If the historical runtime or physical task cannot be qualified, stop the queue with an explicit reason;
  do not silently change inputs, start points or simulator settings to make a run launch.
- **Dependency:** wait for the fresh CircuitGPS v2 run's 20,000 updates and the pair supervisor's successful checkpoint
  review/completion. A failed or interrupted dependency does not count as completion. Do not run new simulations
  while that training remains active. Dispatch sequentially within each assigned Virtuoso session through the existing
  run machinery, respecting session and cell locks. On 2026-10-14 the user authorized using the second Virtuoso for
  this queue; the allocation below replaces the original single-session order. No automatic bridge/backend restart
  or schematic rebuilding is included.
- **Comparison:** add RGCN columns beside the original Step 1 results. On published LDO compare five seeds per
  encoder (GT's seeds 1-4 are in Step 3); elsewhere one seed is exploratory. Use the same section 5 pass measures,
  first-feasible/censored failures, best feasible physical objective, runtime and failure counts. Preserve negative
  results. An infeasible 800-design arm stays a failure; this extension does not automatically add continuations.
- **Evidence:** labels `tx1-<circuit>-rgcn` and `tx1-asz-ldo-rgcn-s<seed>`; store new configs, dependency/queue status,
  per-run identities and results in a separate RGCN subfolder of the transfer review directory. Existing Step 1
  configs/results are inputs, not files to overwrite. The added data does not enter the frozen 304-run source pool.

This adds **9,600** evaluations to Round 1, independently of the prospective journal matrix. RGCN's journal
frozen/adapt/scratch arms remain separate experiments with their own inputs and source split.

**Queue history, 2026-10-13 at 14:43 Europe/London:** the 12 configs passed frozen-runtime schema, saved-row and compilation
checks. `artifacts/local/reviews/transfer-experiment-2026-10-10/rgcn-2026-10-13/manifest.json` pins them and 196
runtime source files (`94e7dd4f23ed09f45c7a5b258c93c918c9a3e80d64da7d82c4047fe7dad076dc`). The detached
`run_queue.py` process initially waited in `waiting_for_circuitgps`; its status, log and process record retain that
history. It ran the ordinary CLI and read-only consistency/nonce-cache checks directly, so it did not
require the workbench HTTP server. It makes a private settings snapshot only after the dependency completes.
A failed dependency, changed input/runtime, failed physical check or incomplete run stops the queue for review;
no costly retry is automatic. No RGCN simulation had started at that initial record. A WSL shutdown stops this local
process; the manifest and run ledger remain available for deliberate recovery.

**Two-session allocation, 2026-10-14 (record 7.346):** after both offline models completed and passed review, the
user requested simulations on the second Virtuoso. The already completed OTA5t run and active RING3 run stay on
Virtuoso 1. Its remaining sequence is LDO1, published BGR, published system, published folded-cascode amplifier,
then VCO. Virtuoso 2 receives the published LDO, seeds 0–4, sequentially. These are the same **12 × 800 = 9,600**
designs, four simulator lanes per active run, with disjoint schematic/testbench cells between sessions.

The routing manifest, private settings snapshots, validation, process identities and live per-session status are in
`artifacts/local/reviews/transfer-experiment-2026-10-10/rgcn-2026-10-13/dual-session-2026-10-14/`.
Only the five second-session configurations change `run.connection_profile_id` from `asz` to `asz2` internally;
the connection panel presents both sessions together. The original frozen configs, all 196 runtime sources,
optimizer digest, inputs, reward, SAC settings and seeds remain unchanged. The historical runtime uses its existing
`GATOR_BRIDGE_STATE_DIR` override to name the same session lock and crash-journal directory as the current workbench;
the dispatcher holds the current cell locks around its child processes. Saved task files are separately pinned.
The original supervisor is held at the next job boundary and retired only after its active child and post-check
finish. The hold remains to prevent a duplicate dispatch. Incomplete runs or failed physical checks stop their
session for review, without automatic costed retries. Shared CPU/simulator load must be recorded when interpreting
wall time; this allocation is not a controlled hardware speed comparison.

**Historical-runtime compatibility correction during dispatch:** the copied current PDK settings had enabled
readback-built netlists, whereas Step 1's runtime predates the numeric-equivalence comparison of record 7.309.
Published LDO seed 0 stopped on `120.9600u` versus `120.96000000u`: four charged preparation failures, **zero Spectre
launches and zero learner updates**. Its failed segment is retained. The two private queue settings restore
`netlist_from_readback: false` for this PDK, the original Step 1 native-export path; live settings are unchanged.
Exact continuation keeps the same run identity and total budget of 800, with 796 attempts remaining. The old
workbench's known family-vocabulary continuation bug (record 7.319) is corrected in a separate, pinned workbench
copy used only for this continuation: pass the saved vocabulary when checking the network-input key. The recorded
and rebuilt keys match, full checkpoint compatibility passes, and the optimizer code/digest is unchanged. Record
the four infrastructure failures separately in the comparison; do not silently refill or discard them.

**Completion and comparison, 2026-10-14 (record 7.347):** all 12 runs reached their 800-attempt cap and saved a final
checkpoint: **9,600 charged attempts, 9,596 Spectre launches and 72,256 learner updates**. The four retained
preparation failures are all in published LDO seed 0; no new infrastructure failure occurred after its reviewed
recovery. Session 2 finished at 18:34 and session 1 at 20:04 Europe/London. The whole campaign, from the first OTA5t
run through the last post-check, took 3 h 59 min; summed active run time was 5 h 35 min. Shared hardware load means
these times are not a controlled encoder speed comparison. A summary-only monitor stopped on a temporary
`budget: null` status; both independent queues continued to completion. The aggregate status was reconciled from
the final records, preserving the stale snapshot and error log.

`rgcn-2026-10-13/compare_completed.py` reads the 12 RGCN runs and 24 qualified historical reference runs without
writing to any source archive. Its `completed-comparison.json` records the section 5 measures, first-pass/censored
outcomes, failures, best-design physical metrics, timing, source paths and hashes. Every stored original Step 1
reference measure was reproduced exactly. The core results above now include RGCN.

Published circuits, seed 0 only; passing designs within the same 800-attempt horizon:

| Circuit | GT | GraphGPS | RGCN |
|---|---:|---:|---:|
| Reference / BGR | 0 | 0 | 0 |
| Folded-cascode amplifier, far start | 1 | 0 | 8 |
| System | 0 | 0 | 2 |

Published LDO, seeds 0-4 in order:

| Encoder | Runs with any pass | Passing designs per run | Median passes | First-pass charged count per run |
|---|---:|---|---:|---|
| GT | 5/5 | 2, 2, 15, 65, 50 | 15 | 739, 483, 714, 63, 532 |
| GraphGPS | 3/5 | 5, 0, 31, 13, 0 | 5 | 273, censored, 368, 408, censored |
| RGCN | 5/5 | 50, 144, 122, 264, 34 | 122 | 545, 360, 221, 202, 508 |

RGCN is a strong baseline on the published LDO in this experiment: all five runs find a pass and its median pass
count is higher. This does not establish a universal architecture ranking. OTA5t and RING3 are close to GraphGPS;
VCO reaches the 50% window earlier but has slightly fewer total passes than GraphGPS. No encoder passes relaxed
LDO1 or the published reference. The amplifier and system gains are single-seed observations; the system's earlier
GT continuation beyond 800 is not included in this 800-attempt comparison. Width/depth matching does not isolate
attention or match parameter counts. These scratch results do not compare the two Round 3 pretrained models.

#### 6.1.2 GATv2 + SAC extension (12 runs, completed 2026-10-16)

Added 2026-10-16, record 7.355 (user: "add gatv2 to round 1 step 1", then "Yes, start now" to the 12 runs). Use
`encoder_type: gatv2`, the existing dynamic-attention encoder with port features on the edges, with the common SAC
learner: a local-attention baseline beside GT's transformer convolution, GraphGPS's local + global blocks and RGCN's
attention-free relations. It is not a reproduction of any published GAT sizing method.

| Tasks | Seeds per task | New runs | Design budget |
|---|---|---:|---:|
| `mscr_ota5t`, `mscr_ring3`, `graphgps_ldo1`, `mscr_vco_lin_c` | 0 | 4 | 3,200 |
| `agentic_ldo_pub`, `agentic_bgr_pub`, `agentic_fc_pub_far`, `agentic_sys_pub` | 0 | 4 | 3,200 |
| `agentic_ldo_pub`, additional repeats | 1, 2, 3, 4 | 4 | 3,200 |
| **Extension total** | | **12** | **9,600** |

- **Matched to 6.1.1 exactly:** every configuration is its RGCN twin with only `encoder_type` changed (checked field by
  field by `prepare.py`): scratch, 800 designs, four lanes, the first Transferable input build, the Step 1 task, start,
  reward and SAC settings, width 48, four layers, four heads (used by GATv2), `structural_encoding: none`, the frozen
  Step 1 runtime (`94e7dd4f...`) and the private PDK settings with the native-export path of 6.1.1.
- **Sessions:** by where each cell was held on 2026-10-16 (a read-only look of both Virtuosos before dispatch, so no
  cell is let go of): Virtuoso 1 runs OTA5t, RING3, LDO1, the amplifier and VCO; Virtuoso 2 the published LDO seeds 0-4,
  the reference and the system (`asz2`, the only change to those configurations). Cells are disjoint between sessions.
- **Checks before dispatch, zero simulations:** schema, saved rows, compilation and session routing for all 12; the
  physical check (saved task against the cell) and the daemon's nonce cache for all 12 in their own session.
- **Queue:** one worker per session with a fixed job list; each holds its session's queue lock and its cells' locks for
  its whole life, waits while the host has less than 1.2 GB free, and stops on a failed run or check with no automatic
  costed retry. `HOLD`, `HOLD-s1`, `HOLD-s2` hold before the next job.
- **Comparison:** add GATv2 columns beside GT, GraphGPS and RGCN with the measures of 6.1.1 (`compare_completed.py`'s
  measures; five seeds per encoder on the published LDO, one elsewhere). The same limits apply: one seed outside the
  published LDO, shared machine load (no speed comparison), width/depth matched rather than parameter counts.
- **Evidence:** `artifacts/local/reviews/transfer-experiment-2026-10-10/gatv2-2026-10-16/` (`prepare.py`,
  `dispatch.py`, `manifest.json`, `qualification.json`, `cell-holds-before.json`, `queue-status.json`, logs). Labels
  `tx1-<circuit>-gatv2` and `tx1-asz-ldo-gatv2-s<seed>`. The data does not enter any source pool.

**Completed 2026-10-16 18:22 (record 7.358):** 12 of 12 runs, 9,600 Spectre launches, no infrastructure failure.
Passing designs of 800, seed 0, GT / GraphGPS / RGCN / GATv2: OTA5t 617 / 636 / 628 / 636; RING3 94 / 182 / 183 / 88;
VCO 466 / 546 / 539 / 587; LDO1, published reference 0 for all; published system 0 / 0 / 2 / 0; published amplifier
1 / 0 / 8 / 274 (one seed). Published LDO, five seeds: GATv2 4/5 runs pass, median 21 passing designs, between GT (5/5,
15) and RGCN (5/5, 122); no difference shown against any encoder (exact rank tests p >= 0.095 on passes, >= 0.22 on the
first pass). GATv2 behaves like GT on RING3, where both local-attention encoders trail.

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
**Status: run on 2026-10-11 (record 7.310), all ten runs complete.** From scratch no run finds a passing design in 800 (five
runs: speed, power, and the in-between speed with three seeds). From the both-goals model: speed 388 passes (first at design 16),
power 309 (16), in-between speed 264 (40), 409 (91) and 300 (85) for seeds 0, 1 and 2 (the third seed's first try died at design 93
when the simulator machine ran out of memory; it was run again the same evening as `tx2-dffr-powermid-both-s2-r`). Results:
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

**Status checked 2026-10-14:** all 30 runs are complete. Recorded outcomes are in
`artifacts/local/reviews/transfer-experiment-2026-10-10/results-step2-analog.json` and record 7.314.

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

**Status checked 2026-10-14:** all nine new runs are complete; the fifth GT-SAC run is Step 1's seed 0.
The exact selection is retained in `jobs-tx3.txt`, with completion checked against each run's own `status.json`.

- **Circuit:** the AgenticSizing LDO (27 variables, 5 rows): the one circuit where the paper gives numbers for a Bayesian
  optimizer that worked (4 of 5 runs, about 524 simulations).
- **Runs:** SAC = GT from scratch, five repeats (seed 0 is step 1's run); Bayesian optimization, five repeats. No
  random-search arm (user).
- **Fairness:** the same first 9 designs per seed (the start and the 8 warm-up designs), the same score (the run's
  reward), 800 designs, 4 simulated at a time.
- **Judged by:** how many of five runs find a pass, the first passing design and the clock time to it, passes of 800,
  the best score against the number of designs.
- The Bayesian optimizer exists since record 7.304 (section 8, item 1): `run.optimizer: "bayes"` in the run's
  configuration file. The original plan required its full regression and browser batch before starting this step;
  the run completion above is not a new claim about those separate acceptance checks.

### 6.3b Step 3b: the second build of the network inputs against the first (24 runs)

User, 2026-10-11: "fix everything this chat mentioned for the encoder networks input. update the experiment plan, add a
new section step for comparing new and old encoder input builds. use the new encoder in the next coming experiment
step". Record 7.317. **Status: run on 2026-10-11/12 (record 7.328), all 24 runs complete. By the rule below `full` is
accepted on all three circuits - median late passes 95 % against 95 % on OTA5t, 32 % against 30 % on RING3, 0 % against
0 % on LDO1, where almost no run passes - and no arm differs from another: no loss shown, no gain shown. Steps 4 to 6
use Transferable 2. Results: `artifacts/local/reviews/input-builds-2026-10-11/results-step3b.md`.** What follows is the
plan as it was run.

- **What changed in the inputs**, in plain words (the record has the detail):

  | The first build reads | The second build reads |
  |---|---|
  | a bias current of 50 uA as 0.00005: currents share one column with voltages, divided by 1 | the current in microamperes, in a column of its own |
  | a voltage source in volts | also its share of the supply; a source's AC magnitude and the two levels of a step |
  | the net tags each task was saved with: ground on all 66 tasks, the supply on 22, nothing else | one rule on every task: ground, supply, input, output, bias |
  | sizes, and four numbers of a transistor's model that are the same for every design of a PDK | also four numbers of each transistor at the simulated operating point (gm/Id, gm/gds, overdrive, Vds/Vdsat) and its region |

  Not changed: how the specs and the sizes are read, and the action - a position between a row's own limits. The
  repository's rule forbids changing what an action means, so "one range for every task" stays a rule for how a ported
  task is made (section 6.4), not something built into the network.
- **Question 1: does the second build learn as well from scratch?** It must, before a step is built on it.
- **Question 2: what do the ratios add, and what do they cost?** They need every design's operating point - one DC
  solve more where the test saves none, and one result file more to read - and no design recorded before this step
  holds one (section 6.5).
- **Tasks:** OTA5t `mscr_ota5t`, RING3 `mscr_ring3`, and LDO1 with the eased limit, `graphgps_ldo1_t2` - the LDO1 task
  that passes from scratch (75 of 800 in step 2; at the saved limits no run passes and two builds could not be told
  apart). They are step 4's three circuits.
- **Arms: GraphGPS from scratch, 800 designs, the run settings of the recorded run of the task, seeds 0, 1 and 2:**

  | Arm | Network inputs | Runs |
  |---|---|---|
  | `first` | Transferable, the first build | seed 0 is recorded (`tx1-ota5t-gps`, `tx1-ring3-gps`, `tx2-ldo1-psrr-scratch`); seeds 1 and 2 are run now, from the same code copy as the other two arms: 6 runs |
  | `full` | Transferable 2 | 9 runs |
  | `bench` | Transferable 2 without the operating-point ratios | 9 runs |

  Three seeds, because one run does not separate two builds: two attempts of one seed on RING3 gave 94 and 161 passes
  by design 635 (record 7.313).
- **Before the runs (27 designs):** a nine-design run per task with Transferable 2 (`tx-prep-<circuit>-opcheck`: the
  start and the eight random warm-up designs, so no proposal of a network is in it). It shows that the operating point
  is read for every transistor of the circuit and what a design then costs in time; the check's "Net tags by rule"
  line of each task is read once by a person and copied into the results.
- **Judged by** (fixed before any result; section 5's measures):
  - late passes, passes of 800 and the 50 % point of every run, and the median of each arm's three;
  - an arm is **accepted** on a circuit when its median late passes are within 10 points of the first build's median
    and its median 50 % point comes no more than 100 designs later (section 5's rule, on medians);
  - two arms **differ** on a circuit only when all three runs of one lie above all three of the other, in late passes
    or in passes of 800; anything less is written "no difference shown";
  - the seconds per design of each arm: what reading the operating points costs.
- **Where:** the review folder `artifacts/local/reviews/input-builds-2026-10-11/` - `make_configs_tx3b.py` (the 24
  configurations and the three checks, each the recorded configuration of its task with the seed, the name and the
  network settings changed), `jobs-tx3b.txt`, `check_opcheck.py`, `README.md` (how to start; nothing starts by itself).
- **What follows** (proposed; the user confirms it with the result):
  - `full` accepted on all three circuits: steps 4 to 6 use Transferable 2, as section 4 says;
  - `full` not accepted on a circuit and `bench` accepted: steps 4 to 6 use Transferable 2 without the ratios;
  - neither accepted: the first build stays, and the next step waits for the user.
- **Second part, run with step 4 (3 runs, counted there):** a run from scratch on a known circuit says whether a build
  learns, not whether it carries over. So step 4 has one more arm per ported circuit: fine-tune from a model of the
  FIRST build, trained offline on the same recorded designs as the second build's model. The two fine-tune runs side
  by side are this step's answer on another PDK.
- **Produces:** the recorded designs with operating points that step 4's start models are trained on - arm `full`,
  three runs per circuit.
- **Limits:** three seeds; LDO1 on an eased limit and with a goal row; OTA5t ends near 95 % late passes with every
  build, so it can show a loss and hardly a gain. The four numbers of a transistor's model are constants of a PDK:
  with two PDKs they tell the network which PDK it is on and little more (section 6.4's limit). The ratios change with
  every design and do not have that limit.

### 6.4 Step 4: the same circuit in a second PDK (12 runs, 3 probes)

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
  | Fine-tune, first build (added 2026-10-11, step 3b's second part) | the same designs, a model made with the first build of the network inputs |
  | Probe | the relative-sizes model, no training |

  Both start models are trained offline from the same recorded gpdk045 designs of the circuit, so the size input is the
  only difference between them: that difference is what the PDK-relative inputs are worth.
  **Changed 2026-10-11 (record 7.317):** every arm reads Transferable 2 but the first-build arm; the absolute-sizes
  arm differs from the relative-sizes arm in the sizes and the device numbers only, the first-build arm in the second
  build's three settings only. The three start models are trained offline on step 3b's recorded runs of the circuit
  (its arm `full`: three runs, 2,400 designs): the designs recorded in steps 1 and 2 hold no operating points.
- **The ports as they will be built** (fixed 2026-10-11 22:20 by the queue session, before any ported cell exists; the
  user was told the five choices and may change them): each transistor becomes the second PDK's 1.8 V transistor of its
  polarity with ONE finger and its whole width in one number; each MIM capacitor becomes the second PDK's MIM
  capacitor of the same side lengths and count (both PDKs' models give the same capacitance for them); ideal parts and
  sources stay. Sizes are the same multiples of the minimum size the network's relative-size input divides by: OTA5t
  and LDO1 (gpdk045's 1.8 V kind, minimum 0.32 um wide and 0.15 um long, against 0.22 and 0.18 um) widths x 0.6875 and
  lengths x 1.2; RING3 (gpdk045's 1 V kind, 0.12 um and 40 nm) widths x 1.8333 and lengths x 4.5; on the 5 nm grid, a
  lower bound rounded up and an upper bound down. OTA5t's and LDO1's benches are 1.8 V benches already and stay as they
  are. RING3's is a 1.0 V bench: it runs at 1.8 V, the supply of its transistors, and what depends on the supply is
  scaled by 1.8 - the start voltages, the level at which the duty cycle is read, the two swing limits, and the power
  (supply voltage times the average current, which the 1 V bench left out). The cells go into the design library the
  published circuits use.
- **The rank rule for the ports** (the rule of record 7.262, `phase3_targets.select`: from the start design and 64
  random designs the largest common rank k, at most 32 and at most half the least-measured row's count, at which every
  ranked row is reached by at least three random designs and no design passes all rows; a row's limit is the k-th best
  value measured in it; 6 dB as the scale of dB rows). It was written for six one-sided rows with positive limits, so it
  is extended here, before any design of a ported task is simulated: (1) a limit in dB may be negative (LDO1's three PSRR
  rows); every other limit must still be positive; (2) a row that asks for a value inside a band around a target (RING3's
  frequency) is ranked as "the higher the better", its k-th best value becomes the band's centre and the band keeps its
  relative width (5 % either side); (3) rows that say what a valid result is rather than how good it is - RING3's duty
  cycle and its two swing limits - are not ranked: they keep their limits (the swing limits scaled by the supply) and
  count in "no design passes all rows". If no rank qualifies, the task is reviewed and no run starts.
  **Corrected 2026-10-11 22:50, when the first port was ranked:** the sentence above names record 7.262, and what that
  record applied is the form with the phase margin held at 60 deg and the random designs' joint passes reported, not
  forbidden (`goals_with_pm_floor`); the paragraph here had written out the older, stricter form of record 7.240. The
  ports follow record 7.262, as the plan's own sentence says: ranked rows at the highest rank up to 32 that at least
  three random designs reach in every row, a phase-margin row at 60 deg. On the ported OTA5t that is rank 32 (gain at
  least 44.3 dB, bandwidth 35.2 MHz, power at most 0.190 mW, PSRR 43.4 dB, noise 35.3 uV; 6 of its 64 random designs
  pass every row); the stricter form gives rank 27 with a phase-margin limit of 84.8 deg, which only weak designs reach -
  the contradiction record 7.262 describes. Both were computed from the same 64 designs; the user was told.
- **Two limits of the second PDK's MIM capacitor, found at the builds (2026-10-11):** its form takes no side shorter
  than 4 um (RING3's two capacitor rows go from 1.0 to 5.6 um in gpdk045) and no count above 1,000 (LDO1's load
  capacitor is 12,460 units, its row 480 to 14,600). Neither port's rows can stay as they are; the choice for each is
  put to the user and the two tasks wait for it. OTA5t has no capacitor: built, checked on Spectre, saved as
  `real:mscr18_ota5t` with its limits from the rule.
  **Decided by the user 2026-10-11 23:0x and built (record 7.320):** RING3's two capacitor rows go from 4.0 to 5.6
  um (the start 4.49 um unchanged; the low end of that action is lost); LDO1's load capacitor is a 23 um unit with the
  count row 32 to 971 and the start 829, the same capacitance as 480 to 14,600 and 12,460 units of 5.6 um within one
  unit; the limits come from the rank rule in record 7.262's form. RING3 is saved with them (frequency 557.2 to 615.9
  MHz, power at most 0.697 mW; duty cycle and the two levels kept; 1 of 64 random designs passes every row). LDO1 is
  built and saved with provisional limits; its Calibration, and with it its limits, wait for the user's go, as every
  run of this step does.
  **2026-10-12, after the user's go (record 7.326):** LDO1's Calibration ran - 44 of its 64 random designs measure
  every row - and the rule gives rank 22 (half the least-measured row's count, the phase margin's): dropout at most
  0.1964 V, quiescent current at most 18.59 uA, phase margin at least 60 deg, PSRR at most -9.97 / -1.41 / -0.0016 dB
  at 10 kHz / 1 MHz / high frequency, load regulation at most 15.0 mV; no random design passes every row. The
  nine-design checks passed on the three ported tasks: the operating point of every transistor is read. The whole
  history of the ports, every row in both PDKs: `pdk-port-history.md`.
- **One range for an action:** a ported task's rows keep the gpdk045 task's ranges as multiples of the minimum size
  and keep each row's scale (log or linear), so the same action is the same multiple of the minimum size in both PDKs.
  A script checks this before a port is saved.
- **Before the runs:** a nine-design check per ported task with Transferable 2, as in step 3b: the operating point of
  the second PDK's transistors is read.
- **Limit:** the simulator machine holds two PDKs, so the device numbers have four transistor models to learn from.
- **Result (record 7.329, 2026-10-12; one seed per arm):** a gpdk045 model of the circuit helps on its port once
  it is trained on - OTA5t's early passes 60 to 66 % against 3 % from scratch, RING3's 29 to 41 % against 2 %, the runs
  ending as well - and passes nowhere without training (the three probes: 0 of 300). Relative against absolute sizes:
  no difference on OTA5t; on RING3 the relative-sizes model is ahead on every measure (41 against 29 % early, 74
  against 53 % late) and the absolute-sizes one misses the "helps" bar by three points, inside what seeds alone do on
  that circuit. The second build against the first, carried over: no difference shown. LDO1's port is reached by no
  arm in 800 designs (its rank-rule limits; 6.4 above) and says nothing.

### 6.5 Step 5: the general model on an unseen circuit in the known PDK (2 runs, 1 probe)

- **The general model:** GraphGPS, new inputs, trained offline on the recorded designs of OTA5t, OTA7t width, RING3, VCO,
  LDO1, LDO2 and the folded cascode, plus step 4's runs in the second PDK. Left out: the telescopic cascode and every
  AgenticSizing circuit, the published ones and the rebuilt ones of 7.295.
- **Runs on `mscr_otatc`:** GraphGPS from scratch, GraphGPS fine-tuned from the general model, a probe.
- **Mark to reach:** with the old inputs GraphGPS had 59 % early passes from its general model against 23 % from scratch
  on this circuit, 100 % late passes both ways (GT: 73 % against 8 %).
- **Why before step 6:** if the general model helps here and not on AgenticSizing, the model is sound and those circuits
  are too different; if it does not help here either, step 6 says nothing about AgenticSizing.
- **The general model's inputs (record 7.317; open, the user's):** of the recorded designs in its pool only step 3b's
  and step 4's hold operating points. Proposed: the general model reads Transferable 2 WITHOUT the ratios (step 3b's
  arm `bench`), so every design of the pool is read the same way, and the runs of steps 5 and 6 use the same inputs.
  The other way - the ratios, with the older designs showing them as missing (`missing_operating_points: "mask"` in
  the request) - trains a network that mostly never saw them and then meets them on the new circuit; it is taken only
  if step 3b shows that the ratios matter.
- **Result (record 7.330, 2026-10-12; one seed):** 79 % early passes from the general model against 21 % from
  scratch, 100 % late both ways, the 50 % point at design 100 against 162: it helps, ends as well and does not
  deteriorate, and it passes the old-input mark of 59 %. The frozen model: 16 passes of 300. **The pool is not the one
  written above:** the plan's 36 archives need about 12 GB of memory in offline training and the workstation had 3.9 GB
  free, so the model was trained on one from-scratch run of 800 designs per circuit and PDK (ten archives, 7,555
  designs; the record names them). The inputs are Transferable 2 without the ratios, as proposed.

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
- **Result (record 7.330, 2026-10-12; one seed, the general model of the smaller pool):** the amplifier from the
  far start - first pass at design 212 after 6.6 minutes, 267 passes of 800, where the from-scratch run found none in
  800 (904 with its continuation); the LDO - 80 passes of 800 against 31 at most in five from-scratch runs, the first
  pass at design 320 (6.6 minutes), no sooner than from scratch; the reference - no pass from any start; the system -
  no pass with GraphGPS, from scratch, continued or from the general model. The frozen model passes on none of the
  four. **Corrected on 2026-10-12 (record 7.334):** this paragraph said the system passes from no start; with GT it
  does - step 1's from-scratch GT run, continued from its own network, passes 8 times from design 813 of its 1,600.

## 7. Round 2: repeats, only where round 1 shows an effect

**Review before dispatch, 2026-10-14:** these were conditional development repeats, not a frozen journal matrix.
The Step 2 proposal below predates the expanded goal-1/goal-2/changed-spec experiments and must be revised before
dispatch. Selecting only promising outcomes for repeats cannot supply the journal's confirmatory evidence; use
the balanced prospective matrix in section 14 for that purpose.

- **Step 2:** the old proposal was a second new target per analog circuit (9 runs, 3 probes, about 2.5 h). Revised
  Step 2 has already tested two goals and an intermediate changed specification, with three seeds on the changed
  specification. Do not dispatch the old proposal unchanged or count its budget as still needed. A further target
  or repeat matrix needs an explicit amendment naming the untested goal/seeds and matched arms. The original
  proposal to repeat logic-cell runs 1-4 with a second seed remains conditional and unexecuted.
- **Step 6:** repeats so the result reads "k of 5" as the paper's: five trials on the LDO and the reference, three or
  five on the amplifier and the system (20 or 28 runs, at most about 7 or 12 h; a repeat stops at its first passing
  design, `stop_at_first_feasible`). Three or five is decided when round 1 is in.

**Execution amendment, 2026-10-14 (record 7.349):** user: "go on with round 2". The selected scope is the
smaller Step 6 option plus the four logic-cell repeats. All 24 configurations passed offline validation against
their historical task definitions, starting dimensions, source checkpoints and runtime digests before dispatch.
Physical preflight passed on all six tasks. Both queues were dispatched at **22:14 Europe/London** on 14 October.
The obsolete analog Step 2 proposal is retired; no extra target, calibration, frozen probe or source retraining is added.

| Block | New runs | Seeds / arms | Maximum charged evaluations |
|---|---:|---|---:|
| Step 2 DFFRX1 | 4 | Seed 1: speed and power, each scratch and the original both-goals model | 3,200 |
| Step 6 published LDO | 4 | General-model seeds 1-4; reuse the five original scratch seeds 0-4 | 3,200 |
| Step 6 published reference | 8 | Scratch and general-model seeds 1-4; reuse seed 0 | 6,400 |
| Step 6 published amplifier, far start | 4 | Scratch and general-model seeds 1-2; reuse seed 0 | 3,200 |
| Step 6 published system | 4 | Scratch and general-model seeds 1-2; reuse seed 0 | 3,200 |
| **Total** | **24** | Five total trials per arm on LDO/reference; three on amplifier/system | **19,200** |

Step 6 stops proposing after its first feasible result and drains already dispatched evaluations, with an 800-attempt
cap. Count all charged attempts, failures and actual simulator launches. Compare success within 800 and first-pass
cost; do not compare full-budget pass counts with early-stopped repeats. Historical continuations beyond 800 are
excluded. DFFRX1 retains its full 800-attempt budget so the goal's improvement after feasibility can still be compared.

Session 1 takes DFFRX1 and the amplifier (8 runs); session 2 takes LDO, reference and system (16 runs). Expected
duration, not run count, motivates the split. Each active run has four simulator lanes and one learner; the two
sessions use disjoint core/testbench cells and canonical locks. Preserve the original optimizer/runtime per arm
(`7309` DFFRX1, `7301` published scratch, `7317` general-model adaptation) and the exact original source checkpoint.
Private settings for `7301` retain native netlist exports, as in Step 1; live PDK settings are unchanged.

**Interpretation:** these are repeats of the original pipelines. Step 6's scratch inputs are Transferable; its
general-model inputs are Transferable 2 without operating-point ratios. This existing difference prevents isolating
pretraining alone as the cause of a gain. DFFRX1 scratch/adaptation retain matched input settings. Shared machine
load also means these runs are not a controlled wall-clock speed comparison with the historical runs. The newer
all-archive GraphGPS/CircuitGPS source pair belongs to Round 3 and is not substituted into these repeats.

Evidence and current queue status: `artifacts/local/reviews/transfer-experiment-2026-10-10/round2-2026-10-14/`
(`manifest.json`, `validation.json`, `initial-preflight.json`, `queue-status.json`). Stop a session's queue on a failed
run or failed restoration check; retain its cost and artifacts, with no automatic costed restart.

**Recovery, 2026-10-14, 23:21 Europe/London (record 7.350):** the user authorized fixing the DFF failure handling
and restarting if needed, and fixing the parameter-write error. All four DFF configs already match Claude's
original policy: missing setup measurements fail the candidate, with negative rewards retained for learning;
the candidate failure limit is 800 and the separate infrastructure limit is 3. The active DFF run continues
without restart, with unchanged measurements, rewards and model settings.

The second queue completed its four LDO runs, then BGR scratch seed 1 stopped before any Spectre launch: the first
Virtuoso held its saved schematic in edit mode. That view was verified to have no unsaved edits and reopened
read-only. The exact failed assignment of 50 parameters then passed write, readback and full restoration in the
second session, with zero simulations. The same saved-view conflict on the later system circuit was released.
BGR restarts under `r2-s6-asz-bgr-scratch-s1-r1`, with identical seed and scientific settings; the original failed
attempt remains recorded (4 charged attempts, 0 launches, 0 learner updates). A recovery dispatcher continues
the 12 remaining second-session jobs and reports the untouched first queue. With the completed LDO costs, even
full budgets for all remaining runs plus the failed attempt total at most 17,368 charged evaluations, within
the original 19,200 ceiling. No further automatic retry is enabled. Evidence is in the Round 2 folder's
`recovery/`; the original manifest, code, configs, runtimes and failed run are preserved.

## 7a. Round 3: GraphGPS and CircuitGPS trained on the saved circuit archive

Added 2026-10-13 at the user's request: "train 2 models with all the circuit runs currently saved: one based on
graph gps one based on circuit GPS ... add round 3 ... to compare this two trained models". The user also chose
"Recompute rewards to include all usable runs" when informed that the historical archives contain different reward
configurations. This section adds a new comparison; it does not relabel any earlier GraphGPS or cross-attention run
as a CircuitGPS result. Evidence: `artifacts/local/reviews/round3-all-circuits-2026-10-13/`.

**Execution record (2026-10-13):** the initial inventory covers 408 folders and selects 304 real runs containing
187,407 replay-eligible transition rows and 200,479 charged source evaluations, across 65 saved task variants
(not 65 distinct topologies). Excluded: 83 folders without replay-eligible transitions, 18 model-only archives,
two legacy ngspice archives containing nine transition rows, and one non-quiescent archive. The requests and
`inventory.json` retain every path and reason. Full transition reconstruction/validation follows this inventory.
The sequential offline job started at 03:51 Europe/London: GraphGPS first, CircuitGPS second. GraphGPS completed
20,000 updates at 09:25 and passed checkpoint integrity/reload plus finite, physically legal proposal checks on
all 65 task variants. These are offline checks, not evidence of circuit performance. CircuitGPS loaded all 304
sources but had no training updates when its process was lost across a WSL restart (host boot 12:46). At 13:07
it was restarted with the same request and frozen runtime; its interrupted directory and log were preserved in
`interrupted-20261013T120737Z/`. Preparation finished at 16:56:57, but CircuitGPS failed at 20:54:55 after 10,491
completed updates, while attempting update 10,492. Exact replay identified overflow in the third block's program
root LayerNorm; deep VCO INL trees amplified finite internal values to 7.1e20. The 10,000-update checkpoint already
had overflowing variances despite finite outputs. GraphGPS's completed checkpoint is retained.

The user authorized normalization within the tree and resuming CircuitGPS. Record 7.341 introduces architecture
v2, with non-affine normalization of base and each combined parent state. The original failed directory, checkpoint
and runtime remain unchanged. `tree-normalization-recovery/` contains the separate pinned runtime, explicit full-state
migration from update 10,000, exact-pool index, failing-batch regression and resumed training output. Actor, both
critics and targets use v2; optimizer states, RNG, SAC hyperparameters, rewards, split and sample order are retained.
That continuation was a development recovery with 10,000 legacy v1 updates, unsuitable as a clean v2 training
comparison. It was stopped at the user's subsequent request for fresh training; its last progress report was 10,575
updates, and its checkpoint and log remain available. It did not complete the planned 20,000 updates.

**Fresh retraining (record 7.342, user: "go on train it again"):** `circuitgps-v2-fresh/` starts CircuitGPS v2 at
update zero, seed 0, with newly initialized actor/critics/targets, empty optimizers and temperature 0.01. No failed
or recovered weights enter this run. It reuses the checksummed, read-only 187,407-transition database, exact split,
reward settings, batch size 8 and 20,000-update budget. The complete sampling schedule is checked against GraphGPS's
recorded candidate counts before dispatch and again on completion. The completed GraphGPS model is retained.
Full checkpoints are saved every 500 updates, with permanent initial/10,000/20,000 checkpoints. Held-out diagnostics
cover those three update counts; the initial checkpoint is evaluated after training, with no effect on the fixed
training budget or checkpoint selection. All actor/critic LayerNorm inputs retain numerical overflow guards.

**Execution acceleration (record 7.344, 2026-10-14, user: "optimize it"):** active-parent tree evaluation and raw
packing-layout reuse preserve the v2 mathematical model and fixed experiment settings. A matched CPU benchmark
measures 1.048 → 0.741 seconds per SAC update; checkpoint and full-validation time are separate. An explicit
full-state migration at update **11,000** (2026-10-14 03:05 London) retains the fresh run's weights, Adam states, temperature, RNG and
verified sampler ledger. Both source runtimes and original checkpoints are kept, and the strict loader remains
unchanged. `artifacts/local/reviews/circuitgps-acceleration-2026-10-14/` records the boundary, verification and
process handover. Initial-checkpoint diagnostic weights also have a separately recorded execution migration;
the original initial checkpoint remains intact. Report training cost by execution segment and retain the
implementation digest on diagnostics: float32 arithmetic can differ slightly despite unchanged semantics.

**Offline completion verified 2026-10-14 (record 7.347):** the pair supervisor completed at **06:13 Europe/London**.
Both models finished 20,000 updates and passed checkpoint integrity/reload plus finite, physically legal proposal
checks on all 65 saved task variants. The retained CircuitGPS model is **v2 initialized from scratch, with zero
legacy v1 updates**. The split and sampled-candidate checks passed; no new simulation was used for either source
training. These numerical/archive-fitting checks do not establish online success or transfer.

| Model | Published model run | Final checkpoint | SHA-256 of `model_weights.pt` |
|---|---|---|---|
| GraphGPS | `offline__seed0__0c88320d35bd` | `ckpt-00000000-efdbeba0` | `8fdd0b6d64c51dca4bf518b604a0184c917192a86dffd93a646c6811fb1ca09b` |
| CircuitGPS v2 | `offline__seed0__6bf93f84d1b6` | `ckpt-00000000-c81b34fb` | `1c33a7506cf29e2342008978132eddb32af8bd0050215fceef9197355186486d` |

Published paths are pinned in `pair-status.json`; metadata is available for
[GraphGPS](../outputs/offline-network__0c88320d35bd/runs/general/offline__seed0__0c88320d35bd/checkpoints/ckpt-00000000-efdbeba0/metadata.json)
and [CircuitGPS v2](../outputs/offline-network__6bf93f84d1b6/runs/general/offline__seed0__6bf93f84d1b6/checkpoints/ckpt-00000000-c81b34fb/metadata.json).
The model-file hashes above were recomputed during this plan check. Trainer-local `trained_unqualified` records
precede the separate `round3-review.json` files and completed pair publication; the online comparison is still
outstanding. No failed v1 or mixed-history recovery checkpoint is selected.

`pair-status.json` identifies the completed training directories. The fresh CircuitGPS status/log are
`circuitgps-v2-fresh/training-circuit_gps/status.json` and `circuitgps-v2-fresh/training.log`.
The supervisor recorded final model paths after both models finished, reload/proposal checks passed and identical
splits/sampled candidates were verified. These gates released the now-completed RGCN supplement. Offline retraining has no
simulator entry point; new Round 3 and journal simulations remain planned. This archive-wide training is still a
development comparison, not the prospective journal protocol's unseen-circuit source split.

### 7a.1 Two independently trained models, one frozen source selection

Inventory every currently saved real run in `outputs/`, including earlier experiments, different seeds, both PDKs,
logic cells and recorded optimization failures when their committed transitions are usable. An offline model's
weights are not additional circuit observations: count its underlying source runs once. Calibration/preflight runs
with no replay-eligible transitions cannot train SAC. Record every exclusion, including absent/incompatible schemas,
unavailable input metadata, non-nominal conditions, active archives, corrupt data and tasks with too few episodes
to form a holdout. Never describe a selected subset as literally every saved run; the inventory gives coverage.

Freeze the source paths and archive hashes, and each encoder's reconstructed-input hashes, before training. Both
requests must contain exactly the same source runs and eligible candidate IDs. Split whole run-scoped episodes
within each task, with 10% of episodes held out and seed 0; use the identical split for both models. This includes
all eligible runs in the source pool while reserving validation episodes from gradient updates. A renamed task or
different seed is not a new topology. No Round 3 rollout may enter either frozen source model.
Repeated physical designs can occur in different historical episodes, so this holdout is an archive-fitting
diagnostic, not independent evidence of performance on unseen physical designs.

The original measurements, limits, target kinds, scales, parameter proposals and physical actions remain as
recorded. In a separate training dataset, recompute rewards with the current experiment configuration:
`violation_shape=compressed`, `worst_spec_share=0.5`, `objective_shape=compressed`, `objective_weight=1`,
`margin_weight=1`, `nominal_gate_band=0.5`. First validate each transition under its recorded reward; then rescore
both observations and the transition consistently, and record the original settings and the migration. No original
archive is rewritten. Invalid/missing values retain their recorded masks and failure semantics.

| Setting | GraphGPS | CircuitGPS |
|---|---|---|
| Encoder | `graph_gps` | `circuit_gps`, architecture version 2, normalized tree states |
| Specification representation | Spec set | Structured measurement programs |
| Common physical inputs | PDK-relative sizes, model features, family vocabulary, relative bench features, rule-based net roles and operating-point ratios | Same |
| Missing historical operating points | Masked, never invented or newly simulated | Same |
| Initial network | Fresh weights, pretraining seed 0 | Fresh weights, pretraining seed 0 |
| Initial training recipe | 48 hidden channels, 4 layers, 4 heads, RWSE; 20,000 SAC updates, batch 8 | Same |
| SAC | Gamma 0, learning rate 0.001, initial alpha 0.01, tau 0.005 | Same |
| Sampling | Equal task sampling, same candidate order for the same sampler seed | Same |

Store the reconstructed pool on disk rather than dropping source runs to fit RAM. The same update budget is the
primary comparison; record actual parameters, sampled counts by task/run, training time, peak memory and CPU
resources. Equal widths and updates do not imply equal parameter counts or equal compute. CircuitGPS's different
spec representation and architecture are compared together; an advantage would not isolate either component.
The fixed update budget does not guarantee every transition is sampled; report actual coverage.

Before publication, check both checkpoint hashes, reload both models, check finite outputs and losses, and inspect
held-out critic errors versus each task's training-reward mean. These errors diagnose offline fitting; they do not
measure simulator success or prove transfer. Select the final configured update, without choosing a winner or an
earlier checkpoint from Round 3 test results. The selected model IDs and checkpoint hashes are now recorded above.
If training fails or the fixed budget is infeasible, record that status; do not publish a partial model as completed.

### 7a.2 What the online comparison can establish

With all saved circuits included, this is primarily a **comparison on previously seen circuits using fresh
rollouts**. It cannot support an unseen-topology or unseen-PDK claim for any circuit/PDK present in the source pool.
A genuine transfer extension must use a new topology or independently chosen specifications outside that pool,
fixed before its first evaluation, and report that extension separately.

Use four saved tasks for the initial comparison: RING3 (`real:mscr_ring3`), relaxed LDO1
(`real:graphgps_ldo1`), the DFFRX1 power task (`real:dffrx1_t2`), and the published amplifier's far-start task
(`real:agentic_fc_pub_far`). Together these cover an oscillator, regulator, logic cell and a larger amplifier in
the second PDK. Before dispatch, pin each task's exact saved target list, netlist, bench, start, parameter ranges,
grid and inputs. If a named task has changed or vanished, report it and resolve the selection before launching.

For each encoder and each target seed, compare three independent arms:

| Arm | Initial weights and learning | Budget per arm |
|---|---|---|
| Frozen pretrained | Copy the matching full-archive model; sampled actions, no updates | 300 nominal design evaluations |
| Adapt pretrained | Copy that same model; fresh optimizer and empty target replay; ordinary online SAC | 800 nominal design evaluations |
| Scratch | Fresh network of that encoder; same online SAC settings | 800 nominal design evaluations |

Every task/seed starts from the fixed source checkpoint; no weights or replay carry from a preceding target.
Keep both encoders' targets, starts, reward, action semantics, warmup, update ratio and four isolated simulator lanes
identical. Count initial/reset designs, failed evaluations and retries. Record underlying Spectre launches separately
and pin launch caps before dispatch. Use full budgets (`stop_at_first_feasible=false`) to retain quality and learning
curves; a first pass is also recorded. Counterbalance encoder order across tasks and seeds. Run one training arm at
a time on the shared host; follow `docs/performance-measurement.md` for time comparisons.

**Staging and cost.** First run target seed 0 on all four tasks: 24 arms, at most 15,200 nominal design evaluations.
After checking correctness, complete matched seeds 1 and 2 for the same matrix: 48 further arms, at most 30,400
evaluations; the full three-seed comparison is 72 arms and 45,600 evaluations. Do not repeat only the apparent
winner. If time allows only screening, keep the one-seed result exploratory. No wall-time estimate is asserted
until CircuitGPS's measured update cost and the benches' throughput are available. These are proposed simulation
budgets, not simulations authorized by the request to train offline and add this plan.

**Seed 0 dispatched (record 7.353, 2026-10-15; user: "Chain it after Round 2", "RGCN arm").** The 24 arms of seed 0
are queued in both Virtuoso sessions, each session starting when its Round 2 runs have completed; a job goes to
whichever session is free (`round3-all-circuits-2026-10-13/online-2026-10-15/queue3.py`). The four tasks are as above,
DFFRX1 as `real:dffrx1_t2`. Each arm takes everything but its network from the task's round 1 configuration, identical
in task and start; the network is the general model's (the second input build with operating-point ratios). A third
encoder is added: RGCN, trained offline on the same request as GraphGPS but the network (`request-rgcn.json`), checked
and published like the other two, then the same three arms on the four tasks (12 arms, at most 7,600 evaluations). The
two sessions run side by side and share the host with that training: compare designs to first pass and pass counts,
not elapsed time. Seeds 1 and 2 stay proposed.

**CircuitGPS version 3 arm (record 7.359, 2026-10-17; user: "Queue the 12 v3 arms").** After the v3 training of
records 7.356/7.357, the same 12 arms for a CircuitGPS model at `architecture_version: 3` (frozen 300, adapt 800,
scratch 800 on the four tasks; at most 7,600 designs), each configuration the v2 arm's with only the version and
the model changed; chained: review + publish, zero-simulation qualification, then the two-session queue.

**Session 2 recovery (record 7.354, 2026-10-15, 13:54 Europe/London).** CircuitGPS Ring3 adaptation stopped at
567 charged evaluations / 4,248 updates after a 120-second bridge timeout left one physical launch unconfirmed.
The VM's matching netlist and Spectre completion log proved that launch occurred; its completed simulator process
was stuck exiting and was terminated by its exact PID and start identity. The original failed evaluation stays
failed and charged, with no metrics backfilled. An audited receipt resolves the one uncertainty during exact restore
from `ckpt-00000567-9ed81941`; weights, optimizers, RNG and the 538-entry replay are retained. The same run continues
to its original 800-attempt limit, then the original shared dispatcher takes the remaining jobs. Session 1 and all
frozen runtime/configuration files were preserved. Evidence and the replacement monitor/worker are in
`round3-all-circuits-2026-10-13/online-2026-10-15/recovery/`; `process.json` there identifies the live recovery processes.
At 13:54, the resumed run had advanced to 583 completed evaluations and 4,312 updates, zero unresolved launches and
no additional infrastructure failures. Historical raw receipts retain their original uncertainty; the
`physical_launch_reconciled` event and `resume-reconciliation.json` supply its resolution.

Keep the existing random-search and Bayesian results as labelled historical references. A claim against these
optimizers requires matched new controls under the same tasks/starts/reward/budgets; the optional matrix is four
tasks × three seeds × two optimizers × 800 evaluations = 19,200 additional evaluations, separately authorized.

### 7a.3 Reporting and decision

Report per task and seed: whether any design passes; first-pass design/launch count and wall time; early and late
pass rates; the full best-so-far reward curve; best feasible physical metrics and the task's objective; invalid and
failed evaluations; target learning time; and source pretraining cost. Compare frozen arms over their common
300-design horizon, and adapt/scratch arms over 800; also give all arms' first 300 designs. For each architecture,
compare adaptation with its own scratch baseline before comparing the two pretrained models.

Show the three paired seed outcomes and their median/range, including failures. Do not treat designs from one
run as independent seed replicates. Both pretrained models have only one pretraining seed, so any conclusion is
conditional on those two trained instances. A universal architecture-superiority claim requires independently
retrained source models. Faster feasibility and better final quality are separate outcomes; call ties and tradeoffs
explicitly. The Round 3 result table remains empty until actual new evaluations have completed.

Round 3 supplies development evidence for the journal programme in section 14. Its full-archive models and seen
tasks do not replace that programme's prospective test split, independent pretraining seeds or component ablations.

## 7b. Round 4: the Round 3 models trained further on LOADBench and all saved runs

Added 2026-10-17 (record 7.363, session "Training encoders with Zenodo dataset"). User: "write a plan for round 4 train
loadbench onto rgcn graphgps and circuitgpsv3 s 304 pretrained run trained model then run on experiments like round 3
to see how it works after trained on all my own runs and loadbench knowledge". **A plan only: nothing is built, trained
or run, and no simulation is authorized by it.**

**Revised the same day** (user: "I want to train everything in the loadbench in fastest way", then the choices "Keep 15
out", "LOADBench, then yours" and, for the encoders, "all three wanted but wait for the test speed first"). This
replaces the sample, the mix and the training path of 7b.2-7b.3; the rest stands.

- **Data: all of LOADBench except its 15 test op-amps**, every distinct design of the other 86 (about 75 million; the
  logs list each generation's survivors again: SimpleOpAmp2 has 2,033,664 rows and 879,981 distinct designs, and no
  repeat with different results). The 15 (SimpleOpAmp1, 13, 36, 53, 130; SimpleTwoStageOpAmp_SimpleOpAmp1_1, _33_7,
  _43_9, _47_9, _8_7; SimpleThreeStageOpAmp_SimpleOpAmp1_1_4, _1_2_1, _47_2_pfc1, _54_2_1, _8_1_7) are the offline check
  of op-amps the models never saw.
- **Two stages instead of the 1 : 1 mix.** Stage 1: each Round 3 model learns all of LOADBench once, on the GPU.
  Stage 2: Round 3's own-run recipe from the stage-1 model (the 304-run pool, 20,000 updates, batch 8, CPU). Control:
  stage 2 alone, from the Round 3 model. A 1 : 1 mix over all of LOADBench would show each of the 168,589 own training
  designs about 450 times.
- **A fast path for stage 1.** Measured 2026-10-17 (no simulator): unpacking one stored design costs about 15 ms and
  assembling a batch most of a GPU step, while the GPU's own work is about 0.6 ms per RGCN design. So LOADBench is kept
  as compact per-op-amp arrays (`~/gator/offline-pools/loadbench/`, about 13 GB), and batches are built by GATOR's own
  input code in parallel worker processes while the GPU learns, with large batches. It is checked to give exactly the
  inputs that a replay run of the same designs gives. The batch size and learning rate come from the RGCN batch-size
  check of the same day (no simulator).
- **Encoders** (speed test 2026-10-17, batch 512 on the RTX 4090; GPU-only rates are what fast feeding would reach):
  RGCN 228 designs/s as fed today, about 1,800 GPU-only (one pass over the 75 million designs about 12 h); GraphGPS
  178 / about 490 (about 1.8 days); CircuitGPS v3 43 / about 55 (about 16 days; batch 512 already takes 9.2 GB of GPU
  memory). The user chose "Subset first, then decide": all three first learn the same subset of 20,000 designs per
  op-amp (1.7 million; CircuitGPS v3 about 9 h), and their held-out error curves are compared; RGCN and GraphGPS then go
  on to all the designs, CircuitGPS v3 only if its error is still falling faster than the other two at the subset's end.
  Evidence: `artifacts/local/reviews/round4-loadbench-2026-10-17/speed-test/` (`summary.json`).

**In plain words.** Round 3 trained one model per encoder on 304 saved runs and tried each on four circuits. Round 4
takes three of those models (RGCN, GraphGPS, CircuitGPS v3), trains each further on a mix of the same 304 runs and
LOADBench (an open dataset of 101 SKY130 op-amps, about a million ngspice-simulated designs each), then repeats Round 3's
test on the same four circuits. Two questions: does op-amp knowledge from another process and simulator change how the
models do on the Virtuoso tasks, and does it cost them what they knew?

### 7b.1 LOADBench as a source

Checked 2026-10-17 on the download (`~/Loadbench`, seven zips, 34 GB of op-amp data):

- Leibl, Azevedo et al., MLCAD 2026; Zenodo DOI 10.5281/zenodo.21759759; CC BY 4.0, so it is cited wherever used.
- 101 op-amps: 31 one-stage, 44 two-stage, 18 three-stage, 8 symmetrical; 6-25 transistors (median 16), 0-2 sized
  compensation capacitors (62 of 101 have one); SKY130 low-threshold 1.8 V transistors.
- One ngspice deck per op-amp, the same bench for all 101: 1.8 V, 1 pF load, 10 uA bias (typical corner, 27 C), three
  test circuits (closed-loop transient, open-loop AC, DC output range).
- Per op-amp, the whole NSGA-II log: about 2 million rows (1,000 generations x 2,048) of sizes in um (W, L; the
  multiplier is always 1; capacitors where present) with 14 results (dc_gain, ft, p, phasemargin, sr_neg, sr_pos,
  voffset, icmr_min, icmr_max, vout_min, vout_max, area, cmrr, psrr), sizing-rule margins and flags; plus a Pareto
  front of about 1,000 designs. Matched transistors share their sizes (`param_match.txt`).
- Traps: failed results are stored as numbers (slew +-1e13, phase margin -1.5e7, ft -4.9e12), not blanks; about half
  the rows break LOADBench's own sizing rules (`feasible = False` concerns those rules, not any spec); each deck's
  control block runs shell commands, so a deck is read before it is ever run; its flow was tested on ngspice 44.2 only.
- Its protocol holds out 15 op-amps (five per stage count) from training.

### 7b.2 To build first (workbench and scripts only; no simulation)

Nothing under `src/analog_optimizer/`: the digest stays `6ebf5ba5`, so the Round 3 models keep loading. Each piece
comes with tests, and an independent review precedes any training.

1. **Extraction.** Stream each op-amp's `all_sims.zip` once, never unpacked whole, and drop each file's cached pages
   as it is read: unpacking about 100 GB would fill WSL's file cache, the host-memory squeeze that froze the simulator
   VM. Never while a Spectre run is going. Keep the seeded sample of 7b.3 per op-amp in a small table with the source
   file's SHA-256 and row numbers.
2. **Importer: one LOADBench op-amp -> one GATOR task.** The graph is the op-amp with ONE bench (the open-loop AC
   bench), not the deck's three copies (GATOR's ngspice reader gives 18 transistors for a 6-transistor op-amp and no
   transistor size); the sizes come from `params.cir` (um -> m); matched transistors share one parameter group; the
   SKY130 cells map to the nMOS/pMOS families; each variable's range is its smallest and largest value in the whole
   log, on a 0.01 um grid, the dataset's own resolution, so every stored design lies exactly on the grid; capacitor
   units are checked against the deck.
3. **SKY130 PDK numbers** for PDK-relative sizes and the device-model inputs (minimum length and width, threshold
   voltage, mobility, saturation velocity, oxide thickness of each transistor model's smallest bin), read from the
   dataset's trimmed SKY130 library by a small SPICE-library reader: `device_models.py` reads Spectre libraries only.
   The numbers stay in the local PDK folder, as for the other PDKs.
4. **Measurement descriptions.** One measurement description per LOADBench result, of the same kind the Virtuoso
   amplifier tasks produce (open-loop gain, unity-gain frequency, phase margin, power, slew rates, offset, ranges,
   area, CMRR, PSRR), written from LOADBench's extractor so it says what was measured; signs explicit (sr_neg is
   negative; larger CMRR and PSRR are better). RGCN and GraphGPS read them as a spec set, CircuitGPS v3 as its
   structured programs. Checked column by column against a Virtuoso amplifier task.
5. **Replay runs.** A proposer like the Bayesian one (record 7.304) that proposes the sampled designs in a fixed order,
   and a backend that returns their stored results instead of simulating and refuses any design not in the list. GATOR
   then records each op-amp as an ordinary run archive, which offline training reads with all its existing checks
   (checksums, every reward re-scored). Zero simulator launches. Each design records its dataset file, hash and row;
   the origin stays "real" (they are simulator results), because any other origin would make the models unloadable on
   the real tasks. Stored failure numbers become failed measurements.
6. **Offline training.** (a) Start from a published model's weights (actor, critics, targets, temperature; new
   optimizers), recording the parent: today `cli pretrain` always starts from new weights. (b) A sampler that splits
   each batch between source groups (own runs : LOADBench = 1 : 1), each task equally often within its group: today
   every task is sampled equally, which would give LOADBench's 86 op-amps 57 % of the updates.
7. **A Round 4 results script** in the Round 4 evidence folder, with Round 3's definitions
   (`thesis/figures/round3-extract.py`).

Optional, local CPU only: re-simulate about 20 stored designs on five op-amps with the local ngspice and compare them
with the stored results, as the AnalogGym import did.

### 7b.3 Training (offline; no simulation)

| Setting | Round 4 |
|---|---|
| Starting weights | Round 3's published models: RGCN `6ea424647872`, GraphGPS `0c88320d35bd`, CircuitGPS v3 `bd7263396019` |
| Own data | Round 3's exact pool: 304 runs, 187,407 transitions, 65 task variants; the same split (seed 0, 10 % of episodes held out) and reward migration |
| LOADBench data | 86 op-amps (101 minus its 15 test op-amps); 2,000 designs each, seed 0: 500 from generation 0, 1,000 spread over all generations, 500 from the final Pareto front, repeats removed; 10 % of episodes held out |
| LOADBench goals | Three goal sets per op-amp, each copying the results of one Pareto design drawn with seed 0, so every set is reachable; rows: gain, unity-gain frequency, phase margin, power, both slew rates, offset, area; fixed before training |
| Inputs | Each model's Round 3 inputs unchanged: PDK-relative sizes, model features, family list, relative bench features, rule-based net roles, operating-point ratios (masked: LOADBench has none, like the older own runs); spec set (RGCN, GraphGPS), structured (CircuitGPS v3) |
| Mix | Each batch half own runs, half LOADBench |
| Updates | 20,000 more per model, batch 8, Round 3's SAC settings (gamma 0, learning rate 0.001, tau 0.005); the temperature continues from the model |
| Control | The same continuation on the own pool only, 20,000 updates: tells "LOADBench" apart from "more training" |

Six trainings (three Round 4, three control), one at a time on the CPU, the pool on disk, with Round 3's host-memory
guard (stop below 0.7 GB free on the host). Round 3 measured about 3 h to load 304 sources and, for CircuitGPS v3,
0.5-0.6 s per update on one thread (about 3 h for 20,000 updates).

**Before anything goes online** (offline numbers, not circuit performance): checkpoint integrity and reload; finite
outputs; legal proposals on all 65 own task variants and all 101 LOADBench tasks; the held-out critic error on the
own tasks against the Round 3 model and the control (did it forget?) and on LOADBench's 15 test op-amps and held-out
episodes, before and after (did it learn?). **Gate:** an encoder whose own-task held-out error rises more than 25 %
above its Round 3 model's goes online only on the user's word.

### 7b.4 Online test, as Round 3

- Round 3's seed-0 arms copied in every setting (RING3 `real:mscr_ring3`, relaxed LDO1 `real:graphgps_ldo1`, DFFRX1
  `real:dffrx1_t2`, the published amplifier's far start `real:agentic_fc_pub_far`); only the model changes. Each arm
  runs on the runtime its Round 3 twin used (`gator-runtime-f8ff5ce` for RGCN and GraphGPS, `gator-runtime-7356r`
  for CircuitGPS v3), so that only the weights differ.
- Per encoder and task: frozen (300 sampled designs) and adapt (800, fine-tune) from the Round 4 model. Scratch is not
  repeated: Round 3's scratch arms are the same task, start, seed and settings with no model at all.
- 3 encoders x 4 tasks x 2 arms = 24 runs, at most 13,200 nominal designs, seed 0, both Virtuoso sessions; about
  12-16 h at Round 3's pace (820-1,100 designs an hour).
- Optional: adapt arms from the three control models (12 runs, at most 9,600 designs), only if Round 4's adapt arms
  differ from Round 3's.
- Seeds 1 and 2 stay proposed, for the whole matrix rather than an apparent winner.

Reference, Round 3 seed 0 passes (frozen of 300 / adapt of 800 / scratch of 800; audited from the run records
2026-10-17 with `thesis/figures/round3-extract.py`, every arm complete, parity with round 1 passed):

| Task | RGCN | GraphGPS | CircuitGPS v3 |
|---|---|---|---|
| RING3 | 118 / 305 / 223 | 1 / 276 / 210 | 21 / 281 / 196 |
| LDO1 | 0 / 64 / 0 | 0 / 17 / 0 | 0 / 0 / 0 |
| DFFRX1 | 8 / 196 / 6 | 1 / 10 / 0 | 0 / 0 / 0 |
| Amplifier | 0 / 229 / 353 | 7 / 509 / 27 | 0 / 22 / 0 |

### 7b.5 What it can show, and what is expected (written before any result)

- Round 4 against Round 3 on the same seen circuits: all four are in the own pool, and LOADBench adds no Virtuoso
  circuit. It cannot show transfer to an unseen circuit.
- The amplifier is the only op-amp of the four: it is where LOADBench could help (SKY130 op-amp knowledge reaching an
  amplifier in the second PDK). RING3, LDO1 and DFFRX1 test whether the mix costs anything.
- Expected: at most a small change on the amplifier; none, or a loss, on the other three; frozen arms still weak;
  CircuitGPS v3 still without LDO1 or DFFRX1 passes. One seed decides nothing either way.
- A Round 4 gain that the control matches is a gain from more training, not from LOADBench.
- Reported like Round 3 (7a.3): passes, first pass, the first 300 designs, early and late pass rates; Round 4 against
  Round 3's same arm, and adapt against Round 3's scratch.

### 7b.6 Order, budget and decisions

Order: build, tests and review -> extraction -> replay archives -> (optional ngspice check) -> six trainings ->
offline checks and gate -> online seed 0 -> results record -> seeds 1-2 on the user's word.

Spectre: at most 13,200 nominal designs, 22,800 with the control arms. The user authorizes it; this plan does not.

Decisions, defaults as written above:

1. Start from Round 3's models (the request), not a fresh model on the combined pool.
2. Mix own runs and LOADBench 1 : 1.
3. 2,000 designs per op-amp, LOADBench's 15 test op-amps held out.
4. Goals copied from three Pareto designs per op-amp.
5. The offline control always; its online arms only if Round 4 differs from Round 3.
6. Round 3's scratch arms reused.
7. The Spectre budget of the 24 online runs.

Parked and unchanged: the AnalogGym-Opt SKY130 benchmark (record 7.121: zero passes in 4,800 designs, mostly the 1 us
settling target, with low fixed bias currents in four circuits; 162 s per design under load). Its two decisions stay
open: let SAC vary the bias current and recalibrate, or compare on the MScR circuits in Spectre instead. Its checkout
was lost from /tmp; Round 4 does not use it.

### 7b.7 Results, offline (2026-10-17 to 2026-10-19; record 7.381)

**In plain words.** LOADBench did not help. Three ways of teaching the Round 3 models from it left their error on the
user's own held-out designs where more training on the user's runs alone puts it, or made it worse. The networks did
learn each LOADBench op-amp they were trained on, but almost nothing that carries over to an op-amp they had not
seen: the 77 million designs are 86 circuits, and the user's tasks are new circuits in another PDK. What did carry
over is close to device physics (area, power, unity-gain frequency, the transistors' operating-region margins), not
circuit behaviour (gain, phase margin, CMRR, PSRR). The online test of 7b.4 was not run: its condition, an offline
gain, was not met.

**Run instead of 7b.2-7b.3** (the user's decisions in the revision block above and in records 7.363 and 7.381):

- Extraction of all 101 op-amps: 191,348,736 rows, 90,745,908 distinct designs (77,075,107 in the 86 training
  op-amps, 13,670,801 in the 15 test ones); 63 op-amps hold 365,408 repeated rows with differing results, the first is
  kept. No replay archives: an importer builds each op-amp as a GATOR task from GATOR's own classes (every design step
  passes `Transition.validate`), and the fast path of the revision block builds the batches.
- Batch size by the rule of the revision block (RGCN, held-out error on the own designs at 160,000 designs): batch 8
  0.0100; batch 512 0.0169 (not within 5 %); batch 128 0.0114, and 0.0090 at 320,000 -> batch 128, learning rate 0.004.
- Stage 1 on the subset of 20,000 designs per op-amp (1.72 million), all three encoders, on the GPU: each step pairs a
  design (the action) with another valid design of the op-amp (the state), one of three goal sets and a budget of 1-4
  steps; the critic regresses the reward (gamma 0).
- Stage 2: Round 3's own-run recipe (its exact pool and split, the task-balanced sampler, batch 8, learning rate
  0.001, 20,000 updates, one CPU thread); the control is the same from the Round 3 model. Seeds 1 and 2 only where
  the result hinged on them.
- Option C (user, 2026-10-18: "build it"): the RGCN encoder learns to predict LOADBench's 14 measured results and each
  transistor's sizing-rule margins (one fixed neutral goal set for all op-amps, so the goals cannot give an op-amp's
  level away), then replaces the encoders of the Round 3 model (actor, critics and their targets; the critics keep
  their action layer) before stage 2.
- Not run: the full passes over all designs (stage 1 learned nothing that carried over on the subset); CircuitGPS v3's
  stage 2 (its subset run lost its last part to a helper crash and two resumes to the PC's restart, record 7.381; its
  curve was not falling faster than the others', so it was left at 1,500,032 designs); GraphGPS's option C (each
  attempt was lost: a helper crash, a passing read fault, the PC's restart; one seed could not change the outcome).

**Error on the user's own held-out designs** (Round 3's held-out split, up to 30 designs per task variant, 65 variants;
the critic's mean squared error on the reward, from the start of stage 2 to its end; "ratio" is the median over the
variants of that error over the error of the variant's training-mean constant; lower is better):

| Model | Error start -> end | Median ratio | Beats the constant |
|---|---|---|---|
| RGCN control, seeds 0 / 1 / 2 | 0.00999 -> 0.00826 / 0.00792 / 0.00788 | 0.255 / 0.259 / 0.223 | 61 / 62 / 62 of 65 |
| RGCN stage 1 + stage 2 | 0.444 -> 0.00787 | 0.267 | 61 |
| RGCN predictor transplant, encoder free, seeds 0 / 1 / 2 | 0.1005 -> 0.00785 / 0.00806 / 0.00776 | 0.233 / 0.213 / 0.247 | 61 / 63 / 63 |
| RGCN predictor transplant, encoder frozen | 0.1005 -> 0.01523 | 0.630 | 51 |
| GraphGPS control | 0.01168 -> 0.00929 | 0.286 | 59 |
| GraphGPS stage 1 + stage 2 | 0.335 -> 0.01354 | 0.496 | 48 |
| CircuitGPS v3 control | 0.01454 -> 0.01211 | 0.453 | 54 |

| Against its control (same seed) | Mean error | Better on variants | Geometric-mean error ratio |
|---|---|---|---|
| RGCN stage 1 + stage 2, seed 0 | 0.00787 vs 0.00826 | 31 of 65 | 0.950 |
| GraphGPS stage 1 + stage 2, seed 0 | 0.01354 vs 0.00929 | 3 | 1.714 |
| RGCN transplant, encoder free, seed 0 | 0.00785 vs 0.00826 | 37 | 0.912 |
| RGCN transplant, encoder free, seed 1 | 0.00806 vs 0.00792 | 37 | 0.915 |
| RGCN transplant, encoder free, seed 2 | 0.00776 vs 0.00788 | 31 | 1.025 |
| RGCN transplant, encoder frozen, seed 0 | 0.01523 vs 0.00826 | 2 | 2.163 |

**What stage 1 learned.** On LOADBench's 15 test op-amps the critic's error, as a ratio to each op-amp's own mean
reward (1 = no better than that mean), fell from 2.3 (RGCN), 2.8 (GraphGPS) and 2.2 (CircuitGPS v3) to about 1.0
within 250,000 designs and stayed there (at the end 1.04, 0.97 and 1.02; CircuitGPS v3 at 1.5 million). Meanwhile the
error on the user's own designs rose from 0.010, 0.012 and 0.015 to 0.44, 0.33 and 0.25. On new designs of op-amps it
was trained on, RGCN reached 0.73 with a rank correlation of 0.58; on the test op-amps 0.98 and 0.25. After stage 2
these were 2.01 and 2.64: it forgot LOADBench. A check that the critic reads the proposed sizes rather than the state
(Round 3's RGCN, its own held-out designs, each step's state swapped for another of the same task): ratio 0.31 as
recorded, 0.47 swapped.

**What option C's predictor learned** (RGCN, 3.25 million designs; R^2 within each test op-amp, median over the 15):
area 0.63, power 0.47, unity-gain frequency 0.22, slew rates 0.07-0.09, transistor margins 0.26-0.48; gain -0.20,
phase margin -0.04, CMRR -0.01, PSRR -0.11.

**The rule** (fixed 2026-10-18 22:45 BST, before the results): the transplant "helps" only if its error is below the
control's on all three seeds by more than the spread of the control's seeds (0.00038). **Outcome: it does not help**:
only seed 0 is below the control by more than that (0.00785 against 0.00826); seed 1 is above it (0.00806 against
0.00792) and seed 2 below by less (0.00776 against 0.00788). Typical variants came out about 9 % better in seeds 0 and 1
(37 of 65 better; geometric-mean error ratio 0.912 and 0.915), but not in seed 2 (31 of 65; 1.025): no consistent edge
either.

**Why, and what next.** For a circuit it has not seen, a network can only use what is common to many circuits, and
LOADBench gives 86. Put to the user on 2026-10-19: pretrain only the per-transistor input layers on what carried over,
keeping the circuit-level layers from the user's runs ("option 1"; the user: "try option 1 after the write-up");
describe transistors by their bias point instead of their sizes, so that the PDKs look alike; many more circuits rather
than more designs; use LOADBench as a prior for Bayesian optimisation instead of for SAC.

Evidence: `artifacts/local/reviews/round4-loadbench-2026-10-17/` - `speed-test/`, `batch-check/`, `code/`,
`results/` (`results.json`, `results.md` and every run's small files, written by `code/2026-10-19/lb_results.py`); the
save points stay on the Linux disk in `~/gator/offline-pools/loadbench-r4-runs/`.

### 7b.8 Option 1: only the per-transistor input layers (2026-10-19; record 7.383)

**In plain words.** The per-transistor input layers alone can hold what carried over from LOADBench: with every other
layer of the Round 3 networks frozen, they learned to predict area and power on op-amps they had not seen about as
well as option C's whole retrained encoder. After Round 3's own-run recipe, though, the model ends where the control
ends: in all three seeds within 3 % of the control's error, closer than the control's own seeds are to each other.
It does not help either.

**What** (user, 2026-10-19: "try option 1 after the write-up"). For each of the Round 3 RGCN model's three networks
(actor, both critics; each has its own encoder) only the layers that turn one transistor's or one net's inputs into a
vector learned (`device_values`, `device_kind`, `operating_points`, `net_values`: 13,593 weights per network); the
other 301,488-306,240 weights of each encoder kept their Round 3 values. Two new heads read them: the design's area,
power and unity-gain frequency (from the pooled transistor vectors and the goal context), and each transistor's three
sizing-rule margins. The critics saw each design as both state and proposal; one fixed neutral goal set. 10,000
designs per training op-amp, one pass (860,000), batch 128, learning rate 0.001, 25 min on the GPU. Then only those
layers replaced the Round 3 model's (actor, critics, targets; every other weight checked unchanged), and Round 3's
own-run recipe ran on seeds 0-2 against the RGCN control's seeds 0-2, by the rule of 7b.7.

**Learned** (R^2 within each of LOADBench's 15 test op-amps, median; actor / critic 1 / critic 2): area 0.59 / 0.71 /
0.71, power 0.40 / 0.57 / 0.66, unity-gain frequency 0.01 / 0.35 / 0.11, transistor margins 0.06-0.37 (option C's
whole encoder: area 0.63, power 0.47, unity-gain frequency 0.22, margins 0.26-0.48).

| Seed | Option 1 | Control | Better on variants | Geometric-mean error ratio |
|---|---|---|---|---|
| 0 | 0.00801 | 0.00826 | 35 of 65 | 0.988 |
| 1 | 0.00791 | 0.00792 | 38 | 0.936 |
| 2 | 0.00785 | 0.00788 | 32 | 0.999 |

(Held-out error on the user's own designs after 20,000 stage-2 updates. Stage 2 started from 0.0160, the control from
0.0100: the new input layers first shift the critics' outputs.) **By the rule it does not help**: below the control by
0.00025, 0.00001 and 0.00003, against a control-seed spread of 0.00038. Unlike option C it is never above the control,
but every difference is smaller than the control's own seed-to-seed spread.

**Reading.** What a transistor's inputs carry - its size, hence the area; its share of the bias, hence the power - the
user's own 168,589 designs teach as well; what they cannot teach, how a new circuit behaves, is what LOADBench does not
carry. Round 4 ends here unless one of 7b.7's other options is chosen (bias-point inputs, many more circuits, a prior
for Bayesian optimisation). Evidence: `results/` (now with option 1) and `code/2026-10-19-option1/`.

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
10. **The second build of the network inputs, for step 3b and later** (record 7.317): built on 2026-10-11 in the
    workbench only - three settings of `run.network`, off by default, and the page's third choice "Transferable 2";
    offline training takes them, and takes runs that read operating points. Before step 3b: the backend on 8765
    restarted and the page built; a frozen copy of the code made after the landing; the three nine-design checks of
    6.3b; the 24 configurations (the recorded GraphGPS configuration of each task with the seed and the three settings
    changed, written as JSON and validated with the new copy).

## 9. Budget and time

These are the original planning ceilings and estimates, with the measured RGCN addition. They are not an actual
simulator-launch ledger; failures, interruptions and separately authorized continuations remain recorded separately.

| Step | Runs | Probes | Other evaluations | Planned evaluations | Time |
|---|---|---|---|---|---|
| 1 | 44 | - | 65 (amplifier start) | 35,265 | original estimate about 7 h; RGCN measured 3 h 59 min elapsed; GATv2 estimated 3-4 h |
| 2 | 40 | - | 777 | 32,777 | about 7.8 h |
| 3 | 9 | - | - | 7,200 | about 1.7 h |
| 3b | 24 | - | 27 | 19,227 | about 5.2 h |
| 4 | 12 | 3 | 195 | 10,695 | about 3.2 h |
| 5 | 2 | 1 | - | 1,900 | about 0.75 h |
| 6 | 4 | 4 | - | 4,400 | about 2 h |
| **Round 1** | **135** | **8** | **1,064** | **111,464** | **original estimate about 27.6 h; RGCN measured 3 h 59 min elapsed; GATv2 estimated 3-4 h** |

The RGCN extension consumed `12 × 800 = 9,600` charged attempts: **9,596 actual Spectre launches and four preparation
failures**, with no extra calibration/probe budget. Its measured 3 h 59 min campaign duration includes overlapping
sessions; 5 h 35 min is the sum of active run times. Neither is a controlled speed comparison with the older arms.
Runtime qualification and any later proposed reruns need an explicit separate ledger.

Step 2 as changed on 2026-10-11 (6.2.2): the logic cell's 10 runs and 192 Calibration designs, and the three analog
circuits' 30 runs, 9 baselines and 576 Calibration designs (about 6 h of the first Virtuoso session; the logic cell runs
beside them in the second). Not in the table: the conditional runs of step 1 (800 designs each), round 2 (the old
analog Step 2 estimate of 8,295 is superseded; the authorized logic-cell repeat is 3,200 and the selected Step 6
option is at most 16,000, for 19,200 in all), offline training (CPU hours, no simulation). The original time estimates used
the recorded runs per 800 designs: OTA5t 9-13 min,
RING3 10-24, LDO1 10-16, VCO 36-99, telescopic cascode 17-25 (the upper values are from days the simulator machine ran
slowly); for the published circuits from the rebuilt cells of 7.295 (LDO and reference 10-13 min, system about 27,
amplifier 37-55) - their own 12-design runs took 1.8 to 2.9 s per design on one lane, so these were planning estimates.
At initial planning the logic cell was unmeasured: about 10 min per 800 designs was assumed, 1.8 h for its part of step 2
(10 runs, 192 designs; the library-cell
simulations of its bench rule are single short simulations and are not counted as designs).

Step 3b and step 4's added arm (record 7.317): 24 runs at the recorded minutes per 800 designs (OTA5t about 11, RING3
about 15, LDO1 about 13: eight runs of each) and three more runs in step 4. Reading the operating points on 18 of step
3b's runs and on step 4's is not in these times: it is measured by step 3b's first check. With a run in each of the
two Virtuoso sessions step 3b takes about half its time on the clock. A cheaper form of step 3b is in section 12.

## 10. Order and gates

**Status 2026-10-14:** the offline pair review/publication gate passed and all 12 RGCN supplement runs are complete.
Round 2's 24 repeats (section 7) were dispatched on both checked sessions at 22:14 Europe/London.
Round 3's online matrix remains separate: first freeze the four task
snapshots, source checkpoint/runtime compatibility and paired arm settings, then run the seed-0 correctness stage
only when its concrete simulation budget is authorized. Journal J0's independent test construction and literature
work can proceed alongside that preparation. Round 2's old analog Step 2 proposal is retired; the selected repeats
use new seeds and run identities without overwriting completed historical runs.

The sequence and restart provisions below record the original Round 1 execution plan; they are not pending actions.

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

**Changed 2026-10-11 (record 7.317): step 3b runs after step 3 and before step 4.** Step 4's start models are trained
on step 3b's recorded designs, so step 3b cannot move behind it; step 4's ports can be prepared while step 3b runs.

## 11. What is expected, written before any result

- **Step 1:** no network difference beyond what one seed can show; the new inputs within the rule on OTA5t and the VCO.
- **Step 2:** the multi-target model helps; the old-target model helps only for a small shift. On the logic cell the both-goals
  model has seen both tasks, so it should be ahead of a fresh network from its first designs on each goal; what is open
  is whether one network keeps the two goals apart - whether its power run and its speed run propose different designs
  from the start. On the task it has not met, the power goal at the in-between speed, it should find a pass sooner than a
  fresh network, because the speed run has been in that fast region; whether a fresh network finds a pass there within
  800 designs at all is open.
- **Step 3:** SAC ahead in passes of 800; which finds the first pass sooner is open.
- **Step 3b:** the second build accepted on OTA5t; on RING3 and LDO1 a difference smaller than the spread between
  seeds, so most likely "no difference shown" from scratch. The inputs were made for carrying over, not for learning one
  circuit: if they gain anything, step 4's first-build arm is where it shows.
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

On 2026-10-13 the user expanded Step 1 to the existing **RGCN + SAC**, clarifying "dont use plain gcn, use what my
code have", then authorized "queue it after the circuit gps training". This supersedes the earlier two-encoder
restriction for the 12 Step 1 additions only. The original GT/GraphGPS records, other steps and frozen offline
training inputs retain their scope.

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

On 2026-10-11 (session "Circuit training and SAC RL graph transformer", record 7.317): "fix everything this chat
mentioned for the encoder networks input. update the experiment plan, add a new section step for comparing new and old
encoder input builds. use the new encoder in the next coming experiment step" - read as: the second build of the
network inputs (section 4), step 3b before step 4 (6.3b), and Transferable 2 for every new model from step 3b on.
Proposed with it and not yet confirmed: three seeds and three arms in step 3b (24 runs; a cheaper form is the arms
`full` and `first` only, 15 runs and about 3.3 h, which leaves the general model's inputs undecided); the three "what
follows" rules of 6.3b; the first-build arm added to step 4; the general model without the ratios (6.5).
Confirmed the same evening: "Checks, then all 24" - step 3b in its full form, started 2026-10-11 22:24 in the first
Virtuoso session. And for the page: "No box, after step 3b" - once step 3b's result is in, a new model always takes the
build it accepts and the Network inputs box becomes one line of text; an old choice shows only while a configuration
holds it.

Decided 2026-10-14: three total trials per arm on the amplifier and system in Round 2 (section 7). Open: the library name of the three
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
| Runs, RL models | 1 Networks with the new inputs (step 1) / 2 New targets (step 2) / 3 SAC against Bayesian (step 3) / 3b Input builds (step 3b) / 4 Second PDK (step 4) / 5 General model, unseen circuit (step 5) / 6 General model, AgenticSizing (step 6) / 7 Baselines, calibrations, offline models (plan) / 8 References: recorded runs the plan compares with / 9 Older (before the transfer experiment) |

`artifacts/local/reviews/transfer-experiment-2026-10-10/categorize.py` files everything (idempotent; run again whenever
runs appear). It files the plan's runs by their experiment names, which are therefore fixed here: `tx1-<circuit>-<gt|gps|rgcn>`
(with `-s<seed>`, `-control`, `-cont`, or `-r` for the rerun of a run a fault of the machine ended),
`tx2-<circuit>-<target>-<scratch|old|multi|probe>` (the logic cell as `dffr`: `tx2-dffr-speed-scratch`, `tx2-dffr-power-scratch`, then `tx2-dffr-power-both` and `tx2-dffr-speed-both` from the offline model `tx-offline-dffr-both`),
`tx3-asz-ldo-<sac|bo>-s<seed>`, `tx3b-<circuit>-<first|full|bench>-s<seed>` (record 7.317), `tx4-<circuit>-<scratch|rel|abs|first|probe>`, `tx5-otatc-<scratch|general|probe>`, `tx6-asz-<circuit>-<general|probe>`,
`tx-offline-*` and `tx-prep-*`. The recorded runs the general model trains on stay in "9 Older" until its request is
frozen.

**The renumbering of record 7.305 is applied** (2026-10-10 23:5x, by the session that owns the folders, on that
record's request): the table and the run names above are the new ones. `categorize.py` carries them and was run - the
folders of the old numbering held no run, model or new-target task yet, so nothing but names moved. It files the logic
cell's first task (a name beginning `dffr`) beside the core circuits and its new-target copy (the same name with
`_t<number>`) among the new targets. No run of step 2 or 3 existed at that renumbering; both steps are now complete.


This plan; record 7.301; per step the configurations, compatibility proofs, queue log, `results-<step>.md` / `.json` and
a record entry, in `artifacts/local/reviews/transfer-experiment-2026-10-10/`; the definitions of the new tasks in
`~/mscr_circuits`; the offline models' `pretraining` blocks; the Bayesian optimizer's own record.

## 14. Journal experiments

**Dropped on 2026-10-23** (user: "we are not doing journal experiments right? I am not publishing"): nothing in this section
will be run. It is kept for reference only.

Added 2026-10-13 (Europe/London), user: "add the experiments needed for a journal paper to my experiment plan
and make a timeline to publish by next august". This section defines proposed research work. It does not dispatch
simulations, alter the running models, change optimizer code, submit a manuscript or authorize publication fees.
The journal campaign is separate from the historical steps' encoder restrictions and result-selection rules.

### 14.1 Main question and boundaries of the contribution

**Question:** does representing measurement expressions and their circuit bindings, jointly with devices and
adjustable parameters, improve sample-efficient circuit sizing and transfer compared with a generic graph encoder?
The candidate method is CircuitGPS, described in [circuit-gps.md](circuit-gps.md). Its benefit and novelty remain
hypotheses until the literature comparison and experiments are complete. GraphGPS, graph-based RL sizing and
technology transfer already have predecessors; none alone is the proposed novelty.

The primary claim, if supported, concerns measured optimization efficiency on the specified tasks. Three distinct
results must remain separate: new specifications on known topologies; new topologies within represented circuit
families; and the optional transfer to a PDK excluded from training. A variable-sized input interface is not evidence
of generalization. Keep the SAC algorithm fixed; explicitly explain gamma 0 and immediate reward fitting rather
than implying that the experiment establishes long-horizon credit assignment.

Round 1/2 results and Round 3 are development evidence. The current 304-run snapshot contains 187,407 eligible
transition rows and 65 task variants, not 65 independent topologies. It contains both PDKs and circuits previously
called unseen in older experiments. A source model trained on that snapshot cannot support those older unseen
claims. Selecting repeats only after a promising result, as historical Round 2 does, is unsuitable for the new
confirmatory comparisons: complete all preregistered arms and seeds, including negative results.

### 14.2 J0: freeze the data, benchmarks and protocol

Before new journal training, create a versioned journal manifest separate from Round 3. Record source archive and
input-view hashes, canonical topology/family IDs, PDK, task/specification identity, measurement programs, start,
legal parameter domains, bench/analysis settings, code and dependency versions, seeds, budgets and metrics.

Group aliases, renamed devices, reordered netlists, alternate starts and near-duplicate physical designs by
structural lineage. Deduplicate source candidates and report the source distribution by actual topology/family;
task aliases must not silently multiply a family's sampling weight. Freeze a canonical task map and sampling policy
on development data. Keep physical-design groups together in the source training/validation split; an episode-only
holdout can repeat the same design and is only an archive-fitting diagnostic. Fit any learned normalization on
source training data only. Target PDK documentation and a target netlist are permitted deployment inputs, not target
simulation statistics. Use the existing explicit reward migration; preserve original archives and missing-data masks.

Use the following **six primary test cases**. Each case has one fixed bench, goal vector and start. Exact task IDs,
equations, limits and lineage hashes must be added to the manifest by 13 November, before competing policies are
evaluated; the descriptions below are selection requirements, not six tasks already built.

| Stratum | Cases | Selection and permitted claim |
|---|---|---|
| New goals on known circuits | One previously untrained goal each for OTA5t, RING3 and relaxed LDO1 | Same topology, new goal; remove the test goal from every original/relabeled training example and from tuning. Freeze goals using engineering requirements, not which model wins. |
| New topologies | One amplifier, one regulator and one oscillator topology absent from all source/development archives | Different connection structure, not a renamed circuit or size/start variant. These test within-family topology transfer; no cross-family claim. |

Existing `mscr_otatc`, `mscr_otafc` and the recorded AgenticSizing tasks remain useful development cases. Their
observed results cannot be presented as prospectively hidden tests merely by removing their rows now. If new
topologies cannot be prepared on time, a source-excluded retrospective study is possible, but must be labelled
retrospective and the manuscript's claims and scope revised before testing. Do not silently substitute it.

Keep a separate development suite for tuning, implementation debugging and ablation-width selection. Benchmark
qualification checks measurement validity and physical feasibility against an engineering reference under the
predeclared limits, with equal information given to every method. Charge that cost. It must not rank candidate
methods or tune goals around their outcomes. Once the manifest is frozen, any change creates a new version and
the affected evidence becomes development evidence. No test trajectories flow back into source models.

### 14.3 J1/J2: primary baseline and transfer matrix

J1 is the existing Round 3 comparison in section 7a, kept as a development pilot. J2 is the six-case prospective
comparison. Use three source-model seeds `0, 1, 2` and three rollout seeds `101, 102, 103`, fully crossed for
pretrained methods: **nine runs per method/case**, with three independent source models. Use the same seed mapping
and sampling order across architectures. For scratch, BO and random search, map each `(source_seed, rollout_seed)`
pair to a distinct seed (for example `1000 + 100 * source_seed + rollout_seed`); these are nine independent runs,
not three duplicated controls. Record initialization, sampler and environment seeds separately.

| Method | Modes per case | Source data | Nominal design budget per run |
|---|---|---|---|
| GraphGPS-SAC | Frozen, adapt, scratch | Same J0 source snapshot for frozen/adapt | 300 frozen; 800 adapt; 800 scratch |
| CircuitGPS-SAC | Frozen, adapt, scratch | Same J0 source snapshot for frozen/adapt | 300 frozen; 800 adapt; 800 scratch |
| Port-relational RGCN-SAC | Frozen, adapt, scratch | Same J0 source snapshot for frozen/adapt | 300 frozen; 800 adapt; 800 scratch |
| Trust-region Bayesian optimization | From scratch | No source data | 800 |
| Random search | From scratch | No source data | 800 |

RGCN-SAC is a baseline within our common SAC system, not an exact reproduction of Li's method. BO uses the existing
workbench implementation; random search must be verified against the same legality, measurement and cost contract
before dispatch. Record each method's source-data advantage explicitly. J4 adds an external published comparator.

Pretrain each architecture independently for 20,000 updates, batch 8, using the same source split, rewards and
candidate sequence for a given seed. Nine full source models are required. Existing Round 3 seed-0 models may be
reused only if source selection, split, sampler, configuration and code contracts match J0 exactly; assume fresh
training in the budget. Select the final fixed-budget checkpoint, not the best checkpoint on test outcomes.

Online SAC retains learning rate 0.001, gamma 0, initial alpha 0.01, warm-up 8, eight updates per design, batch 8,
replay 10,000 and episode length 4. For this prospective campaign, adapt uses `reset_temperature=true`, fresh
optimizers and empty target replay, isolating pretrained network weights from a carried temperature. This does not
retroactively change historical steps or Round 3. Frozen uses sampled actions with fixed weights and no updates;
its measurements still count as simulations. Reset each target run to its source checkpoint, never the previous
target's adapted model. Source rehearsal and online reward changes are excluded from the primary comparison.

All methods receive the same initial design, legal bounds/grids, target definitions, reward scales, warm-up protocol
where applicable, failure handling and four isolated simulator lanes. Count resets, failed evaluations and retries.
Run full budgets; record first feasibility without stopping there. Pin raw simulator-launch caps from each bench's
analysis count before execution. Compare frozen methods at the common 300-design horizon; also truncate other
arms to 300 for that comparison. Adapt/scratch/BO/random comparisons use 800.

J2 contains `6 cases × 9 replicates × (3 encoders × 3 modes + 2 optimizers) = 594` arms and at most
`6 × 9 × [3 × (300 + 800 + 800) + 2 × 800] = 394,200` nominal design evaluations.

### 14.4 J3: test which CircuitGPS components matter

Freeze a three-case subset of J2 before results: one amplifier, one regulator and one oscillator, including at least
one new-topology case. Each variant has three fresh pretraining seeds and three rollout seeds per source model,
with the same source data and 800-design adaptation budget. Reuse the full CircuitGPS and GraphGPS J2 arms as
controls only when the complete configuration matches. Record actual parameter counts and compute for every arm.

| Variant | Single intended change | Question |
|---|---|---|
| A1: no measurement programs | Retain scalar spec values, bounds, scales and masks; disable expression-tree information and its expression-dependent messages | Does the measurement-program pathway add information beyond numerical specs? |
| A2: no circuit bindings | Retain the ordered expression tree but remove probe-to-net/device bindings and the messages using those bindings | Does grounding measurements in the circuit help? |
| A3: no motif pathway | Disable motif tokens/messages; retain device, spec and parameter pathways | Do the conservative structural motifs help? |
| A4: capacity control | Reduce CircuitGPS width on development data to the closest valid size within 10% of GraphGPS's actor-plus-critic parameter count, if achievable | Can any advantage survive comparable model capacity? |

A1 and A2 are related pathway removals, not perfectly independent mathematical factors; describe their exact
effects. Recompute parameter totals after removal. If the 10% capacity target cannot be met, report the closest
configuration and mismatch rather than calling it matched. Retain the full-size model comparison as well.
The selected width must never depend on test performance. Add a secondary comparison under one common wall-time
cap fixed from development timings, using time-stamped prefixes of the same runs; do not select that cap after
seeing the ranking. State explicitly whether source-training time is included.

J3 adds `3 × 4 × 9 = 108` adaptation arms, **86,400** design evaluations and twelve source models. These toggles
are planned work, not existing UI controls. Implement and validate them in a separately frozen research runtime;
preserve the original optimizer/runtime used by current checkpoints. Retrain each variant, rather than removing
components only at inference and attributing the resulting distribution shift to training-time utility.

Offline correctness checks also cover permutation/renaming invariance, ordered subtraction/division, different
probe bindings, equivalent unit conversions, missing values, variable action counts and candidate legality.
Report unsupported measurement expressions and resolved-binding coverage by task. Attention plots or a changed
output are not evidence of improved circuit performance; the controlled online comparisons provide that evidence.

### 14.5 J4/J5: external comparison and circuit validation

**J4, published comparator:** by 31 October, inspect the full papers and runnable implementations of DEGT,
GCN-RL and the RGCN LDO work; choose one closest reproducible comparator and pin its version and justified
adaptations. Reserve three fixed J2 cases × nine runs × 800 evaluations = **21,600** evaluations. Any required
source training uses the same permitted data or is separately costed and labelled. Its independent training seeds
must be reported. Do not silently replace its algorithm with ours and call it a reproduction. If no suitable
implementation is obtainable, record the evidence gap, use the matched RGCN/GraphGPS controls, narrow comparative
claims and review venue readiness; arbitrary numbers from different PDKs/benches are not a head-to-head baseline.

**J5, nominal recheck:** for each J2 adaptation/BO/random arm (five methods), select up to three distinct physically
legal candidates by a frozen rule: feasible first, then best task objective, then hard-spec violation for infeasible
candidates. Rerun with the reference-accuracy bench. Maximum `6 × 5 × 9 × 3 = 810` evaluations. Preserve the
selection even when a recheck fails; report both original and rechecked metrics. Frozen/scratch winners used for
a headline physical-design claim also require the same recheck, charged to the contingency reserve.

**PVT extension, conditional:** qualify appropriate process models, voltages and temperatures first. The current
generated tasks do not automatically support the workbench's historical five-corner flow; do not reuse the old
1.0 V OTA corner values for 1.8 V devices or another PDK. On two preselected eligible cases, check the same five
methods, nine replicates and up to three nominees at five frozen conditions: at most **1,350 condition-design
evaluations**, plus qualification cost. This is a separate budget unit from nominal evaluations. Corners are never
used to reselect the nominal finalists or update training. Unsupported or incomplete conditions remain explicit.

PVT is required if the manuscript claims robustness to those conditions; otherwise keep a nominal-only scope and
state the limitation. Monte Carlo mismatch/yield and post-layout parasitics are optional extensions requiring their
own implemented/qualified flow and budget. Neither exists merely because nominal optimization succeeds. A first
algorithm paper need not wait for silicon, but must not imply silicon, yield or post-layout validation it lacks.

### 14.6 Optional extensions, selected before their test results

| Extension | Fixed comparison | Added ceiling and dependency |
|---|---|---|
| X1: excluded-PDK transfer | Three existing ports (OTA5t, RING3, LDO1), GraphGPS/CircuitGPS frozen/adapt/scratch plus BO/random; nine replicates each | 216 arms, 145,800 nominal evaluations; six new source models trained with **all** target-PDK runs excluded. Historical port results make this a retrospective benchmark unless new ports/goals are frozen prospectively. |
| X2: missing operating points | Three preselected cases, both encoders with OP inputs consistently masked during training and evaluation, compared with full-input J2 arms | 54 adaptation arms, 43,200 evaluations; six source models. Physical bench measurements remain available for grading. |
| X3: source-data scaling | Nested 25%, 50%, 100% source partitions stratified by topology/task, both encoders, three cases and nine replicates; fixed updates | 108 extra adaptation arms, 86,400 evaluations for the two smaller fractions; twelve source models. Full-data controls come from J2; report coverage/repeated sampling. |

These extensions do not enter the core total. Prioritize X1 only if a cross-PDK claim is essential; otherwise
complete the core first. Do not choose a subset of extensions after inspecting their test results. More circuits
or seeds require a revised budget before dispatch. DFFRX1 and the large published system remain useful stress
cases, but need not expand the first analog-sizing paper's central claim.

### 14.7 Metrics, uncertainty and what would support a claim

The primary comparison is **CircuitGPS adaptation versus GraphGPS adaptation**, separately for new goals and new
topologies. Secondary comparisons are each encoder versus its own scratch, RGCN, BO/random and J4, followed by
ablations. Use the identical raw physical pass criterion across methods, independent of the learned critic.

For every case/method/seed, record all-spec success by 300/800 designs, evaluations and wall time to first feasible
design, best-so-far reward/violation, best feasible physical objectives, invalid/failed designs, early/late pass
rates, optimizer compute and end-to-end time. Show sample-efficiency and time-efficiency separately. Show all cases,
including impossible or unsuccessful ones; average cases equally rather than weighting by their archive size.

Runs without a pass are right-censored at their budget, not successes at the last design and not omitted. For
a finite summary use the mean of `min(T_first_feasible, B)` with the censoring indicator and success fraction beside
it; when all runs fail the success median is undefined. Report conditional-on-success times only alongside success
rates. Final objective comparisons must retain unsuccessful runs as failures rather than comparing only survivors.

Report source-seed and rollout-seed variation separately. Nine rollouts sharing three pretrained models are not
nine independent pretraining replications. Use paired contrasts and 95% intervals with source-seed clusters and
rollouts nested within them; three source seeds give limited precision, so show raw results as well. With three
cases per stratum, restrict conclusions to that benchmark, not all circuit topologies. If significance tests are
used, preregister them and correct the two primary stratum tests together; do not test every curve point for a win.

A useful engineering target is at least a **20% reduction in capped evaluations to feasibility**, without more than
a **5 percentage-point loss in success rate**, versus GraphGPS adaptation. These are proposed practical thresholds
to freeze before results, not observed improvements or journal acceptance criteria. Inspect paired intervals and
per-case consistency; an uncertain, tied or mixed result is reported that way. Failure of the broad hypothesis may
support a narrower well-evidenced result, but does not justify selecting only favorable circuits or inventing a win.

Report actor/critic parameter counts, training updates, peak memory, preprocessing/training/inference time, hardware,
threads and simulator lanes. Report historical source simulation cost, new qualification/evaluation cost and all
failed/retried work. Give both reuse-of-an-existing-model cost and total cost from building the source dataset;
estimate the number of deployments needed to repay pretraining only when measured savings are positive.

### 14.8 Budget, feasibility gate and evidence package

| Core work | Runs or checks | Maximum new nominal design evaluations |
|---|---|---:|
| J1: complete existing Round 3 development matrix | 72 arms; counted once, not added twice | 45,600 |
| J2: six-case primary matrix | 594 arms | 394,200 |
| J3: four variants on three fixed cases | 108 arms | 86,400 |
| J4: one published comparator on three cases | 27 arms | 21,600 |
| J5: nominal finalist rechecks | Up to 810 | 810 |
| Qualification, development pilots and tuning | Separate ledger, fixed allowance | 10,000 |
| **Core planning ceiling** | **801 optimization arms plus checks/development** | **558,610** |
| Infrastructure reruns and reviewer/check reserves | Separate ledger; no extra seeds selected for favorable results | 112,000 |
| **Core plus reserve** | Optional X1-X3/PVT excluded | **670,610** |

The 112,000 reserve is roughly 20% of the core. These are design-evaluation ceilings, not raw Spectre-launch caps:
a candidate can require several analyses. Derive and freeze each block's raw-launch cap from the actual bench,
and stop at whichever cap is reached first. No simulator work is authorized merely by this table. If J1 controls
from section 7a are separately run, add their 19,200 evaluations explicitly; they are not required twice by J2.

The separately authorized Step 1 RGCN supplement (6.1.1) adds 9,600 development evaluations outside this table.
Budgeting it together with the journal core gives **568,210**, or **680,210** including the existing reserve,
before optional extensions or separately selected J1 controls. It does not replace J2's prospective RGCN arms.

Core source training comprises nine J2 models plus twelve J3 variants: **21 jobs / 420,000 updates**, before J4's
method-specific training. Preparation/validation time, failed attempts and any development tuning also count.
An identical existing job can reduce new work but never erase its historical cost. Do not translate update counts
into an ETA from the small warm-batch microbenchmark.

By 6 November, measure full-arm throughput on development tasks, including CircuitGPS updates, cold preparation,
I/O and simulator latency under the shared-host protocol in [performance-measurement.md](performance-measurement.md).
Record available hours/day and expected interruptions. For scale only, 558,610 designs at an effective 1 / 5 / 15
seconds per design consume about **155 / 776 / 2,328 execution hours**, before source training and reserve. These are
arithmetic scenarios, not throughput predictions; four lanes are already reflected if that effective rate was
measured with four lanes. Do not divide by four again.

Proceed with the full matrix only if measured availability supports completion by 15 January. Otherwise reduce
scope **before viewing prospective test outcomes**: defer X1-X3/PVT first; then predeclare one three-case stratum
and restrict the paper to that claim, or obtain additional resources. Do not hide an incomplete matrix, remove a
failed seed or shorten only the slower method. Recalculate all ceilings in a dated amendment before launch.

The future evidence folder is `artifacts/local/reviews/journal-circuitgps-2026-2027/` (to be created when execution
is authorized). Save a manifest, configs, source/checkpoint hashes, the full run ledger including interruptions,
raw physical outcomes, preprocessing/timing records, comparison tables and a reproducible analysis command.
Prepare the manuscript's benchmark/split table, method/ablation table, success and best-so-far curves, cost table
and failure cases from those records. A shareable reproduction subset should use an open PDK if available;
commercial PDK files are not part of the public package. Keep publication analysis outside production run data.

### 14.9 Literature and venue checks

Starting reading list, checked 13 October 2026:

| Work | Relevance to establish before writing a novelty claim |
|---|---|
| [AutoCkt, DATE 2020](https://arxiv.org/abs/2001.01808) | RL sizing, specification generalization and parasitic-aware evaluation already exist. |
| [GCN-RL Circuit Designer, DAC 2020](https://arxiv.org/abs/2005.00406) | Graph-based RL with topology and technology transfer is a direct predecessor. |
| [GraphGPS, 2022](https://arxiv.org/abs/2205.12454) | Credit the general graph-transformer architecture; circuit application alone is not the proposed novelty. |
| [Li and Chan Carusone, ICCAD 2023](https://www.zonghaoli.com/docs/ICCAD2023.pdf) | Relational graph encoding and reproducible LDO sizing in SKY130. |
| [DEGT, ISLPED 2025](https://csdl.postech.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=253) | Close graph-transformer/transfer predecessor; publication verified, full methodology still to inspect. |
| [AnaCraft, TCAD, online 2025 / issue 2026](https://ieeexplore.ieee.org/document/11063353/) | SAC-based sizing, model-based efficiency and PVT robustness; distinct from our nominal model-free protocol. |
| [AgenticSizing, September 2026 preprint](https://arxiv.org/abs/2609.25873) | Topology-aware LLM sizing and benchmark context; peer-reviewed acceptance not established by its arXiv record. |

For each, record representation, spec semantics, action interface, source data, generalization split, seeds, actual
simulation budget, code availability and experimental limitations. Refresh the search before submission; this is
a starting comparison, not an exhaustive novelty clearance. Published numbers on different benches/PDKs remain
context, never a numerical claim of superiority over the paper.

**Provisional first venue: IEEE TCAD**, subject to a contribution/evidence review with the supervisor/coauthors.
Its [submission instructions](https://ieee-ceda.org/publications/tcad/tcad-paper-submissions) require original
design-automation contributions and adequate related-work/comparison evidence. They currently specify a 14-page
regular-paper limit and a disclosure of generative-AI use. Plan those into the manuscript and recheck at submission.
[TCAS-I](https://ieee-cas.org/publication/TCAS-I) is an alternative if the contribution is principally circuit
methodology/insight. [IEEE Access](https://ieeeaccess.ieee.org/authors/stages-of-peer-review/) is a potential
schedule-oriented alternative; its stated 4-6 week publication target is not a guaranteed decision or acceptance.
Check the then-current fees and whether the venue satisfies the user's institutional requirement before selection.

## 15. Timeline to August 2027 publication

**Dropped on 2026-10-23** with section 14: there is no publication target. Kept for reference only.

All dates use Europe/London. Since the user specified a month, use **31 August 2027** as the planning endpoint.
Assume the desired outcome is an **accepted, publicly available online journal article** by then; a preprint,
submitted manuscript, acceptance letter and assigned print issue are distinct milestones. Confirm which one the
institution requires during October. This schedule manages the work we control; peer review, acceptance and
publisher production remain external dependencies, and a rejection or multiple revision rounds can miss the date.

### 15.1 Dated milestones and completion criteria

**Progress on 14 October:** the existing Round 1 arms, the RGCN supplement and both archive-trained source models
are complete. Their completion clears the existing-training part of the 13-23 October milestone only. The paper
outline, claim-to-evidence map, coauthor/venue decisions, new test cases and J0 freeze remain outstanding. The next
dated gates remain **31 October** for literature/comparator/test-case selection, **6 November** for measured
feasibility, and **13 November** for the frozen protocol. The January submission and August publication targets
are unchanged; current completion does not establish that the larger journal matrix fits the available compute.

| Date/window | Work and dependency | Required output / decision |
|---|---|---|
| **13-23 October 2026** | Audit existing evidence, finish the already authorized source jobs, draft paper outline; identify coauthors and institutional deadline meaning | Claim-to-evidence map, source inventory, writing owner and proposed venue; current models labelled development evidence |
| **By 31 October** | Read closest methods, select J4 comparator, choose six test-case candidates and an independent development suite | Related-work matrix, comparator feasibility, test construction list and nominal/PVT scope decision |
| **By 6 November** | Qualify timing and estimate the full budget; implement missing research controls and validate them before freezing source models | Measured compute/simulator schedule, interruption/recovery check, revised scope if the full campaign will not fit |
| **By 13 November** | Complete J0 after qualification; freeze topology/goal split, seeds, metric analysis and all J3 case selections | Versioned protocol and dispatch budget; no target-policy results used in freezing decisions |
| **14-20 November** | Train and verify the nine J2 source models under J0; begin the twelve J3 source variants as resources permit | Pinned, reloadable checkpoints for all three source seeds; source cost and diagnostics recorded |
| **21 November-18 December** | Execute all J2 arms, record daily completion and failure ledger; finish J3 source training and write methods/benchmarks in parallel | Complete primary matrix, including negative/failed runs; draft methods and benchmark description |
| **19 December-8 January 2027** | Complete J3/J4 and finalist checks; run only the optional extensions chosen in advance if schedule allows | Component evidence, external comparison and physical rechecks; protected holiday/host-availability allowance |
| **By 15 January** | Freeze experimental results and reproducible analysis; resolve integrity issues rather than chase a better score | All claimed comparisons complete, uncertainty/cost tables and limitations; new exploratory ideas deferred |
| **16-24 January** | Full manuscript review by supervisor/coauthors; check claims against raw records and venue fit | Submission-ready draft, figures/tables, references and reproducibility material |
| **Target 31 January; latest planned 15 February** | Submit after coauthor approval and current author-guideline check | Submission receipt; results version fixed. Slipping past 15 February increases August acceptance/publication risk |
| **February-April** | External review window, not a predicted decision date; keep scripts and environments runnable | Respond to editorial queries; prepare an issue list without modifying the submitted evidence silently |
| **Within 2-4 weeks of a revision request** | Address each comment, execute justified new checks and obtain coauthor review; obey the editor's actual deadline | Point-by-point response, tracked manuscript and supplementary evidence; budget any new simulations |
| **30 April decision checkpoint** | Assess actual editorial state and deadline risk with coauthors | Continue a credible revision path, or after rejection/confirmed withdrawal choose a suitable alternative; no concurrent submission |
| **May-June** | Finish further review/revisions; if changing venue, aim to resubmit by 31 May | Corrected manuscript or new submission; no assumption that a faster journal will accept it |
| **Target by 30 June** | Desired acceptance milestone to leave production buffer | Acceptance letter if achieved; otherwise record the August target as at risk |
| **July-15 August** | Final files, proofs and permitted supporting-material release after acceptance | Publisher-ready materials and online publication/DOI when available |
| **By 31 August 2027** | Check against the institution's actual requirement | Record acceptance and online-publication dates separately; if not accepted, report the true status and revised schedule |

The November/December tasks may overlap only where dependencies permit: paper writing and analysis tooling can
proceed while experiments run, but no test-driven tuning is allowed. The experiment throughput gate must reserve
time for December/January availability, host restarts and failed infrastructure. More compute is useful only when
simulation and learner concurrency remain comparable across methods.

### 15.2 Decisions that protect the deadline and the evidence

- **Scope by 6 November:** favor the six-case nominal representation/transfer paper over a broad framework claiming
  every circuit family, PDK, PVT, layout and LLM capability. Reduce scope prospectively if measured throughput requires it.
- **Scientific review by 18 December:** judge the completed primary matrix as a whole. If CircuitGPS has no reliable
  advantage, retain all results and consider a narrower supported mechanism/efficiency finding. A useful negative
  result still needs a substantive contribution; changing the title does not guarantee publication. Any redesigned
  method needs a fresh prospective test and an explicit schedule revision.
- **Writing throughout:** draft related work and methods in October/November, benchmark definitions when frozen,
  and results only from recorded evidence. Do not postpone the first complete draft until February.
- **Venue review before submission:** confirm novelty, comparison quality, page limits, coauthor approval and the
  institution's venue requirements. Have a suitable alternative in mind, without submitting to two venues at once.
- **Reviewer allowance:** retain the 112,000-evaluation reserve and a working frozen runtime. A new experiment
  requested by reviewers needs a concrete budget; the reserve is capacity planning, not an automatic launch.
- **No automatic journal switch:** the April checkpoint prompts a decision using actual review progress; an active
  promising revision should not be abandoned solely because a calendar date was reached. After a venue change,
  allow for a fresh review and production cycle. A preprint is useful dissemination but does not fulfill a journal
  acceptance/publication requirement by itself.

Progress checklist: `[x] existing Round 1 arms complete (14 October)` · `[x] archive source pair complete (14 October)` ·
`[ ] J0 frozen` · `[ ] J1 online development comparison complete` · `[ ] J2 all arms complete` ·
`[ ] J3 ablations complete` · `[ ] J4 comparator or explicit gap reviewed` · `[ ] J5 rechecks complete` ·
`[ ] results/analysis frozen` · `[ ] manuscript approved` · `[ ] submitted` · `[ ] accepted` · `[ ] online`.
Update completion dates only when the corresponding evidence exists. This plan edit creates no scheduled reminder
or background experiment launcher.

## 16. Matched archived-data comparison: TuRBO transfer, Pareto MOBO and RL

Added 2026-10-21 at the user's request; **plan only**. The implementation handoff is
[plan-bo-mobo-rl-archive-comparison.md](plan-bo-mobo-rl-archive-comparison.md).

It specifies a bounded same-circuit archive-reuse study on the published LDO, published amplifier and DFFRX1:
TuRBO with archived observations, constrained qLogNEHVI, and GraphGPS-SAC adapted/frozen from the same source
bundle, with cold TuRBO as a fixed-target control. Separate fixed-target and Pareto panels use 800 new-call caps;
four-goal portfolios share that cap. Archive-known solutions count at zero new calls. All transfer methods use
the same at-most-600-design source training bundle per circuit and fresh compatible models.

Three paired replicates give 81 analysis cells and 72 distinct searches (identical MOBO trajectories serve both
panels), at most 57,600 search launches, 15 shared qualification launches and 216 finalist confirmations:
**57,831 nominal launches maximum**, subject to verification of each bench's invocation count. Seed 0 across the
complete matrix is capped at 19,287 including its qualification/confirmations. Optional controls have a separate
budget in the handoff. No simulation is authorized or launched by this plan.

Refined the same day from the chat **Compare random forest calibration** (record 7.387). The comparison now
explicitly asks whether SAC adds value over matched transfer BO and separates graph representation from policy
learning. An archive-only RF diagnostic adds no simulations; reward Calibration, measured functioning and target
feasibility remain distinct, and standalone Calibration rows cannot bypass replay/source eligibility. Optional
Panel A extensions are graph-prior TuRBO (7,227 extra launches) and a common RF-screen wrapper for all four transfer
arms (28,908 extra). Primary plus both extensions is at most 93,966 launches, excluding the separate cold controls.
These extensions require frozen recipes and their own elected budget; the primary 57,831 ceiling is unchanged.

This development study leaves the active Round 3 queue and sections 14-15's prospective journal protocol intact.
It can guide optimizer choice for compatible archive reuse; it cannot establish unseen-topology/PDK transfer.

## 17. Amendment (2026-10-30): the reverse port, from the second PDK back to GPDK045 (9 source trainings, 9 runs, 3 probes)

Written on 2026-10-30 on the user's decision, before any run. The user chose this instead of adding seeds 1 and 2
to Step 4 ("dont add new seeds but try to reverse from pdk-b to pdk a"). Step 4 stays as it is; this section adds
the opposite direction with the same rules.

- **Question.** Does a model trained on a circuit in the second PDK help on the same circuit in GPDK045? Step 4
  answered the forward direction with one seed per arm (6.4); the reverse direction says whether the gain depends on
  which process the model learned first.
- **Source archives (fixed now).** The Step 4 scratch run of each port, and only that run: `tx4-ota5t-scratch`,
  `tx4-ring3-scratch`, `tx4-ldo1-scratch` (800 designs each, second input build with operating points; run identities
  in `thesis/figures/data/round1-transfer-results.json` of the thesis repository). The fine-tuned Step 4 runs are
  excluded as sources: their proposals came from GPDK045-trained policies and would blur the direction. The forward
  source had 2,400 designs (three Step 3b runs); the reverse has 800. This asymmetry is stated, not repaired. If a
  matched size is wanted later, two more scratch seeds per port (3 x 2 x 800 = 4,800 evaluations) come first, as a
  separate decision.
- **Source models.** Three per circuit, as in Step 4: relative (full second build), absolute (sizes in micrometres,
  no device descriptors), first build. The offline recipe of the Step 4 models (20,000 updates, batch 8, learning rate
  0.001, gamma 0, initial alpha 0.01), final checkpoint, no selection by target results. Nine trainings, about 20-25
  minutes each on one CPU: 3-4 hours, no simulation.
- **Targets.** The GPDK045 tasks of Step 3b with their saved limits: `mscr_ota5t`, `mscr_ring3`, `graphgps_ldo1_t2`.
  Their scratch references already exist and cost nothing: Step 3b's `full` arm, seeds 0-2 (649 / 572 / 601 feasible
  designs on OTA5t, 235 / 86 / 182 on RING3, 9 / 0 / 0 on the eased LDO1), plus the first-build seeds. So the reverse
  comparison has three scratch seeds per circuit where Step 4 had one. Second asymmetry, stated: Step 4's port limits
  came from the rank rule on each port's own random designs; the reverse targets are the GPDK045 tasks' existing
  limits.
- **Runs.** Per circuit: three fine-tuned runs (relative, absolute, first build) of 800 evaluations and one frozen
  probe of the relative model, 300 evaluations; rollout seed 0 as in Step 4. Total 9 x 800 + 3 x 300 = 8,100
  evaluations, about 0.9-1.3 days of simulator time. Minimal variant, if time is short: relative fine-tune and probe
  only, 3 x 1,100 = 3,300 evaluations, about 0.4-0.5 day.
- **Rules.** The three rules of Section 5 as Step 4 used them, read against the scratch seeds: a model *helps* when its
  early share is at least 30 points above the median scratch early share (the comparison against each seed is also
  reported), *ends as well* when its late share is at most 5 points below the median scratch late share, and *does not
  deteriorate* when its late share is at least its early share minus 10 points. No rule is changed after a result.
- **Runtime and settings.** `gator-runtime-7317` (Step 4's), the Step 4 online settings unchanged, the same input
  builds; the GPDK045 tasks passed their nine-design operating-point checks in Step 3b.
- **Reporting.** A table beside Step 4's (every arm, early and late share, first pass, feasible designs), the
  reverse-direction paragraph in the results chapter's process-transfer section, one sentence each in the discussion
  and the RQ4 answer. The thesis names both processes from its revision 25 on (the user's decision of 2026-10-30);
  this repository keeps the aliases.
- **Not in this amendment.** Seeds 1-2 of Step 4; new ports; limit changes; any tuning on target results.
