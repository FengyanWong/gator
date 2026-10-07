"""Launch requests answered once (record 7.261; plan docs/plan-frontend-run-workflow.md, "One launcher", step 4).

The page sends an id with each Start and Continue and keeps it until the answer has arrived. The same id again - a
second press that overtook the first, or the page asking after a reload during a slow start - gets the answer the
first request got: the same run, never a second one. The answer is written as soon as the run exists and BEFORE its
worker is started (`run_routes.once`), so a launch whose acknowledgement was lost on the way is still found. A refused
request, or one that failed before anything was made, leaves no record, so the repeat the page sends with the answers
to the backend's questions (real budget, a model from another task) is a request of its own. One small file per id in
the workbench's own settings folder (local_settings_dir: tests and browser checks have their own), pruned after a week.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .paths import local_settings_dir
from .storage.atomic import write_json

ID_PATTERN = r'^[A-Za-z0-9_-]{8,80}$'
_ID = re.compile(ID_PATTERN)
KEEP_SECONDS = 7 * 24 * 3600
# A request whose backend went away on the way (a restart during a start) is no longer "on its way" after this long; a
# start takes seconds, the check before every run at most a few minutes.
STALE_PENDING_SECONDS = 15 * 60
_PRUNED = dict(at=0.0)


class RequestPending(RuntimeError):
    """The same request is still being answered."""


def _folder() -> Path:
    return local_settings_dir() / 'launch_requests'


def _path(request_id: str) -> Path:
    if not isinstance(request_id, str) or not _ID.match(request_id):
        raise ValueError('A launch request id is 8 to 80 letters, digits, "-" or "_".')
    return _folder() / f'{request_id}.json'


def _prune(folder: Path):
    """Records older than a week go, looked for at most once an hour (the folder is on the slow mounted drive)."""
    now = time.time()
    if now - _PRUNED['at'] < 3600:
        return
    _PRUNED['at'] = now
    for item in folder.glob('*.json'):
        try:
            if now - item.stat().st_mtime > KEEP_SECONDS:
                item.unlink()
        except OSError:
            pass


def _record(path: Path) -> dict | None:
    """The record, or None: missing, or not readable as JSON yet - claim() creates the file first and writes it a moment
    later, and another process reading it in between used to fail with a JSONDecodeError (review of 2026-10-07). An
    unreadable record counts as one still on its way, by its age like any other."""
    try:
        record = json.loads(path.read_text(encoding='utf8'))
    except (FileNotFoundError, ValueError, UnicodeError):
        return None
    return record if isinstance(record, dict) else None


def claim(request_id: str, kind: str) -> dict | None:
    """None: the request is new and is now on its way - answer() or drop() ends that. A dict: it was answered before,
    and this is the answer the first request got. RequestPending: it is still on its way."""
    path = _path(request_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _prune(path.parent)
    for _ in range(3):
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            record = _record(path)
            if record is not None and record.get('state') == 'done':
                return record.get('answer')
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue                                  # dropped meanwhile: the request is new again
            if age < STALE_PENDING_SECONDS:             # also a record just created and not written yet
                raise RequestPending('This launch is already on its way; its answer comes in a moment.')
            path.unlink(missing_ok=True)
            continue
        with os.fdopen(handle, 'w', encoding='utf8') as stream:
            json.dump(dict(state='pending', kind=kind, at=time.time()), stream)
        return None
    raise RequestPending('This launch is already on its way; its answer comes in a moment.')


def answer(request_id: str, result: dict):
    """The request made `result` (a run): a repeat of the id gets it, for a week."""
    write_json(_path(request_id), dict(state='done', at=time.time(), answer=result))


def drop(request_id: str):
    """The request was refused or failed: nothing was made, and the id may be sent again."""
    _path(request_id).unlink(missing_ok=True)


def lookup(request_id: str) -> dict:
    """{'state': 'done', 'answer': ...}, {'state': 'pending'} or {'state': 'unknown'} (never arrived, refused, failed,
    or older than a week). The page asks this after a reload during a launch, instead of sending it again."""
    path = _path(request_id)
    record = _record(path)
    if record is not None and record.get('state') == 'done':
        return dict(state='done', answer=record.get('answer'))
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return dict(state='unknown')
    return dict(state='pending') if age < STALE_PENDING_SECONDS else dict(state='unknown')
