"""Display log tails discard uncommitted suffixes without retaining their whole contents."""
import io
import json
import os
from pathlib import Path

import pytest

from gator_workbench.storage import atomic


def _before(path, limit, *, block_size=65536):
    """The previous reader, independent of the production implementation."""
    if limit <= 0:
        return []
    try:
        stream = Path(path).open('rb')
    except FileNotFoundError:
        return []
    records, pending, at_end = [], b'', True

    def take(line):
        """Collect valid nonblank JSON lines while ignoring malformed or undecodable records."""
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
                pieces.pop()
                at_end = False
            for line in reversed(pieces):
                take(line)
                if len(records) == limit:
                    break
        if not position and not at_end and len(records) < limit:
            take(pending)
    return records[::-1]


@pytest.mark.parametrize('block_size', [1, 7, 64, 4096])
@pytest.mark.parametrize('boundary', ['empty', 'one', 'before', 'exact', 'after', 'many'])
def test_suffix_boundaries_preserve_all_complete_json_values(tmp_path, block_size, boundary):
    path = tmp_path / 'mock' / 'events.jsonl'
    path.parent.mkdir()
    values = [None, False, 0, '', [], {}, {'origin': 'synthetic', 'provenance': 'mock', 'text': '\u03bc\u96fb\u8def' * 30}]
    lines = [json.dumps(value, ensure_ascii=False).encode() for value in values]
    complete = b' \r\n' + b'\r\ninvalid\n\xff\xfe\n'.join(lines) + b'\n\n'
    length = {'empty': 0, 'one': 1, 'before': max(0, block_size-1), 'exact': block_size,
              'after': block_size+1, 'many': 4*block_size+5}[boundary]
    path.write_bytes(complete + b'x' * length)
    for limit in (-1, 0, 1, 3, 20):
        expected = _before(path, limit, block_size=block_size)
        assert atomic.read_jsonl_tail(path, limit, block_size=block_size) == expected
        assert expected == (values[-limit:] if limit > 0 else [])


@pytest.mark.parametrize('prefix', [b'', b'{"origin":"synthetic","event":"complete"}\n'])
def test_long_uncommitted_suffix_does_not_form_a_growing_concatenation(tmp_path, monkeypatch, prefix):
    path = tmp_path / 'mock' / 'events.jsonl'
    path.parent.mkdir()
    block_size = 65536
    path.write_bytes(prefix + b'x' * (4 * 1024 * 1024 + 17))
    real_open, opened, concatenations = Path.open, [], []

    class Block(bytes):
        """A byte block that rejects concatenations larger than the bounded-read allowance."""
        def __add__(self, other):
            concatenations.append(len(self) + len(other))
            assert len(self) + len(other) <= 2 * block_size, 'The discarded suffix must not accumulate across reads'
            return super().__add__(other)

    class Reader(io.BufferedReader):
        """A reader that counts bytes and enforces bounded reads using instrumented blocks."""
        bytes_read = 0

        def read(self, size=-1):
            """Return an instrumented block and reject reads exceeding the configured block size."""
            value = super().read(size)
            self.bytes_read += len(value)
            assert size <= block_size
            return Block(value)

    def open_file(file, *args, **kwargs):
        """Wrap the target binary log stream with the instrumented reader."""
        if file == path and args == ('rb',):
            stream = Reader(io.FileIO(path, 'r'))
            opened.append(stream)
            return stream
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    assert atomic.read_jsonl_tail(path, 1, block_size=block_size) == ([json.loads(prefix)] if prefix else [])
    assert opened[0].bytes_read == path.stat().st_size and opened[0].closed
    assert not concatenations or max(concatenations) <= 2 * block_size


def test_large_complete_records_are_returned_and_not_mistaken_for_suffixes(tmp_path):
    path = tmp_path / 'mock' / 'events.jsonl'
    path.parent.mkdir()
    rows = [{'origin': 'synthetic', 'text': '\u03bc' * 100000}, {'origin': 'synthetic', 'last': True}]
    path.write_bytes(b'\n'.join(json.dumps(row, ensure_ascii=False).encode() for row in rows) + b'\n' + b'partial' * 20000)
    for limit in (1, 2, 10):
        assert atomic.read_jsonl_tail(path, limit) == _before(path, limit) == rows[-limit:]


@pytest.mark.parametrize('reader', [atomic.read_jsonl_tail, _before])
def test_appends_after_the_initial_size_are_outside_the_read_snapshot(tmp_path, monkeypatch, reader):
    path = tmp_path / 'mock' / 'events.jsonl'
    path.parent.mkdir()
    first, later = {'origin': 'synthetic', 'at': 'first'}, {'origin': 'synthetic', 'at': 'later'}
    path.write_bytes(json.dumps(first).encode() + b'\npartial')
    real_open = Path.open

    class Reader(io.BufferedReader):
        """A reader that appends a later record after the initial end-of-file seek."""
        appended = False

        def seek(self, offset, whence=os.SEEK_SET):
            """Append the fixture record after the first seek that establishes the original file size."""
            position = super().seek(offset, whence)
            if whence == os.SEEK_END and not self.appended:
                self.appended = True
                with real_open(path, 'ab') as writer:
                    writer.write(b'\n' + json.dumps(later).encode() + b'\n')
            return position

    def open_file(file, *args, **kwargs):
        """Wrap the target log stream with a reader that appends after snapshot selection."""
        return Reader(io.FileIO(path, 'r')) if file == path and args == ('rb',) else real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    assert reader(path, 10, block_size=7) == [first]


@pytest.mark.parametrize('reader', [atomic.read_jsonl_tail, _before])
def test_read_failure_still_propagates_and_closes_the_file(tmp_path, monkeypatch, reader):
    path = tmp_path / 'mock' / 'events.jsonl'
    path.parent.mkdir()
    path.write_bytes(b'x' * 100)
    real_open, opened = Path.open, []

    class Reader(io.BufferedReader):
        """A reader that injects an error on its second read."""
        reads = 0

        def read(self, size=-1):
            """Delegate the first read and inject a fixture failure on the second."""
            self.reads += 1
            if self.reads == 2:
                raise OSError('synthetic read failure')
            return super().read(size)

    def open_file(file, *args, **kwargs):
        """Wrap the target binary log stream with the reader that fails mid-read."""
        if file == path and args == ('rb',):
            stream = Reader(io.FileIO(path, 'r'))
            opened.append(stream)
            return stream
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', open_file)
    with pytest.raises(OSError, match='synthetic read failure'):
        reader(path, 1, block_size=7)
    assert opened[0].closed


def test_missing_files_and_nonpositive_limits_keep_their_previous_answers(tmp_path):
    missing = tmp_path / 'mock' / 'missing.jsonl'
    for limit in (-10, 0, 3):
        assert atomic.read_jsonl_tail(missing, limit) == _before(missing, limit) == []
