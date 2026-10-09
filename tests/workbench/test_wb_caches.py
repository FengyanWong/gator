"""Every cache a workbench process keeps for its lifetime joins caches.py, and clear_all empties them all (refactoring
package B10, docs/plan-refactoring.md). A new module-level cache - a dict or OrderedDict made empty at the top of a
module, or a function under lru_cache - that neither registers nor is named below as no cache fails the first test."""
import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

from gator_workbench import caches

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'src' / 'gator_workbench'
NOT_CACHES = {
    'runs._HELD_LOCKS': 'a lock a start hands to its worker',
    'corner_check._STARTING': 'a lock a start hands to its worker',
    'ocean._CLIENTS': 'open OCEAN clients: emptying the dict would leave them open',
    'task_saving._took': "Save task's timing record",
    'paths.repo_root': 'the repository folder never changes',
    'units.LOOKUP': 'the unit table, filled once when the module is imported',
    'caches._CLEARS': 'the registry itself',
}
EMPTY = ('{}', 'dict()', 'OrderedDict()', 'collections.OrderedDict()')


def module_caches() -> set:
    found = set()
    for path in SRC.rglob('*.py'):
        module = '.'.join(path.relative_to(SRC).with_suffix('').parts)
        for stmt in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and stmt.value is not None and ast.unparse(stmt.value) in EMPTY:
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                found |= {f'{module}.{t.id}' for t in targets if isinstance(t, ast.Name)}
            elif isinstance(stmt, ast.FunctionDef) and any('lru_cache' in ast.unparse(d) for d in stmt.decorator_list):
                found.add(f'{module}.{stmt.name}')
    return found


def test_every_module_level_cache_registers_or_is_named_as_no_cache():
    found = module_caches()
    for name in found:
        importlib.import_module('gator_workbench.' + name.rpartition('.')[0])
    assert not sorted(found - set(caches.names()) - set(NOT_CACHES)), 'caches that do not join caches.py'
    assert not sorted(set(caches.names()) - found), 'registered names that are no module-level cache'
    assert set(NOT_CACHES) <= found | {'paths.repo_root'}


def test_clear_all_empties_every_registered_cache_in_a_fresh_process():
    # its own interpreter: emptying the caches of this one would change what later tests on this worker find in them
    script = '''
import importlib, sys
from gator_workbench import caches
modules = sys.argv[1:]
for m in modules:
    importlib.import_module('gator_workbench.' + m)
cached = {}
for name in caches.names():
    module, _, attr = name.rpartition('.')
    cache = getattr(importlib.import_module('gator_workbench.' + module), attr)
    if isinstance(cache, dict):
        cache['test sentinel'] = None
    cached[name] = cache
caches.clear_all()
left = [n for n, c in cached.items() if (len(c) if isinstance(c, dict) else c.cache_info().currsize)]
print(len(cached), left)
'''
    modules = sorted({name.rpartition('.')[0] for name in module_caches()})
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), OMP_NUM_THREADS='1')
    done = subprocess.run([sys.executable, '-c', script, *modules], capture_output=True, text=True, env=env, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    count, left = done.stdout.split(' ', 1)
    assert int(count) == len(caches.names()) >= 17 and left.strip() == '[]'
