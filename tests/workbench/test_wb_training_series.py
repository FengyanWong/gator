"""The Training tab's numbers (record 7.193): GET /api/runs/training delivers the run's RECORDED training values - the
Parquet parts the flush journal lists, then the journal's bundles no flush has published yet - exactly as recorded, in
commit order, page by page, never a bundle twice, a missing value as null. Everything is MOCK (the analytic toy backend);
one test kills a worker process and resumes the run, as test_wb_engine does."""
import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import pytest

from gator_workbench import runs, training_series
from gator_workbench.storage import read_json
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
    """What the page holds after these answers: every page's final rows, then the last answer's tail (the page replaces
    its tail with every answer)."""
    out = {'evaluations': {}, 'updates': {}, 'specs': {}}
    for answer in answers:
        for table in out:
            for name, column in answer['final'][table].items():
                if name != 'n':
                    out[table].setdefault(name, []).extend(decode(column))
    tail = answers[-1]['tail']
    if tail:
        for table in out:
            for name, column in tail[table].items():
                if name != 'n':
                    out[table].setdefault(name, []).extend(decode(column))
    return out


def read_all(run_dir, max_rows=training_series.MAX_ROWS):
    answers, cursor = [], 0
    while True:
        answer = training_series.read_training(run_dir, cursor, max_rows=max_rows)
        json.dumps(answer, allow_nan=False)                     # what the route sends: never a NaN or an infinity
        answers.append(answer)
        assert answer['flushes']['start'] == cursor
        cursor = answer['flushes']['served']
        if cursor == answer['flushes']['total']:
            return answers
        assert answer['tail'] is None                           # a tail only once the page holds every flush


def epoch(value):
    return None if value is None else value.timestamp()


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
    assert [s['entry'] for s in answer['segments']] == ['start'] and answer['tail'] == {'evaluations': {'n': 0}, 'updates': {'n': 0},
                                                                                         'specs': {'n': 0}, 'spec_defs': {}}


def test_pages_add_up_to_one_answer_and_never_repeat_a_row(scripted_run):
    _, layout = scripted_run
    one = read_all(layout.run_dir)
    paged = read_all(layout.run_dir, max_rows=12)
    assert len(one) == 1 and len(paged) > 3
    assert whole(paged) == whole(one)
    assert [a['flushes']['served'] for a in paged] == sorted({a['flushes']['served'] for a in paged})


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
        answer = training_series.read_training(layout.run_dir, cursor)
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
    assert training_series.read_training(frozen_run.run_dir)['learner'] == dict(
        recorded=False, every=1, reason='A frozen run evaluates a saved policy without training it: there are no learner '
                                        'updates, so no losses, temperature or entropy.')


def test_best_feasible_objective_is_the_trackers_objective_value(tmp_path):
    def objective(raw):
        raw['targets'][0]['direction_after_feasible'] = 'maximize'
    layout, state = execute(make_config(tmp_path, threshold=0.4, run=dict(max_evaluations=16, seed=2), mutate=objective), tmp_path)
    assert state == 'completed'
    answer = training_series.read_training(layout.run_dir)
    assert answer['objective'] == dict(metric='score', direction='max')
    got = answer['final']['evaluations']['best_so_far_objective']
    recorded = sorted(rows(layout, 'evaluations'), key=lambda r: r['commit_seq'])
    want = [({p['key']: p['value'] for p in e['best_so_far_metrics']}.get('score') if e['best_so_far_feasible'] else None) for e in recorded]
    assert got == want and any(v is not None for v in got)
    values = [v for v in got if v is not None]
    assert values == sorted(values)                                             # the best feasible score only improves


def test_learner_record_says_why_nothing_was_recorded(tmp_path):
    layout_dir = tmp_path / 'run'
    layout_dir.mkdir()
    write = lambda config, manifest=None: ((layout_dir / 'effective_config.json').write_text(json.dumps(config)),
                                           (layout_dir / 'run_manifest.json').write_text(json.dumps(manifest or {})))
    write(dict(output=dict(save_learner_updates=False), run=dict(mode='scratch')))
    assert 'save learner updates' in training_series.learner_record(layout_dir)['reason']
    write(dict(output={}, run=dict(mode='scratch', search=dict(method='llm'))))
    assert training_series.learner_record(layout_dir)['reason'].startswith('AI sizing only')
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
