# GATOR: Circuit Optimization Frontend, Run Control, and Data-Only Outputs — Claude Code / Fable 5.1 Development Instructions

In the current GATOR / analog-optimizer repository, implement or incrementally improve a local web-based engineering workbench. The goals are to read circuits or create/modify them with an agent, define optimization problems manually or with assistance, launch the existing RL optimization backend, and preserve the raw data and model states needed for research analysis of generalization, knowledge transfer, and simulation efficiency.

This is a complete specification, not a request to add only a "Download CSV" button. Inspect and reuse existing capabilities. Do not rewrite the entire repository or break the existing CLI, parser, graph representation, or trainer.

For this task, produce only data, configurations, models, netlists, and logs. Do not generate training curves, scatter plots, heatmaps, images, PDFs, Excel reports, or HTML analysis reports. Do not introduce plotting libraries. The frontend may display tables, numerical values, status, progress, and file directories.

## 0. Claude Code Execution Conventions and Functional Parity

This file is a complete, standalone development specification for a Claude Code session using Fable 5.1. Reading the earlier Codex specification is not required to understand this task. Sections 1–13 below preserve the original product goals, output fields, experimental accounting conventions, and acceptance criteria in full. This version changes only development-tool integration and execution practices. Do not reduce functionality, change the SAC algorithm, or replace the data formats.

First distinguish two layers:
- You are the development agent writing the project code. The user has selected Fable 5.1 for this development task.
- The application's runtime `AgentProvider` is an optional frontend assistance feature. Preserve `ClaudeCodeProvider`, `CodexProvider`, and `DisabledProvider`. Developing with Claude Code is not a reason to remove Codex support, and users must not need to invoke a language model for every RL run.

Before execution, inspect the working directory, Git status, existing changes, and project rules. Explicitly read existing CLAUDE.md, AGENTS.md, and applicable rules in directories you will modify. Do not assume automatic loading behaves identically across all versions. If CLAUDE.md needs additions, append only concise project guidance. An existing AGENTS.md may be referenced using `@AGENTS.md` after verifying that it exists and avoiding circular references. Do not overwrite user rules or maintain two conflicting copies of the requirements. [C1]

Check which bridge skill is actually visible. Prefer instructions in installed plugins or the project, and inspect applicable `.claude/skills/<skill-name>/SKILL.md` and `~/.claude/skills/<skill-name>/SKILL.md` locations. A skill installed only in the Codex environment is not evidence that the current Claude session has loaded it. Record the actual skill name and source. Do not invent a `/virtuoso-bridge` command or treat Codex's `$skill-name` syntax as a Claude command. If the skill is missing, inspect local bridge documentation, CLI, and source first. If configuration migration is required, propose an executable installation/reference approach that preserves original files and permission boundaries. Do not substitute a fake skill with the same name. [C2]

The source specification identifies `claude-fable-5-1` as the intended model identifier. CLI model selection must respect the user's actual account, gateway, and installed version. Do not automatically change global settings, downgrade to another model, force a different authentication method, or require a new API key when the user has already selected a model. If actual model availability cannot be confirmed, report the status honestly rather than probing with repeated paid requests. [C3][C4]

Execution requirement: perform the necessary code inspection and produce a brief staged plan, then proceed to implementation, testing, and fixes. Do not stop at a plan, pseudocode, or static page. Use conservative defaults when the existing requirements determine the decision. When blocked by real permissions, credentials, PDK rules, or an unavailable environment, do not fabricate information. Continue with independent work and record the blockers.

You may use subagents already supported by the environment for independent inspections or test reviews, but they are not a prerequisite for delivery. The primary agent must coordinate the shared schema, database writes, budget ledger, and checkpoint boundaries to prevent concurrent edits to the same files. Do not automatically start many additional sessions or invoke paid agents or large Spectre workloads without authorization.

Maintain a short implementation record in a repository-approved location, such as `docs/frontend_implementation_status.md`, covering completed modules, changed files, test commands/results, confirmed interfaces, blockers, and next steps. After context compaction or resuming a development session, reread this record, the code diff, and this specification before continuing. Do not redo completed modules based solely on conversational memory. This implementation record is not a research output or analysis report. [C6]

Important: Claude conversation `continue`/`resume` concerns only development/conversation state. RL `resume` inside the application must follow the training-state and data-consistency requirements in Sections 5, 9, 10, and 12. Do not conflate their state semantics or recovery implementations.

## 1. Inspect the Existing Project and Actual Interfaces First

Read CLAUDE.md, AGENTS.md, PROJECT_SPEC.md, README, existing skills, configuration schemas, backend code, trainers, and checkpoint implementations to establish the current implementation status. Record missing files honestly; do not fabricate their contents to pass an inspection.

Project architecture:

```text
Virtuoso/Spectre → canonical circuit IR → port-aware graph
→ Graph Transformer/GNN + goal-conditioned SAC → parameter optimization
```

The integration target is `Arcadia-1/virtuoso-bridge-lite`. Verify the APIs against the locally installed `virtuoso_bridge` package, CLI, skills, and source code. Do not invent methods or silently replace it with another similarly named project. Preserve existing working adapters.

The user's project has previously been located at `/mnt/d/gator`, corresponding to `D:\gator` on Windows. Use the actual working directory; do not hard-code this path. A Windows browser connects to the WSL backend, while Virtuoso/Spectre may run inside VMware Linux or on a remote host. Configure connection profiles, paths, and credentials through the existing mechanisms. Do not hard-code IP addresses or accounts.

Prefer the existing web technology stack. If none exists, use React + TypeScript + Vite with a Python FastAPI backend. Training and simulation must run in independent workers; their lifetimes must not depend on a single HTTP request or agent CLI session.

## 2. Page Layout and Circuit Entry Points

Left: project, connection status (Section 2.1), circuit source, hierarchy tree, and DUT/testbench selection.

Center: editable tabs for "Optimization Parameters / Performance Targets / Measurement Definitions."

Right: persistently visible "Run Configuration / Output Settings."

Bottom: agent conversation, logs, run status, data tables, and output file list.

Support:
- Selecting a Virtuoso library/cell/view through the bridge and reading the native schematic.
- Selecting an existing testbench and specifying the DUT hierarchy.
- Importing a Spectre netlist supported by the existing parser.
- Using a prompt to propose circuit creation or modification.

A schematic, DUT, and testbench are not three files that must be uploaded separately. Allow the DUT to be identified within a testbench, or start from a DUT and add the required test configuration.

Query/export native databases through the bridge. Do not parse Cadence databases as text. Read instance paths, models, nets/ports, parameters and expressions, explicit design variables, available analyses, loads, supplies, and ADE outputs. Mark unknown information as requiring confirmation. Do not guess PDK port order or parameter semantics.

Prompt-driven modification workflow: proposal → structured diff → user confirmation → execution on a working copy/new cellview → reread and validate. Do not overwrite the original design or PDK libraries by default. Generating a netlist does not mean a native schematic has been generated.

After a circuit changes, revalidate variable references, measurement nodes, the test environment, and checkpoint compatibility.

### 2.1 Virtuoso / Bridge Connection Check

Added 2026-09-20. This section adds a requirement that the earlier specification lacked; it removes nothing from Sections 1–13.

Everything in Section 2 depends on a chain the user cannot otherwise see: Windows browser → WSL backend → bridge package → SSH tunnel → bridge daemon inside the Virtuoso CIW → Spectre host and license. Provide a way to check that chain without spending simulation budget, and report which link is broken rather than a generic "connection failed."

Show a persistently visible connection indicator beside the circuit source in the left panel, with a detail view listing every layer, its state, a reason code, a concise diagnostic, the time of the last check, and its duration. Check the layers in dependency order:

1. Bridge package: importable through the same interpreter and import path that the backend and run workers actually use; its installed version; and whether that is the version the existing adapter has verified. A bridge installed only in another virtual environment is `bridge_not_importable`, not a Virtuoso failure.
2. Connection profile: the env file and explicitly named profile that a run would use, and whether the required settings are present. Never display keys, tokens, or passwords.
3. Tunnel: running or not running; `not_applicable` in local mode.
4. Daemon / Virtuoso CIW: one trivial read-only SKILL round trip with a short timeout. Distinguish `no_response` (Virtuoso not running, or the bridge setup not loaded in the CIW), `auth_failed`, and a daemon identity/user mismatch.
5. Session readiness: conditions under which the existing adapter already refuses to run, such as conflicting open ADE/Maestro windows. Report these as `not_ready` with the reason, separately from connectivity.
6. Spectre: the executable is found on the resolved Spectre host.
7. Spectre license: what the license server reports. This may be slow, so it may be a separately triggered step.

Per-layer states are `ok`, `failed`, `not_ready`, `not_applicable`, `not_checked`, `busy`, and `unknown`. Mark every layer downstream of a failure as `not_checked`, never as `ok` or `failed`. Before the first check, and once the last result is older than a configurable staleness limit, show `unknown` with the result's age; never present a cached `ok` as current. A license query is a snapshot: it must not check out or hold a seat, and it does not guarantee that a later simulation will obtain one. Say so in the interface.

Each action declares the layers it needs. Reading or writing a native cellview needs layers 1–4 plus any readiness condition that applies to that operation; launching any real simulation needs all layers. Importing a Spectre netlist, manual editing, JSON import/export, data export, and mock runs need none and must keep working while the bridge is down.

"Test connection" is a user-triggered, read-only, zero-cost action. It launches no Spectre simulation, reserves and charges no evaluation budget, creates no `evaluations` or `simulator_jobs` rows, opens no cellview for editing, and writes to no library. It is not the baseline simulation of Section 9, which remains a costed evaluation.

Map each layer onto capabilities that actually exist in the locally installed bridge, under the verification rule in Section 1. As inspected on 2026-09-20, the installed `virtuoso-bridge` 0.8.0 provides `virtuoso-bridge status` (tunnel, daemon, Spectre) and `virtuoso-bridge license`, both accepting `-p/--profile` and `--env` and both printing human-readable text with no JSON mode; `SSHClient.is_running(profile)`; SKILL execution through `VirtuosoClient`; `list_windows()`; and `SpectreSimulator.check_license()`. Reconfirm these against the local source before relying on them, and do not invent a health API. Prefer structured Python calls over scraping CLI text. Where only text is available, isolate the parser, test it against captured fixtures, and report unparseable output as `unknown`.

An `ok` result must predict what a run will experience. Use the same interpreter, import path, env file, and explicit profile as the run workers; a background web process may not share the development session's HOME, PATH, virtual environment, or SSH agent, and the diagnostics must expose such differences. Reuse the existing adapter's readiness rules by calling or mirroring them, so that the panel and the adapter never hold two definitions of "ready." If the repository gates checkpoint loading or audit reproduction on a digest of the existing package's source files (verify locally), implement the probe outside that package rather than adding or editing files inside it.

The check observes; it never repairs. Do not start, restart, or stop the tunnel, the daemon, or Virtuoso as a side effect of a check, on page load, or on a timer. The existing adapter deliberately requires an already-running tunnel and refuses automatic startup; preserve that policy. On failure, show the specific next step, including the exact command for the user to run in their own terminal. Do not acquire the adapter's session lock, call its full `connect()` sequence, or borrow a running worker's client for a probe: that client is bound to its owning thread, and `connect()` reads, and later restores, design state. Use a separate short-lived probe with its own timeout, run it off the HTTP request thread, coalesce concurrent requests for the same profile, and on cancellation clean up only the probe's own resources.

The browser supplies only the identifier of a configured profile. Do not accept hostnames, ports, paths, or commands from the request, and invoke any CLI with an argument array, never through a shell. Keep credentials, tokens, and raw license-server output, which can name other users and hosts, out of results, logs, and agent inputs.

Automatic checks are limited to the cheap layers: once at backend start or profile change, at the gate below, and optionally at a low configurable interval that is off by default while a run is active. During a run the CIW may be occupied by the worker's own SKILL calls, so a probe timeout then means `busy`, not `failed`; prefer reporting the worker's most recent successful bridge interaction. Several open browser tabs must not multiply probes.

Pre-dispatch gate: before "single baseline simulation," "start," "continue," and the execution of an approved circuit modification, check the layers that action needs and block it when any is not `ok`. An `unknown` layer is a warning the user must acknowledge; it is neither treated as `ok` nor silently ignored. A blocked start is not a failed run: reserve no budget, create no run directory, add nothing to aggregates, and record the refusal in the application log. Never fall back silently to mock mode or to another profile.

A failed check does not by itself stop a run. When evaluations fail because the link is lost, classify them with a distinct infrastructure failure type, such as `bridge_unreachable`, `daemon_no_response`, or `license_unavailable`, so they remain distinguishable from circuit and convergence failures in `evaluations` and `simulator_jobs`. How such failures enter training follows the existing trainer; do not change the algorithm. Budget accounting follows Section 9 unchanged: an evaluation that actually began is not refunded. Because of that, after a configurable number of consecutive infrastructure failures, counted in completion order across workers, stop new dispatches, run the check to record the failing layer, and perform the safe pause sequence of Section 12 instead of spending the remaining budget against a dead link. Continuing requires the gate to pass again.

Store check results in an application-level diagnostics log (JSONL: timestamp, profile identifier, trigger `user`/`gate`/`auto`, per-layer state and reason code, duration, redacted diagnostic), never in research tables or aggregates. Record in `run_manifest.json` the gate result that admitted the run, and record in-run connection events in `logs/events.jsonl`.

Test with fake bridge clients and captured CLI output by default; do not contact a real Virtuoso during unit tests, builds, or frontend startup. Cover at least: bridge not importable; unverified bridge version; missing or incomplete env file/profile; implicit profile binding; tunnel not running; local mode without a tunnel; daemon no response, authentication failure, and user mismatch; conflicting ADE/Maestro windows; Spectre not found; license unavailable, not yet checked, and not checkable; probe timeout; `busy` during an active run; stale results; downstream layers `not_checked`; zero budget charged and zero evaluation/job rows created; a blocked start creating no run directory; acknowledgment of `unknown`; no automatic tunnel start/restart/stop; the session lock never taken by a probe; consecutive infrastructure failures triggering a safe pause; redaction; unparseable CLI output; coalesced concurrent requests; and rejection of host/port/command input from the browser. Because the check is read-only and zero-cost, a real check against a tunnel the user has already started is permitted; report real and fixture results separately, and do not start the tunnel yourself to make one possible.

## 3. Three Unified Configuration Editors

Manual forms, agent outputs, JSON import/export, and backend execution must share one versioned schema and undergo semantic validation.

### Optimization parameter fields

Variable ID/name; target design variable or instance path; parameter name; current/initial value; unit; whether it is optimized; continuous/integer/discrete type; lower and upper bounds; quantization step/candidate values; linear/logarithmic scale; binding group; and ratio/expression relationships.

Show the number of independent action variables. Equal initial values do not imply permanent binding. Validate ranges, units, integer constraints, dependency cycles, and conflicts. Record both the action proposed by the policy and the actual parameters executed after legalization/quantization.

### Performance target fields

Metric ID; `measurement_id`; unit; `>=`/`<=`/interval/target-with-tolerance; thresholds; hard-constraint status; minimization/maximization direction after feasibility; soft-objective weight; normalization scale; and tolerance.

Support extensible metrics such as frequency, power, gain, phase margin, and noise. Agent suggestions must identify their basis and unresolved items. Do not infer the user's requirements solely from the circuit. Determine hard-constraint satisfaction independently of the reward.

### Measurement definition fields

`measurement_id`; analysis type; result source; node/branch/signal; extraction function or restricted expression; time/frequency window; unit; validity conditions; failure handling; corner/test conditions; and aggregation across conditions.

Prefer existing ADE/Maestro measurements and explicitly reject unsupported expressions. Frequency requires a defined steady-state window; power requires a branch-direction convention; phase margin requires a loop-gain/crossover definition; noise requires a frequency point or integration range. Do not directly `eval` arbitrary code. NaN, missing measurements, failure to oscillate, and simulation failures must never be treated as feasible results.

All three editors must support adding, deleting, editing, field-level guidance, undo, saving, natural-language modification, JSON import/export, and diff confirmation.

## 4. Agent Assistance

Implement interchangeable `CodexProvider`, `ClaudeCodeProvider`, and `DisabledProvider` adapters that invoke CLIs installed on the backend host. First check versions, authentication, working directories, and bridge-skill visibility. Use the local `--help` output and actual documentation as the basis for integration.

Use locally supported non-interactive/structured-output capabilities where available. Distinguish intermediate logs from the final configuration. Agent inputs consist of an authorized circuit summary, the current configuration, the user's prompt, and a JSON Schema. Return a configuration proposal/patch, reasoning, warnings, and unresolved items.

Support generating a complete draft, parameters only, targets only, measurements only, and modifications to selected fields. Default to proposals only. Applying configurations, writing circuits, and running real simulations must each respect the relevant user authorization.

Agents assist with configuration preparation and diagnostics; they do not replace every SAC step. The browser must not execute arbitrary shell commands, and prompts must not be interpolated into shell commands. Do not send credentials, license contents, or complete PDK models to an agent.

All manual workflows must remain available without an agent. Provide task-description export and structured-result import. Never present mock responses as genuine agent outputs.

### 4.1 Specific Requirements for `ClaudeCodeProvider`

Prioritize implementing and accepting `ClaudeCodeProvider` in this version, while preserving equivalent interfaces for all three providers. Honor any existing user selection. If there is no previous selection and the Claude CLI is available, default to Claude Code on first use; otherwise clearly show the available providers or Disabled mode. Agent model, effort, timeout, and permitted tools are independent settings. Do not conflate them with RL checkpoints, Spectre concurrency, or circuit-evaluation budgets.

First inspect `claude --version`, authentication status, and locally available guidance, and verify capabilities against official documentation applicable to that version. `--help` may not list every option. Do not conclude that a flag is unsupported solely because it is absent from `--help`, and do not assume every option in the latest documentation exists locally. [C4]

Use `claude -p`, `--output-format json`, and `--json-schema` for non-interactive proposals when supported locally. When streaming is supported, process `stream-json` events separately. Read structured output from the actual result payload, such as the `structured_output` field in supported versions. Do not treat stderr, progress text, or a Markdown passage as configuration JSON. Handle exit codes, error results, permission denials, cancellation, timeouts, schema failures, and incomplete output separately. Do not overwrite the user's existing configuration on failure. [C5]

Launch subprocesses with a controlled working directory and safe argument arrays/standard input. Do not interpolate prompts using `shell=True`. When the bridge skill is required, do not default to `--bare`, which may bypass skill discovery, and do not use `--disable-slash-commands`. Even if the skill file exists, verify that the actual execution environment can load it. Do not use `--dangerously-skip-permissions` to eliminate permission errors. Never read, display, or return authentication tokens. Reuse an authorized, supported authentication method. [C2][C4][C5]

Separate proposal generation from approved execution. Requests that only draft parameters/specifications/measurements must use restricted tools and must not also write schematics or launch real simulations. Passing schema validation does not authorize an action. The backend must still validate references, units, action scope, and user approval. Bind approval to the proposal's version/hash. If the circuit or configuration has changed, invalidate the old approval and revalidate the diff.

Agent inputs must contain only necessary, permitted engineering summaries. Treat netlist comments, imported files, and tool logs as data, not as new system instructions. No proposal may disable backend validation, expand directory permissions, or bypass approval. When the user cancels a request, clean up only that request's subprocess resources; do not kill Virtuoso, training workers, or unrelated Claude sessions.

Use fake CLI fixtures and fixed result events for provider testing by default. Do not automatically launch nested real Claude Code sessions during unit tests, builds, or frontend startup. A working development session does not prove that a background web process has the same HOME, PATH, authentication context, or skills. Real integration diagnostics must expose these differences. If nested sessions are restricted, record the limitation and provide steps for the user to start the backend in a separate supported terminal. Do not bypass safeguards by deleting protective environment variables or applying unknown flags.

Do not store Claude CLI session IDs, conversation-resume state, or token counts as RL run IDs, checkpoints, or Spectre budgets. They may be saved as separate agent-request audit metadata, but they must not substitute for training state.

## 5. Run Configuration and Modes

Provide controls for concurrent Spectre jobs, threads per job, RL network architecture, existing model, checkpoint, run mode, evaluation budget, optional Spectre-launch/time limits, random seed, and whether to stop at the first feasible design.

Concurrency means the number of independent simulation jobs, not the thread count of one simulation. Restore the previous setting; default to 1 if none exists.

Default the RL model to the last compatible model used by the current project. Default the checkpoint to that run's most recently safely saved `latest`, not automatically to `best`. Display its source task, save time, schema, training counters, actual file path, restorable components, and compatibility.

"Do not load weights" means `scratch`, but a network architecture must still be specified. "Which language model the agent uses" and "Which model the RL system loads" are independent settings.

Four modes:
- `scratch`: randomly initialize and create a new run.
- `resume`: restore training state for the same task and continue the same run.
- `fine_tune`: load compatible previous weights, learn on a new task, create a new run, and record its parent.
- `frozen`: load the previous policy without updating weights, the entropy coefficient, or normalization statistics. Record whether actions are deterministic or sampled.

Default to `resume` when full state exists for the same task. Suggest `fine_tune` and require confirmation when loading an old model for a new task. Use `scratch` when no previous weights are loaded. Compatibility failures must be visible; never silently fall back to `scratch`.

Keep learning rate, batch size, warm-up, update frequency, update-to-data ratio (UTD), encoder freezing, encoder-only transfer, critic reset, and similar controls in advanced settings. Preserve the existing implementation by default; do not arbitrarily change the algorithm.

By default, `fine_tune` creates a new target-task replay buffer, optimizers, and task counters while retaining compatible preprocessing definitions. Explicitly record the loading/reset policy for actor, critic, target networks, and temperature parameters. Do not mix in source replay data or source-task optimal dimensions by default.

For `resume`, validate circuit/PDK, test conditions, specifications, action semantics, reward, features, and network versions. A changed task must not be presented as a full continuation of the same training run. A change in graph node count does not necessarily imply incompatibility; equal parameter dimensions do not necessarily imply compatibility.

## 6. Output Settings: Visible, Selectable, and Verifiable in the Frontend

Default the output root to `<repo_root>/outputs`, and remember the user's previous choice. Before a run starts, allow another authorized backend directory to be selected.

Display:
- Output root, experiment name, and experiment ID.
- The complete actual save path for the current run.
- Subpaths for raw data, checkpoints, replay data, best designs, and CSV exports.
- Backend host/environment name, writability, available space, bytes written, and the most recent successful save time.
- A Windows-accessible path only when the mapping has been verified; do not infer a mapping by string manipulation alone.
- Remote Spectre temporary working directories and final-file synchronization status.

For example, if the actual repository is `/mnt/d/gator`, display `/mnt/d/gator/outputs` and, once verified, `D:\gator\outputs`. Do not confuse a folder selected for browser upload with a writable backend output directory.

Implement directory selection using restricted backend file browsing/path entry and a writability test. Lock the run directory after the run starts. Directory migration must be explicit and must not split output between two locations. Give new run directories unique IDs and never overwrite previous experiments with the same name. A resumed run writes back to its original directory.

Provide path copying, file-list refresh, file sizes/summaries, a preview of a few rows, individual-file downloads, and packaged data-only exports. Enable "Open Local Folder" only when genuine desktop integration is available; otherwise provide path copying.

Output options:
- Required: configuration/provenance snapshots, per-evaluation records, actual parameters, individual metrics, simulation-job accounting, run summaries, and event/error logs.
- Enabled by default: learner-update logs, model checkpoints, replay snapshots for resuming training, complete transition archives, and experiment-summary CSV files.
- Detailed CSV copies are exported on demand; use Parquet datasets consistently for the raw tables.
- Configure automatic checkpoint intervals by completed evaluations or elapsed time. Pausing, stopping, and normal completion must save safely.
- Raw-waveform retention: `none` / `best_and_failures` / `all`, defaulting to `best_and_failures`. Support a storage limit and explain the cleanup policy.
- Clearly warn that disabling complete replay saving removes the ability to perform a full training-state resume. Do not generate fictitious optimizer updates in `frozen` mode.

Do not generate images, charts, or reports. Save waveforms only as raw PSF or a numerical format supported by the implementation; do not render them. Retention of best/failed results applies to raw outputs that actually exist. Rerunning a simulation to recover a deleted waveform requires authorization and must be counted.

## 7. Output Directory Layout and File Responsibilities

An existing layout may be retained, but provide a clear mapping and equivalent data. Recommended layout:

```text
<output_root>/<experiment_name>__<experiment_id>/
  experiment.json
  split_manifest.json
  data_dictionary.json
  runs/<task_name>/<mode>__seed<seed>__<run_id>/
    run_manifest.json
    effective_config.json
    input_snapshot/
      circuit.json
      dut.scs
      testbench.scs
      parameter_mapping.json
      pdk_reference.json
    data/
      evaluations/part-*.parquet
      parameters/part-*.parquet
      metrics/part-*.parquet
      simulator_jobs/part-*.parquet
      learner_updates/part-*.parquet
      transitions/part-*.parquet
      states/...
    run_summary.json
    best_design/
      best_feasible.json
      parameters.csv
      optimized_dut.scs
      best_infeasible.json
    checkpoints/
      <checkpoint_id>/
        training_state.pt
        metadata.json
        replay_buffer/...
      latest.json
      best_policy.json
    waveforms/...
    logs/events.jsonl
    logs/errors.jsonl
    exports/...
    artifact_manifest.json
  aggregates/
    run_summary.csv
    budget_success.csv
    paired_runs.csv
    transfer_summary.csv
    cumulative_cost.csv
```

Do not create empty placeholder DUT/testbench files when separate files do not actually exist. Save an exportable combined netlist and hierarchy references instead, and document this in the manifest. When no feasible solution exists, do not create a fictitious `best_feasible` result; represent the absence with an explicit `null`/status. Do not invent a `best_policy` when no validation-set policy evaluation has occurred.

Configuration JSON must be machine-readable. Document data types, units, enumerations, and the meaning of `null` in `data_dictionary.json`. Do not substitute Python `repr`, arbitrary-object pickle serialization, or stringified lists for formal data schemas. Represent non-finite JSON numbers as `null` with a reason.

Manifests must list schema versions, relative paths, purposes, formats, row counts/sizes, checksums, and write status. `pending` is allowed during a run; finalize entries after files are closed. Preserve portable relative paths and information about the original environment.

Do not copy commercial PDK libraries, keys, or licenses. Save PDK versions/identifiers and references. Save required project-owned netlists only as permitted.

## 8. Required Saved Data Fields

### A. `run_manifest.json` / `effective_config.json`

Include at least:

`experiment_id`, `run_id`, `task_id`, `comparison_pair_id`, `task_order`, `run_kind`, `mode`, and a real/mock flag; circuit class, topology/netlist identifiers and hashes, DUT hierarchy, PDK, and test conditions; complete specifications, measurement/parameter/binding/reward definitions; encoder/RL architectures and hyperparameters, source model/checkpoint/hash, and modules actually loaded/reset; train/validation/test assignment and generalization level; `pretrain_seed`, `target_seed`, initial dimensions and their hash; budgets, concurrency/threads, and cache policy; code commit/dirty status and necessary environment versions; UTC timestamps, parent relationships, and output paths.

Save source pretraining costs and references to the source runs. When an external model's source cost is unknown, record `unknown`, not 0. Keep seeds, training sources, and test tasks in distinct fields; do not combine them into one ambiguous seed field.

Record the connection-gate result that admitted the run (Section 2.1): bridge version, profile identifier, per-layer states, and timestamp. For mock runs record `not_applicable`.

### B. `evaluations`: One Row per Candidate Evaluation, Including Successes and Failures

`run_id`, `evaluation_id`, `proposal_id`, `worker_id`, `episode_id`, `episode_step`, `global_env_step`; `dispatch_index`, `completion_index`, and a unified commit/event sequence number; phase (`baseline`/`warmup`/`adapt`/`search`/`validation`, etc.); `policy_version`; proposal/start/completion/commit timestamps and durations; real/cache/retry provenance; parameter and metric references; reward and reward components; validity; whether all hard constraints are satisfied; normalized constraint violation; best-so-far metrics; cumulative budget consumption; cumulative simulation launches; failure type; and concise diagnostics.

Metric-derived rewards are not a substitute for raw physical values. Record every result that actually returns, not only the best step or successful episodes.

### C. `parameters`: A Long-Format Table to Accommodate Different Circuit Action Dimensions

`run_id`, `evaluation_id`, independent variable ID, target instance/parameter, unit, value before the update, raw policy action, decoded value, actual value after projection/quantization, expanded binding results, and references to bounds/step sizes.

### D. `metrics`: A Long-Format Table with One Row per Evaluation/Test Condition/Metric

`run_id`, `evaluation_id`, `measurement_id`, `metric_name`, analysis, corner/condition, raw value, canonical unit, validity/failure reason, threshold reference, constraint satisfaction, violation magnitude, and aggregation level.

Save both the raw metrics for each corner and the aggregated values used for rewards/feasibility. Do not preserve only a worst-case number while discarding its provenance.

### E. `simulator_jobs`: One Row per Actual Simulation Launch Attempt

`job_id`, `evaluation_id`, worker/host, analysis/corner, attempt number, dispatch/start/end timestamps, exit status, timeout status, retry reason, runtime, relative output paths, and retention/synchronization status. Count every actual Spectre launch, including failures and retries.

### F. `learner_updates`: Only Training Updates That Actually Occur

`update_id`, update timestamp, the number of evaluations collected by that point, actor/critic loss, alpha/entropy, learning rate, replay size, batch size, cumulative update count, and `policy_version`.

Populate fields according to the actual implementation. Do not fabricate unavailable values. The logging frequency may be configurable, but cumulative update counts must remain accurate.

### G. `transitions` + `states`: A Complete Experience Archive, Separate from Finite-Capacity Replay Snapshots

`transition_id`, run/task/episode/worker identifiers, `state_ref`, action, reward, `next_state_ref`, `terminated`, `truncated`, `evaluation_id`, `policy_version`, step, and timestamp.

States must contain the graph features, specifications, masks, parameter mappings, and context needed to reconstruct training inputs. Static graphs may be deduplicated and referenced alongside dynamic numerical arrays. Provide a loader and schema; restoration must not depend on access to raw waveforms.

Saving only metric CSV files does not preserve trajectories. Once a circular replay buffer evicts older samples, do not claim it still contains the complete history. Allow complete transition archiving to be disabled, but keep that control separate from the option to disable replay snapshots.

### H. `run_summary.json`: One Summary per Run for Research Statistics

Status/stop reason; feasibility; the evaluation, budget, and time associated with first feasibility; total environment steps; total candidate evaluations; actual Spectre launches; failure/cache/retry counts; gradient-update count; final best design/metrics; target-task costs; references to source-model costs; paused/active durations; output completeness/resumability level; and termination/censoring details.

Keep the cost to first feasibility separate from the final cost of the run. Do not merge them when execution continues after feasibility or when jobs remain in flight.

## 9. Strict Definitions of Budget and First Feasibility

The primary budget, `max_evaluations`, is the number of new, real candidate-circuit evaluations that may be started across the entire run. All workers share it. Reserve budget before dispatch and charge it when execution actually begins. Reservations for canceled tasks that never start may be released; failures that have already started are not refunded.

One set of dimensions evaluated against the specified test suite counts as one candidate evaluation. It may launch multiple Spectre jobs, which must be counted separately. Retries retain the same `evaluation_id` and create a new job attempt; do not misrepresent them as new candidates. Enforce `max_retries`, display the additional launch cost, and optionally provide a hard `max_spectre_launches` limit.

Baseline evaluations, random exploration, fine-tuning samples, and failed evaluations all count toward the corresponding run's cost. Episode resets do not reset the budget. `resume` retains existing counters; `fine_tune` starts new target-task counters.

Clicking "Baseline Simulation" separately in the frontend creates a validation/preflight record and incurs a cost; it is not free. In formal comparisons, reevaluate the same initial dimensions within each run by default. Reusing a previous baseline requires explicit provenance and cost attribution. Do not silently give the transfer group additional data.

The connection check in Section 2.1 is the only zero-cost preflight. It launches no simulation, so it charges no evaluation budget and adds no Spectre launch. It must never be used to obtain circuit metrics.

Under parallel execution, record submission, start, completion, and learner receipt order. First feasibility is the event at which the scheduler actually receives a result and confirms that all hard constraints are satisfied. Do not infer it from the magnitude of `evaluation_id`.

The default primary field, `first_feasible_eval_count`, is the total number of candidate evaluations charged to the budget at that event, including evaluations already started and still in flight. Also save the successful candidate's `dispatch_index`, the completed count, in-flight count, Spectre-launch count, and elapsed time at that moment so alternative accounting conventions can be analyzed.

Save results and costs from jobs that remain in flight after first feasibility, and mark them separately. Do not retroactively treat them as results known earlier. Pausing/stopping should stop new dispatches first and then handle in-flight jobs.

If no feasible design is found, set `first_feasible_eval_count=null` and record `observation_limit`, censoring status, status, and reason. Do not fill in budget B as though success occurred at step B. Cache hits must not be counted as new simulations. For strict research comparisons, disable cross-run caching and test-task data reuse by default.

Record active wall-clock time, paused duration, and the sum of job runtimes separately. Summed parallel-job runtime is not actual elapsed time. Record agent token usage separately when available; never combine it with the simulation budget.

## 10. Checkpoints, Full Training-State Resume, and Best Designs

Save the components supported by the existing implementation: graph/spec encoders, actor, twin critics, target networks, optimizers, temperature and its optimizer, preprocessing/normalization, random states, counters, schema/action semantics, environment/worker states, and references to matching replay snapshots.

Save model state, replay state, log cursors, and the budget ledger at the same consistency boundary. Complete the files before atomically updating the `latest` pointer. Do not combine new weights with stale replay data/counters and call it a full restoration.

Metadata must declare restoration capability such as `full_state`, `weights_only`, or `partial`, along with missing components. Saving training state does not guarantee bit-for-bit reproduction of asynchronous simulations. Explicitly record recoverable boundaries, and never claim to restore the internal state of a running Spectre process.

A frozen inference model may be exported separately with encoder + actor and the required preprocessing. Do not default to unsafe arbitrary-object deserialization from untrusted sources.

`latest` is the most recently safely saved state. Select `best_policy` only under an explicit validation-set rule and record its selection cost. `best_design` is the discovered circuit parameter set and measurement results. Keep these three concepts strictly separate.

A best-design record must include all independent variables and expanded bindings, task/specification, metrics, `evaluation_id`, test conditions, and validation status. Save an optimized project netlist when export is supported. Writing back to a native schematic requires user confirmation and should use a new cellview by default.

Fine-tuning must not overwrite the source checkpoint. By default, start each test task from a fixed source checkpoint rather than inheriting weights fine-tuned on the preceding test task. Expose continual learning as a separate, explicitly labeled option when required.

## 11. Experimental Splits and Data-Only Aggregate Exports

Add a collapsible "Research Experiments" panel for experiment/group, train/validation/test, unseen-spec/unseen-topology/unseen-circuit-class, training sources, test-task lists, seeds, comparison-pair IDs, fixed evaluation-budget checkpoints, and ablation labels.

Research labels are optional for an ordinary single run. Mark absent labels as `unspecified` rather than blocking normal optimization. When generating generalization statistics, report missing labels as errors/warnings; do not infer them automatically.

The `split_manifest` records specific circuits/topologies/specifications, ranges, initial values, counts, and roles. Check for identity/topology overlap and issue warnings. Do not claim that a simple hash proves the absence of data leakage. Tests of an unseen circuit class must exclude that class from source training.

Preserve labels for Scratch, Pretrained-Frozen, Pretrained-Fine-tuned, encoder-only transfer, removal of port information, alternative encoders, and similar experiments. Expose only combinations genuinely supported by the backend; do not invent algorithms to populate the interface.

Use `comparison_pair_id` to associate comparison runs with the same target, initial dimensions, budget, test setup, and target seed. Record the source pretraining seed separately. Runs with different networks/rewards/concurrency settings must not silently be presented as completely controlled pairs.

Implement aggregate exporters that reconstruct results from saved data, without plotting or launching new simulations:

### `run_summary.csv`

One row per run, including task/model/mode/seeds, success status, first feasibility, total costs, best physical metrics, and completeness.

### `budget_success.csv`

One row per run per evaluation-budget checkpoint. Record whether success within the budget is known, the cost under the chosen convention, and `observed`/`unknown`/`censored` status. Optionally export grouped success/total/unknown counts. Runs interrupted early or observed over an insufficient budget must not automatically be marked as failures or discarded.

### `paired_runs.csv`

Comparison run IDs, pairing criteria, success status on both sides, and first-feasibility costs. Compute step-count ratios/reduction fractions only when both sides have valid successes and the denominator is nonzero. Otherwise use `null` and preserve the failure category.

### `transfer_summary.csv`

Group by source training set → target class/topology, mode, encoder, ablation labels, and budget. Retain sample counts, success counts, unknown counts, and links to the original runs. Do not export only means while discarding per-run data.

### `cumulative_cost.csv`

Save fixed task order K, source checkpoint, source pretraining cost, actual target-task cost, and cumulative success count. Count shared source pretraining only once and deduplicate the provenance chain. Unknown source costs make the affected total non-computable; do not substitute 0. Calculate costs separately for different pretraining seeds/models rather than combining them into one supposedly free model.

For every derived table, record the schema, exporter version, input run set, and cutoff sequence number. Make it possible to regenerate the table from raw data at any time. With no data, export a schema-defined empty table and explanation, not demonstration results.

## 12. Reliable Writes, Storage, and Run Control

Write Parquet in batches/partitions. Finish and close each temporary part file before publishing it; do not rewrite an entire table at every step. Use one writer or safely isolated writers for aggregation. Multiple workers must not compete to write the same file. Use JSONL for event logs and define recoverable boundaries clearly.

Implement unique primary keys, idempotent commits, sequences/cursors, and isolation of unfinished partitions. Crash recovery must not double-count historical evaluations or lose acknowledged results. CSV is an export derived from a fixed data snapshot, not a second source of truth edited independently from Parquet.

Pause sequence: stop dispatch → handle/record in-flight jobs → flush → consistent checkpoint → update status. Distinguish forced cancellation from normal completion. Reconnecting after a disconnect must not start duplicate training runs.

Clearly display errors and persistence status for insufficient storage, write failures, or remote synchronization failures. Failure of core persistence must trigger a safe pause; do not continue large amounts of simulation while silently losing data. Automatically clean up only registered temporary files. Do not automatically delete models or primary research data.

Support saving configuration, static validation, a single baseline simulation, start, pause-and-save, continue, stop-and-save, and data export. Show current mode, model/checkpoint, budget use, active workers, actual metrics, first feasibility, best design, actual file paths, and write progress. Do not plot.

Run control includes the zero-cost connection check and pre-dispatch gate of Section 2.1. Show the current connection state and its age beside the run status. A pause caused by repeated infrastructure failures uses the same pause sequence, with a distinct stop reason.

Default to local-only listening, directory allowlists, and credential redaction. Do not launch large real simulations without a user action or automatically modify original schematics. Provide a clearly isolated mock-data root, and exclude mock data from real-experiment aggregates by default.

## 13. Tests, Delivery, and Acceptance

Implement and verify in stages:
1. Inspect the repository; unify schemas, manual editing, and output-directory settings.
2. Integrate the connection check (Section 2.1), real circuit reading, static validation, and one baseline simulation.
3. Integrate the existing optimization backend, budgets, all four run modes, and checkpoints.
4. Complete raw-data persistence, full experience archives, best designs, and aggregate CSV exports.
5. Integrate agent proposals/modifications and frontend operations.

If a core backend is not implemented, display the specific blocker and provide the actual interface contract. Do not substitute a fake trainer or random metrics and claim integration is complete.

Tests must cover at least: units/bindings/measurements; agent schemas and approvals; directory permissions and Windows/WSL/remote paths; shared candidate budgets under multiple workers and retry accounting; asynchronous first feasibility/failure/`null`; `scratch`/`resume`/`fine_tune`/`frozen`; complete replay/checkpoint consistency; interruption recovery and idempotent writes; configuration and trajectory reload; different topology/action dimensions; table exports and data dictionaries; infeasibility/early cancellation; source-cost deduplication; and mock-data isolation. Also cover the connection-check cases listed in Section 2.1.

Validate the full workflow with two small mock tasks, multiple seeds, and supported modes. Do not claim these tests establish algorithmic generalization. When a real backend is accessible, perform a real smoke test only within an authorized budget.

At delivery, report changed files, startup commands, test results, the boundaries of real versus simulated verification, and incomplete items. Show an actual example run's output directory and the files genuinely generated. Confirm that no images or chart reports were generated.

## 14. Additional Claude Code Delivery Checks

After completing all stages in Section 13, verify each of the following:
- Circuit reading/creation/modification, all three configuration editors, the manual workflow, and all three agent providers exist and share the same schema.
- All four RL modes, the default last compatible model/`latest` checkpoint, shared simulation budgets, isolated concurrent jobs, and pause/resume preserve their original semantics.
- None of the file responsibilities, fields, first-feasibility definitions, raw trajectory/replay distinctions, research CSV exports, or source-pretraining cost calculations in Sections 7–11 has been removed.
- The actual output root and final run directory are visible, writability can be checked, and remote temporary directories are not confused with final storage/synchronization status.
- The connection check of Section 2.1 reports each layer separately, costs no evaluation budget, never starts or restarts the tunnel or daemon, gates real dispatch, and leaves offline workflows usable while the bridge is down.
- No charts, training curves, image exports, or research analysis reports have been added. Incomplete, failed, or unauthorized tests are not reported as passed.

Additional Claude integration tests must cover: missing CLI, unauthenticated state, unavailable model, invisible skill, missing structured output, nonzero exit, timeout/cancellation, permission denial, invalidated approval of an old proposal, switching among available providers, cwd/PATH differences, prompts containing special characters, and prevention of user input expanding write permissions. Use fixtures for these tests; real calls are allowed only within the authorized scope.

At delivery, provide actual changed files, startup instructions, accurate test results, the boundaries of real versus simulated verification, one data-output directory that was genuinely generated, and specific incomplete items. Preserve existing code changes. Do not independently commit, push, reset the repository, or launch formal research experiments.

This specification can be implemented using local CLI interfaces. Do not require a new cloud agent SDK, separate model service, or second authentication system. If the repository already uses a supported SDK, its adapter may be retained, but product features, permissions, and data contracts must remain equivalent.

## Appendix A. User Launch Prompt for Claude Code

Place this file in the project root. For example, with the WSL path `/mnt/d/gator` (use the actual path):

```bash
cd /mnt/d/gator
claude --model claude-fable-5-1
```

Use this model argument only when the identifier is available in the current account/deployment. If the intended Fable 5.1 session is already open, do not launch another session. [C3][C4]

Then enter:

```text
Read gator_claude_code_fable51_frontend_data_outputs_en.md in the current repository in full, and incrementally implement the GATOR frontend, run control, and data-only outputs according to every requirement in that file.

First read CLAUDE.md, AGENTS.md, the existing bridge skill, configuration schemas, and actual backend code. Preserve existing implementations and user changes. Do not replace the optimization algorithm or remove any original features. Implement, test, and fix the system in stages rather than stopping after an implementation plan.

Prioritize ClaudeCodeProvider while retaining CodexProvider and fully manual operation. Implement model-state persistence, trajectories/replay, per-evaluation simulation data, visible output paths, and all five research CSV exports.

Do not generate plots, present mock data as real results, or launch unauthorized large simulation workloads. When a real backend is blocked, complete the independent work and clearly document the limitation.

Finally, report actual changes, startup commands, test results, and the locations of files genuinely generated.
```

## Appendix B. References for Claude Execution Integration

The references below are retained from the supplied specification for checking Claude Code behavior and model selection. Actual installed-version and account capabilities still require runtime confirmation. The product design, budget definitions, and output contracts in this document are project requirements, not capabilities automatically promised by these references. The source document records a verification date of 2026-09-19; this translation does not constitute a fresh verification of the URLs or model availability.

- [C1] Project instructions, CLAUDE.md, and AGENTS.md: https://code.claude.com/docs/en/memory
- [C2] Skills and discovery locations: https://code.claude.com/docs/en/skills
- [C3] Model reference retained from the source specification (Fable 5.1): https://platform.claude.com/docs/en/models/fable-5-1/overview
- [C4] Claude Code CLI arguments and session control: https://code.claude.com/docs/en/cli-reference
- [C5] Non-interactive invocation and structured results: https://code.claude.com/docs/en/headless
- [C6] Claude Code workflow practices: https://code.claude.com/docs/en/best-practices
