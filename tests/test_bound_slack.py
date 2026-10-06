"""A value read from a netlist can sit one float step past the bound it equals (record 7.140): "180n" parses to
180 * 1e-9 = 1.8000000000000002e-07, above an upper bound of 1.8e-07. A real 4-lane run on mscr_ring3 stopped on its first
policy design, whose length was exactly that top value ("l: invalid bounds/current value"), and mscr_vco_lin the same."""
import pytest

from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
from analog_optimizer.netlist.expressions import evaluate


def group(value, lower=4.5e-08, upper=1.8e-07, step=5e-09):
    return ParameterGroup('l', 'length', 'm', value, lower, upper, (ParameterBinding('MN1', 'l'),), step=step)


def test_a_netlist_value_one_float_step_past_its_bound_counts_as_that_bound():
    top, bottom = evaluate('180n', {}.__getitem__), evaluate('45n', {}.__getitem__)
    assert top > 1.8e-07                                      # the parse itself is unchanged
    group(top).validate()                                     # was ValueError("l: invalid bounds/current value")
    group(bottom).validate()


@pytest.mark.parametrize('value', [1.85e-07, 1.8e-07 * (1 + 1e-9), 4.4e-08])
def test_a_value_really_outside_its_bounds_is_still_refused(value):
    with pytest.raises(ValueError, match='invalid bounds/current value'):
        group(value).validate()
