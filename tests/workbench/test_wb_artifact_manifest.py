"""Artifact inventories keep their integrity records without visiting simulator scratch."""
from collections import Counter
import hashlib
import os
from pathlib import Path

import pytest

from gator_workbench import layout as output
from gator_workbench.storage.atomic import TEMP_MARKER, read_json


@pytest.fixture
def inventory(tmp_path):
    layout = output.RunLayout(tmp_path / 'mock' / 'synthetic-run')
    layout.create()
    kept = {
        'run_manifest.json': b'{"origin":"synthetic","provenance":"mock"}',
        'input_snapshot/.hidden': b'fixture',
        'data/evaluations/part-000001.parquet': b'synthetic published part',
        'data/evaluations/part-000002.parquet': b'synthetic unpublished part',
        'data/_quarantine/old.parquet': b'synthetic quarantine',
        'data/_journal/flushes.jsonl': b'{"parts":{"evaluations":"part-000001.parquet"}}\n',
        'data/_journal/wal.jsonl': b'{}\n',
        'checkpoints/point/metadata.json': b'{}',
        'checkpoints/point/training_state.pt': b'synthetic checkpoint',
        'checkpoints/point/replay_buffer/manifest.json': b'{}',
        'waveforms/kept.raw': b'synthetic waveform',
        'logs/events.jsonl': b'{}\n',
        'control/command.json': b'{}',
        'data/work/retained.txt': b'only the root work directory is excluded',
        'data/retained.lock': b'only control locks are excluded',
        'data/artifact_manifest.json': b'only the root inventory is excluded',
        f'data/folder{TEMP_MARKER}name/retained': b'temporary-looking directory name',
        'a/nested': b'sorts before a-b with pathlib ordering',
        'a-b': b'no extension',
    }
    omitted = {
        'work/lane/job/nested/scratch.raw': b'synthetic scratch',
        'control/run.lock': b'lock',
        'control/nested/worker.lock': b'lock',
        f'data/part{TEMP_MARKER}unfinished.parquet': b'partial',
        'artifact_manifest.json': b'{}',
    }
    for relative, content in (kept | omitted).items():
        path = layout.run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return layout, kept, omitted


@pytest.mark.parametrize('final', [False, True])
def test_inventory_keeps_paths_order_sizes_checksums_and_write_status(inventory, final):
    layout, kept, _ = inventory
    manifest = output.build_artifact_manifest(layout, run_id='synthetic', final=final,
                                             dataset_status={'rows': {'evaluations': 1}}, notes=['fixture'])
    assert manifest['files'] and manifest['final'] is final
    assert manifest['run_id'] == 'synthetic' and manifest['notes'] == ['fixture']
    assert manifest['table_rows'] == {'evaluations': 1}
    assert manifest['relative_to'] == 'run directory (portable)'
    assert manifest['original_environment']['run_dir'] == str(layout.run_dir)
    assert [row['path'] for row in manifest['files']] == [str(p) for p in sorted(map(Path, kept))]
    assert manifest['total_bytes'] == sum(map(len, kept.values()))
    assert read_json(layout.artifact_manifest) == manifest
    for row in manifest['files']:
        name = row['path']
        expected_status = 'final' if final else 'pending'
        if name == 'data/evaluations/part-000001.parquet':
            expected_status = 'final'
        elif name in ('data/evaluations/part-000002.parquet', 'data/_quarantine/old.parquet'):
            expected_status = 'quarantined_unlisted_part'
        assert row['write_status'] == expected_status
        assert row['bytes'] == len(kept[name])
        assert row['format'] == (Path(name).suffix.lstrip('.') or 'none')
        own_checksum = name in ('checkpoints/point/training_state.pt',
                                'checkpoints/point/replay_buffer/manifest.json')
        expected_hash = (hashlib.sha256(kept[name]).hexdigest()
                         if not own_checksum and (final or expected_status == 'final') else None)
        assert row['sha256'] == expected_hash
        assert row['checksum_in'] == ('checkpoints/point/metadata.json' if own_checksum else None)
    purposes = {row['path']: row['purpose'] for row in manifest['files']}
    assert purposes['run_manifest.json'] == 'Identity and provenance of the run'
    assert purposes['a-b'] == 'run file'
    assert purposes['waveforms/kept.raw'] == 'Retained raw simulator output (never rendered)'


def test_scratch_is_never_scanned_and_only_retained_files_are_statted_once(inventory, monkeypatch):
    layout, kept, omitted = inventory
    scanned, stated = [], Counter()
    scan, stat = os.scandir, Path.stat

    def scandir(path):
        path = Path(path)
        assert path != layout.work and layout.work not in path.parents
        scanned.append(path)
        return scan(path)

    def file_stat(path, *args, **kwargs):
        stated[path] += 1
        return stat(path, *args, **kwargs)

    # Keep journal reading and atomic publication out of the inventory's metadata-operation count.
    monkeypatch.setattr(output, '_flushes', lambda _: [{'parts': {'evaluations': 'part-000001.parquet'}}])
    monkeypatch.setattr(output, 'write_json', lambda *_: None)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(Path, 'stat', file_stat)
    output.build_artifact_manifest(layout, run_id='synthetic', final=True)
    assert layout.data / 'work' in scanned
    assert all(stated[layout.run_dir / name] == 1 for name in kept)
    assert all(stated[layout.run_dir / name] == 0 for name in omitted)


def test_file_links_are_kept_but_directory_links_broken_links_and_fifos_are_not(tmp_path):
    layout = output.RunLayout(tmp_path / 'mock' / 'links')
    layout.create()
    target = tmp_path / 'synthetic-target'
    target.write_bytes(b'fixture')
    (layout.run_dir / 'linked.txt').symlink_to(target)
    (layout.run_dir / 'linked-directory').symlink_to(tmp_path, target_is_directory=True)
    (layout.run_dir / 'broken.txt').symlink_to(tmp_path / 'missing')
    os.mkfifo(layout.run_dir / 'pipe')
    manifest = output.build_artifact_manifest(layout, run_id='synthetic', final=True)
    assert [row['path'] for row in manifest['files']] == ['linked.txt']
    assert manifest['files'][0]['sha256'] == hashlib.sha256(b'fixture').hexdigest()


@pytest.mark.parametrize('failure', ['stat', 'checksum'])
def test_file_removed_while_listing_is_skipped(inventory, monkeypatch, failure):
    layout, kept, _ = inventory
    vanished = layout.logs / 'events.jsonl'
    original = Path.stat if failure == 'stat' else output.sha256_file

    def disappearing(path, *args, **kwargs):
        if path == vanished:
            raise FileNotFoundError('synthetic concurrent removal')
        return original(path, *args, **kwargs)

    if failure == 'stat':
        monkeypatch.setattr(Path, 'stat', disappearing)
    else:
        monkeypatch.setattr(output, 'sha256_file', disappearing)
    manifest = output.build_artifact_manifest(layout, run_id='synthetic', final=True)
    assert {row['path'] for row in manifest['files']} == kept.keys() - {'logs/events.jsonl'}
    assert manifest['total_bytes'] == sum(map(len, kept.values())) - len(kept['logs/events.jsonl'])


def test_empty_run_has_empty_inventory_and_unknown_row_counts(tmp_path):
    layout = output.RunLayout(tmp_path / 'mock' / 'empty')
    layout.create()
    manifest = output.build_artifact_manifest(layout, run_id='synthetic', final=False)
    assert manifest['files'] == [] and manifest['total_bytes'] == 0
    assert manifest['table_rows'] is None and manifest['notes'] == []
