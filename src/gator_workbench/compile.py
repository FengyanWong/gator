"""Translate a validated WorkbenchConfig into the optimizer's existing objects.

Nothing here re-implements optimizer behaviour. Variables become the existing
``ParameterGroup``/``ParameterBinding`` (so ``ActionMapper`` legalizes actions
exactly as before) and targets become ``MetricSpec`` with the v2 reward contract.
Feasibility is checked
separately, from raw values and thresholds, by ``hard_constraints``. Each spec
judges the value of its equation over the probes (``spec_equations``).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

from . import spec_equations, units
from .profile_store import task_spec_registry
from .schema import WorkbenchConfig
from .task_registry import CORNER_TASKS, verified_profile, verified_spec_registry
from .validation import resolve_leaders


class CompileError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledTask:
    graph: object                      # CircuitGraph with the configured parameter groups
    specs: tuple                       # tuple[MetricSpec, ...]
    spec_schema: object                # SpecSchema used by the goal encoder
    variables: tuple                   # per independent variable: id, unit, bounds, members (canonical units)
    targets: tuple                     # canonical thresholds per active target (for independent feasibility)
    plan: object                       # spec_equations.SpecPlan: each spec's value from the probes, the same in every lane
    preference: dict | None            # {'metric': id, 'direction': 'min'|'max'} or None


def _canonical_bounds(parameter):
    lower, upper, step = parameter.lower, parameter.upper, parameter.step
    convert = lambda v: None if v is None else units.to_canonical(v, parameter.unit)
    return convert(lower), convert(upper), (None if step is None else units.scale_to_canonical(step, parameter.unit))


def grid_top(lower, upper, step, integer=False):
    """The highest value the optimizer gives a stepped group, when it lands ABOVE `upper`; else `upper` itself.
    `ParameterGroup.project` quantizes to lower + n*step with n = floor((upper - lower)/step + 1e-12) and does not clamp
    afterwards, so for about a quarter of ranges typed in decimals (1.84 .. 42.38 um in steps of 0.02 um) that top point
    is a hair above `upper` (4.2380000000000004e-05 > 4.238e-05) and the group refuses its own top value: a MOCK run
    failed "invalid bounds/current value" whenever the policy chose it. Computed exactly as `project` computes it, so
    taking it as the upper bound makes the top value legal and leaves every other grid point where it was."""
    grid = step or (1.0 if integer else None)
    if not grid or not all(math.isfinite(v) for v in (lower, upper, grid)):
        return upper                                  # no grid, or a domain the group's own check refuses
    top = lower + math.floor((upper - lower) / grid + 1e-12) * grid
    return top if top > upper else upper


def normalization_scale(target) -> float:
    """The scale a spec's violation is divided by: the one stated, else the size of its threshold (the larger of |lower|
    and |upper|), else 1 - the same rule the Specs column states."""
    if target.normalization_scale:
        return float(target.normalization_scale)
    return max([abs(v) for v in (target.lower, target.upper) if v is not None] or [0.0]) or 1.0


# The optimizer's eight parameter kinds and the one unit each is varied in (analog_optimizer.models.inputs: counts are
# spelled '1' there; the workbench's canonical spelling of a count is 'count').
KIND_UNITS = {'w': 'm', 'l': 'm', 'm': '1', 'nf': '1', 'r': 'ohm', 'c': 'F', 'ind': 'H', 'dc': 'V'}
UNIT_KINDS = {'m': 'l', '1': 'm', 'ohm': 'r', 'F': 'c', 'H': 'ind', 'V': 'dc'}


def group_unit(unit):
    """The unit a group is handed to the optimizer in: a count is '1' there (a group in 'count' was refused by the
    network input, so an `m` or `nf` row could never run before)."""
    return '1' if unit == 'count' else unit


def _group_kind(name, unit):
    """The optimizer's kind of a group: its own name when that is one of the eight kinds in its own unit, else the kind
    of its unit - a PDK parameter (an inductor's radius, a bipolar area factor) is varied as a length or a count, and its
    binding keeps its own name, which is what the network's column is chosen by (pdk.Vocabulary.view)."""
    if KIND_UNITS.get(name) == unit or (name == 'dc' and unit in ('V', 'A')):
        return name
    return UNIT_KINDS.get(unit)


def build_graph(config: WorkbenchConfig, graph):
    """Return a deep copy of `graph` whose parameter_groups are the configured variables."""
    from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
    graph = deepcopy(graph)
    parameters = list(config.parameters)
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
        # A varied group's upper bound is the optimizer's own top grid point when that lands above the typed bound
        # (grid_top), and a follower's own clamp at that same range moves with it; with the point not above, nothing moves.
        top = grid_top(lower, upper, step, leader.value_type == 'integer') if leader.optimized else upper
        bindings = []
        for row, ratio in rows:
            convert = lambda v, r=row: None if v is None else units.to_canonical(v, r.unit)
            own = row is not leader
            clamp = convert(row.upper) if own else None
            if clamp is not None and upper * ratio <= clamp < top * ratio:
                clamp = top * ratio
            bindings.append(ParameterBinding(row.instance_path, row.parameter_name, ratio,
                                             convert(row.lower) if own else None, clamp))
        upper = top
        unit = group_unit(units.canonical_unit(leader.unit))
        kind = _group_kind(leader.parameter_name, unit)
        if kind is None:
            raise CompileError(f'{leader_id}: {leader.parameter_name} in {leader.unit!r} cannot be varied: the optimizer '
                               'varies lengths, counts, resistances, capacitances, inductances and voltages only')
        group = ParameterGroup(id=leader_id, parameter_kind=kind,
                               unit=unit, value=value, lower=lower, upper=upper,
                               members=tuple(bindings),
                               domain='integer' if leader.value_type == 'integer' else 'continuous',
                               scale=leader.scale, mutable=leader.optimized, step=step)
        groups.append(group)
        variables.append(dict(variable_id=leader_id, unit=group.unit, lower=lower, upper=upper, step=step,
                              scale=leader.scale, domain=group.domain, optimized=leader.optimized,
                              parameter_kind=kind, parameter_name=leader.parameter_name,
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
        # The limits as stated: "target +/- tolerance" and a tolerance that loosened a limit were retired on 2026-10-03,
        # and a spec written with them states the limits they meant since it loaded (schema.PerformanceTarget).
        convert = lambda v: None if v is None else units.to_canonical(v, t.unit)
        lower, upper = convert(t.lower), convert(t.upper)
        comparator = 'range' if (lower is not None and upper is not None) else 'min' if lower is not None else 'max'
        unit = units.canonical_unit(t.unit)
        specs.append(MetricSpec(metric_id=t.metric_id, unit=unit, comparator=comparator,
                                scale=units.scale_to_canonical(normalization_scale(t), t.unit),
                                lower=lower, upper=upper, weight=t.soft_weight, required=t.hard, active=t.active,
                                objective={'none': 'none', 'minimize': 'min', 'maximize': 'max'}[t.direction_after_feasible],
                                nominal_only=t.nominal_only, missing_is_failure=t.missing_is_failure, margin_sides=t.margin_sides))
        equation = t.equation.strip()
        targets.append(dict(metric_id=t.metric_id, equation=equation,
                            probe=equation if equation in {m.measurement_id for m in config.measurements} else None,
                            unit=unit, lower=lower, upper=upper, hard=t.hard, active=t.active, constraint=t.constraint,
                            scale=specs[-1].scale, nominal_only=t.nominal_only,
                            objective=specs[-1].objective, margin_sides=t.margin_sides))
        if t.active and t.direction_after_feasible != 'none':
            preference = dict(metric=t.metric_id,
                              direction='min' if t.direction_after_feasible == 'minimize' else 'max')
    return tuple(specs), tuple(targets), preference


def build_spec_schema(config: WorkbenchConfig):
    """The result registry the network is built with: the task's own (or the configured one), plus one entry per spec
    whose name it does not know yet (``spec_equations.registry_entries``). A configured registry is taken as given."""
    from analog_optimizer.models.inputs import SpecSchema
    base = _task_spec_schema(config)
    if config.run.advanced.spec_registry is not None:
        return base
    added = spec_equations.registry_entries(config, base.metrics)
    if not added:
        return base
    return SpecSchema(version=base.version + spec_equations.REGISTRY_SUFFIX, metrics=tuple(base.metrics) + added)


def _task_spec_schema(config: WorkbenchConfig):
    """The registry's `version` is its name (identity); the column layout is the code's (`SpecSchema.layout`)."""
    from analog_optimizer.models.inputs import SpecSchema
    custom = config.run.advanced.spec_registry
    if custom is None:
        generated = task_spec_registry(config.circuit)       # see validation.registry_for: the same fallback, the same order
        if generated is None:
            of_record = verified_spec_registry(config.circuit)
            if of_record is None:
                return SpecSchema()
            version, entries = of_record                      # identical to the experiment's own schema, so it keeps its name
            return SpecSchema(version=version, metrics=tuple((e['metric_id'], e['unit'], float(e['reference'])) for e in entries))
        return SpecSchema(version='spec-input-generated-profile-v1',
                          metrics=tuple((e['metric_id'], units.canonical_unit(e['unit']), float(e['reference'])) for e in generated))
    return SpecSchema(version='spec-input-custom-v1',
                      metrics=tuple((e.metric_id, units.canonical_unit(e.unit), float(e.reference)) for e in custom))


def reward_settings(config):
    from analog_optimizer.measurements.specs import RewardSettings
    return RewardSettings(**config.run.reward.model_dump())


def training_conditions(config):
    if config.run.conditions.policy == 'off':
        return ()
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
    if config.circuit.task_id not in CORNER_TASKS:
        raise CompileError('No task trains at corners: the only one, the real OTA7 task, was removed on 2026-09-30')
    profile = verified_profile(config.circuit.task_id.partition(':')[2])
    corners = {row['id']: PVTCorner(**row) for row in profile.condition_config['screening_corners']}
    return (SimulationCondition(profile.nominal_corner),) + tuple(
        SimulationCondition(corners[key], 'pvt_training') for key in config.run.conditions.corners)


def compile_task(config: WorkbenchConfig, graph) -> CompiledTask:
    compiled_graph, variables = build_graph(config, graph)
    specs, targets, preference = build_specs(config)
    schema = build_spec_schema(config)
    registry = {name: unit for name, unit, _ in schema.metrics}
    for spec in specs:
        if registry.get(spec.metric_id) != spec.unit:
            raise CompileError(f'{spec.metric_id} ({spec.unit}) is absent from the RL specification registry')
    plan = spec_equations.SpecPlan.from_config(config)
    for spec in plan.specs:
        if spec.probe is None:                          # one Probe ID is taken as it is, even with "." or "-" in it
            names, problem = spec_equations.parse(spec.equation)
            if not names:
                raise CompileError(f'{spec.spec_id}: the equation {spec.equation!r} cannot be evaluated '
                                   f'({problem or "it uses no probe"})')
    return CompiledTask(compiled_graph, specs, schema, variables, targets, plan, preference)


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
