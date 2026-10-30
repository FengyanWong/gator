"""The guards in front of a real run: an unauthorized real start creates nothing, and a worker started without
--allow-real never reaches the engine. Local files only; nothing here contacts a bridge or starts a simulation. The tests
of the built-in circuits' connection bindings (receipt and baseline per circuit) left on 2026-09-30 with the last of
those tasks, OTA7 and LDO (record 7.128)."""
from pathlib import Path

import pytest

from gator_workbench import tasks

REPO = Path(__file__).resolve().parents[2]


def test_an_unauthorized_real_start_is_refused_before_anything_exists(tmp_path, monkeypatch):
    from gator_workbench import runs
    from helpers import make_config, roots_for
    config = make_config(tmp_path, run=dict(max_evaluations=6, connection_profile_id='lab'))
    runtime = tasks.load_task(config.circuit)
    runtime.origin = 'real'                                                 # a MOCK-evaluated task relabelled as real
    monkeypatch.setattr(runs, 'load_task', lambda circuit, allow_real=False, profile_id=None: runtime)
    before = sorted(path.name for path in tmp_path.iterdir())
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(config, roots_for(tmp_path), allow_real=False, monitor=None)
    assert refused.value.code == 'real_authorization_required' and 'explicit user action' in str(refused.value)
    assert refused.value.report['requested_max_evaluations'] == 6
    assert sorted(path.name for path in tmp_path.iterdir()) == before       # no run directory, no experiment, no gate probe
    assert runs.list_runs(roots_for(tmp_path), tmp_path) == []


def test_the_worker_refuses_a_real_run_that_was_not_authorized(tmp_path):
    """Third line of defence: a worker launched without --allow-real never reaches the engine."""
    source = (REPO / 'src/gator_workbench/worker.py').read_text()
    guard = source.index('if not task.mock and not args.allow_real')
    assert guard < source.index("if task.mock != manifest['mock']")          # checked right after loading, before any work
    assert 'profile_id=config.run.connection_profile_id' in source          # the gated profile, never silently the active one
