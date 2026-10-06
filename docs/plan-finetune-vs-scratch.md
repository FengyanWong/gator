# Plan: fine-tuning a trained model on a new starting point, against training from scratch (2026-10-06, record 7.227)

User: "Create new tasks for ... ldo1_rgcn and ldo2_rgcn, ota5t and ota7t_w, ring3 and vco_lin_c with a different starting
seed, different starting parameter. Load their run with their corresponding from scratch models and prepare run with
fine-tune model. Write a plan of comparing these fine-tuning runs with from scratch runs. It is possible to set the ldo
tasks with passable psrr target if necessary for the plan."

Status: the six new tasks are built, saved and checked; the twelve runs were started on 2026-10-06 06:58 on the user's
"All twelve" (`queue.sh`, one at a time); section 5's criteria were revised at 08:1x while they ran, before any verdict.

## 1. The question, in plain words

Each of the six circuits already has one trained model: the Graph Transformer starting preset trained from random weights
on the task's original starting design (call that **start A**, seed 0; the runs of records 7.216, 7.199 and the ota7t
width task). The question: when the same circuit is started from **another design (start B)** with another random seed,
does a model that already learned the circuit (loaded and trained on, Mode `fine_tune`) find passing designs sooner and
end better than a fresh model (Mode `scratch`) on exactly the same task, budget and settings?

What to expect, and why it is still worth measuring: the policy proposes **absolute** sizes (`decode_action` maps the
network's output onto each row's range; nothing is relative to the current design), so a policy that learned where the
passing designs are should propose them within its first launches at start B, whatever B is. Start B only changes what
the model sees at every episode reset (the design and its measured results), which is new to it. So the comparison
measures how much of a trained model's knowledge survives a new starting observation, and whether training on from there
keeps or loses it. For the two LDOs it also measures whether a model that never passed at the old target (-5 dB) helps
once the target is passable.

## 2. What exists: the A runs and the B tasks

| Circuit | A run (from scratch, seed 0) | Launches, lanes | First pass | Passing, last third | Model loaded by the fine-tune arm |
|---|---|---|---|---|---|
| ota5t | `starting-preset-mscr_ota5t__86f691dc269c` | 800, 4 | 74 | 252 / 266 (95 %) | `ckpt-00000800` |
| ota7t_w | `ota7t-width__efe47694b7ee` | 800, 1 | 5 (a random warm-up design) | 251 / 266 (94 %) | `ckpt-00000800` |
| ring3 | `starting-preset-mscr_ring3__d1b91e124afe` | 800, 4 | 46 | 40 / 266 (15 %) | `ckpt-00000800` |
| vco_lin_c | `starting-preset-mscr_vco_lin_c__95854a9fe1bc` | 800, 4 | 4 (the start passes) | 250 / 266 (94 %) | `ckpt-00000800` |
| ldo1_rgcn | `starting-preset-mscr_ldo1_rgcn__8b5df9644b56` | 800 + 200 + 500, 4 | none (0 of 1,500 at -5 dB) | 0 / 500 | `ckpt-00001500` |
| ldo2_rgcn | `starting-preset-mscr_ldo2_rgcn__c02fcb5c1553` | 800 + 200 + 500, 1 | none (0 of 1,500 at -5 dB) | 0 / 500 | `ckpt-00001500` |

All six: GT 48/4/4 starting preset (learning rate 1e-3, initial alpha 0.01, 8 updates per design, gamma 0, batch 8,
episode length 4, replay 10,000), the page's starting reward (compressed misses, worst-spec share 0.5, objective and
margin bonus weight 1), optimizer source `f83342bc` (the save points resume only under that source; fine-tune and frozen
load them under today's `4aebbfab`, with a warning - checkpoints.py).

**The B tasks** (`real:mscr_<name>_b`, cells `MScR/mscr_<name>_b` + `tb_<name>_b`, built and saved 2026-10-06 05:10-05:19,
revision 1; ota5t_b, ldo1_rgcn_b, ldo2_rgcn_b revision 2 with the Scales, section 3): the same circuit, rows, ranges and
analyses as the A task, in a cell of its own, sized to **a random design of record** - among the random designs the A
task's Baseline simulation simulated (ota7t_w: the 8 random warm-up designs of its run), the valid one with the median
reward of those that met not every row. A typical random start, chosen by a rule, not by hand (`~/mscr_circuits/
startb_designs.py`; the sizes are in `designs.py` as `OTA5T_B`, `OTA7T_W_B`, `LDO1_B`, `LDO2_B`, `RING3_B`, `VCO_C_B`).

| B task | Start B = design n of the random designs | Reward at the start (A start) | What it misses at the start |
|---|---|---|---|
| mscr_ota5t_b | 15 of 64 | -0.206 (A: -0.035) | UGB 45 MHz (>= 100) |
| mscr_ota7t_w_b | 7 of 8 | -0.351 | gain 251 V/V (>= 400), UGBW 19.5 MHz (>= 25), 1.9 mA (<= 1) |
| mscr_ring3_b | 3 of 64 | -0.414 | f 2.6 GHz (0.95-1.05), 342 uW (<= 150) |
| mscr_vco_lin_c_b | 35 of 64 | -0.157 (A start passes) | f3 806 MHz (1.215-1.485 GHz) |
| mscr_ldo1_rgcn_b | 15 of 64 | -0.425 | PM 119 deg fine; PSRR 1 MHz -6.9 dB (<= -20), HF +0.2 dB |
| mscr_ldo2_rgcn_b | 29 of 64 | -0.456 | load regulation 49 mV (<= 32), PSRR 1 MHz -6.2 dB, HF 0 dB |

Every cell was proven after the build: schCheck 0 / 0, every size read back equal to the design, Check now passed 6 / 6
steps (editors, task, connect, export, deck, Maestro) without a simulation, and the validation route accepts each task.

## 3. The two LDO targets, and the Scales

At `psrr_hf_db <= -5 dB` no working design of 1,500 ever passed on either LDO (records 7.216 and the follow-ups; best
-3.6 / -2.7 dB). The user allowed a passable target for the plan. From the recorded designs that met the other six rows:

| LDO | designs meeting the other six rows | <= -5 dB | <= -3 dB | <= -2.5 dB | <= -2.3 dB | <= -2 dB |
|---|---|---|---|---|---|---|
| ldo1_rgcn | 329 | 0 | 65 (20 %) | 190 | - | 275 |
| ldo2_rgcn | 282 | 0 | 0 | 11 (4 %) | 37 (13 %) | 82 (29 %) |

The B tasks ask `psrr_hf_db <= -3 dB` (LDO1) and `<= -2.3 dB` (LDO2): reached by about one recorded design in five
and in eight - passable, not easy. Every other row is unchanged. The A models were trained at -5 dB; if fine-tuning helps
at the relaxed target, it helps despite that.

Found by the compatibility check and fixed before any run: a model's spec registry takes each Specs row's **Scale** as the
metric's reference, and the A tasks of ota5t, ldo1_rgcn and ldo2_rgcn hold Scale 6 on their dB rows (record 7.187). Saved
without it, the three B tasks refused their A models ("goal/spec input schema"); revision 2 of each holds the same
Scales, and `compat_check.py` then reports every pair compatible for Mode fine_tune (the only remaining difference is the
optimizer source digest, a warning, as expected).

## 4. The twelve runs (nothing started)

Per circuit two runs on the B task, **seed 1** (the A runs used 0), **800 launches**, and otherwise exactly the A run's
settings (its `effective_config.json` run block: network, reward, SAC numbers, lanes - 4 for ota5t / ring3 / vco_lin_c /
ldo1_rgcn, 1 for ota7t_w / ldo2_rgcn, as the A runs had):

* **fine_tune** - Mode `fine_tune`, model = the A run's last save point. The actor, both critics, their targets and the
  temperature are loaded; the replay buffer, the optimizers and the counters start fresh (checkpoints.py; `freeze_encoder`,
  `encoder_only_transfer`, `reset_critic`, `reset_temperature` all off). `research.training_sources` names the A task,
  `comparison_pair_id = ftvs-<circuit>`, `method_label = fine_tune_on_start_b`.
* **scratch** - Mode `scratch`, random weights, `method_label = scratch_on_start_b`, the same pair id.

Files: `artifacts/local/reviews/finetune-vs-scratch-2026-10-06/configs/<circuit>__<arm>.json` (schema-validated;
`make_configs.py` rebuilds them from the live starters and the A runs' settings), `configs.json` (the summary),
`compat.json` (the compatibility answers). The runs land in `/mnt/d/gator/outputs/finetune-vs-scratch-<circuit>-<arm>__*/
runs/mscr_<circuit>_b/`, so the page lists them in Runs... and the Training tab can show them beside the A run (Compare...).

To prepare the same run on the page instead: choose `real:mscr_<circuit>_b` in Tasks..., Mode `fine_tune`, pick the A run's
model in the saved-model chooser (the network follows it), Random seed 1, Evaluation budget 800, the lanes above - the
configuration files hold exactly that.

## 5. What is measured, and the criteria (revised 2026-10-06, during the runs)

The first version of this section made "the first passing design" the main criterion. The user rejected it ("I dont think
first passing design is a good metric for showing transfer learning here") and the first two finished pairs showed why: it
is a single event, chance dominates it (every run's first 8 designs are random warm-ups whatever the mode; a lucky draw
ends the measure before transfer has shown), its seed spread is large, and on an easy start both arms pass early. On ota5t
it read 13 against 19, while the passing share right after the warm-ups read 90 % against 6 %. The runs record everything,
so the measures below come from the same tables; no run was changed.

Per run, from its recorded tables (`compare.py`, no simulation):
* **Passing share of designs 9 to 108** - the first 100 designs the policy itself proposes. A loaded model that knows the
  circuit passes from its first proposals; a fresh one passes almost none. This is the transfer measure.
* **Cumulative passes by 100 / 200 / 400 designs** - sample efficiency over the run.
* **"50 % by"** - the end of the first 100-design window with at least half passing: when the arm has learned.
* **Passing share of the last third** - where the arm ends (the fine-tune arm must not end worse).
* The mean reward early (designs 9-108) and late (last third), the valid share, the working time.
* The first passing design, as a footnote only.

Criteria, per circuit:
* **C1 (transfers):** the fine-tune arm's passing share of designs 9-108 is at least 30 points above the scratch arm's.
* **C2 (ends as well):** the fine-tune arm's last-third passing share is not lower than the scratch arm's by more than
  5 points.
* **C3 (LDOs only):** the fine-tune arm passes at all at the relaxed target.

Verdict rules: "fine-tuning transfers on the same circuit" if C1 and C2 hold on at least five of the six; "it transfers but
training on loses it" if C1 holds on five but C2 fails on two or more; "no transfer" otherwise. One seed per arm; the
"50 % by" figures and the cumulative passes are reported beside the verdict so a close call is visible.

Not measured by these runs, offered as options: a frozen run of each A model on its B task (50 designs, deterministic
policy, no learning) would separate pure zero-shot transfer from the first updates; a frozen run of each fine-tuned model
back on its A task would measure forgetting. 300 launches each.

## 6. Procedure

`queue.sh` (same folder), only on the user's word: for each circuit the fine-tune run, then the scratch run. Before each
run it waits until Virtuoso is free (no run holds the session lock, no Save task running), runs Check now on the B task
(the cell must equal the task; no simulation) and, for a multi-lane run, reads `RB_NONCE_CACHE_MAX` in the running
Virtuoso (`daemon_check.py`; >= 16384 needed, 32768 was applied on 2026-10-05 - it is 4,096 again after a Virtuoso
restart, and the queue then stops instead of applying it). Each run is a workbench CLI run from a clean copy of the
committed source with a copy of the live settings, written straight into `outputs/`; after each run Check now again. The
log is `queue.log`; `compare.py` writes `results.md` / `results.json` at any time.

Time, from the A runs' working times at the same lanes (per 800 launches): ota5t ~12 min, ring3 ~14, ldo1_rgcn ~16,
ota7t_w ~37, ldo2_rgcn ~38, vco_lin_c ~47 - about 2 h 45 min per arm, **about 5.5 h for all twelve**, one run at a time.
The B tasks have no recorded baseline, so their runs use the whole model file (the trimmed one needs a baseline, record
7.154): a little slower per simulation than the A runs, same results.

## 7. Decisions for the user

1. **Start the twelve runs** (9,600 Spectre launches, about 5.5 h): yes / only the four circuits that learned (ota5t,
   ota7t_w, ring3, vco_lin_c: 6,400 launches) / not now.
2. **A Baseline simulation of each B task first** (6 x 65 launches, about 25 min): records the reference and lets the
   trimmed model library speed the runs; optional, the runs do not need it.
3. **A second seed** (seed 2) of both arms on two circuits (+3,200 launches) if the first results are within the seed spread.
4. **The A LDO tasks at the relaxed target** (2 x 800 launches): a scratch run on start A at -3 / -2.3 dB would show whether
   the relaxed rows are learnable from A too; optional.

Parked, as every further plan must say: the SKY130 benchmark (AnalogGym-Opt import, calibration with zero passes, the
tunable bias current) stays untouched; the MScR circuits on Spectre are the test bed.

## 8. What goes on record

The twelve runs' facts in `results.md`, a record entry with the verdict by the rules above, a line in `docs/decisions.md`,
and the B tasks' definitions in `~/mscr_circuits` (`designs.py`, `tasks_def.py`, `startb_designs.py`). Nothing in
`src/analog_optimizer/` changes for any of this.
