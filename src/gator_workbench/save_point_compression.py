"""Save points written compressed, and a one-time pass that compresses the ones written before (record 7.284).

A save point's ``training_state.pt`` is the zip archive ``torch.save`` writes, every entry STORED. The replay inside it -
each stored step with its circuit graph twice - is plain pickle and deflates about three times (41.6 MB -> 14.4 MB in
0.43 s at level 3; on 2026-10-08 save points were 26.2 GB of outputs/' 29 GB). ``torch.load`` reads a deflated archive
as it reads a stored one (torch 2.14: the same weights, random states and replay), so every reader - ``SACLearner.load``,
an older checkout, a queue's frozen runtime - opens a compressed save point unchanged.

Lossless, and shown to be: the new archive has the same entries, in the same order, each with the same bytes - every
entry is read back from the written file and compared with the original before the file is used. ``metadata.json``
records the compressed file's size and SHA-256 (what ``checkpoints.verify_files`` checks); a save point compressed by
the one-time pass keeps the original's size and SHA-256 under ``compressed_from``. The run's ``artifact_manifest.json``
(a size for every file, a checksum for the files without one of their own) is refreshed by the pass once per run, after
all of the run's save points and in the pass's own thread, never by its workers (record 7.286).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fnmatch
import hashlib
import io
import os
from pathlib import Path

from .checkpoints import verify_files
from .layout import RunLayout, find_runs
from .paths import MOCK_SUBDIR
from .run_lock import RunLock
from .storage.atomic import publish, read_json, sha256_file, temporary_path, write_json
# re-exported: moved to checkpoint_codec.py by the refactoring (docs/plan-refactoring.md)
from .checkpoint_codec import LEVEL, is_deflated, deflate, write_compressed

STATE = 'training_state.pt'
RECORD = '7.284'
VERIFIED = ('compressed', 'repaired', 'already')    # the pass checked the save point's training_state.pt against its checksum
REWRITTEN = (STATE, 'metadata.json')                 # the two files of a save point the pass writes
NOTE = (f"Record {RECORD}: a save point's training_state.pt may have been compressed afterwards (its zip entries deflated, "
        "every entry byte-identical); its checksum is in the save point's metadata.json.")


# ---------------------------------------------------------------------------------- the one-time pass over a folder
def compress_save_point(directory, *, apply=False) -> dict:
    """One save point folder: {status, before?, after?, reason?}, status one of compressed, would_compress, already,
    repaired, skipped. Nothing is written unless `apply`, and never for a file that does not match the checksum its
    metadata.json records (reported, not "fixed"). The run's artifact_manifest.json is not touched here: the pass over a
    folder refreshes it once per run (refresh_artifact_manifest)."""
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
    return dict(status='repaired' if interrupted else 'compressed', before=len(data), after=result['bytes'])


def refresh_artifact_manifest(run_dir, save_points, *, apply=False) -> dict:
    """The run's artifact_manifest.json (layout.build_artifact_manifest) lists every file's size, and a checksum for the
    files that carry none of their own - a save point's metadata.json among them. The pass rewrites a save point's
    training_state.pt and metadata.json; this refreshes their rows for the save points in `save_points` (the ones the
    pass verified) and the total, ONCE per run and from one read of the manifest. The workers used to rewrite it per
    save point, each from its own read: updates were lost (3 of 4 in a test), a second pass, finding the save points
    done, never came back to the manifest, and the rows of the rewritten metadata.json were never refreshed at all
    (Astra's review of 7.284, record 7.286). training_state.pt's checksum, where its row carries one, is the one the
    save point's metadata.json records (checked against the file by the pass); metadata.json's is read from the file.
    Returns {rows: the rows that differed, stale: whether anything differed, written: whether the manifest was
    rewritten}; nothing is written unless `apply`, and a manifest that is right already is left as it is."""
    run_dir = Path(run_dir)
    path = run_dir / 'artifact_manifest.json'
    manifest = read_json(path, default=None)
    if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list):
        return dict(rows=0, stale=False, written=False)
    rows = {row['path']: row for row in manifest['files'] if isinstance(row, dict) and isinstance(row.get('path'), str)}
    changed = 0
    for folder in save_points:
        folder = Path(folder)
        recorded = read_json(folder / 'metadata.json', default={})
        recorded = ((recorded.get('files') or {}).get(STATE) or {}) if isinstance(recorded, dict) else {}
        for name in REWRITTEN:
            row, file = rows.get(f'checkpoints/{folder.name}/{name}'), folder / name
            if row is None or not file.is_file():
                continue
            wanted = dict(bytes=file.stat().st_size)
            if row.get('sha256'):
                wanted['sha256'] = recorded.get('sha256') if name == STATE else sha256_file(file)
            wanted = {key: value for key, value in wanted.items() if value is not None}
            if any(row.get(key) != value for key, value in wanted.items()):
                row.update(wanted)
                changed += 1
    total = sum(row['bytes'] for row in manifest['files'] if isinstance(row, dict) and isinstance(row.get('bytes'), int))
    counted = isinstance(manifest.get('total_bytes'), int)
    if not changed and not (counted and manifest['total_bytes'] != total):
        return dict(rows=0, stale=False, written=False)
    if apply:
        if counted:
            manifest['total_bytes'] = total
        if isinstance(manifest.get('notes'), list) and NOTE not in manifest['notes']:
            manifest['notes'].append(NOTE)
        write_json(path, manifest)
    return dict(rows=changed, stale=True, written=bool(apply))


def save_point_folders(root, *, exclude=()) -> list:
    """[(save point folder, why it is left alone or None)] for every save point of every run under `root`: a run that
    is working (a worker holds its lock), lies in an excluded experiment folder, or is a link to a folder elsewhere is
    left alone."""
    root, found = Path(root).resolve(), []
    for run_dir in find_runs(root) + find_runs(root / MOCK_SUBDIR):      # the run list's two places (runs.list_runs)
        reason = None
        if any(fnmatch.fnmatch(run_dir.parents[2].name, pattern) for pattern in exclude):
            reason = 'excluded'
        elif root not in run_dir.resolve().parents:
            reason = 'a link to a run elsewhere'
        elif RunLock.held(RunLayout(run_dir).run_lock):
            reason = 'its run is working'
        try:
            names = sorted(n for n in os.listdir(run_dir / 'checkpoints') if n.startswith('ckpt-'))
        except OSError:
            continue
        found += [(run_dir / 'checkpoints' / name, reason) for name in names]
    return found


def compress_save_points(root, *, apply=False, exclude=(), workers=4, progress=None) -> dict:
    """The one-time pass over every save point under `root`, a dry run unless `apply`. Returns the counts, the bytes the
    compressed save points had before and have now, the runs whose artifact_manifest.json was refreshed (in a dry run:
    would be), and every save point skipped with its reason."""
    folders = save_point_folders(root, exclude=exclude)
    totals = dict(root=str(root), apply=bool(apply), save_points=len(folders), compressed=0, repaired=0,
                  would_compress=0, already=0, skipped=0, left_alone=0, bytes_before=0, bytes_after=0,
                  bytes_to_compress=0, manifests_refreshed=0, manifest_rows_refreshed=0, manifests_to_refresh=0,
                  problems=[])

    def one(item):
        folder, reason = item
        if reason:
            return folder, dict(status='left_alone', reason=reason)
        try:
            return folder, compress_save_point(folder, apply=apply)
        except Exception as exc:                                   # reported; the pass goes on with the next one
            return folder, dict(status='skipped', reason=f'{type(exc).__name__}: {exc}')

    by_run = {}
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
            by_run.setdefault(folder.parent.parent, []).append((folder, status))
    # The manifests: one per run, after all of its save points, written once and from this thread only.
    for run_dir, results in by_run.items():
        verified = [folder for folder, status in results if status in VERIFIED]
        pending = any(status == 'would_compress' for _, status in results)
        if not verified and not pending:
            continue
        try:
            refreshed = refresh_artifact_manifest(run_dir, verified, apply=apply)
        except Exception as exc:                                   # reported; the pass goes on with the next run
            totals['problems'].append(dict(manifest=str(run_dir / 'artifact_manifest.json'),
                                           reason=f'{type(exc).__name__}: {exc}'))
            continue
        if refreshed['written']:
            totals['manifests_refreshed'] += 1
            totals['manifest_rows_refreshed'] += refreshed['rows']
            if progress:
                progress(run_dir / 'artifact_manifest.json', dict(status='manifest', reason=f"{refreshed['rows']} rows refreshed"))
        elif not apply and (pending or refreshed['stale']):
            totals['manifests_to_refresh'] += 1
    return totals
