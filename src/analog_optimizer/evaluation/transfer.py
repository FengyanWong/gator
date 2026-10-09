"""Frozen within-class and cross-category splits; no simulator execution here."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev

from analog_optimizer.graph.circuit_graph import CircuitGraph
from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator


def json_digest(value):
    """SHA-256 of a JSON value, keys sorted (of a file's bytes: backends.common.file_digest)."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


digest = json_digest        # the name the pinned examples import (plan-refactoring E8)


def topology_graph(graph):
    """Exact terminal incidence graph: names, sizes and group IDs are NOT labels.

    Terminal nodes preserve parallel D/G/S/B connections without relying on a
    lossy multiedge hash. Device kind and net roles retain declared semantics.
    """
    import networkx as nx
    result = nx.Graph()
    for device in graph.devices:
        result.add_node(('device', device.id), label=('device', device.kind))
    for net in graph.nets:
        result.add_node(('net', net.id), label=('net', tuple(sorted(net.roles))))
    for i, connection in enumerate(graph.connections):
        terminal = ('terminal', i)
        result.add_node(terminal, label=('terminal', connection.terminal, connection.ordinal, connection.role))
        result.add_edge(('device', connection.device_id), terminal)
        result.add_edge(terminal, ('net', connection.net_id))
    return result


def same_topology(first, second):
    import networkx as nx
    return nx.is_isomorphic(topology_graph(first), topology_graph(second),
                            node_match=lambda a, b: a['label'] == b['label'])


def spec_identity(specs):
    # Weight/scale changes do not create a new held-out specification.
    return tuple(sorted((s.metric_id, s.unit, s.comparator, s.lower, s.upper, s.required)
                        for s in specs if s.active))


@dataclass(frozen=True)
class TransferTask:
    id: str
    partition: str
    transfer: str
    family: str
    graph: CircuitGraph
    specs: tuple[MetricSpec, ...]
    circuit_class: str | None = None

    def __post_init__(self):
        if (not self.id or not self.family or self.partition not in ('train', 'validation', 'test')
                or self.transfer not in ('specification', 'topology', 'category')):
            raise ValueError('Invalid transfer task identity/partition')
        if self.circuit_class is not None and (not isinstance(self.circuit_class, str) or not self.circuit_class.strip()):
            raise ValueError('Circuit class must be a nonempty explicit label')
        if self.transfer == 'category' and (self.partition != 'test' or self.circuit_class is None):
            raise ValueError('Category transfer requires a test task with an explicit circuit class')
        self.graph.validate()
        SpecificationEvaluator(self.specs)


def validate_split(tasks):
    if len({t.id for t in tasks}) != len(tasks):
        raise ValueError('Task IDs must be unique')
    if {t.partition for t in tasks} != {'train', 'validation', 'test'}:
        raise ValueError('Freeze train, validation and test tasks before running')
    training = [t for t in tasks if t.partition == 'train']
    cross_category = any(t.transfer == 'category' for t in tasks)
    if cross_category and any(t.circuit_class is None for t in tasks):
        raise ValueError('Cross-category protocols require explicit circuit classes on every task')
    development_classes = {t.circuit_class for t in tasks if t.partition != 'test'}
    for i, task in enumerate(tasks):
        if task.transfer == 'category' and task.circuit_class in development_classes:
            raise ValueError('Held-out category appears in train or validation')
        if task.partition != 'train' and task.transfer != 'category' and not any(
                t.family == task.family and t.circuit_class == task.circuit_class for t in training):
            raise ValueError('M5 requires a training circuit in the same declared family')
        seen = [t for t in training if same_topology(task.graph, t.graph)]
        if task.partition != 'train' and task.transfer == 'specification' and not seen:
            raise ValueError('Specification transfer must use a training topology')
        for other in tasks[:i]:
            equivalent = same_topology(task.graph, other.graph)
            if task.circuit_class != other.circuit_class and (task.family == other.family or equivalent):
                raise ValueError('Circuit class relabeling cannot change a topology or its family')
            if task.partition == other.partition:
                continue
            if equivalent and spec_identity(task.specs) == spec_identity(other.specs):
                raise ValueError('Leaked topology/specification pair across partitions')
            if equivalent and any(t.transfer in ('topology', 'category') and t.partition != 'train'
                                  for t in (task, other)):
                raise ValueError('Held-out topology is isomorphic to another partition')


def freeze_protocol(path, tasks, settings):
    validate_split(tasks)
    version = 'm6-cross-category-v1' if any(t.transfer == 'category' for t in tasks) else 'm5-transfer-v1'
    payload = dict(version=version, tasks=[asdict(t) for t in tasks], settings=settings)
    payload['sha256'] = json_digest(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
    return payload['sha256']


def summarize_run(records, *, calls, wall_seconds, budget):
    """Include reset, failures, duplicates and right-censored runs in cost."""
    valid = [r for r in records if r.get('evaluation_valid') and r.get('reward') is not None]
    successes = [r for r in valid if r.get('success')]
    first = successes[0] if successes else None
    best = max(valid, key=lambda r: r['reward']) if valid else None
    curve, best_reward = [], None
    for row in records:
        if row in valid:
            best_reward = row['reward'] if best_reward is None else max(best_reward, row['reward'])
        curve.append(dict(call=row.get('simulation_calls'), best_reward=best_reward))
    failures = {}
    for row in records:
        if row.get('status') != 'ok' or not row.get('evaluation_valid'):
            key = row.get('status', row.get('state', 'unknown'))
            failures[key] = failures.get(key, 0) + 1
    return dict(success=bool(first), calls=calls, call_budget=budget, wall_seconds=wall_seconds,
                first_feasible_call=None if first is None else first['simulation_calls'],
                time_to_first_feasible_seconds=None if first is None else first['time_from_start_seconds'],
                right_censored=first is None, censor_call=calls, censor_seconds=wall_seconds,
                valid_evaluations=len(valid), failure_counts=failures,
                duplicate_candidates=sum(bool(r.get('duplicate_of')) for r in records),
                best_reward=None if best is None else best['reward'],
                best_metrics=None if best is None else best['metrics'],
                best_metric_units=None if best is None else best['metric_units'],
                best_parameters=None if best is None else best['applied_parameters'],
                worst_normalized_violation=None if best is None else max(
                    (v for v in best['violations'].values() if v is not None), default=None),
                best_so_far=curve)


def aggregate_runs(runs):
    """Per task/method; never pool distinct test tasks as independent seeds."""
    groups = {}
    for run in runs:
        groups.setdefault((run['task'], run['method']), []).append(run)
    result = []
    for (task, method), rows in sorted(groups.items()):
        n, k = len(rows), sum(r['success'] for r in rows)
        z = 1.959963984540054
        center = (k / n + z * z / (2 * n)) / (1 + z * z / n)
        radius = z * math.sqrt(k / n * (1 - k / n) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        rewards = [r['best_reward'] for r in rows if r['best_reward'] is not None]
        result.append(dict(task=task, method=method, seeds=[r['seed'] for r in rows], runs=n,
                           success_rate=k / n, success_wilson_95=[max(0, center-radius), min(1, center+radius)],
                           censored_runs=n-k, calls=sum(r['calls'] for r in rows),
                           wall_seconds=sum(r['wall_seconds'] for r in rows),
                           best_reward_mean=mean(rewards) if rewards else None,
                           best_reward_std=stdev(rewards) if len(rewards) > 1 else None,
                           first_feasible_calls=[r['first_feasible_call'] for r in rows],
                           time_to_first_feasible_seconds=[r['time_to_first_feasible_seconds'] for r in rows]))
    return result
