"""A task's shown name (record 7.302): a rename changes what the windows show and what new runs are filed under - never
the task's key, so every run and model that names the task keeps its link."""
import json

import pytest
from fastapi.testclient import TestClient

from gator_workbench import task_names, tasks
from gator_workbench.paths import local_settings_dir
from helpers import workbench_app

MOCK = 'synthetic:gpdk045_ota5'


@pytest.fixture
def client(tmp_path):
    with TestClient(workbench_app(tmp_path)) as client:
        yield client


def _task(client, key=MOCK):
    return next(task for task in client.get('/api/tasks').json()['tasks'] if task['task_key'] == key)


def test_a_rename_changes_the_shown_name_and_the_run_label_never_the_key(client):
    before = _task(client)
    assert before['name'] == 'gpdk045_ota5' and before['starter_project'] == dict(name='mock-gpdk045-ota5', task_name='mock_gpdk045_ota5')
    reply = client.post('/api/tasks/rename', json=dict(task_key=MOCK, name=' ota_demo '))
    assert reply.status_code == 200
    assert reply.json() == dict(task_key=MOCK, name='ota_demo', previous='gpdk045_ota5', internal_name='gpdk045_ota5')
    after = _task(client)
    assert after['task_key'] == MOCK and after['name'] == 'ota_demo'
    assert after['starter_project'] == dict(name='ota-demo', task_name='ota_demo')
    # everything else about the task is what it was
    assert {k: v for k, v in after.items() if k not in ('name', 'starter_project')} == {k: v for k, v in before.items() if k not in ('name', 'starter_project')}
    # the rows of the task still come by its key, filed under the new name
    starter = client.get('/api/tasks/starter', params=dict(task_key=MOCK)).json()
    assert starter['circuit']['task_id'] == MOCK and starter['project'] == dict(name='ota-demo', task_name='ota_demo')
    assert json.loads((local_settings_dir() / task_names.FILE).read_text()) == dict(version=1, names={MOCK: 'ota_demo'})
    # the task's own name takes the rename back and leaves no entry
    back = client.post('/api/tasks/rename', json=dict(task_key=MOCK, name='gpdk045_ota5')).json()
    assert back['name'] == 'gpdk045_ota5' and back['previous'] == 'ota_demo'
    assert _task(client)['starter_project'] == before['starter_project']
    assert json.loads((local_settings_dir() / task_names.FILE).read_text()) == dict(version=1, names={})


@pytest.mark.parametrize('name', ['', '   ', 'x', 'Ota_demo', 'ota demo', '1ota', 'ota-demo', 'ota/demo', 'a' * 41])
def test_a_name_that_is_not_a_task_name_is_refused_and_nothing_is_written(client, name):
    assert client.post('/api/tasks/rename', json=dict(task_key=MOCK, name=name)).status_code == 422
    assert not (local_settings_dir() / task_names.FILE).exists()
    assert _task(client)['name'] == 'gpdk045_ota5'


def test_an_unknown_task_and_a_taken_name_are_refused(client, monkeypatch):
    monkeypatch.setattr(tasks, 'list_tasks', lambda: [dict(task_key=key) for key in ('real:ota_a', 'real:ota_b', 'ngspice:ota_c')])
    assert client.post('/api/tasks/rename', json=dict(task_key='real:gone', name='ota_new')).status_code == 404
    taken = client.post('/api/tasks/rename', json=dict(task_key='real:ota_a', name='ota_b'))       # another task's own name
    assert taken.status_code == 409 and taken.json()['detail']['code'] == 'name_taken'
    assert client.post('/api/tasks/rename', json=dict(task_key='real:ota_a', name='ota_c')).status_code == 409   # whatever its kind
    assert client.post('/api/tasks/rename', json=dict(task_key='real:ota_a', name='ldo_relaxed')).status_code == 200
    shown = client.post('/api/tasks/rename', json=dict(task_key='real:ota_b', name='ldo_relaxed'))  # a name another is shown under
    assert shown.status_code == 409 and shown.json()['detail']['code'] == 'name_taken'
    assert client.post('/api/tasks/rename', json=dict(task_key='real:ota_a', name='ldo_relaxed')).status_code == 200   # its own shown name again
    assert task_names.names() == {'real:ota_a': 'ldo_relaxed'}


def test_a_task_saved_later_under_a_shown_name_wins_and_a_deleted_task_loses_its_name():
    known = ['real:ota_a', 'real:ota_b']
    task_names.rename('real:ota_a', 'ota_new', known=known)
    assert task_names.shown('real:ota_a', others=known) == 'ota_new'
    assert task_names.shown('real:ota_a', others=[*known, 'real:ota_new']) == 'ota_a'       # the later task carries the name itself
    assert task_names.shown('real:ota_b', others=known) == 'ota_b'
    task_names.forget('real:ota_a')
    assert task_names.names() == {} and task_names.shown('real:ota_a') == 'ota_a'
    task_names.forget('real:never_renamed')                                                  # nothing to forget is no error


@pytest.mark.parametrize('content', ['{broken', '{"version": 2, "names": {}}', '{"version": 1, "names": {"real:a": "Not A Name"}}'])
def test_a_names_file_that_is_not_ours_never_breaks_the_list_and_is_never_overwritten(client, content):
    directory = local_settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / task_names.FILE).write_text(content)
    assert _task(client)['name'] == 'gpdk045_ota5'                                           # the list shows the tasks' own names
    assert client.post('/api/tasks/rename', json=dict(task_key=MOCK, name='ota_demo')).status_code == 422
    assert (directory / task_names.FILE).read_text() == content
