"""Measuring a Maestro-measured task: its Maestro output expressions, evaluated with OCEAN on each run's own results
(Virtuoso task flow, part 5).

Every evaluation of such a task runs Maestro's own deck around the circuit the run adapter exported (see
`recipes.GenericMaestroProfile`); Spectre leaves its results on the simulator host (the bridge keeps the folder), and
this module evaluates the task's outputs there with OCEAN - the calculator Maestro itself uses - inside the Virtuoso
session: ``openResults`` on that folder, then each output's expression.

Names: a Maestro expression names signals as the schematic does (``VT("/OUT")``, ``IT("/V0/PLUS")``); a result folder
of a plain Spectre run names them as Spectre does (``OUT``, ``XU1.N1``, ``V0:p``). ADE translates with the name maps its
netlister writes (``amap/``); `Names` reads the same maps from Maestro's netlist of the task's test and every signal
string is translated once, when the task is saved. What the maps do not translate plainly (a terminal defined as a
function of another, a signal not in the maps) is refused then, in words - never guessed.

Side effect, stated: ``openResults`` / ``selectResult`` set OCEAN's current results in the user's Virtuoso session (as
the bridge's own waveform export does); ADE and Maestro windows keep their own. OCEAN's ``simulator()`` is never called
(it would reset the OCEAN session).
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shlex

from .virtuoso_setup import FUNCTIONS, TOKEN

NETS = frozenset('VT VF VS VDC VN VN2 getData'.split())         # a string argument that names a net
TERMINALS = frozenset('IT IF IS IDC'.split())                   # ... a terminal of an instance (its current)
INSTANCES = frozenset('OP OPT'.split())                          # ... an instance (its operating point)
PATH = re.compile(r'^/[A-Za-z0-9_!<>\[\]:.\-]+(?:/[A-Za-z0-9_!<>\[\]:.\-]+)*$')
RAW = re.compile(r'^/[A-Za-z0-9_./\-]+$')                        # a result folder on the simulator host
ENTRY = re.compile(r'^"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"\s*$')


class NameError_(ValueError):
    """A signal the name maps cannot translate plainly."""


def _read_map(path) -> list[tuple[str, str]]:
    """The entries of one amap file: ("key", "value") pairs after its HEADER and PSFversion lines."""
    pairs = []
    for line in Path(path).read_text().splitlines():
        match = ENTRY.match(line.strip())
        if match and match.group(1) != 'PSFversion':
            pairs.append((match.group(1).replace('\\"', '"'), match.group(2).replace('\\"', '"')))
    return pairs


class Names:
    """Schematic names -> Spectre result names, from the ``amap/`` folder of a Maestro netlist (the maps ADE uses).

    ``<cell>.inst``: "<instances>n" -> the map file of their master; for a primitive master "<terminal>v" -> ":<t>v"
    (its Spectre terminal); for a subcircuit "<port>v" -> ":<index>v". ``<cell>.net``: "<net>v" -> "<spectre net>v"
    (e.g. gnd! -> 0). ``top_level_map.inst``: the top cell. ``__simulator_information__``: the delimiters."""

    def __init__(self, amap):
        amap = Path(amap)
        info = dict(_read_map(amap / '__simulator_information__')) if (amap / '__simulator_information__').is_file() else {}
        self.hierarchy_delimiter = info.get('__artHierarchyDelimiter__', '.')
        self.terminal_delimiter = info.get('__artInstanceTerminalDelimiter__', ':')
        top = dict(_read_map(amap / 'top_level_map.inst')).get('__NEXT_FILE__')
        if not top:
            raise NameError_('The netlist has no top-level name map (amap/top_level_map.inst)')
        self.top, self.maps, self.nets = top, {}, {}
        for path in amap.glob('*.inst'):
            instances, terminals = {}, {}
            for key, value in _read_map(path):
                names = key.split()                                # "MP3n MP2n MP1n": every name carries its own tag
                if names and all(name.endswith('n') for name in names):
                    instances.update({name[:-1]: value for name in names})
                elif names and all(name.endswith('v') for name in names):
                    terminals.update({name[:-1]: value for name in names})
            self.maps[path.stem] = dict(instances=instances, terminals=terminals)
        for path in amap.glob('*.net'):
            self.nets[path.stem] = {key[:-1]: value[:-1] for key, value in _read_map(path) if key.endswith('v') and value.endswith('v')}

    def _walk(self, parts):
        """(cell map name of the cell that holds the last part, Spectre instance path of the parts before it)."""
        cell, path = self.top, []
        for part in parts:
            master = self.maps.get(cell, {}).get('instances', {}).get(part)
            if master is None:
                raise NameError_(f'{part} is not an instance of {cell} in the name maps')
            cell, path = master, path + [part]
        return cell, path

    def net(self, name) -> str:
        parts = name.strip('/').split('/')
        cell, path = self._walk(parts[:-1])
        net = self.nets.get(cell, {}).get(parts[-1], parts[-1])
        return self.hierarchy_delimiter.join(path + [net])

    def instance(self, name) -> str:
        parts = name.strip('/').split('/')
        self._walk(parts)                                          # every level must be a known instance
        return self.hierarchy_delimiter.join(parts)

    def terminal(self, name) -> str:
        parts = name.strip('/').split('/')
        if len(parts) < 2:
            raise NameError_(f'{name} names no terminal of an instance (/<instance>/<terminal>)')
        master, path = self._walk(parts[:-1])
        mapped = self.maps.get(master, {}).get('terminals', {}).get(parts[-1])
        if mapped is None:
            raise NameError_(f'{parts[-1]} is not a terminal of {parts[-2]} in the name maps')
        if not re.match(r'^:[A-Za-z0-9_]+v$', mapped):
            raise NameError_(f'The current of {name} is derived by the netlister ({mapped[:-1]}), not saved as such: '
                             'measure the terminal it is derived from instead')
        return self.hierarchy_delimiter.join(path) + self.terminal_delimiter + mapped[1:-1]


def translate(expression, names) -> str:
    """The expression with every signal string argument of a signal function translated to its Spectre result name.
    Raises NameError_ (in words) for a signal the maps do not translate plainly."""
    out, pending = [], None
    for match in TOKEN.finditer(expression):
        kind, text = match.lastgroup, match.group(match.lastgroup)
        start, end = match.span(kind)
        out.append(expression[match.start():start])               # the whitespace the token pattern skipped
        if kind == 'string' and pending is not None:
            value = text[1:-1]
            if value.startswith('/'):
                if not PATH.match(value):
                    raise NameError_(f'{value} is not a schematic path the workbench translates')
                value = names.terminal(value) if pending in TERMINALS else names.instance(value) if pending in INSTANCES else names.net(value)
            text = '"' + value + '"'
            pending = None
        elif kind == 'name' and text in FUNCTIONS and expression[end:].lstrip().startswith('('):
            pending = text if text in NETS | TERMINALS | INSTANCES else None
        elif kind != 'op' or text != '(':
            pending = None
        out.append(text)
    return ''.join(out)


def remote_raw_dir(metadata) -> str:
    """The result folder a bridge Spectre run left on the simulator host: the `-raw` argument of its command."""
    argv = shlex.split((metadata or {}).get('spectre_command') or '')
    if '-raw' not in argv or argv.index('-raw') + 1 >= len(argv):
        raise ValueError('The simulation left no result folder on the simulator host (no -raw in its command)')
    raw = argv[argv.index('-raw') + 1]
    if not RAW.match(raw) or '/../' in raw:
        raise ValueError(f'Unexpected result folder {raw!r}')
    return raw


def program(raw_dir, outputs) -> str:
    """The SKILL that opens one result folder and evaluates each output: one line "name=value" per output (value
    "nil" when the expression gave no number). `outputs`: [{name, spectre_expression, analysis}], all checked."""
    lines = ['let((v out)', f'  unless(openResults("{raw_dir}") error("GATOR: no results in {raw_dir}"))', '  out = ""']
    for output in outputs:
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$', output['name']) or not re.match(r'^[a-z][a-z0-9_]{0,31}$', output['analysis']):
            raise ValueError(f'Unexpected output {output["name"]!r} / analysis {output["analysis"]!r}')
        lines += [f"  errset(selectResult('{output['analysis']}) nil)",
                  f"  v = car(errset({output['spectre_expression']} nil))",
                  f'  out = strcat(out "{output["name"]}=" if(numberp(v) sprintf(nil "%.17g" float(v)) "nil") "\\n")']
    lines += ['  out)']
    return '\n'.join(lines)


def parse(text, outputs) -> dict:
    """{output name: float | None} from the program's answer (the decoded SKILL string)."""
    values = {o['name']: None for o in outputs}
    for line in (text or '').replace('\\n', '\n').splitlines():
        name, _, value = line.strip().strip('"').partition('=')
        if name in values and value not in ('', 'nil'):
            try:
                number = float(value)
            except ValueError:
                continue
            values[name] = number if math.isfinite(number) else None
    return values


_CLIENTS = {}


def _client(bridge):
    """A Virtuoso client of this process for the connection the run uses. The run adapter watches the VB_ variables of
    its process; making a client must not change them, so they are put back exactly as they were."""
    key = (bridge.get('profile'), bridge.get('env_file'))
    if key in _CLIENTS:
        return _CLIENTS[key]
    import site
    if bridge.get('site'):
        site.addsitedir(str(Path(bridge['site']).resolve()))
    before = {k: v for k, v in os.environ.items() if k.startswith('VB_')}
    try:
        from virtuoso_bridge import VirtuosoClient
        client = VirtuosoClient.from_env(timeout=60, log_to_ciw=False, profile=bridge.get('profile') or None)
    finally:
        for name in [k for k in os.environ if k.startswith('VB_') and k not in before]:
            del os.environ[name]
        os.environ.update(before)
    _CLIENTS[key] = client
    return client


def measure(bridge, raw_dir, outputs, *, client=None) -> dict:
    """{output name: value | None}: the outputs evaluated with OCEAN on `raw_dir` in the Virtuoso session."""
    from virtuoso_bridge import decode_skill_output
    session = client or _client(bridge)
    try:
        result = session.execute_skill(program(raw_dir, outputs), timeout=120)
    except Exception:
        _CLIENTS.pop((bridge.get('profile'), bridge.get('env_file')), None)   # a dropped link is made again next time
        raise
    if not result.ok or result.errors:
        raise ValueError('OCEAN could not evaluate the outputs: ' + ('; '.join(result.errors) or 'SKILL call failed'))
    return parse(decode_skill_output(result.output), outputs)
