"""The Virtuoso side of a task: what the working copy's Maestro view holds, and how it maps onto the editors' rows.

One Maestro test (``GATOR``) on the working copy's testbench holds what the simulation needs and measures:

* ``model_files`` - the model file and section (``maeSetEnvOption`` ``modelFiles``);
* ``initial_conditions`` - a start voltage per net, for a circuit that does not start by itself (an oscillator sits in
  its symmetric DC point forever). They are written into a small file on the simulator host and registered with the
  test as a model file without a section, so Maestro's own netlist ``include``s it and every run deck built from that
  netlist starts the circuit the same way (live probe 2026-09-22: Maestro lists it as ``("<path>")`` and netlists
  ``include "<path>"`` above the PDK model include);
* ``analyses`` - the enabled analyses and the options the workbench set (``maeSetAnalysis``);
* ``outputs`` - named Cadence calculator expressions on testbench nets and branches (``maeAddOutput``): the Probes;
* ``specs`` - a limit on an output (``maeSetSpec`` ``?gt`` / ``?lt`` / ``?range``): the starting Specs rows;
* ``variables`` + ``bindings`` - Maestro design variables and the instance parameters set to them. Only parameters
  whose PDK computes nothing from them may be bound: on the live GPDK045 (2026-09-21) a transistor width set to a
  variable left the 12 side values the PDK derives from it (as, ad, ps, pd, nrd, nrs, sa, sb, sd, sca, scb, scc) at
  their old numbers, so transistor sizes keep the verified path of writing the number through the PDK callbacks.

Mapping onto the rows: an output is a Probes row with ``result_source = ade_output``, its name in ``source_name`` and
its expression in ``signal``; a spec is a Specs row whose equation is that one probe; a variable is the Parameters
row(s) of the instances bound to it. What only the optimizer uses (ranges, weights, hard/soft, scales, units) lives in
the workbench alone and is never compared with Virtuoso.

An expression runs inside the user's Virtuoso session when it is measured, so it must pass ``check_expression``: calls
of listed calculator functions, strings, numbers, design variable names, arithmetic and ``?keyword`` arguments -
nothing else is accepted, and nothing is evaluated here.
"""
from __future__ import annotations

import hashlib
import json
import re
from . import units

TEST = 'GATOR'
# The Maestro simulator mode of a task's test: plain Spectre, what the optimizer's runs use (the run adapter passes no
# +aps). Maestro's default APS takes other time steps, so its numbers would differ from the runs' (seen live
# 2026-09-22).
SIMULATOR_MODE = 'Spectre'
MAX_EXPRESSION = 300                                   # schema.MeasurementDefinition.signal
# Cadence calculator functions an output may call. Anything else is refused, never evaluated.
FUNCTIONS = frozenset('''
VT VF VS VDC VN VN2 IT IF IS IDC OP OPT VAR getData value ymax ymin xmax xmin average rms peakToPeak frequency
cross delay riseTime fallTime slewRate settlingTime overshoot bandwidth gainMargin phaseMargin gainBwProd
unityGainFreq lshift clip dB10 dB20 db mag phase phaseDeg phaseRad real imag abs sqrt exp log log10 integ deriv
pow min max leafValue calcVal iinteg dutyCycle pavg psd spectralPower thd harmonic harmonicFreq ipn ipnVRI
compression compressionVRI stddev
'''.split())
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
# A signal an `ic` statement may name: a node of the testbench (OUT), one inside a subcircuit (XU1.N1) or a plain
# number, as Spectre spells them ("ic 7=0 out=1 OpAmp1.comp=5", spectre -h ic).
IC_NET = re.compile(r'^[A-Za-z_0-9][A-Za-z0-9_.]{0,127}$')
IC_HEADER = '// GATOR initial conditions - written with the task, do not edit\n'
TOKEN = re.compile(r'''\s*(?:(?P<string>"(?:[^"\\]|\\.)*")|(?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[a-zA-Z]?)
                       |(?P<key>\?[A-Za-z_]\w*)|(?P<name>[A-Za-z_]\w*)|(?P<op>[-+*/(),])|(?P<bad>\S))''', re.X)
ANALYSIS_OF = {'VT': 'tran', 'IT': 'tran', 'VF': 'ac', 'IF': 'ac', 'VDC': 'dc', 'IDC': 'dc', 'OP': 'dc', 'VN': 'noise',
    'VN2': 'noise',
               'VS': 'dc', 'IS': 'dc'}
# The analyses a `?result "..."` names (getData, value, ...): an info result such as dcOpInfo or element names none.
RESULT_ANALYSIS = {'dc': 'dc', 'dcOp': 'dc', 'ac': 'ac', 'tran': 'tran', 'noise': 'noise', 'stb': 'stb', 'pss': 'pss',
    'pnoise': 'pnoise'}
RESULT_NAME = re.compile(r'''\?result\s+(?:"([^"]*)"|'([A-Za-z_]\w*))''')
# A unit SUGGESTED from the outermost function of an expression; a Probes row always says it is a suggestion.
UNIT_OF = {'frequency': 'Hz', 'bandwidth': 'Hz', 'unityGainFreq': 'Hz', 'gainBwProd': 'Hz', 'harmonicFreq': 'Hz',
           'riseTime': 's', 'fallTime': 's', 'delay': 's', 'settlingTime': 's', 'slewRate': 'V/s', 'phaseMargin': 'deg',
           'gainMargin': 'dB', 'dB20': 'dB', 'dB10': 'dB', 'db': 'dB', 'phaseDeg': 'deg', 'dutyCycle': '%'}
SPEC_OPS = {'gt': '>=', 'lt': '<=', 'range': 'interval'}


class SetupError(ValueError):
    """Why a setup cannot be written or used, in words the form can show."""


def check_expression(expression, variables=()) -> list[str]:
    """Problems of one output expression (empty = acceptable). Tokenizes; never evaluates."""
    if not isinstance(expression, str) or not expression.strip():
        return ['The expression is empty']
    if len(expression) > MAX_EXPRESSION:
        return [f'The expression is longer than {MAX_EXPRESSION} characters']
    problems, tokens, depth = [], [], 0
    for match in TOKEN.finditer(expression):
        kind = match.lastgroup
        if kind == 'bad':
            problems.append(f'{match.group(kind)!r} is not allowed in an expression')
        tokens.append((kind, match.group(kind)))
    for index, (kind, text) in enumerate(tokens):
        following = tokens[index + 1][1] if index + 1 < len(tokens) else None
        if kind == 'name':
            if following == '(':
                if text not in FUNCTIONS:
                    problems.append(f'{text}() is not a calculator function the workbench accepts')
            elif text not in ('t', 'nil') and text not in variables:
                problems.append(f'{text} is neither a design variable of this setup nor a function call')
        elif text == '(':
            depth += 1
        elif text == ')':
            depth -= 1
            if depth < 0:
                problems.append('Unbalanced brackets')
                break
    if depth > 0:
        problems.append('Unbalanced brackets')
    return list(dict.fromkeys(problems))


def outermost_function(expression):
    """Return the name of the function call an expression starts with, or None when it starts otherwise."""
    match = re.match(r'\s*([A-Za-z_]\w*)\s*\(', expression or '')
    return match.group(1) if match else None


def analysis_of(expression):
    """The analysis an expression reads, from the signal accessors it calls and the results it names (`?result "stb"`);
    'other' when mixed or unknown. The results were not read until 2026-10-03: a loop gain, a phase margin or a noise
    output read through getData came back 'other', so did a DC sweep (VS, IS), and Save task refused the next save
    after "Read setup" ("reads the other analysis, which the Maestro test does not run")."""
    text = expression or ''
    found = {ANALYSIS_OF[name] for name in re.findall(r'([A-Za-z_]\w*)\s*\(', text) if name in ANALYSIS_OF}
    found |= {RESULT_ANALYSIS[name] for pair in RESULT_NAME.findall(text) for name in pair if name in RESULT_ANALYSIS}
    return found.pop() if len(found) == 1 else 'other'


def suggested_unit(expression):
    """Suggest an output unit from recognized functions, falling back to dimensionless."""
    outer = outermost_function(expression)
    if outer in UNIT_OF:
        return UNIT_OF[outer]
    inner = set(re.findall(r'([A-Za-z_]\w*)\s*\(', expression or ''))
    if inner & {'VT', 'VF', 'VS', 'VDC'} and not inner & {'IT', 'IF', 'IS', 'IDC'}:
        return 'V'
    if inner & {'IT', 'IF', 'IS', 'IDC'} and not inner & {'VT', 'VF', 'VS', 'VDC'}:
        return 'A'
    return '1'


# ---------------------------------------------------------------------------------- the setup itself
def canonical(value) -> str:
    """A value as it is compared: a number in one spelling ("1G", "1e+09" and "1000000000" are the same limit),
    anything else as written."""
    try:
        return format(_plain(value), '.12g')
    except (SetupError, ValueError):
        return ' '.join(str(value).split())


def normalize(setup) -> dict:
    """The comparable form of a setup: names sorted, numbers in one spelling, analyses reduced to the options stated."""
    setup = setup or {}
    return dict(
        test=setup.get('test') or TEST, simulator_mode=setup.get('simulator_mode') or SIMULATOR_MODE,
        model_files=sorted([str(f), str(s)] for f, s in setup.get('model_files') or []),
        initial_conditions={str(k): canonical(v) for k, v in sorted((setup.get('initial_conditions') or {}).items())},
        analyses={name: {str(k): canonical(v) for k, v in (options or {}).items()} for name,
            options in sorted((setup.get('analyses') or {}).items())},
        variables={str(k): canonical(v) for k, v in sorted((setup.get('variables') or {}).items())},
        bindings=sorted((dict(cell=b['cell'], instance=b['instance'], parameter=b['parameter'], variable=b['variable'])
                         for b in setup.get('bindings') or []), key=lambda b: (b['cell'], b['instance'],
                             b['parameter'])),
        outputs=[dict(name=o['name'],
            expression=' '.join(str(o['expression']).split())) for o in setup.get('outputs') or []],
        specs=sorted((dict(output=s['output'], op=s['op'],
            value=[canonical(v) for v in s['value']] if isinstance(s['value'], (list,
            tuple)) else canonical(s['value']))
                      for s in setup.get('specs') or []), key=lambda s: s['output']))


def fingerprint(setup) -> str:
    """Hash the normalized setup using sorted JSON keys."""
    return hashlib.sha256(json.dumps(normalize(setup), sort_keys=True).encode()).hexdigest()


def validate(setup, *, bindable=None) -> list[str]:
    """Problems of a setup before anything is written (empty = it may be written)."""
    s, problems = normalize(setup), []
    if not NAME.match(s['test']):
        problems.append(f'Test name {s["test"]!r} is not a plain name')
    # ---- Check output identities, expressions, and the specs that refer to them.
    names = [o['name'] for o in s['outputs']]
    for name in names:
        if not NAME.match(name):
            problems.append(f'Output name {name!r} must be letters, digits and "_"')
    if len(set(names)) != len(names):
        problems.append('Two outputs have the same name')
    for output in s['outputs']:
        problems += [f'{output["name"]}: {p}' for p in check_expression(output['expression'], s['variables'])]
    for spec in s['specs']:
        if spec['output'] not in names:
            problems.append(f'A spec names the output {spec["output"]!r}, which the setup does not have')
        if spec['op'] not in SPEC_OPS:
            problems.append(f'{spec["output"]}: spec kind {spec["op"]!r} is not one of {", ".join(SPEC_OPS)}')
        elif (spec['op'] == 'range') != isinstance(spec['value'], list):
            problems.append(f'{spec["output"]}: a range spec needs two values, the others one')
    # ---- Check variable names, initial conditions, and writable device bindings.
    for name in s['variables']:
        if not NAME.match(name):
            problems.append(f'Variable name {name!r} must be letters, digits and "_"')
    for net, value in s['initial_conditions'].items():
        if not IC_NET.match(net):
            problems.append(
                f'Initial condition on {net!r}: a net is named as Virtuoso spells it (OUT, XU1.N1), without spaces')
        try:
            _plain(value)
        except (SetupError, ValueError):
            problems.append(f'Initial condition on {net}: {value!r} is not a voltage')
    for binding in s['bindings']:
        if binding['variable'] not in s['variables']:
            problems.append(
                f"{binding['instance']}.{binding['parameter']} is bound to {binding['variable']}, which is "
                f'not a variable of the setup')
        if bindable is not None:
            key = (binding['cell'], binding['instance'])
            if key not in bindable:
                problems.append(
                    f"{binding['instance']} in {binding['cell']} cannot be set by a variable: only analogLib "
                    f'resistors, capacitors, inductors and sources can (a PDK device derives other values '
                    f'from its parameters or clamps them; transistor sizes are written as numbers instead)')
            elif binding['parameter'] not in bindable[key]:
                problems.append(
                    f"{binding['instance']} has no parameter {binding['parameter']!r} (it has: "
                    f"{', '.join(sorted(bindable[key]))})")
    for name, options in s['analyses'].items():
        if not NAME.match(name):
            problems.append(f'Analysis name {name!r} is not a plain name')
    return problems


def differences(expected, found) -> list[str]:
    """What the Virtuoso side (`found`, read back) says differently from `expected`, as plain sentences. Analysis
    options Maestro adds by itself are not differences: only the options `expected` states are compared."""
    e, f, out = normalize(expected), normalize(found), []

    def compare(what, left, right):
        for name in sorted(set(left) | set(right)):
            if left.get(name) != right.get(name):
                out.append(
                    f"{what} {name}: the task says {left.get(name, '(none)')}, Virtuoso has "
                    f"{right.get(name, '(none)')}")
    if e['simulator_mode'] != f['simulator_mode']:
        out.append(f'Simulator mode: the task says {e["simulator_mode"]}, Virtuoso has {f["simulator_mode"]}')
    if e['model_files'] != f['model_files']:
        out.append(f'Model files: the task says {e["model_files"]}, Virtuoso has {f["model_files"]}')
    compare('Initial condition on', e['initial_conditions'], f['initial_conditions'])
    for name in sorted(set(e['analyses']) | set(f['analyses'])):
        if name not in f['analyses']:
            out.append(f'Analysis {name} is not enabled in Virtuoso')
        elif name not in e['analyses']:
            out.append(f'Virtuoso also runs a {name} analysis')
        else:
            for key, value in e['analyses'][name].items():
                if f['analyses'][name].get(key) != value:
                    out.append(f'{name} {key}: the task says {value}, Virtuoso has {f["analyses"][name].get(key)}')
    compare('Design variable', e['variables'], f['variables'])
    key = lambda b: (b['cell'], b['instance'], b['parameter'])
    eb, fb = {key(b): b['variable'] for b in e['bindings']}, {key(b): b['variable'] for b in f['bindings']}
    for k in sorted(set(eb) | set(fb)):
        if eb.get(k) != fb.get(k):
            out.append(
                f"{k[1]}.{k[2]} in {k[0]}: the task binds it to {eb.get(k, '(nothing)')}, Virtuoso to "
                f"{fb.get(k, '(nothing)')}")
    compare('Output', {o['name']: o['expression'] for o in e['outputs']},
        {o['name']: o['expression'] for o in f['outputs']})
    compare('Spec on', {s['output']: (s['op'], s['value']) for s in e['specs']}, {s['output']: (s['op'],
        s['value']) for s in f['specs']})
    return out


# ---------------------------------------------------------------------------------- rows <-> setup
def probe_id(output_name) -> str:
    return f'm_{output_name}'


def from_rows(config, *, test=TEST, model_files=(), analyses=None, variables=None, bindings=None,
    initial_conditions=None) -> dict:
    """The setup a configuration's rows ask for: every `ade_output` Probes row is an output (its `signal` holds the
    expression), every active Specs row whose equation is exactly one such probe is that output's spec. Specs over
    several probes, and every optimizer-only field, stay in the workbench."""
    measurements = [m for m in config.measurements if m.result_source == 'ade_output']
    by_probe = {m.measurement_id: m for m in measurements}
    outputs = [dict(name=m.source_name, expression=m.signal or '') for m in measurements]
    specs = []
    for target in config.targets:
        probe = by_probe.get((target.equation or '').strip())
        if probe is None or not target.active:
            continue
        if target.constraint == '>=' and target.lower is not None:
            specs.append(dict(output=probe.source_name, op='gt', value=_number_text(target.lower, target.unit)))
        elif target.constraint == '<=' and target.upper is not None:
            specs.append(dict(output=probe.source_name, op='lt', value=_number_text(target.upper, target.unit)))
        elif target.constraint == 'interval' and target.lower is not None and target.upper is not None:
            specs.append(dict(output=probe.source_name, op='range',
                              value=[_number_text(target.lower, target.unit), _number_text(target.upper, target.unit)]))
    # None = "keep what the copy has": the write leaves that part of the Maestro setup alone.
    return dict(test=test, model_files=[list(m) for m in model_files],
                analyses=None if analyses is None else dict(analyses),
                variables=None if variables is None else dict(variables),
                bindings=None if bindings is None else list(bindings),
                initial_conditions=None if initial_conditions is None else dict(initial_conditions),
                outputs=outputs, specs=specs)


def _number_text(value, unit):
    """A limit as Maestro gets it: in the probe's canonical unit, as a plain number (Maestro has no units)."""
    try:
        return format(units.to_canonical(float(value), unit), '.12g')
    except Exception:
        return format(float(value), '.12g')


def to_rows(setup) -> dict:
    """Probes and Specs rows that say what the setup says. Units are SUGGESTED from each expression and marked so;
    what only the optimizer uses gets the schema's defaults (and a normalization scale from the limit)."""
    s = normalize(setup)
    probes, specs = [], []
    for output in s['outputs']:
        unit = suggested_unit(output['expression'])
        probes.append(dict(measurement_id=probe_id(output['name']), analysis=analysis_of(output['expression']),
                           result_source='ade_output', source_name=output['name'], signal=output['expression'],
                           unit=unit,
                           notes=f'Maestro output {output["name"]} of the working copy (test {s["test"]}). '
                                 f'Unit {unit!r} suggested from the expression - check it.'))
    units_of = {p['source_name']: p['unit'] for p in probes}
    for spec in s['specs']:
        values = [float(_plain(v)) for v in (spec['value'] if isinstance(spec['value'], list) else [spec['value']])]
        row = dict(metric_id=spec['output'], equation=probe_id(spec['output']), unit=units_of.get(spec['output'], '1'),
                   constraint=SPEC_OPS[spec['op']], normalization_scale=max(abs(v) for v in values) or 1.0,
                   basis=f'Maestro spec on {spec["output"]} in the working copy (test {s["test"]}).')
        if spec['op'] == 'gt':
            row['lower'] = values[0]
        elif spec['op'] == 'lt':
            row['upper'] = values[0]
        else:
            row['lower'], row['upper'] = sorted(values)
        specs.append(row)
    return dict(measurements=probes, targets=specs)


SUFFIX = dict(T=1e12, G=1e9, M=1e6, K=1e3, k=1e3, m=1e-3, u=1e-6, n=1e-9, p=1e-12, f=1e-15, a=1e-18)


def _plain(text) -> float:
    """A Cadence number ("1G", "50n", "2.5e-9") as a float."""
    text = str(text).strip()
    match = re.fullmatch(r'([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([TGMKkmunpfa]?)', text)
    if not match:
        raise SetupError(f'{text!r} is not a number Maestro would write')
    return float(match.group(1)) * SUFFIX.get(match.group(2), 1.0)


# ---------------------------------------------------------------------------------- Maestro's own deck (task flow part
# 5)
DECK_FORMAT = 'gator-maestro-deck-1'
ANALYSIS_STATEMENT = re.compile(r'^\s*[A-Za-z_]\w*\s+(?:\([^)]*\)\s*)?'     # terminals of e.g. `noise ( VOUT 0 ) noise`
                                r'(tran|ac|dc|noise|xf|sp|stb|pss|pac|pnoise|pxf|hb|hbac|hbnoise)\b')


def split_deck(deck, circuit) -> tuple[str, str]:
    """(head, tail) of Maestro's deck of one test around the circuit part it netlisted (`circuit`, its file `netlist`):
    the head holds the header, the design variables and the model include; the tail the options, analyses, info and
    saves. Every evaluation of a Maestro-measured task puts the circuit the run adapter exported between the two.
    A deck whose circuit part is not there exactly once is refused, not guessed at."""
    body = str(circuit).strip('\n')
    if not body or deck.count(body) != 1:
        raise SetupError(
            'Maestro\'s netlist does not hold its circuit part exactly once: its layout is not the one this '
                         'workbench reads')
    index = deck.index(body)
    head, tail = deck[:index], deck[index + len(body):]
    if not re.search(r'(?m)^simulator lang=spectre\s*$', head) or not re.search(r'(?m)^include\s+"[^"]+"', head):
        raise SetupError('Maestro\'s netlist head lacks its simulator line or its model include')
    return head, tail


def deck_includes(head) -> list[tuple[str, str | None]]:
    """Every `include` of a deck head, in order: (file, section or None)."""
    return [(m.group(1), m.group(2)) for m in re.finditer(r'(?m)^include\s+"([^"]+)"(?:\s+section=(\S+))?', head)]


def deck_include(head) -> tuple[str, str | None]:
    """(model file, section) of the MODEL include in a deck head: the one that names a section. A task with initial
    conditions has a second include - the ic file - which names none, so the section decides which is the model."""
    found = deck_includes(head)
    with_section = [item for item in found if item[1]]
    if len(with_section) == 1:
        return with_section[0]
    if not found:
        raise SetupError('The deck head has no model include')
    if len(found) == 1:
        return found[0]
    listed = ', '.join(f'{f} (section {s})' if s else f for f, s in found)
    raise SetupError(f'The deck head has no single model include with a section: {listed}')


def ic_file_text(conditions) -> str:
    """The ic file of a task: one `ic` statement, the nets in one order, numbers in one spelling."""
    items = ' '.join(f'{net}={canonical(value)}' for net, value in sorted((conditions or {}).items()))
    return IC_HEADER + (f'ic {items}\n' if items else '')


def parse_ic_file(text) -> dict:
    """The conditions an ic file states ({net: value}); comments and anything else are ignored."""
    found = {}
    for line in (text or '').splitlines():
        statement = line.split('//')[0].strip()
        if not statement.startswith('ic ') and statement != 'ic':
            continue
        for item in statement[3:].split():
            net, _, value = item.partition('=')
            if net and value:
                found[net] = value
    return found


def deck_analyses(tail) -> list[str]:
    """The analysis types a deck tail runs, in order (e.g. ['tran'])."""
    return [m.group(1) for m in (ANALYSIS_STATEMENT.match(line) for line in tail.splitlines()) if m]
