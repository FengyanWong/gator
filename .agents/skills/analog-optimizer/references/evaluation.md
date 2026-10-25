# Experiments, generalization and technical review

This file defines how to obtain interpretable evidence; it does not claim that one architecture must outperform another.

## 1. Ask four different questions separately

| Experiment | Difference between training and testing | Supported conclusion |
|---|---|---|
| New specifications on the same topology | The same circuit connections, different targets or operating conditions | Generalization through specification conditioning |
| New topology within a category | For example, new LDO connections/parameter scale | Structural transfer within a category |
| Across circuit categories | Changes between LDO, VCO and OpAmp | Transfer only within the categories and protocol covered |
| Across PDKs | Different device models and legal domains | Separately defined process transfer, outside the first version's default scope |

Renaming the same circuit, reordering instances or randomly initializing parameters does not create a new topology.
A common graph's support for variable sizes does not establish effective generalization of the optimization policy.

## 2. Leakage-prevention protocol

- Freeze topology lineage, specification distributions, testbenches and train/validation/test manifests before training.
- Use explicit topology-family labels and structural deduplication checks; filenames or raw netlist hashes alone do not prevent leakage.
- Normalizers, vocabulary selection, surrogates, offline replay and hyperparameter selection all follow the split.
- Define and report before the experiment whether a slight modification of the same base circuit counts as unseen.
- Validation may select hyperparameters; do not repeatedly tune on test data and still call it unbiased testing.
- Give baselines the same testbenches, legal parameter domains, starting-point rules, specifications, corners, accuracy and stopping conditions.
- Do not hide parallelism, CPU threads, GPUs, licenses or pretraining data within "algorithm differences".

## 3. Zero-shot and adaptation

**Zero-shot policy**: no weight updates or test-set statistics fitted from test-circuit data. If initial measurements or multiple online queries on the current circuit are needed, those real simulations still count.
Further distinguish "generate parameters once" from "multiple optimization steps with a frozen policy"; do not call both simulation-free zero-shot.

**Few-shot / online adaptation**: test-circuit simulation and learning are allowed within a fixed budget; report the budget, what is updated, initialization and whether subsequent experience is retained.

**From scratch**: start from a random model/no pretraining with the same online budget.
Record order dependence when experience accumulates across tasks; later-tested tasks must not receive undeclared extra knowledge.

## 4. Baselines and ablations

First establish reproducible random search, then choose a suitable non-RL optimizer (such as CMA-ES, CEM or BO) according to available code.
Choose based on parameter domains, budget and maintainability; the first version need not implement every algorithm at once.

The project currently implements random search and coordinate pattern search. The user-requested encoder controls are compared through a common SAC interface (synchronized 2026-09-30: only the three encoders below remain;
node-wise MLP, topology-only GCN, GATv1 and M5's port-aware message-passing GNN were removed; historical results retain their own records):

```text
port-aware Graph Transformer + SAC       # main approach
port-relational RGCN + SAC               # role × direction relations
port-aware GATv2 + SAC                   # GATv2Conv dynamic attention with terminal edge features
scratch / frozen / adapt                 # all three modes for every explicitly selected encoder
```

When `--encoders` is explicit, pretrain each architecture independently and perform frozen validation diagnostics. Without it, run only the three `graph_transformer` modes plus random search and coordinate pattern search (the default in `examples/benchmark_transfer.py`; the M5 six-method set includes the removed port-GNN and runs only at source commit bbdfe36). Fix splits, specifications, legal action domains, seeds, pretraining/online budgets and update rules; policies may collect different candidates, so equal budgets do not imply identical datasets.

`scratch` uses random initialization; `frozen` copies and freezes same-architecture weights and performs multiple evaluation steps with the mean policy; `adapt` copies same-architecture networks/alpha but creates new optimizers and empty replay. Each test task is independent and its data does not feed back into the source model. Current validation is diagnostic only and does not select models or hyperparameters.

Compare each architecture's frozen/adapt modes against its own scratch mode first, then compare architectures; retain random and non-RL controls. Report actual actor+Q1+Q2 parameter counts, pretraining and online costs; equal width/depth is not matched parameter count. Calculate the budget from the selection matrix and reject an over-budget request before creating a backend; switching encoders does not automatically increase the real simulation budget.

A flattened fixed-topology MLP or the user's old DDPG/RGCN is a separate reference and must not be confused with the current shared RGCN-SAC (or the removed node-wise MLP-SAC); explain action-dimension and optimizer differences. Further ablations of terminal semantics/specification conditioning still need separate implementation and acceptance.
TD3, surrogates, global attention, gated residuals, extra OP features and parallel sampling are separate later ablations.
After changing several factors at once, do not attribute every improvement to one new module.

The 2023 Li work and DEGT are related work requiring verification. Before reproduction, confirm the specific paper, open-source version, actual training/testing protocol and authorization; do not invent paper details from earlier chats.
Do not claim "first", "outperforms" or "fully reproduced" before reading the original text/code.

## 5. Minimum reporting requirements

| Category | Metrics |
|---|---|
| Meeting specifications | Fraction meeting every required spec, failure categories, valid-design fraction |
| Sample efficiency | Real simulation calls before the first pass, best-so-far quality under a fixed budget |
| Time efficiency | time-to-first-feasible, total wall-clock time, throughput, time per stage |
| Quality | Every raw physical metric, worst violation, secondary objectives, Pareto results where applicable |
| Cost | Pretraining, tuning, warm-up, failures, retries, corner/analysis counts and parallel resources |
| Stability | Multiple independent random seeds, distribution across test circuits, intervals and individual cases |

Define whether "one call" in the simulation budget means one analysis, one corner or a complete candidate test package; retain both underlying call counts and candidate-evaluation counts.
Do not count cache hits as new simulations, or omit warm-start data and actual failed calls from costs.

The optimizer package only reserves a fixed 5-corner post-validation interface for the nominal top 3 (workbench Corner check resimulates the 1-3 best designs under 5 conditions); it does not run all combinations. First deduplicate actual executed parameters by nominal reward and freeze top-k, then perform post-validation. Do not use later PVT results to reselect nominal top-k or mix them into training (OTA7's explicitly selected training conditions under reward v2 / v2.1 are separate; see [Conditions and statistical validation](pvt-monte-carlo.md)). The denominator of `pass_rate` is all configured corners; unknown results mean no complete pass rate. For min/max/range, report the worst metric and corresponding corner in the constraint's direction. Calculate robust_score only with complete results; any known failed corner disqualifies a pass.

These five corners select candidates and are validation, not independent test data. Future repeated tuning against them still needs independently held-out validation conditions/statistical seeds before reporting generalization or yield. MC sample pass rates, corner pass rates and real manufacturing yield are different metrics. More budget rules are in [Conditions and statistical validation](pvt-monte-carlo.md).

A run that does not pass within budget is unsuccessful/right-censored; do not remove it from time-to-feasible means or pretend the budget endpoint is its success time.
When reporting time conditional on success, also report success rates and censoring rules.
The seed count for formal experiments depends on budget; explicitly label a single run as a pilot and do not conclude stable superiority.

## 6. Is transfer worthwhile?

Show separately:

```text
online savings per task
upfront training + hyperparameter-search cost
number of tasks needed to recover upfront cost (when measurable)
```

Do not report only that each test task is faster after fine-tuning without stating how much pretraining Spectre data it required.
Report both the marginal cost of reusing a trained model and the total cost of building the system from scratch if useful.
If cross-category transfer fails, diagnose inconsistent specifications/measurements, data distributions, representations, action domains or algorithm limits; a larger replacement model is not a substitute for diagnosis.

## 7. Review / grill checklist

Attach code locations, data or missing evidence to each question and provide a concrete test:

1. **Terminals and topology**: does changing D/G/S/B connections change the features actually passed to the model? Does reordering IDs preserve output equivariance?
2. **Actions and Q**: can different group counts be batched? Are actions bound to the correct devices? Can actor gradients flow back through Q?
3. **Reward**: are failure to oscillate, missing measurements, non-convergence and license failure distinguished? Can success bypass required specifications?
4. **Simulation authenticity**: do writes take effect? Do repeated candidates use the correct cache entry? Did the testbench or corner change unexpectedly?
5. **Generalization**: are test topologies merely renamed? Did test data enter replay, the normalizer, a surrogate or tuning?
6. **Fairness**: does model improvement come from more data/resources, wider bounds, different stopping conditions or excluded failures?
7. **Engineering benefit**: where is the bottleneck? Does training overhead consume the simulation savings? Does recovery preserve the complete learning state?

Review does not require installing `brainstorming` or `grillme`, and it does not mean copying those third-party skills' content.
