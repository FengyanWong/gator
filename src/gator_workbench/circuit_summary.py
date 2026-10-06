"""An engineering summary of a parsed circuit - identifiers and numbers only - as the circuit panel shows it. Moved here
from the Agent tab's prompts on 2026-10-06 (record 7.226), which no longer exist."""
from __future__ import annotations

MAX_SUMMARY_DEVICES = 400


def circuit_summary(graph, *, circuit: dict | None = None) -> dict:
    """Engineering summary of a parsed circuit. Identifiers and numbers only."""
    devices = []
    connections = {}
    for c in graph.connections:
        connections.setdefault(c.device_id, []).append(dict(terminal=c.terminal, net=c.net_id, role=c.role))
    for device in graph.devices[:MAX_SUMMARY_DEVICES]:
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
    from .structures import recognize
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
