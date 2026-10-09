"""The SAC update: cached and uncached updates, the temperature, the target soft update and the terminal bootstrap (refactoring package D4: from test_graph_sac)."""

from copy import deepcopy
import math

import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACConfig, temperature_loss

from research_support import deterministic_cpu, learner, transitions



@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_cached_and_uncached_replay_updates_are_exact_and_recompute_embeddings(encoder, transitions):
    torch.manual_seed(715)
    cached = learner(encoder)
    torch.manual_seed(715)
    uncached = learner(encoder, input_cache_capacity=0, topology_cache_capacity=0)
    replay = ReplayBuffer(origin='synthetic', seed=91)
    for transition in (transitions[0], transitions[3]):
        replay.add(transition)
    obs = [transitions[0].observation]
    before = cached.act(obs, deterministic=True)
    for _ in range(2):
        batch = replay.sample(2)  # New Python objects on every sample.
        rng = torch.get_rng_state()
        expected = uncached.update(batch)
        torch.set_rng_state(rng)
        assert cached.update(deepcopy(batch)) == expected
        for a, b in zip(cached.actor.parameters(), uncached.actor.parameters()):
            torch.testing.assert_close(a, b, rtol=0, atol=0)
        for a, b in zip(cached.critics.parameters(), uncached.critics.parameters()):
            torch.testing.assert_close(a, b, rtol=0, atol=0)
        for a, b in zip(cached.targets.parameters(), uncached.targets.parameters()):
            torch.testing.assert_close(a, b, rtol=0, atol=0)
        assert torch.equal(cached.log_alpha, uncached.log_alpha)
    assert cached.input_cache.info()['misses'] == 4
    assert cached.input_cache.topologies.info()['misses'] == 2
    assert cached.act(obs, deterministic=True) != before
    assert cached.act(obs, deterministic=True) == uncached.act(obs, deterministic=True)


def test_temperature_moves_correctly_for_entropy_above_and_below_target():
    # Entropy target is -count: entropy above target decreases alpha, below increases.
    for log_prob, expected_gradient in ((torch.tensor([-2., -1.]), 1),
                                        (torch.tensor([4., 3.]), -1)):
        log_alpha = torch.tensor(-1., requires_grad=True)
        loss = temperature_loss(log_alpha, log_prob, torch.tensor([2., 1.]), 1.)
        loss.backward()
        assert expected_gradient * log_alpha.grad > 0


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_sac_mixed_update_target_soft_update_and_terminal_bootstrap(encoder, transitions):
    model = learner(encoder, config=SACConfig(tau=.2))
    before = [p.detach().clone() for p in model.targets.parameters()]
    result = model.update([transitions[0], transitions[3]])
    assert result['action_counts'] == [2, 1]
    assert all(math.isfinite(value) for value in result.values() if isinstance(value, (int, float)))
    assert result['actor_grad_norm'] > 0 and result['critic_grad_norm'] > 0
    for old, actual, current in zip(before, model.targets.parameters(), model.critics.parameters()):
        torch.testing.assert_close(actual, torch.lerp(old, current.detach(), .2))
        assert actual.grad is None
    terminals = [transitions[2], transitions[5]]
    assert all(t.terminated and not t.bootstrap for t in terminals)
    result = model.update(terminals)
    assert result['target_mean'] == pytest.approx(sum(t.reward for t in terminals) / 2)
