from dataclasses import replace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")
from torch_geometric.data import Batch

from analog_optimizer.graph.pyg_converter import FeatureSchema, to_pyg
from analog_optimizer.netlist.config import DeviceMapping
from analog_optimizer.netlist.spectre_parser import SpectreParser


def test_port_relations_reverse_edges_empty_types_and_dtypes(parser):
    graph = parser.parse_text("Q (a g 0 0) nmos_demo w=1u l=200n")
    data = to_pyg(graph)
    source = data["device", "source_to_net", "net"].edge_index
    bulk = data["device", "bulk_to_net", "net"].edge_index
    assert torch.equal(source, bulk)  # Same node pair in two distinct relations.
    for role in FeatureSchema().terminal_roles:
        forward = data["device", f"{role}_to_net", "net"]
        reverse = data["net", f"net_to_{role}", "device"]
        assert torch.equal(forward.edge_index.flip(0), reverse.edge_index)
        assert forward.edge_index.dtype == torch.long
    assert data["device", "positive_to_net", "net"].edge_index.shape == (2, 0)
    assert data["device"].x.dtype == torch.float32


def test_missing_unresolved_real_zero_are_distinct(parser):
    graph = parser.parse_text("R (a 0) resistor r=unknown\nV (a 0) vsource dc=0")
    data = to_pyg(graph)
    schema = FeatureSchema()
    r, dc, w = map(schema.parameters.index, ("r", "dc", "w"))
    assert data["device"].parameter_present[0, r] and not data["device"].parameter_mask[0, r]
    assert not data["device"].parameter_present[0, w]
    assert data["device"].parameter_mask[1, dc] and data["device"].x[1, dc] == 0
    assert torch.isfinite(data["device"].x).all()


def test_different_graph_and_group_sizes_batch_unbatch(opamp, ldo, parser):
    empty_groups = parser.parse_text("R (a 0) resistor r=1k")
    # Put the zero-group graph first to exercise empty concatenation and offsets.
    original = [to_pyg(g) for g in (empty_groups, opamp, ldo)]
    batch = Batch.from_data_list(original)
    batch.validate(raise_on_error=True)
    for source, relation, target in batch.edge_types:
        edges = batch[source, relation, target].edge_index
        assert torch.equal(batch[source].batch[edges[0]], batch[target].batch[edges[1]])
    group_batch = torch.repeat_interleave(torch.arange(3), torch.tensor([0, 2, 1]))
    bindings = batch.group_member_index
    assert torch.equal(group_batch[bindings[0]], batch["device"].batch[bindings[1]])
    assert batch.group_x.shape == (3, 3)
    assert batch.group_member_index.shape == (2, 4)
    for before, after in zip(original, batch.to_data_list()):
        for name in ("group_x", "group_member_index", "group_member_parameter", "group_member_ratio", "group_mutable"):
            assert torch.equal(before[name], after[name])
        assert before.graph_metadata == after.graph_metadata
        for edge in before.edge_types:
            assert torch.equal(before[edge].edge_index, after[edge].edge_index)
        assert torch.equal(before["device"].parameter_mask, after["device"].parameter_mask)


def test_unknown_nodes_require_explicit_diagnostic_conversion(parser):
    graph = parser.parse_text("X (a a b) mystery w=1u")
    with pytest.raises(ValueError, match="Incomplete"):
        to_pyg(graph)
    data = to_pyg(graph, allow_incomplete=True)
    store = data["device", "unknown_to_net", "net"]
    assert store.edge_index.shape == (2, 3)
    assert store.terminal_ordinal.tolist() == [0, 1, 2]


def test_names_and_order_do_not_become_learning_features(parser):
    first = parser.parse_text("Q (out in 0 0) nmos_demo w=1u l=200n\nR (out 0) resistor r=1k")
    second = parser.parse_text("renamed_r (z 0) resistor r=1k\nrenamed_q (z x 0 0) nmos_demo w=1u l=200n")
    a, b = to_pyg(first), to_pyg(second)
    assert torch.equal(a["device"].x, b["device"].x.flip(0))
    assert torch.equal(a["device"].kind, b["device"].kind.flip(0))
    devices = {"renamed_r": "R", "renamed_q": "Q"}
    nets = {"z": "out", "x": "in", "0": "0"}
    assert {(c.device_id, c.net_id, c.role) for c in first.connections} == {
        (devices[c.device_id], nets[c.net_id], c.role) for c in second.connections}


def test_dynamic_sizes_refresh_without_changing_structure(opamp):
    before = to_pyg(opamp)
    for identifier in ("input_left", "input_right"):
        old = opamp.parameters[identifier]["w"]
        opamp.parameters[identifier]["w"] = replace(old, value=3e-6)
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], value=3e-6)
    after = to_pyg(opamp)
    assert not torch.equal(before["device"].x, after["device"].x)
    for edge in before.edge_types:
        assert torch.equal(before[edge].edge_index, after[edge].edge_index)


def test_alias_source_names_survive_pyg_batch(config):
    mapping = DeviceMapping("resistor", ("p", "n"), ("positive", "negative"), {"resistance": "r"})
    parser = SpectreParser(replace(config, models={"custom": mapping}))
    data = to_pyg(parser.parse_text("renamed (a 0) custom resistance=1k"))
    restored = Batch.from_data_list([data, data]).to_data_list()
    assert restored[1].graph_metadata.writeback_names == (("renamed", "r", "resistance"),)
    assert restored[1].graph_metadata.device_definitions[0].model_ref == "custom"
