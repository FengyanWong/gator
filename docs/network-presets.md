# Per-encoder network settings in the workbench

Added 2026-09-20. Code: `src/gator_workbench/network_presets.py`, panel `frontend/src/panels/Right.tsx`,
tests `tests/workbench/test_wb_network_presets.py`, browser check `frontend/scripts/network_panel_check.mjs`
(headless Edge, 41 checks; writes are intercepted, so it never changes your saved settings).
The initial preset implementation did not change `src/analog_optimizer/`. Since 2026-09-26, the optimizer and this panel offer only `graph_transformer`, `rgcn` and `gatv2`. GATv1 was replaced by GATv2 on that date; its historical preset settings are borrowed as starting values, not a published GATv2 sizing recipe. MLP/GCN were deleted on that date, and port-GNN on 2026-09-24. Their entries below retain historical preset provenance; they are no longer selectable or editable. Old configurations are rejected explicitly, and existing checkpoints require their matching historical source and dependencies.

## In plain words

Before, the panel had one set of numbers (hidden 32, heads 4, layers 2, batch 8, ...) no matter which
network you picked, and those numbers were typed into the web page rather than read from the backend.

Now the backend keeps **one setting per network type**:

* Picking a network in the drop-down **loads** that network's numbers from the backend.
* Changing a number (network sizes or anything under Advanced) **saves** it in the backend for that
  network only. It is still there after a restart.
* Each network starts from its **starting preset**: the network size (hidden / heads / layers) that
  **published analog-circuit papers actually used**, and **every training number of the runs that learned on
  GATOR circuits** on 2026-10-05 (record 7.192; the user: "merge the publication preset and overwrite those
  settings with the previous learned settings, keep this as the starting preset with no multiple choices", then
  "All training numbers"). The panel shows where every number comes from ("Where the ... values come from"); a
  replaced published number is named there.
* There is no choice between presets: the **GATOR baseline** (32 / 4 / 2 for every network) and the two buttons
  that chose between it and the publication preset were deleted on 2026-10-05 (record 7.191). To go back to a
  preset number, type it again: when all of a network's numbers equal its preset, the saved copy is forgotten and
  the window says **In use: starting preset**. A network that was on the GATOR baseline reads as its starting
  preset; the settings file is not rewritten.
* The **heads** box is greyed out with "ignored by this encoder" unless the network is
  `graph_transformer` or `gatv2`. Only those two have attention heads.

An existing configuration retains its explicit values on reload, even if the saved defaults differ. In the
**RL networks...** window, **In use: current run settings** and the **This run / Saved default** table identify that
case, including differences under Advanced. A new run uses the current values. **Use saved defaults** replaces the
configuration's network and Advanced values without writing preferences; **Save as defaults** keeps the current
values and remembers them for this encoder. A preset's name is shown as in use only when its saved values match.

**The one thing to keep in mind:** the papers ran thousands of simulations per run; GATOR's real runs
used tens to hundreds. A published batch size of 128 with 1,000 warm-up steps means that in a 60-evaluation run
the network never learns and every action is random - which is why the presets no longer take the papers'
training numbers. The network sizes are still the papers'; the runs that learned used 32 / 4 / 2, and each
published size learned as early with the same training values on ngspice, and all three presets on Spectre too
(records 7.199 and 7.209, "Measured" below). With the starting values learning began after about 150 to 600 evaluations. For comparing encoders at equal size, give every encoder the same sizes; an existing checkpoint
always loads with its own network.

## The presets

Since record 7.192 (2026-10-05) every starting preset has the published network size and the training numbers
of the runs that learned on GATOR circuits, the same for all three networks; since record 7.199 (the same day, the
user: "use learning rate 1e-3 in the starting preset") with learning rate 1e-3:

| Encoder | hidden | heads | layers | lr | gamma | tau | batch | warm-up | replay | episode |
|---|---|---|---|---|---|---|---|---|---|---|
| `graph_transformer` | 48 | 4 | 4 | 1e-3 | 0 | 0.005 | 8 | 8 | 10000 | 4 |
| `rgcn` | 32 | (4) | 4 | 1e-3 | 0 | 0.005 | 8 | 8 | 10000 | 4 |
| `gatv2` | 192 | 3 | 4 | 1e-3 | 0 | 0.005 | 8 | 8 | 10000 | 4 |

All three also start with `initial_alpha` 0.01, `updates_per_transition` 8, `update_every` 1,
`target_entropy_per_action` 1 and `max_grad_norm` 10. Of the training numbers, `initial_alpha`,
`updates_per_transition`, `gamma` (record 7.183) and `learning_rate` (record 7.199) were compared and chosen
(basis `gator_tested`; for Graph Transformer and GATv2 the published learning rate is 1e-3 already, so that field
keeps its citation and adds the measurement). Learning rate 1e-3 against 3e-4, with 8 updates and discount 0 on
ngspice `ota5` (Graph Transformer 32 / 4 / 2, 1,000 evaluations, seeds 0-2; the calibration study,
`artifacts/local/reviews/calibration-study-2026-10-05`): learned at evaluation 174, 139, 179 against 251, 262, 294,
98.1 % of the last third passing against 93.1 %, the passing designs' median power 105-110 uW against 101-103 uW.
Batch, warm-up, replay and episode length are the values those measurements were made with (basis
`gator_measured_with`): batch 32 learned a little earlier with 4 updates at four times the cost per update, warm-up 64
brought no gain, replay and episode length were not varied in record 7.183 (the calibration study then found replay 50
with episode 30 worse, 87.8 % at the end). `tau` was not varied; every preset already had 0.005.

**Measured** (record 7.199, `artifacts/local/reviews/starting-presets-2026-10-05`): the three starting presets as a
whole on ngspice `ota5` (1,000 evaluations, seeds 0-2, reward compressed + share 0.5), measured as in the calibration
study; "learned at" = the first design after which 50 of the last 100 pass.

| Network, learning rate | pass % 1st / 2nd / last third | learned at | median power of passing (uW) |
|---|---|---|---|
| Graph Transformer 32 / 4 / 2, 3e-4 (record 7.183's runs) | 34.2 / 85.6 / 93.1 | 251, 262, 294 | 103, 101, 103 |
| Graph Transformer 32 / 4 / 2, 1e-3 (calibration study) | 61.9 / 97.1 / 98.1 | 174, 139, 179 | 109, 105, 110 |
| `graph_transformer` starting preset, 48 / 4 / 4 | 52.7 / 95.8 / 98.5 | 187, 219, 164 | 106, 106, 108 |
| `rgcn` starting preset, 32 / 4 / 4 | 55.2 / 96.8 / 99.2 | 215, 139, 183 | 108, 104, 108 |
| `gatv2` starting preset, 192 / 3 / 4 | 39.5 / 95.9 / 96.7 | 209, 212, 300 | 99, 97, 101 |

All three learn, about as early as 32 / 4 / 2 at the same learning rate: the published sizes cost nothing in
learning. They cost time: one 40-design run took 35 s at 32 / 4 / 2 against 44, 46 and 49 s (Graph Transformer, RGCN,
GATv2) under the same load.

On Spectre, one run of the Graph Transformer starting preset (`real:mscr_ota7t`, one lane, seed 0, 800 launches, the
Specs, parameters and reward of record 7.183's morning run, `artifacts/local/reviews/starting-presets-2026-10-05/spectre`):
469 of 760 designs passed, the first at design 202, against 36 and 591 for that morning run (32 / 4 / 2, learning rate
3e-4, discount 0.99); per 100 designs 0, 0, 27, 95, 94, 98, 97 and 58 of the last 60 passed. The two runs differ in
network size, learning rate and discount at once.

The RGCN and GATv2 presets ran the same way (record 7.209, `spectre-rgcn/` and `spectre-gatv2/` in the same folder; the
configurations differ from the Graph Transformer run's only in the network):

| On Spectre, `real:mscr_ota7t`, seed 0 | designs passing | first passing design | passing per 100 designs | last third passing |
|---|---|---|---|---|
| morning run (7.183): Graph Transformer 32 / 4 / 2, lr 3e-4, discount 0.99 | 36 of 760 | 591 | 0 0 0 0 0 2 16 18 | 14 % |
| `graph_transformer` starting preset, 48 / 4 / 4 (7.199) | 469 of 760 | 202 | 0 0 27 95 94 98 97 58 | 98 % |
| `rgcn` starting preset, 32 / 4 / 4 | 444 of 761 | 218 | 0 0 49 80 84 92 85 54 | 88 % |
| `gatv2` starting preset, 192 / 3 / 4 | 419 of 761 | 289 | 0 0 5 86 85 93 95 55 | 93 % |

All three learn on Spectre as on ngspice. One seed each: the differences between the three are not established.
GATv2's passing designs draw the least bias current (median 527 uA against 691 uA for the Graph Transformer's and
572 uA for RGCN's), as its ngspice runs had the lowest power; no Specs row asked for it. Its larger network made each
design take 2.6-2.9 s against 2.0-2.1 s, with the same 1.1 s of simulation.

The numbers the papers give, kept in each field's note (under `published` in the API when replaced):

| Encoder | hidden | heads | layers | lr | gamma | tau | batch | warm-up | replay | episode |
|---|---|---|---|---|---|---|---|---|---|---|
| `graph_transformer` | 48 | 4 | 4 | 1e-3 | 0.9 | 0.005 | 32 | 8 | 50 | 30 |
| `gatv2` (borrowed GAT settings) | 192 | 3 | 4 | 1e-3 | 0.9 | 0.005 | 32 | 8 | 50 | 30 |
| `gcn` (removed 2026-09-26) | 32 | (4) | 7 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `rgcn` | 32 | (4) | 4 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `port_gnn` (removed 2026-09-24) | 32 | (4) | 5 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `mlp` (removed 2026-09-26) | 256 | (4) | 4 | 3e-3 | 0.8 | 0.005 | 256 | 120 | 1000000 | 30 |
| GATOR baseline (all; deleted 2026-10-05, record 7.191) | 32 | 4 | 2 | 3e-4 | 0 | 0.005 | 8 | 8 | 10000 | 4 |
| schema defaults (the baseline until 2026-10-05) | 32 | 4 | 2 | 3e-4 | 0.99 | 0.005 | 8 | 8 | 10000 | 4 |

## The three tested values (2026-10-05, record 7.183)

Every starting preset uses `initial_alpha` 0.01, `updates_per_transition` 8 and `gamma` 0 (record 7.192), with the
other training numbers those measurements were made with (batch 8, warm-up 8, replay 10,000, episode length 4) and
learning rate 1e-3 (record 7.199; those measurements used 3e-4). The measurements used a 32 / 4 / 2 Graph
Transformer; the presets keep the published network sizes, which learned as early with these values (record 7.199,
below). The GATOR baseline held exactly the measured setting until it was
deleted (record 7.191). The schema defaults -
0.2, 1 and 0.99 - are what every GATOR run used before, and with them soft actor-critic is a uniform random search:
on Spectre (`real:mscr_ota7t`) two very different reward settings gave the same design in 147 of 150 positions, and
none of 922 designs passed. Measured with 175 runs on two ngspice circuits and five Spectre runs
(`artifacts/local/reviews/defaults-study-2026-10-05/README.md`; the reasons are in
[decisions.md](decisions.md), "The tested defaults"):

| Value | Before | Now | What was measured |
|---|---|---|---|
| `initial_alpha` | 0.2 | 0.01 | at 0.2 exploration swamps the reward and never comes down within a run; 0.05 ends lower, 0.002 learns twice as late |
| `updates_per_transition` | 1 | 8 | with 1 nothing learns, whatever else is set; 4 learns at about evaluation 1,000, 8 at about 470, 16 at about 330; 0.1 to 0.15 s per update |
| `gamma` | 0.99 | 0 | an action is a whole design scored on its own measurement; learned at 269 instead of 466 (ngspice only) |

With temperature 0.01 and 8 updates the Spectre run found 36 passing designs in 760 (the first at design 591).
Learning started after 250 to 600 evaluations with these values (after about 150 to 300 with the starting presets,
record 7.199), so a shorter from-scratch run is close to a random search.

* The schema defaults stay as they were: a configuration without an Advanced block, a test and a saved model keep
  their meaning. Static validation warns (`sac_values_random_search`) when a run that trains has fewer than 4 updates
  per evaluation or a starting temperature above 0.05, and (`budget_below_sac_learning`) when a from-scratch SAC run
  has fewer than 300 evaluations; the RL networks window says the first where the values are set.
* Every starting preset holds these three and the other training numbers of the runs that learned (record 7.192);
  until then a published value stayed (`rgcn`: one update per step from the authors' code, the attention presets'
  `gamma` 0.9). The published network sizes were measured with them on ngspice and on Spectre (records 7.199 and
  7.209).
* An encoder whose saved values were the GATOR baseline (the old baseline saved before the change, or the baseline
  with the three values saved on 2026-10-05) is read as its starting preset since record 7.191;
  `network_settings.json` is not rewritten. A configuration already open keeps its own numbers: the window's
  **This run / Saved default** table shows the differences, and **Use saved defaults** applies the preset.

`(4)` = ignored by that network; kept at 4 because the number is written into every checkpoint.

## Where each number comes from

Every quote below was read in the primary source on 2026-09-20 (paper text or the authors' code), not
taken from a summary. "Paper" = stated in the publication; "code" = only in the authors' released code.

### `gcn` (removed 2026-09-26; historical preset provenance)
* **layers 7** - paper. Wang et al., *GCN-RL Circuit Designer*, DAC 2020, arXiv:2005.00406: "we apply
  seven GCN layers to make sure the last layer have a global receptive field over the entire topology
  graph". The paper states nothing else about its agent (no width, learning rate, batch or replay size)
  and its agent code was never released. Budget: "we ran 10000 steps"; 300 in the transfer experiments.
* **hidden 32, and all training numbers** - Li & Chan Carusone, ICCAD 2023 (below). Their GCN+DDPG
  benchmark uses `GCNConv` widths 32-32-16-16 (code); GATOR blocks have one width, so the first is used.

### `rgcn`
All from Z. Li, A. Chan Carusone, *Design and Optimization of Low-Dropout Voltage Regulator Using
Relational Graph Neural Network and Reinforcement Learning in Open-Source SKY130 Process*, ICCAD 2023,
doi:10.1109/ICCAD57390.2023.10323720, code `github.com/ChrisZonghaoLi/sky130_ldo_rl`. It is the one
published line of work with an R-GCN inside a transistor-sizing RL loop (DDPG).
* Paper: "The episode length w is 50, the size of our memory buffer M is 100000, and the batch size B
  is 128."; "1000 and 4000 initial random exploration steps for LDO1 and LDO2"; Algorithm 2:
  "gamma <- 0.99, rho <- 0.005"; "10000 simulations for LDO1 and ... 20000 simulations for LDO2".
* Code only: four `RGCNConv` layers 32-32-16-16 with `num_bases=32` (`models.py`);
  `optim.Adam(..., lr=3e-4, weight_decay=1e-4)` for actor and critic, one update per step (`ddpg.py`).
* Differences from GATOR: two hand-annotated edge types (signal / bias path) instead of terminal role
  and direction; tapering widths; no normalization or residuals; weight decay (GATOR has none); updates
  start only after warm-up (GATOR updates as soon as one batch is stored).

### `gatv2` (replacement on 2026-09-26)

The operator is PyG `GATv2Conv`, following [Brody et al., ICLR 2022](https://arxiv.org/abs/2105.14491). It uses independent source/target projections, port edge features, no inserted self-loops, and the existing outer residual/LayerNorm/feed-forward block. Every cited numerical setting is marked **closest network**: the settings below were gathered for the old GAT preset and have not been validated as a GATv2 sizing recipe. Saved `gat` settings are preserved in their old entry and are not copied to `gatv2`.

### Historical `gat` preset sources (now borrowed by `gatv2`)
No single GAT sizing paper reports a complete agent.
* **layers 4, episode 30** - paper. Gursoy et al., *Lighthouse RL*, arXiv:2607.14008 (2026), the closest
  published setup to GATOR (SAC + GAT): "four Graph Attention Network (GAT) layers with residual
  connections and layer normalization"; "An episode consists of 30 time steps"; "6,000 SPICE simulations
  for the two-stage OpAmp and 30,000 simulations for the multistage amplifier". It reports no width,
  heads, learning rate, batch or replay size.
* **heads 3, hidden 192** - code. Cao, Benosman, Zhang, Ma, DAC 2022, arXiv:2204.12948 is the canonical
  GAT sizing paper but says only "GAT ... can also be built similarly which is not elaborated here". The
  authors' repository `github.com/xz-group/AutoSizing` has `num_heads = 3` and
  `n_latent_var = 64 * num_heads`. Its README names no paper, so linking it to the DAC figures is an
  inference. It uses PPO (lr 5e-4, gamma 0.95, 50-step episodes), which has no replay buffer.
* **lr 1e-3, gamma 0.9, batch 32, replay 50** - paper. Li et al., *A Circuit Attention Network-Based
  Actor-Critic Learning Approach to Robust Analog Transistor Sizing*, MLCAD 2021, the only off-policy
  (DDPG) attention-network sizing paper: "The learning rates for the actor and critic are set as 0.001
  and 0.002, respectively. The replay buffer size is 50 for both the actor and critic. The training batch
  size 32. The reward discount is 0.9." GATOR has one learning rate; the actor's is used. **Its whole
  budget was 300 steps** ("the maximum training step is set as 300"), which is why the replay buffer is
  so small. Raise it for longer runs.

### `graph_transformer`
* **hidden 48, heads 4, layers 4** - paper. Fan et al., *Graph-Transformer-based Surrogate Model for
  Accelerated Converter Circuit Topology Design*, DAC 2024, doi:10.1145/3649329.3656258: "a total of 4
  layers with ReLU activation ... the number of heads as 4 and D_k as 6"; "embeddings with dimension of
  48". It is the only published analog graph transformer whose attention is restricted to graph
  neighbours, like GATOR's `TransformerConv` block. It is a supervised surrogate for power converters,
  not a sizing agent, and reports no learning rate, optimizer or batch size.
* **Training numbers: borrowed** from the attention-network sizing agents of the `gat` preset, marked
  "closest network" in the panel. **No publication uses a graph transformer as the RL sizing agent**
  (searched 2023-2026; the nearest are ZeroSim, which uses a transformer as the simulator surrogate, and
  ARCS, an unreviewed preprint with a GPT policy for fixed templates). GATOR's `graph_transformer` and
  `gatv2` blocks use different attention operators and projection parameterizations.

### `mlp` (removed 2026-09-26; historical preset provenance)
All from Kim et al., *PPAAS: PVT and Pareto Aware Analog Sizing via Goal-conditioned Reinforcement
Learning*, ICCAD 2025, arXiv:2507.17003, code `github.com/SeunggeunKimkr/PPAAS`. It is the best
documented **soft actor-critic** sizing paper (GATOR's own algorithm), with fully connected networks.
* Paper: "we adopt Soft Actor-Critic (SAC)"; "hidden dimensions of [256,256,256,256] for the actor and
  [256,256,128] for the critics"; "learning rate lr=0.003, batch size B=256, discount factor gamma=0.8";
  "The episode horizon is fixed to H=30"; "trained for 12K, 24K, 8K, and 12K steps".
* Code only: `--learning_starts 120` (`scripts/TSA.sh`), `tau` default 0.005 (`train.py`); replay
  1,000,000 and one update per step are Stable-Baselines3 defaults the authors did not change.
* GATOR builds actor and critics at one size (256), where the paper's critics taper to 128.
* Not used: the classic MLP reference AutoCkt (Settaluri et al., DATE 2020, arXiv:2001.01808) uses PPO
  with "three layers with 50 neurons each" (its code says `[64, 64]`) and a 30-step horizon, and states
  no learning rate, so it cannot fill SAC settings.

### `port_gnn` (removed from the optimizer on 2026-09-24, record 7.83; kept as the provenance of the preset that existed)
No sizing paper uses this exact network (an MLP message over the source node and a terminal-role edge
feature, mean-aggregated, no attention). Everything here is marked "closest network".
* **layers 5, hidden 32** - paper. Ren, Kokai, Turner, Ku, *ParaGraph*, DAC 2020,
  doi:10.1109/DAC18072.2020.9218515: "the dimension of embedding and number of layers were set to F = 32
  and L = 5". Its device/net graph types edges by terminal and direction, like GATOR's. It is supervised
  parasitic prediction (Adam, lr 0.01, 300 epochs), so it has no RL settings.
* **Training numbers** - Li & Chan Carusone, ICCAD 2023, the only RL sizing work with edge-typed message
  passing.

## What the publications do not give us

* **Results on GATOR circuits** (records 7.199, 7.209). The starting presets - the published network sizes with the
  training numbers of the runs that learned - learn on ngspice `ota5` (three seeds each) and on Spectre
  (`real:mscr_ota7t`, one run each). The papers' own training numbers were never measured here; they stay a cited
  reference, not evidence.
* **Scale.** Published budgets: 300 steps (CAN), 1,400-4,300 (MBTD3), 6,000-50,000 (the rest). The only
  published SAC settings (PPAAS) were used with 8,000-24,000 steps. Using them with tens of evaluations
  is an extrapolation. Warm-up in the papers is 1-33 % of the budget; nobody uses more than one update
  per transition. In GATOR the random warm-up also applies to `fine_tune`, so a large warm-up stops a
  pretrained policy from acting at all in a short run.
* **Soft actor-critic specifics.** No paper reports an entropy temperature, target entropy or gradient
  clipping, so `target_entropy_per_action` and `max_grad_norm` stay at GATOR defaults and `initial_alpha` is the
  value measured here (0.01, record 7.183).
* **Different architectures.** Every cited network differs from the GATOR block (pre-LayerNorm, residual,
  feed-forward of width 2h, separate encoders for the actor and both critics, one width throughout).
  Layer counts and widths transfer; exact parameter counts do not.
* **Presets break the equal-size encoder comparison.** The encoder ablations give every encoder the same
  width and depth (32 / 4 / 2) by default. With presets the networks differ 32-fold in size, so a
  difference in results is no longer a statement about the encoder type. For such comparisons give every
  encoder the same sizes (the GATOR baseline that set 32 / 4 / 2 for all was deleted on 2026-10-05). Measured
  trainable parameters, actor + two critics (2026-09-20, PyG 2.8.0.post1):

  | Encoder | preset | 32 / 4 / 2 |
  |---|---|---|
  | `graph_transformer` | 349,540 | 105,476 |
  | `gat` (historical GATv1) | 3,858,820 | 87,044 |
  | `gcn` | 159,524 | 78,884 |
  | `rgcn` | 270,884 | 158,756 |
  | `port_gnn` (removed 2026-09-24) | 159,908 | 92,804 |
  | `mlp` | 5,197,060 | 72,164 |

  The `graph_transformer` figures include weights that are never used: PyG's `TransformerConv` always
  allocates `lin_skip`, which the block (`root_weight=False`) never calls. That is 28,224 of the preset's
  349,540 and 6,336 of the 32 / 4 / 2 network's 105,476.
* **Checkpoints.** A checkpoint only loads into the network it was trained with, and the whole
  `model_config` (including the ignored `heads`) is compared. All existing checkpoints are 32 / 4 / 2.
  Since 2026-09-21 the panel shows the network block in Mode `scratch` only: in `resume`, `fine_tune` and
  `frozen` the configuration takes the chosen model's network by itself (the earlier warning with the button
  "Use the checkpoint's network" is gone). Only the network follows, not the numbers under "Advanced"; an
  "Advanced" edit made while a model is loaded keeps the sizes already stored for that encoder.

## Behaviour details

* Storage: `configs/local/workbench/network_settings.json` (git-ignored; `GATOR_WORKBENCH_SETTINGS_DIR`
  overrides the directory, which is how the tests stay out of it). Only encoders you edited are stored.
  Editing back to the preset values removes the stored copy. A damaged file is reported in the panel and
  never overwritten.
* API: `GET /api/network-settings`; `PUT /api/network-settings/{encoder}` with
  `{"network": {...}, "advanced": {...}}`. `POST /api/network-settings/{encoder}/reset` went with the two
  buttons that called it (record 7.191). The complete value set is validated with the same schema
  as a run configuration, including "hidden divisible by heads" for the two attention encoders, so
  hidden and heads can be changed together.
* A configuration submitted **without** a network block still gets the schema defaults (the setting
  behind every result before 2026-10-05), so existing configuration files, the CLI and the tests keep their meaning;
  validation says that those values do not learn. The panel always
  writes explicit values into the configuration, so what is shown is what runs.
* If the configuration's numbers differ from the backend's (an imported file, an undo, "Use the
  checkpoint's network"), the panel says so and offers "Load backend values" / "Save these to the
  backend" instead of silently picking one.
* New static-validation warning `budget_within_warmup`: the whole budget is random warm-up.
* The number boxes now keep what you type while the box has focus, so `0.005` and `3e-4` can be typed.

## Checked but not used

GANA (spectral GCN, annotation), PEA (placement), Hakhamaneshi et al. TCAD 2023 (DeepGEN 15 x 128,
featureless edges, supervised), CktGNN (VAE + BO), Circuit-GNN (RF resonators), DICE (GIN, preprint),
RobustAnalog (4-layer MLPs, batch 64, replay 1000, no learning rate), DNN-Opt and L2DC (no numeric
hyperparameters reported), Uhlmann et al. (TD3 + HER, 2 x 256, lr 1e-3, batch 128, replay 1e6),
MBTD3, GLOVA, CircuitGPS, ZeroSim, CktGen. Not opened (paywall or blocked): Wu & Savidis MLCAD 2022,
PVTSizing DAC 2024, Park et al. ISOCC 2023 (a second SAC paper, abstract only).
