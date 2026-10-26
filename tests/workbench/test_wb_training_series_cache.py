"""Record 7.221: the Training tab's reader keeps what it read and reads only what changed - every answer equals the oracle's (training_series_support), while the run grows, is cut, resumed or polled concurrently (refactoring package D4: from test_wb_training_series)."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import threading
import time

import pytest

from gator_workbench import training_series
from gator_workbench.storage import RawDataset, read_json, write_json
from gator_workbench.storage.atomic import read_jsonl

from helpers import make_config, workbench_app
from training_series_support import (agree, agreed, CHART_TABLES, fresh_caches, liveness, outcome, Page, reference_learner_record, reference_read_training, reference_run_objective, SyntheticRun, T0)


def test_objective_and_learner_helpers_answer_as_before(tmp_path):
    """run_objective and learner_record, kept for callers that use them alone, read their files as they did."""
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    config = make_config(tmp_path).model_dump(mode='json')
    config['targets'][0].update(direction_after_feasible='minimize', upper=10.0)
    for text in (None, 'null', '[]', '[1]', '{}', '{"run": ', json.dumps(config),
                 json.dumps(dict(output=dict(save_learner_updates=False, learner_update_log_every=3)))):
        for manifest in (None, '{}', '{"mode": "frozen"}', '[1]', '{"run_kind": "baseline_preflight"}',
                         '{"run_kind": "calibration", "mode": "frozen"}', '{"run_kind": "optimization"}'):
            for name, value in (('effective_config.json', text), ('run_manifest.json', manifest)):
                (run_dir / name).unlink(missing_ok=True)
                if value is not None:
                    (run_dir / name).write_text(value, encoding='utf8')
            assert outcome(lambda: training_series.run_objective(run_dir)) == outcome(lambda: reference_run_objective(run_dir))
            assert outcome(lambda: training_series.learner_record(run_dir)) == outcome(lambda: reference_learner_record(run_dir))
    assert training_series.run_objective(run_dir) is None
    (run_dir / 'effective_config.json').write_text(json.dumps(config), encoding='utf8')
    assert training_series.run_objective(run_dir) == dict(metric='score', direction='min')


def test_a_baseline_or_calibration_run_says_it_trains_no_model(tmp_path):
    """Record 7.292: a Baseline simulation or a Calibration run never makes a learner update - the Training tab says why
    instead of waiting for updates that cannot come."""
    for kind, start in (('baseline_preflight', 'A Baseline simulation measures'), ('calibration', 'A Calibration run simulates')):
        record = training_series._learner(dict(output=dict(learner_update_log_every=2)), dict(run_kind=kind))
        assert record == dict(recorded=False, every=2, reason=training_series.NO_LEARNER[kind])
        assert record['reason'].startswith(start) and record['reason'].endswith('so no losses, temperature or entropy.')
    assert training_series._learner({}, dict(run_kind='optimization')) == dict(recorded=True, every=1, reason=None)


def test_torn_and_corrupt_flush_records_answer_as_read_jsonl_reads_them(tmp_path, liveness):
    run = SyntheticRun(tmp_path / 'run')
    for _ in range(3):
        run.commit(2)
        run.flush()
    lines = run.log.read_bytes().splitlines(keepends=True)
    page = Page(run.path)
    run.log.write_bytes(b''.join(lines[:2]) + lines[2][:30])            # the third record half written (in place)
    assert page.poll()['flushes']['total'] == 2
    with run.log.open('ab') as stream:
        stream.write(lines[2][30:])                                     # ... and finished
    assert page.poll()['flushes']['total'] == 3
    with run.log.open('ab') as stream:
        stream.write(b'\n  \n')                                         # blank lines: skipped, and counted as lines
    page.poll()
    with run.log.open('ab') as stream:
        stream.write(b'{"flush_id": 4, not json}\n')
    error = agree(run.path, page.flushes, page.tail_cursor)
    assert error == ('error', 'PersistenceError', f'Corrupt JSONL record in {run.log} at line 6')
    run.commit(2)
    run.flush()                                                         # the writer appends after it: the same error
    assert agree(run.path, page.flushes, page.tail_cursor) == error == agree(run.path)
    assert training_series.cache_stats()['flush_runs'] == 0            # nothing kept of a log that fails
    run.log.write_bytes(run.log.read_bytes().replace(b'{"flush_id": 4, not json}\n', b''))   # taken out, in place
    assert page.poll()['flushes']['total'] == 4
    run.assert_whole(page)
    # Complete lines that are JSON but no flush record fail where they always failed, or are read as they always were.
    good = run.log.read_bytes()
    for odd in (b'[1, 2]\n', b'"text"\n', b'{"flush_id": 9}\n', b'{"flush_id": 9, "rows": [], "parts": {}, "last_seq": 8}\n',
                b'{"flush_id": 5, "first_seq": 9, "last_seq": 9, "parts": {}, "rows": {}, "extra": 1}\n'):
        run.log.write_bytes(good + odd)
        for flushes in (0, 3, 4, 5):
            agree(run.path, flushes)
    run.log.write_bytes(good)
    page.poll()
    run.assert_whole(page)


def test_replaced_cut_or_remade_logs_are_read_again(tmp_path, liveness, monkeypatch):
    """A flush log is append-only. Anything else that happens to it is noticed and the log read again whole: an atomic
    replacement, a cut, a change in place at the same size (its times), in its first or in its last read bytes (the
    anchors), the run deleted and made again at the same path. Each change shows in the answers, which agree."""
    monkeypatch.setattr(training_series, '_ANCHOR', 256)               # small anchors: a 12-record log has a middle
    run = SyntheticRun(tmp_path / 'run', updates=1)
    for _ in range(12):
        run.commit(1)
        run.flush()
    log, lines = run.log, run.log.read_bytes().splitlines(keepends=True)
    assert len(lines) == 12 and log.stat().st_size > 6 * 256

    def answers():
        """Compare cached and reference answers from several flush cursors."""
        for flushes in (0, 2, 5, 11):
            agree(run.path, flushes)
        return agreed(run.path)

    def rebuilt():
        """Return the number of flush-cache rebuilds recorded by the reader."""
        return training_series.cache_stats()['flush_rebuilt']

    def rewrite(content, *, keep_times=False):
        """Replace the journal's contents in place with optional access and modification time preservation."""
        before = log.stat()
        time.sleep(0.02)                                                # a later clock tick, on coarse-grained file times
        with log.open('r+b') as stream:
            stream.write(content)
            stream.truncate()
        if keep_times:                                                  # the change time cannot be put back
            os.utime(log, ns=(before.st_atime_ns, before.st_mtime_ns))

    def step(change, *, read_again=True):
        """The answers after `change` (all agreeing), and whether the log was read whole again for them."""
        before = rebuilt()
        change()
        result = answers()
        assert rebuilt() == before + read_again
        return result

    original = answers()
    swap = log.with_name('swap')
    swap.write_bytes(b''.join(lines[:8]))
    assert step(lambda: os.replace(swap, log))['flushes']['total'] == 8   # an atomic replacement, fewer records

    def cut():
        """Truncate the journal after the fixture's first five records."""
        with log.open('r+b') as stream:
            stream.truncate(len(b''.join(lines[:5])))
    assert step(cut)['flushes']['total'] == 5                          # cut in place
    assert step(lambda: rewrite(b''.join(lines)), read_again=False) == original    # grown back: the same first bytes

    # In place, the same size: a middle record names flush 4's parts. Only the times tell (the modification time kept).
    middle = lines[2].replace(b'part-000003.parquet', b'part-000004.parquet')
    assert middle != lines[2] and len(middle) == len(lines[2])
    assert 256 < len(b''.join(lines[:2])) and len(b''.join(lines[:3])) < log.stat().st_size - 256
    changed = step(lambda: rewrite(b''.join(lines[:2] + [middle] + lines[3:]), keep_times=True))
    assert changed != original and changed['final']['evaluations']['commit_seq'][:5] == [1, 2, 4, 4, 5]
    assert step(lambda: rewrite(b''.join(lines))) == original          # put back: the same size, other times

    # In place and longer: the first record changed (the head anchor), then the last record read (the tail anchor).
    first = lines[0].replace(b'part-000001.parquet', b'part-000002.parquet')
    head = step(lambda: rewrite(b''.join([first] + lines[1:] + [lines[11]])))
    assert head['final']['evaluations']['commit_seq'][:3] == [2, 2, 3] and head['flushes']['total'] == 13
    last = lines[11].replace(b'part-000012.parquet', b'part-000011.parquet')
    tail = step(lambda: rewrite(b''.join([first] + lines[1:] + [last] + [lines[10]])))
    assert tail['final']['evaluations']['commit_seq'][-3:] == [11, 11, 11] and tail['flushes']['total'] == 14

    # Missing for one answer (a moment of a replacement on the 9p mount): no flush records then, and not kept so.
    log.rename(log.with_name('aside'))
    assert agreed(run.path)['flushes']['total'] == 0 and training_series.cache_stats()['flush_runs'] == 0
    assert step(lambda: log.with_name('aside').rename(log))['flushes']['total'] == 14

    # The run deleted (its answer: no run data, as before), then made again at the same path: another run's answers.
    def remake():
        """Replace the run with different synthetic values at the same directory path."""
        run.dataset.close()
        shutil.rmtree(run.path)
        assert agree(run.path) == ('error', 'FileNotFoundError', 'This folder holds no recorded run data.')
        again = SyntheticRun(run.path, seed=1, updates=1)
        for _ in range(12):
            again.commit(1)
            again.flush()
    remade = step(remake)
    assert remade['run_id'] != original['run_id']
    assert remade['final']['evaluations']['execution_seconds'] == [s + 1 / 8 for s in range(1, 13)]


def test_a_resumed_writer_cuts_a_torn_record_and_the_reader_reads_on(tmp_path, liveness):
    """A worker killed in the middle of a flush record leaves it torn; the resumed worker's dataset cuts it off when it
    opens the log and appends its next record there. The page reads on, never the log whole again."""
    run = SyntheticRun(tmp_path / 'run')
    for _ in range(2):
        run.commit(3)
        run.flush()
    run.commit(2)                                                       # journaled, not flushed: the page's tail
    page = Page(run.path, max_rows=12)
    page.poll()
    run.dataset.close()                                                 # closing flushes the two bundles
    complete = run.log.read_bytes()
    with run.log.open('ab') as stream:
        stream.write(complete.splitlines(keepends=True)[-1][:50])       # the crash: a flush record half written
    assert page.poll()['flushes']['total'] == 3                         # the torn record is not one
    run.dataset = RawDataset(run.path / 'data', enabled_tables=CHART_TABLES, flush_every=10 ** 9)   # resumed
    assert run.log.read_bytes() == complete                             # reopening cut the torn line off
    manifest = read_json(run.path / 'run_manifest.json')
    manifest['segments'].append(dict(segment=2, entry='resume', started_utc=T0.isoformat()))
    write_json(run.path / 'run_manifest.json', manifest)
    page.poll()
    run.commit(3)
    page.poll()
    run.flush()
    answer = page.poll()
    assert [s['entry'] for s in answer['segments']] == ['start', 'resume'] and answer['flushes']['total'] == 4
    run.assert_whole(page)
    assert training_series.cache_stats()['flush_rebuilt'] == 1


@pytest.mark.parametrize('tight', [False, True], ids=['room', 'one-run-caches'])
def test_concurrent_answers_agree_with_one_answer_at_a_time(tmp_path, liveness, monkeypatch, tight):
    """Eight threads answer polls of three runs at once - from the start, from the last flush, at the end with and
    without a tail cursor - each round after the runs grew (a flush, a compaction). Every answer is the one the reader
    before 7.221 gives alone; also when each cache holds one run, so that entries are evicted while read."""
    if tight:
        monkeypatch.setattr(training_series, 'FLUSH_INDEX_RUNS', 1)
        monkeypatch.setattr(training_series, 'CONFIG_CACHE_RUNS', 1)
    synthetic = [SyntheticRun(tmp_path / f'run{i}', seed=i) for i in range(3)]
    with ThreadPoolExecutor(8) as pool:
        for round_ in range(5):
            for i, run in enumerate(synthetic):
                run.commit(2 + i)
                if (round_ + i) % 2:
                    run.flush()
                if round_ == 3:
                    run.compact()
            polls = []
            for run in synthetic:
                total = len(read_jsonl(run.log))
                polls += [(run.path, flushes, None) for flushes in sorted({0, max(0, total - 1), total})]
                polls.append((run.path, total, reference_read_training(run.path, total)['tail_page']['cursor']))
            want = [outcome(lambda p=p: reference_read_training(p[0], p[1], max_rows=20, tail_cursor=p[2])) for p in polls]
            got = list(pool.map(lambda p: outcome(lambda: training_series.read_training(p[0], p[1], max_rows=20,
                                                                                        tail_cursor=p[2])), polls * 8))
            assert got == want * 8
    stats = training_series.cache_stats()
    assert stats['flush_runs'] == (1 if tight else 3) and (stats['flush_evictions'] > 0) == tight


def test_pages_polled_while_the_run_grows_get_every_row_once(tmp_path, liveness):
    """Four pages poll one run as fast as they can while its writer journals, flushes and compacts, and three other runs
    are polled beside it: each page ends with every recorded row once, and its last answer is the uncached one."""
    run = SyntheticRun(tmp_path / 'live')
    others = [SyntheticRun(tmp_path / f'other{i}', seed=i) for i in range(3)]
    for other in others:
        other.commit(5)
        other.flush()
    done, errors = threading.Event(), []

    def write():
        """Append, publish and compact fixture rows while retaining any writer failure."""
        try:
            for step in range(60):
                run.commit(1)
                if step % 5 == 4:
                    run.flush()
                if step % 17 == 16:
                    run.compact()
            run.flush()
        except Exception as exc:                                        # the test fails with it below
            errors.append(exc)
        finally:
            done.set()

    def read(page):
        """Poll a page during writing and once after completion, retaining any reader failure."""
        try:
            while not done.is_set():
                page.poll()
            page.poll()                                                 # once more after the worker ended, as the page does
        except Exception as exc:
            errors.append(exc)

    pages = [Page(run.path, max_rows=30, check=False) for _ in range(4)]
    beside = [Page(other.path, max_rows=30, check=False) for other in others]
    threads = [threading.Thread(target=read, args=(page,)) for page in pages + beside] + [threading.Thread(target=write)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
    assert not errors and not any(thread.is_alive() for thread in threads)
    for page in pages:
        run.assert_whole(page)
        assert page.answers[-1] == agreed(run.path, page.answers[-1]['flushes']['start'], page.answers[-1]['tail_page']['start'], 30)
    for other, page in zip(others, beside):
        other.assert_whole(page)


def test_eviction_and_clearing_change_only_what_an_answer_costs(tmp_path, liveness, monkeypatch):
    monkeypatch.setattr(training_series, 'FLUSH_INDEX_RUNS', 2)
    monkeypatch.setattr(training_series, 'CONFIG_CACHE_RUNS', 1)
    synthetic = [SyntheticRun(tmp_path / f'run{i}', seed=i) for i in range(4)]
    pages = [Page(run.path, max_rows=25) for run in synthetic]
    for round_ in range(4):
        for run, page in zip(synthetic, pages):
            run.commit(3)
            if round_ % 2:
                run.flush()
            page.poll()
    stats = training_series.cache_stats()
    assert stats['flush_evictions'] > 0 and stats['flush_runs'] == 2
    assert stats['config_evictions'] > 0 and stats['config_runs'] == 1
    monkeypatch.setattr(training_series, 'FLUSH_INDEX_BYTES', 300)     # a log larger than the whole cache: read as before
    for run, page in zip(synthetic, pages):
        run.commit(2)
        run.flush()
        page.poll()
    stats = training_series.cache_stats()
    assert stats['flush_runs'] == 0 and stats['flush_fallbacks'] >= 4
    monkeypatch.setattr(training_series, 'FLUSH_INDEX_BYTES', 16 << 20)
    training_series.clear_caches()
    for run, page in zip(synthetic, pages):
        run.commit(1)
        page.poll()
        run.assert_whole(page)


def test_cached_answers_follow_a_growing_run(tmp_path, liveness):
    """Bundles journaled (the page's tail), flushes publishing them as Parquet parts (the tail replaced), compaction at a
    save point (the tail cursor reset) and unchanged polls: every answer the same three ways, the page ends with every
    row once, and the flush log is read whole once - after that only what was appended, and 2 anchors when nothing was."""
    run = SyntheticRun(tmp_path / 'run')
    page = Page(run.path, max_rows=40)
    page.poll()                                                         # nothing recorded yet: an empty flush log
    resets = 0
    for step in range(12):
        run.commit(3)
        if step % 3 == 2:
            run.flush()
        if step == 7:
            run.compact()
        before = len(page.answers)
        page.poll()
        resets += any(a['tail_page']['reset'] for a in page.answers[before:])
        quiet = page.poll()                                             # nothing new: nothing delivered again
        assert quiet['final']['evaluations']['n'] == 0 and quiet['tail']['evaluations']['n'] == 0
        assert not quiet['tail_page']['reset']
    run.assert_whole(page)
    assert resets >= 5                                                  # four flushes and the compaction reset the tail
    stats = training_series.cache_stats()
    assert stats['flush_rebuilt'] == 1 and stats['flush_appended'] == 4 and stats['flush_fallbacks'] == 0
    assert stats['flush_unchanged'] >= 12 and stats['flush_records_held'] == 4 == len(read_jsonl(run.log))
    assert stats['flush_bytes_parsed'] == run.log.stat().st_size        # each record parsed once
    assert stats['config_misses'] == 1 and stats['config_hits'] == stats['flush_reads'] - 1


def test_worker_state_segments_and_configuration_are_read_for_every_answer(tmp_path, liveness):
    run = SyntheticRun(tmp_path / 'run')
    run.commit(4)
    run.flush()
    page = Page(run.path)
    first = page.poll()
    assert (first['state'], first['worker_alive']) == ('running', True)
    assert first['objective'] == dict(metric='score', direction='max')
    liveness.update(state='completed', worker_alive=False)
    asked = liveness['asked']
    answer = page.poll()
    assert (answer['state'], answer['worker_alive']) == ('completed', False)
    assert liveness['asked'] == asked + 3                               # each reader asked, for each answer
    first['objective']['metric'] = 'changed by a caller'                # an answer's objective is its own
    assert page.poll()['objective'] == dict(metric='score', direction='max')

    # A resume: the configuration replaced (atomically) and a segment added to the manifest.
    config_path, manifest_path = run.path / 'effective_config.json', run.path / 'run_manifest.json'
    config = read_json(config_path)
    config['targets'][0]['direction_after_feasible'] = 'minimize'
    config['output']['learner_update_log_every'] = 4
    write_json(config_path, config)
    manifest = read_json(manifest_path)
    manifest['segments'].append(dict(segment=2, entry='resume', started_utc=T0.isoformat()))
    write_json(manifest_path, manifest)
    answer = page.poll()
    assert answer['objective'] == dict(metric='score', direction='min') and answer['learner']['every'] == 4
    assert [s['entry'] for s in answer['segments']] == ['start', 'resume']

    # Rewritten in place at once, the same length, the same file: the text tells.
    text = config_path.read_text(encoding='utf8')
    changed = text.replace('"direction_after_feasible": "minimize"', '"direction_after_feasible": "maximize"')
    assert changed != text and len(changed) == len(text)
    with config_path.open('r+', encoding='utf8') as stream:
        stream.write(changed)
    assert page.poll()['objective'] == dict(metric='score', direction='max')
    config['output']['save_learner_updates'] = False
    write_json(config_path, config)
    assert page.poll()['learner']['reason'].startswith('This run was started with "save learner updates" off')
    manifest['mode'] = 'frozen'
    write_json(manifest_path, manifest)
    assert page.poll()['learner']['reason'].startswith('A frozen run evaluates a saved policy')

    # Missing for one answer (as for a moment during a replacement on the 9p mount): read as missing, never kept so.
    aside = run.path / 'aside.json'
    config_path.rename(aside)
    gone = page.poll()
    assert gone['objective'] is None and gone['learner']['every'] == 1
    aside.rename(config_path)
    back = page.poll()
    assert back['objective'] == dict(metric='score', direction='min') and back['learner']['every'] == 4
    manifest_path.rename(aside)
    gone = page.poll()
    assert gone['run_id'] is None and gone['segments'] == [] and gone['learner']['reason'].startswith('This run was')
    aside.rename(manifest_path)
    assert [s['entry'] for s in page.poll()['segments']] == ['start', 'resume']

    # Not a configuration: the same error as before, or no objective - and nothing of it kept.
    config_path.write_text('{"run": ', encoding='utf8')
    assert agree(run.path, page.flushes, page.tail_cursor)[:2] == ('error', 'JSONDecodeError')
    config_path.write_text('[1]', encoding='utf8')
    assert agree(run.path, page.flushes, page.tail_cursor)[:2] == ('error', 'AttributeError')
    for odd in ('null', '[]', '{}', '{"run": {"mode": "frozen"}}'):
        config_path.write_text(odd, encoding='utf8')
        assert agreed(run.path, page.flushes, page.tail_cursor)['objective'] is None
    write_json(config_path, config)
    assert page.poll()['objective'] == dict(metric='score', direction='min')
