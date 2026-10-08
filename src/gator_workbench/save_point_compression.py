"""Save points written compressed, and a one-time pass that compresses the ones written before (record 7.284).

A save point's ``training_state.pt`` is the zip archive ``torch.save`` writes, every entry STORED. The replay inside it -
each stored step with its circuit graph twice - is plain pickle and deflates about three times (41.6 MB -> 14.4 MB in
0.43 s at level 3; on 2026-10-08 save points were 26.2 GB of outputs/' 29 GB). ``torch.load`` reads a deflated archive
as it reads a stored one (torch 2.14: the same weights, random states and replay), so every reader - ``SACLearner.load``,
an older checkout, a queue's frozen runtime - opens a compressed save point unchanged.

Lossless, and shown to be: the new archive has the same entries, in the same order, each with the same bytes - every
entry is read back from the written file and compared with the original before the file is used. ``metadata.json``
records the compressed file's size and SHA-256 (what ``checkpoints.verify_files`` checks); a save point compressed by
the one-time pass keeps the original's size and SHA-256 under ``compressed_from``.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fnmatch
import hashlib
import io
import os
from pathlib import Path
import zipfile

from .storage.atomic import publish, read_json, temporary_path, write_json

LEVEL = 3                   # deflate level: 1 gave 15.5 MB in 0.39 s, 3 gave 14.4 MB in 0.43 s, 6 gave 13.9 MB in 0.82 s
STATE = 'training_state.pt'
RECORD = '7.284'


def is_deflated(archive) -> bool:
    """Whether every entry of the zip archive (a path or a file object) is deflated: a save point already compressed."""
    with zipfile.ZipFile(archive) as opened:
        entries = opened.infolist()
    return bool(entries) and all(e.compress_type == zipfile.ZIP_DEFLATED for e in entries)


def deflate(data: bytes, target) -> dict:
    """Write the torch archive `data` (its bytes) to the new file `target`, every entry deflated, and prove it lossless:
    the same entry names in the same order, each entry's size, CRC and bytes equal to the original's, and the file on
    disk holding exactly the archive checked. Returns {bytes, sha256} of `target`; raises ValueError, leaving no
    `target`, when anything differs. The archive is built in memory and written in one piece: written entry by entry
    (a save point has ~1,500), the 9p-mounted D: drive took 3-5 s more per save point."""
    target = Path(target)
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, 'w') as written:
        for entry in source.infolist():
            copy = zipfile.ZipInfo(entry.filename, date_time=entry.date_time)
            copy.compress_type, copy.external_attr = zipfile.ZIP_DEFLATED, entry.external_attr
            written.writestr(copy, source.read(entry), compresslevel=LEVEL)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(io.BytesIO(archive)) as written:
        before, after = source.infolist(), written.infolist()
        if [e.filename for e in before] != [e.filename for e in after]:
            raise ValueError('the compressed archive does not hold the same entries in the same order')
        for old, new in zip(before, after):
            if (old.file_size, old.CRC) != (new.file_size, new.CRC) or source.read(old) != written.read(new):
                raise ValueError(f'entry {old.filename} differs after compression')
    try:
        with target.open('xb') as stream:
            stream.write(archive)
        if target.read_bytes() != archive:
            raise ValueError(f'{target} does not hold the compressed archive as written')
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return dict(bytes=len(archive), sha256=hashlib.sha256(archive).hexdigest())


def write_compressed(source, destination) -> dict:
    """A save point's training_state.pt, written by the package at `source` (a local temporary file), published
    compressed at `destination`. Returns {bytes, sha256} of `destination`."""
    temporary = temporary_path(Path(destination))
    result = deflate(Path(source).read_bytes(), temporary)
    publish(temporary, Path(destination))
    return result


# ---------------------------------------------------------------------------------- the one-time pass over a folder
def compress_save_point(directory, *, apply=False) -> dict:
    """One save point folder: {status, before?, after?, reason?}, status one of compressed, would_compress, already,
    repaired, skipped. Nothing is written unless `apply`, and never for a file that does not match the checksum its
    metadata.json records (reported, not "fixed")."""
    from .checkpoints import verify_files
    directory = Path(directory)
    state, metadata_file = directory / STATE, directory / 'metadata.json'
    metadata = read_json(metadata_file, default=None)
    entry = metadata.get('files', {}).get(STATE) if isinstance(metadata, dict) else None
    if not state.is_file() or not isinstance(entry, dict) or not entry.get('sha256'):
        return dict(status='skipped', reason='no training_state.pt with a checksum in metadata.json')
    data = state.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    original = (entry.get('compressed_from') or {}).get('sha256')
    if digest == entry['sha256'] and is_deflated(io.BytesIO(data)):
        return dict(status='already', after=len(data))
    interrupted = digest == original       # metadata.json names the compressed file, the original is still in place
    if digest != entry['sha256'] and not interrupted:
        return dict(status='skipped', reason='training_state.pt does not match the checksum its metadata.json records')
    if not apply:
        return dict(status='would_compress', before=len(data))
    temporary = temporary_path(state)
    result = deflate(data, temporary)
    if interrupted and result['sha256'] != entry['sha256']:
        temporary.unlink(missing_ok=True)
        return dict(status='skipped', reason='an interrupted compression could not be completed byte for byte')
    if not interrupted:
        metadata['files'][STATE] = dict(bytes=result['bytes'], sha256=result['sha256'], compressed_from=dict(
            bytes=len(data), sha256=digest, method=f'zip entries deflated at level {LEVEL}, every entry byte-identical',
            record=RECORD, utc=datetime.now(timezone.utc).isoformat()))
        write_json(metadata_file, metadata)
    publish(temporary, state)
    problems = verify_files(directory)
    if problems:
        return dict(status='skipped', reason='written, but the save point does not verify: ' + '; '.join(problems))
    _update_artifact_manifest(directory, len(data), result['bytes'])
    return dict(status='repaired' if interrupted else 'compressed', before=len(data), after=result['bytes'])


def _update_artifact_manifest(directory: Path, before: int, after: int) -> None:
    """The run's artifact_manifest.json lists every file's size (the checksum is in the save point's metadata.json)."""
    path, relative = directory.parent.parent / 'artifact_manifest.json', f'checkpoints/{directory.name}/{STATE}'
    manifest = read_json(path, default=None)
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
        return
    for row in manifest['files']:
        if isinstance(row, dict) and row.get('path') == relative and row.get('bytes') == before:
            row['bytes'] = after
            if isinstance(manifest.get('total_bytes'), int):
                manifest['total_bytes'] -= before - after
            note = (f"Record {RECORD}: a save point's training_state.pt may have been compressed afterwards (its zip "
                    "entries deflated, every entry byte-identical); its checksum is in the save point's metadata.json.")
            if isinstance(manifest.get('notes'), list) and note not in manifest['notes']:
                manifest['notes'].append(note)
            write_json(path, manifest)
            return


def save_point_folders(root, *, exclude=()) -> list:
    """[(save point folder, why it is left alone or None)] for every save point of every run under `root`: a run that
    is working (a worker holds its lock), lies in an excluded experiment folder, or is a link to a folder elsewhere is
    left alone."""
    from .engine import RunLock
    from .layout import find_runs
    from .paths import MOCK_SUBDIR
    root, found = Path(root).resolve(), []
    for run_dir in find_runs(root) + find_runs(root / MOCK_SUBDIR):      # the run list's two places (runs.list_runs)
        reason = None
        if any(fnmatch.fnmatch(run_dir.parents[2].name, pattern) for pattern in exclude):
            reason = 'excluded'
        elif root not in run_dir.resolve().parents:
            reason = 'a link to a run elsewhere'
        elif RunLock.held(run_dir / 'control' / 'run.lock'):
            reason = 'its run is working'
        try:
            names = sorted(n for n in os.listdir(run_dir / 'checkpoints') if n.startswith('ckpt-'))
        except OSError:
            continue
        found += [(run_dir / 'checkpoints' / name, reason) for name in names]
    return found


def compress_save_points(root, *, apply=False, exclude=(), workers=4, progress=None) -> dict:
    """The one-time pass over every save point under `root`, a dry run unless `apply`. Returns the counts, the bytes the
    compressed save points had before and have now, and every save point skipped with its reason."""
    folders = save_point_folders(root, exclude=exclude)
    totals = dict(root=str(root), apply=bool(apply), save_points=len(folders), compressed=0, repaired=0,
                  would_compress=0, already=0, skipped=0, left_alone=0, bytes_before=0, bytes_after=0,
                  bytes_to_compress=0, problems=[])

    def one(item):
        folder, reason = item
        if reason:
            return folder, dict(status='left_alone', reason=reason)
        try:
            return folder, compress_save_point(folder, apply=apply)
        except Exception as exc:                                   # reported; the pass goes on with the next one
            return folder, dict(status='skipped', reason=f'{type(exc).__name__}: {exc}')

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:   # the 9p D: drive serves parallel reads well
        for folder, result in pool.map(one, folders):
            status = result['status']
            totals[status] += 1
            if status in ('compressed', 'repaired'):
                totals['bytes_before'] += result['before']
                totals['bytes_after'] += result['after']
            elif status == 'would_compress':
                totals['bytes_to_compress'] += result['before']
            elif status == 'skipped':
                totals['problems'].append(dict(save_point=str(folder), reason=result.get('reason')))
            if progress:
                progress(folder, result)
    return totals
