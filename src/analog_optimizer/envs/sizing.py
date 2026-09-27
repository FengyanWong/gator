from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
from time import perf_counter
from uuid import uuid4

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus, UnsupportedCapability
from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.graph.circuit_graph import CircuitGraph
from analog_optimizer.measurements.specs import REWARD_VERSION, CLEARANCE_RULE, MetricSpec, RewardSettings, SpecificationEvaluator
from analog_optimizer.parameters.actions import ActionMapper


def write_record(path, value):
    """Atomic journal replacement; pending records survive failed operations."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False, default=str)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def parameter_rows(parameters):
    return [{'device': d, 'parameter': p, 'value': v} for (d, p), v in sorted(parameters.items())]


def same_parameters(actual, expected):
    return actual.keys() == expected.keys() and all(
        math.isfinite(actual[k]) and math.isclose(actual[k], v, rel_tol=1e-8, abs_tol=1e-24)
        for k, v in expected.items())


def graph_contract(graph):
    groups = []
    for group in graph.parameter_groups:
        record = asdict(group)
        if group.mutable:
            record.pop('value')
        groups.append(record)
    return {
        'schema': graph.schema_version,
        'devices': sorted((d.id, d.kind, d.model_ref, d.terminals) for d in graph.devices),
        'nets': sorted((n.id, n.roles) for n in graph.nets),
        'connections': sorted((c.device_id, c.net_id, c.terminal, c.ordinal, c.role) for c in graph.connections),
        'groups': groups,
    }


@dataclass(frozen=True)
class ConditionResult:
    condition: SimulationCondition | None
    status: str
    candidate_evaluated: bool
    metrics: dict[str, float | None]
    metric_units: dict[str, str]
    metric_validity: dict[str, bool]
    job_id: str
    reason_code: str
    operating_points: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.condition is not None and not isinstance(self.condition, SimulationCondition):
            raise ValueError('Typed result condition is required')
        if type(self.candidate_evaluated) is not bool or not self.job_id or not self.reason_code:
            raise ValueError('Condition result requires attribution and job/reason identity')
        if self.status not in {s.value for s in SimulationStatus}:
            raise ValueError('Unknown condition status')
        for key in ('metrics', 'metric_units', 'metric_validity', 'operating_points'):
            object.__setattr__(self, key, deepcopy(getattr(self, key)))


def mapped_operating_points(graph, raw):
    """Exact hierarchical name mapping, with no device-name inference or imputation."""
    names = {device.id.replace('/', '.'): device.id for device in graph.devices}
    if len(names) != len(graph.devices):
        raise ValueError('Ambiguous measurement-to-graph device mapping')
    mapped, unmatched = {}, []
    for name, quantities in (raw or {}).items():
        if name not in names:
            unmatched.append(name)
            continue
        if not isinstance(quantities, dict):
            continue
        mapped[names[name]] = {key: float(value) for key, value in quantities.items()
                               if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)}
    return mapped, tuple(sorted(unmatched))


@dataclass(frozen=True)
class Observation:
    graph: CircuitGraph
    specs: tuple[MetricSpec, ...]
    metrics: dict[str, float | None]
    metric_validity: dict[str, bool]
    metric_units: dict[str, str]
    status: str
    origin: str
    remaining_steps: int
    job_id: str
    condition: SimulationCondition | None = None
    condition_results: tuple[ConditionResult, ...] = ()
    planned_conditions: tuple[SimulationCondition | None, ...] = ()
    condition_policy: str = 'off'
    reward_settings: RewardSettings = field(default_factory=RewardSettings)
    operating_points: dict = field(default_factory=dict)
    unmatched_operating_points: tuple[str, ...] = ()

    @property
    def evaluation(self):
        evaluator = SpecificationEvaluator(self.specs, self.reward_settings)
        if self.condition_results:
            return evaluator.evaluate_conditions(self.condition_results, planned_conditions=self.planned_conditions)
        return evaluator.evaluate(self.metrics, self.metric_units, self.metric_validity)


class CircuitSizingEnv:
    """reset() -> (observation, info); step() -> (obs, reward, terminated, truncated, info).

    The step budget is part of the finite-horizon task and of each observation;
    exhaustion terminates with bootstrap=False. Infrastructure/measurement errors
    truncate, reward=None and replay_eligible=False. Attributed circuit failures
    terminate in compatibility mode; robust mode can continue from a masked state.
    No automatic retries or result cache: duplicates are logged and simulated.
    This is a plain Python environment, not a Gymnasium Env implementation.
    Use as a context manager; it owns and restores its backend connection.
    """

    def __init__(self, backend, graph, specs, work_root, *, max_steps=5,
                 timeout_seconds=120.0, stop_on_success=True, expected_origin='real',
                 condition: SimulationCondition | None = None, recorder=None, reward_settings=None,
                 condition_policy='off', corners=()):
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be positive and finite')
        if expected_origin not in ('real', 'synthetic'):
            raise ValueError('Explicit real or synthetic origin required')
        if not isinstance(stop_on_success, bool):
            raise ValueError('stop_on_success must be a boolean')
        self.condition = condition if condition is not None else backend.nominal_condition()
        # The graph and operating-point input always describe the nominal job.
        if self.condition is not None and not self.condition.nominal_only:
            raise ValueError('The primary condition must be nominal (the environment is nominal-only apart from its explicit '
                             'training-corner plan)')
        if self.condition is None and expected_origin == 'real':
            raise ValueError('A real environment needs an explicit nominal condition')
        backend.validate_condition(self.condition)
        self.condition_policy = condition_policy
        corners = tuple(corners)
        if condition_policy not in ('off', 'always') or (condition_policy == 'off' and corners):
            raise ValueError('Training conditions require off or always policy')
        if condition_policy == 'always' and (not corners or expected_origin != 'real'):
            raise ValueError('Robust training requires an explicit real corner plan')
        for corner in corners:
            if not isinstance(corner, SimulationCondition) or corner.purpose != 'pvt_training':
                raise ValueError('Corners must have the explicit pvt_training purpose')
            backend.validate_condition(corner)
        self.planned_conditions = (self.condition,) + corners
        if len(set(self.planned_conditions)) != len(self.planned_conditions):
            raise ValueError('Duplicate planned conditions')
        ids = [c.corner.id if c is not None else 'nominal' for c in self.planned_conditions]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate planned corner identity')
        self._launch_allowance, self._stop_file = None, None
        self.backend = backend
        self.recorder = recorder
        self._recording_observation = None
        self._reference_graph = deepcopy(graph)
        self.mapper = ActionMapper(graph)
        self.evaluator = SpecificationEvaluator(specs, reward_settings)
        self.max_steps, self.timeout_seconds = max_steps, timeout_seconds
        self.stop_on_success, self.expected_origin = stop_on_success, expected_origin
        self._contract = graph_contract(graph)
        self._connected, self._closed, self._done = False, False, True
        self._initial = None
        self._seen = {}
        self.steps, self.simulation_calls, self.episode = 0, 0, 0
        self.candidate_evaluations, self.confirmed_calls, self.uncertain_calls = 0, 0, 0
        if recorder is not None:
            from analog_optimizer.recording.space import RecordingConfig, require_filesystem_space
            require_filesystem_space(work_root, RecordingConfig(**recorder.store.call('configuration')))
        self.directory = Path(work_root).resolve() / uuid4().hex
        self.directory.mkdir(parents=True, exist_ok=False)
        if recorder is None:
            (self.directory / 'candidates').mkdir()
        config = {'schema_version': 'sizing-env-v3', 'action_version': 'absolute-group-v1',
                  'condition': None if self.condition is None else asdict(self.condition),
                  'evaluation_purpose': 'nominal',
                  'origin': expected_origin, 'max_steps': max_steps, 'timeout_seconds': timeout_seconds,
                  'stop_on_success': stop_on_success, 'specs': [asdict(s) for s in self.evaluator.specs],
                  'initial_graph': asdict(graph), 'cache_enabled': False, 'automatic_retries': 0,
                  'reward': REWARD_VERSION, 'reward_settings': asdict(self.evaluator.settings),
                  'clearance_rule': CLEARANCE_RULE, 'condition_policy': self.condition_policy,
                  'failure_policy': 'continue_attributed' if condition_policy == 'always' else 'nominal_terminate',
                  'planned_conditions': [None if c is None else asdict(c) for c in self.planned_conditions],
                  'budget_semantics': 'finite_horizon_termination',
                  'critic_action_semantics': 'normalized_proposal'}
        self.config_sha256 = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        if recorder is None:
            write_record(self.directory / 'config.json', {**config, 'sha256': self.config_sha256})
        else:
            recorder.bind(graph, self.evaluator.specs,
                          {k: v for k, v in config.items() if k not in ('initial_graph', 'specs')})

    def __enter__(self):
        if self._closed or self._connected:
            raise RuntimeError('Environment context cannot be reused or nested')
        self._thread = threading.get_ident()
        try:
            self.backend.connect()
            self._connected = True
            self._initial = dict(self.backend.read_parameters())
            expected = self._reference_graph.assignments({g.id: g.value for g in self.mapper.groups})
            if not same_parameters(self._initial, expected):
                raise ValueError('Initial backend parameters differ from the reference graph')
        except BaseException as original:
            try:
                self.close()
            except BaseException as cleanup:
                original.cleanup_error = f'{type(cleanup).__name__}: {cleanup}'
            raise
        return self

    def _require_connection(self):
        if not self._connected or self._closed:
            raise RuntimeError('Use the environment inside its context manager')
        if threading.get_ident() != self._thread:
            raise RuntimeError('Environment supports only its owning worker thread')

    def reset(self):
        self._require_connection()
        self.steps = 0
        self.episode += 1
        self._done = True
        observation, _, _, _, info = self._evaluate(None, reset=True)
        return observation, info

    def step(self, proposal):
        self._require_connection()
        if self._done:
            raise RuntimeError('Call reset() before step(), or after an episode ends')
        action = self.mapper.legalize(proposal)  # Bad input consumes no budget and performs no I/O.
        self.steps += 1
        return self._evaluate(action, reset=False)

    def authorize_launches(self, allowance, *, stop_file=None):
        if type(allowance) is not int or allowance < 0:
            raise ValueError('A finite nonnegative reserved launch allowance is required')
        self._launch_allowance = allowance
        self._stop_file = None if stop_file is None else Path(stop_file)

    def _evaluate(self, action, *, reset):
        cost = 1 if reset else len(self.planned_conditions)
        allowance = self._launch_allowance
        self._launch_allowance = None
        if allowance is None:
            if self.condition_policy == 'always':
                raise ValueError('Robust execution requires a coordinator reservation before candidate preparation')
            allowance = 1
        if allowance < cost:
            raise ValueError('Reserved launch allowance does not cover the complete candidate plan')
        self.candidate_evaluations += 1
        started = perf_counter()
        candidate_id = uuid4().hex
        path = self.directory / 'candidates' / f'{candidate_id}.json'
        expected = self._initial if reset else action.assignments
        key = tuple(sorted(expected.items()))
        record = {'candidate_id': candidate_id, 'episode': self.episode, 'step': self.steps,
                  'kind': 'reset' if reset else 'step', 'state': 'pending',
                  'started_at': datetime.now(timezone.utc).isoformat(),
                  'config_sha256': self.config_sha256, 'origin': self.expected_origin,
                  'evaluation_purpose': 'nominal',
                  'condition': None if self.condition is None else asdict(self.condition),
                  'proposal': None if reset else action.proposal,
                  'group_values': None if reset else action.group_values,
                  'projected_groups': [] if reset else action.projected_groups,
                  'requested_parameters': parameter_rows(expected), 'applied_parameters': None,
                  'duplicate_of': self._seen.get(key), 'cache_hit': False,
                  'simulation_calls': self.simulation_calls, 'replay_eligible': False,
                  'candidate_evaluations': self.candidate_evaluations,
                  'reward_version': REWARD_VERSION, 'reward_settings': asdict(self.evaluator.settings),
                  'clearance_rule': CLEARANCE_RULE, 'condition_policy': self.condition_policy,
                  'planned_conditions': [None if c is None else asdict(c) for c in self.planned_conditions],
                  'condition_results': [], 'jobs': [], 'reserved_launches': allowance,
                  'timings': {}}
        workspace, result, committed, finalizing = None, None, False, False
        if self.recorder is None:
            write_record(path, record)  # Before restoration or the first candidate mutation.
            output_root = self.directory
        else:
            from analog_optimizer.recording.space import RecordingConfig, require_filesystem_space
            require_filesystem_space(self.directory, RecordingConfig(**self.recorder.store.call('configuration')))
            workspace = self.recorder.begin(record)
            output_root = Path(workspace['path'])
            path = f"sqlite:{self.recorder.run_id}/{candidate_id}"
        self._done = True
        try:
            if self.recorder is not None and hasattr(self.backend, 'prepare_recording'):
                self.backend.prepare_recording(self.recorder, candidate_id)
            stage = perf_counter()
            prepare = getattr(self.backend, 'prepare_candidate', None)
            if callable(prepare):
                artifact, applied = prepare(output_root / 'exports', dict(expected),
                    condition=self.condition, candidate_id=candidate_id)
                record['timings']['candidate_preparation'] = perf_counter() - stage
                record['timings']['queue_wait'] = self.backend.timings.get('queue_wait', 0.)
                record['timings']['parameter_update_readback'] = self.backend.timings.get('parameter_update', 0.)
            else:
                if reset:
                    self.backend.restore()
                else:
                    self.backend.set_parameters(dict(expected))
                applied = self.backend.read_parameters()
                record['applied_parameters'] = parameter_rows(applied)
                if not same_parameters(applied, expected):
                    raise ValueError('Parameter readback differs from requested candidate')
                record['timings']['parameter_update_readback'] = perf_counter() - stage
                stage = perf_counter()
                kwargs = {} if self.condition is None else {'condition': self.condition}
                artifact = self.backend.generate_netlist(output_root / 'exports', **kwargs)
            record['applied_parameters'] = parameter_rows(applied)
            if not same_parameters(applied, expected):
                raise ValueError('Parameter readback differs from requested candidate')
            key = tuple(sorted(applied.items()))
            record['duplicate_of'] = self._seen.get(key)
            record.update(export_job_id=artifact.job_id, netlist_sha256=artifact.sha256,
                          netlist_path=str(artifact.path))
            if artifact.origin != self.expected_origin:
                raise ValueError('Unexpected netlist origin')
            if artifact.condition != self.condition:
                raise ValueError('Exported condition differs from the nominal environment')
            record['timings']['netlisting'] = (self.backend.timings.get('netlisting', 0.)
                                                if callable(prepare) else perf_counter() - stage)
            stage = perf_counter()
            graph = self.backend.get_circuit_graph(artifact)
            graph.validate()
            if graph_contract(graph) != self._contract:
                raise ValueError('Exported graph changed topology or action contract')
            graph_values = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
            if not same_parameters(graph_values, applied):
                raise ValueError('Exported graph differs from parameter readback')
            record['timings']['graph_build'] = perf_counter() - stage
            rows, results, stopped = [], [], False
            planned_now = self.planned_conditions[:1] if reset else self.planned_conditions
            simulation_started = perf_counter()
            if self.recorder is not None:
                self.recorder.start(candidate_id, dict(applied), record)
            for index, condition in enumerate(planned_now):
                if self._stop_file is not None and self._stop_file.exists():
                    stopped = True
                    record['conditions_stop_reason'] = 'coordinator_stop'
                    break
                if allowance < 1:
                    raise RuntimeError('Launch allowance exhausted before physical invocation')
                current = artifact if index == 0 else self.backend.derive_condition_artifact(
                    artifact, output_root / 'exports', condition=condition)
                if current.condition != condition or current.origin != self.expected_origin:
                    raise ValueError('Derived artifact condition/origin mismatch')
                pending = int(self.expected_origin == 'real')     # only a real launch can be left unresolved
                intent = dict(index=index, state='launch_intent', export_job_id=current.job_id,
                              started_at=datetime.now(timezone.utc).isoformat(),
                              condition=None if condition is None else asdict(condition), netlist_sha256=current.sha256,
                              netlist_path=str(current.path), confirmed_calls=0, uncertain_calls=pending)
                record['jobs'].append(intent)
                allowance -= 1
                self.simulation_calls += 1
                self.uncertain_calls += pending
                record.update(state='simulation_started', simulation_calls=self.simulation_calls,
                              simulation_dispatched=True)
                # The per-job intent survives a process loss, including before a result exists.
                write_record(output_root / f'launch-{candidate_id}-{index}.json', intent)
                if self.recorder is None:
                    write_record(path, record)
                elif hasattr(self.recorder, 'launch_intent'):
                    self.recorder.launch_intent(candidate_id, intent)
                required = tuple(s.metric_id for s in self.evaluator.specs if s.active and s.required
                                 and (index == 0 or not s.nominal_only))
                result = self.backend.run_simulation(SimulationRequest(
                    current, output_root / 'simulations', required,
                    self.timeout_seconds, dict(applied), condition=condition))
                if result.origin != self.expected_origin or not same_parameters(result.applied_parameters, applied):
                    raise ValueError('Simulation result origin or parameters differ from the export')
                if result.condition != condition or result.sample_index is not None:
                    raise ValueError('Result condition differs from the launched artifact; it cannot enter nominal replay')
                invocations = result.simulator_invocations
                if invocations is None and result.origin != 'real':
                    # A synthetic backend launches no simulator: its call is complete and never an uncertain
                    # launch (the recorder's convention: zero real invocations for a synthetic result).
                    invocations = 0
                if invocations is not None and (type(invocations) is not int or not 0 <= invocations <= 1):
                    raise ValueError('A condition job must report zero or one invocation, or explicit uncertainty')
                if invocations is not None:
                    self.uncertain_calls -= pending
                    self.confirmed_calls += invocations
                    if result.origin == 'real':
                        self.simulation_calls += invocations - 1   # a real job that never launched costs no call
                intent.update(state='completed', job_id=result.job_id, artifact_directory=str(result.artifact_directory),
                              ended_at=datetime.now(timezone.utc).isoformat(), simulator_version=result.simulator_version,
                              status=result.status.value, reason_code=result.reason_code,
                              elapsed_seconds=result.elapsed_seconds, simulator_invocations=invocations,
                              confirmed_calls=invocations or 0, uncertain_calls=int(invocations is None),
                              candidate_evaluated=result.candidate_evaluated)
                write_record(output_root / f'launch-{candidate_id}-{index}.json', intent)
                if self.recorder is not None and hasattr(self.recorder, 'launch_result'):
                    self.recorder.launch_result(candidate_id, intent)
                names = set(result.metrics) | set(self.evaluator.required_metrics)
                metrics, validity = {}, {}
                for name in names:
                    value = result.metrics.get(name)
                    valid = (result.status == SimulationStatus.OK and result.candidate_evaluated
                             and result.metric_validity.get(name) is True
                             and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))
                    metrics[name], validity[name] = (float(value) if valid else None), valid
                local = self.evaluator.evaluate(metrics, result.metric_units, validity)
                for name in local.errors:
                    metrics[name], validity[name] = None, False
                operating_points = result.operating_points
                if operating_points is None and result.status == SimulationStatus.OK:
                    try:
                        operating_points = self.backend.get_operating_points()
                    except UnsupportedCapability:
                        pass
                row = ConditionResult(condition, result.status.value, result.candidate_evaluated,
                                      metrics, dict(result.metric_units), validity, result.job_id,
                                      result.reason_code, {key: {name: float(value) for name, value in values.items()
                                          if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)}
                                          for key, values in (operating_points or {}).items() if isinstance(values, dict)})
                rows.append(row)
                results.append(result)
                record['condition_results'] = [asdict(r) for r in rows]
                if self.recorder is None:
                    write_record(path, record)
                attributed = result.candidate_evaluated and result.status in (SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED)
                required_valid = self.evaluator.evaluate_conditions(rows).valid
                if invocations is None or (not attributed and (result.status != SimulationStatus.OK or not required_valid)):
                    stopped = True
                    record['conditions_stop_reason'] = 'unavailable_or_uncertain_condition'
                    break
                if index == 0 and attributed:
                    record['conditions_stop_reason'] = 'attributed_nominal_failure'
                    break
            record['timings']['simulation_and_measurement'] = perf_counter() - simulation_started
            if not rows:
                raise RuntimeError('Candidate stopped before nominal evaluation')
            result = results[0]
            record.update(job_id=result.job_id, artifact_directory=str(result.artifact_directory),
                          status=result.status.value, reason_code=result.reason_code,
                          candidate_evaluated=result.candidate_evaluated, retryable=result.retryable,
                          backend_kind=result.backend_kind)
            self._seen.setdefault(key, candidate_id)
            metrics, validity = rows[0].metrics, rows[0].metric_validity
            evaluated = self.evaluator.evaluate_conditions(rows, planned_conditions=self.planned_conditions)
            operating_points, unmatched = mapped_operating_points(graph, rows[0].operating_points)
            observation = Observation(deepcopy(graph), self.evaluator.specs, metrics, validity,
                                      dict(result.metric_units), result.status.value, result.origin,
                                      self.max_steps - self.steps, result.job_id, self.condition,
                                      tuple(rows), self.planned_conditions, self.condition_policy, self.evaluator.settings,
                                      operating_points, unmatched)
            reward, eligible, success, terminated, truncated = None, False, False, False, False
            if self.condition_policy == 'always' and evaluated.valid and not stopped:
                reward, eligible, success = evaluated.reward, not reset, evaluated.success
                terminated = (success and self.stop_on_success) or self.steps >= self.max_steps
            elif not stopped and result.status == SimulationStatus.OK and result.candidate_evaluated and evaluated.valid:
                reward, eligible, success = evaluated.reward, not reset, evaluated.success
                terminated = (success and self.stop_on_success) or self.steps >= self.max_steps
            elif not stopped and result.status in (SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED) and result.candidate_evaluated:
                reward, eligible, terminated = -1.0, not reset, True
            else:
                truncated = True
                if result.status != SimulationStatus.MEASUREMENT_ERROR and result.status != SimulationStatus.OK:
                    observation = None  # Do not fabricate a usable next state for infrastructure failure.
            self._done = terminated or truncated
            info = {'candidate_id': candidate_id, 'record_path': str(path), 'status': result.status.value,
                    'success': success, 'evaluation_valid': evaluated.valid,
                    'evaluation_errors': evaluated.errors, 'violations': evaluated.violations,
                    'replay_eligible': eligible, 'bootstrap': eligible and not terminated and not truncated,
                    'terminated': terminated, 'truncated': truncated,
                    'duplicate_of': record['duplicate_of'], 'cache_hit': False,
                    'simulation_calls': self.simulation_calls, 'job_id': result.job_id}
            info.update(candidate_evaluations=self.candidate_evaluations, confirmed_calls=self.confirmed_calls,
                        uncertain_calls=self.uncertain_calls, conditions_complete=evaluated.complete,
                        nominal_success=evaluated.nominal_success, robust_success=success and evaluated.complete,
                        conditions_evaluated=len(rows), conditions_planned=len(self.planned_conditions),
                        margins=evaluated.margins, clearance_margin=evaluated.clearance_margin,
                        tightest_clearance_spec=evaluated.tightest_clearance_spec,
                        clearance_excluded=evaluated.clearance_excluded,
                        saturated_margins=evaluated.saturated_margins,
                        worst_values=evaluated.worst_values, worst_conditions=evaluated.worst_conditions,
                        missing_coverage=evaluated.missing_coverage)
            record.update(state='completed', **{k: v for k, v in info.items() if k not in ('record_path',)},
                          reward=reward, metrics=metrics, metric_validity=validity,
                          metric_units=result.metric_units,
                          elapsed_seconds=perf_counter() - started)
            if self.recorder is None:
                record['observation'] = None if observation is None else asdict(observation)
                write_record(path, record)
            else:
                finalizing = True
                receipt = self.recorder.finish(record, result, observation, self._recording_observation,
                                               action, rows[0].operating_points)
                committed = True
                info['record'] = deepcopy(record)
                info['eval_id'] = candidate_id
                info['receipt'] = receipt
                self._recording_observation = deepcopy(observation)
                self.recorder.retain_and_clean(receipt, workspace, self.backend)
            return observation, reward, terminated, truncated, info
        except BaseException as exc:
            self._done = True
            record.update(state='execution_error', exception_type=type(exc).__name__, error=str(exc),
                          replay_eligible=False, reward=None, simulation_calls=self.simulation_calls,
                          elapsed_seconds=perf_counter() - started)
            if self.recorder is None:
                write_record(path, record)
            elif not committed and not finalizing:
                self.recorder.finish(record, result, None, self._recording_observation, action)
                # An unexpected exception does not prove the simulator stopped.
                # Keep all workspaces for explicit recovery/inspection.
            raise

    def close(self):
        if self._closed:
            return
        if self._connected and threading.get_ident() != self._thread:
            raise RuntimeError('Close the environment from its owning worker thread')
        record = {'state': 'pending', 'simulation_calls': self.simulation_calls}
        primary = None
        try:
            write_record(self.directory / 'restoration.json', record)
        except BaseException as exc:
            primary = exc
        try:
            if self._connected:
                self.backend.restore()
                actual = self.backend.read_parameters()
                if self._initial is not None and not same_parameters(actual, self._initial):
                    raise RuntimeError('Environment restoration readback mismatch')
                record.update(state='restored', parameters=parameter_rows(actual))
            else:
                record['state'] = 'not_connected'
        except BaseException as exc:
            primary = primary or exc
            record.update(state='recovery_required', exception_type=type(exc).__name__, error=str(exc))
        finally:
            try:
                self.backend.close()
            except BaseException as exc:
                primary = primary or exc
                record.update(state='recovery_required', close_error=str(exc))
            self._closed, self._connected, self._done = True, False, True
            try:
                write_record(self.directory / 'restoration.json', record)
            except BaseException as exc:
                primary = primary or exc
        if primary is not None:
            raise primary

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.close()
        except BaseException as cleanup:
            if exc is None:
                raise
            exc.cleanup_error = f'{type(cleanup).__name__}: {cleanup}'
        return False
