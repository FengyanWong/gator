"""Comparison validation hashes synthetic inputs in bounded reads, without caching or changing refusals."""
import hashlib
from pathlib import Path

import pytest

from gator_workbench import validation
from helpers import make_config


@pytest.mark.parametrize('field', ['initial_designs', 'archive'])
def test_comparison_hashes_all_chunks_and_rechecks_changed_or_missing_inputs(tmp_path, monkeypatch, field):
    # Validating the pinned identity does not parse the payload; no run or search is started by this test.
    root = tmp_path / 'mock'
    root.mkdir()
    first = root / 'initial.json'
    first.write_bytes(b'{"origin":"synthetic"}')
    path = first if field == 'initial_designs' else root / 'archive.json'
    payload = b'synthetic comparison bytes\n' * 125000 + b'end'
    path.write_bytes(payload)
    pinned = hashlib.sha256(payload).hexdigest()
    block = dict(initial_designs=str(first), initial_designs_sha256=hashlib.sha256(first.read_bytes()).hexdigest())
    if field == 'archive':
        block.update(archive=str(path), archive_sha256=pinned)
    config = make_config(tmp_path, run=dict(optimizer='turbo_archive', comparison=block))
    original_open = Path.open
    reads = []

    class BoundedRead:
        def __init__(self, stream, source):
            self.stream, self.source = stream, source

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size=-1):
            assert 0 < size <= 1 << 20, 'Validation must not allocate a whole archive to hash it'
            data = self.stream.read(size)
            reads.append((self.source, size, len(data)))
            return data

    def open_bounded(source, mode='r', *args, **kwargs):
        stream = original_open(source, mode, *args, **kwargs)
        return BoundedRead(stream, source) if source in (first, path) and mode == 'rb' else stream

    def inspect():
        report = validation.Report()
        validation._comparison_rules(config, report)
        return [issue.as_dict() for issue in report.issues if issue.code.startswith('comparison_file_')]

    monkeypatch.setattr(Path, 'open', open_bounded)
    assert inspect() == []
    own = [length for source, _, length in reads if source == path]
    assert sum(own) == len(payload) and len(own) >= 4 and own[-1] == 0
    # A same-length change in the last chunk must be checked again; no cached digest may let it through.
    changed = payload[:-1] + b'!'
    path.write_bytes(changed)
    changed_hash = hashlib.sha256(changed).hexdigest()
    reads.clear()
    assert inspect() == [dict(level='blocker', code='comparison_file_not_pinned', path=f'run.comparison.{field}',
                             message=f'{path} is not the file this run pins: its sha256 is {changed_hash[:12]}..., '
                                     f'the configuration names {pinned[:12]}...')]
    assert sum(length for source, _, length in reads if source == path) == len(changed)
    path.unlink()
    with pytest.raises(OSError) as missing:
        original_open(path, 'rb')
    assert inspect() == [dict(level='blocker', code='comparison_file_missing', path=f'run.comparison.{field}',
                             message=f'{path} cannot be read: {missing.value}')]
