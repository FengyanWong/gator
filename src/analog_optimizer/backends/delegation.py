"""Which thread a simulation belongs to, and where a thread's output goes: a backend's owning thread lends its token to
the helper threads that run a candidate's condition jobs side by side, and each simulation thread captures its own
stdout and stderr. Moved here from virtuoso_bridge.py (which still exports these names) by the optimizer clean-up of
2026-10-09 (plan-refactoring E6)."""
from contextlib import contextmanager
import sys
import threading


# A candidate's condition jobs may run side by side on helper threads of the backend's owning thread (2026-09-30). Such
# a helper carries its owner's token here, and only run_simulation accepts it: every call that touches the Virtuoso
# session still demands the owning thread itself.
_delegation = threading.local()
_capture = threading.local()
_capture_install = threading.Lock()


def delegated_owner():
    """(thread id, pid) of the owner this helper thread runs a simulation for, else None."""
    return getattr(_delegation, 'owner', None)


class _ThreadRoutedStream:
    """Stands in for sys.stdout / sys.stderr: a thread that captures writes to its own log, every other thread to the
    stream this one replaced. contextlib.redirect_stdout swaps the process-wide stream, which two simulations running
    side by side would mix into each other's logs."""
    def __init__(self, original, name):
        self._original, self._name = original, name

    def write(self, text):
        return (getattr(_capture, self._name, None) or self._original).write(text)

    def flush(self):
        (getattr(_capture, self._name, None) or self._original).flush()

    def __getattr__(self, item):
        return getattr(self._original, item)


@contextmanager
def _captured(log):
    """This thread's stdout and stderr go to `log` while inside; other threads keep theirs."""
    with _capture_install:
        for name in ('stdout', 'stderr'):
            if not isinstance(getattr(sys, name), _ThreadRoutedStream):
                setattr(sys, name, _ThreadRoutedStream(getattr(sys, name), name))
    before = getattr(_capture, 'stdout', None), getattr(_capture, 'stderr', None)
    _capture.stdout = _capture.stderr = log
    try:
        yield
    finally:
        _capture.stdout, _capture.stderr = before
