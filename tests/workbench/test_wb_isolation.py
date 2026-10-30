"""The test suite must never touch a user's real workbench settings, at ANY fixture scope."""
from pathlib import Path

import pytest

from gator_workbench import paths, runs

REAL = paths.repo_root() / 'configs' / 'local' / 'workbench'


@pytest.fixture(scope='module')
def settings_dir_at_module_scope():
    """Module-scoped fixtures run before function-scoped overrides: exactly where a leak happened once."""
    return paths.local_settings_dir()


def test_settings_are_redirected_at_every_scope(settings_dir_at_module_scope, tmp_path):
    for seen in (settings_dir_at_module_scope, paths.local_settings_dir()):
        assert seen != REAL and REAL not in Path(seen).parents, f'tests would write real settings: {seen}'
    before = {p.name: p.stat().st_mtime_ns for p in REAL.iterdir()} if REAL.is_dir() else {}
    runs.save_settings(output_root=str(tmp_path), probe='isolation-test')
    after = {p.name: p.stat().st_mtime_ns for p in REAL.iterdir()} if REAL.is_dir() else {}
    assert before == after                                  # the real directory was not touched
    assert runs.load_settings()['probe'] == 'isolation-test'
