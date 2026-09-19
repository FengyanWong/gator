"""Read a netlist, optionally export via the synthetic Backend, then print tensors."""

from __future__ import annotations

import argparse
from pathlib import Path

from .backends.mock import MockBackend
from .netlist.config import ParserConfig
from .netlist.spectre_parser import SpectreParser


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("netlist", type=Path)
    cli.add_argument("--config", type=Path, required=True)
    cli.add_argument("--top", help="Select a declared subckt as the DUT")
    cli.add_argument("--mock-export", type=Path, metavar="WORK_ROOT",
                     help="Explicitly synthetic export through MockBackend (self-contained netlists only)")
    cli.add_argument("--no-pyg", action="store_true", help="Run parser-only without Torch/PyG")
    cli.add_argument("--homogeneous", action="store_true", help="Show the fixed-width neural Data view")
    args = cli.parse_args()
    path = args.netlist
    if args.mock_export:
        with MockBackend(path.read_text()) as backend:
            artifact = backend.generate_netlist(args.mock_export)
            path = artifact.path
            print(f"backend=mock origin={artifact.origin} job_id={artifact.job_id}")
    graph = SpectreParser(ParserConfig.from_file(args.config)).parse_file(path, top=args.top)
    if args.mock_export:
        graph.metadata["backend_origin"] = artifact.origin
        graph.metadata["backend_kind"] = "mock"
    print(f"CircuitGraph {graph.circuit_id}: complete={graph.complete}, schema={graph.schema_version}")
    print("Devices:")
    for device in graph.devices:
        print(f"  {device.id}: kind={device.kind}, model={device.model_ref}, source={device.source}")
        print(f"    parameters={graph.parameters[device.id]}")
    print("Nets:")
    for net in graph.nets:
        print(f"  {net.id}: roles={net.roles} ({net.role_source})")
    print("Terminal-aware edges:")
    for edge in graph.connections:
        print(f"  {edge.device_id}.{edge.terminal}[{edge.ordinal}] --{edge.role}--> {edge.net_id}")
    print("Parameter groups:")
    for group in graph.parameter_groups:
        print(f"  {group}")
    for diagnostic in graph.diagnostics:
        print(f"{diagnostic.severity}: {diagnostic.source}: {diagnostic.code}: {diagnostic.message}")
    if not args.no_pyg:
        try:
            from .graph.pyg_converter import to_pyg
        except ImportError as exc:
            cli.error(f"PyG dependencies unavailable; install the graph extra or use --no-pyg: {exc}")
        data = to_pyg(graph)
        print("Graph tensors (numeric x uses signed log1p(value/reference)):")
        for node in data.node_types:
            for name, tensor in data[node].items():
                print(f"  {node}.{name} = {tensor}")
        for edge in data.edge_types:
            print(f"  {edge}.edge_index = {data[edge].edge_index}")
        for name in ("group_x", "group_mask", "group_mutable", "group_kind", "group_member_index", "group_member_parameter", "group_member_ratio"):
            print(f"  {name} = {data[name]}")
        if args.homogeneous:
            from .graph.neural import as_homogeneous, node_feature_slices
            neural = as_homogeneous(data)
            print(f"Neural view: {neural.tensor_schema}, layout={node_feature_slices(data.graph_metadata.schema)}")
            for name in ('x', 'node_type', 'edge_index', 'edge_type', 'edge_attr', 'edge_weight',
                         'edge_ordinal', 'group_member_index'):
                print(f"  {name}: shape={tuple(neural[name].shape)}, dtype={neural[name].dtype}")


if __name__ == "__main__":
    main()
