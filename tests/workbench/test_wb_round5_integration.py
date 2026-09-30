"""Round-5 follow-ups found while putting the round's changes together: a continued run that cannot start stays
resumable, the Agent settings save says when nothing was saved, and the last routes that turned a NUL byte in a path into
an HTTP 500 refuse it like any other path that is not allowed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import paths, runs, worker
from gator_workbench.storage import read_json
from helpers import make_config, roots_for, workbench_app


def prepared(root):
    return runs.prepare_run(make_config(root), roots_for(root))


def edit_json(path, change):
    value = json.loads(Path(path).read_text())
    change(value)
    Path(path).write_text(json.dumps(value))


@pytest.mark.parametrize('resting', ['paused', 'stopped', 'interrupted'])
def test_a_continued_run_that_cannot_start_stays_resumable_and_says_why(tmp_path, resting):
    layout, _ = prepared(tmp_path)
    edit_json(layout.status, lambda s: s.update(state=resting))           # where the run rested when Continue was pressed

    def continued_under_a_changed_schema(manifest):
        manifest['segments'].append(dict(segment=len(manifest['segments']) + 1, entry='resume'))
        manifest['task_definition_hash'] = '0' * 64
    edit_json(layout.manifest, continued_under_a_changed_schema)
    with pytest.raises(RuntimeError, match='no longer matches'):
        worker.main(['--run-dir', str(layout.run_dir), '--threads'])
    status = read_json(layout.status)
    assert status['state'] == resting                                      # Continue stays on offer once the cause is gone
    assert status['error'] == 'RuntimeError: effective_config.json no longer matches the task this run was created for'


def test_the_agent_settings_save_says_when_nothing_was_saved(tmp_path):
    path = paths.local_settings_dir() / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '{"agent_web_domains": ["example.org",]}\n'                     # a hand edit with a trailing comma
    path.write_text(text)
    client = TestClient(workbench_app(tmp_path))
    answer = client.put('/api/agent/settings', json=dict(provider='disabled'))
    assert answer.status_code == 200 and answer.json()['saved'] is False and path.read_text() == text
    path.write_text('{}')                                                  # fixed by the user
    assert client.put('/api/agent/settings', json=dict(provider='disabled')).json()['saved'] is True


def test_the_last_routes_that_took_a_nul_byte_as_a_server_error_refuse_it(tmp_path):
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    bad = str(tmp_path / 'a\x00b')
    circuit = dict(source='registered_task', task_id='synthetic:gpdk045_ota5', netlist_path=bad)
    assert client.post('/api/circuit/load', json=dict(circuit=circuit)).status_code == 403
    assert client.post('/api/ngspice/read', json=dict(path=bad)).status_code == 403
    check = client.post('/api/ngspice/check', json=dict(text='* a deck\nR1 a 0 1k\n.end\n', source_path=bad))
    assert check.status_code < 500                                         # the deck is checked; the bad path is ignored
