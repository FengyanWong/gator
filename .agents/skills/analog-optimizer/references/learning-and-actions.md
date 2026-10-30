# Selectable encoders, SAC and the action contract

The reward-v2 update of 2026-09-26 takes precedence over this document's older nominal-only/encoder descriptions: the user authorized
optimizer changes under `docs/plan-reward-v2-real-flow.md`; the current encoders are GT/RGCN/GATv2/GraphGPS/parameter-group cross-attention (the last two added on 2026-10-06, record 7.228).
The v2 evaluator, 21N+11 inputs, optional nominal OP, complete condition plan, replay and checkpoint
contracts are integrated and passed bounded real OTA7 A/B/C acceptance: 73 Spectre calls (A21, B44 including one recorded failure, C8),
with a total cap of 77 and B44 separately and explicitly authorized by the user. After acknowledging unknown license status, the user proceeded through the normal licensing process;
licensing was not bypassed. B produced 8 transitions and 7 SAC updates; the 6 update cases for GT/RGCN/GATv2 with OP on/off,
and exact recovery of the next update, used B's real replay, rather than six new on-policy experiments.
No robust-feasible design was found, and no advantage of the new reward was demonstrated. See `docs/reward-v2.md`;
do not automatically migrate old checkpoints, substitute MOCK for acceptance or start an unauthorized 999-call study.
On 2026-09-29, reward v2.1 (digest `3f00832c...`, commit `8cf53ae`) also added `after_nominal`, optional failure on missing values,
continuing episodes after failure, objective shapes and margin sides, and a separate alpha learning rate; the OTA7 physical gate check used 10 Spectre calls (record 7.108).

This document defines project design and verification requirements; see [Project decisions](project-decisions.md) for the implementation state. Interface acceptance is not evidence of transfer effectiveness.
Algorithm foundations are in [S5](sources.md), and graph-operator facts in [S4, S6](sources.md); parameter grouping, masks, rewards and their cross-circuit combination are project design choices.

## 1. State, specifications and model inputs

Suggested state: `s = (G_static, x_current, context, measurements, validity, status, budget_state)`.
Pass specifications `g` separately from state; state measurements must come from the currently executed parameters, not an old candidate.
`budget_state` is needed only when remaining steps affect task termination/decisions, but its Markov/termination meaning must be explicit once used.

Each specification contains at least:

```text
metric_id / unit / comparator: min | max | range
lower_target / upper_target / positive_normalization_scale
weight / required / active
```

LDO/VCO/OpAmp do not share a meaningless "first metric". Specification identity, direction, values and masks all enter the conditioned representation.
Possible implementations include a fixed registry+mask or a shared spec-token encoder; decide from existing code and tests.
Do not estimate specification-normalization statistics from the complete test set.

Ensure inputs contain sizes, targets and validity before adding OP, bias regions or history features; each addition needs an ablation and a missing-value policy.

Nominal-only remains the default; the accepted OTA7 with explicit reward-v2 `always` may put complete five-condition evaluations into
training reward/replay. Input graphs and OP come only from nominal, with the full condition plan and results retained separately; missing required
measurements/infrastructure failures produce no reward/replay. Post-validation remains a separate record, and the old `robust_score` does not replace
training reward. MC, skip-on-fail and training corners on other profiles did not receive physical acceptance in this round.
(Synchronized 2026-09-30: reward v2.1's `after_nominal` runs corners only after nominal passes all hard specs and
has passed a physical gate check on OTA7; MC and training corners on other profiles remain unimplemented.)

## 2. Port-aware Graph Transformer

Requirements:

- Device/net types and D/G/S/B or equivalent terminal relations actually participate in attention key/value/bias or typed-relation operations.
- Do not derive semantic positional embeddings from original node indices or instance names.
- When using stabilizing modules such as residuals, normalization and feed-forward layers, specify and test their actual data flow; do not merely stack a class named Transformer.
- Retain node representations through actor/critic; do not provide only one fixed pooled vector followed by a fixed-dimensional action head.
- Prohibit attention across graphs; padding masks affect attention, pooling and loss.

Explicitly identify the attention scope:

```text
local_port_attention       # multi-head graph attention along actual connections
structural_global_attention # global attention within one graph, with defined structural bias
hybrid_attention            # local/global combination in an explicit order
```

The first choice is an engineering decision to test; do not impose a rule that "more global is more advanced".
PyG `TransformerConv` is neighborhood-based message-passing attention with edge-feature support; that layer alone does not implement global Graphormer/DEGT. [S6](sources.md)

Structural distances, diffusion/spectral features and similar additions are later options. Before adding them, define their graph meaning, caching, complexity, permutation consistency and whether they improve independent test results.

### Encoder-selection contract (implemented before M6)

Select through `models.ModelConfig(encoder_type=...)` and `models.build_encoder()`. The common interface is `encoder(GraphBatch, actions=None) → (nodes[N,H], groups[G,H], context[B,H])`. Actor/Q1/Q2 use the same configuration with independent weights; retain common features, specifications, action injection, parameter-group readout and SAC heads, replacing only node processing.

Currently (synchronized 2026-09-30; see `ENCODER_TYPES` in `src/analog_optimizer/models/encoders.py`), only the first five rows remain; the others were removed, their names are explicitly rejected and old weights are not migrated:

| encoder_type | Current node processing and meaning |
|---|---|
| `graph_transformer` (default) | `TransformerConv` local multi-head attention with role/direction/ordinal in edge features |
| `rgcn` | `RGCNConv`, terminal role × direction as relations, mean per relation; no extra ordinal encoding |
| `gatv2` | `GATv2Conv` multi-head attention (`share_weights=False`), terminal edge features enter attention; no added self-loops, with the outer residual preserving self-representation |
| `graph_gps` | GraphGPS-style (`PortGPSBlock`, 2026-10-06, record 7.228): each layer combines parallel local terminal-attention messages (as in GT) and global self-attention within the circuit (`CircuitAttention`); default `structural_encoding='rwse'` |
| `group_cross_attention` | GT local layers plus parameter-group-to-node cross-attention readout (`GroupAttentionReadout`, 2026-10-06, record 7.228); optional RWSE |
| ~~`port_gnn`~~ | Removed on 2026-09-24 (the former M5 terminal MLP messages and destination mean); available only at source commit bbdfe36 and earlier |
| ~~`mlp`~~ | Removed on 2026-09-26 (the former shared node-wise MLP, ignoring circuit edges/terminals/ordinal); the last five-encoder source containing it is commit 9bc488f |
| ~~`gcn`~~ | Removed on 2026-09-26 (the former ordinary `GCNConv`, ignoring role/ordinal); same source as above |
| ~~`gat`~~ | GATv1 (`GATConv`), replaced by `gatv2` on 2026-09-26; GATv1 weights cannot load into GATv2 |

- The former MLP control (removed) was a connectivity-free ablation supporting variable node/action counts, distinct from a flattened fixed-topology MLP.
- GT/GATv2 hidden_dim must be divisible by heads; RGCN does not use heads. Equal widths/depths do not guarantee matched parameter counts.
- Do not create a dedicated final layer for new topologies. Verify agreement between mixed batches and single graphs, renaming/reordering equivariance, action ownership and gradients, and exact recovery. Also verify sensitivity of port-aware graph encoders (GT/RGCN/GATv2) to structural/terminal changes.
- Retain the original `models.graph_transformer` import; old `attention_mode='local_port_attention'` still maps to GT, while `port_message_passing` (port-GNN) is rejected. New calls use `encoder_type`. Reject conflicting configurations; never silently fall back to GT.
- Checkpoints save encoder configuration. Different architectures cannot load each other's weights directly; code digests/schema/dependencies remain strictly checked, without default compatibility for checkpoints from before a code change.

The project's `docs/encoder-ablation.md` is authoritative for specific commands and acceptance records; see [Experiments and review](evaluation.md) for transfer modes and comparison rules.

M1 now provides homogeneous tensor export independent of RL, dense node masks and batch group-index validation; see the [Graph contract](graph-contract.md). General raw x column widths differ from model hidden_dim, so use the corresponding input projection; do not alter the canonical graph to fit a network's final layer. Every operator with an adjacency cache (such as the removed GCN) must disable caching across calls to prevent mixed topologies from reusing the previous graph.

Training inputs now use bounded caches within the learner: static templates and raw tensors of complete historical observations can be reused; batches, network representations/attention under current parameters and gradients are still recomputed each time. Cache capacities do not change the learning contract, and cold checkpoint recovery retains exact training results; do not extend raw-input caching to stale embeddings or statistics fitted across tasks. Implementation/invalidation conventions are in the [Graph contract](graph-contract.md); project timings are in `docs/input-tensor-cache.md`.

## 3. Variable-dimensional actor

Each independent parameter group `j` aggregates node representations of all its members, combines them with parameter kind, current value, bounds, domain and target conditioning, and uses a shared head to output `mu_j, log_std_j`.
Aggregation is insensitive to member order; apply the same shared weights or an explicitly type-conditioned head to all adjustable groups.
Do not allocate a new set of final output layers for each new topology.

Continuous part:

```text
u_j = mu_j + exp(log_std_j) * epsilon_j
z_j = tanh(u_j)                          # normalized proposal in (-1, 1)
```

Use a numerically stable tanh log-Jacobian correction and limit `log_std` to the configured range.
For each graph, sum `log_pi` over valid independent parameter groups, counting bound devices within a group only once.
Graphs with no valid actions must not enter ordinary SAC training; explicitly skip/error rather than create a meaningless zero-dimensional entropy loss.
With padding, first set invalid entries to safe finite values, then apply masked reduction to avoid `0 * NaN` still producing NaN.

## 4. From actions to physical parameters

Suggested first implementation: one action meaning, made explicit in configuration:

**Absolute linear mapping:**

```text
p = lower + (z + 1) / 2 * (upper - lower)
```

**Absolute logarithmic mapping for positive parameters:**

```text
p = exp(log(lower) + (z + 1) / 2 * (log(upper) - log(lower)))
```

Logarithmic mapping requires `0 < lower < upper`; do not silently add a small constant to zero/negative values and mix them into the same semantics.
A relative-increment mode needs separately defined step sizes, clipping and state dependence, verified by independent tests; do not mix it with absolute mode.

Then perform explicit legalization: integer/grid/enumeration projection, group bindings, bounds and cross-constraint validation.
Save `proposal z`, `applied physical parameters`, projection reasons, quantization/clipping statistics and conversion version.
Caches and real circuit state use actual executed parameters.

### Continuous SAC with discrete parameters

The first continuous-learning baseline may fix discrete parameters; later continuous proposals followed by integer quantization must be labelled **continuous proxy + projection**.
Projection maps several proposals to the same physical candidate; do not call this strict mixed-action SAC.

Suggested initial convention: the critic defines Q over normalized proposals `z`; the environment performs deterministic legalization internally.
Replay stores that `z` and actual parameters, and policy loss queries the critic with the same `z` meaning.
This avoids differentiating round, but the critic remains a function approximation across projection-induced discontinuities and needs tests.

A later change to an applied-action critic requires redesigning policy gradients, probability/entropy and quantization semantics together; replacing one replay column is insufficient.
The environment does not backpropagate through Spectre, netlist editing or external simulation; the policy obtains gradients through the differentiable critic.

## 5. Action-conditioned Twin Critics

Each critic receives `s, g, z`, first binds group actions to parameter tokens or their device members, then performs action-conditioned node processing and graph-level pooling to output one Q per graph. The graph encoder propagates neighborhood messages while retaining action ownership and group readout.
Do not lose action ownership; appending an arbitrarily ordered action vector to a pooled graph does not provide inherent cross-topology support.
Changing actions on the same graph must cause traceable changes to critic inputs; gradient tests must detect the actor→action→Q path.

Q1/Q2 have independent parameter sets by default; actor and critics may share structural code but do not share trainable tensors by default.
With a shared encoder, specify which parameters each loss updates, whether gradients stop and which state the target corresponds to, avoiding duplicate steps.
Sharing one model across circuits and sharing actor/critic encoders within one training run are different questions.

## 6. SAC updates and masks

Start with the continuous SAC variant without a separate V network: twin Q, target Q, a reparameterized actor, entropy term, replay and Polyak/soft updates. [S5](sources.md)
Automatic temperature may be the project's default implementation choice, but its configuration and tests must be recorded.

Project target convention:

```text
y = r + gamma * bootstrap_mask * (
        min(Q1_target(s_next, g, z_next), Q2_target(s_next, g, z_next))
        - alpha * log_pi_next
    )
L_actor = mean(alpha * log_pi - min(Q1(s, g, z), Q2(s, g, z)))
```

Do not backpropagate through the target branch; resample next actions from the current actor. Target Q soft updates include the corresponding encoder.
Temperature updates appropriately detach actor outputs; state the loss sign and test adjustment directions under high/low entropy.

Graphs may have different valid action counts: `target_entropy = -c * active_action_count` is a starting point to test, with configurable `c`.
Check entropy, Q targets and reward scales in mixed batches of large/small graphs; do not use the global padded dimension as every circuit's entropy target.

Distinguish `terminated` from `truncated`. An external sampling time limit is not automatically MDP termination; specify when to bootstrap.
If the step budget is part of the task definition, include remaining budget in state and define termination for that finite-horizon task.
Do not invent next states and rewards for infrastructure failures and insert them into replay.

A single learner's update-to-data ratio is based on newly added valid transitions, rather than uncontrolled independent updates by each parallel worker.

## 7. Reward and metric validity

Prefer a pure-function evaluator, separate from simulator and training code.
First validate units, directions and metric validity; the positive normalization scale `s_i > 0` comes from configuration or training statistics, not direct division by a possibly zero/negative target.

Suggested starting point: nonnegative violations:

```text
min constraint:   v_i = max(0, (target_i - measured_i) / s_i)
max constraint:   v_i = max(0, (measured_i - target_i) / s_i)
range constraint: v_i = max(0, (lower_i - measured_i) / s_i,
                              (measured_i - upper_i) / s_i)
V = sum(active_i * weight_i * v_i) / sum(active_i * weight_i)
base_reward = -V
```

These formulas apply only to required metrics that passed validity checks; no valid required metrics means no success.
Success requires every required metric to be valid and meet its own threshold/predefined tolerance, not just a small-looking average violation.

When adding a success bonus or secondary objectives such as power, specify magnitudes, constraint priority and stopping conditions so required constraints cannot be sacrificed for reward.
Do not treat a non-oscillating VCO as "best zero power"; validate oscillation, amplitude and a steady-state window before VCO frequency.
OpAmp phase margin needs a valid crossover/loop definition; LDO dropout, stability and load conditions need independent measurement contracts.
Every measurement formula comes from this project's testbench/measurement specification and fixtures, not guesses from names inside the model.

Past discussions mentioned potential-based reward; it is not required in the first version. If retained, specify base reward, Phi, gamma and termination boundaries and test the actual `gamma * Phi(s_next) - Phi(s)`; do not call every difference reward potential-based.

## 8. Saving experience and recovery

Complete training recovery records at least:

```text
encoder / actor / Q1 / Q2 / target Q1 / target Q2
optimizers / alpha or log_alpha / temperature optimizer
feature/spec normalizers / type vocabularies / graph & action schema
config / code revision / dependency versions / PDK-map identity
RNG states / sampler states / replay data or replay manifest
training counters / topology split / failure and simulation budgets
```

Do not disguise a new topology as the same transferable policy by changing its output layer.
On recovery, validate schema/vocabulary/action-conversion versions; mismatches need migration or rejection, never silent loading.
Inference-only use may omit critics/replay but retains the actor encoder, specification/parameter normalization and action semantics.

## 9. Later boundaries for surrogates

Surrogates default to off; there is no required "encoder → surrogate → SAC" chain.
For future surrogate research, first define its purpose: metric prediction, candidate screening, auxiliary representation or model-based rollouts; each needs different validation.
Use only permitted data for training/calibration, record uncertainty and OOD, and label real measurements and predictions in separate tables.
Final designs must pass real Spectre validation; report both surrogate-construction costs and the real calls saved.
