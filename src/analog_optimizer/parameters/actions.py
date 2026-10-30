from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from collections.abc import Mapping

from analog_optimizer.graph.circuit_graph import CircuitGraph


@dataclass(frozen=True)
class LegalizedAction:
    proposal: dict[str, float]
    group_values: dict[str, float]
    assignments: dict[tuple[str, str], float]
    projected_groups: tuple[str, ...]
    version: str = 'absolute-group-v1'


class ActionMapper:
    """Absolute [-1, 1] proposals; physical grid projection uses group.project.

    Only mutable groups receive actions. Names are binding IDs, not features.
    Fixed groups are never sent to the backend. Invalid proposals fail before I/O.
    """

    def __init__(self, graph: CircuitGraph, *, copy: bool = True):
        graph.validate()
        # copy=False: a mapper used at once and dropped (a replay check) reads the graph as it is - nothing here changes it.
        self._graph = deepcopy(graph) if copy else graph
        self.groups = tuple(g for g in graph.parameter_groups if g.mutable)
        self.group_ids = tuple(g.id for g in self.groups)
        if not self.groups:
            raise ValueError('An environment needs at least one mutable parameter group')

    def legalize(self, proposal: Mapping[str, float]) -> LegalizedAction:
        if set(proposal) != set(self.group_ids):
            raise ValueError('Action must contain exactly the mutable group IDs')
        proposed, values, projected = {}, {}, []
        for group in self.groups:
            z = proposal[group.id]
            if isinstance(z, bool) or not isinstance(z, (int, float)) or not math.isfinite(z) or not -1 <= z <= 1:
                raise ValueError(f'{group.id}: action must be finite and inside [-1, 1]')
            proposed[group.id] = float(z)
            fraction = (z + 1) / 2
            if z in (-1, 1):
                physical = group.lower if z == -1 else group.upper
            elif group.scale == 'log':
                physical = math.exp((1 - fraction) * math.log(group.lower) + fraction * math.log(group.upper))
            else:
                physical = (1 - fraction) * group.lower + fraction * group.upper
            values[group.id] = group.project(physical)
            if not math.isclose(values[group.id], physical, rel_tol=1e-12, abs_tol=0):
                projected.append(group.id)
        assignments = self._graph.assignments(values)
        if any(not math.isfinite(v) for v in assignments.values()):
            raise ValueError('Non-finite physical assignment')
        return LegalizedAction(proposed, values, assignments, tuple(projected))
