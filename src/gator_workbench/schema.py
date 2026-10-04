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
import math
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import CONFIG_SCHEMA_VERSION

ENCODER_TYPES = ('graph_transformer', 'rgcn', 'gatv2')
REMOVED_ENCODERS = {'port_gnn': ('2026-09-24', 'bbdfe36'),
                    'mlp': ('2026-09-26', '9bc488f'), 'gcn': ('2026-09-26', '9bc488f')}
RUN_MODES = ('scratch', 'resume', 'fine_tune', 'frozen')
UNSPECIFIED = 'unspecified'


class _Model(BaseModel):
    # forbid: an agent (or an imported file) cannot add keys such as "skip_validation".
    # allow_inf_nan=False: NaN/inf never enter a configuration as if they were numbers.
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_assignment=True)


# --------------------------------------------------------------------------- parameters
# Row fields retired on 2026-09-26 (record 7.92), and the Probes' conditions and aggregation on 2026-09-29 (record
# 7.105), each with the default it had. A row written with them still loads:
# the before-validators below take them out - what they meant is kept in the fields that remain, what never ran is
# dropped, what a run refused is refused there, in plain words. Both hashes still see them at these defaults
# (`_hashed`), so every run, checkpoint, task file and approval made before keeps its identity.
RETIRED_PARAMETER_FIELDS = {'name': '', 'target_kind': 'instance_parameter', 'candidates': None, 'relation': 'ratio',
                            'expression': None}
RETIRED_MEASUREMENT_FIELDS = {'function': None, 'window': None, 'at_frequency_hz': None, 'integration_band_hz': None,
                              'branch_direction': None, 'loop_definition': None, 'crossover': None,
                              'on_failure': 'invalid', 'validity': [{'kind': 'finite', 'value': None, 'note': ''}],
                              'conditions': ['nominal'], 'aggregation': 'nominal_only', 'expression': None}
# The Specs' target and tolerance, retired on 2026-10-03 (review of the editor columns): "target +/- tolerance" was an
# interval, and a tolerance only loosened a limit. Hashed at these defaults like the fields above.
RETIRED_TARGET_FIELDS = {'target': None, 'tolerance': 0.0}


def _without_retired(data, retired):
    """The body of a plain retired-field before-validator (Probes rows, run settings): a dict loses the keys of
    `retired`; anything else - and a dict without them - is passed on as it came."""
    if isinstance(data, dict) and retired.keys() & data.keys():
        data = {key: value for key, value in data.items() if key not in retired}
    return data


def uniform_grid(candidates):
    """Return (lower, upper, step) when sorted unique candidates form a uniform grid, else None."""
    values = sorted(set(candidates))
    if len(values) < 2 or len(values) != len(candidates):
        return None
    step = values[1] - values[0]
    if step <= 0 or any(not math.isclose(b - a, step, rel_tol=1e-9, abs_tol=1e-18)
                        for a, b in zip(values, values[1:])):
        return None
    return values[0], values[-1], step


def linear_ratio(expression):
    """ratio r when `expression` in the symbol `leader` equals r*leader with r > 0, else None.

    Uses the optimizer's whitelist AST evaluator; nothing is ever eval()'d.
    """
    from analog_optimizer.netlist.expressions import evaluate, UnresolvedExpression

    def at(x):
        def lookup(name):
            if name != 'leader':
                raise UnresolvedExpression(f'Unknown symbol {name!r}; only `leader` is allowed')
            return x
        return evaluate(expression, lookup)
    try:
        f0, f1, f2, f3 = at(0.0), at(1.0), at(2.0), at(3.5)
    except (UnresolvedExpression, ZeroDivisionError):
        return None
    if (abs(f0) > 1e-15 or f1 <= 0 or not math.isclose(f2, 2 * f1, rel_tol=1e-9)
            or not math.isclose(f3, 3.5 * f1, rel_tol=1e-9)):
        return None
    return f1


class OptimizationParameter(_Model):
    variable_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]*$',
        description='Stable ID of this variable. Used in data tables; it is an identifier, never a learned feature.')
    instance_path: Optional[str] = Field(None, max_length=400,
        description='Full hierarchical instance path exactly as read from the circuit (e.g. XU1/M1). Never inferred '
                    'from a name prefix.')
    parameter_name: str = Field(min_length=1, max_length=120,
        description='Canonical parameter name as reported by the circuit reader (e.g. w, l, c, r).')
    initial_value: Optional[float] = Field(None,
        description='The value read from the circuit, in `unit`. The editors show it and take no typed value; empty '
                    'means the value the circuit has. A stated value is checked against the circuit at validation; a '
                    'mismatch is an error, not silently overwritten.')
    unit: str = Field(min_length=0, max_length=32,
        description='Unit of initial value, bounds and step (e.g. um, nm, pF, kohm, count).')
    optimized: bool = Field(True, description='Whether the optimizer may change this variable.')
    value_type: Literal['continuous', 'integer'] = Field('continuous',
        description='continuous; integer (multiplicity, fingers). The policy always proposes a continuous action that '
                    'is projected onto lower + k*step; this is not a discrete-action SAC.')
    lower: Optional[float] = Field(None, description='Lower bound in `unit`. Required for optimized leaders.')
    upper: Optional[float] = Field(None, description='Upper bound in `unit`. Required for optimized leaders.')
    step: Optional[float] = Field(None, gt=0,
        description='Quantization step in `unit` (manufacturing grid). Values are projected to lower + k*step.')
    scale: Literal['linear', 'log'] = Field('linear',
        description='How the normalized action maps to the physical range. log requires lower > 0.')
    binding_group: Optional[str] = Field(None, max_length=120,
        description='variable_id of the leader this variable is tied to. Empty = independent action variable. '
                    'Equal initial values never imply a binding; bindings must be declared here.')
    ratio: float = Field(1.0, gt=0, description='follower = ratio * leader. Must be positive.')
    notes: str = Field('', max_length=1000, description='Free text; not used by the optimizer.')

    @model_validator(mode='before')
    @classmethod
    def _retired_fields(cls, data):
        """A row written before 2026-09-26 may carry name, target_kind, candidates, relation and expression, and its
        value_type may be discrete (RETIRED_PARAMETER_FIELDS). A display name is dropped; an expression that is a
        constant times the leader becomes the ratio; a discrete row whose candidates form a uniform grid becomes
        lower/upper/step. A design-variable target, a non-uniform candidate list and any other expression never ran
        (each was a blocker) and are refused in plain words."""
        if not isinstance(data, dict) or not (RETIRED_PARAMETER_FIELDS.keys() & data.keys()
                                              or data.get('value_type') == 'discrete'):
            return data
        row, who = dict(data), data.get('variable_id') or 'this row'
        if row.pop('target_kind', None) not in (None, 'instance_parameter'):
            raise ValueError(f'{who}: target_kind design_variable is no longer offered; the optimizer writes instance '
                             'parameters only. Give the row the instance path and parameter name of one instance.')
        row.pop('name', None)
        expression, relation = row.pop('expression', None), row.pop('relation', None)
        if relation == 'expression':
            ratio = linear_ratio(expression or '')
            if ratio is None:
                raise ValueError(f'{who}: relation expression is no longer offered, and {expression!r} is not a constant '
                                 'times the leader. Give the ratio instead.')
            row['ratio'] = ratio
        candidates = row.pop('candidates', None)
        if row.get('value_type') == 'discrete':
            grid = uniform_grid(candidates or [])
            if grid is None:
                raise ValueError(f'{who}: value_type discrete is no longer offered, and its candidates are not a uniform '
                                 'grid. Give lower, upper and step instead.')
            row['lower'], row['upper'], row['step'] = grid
            row['value_type'] = 'continuous'
        return row


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
    unit: str = Field(max_length=32, description='Unit of the thresholds and the normalization scale.')
    constraint: Literal['>=', '<=', 'interval'] = Field(
        description='>= lower; <= upper; interval [lower, upper].')
    lower: Optional[float] = Field(None, description='Lower threshold (>=, interval).')
    upper: Optional[float] = Field(None, description='Upper threshold (<=, interval).')
    hard: bool = Field(True,
        description='Hard constraint: must be satisfied for feasibility. Feasibility is decided from raw metric '
                    'values and thresholds, independently of the reward.')
    direction_after_feasible: Literal['none', 'minimize', 'maximize'] = Field('none',
        description='Preference among feasible designs. At most one target may set it; it selects the best design '
                    'and defines the optional objective bonus when its reward weight is nonzero.')
    nominal_only: bool = Field(False, description='Judge this spec at nominal only; otherwise use every planned condition.')
    missing_is_failure: bool = Field(False, description='Missing value = failed: a completed simulation with this required value missing scores a failure. Wrong units and infrastructure errors remain errors.')
    margin_sides: Literal['both', 'lower', 'upper'] = Field('both', description='Margin sides: which limits contribute to the clearance bonus and Corner check ranking. Feasibility still checks every limit.')
    soft_weight: float = Field(1.0, gt=0, description='Relative weight of this target in the reward.')
    normalization_scale: Optional[float] = Field(None, gt=0,
        description='Violation is (threshold distance)/scale, capped at 1. Empty = the size of the threshold: the larger '
                    'of |lower| and |upper|, or 1 when both are zero. Give a physically meaningful scale to use another.')
    active: bool = Field(True, description='Inactive targets affect neither reward nor feasibility.')
    basis: str = Field('', max_length=1000,
        description='Where this requirement comes from (datasheet, user statement...). Agent suggestions must '
                    'state their basis; requirements are never inferred from the circuit alone.')

    @model_validator(mode='before')
    @classmethod
    def _retired_fields(cls, data):
        """A spec written before 2026-10-03 may carry `target` and `tolerance` (RETIRED_TARGET_FIELDS). What they meant is
        kept in the limits, as the compiler applied them: "target +/- tolerance" was the interval [target - tolerance,
        target + tolerance], and a tolerance on any other spec loosened each limit by that much. An empty scale gets the
        size it had, taken from the limits as typed (and |target|). A target without a positive tolerance, or one with
        limits as well, never ran (both were errors) and is refused in plain words."""
        if not isinstance(data, dict) or not (RETIRED_TARGET_FIELDS.keys() & data.keys() or data.get('constraint') == 'target'):
            return data
        row, who = dict(data), data.get('metric_id') or 'this spec'
        number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        target, tolerance = row.pop('target', None), row.pop('tolerance', None)
        tolerance = 0.0 if tolerance is None else tolerance
        if not number(tolerance) or tolerance < 0:
            raise ValueError(f'{who}: tolerance {tolerance!r} is not a number of at least 0. The tolerance column was '
                             'retired; give the limits it was meant to loosen instead.')
        lower, upper = row.get('lower'), row.get('upper')
        size = max([abs(v) for v in (lower, upper, target) if number(v)] or [0.0]) or 1.0
        if row.get('constraint') == 'target':
            if not number(target) or tolerance <= 0 or lower is not None or upper is not None:
                raise ValueError(f'{who}: "target +/- tolerance" is no longer offered, and this spec is not a target with a '
                                 'positive tolerance and no limits (the run refused it). Give an interval instead.')
            row.update(constraint='interval', lower=target - tolerance, upper=target + tolerance)
        elif tolerance:
            row.update({k: v + d for k, v, d in (('lower', lower, -tolerance), ('upper', upper, tolerance)) if number(v)})
        else:
            return row
        if row.get('normalization_scale') is None:
            row['normalization_scale'] = size
        return row

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
class MeasurementDefinition(_Model):
    measurement_id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z_][A-Za-z0-9_.\-]*$',
        description='Stable ID. Spec equations refer to it. A Maestro output\'s ID is m_ + its output name.')
    analysis: Literal['dc', 'ac', 'tran', 'noise', 'stb', 'pss', 'pnoise', 'other'] = Field(
        description='Analysis that produces the raw data.')
    result_source: Literal['backend_profile', 'ade_output'] = Field('backend_profile',
        description='backend_profile: a metric computed by the circuit-profile analyzer. ade_output: a Maestro output '
                    '(needs the bridge). A task measures one way; a new row takes the way of the rows there.')
    source_name: Optional[str] = Field(None, max_length=200,
        description='Metric name in the backend profile, or the ADE output name.')
    signal: Optional[str] = Field(None, max_length=300,
        description='For a Maestro output: its expression, e.g. ymax(VT("/OUT")) or getData("loopGain" ?result "stb"). '
                    'For a profile metric: a label of what is measured, e.g. VOUT.')
    unit: str = Field(max_length=32,
        description='Unit of the measured value. A target using this measurement must have a compatible unit.')
    notes: str = Field('', max_length=1000, description='Free text; not used by the optimizer.')

    @model_validator(mode='before')
    @classmethod
    def _retired_fields(cls, data):
        """A row written before 2026-09-26 may carry function, window, at_frequency_hz, integration_band_hz,
        branch_direction, loop_definition, crossover, on_failure and validity, and one written before 2026-09-29
        conditions and aggregation (RETIRED_MEASUREMENT_FIELDS). No backend ever read them - a set `function`, like
        conditions other than [nominal] or an aggregation other than nominal_only, even blocked the run - so they are
        dropped, whatever they say. The test conditions are the run's (`run.conditions`) and each spec's
        (`PerformanceTarget.nominal_only`), since reward v2. A probe computed from other probes (`result_source`
        expression, retired on 2026-10-03) is a spec equation's job since record 7.52: in a whole configuration its
        arithmetic is written into the equations of the specs that use it (`WorkbenchConfig._expression_probes`); a row
        on its own is refused in plain words."""
        if isinstance(data, dict) and data.get('result_source') == 'expression':
            raise ValueError(f'{data.get("measurement_id") or "this probe"}: a probe computed from other probes (result '
                             'source "expression") is no longer offered. Write its arithmetic in the equation of the spec '
                             'that uses it.')
        return _without_retired(data, RETIRED_MEASUREMENT_FIELDS)


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
    encoder_type: Literal['graph_transformer', 'rgcn', 'gatv2'] = 'graph_transformer'
    hidden_dim: int = Field(32, ge=4, le=1024)
    heads: int = Field(4, ge=1, le=32)
    layers: int = Field(2, ge=1, le=16)
    operating_points: bool = Field(False, description='Include measured nominal device operating points and missing-value masks.')
    vocabulary: str = Field(STANDARD_VOCABULARY, max_length=80, pattern=r'^(standard|pdk:[A-Za-z_][A-Za-z0-9_.\-]{0,63})$',
        description='Which components the network knows. standard: the 8 generic kinds (MOS, R, C, L, sources) every '
                    'model saved before 2026-09-21 was trained with; other parts are "unknown". pdk:<technology '
                    'library>: every component of that PDK, loaded with "Load PDK..." (gator_workbench.pdk). A model '
                    'trained with one list loads only with the same list.')

    @field_validator('encoder_type', mode='before')
    @classmethod
    def _refuse_removed_encoder(cls, value):
        if value == 'gat':
            raise ValueError('gat (GATv1) was replaced by gatv2 on 2026-09-26. Select gatv2 for new training; '
                             'GATv1 weights cannot be loaded into GATv2. Use the historical source matching '
                             'the checkpoint for GATv1 runs.')
        if isinstance(value, str) and value in REMOVED_ENCODERS:
            date, commit = REMOVED_ENCODERS[value]
            raise ValueError(f'{value} was removed from the optimizer on {date}. Choose graph_transformer, rgcn or gatv2. '
                             f'Use the historical source matching the checkpoint; the last version with this encoder '
                             f'is commit {commit}.')
        return value


class SpecRegistryEntry(_Model):
    metric_id: str
    unit: str = Field(description='Canonical unit of the registered metric.')
    reference: float = Field(gt=0, description='Fixed physical reference used for input normalization.')


class AdvancedRL(_Model):
    """Defaults mirror the existing entry points. Changing them changes the checkpoint contract."""
    learning_rate: float = Field(3e-4, gt=0)
    gamma: float = Field(0.99, ge=0, le=1)
    tau: float = Field(0.005, gt=0, le=1)
    alpha_learning_rate: Optional[float] = Field(None, gt=0, description='Alpha learning rate. Empty uses the learning rate above; a positive value gives the entropy temperature its own Adam rate.')
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


class RewardConfig(_Model):
    nominal_gate_band: float = Field(0.5, gt=0, lt=1, description='Nominal gate band: strictly between 0 and 1. Every scored design that passes nominal ranks above one that fails nominal under after_nominal.')
    objective_shape: Literal['clipped', 'compressed'] = Field('clipped', description='Clipped stops the objective bonus at one scale; compressed keeps rewarding improvement below 1.')
    violation_shape: Literal['capped', 'compressed'] = 'capped'
    worst_spec_share: float = Field(0.0, ge=0, le=1)
    objective_weight: float = Field(0.0, ge=0, le=1)
    margin_weight: float = Field(0.0, ge=0, le=1)


class ConditionsConfig(_Model):
    policy: Literal['off', 'always', 'after_nominal'] = 'off'
    corners: list[Literal['ss_hot_low', 'ff_cold_high', 'fs_nominal', 'sf_nominal']] = Field(default_factory=list)

    @model_validator(mode='after')
    def _plan(self):
        if len(set(self.corners)) != len(self.corners):
            raise ValueError('Corner IDs must be unique')
        if (self.policy != 'off') != bool(self.corners):
            raise ValueError('Every planned corner and Corners after nominal passes need a nonempty corner plan; Nominal only must have no corners')
        return self


# Run settings retired on 2026-09-29, each with the default it had. `threads_per_job` never reached a simulator: no task
# ever applied it (`supports_threads` was false for every one), so the box looked like a control that was none. A
# configuration written with it still loads (the before-validator drops it), and both hashes still see it at this
# default (`_hashed`), so every run, checkpoint, task file and approval made before keeps its identity - every stored
# configuration had 1.
RETIRED_RUN_FIELDS = {'threads_per_job': 1}


class SearchSettings(_Model):
    method: Literal['sac', 'llm_warmstart', 'llm', 'sac_llm_rescue'] = 'sac'
    provider: Optional[Literal['claude_code', 'codex']] = None
    model: Optional[str] = Field(None, max_length=120)
    effort: Optional[str] = Field(None, max_length=32)
    candidates_per_call: int = Field(4, ge=1, le=32, strict=True)
    max_llm_calls: Optional[int] = Field(None, ge=1, le=10000, strict=True)
    max_llm_notional_usd: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    llm_call_timeout_seconds: float = Field(600, gt=0, le=7200, allow_inf_nan=False)
    warm_start_count: Optional[int] = Field(None, ge=1, le=100000, strict=True)
    initial_sac_updates: int = Field(8, ge=1, le=1024, strict=True)
    rescue_stagnation_evaluations: int = Field(8, ge=1, le=100000, strict=True)
    rescue_max_rounds: int = Field(2, ge=1, le=10000, strict=True)
    hints_allowed: bool = True


class RunSettings(_Model):
    @model_validator(mode='before')
    @classmethod
    def _retired_fields(cls, data):
        return _without_retired(data, RETIRED_RUN_FIELDS)

    mode: Literal['scratch', 'resume', 'fine_tune', 'frozen'] = 'scratch'
    model_label: Optional[str] = Field(None, max_length=80,
        description='The name the RL model of this run is filed under (record 7.159, independent of any project name). '
                    'resume, fine_tune and frozen start from the newest model saved under it. Empty: the task\'s run label.')
    concurrency: int = Field(1, ge=1, le=64,
        description='Number of independent simulation jobs running at once. Not the thread count of one job.')
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
    search: SearchSettings = Field(default_factory=SearchSettings)
    reward: RewardConfig = Field(default_factory=RewardConfig)
    conditions: ConditionsConfig = Field(default_factory=ConditionsConfig)
    model_source: ModelSource = Field(default_factory=ModelSource)
    advanced: AdvancedRL = Field(default_factory=AdvancedRL)
    cache_policy: Literal['disabled'] = Field('disabled',
        description='The existing environment has no result cache; duplicates are simulated and counted.')
    continual_learning: bool = Field(False,
        description='Explicit opt-in to inherit weights fine-tuned on a previous test task. Default starts every '
                    'test task from the fixed source checkpoint.')

    @model_validator(mode='after')
    def _search_contract(self):
        search = self.search
        if search.method == 'sac':
            return self
        if search.max_llm_calls is None:
            raise ValueError('Choose a maximum number of AI calls before starting an LLM search')
        if search.provider == 'claude_code' and search.max_llm_notional_usd is None:
            raise ValueError('Claude sizing needs a notional cost ceiling')
        if self.mode == 'frozen':
            raise ValueError('A frozen policy supports SAC only')
        if search.method == 'llm':
            if self.mode == 'fine_tune' or self.concurrency != 1:
                raise ValueError('LLM only uses one simulation lane and supports scratch or resume, without an RL model')
            if self.mode == 'scratch' and self.model_source.run_dir:
                raise ValueError('LLM only does not load a saved RL model; clear the model source or resume AI search progress')
        if search.method == 'llm_warmstart':
            count = search.warm_start_count or max(8, self.advanced.batch_size, self.advanced.warmup_transitions)
            if count < self.advanced.batch_size or self.advanced.replay_capacity < count:
                raise ValueError('Starting designs must fill one training batch and fit in the replay buffer')
        return self


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
# Research labels retired on 2026-10-03 (record 7.163; user, on "which should be kept": "Remove both"), each with the
# default it had. Nothing read `experiment_group` (Output settings' experiment name groups a run's folder) or
# `test_tasks`. A configuration written with them still loads (the before-validator drops them), and the configuration
# hash still sees them at these defaults (`_hashed`), so every approval and run made before keeps its identity; the task
# hash never saw research labels.
RETIRED_RESEARCH_FIELDS = {'experiment_group': UNSPECIFIED, 'test_tasks': []}


class ResearchLabels(_Model):
    @model_validator(mode='before')
    @classmethod
    def _retired_fields(cls, data):
        return _without_retired(data, RETIRED_RESEARCH_FIELDS)

    split: Literal['train', 'validation', 'test', 'unspecified'] = 'unspecified'
    generalization_level: Literal['same_task', 'unseen_spec', 'unseen_topology', 'unseen_circuit_class',
                                  'unspecified'] = 'unspecified'
    training_sources: list[str] = Field(default_factory=list,
        description='Task IDs/classes the source model was trained on.')
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

    @model_validator(mode='before')
    @classmethod
    def _expression_probes(cls, data):
        """A configuration written before 2026-10-03 may hold Probes computed from other probes (`result_source`
        expression, with `expression`, RETIRED_MEASUREMENT_FIELDS). Their arithmetic goes, in parentheses, into the
        equations of the specs that use them (and of such probes first), and the probes go: the specs compute the same
        numbers with the same evaluator, which the probes used too. A cycle of such probes never ran and is refused."""
        rows = data.get('measurements') if isinstance(data, dict) else None
        computed = {m.get('measurement_id'): m.get('expression') or '' for m in rows or []
                    if isinstance(m, dict) and m.get('result_source') == 'expression'} if isinstance(rows, list) else {}
        if not computed:
            return data

        def written(text, seen=()):
            for name in [n for n in computed if isinstance(n, str) and _equation_uses(text, n)]:
                if name in seen:
                    raise ValueError(f'Probe {name} is computed from itself; a cycle of expression probes never ran.')
                text = _replace_name(text, name, f'({written(computed[name], seen + (name,))})')
            return text
        targets = [dict(t, equation=written(t['equation'])) if isinstance(t, dict) and isinstance(t.get('equation'), str)
                   else t for t in data.get('targets') or []]
        return dict(data, targets=targets, measurements=[m for m in rows if not (isinstance(m, dict)
                                                                                     and m.get('result_source') == 'expression')])

    @model_validator(mode='after')
    def _reward_contract(self):
        # The objective rows (one at most, with the limit its direction needs) are checked by validation.py as
        # plain-language errors of the checklist, not here: a half-edited table must still load and be shown.
        if self.run.conditions.policy != 'off':
            # The removed OTA7 task stays accepted HERE, so its saved runs and configurations still parse; the task itself
            # is refused where it would load (tasks.REMOVED_REAL_TASKS, record 7.128).
            if self.circuit.source != 'registered_task' or self.circuit.task_id != 'real:gpdk045_ota7':
                raise ValueError('No task trains at corners: the only one, the real OTA7 task, was removed on 2026-09-30')
            if self.run.max_spectre_launches is None or self.run.max_retries:
                raise ValueError('Robust training needs a finite launch cap and zero automatic retries')
        return self


# --------------------------------------------------------------------------- helpers
SECTIONS = {'parameters': OptimizationParameter, 'targets': PerformanceTarget,
            'measurements': MeasurementDefinition}
SECTION_KEYS = {'parameters': 'variable_id', 'targets': 'metric_id', 'measurements': 'measurement_id'}


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


_ONE_PROBE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]*$')


def _name_pattern(name):
    """A Probe ID as a whole name in a spec equation: its names are plain identifiers (spec_equations.parse reads them
    with Python's ast), so neither a longer name nor a number's SI suffix (2m) holds it."""
    return re.compile(rf'(?<![A-Za-z0-9_.]){re.escape(name)}(?![A-Za-z0-9_])')


def _equation_uses(text, name):
    return isinstance(text, str) and bool(_name_pattern(name).search(text))


def _replace_name(text, name, replacement):
    return _name_pattern(name).sub(lambda _: replacement, text)


def _hashed(data):
    """What both hashes see. A spec whose equation is one Probe ID is hashed in the form every configuration had before
    specs were equations (`measurement_id`), so a configuration written earlier keeps its hashes: its runs still
    resume, its checkpoints still load, and approvals and proposals made for it still bind. The network's component list
    (`run.network.vocabulary`, added later) is hashed as absent while it is the standard one, for the same reason. The
    Parameters and Probes fields retired on 2026-09-26 (record 7.92) and 2026-09-29 (record 7.105, the Probes' conditions
    and aggregation) are hashed as present at their old defaults, for the
    same reason again; a row that stated another value for one of them (it never ran, or the run refused it) hashes
    differently since. So is the retired `run.threads_per_job` (2026-09-29, RETIRED_RUN_FIELDS). The RL model's label
    (`run.model_label`, record 7.159) is hashed as absent while it is not set. The research labels retired on 2026-10-03
    (record 7.163, RETIRED_RESEARCH_FIELDS) are hashed as present at their old defaults, and so are the Specs' target and
    tolerance and the Probes' expression retired the same day (RETIRED_TARGET_FIELDS, RETIRED_MEASUREMENT_FIELDS): a spec
    that used them, or a probe computed from others, was rewritten when it loaded and hashes differently since."""
    data = dict(data)
    research = data.get('research') if isinstance(data, dict) else None
    if isinstance(research, dict):
        data['research'] = dict(research, **{key: research.get(key, default) for key, default in RETIRED_RESEARCH_FIELDS.items()})
    run = data.get('run') if isinstance(data, dict) else None
    if isinstance(run, dict):
        run = dict(run, **{key: run.get(key, default) for key, default in RETIRED_RUN_FIELDS.items()})
        if run.get('model_label') is None:
            run.pop('model_label', None)
        reward = run.get('reward')
        if run.get('search') == SearchSettings().model_dump(mode='json'):
            run.pop('search')
        if isinstance(reward, dict):
            reward = {k: v for k, v in reward.items() if not
                      (k == 'nominal_gate_band' and v == 0.5 or k == 'objective_shape' and v == 'clipped')}
            legacy_default = {k: v for k, v in RewardConfig().model_dump(mode='json').items()
                              if k not in ('nominal_gate_band', 'objective_shape')}
            if reward == legacy_default:
                run.pop('reward')
            else:
                run['reward'] = reward
        advanced = run.get('advanced')
        if isinstance(advanced, dict) and advanced.get('alpha_learning_rate') is None:
            run['advanced'] = {k: v for k, v in advanced.items() if k != 'alpha_learning_rate'}
        if run.get('conditions') == ConditionsConfig().model_dump(mode='json'):
            run.pop('conditions')
        data['run'] = run
    network = run.get('network') if isinstance(run, dict) else None
    if isinstance(network, dict):
        network = dict(network)
        if network.get('vocabulary') == STANDARD_VOCABULARY:
            network.pop('vocabulary')
        if network.get('operating_points') is False:
            network.pop('operating_points')
        data['run'] = dict(run, network=network)
    for section, retired in (('parameters', RETIRED_PARAMETER_FIELDS), ('measurements', RETIRED_MEASUREMENT_FIELDS)):
        rows = data.get(section) if isinstance(data, dict) else None
        if isinstance(rows, list):
            data = dict(data, **{section: [dict(retired, **row) if isinstance(row, dict) else row for row in rows]})
    targets = data.get('targets') if isinstance(data, dict) else None
    if not isinstance(targets, list):
        return data
    targets = [{k: v for k, v in dict(RETIRED_TARGET_FIELDS, **row).items()
                if not (k in ('nominal_only', 'missing_is_failure') and v is False or k == 'margin_sides' and v == 'both')}
               if isinstance(row, dict) else row for row in targets]
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


# Columns the editors show only after "More columns": they exist, an agent may set them, a task file keeps them. The
# Parameters' four were always the same in the saved tasks (review of 2026-10-03): Save task takes value_type and the step
# from the PDK, ratio must equal what the circuit shows, and nobody chose a log scale.
ADVANCED_COLUMNS = {'targets': ('soft_weight', 'active', 'basis', 'missing_is_failure', 'margin_sides'),
                    'parameters': ('value_type', 'step', 'scale', 'ratio')}
# Columns the editors do not show at all: the value follows from elsewhere, and the rows keep it (task files, both hashes,
# the agent, the parked AnalogGym import). initial_value was never filled in a saved task - Save task empties it - and
# result_source is the task's one way of measuring: a new Probes row takes it from the rows there (review of 2026-10-03).
HIDDEN_COLUMNS = {'parameters': ('initial_value',), 'measurements': ('result_source',)}


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
                            guidance=info.description or '', default=prop.get('default'),
                            advanced=name in ADVANCED_COLUMNS.get(section, ()),
                            hidden=name in HIDDEN_COLUMNS.get(section, ())))
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
