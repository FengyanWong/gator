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
from multiprocessing.managers import BaseManager
from pathlib import Path
import queue
import sqlite3
import threading
import time
from uuid import uuid4

from .codec import VERSION, identity, pack, unpack
from .space import RecordingConfig, filesystem
from .store_evaluations import EvaluationRecords
from .store_states import StateRecords
from .store_summary import RunSummary
from .store_workspaces import WorkspaceRecords

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
CREATE TABLE IF NOT EXISTS simulation_jobs(eval_id TEXT NOT NULL REFERENCES evaluations(id),
  job_index INTEGER NOT NULL, state TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY(eval_id,job_index));
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


class ExperimentStore(EvaluationRecords, StateRecords, RunSummary, WorkspaceRecords):
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
                    reward_version='constraint_violation_v2', tolerance=0.0,
                    configuration=configuration or {})
        return self._op_asset('task', task), graph_id

    def _op_position(self):
        return dict(database_id=self.db.execute("SELECT value FROM meta WHERE key='database_id'").fetchone()[0],
                    evaluation_seq=self.db.execute('SELECT coalesce(max(seq),0) FROM evaluations WHERE result IS NOT NULL').fetchone()[0],
                    transition_seq=self.db.execute('SELECT coalesce(max(seq),0) FROM transitions').fetchone()[0])

    def _op_configuration(self):
        return dict(vars(self.config))

    def _op_recording_root(self):
        return str(self.root)

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
