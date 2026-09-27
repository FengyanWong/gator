"""Atomic, verified file publication and an fsynced JSONL appender.

Observed on this project's 9p/drvfs output mount: a ``stat`` issued immediately
after an atomic rename can transiently fail with ENOENT although the data is
durable. Publication therefore verifies with a short bounded retry instead of
reporting a false write failure. A file that still cannot be seen after the
retries IS reported as a failure.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
from uuid import uuid4

TEMP_MARKER = '.gwtmp-'   # only files carrying this marker are ever auto-removed


class PersistenceError(OSError):
    """Core persistence failed. Callers must pause dispatch safely, not continue silently."""


def sha256_file(path, chunk=1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def fsync_directory(path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _await_visible(path: Path, size: int | None, attempts=8, delay=0.025) -> None:
    last = None
    for attempt in range(attempts):
        try:
            actual = path.stat().st_size
            if size is None or actual == size:
                return
            last = f'size {actual} != expected {size}'
        except FileNotFoundError as exc:
            last = str(exc)
        time.sleep(delay * (attempt + 1))
    raise PersistenceError(f'Published file is not visible/complete: {path} ({last})')


def temporary_path(path: Path) -> Path:
    return path.with_name(f'{path.name}{TEMP_MARKER}{uuid4().hex}')


def publish(temporary: Path, destination: Path) -> int:
    """fsync + rename + directory fsync + bounded visibility check. Returns byte size.
    The ONE fsync of the file's bytes happens here, whoever wrote them (write_json does not fsync a second time)."""
    renamed = False
    try:
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        size = temporary.stat().st_size
        temporary.replace(destination)
        renamed = True
        fsync_directory(destination.parent)
        _await_visible(destination, size)
        return size
    except PersistenceError:
        raise
    except OSError as exc:
        raise PersistenceError(f'Cannot publish {destination}: {exc}') from exc
    finally:
        if not renamed:                  # after a rename there is no temporary left to remove
            try:
                temporary.unlink()
            except OSError:
                pass


def jsonable(value):
    """Machine-readable JSON only. Non-finite numbers become null; the caller records why.

    Tuples become lists, Paths become strings, tuple dict keys are rejected (use rows).
    Never falls back to repr() of arbitrary objects.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f'JSON object keys must be strings, got {type(key).__name__}')
            result[key] = jsonable(item)
        return result
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if type(value).__module__.startswith('numpy'):
        return jsonable(value.tolist())
    if hasattr(value, 'model_dump'):
        return jsonable(value.model_dump(mode='json'))
    raise TypeError(f'Not a machine-readable JSON value: {type(value).__name__}')


def nonfinite_paths(value, prefix=''):
    """Paths of NaN/inf numbers, so a manifest can state WHY a value became null."""
    found = []
    if isinstance(value, float) and not math.isfinite(value):
        found.append(prefix or '$')
    elif isinstance(value, dict):
        for key, item in value.items():
            found += nonfinite_paths(item, f'{prefix}.{key}' if prefix else str(key))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            found += nonfinite_paths(item, f'{prefix}[{i}]')
    return found


def write_json(path, value, *, indent=2) -> dict:
    """Atomically publish JSON. Returns {bytes, sha256, null_reasons}."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reasons = {p: 'non_finite_number' for p in nonfinite_paths(value)}
    payload = jsonable(value)
    if reasons and isinstance(payload, dict):
        payload = dict(payload, _null_reasons={**payload.get('_null_reasons', {}), **reasons})
    text = json.dumps(payload, indent=indent, allow_nan=False, ensure_ascii=False, sort_keys=False) + '\n'
    temporary = temporary_path(path)
    try:
        with temporary.open('x', encoding='utf8') as stream:
            stream.write(text)
    except OSError as exc:
        raise PersistenceError(f'Cannot write {path}: {exc}') from exc
    size = publish(temporary, path)             # fsyncs the bytes before the rename
    return dict(bytes=size, sha256=hashlib.sha256(text.encode('utf8')).hexdigest(), null_reasons=reasons)


_MISSING = object()


def read_json(path, default=_MISSING):
    """Read JSON. With `default` (None included) a missing file returns it; otherwise a missing file
    is retried briefly (stale 9p directory entries) and then raised."""
    path = Path(path)
    attempts = 1 if default is not _MISSING else 4
    for attempt in range(attempts):
        try:
            return json.loads(path.read_text(encoding='utf8'))
        except FileNotFoundError:
            if attempt + 1 < attempts:
                time.sleep(0.02 * (attempt + 1))
    if default is not _MISSING:
        return default
    raise FileNotFoundError(path)


class JsonlAppender:
    """Append-only JSONL with one fsync per record (the durable acknowledgement boundary).

    A torn final line from a crash is ignored by ``read_jsonl``; complete lines are never
    rewritten, so recovery cannot lose or duplicate an acknowledged record.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open('a', encoding='utf8')
        self.bytes_written = 0

    def append(self, record) -> None:
        line = json.dumps(jsonable(record), allow_nan=False, ensure_ascii=False, separators=(',', ':')) + '\n'
        try:
            self._stream.write(line)
            self._stream.flush()
            os.fsync(self._stream.fileno())
        except OSError as exc:
            raise PersistenceError(f'Cannot append to {self.path}: {exc}') from exc
        self.bytes_written += len(line.encode('utf8'))

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open('r', encoding='utf8') as stream:
        for line in stream:
            if not line.endswith('\n'):
                break            # torn tail from an interrupted append: not acknowledged
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                break
    return records


def read_jsonl_tail(path, limit, *, block_size=65536):
    """Newest complete log records, without scanning the journal's entire history.

    Display only: skip malformed log lines and an unfinished final line. Recovery still
    uses read_jsonl, which stops at the first malformed record in the journal.
    """
    if limit <= 0:
        return []
    try:
        stream = Path(path).open('rb')
    except FileNotFoundError:
        return []
    records, pending, at_end = [], b'', True

    def take(line):
        if line.strip():
            try:
                records.append(json.loads(line))
            except (ValueError, UnicodeError):
                pass

    with stream:
        position = stream.seek(0, os.SEEK_END)
        while position and len(records) < limit:
            size = min(position, block_size)
            position -= size
            stream.seek(position)
            pieces = (stream.read(size) + pending).split(b'\n')
            pending = pieces.pop(0)
            if at_end and pieces:
                pieces.pop()                         # bytes after the final newline are not a committed record
                at_end = False
            for line in reversed(pieces):
                take(line)
                if len(records) == limit:
                    break
        if not position and not at_end and len(records) < limit:
            take(pending)
    return records[::-1]


def remove_registered_temporaries(directory) -> list[str]:
    """Delete only this package's own temporary files. Never models or primary data."""
    removed = []
    directory = Path(directory)
    if not directory.exists():
        return removed
    for path in directory.rglob(f'*{TEMP_MARKER}*'):
        if path.is_file() and not path.is_symlink():
            path.unlink()
            removed.append(str(path))
    return removed
