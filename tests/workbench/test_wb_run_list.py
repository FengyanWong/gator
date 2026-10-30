"""The list of runs behind the workbench's run window: when a run began, when it came to rest, how long it
worked, and the facts a row shows. Everything is read from the three small files a run keeps. MOCK only;
the last test starts a real detached MOCK worker."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import runs
from gator_workbench.storage import read_json
from helpers import execute, make_config, MOCK_TASK, roots_for, workbench_app

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.


def segment(number, started, ended=None, *, active=None, state=None, entry='start'):
    """Build a run-segment record with optional end time and active duration."""
    return dict(segment=number, entry=entry, requested_utc=started, started_utc=started, ended_utc=ended, end_state=state,
                active_seconds=active, load_policy=dict(notes=['not a fact of the run list']))


def test_a_run_that_finished_in_one_go():
    manifest = dict(segments=[segment(1, '2026-09-20T16:16:43+00:00', '2026-09-20T16:17:01+00:00', active=17.8, state='completed')])
    timing = runs.run_timing(manifest, dict(heartbeat_utc='2026-09-20T16:17:01.6+00:00', active_seconds=18.1))
    assert timing['started_utc'] == '2026-09-20T16:16:43+00:00' and timing['ended_utc'] == '2026-09-20T16:17:01+00:00'
    assert timing['active_seconds'] == 17.8 and timing['paused_seconds'] == 0.0      # the segment's own time, as in run_summary.json
    assert timing['segments'] == [dict(segment=1, entry='start', started_utc='2026-09-20T16:16:43+00:00',
                                       ended_utc='2026-09-20T16:17:01+00:00', end_state='completed', stop_reason=None,
                                       active_seconds=17.8)]                           # the load policy stays in the manifest


def test_a_pause_is_not_part_of_the_duration():
    manifest = dict(segments=[segment(1, '2026-09-21T10:00:00+00:00', '2026-09-21T10:10:00+00:00', active=600.0, state='paused'),
                              segment(2, '2026-09-21T12:10:00+00:00', '2026-09-21T12:15:00+00:00', active=300.0, state='completed',
                                      entry='resume')])
    timing = runs.run_timing(manifest, dict(active_seconds=905.0))
    assert timing['started_utc'] == '2026-09-21T10:00:00+00:00' and timing['ended_utc'] == '2026-09-21T12:15:00+00:00'
    assert timing['active_seconds'] == 900.0 and timing['paused_seconds'] == 7200.0


def test_a_run_that_is_still_working_has_no_end_and_the_workers_running_total():
    manifest = dict(segments=[segment(1, '2026-09-21T10:00:00+00:00', '2026-09-21T10:10:00+00:00', active=600.0, state='paused'),
                              segment(2, '2026-09-21T10:20:00+00:00', entry='resume')])
    timing = runs.run_timing(manifest, dict(heartbeat_utc='2026-09-21T10:21:00+00:00', active_seconds=660.0))
    assert timing['ended_utc'] is None and timing['last_seen_utc'] == '2026-09-21T10:21:00+00:00'
    assert timing['active_seconds'] == 660.0 and timing['paused_seconds'] == 600.0
    # Before the resumed worker has written its first status, the closed segments are what is known.
    assert runs.run_timing(manifest, {})['active_seconds'] == 600.0


def test_a_run_whose_worker_never_began_has_no_duration():
    timing = runs.run_timing(dict(segments=[dict(segment=1, entry='start', requested_utc='2026-09-21T10:00:00+00:00')]), {})
    assert timing['started_utc'] is None and timing['ended_utc'] is None and timing['active_seconds'] is None
    assert runs.run_timing({}, {})['segments'] == []


def fabricate(root, name, manifest, status):
    """Write minimal mock run-list metadata without starting a worker."""
    run = root / 'mock' / 'exp__0123456789ab' / 'runs' / 'task' / name
    run.mkdir(parents=True)
    (run / 'run_manifest.json').write_text(json.dumps(dict(dict(mock=True, experiment_name='exp', experiment_id='0123456789ab'), **manifest)))
    (run / 'status.json').write_text(json.dumps(status))
    return run


def test_a_worker_that_died_is_listed_as_interrupted_with_the_time_it_was_last_seen(tmp_path):
    fabricate(tmp_path, 'scratch__seed0__abcdef012345',
              dict(run_id='abcdef012345', created_utc='2026-09-21T10:00:00+00:00', budgets=dict(max_evaluations=60),
                   segments=[segment(1, '2026-09-21T10:00:03+00:00')]),
              dict(state='running', heartbeat_utc='2026-09-21T10:04:00+00:00', active_seconds=237.0, budget=dict(charged=31)))
    row, = runs.list_runs(roots_for(tmp_path), tmp_path)
    assert row['state'] == 'interrupted' and row['ended_utc'] is None and row['last_seen_utc'] == '2026-09-21T10:04:00+00:00'
    assert row['active_seconds'] == 237.0 and row['evaluations'] == 31 and row['max_evaluations'] == 60   # no summary was ever written


def test_a_row_names_the_registered_task_its_run_ran(tmp_path):
    """Choosing a task shows its newest run (record 7.212): the page matches a row's task_key with the task it chose. A
    Baseline simulation is a run of its task as well, although its folder is named <name>.baseline."""
    task = dict(task_key='real:mscr_ota7t', source='registered_task')
    fabricate(tmp_path, 'scratch__seed0__aaaaaaaaaaaa', dict(run_id='aaaaaaaaaaaa', created_utc='2026-10-05T17:03:29+00:00',
                                                             task_name='mscr_ota7t.baseline', circuit=task), dict(state='completed'))
    fabricate(tmp_path, 'scratch__seed0__bbbbbbbbbbbb', dict(run_id='bbbbbbbbbbbb', created_utc='2026-10-05T18:33:42+00:00',
                                                             task_name='mscr_ota7t', circuit=task), dict(state='completed'))
    fabricate(tmp_path, 'scratch__seed0__cccccccccccc', dict(run_id='cccccccccccc', created_utc='2026-09-01T00:00:00+00:00'),
              dict(state='completed'))                                    # a manifest that names no task: no task_key
    assert [(row['run_id'], row['task_key']) for row in runs.list_runs(roots_for(tmp_path), tmp_path)] == [
        ('bbbbbbbbbbbb', 'real:mscr_ota7t'), ('aaaaaaaaaaaa', 'real:mscr_ota7t'), ('cccccccccccc', None)]


@pytest.fixture(scope='module')
def finished(tmp_path_factory):
    """Provide a completed synthetic run for list and timing checks."""
    root = tmp_path_factory.mktemp('run_list')
    layout, state = execute(make_config(root, run=dict(max_evaluations=8), project=dict(task_name='listed_task')), root)
    assert state == 'completed'
    return root, layout


@pytest.mark.xdist_group('test_wb_run_list')
def test_a_real_mock_run_is_listed_with_the_times_its_manifest_holds(finished):
    root, layout = finished
    row, = runs.list_runs(roots_for(root), root)
    last = read_json(layout.manifest)['segments'][-1]
    assert row['run_dir'] == str(layout.run_dir) and row['state'] == 'completed' and row['stop_reason'] == 'budget_exhausted'
    assert row['started_utc'] == last['started_utc'] and row['ended_utc'] == last['ended_utc'] and row['ended_utc'] > row['started_utc']
    assert row['active_seconds'] == last['active_seconds'] > 0 and row['paused_seconds'] == 0.0
    assert row['task_name'] == 'listed_task' and row['evaluations'] == row['max_evaluations'] == 8 and row['error'] is None
    assert row['task_key'] == MOCK_TASK                     # the registered task, whatever the run label says
    assert [s['end_state'] for s in row['segments']] == ['completed']


@pytest.mark.xdist_group('test_wb_run_list')
def test_the_api_serves_the_same_rows(finished):
    root, layout = finished
    client = TestClient(workbench_app(root))
    row, = client.get('/api/runs', params=dict(output_root=str(root))).json()['runs']
    assert row == json.loads(json.dumps(runs.list_runs(roots_for(root), root)[0]))
    assert {'started_utc', 'ended_utc', 'last_seen_utc', 'active_seconds', 'paused_seconds', 'segments', 'task_key'} <= set(row)


def wait_for(client, run_dir, timeout=180):
    """Wait until the run reaches a resting state and its detached worker exits."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get('/api/runs/status', params=dict(run_dir=run_dir)).json()
        if status.get('state') in ('completed', 'failed', 'paused', 'stopped', 'cancelled') and not status.get('worker_alive'):
            return status
        time.sleep(0.3)
    raise AssertionError(f'run did not come to rest: {status}')


def test_a_detached_run_is_listed_while_it_works_after_a_pause_and_after_it_continued(tmp_path):
    """The three shapes of a row, from the real worker: an open segment, a pause, a second segment."""
    client = TestClient(workbench_app(tmp_path))
    listed = lambda: client.get('/api/runs', params=dict(output_root=str(tmp_path))).json()['runs'][0]
    raw = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=400, concurrency=2)).model_dump(mode='json')
    run_dir = client.post('/api/runs/start', json=dict(config=raw)).json()['run_dir']
    deadline = time.time() + 120
    while time.time() < deadline and ((client.get('/api/runs/status', params=dict(run_dir=run_dir)).json().get('budget') or {}).get('completed') or 0) < 6:
        time.sleep(0.2)
    working = listed()
    assert working['state'] == 'running' and working['ended_utc'] is None and working['started_utc'] and working['last_seen_utc']
    assert working['active_seconds'] > 0 and 6 <= working['evaluations'] < 400 and working['max_evaluations'] == 400   # no summary exists yet
    client.post('/api/runs/command', json=dict(run_dir=run_dir, command='pause'))
    done = wait_for(client, run_dir)['summary']['totals']['candidate_evaluations_charged']
    paused = listed()
    assert paused['state'] == 'paused' and paused['stop_reason'] == 'user_pause' and paused['ended_utc'] > paused['started_utc']
    assert paused['evaluations'] == done and paused['paused_seconds'] == 0.0 and [s['end_state'] for s in paused['segments']] == ['paused']
    time.sleep(1.2)                                                               # the pause that must not count as working time
    client.post('/api/runs/continue', json=dict(run_dir=run_dir, max_evaluations=done + 6))
    assert wait_for(client, run_dir)['state'] == 'completed'
    ended = listed()
    assert [(s['entry'], s['end_state']) for s in ended['segments']] == [('start', 'paused'), ('resume', 'completed')]
    assert ended['started_utc'] == paused['started_utc'] and ended['ended_utc'] > paused['ended_utc'] and ended['paused_seconds'] >= 1.2
    assert ended['active_seconds'] == pytest.approx(sum(s['active_seconds'] for s in ended['segments'])) and ended['active_seconds'] > paused['active_seconds']
    assert ended['evaluations'] == ended['max_evaluations'] == done + 6
