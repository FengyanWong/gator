from dataclasses import replace

import pytest

from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
from analog_optimizer.netlist.config import DeviceMapping
from analog_optimizer.netlist.spectre_parser import SpectreParser


def test_matched_pair_has_one_independent_group_and_named_writeback(opamp):
    assert len(opamp.parameter_groups) == 2
    result = opamp.assignments({"input_pair_width": 3e-6})
    assert result == {("input_left", "w"): 3e-6, ("input_right", "w"): 3e-6}
    assert opamp.parameters["input_left"]["w"].value == 2e-6  # Mapping is pure, no hidden mutation.


def test_alias_writeback_and_ratio_binding(config):
    mapping = DeviceMapping("resistor", ("p", "n"), ("positive", "negative"), {"resistance": "r"})
    group = {"id": "pair", "parameter_kind": "r", "unit": "ohm", "lower": 100, "upper": 3000,
             "members": [{"device_id": "A", "parameter": "r"},
                         {"device_id": "B", "parameter": "r", "ratio": 2}]}
    parser = SpectreParser(replace(config, models={"custom": mapping}, parameter_groups=(group,)))
    graph = parser.parse_text("A (a b) custom resistance=1k\nB (b 0) custom resistance=2k")
    assert graph.assignments({"pair": 1500}) == {("A", "resistance"): 1500, ("B", "resistance"): 3000}


def test_unknown_device_cannot_be_optimized(config):
    group = {"id": "size", "parameter_kind": "w", "unit": "m", "lower": 1e-7, "upper": 2e-6,
             "members": [{"device_id": "X", "parameter": "w"}]}
    parser = SpectreParser(replace(config, parameter_groups=(group,)))
    with pytest.raises(ValueError, match="Unknown optimizable"):
        parser.parse_text("X (a b) unmapped w=1u")


def test_bounds_integer_grid_and_fixed_group():
    group = ParameterGroup("fingers", "nf", "1", 3, 1, 8, (ParameterBinding("Q", "nf"),), domain="integer", step=2)
    assert [group.project(v) for v in (-10, 1.9, 2.1, 100)] == [1, 1, 3, 7]
    assert replace(group, mutable=False).project(7) == 3
    with pytest.raises(ValueError):
        group.project(float("nan"))


def test_unknown_unresolved_duplicate_and_member_domain_conflicts(opamp):
    group = opamp.parameter_groups[0]
    with pytest.raises(ValueError, match="Unknown parameter group"):
        opamp.assignments({"missing": 1})
    opamp.parameter_groups = [group, replace(group, id="duplicate_binding")]
    with pytest.raises(ValueError, match="Conflicting"):
        opamp.validate()
    opamp.parameter_groups = [replace(group, members=(replace(group.members[0], upper=3e-6),))]
    with pytest.raises(ValueError, match="member upper"):
        opamp.validate()
    opamp.parameter_groups = [replace(group, members=(ParameterBinding("missing", "w"),))]
    with pytest.raises(ValueError, match="Unknown optimizable"):
        opamp.validate()
    opamp.parameter_groups = [group]
    opamp.parameters["input_left"]["w"] = replace(opamp.parameters["input_left"]["w"], value=None)
    with pytest.raises(ValueError, match="Unresolved"):
        opamp.validate()


@pytest.mark.parametrize("change", [{"lower": 0, "scale": "log"}, {"upper": 1e-7}, {"step": -1},
                                    {"value": float("inf")}, {"domain": "unsupported"}])
def test_invalid_group_domains(opamp, change):
    with pytest.raises(ValueError):
        replace(opamp.parameter_groups[0], **change).validate()
