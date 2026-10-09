"""A PDK's model files read as text (Spectre and SPICE syntax): the models and subcircuits they define, the files they
include, each element's family (a MOS, a resistor, a capacitor, ...) and the role of each of its pins.

Moved from pdk.py by the refactoring (docs/plan-refactoring.md); pdk.py re-exports every name.
"""
from __future__ import annotations

import re
from pathlib import Path


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


PASSIVE = ('resistor', 'capacitor', 'varactor', 'inductor')


# CDF `units` names -> the workbench's canonical units (units.py), and the reference scale of each canonical unit: the
# same scale the standard list uses for a length / capacitance / resistance / inductance / voltage.
CDF_UNITS = {'lengthMetric': 'm', 'lengthEnglish': 'm', 'resistance': 'ohm', 'capacitance': 'F', 'inductance': 'H',
             'voltage': 'V', 'current': 'A', 'time': 's', 'frequency': 'Hz', 'power': 'W', 'temperature': 'degC',
             'angle': 'deg'}


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
def file_line(entry):
    return f"{Path(entry['file']).name}:{entry['line']}"


def _element_family(element, subckt, scan, depth=0):
    """(family, polarity, basis) of one element inside a subcircuit."""
    master = element['master']
    local = subckt['models'].get(master) or scan['models'].get(master)
    if local is not None:
        family = PRIMITIVE_FAMILY.get(local['primitive'])
        return family, local.get('type'), f"model {master} = {local['primitive']}{', type=' + local['type'] if local.get('type') else ''} ({file_line(local)})"
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
        return found['family'], found.get('polarity'), f"subcircuit {master} ({file_line(inner)}): {found['family_basis']}"
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
                    family_basis=f"model {name} = {model['primitive']}{', type=' + model['type'] if model.get('type') else ''} ({file_line(model)})"
                    if family else f"model {name} uses primitive {model['primitive']}, which is not classified here ({file_line(model)})")
    subckt = scan['subckts'].get(name)
    if subckt is None:
        return dict(family='other', polarity=None, core=None, family_basis=f'{name} is not defined in the model files read')
    if subckt['inline']:
        main = next((e for e in subckt['elements'] if e['name'] == name), None)
        if main is not None:
            family, polarity, basis = _element_family(main, subckt, scan, depth)
            if family:
                return dict(family=family, polarity=polarity, core=main,
                            family_basis=f'inline subcircuit {name} ({file_line(subckt)}): its own element uses {basis}')
    active = [(e, *_element_family(e, subckt, scan, depth)) for e in subckt['elements']]
    for wanted in ('mos', 'bjt'):
        cores = [item for item in active if item[1] == wanted and len(item[0]['nodes']) >= (4 if wanted == 'mos' else 3)]
        if len(cores) == 1:
            element, family, polarity, basis = cores[0]
            return dict(family=family, polarity=polarity, core=element,
                        family_basis=f"subcircuit {name} ({file_line(subckt)}): element {element['name']} uses {basis}")
        if len(cores) > 1:
            return dict(family='other', polarity=None, core=None,
                        family_basis=f'subcircuit {name} ({file_line(subckt)}) holds {len(cores)} {wanted} elements')
    if len(subckt['pins']) < 2:
        return dict(family='other', polarity=None, core=None, family_basis=f'subcircuit {name} has fewer than two pins')
    paths = _paths(subckt, scan, subckt['pins'][0], subckt['pins'][1], set(subckt['pins'][2:]))
    on_path = {family for path in paths for family in path}
    candidates = on_path & set(PASSIVE)
    declared = {CDF_UNITS.get(u) for u in cdf_units}
    by_unit = {'ohm': 'resistor', 'F': 'capacitor', 'H': 'inductor'}
    where = f'subcircuit {name} ({file_line(subckt)})'
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


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_where = file_line
