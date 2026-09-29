"""Shared HTTP responses, circuit loading and agent settings."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from urllib.parse import quote
import zipfile
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from .. import agents, runs, tasks
from ..agents import AgentError, AgentSettings
from ..agents import catalog as agent_catalog
from ..security import redact
from ..validation import validate


KEEPALIVE_SECONDS = 10.0        # a live agent answer sends a comment line when it has nothing else: a page that left is noticed

def compatibility_unchecked(exc) -> dict:
    """The configuration on the page does not compile, so a saved model cannot be compared with it YET. Said in plain
    words for the "RL model to load" block; the developer text stays available under "Technical details"."""
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
    """Prune excluded directories before touching their files. Return one stat per included file."""
    root = Path(root)
    entries = []
    for directory, dirs, files in os.walk(root):
        base = Path(directory)
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not (base == root and d in exclude_roots)]
        for name in files:
            path = base / name
            try:
                info = path.stat()
            except FileNotFoundError:                 # a worker may prune a file while the directory is listed
                continue
            if stat.S_ISREG(info.st_mode):
                entries.append((path, path.relative_to(root).as_posix(), info))
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


def sse(kind: str, data) -> str:
    """One Server-Sent Event. json.dumps escapes every line break, so `data` is always a single line."""
    return f"event: {kind}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


def live_answer(request, provider, finish, done=None, outcome=None):
    """The agent's answer as Server-Sent Events (status record 7.48): `progress` while it works (agents/live.py), then ONE
    `result` (the proposal, exactly as the JSON answer) or ONE `error` (exactly as the 409 detail). The agent runs on a
    thread of its own. If the page goes away first, the request is cancelled: nobody would see the answer. `done` is
    called once the agent is finished, however it ended (the request's tools are closed with it). `outcome` says what the
    request's tools did, so a FAILURE can say it too - a failed request may already have written the working copy."""
    async def events():
        loop, inbox = asyncio.get_running_loop(), asyncio.Queue()

        def post(kind, data):
            try:
                loop.call_soon_threadsafe(inbox.put_nowait, (kind, data))
            except RuntimeError:                  # the event loop is gone: the server is stopping
                pass

        def work():
            try:
                post('result', finish(provider.propose(request, on_event=lambda event: post('progress', event))))
            except AgentError as exc:
                post('error', dict(exc.as_dict(), configuration_unchanged=True, **(outcome() if outcome else {})))
            except Exception as exc:              # the JSON answer would be an HTTP 500; a stream must still end with a verdict
                post('error', dict(code='internal_error', meaning='The workbench failed while handling the reply.',
                                   detail=redact(f'{type(exc).__name__}: {exc}', 1000), configuration_unchanged=True,
                                   **(outcome() if outcome else {})))
            finally:
                if done is not None:
                    done()
        threading.Thread(target=work, name=f'agent-{request.request_id[:8]}', daemon=True).start()
        finished = False
        try:
            while True:
                try:
                    kind, data = await asyncio.wait_for(inbox.get(), KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ': working\n\n'
                    continue
                yield sse(kind, data)
                if kind != 'progress':
                    finished = True
                    return
        finally:
            if not finished:
                agents.REGISTRY.cancel(request.request_id)
    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


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
                fail(409, exc, code=code)
        fail(422 if isinstance(exc, (KeyError, ValueError)) else 502, exc)


def load_runtime(config, *, allow_real=False):
    try:
        return tasks.load_task(config.circuit, allow_real=allow_real, profile_id=config.run.connection_profile_id), None
    except tasks.TaskBlocked as exc:
        return None, dict(blocker=str(exc), interface_contract=exc.contract)
    except Exception as exc:
        return None, dict(blocker=redact(f'{type(exc).__name__}: {exc}', 1000), interface_contract=None)


def validate_loaded(config, runtime, *, roots=None):
    """Static validation against the loaded circuit, the SAME way for the page, the start checklist, the settings
    review and an applied proposal. A cell read from Virtuoso that has no task yet (a native draft) provides metrics
    nobody knows: they are not checked - an empty list reported every probe as `metric_not_provided` in the agent's
    checklist while the page showed none."""
    draft = runtime is not None and bool(runtime.circuit.get('native_draft'))
    report = validate(config, graph=None if runtime is None else runtime.base_graph,
                      provided_metrics=None if runtime is None or draft else set(runtime.provided_metrics))
    if config.run.conditions.policy != 'off' and not report.blocks_run:
        from ..reachability import check
        evidence = check(config, roots=roots)
        report.facts['corner_reachability'] = evidence
        if evidence and evidence['warning']:
            report.add('warning', 'corner_reachability', 'run.conditions', evidence['warning'])
    return report


def agent_settings() -> AgentSettings:
    saved = runs.load_settings().get('agent') or {}
    saved['provider'] = agents.default_provider_name(saved.get('provider'))
    saved['allowed_tools'] = tuple(saved.get('allowed_tools') or ())
    # The two CLIs take different effort levels. A level kept from the other provider (or a hand-edited file)
    # means "the CLI's default" rather than an error that would take the whole Agent tab down.
    if saved.get('effort') not in agent_catalog.efforts_for(saved['provider']):
        saved['effort'] = None
    # A request has no time limit (status record 7.48): the page shows it working and "Cancel request" stops it.
    # A limit kept in the file from before (300 s was the default) is ignored.
    saved.pop('timeout_seconds', None)
    return AgentSettings(**saved).validate()
