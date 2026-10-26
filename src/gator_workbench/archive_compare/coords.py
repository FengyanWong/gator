"""An archived design in the optimizers' coordinates (plan 4.1: "the GP input is the executed physical design mapped to
the frozen target domain").

The optimizer decodes a proposal z in [-1, 1] per parameter group to a physical value - log or linear across the
group's range - and projects it onto the group's grid (`ActionMapper.legalize`). `to_proposal` is the exact inverse
for an executed (on-grid) value, and `round_trip` proves it on a design: legalizing the inverse gives the executed values
back. The BO arms fit and search in u = (z + 1) / 2, the unit cube of `bayes.TrustRegionBO`.
"""
from __future__ import annotations

import math


def group_rows(compiled) -> list[dict]:
    """The varied parameter groups of a compiled task, in the action order: id, scale, bounds, step, domain and the
    members each writes (instance, parameter, ratio)."""
    rows = []
    for group in compiled.graph.parameter_groups:
        if not group.mutable:
            continue
        rows.append(dict(id=group.id, scale=group.scale, lower=group.lower, upper=group.upper, step=group.step,
                         domain=group.domain, members=[dict(instance=m.device_id, parameter=m.parameter, ratio=m.ratio)
                                                       for m in group.members]))
    return rows


def to_proposal(group, value: float) -> float:
    """The proposal z in [-1, 1] whose decode is `value` (before the grid projection, which leaves an on-grid value)."""
    lower, upper = group['lower'], group['upper']
    if not lower <= value <= upper:
        raise ValueError(f"{group['id']}: {value!r} is outside [{lower!r}, {upper!r}]")
    if value == lower:
        return -1.0
    if value == upper:
        return 1.0
    if group['scale'] == 'log':
        fraction = (math.log(value) - math.log(lower)) / (math.log(upper) - math.log(lower))
    else:
        fraction = (value - lower) / (upper - lower)
    return max(-1.0, min(1.0, 2.0 * fraction - 1.0))


def group_values(groups, members: dict) -> dict:
    """Each group's executed value from the executed member values (`members`: (instance, parameter) -> value), read
    from the member with ratio 1 (the group's leader) and checked against every other member it writes."""
    values = {}
    for group in groups:
        leaders = [m for m in group['members'] if m['ratio'] == 1.0]
        if not leaders:
            raise ValueError(f"{group['id']}: no member with ratio 1")
        key = (leaders[0]['instance'], leaders[0]['parameter'])
        if key not in members or members[key] is None:
            raise ValueError(f"{group['id']}: no executed value for {key}")
        values[group['id']] = float(members[key])
    return values


def grid_index(group, value: float):
    """The grid point a value sits on (an int); for a group without a grid, the value to 12 significant digits. Two
    values on one grid point are one physical design even when their last binary digit differs: a start design keeps the
    value its netlist gave it (0.5 um read as 5.000000000000001e-07 m), while the optimizer's projection writes
    lower + n * step (5e-07). A gridless (continuous) value comes back from the log/linear decode within a few units of
    its 16th digit (116136.813164 -> 116136.81316400004), so 12 digits tell it apart from any other design."""
    step = group['step'] or (1.0 if group['domain'] == 'integer' else None)
    return round((value - group['lower']) / step) if step else float(f'{value:.12g}')


def design_key(groups, values: dict) -> tuple:
    return tuple(grid_index(group, values[group['id']]) for group in groups)


def round_trip(mapper, groups, values: dict) -> dict:
    """z for every group, the values legalizing z gives, and whether they are `values` again: bit for bit (`exact`)
    and on the same grid points (`same_grid_point`, the physical identity)."""
    proposal = {group['id']: to_proposal(group, values[group['id']]) for group in groups}
    legal = mapper.legalize(proposal)
    back = {g: legal.group_values[g] for g in proposal}
    exact = all(back[g] == values[g] for g in proposal)
    same = design_key(groups, back) == design_key(groups, values)
    return dict(proposal=proposal, legalized=back, exact=exact, same_grid_point=same,
                differing={g: (values[g], back[g]) for g in proposal if back[g] != values[g]})


def unit_point(groups, proposal: dict) -> list[float]:
    """The point of the unit cube a BO arm works in, in the groups' order."""
    return [(proposal[group['id']] + 1.0) / 2.0 for group in groups]
