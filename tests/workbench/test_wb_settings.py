"""The remembered settings (settings.json): saved whole under concurrent writers, a file with a typo never overwritten, unreadable files said and kept (refactoring package D2: from test_wb_round5_integration and test_wb_round5_safety)."""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from gator_workbench import paths, runs, settings_store
from gator_workbench.storage import read_json

from helpers import prepared, workbench_app


def test_a_settings_file_with_a_typo_is_never_overwritten(tmp_path):
    path = paths.local_settings_dir() / 'settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '{"output_root": "/somewhere",}\n'                             # a hand edit with a trailing comma
    path.write_text(text)
    runs.save_settings(concurrency=2)
    assert path.read_text() == text and runs.read_settings()[1] is not None
    path.write_text('{}')                                                  # fixed by the user
    runs.save_settings(concurrency=2)
    assert runs.read_settings() == (dict(concurrency=2), None)


# ------------------------------------------------------------------------------- A4: two saves of settings.json at once
def test_concurrent_settings_saves_keep_every_update(monkeypatch):
    # Both saves read the file before either writes (the barrier), unless the lock makes the second wait for the first.
    barrier, original = threading.Barrier(2), settings_store.write_json

    def write_after_both_read(path, value, **kwargs):
        """Delay a settings write so both concurrent readers can observe the prior state."""
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


# ------------------------------------------------------------------------------- A12: a settings.json with a typo
@pytest.fixture
def broken_settings():
    """Write invalid settings JSON and return its path and original text."""
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
