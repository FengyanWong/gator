"""Packed observations with bounded raw-input caches; no fitted statistics or embeddings."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import math
import pickle

import torch
from torch_geometric.data import Batch

from analog_optimizer.envs.sizing import ConditionResult, Observation
from analog_optimizer.graph.pyg_converter import CircuitHeteroData, FeatureSchema, TopologyTensorCache, to_pyg
from analog_optimizer.graph.neural import port_edge_tensors
from analog_optimizer.measurements.specs import SpecificationEvaluator


SPEC_INPUT_LAYOUT = 'spec-input-v2'   # 21 columns per registry slot + 11: what this code computes, whatever the registry is called


@dataclass(frozen=True)
class SpecSchema:
    version: str = 'spec-input-v1'    # the default registry's name since M4 (identity); it does not choose the column layout
    # Registry position carries metric identity; values never use instance names.
    metrics: tuple[tuple[str, str, float], ...] = (
        ('score', 'fixture', 1.0),
        ('gain_db_at_start', 'dB', 20.0),
        ('unity_gain_hz', 'Hz', 1e6),
        ('phase_margin_estimate_deg', 'deg', 90.0),
        ('supply_power_w', 'W', 1e-6),
        ('output_dc_v', 'V', 1.0),
        ('unity_downward_crossings', 'count', 1.0),
    )
    layout: str = SPEC_INPUT_LAYOUT   # recorded in every checkpoint contract; a v1 checkpoint is refused by its checkpoint_version

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version:
            raise ValueError('A metric registry needs a version label')
        if self.layout != SPEC_INPUT_LAYOUT:
            raise ValueError(f'Unsupported spec input layout {self.layout!r}: this code computes {SPEC_INPUT_LAYOUT}; '
                             'an older layout needs an explicit migration')
        if not self.metrics or len({m[0] for m in self.metrics}) != len(self.metrics):
            raise ValueError('Metric registry must be nonempty and unique')
        if any(not name or not unit or not math.isfinite(ref) or ref <= 0
               for name, unit, ref in self.metrics):
            raise ValueError('Each metric needs identity, unit and a positive reference')

    @property
    def width(self):
        return len(self.metrics) * 21 + 11


def signed_log(value, reference):
    ratio = abs(value / reference)
    magnitude = math.log1p(ratio) if math.isfinite(ratio) else math.log(abs(value)) - math.log(reference)
    return math.copysign(magnitude, value)


def validate_observation(observation):
    if not isinstance(observation, Observation):
        raise ValueError('A sizing Observation is required')
    if observation.origin not in ('real', 'synthetic'):
        raise ValueError('Explicit observation origin required')
    if observation.condition is not None and not observation.condition.nominal_only:
        raise ValueError('Model/replay inputs are nominal-only')
    if observation.origin == 'real' and observation.condition is None:
        raise ValueError('Real observations require a nominal condition')
    metadata_condition = observation.graph.metadata.get('simulation_condition')
    if metadata_condition is not None:
        from analog_optimizer.backends.conditions import SimulationCondition
        if SimulationCondition.from_dict(metadata_condition) != observation.condition:
            raise ValueError('Graph and observation conditions differ')
    if observation.status not in ('ok', 'invalid_design', 'nonconverged', 'measurement_error'):
        raise ValueError('Infrastructure/measurement failure is not a model state')
    if type(observation.remaining_steps) is not int or observation.remaining_steps < 0:
        raise ValueError('Invalid finite-horizon budget')
    if observation.graph.schema_version != '1.0':
        raise ValueError('Unsupported circuit graph schema')
    observation.graph.validate()
    SpecificationEvaluator(observation.specs, observation.reward_settings)
    if observation.condition_policy not in ('off', 'always', 'after_nominal'):
        raise ValueError('Unknown training condition policy')
    if not isinstance(observation.planned_conditions, tuple) or not isinstance(observation.condition_results, tuple):
        raise ValueError('Condition plans and results must be immutable ordered tuples')
    if observation.condition_policy != 'off' and len(observation.planned_conditions) < 2:
        raise ValueError('Robust training requires an explicit nominal-plus-corners plan')
    if observation.condition_policy == 'off' and len(observation.planned_conditions) > 1:
        raise ValueError('Corners require the always or after_nominal policy')
    if observation.condition_results:
        if not observation.planned_conditions or observation.planned_conditions[0] != observation.condition:
            raise ValueError('Observation must retain its full nominal-first plan')
        if any(not isinstance(row, ConditionResult) for row in observation.condition_results):
            raise ValueError('Typed condition results are required')
        if any(c is None or c.purpose != 'pvt_training' for c in observation.planned_conditions[1:]):
            raise ValueError('Post-validation conditions cannot enter training observations')
        nominal = observation.condition_results[0]
        if any(getattr(nominal, key) != getattr(observation, key) for key in (
                'condition', 'metrics', 'metric_units', 'metric_validity', 'status', 'job_id')):
            raise ValueError('Nominal observation differs from its retained result')
        observation.evaluation
    elif observation.condition_policy != 'off' or observation.planned_conditions:
        raise ValueError('A planned observation requires nominal measurement evidence')
    if observation.status == 'measurement_error' and (not observation.condition_results or not observation.evaluation.valid):
        raise ValueError('Only a scorable opted-in measurement failure is a model state')
    device_ids = {d.id for d in observation.graph.devices}
    if any(key not in device_ids for key in observation.operating_points):
        raise ValueError('Operating points must be mapped to graph devices')
    for values in observation.operating_points.values():
        if not isinstance(values, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                                              for v in values.values()):
            raise ValueError('Operating points must be filtered to finite quantities')


def context_features(observation, schema):
    validate_observation(observation)
    registry = {name: (i, unit, ref) for i, (name, unit, ref) in enumerate(schema.metrics)}
    features = torch.zeros((len(schema.metrics), 21))
    evaluation = observation.evaluation
    for spec in observation.specs:
        if spec.metric_id not in registry:
            raise ValueError(f'Unknown metric: {spec.metric_id}')
        index, unit, ref = registry[spec.metric_id]
        if spec.unit != unit:
            raise ValueError(f'Metric unit differs from schema: {spec.metric_id}')
        if not spec.active:
            continue  # Inactive targets/measurements cannot affect any output.
        value = observation.metrics.get(spec.metric_id)
        valid = observation.metric_validity.get(spec.metric_id) is True
        if valid and (not isinstance(value, (float, int)) or isinstance(value, bool)
                      or not math.isfinite(value) or observation.metric_units.get(spec.metric_id) != unit):
            raise ValueError('Valid measurement must be finite and have the registered unit')
        features[index] = torch.tensor([
            1, spec.required, spec.comparator == 'min', spec.comparator == 'max',
            spec.comparator == 'range', signed_log(spec.lower or 0, ref),
            signed_log(spec.upper or 0, ref), signed_log(spec.scale, ref),
            math.log1p(spec.weight), signed_log(value, ref) if valid else 0,
            valid, spec.lower is not None, spec.upper is not None,
            spec.objective == 'min', spec.objective == 'max',
            signed_log(evaluation.worst_values[spec.metric_id], ref) if evaluation.worst_valid[spec.metric_id] else 0,
            evaluation.worst_valid[spec.metric_id], 0, 0, 0, 0,
        ])
    condition = observation.condition
    extra = [math.log1p(observation.remaining_steps)]
    extra += [float(observation.status == s) for s in ('ok', 'invalid_design', 'nonconverged')]
    extra += ([1, condition.corner.temperature_c / 100, condition.corner.supply_v]
              if condition else [0, 0, 0])
    planned = len(observation.planned_conditions) or 1
    measured = len(observation.condition_results) or 1
    extra += [math.log1p(planned - 1), measured / planned, evaluation.nominal_success, evaluation.success]
    result = torch.cat((features.flatten(), torch.tensor(extra)))
    if not torch.isfinite(result).all():
        raise ValueError('Non-finite context features')
    return result


@dataclass
class GraphBatch:
    graph: Batch
    context: torch.Tensor
    node_batch: torch.Tensor
    edge_index: torch.Tensor
    edge_role: torch.Tensor
    edge_ordinal: torch.Tensor
    group_batch: torch.Tensor
    group_features: torch.Tensor
    active: torch.Tensor
    action_batch: torch.Tensor
    action_counts: torch.Tensor
    action_columns: torch.Tensor
    group_ids: tuple[tuple[str, ...], ...]

    @property
    def size(self):
        return len(self.group_ids)

    def pack_actions(self, padded):
        """Discard padding before arithmetic, including NaN padding."""
        if padded.ndim != 2 or padded.shape[0] != self.size or padded.shape[1] < int(self.action_counts.max()):
            raise ValueError('Padded action shape differs from active groups')
        return self.validate_actions(padded[self.action_batch, self.action_columns])

    def validate_actions(self, actions):
        if actions.shape != (self.active.numel(),) or not torch.isfinite(actions).all() or (actions.abs() > 1).any():
            raise ValueError('One finite normalized proposal per active group is required')
        return actions

    def proposals(self, actions):
        values = self.validate_actions(actions).detach().cpu().tolist()
        result, offset = [], 0
        for ids in self.group_ids:
            result.append(dict(zip(ids, values[offset:offset + len(ids)])))
            offset += len(ids)
        return result


@dataclass(frozen=True)
class _PreparedObservation:
    graph: CircuitHeteroData
    context: torch.Tensor
    group_features: torch.Tensor
    group_ids: tuple[str, ...]


def _prepare_observation(observation, feature_schema, spec_schema, topology_cache=None):
    context = context_features(observation, spec_schema)
    graph = to_pyg(observation.graph, feature_schema, topology_cache=topology_cache,
                   operating_points=observation.operating_points)
    group_ids = tuple(g.id for g in observation.graph.parameter_groups if g.mutable)
    if not group_ids:
        raise ValueError('SAC needs at least one active action per graph')
    features = []
    units = dict(zip(('w', 'l', 'm', 'nf', 'r', 'c', 'ind', 'dc'),
                     ('m', 'm', '1', '1', 'ohm', 'F', 'H', 'V')))
    for group in observation.graph.parameter_groups:
        # Unit is semantic: never silently interpret a length as capacitance.
        expected = units.get(group.parameter_kind)
        if expected is None or group.unit != expected:
            raise ValueError(f'Unsupported group unit: {group.parameter_kind}/{group.unit}')
        ref = feature_schema.references[feature_schema.parameters.index(group.parameter_kind)]
        features.append([signed_log(v, ref) for v in (group.value, group.lower, group.upper)] +
                        [signed_log(group.step or 0, ref), group.scale == 'log',
                         group.domain == 'integer', group.mutable, group.step is not None])
    group_features = torch.tensor(features, dtype=torch.float32)
    if not torch.isfinite(group_features).all():
        raise ValueError('Non-finite group features')
    return _PreparedObservation(graph, context, group_features, group_ids)


def observation_digest(observation):
    """Content digest of a whole observation: graph, sizes, goal, measurements and masks, budget, status, conditions and
    provenance. Two observations with equal content (a deepcopy included) get the same digest; any change to any
    field, nested ones included, gives another. Pickle is only used for local serialization/hashing."""
    return hashlib.sha256(pickle.dumps(observation, protocol=5)).digest()


def _tensor_bytes(prepared):
    """Bytes of the tensors one cached entry holds (each entry owns its tensors: the topology cache hands out copies)."""
    tensors = [prepared.context, prepared.group_features]
    tensors += [value for store in prepared.graph.stores for value in store.values() if isinstance(value, torch.Tensor)]
    return sum(t.element_size() * t.nelement() for t in tensors)


class ObservationTensorCache:
    """Learner-local LRU of deterministic CPU inputs, never learned representations.

    The key is a content digest of the feature/spec schemas plus one of the whole observation: it survives replay
    deepcopy and detects changes to nested mutable data. A caller hashes the observation on every lookup unless it
    passes the observation's digest itself, which only an owner that guarantees the observation stays unchanged may do
    (the replay buffer's learner path, ``ReplayBuffer.update_learner``, record 7.221). Pickle is only used for local
    serialization/hashing, never deserialization. Bounded by entries (``capacity``) and optionally by tensor bytes
    (``max_bytes``); eviction or a cold checkpoint restore only changes conversion cost.
    """

    def __init__(self, capacity=2048, *, topology_capacity=64, max_bytes=None):
        if type(capacity) is not int or capacity < 0:
            raise ValueError('Observation cache capacity must be a nonnegative integer')
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
            raise ValueError('Observation cache byte bound must be a nonnegative integer or None')
        self.capacity, self.max_bytes = capacity, max_bytes
        self._items = OrderedDict()         # key -> (prepared input, its tensor bytes)
        self._schema_keys = {}              # (feature schema, spec schema) -> digest; both are deeply immutable
        self.topologies = TopologyTensorCache(topology_capacity)
        self.hits = self.misses = self.evictions = self.tensor_bytes = 0

    def clear(self):
        self._items.clear()
        self._schema_keys.clear()
        self.topologies.clear()
        self.hits = self.misses = self.evictions = self.tensor_bytes = 0

    def info(self):
        return dict(hits=self.hits, misses=self.misses, entries=len(self._items), capacity=self.capacity,
                    evictions=self.evictions, tensor_bytes=self.tensor_bytes, max_bytes=self.max_bytes,
                    topologies=self.topologies.info())

    def _schema_key(self, feature_schema, spec_schema):
        pair = (feature_schema, spec_schema)    # hashable, as the topology cache's key already requires
        key = self._schema_keys.get(pair)
        if key is None:
            if len(self._schema_keys) >= 16:
                self._schema_keys.clear()
            key = self._schema_keys[pair] = hashlib.sha256(pickle.dumps(pair, protocol=5)).digest()
        return key

    def _prepare(self, observation, feature_schema, spec_schema, digest=None):
        if not self.capacity:
            self.misses += 1
            return _prepare_observation(observation, feature_schema, spec_schema, self.topologies)
        if digest is None:
            digest = observation_digest(observation)
        key = hashlib.sha256(self._schema_key(feature_schema, spec_schema) + digest).digest()
        entry = self._items.get(key)
        if entry is not None:
            self.hits += 1
            self._items.move_to_end(key)
            return entry[0]
        self.misses += 1
        prepared = _prepare_observation(observation, feature_schema, spec_schema, self.topologies)
        size = _tensor_bytes(prepared)
        self._items[key] = (prepared, size)
        self.tensor_bytes += size
        while len(self._items) > self.capacity or (
                self.max_bytes is not None and self.tensor_bytes > self.max_bytes and len(self._items) > 1):
            _, (_, evicted) = self._items.popitem(last=False)
            self.tensor_bytes -= evicted
            self.evictions += 1
        return prepared


def batch_observations(observations, feature_schema=None, spec_schema=None, *, cache=None, digests=None):
    """`digests`: optional ``observation_digest`` of each observation, from an owner that guarantees the observations
    stay unchanged; with a cache they replace re-hashing the observations (without a cache they are not needed)."""
    feature_schema, spec_schema = feature_schema or FeatureSchema(), spec_schema or SpecSchema()
    observations = tuple(observations)
    if not observations:
        raise ValueError('Empty observation batch')
    if digests is not None:
        digests = tuple(digests)
        if len(digests) != len(observations):
            raise ValueError('One digest per observation is required')
    if cache is None:
        prepared = [_prepare_observation(o, feature_schema, spec_schema) for o in observations]
    elif digests is None:
        prepared = [cache._prepare(o, feature_schema, spec_schema) for o in observations]
    else:
        prepared = [cache._prepare(o, feature_schema, spec_schema, d) for o, d in zip(observations, digests)]
    contexts = torch.stack([p.context for p in prepared])
    graph = Batch.from_data_list([p.graph for p in prepared])
    # Tensor collation allocates new storage; opaque metadata needs its own copy - of the one part that can change (the
    # source metadata dict). The other fields are tuples of frozen dataclasses: a deep copy of them cost ~7 % of an update.
    graph.graph_metadata = [replace(m, source_metadata=deepcopy(m.source_metadata)) for m in graph.graph_metadata]
    group_ids = tuple(p.group_ids for p in prepared)
    node_batch = torch.cat((graph['device'].batch, graph['net'].batch))
    edge_index, roles, ordinals = port_edge_tensors(graph)
    if not torch.equal(node_batch[edge_index[0]], node_batch[edge_index[1]]):
        raise ValueError('Cross-graph attention edge')
    group_batch = torch.repeat_interleave(torch.arange(len(prepared)),
                                          torch.tensor([len(p.group_features) for p in prepared]))
    active = (graph.group_mask & graph.group_mutable).nonzero().flatten()
    action_counts = torch.tensor([len(ids) for ids in group_ids])
    action_batch = group_batch[active]
    columns = torch.cat([torch.arange(count) for count in action_counts.tolist()])
    group_features = torch.cat([p.group_features for p in prepared])
    return GraphBatch(graph, contexts, node_batch, edge_index, roles,
                      ordinals, group_batch, group_features, active,
                      action_batch, action_counts, columns, group_ids)
