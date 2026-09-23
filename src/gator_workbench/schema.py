"""The one versioned configuration schema shared by manual forms, agent output,
JSON import/export and backend execution.

Field descriptions double as field-level guidance in the editors and as the JSON
Schema handed to an agent CLI, so there is exactly one definition of every field.
Structural validity lives here; cross-field and circuit-aware checks live in
``validation.py``; translation to optimizer objects lives in ``compile.py``.
Passing this schema never authorizes an action.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import CONFIG_SCHEMA_VERSION

ENCODER_TYPES = ('graph_transformer', 'mlp', 'rgcn', 'gat', 'port_gnn', 'gcn')
RUN_MODES = ('scratch', 'resume', 'fine_tune', 'frozen')
UNSPECIFIED = 'unspecified'


class _Model(BaseModel):
    # forbid: an agent (or an imported file) cannot add keys such as "skip_validation".
    # allow_inf_nan=False: NaN/inf never enter a configuration as if they were numbers.
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_assignment=True)


# --------------------------------------------------------------------------- parameters
class OptimizationParameter(_Model):
    variable_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]*$',
        description='Stable ID of this variable. Used in data tables; it is an identifier, never a learned feature.')
    name: str = Field('', max_length=200, description='Optional display name.')
    target_kind: Literal['instance_parameter', 'design_variable'] = Field('instance_parameter',
        description='instance_parameter: a parameter of one circuit instance. design_variable: a global/ADE design '
                    'variable. Current optimizer adapters can only write instance parameters; design variables are '
                    'kept in the configuration but block a run until an adapter supports them.')
    instance_path: Optional[str] = Field(None, max_length=400,
        description='Full hierarchical instance path exactly as read from the circuit (e.g. XU1/M1). Required for '
                    'instance_parameter. Never inferred from a name prefix.')
    parameter_name: str = Field(min_length=1, max_length=120,
        description='Canonical parameter name as reported by the circuit reader (e.g. w, l, c, r) or the design '
                    'variable name.')
    initial_value: Optional[float] = Field(None,
        description='Current/initial value in `unit`. Leave empty to take the value read from the circuit. It is '
                    'checked against the circuit at validation; a mismatch is an error, not silently overwritten.')
    unit: str = Field(min_length=0, max_length=32,
        description='Unit of initial value, bounds, step and candidates (e.g. um, nm, pF, kohm, count).')
    optimized: bool = Field(True, description='Whether the optimizer may change this variable.')
    value_type: Literal['continuous', 'integer', 'discrete'] = Field('continuous',
        description='continuous; integer (multiplicity, fingers); discrete (explicit candidate list). The policy '
                    'always proposes a continuous action that is projected; this is not a discrete-action SAC.')
    lower: Optional[float] = Field(None, description='Lower bound in `unit`. Required for optimized leaders.')
    upper: Optional[float] = Field(None, description='Upper bound in `unit`. Required for optimized leaders.')
    step: Optional[float] = Field(None, gt=0,
        description='Quantization step in `unit` (manufacturing grid). Values are projected to lower + k*step.')
    candidates: Optional[list[float]] = Field(None, max_length=4096,
        description='Candidate values for value_type=discrete. Supported for execution only when they form a '
                    'uniform grid (then equivalent to lower/upper/step); otherwise reported as unsupported.')
    scale: Literal['linear', 'log'] = Field('linear',
        description='How the normalized action maps to the physical range. log requires lower > 0.')
    binding_group: Optional[str] = Field(None, max_length=120,
        description='variable_id of the leader this variable is tied to. Empty = independent action variable. '
                    'Equal initial values never imply a binding; bindings must be declared here.')
    relation: Literal['ratio', 'expression'] = Field('ratio',
        description='How a bound variable follows its leader.')
    ratio: float = Field(1.0, gt=0, description='follower = ratio * leader (relation=ratio). Must be positive.')
    expression: Optional[str] = Field(None, max_length=512,
        description='Restricted arithmetic in the symbol `leader` (relation=expression). Evaluated by a whitelist '
                    'AST, never eval(). Only expressions equivalent to a positive constant ratio are executable.')
    notes: str = Field('', max_length=1000, description='Free text; not used by the optimizer.')


# --------------------------------------------------------------------------- targets
class PerformanceTarget(_Model):
    metric_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]*$',
        description='Name of this spec: the value its equation gives is recorded, scored and shown under this name. It '
                    'may be the name of a result the simulation returns only when the equation is exactly the Probe of '
                    'that result. A name the RL specification registry does not know adds an entry to it.')
    equation: str = Field(min_length=1, max_length=512,
        description='What this spec judges, as an equation over Probe IDs (the measurement_id of rows in the Probes tab): '
                    'Probe IDs, numbers, + - * / ** and parentheses, e.g. m_supply_power_w / m_osc_frequency_hz. The '
                    'simplest equation is one Probe ID. Probe values are in canonical units (W, Hz, V...), so W / Hz gives '
                    'J. A missing or invalid probe, or a failed operation such as a division by zero, makes the spec '
                    'invalid - never a number. Evaluated by a whitelist, never eval().')
    unit: str = Field(max_length=32, description='Unit of the thresholds, tolerance and normalization scale.')
    constraint: Literal['>=', '<=', 'interval', 'target'] = Field(
        description='>= lower; <= upper; interval [lower, upper]; target +/- tolerance.')
    lower: Optional[float] = Field(None, description='Lower threshold (>=, interval).')
    upper: Optional[float] = Field(None, description='Upper threshold (<=, interval).')
    target: Optional[float] = Field(None, description='Target value (constraint=target).')
    tolerance: float = Field(0.0, ge=0,
        description='Acceptance tolerance in `unit`. For constraint=target it is the half-width and must be > 0. '
                    'For other constraints it relaxes each threshold by this amount.')
    hard: bool = Field(True,
        description='Hard constraint: must be satisfied for feasibility. Feasibility is decided from raw metric '
                    'values and thresholds, independently of the reward.')
    direction_after_feasible: Literal['none', 'minimize', 'maximize'] = Field('none',
        description='Preference among feasible designs. At most one target may set it; it selects the best design '
                    'and does not change the reward.')
    soft_weight: float = Field(1.0, gt=0, description='Relative weight of this target in the reward.')
    normalization_scale: float = Field(gt=0,
        description='Violation is (threshold distance)/scale, capped at 1. Use a physically meaningful scale.')
    active: bool = Field(True, description='Inactive targets affect neither reward nor feasibility.')
    basis: str = Field('', max_length=1000,
        description='Where this requirement comes from (datasheet, user statement...). Agent suggestions must '
                    'state their basis; requirements are never inferred from the circuit alone.')

    @model_validator(mode='before')
    @classmethod
    def _one_probe_before_equations(cls, data):
        """A configuration written before specs had equations named ONE probe in `measurement_id`: that probe is the
        equation (the simplest one). An `equation` given as well wins."""
        if isinstance(data, dict) and 'measurement_id' in data:
            data = {('equation' if key == 'measurement_id' else key): value for key, value in data.items()
                    if not (key == 'measurement_id' and 'equation' in data)}
        return data


# --------------------------------------------------------------------------- measurements
class MeasurementWindow(_Model):
    start: float
    stop: float
    unit: str = Field(description='s for time windows, Hz for frequency windows.')


class ValidityCondition(_Model):
    kind: Literal['finite', 'min', 'max', 'oscillating', 'settled', 'crossing_exists'] = Field(
        description='A condition that must hold for the measurement to be valid.')
    value: Optional[float] = Field(None, description='Threshold for min/max in the measurement unit.')
    note: str = Field('', max_length=300)


class MeasurementDefinition(_Model):
    measurement_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]*$',
        description='Stable ID. Targets refer to it, and expression measurements may use it as a symbol.')
    analysis: Literal['dc', 'ac', 'tran', 'noise', 'stb', 'pss', 'pnoise', 'other'] = Field(
        description='Analysis that produces the raw data.')
    result_source: Literal['backend_profile', 'ade_output', 'expression'] = Field('backend_profile',
        description='backend_profile: a metric computed by the verified circuit-profile analyzer. ade_output: an '
                    'existing ADE/Maestro output (preferred for native designs; needs the bridge). expression: '
                    'restricted arithmetic over other measurement IDs.')
    source_name: Optional[str] = Field(None, max_length=200,
        description='Metric name in the backend profile, or the ADE output name.')
    signal: Optional[str] = Field(None, max_length=300, description='Node, branch or signal, e.g. VOUT or VDD:p.')
    function: Optional[Literal['value_at', 'average', 'rms', 'peak_to_peak', 'frequency', 'period', 'dc_gain',
                               'gain_at', 'unity_gain_frequency', 'phase_margin', 'gain_margin', 'bandwidth',
                               'slew_rate', 'settling_time', 'average_power', 'spot_noise',
                               'integrated_noise']] = Field(None,
        description='Extraction function from a fixed whitelist. Anything else is rejected, never evaluated.')
    expression: Optional[str] = Field(None, max_length=512,
        description='Restricted arithmetic (+ - * / ** and parentheses) over other measurement IDs. No function '
                    'calls, no attribute access, never eval().')
    window: Optional[MeasurementWindow] = Field(None,
        description='Time/frequency window. A frequency measurement needs a defined steady-state window.')
    at_frequency_hz: Optional[float] = Field(None, gt=0, description='Frequency point for gain_at / spot_noise.')
    integration_band_hz: Optional[tuple[float, float]] = Field(None,
        description='[f_low, f_high] for integrated_noise.')
    branch_direction: Optional[Literal['into_source_positive', 'out_of_source_positive']] = Field(None,
        description='Sign convention for power from a supply branch current. Required for average_power.')
    loop_definition: Optional[str] = Field(None, max_length=300,
        description='How loop gain is obtained for phase/gain margin (stb probe name, or open-loop AC path).')
    crossover: Optional[Literal['first_unity_gain_downward', 'last_unity_gain_downward']] = Field(None,
        description='Which unity-gain crossing defines phase margin.')
    unit: str = Field(max_length=32,
        description='Unit of the measured value. A target using this measurement must have a compatible unit.')
    validity: list[ValidityCondition] = Field(default_factory=lambda: [ValidityCondition(kind='finite')],
        description='Conditions that must ALL hold for the value to count (finite, min/max, oscillating, settled, '
                    'crossing_exists). A measurement failing any of them is invalid and can never be feasible.')
    on_failure: Literal['invalid'] = Field('invalid',
        description='A failed/missing/NaN measurement is always invalid. There is deliberately no option that '
                    'treats a failure as a feasible result.')
    conditions: list[str] = Field(default_factory=lambda: ['nominal'],
        description='Corner/test-condition IDs this measurement is evaluated under.')
    aggregation: Literal['nominal_only', 'worst_case', 'mean', 'min', 'max'] = Field('nominal_only',
        description='How per-condition values combine into the value used for reward/feasibility. Per-condition '
                    'raw values are always stored as well.')
    notes: str = Field('', max_length=1000, description='Free text; not used by the optimizer.')


# --------------------------------------------------------------------------- circuit
class CircuitReference(_Model):
    source: Literal['registered_task', 'netlist', 'virtuoso'] = Field(
        description='registered_task: a task provider known to the backend. virtuoso: a native library/cell/view read '
                    'through the bridge. netlist: the REMOVED Spectre netlist import - still read, so configurations '
                    'and runs saved before stay readable (and keep their hashes), but no circuit is loaded from it.')
    task_id: Optional[str] = Field(None, max_length=200)
    netlist_path: Optional[str] = Field(None, max_length=1000,
        description='Removed netlist source only (kept for configurations saved before). Backend-side path.')
    parser_config_path: Optional[str] = Field(None, max_length=1000,
        description='Removed netlist source only (kept for configurations saved before). Device/port mapping.')
    library: Optional[str] = Field(None, max_length=200)
    cell: Optional[str] = Field(None, max_length=200)
    view: Optional[str] = Field(None, max_length=200)
    testbench_cell: Optional[str] = Field(None, max_length=200,
        description='Existing testbench cell. A DUT may instead be identified inside one testbench.')
    dut_hierarchy: Optional[str] = Field(None, max_length=400,
        description='Instance path or subcircuit name of the DUT inside the testbench/netlist.')
    circuit_class: str = Field(UNSPECIFIED, max_length=120)
    pdk_id: str = Field(UNSPECIFIED, max_length=200,
        description='PDK name/version identifier. PDK files themselves are never copied.')
    content_sha256: Optional[str] = Field(None, pattern=r'^[0-9a-f]{64}$',
        description='Hash of the circuit content the configuration was validated against.')


# --------------------------------------------------------------------------- run
STANDARD_VOCABULARY = 'standard'


class NetworkConfig(_Model):
    encoder_type: Literal['graph_transformer', 'mlp', 'rgcn', 'gat', 'port_gnn', 'gcn'] = 'graph_transformer'
    hidden_dim: int = Field(32, ge=4, le=1024)
    heads: int = Field(4, ge=1, le=32)
    layers: int = Field(2, ge=1, le=16)
    vocabulary: str = Field(STANDARD_VOCABULARY, max_length=80, pattern=r'^(standard|pdk:[A-Za-z_][A-Za-z0-9_.\-]{0,63})$',
        description='Which components the network knows. standard: the 8 generic kinds (MOS, R, C, L, sources) every '
                    'model saved before 2026-09-21 was trained with; other parts are "unknown". pdk:<technology '
                    'library>: every component of that PDK, loaded with "Load PDK..." (gator_workbench.pdk). A model '
                    'trained with one list loads only with the same list.')


class SpecRegistryEntry(_Model):
    metric_id: str
    unit: str = Field(description='Canonical unit of the registered metric.')
    reference: float = Field(gt=0, description='Fixed physical reference used for input normalization.')


class AdvancedRL(_Model):
    """Defaults mirror the existing entry points. Changing them changes the checkpoint contract."""
    learning_rate: float = Field(3e-4, gt=0)
    gamma: float = Field(0.99, ge=0, le=1)
    tau: float = Field(0.005, gt=0, le=1)
    initial_alpha: float = Field(0.2, gt=0)
    target_entropy_per_action: float = Field(1.0, gt=0)
    max_grad_norm: float = Field(10.0, gt=0)
    batch_size: int = Field(8, ge=1, le=4096)
    warmup_transitions: int = Field(8, ge=0, description='Random exploration until this many replay insertions.')
    update_every: int = Field(1, ge=1, description='Run learner updates every N admitted transitions.')
    updates_per_transition: int = Field(1, ge=1, le=64, description='Update-to-data ratio (UTD).')
    replay_capacity: int = Field(10000, ge=1)
    episode_length: int = Field(4, ge=1, le=1000, description='Environment steps per episode (finite horizon).')
    episode_terminates_on_success: bool = Field(False,
        description='MDP-level: end the episode at a feasible design. Distinct from stopping the whole run.')
    freeze_encoder: bool = Field(False, description='fine_tune only: keep loaded encoder weights fixed.')
    encoder_only_transfer: bool = Field(False,
        description='fine_tune only: load encoder weights; actor/critic heads start random.')
    reset_critic: bool = Field(False, description='fine_tune only: load the actor but start critics/targets fresh.')
    reset_temperature: bool = Field(False, description='fine_tune only: start alpha from initial_alpha.')
    spec_registry: Optional[list[SpecRegistryEntry]] = Field(None,
        description='Custom metric registry for the goal encoder. Empty = optimizer default. Changing it changes '
                    'the network input width and therefore checkpoint compatibility.')
    simulation_timeout_seconds: float = Field(120.0, gt=0)


class ModelSource(_Model):
    run_dir: Optional[str] = Field(None, max_length=1000,
        description='Run directory whose checkpoint is loaded (resume / fine_tune / frozen).')
    checkpoint_id: str = Field('latest', max_length=120,
        description='`latest` = most recently safely saved state (default, not automatically `best`), '
                    '`best_policy`, or an explicit checkpoint ID.')
    source_pretraining_cost_evaluations: Optional[int] = Field(None, ge=0,
        description='Only for external models whose cost cannot be read from a source run. Empty = unknown '
                    '(recorded as unknown, never as 0).')


class RunSettings(_Model):
    mode: Literal['scratch', 'resume', 'fine_tune', 'frozen'] = 'scratch'
    concurrency: int = Field(1, ge=1, le=64,
        description='Number of independent simulation jobs running at once. Not the thread count of one job.')
    threads_per_job: int = Field(1, ge=1, le=256, description='Simulator threads inside each job.')
    max_evaluations: int = Field(ge=1,
        description='Primary budget: new real candidate evaluations that may START in the whole run, shared by '
                    'all workers. Baselines, warm-up, failures all count. Episode resets do not reset it.')
    max_spectre_launches: Optional[int] = Field(None, ge=1,
        description='Optional hard cap on actual simulator launches, including retries and failures.')
    max_wall_seconds: Optional[float] = Field(None, gt=0, description='Optional active wall-clock limit.')
    max_retries: int = Field(0, ge=0, le=10,
        description='Retries per evaluation for retryable infrastructure failures. A retry keeps the '
                    'evaluation_id and adds a job attempt; it costs a launch, not a new evaluation.')
    max_consecutive_failures: int = Field(5, ge=1, le=1000,
        description='Safe stop (flush + checkpoint) after this many consecutive failed evaluations, so a dead '
                    'backend cannot consume the budget unattended.')
    max_consecutive_infrastructure_failures: int = Field(3, ge=1, le=1000,
        description='After this many consecutive INFRASTRUCTURE failures (lost bridge, silent daemon, no license), '
                    'counted in completion order across workers: stop dispatching, record a connection check and '
                    'pause safely instead of spending the budget against a dead link. Continuing needs the '
                    'connection gate to pass again.')
    connection_profile_id: Optional[str] = Field(None, max_length=64, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$',
        description='Identifier of a configured bridge connection profile (real tasks only). Only an identifier: '
                    'hosts, ports, paths and commands are never taken from a configuration or a request.')
    seed: int = Field(0, ge=0, lt=2**32, description='Target-task seed (collector, replay sampling, torch).')
    stop_at_first_feasible: bool = Field(False,
        description='Stop dispatching once the scheduler confirms a design meeting all hard constraints.')
    frozen_action: Literal['deterministic', 'sampled'] = Field('deterministic',
        description='frozen mode only: mean action or a sample from the fixed policy.')
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    model_source: ModelSource = Field(default_factory=ModelSource)
    advanced: AdvancedRL = Field(default_factory=AdvancedRL)
    cache_policy: Literal['disabled'] = Field('disabled',
        description='The existing environment has no result cache; duplicates are simulated and counted.')
    continual_learning: bool = Field(False,
        description='Explicit opt-in to inherit weights fine-tuned on a previous test task. Default starts every '
                    'test task from the fixed source checkpoint.')


# --------------------------------------------------------------------------- output
class OutputSettings(_Model):
    output_root: Optional[str] = Field(None, max_length=1000,
        description='Backend directory. Empty = <repo_root>/outputs. Must be inside an allowed root and writable.')
    experiment_name: str = Field('experiment', min_length=1, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]*$')
    experiment_id: Optional[str] = Field(None, max_length=64,
        description='Set to append runs to an existing experiment; empty creates a new unique ID.')
    save_learner_updates: bool = True
    save_checkpoints: bool = True
    save_replay_snapshots: bool = Field(True,
        description='Needed for a full training-state resume. When off, checkpoints are weights_only.')
    save_transition_archive: bool = Field(True,
        description='Complete experience archive (every transition + states). Independent of replay snapshots.')
    export_summary_csv: bool = True
    checkpoint_every_evaluations: Optional[int] = Field(50, ge=1)
    checkpoint_every_seconds: Optional[float] = Field(None, gt=0)
    keep_last_checkpoints: Optional[int] = Field(10, ge=1,
        description='How many PERIODIC save points to keep, the newest ones. A save point holds the replay buffer, so '
                    'it grows with the run: keeping every one of a long run filled the run folder with copies (measured '
                    '2026-09-23: 40 MB of save points against 1.2 MB of data after 250 evaluations). Save now, pause, '
                    'stop and final save points, the latest one and a selected best policy are never removed. '
                    'Empty = keep every one.')
    learner_update_log_every: int = Field(1, ge=1,
        description='Write every Nth learner update. cumulative_updates stays exact regardless.')
    flush_every_evaluations: int = Field(16, ge=1, le=100000,
        description='Parquet part size in evaluations. Acknowledged results are journaled before this.')
    waveform_retention: Literal['none', 'best_and_failures', 'all'] = 'best_and_failures'
    waveform_storage_limit_bytes: Optional[int] = Field(2 * 1024**3, ge=0,
        description='Cap on retained raw simulator output. Oldest retained failures are removed first, then '
                    'nothing else: models and primary data are never deleted automatically.')
    min_free_bytes: int = Field(1 * 1024**3, ge=0,
        description='Dispatch pauses safely when free space on the output filesystem falls below this.')


# --------------------------------------------------------------------------- research
class ResearchLabels(_Model):
    experiment_group: str = UNSPECIFIED
    split: Literal['train', 'validation', 'test', 'unspecified'] = 'unspecified'
    generalization_level: Literal['same_task', 'unseen_spec', 'unseen_topology', 'unseen_circuit_class',
                                  'unspecified'] = 'unspecified'
    training_sources: list[str] = Field(default_factory=list,
        description='Task IDs/classes the source model was trained on.')
    test_tasks: list[str] = Field(default_factory=list)
    comparison_pair_id: str = UNSPECIFIED
    task_order: Optional[int] = Field(None, ge=0, description='Position K in a fixed task order.')
    pretrain_seed: Optional[int] = Field(None, ge=0, description='Seed of the SOURCE pretraining run.')
    budget_checkpoints: list[int] = Field(default_factory=list,
        description='Evaluation budgets at which success is tabulated.')
    ablation_labels: list[str] = Field(default_factory=list)
    method_label: str = Field(UNSPECIFIED,
        description='e.g. Scratch, Pretrained-Frozen, Pretrained-Fine-tuned, encoder-only transfer.')


class ProjectInfo(_Model):
    name: str = Field('gator-project', min_length=1, max_length=120)
    task_name: str = Field('task', min_length=1, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-]*$')
    notes: str = Field('', max_length=2000)


class WorkbenchConfig(_Model):
    schema_version: Literal['gator-workbench-config-v1'] = CONFIG_SCHEMA_VERSION
    project: ProjectInfo = Field(default_factory=ProjectInfo)
    circuit: CircuitReference
    parameters: list[OptimizationParameter] = Field(default_factory=list, max_length=2000)
    targets: list[PerformanceTarget] = Field(default_factory=list, max_length=500)
    measurements: list[MeasurementDefinition] = Field(default_factory=list, max_length=500)
    run: RunSettings
    output: OutputSettings = Field(default_factory=OutputSettings)
    research: ResearchLabels = Field(default_factory=ResearchLabels)


# --------------------------------------------------------------------------- helpers
SECTIONS = {'parameters': OptimizationParameter, 'targets': PerformanceTarget,
            'measurements': MeasurementDefinition}
SECTION_KEYS = {'parameters': 'variable_id', 'targets': 'metric_id', 'measurements': 'measurement_id'}


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


_ONE_PROBE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]*$')


def _hashed(data):
    """What both hashes see. A spec whose equation is one Probe ID is hashed in the form every configuration had before
    specs were equations (`measurement_id`), so a configuration written earlier keeps its hashes: its runs still
    resume, its checkpoints still load, and approvals and proposals made for it still bind. The network's component list
    (`run.network.vocabulary`, added later) is hashed as absent while it is the standard one, for the same reason."""
    run = data.get('run') if isinstance(data, dict) else None
    network = run.get('network') if isinstance(run, dict) else None
    if isinstance(network, dict) and network.get('vocabulary') == STANDARD_VOCABULARY:
        data = dict(data, run=dict(run, network={k: v for k, v in network.items() if k != 'vocabulary'}))
    targets = data.get('targets') if isinstance(data, dict) else None
    if not isinstance(targets, list):
        return data
    return dict(data, targets=[
        {('measurement_id' if key == 'equation' else key): value for key, value in row.items()}
        if isinstance(row, dict) and 'measurement_id' not in row and isinstance(row.get('equation'), str)
        and _ONE_PROBE.match(row['equation']) else row for row in targets])


def config_hash(config: WorkbenchConfig | dict) -> str:
    """Hash used to bind approvals to an exact configuration version."""
    data = config.model_dump(mode='json') if isinstance(config, WorkbenchConfig) else config
    return hashlib.sha256(canonical_json(_hashed(data)).encode('utf8')).hexdigest()


def task_definition_hash(config: WorkbenchConfig) -> str:
    """Identity of the optimization *task* (circuit, variables, targets, measurements).

    Run/output/research settings are deliberately excluded: changing a budget or an
    output directory does not make it a different task; changing a threshold does.
    """
    data = _hashed(config.model_dump(mode='json'))
    return hashlib.sha256(canonical_json({k: data[k] for k in (
        'circuit', 'parameters', 'targets', 'measurements')}).encode('utf8')).hexdigest()


def json_schema(section: str | None = None) -> dict:
    if section is None:
        return WorkbenchConfig.model_json_schema()
    return SECTIONS[section].model_json_schema()


def editor_columns(section: str) -> list[dict]:
    """Column descriptors derived from the schema so the UI has no second field list."""
    model = SECTIONS[section]
    schema = model.model_json_schema()
    required = set(schema.get('required', []))
    columns = []
    for name, info in model.model_fields.items():
        prop = schema['properties'][name]
        options = prop.get('enum')
        kind = prop.get('type')
        for branch in prop.get('anyOf', []):
            options = options or branch.get('enum')
            if branch.get('type') not in (None, 'null'):
                kind = kind or branch['type']
            if '$ref' in branch:
                kind = kind or 'object'
        if '$ref' in prop:
            kind = 'object'
        columns.append(dict(name=name, type=kind or 'string', options=options, required=name in required,
                            nullable=any(b.get('type') == 'null' for b in prop.get('anyOf', [])),
                            guidance=info.description or '', default=prop.get('default')))
    return columns


# --------------------------------------------------------------------------- schema errors in plain words
# The row IDs, and what else names them: an ID that is renamed has to be renamed there too.
ID_FIELDS = {'variable_id': 'rows that follow it (binding_group)', 'metric_id': None,
             'measurement_id': 'Specs equations that use it'}
_NOT_IN_AN_ID = re.compile(r'[^A-Za-z0-9_.\-]')
_BOUNDS = dict(greater_than=('gt', 'greater than'), greater_than_equal=('ge', 'at least'),
               less_than=('lt', 'less than'), less_than_equal=('le', 'at most'))


def describe_errors(exc, limit: int = 50) -> list[dict]:
    """What the schema rejects in a configuration, one entry per field, in plain words (user report 2026-09-21: the page
    showed pydantic's list as JSON, "String should match pattern ..."). `path` is written like the validation report's
    (parameters[1].variable_id), so the page names the row and the editor marks it; `code` is invalid_id for an ID the
    schema cannot take, otherwise schema; `technical` keeps the schema's own words."""
    out = []
    for error in exc.errors()[:limit]:
        code, message = _plain_error(error)
        out.append(dict(path=_error_path(error['loc']), code=code, message=message,
                        technical=f"{error['msg']} [{error['type']}]"))
    return out


def _error_path(loc) -> str:
    path = ''
    for part in loc:
        path += f'[{part}]' if isinstance(part, int) else f'.{part}' if path else str(part)
    return path


def _quoted(value) -> str:
    text = str(value)
    return f'"{text[:60]}..."' if len(text) > 60 else f'"{text}"'


def _number(value) -> str:
    return str(value).lower() if isinstance(value, bool) else format(value, 'g') if isinstance(value, (int, float)) else str(value)


def _given(value) -> str:
    """What the field holds, when that is short enough to say: ' (it is "abc")', ' (it is 1.5)'."""
    if isinstance(value, str):
        return f' (it is {_quoted(value)})' if value else ''
    return f' (it is {_number(value)})' if isinstance(value, (int, float)) else ''


def _plain_error(error) -> tuple[str, str]:
    kind, value, ctx = error['type'], error.get('input'), error.get('ctx') or {}
    names = [part for part in error['loc'] if isinstance(part, str)]
    field = names[-1] if names else 'The configuration'
    given = _given(value)
    if kind == 'string_pattern_mismatch' and field in ID_FIELDS and isinstance(value, str):
        return 'invalid_id', _id_advice(value, ID_FIELDS[field])
    if kind == 'string_pattern_mismatch':
        return 'schema', f'{field} is not written in the form this field takes{given}.'
    if kind == 'missing':
        return 'schema', f'{field} is missing: this field needs a value.'
    if kind == 'string_too_short':
        return 'schema', f'{field} is empty: it needs a value.'
    if kind == 'string_too_long':
        return 'schema', f'{field} is too long: at most {ctx.get("max_length")} characters.'
    if kind == 'too_long':
        return 'schema', f'{field} has too many entries: at most {ctx.get("max_length")}.'
    if kind == 'extra_forbidden':
        return 'schema', f'{field} is not a field of this part of the configuration: remove it.'
    if kind in ('float_parsing', 'float_type'):
        return 'schema', f'{field} needs a number{given}.'
    if kind in ('int_parsing', 'int_type', 'int_from_float'):
        return 'schema', f'{field} needs a whole number{given}.'
    if kind in ('bool_parsing', 'bool_type'):
        return 'schema', f'{field} needs true or false{given}.'
    if kind == 'finite_number':
        return 'schema', f'{field} needs a finite number, not NaN or infinity.'
    if kind == 'literal_error':
        return 'schema', f'{field} must be one of {ctx.get("expected")}{given}.'
    if kind in _BOUNDS and _BOUNDS[kind][0] in ctx:
        key, words = _BOUNDS[kind]
        return 'schema', f'{field} must be {words} {_number(ctx[key])}{given}.'
    if kind == 'value_error':
        return 'schema', str(error['msg']).removeprefix('Value error, ')
    return 'schema', f'{field}: {error["msg"]}.'


def _shown(char: str) -> str:
    return 'a space' if char == ' ' else f'"{char}"'


def _id_advice(value: str, also: str | None) -> str:
    """Why `value` cannot be an ID, and one that can: every character an ID may not hold becomes _ (the swap the task
    starters make, tasks._member_variable_id)."""
    bad = sorted(set(_NOT_IN_AN_ID.findall(value)), key=value.index)
    reasons = ['it contains ' + ', '.join(map(_shown, bad))] if bad else []
    if value[:1] in tuple('0123456789.-'):
        reasons.append(f'it starts with "{value[0]}"')
    suggestion = _NOT_IN_AN_ID.sub('_', value)
    suggestion = suggestion if re.match(r'[A-Za-z_]', suggestion) else f'_{suggestion}'
    return (f'{_quoted(value)} cannot be an ID: {" and ".join(reasons) or "it is not written like one"}. An ID holds only '
            f'letters, digits and _ . - and starts with a letter or _, for example {suggestion}'
            + (f' - {also} need the new ID too.' if also else '.'))
