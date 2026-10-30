# M6: faster VCO evaluation

The qualified VCO now defaults to a shorter, moderate-accuracy transient policy. Explicit `--analysis-mode reference` retains the original strict deck for reproduction and final design checks. This changes numerical settings only; the physical circuit, three width actions, control voltages and creation receipt remain unchanged.

## Numerical contract

| Setting | Reference | Fast (default) |
| --- | ---: | ---: |
| Transient stop | 2 µs | 0.6 µs |
| Measurement window | 1–2 µs | 0.2–0.6 µs |
| Maximum timestep | 100 ps | 50 ps |
| `errpreset` | conservative | moderate |
| Global `reltol` | 1e-5 | 1e-4 |
| `vabstol` / `iabstol` | 1e-8 V / 1e-13 A | 1e-6 V / 1e-12 A |

Installed Spectre help and the executed logs show that the reference conservative preset makes the effective transient `reltol` 1e-6; the fast run uses 1e-4. The tighter fast maximum timestep still bounds sampling while permitting much larger adaptive steps than the strict reference tolerances allowed. Every candidate still executes three independently initialized transients at 0.55/0.65/0.75 V control, TT/27°C/1.0 V supply, with all three ring outputs and supply current saved.

The fast window retains the original swing, crossing, period-spread, drift, stage-consistency, monotonic-tuning and sampling checks, including at least eight complete cycles in each half-window. Sustained oscillation must now be detected by 200 ns, the start of measurement. A slow or late-starting candidate that cannot satisfy this shorter contract fails explicitly. There is no automatic retry or silent substitution of reference results.

The numerical policy is stored in export manifests, simulation manifests, bridge results, measurement files and qualification reports. Measurement rejects a policy mismatch. The independent artifact audit verifies the executed deck against the recorded policy and recomputes metrics using that policy's window. Legacy reference artifacts without the new metadata remain auditable without being rewritten. OTA and LDO numerical settings are unchanged.

## Accuracy and cost

Before the first fast trial, the [plan](../artifacts/local/m6-vco-runtime/plan.json) froze the settings, call budget and agreement limits: 0.1% relative frequency/tuning, 0.5% power, 1 mV absolute swing, 0.001 duty and 2 ns startup-detection time. Stability checks keep their original absolute qualification limits; tiny deterministic numerical period spread is not interpreted as jitter.

Twelve fast evaluations covered eight unique width assignments: baseline, each individual stage high, all widths low/high, and two mixed interior assignments through the environment. Baseline repeats matched exactly. Every fast evaluation passed both waveform qualification and the predeclared agreement limits against strict results at identical physical parameters.

| Maximum difference from strict reference | Observed | Limit |
| --- | ---: | ---: |
| Any control-point frequency | 0.0296% | 0.1% |
| Endpoint tuning gain | 0.0454% | 0.1% |
| Tuning fraction | 0.0388% | 0.1% |
| Mean supply power | 0.2081% | 0.5% |
| Minimum cycle swing | 0.1643 mV | 1 mV |
| Duty cycle | 0.0000752 | 0.001 |
| Startup detection | 0.00961 ns | 2 ns |

The power comparison intentionally includes the change of integration window; both measurements use the exact time-weighted integral over their declared windows. No post hoc relaxation of the limits was needed.

The [comparison](../artifacts/local/m6-vco-runtime/comparison.json) preserves all per-job values. Across the 12 fast evaluations, the Python backend averaged 6.02 seconds (5.33–6.62 s), including remote execution, download, parsing and custom measurement. The 11 historical strict comparison evaluations averaged 59.10 seconds. Parameter update, native export and session setup are outside this backend timer. Average accepted transient steps fell from 571,085 to 44,065; total raw transient output fell from 119.37 MB to 9.22 MB per candidate.

A fresh strict baseline also reproduced the original metrics and executed deck hash exactly. Its [same-session comparison](../artifacts/local/m6-vco-runtime/same-session-comparison.json) measured 56.93 s strict versus 5.84 s fast for the backend, a 9.74× improvement. The external remote-command timer measured 39.67 versus 4.29 s. This is one paired timing control, not a statistical benchmark across machines.

Spectre's aggregate footer reports an average 6.65 seconds for the fast runs, while its accumulated elapsed timer reports 3.88 seconds and the bridge's external command timer reports 4.27 seconds. The footer's reported wall time sometimes equals CPU time and exceeds the enclosing Python duration. These counters are therefore saved separately; speedup uses the external monotonic timers. Historical footer-only timing should not be treated as an exact end-to-end duration.

The increment used **13 new Spectre invocations / 39 transient analyses**: one fast trial, eight fast width/repeat evaluations, three fast environment evaluations and one fresh strict reference. All succeeded, with zero failed simulations, retries, uncertain invocations or learner updates. Cumulative M6 real qualification cost is 38 calls, including the earlier LDO measurement failure.

The [independent waveform audit](../artifacts/local/m6-vco-runtime/audit.json) covers all 13 new jobs plus two existing strict/half-step jobs to verify legacy compatibility. Those two historical jobs were read only, not resimulated. All 15 saved executions passed deck, metadata, CDF, snapshot, metric and reward checks. The [final inspection](../artifacts/local/m6-vco-runtime/final-inspection.json) confirms all four cores and the previously recorded PDK entry/MOS hashes are unchanged; the model hash check is not recursive.

Full regression passed **501 tests, zero failures/errors/skips** with local IPC enabled. The only warning was upstream TorchScript deprecation. Added checks cover numerical-policy provenance, physical-design independence, strict deck compatibility, default/reference selection and the short window's minimum-cycle rejection. [JUnit](../artifacts/local/m6-vco-runtime-tests.xml) and the [acceptance summary](../artifacts/local/m6-vco-runtime-acceptance-summary.json) retain the test, cost and source-digest evidence. Historical checkpoints retain their original source digest; no automatic migration is performed.

## Reproduction and scope

Use the existing bridge connection and VCO creation receipt; do not recreate the cells:

```bash
python examples/verify_vco_baseline.py --analysis-mode fast \
  --env /path/to/bridge.env --library GATOR_TESTS \
  --creation-receipt artifacts/local/m6-vco-baseline/creation.json \
  --model-file /absolute/spectre-host/path/to/gpdk045.scs \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/vco-fast-qualification
```

`--baseline-only` runs one candidate; otherwise eight are evaluated. The environment entry point accepts the same `--analysis-mode` option. Use `--analysis-mode reference --baseline-only --half-step` to reproduce the earlier strict half-step check; with fast mode, `--half-step` means a 25 ps maximum step.

`examples/compare_vco_runtime.py --reference REPORT [...] --candidate REPORT [...] --output COMPARISON` matches executed widths, conditions and physical netlist hashes. Its default coverage requirement is eight unique points. `examples/audit_vco_baseline.py REPORT [...] --bridge-site-packages PATH --output AUDIT` independently recomputes saved metrics without new simulations.

This qualification applies to the current nominal circuit and bounded width domain. It is not an exhaustive sweep of the width grid, a PVT study, a phase-noise result or evidence of transfer-learning performance. The next M6 step is to freeze the real physical metric registry, task splits and simulator budget, then run the cross-category comparison. The original qualification data and this runtime tuning must remain disclosed when defining that experiment.
