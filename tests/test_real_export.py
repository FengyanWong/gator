"""Saved OTA export and subcircuit syntax checks that read local files without contacting Virtuoso or Spectre."""

from pathlib import Path
import pytest

from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import ParseError, SpectreParser

ROOT = Path(__file__).resolve().parents[1]


def test_gpdk045_export_connectivity_dimensions_and_matching():
    config = ParserConfig.from_file(ROOT / 'configs/gpdk045_opamp.json')
    graph = SpectreParser(config).parse_file(ROOT / 'examples/circuits/gpdk045_ota5.scs')
    graph.validate()
    assert len(graph.devices) == 10
    assert len(graph.nets) == 8
    assert len(graph.connections) == 30
    assert len(graph.parameter_groups) == 3
    terms = {(c.device_id, c.terminal): c.net_id for c in graph.connections}
    assert terms['XU1/M5', 'S'] == terms['XU1/M5', 'B'] == '0'
    assert terms['XU1/M3', 'D'] == terms['XU1/M3', 'G'] == 'XU1/NLOAD'
    assert terms['XU1/M1', 'S'] == terms['XU1/M2', 'S'] == terms['XU1/M5', 'D'] == 'XU1/NTAIL'
    assert terms['XU1/M2', 'D'] == terms['XU1/M4', 'D'] == 'VOUT'
    assert graph.parameters['XU1/M1']['w'].value == pytest.approx(4e-6)
    assert graph.parameters['XU1/M4']['w'].value == pytest.approx(8e-6)
    assert graph.parameters['XU1/M5']['l'].value == pytest.approx(1e-6)
    assert graph.assignments({'input_pair_width': 5e-6}) == {
        ('XU1/M1', 'w'): 5e-6, ('XU1/M2', 'w'): 5e-6}


@pytest.mark.parametrize('header', ['subckt s a a', 'subckt s a w=1u', 'subckt s a )'])
def test_malformed_bare_subckt_is_rejected(parser, header):
    with pytest.raises(ParseError):
        parser.parse_text(header + '\nends s\n')


def test_bare_subckt_and_parenthesized_ports_are_equivalent(parser):
    template = 'subckt s PORTS\nR (a b) resistor r=1k\nends s\nX (in 0) s\n'
    bare = parser.parse_text(template.replace('PORTS', 'a b'))
    bracketed = parser.parse_text(template.replace('PORTS', '(a b)'))
    assert [(c.device_id, c.terminal, c.net_id) for c in bare.connections] == [
        (c.device_id, c.terminal, c.net_id) for c in bracketed.connections]
