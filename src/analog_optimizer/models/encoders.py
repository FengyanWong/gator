"""Interchangeable circuit encoders with a common node/group/context contract."""
from __future__ import annotations

from dataclasses import dataclass
import math

import torch
from torch import nn
from torch_geometric.nn import TransformerConv, RGCNConv, GATv2Conv


ENCODER_TYPES = ('graph_transformer', 'rgcn', 'gatv2')
LEGACY_MODES = {'local_port_attention': 'graph_transformer'}
# Encoders that existed and were removed. Naming one is refused in words: the models trained with it load only from
# the last source commit that still has it (the checkpoint contract pins the source digest).
REMOVED_ENCODERS = {'port_gnn': 'port_gnn (legacy attention_mode port_message_passing) was removed from the optimizer '
                                'on 2026-09-24: it answered the same question as rgcn (edge-typed message passing '
                                'without attention) and had no published reference. Models trained with it load only '
                                'from source commit bbdfe36 (source digest 02127bc3...).',
                    'gat': 'gat (GATv1) was replaced by gatv2 on 2026-09-26. Select gatv2 for new training; '
                           'GATv1 weights cannot be loaded into GATv2. Use the historical source matching '
                           'the checkpoint for GATv1 runs.',
                    **{name: f'{name} was removed from the optimizer on 2026-09-26 by user request. '
                             'Choose graph_transformer, rgcn or gatv2. Use the historical source matching the checkpoint; '
                             'the last five-encoder version is commit 9bc488f (source digest aa987cf0...).'
                       for name in ('mlp', 'gcn')}}
REMOVED_LEGACY_MODES = {'port_message_passing': 'port_gnn'}


@dataclass(frozen=True)
class ModelConfig:
    hidden_dim: int = 64
    heads: int = 4
    layers: int = 2
    attention_mode: str | None = None  # Compatibility alias for M4/M5 callers.
    log_std_min: float = -5.0
    log_std_max: float = 2.0
    encoder_type: str | None = None  # Resolved to graph_transformer by default.

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in (self.hidden_dim, self.heads, self.layers)):
            raise ValueError('Model sizes must be positive integers')
        removed = REMOVED_ENCODERS.get(self.encoder_type) or REMOVED_ENCODERS.get(REMOVED_LEGACY_MODES.get(self.attention_mode))
        if removed:
            raise ValueError(removed)
        legacy = None
        if self.attention_mode is not None:
            if self.attention_mode not in LEGACY_MODES:
                raise ValueError('Unsupported attention_mode; select encoder_type instead')
            legacy = LEGACY_MODES[self.attention_mode]
        encoder = self.encoder_type if self.encoder_type is not None else (legacy or 'graph_transformer')
        if encoder not in ENCODER_TYPES:
            raise ValueError(f'Unsupported encoder_type: {encoder}')
        if legacy is not None and legacy != encoder:
            raise ValueError('encoder_type conflicts with legacy attention_mode')
        if encoder in ('graph_transformer', 'gatv2') and self.hidden_dim % self.heads:
            raise ValueError('Attention hidden_dim must be divisible by heads')
        object.__setattr__(self, 'encoder_type', encoder)
        object.__setattr__(self, 'attention_mode', next((k for k, v in LEGACY_MODES.items() if v == encoder), None))
        if not math.isfinite(self.log_std_min + self.log_std_max) or not -20 <= self.log_std_min < self.log_std_max <= 2:
            raise ValueError('Invalid log standard deviation limits')


def segment_sum(values, index, count):
    return values.new_zeros((count,) + values.shape[1:]).index_add(0, index, values)


def segment_mean(values, index, count):
    total = segment_sum(values, index, count)
    sizes = torch.bincount(index, minlength=count).clamp_min(1).to(values.dtype)
    return total / sizes.reshape((-1,) + (1,) * (values.ndim - 1))


def mlp(inputs, hidden, outputs):
    return nn.Sequential(nn.Linear(inputs, hidden), nn.SiLU(), nn.Linear(hidden, outputs))


class PortAttentionBlock(nn.Module):
    def __init__(self, config):
        super().__init__()
        h = config.hidden_dim
        self.norm_attention = nn.LayerNorm(h)
        self.attention = TransformerConv(h, h // config.heads, heads=config.heads,
                                         edge_dim=h, dropout=0, root_weight=False)
        self.norm_ff = nn.LayerNorm(h)
        self.ff = mlp(h, 2 * h, h)

    def forward(self, nodes, edges, edge_features, edge_role):
        nodes = nodes + self.attention(self.norm_attention(nodes), edges, edge_features)
        return nodes + self.ff(self.norm_ff(nodes))


class PortRGCNBlock(nn.Module):
    """One relation per terminal role and direction; no node ID embeddings."""
    def __init__(self, config, num_relations):
        super().__init__()
        h = config.hidden_dim
        self.norm_message = nn.LayerNorm(h)
        self.message = RGCNConv(h, h, num_relations, aggr='mean', root_weight=False)
        self.norm_ff = nn.LayerNorm(h)
        self.ff = mlp(h, 2 * h, h)

    def forward(self, nodes, edges, edge_features, edge_role):
        nodes = nodes + self.message(self.norm_message(nodes), edges, edge_role)
        return nodes + self.ff(self.norm_ff(nodes))


class PortGATv2Block(nn.Module):
    """Dynamic GATv2 attention with port features, real edges and a residual."""
    def __init__(self, config):
        super().__init__()
        h = config.hidden_dim
        self.norm_attention = nn.LayerNorm(h)
        self.attention = GATv2Conv(h, h // config.heads, heads=config.heads, edge_dim=h,
                                  dropout=0, add_self_loops=False, share_weights=False, residual=False)
        self.norm_ff = nn.LayerNorm(h)
        self.ff = mlp(h, 2 * h, h)

    def forward(self, nodes, edges, edge_features, edge_role):
        nodes = nodes + self.attention(self.norm_attention(nodes), edges, edge_features)
        return nodes + self.ff(self.norm_ff(nodes))


def build_block(config, num_relations):
    """Architecture selection is confined to the representation layer."""
    if config.encoder_type == 'rgcn':
        return PortRGCNBlock(config, num_relations)
    blocks = dict(graph_transformer=PortAttentionBlock, gatv2=PortGATv2Block)
    return blocks[config.encoder_type](config)


class CircuitEncoder(nn.Module):
    """forward(GraphBatch, actions=None) -> nodes [N,H], groups [G,H], context [B,H].

    Input features, action-to-member binding and readout are shared by all
    architectures. Only node processing changes. There are no topology-sized
    trainable layers. Each actor/critic owns a separate encoder instance.
    """
    def __init__(self, feature_schema, spec_schema, config, *, action_conditioned=False):
        super().__init__()
        h = config.hidden_dim
        self.config = config
        self.action_conditioned = action_conditioned
        self.device_values = nn.Linear(len(feature_schema.parameters) * 4, h)
        if feature_schema.op_columns:
            self.operating_points = nn.Linear(2 * len(feature_schema.op_columns), h)
        self.device_kind = nn.Embedding(len(feature_schema.device_kinds), h)
        self.net_values = nn.Linear(len(feature_schema.net_roles), h)
        self.context = mlp(spec_schema.width, h, h)
        self.uses_edge_features = config.encoder_type in ('graph_transformer', 'gatv2')
        if self.uses_edge_features:
            self.port_role = nn.Embedding(2 * len(feature_schema.terminal_roles), h)
            self.port_ordinal = nn.Linear(1, h, bias=False)
        self.parameter_kind = nn.Embedding(len(feature_schema.parameters), h)
        self.binding_ratio = nn.Linear(1, h, bias=False)
        self.group_values = mlp(8, h, h)
        if action_conditioned:
            self.action_token = mlp(h + 1, h, h)
        self.blocks = nn.ModuleList([build_block(config, 2 * len(feature_schema.terminal_roles))
                                     for _ in range(config.layers)])
        self.group_head = mlp(3 * h, h, h)
        self.output_norm = nn.LayerNorm(h)

    def forward(self, batch, actions=None):
        graph = batch.graph
        device = graph['device']
        values = torch.cat((device.x, device.parameter_mask.float(),
                            device.parameter_present.float(), device.optimizable_mask.float()), dim=-1)
        device_nodes = self.device_values(values) + self.device_kind(device.kind)
        if hasattr(self, 'operating_points'):
            device_nodes = device_nodes + self.operating_points(torch.cat((device.op, device.op_mask.float()), dim=-1))
        nodes = torch.cat((device_nodes, self.net_values(graph['net'].x)))
        context = self.context(batch.context)
        nodes = nodes + context[batch.node_batch]
        groups = self.group_values(batch.group_features) + self.parameter_kind(graph.group_kind)
        group_index, member_index = graph.group_member_index
        if self.action_conditioned:
            batch.validate_actions(actions)
            active_tokens = self.action_token(torch.cat((groups[batch.active], actions[:, None]), dim=-1))
            tokens = groups.new_zeros(groups.shape).index_add(0, batch.active, active_tokens)
            # Inject bound action tokens BEFORE node processing and retain at group readout.
            nodes = nodes + segment_sum(tokens[group_index], member_index, nodes.shape[0])
            groups = groups + tokens
        elif actions is not None:
            raise ValueError('Actor encoder does not accept actions')
        edge_features = None
        if self.uses_edge_features:
            edge_features = (self.port_role(batch.edge_role) +
                             self.port_ordinal(torch.log1p(batch.edge_ordinal.float())[:, None]))
        for block in self.blocks:
            nodes = block(nodes, batch.edge_index, edge_features, batch.edge_role)
        nodes = self.output_norm(nodes)
        binding = (nodes[member_index] + self.parameter_kind(graph.group_member_parameter) +
                   self.binding_ratio(graph.group_member_ratio.float().log()[:, None]))
        members = segment_mean(binding, group_index, groups.shape[0])
        groups = self.group_head(torch.cat((members, groups, context[batch.group_batch]), dim=-1))
        return nodes, groups, context


def build_encoder(feature_schema, spec_schema, config, *, action_conditioned=False):
    """Common factory used by both policy and Q networks."""
    return CircuitEncoder(feature_schema, spec_schema, config, action_conditioned=action_conditioned)


# Keep the original import/construction API available to existing callers.
PortGraphEncoder = CircuitEncoder
