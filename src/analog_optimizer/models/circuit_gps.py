"""CircuitGPS: joint circuit, specification, parameter and motif tokens.

Separate weights for each relation, Pre-LN gated residuals, no learned instance
IDs. The actor and each action-conditioned critic own their entire encoder.
"""
from collections import OrderedDict, deque
import threading

import torch
from torch import nn
from torch.nn import functional as F
from torch_geometric.nn import TransformerConv

from .encoders import mlp, segment_sum, segment_mean
from .global_attention import CircuitAttention, GraphPacking, RWSE_STEPS, structural_features, pack_by_graph
from .inputs import SpecSetSchema, SPEC_PROGRAM_LAYOUT
from .measurement_program import OPERATIONS, BINDING_ROLES, BLOCK_KINDS

_DISTANCES = OrderedDict()
_DISTANCE_LOCK = threading.Lock()
_DISTANCE_BYTES = 32 * 1024 * 1024


def distances(count, edges):
    """Undirected electrical distance: 0..8 hops, 9 = disconnected. Raw bounded cache."""
    edges = edges.detach().cpu().contiguous()
    key = (count, edges.numpy().tobytes())
    with _DISTANCE_LOCK:
        if key in _DISTANCES:
            _DISTANCES.move_to_end(key)
            return _DISTANCES[key].clone()
    adjacency = [set() for _ in range(count)]
    for a, b in edges.T.tolist():
        adjacency[a].add(b)
        adjacency[b].add(a)
    result = torch.full((count, count), 9, dtype=torch.long)
    for start in range(count):
        found, queue = {start: 0}, deque([start])
        while queue:
            a = queue.popleft()
            for b in adjacency[a]:
                if b not in found:
                    found[b] = found[a] + 1
                    queue.append(b)
        for b, d in found.items():
            result[start, b] = min(d, 8)
    size = result.numel() * result.element_size() + len(key[1])
    with _DISTANCE_LOCK:
        if size <= _DISTANCE_BYTES:
            _DISTANCES[key] = result
            while len(_DISTANCES) > 64 or sum(v.numel() * v.element_size() + len(k[1])
                                             for k, v in _DISTANCES.items()) > _DISTANCE_BYTES:
                _DISTANCES.popitem(last=False)
    return result.clone()


class RelationAttention(nn.Module):
    def __init__(self, config, kind, *, fallback=True):
        super().__init__()
        h = config.hidden_dim
        self.query_norm, self.key_norm = nn.LayerNorm(h), nn.LayerNorm(h)
        self.attention = CircuitAttention(h, config.heads, kind)
        self.fallback = fallback
        self.gate = nn.Parameter(torch.full((h,), -1.))

    def forward(self, queries, keys, query_batch, key_batch, run, *, packing=None):
        if not len(queries):
            return queries
        # Every circuit has a real run token even with no active/measured specs.
        if self.fallback:
            keys = torch.cat((keys, run))
            key_batch = (torch.cat((key_batch, torch.arange(len(run), device=key_batch.device)))
                         if packing is None else packing.with_run(key_batch))
        update = self.attention(self.query_norm(queries), self.key_norm(keys), query_batch, key_batch,
                                len(run), packing=packing)
        return queries + self.gate.sigmoid() * update


class ResidualFF(nn.Module):
    def __init__(self, h):
        super().__init__()
        self.norm = nn.LayerNorm(h)
        self.ff = mlp(h, 2 * h, h)
        self.gate = nn.Parameter(torch.full((h,), -1.))

    def forward(self, values):
        return values + self.gate.sigmoid() * self.ff(self.norm(values))


class StructuralAttention(nn.Module):
    def __init__(self, config, relations):
        super().__init__()
        self.heads = config.heads
        self.attention = nn.MultiheadAttention(config.hidden_dim, config.heads, dropout=0, batch_first=True)
        self.attention.attention_kind = 'global'
        self.distance_bias = nn.Embedding(10, config.heads)
        self.terminal_bias = nn.Embedding(relations, config.heads)

    def forward(self, nodes, batch, *, packing=None):
        dense, padding, position = pack_by_graph(nodes, batch.node_batch, batch.size, packing=packing)
        width = dense.shape[1]
        bias = nodes.new_zeros((batch.size, self.heads, width, width))
        for circuit in range(batch.size):
            ids = (batch.node_batch == circuit).nonzero().flatten()
            selected = batch.node_batch[batch.edge_index[0]] == circuit
            edges = position[batch.edge_index[:, selected]]
            d = distances(len(ids), edges).to(nodes.device)
            own = self.distance_bias(d).permute(2, 0, 1)
            # Both directions and parallel terminals have their own bias. Sum, never coalesce roles.
            terminal = self.terminal_bias(batch.edge_role[selected])
            flat = own.permute(1, 2, 0).reshape(-1, self.heads)
            flat = flat.index_add(0, edges[1] * len(ids) + edges[0], terminal)
            bias[circuit, :, :len(ids), :len(ids)] = flat.reshape(len(ids), len(ids), -1).permute(2, 0, 1)
        bias = bias.masked_fill(padding[:, None, None, :], float('-inf'))
        out, _ = self.attention(dense, dense, dense, attn_mask=bias.flatten(0, 1), need_weights=False)
        return out[batch.node_batch, position]


def _program_levels(data):
    """Raw execution schedule shared by the readers in one encoder forward."""
    child, parent = data['children']
    heights = data['height']
    levels = []
    for height in range(1, int(heights.max()) + 1 if len(heights) else 1):
        rows = (heights == height).nonzero().flatten()
        selected = heights[parent] == height
        # rows is sorted. Preserve the original child order within each parent.
        local_parent = torch.searchsorted(rows, parent[selected])
        slots = torch.log1p(data['slot'][selected])[:, None]
        levels.append((rows, child[selected], local_parent, slots))
    return levels


class ProgramReader(nn.Module):
    """Bottom-up ordered tree computation, with live graph embeddings at leaves."""
    def __init__(self, h, *, normalize_tree=True):
        super().__init__()
        self.normalize_tree = normalize_tree
        self.operation = nn.Embedding(len(OPERATIONS), h)
        self.values = mlp(6, h, h)
        self.binding_role = nn.Embedding(len(BINDING_ROLES), h)
        self.binding = mlp(2 * h, h, h)
        self.slot = mlp(1, h, h)
        self.child = mlp(2 * h, h, h)
        self.combine = mlp(2 * h, h, h)
        self.norm = nn.LayerNorm(h)

    def forward(self, nodes, data, *, levels=None):
        base = self.operation(data['op']) + self.values(data['values'])
        tokens, ids = data['bindings']
        bound = self.binding(torch.cat((nodes[ids], self.binding_role(data['binding_role'])), dim=-1))
        base = base + segment_sum(bound, tokens, len(base))
        # Bound the states reused at every tree height. Root-only normalization
        # allows repeated learned amplification to overflow on deep programs.
        # No affine parameters: saved weights retain their names and shapes.
        if self.normalize_tree:
            base = F.layer_norm(base, (base.shape[-1],))
        state = base
        if self.normalize_tree:
            levels = _program_levels(data) if levels is None else levels
            for rows, children, parents, slots in levels:
                messages = self.child(torch.cat((state[children], self.slot(slots)), dim=-1))
                summed = segment_sum(messages, parents, len(rows))
                updated = self.combine(torch.cat((base[rows], summed), dim=-1))
                updated = F.layer_norm(updated, (updated.shape[-1],))
                state = state.index_copy(0, rows, updated)
            return self.norm(state[data['roots']])
        # Version 1 retains its historical root-only computation, including the
        # original full-row arithmetic; only normalized v2 uses the sparse rows.
        child, parent = data['children']
        # Heights are raw program topology; every subtree is evaluated completely.
        for height in range(1, int(data['height'].max()) + 1 if len(base) else 1):
            selected = data['height'][parent] == height
            ci, pi = child[selected], parent[selected]
            slots = self.slot(torch.log1p(data['slot'][selected])[:, None])
            messages = self.child(torch.cat((state[ci], slots), dim=-1))
            summed = segment_sum(messages, pi, len(base))
            updated = self.combine(torch.cat((base, summed), dim=-1))
            state = torch.where((data['height'] == height)[:, None], updated, state)
        return self.norm(state[data['roots']])


class JointBlock(nn.Module):
    def __init__(self, config, relations, structured):
        super().__init__()
        h = config.hidden_dim
        self.norm_local, self.norm_global = nn.LayerNorm(h), nn.LayerNorm(h)
        self.attention = TransformerConv(h, h // config.heads, heads=config.heads,
                                         edge_dim=h, dropout=0, root_weight=False)
        self.global_attention = StructuralAttention(config, relations)
        self.local_gate, self.global_gate = nn.Parameter(torch.full((h,), -1.)), nn.Parameter(torch.full((h,), -1.))
        self.spec_from_nodes = RelationAttention(config, 'spec_graph', fallback=False)
        self.nodes_from_specs = RelationAttention(config, 'graph_spec')
        self.groups_from_nodes = RelationAttention(config, 'group', fallback=False)
        self.nodes_from_groups = RelationAttention(config, 'graph_group')
        self.groups_from_specs = RelationAttention(config, 'parameter_spec')
        self.spec_self = RelationAttention(config, 'spec_self')
        self.group_self = RelationAttention(config, 'parameter_self')
        self.node_ff, self.spec_ff, self.group_ff = (ResidualFF(h) for _ in range(3))
        self.member_message = mlp(2 * h, h, h)
        self.member_gate = nn.Parameter(torch.full((h,), -1.))
        if structured:
            self.program = ProgramReader(h, normalize_tree=config.architecture_version >= 2)
            self.program_gate = nn.Parameter(torch.full((h,), -1.))
            self.spec_binding = mlp(2 * h, h, h)
            self.block_from_nodes = RelationAttention(config, 'block_graph', fallback=False)
            self.nodes_from_blocks = RelationAttention(config, 'graph_block')
            self.block_ff = ResidualFF(h)
            self.block_members = mlp(2 * h, h, h)

    def forward(self, nodes, specs, groups, blocks, run, spec_batch, batch, edge_features, member_features,
                *, packing=None, program_levels=None):
        local = self.attention(self.norm_local(nodes), batch.edge_index, edge_features)
        global_nodes = self.global_attention(self.norm_global(nodes), batch, packing=packing)
        nodes = nodes + self.local_gate.sigmoid() * local + self.global_gate.sigmoid() * global_nodes
        if batch.structured is not None:
            data = batch.structured
            specs = specs + self.program_gate.sigmoid() * self.program(nodes, data, levels=program_levels)
            ti, ni = data['bindings']
            messages = self.spec_binding(torch.cat((specs[data['owner'][ti]],
                                                    self.program.binding_role(data['binding_role'])), dim=-1))
            nodes = nodes + self.program_gate.sigmoid() * segment_sum(messages, ni, len(nodes))
            bi, ni = data['block_members']
            blocks = blocks + segment_mean(nodes[ni], bi, len(blocks))
            blocks = self.block_ff(self.block_from_nodes(blocks, nodes, data['block_batch'], batch.node_batch,
                                                         run, packing=packing))
            messages = self.block_members(torch.cat((nodes[ni], blocks[bi]), dim=-1))
            nodes = nodes + self.program_gate.sigmoid() * segment_mean(messages, ni, len(nodes))
            nodes = self.nodes_from_blocks(nodes, blocks, batch.node_batch, data['block_batch'], run, packing=packing)
        gi, ni = batch.graph.group_member_index
        bound = self.member_message(torch.cat((nodes[ni], member_features), dim=-1))
        groups = groups + self.member_gate.sigmoid() * segment_sum(bound, gi, len(groups))
        specs = self.spec_from_nodes(specs, nodes, spec_batch, batch.node_batch, run, packing=packing)
        specs = self.spec_ff(self.spec_self(specs, specs, spec_batch, spec_batch, run, packing=packing))
        nodes = self.nodes_from_specs(nodes, specs, batch.node_batch, spec_batch, run, packing=packing)
        groups = self.groups_from_nodes(groups, nodes, batch.group_batch, batch.node_batch, run, packing=packing)
        groups = self.groups_from_specs(groups, specs, batch.group_batch, spec_batch, run, packing=packing)
        groups = self.group_ff(self.group_self(groups, groups, batch.group_batch, batch.group_batch, run, packing=packing))
        nodes = self.node_ff(self.nodes_from_groups(nodes, groups, batch.node_batch, batch.group_batch, run, packing=packing))
        return nodes, specs, groups, blocks


class CircuitGPSEncoder(nn.Module):
    def __init__(self, feature_schema, spec_schema, config, *, action_conditioned=False):
        super().__init__()
        h = config.hidden_dim
        self.config, self.action_conditioned = config, action_conditioned
        self.spec_set = isinstance(spec_schema, SpecSetSchema)
        self.structured = getattr(spec_schema, 'layout', None) == SPEC_PROGRAM_LAYOUT
        self.device_values = nn.Linear(len(feature_schema.parameters) * 4, h)
        self.device_kind = nn.Embedding(len(feature_schema.device_kinds), h)
        self.net_values = nn.Linear(len(feature_schema.net_roles), h)
        if feature_schema.op_columns:
            self.operating_points = nn.Linear(2 * len(feature_schema.op_columns), h)
        self.context = mlp(spec_schema.run_width if self.spec_set else spec_schema.width, h, h)
        if self.spec_set:
            self.spec_values = mlp(spec_schema.token_width, h, h)
        self.parameter_kind = nn.Embedding(len(feature_schema.parameters), h)
        self.binding_ratio = nn.Linear(1, h, bias=False)
        self.group_values = mlp(8, h, h)
        self.port_role = nn.Embedding(2 * len(feature_schema.terminal_roles), h)
        self.port_ordinal = nn.Linear(1, h, bias=False)
        if self.structured:
            self.group_coordinates = mlp(3, h, h)
            self.physics = mlp(10, h, h)
            self.block_kind = nn.Embedding(len(BLOCK_KINDS), h)
        if config.structural_encoding == 'rwse':
            self.structural_projection = nn.Linear(len(RWSE_STEPS), h)
        if action_conditioned:
            self.action_token = mlp(h + 1, h, h)
        self.blocks = nn.ModuleList(JointBlock(config, len(feature_schema.terminal_roles) * 2, self.structured)
                                    for _ in range(config.layers))
        self.output_norm, self.group_norm = nn.LayerNorm(h), nn.LayerNorm(h)
        self.readout = RelationAttention(config, 'joint_readout')
        # Attention + separate sums of each type + counts preserve cardinality.
        self.readout_output = mlp(5 * h + 4, 2 * h, h)

    def forward(self, batch, actions=None):
        if self.structured != (batch.structured is not None):
            raise ValueError('CircuitGPS measurement program input differs from its saved schema')
        graph, device = batch.graph, batch.graph['device']
        values = torch.cat((device.x, device.parameter_mask.float(), device.parameter_present.float(),
                            device.optimizable_mask.float()), dim=-1)
        dev = self.device_values(values) + self.device_kind(device.kind)
        if hasattr(self, 'operating_points'):
            dev = dev + self.operating_points(torch.cat((device.op, device.op_mask.float()), dim=-1))
        if self.structured:
            dev = dev + self.physics(batch.structured['physics'])
        run = self.context(batch.context)
        nodes = torch.cat((dev, self.net_values(graph['net'].x))) + run[batch.node_batch]
        if hasattr(self, 'structural_projection'):
            nodes = nodes + self.structural_projection(structural_features(batch))
        specs = self.spec_values(batch.spec_items) if self.spec_set else run
        spec_batch = batch.spec_batch if self.spec_set else torch.arange(batch.size, device=nodes.device)
        groups = self.group_values(batch.group_features) + self.parameter_kind(graph.group_kind) + run[batch.group_batch]
        blocks = nodes.new_empty((0, nodes.shape[-1]))
        block_batch = batch.node_batch.new_empty(0)
        if self.structured:
            groups = groups + self.group_coordinates(batch.structured['coordinates'])
            blocks = self.block_kind(batch.structured['block_kind'])
            block_batch = batch.structured['block_batch']
        gi, ni = graph.group_member_index
        member_features = (self.parameter_kind(graph.group_member_parameter)
                           + self.binding_ratio(graph.group_member_ratio.float().log()[:, None]))
        groups = groups + segment_mean(nodes[ni] + member_features, gi, len(groups))
        if self.action_conditioned:
            batch.validate_actions(actions)
            tokens = self.action_token(torch.cat((groups[batch.active], actions[:, None]), dim=-1))
            tokens = groups.new_zeros(groups.shape).index_add(0, batch.active, tokens)
            nodes = nodes + segment_sum(tokens[gi], ni, len(nodes))
            groups = groups + tokens
        elif actions is not None:
            raise ValueError('Actor encoder does not accept actions')
        edge_features = self.port_role(batch.edge_role) + self.port_ordinal(torch.log1p(batch.edge_ordinal.float())[:, None])
        packing = GraphPacking(batch.size)
        program_levels = (_program_levels(batch.structured)
                          if self.structured and self.config.architecture_version >= 2 else None)
        for block in self.blocks:
            nodes, specs, groups, blocks = block(nodes, specs, groups, blocks, run, spec_batch, batch,
                                                edge_features, member_features, packing=packing,
                                                program_levels=program_levels)
        nodes, groups = self.output_norm(nodes), self.group_norm(groups)
        types = ((nodes, batch.node_batch), (groups, batch.group_batch), (specs, spec_batch), (blocks, block_batch))
        keys, key_batch = torch.cat([v for v, _ in types]), torch.cat([b for _, b in types])
        attended = self.readout(run, keys, torch.arange(batch.size, device=nodes.device), key_batch, run, packing=packing)
        sums = [segment_sum(v, b, batch.size) for v, b in types]
        counts = torch.stack([torch.bincount(b, minlength=batch.size) for _, b in types], dim=-1).to(nodes).log1p()
        context = self.readout_output(torch.cat((attended, *sums, counts), dim=-1))
        return nodes, groups, context
