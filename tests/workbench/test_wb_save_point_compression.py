"""Record 7.284: save points are written compressed - training_state.pt's zip entries deflated, each byte-identical to
what torch.save wrote, read by torch.load as before - and a one-time pass compresses the save points written before,
checking every original against its recorded checksum first and every entry after."""
import dataclasses
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest
import torch

from gator_workbench import checkpoints, cli, save_point_compression as spc
from gator_workbench.engine import RunLock
from gator_workbench.layout import build_artifact_manifest
from gator_workbench.storage.atomic import read_json, sha256_file, write_json
from helpers import execute, make_config


def payload():
    return dict(weights=torch.arange(12, dtype=torch.float32).reshape(3, 4), names=['a', 'b'] * 50,
                nested=dict(values=[0.5] * 200, flag=True), log_alpha=torch.tensor(-2.0))


def same(a, b):
    """Equal through and through: tensors and arrays element for element (with their types and shapes), dataclasses and
    plain objects field by field, containers item by item."""
    if type(a) is not type(b):
        return False
    if isinstance(a, torch.Tensor):
        return a.dtype == b.dtype and a.shape == b.shape and torch.equal(a, b)
    if isinstance(a, np.ndarray):
        return a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b)
    if isinstance(a, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if dataclasses.is_dataclass(a):
        return all(same(getattr(a, f.name), getattr(b, f.name)) for f in dataclasses.fields(a))
    if hasattr(a, '__dict__'):
        return same(vars(a), vars(b))
    if isinstance(a, float) and a != a:
        return b != b
    return a == b


def test_deflating_keeps_every_entry_and_torch_reads_the_result(tmp_path):
    stored = io.BytesIO()
    torch.save(payload(), stored)
    result = spc.deflate(stored.getvalue(), tmp_path / 'state.pt')
    assert spc.is_deflated(tmp_path / 'state.pt') and not spc.is_deflated(io.BytesIO(stored.getvalue()))
    assert result == dict(bytes=(tmp_path / 'state.pt').stat().st_size, sha256=sha256_file(tmp_path / 'state.pt'))
    with zipfile.ZipFile(io.BytesIO(stored.getvalue())) as before, zipfile.ZipFile(tmp_path / 'state.pt') as after:
        assert [e.filename for e in before.infolist()] == [e.filename for e in after.infolist()]
        assert all(before.read(e.filename) == after.read(e.filename) for e in before.infolist())
    assert same(torch.load(tmp_path / 'state.pt', weights_only=False), payload())


def test_a_difference_after_compression_is_refused_and_nothing_is_left(tmp_path, monkeypatch):
    stored = io.BytesIO()
    torch.save(payload(), stored)
    original = zipfile.ZipFile.writestr

    def altered(self, info, data, *args, **kwargs):          # one entry written with a byte changed
        if isinstance(data, bytes) and data and info.filename.endswith('data.pkl'):
            data = data[:-1] + bytes([data[-1] ^ 1])
        return original(self, info, data, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', altered)
    with pytest.raises(ValueError, match='differs'):
        spc.deflate(stored.getvalue(), tmp_path / 'state.pt')
    assert not (tmp_path / 'state.pt').exists()


def save_points(layout):
    return sorted(p for p in layout.checkpoints.iterdir() if p.is_dir() and p.name.startswith('ckpt-'))


def test_a_run_writes_its_save_points_compressed_and_they_verify(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=12),
                                        output=dict(checkpoint_every_evaluations=4)), tmp_path)
    assert state == 'completed' and save_points(layout)
    for point in save_points(layout):
        assert spc.is_deflated(point / 'training_state.pt') and checkpoints.verify_files(point) == []
        meta = read_json(point / 'metadata.json')
        assert 'compressed_from' not in meta['files']['training_state.pt']       # written so, nothing replaced
        assert set(torch.load(point / 'training_state.pt', weights_only=False)) >= {'actor', 'critics', 'replay', 'run_state'}


def as_written_before(point):
    """Turn a save point into one written before 7.284: training_state.pt as torch.save writes it (stored entries), and
    metadata.json with that file's size and checksum."""
    state = point / 'training_state.pt'
    torch.save(torch.load(state, weights_only=False), state)
    meta = read_json(point / 'metadata.json')
    meta['files']['training_state.pt'] = dict(bytes=state.stat().st_size, sha256=sha256_file(state))
    write_json(point / 'metadata.json', meta)
    assert not spc.is_deflated(state) and checkpoints.verify_files(point) == []
    return torch.load(state, weights_only=False)


def test_the_one_time_pass_compresses_old_save_points_losslessly(tmp_path, capsys):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=12), output=dict(checkpoint_every_evaluations=4)),
                        tmp_path)
    points = save_points(layout)
    contents = {point: as_written_before(point) for point in points}
    sizes = {point: (point / 'training_state.pt').stat().st_size for point in points}
    dry = spc.compress_save_points(tmp_path)
    assert dry['would_compress'] == len(points) and dry['compressed'] == 0
    assert all(not spc.is_deflated(p / 'training_state.pt') for p in points)            # a dry run writes nothing
    capsys.readouterr()
    assert cli.main(['compress-save-points', '--root', str(tmp_path), '--apply']) == 0
    out = capsys.readouterr().out
    totals = json.loads(out[out.index('{\n'):])                       # the lines per save point, then the totals
    assert totals['compressed'] == len(points) and 0 < totals['bytes_after'] < totals['bytes_before']
    assert out.count('compressed ') == len(points)
    for point in points:
        state, entry = point / 'training_state.pt', read_json(point / 'metadata.json')['files']['training_state.pt']
        assert spc.is_deflated(state) and checkpoints.verify_files(point) == []
        assert entry['compressed_from']['bytes'] == sizes[point] and entry['bytes'] == state.stat().st_size
        assert same(torch.load(state, weights_only=False), contents[point])               # nothing lost
    again = spc.compress_save_points(tmp_path, apply=True)
    assert again['already'] == len(points) and again['compressed'] == 0


def test_the_pass_leaves_alone_what_it_cannot_vouch_for(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=8), output=dict(checkpoint_every_evaluations=4)),
                        tmp_path)
    first, *rest = save_points(layout)
    as_written_before(first)
    for point in rest:
        as_written_before(point)
    with (first / 'training_state.pt').open('ab') as stream:                 # not the file its checksum names
        stream.write(b'\0')
    tampered = (first / 'training_state.pt').read_bytes()
    result = spc.compress_save_points(tmp_path, apply=True)
    assert result['skipped'] == 1 and result['problems'][0]['save_point'] == str(first)
    assert (first / 'training_state.pt').read_bytes() == tampered                # never "fixed"
    excluded = spc.compress_save_points(tmp_path, apply=True, exclude=[layout.run_dir.parents[2].name])
    assert excluded['left_alone'] == len(rest) + 1

    lock = RunLock(layout.run_dir / 'control' / 'run.lock')
    lock.acquire()
    try:
        assert {reason for _, reason in spc.save_point_folders(tmp_path)} == {'its run is working'}
    finally:
        lock.release()


def test_a_pass_stopped_between_its_two_writes_still_verifies_and_is_completed(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=8), output=dict(checkpoint_every_evaluations=4)),
                        tmp_path)
    point = save_points(layout)[0]
    content = as_written_before(point)
    state = point / 'training_state.pt'
    original = state.read_bytes()
    assert spc.compress_save_point(point, apply=True)['status'] == 'compressed'
    compressed_meta = read_json(point / 'metadata.json')
    state.write_bytes(original)                         # as if the pass stopped after metadata.json, before the file
    assert checkpoints.verify_files(point) == []          # the original is recorded under compressed_from
    assert spc.compress_save_point(point)['status'] == 'would_compress'
    assert spc.compress_save_point(point, apply=True)['status'] == 'repaired'
    assert read_json(point / 'metadata.json') == compressed_meta and spc.is_deflated(state)
    assert checkpoints.verify_files(point) == [] and same(torch.load(state, weights_only=False), content)


def manifest_rows_match_files(layout):
    """The artifact manifest's rows for every save point's training_state.pt and metadata.json against the files: []
    when each row's size, its checksum (where the row carries one) and the total agree with what is on disk."""
    manifest = read_json(layout.run_dir / 'artifact_manifest.json')
    problems = []
    for row in manifest['files']:
        if row['path'].startswith('checkpoints/') and row['path'].rsplit('/', 1)[1] in spc.REWRITTEN:
            file = layout.run_dir / row['path']
            if row['bytes'] != file.stat().st_size or (row['sha256'] and row['sha256'] != sha256_file(file)):
                problems.append(row['path'])
    if manifest['total_bytes'] != sum(r['bytes'] for r in manifest['files']):
        problems.append('total_bytes')
    return problems


def test_the_pass_refreshes_each_runs_manifest_once_and_a_later_pass_repairs_stale_rows(tmp_path, monkeypatch):
    """Astra's review of 7.284: the workers rewrote the manifest per save point (3 of 4 updates lost), a second pass never
    came back to it, and the rows of the rewritten metadata.json were never refreshed (616 stale checksums, 628 sizes)."""
    layout, _ = execute(make_config(tmp_path, run=dict(max_evaluations=16), output=dict(checkpoint_every_evaluations=4)),
                        tmp_path)
    points = save_points(layout)
    assert len(points) >= 4                                               # four workers on one run: the lost-update case
    for point in points:
        as_written_before(point)
    manifest_file = layout.run_dir / 'artifact_manifest.json'
    build_artifact_manifest(layout, run_id=read_json(manifest_file)['run_id'], final=True)   # describes the old files exactly
    assert manifest_rows_match_files(layout) == []
    writes, original = [], spc.write_json
    monkeypatch.setattr(spc, 'write_json', lambda path, value, **kw: writes.append(Path(path).name) or original(path, value, **kw))
    dry = spc.compress_save_points(tmp_path)
    assert dry['manifests_to_refresh'] == 1 and dry['manifests_refreshed'] == 0 and writes == []
    totals = spc.compress_save_points(tmp_path, apply=True, workers=4)
    assert totals['compressed'] == len(points) and totals['manifests_refreshed'] == 1
    assert totals['manifest_rows_refreshed'] == 2 * len(points) and writes.count('artifact_manifest.json') == 1
    assert manifest_rows_match_files(layout) == []
    manifest = read_json(manifest_file)                   # a manifest an earlier pass left stale (its rows written per save point)
    for row in manifest['files']:
        if row['path'].startswith('checkpoints/') and row['path'].rsplit('/', 1)[1] in spc.REWRITTEN:
            row['bytes'], row['sha256'] = 1, '0' * 64     # a training_state.pt row with a checksum: the one metadata.json records
    manifest['total_bytes'] = 1
    write_json(manifest_file, manifest)
    again = spc.compress_save_points(tmp_path, apply=True)
    assert again['already'] == len(points) and again['manifests_refreshed'] == 1 and again['manifest_rows_refreshed'] == 2 * len(points)
    assert manifest_rows_match_files(layout) == [] and writes.count('artifact_manifest.json') == 2
    assert spc.NOTE in read_json(manifest_file)['notes']
    third = spc.compress_save_points(tmp_path, apply=True)
    assert third['manifests_refreshed'] == 0 and writes.count('artifact_manifest.json') == 2     # right already: not rewritten
