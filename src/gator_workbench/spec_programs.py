"""Compile measurement expressions without learning probe, spec or instance names.

The program retains operand order, constants, windows and crossing directions.
Unsupported syntax/results stay explicit unknown tokens, never guessed from a
metric's display name. Addresses are resolved against each observation's graph.
"""
import ast
import math

from . import spec_descriptors as descriptors, spec_equations, units


def spec_program_schema():
    from analog_optimizer.models.inputs import SpecSetSchema, SPEC_PROGRAM_LAYOUT
    from analog_optimizer.models.measurement_program import PROGRAM_VERSION
    return SpecSetSchema(PROGRAM_VERSION, descriptors.DESCRIPTOR_COLUMNS, descriptors.UNIT_REFERENCES,
                         layout=SPEC_PROGRAM_LAYOUT)


def _node(op, children=(), **values):
    from analog_optimizer.models.measurement_program import OPERATIONS
    return dict(op=op if op in OPERATIONS else 'unknown', children=list(children), **values)


def _address(path, kind, role):
    return dict(kind=kind, id=str(path).strip().lstrip('/'), role=role)


def _ocean(tree):
    if tree is None:
        return _node('unknown')
    if tree.kind == 'number':
        return _node('number', value=float(tree.value))
    if tree.kind in ('add', 'sub', 'mul', 'div', 'neg'):
        return _node(tree.kind, map(_ocean, tree.children))
    if tree.kind in ('name', 'string'):
        # Fixed semantic literals only. A signal path is handled by its probe call.
        return _node({'t': 'true', 'rise': 'rising', 'fall': 'falling'}.get(str(tree.value).lower(), str(tree.value).lower()))
    if tree.kind == 'keyword':
        return _node(str(tree.value).lower(), map(_ocean, tree.children))
    name = str(tree.value)
    if name in descriptors._VOLTAGE or name in descriptors._CURRENT:
        voltage = name in descriptors._VOLTAGE
        children = []
        for i, child in enumerate(tree.children):
            if child.kind != 'string':
                children.append(_ocean(child))
                continue
            path = child.value.strip().lstrip('/')
            role = 'voltage' if voltage else 'current'
            if voltage and i:
                role = 'reference'
            if not voltage and '/' in path:
                device, _, terminal = path.rpartition('/')
                pin = {'d': 'drain', 'g': 'gate', 's': 'source', 'b': 'bulk',
                       'plus': 'positive', 'minus': 'negative'}.get(terminal.lower())
                if pin:
                    path, role = device, pin
            children.append(_node('voltage' if voltage else 'current',
                                  bindings=[_address(path, 'net' if voltage else 'device', role)]))
        if voltage and sum(c.kind == 'string' for c in tree.children) == 1:
            children.append(_node('reference', bindings=[dict(kind='net', selector='ground', role='reference')]))
        # Preserve VF/VM/VP/VR/VI etc. as explicit transformations, not name embeddings.
        result = _node('voltage' if voltage else 'current', children)
        transform = {'VM': 'mag', 'IM': 'mag', 'VP': 'phase', 'IP': 'phase',
                     'VR': 'real', 'IR': 'real', 'VI': 'imag', 'II': 'imag'}.get(name)
        result = _node(transform, [result]) if transform else result
        return _node(name.lower(), [result])
    if name == 'getData':
        signal = descriptors._first_string(tree) or ''
        kind = {'loopGain': 'loopgain', 'out': 'outputnoise'}.get(signal, 'getdata')
        # A source name used by xf is an address, never a learned categorical ID.
        result = descriptors._keyword(tree, 'result')
        bindings = []
        if result is not None and str(result.value) == 'xf':
            kind, bindings = 'transfer', [_address(signal, 'device', 'excitation')]
        children = [_ocean(c) for c in tree.children if c.kind != 'string']
        if kind == 'getdata':
            children.append(_node('unknown'))
        return _node(kind, children, bindings=bindings)
    return _node({'db': 'db20'}.get(name.lower(), name.lower()), map(_ocean, tree.children))


def _arithmetic(tree, name_lookup, patterns=()):
    if isinstance(tree, ast.Expression):
        return _arithmetic(tree.body, name_lookup, patterns)
    if isinstance(tree, ast.Constant) and isinstance(tree.value, (int, float)) and math.isfinite(tree.value):
        return _node('number', value=float(tree.value))
    if isinstance(tree, ast.Constant) and isinstance(tree.value, str) and tree.value.isdigit():
        index = int(tree.value)
        if index < len(patterns):
            return _node('width', bindings=[dict(_address(patterns[index], 'device', 'size'), pattern=True)])
    if isinstance(tree, ast.Name):
        return name_lookup(tree.id)
    if isinstance(tree, ast.UnaryOp):
        child = _arithmetic(tree.operand, name_lookup, patterns)
        return _node('neg', [child]) if isinstance(tree.op, ast.USub) else child
    if isinstance(tree, ast.BinOp):
        op = {ast.Add: 'add', ast.Sub: 'sub', ast.Mult: 'mul', ast.Div: 'div', ast.Pow: 'pow'}.get(type(tree.op), 'unknown')
        return _node(op, [_arithmetic(tree.left, name_lookup, patterns), _arithmetic(tree.right, name_lookup, patterns)])
    if isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name):
        return _node(tree.func.id, [_arithmetic(c, name_lookup, patterns) for c in tree.args])
    return _node('unknown')


def describe_programs(config, bench=None):
    """A tree per target. The graph view pins the complete trees in its input key."""
    from analog_optimizer.netlist.expressions import NUMBER, SCALES
    bench = descriptors.bench_of_task(config) if bench is None else bench
    probes = {p.measurement_id: p for p in config.measurements}

    def probe(name):
        if name not in probes:
            return _node('unknown')
        p = probes[name]
        if p.result_source == 'size_estimate':
            parsed, _, error = spec_equations._size_tree(p.signal)
            inner = (_arithmetic(parsed[0], lambda _: _node('unknown'), parsed[1])
                     if error is None else _node('unknown'))
        elif p.result_source == 'backend_profile':
            inner = _node('analyzer', [_node('unknown')])
        else:
            inner = _ocean(descriptors.parse_expression(p.signal))
        stimuli = [_node('excitation', bindings=[_address(s, 'device', 'excitation')])
                   for s in sorted(bench.ac_sources)] if p.analysis in ('ac', 'stb', 'noise', 'pnoise') else []
        unit = units.canonical_unit(p.unit) if units.known(p.unit) else p.unit
        return _node('probe', [_node(p.analysis, [inner, _node('excitation', stimuli)]), _node('unit:' + unit)])

    programs = {}
    for target in config.targets:
        text = target.equation.strip()
        if text in probes:
            tree = probe(text)
        elif spec_equations.parse(text)[1] is None:
            normalized = NUMBER.sub(lambda m: repr(float(m[1]) * SCALES.get(m[2], 1.)), text)
            tree = _arithmetic(ast.parse(normalized, mode='eval'), probe)
        else:
            tree = _node('unknown')
        programs[target.metric_id] = tree
    return programs
