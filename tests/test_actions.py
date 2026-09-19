from dataclasses import replace
import math

import pytest

from analog_optimizer.parameters import ActionMapper
from analog_optimizer.netlist.config import DeviceMapping
from analog_optimizer.netlist.spectre_parser import SpectreParser


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
