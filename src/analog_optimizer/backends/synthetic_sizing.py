"""Explicit analytic toy backend for M4 plumbing; it is NOT a circuit solver."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .backend import VirtuosoBackend, NetlistArtifact, SimulationResult, SimulationStatus, BackendNotConnected


class SyntheticSizingBackend(VirtuosoBackend):
    """Evaluates a bounded quadratic score of executed normalized group values.

    Targets are declared per parameter kind, never inferred from instance names.
    This checks learning interfaces, not electrical behavior or optimization merit.
    """
    def __init__(self, graph, *, targets):
        graph.validate()
        self.graph = deepcopy(graph)
        self.targets = dict(targets)
        for group in graph.parameter_groups:
            if group.mutable and (group.parameter_kind not in targets or
                                  not math.isfinite(targets[group.parameter_kind]) or
                                  not -1 <= targets[group.parameter_kind] <= 1):
                raise ValueError('Each active parameter kind needs an explicit normalized toy target')
        self.initial = graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})
        self.parameters, self.exports = dict(self.initial), {}
        self.connected, self.calls = False, 0

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def _check(self):
        if not self.connected:
            raise BackendNotConnected('Synthetic sizing backend is not connected')

    def restore(self):
        self._check()
        self.parameters = dict(self.initial)

    def read_parameters(self):
        self._check()
        return dict(self.parameters)

    def set_parameters(self, parameters):
        self._check()
        if parameters.keys() != self.initial.keys() or not all(math.isfinite(v) for v in parameters.values()):
            raise ValueError('Unexpected synthetic parameter assignment')
        self.parameters = dict(parameters)

    def generate_netlist(self, work_root):
        self._check()
        job_id = uuid4().hex
        directory = Path(work_root) / job_id
        directory.mkdir(parents=True)
        path = directory / 'synthetic-parameters.json'
        path.write_text(json.dumps({'origin': 'synthetic', 'parameters': sorted(self.parameters.items()),
                                    'targets': self.targets}, allow_nan=False))
        artifact = NetlistArtifact(path, job_id, hashlib.sha256(path.read_bytes()).hexdigest(), 'synthetic')
        self.exports[job_id] = (artifact, dict(self.parameters))
        return artifact

    def get_circuit_graph(self, artifact):
        self._check()
        saved, values = self.exports[artifact.job_id]
        if artifact != saved or hashlib.sha256(artifact.path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError('Synthetic export identity changed')
        graph = deepcopy(self.graph)
        for i, group in enumerate(graph.parameter_groups):
            if not group.mutable:
                continue
            for member in group.members:
                old = graph.parameters[member.device_id][member.parameter]
                value = values[member.device_id, old.source_name or member.parameter]
                graph.parameters[member.device_id][member.parameter] = replace(old, value=value, raw=str(value))
            graph.parameter_groups[i] = replace(group, value=value / member.ratio)
        graph.validate()
        return graph

    def run_simulation(self, request):
        self._check()
        self.validate_condition(request.condition)
        started = perf_counter()
        graph = self.get_circuit_graph(request.netlist)
        exported = self.exports[request.netlist.job_id][1]
        if request.parameters != exported:
            raise ValueError('Synthetic request parameters differ from export')
        errors = []
        for group in graph.parameter_groups:
            if not group.mutable:
                continue
            value, lower, upper = group.value, group.lower, group.upper
            if group.scale == 'log':
                value, lower, upper = map(math.log, (value, lower, upper))
            z = 2 * (value - lower) / (upper - lower) - 1
            errors.append(((z - self.targets[group.parameter_kind]) / 2) ** 2)
        score = 1 - sum(errors) / len(errors)
        directory = request.work_root / uuid4().hex
        directory.mkdir(parents=True)
        self.calls += 1
        return SimulationResult(directory.name, 'analytic-toy-sizing-v1', 'synthetic', SimulationStatus.OK,
                                'synthetic_quadratic_not_circuit_simulation', False, True,
                                {'score': score}, {'score': 'fixture'}, {'score': True},
                                dict(exported), directory, perf_counter() - started)
