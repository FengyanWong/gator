"""Interchangeable circuit encoders with a common node/group/context contract."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import torch
from torch import nn
from torch_geometric.nn import TransformerConv, RGCNConv, GATv2Conv
from .global_attention import CircuitAttention, RWSE_STEPS, structural_features
from .inputs import SpecSetSchema, SPEC_PROGRAM_LAYOUT


ENCODER_TYPES = ('graph_transformer', 'rgcn', 'gatv2', 'graph_gps', 'group_cross_attention', 'circuit_gps')
GLOBAL_ENCODERS = ('graph_gps', 'group_cross_attention', 'circuit_gps')
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
    structural_encoding: str | None = None  # GPS defaults to rwse; the group readout defaults to none.
    architecture_version: int = 1

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
        if encoder != 'rgcn' and self.hidden_dim % self.heads:
            raise ValueError('Attention hidden_dim must be divisible by heads')
        structural = self.structural_encoding if self.structural_encoding is not None else ('rwse' if encoder in ('graph_gps', 'circuit_gps') else 'none')
        if structural not in ('none', 'rwse') or (structural != 'none' and encoder not in GLOBAL_ENCODERS):
            raise ValueError('structural_encoding must be none, or rwse for graph_gps/group_cross_attention/circuit_gps')
        if type(self.architecture_version) is not int or self.architecture_version != 1:
            raise ValueError('Unsupported encoder architecture_version')
        object.__setattr__(self, 'structural_encoding', structural)
        object.__setattr__(self, 'encoder_type', encoder)
        object.__setattr__(self, 'attention_mode', next((k for k, v in LEGACY_MODES.items() if v == encoder), None))
        if not math.isfinite(self.log_std_min + self.log_std_max) or not -20 <= self.log_std_min < self.log_std_max <= 2:
            raise ValueError('Invalid log standard deviation limits')

    def to_dict(self):
        """Keep the existing encoders' checkpoint architecture contract unchanged."""
        values = asdict(self)
        if self.encoder_type not in GLOBAL_ENCODERS:
            values.pop('structural_encoding')
            values.pop('architecture_version')
        return values


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


class PortGPSBlock(PortAttentionBlock):
    """GPS-style parallel local port messages and full within-circuit attention."""
    def __init__(self, config):
        super().__init__(config)
        self.norm_global = nn.LayerNorm(config.hidden_dim)
        self.global_attention = CircuitAttention(config.hidden_dim, config.heads, 'global')

    def forward(self, nodes, edges, edge_features, edge_role, node_batch, count):
        local = nodes + self.attention(self.norm_attention(nodes), edges, edge_features)
        normalized = self.norm_global(nodes)
        global_nodes = nodes + self.global_attention(normalized, normalized, node_batch, node_batch, count)
        nodes = local + global_nodes
        return nodes + self.ff(self.norm_ff(nodes))


class GroupAttentionReadout(nn.Module):
    """One bound, goal-conditioned query per parameter group over circuit nodes."""
    def __init__(self, config):
        super().__init__()
        h = config.hidden_dim
        self.norm_query = nn.LayerNorm(h)
        self.norm_nodes = nn.LayerNorm(h)
        self.cross_attention = CircuitAttention(h, config.heads, 'group')
        self.norm_ff = nn.LayerNorm(h)
        self.ff = mlp(h, 2 * h, h)

    def forward(self, groups, nodes, batch):
        groups = groups + self.cross_attention(self.norm_query(groups), self.norm_nodes(nodes),
                                               batch.group_batch, batch.node_batch, len(batch.context))
        return groups + self.ff(self.norm_ff(groups))


class SpecSetReader(nn.Module):
    """The spec set input (inputs.SpecSetSchema, record 7.298) read into the same [B,H] context the slot input gives.

    One shared network turns every spec item into a vector, whatever the spec's name and however many a task has. The
    run's own row becomes a query that attends over its own specs (and over itself, so an observation without an active
    spec still reads); the context is formed from the run row, that attention and the mean of the spec vectors. Spec
    order changes nothing."""
    def __init__(self, spec_schema, config):
        super().__init__()
        h = config.hidden_dim
        self.item = mlp(spec_schema.token_width, h, h)
        self.run = mlp(spec_schema.run_width, h, h)
        self.norm_query = nn.LayerNorm(h)
        self.norm_keys = nn.LayerNorm(h)
        self.attention = CircuitAttention(h, config.heads if h % config.heads == 0 else 1, 'spec')
        self.output = mlp(3 * h, h, h)

    def forward(self, batch):
        count = len(batch.context)
        run = self.run(batch.context)
        items = self.item(batch.spec_items)
        graphs = torch.arange(count, device=run.device)
        keys, key_batch = torch.cat((items, run)), torch.cat((batch.spec_batch, graphs))
        attended = self.attention(self.norm_query(run), self.norm_keys(keys), graphs, key_batch, count)
        return self.output(torch.cat((run, attended, segment_mean(items, batch.spec_batch, count)), dim=-1))


def build_block(config, num_relations):
    """Architecture selection is confined to the representation layer."""
    if config.encoder_type == 'rgcn':
        return PortRGCNBlock(config, num_relations)
    blocks = dict(graph_transformer=PortAttentionBlock, gatv2=PortGATv2Block,
                  graph_gps=PortGPSBlock, group_cross_attention=PortAttentionBlock)
    return blocks[config.encoder_type](config)


class CircuitEncoder(nn.Module):
    """forward(GraphBatch, actions=None) -> nodes [N,H], groups [G,H], context [B,H].

    Input features, action-to-member binding and readout are shared by all
    architectures. Node processing and group readout can vary. There are no topology-sized
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
        self.spec_set = isinstance(spec_schema, SpecSetSchema)
        if self.spec_set:
            self.spec_reader = SpecSetReader(spec_schema, config)
        else:
            self.context = mlp(spec_schema.width, h, h)
        self.uses_edge_features = config.encoder_type != 'rgcn'
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
        if config.structural_encoding == 'rwse':
            self.structural_projection = nn.Linear(len(RWSE_STEPS), h)
        if config.encoder_type == 'group_cross_attention':
            self.group_readout = GroupAttentionReadout(config)

    def forward(self, batch, actions=None):
        graph = batch.graph
        device = graph['device']
        values = torch.cat((device.x, device.parameter_mask.float(),
                            device.parameter_present.float(), device.optimizable_mask.float()), dim=-1)
        device_nodes = self.device_values(values) + self.device_kind(device.kind)
        if hasattr(self, 'operating_points'):
            device_nodes = device_nodes + self.operating_points(torch.cat((device.op, device.op_mask.float()), dim=-1))
        nodes = torch.cat((device_nodes, self.net_values(graph['net'].x)))
        context = self.spec_reader(batch) if self.spec_set else self.context(batch.context)
        nodes = nodes + context[batch.node_batch]
        if hasattr(self, 'structural_projection'):
            nodes = nodes + self.structural_projection(structural_features(batch))
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
            if isinstance(block, PortGPSBlock):
                nodes = block(nodes, batch.edge_index, edge_features, batch.edge_role, batch.node_batch, len(context))
            else:
                nodes = block(nodes, batch.edge_index, edge_features, batch.edge_role)
        nodes = self.output_norm(nodes)
        binding = (nodes[member_index] + self.parameter_kind(graph.group_member_parameter) +
                   self.binding_ratio(graph.group_member_ratio.float().log()[:, None]))
        members = segment_mean(binding, group_index, groups.shape[0])
        groups = self.group_head(torch.cat((members, groups, context[batch.group_batch]), dim=-1))
        if hasattr(self, 'group_readout'):
            groups = self.group_readout(groups, nodes, batch)
        return nodes, groups, context


def build_encoder(feature_schema, spec_schema, config, *, action_conditioned=False):
    """Common factory used by both policy and Q networks."""
    if config.encoder_type == 'circuit_gps':
        from .circuit_gps import CircuitGPSEncoder
        return CircuitGPSEncoder(feature_schema, spec_schema, config, action_conditioned=action_conditioned)
    if getattr(spec_schema, 'layout', None) == SPEC_PROGRAM_LAYOUT:
        raise ValueError('Structured measurement programs require circuit_gps; other encoders use slots or set')
    return CircuitEncoder(feature_schema, spec_schema, config, action_conditioned=action_conditioned)


# Keep the original import/construction API available to existing callers.
PortGraphEncoder = CircuitEncoder
