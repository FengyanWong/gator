"""The Training tab's numbers (record 7.193): GET /api/runs/training delivers the run's RECORDED training values - the
Parquet parts the flush journal lists, then the journal's bundles no flush has published yet - exactly as recorded, in
commit order, page by page, never a bundle twice, a missing value as null. Everything is MOCK (the analytic toy backend);
one test kills a worker process and resumes the run, as test_wb_engine does.

Record 7.221: read_training keeps a run's flush records and its configuration's objective between answers. Every answer
read here is also read by the reader before 7.221 (reference_read_training, its code word for word) and uncached: the
same answer, or the same error, whatever happened to the files."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
import pytest

from gator_workbench import runs, training_series
from gator_workbench.layout import RunLayout
from gator_workbench.storage import RawDataset, read_json, write_json
from gator_workbench.storage.atomic import read_jsonl
from helpers import execute, make_config, roots_for, rows, run_prepared, workbench_app

pytestmark = pytest.mark.xdist_group('test_wb_training_series')
REPO = Path(__file__).resolve().parents[2]


def decode(column):
    """A delivered column as a plain list: {values, codes} words decoded, -1 = null."""
    if isinstance(column, dict):
        return [None if c < 0 else column['values'][c] for c in column['codes']]
    return column


def whole(answers):
    """Final rows plus tail pages since the latest cursor reset."""
    out = {'evaluations': {}, 'updates': {}, 'specs': {}}
    pending = []
    for answer in answers:
        for table in out:
            for name, column in answer['final'][table].items():
                if name != 'n':
                    out[table].setdefault(name, []).extend(decode(column))
        if answer.get('tail_page', {}).get('reset', True):
            pending.clear()
        if answer['tail']:
            pending.append(answer['tail'])
    for tail in pending:
        for table in out:
            for name, column in tail[table].items():
                if name != 'n':
                    out[table].setdefault(name, []).extend(decode(column))
    return out


def read_all(run_dir, max_rows=training_series.MAX_ROWS):
    answers, cursor, tail_cursor = [], 0, None
    while True:
        answer = agreed(run_dir, cursor, tail_cursor, max_rows)  # the same answer before 7.221, uncached and cached
        json.dumps(answer, allow_nan=False)                     # what the route sends: never a NaN or an infinity
        answers.append(answer)
        assert answer['flushes']['start'] == cursor
        cursor = answer['flushes']['served']
        tail_cursor = answer['tail_page']['cursor']
        if cursor == answer['flushes']['total'] and not answer['tail_page']['more']:
            return answers
        if cursor < answer['flushes']['total']:
            assert answer['tail'] is None                       # a tail only once the page holds every flush


def epoch(value):
    return None if value is None else value.timestamp()


# ---- The reader before record 7.221 (c170802), word for word: every file read whole for every answer. The oracle.
def reference_run_objective(run_dir):
    from gator_workbench import schema
    from gator_workbench.compile import build_specs
    raw = read_json(RunLayout(run_dir).effective_config, default=None)
    if not raw:
        return None
    try:
        return build_specs(schema.WorkbenchConfig.model_validate(raw))[2]
    except Exception:
        return None


def reference_learner_record(run_dir):
    layout = RunLayout(run_dir)
    config = read_json(layout.effective_config, default={}) or {}
    manifest = read_json(layout.manifest, default={}) or {}
    output, run = config.get('output') or {}, config.get('run') or {}
    method = (run.get('search') or {}).get('method', 'sac')
    every = output.get('learner_update_log_every') or 1
    if manifest.get('mode') == 'frozen' or run.get('mode') == 'frozen':
        return dict(recorded=False, every=every, reason='A frozen run evaluates a saved policy without training it: '
                    'there are no learner updates, so no losses, temperature or entropy.')
    if method == 'llm':
        return dict(recorded=False, every=every, reason='An LLM-only run has no RL learner, so no losses, temperature '
                    'or entropy.')
    if output.get('save_learner_updates') is False:
        return dict(recorded=False, every=every, reason='This run was started with "save learner updates" off '
                    '(Output settings), so its losses, temperature and entropy were not recorded.')
    return dict(recorded=True, every=every, reason=None)


def reference_read_training(run_dir, flushes=0, *, max_rows=training_series.MAX_ROWS, tail_cursor=None):
    ts = training_series
    layout = RunLayout(Path(run_dir))
    data = layout.data
    if not (data / '_journal').is_dir():
        raise FileNotFoundError('This folder holds no recorded run data.')
    records = read_jsonl(data / '_journal' / 'flushes.jsonl')
    total = len(records)
    start = max(0, min(int(flushes), total))
    manifest = read_json(layout.manifest, default={}) or {}
    objective = reference_run_objective(layout.run_dir)
    chosen, rows = [], 0
    for record in records[start:]:
        if chosen and rows + sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics')) > max_rows:
            break
        chosen.append(record)
        rows += sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics'))
    served = start + len(chosen)
    final = ts._flush_chunk(data, chosen, objective) if chosen else ts._Chunk()
    tail, tail_complete, latest = None, True, (records[-1]['last_seq'] if records else 0)
    tail_page = dict(start=tail_cursor, cursor=None, reset=True, more=False)
    if served == total:
        budget = max(0, max_rows - rows)
        if budget:
            pending, tail_page, tail_complete, latest = ts.journal_page(
                data / '_journal' / 'wal.jsonl', latest, objective, tail_cursor, max_rows=budget)
            tail = pending.as_json()
        else:
            tail_page['more'] = True
    from gator_workbench.runs import run_status
    status = run_status(layout.run_dir)
    return dict(run_dir=str(layout.run_dir), run_id=manifest.get('run_id'), mode=manifest.get('mode'),
                mock=manifest.get('mock'), state=status.get('state'), worker_alive=bool(status.get('worker_alive')),
                flushes=dict(served=served, total=total, start=start),
                final=final.as_json(), tail=tail, tail_complete=tail_complete, latest_seq=latest, tail_page=tail_page,
                objective=objective, learner=reference_learner_record(layout.run_dir),
                segments=[{k: s.get(k) for k in ('segment', 'entry', 'started_utc', 'ended_utc', 'end_state', 'stop_reason')}
                          for s in manifest.get('segments') or []])


def outcome(read):
    """What a reader gave: ('answer', the answer) or ('error', its type, its words)."""
    try:
        return 'answer', read()
    except Exception as exc:
        return 'error', type(exc).__name__, str(exc)


def agree(run_dir, flushes=0, tail_cursor=None, max_rows=training_series.MAX_ROWS):
    """One poll read by the reader before 7.221, then uncached, then cached, nothing written in between: the same
    answer or the same error, three times. Returns that outcome."""
    want = outcome(lambda: reference_read_training(run_dir, flushes, max_rows=max_rows, tail_cursor=tail_cursor))
    for cached in (False, True):
        got = outcome(lambda: training_series.read_training(run_dir, flushes, max_rows=max_rows, tail_cursor=tail_cursor,
                                                            cached=cached))
        assert got == want, f'cached={cached} differs from the reader before 7.221'
    return want


def agreed(run_dir, flushes=0, tail_cursor=None, max_rows=training_series.MAX_ROWS):
    result = agree(run_dir, flushes, tail_cursor, max_rows)
    assert result[0] == 'answer', result
    return result[1]


@pytest.fixture(scope='module')
def scripted_run(tmp_path_factory):
    """A MOCK run with a measurement that comes back NaN and a simulation that times out: the gaps the charts must show."""
    root = tmp_path_factory.mktemp('training')
    config = make_config(root, threshold=0.6, run=dict(max_evaluations=24, seed=3), output=dict(flush_every_evaluations=5))
    layout, state = execute(config, root, scripts={'0': {4: 'nan', 9: 'timeout'}})
    assert state == 'completed'
    return root, layout


def test_values_are_the_recorded_rows_exactly(scripted_run):
    root, layout = scripted_run
    answer = TestClient(workbench_app(root)).get('/api/runs/training', params=dict(run_dir=str(layout.run_dir), flushes=0)).json()
    got = whole([answer])
    evaluations = sorted(rows(layout, 'evaluations'), key=lambda r: r['commit_seq'])
    assert len(evaluations) == 24 and answer['final']['evaluations']['n'] == 24
    for name in ('commit_seq', 'completion_index', 'global_env_step', 'episode_id', 'episode_step', 'phase', 'action_source', 'status',
                 'policy_version', 'reward', 'valid', 'all_hard_constraints_satisfied', 'normalized_constraint_violation',
                 'clearance_margin', 'best_so_far_feasible', 'best_so_far_violation', 'execution_seconds'):
        assert got['evaluations'][name] == [e[name] for e in evaluations], name
    assert got['evaluations']['committed_at'] == [epoch(e['committed_at']) for e in evaluations]
    # the scripted failures: a NaN measurement and a timeout recorded as gaps (null), never as a number
    assert None in got['evaluations']['reward'] and 'timeout' in got['evaluations']['status'] and False in got['evaluations']['valid']
    updates = rows(layout, 'learner_updates')
    assert updates, 'the MOCK run trained'
    for name in ('cumulative_updates', 'evaluations_collected', 'update_phase', 'actor_loss', 'critic_loss', 'alpha_loss', 'alpha',
                 'mean_log_prob', 'target_mean', 'critic_grad_norm', 'actor_grad_norm'):
        assert got['updates'][name] == [u[name] for u in updates], name
    seq_of = {e['evaluation_id']: e['commit_seq'] for e in evaluations}
    specs = [m for m in rows(layout, 'metrics') if m['aggregation_level'] == 'aggregate' and m['hard'] is not None]
    assert [(s['metric_name'], seq_of[s['evaluation_id']], s['raw_value'], s['satisfied']) for s in specs] == list(zip(
        got['specs']['metric_name'], got['specs']['commit_seq'], got['specs']['raw_value'], got['specs']['satisfied']))
    gaps = {reason for value, reason in zip(got['specs']['raw_value'], got['specs']['failure_reason']) if value is None}
    assert gaps == {'missing_or_nonfinite', 'evaluation_status_timeout'}           # the NaN measurement and the timeout: gaps, with why
    assert answer['final']['spec_defs'] == {'score': dict(unit='fixture', threshold_lower=0.6, threshold_upper=None, hard=True)}
    assert answer['learner'] == dict(recorded=True, every=1, reason=None) and answer['objective'] is None
    assert answer['state'] == 'completed' and answer['worker_alive'] is False      # a run compared beside the shown one (7.200)
    assert [s['entry'] for s in answer['segments']] == ['start'] and answer['tail'] == {'evaluations': {'n': 0}, 'updates': {'n': 0},
                                                                                         'specs': {'n': 0}, 'spec_defs': {}}


def test_pages_add_up_to_one_answer_and_never_repeat_a_row(scripted_run):
    _, layout = scripted_run
    one = read_all(layout.run_dir)
    paged = read_all(layout.run_dir, max_rows=12)
    assert len(one) == 1 and len(paged) > 3
    assert whole(paged) == whole(one)
    assert [a['flushes']['served'] for a in paged] == sorted(a['flushes']['served'] for a in paged)


def test_journal_tail_reads_back_to_the_last_flush_only(tmp_path):
    wal = tmp_path / 'wal.jsonl'
    bundle = lambda seq: json.dumps(dict(evaluation_id=f'e{seq}', commit_seq=seq, rows={})) + '\n'
    assert training_series.journal_tail(wal, 0) == ([], True)                  # no journal yet: nothing, and nothing missed
    wal.write_text(''.join(bundle(s) for s in range(1, 8)) + '{"evaluation_id": "e8", "commit_s')   # a torn last line
    found, complete = training_series.journal_tail(wal, 4)
    assert complete and [b['commit_seq'] for b in found] == [5, 6, 7]           # the torn line is not acknowledged
    assert training_series.journal_tail(wal, 7) == ([], True)
    found, complete = training_series.journal_tail(wal, 0, block_size=16)       # lines longer than a block
    assert complete and [b['commit_seq'] for b in found] == list(range(1, 8))
    wal.write_text(''.join(bundle(s) for s in range(10, 13)))                    # compacted after a flush we have not seen
    assert training_series.journal_tail(wal, 6) == ([], False)
    wal.write_text(bundle(1) + '{not json}\n' + bundle(3))
    assert training_series.journal_tail(wal, 0) == ([], False)


CRASH_SCRIPT = '''
import sys
sys.path[:0] = [{src!r}, {tests!r}]
import torch; torch.set_num_threads(1)
from gator_workbench.layout import RunLayout
from helpers import run_prepared
run_prepared(RunLayout({run_dir!r}), delays={{'0': 0.08}})
'''


def test_a_killed_and_resumed_run_reads_whole_in_order_and_once(tmp_path):
    """The worker is killed (no flush, no save point), so recorded results wait in the journal: the tail delivers them. The
    run is resumed: those bundles come back in a part, the page's tail is replaced, nothing is counted twice; a learner
    whose updates after its last save point were lost repeats their counts, and the rows come as recorded."""
    config = make_config(tmp_path, threshold=1.5, run=dict(max_evaluations=30),
                         output=dict(checkpoint_every_evaluations=4, flush_every_evaluations=6))
    layout, _ = runs.prepare_run(config, roots_for(tmp_path))
    script = CRASH_SCRIPT.format(src=str(REPO / 'src'), tests=str(Path(__file__).parent), run_dir=str(layout.run_dir))
    process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            persistence = (read_json(layout.status, default={}) or {}).get('persistence') or {}
            if persistence.get('last_commit_seq', 0) >= 10 and persistence.get('last_commit_seq', 0) > persistence.get('flushed_seq', 0):
                break
            assert process.poll() is None, 'worker ended before it could be killed'
            time.sleep(0.01)
        process.send_signal(signal.SIGKILL)
    finally:
        process.wait(timeout=30)
    before = read_all(layout.run_dir)
    flushes = read_jsonl(layout.data / '_journal' / 'flushes.jsonl')
    acknowledged = max([b['commit_seq'] for b in read_jsonl(layout.data / '_journal' / 'wal.jsonl')] + [flushes[-1]['last_seq'] if flushes else 0])
    held = whole(before)['evaluations']['commit_seq']
    assert held == list(range(1, len(held) + 1)) and held[-1] == acknowledged      # every acknowledged result, the journal's too
    assert before[-1]['tail']['evaluations']['n'] == acknowledged - (flushes[-1]['last_seq'] if flushes else 0)

    resumed = config.model_copy(deep=True)
    resumed.run.mode, resumed.run.model_source.run_dir = 'resume', str(layout.run_dir)
    again, _ = runs.prepare_run(resumed, roots_for(tmp_path))
    assert run_prepared(again) == 'completed'
    # the page goes on from the cursor it had; its tail is replaced
    later = []
    cursor = before[-1]['flushes']['served']
    while True:
        answer = agreed(layout.run_dir, cursor)
        later.append(answer)
        cursor = answer['flushes']['served']
        if cursor == answer['flushes']['total']:
            break
    page = whole(before[:-1] + [dict(before[-1], tail=None)] + later)
    recorded = sorted(rows(layout, 'evaluations'), key=lambda r: r['commit_seq'])
    assert page['evaluations']['commit_seq'] == [e['commit_seq'] for e in recorded] == list(range(1, len(recorded) + 1))
    assert page['evaluations']['completion_index'] == [e['completion_index'] for e in recorded]
    assert page['updates']['cumulative_updates'] == [u['cumulative_updates'] for u in rows(layout, 'learner_updates')]
    assert [s['entry'] for s in later[-1]['segments']] == ['start', 'resume']
    counts = page['updates']['cumulative_updates']
    repeats = sum(1 for a, b in zip(counts, counts[1:]) if b <= a)
    resume_event = next(e for e in read_jsonl(layout.logs / 'events.jsonl') if e['event'] == 'resumed')
    lost_updates = resume_event.get('post_checkpoint_evaluations', 0) > 0
    assert repeats <= 1 and (repeats == 0 or lost_updates)                     # a restart only where updates were lost


@pytest.fixture(scope='module')
def frozen_run(tmp_path_factory):
    root = tmp_path_factory.mktemp('frozen')
    source, state = execute(make_config(root, run=dict(max_evaluations=12, seed=5), project=dict(task_name='source')), root)
    assert state == 'completed'
    config = make_config(root, run=dict(max_evaluations=8, mode='frozen'), project=dict(task_name='frozen'))
    config.run.model_source.run_dir = str(source.run_dir)
    target, state = execute(config, root)
    assert state == 'completed'
    return target


def test_a_frozen_run_is_an_evaluation_and_has_no_learner(frozen_run):
    answer = whole(read_all(frozen_run.run_dir))
    assert 'frozen_eval' in answer['evaluations']['phase'] and answer['updates'] == {}
    assert agreed(frozen_run.run_dir)['learner'] == dict(
        recorded=False, every=1, reason='A frozen run evaluates a saved policy without training it: there are no learner '
                                        'updates, so no losses, temperature or entropy.')


def test_best_feasible_objective_is_the_trackers_objective_value(tmp_path):
    def objective(raw):
        raw['targets'][0]['direction_after_feasible'] = 'maximize'
    layout, state = execute(make_config(tmp_path, threshold=0.4, run=dict(max_evaluations=16, seed=2), mutate=objective), tmp_path)
    assert state == 'completed'
    answer = agreed(layout.run_dir)
    assert answer['objective'] == dict(metric='score', direction='max')
    got = answer['final']['evaluations']['best_so_far_objective']
    recorded = sorted(rows(layout, 'evaluations'), key=lambda r: r['commit_seq'])
    want = [({p['key']: p['value'] for p in e['best_so_far_metrics']}.get('score') if e['best_so_far_feasible'] else None) for e in recorded]
    assert got == want and any(v is not None for v in got)
    values = [v for v in got if v is not None]
    assert values == sorted(values)                                             # the best feasible score only improves


def test_infeasible_or_unknown_best_design_has_no_feasible_objective():
    import pyarrow as pa
    objective = dict(metric='gain', direction='max')
    recorded = [dict(best_so_far_metrics=[dict(key='gain', value=100. + i)], best_so_far_feasible=flag)
                for i, flag in enumerate((False, None, True, False))]
    columns = ('best_so_far_metrics', 'best_so_far_feasible')
    parquet = training_series._table_columns(pa.Table.from_pylist(recorded), objective)
    journal = training_series._rows_columns(recorded, columns, objective)
    assert parquet['best_so_far_objective'] == journal['best_so_far_objective'] == [None, None, 102., None]


def journal_bundle(seq, updates=7):
    return dict(commit_seq=seq, evaluation_id=f'e{seq}', rows=dict(
        evaluations=[dict(evaluation_id=f'e{seq}', commit_seq=seq)],
        learner_updates=[dict(cumulative_updates=(seq - 1) * updates + i + 1) for i in range(updates)],
        metrics=[dict(evaluation_id=f'e{seq}', metric_name='gain', raw_value=float(seq), hard=True,
                      aggregation_level='aggregate', satisfied=True)]))


def test_live_journal_is_bounded_incremental_and_splits_large_bundles(tmp_path):
    data = tmp_path / 'data' / '_journal'
    data.mkdir(parents=True)
    wal = data / 'wal.jsonl'
    wal.write_text(''.join(json.dumps(journal_bundle(seq)) + '\n' for seq in range(1, 4)))
    answers = read_all(tmp_path, max_rows=4)
    assert len(answers) == 7
    assert all(sum(a['tail'][name]['n'] for name in ('evaluations', 'updates', 'specs')) <= 4 for a in answers)
    assert [a['tail_page']['reset'] for a in answers] == [True] + [False] * 6
    got = whole(answers)
    assert got['evaluations']['commit_seq'] == [1, 2, 3]
    assert got['updates']['cumulative_updates'] == list(range(1, 22))
    assert got['specs']['commit_seq'] == [1, 2, 3]
    assert got['specs']['raw_value'] == [1., 2., 3.]
    cursor = answers[-1]['tail_page']['cursor']
    quiet = agreed(tmp_path, 0, cursor, 4)
    assert quiet['tail_page'] == dict(start=cursor, cursor=cursor, reset=False, more=False)
    assert all(quiet['tail'][name]['n'] == 0 for name in ('evaluations', 'updates', 'specs'))
    with wal.open('a') as stream:
        stream.write(json.dumps(journal_bundle(4, updates=0)) + '\n')
    added = agreed(tmp_path, 0, cursor, 4)
    assert added['tail']['evaluations']['commit_seq'] == [4] and added['latest_seq'] == 4
    assert not added['tail_page']['reset'] and not added['tail_page']['more']


def test_live_cursor_handles_torn_lines_flushes_and_compaction(tmp_path):
    wal = tmp_path / 'wal.jsonl'
    line = lambda seq: json.dumps(journal_bundle(seq, updates=0)) + '\n'
    wal.write_text(line(1) + line(2)[:-5])
    chunk, page, complete, latest = training_series.journal_page(wal, 0, None)
    assert complete and latest == 1 and chunk.evaluations['commit_seq'] == [1] and not page['more']
    with wal.open('a') as stream:
        stream.write(line(2)[-5:])
    chunk, page, complete, latest = training_series.journal_page(wal, 0, None, page['cursor'])
    assert complete and latest == 2 and chunk.evaluations['commit_seq'] == [2] and not page['reset']
    cursor = page['cursor']
    # Atomic WAL compaction changes the file identity, even if its size is unchanged.
    replacement = tmp_path / 'replacement'
    replacement.write_text(line(2) + line(3))
    replacement.replace(wal)
    chunk, page, complete, latest = training_series.journal_page(wal, 1, None, cursor)
    assert complete and latest == 3 and page['reset'] and chunk.evaluations['commit_seq'] == [2, 3]
    # A reader with a stale flush list waits for the next poll rather than inventing a missing bundle.
    chunk, page, complete, latest = training_series.journal_page(wal, 0, None, cursor)
    assert not complete and chunk.as_json()['evaluations']['n'] == 0 and page['reset']
    chunk, page, complete, latest = training_series.journal_page(wal, 1, None, 'invalid cursor')
    assert complete and page['reset'] and chunk.evaluations['commit_seq'] == [2, 3]


def test_new_flush_cursor_seeks_past_the_published_history(tmp_path, monkeypatch):
    wal = tmp_path / 'wal.jsonl'
    wal.write_text(''.join(json.dumps(journal_bundle(seq, updates=0)) + '\n' for seq in range(1, 1003)))
    visited = []
    original = training_series._journal_lines

    def track(stream):
        for line, end in original(stream, block_size=128):
            visited.append(json.loads(line)['commit_seq'])
            yield line, end

    monkeypatch.setattr(training_series, '_journal_lines', track)
    chunk, page, complete, latest = training_series.journal_page(wal, 1000, None, max_rows=2)
    assert complete and chunk.evaluations['commit_seq'] == [1001] and page['more']
    assert visited == [1002, 1001, 1000]
    visited.clear()
    chunk, page, complete, latest = training_series.journal_page(wal, 1000, None, page['cursor'], max_rows=2)
    assert complete and latest == 1002 and chunk.evaluations['commit_seq'] == [1002] and not page['more']
    assert not visited                         # next page seeks straight to its saved byte offset


def test_learner_record_says_why_nothing_was_recorded(tmp_path):
    layout_dir = tmp_path / 'run'
    layout_dir.mkdir()
    write = lambda config, manifest=None: ((layout_dir / 'effective_config.json').write_text(json.dumps(config)),
                                           (layout_dir / 'run_manifest.json').write_text(json.dumps(manifest or {})))
    write(dict(output=dict(save_learner_updates=False), run=dict(mode='scratch')))
    assert 'save learner updates' in training_series.learner_record(layout_dir)['reason']
    write(dict(output={}, run=dict(mode='scratch', search=dict(method='llm'))))
    assert training_series.learner_record(layout_dir)['reason'].startswith('An LLM-only run')     # a run made before 2026-10-06
    write(dict(output=dict(learner_update_log_every=5), run=dict(mode='scratch')))
    assert training_series.learner_record(layout_dir) == dict(recorded=True, every=5, reason=None)


def test_the_route_reads_nothing_outside_a_run(scripted_run, tmp_path):
    root, layout = scripted_run
    client = TestClient(workbench_app(root))
    assert client.get('/api/runs/training', params=dict(run_dir=str(root))).status_code == 404            # not a run folder
    assert client.get('/api/runs/training', params=dict(run_dir=str(tmp_path))).status_code == 403        # outside the roots
    assert client.get('/api/runs/training', params=dict(run_dir=str(layout.run_dir), flushes=-1)).status_code == 422
    beyond = client.get('/api/runs/training', params=dict(run_dir=str(layout.run_dir), flushes=999)).json()
    assert beyond['flushes']['start'] == beyond['flushes']['total'] and beyond['final']['evaluations']['n'] == 0
    assert math.isfinite(beyond['latest_seq'])


# ------------------------------------------------------------------------------------------- record 7.221: the caches
T0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
CHART_TABLES = ('evaluations', 'learner_updates', 'metrics')


@pytest.fixture(autouse=True)
def fresh_caches():
    training_series.clear_caches()
    yield
    training_series.clear_caches()


@pytest.fixture
def liveness(monkeypatch):
    """The worker's state as the test sets it, in place of runs.run_status (status.json + the run lock), which every answer
    asks anew; `asked` counts the questions. An answer reads no clock, so with this the readers of one poll see one run."""
    state = dict(state='running', worker_alive=True, asked=0)

    def run_status(run_dir):
        state['asked'] += 1
        return dict(state=state['state'], worker_alive=state['worker_alive'], run_dir=str(run_dir))
    monkeypatch.setattr(runs, 'run_status', run_status)
    return state


class SyntheticRun:
    """A run folder as storage/dataset.py writes one - each bundle journaled and fsynced, a flush publishing Parquet parts
    and then its record, compaction at a save point - with a run's manifest and configuration, and no worker (see
    `liveness`). `seed` changes every recorded value, not the shape: a run made again at the same path."""

    def __init__(self, path, *, seed=0, updates=2):
        self.path, self.seed, self.updates, self.seq, self.update = Path(path), seed, updates, 0, 0
        self.path.mkdir(parents=True)

        def objective(raw):                                             # both limits: either direction is valid
            raw['targets'][0].update(direction_after_feasible='maximize', upper=10.0)
        write_json(self.path / 'effective_config.json', make_config(self.path, mutate=objective).model_dump(mode='json'))
        write_json(self.path / 'run_manifest.json', dict(run_id=f'{self.path.name}-{seed}', mode='scratch', mock=True,
                                                         segments=[dict(segment=1, entry='start', started_utc=T0.isoformat())]))
        self.dataset = RawDataset(self.path / 'data', enabled_tables=CHART_TABLES, flush_every=10 ** 9)

    @property
    def log(self):
        return self.path / 'data' / '_journal' / 'flushes.jsonl'

    def commit(self, count=1):
        for _ in range(count):
            self.seq += 1
            seq, value, eid = self.seq, self.seq + self.seed / 8, f'e{self.seq}'
            updates = []
            for _ in range(self.updates):
                self.update += 1
                updates.append(dict(run_id='r', update_id=f'u{self.update}', updated_at=T0 + timedelta(seconds=self.update),
                                    update_phase='online', evaluations_collected=seq, actor_loss=-value, critic_loss=1 / value,
                                    alpha_loss=0.1, alpha=0.2, mean_log_prob=-1.5, target_mean=value / 2,
                                    critic_grad_norm=1.0, actor_grad_norm=2.0, learning_rate=1e-3, replay_size=seq,
                                    batch_size=8, cumulative_updates=self.update, policy_version=self.update,
                                    update_seconds=0.01))
            evaluation = dict(
                run_id='r', evaluation_id=eid, task_id='t', proposal_id=f'p{seq}', worker_id='w0',
                episode_id=f'ep{(seq - 1) // 3}', episode_step=(seq - 1) % 3, global_env_step=seq, dispatch_index=seq,
                completion_index=seq, commit_seq=seq, phase='search', action_source='sac_policy', proposed_at=T0,
                started_at=T0, completed_at=T0, committed_at=T0 + timedelta(seconds=seq), queue_seconds=0.0,
                execution_seconds=value, provenance='mock', result_source='simulation', cache_hit=False, attempts=1,
                parameters_ref=eid, metrics_ref=eid, valid=True, all_hard_constraints_satisfied=seq % 2 == 0,
                best_so_far_feasible=seq > 1, best_so_far_metrics={'score': value}, cumulative_evaluations_charged=seq,
                cumulative_completed=seq, cumulative_launches=seq, in_flight_at_commit=0, after_first_feasible=seq > 1,
                in_flight_at_first_feasible=False, status='ok', terminated=False, truncated=False, replay_eligible=True,
                reward=value / 10)
            metrics = [dict(run_id='r', evaluation_id=eid, metric_name='score', condition='nominal', valid=True,
                            aggregation_level=level, raw_value=value, unit='fixture', threshold_lower=0.6, hard=True,
                            satisfied=seq % 2 == 0) for level in ('aggregate', 'condition')]
            assert self.dataset.commit(dict(evaluation_id=eid, commit_seq=seq, rows=dict(
                evaluations=[evaluation], learner_updates=updates, metrics=metrics)))

    def flush(self):
        return self.dataset.flush()                                     # None when nothing waited

    def compact(self):
        self.dataset.compact_journal()

    def assert_whole(self, page):
        """The page holds every acknowledged row once, in commit order, with the values recorded."""
        got = whole(page.answers)
        assert got['evaluations']['commit_seq'] == list(range(1, self.seq + 1))
        assert got['evaluations']['execution_seconds'] == [s + self.seed / 8 for s in range(1, self.seq + 1)]
        assert got['updates']['cumulative_updates'] == list(range(1, self.update + 1))
        assert got['specs']['commit_seq'] == list(range(1, self.seq + 1))


class Page:
    """The Training tab reading one run (TrainingTab.tsx): from the last answer's flush and tail cursors, answer after
    answer until nothing more waits. `check`: each answer read three ways (agree); off while a writer is at work."""

    def __init__(self, run_dir, max_rows=training_series.MAX_ROWS, check=True):
        self.run_dir, self.max_rows, self.check = run_dir, max_rows, check
        self.flushes, self.tail_cursor, self.answers = 0, None, []

    def poll(self):
        while True:
            answer = (agreed(self.run_dir, self.flushes, self.tail_cursor, self.max_rows) if self.check else
                      training_series.read_training(self.run_dir, self.flushes, max_rows=self.max_rows,
                                                    tail_cursor=self.tail_cursor))
            self.answers.append(answer)
            self.flushes, self.tail_cursor = answer['flushes']['served'], answer['tail_page']['cursor']
            if self.flushes == answer['flushes']['total'] and not answer['tail_page']['more']:
                return answer


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


def test_objective_and_learner_helpers_answer_as_before(tmp_path):
    """run_objective and learner_record, kept for callers that use them alone, read their files as they did."""
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    config = make_config(tmp_path).model_dump(mode='json')
    config['targets'][0].update(direction_after_feasible='minimize', upper=10.0)
    for text in (None, 'null', '[]', '[1]', '{}', '{"run": ', json.dumps(config),
                 json.dumps(dict(output=dict(save_learner_updates=False, learner_update_log_every=3)))):
        for manifest in (None, '{}', '{"mode": "frozen"}', '[1]'):
            for name, value in (('effective_config.json', text), ('run_manifest.json', manifest)):
                (run_dir / name).unlink(missing_ok=True)
                if value is not None:
                    (run_dir / name).write_text(value, encoding='utf8')
            assert outcome(lambda: training_series.run_objective(run_dir)) == outcome(lambda: reference_run_objective(run_dir))
            assert outcome(lambda: training_series.learner_record(run_dir)) == outcome(lambda: reference_learner_record(run_dir))
    assert training_series.run_objective(run_dir) is None
    (run_dir / 'effective_config.json').write_text(json.dumps(config), encoding='utf8')
    assert training_series.run_objective(run_dir) == dict(metric='score', direction='min')


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
        for flushes in (0, 2, 5, 11):
            agree(run.path, flushes)
        return agreed(run.path)

    def rebuilt():
        return training_series.cache_stats()['flush_rebuilt']

    def rewrite(content, *, keep_times=False):
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


def test_a_kept_run_is_still_refused_outside_the_allowed_roots(scripted_run, tmp_path):
    """The route checks the run folder (resolved, inside an allowed root, a run) before anything is read or kept."""
    root, layout = scripted_run
    allowed = TestClient(workbench_app(root)).get('/api/runs/training', params=dict(run_dir=str(layout.run_dir)))
    assert allowed.status_code == 200 and training_series.cache_stats()['flush_runs'] == 1
    other = TestClient(workbench_app(tmp_path))
    assert other.get('/api/runs/training', params=dict(run_dir=str(layout.run_dir))).status_code == 403
