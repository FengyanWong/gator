"""One file-driven circuit profile for the real backend, instead of one hand-written class per circuit.

The four verified profiles (``analog_optimizer.backends.gpdk045*``) follow one pattern and differ in
lists and numbers only: which MOS widths of the core cell may be written, inside which bounds, which
of them move together, and which other instances must stay exactly as recorded. This class reads
those from ``rules.json`` and otherwise repeats the verified checks line for line
(``Gpdk045TwoStageProfile`` is the closest hand-written form). ``tests/workbench/
test_wb_generic_profile.py`` regenerates the four circuits as rule files and proves that both forms
accept and reject the same assignments, readbacks, transitions and exports.

It lives outside ``src/analog_optimizer/`` on purpose: that package's source digest gates checkpoint
loading and the M5/M6 audits, and the real-run code is duck-typed on the profile object
(``backends/virtuoso_bridge.py``, ``native_preparation.py``, ``training/parallel.py``,
``provenance.profile_contract``), so subclassing from here needs no change there.

Deliberate limits, because they are the limits of what has been verified (every other value the PDK's property form
lets a user type is written by ``cdf_write``, rules of format 2 - this class stays the verified path for widths):
  * only MOS widths are writable - the adapter's single write path is ``set_gpdk_mos``, which also
    forces ``fingers = 1`` and ``m = 1``; a writable transistor recorded with anything else is refused;
  * widths move on the 5 nm grid that real CDF readbacks confirmed (``docs/decisions.md``);
  * nominal condition only, as for the LDO and VCO profiles: the supply override of the OTA profile
    rewrites one specific source line and is not generic;
  * GPDK045 only (``set_gpdk_mos`` refuses another PDK's callbacks).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path

from analog_optimizer.backends.backend import UnsupportedCapability
from analog_optimizer.backends.gpdk045 import GEOMETRY, Gpdk045OtaProfile, equal, number
from . import model_library
from .compile import grid_top

RULES_FORMAT = 'gator-profile-rules-1'
VERIFIED_WIDTH_STEP = 5e-9
MOS_FIXED = ('l', 'm', 'fingers')                       # never written by this profile: equal to the record, always
MOS_SIZE = ('w', 'fw') + GEOMETRY                       # follow the width of a writable transistor; fixed on every other


class RulesError(ValueError):
    """The rule file does not describe something the verified real backend can do."""


def _to_grid_top(group):
    """`group` with the optimizer's top grid point as its upper bound when that lands above it (compile.grid_top), a
    member clamp at that range moved with it - what compile.build_graph makes of the same row; else `group` itself."""
    top = grid_top(group.lower, group.upper, group.step, group.domain == 'integer') if group.mutable else group.upper
    if not top > group.upper:
        return group
    members = tuple(replace(m, upper=top * m.ratio) if m.upper is not None and group.upper * m.ratio <= m.upper < top * m.ratio
                    else m for m in group.members)
    return replace(group, upper=top, members=members)


def _same(a, b) -> bool:
    """Numbers compare as numbers ('50f' == '5e-14'); CDF expressions and flags compare as text."""
    try:
        return equal(number(a), number(b))
    except Exception:
        return str(a) == str(b)


class GenericMosWidthProfile(Gpdk045OtaProfile):
    recipe = 'opamp_ac'                                   # the adapter's own deck and `measurements.opamp.analyze`

    def __init__(self, *, rules_file, design_file, mapping_file, reference_structure, reference_readback,
                 conditions_file=None):
        rules = json.loads(Path(rules_file).read_text())
        if rules.get('format') != RULES_FORMAT:
            raise RulesError(f'Unknown rules format {rules.get("format")!r}')
        if rules.get('recipe', 'opamp_ac') != self.recipe:
            raise RulesError(f'These rules ask for the {rules.get("recipe")!r} recipe; this class provides {self.recipe!r}')
        core = rules.get('core_instance')
        if not isinstance(core, str) or not core or '/' in core:
            raise RulesError('core_instance must name the instance of the core cell in the testbench (e.g. "XU1")')
        step = rules.get('width_step')
        if step != VERIFIED_WIDTH_STEP:
            raise RulesError(f'Only the verified {VERIFIED_WIDTH_STEP:g} m width grid is supported')
        writable = rules.get('writable') or []
        names = [item.get('instance') for item in writable]
        if not writable or len(set(names)) != len(names) or any(not isinstance(n, str) or not n for n in names):
            raise RulesError('writable must list distinct transistor instances of the core cell')
        self.rules, self.core_instance = rules, core
        self.mos_names = tuple(rules.get('mos_instances') or ())
        self.fixed_instances = tuple(rules.get('fixed_instances') or ())
        if set(names) - set(self.mos_names) or set(self.mos_names) & set(self.fixed_instances):
            raise RulesError('Every writable instance must be one of mos_instances, and no instance can be both MOS and fixed')
        self.writable_keys = tuple((f'{core}/{name}', 'w') for name in names)
        self.bounds = {}
        for item in writable:
            lower, upper = item.get('lower'), item.get('upper')
            if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lower, upper))
                    or not 0 < lower < upper):
                raise RulesError(f'Invalid width bounds for {item["instance"]}')
            self.bounds[f'{core}/{item["instance"]}'] = (float(lower), float(upper))
        self.deck_name = rules.get('deck_name') or 'circuit.scs'
        overall = (min(b[0] for b in self.bounds.values()), max(b[1] for b in self.bounds.values()))
        # The base constructor loads every file, requires the bounds on the grid and runs validate_readback /
        # validate_export (the overrides below) against the recorded reference.
        super().__init__(design_file=design_file, mapping_file=mapping_file, reference_structure=reference_structure,
                         reference_readback=reference_readback, width_bounds=overall, width_step=step,
                         conditions_file=conditions_file)
        if any(not self._on_width_grid(v) for bounds in self.bounds.values() for v in bounds):
            raise RulesError('Every width bound must lie on the width grid')
        self._bounds_to_grid_top()
        self._check_group_contract()

    # ------------------------------------------------------------------ contract between rules and mapping
    def _bounds_to_grid_top(self):
        """A group's top grid point can land a hair above an upper bound typed in decimals (compile.grid_top: 1.84 ..
        42.38 um in 0.02 um steps tops out at 4.2380000000000004e-05 m), and a task saved before compile took that point
        as the group's upper bound kept rules bounds a hair below it: the profile refused its own top value at load
        ("outside its bounds or off the CDF-compatible grid"). A member bound AT the group's upper moves to that point,
        as compile moves the group's (_to_grid_top); where the point is not above, nothing moves."""
        for group in self.graph.parameter_groups:
            top = _to_grid_top(group).upper
            for member in group.members if top > group.upper else ():
                lower, upper = self.bounds.get(member.device_id, (None, None))
                if upper is not None and group.upper * member.ratio <= upper < top * member.ratio:
                    self.bounds[member.device_id] = (lower, top * member.ratio)

    def _check_group_contract(self):
        """The mapping's mutable groups must BE the rules: widths of writable transistors only, each exactly once,
        linear on the grid, inside the bounds of every member. (The hand-written classes pin the same thing.)"""
        seen = {}
        for group in self.graph.parameter_groups:
            if not group.mutable:
                continue
            if group.scale != 'linear' or group.domain != 'continuous' or group.step is None:
                raise RulesError(f'Group {group.id} must be linear and continuous with an explicit step')
            for member in group.members:
                key = (member.device_id, member.parameter)
                if key not in self.writable_keys or key in seen or member.ratio <= 0:
                    raise RulesError(f'Group {group.id} binds {key}, which is not a writable width (or is bound twice)')
                seen[key] = group.id
                # One group step must move EVERY member by whole grid steps (a 1:4 pair needs a 20 nm group step).
                if not self._on_width_grid(group.step * member.ratio):
                    raise RulesError(f'Group {group.id}: its step does not keep {member.device_id} on the {self.width_step:g} m grid')
                lower, upper = self.bounds[member.device_id]
                # group value * ratio = member width, so the group range must map inside the member's bounds
                if group.lower * member.ratio < lower - 1e-15 or group.upper * member.ratio > upper + 1e-15:
                    raise RulesError(f'Group {group.id} lets {member.device_id} leave its bounds')
        if set(seen) != set(self.writable_keys):
            raise RulesError('Every writable width must belong to exactly one mutable group')
        for value in (-1., 0., 1.):                        # the corners and the centre of the action space are legal
            from analog_optimizer.parameters.actions import ActionMapper
            groups = [g.id for g in self.graph.parameter_groups if g.mutable]
            self.validate_assignment(ActionMapper(self.graph).legalize({k: value for k in groups}).assignments)

    # ------------------------------------------------------------------ what the adapter calls
    def validate_condition(self, condition):
        super().validate_condition(condition)
        if not condition.nominal_only or condition.corner != self.nominal_corner:
            raise UnsupportedCapability('A generated profile supports its nominal condition only')

    def build_deck(self, structure, model_file, section='tt', *, temperature_c=27.):
        """The adapter's own deck (`virtuoso_bridge.build_deck`, which the adapter used before this method existed), with
        a run's trimmed model library in place of its model include (record 7.154)."""
        from analog_optimizer.backends.virtuoso_bridge import build_deck
        return model_library.apply(build_deck(structure, model_file, section, temperature_c=temperature_c),
                                   model_file, section, getattr(self, 'model_library', None))

    def assignments(self, values=None):
        """{group id: value} -> {(device, 'w'): width}; the recorded sizes when nothing is given."""
        graph = deepcopy(self.graph)
        chosen = {g.id: g.value for g in graph.parameter_groups if g.mutable}
        chosen.update(values or {})
        result = graph.assignments(chosen)
        self.validate_assignment(result)
        return result

    def validate_assignment(self, parameters):
        if set(parameters) != set(self.writable_keys):
            raise ValueError('A complete assignment of every writable width is required')
        for (device, _), value in parameters.items():
            lower, upper = self.bounds[device]
            if (isinstance(value, bool) or not math.isfinite(value) or not lower <= value <= upper
                    or not self._on_width_grid(value)):
                raise ValueError(f'Width of {device} outside its bounds or off the CDF-compatible grid')
        for group in self.graph.parameter_groups:          # members of one group keep their recorded ratio
            if group.mutable:
                if any((m.device_id, m.parameter) not in parameters for m in group.members):
                    raise RulesError(f'Group {group.id} of the mapping moves a parameter that the rules do not make writable')
                shared = [parameters[m.device_id, m.parameter] / m.ratio for m in group.members]
                if any(not equal(shared[0], other) for other in shared[1:]):
                    raise ValueError(f'Group {group.id}: matched widths / fixed ratio violated')

    def optimization_graph(self, structure=None):
        graph = self.parser.parse_file(structure) if structure is not None else deepcopy(self.graph)
        # The groups a run gets are the ones compile makes from the task's rows, also from a mapping saved before compile
        # took a group's top grid point as its upper bound: otherwise such a task's own rows no longer matched it at Start.
        graph.parameter_groups = [_to_grid_top(group) for group in graph.parameter_groups]
        graph.validate()
        self.validate_assignment(graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable}))
        return graph

    def validate_readback(self, snapshot):
        actual, reference = self.instances(snapshot), self.instances(self.reference)
        if set(actual) != set(reference) or set(actual) != set(self.mos_names) | set(self.fixed_instances):
            raise ValueError('Unexpected instance set in the core cell')
        writable = {device.split('/')[1] for device, _ in self.writable_keys}
        for name, inst in actual.items():
            ref = reference[name]
            for key in ('lib', 'cell', 'view', 'terms'):
                if inst[key] != ref[key]:
                    raise ValueError(f'Unexpected {name} {key}')
            params = inst['params']
            if name in self.fixed_instances:               # not a transistor: nothing about it may change
                if params.keys() != ref['params'].keys() or any(not _same(params[k], ref['params'][k]) for k in params):
                    raise ValueError(f'Fixed instance {name} changed')
                continue
            for key in MOS_FIXED + (() if name in writable else MOS_SIZE):
                if not equal(number(params[key]), number(ref['params'][key])):
                    raise ValueError(f'Unexpected fixed parameter {name}.{key}')
            if not equal(number(params['w']), number(params['fw'])):
                raise ValueError(f'Stale finger width on {name}')
            if any(number(params[key]) <= 0 for key in GEOMETRY):
                raise ValueError(f'Invalid derived geometry on {name}')
        result = {(device, key): number(actual[device.split('/')[1]]['params'][key]) for device, key in self.writable_keys}
        self.validate_assignment(result)
        return result

    def verify_transition(self, before, after, expected):
        actual = self.validate_readback(after)
        if any(not equal(actual[k], v) for k, v in expected.items()):
            raise ValueError('CDF width readback differs from requested values')
        old, new = self.instances(before), self.instances(after)
        for device, _ in self.writable_keys:
            name = device.split('/')[1]
            a, b = old[name]['params'], new[name]['params']
            if not equal(number(a['w']), number(b['w'])):
                for key in ('ad', 'as', 'pd', 'ps', 'nrd', 'nrs'):
                    if equal(number(a[key]), number(b[key])):
                        raise ValueError(f'Stale derived geometry {name}.{key}')

    def _exported_graph(self, structure):
        """The exported netlist's graph, refused unless its topology is the recorded reference's."""
        graph = self.parser.parse_file(structure)
        graph.validate()

        def topology(g):
            return (sorted((d.id, d.model_ref, d.terminals) for d in g.devices),
                    sorted((c.device_id, c.terminal, c.net_id) for c in g.connections))
        if topology(graph) != topology(self.graph):
            raise ValueError('Exported topology differs from the recorded reference')
        return graph

    def validate_export(self, structure, snapshot):
        graph = self._exported_graph(structure)
        actual = self.instances(snapshot)
        writable = {device for device, _ in self.writable_keys}
        for device, params in graph.parameters.items():
            ref = self.graph.parameters[device]
            if params.keys() != ref.keys():
                raise ValueError(f'Exported parameter set changed on {device}')
            for key, param in params.items():
                if device in writable and key in ('w',) + GEOMETRY:
                    same = param.valid and equal(param.value, number(actual[device.split('/')[1]]['params'][key]))
                elif param.valid and ref[key].valid:
                    same = equal(param.value, ref[key].value)
                else:
                    same = param.raw == ref[key].raw
                if not same:
                    raise ValueError(f'Exported parameter mismatch: {device}.{key}')
        return self.validate_readback(snapshot)


def check_writable_record(reference, names):
    """`set_gpdk_mos` rewrites fingers and m to 1 on every write: a writable transistor must be recorded that way."""
    instances = {item['name']: item for item in reference['instances']}
    for name in names:
        params = (instances.get(name) or {}).get('params') or {}
        for key in ('fingers', 'm'):
            if key not in params or not equal(number(params[key]), 1.0):
                raise RulesError(f'{name} has {key}={params.get(key)!r}: the write path sets {key}=1, so only single-finger, '
                                 'm=1 transistors can be sized')
