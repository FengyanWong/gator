from dataclasses import replace
import math

import pytest

from analog_optimizer.parameters import ActionMapper
from analog_optimizer.netlist.config import DeviceMapping
from analog_optimizer.netlist.spectre_parser import SpectreParser
import random
from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup


def test_linear_log_endpoints_fixed_groups_and_no_mutation(opamp):
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    mapper = ActionMapper(opamp)
    assert mapper.group_ids == ('input_pair_width',)
    for z, expected in [(-1, 1e-6), (0, math.sqrt(8) * 1e-6), (1, 8e-6)]:
        action = mapper.legalize({'input_pair_width': z})
        assert set(action.assignments) == {('input_left', 'w'), ('input_right', 'w')}
        assert list(action.assignments.values()) == pytest.approx([expected, expected])
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], scale='linear')
    assert ActionMapper(opamp).legalize({'input_pair_width': 0}).group_values['input_pair_width'] == pytest.approx(4.5e-6)
    assert opamp.parameters['input_left']['w'].value == 2e-6


@pytest.mark.parametrize('bad', [{}, {'extra': 0}, {'input_pair_width': float('nan')},
                                {'input_pair_width': float('inf')}, {'input_pair_width': True},
                                {'input_pair_width': -1.001}, {'input_pair_width': 1.001}])
def test_reject_invalid_proposals(opamp, bad):
    opamp.parameter_groups[1] = replace(opamp.parameter_groups[1], mutable=False)
    with pytest.raises(ValueError):
        ActionMapper(opamp).legalize(bad)


def test_integer_grid_ratio_and_source_alias(config):
    mapping = DeviceMapping('resistor', ('p', 'n'), ('positive', 'negative'), {'resistance': 'r'})
    group = {'id': 'pair', 'parameter_kind': 'r', 'unit': 'ohm', 'lower': 1, 'upper': 8,
             'domain': 'integer', 'step': 2, 'members': [{'device_id': 'A', 'parameter': 'r'},
             {'device_id': 'B', 'parameter': 'r', 'ratio': 2}]}
    graph = SpectreParser(replace(config, models={'custom': mapping}, parameter_groups=(group,))).parse_text(
        'A (a b) custom resistance=3\nB (b 0) custom resistance=6')
    action = ActionMapper(graph).legalize({'pair': 1})
    assert action.assignments == {('A', 'resistance'): 7, ('B', 'resistance'): 14}
    assert action.projected_groups == ('pair',) and action.proposal == {'pair': 1}


def test_no_active_actions_are_rejected(opamp):
    opamp.parameter_groups = [replace(g, mutable=False) for g in opamp.parameter_groups]
    with pytest.raises(ValueError, match='mutable'):
        ActionMapper(opamp)


def group(lower, upper, step, value=None):
    return ParameterGroup('g', 'width', 'm', lower if value is None else value, lower, upper,
                          (ParameterBinding('M1', 'w'),), step=step)


def old_project(g, value):
    """ParameterGroup.project before the clamp."""
    value = min(g.upper, max(g.lower, value))
    index = min(math.floor((g.upper - g.lower) / g.step + 1e-12), max(0, math.floor((value - g.lower) / g.step + 0.5)))
    return g.lower + index * g.step


def test_the_top_grid_point_of_a_range_typed_in_decimals_is_the_upper_bound():
    g = group(1.84e-6, 42.38e-6, 0.02e-6)
    assert old_project(g, g.upper) > g.upper                     # the old top: 4.2380000000000004e-05
    top = g.project(g.upper)
    assert top == g.upper and g.lower <= top <= g.upper
    replace(g, value=top).validate()                             # the group accepts its own top value


def test_every_other_projection_is_bitwise_what_it_was():
    rng = random.Random(20260930)
    for _ in range(20000):
        step = rng.choice([0.005, 0.01, 0.02, 0.05, 0.1]) * 1e-6
        lower = round(rng.uniform(0.2, 5) / (step * 1e6)) * step
        upper = float(f'{(lower + step * rng.randint(10, 3000)) * 1e6:.4f}') * 1e-6
        g = group(lower, upper, step)
        value = rng.uniform(lower - step, upper + step)
        old, new = old_project(g, value), g.project(value)
        assert new == old if old <= upper else new == upper


def test_a_mapper_that_reads_the_graph_as_it_is_legalizes_the_same(opamp):
    from analog_optimizer.parameters.actions import ActionMapper
    rng = random.Random(7)
    copied, shared = ActionMapper(opamp), ActionMapper(opamp, copy=False)
    for _ in range(200):
        proposal = {g: rng.uniform(-1, 1) for g in copied.group_ids}
        assert copied.legalize(proposal) == shared.legalize(proposal)
    assert shared._graph is opamp and copied._graph is not opamp
