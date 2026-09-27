"""M1 extraction to neural operators: semantics, batching, masks and gradients."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')
from torch_geometric.nn import GCNConv, GATv2Conv, RGCNConv, TransformerConv

from analog_optimizer.graph.neural import (
    as_homogeneous, batch_homogeneous, dense_node_features, node_feature_slices,
    port_edge_tensors, to_homogeneous_pyg, validate_neural_data)
from analog_optimizer.graph.pyg_converter import FeatureSchema, to_pyg
from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser


@pytest.fixture(autouse=True)
def cpu():
    threads = torch.get_num_threads()
    rng = torch.get_rng_state()
    torch.set_num_threads(1)
    torch.manual_seed(32)
    yield
    torch.set_num_threads(threads)
    torch.set_rng_state(rng)


def test_node_columns_preserve_types_masks_and_physical_zero(parser):
    graph = parser.parse_text('R (a 0) resistor r=unknown\nV (a 0) vsource dc=0')
    data = to_homogeneous_pyg(graph)
    schema, columns = FeatureSchema(), node_feature_slices()
    assert data.x.shape == (len(graph.devices) + len(graph.nets), 49)
    assert data.edge_attr.shape == (2 * len(graph.connections), 15)
    assert torch.isfinite(data.x).all() and torch.isfinite(data.edge_attr).all()
    r, dc, w = map(schema.parameters.index, ('r', 'dc', 'w'))
    assert data.x[0, columns['parameter_present']][r] == 1
    assert data.x[0, columns['parameter_valid']][r] == 0
    assert data.x[0, columns['parameter_present']][w] == 0
    assert data.x[1, columns['parameter_valid']][dc] == 1
    assert data.x[1, columns['parameter_value']][dc] == 0
    assert torch.equal(data.x[:2, columns['node_type']], torch.tensor([[1., 0.], [1., 0.]]))
    assert data.x[2:, columns['device_kind']].count_nonzero() == 0
    assert data.x[2:, columns['parameter_present']].count_nonzero() == 0
    assert data.x[:2, columns['net_role']].count_nonzero() == 0


def test_shared_bulk_source_and_reverse_ports_survive(parser):
    graph = parser.parse_text('Q (a g 0 0) nmos_demo w=1u l=200n')
    data = to_homogeneous_pyg(graph)
    schema = FeatureSchema()
    source, bulk = [2 * schema.terminal_roles.index(key) for key in ('source', 'bulk')]
    assert torch.equal(data.edge_index[:, data.edge_type == source], data.edge_index[:, data.edge_type == bulk])
    assert not torch.equal(data.edge_attr[data.edge_type == source], data.edge_attr[data.edge_type == bulk])
    for role in range(len(schema.terminal_roles)):
        a, b = data.edge_type == 2 * role, data.edge_type == 2 * role + 1
        assert torch.equal(data.edge_index[:, a].flip(0), data.edge_index[:, b])
        assert torch.equal(data.edge_ordinal[a], data.edge_ordinal[b])
    assert data.edge_index.shape == (2, 8)
    torch.testing.assert_close(data.edge_attr[:, -1], data.edge_ordinal.float().log1p())


def test_group_and_node_offsets_roundtrip_and_dense_mask(opamp, ldo, parser):
    graphs = (parser.parse_text('R (a 0) resistor r=1k'), opamp, ldo)
    items = [to_homogeneous_pyg(g) for g in graphs]
    batch = batch_homogeneous(items)
    assert torch.equal(batch.batch[batch.edge_index[0]], batch.batch[batch.edge_index[1]])
    group, member = batch.group_member_index
    assert torch.equal(batch.group_x_batch[group], batch.batch[member])
    assert (batch.node_type[member] == 0).all()
    assert batch.group_x_ptr.tolist() == [0, 0, 2, 3]
    offset = 0
    for i, item in enumerate(items):
        assert batch.ptr[i] == offset
        offset += item.num_nodes
    for before, after in zip(items, batch.to_data_list()):
        for key in ('x', 'edge_index', 'edge_type', 'edge_attr', 'edge_weight', 'edge_ordinal',
                    'group_x', 'group_member_index', 'group_kind', 'group_member_ratio'):
            assert torch.equal(before[key], after[key]), key
        assert before.graph_metadata == after.graph_metadata
        validate_neural_data(after)
    dense, mask = dense_node_features(batch)
    assert dense.shape == (3, max(d.num_nodes for d in items), 49)
    assert mask.dtype == torch.bool
    for i, item in enumerate(items):
        torch.testing.assert_close(dense[i, mask[i]], item.x)
        assert dense[i, ~mask[i]].count_nonzero() == 0


@pytest.mark.parametrize('operator', ['gcn', 'gatv2', 'rgcn', 'graph_transformer', 'mlp'])
def test_m1_tensors_feed_real_operators_forward_backward_and_batch(opamp, ldo, operator):
    root = Path(__file__).resolve().parents[1]
    graphs = [opamp, ldo]
    # Include a third circuit family, a larger topology and an existing real
    # exported netlist. Reading the real snapshot does not invoke Spectre.
    for config, source in (('synthetic', 'tests/fixtures/synthetic/vco.scs'),
                           ('opamp_two_stage', 'tests/fixtures/synthetic/opamp_two_stage.scs'),
                           ('gpdk045_opamp', 'examples/circuits/gpdk045_ota5.scs')):
        parser = SpectreParser(ParserConfig.from_file(root / f'configs/{config}.json'))
        graphs.append(parser.parse_file(root / source))
    items = [to_homogeneous_pyg(g) for g in graphs]
    batch = batch_homogeneous(items)
    width, edge_width = batch.x.shape[1], batch.edge_attr.shape[1]
    if operator == 'gcn':
        layer = GCNConv(width, 16, cached=False)
        apply = lambda d: layer(d.x, d.edge_index, d.edge_weight)
    elif operator == 'gatv2':
        layer = GATv2Conv(width, 8, heads=2, edge_dim=edge_width, add_self_loops=False)
        apply = lambda d: layer(d.x, d.edge_index, d.edge_attr)
    elif operator == 'rgcn':
        layer = RGCNConv(width, 16, 2 * len(FeatureSchema().terminal_roles))
        apply = lambda d: layer(d.x, d.edge_index, d.edge_type)
    elif operator == 'graph_transformer':
        layer = TransformerConv(width, 8, heads=2, edge_dim=edge_width)
        apply = lambda d: layer(d.x, d.edge_index, d.edge_attr)
    else:
        layer = torch.nn.Sequential(torch.nn.Linear(width, 16), torch.nn.SiLU(), torch.nn.Linear(16, 16))
        apply = lambda d: layer(d.x)
    batch.x.requires_grad_(True)
    output = apply(batch)
    assert output.shape == (batch.num_nodes, 16) and torch.isfinite(output).all()
    torch.testing.assert_close(output, torch.cat([apply(d) for d in items]), atol=2e-6, rtol=2e-5)
    output.square().mean().backward()
    assert torch.isfinite(batch.x.grad).all() and batch.x.grad.abs().sum() > 0
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in layer.parameters())
    assert sum(float(p.grad.abs().sum()) for p in layer.parameters() if p.grad is not None) > 0


def test_custom_schema_empty_and_unknown_graphs_keep_fixed_shapes(parser):
    schema = replace(FeatureSchema(), parameters=FeatureSchema().parameters + ('extra',),
                     references=FeatureSchema().references + (1.,))
    empty = to_homogeneous_pyg(parser.parse_text(''), schema)
    assert empty.x.shape == (0, 53) and empty.edge_attr.shape == (0, 15)
    assert empty.group_member_index.shape == (2, 0)
    unknown = parser.parse_text('X (a a b) mystery w=1u')
    with pytest.raises(ValueError, match='Incomplete'):
        to_homogeneous_pyg(unknown, schema)
    diagnostic = to_homogeneous_pyg(unknown, schema, allow_incomplete=True)
    assert sorted(diagnostic.edge_ordinal.tolist()) == [0, 0, 1, 1, 2, 2]
    batch = batch_homogeneous([empty, diagnostic, empty])
    dense, mask = dense_node_features(batch)
    assert dense.shape == (3, diagnostic.num_nodes, 53)
    assert mask[0].sum() == mask[2].sum() == 0
    assert mask[1].sum() == diagnostic.num_nodes
    all_empty, all_empty_mask = dense_node_features(batch_homogeneous([empty, empty]))
    assert all_empty.shape == (2, 0, 53) and all_empty_mask.shape == (2, 0)


def test_schema_mixing_and_cross_graph_corruption_fail(opamp, ldo):
    a, b = [to_homogeneous_pyg(g) for g in (opamp, ldo)]
    reordered = replace(FeatureSchema(), device_kinds=tuple(reversed(FeatureSchema().device_kinds)))
    with pytest.raises(ValueError, match='schemas'):
        batch_homogeneous([a, to_homogeneous_pyg(ldo, reordered)])
    batch = batch_homogeneous([a, b])
    changed = deepcopy(batch)
    # A device in the second graph is paired with a net in the first.
    changed.edge_index[0, 0] = batch.ptr[1]
    with pytest.raises(ValueError, match='Cross-graph'):
        validate_neural_data(changed)
    changed = deepcopy(batch)
    changed.group_member_index[1, 0] = batch.ptr[1]
    with pytest.raises(ValueError, match='Cross-graph'):
        validate_neural_data(changed)
    changed = deepcopy(a)
    changed.edge_type = changed.edge_type.float()
    with pytest.raises(ValueError, match='int64'):
        validate_neural_data(changed)
    changed = deepcopy(a)
    changed.edge_attr[0, 0] += 1
    with pytest.raises(ValueError, match='attributes'):
        validate_neural_data(changed)


def test_sac_uses_the_same_m1_edge_conversion(opamp):
    from analog_optimizer.envs.sizing import Observation
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.models.inputs import batch_observations
    obs = Observation(opamp, (MetricSpec('score', 'fixture', 'min', 1, lower=.95),),
                      {'score': .6}, {'score': True}, {'score': 'fixture'}, 'ok', 'synthetic', 4, 'fixture')
    model_batch = batch_observations([obs])
    exported = to_homogeneous_pyg(opamp)
    assert torch.equal(model_batch.edge_index, exported.edge_index)
    assert torch.equal(model_batch.edge_role, exported.edge_type)
    assert torch.equal(model_batch.edge_ordinal, exported.edge_ordinal)
    assert torch.equal(model_batch.graph.group_member_index, exported.group_member_index)
    packed = port_edge_tensors(model_batch.graph)
    assert torch.equal(packed[0], model_batch.edge_index)


def test_dynamic_size_refresh_and_metadata_isolation(opamp):
    typed = to_pyg(opamp)
    first = as_homogeneous(typed)
    first.graph_metadata.source_metadata['export_view_only'] = True
    assert 'export_view_only' not in typed.graph_metadata.source_metadata
    changed = deepcopy(opamp)
    for identifier in ('input_left', 'input_right'):
        changed.parameters[identifier]['w'] = replace(changed.parameters[identifier]['w'], value=3e-6)
    changed.parameter_groups[0] = replace(changed.parameter_groups[0], value=3e-6)
    second = to_homogeneous_pyg(changed)
    assert not torch.equal(first.x, second.x)
    assert torch.equal(first.edge_index, second.edge_index)
    assert torch.equal(first.edge_attr, second.edge_attr)


def test_node_reordering_renaming_preserves_features_and_operator(opamp):
    changed = deepcopy(opamp)
    devices = {d.id: f'd_{i}' for i, d in enumerate(changed.devices)}
    nets = {n.id: f'n_{i}' for i, n in enumerate(changed.nets)}
    changed.devices = [replace(d, id=devices[d.id]) for d in reversed(changed.devices)]
    changed.nets = [replace(n, id=nets[n.id]) for n in reversed(changed.nets)]
    changed.connections = [replace(c, device_id=devices[c.device_id], net_id=nets[c.net_id])
                           for c in reversed(changed.connections)]
    changed.parameters = {devices[k]: v for k, v in changed.parameters.items()}
    changed.parameter_groups = [replace(g, members=tuple(replace(m, device_id=devices[m.device_id])
                                                         for m in reversed(g.members)))
                                for g in changed.parameter_groups]
    before, after = to_homogeneous_pyg(opamp), to_homogeneous_pyg(changed)
    nd, nn = len(opamp.devices), len(opamp.nets)
    permutation = torch.cat((torch.arange(nd).flip(0), nd + torch.arange(nn).flip(0)))
    assert torch.equal(before.x, after.x[permutation])
    layer = GATv2Conv(before.x.shape[1], 8, edge_dim=before.edge_attr.shape[1], add_self_loops=False)
    torch.testing.assert_close(layer(before.x, before.edge_index, before.edge_attr),
                               layer(after.x, after.edge_index, after.edge_attr)[permutation],
                               atol=2e-6, rtol=2e-5)
