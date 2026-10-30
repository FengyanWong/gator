"""Reliable writes (idempotent commits, interruption recovery, unfinished-partition isolation), the
shared budget ledger, and output-directory permissions / Windows-WSL path handling."""
import json
import os
from pathlib import Path
import threading

import pytest

from gator_workbench import layout as layout_module, paths
from gator_workbench.budget import BudgetError, BudgetLedger
from gator_workbench.storage import atomic, data_dictionary, DatasetReader, RawDataset, read_json, write_json
from gator_workbench.storage.tables import TABLES, arrow_schema, normalize_row
import subprocess


def metric_bundle(seq, *, value=0.5):
    """Build one identified synthetic metric bundle for storage commit checks."""
    key = f'e{seq:03d}'
    return dict(evaluation_id=key, commit_seq=seq, rows=dict(metrics=[dict(
        run_id='r', evaluation_id=key, measurement_id='m', metric_name='score', analysis=None, condition='nominal',
        raw_value=value, unit='fixture', valid=True, hard=True, satisfied=False, violation=0.4,
        aggregation_level='condition')]))


# ------------------------------------------------------------------------------- atomic files
def test_json_is_machine_readable_and_non_finite_becomes_null_with_a_reason(tmp_path):
    info = write_json(tmp_path / 'x.json', dict(a=float('nan'), b=[1.0, float('inf')], c=Path('/p'), d=(1, 2)))
    data = json.loads((tmp_path / 'x.json').read_text())            # strict JSON: would fail on NaN
    assert data['a'] is None and data['b'] == [1.0, None] and data['c'] == '/p' and data['d'] == [1, 2]
    assert data['_null_reasons'] == {'a': 'non_finite_number', 'b[1]': 'non_finite_number'} == info['null_reasons']
    with pytest.raises(TypeError):
        write_json(tmp_path / 'y.json', dict(bad=object()))         # never repr() of arbitrary objects
    with pytest.raises(TypeError):
        write_json(tmp_path / 'z.json', {('tuple', 'key'): 1})
    assert not list(tmp_path.glob(f'*{atomic.TEMP_MARKER}*'))


def test_read_json_default_none_is_honoured(tmp_path):
    assert read_json(tmp_path / 'missing.json', default=None) is None
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / 'missing.json')


def test_jsonl_ignores_a_torn_tail(tmp_path):
    log = atomic.JsonlAppender(tmp_path / 'l.jsonl')
    log.append(dict(n=1)); log.append(dict(n=2)); log.close()
    with (tmp_path / 'l.jsonl').open('a') as stream:
        stream.write('{"n": 3, "unfinished"')
    assert [r['n'] for r in atomic.read_jsonl(tmp_path / 'l.jsonl')] == [1, 2]


@pytest.mark.parametrize('prefix', [b'', b'{"n":1}\n'])
@pytest.mark.parametrize('tail', [b'{"unfinished"', b'\xe2\x82', b'x' * 140000, b'{"n":2}'])
def test_jsonl_repairs_only_unacknowledged_tail_before_append(tmp_path, prefix, tail):
    path = tmp_path / 'log.jsonl'
    path.write_bytes(prefix + tail)
    before = atomic.read_jsonl(path)
    log = atomic.JsonlAppender(path)
    try:
        log.append(dict(n=3, text='μ電路'))
    finally:
        log.close()
    assert path.read_bytes().startswith(prefix)
    assert atomic.read_jsonl(path) == before + [dict(n=3, text='μ電路')]


def test_complete_corrupt_journal_record_is_not_silently_skipped(tmp_path):
    path = tmp_path / 'log.jsonl'
    original = b'{"n":1}\ninvalid\n{"n":2}\n'
    path.write_bytes(original)
    with pytest.raises(atomic.PersistenceError, match='line 2'):
        atomic.read_jsonl(path)
    assert path.read_bytes() == original


@pytest.mark.parametrize('journal', ['wal.jsonl', 'flushes.jsonl'])
def test_commit_after_crash_survives_compaction_and_second_restart(tmp_path, journal):
    root = tmp_path / 'data'
    data = RawDataset(root, flush_every=1)
    data.commit(metric_bundle(1)); data.close()
    with (root / '_journal' / journal).open('ab') as stream:
        stream.write(b'{"unfinished": "\xe2\x82')
    recovered = RawDataset(root, flush_every=100)
    assert recovered.commit(metric_bundle(2))
    # Another crash before the new acknowledgement reaches Parquet must work too.
    recovered._wal.close(); recovered._flush_log.close()
    recovered = RawDataset(root, flush_every=100)
    assert recovered.has('e002')
    recovered.flush(); recovered.compact_journal(); recovered.close()
    reopened = RawDataset(root, flush_every=1)
    assert reopened.has('e002') and not reopened.recovery['quarantined_parts']
    assert reopened.commit(metric_bundle(2)) is False
    assert reopened.commit(metric_bundle(3))
    reopened.close()
    reader = DatasetReader(root)
    assert [r['evaluation_id'] for r in reader.rows('metrics')] == ['e001', 'e002', 'e003']
    assert reader.verify() == []


def test_only_registered_temporaries_are_removed(tmp_path):
    keep = tmp_path / 'model.pt'; keep.write_text('model')
    temp = tmp_path / f'part.parquet{atomic.TEMP_MARKER}abc'; temp.write_text('x')
    assert atomic.remove_registered_temporaries(tmp_path) == [str(temp)]
    assert keep.exists() and not temp.exists()


# ------------------------------------------------------------------------------- dataset
def test_commits_are_idempotent_and_sequenced(tmp_path):
    data = RawDataset(tmp_path / 'data', flush_every=100)
    assert data.commit(metric_bundle(1)) is True
    assert data.commit(metric_bundle(1)) is False              # same evaluation again: no-op
    with pytest.raises(ValueError):
        data.commit(metric_bundle(3))                          # gaps are rejected
    with pytest.raises(KeyError):
        data.commit(dict(evaluation_id='x', commit_seq=2, rows=dict(metrics=[dict(bogus_column=1)])))
    data.commit(metric_bundle(2)); data.close()
    reader = DatasetReader(tmp_path / 'data')
    assert [r['evaluation_id'] for r in reader.rows('metrics')] == ['e001', 'e002'] and reader.verify() == []


def test_acknowledged_results_survive_a_crash_without_double_counting(tmp_path):
    data = RawDataset(tmp_path / 'data', flush_every=2)
    for seq in (1, 2, 3):
        data.commit(metric_bundle(seq))                         # 1-2 flushed to a part, 3 only journaled
    assert data.status()['flushed_seq'] == 2 and data.status()['buffered_bundles'] == 1
    data._wal.close(); data._flush_log.close()                  # simulate process death: no close(), no flush
    recovered = RawDataset(tmp_path / 'data', flush_every=2)
    assert recovered.recovery['rebuffered_bundles'] == 1 and recovered.has('e003')
    assert recovered.commit(metric_bundle(3)) is False          # not counted twice
    recovered.commit(metric_bundle(4)); recovered.close()
    ids = [r['evaluation_id'] for r in DatasetReader(tmp_path / 'data').rows('metrics')]
    assert ids == ['e001', 'e002', 'e003', 'e004']


def test_unfinished_partitions_are_quarantined_not_read(tmp_path):
    import pyarrow as pa, pyarrow.parquet as pq
    data = RawDataset(tmp_path / 'data', flush_every=1)
    data.commit(metric_bundle(1)); data.close()
    orphan = tmp_path / 'data' / 'metrics' / 'part-000002.parquet'      # published but never listed by a flush record
    row = normalize_row('metrics', metric_bundle(2)['rows']['metrics'][0])
    pq.write_table(pa.Table.from_pylist([row], schema=arrow_schema('metrics')), orphan)
    (tmp_path / 'data' / 'metrics' / f'part-000003.parquet{atomic.TEMP_MARKER}zz').write_text('partial')
    assert len(DatasetReader(tmp_path / 'data').rows('metrics')) == 1      # readers ignore unlisted parts
    reopened = RawDataset(tmp_path / 'data')
    assert reopened.recovery['quarantined_parts'] == ['_quarantine/metrics__part-000002.parquet']
    assert len(reopened.recovery['removed_temporaries']) == 1 and not orphan.exists()
    reopened.close()


def test_reader_gives_a_fixed_snapshot_at_a_cutoff(tmp_path):
    data = RawDataset(tmp_path / 'data', flush_every=2)
    for seq in range(1, 7):
        data.commit(metric_bundle(seq))
    data.close()
    assert len(DatasetReader(tmp_path / 'data', cutoff_seq=4).rows('metrics')) == 4
    assert DatasetReader(tmp_path / 'data').cutoff_seq == 6
    empty = DatasetReader(tmp_path / 'data').table('transitions')
    assert empty.num_rows == 0 and empty.schema.names == [c.name for c in TABLES['transitions']['columns']]


def test_a_failed_writer_refuses_further_commits(tmp_path, monkeypatch):
    data = RawDataset(tmp_path / 'data', flush_every=1)

    def broken(*args, **kwargs):
        """Raise a full-disk error from the fixture writer."""
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr('pyarrow.parquet.write_table', broken)
    with pytest.raises(atomic.PersistenceError):
        data.commit(metric_bundle(1))
    assert 'No space left' in data.status()['failed']
    with pytest.raises(atomic.PersistenceError):
        data.commit(metric_bundle(2))                           # no silent continuation while losing data


def test_data_dictionary_documents_types_units_enums_and_null(tmp_path):
    dictionary = data_dictionary()
    assert set(dictionary['tables']) == {'evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates',
                                         'transitions', 'states', 'llm_calls'}
    for name, table in dictionary['tables'].items():
        assert [c['name'] for c in table['columns']] == arrow_schema(name).names
        for column in table['columns']:
            assert column['description'] and (column['nullable'] is False or column['null_meaning'])
    columns = {c['name']: c for c in dictionary['tables']['evaluations']['columns']}
    assert 'baseline' in columns['phase']['enum'] and columns['provenance']['enum'] == ['real', 'mock']
    assert columns['queue_seconds']['unit'] == 's'
    assert columns['llm_call_id']['nullable'] and columns['llm_call_id']['null_meaning']
    assert 'never' in columns['all_hard_constraints_satisfied']['description'].lower()


# ------------------------------------------------------------------------------- budget ledger
def test_reserve_charge_release_semantics():
    ledger = BudgetLedger(3)
    a, b, _ = ledger.reserve(), ledger.reserve(), ledger.reserve()
    assert ledger.reserve() is None and ledger.remaining() == 0          # all workers share one budget
    assert ledger.charged == 0                                            # a reservation is not a charge
    assert ledger.start(a) == 1 and ledger.charged == 1                   # charged when execution begins
    ledger.release(b)                                                     # cancelled before it started: refunded
    assert ledger.remaining() == 1 and ledger.snapshot()['released'] == 1
    with pytest.raises(BudgetError):
        ledger.release(a)                                                 # a started evaluation is never refunded
    ledger.begin_attempt(a); ledger.end_attempt(a, launches=1)
    ledger.complete(a, failed=True)
    assert ledger.charged == 1 and ledger.snapshot()['failed'] == 1       # failures stay charged
    with pytest.raises(BudgetError):
        ledger.start('never-reserved')


def test_retries_keep_the_evaluation_and_add_launches():
    ledger = BudgetLedger(5, max_retries=2)
    e = ledger.reserve(); ledger.start(e)
    assert ledger.begin_attempt(e) == 1; ledger.end_attempt(e, launches=1)
    assert ledger.may_retry(e)
    assert ledger.begin_attempt(e) == 2; ledger.end_attempt(e, launches=1)
    assert ledger.begin_attempt(e) == 3; ledger.end_attempt(e, launches=0)    # failed before reaching the simulator
    assert not ledger.may_retry(e)
    with pytest.raises(BudgetError):
        ledger.begin_attempt(e)
    ledger.complete(e)
    snapshot = ledger.snapshot()
    assert (snapshot['charged'], snapshot['launches'], snapshot['retries']) == (1, 2, 2)


def test_hard_launch_limit_blocks_new_evaluations_and_retries():
    ledger = BudgetLedger(10, max_launches=2, max_retries=5)
    a = ledger.reserve(); ledger.start(a); ledger.begin_attempt(a); ledger.end_attempt(a, launches=1)
    b = ledger.reserve()
    assert b is not None and ledger.reserve() is None                     # the second launch slot is spoken for
    assert not ledger.may_retry(a)
    ledger.start(b); ledger.begin_attempt(b); ledger.end_attempt(b, launches=1); ledger.complete(b); ledger.complete(a)
    assert ledger.reserve() is None and ledger.launches == 2


def test_cache_hits_are_never_simulations():
    ledger = BudgetLedger(2)
    e = ledger.reserve(); ledger.start(e); ledger.begin_attempt(e); ledger.end_attempt(e, launches=1)
    with pytest.raises(BudgetError):
        ledger.complete(e, cache_hit=True)


def test_first_feasible_counts_in_flight_evaluations_and_is_recorded_once():
    ledger = BudgetLedger(10)
    ids = [ledger.reserve() for _ in range(4)]
    for e in ids:
        ledger.start(e); ledger.begin_attempt(e)
    ledger.end_attempt(ids[2], launches=1); ledger.complete(ids[2])       # the THIRD dispatched finishes first
    first = ledger.mark_first_feasible(ids[2], dispatch_index=3, commit_seq=1, active_seconds=1.5, wall_seconds=2.0)
    assert first['first_feasible_eval_count'] == 4                        # includes the three still running
    assert (first['dispatch_index'], first['completed_count'], first['in_flight_count']) == (3, 1, 3)
    assert sorted(first['in_flight_evaluation_ids']) == sorted(e for e in ids if e != ids[2])
    assert ledger.mark_first_feasible(ids[0], dispatch_index=1, commit_seq=2, active_seconds=3, wall_seconds=3) is None


def test_ledger_is_thread_safe_and_never_overspends():
    ledger, started = BudgetLedger(50), []

    def worker():
        """Reserve and complete single-launch evaluations until the shared budget is exhausted."""
        while (e := ledger.reserve()) is not None:
            started.append(ledger.start(e)); ledger.begin_attempt(e); ledger.end_attempt(e, launches=1); ledger.complete(e)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(started) == list(range(1, 51)) and ledger.charged == 50 and ledger.launches == 50


def test_ledger_state_roundtrip_and_reconcile_never_lowers_counters():
    ledger = BudgetLedger(10)
    e = ledger.reserve(); ledger.start(e)
    with pytest.raises(BudgetError):
        ledger.state_dict()                                               # only at a quiescent boundary
    ledger.begin_attempt(e); ledger.end_attempt(e, launches=1); ledger.complete(e)
    restored = BudgetLedger(20)                                           # resume may extend the budget
    restored.load_state(ledger.state_dict())
    assert restored.charged == 1 and restored.remaining() == 19           # resume keeps existing counters
    restored.reconcile(charged=4, completed=4, failed=1, launches=5, retries=1, cache_hits=0)
    assert (restored.charged, restored.launches) == (4, 5)
    restored.reconcile(charged=2, completed=2, failed=0, launches=1, retries=0, cache_hits=0)
    assert (restored.charged, restored.launches) == (4, 5)


# ------------------------------------------------------------------------------- output paths
def test_the_default_output_root_can_be_another_folder(tmp_path, monkeypatch):
    """Record 7.276: the browser checks' scratch backends list an empty folder of their own, not the user's runs."""
    monkeypatch.delenv(paths.ENV_DEFAULT_OUTPUT_ROOT, raising=False)
    assert paths.default_output_root() == paths.repo_root() / 'outputs'
    monkeypatch.setenv(paths.ENV_DEFAULT_OUTPUT_ROOT, str(tmp_path))
    assert paths.default_output_root() == tmp_path and paths.OutputRoots().roots[0] == tmp_path.resolve()


def test_only_operator_allowed_roots_are_usable(tmp_path):
    allowed, outside = tmp_path / 'allowed', tmp_path / 'outside'
    allowed.mkdir(); outside.mkdir()
    roots = paths.OutputRoots([allowed], include_default=False)
    assert roots.resolve(allowed / 'sub') == allowed / 'sub'
    for bad in (outside, allowed / '..' / 'outside', Path('relative/path')):
        with pytest.raises(paths.PathNotAllowed):
            roots.resolve(bad)
    (allowed / 'link').symlink_to(outside)
    with pytest.raises(paths.PathNotAllowed):
        roots.resolve(allowed / 'link' / 'x')                             # symlink escape
    assert roots.check(outside)['allowed'] is False
    with pytest.raises(paths.PathNotAllowed):
        roots.browse(outside)
    assert [e['name'] for e in roots.browse(allowed)['entries']] == []    # symlinks are not offered


def test_writability_is_tested_not_assumed(tmp_path):
    root = tmp_path / 'out'; root.mkdir()
    roots = paths.OutputRoots([root], include_default=False)
    good = roots.check(root, verify_windows=False)
    assert good['writable'] is True and good['free_bytes'] > 0 and good['filesystem'] != 'unknown'
    assert not list(root.iterdir())                                       # the probe file is removed again
    if os.geteuid() != 0:
        root.chmod(0o555)
        try:
            denied = roots.check(root, verify_windows=False)
            assert denied['writable'] is False and 'Permission' in denied['error']
        finally:
            root.chmod(0o755)
    missing = roots.check(root / 'later', verify_windows=False)
    assert missing['exists'] is False and missing['writable_basis'] == 'parent_directory_permission_only'


def test_windows_path_is_reported_only_after_readback(tmp_path, monkeypatch):
    root = tmp_path / 'out'; root.mkdir()
    roots = paths.OutputRoots([root], include_default=False)
    monkeypatch.setattr(paths.shutil, 'which', lambda name: None)         # no WSL interop (remote Linux host)
    result = roots.check(root)
    assert result['windows_path'] is None and result['windows_mapping'] == 'unavailable_no_wsl_interop'

    class Completed:
        """A minimal subprocess result for Windows-path verification."""
        def __init__(self, out, code=0):
            self.stdout, self.returncode = out, code
    monkeypatch.setattr(paths.shutil, 'which', lambda name: f'/fake/{name}')

    def translated_but_unreadable(command, **kwargs):
        """Return a translated Windows path whose readback command fails."""
        return Completed('X:\\guess\\out\n') if 'wslpath' in command[0] else Completed('', 1)
    monkeypatch.setattr(paths.subprocess, 'run', translated_but_unreadable)
    result = paths.OutputRoots([root], include_default=False).check(root)
    assert result['windows_path'] is None and result['windows_mapping'] == 'translation_not_verified'

    def verified(command, **kwargs):
        """Return a translated Windows path and the actual writable-probe token."""
        if 'wslpath' in command[0]:
            return Completed('D:\\out\n')
        return Completed(next(root.glob('.writable*')).read_text())      # Windows really sees the token
    monkeypatch.setattr(paths.subprocess, 'run', verified)
    result = paths.OutputRoots([root], include_default=False).check(root)
    assert result['windows_path'] == 'D:\\out' and result['windows_mapping'] == 'verified_by_readback'


def test_mock_root_is_isolated(tmp_path):
    root = tmp_path / 'out'; root.mkdir()
    roots = paths.OutputRoots([root], include_default=False)
    assert roots.data_root(root, mock=True) == root / 'mock' and roots.data_root(root, mock=False) == root
    with pytest.raises(paths.PathNotAllowed):
        roots.data_root(root / 'mock', mock=False)                        # a real run cannot target the mock root
    assert paths.is_mock_path(root / 'mock' / 'e__1') and not paths.is_mock_path(root / 'e__1')


def test_safe_child_blocks_traversal(tmp_path):
    (tmp_path / 'run').mkdir()
    assert paths.safe_child(tmp_path / 'run', 'data/x.parquet') == tmp_path / 'run' / 'data' / 'x.parquet'
    with pytest.raises(paths.PathNotAllowed):
        paths.safe_child(tmp_path / 'run', '../secret')


def publish_with(tmp_path):
    """(destination, publish): `publish()` puts our file over settings.json. What happens right after our rename is
    staged by replacing `atomic.fsync_directory`, the step that follows it."""
    destination = tmp_path / 'settings.json'
    destination.write_text('{"old": 1}')
    temporary = atomic.temporary_path(destination)
    temporary.write_text('{"ours": 1}')
    return destination, lambda: atomic.publish(temporary, destination)


def test_a_newer_complete_replacement_is_no_write_failure(tmp_path, monkeypatch):
    destination, publish = publish_with(tmp_path)
    real_fsync = atomic.fsync_directory

    def another_writer_lands(path):
        """Replace the destination with a newer complete file after the original sync."""
        real_fsync(path)
        newer = atomic.temporary_path(destination)
        newer.write_text('{"a newer writer": "longer"}')
        os.replace(newer, destination)
    monkeypatch.setattr(atomic, 'fsync_directory', another_writer_lands)
    assert publish() == len('{"ours": 1}')
    assert json.loads(destination.read_text()) == {'a newer writer': 'longer'}


def test_our_own_incomplete_or_missing_file_is_still_a_write_failure(tmp_path, monkeypatch):
    destination, publish = publish_with(tmp_path)
    real_fsync = atomic.fsync_directory

    def grows_in_place(path):                     # the SAME file (inode) with another size: not a newer writer's file
        """Change the just-synced destination in place without replacing its inode."""
        real_fsync(path)
        with destination.open('a') as stream:
            stream.write(' ')
    monkeypatch.setattr(atomic, 'fsync_directory', grows_in_place)
    with pytest.raises(atomic.PersistenceError, match='size'):
        publish()
    destination, publish = publish_with(tmp_path)
    monkeypatch.setattr(atomic, 'fsync_directory', lambda path: destination.unlink())
    with pytest.raises(atomic.PersistenceError, match='not visible'):   # the 9p retry still ends in a failure when it stays gone
        publish()


# ------------------------------------------------------------------------------- B3: the output-folder size walk
def rglob_bytes(path):
    """The walk directory_bytes replaced, kept here as the reference its totals must equal."""
    total = 0
    path = Path(path)
    if not path.exists():
        return 0
    for child in path.rglob('*'):
        try:
            if child.is_file() and not child.is_symlink():
                total += child.stat().st_size
        except OSError:
            pass
    return total


def test_the_size_walk_counts_exactly_what_the_old_one_did(tmp_path):
    outside = tmp_path / 'outside'
    (outside / 'deep').mkdir(parents=True)
    (outside / 'big.bin').write_bytes(b'x' * 5000)
    (outside / 'deep' / 'more.bin').write_bytes(b'y' * 700)
    root = tmp_path / 'root'
    for index, folder in enumerate(('a', 'a/b', 'a/b/c', '.hidden', 'unreadable', 'listable_only', 'empty')):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / f'file{index}.txt').write_bytes(b'z' * (10 * index + 3))
        (root / folder / '.dotfile').write_bytes(b'd' * (index + 1))
    (root / 'a' / 'link_to_file').symlink_to(outside / 'big.bin')          # never counted
    (root / 'a' / 'link_to_dir').symlink_to(outside)                       # never followed
    (root / 'a' / 'b' / 'dangling').symlink_to(tmp_path / 'nowhere')
    (root / 'a' / 'b' / 'hard_link').hardlink_to(root / 'a' / 'file0.txt')
    os.mkfifo(root / 'a' / 'pipe')                                         # not a regular file
    (root / 'unreadable' / 'inner').mkdir()
    (root / 'unreadable' / 'inner' / 'secret.bin').write_bytes(b's' * 999)
    os.chmod(root / 'unreadable', 0o000)
    os.chmod(root / 'listable_only', 0o444)                                # listed, but its entries cannot be stat'ed
    (tmp_path / 'root_link').symlink_to(root)
    try:
        for path in (root, root / 'a', root / 'a' / 'b', root / 'empty', tmp_path / 'root_link', tmp_path / 'root_link' / 'a',
                     root / 'a' / 'link_to_dir', root / 'a' / 'file0.txt', root / 'a' / 'link_to_file', root / 'nothing_here',
                     root / 'a' / 'b' / 'dangling', root / 'unreadable', root / 'listable_only', outside):
            assert paths.directory_bytes(path) == rglob_bytes(path), path
        assert paths.directory_bytes(root) > 0
    finally:
        os.chmod(root / 'unreadable', 0o755)
        os.chmod(root / 'listable_only', 0o755)


# ------------------------------------------------------------------------------- B10: git without optional locks
def test_the_run_provenance_asks_git_without_taking_the_index_lock(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        """Record git commands and return fixture revision or dirty-status output."""
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=' M file.py\n' if 'status' in argv else 'abc123\n', stderr='')
    monkeypatch.setattr(layout_module.subprocess, 'run', fake_run)
    provenance = layout_module.code_provenance()
    status = next(argv for argv in calls if 'status' in argv)
    assert status[:3] == ['git', '-C', str(paths.repo_root())] and status[3:] == ['--no-optional-locks', 'status', '--porcelain']
    assert provenance['git_dirty'] is True and provenance['git_dirty_paths'] == 1


def test_a_json_file_is_fsynced_once(tmp_path, monkeypatch):
    from gator_workbench.storage import atomic
    calls, real = [], os.fsync
    monkeypatch.setattr(os, 'fsync', lambda fd: calls.append(fd) or real(fd))
    atomic.write_json(tmp_path / 'a.json', dict(value=1))
    assert len(calls) == 2                                                       # the file's bytes, then its directory
    assert [p.name for p in tmp_path.iterdir()] == ['a.json'] and read_json(tmp_path / 'a.json') == dict(value=1)
