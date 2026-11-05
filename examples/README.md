# Example scripts

These 46 Python files are research entry points and support modules, not a startup sequence for the workbench.
The table describes source at `18fe81e` (2026-10-25); it does not report a fresh execution or authorize a simulation.
For the browser workflow, use [the workbench reference](../docs/workbench.md).

Every existing Python file here is protected during the readability work. A **pinned: never edit** label identifies
an explicit file dependency of the historical M5/M6 plans or VCO requalification; changing even whitespace breaks
that evidence identity. Other experiment manifests can pin additional files, so absence of the label is not permission
to edit a script. Real circuit creation, parameter writes and simulator calls need the user's explicit authorization.

## Historical checkout rule

The old built-in OTA and VCO tasks/cells were removed in 2026-09-23, followed by the OTA7 and LDO tasks and their
example configurations/netlists on 2026-09-30. The scripts remain as research history. Rows marked with removed
OTA7/LDO files cannot be made current by replacing their inputs with another circuit.

Revalidation uses the recorded source commit, dependency versions, named files and expected paths of the original
experiment, including a checkout before the relevant deletion where needed; merely choosing any old checkout does
not satisfy a saved source digest. Preserve the original run evidence and keep these historical entry points away
from an active experiment's settings or cells. See [repository rules](../CLAUDE.md),
[project decisions](../docs/decisions.md) and [README history](../docs/history-readme-milestones.md).
The original M5 six-method protocol with `port_gnn` requires its historical source; current M5 entry points explicitly
select the surviving encoders instead of reproducing that removed method.

## Training

| Script | Purpose | Scope and protection |
|---|---|---|
| [train_synthetic_sac.py](train_synthetic_sac.py) | Train one group SAC learner on two analytic toy circuits and check exact checkpoint continuation. | Synthetic; writes training artifacts. |
| [train_opamp_sac_smoke.py](train_opamp_sac_smoke.py) | Run the bounded real M4 learner acceptance and restore the starting OTA design. | Historical real OTA setup; runs Spectre. |
| [train_opamp_sac_parallel.py](train_opamp_sac_parallel.py) | Train or resume OTA SAC with serial native CDF preparation and up to four Spectre workers. | Historical real OTA setup; runs Spectre; this entry point retains its own four-worker cap. |

## Benchmarks

| Script | Purpose | Scope and protection |
|---|---|---|
| [benchmark_encoders.py](benchmark_encoders.py) | Preview the budget or explicitly execute a synthetic comparison of current encoders and structural settings. | Synthetic; execution requires `--execute`. |
| [benchmark_cross_category.py](benchmark_cross_category.py) | Run the synthetic M6 leave-one-class-out protocol with independently trained source policies. | Synthetic; `--dry-run` previews; entrypoint hash recorded. |
| [benchmark_transfer.py](benchmark_transfer.py) | Run M5 synthetic topology comparisons or a bounded real same-topology specification comparison. | Synthetic by default; `--origin real` runs Spectre; entrypoint hash recorded. |
| [benchmark_real_topology.py](benchmark_real_topology.py) | Compare specification and new-topology transfer across independently qualified real OTA profiles. | **pinned: never edit** (M5); historical OTA7 files removed. |
| [benchmark_real_cross_category.py](benchmark_real_cross_category.py) | Freeze or check the physical M6 plan offline, or execute that exact saved plan. | **pinned: never edit** (M6); historical LDO files removed; execution runs Spectre. |
| [benchmark_input_cache.py](benchmark_input_cache.py) | Measure synthetic input-cache and learner-update timings without a circuit simulator. | Offline timing; writes measurements. |
| [benchmark_recording.py](benchmark_recording.py) | Exercise recorder, replay and checkpoint I/O with injected MockBackend evaluations. | Synthetic; records its own source file among project assets. |
| [benchmark_recording_overhead.py](benchmark_recording_overhead.py) | Compare JSON and SQLite recording costs and replay readback using matched injected evaluations and updates. | Offline timing; no Spectre or SSH. |

## Audits and recording summaries

| Script | Purpose | Scope and protection |
|---|---|---|
| [audit_cross_category.py](audit_cross_category.py) | Audit a trusted synthetic M6 suite for split leakage, recorded evaluations and checkpoint recovery. | Saved artifacts; no new backend evaluations. |
| [audit_real_topology.py](audit_real_topology.py) | Audit the saved real M5 topology comparison against its source, circuit files and candidate evidence. | Historical OTA7 files removed; no new simulation. |
| [audit_real_cross_category.py](audit_real_cross_category.py) | Recompute saved physical M6 metrics and check frozen-plan and checkpoint consistency. | Historical LDO files removed; no bridge connection or new simulation. |
| [audit_ldo_baseline.py](audit_ldo_baseline.py) | Audit recorded LDO qualification jobs and their saved measurements. | Historical LDO files removed; no Virtuoso or Spectre invocation. |
| [audit_vco_baseline.py](audit_vco_baseline.py) | Audit recorded VCO qualification jobs and their saved measurements. | Saved artifacts; no Virtuoso or Spectre invocation. |
| [save_recording_summary.py](save_recording_summary.py) | Write a human-readable snapshot beside an existing recording database. | Reads the database and writes a summary file. |

## Baselines, circuit qualification and support

| Script | Purpose | Scope and protection |
|---|---|---|
| [build_opamp_baseline.py](build_opamp_baseline.py) | Create a dedicated GPDK045 five-transistor OTA and export its AC testbench while refusing existing target cells. | Historical real setup; writes new Virtuoso cells. |
| [build_two_stage_ota.py](build_two_stage_ota.py) | Create an independent two-stage OTA while protecting the original OTA and holding its session lock. | **pinned: never edit** (M5); historical OTA7 files removed; writes Virtuoso cells. |
| [build_ldo_baseline.py](build_ldo_baseline.py) | Create a dedicated six-MOS LDO while protecting both OTA circuits and refusing existing target cells. | Historical LDO files removed; writes Virtuoso cells. |
| [build_vco_baseline.py](build_vco_baseline.py) | Create an owned three-stage NMOS-current-limited ring VCO while refusing existing target cells. | Historical real setup; writes new Virtuoso cells. |
| [simulate_opamp_baseline.py](simulate_opamp_baseline.py) | Simulate a real DC/AC baseline from a verified exported OTA structure and an explicit TT deck. | Historical real setup; runs Spectre. |
| [verify_opamp_backend.py](verify_opamp_backend.py) | Check the bridge adapter with a width perturbation and restoration of the original OTA. | Historical real setup; changes sizes and runs Spectre. |
| [verify_opamp_environment.py](verify_opamp_environment.py) | Check real environment resets, bounds, seeded random candidates, a repeated candidate and restoration. | Historical real setup; changes sizes and runs Spectre. |
| [verify_two_stage_ota.py](verify_two_stage_ota.py) | Commission the real two-stage OTA and verify its independent width groups with retained qualification calls. | **pinned: never edit** (M5); historical OTA7 files removed; runs Spectre. |
| [verify_ldo_baseline.py](verify_ldo_baseline.py) | Qualify the dedicated LDO with bounded native CDF changes and restoration. | Historical LDO files removed; runs Spectre. |
| [verify_ldo_environment.py](verify_ldo_environment.py) | Check LDO reset/step behavior through real qualification evaluations without learner updates. | Historical LDO files removed; runs Spectre. |
| [verify_vco_baseline.py](verify_vco_baseline.py) | Qualify the dedicated VCO with bounded native CDF changes, analysis-mode selection and restoration. | Historical real setup; runs Spectre. |
| [verify_vco_environment.py](verify_vco_environment.py) | Check VCO reset/step behavior through real qualification evaluations without learner updates. | Historical real setup; runs Spectre. |
| [analyze_opamp_baseline.py](analyze_opamp_baseline.py) | Extract and print measurements from a saved real OTA baseline job. | Saved simulation data; no new simulation. |
| [compare_opamp_baseline.py](compare_opamp_baseline.py) | Compare saved baseline, perturbation and repeat jobs and write their measured AC plots. | Historical research tool; writes JSON and plots outside the data-only workbench flow. |
| [compare_vco_precision.py](compare_vco_precision.py) | Compare trusted saved baseline and half-step VCO artifacts. | Saved artifacts; no new simulation. |
| [compare_vco_runtime.py](compare_vco_runtime.py) | Compare saved fast-policy VCO evaluations with reference runs at matching widths. | Saved artifacts; no new simulation. |
| [requalify_vco_designs.py](requalify_vco_designs.py) | Freeze, check, execute or compare strict-reference requalification of saved feasible VCO designs. | **pinned: never edit** (M6 requalification); only execution uses the bridge and Spectre. |
| [vco_requalification.py](vco_requalification.py) | Provide frozen-plan, execution and comparison helpers for strict-reference VCO requalification. | **pinned: never edit** (M6 requalification); helper module, not a standalone CLI. |
| [opamp_connection.py](opamp_connection.py) | Provide explicit bridge-connection arguments and the verified OTA profile to real example entry points. | Support module; a historical real-circuit contract. |

## Reward qualification

| Script | Purpose | Scope and protection |
|---|---|---|
| [check_reward_identity.py](check_reward_identity.py) | Recompute default rewards from manifest-listed real M6 records without loading learners. | Saved-data arithmetic; no new simulation. |
| [freeze_reward_v2_baseline.py](freeze_reward_v2_baseline.py) | Snapshot source, dependency, task and protected-file provenance for the reward-v2 baseline. | Historical removed OTA7 task; no backend connection. |
| [qualify_reward_v2_real.py](qualify_reward_v2_real.py) | Freeze, preflight or execute bounded real reward-v2 qualification against its pinned OTA7 manifest. | Historical OTA7 task/files removed; execution runs Spectre. |
| [qualify_reward_v2_learning.py](qualify_reward_v2_learning.py) | Run the real workbench learning and recovery acceptance stages after qualified reward-v2 Stage A. | Historical OTA7 task/files removed; runs Spectre and learner updates. |
| [report_reward_v2_acceptance.py](report_reward_v2_acceptance.py) | Write the provenance report from saved evidence of the license-blocked reward-v2 implementation. | Historical OTA7 task and evidence paths; no new tests or simulations. |
| [report_reward_v2_real_acceptance.py](report_reward_v2_real_acceptance.py) | Audit saved real reward-v2 qualification evidence and protected-file identity. | Historical OTA7 task and evidence paths; no new simulation. |

## Imports and parser entry point

| Script | Purpose | Scope and protection |
|---|---|---|
| [netlist_demo.py](netlist_demo.py) | Delegate to the package CLI that parses a netlist and displays its graph and optional PyG representation. | Offline parser entry point. |
| [import_analoggym.py](import_analoggym.py) | Import the pinned AnalogGym-Opt benchmark into local task settings without copying its models into GATOR. | Writes local settings; no simulation. |
| [check_analoggym.py](check_analoggym.py) | Check local parity against the independent original AnalogGym testbenches after import. | Runs ngspice; no provider requests. |
| [calibrate_analoggym.py](calibrate_analoggym.py) | Run free calibration and independently re-simulate every passing design with the upstream testbenches. | Runs ngspice and writes results; no provider requests. |

## Where the pins come from

| Evidence contract | Script files pinned explicitly | Definition and verification |
|---|---|---|
| M5 real topology | `benchmark_real_topology.py`, `verify_two_stage_ota.py`, `build_two_stage_ota.py` | `project_files` in [benchmark_real_topology.py](benchmark_real_topology.py) is hashed into provenance; [audit_real_topology.py](audit_real_topology.py) checks every listed file. |
| M6 physical pilot | `benchmark_real_cross_category.py` | [real_category.build_plan](../src/analog_optimizer/evaluation/real_category.py) hashes the entry point; `validate_frozen_plan` rebuilds and compares the saved plan before the physical audit. |
| M6 VCO requalification | `vco_requalification.py`, `requalify_vco_designs.py` | `SOURCE_FILES` in [vco_requalification.py](vco_requalification.py) becomes `source_hashes`; revalidation rebuilds and compares the frozen plan. |

These contracts also pin inputs outside this folder:

- M5 real topology lists its OTA/OTA7 design, mapping and transfer configurations, conditions, structure netlists and
  CDF readbacks beside the three script files.
- Synthetic M6 [load_categories](../src/analog_optimizer/evaluation/cross_category.py) hashes the manifest, each
  configured mapping and fixture netlist, and the mapping's model file by resolved path; it does not name an example
  script in that file map.
- Physical M6 [load_physical_categories and build_plan](../src/analog_optimizer/evaluation/real_category.py) hash the
  manifest, designs, mappings, netlists, readbacks, referenced model mapping files, conditions, run bindings and
  qualification evidence, while the optimizer source digest and dependency versions are checked separately.

Those named configurations and fixtures must remain unchanged as well. In addition,
[benchmark_transfer.py](benchmark_transfer.py) and [benchmark_cross_category.py](benchmark_cross_category.py) record
their entrypoint hashes; [benchmark_recording.py](benchmark_recording.py) records its source as a project asset.
The [reward baseline snapshot](freeze_reward_v2_baseline.py) hashes all example Python files, configuration JSON files
and synthetic netlists present when it is made, and [its real acceptance report](report_reward_v2_real_acceptance.py)
checks those protected hashes. Consult the saved manifest to know which historical file set it covers.
