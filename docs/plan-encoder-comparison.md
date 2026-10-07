# Plan: the other encoders on the six circuits, compared with the Graph Transformer (A, B, C)

Revised 2026-10-07 (Europe/London), record 7.256, session "Encoder run plan revision". User: "[reusable encoder run
plan] base on this file and the chat task button and fine-tuning comparison plan, revise the plan of running other
encoders on the six circuits as comparison".

Status: **plan only; nothing started, no task changed, no run queued.** The twelve from-scratch configurations of record
7.231 stay as they are (revalidated today against the current source: 12 of 12, no error); the rest of this plan says
what to prepare around them. The six circuits are OTA5t, OTA7t (the width task), LDO1, LDO2, RING3 and VCO_linear_c.
Revision 2 (07:30; user: "does ota8m count as a heldout? shouldnt it only happen on the folded-cascode?"): stage D, the
held-out test on the folded cascode only, added as section 6.3; OTA8m does not count; the budget rows follow.

What this plan is built from:

- the reusable protocol [six-circuit A/B/C run plan](plan-encoder-baseline-abc.md) (record 7.244): stages A, B, C, the
  frozen starts, settings, measures and criteria, the budget worksheet;
- the chat "Task button and fine-tuning comparison plan": the task window and the six start-B tasks (7.227), the
  fine-tuning comparison and its twelve Graph Transformer runs (7.229, [plan and results](plan-finetune-vs-scratch.md)),
  the general-network plan (7.230 / 7.232, [plan and results](plan-general-network.md)) and its execution (7.233-7.243);
- the encoder libraries `graphgps` and `xatten` with their twelve tasks and twelve prepared runs (7.231), the two
  encoders themselves ([GraphGPS and parameter-group cross-attention](global-encoders.md), 7.228);
- today's workbench changes: Save as (7.246), the automatic one-launch baseline of every saved task and Calibration =
  64 random designs only (7.248), task names without `real:` (7.249), task folders per encoder (7.250).

It replaces the twelve-run queue of 7.231 as "the plan": that queue is stage A of this one. The same plan as a private
page: https://claude.ai/artifact/D3Sc9TZYdcVg5yUQ8oPbtc.

## 1. In plain words

Every other encoder goes through the three stages the Graph Transformer (GT) has gone through, on the same six
circuits, the same starting designs, seeds, budgets and learning settings, so that the only difference in each
comparison is the network:

| Stage | Question | Runs per encoder | Start, seed | Compared with |
|---|---|---|---|---|
| **A** learn from scratch | does the encoder learn each circuit within 800 launches, as well as GT? | 6 scratch | A (the task's own start), seed 0 | GT's A runs (7.199, 7.216, the ota7t width run; new matched runs for the two LDOs) |
| **B** same circuit, new start | does its own A model carry over to a new starting design, as GT's did? | 6 scratch + 6 fine-tune | B (the random design of record, 7.227), seed 1 | GT's twelve B runs (7.229) |
| **C** one general model | does one model of this encoder, trained offline on the recorded GT experience of the six circuits, help on a third start? | 6 frozen probes + 6 scratch + 6 general + 1 own (ota5t) | C (the 25th-percentile random design, 7.232), seed 2 | GT's C-S runs (7.239), the equal-recipe G2 runs (queued 2026-10-07 06:54), arm O (7.239) |
| **D** held-out circuit | does the general model help on a circuit it never saw? | 1 frozen probe + 1 scratch + 1 general on the folded cascode | the folded cascode's own start, seed 0 | the folded-cascode session's probe / scratch / general runs on the same task |

Stage by stage, with the user's go between them: A for both new encoders first (one evening), then B for the encoders
that learned, then C; D, the held-out folded cascode, needs only the offline general models (section 6.3). The two new encoders are GraphGPS (`graph_gps`, with random-walk structural inputs) and the
parameter-group cross-attention (`group_cross_attention`); RGCN and GATv2 can follow the same protocol later
(section 3.6).

What is reused from the GT work and what GT still lacks: GT's 4 A runs on the non-LDO circuits, its 12 B runs, its 6
C scratch runs, the 6 equal-recipe G2 runs now in progress (the folded-cascode session of section 2.3) and arm O are matched references under the settings of this
plan (section 2.3). GT lacks matched A runs on the two LDOs at the relaxed HF PSRR targets (its A runs asked -5 dB,
which nothing met) and B fine-tune runs on the LDOs from such parents: four GT runs, 3,200 launches (section 3.4).

Two deliberate departures from the A/B/C runbook, both so that the recorded GT runs stay valid references instead of
being rerun (14,400 launches saved); both are the user's decision (section 10): the spec registry is the task's own in
stages A and B and the shared 41-slot one in stage C, exactly as GT ran (3.1); a loaded model keeps its learned
temperature, as every recorded loaded GT run did (3.2).

Cost of the whole pilot for the two new encoders: **60,666 Spectre launches, about 33 h of simulation**, one run at a
time, the held-out stage D included; stage A alone **11,276 launches, about 6 h** (section 8). Offline training adds CPU hours, no launches.

## 2. What exists today

### 2.1 Encoders

| Encoder ID | Structural input | Library / task folder | Starting preset | Learner step, synthetic replay (1 thread, load ~5-6) |
|---|---|---|---|---|
| `graph_transformer` | none | `MScR` / Graph Transformer | 48 hidden / 4 heads / 4 layers | 48.3 ms |
| `graph_gps` | `rwse` (walk lengths 2, 4, 8, 16) | `graphgps` / GraphGPS | 48 / 4 / 4 | 55.2 ms (1.14x GT) |
| `group_cross_attention` | none | `xatten` / Group Cross Attention | 48 / 4 / 4 | 38.7 ms (0.80x GT) |

The timing is `tests/perf/learner_update_profile.py` today at HEAD `8b2d29e` (optimizer digest `0b0808bc`), 60 timed
updates of batch 8 after 20 warm-ups, the synthetic op-amp fixture; file
`artifacts/local/reviews/encoder-libraries-2026-10-06/profile-encoders-synthetic-2026-10-07.json`. It says the new
encoders cost about the same learner time as GT, so the recorded GT working times are the time estimate for them
(section 8). All three SAC settings blocks are identical (the presets inherit GT's: learning rate 1e-3, initial alpha
0.01, 8 updates per transition, gamma 0, batch 8, replay 10,000, episode length 4), checked by `make_configs.py` of 7.231.
Parameter counts of actor / Q1 / Q2 are read from the saved-model structure view when the first A run of each encoder
is saved; equal 48 / 4 / 4 does not mean equal counts (the A/B/C runbook, section 3).

### 2.2 Tasks

| Circuit | A task (start A) | A copies for the new encoders | B task (start B) | C task (start C) | Lanes | LDO HF PSRR |
|---|---|---|---|---|---|---|
| OTA5t | `mscr_ota5t` | `graphgps_ota5t`, `xatten_ota5t` | `mscr_ota5t_b` | `mscr_ota5t_c` | 4 | - |
| OTA7t width | `mscr_ota7t_w` | `graphgps_ota7t_w`, `xatten_ota7t_w` | `mscr_ota7t_w_b` | `mscr_ota7t_w_c` | 1 | - |
| LDO1 | `mscr_ldo1_rgcn` (-5 dB) | `graphgps_ldo1`, `xatten_ldo1` (-3 dB) | `mscr_ldo1_rgcn_b` (-3 dB) | `mscr_ldo1_rgcn_c` (-3 dB) | 4 | <= -3 dB in every new arm |
| LDO2 | `mscr_ldo2_rgcn` (-5 dB) | `graphgps_ldo2`, `xatten_ldo2` (-2.3 dB) | `mscr_ldo2_rgcn_b` (-2.3 dB) | `mscr_ldo2_rgcn_c` (-2.3 dB) | 1 | <= -2.3 dB in every new arm |
| RING3 | `mscr_ring3` | `graphgps_ring3`, `xatten_ring3` | `mscr_ring3_b` | `mscr_ring3_c` | 4 | - |
| VCO_linear_c | `mscr_vco_lin_c` | `graphgps_vco_lin_c`, `xatten_vco_lin_c` | `mscr_vco_lin_c_b` | `mscr_vco_lin_c_c` | 4 | - |

All 34 registered tasks are listed by the running backend (task keys keep `real:`; the page shows them without it since
7.249). The twelve copies hold the A task's rows, Scales (6 on dB rows), probes, analyses, model file and starting sizes
(7.231: DUT texts byte-identical to the MScR cell but for library and cell name); the `_b` and `_c` tasks hold the frozen
B and C vectors (`~/mscr_circuits/designs.py`: `*_B`; `artifacts/general-network-20261006/start-c.json`). `_rgcn` in the
LDO names is a paper's method, not the encoder of any run. A task does not force an encoder: the encoder is a run
setting; the Tasks window's folders only organize (7.250).

### 2.3 Graph Transformer runs of record, and whether they are matched references

Matched = same start, seed, budget, lanes, reward, SAC settings, registry kind and temperature policy as this plan's
arms. The optimizer source differs by digest between the A runs (`f83342bc`), the B runs (`4aebbfab`) and everything
since (`0b0808bc`): the changes in between were proven behaviour-identical for GT (7.221, RNG-exact; 7.226 removals;
7.228 additions), so the plan treats them as matched on behaviour and never compares working times across them.

| Stage | GT runs | Matched? | Gap |
|---|---|---|---|
| A | `mscr_ota5t`, `mscr_ota7t_w`, `mscr_ring3`, `mscr_vco_lin_c`: scratch, seed 0, 800, task registry | yes | - |
| A | `mscr_ldo1_rgcn`, `mscr_ldo2_rgcn`: 1,500 launches at -5 dB, 0 passes | **no** (target) | 2 new GT runs at -3 / -2.3 dB from start A (3.4) |
| B | 7.229: six `scratch` + six `fine_tune` on the `_b` tasks, seed 1, 800, temperature carried, task registry | yes, under 3.1 and 3.2 | LDO `fine_tune` parents were -5 dB models: 2 new GT B-F runs from the relaxed A models (3.4) |
| C | six `S` on the `_c` tasks, seed 2, 800, 41-slot registry, scratch recipe | yes | - |
| C | six `G` (2e-4, two updates, half-source rehearsal) | **no** (recipe) | the six **G2** arms of `artifacts/general-network-20261006/equal-recipe-C/` (scratch recipe, target-only, temperature carried, seed 2) = the matched reference, queued by the session "Task button and fine-tuning comparison plan" at 06:54 today (its record entry is pending and takes the next free number; "the folded-cascode session" below, because it then builds the folded cascode of section 6.3); G2-ota5t ran 06:54-07:05, about 2 h for all six |
| C | six frozen probes of the general model, 300 sampled launches, **on the B starts** | partly (B start, not C) | optional: six GT probes on the C starts, 1,800 (3.4) |
| C | arm O on `mscr_ota5t_c` (own-data offline model, scratch recipe) | yes | - |

GT's general model (`offline-network__c8c3531a0d78`, 20,000 updates on the 22-run pool of 17,124 evaluations) is a
historical reference, not this plan's GT model: the plan's common pool is the 18 archives of the six circuits (section 6),
and a GT model from exactly that pool would be needed for a fully matched C stage of GT (optional, section 10).

### 2.4 Qualification state of the 18 circuit/start combinations

A qualified baseline (A/B/C runbook, section 4) = the start plus 64 seeded random draws, no learning. Since 7.248 that is
two things on the page: the automatic one-launch **baseline** of a saved task (a retry button for tasks saved before
7.248) and **Calibration** (exactly 64 random designs, no reset simulations).

| Start | State | Launches to qualify |
|---|---|---|
| A: ota5t, ldo1, ldo2, ring3, vco_lin_c | calibrations of 2026-10-05/06 (`calibration__*`, 64 draws, 65-68 launches) | 0 |
| A: ota7t_w | one-launch baseline only (its B start was drawn from the run's 8 warm-ups) | 64 (Calibration, seed 0; answer "Not now" to the Scale proposal) |
| A copies: the 12 `graphgps_*` / `xatten_*` tasks | no baseline | 12 (one launch each through the page's retry); the measured start must equal the MScR A baseline's: that is the equivalence record the runbook asks for |
| B: the six `_b` tasks | no baseline, no calibration (7.229 ran without; the whole model file was used) | 390 = 6 x (1 + 64), seed 1 |
| C: the six `_c` tasks | qualified, 391 launches (7.233-7.235) | 0 |

Calibration data never enter training or replay. The B calibrations also let the trimmed model library speed the B runs
(7.154, 7.229 section 6).

### 2.5 Runtime and the prepared configurations

- Optimizer digest `0b0808bc` since `c317e18`, unchanged through HEAD `8b2d29e` (7.233-7.251 changed workbench code
  only). The 7.231 `repo/` copy is `c317e18`: it lacks the pretraining and rehearsal tools of `bee0bae`, which stage C
  needs. Each stage runs from one fresh `git archive` of HEAD taken when the stage is frozen; the digest check in the
  queue (`0b0808bc`) keeps every save point of the study mutually loadable.
- The twelve A configurations (`artifacts/local/reviews/encoder-libraries-2026-10-06/configs/<library>_<circuit>.json`):
  scratch, seed 0, 800 launches, the A run's lanes and reward, the encoder's preset network, `spec_registry` empty (the
  task's own), `reset_temperature` false. Validated today at HEAD: no error; the warnings are the A tasks' own (three
  `unused_measurement` on each LDO, six `equation_unit_unchecked` on the VCO).
- `make_configs.py` writes only stage A. Stages B and C need their generators, written like 7.229's and 7.233's (sections
  5 and 6), in the same folder.

### 2.6 The learned temperatures of GT's A models (why section 3.2 is a real choice)

SAC tunes the entropy temperature during a run (`alpha_learning_rate` empty = the learning rate, target entropy 1 per
action), so an A model's last save point carries a temperature other than the 0.01 it started with:

| A model | ota5t | ota7t_w | ldo1 (-5 dB) | ldo2 (-5 dB) | ring3 | vco_lin_c |
|---|---|---|---|---|---|---|
| alpha at the last save point | 0.0070 | 0.0036 | 0.0038 | 0.0013 | 0.0131 | 0.0030 |

Read from `training_state.pt` of each final save point. The runbook's `reset_temperature = true` would start every
loaded arm at 0.01 instead; 7.229's fine-tune arms, the C G arms, arm O and the G2 arms all carried the learned value.

## 3. The decisions of this revision

### 3.1 Registry: the task's own in A and B, the shared 41-slot registry in C

The A/B/C runbook asks for the shared registry in every stage. Here A and B use the task's own registry (as the 12
prepared configurations do and as all 18 recorded GT A/B runs did), and C uses the audited 41-slot list
`artifacts/general-network-20261006/training/spec_registry.json` in every C arm, probe and offline training (as GT's
C did). Why: the A and B models are never loaded in C (C loads only offline-trained models, which are trained under the
shared registry whatever registry their source archives ran under: the pretraining tool re-contexts the recorded
metrics, the general plan section 3), so nothing is lost; and GT's A and B runs stay matched references, which under
the runbook's rule would need 14,400 new GT launches. Within a stage every encoder uses the same registry, so no
comparison mixes registry kinds. A model saved in A loads on the B task of its circuit (same rows and Scales; 7.227's
compatibility check proves each pair offline before the run).

### 3.2 Temperature: carried, as in every recorded loaded run

Loaded arms (B fine-tune, C general, C own) keep the loaded model's temperature (`reset_temperature` false). Why: the
twelve B runs, the six G, arm O and the six G2 arms of GT all carried it; resetting would unmatch all of them (another
9,600 GT launches to redo B-F and G). The measured values (2.6) are within one order of magnitude of 0.01 and SAC
re-tunes alpha from the first updates on, so the two policies differ at the start of a run, not for long. The
runbook's reset is kept as a labelled option: one pair (`B-F-reset` on ota5t, 800 launches) would show the size of the
difference if the user wants it measured.

### 3.3 Stage B and C arms run on the shared MScR `_b` and `_c` tasks

No B or C copies in the `graphgps` / `xatten` libraries. The runbook allows "the frozen B/C task or an explicitly
equivalent owned copy"; the frozen task itself needs no equivalence proof, no cells, no baselines (the C ones are
qualified, the B ones are qualified once for everyone), and every arm of a circuit then lists under one task in the
Tasks window and the Training tab's Compare... The run's encoder is recorded in its configuration and manifest; the
output folders name it (`graphgps-<circuit>-b-<arm>__*`). Alternative, if the user wants the VM libraries to hold
everything of an encoder: 12 more cells and tasks per library through `build.py --lib` and `save_tasks.py`, each with its
one-launch baseline and a recorded equivalence to the MScR task (24 cells, 24 launches, about an hour of build and
checks); this plan does not assume it.

### 3.4 GT's missing matched references (4 runs, 3,200 launches)

1. **A on the LDOs at the relaxed targets**: two new MScR tasks with start A and the B/C rows: `mscr_ldo1_rgcn_a`
   (HF PSRR <= -3 dB) and `mscr_ldo2_rgcn_a` (<= -2.3 dB), everything else the A task's. Made on the page: load the
   A task, set the HF PSRR row's limit, **Save as** with the name (7.246 makes the renamed DUT and testbench copies and
   registers the task at revision 1; its one-launch baseline follows by itself, 7.248); or, for a definition of record,
   `tasks_def.py` + `build.py` + `save_tasks.py` as the `_b` tasks were made. Then one GT scratch run each, seed 0, 800
   launches, 4 / 1 lanes: 1,600 launches. These are the A references for the new encoders' LDO runs; the -5 dB runs
   stay as history (and their archives, relabelled, stay in the C pool as before).
2. **B fine-tune on the LDOs from those models**: `mscr_ldo1_rgcn_b` / `mscr_ldo2_rgcn_b`, seed 1, 800, parent = the
   `_a` run's last save point: 1,600 launches. 7.229's LDO fine-tune rows (parents trained at -5 dB) remain as the
   historical result; the new pair is the matched one.
3. Optional: six GT frozen probes on the C starts (1,800), so that probes of every encoder start from the same design.
   The probes have no criterion, so this is for the descriptive table only.

Not needed: GT's G2 arms are running; GT's C-S and O exist.

### 3.5 Stage gates and queue order

A for both new encoders (alternating per circuit as `queue.sh` does: ota5t GPS, ota5t XAtten, ota7t_w GPS, ...), then
the GT `_a` runs, then the user's verdict on A per encoder. B only for encoders that learned on at least the four
circuits GT learned (A1 below): a B stage is a question about the A model, and there is no question about a model that
did not learn. C after B's verdict. Within B and C the scratch and loaded arms of a circuit alternate as in 7.229 and
7.239. One run at a time on the one Virtuoso session; the queue waits while the G2 arms, a peer run or a Save task
holds it.

### 3.6 Scope of encoders

Primary: `graph_gps` (rwse) and `group_cross_attention`. Optional, same protocol: `rgcn` and `gatv2` at their
starting presets (7.209 ran them on `mscr_ota7t`: different task, old reward; no matched run on the six), and
`graph_gps` with `structural_encoding: none` as the structural-input ablation. Each optional encoder costs the full
26,600 per pilot and, if the user wants libraries per encoder as in 7.231, six more cells and tasks.

### 3.7 Seeds

One seed per stage (0 / 1 / 2) is a pilot, as GT's was. Repetitions, if wanted after the pilot: A/B/C seeds (10, 11, 12)
and (20, 21, 22), offline seeds 10 / 20, the same physical starts, paired across encoders (the runbook, section 8).

## 4. Stage A: six scratch runs per encoder

**Before the runs (qualification, 76 launches, about 20 min):**

1. The twelve copies' one-launch baselines through the page (choose the task, the baseline retry of 7.248): the start's
   measured metrics must equal those of the MScR A task's baseline (the same deck on the same simulator; a difference
   beyond Spectre's own repeatability means the copy is not the circuit and stops that task). Recorded as the equivalence
   mapping copy -> A task.
2. Calibration of `mscr_ota7t_w` (64 random designs, seed 0): A-start qualification. The "Calibration ready" line's
   Scale proposal is answered **Not now**: the task stays as frozen.

**The runs:** the twelve prepared configurations as they are, from a fresh HEAD archive (2.5): per circuit the
GraphGPS run on `graphgps_<circuit>` then the cross-attention run on `xatten_<circuit>`; seed 0, 800 launches, the A
run's lanes and reward, the preset network; `research.comparison_pair_id = encoder-<circuit>`,
`method_label = <encoder>_scratch`. Output `/mnt/d/gator/outputs/<library>-<circuit>__*/runs/<library>_<circuit>/`,
so the page lists them under their task (the newest run follows the task choice, 7.212) and the Training tab can put
them beside GT's A run (Compare...). Check now before and after each run; the nonce-cache read before each
multi-lane run; the `queue.sh` of 7.231 does all of this, with `REPO` pointed at the fresh archive.

Then the two GT `_a` runs (3.4).

**Measures per run** (7.229's set, `compare.py`, no simulation): passing share of designs 9-108 (the first 100 own
proposals), cumulative passes by 100 / 200 / 400 / 800, "50 % by" and "75 % by" (the end of the first 100-design window
with that share), passing share of the last third (266 designs), mean reward early and late, valid share, per-row
failure shares, working time and learner update time (`update_seconds`), unique designs, best reward; the first passing
design as a footnote only (the user's ruling of 7.229). Plus, once per encoder: parameter counts, model contract.

**Criteria, per circuit, encoder E against GT's matched A run:**

- **A1 learns as well:** E's last-third passing share is not lower than GT's by more than 10 points.
- **A2 as fast:** E's "50 % by" is not later than GT's by more than 100 designs (both "never" counts as met for A2 and
  is said).
- **A3 LDOs:** E passes at all at the relaxed target (the GT `_a` runs say whether GT does).

Suite reading: "E keeps up with GT" when A1 holds on at least five of six and A2 on the four circuits GT learned;
"E learns" when A1 holds on the four circuits GT learned (the gate to stage B). Otherwise reported as measured, with
the per-circuit deltas first. One seed; an encoder ahead on one circuit and behind on another is a seed-spread
candidate for the repetition of 3.7, not a verdict.

**Budget:** 9,600 (both encoders) + 1,600 (GT LDO A) + 76 = **11,276 launches**, about 6 h at the recorded A-run
times (section 8).

## 5. Stage B: same circuit, start B, own model against fresh weights

**Qualification first (390 launches, about 25 min, once for every encoder):** on each `_b` task the one-launch
baseline (the retry button) and a Calibration of 64 random designs with Random seed 1; "Not now" to the proposals.

**Per encoder, twelve runs on the `_b` tasks, seed 1, 800 launches, the circuit's lanes:**

| Arm | Mode | Model | Settings |
|---|---|---|---|
| `B-S` | `scratch` | random weights | the A run's settings block (7.229's `make_configs.py` pattern), task registry |
| `B-F` | `fine_tune` | the encoder's own A model of the circuit, its final save point (`ckpt-00000800-*`), from the `graphgps_*` / `xatten_*` run | same settings; actor, critics, targets and temperature loaded (3.2); replay, optimizers and counters fresh; `freeze_encoder`, `encoder_only_transfer`, `reset_critic`, `reset_temperature` off; `rehearsal` none; `continual_learning` false; `--confirm-transfer` (another task's model) |

`research.comparison_pair_id = ftvs-<encoder>-<circuit>`, `method_label = <encoder>_fine_tune_on_start_b` /
`<encoder>_scratch_on_start_b`, `training_sources = [the A task]`. Each pair is proven compatible offline before the
queue (7.227's `compat_check.py`: identical spec schema, feature schema, model config, action version; the source
digest equal, so not even a warning). Outputs `outputs/<library>-<circuit>-b-<arm>__*/runs/mscr_<circuit>_b/`.

The GT references: 7.229's twelve runs, plus the two new LDO fine-tune runs of 3.4 (parents: the `_a` models).

**Criteria** (7.229 section 5, the runbook's C4 added), per circuit, B-F against B-S of the same encoder:

- **C1 transfers:** B-F's passing share of designs 9-108 at least 30 points above B-S's.
- **C2 ends as well:** B-F's last-third share not below B-S's by more than 5 points.
- **C3 LDOs:** B-F passes at the relaxed target.
- **C4 no deterioration:** B-F's last-third share at least its early share minus 10 points, and the failure share of
  its weakest row of the first 200 designs rises by no more than 15 points afterwards.

Verdict per encoder as 7.229's rule: "transfers on the same circuit" when C1 and C2 hold on at least five of six;
"transfers but training on loses it" when C1 holds on five and C2 fails on two or more; "no transfer" otherwise; always
with the gains measured (7.229's GT verdict was "no transfer" by the bar while the loaded model led early on all six).
Then the cross-encoder table: per circuit, the early share and last-third share of B-S and B-F for GT, GraphGPS and
XAtten side by side, and the differences E minus GT.

**Budget per encoder:** 9,600; GT gap 1,600; qualification 390. Time per encoder about 4.5-5.5 h (7.229: 5 h 05 min).

## 6. Stage C: one general model per encoder, start C

**6.1 The common pool (no simulation).** For every encoder the same 18 archives of the six circuits: GT's six A runs
(`mscr_ota5t`, `mscr_ota7t_w`, `mscr_ring3`, `mscr_vco_lin_c`, `mscr_ldo1_rgcn`, `mscr_ldo2_rgcn`) and twelve B runs
(7.229), 15,800 recorded evaluations (6,200 A + 9,600 B); excluded: `mscr_vco_lin`, `mscr_ldo2_rgcn_gt` (both),
`mscr_ldo_basic`, every C run, every baseline, probe and OTA8m run. A pretrain request like
`artifacts/general-network-20261006/training/request.json` with those 18 `run_dir` + `archive_sha256` entries, the same
`reference_overrides` (the eight settled references), the same `relabel_upper` for the two -5 dB LDO A archives, seed 0,
`holdout_fraction` 0.1, 20,000 updates, batch 8, checkpoints every 1,000, and the encoder's model block
(`encoder_type`, 48 / 4 / 4, `structural_encoding`). The split and the sampling depend on the seed and the pool, not on
the model, so every encoder trains on the identical split. `pretrain --audit-only` first (archive hashes, the reward
reproduction gate, the counts of training-eligible transitions); then training (about 1 h of CPU per model at GT's
step time; GraphGPS about 15 % more); then the offline checks of the general plan section 4 (held-out critic error per
task against the constant and the specialist, actor proposals inside the ranges, the forgetting curve) and publication
through the existing path (`offline_publish`), one run-shaped folder per model. The first non-GT model block through
`pretrain.py` is a first: `ModelConfig(**request['model'])` accepts `encoder_type` and `structural_encoding`, and the
audit-only pass plus one 1,000-update dry run on the pool prove it before the real training.

The **own-data OTA5t model** of each encoder: the same tool on GT's three ota5t archives (its A run and two B runs,
2,400 evaluations), as arm O's parent was made.

The end-to-end variant (an encoder's general model from its **own** 18 A/B archives, 14,400 evaluations at the fixed
budgets) is the runbook's `C-own-data`: optional, reported apart, never pooled into the common-data table.

**6.2 The runs, per encoder, on the `_c` tasks, seed 2, the circuit's lanes, `spec_registry` = the 41-slot list:**

| Arm | Mode | Model | Launches | Settings |
|---|---|---|---|---|
| `C-probe` | `frozen`, sampled actions | the encoder's general model | 300 x 6 | zero updates; the 300 include the periodic start checks; report proposals, resets, duplicates |
| `C-S` | `scratch` | random weights | 800 x 6 | the scratch recipe (section 2.1 settings) |
| `C-G` | `fine_tune` | the general model, the published 20,000-update checkpoint, the same for all six | 800 x 6 | the scratch recipe, target-only batches, no rehearsal, temperature carried = the G2 recipe |
| `C-O` | `fine_tune` | the own-data ota5t model | 800 x 1 (ota5t) | as C-G |

Never the adapted model of one circuit into the next; never C observations into the pool. GT references: C-S (exists),
G2 (running), O (exists); the GT probes of record are on the B starts (3.4 for the C-start option).

**Criteria** (the general plan section 5): C1-C4 as in stage B, G against S; C5 on ota5t: O's early share within 10
points of the encoder's own B fine-tune early share on ota5t (the live own-model reference measured in stage B), and
G's within 10 points of O's. Verdict per encoder: "one general network transfers to a new start" when C1 holds on at
least four of six, C2 on six and C4 on at least five; otherwise as measured. The cross-encoder table as in stage B,
with GT's G2 as its loaded arm.

**Budget per encoder:** 1,800 + 9,600 + 800 = 12,200 launches, about 6-7 h; offline training 2 models, about 2 h CPU.

### 6.3 Stage D: the held-out circuit is the folded cascode only (revision 2)

Each encoder's general model is tested on **one circuit it never saw: the folded-cascode OTA `mscr_otafc`** that the
folded-cascode session (section 2.3) is building as the real held-out circuit (NMOS input pair, PMOS fold, NMOS cascode mirror load, bias network
inside, 19 MOS; the six OTA metrics on the 1 V follower bench, Scale 6 on the dB rows; targets fixed by the
baseline-only rule from its own 64 random draws, before any policy sees it). **OTA8m does not count** as held-out: it is
OTA7t with a series resistor in the Miller path (the same eight MOS, so a model trained on OTA7t has seen the amplifier;
record 7.241 says it cannot establish unseen-family transfer), its results already fixed the recipe this plan uses (the
G2 recipe comes from its follow-up, 7.243), and that session deletes its task and renames the cells `mscr_ota7t_rz`.
Its archives stay out of every pool, as before; no arm of this plan runs on it.

Per encoder, on the registered `mscr_otafc` task with its qualified baseline (65 launches, made once by that session), seed 0,
four lanes as that session's runs, `spec_registry` = the 41-slot list (the six metrics are in it; the general model is bound
to it):

| Arm | Mode | Model | Launches | Settings |
|---|---|---|---|---|
| `D-probe` | `frozen`, sampled | the encoder's common-data general model of 6.1 | 300 | zero updates |
| `D-S` | `scratch` | random weights | 800 | the scratch recipe |
| `D-G` | `fine_tune` | the same general checkpoint as C-G | 800 | the G2 recipe: scratch recipe, target-only, temperature carried |

Criteria C1, C2 and C4 as OTA8m's phase 3 (G against S; the probe reported, no bar); GT's reference = that session's own
probe / scratch / general runs on the same task. Conditions that hold by construction and must stay true: the folded
cascode is absent from the 18-archive pool and from every own-data variant; its targets are frozen before any encoder's
model is evaluated on it; no stage-D result changes a model, a recipe or a target. What "held-out" means here: an
unseen circuit, bench and metric set, not an unseen building block: LDO2's error amplifier in the pool is itself a
folded cascode (the circuit tooling's own note), so the typed-graph comparison of `mscr_otafc` against the archived
LDO2 graph and the fourteen others is recorded with the verdict, as 7.240 did for OTA8m. One circuit at one seed is a
pilot of generalization.

Stage D needs only the offline general model of 6.1, not stage C's runs, so it can run right after the offline step; the
queue puts it after that session's own runs on the task, so the GT reference exists first. **Cost per encoder: 1,900 launches**
(300 + 800 + 800), about 1.5 h at four lanes (OTA8m's phase 3: 1,965 launches in about 1.5 h).

## 7. Measures and reporting rules

The runbook's section 8 applies as written except where sections 3-6 above say otherwise (registry, temperature,
probe start of GT). In short: the same `compare.py` for every arm, exact fractions, failures kept in the denominators,
charged launches and committed evaluations both reported, incomplete budgets never labelled as paired comparisons,
operational faults apart. Every result page shows the per-circuit deltas first and the suite verdicts second, and names
the seed count. The three-encoder tables (GT, GraphGPS, XAtten per circuit per measure) are the deliverable of each
stage; `results.md` / `results.json` in the stage's folder, the charts on a private page as 7.229's.

## 8. Budget and time

Launches:

| Work | GraphGPS | XAtten | GT gaps | Qualification | Total |
|---|---|---|---|---|---|
| Stage A | 4,800 | 4,800 | 1,600 | 76 | **11,276** |
| Stage B | 9,600 | 9,600 | 1,600 | 390 | **21,190** |
| Stage C | 12,200 | 12,200 | 0 (+1,800 optional probes) | 0 | **24,400** |
| Stage D, held-out folded cascode | 1,900 | 1,900 | 0 (the folded-cascode session's runs) | 0 (its baseline) | **3,800** |
| **Pilot, both encoders** | 28,500 | 28,500 | 3,200 | 466 | **60,666** |

Not in the table: the six G2 arms (4,800, the folded-cascode session, running), the B-F-reset option (800),
the optional GT probes (1,800), the GT general model from the 18-archive pool (0 launches, about 1 h CPU; it would make
GT's C-G reference pool-matched as well: today G2 loads the 22-run model), the `C-own-data` variant (12,200 per
encoder), repetitions (28,500 per encoder per seed triple), optional encoders (28,500 each).

Time, from the recorded GT working times per 800 launches (A runs before the 7.221 speed-ups / B and C runs after):
ota5t 12 / 8-10 min, ring3 14 / 9-12, ldo1 15 / 9-12, ota7t_w 37 / 22-30, ldo2 38 / 26-32, vco_lin_c 47 / 35-36. A six-run
set is about 2-2.7 h; the new encoders' learner steps are within -20 % / +14 % of GT's (2.1), and the single-lane runs
are simulator-bound, so the same figures hold for them within a few minutes per run.

| Stage | Simulation time | Of which the user's wait before the next decision |
|---|---|---|
| A (12 + 2 GT runs, qualification) | about 6 h | one evening |
| B (24 + 2 GT runs, qualification) | about 10-11 h | overnight |
| C (12 probes + 26 runs, 4 offline models) | about 13-14 h, plus about 4 h CPU before the first C launch | one day |
| D (2 probes + 4 runs on the folded cascode) | about 3 h | an evening, after the offline models and the folded-cascode session's runs |

Virtuoso is busy for a few hours today with the folded-cascode session's work (the G2 arms, then the folded-cascode cell `mscr_otafc`,
its task and baseline); a peer CLI run or a Save task also holds it (7.207), and the queue waits.

## 9. Procedure

1. **Freeze stage A** (free): a fresh `git archive` of HEAD into the stage folder, digest check `0b0808bc`; the
   manifest (protocol version, the six task IDs and the twelve copies, task hashes, A vector, seeds, lanes, budgets,
   measures, queue order); the equivalence record after step 2.
2. **Qualification A** (76 launches): the twelve one-launch baselines, the ota7t_w Calibration. Compare the twelve
   starts' metrics with the MScR baselines; write `equivalence.json`.
3. **Queue A** (`queue.sh` of 7.231 with `REPO` = the fresh archive; 12 runs; `queue.log`), then the two `_a` tasks and
   their GT runs (3.4). After each run: Check now (the cell equals its task), the run's own audit lines (initial sizes,
   actual update count, restoration).
4. **Compare A**: `compare.py` extended to the A measures and criteria; `results.md`; the record entry and the private
   page; the user's go for B per encoder.
5. **Freeze and run B**: `make_configs_b.py` (12 configurations per encoder + the 2 GT), `compat.json` for every
   fine-tune pair, qualification of the `_b` tasks (390), the queue in alternating order; compare; record; go for C.
6. **Freeze C offline** (CPU): the 18-archive request, `pretrain --audit-only`, the dry run, the two trainings per
   encoder, the offline checks, publication; `C` configurations (probe / S / G / O) with the 41-slot registry;
   compatibility of every loaded arm against its C task proven before a lane opens.
7. **Queue C**: per circuit probe, S, G (and O on ota5t); audits as the general-network experiment did (initial
   parameters, parent weights, target-only replay, update counts, frozen-tensor invariance, costs, restoration).
   Then **D** on `mscr_otafc`: probe, S and G per encoder, after the folded-cascode session's own three runs on it, with the same
   audits and the typed-graph comparison of 6.3 recorded first.
8. **Audit and deliver**: the three-encoder tables, the verdicts bounded by one seed, the budget actually spent against
   this worksheet, the record.

Existing entry points: `gator_workbench.cli validate`, `run` (with `--authorize-real`, `--allow-root
/mnt/d/gator/outputs`, `--confirm-transfer` for a loaded model of another task), `pretrain [--audit-only]`; the 7.231
and 7.227 queues; `compare.py` of 7.227 and 7.233; `daemon_check.py` (nonce cache); `check_tasks.py` in
`~/mscr_circuits` (Check now without simulation). None of this changes `src/analog_optimizer/`.

## 10. Decisions for the user

1. **Registry (3.1):** the task's own in A/B and the shared list in C, as GT ran (recommended) / the shared list in every
   stage as the runbook says (+14,400 GT launches to re-run its A and B).
2. **Temperature (3.2):** carried, as every recorded loaded run (recommended) / reset to 0.01 (+9,600 GT launches to
   re-run B-F and G) / carried plus the one `B-F-reset` pair on ota5t (+800).
3. **Where B and C run (3.3):** on the shared `_b` / `_c` tasks (recommended) / copies in `graphgps` and `xatten` (+24
   cells and tasks, +24 launches, about an hour of build).
4. **GT's LDO references (3.4):** the two `_a` tasks and four GT runs (recommended, 3,200) / compare the new encoders'
   LDO A runs with GT's B-stage scratch runs only (0, not matched: start B, seed 1).
5. **Start stage A now** (11,276 launches, about 6 h, after the G2 arms): yes / only the non-LDO circuits first (8 runs,
   6,400) / not now.
6. **GT probes on the C starts** (1,800) and **a GT general model from the 18-archive pool** (0 launches, 1 h CPU):
   yes / no. Recommended: the model yes (it makes GT's C-G loaded arm pool-matched), the probes no.
7. **Optional encoders (3.6):** RGCN, GATv2, GraphGPS without structural inputs: none now (recommended) / which.
8. **Repetitions (3.7):** after the pilot.
9. **Stage D on the folded cascode (6.3):** yes, 1,900 per encoder (recommended) / no. OTA8m is not an option.

Parked, as every further plan must say: the SKY130 benchmark (AnalogGym-Opt import, calibration with zero passes, the
tunable bias current) stays untouched; the MScR circuits on Spectre are the test bed.

## 11. What goes on record

This plan; record 7.256; a line in `docs/decisions.md` for choices 1-3 once made; per stage the configurations,
`compat.json`, `equivalence.json`, `queue.log`, `results.md` / `results.json` and the record entry with the tables; the
`_a` tasks' definitions in `~/mscr_circuits` if made there; the offline models' `pretraining` blocks. Nothing in
`src/analog_optimizer/` changes.
