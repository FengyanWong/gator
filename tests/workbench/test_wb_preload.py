"""The optimizer stack is imported before the threaded backend serves anything (gator_workbench.preload).

The defect needs a FRESH interpreter: this test process has long imported torch (conftest), so the
parallel first requests run in a subprocess, exactly as a browser's first page load produces them.
"""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

from gator_workbench import preload
from helpers import make_config

REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / 'src' / 'gator_workbench'

FIRST_PAGE_LOAD = '''
import json, sys, threading, warnings
warnings.filterwarnings('ignore')
from fastapi.testclient import TestClient
from gator_workbench.api import create_app

config = json.load(open(sys.argv[1]))
app = create_app(extra_output_roots=[sys.argv[2]], serve_frontend=False, auto_check_on_start=False)
barrier, replies = threading.Barrier(2), {}

def request(name, send):
    client = TestClient(app, raise_server_exceptions=False)      # one portal per thread
    barrier.wait()
    reply = send(client)
    replies[name] = dict(status=reply.status_code, body=reply.json() if reply.status_code == 200 else reply.text)

threads = [threading.Thread(target=request, args=('meta', lambda c: c.get('/api/meta'))),
           threading.Thread(target=request, args=('validate', lambda c: c.post('/api/config/validate', json=dict(config=config))))]
[t.start() for t in threads]
[t.join() for t in threads]
later = TestClient(app, raise_server_exceptions=False).post('/api/config/validate', json=dict(config=config))
replies['later_validate'] = dict(status=later.status_code)
replies['bridge_package_imported'] = 'virtuoso_bridge' in sys.modules
print(json.dumps(replies))
'''


def lazy_imports():
    """{module: [files]} for every import statement inside a function of the workbench package."""
    found = {}
    for path in sorted(PACKAGE.rglob('*.py')):
        for function in ast.walk(ast.parse(path.read_text())):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    found.setdefault(name, []).append(path.relative_to(PACKAGE).as_posix())
    return found


def test_every_lazy_optimizer_import_is_preloaded():
    guarded = {name: files for name, files in lazy_imports().items() if name.split('.')[0] in preload.GUARDED_PACKAGES}
    assert guarded, 'the scan found no lazy import at all: it is broken, not the package clean'
    missing = {name: files for name, files in guarded.items() if name not in preload.MODULES}
    assert not missing, f'add to gator_workbench.preload.MODULES (imported lazily, so it can race in the API thread pool): {missing}'


def test_the_optional_bridge_package_is_never_preloaded():
    assert not [name for name in preload.MODULES if name.split('.')[0] == 'virtuoso_bridge']


def test_parallel_first_requests_do_not_corrupt_the_optimizer_import(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(make_config(tmp_path).model_dump(mode='json')))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(REPO / 'src'), os.environ.get('PYTHONPATH')])))
    done = subprocess.run([sys.executable, '-B', '-c', FIRST_PAGE_LOAD, str(config), str(tmp_path)],
                          capture_output=True, text=True, env=env, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    replies = json.loads(done.stdout.strip().splitlines()[-1])
    assert replies['meta']['status'] == 200, replies['meta']
    assert replies['validate']['status'] == 200, replies['validate']
    assert replies['meta']['body']['environment']['torch_geometric'] != 'unavailable'
    assert 'issues' in replies['validate']['body']
    assert replies['later_validate']['status'] == 200          # the process was not left poisoned
    assert replies['bridge_package_imported'] is False
