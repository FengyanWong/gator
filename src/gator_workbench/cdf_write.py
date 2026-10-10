"""Real runs that change any parameter the PDK's property form lets a user type - not only transistor widths (user
request 2026-09-22: "after reading the PDK file, it should be allowing me to change any parameters allowed in the cdf
process") - without a change under ``src/analog_optimizer``.

What the form does when a user types a value, and what this writer therefore does (``write_skill``): the cell is opened
by library and name (never through a window); for an instance with a value to change, its CDF data is taken, the cell's
form-init procedure runs (GPDK045: ``PasCdfFormInit``), and for every value: the form's own rule that it may be typed
now is checked, the value is set, and that field's callback runs (``gpdk045_mosCB('w)`` ...), recomputing what depends
on it. A callback can move another field - GPDK045 folds a wide transistor into more fingers when its total width is
typed - so the values the task keeps as recorded ("held", ``cdf_rules``) are part of the round too, and the round is
repeated until every requested and every held value reads back as it should: at most three rounds, else the write
stops and names the value that would not hold. Then the form's done procedure (``PasCdfDone``), ``schCheck`` and one
``dbSave`` for the whole candidate. An instance whose values are all as asked is not touched at all.

A rule is one of: always / an expression over the instance's own values (``cdfgData->calcParam->value != "width"``:
evaluated, and "no" stops the write) / a PDK function only the open form can decide (``gpdk045_mosEditable`` reads the
form's widgets and fails without them): trusted as the form would be, which is what the verified width writer
(``backends.gpdk045.set_gpdk_mos``) has always relied on; the callback and the strict read-back decide.

Where it plugs in: the run adapter ``VirtuosoBridgeBackend`` leaves every check to the circuit's profile and has two
transistor-specific methods, ``_write_widths`` and ``_verify_restored``; ``CdfBridgeBackend`` overrides exactly those.
``CdfWritableProfile`` is the profile of a rules file of format 2 (``cdf_rules.rules_v2``) with the checks of
``GenericMosWidthProfile`` generalized: an instance that is not written stays exactly as recorded; a written one may
change what its callbacks compute, never a mode or a held value; the exported netlist keeps the topology and carries,
for every written parameter, the value the CDF reads back. The recipe classes combine with it unchanged (their deck and
measurement stay theirs). ``CdfNativeEnvironmentFactory`` (in ``cdf_factory``, so that this module does not import
torch) starts the preparation service - the one owner of the Virtuoso session - with the CDF backend; the Spectre lanes
are unchanged. ``backend_class`` / ``factory_class`` pick the class for a profile, so the check before a run, the
corner check and the run itself agree.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from analog_optimizer.backends.gpdk045 import GEOMETRY, Gpdk045OtaProfile, equal, number
from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend

from .cdf_rules import RULES_FORMAT
from .generic_profile import GenericMosWidthProfile, RulesError, same_value
from .names import CADENCE_NAME
from .recipes import GenericMaestroProfile, GenericRingOscillatorProfile, MAESTRO, RING
from .schematic_read import read_cell
from .security import skill_string as _skill_string
from .storage.atomic import read_json_quiet

NAME = re.compile(CADENCE_NAME)       # library / cell / instance, as everywhere in the workbench
FIELD = re.compile(r'^[A-Za-z_]\w{0,63}$')                        # a CDF parameter (form field)
PROC = re.compile(r'^[A-Za-z_]\w{0,127}$')                        # a form procedure
KINDS = ('string', 'int', 'float', 'choice')                      # how a number is held in the CDF
PASSES = 3
CONTRACT_BOUNDS, CONTRACT_STEP = (5e-9, 1.0), 5e-9                 # fields of the package's profile contract only
STALE = ('ad', 'as', 'pd', 'ps', 'nrd', 'nrs')                    # what a transistor's width callback must recompute


def _whole(value):
    return math.isfinite(value) and math.isclose(value, round(value), rel_tol=0, abs_tol=1e-7)


def _num(value):
    try:
        return number(value)
    except Exception:
        return None


# ------------------------------------------------------------------------------------------ one form field
@dataclass(frozen=True)
class Field:
    """One form field the writer sets: on `instance` (a direct instance of the core cell), CDF parameter `cdf`."""
    instance: str
    cdf: str
    kind: str                     # string | int | float | choice
    rule: object                  # True | the form's SKILL expression for "may be typed now"
    callback: str | None
    choices: tuple | None = None

    def check(self, where):
        if not NAME.match(self.instance or '') or not FIELD.match(self.cdf or ''):
            raise RulesError(f'{where}: invalid instance or form field name')
        if self.kind not in KINDS:
            raise RulesError(f'{where}: unknown value kind {self.kind!r}')
        if not (self.rule is True or isinstance(self.rule, str)):
            raise RulesError(f'{where}: a field the form never lets you type cannot be written')
        if self.callback is not None and not isinstance(self.callback, str):
            raise RulesError(f'{where}: invalid callback')
        if self.kind == 'choice' and not (self.choices and all(_num(c) is not None for c in self.choices)):
            raise RulesError(f'{where}: a choice list of numbers is required')

    @property
    def name(self):
        return f'{self.instance}.{self.cdf}'

    def choice(self, value):
        return next((c for c in self.choices or () if equal(_num(c), value)), None)

    def literal(self, value) -> str:
        """The value as SKILL writes it into this field."""
        if self.kind == 'choice':
            chosen = self.choice(value)
            if chosen is None:
                raise ValueError(f'{self.name}: {value!r} is none of the choices {list(self.choices)}')
            return _skill_string(chosen)
        if self.kind == 'int':
            return str(int(round(value)))
        if self.kind == 'float':
            return repr(float(value))
        return _skill_string(format(float(value), '.12g'))

    def holds(self, value) -> str:
        """A SKILL test that the instance holds `value` in this field now."""
        held = f'cdfgData~>{self.cdf}~>value'
        if self.kind == 'choice':
            return f'equal({held} {self.literal(value)})'
        if self.kind == 'int':
            return f'equal({held} {int(round(value))})'
        if self.kind == 'float':
            return f'funcall(same {held} {float(value)!r})'
        return f'funcall(same cdfParseFloatString(or({held} "")) {float(value)!r})'


@dataclass(frozen=True)
class Write:
    """One parameter a run may change: the netlist parameter the optimizer varies and the form field typed for it."""
    device: str
    parameter: str
    field: Field
    lower: float
    upper: float
    step: float | None = None
    integer: bool = False
    unit: str | None = None
    grid: float | None = None     # what the PDK itself works on (5 nm, fingers x 5 nm, 1, a choice spacing)

    def check(self):
        self.field.check(f'{self.device}.{self.parameter}')
        if self.grid is not None and (not math.isfinite(self.grid) or self.grid <= 0):
            raise RulesError(f'{self.device}.{self.parameter}: invalid grid')
        if self.grid is not None and self.step is not None and not _whole(self.step / self.grid):
            raise RulesError(f'{self.device}.{self.parameter}: its step {self.step:g} is not a multiple of the {self.grid:g} grid')
        if self.grid is not None and self.field.kind != 'choice' and not (_whole(self.lower / self.grid) and _whole(self.upper / self.grid)):
            raise RulesError(f'{self.device}.{self.parameter}: its bounds are off the {self.grid:g} grid')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (self.lower, self.upper)) \
                or not self.lower < self.upper:
            raise RulesError(f'{self.device}.{self.parameter}: invalid bounds')
        if self.step is not None and (not math.isfinite(self.step) or self.step <= 0):
            raise RulesError(f'{self.device}.{self.parameter}: invalid step')
        return self

    def legal(self, value) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        span = 1e-12 * max(abs(self.lower), abs(self.upper)) + 1e-30
        if not self.lower - span <= value <= self.upper + span:
            return False
        if self.field.kind == 'choice' and self.field.choice(value) is None:
            return False
        if self.integer and not math.isclose(value, round(value), rel_tol=0, abs_tol=1e-9):
            return False
        if self.step is not None:
            k = (value - self.lower) / self.step
            if not math.isclose(k, round(k), rel_tol=0, abs_tol=1e-7):
                return False
        return True


@dataclass(frozen=True)
class Held:
    """A value of a written instance a user could type that the task keeps as recorded (put back if a callback moves
    it; `value` None = not a number: compared, never put back). `parameter`: its name in the circuit graph, None when
    the netlist leaves it out."""
    device: str
    parameter: str | None
    field: Field
    value: float | None


# ------------------------------------------------------------------------------------------ the SKILL of one candidate
def write_skill(library, cell, plan) -> str | None:
    """The whole candidate as ONE SKILL transaction. plan = [dict(instance, form=dict(init, done), targets=[(Field, value)])]
    in a fixed order. None when there is nothing to write. Every name has passed NAME / FIELD / PROC; a rule or callback
    is the PDK's own text, handed to `errsetstring` as a string literal."""
    for value in (library, cell):
        if not NAME.match(value or ''):
            raise ValueError('library and cell must be plain Cadence names')
    blocks = []
    for item in plan:
        # A length before everything else of its instance: GPDK045's width callback computes the well-proximity values
        # (sca/scb/scc) from the length the transistor has AT THAT MOMENT and the length callback leaves them alone, so a
        # width typed before its length kept the previous length's values, in every candidate and in the restoration (MScR
        # ring, 2026-09-30). Stable, so held values stay after what they correct.
        targets = sorted(item['targets'], key=lambda target: target[0].cdf != 'l')
        if not targets:
            continue
        name, form = item['instance'], item.get('form') or {}
        init, done = form.get('init') or None, form.get('done') or None      # '' = the form has no such procedure (a second foundry PDK's CDF, 2026-10-09)
        for proc in (init, done):
            if proc is not None and not PROC.match(proc):
                raise ValueError(f'{name}: invalid form procedure {proc!r}')
        for field, _ in targets:
            if not NAME.match(field.instance or '') or not FIELD.match(field.cdf or '') or field.instance != name:
                raise ValueError(f'{name}: invalid form field {field.name}')
        lines = [f'inst = car(setof(x cv~>instances x~>name == {_skill_string(name)}))',
                 f'unless(inst error("%s" {_skill_string(f"instance {name} not found")}))',
                 'cdfgData = cdfGetInstCDF(inst)', 'cdfgForm = nil',
                 f'unless(cdfgData error("%s" {_skill_string(f"{name} has no CDF")}))']
        steps = []
        if init:
            steps += [f'unless(cdfgData~>formInitProc == {_skill_string(init)} '
                      f'error("%s" {_skill_string(f"{name}: its form no longer starts with {init}")}))',
                      f'funcall(stringToSymbol({_skill_string(init)}) cdfgData)']
        else:      # none: nil, or the empty string a PDK may state (a second foundry PDK: formInitProc = "", which SKILL takes as true)
            steps.append(f'when(and(cdfgData~>formInitProc cdfgData~>formInitProc != "") '
                         f'error("%s" {_skill_string(f"{name}: its form has an init procedure now")}))')
        # ... and its width typed again, at its own value, in a round that typed the length: only the width, finger width
        # and finger count callbacks recompute those values, so a task that writes lengths and holds the widths (the MScR
        # OTA7T, the LDO pass device) ran every candidate with the build's values (MScR session, 2026-09-30).
        retype = any(field.cdf == 'l' for field, _ in targets) and any(field.cdf == 'w' for field, _ in targets)
        rounds = []
        for field, value in targets:
            one = []
            if isinstance(field.rule, str):
                one += [f'rule = errsetstring({_skill_string(field.rule)})',
                        f'when(and(rule !car(rule)) error("%s" {_skill_string(f"{field.name} cannot be typed in the form now (its rule: {field.rule})")}))']
            one.append(f'cdfgData~>{field.cdf}~>value = {field.literal(value)}')
            if field.callback and field.callback.strip() not in ('', 'nil'):
                one.append(f'unless(errsetstring({_skill_string(field.callback)}) '
                           f'error("%s" {_skill_string(f"the callback of {field.name} failed: {field.callback}")}))')
            if retype and field.cdf in ('l', 'w'):
                one.append('lengthTyped = ' + ('t' if field.cdf == 'l' else 'nil'))
            one.append('unsettled = t')
            test = f'and({field.holds(value)} !lengthTyped)' if retype and field.cdf == 'w' else field.holds(value)
            rounds.append(f'unless({test}\n          ' + '\n          '.join(one) + ')')
        steps += ['lengthTyped = nil', 'unsettled = t', 'rounds = 0', f'while(and(unsettled rounds < {PASSES})',
                  '  rounds = rounds + 1', '  unsettled = nil', '  ' + '\n        '.join(rounds) + ')']
        for field, value in targets:
            steps.append(f'unless({field.holds(value)} error("%s" {_skill_string(f"{field.name} did not keep the value {value:.12g} after the PDK callbacks")}))')
        if done:
            steps += [f'unless(cdfgData~>doneProc == {_skill_string(done)} '
                      f'error("%s" {_skill_string(f"{name}: its form no longer ends with {done}")}))',
                      f'funcall(stringToSymbol({_skill_string(done)}) inst)']
        else:      # none: nil or "" (as for the init procedure above)
            steps.append(f'when(and(cdfgData~>doneProc cdfgData~>doneProc != "") '
                         f'error("%s" {_skill_string(f"{name}: its form has a done procedure now")}))')
        steps.append('changed = t')
        pending = ' '.join(f'!{field.holds(value)}' for field, value in targets)
        lines.append(f'when(or({pending})\n      ' + '\n      '.join(steps) + ')')
        blocks.append('\n    '.join(lines))
    if not blocks:
        return None
    return ('let((cv inst cdfgData cdfgForm rule unsettled rounds same changed lengthTyped)\n'
            '  same = lambda((have want) and(numberp(have) abs(have - want) <= 1.0e-9 * abs(want) + 1.0e-30))\n'
            '  changed = nil\n'
            f'  cv = dbOpenCellViewByType({_skill_string(library)} {_skill_string(cell)} "schematic" "schematic" "a")\n'
            '  unwindProtect(progn(\n'
            '    unless(cv error("%s" "cannot open the cell for writing"))\n'
            # A cellview that a Virtuoso window holds with UNSAVED edits would have those edits saved by this write's own
            # dbSave, and an aborted write could not be thrown away by closing it (dbClose only drops one open count).
            # Refuse before anything is set (review of 2026-09-23).
            '    when(cv~>modifiedButNotSaved error("%s" "the cell has unsaved edits in a Virtuoso window: save or '
            'discard them there, then start again"))\n    '
            + '\n    '.join(blocks) +
            '\n    when(changed\n      schCheck(cv)\n      unless(dbSave(cv) error("%s" "Save failed")))\n    t\n'
            '  ) when(cv dbClose(cv))))')


# ------------------------------------------------------------------------------------------ the profile
class CdfWritableProfile(GenericMosWidthProfile):
    """The profile of a rules file of format 2: any parameter the form lets a user type, with the checks of
    `GenericMosWidthProfile` generalized. Combined with a recipe class the recipe's deck and measurement stay its own."""

    def __init__(self, *, rules_file, design_file, mapping_file, reference_structure, reference_readback,
                 conditions_file=None):
        rules = json.loads(Path(rules_file).read_text())
        if rules.get('format') != RULES_FORMAT:
            raise RulesError(f'Unknown rules format {rules.get("format")!r}')
        if rules.get('recipe', 'opamp_ac') != self.recipe:
            raise RulesError(f'These rules ask for the {rules.get("recipe")!r} recipe; this class provides {self.recipe!r}')
        core = rules.get('core_instance')
        if not isinstance(core, str) or not NAME.match(core):
            raise RulesError('core_instance must name the instance of the core cell in the testbench (e.g. "XU1")')
        self.rules, self.core_instance = rules, core
        self.instance_cells = {str(k): v for k, v in (rules.get('instances') or {}).items()}
        self.cells = dict(rules.get('cells') or {})

        def field(item):
            return Field(item['instance'], item['cdf'], item['kind'], item['rule'], item.get('callback'),
                         tuple(item['choices']) if item.get('choices') else None)
        self.writes = tuple(Write(w['device'], w['parameter'], field(w), float(w['lower']), float(w['upper']),
                                  None if w.get('step') is None else float(w['step']), bool(w.get('integer')), w.get('unit'),
                                  None if w.get('grid') is None else float(w['grid'])).check()
                            for w in rules.get('writes') or ())
        if not self.writes:
            raise RulesError('The rules name no parameter that may change')
        self.held = tuple(Held(h['device'], h.get('parameter'), field(h),
                               None if h.get('value') is None else float(h['value'])) for h in rules.get('held') or ())
        self.derived = {(d['device'], d['parameter']): (d['instance'], d['cdf']) for d in rules.get('derived') or ()}
        for h in self.held:
            if h.value is not None:
                h.field.check(f'{h.device} ({h.field.cdf})')
        self.writable_keys = tuple((w.device, w.parameter) for w in self.writes)
        if len(set(self.writable_keys)) != len(self.writable_keys):
            raise RulesError('A parameter is written twice')
        fields = [(w.field.instance, w.field.cdf) for w in self.writes] + [(h.field.instance, h.field.cdf) for h in self.held]
        if len(set(fields)) != len(fields):
            raise RulesError('A form field is written twice, or both written and held')
        for w in self.writes:
            parts = w.device.split('/')
            if parts[0] != core or len(parts) not in (2, 3) or parts[1] != w.field.instance:
                raise RulesError(f'{w.device}: only instances directly inside the core cell (or the one primitive their cell places) can be written')
            if w.field.instance not in self.instance_cells:
                raise RulesError(f'{w.device}: {w.field.instance} is not among the instances of the core cell')
        self.written_instances = tuple(sorted({w.field.instance for w in self.writes}))
        self.mos_names = tuple(rules.get('mos_instances') or ())     # the adapter reads operating points of these
        self.fixed_instances = tuple(sorted(set(self.instance_cells) - set(self.written_instances)))
        self.bounds = {w.device: (w.lower, w.upper) for w in self.writes}
        self.deck_name = rules.get('deck_name') or 'circuit.scs'
        # The package's profile: files, parser, reference graph, conditions - and it runs validate_readback /
        # validate_export (below) on the recorded reference. Its width bounds are fields of the profile contract only.
        Gpdk045OtaProfile.__init__(self, design_file=design_file, mapping_file=mapping_file,
                                   reference_structure=reference_structure, reference_readback=reference_readback,
                                   width_bounds=CONTRACT_BOUNDS, width_step=CONTRACT_STEP, conditions_file=conditions_file)
        self._check_group_contract()
        self.pdk_quirks = pdk_quirks(self.design.get('pdk_library'))
        if self.pdk_quirks.get('netlist_from_readback') is False:
            # No netlist built from the readback for a cell of a PDK whose local quirks say so (2026-10-10, a second foundry
            # PDK): its netlister re-spells typed transistor and MIM values (47.8050u for the form's 47.805u) and prints a
            # changed poly resistor's length in a form this code does not reproduce (375.535000000u for 375.535u), so the
            # comparison of record 7.142 stopped every run at its first candidate. Without render_export every candidate is
            # exported natively, unchecked by text (the native export is the netlist simulated) - whoever starts the run.
            self.render_export = None

    # ------------------------------------------------------------------ rules <-> mapping
    def _write(self, key):
        return self.writes[self.writable_keys.index(key)]

    def _check_group_contract(self):
        seen = {}
        for group in self.graph.parameter_groups:
            if not group.mutable:
                continue
            for member in group.members:
                key = (member.device_id, member.parameter)
                if key not in self.writable_keys or key in seen or member.ratio <= 0:
                    raise RulesError(f'Group {group.id} binds {key}, which the rules do not make writable (or twice)')
                seen[key] = group.id
                write = self._write(key)
                span = 1e-12 * max(abs(write.lower), abs(write.upper)) + 1e-30
                if group.lower * member.ratio < write.lower - span or group.upper * member.ratio > write.upper + span:
                    raise RulesError(f'Group {group.id} lets {write.field.name} leave its bounds')
                if write.step is not None and (group.step is None or not math.isclose(
                        group.step * member.ratio / write.step, round(group.step * member.ratio / write.step), rel_tol=0, abs_tol=1e-7)):
                    raise RulesError(f'Group {group.id}: its step does not keep {write.field.name} on its grid')
                if write.field.kind == 'choice':
                    count = int(round((group.upper - group.lower) / group.step)) + 1 if group.step else 0
                    if not 2 <= count <= 10000 or any(not write.legal((group.lower + k * group.step) * member.ratio) for k in range(count)):
                        raise RulesError(f'Group {group.id}: every value of it must be one of the choices of {write.field.name}')
        if set(seen) != set(self.writable_keys):
            raise RulesError('Every writable parameter must belong to exactly one mutable group')
        from analog_optimizer.parameters.actions import ActionMapper
        groups = [g.id for g in self.graph.parameter_groups if g.mutable]
        for value in (-1., -.5, 0., .5, 1.):               # the corners and inner points of the action space are legal
            self.validate_assignment(ActionMapper(self.graph).legalize({k: value for k in groups}).assignments)

    # ------------------------------------------------------------------ what the adapter calls
    def validate_assignment(self, parameters):
        if set(parameters) != set(self.writable_keys):
            raise ValueError('A complete assignment of every writable parameter is required')
        for key, value in parameters.items():
            write = self._write(key)
            if not write.legal(value):
                raise ValueError(f'{write.field.name} = {value!r} is outside its bounds, off its grid or none of its choices')
        for group in self.graph.parameter_groups:
            if group.mutable:
                shared = [parameters[m.device_id, m.parameter] / m.ratio for m in group.members]
                if any(not equal(shared[0], other) for other in shared[1:]):
                    raise ValueError(f'Group {group.id}: members no longer keep their fixed ratio')

    def cdf_plan(self, parameters):
        """{(device, parameter): value} -> the writer's plan: per written instance its requested and its held values."""
        order, plan = [], {}
        for w in self.writes:
            name = w.field.instance
            if name not in plan:
                order.append(name)
                cell = self.instance_cells.get(name)
                plan[name] = dict(instance=name, form=(self.cells.get(cell) or {}).get('form') or {}, targets=[])
            plan[name]['targets'].append((w.field, parameters[w.device, w.parameter]))
        for h in self.held:
            if h.value is not None and h.field.instance in plan:
                plan[h.field.instance]['targets'].append((h.field, h.value))
        return [plan[name] for name in order]

    def _internal(self, name):
        return set((self.cells.get(self.instance_cells.get(name)) or {}).get('internal') or ())

    def _differences(self, name, a, b, keys=None, *, skip_internal=True):
        """The fields of instance `name` that differ between two readbacks. The form's own bookkeeping (fields it never
        shows) is left out where the form ran; an instance that is never opened is compared field for field."""
        keys = (set(a) | set(b)) if keys is None else set(keys)
        return sorted(k for k in keys - (self._internal(name) if skip_internal else set()) if not same_value(a.get(k), b.get(k)))

    def validate_readback(self, snapshot):
        actual, reference = self.instances(snapshot), self.instances(self.reference)
        if set(actual) != set(reference) or set(actual) != set(self.instance_cells):
            raise ValueError('Unexpected instance set in the core cell')
        written = set(self.written_instances)
        held = {}
        for h in self.held:
            held.setdefault(h.field.instance, []).append(h.field.cdf)
        written_fields = {(w.field.instance, w.field.cdf) for w in self.writes}
        for name, inst in actual.items():
            ref = reference[name]
            for key in ('lib', 'cell', 'view', 'terms'):
                if inst[key] != ref[key]:
                    raise ValueError(f'Unexpected {name} {key}')
            params, before = inst['params'], ref['params']
            if name not in written:                       # nothing about an instance that is not written may change
                changed = self._differences(name, params, before, skip_internal=False)
                if changed:
                    raise ValueError(f'Fixed instance {name} changed: {", ".join(changed)}')
                continue
            modes = [k for k in (self.cells.get(inst['cell']) or {}).get('modes') or () if (name, k) not in written_fields]
            changed = self._differences(name, params, before, modes)
            if changed:
                raise ValueError(f'The setting(s) {", ".join(changed)} of {name} changed')
            changed = self._differences(name, params, before, held.get(name, ()))
            if changed:
                raise ValueError(f'{name}: {", ".join(changed)} must stay as recorded, and changed')
            if {'w', 'fw', 'fingers'} <= set(params):     # a transistor's form: total width = fingers x finger width
                w, fw, fingers = (_num(params[k]) for k in ('w', 'fw', 'fingers'))
                if None in (w, fw, fingers) or not equal(w, fw * fingers):
                    raise ValueError(f'Stale finger width on {name}')
                if any((_num(params[k]) or 0) <= 0 for k in GEOMETRY if k in params):
                    raise ValueError(f'Invalid derived geometry on {name}')
        result = {}
        for w in self.writes:
            value = _num(actual[w.field.instance]['params'].get(w.field.cdf))
            if value is None:
                raise ValueError(f'{w.field.name} could not be read back')
            result[w.device, w.parameter] = value
        self.validate_assignment(result)
        return result

    def verify_transition(self, before, after, expected):
        actual = self.validate_readback(after)
        for key, value in expected.items():
            if not equal(actual[key], value):
                raise ValueError(f'{self._write(key).field.name} reads back {actual[key]:.12g}, not the requested {value:.12g}')
        old, new = self.instances(before), self.instances(after)
        for name in self.written_instances:
            a, b = old[name]['params'], new[name]['params']
            if {'w', 'fw', 'fingers'} <= set(a) and not equal(_num(a['w']), _num(b['w'])):
                for key in STALE:
                    if key in a and key in b and same_value(a[key], b[key]):
                        raise ValueError(f'Stale derived geometry {name}.{key}')

    def compare_written(self, snapshot, reference):
        """Every field of every written instance as in `reference` (restoration, and the live cell at connect)."""
        a, b = self.instances(snapshot), self.instances(reference)
        for name in self.written_instances:
            changed = self._differences(name, a[name]['params'], b[name]['params'])
            if changed:
                raise RuntimeError(f'Restoration mismatch: {name}.{changed[0]}')

    def validate_export(self, structure, snapshot):
        graph = self._exported_graph(structure)
        read = self.validate_readback(snapshot)
        actual = self.instances(snapshot)
        for device, params in graph.parameters.items():
            ref = self.graph.parameters[device]
            if params.keys() != ref.keys():
                raise ValueError(f'Exported parameter set changed on {device}')
            for key, param in params.items():
                if (device, key) in read:                  # written: exactly the value the form reads back
                    if not (param.valid and equal(param.value, read[device, key])):
                        raise ValueError(f'Exported {device}.{key} = {param.raw} is not the value the form reads back')
                    continue
                if (device, key) in self.derived:          # computed by a callback: what the form holds now
                    instance, cdf = self.derived[device, key]
                    if not same_value(param.raw, actual[instance]['params'].get(cdf)):
                        raise ValueError(f'Exported {device}.{key} = {param.raw} is not what the form computed '
                                         f'({instance}.{cdf} = {actual[instance]["params"].get(cdf)!r})')
                    continue
                same = equal(param.value, ref[key].value) if param.valid and ref[key].valid else param.raw == ref[key].raw
                if not same:                               # held, and everything else: exactly as recorded
                    raise ValueError(f'Exported parameter mismatch: {device}.{key}')
        return read

    def netlister_spelling(self, instance, cdf, text):
        """What the netlister prints for the form's text of a DERIVED (callback-computed) value. GPDK045's netlister prints
        the text as it is. Another netlister (a second foundry PDK's; its local quirks state `derived_value_spelling:
        "significant_digits"`) re-spells an SI-suffixed number with as many decimals
        as the text has significant digits minus one, which appends a zero for every integer digit beyond the first:
        ps=10.960u for the form's 10.96u, 20.74420u for 20.7442u; one-digit mantissas, exponent forms and typed values come
        out as written. Read off the exports of the four agenticsizing cells on 2026-10-09 (114 derived values, every one)."""
        if self.pdk_quirks.get('derived_value_spelling') != 'significant_digits' or (instance, cdf) not in self._derived_slots:
            return text
        return significant_digit_spelling(text)

    @property
    def _derived_slots(self):
        return {(instance, cdf) for (_, _), (instance, cdf) in self.derived.items()}

    def render_export(self, template, snapshot):
        """The export `snapshot` would give, built without Virtuoso from `template`, an export of this cell (record 7.140).
        The values a run changes - the written parameters and those the PDK callbacks derive - are the form's own text in
        `snapshot`, bracketed as in the template; every other value stays as the template has it, which `validate_export`
        holds to the record. A written parameter takes the form field of its own name when the instance has one (the
        netlister writes the total width `w`, not the finger width it may be typed as), else the field it is typed in.
        The statements of a candidate's native export differ from each other only in these values (7.138)."""
        actual = self.instances(snapshot)
        slots = {(w.field.instance, w.parameter): w.parameter if w.parameter in actual[w.field.instance]['params'] else w.field.cdf
                 for w in self.writes}
        slots.update({(instance, key): cdf for (_, key), (instance, cdf) in self.derived.items()})
        core, inside, continued, name, out = self.design['core_cell'], False, False, None, []
        for line in template.splitlines(keepends=True):
            words = line.split()
            if not continued:                              # a new statement: its first word names it
                if words[:2] == ['subckt', core]:
                    inside = True
                elif words[:1] == ['ends']:
                    inside = False
                name = words[0] if inside and words else None
            if name in actual:
                def put(match, name=name):
                    key, value = match.group(1), match.group(2)
                    cdf = slots.get((name, key))
                    text = actual[name]['params'].get(cdf) if cdf else None
                    if text is None:
                        return match.group(0)
                    text = self.netlister_spelling(name, cdf, text)
                    return f'{key}=({text})' if value.startswith('(') else f'{key}={text}'
                line = re.sub(r'\b(\w+)=(\([^)]*\)|[^\s\\()]+)', put, line)
            continued = line.rstrip().endswith('\\')
            out.append(line)
        return ''.join(out)


_SI_TEXT = re.compile(r'^([-+]?)(\d+)(?:\.(\d+))?([TGMKkmunpfa])$')


PDK_QUIRKS_FILE = 'quirks.json'


def pdk_quirks(technology_library) -> dict:
    """What a run has to know about one PDK that neither its CDF nor its loaded record says, from the PDK's own folder in
    the local settings (`pdks/<technology library>/quirks.json`: git-ignored, never in the repository); {} when the PDK has
    none. `netlist_from_readback: false` - no netlist is built from the readback, every candidate is exported natively;
    `derived_value_spelling: "significant_digits"` - how its netlister prints a callback-computed value. Without the file
    a cell of such a PDK stops at its first candidate on the netlist comparison: loudly, never with a wrong netlist."""
    from .pdk_record import PdkError, pdk_dir                # the PDK store knows nothing of the writer
    try:
        data = read_json_quiet(pdk_dir(technology_library) / PDK_QUIRKS_FILE, None)
    except PdkError:
        return {}
    return data if isinstance(data, dict) else {}


def significant_digit_spelling(text) -> str:
    """One netlister's spelling of a derived value's SI-suffixed text (see CdfWritableProfile.netlister_spelling):
    decimals = significant digits - 1. Anything else (exponent forms, plain decimals, expressions) is returned as it is."""
    match = _SI_TEXT.match(str(text).strip())
    if not match:
        return text
    sign, whole, frac, suffix = match.groups()
    digits = (whole + (frac or '')).lstrip('0').rstrip('0')
    decimals = max(len(digits) - 1, 0)
    return f'{sign}{float(whole + "." + (frac or "0")):.{decimals}f}{suffix}'


class CdfRingOscillatorProfile(GenericRingOscillatorProfile, CdfWritableProfile):
    """The ring-oscillator deck and measurement, with rules of format 2."""


class CdfMaestroProfile(GenericMaestroProfile, CdfWritableProfile):
    """The Maestro deck and OCEAN measurement, with rules of format 2."""


PROFILE_CLASSES = {'opamp_ac': CdfWritableProfile, RING: CdfRingOscillatorProfile, MAESTRO: CdfMaestroProfile}


def rules_format(rules_file):
    return read_json_quiet(rules_file, default={}).get('format')


# ------------------------------------------------------------------------------------------ the backend and the factory
class CdfBridgeBackend(VirtuosoBridgeBackend):
    """The verified run adapter with the form writer in place of its transistor-width writer, and the cell read built once
    instead of line by line (record 7.296)."""

    def _read_snapshot(self):
        # The verified read (include_positions=True, param_filters=None), the same answer: 6 instead of 434 ms inside
        # Virtuoso on mscr_vco_lin_c, and every candidate reads the cell before and after its write (schematic_read).
        return read_cell(self.client, self.config.library, self.circuit.design['core_cell'])

    def _write_widths(self, parameters):
        skill = write_skill(self.config.library, self.circuit.design['core_cell'], self.circuit.cdf_plan(parameters))
        if skill is None:
            return
        result = self.client.execute_skill(skill, timeout=120)
        if not result.ok or (result.output or '').strip() != 't':
            raise RuntimeError('The form write failed: ' + ('; '.join(str(e) for e in result.errors or []) or str(result.output)))

    def _verify_restored(self, snapshot, reference):
        self.circuit.validate_readback(snapshot)
        self.circuit.compare_written(snapshot, reference)


def backend_class(profile):
    """The adapter class for a profile; the verified one looked up where it lives, at call time, as its callers did."""
    if isinstance(profile, CdfWritableProfile):
        return CdfBridgeBackend
    import analog_optimizer.backends.virtuoso_bridge as verified
    return verified.VirtuosoBridgeBackend


@dataclass(frozen=True)
class CdfPreparationFactory:
    config: object
    circuit: object

    def __call__(self):
        return CdfBridgeBackend(self.config, self.circuit)


@contextmanager
def preparation_session(config, circuit, limits, report):
    """`analog_optimizer.backends.native_preparation.preparation_session` with the CDF backend as the owner of the
    Virtuoso session (until 2026-10-09 a line-for-line copy of it; plan-refactoring E7)."""
    from analog_optimizer.backends.native_preparation import preparation_session as session
    with session(config, circuit, limits, report, factory=CdfPreparationFactory) as service:
        yield service


def factory_class(profile):
    if isinstance(profile, CdfWritableProfile):
        # lazy: cdf_factory imports torch: only a run needs it (see its docstring)
        from .cdf_factory import CdfNativeEnvironmentFactory
        return CdfNativeEnvironmentFactory
    import analog_optimizer.training.parallel as verified
    return verified.NativeEnvironmentFactory


def __getattr__(name):
    # The run's factory lives in cdf_factory.py: its base class imports torch, which the processes that only prepare or
    # check a cell never need (review of 2026-09-30). The old name still reaches it.
    if name == 'CdfNativeEnvironmentFactory':
        # lazy: cdf_factory imports torch: only a run needs it (see its docstring)
        from .cdf_factory import CdfNativeEnvironmentFactory
        return CdfNativeEnvironmentFactory
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
