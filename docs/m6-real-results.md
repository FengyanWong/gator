# M6: physical cross-category pilot results

The frozen three-fold experiment completed on 2026-09-20 with **2,811 real Spectre calls and 1,566 SAC updates**. The runner restored all circuits and passed the three final baseline evaluations. The [independent audit](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/audit.json) subsequently verified every saved candidate package and all 162 learner checkpoints without new simulator calls, and the final regression suite passed 544 tests; see [audit results](#audit-results--2026-09-20).

GT adaptation succeeded on 2/3 OTA, 3/3 LDO and 3/3 VCO seeds, compared with 2/3 in each class for GT scratch. Coordinate search and GCN scratch succeeded on all three seeds in every class. These results do **not establish a GT advantage**: the circuits were already characterized, the training budget is small, and transfer incurs source-training cost. All six frozen encoders failed every held-out target episode within budget.

The [protocol](m6-real-protocol.md) and [manifest](../configs/m6_real_cross_category.json) define the targets, numerical settings, action domains and interpretation limits. No production code, targets, hyperparameters or budget changed during execution. The protocol SHA-256 is `993f759f07b5f87b97048973bf526a97633129a8fff547d2067b0041a07f5129`.

## Evidence and cost

The local run is [`eedb54fe59d642edaff93ba9def27649`](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/report.json). Its [saved protocol](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/suite-protocol.json) pins the physical definitions, qualified baselines, source digest and dependencies. Each fold preserves every candidate journal, native export, executed deck, raw PSF package and learner checkpoint.

| Cost | Real candidate packages |
| --- | ---: |
| Source training | 972 |
| Frozen source validation | 216 |
| Held-out target runs | 1,620 |
| Final baseline evaluations | 3 |
| **This experiment** | **2,811** |
| Earlier M6 physical qualification | 38 |
| **M6 physical total through this experiment** | **2,849** |

There were 937 candidate evaluations per circuit. A VCO package contains three control-voltage transients; OTA and LDO retain their fixed multi-analysis packages. Resets and duplicate designs are counted. There were no new simulation failures, uncertain invocations, cache hits or automatic retries. The earlier 38 qualification calls retain their one disclosed LDO measurement failure. Earlier M5 work and the separate M6 synthetic suite are not part of these new real-call counts.

Each encoder/seed/fold uses 18 source-training calls, four diagnostic validation calls, and nine calls per target method. The report's `pretraining_plus_online_calls` is 27 for a transferred target, with its four validation calls reported separately. Scratch and search methods use nine online calls per run. Source training is shared by the corresponding frozen/adaptation pair and is counted once in the suite total. The full pilot took **14,934.71 seconds (4 h 8 min 55 s)**, excluding the later audit and regression tests.

## Success rates

Every entry is successful seeds out of three, using seeds 17, 29 and 43. A seed succeeds only if a candidate satisfies every active required specification. Each target run uses a measured reset and eight sizing steps; it continues to its fixed budget after success.

| Method | OTA | LDO | VCO |
| --- | ---: | ---: | ---: |
| GT scratch | 2/3 | 2/3 | 2/3 |
| GT frozen | 0/3 | 0/3 | 0/3 |
| GT adaptation | 2/3 | 3/3 | 3/3 |
| MLP scratch | 3/3 | 3/3 | 2/3 |
| MLP frozen | 0/3 | 0/3 | 0/3 |
| MLP adaptation | 2/3 | 3/3 | 3/3 |
| GCN scratch | 3/3 | 3/3 | 3/3 |
| GCN frozen | 0/3 | 0/3 | 0/3 |
| GCN adaptation | 2/3 | 3/3 | 3/3 |
| RGCN scratch | 2/3 | 2/3 | 2/3 |
| RGCN frozen | 0/3 | 0/3 | 0/3 |
| RGCN adaptation | 2/3 | 3/3 | 3/3 |
| GAT scratch | 2/3 | 2/3 | 3/3 |
| GAT frozen | 0/3 | 0/3 | 0/3 |
| GAT adaptation | 2/3 | 3/3 | 3/3 |
| Port-GNN scratch | 2/3 | 2/3 | 2/3 |
| Port-GNN frozen | 0/3 | 0/3 | 0/3 |
| Port-GNN adaptation | 2/3 | 3/3 | 3/3 |
| Random search | 2/3 | 3/3 | 1/3 |
| Coordinate pattern search | 3/3 | 3/3 | 3/3 |

Do not pool the three circuits as nine independent topology samples. Even 3/3 successes has a wide Wilson 95% interval, approximately 0.44–1.00; 2/3 is approximately 0.21–0.94. Per-task intervals and complete per-seed results are retained in the [OTA](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/opamp/report.json), [LDO](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/ldo/report.json) and [VCO](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/vco/report.json) reports.

All models use the same declared width/depth, but capacity differs. Actor plus twin-critic parameter counts are GT 125,444; MLP 92,132; GCN 98,852; RGCN 178,724; GAT 107,012; port-GNN 112,772. This is not a parameter-matched comparison.

## Calls and time to feasibility

Cells list the first feasible call for seeds 17 / 29 / 43, including the measured reset. A dash means no success within nine calls; these runs remain right-censored and are not removed from reporting.

| Method | OTA calls | LDO calls | VCO calls |
| --- | --- | --- | --- |
| GT scratch | 9 / 3 / — | 2 / 5 / — | 2 / 3 / — |
| GT frozen | — / — / — | — / — / — | — / — / — |
| GT adaptation | 6 / 2 / — | 6 / 6 / 3 | 7 / 2 / 3 |
| Random search | 4 / 4 / — | 2 / 5 / 4 | 2 / — / — |
| Coordinate pattern search | 4 / 4 / 4 | 8 / 8 / 8 | 8 / 8 / 8 |

For GT adaptation, corresponding first-feasible times were OTA **21.44 / 5.82 / — s**, LDO **24.90 / 25.08 / 10.63 s**, and VCO **56.44 / 16.54 / 25.09 s**. Coordinate search took OTA **14.44 / 14.48 / 14.00 s**, LDO **33.15 / 30.99 / 32.40 s**, and VCO **64.14 / 68.27 / 63.76 s**. These are online episode times; source training and validation are additional costs. The fold reports retain every other method's times, inference/update timing and censor duration.

Some scratch successes precede learning: all six LDO scratch runs at seed 17 and all six VCO scratch runs at seed 17 succeeded on their initial random exploration candidate. Those twelve successes cannot be attributed to a trained policy. Frozen evaluation uses sequential deterministic mean-policy queries and still incurs all nine calls; it is not a simulation-free prediction.

Wall time was measured on a shared workstation and simulator host. Small read-only audit samples overlapped early OTA-fold execution, and methods ran in the frozen order. These timing records are descriptive; this run is not a controlled wall-time speedup study.

## Physical examples

The following are the best-reward designs saved by GT adaptation, in seed order. Reward is a capped violation measure and ties retain the first encountered design; a zero reward does not select the lowest-power design among all feasible candidates. Complete secondary metrics, units, validity flags and executed widths remain in the corresponding candidate records.

| Class / seed | Principal measured values | Feasible |
| --- | --- | --- |
| OTA / 17 | 25.02863 dB, 3.57083 MHz unity frequency, 1.96105 µW | Yes |
| OTA / 29 | 25.02543 dB, 3.56580 MHz, 1.96050 µW | Yes |
| OTA / 43 | 25.01705 dB, 3.55269 MHz, 1.95905 µW | No |
| LDO / 17 | 7.20315 mV output error, 257.181 V/A load regulation, 12.94139 µW | Yes |
| LDO / 29 | 7.19046 mV output error, 256.860 V/A, 12.94031 µW | Yes |
| LDO / 43 | 7.20287 mV output error, 257.267 V/A, 12.94424 µW | Yes |
| VCO / 17 | 177.50855 MHz nominal frequency, 1,001.250 MHz/V tuning gain, 27.57262 µW | Yes |
| VCO / 29 | 175.25947 MHz, 990.055 MHz/V, 27.19872 µW | Yes |
| VCO / 43 | 177.09935 MHz, 999.065 MHz/V, 27.44209 µW | Yes |

The OTA failure misses both the 25.020 dB gain and 3.56 MHz unity-frequency requirements. Feasibility for the successful rows also requires every secondary constraint in the frozen manifest; the table shows only selected metrics.

## Audit and reproduction

The [independent auditor](../examples/audit_real_cross_category.py) checks the complete fold/method/seed matrix, every proposal and native CDF export, file/deck hashes, rebuilt observation graphs, conditions and numerical policies. It recomputes OTA AC/DC metrics with NumPy and LDO/VCO metrics from saved raw PSF, then recomputes rewards and feasibility. It checks every baseline against qualification, episode restoration, exact call counts and absence of unaccounted candidate/simulation artifacts.

Checkpoint checks cover source/target task isolation, exact replay-to-journal agreement, encoder/SAC contracts, optimizer step counts, unchanged frozen weights and copied transfer weights. Two independent reloads must produce the same next sampled update, loss and resulting weight digest. These recovery probes update memory only and make no simulator calls. Torch checkpoints are trusted local Python artifacts; do not use this command on untrusted files.

```bash
python -B examples/audit_real_cross_category.py \
  artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649 \
  --bridge-site-packages /path/to/bridge/site-packages

python -B -m pytest -q --junitxml=artifacts/local/m6-real-final-tests.xml
```

### Audit results — 2026-09-20

The audit **passed with 0 new simulator calls**. It verified all **2,811 existing real calls** (937 per class, including the three final baseline resets) against their candidate journals, native exports, deck/file hashes and rebuilt observation graphs, and recomputed all **2,811 raw metric packages** and rewards from the saved PSF data. All **162 checkpoints** (54 per fold) reproduced their next sampled update, loss and weight digest exactly from two independent reloads; source/target task isolation and unchanged frozen weights were confirmed, and the recorded total remains 1,566 training updates. All **399 environment restorations** (396 episodes plus the three final baseline checks) were verified, and the final circuit/model state matched the frozen protocol. The audit took 2,560.88 s (42 min 41 s) over Windows-mounted artifact storage; its recovery probes ran only in memory and are not part of the experiment counts.

Per-candidate wall times recorded by the audit are OTA mean 3.35 s (backend 1.63 s), LDO mean 3.94 s (backend 2.05 s) and VCO mean 8.01 s (backend 6.06 s), with p95 candidate times of 4.04 / 4.52 / 8.84 s. The single simulator version was `23.1.0.242.isr1 64bit -- 7 Sep 2023`. Model hashes cover the recorded PDK entry and MOS files, not a recursive PDK digest.

The final regression suite, run after the audit completed, passed **544 tests with zero failures, errors or skips** in 281.9 s; the only warning was the upstream TorchScript deprecation. Evidence is retained in the [JUnit record](../artifacts/local/m6-real-final-tests.xml), the [audit output](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/audit.json), the [audit log](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/audit.log) and the [machine acceptance summary](../artifacts/local/m6-real-acceptance-summary.json).

The real pilot used the existing bridge connection and qualified fast VCO policy throughout. It did not introduce PVT/Monte Carlo, phase noise, transient noise, broader action ranges or additional topologies. VCO results are nominal measurements with the previously qualified assisted-startup testbench. Strict-mode requalification of selected optimized VCO designs remains a separate next step and budget. A larger, prospectively defined set of circuits and training budgets is needed before making general transfer or encoder-superiority claims.
