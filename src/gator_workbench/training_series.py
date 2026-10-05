"""The Training tab's numbers (record 7.193): a run's recorded training values as compact columns, read incrementally.

Read-only, and nothing is computed INTO the numbers. They come from the run's own records, never from console text: the
Parquet parts that ``data/_journal/flushes.jsonl`` lists (storage/dataset.py: a part is published whole and never
rewritten), then the acknowledged bundles of ``data/_journal/wal.jsonl`` that no flush has published yet. Those are the
same rows, journaled before the next flush (every 16 evaluations by default), so a live run is drawn up to its newest
result without waiting for the next part. The training loop is not touched: no event, no file and no simulation is added
for the charts, and the page draws them in the browser only.

Cursor: the number of flush records the page already holds. An answer carries the rows of the next flush records
(``final``: they never change) and, once the page holds every flush, the journal's bundles after the newest one
(``tail``: provisional - the page replaces its tail with every answer, so a bundle that a later flush publishes is never
counted twice). A journal being rewritten while it is read (compaction at a save point) gives an empty tail for that one
answer; the next one has the bundles in a part.

What is NOT here, because the run does not record it: an episode return (the reward is recorded per evaluation - the
step reward), a separate evaluation of the policy during training (only a frozen run evaluates a policy), and an
objective when no Specs row says "then lower/higher is better". The answer says so instead of inventing them.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
import os
from pathlib import Path
import threading

from .layout import RunLayout
from .storage.atomic import read_json, read_jsonl
from .storage.tables import arrow_schema

# The recorded columns each table gives, by their own names (storage/tables.py says what each one means). Two are
# delivered in another form: a timestamp as seconds since 1970 (UTC), and best_so_far_metrics as ONE number - the
# objective's value of the best feasible design so far (best_so_far_objective, below).
EVALUATION_COLUMNS = ('commit_seq', 'completion_index', 'global_env_step', 'episode_id', 'episode_step', 'phase',
                      'action_source', 'status', 'policy_version', 'reward', 'valid', 'all_hard_constraints_satisfied',
                      'normalized_constraint_violation', 'clearance_margin', 'best_so_far_feasible',
                      'best_so_far_violation', 'execution_seconds', 'committed_at')
UPDATE_COLUMNS = ('cumulative_updates', 'evaluations_collected', 'update_phase', 'actor_loss', 'critic_loss', 'alpha_loss',
                  'alpha', 'mean_log_prob', 'target_mean', 'critic_grad_norm', 'actor_grad_norm', 'updated_at')
# A spec's row: one per evaluation and spec, the value its equation gave and the limits it was held to (engine._metric_rows:
# aggregation_level 'aggregate' with `hard` set; a probe that no spec shows whole has hard = null and is not a spec).
SPEC_COLUMNS = ('evaluation_id', 'metric_name', 'raw_value', 'unit', 'threshold_lower', 'threshold_upper', 'hard',
                'satisfied', 'failure_reason', 'aggregation_level')
STRING_COLUMNS = {'episode_id', 'phase', 'action_source', 'status', 'update_phase', 'metric_name', 'failure_reason'}
TIME_COLUMNS = {'committed_at', 'updated_at'}
MAX_ROWS = 30000                # rows of one answer (evaluations + updates + specs); a longer history comes in pages
_POOL = None
_POOL_LOCK = threading.Lock()


def _pool():
    """Parts are read side by side: on the 9p-mounted D: drive a part costs ~30 ms of waiting, and the 192 parts of an
    800-evaluation run took 5.9 s one after the other, 0.24 s eight at a time (measured 2026-10-05)."""
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ThreadPoolExecutor(8, thread_name_prefix='training-parts')
        return _POOL


def _finite(value):
    """A number as JSON can carry it: the tables never store a non-finite number, and nothing here makes one up."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _epoch(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.timestamp()


def _read_part(path, table, columns):
    """One open per part (DatasetReader._read_part opens it twice): the columns asked for, and a column an older part
    lacks as nulls - the reader's rule for parts written before the column existed."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = arrow_schema(table)
    with pq.ParquetFile(path) as part:
        present = set(part.schema_arrow.names)
        data = part.read(columns=[c for c in columns if c in present])
    arrays = []
    for name in columns:
        field = schema.field(name)
        if name in data.column_names:
            arrays.append(data[name])
        elif field.nullable:
            arrays.append(pa.nulls(data.num_rows, type=field.type))
        else:
            raise ValueError(f'Historical {table} part lacks required column {name}')
    return pa.Table.from_arrays(arrays, names=list(columns))


def _table_columns(table, objective):
    """pyarrow table -> {column: python list}, timestamps as epoch seconds."""
    import pyarrow as pa
    out = {}
    for name in table.column_names:
        column = table[name]
        if name in TIME_COLUMNS:
            micros = column.cast(pa.int64()).to_pylist()
            out[name] = [None if v is None else v / 1e6 for v in micros]
        elif name == 'best_so_far_metrics':
            out['best_so_far_objective'] = _objective_values(column.to_pylist(), objective)
        else:
            out[name] = column.to_pylist()
    if 'aggregation_level' in out:              # spec rows only (see SPEC_COLUMNS)
        keep = [i for i, (level, hard) in enumerate(zip(out['aggregation_level'], out['hard']))
                if level == 'aggregate' and hard is not None]
        out = {k: [v[i] for i in keep] for k, v in out.items() if k != 'aggregation_level'}
    return out


def _objective_values(maps, objective):
    """best_so_far_metrics holds the metrics of the design the run keeps as best (best_design.py: a feasible design
    always beats an infeasible one; among feasible ones the objective decides). The objective's value of it, only while
    that design is feasible: before the first feasible design there is no best feasible objective, and none is made up."""
    if not objective:
        return [None] * len(maps)
    metric = objective['metric']
    values = []
    for pairs in maps:
        value = None
        for item in pairs or ():
            if item['key'] == metric:
                value = item['value']
                break
        values.append(value)
    return values


def _rows_columns(rows, columns, objective):
    """Journal rows (dicts, timestamps as ISO text, map columns as key/value pairs) -> the same columns as a part gives."""
    out = {name: [] for name in columns if name != 'best_so_far_metrics'}
    if 'best_so_far_metrics' in columns:
        out['best_so_far_objective'] = []
    for row in rows:
        for name in columns:
            value = row.get(name)
            if name in TIME_COLUMNS:
                out[name].append(_epoch(value))
            elif name == 'best_so_far_metrics':
                out['best_so_far_objective'].extend(_objective_values([value], objective))
            else:
                out[name].append(value)
    if 'aggregation_level' in out:
        keep = [i for i, (level, hard) in enumerate(zip(out['aggregation_level'], out['hard']))
                if level == 'aggregate' and hard is not None]
        out = {k: [v[i] for i in keep] for k, v in out.items() if k != 'aggregation_level'}
    return out


class _Chunk:
    """The rows of consecutive bundles, in commit order: evaluations, learner updates and spec values."""
    def __init__(self):
        self.evaluations, self.updates, self.specs, self.spec_defs = {}, {}, {}, {}

    @staticmethod
    def _extend(target, columns):
        for name, values in columns.items():
            target.setdefault(name, []).extend(values)

    def add(self, evaluations=None, updates=None, specs=None, seq_of=None):
        if evaluations:
            self._extend(self.evaluations, evaluations)
        if updates:
            self._extend(self.updates, updates)
        if specs and specs.get('metric_name'):
            # A spec row names its evaluation; the page places it by that evaluation's commit sequence.
            specs = dict(specs, commit_seq=[seq_of.get(e) for e in specs['evaluation_id']])
            for name, unit, lower, upper, hard in zip(specs['metric_name'], specs['unit'], specs['threshold_lower'],
                                                      specs['threshold_upper'], specs['hard']):
                self.spec_defs[name] = dict(unit=unit, threshold_lower=_finite(lower), threshold_upper=_finite(upper),
                                            hard=hard)
            self._extend(self.specs, {k: v for k, v in specs.items()
                                      if k in ('commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason')})

    def as_json(self):
        def encode(columns, order):
            n = len(next(iter(columns.values()), []))
            result = {'n': n}
            for name in order:
                if name not in columns:
                    continue
                values = columns[name]
                if name in STRING_COLUMNS:          # a few distinct words, many rows: each word once, then its number
                    words, codes = {}, []
                    for value in values:
                        codes.append(-1 if value is None else words.setdefault(value, len(words)))
                    result[name] = {'values': list(words), 'codes': codes}
                else:
                    result[name] = [_finite(v) for v in values]
            return result
        evaluation_order = [c for c in EVALUATION_COLUMNS] + ['best_so_far_objective']
        return dict(evaluations=encode(self.evaluations, evaluation_order),
                    updates=encode(self.updates, UPDATE_COLUMNS),
                    specs=encode(self.specs, ('commit_seq', 'metric_name', 'raw_value', 'satisfied', 'failure_reason')),
                    spec_defs=self.spec_defs)


def _flush_chunk(data, flushes, objective):
    """The rows of these flush records, read from their parts eight at a time, kept in commit order."""
    jobs = []
    for flush in flushes:
        for table, columns in (('evaluations', ('evaluation_id',) + EVALUATION_COLUMNS + ('best_so_far_metrics',)),
                               ('learner_updates', UPDATE_COLUMNS), ('metrics', SPEC_COLUMNS)):
            if table in flush['parts']:
                jobs.append((flush['flush_id'], table, data / table / flush['parts'][table], columns))
    tables = dict(zip([(j[0], j[1]) for j in jobs],
                      _pool().map(lambda job: _table_columns(_read_part(job[2], job[1], list(job[3])), objective), jobs)))
    chunk = _Chunk()
    for flush in flushes:
        evaluations = tables.get((flush['flush_id'], 'evaluations'))
        # evaluation_id is read but not delivered: the spec rows of this flush find their evaluation through it.
        seq_of = dict(zip(evaluations['evaluation_id'], evaluations['commit_seq'])) if evaluations else {}
        chunk.add(evaluations, tables.get((flush['flush_id'], 'learner_updates')),
                  tables.get((flush['flush_id'], 'metrics')), seq_of)
    return chunk


def _bundle_chunk(bundles, objective):
    chunk = _Chunk()
    for bundle in bundles:
        rows = bundle.get('rows') or {}
        evaluations = rows.get('evaluations') or []
        seq_of = {row['evaluation_id']: row['commit_seq'] for row in evaluations}
        chunk.add(_rows_columns(evaluations, EVALUATION_COLUMNS + ('best_so_far_metrics',), objective) if evaluations else None,
                  _rows_columns(rows.get('learner_updates') or [], UPDATE_COLUMNS, objective) if rows.get('learner_updates') else None,
                  _rows_columns(rows.get('metrics') or [], SPEC_COLUMNS, objective) if rows.get('metrics') else None,
                  seq_of)
    return chunk


def journal_tail(path, after_seq, *, block_size=1 << 16):
    """The journal's acknowledged bundles with commit_seq > after_seq, oldest first, read from the end backwards and
    stopping at the first older bundle - the part a flush has not published yet, not the whole journal (it can hold a
    long run when save points are off). The blocks are walked as atomic.read_jsonl_tail walks them: bytes after the final
    newline are not an acknowledged record and are skipped. Returns (bundles, complete): complete is False when the
    bundles found do not follow `after_seq` one by one - the journal was rewritten between reading the flush list and
    reading it (compaction at a save point) - or a line cannot be read; no bundle is given then, and the next read finds
    them in a part."""
    path = Path(path)
    try:
        stream = path.open('rb')
    except FileNotFoundError:
        return [], True
    found, pending, at_end, older = [], b'', True, False

    def take(line):
        nonlocal older
        if not line.strip():
            return
        bundle = json.loads(line)
        if bundle['commit_seq'] <= after_seq:
            older = True
        else:
            found.append(bundle)
    try:
        with stream:
            position = stream.seek(0, os.SEEK_END)
            while position and not older:
                size = min(position, block_size)
                position -= size
                stream.seek(position)
                pieces = (stream.read(size) + pending).split(b'\n')
                pending = pieces.pop(0)
                if at_end and pieces:
                    pieces.pop()                         # bytes after the final newline are not a committed record
                    at_end = False
                for line in reversed(pieces):
                    take(line)
                    if older:
                        break
            if not position and not at_end and not older:
                take(pending)
    except (ValueError, KeyError, TypeError, UnicodeError):
        return [], False
    found.reverse()
    if [b['commit_seq'] for b in found] != list(range(after_seq + 1, after_seq + 1 + len(found))):
        return [], False
    return found, True


def run_objective(run_dir):
    """The run's objective as its best-design tracker uses it (compile.build_specs: the last active Specs row whose
    "then lower/higher is better" is set), from the run's own effective_config.json; None when there is none."""
    from . import schema
    from .compile import build_specs
    raw = read_json(RunLayout(run_dir).effective_config, default=None)
    if not raw:
        return None
    try:
        return build_specs(schema.WorkbenchConfig.model_validate(raw))[2]
    except Exception:                       # a configuration this backend can no longer read: no objective is claimed
        return None


def learner_record(run_dir):
    """Whether this run records learner updates, and in plain words why not (engine._prepare decides the same way)."""
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
        return dict(recorded=False, every=every, reason='AI sizing only: this run has no RL learner, so no losses, '
                    'temperature or entropy.')
    if output.get('save_learner_updates') is False:
        return dict(recorded=False, every=every, reason='This run was started with "save learner updates" off '
                    '(Output settings), so its losses, temperature and entropy were not recorded.')
    return dict(recorded=True, every=every, reason=None)


def read_training(run_dir, flushes=0, *, max_rows=MAX_ROWS):
    """The Training tab's answer for one run: the rows of flush records [flushes, served) and, once served is the last
    one, the journal's tail. Raises FileNotFoundError when the folder holds no run data."""
    layout = RunLayout(Path(run_dir))
    data = layout.data
    if not (data / '_journal').is_dir():
        raise FileNotFoundError('This folder holds no recorded run data.')
    records = read_jsonl(data / '_journal' / 'flushes.jsonl')
    total = len(records)
    start = max(0, min(int(flushes), total))
    manifest = read_json(layout.manifest, default={}) or {}
    objective = run_objective(layout.run_dir)
    chosen, rows = [], 0
    for record in records[start:]:
        if chosen and rows + sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics')) > max_rows:
            break
        chosen.append(record)
        rows += sum(record['rows'].get(t, 0) for t in ('evaluations', 'learner_updates', 'metrics'))
    served = start + len(chosen)
    final = _flush_chunk(data, chosen, objective) if chosen else _Chunk()
    tail, tail_complete, latest = None, True, (records[-1]['last_seq'] if records else 0)
    if served == total:
        bundles, tail_complete = journal_tail(data / '_journal' / 'wal.jsonl', latest)
        tail = _bundle_chunk(bundles, objective).as_json()
        if bundles:
            latest = bundles[-1]['commit_seq']
    return dict(run_dir=str(layout.run_dir), run_id=manifest.get('run_id'), mode=manifest.get('mode'),
                mock=manifest.get('mock'), flushes=dict(served=served, total=total, start=start),
                final=final.as_json(), tail=tail, tail_complete=tail_complete, latest_seq=latest,
                objective=objective, learner=learner_record(layout.run_dir),
                segments=[{k: s.get(k) for k in ('segment', 'entry', 'started_utc', 'ended_utc', 'end_state', 'stop_reason')}
                          for s in manifest.get('segments') or []])
