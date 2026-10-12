# GraphGPS and parameter-group cross-attention

**2026-10-12:** [CircuitGPS](circuit-gps.md) adds a separate `circuit_gps` option with
joint circuit/spec/parameter attention and structured measurement programs. The
two architectures described below retain their computations and saved weights.

Added on 2026-10-06 at the user's request. Both are experimental alternatives to
the existing port-aware Graph Transformer. Integration tests establish execution,
batch isolation and checkpoint behavior; they do not establish better circuit
optimization, transfer performance, or novelty.

| Encoder ID | Computation | Starting structural input |
| --- | --- | --- |
| `graph_gps` | Every block combines parallel local port-aware TransformerConv messages and full attention over nodes in the same circuit, followed by a feed-forward residual | `rwse` |
| `group_cross_attention` | Local port-aware Graph Transformer blocks, then one cross-attention readout per parameter group over every device/net node in that circuit | `none` |

The second encoder's query combines the group's numeric features and parameter
kind, its bound-device representations (including parameter kinds and ratios),
and the goal context. The attention result is added to the query with a residual
feed-forward step. There are no learned device names, topology-sized output
heads, functional-block annotations, or path-distance biases. A critic still
injects each proposed action into its bound devices **before** node processing
and retains it in the group representation. Actor, Q1 and Q2 have independent
weights; SAC, reward, action mapping and parser semantics are unchanged.

The common result remains `(nodes[N,H], groups[G,H], context[B,H])`. SAC batches
store all devices before all nets, so nodes from one graph need not be contiguous.
Attention explicitly packs by graph ID and restores original positions. Padded
keys are masked; only real query positions are returned. Nothing attends across
circuits. Both architectures use `heads`; it must divide `hidden_dim`.

## Structural inputs and cost

Both encoders accept `structural_encoding: none | rwse`. RWSE projects the return
probabilities of walks of lengths **2, 4, 8, 16** into the hidden width and adds
them to the node input. These even lengths suit the device/net bipartite graph.
Walks use the bidirectional terminal multigraph: parallel terminals count
separately, outgoing probabilities sum to one, and isolated nodes have zero
return probabilities. Terminal roles still enter local attention independently.

Only raw CPU structural inputs are cached: an LRU of at most 64 topologies and
32 MiB, including edge-index keys. Keys bind node count, ordered edge indices and
the `terminal-rwse-v1` feature definition. Learned projections and embeddings are
recomputed every forward pass. The structural cache is independent of the
observation cache. Exact RWSE preparation uses a sparse transition matrix and
dense walk states, with quadratic temporary memory. Full global attention has
quadratic node cost; the group readout adds `O(GN)` attention. This implementation
does not provide linear-attention approximations for very large graphs.

## Workbench and checkpoints

In **RL networks…**, choose **GraphGPS — port-aware** or **Parameter-group
attention — experimental**. Each stores its own sizes, structural option and SAC
settings. Both start at **48 hidden / 4 heads / 4 layers**, matching the existing
Graph Transformer starting size, with inherited SAC starting settings. These are
project choices, not published or measured optima for the new architectures.
Operating-point inputs and the component vocabulary remain available.

For the backend/JSON interface:

```json
{"encoder_type": "graph_gps", "hidden_dim": 48, "heads": 4,
 "layers": 4, "structural_encoding": "rwse"}
```

Put this in `run.network` in an ordinary workbench configuration. The existing
workbench CLI and API support scratch, resume, fine_tune and frozen with either
encoder. Loading a saved model restores its architecture settings; switching to
a new architecture requires scratch training. Structural settings and
`architecture_version: 1` are recorded in new-encoder model contracts and checked
before loading weights. Existing encoders retain their previous model-contract
fields and tensor layouts. Default `none` is omitted from legacy configuration
hashes to preserve task identities.

Optimizer source changes invalidate **exact resume** from older source digests.
Use the checkpoint's historical source for that operation. Existing models remain
eligible for inspection and compatible fine_tune/frozen loading under the
existing schema, architecture, dependency and provenance checks. No cross-encoder
weight conversion is performed.

The saved-model structure view includes all global attention, structural-input
and group-readout layers. The circuit graph view distinguishes **Local port
edges**, **Global node attention** (choose the receiving node), and
**Parameter-group attention** (choose a group). Global/group modes color nodes
and list normalized weights; physical connections remain the only drawn edges.
Inspection hooks are installed only for the read-only replay and removed on exit;
they leave the returned policy outputs unchanged. Attention is not a causal
explanation or evidence of generalization.

## Comparison entrypoint

Historical M5/M6 entrypoint files and evidence remain untouched. Use the current
workbench CLI for configured real tasks, or the new **synthetic** comparison
entrypoint. It requires an explicit selection and previews the budget by default:

```bash
python examples/benchmark_encoders.py --encoders graph_transformer graph_gps group_cross_attention
python examples/benchmark_encoders.py --encoders graph_gps group_cross_attention --structural-encoding none
```

`--execute` runs that synthetic protocol. Results go under `<output>/mock/<id>`.
The existing learner-step profiler also accepts both new encoder names via
`--encoders`; its default three-encoder timing selection is unchanged. Follow
`docs/performance-measurement.md` before collecting timing evidence.
The common benchmark runner gives each selected encoder scratch/frozen/adapt
arms, plus random and pattern-search baselines, and records the resolved model
configuration. Historical scripts that use the live encoder registry can now
see five encoders: pass an explicit selection and budget when running them under
current source. Frozen evidence must be revalidated from its historical checkout.

For a meaningful generalization study, compare the same train/validation/held-out
topology splits, seeds and simulation budgets; include structural-input ablations,
parameter counts, runtime and memory. Such a real-simulator study was not run as
part of this implementation.

## Architecture references

- [Rampášek et al., GraphGPS, NeurIPS 2022](https://arxiv.org/abs/2205.12454): the
  local/global/structural framework. GATOR adapts the local branch to port-aware
  circuit messages and uses full multihead attention.
- [Lee et al., Set Transformer, ICML 2019](https://proceedings.mlr.press/v97/lee19d.html):
  query-based attention pooling. GATOR's queries are derived from parameter groups
  and goals rather than a fixed set of learned pooling seeds.
- [Hakhamaneshi et al., 2022 preprint](https://arxiv.org/abs/2203.15913) and
  [ACCFormer, IJCAI 2026](https://www.ijcai.org/proceedings/2026/720) provide circuit
  precedents for attention readout. Neither citation establishes novelty or
  superiority of this parameter-group SAC readout.
