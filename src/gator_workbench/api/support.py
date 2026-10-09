"""Shared HTTP responses and circuit loading."""
from __future__ import annotations
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import quote
import zipfile
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from .. import runs, tasks
from ..reachability import check
from ..security import redact
from ..validation import validate


def compatibility_unchecked(exc) -> dict:
    """The configuration on the page does not compile, so a saved model cannot be compared with it YET. Said in plain
    words for the saved model's check in the RL model window; the developer text stays available under "Technical details"."""
    import re
    text = str(exc)
    row = re.fullmatch(r'(.+): bounds are required', text)
    unresolved = re.fullmatch(r'(.+): (.+) is unresolved', text)
    if row:
        what = (f'Parameter row "{row.group(1)}" is set to be optimized but has no lower and no upper bound. Fill in both '
                'bounds in the Parameters table, or untick "optimize" for that row.')
    elif unresolved:
        what = (f'Parameter row "{unresolved.group(1)}" points at {unresolved.group(2)}, and the loaded circuit has no usable '
                'value there. Correct the instance or parameter name of that row in the Parameters table.')
    else:
        what = 'The Parameters / Targets tables on this page cannot be turned into a task yet.'
    return dict(title='Not compared with your configuration yet: the configuration on this page is incomplete.', what=what,
                note='This says nothing about the saved model. Its facts, its network structure and its circuit graph view '
                     'are unaffected; the comparison appears as soon as the configuration is complete. The blocking '
                     'issues in the header list the same problem.',
                technical=redact(f'{type(exc).__name__}: {text}', 500))


def attachment(name: str) -> dict:
    """Content-Disposition of a download. The browser saves the file under this name."""
    encoded = quote(name)
    return {'Content-Disposition': f'attachment; filename="{name}"' if encoded == name
            else f"attachment; filename*=utf-8''{encoded}"}


class _ArchiveResponse(StreamingResponse):
    """Own the spool even when a client disconnects before the iterator starts."""
    def __init__(self, stream, name):
        self.stream = stream
        size = stream.tell()
        stream.seek(0)
        super().__init__(iter(lambda: stream.read(1 << 20), b''), media_type='application/zip',
                         headers={**attachment(name), 'Content-Length': str(size)})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()


def zip_download(members, name: str):
    """Bounded-memory ZIP download; large archives spill to an automatically deleted temporary file."""
    stream = tempfile.SpooledTemporaryFile(max_size=1 << 20, mode='w+b')
    try:
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item, inside in members:
                archive.write(item, inside)
        return _ArchiveResponse(stream, name)
    except BaseException:
        stream.close()
        raise


def run_files(root, *, exclude_roots=(), exclude_dirs=()):
    """Prune excluded directories before touching their files. Return one stat per included file. The stats go many at
    a time (runs.read_many, record 7.279): one by one, a run's ~760 files took 3.6 s on the 9p-mounted D: drive."""
    root = Path(root)
    paths = []
    for directory, dirs, files in os.walk(root):
        base = Path(directory)
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not (base == root and d in exclude_roots)]
        paths += [base / name for name in files]

    def stat_of(path):
        try:
            return path.stat()
        except FileNotFoundError:                     # a worker may prune a file while the directory is listed
            return None
    entries = [(path, path.relative_to(root).as_posix(), info) for path, info in zip(paths, runs.read_many(stat_of, paths))
               if info is not None and stat.S_ISREG(info.st_mode)]
    return sorted(entries, key=lambda entry: entry[1])


def file_snapshot(path: Path, chunk_size: int = 1 << 20):
    """(size, chunks): exactly the bytes `path` holds now, however much is appended while they are sent.

    A live run keeps appending to its logs. FileResponse announces the size first and then reads to the end of the
    file, so a file that grew in between breaks the transfer. A JSONL snapshot ends on its last complete line."""
    stream = Path(path).open('rb')
    try:
        size = os.fstat(stream.fileno()).st_size
        if Path(path).suffix == '.jsonl':
            while size:                                 # a torn last line is not part of the record (see read_jsonl)
                start = max(0, size - 65536)
                stream.seek(start)
                newline = stream.read(size - start).rfind(b'\n')
                if newline >= 0 or not start:
                    size = start + newline + 1
                    break
                size = start
            stream.seek(0)
    except BaseException:
        stream.close()
        raise

    def chunks():
        with stream:
            remaining = size
            while remaining:
                block = stream.read(min(chunk_size, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
    return size, chunks()


def fail(status, message, **extra):
    raise HTTPException(status, detail=dict(message=redact(str(message), 2000), **extra))


def _bridge_call(action, *refusals):
    """A request that goes through the connection gate to Virtuoso. A blocked gate is a 409 carrying the gate; each
    (exception classes, code) of `refusals`, in order, a 409 with that code; a wrong name or value a 422; anything
    else a 502."""
    try:
        return action()
    except PermissionError as exc:
        raise HTTPException(409, detail=dict(message=str(exc), gate=getattr(exc, 'gate', None)))
    except Exception as exc:
        for kinds, code in refusals:
            if isinstance(exc, kinds):
                fail(409, exc, code=code, **getattr(exc, 'detail_extra', {}))      # what the page needs to ask (record 7.203)
        fail(422 if isinstance(exc, (KeyError, ValueError)) else 502, exc)


def load_runtime(config, *, allow_real=False):
    try:
        if allow_real:
            return tasks.load_task(config.circuit, allow_real=True, profile_id=config.run.connection_profile_id), None
        # The page's loads - validation, the task, Matched devices, the saved-model check, the checklist: a saved task is kept
        # while its files are unchanged (tasks.load_task_view, review of 2026-10-01).
        return tasks.load_task_view(config.circuit, profile_id=config.run.connection_profile_id), None
    except tasks.TaskBlocked as exc:
        return None, dict(blocker=str(exc), interface_contract=exc.contract)
    except Exception as exc:
        return None, dict(blocker=redact(f'{type(exc).__name__}: {exc}', 1000), interface_contract=None)


def validate_loaded(config, runtime, *, roots=None, reachability=True, rows_from=None):
    """Static validation against the loaded circuit, the SAME way for the page and the start checklist. A cell read
    from Virtuoso that has no task yet (a native draft) provides metrics nobody knows: they are not checked - an empty
    list reported every probe as `metric_not_provided` in the checklist while the page showed none. `reachability=False` leaves out the corner reachability evidence, a warning
    that reads recorded runs: for a caller that keeps only the errors and blockers."""
    draft = runtime is not None and bool(runtime.circuit.get('native_draft'))
    report = validate(config, graph=None if runtime is None else runtime.base_graph,
                      provided_metrics=None if runtime is None or draft else set(runtime.provided_metrics), rows_from=rows_from)
    if reachability and config.run.conditions.policy != 'off' and not report.blocks_run:
        try:
            evidence = check(config, roots=roots)
        except Exception:                   # recorded evidence for a warning: it never fails the validation itself
            evidence = None
        report.facts['corner_reachability'] = evidence
        if evidence and evidence['warning']:
            report.add('warning', 'corner_reachability', 'run.conditions', evidence['warning'])
    return report
