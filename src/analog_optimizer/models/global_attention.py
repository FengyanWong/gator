"""Circuit-isolated dense attention and cached, topology-only structural inputs."""
from collections import OrderedDict
import threading

import torch
from torch import nn


RWSE_STEPS = (2, 4, 8, 16)  # Even walks carry information on the device/net bipartite graph.
_RWSE_CACHE = OrderedDict()
_RWSE_LOCK = threading.Lock()
_RWSE_MAX_BYTES = 32 * 1024 * 1024


def _packing_layout(batch, count):
    sizes = torch.bincount(batch, minlength=count)
    order = torch.argsort(batch, stable=True)
    starts = sizes.cumsum(0) - sizes
    positions = torch.empty_like(batch)
    positions[order] = torch.arange(len(batch), device=batch.device) - starts[batch[order]]
    width = int(sizes.max())
    padding = torch.arange(width, device=batch.device)[None, :] >= sizes[:, None]
    return padding, positions


class GraphPacking:
    """Raw layouts reused within one forward; never holds learned representations.

    Membership tensors are immutable for this scope. Keeping their references
    prevents identity reuse; a new scope on every forward avoids stale layouts
    when a caller changes an observation between calls.
    """
    def __init__(self, count):
        self.count = count
        self._layouts = {}
        self._fallback = {}

    def layout(self, batch):
        key = id(batch)
        if key not in self._layouts:
            self._layouts[key] = (batch, *_packing_layout(batch, self.count))
        return self._layouts[key][1:]

    def with_run(self, batch):
        key = id(batch)
        if key not in self._fallback:
            extended = torch.cat((batch, torch.arange(self.count, device=batch.device)))
            self._fallback[key] = (batch, extended)
        return self._fallback[key][1]


def pack_by_graph(values, batch, count, *, packing=None):
    """Dense rows plus inverse positions; accepts interleaved device/net graph IDs."""
    if packing is not None and packing.count != count:
        raise ValueError('Graph packing circuit count differs')
    padding, positions = _packing_layout(batch, count) if packing is None else packing.layout(batch)
    dense = values.new_zeros((count, padding.shape[1], values.shape[-1]))
    dense[batch, positions] = values
    return dense, padding, positions


class CircuitAttention(nn.Module):
    """Queries attend only to keys in their circuit; padding never receives weight."""
    def __init__(self, hidden, heads, kind):
        super().__init__()
        self.attention = nn.MultiheadAttention(hidden, heads, dropout=0, batch_first=True)
        self.attention.attention_kind = kind  # Read-only workbench inspection labels this scope.

    def forward(self, queries, keys, query_batch, key_batch, count, *, packing=None):
        q, _, positions = pack_by_graph(queries, query_batch, count, packing=packing)
        kv, padding, _ = pack_by_graph(keys, key_batch, count, packing=packing)
        output, _ = self.attention(q, kv, kv, key_padding_mask=padding, need_weights=False)
        return output[query_batch, positions]


def _return_probabilities(count, edges, *, cached=True):
    """Unweighted terminal multigraph walks. Cache only raw CPU [N,4] inputs.

    Duplicate terminals count as separate walks. Isolated nodes have zero return
    probabilities. The version fixes the walk lengths and multiplicity semantics.
    Edge indices, including their ordering, bind each cached row to its node.
    """
    edges = edges.detach().cpu().contiguous()
    key = ('terminal-rwse-v1', count, edges.numpy().tobytes())
    with _RWSE_LOCK:
        if cached and key in _RWSE_CACHE:
            _RWSE_CACHE.move_to_end(key)
            return _RWSE_CACHE[key].clone()
    degree = torch.bincount(edges[0], minlength=count).clamp_min(1).float()
    transition = torch.sparse_coo_tensor(edges, 1 / degree[edges[0]], (count, count), check_invariants=True).coalesce()
    walks = torch.eye(count)
    diagonals = []
    for step in range(1, max(RWSE_STEPS) + 1):
        walks = torch.sparse.mm(transition, walks)
        if step in RWSE_STEPS:
            diagonals.append(walks.diagonal().clone())
    result = torch.stack(diagonals, dim=-1)
    size = result.numel() * result.element_size() + len(key[2])
    with _RWSE_LOCK:
        if cached and size <= _RWSE_MAX_BYTES:
            _RWSE_CACHE[key] = result
            while len(_RWSE_CACHE) > 64 or sum(v.numel() * v.element_size() + len(k[2])
                                              for k, v in _RWSE_CACHE.items()) > _RWSE_MAX_BYTES:
                _RWSE_CACHE.popitem(last=False)
    return result.clone()


def structural_features(batch, *, cached=True):
    result = batch.context.new_zeros((len(batch.node_batch), len(RWSE_STEPS)))
    for graph_id in range(len(batch.context)):
        indices = (batch.node_batch == graph_id).nonzero().flatten()
        inverse = torch.empty_like(batch.node_batch)
        inverse[indices] = torch.arange(len(indices), device=indices.device)
        selected = batch.node_batch[batch.edge_index[0]] == graph_id
        edges = inverse[batch.edge_index[:, selected]]
        result[indices] = _return_probabilities(len(indices), edges, cached=cached).to(result)
    return result
