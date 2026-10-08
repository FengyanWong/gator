"""Load ONE PDK so that the graph network understands every component in it (user request 2026-09-21).

Why this lives here and not in ``src/analog_optimizer``: the network is BUILT from a component list - device kinds,
terminal roles, parameter columns and their scales - that the package takes as an argument (``FeatureSchema``) and that
every saved model records in its contract. The package's own list (8 generic kinds, 8 parameters) is only its default.
A PDK list is therefore built here, from the PDK itself, and handed to the unchanged package: the source digest stays,
every model saved so far keeps its standard list and still loads, and the M6 audit re-runs unchanged. A model trained
with a PDK list loads only with that same list - the existing contract check says so.

What "Load PDK" reads (``bridge_read`` op ``pdk``), all read-only and at no simulation cost:

1. Virtuoso's own description of every cell of the technology library (its CDF): the Spectre name a cell netlists to,
   the pin order, the parameters written on each instance line, their declared units and defaults. A cell without a
   Spectre entry of its own (GPDK045's resistors) is looked into: its schematic places a primitive that names the model.
2. The PDK's Spectre model files, downloaded through the bridge into a temporary folder OUTSIDE the repository and
   deleted after scanning: which primitive each model is (``bsim4``, ``bjt``, ``diode``, ``resistor``...), its
   polarity, and which primitive terminal each pin reaches. PDK files are never copied; only the facts drawn from them
   and the files' SHA-256 are kept.
3. The ideal parts every circuit holds besides its PDK's - sources, ideal R / C / L, probes, controlled sources: the
   description of Cadence's generic library `analogLib`, in one more query that opens nothing (`IDEAL_SKILL`). Which
   Spectre component each of its cells netlists as, and in which pin order, is then read from Virtuoso like a PDK
   component's, not written by hand (user, 2026-10-05: "it should be recognizing all the loaded components").

Nothing is guessed from a name: a family comes from the Spectre primitive, a pin role from the primitive terminal the
pin reaches, a scale from the declared unit or else the PDK's own default value. What cannot be established stays
``unknown`` and is listed with the reason.

The component list covers the Spectre models that the library's cells netlist to. Models that no cell uses (internal
building blocks of the model files) are named in the record but not added.

How a circuit reaches the network (``Vocabulary.view``): the circuit graph of a task is left exactly as it is - the
environment, the backend, the replay and every table keep the graph the simulator saw. Only at the network's input,
each device whose Spectre model belongs to the PDK takes its PDK kind and pin roles, and its parameters are placed in
the PDK's columns. Devices outside the PDK (sources, ideal parts) keep their standard kinds.
"""
from __future__ import annotations

import hashlib
import json
import math
import posixpath
import re
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from .paths import local_settings_dir
from .storage.atomic import read_json, write_json
from .storage.dataset import utcnow

FORMAT = 'gator-pdk-1'
VOCABULARY_FORMAT = 'gator-pdk-vocabulary-1'
STANDARD = 'standard'
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$')          # a technology library name (also a folder name)
REMOTE_PATH = re.compile(r'^/[A-Za-z0-9_./+\-]{1,1000}$')           # an absolute POSIX path; no shell characters
MAX_MODEL_FILES, MAX_MODEL_BYTES = 64, 128 * 1024 * 1024

# ------------------------------------------------------------------------------------------ what the families are
# Spectre primitive -> family. Terminal order of each primitive as Spectre defines it.
PRIMITIVE_FAMILY = {
    **dict.fromkeys(('bsim3v3', 'bsim4', 'bsim6', 'bsimbulk', 'bsimsoi', 'bsimcmg', 'bsimimg', 'b3soipd', 'b4soi',
                     'psp102', 'psp103', 'psp104', 'hisim2', 'hisimhv', 'hisim_hv', 'mos1', 'mos2', 'mos3', 'mos9',
                     'mos11', 'mos902', 'mos903', 'mos1100', 'mos1101', 'ekv', 'bsim3', 'bsim4soi'), 'mos'),
    **dict.fromkeys(('bjt', 'vbic', 'hbt', 'hicum', 'hicum0', 'hicum2', 'mextram', 'bjt301', 'bjt500', 'bjt503',
                     'bjt504', 'bjt504t'), 'bjt'),
    **dict.fromkeys(('diode', 'juncap', 'juncap200', 'dio500'), 'diode'),
    'resistor': 'resistor', 'phy_res': 'resistor', 'rdiff': 'resistor',
    'capacitor': 'capacitor', 'inductor': 'inductor',
}
TERMINAL_ROLES = {'mos': ('drain', 'gate', 'source', 'bulk'), 'bjt': ('collector', 'base', 'emitter', 'bulk'),
                  'diode': ('anode', 'cathode')}
PRIMITIVE_PINS = {'mos': ('d', 'g', 's', 'b'), 'bjt': ('c', 'b', 'e', 's'), 'diode': ('a', 'c')}
PASSIVE = ('resistor', 'capacitor', 'varactor', 'inductor')
FAMILY_LABEL = {'mos': 'MOS transistor', 'bjt': 'bipolar transistor', 'diode': 'diode', 'resistor': 'resistor',
                'capacitor': 'capacitor', 'varactor': 'varactor', 'inductor': 'inductor', 'other': 'other'}

# CDF `units` names -> the workbench's canonical units (units.py), and the reference scale of each canonical unit: the
# same scale the standard list uses for a length / capacitance / resistance / inductance / voltage.
CDF_UNITS = {'lengthMetric': 'm', 'lengthEnglish': 'm', 'resistance': 'ohm', 'capacitance': 'F', 'inductance': 'H',
             'voltage': 'V', 'current': 'A', 'time': 's', 'frequency': 'Hz', 'power': 'W', 'temperature': 'degC',
             'angle': 'deg'}
UNIT_REFERENCE = {'m': 1e-6, 'F': 1e-12, 'ohm': 1e3, 'H': 1e-9, 'V': 1.0, 'A': 1e-6, 's': 1e-9, 'Hz': 1e9, 'W': 1e-3,
                  'degC': 1.0, 'deg': 1.0, 'count': 1.0}
# The optimizer can vary a group only in one of its eight standard parameter kinds, each with a fixed unit
# (analog_optimizer.models.inputs). A PDK parameter is varied in the kind of its unit: its own name stays on the binding.
ACTION_CLASS = {'m': 'l', 'count': 'm', 'ohm': 'r', 'F': 'c', 'H': 'ind', 'V': 'dc'}
SCALE_TOLERANCE_DECADES = 1.5          # two parameters of one name share a column only if their scales agree this closely
NUMERIC_CDF_TYPES = ('string', 'int', 'float')


def standard_schema():
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    return FeatureSchema()


STANDARD_UNITS = {'w': 'm', 'l': 'm', 'm': 'count', 'nf': 'count', 'r': 'ohm', 'c': 'F', 'ind': 'H', 'dc': 'V'}


# ------------------------------------------------------------------------------------------ the Virtuoso query
# One read-only call. `ddGetObj`, `cdfGetBaseCellCDF` and `cdfFindParamByName` open nothing. A cell that has no Spectre
# entry of its own is netlisted through its schematic: that schematic is opened READ-ONLY and closed again exactly as
# the bridge's own reader does (virtuoso_bridge/virtuoso/schematic/reader.py, unwindProtect + dbClose), only to see which
# primitive it places and with which model. Lines are collected in a list and joined once.
PDK_SKILL = r'''
let((lib lines cdf sp mp cv)
  lib = ddGetObj("@LIBRARY@")
  lines = nil
  when(lib
    foreach(cell lib~>cells
      cdf = cdfGetBaseCellCDF(cell)
      if(null(cdf) then
        lines = cons(sprintf(nil "NOCDF|%s|%L" cell~>name cell~>views~>name) lines)
      else
        sp = get(cdf~>simInfo 'spectre)
        mp = cdfFindParamByName(cdf "model")
        lines = cons(sprintf(nil "CELL|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name
          if(mp mp~>defValue nil) get(sp 'termOrder) get(sp 'termMapping) get(sp 'instParameters)
          get(sp 'otherParameters) get(sp 'propMapping) get(sp 'componentName) get(sp 'namePrefix)
          cell~>views~>name) lines)
        lines = cons(sprintf(nil "FORM|%s|%L|%L" cell~>name cdf~>formInitProc cdf~>doneProc) lines)
        foreach(p cdf~>parameters
          lines = cons(sprintf(nil "PARAM|%s|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name p~>name p~>paramType p~>units p~>defValue
            p~>prompt p~>editable p~>display p~>callback p~>choices p~>range) lines))
        when(and(null(sp) member("schematic" cell~>views~>name))
          cv = nil
          unwindProtect(
            progn(
              cv = dbOpenCellViewByType(lib~>name cell~>name "schematic" "schematic" "r")
              when(cv
                foreach(inst cv~>instances
                  lines = cons(sprintf(nil "LEAF|%s|%s|%s|%s|%L" cell~>name inst~>name inst~>libName inst~>cellName
                    dbGetq(inst model)) lines))))
            progn(when(cv dbClose(cv) cv = nil)))))))
  buildString(reverse(lines) "\n"))
'''


def pdk_skill(library):
    if not NAME.match(library or ''):
        raise ValueError('The technology library must be a plain Cadence name')
    return PDK_SKILL.replace('@LIBRARY@', library)


# ------------------------------------------------------------------------------------------ the ideal parts
# What a circuit holds besides its PDK's components lives in Cadence's generic library. Until record 7.190 the workbench
# knew five of those parts from definitions written by hand into the example circuits' mapping files, and lost two of
# them when the examples were deleted (record 7.187). Now the library says it itself, read with every PDK.
IDEAL_LIBRARY = 'analogLib'
IDEAL_FORMAT = 'gator-ideal-parts-1'
# The CELL / NOCDF lines of PDK_SKILL and nothing else: no parameter, no form, no schematic opened. One line per cell
# (180 in IC23.1's analogLib, 0.1 MB, about a second).
IDEAL_SKILL = r'''
let((lib lines cdf sp mp)
  lib = ddGetObj("@LIBRARY@")
  lines = nil
  when(lib
    foreach(cell lib~>cells
      cdf = cdfGetBaseCellCDF(cell)
      if(null(cdf) then
        lines = cons(sprintf(nil "NOCDF|%s|%L" cell~>name cell~>views~>name) lines)
      else
        sp = get(cdf~>simInfo 'spectre)
        mp = cdfFindParamByName(cdf "model")
        lines = cons(sprintf(nil "CELL|%s|%L|%L|%L|%L|%L|%L|%L|%L|%L" cell~>name
          if(mp mp~>defValue nil) get(sp 'termOrder) get(sp 'termMapping) get(sp 'instParameters)
          get(sp 'otherParameters) get(sp 'propMapping) get(sp 'componentName) get(sp 'namePrefix)
          cell~>views~>name) lines))))
  buildString(reverse(lines) "\n"))
'''
# The Spectre components the optimizer's standard list has a kind for, each with the one value its instance line carries
# (netlist name -> the standard parameter it is). All are two-terminal: Spectre's first node is the positive one. A
# current probe is a 0 V source in series, which is how the project's own mapping always read it. Every other component
# of the library is still read and named - pins as the library orders them - and reaches the network as "unknown", as a
# PDK's diode or bipolar does under the standard list.
MAX_IDEAL_PINS = 64             # analogLib's `nport` states 2,000 pins, `vcvsp` 42: an order longer than this is counted, not kept
IDEAL_KINDS = {'vsource': ('vsource', {'dc': 'dc'}), 'isource': ('isource', {'dc': 'dc'}), 'resistor': ('resistor', {'r': 'r'}),
               'capacitor': ('capacitor', {'c': 'c'}), 'inductor': ('inductor', {'l': 'ind'}), 'iprobe': ('vsource', {})}


def ideal_skill(library=IDEAL_LIBRARY):
    if not NAME.match(library or ''):
        raise ValueError('The library of ideal parts must be a plain Cadence name')
    return IDEAL_SKILL.replace('@LIBRARY@', library)


class PdkError(ValueError):
    """Why a PDK cannot be loaded or used, in words the page can show."""


# ------------------------------------------------------------------------------------------ SKILL output
def _fields(line):
    """Split a query line at `|`, but never inside a quoted string."""
    out, current, quoted, i = [], [], False, 0
    while i < len(line):
        char = line[i]
        if char == '\\' and quoted and i + 1 < len(line):
            current.append(line[i:i + 2])
            i += 2
            continue
        if char == '"':
            quoted = not quoted
        if char == '|' and not quoted:
            out.append(''.join(current))
            current = []
        else:
            current.append(char)
        i += 1
    out.append(''.join(current))
    return out


def skill_value(text):
    """A value printed by SKILL's %L (as the bridge returns it: its backslashes doubled once more).
    nil -> None, t -> True, "s" -> str, (a b) -> list, symbols -> str, numbers -> int/float."""
    text = (text or '').strip().replace('\\\\', '\\')
    tokens, i = [], 0
    while i < len(text):
        char = text[i]
        if char.isspace():
            i += 1
        elif char in '()':
            tokens.append(char)
            i += 1
        elif char == '"':
            j, chars = i + 1, []
            while j < len(text) and text[j] != '"':
                if text[j] == '\\' and j + 1 < len(text):
                    j += 1
                chars.append(text[j])
                j += 1
            tokens.append(('s', ''.join(chars)))
            i = j + 1
        else:
            j, chars = i, []
            while j < len(text) and not text[j].isspace() and text[j] not in '()"':
                if text[j] == '\\' and j + 1 < len(text):
                    j += 1
                chars.append(text[j])
                j += 1
            tokens.append(('a', ''.join(chars)))
            i = j

    def atom(token):
        kind, value = token
        if kind == 's':
            return value
        if value == 'nil':
            return None
        if value == 't':
            return True
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            return value

    def parse(position):
        token = tokens[position]
        if token == '(':
            items, position = [], position + 1
            while position < len(tokens) and tokens[position] != ')':
                item, position = parse(position)
                items.append(item)
            return items, position + 1
        if token == ')':
            raise ValueError('unbalanced SKILL list')
        return atom(token), position + 1
    if not tokens:
        return None
    value, _ = parse(0)
    return value


def _plist(value):
    """A SKILL disembodied property list `(nil k1 v1 k2 v2)` -> {k1: v1}. Symbols like `\\:d` arrive as ':d'."""
    if not isinstance(value, list) or not value or value[0] is not None:
        return {}
    items = value[1:]
    return {str(items[i]): items[i + 1] for i in range(0, len(items) - 1, 2)}


def _form_rule(text):
    """A CDF `editable` / `display` attribute: True (unset, or t), False (the expression nil), or the SKILL expression that
    decides it for one instance (e.g. gpdk045_mosEditable('w) or cdfgData->calcParam->value != "width")."""
    value = skill_value(text)
    if value is None or value is True or value == 't':
        return True
    if value == 'nil':
        return False
    return str(value)


def numeric_range(value):
    """A CDF `range` attribute as two numbers, or None when it is absent or not a plain numeric pair. The property form
    itself refuses a value outside it, so a task whose bounds leave it would die on its first clamped candidate."""
    if isinstance(value, str):
        value = [part for part in value.replace('(', ' ').replace(')', ' ').split() if part]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        low, high = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return [low, high] if low <= high and math.isfinite(low) and math.isfinite(high) else None


def parse_cdf_text(text):
    """The query's lines -> {cells: {name: {...}}, leaves: {cell: [{instance, library, cell, model}]}, layout_only: [..]}."""
    cells, leaves, layout_only = {}, {}, []
    lines = [_fields(raw.rstrip('\r')) for raw in (text or '').splitlines()]
    # Cells first, then what belongs to them: the order of a library's cells (and of the lines) is not guaranteed.
    for parts in sorted(lines, key=lambda parts: parts[0] != 'CELL'):
        tag = parts[0]
        if tag == 'CELL' and len(parts) >= 11:
            name = parts[1]
            spectre = dict(term_order=skill_value(parts[3]), term_mapping=_plist(skill_value(parts[4])),
                           inst_parameters=skill_value(parts[5]), other_parameters=skill_value(parts[6]),
                           prop_mapping=_plist(skill_value(parts[7])), component_name=skill_value(parts[8]),
                           name_prefix=skill_value(parts[9]))
            has_spectre = any(v for key, v in spectre.items() if key not in ('name_prefix',))
            cells[name] = dict(name=name, model=skill_value(parts[2]), spectre=spectre if has_spectre else None,
                               views=skill_value(parts[10]) or [], parameters={})
        elif tag == 'PARAM' and len(parts) >= 7 and parts[1] in cells:
            entry = dict(type=skill_value(parts[3]), units=skill_value(parts[4]), default=skill_value(parts[5]),
                         prompt=skill_value(parts[6]))
            if len(parts) >= 11:                          # how the property form treats it (Load PDK since 2026-09-22)
                entry.update(editable=_form_rule(parts[7]), display=_form_rule(parts[8]), callback=skill_value(parts[9]),
                             choices=skill_value(parts[10]))
            if len(parts) >= 12:                          # the range the form itself enforces (2026-09-23): (low high)
                entry['range'] = numeric_range(skill_value(parts[11]))
            cells[parts[1]]['parameters'][parts[2]] = entry
        elif tag == 'FORM' and len(parts) >= 4 and parts[1] in cells:
            cells[parts[1]]['form'] = dict(init=skill_value(parts[2]), done=skill_value(parts[3]))
        elif tag == 'LEAF' and len(parts) >= 6:
            leaves.setdefault(parts[1], []).append(dict(instance=parts[2], library=parts[3], cell=parts[4],
                                                         model=skill_value(parts[5])))
        elif tag == 'NOCDF' and len(parts) >= 2:
            layout_only.append(dict(cell=parts[1], views=skill_value(parts[2]) if len(parts) > 2 else []))
    return dict(cells=cells, leaves=leaves, layout_only=sorted(layout_only, key=lambda item: item['cell']))


# ------------------------------------------------------------------------------------------ Spectre model files
_ASSIGNMENT = re.compile(r'([A-Za-z_][\w.$]*)\s*=\s*')
_INCLUDE = re.compile(r'^\s*include\s+"([^"]+)"', re.I)


def _strip_comment(line):
    """Drop `// ...` outside quotes."""
    quoted = False
    for i, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == '/' and not quoted and line[i:i + 2] == '//':
            return line[:i]
    return line


def _logical_lines(text):
    """(line number, logical line): `+` continuation lines and trailing-backslash continuations joined, `//` comments and
    comment lines (`*` at the start, as in SPICE and Spectre) dropped."""
    current, start, joining = None, 0, False
    for number, physical in enumerate(text.splitlines(), 1):
        stripped = _strip_comment(physical).strip()
        if not stripped or stripped.startswith('*'):
            continue
        if current is not None and (joining or stripped.startswith('+')):
            current += ' ' + (stripped[1:] if stripped.startswith('+') else stripped)
        else:
            if current is not None:
                yield start, current
            current, start = stripped, number
        joining = current.endswith('\\')
        if joining:
            current = current[:-1].rstrip()
    if current is not None:
        yield start, current


def _assignments(text):
    """`a=1 b = 2*x c=[1 2]` -> {'a': '1', 'b': '2*x', 'c': '[1 2]'} (values as written)."""
    matches = list(_ASSIGNMENT.finditer(text))
    out = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        if value:
            out[match.group(1)] = value
    return out


def includes_of(text):
    """The files a model file includes, as written (relative to that file)."""
    return sorted({m.group(1) for line in text.splitlines() for m in [_INCLUDE.match(_strip_comment(line))] if m})


def _define(into, name, item, models, subckts, duplicates):
    """The first definition of a name wins, across models and subcircuits; a later one is listed."""
    if name in models or name in subckts:
        duplicates.append(dict(name=name, file=item['file'], line=item['line']))
    else:
        into[name] = item


def scan_model_text(text, file):
    """Top-level definitions of one Spectre model file: {'models': {name: {...}}, 'subckts': {name: {...}}}.
    Only what classifying a device needs is kept: a model's primitive and `type`; a subcircuit's pins, parameters,
    elements (name, nodes, master, which of r/c/q/l they set) and its own local models. Model parameter blocks
    `{ ... }` (binned BSIM cards, thousands of lines) are skipped except for their `type=`."""
    models, subckts, duplicates = {}, {}, []
    scope, brace, brace_model, language = None, 0, None, 'spectre'
    for number, line in _logical_lines(text):
        if brace:
            depth_change = line.count('{') - line.count('}')
            if brace_model is not None and brace_model.get('type') is None:
                found = re.search(r'\btype\s*=\s*([A-Za-z]+)', line)
                if found:
                    brace_model['type'] = found.group(1).lower()
            brace += depth_change
            if brace <= 0:
                brace, brace_model = 0, None
            continue
        normalized = re.sub(r'\s*=\s*', '=', line)
        words = normalized.split()
        head = words[0].lower() if words else ''
        if head == 'simulator':
            found = re.search(r'lang=(\w+)', normalized, re.I)
            if found:
                language = found.group(1).lower()
            continue
        if language == 'spice':
            scope = _spice_statement(words, line, number, file, scope, models, subckts, duplicates)
            continue
        if head in ('inline', 'subckt') and (head == 'subckt' or (len(words) > 1 and words[1].lower() == 'subckt')):
            inline = head == 'inline'
            rest = line.split(None, 2 if inline else 1)[-1]
            found = re.match(r'([A-Za-z_][\w.$!]*)\s*(?:\(([^)]*)\)|(.*))', rest)
            if not found:
                continue
            name = found.group(1)
            pins = (found.group(2) if found.group(2) is not None else found.group(3) or '').split()
            scope = dict(name=name, inline=inline, pins=pins, parameters={}, elements=[], models={}, file=file,
                         line=number)
            _define(subckts, name, scope, models, subckts, duplicates)
            continue
        if head == 'ends':
            scope = None
            continue
        if head == 'parameters' and scope is not None:
            scope['parameters'].update(_assignments(line.split(None, 1)[1] if ' ' in line else ''))
            continue
        if head == 'model' and len(words) >= 3:
            model = dict(name=words[1], primitive=words[2].lower(), type=None, file=file, line=number)
            tail = normalized.split(None, 3)[3] if len(words) > 3 else ''
            found = re.search(r'\btype=([A-Za-z]+)', tail)
            if found:
                model['type'] = found.group(1).lower()
            if '{' in line:
                brace = line.count('{') - line.count('}')
                brace_model = model if brace > 0 else None
                if brace <= 0:
                    brace = 0
            if scope is not None:
                scope['models'][model['name']] = model
            else:
                _define(models, model['name'], model, models, subckts, duplicates)
            continue
        if '{' in line:                                           # statistics { ... } and other blocks
            brace = line.count('{') - line.count('}')
            if brace <= 0:
                brace = 0
            continue
        if scope is not None:
            element = re.match(r'([A-Za-z_][\w.$!]*)\s*\(([^)]*)\)\s*([A-Za-z_][\w.$!]*)(.*)$', line)
            if element:
                params = _assignments(element.group(4))
                scope['elements'].append(dict(name=element.group(1), nodes=element.group(2).split(),
                                              master=element.group(3), sets=sorted(k for k in params if k in ('r', 'c', 'q', 'l', 'i'))))
    return dict(models=models, subckts=subckts, duplicates=duplicates)


def _spice_statement(words, line, number, file, scope, models, subckts, duplicates):
    """The few SPICE statements a model file may switch to: .subckt/.ends/.model and element lines inside a .subckt."""
    head = words[0].lower() if words else ''
    if head == '.subckt' and len(words) >= 2:
        pins = [w for w in words[2:] if '=' not in w and w.lower() != 'params:']
        scope = dict(name=words[1], inline=False, pins=pins, parameters=_assignments(line.split(None, 2)[2] if len(words) > 2 else ''),
                     elements=[], models={}, file=file, line=number)
        _define(subckts, words[1], scope, models, subckts, duplicates)
        return scope
    if head == '.ends':
        return None
    if head == '.model' and len(words) >= 3:
        primitive = words[2].split('(')[0].lower()
        primitive = {'nmos': 'bsim4', 'pmos': 'bsim4', 'npn': 'bjt', 'pnp': 'bjt', 'd': 'diode', 'r': 'resistor',
                     'c': 'capacitor', 'l': 'inductor'}.get(primitive, primitive)
        kind = words[2].split('(')[0].lower()
        model = dict(name=words[1], primitive=primitive, file=file, line=number,
                     type={'nmos': 'n', 'pmos': 'p', 'npn': 'npn', 'pnp': 'pnp'}.get(kind))
        (scope['models'] if scope is not None else models).setdefault(words[1], model)
        return scope
    if scope is not None and words and words[0][:1].isalpha():
        letter = words[0][0].lower()
        count = dict(m=4, q=3, d=2, r=2, c=2, l=2).get(letter)
        if letter == 'x':
            plain = [w for w in words[1:] if '=' not in w]
            if len(plain) >= 2:
                scope['elements'].append(dict(name=words[0], nodes=plain[:-1], master=plain[-1], sets=[]))
        elif count and len(words) > count:
            master = words[count + 1] if len(words) > count + 1 and '=' not in words[count + 1] else \
                {'r': 'resistor', 'c': 'capacitor', 'l': 'inductor'}.get(letter, '')
            scope['elements'].append(dict(name=words[0], nodes=words[1:count + 1], master=master or '', sets=[]))
    return scope


def merge_scans(scans):
    """Several files' scans -> one namespace (the first definition of a name wins; later ones are listed)."""
    models, subckts, duplicates = {}, {}, []
    for scan in scans:
        for name, model in scan['models'].items():
            _define(models, name, model, models, subckts, duplicates)
        for name, subckt in scan['subckts'].items():
            _define(subckts, name, subckt, models, subckts, duplicates)
        duplicates += scan['duplicates']
    return dict(models=models, subckts=subckts, duplicates=duplicates)


# ------------------------------------------------------------------------------------------ classifying one model
def _where(entry):
    return f"{Path(entry['file']).name}:{entry['line']}"


def _element_family(element, subckt, scan, depth=0):
    """(family, polarity, basis) of one element inside a subcircuit."""
    master = element['master']
    local = subckt['models'].get(master) or scan['models'].get(master)
    if local is not None:
        family = PRIMITIVE_FAMILY.get(local['primitive'])
        return family, local.get('type'), f"model {master} = {local['primitive']}{', type=' + local['type'] if local.get('type') else ''} ({_where(local)})"
    if master.lower() in PRIMITIVE_FAMILY:
        return PRIMITIVE_FAMILY[master.lower()], None, f'Spectre primitive {master}'
    if master.lower() == 'bsource':
        sets = set(element.get('sets') or ())
        family = 'resistor' if 'r' in sets else 'varactor' if 'q' in sets else 'capacitor' if 'c' in sets else \
            'inductor' if 'l' in sets else 'other'
        return family, None, f"behavioural source with {'/'.join(sorted(sets)) or 'no'} value"
    inner = scan['subckts'].get(master)
    if inner is not None and depth < 4:
        found = classify_model(master, scan, depth=depth + 1)
        return found['family'], found.get('polarity'), f"subcircuit {master} ({_where(inner)}): {found['family_basis']}"
    return None, None, f'{master}: not defined in the model files read'


def _paths(subckt, scan, start, end, blocked):
    """Families of the elements on every simple path from pin `start` to pin `end` through internal nodes only."""
    edges = []
    for element in subckt['elements']:
        if len(element['nodes']) == 2:
            family = _element_family(element, subckt, scan)[0]
            edges.append((element['nodes'][0], element['nodes'][1], family or 'other'))
    found, stack = [], [(start, (), frozenset([start]))]
    while stack and len(found) < 64:
        node, families, seen = stack.pop()
        for a, b, family in edges:
            for here, there in ((a, b), (b, a)):
                if here != node:
                    continue
                if there == end:
                    found.append(families + (family,))
                elif there not in seen and there not in blocked and len(seen) < 32:
                    stack.append((there, families + (family,), seen | {there}))
    return found


def classify_model(name, scan, *, cdf_units=(), depth=0):
    """What one Spectre model is: {family, polarity, family_basis, core (element whose terminals give the pin roles)}.
    `cdf_units` = the units the cell's CDF declares (decides between passive candidates, never overrides a primitive)."""
    model = scan['models'].get(name)
    if model is not None:
        family = PRIMITIVE_FAMILY.get(model['primitive'])
        return dict(family=family or 'other', polarity=model.get('type'), core=None,
                    family_basis=f"model {name} = {model['primitive']}{', type=' + model['type'] if model.get('type') else ''} ({_where(model)})"
                    if family else f"model {name} uses primitive {model['primitive']}, which is not classified here ({_where(model)})")
    subckt = scan['subckts'].get(name)
    if subckt is None:
        return dict(family='other', polarity=None, core=None, family_basis=f'{name} is not defined in the model files read')
    if subckt['inline']:
        main = next((e for e in subckt['elements'] if e['name'] == name), None)
        if main is not None:
            family, polarity, basis = _element_family(main, subckt, scan, depth)
            if family:
                return dict(family=family, polarity=polarity, core=main,
                            family_basis=f'inline subcircuit {name} ({_where(subckt)}): its own element uses {basis}')
    active = [(e, *_element_family(e, subckt, scan, depth)) for e in subckt['elements']]
    for wanted in ('mos', 'bjt'):
        cores = [item for item in active if item[1] == wanted and len(item[0]['nodes']) >= (4 if wanted == 'mos' else 3)]
        if len(cores) == 1:
            element, family, polarity, basis = cores[0]
            return dict(family=family, polarity=polarity, core=element,
                        family_basis=f"subcircuit {name} ({_where(subckt)}): element {element['name']} uses {basis}")
        if len(cores) > 1:
            return dict(family='other', polarity=None, core=None,
                        family_basis=f'subcircuit {name} ({_where(subckt)}) holds {len(cores)} {wanted} elements')
    if len(subckt['pins']) < 2:
        return dict(family='other', polarity=None, core=None, family_basis=f'subcircuit {name} has fewer than two pins')
    paths = _paths(subckt, scan, subckt['pins'][0], subckt['pins'][1], set(subckt['pins'][2:]))
    on_path = {family for path in paths for family in path}
    candidates = on_path & set(PASSIVE)
    declared = {CDF_UNITS.get(u) for u in cdf_units}
    by_unit = {'ohm': 'resistor', 'F': 'capacitor', 'H': 'inductor'}
    where = f'subcircuit {name} ({_where(subckt)})'
    if not paths:
        return dict(family='other', polarity=None, core=None, family_basis=f'{where}: its first two pins are not connected')
    # A diode wrapped with its series resistance (`r1 (1 3) resistor` + `d1 (3 2) <diode model>`): every path between the
    # first two pins crosses the one diode that can lie on such a path, and nothing but resistors besides it. A diode to
    # a further pin (the body) never lies on one; a resistor beside a diode in parallel leaves a path without it.
    series = [item for item in active if item[1] == 'diode' and len(item[0]['nodes']) == 2
              and not set(item[0]['nodes']) & set(subckt['pins'][2:])]
    if len(series) == 1 and all(path.count('diode') == 1 and set(path) <= {'diode', 'resistor'} for path in paths):
        element, _, _, basis = series[0]
        return dict(family='diode', polarity=None, core=element,
                    family_basis=f"{where}: element {element['name']} uses {basis}, with only resistance in series between its first two pins")
    if on_path == {'resistor'}:
        return dict(family='resistor', polarity=None, core=None, family_basis=f'{where}: only resistive elements between its first two pins')
    if len(candidates) == 1 and on_path <= set(PASSIVE):
        family = candidates.pop()
        return dict(family=family, polarity=None, core=None, family_basis=f'{where}: only {family} elements between its first two pins')
    backed = [by_unit[u] for u in sorted(declared & set(by_unit)) if by_unit[u] in candidates]
    if len(backed) == 1:
        return dict(family=backed[0], polarity=None, core=None,
                    family_basis=f"{where}: {', '.join(sorted(candidates))} between its first two pins; the cell declares a "
                                 f"{ {v: k for k, v in by_unit.items()}[backed[0]] } parameter")
    if 'inductor' in candidates:
        return dict(family='inductor', polarity=None, core=None,
                    family_basis=f"{where}: an inductor lies between its first two pins (with {', '.join(sorted(candidates - {'inductor'})) or 'nothing else'})")
    return dict(family='other', polarity=None, core=None,
                family_basis=f"{where}: {', '.join(sorted(on_path)) or 'nothing'} between its first two pins - not classified")


def pin_roles(name, found, scan):
    """Role of each pin of model `name` (in the model's own pin order), with the basis of each."""
    family = found['family']
    subckt = scan['subckts'].get(name)
    if subckt is None:                                   # a primitive model used directly: Spectre's terminal order
        roles = TERMINAL_ROLES.get(family)
        return None if roles is None else [dict(model_pin=f'{i + 1}', role=role, basis=f'{family} terminal {i + 1}')
                                           for i, role in enumerate(roles)]
    pins = subckt['pins']
    if family in PASSIVE:
        return [dict(model_pin=pin, role=('positive', 'negative')[i] if i < 2 else 'bulk',
                     basis='first terminal' if i == 0 else 'second terminal' if i == 1 else 'further terminal (substrate / body)')
                for i, pin in enumerate(pins)]
    core, roles = found.get('core'), TERMINAL_ROLES.get(family)
    if core is None or roles is None:
        return [dict(model_pin=pin, role='unknown', basis='not traced') for pin in pins]
    out = []
    for pin in pins:
        role, basis = 'unknown', 'reaches no terminal of the core element'
        if pin in core['nodes'] and core['nodes'].index(pin) < len(roles):
            role, basis = roles[core['nodes'].index(pin)], f"terminal {core['nodes'].index(pin) + 1} of {core['name']}"
        else:
            for element in subckt['elements']:
                if element is core or len(element['nodes']) != 2 or pin not in element['nodes']:
                    continue
                other = element['nodes'][1 - element['nodes'].index(pin)]
                if other in core['nodes'] and core['nodes'].index(other) < len(roles):
                    role = roles[core['nodes'].index(other)]
                    basis = f"through {element['name']} to terminal {core['nodes'].index(other) + 1} of {core['name']}"
                    break
        out.append(dict(model_pin=pin, role=role, basis=basis))
    return out


# ------------------------------------------------------------------------------------------ building the record
def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    from analog_optimizer.netlist.expressions import UnresolvedExpression, evaluate

    def refuse(name):
        raise UnresolvedExpression(name)
    try:
        return evaluate(str(value), refuse)
    except (UnresolvedExpression, ValueError):
        return None


_REFERENCE = re.compile(r'^\s*([ip])Par\(\s*"([A-Za-z_]\w*)"\s*\)\s*$')


def _cdf_entry(cells, cell, name, parent=None, depth=0):
    """(CDF parameter entry, default value resolved through iPar/pPar references) of `name` on `cell`."""
    entry = (cells.get(cell) or {}).get('parameters', {}).get(name)
    if entry is None:
        return None, None
    default, units = entry.get('default'), entry.get('units')
    found = _REFERENCE.match(default) if isinstance(default, str) else None
    if found and depth < 6:
        target_cell = cell if found.group(1) == 'i' else parent
        if target_cell:
            inner, value = _cdf_entry(cells, target_cell, found.group(2), None, depth + 1)
            if inner is not None:
                return dict(entry, units=units or inner.get('units')), value
        return entry, None
    return entry, _number(default)


def _write_source(cells, cell, name, parent=None, depth=0):
    """Which CDF parameter a user edits to set CDF parameter `name` of `cell`: `name` itself, or - when its default ties it
    to another one - that one: `iPar("x")` = x of the same instance (GPDK045's `simW` = `w`, an inductor's `width` = its
    choice list `width_cyclic`), `pPar("x")` = x of the cell that places this primitive (a resistor's `segL`). None when
    the chain leads nowhere. `editable` / `display` are the form's own rules (True, False or a SKILL expression decided per
    instance); both are None for a PDK loaded before the form was read."""
    entry = (cells.get(cell) or {}).get('parameters', {}).get(name)
    if entry is None or depth > 6:
        return None
    found = _REFERENCE.match(entry['default']) if isinstance(entry.get('default'), str) else None
    if found:
        if found.group(1) == 'i':
            return _write_source(cells, cell, found.group(2), parent, depth + 1)
        inner = _write_source(cells, parent, found.group(2), None, depth + 1) if parent else None
        return None if inner is None else dict(inner, on='parent')
    return dict(cdf=name, on='self', cell=cell, type=entry.get('type'), editable=entry.get('editable'),
                display=entry.get('display'), callback=entry.get('callback'), choices=entry.get('choices'),
                range=entry.get('range'))          # what the form itself accepts, when the PDK declares it


def _writable(source, numeric):
    """'yes' / 'no' / 'depends' (on the instance's current mode, decided in Virtuoso) / 'unknown' (no form read)."""
    if source is None or not numeric:
        return 'no'
    if source['editable'] is None:
        return 'unknown'
    if source['editable'] is False or source['display'] is False or source['type'] not in NUMERIC_CDF_TYPES + ('cyclic',):
        return 'no'
    if source['type'] == 'cyclic' and not (isinstance(source['choices'], list)
                                           and all(_number(c) is not None for c in source['choices'])):
        return 'no'                                       # a choice list of words (a mode), not of numbers
    return 'yes' if source['editable'] is True and source['display'] is True else 'depends'


def _leaf_of(cells, leaves, name):
    """A cell without a Spectre entry of its own: the one primitive its schematic places that has one."""
    found = [leaf for leaf in leaves.get(name, []) if (cells.get(leaf['cell']) or {}).get('spectre') and leaf.get('model')]
    return found[0] if len(found) == 1 else None


def build_record(pdk_id, cdf, scans, *, sources=None, technology_library=None):
    """The PDK record: one entry per Spectre model a cell of the library netlists to, and the component list."""
    scan = merge_scans(scans)
    cells, leaves = cdf['cells'], cdf['leaves']
    by_model, not_netlisted = {}, []
    for name in sorted(cells):
        cell = cells[name]
        spectre, parent, via = cell.get('spectre'), None, None
        model = cell.get('model') or (spectre or {}).get('component_name')
        if spectre is None:
            leaf = _leaf_of(cells, leaves, name)
            if leaf is None:
                not_netlisted.append(dict(cell=name, reason='no Spectre entry and no netlisted primitive in its schematic'
                                          if 'schematic' in cell.get('views', []) else 'no Spectre entry (not netlisted)'))
                continue
            parent, via, model = name, leaf, leaf['model']
            spectre = cells[leaf['cell']]['spectre']
        if not model or not isinstance(model, str):
            placed = any(leaf['cell'] == name for entries in leaves.values() for leaf in entries)
            not_netlisted.append(dict(cell=name, reason='a primitive placed inside other cells, which name its model' if placed
                                      else 'its description names no Spectre model'))
            continue
        by_model.setdefault(model, []).append(dict(cell=name, spectre=spectre, parent=parent, via=via,
                                                   leaf_cell=via['cell'] if via else name))
    devices = {}
    for model in sorted(by_model):
        uses = by_model[model]
        # The cell whose pins are all named in its own mapping describes the pins (nmos1v rather than nmos1v_3 with its
        # inherited bulk); ties go to the shortest, then alphabetical name.
        uses.sort(key=lambda u: (not all(str(t) in u['spectre']['term_mapping'] for t in u['spectre']['term_order'] or []),
                                 len(u['cell']), u['cell']))
        lead = uses[0]
        units_declared = sorted({str(p.get('units')) for u in uses for p in cells[u['leaf_cell']]['parameters'].values()
                                 if p.get('units')} | {str(p.get('units')) for u in uses if u['parent']
                                                        for p in cells[u['parent']]['parameters'].values() if p.get('units')})
        found = classify_model(model, scan, cdf_units=units_declared)
        problems = []
        roles = pin_roles(model, found, scan) if found['family'] != 'other' else None
        order = [str(t) for t in lead['spectre'].get('term_order') or []]
        mapping = {str(k): str(v) for k, v in lead['spectre'].get('term_mapping', {}).items()}
        pins = []
        subckt = scan['subckts'].get(model)
        model_pins = subckt['pins'] if subckt else [str(i + 1) for i in range(len(order))]
        if not order:
            problems.append('the description gives no pin order')
        if subckt is not None and order and len(order) != len(model_pins):
            problems.append(f'{len(order)} pins in the description, {len(model_pins)} in the model file')
        for index, symbol in enumerate(order):
            target = mapping.get(symbol, '').lstrip(':')
            model_pin = model_pins[index] if index < len(model_pins) else None
            role = roles[index]['role'] if roles and index < len(roles) else 'unknown'
            basis = roles[index]['basis'] if roles and index < len(roles) else 'no role established'
            allowed = {model_pin, str(index + 1)} | ({PRIMITIVE_PINS[found['family']][index]}
                                                     if subckt is None and index < len(PRIMITIVE_PINS.get(found['family'], ())) else set())
            if target and model_pin is not None and target not in allowed and not target.startswith('('):
                problems.append(f'pin {symbol} maps to {target} but position {index + 1} of {model} is {model_pin}')
                role, basis = 'unknown', 'pin order and mapping disagree'
            pins.append(dict(name=symbol, model_pin=model_pin, role=role, basis=basis))
        parameters = []
        leaf_cell, parent = lead['leaf_cell'], lead['parent']
        prop = {str(k): str(v) for k, v in lead['spectre'].get('prop_mapping', {}).items()}
        for netlist in [str(p) for p in lead['spectre'].get('inst_parameters') or []]:
            cdf_name = prop.get(netlist, netlist)
            entry, default = _cdf_entry(cells, leaf_cell, cdf_name, parent)
            if entry is None:
                entry, default = _cdf_entry(cells, leaf_cell, netlist, parent)
            kind = (entry or {}).get('type')
            unit = CDF_UNITS.get((entry or {}).get('units'))
            numeric = kind in NUMERIC_CDF_TYPES and (default is not None or unit is not None or netlist in STANDARD_UNITS)
            source = _write_source(cells, leaf_cell, cdf_name if entry is not None and cdf_name in cells[leaf_cell]['parameters']
                                   else netlist, parent)
            parameters.append(dict(name=netlist, cdf=cdf_name, type=kind, unit=unit, unit_declared=unit is not None,
                                   default=default, prompt=(entry or {}).get('prompt'), numeric=bool(numeric),
                                   write=source, writable=_writable(source, numeric)))
        standard = dict(mos={'n': 'nmos', 'p': 'pmos'}.get(found.get('polarity')), resistor='resistor',
                        capacitor='capacitor', inductor='inductor').get(found['family']) or 'unknown'
        known = {p['role'] for p in pins}
        if 'unknown' in known and found['family'] != 'other':
            problems.append('the role of some pins could not be established')
        forms = dict(self=cells[leaf_cell].get('form'), parent=cells[parent].get('form') if parent else None)
        devices[model] = dict(
            model=model, kind=f'{pdk_id}:{model}', cells=[u['cell'] for u in uses], form=forms,
            netlisted_through=sorted({u['via']['cell'] for u in uses if u['via']}),
            family=found['family'], family_label=FAMILY_LABEL[found['family']], polarity=found.get('polarity'),
            family_basis=found['family_basis'], pins=pins, parameters=parameters,
            standard_kind=standard, standard_roles=_standard_roles(standard, pins),
            source=_where(subckt) if subckt else _where(scan['models'][model]) if model in scan['models'] else None,
            problems=problems)
    used = set(devices)
    unused = sorted((set(scan['subckts']) | set(scan['models'])) - used)
    _assign_columns(devices)
    vocabulary = _vocabulary(pdk_id, devices)
    record = dict(format=FORMAT, pdk_id=pdk_id, technology_library=technology_library or pdk_id, loaded_utc=utcnow().isoformat(),
                  sources=sources or {}, devices=devices, not_netlisted=not_netlisted, layout_only=cdf.get('layout_only', []),
                  model_file_definitions_not_used=unused,
                  duplicates=scan['duplicates'][:50], vocabulary=vocabulary, summary=_summary(devices))
    record['sha256'] = vocabulary['sha256']
    return record


def _standard_roles(kind, pins):
    if kind in ('nmos', 'pmos'):
        return [p['role'] if p['role'] in ('drain', 'gate', 'source', 'bulk') else 'unknown' for p in pins]
    if kind in ('resistor', 'capacitor', 'inductor'):
        return [p['role'] if p['role'] in ('positive', 'negative', 'bulk') else 'unknown' for p in pins]
    return ['unknown'] * len(pins)


def _decade(value):
    return None if not value else math.log10(abs(value))


def _compatible(a, b):
    """Two parameters may share one network column: same declared unit, or (undeclared) defaults of the same scale."""
    if a['unit'] and b['unit']:
        return a['unit'] == b['unit']
    ua = a['unit'] or b['unit']
    reference = UNIT_REFERENCE.get(ua) if ua else None
    da, db = _decade(a['default']), _decade(b['default'])
    if reference is not None:
        other = db if a['unit'] else da
        return other is None or abs(other - math.log10(reference)) <= SCALE_TOLERANCE_DECADES
    return da is None or db is None or abs(da - db) <= SCALE_TOLERANCE_DECADES


def _reference(entries):
    units = {e['unit'] for e in entries if e['unit']}
    if len(units) == 1:
        return UNIT_REFERENCE.get(next(iter(units)), 1.0)
    decades = [_decade(e['default']) for e in entries if _decade(e['default']) is not None]
    return 10.0 ** round(sum(decades) / len(decades)) if decades else 1.0


def _typical(entries, family):
    """The geometric mean of the nonzero defaults a family gives one parameter name (None if it gives none)."""
    decades = [_decade(p['default']) for d, p in entries if d['family'] == family and _decade(p['default']) is not None]
    return 10.0 ** (sum(decades) / len(decades)) if decades else None


def _assign_columns(devices):
    """Give every numeric parameter a canonical name and a network column (in place).

    canonical: the netlist name, unless that name is one of the eight standard parameters with another meaning (an
    inductor's `r` is its radius, not a resistance); then the CDF's own name for it (`rad`).
    column: the canonical name, shared by every device whose parameter of that name has the same scale; the standard
    names keep the standard scale. Names whose scales disagree across families get one column per family
    (`bjt.area`, `diode.area`)."""
    standard = standard_schema()
    standard_ref = dict(zip(standard.parameters, standard.references))
    groups = {}
    for device in devices.values():
        for p in device['parameters']:
            if not p['numeric']:
                p.update(canonical=None, column=None, reference=None, action_class=None)
                continue
            probe = dict(unit=STANDARD_UNITS.get(p['name']), default=standard_ref.get(p['name']))
            if p['name'] in STANDARD_UNITS and not _compatible(dict(p, unit=p['unit'] if p['unit'] != 'count' else None),
                                                               dict(probe, unit=probe['unit'] if probe['unit'] != 'count' else None)):
                p['canonical'] = p['cdf'] if p['cdf'] != p['name'] and p['cdf'] not in STANDARD_UNITS else f"{p['name']}_{device['family']}"
            else:
                p['canonical'] = p['name']
            if p['canonical'] in STANDARD_UNITS and not p['unit']:
                p['unit'], p['unit_basis'] = STANDARD_UNITS[p['canonical']], 'same name and scale as the standard parameter'
            groups.setdefault(p['canonical'], []).append((device, p))

    def agree(entries):
        return all(_compatible(a[1], b[1]) for i, a in enumerate(entries) for b in entries[i + 1:])

    for name, entries in sorted(groups.items()):
        if name in standard_ref:
            for _, p in entries:
                p.update(column=name, reference=standard_ref[name])
            continue
        # Within one family a name is one quantity (a transistor's `scc` stays one column even where the flavours'
        # defaults differ); only families that disagree get columns of their own.
        families = sorted({d['family'] for d, _ in entries})
        firsts = [next(item for item in entries if item[0]['family'] == f) for f in families]
        if len(families) == 1 or agree([(d, dict(p, default=_typical(entries, d['family']))) for d, p in firsts]):
            columns = {name: entries}
        else:
            columns = {f'{family}.{name}': [item for item in entries if item[0]['family'] == family] for family in families}
        for column, members in columns.items():
            reference = _reference([p for _, p in members])
            for _, p in members:
                p.update(column=column, reference=reference)
    for device in devices.values():
        for p in device['parameters']:
            if p['numeric']:
                unit = p['unit']
                p['action_class'] = p['canonical'] if p['canonical'] in STANDARD_UNITS else ACTION_CLASS.get(unit)
                if p['action_class'] == 'l' and p['canonical'] == 'w':
                    p['action_class'] = 'w'


def _vocabulary(pdk_id, devices):
    """The component list the network is built with, and what the network view does per Spectre model."""
    standard = standard_schema()
    roles = list(standard.terminal_roles)
    roles += sorted({pin['role'] for device in devices.values() for pin in device['pins']} - set(roles))
    columns = {}
    for device in devices.values():
        for p in device['parameters']:
            if p['numeric'] and p['column'] not in standard.parameters:
                columns.setdefault(p['column'], p['reference'])
    extra = sorted(columns)
    view = {model: dict(kind=device['kind'], roles=[p['role'] for p in device['pins']], family=device['family'],
                        polarity=device.get('polarity'),
                        columns={key: p['column'] for p in device['parameters'] if p['numeric']
                                 for key in dict.fromkeys((p['name'], p['canonical']))})
            for model, device in sorted(devices.items())}
    body = dict(format=VOCABULARY_FORMAT, pdk_id=pdk_id,
                device_kinds=list(standard.device_kinds) + [devices[m]['kind'] for m in sorted(devices)],
                terminal_roles=roles, net_roles=list(standard.net_roles),
                parameters=list(standard.parameters) + extra,
                references=list(standard.references) + [float(columns[c]) for c in extra], devices=view)
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(body, version=f'pdk-{pdk_id}-{sha[:16]}', sha256=sha)


def _summary(devices):
    counts = {}
    for device in devices.values():
        key = device['family'] if device['family'] not in ('mos', 'bjt') or not device.get('polarity') \
            else f"{device['family']}:{device['polarity']}"
        counts[key] = counts.get(key, 0) + 1
    return dict(devices=len(devices), cells=sum(len(d['cells']) for d in devices.values()), by_family=counts,
                with_problems=sorted(m for m, d in devices.items() if d['problems']))


# ------------------------------------------------------------------------------------------ the ideal parts' record
def _pin_names(order):
    """A CDF pin order as names, or None when it is absent or not a plain list. SKILL prints a pin called `t` as its
    truth value, which the reader turns into True."""
    if not isinstance(order, list) or not order:
        return None
    names = ['t' if pin is True else str(pin) for pin in order if isinstance(pin, (str, int)) or pin is True]
    return names if len(names) == len(order) and len(set(names)) == len(names) else None


def build_ideal_parts(library, cdf) -> dict:
    """What the generic library says about its parts: one entry per Spectre component a cell netlists as, with every pin
    order the library states for it and, where the standard list has a kind for the component, that kind.

    Several cells share a component, and not always with the same pins: `vdc`, `vpulse`, `vsin` netlist a `vsource` with
    two nodes, `vprbs` and the cell called `vsource` itself one with six. So a component keeps each stated pin order with
    the cells that state it, and a netlist is read with the order that has as many pins as its lines have nodes
    (`ideal_models`). A cell that netlists with a model named on the instance (`nmos4`, `bsim4`) is no component of its
    own: its model belongs to a PDK."""
    by_component, not_components = {}, []
    for name in sorted(cdf['cells']):
        spectre = cdf['cells'][name].get('spectre') or {}
        component = spectre.get('component_name')
        if not isinstance(component, str) or not component:
            not_components.append(dict(cell=name, reason='netlists with a model named on the instance' if spectre
                                       else 'no Spectre entry (not netlisted)'))
            continue
        by_component.setdefault(component, {}).setdefault(tuple(_pin_names(spectre.get('term_order')) or ()), []).append(name)
    components = {}
    for component in sorted(by_component):
        orders = by_component[component]
        # Most cells first, then the order of the cell that carries the component's own name, then the shorter one.
        stated = sorted((pins for pins in orders if pins and len(pins) <= MAX_IDEAL_PINS),
                        key=lambda pins: (-len(orders[pins]), component not in orders[pins], len(pins), pins))
        kind, aliases = IDEAL_KINDS.get(component, ('unknown', {}))
        if kind != 'unknown' and not any(len(pins) == 2 for pins in stated):
            kind, aliases = 'unknown', {}                # never the two-terminal part the standard list means
        if not stated:
            basis = 'the library states no pin order for it'
        elif kind == 'unknown':
            basis = f'Spectre component {component}: the standard list has no kind for it, so the network sees "unknown"'
        else:
            basis = f'Spectre component {component} with two nodes: the first is the positive one' + (
                ' (a current probe is a 0 V source in series)' if component == 'iprobe' else '')
        components[component] = dict(
            component=component, cells=sorted(cell for cells in orders.values() for cell in cells), kind=kind,
            parameters=dict(aliases), basis=basis,
            pin_orders=[dict(pins=list(pins), cells=sorted(orders[pins])) for pins in stated],
            cells_without_pin_order=sorted(orders.get((), [])),
            cells_with_too_many_pins=sorted(cell for pins, cells in orders.items() if len(pins) > MAX_IDEAL_PINS for cell in cells))
    body = dict(format=IDEAL_FORMAT, library=library, components=components)
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    usable = [c for c in components.values() if c['pin_orders']]
    return dict(body, sha256=sha, read_utc=utcnow().isoformat(), not_components=not_components,
                layout_only=cdf.get('layout_only', []),
                summary=dict(cells=len(cdf['cells']) + len(cdf.get('layout_only', [])), components=len(components),
                             recognized=len(usable), with_a_kind=sorted(c['component'] for c in usable if c['kind'] != 'unknown'),
                             as_unknown=sum(1 for c in usable if c['kind'] == 'unknown'),
                             without_pins=sorted(c['component'] for c in components.values() if not c['pin_orders'])))


def _ideal_parts_of(read, previous):
    """The ideal parts for a record that is being stored: what this read brought, else what an earlier read of the same
    PDK brought (kept, with the reason this read brought nothing), else only the reason."""
    read = read or {}
    library = read.get('library') or IDEAL_LIBRARY
    reason = read.get('error')
    if read.get('cdf_text'):
        cdf = parse_cdf_text(read['cdf_text'])
        if cdf['cells']:
            return build_ideal_parts(library, cdf)
        reason = f'{library} has no cell with a component description (CDF)'
    reason = reason or 'this read did not ask for them (an older reader)'
    kept = (previous or {}).get('ideal_parts')
    if isinstance(kept, dict) and kept.get('components'):
        return dict(kept, not_read_again=reason)
    return dict(format=IDEAL_FORMAT, library=library, components={}, error=reason)


def ideal_models(record, node_counts=None) -> dict:
    """The parser's device mappings for the ideal parts read with a PDK: every component the library states a pin order
    for - its kind where the standard list has one and the line has two nodes, "unknown" with its pins named otherwise.
    `node_counts` = {component: how many nodes its lines have in the netlist being read} picks, per component, the
    stated order of that length; a component whose lines differ in length, or fit no stated order, gets no mapping (it
    stays unrecognized, which the reader of the cell reports). Without it: the first order of each component."""
    parts = (record or {}).get('ideal_parts') or {}
    models = {}
    for name, part in (parts.get('components') or {}).items():
        orders = [order['pins'] for order in part.get('pin_orders') or []]
        if node_counts is not None:
            if name not in node_counts or len(set(node_counts[name])) != 1:
                continue
            orders = [pins for pins in orders if len(pins) == next(iter(node_counts[name]))]
        if not orders:
            continue
        pins = orders[0]
        standard = part['kind'] != 'unknown' and len(pins) == 2
        models[name] = dict(kind=part['kind'] if standard else 'unknown', terminals=list(pins),
                            roles=['positive', 'negative'] if standard else ['unknown'] * len(pins),
                            parameters=dict(part['parameters']) if standard else {})
    return models


def describe_ideal_parts(record, *, brief=False):
    """What the page shows about the ideal parts read with a PDK; None for a PDK loaded before they were read."""
    parts = (record or {}).get('ideal_parts')
    if not isinstance(parts, dict):
        return None
    out = dict(library=parts.get('library'), read_utc=parts.get('read_utc'), sha256=parts.get('sha256'),
               summary=parts.get('summary'), error=parts.get('error'), not_read_again=parts.get('not_read_again'))
    if not brief:
        out.update(components=list((parts.get('components') or {}).values()), not_components=parts.get('not_components', []))
    return out


# ------------------------------------------------------------------------------------------ storage
def store_root() -> Path:
    return local_settings_dir() / 'pdks'


def pdk_dir(pdk_id) -> Path:
    if not isinstance(pdk_id, str) or not NAME.match(pdk_id):
        raise PdkError('A PDK is named by its technology library: a plain Cadence name')
    return store_root() / pdk_id


def save_record(record) -> dict:
    """The current record of a PDK, plus every version ever loaded (a run names its version by SHA-256, and a model
    trained with one version must still find it after the PDK was loaded again)."""
    directory = pdk_dir(record['pdk_id'])
    (directory / 'versions').mkdir(parents=True, exist_ok=True)
    version = directory / 'versions' / f"{record['sha256']}.json"
    if not version.exists():
        write_json(version, record)
    write_json(directory / 'pdk.json', record)
    return record


def load_record(pdk_id, sha256=None) -> dict | None:
    try:
        directory = pdk_dir(pdk_id)
    except PdkError:
        return None
    path = directory / ('pdk.json' if sha256 is None else f'versions/{sha256}.json')
    if sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', sha256):
        return None
    record = read_json(path, default=None)
    if not isinstance(record, dict) or record.get('format') != FORMAT or record.get('pdk_id') != pdk_id:
        return None
    return record


def list_pdks() -> list:
    root = store_root()
    found = []
    for path in sorted(root.glob('*/pdk.json')) if root.is_dir() else ():
        record = load_record(path.parent.name)
        if record is not None:
            found.append(describe(record, brief=True))
    return found


def describe(record, *, brief=False):
    """What the page shows about a loaded PDK."""
    out = dict(pdk_id=record['pdk_id'], vocabulary=f"pdk:{record['pdk_id']}", sha256=record['sha256'],
               version=record['vocabulary']['version'], loaded_utc=record['loaded_utc'],
               technology_library=record['technology_library'], summary=record['summary'],
               label=label(record['vocabulary']), sources=record.get('sources', {}),
               columns=len(record['vocabulary']['parameters']), kinds=len(record['vocabulary']['device_kinds']),
               roles=len(record['vocabulary']['terminal_roles']), ideal_parts=describe_ideal_parts(record, brief=brief))
    if not brief:
        out.update(devices=list(record['devices'].values()), not_netlisted=record['not_netlisted'],
                   layout_only=record['layout_only'], not_used=record['model_file_definitions_not_used'],
                   parameters=record['vocabulary']['parameters'], terminal_roles=record['vocabulary']['terminal_roles'])
    return out


def label(vocabulary) -> str:
    if vocabulary is None:
        return 'standard (8 generic kinds)'
    count = len(vocabulary['devices'])
    return f"PDK {vocabulary['pdk_id']} ({count} components, version {vocabulary['sha256'][:8]})"


# ------------------------------------------------------------------------------------------ the network's view
class Vocabulary:
    """A loaded PDK's component list, as the learner uses it. Built from the `vocabulary` block of a record (or of a
    run's own copy), never from the live PDK folder: what a run used is fixed at its start."""

    def __init__(self, block):
        if not isinstance(block, dict) or block.get('format') != VOCABULARY_FORMAT:
            raise PdkError('Not a PDK component list')
        self.block = block
        self.pdk_id, self.sha256, self.version = block['pdk_id'], block['sha256'], block['version']
        self.devices = block['devices']
        from analog_optimizer.graph.pyg_converter import FeatureSchema
        self.schema = FeatureSchema(version=block['version'], device_kinds=tuple(block['device_kinds']),
                                    terminal_roles=tuple(block['terminal_roles']), net_roles=tuple(block['net_roles']),
                                    parameters=tuple(block['parameters']), references=tuple(float(r) for r in block['references']))
        self.name = f'pdk:{self.pdk_id}'

    @property
    def label(self):
        return label(self.block)

    def view_graph(self, graph):
        """The graph as the network sees it (a new object; `graph` is not changed)."""
        from analog_optimizer.graph.circuit_graph import CircuitGraph
        devices, roles, renames = [], {}, {}
        for device in graph.devices:
            entry = self.devices.get(device.model_ref)
            if entry is None or len(entry['roles']) != len(device.terminals):
                devices.append(device)
                continue
            devices.append(replace(device, kind=entry['kind']))
            roles[device.id] = entry['roles']
            renames[device.id] = entry['columns']
        connections = [replace(c, role=roles[c.device_id][c.ordinal]) if c.device_id in roles else c
                       for c in graph.connections]
        parameters = {}
        for device_id, values in graph.parameters.items():
            columns = renames.get(device_id)
            if not columns:
                parameters[device_id] = values
                continue
            moved = {}
            for key, value in values.items():
                target = columns.get(key, key)
                moved[target if target not in moved else key] = value
            parameters[device_id] = moved
        groups = []
        for group in graph.parameter_groups:
            members = tuple(replace(m, parameter=renames[m.device_id].get(m.parameter, m.parameter))
                            if m.device_id in renames else m for m in group.members)
            groups.append(replace(group, members=members) if members != group.members else group)
        return CircuitGraph(graph.circuit_id, devices, list(graph.nets), connections, parameters, groups,
                            list(graph.diagnostics), graph.metadata, graph.schema_version)

    def view(self, observation):
        return replace(observation, graph=self.view_graph(observation.graph))

def parse_models(record) -> dict:
    """The parser's device mappings (``ParserConfig.models``) for every component of a loaded PDK, in the STANDARD
    list's terms: the kind and pin roles of the eight generic kinds, `unknown` for a family that list has no kind for
    (bipolar, diode). A circuit graph thus keeps what the standard list reads - with its pins named - and only the
    network's view adds the PDK kinds (Vocabulary.view). Parameters keep their netlist names, except where a name means
    something else in the standard list (an inductor's radius `r` becomes `rad`; its netlist name is kept for writing)."""
    models = {}
    for model, device in (record or {}).get('devices', {}).items():
        names = [pin['name'] for pin in device['pins']]
        aliases = {p['name']: p['canonical'] for p in device['parameters'] if p['numeric'] and p.get('canonical')}
        if not names or len(set(names)) != len(names) or len(set(aliases.values())) != len(aliases):
            continue
        models[model] = dict(kind=device['standard_kind'], terminals=names, roles=device['standard_roles'], parameters=aliases)
    return models


def vocabulary_of_record(record) -> Vocabulary:
    return Vocabulary(record['vocabulary'])


def parameter_facts(record, model_ref, name):
    device = (record or {}).get('devices', {}).get(model_ref)
    if device is None:
        return None
    return next((p for p in device['parameters'] if name in (p['name'], p.get('canonical'))), None)


# ------------------------------------------------------------------------------------------ learner
def learner_class(vocabulary):
    """The optimizer's own SACLearner, or - with a PDK list - a subclass whose only change is that the observations are
    shown to the network through the PDK's view. Weights, losses, saving and the contract are the package's own."""
    from analog_optimizer.training.sac import SACLearner
    if vocabulary is None:
        return SACLearner

    class PdkViewLearner(SACLearner):
        def batch(self, observations, *, digests=None):
            # The network sees new objects (the PDK's view): digests of the recorded observations do not describe
            # them, so the input cache keys the viewed observations by their own content (record 7.221).
            return super().batch([vocabulary.view(o) for o in observations])
    return PdkViewLearner


# ------------------------------------------------------------------------------------------ runs
RUN_FILE = 'network_vocabulary.json'


def requested(config) -> str:
    return getattr(getattr(config.run, 'network', None), 'vocabulary', STANDARD) or STANDARD


def current_vocabulary(name) -> Vocabulary | None:
    """`standard` -> None; `pdk:<id>` -> the currently loaded version of that PDK (PdkError when it is not loaded)."""
    if name in (None, '', STANDARD):
        return None
    if not name.startswith('pdk:'):
        raise PdkError(f'Unknown component list {name!r}')
    record = load_record(name[4:])
    if record is None:
        raise PdkError(f'PDK {name[4:]} is not loaded. Read it in the Virtuoso window first ("PDK window..." reads one by name).')
    return vocabulary_of_record(record)


def run_vocabulary(run_dir) -> Vocabulary | None:
    """The component list a run was started with (its own copy), or None for the standard list."""
    block = read_json(Path(run_dir) / RUN_FILE, default=None)
    if block is None:
        return None
    return Vocabulary(block)


def write_run_vocabulary(run_dir, vocabulary):
    if vocabulary is not None:
        write_json(Path(run_dir) / RUN_FILE, vocabulary.block)


def schema_label(feature_schema) -> str:
    """A saved model's component list in words, from the feature schema its contract records."""
    version = (feature_schema or {}).get('version', '')
    if version.startswith('pdk-'):
        kinds = len((feature_schema or {}).get('device_kinds') or ()) - len(standard_schema().device_kinds)
        return f"PDK {version[4:].rsplit('-', 1)[0]} ({kinds} components, version {version.rsplit('-', 1)[-1][:8]})"
    return 'standard (8 generic kinds)'


# ------------------------------------------------------------------------------------------ reading (reader process)
# The model files of a PDK, kept by the reader between reads (record 7.279): every cell read and every Save task read
# the PDK again, nine downloads and 5.3 MB for GPDK045, 2.5-5 s, for files that do not change. A file is taken from the
# copy only when the simulator host reports the size and modification time recorded when it was downloaded AND the copy
# still has the SHA-256 recorded for it; whatever cannot be told for sure is downloaded, as before. The time is asked
# before a download: a file that changes during one is fetched again next time. Outside the PDK store (pdks/).
STAMP_SKILL = r'''
let((lines)
  lines = nil
  foreach(p list(@PATHS@)
    lines = cons(if(isFile(p) then sprintf(nil "%s|%L|%L" p fileLength(p) fileTimeModified(p)) else sprintf(nil "%s|missing" p))
      lines))
  buildString(reverse(lines) "\n"))
'''


def remote_stamps(client, decode, paths) -> dict:
    """{path: (bytes, modified)} of these model files on the simulator host, in one read-only query; a file not there,
    or not told plainly, is left out. {} when the query fails: then everything is downloaded."""
    paths = [p for p in paths if REMOTE_PATH.match(p or '') and '/../' not in p]
    if not paths:
        return {}
    try:
        result = client.execute_skill(STAMP_SKILL.replace('@PATHS@', ' '.join(f'"{p}"' for p in paths)), timeout=30)
        text = decode(result.output) if result.ok else ''
    except Exception:
        return {}
    stamps = {}
    for line in (text or '').splitlines():
        path, _, rest = line.partition('|')
        size, _, modified = rest.partition('|')
        if path in paths and size.isdigit() and modified.isdigit():
            stamps[path] = (int(size), modified)
    return stamps


class ModelFileCache:
    """The reader's copies of one technology library's model files: `index.json` {remote path: bytes, modified, sha256}
    and the files themselves, named by their SHA-256."""

    def __init__(self, technology_library):
        self.folder = local_settings_dir() / 'pdk-model-files' / technology_library
        index = read_json(self.folder / 'index.json', default={})
        self.index = index if isinstance(index, dict) else {}

    def paths(self):
        return list(self.index)

    def get(self, remote, stamp):
        """The kept bytes of `remote`, or None: not kept, another stamp on the host now, or a copy that changed."""
        known = self.index.get(remote)
        if not stamp or not isinstance(known, dict) or (known.get('bytes'), known.get('modified')) != stamp:
            return None
        try:
            data = (self.folder / str(known.get('sha256'))).read_bytes()
        except OSError:
            return None
        return data if len(data) == stamp[0] and hashlib.sha256(data).hexdigest() == known.get('sha256') else None

    def put(self, remote, stamp, data):
        """Keep a download under the stamp asked for before it - only when its size is that stamp's."""
        if not stamp or len(data) != stamp[0]:
            return
        digest = hashlib.sha256(data).hexdigest()
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if not (self.folder / digest).is_file():
                tmp = self.folder / f'{digest}.part'
                tmp.write_bytes(data)
                tmp.replace(self.folder / digest)
            self.index[remote] = dict(bytes=stamp[0], modified=stamp[1], sha256=digest)
            write_json(self.folder / 'index.json', self.index)
        except OSError:
            pass                                        # a copy not kept is only a download next time


def read_from_virtuoso(client, *, technology_library, model_file, decode=None):
    """Runs in the bridge reader process. Returns the raw material for `finish_load`. The model files go to a temporary
    folder outside the repository and are deleted before this returns; a copy of each is kept for the next read
    (ModelFileCache, record 7.279), and an unchanged file is taken from it instead of downloaded.
    `decode`: the bridge's ``decode_skill_output`` (injectable for tests without the bridge)."""
    if decode is None:
        from virtuoso_bridge import decode_skill_output as decode
    result = client.execute_skill(pdk_skill(technology_library), timeout=180)
    if not result.ok:
        raise RuntimeError('; '.join(result.errors) or 'reading the PDK description failed')
    cdf_text = decode(result.output)
    ideal = read_ideal_parts(client, decode)
    if not REMOTE_PATH.match(model_file or '') or '/../' in model_file:
        raise ValueError('The model file must be an absolute path on the simulator host')
    scratch = Path(tempfile.mkdtemp(prefix='gator-pdk-'))
    cache = ModelFileCache(technology_library)
    try:
        # Breadth first, as before; each level's files new to this read are stamped in one query before any download.
        files, sources, total = {}, [], 0
        stamps = remote_stamps(client, decode, [model_file, *cache.paths()])
        stamping = model_file in stamps                 # a query that failed is not asked again in this read
        level = [model_file]
        while level:
            unstamped = [p for p in level if p not in stamps and p not in files]
            if unstamped and stamping:
                stamps.update(remote_stamps(client, decode, unstamped))
            following = []
            for remote in level:
                if remote in files:
                    continue
                if len(files) >= MAX_MODEL_FILES:
                    raise RuntimeError(f'More than {MAX_MODEL_FILES} model files are included; not read further')
                data = cache.get(remote, stamps.get(remote))
                if data is None:
                    local = scratch / f'{len(files):03d}_{Path(remote).name}'
                    fetched = client.download_file(remote, local, timeout=300)
                    if not fetched.ok or not local.is_file():
                        raise RuntimeError(f"Cannot read {remote} on the simulator host: {'; '.join(fetched.errors or []) or 'download failed'}")
                    data = local.read_bytes()
                    cache.put(remote, stamps.get(remote), data)
                total += len(data)
                if total > MAX_MODEL_BYTES:
                    raise RuntimeError('The model files are larger than the reader accepts')
                text = data.decode('utf-8', errors='replace')
                files[remote] = text
                sources.append(dict(path=remote, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
                for include in includes_of(text):
                    target = posixpath.normpath(include if include.startswith('/') else posixpath.join(posixpath.dirname(remote), include))
                    if REMOTE_PATH.match(target) and target not in files and target not in level and target not in following:
                        following.append(target)
            level = following
        scans = [scan_model_text(text, remote) for remote, text in files.items()]
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return dict(technology_library=technology_library, cdf_text=cdf_text, scans=scans, ideal=ideal,
                sources=dict(model_files=sources, cdf=dict(library=technology_library, lines=len(cdf_text.splitlines()))))


def read_ideal_parts(client, decode, library=IDEAL_LIBRARY) -> dict:
    """Runs in the bridge reader process, with the PDK: the generic library's description in one read-only query.
    Whatever goes wrong is returned as the reason - the PDK itself is read and stored all the same."""
    from .security import redact
    try:
        result = client.execute_skill(ideal_skill(library), timeout=120)
        if not result.ok:
            return dict(library=library, error=redact('; '.join(map(str, result.errors)) or 'the query failed', 400))
        text = decode(result.output)
        return dict(library=library, cdf_text=text) if (text or '').strip() else dict(
            library=library, error=f'Virtuoso knows no library called {library}, or it holds no cell')
    except Exception as exc:
        return dict(library=library, error=redact(f'{type(exc).__name__}: {exc}', 400))


def finish_load(raw) -> dict:
    """Runs in the backend: parse, build, store. Refuses a PDK in which nothing could be recognized."""
    library = raw['technology_library']
    cdf = parse_cdf_text(raw['cdf_text'])
    if not cdf['cells']:
        raise PdkError(f'{library} has no cell with a component description (CDF). Is it the technology library?')
    record = build_record(library, cdf, raw['scans'], sources=raw.get('sources'), technology_library=library)
    if not record['devices']:
        raise PdkError(f'No cell of {library} names a Spectre model that the model files define.')
    record['ideal_parts'] = _ideal_parts_of(raw.get('ideal'), load_record(library))
    return save_record(record)
