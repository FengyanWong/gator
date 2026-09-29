"""Explicit synthetic contract fixtures; these functions do not model a circuit."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from analog_optimizer.backends.backend import (VirtuosoBackend, NetlistArtifact, SimulationResult,
                                               SimulationStatus)
from analog_optimizer.envs import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec


class SyntheticSizingFixture(VirtuosoBackend):
    def __init__(self, graph):
        self.graph = deepcopy(graph)
        self.initial = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
        self.parameters = dict(self.initial)
        self.status, self.evaluated, self.unit = SimulationStatus.OK, True, 'fixture'
        self.valid, self.value_override = True, None
        self.connected, self.calls, self.writes = False, 0, 0
        self.exports = {}

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def restore(self):
        self.parameters = dict(self.initial)

    def read_parameters(self):
        return dict(self.parameters)

    def set_parameters(self, parameters):
        self.writes += 1
        self.parameters = dict(parameters)

    def generate_netlist(self, work_root):
        job_id = uuid4().hex
        directory = work_root / job_id
        directory.mkdir(parents=True)
        path = directory / 'fixture.json'
        path.write_text(json.dumps(sorted(self.parameters.items())))
        self.exports[job_id] = dict(self.parameters)
        return NetlistArtifact(path, job_id, hashlib.sha256(path.read_bytes()).hexdigest(), 'synthetic')

    def get_circuit_graph(self, artifact):
        graph, values = deepcopy(self.graph), self.exports[artifact.job_id]
        for group_index, group in enumerate(graph.parameter_groups):
            if not group.mutable:
                continue
            for member in group.members:
                old = graph.parameters[member.device_id][member.parameter]
                key = (member.device_id, old.source_name or member.parameter)
                graph.parameters[member.device_id][member.parameter] = replace(old, value=values[key], raw=str(values[key]))
            graph.parameter_groups[group_index] = replace(group, value=values[key] / member.ratio)
        return graph

    def run_simulation(self, request):
        self.calls += 1
        directory = request.work_root / uuid4().hex
        directory.mkdir(parents=True)
        value = next(iter(self.parameters.values())) / 1e-6
        if self.value_override is not None:
            value = self.value_override
        return SimulationResult(directory.name, 'synthetic-sizing-fixture', 'synthetic', self.status,
                                'injected_fixture', False, self.evaluated, {'score': value},
                                {'score': self.unit}, {'score': self.valid}, dict(self.parameters), directory, 0.01)


@pytest.fixture
def fixture_backend(opamp):
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], scale='linear')
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    return SyntheticSizingFixture(opamp)


def environment(backend, tmp_path, **kwargs):
    return CircuitSizingEnv(backend, backend.graph, [MetricSpec('score', 'fixture', 'min', 1, lower=3)],
                            tmp_path, expected_origin='synthetic', **kwargs)


def test_reset_step_success_actual_graph_and_restoration(fixture_backend, tmp_path):
    backend = fixture_backend
    with environment(backend, tmp_path) as env:
        first, info = env.reset()
        assert first.metrics == {'score': 2} and not info['success']
        assert not info['replay_eligible'] and first.remaining_steps == 5
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 0})
        assert obs.metrics == {'score': 4.5} and reward == 0 and terminated and not truncated
        assert info['success'] and info['replay_eligible'] and not info['bootstrap']
        assert first.graph.parameters['input_left']['w'].value == 2e-6
        assert obs.graph.parameters['input_left']['w'].value == pytest.approx(4.5e-6)
        record = json.loads(Path(info['record_path']).read_text())
        assert record['proposal'] == {'input_pair_width': 0}
        assert record['applied_parameters'][0]['value'] == pytest.approx(4.5e-6)
        assert record['netlist_sha256'] and record['origin'] == 'synthetic'
        with pytest.raises(RuntimeError, match='reset'):
            env.step({'input_pair_width': -1})
    assert backend.parameters == backend.initial and not backend.connected
    assert json.loads((env.directory / 'restoration.json').read_text())['state'] == 'restored'


def test_duplicates_are_resimulated_and_finite_budget_terminates(fixture_backend, tmp_path):
    with environment(fixture_backend, tmp_path, max_steps=2, stop_on_success=False) as env:
        env.reset()
        first = env.step({'input_pair_width': -1})
        second = env.step({'input_pair_width': -1})
        assert not first[2] and first[4]['bootstrap']
        assert second[2] and not second[3] and second[0].remaining_steps == 0
        assert second[4]['duplicate_of'] == first[4]['candidate_id'] and not second[4]['cache_hit']
        assert env.simulation_calls == fixture_backend.calls == 3
        obs, _ = env.reset()
        assert obs.metrics['score'] == 2 and obs.remaining_steps == 2
        assert env.episode == 2 and env.simulation_calls == 4


@pytest.mark.parametrize('bad', [{}, {'input_pair_width': 2}, {'input_pair_width': float('nan')}])
def test_bad_action_has_no_side_effect_or_budget_cost(fixture_backend, tmp_path, bad):
    with environment(fixture_backend, tmp_path) as env:
        with pytest.raises(RuntimeError):
            env.step({'input_pair_width': 0})
        env.reset()
        with pytest.raises(ValueError):
            env.step(bad)
        assert env.steps == fixture_backend.writes == 0
        assert env.simulation_calls == 1


@pytest.mark.parametrize('status', [SimulationStatus.TIMEOUT, SimulationStatus.TRANSPORT_ERROR,
                                  SimulationStatus.LICENSE_ERROR, SimulationStatus.BACKEND_ERROR])
def test_infrastructure_failure_has_no_reward_or_next_state(fixture_backend, tmp_path, status):
    with environment(fixture_backend, tmp_path) as env:
        env.reset()
        fixture_backend.status = status
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 0})
        assert obs is None and reward is None and not terminated and truncated
        assert not info['replay_eligible'] and not info['bootstrap'] and not info['success']
        record = json.loads(Path(info['record_path']).read_text())
        assert record['metrics'] == {'score': None} and record['simulation_calls'] == 2


@pytest.mark.parametrize('mode', ['unit', 'validity', 'nan', 'not_evaluated', 'measurement_error'])
def test_bad_measurement_cannot_become_success(fixture_backend, tmp_path, mode):
    with environment(fixture_backend, tmp_path) as env:
        env.reset()
        if mode == 'unit':
            fixture_backend.unit = 'wrong'
        elif mode == 'validity':
            fixture_backend.valid = False
        elif mode == 'nan':
            fixture_backend.value_override = float('nan')
        elif mode == 'not_evaluated':
            fixture_backend.evaluated = False
        else:
            fixture_backend.status = SimulationStatus.MEASUREMENT_ERROR
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 1})
        assert reward is None and not terminated and truncated and not info['success']
        assert not info['replay_eligible']
        assert obs.metrics['score'] is None and not obs.metric_validity['score']


@pytest.mark.parametrize('status', [SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED])
def test_attributed_circuit_failure_has_finite_continuing_penalty(fixture_backend, tmp_path, status):
    with environment(fixture_backend, tmp_path) as env:
        env.reset()
        fixture_backend.status = status
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 1})
        assert reward == -1 and not terminated and not truncated and info['replay_eligible']
        assert obs.metrics['score'] is None and not info['success'] and info['bootstrap']


@pytest.mark.parametrize('stage', ['write', 'graph', 'simulation'])
def test_unexpected_failure_is_journaled_and_restored(fixture_backend, tmp_path, monkeypatch, stage):
    env = environment(fixture_backend, tmp_path)
    def fail(*args):
        raise ConnectionError('injected stage failure')
    with pytest.raises(ConnectionError), env:
        env.reset()
        method = {'write': 'set_parameters', 'graph': 'get_circuit_graph', 'simulation': 'run_simulation'}[stage]
        monkeypatch.setattr(fixture_backend, method, fail)
        env.step({'input_pair_width': 1})
    assert fixture_backend.parameters == fixture_backend.initial and not fixture_backend.connected
    records = [json.loads(p.read_text()) for p in (env.directory / 'candidates').glob('*.json')]
    failed = next(r for r in records if r['state'] == 'execution_error')
    assert not failed['replay_eligible'] and failed['reward'] is None
    assert failed['simulation_calls'] == (2 if stage == 'simulation' else 1)


def test_failed_restore_is_visible_and_closes_connection(fixture_backend, tmp_path, monkeypatch):
    env = environment(fixture_backend, tmp_path)
    with pytest.raises(ConnectionError, match='restore'), env:
        env.reset()
        env.step({'input_pair_width': 1})
        def fail():
            raise ConnectionError('injected restore failure')
        monkeypatch.setattr(fixture_backend, 'restore', fail)
    assert not fixture_backend.connected
    record = json.loads((env.directory / 'restoration.json').read_text())
    assert record['state'] == 'recovery_required'


@pytest.mark.parametrize('mode', ['readback', 'origin', 'graph', 'result'])
def test_inconsistent_candidate_binding_is_rejected(fixture_backend, tmp_path, monkeypatch, mode):
    with environment(fixture_backend, tmp_path) as env:
        env.reset()
        if mode == 'readback':
            monkeypatch.setattr(fixture_backend, 'set_parameters', lambda _: None)
        elif mode == 'origin':
            original = fixture_backend.generate_netlist
            monkeypatch.setattr(fixture_backend, 'generate_netlist', lambda p: replace(original(p), origin='real'))
        elif mode == 'graph':
            monkeypatch.setattr(fixture_backend, 'get_circuit_graph', lambda _: deepcopy(fixture_backend.graph))
        else:
            original = fixture_backend.run_simulation
            monkeypatch.setattr(fixture_backend, 'run_simulation', lambda req: replace(original(req), applied_parameters={}))
        with pytest.raises(ValueError):
            env.step({'input_pair_width': 1})
        assert env._done


def test_observation_can_be_converted_to_pyg_with_current_values(fixture_backend, tmp_path):
    pytest.importorskip('torch_geometric')
    from analog_optimizer.graph.pyg_converter import to_pyg
    with environment(fixture_backend, tmp_path) as env:
        baseline, _ = env.reset()
        updated, *_ = env.step({'input_pair_width': 1})
        first, last = to_pyg(baseline.graph), to_pyg(updated.graph)
        assert first.group_x[0, 0] != last.group_x[0, 0]
        assert last.group_mutable.tolist() == [True, False]


@pytest.mark.parametrize('mc', [False, True])
def test_validation_conditions_cannot_enter_nominal_environment(fixture_backend, tmp_path, mc):
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition, MonteCarloConfig
    condition = SimulationCondition(PVTCorner('tt', 'tt', 27, 1),
        'mc_validation' if mc else 'pvt_validation', MonteCarloConfig(3, 42) if mc else None)
    with pytest.raises(ValueError, match='nominal-only'):
        environment(fixture_backend, tmp_path, condition=condition)
    assert not fixture_backend.connected and fixture_backend.writes == 0 and not list(tmp_path.iterdir())


def test_pvt_result_cannot_become_nominal_replay(fixture_backend, tmp_path, monkeypatch):
    from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
    from analog_optimizer.evaluation.corners import NominalDesign
    with environment(fixture_backend, tmp_path) as env:
        env.reset()
        original = fixture_backend.run_simulation
        condition = SimulationCondition(PVTCorner('tt', 'tt', 27, 1), 'pvt_validation')
        monkeypatch.setattr(fixture_backend, 'run_simulation', lambda req: replace(original(req), condition=condition))
        with pytest.raises(ValueError, match='nominal replay'):
            env.step({'input_pair_width': 0})
        records = [json.loads(p.read_text()) for p in (env.directory / 'candidates').glob('*.json')]
        record = next(r for r in records if r['kind'] == 'step')
        assert record['replay_eligible'] is False
        with pytest.raises(ValueError):
            NominalDesign.from_record(record)
