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

import hashlib
import importlib.util
import math
from pathlib import Path
from dataclasses import dataclass, asdict

from . import families, network_inputs, pdk_record, saved_rows, spec_descriptors, units
from .pdk import label, parameter_facts
from .profile_store import task_spec_registry
from .schema import WorkbenchConfig
from .spec_equations import parse, parse_size_formula, size_matches
from .start_grid import row_start_issue
from .task_registry import verified_spec_registry

FEATURE_PARAMETER_KINDS = ('w', 'l', 'm', 'nf', 'r', 'c', 'ind', 'dc')
BLOCKING = ('error', 'blocker')
# The units the optimizer can vary a group in (analog_optimizer.models.inputs): a PDK parameter is varied in the standard
# kind of its unit (compile._group_kind). An area, a current or a temperature has no such kind.
VARIABLE_UNITS = ('m', 'count', '1', 'ohm', 'F', 'H', 'V')


def native_count_columns(config):
    """Extra ngspice multiplicity names, shared by validation and the saved learner schema."""
    if not (config.circuit.task_id or '').startswith('ngspice:'):
        return ()
    return tuple(sorted({p.parameter_name for p in config.parameters
                         if p.parameter_name in ('mf', 'mult') and p.unit == 'count'}))


def _pdk_record(config):
    """The loaded PDK the configuration's network is built with, or None (standard list, or a PDK not loaded)."""
    name = getattr(config.run.network, 'vocabulary', 'standard') or 'standard'
    if not name.startswith('pdk:'):
        return None
    from .pdk_record import load_record  # lazy: tests patch pdk_record.load_record
    return load_record(name[4:])


def _pdk_facts(record, graph, parameter):
    """The PDK's facts about the parameter a row names, when its instance is a component of that PDK."""
    if record is None or graph is None or not parameter.instance_path:
        return None
    device = next((d for d in graph.devices if d.id == parameter.instance_path), None)
    if device is None or device.model_ref not in record['devices']:
        return None
    return parameter_facts(record, device.model_ref, parameter.parameter_name)


def _loaded_pdk_knowing(graph, parameter, loaded=None):
    """The id of a LOADED PDK that knows this row's device and parameter, for a hint under the standard list.
    `loaded`: a dict the caller keeps over one validation, so the PDKs are listed once and each record is read at most
    once for all such rows (list_pdks and more loads for every row were 18 ms a row on the 9p-mounted repo)."""
    if graph is None or not parameter.instance_path:
        return None
    device = next((d for d in graph.devices if d.id == parameter.instance_path), None)
    if device is None:
        return None
    from .pdk_record import list_pdks, load_record  # lazy: tests patch pdk_record.list_pdks and pdk_record.load_record
    loaded = {} if loaded is None else loaded
    if 'ids' not in loaded:
        loaded.update(ids=[entry['pdk_id'] for entry in list_pdks()], records={})
    records = loaded['records']
    for pdk_id in loaded['ids']:
        if pdk_id not in records:                 # read when first needed, as before: the first PDK that knows it ends the search
            records[pdk_id] = load_record(pdk_id)
        facts = parameter_facts(records[pdk_id], device.model_ref, parameter.parameter_name)
        if facts and facts.get('numeric'):
            return pdk_id
    return None


@dataclass(frozen=True)
class Issue:
    # A semantic-validation finding with its severity, stable code, configuration path and message.
    level: str
    code: str
    path: str
    message: str

    def as_dict(self):
        return asdict(self)


class Report:
    """Collect semantic issues and facts while keeping editor-only unsaved-row details separate."""
    def __init__(self):
        self.issues: list[Issue] = []
        self.facts: dict = {}
        # The rows that differ from the saved task, row by row (record 7.222): for the page's editors only, so not in as_dict.
        self.unsaved_rows: dict | None = None

    def add(self, level, code, path, message):
        self.issues.append(Issue(level, code, path, message))

    @property
    def blocks_run(self):
        """Check whether any recorded issue has a severity that blocks starting a run."""
        return any(i.level in BLOCKING for i in self.issues)

    def as_dict(self):
        """Serialize validation facts and issues with severity counts and the run-blocking decision."""
        counts = {}
        for issue in self.issues:
            counts[issue.level] = counts.get(issue.level, 0) + 1
        return dict(blocks_run=self.blocks_run, counts=counts, facts=self.facts,
                    issues=[i.as_dict() for i in self.issues])


def _integral(value):
    return value is not None and math.isclose(value, round(value), abs_tol=1e-9)


def resolve_leaders(parameters):
    """Map variable_id -> (leader_id, cumulative_ratio) or raise ValueError on a cycle/dangling link."""
    by_id = {p.variable_id: p for p in parameters}
    resolved = {}
    for parameter in parameters:
        ratio, current, seen = 1.0, parameter, [parameter.variable_id]
        while current.binding_group:
            if current.binding_group not in by_id:
                raise ValueError(f'{current.variable_id}: binding_group {current.binding_group!r} does not exist')
            step_ratio = current.ratio
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
    """Count optimized binding leaders, returning nothing when parameter bindings cannot be resolved."""
    try:
        leaders = resolve_leaders(parameters)
    except ValueError:
        return None
    by_id = {p.variable_id: p for p in parameters}
    return len({leader for leader, _ in leaders.values() if by_id[leader].optimized})


# ------------------------------------------------------------------------------ sections
def _check_pdk_parameter(report, path, parameter, facts, record):
    """A row that varies a parameter of a PDK component, under that PDK's component list."""
    where = f"{parameter.parameter_name} of {parameter.instance_path} (PDK {record['pdk_id']})"
    if not facts.get('numeric'):
        report.add('blocker', 'pdk_parameter_not_numeric', path + '.parameter_name',
                   f"{where} is a {facts.get('type') or 'non-numeric'} setting in the PDK's description, not a number: it "
                   'cannot be varied.')
        return
    stated = units.canonical_unit(parameter.unit)
    stated = 'count' if stated == '1' else stated
    declared = facts.get('unit')
    if declared and stated != declared:
        report.add('error', 'unit_mismatch', path + '.unit',
                   f"{where} is measured in {declared} ({'declared by the PDK' if facts.get('unit_declared') else facts.get('unit_basis') or 'standard parameter'}), "
                   f'not {parameter.unit!r}')
        return
    if stated not in VARIABLE_UNITS:
        report.add('blocker', 'parameter_unit_not_variable', path + '.unit',
                   f'{where} would be varied in {parameter.unit!r}. The optimizer varies lengths, counts, resistances, '
                   'capacitances, inductances and voltages only.')
        return
    if not declared:
        report.add('warning', 'pdk_unit_undeclared', path + '.unit',
                   f"The PDK does not declare the unit of {where}; it is taken as {parameter.unit!r}, as this row states. Its "
                   f"default there is {facts.get('default')!r} - check that the unit is right.")


def _check_parameters(config, report, graph, record):
    """`record`: the PDK the network is built with (_pdk_record), loaded once by validate() for every check."""
    count_columns = native_count_columns(config)
    feature_columns = FEATURE_PARAMETER_KINDS + count_columns
    parameters = config.parameters
    seen, targets, loaded = set(), {}, {}
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
        if not p.instance_path:
            report.add('error', 'missing_instance_path', path + '.instance_path',
                       'The row needs the instance path read from the circuit')
        key = (p.instance_path, p.parameter_name)
        if key in targets:
            report.add('error', 'conflicting_targets', path,
                       f'{p.variable_id} and {targets[key]} both write {p.instance_path}.{p.parameter_name}')
        targets[key] = p.variable_id
        if p.parameter_name == 'dc' and units.canonical_unit(p.unit) == 'A':
            report.add('blocker', 'current_group_not_supported_by_sac', path + '.unit',
                       'The SAC encoder cannot represent current-source values in amperes yet. '
                       'Remove this parameter row to keep the circuit\'s current fixed. '
                       'Marking this row fixed still leaves an unsupported group in the encoder input.')
        facts = _pdk_facts(record, graph, p)
        if facts is not None:                       # a component of the PDK the network is built with
            _check_pdk_parameter(report, path, p, facts, record)
        else:
            expected = ('count' if p.parameter_name in count_columns else
                        units.PARAMETER_KIND_UNITS.get(p.parameter_name))
            if expected and units.canonical_unit(p.unit) != expected:
                report.add('error', 'unit_mismatch', path + '.unit',
                           f'Parameter {p.parameter_name!r} is measured in {expected}, not {p.unit!r}')
            if p.parameter_name not in feature_columns:
                knowing = _loaded_pdk_knowing(graph, p, loaded) if record is None else None
                report.add('blocker', 'parameter_kind_unsupported', path + '.parameter_name',
                           f'{p.parameter_name!r} is not in the optimizer feature vocabulary '
                           f'{feature_columns}; the graph encoder cannot represent it'
                           + (f'. The loaded PDK {knowing} knows it: choose the component list "PDK {knowing}" under '
                              'Components in the RL model window to vary it.' if knowing else ''))
        if p.binding_group == p.variable_id:
            report.add('error', 'self_binding', path + '.binding_group', 'A variable cannot be bound to itself')
        _check_row_bounds(report, path, p)
    _check_bindings(report, parameters, count_columns)
    report.facts['independent_action_variables'] = independent_action_count(parameters)
    report.facts['parameter_rows'] = len(parameters)
    if not any(p.optimized for p in parameters):
        report.add('error', 'nothing_to_optimize', 'parameters', 'At least one optimized variable is required')
    if graph is not None:
        _check_parameters_against_circuit(config, report, graph, record)


def _check_row_bounds(report, path, parameter):
    """One parameter row's bounds, step, scale, initial value and integer constraint (an optimized independent row)."""
    leader_like = not parameter.binding_group
    lower, upper, step = parameter.lower, parameter.upper, parameter.step
    if parameter.optimized and leader_like:
        if lower is None or upper is None:
            report.add('error', 'missing_bounds', path, 'An optimized independent variable needs both bounds')
        elif not lower < upper:
            report.add('error', 'invalid_bounds', path, f'lower ({lower}) must be below upper ({upper})')
        else:
            if parameter.scale == 'log' and lower <= 0:
                report.add('error', 'log_scale_nonpositive', path + '.scale', 'log scale needs lower > 0')
            if step is not None and step > upper - lower:
                report.add('error', 'step_exceeds_range', path + '.step', 'step is larger than the range')
            if parameter.initial_value is not None:
                if not lower <= parameter.initial_value <= upper:
                    report.add('error', 'initial_out_of_bounds', path + '.initial_value',
                               f'{parameter.initial_value} is outside [{lower}, {upper}]')
                elif step and not _integral((parameter.initial_value - lower) / step):
                    report.add('error', 'initial_off_grid', path + '.initial_value',
                               'Initial value is not on lower + k*step; the optimizer requires a legal start')
    if parameter.value_type == 'integer':
        for name, value in (('lower', lower), ('upper', upper), ('initial_value', parameter.initial_value),
                            ('step', step)):
            if value is not None and not _integral(value):
                report.add('error', 'integer_constraint', f'{path}.{name}', f'{name} must be an integer')


def _check_bindings(report, parameters, count_columns):
    """The bindings between parameter rows: a resolvable binding graph, and each follower's unit, parameter kind,
    bounds and initial value against its leader times its ratio."""
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
            same_native_count = (p.unit == leader.unit == 'count' and
                                 p.parameter_name in ('m', *count_columns) and
                                 leader.parameter_name in ('m', *count_columns))
            if p.parameter_name != leader.parameter_name and not same_native_count:
                report.add('blocker', 'mixed_parameter_kind_group', path,
                           'The optimizer groups members of one parameter kind; binding different parameter '
                           'names in one group is not supported')
            if (leader.lower is not None and leader.upper is not None and units.known(p.unit)
                    and units.compatible(p.unit, leader.unit)):
                low = units.to_canonical(leader.lower, leader.unit) * ratio
                high = units.to_canonical(leader.upper, leader.unit) * ratio
                if p.lower is not None and low < units.to_canonical(p.lower, p.unit) * (1 - 1e-12):
                    report.add('error', 'binding_violates_member_bound', path + '.lower',
                               f'leader range x ratio reaches {_in(low, p.unit)}, below this member lower bound')
                if p.upper is not None and high > units.to_canonical(p.upper, p.unit) * (1 + 1e-12):
                    report.add('error', 'binding_violates_member_bound', path + '.upper',
                               f'leader range x ratio reaches {_in(high, p.unit)}, above this member upper bound')
            if (p.initial_value is not None and leader.initial_value is not None and units.known(p.unit)
                    and units.compatible(p.unit, leader.unit)):
                expected = units.to_canonical(leader.initial_value, leader.unit) * ratio
                actual = units.to_canonical(p.initial_value, p.unit)
                if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-18):
                    report.add('error', 'binding_initial_mismatch', path + '.initial_value',
                               f'Initial value {_in(actual, p.unit)} is not ratio x leader '
                               f'({_in(expected, p.unit)}); the optimizer '
                               'requires current values to satisfy declared bindings')


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
                       f'In the circuit {p.instance_path}.{p.parameter_name} = {_in(own, p.unit)}, but ratio x leader '
                       f'({leader_id}) = {_in(lead * ratio, p.unit)}. Change the ratio, or modify the circuit first.')


def _check_parameters_against_circuit(config, report, graph, record):
    _check_bindings_against_circuit(config, report, graph)
    devices = {d.id: d for d in graph.devices}
    for i, p in enumerate(config.parameters):
        if not p.instance_path:
            continue
        path = f'parameters[{i}]'
        device = devices.get(p.instance_path)
        if device is None:
            report.add('error', 'unknown_instance', path + '.instance_path',
                       f'{p.instance_path!r} is not an instance of the loaded circuit')
            continue
        if device.kind == 'unknown' and not (record is not None and device.model_ref in record['devices']):
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
                           f'Configuration says {_in(actual, p.unit)} but the circuit has '
                           f'{_in(value.value, p.unit)}')
        if value is not None and value.valid and p.optimized and not p.binding_group:
            # The circuit's own value must be one the optimizer starts from: a size on an upper bound its grid ends one
            # step under was refused by every run of the task, in the optimizer's words (start_grid).
            words = row_start_issue(p, value.value)
            if words:
                report.add('error', 'start_off_grid', path, words)


def _check_size_measurement(config, report, m, path, provided_metrics):
    """Check a size probe name and formula against the parameters the task varies."""
    if not m.source_name:
        report.add('error', 'missing_source_name', path + '.source_name',
                   'A probe that measures the sizes needs a name for its value (source name)')
    elif provided_metrics is not None and m.source_name in provided_metrics:
        report.add('error', 'size_probe_name_is_a_result', path + '.source_name',
                   f'{m.source_name!r} is the name of a result the simulation returns: give the size probe its own name')
    patterns, why = parse_size_formula(m.signal)
    if why is not None:
        report.add('error', 'size_formula_rejected', path + '.signal', f'{m.measurement_id}: the size formula - {why}')
    else:
        varied = [p.instance_path for p in config.parameters if p.parameter_name == 'w' and p.optimized]
        for pattern in patterns:
            if not any(size_matches(pattern, instance) for instance in varied):
                report.add('error', 'size_pattern_matches_nothing', path + '.signal',
                           f'{m.measurement_id}: no width the task varies is on an instance named {pattern!r} '
                           '(a size formula sees only the widths in the Parameters rows)')


def _check_measurements(config, report, *, provided_metrics):
    ids = {}
    for i, m in enumerate(config.measurements):
        path = f'measurements[{i}]'
        if m.measurement_id in ids:
            report.add('error', 'duplicate_measurement_id', path, f'Duplicate measurement_id {m.measurement_id!r}')
        ids[m.measurement_id] = m
        if not units.known(m.unit):
            report.add('error', 'unknown_unit', path + '.unit', f'Unknown unit {m.unit!r}')
        if m.result_source == 'backend_profile':
            if not m.source_name:
                report.add('error', 'missing_source_name', path + '.source_name',
                           'backend_profile needs the metric name produced by the circuit profile')
            elif provided_metrics is not None and m.source_name not in provided_metrics:
                report.add('error', 'metric_not_provided', path + '.source_name',
                           f'The selected task backend does not produce {m.source_name!r}; it provides '
                           f'{sorted(provided_metrics)}')
        elif m.result_source == 'ade_output':
            if not m.source_name:
                report.add('error', 'missing_source_name', path + '.source_name', 'ade_output needs the output name')
            elif provided_metrics is None or m.source_name not in provided_metrics:
                # A saved task measured by Maestro provides its outputs (OCEAN on every run, task flow part 5); anything
                # else cannot measure a Maestro output.
                report.add('blocker', 'ade_outputs_not_wired', path + '.result_source',
                           f'The Maestro output {m.source_name!r} is measured only by a task saved with it: this circuit '
                           'does not measure it.')
        elif m.result_source == 'size_estimate':                   # worked out from the sizes, never simulated (record 7.308)
            _check_size_measurement(config, report, m, path, provided_metrics)
    return ids


def _expression_symbols(expression):
    # Read off the formula, not by trial evaluation: (m_a - m_b) / (m_c - m_d) with every symbol at 1.0 divided by
    # zero and was rejected as unsupported.
    return parse(expression)


def check_equation(t, path, report, measurement_ids):
    """A spec judges the value of its equation over the probes (spec_equations). Returns the probe when the equation
    is exactly one Probe ID - the simplest equation, whose unit can be checked."""
    equation = t.equation.strip()
    probe = measurement_ids.get(equation)
    if probe is not None:
        if units.known(t.unit) and units.known(probe.unit) and not units.compatible(t.unit, probe.unit):
            report.add('error', 'target_unit_mismatch', path + '.unit',
                       f'Spec unit {t.unit} is incompatible with the unit {probe.unit} of the Probe {equation}')
        return probe
    names, problem = parse(equation)
    if names is None:
        report.add('error', 'equation_rejected', path + '.equation',
                   f'The equation cannot be used: {problem}. Allowed: Probe IDs, numbers, + - * / ** and parentheses.')
    elif not names:
        report.add('error', 'equation_without_probe', path + '.equation',
                   'The equation uses no Probe: a spec must judge something the simulation measures.')
    elif [n for n in names if n not in measurement_ids]:
        unknown = [n for n in names if n not in measurement_ids]
        dotted = [m for m in measurement_ids if '.' in m or '-' in m]
        report.add('error', 'equation_unknown_probe', path + '.equation',
                   f'No Probe called {", ".join(unknown)}. Probes: {", ".join(measurement_ids) or "none yet"}.'
                   + (f' A Probe ID with "." or "-" ({", ".join(dotted)}) can only be a whole equation on its own.' if dotted else ''))
    elif units.known(t.unit) and not units.is_affine(t.unit):
        report.add('warning', 'equation_unit_unchecked', path + '.unit',
                   f'The unit of a formula is not checked: {t.unit} must be what {equation} gives with every probe in its '
                   'canonical unit (W, Hz, V, A, s...; W / Hz gives J).')
    return None


def _check_targets(config, report, measurement_ids, *, registry, extensible=True, provided_metrics=None):
    seen, preference, active_hard = set(), [], 0
    for i, t in enumerate(config.targets):
        path = f'targets[{i}]'
        if t.metric_id in seen:
            report.add('error', 'duplicate_metric_id', path, f'Duplicate metric_id {t.metric_id!r}')
        seen.add(t.metric_id)
        if not units.known(t.unit):
            report.add('error', 'unknown_unit', path + '.unit', f'Unknown unit {t.unit!r}')
        probe = check_equation(t, path, report, measurement_ids)
        equation = t.equation.strip()
        # A spec's name is where its value lives - in the simulation result, the network's registry and the tables -
        # so it may only be the name of a probe or of a simulator result when the spec IS that probe / that result.
        if t.metric_id in measurement_ids and equation != t.metric_id:
            report.add('error', 'spec_name_is_a_probe', path + '.metric_id',
                       f'{t.metric_id!r} is the ID of a Probe, but this spec computes {equation!r}. Give the spec its own name.')
        result_backed = probe is not None and probe.result_source in ('backend_profile', 'ade_output', 'size_estimate') and probe.source_name == t.metric_id
        if provided_metrics is not None and t.metric_id in provided_metrics and not result_backed:
            report.add('error', 'spec_name_is_a_result', path + '.metric_id',
                       f'{t.metric_id!r} is the name of a result the simulation returns, but this spec computes {equation!r}. '
                       f'Give the spec its own name, or make its equation the Probe that reads {t.metric_id}.')
        _check_limits(report, path, t)
        if t.direction_after_feasible != 'none' and t.active:
            preference.append(t.metric_id)
            needed = 'upper' if t.direction_after_feasible == 'minimize' else 'lower'
            if getattr(t, needed) is None:
                report.add('error', 'objective_without_limit', path + f'.{needed}',
                           f'{t.metric_id}: a {t.direction_after_feasible} objective needs its {needed} limit - the objective '
                           'bonus measures how far inside that limit the design is')
        if t.active and t.hard:
            active_hard += 1
        if units.known(t.unit) and units.is_affine(t.unit):
            report.add('error', 'affine_unit', path + '.unit', 'Offset units are not supported for targets')
        _check_registry_entry(report, path, t, registry, extensible)
        if not t.basis.strip():
            report.add('info', 'basis_not_stated', path + '.basis', 'The source of this requirement is not recorded')
    if len(preference) > 1:
        report.add('error', 'multiple_preferences', 'targets',
                   f'Only one target may set direction_after_feasible; found {preference}')
    if active_hard == 0:
        report.add('error', 'no_hard_constraint', 'targets',
                   'At least one active hard constraint is required to define feasibility')
    _warn_unused_probes(config, report, measurement_ids)


# A from-scratch soft actor-critic run below this many evaluations is told that it has hardly had time to learn. Record
# 7.183's values started to learn after 250 to 600 evaluations on three circuits; the starting presets (record 7.199)
# after about 150 to 300 on ngspice and Spectre (record 7.210). So 300 stays: about where the slowest of them had begun.
SAC_LEARNS_AFTER = 300


def _check_run(config, report, record):
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
    if net.encoder_type != 'rgcn' and net.hidden_dim % net.heads:
        report.add('error', 'heads_divisibility', 'run.network', 'hidden_dim must be divisible by heads')
    if run.mode != 'frozen' and run.max_evaluations < adv.batch_size + 1:
        report.add('warning', 'budget_below_batch', 'run.max_evaluations',
                   'The budget cannot fill one batch; no learner update will occur')
    if run.mode != 'frozen' and run.max_evaluations <= adv.warmup_transitions:
        report.add('warning', 'budget_within_warmup', 'run.advanced.warmup_transitions',
                   'The whole budget is random warm-up exploration; the policy never chooses an action. Published '
                   'settings assume thousands of simulations: lower the warm-up or raise the budget')
    _warn_learning_values(report, run, adv)
    _check_vocabulary(report, run, record)
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
    _warn_output_settings(report, config.output)


def _check_limits(report, path, target):
    """One spec's limits: those its constraint needs and only those, an interval in order, and a Scale where a limit of
    0 would leave a miss without a size."""
    given = dict(lower=target.lower is not None, upper=target.upper is not None)
    need = {'>=': ('lower',), '<=': ('upper',), 'interval': ('lower', 'upper')}[target.constraint]
    for name in need:
        if not given[name]:
            report.add('error', 'missing_threshold', f'{path}.{name}', f'constraint {target.constraint} needs {name}')
    for name, present in given.items():
        if present and name not in need:
            report.add('error', 'unexpected_threshold', f'{path}.{name}',
                       f'{name} is not used by constraint {target.constraint}; remove it to avoid ambiguity')
    if target.constraint == 'interval' and given['lower'] and given['upper'] and target.lower > target.upper:
        report.add('error', 'invalid_interval', path, 'lower must not exceed upper')
    # An empty scale measures a miss against the size of the limit. A limit of 0 has no size, and the miss was
    # silently counted against 1 of the row's unit - 1 V, 1 Hz or 1 A, whatever the circuit (plan of 2026-10-05, S3).
    limits = [getattr(target, name) for name in need if given[name]]
    if target.active and target.normalization_scale is None and limits and not any(limits):
        report.add('blocker', 'scale_needed_for_zero_limit', path + '.normalization_scale',
                   f'{target.metric_id}: the limit is 0, so a miss cannot be measured as a fraction of the limit (it would be '
                   f'counted against 1 {target.unit}). Type a Scale for this row (Specs, More columns): the distance outside '
                   'the limit that should cost half of the row\'s penalty.')


def _check_registry_entry(report, path, target, registry, extensible):
    """One spec against the result registry the network reads: new to it (added by this run, or refused), or in it with
    the same unit."""
    if registry is not None and units.known(target.unit) and not units.is_affine(target.unit):
        entry = registry.get(target.metric_id)
        if entry is None and extensible:
            report.add('info', 'spec_adds_registry_entry', path + '.metric_id',
                       f'{target.metric_id!r} is new to the result registry the network reads, so this run adds it there. '
                       'Saved models made without this spec cannot be loaded into such a run, nor its models into one '
                       'without it.')
        elif entry is None:
            report.add('blocker', 'metric_not_in_registry', path + '.metric_id',
                       f'{target.metric_id!r} is not in the RL specification registry {sorted(registry)}. Add it '
                       'under Run > Advanced > spec_registry (this changes checkpoint compatibility).')
        elif units.canonical_unit(target.unit) != units.canonical_unit(entry) if units.known(entry) else True:
            report.add('error', 'registry_unit_mismatch', path + '.unit',
                       f'Registry expects {entry!r} for {target.metric_id}')


def _warn_unused_probes(config, report, measurement_ids):
    """A warning for each Probes row that no spec equation uses."""
    used = set()
    for t in config.targets:
        equation = t.equation.strip()
        used |= {equation} if equation in measurement_ids else set(_expression_symbols(equation)[0] or ())
    for i, m in enumerate(config.measurements):
        if m.measurement_id not in used:
            report.add('warning', 'unused_measurement', f'measurements[{i}]', 'No spec equation uses this probe')

def _warn_learning_values(report, run, adv):
    """Warnings for a run that would train with values that learned late or not at all in the tests of 2026-10-05."""
    # Measured on 2026-10-05 (record 7.183, artifacts/local/reviews/defaults-study-2026-10-05): the values a configuration
    # without an Advanced block still gets - starting temperature 0.2, one update per evaluation - leave soft actor-critic
    # a uniform random search under every reward setting. The schema defaults stay (old configurations and checkpoints
    # keep their meaning); a run that would train with such values is told.
    trains = run.mode in ('scratch', 'fine_tune')
    slow = []
    if adv.updates_per_transition < 4:
        slow.append(f'{adv.updates_per_transition} update{"" if adv.updates_per_transition == 1 else "s"} per evaluation')
    if adv.initial_alpha > 0.05:
        slow.append(f'a starting temperature of {adv.initial_alpha:g}')
    if trains and slow:
        report.add('warning', 'sac_values_random_search', 'run.advanced',
                   f'With {" and ".join(slow)}, soft actor-critic learned late or not at all in GATOR\'s tests of 2026-10-05: '
                   'with 1 update per evaluation the designs stayed a uniform random search for 1,500 evaluations, and a '
                   'starting temperature of 0.2 delayed learning to about evaluation 1,000. The tested values are 8 updates '
                   'per evaluation, starting temperature 0.01 and discount 0, under Advanced in the RL model window.')
    if run.mode == 'scratch' and run.max_evaluations < SAC_LEARNS_AFTER:
        report.add('warning', 'budget_below_sac_learning', 'run.max_evaluations',
                   f'Soft actor-critic from scratch started to pass designs after about 150 to 300 evaluations with the '
                   f'starting presets in GATOR\'s tests of 2026-10-05 (after 250 to 600 with the values tested before them). '
                   f'With {run.max_evaluations} evaluations this run has little or no time to learn: raise the budget to '
                   'several hundred.')


def _check_vocabulary(report, run, record):
    """The component list the network is built with: a PDK's needs that PDK loaded."""
    vocabulary = getattr(run.network, 'vocabulary', 'standard') or 'standard'
    if vocabulary.startswith('pdk:'):             # `record` is _pdk_record's load of <name>; the family list: _check_network_inputs
        if record is None:
            report.add('blocker', 'pdk_not_loaded', 'run.network.vocabulary',
                       f'The network is to know the components of PDK {vocabulary[4:]}, but that PDK is not loaded. Read it '
                       'in the Virtuoso window (reading a cell reads its PDK; "PDK window..." reads one by name), or choose '
                       'the standard list.')
        else:
            report.add('info', 'pdk_vocabulary', 'run.network.vocabulary',
                       f"The network is built with the component list of {label(record['vocabulary'])}. A model trained "
                       'with it loads only with this list, and models trained with the standard list do not load with it.')


def _check_second_build(config, report, graph, settings):
    """The second build of the network inputs (record 7.317), said per task: which source the rule takes as the supply,
    what each tagged net is, and what a run with the operating-point ratios reads."""
    bench, rule = settings['bench_features'] == 'relative', settings['net_roles'] == 'rule'
    if (bench or rule) and graph is not None:
        found = network_inputs.bench_of_graph(graph, network_inputs.bench_variables(config))
        supply = (f'{found.supply_source} on {found.supply_net}, {units.text(found.supply_v, "V")}'
                  if found.supply_source else None)
        if bench:
            currents = sum(1 for s in found.sources if s.kind == 'isource')
            unread = sorted(s.id for s in found.sources if s.dc is None and not s.signal)
            report.add('info', 'bench_features_relative', 'run.network.bench_features',
                       f'Bench sources on their own scales: {len(found.sources)} at the top level, {currents} of them current '
                       'sources read in microamperes; ' + (f'voltages are also given as a share of the supply ({supply}).'
                                                           if supply else 'no supply was found.'))
            if supply is None:
                report.add('warning', 'bench_supply_unknown', 'run.network.bench_features',
                           'No supply was found: the circuit has no voltage source at the top level with one pin on ground and '
                           'a DC value. Voltages are then given in volts only, not as a share of the supply.')
            if unread:
                report.add('warning', 'bench_value_unread', 'run.network.bench_features',
                           f"The DC value of {', '.join(unread)} is not a number in the netlist and not a variable of the "
                           'test with one value: the network sees it as missing.')
        if rule:
            roles = network_inputs.ruled_roles(graph, found, spec_descriptors.measured_nets(config))
            said = '; '.join(f"{net}: {' and '.join(tags)}" for net, tags in sorted(roles.items()))
            report.add('info', 'net_roles_by_rule', 'run.network.net_roles',
                       'Net tags by rule (every other net is a plain one): ' + (said or 'none found') + '.')
            if not any('output' in tags for tags in roles.values()):
                report.add('warning', 'net_roles_no_output', 'run.network.net_roles',
                           "No net is tagged as an output: no active spec's probe reads a node voltage this workbench can "
                           'follow (a built-in analyzer, an ngspice measure, or a current or loop-gain probe only).')
    if settings['operating_point_ratios']:
        report.add('info', 'operating_point_ratios', 'run.network.operating_point_ratios',
                   "Operating-point ratios: each design's operating point is read after its simulation, and every transistor "
                   'gets gm/Id, gm/gds, |Vgs| - |Vth| and |Vds|/|Vdsat| with its region. A design whose operating point is not '
                   'there (a failed simulation, a simulator that gives none) shows them as missing.')


def _check_network_inputs(config, report, graph):
    """The transferable inputs of record 7.298: what the network reads of each spec (on its Specs row), and whether the
    task's PDK gives every MOS model of the circuit the numbers the size and device-model inputs need (names and counts
    only - the numbers are never shown)."""
    network = config.run.network
    settings = network_inputs.transfer_settings(network)
    if (network.encoder_type == 'circuit_gps') != (settings['spec_input'] == 'structured'):
        report.add('blocker', 'encoder_spec_input_mismatch', 'run.network.spec_input',
                   'CircuitGPS needs Structured network inputs. Other encoders use Standard, Transferable or Transferable 2.')
    _check_structured_specs(settings, config, report)
    _describe_spec_inputs(settings, config, report)
    _check_pdk_network_numbers(settings, config, report, graph)
    _check_second_build(config, report, graph, settings)
    _check_component_vocabulary(network, config, report, graph)
    _check_search_input_policy(config, report, network)


def _check_structured_specs(settings, config, report):
    """Describe structured measurement programs and report how many operations retain unknown semantics."""
    if settings['spec_input'] == 'structured':
        # lazy: only structured spec validation needs the measurement-program compiler.
        from .spec_programs import describe_programs
        programs = describe_programs(config)
        def unknown_count(node):
            return int(node['op'] == 'unknown') + sum(unknown_count(c) for c in node.get('children', ()))
        for i, target in enumerate(config.targets):
            if target.active:
                unknown = unknown_count(programs[target.metric_id])
                report.add('info', 'spec_measurement_program', f'targets[{i}]',
                           'CircuitGPS preserves the measurement program, its circuit bindings and reward scale. '
                           + (f'{unknown} part(s) have unknown semantics (including opaque analyzer results); '
                              'they keep explicit unknown tokens.' if unknown else 'Every operation is recognized.'))


def _describe_spec_inputs(settings, config, report):
    """Describe each active specification as the set-based network inputs will represent it."""
    if settings['spec_input'] in ('set', 'structured'):
        described = spec_descriptors.describe_specs(config)
        report.add('info', 'spec_input_set', 'targets',
                   'The network reads these specs as a set: any names and any number of them, each described by what it '
                   'measures (its row says how) and by how far it is from its limits. A model trained so loads on any task '
                   'with the same network inputs.')
        for i, target in enumerate(config.targets):
            if target.active:
                report.add('info', 'spec_input_set_item', f'targets[{i}]',
                           f'The network reads {target.metric_id} as: '
                           + spec_descriptors.words(described[target.metric_id], units.canonical_unit(target.unit)
                                                    if units.known(target.unit) else target.unit))


def _check_pdk_network_numbers(settings, config, report, graph):
    """Validate the PDK size and device-model numbers required by the selected network inputs."""
    relative, numbers = settings['size_features'] == 'pdk_relative', settings['device_model_features']
    if relative or numbers:
        path = 'run.network.size_features' if relative else 'run.network.device_model_features'
        try:
            document = network_inputs.numbers_for(config, required=True)
        except network_inputs.InputsUnavailable as exc:
            report.add('blocker', 'pdk_numbers_unavailable', path, str(exc))
            document = None
        if document is not None and graph is not None:
            found = network_inputs.coverage(graph, document)
            if relative and found['missing_sizes']:
                report.add('blocker', 'pdk_sizes_missing', 'run.network.size_features',
                           f"Sizes relative to the PDK need each MOS model's minimum size, which PDK {document['pdk_id']} does "
                           f"not give for {', '.join(found['missing_sizes'])}. Choose absolute sizes, or load the PDK again.")
            if numbers and found['missing_numbers']:
                level = 'blocker' if len(found['missing_numbers']) == len(found['models']) else 'warning'
                report.add(level, 'device_numbers_missing', 'parameters' if level == 'warning' else 'run.network.device_model_features',
                           f"Device model features: the nominal model section of PDK {document['pdk_id']} does not give all "
                           f"four technology numbers of {', '.join(found['missing_numbers'])}"
                           + ('; the network sees those inputs as missing on these devices.' if level == 'warning' else
                              '; none of this circuit\'s MOS models has them. Switch the device model features off.'))


def _check_component_vocabulary(network, config, report, graph):
    """Warn about legacy component lists and explain devices whose family classification is unavailable."""
    vocabulary = getattr(network, 'vocabulary', 'standard') or 'standard'
    if vocabulary == 'standard' and config.run.mode == 'scratch':
        report.add('warning', 'standard_list_new_model', 'run.network.vocabulary',
                   'A new model is built with the device-family list (RL model window, Components): the standard list is kept '
                   'to continue the models trained with it. This configuration still asks for it.')
    if vocabulary == families.NAME and graph is not None:
        pdk_id = getattr(config.circuit, 'pdk_id', None)
        unknown = families.coverage(graph, families.FamilyList(families.block_for(pdk_id)))['unknown']
        if unknown:
            loaded = bool(pdk_id) and pdk_record.load_record(pdk_id) is not None
            report.add('info', 'family_list_unknown_parts', 'parameters',
                       f"Device families: {', '.join(sorted(set(unknown)))} read as unknown parts - "
                       + (f'PDK {pdk_id} is not loaded; loading it (PDK window) gives its bipolars, diodes and varactors their '
                          'families.' if not loaded else 'the rules of the family list could not classify them (their model '
                          'facts are in the PDK window).'))


def _check_search_input_policy(config, report, network):
    """Report optimizer, archive-comparison and rehearsal restrictions and any added operating-point analysis."""
    if config.run.optimizer == 'bayes':                       # record 7.304
        if config.run.mode != 'scratch':
            report.add('blocker', 'bayes_needs_scratch', 'run.mode',
                       'Bayesian optimization (run.optimizer "bayes") proposes the designs itself: it starts from scratch '
                       'and loads no saved model. Choose New model, or the SAC optimizer.')
        else:
            report.add('info', 'bayes_run', 'run.optimizer',
                       'This run is searched by Bayesian optimization, not by the network: the same task, reward, lanes and '
                       'budget, the same random warm-up designs for the same seed. The network is neither asked nor trained, '
                       'so the run saves no model worth loading, and it cannot be resumed.')
    _comparison_rules(config, report)
    if network_inputs.any_transfer(network) and config.run.rehearsal is not None:
        report.add('blocker', 'rehearsal_with_transfer_inputs', 'run.rehearsal',
                   'Rehearsal mixes in recorded transitions of other tasks, and those would need the view of their own task '
                   '(their spec descriptions, their PDK): not built yet for the transferable network inputs. Switch '
                   'rehearsal off, or use the standard inputs.')
    if network_inputs.reads_operating_points(network) and network_inputs.maestro_dc_operating_point(config) == 'added':
        report.add('info', 'dc_operating_point_added', 'parameters',
                   "Operating-point inputs: this task's Maestro test does not save the DC operating point, so this run adds it "
                   'to the deck - one short DC solve more per evaluation; every other analysis and output stays as the test '
                   'has it.')


def _comparison_rules(config, report):
    """The archive comparison's runs (docs/plan-bo-mobo-rl-archive-comparison.md, run.comparison): every method evaluates
    its start design, then the common first designs, then its own proposals - nothing random in between."""
    run, comparison = config.run, config.run.comparison
    for name in ('initial_designs', 'archive'):          # pinned files: present and the very bytes the run pins
        path = None if comparison is None else getattr(comparison, name)
        if path is None:
            continue
        try:
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError as exc:
            report.add('blocker', 'comparison_file_missing', f'run.comparison.{name}', f'{path} cannot be read: {exc}')
            continue
        if digest != getattr(comparison, f'{name}_sha256'):
            report.add('blocker', 'comparison_file_not_pinned', f'run.comparison.{name}',
                       f'{path} is not the file this run pins: its sha256 is {digest[:12]}..., the configuration names '
                       f'{getattr(comparison, f"{name}_sha256")[:12]}...')
    if run.optimizer in ('turbo_archive', 'mobo'):
        if run.mode not in ('scratch', 'resume'):
            report.add('blocker', 'comparison_search_needs_scratch', 'run.mode',
                       f'run.optimizer "{run.optimizer}" (the archive comparison) proposes the designs itself and loads no '
                       'saved model: its mode is scratch. A stopped run goes on from its own save point (Continue).')
        if not config.output.save_checkpoints:
            report.add('warning', 'comparison_search_not_resumable', 'output.save_checkpoints',
                       'Without save points this search cannot be continued after a pause, a stop or a crash.')
        if run.optimizer == 'mobo':
            if importlib.util.find_spec('botorch') is None:
                report.add('blocker', 'mobo_needs_botorch', 'run.optimizer',
                           'M+ (run.optimizer "mobo") needs BoTorch, which only the comparison\'s own environment has '
                           '(~/gator/envs/archive-compare-venv); this Python has none.')
        report.add('info', 'comparison_search_run', 'run.optimizer',
                   f'This run is searched by {run.optimizer} (the archive comparison): the network is neither asked nor '
                   'trained, and the run saves its search with its save points, so it can be continued.')
    elif comparison is not None:
        if run.optimizer == 'bayes':
            report.add('blocker', 'comparison_not_for_bayes', 'run.comparison',
                       'Production Bayesian optimization keeps its own random warm-up: the comparison\'s first designs '
                       'are for the comparison\'s searches (turbo_archive, mobo) and SAC runs.')
        elif comparison.initial_designs is not None and run.advanced.warmup_transitions:
            report.add('blocker', 'comparison_designs_replace_warmup', 'run.advanced.warmup_transitions',
                       'In the archive comparison the common first designs replace the random warm-up: after them comes '
                       'the method itself. Set warmup_transitions to 0.')


def _warn_output_settings(report, out):
    """What the output settings make impossible later (a full resume, a transfer source, a complete history), and a
    save-point interval given twice."""
    if not out.save_replay_snapshots:
        report.add('warning', 'no_full_resume', 'output.save_replay_snapshots',
                   'Replay snapshots are off: checkpoints will be weights_only and a FULL training-state resume '
                   'of this run will not be possible.')
    if not out.save_checkpoints:
        report.add('warning', 'no_checkpoints', 'output.save_checkpoints',
                   'Checkpoints are off: the run can be neither resumed nor used as a transfer source.')
    if out.checkpoint_every_evaluations is not None and out.checkpoint_every_seconds is not None:
        # One interval, counted in evaluations OR in seconds (user request 2026-09-22). The engine would save at whichever
        # comes first; the Output settings panel keeps one and empties the other, so both come only from a file or an old copy.
        report.add('error', 'checkpoint_interval_both', 'output.checkpoint_every_seconds',
                   f'Choose one checkpoint interval: every {out.checkpoint_every_evaluations} evaluations OR every '
                   f'{out.checkpoint_every_seconds:g} seconds, not both. In Output settings, type one number and choose '
                   'its unit; the other one is emptied.')
    if not out.save_transition_archive:
        report.add('warning', 'no_transition_archive', 'output.save_transition_archive',
                   'The complete experience archive is off. A replay snapshot is NOT a complete history once the '
                   'circular buffer evicts samples.')

def _check_research(config, report, *, for_generalization=False):
    r = config.research
    level = 'error' if for_generalization else 'info'
    missing = [name for name in ('comparison_pair_id', 'method_label')
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
    """Return the optimizer's default metric-to-unit registry."""
    from analog_optimizer.models.inputs import SpecSchema
    return {name: unit for name, unit, _ in SpecSchema().metrics}


def registry_for(config):
    """Select the configuration's custom, task-specific or default metric registry."""
    custom = config.run.advanced.spec_registry
    if custom is None:
        if config.circuit.source == 'virtuoso':
            return None                   # a cell without a profile: its registry comes with the profile, nothing to check yet
        generated = task_spec_registry(config.circuit)       # a generated profile brings the results of its circuit type
        if generated is not None:
            return {entry['metric_id']: entry['unit'] for entry in generated}
        of_record = verified_spec_registry(config.circuit)   # the verified LDO and VCO: the registry of their real experiment
        if of_record is not None:
            return {entry['metric_id']: entry['unit'] for entry in of_record[1]}
        return default_registry()
    return {entry.metric_id: entry.unit for entry in custom}


def validate(config: WorkbenchConfig, *, graph=None, provided_metrics=None,
             for_generalization=False, rows_from=None) -> Report:
    """Full semantic validation. `graph` enables circuit-aware checks; without one they are
    reported as not performed rather than assumed to pass."""
    report = Report()
    record = _pdk_record(config)                  # one read of the PDK record for every check below (it was four)
    _check_parameters(config, report, graph, record)
    measurement_ids = _check_measurements(config, report, provided_metrics=provided_metrics)
    registry = None if config.run.network.spec_input != 'slots' else registry_for(config)      # sets/programs have none
    _check_targets(config, report, measurement_ids, registry=registry,
                   extensible=config.run.advanced.spec_registry is None, provided_metrics=provided_metrics)
    _check_run(config, report, record)
    _check_network_inputs(config, report, graph)
    _check_research(config, report, for_generalization=for_generalization)
    if record is not None and graph is not None and not any(d.model_ref in record['devices'] for d in graph.devices):
        report.add('warning', 'pdk_not_in_circuit', 'run.network.vocabulary',
                   f"No part of this circuit is a component of PDK {record['pdk_id']}: the network is built with that PDK's "
                   'list, but sees this circuit as the standard list does. Its models would only load with that list.')
    report.facts['circuit_checked'] = graph is not None
    if graph is None:
        report.add('unresolved', 'circuit_not_loaded', 'circuit',
                   'Instance paths, parameter names and initial values were NOT checked against a circuit')
    if config.circuit.source == 'registered_task':
        # lazy: tests patch task_registry.SYNTHETIC_FIXTURES
        from .task_registry import MOCK_TASK_REMOVED, REMOVED_MOCK_TASKS, REMOVED_REAL_TASKS, SYNTHETIC_FIXTURES, real_task_removed
        # Status records 7.59 and 7.128: such a configuration can never run again - unless a test registered the circuit.
        if config.circuit.task_id in REMOVED_MOCK_TASKS and config.circuit.task_id.partition(':')[2] not in SYNTHETIC_FIXTURES:
            report.add('error', 'task_removed', 'circuit.task_id', MOCK_TASK_REMOVED.format(task=config.circuit.task_id))
        if config.circuit.task_id in REMOVED_REAL_TASKS:        # records 7.73 and 7.128: the built-in verified tasks
            report.add('error', 'task_removed', 'circuit.task_id', real_task_removed(config.circuit.task_id))
    _check_saved_task(config, report, rows_from)
    return report


def _in(value, unit) -> str:
    """A number in the canonical unit of `unit`, written as the editors write quantities (record 7.208: 450 nm, 1.1 GHz); in a
    unit the registry does not know, as before."""
    return units.text(value, units.canonical_unit(unit)) if units.known(unit) else format(value, 'g')


# What a goal view of the archive comparison changes in a Specs row (archive_compare.views.view_config): nothing else.
GOAL_VIEW_FIELDS = ('lower', 'upper', 'normalization_scale', 'direction_after_feasible')


def _only_goal_view(config, saved) -> bool:
    """Whether the configuration's Specs rows are the saved task's but for the goal-view fields: the same rows, in the
    same order, every other field equal. A goal view only rescores what the saved task simulates - limits, scales and the
    preferred direction never reach the deck - so a comparison run of it is still a run of the saved task."""
    saved_rows_ = {row.get('metric_id'): row for row in saved.get('specs') or [] if isinstance(row, dict)}
    neutral = config.model_copy(deep=True)
    for row in neutral.targets:
        kept = saved_rows_.get(row.metric_id)
        if kept is None:
            return False
        for field in GOAL_VIEW_FIELDS:                # a field the saved row leaves out has its default there
            setattr(row, field, kept.get(field, type(row).model_fields[field].default))
    return 'targets' not in saved_rows.row_differences(neutral, saved)


def _check_saved_task(config, report, rows_from=None):
    """A saved task runs exactly as it was saved (task flow part 4, saved_rows.py): Parameters, Probes or Specs rows that
    differ from its task file block a start until "Save task" stores them, or "Reload saved values" takes the saved
    rows back. A resume runs the run's own saved rows, so it is not blocked. Rows older than the saved task - saving
    them would undo what was saved since - point to Reload saved values (record 7.203; `rows_from`: the revision the
    page's rows came from, when it knows). Which rows differ, row by row, goes to `report.unsaved_rows` in every run
    mode: the editors mark them (record 7.222)."""
    found = saved_rows.saved_task(config, with_entry=False)
    if found is None:
        return
    name, _, saved = found
    report.unsaved_rows = saved_rows.unsaved_rows(config, saved)
    if config.run.mode == 'resume':
        return
    differences = saved_rows.row_differences(config, saved)
    if config.run.comparison is not None and 'targets' in differences and _only_goal_view(config, saved):
        differences.pop('targets')
        report.add('info', 'comparison_goal_view', 'targets',
                   f'The Specs are the archive comparison\'s goal view of the saved task real:{name}: its limits, stated '
                   'scales and preferred direction; every other field of every row is the saved one.')
    undone = saved_rows.undone_by_saving(config, name, saved, base=rows_from) if differences else None
    older = {item['section'] for item in undone['items']} if undone else set()
    for section, lines in differences.items():
        fix = saved_rows.FIX_NEWER.format(**undone) if section in older else saved_rows.FIX_ROWS
        report.add('error', 'task_not_saved', section,
                   saved_rows.describe_rows(section, lines, name=name, revision=saved.get('revision')) + ' ' + fix)


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_check_equation = check_equation
