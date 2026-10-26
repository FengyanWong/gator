# Conditions, Monte Carlo and compute budgets

Updated 2026-09-26: `docs/plan-reward-v2-real-flow.md` authorizes OTA7's explicit `always`
training plan (nominal + four screening corners); other profiles reject training corners, and post-validation
remains independent. Reward-v2 passed bounded real OTA7 A/B/C acceptance: 73 Spectre calls (A21, B44 including
one recorded failure, C8), 0 uncertain calls, and all physical restorations and baseline requalifications passed.
The user acknowledged unknown license status and explicitly authorized B44/77 total; the normal licensing process
was not bypassed. A passed native-derived/independently exported netlist, PSF and supply checks; C's shared budget
refused to launch five conditions with only four slots remaining. Corners still default to off; MC is unimplemented.
No robust-feasible design was found, and this does not establish a reward advantage, complete worst-case coverage or yield. See `docs/reward-v2.md`.
Reward v2.1 added `after_nominal` on 2026-09-29: run four corners only after nominal passes every hard spec (a step
that fails nominal costs only 1 call). The OTA7 physical gate check used 10 calls (record 7.108). MC remains unimplemented;
only `docs/plan-finalist-monte-carlo.md` exists (synchronized 2026-09-30).

## Current scope

The early condition-interface task was limited to M3; later M4/M5/M6 and reward-v2 authorization is not limited by that historical scope.
Nominal SAC, independent Corner check and explicit five-condition OTA7 training are implemented. General top-k batches
and MC execution remain unimplemented. The "future" suggestions below do not start experiments automatically; research call budgets still need separate decisions.

Default nominal mode does not ingest post-validation PVT/MC results. Explicit `always` mode reserves calls for the whole plan,
executes five conditions per step and enters them into v2 reward/replay; reset runs nominal only and does not claim full coverage.
The two modes cannot be mixed in exact resume. Five screening points are still neither all combinations nor a yield test.

## Condition sources and current GPDK045

First read the target PDK's model entry, device types, temperature range, SOA/voltage documentation and statistical models. Do not copy examples the user has withdrawn, or use another PDK's SS/FF/MC names or voltages as defaults.

Sources for the current `configs/gpdk045_conditions.json`:

- `models/spectre/gpdk045.scs`: tt/ss/ff/fs/sf and a separate mc entry.
- `docs/gpdk045_PDK_Model_Report.pdf`, tables 2.1/2.3: −40..125°C and five process corners for the corresponding models.
- `models/spectre/gpdk045_soa.scs`: `max_vdd_1v=1.1`, whose comment describes a check threshold of 1 V +10%; do not widen the range based only on a device name or an old 1.2 V label on a manual page.

Retain the validated TT/27°C/1.0 V nominal condition. The engineering screening set is TT/27/1.0, SS/125/0.9, FF/−40/1.1, FS/27/1.0 and SF/27/1.0 (temperature in °C, voltage in V). The project chose 0.9 V as a −10% screening point; it is not a PDK-declared minimum voltage. This set does not establish exhaustive worst-case coverage. SOA is OFF in the original model entry; limiting testbench supply does not mean all terminal-voltage reliability checks have been performed.

The current ideal input common-mode voltage of 0.6 V and bias of 0.4 V do not scale with supply; the load stays at 1 pF. Changing this policy needs a new configuration and baseline; do not change it implicitly when extending PVT.

## Infrastructure contract

- Static circuits and nominal geometry continue to use the common CircuitGraph/parameter groups; equal-size matching does not prohibit the PDK from injecting random device mismatch.
- PVT is an external evaluation condition, not a sizing action. Context must agree across the real request, immutable netlist, result, graph metadata and logs; the VDD feature must match the executed value.
- MC must distinguish process/mismatch/all, model section, sample count, seed and per-sample index. The current interface reserves this capability; an unimplemented capability must explicitly raise UnsupportedCapability, never substitute N nominal runs.
- Retain every failed/unknown sample and condition; count design failures, measurement failures and infrastructure failures separately. The fraction of successful samples after excluding faults is not the whole plan's yield.
- Future cache keys cover actual sizes, model/PDK fingerprints, testbench, PVT, MC settings and sample identity, analysis accuracy and measurement version. Width or seed alone is insufficient.
- Count candidates, corner/sample points, Spectre invocations, failures/retries and time together; an MC batch may use few process calls while incurring the cost of many samples.

## Data rules for top 3 post-validation

First rank valid nominal_reward values for the same circuit, specifications and nominal context, and deduplicate actual executed sizes. Use and record a fixed tie-breaking rule; once the current reward saturates, do not claim it distinguishes the quality of all passing designs. Return the actual number when fewer than three valid independent designs exist; do not duplicate them to fill the set.

A candidate's five results must share the same sizes and origin and have exact corner identities. Do not mix results from another candidate or old conditions. All required specs jointly determine a pass for each fixed corner.

```
robust_score = nominal_reward - lambda_failed * number_of_failed_corners
```

Lambda is explicitly configured; the current engineering default is 1.0, not a theoretical optimum. robust_score supports post-validation ranking; **a design with even one known failed corner cannot be accepted**. Keep missing or infrastructure/measurement failures inconclusive; a confirmed failure can mark the design rejected first, but do not invent the unfinished portion's score or pass rate. Calculate a complete pass rate only after the entire plan finishes.

For worst-case results, use the minimum for min, maximum for max, and deviation from both bounds for range, retaining the corresponding corner and valid coverage count. Do not substitute an average for meeting constraints or call the observed worst point the mathematical worst-case of the entire process space.

## Optional low-cost extensions when explicitly authorized later

These are proposed experiment designs, unimplemented, and they do not change the current nominal-only default.

1. **Keep training and validation separate first.** Freeze the candidate set after training or at explicitly configured checkpoints, and screen only the top 3 at five points. One round has at most 15 deterministic condition points, with failures/retries counted separately; do not automatically incur this cost after every SAC step.
2. **If PVT-aware training is needed, sample a few corners first.** For example, sample only 1–2 training corners per sizing step and make the condition or evaluation plan explicit; periodically check the full validation set. Retain sampling probability for difficult corners while covering other training conditions. A sampled reward does not mean all corners have been validated; compare real point counts, pass rates and total time with the nominal baseline.
3. **Use MC on a limited candidate set first, with staged budgets.** For example, 8 → 32 → 128 samples illustrate budget levels only; reject clear failures early and add samples only for promising candidates. Every yield conclusion needs a sample count, statistical method and confidence interval; a small batch of all passes does not demonstrate high yield. Adaptive stopping/selection needs suitable intervals or explicitly independent final validation, rather than uncorrected fixed-sample conclusions.
4. **Study paired random samples for candidate comparisons.** When models and instance identities are reproducible, common random samples can reduce comparison noise. Record seed/sampling method/statistical variables; do not assume the same seed alone aligns different topologies. Use independently held-out random samples for final validation to avoid repeatedly optimizing against fixed seeds.
5. **Study statistically robust training last.** Compare expected violation, tail risk or yield constraints from small statistical batches; put the objective, sample count and uncertainty in an explicit contract and first test reward variance and bias. Do not treat one random failure as a deterministic design label or a small batch's worst sample as a reliable tail estimate. Version this separately from original nominal replay and check context/reward/schema when migrating checkpoints.
6. **Allocate compute according to measured bottlenecks.** GPUs mainly serve graph networks; time Spectre, netlisting, transfer and PSF costs separately. First reuse immutable job copies from one size update/export. Parallelism requires isolated result directories, authorized CPU/memory/licenses and safe session isolation. A GPU does not make multiple-corner simulation cheap, and multiple workers are not the default change.

Do not introduce a surrogate now. Treat any future acceleration approach as a separate experiment and compare it with nominal+post-validation under the same total simulation budget.

## References for statistical meaning

- [Cadence: differences between process, mismatch and all](https://community.cadence.com/cadence_technology_forums/f/custom-ic-design/20466/monte-carlo-simulation-global-local-vs-local-and-process-vs-mismatch). Actual section combinations still depend on the local PDK; do not assume all deterministic corners support the same statistical modes.
- [Cadence: Monte Carlo sampling and confidence intervals](https://community.cadence.com/cadence_blogs_8/b/cic/posts/the-art-of-analog-design-part-2-monte-carlo-sampling). Distinguish corner pass rates, statistical pass rates under simulation models and real manufacturing yield.
