import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Redirect remembered settings / application logs for the WHOLE test process, at import time.
# A pytest_sessionstart hook is not enough: on a full-suite run this sub-directory conftest is loaded
# lazily, after the session has started, and module-scoped fixtures are set up BEFORE any
# function-scoped override - so they would write into the user's real configs/local/workbench.
# The variable is inherited by child processes (run workers, connection probes).
_settings_base = os.environ.get('GATOR_WORKBENCH_SETTINGS_DIR')
if not _settings_base:
    # A folder of this process's own, removed when the process ends: one was left in /tmp by every run and every xdist
    # worker (review round 5, E5: 810 of them). A folder passed in by the caller, or inherited from the xdist controller
    # (which made it and removes it), is not this process's to remove.
    _settings_base = tempfile.mkdtemp(prefix='gator-wb-test-settings-')
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = _settings_base

    def _remove_own_settings(path=_settings_base, pid=os.getpid()):
        if os.getpid() == pid:                                  # never from a forked child that inherited the hook
            shutil.rmtree(path, ignore_errors=True)
    atexit.register(_remove_own_settings)
# Under pytest-xdist every worker INHERITS that one folder from the controller process, and a module-scoped
# fixture (which runs before the per-test redirect below) then has several workers writing settings.json at once:
# 'Published file is not visible/complete'. Each worker gets a folder of its own inside it (review of 2026-09-23).
_worker = os.environ.get('PYTEST_XDIST_WORKER')
if _worker:
    _mine = Path(_settings_base) / _worker
    _mine.mkdir(parents=True, exist_ok=True)
    os.environ['GATOR_WORKBENCH_SETTINGS_DIR'] = str(_mine)

sys.path.insert(0, str(Path(__file__).parent))

pytest.importorskip('pyarrow', reason='the workbench raw tables need the `web`/`export` extra')
pytest.importorskip('pydantic', reason='the workbench schema needs the `web` extra')


@pytest.fixture(autouse=True)
def _single_torch_thread():
    try:
        import torch
    except ImportError:            # pure-schema tests do not need torch
        yield
        return
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Tests never touch the user's remembered settings under configs/local/workbench."""
    monkeypatch.setenv('GATOR_WORKBENCH_SETTINGS_DIR', str(tmp_path / '_settings'))
    yield


@pytest.fixture(autouse=True)
def _no_real_model_requests(tmp_path, monkeypatch):
    """CLI discovery must never turn an offline test into a real account request."""
    import subprocess
    import shutil
    original = subprocess.Popen

    def guarded(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and argv:
            executable = Path(shutil.which(str(argv[0])) or str(argv[0])).resolve()
            if executable.name in ('codex', 'claude') and not any(a in argv for a in ('--help', '--version')):
                if tmp_path.resolve() not in executable.parents:
                    raise AssertionError(f'Offline test refused a real model CLI: {executable.name}')
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', guarded)
