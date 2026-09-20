# M6: strict requalification of optimized VCO designs

The [physical pilot](m6-real-results.md) evaluated all 937 VCO candidate packages with the qualified **fast** numerical policy. That policy was [qualified](m6-vco-runtime.md) against the strict reference at eight width assignments, none of which is a design the optimizers later found. This increment resimulates the pilot's feasible held-out VCO designs with the original **reference** deck and reports, separately, whether the fast policy still agrees there and whether each feasibility claim survives.

This matters because several claims sit inside the previously measured fast-versus-strict differences (up to 0.0296% in frequency and 0.2081% in power):

| Run (method / seed) | Fast measurement | Distance to the frozen limit |
| --- | --- | ---: |
| MLP scratch / 29 | 175.0267 MHz | 0.015% above the 175 MHz floor |
| GAT scratch / 43 | 175.0436 MHz | 0.025% above the 175 MHz floor |
| MLP adaptation / 17, GCN adaptation / 17 | 179.8633 MHz, 27.9456 µW | 0.076% below 180 MHz; 0.194% below the 28 µW cap |
| Coordinate pattern search / 17, 29, 43 | 175.2051 MHz | 0.117% above the 175 MHz floor |

No pilot result, learner, replay or checkpoint is modified, and strict results never enter training.

## Frozen contract

[`vco_requalification.py`](../examples/vco_requalification.py) builds a deterministic plan from saved evidence only. It requires the completed real pilot and its passed [independent audit](../artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649/audit.json), and pins the suite report, VCO fold report and audit by SHA-256. For every selected design it pins the candidate record, simulation job, executed fast deck hash, physical source-netlist hash and fast metrics. Records or jobs outside the pilot directory, cache hits, a different numerical policy, off-grid widths and identical widths with different fast evidence are rejected.

In all 36 successful VCO runs the saved best design is the **first feasible candidate**: feasible rewards tie at zero and the first is retained. The plan verifies this, so requalifying a saved design requalifies that run's success and first-feasible-call claim. Two scopes are supported and the choice is part of the frozen plan:

| Scope | Designs | Claims covered | Strict calls | What it can conclude |
| --- | ---: | ---: | ---: | --- |
| `best` | 26 unique first-feasible designs | 36 runs | 28 | Confirms or does not confirm each run's saved design. An unconfirmed run is **not re-scored**, because its later feasible candidates were not resimulated. |
| `feasible` | 67 unique feasible candidates | 80 candidate claims in 36 runs | 69 | Re-scores every successful run and its first feasible call under the strict policy. |

Runs that failed under the fast policy are not resimulated in either scope, so neither scope can turn a fast failure into a strict success. Each call is one complete nominal candidate package of three reference-mode transients at 0.55/0.65/0.75 V control. The sequence is a strict baseline, every design in sorted width order, then a restored strict baseline. The ceiling equals the plan; there are no retries, cache hits or learner updates. Historical strict jobs took about 55–63 s of backend time each.

- **Baselines.** Both baseline calls must reproduce the [saved strict baseline](../artifacts/local/m6-vco-runtime/reference/2b6a8631855c497eaf0086ae7b391de8/verification.json) metrics to 1e-6 relative and its executed deck hash exactly.
- **Agreement.** Limits are those frozen before the first fast trial and are not retuned: 0.1% relative for the three frequencies, tuning gain and tuning fraction; 0.5% for power; 1 mV swing; 0.001 duty; 2 ns startup detection. Period spread and window drift keep their 0.02 / 0.01 qualification limits. Strict and fast jobs must share the same physical source-netlist hash.
- **Feasibility.** A design is strict-confirmed only if its reference-mode simulation is valid and satisfies all eleven required specifications of the frozen [pilot manifest](../configs/m6_real_cross_category.json) VCO test task, including the 175–180 MHz window and 28 µW cap.
- **Interpretation, declared before execution.** Exceeding an agreement limit, or an invalid strict simulation of a design, fails the requalification. A lost feasibility verdict is a reported finding and does not fail execution.
- **Stopping.** An uncertain invocation count, a baseline that is not `ok`, or any design status other than `ok` or `measurement_error` stops the run without retry. A strict `measurement_error` on a design is recorded as an invalid strict result and execution continues. The VCO is always restored, and the full VCO snapshot plus the two OTA cores and the LDO are compared before and after.
- **Timeout.** The per-call limit is 180 s instead of the default 60 s, since historical strict jobs used up to 44 s of remote execution. The limit is not part of the deck or numerical policy.

The plan also pins both numerical policies, the test specifications, limits and the SHA-256 of the VCO profile, measurement code, this module, its entry point and the three configuration files. `freeze` refuses to overwrite; `check`, `execute` and `compare` rebuild the plan and reject any drift in code, definitions or pilot evidence before doing anything else.

## Commands

```bash
# Offline: freeze the design list, limits and ceiling. Choose the scope here.
python -B examples/requalify_vco_designs.py freeze \
  artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649 \
  --reference artifacts/local/m6-vco-runtime/reference/2b6a8631855c497eaf0086ae7b391de8/verification.json \
  --scope best --output artifacts/local/m6-vco-requalification/plan-best.json

# Offline: rebuild and compare the frozen plan. Use plan-feasible.json throughout for the larger scope.
python -B examples/requalify_vco_designs.py check artifacts/local/m6-vco-requalification/plan-feasible-r2.json

# Real: spends the frozen number of reference-mode Spectre calls through the existing bridge.
python -B examples/requalify_vco_designs.py execute artifacts/local/m6-vco-requalification/plan-best.json \
  --env /path/to/bridge.env --library GATOR_TESTS \
  --creation-receipt artifacts/local/m6-vco-baseline/creation.json \
  --model-file /absolute/spectre-host/path/to/gpdk045.scs \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/m6-vco-requalification/execution

# Offline: agreement, strict feasibility and per-run findings; then the independent waveform audit.
python -B examples/requalify_vco_designs.py compare artifacts/local/m6-vco-requalification/plan-best.json \
  RUN/verification.json --output artifacts/local/m6-vco-requalification/comparison.json
python -B examples/audit_vco_baseline.py RUN/verification.json \
  --bridge-site-packages /path/to/bridge/site-packages --output artifacts/local/m6-vco-requalification/audit.json
```

`execute` writes `verification.json` after every stage in the same layout as the VCO qualification reports, so the existing [waveform audit](../examples/audit_vco_baseline.py) rebuilds each strict deck, recomputes all metrics from saved PSF and checks both baselines without modification. Connection library and model file must equal those recorded by the pilot's fast jobs.

## Frozen plans — 2026-09-20

Both scopes were frozen before any strict call, so the choice of scope could not depend on strict results:

| Plan | Designs | Claims | Strict calls | Plan SHA-256 |
| --- | ---: | ---: | ---: | --- |
| [`plan-best.json`](../artifacts/local/m6-vco-requalification/plan-best.json) | 26 | 36 runs | 28 | `cf88a690065fe47deee2ed1dbc3093e32535e77b64f42478aa8012943eaf5d52` |
| [`plan-feasible.json`](../artifacts/local/m6-vco-requalification/plan-feasible.json) | 67 | 80 candidates | 69 | `f4ffcb2495ceb1d484a99c90487401b742e51669ac907a1edfa2a0fd12269d97` |

Both plans rebuild identically with `check`, and a second `freeze` to either path is refused. Full regression passed **574 tests, zero failures/errors/skips**; the only warning was upstream TorchScript deprecation. Thirty new offline tests cover design collection and claims, tampered or escaping evidence, overwrite and drift rejection, identity of the limits with the fast-policy qualification, call accounting, stopping without retry, restoration failure and the separation of policy agreement from feasibility. Test fixtures and the stub backend are not simulation evidence. The preparation increment made **zero new real Spectre calls and zero learner updates**. Evidence is retained in [JUnit](../artifacts/local/m6-vco-requalification-protocol-tests.xml) and the [acceptance summary](../artifacts/local/m6-vco-requalification-protocol-acceptance-summary.json).

## Results — 2026-09-20

The user authorized the `best` scope. [Execution](../artifacts/local/m6-vco-requalification/execution/ec73aab28cfc470d84a03960665ada27/verification.json) spent exactly **28 reference-mode Spectre calls / 84 transients** in 1,711.5 s of wall time (1,664.6 s summed backend time, 59.4 s per call). There were zero failed simulations, retries, uncertain invocations, cache hits or learner updates. The `feasible` plan remains frozen and unexecuted. Cumulative M6 physical cost is now 2,877 candidate packages.

**All 26 designs are strict-valid and satisfy every required test specification, so all 36 first-feasible success claims in the pilot's VCO column are confirmed.** No run is unconfirmed, and the pilot's VCO success table and first-feasible-call table stand unchanged.

The fast policy also stayed inside every frozen agreement limit at these optimized designs, which lie outside its eight original qualification points:

| Maximum difference from strict reference | 26 optimized designs | Eight qualification points | Limit |
| --- | ---: | ---: | ---: |
| Nominal frequency | 0.0178% | — | 0.1% |
| Any control-point frequency | 0.0345% | 0.0296% | 0.1% |
| Endpoint tuning gain | 0.0519% | 0.0454% | 0.1% |
| Tuning fraction | 0.0363% | 0.0388% | 0.1% |
| Mean supply power | 0.2545% | 0.2081% | 0.5% |
| Minimum cycle swing | 0.1589 mV | 0.1643 mV | 1 mV |
| Duty cycle | 0.0000956 | 0.0000752 | 0.001 |
| Startup detection | 0.00769 ns | 0.00961 ns | 2 ns |

The frequency difference is systematic, not scatter: fast minus strict nominal frequency is **+0.0153% on average and between +0.0141% and +0.0178% for every design**. Power differs in both directions, from −0.128% to +0.255%. Three differences exceed the earlier observed maxima while remaining well inside the limits frozen before the first fast trial; no limit was relaxed.

Several verdicts are confirmed only narrowly, and should be read as statements about this numerical policy rather than as design margin:

| Design | Runs | Strict measurement | Remaining distance to the limit |
| --- | --- | --- | ---: |
| 04 | MLP scratch / 29 | 175.00103 MHz | 1.03 kHz (0.0006%) above the 175 MHz floor |
| 24 | GAT scratch / 43 | 175.0168 MHz | 0.0096% above the floor |
| 17 | MLP adapt / 17, GCN adapt / 17 | 179.8341 MHz, 27.9215 µW | 0.092% below 180 MHz; 0.280% below the 28 µW cap |
| 25 | Coordinate pattern search / 17, 29, 43 | 175.1798 MHz | 0.103% above the floor |

At the mean difference, a fast reading below about 175.027 MHz would not meet the strict floor. Design 04 read 175.0267 MHz and survived because its own difference was 0.0147%. Because the fast policy reads frequency high, a fast failure just above the 180 MHz ceiling could in principle be strict-feasible. Fast failures were not resimulated, but an offline scan of all 460 valid fast-infeasible held-out VCO candidates found **none** that failed only the ceiling within +0.0178% or only the power cap within +0.2545%; the nearest reading above the ceiling is 180.4969 MHz (+0.276%).

| Design | Widths MS1/MS2/MS3 (µm) | First feasible design of (method / seeds) | Fast (MHz, µW) | Strict (MHz, µW) |
| --- | --- | --- | ---: | ---: |
| 01 | 1.005/1.060/1.090 | GT scratch / 17; MLP scratch / 17; GCN scratch / 17; RGCN scratch / 17; GAT scratch / 17; Port-GNN scratch / 17; Random / 17 | 177.6434, 27.5718 | 177.6118, 27.5820 |
| 02 | 1.075/0.990/1.040 | GCN scratch / 29 | 175.5197, 27.2121 | 175.4938, 27.2348 |
| 03 | 1.075/0.995/1.040 | GCN adapt / 29 | 175.7480, 27.3074 | 175.7211, 27.2769 |
| 04 | 1.080/0.975/1.040 | MLP scratch / 29 | 175.0267, 27.1873 | 175.0010, 27.1664 |
| 05 | 1.080/0.980/1.040 | GT adapt / 29; MLP adapt / 29 | 175.2595, 27.1987 | 175.2328, 27.2168 |
| 06 | 1.080/0.985/1.040 | RGCN adapt / 29 | 175.4921, 27.2000 | 175.4631, 27.2228 |
| 07 | 1.080/0.985/1.045 | RGCN scratch / 29 | 175.6979, 27.3041 | 175.6727, 27.2735 |
| 08 | 1.080/0.995/1.045 | GAT adapt / 29 | 176.1592, 27.3979 | 176.1306, 27.3284 |
| 09 | 1.080/0.995/1.050 | GAT scratch / 29 | 176.3676, 27.4271 | 176.3402, 27.3818 |
| 10 | 1.080/1.025/1.040 | Port-GNN adapt / 17 | 177.2907, 27.5479 | 177.2627, 27.5335 |
| 11 | 1.080/1.030/1.040 | GT adapt / 17 | 177.5086, 27.5726 | 177.4822, 27.5444 |
| 12 | 1.080/1.035/1.045 | RGCN adapt / 17 | 177.9421, 27.6961 | 177.9152, 27.6396 |
| 13 | 1.080/1.070/0.975 | RGCN adapt / 43 | 176.2608, 27.4258 | 176.2357, 27.3700 |
| 14 | 1.085/0.980/1.045 | GT scratch / 29 | 175.6632, 27.3002 | 175.6386, 27.2632 |
| 15 | 1.085/0.995/1.055 | Port-GNN adapt / 29 | 176.7752, 27.4784 | 176.7476, 27.4291 |
| 16 | 1.085/1.035/1.050 | GAT adapt / 17 | 178.3599, 27.7092 | 178.3318, 27.6918 |
| 17 | 1.085/1.050/1.070 | MLP adapt / 17; GCN adapt / 17 | 179.8633, 27.9456 | 179.8341, 27.9215 |
| 18 | 1.085/1.075/0.975 | Port-GNN adapt / 43 | 176.6624, 27.4209 | 176.6362, 27.4194 |
| 19 | 1.085/1.075/0.985 | GAT adapt / 43 | 177.1329, 27.4495 | 177.1064, 27.4780 |
| 20 | 1.085/1.080/0.980 | GT adapt / 43 | 177.0994, 27.4421 | 177.0732, 27.4772 |
| 21 | 1.090/0.995/1.055 | Port-GNN scratch / 29 | 176.9739, 27.4453 | 176.9456, 27.4761 |
| 22 | 1.090/1.080/0.970 | MLP adapt / 43 | 176.8235, 27.4610 | 176.7965, 27.4215 |
| 23 | 1.090/1.085/0.985 | GCN adapt / 43 | 177.7369, 27.5825 | 177.7087, 27.5961 |
| 24 | 1.095/1.055/0.950 | GAT scratch / 43 | 175.0436, 27.1860 | 175.0168, 27.1641 |
| 25 | 1.100/1.000/1.000 | Coordinate / 17, 29, 43 | 175.2051, 27.2097 | 175.1798, 27.2026 |
| 26 | 1.100/1.070/0.940 | GCN scratch / 43 | 175.3493, 27.1672 | 175.3234, 27.1915 |

Both strict baselines returned identical metrics and deck hash, matched the saved strict baseline (171.1402 MHz, 26.5558 µW), and the VCO snapshot and three protected cores were unchanged. The offline [comparison](../artifacts/local/m6-vco-requalification/comparison.json) revalidated the frozen plan, required equal physical source-netlist hashes for every fast/strict pair and made no simulator call. The independent [waveform audit](../artifacts/local/m6-vco-requalification/audit.json) rebuilt all 28 executed reference decks from their recorded policy, verified export hashes and CDF readbacks, and recomputed all 28 metric packages from saved PSF with NumPy; all passed. The read-only [final inspection](../artifacts/local/m6-vco-requalification/final-inspection.json) found all four cores identical to the pilot's after-snapshot and the PDK entry/MOS hashes unchanged; that hash check is not recursive. A [machine-readable summary](../artifacts/local/m6-vco-requalification-acceptance-summary.json) links the evidence and its hashes. The regression result above was obtained at the same pinned source state, which `compare` re-verified after execution.

## Source location and revalidation

The module was first written as `src/analog_optimizer/evaluation/vco_requalification.py`. Every `*.py` in that package enters `training/sac.py::source_digest()`, which is part of each checkpoint contract and of the frozen physical pilot plan. The new file therefore changed the digest from the pilot's `02127bc3…` to `2b21a512…`, so the 162 pilot checkpoints could not be loaded and `examples/audit_real_cross_category.py` could not revalidate the pilot plan in the working tree. Nothing was damaged, and the pilot's saved audit was unaffected.

Both requalification plans pin that file by path and SHA-256, so it was deliberately left untouched until execution, comparison, waveform audit and final inspection had all completed against the pinned sources. It was then moved to [`examples/vco_requalification.py`](../examples/vco_requalification.py); the only content changes are its two package-relative imports, its own entry in the pinned source list and a docstring note. After the move, `source_digest()` equals the pilot's `02127bc39140be87232cd6799b7c020de0e5d7960d59fff58e6ba9e2c32ea101` again and `validate_frozen_plan` accepts the pilot's saved protocol.

Consequently `plan-best.json` and `plan-feasible.json` describe the pre-move source state, recorded in their `source_hashes`; `check` and `compare` reject them now, as designed. The executed evidence above is complete and was verified before the move. The unexecuted larger scope was re-frozen as [`plan-feasible-r2.json`](../artifacts/local/m6-vco-requalification/plan-feasible-r2.json) (`d033582917739821e14da4786ee9c66b869d7b42e664fda94142221842dcbfe0`). It differs from the original only in `source_hashes` and the resulting digest; its designs, claims, limits, specifications, baseline and 69-call ceiling are identical. It was frozen after the `best` results were known, which is disclosed here; its content was fixed by the original plan before any strict call.

## Scope and limits

This is a nominal TT/27°C/1.0 V numerical-policy check on one characterized topology. It does not add PVT/Monte Carlo, phase noise, transient noise, unassisted startup, new topologies or wider action ranges, and it cannot establish a transfer or encoder advantage. The strict reference is itself a numerical setting, not a measurement of silicon. With three seeds, confirmed success rates keep the same wide Wilson intervals as the pilot.
