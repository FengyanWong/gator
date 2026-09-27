"""Read-only run inspection and streaming on-demand Parquet+ZSTD export."""
from pathlib import Path
import math
import shutil
import sqlite3
import time

from .codec import VERSION, unpack
from .store import ExperimentStore


class RunReader:
    def __init__(self, root):
        path = Path(root).resolve()
        self.root = path if path.is_dir() else path.parent
        path = path / 'experiments.sqlite3' if path.is_dir() else path
        self.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        self.db.row_factory = sqlite3.Row
        if self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0] != VERSION:
            raise ValueError('Unsupported recording database schema')
        # Share decoding logic without opening a writer, making schema drift visible.
        self._decoder = ExperimentStore.__new__(ExperimentStore)
        self._decoder.db = self.db

    def call(self, operation, *args, **kwargs):
        if operation not in ('read', 'pending', 'position', 'verify_transition'):
            raise ValueError('Reader is read-only')
        return getattr(self._decoder, '_op_' + operation)(*args, **kwargs)

    def evaluations(self, run_id):
        for row in self.db.execute('SELECT * FROM evaluations WHERE run_id=? ORDER BY seq', (run_id,)):
            row = dict(row)
            row['request'] = unpack(row['request'])
            row['result'] = None if row['result'] is None else unpack(row['result'])
            yield row

    def usage(self):
        """Logical bytes on this recording root, excluding remote/other filesystems."""
        from .space import disk_bytes
        sizes = {name: disk_bytes(self.root / name) for name in ('attachments', 'checkpoints', 'temporary')}
        sizes['database'] = disk_bytes(self.root / 'experiments.sqlite3')
        sizes['journal'] = sum(disk_bytes(self.root / ('experiments.sqlite3' + suffix))
                               for suffix in ('-wal', '-shm', '-journal'))
        sizes['total'] = disk_bytes(self.root)
        sizes['other'] = max(0, sizes['total'] - sum(v for k, v in sizes.items() if k != 'total'))
        sizes['filesystem_free'] = shutil.disk_usage(self.root).free
        return dict(scope='recording_root_only', root=str(self.root), bytes=sizes)

    def overview(self, run_id=None, *, recent=5):
        """Small control/inspection snapshot; new runs do not scan historical payloads.

        Registered pending/running states are not proof of worker liveness. Old
        databases lacking cumulative breakdowns use a read-only compatibility scan.
        """
        if type(recent) is not int or not 0 <= recent <= 100:
            raise ValueError('recent must be an integer between 0 and 100')
        owns_snapshot = not self.db.in_transaction
        if owns_snapshot:
            self.db.execute('BEGIN')
        try:
            row = self.db.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone() if run_id else self.db.execute(
                'SELECT * FROM runs ORDER BY started DESC,rowid DESC LIMIT 1').fetchone()
            if row is None:
                raise KeyError(run_id or 'No recorded runs')
            run_id = row['id']
            summary = unpack(row['summary'])
            if not summary.get('breakdown_complete', False):
                from analog_optimizer.measurements.specs import SpecificationEvaluator
                evaluators = {}
                for name in ('status_counts', 'source_counts', 'error_counts', 'outcome_counts'):
                    summary[name] = {}
                for evaluation in self.evaluations(run_id):
                    result = evaluation['result']
                    if result is None:
                        continue
                    task_id = evaluation['task_id']
                    if task_id not in evaluators:
                        task = self.call('read', 'asset', task_id)
                        evaluators[task_id] = SpecificationEvaluator(self.call('read', 'asset', task['spec_id']))
                    observation = self._decoder._load_state(result.get('state_id'))
                    verdict = (observation.evaluation if observation is not None else
                               evaluators[task_id].evaluate(result['metrics'], result.get('metric_units', {}),
                                                            result['metric_validity']))
                    valid = verdict.valid and result['status'] == 'ok'
                    ExperimentStore._count_result(summary, result, evaluation['request'], valid, valid and verdict.success)
            pending = {r['state']: r['n'] for r in self.db.execute(
                'SELECT state,count(*) n FROM evaluations WHERE run_id=? AND result IS NULL GROUP BY state', (run_id,))}
            recent_rows = []
            for item in self.db.execute('SELECT * FROM evaluations WHERE run_id=? ORDER BY seq DESC LIMIT ?', (run_id, recent)):
                request = unpack(item['request'])
                result = unpack(item['result']) if item['result'] is not None else {}
                recent_rows.append(dict(eval_id=item['id'], state=item['state'], started=item['started'], ended=item['ended'],
                    **{k: request.get(k) for k in ('worker_id', 'episode_id', 'step', 'phase', 'source')},
                    **{k: result.get(k) for k in ('status', 'error_class', 'error_summary', 'metrics', 'metric_validity')}))
            # Include units and bounds for the few selected designs, not whole configs/graphs.
            for name in ('initial', 'best_feasible', 'best_nominal_feasible', 'best_infeasible'):
                candidate = summary.get(name)
                if candidate is None:
                    continue
                evaluation = self.call('read', 'evaluation', candidate['eval_id'])
                task = self.call('read', 'asset', candidate['task_id'])
                result = evaluation['result']
                observation = self._decoder._load_state(result.get('state_id'))
                recorded_conditions = observation is not None and bool(observation.condition_results)
                verdict = observation.evaluation if recorded_conditions else None
                candidate.update(coverage_complete=verdict.complete if verdict else None,
                    condition_policy=observation.condition_policy if recorded_conditions else 'off',
                    robust_feasible=verdict.success if recorded_conditions and observation.condition_policy == 'always' else None,
                    missing_coverage=verdict.missing_coverage if verdict else {})
                if verdict:
                    candidate.update(nominal_feasible=verdict.nominal_success,
                        clearance_margin=verdict.clearance_margin,
                        tightest_clearance_spec=verdict.tightest_clearance_spec)
                candidate['constraints'] = []
                for spec in self.call('read', 'asset', task['spec_id']):
                    def measured(metrics, validity, units, available=True):
                        value = metrics.get(spec.metric_id)
                        valid = (available and validity.get(spec.metric_id, False) and value is not None
                                 and math.isfinite(value) and units.get(spec.metric_id) == spec.unit)
                        met = ((spec.lower is None or value >= spec.lower) and
                               (spec.upper is None or value <= spec.upper)) if valid else None
                        return dict(value=value, valid=bool(valid), met=met)

                    details = []
                    aggregate = measured(result['metrics'], result['metric_validity'], result.get('metric_units', {}),
                                         result['status'] == 'ok')
                    if recorded_conditions and spec.active:
                        rows = observation.condition_results[:1] if spec.nominal_only else observation.condition_results
                        for condition_result in rows:
                            condition = condition_result.condition
                            details.append(dict(condition=condition.corner.id if condition else 'nominal',
                                **measured(condition_result.metrics, condition_result.metric_validity,
                                           condition_result.metric_units,
                                           condition_result.status == 'ok' and condition_result.candidate_evaluated)))
                        valid = verdict.worst_valid[spec.metric_id] and not verdict.missing_coverage[spec.metric_id]
                        # Bounds on every actual value are authoritative, not rounded reward penalties.
                        aggregate = dict(value=verdict.worst_values[spec.metric_id], valid=valid,
                                         met=all(item['met'] is True for item in details) if valid else None)
                    candidate['constraints'].append(dict(metric=spec.metric_id, unit=spec.unit, lower=spec.lower,
                        upper=spec.upper, **aggregate, required=spec.required, active=spec.active,
                        nominal_only=spec.nominal_only, conditions=details,
                        binding_condition=verdict.worst_conditions.get(spec.metric_id) if verdict else None,
                        missing_coverage=verdict.missing_coverage.get(spec.metric_id, ()) if verdict else ()))
            summary['wall_seconds'] = (row['ended'] or time.time()) - row['started']
            full = self.db.execute("SELECT step,path FROM checkpoints WHERE run_id=? AND kind='full' AND status='retained' "
                                   'ORDER BY step DESC,rowid DESC LIMIT 1', (run_id,)).fetchone()
            state = 'ended_with_pending' if row['ended'] and pending else 'ended' if row['ended'] else 'open'
            result = dict(format_version='run-overview-v1', run_id=run_id, lifecycle=state,
                          started=row['started'], ended=row['ended'], pending_by_state=pending, summary=summary,
                          recent_evaluations=recent_rows, latest_checkpoint=None if full is None else dict(full))
        finally:
            if owns_snapshot:
                self.db.rollback()
        # Filesystem usage is a separate live measurement, outside the SQL read lock.
        result['storage'] = self.usage()
        return result

    def export(self, run_id, destination, *, batch_size=512):
        """One coherent SQLite read snapshot; numeric columns + exact relational payloads.

        Exact payloads use recording.codec.unpack(), including dtype/shape/field
        order. Arrow does not infer heterogeneous circuit arrays or round floats.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError('Export batch size must be positive')
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        queries = {
            'runs': ('SELECT * FROM runs WHERE id=?', (run_id,)),
            'evaluations': ('SELECT * FROM evaluations WHERE run_id=? ORDER BY seq', (run_id,)),
            'transitions': ('SELECT t.* FROM transitions t JOIN evaluations e ON t.eval_id=e.id WHERE e.run_id=? ORDER BY t.seq', (run_id,)),
        }
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='simulation_jobs'").fetchone():
            queries['simulation_jobs'] = ('SELECT j.* FROM simulation_jobs j JOIN evaluations e ON j.eval_id=e.id '
                                          'WHERE e.run_id=? ORDER BY e.seq,j.job_index', (run_id,))
        self.db.execute('BEGIN')
        try:
            # Include only this run's static definitions and their explicit references.
            run = self.call('read', 'run', run_id)
            asset_ids = {run['config_id']}
            state_ids, task_ids = set(), set()
            for row in self.evaluations(run_id):
                asset_ids.update((row['task_id'], row['graph_id']))
                if row['request'].get('condition_id'):
                    asset_ids.add(row['request']['condition_id'])
                if row['result'] and row['result'].get('simulator_version_asset_id'):
                    asset_ids.add(row['result']['simulator_version_asset_id'])
                if row['result'] and row['result'].get('state_id'):
                    state_ids.add(row['result']['state_id'])
                task_ids.add(row['task_id'])
            for task_id in task_ids:
                asset_ids.add(self.call('read', 'asset', task_id)['spec_id'])
            for row in self.db.execute('SELECT t.state_id,t.next_state_id FROM transitions t JOIN evaluations e ON t.eval_id=e.id WHERE e.run_id=?', (run_id,)):
                state_ids.update(key for key in row if key is not None)
            # Explicit asset references in run configuration (e.g. project snapshot/template).
            def references(value):
                if isinstance(value, dict):
                    for key, val in value.items():
                        if key.endswith('_asset_id') and isinstance(val, str):
                            asset_ids.add(val)
                        references(val)
                elif isinstance(value, (list, tuple)):
                    for val in value:
                        references(val)
            references(run['configuration'])
            # Keep SQL parameter counts bounded, and do not include another run's
            # observations merely because it shares this task's static graph.
            for table, selected in [('assets', asset_ids), ('states', state_ids)]:
                writer = None
                keys = sorted(selected)
                chunk_size = min(batch_size, 512)
                try:
                    for offset in range(0, len(keys), chunk_size):
                        chunk = keys[offset:offset + chunk_size]
                        rows = [dict(r) for r in self.db.execute(
                            f'SELECT * FROM {table} WHERE id IN (' + ','.join('?' * len(chunk)) + ')', chunk)]
                        arrow = pa.Table.from_pylist(rows)
                        if writer is None:
                            writer = pq.ParquetWriter(destination / f'{table}.parquet', arrow.schema, compression='zstd')
                        writer.write_table(arrow)
                finally:
                    if writer:
                        writer.close()
            for name, (sql, args) in queries.items():
                cursor = self.db.execute(sql, args)
                writer = None
                try:
                    while rows := cursor.fetchmany(batch_size):
                        rows = [dict(row) for row in rows]
                        # Explicit SQL schema prevents all-null first batches from fixing Arrow null types.
                        columns = {}
                        schema = {r['name']: r['type'] for r in self.db.execute(f'PRAGMA table_info({name})')}
                        for key in rows[0]:
                            dtype = {'TEXT': pa.string(), 'BLOB': pa.binary(), 'INTEGER': pa.int64(), 'REAL': pa.float64()}[schema[key]]
                            columns[key] = pa.array([r[key] for r in rows], type=dtype)
                        table = pa.table(columns)
                        if writer is None:
                            writer = pq.ParquetWriter(destination / f'{name}.parquet', table.schema, compression='zstd')
                        writer.write_table(table)
                finally:
                    if writer:
                        writer.close()
            # A compact, convenient long numeric table; original typed payloads remain authoritative.
            schema = pa.schema([('eval_id', pa.string()), ('metric', pa.string()), ('value', pa.float64()),
                                ('valid', pa.bool_()), ('unit', pa.string()), ('status', pa.string())])
            with pq.ParquetWriter(destination / 'metrics.parquet', schema, compression='zstd') as writer:
                rows = []
                for evaluation in self.evaluations(run_id):
                    result = evaluation['result']
                    if result is None:
                        continue
                    for key, value in result['metrics'].items():
                        rows.append(dict(eval_id=evaluation['id'], metric=key, value=value,
                                         valid=result['metric_validity'][key], unit=result.get('metric_units', {}).get(key),
                                         status=result['status']))
                    if len(rows) >= batch_size:
                        writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                        rows.clear()
                if rows:
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        finally:
            self.db.rollback()
        return destination

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
