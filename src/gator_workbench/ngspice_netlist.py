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
import math
from pathlib import Path
import re

from analog_optimizer.graph.circuit_graph import (CircuitGraph, Connection, Device, Diagnostic, Net, ParameterValue,
                                                    SourceSpan)

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
SCALES = {'t': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15, 'a': 1e-18,
          'mil': 25.4e-6}
NUMBER = re.compile(r'^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[tgkmunpfa])?[a-z]*$', re.IGNORECASE)
NAME = re.compile(r'^[A-Za-z_][\w.\-:$#@!]*$')
MEASURE_ANALYSES = {'ac': 'ac', 'dc': 'dc', 'tran': 'tran', 'sp': 'other', 'noise': 'noise'}
MODEL_SCAN_BYTES = 48 * 1024 * 1024        # how much of the included model files is read for their .model types, at most
MAX_INCLUDE_DEPTH = 8


class NetlistError(ValueError):
    """The deck cannot be read, with the line that stopped it."""


@dataclass(frozen=True)
class Token:
    text: str
    line: int          # 1-based physical line of the deck
    column: int        # 0-based offset in that line


@dataclass(frozen=True)
class Measurement:
    name: str          # as ngspice prints it: lowercase
    analysis: str      # the workbench's analysis label of the Probes row
    unit: str          # a guess from the measured expression (V, A, dB, s, Hz, '1'); the row is editable
    line: int
    text: str


@dataclass(frozen=True)
class Sizable:
    """One writable value: which token of the deck holds it."""
    device_id: str
    parameter: str     # canonical: w, l, m, nf, r, c, ind, dc
    source_name: str   # how the deck spells it (W, L, r, the positional value...)
    token: Token
    subckt: str | None # the definition the device sits in (None = top level)


@dataclass
class Parsed:
    graph: CircuitGraph
    measurements: list
    analyses: list
    sizables: dict                  # (device_id, parameter) -> Sizable
    lines: list                     # the deck's physical lines, as given
    title: str
    subckt_uses: dict               # subckt name -> number of instances in the expanded circuit
    includes: list                  # (kind, path as written, line)
    has_control: bool
    has_end: bool
    unknown_models: list            # model / subckt names the deck uses without saying their kind
    model_types: dict               # model name -> type found in the deck or its included files

    @property
    def sha256(self) -> str:
        return hashlib.sha256('\n'.join(self.lines).encode()).hexdigest()

    @property
    def by_source(self) -> dict:
        """(device_id, the name the deck spells the value by) -> Sizable: the keys of the optimizer's assignments."""
        return {(s.device_id, s.source_name): s for s in self.sizables.values()}

    @property
    def result_names(self) -> list:
        return list(dict.fromkeys(m.name for m in self.measurements))

    @property
    def units(self) -> dict:
        return {m.name: m.unit for m in self.measurements}


# ------------------------------------------------------------------------------------------------ numbers and expressions
def number(text):
    """A SPICE number, or None. `10uF` = 10e-6 (letters after the scale are ignored), `1Meg` = 1e6, `1M` = 1e-3."""
    match = NUMBER.match(text.strip())
    if not match:
        return None
    value = float(match.group(1)) * SCALES.get((match.group(2) or '').lower(), 1.0)
    return value if math.isfinite(value) else None


_FUNCTIONS = {'sqrt': math.sqrt, 'exp': math.exp, 'log': math.log, 'ln': math.log, 'log10': math.log10, 'abs': abs,
              'pow': math.pow, 'max': max, 'min': min, 'int': lambda x: float(int(x)), 'floor': math.floor,
              'ceil': math.ceil, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'atan': math.atan,
              'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh, 'nint': lambda x: float(round(x))}
_EXPRESSION_NUMBER = re.compile(r'(?<![\w.])((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[tgkmunpfa])?(?![\w.])', re.IGNORECASE)


class Unresolved(ValueError):
    pass


def evaluate(text, lookup):
    """The value of a SPICE expression (`{2*wn}`, `'wn/2'`, `wn`) with `lookup(name)` for parameters: numbers with SPICE
    scales, + - * / ** and unary signs, brackets and the arithmetic functions ngspice has. A whitelist over the syntax
    tree, never eval(); anything else is Unresolved."""
    import ast
    import operator
    source = text.strip()
    if source[:1] in ('{', "'", '"'):
        close = {'{': '}', "'": "'", '"': '"'}[source[0]]
        if not source.endswith(close):
            raise Unresolved('unclosed expression')
        source = source[1:-1]
    if not source or len(source) > 2048:
        raise Unresolved('empty or too long')
    plain = number(source)
    if plain is not None:
        return plain

    def literal(match):
        value = float(match.group(1)) * SCALES.get((match.group(2) or '').lower(), 1.0)
        return repr(value)
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.Pow: operator.pow, ast.Mod: operator.mod}

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name):
            return float(lookup(node.id))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise Unresolved('exponent too large')
            return binary[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in _FUNCTIONS and not node.keywords:
            return float(_FUNCTIONS[node.func.id.lower()](*[visit(a) for a in node.args]))
        raise Unresolved(f'unsupported {type(node).__name__}')
    try:
        tree = ast.parse(_EXPRESSION_NUMBER.sub(literal, source).replace('^', '**'), mode='eval')
        if sum(1 for _ in ast.walk(tree)) > 200:
            raise Unresolved('expression too complex')
        value = float(visit(tree.body))
    except Unresolved:
        raise
    except (SyntaxError, ValueError, TypeError, ArithmeticError, RecursionError, KeyError) as exc:
        raise Unresolved(str(exc)) from exc
    if not math.isfinite(value):
        raise Unresolved('not a finite number')
    return value


# ------------------------------------------------------------------------------------------------ tokens and statements
def strip_comment(line):
    """The line without a `$ ...` or `; ...` inline comment (SPICE), keeping quotes and braces whole."""
    depth, quote = 0, None
    for i, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "'\"":
            quote = char
        elif char in '{(':
            depth += 1
        elif char in '})':
            depth = max(0, depth - 1)
        elif depth == 0 and (char == '$' or char == ';') and (i == 0 or line[i - 1] in ' \t'):
            return line[:i]
    return line


def tokenize(line, line_number):
    """Tokens of one physical line: split on blanks and commas outside quotes and brackets, then `a = b` joined to `a=b`
    (SPICE allows the spaces). Each token remembers its place, so a value can be replaced in the deck later."""
    raw, i, n = [], 0, len(line)
    while i < n:
        if line[i] in ' \t,':
            i += 1
            continue
        start, depth, quote = i, 0, None
        while i < n:
            char = line[i]
            if quote:
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif char in '{(':
                depth += 1
            elif char in '})':
                depth -= 1
            elif char in ' \t,' and depth <= 0:
                break
            i += 1
        raw.append(Token(line[start:i], line_number, start))
    tokens = []
    for token in raw:
        if tokens and (token.text.startswith('=') or tokens[-1].text.endswith('=')) and not (tokens[-1].text == '=' and len(tokens) == 1):
            previous = tokens.pop()
            tokens.append(Token(previous.text + token.text, previous.line, previous.column))
        else:
            tokens.append(token)
    return tokens


def statements(lines):
    """Logical statements of the deck: each a list of tokens across `+` continuation lines. The title line is not a
    statement. Returns (title, statements, has_control, control_lines)."""
    title = lines[0].rstrip() if lines else ''
    result, control, in_control, control_lines = [], False, False, []
    current = None
    for index, line in enumerate(lines[1:], start=2):
        text = strip_comment(line.rstrip('\r'))
        stripped = text.strip()
        if not stripped or stripped.startswith('*'):
            continue
        if in_control:
            if stripped.lower().startswith('.endc'):
                in_control = False
            else:
                control_lines.append((index, stripped))
            continue
        if stripped.lower().startswith('.control'):
            in_control, control = True, True
            continue
        if stripped.startswith('+'):
            if current is None:
                raise NetlistError(f'line {index}: a continuation line (+) with nothing before it')
            offset = text.index('+')
            current.extend(tokenize(' ' * (offset + 1) + text[offset + 1:], index))
            continue
        if current is not None:
            result.append(current)
        current = tokenize(text, index)
    if current is not None:
        result.append(current)
    return title, result, control, control_lines


def _split(tokens, *, first=1):
    """(positional tokens, {name: token of the whole `name=value`}) after the element name."""
    positional, named = [], {}
    for token in tokens[first:]:
        head, equals, _ = token.text.partition('=')
        if equals and head and NAME.match(head) and not token.text.startswith('{') and not token.text.startswith("'"):
            named[head.lower()] = token
        else:
            positional.append(token)
    return positional, named


def _value_token(token):
    """The value part of a `name=value` token as a token of its own (for the writeback), or the token itself."""
    head, equals, tail = token.text.partition('=')
    if equals and NAME.match(head or ' '):
        return Token(tail, token.line, token.column + len(head) + 1)
    return token


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


def _guess_unit(analysis, words):
    """The unit a .meas result most likely has, from its own words: the measure type decides. FIND / MAX / MIN / AVG /
    RMS / PP / INTEG / DERIV of v(...) -> V, i(...) -> A, vdb -> dB, vp / ph -> rad (ngspice's default); WHEN, TRIG /
    TARG (a point on the x axis) -> s in tran, Hz in ac, V in dc; PARAM -> 1. The Probes row stays editable."""
    words = [w.lower() for w in words]
    kind = words[0] if words else ''
    expression = ' '.join(words[1:2])
    if kind == 'param':
        return '1'
    if kind in ('when', 'trig', 'targ'):
        return {'tran': 's', 'ac': 'Hz', 'dc': 'V'}.get(analysis, '1')
    if kind in ('find', 'max', 'min', 'avg', 'rms', 'pp', 'integ', 'deriv', 'max_at', 'min_at'):
        return expression_unit(expression, {'tran': 's', 'ac': 'Hz', 'dc': 'V'}.get(analysis, '1') if kind in ('max_at', 'min_at') else None)
    return '1'


NAME_UNITS = {'_deg': 'deg', '_rad': 'rad', '_hz': 'Hz', '_db': 'dB', '_w': 'W', '_v': 'V', '_a': 'A', '_s': 's', '_f': 'F',
              '_ohm': 'ohm', '_h': 'H', '_j': 'J', '_pct': '%'}


def unit_from_name(name):
    """A unit the result's own name states with its suffix (gain_db, ugf_hz, phase_margin_deg, power_w), or None."""
    lowered = (name or '').lower()
    for suffix, unit in NAME_UNITS.items():
        if lowered.endswith(suffix):
            return unit
    return None


def expression_unit(expression, default=None):
    """The unit of an ngspice expression such as v(out), vdb(out), i(vdd), -1.8*i(vdd): a guess from its outermost
    signal function; `default` (else '1') when there is none."""
    text = (expression or '').lower()
    if re.search(r'\bvdb\(|\bdb\(', text):
        return 'dB'
    if re.search(r'\bvp\(|\bph\(|\bphase\(', text):
        return 'rad'
    if re.search(r'\bi\(|\bi[a-z]*\(', text) and not re.search(r'\bv\(|\bv[a-z]*\(', text):
        return 'A'
    if re.search(r'\bv\(|\bv[a-z]*\(', text):
        return 'V'
    return default or '1'


def _measure(words, line, text):
    """A `.meas[ure] <analysis> <name> ...` (deck) or `meas <analysis> <name> ...` (control) statement, or None."""
    if len(words) < 3:
        return None
    analysis = words[1].lower()
    if analysis not in MEASURE_ANALYSES:
        return None
    name = words[2].lower()
    if not re.match(r'^[a-z_]\w*$', name):
        return None
    return Measurement(name, MEASURE_ANALYSES[analysis], unit_from_name(name) or _guess_unit(analysis, [w.lower() for w in words[3:]]), line, text)


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
            elif word == '.ends':
                if scope is root:
                    raise NetlistError(f'line {head.line}: .ends without a .subckt')
                scope = root
            elif word == '.param':
                for token in tokens[1:]:
                    key, equals, value = token.text.partition('=')
                    if equals and key:
                        scope.params[key.lower()] = value
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

    def net(name, path, port_map):
        key = port_map.get(name.lower())
        if key is None:
            key = name if name.lower() in {g.lower() for g in globals_} or not path else f'{path}/{name}'
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
    return Parsed(graph, measurements, analyses, sizables, lines, title, dict(subckt_uses), includes, has_control, has_end,
                  unknown, model_types)


def _with_name(value, source_name):
    return value.raw, value.value, value.source, value.reason, source_name


def parse_file(path, **kwargs) -> Parsed:
    path = Path(path)
    return parse_text(path.read_text(errors='replace'), source=str(path), circuit_id=path.stem,
                      include_root=kwargs.pop('include_root', path.parent), **kwargs)


# ------------------------------------------------------------------------------------------------ writing back
def format_value(value):
    """A number ngspice reads back as the same value: 12 significant digits, plain notation."""
    return f'{float(value):.12g}'


def rewrite(parsed: Parsed, assignments, *, include_root=None, absolute_includes=False):
    """The deck with every (device_id, parameter) of `assignments` set to its value: each value's own token is
    replaced, from the last token of a line backwards so the columns stay valid. Values inside a subcircuit are written
    into its definition, which the parser guarantees is used once. With `absolute_includes`, relative .include /
    .lib paths are resolved from `include_root` (ngspice resolves them from ITS working directory, not from the
    deck's folder). Returns (text, {device_id.parameter: new token text})."""
    lines = list(parsed.lines)
    edits = {}
    by_source = parsed.by_source
    for (device_id, parameter), value in assignments.items():
        sizable = parsed.sizables.get((device_id, parameter)) or by_source.get((device_id, parameter))
        if sizable is None:
            raise NetlistError(f'{device_id}.{parameter} cannot be written: not a sizable value of this netlist')
        edits.setdefault(sizable.token.line, []).append((sizable.token, format_value(value)))
    written = {}
    for line_number, changes in edits.items():
        line = lines[line_number - 1]
        for token, text in sorted(changes, key=lambda c: -c[0].column):
            if line[token.column:token.column + len(token.text)] != token.text:
                raise NetlistError(f'line {line_number}: the deck changed under the parser ({token.text!r} not found)')
            line = line[:token.column] + text + line[token.column + len(token.text):]
            written[f'{token.line}:{token.column}'] = text
        lines[line_number - 1] = line
    if absolute_includes and include_root is not None:
        for kind, target, line_number in parsed.includes:
            path = Path(target)
            if path.is_absolute():
                continue
            line = lines[line_number - 1]
            absolute = str((Path(include_root) / path).resolve())
            quoted = re.escape(target)
            lines[line_number - 1] = re.sub(r'(?i)^(\s*\.(?:include|inc|lib)\s+)(["\']?)' + quoted + r'\2',
                                            lambda m: f'{m.group(1)}"{absolute}"', line, count=1)
    return '\n'.join(lines), written


def deck_text(parsed: Parsed, assignments, **kwargs):
    """`rewrite` plus the `.end` line a deck needs (some hand-written decks leave it out; ngspice wants it)."""
    text, written = rewrite(parsed, assignments, **kwargs)
    if not parsed.has_end:
        text = text.rstrip('\n') + '\n.end\n'
    return text, written


# ------------------------------------------------------------------------------------------------ what a run reads
RESULT_LINE = re.compile(r'^\s*([A-Za-z_]\w*)\s*=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|[-+]?(?:nan|inf))\b', re.IGNORECASE)
FAILURE_PATTERNS = (
    ('nonconverged', re.compile(r'(?i)(timestep too small|no convergence|singular matrix|gmin stepping failed|'
                                r'source stepping failed|convergence problem|failed to converge|too many iterations)')),
    ('measurement_error', re.compile(r'(?i)(\bmeas(?:ure(?:ment)?)?\b.*\bfailed|out of interval|no such vector|vector .* not found|'
                                     r'result is not a number)')),
    ('deck_error', re.compile(r'(?i)(error on line|fatal error|unknown subckt|could not find include|'
                              r'unable to find definition of model|model .* not found|no circuit loaded|'
                              r'syntax error|cannot compute substitute|error in netlist)')),
)


def read_results(stdout, wanted):
    """{name: value} for every `<name> = <number>` line of ngspice's batch output whose name is one of `wanted` (ngspice
    prints .meas names in lowercase). nan / inf stay out: a failed measurement is missing, never a number."""
    names = {name.lower(): name for name in wanted}
    found = {}
    for line in (stdout or '').splitlines():
        match = RESULT_LINE.match(line)
        if not match:
            continue
        key = match.group(1).lower()
        if key not in names or key in found:
            continue
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if math.isfinite(value):
            found[names[key]] = value
    return found


def classify_failure(stdout, stderr, returncode):
    """(status word, one line of evidence) when the output says the deck or the solution failed, else (None, '')."""
    text = '\n'.join(filter(None, (stdout, stderr)))
    for status, pattern in FAILURE_PATTERNS:
        match = pattern.search(text)
        if match:
            start = text.rfind('\n', 0, match.start()) + 1
            end = text.find('\n', match.end())
            return status, text[start:end if end >= 0 else len(text)].strip()[:300]
    if returncode not in (0, None):
        tail = [line.strip() for line in (stderr or stdout or '').splitlines() if line.strip()]
        return 'deck_error', (tail[-1] if tail else f'ngspice ended with exit code {returncode}')[:300]
    return None, ''
