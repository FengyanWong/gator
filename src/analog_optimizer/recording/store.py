"""SQLite is the authoritative numerical store; one queued writer per database.

Use start_service() for spawned process workers. Only the service opens a write
connection; workers synchronously wait for each durable acknowledgement.
"""
from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
from dataclasses import fields
from functools import lru_cache
import fcntl
import hashlib
import json
import math
from multiprocessing.managers import BaseManager
from pathlib import Path
import queue
import sqlite3
import threading
import time
from uuid import uuid4

from .codec import VERSION, identity, pack, unpack, tree, untree, diff, patched, raw
from .space import (RecordingConfig, SpaceExhausted, filesystem, disk_bytes, require_space,
                    create_workspace, checked_workspace, remove_workspace, fsync_directory)

SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, kind TEXT NOT NULL, data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, config_id TEXT NOT NULL REFERENCES assets(id),
  started REAL NOT NULL, ended REAL, summary BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS evaluations(seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
  task_id TEXT NOT NULL REFERENCES assets(id), graph_id TEXT NOT NULL REFERENCES assets(id),
  state TEXT NOT NULL, request BLOB NOT NULL, result BLOB, result_hash TEXT,
  started REAL NOT NULL, ended REAL, dispatched INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS evaluations_run ON evaluations(run_id,seq);
CREATE INDEX IF NOT EXISTS evaluations_pending ON evaluations(run_id,state) WHERE result IS NULL;
CREATE TABLE IF NOT EXISTS states(id TEXT PRIMARY KEY, graph_id TEXT NOT NULL REFERENCES assets(id),
  task_id TEXT NOT NULL REFERENCES assets(id), data BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS transitions(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
  eval_id TEXT NOT NULL REFERENCES evaluations(id), state_id TEXT REFERENCES states(id),
  next_state_id TEXT REFERENCES states(id), data BLOB NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, eval_id TEXT NOT NULL REFERENCES evaluations(id),
  data BLOB NOT NULL, cleaned INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS workspaces_eval ON workspaces(eval_id);
CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  eval_id TEXT NOT NULL REFERENCES evaluations(id), role TEXT NOT NULL, error_type TEXT,
  path TEXT, bytes INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT);
CREATE INDEX IF NOT EXISTS attachments_run ON attachments(run_id,status);
CREATE TABLE IF NOT EXISTS checkpoints(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  path TEXT NOT NULL, kind TEXT NOT NULL, step INTEGER NOT NULL, data BLOB NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS updates(run_id TEXT NOT NULL REFERENCES runs(id), first_update INTEGER NOT NULL,
  last_update INTEGER NOT NULL, data BLOB NOT NULL, PRIMARY KEY(run_id,first_update));
'''


def wal_fixed(version):
    return version >= (3, 53, 0) or (3, 51, 3) <= version < (3, 52, 0) or (
        (3, 50, 7) <= version < (3, 51, 0)) or ((3, 44, 6) <= version < (3, 45, 0))


class ExperimentStore:
    def __init__(self, root, config=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ('experiments.sqlite3', '.writer.lock', 'attachments', 'checkpoints', 'temporary'):
            if (self.root / name).is_symlink():
                raise ValueError('Recording paths must not be symlinks')
        self.config = config if isinstance(config, RecordingConfig) else RecordingConfig(**(config or {}))
        fs = filesystem(self.root)
        if fs not in ('ext4', 'xfs', 'btrfs', 'tmpfs', 'overlay', 'zfs'):
            raise ValueError(f'Use a verified local Linux filesystem for SQLite, not {fs}: {self.root}')
        if self.config.journal_mode == 'WAL' and not wal_fixed(sqlite3.sqlite_version_info):
            raise ValueError(f'SQLite {sqlite3.sqlite_version} has no verified WAL-reset fix; use DELETE')
        self.path = self.root / 'experiments.sqlite3'
        self._lock = (self.root / '.writer.lock').open('a+b')
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self._lock.close()
            raise RuntimeError('Another writer owns this database')
        for name in ('attachments', 'checkpoints', 'temporary'):
            (self.root / name).mkdir(exist_ok=True)
        self._queue = queue.Queue(maxsize=256)
        self._closed, self._failure = False, None
        self._ready = Future()
        # Immutable content-addressed definitions; never cache mutable observations.
        self._state_definition = lru_cache(maxsize=16)(self._state_definition)
        self._thread = threading.Thread(target=self._writer, name='gator-sqlite-writer', daemon=True)
        self._thread.start()
        try:
            self._ready.result()
        except BaseException:
            self.close()
            raise

    def _writer(self):
        try:
            self.db = sqlite3.connect(self.path, timeout=30)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA busy_timeout=30000')
            self.db.execute(f'PRAGMA journal_mode={self.config.journal_mode}')
            self.db.execute('PRAGMA synchronous=EXTRA')
            if self.config.journal_mode == 'WAL':
                self.db.execute('PRAGMA wal_autocheckpoint=1000')
                self.db.execute('PRAGMA journal_size_limit=8388608')
            self.db.executescript(SCHEMA)
            old = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if old and old[0] != VERSION:
                raise ValueError('Unsupported recording database schema')
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO meta VALUES('schema',?)", (VERSION,))
                self.db.execute("INSERT OR IGNORE INTO meta VALUES('database_id',?)", (uuid4().hex,))
                self.db.execute("INSERT OR REPLACE INTO meta VALUES('sqlite_version',?)", (sqlite3.sqlite_version,))
            self._database_id = self.db.execute("SELECT value FROM meta WHERE key='database_id'").fetchone()[0]
            self._ready.set_result(None)
            while True:
                item = self._queue.get()
                if item is None:
                    break
                name, args, kwargs, future = item
                try:
                    if self._failure is not None and name not in ('read', 'usage', 'pending', 'position'):
                        raise RuntimeError('Writer previously failed; stop dispatch and recover') from self._failure
                    method = getattr(self, '_op_' + name)
                    with self.db:
                        result = method(*args, **kwargs)
                    # No acknowledgement before transaction commit succeeds.
                    future.set_result(result)
                except BaseException as exc:
                    if isinstance(exc, (sqlite3.Error, OSError)):
                        self._failure = exc
                    future.set_exception(exc)
            if self.config.journal_mode == 'WAL':
                self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except BaseException as exc:
            self._failure = exc
            if not self._ready.done():
                self._ready.set_exception(exc)
        finally:
            if hasattr(self, 'db'):
                self.db.close()

    def call(self, operation, *args, **kwargs):
        if self._closed or not self._thread.is_alive():
            raise RuntimeError('Recording writer is closed or dead')
        if not hasattr(self, '_op_' + operation):
            raise ValueError('Unknown recording operation')
        future = Future()
        # Snapshot before enqueue: caller mutation cannot alter a queued record.
        self._queue.put((operation, deepcopy(args), deepcopy(kwargs), future))
        return future.result()

    def close(self):
        if not self._closed:
            self._closed = True
            if self._thread.is_alive():
                self._queue.put(None)
                self._thread.join()
            self._state_definition.cache_clear()
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _op_asset(self, kind, value):
        key = identity((kind, value))
        if not self.db.execute('SELECT 1 FROM assets WHERE id=?', (key,)).fetchone():
            self.db.execute('INSERT INTO assets VALUES(?,?,?)', (key, kind, pack(value)))
        return key

    def _asset(self, key):
        row = self.db.execute('SELECT data FROM assets WHERE id=?', (key,)).fetchone()
        if row is None:
            raise KeyError(key)
        return unpack(row[0])

    def _op_run(self, configuration, run_id=None):
        config_id = self._op_asset('run_config', configuration)
        run_id = run_id or uuid4().hex
        row = self.db.execute('SELECT config_id FROM runs WHERE id=?', (run_id,)).fetchone()
        if row:
            if row[0] != config_id:
                raise ValueError('Run ID reused with different configuration')
            return run_id
        summary = dict(initial=None, best_feasible=None, best_infeasible=None, has_feasible=False,
                       first_feasible=None, evaluations=0, real_simulations=0, failures=0, cache_hits=0,
                       wall_seconds=0.0, selection=configuration.get('selection', {'feasible': 'first_feasible'}),
                       best_scope='best observed; no global optimality claim')
        summary.update(breakdown_complete=True, status_counts={}, error_counts={}, source_counts={},
                       outcome_counts={})
        self.db.execute('INSERT INTO runs VALUES(?,?,?,NULL,?)', (run_id, config_id, time.time(), pack(summary)))
        return run_id

    def _op_task(self, graph, specs, configuration=None):
        graph_id = self._op_asset('graph', graph)
        spec_id = self._op_asset('spec', tuple(specs))
        groups = [{f.name: getattr(g, f.name) for f in fields(g) if f.name != 'value'}
                  for g in graph.parameter_groups]
        task = dict(schema_version=VERSION, circuit_id=graph.circuit_id, graph_id=graph_id,
                    spec_id=spec_id, variables=groups, action_version='absolute-group-v1',
                    action_rule='absolute linear/log -> clamp -> nearest grid half up -> bindings',
                    reward_version='negative_weighted_mean_capped_violation-v1', tolerance=0.0,
                    configuration=configuration or {})
        return self._op_asset('task', task), graph_id

    def _op_begin(self, run_id, task_id, graph_id, request, eval_id=None):
        eval_id = eval_id or uuid4().hex
        defaults = dict(parent_step_id=None, worker_id='0', episode_id=None, phase='training',
                        retry=0, source='mock', cache_eval_id=None, corner_id=None, sample_id=None, seed=None,
                        condition_id=None)
        defaults.update(request)
        request = defaults
        registration_hash = identity(request)
        old = self.db.execute('SELECT * FROM evaluations WHERE id=?', (eval_id,)).fetchone()
        if old:
            if (old['run_id'], old['task_id'], old['graph_id'], unpack(old['request']).get('registration_hash')) != (
                    run_id, task_id, graph_id, registration_hash):
                raise ValueError('Evaluation ID reused with different request')
            return eval_id
        self._op_preflight()
        if self._asset(task_id)['graph_id'] != graph_id:
            raise ValueError('Task/graph mismatch')
        if request.get('source') == 'cache':
            cached = self._evaluation(request.get('cache_eval_id'))
            if cached['result'] is None or cached['task_id'] != task_id:
                raise ValueError('Cache source must be a committed evaluation of this task')
            if any(request.get(key) != cached['request'].get(key)
                   for key in ('condition_id', 'corner_id', 'sample_id', 'seed')):
                raise ValueError('Cache cannot reuse a different condition or random sample')
        request['registration_hash'] = registration_hash
        self.db.execute('INSERT INTO evaluations(id,run_id,task_id,graph_id,state,request,started) '
                        'VALUES(?,?,?,?,?,?,?)', (eval_id, run_id, task_id, graph_id, 'pending', pack(defaults), time.time()))
        return eval_id

    def _evaluation(self, eval_id):
        row = self.db.execute('SELECT * FROM evaluations WHERE id=?', (eval_id,)).fetchone()
        if row is None:
            raise KeyError(eval_id)
        row = dict(row)
        row['request'] = unpack(row['request'])
        row['result'] = None if row['result'] is None else unpack(row['result'])
        return row

    def _op_start(self, eval_id, parameters, details=None):
        row = self._evaluation(eval_id)
        if row['state'] not in ('pending', 'running'):
            raise ValueError('Evaluation already ended')
        request = row['request']
        if request.get('source') == 'cache':
            raise ValueError('Cache reuse cannot dispatch a new simulator')
        if row['state'] == 'running' and (request.get('applied_parameters') != parameters or
                                          request.get('dispatch_details') != (details or {})):
            raise ValueError('Repeated dispatch has different executed parameters')
        request.update(applied_parameters=parameters, dispatch_details=details or {})
        self.db.execute('UPDATE evaluations SET state=?,request=?,dispatched=1 WHERE id=?',
                        ('running', pack(request), eval_id))
        return eval_id

    def _state_definition(self, graph_id, task_id):
        return tree(self._asset(graph_id)), self._asset(self._asset(task_id)['spec_id'])

    def _state(self, observation, graph_id, task_id):
        if observation is None:
            return None
        template, specs = self._state_definition(graph_id, task_id)
        encoded = tree(observation.graph)
        patches = diff(template, encoded)
        if patched(template, patches) != encoded:
            raise ValueError('Graph reconstruction is not exact')
        values = {f.name: getattr(observation, f.name) for f in fields(observation)
                  if f.name not in ('graph', 'specs')}
        if tuple(observation.specs) != specs:
            raise ValueError('State spec differs from task')
        data = dict(graph_patches=patches, observation=values,
                    normalizer_version='fixed-references-signed-log1p-v1')
        key = identity((graph_id, task_id, data))
        if not self.db.execute('SELECT 1 FROM states WHERE id=?', (key,)).fetchone():
            self.db.execute('INSERT INTO states VALUES(?,?,?,?)', (key, graph_id, task_id, pack(data)))
        return key

    def _load_state(self, state_id):
        if state_id is None:
            return None
        from analog_optimizer.envs.sizing import Observation
        row = self.db.execute('SELECT * FROM states WHERE id=?', (state_id,)).fetchone()
        if row is None:
            raise KeyError(state_id)
        data = unpack(row['data'])
        graph = untree(patched(tree(self._asset(row['graph_id'])), data['graph_patches']))
        specs = self._asset(self._asset(row['task_id'])['spec_id'])
        return Observation(graph=graph, specs=specs, **data['observation'])

    def _op_finish(self, eval_id, result, *, observation=None, transition=None):
        row = self._evaluation(eval_id)
        result = deepcopy(result)
        invocations = result.get('simulator_invocations', 0)
        if type(invocations) is not int or invocations < 0:
            raise ValueError('Explicit nonnegative simulator invocation count required')
        if row['request']['source'] == 'cache' and invocations:
            raise ValueError('Cache hits cannot count as real simulator calls')
        error = str(result.get('error_summary', result.get('error', ''))).encode('utf8')
        result['error_summary'] = error[:self.config.error_bytes].decode('utf8', errors='ignore')
        result.pop('error', None)
        metrics, validity = result.get('metrics', {}), result.get('metric_validity', {})
        for name in set(metrics) | set(validity):
            value = metrics.get(name)
            valid = validity.get(name) is True and isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
            # Keep finite partial values even when validity=False, in a separate diagnostic map.
            if not valid and isinstance(value, (float, int)) and math.isfinite(value):
                result.setdefault('partial_metrics', {})[name] = value
            metrics[name], validity[name] = (value if valid else None), valid
        result.update(metrics=metrics, metric_validity=validity)
        result['state_id'] = self._state(observation, row['graph_id'], row['task_id'])
        digest = identity((result, transition))
        if row['result_hash'] is not None:
            if row['result_hash'] != digest:
                raise ValueError('Conflicting duplicate evaluation result')
            return self._receipt(row)
        if row['request']['source'] == 'cache':
            cached = self._evaluation(row['request']['cache_eval_id'])
            for key in ('applied_parameters', 'metrics', 'metric_validity', 'metric_units'):
                if result.get(key) != cached['result'].get(key):
                    raise ValueError('Cache result differs from original evaluation')
        ended = time.time()
        self.db.execute('UPDATE evaluations SET state=?,result=?,result_hash=?,ended=? WHERE id=?',
                        ('completed', pack(result), digest, ended, eval_id))
        row.update(state='completed', result=result, result_hash=digest, ended=ended)
        if transition is not None:
            self._transition(row, transition, {id(observation): result['state_id']})
        self._summary(row)
        return self._receipt(row)

    def _receipt(self, row):
        return dict(eval_id=row['id'], result_hash=row['result_hash'],
                    database_id=self._database_id, committed=True)

    def _transition(self, row, transition, known_states):
        eval_id = row['id']
        data = dict(transition)
        if data.get('replay_eligible') is True:
            from .session import transition_from_data
            # Derived by the writer from the exact submitted states, never trust
            # a caller-supplied fingerprint. _state verifies their reconstruction.
            data.pop('replay_fingerprint', None)
            data['replay_fingerprint'] = transition_from_data(data, validate=False).fingerprint()
        def state(value):
            return known_states[id(value)] if id(value) in known_states else self._state(value, row['graph_id'], row['task_id'])
        first = state(data.pop('observation', None))
        last = state(data.pop('next_observation', None))
        data.update(task_id=row['task_id'], graph_id=row['graph_id'], eval_id=eval_id)
        for flag in ('terminated', 'truncated'):
            if type(data.get(flag)) is not bool:
                raise ValueError('Transition needs separate boolean end flags')
        tid = data.pop('transition_id', eval_id)
        digest = identity((first, last, data))
        old = self.db.execute('SELECT hash FROM transitions WHERE id=?', (tid,)).fetchone()
        if old and old[0] != digest:
            raise ValueError('Conflicting transition ID')
        self.db.execute('INSERT OR IGNORE INTO transitions(id,eval_id,state_id,next_state_id,data,hash) '
                        'VALUES(?,?,?,?,?,?)', (tid, eval_id, first, last, pack(data), digest))
        return tid

    def _op_verify_transition(self, transition_id, fingerprint):
        row = self.db.execute('SELECT t.data,e.result_hash,e.state FROM transitions t '
                              'JOIN evaluations e ON e.id=t.eval_id WHERE t.id=?', (transition_id,)).fetchone()
        if row is None or row['result_hash'] is None or row['state'] != 'completed':
            raise ValueError('Replay requires a committed transition')
        data = unpack(row['data'])
        if data.get('replay_eligible') is not True:
            raise ValueError('Recorded transition is ineligible for training replay')
        expected = data.get('replay_fingerprint')
        if expected is None:
            # Databases written before fingerprint admission remain usable;
            # only those older rows require full readback, with no migration.
            from .session import transition_from_data
            expected = transition_from_data(self._op_read('transition', transition_id)).fingerprint()
        if expected != fingerprint:
            raise ValueError('Replay differs from durable transition')
        return True

    def _summary(self, row):
        from analog_optimizer.measurements.specs import SpecificationEvaluator
        run = self.db.execute('SELECT * FROM runs WHERE id=?', (row['run_id'],)).fetchone()
        summary, result, request = unpack(run['summary']), row['result'], row['request']
        specs = self._asset(self._asset(row['task_id'])['spec_id'])
        evaluation = SpecificationEvaluator(specs).evaluate(result['metrics'], result.get('metric_units', {}), result['metric_validity'])
        valid = evaluation.valid and result.get('status') == 'ok'
        feasible = valid and evaluation.success
        # Uncapped weighted violation distinguishes very bad infeasible candidates.
        violations = {}
        if valid:
            for spec in specs:
                if spec.active and spec.required:
                    value = result['metrics'][spec.metric_id]
                    violations[spec.metric_id] = max(0.0, (spec.lower - value) / spec.scale if spec.lower is not None else 0.0,
                                                      (value - spec.upper) / spec.scale if spec.upper is not None else 0.0)
        weights = {s.metric_id: s.weight for s in specs if s.active and s.required}
        score = sum(violations[k] * weights[k] for k in violations) / sum(weights.values()) if valid else None
        candidate = dict(eval_id=row['id'], task_id=row['task_id'], parameters=result.get('applied_parameters'),
                         metrics=result['metrics'], valid=valid, feasible=feasible,
                         violations=violations if valid else evaluation.violations, violation_score=score)
        summary['evaluations'] += 1
        real = request['source'] != 'cache' and bool(result.get('simulator_invocations', 0))
        summary['real_simulations'] += int(result.get('simulator_invocations', 0)) if real else 0
        summary['real_dispatches'] = summary.get('real_dispatches', 0) + int(request['source'] == 'spectre' and row['dispatched'])
        summary['unconfirmed_invocations'] = summary.get('unconfirmed_invocations', 0) + int(result.get('invocation_uncertain', False))
        summary['cache_hits'] += request['source'] == 'cache'
        summary['failures'] += result.get('status') != 'ok' or not evaluation.valid
        self._count_result(summary, result, request, valid, feasible)
        summary['wall_seconds'] = row['ended'] - run['started']
        if summary['initial'] is None and request['phase'] == 'initial':
            summary['initial'] = candidate
        # PVT/MC and validation have independent records; they do not change nominal best.
        nominal = request.get('sample_id') is None and request['phase'] not in ('validation', 'pvt_validation', 'mc_validation')
        if request.get('condition_id'):
            condition = self._asset(request['condition_id'])
            if condition is not None:
                purpose = condition.get('purpose') if isinstance(condition, dict) else condition.purpose
                nominal = nominal and purpose == 'nominal'
        if nominal and feasible:
            if not summary['has_feasible']:
                summary['first_feasible'] = dict(eval_id=row['id'], real_simulations=summary['real_simulations'],
                                                 unconfirmed_invocations=summary['unconfirmed_invocations'],
                                                 seconds=summary['wall_seconds'])
            summary['has_feasible'] = True
            objective = summary['selection'].get('objective')
            old = summary['best_feasible']
            better = old is None
            if objective:
                metric, direction = objective['metric'], objective['direction']
                value = result['metrics'].get(metric)
                if value is None or direction not in ('min', 'max'):
                    raise ValueError('Feasible selection objective unavailable or invalid')
                candidate['objective'] = value
                better = old is None or (value < old['objective'] if direction == 'min' else value > old['objective'])
            if better:
                summary['best_feasible'] = candidate
        elif nominal and valid:
            old = summary['best_infeasible']
            if old is None or score < old['violation_score']:
                summary['best_infeasible'] = candidate
        self.db.execute('UPDATE runs SET summary=? WHERE id=?', (pack(summary), row['run_id']))

    @staticmethod
    def _count_result(summary, result, request, valid, feasible):
        outcome = 'feasible' if feasible else 'infeasible' if valid else 'failed'
        for field, key in [('status_counts', result.get('status', 'unknown')),
                           ('source_counts', request.get('source', 'unknown')),
                           ('outcome_counts', outcome)]:
            counts = summary.setdefault(field, {})
            counts[key] = counts.get(key, 0) + 1
        if not valid:
            key = result.get('error_class') or result.get('status', 'unknown')
            if result.get('status') == 'ok':
                key = 'invalid_metrics'
            counts = summary.setdefault('error_counts', {})
            counts[key] = counts.get(key, 0) + 1

    def _op_pending(self, run_id=None):
        sql = "SELECT id FROM evaluations WHERE result IS NULL AND state IN ('pending','running','interrupted')"
        args = ()
        if run_id:
            sql += ' AND run_id=?'
            args = (run_id,)
        return [self._evaluation(r[0]) for r in self.db.execute(sql, args)]

    def _op_recover(self, eval_ids):
        # Only after caller establishes the workers are stopped. No auto redispatch/delete.
        for key in eval_ids:
            row = self._evaluation(key)
            if row['result'] is None:
                self.db.execute("UPDATE evaluations SET state='interrupted' WHERE id=?", (key,))
        return self._op_pending()

    def _op_position(self):
        return dict(database_id=self.db.execute("SELECT value FROM meta WHERE key='database_id'").fetchone()[0],
                    evaluation_seq=self.db.execute('SELECT coalesce(max(seq),0) FROM evaluations WHERE result IS NOT NULL').fetchone()[0],
                    transition_seq=self.db.execute('SELECT coalesce(max(seq),0) FROM transitions').fetchone()[0])

    def _op_configuration(self):
        return dict(vars(self.config))

    def _op_recording_root(self):
        return str(self.root)

    def _op_verify_receipt(self, receipt):
        row = self.db.execute('SELECT id,result_hash FROM evaluations WHERE id=?', (receipt['eval_id'],)).fetchone()
        if row is None or row['result_hash'] is None or receipt != self._receipt(row):
            raise ValueError('Expected durable acknowledgement of this evaluation')
        return True

    def _op_retention(self, receipt):
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Retention requires durable acknowledgement')
        summary = unpack(self.db.execute('SELECT summary FROM runs WHERE id=?', (row['run_id'],)).fetchone()[0])
        role = None
        if summary['initial'] and summary['initial']['eval_id'] == row['id']:
            role = 'initial'
        elif row['result']['status'] != 'ok' or row['result'].get('environment', {}).get('evaluation_valid') is False:
            role = 'failure'
        else:
            best = summary['best_feasible'] or summary['best_infeasible']
            if best and best['eval_id'] == row['id']:
                role = 'best'
        return dict(role=role, error_class=row['result'].get('error_class'))

    def _op_external_workspace(self, data):
        self._evaluation(data['eval_id'])
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?,0)', (data['token'], data['eval_id'], pack(data)))

    def _op_external_cleaned(self, receipt, token):
        self._op_verify_receipt(receipt)
        row = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if row is None or row['eval_id'] != receipt['eval_id'] or not unpack(row['data'])['finished']:
            raise ValueError('Workspace acknowledgement mismatch')
        self.db.execute('UPDATE workspaces SET cleaned=1 WHERE id=?', (token,))

    def _op_read(self, kind, key=None):
        if kind == 'evaluation':
            return self._evaluation(key)
        if kind == 'asset':
            return self._asset(key)
        if kind == 'run_configuration':
            return self._asset(self.db.execute('SELECT config_id FROM runs WHERE id=?', (key,)).fetchone()[0])
        if kind == 'state':
            return self._load_state(key)
        if kind == 'transition':
            row = self.db.execute('SELECT * FROM transitions WHERE id=?', (key,)).fetchone()
            if row is None:
                raise KeyError(key)
            return dict(unpack(row['data']), observation=self._load_state(row['state_id']),
                        next_observation=self._load_state(row['next_state_id']))
        if kind == 'run':
            row = dict(self.db.execute('SELECT * FROM runs WHERE id=?', (key,)).fetchone())
            row['summary'] = unpack(row['summary'])
            row['configuration'] = self._asset(row['config_id'])
            row['pending'] = len(self._op_pending(key))
            row['summary']['wall_seconds'] = (row['ended'] or time.time()) - row['started']
            return row
        if kind in ('runs', 'assets', 'states', 'evaluations', 'transitions', 'attachments', 'checkpoints', 'updates', 'workspaces'):
            return [dict(r) for r in self.db.execute(f'SELECT * FROM {kind}')]
        raise ValueError('Unknown read kind')

    def _op_end_run(self, run_id):
        self.db.execute('UPDATE runs SET ended=? WHERE id=?', (time.time(), run_id))

    def _op_workspace(self, eval_id):
        row = self._evaluation(eval_id)
        if row['result'] is not None:
            raise ValueError('Evaluation already ended')
        data = create_workspace(self.root / 'temporary', eval_id)
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?,0)', (data['token'], eval_id, pack(data)))
        return data

    def _op_begin_workspace(self, run_id, task_id, graph_id, request, eval_id=None):
        """One pre-dispatch transaction for the request and its owned workspace."""
        eval_id = self._op_begin(run_id, task_id, graph_id, request, eval_id=eval_id)
        for row in self.db.execute('SELECT data FROM workspaces WHERE eval_id=? AND cleaned=0', (eval_id,)):
            data = unpack(row['data'])
            if data['host'] == 'local':
                return data
        return self._op_workspace(eval_id)

    def _op_workspace_finished(self, token):
        row = self.db.execute('SELECT data FROM workspaces WHERE id=?', (token,)).fetchone()
        data = unpack(row[0])
        data['finished'] = True
        self.db.execute('UPDATE workspaces SET data=? WHERE id=?', (pack(data), token))

    def _op_finalize_workspace(self, receipt, token):
        """Separate from result commit: only an already durable result permits cleanup.

        Metadata changes share one transaction; file deletion still requires the
        existing ownership and live-process checks. A failed commit can leave
        stale cleanup metadata, never an uncommitted numerical result deleted.
        """
        self._op_verify_receipt(receipt)
        workspace = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if workspace is None or workspace['eval_id'] != receipt['eval_id']:
            raise ValueError('Workspace/evaluation mismatch')
        if workspace['cleaned']:
            return
        data = unpack(workspace['data'])
        if data['host'] != 'local':
            raise ValueError('Local finalization cannot remove a remote workspace')
        self._op_workspace_finished(token)
        retention = self._op_retention(receipt)
        if retention['role']:
            self._op_attach(receipt, token, retention['role'], retention['error_class'])
        self._op_cleanup(receipt, token)

    def _op_cleanup(self, receipt, token):
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Cleanup requires a matching durable result acknowledgement')
        item = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if item is None or item['eval_id'] != row['id']:
            raise ValueError('Workspace belongs to another evaluation')
        remove_workspace(unpack(item['data']))
        self.db.execute('UPDATE workspaces SET cleaned=1 WHERE id=?', (token,))

    def _op_usage(self):
        return dict(database=disk_bytes(self.path),
                    journal=sum(disk_bytes(Path(str(self.path) + suffix)) for suffix in ('-wal', '-shm', '-journal')),
                    attachments=disk_bytes(self.root / 'attachments'), checkpoints=disk_bytes(self.root / 'checkpoints'),
                    temporary=disk_bytes(self.root / 'temporary'), total=disk_bytes(self.root))

    def _evict(self, item):
        path = Path(item['path'])
        if path.parent != self.root / 'attachments' or path.is_symlink():
            raise ValueError('Attachment path escaped its dedicated directory')
        path.unlink(missing_ok=True)
        fsync_directory(path.parent)
        self.db.execute("UPDATE attachments SET status='evicted',reason='budget_or_replaced' WHERE id=?", (item['id'],))

    def _op_preflight(self, extra=0):
        in_flight = self.db.execute("SELECT count(*) FROM evaluations WHERE result IS NULL").fetchone()[0]
        reserved = (in_flight + 1) * (self.config.temporary_reserve + self.config.result_reserve) + extra
        try:
            require_space(self.root, self.config, reserved)
        except SpaceExhausted:
            for item in self.db.execute("SELECT * FROM attachments WHERE status='retained'").fetchall():
                self._evict(item)
                # Preflight runs before any core mutation. Filesystem deletion
                # cannot roll back: preserve its metadata even if capacity is
                # still insufficient and this operation must raise below.
                self.db.commit()
                try:
                    require_space(self.root, self.config, reserved)
                    return
                except SpaceExhausted:
                    pass
            require_space(self.root, self.config, reserved)

    def _op_attach(self, receipt, token, role, error_type=None):
        import tarfile
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Attachment retention requires durable acknowledgement')
        if role not in ('initial', 'best', 'failure'):
            raise ValueError('Unknown attachment retention role')
        workspace_row = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if workspace_row is None or workspace_row['eval_id'] != row['id']:
            raise ValueError('Workspace/evaluation mismatch')
        workspace = unpack(workspace_row['data'])
        path = checked_workspace(workspace)
        size = disk_bytes(path)
        existing = self.db.execute("SELECT * FROM attachments WHERE run_id=? AND status='retained'", (row['run_id'],)).fetchall()
        same = [a for a in existing if a['role'] == role]
        reason = 'workspace_missing_after_cleanup_or_recovery' if not path.exists() else None
        if role == 'initial' and same:
            reason = 'initial_already_retained'
        if role == 'failure' and (len(same) >= 2 or any(a['error_type'] == error_type for a in same)):
            reason = 'representative_failure_limit'
        # Conservative bound for tar headers; compressed bytes checked again below.
        reserve = size + 10240 + sum(1024 for _ in path.rglob('*'))
        reclaim = sum(a['bytes'] for a in same) if role == 'best' else 0
        if reserve + sum(a['bytes'] for a in existing) - reclaim > self.config.attachment_budget:
            reason = 'attachment_byte_budget'
        key = uuid4().hex
        destination = self.root / 'attachments' / (key + '.tar.gz')
        if reason is None:
            try:
                self._op_preflight(extra=reserve)
            except SpaceExhausted:
                reason = 'space_reserve'
        if reason is None:
            temporary = destination.with_suffix('.tmp')
            with tarfile.open(temporary, 'w:gz') as archive:
                archive.add(path, arcname='job')
            with temporary.open('rb') as stream:
                import os
                os.fsync(stream.fileno())
            if temporary.stat().st_size > self.config.attachment_budget:
                temporary.unlink()
                reason = 'compressed_attachment_byte_budget'
            else:
                temporary.replace(destination)
                fsync_directory(destination.parent)
                if role == 'best':
                    for item in same:
                        self._evict(item)
        self.db.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?,?,?)',
                        (key, row['run_id'], row['id'], role, error_type,
                         str(destination) if reason is None else None,
                         destination.stat().st_size if reason is None else 0,
                         'retained' if reason is None else 'omitted', reason))
        return key

    def _op_checkpoint(self, run_id, path, kind, step, data):
        path = Path(path).resolve()
        if path.parent != self.root / 'checkpoints' or not path.is_file() or path.is_symlink():
            raise ValueError('Checkpoint must be atomically published inside checkpoint directory')
        key = path.name
        self.db.execute('INSERT INTO checkpoints VALUES(?,?,?,?,?,?,?)',
                        (key, run_id, str(path), kind, step, pack(data), 'retained'))
        keep = 2 if kind == 'full' else 1
        rows = self.db.execute("SELECT * FROM checkpoints WHERE run_id=? AND kind=? AND status='retained' ORDER BY step DESC,rowid DESC",
                               (run_id, kind)).fetchall()
        for item in rows[keep:]:
            old = Path(item['path'])
            if old.parent != self.root / 'checkpoints' or old.is_symlink():
                raise ValueError('Checkpoint escaped directory')
            old.unlink(missing_ok=True)
            self.db.execute("UPDATE checkpoints SET status='evicted' WHERE id=?", (item['id'],))
        return key

    def _op_update_summary(self, run_id, first, last, values):
        self.db.execute('INSERT OR REPLACE INTO updates VALUES(?,?,?,?)', (run_id, first, last, pack(values)))


class StoreManager(BaseManager):
    pass


StoreManager.register('ExperimentStore', ExperimentStore, exposed=('call', 'close'))


def start_service(root, config=None):
    """Return manager + picklable proxy; parent must close store then shutdown manager."""
    import multiprocessing
    import tempfile
    # Local IPC only: never expose a TCP writer or permit machines to share SQLite.
    address = str(Path(tempfile.gettempdir()) / ('gator-writer-' + uuid4().hex + '.sock'))
    manager = StoreManager(address=address, ctx=multiprocessing.get_context('spawn'))
    manager.start()
    try:
        return manager, manager.ExperimentStore(str(root), config)
    except BaseException:
        manager.shutdown()
        raise
