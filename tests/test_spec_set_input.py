"""The spec set input (record 7.298): every active spec is one described item read by one shared network, so a model
reads any spec list - any name, any number of specs - and its contract is the same on every task."""
from copy import deepcopy
from dataclasses import asdict, replace
import math

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.envs.sizing import Observation
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ENCODER_TYPES, GraphCritic, GroupActor, ModelConfig
from analog_optimizer.models.inputs import (SPEC_DESCRIPTOR_KEY, SPEC_SET_RUN_COLUMNS, SPEC_SET_STATE_COLUMNS, SpecSchema,
                                            SpecSetSchema, batch_observations, signed_log, spec_schema_from_dict,
                                            spec_set_features)
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner

from research_support import EXPERIMENT, deterministic_cpu, transitions  # noqa: F401 (fixtures)


UNITS = (('dB', 20.0), ('Hz', 1e6), ('W', 1e-3), ('fixture', 1.0))
SCHEMA = SpecSetSchema('test-descriptor-v1', ('kind_a', 'kind_b', 'point'), UNITS)
COLUMN = {name: i for i, name in enumerate(SPEC_SET_STATE_COLUMNS)}
UNIT_START = len(SPEC_SET_STATE_COLUMNS)


def model(encoder='graph_transformer'):
    """Build a small model configuration with the requested encoder for spec-set input tests."""
    return ModelConfig(hidden_dim=16, heads=2, layers=2, encoder_type=encoder)


def described(observation, descriptors=None):
    """Copy an observation graph and attach caller-supplied or default spec descriptors."""
    graph = deepcopy(observation.graph)
    graph.metadata = dict(graph.metadata, **{SPEC_DESCRIPTOR_KEY: descriptors if descriptors is not None else
                                             {s.metric_id: (1.0, 0.0, 0.5) for s in observation.specs}})
    return replace(observation, graph=graph)


def amplifier(graph, specs, metrics, **descriptors):
    """Build a synthetic observation with valid metrics and a descriptor for each supplied spec."""
    observation = Observation(deepcopy(graph), tuple(specs), dict(metrics), {k: True for k in metrics},
                              {s.metric_id: s.unit for s in specs}, 'ok', 'synthetic', 4, 'fixture')
    return described(observation, {s.metric_id: descriptors.get(s.metric_id, (1.0, 0.0, 0.5)) for s in specs})


SPECS = (MetricSpec('gain_db', 'dB', 'min', 10.0, lower=90.0),
         MetricSpec('cmrr_db', 'dB', 'min', 10.0, lower=100.0, weight=2.0),
         MetricSpec('ugb_hz', 'Hz', 'min', 1e6, lower=3e7),
         MetricSpec('power_w', 'W', 'max', 1e-4, upper=1e-3, required=False))
METRICS = {'gain_db': 85.0, 'cmrr_db': 120.0, 'ugb_hz': 5e7, 'power_w': 9e-4}


def test_items_hold_the_distance_to_the_limit_in_the_specs_own_scale(opamp):
    run, items = spec_set_features(amplifier(opamp, SPECS, METRICS, cmrr_db=(0.0, 1.0, 2.0)), SCHEMA)
    assert run.shape == (len(SPEC_SET_RUN_COLUMNS),) and items.shape == (4, SCHEMA.token_width)
    gain, cmrr, ugb, power = items.tolist()
    assert gain[COLUMN['margin']] == pytest.approx(-math.log1p(0.5))         # 5 dB short, scale 10 dB
    assert gain[COLUMN['violation']] == pytest.approx(0.5) and gain[COLUMN['satisfied']] == 0
    assert cmrr[COLUMN['margin']] == pytest.approx(math.log1p(2.0)) and cmrr[COLUMN['satisfied']] == 1
    assert power[COLUMN['hard']] == 0 and power[COLUMN['compare_max']] == 1 and power[COLUMN['has_upper']] == 1
    assert cmrr[COLUMN['relative_weight']] == 1.0 and gain[COLUMN['relative_weight']] == 0.5
    assert gain[COLUMN['value_magnitude']] == pytest.approx(signed_log(85.0, 20.0))
    assert gain[COLUMN['lower_magnitude']] == pytest.approx(signed_log(90.0, 20.0))
    assert gain[UNIT_START:UNIT_START + len(UNITS) + 1] == [1.0, 0.0, 0.0, 0.0, 0.0]          # dB
    assert ugb[UNIT_START:UNIT_START + len(UNITS) + 1] == [0.0, 1.0, 0.0, 0.0, 0.0]           # Hz
    assert cmrr[-3:] == [0.0, 1.0, 2.0] and gain[-3:] == [1.0, 0.0, 0.5]                     # the caller's description
    assert run[-1] == pytest.approx(math.log1p(4))                                          # four active specs


def test_a_unit_outside_the_list_reads_as_other_without_magnitudes(opamp):
    specs = (MetricSpec('tc_ppm', '1', 'max', 5.0, upper=25.0),)
    _, items = spec_set_features(amplifier(opamp, specs, {'tc_ppm': 27.3}), SCHEMA)
    item = items[0].tolist()
    assert item[UNIT_START:UNIT_START + len(UNITS) + 1] == [0.0, 0.0, 0.0, 0.0, 1.0]
    assert item[COLUMN['magnitude_known']] == 0 and item[COLUMN['value_magnitude']] == 0
    assert item[COLUMN['margin']] == pytest.approx(-math.log1p(2.3 / 5.0))


def test_invalid_measurements_and_inactive_specs(opamp):
    specs = SPECS[:2] + (replace(SPECS[2], active=False),)
    observation = amplifier(opamp, specs, METRICS)
    observation = replace(observation, metric_validity=dict(observation.metric_validity, gain_db=False))
    run, items = spec_set_features(observation, SCHEMA)
    assert len(items) == 2                                                     # the inactive spec is left out
    assert items[0, COLUMN['valid']] == 0 and items[0, COLUMN['margin']] == 0 and items[0, COLUMN['value_magnitude']] == 0
    assert run[-1] == pytest.approx(math.log1p(2))


def test_a_spec_without_its_description_is_refused(opamp):
    observation = amplifier(opamp, SPECS, METRICS)
    with pytest.raises(ValueError, match='description'):
        spec_set_features(described(observation, {'gain_db': (1.0, 0.0, 0.5)}), SCHEMA)
    with pytest.raises(ValueError, match='no descriptions'):
        spec_set_features(replace(observation, graph=deepcopy(observation.graph).__class__(
            **{**vars(observation.graph), 'metadata': {}})), SCHEMA)
    with pytest.raises(ValueError, match='finite'):
        spec_set_features(described(observation, {s.metric_id: (1.0, math.nan, 0.0) for s in SPECS}), SCHEMA)


def test_order_and_names_of_specs_change_nothing(opamp):
    actor = GroupActor(spec_schema=SCHEMA, config=model()).eval()
    first = amplifier(opamp, SPECS, METRICS)
    renamed = {'gain_db': 'a1', 'cmrr_db': 'b2', 'ugb_hz': 'c3', 'power_w': 'd4'}
    specs = tuple(replace(s, metric_id=renamed[s.metric_id]) for s in reversed(SPECS))
    second = amplifier(opamp, specs, {renamed[k]: v for k, v in METRICS.items()},
                       **{renamed[k]: (1.0, 0.0, 0.5) for k in METRICS})
    with torch.no_grad():
        a = actor.distribution(batch_observations([first], spec_schema=SCHEMA))
        b = actor.distribution(batch_observations([second], spec_schema=SCHEMA))
    for x, y in zip(a, b):
        torch.testing.assert_close(x, y, rtol=1e-5, atol=1e-6)


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_every_encoder_reads_mixed_spec_lists_in_one_batch(opamp, ldo, encoder):
    actor, critic = GroupActor(spec_schema=SCHEMA, config=model(encoder)), GraphCritic(spec_schema=SCHEMA, config=model(encoder))
    ldo_specs = (MetricSpec('vout_v', 'V', 'range', 0.05, lower=1.15, upper=1.25),)
    batch = batch_observations([amplifier(opamp, SPECS, METRICS), amplifier(ldo, ldo_specs, {'vout_v': 1.2}),
                                amplifier(opamp, (replace(SPECS[0], active=False), SPECS[2]), {'gain_db': 85.0, 'ugb_hz': 5e7})],
                               spec_schema=SCHEMA)
    assert batch.spec_items.shape == (6, SCHEMA.token_width) and batch.spec_batch.tolist() == [0, 0, 0, 0, 1, 2]
    sample = actor.sample(batch)
    q = critic(batch, sample.actions)
    assert torch.isfinite(sample.log_prob).all() and q.shape == (3,) and torch.isfinite(q).all()


def test_one_contract_for_every_spec_list_and_slot_models_keep_their_weights(opamp):
    keys = set(GroupActor(spec_schema=SCHEMA, config=model()).state_dict())
    assert any(k.startswith('encoder.spec_reader.item.') for k in keys) and not any(k.startswith('encoder.context.') for k in keys)
    slot = set(GroupActor(config=model()).state_dict())
    assert 'encoder.context.0.weight' in slot and not any('spec_reader' in k for k in slot)
    first = SACLearner(experiment=EXPERIMENT, spec_schema=SCHEMA, model_config=model())
    second = SACLearner(experiment=EXPERIMENT, spec_schema=SCHEMA, model_config=model())
    assert first.contract()['spec_schema'] == second.contract()['spec_schema'] == asdict(SCHEMA)
    second.actor.load_state_dict(first.actor.state_dict())                   # any task's model loads on any other
    assert spec_schema_from_dict(asdict(SCHEMA)) == SCHEMA
    assert spec_schema_from_dict(asdict(SpecSchema())) == SpecSchema()
    assert SCHEMA.version == 'spec-set-v1/test-descriptor-v1'


def test_update_act_and_checkpoint_round_trip(transitions, tmp_path):
    rows = [replace(t, observation=described(t.observation), next_observation=described(t.next_observation))
            for t in transitions]
    learner = SACLearner(experiment=EXPERIMENT, spec_schema=SCHEMA, model_config=model())
    replay = ReplayBuffer(16, origin='synthetic', seed=3)
    for row in rows:
        replay.add(row)
    result = learner.update(rows)
    assert math.isfinite(result['critic_loss']) and math.isfinite(result['actor_loss'])
    assert learner.act([rows[0].observation], deterministic=True)[0].keys() == rows[0].proposal.keys()
    learner.save(tmp_path / 'state.pt', replay)
    loaded, restored, _ = SACLearner.load(tmp_path / 'state.pt', experiment=EXPERIMENT, spec_schema=SCHEMA,
                                          model_config=model())
    assert loaded.contract() == learner.contract() and len(restored) == len(rows)
    with torch.no_grad():
        a = learner.actor.distribution(learner.batch([rows[1].observation]))
        b = loaded.actor.distribution(loaded.batch([rows[1].observation]))
    for x, y in zip(a, b):
        torch.testing.assert_close(x, y, rtol=0, atol=0)
    with pytest.raises(ValueError):
        SACLearner.load(tmp_path / 'state.pt', experiment=EXPERIMENT, model_config=model())   # slot input: refused


def test_the_schema_refuses_what_it_cannot_build():
    with pytest.raises(ValueError, match='layout'):
        SpecSetSchema('v', ('a',), UNITS, layout='spec-set-v0')
    with pytest.raises(ValueError, match='unique'):
        SpecSetSchema('v', ('a', 'a'), UNITS)
    with pytest.raises(ValueError, match='Unit references'):
        SpecSetSchema('v', ('a',), (('dB', 0.0),))
    with pytest.raises(ValueError, match='descriptor version'):
        SpecSetSchema('', ('a',), UNITS)
