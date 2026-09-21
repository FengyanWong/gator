"""Semantic validation shared by manual edits, agent proposals and run start.

Structural validity is pydantic's job (schema.py). This module checks meaning:
ranges, units, integer constraints, binding cycles/conflicts, measurement
definitions, and whether the *existing* optimizer backend can execute what the
configuration expresses. Anything the backend cannot execute is reported as a
blocking issue; it is never silently dropped or approximated.

Levels:
  error      - inconsistent configuration; blocks a run.
  blocker    - consistent, but not executable by the current backend; blocks a run.
  warning    - allowed, but the user should know.
  unresolved - information that needs the user's confirmation.
  info
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from . import units
from .schema import WorkbenchConfig

FEATURE_PARAMETER_KINDS = ('w', 'l', 'm', 'nf', 'r', 'c', 'ind', 'dc')
BLOCKING = ('error', 'blocker')


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    path: str
    message: str

    def as_dict(self):
        return asdict(self)


class Report:
    def __init__(self):
        self.issues: list[Issue] = []
        self.facts: dict = {}

    def add(self, level, code, path, message):
        self.issues.append(Issue(level, code, path, message))

    @property
    def blocks_run(self):
        return any(i.level in BLOCKING for i in self.issues)

    def as_dict(self):
        counts = {}
        for issue in self.issues:
            counts[issue.level] = counts.get(issue.level, 0) + 1
        return dict(blocks_run=self.blocks_run, counts=counts, facts=self.facts,
                    issues=[i.as_dict() for i in self.issues])


def _integral(value):
    return value is not None and math.isclose(value, round(value), abs_tol=1e-9)


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


def resolve_leaders(parameters):
    """Map variable_id -> (leader_id, cumulative_ratio) or raise ValueError on a cycle/dangling link."""
    by_id = {p.variable_id: p for p in parameters}
    resolved = {}
    for parameter in parameters:
        ratio, current, seen = 1.0, parameter, [parameter.variable_id]
        while current.binding_group:
            if current.binding_group not in by_id:
                raise ValueError(f'{current.variable_id}: binding_group {current.binding_group!r} does not exist')
            step_ratio = current.ratio if current.relation == 'ratio' else linear_ratio(current.expression or '')
            if step_ratio is None:
                raise ValueError(f'{current.variable_id}: expression is not an executable positive ratio')
            ratio *= step_ratio
            current = by_id[current.binding_group]
            if current.variable_id in seen:
                raise ValueError('binding cycle: ' + ' -> '.join(seen + [current.variable_id]))
            seen.append(current.variable_id)
        resolved[parameter.variable_id] = (current.variable_id, ratio)
    return resolved


def independent_action_count(parameters):
    try:
        leaders = resolve_leaders(parameters)
    except ValueError:
        return None
    by_id = {p.variable_id: p for p in parameters}
    return len({leader for leader, _ in leaders.values() if by_id[leader].optimized})


# ------------------------------------------------------------------------------ sections
def _check_parameters(config, report, graph):
    parameters = config.parameters
    seen, targets = set(), {}
    for i, p in enumerate(parameters):
        path = f'parameters[{i}]'
        if p.variable_id in seen:
            report.add('error', 'duplicate_variable_id', path, f'Duplicate variable_id {p.variable_id!r}')
        seen.add(p.variable_id)
        if not units.known(p.unit):
            report.add('error', 'unknown_unit', path + '.unit', f'Unknown unit {p.unit!r}')
            continue
        if units.is_affine(p.unit):
            report.add('error', 'affine_unit', path + '.unit', 'Offset units cannot be used for sizing variables')
        if p.target_kind == 'instance_parameter':
            if not p.instance_path:
                report.add('error', 'missing_instance_path', path + '.instance_path',
                           'instance_parameter needs the instance path read from the circuit')
            key = (p.instance_path, p.parameter_name)
            if key in targets:
                report.add('error', 'conflicting_targets', path,
                           f'{p.variable_id} and {targets[key]} both write {p.instance_path}.{p.parameter_name}')
            targets[key] = p.variable_id
            expected = units.PARAMETER_KIND_UNITS.get(p.parameter_name)
            if expected and units.canonical_unit(p.unit) != expected:
                report.add('error', 'unit_mismatch', path + '.unit',
                           f'Parameter {p.parameter_name!r} is measured in {expected}, not {p.unit!r}')
            if p.parameter_name not in FEATURE_PARAMETER_KINDS:
                report.add('blocker', 'parameter_kind_unsupported', path + '.parameter_name',
                           f'{p.parameter_name!r} is not in the optimizer feature vocabulary '
                           f'{FEATURE_PARAMETER_KINDS}; the graph encoder cannot represent it')
        else:
            report.add('blocker', 'design_variable_writeback_unsupported', path + '.target_kind',
                       'Existing adapters write instance parameters only; global/ADE design-variable writeback '
                       'is not implemented. Kept in the configuration, but it blocks a run.')
        if p.binding_group == p.variable_id:
            report.add('error', 'self_binding', path + '.binding_group', 'A variable cannot be bound to itself')
        if p.relation == 'expression':
            if not p.expression:
                report.add('error', 'missing_expression', path + '.expression', 'relation=expression needs one')
            elif linear_ratio(p.expression) is None:
                report.add('blocker', 'expression_not_executable', path + '.expression',
                           'Only expressions equal to a positive constant times `leader` can be executed by the '
                           'action mapper (members follow their group by a fixed ratio). Rejected, not evaluated.')
        if p.relation == 'expression' and not p.binding_group:
            report.add('error', 'expression_without_leader', path, 'An expression relation needs a binding_group')
        leader_like = not p.binding_group
        if p.value_type == 'discrete':
            if not p.candidates:
                report.add('error', 'missing_candidates', path + '.candidates', 'discrete needs candidate values')
            else:
                grid = uniform_grid(p.candidates)
                if grid is None:
                    report.add('blocker', 'nonuniform_candidates', path + '.candidates',
                               'The action mapper projects onto lower + k*step. A non-uniform candidate list has '
                               'no equivalent and is not approximated.')
                elif any(v is not None and not math.isclose(v, g, rel_tol=1e-9, abs_tol=1e-18)
                         for v, g in zip((p.lower, p.upper, p.step), grid)):
                    report.add('error', 'candidates_conflict', path,
                               'lower/upper/step disagree with the candidate grid; leave them empty or match')
        elif p.candidates:
            report.add('warning', 'candidates_ignored', path + '.candidates', 'Used only for value_type=discrete')
        lower, upper, step = p.lower, p.upper, p.step
        if p.value_type == 'discrete' and p.candidates and uniform_grid(p.candidates):
            lower, upper, step = uniform_grid(p.candidates)
        if p.optimized and leader_like:
            if lower is None or upper is None:
                report.add('error', 'missing_bounds', path, 'An optimized independent variable needs both bounds')
            elif not lower < upper:
                report.add('error', 'invalid_bounds', path, f'lower ({lower}) must be below upper ({upper})')
            else:
                if p.scale == 'log' and lower <= 0:
                    report.add('error', 'log_scale_nonpositive', path + '.scale', 'log scale needs lower > 0')
                if step is not None and step > upper - lower:
                    report.add('error', 'step_exceeds_range', path + '.step', 'step is larger than the range')
                if p.initial_value is not None:
                    if not lower <= p.initial_value <= upper:
                        report.add('error', 'initial_out_of_bounds', path + '.initial_value',
                                   f'{p.initial_value} is outside [{lower}, {upper}]')
                    elif step and not _integral((p.initial_value - lower) / step):
                        report.add('error', 'initial_off_grid', path + '.initial_value',
                                   'Initial value is not on lower + k*step; the optimizer requires a legal start')
        if p.value_type == 'integer':
            for name, value in (('lower', lower), ('upper', upper), ('initial_value', p.initial_value),
                                ('step', step)):
                if value is not None and not _integral(value):
                    report.add('error', 'integer_constraint', f'{path}.{name}', f'{name} must be an integer')
    try:
        leaders = resolve_leaders(parameters)
    except ValueError as exc:
        report.add('error', 'binding_graph', 'parameters', str(exc))
        leaders = None
    by_id = {p.variable_id: p for p in parameters}
    if leaders:
        for i, p in enumerate(parameters):
            leader_id, ratio = leaders[p.variable_id]
            if leader_id == p.variable_id:
                continue
            leader, path = by_id[leader_id], f'parameters[{i}]'
            if units.known(p.unit) and units.known(leader.unit) and not units.compatible(p.unit, leader.unit):
                report.add('error', 'binding_unit_mismatch', path + '.unit',
                           f'{p.variable_id} ({p.unit}) cannot follow {leader_id} ({leader.unit})')
            if p.optimized != leader.optimized:
                report.add('warning', 'follower_flag_ignored', path + '.optimized',
                           f'A bound variable follows its leader {leader_id}; its own optimized flag has no effect')
            if p.parameter_name != leader.parameter_name:
                report.add('blocker', 'mixed_parameter_kind_group', path,
                           'The optimizer groups members of one parameter kind; binding different parameter '
                           'names in one group is not supported')
            if (leader.lower is not None and leader.upper is not None and units.known(p.unit)
                    and units.compatible(p.unit, leader.unit)):
                low = units.to_canonical(leader.lower, leader.unit) * ratio
                high = units.to_canonical(leader.upper, leader.unit) * ratio
                if p.lower is not None and low < units.to_canonical(p.lower, p.unit) * (1 - 1e-12):
                    report.add('error', 'binding_violates_member_bound', path + '.lower',
                               f'leader range x ratio reaches {low:g}, below this member lower bound')
                if p.upper is not None and high > units.to_canonical(p.upper, p.unit) * (1 + 1e-12):
                    report.add('error', 'binding_violates_member_bound', path + '.upper',
                               f'leader range x ratio reaches {high:g}, above this member upper bound')
            if (p.initial_value is not None and leader.initial_value is not None and units.known(p.unit)
                    and units.compatible(p.unit, leader.unit)):
                expected = units.to_canonical(leader.initial_value, leader.unit) * ratio
                actual = units.to_canonical(p.initial_value, p.unit)
                if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-18):
                    report.add('error', 'binding_initial_mismatch', path + '.initial_value',
                               f'Initial value {actual:g} is not ratio x leader ({expected:g}); the optimizer '
                               'requires current values to satisfy declared bindings')
    report.facts['independent_action_variables'] = independent_action_count(parameters)
    report.facts['parameter_rows'] = len(parameters)
    if not any(p.optimized for p in parameters):
        report.add('error', 'nothing_to_optimize', 'parameters', 'At least one optimized variable is required')
    if graph is not None:
        _check_parameters_against_circuit(config, report, graph)


def _check_bindings_against_circuit(config, report, graph):
    """Declared bindings must already hold in the circuit as read: the optimizer requires current
    member values to equal ratio x group value, and nothing here 'fixes' the circuit silently."""
    try:
        leaders = resolve_leaders(config.parameters)
    except ValueError:
        return
    by_id = {p.variable_id: p for p in config.parameters}

    def circuit_value(p):
        value = graph.parameters.get(p.instance_path or '', {}).get(p.parameter_name)
        return value.value if value is not None and value.valid else None
    for i, p in enumerate(config.parameters):
        leader_id, ratio = leaders[p.variable_id]
        if leader_id == p.variable_id:
            continue
        own, lead = circuit_value(p), circuit_value(by_id[leader_id])
        if own is not None and lead is not None and not math.isclose(own, lead * ratio, rel_tol=1e-9, abs_tol=1e-18):
            report.add('error', 'binding_initial_mismatch', f'parameters[{i}]',
                       f'In the circuit {p.instance_path}.{p.parameter_name} = {own:g}, but ratio x leader '
                       f'({leader_id}) = {lead * ratio:g}. Change the ratio, or modify the circuit first.')


def _check_parameters_against_circuit(config, report, graph):
    _check_bindings_against_circuit(config, report, graph)
    devices = {d.id: d for d in graph.devices}
    for i, p in enumerate(config.parameters):
        if p.target_kind != 'instance_parameter' or not p.instance_path:
            continue
        path = f'parameters[{i}]'
        device = devices.get(p.instance_path)
        if device is None:
            report.add('error', 'unknown_instance', path + '.instance_path',
                       f'{p.instance_path!r} is not an instance of the loaded circuit')
            continue
        if device.kind == 'unknown':
            report.add('error', 'unknown_device_semantics', path,
                       f'{p.instance_path} uses an unmapped model; its parameters cannot be optimized')
        value = graph.parameters.get(p.instance_path, {}).get(p.parameter_name)
        if value is None:
            report.add('error', 'unknown_parameter', path + '.parameter_name',
                       f'{p.instance_path} has no parameter {p.parameter_name!r}')
        elif not value.valid:
            report.add('unresolved', 'unresolved_parameter', path,
                       f'{p.instance_path}.{p.parameter_name} = {value.raw!r} could not be resolved '
                       f'({value.reason}); confirm its value before optimizing')
        elif p.initial_value is not None and units.known(p.unit) and not units.is_affine(p.unit):
            actual = units.to_canonical(p.initial_value, p.unit)
            if not math.isclose(actual, value.value, rel_tol=1e-9, abs_tol=1e-24):
                report.add('error', 'initial_differs_from_circuit', path + '.initial_value',
                           f'Configuration says {actual:g} but the circuit has {value.value:g} (canonical units)')


def _check_measurements(config, report, *, provided_metrics):
    ids = {}
    for i, m in enumerate(config.measurements):
        path = f'measurements[{i}]'
        if m.measurement_id in ids:
            report.add('error', 'duplicate_measurement_id', path, f'Duplicate measurement_id {m.measurement_id!r}')
        ids[m.measurement_id] = m
        if not units.known(m.unit):
            report.add('error', 'unknown_unit', path + '.unit', f'Unknown unit {m.unit!r}')
        if m.window is not None:
            if not m.window.start < m.window.stop:
                report.add('error', 'invalid_window', path + '.window', 'window start must be below stop')
            if not units.known(m.window.unit) or units.canonical_unit(m.window.unit) not in ('s', 'Hz'):
                report.add('error', 'invalid_window_unit', path + '.window.unit', 'window unit must be time or Hz')
        for j, condition in enumerate(m.validity):
            if condition.kind in ('min', 'max') and condition.value is None:
                report.add('error', 'validity_needs_value', f'{path}.validity[{j}]', 'min/max need a value')
        if m.result_source == 'backend_profile':
            if not m.source_name:
                report.add('error', 'missing_source_name', path + '.source_name',
                           'backend_profile needs the metric name produced by the circuit profile')
            elif provided_metrics is not None and m.source_name not in provided_metrics:
                report.add('error', 'metric_not_provided', path + '.source_name',
                           f'The selected task backend does not produce {m.source_name!r}; it provides '
                           f'{sorted(provided_metrics)}')
            if m.function is not None:
                report.add('warning', 'function_ignored_for_profile', path + '.function',
                           'The verified profile analyzer defines this extraction; `function` is documentation only')
        elif m.result_source == 'ade_output':
            if not m.source_name:
                report.add('error', 'missing_source_name', path + '.source_name', 'ade_output needs the output name')
            report.add('blocker', 'ade_outputs_not_wired', path + '.result_source',
                       'Reading ADE/Maestro outputs during optimization is not implemented by the existing '
                       'backends (they evaluate circuit-profile analyzers). Supported sources: backend_profile, '
                       'expression.')
        elif m.result_source == 'expression':
            if not m.expression:
                report.add('error', 'missing_expression', path + '.expression', 'expression source needs one')
        # Domain rules for user-defined extraction functions (Section 3 of the specification).
        if m.function is not None and m.result_source != 'backend_profile':
            if m.function in ('frequency', 'period'):
                if m.analysis not in ('tran', 'pss'):
                    report.add('error', 'frequency_needs_time_domain', path + '.analysis',
                               'Frequency/period extraction needs a tran or pss analysis')
                if m.analysis == 'tran' and m.window is None:
                    report.add('error', 'frequency_needs_window', path + '.window',
                               'A frequency measurement needs a defined steady-state window')
            if m.function == 'average_power':
                if not m.signal:
                    report.add('error', 'power_needs_branch', path + '.signal', 'Power needs a supply branch')
                if m.branch_direction is None:
                    report.add('error', 'power_needs_direction', path + '.branch_direction',
                               'Power needs an explicit branch-direction convention; the sign is not guessed')
            if m.function in ('phase_margin', 'gain_margin'):
                if not m.loop_definition:
                    report.add('error', 'margin_needs_loop', path + '.loop_definition',
                               'Phase/gain margin needs a loop-gain definition')
                if m.function == 'phase_margin' and m.crossover is None:
                    report.add('error', 'margin_needs_crossover', path + '.crossover',
                               'Phase margin needs the unity-gain crossover definition')
            if m.function in ('spot_noise', 'gain_at') and m.at_frequency_hz is None:
                report.add('error', 'needs_frequency_point', path + '.at_frequency_hz',
                           f'{m.function} needs a frequency point')
            if m.function == 'integrated_noise':
                band = m.integration_band_hz
                if band is None or not 0 < band[0] < band[1]:
                    report.add('error', 'noise_needs_band', path + '.integration_band_hz',
                               'Integrated noise needs 0 < f_low < f_high')
            if m.function in ('spot_noise', 'integrated_noise') and m.analysis not in ('noise', 'pnoise'):
                report.add('error', 'noise_needs_noise_analysis', path + '.analysis', 'Noise needs noise/pnoise')
            report.add('blocker', 'generic_extraction_not_wired', path + '.function',
                       'The existing backends have no generic waveform extractor; user-defined extraction '
                       'functions are validated and stored but cannot be executed yet.')
        if list(m.conditions) != ['nominal'] or m.aggregation != 'nominal_only':
            report.add('blocker', 'nominal_only_backend', path + '.conditions',
                       'The sizing environment is nominal-only; PVT/Monte-Carlo scheduling is not implemented. '
                       'Use conditions=[nominal], aggregation=nominal_only.')
    _check_expression_measurements(config, report, ids)
    return ids


def _expression_symbols(expression):
    from analog_optimizer.netlist.expressions import evaluate, UnresolvedExpression
    names = []

    def lookup(name):
        names.append(name)
        return 1.0
    try:
        evaluate(expression, lookup)
    except ZeroDivisionError:
        pass
    except UnresolvedExpression as exc:
        return None, str(exc)
    return names, None


def _check_expression_measurements(config, report, ids):
    graph = {}
    for i, m in enumerate(config.measurements):
        if m.result_source != 'expression' or not m.expression:
            continue
        names, error = _expression_symbols(m.expression)
        path = f'measurements[{i}].expression'
        if names is None:
            report.add('error', 'expression_rejected', path,
                       f'Unsupported expression ({error}). Allowed: numbers, measurement IDs, + - * / ** ( )')
            continue
        unknown = [n for n in names if n not in ids]
        if unknown:
            report.add('error', 'expression_unknown_symbol', path, f'Unknown measurement IDs: {unknown}')
        graph[m.measurement_id] = [n for n in names if n in ids]
    state = {}

    def visit(node, trail):
        if state.get(node) == 'done':
            return
        if state.get(node) == 'open':
            report.add('error', 'expression_cycle', 'measurements', 'cycle: ' + ' -> '.join(trail + [node]))
            return
        state[node] = 'open'
        for child in graph.get(node, []):
            visit(child, trail + [node])
        state[node] = 'done'
    for node in graph:
        visit(node, [])


def _check_targets(config, report, measurement_ids, *, registry):
    seen, preference, active_hard = set(), [], 0
    for i, t in enumerate(config.targets):
        path = f'targets[{i}]'
        if t.metric_id in seen:
            report.add('error', 'duplicate_metric_id', path, f'Duplicate metric_id {t.metric_id!r}')
        seen.add(t.metric_id)
        if not units.known(t.unit):
            report.add('error', 'unknown_unit', path + '.unit', f'Unknown unit {t.unit!r}')
        measurement = measurement_ids.get(t.measurement_id)
        if measurement is None:
            report.add('error', 'unknown_measurement', path + '.measurement_id',
                       f'No measurement definition {t.measurement_id!r}')
        elif units.known(t.unit) and units.known(measurement.unit) and not units.compatible(t.unit, measurement.unit):
            report.add('error', 'target_unit_mismatch', path + '.unit',
                       f'Target unit {t.unit} is incompatible with measurement unit {measurement.unit}')
        given = dict(lower=t.lower is not None, upper=t.upper is not None, target=t.target is not None)
        need = {'>=': ('lower',), '<=': ('upper',), 'interval': ('lower', 'upper'), 'target': ('target',)}[t.constraint]
        for name in need:
            if not given[name]:
                report.add('error', 'missing_threshold', f'{path}.{name}', f'constraint {t.constraint} needs {name}')
        for name, present in given.items():
            if present and name not in need:
                report.add('error', 'unexpected_threshold', f'{path}.{name}',
                           f'{name} is not used by constraint {t.constraint}; remove it to avoid ambiguity')
        if t.constraint == 'interval' and given['lower'] and given['upper'] and t.lower > t.upper:
            report.add('error', 'invalid_interval', path, 'lower must not exceed upper')
        if t.constraint == 'target' and t.tolerance <= 0:
            report.add('error', 'target_needs_tolerance', path + '.tolerance',
                       'target-with-tolerance needs a positive tolerance')
        if t.direction_after_feasible != 'none' and t.active:
            preference.append(t.metric_id)
        if t.active and t.hard:
            active_hard += 1
        if units.known(t.unit) and units.is_affine(t.unit):
            report.add('error', 'affine_unit', path + '.unit', 'Offset units are not supported for targets')
        if registry is not None and units.known(t.unit) and not units.is_affine(t.unit):
            entry = registry.get(t.metric_id)
            if entry is None:
                report.add('blocker', 'metric_not_in_registry', path + '.metric_id',
                           f'{t.metric_id!r} is not in the RL specification registry {sorted(registry)}. Add it '
                           'under Run > Advanced > spec_registry (this changes checkpoint compatibility).')
            elif units.canonical_unit(t.unit) != units.canonical_unit(entry) if units.known(entry) else True:
                report.add('error', 'registry_unit_mismatch', path + '.unit',
                           f'Registry expects {entry!r} for {t.metric_id}')
        if not t.basis.strip():
            report.add('info', 'basis_not_stated', path + '.basis', 'The source of this requirement is not recorded')
    if len(preference) > 1:
        report.add('error', 'multiple_preferences', 'targets',
                   f'Only one target may set direction_after_feasible; found {preference}')
    if active_hard == 0:
        report.add('error', 'no_hard_constraint', 'targets',
                   'At least one active hard constraint is required to define feasibility')
    used = {t.measurement_id for t in config.targets}
    for i, m in enumerate(config.measurements):
        referenced = any(m.measurement_id in (_expression_symbols(o.expression)[0] or [])
                         for o in config.measurements if o.result_source == 'expression' and o.expression)
        if m.measurement_id not in used and not referenced:
            report.add('warning', 'unused_measurement', f'measurements[{i}]', 'No target uses this measurement')


def _check_run(config, report):
    run, adv = config.run, config.run.advanced
    if run.mode in ('resume', 'fine_tune', 'frozen') and not run.model_source.run_dir:
        report.add('error', 'missing_model_source', 'run.model_source.run_dir',
                   f'mode={run.mode} loads an existing model; select a source run. There is no silent fallback '
                   'to scratch.')
    if run.mode == 'scratch' and run.model_source.run_dir:
        report.add('warning', 'source_ignored_in_scratch', 'run.model_source.run_dir',
                   'scratch never loads weights; the selected source is ignored')
    fine_tune_only = [name for name in ('freeze_encoder', 'encoder_only_transfer', 'reset_critic',
                                        'reset_temperature') if getattr(adv, name)]
    if fine_tune_only and run.mode != 'fine_tune':
        report.add('error', 'fine_tune_only_option', 'run.advanced',
                   f'{fine_tune_only} apply to fine_tune only (mode is {run.mode})')
    if adv.encoder_only_transfer and adv.reset_critic:
        report.add('info', 'redundant_reset_critic', 'run.advanced.reset_critic',
                   'encoder_only_transfer already leaves critic heads random; critic encoders are still loaded '
                   'unless reset_critic is set')
    net = run.network
    if net.encoder_type in ('graph_transformer', 'gat') and net.hidden_dim % net.heads:
        report.add('error', 'heads_divisibility', 'run.network', 'hidden_dim must be divisible by heads')
    if run.mode != 'frozen' and run.max_evaluations < adv.batch_size + 1:
        report.add('warning', 'budget_below_batch', 'run.max_evaluations',
                   'The budget cannot fill one batch; no learner update will occur')
    if run.mode != 'frozen' and run.max_evaluations <= adv.warmup_transitions:
        report.add('warning', 'budget_within_warmup', 'run.advanced.warmup_transitions',
                   'The whole budget is random warm-up exploration; the policy never chooses an action. Published '
                   'settings assume thousands of simulations: lower the warm-up or raise the budget')
    if run.mode == 'frozen':
        report.add('info', 'frozen_no_updates', 'run.mode',
                   'frozen: no weight, temperature or normalization updates; no learner_updates rows are written')
    if adv.spec_registry is not None:
        names = [e.metric_id for e in adv.spec_registry]
        if len(set(names)) != len(names) or not names:
            report.add('error', 'invalid_spec_registry', 'run.advanced.spec_registry', 'IDs must be unique, nonempty')
        for j, entry in enumerate(adv.spec_registry):
            if not units.known(entry.unit):
                report.add('error', 'unknown_unit', f'run.advanced.spec_registry[{j}].unit', entry.unit)
    out = config.output
    if not out.save_replay_snapshots:
        report.add('warning', 'no_full_resume', 'output.save_replay_snapshots',
                   'Replay snapshots are off: checkpoints will be weights_only and a FULL training-state resume '
                   'of this run will not be possible.')
    if not out.save_checkpoints:
        report.add('warning', 'no_checkpoints', 'output.save_checkpoints',
                   'Checkpoints are off: the run can be neither resumed nor used as a transfer source.')
    if not out.save_transition_archive:
        report.add('warning', 'no_transition_archive', 'output.save_transition_archive',
                   'The complete experience archive is off. A replay snapshot is NOT a complete history once the '
                   'circular buffer evicts samples.')


def _check_research(config, report, *, for_generalization=False):
    r = config.research
    level = 'error' if for_generalization else 'info'
    missing = [name for name in ('experiment_group', 'comparison_pair_id', 'method_label')
               if getattr(r, name) == 'unspecified']
    missing += [name for name in ('split', 'generalization_level') if getattr(r, name) == 'unspecified']
    if missing:
        report.add(level, 'research_labels_unspecified', 'research',
                   f'Unspecified research labels: {missing}. They are recorded as "unspecified" and never inferred.')
    if r.generalization_level == 'unseen_circuit_class' and config.circuit.circuit_class != 'unspecified':
        if config.circuit.circuit_class in r.training_sources:
            report.add('error', 'class_leak', 'research.training_sources',
                       'An unseen-circuit-class test must exclude that class from source training')
    if config.run.mode in ('fine_tune', 'frozen') and r.pretrain_seed is None:
        report.add(level if for_generalization else 'info', 'pretrain_seed_unspecified', 'research.pretrain_seed',
                   'The source pretraining seed is kept separate from the target seed; it is not recorded yet')


def default_registry():
    from analog_optimizer.models.inputs import SpecSchema
    return {name: unit for name, unit, _ in SpecSchema().metrics}


def registry_for(config):
    custom = config.run.advanced.spec_registry
    if custom is None:
        if config.circuit.source == 'virtuoso':
            return None                   # a cell without a profile: its registry comes with the profile, nothing to check yet
        from .profiles import task_spec_registry
        generated = task_spec_registry(config.circuit)       # a generated profile brings the results of its circuit type
        if generated is not None:
            return {entry['metric_id']: entry['unit'] for entry in generated}
        return default_registry()
    return {entry.metric_id: entry.unit for entry in custom}


def validate(config: WorkbenchConfig, *, graph=None, provided_metrics=None,
             for_generalization=False) -> Report:
    """Full semantic validation. `graph` enables circuit-aware checks; without one they are
    reported as not performed rather than assumed to pass."""
    report = Report()
    _check_parameters(config, report, graph)
    measurement_ids = _check_measurements(config, report, provided_metrics=provided_metrics)
    _check_targets(config, report, measurement_ids, registry=registry_for(config))
    _check_run(config, report)
    _check_research(config, report, for_generalization=for_generalization)
    report.facts['circuit_checked'] = graph is not None
    if graph is None:
        report.add('unresolved', 'circuit_not_loaded', 'circuit',
                   'Instance paths, parameter names and initial values were NOT checked against a circuit')
    return report
