"""Explicit synthetic contract fixtures; these functions do not model a circuit."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from analog_optimizer.backends.backend import NetlistArtifact, SimulationStatus
from analog_optimizer.envs import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from research_support import SyntheticSizingFixture, environment
from analog_optimizer.backends.backend import UnsupportedCapability
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition


@pytest.fixture
def fixture_backend(opamp):
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], scale='linear')
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    return SyntheticSizingFixture(opamp)


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
        assert not terminated and not info['success']
        if mode in ('validity', 'nan'):
            # A completed simulation without a usable value for the required spec: a FAILED row since 2026-10-10 (the
            # default of MetricSpec.missing_is_failure) - the full penalty, replayed, and the episode goes on.
            assert reward == -1 and not truncated and info['replay_eligible'] and info['bootstrap'] and info['evaluation_valid']
            assert info['missing_counted_as_failure'] == {'nominal': ('score',)} and info['status'] == 'ok'
            assert obs.metrics['score'] is None and not obs.metric_validity['score']
        else:
            # A wrong unit, a simulation that never judged the candidate, and a measurement error that lacks no required
            # value (nothing explains it) stay errors: no reward, never replayed, the episode cut.
            assert reward is None and truncated and not info['replay_eligible'] and not info['evaluation_valid']
            assert info['missing_counted_as_failure'] == {}
            if mode != 'measurement_error':
                assert obs.metrics['score'] is None and not obs.metric_validity['score']


@pytest.mark.parametrize('mode', ['validity', 'nan'])
def test_a_spec_that_opts_out_keeps_a_missing_value_an_error(fixture_backend, tmp_path, mode):
    """missing_is_failure=False: the rule of every spec before 2026-10-10."""
    spec = MetricSpec('score', 'fixture', 'min', 1, lower=3, missing_is_failure=False)
    with CircuitSizingEnv(fixture_backend, fixture_backend.graph, [spec], tmp_path, expected_origin='synthetic') as env:
        env.reset()
        if mode == 'validity':
            fixture_backend.valid = False
        else:
            fixture_backend.value_override = float('nan')
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 1})
        assert reward is None and not terminated and truncated and not info['success'] and not info['replay_eligible']
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


def test_a_journal_can_skip_the_fsync_and_stays_atomic(tmp_path, monkeypatch):
    from analog_optimizer.envs import sizing
    calls = []
    monkeypatch.setattr(sizing.os, 'fsync', lambda fd: calls.append(fd))
    sizing.write_record(tmp_path / 'a.json', {'x': 1})
    sizing.write_record(tmp_path / 'b.json', {'x': 2}, durable=False)
    assert len(calls) == 1 and (tmp_path / 'b.json').read_text() == '{\n  "x": 2\n}\n'
    assert not list(tmp_path.glob('*.tmp'))


def test_a_synthetic_environment_skips_the_fsync_and_a_real_one_does_not(monkeypatch):
    from analog_optimizer.envs import sizing
    seen = []
    monkeypatch.setattr(sizing, 'write_record', lambda path, value, **options: seen.append(options))
    for origin in ('synthetic', 'real'):
        env = object.__new__(sizing.CircuitSizingEnv)
        env.expected_origin = origin
        env._record('journal.json', {})
    assert seen == [dict(durable=False), {}]


NOMINAL = SimulationCondition(PVTCorner('nominal', 'tt', 27.0, 1.0))


def prepared(opamp):
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], scale='linear')
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    return opamp


class RelabelledFixture(SyntheticSizingFixture):
    """The synthetic fixture with a scripted origin and invocation count; nothing else changes."""
    origin, invocations = 'real', None

    def nominal_condition(self):
        return NOMINAL

    def validate_condition(self, condition):
        if condition not in (None, NOMINAL):
            raise UnsupportedCapability('fixture: nominal only')

    def generate_netlist(self, work_root, *, condition=None):
        artifact = super().generate_netlist(work_root)
        return NetlistArtifact(artifact.path, artifact.job_id, artifact.sha256, self.origin, condition)

    def run_simulation(self, request):
        result = super().run_simulation(request)
        return replace(result, origin=self.origin, condition=request.condition, simulator_invocations=self.invocations)


def test_a_synthetic_result_without_an_invocation_count_is_a_complete_call(opamp, tmp_path):
    """F1: the synthetic and MOCK backends never report simulator invocations; their call is never 'uncertain'."""
    backend = SyntheticSizingFixture(prepared(opamp))
    with environment(backend, tmp_path) as env:
        first, info = env.reset()
        assert not info['truncated'] and info['evaluation_valid'] and env.simulation_calls == 1
        assert env.uncertain_calls == 0 and env.confirmed_calls == 0            # no simulator was launched
        record = json.loads(Path(info['record_path']).read_text())
        assert record['jobs'][0]['uncertain_calls'] == 0 and record['jobs'][0]['confirmed_calls'] == 0
        obs, reward, terminated, truncated, info = env.step({'input_pair_width': 0})
        assert reward == 0 and not truncated and info['replay_eligible'] and env.simulation_calls == 2


@pytest.mark.parametrize('invocations, uncertain', [(None, 1), (1, 0), (0, 0)])
def test_a_real_result_reports_its_invocation_or_stays_uncertain(opamp, tmp_path, invocations, uncertain):
    backend = RelabelledFixture(prepared(opamp))
    backend.invocations = invocations
    specs = [MetricSpec('score', 'fixture', 'min', 1, lower=3)]
    with CircuitSizingEnv(backend, backend.graph, specs, tmp_path, expected_origin='real') as env:
        first, info = env.reset()
        assert info['truncated'] == (invocations is None) and env.uncertain_calls == uncertain
        assert env.confirmed_calls == (invocations or 0) and env.simulation_calls == (1 if invocations != 0 else 0)
        record = json.loads(Path(info['record_path']).read_text())
        assert record['jobs'][0]['uncertain_calls'] == uncertain
        if invocations is None:
            assert record['conditions_stop_reason'] == 'unavailable_or_uncertain_condition'
