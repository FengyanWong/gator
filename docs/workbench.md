# GATOR workbench: frontend, run control and data-only outputs

Local web workbench around the existing optimizer. It reads circuits, lets you define
optimization problems by hand or with agent assistance, runs the existing SAC backend, and
saves the raw data and model state needed for research analysis.

It produces **data, configurations, models, netlists and logs only**: no plots, images, PDFs,
spreadsheets or analysis reports, and no plotting library is installed or imported.

All code lives in `src/gator_workbench/` and `frontend/`. **Nothing under
`src/analog_optimizer/` is modified**, because `training/sac.py::source_digest()` hashes that
package and gates checkpoint loading and the M5/M6 audits.

## Start

```bash
# once: backend dependencies into the project environment
/tmp/analog-optimizer-venv/bin/python -m pip install -e '.[graph,web,webtest]'

# once (and after UI changes): build the UI. This machine has no Linux node; the Windows
# toolchain works through WSL interop. A native Linux node works the same way.
cd frontend && npm install && npm run build && cd ..

# run (local-only listening by default)
PYTHONPATH=src /tmp/analog-optimizer-venv/bin/python -m gator_workbench.cli serve --port 8765
# then open http://127.0.0.1:8765 in the Windows browser
```

Options: `--allow-root DIR` adds an allowed **output** root, `--allow-input-root DIR` an allowed
**netlist input** root. Roots can only be added by the operator here (or with
`GATOR_WORKBENCH_ALLOWED_ROOTS`), never from the browser, an imported file or an agent.
`--host` other than localhost prints a warning: there is no authentication layer.

UI development: `cd frontend && npm run dev` (Vite on 127.0.0.1:5173, proxying `/api`).

Without the UI:

```bash
PYTHONPATH=src python -m gator_workbench.cli validate  my.config.json
PYTHONPATH=src python -m gator_workbench.cli run       my.config.json      # foreground run
PYTHONPATH=src python -m gator_workbench.cli aggregates outputs/mock/<experiment>
PYTHONPATH=src python -m gator_workbench.cli check     <profile-id> [--scope full]
```

## What is real and what is mock

| Path | Status |
|---|---|
| `synthetic:*` tasks, imported netlists | **MOCK**: the optimizer's analytic toy backend (`origin=synthetic`). Every row says `provenance=mock`, data lives under `<output_root>/mock/`, and it is excluded from real-experiment aggregates. The `score` is not a circuit metric. |
| `real:gpdk045_*` tasks | The verified bridge profiles through the existing `NativeEnvironmentFactory`. Need virtuoso-bridge 0.8.0 importable by the backend interpreter, a connection profile, a passing connection gate and an explicit budget authorization. **Not exercised in this delivery** (see the status record). Nothing ever falls back to mock. |
| Arbitrary native cellviews | Read-only browsing through the bridge. Optimizing one needs a verified circuit profile; writing a native schematic is not implemented (contract returned by the API). |

## Connection profiles (section 2.1)

`configs/local/workbench/bridge_connection.json` (git-ignored; operator-owned):

```json
{"active": "lab",
 "profiles": {"lab": {"env_file": "/home/me/.virtuoso-bridge/.env", "profile": null,
                      "library": "MY_LIB", "creation_receipt": "/path/receipt.json",
                      "model_file": "/remote/pdk/models/spectre/model.scs",
                      "reference_measurements": "/path/baseline_measurements.json",
                      "bridge_site_packages": "/home/me/virtuoso-bridge-lite/.venv/lib/python3.10/site-packages"}}}
```

The browser only ever sends the profile **identifier**. The check is read-only and zero-cost,
runs in a short-lived process with the same interpreter and environment as a run worker, names
the broken layer, and never starts, restarts or stops the tunnel, the daemon or Virtuoso. If the
tunnel is down it tells you the command to run yourself (`virtuoso-bridge start`).
Results go to `configs/local/workbench/connection_checks.jsonl`, never into research tables.

## Output layout

Default root `<repo>/outputs` (remembered; selectable among allowed roots; writability is tested;
a Windows path is shown only after a token written through Linux was read back through Windows).

```text
<output_root>/[mock/]<experiment_name>__<experiment_id>/
  experiment.json  split_manifest.json  data_dictionary.json
  aggregates/{run_summary,budget_success,budget_success_grouped,paired_runs,transfer_summary,cumulative_cost}.csv (+ .meta.json)
  runs/<task_name>/<mode>__seed<seed>__<run_id>/
    run_manifest.json  effective_config.json  run_summary.json  artifact_manifest.json  status.json
    input_snapshot/{circuit.json, netlist.scs, hierarchy.json, parameter_mapping.json, pdk_reference.json}
    data/{evaluations,parameters,metrics,simulator_jobs,learner_updates,transitions,states}/part-*.parquet
    data/states/static/*.json      de-duplicated graph/spec templates
    data/_journal/                 wal.jsonl (acknowledgement), flushes.jsonl (visible parts), dispatch.jsonl
    best_design/{best_feasible.json, best_infeasible.json, parameters.csv, optimized_dut.scs}
    checkpoints/<id>/{training_state.pt, model_weights.pt, metadata.json, replay_buffer/manifest.json}
    checkpoints/{latest.json, best_policy.json}
    waveforms/  logs/{events,errors}.jsonl  exports/  control/  work/
```

Mapping to the recommended layout of the specification:

* `input_snapshot/dut.scs` + `testbench.scs` -> **`netlist.scs` + `hierarchy.json`** when the source is
  one combined netlist. No empty placeholder files are created; the manifest says so.
* `checkpoints/<id>/replay_buffer/...` -> the replay snapshot is **embedded in `training_state.pt`**
  (written by the existing `SACLearner.save`), so weights, replay and counters can never come from
  different moments. `replay_buffer/manifest.json` lists its members so it can be checked against
  the complete `transitions` archive without unpickling.
* A part file belongs to the dataset only if `data/_journal/flushes.jsonl` lists it.

Three things that are deliberately not the same:
`latest` (most recently safely saved state) / `best_policy` (only by an explicit validation-set
rule, otherwise explicitly `not_selected`) / `best_design` (a circuit parameter set, not a model).
And: first-feasibility cost vs. final run cost; the complete `transitions` archive vs. the finite
replay snapshot; an agent conversation `--resume` vs. an RL training `resume`.

## Reload saved data

```python
from gator_workbench.storage import DatasetReader
from gator_workbench.trajectory import TrajectoryLoader
rows = DatasetReader('<run>/data').rows('evaluations')            # fixed snapshot
transitions = TrajectoryLoader('<run>').transitions()             # optimizer Transition objects, validated
```

## Agent providers

`ClaudeCodeProvider` (default when `claude` is on the backend PATH), `CodexProvider`,
`DisabledProvider` (task-description export + structured-result import). Proposals only:
prompt on stdin, argv array, no shell, no write/exec tools, no permission bypass; applying needs an
approval bound to the proposal, configuration and circuit hashes. Agent model/effort/timeout are
independent of RL checkpoints and simulation budgets, and agents are never in the SAC loop.

Bridge skills exist in `~/virtuoso-bridge-lite/skills/` and the project's Codex-style
`.agents/skills/`, but **not** in a Claude Code discovery location. `GET /api/agent/diagnostics`
reports this and proposes (never executes) symlinks into `.claude/skills/`.

## Tests

```bash
/tmp/analog-optimizer-venv/bin/python -m pytest tests/workbench -q
```

Provider tests use a fake CLI fixture; connection tests use fake bridge clients and a fake probe
process. No test starts a real agent session or contacts a real Virtuoso.
