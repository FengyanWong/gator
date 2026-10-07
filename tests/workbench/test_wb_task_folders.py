"""Persistent organization must preserve task identity and unrelated concurrent edits."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from gator_workbench import task_folders as folders, tasks
from gator_workbench.paths import local_settings_dir
from helpers import workbench_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, 'list_tasks', lambda: [dict(task_key=key) for key in ('real:a', 'real:b', 'ngspice:c')])
    with TestClient(workbench_app(tmp_path)) as client:
        yield client


def test_api_move_rename_reload_and_delete_preserve_tasks(client):
    assert client.get('/api/task-folders').json()['folders'] == {}
    first = client.post('/api/task-folders', json={'name': ' Graph Transformer '}).json()['created_id']
    second = client.post('/api/task-folders', json={'name': 'GraphGPS'}).json()['created_id']
    reply = client.put('/api/task-folders/assign', json={'task_keys': ['real:a', 'real:b'], 'folder_id': first})
    assert reply.status_code == 200
    assert reply.json()['assignments'] == {'real:a': first, 'real:b': first}
    client.put('/api/task-folders/assign', json={'task_keys': ['real:b'], 'folder_id': second})
    client.patch(f'/api/task-folders/{first}', json={'name': 'GT'})
    saved = json.loads((local_settings_dir() / folders.FILE).read_text())
    assert saved == client.get('/api/task-folders').json()
    assert saved['assignments'] == {'real:a': first, 'real:b': second}
    assert saved['folders'][first] == 'GT'
    deleted = client.delete(f'/api/task-folders/{first}').json()
    assert deleted['assignments'] == {'real:b': second}
    assert tasks.list_tasks() == [dict(task_key=key) for key in ('real:a', 'real:b', 'ngspice:c')]
    assert client.put('/api/task-folders/assign', json={'task_keys': ['real:b'], 'folder_id': None}).json()['assignments'] == {}


@pytest.mark.parametrize('name', ['', '   ', 'all TASKS', 'Unfiled', '../bad', 'a/b', 'a\\b', 'a\nline', 'x' * 61])
def test_invalid_names_do_not_write(client, name):
    assert client.post('/api/task-folders', json={'name': name}).status_code in (409, 422)
    assert client.get('/api/task-folders').json()['folders'] == {}


def test_duplicate_missing_and_removed_tasks_are_atomic(client):
    first = client.post('/api/task-folders', json={'name': 'GT'}).json()['created_id']
    assert client.post('/api/task-folders', json={'name': 'gt'}).status_code == 409
    assert client.put('/api/task-folders/assign', json={'task_keys': ['real:a', 'real:removed'], 'folder_id': first}).status_code == 409
    assert client.put('/api/task-folders/assign', json={'task_keys': [], 'folder_id': first}).status_code == 422
    assert client.put('/api/task-folders/assign', json={'task_keys': ['real:a'], 'folder_id': 'missing'}).status_code == 404
    assert client.get('/api/task-folders').json()['assignments'] == {}
    assert client.patch('/api/task-folders/missing', json={'name': 'x'}).status_code == 404
    assert client.delete('/api/task-folders/missing').status_code == 404


@pytest.mark.parametrize('content', ['{broken', '{"version": 999}', '{"version":1,"folders":{},"assignments":{"real:a":"missing"}}'])
def test_corrupt_state_is_reported_and_never_overwritten(client, content):
    directory = local_settings_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / folders.FILE
    path.write_text(content)
    assert client.get('/api/task-folders').status_code == 409
    assert client.post('/api/task-folders', json={'name': 'New'}).status_code == 409
    assert path.read_text() == content


def test_concurrent_changes_keep_each_other_and_duplicate_names_are_rejected():
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: folders.create(f'Folder {i}'), range(8)))
    ids = [r['created_id'] for r in results]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: folders.move([f'real:{i}'], ids[i], known_tasks=[f'real:{i}']), range(8)))
    assert len(folders.read()['folders']) == len(folders.read()['assignments']) == 8
    with pytest.raises(folders.FolderError):
        folders.rename(ids[0], 'Folder 1')
