import os
import sys
import tempfile
from pathlib import Path

import pytest

# Redirect remembered settings / application logs for the WHOLE test process, at import time.
# A pytest_sessionstart hook is not enough: on a full-suite run this sub-directory conftest is loaded
# lazily, after the session has started, and module-scoped fixtures are set up BEFORE any
# function-scoped override - so they would write into the user's real configs/local/workbench.
# The variable is inherited by child processes (run workers, connection probes).
os.environ.setdefault('GATOR_WORKBENCH_SETTINGS_DIR', tempfile.mkdtemp(prefix='gator-wb-test-settings-'))

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
