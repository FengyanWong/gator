"""Fixed-schema device/net HeteroData, plus a separately indexed group table."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import math

import torch
from torch_geometric.data import HeteroData

from .circuit_graph import CircuitGraph


@dataclass(frozen=True)
class FeatureSchema:
    version: str = "1.0"
    device_kinds: tuple[str, ...] = ("unknown", "nmos", "pmos", "resistor", "capacitor", "inductor", "vsource", "isource")
    terminal_roles: tuple[str, ...] = ("unknown", "drain", "gate", "source", "bulk", "positive", "negative")
    net_roles: tuple[str, ...] = ("normal", "ground", "supply", "input", "output", "bias", "clock")
    parameters: tuple[str, ...] = ("w", "l", "m", "nf", "r", "c", "ind", "dc")
    # Values in canonical SI units, divided by explicit reference scales. No fitted statistics.
    references: tuple[float, ...] = (1e-6, 1e-6, 1.0, 1.0, 1e3, 1e-12, 1e-9, 1.0)

    def __post_init__(self) -> None:
        for vocabulary in (self.device_kinds, self.terminal_roles, self.net_roles, self.parameters):
            if not vocabulary or len(vocabulary) != len(set(vocabulary)):
                raise ValueError("Feature vocabularies must be nonempty and unique")
        if len(self.references) != len(self.parameters) or any(not math.isfinite(x) or x <= 0 for x in self.references):
            raise ValueError("Each numeric feature needs a positive finite reference")


@dataclass(frozen=True)
class GraphMetadata:
    """Opaque to PyG collation: retained per graph and restored on unbatch."""
    circuit_id: str
    device_ids: tuple[str, ...]
    net_ids: tuple[str, ...]
    group_ids: tuple[str, ...]
    schema: FeatureSchema
    source_metadata: dict
    group_definitions: tuple
    diagnostics: tuple
    device_definitions: tuple
    writeback_names: tuple[tuple[str, str, str], ...]


class CircuitHeteroData(HeteroData):
    def __cat_dim__(self, key, value, store=None, *args, **kwargs):
        if key == "group_member_index":
            return 1
        return super().__cat_dim__(key, value, store, *args, **kwargs)

    def __inc__(self, key, value, store=None, *args, **kwargs):
        if key == "group_member_index":
            return value.new_tensor([[self.group_x.shape[0]], [self["device"].num_nodes]])
        return super().__inc__(key, value, store, *args, **kwargs)


class TopologyTensorCache:
    """Bounded CPU templates, independent of sizes, measurements and encoder weights."""

    def __init__(self, capacity=64):
        if type(capacity) is not int or capacity < 0:
            raise ValueError('Topology cache capacity must be a nonnegative integer')
        self.capacity = capacity
        self._items = OrderedDict()
        self.hits = self.misses = 0

    def clear(self):
        self._items.clear()
        self.hits = self.misses = 0

    def info(self):
        return dict(hits=self.hits, misses=self.misses, entries=len(self._items), capacity=self.capacity)

    def _template(self, graph, schema):
        if not self.capacity:
            self.misses += 1
            return _static_features(graph, schema)
        # Order is part of the key: cached indices must match current writeback IDs.
        key = (schema, graph.schema_version,
               tuple((d.id, d.kind, d.model_ref, d.terminals) for d in graph.devices),
               tuple((n.id, n.roles) for n in graph.nets), tuple(graph.connections),
               tuple((g.id, g.parameter_kind, g.mutable,
                      tuple((m.device_id, m.parameter, m.ratio) for m in g.members))
                     for g in graph.parameter_groups))
        if key in self._items:
            self.hits += 1
            self._items.move_to_end(key)
            return self._items[key].clone()
        self.misses += 1
        data = _static_features(graph, schema)
        if self.capacity:
            self._items[key] = data
            if len(self._items) > self.capacity:
                self._items.popitem(last=False)
            return data.clone()  # Public results never expose a cached tensor.
        return data


def _static_features(graph, schema):
    data = CircuitHeteroData()
    device_ids = {device.id: i for i, device in enumerate(graph.devices)}
    net_ids = {net.id: i for i, net in enumerate(graph.nets)}
    n, width = len(device_ids), len(schema.parameters)
    data["device"].num_nodes = n
    data["net"].num_nodes = len(net_ids)
    data["device"].kind = torch.tensor([schema.device_kinds.index(d.kind) for d in graph.devices], dtype=torch.long)
    mutable = torch.zeros((n, width), dtype=torch.bool)
    data["device"].optimizable_mask = mutable
    data["net"].x = torch.zeros((len(net_ids), len(schema.net_roles)), dtype=torch.float32)
    for net in graph.nets:
        for role in net.roles:
            data["net"].x[net_ids[net.id], schema.net_roles.index(role)] = 1.0

    for role in schema.terminal_roles:
        edges = [c for c in graph.connections if c.role == role]
        index = torch.tensor([[device_ids[c.device_id], net_ids[c.net_id]] for c in edges], dtype=torch.long).reshape(-1, 2).t().contiguous()
        forward, reverse = ("device", f"{role}_to_net", "net"), ("net", f"net_to_{role}", "device")
        data[forward].edge_index = index
        data[reverse].edge_index = index.flip(0)
        # Ordinal distinguishes even unknown ports on the same pair of nodes.
        data[forward].terminal_ordinal = torch.tensor([c.ordinal for c in edges], dtype=torch.long)
        data[reverse].terminal_ordinal = data[forward].terminal_ordinal.clone()
    if any(c.role not in schema.terminal_roles for c in graph.connections):
        raise ValueError("Terminal role absent from fixed feature schema")

    data.group_mask = torch.ones(len(graph.parameter_groups), dtype=torch.bool)
    data.group_mutable = torch.tensor([g.mutable for g in graph.parameter_groups], dtype=torch.bool)
    data.group_kind = torch.tensor([schema.parameters.index(g.parameter_kind) for g in graph.parameter_groups], dtype=torch.long)
    bindings, parameter_ids, ratios = [], [], []
    for i, group in enumerate(graph.parameter_groups):
        for member in group.members:
            row, col = device_ids[member.device_id], schema.parameters.index(member.parameter)
            bindings.append([i, row])
            parameter_ids.append(col)
            ratios.append(member.ratio)
            mutable[row, col] = group.mutable
    data.group_member_index = torch.tensor(bindings, dtype=torch.long).reshape(-1, 2).t().contiguous()
    data.group_member_parameter = torch.tensor(parameter_ids, dtype=torch.long)
    data.group_member_ratio = torch.tensor(ratios, dtype=torch.float64)
    return data


def to_pyg(graph: CircuitGraph, schema: FeatureSchema | None = None,
           *, allow_incomplete: bool = False,
           topology_cache: TopologyTensorCache | None = None) -> CircuitHeteroData:
    """Refresh sizes/masks/metadata, optionally reusing a validated static template."""
    graph.validate(require_complete=not allow_incomplete)
    schema = schema or FeatureSchema()
    data = (_static_features(graph, schema) if topology_cache is None
            else topology_cache._template(graph, schema))
    device_ids = {device.id: i for i, device in enumerate(graph.devices)}
    net_ids = {net.id: i for i, net in enumerate(graph.nets)}
    values = torch.zeros((len(device_ids), len(schema.parameters)), dtype=torch.float32)
    mask = torch.zeros_like(values, dtype=torch.bool)
    present = torch.zeros_like(mask)
    for device in graph.devices:
        row = device_ids[device.id]
        for col, key in enumerate(schema.parameters):
            parameter = graph.parameters[device.id].get(key)
            present[row, col] = parameter is not None
            if parameter is not None and parameter.valid:
                scaled = parameter.value / schema.references[col]
                values[row, col] = math.copysign(math.log1p(abs(scaled)), scaled)
                mask[row, col] = True
    data["device"].x = values
    data["device"].parameter_mask = mask
    data["device"].parameter_present = present
    # Group physical values remain float64 with units/domains stored in metadata.
    data.group_x = torch.tensor([[g.value, g.lower, g.upper] for g in graph.parameter_groups], dtype=torch.float64).reshape(-1, 3)
    data.graph_metadata = GraphMetadata(graph.circuit_id, tuple(device_ids), tuple(net_ids),
                                        tuple(g.id for g in graph.parameter_groups), schema,
                                        deepcopy(graph.metadata), tuple(graph.parameter_groups), tuple(graph.diagnostics),
                                        tuple(graph.devices),
                                        tuple((device_id, parameter, value.source_name or parameter)
                                              for device_id, parameters in graph.parameters.items()
                                              for parameter, value in parameters.items()))
    if not torch.isfinite(values).all():
        raise ValueError("Feature scaling overflow")
    data.validate(raise_on_error=True)
    return data
