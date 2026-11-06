"""Record 7.274: the run list and the saved models read faster on the 9p-mounted D: drive (6-11 s and 15-17 s for ~100
runs). One cheap look at each run's save point (checkpoints.latest_point instead of resolve_checkpoint twice), the run
lock probed only for runs whose status says they work, a scandir folder search, and a per-run cache checked by two folder
stats. These tests pin that the ANSWERS stay what they were, and what the cache sees and when."""
import json
import os
import shutil
import threading
import time

import pytest

from gator_workbench import checkpoints as ckpt, layout as layout_module, run_index, runs
from gator_workbench.layout import find_runs
from gator_workbench.storage.atomic import write_json
from helpers import execute, fabricate_run, make_config, roots_for
from pathlib import Path
from gator_workbench.storage import read_dict, read_json


def fabricate(root, name, *, created='2026-10-07T10:00:00+00:00', state='completed', label='ota', summary=None):
    """Create minimal run files for cache tests without running a simulation."""
    run = root / 'exp__0123456789ab' / 'runs' / 'task' / name
    run.mkdir(parents=True)
    write_json(run / 'run_manifest.json', dict(run_id=name, created_utc=created, mock=False, experiment_name='exp',
                                               experiment_id='0123456789ab', task_name='task', model_label=label))
    write_json(run / 'status.json', dict(state=state))
    write_json(run / 'run_summary.json', summary or dict(output=dict(resumability='full_state')))
    return run


def save(run, point, *, code='abc', evaluations=10):
    """Write fixture save-point metadata and select it as the run's latest point."""
    directory = run / 'checkpoints' / point
    directory.mkdir(parents=True)
    write_json(directory / 'metadata.json', dict(
        checkpoint_id=point, kind='periodic', created_utc=f'2026-10-07T10:{evaluations:02d}:00+00:00', mode='scratch',
        counters=dict(evaluations_committed=evaluations, learner_updates=evaluations, replay_size=evaluations),
        restoration_capability='full_state', missing_components=[],
        contract=dict(code_sha256=code, model_config=dict(encoder_type='rgcn', hidden_dim=16, heads=2, layers=1))))
    write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id=point))
    return directory


# ---- one look at the save point ------------------------------------------------------------------------------------
def test_latest_point_names_the_save_point_and_its_code_as_resolve_checkpoint_did(tmp_path):
    run = fabricate(tmp_path, 'r1')
    save(run, 'ckpt-00000010-a', code='abc')
    assert ckpt.latest_point(run) == ('ckpt-00000010-a', 'abc')
    assert ckpt.resolve_checkpoint(run, 'latest').name == 'ckpt-00000010-a'


@pytest.mark.parametrize('pointer', ['../escape', '/abs', '', '.', '..', 'ckpt-missing', None, 7])
def test_latest_point_refuses_what_resolve_checkpoint_refuses(tmp_path, pointer):
    run = fabricate(tmp_path, 'r1')
    (tmp_path / 'escape').mkdir()
    write_json(tmp_path / 'escape' / 'metadata.json', dict(contract=dict(code_sha256='x')))
    (run / 'checkpoints').mkdir()
    write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id=pointer))
    assert ckpt.latest_point(run) == (None, None)
    with pytest.raises((FileNotFoundError, TypeError, ValueError)):
        ckpt.resolve_checkpoint(run, 'latest')


def test_latest_point_without_a_pointer_or_metadata_is_none(tmp_path):
    run = fabricate(tmp_path, 'r1')
    assert ckpt.latest_point(run) == (None, None)                      # no checkpoints/ at all
    (run / 'checkpoints' / 'ckpt-a').mkdir(parents=True)
    write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id='ckpt-a'))
    assert ckpt.latest_point(run) == (None, None)                      # a folder without metadata.json: no save point


def test_unreadable_metadata_is_a_save_point_of_no_known_code(tmp_path):
    """resolve_checkpoint only asks that metadata.json is a file; reading its code is what fails (save_point_code None)."""
    run = fabricate(tmp_path, 'r1')
    directory = save(run, 'ckpt-a')
    (directory / 'metadata.json').write_text('{not json')
    assert ckpt.latest_point(run) == ('ckpt-a', None)
    assert runs.save_point(run) == 'ckpt-a' and runs.save_point_code(run) is None and runs.save_point_facts(run) == ('ckpt-a', None)


def test_a_linked_save_point_folder_is_not_offered(tmp_path):
    """The one change on purpose: a save point that is a symbolic link is refused (GATOR never makes one)."""
    run = fabricate(tmp_path, 'r1')
    target = save(run, 'ckpt-a')
    os.symlink(target, run / 'checkpoints' / 'ckpt-link')
    write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id='ckpt-link'))
    assert ckpt.latest_point(run) == (None, None)


def test_the_code_of_the_save_point_is_compared_with_the_source_digest_of_now(tmp_path, monkeypatch):
    run = fabricate(tmp_path, 'r1')
    save(run, 'ckpt-a', code='old-code')
    monkeypatch.setattr(run_index, 'current_source_digest', lambda max_age=30.0: 'new-code')
    assert runs.save_point_facts(run) == ('ckpt-a', 'older')
    row, = runs.list_runs(roots_for(tmp_path), tmp_path)
    assert row['resumability'] == 'weights_only'                        # a full save point of older code: model only (7.221)
    monkeypatch.setattr(run_index, 'current_source_digest', lambda max_age=30.0: 'old-code')
    row, = runs.list_runs(roots_for(tmp_path), tmp_path)                 # the cache keeps the code, never the verdict
    assert row['resumability'] == 'full_state' and runs.save_point_code(run) == 'current'


# ---- the folder search -------------------------------------------------------------------------------------------
def test_find_runs_finds_what_the_glob_found(tmp_path):
    for path, manifest in [('exp__a/runs/t/r1', True), ('exp__a/runs/t/.hidden', True), ('exp__a/runs/t/r2', False),
                           ('noexp/runs/t/r3', True), ('exp__b/runs/t2/r4', True), ('.exp__h/runs/t/r5', True)]:
        (tmp_path / path).mkdir(parents=True)
        if manifest:
            (tmp_path / path / 'run_manifest.json').write_text('{}')
    (tmp_path / 'exp__a' / 'runs' / 'stray.txt').write_text('')
    glob = sorted(p.parent for p in tmp_path.glob('*__*/runs/*/*/run_manifest.json'))
    assert find_runs(tmp_path) == glob and len(glob) == 4
    assert set(find_runs(tmp_path, manifest=False)) == set(glob) | {tmp_path / 'exp__a/runs/t/r2'}
    assert find_runs(tmp_path / 'missing') == [] and find_runs(tmp_path / 'exp__a' / 'runs' / 'stray.txt') == []
    # several experiment folders at a time (record 7.478): the same runs in the same order
    assert find_runs(tmp_path, many=run_index.read_many) == glob
    assert find_runs(tmp_path, manifest=False, many=run_index.read_many) == find_runs(tmp_path, manifest=False)
    assert find_runs(tmp_path / 'missing', many=run_index.read_many) == []


def test_the_run_list_walks_several_experiment_folders_at_a_time(tmp_path, monkeypatch):
    """Record 7.478: with 826 runs under the output root, the walk that finds the run folders - two folder listings a
    run, one after another on the 9p-mounted D: drive - had become the larger part of the run list's 6 s. The listings
    of the experiment folders go through the read pool now, 16 at a time (a list in 1.25 s); the root is listed once,
    by the caller."""
    for name, experiment in (('one', 'exp__a'), ('two', 'exp__b'), ('three', 'exp__c')):
        run = tmp_path / experiment / 'runs' / 'task' / name
        run.mkdir(parents=True)
        write_json(run / 'run_manifest.json', dict(run_id=name, created_utc='2026-11-06T00:00:00+00:00', mock=False,
                                                   experiment_name='exp', experiment_id=experiment[-1], task_name='task'))
        write_json(run / 'status.json', dict(state='completed'))
        write_json(run / 'run_summary.json', dict(output=dict(resumability='full_state')))
    listed = []
    subfolders = layout_module._subfolders
    monkeypatch.setattr(layout_module, '_subfolders', lambda path, **kwargs: listed.append(
        (os.path.relpath(path, tmp_path), threading.current_thread().name)) or subfolders(path, **kwargs))
    assert sorted(row['run_id'] for row in runs.list_runs(roots_for(tmp_path), tmp_path, include_mock=False)) == ['one', 'three', 'two']
    pooled = sorted(path for path, thread in listed if thread.startswith('gator-run-read'))
    assert pooled == ['exp__a/runs', 'exp__a/runs/task', 'exp__b/runs', 'exp__b/runs/task', 'exp__c/runs', 'exp__c/runs/task']
    assert [path for path, thread in listed if not thread.startswith('gator-run-read')] == ['.']
    listed.clear()
    assert len(runs.model_label_rows(tmp_path)) == 3                             # the model names' lean rows: the same walk
    assert len([path for path, thread in listed if thread.startswith('gator-run-read')]) == 6


# ---- the per-run cache ---------------------------------------------------------------------------------------------
def rows_of(root, **kwargs):
    """Index the run-list response by run identifier."""
    return {row['run_id']: row for row in runs.list_runs(roots_for(root), root, **kwargs)}


def test_a_replaced_file_is_seen_at_the_next_read(tmp_path):
    """Every file GATOR writes in a run folder is replaced whole (write_json renames a temp file): the folder changes."""
    run = fabricate(tmp_path, 'r1')
    assert rows_of(tmp_path)['r1']['state'] == 'completed'
    write_json(run / 'status.json', dict(state='failed', stop_reason='error'))
    assert rows_of(tmp_path)['r1']['state'] == 'failed'
    ckpt.rename_model(run, 'renamed', taken=set())                       # model_label.json, written whole
    assert rows_of(tmp_path)['r1']['model_label'] == 'renamed'


def test_a_new_or_pruned_save_point_is_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(run_index, 'current_source_digest', lambda max_age=30.0: 'abc')     # the code save() writes
    run = fabricate(tmp_path, 'r1')
    assert rows_of(tmp_path)['r1']['resumability'] == 'none'             # the summary claims one, the folder holds none
    save(run, 'ckpt-00000010-a')
    assert rows_of(tmp_path)['r1']['resumability'] == 'full_state'
    shutil.rmtree(run / 'checkpoints' / 'ckpt-00000010-a')
    assert rows_of(tmp_path)['r1']['resumability'] == 'none'


def test_an_in_place_edit_is_seen_with_fresh(tmp_path):
    """The trade-off: a file written IN PLACE by another tool leaves the folder unchanged. The page's Refresh list
    reads with fresh=True (record 7.279: no expiry by age any more)."""
    run = fabricate(tmp_path, 'r1')
    assert rows_of(tmp_path)['r1']['state'] == 'completed'
    with open(run / 'status.json', 'r+') as stream:                      # in place: the same file, no rename
        stream.truncate(0)
        stream.write(json.dumps(dict(state='failed')))
    assert rows_of(tmp_path)['r1']['state'] == 'completed'
    assert rows_of(tmp_path, fresh=True)['r1']['state'] == 'failed'


def test_an_entry_is_kept_however_old_until_its_folder_changes(tmp_path, monkeypatch):
    """Record 7.279: entries no longer expire after 10 minutes - they all expired together, and the saved models took
    12.9 s again every 10 minutes. A replaced file changes the folder; an in-place edit shows at Refresh list."""
    run = fabricate(tmp_path, 'r1')
    rows_of(tmp_path)
    with open(run / 'status.json', 'r+') as stream:
        stream.truncate(0)
        stream.write(json.dumps(dict(state='failed')))
    a_day_later = time.monotonic() + 86400
    monkeypatch.setattr(time, 'monotonic', lambda: a_day_later)
    assert rows_of(tmp_path)['r1']['state'] == 'completed' and not hasattr(run_index, 'RUN_CACHE_MAX_AGE')
    assert rows_of(tmp_path, fresh=True)['r1']['state'] == 'failed'


def test_a_removed_run_leaves_the_list_and_the_cache(tmp_path):
    keep, gone = fabricate(tmp_path, 'r1'), fabricate(tmp_path, 'r2', created='2026-10-07T11:00:00+00:00')
    assert set(rows_of(tmp_path)) == {'r1', 'r2'} and str(gone) in run_index._RUN_CACHE
    shutil.rmtree(gone)
    assert set(rows_of(tmp_path)) == {'r1'} and str(gone) not in run_index._RUN_CACHE and str(keep) in run_index._RUN_CACHE


def test_the_lock_is_probed_only_for_runs_that_say_they_work(tmp_path, monkeypatch):
    fabricate(tmp_path, 'rest'), fabricate(tmp_path, 'gone', state='running', created='2026-10-07T11:00:00+00:00')
    probed = []
    monkeypatch.setattr(runs.RunLock, 'held', staticmethod(lambda path: probed.append(path) or False))
    rows = rows_of(tmp_path)
    assert len(probed) == 1 and 'gone' in str(probed[0])
    assert rows['gone']['state'] == 'interrupted' and rows['rest']['state'] == 'completed'   # a worker that died, as before


def test_saved_models_reuse_the_listing_until_the_run_changes(tmp_path, monkeypatch):
    run = fabricate(tmp_path, 'r1')
    save(run, 'ckpt-00000010-a')
    original, reads = ckpt.list_checkpoints, []
    monkeypatch.setattr(ckpt, 'list_checkpoints', lambda run_dir: reads.append(run_dir) or original(run_dir))
    rows = runs.list_runs(roots_for(tmp_path), tmp_path)
    first = ckpt.saved_models(rows, runs.checkpoint_listing)
    again = ckpt.saved_models(runs.list_runs(roots_for(tmp_path), tmp_path), runs.checkpoint_listing)
    assert len(reads) == 1 and first == again == ckpt.saved_models(rows)     # the same answer as without the cache
    save(run, 'ckpt-00000020-b', evaluations=20)
    model, = ckpt.saved_models(runs.list_runs(roots_for(tmp_path), tmp_path), runs.checkpoint_listing)
    assert len(model['checkpoints']) == 2 and model['trained_evaluations'] == 20


def test_model_label_rows_follow_a_rename(tmp_path):
    run = fabricate(tmp_path, 'r1', label='ota')
    assert [row['model_label'] for row in runs.model_label_rows(tmp_path)] == ['ota']
    ckpt.rename_model(run, 'ota-renamed', taken=set())
    assert [(row['model_label'], row['renamed']) for row in runs.model_label_rows(tmp_path)] == [('ota-renamed', True)]


# ---- the lock (record 7.278) ---------------------------------------------------------------------------------------
class _OwnedLock:
    """_RUN_CACHE_LOCK that knows which thread holds it: since record 7.279 a request reads its runs on several threads
    at once, and one thread's file read while ANOTHER thread holds the lock is fine."""
    def __init__(self):
        self._lock, self.owner = threading.Lock(), None

    def __enter__(self):
        self._lock.acquire()
        self.owner = threading.get_ident()
        return self

    def __exit__(self, *exc):
        self.owner = None
        self._lock.release()

    def mine(self):
        """Report whether the current thread owns the fixture cache lock."""
        return self.owner == threading.get_ident()


class _Guarded(dict):
    """A cache that refuses every touch made without _RUN_CACHE_LOCK. The API answers on several threads at once, and
    two lists at once could end in "dictionary changed size during iteration" while one let go of entries and the other
    added some (Astra's review of 2026-10-08)."""
    def _held(self):
        """Assert that the current thread holds the run-cache lock."""
        assert run_index._RUN_CACHE_LOCK.mine(), 'the run cache was touched without its lock'

    def get(self, *args):
        """Require the cache lock before reading an entry."""
        self._held()
        return super().get(*args)

    def __setitem__(self, key, value):
        """Require the cache lock before replacing an entry."""
        self._held()
        super().__setitem__(key, value)

    def pop(self, *args):
        """Require the cache lock before removing an entry."""
        self._held()
        return super().pop(*args)

    def __iter__(self):
        """Require the cache lock before iterating over keys."""
        self._held()
        return super().__iter__()


def test_the_cache_is_touched_under_its_lock_only_and_the_files_are_read_outside_it(tmp_path, monkeypatch):
    monkeypatch.setattr(run_index, '_RUN_CACHE', _Guarded())
    monkeypatch.setattr(run_index, '_RUN_CACHE_LOCK', _OwnedLock())
    original, original_dict = run_index.read_json, run_index.read_dict

    def read_outside(*args, **kwargs):
        """Assert that run-file JSON reads happen outside the cache lock."""
        assert not run_index._RUN_CACHE_LOCK.mine(), 'a run file was read while the cache lock was held'
        return original(*args, **kwargs)

    def read_dict_outside(path):                     # the empty-dict reads (refactoring package B8), checked the same way
        """Assert that empty-dict fallback reads happen outside the cache lock."""
        assert not run_index._RUN_CACHE_LOCK.mine(), 'a run file was read while the cache lock was held'
        return original_dict(path)
    monkeypatch.setattr(run_index, 'read_json', read_outside)
    monkeypatch.setattr(run_index, 'read_dict', read_dict_outside)
    kept, gone = fabricate(tmp_path, 'r1'), fabricate(tmp_path, 'r2', created='2026-10-07T11:00:00+00:00')
    save(kept, 'ckpt-a')
    (tmp_path / 'exp__0123456789ab' / 'runs' / 'task' / 'no-manifest').mkdir()         # a folder without a manifest: let go
    rows = runs.list_runs(roots_for(tmp_path), tmp_path)
    ckpt.saved_models(rows, runs.checkpoint_listing)
    ckpt.saved_models(runs.list_runs(roots_for(tmp_path), tmp_path), runs.checkpoint_listing)
    ckpt.saved_models(rows, runs.checkpoint_listings(rows))                 # the route's way since 7.279: many at a time
    runs.model_label_rows(tmp_path)
    shutil.rmtree(gone)
    assert set(rows_of(tmp_path)) == {'r1'} and set(rows_of(tmp_path, fresh=True)) == {'r1'}


# ------------------------------------------------------------------------------- B8: the run list and the model list
@pytest.fixture(scope='module')
def two_runs(tmp_path_factory):
    """Provide one completed synthetic run and one prepared run without a model."""
    root = tmp_path_factory.mktemp('lists')
    execute(make_config(root, run=dict(max_evaluations=6), project=dict(task_name='with_model')), root)
    runs.prepare_run(make_config(root, project=dict(task_name='just_created')), roots_for(root))
    return root


def test_the_run_list_reads_each_status_once_and_the_model_list_no_manifest(two_runs, monkeypatch):
    rows = runs.list_runs(roots_for(two_runs), two_runs)
    assert len(rows) == 2 and rows == json.loads(json.dumps(rows))     # plain JSON as ever
    read = []
    monkeypatch.setattr(layout_module, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    monkeypatch.setattr(run_index, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    monkeypatch.setattr(ckpt, 'read_json', lambda path, *a, **k: read.append(Path(path).name) or read_json(path, *a, **k))
    # the empty-dict reads of these modules go through read_dict (refactoring package B8): counted the same way
    monkeypatch.setattr(run_index, 'read_dict', lambda path: read.append(Path(path).name) or read_dict(path))
    monkeypatch.setattr(ckpt, 'read_dict', lambda path: read.append(Path(path).name) or read_dict(path))
    listed = runs.list_runs(roots_for(two_runs), two_runs, fresh=True)     # read from disk (Refresh list): each file once
    assert read.count('status.json') == 2 and read.count('run_manifest.json') == 2
    read.clear()
    # Record 7.274: run folders unchanged since the last list are read from its cache - no file at all.
    assert runs.list_runs(roots_for(two_runs), two_runs) == listed and read == []
    models = ckpt.saved_models(listed)
    assert 'run_manifest.json' not in read
    # rows that lost their manifest (a JSON round trip) are read from disk: the same answer
    assert models == ckpt.saved_models(json.loads(json.dumps(listed))) and [m['task_name'] for m in models] == ['with_model']
    assert models[0]['circuit_task'] == 'synthetic:gpdk045_ota5'


# ---- the source digest and a start's code facts ---------------------------------------------------------------------
def test_the_source_digest_is_hashed_again_in_a_thread_once_known(monkeypatch):
    import analog_optimizer.training.sac as sac
    values, release = iter(['first', 'second']), threading.Event()

    def digest():
        """Return scripted digests while holding the second calculation for the concurrency check."""
        value = next(values)
        if value == 'second':
            release.wait(5)
        return value
    # A refresh that the test before started - its last run list, when this process's digest was over 30 s old - hashes
    # the real sources in a thread. It has to end before this test puts its own state in place, or its answer lands there
    # (record 7.478: one failure in a full run on a busy machine; the code from before that record does the same).
    for _ in range(1000):
        if not run_index._SOURCE_DIGEST['refreshing']:
            break
        time.sleep(0.01)
    monkeypatch.setattr(sac, 'source_digest', digest)
    monkeypatch.setattr(run_index, '_SOURCE_DIGEST', dict(value=None, at=0.0, refreshing=False))
    assert run_index.current_source_digest() == 'first'                         # the first one: hashed at once
    assert run_index.current_source_digest(max_age=0.0) == 'first'              # older: answered at once, hashed in a thread
    assert run_index._SOURCE_DIGEST['refreshing'] and run_index.current_source_digest(max_age=0.0) == 'first'   # one thread at a time
    release.set()
    for _ in range(200):
        if not run_index._SOURCE_DIGEST['refreshing']:
            break
        time.sleep(0.01)
    assert run_index.current_source_digest() == 'second'


def test_a_started_job_gives_its_answer_or_its_error():
    assert runs._started(lambda: 41 + 1).result(5) == 42

    def fails():
        """Raise a fixture error from the background job."""
        raise ValueError('no git')
    with pytest.raises(ValueError, match='no git'):
        runs._started(fails).result(5)


def test_read_many_answers_in_the_order_asked():
    items = list(range(60))
    assert runs.read_many(lambda n: (time.sleep(0.002 * (n % 3)), n * n)[1], items) == [n * n for n in items]
    assert runs.read_many(str, [7]) == ['7'] and runs.read_many(str, []) == []


def test_the_saved_models_listings_read_many_at_a_time_are_those_read_one_by_one(tmp_path):
    for n in range(5):
        run = fabricate_run(tmp_path, f'r{n}', created=f'2026-10-08T10:0{n}:00+00:00')
        point = run / 'checkpoints' / f'ckpt-0000001{n}-a'
        point.mkdir(parents=True)
        write_json(point / 'metadata.json', dict(checkpoint_id=point.name, kind='periodic', created_utc='2026-10-08T10:10:00+00:00',
                                                 mode='scratch', counters=dict(evaluations_committed=10, learner_updates=10, replay_size=10),
                                                 restoration_capability='full_state', missing_components=[],
                                                 contract=dict(code_sha256='abc', model_config=dict(encoder_type='rgcn', hidden_dim=16, heads=2, layers=1))))
        write_json(run / 'checkpoints' / 'latest.json', dict(checkpoint_id=point.name))
    rows = runs.list_runs(roots_for(tmp_path), tmp_path)
    assert ckpt.saved_models(rows, runs.checkpoint_listings(rows)) == ckpt.saved_models(rows)
    assert [r['run_id'] for r in rows] == ['r4', 'r3', 'r2', 'r1', 'r0']
