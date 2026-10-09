"""Record 7.221: the gamma-zero shortcut and the lent replay give exactly the full calculation (refactoring package D4: from test_graph_sac)."""

import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACConfig, SACLearner

from research_support import deterministic_cpu, EXPERIMENT, learner, model_config, transitions



# ------------------------------------------------------------------- record 7.221: gamma-zero shortcut, lent replay
def _equal_state(a, b):
    import numpy as np
    if isinstance(a, torch.Tensor):
        assert isinstance(b, torch.Tensor) and a.dtype == b.dtype and torch.equal(a, b)
    elif isinstance(a, np.ndarray):
        assert isinstance(b, np.ndarray) and a.dtype == b.dtype and np.array_equal(a, b)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            _equal_state(a[key], b[key])
    elif isinstance(a, (list, tuple)):
        assert type(a) is type(b) and len(a) == len(b)
        for x, y in zip(a, b):
            _equal_state(x, y)
    else:
        assert a == b


def assert_same_learner_state(a, b):
    """Weights, target networks, temperature, all three optimizers' moments and the update counter."""
    for module_a, module_b in ((a.actor, b.actor), (a.critics, b.critics), (a.targets, b.targets)):
        _equal_state(module_a.state_dict(), module_b.state_dict())
    assert torch.equal(a.log_alpha, b.log_alpha) and a.updates == b.updates
    for name in ('actor_optimizer', 'critic_optimizer', 'alpha_optimizer'):
        _equal_state(getattr(a, name).state_dict(), getattr(b, name).state_dict())


def _cache(cache):
    return {} if cache == 'warm' else dict(input_cache_capacity=0, topology_cache_capacity=0)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
@pytest.mark.parametrize('batch_size', [1, 3, 6])
@pytest.mark.parametrize('cache', ['warm', 'cold'])
def test_zero_gamma_shortcut_equals_the_full_calculation(encoder, batch_size, cache, transitions):
    """gamma 0 leaves out the next states' batch, actor and target critics. Losses, targets, weights, optimizer moments,
    temperature, counters, every random-number generator and the following actions stay identical to the full
    calculation - mixed graphs, odd packed action counts (2 + 1), terminal and bootstrapping transitions."""
    import random
    import numpy as np
    config = SACConfig(gamma=0.0, tau=.2)
    torch.manual_seed(11)
    fast = learner(encoder, config=config, **_cache(cache))
    torch.manual_seed(11)
    full = learner(encoder, config=config, **_cache(cache))
    full.zero_gamma_shortcut = False
    assert fast.skips_unused_bootstrap() and not full.skips_unused_bootstrap()
    replays = [ReplayBuffer(origin='synthetic', seed=5) for _ in range(2)]
    for transition in transitions:
        for replay in replays:
            replay.add(transition)
    python_rng, numpy_rng = random.getstate(), np.random.get_state()
    for _ in range(4):
        before = torch.get_rng_state()
        expected = full.update(replays[1].sample(batch_size))
        after = torch.get_rng_state()
        torch.set_rng_state(before)
        actual = fast.update(replays[0].sample(batch_size))
        assert torch.equal(torch.get_rng_state(), after)
        assert actual == expected
        assert_same_learner_state(fast, full)
        assert replays[0]._rng.getstate() == replays[1]._rng.getstate()
    assert random.getstate() == python_rng
    _equal_state(np.random.get_state(), numpy_rng)
    states = [transitions[0].observation, transitions[3].observation]
    before = torch.get_rng_state()
    expected = full.act(states)
    torch.set_rng_state(before)
    assert fast.act(states) == expected
    assert fast.act(states, deterministic=True) == full.act(states, deterministic=True)


def test_zero_gamma_noise_has_the_size_the_next_state_actor_draws(transitions):
    """The draw that replaces actor.sample(next-state batch) has exactly that batch's active-action count."""
    model = learner()
    for subset in ([transitions[0]], [transitions[0], transitions[3]], transitions):
        following = model.batch([t.next_observation for t in subset])
        torch.manual_seed(3)
        with torch.no_grad():
            model.actor.sample(following)
        expected = torch.get_rng_state()
        torch.manual_seed(3)
        model._draw_skipped_next_action_noise([t.next_observation for t in subset])
        assert torch.equal(torch.get_rng_state(), expected)
        assert sum(g.mutable for t in subset for g in t.next_observation.graph.parameter_groups) == following.active.numel()


@pytest.mark.parametrize('gamma', [1e-300, 1e-9, .5, .99])
def test_nonzero_gamma_keeps_the_full_bootstrap(gamma, transitions):
    """Every nonzero discount, however small, batches the next states and bootstraps: the shortcut only reads gamma."""
    model = learner(config=SACConfig(gamma=gamma))
    assert not model.skips_unused_bootstrap()
    calls = []
    original = model.batch
    model.batch = lambda observations, **kwargs: calls.append(len(observations)) or original(observations, **kwargs)
    bootstrapping = [transitions[0], transitions[3]]
    assert all(t.bootstrap for t in bootstrapping)
    result = model.update(bootstrapping)
    assert calls == [2, 2]
    if gamma >= .5:
        assert result['target_mean'] != pytest.approx(sum(t.reward for t in bootstrapping) / 2, abs=1e-9)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_zero_gamma_save_and_resume_gives_the_exact_next_update(encoder, transitions, tmp_path):
    config = SACConfig(gamma=0.0)
    replay = ReplayBuffer(origin='synthetic', seed=97)
    for item in transitions:
        replay.add(item)
    original = learner(encoder, config=config)
    replay.update_learner(original, 4)
    path = tmp_path / 'checkpoint.pt'
    original.save(path, replay, run_state={'episodes': 2})
    expected = replay.update_learner(original, 4)
    restored, restored_replay, _ = SACLearner.load(path, experiment=EXPERIMENT, model_config=model_config(encoder),
                                                   config=config)
    assert restored_replay._digests == {}                      # the digests are disposable, never saved
    assert restored_replay.update_learner(restored, 4) == expected
    assert_same_learner_state(original, restored)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
@pytest.mark.parametrize('gamma', [0.0, .99])
def test_lent_replay_updates_equal_copied_ones_and_never_change_the_replay(encoder, gamma, transitions):
    """update_learner draws what sample() draws (same generator, items, order) but lends the stored transitions instead
    of deep-copying them: same updates and states over ring wraparound and eviction; the replay is bit-identical."""
    torch.manual_seed(3)
    copied = learner(encoder, config=SACConfig(gamma=gamma))
    torch.manual_seed(3)
    lent = learner(encoder, config=SACConfig(gamma=gamma))
    replays = [ReplayBuffer(capacity=4, origin='synthetic', seed=31) for _ in range(2)]
    for _ in range(2):                                          # 12 admissions into a ring of 4: wraparound + eviction
        for transition in transitions:
            for replay in replays:
                replay.add(transition)
            if len(replays[0]) < 2:
                continue
            fingerprints = [t.fingerprint() for t in replays[1]._items]
            before = torch.get_rng_state()
            expected = copied.update(replays[0].sample(2))
            after = torch.get_rng_state()
            torch.set_rng_state(before)
            assert replays[1].update_learner(lent, 2) == expected
            assert torch.equal(torch.get_rng_state(), after)
            assert replays[0]._rng.getstate() == replays[1]._rng.getstate()
            assert [t.fingerprint() for t in replays[1]._items] == fingerprints
            assert set(replays[1]._digests) <= {id(t) for t in replays[1]._items}   # evicted entries are dropped
    assert_same_learner_state(copied, lent)
    assert lent.input_cache.info()['hits'] > 0
