# Plan: one general network from all saved experience, then the six circuits from a third start (2026-10-06, record 7.230; rewritten as record 7.232)

User: "write the plan is it possible to train one general network with all the previous saved experience and then compare
the six cases with different starting design parameter and starting seed from scratch and load the general network. how
to avoid policy drift?" Then, after asking what arm O and leave-one-out do and whether a more complex op-amp added to the
library could serve as the held-out test: "rewrite the plan" and "arm o trim to only ota5t circuit".

Status (2026-10-07 afternoon): the required experiment, the OTA8m follow-up, the equal-recipe arms and the two held-out
circuits built for the purpose (section 23, record 7.262) are complete.
The required experiment used 14,556 new launches; the follow-up added 1,388, for 15,944 total.
All six start-C baselines qualified with 64 random draws each (391 launches including reset overhead).
Sections 20 and 22 hold the final results; earlier sections retain the historical protocol and execution record.
For future encoder comparisons, use the [six-circuit A/B/C run plan](plan-encoder-baseline-abc.md):
matched scratch/fine-tune recipes, an explicit six-family source pool and fixed baseline variants.
That prospective plan does not replace the original experiment's results or authorize new runs.
The recommendations in D1-D6, D8-D10 are the initial implementation settings; D7 and optional phase 3b stay conditional.
New tasks, baselines and comparison runs remain subject to the technical gates below, not another start confirmation.
The historical inventory numbers below were read from
the recorded runs under `outputs/` and from the source at commit `2cba8c6` (optimizer digest `0b0808bc`). The execution
audit corrected the registry count and the phase-3 topology claim below. Arm O is one run, on ota5t, a check of the offline
method (it repeats 7.229's question); phase 3 is a held-out compensation variant (section 6) instead
of leave-one-out. Section 10 records the initial settings and conditional decisions; sections 4 and 8 name
which steps would and would not change the optimizer package. Section 12 tracks execution evidence.

---

## 1. The questions, in plain words, and the short answers

Three questions are in the request:

- (a) Can ONE network be trained from everything the workbench has recorded, without new simulation?
- (b) Does loading it help the six circuits (ota5t, ota7t_w, ring3, vco_lin_c, ldo1_rgcn, ldo2_rgcn) when each starts
  from a third starting design with a third seed, compared with training from scratch?
- (c) How is the loaded policy kept from drifting away from what it knew while it adapts to the new task?

Short answers:

- **(a) Yes.** Everything one training step needs is archived: every run keeps every transition with both of its states
  (`data/transitions`, `data/states`), and `TrajectoryLoader(run_dir).transitions()` rebuilds the optimizer's
  `Transition` objects from them, independent of replay snapshots. `SACLearner.update` accepts a batch of transitions of
  different circuits: the graph batch handles different topologies, and the code checks only the reward settings, the
  condition policy and the origin of each transition. The one input all circuits must share is the spec registry (the
  goal input of the network): one shared registry replaces the per-task ones (section 3). 22 recorded runs, 17,124 Spectre
  evaluations over 15 tasks of nine named circuit variants, share today's reward settings and pool as they are; 8 older ota7t runs (4,326
  evaluations) were recorded under earlier reward settings and would need their rewards recomputed first. The recommended
  training method uses the existing learner unchanged: nothing in `src/analog_optimizer/` changes, the cost is about an
  hour of CPU, no Spectre launch.
- **(b) It can be measured the way record 7.229 measured fine-tuning:** six new start-C tasks, two arms each (scratch,
  load-general), seed 2, 800 launches, the criteria of 7.229 plus a "no drift" criterion. 9,600 Spectre launches, about 5
  hours. One extra run on ota5t (a model of ota5t's own data, trained offline) checks that the offline route keeps the head
  start 7.229 measured live. A new Miller-compensation variant (section 6, 1,965 launches) tests a limited graph change
  outside the pooled circuits; it does not introduce a new amplifier family.
- **(c) Policy drift** here means: the loaded model loses part of what it knew while its weights are updated on the new
  task. Record 7.229 saw it on ldo1_rgcn (27 % of the first 100 own proposals passed, 7 % of the last third). The lever that
  attacks the cause (rehearsal: keep drawing half of every update batch from the pooled experience) is a workbench engine
  change, not an optimizer change; three further levers are settings that exist today; the regularizers of the literature
  that would change the optimizer are listed and not proposed (section 8).

What "general" means and does not mean. The network reads the circuit graph and the Specs rows, so one network can serve
many circuits: that is what the graph encoder and the spec context exist for. Trained on these nine circuit variants it is general
over THEM; whether it helps the proposed compensation variant is what section 6 measures. This experiment cannot
establish generalization to an unseen amplifier family. "General" is also not weight averaging: the six A models cannot
be merged (different spec schemas, and
averaging independently trained networks does not give a working one); the general network is trained anew from the
pooled data.

---

## 2. What exists (read from the source and the recorded runs)

### 2.1 The experience archive

Every optimization run under `outputs/` with today's reward settings (`margin_weight` 1, `objective_weight` 1,
compressed shapes, `worst_spec_share` 0.5; reward version `constraint_violation_v2`):

| Task | Runs | Evaluations | Specs slots | Note |
|---|---|---|---|---|
| mscr_ota5t | 1 | 800 | 6 | A run (record 7.199) |
| mscr_ota5t_b | 2 | 1,600 | 6 | 7.229 fine_tune + scratch |
| mscr_ota7t_w | 1 | 800 | 4 | A run (ota7t width task) |
| mscr_ota7t_w_b | 2 | 1,600 | 4 | 7.229 |
| mscr_ring3 | 1 | 800 | 5 | A run (7.216) |
| mscr_ring3_b | 2 | 1,600 | 5 | 7.229 |
| mscr_vco_lin_c | 1 | 800 | 13 | A run (7.216) |
| mscr_vco_lin_c_b | 2 | 1,600 | 13 | 7.229 |
| mscr_vco_lin | 1 | 60 | 13 | stopped early |
| mscr_ldo1_rgcn | 1 | 1,500 | 10 | A run, HF PSRR -5 dB (never passed) |
| mscr_ldo1_rgcn_b | 2 | 1,600 | 10 | 7.229, HF PSRR -3 dB |
| mscr_ldo2_rgcn | 1 | 1,500 | 10 | A run, -5 dB (never passed) |
| mscr_ldo2_rgcn_b | 2 | 1,600 | 10 | 7.229, -2.3 dB |
| mscr_ldo2_rgcn_gt | 2 | 464 | 10 | gate-tracking variant, stopped by the user |
| mscr_ldo_basic | 1 | 800 | 14 | |
| **Total** | **22** | **17,124** | | |

The execution audit corrects the original "10 circuits" count: removing the six `_b` start variants gives nine named
circuit variants. Their archived DUT graphs fall into eight structural groups when ignoring names, dimensions,
model references and testbench devices (`topology-inventory.json`); `vco_lin` and `vco_lin_c` share that structure.
This grouping preserves device kinds, individual terminal roles and net roles, but does not assert electrical equivalence.

Not in this pool as recorded: 8 ota7t runs (the gamma 0.99 presets, the encoder comparison, the 7.216 run; 4,326
evaluations) under earlier reward settings (no margin and no objective term; one with the capped shape); the baselines
and calibrations (no transitions); the mock runs (origin `synthetic`, refused by a real learner). Replay-eligible
transitions are fewer than evaluations: failed evaluations (reward None) and episode ends with no next state are
archived but cannot train (`transition_rows` marks them). The exact count is an output of phase 0.

### 2.2 What is already identical across all 30 recorded models

Read from the `contract` block of every save point's `metadata.json`: one value each of reward version
(`constraint_violation_v2`), clearance rule, failure policy, condition policy (`off`), planned conditions (none), action
version (`absolute-group-v1`), critic action (`normalized_proposal`), normalizer (`fixed-references-signed-log1p-v1`),
graph schema (1.0) and feature schema (the standard component list; fine_tune and frozen runs always use it,
`runs.py`). Only two things differ between the recorded models: the spec schema (one per task, 4 to 14 slots) and, for
the 8 ota7t runs, the reward settings.

### 2.3 The rules in the code that the plan respects

- `SACLearner.update` (`src/analog_optimizer/training/sac.py`): per transition, its reward settings must equal the
  learner's, its condition policy the learner's, its origin the experiment's; else it raises. Nothing checks the task or
  the topology, so a batch may mix circuits. With gamma 0 the next states are not even batched.
- `context_features` (`models/inputs.py`): every Specs row's metric must be in the registry with the registered unit; a
  registry slot without a row is a zero row; the context has 21 columns per slot plus 11.
- `check_compatibility` (`gator_workbench/checkpoints.py`): spec schema, feature schema, model config and action version
  must be identical to load a model, in every mode; the task hash and the source digest are warnings outside resume. Loading
  another task's model is a transfer: `--confirm-transfer` on the CLI, the question in the chooser.
- `modes.build` for fine_tune: loads the actor, the critics and targets (unless `reset_critic` or the reward contract
  changed, when they start fresh by itself) and the temperature (unless `reset_temperature`); replay, optimizers and
  counters are new; `freeze_encoder` keeps the encoders fixed. The documented rule "No source replay data and no
  source-task dimensions are mixed in" is written into every run manifest's policy notes: rehearsal (section 8) departs
  from it and must be recorded as a decision.
- The model chooser (`checkpoints.saved_models`) lists every run folder under the output root that holds a complete save
  point and a run manifest; a run's mode must be one of `scratch`, `resume`, `fine_tune`, `frozen` (`schema.RUN_MODES`).
  An offline-trained model therefore needs a run-shaped folder (section 4, step 6).
- `run.continual_learning`: a model whose own run was a fine_tune loads only with this flag. The general model's folder is
  not a fine_tune, so the comparison needs no flag; a later chain (general -> C task -> another task) would.
- Budget accounting: a run that loads a model adds its parent's cost (`modes.py`; `source_pretraining_cost_evaluations`).
  The general model's parent cost is the whole pool, 17,124 evaluations, already spent; the comparison reports both "own
  launches" and "including pre-training".
- The ldo2 HF PSRR limit of record: the original -5 dB rows are unreachable in 1,500 designs; the B tasks' relaxed rows
  (-3 / -2.3 dB) are the targets of the comparison, as in 7.229.

---

---

## 3. One shared spec registry

The audited union of the 15 task registries holds **41 metrics** (phase-0 correction to the original estimate of 34).
The saved run manifests and checkpoint contracts independently give the same union. 33 agree on unit and reference
everywhere; 8 agree on the unit and
differ in the reference (the fixed physical reference the context normalizes against):

| Metric | References in use (tasks) | Proposed | Why |
|---|---|---|---|
| iq_a | 200 uA (ldo1_rgcn, ldo1_rgcn_b, ldo_basic); 400 uA (ldo2_rgcn, ldo2_rgcn_b, ldo2_rgcn_gt) | 300 uA | between the two |
| loopgain_db | 1 dB (both LDOs and their _b, ldo2_rgcn_gt); 6 dB (ldo_basic) | 6 dB | the dB convention of record 7.227 (Scale 6 on dB rows) |
| ugb_hz | 1 Hz (ldo1_rgcn, ldo2_rgcn and their _b, ldo2_rgcn_gt); 50 kHz (ldo_basic); 100 MHz (ota5t, ota5t_b) | 10 MHz | LDO UGB about 14 MHz, OTA about 100 MHz; 1 Hz is a reference no row meant |
| psrr_10k_db | 6 dB (LDOs); 30 dB (ldo2_rgcn_gt) | 6 dB | dB convention |
| psrr_1m_db | 6 dB (LDOs, ldo_basic); 20 dB (ldo2_rgcn_gt) | 6 dB | dB convention |
| psrr_hf_db | 6 dB (LDOs); 5 dB (ldo2_rgcn_gt) | 6 dB | dB convention |
| noise_vrms | 150 uV (ldo_basic); 50 uV (ota5t, ota5t_b) | 100 uV | between the two |
| power_w | 500 uW (ota5t, ota5t_b); 150 uW (ring3, ring3_b); 650 uW (vco_lin, vco_lin_c, vco_lin_c_b) | 500 uW | the middle value |

What a reference does and does not do. It only normalizes the goal input: the row's lower and upper limit, its Scale and
the measured value enter the context as signed logarithms against the reference. It does not enter the reward: the
reward uses the row's Scale, which is inside the recorded transitions and stays as recorded. A changed reference
re-contexts the old data consistently, and since the general network is trained from scratch on the shared registry,
no old model has to stay compatible with it.

Width. 41 slots make a context of 41 x 21 + 11 = 872 columns (today: 95 for ota7t_w, 137 for ota5t, 116 for ring3, 221
for the LDOs, 284 for vco_lin_c). The layer that reads the context grows with it; the parameter count is read from the
model inspection once the registry is fixed (phase 0 output).

Where it is set. `run.advanced.spec_registry` (a list of metric id, unit, reference) in the run configuration; the run
then compiles its SpecSchema from that list. Every run that loads the general model must set the same list; the
compatibility check enforces it, so a mistake fails loudly. Both arms use it, including scratch. G also uses the
lower learning rate, fewer updates and rehearsal fixed in section 8: S versus G compares the complete transfer recipe,
not an ablation isolating pretrained weights. The comparison's runs are CLI runs from written configurations, as
7.229's were (`make_configs.py` in the review folder), which is where the list goes.

Hindsight relabelling (optional, decision D3). The reward and the goal input both derive from the recorded metrics and
the Specs rows, so an archived design can be re-scored under other targets with
`SpecificationEvaluator(specs, settings).evaluate(metrics, units, validity)` (the scale study of 2026-10-05 re-scored
227 recorded designs this way). The 3,000 LDO designs recorded at -5 dB, re-scored at the relaxed -3 / -2.3 dB rows, give
the general network passing examples at the targets the comparison uses (today only the B fine-tune runs hold such
passes: 89 and 58 designs). Requirements: both states of a relabelled transition carry the relabelled rows and
re-evaluated results (`Transition.validate` requires equal rows on both ends); the reward settings stay as recorded. Gate:
re-scoring a transition under its own, unchanged rows must give the recorded reward exactly, on every pooled run.

---

---

## 4. Training the general network offline (no Spectre)

Method of record: offline SAC updates through the existing learner, fed from the pooled archive instead of a live replay.

1. **Pool.** For each of the 22 runs, `TrajectoryLoader(run_dir).transitions()`; tag each transition with its task.
   (The 8 older ota7t runs join only after re-scoring, decision D2.)
2. **Hold out** 10 % per task, whole episodes (episode length 4), for the checks of step 5.
3. **Learner.** A new `SACLearner` with the shared SpecSchema, the standard feature schema, the 48 / 4 / 4 Graph
   Transformer model config of every recorded run, the starting preset's SAC config (learning rate 1e-3, initial alpha
   0.01, gamma 0, tau 0.005), seed 0, an experiment descriptor with origin `real` and all pooled tasks under `designs`.
4. **Updates.** Batches of 8 (record 7.221 measured about 0.1 s per update of batch 8; batch 32 cost four times batch 8
   in 7.183's study), each batch mixing circuits, balanced per task (every task contributes the same number of
   transitions per pass; the small tasks, vco_lin with 60 and ldo2_rgcn_gt with 464, are oversampled, otherwise they are
   invisible). 10 to 20 passes over the pool are 20,000 to 40,000 updates: 35 to 70 minutes on the CPU. Gamma 0 makes this
   an easy offline problem: the critic is a reward model (no bootstrapping, so errors on actions never recorded do not
   compound), the actor maximizes the critic plus entropy. The actor's only risk is exploiting critic errors where the pool
   has no data; step 5 measures it before any launch.
5. **Checks before any launch** (free):
   - (i) Critic: reward-prediction error on the held-out transitions per task, against a per-task constant (the "learned
     nothing" line) and against the task's own A model's critic on the same held-out set (the "as good as the specialist"
     line).
   - (ii) Actor: deterministic proposals at each task's recorded starting state and at 20 recorded states; their critic
     value against the best recorded reward of the task; the share of proposals inside the parameter ranges.
   - (iii) Forgetting curve while training: the held-out error per task per pass. It must not rise for one task while it
     falls for others; if it does, the balancing is wrong or the network is too small (decision D9).
6. **Save** a run-shaped folder, `outputs/general-network__<id>/runs/general/offline__<id>/`: `run_manifest.json` (mode
   `scratch`, task name "general", a `pretraining` block with the pooled runs, their evaluations, the
   registry and the held-out numbers; `model_label` "general") and one save point through `CheckpointStore.save` (own
   evaluations 0, the learner updates counted). The chooser then lists "general"; it loads on any task through the
   transfer question, with `source_pretraining_cost_evaluations` 17,124. Phase-0 check: the readers of a run folder (run
   list, status, Training tab) must tolerate a folder with no evaluations, or the tool writes a minimal `status.json`.

Where the tool lives: `src/gator_workbench/` (a CLI command, `pretrain`), with tests on synthetic data (the test
stand-in task, origin `synthetic`). Nothing in `src/analog_optimizer/` changes: the learner, the replay buffer and the
checkpoint format are used as they are, so the optimizer digest stays `0b0808bc`.

Alternatives if step 5 fails: (b) filtered behaviour cloning of the actor on the best-reward transitions per task, a loss
added outside the learner (the tool steps `learner.actor` with its own objective; no optimizer change, but a second
training path to record) or inside it (digest change); (c) a conservative critic (a CQL-style penalty on actions off the
data), an optimizer change. Neither is planned unless (a) fails its checks.

---

---

## 5. The comparison on a third start (start C)

**Tasks.** Six new tasks `real:mscr_<name>_c` by the start-B rule of record 7.227 with a second draw: among the valid
random designs of record that failed at least one row, the design at the 25th percentile of reward (B took the median),
so a typical but worse start, different from A and B on every row; decision D5. The LDOs keep the relaxed HF PSRR rows of
the B tasks (-3 / -2.3 dB) and Scale 6 on dB rows. All six C tasks and every arm set the shared registry. Built as the B
tasks were (`~/mscr_circuits`: `designs.py`, `circuits.py`, `tasks_def.py`, `save_tasks.py`), each saved through the
workbench and checked with Check now. **A Baseline simulation is required for every start-C task:** its starting
design plus 64 seeded random designs, nominally 65 launches per task, **390 planned launches total**. Count periodic
reset checks separately: execution used **391**, because LDO2 needed one additional draw after a paid reset (section 14).
Use seed 2 and the exact frozen
start-C parameters, bounds, Specs rows and shared registry. Preserve the baseline run ID, task/config hashes, raw
metrics, validity/failure counts and per-row pass shares; perform Check now again after restoration. A baseline is
complete when the start, all 64 random draws and any reset overhead are accounted for and restoration is verified,
not when its designs pass the Specs.
An infrastructure error or unresolved missing measurement blocks that task's S/G/O runs until resolved. Do not adjust
targets, scales, bounds or the selected start in response to these baselines. They are qualification data only: exclude
them from general/own-model pretraining, rehearsal and each arm's initial replay; charge their cost separately.

**Arms**, 800 launches each, seed 2, the A runs' settings as in 7.229 (learning rate 1e-3, alpha 0.01, 8 updates, gamma 0):

- **S** scratch: random weights, the shared registry.
- **G** load-general: fine_tune from the general model with the anti-drift settings of section 8 (rehearsal if built,
  decision D4; otherwise the settings-only levers).
- **O** load-own, on ota5t only (decision D6): fine_tune from a model the same tool trains offline on ota5t's own
  recorded data (its A run and its two B runs, 2,400 evaluations; shared registry, same method). Arm O repeats 7.229's
  question, an own model on a new start, so it measures nothing new about transfer; its one job is to show that the
  offline route and the wider registry keep the head start 7.229 measured live (ota5t: 90 % of the first 100 own
  proposals). ota5t is where that head start was largest, so any loss shows. For the other five circuits 7.229's fine-tune
  rows are the approximate own-model reference (start B, seed 1, a live-trained model under the task's own registry). The
  A models themselves cannot serve here: they carry the task's own registry.

**Frozen probes first** (phase 1): the general model in frozen mode, sampled actions, 300 launches on each of the six B
tasks (they exist; their 7.229 numbers are the reference). These B tasks are included in offline training: here
"zero-shot" means no online adaptation, not an unseen task. Report passing share, best reward and per-row failure
shares before any online update. The 300 launches include periodic checks of the starting design. Also report sampled
policy counts and unique executed designs; sampling does not guarantee 300 different designs.

**Measures**, the definitions of record 7.229 (section 5 of `docs/plan-finetune-vs-scratch.md`): early share = passing
share of designs 9-108 in committed evaluation order, cumulative passes by 100 / 200 / 400,
the "50 % by" point, last-third share, mean reward early and late, per-row failure shares, working time.
Keep the 9-108 window exactly as in 7.229; initial/reset evaluations and concurrent warm-ups mean it is not guaranteed
to contain 100 policy proposals. Also record its action-source counts. Thresholds use exact fractions without rounding.

**Criteria**, fixed before any run starts:

- C1 head start: G's early share at least 30 points above S's.
- C2 end: G's last-third share within 5 points of S's or above.
- C3 LDOs: G passes at the relaxed targets.
- C4 no drift (new): G's last-third share at least its early share minus 10 points, and the failure share of G's weakest
  row does not rise by more than 15 points from its first 200 designs to the rest. Fix that row from the largest failure
  share in the first 200 designs, break ties by metric ID, and report every row's change as well. Invalid or missing
  required rows count as failures and stay in the denominator (ldo1_rgcn in 7.229 would fail both:
  27 % to 7 %, the HF PSRR row 63 % to 82-88 %).
- C5 offline method (ota5t only): O's early share within 10 points of 7.229's live fine-tune (90 %), and G's within 10
  points of O's.
- Frozen probes: reported, no bar. A comparison with S's early share is descriptive because probes start at B and S
  starts at C. The paired S/G arms at C determine the new-start transfer verdict.

Verdict rule: "one general network transfers to a new start" if C1 holds on at least four of six circuits, C2 on six and
C4 on at least five; otherwise reported as measured, no claim. One seed per arm, as in 7.229; a second seed on the
circuits whose arms end within the seed spread is decision D7.

---

## 6. The held-out compensation variant (phase 3)

Phase 2 tests the general network on circuits that are in its pool, the in-distribution case. A circuit outside the pool
is the only test of knowledge that carries across circuits. Leave-one-out (six networks each trained without one circuit,
one run per held-out circuit) was the first version of that test; the rewrite replaces it with a circuit built for the
purpose. **Topology correction (record 7.235):** the pool already contains the two-stage Miller OTA `mscr_ota7t_w`.
Its builder has M1-M8 (including the bias diode) and CC between N1 and VOUT. The proposed eight-transistor circuit
therefore differs mainly by adding a series nulling resistor. The general network trained on all nine circuit variants is
tested as it is; there is no own-data model of this variant. The comparison costs 1,965 launches instead of 4,800.
Before construction, pin the device/net/terminal graph difference against the pooled OTA7t and retain its lineage;
a renamed or resized duplicate does not qualify as held out.

**The circuit.** A two-stage Miller-compensated OTA, `real:mscr_ota8m` (name proposed): differential pair, current-mirror
load, tail source, a common-source second stage with its current source, a bias mirror; eight transistors, a Miller
capacitor with a series nulling resistor. The resistor and its intermediate net are the proposed graph change from
the pooled OTA7t. A folded-cascode OTA (`mscr_otafc`, eleven to thirteen transistors, single stage) is
the harder second point if the first result is positive; it is the same recipe again.

**What makes it cheap.** The cell gets the ota5t pins (VINP, VINN, VOUT, IBIAS, VDD, VSS) and its
six metrics (gain_db, ugb_hz, pm_deg, power_w, psrr_db, noise_vrms). Reuse the measurement structure, but qualify the
supply, common-mode and load for the selected devices: OTA5t's existing bench is 1.8 V and cannot simply be attached
to the proposed 1 V devices. The shared registry already holds the six metrics, so no slot is added. The device kinds (1 V MOS,
MIM capacitor, resistor) are in the component list through the LDOs. Node count and action dimensions are deliberately not
compatibility criteria (`check_compatibility`), so the general model loads on the bigger graph with its more numerous
parameter groups.

**Rows and targets.** Parameters as in ota5t (w and l of every transistor, matched pairs as leader and followers) plus the
Miller capacitor and the nulling resistor. Specs: the six ota5t metrics, Scale 6 on dB rows. The targets are fixed AFTER a
Baseline simulation (the baseline design plus 64 random designs), not before: each row at a level some random designs
reach on their own, the whole set reached by none. Any proposed 60 dB gain target needs support from this baseline;
the gain requirement does not establish topology novelty. The LDO lesson of record 7.229: a row no
design can reach makes every arm look the same.

**Fixed before phase 0:** the circuit's spec list. The registry is fixed when the general network is trained; a slew-rate
or settling row would need a transient testbench and a registry slot added before training. Decision D10 (recommended:
the six ota5t metrics only).

**Start and arms.** One start, the textbook sizing (start A, as the library's circuits), seed 0. First the zero-shot probe
(frozen, sampled actions, 300 launches), then S (scratch) and G (load-general with the anti-drift settings) at 800
launches each. With the baseline simulation: 65 + 300 + 1,600 = 1,965 launches, about 1.5 h. The cell is a few hours of the
writer on the VM, as the six B cells were (`~/mscr_circuits`: `circuits.py`, `designs.py`, `tasks_def.py`,
`save_tasks.py`); after the topology correction, construction and its single baseline wait for phase 2's verdict
and the graph/voltage-domain checks above.

**Criteria:** C1, C2 and C4 of section 5 on this circuit; the zero-shot share reported. If C1 and C2 hold, report a
head start on a held-out compensation variant. One circuit and one seed cannot establish unseen-family transfer;
failure to show a head start also cannot prove that the network only memorizes. A second seed remains conditional.
Keep these results excluded from the current network; they may join a separately versioned future pool.

---

## 7. Budget and time

| Phase | What | Spectre launches | Time |
|---|---|---|---|
| 0 | shared registry, pooling tool, offline training, held-out checks, model folder (the general model; the ota5t own-data model under D6) | 0 | about 1 h CPU per network, plus the tooling |
| 1 | zero-shot probes of the general model on the six B tasks | 1,800 | about 1 h |
| 2a | six C cells/tasks and required baselines; one extra reset check in LDO2 | 391 actual (390 planned) | completed; see section 14 |
| 2b | arms S and G on the six C tasks | 9,600 | about 5 h (7.229's twelve ran 06:58-12:03) |
| 2c | arm O on ota5t (D6) | 800 | about 12 min |
| 3 | held-out compensation variant: graph/voltage audit, required baseline, zero-shot probe, arms S and G | 1,965 | about 1.5 h, plus a few hours for the cell |
| 3b | the folded-cascode second point, optional, after a positive phase 3 | 1,965 | about 1.5 h, plus its cell |

Times per 800 launches from 7.229: ota5t 10-12 min, ring3 11-14, ldo1_rgcn 12-29, ota7t_w 27-37, ldo2_rgcn 31-71,
vco_lin_c 35-47. The queue of 7.229 (`queue.sh`: one run at a time, the session lock, Check now before and after each run,
the nonce cache read for multi-lane runs) is reused as it is.

---

## 8. Policy drift: what it is here, why it happens, how to avoid it

**Two kinds.**

- (D-a) While adapting: the loaded policy loses what it knew on the new task while its weights are updated on the new
  task's transitions. Record 7.229, ldo1_rgcn: 27 % early, 7 % in the last third; the relaxed HF PSRR row failed on 63 %
  of the first 200 designs and on 82-88 % after. Not seen on the four circuits whose loaded model ended at 95 % or above.
- (D-b) While training the general network: training on the circuits one after another overwrites the earlier ones
  (catastrophic forgetting). Avoided by construction in section 4: the whole pool, shuffled, balanced per task, with the
  per-task forgetting curve as the gate. The general network is never trained sequentially, and a model continued on one
  task is never called general.

**Why D-a happens in this setting.** fine_tune starts an empty replay and keeps the loaded critics; from the first update
on, every batch is 8 transitions of the new task only, 8 updates per transition at learning rate 1e-3. The critic (a reward
model, gamma 0) is pulled toward the few hundred new samples and loses its shape elsewhere; the actor follows the critic;
with alpha 0.01 the entropy term holds nothing back. On the LDOs the loaded critics were also trained at the old -5 dB
target. Nothing in a run measures or limits the distance from the loaded policy.

**Levers, ranked by value for cost** (and whether they change the optimizer digest):

1. **Rehearsal replay** (attacks the cause). Keep the pooled experience as a second replay beside the run's own and draw
   every update batch half from each; the same idea as the symmetric sampling of RLPD (Ball et al., 2023, online RL with
   offline data) and the balanced replay of Lee et al. (2021). The learner accepts such batches today (same reward
   settings, same registry). Cost: a workbench engine change (a `rehearsal` block in the run settings: the source pool, the
   share, a capacity), the documented fine_tune rule changes to "unless rehearsal is on" in the manifest's policy notes,
   tests. No optimizer change: `ReplayBuffer` and `SACLearner` stay as they are. Variant to measure with lever 6: the
   rehearsal half drawn half from the same circuit's recorded data and half from the rest. Decision D4.
2. **Learning rate and update budget of the loaded arm:** 2e-4 and 2 updates per transition for G (settings that exist).
   Cheap; it also slows G's own adaptation, which ring3 needs. With lever 1, or alone if 1 is not built.
3. **`freeze_encoder`** (exists): the graph representation stays, only the heads move. Cheap; likely enough on the four
   easy circuits, not on the LDOs, where the critic head is what drifts.
4. **Keep the loaded critics and temperature** (today's default). `reset_critic` goes the wrong way for drift: it throws
   the reward model away; it is right only when the reward contract changed, which `modes.py` does by itself.
5. **Keep-best instead of keep-last.** Save points every N designs exist; `best_policy.json` is "selected only by an
   explicit validation-set rule" and nothing selects today. A rule "the save point with the highest passing share over its
   following 100 designs" (read from the run's own data) makes the delivered model the best one, drift or not. A read-only
   tool, no engine change.
6. **A drift meter** (measurement, not prevention). For every save point: the deterministic proposals of the loaded model
   and of the save point's model on 64 fixed recorded states per circuit, their mean absolute difference in normalized
   action units; plus the critic's held-out reward error on the pool. Read-only over save points
   (`SACLearner.act(..., deterministic=True)`), no digest change. It turns "drift" from a guess into a number per save
   point; built once, used by every later comparison and by C4.
7. **Regularizers that need an optimizer change** (digest): a KL term toward the loaded actor (what RLHF fine-tuning
   does), an L2 pull toward the loaded weights (L2-SP), elastic weight consolidation (Kirkpatrick et al., 2017), a
   conservative critic (CQL; Cal-QL for offline-to-online, Nakamoto et al., 2023). Not proposed: they change
   `training/sac.py`, which re-digests the package (Continue of every saved model blocked until re-saved), and levers 1-3
   are expected to do the job. Decision D8.

For the general network itself (D-b): balanced per-task sampling, the forgetting curve, early stopping on the held-out
error, no sequential training.

---

---

## 9. Procedure

Phase 0 (free): decisions D1-D3, D9 and the held-out circuit's spec list (D10, because the registry is fixed at training);
the `pretrain` tool with tests; the general model and, under D6, the ota5t own-data model; the held-out checks written
into each model folder's `pretraining` block; the drift meter and the keep-best rule (levers 5-6 of section 8) if the
user wants them in this round; under D4 the rehearsal engine change with tests. Phase 1: the six zero-shot probes (1,800
launches). Phase 2: the C cells and tasks, the six required start-C baselines (391 actual launches), then the twelve runs
plus arm O on ota5t through the 7.229 queue,
`compare.py` extended by C4 / C5 and the zero-shot rows. Each task's baseline is a gate for its comparison arms.
Phase 3 (after the verdict of phase 2): the compensation variant's topology/voltage audit, construction, baseline,
probe and two runs; the folded cascode only after a positive
result.

The user's "start it" authorizes work through this plan's required phases, including the six start-C baselines.
Proceed through the offline and physical qualification gates in order; optional extra seeds and phase 3b remain
conditional. Updated launch accounting: **12,591 through phase 2**, **14,556 through phase 3** (including the one
required baseline reset overhead; originally 12,590 / 14,555). The S/G/O and probe budgets are unchanged.
The held-out variant's 65-launch baseline is counted once. Historical pretraining
evaluations are reported separately and are not new launches.

---

## 10. Initial settings and conditional decisions

The 2026-10-06 start request adopts the recommendations below for the initial implementation. D7 and phase 3b
remain conditional; optimizer-side regularizers remain excluded. These are recorded choices, not a new approval gate.

1. **D1 References of the 8 conflicting metrics:** the proposal of section 3, or other values.
2. **D2 The 8 older ota7t runs:** recompute their rewards under today's settings and include them (+4,326 evaluations of
   the 4-row OTA; a re-scoring step with the gate of section 3), or leave them out. Recommended: leave them out of the first
   network (ota7t is represented through ota7t_w).
3. **D3 Hindsight relabelling** of the LDO -5 dB data at the relaxed targets: yes / no. Recommended: yes, with the gate.
4. **D4 Build rehearsal** (engine change, the fine_tune rule of record changes): yes / no (then levers 2 and 3 only).
   Recommended: yes; it is the one lever aimed at the cause.
5. **D5 The start-C rule:** 25th-percentile random design of record, seed 2; or another rule.
6. **D6 Arm O on ota5t** (one own-data offline model, one run, +800 launches): yes / no. Recommended: yes; it is the check
   that the offline route keeps 7.229's head start, at the price of one short run.
7. **D7 A second seed** on the circuits whose arms end within the seed spread: decided after phase 2.
8. **D8 Optimizer-side regularizers** (KL / L2-SP / EWC / CQL): no, unless levers 1-3 fail C4.
9. **D9 Network size:** 48 / 4 / 4 as every recorded run, unless the forgetting curve says it is too small; a larger
   network applies to both arms.
10. **D10 The held-out op-amp:** the two-stage Miller OTA `mscr_ota8m` first, with the six ota5t metrics and no transient
    row (a slew or settling row adds a registry slot before phase 0 and a transient testbench). This is a compensation
    variant of the pooled OTA7t, subject to the graph/voltage audit and phase-2 verdict before construction; the folded
    cascode `mscr_otafc` remains an optional second point after a positive result.

Parked, as every further plan must say: the SKY130 benchmark (AnalogGym-Opt import, calibration with zero passes, the
tunable bias current) stays untouched; the MScR circuits on Spectre are the test bed.

---

## 11. What goes on record

This plan; record entries 7.230 (the plan) and 7.232 (the rewrite); when built: the `pretrain` command, the drift meter
and the keep-best rule with tests and their rows in `docs/functionality-reference.md`; the rehearsal decision in
`docs/decisions.md` if D4 is yes; the C tasks' and the held-out op-amp's definitions in `~/mscr_circuits`; the model
folders' `pretraining` blocks; the comparison's `results.md`. Under D8 = no, nothing in `src/analog_optimizer/` changes.

---

## 12. Execution started (2026-10-06, record 7.233)

The first implementation is `gator-workbench pretrain REQUEST.json --output NEW_DIRECTORY` (add `--audit-only`
to validate without training). The request explicitly lists source directories and their archive SHA-256 hashes;
new runs and start-C baselines cannot enter by a later directory scan. All 22 sources / 17,124 historical evaluations
are pinned in `artifacts/general-network-20261006/request.json`. The request uses the eight references of section 3,
seed 0, 10% whole-episode holdout, the 48/4/4 GT, gamma 0, batches of 8 and 20,000 updates, saving every 1,000 updates.

Implemented gates: table/static-data integrity; unique source run/candidate identities; nominal-only, uniform reward
and origin; exact unchanged-goal reward reconstruction; shared-registry units and explicit reference conflicts.
LDO relabelling adds derived examples at -3 / -2.3 dB without overwriting the originals; both endpoints get the new
Specs, and originals/derived examples always stay in the same episode partition. Tasks are sampled equally over
shuffled cycles. The constant-reward diagnostic is fitted on training data only; held-out twin-critic errors are saved
before training and at every checkpoint. These are within-source diagnostics, not unseen-circuit evidence.

Live evidence is under `artifacts/general-network-20261006/`: `training.log`, `training/status.json`,
`training/pool.json` (counts and exact split), `training/spec_registry.json`, `training/validation.json` and
`training/checkpoints/`. Completion is labelled `trained_unqualified`: these are provisional weights, not yet a model
published to the workbench chooser. The ordinary online Continue command cannot resume this offline sampler; save
points are explicitly weights-only for transfer. No source archive or optimizer-package file is modified.

Remaining phase-0 gates: specialist-critic and actor-proposal diagnostics, forgetting-curve review, model-folder
publication with historical cost, the ota5t own-data model and the online rehearsal engine. After those gates,
proceed to the probes, start-C task creation and all six mandatory baselines before the comparison arms. None of the
new Spectre launches is claimed by the offline training job.

**First live audit:** all 22 sources passed; 16,076 original eligible transitions and 2,822 derived LDO transitions,
split into 16,966 training examples and 1,932 validation examples across 15 tasks. There are 41 registry metrics
(872 context columns); the original 34-slot estimate was incorrect. The 17,124 source evaluations include 1,048
evaluations with no eligible archived transition; they still count toward historical cost. The offline job completed
20,000 updates; see the continuation below for the completed gates and physical work.

## 13. Autonomous continuation (2026-10-06, record 7.234)

The user said "Go on on your own". Both offline networks completed 20,000 updates with the same 41-slot registry:
the general model uses the frozen 22-run pool; the own-data model uses only OTA5t A and its two B runs (2,400 recorded
evaluations). `training/qualification.json` and `own-ota5t/qualification.json` contain the specialist comparisons and
actor diagnostics. Both critics beat the training-mean constant on every task. General error exceeds the specialist
on 8/15 tasks; the specialists may have trained on these held-out episodes, so the comparison is descriptive. All 297
general and 42 own-model proposals are legal, with no best-plus-three-RMSE flags. None of this establishes transfer
benefit or measures the true reward of a new actor proposal.

The forgetting gate is reviewed for a persistent deterioration, not for individual noisy checkpoint increases:
the last six checkpoints fluctuate rather than rise consistently. Final/best worst-critic MSE is at most 1.31 on
14 tasks; `vco_lin` is 3.92 with only **two** held-out transitions, insufficient to decide capacity. The recorded
review allows the diagnostic real probes without an architecture change. Do not describe this as specialist parity.

Published, immutable source models (weights-only transfer):

- `outputs/offline-network__c8c3531a0d78/runs/general/offline__seed0__c8c3531a0d78`, label `general`, checkpoint
  `ckpt-00000000-9b48fb98`; historical cost 17,124, new simulations 0.
- `outputs/offline-network__bc48fbe3d4f3/runs/general/offline__seed0__bc48fbe3d4f3`, label `ota5t own offline`,
  checkpoint `ckpt-00000000-64e5d9b0`; historical cost 2,400, new simulations 0.

Rehearsal is implemented in the workbench, not the optimizer. The fixed general snapshot contains 1,931 transitions
under capacity 2,048: up to 136/137 per task, only 19 available for the smallest task. Sampling remains balanced by
task. Every G update uses four target and four source transitions, learning rate 2e-4, two updates per new transition,
with no encoder freeze. The source sampler is checkpointed; baseline and holdout transitions remain excluded.
O keeps the original control's 1e-3/eight-update settings, with no general-source rehearsal.

`start-c.json` freezes the six starts. Selection uses the same historical random-design runs as B, scored under the
unchanged B/C goals; remove passing/invalid designs and any start equal to A or B on an independent row, sort reward
ascending, then choose nearest rank `ceil(0.25*n)`. Selected source evaluation numbers: OTA5t 57, OTA7t-w 3, ring3 41,
VCO 34, LDO1 48, LDO2 40. Separate MScR DUT/testbench copies are built and readback verified. Registration and Check
now receipts live under `cells-c/`; no A/B schematic is overwritten.

The durable queue performs the six C baselines first, then the six B frozen probes, followed by C arms S/G and OTA5t O.
The original total was **12,590** new launches; section 14 records one extra required baseline launch.
Each baseline uses **one lane**, one start plus 64 random draws, seed 2. Before/after Check now,
actual launch accounting, raw data integrity and missing-measurement gates must pass. Failure stops the queue;
an incomplete job is never silently skipped. Calibration proposals are recorded but never applied. Runtime source,
settings and configurations are frozen in `artifacts/general-network-20261006/`; `queue-status.json` is authoritative
for actual progress. Phase 3 still requires the phase-2 verdict and the held-out OTA's construction/qualification.

Validation: **133 tests passed**, covering offline pooling, model loading/publication, rehearsal immutability and
exact sampler/engine resume, existing transfer/trajectory behavior, schemas and empty Training-tab readers.

**Queue started:** all 25 configurations passed offline registry/model compatibility checks. The OTA5t-C baseline
started on Spectre at 15:22 UTC; its run is
`outputs/general-baseline-ota5t__ec25da8a08f7/runs/mscr_ota5t_c.baseline/scratch__seed2__b3c4792dc761`.
A preceding isolated-runner output-root rejection spent zero launches and passed the after-check; its evidence is
retained. Actual committed launch totals and completed gates are in `queue-status.json` and `results/`, not inferred
from the planned budget.

## 14. Baseline recovery and comparison audit (2026-10-06, record 7.235)

The OTA7t-C baseline completed 65 launches: 61 valid designs, two passing, four `measurement_error` designs. All four
Spectre jobs returned zero errors; UGB and phase margin were nil. A read-only OCEAN review of their retained STB
waveforms found maximum loop-gain magnitudes **0.0008290, 0.0011405, 0.0009989 and 0.1917524** over the recorded
sweep. No unity crossing exists there, so these two measurements are physically undefined. The backend invalidates
the whole evaluation, including gain/current scalars still present in raw measurements. These designs remain failed;
their rewards, raw metrics, validity flags and cost are unchanged. There was no rerun or zero-fill.

`results/baseline-ota7t_w-waveform-review.json` and its hash-pinned `-resolution.json` explain the exact four designs
and sixteen aggregate missing rows. The queue only accepts this resolution for the same run/task/config and unchanged
raw measurement files. After-review Check now passed and the live baseline reference was adopted. Unexplained missing
measurements in any other run still block. Accounting now records every finished job's cost before qualification;
`progress.json` adds the active worker's ledger without double-counting it.

All six C baselines are qualified (`baseline-qualification.json`):

| Task | Launches | Valid | Passing | Random draws |
|---|---:|---:|---:|---:|
| OTA5t | 65 | 65 | 1 | 64 |
| OTA7t-w | 65 | 61 | 2 | 64 |
| Ring3 | 65 | 65 | 1 | 64 |
| VCO | 65 | 65 | 3 | 64 |
| LDO1 | 65 | 61 | 0 | 64 |
| LDO2 | 66 | 59 | 0 | 64 |
| Total | 391 | 376 | 7 | 384 |

LDO1's four and LDO2's seven missing-bandwidth/phase-margin failures were also reviewed from retained STB sweeps:
max |loopGain| stayed below unity (ranges 0.0139895–0.184114 and 0.0000595133–0.492988). Their exact reviewed rows,
raw-file hashes and evidence are pinned in each baseline's `-resolution.json`; the failures remain in all counts.

**LDO2 draw-count repair.** The original 65-launch run had 63 random draws and two starting-design evaluations: the
engine performs a paid check every fifth reset, and measurement failures truncated episodes. Keep that archive intact.
`supplement_ldo2_baseline.py` reproduced all 63 normalized proposals exactly from seed 2, then ran only draw 64 in a
separate one-launch archive, with a recorded logical initial observation, no extra simulated reset and no updates.
The supplement was valid/nonpassing and passed restoration. This is 66 LDO2 launches including one reset overhead,
not a new baseline or a changed seed. All 64 random draws enter its per-row shares; both resets stay in total cost.
The existing workbench baseline path still needs this external count gate when failures cause periodic resets.

All six initial designs were valid and nonpassing; physical definitions and shared registry match their frozen configs.
Four resistor properties were already serialized to six significant digits by the existing MScR builder before
construction (largest change from the selected archived value 1.6 ppm). The new audit compares against that exact
frozen property text and records the differences; it does not relax the comparison or resize the C cells.
Baseline and supplement IDs are absent from both pretraining pools and rehearsal. `queue-status.json` records completed
gates, `progress.json` records current cost/progress, and `comparison.json` refreshes on queue events. Frozen probes
follow, then S/G/O. Read these files for current numbers.

**First frozen probe (16:31 UTC):** OTA5t-B completed **300 valid simulations, 199 passing (66.3%), zero updates**;
restoration passed. Run `c2c7b955ca4244afb9bf430b297f9303`. The OTA7t-B probe started next. This measures the
unadapted general model on B; the paired C-transfer verdict remains pending.

The experiment's `compare.py` is fixed before the first probe or comparison arm (`comparison-protocol.json`). It
records C1–C5, early/late reward and passing shares, cumulative passes, 50%-by, all hard-row failure shares and costs.
Thresholds use exact fractions. The weakest row is fixed from the first 200 designs with deterministic tie-breaking;
missing/invalid rows count as failures. Incomplete arms remain pending. Synthetic in-memory checks cover threshold
boundaries, the 9–108 window, last-third size, missing rows, row ties and incomplete-run rejection. G versus S measures
the full pretrained/rehearsal/settings recipe, not the isolated effect of weights. Source history is reported separately.

The builder audit also corrected section 6: `~/mscr_circuits/circuits.py::ota7t` already contains eight MOS devices
and Miller CC. The proposed `mscr_ota8m` can test a series-null-resistor variant, not a previously unseen two-stage
amplifier family. OTA5t's 1.8 V bench also needs adaptation before use with 1 V devices. Graph lineage and voltage
checks now precede phase-3 construction after the phase-2 verdict. No optional topology or comparison budget was added.

The archived-graph audit (`audit_topology.py`, `topology-inventory.json`) confirms the same OTA7t connections in the
actual training source, independent of the builder. It also corrects the inventory to **15 tasks, nine named circuit
variants, eight DUT structural groups**; the earlier ten-circuit prose was an overcount. The 22 frozen source runs,
17,124 historical evaluations, trained weights and selected comparison tasks are unchanged.

## 15. Frozen-probe audit and phase-3 preparation (2026-10-06, record 7.236)

All six probes completed their 300-launch budgets, all valid, with restoration verified. Separate
policy-only counts below explain the periodic start checks; the frozen comparison criteria still use all launches.

| Probe on B | Passing / all launches | Passing / sampled policy | Start checks | Unique executed designs, including start |
| --- | --- | --- | --- | --- |
| OTA5t | 199/300 (66.3%) | 199/284 (70.1%) | 16 | 285 |
| OTA7t | 271/300 (90.3%) | 271/285 (95.1%) | 15 | 286 |
| Ring3 | 16/300 (5.3%) | 16/284 (5.6%) | 16 | 285 |
| VCO | 269/300 (89.7%) | 269/284 (94.7%) | 16 | 285 |
| LDO1 | 11/300 (3.7%) | 11/284 (3.9%) | 16 | 285 |
| LDO2 | 0/300 (0.0%) | 0/285 (0.0%) | 15 | 286 |

Every policy proposal in these six probes produced a distinct executed parameter tuple within its task; all repeats were start
checks. All starts were nonpassing. The largest policy-only hard-row failure counts were OTA5t UGB (85/284), OTA7t
current (14/285), ring3 frequency (262/284), VCO center frequency (15/284), LDO1 HF PSRR (255/284), and LDO2 HF
PSRR (271/285; current also failed 239/285). These are known B tasks from the offline pool. Neither a strong probe
nor a comparison against the different C start proves unseen-task transfer or satisfies C1–C5.

`probe_review.py` independently verifies archived data checksums, frozen config/source identity, zero online updates,
no learner-update rows, and empty checkpoint replay. It safely loads tensor-only model payloads and compares every
actor, critic, target and temperature tensor with the published source. All 492 tensors match at all 18 saved
checkpoints across these six runs. The checkpoint counter stays at the inherited 20,000 offline updates; it is not
20,000 new online updates. Archived `replay_eligible` flags describe reusable transitions, not actual replay insertion.
Synthetic checks reject changed tensors, temperature, update count, schema and incomplete executed parameters.
The read-only follower completed `probe-review.json` and exited. The baseline-plus-probe cost is **2,191 launches**:
391 for baseline qualification and 1,800 for probes. The durable simulation queue now proceeds to C
scratch/general/own arms with unchanged comparison thresholds. A C-transfer verdict remains pending.

**C training started (17:12 UTC).** OTA5t-C scratch run `6a61940deda14259b7c031f02cd91fbd` uses the fixed
800-launch budget. Its recorded initial parameters exactly match the qualified baseline; parameter definitions,
measurements, targets and registry also match. It reached 101 completed evaluations and 688 new learner updates
at the first audit. `phase1-complete.json` records the six probe receipts and this transition into C learning;
`progress.json` carries the current counters. The queue continues through all S, G and the one OTA5t O arm.

Offline phase-3 preparation is recorded in `phase3-structural-proposal.json`. It pins exactly one graph change to the
pooled OTA7t: move CC.MINUS from VOUT to a new NZ net, and add RZ between NZ and VOUT. Device/net/terminal-role
isomorphism rejects equivalence with all 15 archived task graphs. This is a proposed compensation variant, not a
constructed or measured circuit. The proposed bench inherits OTA7t's 1.0 V supply, 0.7 V common-mode, 30 uA bias and
10 pF load, with its 1 V MOS devices. Existing hash-pinned local PDK evidence supports the supply domain; actual
terminal-voltage, physical-export, action-bound and baseline qualification remains pending. No additional simulation
or schematic write was made for this preparation, and phase-3 construction still waits for the phase-2 verdict.

## 16. First C comparisons and rehearsal audit (2026-10-06, record 7.237)

All six scratch arms completed 800 launches each. General-model arms for OTA5t, **OTA7t-width** (`mscr_ota7t_w_c`)
and ring3 also completed and passed restoration. The fixed early window is designs 9–108; the final third contains
266 designs. Invalid designs remain in both denominators. These are the completed pairs at 20:00 UTC:

| C task | S early | G early | S final third | G final third | C1 / C2 / C4 |
| --- | --- | --- | --- | --- | --- |
| OTA5t | 2/100 | 83/100 | 252/266 (94.7%) | 254/266 (95.5%) | pass / pass / pass |
| OTA7t-width | 0/100 | 91/100 | 247/266 (92.9%) | 252/266 (94.7%) | pass / pass / pass |
| Ring3 | 4/100 | 24/100 | 33/266 (12.4%) | 168/266 (63.2%) | fail / pass / pass |

Ring3 improves substantially by the end but its 20-point early gain misses the fixed 30-point C1 threshold. The
weakest-row failure changes from first 200 to remaining 600 designs are −9.83 points (OTA5t UGB), −4.50 (OTA7t
gain), and −25.83 (ring3 frequency); these satisfy the row part of C4. This is an interim result, not a six-circuit
transfer verdict. VCO-G, LDO1-G, LDO2-G and OTA5t-O remain queued/running. Scratch VCO has 4/100 early and
246/266 late passes; both scratch LDOs have zero passes in 800. Source history is separate from the **9,391 new
launches** spent through the three completed pairs and all scratch controls.

`arm_review.py` independently audited all nine completed C arms, checking data/checkpoint hashes, exact C starting
parameters, physical rows and shared registry against the qualified baseline, fixed run settings and source-model
identity. It reads only the completed queue's trusted local checkpoint state after verifying every saved file hash
and matching optimizer/torch/PyG versions; it never resumes a model or changes an archive.

Replay membership equals the respective arm's admitted target transitions, with no source samples inserted. Every
logged update has the fixed batch size and learning rate; update totals equal admitted transitions after the first
seven warm-up insertions, times eight for S/O or two for G. The first three G arms record respectively **6,024 / 6,016 /
6,024 source draws** across **1,506 / 1,504 / 1,506 updates**, exactly four source samples per update. Each source task
appears equally often to within one draw; the sampler preserves its RNG/pending cycle and the pinned training-only
pool hash. Source/target batching remains 4+4. No source examples are charged as new simulator calls.

The scratch arms retain 37 measurement errors (22 OTA7t-width, nine LDO1, six LDO2); the completed G arms retain two
(OTA7t-width). All remain failed designs in comparison shares, without imputation or relabelling. There were no
infrastructure failures. These online measurement-error counts are not a new waveform-level diagnosis.

Eight synthetic rejection checks cover wrong update counts, missing update rows, changed learning rate, injected
source replay IDs, pool mismatch, wrong draw totals, task imbalance and duplicate pending tasks. A valid rehearsal
case passes. `follow_arm_review.py` now audits only newly completed arms and refreshes `arm-review.json`, alongside
the existing queue/progress/comparison tools. Frozen comparison criteria, model settings, runtime and source pools
remain unchanged. The phase-3 physical work still waits for the complete phase-2 verdict and its review.

## 17. VCO and LDO1 comparisons; held-out draft (2026-10-06, record 7.238)

At 20:46 UTC, VCO-G and LDO1-G have also completed 800 launches each, all valid, with restoration verified.
The independent training audit has passed all eleven completed S/G arms. Both new G runs have 1,506 updates,
6,024 source draws and target-only replay of 760 transitions, following the fixed 4+4 rehearsal recipe.

| C task | S early | G early | S final third | G final third | G passing / all | C1 / C2 / C4 |
| --- | --- | --- | --- | --- | --- | --- |
| VCO | 4/100 | 80/100 | 246/266 | 253/266 | 735/800 | pass / pass / pass |
| LDO1 | 0/100 | 4/100 | 0/266 | 99/266 | 155/800 | fail / pass / pass |

LDO1 passes C3 (some feasible designs) but misses the fixed early-gain threshold. Weakest-row failure changes are
−13.17 points for VCO center frequency and −27.50 for LDO1 HF PSRR. Across the five completed pairs, C1 passes on
three, C2 and C4 on five. LDO2-G and OTA5t-O remain; the six-circuit verdict and own-model diagnostic are pending.
Completed new cost is **10,991 launches**, plus the active run's ledger, against 12,591 through phase 2.

**Monitor recovery.** The original read-only progress watcher stopped on `/mnt/d`'s transient `ENODATA` while
reading the queue status. The real simulation queue continued. `resilient_monitor.py` now wraps only the monitors'
JSON I/O with bounded retries and permits at most three monitor starts for transient archive-read errors. Permanent
errors and failed audit checks remain fatal. Progress/comparison updates recovered; simulation settings, frozen
comparison code and archives were untouched. Synthetic checks cover recovery, permanent-error rejection and retry
exhaustion. Monitor receipts distinguish the wrapper from the unchanged comparison and audit scripts.

**Phase-3 preparation, no new physical cell or simulation.** `phase3_design.py` composes the existing builder into
the pinned series-RZ graph. DUT and bench geometry checks pass, including exact terminal agreement with the proposal.
Its eleven independent groups cover every MOS width/length through matched followers, CC multiplicity and RZ;
MOS copy counts and fingers stay at parent start A. The proposed RZ starts at 1 kΩ, with a 10 Ω–10 kΩ log domain;
this is an engineering start, not a measured zero-cancellation value. The OTA7t bench supplies 1.0 V, 0.7 V common-mode,
30 µA reference and 10 pF load. The copied OTA5t power expression was corrected from a literal 1.8 to **1.0 V**;
noise remains output noise integrated over 10 Hz–10 MHz. Maestro canonical readback and measured terminal voltages
remain physical gates. Negative geometry/lineage checks and baseline zero-update scheduling checks pass.

`phase3-target-protocol.json` freezes a deterministic baseline-only rule before any held-out measurements. For each
of the six fixed one-sided rows, sort valid random values from best to worst. Test a common rank from half the
smallest measured row (at most 32) downward to three. Choose the first vector of strictly positive observed limits
with at least three random designs meeting each row and no jointly passing initial or random design. Ties count in
full; invalid/missing values are never filled. If no vector qualifies, stop for baseline review before policy runs.
dB scales remain 6; other scales follow the existing default rule, and alpha is not calibrated. Synthetic checks
reject missing draws, policy contamination, identical values, absent measurements, invalid starts and duplicate rows.
This rule chooses targets only, without tuning the general model or anti-drift settings.

`create_phase3.py` is prepared but has not run. Its first gate requires a complete, recorded phase-2 review including
all thirteen S/G/O audits and C5. It refuses pre-existing cells without its own completed build receipt, uses an owned
temporary Maestro cell for canonicalization, and registers only the new held-out task. The phase-2 verdict need not
be positive for required phase 3; only optional phase 3b has that condition. Baseline qualification still precedes
every held-out policy arm. Frozen runtime and optimizer sources remain unchanged; no commit or push was made.

## 18. Phase-2 final result and review (2026-10-06, record 7.239)

All six S/G pairs and the OTA5t O control completed 800 launches each. The queue, independent arm audit and final
comparison monitor have finished. Every run restored its initial schematic; all thirteen training archives/checkpoints
passed the fixed-recipe, initial-parameter, source-lineage and replay audits. `phase2-reviewed.json` pins the final
comparison, queue, baseline/probe/training audits and every receipt. New cost is exactly **12,591 launches**.

| C task | S passing / 800 | G passing / 800 | S early → G early (of 100) | S late → G late (of 266) | C1 / C2 / C4 |
| --- | --- | --- | --- | --- | --- |
| OTA5t | 624 | 743 | 2 → 83 | 252 → 254 | pass / pass / pass |
| OTA7t-width | 404 | 740 | 0 → 91 | 247 → 252 | pass / pass / pass |
| Ring3 | 76 | 395 | 4 → 24 | 33 → 168 | fail / pass / pass |
| VCO | 462 | 735 | 4 → 80 | 246 → 253 | pass / pass / pass |
| LDO1 | 0 | 155 | 0 → 4 | 0 → 99 | fail / pass / pass |
| LDO2 | 0 | 87 | 0 → 0 | 0 → 55 | fail / pass / pass |

**The predeclared overall criterion is not met:** C1 passes on **3/6**, below the required 4/6. C2 passes on **6/6**
and C4 on **6/6**. Both LDOs pass C3; LDO2 first meets all goals at evaluation 200, after the early window. Its
weakest-row HF PSRR failure rate falls by 25.67 points from the first 200 to the remaining 600 designs. These
results establish the recorded gains and criterion outcomes at one seed, not a general transfer guarantee.

The own-data OTA5t control passed **751/800**, all valid: **91/100 early** and **254/266 late**. C5 passes:
own differs from the prior 90% early result by one point, and general's 83% is eight points below own. Its 6,024
updates and target-only replay of 760 transitions passed audit; it has no rehearsal. The general runs use
weights plus rehearsal, lower learning rate and fewer updates, so the comparison cannot isolate pretrained weights.

Scratch retains 37 measurement errors, general three (two OTA7t-width, one LDO2), and own zero. All remain in the
800-design denominators; none was filled or relabelled. LDO2-G's failed evaluation is a random warm-up draw and
was excluded from replay; its 760 admitted target transitions produce 1,506 updates and 6,024 source draws.
There were no infrastructure failures.
The original published models, historical source archives, source pool, settings and C1–C5 definitions remain fixed.
Historical costs are 17,124 general / 2,400 own evaluations; own's history overlaps the general pool and is not added
again as new simulation cost.

Required phase 3 proceeds after this recorded review. Its physical construction is a separate operation, followed by
the graph/native-CDF checks, one retained-results baseline, measured DC terminal screening, fixed target selection,
frozen probe and S/G comparison. `review_phase2.py` rejects premature closure; `create_phase3.py` requires its completed
receipt. Optional extra seeds and the folded-cascode extension have not been started.

## 19. Held-out OTA qualification and policy queue (2026-10-06, record 7.240)

After the completed phase-2 review, created owned cells `MScR/mscr_ota8m` and `MScR/tb_ota8m`, saved as
`real:mscr_ota8m`. This is the pinned **series-RZ compensation variant of the pooled OTA7t**, whose parent already
contains eight MOS including its bias diode. The exact delta moves CC.MINUS from VOUT to NZ and adds RZ from NZ
to VOUT. Typed connectivity matches the proposal and differs from all fifteen archived task graphs. Both schematics
have zero check errors/warnings; native CDF, legal domains, initial sizing, exported graph and all six canonical
Maestro expressions passed readback. Original cells were preserved. The builder's escaped-tab decoding correction
is recorded separately; its earlier source remains in `revisions/` with its prior hash.

There are eleven independent parameter groups over eighteen rows: matched MOS widths/lengths, M8 reference width,
CC multiplicity and RZ. Parent MOS multipliers/fingers remain fixed. The bench uses 1.0 V supply, 0.7 V common-mode,
30 µA reference and 10 pF load. Supply power includes the reference branch at the actual 1.0 V; noise is output RMS
integrated from 10 Hz to 10 MHz.

The retained-results baseline completed **65/65 valid evaluations**, exactly one initial design plus **64 random draws**,
with **zero learner updates** and verified restoration. Its original provisional-goal archive remains unchanged.
Measured DC screening over all six D/G/S/B pairs for all eight MOS passed on every design: the largest absolute
terminal difference was **0.7228107111 V**, below the pinned engineering ceiling of 1.1 V; every supply readback was
1.0 V. This is a DC screen, not enabled PDK SOA or PVT/transient certification. No extra simulations were needed.

The predeclared baseline-only rule selected common rank **28**. Each goal is individually met by 28/64 random
designs, and no initial or random design meets all six together. The exact limits are pinned in
`phase3-target-selection.json`; display values below are rounded. Saved task revision 2 preserves its baseline reference.

| Metric | Final held-out target |
| --- | --- |
| Gain | ≥49.140919 dB |
| UGB | ≥33.579796 MHz |
| Phase margin | ≥84.713358° |
| Supply power | ≤0.812261 mW |
| PSRR | ≥44.776813 dB |
| Output noise, 10 Hz–10 MHz | ≤42.351706 µV RMS |

`phase3-baseline-qualified.json` pins the measured baseline, voltage screen, selected goals, saved task and model
compatibility evidence. A separate private policy profile carries revision 2. All three configurations compile; both
transfer modes accept the same published general checkpoint. Preparation normalized optional schema fields and
supplied the starter response's omitted `run` section before freezing; no policy data influenced goals or settings.

At **21:53:51 UTC**, the durable phase-3 queue started in this fixed order: **frozen sampled probe 300 → scratch 800 →
general 800**, seed 0, four lanes. G retains the original half-source rehearsal, 2e-4 learning rate and two updates;
S retains 1e-3 and eight updates. Runtime, source model/pool and goals remain fixed. Policy cost is 1,900 launches;
including the baseline, phase 3 is **1,965**, giving **14,556** new launches through the required experiment.
`phase3-progress.json` records active progress; `phase3-comparison.json` reports qualified arms and the unchanged
C1/C2/C4 definitions. Each arm must pass restoration, archive/budget and checkpoint/replay audits before the next
starts. A failed gate blocks the queue without silently repeating simulation. `phase3-reviewed.json` is written only
when all three arms and their audits finish. No policy result is claimed in this start record.

Five synthetic queue rejection checks cover changed order, budget, baseline proof, goals and configuration, without
remote calls. The valid frozen queue and all qualification hashes pass. New helper/configuration hashes are pinned in
`experiment-scripts-sha256-7.240.json`; the prior 133-test production result applies to unchanged source. Optional
extra seeds and folded-cascode work remain unstarted.

## 20. Required experiment complete; held-out result (2026-10-06, record 7.241)

All required phases are complete. The phase-3 queue has exited; its baseline, frozen probe and both learning arms
passed restoration and archive/budget checks. Independent audits confirm initial sizing, physical rows, final goals,
checkpoint identity/integrity, target replay and the prescribed learning recipes. `phase3-reviewed.json` pins the final
phase-3 evidence; `experiment-reviewed.json` closes the required plan and re-verifies both phase reviews, all script
and runtime hashes, published checkpoints and the unchanged training-only source pool.

| Held-out `mscr_ota8m` arm | Valid | All passing | Early passing (of 100) | Final third passing (of 266 for S/G) |
| --- | --- | --- | --- | --- |
| Frozen sampled general probe | 300/300 | 0/300 | 0 | 0/100 |
| S: scratch | 800/800 | 486/800 (60.75%) | 1 (1%) | 245/266 (92.11%) |
| G: general plus fixed rehearsal recipe | 800/800 | 24/800 (3.00%) | 0 (0%) | 22/266 (8.27%) |

**The held-out head-start criterion is not met.** C1 and C2 fail; the early difference is −1 point and the final-third
difference is −83.83 points. C4 passes under its fixed definition: late G improves over early G, and its first-200
weakest row, power, falls from 147/200 failures to 199/600 (−40.33 points). This C4 result does not imply useful joint
feasibility or offset C1/C2. Scratch's success confirms that the frozen target set is achievable within the budget.

The frozen probe missed UGB on all 300 designs. Its 492 tensors, including temperature, remain equal to the published
model at all three checkpoints; online updates and actual replay are zero. Its 16 reset evaluations remain in the
300-design denominator. During G, some row tradeoffs improved, but its final third still missed phase margin on
152/266 designs, UGB on 89/266 and PSRR on 47/266; rows can overlap. No measurement or infrastructure failure occurred
in any held-out arm. First success was committed at evaluation 51 for S and 507 for G, with **54 versus 510 evaluations
charged** when confirmed (parallel work in flight included). The frozen probe is budget-censored without a success.

S and G each have 760 admitted target transitions. S recorded **6,024 updates**, without rehearsal; G recorded
**1,506 updates and 6,024 source draws**, four source plus four target examples per batch. All fifteen source tasks
are sampled equally to within one draw, and held-out data is absent from the pinned source pool. Every learning and
replay check passed. This compares the complete recipes—weights, rehearsal, learning rate and update count—not
weights alone. One seed on a compensation variant cannot establish unseen-family transfer or prove memorization.
The general model, source pool, goals and hyperparameters were not retuned from this result.

| New simulator cost | Qualified baselines | Frozen probes | S/G/O learning | Total |
| --- | --- | --- | --- | --- |
| Through phase 2 | 391 | 1,800 | 10,400 | 12,591 |
| Phase 3 | 65 | 300 | 1,600 | 1,965 |
| Required experiment | 456 | 2,100 | 12,000 | **14,556** |

Historical general-model experience remains **17,124** evaluations, with own's **2,400** overlapping that history;
these are separate from new cost. There are seven qualified task baselines, seven audited frozen probes and fifteen
audited learning arms. The original six-circuit verdict remains negative because C1 passes only three circuits,
although C2/C4 pass all six and C3/C5 pass. Both predeclared transfer verdicts are therefore negative, with the recorded
per-circuit gains preserved in section 18. Optional second seeds and folded-cascode phase 3b were not started.

All 150 frozen runtime files, all 7.240 experiment-script hashes, original comparison definitions, both published
checkpoints and source-pool hashes re-verify. Optimizer digest remains `0b0808bc…a7dbac8`. Production code has not
changed since the 133-test result; artifact-specific qualification/rejection checks are recorded separately.
`git diff --check` passes. No frontend build, service restart, original-schematic overwrite, commit or push occurred.

## 21. OTA8m continuation and matched-recipe follow-up (2026-10-06, record 7.242)

After reviewing the completed experiment, the user authorized two sequential follow-ups and specified **75%** as
acceptable. The operational definition is **at least 75 passing designs in the latest 100 committed evaluations**,
including resets and invalid designs. This is a new, post-result experiment; sections 18–20 and their verdicts remain
historical records. The target set, qualified baseline, circuit/start, seed 0 and four-lane execution stay fixed.

1. **Continue existing G:** resume the full state at `ckpt-00000800-003f07c8` in run `79c3220214104bb4950c98ebee4d0b5e`.
   Add up to **800** evaluations/launches (maximum lifetime 1,600). Keep learning rate 2e-4, two updates per admitted
   transition, batch eight with four source/four target examples, all optimizer/replay/RNG and rehearsal state.
   Request a graceful stop when a newly observed rolling window reaches 75/100. In-flight work may finish; record
   the first crossing, charged cost and final window separately. The extra 800 is a hard ceiling for this block;
   failure to reach 75% is reported, without an automatic additional block.
2. **Fresh G with scratch's recipe:** load the original published general checkpoint `ckpt-00000000-9b48fb98`, not the
   continued OTA8m model. Start new optimizers and empty target replay. Use learning rate **1e-3**, **eight updates**,
   batch eight entirely from the target task, **no rehearsal**, and the same remaining scratch hyperparameters.
   Preserve the original full-model transfer choice. Run the full **800** evaluations so its result can be compared
   with original G's first 800 and the existing scratch reference; report the first 75/100 crossing if any.

The primary comparison isolates the **recipe bundle** (learning rate, update count and rehearsal) between two G runs
with the same original model and simulation budget. It does not separate those three factors individually. Compare
all-run passing share, early designs 9–108, final 266, last 100, per-row failures and first-feasibility/75%-window cost.
The continued G curve is a separate test of learning duration and must not be presented as an equal-budget 1,600-vs-800
comparison. Extra cost is at most **1,600** launches; total new experiment cost is at most **16,156**.

Before continuation, all files of the original 800-evaluation G run were copied and verified under
`artifacts/general-network-20261006/ota8m-recipe-followup/original-G-800/`, outside the run catalog. Its run ID and cost
are unchanged; this copy is an immutable historical snapshot, not another run. `original-G-800-snapshot.json` pins
all files and the original receipt. The live run is resumed in place; use this snapshot to reproduce the original
phase-3 comparison after its lifetime counters grow. No original completed comparison receipt is rewritten.

Both configurations passed checkpoint compatibility. Before opening simulator lanes, a verification hook checks
loaded weights/temperature; continuation additionally checks all optimizer states, target replay and sampler RNG,
rehearsal state, collector RNG and the 800-evaluation/1,506-update counters. The hook observes state only. Fresh G must
have empty replay, new optimizers and no rehearsal. After each arm, restoration, dataset checksums, initial sizing,
recipe/counters, source lineage and replay are independently audited. Continued data must preserve the first 800 rows
and their immutable dataset files. Scripts/configuration/protocol hashes are pinned in the follow-up folder.

Five synthetic rolling-threshold cases, two state-equality cases and two changed-protocol rejection cases pass with
zero remote calls. Execution uses the unchanged frozen runtime and a private settings copy. No new baseline, source
pool change, offline pretraining rerun, automatic switching rule or additional seed is included in this follow-up.

## 22. OTA8m follow-up complete (2026-10-07 London time, record 7.243)

Both user-authorized arms completed their stopping/budget rules, restoration and independent audits. The continuation
met the requested 75/100 threshold within its additional 800-launch allowance. The fresh run completed all 800 for
the recipe comparison. `ota8m-recipe-followup/reviewed.json` pins the final comparison, protocol, scripts and audits;
`invariance-review.json` verifies the preserved original archive, unchanged earlier evidence/scripts, frozen runtime,
original published checkpoint and rehearsal pool. The durable queue exited at 00:11 London time (23:11 UTC on October 6).

**Continuation with unchanged recipe.** G first reached 75/100 at committed evaluation **1,367**, when **1,370**
evaluations had been charged. The archived-window monitor observed the crossing at commit 1,379 and requested a
graceful stop; pending work completed. Final lifetime cost was **1,388**, or **588 additional launches**, with **76/100**
passing in the final window. This meets the agreed operational criterion; a selected crossing window is not an
independent estimate of long-run policy reliability. All 1,388 measurements are valid. The added segment passed
**298/588 (50.68%)**; lifetime passing is **322/1,388 (23.20%)**. These whole-run shares are distinct from the 76% final
window. The original 800 recorded evaluations and immutable dataset files are unchanged.

Exact-resume verification passed before opening lanes: actor/critics/targets/temperature, all three optimizer states,
760 original target transitions and their sampler RNG, rehearsal state, collector RNG, 1,506 prior updates and the
800-evaluation ledger. At stopping, replay contains 1,318 target transitions and the learner has 2,622 total updates;
rehearsal has drawn 10,488 historical examples, an increase of 4,464. No learning recipe changed during continuation.

**Equal-budget comparison from the original general model.** The fresh G run verified identical initial source
weights/temperature, fresh optimizers, empty replay and disabled rehearsal. It then used the scratch hyperparameters
with target-only batches. All 800 measurements are valid; the final checkpoint has 6,024 updates and 760 target
transitions, without source samples. Task, starting parameters, fixed goals, seed and four lanes match.

| OTA8m arm, first 800 evaluations | All passing | Early (100) | Final third (266) | Final 100 | First success, charged cost | First 75/100, charged cost |
| --- | --- | --- | --- | --- | --- | --- |
| Original G: 2e-4, two updates, half-source rehearsal | 24/800 (3.00%) | 0 | 22 (8.27%) | 15 | 510 | Not reached within 800 |
| Fresh G: 1e-3, eight updates, target-only | 491/800 (61.38%) | 0 | 217 (81.58%) | 89 | 137 | 354 |
| Existing S: random initialization, scratch recipe | 486/800 (60.75%) | 1 | 245 (92.11%) | 96 | 54 | 373 |

The fresh recipe adds **467 passing designs / 58.375 percentage points** over original G at the same 800-launch budget.
Its first 75/100 window ends at commit 351, charged cost 354, versus commit 1,367 / charged 1,370 for continued original
G. This substantial difference belongs to the whole recipe bundle; learning rate, update count and rehearsal changed
together, so this experiment cannot assign causality to rehearsal or either learning setting separately.

Compared with scratch, fresh G has only five more passing designs overall, reaches its first success later, reaches
the 75/100 window slightly earlier, and has a **10.53-point lower final-third rate**. Both G recipes score 0/100 in the
fixed early window. There is no clear general advantage over scratch from this single seed. The follow-up shows that
original G's poor 800-budget result was strongly recipe-dependent, and that the same conservative recipe can reach
75/100 given more training. It does not justify the conclusion that the general model cannot adapt to this circuit.
The new post-result recipe must not replace the frozen original experiment's negative verdict.

**Cost and preserved evidence.** This follow-up spent **588 + 800 = 1,388 new launches**, leaving 212 of its 1,600 cap
unused. Total new cost across the original experiment and follow-up is **15,944**; historical pretraining remains
separate. No new baseline or source pretraining was run. The original G-800 snapshot remains byte-verified and is the
reference for reproducing the original comparison now that the live G run has a continuation segment. All scripts,
150 runtime files, original general checkpoint and source-pool hashes re-verify. Production source is unchanged;
the earlier 133-test result and the nine follow-up offline checks remain the relevant checks. `git diff --check` passes.

## 23. The held-out circuits built for the purpose, and the equal-recipe arms (2026-10-07, record 7.262)

User: "build the folded cascode as the real held-out circuit and test the general model on it with same recipe. Delete the
previous task but rename and keep actual circuit in the vm library. queue redo an equal-recipe comparison on the six C
tasks"; then "build the telescopic cascode too after the folded cascode, if the circuit is from any publicated sources it
would be better"; and the caveat "LDO2's error amplifier in the pool is itself a folded cascode ... 'held-out' here means an
unseen circuit, bench and metric set".

**The equal-recipe arms on the six C tasks (G2).** The general model loaded with the SCRATCH recipe (1e-3, eight updates,
target-only, no rehearsal; the "fresh G" recipe of section 22), seed 2, 800 launches, the same C tasks, goals, registry,
runtime and settings copy as the original S and G arms, so the three arms of a circuit differ only in the recipe:

| C task | S: passing / early / last third | G (anti-drift recipe) | G2 (scratch recipe) |
|---|---|---|---|
| ota5t | 624 / 2 % / 95 % | 743 / 83 % / 95 % | 742 / 88 % / 95 % |
| ota7t_w | 404 / 0 % / 93 % | 740 / 91 % / 95 % | 745 / 88 % / 94 % |
| ring3 | 76 / 4 % / 12 % | 395 / 24 % / 63 % | 245 / 24 % / 30 % |
| vco_lin_c | 462 / 4 % / 92 % | 735 / 80 % / 95 % | 740 / 83 % / 95 % |
| ldo1_rgcn | 0 / 0 % / 0 % | 155 / 4 % / 37 % | 34 / 2 % / 8 % |
| ldo2_rgcn | 0 / 0 % / 0 % | 87 / 0 % / 21 % | 80 / 0 % / 14 % |

The recipe does not change the head start (the same 83-91 % early on ota5t, ota7t_w and vco_lin_c; 24 % on ring3; the
LDOs at 0-4 %), so the head start is the weights' doing, not the recipe's. The late phase differs: the anti-drift recipe
(lower learning rate, two updates, half-source rehearsal) kept improving on ring3 (63 % against 30 %) and ldo1 (37 %
against 8 %), where the scratch recipe did not; on the four easy circuits the two recipes end alike. C1 stays at three of
six under either recipe. 4,800 launches, 06:54-09:29.

**Two held-out circuits built for the purpose.** Each registered as a task of its own in library MScR, baselined with 64
random designs (required), goals from the baseline-only rule, then the frozen probe (300, sampled actions), scratch
(800) and the general model with the scratch recipe (800), seed 0, through the same frozen runtime as every arm above.
Pipeline: `artifacts/general-network-20261006/folded-cascode/` (fc_pipeline.py, fc_run.py, queue_fc.sh, graph_audit.py,
retire_ota8m.py, trial_nodes.py, the logs, checks, configurations and results).

- **Folded cascode `real:mscr_otafc`** (own design; `~/mscr_circuits` designs.OTAFC / circuits.otafc / TASKS['otafc']):
  NMOS pair, PMOS folding sources, PMOS cascodes, an NMOS cascode mirror load, the whole bias network inside from the
  30 uA reference (wide-swing diodes for both cascode rails); 19 transistors, 14 groups over 36 rows, the ota5t bench and
  six metrics at 1.0 V, 0.65 V common mode, 10 pF. Start design after one resizing round (the first sat at the saturation
  edge): 50.3 dB, 12.5 MHz, 86 deg, 0.30 mW, 58 dB PSRR, 36 uV.
- **Telescopic cascode `real:mscr_otatc`**, the single-ended port of the Analog Design Bench task
  `sky130-telescopic-cascode-ota-pvt-fix` (Yilin Xu; Arcadia-1/analog-design-bench, task content CC BY-NC 4.0; its files
  stayed outside the repository): the published NMOS-input telescopic signal path and its three bias rails from one 50 uA
  reference (the NMOS cascode rail from an input-tracking replica, I x R1 and a matched diode; the PMOS cascode rail from
  VDD - I x R2 - a matched diode; the PMOS mirror master rail) are kept; the published circuit is fully differential with
  a CMFB loop, so the single-ended variant takes the PMOS cascode current-mirror load and drops the loop; the replica
  follows VINP. Ported to GPDK045 1 V devices at the published lengths; 18 transistors and two resistors, 18 groups over
  38 rows. Two resizing rounds (every NMOS mirror device doubled for lower overdrive, the PMOS stack widened, R2 raised;
  the PDK form caps the multiplier at 100, so the tail and the top pair use two fingers): 47.7 dB, 17.5 MHz, 87.5 deg,
  0.24 mW, 46 dB PSRR, 29 uV, every device saturated with margin.

**The goal rule needed a floor.** The rank rule of section 19 gave the folded cascode `PM >= 90.24 deg` at rank 30, a
limit only weak, slow designs reach: the scratch arm met every other row in 44-93 % of its designs and that row in 8 %,
and no design of 800 passed jointly (probe 0 / 300, S 0 / 800, G 0 / 800: the first goal set, kept on record). The
revision keeps the rule for five rows and puts the phase-margin row at the standard 60 deg floor (`PM_FLOOR`,
fc_pipeline.goals_with_pm_floor); the telescopic got the floor from the start. Under the revision 3 of the 64 random
designs pass all six rows on each circuit, and - a difference from the rule of record, stated here - the START design of
each circuit passes too (its power sits 1-2 % inside the power row); every episode reset re-evaluates the start, so the
"as recorded" counts (the 7.229 definitions) contain those resets as passes; the policy-only columns leave them out.

| Circuit, goals | Arm | Passing, as recorded | Early 9-108 | Last third | Policy designs: passing | Policy early (own proposals among 9-108) |
|---|---|---|---|---|---|---|
| folded, revision 3 | probe | 75 / 300 (25 %) | 25 % | - | 59 / 284 (21 %) | 21 / 96 |
| folded, revision 3 | S | 471 / 800 (59 %) | 13 % | 93 % | 431 / 752 (57 %) | 9 / 92 |
| folded, revision 3 | G | 524 / 800 (66 %) | 20 % | 95 % | 484 / 752 (64 %) | 16 / 92 |
| telescopic | probe | 21 / 300 (7 %) | 6 % | - | 5 / 284 (2 %) | 2 / 96 |
| telescopic | S | 322 / 800 (40 %) | 8 % | 89 % | 281 / 752 (37 %) | 3 / 92 |
| telescopic | G | 767 / 800 (96 %) | 73 % | 100 % | 726 / 752 (97 %) | 68 / 92 |

Criteria of section 5: folded cascode C1 fails (20 % against 13 %, +7 points), C2 passes (95 % against 93 %), C4 passes
(the weakest row, power, falls from 58 % failures in the first 200 to 13 % after); telescopic cascode C1 passes (73 %
against 8 %, +65 points), C2 passes (100 % against 89 %), C4 passes (power 10 % to 0 %). By the rule of section 6, "the
general network transfers to an unseen amplifier" holds for the telescopic cascode and not for the folded cascode. One
seed each; the start designs pass the goals (above); the verdict carries the caveat below.

**The caveat and the typed-graph audit.** LDO2's error amplifier (ldo2_rgcn, its _b start, the _gt variant: four pooled
runs, 5,164 evaluations) is an NMOS-input folded cascode with PMOS folding sources and cascodes and NMOS sinks, bias from
two pins, so the folded-cascode building block is in the pool; "held-out" means an unseen circuit, bench and metric set.
`graph_audit.py` on each circuit's baseline graph: whole-graph isomorphism with none of the fifteen archived pooled graphs
nor OTA8m; the pooled amplifier cores (LDO2's nine-transistor amplifier, the LDO1 and ldo_basic 5T amplifiers, ota5t,
ota7t) embed in neither new graph as a labelled subgraph (device kinds and terminal roles) - the shared fold is a shared
idea with different wiring (the mirror in the NMOS load, the bias inside), not a copied block. The telescopic's result is
the stronger one: its stacked-cascode structure has no pooled relative, its zero-shot probe is near zero (2 % of own
proposals), and the loaded model still reaches 73 % in its first 100 own proposals against 8 % from scratch.

**OTA8m retired** (user: "delete the previous task but rename and keep actual circuit in the vm library"): the cells were
rebuilt from Codex's frozen draft as `MScR/mscr_ota7t_rz` and `tb_ota7t_rz` (what they are: the pooled OTA7t with a series
nulling resistor), their readback compared with the originals instance by instance (equal; RZ's "1K" against "1.0K" is
the same 1 kohm), then `mscr_ota8m` and `tb_ota8m` deleted; the task registration `real:mscr_ota8m` backed up
(`folded-cascode/retired/mscr_ota8m-profile.tar.gz`) and removed from the profiles and the Tasks window's folders. Its runs
and Codex's artifacts are untouched.

**Cost.** 10,632 new launches: the six G2 arms 4,800; the folded cascode 1,965 (first goals) + 1,900 (revision 3); the
telescopic 1,965; two automatic one-design baselines at task creation; plus 7 plain Spectre trial runs for the start designs.

**Incidents, on record.** WSL's /mnt/d mount died at 09:40 (every access an I/O error; the drive fine on Windows; a peer's
git crashed with SIGBUS); the user remounted; the first remount lacked the user id (root-owned files, tar unable to set
times, so the workbench's Check now export step failed until the second remount at about 10:20); the backend died in the
outage and the committing session restarted it. Maestro's netlister reuses a cached subcircuit netlist on the VM
(`ihnl` under the trial's folder), so a rebuilt cell simulated with its old sizes until that folder was deleted before each
trial. The rank-30 queue script died of a bash syntax error after its last stage because the file was edited while that
instance ran (nothing lost; the next chain started from the completed state).
