"""Synthetic behavioral checks for the joint encoder and its versioned inputs."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest
import torch

from analog_optimizer.graph.pyg_converter import FeatureSchema, OPERATING_POINT_COLUMNS, OPERATING_POINT_REFERENCES
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ModelConfig, GroupActor, GraphCritic
from analog_optimizer.models.inputs import (SpecSetSchema, SPEC_PROGRAM_LAYOUT, batch_observations,
                                            spec_schema_from_dict, ObservationTensorCache)
from analog_optimizer.models.measurement_program import PROGRAM_KEY, BLOCK_KINDS
from analog_optimizer.models.circuit_gps import ProgramReader, distances
from analog_optimizer.training.sac import SACLearner
from research_support import observation, transitions, EXPERIMENT, deterministic_cpu  # noqa: F401

SCHEMA = SpecSetSchema('measurement-program-v1', (), (('V', 1.), ('fixture', 1.)), layout=SPEC_PROGRAM_LAYOUT)
MODEL = ModelConfig(encoder_type='circuit_gps', hidden_dim=16, heads=2, layers=2)


def test_tree_normalization_is_versioned_without_new_weights():
    assert MODEL.architecture_version == 2
    legacy = replace(MODEL, architecture_version=1)
    new = GroupActor(spec_schema=SCHEMA, config=MODEL)
    old = GroupActor(spec_schema=SCHEMA, config=legacy)
    new.load_state_dict(old.state_dict(), strict=True)
    assert new.encoder.blocks[0].program.normalize_tree
    assert not old.encoder.blocks[0].program.normalize_tree
    assert ModelConfig(**legacy.to_dict()) == legacy
    assert ModelConfig(**MODEL.to_dict()) == MODEL
    with pytest.raises(ValueError, match='architecture_version'):
        replace(MODEL, architecture_version=4)


@pytest.mark.parametrize('depth', [16, 64])
def test_deep_high_gain_program_has_finite_forward_and_gradients(opamp, depth):
    original = described(opamp)
    tree = original.graph.metadata[PROGRAM_KEY]['first']['children'][0]
    for _ in range(depth):
        tree = dict(op='add', children=[tree, dict(op='number', value=1.)])
    original.graph.metadata[PROGRAM_KEY]['first'] = tree
    packed = batch(original)
    torch.manual_seed(621)
    reader = ProgramReader(16)
    # Learned transforms can amplify even though all weights and inputs are finite.
    with torch.no_grad():
        for module in reader.modules():
            if isinstance(module, torch.nn.Linear):
                module.weight.mul_(20.)
    nodes = torch.randn(len(packed.node_batch), 16, requires_grad=True)
    output = reader(nodes, packed.structured)
    assert torch.isfinite(output).all()
    output[:, 0].sum().backward()
    assert torch.isfinite(nodes.grad).all()
    assert nodes.grad.abs().max() > 0
    assert all(torch.isfinite(p.grad).all() for p in reader.parameters() if p.grad is not None)
    legacy = ProgramReader(16, normalize_tree=False)
    legacy.load_state_dict(reader.state_dict())
    with torch.no_grad():
        assert not torch.isfinite(legacy(nodes.detach(), packed.structured)).all()


def described(graph):
    """Attach matching spec descriptors and distinct measured-net bindings to a copied observation."""
    original = observation(graph)
    graph = deepcopy(original.graph)
    specs = (MetricSpec('first', 'V', 'min', .1, lower=.2), MetricSpec('second', 'V', 'min', .1, lower=.8))
    # Intentionally same measured values and spec descriptors, distinct measured nets.
    nets = [n.id for n in graph.nets if n.id != '0']
    graph.metadata['spec_descriptors'] = {s.metric_id: () for s in specs}
    graph.metadata[PROGRAM_KEY] = {s.metric_id: dict(op='dc', children=[dict(op='voltage', bindings=[
        dict(kind='net', id=nets[i], role='voltage')])]) for i, s in enumerate(specs)}
    return replace(original, graph=graph, specs=specs, metrics={s.metric_id: .5 for s in specs},
                   metric_units={s.metric_id: 'V' for s in specs}, metric_validity={s.metric_id: True for s in specs})


def batch(*observations, **kwargs):
    """Batch observations under the structured spec schema shared by these tests."""
    return batch_observations(observations, spec_schema=SCHEMA, **kwargs)


def models():
    """Seed and build the actor and critic with the same structured input contract."""
    torch.manual_seed(724)
    return GroupActor(spec_schema=SCHEMA, config=MODEL), GraphCritic(spec_schema=SCHEMA, config=MODEL)


def _dense_normalized_program(reader, nodes, data):
    """Pre-acceleration v2 calculation: update every row, then select this height."""
    from analog_optimizer.models.encoders import segment_sum
    from torch.nn import functional as F
    base = reader.operation(data['op']) + reader.values(data['values'])
    tokens, ids = data['bindings']
    bound = reader.binding(torch.cat((nodes[ids], reader.binding_role(data['binding_role'])), -1))
    base = F.layer_norm(base + segment_sum(bound, tokens, len(base)), (nodes.shape[-1],))
    state = base
    child, parent = data['children']
    for height in range(1, int(data['height'].max()) + 1 if len(base) else 1):
        selected = data['height'][parent] == height
        slots = reader.slot(torch.log1p(data['slot'][selected])[:, None])
        messages = reader.child(torch.cat((state[child[selected]], slots), -1))
        summed = segment_sum(messages, parent[selected], len(base))
        updated = F.layer_norm(reader.combine(torch.cat((base, summed), -1)), (nodes.shape[-1],))
        state = torch.where((data['height'] == height)[:, None], updated, state)
    return reader.norm(state[data['roots']])


@pytest.mark.parametrize('depth', [0, 1, 17])
@pytest.mark.parametrize('dtype', [torch.float32, torch.float64])
def test_sparse_program_matches_dense_values_and_gradients(opamp, depth, dtype):
    a, b = described(opamp), described(opamp)
    tree = a.graph.metadata[PROGRAM_KEY]['first']['children'][0]
    # Unequal depths, an ordered branch, a leaf root, and multiple graph bindings.
    tree['bindings'].append(dict(tree['bindings'][0]))
    for _ in range(depth):
        tree = dict(op='sub', children=[dict(op='number', value=.25), tree])
    a.graph.metadata[PROGRAM_KEY]['first'] = tree
    a.graph.metadata[PROGRAM_KEY]['second'] = dict(op='number', value=.75)
    packed = batch(a, b)
    data = {k: v.to(dtype) if v.is_floating_point() else v for k, v in packed.structured.items()}
    torch.manual_seed(822)
    reader = ProgramReader(16).to(dtype)
    reference = deepcopy(reader)
    nodes = torch.randn(len(packed.node_batch), 16, dtype=dtype, requires_grad=True)
    other = nodes.detach().clone().requires_grad_()
    processed = []
    hook = reader.combine.register_forward_pre_hook(lambda module, args: processed.append(len(args[0])))
    actual = reader(nodes, data)
    hook.remove()
    expected = _dense_normalized_program(reference, other, data)
    tol = dict(atol=2e-6, rtol=2e-5) if dtype == torch.float32 else dict(atol=1e-12, rtol=1e-11)
    torch.testing.assert_close(actual, expected, **tol)
    weights = torch.randn_like(actual)
    (actual * weights).sum().backward()
    (expected * weights).sum().backward()
    torch.testing.assert_close(nodes.grad, other.grad, **tol)
    for p, q in zip(reader.parameters(), reference.parameters(), strict=True):
        assert (p.grad is None) == (q.grad is None)
        if p.grad is not None:
            torch.testing.assert_close(p.grad, q.grad, **tol)
    assert sum(processed) == int((data['height'] > 0).sum())


def test_binding_swap_breaks_the_old_spec_pooling_collision(opamp):
    original = described(opamp)
    changed = deepcopy(original)
    programs = changed.graph.metadata[PROGRAM_KEY]
    programs['first'], programs['second'] = programs['second'], programs['first']
    a, b = batch(original), batch(changed)
    torch.testing.assert_close(a.spec_items, b.spec_items)
    actor, critic = models()
    assert (actor.distribution(a)[0] - actor.distribution(b)[0]).abs().max() > 1e-6
    action = torch.tensor([-.3, .7])
    assert (critic(a, action) - critic(b, action)).abs().max() > 1e-7


def test_explicit_scale_and_both_range_margins(opamp):
    original = described(opamp)
    original = replace(original, specs=(replace(original.specs[0], lower=.5),))
    changed = replace(original, specs=(replace(original.specs[0], scale=1.),))
    a, b = batch(original), batch(changed)
    torch.testing.assert_close(a.spec_items[:, :-4], b.spec_items[:, :-4])
    assert a.spec_items[0, -4] != b.spec_items[0, -4]
    ranged = replace(original, specs=(replace(original.specs[0], comparator='range', lower=.2, upper=.7),))
    item = batch(ranged).spec_items[0]
    torch.testing.assert_close(item[-2:], torch.log1p(torch.tensor([3., 2.])))
    actor, _ = models()
    assert not torch.allclose(actor.distribution(a)[0], actor.distribution(b)[0])


def test_program_operators_operand_order_and_constants_reach_the_actor(opamp):
    original = described(opamp)
    actor, _ = models()
    outputs = []
    for op, reverse, constant in [('div', False, 1e-9), ('div', True, 1e-9), ('mul', False, 1e-9), ('div', False, 2e-9)]:
        changed = deepcopy(original)
        child = changed.graph.metadata[PROGRAM_KEY]['first']
        children = [child, dict(op='number', value=constant)]
        changed.graph.metadata[PROGRAM_KEY]['first'] = dict(op=op, children=children[::-1] if reverse else children)
        outputs.append(actor.distribution(batch(changed))[0])
    for i, out in enumerate(outputs):
        assert all(not torch.allclose(out, other, atol=1e-7, rtol=1e-7) for other in outputs[i + 1:])


def test_joint_batch_isolation_missing_specs_and_invalid_measurements(opamp, ldo):
    a, b = described(opamp), described(ldo)
    b = replace(b, specs=(b.specs[0], replace(b.specs[1], active=False)),
                metrics={}, metric_validity={'first': False, 'second': False})
    a = replace(a, metrics=dict(a.metrics, first=float('nan')), metric_validity=dict(a.metric_validity, first=False))
    together = batch(a, b)
    assert together.spec_items.shape[0] == 3 and together.spec_items[0, 12] == 0
    actor, critic = models()
    expected = torch.cat([actor.distribution(batch(o))[0] for o in (a, b)])
    torch.testing.assert_close(actor.distribution(together)[0], expected, atol=2e-6, rtol=2e-5)
    proposed = torch.tensor([.1, -.5, .3], requires_grad=True)
    q = critic(together, proposed)
    separate = torch.cat((critic(batch(a), proposed[:2]), critic(batch(b), proposed[2:])))
    torch.testing.assert_close(q, separate, atol=2e-6, rtol=2e-5)
    q[0].backward()
    assert torch.isfinite(proposed.grad).all() and proposed.grad[:2].abs().min() > 0
    assert proposed.grad[2] == 0
    assert torch.isfinite(actor.sample(together).log_prob).all()


def test_graph_parameter_spec_renaming_and_permutation(opamp):
    original = described(opamp)
    changed = deepcopy(original)
    graph = changed.graph
    devices = {d.id: f'd{i}' for i, d in enumerate(graph.devices)}
    nets = {n.id: f'n{i}' for i, n in enumerate(graph.nets)}
    graph.devices = [replace(d, id=devices[d.id]) for d in reversed(graph.devices)]
    graph.nets = [replace(n, id=nets[n.id]) for n in reversed(graph.nets)]
    graph.connections = [replace(c, device_id=devices[c.device_id], net_id=nets[c.net_id]) for c in reversed(graph.connections)]
    graph.parameters = {devices[k]: v for k, v in graph.parameters.items()}
    graph.parameter_groups = [replace(g, id=f'g{i}', members=tuple(replace(m, device_id=devices[m.device_id]) for m in reversed(g.members)))
                              for i, g in enumerate(reversed(graph.parameter_groups))]
    for program in graph.metadata[PROGRAM_KEY].values():
        binding = program['children'][0]['bindings'][0]
        binding['id'] = nets[binding['id']]
    names = {'first': 'renamed_b', 'second': 'renamed_a'}
    for key in ('spec_descriptors', PROGRAM_KEY):
        graph.metadata[key] = {names[k]: v for k, v in graph.metadata[key].items()}
    changed = replace(changed, specs=tuple(replace(s, metric_id=names[s.metric_id]) for s in reversed(changed.specs)),
                      metrics={names[k]: v for k, v in changed.metrics.items()},
                      metric_units={names[k]: v for k, v in changed.metric_units.items()},
                      metric_validity={names[k]: v for k, v in changed.metric_validity.items()})
    actor, critic = models()
    a, b = batch(original), batch(changed)
    for x, y in zip(actor.distribution(a), actor.distribution(b)):
        torch.testing.assert_close(x, y.flip(0), atol=2e-6, rtol=2e-5)
    torch.testing.assert_close(critic(a, torch.tensor([-.5, .3])), critic(b, torch.tensor([.3, -.5])), atol=2e-6, rtol=2e-5)


def test_raw_cache_binding_invalidation_physics_masks_and_immutable_reads(opamp):
    original = described(opamp)
    device = opamp.devices[0].id
    original = replace(original, operating_points={device: dict(ids=0., gm=.002, gds=.0001, vgs=.7, vth=.4, vds=.5, vdsat=.2)})
    feature = replace(FeatureSchema(), op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES)
    cache = ObservationTensorCache(capacity=4)
    first = batch(original, cache=cache, feature_schema=feature)
    assert first.structured['physics'][0, 5:].tolist() == [0., 1., 1., 1., 1.]
    assert torch.isfinite(first.structured['physics']).all()
    before = first.structured['bindings'].clone()
    first.structured['bindings'].zero_()
    torch.testing.assert_close(batch(original, cache=cache, feature_schema=feature).structured['bindings'], before)
    assert cache.info()['hits'] == 1 and cache.info()['tensor_bytes'] > 0
    changed = deepcopy(original)
    changed.graph.metadata[PROGRAM_KEY]['first']['children'][0]['bindings'][0]['id'] = 'unresolved'
    other = batch(changed, cache=cache, feature_schema=feature)
    assert cache.info()['misses'] == 2 and other.structured['bindings'].shape[1] == before.shape[1] - 1
    # Unresolved addresses retain a request count and a separate validity channel.
    assert (other.structured['values'][:, 4] > 0).any()
    assert (other.structured['values'][:, 5] == 0).any()


def test_structural_distance_distinguishes_disconnected_and_is_equivariant():
    edges = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]])
    expected = torch.tensor([[0, 1, 2, 9], [1, 0, 1, 9], [2, 1, 0, 9], [9, 9, 9, 0]])
    torch.testing.assert_close(distances(4, edges), expected)
    permutation = torch.tensor([2, 0, 3, 1])
    torch.testing.assert_close(distances(4, permutation[edges])[permutation][:, permutation], expected)


def test_unknown_program_is_explicit_and_schema_roundtrips(opamp):
    assert spec_schema_from_dict(asdict(SCHEMA)) == SCHEMA
    original = described(opamp)
    original.graph.metadata[PROGRAM_KEY]['first'] = dict(op='unknown')
    packed = batch(original)
    assert packed.structured['values'][0, 3] == 0
    del original.graph.metadata[PROGRAM_KEY]['first']
    with pytest.raises(ValueError, match='Missing measurement program'):
        batch(original)


def test_hierarchy_uses_electrical_motifs_and_explicit_members(opamp):
    original = described(opamp)
    kinds = batch(original).structured['block_kind'].tolist()
    assert BLOCK_KINDS.index('shared_source_pair') in kinds
    grounded = deepcopy(original)
    grounded.graph.connections = [replace(c, net_id='0') if c.role == 'source' and c.device_id.startswith('input_') else c
                                   for c in grounded.graph.connections]
    assert BLOCK_KINDS.index('shared_source_pair') not in batch(grounded).structured['block_kind'].tolist()
    original.graph.metadata['functional_blocks'] = [dict(kind='gain_stage', members=['input_left', 'input_right'])]
    assert BLOCK_KINDS.index('gain_stage') in batch(original).structured['block_kind'].tolist()
    original.graph.metadata['functional_blocks'][0]['members'] = ['missing_device']
    with pytest.raises(ValueError, match='Unknown device'):
        batch(original)


def test_structured_sac_update_checkpoint_restores_next_update(tmp_path, transitions):
    from analog_optimizer.training.replay import ReplayBuffer
    torch.manual_seed(13)
    learner = SACLearner(experiment=EXPERIMENT, spec_schema=SCHEMA, model_config=MODEL)
    replay = ReplayBuffer(10, origin='synthetic')
    def decorate(obs):
        """Add minimal analyzer programs and empty spec descriptors to replay observations."""
        graph = deepcopy(obs.graph)
        graph.metadata['spec_descriptors'] = {s.metric_id: () for s in obs.specs}
        graph.metadata[PROGRAM_KEY] = {s.metric_id: dict(op='analyzer', children=[dict(op='unknown')]) for s in obs.specs}
        return replace(obs, graph=graph)
    for transition in transitions:
        replay.add(replace(transition, observation=decorate(transition.observation),
                           next_observation=decorate(transition.next_observation)))
    replay.update_learner(learner, 2)
    path = tmp_path / 'joint.pt'
    learner.save(path, replay=replay)
    expected = replay.update_learner(learner, 2)
    restored, restored_replay, _ = SACLearner.load(path, experiment=EXPERIMENT, spec_schema=SCHEMA, model_config=MODEL)
    actual = restored_replay.update_learner(restored, 2)
    assert actual == expected
    for key, value in learner.actor.state_dict().items():
        torch.testing.assert_close(value, restored.actor.state_dict()[key], rtol=0, atol=0)


V3 = replace(MODEL, architecture_version=3)


def test_v3_keeps_v2_weights_and_changes_only_aggregation(opamp):
    old = GroupActor(spec_schema=SCHEMA, config=MODEL)
    new = GroupActor(spec_schema=SCHEMA, config=V3)
    new.load_state_dict(old.state_dict(), strict=True)
    assert new.encoder.blocks[0].program.mean_bindings and not old.encoder.blocks[0].program.mean_bindings
    assert ModelConfig(**V3.to_dict()) == V3 and ModelConfig(**MODEL.to_dict()).architecture_version == 2
    observed = batch(described(opamp))
    assert not torch.allclose(old.distribution(observed)[0], new.distribution(observed)[0])


def test_v3_readout_pools_are_means_of_the_final_tokens(opamp, ldo):
    from analog_optimizer.models.encoders import segment_mean
    torch.manual_seed(5)
    actor = GroupActor(spec_schema=SCHEMA, config=V3)
    together = batch(described(opamp), described(ldo))
    captured = {}
    handle = actor.encoder.readout_output.register_forward_pre_hook(lambda module, inputs: captured.update(x=inputs[0]))
    nodes, groups, context = actor.encoder(together)
    handle.remove()
    h = V3.hidden_dim
    torch.testing.assert_close(captured['x'][:, h:2 * h], segment_mean(nodes, together.node_batch, together.size))
    torch.testing.assert_close(captured['x'][:, 2 * h:3 * h], segment_mean(groups, together.group_batch, together.size))
    # Averages of normalized rows stay within the rows' own range, whatever the circuit size.
    assert captured['x'][:, h:3 * h].abs().max() <= max(nodes.abs().max(), groups.abs().max()) + 1e-6
    assert torch.isfinite(context).all()


def test_v3_program_bindings_average_repeated_references():
    torch.manual_seed(3)
    h = 8
    summed, averaged = ProgramReader(h), ProgramReader(h, mean_bindings=True)
    averaged.load_state_dict(summed.state_dict(), strict=True)
    nodes = torch.randn(1, h).repeat(8, 1)

    def program(k):
        """Build a single-node packed program with the requested number of bindings."""
        return {'op': torch.zeros(1, dtype=torch.long), 'values': torch.zeros(1, 6),
                'bindings': (torch.zeros(k, dtype=torch.long), torch.arange(k)),
                'binding_role': torch.zeros(k, dtype=torch.long),
                'children': torch.zeros((2, 0), dtype=torch.long), 'height': torch.zeros(1, dtype=torch.long),
                'slot': torch.zeros(0), 'roots': torch.zeros(1, dtype=torch.long)}
    torch.testing.assert_close(averaged(nodes, program(1)), averaged(nodes, program(8)))
    assert not torch.allclose(summed(nodes, program(1)), summed(nodes, program(8)))
