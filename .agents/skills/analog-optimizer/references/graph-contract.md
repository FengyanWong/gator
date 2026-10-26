# Netlist, CircuitGraph and parameter contract

This is an implementation contract proposed for the project, not a schema that already exists in an upstream library.
Check the repository before implementing; adapt compatibly to an existing equivalent model instead of writing a parallel replacement.

## 1. Minimum information in the common graph

Suggested representation: typed data classes or an existing schema library independent of PyTorch/Cadence:

```text
CircuitGraph
  schema_version
  circuit_id / topology_id / source_manifest
  devices: Device[]
  nets: Net[]
  connections: TerminalConnection[]
  parameter_groups: ParameterGroup[]
  context: CircuitContext
  diagnostics: Diagnostic[]

Device
  id / instance_path             # location, not transferable semantic embeddings
  kind / polarity / model_ref    # model_ref is a local mapping key
  raw_parameters / resolved_parameters
  parameter_valid_mask / source_span

Net
  id / hierarchical_name
  roles                         # ground, supply, input, output... record their source
  source_span

TerminalConnection
  device_id / terminal_name / terminal_role / terminal_ordinal / net_id

ParameterGroup
  id / parameter_kind / unit / domain
  value / lower / upper / scale / legal_values_or_step
  members[] / binding_rules / mutable

CircuitContext
  ports / supplies / temperature / corner / analysis_context
  task_features / specification_set / schema_versions
```

`source_manifest` records netlist/testbench digests, PDK mapping version, parser version and input origin.
Redact according to user permissions before public or remote use; do not upload model-file contents as ordinary features.

## 2. Preserve terminal semantics

The first version uses a device-net bipartite multigraph, with terminals represented as connection attributes or relation types.
Do not introduce device/net/port nodes at three levels without a reason; add explicit port nodes only for a defined experiment.

Example MOS relations:

```text
(device, d_to_net, net)     (net, net_to_d, device)
(device, g_to_net, net)     (net, net_to_g, device)
(device, s_to_net, net)     (net, net_to_s, device)
(device, b_to_net, net)     (net, net_to_b, device)
```

- Retain one original connection per terminal, then generate explicitly directed reverse edges for message passing.
- A MOS with S and B on the same ground net still has two distinct connections.
- Preserve actual terminal labels for resistors, capacitors and sources; symmetrize only explicitly symmetric devices.
- Positive/negative terminals of an ideal voltage source are not arbitrary symmetric terminals.
- Device mappings or subckt declarations determine terminal order. Do not assume D/G/S/B merely because an instance name starts with `M`.
- Prefer `global`, declarations, testbench configuration or explicit mappings for GND, VDD and input/output roles; mark the source of any heuristic identification.
- Do not merge same-named local nets in different scopes; merge global nets only under explicit rules.

## 3. Initial Spectre parser scope

First read a small actual user netlist, openly state the supported syntax subset, then write fixture-driven tests.
The first version covers at least comments, whitespace, device terminal lists, parameter assignments, ordinary numbers/units, basic parameters and subckt definitions/calls.

Parsing requirements:

- Retain file/line numbers/raw values after tokenization; a collection of loose regular expressions is not a parser supporting all Spectre syntax.
- State the supported dialect. Dispatch `simulator lang=spice` or mixed-language input to the appropriate parser, or report an error with its location.
- Interpret numeric units according to the declared dialect; do not apply SPICE case/suffix rules indiscriminately to Spectre inputs.
- Use an allowlisted expression parser or retain expressions; never execute input netlist expressions with `eval()`.
- Unresolved expressions are unknown, not 0; resolve required values and bounds before writing real parameters.
- Restrict `include` to allowed directories, handling relative paths, cycles and depth limits; do not recursively expand encrypted/private model files.
- Identify subckt calls from parsed definitions, not instance prefixes alone.
- Hierarchy expansion preserves full instance paths and terminal mappings and distinguishes local/global nets; explicitly reject recursive or unsupported structures.
- Do not expand device-model internals into meaningless large graphs; mapped PDK devices with known terminals can remain atomic.
- Have explicit policies for analyses, save, options, stimuli, DUT and testbench scope; do not silently discard context that affects the task.
- Diagnostics may still be output on parse failure, but incomplete graphs must not be used as validated simulation/optimization inputs.

**Canonical does not mean graph-isomorphism canonicalization is complete.** Sorting names only makes the current input deterministic; it does not guarantee an isomorphism hash after renaming.
Topology splits need explicit topology lineage or verified structural deduplication, not just hashes of text or sorted names.

## 4. Numbers and features

Use explicit units for internal physical quantities; convert lengths, frequencies, power and similar values to common units as appropriate, while retaining definitions and units for metrics such as dB.
Positive sizes may use log-domain normalization; signed values such as voltages use linear or separately defined transforms.

Learning features may include device kind/polarity, current parameters, legal bounds, adjustable masks, net roles and verified operating-point information.
Operating-point features are optional; do not invent real values without OP results.

Represent missing values with finite placeholders and masks; masks are required, and placeholder zero must not mean physical zero.
Fit normalizers on the training set and save them in checkpoints; do not refit on all test results at test time.
Use an explicit unknown/error policy for unknown categories; do not silently expand the semantic vocabulary when loading a checkpoint.

## 5. Parameter groups and action mapping

A parameter group is an independently adjustable degree of freedom, not necessarily one MOS.
One device can have separate W and L groups; one group can constrain equal or ratio-bound parameters of several devices.

```text
group_g → binding 1: device_A.w = g
        → binding 2: device_B.w = 2 * g
```

Every group needs a nonempty legal domain checked against cross-constraints; propagate each binding's legal domain back to the group domain.
Distinguish per-finger width, total width, finger count and multiplicity, using semantics from the local PDK.
Do not assume `W × nf × m` is always correct or expand the same degree of freedom twice.

Bias/global parameters outside device bindings need explicit objects and association locations; do not put them into "the last fixed action dimensions".
Fixed or derived parameters do not create independent stochastic actions; report dependency cycles and contradictory constraints as errors.
Write actions back through auditable ID mappings, independent of input row order.

## 6. PyG conversion

`HeteroData` stores distinct node/edge types and is one preferred representation for this project; see [S4](sources.md).
Do not restructure a validated homogeneous typed graph merely to "use PyG".

The conversion function returns or retains:

```text
pyg_graph
node_id_maps / terminal_relation_vocabulary
parameter_group_index / member_bindings
feature_schema / masks / per_graph_context
```

Requirements:

- Define type vocabularies and feature dimensions in advance; output valid empty tensors when an edge type is absent instead of changing schema unpredictably at batching time.
- `edge_index` uses integer indices and floating-point features use a consistent dtype; validate index bounds per type.
- Do not casually discard multi-terminal information through edge coalescing; relation-semantics tests must establish whether merging is valid.
- Batch/unbatch restores parameter groups and device bindings; check PyG offset behavior for custom indices.
- Dense attention masks both padding within each graph and boundaries between graphs, preventing samples from attending to each other.
- Structural caches reuse connections only for the same topology/version; size changes refresh dynamic features.

### Current training-input cache

`SACLearner` enables two CPU LRU levels by default: 8192 complete-observation inputs (since 2026-10-06, record 7.221; previously 2048, with an additional 256 MiB tensor-byte cap), and 64 static topology templates. All encoders (six then, only GT/RGCN/GATv2 since 2026-09-26) use the same mechanism, owned separately by each learner; caches are neither learned weights nor raw replay records.

- `TopologyTensorCache` reuses kind/net roles/forward and reverse terminal edges/ordinal/group bindings/mutable. Changes to ordered nodes, edges, groups, relations, bindings or schema invalidate it. `to_pyg(..., topology_cache=cache)` still validates and refreshes dynamic sizes, masks, group domains and provenance/writeback metadata every time.
- `ObservationTensorCache` reuses complete raw inputs, context and group features. Its key is a local content digest of the complete Observation and FeatureSchema/SpecSchema, covering sizes, targets, measurements/masks, budgets, status, origin, conditions and provenance, not just object addresses or job IDs. Since record 7.221, the key is a schema digest (memoized by (FeatureSchema, SpecSchema)) + the complete observation content digest (`observation_digest`): replay's learning path `ReplayBuffer.update_learner` borrows uncopied transitions and passes the digests of both observations, computed once per stored transition; other callers (`act()`, and `update()` after public `sample()`) compute full digests each time. Equal-content observations, including deep copies, hit the same entry; PDK views (`PdkViewLearner`) generate new objects and use their own content digests. Names support indexing and writeback consistency only; they are neither learning semantics nor proof of graph isomorphism.
- `batch_observations(..., cache=cache)` builds a new batch, adjusts indices and copies opaque metadata each time; caller changes to returned tensors or metadata must not contaminate the cache. Static templates return independent tensors externally.
- Capacity is counted in entries (with an optional `max_bytes` byte cap; `info()` also reports eviction counts and tensor bytes), with LRU eviction above the limit. Set both capacities to 0 to disable caching; use `learner.input_cache.info()/clear()` to inspect/release it. Conversion can repeat after eviction/restart; there is no indefinite "convert only once" promise.
- Do not cache embeddings, attention, Q, actions or gradients; run network forward/backward with current parameters each time. Operators with adjacency caches must disable caching across batches (the removed GCN encoder used `GCNConv(cached=False)`) so mixed topologies cannot reuse the previous batch's adjacency. Caches are not saved in checkpoints; cold recovery rebuilds them as needed and the next training step must match exactly.
- Retain real-candidate parameter readback, netlist export/parsing and consistency checks; this is not a simulation-result cache. Record conversion-stage timing separately from full SAC updates; do not present training acceleration as Spectre or end-to-end acceleration.

The project's `docs/input-tensor-cache.md` records interfaces, reproduction commands and acceptance. Tests must cover invalidation after content changes, mixed batches, isolated return values, finite capacity and training equivalence with caching on/off across six encoders.

### Current M1 neural-network views

Original `to_pyg()` retains HeteroData; ordinary operators use `graph.neural.to_homogeneous_pyg()`, and existing single-graph HeteroData can use `as_homogeneous()`. No RL Observation is needed. Default `circuit-neural-v1`:

- `x[N,49]` float32: node type one-hot(2), device kind one-hot(8), 8 columns each for parameter value/valid/present/adjustable, net role(7). Use `node_feature_slices(schema)` for columns; the width is `2 + K_device + 4P + R_net`, independent of graph size. Fill inapplicable device/net fields with finite zeros and retain explicit type/missing masks; do not mix parameters from original device.x and roles from net.x in the same columns.
- `edge_index[2,E]`, `edge_type[E]` and `edge_ordinal[E]` are int64. Relation IDs are `2 * role_id + direction` (0=device→net, 1=net→device); do not merge forward/reverse or parallel terminals. `edge_attr[E,15]` is relation one-hot + log1p(ordinal), and `edge_weight[E]` holds unit weights. Terminal-category IDs are not continuous GCN edge weights.
- GCN consumes x/index/weight, RGCN x/index/type, GAT/GT x/index/attr; MLP processes only node features and reads out by group. Ordinary GCN deliberately ignores terminal labels, but the original graph retains all terminal information. (These are general PyG operators; the optimizer's encoders have been GT/RGCN/GATv2 only since 2026-09-26, synchronized 2026-09-30.)
- Convert single graphs first, then use `batch_homogeneous([data,...])` for graph-contiguous node batch/ptr and group_x_batch/ptr. Offset the first row of group bindings by G and the second by the full graph's N; members must be devices. Reject cross-graph edges/bindings and mixed-schema batches.
- `dense_node_features()` returns `[B,Nmax,F]` and a `[B,Nmax]` boolean mask without truncating nodes. Padding creates no actions; attention/pooling must use masks. This does not make a fixed-length flattened MLP a general-topology model.
- SAC retains its existing learned projections by type and group normalization, sharing only terminal-edge packing through `port_edge_tensors()`. Its all-devices-then-all-nets ordering differs from the export batch's per-graph ordering; do not interchange indices.

Acceptance includes direct PyG operator forward/backward passes and agreement between single/mixed batches, S/B on the same net, empty graphs/zero groups, missing versus real zero values, dense masks, reordering, dynamic-feature refresh and actual exported-netlist snapshots. Fields, commands and latest evidence are in the project's `docs/m1-neural-inputs.md`; successful export does not establish real circuit transfer.

## 7. Required tests

1. MOS D/G/S/B, S and B on the same net, multiple terminals on one net and reverse-edge consistency.
2. Repeated local net names in hierarchies, subckt terminal mappings, include cycles, mixed-language rejection and unknown-device diagnostics.
3. Units, expressions, missing values, legal parameter groups, binding-domain conflicts and integer-projection boundaries.
4. Correct recovery before/after batching two graphs of different sizes/parameter counts, with no cross-graph edges.
5. Renamed/reordered fixtures preserve structural equivalence and correct writeback mappings; never pass these tests through name embeddings.
6. At the model stage, compare parameter-group outputs and graph-level Q before/after permutations in eval mode; for stochastic policies, compare distribution parameters or controlled random samples.
