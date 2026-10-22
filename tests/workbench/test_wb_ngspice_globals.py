"""Synthetic deck parsing only; no simulator or included model files."""
from dataclasses import replace

import pytest

from gator_workbench import ngspice_netlist as ng


@pytest.mark.parametrize('declaration', ['.global VDD vDd', '.GLOBAL vDd VDD'])
def test_globals_keep_first_used_spelling_and_ports_override_global_names(declaration):
    deck = f'''Synthetic global wiring
.subckt leaf VDD b
r1 vdd internal 1k
r2 INTERNAL b 2k
r3 vDd GND 3k
.ends
.subckt wrapper a b
xinner a b leaf
r4 VdD b 4k
.ends
xouter INPUT 0 wrapper
vsource vdd 0 1
{declaration}
.end
'''
    graph = ng.parse_text(deck, scan_includes=False).graph
    assert [net.id for net in graph.nets] == ['INPUT', '0', 'xouter/xinner/internal', 'GND', 'VdD']
    wires = {}
    for connection in graph.connections:
        wires.setdefault(connection.device_id, []).append(connection.net_id)
    assert wires == {
        'xouter/xinner/r1': ['INPUT', 'xouter/xinner/internal'],
        'xouter/xinner/r2': ['xouter/xinner/internal', '0'],
        'xouter/xinner/r3': ['INPUT', 'GND'],
        'xouter/r4': ['VdD', '0'], 'vsource': ['VdD', '0'],
    }
    assert graph.metadata['globals'] == sorted(['0', 'gnd', 'VDD', 'vDd'])


def test_global_names_are_local_to_each_parse():
    deck = 'Synthetic scopes\n.subckt leaf a\nr1 Shared a 1k\n.ends\nx1 0 leaf\n{}\n.end\n'
    assert [net.id for net in ng.parse_text(deck.format('.global SHARED'), scan_includes=False).graph.nets] == ['0', 'Shared']
    assert [net.id for net in ng.parse_text(deck.format(''), scan_includes=False).graph.nets] == ['0', 'x1/Shared']


def test_declared_global_names_are_normalized_once_per_parse(monkeypatch):
    calls = []

    class Name(str):
        def lower(self):
            calls.append(str(self))
            return super().lower()

    original = ng.statements

    def tracked(lines):
        title, statements, control, control_lines = original(lines)
        statements = [([row[0]] + [replace(token, text=Name(token.text)) for token in row[1:]])
                      if row[0].text.lower() == '.global' else row for row in statements]
        return title, statements, control, control_lines

    monkeypatch.setattr(ng, 'statements', tracked)
    deck = 'Synthetic resistor chain\n.global SUPPLY Return\n' + ''.join(
        f'r{i} n{i} n{i + 1} 1k\n' for i in range(256)) + '.end\n'
    parsed = ng.parse_text(deck, scan_includes=False)
    assert len(parsed.graph.devices) == 256
    assert sorted(calls) == ['Return', 'SUPPLY']
