"""Temperature optimizer contracts on algebraic replay; no circuit/backend run."""
from dataclasses import replace
import math

import pytest
import torch

from analog_optimizer.models import ModelConfig
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACConfig, SACLearner
from reward_v21_support import algebraic_transitions


@pytest.mark.parametrize('rate', [0., -1., True, float('nan'), float('inf')])
def test_alpha_rate_validation(rate):
    with pytest.raises(ValueError, match='Alpha learning rate'):
        SACConfig(alpha_learning_rate=rate)


def test_default_temperature_rate_is_bit_identical_and_separate_rate_only_affects_alpha(opamp):
    batch = algebraic_transitions(opamp)[:4]
    def model(rate):
        torch.manual_seed(195)
        return SACLearner(experiment=dict(origin='synthetic', split='unit-only', designs=['toy']),
            model_config=ModelConfig(hidden_dim=8, heads=2, layers=1),
            config=SACConfig(alpha_learning_rate=rate), reward_settings=batch[0].reward_settings)
    default, explicit, faster = [model(rate) for rate in (None, .0003, .01)]
    results = []
    for learner in (default, explicit, faster):
        torch.manual_seed(913)
        results.append(learner.update(batch))
    assert results[0] == results[1]
    assert results[2]['alpha'] < results[0]['alpha']
    assert faster.actor_optimizer.param_groups[0]['lr'] == .0003
    assert faster.alpha_optimizer.param_groups[0]['lr'] == .01
    for key, tensor in default.actor.state_dict().items():
        assert torch.equal(tensor, faster.actor.state_dict()[key])


def test_resume_refuses_pre_edit_digest(opamp, tmp_path):
    transitions = algebraic_transitions(opamp)
    args = dict(experiment=dict(origin='synthetic', split='unit-only', designs=['toy']),
                model_config=ModelConfig(hidden_dim=8, heads=2, layers=1),
                config=SACConfig(alpha_learning_rate=.01), reward_settings=transitions[0].reward_settings)
    learner = SACLearner(**args)
    replay = ReplayBuffer(origin='synthetic')
    checkpoint = tmp_path / 'unit.pt'
    learner.save(checkpoint, replay)
    saved = torch.load(checkpoint, weights_only=False)
    saved['contract']['code_sha256'] = 'f087a4ce40d9a1bd7db5c0c756851b5f46be71f659f3e2365d691ddb707b004a'
    torch.save(saved, checkpoint)
    with pytest.raises(ValueError, match='code/dependency mismatch'):
        SACLearner.load(checkpoint, **args)
