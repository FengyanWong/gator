"""What each spec measures, as numbers the network can read without the spec's name (record 7.298, spec input "set").

The optimizer's spec set input (``analog_optimizer.models.inputs.SpecSetSchema``) turns every active spec into one item:
its own state (limits, distance to them in its scale, validity, unit) plus a description that this module supplies. The
description is computed from the task alone, never typed and never guessed from a name:

- the probes the spec's equation uses (``spec_equations.parse``) and their analyses;
- each probe's OCEAN expression, parsed into a small tree: which signals it reads (node voltages, a source's current, the
  stb loop gain, an xf transfer, noise), how it reduces them (a value at a point, a crossing, a phase margin, extremes,
  an integral, a waveform measure, a magnitude, decibels, a root), whether it is a ratio, a difference of two nodes,
  negated, scaled or offset by a constant, and WHERE it is read: the point (``value(x f)``) or the window (``clip``,
  ``integ``) in frequency or time - its position (log10 of the point, or of the window's centre) and its span (log10 of
  the window's stop over its start; 0 for a point). That tells apart a PSRR read up to 10 kHz from one above 1 MHz, a
  noise band from another, and the members of a series (the first probe of a spec's equation sets its place);
- the testbench netlist the task was saved with (``structure.scs``): which source is the supply (the one ``design.json``
  declares, else the largest ground-referenced DC voltage source - the rule Save task uses), and which sources carry
  the AC stimulus (``mag=``). An xf result or a current read at the supply, or an ac probe while the stimulus sits on
  the supply, is marked "from the supply"; another source's, "from another source".

A probe measured by a built-in circuit analyzer (``result_source`` backend_profile) has no expression: it is described
by its analysis and that fact alone. Anything this module cannot read leaves its columns at 0 - an item is never
refused for an expression it does not understand.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

from . import spec_equations, units
from .profile_store import FILES, profile_entry

DESCRIPTOR_VERSION = 'gator-spec-descriptor-v2'           # v2: position + span replace the frequency point
ANALYSES = ('dc', 'ac', 'tran', 'noise', 'stb', 'pss', 'pnoise', 'other')
SIGNALS = ('voltage', 'current', 'loop_gain', 'transfer_xf', 'noise', 'other_data', 'no_expression')
SOURCES = ('from_supply', 'from_other_source', 'ac_stimulus_on_supply', 'node_difference')
FORMS = ('ratio', 'negated', 'scaled', 'offset', 'combined_probes')
REDUCTIONS = ('value_at', 'cross', 'margin', 'extreme', 'window', 'integral', 'waveform', 'magnitude', 'decibel', 'root')
DESCRIPTOR_COLUMNS = (tuple(f'analysis_{a}' for a in ANALYSES) + tuple(f'signal_{s}' for s in SIGNALS) + SOURCES +
                      tuple(f'form_{f}' for f in FORMS) + tuple(f'reduction_{r}' for r in REDUCTIONS) +
                      ('position', 'span', 'has_position', 'probe_count'))
# The unit list of the item's one-hot and the reference its magnitudes are divided by (signed log1p): every canonical
# unit of units.py, in a fixed order that is part of every set model's contract. A unit outside it is "other".
UNIT_REFERENCES = (('V', 1.0), ('A', 1e-6), ('W', 1e-3), ('Hz', 1e6), ('s', 1e-6), ('dB', 20.0), ('deg', 90.0),
                   ('V/V', 1.0), ('V/A', 1.0), ('%', 1.0), ('1', 1.0), ('count', 1.0), ('ohm', 1e3), ('F', 1e-12),
                   ('H', 1e-9), ('m', 1e-6), ('J', 1e-12), ('rad', math.pi / 2), ('dBc/Hz', 100.0),
                   ('V/sqrt(Hz)', 1e-8), ('A/sqrt(Hz)', 1e-11), ('V^2/Hz', 1e-16), ('Vrms', 1e-3), ('V/s', 1e6),
                   ('Hz/V', 1e6), ('degC', 100.0), ('fixture', 1.0))
FREQUENCY_ANALYSES = {'ac', 'noise', 'stb', 'pnoise'}
PLACED_ANALYSES = FREQUENCY_ANALYSES | {'tran'}           # where a point or window means a frequency or a time
_WINDOWS = {'clip', 'integ', 'iinteg'}                     # f(x from to)

_VOLTAGE = {'VF', 'VS', 'VDC', 'VT', 'VN', 'VM', 'VP', 'VR', 'VI', 'v'}
_CURRENT = {'IF', 'IS', 'IDC', 'IT', 'IN', 'IM', 'IP', 'IR', 'II', 'i'}
_REDUCTION_OF = dict(value='value_at', cross='cross', phaseMargin='margin', gainMargin='margin', ymax='extreme',
                     ymin='extreme', peakToPeak='extreme', clip='window', integ='integral', average='integral',
                     rms='integral', iinteg='integral', frequency='waveform', dutyCycle='waveform', riseTime='waveform',
                     fallTime='waveform', slewRate='waveform', delay='waveform', period='waveform', settlingTime='waveform',
                     overshoot='waveform', bandwidth='cross', unityGainFreq='cross', mag='magnitude', abs='magnitude',
                     dB20='decibel', dB10='decibel', db='decibel', db10='decibel', sqrt='root', pow='root')
_SI = dict(T=1e12, G=1e9, M=1e6, K=1e3, k=1e3, m=1e-3, u=1e-6, n=1e-9, p=1e-12, f=1e-15, a=1e-18)


# ------------------------------------------------------------------------------------------ the expression tree
@dataclass
class Node:
    kind: str                       # number, string, keyword, name, call, neg, add, sub, mul, div
    value: object = None            # number value, string text, name or function name
    children: list = field(default_factory=list)


_TOKEN = re.compile(r'\s*(?:(?P<number>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?[TGMKkmunpfa]?(?![A-Za-z_]))|'
                    r'(?P<string>"(?:[^"\\]|\\.)*")|(?P<keyword>\?[A-Za-z_][A-Za-z0-9_]*)|'
                    r'(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>[-+*/()]))')


def _tokens(text):
    position, found = 0, []
    while position < len(text):
        if text[position:].strip() == '':
            break
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise ValueError(f'cannot read {text[position:position + 12]!r}')
        kind = match.lastgroup
        found.append((kind, match.group(kind)))
        position = match.end()
    return found


def _number(text):
    if text[-1] in _SI:
        return float(text[:-1]) * _SI[text[-1]]
    return float(text)


class _Parser:
    """OCEAN's infix subset: arithmetic, unary minus, calls with whitespace-separated arguments and ?keywords."""

    def __init__(self, text):
        self.tokens, self.at = _tokens(text), 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else (None, None)

    def take(self, kind=None, value=None):
        token = self.peek()
        if token[0] is None or (kind and token[0] != kind) or (value and token[1] != value):
            raise ValueError(f'expected {value or kind}, found {token[1]!r}')
        self.at += 1
        return token

    def parse(self):
        tree = self.expression()
        if self.at != len(self.tokens):
            raise ValueError(f'unexpected {self.peek()[1]!r}')
        return tree

    def expression(self):
        left = self.term()
        while self.peek() in (('op', '+'), ('op', '-')):
            op = self.take()[1]
            left = Node('add' if op == '+' else 'sub', children=[left, self.term()])
        return left

    def term(self):
        left = self.unary()
        while self.peek() in (('op', '*'), ('op', '/')):
            op = self.take()[1]
            left = Node('mul' if op == '*' else 'div', children=[left, self.unary()])
        return left

    def unary(self):
        if self.peek() == ('op', '-'):
            self.take()
            return Node('neg', children=[self.unary()])
        if self.peek() == ('op', '+'):
            self.take()
            return self.unary()
        return self.primary()

    def primary(self):
        kind, value = self.peek()
        if kind == 'number':
            self.take()
            return Node('number', _number(value))
        if kind == 'string':
            self.take()
            return Node('string', value[1:-1])
        if kind == 'op' and value == '(':
            self.take()
            inner = self.expression()
            self.take('op', ')')
            return inner
        if kind == 'name':
            self.take()
            if self.peek() == ('op', '('):
                self.take()
                arguments = []
                while self.peek() != ('op', ')'):
                    if self.peek()[0] is None:
                        raise ValueError('unclosed call')
                    if self.peek()[0] == 'keyword':
                        keyword = self.take()[1]
                        arguments.append(Node('keyword', keyword[1:], [self.expression()]))
                    else:
                        arguments.append(self.expression())
                self.take('op', ')')
                return Node('call', value, arguments)
            return Node('name', value)
        raise ValueError(f'unexpected {value!r}')


def parse_expression(text):
    """The tree of an OCEAN expression, or None when it cannot be read (the description then leaves it out)."""
    try:
        return _Parser(text).parse() if isinstance(text, str) and text.strip() else None
    except (ValueError, IndexError):
        return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _is_constant(node):
    return all(n.kind in ('number', 'neg', 'add', 'sub', 'mul', 'div') for n in _walk(node))


def _signal_calls(node):
    return [n for n in _walk(node) if n.kind == 'call' and (n.value in _VOLTAGE or n.value in _CURRENT or n.value == 'getData')]


def _first_string(node):
    return next((c.value for c in node.children if c.kind == 'string'), None)


def _keyword(node, name):
    return next((c.children[0] for c in node.children if c.kind == 'keyword' and c.value == name and c.children), None)


# ------------------------------------------------------------------------------------------ the bench
@dataclass(frozen=True)
class Bench:
    """What the testbench netlist says about its sources (names as written in the netlist)."""
    supply: str | None = None
    ac_sources: frozenset = frozenset()


_SOURCE_LINE = re.compile(r'^(?P<name>[^\s(]+)\s*\((?P<nets>[^)]*)\)\s+(?P<kind>vsource|isource)\b(?P<rest>.*)$')
_ASSIGN = re.compile(r'(\w+)\s*=\s*("[^"]*"|\S+)')


def bench_of_netlist(text, declared_supply=None):
    """The sources of a Spectre testbench netlist (outside every subckt): the supply - `declared_supply` when the task
    names it, else the largest ground-referenced DC voltage source (Save task's rule) - and the AC stimulus sources."""
    lines, joined = [], ''
    for raw in (text or '').splitlines():
        line = raw.split('//')[0].rstrip()
        if line.endswith('\\'):
            joined += line[:-1] + ' '
            continue
        lines.append(joined + line)
        joined = ''
    depth, best, ac = 0, None, set()
    for line in lines:
        stripped = line.strip()
        first = stripped.split(' ', 1)[0] if stripped else ''
        if first in ('subckt', 'inline'):
            depth += 1
            continue
        if first == 'ends':
            depth = max(0, depth - 1)
            continue
        match = _SOURCE_LINE.match(stripped)
        if depth or match is None:
            continue
        values = dict(_ASSIGN.findall(match['rest']))
        mag = values.get('mag')
        if mag is not None and _numeric(mag) != 0:
            ac.add(match['name'])
        nets = match['nets'].split()
        dc = _numeric(values.get('dc'))
        if match['kind'] == 'vsource' and dc is not None and len(nets) == 2 and ('0' in nets or 'gnd!' in nets):
            if best is None or abs(dc) > best[0]:
                best = (abs(dc), match['name'])
    supply = declared_supply or (best[1] if best and best[0] > 0 else None)
    return Bench(supply, frozenset(ac))


def _numeric(text):
    if text is None:
        return None
    try:
        return _number(text.strip('"'))
    except (ValueError, IndexError):
        return None


def bench_of_task(config):
    """The bench of a saved Virtuoso task (its profile's structure.scs and design.json), or an empty one."""
    task_id = getattr(config.circuit, 'task_id', None) or ''
    if getattr(config.circuit, 'source', None) != 'registered_task' or not task_id.startswith('real:'):
        return Bench()
    entry = profile_entry(task_id[len('real:'):])
    if entry is None:
        return Bench()
    from pathlib import Path
    folder = Path(entry['directory'])
    try:
        design = json.loads((folder / FILES['design']).read_text())
    except (OSError, ValueError):
        design = {}
    try:
        netlist = (folder / FILES['structure']).read_text()
    except OSError:
        netlist = ''
    return bench_of_netlist(netlist, design.get('supply_source') if isinstance(design, dict) else None)


# ------------------------------------------------------------------------------------------ one probe
def probe_facts(analysis, expression, bench=Bench(), *, measured_by_analyzer=False):
    """The description columns of one probe, as a dict column -> number (only the ones it sets)."""
    found = {f'analysis_{analysis if analysis in ANALYSES else "other"}': 1.0}
    if measured_by_analyzer:
        found['signal_no_expression'] = 1.0
        return found
    tree = parse_expression(expression)
    if tree is None:
        found['signal_no_expression'] = 1.0
        return found
    for node in _walk(tree):
        if node.kind == 'call':
            if node.value in _VOLTAGE:
                found['signal_voltage'] = 1.0
                if analysis == 'ac' and bench.supply and bench.supply in bench.ac_sources:
                    found['ac_stimulus_on_supply'] = 1.0
            elif node.value in _CURRENT:
                found['signal_current'] = 1.0
                terminal = (_first_string(node) or '').strip('/').split('/')[0]
                if terminal:
                    found['from_supply' if terminal == bench.supply else 'from_other_source'] = 1.0
            elif node.value == 'getData':
                result = _keyword(node, 'result')
                result = result.value if result is not None and result.kind == 'string' else ''
                name = (_first_string(node) or '').strip('/')
                if result == 'stb' and name == 'loopGain':
                    found['signal_loop_gain'] = 1.0
                elif result == 'xf':
                    found['signal_transfer_xf'] = 1.0
                    if name:
                        found['from_supply' if name == bench.supply else 'from_other_source'] = 1.0
                elif result == 'noise':
                    found['signal_noise'] = 1.0
                else:
                    found['signal_other_data'] = 1.0
            reduction = _REDUCTION_OF.get(node.value)
            if reduction:
                found[f'reduction_{reduction}'] = 1.0
            if analysis in PLACED_ANALYSES and 'has_position' not in found:
                place = _place(node)
                if place is not None:
                    low, high = place
                    found['position'] = math.log10(math.sqrt(low * high)) / 10
                    found['span'] = math.log10(high / low) / 10
                    found['has_position'] = 1.0
        elif node.kind == 'div' and all(_signal_calls(child) for child in node.children):
            found['form_ratio'] = 1.0
        elif node.kind == 'sub' and all(any(c.value in _VOLTAGE for c in _signal_calls(child)) for child in node.children):
            found['node_difference'] = 1.0
        if node.kind in ('mul', 'div') and any(_is_constant(c) for c in node.children) and _signal_calls(node):
            found['form_scaled'] = 1.0
        if node.kind in ('add', 'sub') and any(_is_constant(c) for c in node.children) and _signal_calls(node):
            found['form_offset'] = 1.0
    top = tree
    if top.kind == 'neg' or (top.kind == 'mul' and any(_is_constant(c) and (_evaluate(c) or 0) < 0 for c in top.children)):
        found['form_negated'] = 1.0
    return found


def _place(node):
    """(low, high) of a call that reads at a point (value(x p): low = high = p) or over a window (clip/integ(x a b));
    None for any other node, or bounds that are not positive constants. A window from 0 counts as its upper end."""
    if node.kind != 'call' or not (node.value == 'value' or node.value in _WINDOWS):
        return None
    plain = [c for c in node.children if c.kind != 'keyword']
    bounds = plain[-1:] if node.value == 'value' else plain[1:3]
    if len(plain) < 2 or len(bounds) != (1 if node.value == 'value' else 2) or not all(_is_constant(b) for b in bounds):
        return None
    values = [_evaluate(b) for b in bounds]
    if any(v is None for v in values):
        return None
    low, high = (values[0], values[0]) if len(values) == 1 else (min(values), max(values))
    if high <= 0:
        return None
    return (high, high) if low <= 0 else (low, high)


def _evaluate(node):
    try:
        if node.kind == 'number':
            return node.value
        if node.kind == 'neg':
            return -_evaluate(node.children[0])
        a, b = (_evaluate(c) for c in node.children)
        return dict(add=a + b, sub=a - b, mul=a * b, div=a / b if b else None)[node.kind]
    except (TypeError, ValueError, IndexError, KeyError):
        return None


# ------------------------------------------------------------------------------------------ the task
def describe_specs(config, bench=None):
    """{metric_id: tuple of len(DESCRIPTOR_COLUMNS) numbers} for every spec of a configuration."""
    bench = bench_of_task(config) if bench is None else bench
    probes = {m.measurement_id: m for m in config.measurements}
    described = {}
    for target in config.targets:
        equation = target.equation.strip()
        names = [equation] if equation in probes else sorted(
            (n for n in (spec_equations.parse(equation)[0] or ()) if n in probes), key=lambda n: _first_at(equation, n))
        columns = {}
        for name in names:                       # in the order the equation names them: the first one placed sets the place
            probe = probes[name]
            facts = probe_facts(probe.analysis, probe.signal, bench,
                                measured_by_analyzer=probe.result_source in ('backend_profile', 'size_estimate'))
            for key, value in facts.items():
                if key in ('position', 'span'):
                    columns.setdefault(key, value)
                else:
                    columns[key] = max(columns.get(key, 0.0), value)
        if len(names) > 1 or (names and equation not in probes):
            columns['form_combined_probes'] = 1.0
        columns['probe_count'] = math.log1p(len(names))
        described[target.metric_id] = tuple(float(columns.get(c, 0.0)) for c in DESCRIPTOR_COLUMNS)
    return described


def measured_nets(config) -> tuple:
    """The nets whose voltage the probes of the ACTIVE specs read (record 7.317: the "output" tag of the net-role
    rule), as graph net names: an OCEAN signal path "/VOUT" is the net VOUT, "/DUT/X" the net DUT/X. A probe without an
    expression this module reads (a built-in analyzer's, an ngspice measure) names none."""
    probes = {m.measurement_id: m for m in config.measurements}
    found = set()
    for target in config.targets:
        if not target.active:
            continue
        equation = target.equation.strip()
        names = [equation] if equation in probes else [n for n in (spec_equations.parse(equation)[0] or ()) if n in probes]
        for name in names:
            probe = probes[name]
            if probe.result_source in ('backend_profile', 'size_estimate'):
                continue
            tree = parse_expression(probe.signal)
            for node in (_walk(tree) if tree is not None else ()):
                if node.kind == 'call' and node.value in _VOLTAGE:
                    path = _first_string(node)
                    if path:
                        found.add(path.strip().lstrip('/'))
    return tuple(sorted(found))


def _first_at(text, name):
    match = re.search(r'(?<![\w.])' + re.escape(name) + r'(?![\w])', text)
    return match.start() if match else len(text)


def spec_set_schema():
    from analog_optimizer.models.inputs import SpecSetSchema
    return SpecSetSchema(DESCRIPTOR_VERSION, DESCRIPTOR_COLUMNS, UNIT_REFERENCES)


_WORDS = dict(signal_voltage='node voltages', signal_current='a source current', signal_loop_gain='the stb loop gain',
              signal_transfer_xf='an xf transfer', signal_noise='output noise', signal_other_data='other simulator data',
              signal_no_expression="a built-in analyzer's result",
              from_supply='from the supply', from_other_source='from another source',
              ac_stimulus_on_supply='with the AC stimulus on the supply', node_difference='a difference of two nodes',
              form_ratio='a ratio', form_negated='negated', form_scaled='scaled by a constant',
              form_offset='offset by a constant', form_combined_probes='combining several probes',
              reduction_value_at='value at a point', reduction_cross='a crossing', reduction_margin='a phase/gain margin',
              reduction_extreme='an extreme', reduction_window='a window', reduction_integral='an integral or average',
              reduction_waveform='a waveform measure', reduction_magnitude='a magnitude', reduction_decibel='in decibels',
              reduction_root='a root or power')


def words(described, unit):
    """One plain line saying what the network reads for a spec (the validation report shows it on the Specs row)."""
    columns = dict(zip(DESCRIPTOR_COLUMNS, described))
    analyses = [a for a in ANALYSES if columns[f'analysis_{a}']]
    parts = [unit or 'no unit', (', '.join(analyses) + ' analysis') if analyses else 'no analysis']
    parts.append('reads ' + (', '.join(_WORDS[f'signal_{s}'] for s in SIGNALS if columns[f'signal_{s}']) or 'nothing it recognises'))
    parts += [_WORDS[k] for k in SOURCES + tuple(f'form_{f}' for f in FORMS) if columns[k]]
    reductions = [_WORDS[f'reduction_{r}'] for r in REDUCTIONS if columns[f'reduction_{r}']]
    if reductions:
        parts.append('as ' + ', '.join(reductions))
    if columns['has_position']:
        unit = 's' if columns['analysis_tran'] and not any(columns[f'analysis_{a}'] for a in FREQUENCY_ANALYSES) else 'Hz'
        centre, span = 10 ** (columns['position'] * 10), 10 ** (columns['span'] * 10)
        low, high = (float(f'{x:.4g}') for x in (centre / math.sqrt(span), centre * math.sqrt(span)))
        parts.append(f"at {units.text(float(f'{centre:.4g}'), unit)}" if columns['span'] == 0 else
                     f'over {units.text(low, unit)} to {units.text(high, unit)}')
    return '; '.join(parts)
