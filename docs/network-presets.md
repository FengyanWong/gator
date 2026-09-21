# Per-encoder network settings in the workbench

Added 2026-09-20. Code: `src/gator_workbench/network_presets.py`, panel `frontend/src/panels/Right.tsx`,
tests `tests/workbench/test_wb_network_presets.py`, browser check `frontend/scripts/network_panel_check.mjs`
(headless Edge, 16 checks; writes are intercepted, so it never changes your saved settings).
Nothing under `src/analog_optimizer/` changed.

## In plain words

Before, the panel had one set of numbers (hidden 32, heads 4, layers 2, batch 8, ...) no matter which
network you picked, and those numbers were typed into the web page rather than read from the backend.

Now the backend keeps **one setting per network type**:

* Picking a network in the drop-down **loads** that network's numbers from the backend.
* Changing a number (network sizes or anything under Advanced) **saves** it in the backend for that
  network only. It is still there after a restart.
* Each network starts from numbers that **published analog-circuit papers actually used**. The panel
  shows where every number comes from ("Where the ... values come from").
* Two buttons bring you back: **Publication preset** (forget my edits) and **GATOR baseline** (the old
  32 / 4 / 2 setting that every existing GATOR result and checkpoint was made with).
* The **heads** box is greyed out with "ignored by this encoder" unless the network is
  `graph_transformer` or `gat`. Only those two have attention heads.

**The one thing to keep in mind:** the papers ran thousands of simulations per run; GATOR's real runs
used tens. A published batch size of 128 with 1,000 warm-up steps means that in a 60-evaluation run the
network never learns and every action is random. The panel and the static validation warn when that
happens. For short runs, for comparing encoders at equal size, and for loading an existing checkpoint,
click **GATOR baseline**.

## The presets

`hidden / heads / layers`, then the training numbers. Anything not listed is the GATOR default
(`update_every` 1, `updates_per_transition` 1, `initial_alpha` 0.2, `target_entropy_per_action` 1,
`max_grad_norm` 10; for `gat` and `graph_transformer` also `tau` 0.005 and `warmup_transitions` 8).

| Encoder | hidden | heads | layers | lr | gamma | tau | batch | warm-up | replay | episode |
|---|---|---|---|---|---|---|---|---|---|---|
| `graph_transformer` | 48 | 4 | 4 | 1e-3 | 0.9 | 0.005 | 32 | 8 | 50 | 30 |
| `gat` | 192 | 3 | 4 | 1e-3 | 0.9 | 0.005 | 32 | 8 | 50 | 30 |
| `gcn` | 32 | (4) | 7 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `rgcn` | 32 | (4) | 4 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `port_gnn` | 32 | (4) | 5 | 3e-4 | 0.99 | 0.005 | 128 | 1000 | 100000 | 50 |
| `mlp` | 256 | (4) | 4 | 3e-3 | 0.8 | 0.005 | 256 | 120 | 1000000 | 30 |
| GATOR baseline (all) | 32 | 4 | 2 | 3e-4 | 0.99 | 0.005 | 8 | 8 | 10000 | 4 |

`(4)` = ignored by that network; kept at 4 because the number is written into every checkpoint.

## Where each number comes from

Every quote below was read in the primary source on 2026-09-20 (paper text or the authors' code), not
taken from a summary. "Paper" = stated in the publication; "code" = only in the authors' released code.

### `gcn`
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

### `gat`
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
  `gat` blocks differ only in the attention function.

### `mlp`
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

### `port_gnn`
No sizing paper uses this exact network (an MLP message over the source node and a terminal-role edge
feature, mean-aggregated, no attention). Everything here is marked "closest network".
* **layers 5, hidden 32** - paper. Ren, Kokai, Turner, Ku, *ParaGraph*, DAC 2020,
  doi:10.1109/DAC18072.2020.9218515: "the dimension of embedding and number of layers were set to F = 32
  and L = 5". Its device/net graph types edges by terminal and direction, like GATOR's. It is supervised
  parasitic prediction (Adam, lr 0.01, 300 epochs), so it has no RL settings.
* **Training numbers** - Li & Chan Carusone, ICCAD 2023, the only RL sizing work with edge-typed message
  passing.

## What the publications do not give us

* **No result on GATOR circuits.** None of these settings has been run on GPDK045 or with Spectre here.
  A preset is a cited starting point, not evidence that it is better than the baseline.
* **Scale.** Published budgets: 300 steps (CAN), 1,400-4,300 (MBTD3), 6,000-50,000 (the rest). The only
  published SAC settings (PPAAS) were used with 8,000-24,000 steps. Using them with tens of evaluations
  is an extrapolation. Warm-up in the papers is 1-33 % of the budget; nobody uses more than one update
  per transition. In GATOR the random warm-up also applies to `fine_tune`, so a large warm-up stops a
  pretrained policy from acting at all in a short run.
* **Soft actor-critic specifics.** No paper reports an entropy temperature, target entropy or gradient
  clipping, so `initial_alpha`, `target_entropy_per_action` and `max_grad_norm` stay at GATOR defaults.
* **Different architectures.** Every cited network differs from the GATOR block (pre-LayerNorm, residual,
  feed-forward of width 2h, separate encoders for the actor and both critics, one width throughout).
  Layer counts and widths transfer; exact parameter counts do not.
* **Presets break the equal-size encoder comparison.** The encoder ablations give every encoder the same
  width and depth (32 / 4 / 2) by default. With presets the networks differ 32-fold in size, so a
  difference in results is no longer a statement about the encoder type. Use the GATOR baseline for such
  comparisons. Measured trainable parameters, actor + two critics (2026-09-20, PyG 2.8.0.post1):

  | Encoder | preset | GATOR baseline |
  |---|---|---|
  | `graph_transformer` | 349,540 | 105,476 |
  | `gat` | 3,858,820 | 87,044 |
  | `gcn` | 159,524 | 78,884 |
  | `rgcn` | 270,884 | 158,756 |
  | `port_gnn` | 159,908 | 92,804 |
  | `mlp` | 5,197,060 | 72,164 |

  The `graph_transformer` figures include weights that are never used: PyG's `TransformerConv` always
  allocates `lin_skip`, which the block (`root_weight=False`) never calls. That is 28,224 of the preset's
  349,540 and 6,336 of the baseline's 105,476.
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
  `{"network": {...}, "advanced": {...}}`; `POST /api/network-settings/{encoder}/reset` with
  `{"to": "publication" | "gator_baseline"}`. The complete value set is validated with the same schema
  as a run configuration, including "hidden divisible by heads" for the two attention encoders, so
  hidden and heads can be changed together.
* A configuration submitted **without** a network block still gets the schema defaults (the GATOR
  baseline), so existing configuration files, the CLI and the tests keep their meaning. The panel always
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
