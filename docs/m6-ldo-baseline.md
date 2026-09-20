# M6: real LDO baseline qualification

The dedicated GPDK045 LDO now completes native CDF updates, export, DC/AC/transient measurement and `CircuitSizingEnv.reset/step`, with full parameter restoration. This is the second M6 increment, following the [synthetic category protocol](m6-cross-category.md). It qualifies a small nominal regulator testbench; real cross-category learning and VCO qualification remain pending.

## Circuit and permitted actions

[The design](../configs/gpdk045_ldo_design.json) creates `GATOR_TESTS/ldo_m6_v1` and `tb_ldo_m6_v1`. A five-MOS error amplifier drives a PMOS pass transistor. The feedback input is wired to account for the pass stage inversion. A 200 kΩ / 600 kΩ divider and ideal 0.6 V reference set a nominal 0.8 V target, using the usual `Vref × (1 + Rupper/Rlower)` relation described in [TI's LDO feedback explanation](https://www.ti.com/document-viewer/lit/html/SSZTA13/GUID-64785883-61C4-4313-9D56-938169EF979A).

The fixed testbench uses TT, 27°C, 1.0 V supply, 0.4 V ideal bias, a 10 nF ideal output capacitor and 10 µA initial load. All MOS devices have one finger and multiplicity one. The [native exported structure](../examples/circuits/gpdk045_ldo.scs) and [CDF snapshot](../examples/circuits/gpdk045_ldo.cdf.json) are actual Virtuoso outputs, not synthetic substitutes. The complete graph contains 13 devices and two mutable groups:

| Action | Baseline | Permitted range | Grid |
| --- | ---: | ---: | ---: |
| Matched M1/M2 width | 4 µm | 3.6–4.4 µm | 5 nm |
| PMOS pass width | 8 µm | 7.2–8.8 µm | 5 nm |

Lengths, other transistor widths, finger/multiplicity, divider, capacitor, sources and pulse parameters remain fixed. These are project bounds for this circuit, not inferred PDK-wide limits. Seven qualification evaluations cover baseline, input high, repeated baseline, pass high, both low, both high and restored baseline. Two further environment steps cover mixed interior settings. This samples the permitted domain; it does not enumerate or prove feasibility of every grid point.

The builder refuses existing target cells and records ownership before creation. The LDO profile separately checks complete assignments, matching, quantization, CDF geometry and every exported connection/fixed parameter. It uses the existing bridge session lock and restoration path. Both earlier OTA cores are compared before and after creation and every qualification session.

## Measurement contract

Each candidate uses one Spectre invocation containing DC operating point, load sweep, supply sweep, AC and transient analyses. Required traces and finite values are checked; missing or inconsistent data produces a measurement failure.

| Measurement | Definition / stimulus | Qualification limit |
| --- | --- | ---: |
| Output error | Absolute DC distance from 0.8 V | ≤20 mV |
| Quiescent current | Measured supply current minus measured load current | 0–8 µA |
| Line regulation | Absolute endpoint slope over 0.95–1.05 V | ≤0.1 V/V |
| Load regulation | Absolute endpoint slope over 10–20 µA | ≤1,000 V/A |
| PSRR | `−20 log10(abs(Vout/Vdd))` at 1 kHz | ≥10 dB |
| Load-step deviation | Maximum output distance from the pre-step mean | ≤50 mV |
| Tail ripple | Maximum minus minimum output in the final window | ≤1 mV |

The load steps from 10 to 20 µA at 10 µs with a 100 ns rise, then stays high through the 80 µs observation window. Transient starts from the DC operating point; maximum step is 100 ns with conservative accuracy. The pre-step mean uses 5–9 µs and the final window uses 66–80 µs. The reader validates the measured current step (`ILOAD:i`), DC consistency and time coverage. Final output shift is also reported.

These are engineering qualification thresholds established before running the baseline, not held-out transfer targets. Quiescent current includes the divider and excludes ideal reference/bias generation power. Endpoint slopes are not worst-case differential regulation. The supply sweep is a fixed characterization within the nominal package, not PVT training. Finite-window response does not establish startup, dropout, loop phase margin, stability across loads/ESR, PVT, Monte Carlo or phase noise. This small-load ideal-capacitor circuit is not a production LDO qualification.

## Results — 2026-09-19

| Baseline metric | Measured value |
| --- | ---: |
| Output | 0.792484 V |
| Output error | 7.516 mV |
| Supply power | 12.941 µW |
| Quiescent current | 2.941 µA |
| Line regulation | 0.011655 V/V |
| Load regulation | 264.518 V/A |
| PSRR at 1 kHz | 38.827 dB |
| Load-step deviation | 2.645 mV |

All seven width-check evaluations and all three environment evaluations passed their qualification criteria. Each nonbaseline width change affected both the executed deck and measured response. Repeated/restored baseline netlists and all metric values matched exactly. Two environment transitions passed the existing replay contract checks and the episode ended at its two-step horizon. No learner or replay buffer was trained; training updates were zero.

| Real cost | Spectre invocations |
| --- | ---: |
| Initial current-trace naming failure | 1 |
| Corrected baseline | 1 |
| Width/repeat/restoration checks | 7 |
| Environment reset + two steps | 3 |
| Total | **12** |

The first run completed Spectre but requested the nonexistent current-source trace `ILOAD:p`, so it was classified as `measurement_error` and retained. Installed Spectre help and raw operating-point data established `ILOAD:i`; the deck and reader were corrected before the explicit baseline rerun. There were **11 valid evaluations, one measurement failure, no automatic retries and no uncertain invocation counts**. Creation, final inspection and offline audit added zero simulator calls.

The final read-only inspection found all three cores restored, both OTAs identical to their pre-LDO snapshots, and the PDK entry/MOS file hashes identical to the M5 final inspection. This is a two-file comparison, not a recursive PDK hash. The audit checked all 12 executed decks against native export/CDF evidence and independently recomputed the ten saved metrics for all 11 successful evaluations from PSF. It also checked recorded rewards, costs and repeated baselines. Every file listed in each original export manifest, including its log, passed its SHA-256 check. The upstream PSF reader emits a metadata-only `units` length warning; actual measurement trace lengths and values are checked explicitly.

Full regression: **472 passed, zero failures and zero skips**, 209.35 seconds. The sole test warning was upstream TorchScript deprecation. The added tests cover legal actions, fixed parameters/topology, partial-write rollback, nominal-only conditions, measurement arithmetic and damaged/missing waveforms. No production source changed after that regression; the subsequent audit script was exercised on all saved real results.

Evidence:

- [Creation and protected-circuit checks](../artifacts/local/m6-ldo-baseline/build-report.json)
- [Retained initial failure](../artifacts/local/m6-ldo-qualification/7edb0b21ddde494990f89231fa6fc994/verification.json), [corrected baseline](../artifacts/local/m6-ldo-qualification/63a45d0c2f0e430f9041c82fc91d7a85/verification.json), [seven-point qualification](../artifacts/local/m6-ldo-qualification/dc87500001c44675b47a6628a3daabb2/verification.json)
- [Environment acceptance](../artifacts/local/m6-ldo-environment/5a386510f1534a3fb0424852c398d9de/verification.json), [final inspection](../artifacts/local/m6-ldo-preflight/final-inspection.json), [artifact audit](../artifacts/local/m6-ldo-audit.json)
- [JUnit report](../artifacts/local/m6-ldo-tests.xml), [machine-readable acceptance summary](../artifacts/local/m6-ldo-acceptance-summary.json)

## Reproduction and next step

Use the existing bridge 0.8.0 installation and connection. `examples/build_ldo_baseline.py` is only for first creation in an appropriate dedicated library; do not rerun it over these existing cells. The verification commands use the LDO creation receipt and never recreate the circuit:

```bash
python examples/verify_ldo_baseline.py \
  --env /path/to/bridge.env --library GATOR_TESTS \
  --creation-receipt artifacts/local/m6-ldo-baseline/creation.json \
  --model-file /absolute/spectre-host/path/to/gpdk045.scs \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/m6-ldo-qualification

# Same connection arguments; three additional real evaluations.
python examples/verify_ldo_environment.py \
  --env /path/to/bridge.env --library GATOR_TESTS \
  --creation-receipt artifacts/local/m6-ldo-baseline/creation.json \
  --model-file /absolute/spectre-host/path/to/gpdk045.scs \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/m6-ldo-environment

# Supply all verification.json files to account for failures as well as successes.
python examples/audit_ldo_baseline.py /path/to/run/verification.json \
  --bridge-site-packages /path/to/bridge/site-packages \
  --output artifacts/local/ldo-audit.json
```

The subsequent [real VCO baseline](m6-vco-baseline.md) now qualifies assisted startup/oscillation detection, measured frequency/tuning response, legal width actions and restoration. Next, freeze physical metric schemas, tasks and a separate real comparison budget. Qualification data must remain labeled as such; the observed LDO measurements cannot support a claim of blind category generalization. Historical synthetic checkpoints retain their original source-digest restriction and are not automatically migrated after these backend changes.
