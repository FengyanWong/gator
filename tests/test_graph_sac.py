"""M4 behavioral acceptance: packed graphs, semantics, gradients and exact resume."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import math

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition, MonteCarloConfig
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv, Observation
from analog_optimizer.graph.pyg_converter import FeatureSchema
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.models.inputs import SpecSchema, batch_observations
from analog_optimizer.models.graph_transformer import ModelConfig, GroupActor, GraphCritic
from analog_optimizer.training.replay import Transition, ReplayBuffer
from analog_optimizer.training.sac import SACLearner, SACConfig, temperature_loss
from analog_optimizer.training.runner import collect_episode

MODEL = ModelConfig(hidden_dim=16, heads=2, layers=2)
EXPERIMENT = {'origin': 'synthetic', 'split': 'training-fixture', 'designs': ['opamp-v1', 'ldo-v1']}


@pytest.fixture(autouse=True)
def deterministic_cpu():
    threads = torch.get_num_threads()
    rng = torch.get_rng_state()
    torch.set_num_threads(1)
    torch.manual_seed(135)
    yield
    torch.set_num_threads(threads)
    torch.set_rng_state(rng)


def observation(graph, *, steps=4):
    return Observation(deepcopy(graph), (MetricSpec('score', 'fixture', 'min', 1, lower=.95),),
                       {'score': .6}, {'score': True}, {'score': 'fixture'}, 'ok', 'synthetic', steps, 'fixture')


@pytest.fixture
def transitions(opamp, ldo, tmp_path):
    result = []
    for graph in (opamp, ldo):
        backend = SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3})
        with CircuitSizingEnv(backend, graph, observation(graph).specs, tmp_path,
                              max_steps=3, stop_on_success=False, expected_origin='synthetic') as env:
            current, _ = env.reset()
            for value in (-.6, .2, .7):
                proposal = {g: value for g in env.mapper.group_ids}
                step = env.step(proposal)
                result.append(Transition.from_step(current, proposal, step))
                current = step[0]
        assert backend.parameters == backend.initial
    return result


def model_config(encoder):
    return ModelConfig(hidden_dim=16, heads=2, layers=2, encoder_type=encoder)


def learner(encoder='graph_transformer', **kwargs):
    return SACLearner(experiment=EXPERIMENT, model_config=model_config(encoder), **kwargs)


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


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_mixed_graph_batch_matches_individual_outputs(encoder, opamp, ldo):
    observations = [observation(g) for g in (opamp, ldo)]
    batch = batch_observations(observations)
    actor, critic = GroupActor(config=model_config(encoder)), GraphCritic(config=model_config(encoder))
    assert batch.action_counts.tolist() == [2, 1]
    assert torch.equal(batch.node_batch[batch.edge_index[0]], batch.node_batch[batch.edge_index[1]])
    assert torch.equal(batch.group_batch[batch.graph.group_member_index[0]],
                       batch.graph['device'].batch[batch.graph.group_member_index[1]])
    mu, std = actor.distribution(batch)
    individual = [actor.distribution(batch_observations([o])) for o in observations]
    torch.testing.assert_close(mu, torch.cat([x[0] for x in individual]))
    torch.testing.assert_close(std, torch.cat([x[1] for x in individual]))
    actions = torch.tensor([-.5, .8, .2])
    expected = torch.cat([critic(batch_observations([observations[0]]), actions[:2]),
                          critic(batch_observations([observations[1]]), actions[2:])])
    torch.testing.assert_close(critic(batch, actions), expected)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_nan_padding_discarded_before_q_and_gradient(encoder, opamp, ldo):
    batch = batch_observations([observation(opamp), observation(ldo)])
    critic = GraphCritic(config=model_config(encoder))
    padded = torch.tensor([[.2, .3, float('nan')], [.4, float('nan'), float('inf')]], requires_grad=True)
    packed = batch.pack_actions(padded)
    q = critic(batch, packed)
    torch.testing.assert_close(q, critic(batch, torch.tensor([.2, .3, .4])))
    q.sum().backward()
    assert torch.isfinite(padded.grad).all()
    assert padded.grad[0, 2] == padded.grad[1, 1] == padded.grad[1, 2] == 0
    assert padded.grad[0, :2].abs().sum() > 0 and padded.grad[1, 0].abs() > 0
    with pytest.raises(ValueError, match='finite'):
        batch.pack_actions(torch.full((2, 2), float('nan')))


def test_port_roles_affect_output_and_receive_gradients(opamp):
    batch = batch_observations([observation(opamp)])
    actor = GroupActor(config=MODEL)
    first = actor.distribution(batch)[0]
    changed = deepcopy(batch)
    # Swap gate/drain relations, retaining the same endpoints and edge count.
    role = changed.edge_role.clone()
    for a, b in ((2, 4), (3, 5)):
        changed.edge_role[role == a] = b
        changed.edge_role[role == b] = a
    second = actor.distribution(changed)[0]
    assert not torch.allclose(first, second, atol=1e-7, rtol=1e-7)
    first.sum().backward()
    assert actor.encoder.port_role.weight.grad.abs().sum() > 0
    assert actor.encoder.blocks[0].attention.lin_edge.weight.grad.abs().sum() > 0


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_renaming_node_group_and_member_permutation_is_equivariant(encoder, opamp):
    original = observation(opamp)
    changed = deepcopy(original.graph)
    devices = {d.id: f'renamed_{i}' for i, d in enumerate(changed.devices)}
    nets = {n.id: f'wire_{i}' for i, n in enumerate(changed.nets)}
    changed.devices = [replace(d, id=devices[d.id]) for d in reversed(changed.devices)]
    changed.nets = [replace(n, id=nets[n.id]) for n in reversed(changed.nets)]
    changed.connections = [replace(c, device_id=devices[c.device_id], net_id=nets[c.net_id])
                           for c in reversed(changed.connections)]
    changed.parameters = {devices[k]: v for k, v in changed.parameters.items()}
    changed.parameter_groups = [replace(g, id=f'group_{i}',
        members=tuple(replace(m, device_id=devices[m.device_id]) for m in reversed(g.members)))
        for i, g in enumerate(reversed(changed.parameter_groups))]
    before, after = batch_observations([original]), batch_observations([replace(original, graph=changed)])
    actor, critic = GroupActor(config=model_config(encoder)), GraphCritic(config=model_config(encoder))
    for a, b in zip(actor.distribution(before), actor.distribution(after)):
        torch.testing.assert_close(a, b.flip(0), atol=2e-6, rtol=2e-5)
    torch.testing.assert_close(critic(before, torch.tensor([-.4, .7])),
                               critic(after, torch.tensor([.7, -.4])), atol=2e-6, rtol=2e-5)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_group_binding_action_identity_and_independent_weights(encoder, opamp):
    batch = batch_observations([observation(opamp)])
    model = learner(encoder)
    weights = [{p.data_ptr() for p in module.parameters()} for module in
               (model.actor, model.critics[0], model.critics[1], model.targets[0], model.targets[1])]
    for i, a in enumerate(weights):
        assert all(not a.intersection(b) for b in weights[i + 1:])
    actions = torch.tensor([-.8, .9], requires_grad=True)
    q = model.critics[0](batch, actions)
    swapped = model.critics[0](batch, actions.flip(0))
    assert not torch.allclose(q, swapped, rtol=1e-6, atol=1e-7)
    q.sum().backward()
    assert torch.isfinite(actions.grad).all() and (actions.grad.abs() > 0).all()
    model.critics.zero_grad(set_to_none=True)
    sample = model.actor.sample(batch)
    model.critics[0](batch, sample.actions).sum().backward()
    assert model.actor.head[-1].weight.grad.abs().sum() > 0


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_log_prob_counts_groups_once_and_stays_finite_at_saturation(encoder, opamp, ldo):
    batch = batch_observations([observation(opamp), observation(ldo)])
    actor = GroupActor(config=model_config(encoder))
    mu, log_std = actor.distribution(batch)
    sample = actor.sample(batch, deterministic=True)
    per_dim = -.5 * math.log(2 * math.pi) - log_std - torch.log1p(-mu.tanh().square())
    torch.testing.assert_close(sample.log_prob, torch.stack((per_dim[:2].sum(), per_dim[2])))
    with torch.no_grad():
        actor.head[-1].weight.zero_()
        actor.head[-1].bias.copy_(torch.tensor([100., -5.]))
    saturated = actor.sample(batch)
    assert torch.isfinite(saturated.log_prob).all()
    saturated.log_prob.sum().backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in actor.parameters())


def test_fixed_groups_and_absent_measurements_do_not_create_actions(opamp):
    graph = deepcopy(opamp)
    graph.parameter_groups[1] = replace(graph.parameter_groups[1], mutable=False)
    first = observation(graph)
    first = replace(first, metrics={'score': None}, metric_validity={'score': False})
    second = replace(first, metrics={'score': float('nan')})
    a, b = batch_observations([first]), batch_observations([second])
    assert a.action_counts.tolist() == [1]
    torch.testing.assert_close(a.context, b.context)
    actor = GroupActor(config=MODEL)
    torch.testing.assert_close(actor.distribution(a)[0], actor.distribution(b)[0])
    graph.parameter_groups[0] = replace(graph.parameter_groups[0], mutable=False)
    with pytest.raises(ValueError, match='active action'):
        batch_observations([observation(graph)])


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_goal_validity_budget_and_dynamic_sizes_are_model_inputs(encoder, opamp, transitions):
    actor = GroupActor(config=model_config(encoder))
    initial = observation(opamp)
    variants = [replace(initial, remaining_steps=1),
                replace(initial, specs=(replace(initial.specs[0], lower=.8),)),
                replace(initial, metric_validity={'score': False})]
    before = actor.distribution(batch_observations([initial]))[0]
    for variant in variants:
        after = actor.distribution(batch_observations([variant]))[0]
        assert not torch.allclose(before, after, atol=1e-7, rtol=1e-7)
    changed = replace(initial, graph=transitions[0].next_observation.graph)
    assert not torch.allclose(before, actor.distribution(batch_observations([changed]))[0])


@pytest.mark.parametrize('mode', ['pvt', 'mc', 'real_missing_condition', 'unknown_metric', 'unit', 'invalid_validity'])
def test_bad_inputs_fail_explicitly(opamp, mode):
    obs = observation(opamp)
    if mode in ('pvt', 'mc'):
        cond = SimulationCondition(PVTCorner('tt', 'tt', 27, 1),
            'pvt_validation' if mode == 'pvt' else 'mc_validation',
            None if mode == 'pvt' else MonteCarloConfig(2, 3))
        obs = replace(obs, condition=cond)
    elif mode == 'real_missing_condition':
        obs = replace(obs, origin='real')
    elif mode == 'unknown_metric':
        obs = replace(obs, specs=(MetricSpec('mystery', 'V', 'min', 1, lower=1),))
    elif mode == 'unit':
        obs = replace(obs, specs=(MetricSpec('score', 'V', 'min', 1, lower=1),))
    else:
        obs = replace(obs, metrics={'score': float('nan')})
    with pytest.raises(ValueError):
        batch_observations([obs])


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


def test_inactive_spec_values_are_masked_and_graph_schema_is_checked(opamp):
    first = observation(opamp)
    inactive = MetricSpec('output_dc_v', 'V', 'min', 1, lower=1, active=False)
    a = replace(first, specs=first.specs + (inactive,))
    b = replace(first, specs=first.specs + (replace(inactive, lower=900, scale=100),),
                metrics={**first.metrics, 'output_dc_v': float('nan')})
    torch.testing.assert_close(batch_observations([a]).context, batch_observations([b]).context)
    graph = deepcopy(opamp)
    graph.schema_version = 'unsupported'
    with pytest.raises(ValueError, match='schema'):
        batch_observations([observation(graph)])


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_encoder_topology_and_port_ablation(opamp, encoder):
    batch = batch_observations([observation(opamp)])
    actor, critic = GroupActor(config=model_config(encoder)), GraphCritic(config=model_config(encoder))
    first = actor.distribution(batch)[0]
    actions = torch.tensor([-.4, .7])
    first_q = critic(batch, actions)
    changed = deepcopy(batch)
    role = changed.edge_role.clone()
    for a, b in ((2, 4), (3, 5)):
        changed.edge_role[role == a] = b
        changed.edge_role[role == b] = a
    second = actor.distribution(changed)[0]
    disconnected = deepcopy(batch)
    disconnected.edge_index = batch.edge_index[:, :0]
    disconnected.edge_role = batch.edge_role[:0]
    disconnected.edge_ordinal = batch.edge_ordinal[:0]
    assert not torch.allclose(first, second, atol=1e-7, rtol=1e-7)
    assert not torch.allclose(first_q, critic(changed, actions), atol=1e-7, rtol=1e-7)
    assert not torch.allclose(first, actor.distribution(disconnected)[0], atol=1e-7, rtol=1e-7)
    first.sum().backward()
    if encoder == 'rgcn':
        assert actor.encoder.blocks[0].message.weight.grad.abs().sum() > 0
    else:
        assert actor.encoder.port_role.weight.grad.abs().sum() > 0


def test_encoder_configuration_roundtrip_and_legacy_aliases():
    assert ModelConfig().encoder_type == 'graph_transformer'
    assert ENCODER_TYPES == ('graph_transformer', 'rgcn', 'gatv2')
    with pytest.raises(ValueError, match=r'gat \(GATv1\) was replaced by gatv2'):
        ModelConfig(encoder_type='gat')
    for removed in ('mlp', 'gcn'):
        with pytest.raises(ValueError, match=f'{removed} was removed from the optimizer on 2026-09-26'):
            ModelConfig(encoder_type=removed)
    for removed in (dict(attention_mode='port_message_passing'), dict(encoder_type='port_gnn')):
        with pytest.raises(ValueError, match='removed from the optimizer on 2026-09-24'):
            ModelConfig(**removed)                                    # the M5 port-GNN: refused by name, in words
    for encoder in ENCODER_TYPES:
        config = model_config(encoder)
        assert ModelConfig(**json.loads(json.dumps(asdict(config)))) == config
    for config in (dict(encoder_type='unknown'), dict(encoder_type=''),
                   dict(attention_mode='rgcn'), dict(encoder_type='rgcn', attention_mode='local_port_attention'),
                   dict(encoder_type='gatv2', hidden_dim=15, heads=2)):
        with pytest.raises(ValueError):
            ModelConfig(**config)
    assert ModelConfig(encoder_type='rgcn', hidden_dim=15, heads=2).hidden_dim == 15


@pytest.mark.parametrize('encoder', ['rgcn', 'gatv2'])
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
