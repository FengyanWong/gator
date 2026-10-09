"""The replay buffer: what it admits, its snapshot ring, its isolation from the objects it is given, its checkpoint bytes (refactoring package D4: from test_graph_sac)."""

from copy import deepcopy
from dataclasses import replace
import io

import pytest
torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.training.replay import ReplayBuffer

from research_support import deterministic_cpu, learner, transitions



@pytest.mark.parametrize('mode', ['parameters', 'proposal', 'reward', 'truncated', 'bootstrap', 'budget', 'goal', 'origin', 'pvt'])
def test_replay_rejects_invalid_transitions(transitions, mode):
    transition = transitions[0]
    if mode == 'parameters':
        transition = replace(transition, applied_parameters={})
    elif mode == 'proposal':
        transition = replace(transition, proposal={k: .99 for k in transition.proposal})
    elif mode == 'reward':
        transition = replace(transition, reward=123)
    elif mode == 'truncated':
        transition = replace(transition, truncated=True)
    elif mode == 'bootstrap':
        transition = replace(transition, bootstrap=False)
    elif mode == 'budget':
        transition = replace(transition, next_observation=replace(transition.next_observation, remaining_steps=0))
    elif mode == 'goal':
        next_obs = replace(transition.next_observation, specs=(MetricSpec('score', 'fixture', 'min', 1, lower=.1),))
        transition = replace(transition, next_observation=next_obs)
    elif mode == 'origin':
        transition = replace(transition, next_observation=replace(transition.next_observation, origin='real'))
    else:
        cond = SimulationCondition(PVTCorner('tt', 'tt', 27, 1), 'pvt_validation')
        transition = replace(transition, next_observation=replace(transition.next_observation, condition=cond))
    with pytest.raises(ValueError):
        ReplayBuffer(origin='synthetic').add(transition)


def test_replay_snapshot_ring_and_origin_separation(transitions):
    replay = ReplayBuffer(capacity=2, origin='synthetic', seed=42)
    for transition in transitions:
        replay.add(transition)
    assert len(replay) == 2 and replay.insertions == 6
    state = replay.state_dict()
    restored = ReplayBuffer.from_state_dict(state)
    assert [t.candidate_id for t in replay.sample(2)] == [t.candidate_id for t in restored.sample(2)]
    sample = replay.sample(1)[0]
    sample.proposal.clear()
    assert replay.sample(1)[0].proposal
    with pytest.raises(ValueError, match='mix'):
        ReplayBuffer(origin='real').add(transitions[0])


def test_replay_is_isolated_from_admitted_sampled_and_batched_objects(transitions):
    """Changing the admitted originals, a public sample's nested data, or a learner batch's tensors and metadata never
    reaches the stored transitions or a later lent update."""
    originals = deepcopy(transitions)
    replay = ReplayBuffer(origin='synthetic', seed=7)
    for transition in originals:
        replay.add(transition)
    fingerprints = [t.fingerprint() for t in replay._items]
    originals[0].proposal.clear()
    originals[1].observation.metrics['score'] = .1
    originals[2].next_observation.graph.metadata['new'] = ['changed']
    sample = replay.sample(3)
    sample[0].proposal.clear()
    sample[1].next_observation.metrics['score'] = .2
    group = sample[2].observation.graph.parameter_groups[0]
    sample[2].observation.graph.parameter_groups[0] = replace(group, value=group.value * 2)
    model = learner()
    batch = model.batch([t.observation for t in replay._items[:2]])
    for store in batch.graph.stores:
        for value in store.values():
            if isinstance(value, torch.Tensor):
                value.fill_(0)
    batch.graph.graph_metadata[0].source_metadata['nested'] = ['corrupted']
    for _ in range(3):
        replay.update_learner(model, 4)
    assert [t.fingerprint() for t in replay._items] == fingerprints


def test_the_replay_checkpoint_bytes_do_not_depend_on_the_copy():
    from analog_optimizer.training.replay import ReplayBuffer
    replay = ReplayBuffer(8, origin='synthetic')
    replay._items = [{'a': [1, 2.5, 'x'], 'b': {'c': (3, 4)}}, {'a': [5], 'b': {}}]
    copied, direct = io.BytesIO(), io.BytesIO()
    torch.save(dict(replay=replay.state_dict()), copied)
    torch.save(dict(replay=replay.state_dict(copy=False)), direct)
    assert copied.getvalue() == direct.getvalue()
    assert replay.state_dict()['items'] is not replay._items and replay.state_dict(copy=False)['items'] is replay._items
