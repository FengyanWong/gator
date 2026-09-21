"""Translate a validated WorkbenchConfig into the optimizer's existing objects.

Nothing here re-implements optimizer behaviour. Variables become the existing
``ParameterGroup``/``ParameterBinding`` (so ``ActionMapper`` legalizes actions
exactly as before) and targets become the existing ``MetricSpec`` (so the reward
is the existing negative weighted mean capped violation). Feasibility is checked
separately, from raw values and thresholds, by ``hard_constraints``.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import math

from . import units
from .schema import WorkbenchConfig
from .validation import resolve_leaders, uniform_grid, registry_for


class CompileError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledTask:
    graph: object                      # CircuitGraph with the configured parameter groups
    specs: tuple                       # tuple[MetricSpec, ...]
    spec_schema: object                # SpecSchema used by the goal encoder
    variables: tuple                   # per independent variable: id, unit, bounds, members (canonical units)
    targets: tuple                     # canonical thresholds per active target (for independent feasibility)
    metric_sources: dict               # metric_id -> ('profile', source_name) | ('expression', text, measurement map)
    preference: dict | None            # {'metric': id, 'direction': 'min'|'max'} or None


def _canonical_bounds(parameter):
    lower, upper, step = parameter.lower, parameter.upper, parameter.step
    if parameter.value_type == 'discrete':
        grid = uniform_grid(parameter.candidates or [])
        if grid is None:
            raise CompileError(f'{parameter.variable_id}: non-uniform candidates are not executable')
        lower, upper, step = grid
    convert = lambda v: None if v is None else units.to_canonical(v, parameter.unit)
    return convert(lower), convert(upper), (None if step is None else units.scale_to_canonical(step, parameter.unit))


def build_graph(config: WorkbenchConfig, graph):
    """Return a deep copy of `graph` whose parameter_groups are the configured variables."""
    from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
    graph = deepcopy(graph)
    parameters = [p for p in config.parameters if p.target_kind == 'instance_parameter']
    if len(parameters) != len(config.parameters):
        raise CompileError('Design-variable targets cannot be executed by the current adapters')
    leaders = resolve_leaders(parameters)
    by_id = {p.variable_id: p for p in parameters}
    members = {}
    for p in parameters:
        leader_id, ratio = leaders[p.variable_id]
        members.setdefault(leader_id, []).append((p, ratio))
    groups, variables = [], []
    for leader_id, rows in members.items():
        leader = by_id[leader_id]
        lower, upper, step = _canonical_bounds(leader)
        current = graph.parameters.get(leader.instance_path, {}).get(leader.parameter_name)
        if current is None or not current.valid:
            raise CompileError(f'{leader_id}: {leader.instance_path}.{leader.parameter_name} is unresolved')
        value = current.value
        if not leader.optimized:
            # A fixed group still needs a legal, non-degenerate domain for the graph contract.
            lower = value if lower is None else lower
            upper = value if upper is None else upper
            if not lower < upper:
                span = abs(value) * 1e-9 or 1e-30
                lower, upper = value - span, value + span
                step = None
        if lower is None or upper is None:
            raise CompileError(f'{leader_id}: bounds are required')
        bindings = []
        for row, ratio in rows:
            convert = lambda v, r=row: None if v is None else units.to_canonical(v, r.unit)
            own = row is not leader
            bindings.append(ParameterBinding(row.instance_path, row.parameter_name, ratio,
                                             convert(row.lower) if own else None,
                                             convert(row.upper) if own else None))
        group = ParameterGroup(id=leader_id, parameter_kind=leader.parameter_name,
                               unit=units.canonical_unit(leader.unit), value=value, lower=lower, upper=upper,
                               members=tuple(bindings),
                               domain='integer' if leader.value_type == 'integer' else 'continuous',
                               scale=leader.scale, mutable=leader.optimized, step=step)
        groups.append(group)
        variables.append(dict(variable_id=leader_id, unit=group.unit, lower=lower, upper=upper, step=step,
                              scale=leader.scale, domain=group.domain, optimized=leader.optimized,
                              parameter_kind=leader.parameter_name,
                              members=[dict(variable_id=row.variable_id, instance_path=row.instance_path,
                                            parameter_name=row.parameter_name, ratio=ratio) for row, ratio in rows]))
    graph.parameter_groups = groups
    try:
        graph.validate()
    except ValueError as exc:
        raise CompileError(f'Optimizer rejected the variable definition: {exc}') from exc
    return graph, tuple(variables)


def build_specs(config: WorkbenchConfig):
    from analog_optimizer.measurements.specs import MetricSpec
    specs, targets, preference = [], [], None
    for t in config.targets:
        convert = lambda v: None if v is None else units.to_canonical(v, t.unit)
        tolerance = units.scale_to_canonical(t.tolerance, t.unit)
        lower, upper = convert(t.lower), convert(t.upper)
        if t.constraint == 'target':
            center = convert(t.target)
            lower, upper = center - tolerance, center + tolerance
        else:
            # The optimizer has no tolerance field: relax the thresholds so reward, success
            # and the independent feasibility check all use the same acceptance region.
            lower = None if lower is None else lower - tolerance
            upper = None if upper is None else upper + tolerance
        comparator = 'range' if (lower is not None and upper is not None) else 'min' if lower is not None else 'max'
        unit = units.canonical_unit(t.unit)
        specs.append(MetricSpec(metric_id=t.metric_id, unit=unit, comparator=comparator,
                                scale=units.scale_to_canonical(t.normalization_scale, t.unit),
                                lower=lower, upper=upper, weight=t.soft_weight, required=t.hard, active=t.active))
        targets.append(dict(metric_id=t.metric_id, measurement_id=t.measurement_id, unit=unit, lower=lower,
                            upper=upper, hard=t.hard, active=t.active, constraint=t.constraint,
                            tolerance_applied=tolerance, scale=specs[-1].scale))
        if t.active and t.direction_after_feasible != 'none':
            preference = dict(metric=t.metric_id,
                              direction='min' if t.direction_after_feasible == 'minimize' else 'max')
    return tuple(specs), tuple(targets), preference


def build_spec_schema(config: WorkbenchConfig):
    from analog_optimizer.models.inputs import SpecSchema
    custom = config.run.advanced.spec_registry
    if custom is None:
        from .profiles import task_spec_registry
        generated = task_spec_registry(config.circuit)       # see validation.registry_for: the same fallback, the same order
        if generated is None:
            return SpecSchema()
        return SpecSchema(version='spec-input-generated-profile-v1',
                          metrics=tuple((e['metric_id'], units.canonical_unit(e['unit']), float(e['reference'])) for e in generated))
    return SpecSchema(version='spec-input-custom-v1',
                      metrics=tuple((e.metric_id, units.canonical_unit(e.unit), float(e.reference)) for e in custom))


def metric_sources(config: WorkbenchConfig):
    measurements = {m.measurement_id: m for m in config.measurements}
    sources = {}
    for t in config.targets:
        m = measurements[t.measurement_id]
        if m.result_source == 'backend_profile':
            sources[t.metric_id] = ('profile', m.source_name)
        elif m.result_source == 'expression':
            sources[t.metric_id] = ('expression', t.measurement_id)
        else:
            raise CompileError(f'{t.metric_id}: result_source={m.result_source} is not executable')
    return sources


def compile_task(config: WorkbenchConfig, graph) -> CompiledTask:
    compiled_graph, variables = build_graph(config, graph)
    specs, targets, preference = build_specs(config)
    schema = build_spec_schema(config)
    registry = {name: unit for name, unit, _ in schema.metrics}
    for spec in specs:
        if registry.get(spec.metric_id) != spec.unit:
            raise CompileError(f'{spec.metric_id} ({spec.unit}) is absent from the RL specification registry')
    return CompiledTask(compiled_graph, specs, schema, variables, targets, metric_sources(config), preference)


def evaluate_expression_measurements(config: WorkbenchConfig, raw: dict[str, float | None]):
    """Derive expression measurements from profile metrics. A missing/non-finite input makes
    the derived value invalid (None); it is never replaced by a number."""
    from analog_optimizer.netlist.expressions import evaluate, UnresolvedExpression
    measurements = {m.measurement_id: m for m in config.measurements}
    values: dict[str, float | None] = {}

    def resolve(measurement_id, trail=()):
        if measurement_id in values:
            return values[measurement_id]
        if measurement_id in trail:
            raise CompileError('expression cycle')
        m = measurements[measurement_id]
        if m.result_source == 'backend_profile':
            value = raw.get(m.source_name)
        elif m.result_source == 'expression':
            class Missing(Exception):
                pass

            def lookup(name):
                inner = resolve(name, trail + (measurement_id,))
                if inner is None:
                    raise Missing()
                return inner
            try:
                value = evaluate(m.expression, lookup)
            except (Missing, UnresolvedExpression, ZeroDivisionError, KeyError):
                value = None
        else:
            value = None
        if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
            value = None
        values[measurement_id] = value
        return value
    for key in measurements:
        resolve(key)
    return values


def hard_constraints(targets, metrics: dict, validity: dict):
    """Feasibility decided from raw canonical values and thresholds, independent of the reward.

    Returns (valid, feasible, rows). NaN, missing or invalid measurements are never feasible.
    `normalized_violation` is max(0, distance/scale) and is NOT capped, unlike the reward term.
    """
    rows, valid, feasible, worst = [], True, True, 0.0
    for t in targets:
        if not t['active']:
            continue
        value = metrics.get(t['metric_id'])
        ok = (validity.get(t['metric_id']) is True and isinstance(value, (int, float))
              and not isinstance(value, bool) and math.isfinite(value))
        satisfied, violation = None, None
        if ok:
            below = 0.0 if t['lower'] is None else max(0.0, t['lower'] - value)
            above = 0.0 if t['upper'] is None else max(0.0, value - t['upper'])
            violation = max(below, above) / t['scale']
            satisfied = violation == 0.0
        if t['hard']:
            valid = valid and ok
            feasible = feasible and bool(satisfied)
            if violation is not None:
                worst = max(worst, violation)
        rows.append(dict(metric_id=t['metric_id'], value=value if ok else None, valid=ok, hard=t['hard'],
                         lower=t['lower'], upper=t['upper'], satisfied=satisfied,
                         normalized_violation=violation))
    feasible = valid and feasible
    return valid, feasible, rows, (worst if valid else None)


def with_group_values(graph, values: dict):
    """Copy of `graph` with group/current member values set (used when re-reading a state)."""
    graph = deepcopy(graph)
    for i, group in enumerate(graph.parameter_groups):
        if group.id in values:
            graph.parameter_groups[i] = replace(group, value=values[group.id])
    return graph
