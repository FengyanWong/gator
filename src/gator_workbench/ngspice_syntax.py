"""Source-located SPICE values, tokens and statements, shared by graph reading and deck writing.

The ngspice grammar is deliberately separate from Spectre and workbench size formulas.
Definitions are re-exported by ngspice_netlist for existing callers.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re

from analog_optimizer.graph.circuit_graph import CircuitGraph

SCALES = {'t': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15,
    'a': 1e-18,
          'mil': 25.4e-6}


NUMBER = re.compile(r'^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[tgkmunpfa])?[a-z]*$', re.IGNORECASE)


NAME = re.compile(r'^[A-Za-z_][\w.\-:$#@!]*$')


class NetlistError(ValueError):
    """The deck cannot be read, with the line that stopped it."""


@dataclass(frozen=True)
class Token:
    # A source token with its physical line and character offset in the deck.
    text: str
    line: int          # 1-based physical line of the deck
    column: int        # 0-based offset in that line


@dataclass(frozen=True)
class Measurement:
    # A parsed measurement with its analysis, suggested unit and original source text.
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
    # A parsed deck retaining its circuit graph, source lines and metadata needed for rewriting.
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
        """Hash the retained physical deck lines joined by newline characters."""
        return hashlib.sha256('\n'.join(self.lines).encode()).hexdigest()

    @property
    def by_source(self) -> dict:
        """(device_id, the name the deck spells the value by) -> Sizable: the keys of the optimizer's assignments."""
        return {(s.device_id, s.source_name): s for s in self.sizables.values()}

    @property
    def result_names(self) -> list:
        """Return unique measurement names in their original order."""
        return list(dict.fromkeys(m.name for m in self.measurements))

    @property
    def units(self) -> dict:
        return {m.name: m.unit for m in self.measurements}


def number(text: str) -> float | None:
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


_EXPRESSION_NUMBER = re.compile(r'(?<![\w.])((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|mil|[tgkmunpfa])?(?![\w.])',
    re.IGNORECASE)


class Unresolved(ValueError):
    """An expression could not be resolved within the supported SPICE value grammar."""
    pass


def evaluate(text: str, lookup) -> float:
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

    def literal(match: re.Match[str]) -> str:
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
        if isinstance(node, ast.Call) and isinstance(node.func,
            ast.Name) and node.func.id.lower() in _FUNCTIONS and not node.keywords:
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


def strip_comment(line: str) -> str:
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


def _scan_spice_token(line: str, i: int, n: int) -> tuple[int, int]:
    """Find the end and starting offset of a token while respecting quotes and brackets."""
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
    return i, start


def tokenize(line: str, line_number: int) -> list[Token]:
    """Tokens of one physical line: split on blanks and commas outside quotes and brackets, then `a = b` joined to `a=b`
    (SPICE allows the spaces). Each token remembers its place, so a value can be replaced in the deck later."""
    raw, i, n = [], 0, len(line)
    while i < n:
        if line[i] in ' \t,':
            i += 1
            continue
        i, start = _scan_spice_token(line, i, n)
        raw.append(Token(line[start:i], line_number, start))
    tokens = []
    for token in raw:
        if tokens and (token.text.startswith('=') or tokens[-1].text.endswith('=')) and not (tokens[
            -1].text == '=' and len(tokens) == 1):
            previous = tokens.pop()
            tokens.append(Token(previous.text + token.text, previous.line, previous.column))
        else:
            tokens.append(token)
    return tokens


def statements(lines) -> tuple:
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


def _split(tokens, *, first: int=1) -> tuple[list, dict]:
    """(positional tokens, {name: token of the whole `name=value`}) after the element name."""
    positional, named = [], {}
    for token in tokens[first:]:
        head, equals, _ = token.text.partition('=')
        if equals and head and NAME.match(head) and not token.text.startswith('{') and not token.text.startswith("'"):
            named[head.lower()] = token
        else:
            positional.append(token)
    return positional, named


def _value_token(token: Token) -> Token:
    """The value part of a `name=value` token as a token of its own (for the writeback), or the token itself."""
    head, equals, tail = token.text.partition('=')
    if equals and NAME.match(head or ' '):
        return Token(tail, token.line, token.column + len(head) + 1)
    return token
