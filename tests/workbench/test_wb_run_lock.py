"""The run lock and its probe (RunLock.held, review of 2026-10-01). A worker holds the lock exclusively for its whole life;
the probe behind "worker alive" (run status, corner checks, bridge busy) must never mistake another probe for a worker.
Two status reads at the same moment - the page's poll and another request - said "worker alive" for a stopped run, and
the header went back from "Start" to "Aborting..."; an exclusive probe could also make a Resume fail as "already
running"."""
import fcntl
import threading
import time
from pathlib import Path

import pytest

from gator_workbench import runs
from gator_workbench.engine import RunLock
from gator_workbench.layout import RunLayout
from gator_workbench.storage import write_json


@pytest.fixture
def lock_path(tmp_path):
    path = tmp_path / 'control' / 'run.lock'
    path.parent.mkdir()
    path.write_text('')
    return path


def probe_in_progress(path, seconds):
    """What a probe of another request does for a moment: hold the shared lock, then let go."""
    stream = Path(path).open('a+')
    fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)

    def end():
        time.sleep(seconds)
        fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()
    thread = threading.Thread(target=end)
    thread.start()
    return thread


def test_a_probe_in_progress_is_not_a_worker(lock_path):
    other = probe_in_progress(lock_path, 0.3)
    try:
        assert RunLock.held(lock_path) is False
    finally:
        other.join()


def test_a_worker_is_seen_and_its_end_too(lock_path):
    worker = RunLock(lock_path)
    worker.acquire()
    try:
        assert RunLock.held(lock_path) is True
    finally:
        worker.release()
    assert RunLock.held(lock_path) is False


def test_concurrent_probes_never_see_a_worker(lock_path):
    seen = []

    def probe():
        seen.extend(RunLock.held(lock_path) for _ in range(300))
    threads = [threading.Thread(target=probe) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(seen) == 1800 and not any(seen)               # the exclusive probe said "held" ~40 % of the time


def test_acquire_waits_out_a_probe_but_still_refuses_a_worker(lock_path):
    other = probe_in_progress(lock_path, 0.05)
    try:
        lock = RunLock(lock_path)
        lock.acquire()                                         # waited the probe out (default patience 0.2 s)
        lock.release()
    finally:
        other.join()
    other = probe_in_progress(lock_path, 0.3)
    try:
        with pytest.raises(RuntimeError):
            RunLock(lock_path).acquire(patience=0)             # no patience: the moment of the probe refused it
    finally:
        other.join()
    worker = RunLock(lock_path)
    worker.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(RuntimeError, match='Another worker already owns this run'):
            RunLock(lock_path).acquire(patience=0.1)
        assert time.monotonic() - started < 2
    finally:
        worker.release()


def test_a_stopped_run_read_during_another_read_has_no_worker(tmp_path):
    layout = RunLayout(tmp_path / 'run')
    layout.control.mkdir(parents=True)
    write_json(layout.status, dict(state='stopped', heartbeat_utc='2026-10-01T02:17:40+00:00'))
    (layout.control / 'run.lock').write_text('')
    other = probe_in_progress(layout.control / 'run.lock', 0.3)
    try:
        status = runs.run_status(layout.run_dir)
    finally:
        other.join()
    assert status['state'] == 'stopped' and status['worker_alive'] is False
