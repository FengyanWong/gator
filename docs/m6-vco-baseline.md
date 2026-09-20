# M6: real VCO baseline qualification

This increment adds a dedicated GPDK045 three-stage ring VCO, physical oscillation/tuning measurements and three independently writable stage-current widths. It follows the [LDO qualification](m6-ldo-baseline.md). Both are engineering preparation for a later real cross-category experiment; neither establishes a transfer advantage.

The results below use the original strict settings. The later [runtime qualification](m6-vco-runtime.md) makes a validated fast policy the default; pass `--analysis-mode reference` to reproduce this document's runs.

## Circuit and execution contract

`GATOR_TESTS/vco_m6_v1` contains three CMOS inverters, each with an additional NMOS current limiter and a 50 fF stage capacitor. The three limiter gates share `VCTRL`; the last inverter feeds the first. The dedicated testbench is `tb_vco_m6_v1`. The builder refuses existing cells and checks the earlier OTA/LDO core snapshots before and after creation. [Design configuration](../configs/gpdk045_vco_design.json), [native exported structure](../examples/circuits/gpdk045_vco.scs) and [native CDF snapshot](../examples/circuits/gpdk045_vco.cdf.json) describe the actual circuit.

The fixed inverter widths are NMOS 1 µm / PMOS 2 µm, with 100 nm lengths. Current limiters use 500 nm length and 1 µm baseline width. All devices have one finger and multiplicity one. The graph has 14 devices: nine MOS, three capacitors and two voltage sources.

Three actions independently set MS1/MS2/MS3 width to 0.9–1.1 µm on a 5 nm grid. Other dimensions, stage loads and sources remain fixed. These are project bounds for this circuit, not a claim about every legal PDK geometry. Each update runs native PDK callbacks, reads back complete CDF geometry, checks fixed parameters and connections, and exports a fresh native netlist. The VCO profile preserves the existing backend's locking, rollback and restoration contracts.

Each candidate has one Spectre invocation containing nominal DC operating-point information and three separately initialized transients at control voltages 0.55, 0.65 and 0.75 V. Supply is 1.0 V, TT, 27°C throughout. Each transient runs for 2 µs with conservative accuracy, a 100 ps maximum step, explicit selected traces and its own initial-condition solve. These control voltages are fixed characterization stimuli, not extra policy actions or PVT conditions. The graph stores the nominal 0.65 V control source; the three-point measurement protocol accompanies every candidate.

The deck declares `ic VOUT=0 XU1.N1=1 XU1.N2=0`, with `ic=all skipdc=no useprevic=no restart=yes`. Initial conditions can initiate oscillation by introducing a state inconsistent with an odd inverter loop, as explained by [Cadence](https://community.cadence.com/cadence_technology_forums/f/mixed-signal-design/48967/pss-failure-for-a-ring-vco/1377269). This is **initial-condition-assisted startup**, not proof of physical startup from thermal noise, a power ramp or arbitrary initial states. Installed Spectre `ic`, `alter` and `tran` help was checked before executing the deck.

## Measurements and rejection rules

Every stage output at every control voltage must establish full-swing periodic behavior. Frequency comes from linearly interpolated rising crossings at half the measured nominal supply. Measurements use complete cycles in 1–2 µs, with at least eight complete cycles in **each** half-window. The maximum actual sample gap must be no more than one fortieth of the shortest measured period.

Each cycle must cross downward exactly once, reach below 0.2 V and above 0.8 V, and have at least 0.8 V swing. Period spread must be at most 2%; the two half-windows' mean periods must agree within 1%. All three stages must agree in frequency within 1%, and frequency must increase from low through nominal to high control voltage. Flat, decaying, stopped, sparse, drifting or incomplete traces fail explicitly; no zero or invented frequency is returned as a valid measurement.

Startup detection is the completion time of the first eight consecutive full-swing cycles whose periods agree with the eventual median within 2%. Detection must occur before 1 µs. This definition includes eight cycles of observation latency and depends on the declared initial conditions. It is not an extrapolated silicon startup time.

Mean supply power uses the time integral of `−VDD × I(VDD:p)` over the exact 1–2 µs window, with interpolated window endpoints; a plain mean of nonuniform samples would be incorrect. The report also saves duty cycle, minimum cycle swing across all stages/control points, three frequencies, endpoint tuning gain and `(f_high − f_low) / f_nominal`. DC MOS operating points describe the static nominal equilibrium, not transistor behavior resolved over the oscillation phase.

Qualification thresholds were declared before the baseline: nominal frequency 1 MHz–1 GHz, supply power 0–1 mW, minimum swing 0.8 V, tuning fraction at least 0.05, period spread at most 0.02, window drift at most 0.01, startup detection within 1 µs and nominal duty cycle 0.05–0.95. Oscillation validity checks further constrain usable data. These broad engineering thresholds are not held-out learning targets.

## Baseline results

| Control voltage | Measured frequency |
| --- | ---: |
| 0.55 V | 80.1496 MHz |
| 0.65 V | 171.1402 MHz |
| 0.75 V | 274.0147 MHz |

| Other baseline measurements | Value |
| --- | ---: |
| Nominal mean supply power | 26.5558 µW |
| Endpoint tuning gain | 969.3257 MHz/V |
| Minimum cycle swing, all stages/controls | 0.89856 V |
| Nominal output duty cycle | 0.58451 |
| Maximum deterministic period spread | 2.736 × 10⁻⁶ |
| Latest eight-cycle startup detection | 108.33 ns |

The [first baseline](../artifacts/local/m6-vco-qualification/63ee40603ec84dc79fcbd87418f556b4/verification.json) passed and restored all circuit snapshots. Its [independent audit](../artifacts/local/m6-vco-baseline-audit.json) recomputed all metrics from the saved PSF with a separate NumPy implementation, and verified native CDF/export data and file hashes without another simulator invocation.

The [eight-point width qualification](../artifacts/local/m6-vco-qualification/6941f65010d7404091538abf622473b2/verification.json) passed: each individual stage increase, all-low and all-high widths, and two baseline repeats. Nominal frequency spans 158.2056 MHz at all-low widths to 183.8491 MHz at all-high widths. Each changed setting affected the executed deck and measured response; repeated baseline deck hashes and every metric matched exactly. All four core snapshots were restored.

The [half-step run](../artifacts/local/m6-vco-precision/ed8224bb49ee454086d56107878a4922/verification.json) and [numerical comparison](../artifacts/local/m6-vco-precision-comparison.json) passed. The only deck changes were the three maximum timesteps, 100→50 ps. Predeclared tolerances were 0.1% relative frequency/tuning, 0.5% relative power, 1 mV absolute swing, 0.001 absolute duty and 2 ns startup-detection time. Maximum frequency change was 0.000526%, at low control; nominal frequency changed 0.00000203%. This checks sensitivity to that numerical setting, not every possible simulator accuracy choice.

Regression acceptance covers **495 distinct tests, all passing with no skips**. The initial sandbox run passed 487 and failed eight when Python multiprocessing tried to open local IPC sockets. Those same eight passed with local sockets enabled; there were no code changes between the runs. Both [initial JUnit](../artifacts/local/m6-vco-tests.xml) and [IPC rerun JUnit](../artifacts/local/m6-vco-ipc-tests.xml) are retained. The sole test warning was upstream TorchScript deprecation. New tests cover native three-action graphs, fixed circuit/stimulus rejection, partial-write rollback, bounded conditions, oscillation failure cases and nonuniform power integration.

The [environment run](../artifacts/local/m6-vco-environment/ba0febe1374542d8b9136e24301ff62d/verification.json) passed reset plus two mixed interior width actions. Both transitions passed the existing replay contract; the episode terminated at its two-step horizon and all four circuit snapshots were restored. No replay buffer or learner was trained.

| Real cost | Spectre invocations | Transient analyses |
| --- | ---: | ---: |
| Initial baseline | 1 | 3 |
| Width/repeat/restoration checks | 8 | 24 |
| Half-step numerical check | 1 | 3 |
| Environment reset + two actions | 3 | 9 |
| Total | **13** | **39** |

All 13 evaluations were valid and passed qualification, with zero failed simulations, automatic retries, uncertain invocations or training updates. Creation, auditing and final inspection added zero simulator calls. Including the earlier LDO increment, M6 real qualification has cost 25 Spectre invocations, including the retained LDO measurement failure.

The [combined audit](../artifacts/local/m6-vco-audit.json) joins separate [qualification/numerical](../artifacts/local/m6-vco-qualification-audit.json) and [environment](../artifacts/local/m6-vco-environment-audit.json) audits. It checks 13 unique executed jobs, all original export-file hashes, native CDF parameters, executed decks, recorded metrics/rewards and baseline repeats, and recomputes all 11 metrics per successful evaluation with an independent NumPy implementation. The [final read-only inspection](../artifacts/local/m6-vco-preflight/final-inspection.json) matches the three protected cores to pre-creation snapshots and the VCO to its native baseline snapshot. PDK entry/MOS file hashes match the preflight values; this is not a recursive PDK hash.

The [acceptance summary](../artifacts/local/m6-vco-acceptance-summary.json) records source-file hashes, tests, costs, baseline metrics, numerical comparison and restoration evidence. Raw waveforms and failures from the sandboxed test attempt remain available locally. This completes VCO qualification, not the entire M6 transfer study.

## Reproduction and limits

Use the existing bridge 0.8.0 connection and the VCO creation receipt. The builder is for first creation only; it will refuse the already-created cells. The commands below default to one worker and restore parameters on exit:

```bash
python examples/verify_vco_baseline.py --analysis-mode reference \
  --env /path/to/bridge.env --library GATOR_TESTS \
  --creation-receipt artifacts/local/m6-vco-baseline/creation.json \
  --model-file /absolute/spectre-host/path/to/gpdk045.scs \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/m6-vco-qualification
```

`--baseline-only` runs one candidate; the default runs eight. `--analysis-mode reference --baseline-only --half-step` keeps the physical circuit and stimuli fixed and halves the strict maximum timestep to 50 ps. `examples/verify_vco_environment.py` accepts the same connection arguments and analysis-mode option and runs a reset plus two steps. `examples/audit_vco_baseline.py VERIFICATION_JSON [...] --bridge-site-packages PATH --output REPORT_JSON` checks saved runs offline; include every run to retain complete costs.

No PSS/PNoise, transient noise, physical jitter, phase-noise figure of merit, power-ramp startup, PVT, Monte Carlo, load sweep, layout/parasitics or real SAC updates are included. Deterministic period variation is a numerical periodicity diagnostic, not physical jitter. Sampled width points do not prove feasibility of the entire grid. Qualification observations and their costs must be disclosed before a real transfer experiment; later targets are not blind to this circuit characterization.

The next M6 increment is to freeze a physical metric registry, category splits and a total real-call budget, then connect these qualified circuits to the existing scratch/frozen/adapt and non-RL comparisons. Historical checkpoints retain their strict source-digest restrictions.
