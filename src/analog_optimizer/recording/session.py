"""Opt-in recording hooks for existing environments, without changing rewards."""
from collections import OrderedDict
from dataclasses import dataclass, field

from .codec import identity
from analog_optimizer.backends.common import parameter_rows
from analog_optimizer.measurements.specs import REWARD_VERSION, RewardSettings


@dataclass
class RunRecorder:
    store: object
    run_id: str
    worker_id: str = '0'
    task_id: str | None = None
    graph_id: str | None = None
    phase: str = 'training'
    policy_version: int | str | None = None
    last_eval_id: str | None = field(default=None, init=False)
    _asset_ids: OrderedDict = field(default_factory=OrderedDict, init=False, repr=False)

    def _asset(self, kind, value):
        key = identity((kind, value))
        if key not in self._asset_ids:
            self._asset_ids[key] = self.store.call('asset', kind, value)
            if len(self._asset_ids) > 32:
                self._asset_ids.popitem(last=False)
        self._asset_ids.move_to_end(key)
        return self._asset_ids[key]

    def bind(self, graph, specs, configuration):
        self._asset_ids.clear()
        self.task_id, self.graph_id = self.store.call('task', graph, tuple(specs), configuration)

    def begin(self, record):
        self.last_eval_id = record['candidate_id']
        condition_id = self._asset('condition', record['condition'])
        condition = record['condition']
        return self.store.call('begin_workspace', self.run_id, self.task_id, self.graph_id,
                        dict(parent_step_id=record['candidate_id'] if record['kind'] == 'step' else None,
                             worker_id=self.worker_id, episode_id=record['episode'], step=record['step'],
                             phase='initial' if record['kind'] == 'reset' else self.phase,
                             source='spectre' if record['origin'] == 'real' else 'mock',
                             condition_id=condition_id,
                             corner_id=None if condition is None else condition['corner']['id'],
                             requested_parameters=record['requested_parameters']), eval_id=record['candidate_id'])

    def start(self, eval_id, parameters, record):
        return self.store.call('start', eval_id, parameters,
                               dict(netlist_sha256=record['netlist_sha256'], job_id=record['export_job_id']))

    def launch_intent(self, eval_id, intent):
        return self.store.call('launch_intent', eval_id, intent)

    def launch_result(self, eval_id, result):
        return self.store.call('launch_result', eval_id, result)

    def finish(self, record, result, observation, previous, action, operating_points=None):
        # These fields already have authoritative result/request/condition entries.
        # Keep diagnostics, projection details and timings, not a second raw result.
        repeated = {'observation', 'metrics', 'metric_units', 'metric_validity',
                    'applied_parameters', 'requested_parameters', 'condition'}
        environment = {k: v for k, v in record.items() if k not in repeated}
        environment['format'] = 'diagnostics-v2'
        environment.pop('error', None)  # One bounded error summary, never a duplicate long log.
        if result is None:
            status = 'cancelled' if record.get('exception_type') in ('KeyboardInterrupt', 'CancelledError') else 'execution_error'
            data = dict(status=status, error_class=record.get('exception_type'),
                        error_summary=record.get('error', ''), metrics={}, metric_validity={}, metric_units={},
                        applied_parameters=record.get('applied_parameters'), simulator_invocations=0,
                        invocation_uncertain=record['origin'] == 'real' and record.get('simulation_dispatched', False))
        else:
            data = dict(status=result.status.value, error_class=result.reason_code,
                        error_summary=getattr(result, 'error_summary', ''), metrics=dict(result.metrics),
                        metric_validity=dict(result.metric_validity), metric_units=dict(result.metric_units),
                        applied_parameters=result.applied_parameters, backend_kind=result.backend_kind,
                        origin=result.origin, candidate_evaluated=result.candidate_evaluated,
                        retryable=result.retryable, operating_points=operating_points,
                        simulator_version_asset_id=self._asset('simulator_version',
                            dict(version=result.simulator_version, status='available' if result.simulator_version else 'unavailable')),
                        simulator_invocations=getattr(result, 'simulator_invocations', None),
                        sample_id=result.sample_index)
            if data['simulator_invocations'] is None:
                # Backend calls are dispatch attempts; the existing adapter can fail before exec.
                data['simulator_invocations'] = int(result.origin == 'real' and result.candidate_evaluated)
                data['invocation_uncertain'] = result.origin == 'real' and not result.candidate_evaluated
            if record['state'] == 'execution_error':
                data.update(underlying_status=data['status'], status='execution_error',
                            error_class=record.get('exception_type'), error_summary=record.get('error', ''))
        data.update(environment=environment, elapsed_seconds=record['elapsed_seconds'])
        if record.get('jobs'):
            data['simulator_invocations'] = sum(job.get('confirmed_calls', 0) for job in record['jobs'])
            data['unconfirmed_invocations'] = sum(job.get('uncertain_calls', 0) for job in record['jobs'])
            data['invocation_uncertain'] = bool(data['unconfirmed_invocations'])
        transition = None
        if action is not None:
            transition = dict(observation=previous, next_observation=observation, proposal=dict(action.proposal),
                              reward=record.get('reward'), terminated=record.get('terminated', False),
                              truncated=record.get('truncated', True), bootstrap=record.get('bootstrap', False),
                              applied_parameters=(dict(sorted(data['applied_parameters'].items()))
                                                  if isinstance(data['applied_parameters'], dict) else data['applied_parameters']),
                              candidate_id=record['candidate_id'],
                              record_path=f"sqlite:{self.run_id}/{record['candidate_id']}",
                              action_version='absolute-group-v1', reward_version=REWARD_VERSION,
                              reward_settings=observation.reward_settings if observation is not None else RewardSettings(**record['reward_settings']),
                              reward_components=dict(violations=record.get('violations'), evaluation_errors=record.get('evaluation_errors')),
                              replay_eligible=record.get('replay_eligible', False),
                              episode=record['episode'], step=record['step'], worker_id=self.worker_id,
                              policy_version=self.policy_version, phase=self.phase,
                              action_mask={key: True for key in action.proposal},
                              observation_contract='Observation fields + exact graph patches; fixed physical normalizer')
        return self.store.call('finish', record['candidate_id'], data, observation=observation, transition=transition)

    def retain_and_clean(self, receipt, workspace, backend):
        # Remote copies must pass their own ownership/process checks before local removal.
        if hasattr(backend, 'finish_recording'):
            backend.finish_recording(receipt)
        self.store.call('finalize_workspace', receipt, workspace['token'])


def transition_from_store(store, transition_id):
    return transition_from_data(store.call('read', 'transition', transition_id))


def evaluation_record(store, eval_id):
    """Reconstruct the environment journal view used by existing evaluators."""
    row = store.call('read', 'evaluation', eval_id)
    result = row['result']
    if result is None:
        raise ValueError('Evaluation has no durable result')
    record = dict(result.get('environment', {}))
    record.update(candidate_id=eval_id, status=result['status'],
                  **{key: result.get(key) for key in ('metrics', 'metric_units', 'metric_validity', 'applied_parameters')})
    if isinstance(record['applied_parameters'], dict):
        record['applied_parameters'] = parameter_rows(record['applied_parameters'])
    return record


def transition_from_data(data, *, validate=True):
    from analog_optimizer.training.replay import Transition
    from dataclasses import fields
    if not data['replay_eligible']:
        raise ValueError('Recorded transition is ineligible for training replay')
    transition = Transition(**{f.name: data[f.name] for f in fields(Transition)})
    if validate:
        transition.validate()
        expected = data.get('replay_fingerprint')
        if expected is not None and expected != transition.fingerprint():
            raise ValueError('Stored replay fingerprint does not match reconstructed transition')
    return transition


class UpdateAggregator:
    def __init__(self, store, run_id, interval=100):
        self.store, self.run_id, self.interval = store, run_id, interval
        self.rows = []

    def add(self, values):
        # Scalar diagnostics only. No gradients, activations, embeddings or model copies.
        self.rows.append({k: v for k, v in values.items() if type(v) in (int, float)})
        if len(self.rows) >= self.interval:
            self.flush()

    def flush(self):
        if not self.rows:
            return
        values = {k: dict(count=len(v), mean=sum(v) / len(v), minimum=min(v), maximum=max(v))
                  for k in self.rows[0] if k != 'updates'
                  for v in [[row[k] for row in self.rows if k in row]]}
        self.store.call('update_summary', self.run_id, self.rows[0]['updates'], self.rows[-1]['updates'], values)
        self.rows.clear()
