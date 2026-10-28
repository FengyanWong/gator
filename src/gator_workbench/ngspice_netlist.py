"""An ngspice (SPICE) netlist read into the optimizer's circuit graph, and written back with new sizes.

The workbench's second circuit language (2026-09-23). The Spectre subset lives in
``analog_optimizer.netlist.spectre_parser`` and is not touched (its source digest gates the checkpoints);
this module produces the SAME ``CircuitGraph`` objects for a SPICE deck, so everything downstream - the
Parameters editor, the network's view of the circuit, the environment's contract check - works unchanged.

What is read (a subset, source-located, never executed):

* element lines by their first letter: ``R C L M X D Q J V I E G F H B S``; ``+`` continuation lines; ``*``
  comment lines; ``$`` and ``;`` inline comments; the first line is the title, as in every SPICE deck;
* ``.subckt`` / ``.ends`` with ``params:`` defaults, ``X`` instances expanded into ``X1/M1`` device paths (the
  spelling the Spectre reader uses too); ``.param`` at top level and inside a subcircuit; ``.global``;
* values: SPICE numbers (``4u``, ``1k``, ``10Meg``, ``2.5e-6``, trailing letters ignored: ``1kohm``) and
  ``{expressions}`` / ``'expressions'`` over parameters with a whitelist evaluator (never ``eval``);
* ``.model <name> <type>`` lines in the deck and in the files ``.include`` / ``.lib`` name, read for the model
  TYPES only (nmos, pmos, npn, d, r, ...) - their contents are never copied, shown or sent anywhere;
* ``.meas`` statements (in the deck and inside ``.control``): their names are the results a run can measure;
* the analyses (``.op .dc .ac .tran .noise ...``) as the analysis context.

What the network sees: the kinds of the standard vocabulary only (``pyg_converter.FeatureSchema``: unknown, nmos,
pmos, resistor, capacitor, inductor, vsource, isource). A diode, a bipolar, a switch, a behavioural source, an
instance of a subcircuit that the deck does not define (a PDK cell) is ``unknown`` unless the task's ``device_kinds``
say what it is (``sky130_fd_pr__nfet_01v8=nmos``). Unknown is a warning, not an error: ngspice simulates the whole
deck whatever the network knows of it; only an unknown device cannot be SIZED.

Sizes that can be varied: a numeric parameter of a top-level element, or of an element inside a subcircuit the deck
instantiates EXACTLY ONCE (a testbench around one DUT). Inside a subcircuit used twice, changing the definition would
change both instances - such a parameter is shown but not offered. Writing back replaces the value's own token in
the deck (``W=4u`` -> ``W=4.5e-06``, ``{wn}`` -> the number), nothing else moves; the result is re-read to prove it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re

from analog_optimizer.graph.circuit_graph import (CircuitGraph, Connection, Device, Diagnostic, Net, ParameterValue,
                                                    SourceSpan)


# Compatibility facade: existing imports keep working; graph construction remains in this module.
from .ngspice_syntax import (
    SCALES, NUMBER, NAME, NetlistError, Token,
    Measurement, Sizable, Parsed, number, _FUNCTIONS,
    _EXPRESSION_NUMBER, Unresolved, evaluate, strip_comment, tokenize,
    statements, _split, _value_token
)
from .ngspice_results import (
    MEASURE_ANALYSES, _guess_unit, NAME_UNITS, unit_from_name, expression_unit,
    _measure, RESULT_LINE, FAILURE_PATTERNS, read_results, classify_failure
)
from .ngspice_writer import (
    format_value, rewrite, deck_text
)

# Preserve the import path of data classes that callers may have pickled.
for _definition in (NetlistError, Token, Measurement, Sizable, Parsed, Unresolved):
    _definition.__module__ = __name__

PARSER_VERSION = 'ngspice-subset-1'
# The network's vocabulary (analog_optimizer.graph.pyg_converter.FeatureSchema): a kind outside it cannot be encoded.
KINDS = ('unknown', 'nmos', 'pmos', 'resistor', 'capacitor', 'inductor', 'vsource', 'isource')
ROLES = {'nmos': ('drain', 'gate', 'source', 'bulk'), 'pmos': ('drain', 'gate', 'source', 'bulk'),
         'resistor': ('positive', 'negative'), 'capacitor': ('positive', 'negative'), 'inductor': ('positive', 'negative'),
         'vsource': ('positive', 'negative'), 'isource': ('positive', 'negative')}
# .model types -> the kind the network can see. Everything else (npn, pnp, njf, sw, ...) is unknown.
MODEL_KINDS = {'nmos': 'nmos', 'pmos': 'pmos', 'r': 'resistor', 'c': 'capacitor', 'l': 'inductor'}
# The one parameter each two-terminal element is sized by (the optimizer's kind names: r, c, ind, dc), the MOS names.
MOS_PARAMETERS = {'w': 'w', 'l': 'l', 'm': 'm', 'nf': 'nf'}
VALUE_PARAMETER = {'R': 'r', 'C': 'c', 'L': 'ind', 'V': 'dc', 'I': 'dc'}
ELEMENT_KINDS = {'R': 'resistor', 'C': 'capacitor', 'L': 'inductor', 'V': 'vsource', 'I': 'isource'}
NODE_COUNT = {'R': 2, 'C': 2, 'L': 2, 'V': 2, 'I': 2, 'D': 2, 'J': 3, 'Z': 3, 'S': 4, 'B': 2, 'E': 2, 'G': 2, 'F': 2, 'H': 2}
GROUND = ('0', 'gnd')
MODEL_SCAN_BYTES = 48 * 1024 * 1024        # how much of the included model files is read for their .model types, at most
MAX_INCLUDE_DEPTH = 8


# ------------------------------------------------------------------------------------------------ model types
_MODEL_LINE = re.compile(r'^\s*\.model\s+([\w.\-:$#@!]+)\s+([A-Za-z]\w*)', re.IGNORECASE | re.MULTILINE)
_SUBCKT_LINE = re.compile(r'^\s*\.subckt\s+([\w.\-:$#@!]+)((?:[ \t]+[^\s]+)*)', re.IGNORECASE | re.MULTILINE)
_INCLUDE_LINE = re.compile(r'^\s*\.(include|inc|lib)\s+("[^"]*"|\'[^\']*\'|[^\s]+)', re.IGNORECASE | re.MULTILINE)


def _unquote(text):
    return text[1:-1] if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'' else text


def scan_models(text, *, root, depth=0, budget=None, seen=None, found=None, subckts=None, notes=None):
    """`.model` names -> types and `.subckt` names -> port counts from `text` and the files it includes (relative paths
    under `root`). Model files are read for these two facts only, within MODEL_SCAN_BYTES; a file that cannot be read,
    or the budget, is noted and never an error - the simulator reads the real thing."""
    found = {} if found is None else found
    subckts = {} if subckts is None else subckts
    notes = [] if notes is None else notes
    seen = set() if seen is None else seen
    budget = [MODEL_SCAN_BYTES] if budget is None else budget
    for match in _MODEL_LINE.finditer(text):
        name, kind = match.group(1).lower(), match.group(2).lower()
        base = name.split('.')[0] if re.search(r'\.\d+$', name) else name     # binned models: nch.1, nch.2 -> nch
        found.setdefault(base, kind)
        found.setdefault(name, kind)
    for match in _SUBCKT_LINE.finditer(text):
        words = match.group(2).split()
        ports = [w for w in words if '=' not in w and w.lower() != 'params:']
        subckts.setdefault(match.group(1).lower(), len(ports))
    if depth >= MAX_INCLUDE_DEPTH:
        return found, subckts, notes
    for match in _INCLUDE_LINE.finditer(text):
        target = _unquote(match.group(2))
        path = Path(target)
        if not path.is_absolute():
            if root is None:
                notes.append(f'{target}: a relative include; its models are unknown until the netlist has a folder')
                continue
            path = Path(root) / path
        try:
            key = path.resolve()
            if key in seen:
                continue
            seen.add(key)
            size = key.stat().st_size
            if size > budget[0]:
                notes.append(f'{target}: not scanned for model types ({size} bytes; the scan budget is used up)')
                continue
            budget[0] -= size
            included = key.read_text(errors='replace')
        except OSError as exc:
            notes.append(f'{target}: cannot be read here ({type(exc).__name__}); its model types stay unknown')
            continue
        scan_models(included, root=key.parent, depth=depth + 1, budget=budget, seen=seen, found=found, subckts=subckts, notes=notes)
    return found, subckts, notes


# ------------------------------------------------------------------------------------------------ the parser
@dataclass
class _Scope:
    name: str | None
    ports: tuple = ()
    params: dict = field(default_factory=dict)      # name -> raw text
    body: list = field(default_factory=list)


class _Env:
    def __init__(self, definitions, parent=None, overrides=None):
        self.definitions, self.parent, self.overrides = definitions, parent, overrides or {}
        self.cache, self.active = {}, set()

    def lookup(self, name):
        key = name.lower()
        if key in self.overrides:
            return self.overrides[key]
        if key in self.cache:
            return self.cache[key]
        if key in self.active:
            raise Unresolved(f'cyclic parameter {name}')
        if key not in self.definitions:
            if self.parent is not None:
                return self.parent.lookup(name)
            raise Unresolved(f'unknown parameter {name}')
        self.active.add(key)
        try:
            value = evaluate(self.definitions[key], self.lookup)
            self.cache[key] = value
            return value
        finally:
            self.active.discard(key)


def parse_text(text, *, source='<memory>', circuit_id='ngspice', device_kinds=None, include_root=None,
               scan_includes=True) -> Parsed:
    """Read a deck. `device_kinds`: {model or subckt name: kind} the user declares for what the deck does not say.
    `include_root`: the folder relative includes are resolved from (the netlist's own folder when it came from a file)."""
    lines = text.split('\n')
    title, stmts, has_control, control_lines = statements(lines)
    kinds_given = {str(k).lower(): str(v).lower() for k, v in (device_kinds or {}).items()}
    for name, kind in kinds_given.items():
        if kind not in KINDS:
            raise NetlistError(f'device kind {kind!r} for {name!r} is not one of {", ".join(KINDS)}')
    (root, scopes, globals_, analyses, measurements, includes,
     has_end, diagnostics) = _collect_deck_statements(stmts, source)
    _read_control_outputs(control_lines, source, measurements, analyses)
    # model types: the deck itself, then its included files (read for their .model / .subckt lines only)
    model_types, external_subckts, notes = scan_models(text, root=include_root) if scan_includes else scan_models(text, root=None, depth=MAX_INCLUDE_DEPTH)
    for note in notes:
        diagnostics.append(Diagnostic('include_not_scanned', note, SourceSpan(source, 1), 'warning'))

    graph = CircuitGraph(circuit_id, [], [], [], {}, metadata={
        'parser_version': PARSER_VERSION, 'simulator': 'ngspice', 'title': title, 'analysis_context': analyses,
        'source_manifest': {source: hashlib.sha256(text.encode()).hexdigest()}, 'selected_top': None,
        'globals': sorted(globals_), 'measurements': [m.name for m in measurements],
        'scope_parameters': {name or '<root>': dict(s.params) for name, s in [(None, root), *scopes.items()]}})
    nets, sizables, unknown_models, subckt_uses = {}, {}, [], {name: 0 for name in scopes}
    net, resolve, kind_of = _graph_resolvers(globals_, nets, source, diagnostics, kinds_given, model_types)

    def expand(current, env, path, port_map, ancestry):
        if len(ancestry) > 32:
            raise NetlistError('subcircuit nesting deeper than 32')
        seen = set()
        for tokens in current.body:
            head = tokens[0]
            name = head.text
            letter = name[0].upper()
            if name.lower() in seen:
                raise NetlistError(f'line {head.line}: instance {name} appears twice in {current.name or "the deck"}')
            seen.add(name.lower())
            identifier = f'{path}/{name}' if path else name
            positional, named = _split(tokens)
            span = SourceSpan(source, head.line, head.column + 1)
            if letter == 'X':
                if not positional:
                    raise NetlistError(f'line {head.line}: {name} names no subcircuit')
                sub = positional[-1].text.lower()
                ports = [t.text for t in positional[:-1]]
                child = scopes.get(sub)
                if child is not None:
                    if sub in ancestry:
                        raise NetlistError(f'line {head.line}: subcircuit {sub} instantiates itself')
                    if len(ports) != len(child.ports):
                        raise NetlistError(f'line {head.line}: {name} connects {len(ports)} nodes, subcircuit {sub} has {len(child.ports)} ports')
                    subckt_uses[sub] += 1
                    overrides = {}
                    for key, token in named.items():
                        value = resolve(_value_token(token), env, f'{identifier}.{key}')
                        if value.valid:
                            overrides[key] = value.value
                    actual = [net(p, path, port_map) for p in ports]
                    expand(child, _Env(child.params, env, overrides), identifier,
                           {p.lower(): n for p, n in zip(child.ports, actual)}, (*ancestry, sub))
                    continue
                # an instance of a subcircuit the deck does not define: a PDK cell (its kind from device_kinds)
                kind = kinds_given.get(sub, 'unknown')
                expected = external_subckts.get(sub)
                if expected is not None and expected != len(ports):
                    diagnostics.append(Diagnostic('port_count', f'{identifier}: {len(ports)} nodes, but {sub} has {expected} ports',
                                                  span, 'warning'))
                roles = ROLES.get(kind)
                if roles is not None and len(ports) != len(roles):
                    diagnostics.append(Diagnostic('port_count', f'{identifier}: {sub} is declared {kind} ({len(roles)} terminals) '
                                                  f'but connects {len(ports)} nodes', span, 'warning'))
                    roles, kind = None, 'unknown'
                if kind == 'unknown':
                    unknown_models.append(sub)
                    diagnostics.append(Diagnostic('unknown_device', f'{identifier}: subcircuit {sub} is not defined in the '
                                                  'netlist and its kind is not declared', span, 'warning'))
                terminals = tuple(f'port_{i}' for i in range(len(ports))) if roles is None else \
                    tuple(('d', 'g', 's', 'b') if len(roles) == 4 else ('p', 'n'))
                roles = roles or ('unknown',) * len(ports)
                graph.devices.append(Device(identifier, kind, sub, terminals, span))
                values = {}
                for key, token in named.items():
                    canonical = MOS_PARAMETERS.get(key, key) if kind in ('nmos', 'pmos') else key
                    values[canonical] = ParameterValue(*_with_name(resolve(_value_token(token), env, f'{identifier}.{key}', numeric=False), key))
                    if canonical in ('w', 'l', 'm', 'nf') and values[canonical].valid and kind in ('nmos', 'pmos'):
                        sizables[(identifier, canonical)] = Sizable(identifier, canonical, key, _value_token(token), current.name)
                graph.parameters[identifier] = values
                for ordinal, (terminal, role, target) in enumerate(zip(terminals, roles, [net(p, path, port_map) for p in ports])):
                    graph.connections.append(Connection(identifier, target, terminal, ordinal, role))
                continue
            if letter in ('K', 'T', 'O', 'U', 'A', 'N', 'P', 'Y', 'W'):
                diagnostics.append(Diagnostic('unsupported_element', f'{identifier}: a {letter} element is simulated by ngspice '
                                              'but not shown to the network', span, 'warning'))
                continue
            if letter not in 'RCLMDQJZVIEGFHBS':
                raise NetlistError(f'line {head.line}: {name!r} is not an element the reader knows')
            # nodes and model: the first `count` positional tokens are nodes; the next one, if any, the model
            model = None
            if letter == 'M':
                count = 4
                if len(positional) < 5:
                    raise NetlistError(f'line {head.line}: {name} needs four nodes and a model')
                model = positional[4].text.lower()
            elif letter == 'Q':
                rest = positional[3:]
                if len(rest) >= 2 and rest[1].text.lower() in model_types and rest[0].text.lower() not in model_types:
                    count, model = 4, rest[1].text.lower()
                elif rest:
                    count, model = 3, rest[0].text.lower()
                else:
                    raise NetlistError(f'line {head.line}: {name} needs three nodes and a model')
            else:
                count = NODE_COUNT[letter]
                if letter in ('D', 'J', 'Z', 'S'):
                    if len(positional) <= count:
                        raise NetlistError(f'line {head.line}: {name} needs {count} nodes and a model')
                    model = positional[count].text.lower()
                elif letter in ELEMENT_KINDS and len(positional) > count and number(positional[count].text) is None \
                        and not positional[count].text.startswith(('{', "'", '"')) \
                        and positional[count].text.lower() not in ('dc', 'ac', 'pulse', 'sin', 'pwl', 'exp', 'sffm', 'am', 'trnoise', 'trrandom') \
                        and (positional[count].text.lower() in model_types or letter in 'RCL' and len(positional) == count + 1 and 'r' not in named and 'c' not in named and 'l' not in named):
                    model = positional[count].text.lower()
            if len(positional) < count:
                raise NetlistError(f'line {head.line}: {name} needs {count} nodes')
            kind, roles, _ = kind_of(letter, model, [t.text.lower() for t in positional])
            if kind == 'unknown' and letter in ('M', 'D', 'Q', 'J', 'Z', 'S') and model:
                unknown_models.append(model)
                diagnostics.append(Diagnostic('unknown_device', f'{identifier}: model {model} has no known kind '
                                              + ('' if model in model_types else '(no .model line for it was found)'), span, 'warning'))
            elif kind == 'unknown' and letter in 'EGFHB':
                diagnostics.append(Diagnostic('unknown_device', f'{identifier}: a {letter} source is shown as unknown', span, 'warning'))
            node_tokens = positional[:count]
            if letter in ('M', 'D', 'Q', 'J', 'Z', 'S') or roles is None:
                terminals = ('d', 'g', 's', 'b') if letter == 'M' else tuple(f'port_{i}' for i in range(count))
                roles = roles or ('unknown',) * count
                if len(roles) != count:
                    roles = ('unknown',) * count
            else:
                terminals = ('p', 'n')
            graph.devices.append(Device(identifier, kind, model or letter.lower(), terminals, span))
            values = {}
            # the sized value: MOS W/L/M/NF, or the positional value of R C L V I (`R1 a b 1k`, `V1 a 0 dc 1.8`)
            if letter == 'M':
                for key, token in named.items():
                    canonical = MOS_PARAMETERS.get(key, key)
                    values[canonical] = ParameterValue(*_with_name(resolve(_value_token(token), env, f'{identifier}.{key}',
                                                                           numeric=key in MOS_PARAMETERS), key))
                    if canonical in MOS_PARAMETERS.values() and values[canonical].valid and kind != 'unknown':
                        sizables[(identifier, canonical)] = Sizable(identifier, canonical, key, _value_token(token), current.name)
            elif letter in ELEMENT_KINDS:
                canonical = VALUE_PARAMETER[letter]
                value_token = None
                tail = positional[count + (1 if model else 0):]
                if letter in ('V', 'I'):
                    lowered = [t.text.lower() for t in tail]
                    if 'dc' in lowered and lowered.index('dc') + 1 < len(tail):
                        value_token = tail[lowered.index('dc') + 1]
                    elif tail and tail[0].text.lower() not in ('ac', 'pulse', 'sin', 'pwl', 'exp', 'sffm', 'am', 'trnoise', 'trrandom'):
                        value_token = tail[0]
                    if 'dc' in named:
                        value_token = _value_token(named['dc'])
                else:
                    own = {'R': 'r', 'C': 'c', 'L': 'l'}[letter]
                    if own in named:
                        value_token = _value_token(named[own])
                    elif tail:
                        value_token = tail[0]
                if value_token is not None:
                    values[canonical] = ParameterValue(*_with_name(resolve(value_token, env, f'{identifier}.{canonical}'), canonical))
                    if values[canonical].valid and kind != 'unknown':
                        sizables[(identifier, canonical)] = Sizable(identifier, canonical, canonical, value_token, current.name)
                for key, token in named.items():
                    if key == {'R': 'r', 'C': 'c', 'L': 'l', 'V': 'dc', 'I': 'dc'}[letter]:
                        continue
                    values[key] = ParameterValue(*_with_name(resolve(_value_token(token), env, f'{identifier}.{key}', numeric=False), key))
            else:
                for key, token in named.items():
                    values[key] = ParameterValue(*_with_name(resolve(_value_token(token), env, f'{identifier}.{key}', numeric=False), key))
            graph.parameters[identifier] = values
            for ordinal, (terminal, role, token) in enumerate(zip(terminals, roles, node_tokens)):
                graph.connections.append(Connection(identifier, net(token.text, path, port_map), terminal, ordinal, role))

    expand(root, _Env(root.params), '', {}, ())
    unknown = _finish_circuit_graph(graph, nets, diagnostics, subckt_uses, sizables, unknown_models)
    return Parsed(graph, measurements, analyses, sizables, lines, title, dict(subckt_uses), includes, has_control, has_end,
                  unknown, model_types)


def _collect_deck_statements(stmts, source):
    """Collect circuit scopes, directives and element statements while preserving their source order."""
    root = _Scope(None)
    scopes, scope = {}, root
    globals_ = set(GROUND)
    analyses, measurements, includes = [], [], []
    has_end = False
    diagnostics = []
    for tokens in stmts:
        head = tokens[0]
        word = head.text.lower()
        if word.startswith('.'):
            if word == '.end':
                has_end = True
            elif word == '.subckt':
                scope = _open_subcircuit(scope, root, tokens, head, scopes)
            elif word == '.ends':
                if scope is root:
                    raise NetlistError(f'line {head.line}: .ends without a .subckt')
                scope = root
            elif word == '.param':
                _record_scope_parameters(tokens, scope)
            elif word == '.global':
                globals_.update(t.text for t in tokens[1:])
            elif word in ('.include', '.inc', '.lib'):
                if len(tokens) > 1:
                    includes.append((word.lstrip('.'), _unquote(tokens[1].text), head.line))
            elif word in ('.meas', '.measure'):
                found = _measure([t.text for t in tokens], head.line, ' '.join(t.text for t in tokens))
                if found:
                    measurements.append(found)
            elif word in ('.op', '.dc', '.ac', '.tran', '.noise', '.pz', '.tf', '.sens', '.disto', '.sp', '.pss'):
                analyses.append(dict(text=' '.join(t.text for t in tokens), source=str(SourceSpan(source, head.line))))
            continue
        if scope is None:
            continue
        scope.body.append(tokens)
    if scope is not root:
        raise NetlistError(f'subcircuit {scope.name} is not closed with .ends')
    return root, scopes, globals_, analyses, measurements, includes, has_end, diagnostics


def _open_subcircuit(scope, root, tokens, head, scopes):
    """Validate a subcircuit declaration and register its port and parameter scope."""
    if scope is not root:
        raise NetlistError(f'line {head.line}: a .subckt inside a .subckt is not supported')
    if len(tokens) < 2:
        raise NetlistError(f'line {head.line}: .subckt without a name')
    name = tokens[1].text.lower()
    ports, params = [], {}
    in_params = False
    for token in tokens[2:]:
        if token.text.lower() == 'params:':
            in_params = True
            continue
        key, equals, value = token.text.partition('=')
        if equals:
            params[key.lower()] = value
        elif not in_params:
            ports.append(token.text)
    if name in scopes:
        raise NetlistError(f'line {head.line}: subcircuit {name} is defined twice')
    scope = scopes[name] = _Scope(name, tuple(ports), params)
    return scope


def _record_scope_parameters(tokens, scope):
    """Record named parameter definitions in the current circuit scope."""
    for token in tokens[1:]:
        key, equals, value = token.text.partition('=')
        if equals and key:
            scope.params[key.lower()] = value


def _read_control_outputs(control_lines, source, measurements, analyses):
    """Collect control-block analyses and measurements in their original order."""
    control_units, last_analysis = {}, 'other'
    for line, statement in control_lines:
        words = statement.split()
        if not words:
            continue
        command = words[0].lower()
        if command in ('meas', 'measure'):
            found = _measure(words, line, statement)
            if found:
                measurements.append(found)
        elif command in ('op', 'dc', 'ac', 'tran', 'noise', 'pz', 'tf', 'sens', 'disto', 'sp'):
            last_analysis = MEASURE_ANALYSES.get(command, 'other') if command != 'op' else 'dc'
            analyses.append(dict(text=statement, source=str(SourceSpan(source, line))))
        elif command == 'let':
            key, equals, expression = statement[3:].partition('=')
            if equals and re.match(r'^[a-z_]\w*$', key.strip().lower()):
                control_units[key.strip().lower()] = expression_unit(expression)
        elif command in ('print', 'echo') and command == 'print':
            for word in words[1:]:
                name = word.lower()
                if re.match(r'^[a-z_]\w*$', name) and name not in ('all',) and name not in {m.name for m in measurements}:
                    measurements.append(Measurement(name, last_analysis, unit_from_name(name) or control_units.get(name, '1'), line, statement))


def _graph_resolvers(globals_, nets, source, diagnostics, kinds_given, model_types):
    """Create the name, parameter and device-kind resolvers for one parsed circuit."""
    # ngspice reads a node's name without regard to case (IN and in are one wire): one net per name, under the spelling
    # the deck gives first - a deck of one spelling reads as it always did. Until record 7.322 each spelling was a net.
    spelled = {}
    global_names = {name.lower() for name in globals_}

    def net(name, path, port_map):
        key = port_map.get(name.lower())
        if key is None:
            key = name if name.lower() in global_names or not path else f'{path}/{name}'
            key = spelled.setdefault(key.lower(), key)
        if key not in nets:
            nets[key] = Net(key, ('ground',) if key.lower() in GROUND else ('normal',), 'default')
        return key

    def resolve(token, env, label, *, numeric=True):
        raw = token.text
        try:
            return ParameterValue(raw, evaluate(raw, env.lookup), SourceSpan(source, token.line, token.column + 1))
        except Unresolved as exc:
            if numeric:
                diagnostics.append(Diagnostic('unresolved_expression', f'{label}: {raw} ({exc})',
                                              SourceSpan(source, token.line, token.column + 1), 'warning'))
            return ParameterValue(raw, None, SourceSpan(source, token.line, token.column + 1), str(exc))

    def kind_of(letter, model, positional):
        """(kind, roles, node count) of an element from its letter and model."""
        if letter == 'M':
            declared = kinds_given.get(model) or MODEL_KINDS.get(model_types.get(model, ''), None)
            if declared is None:
                declared = 'nmos' if model_types.get(model) == 'vdmos' and 'pchan' not in positional else \
                    'pmos' if model_types.get(model) == 'vdmos' else 'unknown'
            return declared, ROLES.get(declared, ('unknown',) * 4), 4
        if letter in ELEMENT_KINDS:
            kind = kinds_given.get(model, ELEMENT_KINDS[letter]) if model else ELEMENT_KINDS[letter]
            return kind, ROLES.get(kind, ('unknown', 'unknown')), 2
        if letter == 'Q':
            return kinds_given.get(model, 'unknown'), None, None
        return kinds_given.get(model, 'unknown'), None, NODE_COUNT.get(letter)
    return net, resolve, kind_of


def _finish_circuit_graph(graph, nets, diagnostics, subckt_uses, sizables, unknown_models):
    """Finalize and validate the circuit graph, excluding sizes shared by repeated subcircuits."""
    graph.nets = list(nets.values())
    graph.diagnostics = diagnostics
    graph.metadata['ports'] = ()
    graph.metadata['subckt_uses'] = dict(subckt_uses)
    # a value inside a subcircuit used more than once cannot be written for one instance alone
    shared = {name for name, uses in subckt_uses.items() if uses != 1}
    for key in [k for k, s in sizables.items() if s.subckt in shared]:
        sizables.pop(key)
    graph.validate(require_complete=False)
    unknown = list(dict.fromkeys(unknown_models))
    return unknown


def _with_name(value, source_name):
    return value.raw, value.value, value.source, value.reason, source_name


def parse_file(path, **kwargs) -> Parsed:
    """Parse a deck file using its directory as the default include root."""
    path = Path(path)
    return parse_text(path.read_text(errors='replace'), source=str(path), circuit_id=path.stem,
                      include_root=kwargs.pop('include_root', path.parent), **kwargs)
