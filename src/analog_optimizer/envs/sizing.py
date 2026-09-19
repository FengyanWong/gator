from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
from time import perf_counter
from uuid import uuid4

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus
from analog_optimizer.backends.conditions import SimulationCondition
from analog_optimizer.graph.circuit_graph import CircuitGraph
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
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


class CircuitSizingEnv:
    """reset() -> (observation, info); step() -> (obs, reward, terminated, truncated, info).

    The step budget is part of the finite-horizon task and of each observation;
    exhaustion terminates with bootstrap=False. Infrastructure/measurement errors
    truncate, reward=None and replay_eligible=False. Circuit failures terminate
    with -1 only when the backend explicitly attributes an evaluated candidate.
    No automatic retries or result cache: duplicates are logged and simulated.
    This is a plain Python environment, not a Gymnasium Env implementation.
    Use as a context manager; it owns and restores its backend connection.
    """

    def __init__(self, backend, graph, specs, work_root, *, max_steps=5,
                 timeout_seconds=120.0, stop_on_success=True, expected_origin='real',
                 condition: SimulationCondition | None = None):
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError('max_steps must be a positive integer')
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be positive and finite')
        if expected_origin not in ('real', 'synthetic'):
            raise ValueError('Explicit real or synthetic origin required')
        if not isinstance(stop_on_success, bool):
            raise ValueError('stop_on_success must be a boolean')
        self.condition = condition if condition is not None else backend.nominal_condition()
        # Current M3 contract: nominal-only sampling. PVT/MC validation must
        # use separate results and budgets, never nominal reward/replay updates.
        if self.condition is not None and not self.condition.nominal_only:
            raise ValueError('Sizing environment is nominal-only; PVT/MC belongs to post-validation')
        if self.condition is None and expected_origin == 'real':
            raise ValueError('A real environment needs an explicit nominal condition')
        backend.validate_condition(self.condition)
        self.backend = backend
        self._reference_graph = deepcopy(graph)
        self.mapper = ActionMapper(graph)
        self.evaluator = SpecificationEvaluator(specs)
        self.max_steps, self.timeout_seconds = max_steps, timeout_seconds
        self.stop_on_success, self.expected_origin = stop_on_success, expected_origin
        self._contract = graph_contract(graph)
        self._connected, self._closed, self._done = False, False, True
        self._initial = None
        self._seen = {}
        self.steps, self.simulation_calls, self.episode = 0, 0, 0
        self.directory = Path(work_root).resolve() / uuid4().hex
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / 'candidates').mkdir()
        config = {'schema_version': 'sizing-env-v2', 'action_version': 'absolute-group-v1',
                  'condition': None if self.condition is None else asdict(self.condition),
                  'evaluation_purpose': 'nominal',
                  'origin': expected_origin, 'max_steps': max_steps, 'timeout_seconds': timeout_seconds,
                  'stop_on_success': stop_on_success, 'specs': [asdict(s) for s in self.evaluator.specs],
                  'initial_graph': asdict(graph), 'cache_enabled': False, 'automatic_retries': 0,
                  'reward': 'negative_weighted_mean_capped_violation',
                  'budget_semantics': 'finite_horizon_termination',
                  'critic_action_semantics': 'normalized_proposal'}
        self.config_sha256 = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        write_record(self.directory / 'config.json', {**config, 'sha256': self.config_sha256})

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
        except BaseException:
            self.close()
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

    def _evaluate(self, action, *, reset):
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
                  'timings': {}}
        write_record(path, record)  # Before restoration or the first candidate mutation.
        self._done = True
        try:
            stage = perf_counter()
            if reset:
                self.backend.restore()
            else:
                self.backend.set_parameters(dict(expected))
            applied = self.backend.read_parameters()
            record['applied_parameters'] = parameter_rows(applied)
            if not same_parameters(applied, expected):
                raise ValueError('Parameter readback differs from requested candidate')
            key = tuple(sorted(applied.items()))
            record['duplicate_of'] = self._seen.get(key)
            record['timings']['parameter_update_readback'] = perf_counter() - stage
            stage = perf_counter()
            kwargs = {} if self.condition is None else {'condition': self.condition}
            artifact = self.backend.generate_netlist(self.directory / 'exports', **kwargs)
            record.update(export_job_id=artifact.job_id, netlist_sha256=artifact.sha256,
                          netlist_path=str(artifact.path))
            if artifact.origin != self.expected_origin:
                raise ValueError('Unexpected netlist origin')
            if artifact.condition != self.condition:
                raise ValueError('Exported condition differs from the nominal environment')
            record['timings']['netlisting'] = perf_counter() - stage
            stage = perf_counter()
            graph = self.backend.get_circuit_graph(artifact)
            graph.validate()
            if graph_contract(graph) != self._contract:
                raise ValueError('Exported graph changed topology or action contract')
            graph_values = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
            if not same_parameters(graph_values, applied):
                raise ValueError('Exported graph differs from parameter readback')
            record['timings']['graph_build'] = perf_counter() - stage
            self.simulation_calls += 1
            record.update(state='simulation_started', simulation_calls=self.simulation_calls)
            write_record(path, record)
            stage = perf_counter()
            result = self.backend.run_simulation(SimulationRequest(
                artifact, self.directory / 'simulations', self.evaluator.required_metrics,
                self.timeout_seconds, dict(applied), condition=self.condition))
            record['timings']['simulation_and_measurement'] = perf_counter() - stage
            if result.origin != self.expected_origin or not same_parameters(result.applied_parameters, applied):
                raise ValueError('Simulation result origin or parameters differ from the export')
            if result.condition != self.condition or result.sample_index is not None:
                raise ValueError('Non-nominal or mismatched result cannot enter nominal replay')
            record.update(job_id=result.job_id, artifact_directory=str(result.artifact_directory),
                          status=result.status.value, reason_code=result.reason_code,
                          candidate_evaluated=result.candidate_evaluated, retryable=result.retryable,
                          backend_kind=result.backend_kind)
            self._seen.setdefault(key, candidate_id)
            names = set(result.metrics) | set(self.evaluator.required_metrics)
            metrics, validity = {}, {}
            for name in names:
                value = result.metrics.get(name)
                valid = (result.status == SimulationStatus.OK and result.candidate_evaluated
                         and result.metric_validity.get(name) is True
                         and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))
                metrics[name], validity[name] = (float(value) if valid else None), valid
            evaluated = self.evaluator.evaluate(metrics, result.metric_units, validity)
            for name in evaluated.errors:
                metrics[name], validity[name] = None, False
            observation = Observation(deepcopy(graph), self.evaluator.specs, metrics, validity,
                                      dict(result.metric_units), result.status.value, result.origin,
                                      self.max_steps - self.steps, result.job_id, self.condition)
            reward, eligible, success, terminated, truncated = None, False, False, False, False
            if result.status == SimulationStatus.OK and result.candidate_evaluated and evaluated.valid:
                reward, eligible, success = evaluated.reward, not reset, evaluated.success
                terminated = (success and self.stop_on_success) or self.steps >= self.max_steps
            elif result.status in (SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED) and result.candidate_evaluated:
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
            record.update(state='completed', **{k: v for k, v in info.items() if k not in ('record_path',)},
                          reward=reward, metrics=metrics, metric_validity=validity,
                          metric_units=result.metric_units, observation=None if observation is None else asdict(observation),
                          elapsed_seconds=perf_counter() - started)
            write_record(path, record)
            return observation, reward, terminated, truncated, info
        except BaseException as exc:
            self._done = True
            record.update(state='execution_error', exception_type=type(exc).__name__, error=str(exc),
                          replay_eligible=False, reward=None, simulation_calls=self.simulation_calls,
                          elapsed_seconds=perf_counter() - started)
            write_record(path, record)
            raise

    def close(self):
        if self._closed:
            return
        if self._connected and threading.get_ident() != self._thread:
            raise RuntimeError('Close the environment from its owning worker thread')
        record = {'state': 'pending', 'simulation_calls': self.simulation_calls}
        write_record(self.directory / 'restoration.json', record)
        try:
            try:
                if self._connected:
                    self.backend.restore()
                    actual = self.backend.read_parameters()
                    if self._initial is not None and not same_parameters(actual, self._initial):
                        raise RuntimeError('Environment restoration readback mismatch')
                    record.update(state='restored', parameters=parameter_rows(actual))
                else:
                    record['state'] = 'not_connected'
            finally:
                self.backend.close()
        except BaseException as exc:
            record.update(state='recovery_required', exception_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            self._closed, self._connected, self._done = True, False, True
            write_record(self.directory / 'restoration.json', record)

    def __exit__(self, exc_type, exc, traceback):
        self.close()
