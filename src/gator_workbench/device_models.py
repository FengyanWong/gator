"""Technology numbers of a PDK's MOS models, read from its Spectre model library (record 7.298): what the network's
"PDK-relative sizes" and "device model features" inputs need.

For every MOS model of a loaded PDK (``pdk.json``: the models its cells netlist to) this reads, in the library section
a task simulates at nominal (``tt``):

- the smallest bin the model covers (its ``lmin``/``wmin``), whose lower bounds are the minimum length and width the
  sizes are divided by, else the CDF default size of the cell (the record's ``default``), said so in ``basis``;
- four numbers of that bin: threshold voltage ``vth0``, mobility ``u0`` (m^2/Vs; a value above 1 is cm^2/Vs, as BSIM
  reads it), saturation velocity ``vsat`` (m/s) and oxide thickness ``toxe``/``tox`` (m).

The library is the one Load PDK already copied into the local model-file cache (``pdk_remote.ModelFileCache``): nothing
here reaches the simulator host. Spectre's library language is followed as far as these numbers need: ``library`` /
``section`` / ``endsection``, ``include "file" section=name``, ``parameters``, ``model`` cards (one line, continued
lines, brace bins ``{ 1: ... }``), ``inline subckt`` wrappers (their own parameters and the model their device uses) and
``statistics`` blocks (skipped). Parameter expressions are evaluated with the section's parameters only (a small
arithmetic evaluator - no code is run); a number that cannot be evaluated is left out, never guessed.

The numbers stay in the local PDK folder (``device_models.json`` beside ``pdk.json``): no route returns them and no
message shows them (CLAUDE.md: PDK models are never shown or sent).
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re
from pathlib import PurePosixPath

from .paths import local_settings_dir
from .pdk_record import load_record, pdk_dir
from .storage.atomic import write_json

FORMAT = 'gator-device-models-v1'
FILE = 'device_models.json'
FEATURES = ('vth0', 'u0', 'vsat', 'tox')
ALIASES = dict(vth0=('vth0', 'vtho'), u0=('u0', 'uo'), vsat=('vsat',), tox=('toxe', 'tox'))
MOS_TYPES = re.compile(r'^(bsim\w*|psp\w*|hisim\w*|ekv\w*|mos\d*|bsimsoi\w*|b3soi\w*|b4soi\w*|nmos|pmos)$', re.I)
_SI = dict(T=1e12, G=1e9, M=1e6, K=1e3, k=1e3, m=1e-3, u=1e-6, n=1e-9, p=1e-12, f=1e-15, a=1e-18)
_NUMBER = re.compile(r'(?<![\w.])(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?([TGMKkmunpfa])?(?![\w.])')


class ModelLibraryError(ValueError):
    """The model library cannot be read the way this module needs."""


# ------------------------------------------------------------------------------------------ expressions
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow}
_FUNCTIONS = dict(sqrt=math.sqrt, exp=math.exp, log=math.log, ln=math.log, log10=math.log10, abs=abs, min=min, max=max,
                  pow=math.pow, int=int, floor=math.floor, ceil=math.ceil, tanh=math.tanh, sin=math.sin, cos=math.cos)


def _python(text):
    """A Spectre expression in Python syntax: SI-suffixed numbers as plain floats, '^' as '**'."""
    def number(match):
        value = float(match.group(1) + (match.group(2) or ''))
        return repr(value * _SI[match.group(3)] if match.group(3) else value)
    return _NUMBER.sub(number, text.strip().strip("'\"")).replace('^', '**')


def evaluate(text, scope, *, depth=0):
    """The value of a Spectre expression with the names of `scope` (name -> expression text, evaluated as needed), or
    None when it uses anything else (an undefined name, a statistical function, a condition)."""
    if depth > 32:
        return None
    try:
        tree = ast.parse(_python(str(text)), mode='eval').body
    except (SyntaxError, ValueError):
        return None
    try:
        value = _node(tree, scope, depth)
    except (ArithmeticError, ValueError, TypeError, KeyError, RecursionError):
        return None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _node(node, scope, depth):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _node(node.operand, scope, depth)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)](_node(node.left, scope, depth), _node(node.right, scope, depth))
    if isinstance(node, ast.Name):
        if node.id not in scope:
            raise KeyError(node.id)
        value = evaluate(scope[node.id], {k: v for k, v in scope.items() if k != node.id}, depth=depth + 1)
        if value is None:
            raise ValueError(node.id)
        return value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS
            and not node.keywords):
        return _FUNCTIONS[node.func.id](*(_node(a, scope, depth) for a in node.args))
    raise ValueError('unsupported expression')


# ------------------------------------------------------------------------------------------ the library text
_HEAD = re.compile(r'(?<![\w.<>=!])([A-Za-z_][\w.]*)\s*=(?!=)')


def assignments(text):
    """name=value pairs of a statement's text, names and values as written (Spectre is case-sensitive). A value runs
    to the next "name=", so an expression written with spaces ("vth0= -0.5 + d") stays whole."""
    heads = list(_HEAD.finditer(text))
    found = {}
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        value = text[head.end():end].strip()
        if value:
            found[head.group(1)] = value
    return found


def _field(values, name):
    """A card's value of `name` whatever its spelling's case (model parameter names are case-insensitive in BSIM)."""
    if name in values:
        return values[name]
    lowered = {k.lower(): v for k, v in values.items()}
    return lowered.get(name.lower())


def statements(text):
    """The file's statements: comments removed, continued lines joined, a brace block kept whole with its statement."""
    lines, current, depth = [], '', 0
    for raw in text.splitlines():
        line = raw.split('//')[0]
        if not current and line.lstrip().startswith('*'):
            continue
        line = line.rstrip()
        if line.lstrip().startswith('+'):                    # a "+" line continues the statement before it
            if current:
                part = line.lstrip()[1:]
                current += ' ' + part
                depth += part.count('{') - part.count('}')
                continue
            if lines:
                lines[-1] += ' ' + line.lstrip()[1:]
                continue
        if line.endswith('\\'):
            part = line[:-1]
            current += part + ' '
            depth += part.count('{') - part.count('}')
            continue
        current += line
        depth += line.count('{') - line.count('}')
        if depth > 0:
            current += '\n'
            continue
        if current.strip():
            lines.append(current.strip())
        current, depth = '', 0
    if current.strip():
        lines.append(current.strip())
    return lines


class _Library:
    """Statements of the reachable files of one section (nominal), with their parameters, cards and inline wrappers."""

    def __init__(self, read):
        self.read = read                     # remote path -> text (or None when the file is not in the cache)
        self.parameters = {}                 # name -> expression text, the section's (later ones win, as in Spectre)
        self.cards = {}                      # model name -> dict(type, values, bins)
        self.wrappers = {}                   # inline subckt name -> dict(parameters, cards, devices)
        self.missing, self.seen = [], set()

    def load(self, path, section=None):
        key = (str(path), section)
        if key in self.seen:
            return
        self.seen.add(key)
        text = self.read(str(path))
        if text is None:
            self.missing.append(str(path))
            return
        self._statements(statements(text), PurePosixPath(str(path)), section)

    def _statements(self, items, path, section):
        active = section is None          # a file read whole: statements outside every section count
        current, wrapper = None, None
        for item in items:
            words = item.split()
            head = words[0].lower() if words else ''
            if head == 'simulator':
                continue
            if head == 'section':
                current = words[1] if len(words) > 1 else None
                continue
            if head == 'endsection':
                current = None
                continue
            if head in ('library', 'endlibrary', 'endl'):
                continue
            inside = current == section if section is not None else current is None
            if not (inside or (active and current is None)):
                continue
            if head == 'statistics':
                continue
            if head == 'include':
                match = re.match(r'include\s+"([^"]+)"(?:\s+section\s*=\s*(\S+))?', item)
                if match:
                    target = PurePosixPath(match.group(1))
                    target = target if target.is_absolute() else path.parent / target
                    self.load(target, match.group(2))
                continue
            if head == 'inline' and len(words) > 2 and words[1].lower() == 'subckt':
                wrapper = dict(name=words[2].split('(')[0], parameters={}, cards={}, devices=[])
                continue
            if head == 'ends':
                if wrapper is not None:
                    self.wrappers[wrapper['name']] = wrapper
                wrapper = None
                continue
            if head == 'parameters':
                (wrapper['parameters'] if wrapper is not None else self.parameters).update(assignments(item[len('parameters'):]))
                continue
            if head == 'model' and len(words) >= 3:
                name, kind = words[1], words[2].split('{')[0]
                card = dict(type=kind, values={}, bins=[])
                body = item.split(None, 3)[3] if len(words) > 3 else ''
                if '{' in item:
                    outer, _, inner = item.partition('{')
                    card['values'] = assignments(outer.split(None, 3)[3] if len(outer.split()) > 3 else '')
                    for _, bin_text in re.findall(r'(?:^|\s)(\d+)\s*:\s*(.*?)(?=(?:\s\d+\s*:)|\}|$)', inner, re.S):
                        card['bins'].append(assignments(bin_text))
                else:
                    card['values'] = assignments(body)
                (wrapper['cards'] if wrapper is not None else self.cards)[name] = card
                continue
            if wrapper is not None:
                match = re.match(r'(\S+)\s*\(([^)]*)\)\s*(\S+)(.*)$', item)
                if match:
                    wrapper['devices'].append(dict(master=match.group(3), values=assignments(match.group(4))))


def _mos_card(library, name):
    """(card, scope) of the MOS model a device master names: a card itself, or the card the device of an inline
    subckt wrapper uses (with the wrapper's parameters in scope)."""
    wrapper = library.wrappers.get(name)
    card = library.cards.get(name) if wrapper is None else None
    if card is not None:
        # a card defined beside the inline wrappers that use it may name their local defaults (mismatch switches,
        # geometry factors): those defaults stand in, the section's own parameters first
        defaults = {k: v for w in library.wrappers.values() for k, v in w['parameters'].items()}
        return card, dict(defaults, **library.parameters)
    if wrapper is None:
        return None, None
    scope = dict(library.parameters, **wrapper['parameters'])
    for device in wrapper['devices']:
        inner = wrapper['cards'].get(device['master']) or library.cards.get(device['master'])
        if inner is not None and MOS_TYPES.match(inner['type']):
            return inner, scope        # the card reads the wrapper's parameters; the device line only passes them on
    return None, None


def _smallest_bin(card, scope):
    """The values of the card's bin with the smallest lmin (then wmin): the minimum-size device."""
    bins = [dict(card['values'], **b) for b in card['bins']] or [card['values']]
    def size(values):
        found = (_field(values, k) for k in ('lmin', 'wmin'))
        return tuple(math.inf if text is None else (evaluate(text, scope) or math.inf) for text in found)
    return min(bins, key=size)


def _number_of(text):
    if text is None:
        return None
    match = _NUMBER.fullmatch(str(text).strip().strip('"'))
    if not match:
        return None
    value = float(match.group(1) + (match.group(2) or ''))
    return value * _SI[match.group(3)] if match.group(3) else value


def read_library(read, entry, section):
    library = _Library(read)
    library.load(entry, section)
    return library


def mos_numbers(library, record, *, temperature_c=27.0):
    """{model: dict(lmin, wmin, basis, vth0, u0, vsat, tox)} for every MOS model of the PDK record, and
    {model: reason} for the ones that could not be read. Absent numbers are left out (the network masks them).
    Spectre's own `temp` and `tnom` are the nominal temperature and `m`, the implicit multiplier of a subckt instance, 1."""
    found, problems = {}, {}
    builtins = dict(temp=repr(float(temperature_c)), tnom=repr(float(temperature_c)), m='1')   # m: a subckt's implicit multiplier
    for model, device in sorted((record or {}).get('devices', {}).items()):
        if device.get('standard_kind') not in ('nmos', 'pmos'):
            continue
        card, scope = _mos_card(library, model)
        scope = None if scope is None else dict(builtins, **scope)
        defaults = {p['name']: _number_of(p.get('default')) for p in device.get('parameters', ()) if p.get('name') in ('w', 'l')}
        numbers = {}
        if card is not None:
            values = _smallest_bin(card, scope)
            sizes = {k: evaluate(_field(values, k), scope) for k in ('lmin', 'wmin') if _field(values, k) is not None}
            # a card's own expressions may use the instance's l and w: take the bin's minimum size for them
            local = dict(scope, l=repr(sizes.get('lmin') or defaults.get('l') or 1e-6),
                         w=repr(sizes.get('wmin') or defaults.get('w') or 1e-6))
            for feature, names in ALIASES.items():
                value = next((evaluate(_field(values, n), local) for n in names if _field(values, n) is not None), None)
                if value is not None:
                    numbers[feature] = value * 1e-4 if feature == 'u0' and value > 1 else value
            if sizes.get('lmin') and sizes.get('wmin'):
                numbers.update(lmin=sizes['lmin'], wmin=sizes['wmin'], basis='model bin')
        if 'lmin' not in numbers and defaults.get('l') and defaults.get('w'):
            numbers.update(lmin=defaults['l'], wmin=defaults['w'], basis='CDF default size')
        if numbers:
            found[model] = numbers
        else:
            problems[model] = 'not found in the nominal section of the cached model library' if card is None else 'no usable number'
    return found, problems


# ------------------------------------------------------------------------------------------ the PDK folder
def _cache_reader(pdk_id, record):
    """remote path -> cached text, for the model files Load PDK cached for this PDK (any host's cache folder)."""
    shas = {f['path']: f['sha256'] for f in record.get('sources', {}).get('model_files', ())}
    folders = [p for p in (local_settings_dir() / 'pdk-model-files').glob(f'*/{record.get("technology_library") or pdk_id}')
               if (p / 'index.json').is_file()]

    def read(path):
        sha = shas.get(path)
        for folder in folders:
            try:
                index = json.loads((folder / 'index.json').read_text())
            except (OSError, ValueError):
                continue
            entry = index.get(path)
            if entry and (sha is None or entry.get('sha256') == sha):
                try:
                    return (folder / entry['sha256']).read_text(errors='replace')
                except OSError:
                    continue
        return None
    return read


def build(pdk_id, *, entry=None, section='tt'):
    """Read the numbers of a loaded PDK from its cached model library and keep them beside its record. Returns the
    saved document (callers show counts only)."""
    record = load_record(pdk_id)
    if record is None:
        raise ModelLibraryError(f'PDK {pdk_id} is not loaded: read it in the PDK window first')
    files = [f['path'] for f in record.get('sources', {}).get('model_files', ())]
    entry = entry or (files[0] if files else None)
    if entry is None:
        raise ModelLibraryError(f'PDK {pdk_id} lists no model files')
    library = read_library(_cache_reader(pdk_id, record), entry, section)
    devices, problems = mos_numbers(library, record)
    document = dict(format=FORMAT, pdk_id=pdk_id, record_sha256=record.get('sha256'), entry=entry, section=section,
                    files_missing=sorted(set(library.missing)), devices=devices, problems=problems)
    write_json(pdk_dir(pdk_id) / FILE, document)
    return document


def load(pdk_id, *, entry=None, section='tt'):
    """The saved numbers of a PDK, rebuilt when missing or made from another version of its record (or another entry
    file or section)."""
    record = load_record(pdk_id)
    if record is None:
        return None
    try:
        document = json.loads((pdk_dir(pdk_id) / FILE).read_text())
    except (OSError, ValueError):
        document = None
    if (not isinstance(document, dict) or document.get('format') != FORMAT or document.get('record_sha256') != record.get('sha256')
            or document.get('section') != section or (entry is not None and document.get('entry') != entry)):
        try:
            document = build(pdk_id, entry=entry, section=section)
        except ModelLibraryError:
            return None
    return document


def summary(document):
    """Counts only - what a message may say about the numbers."""
    if not document:
        return 'no device model numbers'
    devices = document.get('devices', {})
    with_features = sum(all(f in d for f in FEATURES) for d in devices.values())
    from_bins = sum(d.get('basis') == 'model bin' for d in devices.values())
    total = len(devices) + len(document.get('problems', {}))
    return (f'{len(devices)} of {total} MOS models read ({with_features} with all four technology numbers, '
            f'{from_bins} minimum sizes from their model bins)')
