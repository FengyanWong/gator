"""Save task's side of writing any parameter the PDK's form lets a user type (the run's side is ``cdf_write``).

The rows of the parameter editor are checked against the form rules read together with the cell (``cdf_facts``):
which CDF parameter feeds each netlist parameter, whether the form lets a user type it in that instance now, what kind
of value it holds. What passes becomes a rules file of format 2 (``rules_v2``):

* every write - the netlist parameter the optimizer varies, the CDF parameter typed for it, its instance and cell, the
  form's rule and callback, its range and grid;
* every value of a written instance that a user could type but that must stay as recorded ("held": the run puts it
  back when a callback moves it, as a user re-types a field the form changed - GPDK045 folds a wide transistor into
  more fingers when its total width is typed);
* per cell: the form's init and done procedures, its mode settings (never changed by a write) and its internal
  bookkeeping values (never shown in the form, e.g. ``pasUpdateParamList``: not compared).

Grids, because a real run stops at the first value the PDK does not keep as written: lengths on the 5 nm grid the
GPDK045 readbacks confirmed (a transistor's total width on fingers x 5 nm, so that its finger width stays on it),
counts on whole numbers, a choice list on its own values (a uniform one only), anything else on the row's own step or
continuous.
"""
from __future__ import annotations

import math

from . import cdf_facts, units
from .cdf_facts import NotWritable
from .compile import group_unit
from .generic_profile import VERIFIED_WIDTH_STEP
from .cdf_text import cdf_number
from .validation import resolve_leaders

_GRID_ROUNDING_TOL = 1e-07
_GRID_ABS_TOL = 1e-18


RULES_FORMAT = 'gator-profile-rules-2'
LENGTH_GRID = VERIFIED_WIDTH_STEP


class RowError(ValueError):
    """A row a real run cannot honour, in words the editor can show."""


def _instance_params(reference, instance):
    found = [item for item in reference.get('instances', []) if item.get('name') == instance]
    if len(found) != 1:
        raise NotWritable(f'{instance} is not in the recorded readback of the core cell')
    return found[0].get('params') or {}


def _netlist_name(graph, device, parameter):
    """The netlist's own name of a graph parameter (the parser may rename one: an inductor's radius `r` is `rad`)."""
    value = (graph.parameters.get(device) or {}).get(parameter)
    return getattr(value, 'source_name', None) or parameter


def spec_for(facts, core, device, parameter, reference, graph) -> dict:
    """What a run writes for one netlist parameter, or NotWritable with the reason."""
    found = cdf_facts.sources(facts, core, device)
    name = _netlist_name(graph, device, parameter)
    if name not in found:
        raise NotWritable(f'{device} has no netlist parameter "{name}" in its description')
    source = found[name]
    if source is None:
        raise NotWritable(f'{device}.{parameter}: no field of the property form sets it')
    instance = device.split('/')[1]
    if source['on'] != 'parent' and len(device.split('/')) == 3:
        raise NotWritable(f'{device}.{parameter}: its value is set inside the cell {facts["instances"][instance]["cell"]} '
                          f'places, not on {instance}, so the form of {instance} cannot type it')
    why = cdf_facts.editable(facts, instance, source)
    if why:
        # A field the form computes, with a typed field of the netlist parameter's own name beside it (the second foundry
        # PDK's transistor multiplier: netlist m <- simM = fingers x m, typed in `m`): the user sets it there. The comparison
        # below admits it only while that field holds the netlisted number (one finger).
        twin = cdf_facts.typed_twin(facts, core, device, name, source)
        if twin is None:
            raise NotWritable(f'{device}.{parameter} (form field {source["cdf"]}): {why}')
        source = twin
    current = _instance_params(reference, instance).get(source['cdf'])
    try:
        kind, choices = cdf_facts.value_kind(source, current)
    except NotWritable as exc:
        raise NotWritable(f'{device}.{parameter} (form field {source["cdf"]}): {exc}')
    netlisted = (graph.parameters.get(device) or {}).get(parameter)
    value = cdf_number(current)
    if netlisted is None or not netlisted.valid:
        raise NotWritable(f'{device}.{parameter}: the exported netlist gives it no number')
    if value is None or not math.isclose(value, netlisted.value, rel_tol=1e-8, abs_tol=1e-24):
        raise NotWritable(f'{device}.{parameter} = {netlisted.raw} in the netlist, but its form field {source["cdf"]} holds '
                          f'{current!r}: the PDK computes one from the other, so it cannot be written')
    return dict(device=device, parameter=parameter, instance=instance, cell=facts['instances'][instance]['cell'],
                cdf=source['cdf'], on=source['on'], kind=kind, choices=choices,
                rule=True if source['editable'] is True else source['editable'], callback=source['callback'] or None,
                unit=cdf_facts.unit_of(facts, source), value=value, range=source.get('range'))


def held_for(facts, core, device, written, reference, graph) -> list:
    """The values a user could type into the instance of `device` that the run must keep as recorded: every other
    netlist parameter fed by an editable field (a number: put back when a callback moves it; anything else: compared).
    `written` = {(device, graph parameter)}."""
    instance = device.split('/')[1]
    params = _instance_params(reference, instance)
    in_graph = {getattr(value, 'source_name', None) or key: key for key, value in (graph.parameters.get(device) or {}).items()}
    written_names = {_netlist_name(graph, d, p) for d, p in written if d == device}
    out = []
    for name, source in cdf_facts.sources(facts, core, device).items():
        if source is None or name in written_names or source['on'] == 'self' and len(device.split('/')) == 3:
            continue                                        # computed / written / inside the PDK cell's own schematic
        if cdf_facts.editable(facts, instance, source) is not None or source['type'] in ('boolean', 'radio'):
            continue                                        # computed by the form (areas, ...) - or a mode, compared anyway
        current = params.get(source['cdf'])
        try:
            kind, choices = cdf_facts.value_kind(source, current)
            value = cdf_number(current)
        except NotWritable:
            if source['type'] == 'cyclic':
                continue                                    # a word choice: a mode, compared with the modes
            kind, choices, value = source['type'], None, None
        out.append(dict(device=device, netlist=name, parameter=in_graph.get(name), instance=instance, cdf=source['cdf'],
                        kind=kind, choices=choices,
                        rule=True if source['editable'] is True else source['editable'], callback=source['callback'] or None,
                        value=value, recorded=current))
    return out


def derived_for(facts, core, device, written, held, graph) -> list:
    """The netlist parameters of a written instance that the form COMPUTES (a transistor's areas, a MIM capacitor's
    capacitance): they may change with a write, and the export must then carry what the form now holds - the check the
    verified profile makes for a transistor's geometry."""
    instance = device.split('/')[1]
    in_graph = {getattr(value, 'source_name', None) or key: key for key, value in (graph.parameters.get(device) or {}).items()}
    taken = {_netlist_name(graph, d, p) for d, p in written if d == device} | {h['netlist'] for h in held if h['device'] == device}
    out = []
    for name, source in cdf_facts.sources(facts, core, device).items():
        if source is None or name in taken or name not in in_graph:
            continue
        if source['on'] != 'parent' and len(device.split('/')) == 3:
            continue                                        # inside the PDK cell's own schematic: compared with the record
        out.append(dict(device=device, parameter=in_graph[name], netlist=name, instance=instance, cdf=source['cdf']))
    return out


# ------------------------------------------------------------------------------------------ the rows
def member_grid(spec, facts, reference, written) -> tuple:
    """(grid, integer) of one written value: the step every value of it must be a whole multiple of. `written` = every
    write of the task, because a grid can depend on another written value of the same instance."""
    if spec['kind'] == 'choice':
        values = sorted(cdf_number(c) for c in spec['choices'])
        if len(values) < 2 or any(not math.isclose(b - a, values[1] - values[0], rel_tol=1e-9, abs_tol=_GRID_ABS_TOL)
                                  for a, b in zip(values, values[1:])):
            raise RowError(f'{spec["device"]}.{spec["parameter"]}: its choices {spec["choices"]} are not evenly spaced')
        return values[1] - values[0], False
    if spec['unit'] == '1':
        return 1.0, True
    if spec['unit'] == 'm':
        params = _instance_params(reference, spec['instance'])
        if spec['cdf'] == 'w' and {'fw', 'fingers'} <= set(params):
            if any(other['instance'] == spec['instance'] and other['cdf'] == 'fingers' for other in written):
                raise RowError(f'{spec["device"]}: vary its total width or its finger count, not both - the finger width '
                               'must stay on the 5 nm grid')
            fingers = cdf_number(params['fingers'])
            if fingers is None or fingers < 1 or fingers != int(fingers):
                raise RowError(f'{spec["device"]}: its finger count {params["fingers"]!r} is not a whole number')
            return LENGTH_GRID * fingers, False
        return LENGTH_GRID, False
    return None, False


def _multiple(value, grid):
    return math.isclose(value / grid, round(value / grid), rel_tol=0, abs_tol=_GRID_ROUNDING_TOL)


def _group_step(members, wanted):
    """The smallest step that moves every member (ratio, grid) by whole grid steps; `wanted` must do that itself."""
    gridded = [(ratio, grid) for ratio, grid in members if grid]
    if wanted is not None:
        if any(not _multiple(wanted * ratio, grid) for ratio, grid in gridded):
            raise RowError(f'a step of {wanted:g} does not keep every bound value on its grid')
        return wanted
    if not gridded:
        return None
    base = gridded[0][1] / gridded[0][0]
    for multiple in range(1, 401):
        if all(_multiple(multiple * base * ratio, grid) for ratio, grid in gridded):
            return multiple * base
    raise RowError('no step keeps every bound value on its grid: simplify the ratios')


def _short(value) -> float:
    return float(format(value, '.12g'))


def adjust(config, graph, core, facts, reference) -> tuple:
    """Rows of the parameter editor -> (rows a real run honours, optimized leader ids, leaders, {key: spec}).
    Raises RowError with the reason."""
    rows, leaders, optimized = _checked_adjustment_rows(config)
    specs = _checked_parameter_specs(rows, leaders, optimized, facts, core, reference, graph)
    by_id = {row.variable_id: row for row in rows}
    adjusted = []
    for row in rows:
        leader_id, _ = leaders[row.variable_id]
        if leader_id in optimized and row.binding_group:     # a follower keeps the ratio and nothing else
            row = row.model_copy(update=dict(lower=None, upper=None, step=None, scale='linear', value_type='continuous'))
        elif row.variable_id in optimized:
            row = _adjust_leader(row, specs, by_id, leaders, reference)
        adjusted.append(row)
    return adjusted, optimized, leaders, specs


def _checked_adjustment_rows(config) -> tuple:
    """Copy editor rows and require valid binding leaders with at least one optimized variable."""
    rows = [row.model_copy() for row in config.parameters]
    try:
        leaders = resolve_leaders(rows)
    except ValueError as exc:
        raise RowError(str(exc))
    optimized = {row.variable_id for row in rows if row.optimized and not row.binding_group}
    if not optimized:
        raise RowError('Nothing is marked as optimized: the parameter editor needs at least one variable that may change')
    return rows, leaders, optimized


def _checked_parameter_specs(rows, leaders, optimized, facts, core, reference, graph):
    """Resolve writable form specifications, validate units, and determine each optimized member grid."""
    specs = {}
    for row in rows:
        leader_id, _ = leaders[row.variable_id]
        if leader_id not in optimized:
            continue                                        # a fixed variable: recorded, never written
        where = f'{row.variable_id} ({row.instance_path}.{row.parameter_name})'
        try:
            spec = spec_for(facts, core, row.instance_path, row.parameter_name, reference, graph)
        except NotWritable as exc:
            raise RowError(f'{where}: {exc}')
        if not units.known(row.unit) or group_unit(units.canonical_unit(row.unit)) != spec['unit']:
            unit = {'m': 'a length (um, nm, m)', '1': 'a count', 'F': 'a capacitance (pF, fF)', 'ohm': 'a resistance (ohm, kohm)',
                    'H': 'an inductance (nH, pH)', 'V': 'a voltage (V, mV)'}.get(spec['unit'], spec['unit'])
            raise RowError(f'{where}: its form field {spec["cdf"]} holds {unit}; give the row that unit')
        specs[row.instance_path, row.parameter_name] = spec
    for spec in specs.values():                             # a grid can depend on another written value of the instance
        spec['grid'], spec['integer'] = member_grid(spec, facts, reference, list(specs.values()))
    return specs


def _adjust_leader(row, specs, by_id, leaders, reference):
    """Validate an optimized binding group and return its leader with legal bounds, step, and value type."""
    members = [(ratio, specs[by_id[other].instance_path, by_id[other].parameter_name])
               for other, (lead, ratio) in leaders.items() if lead == row.variable_id]
    spec = specs[row.instance_path, row.parameter_name]
    if len({m['unit'] for _, m in members}) != 1:
        raise RowError(f'{row.variable_id}: the values bound together hold different kinds of quantity')
    choice = [m for _, m in members if m['kind'] == 'choice']
    if choice and (len(choice) != len(members) or any(r != 1.0 for r, _ in members)
                   or len({tuple(m['choices']) for m in choice}) != 1):
        raise RowError(f'{row.variable_id}: a choice list can only be bound to the same choice list, ratio 1')
    integer = any(m['integer'] for _, m in members)
    if row.lower is None or row.upper is None:
        raise RowError(f'{row.variable_id}: a lower and an upper bound are required')
    lower, upper = units.to_canonical(row.lower, row.unit), units.to_canonical(row.upper, row.unit)
    step = None if row.step is None else units.scale_to_canonical(row.step, row.unit)
    if row.scale == 'log' and lower <= 0:
        raise RowError(f'{row.variable_id}: a logarithmic range needs a positive lower bound')
    _check_declared_ranges(members, lower, upper, row)
    step, lower, upper = _snap_leader_range(members, step, row, integer, choice, spec, lower, upper)
    _check_finger_widths(members, reference, step, lower, upper, row)
    if choice:
        allowed = [cdf_number(c) for c in spec['choices']]
        grid_points = [lower + k * step for k in range(int(round((upper - lower) / step)) + 1)]
        if any(not any(math.isclose(p, a, rel_tol=1e-9, abs_tol=_GRID_ABS_TOL) for a in allowed) for p in grid_points):
            raise RowError(f'{row.variable_id}: every value of the range must be one of the choices {spec["choices"]}')
    scale = units.scale_to_canonical(1.0, row.unit)
    row = row.model_copy(update=dict(
        lower=_short(lower / scale), upper=_short(upper / scale), step=None if step is None else _short(step / scale),
        initial_value=None, value_type='integer' if integer else 'continuous'))
    return row


def _check_declared_ranges(members, lower, upper, row) -> None:
    """Reject a bound group whose requested range exceeds any member property form range."""
    # The PDK's own declared range, when it states one: the property form refuses a value outside it, so a row
    # that leaves it would die on its first clamped candidate - after a real evaluation was paid for.
    for ratio, member in members:
        allowed = member.get('range')
        if not allowed or not ratio:
            continue
        low, high = min(lower * ratio, upper * ratio), max(lower * ratio, upper * ratio)
        if low < allowed[0] - _GRID_ABS_TOL or high > allowed[1] + _GRID_ABS_TOL:
            scale = units.scale_to_canonical(1.0, row.unit) or 1.0        # canonical -> the row's own unit
            raise RowError(f'{row.variable_id}: the property form of {member["device"]} accepts '
                           f'{allowed[0] / scale:g} to {allowed[1] / scale:g} {row.unit} for {member["cdf"]}; '
                           f'the row asks for {row.lower:g} to {row.upper:g} {row.unit}'
                           + (f' (ratio {ratio:g})' if ratio != 1 else ''))


def _snap_leader_range(members, step, row, integer, choice, spec, lower, upper) -> tuple:
    """Resolve a shared step, snap bounds inward, and check the present value and count constraints."""
    try:
        step = _group_step([(ratio, m['grid']) for ratio, m in members], step)
    except RowError as exc:
        raise RowError(f'{row.variable_id}: {exc}')
    if integer and step is not None and step != int(step):
        raise RowError(f'{row.variable_id}: a count moves in whole steps')
    if choice:                                                    # snapped INWARD onto the choices
        inside = [a for a in sorted(cdf_number(c) for c in spec['choices'])
                  if lower - 1e-12 * abs(lower) <= a <= upper + 1e-12 * abs(upper)]
        if len(inside) < 2:
            raise RowError(f'{row.variable_id}: the range holds fewer than two of the choices {spec["choices"]}')
        lower, upper = inside[0], inside[-1]
    elif step is not None:                                       # snapped INWARD onto the grid
        lower = math.ceil(lower / step - _GRID_ROUNDING_TOL) * step
        upper = math.floor(upper / step + _GRID_ROUNDING_TOL) * step
    current = spec['value']
    if not lower < upper or not lower - 1e-15 * abs(lower) - 1e-30 <= current <= upper + 1e-15 * abs(upper) + 1e-30:
        raise RowError(f'{row.variable_id}: the range {lower:g} .. {upper:g} {spec["unit"]} (after snapping onto the '
                       f'grid) must contain the present value {current:g}')
    if step is not None and not _multiple((current - lower), step):
        raise RowError(f'{row.variable_id}: the present value {current:g} is not on the grid {lower:g} + k x {step:g}')
    if integer and lower < 1:
        raise RowError(f'{row.variable_id}: a count starts at 1')
    return step, lower, upper


def _check_finger_widths(members, reference, step, lower, upper, row) -> None:
    """Reject finger-count ranges that would place the recorded total width off the verified length grid."""
    for ratio, member in members:                  # a finger count must keep the finger width on the grid
        params = _instance_params(reference, member['instance'])
        if member['cdf'] == 'fingers' and {'w', 'fw'} <= set(params) and step:
            total = cdf_number(params['w'])
            counts = [(lower + k * step) * ratio for k in range(int(round((upper - lower) / step)) + 1)]
            off = [round(c) for c in counts if total is None or not _multiple(total / c, LENGTH_GRID)]
            if off:
                fits = [round(c) for c in counts if round(c) not in off]
                raise RowError(f'{row.variable_id}: with its total width of {total:g} m, {member["device"]} would get a '
                               f'finger width off the 5 nm grid at {", ".join(map(str, off[:6]))} fingers; the counts of '
                               f'the range that fit: {", ".join(map(str, fits)) or "none"}')


# ------------------------------------------------------------------------------------------ the rules file
def rules_v2(*, recipe, core, facts, reference, compiled, specs) -> dict:
    """The rules file of format 2 from the compiled groups (their bounds are what the optimizer may ask for)."""
    writes = []
    for group in compiled.parameter_groups:
        if not group.mutable:
            continue
        for member in group.members:
            spec = specs[member.device_id, member.parameter]
            grid = None if group.step is None else group.step * member.ratio
            writes.append(dict(device=spec['device'], parameter=spec['parameter'], instance=spec['instance'], cell=spec['cell'],
                               cdf=spec['cdf'], kind=spec['kind'], rule=spec['rule'], callback=spec['callback'],
                               lower=group.lower * member.ratio, upper=group.upper * member.ratio,
                               step=grid, integer=group.domain == 'integer' or bool(spec['integer']),
                               grid=spec['grid'], choices=spec['choices'], unit=spec['unit']))
    written = {(w['device'], w['parameter']) for w in writes}
    held = []
    for device in sorted({w['device'] for w in writes}):
        held += held_for(facts, core, device, written, reference, compiled)
    derived = []
    for device in sorted({w['device'] for w in writes}):
        derived += derived_for(facts, core, device, written, held, compiled)
    held_cdf = {(h['instance'], h['cdf']) for h in held}
    written_cdf = {(w['instance'], w['cdf']) for w in writes}
    if held_cdf & written_cdf:
        raise RowError('A form field would be both written and held: ' + ', '.join(f'{i}.{c}' for i, c in sorted(held_cdf & written_cdf)))
    instances = {item['name']: item.get('cell') for item in reference.get('instances', [])}
    cells = {}
    for cell in sorted({c for c in instances.values() if c in facts['cells']}):
        parameters = facts['cells'][cell].get('parameters') or {}
        cells[cell] = dict(form=cdf_facts.form_of(facts, cell), modes=cdf_facts.mode_parameters(facts, cell),
                           internal=sorted(name for name, entry in parameters.items() if entry.get('display') is False))
    return dict(format=RULES_FORMAT, recipe=recipe, core_instance=core, instances=instances, cells=cells, writes=writes,
                held=held, derived=derived, facts=dict(format=facts.get('format'), library=facts.get('library'), cell=facts.get('cell')))
