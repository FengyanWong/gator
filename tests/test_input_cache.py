"""Input reuse must survive replay copies without stale values or mutable aliases."""
from copy import deepcopy
from dataclasses import fields, replace

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.envs.sizing import Observation
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.graph.pyg_converter import FeatureSchema, TopologyTensorCache, to_pyg
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models.inputs import ObservationTensorCache, SpecSchema, batch_observations, observation_digest


@pytest.fixture(autouse=True)
def single_thread():
    """Temporarily limit Torch to one thread and restore the previous thread count afterward."""
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(threads)


def observation(graph):
    """Build an independent synthetic score observation from a copied circuit graph."""
    return Observation(deepcopy(graph), (MetricSpec('score', 'fixture', 'min', 1, lower=.95),),
                       {'score': .6}, {'score': True}, {'score': 'fixture'}, 'ok', 'synthetic', 4, 'fixture')


def equal(a, b):
    """Recursively require exact tensor values and matching nested container contents."""
    if isinstance(a, torch.Tensor):
        torch.testing.assert_close(a, b, rtol=0, atol=0)
    elif isinstance(a, dict):
        assert a.keys() == b.keys()
        for key in a:
            equal(a[key], b[key])
    else:
        assert a == b


def equal_batch(a, b):
    """Compare graph tensors and every other dataclass field in two observation batches."""
    equal(a.graph.to_dict(), b.graph.to_dict())
    for field in fields(a):
        if field.name != 'graph':
            equal(getattr(a, field.name), getattr(b, field.name))


def resize(graph):
    """Resize the first parameter group and its members together to invalidate cached graph content."""
    group = graph.parameter_groups[0]
    group = replace(group, value=group.value * 1.1)
    graph.parameter_groups[0] = group
    for member in group.members:
        old = graph.parameters[member.device_id][member.parameter]
        graph.parameters[member.device_id][member.parameter] = replace(old, value=group.value * member.ratio)


def test_deepcopy_reuses_conversion_and_mixed_batch_offsets(opamp, ldo, monkeypatch):
    from analog_optimizer.models import inputs
    original = inputs.to_pyg
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0].circuit_id)
        return original(*args, **kwargs)

    monkeypatch.setattr(inputs, 'to_pyg', counted)
    observations = [observation(opamp), observation(ldo)]
    cache = ObservationTensorCache()
    expected = batch_observations(observations)
    first = batch_observations(observations, cache=cache)
    calls.clear()
    actual = batch_observations(deepcopy(observations), cache=cache)
    equal_batch(expected, first)
    equal_batch(expected, actual)
    assert calls == []
    assert cache.info()['hits'] == 2
    assert cache.topologies.info()['misses'] == 2
    assert torch.equal(actual.node_batch[actual.edge_index[0]], actual.node_batch[actual.edge_index[1]])
    assert torch.equal(actual.group_batch[actual.graph.group_member_index[0]],
                       actual.graph['device'].batch[actual.graph.group_member_index[1]])


def test_dynamic_sizes_refresh_but_topology_and_old_observation_survive(opamp):
    cache = ObservationTensorCache()
    original = observation(opamp)
    before = batch_observations([original], cache=cache)
    changed = deepcopy(original)
    resize(changed.graph)
    after = batch_observations([changed], cache=cache)
    equal_batch(after, batch_observations([changed]))
    assert not torch.equal(before.graph['device'].x, after.graph['device'].x)
    assert not torch.equal(before.group_features, after.group_features)
    assert torch.equal(before.edge_index, after.edge_index)
    equal_batch(before, batch_observations([deepcopy(original)], cache=cache))
    assert cache.topologies.info()['hits'] == 1
    assert cache.topologies.info()['misses'] == 1


@pytest.mark.parametrize('change', ['metric', 'validity', 'target', 'budget', 'status', 'metadata',
                                   'bounds', 'step', 'missing', 'zero', 'unresolved'])
def test_observation_key_covers_context_domains_masks_and_provenance(opamp, change):
    cache = ObservationTensorCache()
    original = observation(opamp)
    batch_observations([original], cache=cache)
    changed = deepcopy(original)
    if change == 'metric':
        changed.metrics['score'] = .9
    elif change == 'validity':
        changed.metric_validity['score'] = False
    elif change == 'target':
        changed = replace(changed, specs=(replace(changed.specs[0], lower=.8),))
    elif change == 'budget':
        changed = replace(changed, remaining_steps=2)
    elif change == 'status':
        changed = replace(changed, status='nonconverged')
    elif change == 'metadata':
        changed.graph.metadata['new_source'] = {'path': ['second-export']}
        changed = replace(changed, job_id='second-export')
    elif change in ('bounds', 'step'):
        group = changed.graph.parameter_groups[0]
        changed.graph.parameter_groups[0] = replace(group, **({'upper': group.upper * 2}
                                                               if change == 'bounds' else {'step': 1e-7}))
    elif change == 'missing':
        del changed.graph.parameters['ITAIL']['dc']
    else:
        old = changed.graph.parameters['ITAIL']['dc']
        changed.graph.parameters['ITAIL']['dc'] = replace(old, value=0.0 if change == 'zero' else None)
    equal_batch(batch_observations([changed], cache=cache), batch_observations([changed]))
    assert cache.info()['misses'] == 2
    assert cache.topologies.info()['misses'] == 1
    assert cache.topologies.info()['hits'] == 1


@pytest.mark.parametrize('change', ['nodes', 'nets', 'roles', 'edges', 'groups', 'mutable', 'members'])
def test_topology_key_covers_order_roles_and_bindings(opamp, change):
    cache = ObservationTensorCache()
    original = observation(opamp)
    batch_observations([original], cache=cache)
    changed = deepcopy(original)
    graph = changed.graph
    if change == 'nodes':
        graph.devices.reverse()
    elif change == 'nets':
        graph.nets.reverse()
    elif change == 'roles':
        graph.nets[0] = replace(graph.nets[0], roles=('bias',))
    elif change == 'edges':
        # Valid terminal connection, but different relation semantics.
        graph.connections[0] = replace(graph.connections[0], role='unknown')
    elif change == 'groups':
        graph.parameter_groups.reverse()
    elif change == 'mutable':
        graph.parameter_groups[0] = replace(graph.parameter_groups[0], mutable=False)
    else:
        group = graph.parameter_groups[0]
        graph.parameter_groups[0] = replace(group, members=tuple(reversed(group.members)))
    equal_batch(batch_observations([changed], cache=cache), batch_observations([changed]))
    assert cache.topologies.info()['misses'] == 2


def test_schema_reference_and_vocab_order_never_reuse_old_tensors(opamp):
    cache = ObservationTensorCache()
    obs = observation(opamp)
    fs, ss = FeatureSchema(), SpecSchema()
    variants = [(fs, ss), (replace(fs, references=(2e-6,) + fs.references[1:]), ss),
                (replace(fs, terminal_roles=tuple(reversed(fs.terminal_roles))), ss),
                (fs, replace(ss, metrics=tuple(reversed(ss.metrics))))]
    for feature_schema, spec_schema in variants:
        equal_batch(batch_observations([obs], feature_schema, spec_schema, cache=cache),
                    batch_observations([obs], feature_schema, spec_schema))
    assert cache.info()['misses'] == 4
    assert cache.topologies.info()['misses'] == 3


def test_public_tensors_and_metadata_are_isolated_from_caches_and_source(opamp):
    cache = ObservationTensorCache()
    obs = observation(opamp)
    obs.graph.metadata['nested'] = ['original']
    expected = batch_observations([obs])
    actual = batch_observations([obs], cache=cache)
    # Mutate every exposed tensor, including static edges and dynamic context.
    for store in actual.graph.stores:
        for value in store.values():
            if isinstance(value, torch.Tensor):
                value.fill_(0)
    for field in fields(actual):
        value = getattr(actual, field.name)
        if isinstance(value, torch.Tensor):
            value.fill_(0)
    actual.graph.graph_metadata[0].source_metadata['nested'][0] = 'corrupted'
    equal_batch(expected, batch_observations([deepcopy(obs)], cache=cache))
    assert obs.graph.metadata['nested'] == ['original']
    topology = TopologyTensorCache()
    first = to_pyg(obs.graph, topology_cache=topology)
    for store in first.stores:
        for value in store.values():
            if isinstance(value, torch.Tensor):
                value.fill_(0)
    first.graph_metadata.source_metadata['nested'][0] = 'corrupted'
    equal(to_pyg(obs.graph, topology_cache=topology).to_dict(), to_pyg(obs.graph).to_dict())


def test_invalid_mutation_is_revalidated_not_hidden_by_cached_job_id(opamp):
    cache = ObservationTensorCache()
    obs = observation(opamp)
    batch_observations([obs], cache=cache)
    obs.metrics['score'] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        batch_observations([obs], cache=cache)
    obs.metrics['score'] = .6
    obs.graph.connections.pop()
    with pytest.raises(ValueError, match='Missing terminal'):
        batch_observations([obs], cache=cache)
    assert cache.info()['entries'] == 1


@pytest.mark.parametrize('change', ['units', 'origin', 'condition', 'graph_version'])
def test_cached_observation_cannot_bypass_input_contracts(opamp, change):
    cache = ObservationTensorCache()
    obs = observation(opamp)
    batch_observations([obs], cache=cache)
    if change == 'units':
        obs.metric_units['score'] = 'V'
    elif change == 'origin':
        obs = replace(obs, origin='real')  # Real inputs require nominal provenance.
    elif change == 'condition':
        obs = replace(obs, condition=SimulationCondition(PVTCorner('tt', 'tt', 27, 1),
                                                         purpose='pvt_validation'))
    else:
        obs.graph.schema_version = 'unsupported'
    with pytest.raises(ValueError):
        batch_observations([obs], cache=cache)
    assert cache.info()['entries'] == 1


def test_nominal_condition_change_refreshes_context(opamp):
    cache = ObservationTensorCache()
    obs = replace(observation(opamp), condition=SimulationCondition(PVTCorner('tt', 'tt', 27, 1)))
    before = batch_observations([obs], cache=cache)
    changed = replace(obs, condition=SimulationCondition(PVTCorner('tt', 'tt', 30, 1)))
    after = batch_observations([changed], cache=cache)
    equal_batch(after, batch_observations([changed]))
    assert not torch.equal(before.context, after.context)
    assert cache.topologies.info()['misses'] == cache.topologies.info()['hits'] == 1


def test_bounded_lru_eviction_clear_and_disabled_mode(opamp, ldo):
    cache = ObservationTensorCache(2, topology_capacity=1)
    a, b = observation(opamp), observation(ldo)
    c = replace(a, remaining_steps=2)
    for obs in (a, b, deepcopy(a), c):
        batch_observations([obs], cache=cache)
    assert cache.info()['entries'] == 2
    assert cache.topologies.info()['entries'] == 1
    assert cache.info()['hits'] == 1
    # a was promoted, so b was evicted.
    batch_observations([a], cache=cache)
    assert cache.info()['hits'] == 2
    batch_observations([b], cache=cache)
    assert cache.info()['misses'] == 4
    cache.clear()
    assert cache.info()['entries'] == cache.topologies.info()['entries'] == 0
    assert cache.info()['hits'] == cache.info()['misses'] == 0
    disabled = ObservationTensorCache(0, topology_capacity=0)
    for _ in range(2):
        equal_batch(batch_observations([a], cache=disabled), batch_observations([a]))
    assert disabled.info()['entries'] == disabled.topologies.info()['entries'] == 0
    assert disabled.info()['hits'] == disabled.topologies.info()['hits'] == 0


# ------------------------------------------------------------ record 7.221: owner digests, byte accounting and bounds
def test_digest_is_the_whole_content(opamp):
    obs = observation(opamp)
    assert observation_digest(obs) == observation_digest(deepcopy(obs))
    for change in (lambda o: o.metrics.__setitem__('score', .7), lambda o: o.graph.metadata.__setitem__('x', [1]),
                   lambda o: resize(o.graph)):
        changed = deepcopy(obs)
        change(changed)
        assert observation_digest(changed) != observation_digest(obs)


def test_owner_digests_share_entries_with_content_keys_and_give_identical_batches(opamp, ldo):
    """An owner (the replay's learner path) passes digests instead of having the observations re-hashed: the same
    entries are found as by content keys, the batch is identical, and nothing is converted twice."""
    observations = [observation(opamp), observation(ldo)]
    cache = ObservationTensorCache()
    expected = batch_observations(observations)
    equal_batch(expected, batch_observations(observations, cache=cache))
    owned = batch_observations(deepcopy(observations), cache=cache, digests=[observation_digest(o) for o in observations])
    equal_batch(expected, owned)
    assert cache.info()['hits'] == 2 and cache.info()['misses'] == 2
    fresh = ObservationTensorCache()
    equal_batch(expected, batch_observations(observations, cache=fresh, digests=[observation_digest(o) for o in observations]))
    equal_batch(expected, batch_observations(deepcopy(observations), cache=fresh))      # content keys find owner entries
    assert fresh.info()['hits'] == 2 and fresh.info()['misses'] == 2


def test_owner_digests_still_separate_schemas(opamp):
    cache = ObservationTensorCache()
    obs = observation(opamp)
    digest = observation_digest(obs)
    fs, ss = FeatureSchema(), SpecSchema()
    variants = [(fs, ss), (replace(fs, references=(2e-6,) + fs.references[1:]), ss),
                (fs, replace(ss, metrics=tuple(reversed(ss.metrics))))]
    for feature_schema, spec_schema in variants:
        equal_batch(batch_observations([obs], feature_schema, spec_schema, cache=cache, digests=[digest]),
                    batch_observations([obs], feature_schema, spec_schema))
    assert cache.info()['misses'] == 3
    equal_batch(batch_observations([obs], FeatureSchema(), SpecSchema(), cache=cache, digests=[digest]),
                batch_observations([obs]))                     # an EQUAL schema object finds the same entry
    assert cache.info()['hits'] == 1


def test_digests_must_match_the_observations_and_a_disabled_cache_ignores_them(opamp, ldo):
    observations = [observation(opamp), observation(ldo)]
    with pytest.raises(ValueError, match='One digest per observation'):
        batch_observations(observations, cache=ObservationTensorCache(), digests=[observation_digest(observations[0])])
    disabled = ObservationTensorCache(0, topology_capacity=0)
    equal_batch(batch_observations(observations, cache=disabled, digests=[b'x' * 32, b'y' * 32]),
                batch_observations(observations))
    equal_batch(batch_observations(observations, digests=[b'x' * 32, b'y' * 32]), batch_observations(observations))
    assert disabled.info()['entries'] == 0


def test_tensor_bytes_evictions_and_the_optional_byte_bound(opamp, ldo):
    a, b = observation(opamp), observation(ldo)
    cache = ObservationTensorCache()
    batch_observations([a], cache=cache)
    one = cache.info()['tensor_bytes']
    assert one > 0 and cache.info()['evictions'] == 0 and cache.info()['max_bytes'] is None
    batch_observations([b], cache=cache)
    both = cache.info()['tensor_bytes']
    assert both > one
    counted = ObservationTensorCache(1)
    for obs in (a, b, a):
        batch_observations([obs], cache=counted)
    assert counted.info()['entries'] == 1 and counted.info()['evictions'] == 2 and counted.info()['tensor_bytes'] == one
    bounded = ObservationTensorCache(10, max_bytes=both - 1)
    for obs in (a, b):
        equal_batch(batch_observations([obs], cache=bounded), batch_observations([obs]))
    assert bounded.info()['entries'] == 1 and bounded.info()['evictions'] == 1
    assert bounded.info()['tensor_bytes'] == both - one        # the newest entry stays even when it alone is large
    tiny = ObservationTensorCache(10, max_bytes=0)
    equal_batch(batch_observations([a], cache=tiny), batch_observations([a]))
    assert tiny.info()['entries'] == 1
    bounded.clear()
    assert bounded.info()['tensor_bytes'] == bounded.info()['evictions'] == bounded.info()['entries'] == 0
    with pytest.raises(ValueError):
        ObservationTensorCache(4, max_bytes=-1)


def test_a_batch_keeps_its_own_source_metadata(opamp):
    from analog_optimizer.models.inputs import batch_observations
    from research_support import observation
    opamp_observation = observation(opamp)
    batch = batch_observations([opamp_observation])
    metadata = batch.graph.graph_metadata[0]
    metadata.source_metadata['changed_by_the_batch'] = True
    again = batch_observations([opamp_observation]).graph.graph_metadata[0]
    assert 'changed_by_the_batch' not in again.source_metadata
