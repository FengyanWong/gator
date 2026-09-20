# M6: cross-category protocol and offline acceptance

M6 has started. This first increment makes OpAmp/LDO/VCO category holdout executable and auditable. It uses synthetic structures and analytic toy objectives; it does not establish electrical transfer performance. M5's real OTA results remain separate.

## Experiment contract

`TransferTask.circuit_class` explicitly identifies the category, while `family` identifies topology lineage. The new `category` transfer mode is test-only. Every task in a category experiment must declare its class. The held-out class cannot appear in training or validation, and changing class/family labels cannot disguise an identical port-aware topology. Existing within-family specification/topology protocols retain their M5 rules.

The default suite freezes three folds before the first evaluation:

| Training and validation classes | Held-out test class | Test actions |
| --- | --- | ---: |
| LDO, VCO | OpAmp | 2 |
| OpAmp, VCO | LDO | 1 |
| LDO, OpAmp | VCO | 3 |

Each encoder/seed/fold starts a fresh source learner and replay. Source tasks run sequentially in the order saved in the protocol, sharing that learner and replay across the two training classes. Validation runs the frozen source policy with separate specification targets. The held-out task gets independent scratch, frozen and adaptation runs; adaptation copies only same-architecture weights and temperature, with new optimizers and empty replay. There is no transfer of data or weights between folds.

This uses the existing serial multi-environment training path. It does not add concurrent heterogeneous workers or claim a scheduling speedup. Replay sampling is uniform over stored transitions; it does not guarantee equal category counts in every minibatch. Source order and class coverage are recorded for later sampling ablations.

All six encoders run the same matrix: Graph Transformer, MLP, GCN, RGCN, GAT and port-GNN, each with scratch/frozen/adapt, plus random search and coordinate pattern search. Width/depth are common, with actual parameter counts reported; models are not parameter-count matched.

## Fixtures, actions and metrics

[The manifest](../configs/m6_cross_category.json) freezes mappings, target functions and train/validation/test goals. [The VCO mapping](../configs/vco.json) adds three independently adjustable stage widths to the existing ring-like fixture; each stage binds its PMOS width to twice its NMOS width. This is an offline action contract, not authorization to modify a real oscillator.

Every backend computes a quadratic score from the *executed* normalized group values, then applies a declared affine transform. Distinct `toy_opamp_quality`, `toy_ldo_error` and `toy_vco_window` identities exercise minimum, maximum and range constraints. All use unit `fixture`; none is gain, regulation, frequency or phase noise. The LDO-like structure has no validated regulator loop, and the VCO-like structure has no validated oscillation test.

The M6 specification registry is supplied explicitly to the benchmark and saved in each checkpoint. It is fixed before training; measurements for inactive classes remain masked. Its identities and reference scales are schema knowledge, not fitted held-out statistics. The source model has never trained on the held-out metric slot; successful tensor handling does not imply it learned that metric's meaning. The default M5 registry is unchanged. Checkpoints must match their architecture, registry, source digest and dependencies; earlier checkpoints are not silently upgraded.

## Running and auditing

```bash
# No evaluation or output directory: validate the complete suite and call ceiling.
/tmp/analog-optimizer-venv/bin/python -B examples/benchmark_cross_category.py --dry-run

# Three held-out classes, six encoders, three seeds; 1,656 analytic evaluations.
/tmp/analog-optimizer-venv/bin/python -u -B examples/benchmark_cross_category.py

# Small end-to-end run: 360 analytic evaluations.
/tmp/analog-optimizer-venv/bin/python -u -B examples/benchmark_cross_category.py \
  --seeds 17 --pretrain-steps 2 --test-steps 2 --max-calls 360

# Audit trusted locally generated artifacts; no new backend evaluations.
/tmp/analog-optimizer-venv/bin/python -B examples/audit_cross_category.py RUN_DIRECTORY
```

`--heldout` and `--encoders` select subsets. `--max-calls` applies to the whole suite, including all selected folds and seeds, resets, source training and validation. An excessive plan is rejected before environment construction. Partial failures retain per-fold reports and completed-call accounting; there are no automatic retries. The entrypoint runs one worker and writes JSON records and complete checkpoints. It does not expose a real mode or automatically load the OTA bridge configuration.

The suite protocol freezes all tasks, objective configuration, fixture/model mapping hashes, source digest, seeds and budgets before any fold runs. Each fold saves candidate records, restoration evidence, per-method outcomes, time and call costs, parameter counts and checkpoints. The audit independently recomputes toy metrics and rewards from executed parameters, verifies replay membership and source-class coverage, checks frozen/copied weights, and probes the next SAC update twice from each checkpoint.

## Acceptance results — 2026-09-19

The full repository regression passed **454 tests, zero failures and zero skips** on the existing CPU environment. The only warning was an upstream TorchScript deprecation notice. [JUnit results](../artifacts/local/m6-cross-category-tests.xml) include the existing M1–M5 tests and the new class holdout, global budget, metric mask, mixed 1/2/3-action batch, six-encoder checkpoint recovery and source/target replay isolation checks.

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest -q \
  --junitxml=artifacts/local/m6-cross-category-tests.xml
```

The default suite completed all three folds with seeds 17/29/43, six encoders and 20 methods per target: **1,656 synthetic evaluations, 702 training updates and zero real Spectre calls**. Each source task and test run used four candidate steps plus reset; validation used one step plus reset. All 396 environments restored, with no failed evaluations, retries or cache hits.

| Cost across the suite | Evaluations |
| --- | ---: |
| Source training | 540 |
| Frozen source-class validation | 216 |
| Held-out tests | 900 |
| Total | 1,656 |

The model uses 32 hidden channels and two layers (four attention heads where applicable). Actor + Q1 + Q2 parameter counts are GT 100,484; MLP 67,172; GCN 73,892; RGCN 153,764; GAT 82,052; port-GNN 87,812. These counts include the M6 toy specification registry, so they differ from M5's physical metric registry. The suite took 297.38 seconds on this CPU environment while the regression suite also ran; this is not a speed comparison.

Evidence: [suite report](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/report.json), [frozen suite protocol](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/suite-protocol.json), and individual [OpAmp](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/opamp/report.json), [LDO](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/ldo/report.json), [VCO](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/vco/report.json) reports. Per-method toy success rates, right-censoring, best metrics/parameters, first-feasible calls/times and pretraining/online costs remain in those reports; they do not establish an electrical optimization ranking.

The [independent audit](../artifacts/local/m6-cross-category/431b381ae54a47e280e52029a5c79e10/audit.json) passed for all **1,656 evaluations and 162 checkpoints**. Both source classes were present in every source replay, held-out replay stayed task-local, frozen weights were unchanged, and every checkpoint reproduced the next sampled update's losses and weights exactly. Audit probes ran only in memory and are excluded from the 702 experiment updates. A [machine-readable acceptance summary](../artifacts/local/m6-acceptance-summary.json) links the regression and experiment evidence.

## Later increments and closure

The [real LDO baseline increment](m6-ldo-baseline.md) now qualifies native CDF/export/readback, two bounded width actions, DC/AC/load-step measurements, failure classification, environment integration and full restoration. It used 12 real Spectre calls including one retained measurement failure; 11 evaluations were valid. This is circuit qualification, not a real transfer experiment.

The [real VCO qualification](m6-vco-baseline.md) is also complete: 13 valid Spectre evaluations, three independently writable stage widths, sustained-oscillation checks at three control voltages, a tighter-timestep comparison and full restoration. It uses explicit initial conditions and does not claim noise-driven startup or phase-noise validation. The latest regression covers 495 passing tests, with eight local-IPC tests rerun outside the socket-restricted sandbox.

The subsequent [VCO runtime qualification](m6-vco-runtime.md) reduces candidate evaluation time to about 6 seconds and brings prior M6 real qualification cost to 38 calls. The [physical pilot protocol](m6-real-protocol.md) now freezes 23 metric identities, all three class holdouts, six encoders, three seeds and a complete 2,811-call ceiling. Preparation and protocol verification made no new real calls. The frozen comparison has since been [executed and audited](m6-real-results.md), and a [strict requalification](m6-vco-requalification.md) has confirmed the first feasible design of all 36 successful VCO runs with the reference deck. Previously observed qualification data are disclosed, so these circuits are not blind holdouts. Heterogeneous concurrent sampling, PVT/MC execution, surrogate models, global attention and expanded real parameter domains remain separate extensions. M6 was closed at pilot scale on 2026-09-20; see the closing entry in [project decisions](decisions.md). These extensions were not started and are not part of that closure.
