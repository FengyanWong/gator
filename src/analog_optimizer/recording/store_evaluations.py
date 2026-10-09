"""An evaluation's life in the recording database: its registration, dispatch, simulation launch intents and
results, finished result and receipt, and recovery of the ones left pending.

One of the parts ExperimentStore (store.py) is made of since 2026-10-09 (plan-refactoring E5); its methods run on
the store's writer thread, inside the transaction of the operation that called them."""
from copy import deepcopy
import math
import time
from uuid import uuid4

from .codec import identity, pack, unpack


class EvaluationRecords:
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

    def _op_launch_intent(self, eval_id, intent):
        self._evaluation(eval_id)
        key = (eval_id, intent['index'])
        old = self.db.execute('SELECT data FROM simulation_jobs WHERE eval_id=? AND job_index=?', key).fetchone()
        if old is not None:
            if unpack(old[0]) != intent:
                raise ValueError('Conflicting simulation launch intent')
            return
        if intent['state'] != 'launch_intent' or intent['uncertain_calls'] not in (0, 1):
            raise ValueError('A physical launch must first record an uncertain intent (a synthetic call records none)')
        self.db.execute('INSERT INTO simulation_jobs VALUES(?,?,?,?)', (*key, 'launch_intent', pack(intent)))

    def _op_launch_result(self, eval_id, result):
        key = (eval_id, result['index'])
        old = self.db.execute('SELECT data FROM simulation_jobs WHERE eval_id=? AND job_index=?', key).fetchone()
        if old is None:
            raise ValueError('Cannot complete a simulation without a durable intent')
        intent = unpack(old[0])
        for name in ('export_job_id', 'condition', 'netlist_sha256', 'netlist_path'):
            if intent[name] != result[name]:
                raise ValueError('Simulation result identity differs from launch intent')
        if intent['state'] == 'completed' and intent != result:
            raise ValueError('Conflicting simulation result')
        self.db.execute('UPDATE simulation_jobs SET state=?,data=? WHERE eval_id=? AND job_index=?',
                        ('completed', pack(result), *key))

    def _op_simulation_jobs(self, eval_id):
        return [unpack(row[0]) for row in self.db.execute(
            'SELECT data FROM simulation_jobs WHERE eval_id=? ORDER BY job_index', (eval_id,))]

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

    def _op_verify_receipt(self, receipt):
        row = self.db.execute('SELECT id,result_hash FROM evaluations WHERE id=?', (receipt['eval_id'],)).fetchone()
        if row is None or row['result_hash'] is None or receipt != self._receipt(row):
            raise ValueError('Expected durable acknowledgement of this evaluation')
        return True
