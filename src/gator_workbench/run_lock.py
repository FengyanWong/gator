"""One worker per run directory: the run's lock file, and the time stamp it writes.

Moved from engine.py by the refactoring (docs/plan-refactoring.md), so that modules that only need the lock do not
import the run engine.
"""
from __future__ import annotations

from datetime import timezone
import fcntl
import os
from pathlib import Path
import socket
import time

from .storage.dataset import utcnow


def iso(value=None):
    """Format the supplied time, or the current time, as a UTC ISO timestamp."""
    return (value or utcnow()).astimezone(timezone.utc).isoformat()


class RunLock:
    """One worker per run directory: reconnecting or double-clicking cannot start a duplicate."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = None

    def acquire(self, patience=0.2):
        """`patience`: seconds to wait for a lock held only by a probe of `held` - a status read, a run list - which
        holds it for a moment; a worker holds it for its whole life, so it is still refused (review of 2026-10-01:
        a Resume pressed while the page read the status could be refused as "already running")."""
        self._stream = self.path.open('a+')
        deadline = time.monotonic() + patience
        while True:
            try:
                fcntl.flock(self._stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() < deadline:
                    time.sleep(0.01)
                    continue
                self._stream.close()
                self._stream = None
                raise RuntimeError(f'Another worker already owns this run: {self.path.parent.parent}')
        self._stream.seek(0)
        self._stream.truncate()
        self._stream.write(f'{os.getpid()} {socket.gethostname()} {iso()}\n')
        self._stream.flush()

    def release(self):
        """Unlock and close this instance's held run-lock stream."""
        if self._stream is not None:
            fcntl.flock(self._stream, fcntl.LOCK_UN)
            self._stream.close()
            self._stream = None

    # ---- hand-over: the lock is held CONTINUOUSLY from before the manifest is touched until the worker
    # ends. flock belongs to the open file description, which the child inherits through the descriptor.
    def fileno(self):
        return self._stream.fileno()

    def detach(self):
        """Close this process's descriptor WITHOUT unlocking: the worker's inherited copy keeps the lock."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    @classmethod
    def adopt(cls, path, descriptor):
        """Create a run lock around an inherited descriptor."""
        lock = cls(path)
        lock._stream = os.fdopen(descriptor, 'a+')
        return lock

    @property
    def held_here(self):
        return self._stream is not None

    @staticmethod
    def held(path) -> bool:
        """A worker holds the lock exclusively. The probe asks for a SHARED lock, which every other probe can share: an
        exclusive probe was itself seen as a worker by a probe running at the same moment (review of 2026-10-01: two
        status reads at once - the page's poll and another request - said "worker alive" for a stopped run, and the
        header went back from "Start" to "Aborting..."; 40 % of 8 concurrent probes of a free lock said "held")."""
        path = Path(path)
        if not path.exists():
            return False
        with path.open('a+') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(stream, fcntl.LOCK_UN)
                return False
            except OSError:
                return True
