# Optimizer package

The `analog_optimizer` package provides circuit graphs, legal parameter actions, simulator adapters and graph SAC.
The browser and its saved-task workflow live in the separate [workbench](workbench.md).
These contracts describe the source at the readability plan's base, `18fe81e` (2026-10-25).

## Package map

| Package or module | Responsibility |
|---|---|
| `backends/` | The backend interface, explicit synthetic providers, real bridge adapter and circuit profiles. |
| `netlist/` | Source-located Spectre parsing, guarded arithmetic and model/port mappings from configuration. |
| `graph/` | Circuit data classes, parameter groups, heterogeneous PyG and fixed-semantics homogeneous/dense views. |
| `parameters/` | Normalized proposals mapped to legal physical values with bounds, grids and integer domains. |
| `measurements/` | Measurement readers, units, validity, specification evaluation and reward. |
| `envs/` | Candidate evaluation, episode state, failure handling and recovery. |
| `evaluation/` | Task splits, transfer and benchmark protocols, costs, and top-k/corner summaries. |
| `models/` | Feature/spec inputs, graph encoders, parameter-group actors and action-conditioned critics. |
| `training/` | Replay, SAC updates, serial/parallel collection and checkpoint recovery. |
| `recording/` | SQLite records, static assets, dynamic transitions, capacity control, checkpoints, queries and exports. |

The parser, graph data classes and `MockBackend` use the standard library. PyG and learning dependencies are optional;
the [installation instructions](../README.md#start) install the extras needed by the workbench and its tests.
The four [synthetic netlists](../tests/fixtures/synthetic/) exercise the same parser. Evidence-pinned configurations,
example scripts and fixtures must not be edited, moved or reformatted; see [CLAUDE.md](../CLAUDE.md).

## Backends

`MockBackend` exports an immutable fixture into a unique job directory with its digest and provenance. It returns
only explicitly supplied test metrics and status, marks results `origin=synthetic` and `candidate_evaluated=False`,
and rejects candidate parameter execution. Missing or invalid values remain unavailable, with validity masks;
infrastructure, convergence and measurement failures have separate statuses. Unsupported capabilities raise explicitly.

`SyntheticSizingBackend` evaluates a bounded quadratic score of executed normalized group values. It is an analytic
toy backend for learning-interface tests and does not calculate circuit metrics. Neither backend silently replaces
a failed real simulation. The real adapters use the existing Virtuoso bridge; the package's backend methods are
its own interface, not a claim about the upstream bridge API.

## Spectre dialect

- The parser accepts native Spectre, optionally declared by `simulator lang=spectre`, and preserves case. It reads
  whitespace, `//` comments and backslash-newline continuations.
- Instances have `instance (nets ...) model parameter=value ...` form. Configuration supplies each model's terminal
  order and roles; an instance-name prefix does not decide its device type.
- Numeric suffixes are `T G M K k m u n p f a`, with distinct `M` and `m`. Arithmetic supports forward parameter
  references, `+ - * / **`, parentheses and quoted/braced expressions through a bounded AST whitelist. Unknown symbols,
  cycles, function calls, unsupported suffixes and non-finite results remain unresolved.
- Subcircuits accept parenthesized or bare formal ports, internal parameter defaults, nested calls and declared
  overrides. Recursive calls, nested definitions and undeclared overrides are refused. Explicit model mappings take
  precedence over subcircuit expansion.
- Globals come from `global` statements and configuration, with `0` the default. Hierarchical local nets get full
  instance paths. Net roles come from configuration rather than guessed supply names.
- Includes expand only plaintext structure files within configured `include_roots`. Real paths, traversal, cycles and
  depth are checked; includes are disabled by default. Model sections and encrypted PDK content are not parsed.
- Top-level `save` and named `dc/ac/tran/options/info` statements remain source-located context, without execution.
  Selecting a top subcircuit retains that context. Balanced bracket values such as PWL `wave=[...]` are retained as
  unresolved expressions; the parser does not evaluate waveforms.

Mixed/SPICE dialects, bare instance-port lists, plus-line continuations, star/block comments, escaped identifiers,
conditional/statistical statements and model definitions are outside this subset. Unsupported active structure
raises a source-located `ParseError`; this is not a general Spectre or PDK-model parser.

An unknown model retains its device and ordinal connections, adds an error diagnostic and makes the graph incomplete.
Unresolved values retain raw tokens, source and reason with a missing numeric value. Structural completeness does
not establish simulability or resolve every parameter; optimizable parameters must resolve on known devices.

## Graph and parameter contract

- Static devices, nets and terminal connections are separate from dynamic parameter values. MOS drain/gate/source/bulk
  connections remain distinct even when terminals share a net; PyG has separate forward and reverse role edges.
- Configured groups define the independent parameters, positive-ratio bindings, bounds, grids, mutable flags and
  linear/log scales. Group/member conflicts are rejected. `assignments` returns flattened instance IDs and original
  parameter names; it does not write a netlist or schematic or infer freedom from shared expressions.
- `FeatureSchema` fixes kind, role and parameter vocabularies and reference scales. Unknown categories fail rather than
  growing the vocabulary; every relation has a tensor, including an empty edge index with shape `[2, 0]`.
- `device.kind` holds category indices; numeric features use the signed `log1p` of magnitude divided by reference.
  Presence, validity and optimizability masks distinguish zero, missing, unresolved and adjustable values. Instance
  names and model references stay in metadata.
- The separate group table has physical `[value, lower, upper]` values in float64, group/device binding indices,
  parameter IDs and ratios. Units, domains and steps remain in metadata; existence and mutability masks are separate.
  `CircuitHeteroData` offsets groups and devices independently when batching. Graphs in a batch share a feature schema.
- The canonical graph is a data contract. The evaluation package separately checks exact port-incidence graph
  isomorphism for split leakage, ignoring names and sizes. The [neural-input reference](m1-neural-inputs.md) describes
  homogeneous and dense views of the same contract.

Current source: [graph classes](../src/analog_optimizer/graph/circuit_graph.py),
[PyG conversion](../src/analog_optimizer/graph/pyg_converter.py),
[Spectre parser](../src/analog_optimizer/netlist/spectre_parser.py),
[arithmetic](../src/analog_optimizer/netlist/expressions.py), and
[parser configuration](../src/analog_optimizer/netlist/config.py).
Historical single-circuit permissions and experiment claims remain in [README history](history-readme-milestones.md);
current saved-task permissions belong to the workbench. Monte Carlo execution and surrogate extensions are not
implemented by these contracts.
