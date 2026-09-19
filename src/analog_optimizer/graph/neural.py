"""Model-independent tensor views of M1 graphs, without losing port/group identity.

The original HeteroData remains the canonical typed view. This module supplies
fixed semantic feature columns for ordinary PyG convolutions and dense nodes.
It has no dependency on sizing observations, rewards or a particular encoder.
"""
from __future__ import annotations

from copy import deepcopy

import torch
from torch.nn import functional as F
from torch_geometric.data import Batch, Data
from torch_geometric.utils import to_dense_batch

from .pyg_converter import FeatureSchema, GraphMetadata, to_pyg


NEURAL_TENSOR_VERSION = 'circuit-neural-v1'
GROUP_FIELDS = ('group_x', 'group_mask', 'group_mutable', 'group_kind',
                'group_member_index', 'group_member_parameter', 'group_member_ratio')


def node_feature_slices(schema=None):
    """Column layout independent of circuit size, node ordering and encoder."""
    schema = schema or FeatureSchema()
    widths = dict(node_type=2, device_kind=len(schema.device_kinds),
                  parameter_value=len(schema.parameters), parameter_valid=len(schema.parameters),
                  parameter_present=len(schema.parameters), optimizable=len(schema.parameters),
                  net_role=len(schema.net_roles))
    result, start = {}, 0
    for key, width in widths.items():
        result[key] = slice(start, start + width)
        start += width
    return result


def _schema(data):
    metadata = data.graph_metadata
    entries = metadata if isinstance(metadata, list) else [metadata]
    if not entries or any(not isinstance(item, GraphMetadata) for item in entries):
        raise ValueError('Circuit graph metadata required')
    schema = entries[0].schema
    if any(item.schema != schema for item in entries):
        raise ValueError('Cannot mix feature schemas in one neural batch')
    return schema


def port_edge_tensors(data):
    """Single graph OR HeteroData batch, ordered devices then nets.

    relation_id = 2 * terminal_role_id + direction, direction 0=device→net.
    No coalescing: parallel S/B connections and reverse edges stay distinct.
    This is also the edge-packing implementation used by the SAC input adapter.
    """
    schema = _schema(data)
    nd = data['device'].num_nodes
    edges, roles, ordinals = [], [], []
    for role_id, role in enumerate(schema.terminal_roles):
        for direction, key in enumerate((('device', f'{role}_to_net', 'net'),
                                         ('net', f'net_to_{role}', 'device'))):
            store = data[key]
            index = store.edge_index.clone()
            index[1 if direction == 0 else 0] += nd
            edges.append(index)
            roles.append(index.new_full((index.shape[1],), 2 * role_id + direction))
            ordinals.append(store.terminal_ordinal)
    return torch.cat(edges, dim=1), torch.cat(roles), torch.cat(ordinals)


class CircuitData(Data):
    """Homogeneous node IDs; group IDs have their own batch offset."""
    def __cat_dim__(self, key, value, *args, **kwargs):
        if key == 'group_member_index':
            return 1
        return super().__cat_dim__(key, value, *args, **kwargs)

    def __inc__(self, key, value, *args, **kwargs):
        if key == 'group_member_index':
            return value.new_tensor([[self.group_x.shape[0]], [self.num_nodes]])
        return super().__inc__(key, value, *args, **kwargs)


def as_homogeneous(data):
    """Convert one M1 HeteroData; batch AFTER conversion to keep nodes contiguous.

    Missing/type-inapplicable values are zero with explicit type/presence/validity
    columns. Raw IDs/model names stay in metadata, never in learned features.
    """
    if isinstance(data, Batch):
        raise ValueError('Convert individual graphs before batch_homogeneous')
    schema = _schema(data)
    nd, nn = data['device'].num_nodes, data['net'].num_nodes
    layout = node_feature_slices(schema)
    x = data['device'].x.new_zeros((nd + nn, layout['net_role'].stop))
    node_type = torch.cat((x.new_zeros(nd, dtype=torch.long), x.new_ones(nn, dtype=torch.long)))
    x[:, layout['node_type']] = F.one_hot(node_type, 2).to(x.dtype)
    x[:nd, layout['device_kind']] = F.one_hot(data['device'].kind, len(schema.device_kinds)).to(x.dtype)
    for column, field in (('parameter_value', 'x'), ('parameter_valid', 'parameter_mask'),
                           ('parameter_present', 'parameter_present'), ('optimizable', 'optimizable_mask')):
        x[:nd, layout[column]] = data['device'][field].to(x.dtype)
    x[nd:, layout['net_role']] = data['net'].x
    index, edge_type, ordinal = port_edge_tensors(data)
    edge_attr = torch.cat((F.one_hot(edge_type, 2 * len(schema.terminal_roles)).to(x.dtype),
                           ordinal.to(x.dtype).log1p()[:, None]), dim=-1)
    result = CircuitData(x=x, node_type=node_type, edge_index=index, edge_type=edge_type,
                         edge_attr=edge_attr, edge_ordinal=ordinal.clone(),
                         edge_weight=x.new_ones(index.shape[1]), num_nodes=nd + nn)
    for field in GROUP_FIELDS:
        result[field] = data[field].clone()
    result.graph_metadata = deepcopy(data.graph_metadata)
    result.tensor_schema = NEURAL_TENSOR_VERSION
    validate_neural_data(result)
    return result


def to_homogeneous_pyg(graph, schema=None, *, allow_incomplete=False):
    """CircuitGraph → fixed-width CircuitData, no RL observation required."""
    return as_homogeneous(to_pyg(graph, schema, allow_incomplete=allow_incomplete))


def validate_neural_data(data):
    """Reject ambiguous schemas, malformed shapes and cross-graph bindings."""
    data.validate(raise_on_error=True)
    schema = _schema(data)
    version = data.tensor_schema
    versions = version if isinstance(version, list) else [version]
    if any(v != NEURAL_TENSOR_VERSION for v in versions):
        raise ValueError('Unsupported neural tensor schema')
    n, e, g = data.num_nodes, data.edge_index.shape[1], data.group_x.shape[0]
    width = node_feature_slices(schema)['net_role'].stop
    relations = 2 * len(schema.terminal_roles)
    expected = {'x': (n, width), 'node_type': (n,), 'edge_index': (2, e),
                'edge_type': (e,), 'edge_ordinal': (e,), 'edge_attr': (e, relations + 1),
                'edge_weight': (e,), 'group_x': (g, 3), 'group_kind': (g,),
                'group_mask': (g,), 'group_mutable': (g,)}
    for key, shape in expected.items():
        value = data[key]
        if tuple(value.shape) != shape or not torch.isfinite(value).all():
            raise ValueError(f'Invalid neural tensor shape/values: {key}')
    for key in ('node_type', 'edge_index', 'edge_type', 'edge_ordinal', 'group_member_index',
                'group_kind', 'group_member_parameter'):
        if data[key].dtype != torch.long:
            raise ValueError(f'Expected int64 indices: {key}')
    if data.x.dtype != torch.float32 or data.edge_attr.dtype != torch.float32 or data.edge_weight.dtype != torch.float32:
        raise ValueError('Neural floating features must be float32')
    if ((data.node_type < 0) | (data.node_type > 1)).any():
        raise ValueError('Invalid neural node type')
    if ((data.edge_type < 0) | (data.edge_type >= relations)).any() or (data.edge_ordinal < 0).any():
        raise ValueError('Invalid port relation or ordinal')
    if (data.edge_weight < 0).any():
        raise ValueError('Edge weights must be nonnegative')
    source, target = data.edge_index
    if not torch.equal(data.node_type[source], data.edge_type % 2) or not torch.equal(
            data.node_type[target], 1 - data.edge_type % 2):
        raise ValueError('Port direction disagrees with node types')
    expected_attr = torch.cat((F.one_hot(data.edge_type, relations).to(data.x.dtype),
                               data.edge_ordinal.to(data.x.dtype).log1p()[:, None]), dim=-1)
    if not torch.equal(data.edge_attr, expected_attr):
        raise ValueError('Port attributes disagree with relation/ordinal')
    bindings = data.group_member_index
    if bindings.ndim != 2 or bindings.shape[0] != 2:
        raise ValueError('Invalid group member index shape')
    group, member = bindings
    if ((group < 0) | (group >= g)).any() or ((member < 0) | (member >= n)).any():
        raise ValueError('Group member index out of range')
    if (data.node_type[member] != 0).any():
        raise ValueError('Parameter group must bind to a device')
    for key in ('group_member_parameter', 'group_member_ratio'):
        if data[key].shape != group.shape or not torch.isfinite(data[key]).all():
            raise ValueError(f'Invalid group binding feature: {key}')
    if ((data.group_member_parameter < 0) | (data.group_member_parameter >= len(schema.parameters))).any():
        raise ValueError('Invalid binding parameter kind')
    if (data.group_member_ratio <= 0).any():
        raise ValueError('Binding ratios must be positive')
    if isinstance(data, Batch):
        if not torch.equal(data.batch[source], data.batch[target]):
            raise ValueError('Cross-graph neural edge')
        counts = data.x.new_tensor([len(m.group_ids) for m in data.graph_metadata], dtype=torch.long)
        group_batch = torch.repeat_interleave(torch.arange(data.num_graphs, device=data.x.device), counts)
        if not torch.equal(group_batch[group], data.batch[member]):
            raise ValueError('Cross-graph parameter group binding')
    return data


def batch_homogeneous(items):
    """Batch CircuitData with schema checks, node ptr and group_x_batch/ptr."""
    items = tuple(items)
    if not items:
        raise ValueError('Empty neural graph batch')
    for item in items:
        if isinstance(item, Batch) or not isinstance(item, CircuitData):
            raise ValueError('Expected individual CircuitData graphs')
        validate_neural_data(item)
    if any(_schema(item) != _schema(items[0]) for item in items):
        raise ValueError('Cannot mix feature schemas in one neural batch')
    return validate_neural_data(Batch.from_data_list(items, follow_batch=['group_x']))


def dense_node_features(data):
    """Return [B,Nmax,F] plus [B,Nmax] valid-node mask, without truncation.

    This view pads nodes, never action dimensions. Consumers must use the mask;
    flattening Nmax into a trainable layer does not support arbitrary topology.
    """
    validate_neural_data(data)
    if isinstance(data, Batch):
        return to_dense_batch(data.x, data.batch, batch_size=data.num_graphs)
    return data.x.unsqueeze(0), data.x.new_ones((1, data.num_nodes), dtype=torch.bool)
