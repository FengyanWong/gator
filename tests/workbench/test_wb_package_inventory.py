"""Package inventories avoid unused metadata reads while ZIP creation still sees current files."""
import io
import os
from pathlib import Path
import threading
import zipfile

import pytest

from gator_workbench.api import support

OPTIONS = dict(exclude_roots=('work', 'control', 'waveforms', 'checkpoints'), exclude_dirs=('_quarantine',))


def _files(root):
    """Create a deterministic synthetic run tree containing included and excluded package files."""
    contents = {'run_manifest.json': b'{"origin":"synthetic","provenance":"mock"}',
                'logs/events.jsonl': b'{"origin":"synthetic","event":"saved"}\n' * 300,
                'logs/errors.jsonl': b'', 'exports/measurements.csv': b'name,value\nsynthetic,0.5\n' * 100,
                'data/work/kept.txt': b'nested work is included', 'data/\u03bc.txt': '\u03bc synthetic'.encode(),
                'work/deep/omitted.txt': b'excluded', 'control/omitted.json': b'{}',
                'waveforms/omitted.bin': b'excluded', 'checkpoints/omitted.pt': b'excluded',
                'data/_quarantine/omitted.parquet': b'excluded'}
    for name, content in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o640)
        os.utime(path, (1780000000, 1780000000))
    return contents


def _old_members(root):
    """Return package members using the original metadata-reading inventory."""
    return [(path, relative) for path, relative, _ in support.run_files(root, **OPTIONS)]


def _packed(members):
    """Read a complete fixture ZIP response and close its spool after checking its length."""
    response = support.zip_download(members, 'synthetic.zip')
    try:
        packed = response.stream.read()
        assert len(packed) == int(response.headers['content-length'])
        return packed
    finally:
        response.stream.close()


def test_static_package_members_and_complete_zip_bytes_match(tmp_path):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    import pyarrow as pa
    import pyarrow.parquet as pq
    parquet = root / 'data' / 'part-0.parquet'
    pq.write_table(pa.table({'name': ['synthetic'] * 64, 'value': list(range(64))}), parquet, compression='zstd')
    os.utime(parquet, (1780000000, 1780000000))
    expected = _old_members(root)
    actual = support.package_files(root, **OPTIONS)
    assert actual == expected
    before, after = _packed(expected), _packed(actual)
    assert after == before
    with zipfile.ZipFile(io.BytesIO(before)) as old, zipfile.ZipFile(io.BytesIO(after)) as new:
        assert new.testzip() is None
        for was, now in zip(old.infolist(), new.infolist()):
            assert all(getattr(was, field) == getattr(now, field) for field in (
                'filename', 'date_time', 'file_size', 'compress_size', 'CRC', 'compress_type', 'external_attr',
                'flag_bits', 'create_system', 'create_version', 'extract_version'))
            assert old.read(was) == new.read(now)


def test_directory_exclusions_are_pruned_before_scanning(tmp_path, monkeypatch):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    visited, scan = [], os.scandir

    def tracked(path):
        """Record directories visited by the package inventory."""
        visited.append(Path(path))
        return scan(path)

    monkeypatch.setattr(os, 'scandir', tracked)
    names = [name for _, name in support.package_files(root, **OPTIONS)]
    assert 'data/work/kept.txt' in names
    for name in (*OPTIONS['exclude_roots'], 'data/_quarantine'):
        assert root / name not in visited


def test_regular_file_links_follow_targets_and_directory_or_broken_links_are_omitted(tmp_path):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    (root / 'linked.txt').symlink_to('data/work/kept.txt')
    (root / 'directory-link').symlink_to('data', target_is_directory=True)
    (root / 'broken-link').symlink_to('missing')
    expected = _old_members(root)
    actual = support.package_files(root, **OPTIONS)
    assert actual == expected
    names = [name for _, name in actual]
    assert 'linked.txt' in names and 'directory-link' not in names and 'broken-link' not in names
    assert _packed(actual) == _packed(expected)


def test_directory_replaced_by_a_sibling_scan_is_not_followed(tmp_path, monkeypatch):
    scan = os.scandir
    results = []
    for name, inventory in [('old', _old_members), ('new', lambda root: support.package_files(root, **OPTIONS))]:
        root = tmp_path / 'mock' / name
        (root / 'first').mkdir(parents=True)
        (root / 'first/inside.txt').write_text('synthetic included file')
        (root / 'second').mkdir()
        outside = tmp_path / 'mock' / f'{name}-outside'
        outside.mkdir()
        (outside / 'marker.txt').write_text('synthetic external marker must not be included')
        visited = []

        class OrderedScan:
            """A name-sorted directory iterator that makes the replacement race reproducible."""
            def __init__(self, path):
                with scan(path) as entries:
                    self.entries = iter(sorted(entries, key=lambda entry: entry.name))

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return self

            def __next__(self):
                return next(self.entries)

        def swapping_scan(path):
            """Replace an unvisited sibling directory with an external link during traversal."""
            path = Path(path)
            visited.append(path)
            if path == root:
                return OrderedScan(path)
            if path == root / 'first':
                (root / 'second').rmdir()
                (root / 'second').symlink_to(outside, target_is_directory=True)
            return scan(path)

        with monkeypatch.context() as patch:
            patch.setattr(os, 'scandir', swapping_scan)
            results.append([relative for _, relative in inventory(root)])
        assert root / 'second' not in visited
    assert results == [['first/inside.txt'], ['first/inside.txt']]


def test_an_explicit_root_symlink_still_follows_the_root(tmp_path):
    actual = tmp_path / 'mock' / 'actual'
    _files(actual)
    linked = tmp_path / 'mock' / 'linked'
    linked.symlink_to(actual, target_is_directory=True)
    assert support.package_files(linked, **OPTIONS) == _old_members(linked)


def test_special_files_are_never_opened_or_packed(tmp_path):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    os.mkfifo(root / 'pipe')
    (root / 'linked-pipe').symlink_to('pipe')
    expected = _old_members(root)
    actual = support.package_files(root, **OPTIONS)
    assert actual == expected
    assert not {'pipe', 'linked-pipe'} & {name for _, name in actual}
    assert _packed(actual) == _packed(expected)


@pytest.mark.parametrize('change', ['append', 'replace'])
def test_packing_uses_fresh_metadata_and_contents_after_inventory(tmp_path, change):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    before = _old_members(root)
    members = support.package_files(root, **OPTIONS)
    path = root / 'logs/events.jsonl'
    if change == 'append':
        with path.open('ab') as stream:
            stream.write(b'{"origin":"synthetic","event":"newer"}\n' * 1000)
    else:
        replacement = root / 'replacement'
        replacement.write_bytes(b'{"origin":"synthetic","event":"replaced"}\n')
        replacement.replace(path)
    path.chmod(0o600)
    os.utime(path, (1780000120, 1780000120))
    packed = _packed(members)
    assert packed == _packed(before)
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        info = archive.getinfo('logs/events.jsonl')
        fresh = zipfile.ZipInfo.from_file(path, 'logs/events.jsonl')
        assert archive.read(info) == path.read_bytes()
        assert info.file_size == fresh.file_size and info.date_time == fresh.date_time
        assert info.external_attr == fresh.external_attr


def test_disappearance_after_inventory_keeps_build_failure_and_spool_cleanup(tmp_path, monkeypatch):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    before, members = _old_members(root), support.package_files(root, **OPTIONS)
    (root / 'logs/events.jsonl').unlink()
    spools, make = [], support.tempfile.SpooledTemporaryFile

    def tracked(**kwargs):
        """Retain created ZIP spools so failure cleanup can be checked."""
        spool = make(**kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(support.tempfile, 'SpooledTemporaryFile', tracked)
    for inventory in (before, members):
        with pytest.raises(FileNotFoundError):
            support.zip_download(inventory, 'synthetic.zip')
    assert len(spools) == 2 and all(spool.closed for spool in spools)


def test_unreadable_directory_matches_walk(tmp_path, monkeypatch):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    scan = os.scandir

    def blocked(path):
        """Refuse the fixture log directory while allowing all other scans."""
        if Path(path) == root / 'logs':
            raise PermissionError('synthetic unreadable directory')
        return scan(path)

    monkeypatch.setattr(os, 'scandir', blocked)
    assert support.package_files(root, **OPTIONS) == _old_members(root)


@pytest.mark.parametrize('failure', [FileNotFoundError, PermissionError])
def test_disappeared_entry_is_skipped_and_other_file_errors_propagate(tmp_path, monkeypatch, failure):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    scan = os.scandir

    class Entry:
        """A directory entry that injects a chosen failure when classifying the events log."""
        def __init__(self, entry):
            self.entry, self.name, self.path = entry, entry.name, entry.path

        def is_dir(self):
            return self.entry.is_dir()

        def is_file(self):
            """Raise the selected classification failure for the events log only."""
            if self.name == 'events.jsonl':
                raise failure('synthetic entry classification failure')
            return self.entry.is_file()

    class Scan:
        """A real directory scan yielding entries with injectable classification failures."""
        def __init__(self, path):
            self.entries = scan(path)

        def __enter__(self):
            self.entries.__enter__()
            return self

        def __exit__(self, *args):
            return self.entries.__exit__(*args)

        def __iter__(self):
            return self

        def __next__(self):
            return Entry(next(self.entries))

    monkeypatch.setattr(os, 'scandir', Scan)
    if failure is FileNotFoundError:
        assert 'logs/events.jsonl' not in {name for _, name in support.package_files(root, **OPTIONS)}
    else:
        with pytest.raises(PermissionError, match='synthetic entry classification failure'):
            support.package_files(root, **OPTIONS)


def test_regular_members_remove_the_redundant_explicit_stat_pass(tmp_path, monkeypatch):
    root = tmp_path / 'mock' / 'archive'
    _files(root)
    paths = {path for path, _ in _old_members(root)}
    calls, actual_stat, actual_path_stat = [], os.stat, Path.stat
    inside_path_stat = threading.local()

    def tracked(path, *args, **kwargs):
        """Count direct metadata calls for package members without double-counting Path.stat."""
        if not getattr(inside_path_stat, 'active', False) and not isinstance(path, int) and Path(path) in paths:
            calls.append(Path(path))
        return actual_stat(path, *args, **kwargs)

    def path_stat(path, *args, **kwargs):
        """Count package-member Path.stat calls and distinguish their underlying system calls."""
        if path in paths:
            calls.append(path)
        inside_path_stat.active = True
        try:
            return actual_path_stat(path, *args, **kwargs)
        finally:
            inside_path_stat.active = False

    monkeypatch.setattr(os, 'stat', tracked)
    monkeypatch.setattr(Path, 'stat', path_stat)     # Python3.10 pathlib retains its own cached stat accessor.
    old_members = _old_members(root)
    assert len(calls) == len(paths)
    calls.clear()
    new_members = support.package_files(root, **OPTIONS)
    assert new_members == old_members and calls == []
    _packed(new_members)
    assert len(calls) == len(paths)                 # ZipFile.write still stats every file just before packing.
    # This counts explicit Python stat calls, not DirEntry's internal fallback on links or DT_UNKNOWN filesystems.


def test_missing_or_empty_root_has_no_package_members(tmp_path):
    missing = tmp_path / 'mock' / 'missing'
    assert support.package_files(missing, **OPTIONS) == _old_members(missing) == []
    missing.mkdir(parents=True)
    assert support.package_files(missing, **OPTIONS) == _old_members(missing) == []
