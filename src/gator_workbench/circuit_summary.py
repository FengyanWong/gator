"""An engineering summary of a parsed circuit - identifiers and numbers only - as the circuit panel shows it. Moved here
from the Agent tab's prompts on 2026-10-06 (record 7.226), which no longer exist."""
from __future__ import annotations
from .structures import recognize

MAX_SUMMARY_DEVICES = 400


def circuit_summary(graph, *, circuit: dict | None = None) -> dict:
    """Engineering summary of a parsed circuit. Identifiers and numbers only."""
    shown = graph.devices[:MAX_SUMMARY_DEVICES]
    shown_ids = {device.id for device in shown}
    devices = []
    connections = {}
    for c in graph.connections:
        device_id = c.device_id
        if device_id in shown_ids:
            # The summary shows at most 400 devices; do not allocate terminal records for the others.
            connections.setdefault(device_id, []).append(dict(terminal=c.terminal, net=c.net_id, role=c.role))
    for device in shown:
        devices.append(dict(
            instance_path=device.id, kind=device.kind, model=device.model_ref,
            terminals=connections.get(device.id, []),
            parameters={name: dict(value=value.value, expression=value.raw if value.value is None or not _is_number(value.raw) else None,
                                   resolved=value.valid)
                        for name, value in graph.parameters.get(device.id, {}).items()}))
    info = circuit or {}
    return dict(circuit_class=info.get('circuit_class'), pdk_id=info.get('pdk_id'),
                dut_hierarchy=info.get('dut_hierarchy'), device_count=len(graph.devices),
                truncated=len(graph.devices) > MAX_SUMMARY_DEVICES, devices=devices,
                nets=[dict(net=n.id, roles=list(n.roles)) for n in graph.nets],
                unknown_devices=[d.id for d in graph.devices if d.kind == 'unknown'],
                structures=_structures(graph),
                note='Port order and parameter semantics come from the verified device mapping. Structures are read from '
                     'the device types and pin roles (differential pairs, current mirrors, loads, cascodes, tails).')


def _structures(graph) -> list:
    """The matched structures of the circuit (structures.recognize, status record 7.103), one sentence each. A circuit
    they cannot be read from is summarized without them: the summary never fails because of this list."""
    try:
        return [s.text for s in recognize(graph)]
    except Exception:                                   # a graph without the usual pins: no structures, not no summary
        return []


def _is_number(text) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def loaded_circuit(runtime) -> dict:
    """A loaded task's circuit as the page shows it after "Load": the task, its source and simulator, the results it
    provides, its device hierarchy, its summary and diagnostics, and its profile's state."""
    graph = runtime.base_graph
    tree = {}
    for device in graph.devices:
        node = tree
        for part in device.id.split('/'):
            node = node.setdefault(part, {})
    return dict(task_key=runtime.task_key, mock=runtime.mock, circuit=runtime.circuit,
                simulator=runtime.circuit.get('simulator') or ('mock' if runtime.mock else 'spectre'),
                content_sha256=runtime.circuit.get('netlist_sha256'), provided_metrics=list(runtime.provided_metrics),
                hierarchy=tree, summary=circuit_summary(graph, circuit=runtime.circuit), complete=graph.complete,
                diagnostics=[dict(code=d.code, severity=d.severity, message=d.message) for d in graph.diagnostics],
                analysis_context=graph.metadata.get('analysis_context'), notes=runtime.notes,
                evaluation_backend=runtime.circuit.get('evaluation_backend'), max_concurrency=runtime.max_concurrency,
                native_draft=bool(runtime.circuit.get('native_draft')), generated_profile=bool(runtime.circuit.get('generated_profile')),
                baseline_recorded=runtime.circuit.get('baseline_recorded'), baseline_attempt=runtime.circuit.get('baseline_attempt'))
