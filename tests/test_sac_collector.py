"""The experience collector: what it admits from environment results and journals, its budget (refactoring package D4: from test_graph_sac)."""

from dataclasses import replace
import json
import math

import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.runner import collect_episode

from research_support import deterministic_cpu, learner, observation, transitions


@pytest.mark.parametrize('status', ['timeout', 'measurement_error', 'nonconverged'])
def test_failed_environment_results_only_admit_attributed_continuing_design_failure(opamp, tmp_path, monkeypatch, status):
    from analog_optimizer.backends.backend import SimulationStatus
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    with CircuitSizingEnv(backend, opamp, observation(opamp).specs, tmp_path,
                          max_steps=3, stop_on_success=False, expected_origin='synthetic') as env:
        first, _ = env.reset()
        simulate = backend.run_simulation
        monkeypatch.setattr(backend, 'run_simulation', lambda req: replace(simulate(req), status=SimulationStatus(status)))
        proposal = {key: .3 for key in env.mapper.group_ids}
        step = env.step(proposal)
        if status == 'nonconverged':
            transition = Transition.from_step(first, proposal, step)
            replay = ReplayBuffer(origin='synthetic')
            replay.add(transition)
            result = learner().update(replay.sample(1))
            assert not transition.terminated and transition.bootstrap and transition.reward == -1
            assert math.isfinite(result['target_mean'])
        else:
            with pytest.raises(ValueError, match='eligible'):
                Transition.from_step(first, proposal, step)
    assert backend.parameters == backend.initial


def test_candidate_journal_mismatch_prevents_admission(transitions):
    transition = transitions[0]
    from pathlib import Path
    path = Path(transition.record_path)
    record = json.loads(path.read_text())
    record['evaluation_purpose'] = 'pvt_validation'
    path.write_text(json.dumps(record))
    step = (transition.next_observation, transition.reward, transition.terminated, transition.truncated,
            {'replay_eligible': True, 'bootstrap': transition.bootstrap,
             'record_path': str(path), 'candidate_id': transition.candidate_id})
    with pytest.raises(ValueError, match='journal'):
        Transition.from_step(transition.observation, transition.proposal, step)


def test_collector_counts_new_data_uses_policy_and_respects_budget(opamp, tmp_path):
    import random
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    model, replay = learner(), ReplayBuffer(origin='synthetic')
    with CircuitSizingEnv(backend, opamp, observation(opamp).specs, tmp_path,
                          max_steps=3, stop_on_success=False, expected_origin='synthetic') as env:
        rows = collect_episode(env, model, replay, random.Random(5), warmup=1, batch_size=2)
        assert env.simulation_calls == 4
        assert [row['action_source'] for row in rows] == ['random_warmup', 'sac_policy', 'sac_policy']
        assert len(replay) == replay.insertions == 3 and model.updates == 2
        with pytest.raises(ValueError, match='origins'):
            collect_episode(env, model, ReplayBuffer(origin='real'), random.Random(5))
        assert env.simulation_calls == 4
    assert backend.parameters == backend.initial
