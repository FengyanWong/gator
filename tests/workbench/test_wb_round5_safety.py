"""Round-5 review fixes (2026-09-29): a worker that cannot start says so, settings saves that neither fail nor lose
each other's keys, a hand-edited settings.json with a typo, the manifest's test conditions, the Host allowlist, malformed
bodies and NUL bytes, the output-folder size walk, the run and model lists, and git without optional locks. (The round's
agent parts - license text kept from the agent, a cancel before the agent CLI starts, web links in a settings review -
went with the Agent tab's own agent on 2026-10-06, record 7.226.) MOCK only: no Virtuoso, no simulator."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, layout as layout_module, paths, run_index, runs, schema, settings_store, worker
from gator_workbench.api import app as app_module
from gator_workbench.storage import atomic, read_dict, read_json
from helpers import execute, make_config, roots_for, workbench_app
from helpers import edit_json


def prepared(root, **kwargs):
    """A MOCK run as prepare_run leaves it for its worker: state `created`."""
    layout, manifest = runs.prepare_run(make_config(root, **kwargs), roots_for(root))
    return layout, manifest


# ------------------------------------------------------------------------------- A3: a worker that fails at startup
def test_a_worker_that_cannot_start_says_so_in_the_run_status(tmp_path):
    layout, manifest = prepared(tmp_path)
    # schema.py or compile.py changed under a running backend: the task hash no longer matches the run's manifest
    edit_json(layout.manifest, lambda m: m.update(task_definition_hash='0' * 64))
    with pytest.raises(RuntimeError, match='no longer matches'):         # still raised: the traceback goes to worker.log
        worker.main(['--run-dir', str(layout.run_dir), '--threads'])
    status = runs.run_status(layout.run_dir)
    assert status['state'] == 'failed' and not status['worker_alive'] and status['run_id'] == manifest['run_id']
    assert status['error'] == 'RuntimeError: effective_config.json no longer matches the task this run was created for'
    assert status['paths'] == layout.subpaths()


def test_a_mock_real_mismatch_is_a_failed_start_too(tmp_path, capsys):
    layout, manifest = prepared(tmp_path)
    edit_json(layout.manifest, lambda m: m.update(mock=False))
    assert worker.main(['--run-dir', str(layout.run_dir), '--threads']) == 2
    assert 'Mock/real provenance differs from the run manifest' in capsys.readouterr().err
    status = read_json(layout.status)
    assert status == dict(state='failed', run_id=manifest['run_id'], error='Mock/real provenance differs from the run manifest',
                          paths=layout.subpaths())


def test_a_half_edited_module_still_leaves_a_failed_status(tmp_path, monkeypatch):
    layout, manifest = prepared(tmp_path)
    # None in sys.modules makes an import fail, as a module another session is half-way through editing does. Even the
    # storage and layout modules are gone here: the status is written with plain JSON.
    for name in ('gator_workbench.engine', 'gator_workbench.storage.atomic', 'gator_workbench.layout'):
        monkeypatch.setitem(sys.modules, name, None)
    with pytest.raises(ImportError):
        worker.main(['--run-dir', str(layout.run_dir), '--threads'])
    status = json.loads(layout.status.read_text())
    assert status == dict(state='failed', run_id=manifest['run_id'],
                          error='ModuleNotFoundError: import of gator_workbench.engine halted; None in sys.modules')
    assert not [p for p in layout.run_dir.iterdir() if atomic.TEMP_MARKER in p.name]


def test_a_failed_start_outside_a_run_directory_creates_nothing(tmp_path):
    missing = tmp_path / 'no_such_run'
    with pytest.raises(FileNotFoundError):
        worker.main(['--run-dir', str(missing), '--threads'])
    assert not missing.exists()


# ------------------------------------------------------------------------------- A4: two saves of settings.json at once
def test_concurrent_settings_saves_keep_every_update(monkeypatch):
    # Both saves read the file before either writes (the barrier), unless the lock makes the second wait for the first.
    barrier, original = threading.Barrier(2), settings_store.write_json

    def write_after_both_read(path, value, **kwargs):
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return original(path, value, **kwargs)
    monkeypatch.setattr(settings_store, 'write_json', write_after_both_read)
    threads = [threading.Thread(target=settings_store.save_settings, kwargs={key: value})
               for key, value in (('agent', dict(provider='disabled')), ('output_root', '/tmp/somewhere'))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert settings_store.load_settings() == dict(agent=dict(provider='disabled'), output_root='/tmp/somewhere')


def publish_with(tmp_path):
    """(destination, publish): `publish()` puts our file over settings.json. What happens right after our rename is
    staged by replacing `atomic.fsync_directory`, the step that follows it."""
    destination = tmp_path / 'settings.json'
    destination.write_text('{"old": 1}')
    temporary = atomic.temporary_path(destination)
    temporary.write_text('{"ours": 1}')
    return destination, lambda: atomic.publish(temporary, destination)


def test_a_newer_complete_replacement_is_no_write_failure(tmp_path, monkeypatch):
    destination, publish = publish_with(tmp_path)
    real_fsync = atomic.fsync_directory

    def another_writer_lands(path):
        real_fsync(path)
        newer = atomic.temporary_path(destination)
        newer.write_text('{"a newer writer": "longer"}')
        os.replace(newer, destination)
    monkeypatch.setattr(atomic, 'fsync_directory', another_writer_lands)
    assert publish() == len('{"ours": 1}')
    assert json.loads(destination.read_text()) == {'a newer writer': 'longer'}


def test_our_own_incomplete_or_missing_file_is_still_a_write_failure(tmp_path, monkeypatch):
    destination, publish = publish_with(tmp_path)
    real_fsync = atomic.fsync_directory

    def grows_in_place(path):                     # the SAME file (inode) with another size: not a newer writer's file
        real_fsync(path)
        with destination.open('a') as stream:
            stream.write(' ')
    monkeypatch.setattr(atomic, 'fsync_directory', grows_in_place)
    with pytest.raises(atomic.PersistenceError, match='size'):
        publish()
    destination, publish = publish_with(tmp_path)
    monkeypatch.setattr(atomic, 'fsync_directory', lambda path: destination.unlink())
    with pytest.raises(atomic.PersistenceError, match='not visible'):   # the 9p retry still ends in a failure when it stays gone
        publish()


# ------------------------------------------------------------------------------- A12: a settings.json with a typo
@pytest.fixture
def broken_settings():
    path = paths.local_settings_dir() / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '{"output_root": "/somewhere",}\n'                          # a hand edit with a trailing comma
    path.write_text(text)
    return path, text


def test_a_settings_file_with_a_typo_takes_no_page_down(tmp_path, broken_settings):
    path, text = broken_settings
    client = TestClient(workbench_app(tmp_path))
    meta = client.get('/api/meta')
    assert meta.status_code == 200 and meta.json()['remembered'] == {}
    assert meta.json()['settings_problem'] == (f'{path} is not valid JSON (line 1): fix or remove it; nothing is saved to it '
                                               'until then.')
    assert client.get('/api/runs', params=dict(output_root=str(tmp_path))).status_code == 200
    assert path.read_text() == text                                     # never overwritten: it holds the user's own edits


def test_a_run_still_starts_and_leaves_the_broken_file_alone(tmp_path, broken_settings):
    path, text = broken_settings
    layout, _ = prepared(tmp_path)                                      # used to fail here, AFTER its run folder was made
    assert read_json(layout.status)['state'] == 'created' and path.read_text() == text
    path.write_text('{}')                                               # fixed by the user: saving works again
    prepared(tmp_path)
    settings, problem = runs.read_settings()
    assert problem is None and settings['output_root'] == str(tmp_path)


@pytest.mark.parametrize('text, problem', [('[1, 2]', 'does not hold a JSON object'), ('null', 'does not hold a JSON object'),
                                           (b'{"a": "\xff"}', 'cannot be read (UnicodeDecodeError)')])
def test_other_unreadable_settings_files_are_said_and_kept(text, problem):
    path = paths.local_settings_dir() / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode())
    settings, said = runs.read_settings()
    assert settings == {} and problem in said and 'nothing is saved to it until then' in said
    runs.save_settings(concurrency=2)
    assert path.read_bytes() == (text if isinstance(text, bytes) else text.encode())
    path.unlink()                                                       # no file at all is no problem
    assert runs.read_settings() == ({}, None)


# ------------------------------------------------------------------------------- A11: the manifest's test conditions
def test_a_nominal_only_manifest_keeps_its_exact_words(tmp_path):
    _, manifest = prepared(tmp_path)
    assert manifest['test_conditions'] == dict(conditions=['nominal'], note='The sizing environment is nominal-only')


@pytest.mark.parametrize('policy, who', [('always', 'every design'), ('after_nominal', 'designs that pass nominal')])
def test_a_corner_run_manifest_names_its_corners(policy, who):
    stated = runs.manifest_conditions(schema.ConditionsConfig(policy=policy, corners=['ss_hot_low', 'fs_nominal']))
    assert stated['conditions'] == ['nominal', 'ss_hot_low', 'fs_nominal']
    assert 'nominal-only' not in stated['note'] and who in stated['note'] and f'policy {policy}' in stated['note']


# ------------------------------------------------------------------------------- A15: the Host allowlist
@pytest.mark.parametrize('host, status', [('127.0.0.1:8765', 200), ('localhost:8765', 200), ('[::1]:8765', 200), ('testserver', 200),
                                          ('rebound.example', 400), ('rebound.example:8765', 400), ('127.0.0.1.nip.io', 400)])
def test_only_the_names_the_backend_is_served_under_are_answered(tmp_path, host, status):
    client = TestClient(workbench_app(tmp_path))
    assert client.get('/api/connection/profiles', headers={'Host': host}).status_code == status


def test_the_host_the_operator_serves_on_is_answered_too(tmp_path):
    client = TestClient(workbench_app(tmp_path, host='192.168.1.50'))
    assert client.get('/api/connection/profiles', headers={'Host': '192.168.1.50:8765'}).status_code == 200
    assert client.get('/api/connection/profiles', headers={'Host': 'rebound.example'}).status_code == 400
    assert app_module.trusted_hosts('2001:db8::5')[-1] == '[2001:db8::5]'
    assert app_module.trusted_hosts('Lab-PC.local')[-2:] == ['Lab-PC.local', 'lab-pc.local']
    assert app_module.trusted_hosts('::1') == app_module.trusted_hosts('localhost') == app_module.trusted_hosts()
    assert app_module.trusted_hosts('0.0.0.0') == app_module.trusted_hosts('::') == ['*']   # every interface: names unknown


def test_serve_hands_its_host_to_the_app(monkeypatch):
    import uvicorn
    from gator_workbench import api, cli as cli_module
    made, served = {}, {}
    monkeypatch.setattr(api, 'create_app', lambda **options: made.update(options) or 'app')
    monkeypatch.setattr(uvicorn, 'run', lambda app, **options: served.update(app=app, **options))
    assert cli_module.main(['serve', '--host', '192.168.1.50', '--port', '8799']) == 0
    assert made['host'] == '192.168.1.50' and served == dict(app='app', host='192.168.1.50', port=8799, log_level='info',
                                                             timeout_graceful_shutdown=cli_module.SHUTDOWN_GRACE_SECONDS)


# ------------------------------------------------------------------------------- A16: malformed bodies and NUL bytes
def test_a_malformed_model_request_is_refused_not_a_server_error(tmp_path):
    layout, _ = prepared(tmp_path)
    client = TestClient(workbench_app(tmp_path))
    for body in ({}, dict(run_dir=str(layout.run_dir), checkpoint_id=5), dict(run_dir=['x']),
                 dict(run_dir=str(layout.run_dir), config=[1]), dict(run_dir=str(layout.run_dir), unexpected=1)):
        assert client.post('/api/runs/model', json=body).status_code == 422, body
    # what the page sends is still answered as before: no save point yet is a 404, a foreign folder a 403
    assert client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest')).status_code == 404
    assert client.post('/api/runs/model', json=dict(run_dir='/etc', checkpoint_id='latest', config=None)).status_code == 403


def test_a_nul_byte_in_a_path_is_refused_like_any_other_bad_path(tmp_path):
    layout, _ = prepared(tmp_path)
    client = TestClient(workbench_app(tmp_path), raise_server_exceptions=False)
    bad = str(tmp_path / 'a\x00b')
    assert client.get('/api/runs/status', params=dict(run_dir=bad)).status_code == 403
    assert client.get('/api/output/browse', params=dict(path=bad)).status_code == 403
    assert client.get('/api/runs', params=dict(output_root=bad)).status_code == 403
    assert client.get('/api/runs/models', params=dict(output_root=bad)).status_code == 403
    assert client.get('/api/runs/download', params=dict(run_dir=str(layout.run_dir), path='run_manifest.json\x00')).status_code == 403
    check = client.post('/api/output/check', json=dict(path=bad))
    assert check.status_code == 200 and check.json()['allowed'] is False and 'NUL' in check.json()['error']
    assert roots_for(tmp_path).is_allowed(bad) is False


# ------------------------------------------------------------------------------- B3: the output-folder size walk
def rglob_bytes(path):
    """The walk directory_bytes replaced, kept here as the reference its totals must equal."""
    total = 0
    path = Path(path)
    if not path.exists():
        return 0
    for child in path.rglob('*'):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            pass
    return total


def test_the_size_walk_counts_exactly_what_the_old_one_did(tmp_path):
    outside = tmp_path / 'outside'
    (outside / 'deep').mkdir(parents=True)
    (outside / 'big.bin').write_bytes(b'x' * 5000)
    (outside / 'deep' / 'more.bin').write_bytes(b'y' * 700)
    root = tmp_path / 'root'
    for index, folder in enumerate(('a', 'a/b', 'a/b/c', '.hidden', 'unreadable', 'listable_only', 'empty')):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / f'file{index}.txt').write_bytes(b'z' * (10 * index + 3))
        (root / folder / '.dotfile').write_bytes(b'd' * (index + 1))
    (root / 'a' / 'link_to_file').symlink_to(outside / 'big.bin')          # never counted
    (root / 'a' / 'link_to_dir').symlink_to(outside)                       # never followed
    (root / 'a' / 'b' / 'dangling').symlink_to(tmp_path / 'nowhere')
    (root / 'a' / 'b' / 'hard_link').hardlink_to(root / 'a' / 'file0.txt')
    os.mkfifo(root / 'a' / 'pipe')                                         # not a regular file
    (root / 'unreadable' / 'inner').mkdir()
    (root / 'unreadable' / 'inner' / 'secret.bin').write_bytes(b's' * 999)
    os.chmod(root / 'unreadable', 0o000)
    os.chmod(root / 'listable_only', 0o444)                                # listed, but its entries cannot be stat'ed
    (tmp_path / 'root_link').symlink_to(root)
    try:
        for path in (root, root / 'a', root / 'a' / 'b', root / 'empty', tmp_path / 'root_link', tmp_path / 'root_link' / 'a',
                     root / 'a' / 'link_to_dir', root / 'a' / 'file0.txt', root / 'a' / 'link_to_file', root / 'nothing_here',
                     root / 'a' / 'b' / 'dangling', root / 'unreadable', root / 'listable_only', outside):
            assert paths.directory_bytes(path) == rglob_bytes(path), path
        assert paths.directory_bytes(root) > 0
    finally:
        os.chmod(root / 'unreadable', 0o755)
        os.chmod(root / 'listable_only', 0o755)


# ------------------------------------------------------------------------------- B8: the run list and the model list
@pytest.fixture(scope='module')
def two_runs(tmp_path_factory):
    root = tmp_path_factory.mktemp('lists')
    execute(make_config(root, run=dict(max_evaluations=6), project=dict(task_name='with_model')), root)
    runs.prepare_run(make_config(root, project=dict(task_name='just_created')), roots_for(root))
    return root


def test_the_run_list_reads_each_status_once_and_the_model_list_no_manifest(two_runs, monkeypatch):
    rows = runs.list_runs(roots_for(two_runs), two_runs)
    assert len(rows) == 2 and rows == json.loads(json.dumps(rows))     # plain JSON as ever
    read = []
    monkeypatch.setattr(layout_module, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    monkeypatch.setattr(run_index, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    monkeypatch.setattr(ckpt, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    # the empty-dict reads of these modules go through read_dict (refactoring package B8): counted the same way
    monkeypatch.setattr(run_index, 'read_dict', lambda path: read.append(Path(path).name) or read_dict(path))
    monkeypatch.setattr(ckpt, 'read_dict', lambda path: read.append(Path(path).name) or read_dict(path))
    listed = runs.list_runs(roots_for(two_runs), two_runs, fresh=True)     # read from disk (Refresh list): each file once
    assert read.count('status.json') == 2 and read.count('run_manifest.json') == 2
    read.clear()
    # Record 7.274: run folders unchanged since the last list are read from its cache - no file at all.
    assert runs.list_runs(roots_for(two_runs), two_runs) == listed and read == []
    models = ckpt.saved_models(listed)
    assert 'run_manifest.json' not in read
    # rows that lost their manifest (a JSON round trip) are read from disk: the same answer
    assert models == ckpt.saved_models(json.loads(json.dumps(listed))) and [m['task_name'] for m in models] == ['with_model']
    assert models[0]['circuit_task'] == 'synthetic:gpdk045_ota5'


# ------------------------------------------------------------------------------- B10: git without optional locks
def test_the_run_provenance_asks_git_without_taking_the_index_lock(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=' M file.py\n' if 'status' in argv else 'abc123\n', stderr='')
    monkeypatch.setattr(layout_module.subprocess, 'run', fake_run)
    provenance = layout_module.code_provenance()
    status = next(argv for argv in calls if 'status' in argv)
    assert status[:3] == ['git', '-C', str(paths.repo_root())] and status[3:] == ['--no-optional-locks', 'status', '--porcelain']
    assert provenance['git_dirty'] is True and provenance['git_dirty_paths'] == 1
