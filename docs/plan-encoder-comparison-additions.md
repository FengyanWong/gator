# Encoder comparison, additions of 2026-10-09 (draft for the user's agreement)

Three additions to [plan-encoder-comparison.md](plan-encoder-comparison.md) (record 7.256, run as its section 12 on 2026-10-07 to
2026-10-09, records 7.273, 7.277, 7.285, 7.288, 7.289). Status at writing (18:40 on 2026-10-09):

| Part | What | Status |
|---|---|---|
| 1 | ~~The GCN arm~~ - **not part of the plan** (user, 18:5x: "dont add rgcns to the plan"); the arm was prepared and stopped before its first run (18:36); its library, six tasks, configurations and chain script stay as tooling, unused |
| 1b | The four AgenticSizing circuits (arXiv 2609.25873) as new tasks, the paper's specs unchanged, then the previous stages' runs on them | **proposed; blocked on source material and two decisions** (section 1b) |
| 2 | Stage R: reward steering by the Objective row, under each trained network | **proposed**; starts only on the user's word |
| 3 | Browse folders for the Tasks, Runs and RL-model windows, by stage | **done** (`categorize.py`) |

After agreement, parts 1b and 2 join the main plan as its section 13; part 3 is a workbench fact, recorded with the next record.

## 1. The GCN arm (not in the plan; kept as tooling)

**What "GCN" is here.** The optimizer has five encoders: `graph_transformer`, `gatv2`, `graph_gps`, `group_cross_attention` and
`rgcn`. The GCN-family encoder is `rgcn` (relational GCN: `RGCNConv` with GATOR's edge types, mean aggregation), the one
non-attention encoder; there is no plain GCN, and adding one would change the optimizer digest. Its starting preset is the published
size of the one R-GCN sizing agent (li2023rgcn): 32 wide, 4 layers, no heads, no structural inputs; its training numbers are the
SAC set every preset shares (lr 1e-3, 8 updates, alpha 0.01, gamma 0, batch 8, warm-up 8, replay 10,000, episode 4), so a GCN run
differs from its reference only in the network block, as the GraphGPS and cross-attention runs did.

**Tasks.** A third Virtuoso library `gcn` beside `graphgps` and `xatten`, built with the same tooling (`~/mscr_circuits/build.py
--lib=gcn`: 6 circuits + 6 benches, 24 schematic checks with 0 errors) and registered as `real:gcn_<circuit>` for ota5t, ota7t_w,
ring3, vco_lin_c, ldo1, ldo2 with the A tasks' rows, Scale 6 on dB rows and the LDOs' HF PSRR row relaxed to <= -3 / -2.3 dB
exactly as the other two libraries (`save_tasks.py`; one-launch baselines automatic). The stage C and D tasks are shared
(`mscr_*_c`, `mscr_otafc`, `mscr_otatc`).

**Runs** (the night's mechanics: `queue_cd.sh` on the frozen runtime `~/gator-runtime-7256`, HEAD 6016bbd, digest 0b0808bc; Check
now before and after every run; a copy of the live settings; output in `/mnt/d/gator/outputs`):

| Stage | Runs | Settings | Reference |
|---|---|---|---|
| A | 6 scratch, `gcn-<circuit>` | seed 0, 800 launches, the A run's lanes and page reward; network = the rgcn preset (`make_configs_gcn.py`, `jobs-GA.txt`) | the GT A runs of record; GraphGPS and cross-attention A runs |
| offline | 1 general model | the 18 GT archives (6 A + 12 B, 15,800 evaluations), the pinned 41-slot registry, 20,000 updates, seed 0 (`offline/request2-general-rgcn.json`) | the three published general models; the offline indicator (held-out critic MSE) |
| C | 12: S and G on the six `_c` tasks, `gcn-<circuit>-c-{s,g}` | seed 2, 800 launches, G = fine_tune from the rgcn general model with the G2 recipe (`make_configs_cd.py`, ENCODERS_ONLY=rgcn) | GT 7.239 S / 7.262 G2; the other encoders' C arms |
| D | 4: S and G on the held-out cascodes, `gcn-ota{f,t}c-d-{s,g}` | seed 0, 4 lanes, the 7.262 final goals | GT 7.262; the other encoders' D arms |

No stage E for GCN: the GT LDO references at the relaxed targets exist (7.289), and the GCN LDO runs compare with them and with the
other encoders at the same rows. Chain: `stage_gcn.sh` (log `stage_gcn.log`); publication and compatibility by `publish_gcn.py`
(`models.json` key `rgcn`, `compat-gcn.json`, marker `GCN-CD.ready`); tables by `compare_runs.py` (`rgcn` admitted in every table).

**Criteria, unchanged:** A1 (last third within 10 points of GT), A2 (50 % point not later than GT + 100), A3 (LDO passes at the
relaxed target); C1-C4 and the suite rule; the D goals. The pre-registered rules of section 12 apply as written (the OTA5t stop rule;
the second seed; the GraphGPS ablation is GraphGPS-specific; the GT LDO references are done).

**Expectation, written before any result:** the simplest encoder keeps up on the OTAs and the VCO (A1 within 10 points) and falls
behind on RING3 and the folded cascode from scratch, where the attention encoders differed most; if it keeps up everywhere, the
study's reading becomes "attention is not what these circuits reward".

**Cost.** 22 runs = 17,600 launches + 6 baselines. Time at the VM's restored P-core speed: A about 2.7 h (12 + 30 + 15 + 43 + 12 +
47 min), offline training about 1 h, C about 5.3 h, D about 1.2 h: about 10 h, so done around 05:00 on 2026-10-10 if nothing waits.

## 1b. The AgenticSizing circuits (proposed)

**User (18:5x on 2026-10-09):** "add the four agentic sizing circuits and queue the runs of the previous stages without spec change
... add to the tasks and give a folder called agenticsizing".

**The circuits** (AgenticSizing, arXiv 2609.25873, Hao et al., Edinburgh; counts from its Table III, specs from Tables V-VIII, the
paper's units):

| Circuit | Source cited by the paper | Transistors | Variables | Spec rows (the paper's limits) |
|---|---|---|---|---|
| Bandgap reference (BGR) | Ueno et al. 2009, subthreshold CMOS voltage reference | 25 | 26 | power <= 1 uW; Vref in [0.5, 1.3] V; PSR <= -40 dB; TC <= 25 ppm/degC |
| Two-stage folded-cascode amplifier (FC) | Budak et al. 2022 | 29 | 29 | power <= 1 mW; CMRR >= 100 dB; gain >= 90 dB; PSRR >= 100 dB; output swing >= 2.4 V; PM >= 60 deg; noise <= 335 uV; rise time <= 30 ns; slew (printed as <= -0.3 V); UGB >= 30 MHz; CM phase margin >= 50 deg |
| LDO | Leung and Mok 2003, capacitor-free LDO with damping-factor control | 20 | 26 | power <= 100 uW; Vout in [1.15, 1.25] V; load regulation <= 0.2 V/A; line regulation <= 0.2 V/V; PSRR >= 50 dB |
| Full system: LDO + BGR + FC error amplifier | the authors' own composition | 55 | 60 | power <= 700 uW; Vout in [1.15, 1.25] V; load regulation <= 0.2 V/A; line regulation <= 0.2 V/V; TC <= 40 ppm/degC; PSRR >= 50 dB |

**What exists, and what does not.** Nothing of these circuits exists in this project (no cell, netlist or task). The paper's code
repository (github.com/aprilaihub/agentic-analog-sizing, Apache 2.0) holds the agent framework and one 5T-OTA case; it names no
PDK, distributes no technology data, and has no netlist, schematic or spec file for the four circuits. The paper names Cadence Spectre
but neither the technology node nor the supply. So "add to the tasks" means building four circuits (one of 55 transistors) in
Virtuoso by hand from the cited papers, with testbenches, probes and the paper's spec rows, as the MScR library was built - days
of work, not a queue action - unless the netlists can be obtained from the authors (the same university).

**Two decisions needed before a build.**

1. **Supply and devices.** The paper's limits assume a supply well above GPDK045's 1.1 V core devices: an output swing >= 2.4 V, a
   reference of 0.5-1.3 V, an LDO output of 1.15-1.25 V (the input must be higher). "Without spec change" therefore means the
   thick-oxide devices of gpdk045 at a 2.5 V supply (if the PDK provides them, see the check in the record), or another PDK; the
   1.1 V devices would force spec changes.
2. **Measurements the workbench has not run yet.** TC (ppm/degC) needs a temperature sweep; load and line regulation need DC sweeps of
   load current and supply; rise time and slew need a transient step; CMRR/PSRR/CM phase margin need their own AC testbench
   configurations. Each is expressible in Maestro and as Probes rows, but each is new to GATOR's tasks and must be verified against
   the paper's definitions (the printed "slew <= -0.3 V" needs reading in the full text).

**Runs once the tasks exist** ("the runs of the previous stages"): per circuit the GT A-style scratch run (seed 0, 800 launches, the
page's reward, lanes by run time), the two new encoders' scratch runs, and the general-model arms (fine_tune from each published
general model, G2 recipe, pinned registry) as held-out circuits like stage D; no spec relaxation (A3-style passes counted at the
paper's limits). 4 circuits x (3 scratch + 3 general) = 24 runs, about 19,200 launches; the 55-transistor system's run time is
unknown (a 60-variable action space, long transient benches).

**Folder.** `agenticsizing` exists in the Tasks, Runs and RL-model windows (empty until the tasks exist); `categorize.py` puts tasks
`agentic_<circuit>` and runs `agentic-<circuit>*` there.

**Next step, the user's:** (a) ask the authors for the Spectre netlists and their PDK, or confirm a hand build from the cited papers;
(b) decide the supply/device question; then the build order FC -> LDO -> BGR -> full system, each saved as a task with its baseline
before the next.

## 2. Stage R: reward steering under each trained network (proposed)

**Question.** Does a different reward setting still produce working designs while steering them toward a different requirement, and
does the answer depend on the network (encoder, and trained general model against scratch)?

**Mechanism, and why not the Soft weight.** The reward's penalty is the weighted average of the rows' misses (plus half the worst
miss); a design that passes every hard row has no misses, so weights cannot distinguish feasible designs. What steers them is the
**Objective** row (`direction_after_feasible`, at most one row): the objective bonus pays up to +1 for improving that row beyond its
limit, in units of its Scale, under the tested reward (objective bonus weight 1 compressed, margin bonus 1, worst share 0.5). Scale
is the second lever (the margin bonus goes to the row with least room in its Scale), kept optional here.

**Circuit and settings.** OTA5t, AC and DC only (12 min a run at P-core speed), 95 % of the reference run's last third passing, its
passing designs in a tight cluster (power 0.269-0.305 mW, median 0.3015; UGB 105-126 MHz, median 116.5; gain 30.35-31.4 dB). Two
settings, the six hard limits and Scales unchanged:

- **P**: `power_w` "lower is better" (limit <= 0.5 mW, Scale = the limit);
- **U**: `ugb_hz` "higher is better" (limit >= 100 MHz, Scale = the limit);
- optional **S**: no objective, Scale of `ugb_hz` set to 10 MHz (the margin bonus moves to that row).

Two tasks by Save as of `real:mscr_ota5t`, one Objective cell changed each: `mscr_ota5t_objp`, `mscr_ota5t_obju` (one pair for every
encoder: the encoder is a run setting, the separate libraries of stage A were for ownership, not necessity).

**Arms.** Per encoder E in {GT, GraphGPS, cross-attention, GCN}:

| Arm | Start | Seeds | Runs | Control (exists) |
|---|---|---|---|---|
| E-P, E-U scratch | random weights, the A run's settings + the Objective row | 0 and 1 | 4 x 2 x 2 = 16 | the encoder's A run on OTA5t (no objective) |
| E-P, E-U general | fine_tune from E's published general model, the G2 recipe, pinned registry | 0 | 4 x 2 = 8 | the encoder's C arm on `mscr_ota5t_c`, no objective (start C differs: a control run on the new tasks without objective would be cleaner: +4 runs, decide) |

**Read-out.** From the recorded tables, per run: the last-third passing designs' quartiles of `power_w` and `ugb_hz`, pass rate,
50 % point, per-row pass rates, the kept best design; one figure per encoder: power against UGB of the last-third passing designs,
control grey, P and U in two colours. Script in the style of `compare_runs.py`.

**Criteria, pre-registered.**

1. **R1 still works**: each arm's last-third pass rate within 10 points of its control's, and its 50 % point not later than the
   control's + 100.
2. **R2 steers**: among the last third's passing designs, the median of the targeted spec lies beyond anything the control produced
   (P: power median below the control's minimum; U: UGB median above the control's maximum), each arm beats the other on its own spec,
   and both seeds agree in direction. The size is reported in Scale units, not thresholded.
3. **R3 no collateral**: every other row's pass rate within 10 points of the control's. Gain is the row expected to give (1 dB of room).
4. **R4 the kept design**: the best design each run keeps has lower power in P and higher UGB in U than the control's.
5. **Across networks**: "steering is network-independent" if every encoder passes R1-R3 in both settings, scratch and general; otherwise
   the exceptions are named, and the shift sizes are compared across encoders and between general and scratch (one seed for the general
   arms: reported, not judged).

**Cost.** 24 runs = 19,200 launches (+ 4 control runs on the new tasks = 3,200 if chosen; + 8 for the Scale arm), 2 baselines;
about 5 h at P-core speed (OTA5t 12 min a run), 6 h with the controls. The GCN general arm needs the GCN general model, so stage R runs
after part 1 or without GCN's general arm.

**Decisions for the user before the start:** (a) all four encoders, or GT + GraphGPS only; (b) the general-model arms yes or no;
(c) controls on the new tasks (+4) or the existing A runs; (d) the optional Scale arm; (e) seeds 0 and 1 for scratch (recommended) or
one; (f) run after the GCN arm (recommended) or interleaved.

## 3. Browse folders (done 18:30 on 2026-10-09)

`artifacts/local/reviews/encoder-comparison-2026-10-07/categorize.py` (idempotent; re-run when new runs appear) made the stage
folders of the three windows and assigned every task, run and saved model; the three encoder-named task folders of record 7.250
were removed once empty.

| Window | Folders |
|---|---|
| Tasks (8) | A: start-A circuits (MScR originals, the GT A runs) / A: GraphGPS library / A: cross-attention library / A: GCN library / B: start-B tasks (7.229) / C: start-C tasks (general model) / D: held-out cascodes / Other circuits |
| Runs (13) | Encoder A: scratch runs (GraphGPS, cross-attention, GCN) / Encoder A: the GT reference runs / Encoder C: general vs scratch on the start-C tasks / Encoder C: the GT reference arms (7.239 S, 7.262 G2) / Encoder D: held-out cascodes (new encoders) / Encoder D: the GT reference arms (7.262) / Encoder E: GT at the relaxed LDO targets / Encoder study: offline general models / Encoder study: qualification / General-network plan (7.229-7.262) / Fine-tune vs scratch on start B (7.229) / Earlier studies (SAC defaults, presets, first runs) / Baselines and calibration / ngspice and mock runs |
| RL models (11) | the run folders that hold saved models (the same names) |

Stores: `configs/local/workbench/{task,run,model}_folders.json`; a folder name is at most 60 characters.
