"""Learner checkpoints: the exact next update after a reload, schema and encoder refusals (refactoring package D4: from test_graph_sac)."""

from dataclasses import replace

import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.graph.pyg_converter import FeatureSchema
from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner

from research_support import deterministic_cpu, EXPERIMENT, learner, MODEL, model_config, transitions


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_checkpoint_exact_next_update_and_schema_rejection(encoder, transitions, tmp_path):
    replay = ReplayBuffer(origin='synthetic', seed=97)
    for item in transitions:
        replay.add(item)
    original = learner(encoder)
    original.update(replay.sample(4))
    path = tmp_path / 'checkpoint.pt'
    original.save(path, replay, run_state={'episodes': 2, 'simulation_calls': 8})
    expected = original.update(replay.sample(4))
    restored, restored_replay, run_state = SACLearner.load(path, experiment=EXPERIMENT, model_config=model_config(encoder))
    actual = restored.update(restored_replay.sample(4))
    assert expected == actual
    assert run_state == {'episodes': 2, 'simulation_calls': 8}
    for a, b in zip(original.actor.parameters(), restored.actor.parameters()):
        torch.testing.assert_close(a, b, rtol=0, atol=0)
    for a, b in zip(original.critics.parameters(), restored.critics.parameters()):
        torch.testing.assert_close(a, b, rtol=0, atol=0)
    for a, b in zip(original.targets.parameters(), restored.targets.parameters()):
        torch.testing.assert_close(a, b, rtol=0, atol=0)
    assert torch.equal(original.log_alpha, restored.log_alpha)
    with pytest.raises(ValueError, match='mismatch'):
        SACLearner.load(path, experiment=EXPERIMENT, model_config=model_config(encoder),
                        feature_schema=replace(FeatureSchema(), version='incompatible'))
    with pytest.raises(ValueError, match='mismatch'):
        SACLearner.load(path, experiment={**EXPERIMENT, 'split': 'test'}, model_config=model_config(encoder))


@pytest.mark.parametrize('encoder', ['rgcn', 'gatv2', 'graph_gps', 'group_cross_attention'])
def test_checkpoint_rejects_different_encoder_before_loading(transitions, tmp_path, encoder):
    source = learner(encoder)
    replay = ReplayBuffer(origin='synthetic')
    replay.add(transitions[0])
    path = tmp_path / 'source.pt'
    source.save(path, replay)
    payload = torch.load(path, weights_only=False)
    assert payload['contract']['model_config']['encoder_type'] == encoder
    with pytest.raises(ValueError, match='mismatch'):
        SACLearner.load(path, experiment=EXPERIMENT, model_config=MODEL)
