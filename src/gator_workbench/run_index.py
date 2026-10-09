"""The run list and what it reads from each run folder, kept while the folder is unchanged (record 7.274), many folders
at a time (record 7.279): a run's timing and lineage, its latest save point and whether the optimizer source of now
wrote it, and the unique names of the runs' models.

Moved from runs.py by the refactoring (docs/plan-refactoring.md): profiles and the API read the run list without the
run preparation, and profiles importing runs for it closed an import cycle. runs.py re-exports every name except the
caches' and the source digest's own state, which tests patch here.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import threading
import time

from . import checkpoints as ckpt
from .names import WORKING_STATES
from .run_lock import RunLock
from .layout import RunLayout, find_runs
from .paths import OutputRoots
from .storage.atomic import read_dict, read_json
from .summary import durations
from .settings_store import remembered_output_root


SEGMENT_FACTS = ('segment', 'entry', 'started_utc', 'ended_utc', 'end_state', 'stop_reason', 'active_seconds')


def run_timing(manifest, status) -> dict:
    """When a run began to work, when it came to rest and how long it worked: the time columns of the run list.

    ``ended_utc`` is the end of the LAST segment, so it is set for a run that completed, stopped, failed or is
    paused, and None while a worker is on it. A worker that died wrote no end: ``last_seen_utc``, its last status
    heartbeat, is all that is known then. ``active_seconds`` is working time as in run_summary.json - the pauses
    between segments (``paused_seconds``) are not part of it - and None for a run whose worker never began."""
    segments = manifest.get('segments') or []
    started = next((s['started_utc'] for s in segments if s.get('started_utc')), None)
    ended = segments[-1].get('ended_utc') if segments else None
    active, paused = durations(manifest)
    if not ended and status.get('active_seconds') is not None:
        active = status['active_seconds']           # an open segment has no time of its own yet: the worker's running total
    return dict(started_utc=started, ended_utc=ended, last_seen_utc=status.get('heartbeat_utc'),
                active_seconds=active if started else None, paused_seconds=paused,
                segments=[{fact: s.get(fact) for fact in SEGMENT_FACTS} for s in segments])


def lineage(manifest) -> dict:
    """Where a run's model came from, as its manifest recorded it (record 7.264; plan "Relationships and history: data").
    `parent`: the run, save point and relation a fine-tune or evaluate run loaded (None for a new model); `run_kind`:
    optimization, baseline_preflight, calibration or offline_pretraining; `encoder`: the network a new model was made
    from (its template); `pretraining_sources`: how many recorded runs an offline model was trained on. Read, never
    inferred from names or folder paths."""
    sources = (manifest.get('pretraining') or {}).get('sources')
    return dict(parent=manifest.get('parent'), run_kind=manifest.get('run_kind'),
                encoder=((manifest.get('architecture') or {}).get('network') or {}).get('encoder_type'),
                pretraining_sources=len(sources) if isinstance(sources, list) else None)


class _RunRow(dict):
    """A row of list_runs - plain JSON as ever - that also keeps the manifest it was built from, as an attribute that is
    never serialized: checkpoints.saved_models is handed these rows and used to read every manifest a second time.
    `cache_key`: the run folder's fingerprint the row was built at (checkpoint_listing, record 7.274)."""
    __slots__ = ('manifest', 'cache_key')

    def __init__(self, manifest, **fields):
        super().__init__(**fields)
        self.manifest = manifest
        self.cache_key = None


def save_point(run_dir) -> str | None:
    """The run's latest save point as its folder holds it now (``checkpoints/latest.json`` and the save point it names),
    or None: none was written, or it is gone - a copy made without its save points (record 7.213's viewing copies of
    recorded runs), or deleted. Continue needs it: a resume refuses "Nothing to resume" without it."""
    return ckpt.latest_point(run_dir)[0]


def save_point_facts(run_dir) -> tuple[str | None, str | None]:
    """``(save_point, save_point_code)`` from ONE read of the run's pointer (record 7.274): the polled status asks both."""
    name, saved = ckpt.latest_point(run_dir)
    return name, _code_of(saved) if name else None


_SOURCE_DIGEST = dict(value=None, at=0.0, refreshing=False)
_SOURCE_DIGEST_LOCK = threading.Lock()


def _refresh_source_digest():
    from analog_optimizer.training.sac import source_digest
    try:
        value = source_digest()
        with _SOURCE_DIGEST_LOCK:
            _SOURCE_DIGEST.update(value=value, at=time.monotonic())
    finally:
        with _SOURCE_DIGEST_LOCK:
            _SOURCE_DIGEST['refreshing'] = False


def current_source_digest(max_age=30.0) -> str:
    """The optimizer source digest a run started now would record (training.sac.source_digest hashes every file under
    src/analog_optimizer/). Kept for 30 s: the hashing takes ~0.4 s on the 9p mount and the run list asks per request.
    Once known, an older value is hashed again in a thread while the request goes on with it (record 7.279): the hash
    inside a request made a status poll take 0.2-0.45 s every 30 s. Only for what the page says; a start checks the
    digest itself (runs.prepare_run, checkpoints.check_compatibility)."""
    with _SOURCE_DIGEST_LOCK:
        value = _SOURCE_DIGEST['value']
        refresh = (value is not None and not _SOURCE_DIGEST['refreshing']
                   and time.monotonic() - _SOURCE_DIGEST['at'] > max_age)
        if refresh:
            _SOURCE_DIGEST['refreshing'] = True
    if value is None:                                  # the first one: there is nothing to answer with meanwhile
        from analog_optimizer.training.sac import source_digest
        value = source_digest()
        with _SOURCE_DIGEST_LOCK:
            _SOURCE_DIGEST.update(value=value, at=time.monotonic())
    elif refresh:
        threading.Thread(target=_refresh_source_digest, name='gator-source-digest', daemon=True).start()
    return value


def _code_of(saved) -> str | None:
    return None if saved is None else 'current' if saved == current_source_digest() else 'older'


def save_point_code(run_dir) -> str | None:
    """'current' or 'older': whether the latest save point was written by the optimizer source the repository holds now.
    Continue (an exact resume, SACLearner.load) needs exactly that source; a save point of 'older' source still loads
    for fine-tune and frozen, where the digest is only a warning (record 7.221). None: no readable save point."""
    return save_point_facts(run_dir)[1]


def _resumability(run_dir, summary, point=None):
    """The run window's "Can continue" (record 7.215): what the summary says the latest save point allows, while that
    save point is still in the run folder; 'none' once it is gone, whatever the summary wrote when the run came to rest.
    A full save point written by an older optimizer source reads 'weights_only' ("model only"): Continue needs that
    source, fine-tune and frozen still load the model (record 7.221). `point`: ckpt.latest_point(run_dir), when known."""
    claimed = (summary.get('output') or {}).get('resumability')
    if claimed in (None, 'none'):
        return claimed
    name, saved = point if point is not None else ckpt.latest_point(run_dir)
    if not name:
        return 'none'
    return 'weights_only' if claimed == 'full_state' and _code_of(saved) == 'older' else claimed


# ---- the run list's per-run cache (record 7.274) --------------------------------------------------------------------
# On the 9p-mounted D: drive the run list took 6-11 s for ~100 runs (dozens of file operations per run) and the saved
# models twice that. A run's files are only ever replaced whole (write_json: a temp file renamed into place), which
# changes the folder's mtime - and a new or pruned save point changes checkpoints/'s. So what was read from a run
# folder is kept while both folders' (inode, mtime, ctime) are unchanged: two stats per run instead of dozens. Each
# request still probes the run lock of runs whose status says they work, compares the save point's code with the
# source digest of NOW, and works out the unique model names. The page's "Refresh list" asks with fresh=True: a file
# changed in place by another tool is seen then (an entry was read again after 10 minutes too until record 7.279: all
# of them expired together, and the saved models took 12.9 s again every 10 minutes).
# The reads of a request go through a pool of READ_THREADS threads (record 7.279): on the 9p mount the file operations
# of many folders overlap well (16 at once: a stat 5-8 ms -> 0.2-0.5 ms each).
# The API answers several requests at once (FastAPI runs these routes on a thread pool), so the dict itself is read,
# written and walked under _RUN_CACHE_LOCK only; the file reads stay outside it (record 7.278: two lists at once could
# end in "dictionary changed size during iteration" while one let go of entries and the other added some).
_RUN_CACHE: dict = {}
_RUN_CACHE_LOCK = threading.Lock()
READ_THREADS = 16
_READ_POOL: list = []
_READ_POOL_LOCK = threading.Lock()
LIVE_STATES = WORKING_STATES


def _fingerprint(run_dir):
    own = os.stat(run_dir)
    try:
        points = os.stat(os.path.join(run_dir, 'checkpoints'))
        points = (points.st_ino, points.st_mtime_ns, points.st_ctime_ns)
    except FileNotFoundError:
        points = None
    return own.st_ino, own.st_mtime_ns, own.st_ctime_ns, points


def run_facts(run_dir, *, fresh=False) -> dict | None:
    """What list_runs and model_label_rows read from one run folder, from the cache while the folder is unchanged; None
    for a folder without a manifest (or one that is gone)."""
    try:
        key = _fingerprint(run_dir)                  # BEFORE the reads: a change while they run is a miss next time
    except OSError:
        return None
    with _RUN_CACHE_LOCK:
        entry = _RUN_CACHE.get(str(run_dir))
    if fresh or entry is None or entry['key'] != key:
        manifest = read_json(Path(run_dir) / 'run_manifest.json', default=None)      # the reads: outside the lock
        if not isinstance(manifest, dict):
            with _RUN_CACHE_LOCK:
                _RUN_CACHE.pop(str(run_dir), None)
            return None
        entry = dict(key=key, manifest=manifest, summary=read_dict(Path(run_dir) / 'run_summary.json'),
                     status=read_dict(Path(run_dir) / 'status.json'), point=ckpt.latest_point(run_dir),
                     label=ckpt.model_label_of(run_dir, manifest), listing=None)
        with _RUN_CACHE_LOCK:
            _RUN_CACHE[str(run_dir)] = entry
    return entry


def checkpoint_listing(row) -> dict:
    """ckpt.list_checkpoints of a list_runs row, kept with the run's cache entry that row was built from (the saved
    models re-read ~400 metadata files on every request before); read anew when the entry has changed since."""
    with _RUN_CACHE_LOCK:
        entry = _RUN_CACHE.get(row['run_dir'])
    if entry is None or entry['key'] != getattr(row, 'cache_key', None):
        return ckpt.list_checkpoints(row['run_dir'])
    if entry['listing'] is None:
        entry['listing'] = ckpt.list_checkpoints(row['run_dir'])
    return entry['listing']


def _read_pool() -> ThreadPoolExecutor:
    with _READ_POOL_LOCK:
        if not _READ_POOL:
            _READ_POOL.append(ThreadPoolExecutor(max_workers=READ_THREADS, thread_name_prefix='gator-run-read'))
        return _READ_POOL[0]


def read_many(read, items) -> list:
    """`read(item)` of every item, in their order, READ_THREADS at a time (record 7.279)."""
    items = list(items)
    return list(_read_pool().map(read, items)) if len(items) > 1 else [read(item) for item in items]


def checkpoint_listings(rows):
    """checkpoint_listing of every list_runs row, read READ_THREADS at a time: what saved_models reads one by one, as a
    `read_listing` for it (record 7.279; the first saved models after a start read ~800 metadata files)."""
    listings = dict(zip((row['run_dir'] for row in rows), read_many(checkpoint_listing, rows)))
    return lambda row: listings[row['run_dir']]


def list_runs(roots: OutputRoots, output_root=None, *, include_mock=True, fresh=False):
    """Every run under the output root, newest first. `fresh`: read every run folder again (the page's Refresh list)."""
    root = roots.resolve(output_root or remembered_output_root())
    runs, seen = [], set()
    for data_root, mock in ((root, False), (root / 'mock', True)):
        if mock and not include_mock:
            continue
        found = find_runs(data_root, manifest=False)
        for run_dir, facts in zip(found, read_many(lambda run_dir: run_facts(run_dir, fresh=fresh), found)):
            if facts is None:
                continue
            seen.add(str(run_dir))
            manifest, summary, status = facts['manifest'], facts['summary'], facts['status']
            # The lock is probed only for a run whose status says it works: the row has no `worker_alive`, so a run at
            # rest needs no probe (run_status still probes every time for the polled status).
            if status.get('state') in LIVE_STATES and not RunLock.held(RunLayout(run_dir).run_lock):
                status = dict(status, state='interrupted')
            budget = status.get('budget') or {}     # current while a worker is on the run; the summary is written when it rests
            row = _RunRow(manifest, run_dir=str(run_dir), run_id=manifest.get('run_id'), task_id=manifest.get('task_id'),
                          task_definition_hash=manifest.get('task_definition_hash'), mode=manifest.get('mode'),
                          mock=manifest.get('mock'), seed=(manifest.get('seeds') or {}).get('target_seed'),
                          created_utc=manifest.get('created_utc'), state=status.get('state'),
                          experiment=f"{manifest.get('experiment_name')}__{manifest.get('experiment_id')}",
                          evaluations=budget.get('charged', (summary.get('totals') or {}).get('candidate_evaluations_charged')),
                          first_feasible_eval_count=summary.get('first_feasible_eval_count'),
                          resumability=_resumability(run_dir, summary, facts['point']),
                          # The run window (frontend RunList.tsx): what a run was, how it ended and how long it took.
                          task_name=manifest.get('task_name'), stop_reason=status.get('stop_reason'), error=status.get('error'),
                          max_evaluations=(manifest.get('budgets') or {}).get('max_evaluations'),
                          # The registered task it ran (real:<name>, ngspice:<name>, as the Task list names it): choosing
                          # that task shows its newest run (App.tsx, record 7.212).
                          task_key=(manifest.get('circuit') or {}).get('task_key'),
                          **lineage(manifest),
                          **facts['label'], **run_timing(manifest, status))
            row.cache_key = facts['key']
            runs.append(row)
    # Entries of run folders that are gone from this root are let go - under the lock: another request's _run_facts may
    # be adding entries while this one walks the dict.
    with _RUN_CACHE_LOCK:
        for key in [k for k in _RUN_CACHE if k.startswith(str(root) + os.sep) and k not in seen]:
            _RUN_CACHE.pop(key, None)
    # The name of each run's model, no two alike under this root (record 7.225): the run window and the saved-model
    # cards show it; `renamed` says whether it was given by a rename.
    names = ckpt.unique_model_labels(runs)
    for row in runs:
        row['model_label'] = names.get(row['run_dir'])
    return sorted(runs, key=lambda r: r['created_utc'] or '', reverse=True)


def model_label_rows(output_root) -> list[dict]:
    """Every run under an output root (real and mock) with the name of its model, read lean - the manifest and
    model_label.json only - for the numbering at a start and the taken names at a rename (record 7.225). Through the run
    cache (record 7.274): a rename or a new run changes its folder, so the cache never holds an old name."""
    rows = []
    for data_root in (Path(output_root), Path(output_root) / 'mock'):
        found = find_runs(data_root, manifest=False)
        for run_dir, facts in zip(found, read_many(run_facts, found)):
            if facts is not None:
                rows.append(dict(run_dir=str(run_dir), created_utc=facts['manifest'].get('created_utc'), **facts['label']))
    return rows


def output_root_of(run_dir) -> Path:
    """The output root a run folder lies under: <root>[/mock]/<experiment>/runs/<task>/<run>."""
    data_root = Path(run_dir).parents[3]
    return data_root.parent if data_root.name == 'mock' else data_root


# The name this had before refactoring package B9 (2026-10-09), kept for code that still uses it.
_run_facts = run_facts
