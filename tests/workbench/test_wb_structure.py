"""The package's import structure, as the refactoring of 2026-10-09 left it (docs/plan-refactoring.md, package B1):

- no import cycle among the workbench's modules beyond the three known ones (imports inside functions count: they
  close a cycle at run time just the same);
- every import of a workbench module inside a function says why it is there, in a comment on its line or the line
  above (`# lazy: ...`) - except in the process entry points, which import at use on purpose;
- no module outside api/ imports the API, except the command line that serves it;
- every name a test patches on a workbench module exists at the top of that module: a patch of a name that moved
  elsewhere fails here, statically, instead of patching nothing.

Imports of the optimizer package (analog_optimizer) stay inside functions without a comment: a process that does not
use the optimizer then never imports torch. Pure AST: nothing is imported.
"""
import ast
import collections
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'src'
PACKAGE = 'gator_workbench'
KNOWN_CYCLES = [
    {'gator_workbench.paths', 'gator_workbench.directories', 'gator_workbench.layout'},   # bridge_state_dir, local_scratch, check_local
    {'gator_workbench.connection', 'gator_workbench.ngspice_link'},                       # the probe of an ngspice connection
    {'gator_workbench.cdf_write', 'gator_workbench.cdf_factory'},                         # the factory imports torch: at use only
]
ENTRY_MODULES = {'gator_workbench.cli', 'gator_workbench.worker'}
ENTRY_FUNCTIONS = {('gator_workbench.connection', '_probe_main'), ('gator_workbench.bridge_read', '_main')}


def modules():
    found = {}
    for dirpath, _, files in os.walk(SRC / PACKAGE):
        if '__pycache__' in dirpath:
            continue
        for f in files:
            if f.endswith('.py'):
                path = Path(dirpath) / f
                parts = list(path.relative_to(SRC).with_suffix('').parts)
                is_pkg = parts[-1] == '__init__'
                name = '.'.join(parts[:-1] if is_pkg else parts)
                text = path.read_text(encoding='utf-8')
                found[name] = dict(path=path, text=text, tree=ast.parse(text), is_pkg=is_pkg)
    return found


MODULES = modules()


def absolute(module, stmt):
    if not stmt.level:
        return stmt.module or ''
    base = module.split('.')
    if not MODULES[module]['is_pkg']:
        base = base[:-1]
    if stmt.level > 1:
        base = base[:len(base) - (stmt.level - 1)]
    return '.'.join(base + ([stmt.module] if stmt.module else []))


def targets(module, stmt):
    out = set()
    if isinstance(stmt, ast.ImportFrom):
        base = absolute(module, stmt)
        if not base.startswith(PACKAGE):
            return out
        for alias in stmt.names:
            if f'{base}.{alias.name}' in MODULES:
                out.add(f'{base}.{alias.name}')
            else:
                t = base
                while t and t not in MODULES:
                    t = t.rpartition('.')[0]
                if t:
                    out.add(t)
    else:
        out |= {a.name for a in stmt.names if a.name in MODULES}
    return out - {module}


def graph():
    edges = collections.defaultdict(set)
    for name, info in MODULES.items():
        for node in ast.walk(info['tree']):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                edges[name] |= targets(name, node)
    return edges


def cycles(edges):
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]

    def strong(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in edges.get(v, ()):
            if w not in index:
                strong(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component = set()
            while True:
                w = stack.pop()
                on.discard(w)
                component.add(w)
                if w == v:
                    break
            if len(component) > 1:
                found.append(component)
    for v in sorted(MODULES):
        if v not in index:
            strong(v)
    return found


def test_no_import_cycle_beyond_the_known_ones():
    edges = graph()
    unknown = [sorted(c) for c in cycles(edges) if c not in KNOWN_CYCLES]
    assert not unknown, ('new import cycle(s) among the workbench modules (imports inside functions count): '
                         + '; '.join(' <-> '.join(m.split('.', 1)[1] for m in c) for c in unknown))


def own_statements(func):
    """The statements of a function's own code: its body and every block in it, not the functions or classes it defines."""
    stack = list(func.body)
    while stack:
        stmt = stack.pop(0)
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field in ('body', 'orelse', 'finalbody'):
            stack.extend(getattr(stmt, field, None) or [])
        for handler in getattr(stmt, 'handlers', None) or []:
            stack.extend(handler.body)


def test_every_import_of_a_workbench_module_inside_a_function_says_why():
    silent = []
    for name, info in MODULES.items():
        if name in ENTRY_MODULES:
            continue
        lines = info['text'].split('\n')
        for top in info['tree'].body:
            for func in [n for n in ast.walk(top) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                if (name, top.name if hasattr(top, 'name') else None) in ENTRY_FUNCTIONS:
                    continue
                for stmt in own_statements(func):
                    if isinstance(stmt, (ast.Import, ast.ImportFrom)) and targets(name, stmt):
                        line, above = lines[stmt.lineno - 1], lines[stmt.lineno - 2] if stmt.lineno > 1 else ''
                        if '#' not in line[stmt.col_offset:] and not above.strip().startswith('#'):
                            silent.append(f'{info["path"].relative_to(ROOT)}:{stmt.lineno} {line.strip()}')
    assert not silent, ('an import of a workbench module inside a function, with no comment saying why (move it to the '
                        'top of the module, or say why it stays, e.g. "# lazy: x imports the optimizer"):\n' + '\n'.join(silent))


def test_only_the_api_and_the_command_line_import_the_api():
    outside = []
    for name, info in MODULES.items():
        if name.startswith(f'{PACKAGE}.api') or name == f'{PACKAGE}.cli':
            continue
        for node in ast.walk(info['tree']):
            if isinstance(node, (ast.Import, ast.ImportFrom)) and any(t.startswith(f'{PACKAGE}.api') for t in targets(name, node)):
                outside.append(f'{name}:{node.lineno}')
    assert not outside, f'modules outside api/ import the API: {outside}'


def top_level_names(module):
    names = set()
    for stmt in MODULES[module]['tree'].body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]):
                names |= {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name.split('.')[0]) for a in stmt.names}
        elif isinstance(stmt, (ast.If, ast.Try)):
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    names |= {(a.asname or a.name.split('.')[0]) for a in sub.names}
    names |= {m.rpartition('.')[2] for m in MODULES if m.rpartition('.')[0] == module}   # its submodules
    return names


def test_every_name_a_test_patches_exists_where_it_is_patched():
    stale = []
    for path in sorted((ROOT / 'tests').rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith(PACKAGE):
                for a in node.names:
                    aliases[a.asname or a.name] = f'{node.module}.{a.name}'
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith(PACKAGE):
                        aliases[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'setattr'):
                continue
            if any(k.arg == 'raising' for k in node.keywords) or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.startswith(PACKAGE):
                module, _, name = first.value.rpartition('.')
            elif len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(first, (ast.Name, ast.Attribute)):
                chain, target = [], first
                while isinstance(target, ast.Attribute):
                    chain.insert(0, target.attr)
                    target = target.value
                if not isinstance(target, ast.Name) or target.id not in aliases:
                    continue
                module, name = '.'.join([aliases[target.id]] + chain), node.args[1].value
            else:
                continue
            if module in MODULES and name not in top_level_names(module):
                stale.append(f'{path.relative_to(ROOT)}:{node.lineno} patches {module}.{name}, which that module does not define')
    assert not stale, 'stale patch targets (the name moved elsewhere?):\n' + '\n'.join(stale)
