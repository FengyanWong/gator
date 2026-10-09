"""Scripted real-labelled mechanism tests. No Spectre, Virtuoso or bridge calls."""
import json
from pathlib import Path
import random

import pytest
import torch

from analog_optimizer.backends.backend import SimulationStatus as Status
from analog_optimizer.models import ModelConfig
from analog_optimizer.models.inputs import SpecSchema, batch_observations
from analog_optimizer.recording import ExperimentStore, RecordingConfig, RunRecorder
from analog_optimizer.recording.codec import raw, pack, unpack
from analog_optimizer.recording.reader import RunReader
from analog_optimizer.recording.session import transition_from_store
from analog_optimizer.training.parallel import collect_parallel_episodes
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.runner import collect_episode
from analog_optimizer.training.sac import SACConfig, SACLearner
from reward_v21_support import NOMINAL, CORNERS, PLAN, ParallelFactory, environment, reset, step

SCHEMA = SpecSchema(metrics=(('score', 'fixture', 1.), ('other', 'fixture', 1.)))


def learner():
    return SACLearner(experiment=dict(origin='real', split='scripted-mechanism-only', designs=['fake-real']),
        model_config=ModelConfig(hidden_dim=8, heads=2, layers=1), spec_schema=SCHEMA,
        config=SACConfig(alpha_learning_rate=.01), condition_policy='after_nominal', planned_conditions=PLAN)


def missing(status=Status.MEASUREMENT_ERROR, evaluated=True, unit='fixture'):
    return status, evaluated, {'score': None, 'other': 2.}, {'score': False, 'other': True}, {'score': unit, 'other': 'fixture'}


def record(result):
    return json.loads(Path(result[4]['record_path']).read_text())


def test_gate_failure_is_scored_replayed_and_skips_corners(opamp, tmp_path):
    with environment(opamp, tmp_path) as env:
        before, info = reset(env)
        assert env.backend.launched == [NOMINAL] and not info['replay_eligible']
        proposal, result = step(env)
        assert result[1] < -.5 and not result[2] and not result[3]
        assert env.backend.launched == [NOMINAL, NOMINAL]
        assert record(result)['conditions_stop_reason'] == 'nominal_gate_not_met'
        assert not result[0].evaluation.complete and not result[0].evaluation.success
        transition = Transition.from_step(before, proposal, result)
        replay = ReplayBuffer(origin='real')
        replay.add(transition)
        assert len(replay) == 1 and result[4]['bootstrap']
        assert raw(unpack(pack(result[0]))) == raw(result[0])
        assert json.loads((env.directory / 'config.json').read_text())['failure_policy'] == 'continue_attributed'


def test_corner_flagged_missing_value_preserves_status_and_other_values(opamp, tmp_path):
    with environment(opamp, tmp_path, nominal_pass=True) as env:
        before, _ = reset(env)
        env.backend.outcomes[CORNERS[0]] = missing()
        proposal, result = step(env)
        assert env.backend.launched == [NOMINAL, *PLAN]
        assert result[4]['replay_eligible'] and not result[3]
        verdict = result[0].evaluation
        assert verdict.violations == {'score': 1., 'other': 0.}
        assert verdict.missing_counted_as_failure == {'corner_0': ('score',)}
        failed = result[0].condition_results[1]
        assert failed.status == 'measurement_error' and failed.metrics['other'] == 2.
        assert failed.reason_code == 'missing_counted_as_failure' and failed.missing_failure_metrics == ['score']
        Transition.from_step(before, proposal, result).validate()


@pytest.mark.parametrize('policy', ['off', 'always', 'after_nominal'])
def test_flagged_missing_nominal_is_actionable_and_next_step_can_recover(opamp, tmp_path, policy):
    with environment(opamp, tmp_path, policy=policy) as env:
        before, _ = reset(env)
        env.backend.outcomes[NOMINAL] = missing()
        proposal, result = step(env)
        assert result[0].status == 'measurement_error' and result[4]['replay_eligible']
        Transition.from_step(before, proposal, result).validate()
        assert torch.isfinite(batch_observations([result[0]], spec_schema=SCHEMA).context).all()
        env.backend.outcomes.clear()
        proposal, recovered = step(env)
        Transition.from_step(result[0], proposal, recovered).validate()
        assert recovered[0].status == 'ok'


@pytest.mark.parametrize('failure', ['unflagged', 'unit', 'infrastructure', 'unanalyzed', 'uncertain'])
def test_unscorable_corner_truncates_and_never_enters_replay(opamp, tmp_path, failure):
    with environment(opamp, tmp_path, nominal_pass=True, flag=failure != 'unflagged') as env:
        before, _ = reset(env)
        env.backend.outcomes[CORNERS[0]] = missing(
            status=Status.TIMEOUT if failure == 'infrastructure' else Status.MEASUREMENT_ERROR,
            evaluated=failure not in ('infrastructure', 'unanalyzed'), unit='wrong' if failure == 'unit' else 'fixture')
        if failure == 'uncertain': env.backend.unknown = True
        proposal, result = step(env)
        assert result[1] is None and result[3] and not result[4]['replay_eligible']
        with pytest.raises(ValueError, match='eligible'):
            Transition.from_step(before, proposal, result)
        assert CORNERS[1] not in env.backend.launched


@pytest.mark.parametrize('policy', ['off', 'always', 'after_nominal'])
@pytest.mark.parametrize('status', [Status.INVALID_DESIGN, Status.NONCONVERGED])
def test_attributed_failure_continues_until_normal_horizon(opamp, tmp_path, policy, status):
    with environment(opamp, tmp_path, policy=policy, max_steps=2) as env:
        before, _ = reset(env)
        env.backend.outcomes[NOMINAL] = missing(status=status)
        proposal, first = step(env)
        assert first[1] == -1. and not first[2] and not first[3] and first[4]['bootstrap']
        Transition.from_step(before, proposal, first).validate()
        proposal, last = step(env)
        assert last[2] and not last[3] and not last[4]['bootstrap']
        Transition.from_step(first[0], proposal, last).validate()


def test_stop_on_success_and_stop_between_conditions_remain_effective(opamp, tmp_path):
    with environment(opamp, tmp_path, stop_on_success=True) as env:
        reset(env)
        env.backend.nominal_pass = True
        _, result = step(env)
        assert result[2] and result[4]['success'] and not result[4]['bootstrap']
    with environment(opamp, tmp_path, nominal_pass=True) as env:
        reset(env)
        stop_file = tmp_path / 'stop'
        env.backend.stop_after_nominal = stop_file
        _, result = step(env, stop_file=stop_file)
        assert result[3] and result[1] is None and not result[4]['replay_eligible']
        assert record(result)['conditions_stop_reason'] == 'coordinator_stop'
        assert env.backend.launched == [NOMINAL, NOMINAL]


@pytest.mark.parametrize('ceiling,transitions,charged', [(4, 1, 2), (6, 3, 4)])
def test_serial_reserves_full_plan_and_charges_actual_calls(opamp, tmp_path, ceiling, transitions, charged):
    replay = ReplayBuffer(origin='real')
    with environment(opamp, tmp_path) as env:
        collect_episode(env, learner(), replay, random.Random(8), warmup=100, batch_size=100,
                        max_simulation_calls=ceiling)
        ledger = json.loads((env.directory / 'collector-launch-budget.json').read_text())
        assert ledger['charged_calls'] == charged == len(env.backend.launched)
        assert ledger['reservations'] == {} and ledger['uncertain_calls'] == 0
        assert len(replay) == transitions


def test_no_preparation_without_full_reservation(opamp, tmp_path):
    with environment(opamp, tmp_path) as env:
        reset(env)
        env.authorize_launches(2)
        with pytest.raises(ValueError, match='complete candidate plan'):
            env.step({key: 0. for key in env.mapper.group_ids})
        assert env.backend.writes == 0 and env.backend.calls == 1


def test_two_lanes_share_reservations_and_charge_only_launched_conditions(opamp, tmp_path):
    replay = ReplayBuffer(origin='real')
    report = collect_parallel_episodes(ParallelFactory(opamp, tmp_path), learner(), replay, random.Random(8),
        max_workers=2, episodes=2, warmup=100, batch_size=100, max_simulation_calls=12)
    assert report['passed'] and report['completed_episodes'] == 2 and len(replay) == 4
    assert report['simulation_calls'] == 10 and report['worker_count'] == 2
    ledger = json.loads((tmp_path / 'collector-launch-budget.json').read_text())
    assert ledger['charged_calls'] == 10 and ledger['reservations'] == {}
    assert [row['reward'] for row in report['stages'] if row['lane'] == 0] == [-.625, -.625]
    assert [row['reward'] for row in report['stages'] if row['lane'] == 1] == [0., 0.]


def test_durable_missing_failure_transition_and_checkpoint_contract(opamp, tmp_path):
    with ExperimentStore(tmp_path / 'db', RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', {})
        recorder = RunRecorder(store, run)
        replay = ReplayBuffer(origin='real', store=store)
        with environment(opamp, tmp_path / 'env', nominal_pass=True, recorder=recorder) as env:
            before, _ = reset(env)
            env.backend.outcomes[CORNERS[0]] = missing()
            proposal, result = step(env)
            transition = Transition.from_step(before, proposal, result)
            replay.add(transition)
            restored = transition_from_store(store, transition.candidate_id)
            assert raw(vars(restored)) == raw(vars(transition))
            model = learner()
            model.update([restored])
            checkpoint = tmp_path / 'v21.pt'
            model.save(checkpoint, replay)
            recovered, buffer, _ = SACLearner.load(checkpoint, experiment=model.experiment,
                model_config=model.model_config, spec_schema=SCHEMA, config=model.config,
                condition_policy='after_nominal', planned_conditions=PLAN, store=store)
            assert recovered.contract() == model.contract() and len(buffer) == 1
            assert model.contract()['failure_policy'] == 'continue_attributed'
            assert model.contract()['config']['alpha_learning_rate'] == .01
            assert model.contract()['reward_settings']['nominal_gate_band'] == .5
            reader = RunReader(tmp_path / 'db')
            try:
                candidate = reader.overview(run)['summary']['best_infeasible']
                assert candidate['robust_feasible'] is False
            finally:
                reader.db.close()
