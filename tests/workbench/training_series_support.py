"""The Training tab's reader as it was before record 7.221 (c170802), word for word - every file read whole for every answer: the oracle both training-series test modules compare the cached reader with - and the autouse fixture that empties the reader's caches around every test of both (refactoring package D4)."""

from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from gator_workbench import runs, training_series
from gator_workbench.layout import RunLayout
from gator_workbench.storage import RawDataset, read_json, write_json
from gator_workbench.storage.atomic import read_jsonl

from helpers import execute, make_config


# ---- The reader before record 7.221 (c170802), word for word: every file read whole for every answer. The oracle.
def reference_run_objective(run_dir):
    """Read the saved objective as the original uncached training-series reader did."""
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
    """Report learner-log availability using the reference reader's saved-run rules."""
    layout = RunLayout(run_dir)
    config = read_json(layout.effective_config, default={}) or {}
    manifest = read_json(layout.manifest, default={}) or {}
    output, run = config.get('output') or {}, config.get('run') or {}
    method = (run.get('search') or {}).get('method', 'sac')
    every = output.get('learner_update_log_every') or 1
    if manifest.get('run_kind') in training_series.NO_LEARNER:          # 7.292: the runs that train no model
        return dict(recorded=False, every=every, reason=training_series.NO_LEARNER[manifest['run_kind']])
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
    """Return the reference training-series page for the requested flush and tail cursors."""
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


@pytest.fixture(autouse=True)
def fresh_caches():
    """Clear training-series caches before and after each test."""
    training_series.clear_caches()
    yield
    training_series.clear_caches()


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
    """Return a page only after cached, uncached and reference readers agree on a successful result."""
    result = agree(run_dir, flushes, tail_cursor, max_rows)
    assert result[0] == 'answer', result
    return result[1]


# ------------------------------------------------------------------------------------------- record 7.221: the caches
T0 = datetime(2026, 10, 6, tzinfo=timezone.utc)


CHART_TABLES = ('evaluations', 'learner_updates', 'metrics')


@pytest.fixture
def liveness(monkeypatch):
    """The worker's state as the test sets it, in place of runs.run_status (status.json + the run lock), which every answer
    asks anew; `asked` counts the questions. An answer reads no clock, so with this the readers of one poll see one run."""
    state = dict(state='running', worker_alive=True, asked=0)

    def run_status(run_dir):
        """Return and count the fixture's current worker-status answer."""
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
            """Give the synthetic score an upper target and a maximizing feasible objective."""
            raw['targets'][0].update(direction_after_feasible='maximize', upper=10.0)
        write_json(self.path / 'effective_config.json', make_config(self.path, mutate=objective).model_dump(mode='json'))
        write_json(self.path / 'run_manifest.json', dict(run_id=f'{self.path.name}-{seed}', mode='scratch', mock=True,
                                                         segments=[dict(segment=1, entry='start', started_utc=T0.isoformat())]))
        self.dataset = RawDataset(self.path / 'data', enabled_tables=CHART_TABLES, flush_every=10 ** 9)

    @property
    def log(self):
        """Return the flush journal path used to inspect publication records."""
        return self.path / 'data' / '_journal' / 'flushes.jsonl'

    def commit(self, count=1):
        """Append deterministic evaluation, learner-update and metric rows to the run journal."""
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
        """Publish pending fixture rows as Parquet parts, if any."""
        return self.dataset.flush()                                     # None when nothing waited

    def compact(self):
        """Compact the fixture run's journal as a save point would."""
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
        """Read and retain pages until the available flushes and journal tail are exhausted."""
        while True:
            answer = (agreed(self.run_dir, self.flushes, self.tail_cursor, self.max_rows) if self.check else
                      training_series.read_training(self.run_dir, self.flushes, max_rows=self.max_rows,
                                                    tail_cursor=self.tail_cursor))
            self.answers.append(answer)
            self.flushes, self.tail_cursor = answer['flushes']['served'], answer['tail_page']['cursor']
            if self.flushes == answer['flushes']['total'] and not answer['tail_page']['more']:
                return answer
