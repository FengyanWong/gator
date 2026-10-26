# Virtuoso bridge and simulation backends

## 1. Names and factual boundaries

Checked: 2026-09-19. The upstream repository is `Arcadia-1/virtuoso-bridge-lite`; the checked `pyproject.toml` names the distribution `virtuoso-bridge` and the import namespace `virtuoso_bridge`. [S2–S3](sources.md)
Do not run `pip install virtuoso-bridge-lite` based only on the repository name, or assume the local version matches current upstream.

Upstream provides SKILL execution and standalone Spectre capabilities; the two paths can be used separately. [S2](sources.md)
This does not mean every schematic/ADE export or measurement task already has a common API. Check actual local signatures and return objects before coding.

Suggested read-only checks:

```bash
command -v python
command -v virtuoso-bridge
python -m pip show virtuoso-bridge
virtuoso-bridge --help
```

Use the user's existing profile for real connection checks and respect local permissions; do not reset user configuration or deploy a new daemon merely to check it.
Upstream `AGENTS.md` and `skills/virtuoso`, `skills/spectre`, `skills/netlist` are interface-use references, not replacements for this project's research architecture.

## 2. The project's own Backend

The following names are a proposed **project Protocol**, not claims of native upstream support:

```text
healthcheck(config) -> BackendHealth
export_netlist(circuit_ref, work_dir) -> NetlistArtifact
read_parameters(circuit_ref, bindings) -> ParameterSnapshot
apply_parameters(circuit_ref, assignments, job_context) -> AppliedParameters
run_simulation(request) -> SimulationResult
collect_measurements(result, measurement_spec) -> MeasurementResult
close() -> None
```

Each method has an input schema, timeout, error categories and tests.
Explicitly return/raise `UnsupportedCapability` for unsupported capabilities; a TODO must not return success.
Methods may be combined to fit the actual code, while retaining testable boundaries.

Implementation layers:

```text
MockBackend                       # synthetic, the default for offline tests
VirtuosoBridgeBackend             # adapts verified upstream calls
Runner / MeasurementExtractor     # split if needed; no forced premature abstraction
```

A real Backend must not depend on mock. Without Cadence, explicitly retain the adapter's unconnected state; offline tests and contract tests can still be completed.

## 3. Request and result contract

A request contains `job_id`, netlist/testbench identity, candidate parameters, corner/temperature, analysis configuration, timeout, resource limits, output directory and origin type.
Verify the values that actually took effect after a parameter write, through netlist readback or verified database/variable readback; an API call without an exception does not prove a successful update.

Results contain at least:

```text
job_id / backend_kind / result_origin: real | synthetic
status / reason_code / retryable / candidate_evaluated
proposed_action / applied_parameters
metrics / metric_units / metric_validity
artifact_locations / redacted_log_summary
timing_breakdown / config_fingerprint / provenance
```

Recommended distinctions:

- `ok`: execution and required measurements finished; the evaluator separately determines whether specifications pass.
- `invalid_design`, `nonconverged`: an invalid design caused by candidate parameters or circuit behavior.
- `measurement_error`: output or metric extraction violates the contract; do not fill in normal values.
- `timeout`: further determine whether it occurred during solving, queueing or network operations.
- `transport_error`, `license_error`, `backend_error`: infrastructure or interface failure.

Do not map statuses directly one-to-one onto rewards. Infrastructure failures are generally not training examples of a poor candidate design; record retries and actual costs, and interrupt if needed.
Circuit-related failures may use declared finite penalty rules; label failures with unknown causes ambiguous instead of inventing an attribution.

### M3 condition/statistical interface

The project uses typed `PVTCorner(id, model_section, temperature_c, supply_v)` and `SimulationCondition(corner, purpose, monte_carlo)`; purpose is nominal/pvt_validation/mc_validation. `NetlistArtifact`, `SimulationRequest`, `SimulationResult` and logs retain the same context; a request cannot relabel an already generated netlist. Validate supported conditions before generating a netlist, rejecting unknown sections, out-of-range conditions and unimplemented MC before writing parameters.

`MonteCarloConfig(samples, seed, variation, model_section)` and `MonteCarloResult` reserve a future statistical execution entry point. Each sample has its own sample_index, status, validity and artifact; retain failed samples. Samples in one batch must share nominal sizes and provenance; do not mix another candidate or synthetic/real origins. Also record simulator_invocations for the batch; do not count the whole batch as one sample. The current GPDK045 adapter does not execute MC; `run_monte_carlo` explicitly reports it as unsupported.

PVT changes apply only to approved testbench job copies. The current OTA permits condition overrides of its supply, while VINP/VINN/VBIAS retain their original absolute voltages; do not silently scale biases with VDD. The graph's VDD feature must follow the executed value; PDK model contents and statistical syntax still do not enter the structural parser. Separate training context, sampling budget and post-validation budget; see the [Detailed contract](pvt-monte-carlo.md).

## 4. Execution modes and recovery

- Python may run in WSL/Linux and Virtuoso/Spectre in a Linux VM; local and remote modes use the same project API.
- Local and remote paths are separate namespaces. Verify remote file existence/digests after upload; do not pass a WSL file path directly to the VM.
- The Cadence environment may load through csh configuration; respect upstream/local settings and do not directly `source` a csh file in bash.
- Prefer an existing SSH profile; do not record passwords, disable host-key verification or assume passwordless access is configured.
- Explicitly bind the required bridge configuration so another directory's `.env` cannot change the target of a long-running process; check the local version for the binding method.
- Lock shared Virtuoso sessions. Use design copies/checkpoints and a verified restoration strategy when changing schematics.
- A netlist-only parameterization path may replace ADE only after models, corners and measurements have been verified equivalent to the original testbench.
- Use unique job directories, write input/result manifests atomically and save candidate-parameter digests; multiple jobs must not overwrite the same `input.scs`.
- Retries must be bounded and classified by cause; first query existing results by `job_id` to avoid blindly repeating expensive simulations after a lost connection.
- On timeout, stop only this job's process group or known task; do not use indiscriminate `killall spectre` / `killall virtuoso`.

## 5. Parallelism principles

Complete the real baseline with one worker before adding workers. Multiple environments sharing one policy/experience pool are a later extension, not a first-version dependency.

Independent simulation instances need independent working directories, controlled resources and independent design states, or a shared read-only design with independent netlists.
Multiple workers must not interleave changes to the same design in one Virtuoso session without locking.

Time simulation sampling separately from training updates; record CPU threads, memory, licenses, queue delay and failure rates.
Do not hard-code "7 workers" or historical speedups as an optimal configuration.

## 6. Performance and data recording

Measure at least:

```text
queue_wait / connect_or_transport / parameter_update / netlisting
simulation / transfer / measurement_parse / graph_build
policy_inference / learner_update / total_wall
```

Start by reusing connections, reducing repeated netlisting/full waveform transfers and caching static graphs, but every optimization needs regression tests.
Cache keys must cover factors affecting outputs, including executed parameters, PDK/model version identifiers, testbench, corner, simulation accuracy, measurement version and random seed.
Count cache hits separately from real calls; do not reuse unauthorized candidate results across train/test splits.

## 7. Integration acceptance

Offline tests: mock never accesses the network; inject timeouts/missing metrics/failed parameter writes; validate result structures; redact logs.
Real tests: read an explicit target → export/read its netlist → run original parameters → validate measurements → change one authorized parameter → confirm the change took effect → restore as agreed.
If real tests lack permission or a PDK, explicitly report skip/blocked; do not claim end-to-end acceptance passed.
