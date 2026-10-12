# CircuitGPS: joint circuit, specification and parameter encoding

Built on 2026-10-12 at the user's request, after an architecture review. Encoder
ID **`circuit_gps`**, architecture version **1**, spec layout **`spec-program-v1`**.
This implements a representation intended for transfer; it is not evidence of
better optimization or a mathematically optimal encoder. No ablation campaign or
real simulation was started for this change.

## Select and use

In **RL model → New model → Templates**, select **CircuitGPS — joint spec and
parameter attention**. The template selects Structured spec inputs and keeps the
chosen physical inputs. **Structured + Transferable 2** also selects PDK-relative
sizes, model features, bench features, rule-based net roles and operating-point
ratios; it requires the task's PDK data, like Transferable 2. The ordinary
Structured option works without PDK data and leaves operating-point acquisition
under its existing switch. The default encoder for other/new configurations is
still Graph Transformer. Existing tasks and saved settings are not rewritten.

A minimal workbench network block is:

```json
{
  "encoder_type": "circuit_gps",
  "hidden_dim": 48,
  "heads": 4,
  "layers": 4,
  "structural_encoding": "rwse",
  "spec_input": "structured"
}
```

These sizes and inherited SAC defaults are starting choices, not a measured
optimum. Offline pretraining accepts the same encoder in `model` and
`inputs.spec_input: structured` (the default when that model ID is requested).
Each source archive is viewed with its own task's measurement programs. Raw
operating-point availability and the existing missing-points policy still apply.
Changing architecture requires a new model; weights from another encoder are not
silently transplanted.

## Representation

The circuit remains a device–net bipartite terminal multigraph. Node kinds,
parameter values/presence/validity/optimizable masks, net roles, and optional raw
operating points retain the existing feature schema. Every terminal direction
and parallel connection is preserved. Instance, net, group and spec names only
resolve addresses; none is embedded as a categorical identity.

Every active specification retains its own token. The existing set state/unit/
descriptor columns are followed by **scale magnitude, absolute weight, signed
lower margin and signed upper margin**. Separate validity and bound-presence
flags distinguish a missing measurement from zero and a missing limit from zero.
Both margins use the spec's reward scale. Scale is explicit even at zero margin.

`spec_programs` metadata holds an ordered measurement tree per spec:

- Analysis, probe units, arithmetic and distinct measurement operators (including
  rise/fall, max/min, average/RMS), constants, window endpoints, threshold and
  crossing direction remain distinct.
- Spec equations expand their referenced probes; subtraction, division and
  nested expressions preserve operand order. AC excitation sources form an
  unordered set, so renaming them cannot change their meaning.
- Voltage leaves bind to nets and their explicit or canonical-ground reference;
  current leaves bind to devices and supported
  terminal roles; xf sources bind as excitation; size formulas bind their
  declared patterns to the same variable-width instances as the evaluator.
- Constants have signed `log1p` and log-magnitude channels, with an explicit
  numeric mask. Leaves report requested bindings and their resolved fraction.
  Unsupported expressions/results are **explicit unknown tokens**, and unknown
  addresses remain unresolved rather than being guessed from spelling. Built-in
  analyzer results with no inspectable expression also carry an unknown token.
  This parser is a bounded supported OCEAN subset, not a full SKILL interpreter.

Parameter tokens include semantic parameter kind, current value, bounds, domain,
grid, mutable flag, normalized position in the legal linear/log domain, and
member count. Their device memberships include parameter kind and binding ratio.
When the feature schema enables operating-point input, structured inputs also
carry masked gm/Id, gm/gds, overdrive, saturation headroom and Vds/Vdsat. Zero
denominators and missing/non-finite inputs are invalid, not fabricated zeros.

Conservative hierarchy tokens describe shared-source transistor pairs, diode-
connected mirror motifs and parameter ties. A shared-source motif is **not** a
verified differential amplifier. Known gain-stage, bias and compensation groups
can be supplied in graph metadata `functional_blocks` as `{kind, members}` with
explicit device members. No LLM or name-based function classifier runs in training.

## Computation and SAC

Each block combines port-conditioned local attention and global node attention
using separate learned channel gates and one residual. Global attention has
learned device–net distance bias (0–8 hops, with a separate disconnected bin) and
direct terminal/direction bias. Optional RWSE uses the existing 2/4/8/16 returns.
Neither structural input is a positional embedding of an arbitrary node number.

Inside every block, specs query nodes, nodes query specs, parameters query nodes
and specs, nodes query parameters, and specs and parameters each self-attend.
Relations have separate projections and Pre-LN gated residuals. The measurement
tree is recomputed bottom-up with current bound-node embeddings, and specs send
messages back through their explicit bindings. Motifs exchange messages with
their members and attend over their own circuit. Parameter membership messages
are refreshed every block, not only at a final pooled readout.

The shared actor head still returns μ and log-std per independent active group.
Each critic injects its proposed action into its parameter token **and bound
devices before processing**. Actor, Q1 and Q2 have separate weights. Context
readout combines attention, separate sums for nodes/groups/specs/motifs and their
counts. The common `(nodes, groups, context)` interface and shared SAC heads,
proposal-action semantics, legalizer, reward and entropy computation are intact.

All attention is circuit-isolated; interleaved device/net batches, padding and
variable numbers of specs/parameters are supported. Empty optional token sets
use a run token as an attention fallback. The environment's requirement for at
least one active hard spec remains unchanged.

## Storage, cost and compatibility

Program tensors, bindings, motif membership, physical features and legal-domain
coordinates are raw inputs counted in the bounded observation cache. Changing
an expression, binding, spec scale or operating point invalidates that input.
No learned embedding is cached. A separate distance cache has limits of 64
topologies and 32 MiB, including keys; RWSE retains its existing bounds.
Global attention and distance preparation have quadratic storage; joint attention
adds node/spec/parameter interactions. Measurement trees are limited to 4,096
nodes per observation and depth 64. This is intended for sizing graphs, not a
linear-memory whole-chip encoder.

The new architecture/spec contracts are saved, checked and restored by the
workbench, including offline publication and the model chooser. The structure
inspector describes the new layers; the graph inspector exposes every block's
local, global and parameter-to-node attention. These weights are not causal
explanations. Low-level CircuitGPS also accepts legacy slot/set batches for the
common optimizer API; those lack measurement programs and hierarchy. Workbench
CircuitGPS requires Structured inputs, and older encoders reject that schema.

The five existing encoders retain their tensor layouts and input calculations.
The optimizer source digest changes because new source was added. Existing
retained models can still fine-tune/evaluate under the usual compatibility
checks; **exact resume of a pre-change checkpoint requires its historical
runtime**. There is no exception to the source-digest gate.

Behavioral tests cover the formerly colliding spec-to-node assignments, explicit
scale, operand/operator/constant sensitivity, renaming/permutation equivariance,
batch isolation, action gradients, missing values, cache isolation and exact
next-update restoration for a new checkpoint. A complete MOCK workbench run,
saved structure/attention inspection, offline pool reconstruction and the two
affected browser checks exercise the integration.
