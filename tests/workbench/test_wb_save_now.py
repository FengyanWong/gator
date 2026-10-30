""""Save now" = run command `checkpoint`: the RUNNING worker writes a save point at its next safe boundary and
goes on. Refused, with the reason, when nothing would come of it; never replaces a pending pause/stop/cancel;
a save point made on request is never pruned. MOCK backend only."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, runs
from gator_workbench.engine import RunLock
from gator_workbench.storage import read_json, read_jsonl
from helpers import execute, make_config, roots_for, run_prepared, summary, workbench_app
import json


def send_after(layout, commands, evaluations, timeout=60):
    """Send `commands` one after the other as soon as `evaluations` evaluations have completed. Returns the list
    that receives each command record (or the exception it raised)."""
    sent = []

    def watch():
        """Send the requested commands once the run records enough completed evaluations."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = read_json(layout.status, default={}) or {}
            if ((status.get('budget') or {}).get('completed') or 0) >= evaluations:
                for command in commands:
                    try:
                        sent.append(runs.send_command(layout.run_dir, command))
                    except Exception as exc:                     # noqa: BLE001 - the test looks at it
                        sent.append(exc)
                return
            time.sleep(0.005)
    threading.Thread(target=watch, daemon=True).start()
    return sent


def save_points(layout):
    """Return the run's listed save-point metadata."""
    return ckpt.list_checkpoints(layout.run_dir)['checkpoints']


def test_save_now_writes_a_full_save_point_and_the_run_goes_on(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=30, concurrency=2))   # no periodic saves
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    sent = send_after(layout, ['checkpoint'], 8)
    assert run_prepared(layout, delays={'0': 0.03, '1': 0.03}) == 'completed'                   # not paused, not stopped
    assert summary(layout)['totals']['candidate_evaluations_charged'] == 30                     # the run went on to its end
    assert len(sent) == 1 and sent[0]['command'] == 'checkpoint'
    points = save_points(layout)
    assert [p['kind'] for p in points] == ['manual', 'final']
    manual = points[0]
    assert 8 <= manual['evaluations'] < 30 and manual['restoration_capability'] == 'full_state'
    directory = ckpt.resolve_checkpoint(layout.run_dir, manual['checkpoint_id'])
    meta = ckpt.read_metadata(directory)
    # The same consistency boundary as every other save (the ledger refuses to be saved with anything in flight):
    # ledger = data cursor = counters.
    assert meta['ledger']['charged'] == meta['data_cursor']['commit_seq'] == manual['evaluations']
    assert ckpt.verify_files(directory) == []
    answer = read_json(layout.status)['manual_save']
    assert answer['id'] == sent[0]['id'] and answer['state'] == 'saved'
    assert answer['checkpoint_id'] == manual['checkpoint_id'] and answer['evaluations'] == manual['evaluations']
    events = read_jsonl(layout.logs / 'events.jsonl')
    assert any(e.get('event') == 'control' and e.get('command') == 'checkpoint' for e in events)
    assert any(e.get('event') == 'checkpoint_saved' and e.get('kind') == 'manual' for e in events)


def test_a_save_point_made_on_request_is_never_pruned(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=24, concurrency=1),
                         output=dict(checkpoint_every_evaluations=5, keep_last_checkpoints=1))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    send_after(layout, ['checkpoint'], 7)
    assert run_prepared(layout, delays={'0': 0.02}) == 'completed'
    kinds = [p['kind'] for p in save_points(layout)]
    assert kinds.count('manual') == 1 and kinds[-1] == 'final'                                  # periodic ones were pruned
    assert kinds.count('periodic') <= 1


def test_a_pause_right_after_save_now_still_pauses_and_answers_the_request(tmp_path):
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=40, concurrency=2))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    sent = send_after(layout, ['checkpoint', 'pause'], 8)
    assert run_prepared(layout, delays={'0': 0.03, '1': 0.03}) == 'paused'                      # the pause was not lost
    assert [s['command'] for s in sent] == ['checkpoint', 'pause']
    points = save_points(layout)
    assert points[-1]['kind'] == 'pause' and points[-1]['is_latest']
    answer = read_json(layout.status).get('manual_save')
    if answer is not None:          # the worker had already read the request: the pause's save answers it
        assert answer['state'] == 'saved' and answer['checkpoint_id'] in [p['checkpoint_id'] for p in points]


def test_save_now_is_refused_with_the_reason_when_nothing_would_come_of_it(tmp_path, monkeypatch):
    finished, _ = execute(make_config(tmp_path, run=dict(max_evaluations=6), project=dict(task_name='finished')), tmp_path)
    with pytest.raises(runs.RunRejected) as refused:
        runs.send_command(finished.run_dir, 'checkpoint')
    assert refused.value.code == 'not_running' and 'saved when it finished' in str(refused.value)
    assert not (finished.control / 'command.json').exists() or read_json(finished.control / 'command.json')['command'] != 'checkpoint'

    # From here on the worker "is alive" (no process is started: only the lock probe is replaced).
    monkeypatch.setattr(RunLock, 'held', classmethod(lambda cls, path: True))
    off, _ = runs.prepare_run(make_config(tmp_path, project=dict(task_name='off'), output=dict(save_checkpoints=False)), roots_for(tmp_path))
    with pytest.raises(runs.RunRejected) as refused:
        runs.send_command(off.run_dir, 'checkpoint')
    assert refused.value.code == 'checkpoints_off' and 'Model checkpoints' in str(refused.value)

    live, _ = runs.prepare_run(make_config(tmp_path, project=dict(task_name='live')), roots_for(tmp_path))
    first = runs.send_command(live.run_dir, 'checkpoint')
    second = runs.send_command(live.run_dir, 'checkpoint')                                      # asking twice is harmless
    assert read_json(live.control / 'command.json')['id'] == second['id'] != first['id']
    for going_down in ('pause', 'stop', 'cancel'):
        record = runs.send_command(live.run_dir, going_down)
        with pytest.raises(runs.RunRejected) as refused:
            runs.send_command(live.run_dir, 'checkpoint')
        assert refused.value.code == 'already_stopping'
        assert read_json(live.control / 'command.json')['id'] == record['id']                  # the pause/stop/cancel stays in place


def test_save_now_over_http_with_a_real_detached_worker(tmp_path):
    """The whole path of the button: API -> control file -> detached worker process -> status.json -> model list."""
    client = TestClient(workbench_app(tmp_path))
    raw = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=2000, concurrency=2)).model_dump(mode='json')
    run_dir = client.post('/api/runs/start', json=dict(config=raw)).json()['run_dir']

    def status():
        """Read the detached fixture worker's current status through the API."""
        return client.get('/api/runs/status', params=dict(run_dir=run_dir)).json()

    def wait(test, seconds=120):
        """Poll API status until the supplied condition holds or the timeout fails."""
        deadline = time.time() + seconds
        while time.time() < deadline:
            now = status()
            if test(now):
                return now
            time.sleep(0.1)
        raise AssertionError(f'not reached: {now}')
    try:
        wait(lambda s: s.get('state') == 'running' and ((s.get('budget') or {}).get('completed') or 0) >= 6)
        record = client.post('/api/runs/command', json=dict(run_dir=run_dir, command='checkpoint'))
        assert record.status_code == 200 and record.json()['command'] == 'checkpoint'
        saved = wait(lambda s: (s.get('manual_save') or {}).get('id') == record.json()['id'] and s['manual_save']['state'] == 'saved')
        assert saved['worker_alive'] and saved['state'] == 'running'                           # saved, and still running
        at = saved['manual_save']['evaluations']
        wait(lambda s: s['budget']['completed'] > at + 4)                                        # ... and it goes on evaluating
        models = client.get('/api/runs/models', params=dict(output_root=str(tmp_path))).json()['models']
        points = next(m for m in models if m['run_dir'] == run_dir)['checkpoints']
        assert [(p['kind'], p['checkpoint_id']) for p in points] == [('manual', saved['manual_save']['checkpoint_id'])]
    finally:
        client.post('/api/runs/command', json=dict(run_dir=run_dir, command='stop'))
        wait(lambda s: not s.get('worker_alive'))
    assert [p['kind'] for p in ckpt.list_checkpoints(run_dir)['checkpoints']] == ['manual', 'stop']


def test_the_api_accepts_the_command_and_answers_a_refusal_in_plain_words(tmp_path):
    finished, _ = execute(make_config(tmp_path, run=dict(max_evaluations=6)), tmp_path)
    client = TestClient(workbench_app(tmp_path))
    response = client.post('/api/runs/command', json=dict(run_dir=str(finished.run_dir), command='checkpoint'))
    assert response.status_code == 409
    detail = response.json()['detail']
    assert detail['code'] == 'not_running' and detail['message'].startswith('This run is not running')
    assert client.post('/api/runs/command', json=dict(run_dir=str(finished.run_dir), command='save')).status_code == 422


def _checkpoints(layout):
    """Read saved evaluation counts, kinds and relabelling origins in save-point order."""
    found = [read_json(p / 'metadata.json') for p in sorted((layout.run_dir / 'checkpoints').glob('ckpt-*'))]
    return [(m['counters']['evaluations_committed'], m['kind'], m.get('relabelled_from')) for m in found]


def test_a_run_that_completes_right_after_a_periodic_save_does_not_save_it_twice(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=8), output=dict(checkpoint_every_evaluations=4)), tmp_path)
    assert state == 'completed'
    saved = _checkpoints(layout)
    assert saved[-1] == (8, 'final', 'periodic') and [s for s in saved if s[0] == 8] == [saved[-1]]
    latest = read_json(layout.run_dir / 'checkpoints' / 'latest.json')
    assert latest['kind'] == 'final'
    events = [json.loads(line) for line in (layout.logs / 'events.jsonl').read_text().splitlines()]
    assert any(e.get('event') == 'checkpoint_saved' and e.get('kind') == 'final' and e.get('relabelled_from') == 'periodic' for e in events)


def test_a_run_that_completes_between_two_periodic_saves_still_writes_its_final_save(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=6), output=dict(checkpoint_every_evaluations=4)), tmp_path)
    assert state == 'completed'
    assert _checkpoints(layout)[-1] == (6, 'final', None)


def test_one_save_hashes_the_optimizer_source_once(monkeypatch):
    from analog_optimizer.training import sac
    from gator_workbench import checkpoints
    calls, real = [], sac.source_digest
    monkeypatch.setattr(sac, 'source_digest', lambda: calls.append(1) or real())
    with checkpoints._one_source_digest():
        first, second, third = sac.source_digest(), sac.source_digest(), sac.source_digest()
    assert first == second == third == real() and len(calls) == 1
    sac.source_digest()
    assert len(calls) == 2                                                       # the package's own function is back
