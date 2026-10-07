"""One launcher, the backend half (record 7.261; plan docs/plan-frontend-run-workflow.md, "One launcher" and "Existing
runs: continued in place"). The continuation check answers BEFORE the press what Continue would do - the press's own
refusals in its words, the numbers of the budget form and the new run that still goes on from the model - and writes
nothing. A launch request id is answered once: the same id again gets the run the first request made, never a second
one; a refused request leaves no record. MOCK runs in-process; no worker process is started."""
import json
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import launch_requests, runs
from gator_workbench.engine import RunLock
from gator_workbench.storage.atomic import PersistenceError, write_json
from helpers import execute, make_config, workbench_app

FINE_TUNE = 'Fine-tune from its newest save point (a new run)'


@pytest.fixture
def finished(tmp_path):
    """A MOCK run of 6 evaluations that has completed, with its final full save point."""
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=6)), tmp_path)
    assert runs.run_status(layout.run_dir)['state'] == 'completed'
    return layout.run_dir


@pytest.fixture
def no_worker(monkeypatch):
    """Starts and continues are prepared as ever, but no worker process is launched: the run lock a continue takes
    for its worker is let go of here."""
    launched = []

    def launch(layout, allow_real=False):
        held = runs.take_lock(layout.run_dir)
        if held:
            held.release()
        launched.append(str(layout.run_dir))
        return 4242
    monkeypatch.setattr(runs, 'launch_worker', launch)
    return launched


def files_of(folder):
    return {str(p.relative_to(folder)): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob('*') if p.is_file()}


def manifest_of(run_dir):
    return json.loads((run_dir / 'run_manifest.json').read_text())


# ------------------------------------------------------------------------------------------- the continuation check
def test_a_completed_run_goes_on_once_its_total_is_raised_and_the_check_writes_nothing(finished):
    before = files_of(finished)
    kept = runs.continuation(finished)
    assert kept['eligible'] and kept['code'] is None and kept['alternative'] is None and kept['state'] == 'completed'
    assert (kept['used'], kept['total'], kept['remaining'], kept['minimum_total'], kept['exhausted']) == (6, 6, 0, 7, True)
    raised = runs.continuation(finished, max_evaluations=10)
    assert raised['eligible'] and raised['remaining'] == 4 and raised['save_point'] == kept['save_point'] and kept['save_point'].startswith('ckpt-')
    assert files_of(finished) == before                          # read-only: no file written, none touched
    assert not RunLock.held(finished / 'control' / 'run.lock')   # and no run lock left behind


def test_a_changed_task_is_said_before_the_press_with_the_fine_tune_instead(finished):
    manifest = manifest_of(finished)
    manifest['task_definition_hash'] = 'f' * 64                  # the task was saved again since the run
    (finished / 'run_manifest.json').write_text(json.dumps(manifest))
    answer = runs.continuation(finished, max_evaluations=10)
    assert not answer['eligible'] and answer['code'] == 'task_changed' and 'task definition changed' in answer['reason']
    assert answer['alternative'] == dict(action='fine_tune', run_dir=str(finished), checkpoint_id=answer['save_point'], label=FINE_TUNE)


def test_no_save_point_means_no_continue_and_nothing_to_fine_tune_from(finished):
    shutil.rmtree(finished / 'checkpoints')
    answer = runs.continuation(finished, max_evaluations=10)
    assert answer['code'] == 'no_checkpoint' and answer['save_point'] is None and answer['alternative'] is None
    assert 'no save point' in answer['reason']


def test_a_save_point_of_older_optimizer_code_continues_only_as_a_new_run(finished, monkeypatch):
    monkeypatch.setattr(runs, 'current_source_digest', lambda max_age=30.0: 'another-version-of-the-code')
    answer = runs.continuation(finished, max_evaluations=10)
    assert answer['code'] == 'older_code' and 'older version of the optimizer code' in answer['reason']
    assert answer['alternative']['action'] == 'fine_tune' and answer['alternative']['checkpoint_id'] == answer['save_point']


def test_a_running_run_is_never_continued_twice(finished):
    lock = RunLock(finished / 'control' / 'run.lock')
    lock.acquire()
    try:
        answer = runs.continuation(finished, max_evaluations=10)
    finally:
        lock.release()
    assert answer['code'] == 'already_running' and not answer['eligible'] and answer['alternative'] is None


def test_the_route_answers_as_the_check_and_refuses_what_is_no_run(finished, tmp_path):
    client = TestClient(workbench_app(tmp_path))
    answer = client.get('/api/runs/continuation', params=dict(run_dir=str(finished), max_evaluations=9)).json()
    assert answer['eligible'] and answer['remaining'] == 3 and answer['run_dir'] == str(finished)
    assert client.get('/api/runs/continuation', params=dict(run_dir=str(tmp_path))).status_code == 404
    assert client.get('/api/runs/continuation', params=dict(run_dir='/etc')).status_code == 403
    assert client.get('/api/runs/continuation', params=dict(run_dir=str(finished), max_evaluations=0)).status_code == 422
    assert {'launch_requests', 'continuation_check'} <= set(client.get('/api/meta').json()['features'])


# ------------------------------------------------------------------------------------------------ launch request ids
def test_a_start_sent_twice_makes_one_run(tmp_path, no_worker):
    client = TestClient(workbench_app(tmp_path))
    raw = make_config(tmp_path).model_dump(mode='json')
    first = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0001')).json()
    again = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0001')).json()
    assert again['run_dir'] == first['run_dir'] and again['repeated'] is True and 'repeated' not in first
    assert no_worker == [first['run_dir']] and len(list(tmp_path.rglob('run_manifest.json'))) == 1
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0001')).json() == dict(state='done', answer=first)
    other = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0002')).json()
    assert other['run_dir'] != first['run_dir'] and len(no_worker) == 2      # another id is another launch
    plain = client.post('/api/runs/start', json=dict(config=raw)).json()     # an older page sends none: as before
    assert plain['run_dir'] not in (first['run_dir'], other['run_dir']) and len(no_worker) == 3


def test_a_refused_start_leaves_no_record_so_its_repeat_goes_ahead(tmp_path, no_worker):
    client = TestClient(workbench_app(tmp_path))
    raw = make_config(tmp_path).model_dump(mode='json')
    refused = client.post('/api/runs/start', json=dict(config=raw, calibration_only=True, request_id='page-start-0003'))
    assert refused.status_code == 400 and not no_worker
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0003')).json() == dict(state='unknown')
    made = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0003'))
    assert made.status_code == 200 and no_worker == [made.json()['run_dir']]


def test_a_request_on_its_way_is_not_carried_out_a_second_time(tmp_path, no_worker):
    client = TestClient(workbench_app(tmp_path))
    assert launch_requests.claim('page-start-0004', 'start') is None         # the first one is on its way
    raw = make_config(tmp_path).model_dump(mode='json')
    again = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0004'))
    assert again.status_code == 409 and again.json()['detail']['code'] == 'request_pending' and not no_worker
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0004')).json() == dict(state='pending')
    assert client.get('/api/runs/request', params=dict(request_id='no')).status_code == 422          # not an id


def test_a_request_whose_backend_went_away_is_new_again():
    assert launch_requests.claim('page-start-0005', 'start') is None
    old = time.time() - launch_requests.STALE_PENDING_SECONDS - 5
    os.utime(launch_requests._path('page-start-0005'), (old, old))
    assert launch_requests.lookup('page-start-0005') == dict(state='unknown')
    assert launch_requests.claim('page-start-0005', 'start') is None
    with pytest.raises(ValueError):
        launch_requests.claim('../escape', 'start')


def test_the_answer_is_on_disk_before_the_worker_starts_and_survives_a_lost_acknowledgement(tmp_path, monkeypatch):
    """Review of 2026-10-07: the record used to be written after the worker was spawned. A write that failed then left
    the request pending, "unknown" a quarter of an hour later, and the same id made a second run."""
    seen = []

    def launch(layout, allow_real=False):                               # a worker that starts: it writes its status
        seen.append(launch_requests.lookup('page-start-0006'))          # what the page would learn at this moment
        held = runs.take_lock(layout.run_dir)
        if held:
            held.release()
        write_json(layout.status, dict(state='starting', run_dir=str(layout.run_dir)))
        return 4242
    monkeypatch.setattr(runs, 'launch_worker', launch)

    def losing_answer(request_id, result):                               # the acknowledgement after the spawn is lost
        raise PersistenceError('the drive did not take the record')
    monkeypatch.setattr(launch_requests, 'answer', losing_answer)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    raw = make_config(tmp_path).model_dump(mode='json')
    first = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0006'))
    assert first.status_code == 500 and len(seen) == 1
    assert seen[0] == dict(state='pending')                             # on disk, launching, before the worker existed
    run_dir = str(next(tmp_path.rglob('run_manifest.json')).parent)
    known = client.get('/api/runs/request', params=dict(request_id='page-start-0006')).json()
    assert known['state'] == 'done' and known['answer']['run_dir'] == run_dir      # the page finds the run it made
    assert known['answer']['worker_pid'] is None
    monkeypatch.setattr(launch_requests, 'answer', lambda request_id, result: launch_requests.prepared(request_id, result))
    again = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0006')).json()
    assert again['run_dir'] == run_dir and again['repeated'] is True and len(seen) == 1     # no second run
    assert len(list(tmp_path.rglob('run_manifest.json'))) == 1


def test_a_failed_record_write_lets_go_of_the_continue_lock(finished, tmp_path, no_worker, monkeypatch):
    """Astra's follow-up of 2026-10-07, 1: the lock prepare_run takes for a continue's worker stayed held when the record
    write failed, and every later continue was refused as already_running until the backend restarted."""
    real_prepared = launch_requests.prepared

    def failing(request_id, result):
        raise PersistenceError('the drive did not take the record')
    monkeypatch.setattr(launch_requests, 'prepared', failing)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    body = dict(run_dir=str(finished), max_evaluations=9, request_id='page-continue-0002')
    assert client.post('/api/runs/continue', json=body).status_code == 500 and no_worker == []
    assert client.get('/api/runs/request', params=dict(request_id='page-continue-0002')).json() == dict(state='unknown')
    monkeypatch.setattr(launch_requests, 'prepared', real_prepared)
    retry = client.post('/api/runs/continue', json=dict(body, request_id='page-continue-0003'))
    assert retry.status_code == 200 and no_worker == [str(finished)]


def test_a_launching_record_is_the_run_once_its_worker_is_there_and_nothing_once_stale(tmp_path, no_worker, monkeypatch):
    """Astra's follow-up of 2026-10-07, 2: a record written as "done" before the spawn answered the repeat with a run that
    never started when the backend died in between. Now it is "launching": pending while young, the run once its worker
    shows (lock or status), unknown - and the id new again - once stale."""
    from gator_workbench.layout import RunLayout
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    raw = make_config(tmp_path).model_dump(mode='json')
    first = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0009')).json()
    run_dir = first['run_dir']
    # As a backend that died between the record and the spawn leaves it: launching, no worker, the run still `created`.
    launch_requests.prepared('page-start-0009', dict(first, worker_pid=None))
    assert runs.run_status(run_dir)['state'] == 'created'                 # prepare_run's own status, older than the record
    assert not runs.worker_started(run_dir, since=time.time())
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0009')).json() == dict(state='pending')
    again = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0009'))
    assert again.status_code == 409 and again.json()['detail']['code'] == 'request_pending' and no_worker == [run_dir]
    old = time.time() - launch_requests.STALE_PENDING_SECONDS - 5
    os.utime(launch_requests._path('page-start-0009'), (old, old))
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0009')).json() == dict(state='unknown')
    assert not launch_requests._path('page-start-0009').exists()
    anew = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0009')).json()
    assert anew['run_dir'] != run_dir and 'repeated' not in anew and len(no_worker) == 2    # a run of its own; the created one stays
    assert runs.run_status(run_dir)['state'] == 'created'
    # The worker there (its status written): the launching record is the answer, and a repeat gets that run.
    launch_requests.prepared('page-start-0010', dict(first, worker_pid=None))
    write_json(RunLayout(run_dir).status, dict(state='starting', run_dir=run_dir))
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0010')).json() == dict(state='done', answer=dict(first, worker_pid=None))
    repeat = client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0010')).json()
    assert repeat['run_dir'] == run_dir and repeat['repeated'] is True and len(no_worker) == 2


def test_a_spawn_that_fails_leaves_no_record(tmp_path, monkeypatch):
    def launch(layout, allow_real=False):
        raise OSError('no more processes')
    monkeypatch.setattr(runs, 'launch_worker', launch)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    raw = make_config(tmp_path).model_dump(mode='json')
    assert client.post('/api/runs/start', json=dict(config=raw, request_id='page-start-0007')).status_code == 500
    assert client.get('/api/runs/request', params=dict(request_id='page-start-0007')).json() == dict(state='unknown')


def test_a_record_not_written_yet_counts_as_on_its_way():
    path = launch_requests._path('page-start-0008')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()                                                     # claim() has created it and not written it yet
    assert launch_requests.lookup('page-start-0008') == dict(state='pending')
    with pytest.raises(launch_requests.RequestPending):
        launch_requests.claim('page-start-0008', 'start')


def test_a_continue_sent_twice_continues_once(finished, tmp_path, no_worker):
    client = TestClient(workbench_app(tmp_path))
    body = dict(run_dir=str(finished), max_evaluations=9, request_id='page-continue-0001')
    first = client.post('/api/runs/continue', json=body).json()
    again = client.post('/api/runs/continue', json=body).json()
    assert first['run_dir'] == again['run_dir'] == str(finished) and again['repeated'] is True
    manifest = manifest_of(finished)
    assert len(manifest['segments']) == 2 and manifest['budgets']['max_evaluations'] == 9 and no_worker == [str(finished)]
