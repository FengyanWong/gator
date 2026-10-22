"""Circuit summaries allocate terminals only for shown devices and preserve the full graph's facts."""
from collections import Counter
from copy import deepcopy
import random
from types import SimpleNamespace

import pytest

from gator_workbench import circuit_summary as summary


def graph_of(count):
    """An invented four-terminal graph; no simulator, PDK or saved task is involved."""
    devices = [SimpleNamespace(id=f'synthetic/M{i}', kind='unknown' if i % 7 == 0 else 'resistor',
                               model_ref='mock-device') for i in range(count)]
    connections = [SimpleNamespace(device_id=device.id, terminal=f'P{pin}', net_id=f'n{index}-{pin}', role='unknown')
                   for index, device in enumerate(devices) for pin in range(4)]
    parameters = {device.id: dict(value=SimpleNamespace(value=1.0, raw='1', valid=True),
                                 expression=SimpleNamespace(value=None, raw='unresolved', valid=False))
                  for device in devices}
    return SimpleNamespace(devices=devices, connections=connections, parameters=parameters,
                           nets=[SimpleNamespace(id=c.net_id, roles=()) for c in connections],
                           metadata=dict(origin='synthetic', provenance='mock'))


def previous_summary(graph, circuit=None):
    """The previous complete response, retaining its unbounded intermediate connection map."""
    connections = {}
    for c in graph.connections:
        connections.setdefault(c.device_id, []).append(dict(terminal=c.terminal, net=c.net_id, role=c.role))
    devices = [dict(instance_path=device.id, kind=device.kind, model=device.model_ref,
                    terminals=connections.get(device.id, []),
                    parameters={name: dict(value=value.value,
                                           expression=value.raw if value.value is None or not summary._is_number(value.raw) else None,
                                           resolved=value.valid)
                                for name, value in graph.parameters.get(device.id, {}).items()})
               for device in graph.devices[:summary.MAX_SUMMARY_DEVICES]]
    info = circuit or {}
    return dict(circuit_class=info.get('circuit_class'), pdk_id=info.get('pdk_id'),
                dut_hierarchy=info.get('dut_hierarchy'), device_count=len(graph.devices),
                truncated=len(graph.devices) > summary.MAX_SUMMARY_DEVICES, devices=devices,
                nets=[dict(net=n.id, roles=list(n.roles)) for n in graph.nets],
                unknown_devices=[d.id for d in graph.devices if d.kind == 'unknown'],
                structures=summary._structures(graph),
                note='Port order and parameter semantics come from the verified device mapping. Structures are read from '
                     'the device types and pin roles (differential pairs, current mirrors, loads, cascodes, tails).')


@pytest.mark.parametrize('count', [0, 399, 400, 401, 4000])
@pytest.mark.parametrize('interleaved', [False, True])
def test_complete_summary_matches_before_across_projection_boundary(count, interleaved):
    graph = graph_of(count)
    if interleaved:
        random.Random(84).shuffle(graph.connections)
    circuit = dict(circuit_class='synthetic', pdk_id='mock', dut_hierarchy='synthetic')
    before_graph, before_circuit = deepcopy(graph), deepcopy(circuit)
    answer = summary.circuit_summary(graph, circuit=circuit)
    assert answer == previous_summary(graph, circuit)
    assert len(answer['devices']) == min(count, 400)
    assert len(answer['nets']) == 4 * count
    assert answer['unknown_devices'] == [d.id for d in graph.devices if d.kind == 'unknown']
    assert graph == before_graph and circuit == before_circuit


def test_missing_and_duplicate_device_ids_preserve_terminal_order():
    graph = graph_of(402)
    # A repeated identifier after the limit still contributes its connections to the shown device of that ID.
    graph.devices[-1].id = graph.devices[0].id
    for connection in graph.connections[-4:]:
        connection.device_id = graph.devices[0].id
    # Duplicate identifiers within the visible part also keep the original shared terminal list.
    graph.devices[2].id = graph.devices[0].id
    graph.connections = [c for c in graph.connections if c.device_id != graph.devices[1].id]
    graph.connections.append(SimpleNamespace(device_id='missing-device', terminal='P', net_id='orphan', role='unknown'))
    random.Random(54).shuffle(graph.connections)
    before = deepcopy(graph)
    answer = summary.circuit_summary(graph)
    assert answer == previous_summary(graph)
    assert answer['devices'][1]['terminals'] == []
    assert len(answer['devices'][0]['terminals']) == 8
    assert answer['devices'][0]['terminals'] is answer['devices'][2]['terminals']
    assert graph == before


def test_structure_recognition_still_sees_devices_after_the_display_limit():
    graph = graph_of(400)
    for name, kind, pins in [
        ('A', 'nmos', [('drain', 'left'), ('gate', 'in-a'), ('source', 'tail'), ('bulk', '0')]),
        ('B', 'nmos', [('drain', 'right'), ('gate', 'in-b'), ('source', 'tail'), ('bulk', '0')]),
        ('TAIL', 'isource', [('positive', 'tail'), ('negative', '0')]),
    ]:
        graph.devices.append(SimpleNamespace(id=name, kind=kind, model_ref='mock-mos'))
        graph.connections.extend(SimpleNamespace(device_id=name, terminal=role, net_id=net, role=role) for role, net in pins)
    graph.nets.extend(SimpleNamespace(id=net, roles=('ground',) if net == '0' else ())
                      for net in ('left', 'right', 'in-a', 'in-b', 'tail', '0'))
    answer = summary.circuit_summary(graph)
    assert answer == previous_summary(graph)
    assert answer['device_count'] == 403 and answer['truncated']
    assert answer['structures'] == ['A and B are a differential pair (gates in-a / in-b, shared source tail).']
    assert all(d['instance_path'] not in {'A', 'B', 'TAIL'} for d in answer['devices'])


def test_terminal_records_are_built_only_for_shown_device_ids(monkeypatch):
    graph = graph_of(4000)
    reads = Counter()

    class CountedConnection:
        def __init__(self, original):
            self.device_id = original.device_id
            self.original = original

        def __getattr__(self, name):
            reads[name] += 1
            return getattr(self.original, name)

    graph.connections = [CountedConnection(c) for c in graph.connections]
    # Isolate summary terminal construction; structure recognition intentionally scans the full graph separately.
    monkeypatch.setattr(summary, '_structures', lambda graph: [])
    answer = summary.circuit_summary(graph)
    assert sum(len(d['terminals']) for d in answer['devices']) == 1600
    assert reads == dict(terminal=1600, net_id=1600, role=1600)
    reads.clear()
    assert answer == previous_summary(graph)
    assert reads == dict(terminal=16000, net_id=16000, role=16000)
