from dataclasses import replace

import pytest

from analog_optimizer.netlist.config import DeviceMapping
from analog_optimizer.netlist.expressions import UnresolvedExpression, evaluate
from analog_optimizer.netlist.spectre_parser import ParseError, SpectreParser
from conftest import FIXTURES


@pytest.mark.parametrize("name,count", [("opamp", 7), ("ldo", 6), ("vco", 10)])
def test_same_parser_for_three_structures(parser, name, count):
    graph = parser.parse_file(FIXTURES / f"{name}.scs")
    graph.validate()
    assert len(graph.devices) == count
    assert graph.metadata["source_manifest"]
    assert not graph.diagnostics


def test_ports_preserved_and_not_inferred_from_instance_prefix(parser):
    graph = parser.parse_text("R_named (d g 0 0) nmos_demo w=1u l=180n\nM_named (a b) resistor r=1k")
    mos = graph.devices[0]
    assert mos.kind == "nmos"
    assert mos.terminals == ("D", "G", "S", "B")
    shared = [c for c in graph.connections if c.device_id == "R_named" and c.net_id == "0"]
    assert [(c.terminal, c.role) for c in shared] == [("S", "source"), ("B", "bulk")]
    assert graph.devices[1].kind == "resistor"


def test_mapping_controls_order_and_aliases(config):
    mapping = DeviceMapping("nmos", ("G", "S", "D", "B"), ("gate", "source", "drain", "bulk"), {"width": "w"})
    parser = SpectreParser(replace(config, models={"custom": mapping}))
    graph = parser.parse_text("anything (a b c b) custom width=3u")
    assert graph.connections[0].role == "gate"
    assert graph.parameters["anything"]["w"].value == pytest.approx(3e-6)
    assert graph.parameters["anything"]["w"].source_name == "width"


def test_comments_continuation_expressions_sources(parser):
    graph = parser.parse_text('// heading\nparameters base=1u twice=2*base\nQ (d g 0 0) nmos_demo w = (twice + base) \\\n  l=200n nf=2 // tail\n', source="demo.scs")
    values = graph.parameters["Q"]
    assert values["w"].value == pytest.approx(3e-6)
    assert values["l"].source.line == 4
    assert graph.devices[0].source.line == 3
    assert values["w"].raw == "( twice + base )"


@pytest.mark.parametrize("raw,expected", [("1M", 1e6), ("1m", 1e-3), ("2K", 2e3), ("2k", 2e3),
                                          (".5u", .5e-6), ("1e-3", .001), ("-2.5", -2.5),
                                          ("'2*3u'", 6e-6), ("{2*3u}", 6e-6), ("2**3", 8)])
def test_numeric_subset(raw, expected):
    assert evaluate(raw, lambda key: 0) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["1meg", "1um", "abs(-1)", "1/0", "2**1000000", "1e999", "__import__('os')"])
def test_unsafe_or_unsupported_expressions_are_not_executed(raw):
    with pytest.raises(UnresolvedExpression):
        evaluate(raw, lambda key: 0)


def test_unresolved_parameters_are_preserved(parser):
    graph = parser.parse_text("parameters a=b b=a\nQ (d g 0 0) nmos_demo w=a l=missing nf=2")
    assert graph.parameters["Q"]["w"].value is None
    assert "Cyclic" in graph.parameters["Q"]["w"].reason
    assert graph.parameters["Q"]["l"].raw == "missing"
    assert len(graph.diagnostics) == 2


def test_hierarchy_scope_global_ports_and_overrides(parser):
    graph = parser.parse_file(FIXTURES / "vco.scs")
    names = {n.id for n in graph.nets}
    assert {"stage_a/local", "stage_b/local", "stage_c/local"} <= names
    assert "stage_a/vdd" not in names and "stage_a/0" not in names
    assert graph.parameters["stage_b/pull_down"]["w"].value == pytest.approx(2e-6)
    assert graph.parameters["stage_b/pull_up"]["w"].value == pytest.approx(4e-6)
    assert next(c.net_id for c in graph.connections if c.device_id == "stage_b/pull_down" and c.role == "gate") == "n1"


def test_subckt_default_dependencies_and_selected_top(parser):
    source = """parameters w=10u
subckt cell (i o)
parameters w=1u derived=2*w
Q (o i 0 0) nmos_demo w=derived l=1u
ends cell
X (a b) cell w=w
"""
    assert parser.parse_text(source).parameters["X/Q"]["w"].value == pytest.approx(20e-6)
    top = parser.parse_text(source, top="cell")
    assert top.parameters["Q"]["w"].value == pytest.approx(2e-6)
    assert top.metadata["ports"] == ("i", "o")
    assert "X/Q" not in top.parameters


def test_unknown_device_is_retained_but_incomplete(parser):
    graph = parser.parse_text("M1 (a b a) unrecognized p=3")
    assert len(graph.devices) == 1 and len(graph.connections) == 3
    assert graph.devices[0].kind == "unknown"
    assert [c.ordinal for c in graph.connections] == [0, 1, 2]
    assert graph.diagnostics[0].code == "unknown_device"
    with pytest.raises(ValueError, match="Incomplete"):
        graph.validate()


@pytest.mark.parametrize("text,reason", [
    ("simulator lang=spice", "dialect"),
    ("simulator lang=spectre\nsimulator lang=spice", "dialect"),
    ("Q (d g s) nmos_demo", "port count"),
    ("Q (d g 0 0) nmos_demo w=", "Empty"),
    ("Q (d g 0 0) nmos_demo w=1 w=2", "Duplicate"),
    ("X (a b) resistor r=1\nX (a b) resistor r=2", "Duplicate instance"),
    ("subckt s (a)\nX (a) s\nends s\nY (b) s", "Recursive"),
    ("subckt s (a)\nends wrong", "Mismatched"),
    ("subckt s (a)\n", "Unclosed"),
    ("subckt s (a)\nends s\nX (a) s m=2", "Undeclared"),
    ("model n bsim4", "Unsupported statement"),
    ("statistics {", "Unsupported statement"),
])
def test_located_errors(parser, text, reason):
    with pytest.raises(ParseError, match=reason) as error:
        parser.parse_text(text, source="bad.scs")
    assert "bad.scs:" in str(error.value)


def test_include_relative_allowed_root_cycle_and_depth(config, tmp_path):
    main = tmp_path / "main.scs"
    child = tmp_path / "child.scs"
    main.write_text('include "child.scs"\n')
    child.write_text("R (a 0) resistor r=2k")
    parser = SpectreParser(replace(config, include_roots=(tmp_path,)))
    graph = parser.parse_file(main)
    assert graph.devices[0].source.file == str(child)
    assert len(graph.metadata["source_manifest"]) == 2
    with pytest.raises(ParseError, match="outside"):
        SpectreParser(config).parse_file(main)
    with pytest.raises(ParseError, match="depth"):
        SpectreParser(replace(config, include_roots=(tmp_path,), max_include_depth=0)).parse_file(main)
    child.write_text('include "main.scs"')
    with pytest.raises(ParseError, match="cycle"):
        parser.parse_file(main)


def test_include_symlink_escape_and_section_rejected(config, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.scs"
    outside.write_text("R (a 0) resistor r=1")
    (allowed / "link.scs").symlink_to(outside)
    main = allowed / "main.scs"
    main.write_text('include "link.scs"')
    parser = SpectreParser(replace(config, include_roots=(allowed,)))
    with pytest.raises(ParseError, match="outside"):
        parser.parse_file(main)
    main.write_text('include "link.scs" section=tt')
    with pytest.raises(ParseError, match="sections"):
        parser.parse_file(main)


def test_analysis_context_preserved_and_no_name_role_guessing(parser):
    graph = parser.parse_text("R (VDD 0) resistor r=1\nac1 ac start=1 stop=1G\nsave VDD")
    assert len(graph.metadata["analysis_context"]) == 2
    assert next(n for n in graph.nets if n.id == "VDD").roles == ("normal",)
