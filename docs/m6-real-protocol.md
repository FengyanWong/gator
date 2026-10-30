# M6: frozen physical cross-category pilot

The current configuration (2026-09-26) retains only Graph Transformer, RGCN and GATv2. The `gatv2` entry uses fresh GATv2 weights, not the archived GATv1 models. It plans 1,488 calls and must be frozen as a new protocol before any authorized execution. The original six-encoder, 2,811-call pilot remains archived in [physical pilot results](m6-real-results.md); its evidence is unchanged. Preparing or checking a protocol performs no bridge connection, Spectre evaluation or learner update.

The [manifest](../configs/m6_real_cross_category.json) defines new three-encoder runs. A frozen protocol additionally binds it to actual creation receipts, baseline measurements/decks, circuit snapshots, PDK entry/MOS hash evidence, source code and dependency versions. The [original local frozen protocol](../artifacts/local/m6-real-protocol/protocol.json) records the six-encoder study and requires the matching historical source/configuration from `bbdfe36` and its pinned dependencies. The [runner](../examples/benchmark_real_cross_category.py) rejects a changed protocol or changed inputs before constructing a real environment. An existing protocol file cannot be overwritten through the freeze command.

## Physical tasks

| Held-out target | Training and validation classes | Target actions |
| --- | --- | ---: |
| Five-MOS OTA | LDO, VCO | 1 |
| Six-MOS LDO | OTA, VCO | 2 |
| Three-stage VCO | LDO, OTA | 3 |

These are the qualified `ota5_v1`, `ldo_m6_v1` and `vco_m6_v1` circuits. The OTA adjusts only matched input-pair width, 3.6–4.4 µm. LDO adjusts matched input-pair width, 3.6–4.4 µm, and pass width, 7.2–8.8 µm. VCO adjusts its three limiter widths independently, 0.9–1.1 µm. All widths retain their 5 nm grid, native CDF callbacks and fixed-parameter checks. The earlier `ota7_m5_v2` remains a protected core outside this study.

Every fold starts fresh learners and replay buffers. Its held-out category cannot occur in source training or validation. Each encoder/seed trains sequentially on the other two classes in alphabetic order, sharing that source learner/replay only within the fold. Validation uses different goals on the source circuits with frozen weights and does not select hyperparameters. No fold's results are used to tune another fold.

The physical metric registry has **23 slots**, with fixed units and reference scales. Unused class metrics are masked; unknown or mismatched units are rejected. The reference scales are declared constants, not statistics fitted from held-out results. Supply power is a shared metric: steady DC power for OTA/LDO and time-averaged nominal-control power for VCO, under each circuit's fixed testbench. Other diagnostic measurements remain in raw reports even when absent from the policy's active targets.

| Principal goal | Source training | Source validation | Held-out test |
| --- | ---: | ---: | ---: |
| OTA gain / unity frequency | ≥25.010 dB / ≥3.54 MHz | ≥25.015 dB / ≥3.55 MHz | ≥25.020 dB / ≥3.56 MHz |
| LDO absolute output error | ≤7.5 mV | ≤7.4 mV | ≤7.3 mV |
| VCO nominal frequency | 165–170 MHz | 170–175 MHz | 175–180 MHz |
| VCO nominal power | ≤27 µW | ≤27.5 µW | ≤28 µW |

All tasks include required secondary constraints. OTA keeps the prior M5 phase-margin estimate, output voltage, power and unique unity-crossing requirements. LDO also constrains quiescent current, power, endpoint line/load regulation, PSRR and load-step response. VCO also constrains low/high-control frequency, endpoint tuning gain/fraction, swing, period spread, drift, assisted startup and duty cycle. The JSON manifest is authoritative for all bounds, reward scales and units; success requires every active required constraint, and reward uses the existing capped weighted mean of normalized violations.

The OTA goals are reused from the already observed M5 pilot. LDO/VCO goals were selected using their disclosed qualification ranges. There is one characterized topology per class, so the study is **an engineering pilot on known circuits**, not a blind category benchmark. The 38 prior M6 qualification calls, including the retained LDO measurement failure, remain separate upfront engineering cost; earlier M5 work is also disclosed. Saved transitions, checkpoints and fitted statistics from that work are not imported into learning. Knowing metric identities and circuit structure does not establish that a source policy understands an untrained target metric.

## Methods and budget

All three encoders—Graph Transformer, RGCN and GATv2—run scratch, frozen and adaptation, alongside random search and coordinate pattern search: 11 target methods. Seeds are 17, 29 and 43. Networks use 32 hidden channels, two layers and four heads where applicable; parameter counts are reported, not assumed equal. SAC retains its existing fixed hyperparameters, one random warm-up transition and batch size two. Source tasks and target runs each have eight sizing steps plus a measured reset. Each validation episode has one step plus reset.

| Cost | Per fold | All three folds |
| --- | ---: | ---: |
| Source training: 3 encoders × 3 seeds × 2 tasks × 9 calls | 162 | 486 |
| Frozen validation: 3 encoders × 3 seeds × 2 tasks × 2 calls | 36 | 108 |
| Targets: 11 methods × 3 seeds × 9 calls | 297 | 891 |
| Benchmark total | 495 | 1,485 |
| Final baseline reset for each physical circuit | — | 3 |
| **Complete call ceiling** | — | **1,488** |

One call means the complete nominal candidate package. VCO retains three control-voltage transients in each call; LDO retains its DC/sweep/AC/transient package. Successful completion would make 496 evaluations per circuit, including its final baseline check. No extra simulation is hidden behind validation, reset or restoration. Every environment restores on exit; the three final simulations independently verify restored baseline metrics/decks. Full core snapshots and the two previously hashed model files are checked before and after the suite without simulator calls.

The budget validator checks the whole suite before bindings or backends are opened, and the runner reserves each fold and final baseline checks. Failure retains partial call counts and stops further folds; it does not silently retry or refill failed calls. Duplicate proposals are still simulated and counted. Execution is serial through the existing native bridge lock. There is no automatic resume of a partially completed suite, since repeating it would spend additional calls and must be accounted for separately.

Frozen policies use measured resets and sequential mean-policy queries, with zero weight updates; they are not simulation-free one-shot predictions. Adaptation copies only same-architecture weights and alpha, with fresh optimizers and empty target replay. Scratch uses a fresh model with the same online budget. The short training budget is a pilot choice and cannot support claims about convergence or stable superiority. Reports retain upfront versus online cost, success, right-censoring, first-feasible calls/time, final metrics, parameter counts, failures and update cost.

OTA/LDO use their existing qualified numerical decks. VCO uses the validated fast policy: 0.6 µs transients, 0.2–0.6 µs measurement, moderate accuracy and 50 ps maximum step. The three fixed control voltages and waveform rejection rules are unchanged. All methods get identical numerical settings for a given task. Final VCO baseline restoration is also checked in fast mode; reference-mode verification of selected optimized designs is a separate future qualification budget, not included in this pilot's performance claims.

## Commands and execution boundary

The local bindings file contains paths to the existing qualified artifacts, library and model entry. It contains no credentials. Planning needs neither an environment file nor a bridge installation:

```bash
python examples/benchmark_real_cross_category.py --dry-run \
  --bindings artifacts/local/m6-real-protocol/bindings.json

python examples/benchmark_real_cross_category.py \
  --bindings artifacts/local/m6-real-protocol/bindings.json \
  --freeze artifacts/local/m6-three-encoder-protocol/protocol.json

python examples/benchmark_real_cross_category.py \
  --check-plan artifacts/local/m6-three-encoder-protocol/protocol.json
```

The second command is for first freezing only; it refuses an existing output. Execution requires the exact saved plan and the existing bridge connection:

```bash
python examples/benchmark_real_cross_category.py \
  --execute artifacts/local/m6-three-encoder-protocol/protocol.json \
  --env /path/to/bridge.env \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/m6-real-cross-category
```

Execution revalidates local evidence and source/dependency identity before connecting, then checks live circuit/model state. Changing targets, budget, code or reference evidence requires a new explicitly identifiable protocol; the old file remains preserved. Raw circuit data and simulation artifacts remain local.

The original protocol-preparation increment ran only the planning and verification commands. The subsequent authorized six-encoder execution is recorded in [physical pilot results](m6-real-results.md). Current offline tests exercise the physical 1/2/3-action inputs across all three retained encoders, metric masks, evidence binding, task/precision/budget drift, immutable plans, partial-cost retention and final-check accounting. Test-only fixtures and stub executions are not real simulation evidence. PVT/MC, transient noise, phase noise, dropout/general LDO stability and broader topology sampling remain outside this protocol.

Acceptance on 2026-09-20: **530 tests passed, zero failures/errors/skips**, with local IPC enabled; the only warning was upstream TorchScript deprecation. Freeze and check-plan reconstructed the same protocol digest, `993f759f07b5f87b97048973bf526a97633129a8fff547d2067b0041a07f5129`. New real simulator calls and real learner updates are both zero. Evidence is retained in [JUnit](../artifacts/local/m6-real-protocol-tests.xml), [freeze output](../artifacts/local/m6-real-protocol/freeze-result.json), [verification output](../artifacts/local/m6-real-protocol/check-result.json) and the [acceptance summary](../artifacts/local/m6-real-protocol-acceptance-summary.json).
