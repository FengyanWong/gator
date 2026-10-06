"""Follow-up of review round 5 (2026-10-01): the backend's stop waits a bounded time, the ngspice deck is published
whole, and a run paused for infrastructure failures can be resumed. (The round's agent parts - CLIs stopping with the
backend, a proposal applied once, the tool relay - went with the Agent tab's own agent on 2026-10-06, record 7.226.)"""
from pathlib import Path
import time

import pytest

from gator_workbench import cli as workbench_cli, ngspice_tasks, runs
from helpers import execute, make_config, roots_for, rows, run_prepared, summary


# ------------------------------------------------------------------------------- a stop never waits for ever
@pytest.mark.parametrize('ending', ['returns', 'raises'])
def test_serve_bounds_its_wait_for_open_requests_however_it_ends(monkeypatch, ending):
    import uvicorn
    import gator_workbench.api
    seen = {}

    def run(app, **options):
        seen.update(options)
        if ending == 'raises':
            raise KeyboardInterrupt
    monkeypatch.setattr(uvicorn, 'run', run)
    monkeypatch.setattr(gator_workbench.api, 'create_app', lambda **options: object())
    if ending == 'raises':
        with pytest.raises(KeyboardInterrupt):
            workbench_cli.main(['serve', '--port', '1'])
    else:
        assert workbench_cli.main(['serve', '--port', '1']) == 0
    assert seen['timeout_graceful_shutdown'] == workbench_cli.SHUTDOWN_GRACE_SECONDS


# ------------------------------------------------------------------------------- the ngspice deck is published whole
DECK = '* a divider\nv1 in 0 dc 1\nr1 in out 1k\nr2 out 0 2k\n.op\n.end\n'


def test_a_failed_save_leaves_the_deck_before_it_whole(monkeypatch):
    ngspice_tasks.save('divider', DECK)
    deck = ngspice_tasks.task_dir('divider') / ngspice_tasks.FILES['netlist']
    write = Path.write_text

    def half_then_fail(self, text, *args, **kwargs):            # the disk fills up half way through the new deck
        write(self, text[:len(text) // 2], *args, **kwargs)
        raise OSError(28, 'No space left on device')
    with monkeypatch.context() as patched, pytest.raises(OSError):
        patched.setattr(Path, 'write_text', half_then_fail)
        ngspice_tasks.save('divider', DECK.replace('2k', '3k'))
    assert deck.read_text() == DECK                               # it was the half-written new deck before
    assert ngspice_tasks.list_tasks()['divider']['revision'] == 1


# ------------------------------------------------------------------------------- pauses for infrastructure failures
def infrastructure_pause(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2,
                                                           max_consecutive_infrastructure_failures=3,
                                                           max_consecutive_failures=50))
    script = {n: 'timeout' for n in range(3, 40)}
    layout, state = execute(config, tmp_path, scripts={'0': script, '1': script})
    assert state == 'paused' and summary(layout)['stop_reason'] == 'infrastructure_failures'
    return config, layout


def test_a_run_paused_for_infrastructure_failures_continues_when_resumed(tmp_path):
    config, layout = infrastructure_pause(tmp_path)
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))
    assert run_prepared(again) == 'completed'                     # the link works again; it paused again at once before
    final = summary(layout)
    assert final['stop_reason'] == 'budget_exhausted' and final['totals']['candidate_evaluations_charged'] == 40


def test_a_candidate_a_pause_stops_before_its_launch_is_cancelled_not_a_failure_of_the_link(tmp_path, monkeypatch):
    from analog_optimizer.envs.sizing import CircuitSizingEnv
    layout, _ = runs.prepare_run(make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2)),
                                 roots_for(tmp_path))
    authorize, calls = CircuitSizingEnv.authorize_launches, {}

    def pause_on_the_way(env, allowance, *, stop_file=None):
        authorize(env, allowance, stop_file=stop_file)
        calls[id(env)] = calls.get(id(env), 0) + (allowance > 0)
        if calls[id(env)] == 3 and 'paused' not in calls:       # Pause is pressed while this candidate is on its way
            calls['paused'] = True
            runs.send_command(layout.run_dir, 'pause')
            deadline = time.monotonic() + 30
            while not Path(stop_file).exists() and time.monotonic() < deadline:
                time.sleep(0.005)
    monkeypatch.setattr(CircuitSizingEnv, 'authorize_launches', pause_on_the_way)
    assert run_prepared(layout) == 'paused' and summary(layout)['stop_reason'] == 'user_pause'
    evaluations = rows(layout, 'evaluations')
    stopped = [e for e in evaluations if e['status'] == 'cancelled']
    assert len(stopped) == 1 and stopped[0]['failure_type'] == 'cancelled'
    assert 'stopped before nominal evaluation' in stopped[0]['diagnostics']
    assert not [e for e in evaluations if e['failure_type'] and e['failure_type'].startswith('infrastructure')]


def test_a_resume_that_fails_writing_its_check_gives_the_run_lock_back(tmp_path, monkeypatch):
    config, layout = infrastructure_pause(tmp_path)
    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    monkeypatch.setattr(runs, '_check_consistency', lambda *args: dict(ok=True))     # a saved task's check, written down
    write = runs.write_json

    def full_disk(path, value, **options):
        if Path(path) == layout.manifest and value['segments'][-1].get('consistency_check'):
            raise OSError(28, 'No space left on device')
        return write(path, value, **options)
    with monkeypatch.context() as patched, pytest.raises(OSError):
        patched.setattr(runs, 'write_json', full_disk)
        runs.prepare_run(resumed, roots_for(tmp_path))
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))      # refused as "already running" until a restart before
    runs.take_lock(again.run_dir).release()
