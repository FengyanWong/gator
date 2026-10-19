"""Save task, one at a time, and how far it is (record 7.198).

A save of a Maestro-measured task takes about half a minute: Virtuoso writes the task's Maestro test into the cell and
reads it back, netlists it, and the cell is read into the workbench again. The page showed nothing else meanwhile (its
"Saving..." is screen-reader text since the icon buttons of record 7.82), so on 2026-10-05 the user loaded the page
again during two saves and pressed Save task again from older rows (record 7.194). Now this process keeps the save that
is running - its task, its steps, where it is - and the last one that ended. The page asks when its Save task appears,
follows a running save until it ends and keeps its own Save task closed meanwhile; a second save is refused while one
runs, whichever page or tab sends it (`Busy`). Held in memory: a restart of the backend forgets both."""
from __future__ import annotations
from contextlib import contextmanager
import threading
import time
import uuid

from .security import redact
from .storage.dataset import utcnow

# Every step a save can take, in their order; a save names the ones it takes (`Save.mark`).
TITLES = dict(
    copy="Virtuoso makes the task's own copy of the cell",
    setup='Virtuoso writes the Maestro test into the cell and reads it back',
    deck='Virtuoso netlists the Maestro test',
    read='Virtuoso reads the cell into the workbench',
    files='Writing the task files and checking them',
)
ANSWER_KEYS = ('task_key', 'revision', 'created', 'baseline_kept', 'changed', 'baseline')

_lock = threading.Lock()
_running: dict | None = None          # the save going on now; changed only under _lock
_last: dict | None = None             # the last save that ended
_took: dict[str, float] = {}          # task key -> seconds its last successful save took


class Busy(RuntimeError):
    """Another save is running."""


class Save:
    """The running save, as `profiles.save_task` reports it: `mark(step, steps)` says which step starts now and every
    step this save takes. The route puts the save's answer into `answer`."""

    def __init__(self, record):
        self._record = record
        self.answer = None

    def mark(self, step, steps):
        with _lock:
            self._record.update(steps=list(steps), step=step, step_started=time.monotonic())


@contextmanager
def running(task_key):
    """Holds the one place for a save while the block runs; `Busy` when a save is running already. The block's end -
    its answer, or the problem that ended it - becomes `last`."""
    global _running, _last
    with _lock:
        if _running is not None:
            seconds = time.monotonic() - _running['started']
            raise Busy(f'Another save is running ({_running["task_key"]}, {seconds:.0f} s so far). Save as can be pressed '
                       'again when it has ended.')
        record = _running = dict(id=uuid.uuid4().hex[:12], task_key=task_key, started_utc=utcnow().isoformat(),
                                 started=time.monotonic(), steps=[], step=None, step_started=None)
    save = Save(record)
    outcome = None
    try:
        yield save
        answer = save.answer or {}
        outcome = dict(ok=True, answer={key: answer.get(key) for key in ANSWER_KEYS if key != 'baseline' or key in answer})
    except BaseException as exc:
        outcome = dict(ok=False, problem=_problem(exc))
        raise
    finally:
        with _lock:
            seconds = round(time.monotonic() - record['started'], 1)
            if outcome is None:                                         # a generator closed without an outcome
                outcome = dict(ok=False, problem=dict(message='The save stopped without an answer.', code=None))
            if outcome['ok']:
                _took[task_key] = seconds
            _last = dict(id=record['id'], task_key=task_key, ended_utc=utcnow().isoformat(), seconds=seconds, **outcome)
            _running = None


def _problem(exc) -> dict:
    detail = getattr(exc, 'detail', None)                              # the route's refusal: {message, code, ...}
    if isinstance(detail, dict):
        return dict(message=str(detail.get('message') or ''), code=detail.get('code'))
    return dict(message=redact(f'{type(exc).__name__}: {exc}', 1000), code=None)


def status() -> dict:
    """The save running now (`running`, None when there is none) and the last one that ended (`last`). Seconds are
    counted here, so the page needs no clock of its own."""
    with _lock:
        now, record = time.monotonic(), _running
        running_now = None
        if record is not None:
            steps, step = record['steps'], record['step']
            running_now = dict(id=record['id'], task_key=record['task_key'], started_utc=record['started_utc'],
                               seconds=round(now - record['started'], 1),
                               steps=[dict(id=s, title=TITLES[s]) for s in steps], step=step,
                               step_number=steps.index(step) + 1 if step in steps else 0,
                               step_seconds=round(now - record['step_started'], 1) if record['step_started'] else None,
                               usual_seconds=_took.get(record['task_key']))
        return dict(running=running_now, last=_last)


def running_task() -> str | None:
    """The task key of the save running now, if any."""
    with _lock:
        return _running['task_key'] if _running is not None else None
