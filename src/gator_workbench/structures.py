"""Matched devices read from the circuit graph, and the ties they suggest for the Parameters rows (status record 7.103).

The idea comes from netlist-crawler (github.com/Arcadia-1/netlist-crawler, MIT): recognize differential pairs, current
mirrors, tail sources, active loads and cascodes, and tell the user and the agent. Its rules take a device's type from the
first letter of its instance name and the supply rails from net names; here they run on the CircuitGraph the workbench
already loads, where the kind (nmos / pmos) and every pin's role (drain, gate, source, bulk) come from the verified device
mapping. So a PMOS pair that only shares VDD is no differential pair - the shared source of a pair must be a tail node,
with nothing on it but the pair and the current source below it - and an instance called TAIL or NM0 is read like any other.

A matched structure spreads along its two branches: from a differential or cross-coupled pair, the devices whose sources sit
on the two drains and share a gate are its cascodes, and the devices whose drains sit there and share a gate are its loads
(a current-mirror load when one of them is diode-connected); each pair found continues from its own far side. A current
mirror that is no load of a pair is a bias mirror: its ratio sets a current, which may be a design variable, so tying it is
offered but not ticked.

Nothing is simulated and nothing is written: `recognize` lists the structures, `suggest` turns the matched ones into ties of
the Parameters rows (binding_group + ratio, the ratio the circuit has now), which the page shows as a diff to apply or not.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from .schema import OptimizationParameter
from .tasks import member_variable_id
from .validation import resolve_leaders

MOS = ('nmos', 'pmos')
TAIL_ELEMENTS = ('isource', 'resistor')          # below a pair, besides the drain of a transistor of the pair's own type
KEEP_RATIO = ('w',)                              # a width may follow in the ratio the circuit has; others only when equal
TIE_KINDS = {'differential_pair': True, 'cross_coupled_pair': True, 'active_load': True, 'load_pair': True,
             'cascode_pair': True, 'current_mirror': False}          # kind -> ticked by default
NOTE_LIMIT = 1000                                # schema.OptimizationParameter.notes


@dataclass(frozen=True)
class Structure:
    # A recognized device relationship with ordered members and an explanation for the parameter editor.
    kind: str                                    # differential_pair, cross_coupled_pair, tail_source, active_load,
    devices: tuple[str, ...]                     # load_pair, cascode_pair, current_mirror; a mirror's reference first
    text: str

    def as_dict(self) -> dict:
        return dict(kind=self.kind, devices=list(self.devices), text=self.text)


def _natural(text: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]


def _pins(graph) -> dict:
    pins: dict = {}
    for c in graph.connections:
        pins.setdefault(c.device_id, {})[c.role] = c.net_id
    return pins


def _transistors(graph, pins) -> dict:
    """id -> (kind, model, pins) of every transistor whose drain, gate and source the mapping names, in natural order."""
    found = {d.id: (d.kind, d.model_ref, pins.get(d.id, {})) for d in graph.devices
             if d.kind in MOS and all(role in pins.get(d.id, {}) for role in ('drain', 'gate', 'source'))}
    return {key: found[key] for key in sorted(found, key=_natural)}


def _rails(graph) -> set:
    return ({n.id for n in graph.nets if {'ground', 'supply'} & set(n.roles)}
            | set((graph.metadata or {}).get('globals') or ()))


def _tail(net, pair, kind, on_net, kinds):
    """The elements below a pair on its shared source `net`: every one a current source - the drain of a transistor of the
    pair's type, a current source or a resistor - and at least one. None for any other net: a rail where other sources
    sit, a node a voltage source drives, a node a pair device reaches with its drain or gate."""
    below = []
    for c in on_net.get(net, ()):
        if c.device_id in pair:
            if c.role not in ('source', 'bulk'):
                return None
        elif (kinds.get(c.device_id) == kind and c.role == 'drain') or kinds.get(c.device_id) in TAIL_ELEMENTS:
            below.append(c.device_id)
        else:
            return None
    return sorted(set(below), key=_natural) or None


def _both(pair) -> str:
    return f'{pair[0]} / {pair[1]}'


def _seed_groups(mos):
    """Each device's ordered peers of the same kind, model and source, and its position among them.

    Keep the outer device order: walking whole groups in turn would move interleaved pairs and their explanations.
    Each group's positions avoid slicing the full remaining device list for every outer device.
    """
    groups, positions = {}, {}
    for name, (kind, model, pins) in mos.items():
        members = groups.setdefault((kind, model, pins['source']), [])
        positions[name] = (members, len(members))
        members.append(name)
    return positions


def recognize(graph) -> list:
    """The structures of `graph` (an analog_optimizer CircuitGraph), in a stable order. Identifiers only."""
    pins = _pins(graph)
    mos = _transistors(graph, pins)
    kinds = {d.id: d.kind for d in graph.devices}
    rails = _rails(graph)
    on_net: dict = {}
    for c in graph.connections:
        on_net.setdefault(c.net_id, []).append(c)
    diode = {d for d, (_, _, p) in mos.items() if p['gate'] == p['drain']}
    order = list(mos)
    structures, seen = [], set()

    def add(kind, devices, text):
        key = (kind, tuple(devices))
        if key not in seen:
            seen.add(key)
            structures.append(Structure(kind, tuple(devices), text))

    # Seeds: differential and cross-coupled pairs (same type and model, one source, two gates, two drains).
    seeds = []
    seed_groups = _seed_groups(mos)
    for a in order:
        ka, ma, pa = mos[a]
        members, position = seed_groups[a]
        for index in range(position + 1, len(members)):
            b = members[index]
            kb, mb, pb = mos[b]
            if (ka, ma, pa['source']) != (kb, mb, pb['source']) or pa['gate'] == pb['gate'] or pa['drain'] == pb['drain']:
                continue
            if a in diode or b in diode:
                continue
            cross = pa['gate'] == pb['drain'] and pb['gate'] == pa['drain']
            source = pa['source']
            below = None if source in rails else _tail(source, (a, b), ka, on_net, kinds)
            if not cross and below is None:
                continue
            if cross:
                add('cross_coupled_pair', (a, b), f'{a} and {b} are a cross-coupled pair: each gate is on the other\'s drain.')
            else:
                add('differential_pair', (a, b), f'{a} and {b} are a differential pair (gates {pa["gate"]} / {pb["gate"]}, '
                                                 f'shared source {source}).')
            for t in below or ():
                if t in mos:
                    add('tail_source', (t,), f'{t} is the tail current source of the pair {a} / {b}.')
            seeds.append(((a, b), (pa['drain'], pb['drain'])))

    # Spread along the two branches of every matched pair.
    matched = {tuple(s[0]) for s in seeds}
    # A cascode or a load of a branch pair has its source or its drain on the two branches, so only the transistors that
    # touch those two nets are tried - in natural order, the same pairs in the same order as trying every pair, which was
    # quadratic per pair found (800 transistors: 12 s).
    touching: dict = {}                          # net -> the transistors whose source or drain is on it
    for x in order:
        for net in dict.fromkeys((mos[x][2]['source'], mos[x][2]['drain'])):
            touching.setdefault(net, []).append(x)
    work, visited = list(seeds), set()
    while work:
        pair, (left, right) = work.pop(0)
        if (left, right) in visited or left == right:
            continue
        visited.add((left, right))
        for c in touching.get(left, ()):
            kc, mc, pc = mos[c]
            for d in touching.get(right, ()):
                if d == c or c in pair or d in pair:
                    continue
                kd, md, pd = mos[d]
                if (kc, mc, pc['gate']) != (kd, md, pd['gate']):
                    continue
                if pc['source'] == left and pd['source'] == right:              # above the branches: cascodes
                    found = (c, d)
                    if found not in matched:
                        matched.add(found)
                        add('cascode_pair', found, f'{c} and {d} are matched cascodes on {_both(pair)} '
                                                   f'(shared gate {pc["gate"]}).')
                        work.append((found, (pc['drain'], pd['drain'])))
                elif pc['drain'] == left and pd['drain'] == right:              # on the branches: loads
                    found = (c, d)
                    if found in matched:
                        continue
                    matched.add(found)
                    if pc['source'] == pd['source']:
                        reference = next((x for x in found if x in diode), None)
                        if reference is not None:
                            other = d if reference == c else c
                            add('active_load', (reference, other), f'{reference} (diode-connected) and {other} are the '
                                                                   f'current-mirror load of {_both(pair)}.')
                        else:
                            add('load_pair', found, f'{c} and {d} are matched loads of {_both(pair)} '
                                                    f'(shared gate {pc["gate"]}).')
                        if pc['source'] not in rails:
                            work.append((found, (pc['source'], pd['source'])))
                    else:
                        add('cascode_pair', found, f'{c} and {d} are matched cascodes of the loads of {_both(pair)} '
                                                   f'(shared gate {pc["gate"]}).')
                        work.append((found, (pc['source'], pd['source'])))

    # Current mirrors: one gate, one source, a diode-connected reference. One that already is a load is not listed twice.
    loads = {frozenset(s.devices) for s in structures if s.kind == 'active_load'}
    groups: dict = {}
    for d, (kind, model, p) in mos.items():
        groups.setdefault((kind, model, p['gate'], p['source']), []).append(d)
    for members in groups.values():
        references = [d for d in members if d in diode]
        if len(members) < 2 or not references:
            continue
        reference, outputs = references[0], [d for d in members if d != references[0]]
        if frozenset(members) in loads:
            continue
        add('current_mirror', (reference, *outputs), f'{reference} (diode-connected) mirrors its current into '
                                                     f'{", ".join(outputs)}.')
    return structures


# ------------------------------------------------------------------------------ ties for the Parameters rows
def _value(graph, device, parameter):
    value = (graph.parameters.get(device) or {}).get(parameter)
    return value.value if value is not None and value.valid and value.value > 0 else None


def _ultimate(leaders, variable_id):
    return leaders.get(variable_id, (variable_id, 1.0))[0]


def _ratio_text(ratio) -> str:
    return f'{ratio:.6g}'


def plan_ties(graph, rows, structures=None) -> list:
    """One suggestion per matched structure: what tying its devices would change in `rows` (schema.OptimizationParameter
    objects). Rows are never changed here. Each change: tie (an existing row follows the leader), add (a follower row for
    a device that has none), kept (already tied that way) or skip (with the reason)."""
    structures = recognize(graph) if structures is None else structures
    try:
        leaders = resolve_leaders(rows)
    except ValueError:
        leaders = {}
    by_key = {(r.instance_path, r.parameter_name): r for r in rows if r.instance_path}
    suggestions = []
    for structure in structures:
        if structure.kind not in TIE_KINDS:
            continue
        devices = structure.devices
        parameters = sorted({p for (device, p) in by_key if device in devices}, key=lambda p: (p != 'w', p))
        changes = []
        for parameter in parameters:
            present = [by_key.get((d, parameter)) for d in devices]
            independent = [r for r in present if r is not None and not r.binding_group]
            leader = independent[0] if independent else next(r for r in present if r is not None)
            lead_value = _value(graph, leader.instance_path, parameter)
            for device, row in zip(devices, present):
                if device == leader.instance_path:
                    continue
                change = dict(device=device, parameter=parameter, variable_id=row.variable_id if row else None,
                              leader=leader.variable_id, leader_device=leader.instance_path)
                value = _value(graph, device, parameter)
                if row is not None and row.binding_group and _ultimate(leaders, row.variable_id) == _ultimate(leaders, leader.variable_id):
                    changes.append(dict(change, action='kept', reason=f'already follows {row.binding_group}'))
                    continue
                if row is not None and row.binding_group:
                    changes.append(dict(change, action='skip', reason=f'already follows {row.binding_group}: left as it is'))
                    continue
                if value is None or lead_value is None:
                    changes.append(dict(change, action='skip', reason='its value in the circuit is not a positive number'))
                    continue
                ratio = value / lead_value
                if parameter not in KEEP_RATIO and not math.isclose(ratio, 1.0, rel_tol=1e-9):
                    changes.append(dict(change, action='skip', reason=f'{parameter} differs in the circuit '
                                                                      f'({value:g} vs {lead_value:g}): left as it is'))
                    continue
                changes.append(dict(change, action='tie' if row is not None else 'add', ratio=ratio))
        if not changes:
            continue
        acting = [c for c in changes if c['action'] in ('tie', 'add')]
        suggestions.append(dict(id=f'{structure.kind}:{"+".join(devices)}', kind=structure.kind, devices=list(devices),
                                text=structure.text, default=TIE_KINDS[structure.kind] and bool(acting),
                                note='' if TIE_KINDS[structure.kind] else
                                'A bias mirror: tying keeps the copied current fixed. Leave it untied when that current is a '
                                'design variable.',
                                changes=changes, acts=bool(acting)))
    return suggestions


def _note(existing: str, added: str) -> str:
    text = f'{existing} {added}'.strip() if existing else added
    return text if len(text) <= NOTE_LIMIT else text[:NOTE_LIMIT - 3] + '...'


WHY = {'differential_pair': 'differential pair', 'cross_coupled_pair': 'cross-coupled pair', 'active_load':
       'current-mirror load', 'load_pair': 'matched loads', 'cascode_pair': 'matched cascodes',
       'current_mirror': 'current mirror'}


def apply_ties(graph, rows, chosen, structures=None) -> list:
    """`rows` (schema.OptimizationParameter) with the ties of the chosen suggestion IDs made: plain dicts in editor order,
    a new follower row right after the rows of its leader's group. The suggestions are planned again after each one is
    made, so two that share a device never tie it in a circle (the second one sees the first as kept). Unknown IDs are
    ignored; nothing changes that `plan_ties` would not list as tie or add."""
    structures = recognize(graph) if structures is None else structures
    out = [r.model_dump() for r in rows]
    for structure in structures:
        current = [OptimizationParameter.model_validate(r) for r in out]
        for suggestion in plan_ties(graph, current, [structure]):
            if suggestion['id'] in chosen:
                out = _make(out, suggestion)
    return out


def _make(out, suggestion) -> list:
    """The rows (dicts) with one planned suggestion's tie and add changes made."""
    out = [dict(r) for r in out]
    used = {r['variable_id'] for r in out}
    why = WHY[suggestion['kind']]
    for change in suggestion['changes']:
        if change['action'] not in ('tie', 'add'):
            continue
        leader = next(r for r in out if r['variable_id'] == change['leader'])
        said = f'Tied to {change["leader"]} ({why}, ratio {_ratio_text(change["ratio"])}) by Matched devices.'
        follow = dict(binding_group=change['leader'], ratio=change['ratio'], optimized=leader['optimized'],
                      lower=None, upper=None, step=None)
        if change['action'] == 'tie':
            row = next(r for r in out if r['variable_id'] == change['variable_id'])
            was = (f' Its own range was {row["lower"]:g} .. {row["upper"]:g} {row["unit"]}.'
                   if row.get('lower') is not None and row.get('upper') is not None else '')
            row.update(follow, notes=_note(row.get('notes') or '', said + was))
            continue
        base = member_variable_id(change['leader'], change['device'])
        variable_id, n = base, 2
        while variable_id in used:
            variable_id, n = f'{base}_{n}', n + 1
        used.add(variable_id)
        row = dict(leader, variable_id=variable_id, instance_path=change['device'], initial_value=None,
                   notes=_note('', 'Added: ' + said), **follow)
        group = {change['leader']} | {r['variable_id'] for r in out if r.get('binding_group') == change['leader']}
        last = max(i for i, r in enumerate(out) if r['variable_id'] in group)
        out.insert(last + 1, row)
    return out


def suggest(graph, rows, chosen=None) -> dict:
    """What the page asks for: the structures, one suggestion per matched one, and - when `chosen` (suggestion IDs) is
    given - the rows with those ties made."""
    structures = recognize(graph)
    answer = dict(structures=[s.as_dict() for s in structures], suggestions=plan_ties(graph, rows, structures))
    if chosen is not None:
        answer['parameters'] = apply_ties(graph, rows, set(chosen), structures)
    return answer
