# Plan: one general network from all saved experience, then the six circuits from a third start (2026-10-06, record 7.230; rewritten as record 7.232)

User: "write the plan is it possible to train one general network with all the previous saved experience and then compare
the six cases with different starting design parameter and starting seed from scratch and load the general network. how
to avoid policy drift?" Then, after asking what arm O and leave-one-out do and whether a more complex op-amp added to the
library could serve as the held-out test: "rewrite the plan" and "arm o trim to only ota5t circuit".

Status: plan only. Nothing is built, no task is registered, no simulation has started. Every number below is read from
the recorded runs under `outputs/` and from the source at commit `2cba8c6` (optimizer digest `0b0808bc`); the rewrite
changed no fact. What the rewrite changed: arm O is one run, on ota5t, a check of the offline method rather than a transfer
measure (it repeats 7.229's question); phase 3 is a held-out two-stage op-amp built for the purpose (section 6) instead
of leave-one-out. Section 10 lists the decisions the user has to take before anything is built; sections 4 and 8 name
which steps would and would not change the optimizer package.

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
  evaluations over 15 tasks of 10 circuits, share today's reward settings and pool as they are; 8 older ota7t runs (4,326
  evaluations) were recorded under earlier reward settings and would need their rewards recomputed first. The recommended
  training method uses the existing learner unchanged: nothing in `src/analog_optimizer/` changes, the cost is about an
  hour of CPU, no Spectre launch.
- **(b) It can be measured the way record 7.229 measured fine-tuning:** six new start-C tasks, two arms each (scratch,
  load-general), seed 2, 800 launches, the criteria of 7.229 plus a "no drift" criterion. 9,600 Spectre launches, about 5
  hours. One extra run on ota5t (a model of ota5t's own data, trained offline) checks that the offline route keeps the head
  start 7.229 measured live. A circuit the network never saw, a two-stage op-amp built for the purpose (section 6, 1,965
  launches), is the only test of knowledge that carries across circuits.
- **(c) Policy drift** here means: the loaded model loses part of what it knew while its weights are updated on the new
  task. Record 7.229 saw it on ldo1_rgcn (27 % of the first 100 own proposals passed, 7 % of the last third). The lever that
  attacks the cause (rehearsal: keep drawing half of every update batch from the pooled experience) is a workbench engine
  change, not an optimizer change; three further levers are settings that exist today; the regularizers of the literature
  that would change the optimizer are listed and not proposed (section 8).

What "general" means and does not mean. The network reads the circuit graph and the Specs rows, so one network can serve
many circuits: that is what the graph encoder and the spec context exist for. Trained on these ten circuits it is general
over THEM; whether it helps a circuit it never saw is what the held-out op-amp of section 6 measures. The literature has
no published joint RL sizing policy evaluated on a held-out circuit family (answer of 2026-10-06, memory "unified model
question"). "General" is also not weight averaging: the six A models cannot be merged (different spec schemas, and
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

The union of the 15 task registries holds 34 metrics. 26 agree on unit and reference everywhere; 8 agree on the unit and
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

Width. 34 slots make a context of 34 x 21 + 11 = 725 columns (today: 95 for ota7t_w, 137 for ota5t, 116 for ring3, 221
for the LDOs, 284 for vco_lin_c). The layer that reads the context grows with it; the parameter count is read from the
model inspection once the registry is fixed (phase 0 output).

Where it is set. `run.advanced.spec_registry` (a list of metric id, unit, reference) in the run configuration; the run
then compiles its SpecSchema from that list. Every run that loads the general model must set the same list; the
compatibility check enforces it, so a mistake fails loudly. Both arms of the comparison set it (the scratch arm too), so
the two arms differ only in the loaded weights. The comparison's runs are CLI runs from written configurations, as
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
   `scratch`, task name "general (10 circuits)", a `pretraining` block with the pooled runs, their evaluations, the
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
workbench and checked with Check now; a Baseline simulation per task is optional (6 x 65 launches).

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

**Zero-shot probes first** (phase 1): the general model in frozen mode, sampled actions, 300 launches on each of the six B
tasks (they exist; their 7.229 numbers are the reference). They measure what the network knows before any update:
passing share, best reward, per-row failure shares. Deterministic actions would repeat one four-design episode; sampled
actions give 300 different designs.

**Measures**, the definitions of record 7.229 (section 5 of `docs/plan-finetune-vs-scratch.md`): early share = passing
share of designs 9-108 (the first 100 own proposals after the 8 random warm-ups), cumulative passes by 100 / 200 / 400,
the "50 % by" point, last-third share, mean reward early and late, per-row failure shares, working time.

**Criteria**, fixed before any run starts:

- C1 head start: G's early share at least 30 points above S's.
- C2 end: G's last-third share within 5 points of S's or above.
- C3 LDOs: G passes at the relaxed targets.
- C4 no drift (new): G's last-third share at least its early share minus 10 points, and the failure share of G's weakest
  row does not rise by more than 15 points from its first 200 designs to the rest (ldo1_rgcn in 7.229 would fail both:
  27 % to 7 %, the HF PSRR row 63 % to 82-88 %).
- C5 offline method (ota5t only): O's early share within 10 points of 7.229's live fine-tune (90 %), and G's within 10
  points of O's.
- Zero-shot: reported, no bar; a passing share above S's early share says the knowledge transferred before any update.

Verdict rule: "one general network transfers to a new start" if C1 holds on at least four of six circuits, C2 on six and
C4 on at least five; otherwise reported as measured, no claim. One seed per arm, as in 7.229; a second seed on the
circuits whose arms end within the seed spread is decision D7.

---

## 6. The held-out op-amp (phase 3): a circuit the network never saw

Phase 2 tests the general network on circuits that are in its pool, the in-distribution case. A circuit outside the pool
is the only test of knowledge that carries across circuits. Leave-one-out (six networks each trained without one circuit,
one run per held-out circuit) was the first version of that test; the rewrite replaces it with a circuit built for the
purpose. It is a true unseen circuit, in a family the pool knows from two single-stage OTAs; the general network trained on
all ten circuits is tested as it is, no extra networks; and for a new circuit there is no own-data model, so scratch
against load-general is the whole story. 1,965 launches instead of 4,800.

**The circuit.** A two-stage Miller-compensated OTA, `real:mscr_ota8m` (name proposed): differential pair, current-mirror
load, tail source, a common-source second stage with its current source, a bias mirror; eight transistors, a Miller
capacitor with a nulling resistor. A textbook circuit like the rest of the MScR library, with two things the pool's
amplifiers lack: a second stage, and a compensation network (a capacitor and a resistor inside an amplifier; the pool
holds such parts only in the LDOs). A folded-cascode OTA (`mscr_otafc`, eleven to thirteen transistors, single stage) is
the harder second point if the first result is positive; it is the same recipe again.

**What makes it cheap.** The cell gets the ota5t pins (VINP, VINN, VOUT, IBIAS, VDD, VSS), so the ota5t testbench and its
six metrics (gain_db, ugb_hz, pm_deg, power_w, psrr_db, noise_vrms) carry over as the B tasks' testbenches did, a copy with
the cell name swapped. The shared registry already holds the six metrics, so no slot is added. The device kinds (1 V MOS,
MIM capacitor, resistor) are in the component list through the LDOs. Node count and action dimensions are deliberately not
compatibility criteria (`check_compatibility`), so the general model loads on the bigger graph with its more numerous
parameter groups.

**Rows and targets.** Parameters as in ota5t (w and l of every transistor, matched pairs as leader and followers) plus the
Miller capacitor and the nulling resistor. Specs: the six ota5t metrics, Scale 6 on dB rows. The targets are fixed AFTER a
Baseline simulation (the baseline design plus 64 random designs), not before: each row at a level some random designs
reach on their own, the whole set reached by none, and the gain target above what a single-stage OTA gives (a two-stage
amplifier is asked for 60 dB or more), so the task is not an ota5t in disguise. The LDO lesson of record 7.229: a row no
design can reach makes every arm look the same.

**Fixed before phase 0:** the circuit's spec list. The registry is fixed when the general network is trained; a slew-rate
or settling row would need a transient testbench and a registry slot added before training. Decision D10 (recommended:
the six ota5t metrics only).

**Start and arms.** One start, the textbook sizing (start A, as the library's circuits), seed 0. First the zero-shot probe
(frozen, sampled actions, 300 launches), then S (scratch) and G (load-general with the anti-drift settings) at 800
launches each. With the baseline simulation: 65 + 300 + 1,600 = 1,965 launches, about 1.5 h. The cell is a few hours of the
writer on the VM, as the six B cells were (`~/mscr_circuits`: `circuits.py`, `designs.py`, `tasks_def.py`,
`save_tasks.py`); it can be built and baselined during phase 2a, in the same Virtuoso session of work, and its runs wait
for phase 2's verdict.

**Criteria:** C1, C2 and C4 of section 5 on this circuit; the zero-shot share reported. "The general network transfers to
an unseen amplifier" if C1 and C2 hold; one circuit and one seed, so a second seed follows if the arms end within the seed
spread. What the result means: the network has seen only 5T and 7T single-stage OTAs; a head start on a two-stage
amplifier is cross-topology transfer within the family, the strongest claim this plan can make; no head start means the
network is a memory of the circuits it saw, still useful, a narrower claim. Once run, the circuit's data joins the pool
(eleven circuits) for the next network.

---

## 7. Budget and time

| Phase | What | Spectre launches | Time |
|---|---|---|---|
| 0 | shared registry, pooling tool, offline training, held-out checks, model folder (the general model; the ota5t own-data model under D6) | 0 | about 1 h CPU per network, plus the tooling |
| 1 | zero-shot probes of the general model on the six B tasks | 1,800 | about 1 h |
| 2a | six C cells and tasks (Virtuoso writer, Check now); baselines optional; the held-out op-amp's cell and baseline can be built here too | 0 (390 with baselines; +65 for the op-amp) | about 1 h (plus 25 min), plus a few hours for the op-amp cell |
| 2b | arms S and G on the six C tasks | 9,600 | about 5 h (7.229's twelve ran 06:58-12:03) |
| 2c | arm O on ota5t (D6) | 800 | about 12 min |
| 3 | the held-out op-amp: zero-shot probe, arms S and G | 1,900 (1,965 with its baseline) | about 1.5 h |
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
launches). Phase 2: the C cells and tasks, the held-out op-amp's cell and baseline in the same Virtuoso session of work,
then the twelve runs plus arm O on ota5t through the 7.229 queue, `compare.py` extended by C4 / C5 and the zero-shot rows.
Phase 3 (after the verdict of phase 2): the held-out op-amp's probe and two runs; the folded cascode only after a positive
result.

Nothing simulates without the user's word; the phases are separately approvable.

---

## 10. Decisions for the user

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
    row (a slew or settling row adds a registry slot before phase 0 and a transient testbench); its cell built during
    phase 2a, its runs after phase 2's verdict; the folded cascode `mscr_otafc` as a second point only after a positive
    result. Recommended as stated.

Parked, as every further plan must say: the SKY130 benchmark (AnalogGym-Opt import, calibration with zero passes, the
tunable bias current) stays untouched; the MScR circuits on Spectre are the test bed.

---

## 11. What goes on record

This plan; record entries 7.230 (the plan) and 7.232 (the rewrite); when built: the `pretrain` command, the drift meter
and the keep-best rule with tests and their rows in `docs/functionality-reference.md`; the rehearsal decision in
`docs/decisions.md` if D4 is yes; the C tasks' and the held-out op-amp's definitions in `~/mscr_circuits`; the model
folders' `pretraining` blocks; the comparison's `results.md`. Under D8 = no, nothing in `src/analog_optimizer/` changes.
