"""A saved task as the page loads it is kept while its files are unchanged (tasks.load_task_view, review of 2026-10-01).

Loading a generated task opened ~43 files on the 9p-mounted D: drive at every edit of the page - validation, the task
load, Matched devices, the saved-model check - 0.3-1 s each time. The page's loads keep it; a run's never do."""
import json
import os
from pathlib import Path

import pytest

from gator_workbench import paths, profiles, schema, tasks
from gator_workbench.api.support import load_runtime
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from ring_cell_support import config, connection_file, read_cell

REF = schema.CircuitReference(source='registered_task', task_id='real:ring_osc_3stage')


def later(path):
    """A new modification time, whatever the clock's resolution: what a rewrite of the file does."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))


@pytest.fixture
def saved(tmp_path, monkeypatch):
    tasks._view_cache.clear()
    read_cell(tmp_path)
    made = profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    connection_file()
    loads = []
    real = tasks.load_task

    def counted(*args, **kwargs):
        loads.append(bool(kwargs.get('allow_real')))
        return real(*args, **kwargs)
    monkeypatch.setattr(tasks, 'load_task', counted)
    yield Path(made['directory']), loads
    tasks._view_cache.clear()


def test_kept_while_its_files_are_unchanged_and_read_again_after_a_change(saved):
    folder, loads = saved
    first = tasks.load_task_view(REF, profile_id='lab')
    again = tasks.load_task_view(REF, profile_id='lab')
    assert loads == [False] and again.task_key == first.task_key == 'real:ring_osc_3stage'
    assert again.provided_metrics == first.provided_metrics and again.base_graph is first.base_graph
    assert first.circuit['baseline_recorded'] is False
    # a recorded baseline lands in the task's folder: the next load sees it
    (folder / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.2e9))))
    later(folder / 'reference_measurements.json')
    recorded = tasks.load_task_view(REF, profile_id='lab')
    assert loads == [False, False] and recorded.circuit['baseline_recorded'] is True
    # a saved revision rewrites a file of the folder; the connection file changes: read again each time
    later(folder / 'design.json')
    tasks.load_task_view(REF, profile_id='lab')
    later(paths.local_settings_dir() / 'bridge_connection.json')
    tasks.load_task_view(REF, profile_id='lab')
    assert loads == [False] * 4


def test_a_caller_changes_only_its_own_copy(saved):
    mine = tasks.load_task_view(REF, profile_id='lab')
    mine.circuit['generated_profile'] = 'changed by a caller'
    mine.notes.append('a note of a caller')
    theirs = tasks.load_task_view(REF, profile_id='lab')
    assert theirs.circuit['generated_profile'] is True and 'a note of a caller' not in theirs.notes


def test_the_link_is_checked_at_every_call(saved, monkeypatch):
    tasks.load_task_view(REF, profile_id='lab')
    monkeypatch.setattr(tasks, 'generated_backend_blocker', lambda profile_id=None: 'FIXTURE: the link is gone')
    with pytest.raises(tasks.TaskBlocked, match='FIXTURE: the link is gone'):
        tasks.load_task_view(REF, profile_id='lab')


def test_a_deleted_task_is_not_shown_from_memory(saved):
    folder, loads = saved
    tasks.load_task_view(REF, profile_id='lab')
    profiles.delete_profile('ring_osc_3stage')
    with pytest.raises(tasks.TaskBlocked):
        tasks.load_task_view(REF, profile_id='lab')


def test_the_pages_loads_are_kept_and_a_runs_never(saved):
    folder, loads = saved
    shell = schema.WorkbenchConfig.model_validate(dict(circuit=REF.model_dump(), run=dict(max_evaluations=1, connection_profile_id='lab')))
    for _ in range(2):
        runtime, blocked = load_runtime(shell)
        assert blocked is None and runtime.authorized is False
    for _ in range(2):
        load_runtime(shell, allow_real=True)
    assert loads == [False, True, True]


def test_other_tasks_load_as_before(monkeypatch):
    """Only a task saved from a cell is kept: any other reference - MOCK, ngspice, a built-in profile, a Virtuoso draft -
    goes to load_task at every call (whichever of them the registry still has)."""
    calls = []
    tasks._view_cache.clear()        # an earlier test in this process may have kept a saved task (test_wb_profiles does)
    monkeypatch.setattr(tasks, 'load_task', lambda circuit, **kwargs: calls.append(circuit.task_id) or circuit.task_id)
    keys = ['synthetic:gpdk045_ota5', 'ngspice:ota5_level1', f'real:{next(iter(tasks.REAL_PROFILES))}']
    for key in keys:
        ref = schema.CircuitReference(source='registered_task', task_id=key)
        assert tasks.load_task_view(ref) == tasks.load_task_view(ref) == key
    draft = schema.CircuitReference(source='virtuoso', library='L', cell='C')
    tasks.load_task_view(draft)
    assert calls == [key for key in keys for _ in range(2)] + [None] and not tasks._view_cache


def test_the_repository_is_resolved_once():
    assert paths.repo_root() is paths.repo_root() and (paths.repo_root() / 'src' / 'gator_workbench').is_dir()
