"""M4 behavioral acceptance: packed graphs, semantics, gradients and exact resume."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
import math

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition, MonteCarloConfig
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ENCODER_TYPES
from analog_optimizer.models.inputs import batch_observations
from analog_optimizer.models.graph_transformer import ModelConfig, GroupActor, GraphCritic
from research_support import deterministic_cpu, EXPERIMENT, learner, MODEL, model_config, observation, transitions


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
    assert ENCODER_TYPES == ('graph_transformer', 'rgcn', 'gatv2', 'graph_gps', 'group_cross_attention', 'circuit_gps')
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


