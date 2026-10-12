"""A size the optimizer's grid does not hold as a start (record 7.333): what a run would start a varied row from, asked
of the optimizer package's own legalization, and the words a person is told when that is not the circuit's own value.

A leaf: `compile.build_graph` raises with these words where Save task, Check now and Start all pass, and `validation`
marks the row with them - and `compile` imports `validation`, so the functions cannot live in either.
"""
from __future__ import annotations

import math

from . import units


def start_off_grid(lower, upper, step, value, integer=False):
    """The value the optimizer would START a varied row from when that is not the circuit's own value; None when it is
    the same (within the tolerance of the optimizer's own start check, `sizing.same_parameters`). Canonical units.
    A run starts from the circuit as it stands and first compares what the cell holds with what the optimizer's grid
    makes of it (`CircuitGraph.assignments` -> `ParameterGroup.project`). `project` counts the grid's steps from the
    lower bound in floats, and for bounds whose floats divide to a hair under a whole number - 13.75 .. 137.5 um in
    5 nm steps: 24749.999999999993 - the grid ends ONE STEP UNDER the upper bound. A cell that sits on that bound then
    differs from its own start design, and every run of the task, its baseline first, was refused with "Initial backend
    parameters differ from the reference graph" (record 7.320: the pass transistor of a ported LDO). The count is the
    optimizer package's and stays as it is (its source digest); this is what lets the workbench say so in words before
    a task is saved or a run is tried. It ASKS the package's own `project`, on a group of these numbers, so it cannot
    drift from it. `compile.grid_top` is the opposite case: a top that lands above the bound."""
    from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
    try:
        start = ParameterGroup('row', 'w', 'm', value, lower, upper, (ParameterBinding('row', 'w'),),
                               domain='integer' if integer else 'continuous', step=step).project(value)
    except ValueError:
        return None                                   # a row the optimizer refuses for another reason says so itself
    return None if math.isclose(start, value, rel_tol=1e-8, abs_tol=1e-24) else start


def start_words(row, value, start) -> str:
    """What a person is told when the circuit's value of a varied row is not one the optimizer starts from
    (`start_off_grid`): the row, both values in the row's own units, and what to do."""
    canonical = units.canonical_unit(row.unit)
    show = lambda v: units.text(float(f'{v:.12g}'), canonical)           # noqa: E731 - without the float's last digits
    typed = lambda v: units.text(v, row.unit)                             # noqa: E731
    grid = f'{typed(row.step)} steps from {typed(row.lower)}' if row.step else f'whole numbers from {typed(row.lower)}'
    on_bound = math.isclose(value, units.to_canonical(row.upper, row.unit), rel_tol=1e-8, abs_tol=1e-24)
    return (f'{row.variable_id}: the circuit has {show(value)} on {row.instance_path}.{row.parameter_name}'
            + (', which is this row\'s upper bound, but ' if on_bound else ', but ')
            + f'the optimizer\'s grid for the row ({grid}) '
            + (f'ends at {show(start)}, one step under that bound' if on_bound else f'gives {show(start)} for it')
            + '. A run starts from the circuit as it stands and would be refused: set this size to '
            + f'{show(start)} in the cell, or move the bound.')


def row_start_issue(row, value):
    """`start_words` for one optimized, independent Parameters row whose circuit value is `value` (canonical), or None.
    With the bound as typed: where the optimizer's top grid point lands a hair ABOVE it, `compile.build_graph` hands the
    optimizer that point as the bound (`compile.grid_top`) and the circuit's value is a start either way - the same
    answer, which the tests compare on thousands of ranges."""
    if row.lower is None or row.upper is None or not units.known(row.unit) or units.is_affine(row.unit):
        return None
    lower, upper = units.to_canonical(row.lower, row.unit), units.to_canonical(row.upper, row.unit)
    step = None if row.step is None else units.scale_to_canonical(row.step, row.unit)
    if not lower < upper or not all(math.isfinite(v) for v in (lower, upper, value)):
        return None
    start = start_off_grid(lower, upper, step, value, row.value_type == 'integer')
    return None if start is None else start_words(row, value, start)
