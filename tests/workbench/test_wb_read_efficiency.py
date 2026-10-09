"""Bounded display reads and exports; execution integrity checks remain fresh."""
import asyncio
import io
import json
import os
from pathlib import Path
import zipfile

import pytest

from gator_workbench import checkpoints as ckpt
from gator_workbench.api import support
from gator_workbench.storage import atomic
import importlib.util
import sys
import time
import datetime as dt
import stat


@pytest.mark.parametrize('block_size', [1, 7, 64, 65536])
@pytest.mark.parametrize('ending', [b'', b'{"unfinished":true}', b'\xe2\x82'])
def test_log_tail_matches_complete_records_across_utf8_boundaries(tmp_path, block_size, ending):
    path = tmp_path / 'events.jsonl'
    rows = [dict(index=i, text='μ電路' * (i + 1)) for i in range(20)]
    path.write_bytes(b'\r\n'.join(json.dumps(row, ensure_ascii=False).encode() for row in rows) + b'\n\n' + ending)
    for limit in (0, 1, 7, 50):
        assert atomic.read_jsonl_tail(path, limit, block_size=block_size) == (rows[-limit:] if limit else [])


def test_log_tail_empty_missing_and_corrupt_lines_do_not_change_recovery(tmp_path):
    path = tmp_path / 'log'
    assert atomic.read_jsonl_tail(path, 10) == []
    for content in (b'', b'{"partial":true}'):
        path.write_bytes(content)
        assert atomic.read_jsonl_tail(path, 10) == []
    path.write_bytes(b'{"i":1}\ninvalid\n{"i":2}\npartial')
    assert atomic.read_jsonl_tail(path, 10) == [{'i': 1}, {'i': 2}]
    with pytest.raises(atomic.PersistenceError, match='line 2'):
        atomic.read_jsonl(path)                     # recovery refuses to hide complete records after corruption


def test_log_tail_io_is_bounded_by_the_requested_window(tmp_path, monkeypatch):
    path = tmp_path / 'events.jsonl'
    path.write_text(''.join(json.dumps(dict(i=i, text='x' * 100)) + '\n' for i in range(10000)))
    opened, real_open = [], Path.open

    class Counted(io.BufferedReader):
        bytes_read = 0

        def read(self, size=-1):
            value = super().read(size)
            self.bytes_read += len(value)
            return value

    def open_file(p, *args, **kwargs):
        if p == path and args == ('rb',):
            stream = Counted(io.FileIO(p, 'r'))
            opened.append(stream)
            return stream
        return real_open(p, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    assert [r['i'] for r in atomic.read_jsonl_tail(path, 200)] == list(range(9800, 10000))
    assert opened[0].bytes_read <= 65536 < path.stat().st_size
    assert opened[0].closed


def test_opening_a_healthy_append_log_does_not_scan_its_history(tmp_path, monkeypatch):
    path = tmp_path / 'events.jsonl'
    path.write_bytes(b'{"event":"complete"}\n' * 100000)
    opened, real_open = [], Path.open

    class Counted(io.BufferedRandom):
        bytes_read = 0

        def read(self, size=-1):
            value = super().read(size)
            self.bytes_read += len(value)
            return value

    def open_file(p, *args, **kwargs):
        if p == path and args == ('a+b',):
            stream = Counted(io.FileIO(p, 'a+'))
            opened.append(stream)
            return stream
        return real_open(p, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    log = atomic.JsonlAppender(path)
    log.append(dict(event='new'))
    log.close()
    assert opened[0].bytes_read <= 64 < path.stat().st_size
    assert opened[0].closed


def test_file_walk_prunes_work_before_visiting_and_keeps_nested_names(tmp_path, monkeypatch):
    names = ['run_manifest.json', 'data/a.parquet', 'data/work/included.txt', 'data/_quarantine/omit',
             'work/huge/tree/omit', 'waveforms/omit', 'checkpoints/omit', 'control/omit']
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    visited, scan = [], os.scandir

    def scandir(path):
        visited.append(Path(path))
        return scan(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    entries = support.run_files(tmp_path, exclude_roots=('work', 'waveforms', 'checkpoints', 'control'),
                                exclude_dirs=('_quarantine',))
    assert [relative for _, relative, _ in entries] == ['data/a.parquet', 'data/work/included.txt', 'run_manifest.json']
    assert tmp_path / 'work' not in visited and tmp_path / 'data/_quarantine' not in visited


@pytest.mark.parametrize('disconnect', [False, True])
def test_zip_spills_to_disk_streams_large_chunks_and_closes_on_disconnect(tmp_path, disconnect):
    path = tmp_path / 'data.bin'
    original = os.urandom(2 * 1024 * 1024)
    path.write_bytes(original)
    response = support.zip_download([(path, 'data.bin')], 'data.zip')
    assert response.stream._rolled                # bounded to the 1 MiB spool threshold
    chunks = []

    async def send(message):
        if message['type'] == 'http.response.body' and message.get('body'):
            chunks.append(message['body'])
            if disconnect:
                raise OSError('client disconnected')

    async def receive():
        return {'type': 'http.disconnect'}

    async def transfer():
        await response({'type': 'http', 'asgi': {'spec_version': '2.4'}}, receive, send)

    if disconnect:
        from starlette.requests import ClientDisconnect
        with pytest.raises(ClientDisconnect):
            asyncio.run(transfer())
    else:
        asyncio.run(transfer())
        assert len(chunks) == 3 and len(chunks[0]) == 1 << 20
        assert sum(map(len, chunks)) == int(response.headers['content-length'])
        with zipfile.ZipFile(io.BytesIO(b''.join(chunks))) as archive:
            assert archive.namelist() == ['data.bin'] and archive.read('data.bin') == original
    assert response.stream.closed


def test_zip_closes_the_spool_if_building_fails(tmp_path, monkeypatch):
    spool = support.tempfile.SpooledTemporaryFile(max_size=1024)
    monkeypatch.setattr(support.tempfile, 'SpooledTemporaryFile', lambda **kw: spool)
    with pytest.raises(FileNotFoundError):
        support.zip_download([(tmp_path / 'missing', 'missing')], 'data.zip')
    assert spool.closed


def test_display_checksum_cache_invalidates_and_never_serves_execution(tmp_path, monkeypatch):
    directory = tmp_path / 'checkpoints' / 'first'
    directory.mkdir(parents=True)
    data = directory / 'training_state.pt'
    data.write_bytes(b'original')
    fields = ('checkpoint_id', 'kind', 'run_id', 'task_id', 'mode', 'created_utc', 'metadata_version',
              'counters', 'restoration_capability', 'restorable_components', 'missing_components', 'contract')
    meta = dict.fromkeys(fields, 'fixture')
    meta['checkpoint_id'] = 'first'
    meta['files'] = {'training_state.pt': dict(sha256=atomic.sha256_file(data))}
    atomic.write_json(directory / 'metadata.json', meta)
    atomic.write_json(directory.parent / 'latest.json', dict(checkpoint_id='first'))
    reads = []

    def digest(path):
        reads.append(path)
        return atomic.sha256_file(path)

    monkeypatch.setattr(ckpt, 'sha256_file', digest)
    for _ in range(3):
        assert ckpt.describe(tmp_path)['file_problems'] == []
    assert len(reads) == 1
    assert ckpt.verify_files(directory) == []
    assert len(reads) == 2                          # actual loading uses a fresh checksum
    before = data.stat()
    data.write_bytes(b'tampered')                   # same length and restored mtime; ctime still invalidates
    os.utime(data, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert ckpt.describe(tmp_path)['file_problems'] == ['checksum mismatch training_state.pt']
    assert len(reads) == 3
    data.unlink()
    assert ckpt.describe(tmp_path)['file_problems'] == ['missing training_state.pt']
    second = directory.parent / 'second'
    second.mkdir()
    atomic.write_json(second / 'metadata.json', dict(meta, checkpoint_id='second', files={}))
    atomic.write_json(directory.parent / 'latest.json', dict(checkpoint_id='second'))
    assert ckpt.describe(tmp_path)['checkpoint_id'] == 'second'


def test_scalars_do_not_search_for_a_missing_dateutil_per_value():
    import pyarrow as pa
    import gator_workbench.storage.dataset  # noqa: F401 - importing it is what sets the sentinel
    assert 'dateutil' in sys.modules
    if sys.modules['dateutil'] is not None:
        pytest.skip('dateutil is installed here')
    assert importlib.util.find_spec('dateutil') is None
    started = time.perf_counter()
    for value in range(2000):
        pa.scalar(value)                                          # what a parquet filter does with its value
    assert time.perf_counter() - started < 0.5                    # a failed import search per value was ~1 ms


def test_timestamps_do_not_search_for_a_missing_pytz_per_value():
    import importlib.util
    import pyarrow as pa
    import gator_workbench.storage.dataset  # noqa: F401 - importing it is what sets the sentinel
    assert 'pytz' in sys.modules                          # the real package, or None: "not installed", answered at once
    if sys.modules['pytz'] is not None:
        pytest.skip('pytz is installed here')
    assert importlib.util.find_spec('pytz') is None
    column = pa.array([dt.datetime(2026, 9, 22, tzinfo=dt.timezone.utc)] * 2000, type=pa.timestamp('us', tz='UTC'))
    started = time.perf_counter()
    rows = pa.table({'t': column}).to_pylist()
    assert rows[0]['t'].tzinfo is not None and time.perf_counter() - started < 0.5      # was ~1.25 ms per value


def test_a_runs_files_listed_many_at_a_time_are_those_listed_one_by_one(tmp_path):
    for relative in ('run_manifest.json', 'data/evaluations/part-0.parquet', 'data/_quarantine/x.bin', 'work/lane-1/job.json',
                     'logs/events.jsonl', 'checkpoints/ckpt-a/metadata.json'):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text(relative)

    def one_by_one(root, *, exclude_roots=(), exclude_dirs=()):          # run_files before record 7.279
        entries = []
        for directory, dirs, files in os.walk(root):
            base = Path(directory)
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not (base == root and d in exclude_roots)]
            for name in files:
                info = (base / name).stat()
                if stat.S_ISREG(info.st_mode):
                    entries.append((base / name, (base / name).relative_to(root).as_posix(), info))
        return sorted(entries, key=lambda entry: entry[1])
    for options in (dict(), dict(exclude_roots=('work',)), dict(exclude_roots=('work', 'checkpoints'), exclude_dirs=('_quarantine',))):
        assert support.run_files(tmp_path, **options) == one_by_one(tmp_path, **options)
