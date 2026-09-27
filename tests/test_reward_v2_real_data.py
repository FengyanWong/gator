"""Recorded REAL data contracts. No simulator, synthetic backend, or fabricated electrical data."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest
import torch

from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.envs.sizing import ConditionResult, Observation, mapped_operating_points
from analog_optimizer.graph.circuit_graph import (
    CircuitGraph, Connection, Device, Diagnostic, Net, ParameterBinding, ParameterGroup, ParameterValue, SourceSpan,
)
from analog_optimizer.graph.pyg_converter import FeatureSchema, OPERATING_POINT_COLUMNS, OPERATING_POINT_REFERENCES
from analog_optimizer.measurements.specs import MetricSpec, RewardSettings, SpecificationEvaluator, spec_margin
from analog_optimizer.models import ModelConfig
from analog_optimizer.models.inputs import ObservationTensorCache, SpecSchema, batch_observations, context_features
from analog_optimizer.recording import ExperimentStore, RecordingConfig
from analog_optimizer.recording.codec import pack, raw, unpack
from analog_optimizer.recording.session import transition_from_store
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.sac import SACLearner


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'artifacts/local/m6-real-cross-category/eedb54fe59d642edaff93ba9def27649'


def read(path):
    return json.loads(Path(path).read_text())


def recorded_observation(record):
    assert record['origin'] == 'real' and record['status'] == 'ok'
    saved = deepcopy(record['observation'])
    data = saved.pop('graph')
    data['devices'] = [Device(**dict(d, terminals=tuple(d['terminals']), source=SourceSpan(**d['source']))) for d in data['devices']]
    data['nets'] = [Net(**dict(n, roles=tuple(n['roles']))) for n in data['nets']]
    data['connections'] = [Connection(**c) for c in data['connections']]
    data['parameters'] = {d: {k: ParameterValue(**dict(v, source=SourceSpan(**v['source']))) for k, v in values.items()}
                          for d, values in data['parameters'].items()}
    data['parameter_groups'] = [ParameterGroup(**dict(g, members=tuple(ParameterBinding(**m) for m in g['members'])))
                                for g in data['parameter_groups']]
    data['diagnostics'] = [Diagnostic(**dict(d, source=SourceSpan(**d['source']))) for d in data['diagnostics']]
    graph = CircuitGraph(**data)
    condition = SimulationCondition.from_dict(saved.pop('condition'))
    measurements = read(Path(record['artifact_directory']) / 'measurements.json')
    assert measurements['origin'] == 'real' and measurements['job_id'] == record['job_id']
    operating_points, unmatched = mapped_operating_points(graph, measurements.get('operating_points'))
    row = ConditionResult(condition, saved['status'], record['candidate_evaluated'], saved['metrics'],
                          saved['metric_units'], saved['metric_validity'], saved['job_id'], record['reason_code'],
                          measurements.get('operating_points') or {})
    saved['specs'] = tuple(MetricSpec(**s) for s in saved['specs'])
    return Observation(graph=graph, condition=condition, **saved, condition_results=(row,),
                       planned_conditions=(condition,), operating_points=operating_points,
                       unmatched_operating_points=unmatched)


@pytest.fixture(scope='module')
def real_transition():
    if not EVIDENCE.is_dir():
        pytest.fail('Required local REAL evidence is unavailable; do not substitute a simulator mock')
    report = read(EVIDENCE / 'opamp/report.json')
    phase = next(p for p in report['phases'] if p['circuit_class'] == 'opamp')
    before, after = (read(p) for p in phase['records'][:2])
    first, last = recorded_observation(before), recorded_observation(after)
    transition = Transition(first, after['proposal'], after['reward'], last, after['terminated'], after['truncated'],
                            after['bootstrap'], {(p['device'], p['parameter']): p['value'] for p in after['applied_parameters']},
                            after['candidate_id'], phase['records'][1])
    transition.validate()
    return transition


def test_recorded_observation_roundtrip_and_columns(real_transition):
    observation = real_transition.observation
    assert raw(unpack(pack(observation))) == raw(observation)
    schema = SpecSchema()
    features = context_features(observation, schema)
    assert features.shape == (21 * len(schema.metrics) + 11,) and torch.isfinite(features).all()
    metrics = features[:-11].reshape(-1, 21)
    assert torch.count_nonzero(metrics[:, 17:]) == 0
    assert features[-4].item() == 0 and features[-3].item() == 1
    for i, (key, _, _) in enumerate(schema.metrics):
        if key in observation.metrics:
            assert metrics[i, 10] == metrics[i, 16]
            assert metrics[i, 9] == metrics[i, 15]


def test_v1_columns_identical_to_frozen_function(real_transition):
    import importlib.util
    import sys
    path = ROOT / 'artifacts/local/reward-v2-real/20260926-implementation-01/source/analog_optimizer/models/inputs.py'
    specification = importlib.util.spec_from_file_location('frozen_reward_v1_inputs', path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    for observation in (real_transition.observation, real_transition.next_observation):
        old = module.context_features(observation, module.SpecSchema())
        new = context_features(observation, SpecSchema())
        assert torch.equal(old[:-7].reshape(-1, 13), new[:-11].reshape(-1, 21)[:, :13])
        assert torch.equal(old[-7:], new[-11:-4])


def test_operating_points_are_real_masked_and_cache_sensitive(real_transition):
    observation = real_transition.observation
    assert observation.operating_points
    schema = FeatureSchema(op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES)
    cache = ObservationTensorCache()
    packed = batch_observations([observation], schema, cache=cache)
    assert packed.graph['device'].op.shape == (len(observation.graph.devices), 12)
    assert packed.graph['device'].op_mask.any()
    missing = replace(observation, operating_points={})
    masked = batch_observations([missing], schema, cache=cache)
    assert not masked.graph['device'].op_mask.any() and not masked.graph['device'].op.any()
    assert cache.info()['misses'] == 2
    duplicate = batch_observations([deepcopy(observation)], schema, cache=cache)
    assert torch.equal(duplicate.graph['device'].op, packed.graph['device'].op) and cache.info()['hits'] == 1
    disabled = batch_observations([observation])
    assert disabled.graph['device'].op.shape[1] == 0


@pytest.mark.parametrize('encoder', ['graph_transformer', 'rgcn', 'gatv2'])
@pytest.mark.parametrize('operating_points', [False, True])
def test_real_replay_update_and_exact_recovery(real_transition, encoder, operating_points, tmp_path):
    torch.set_num_threads(1)
    torch.manual_seed(260926)
    schema = FeatureSchema(op_columns=OPERATING_POINT_COLUMNS, op_references=OPERATING_POINT_REFERENCES) if operating_points else FeatureSchema()
    config = ModelConfig(encoder_type=encoder, hidden_dim=16, layers=1, heads=2)
    args = dict(experiment=dict(origin='real', split='recorded-evidence-contract-check', designs=['M6-archived-opamp']),
                feature_schema=schema, model_config=config, planned_conditions=real_transition.observation.planned_conditions)
    learner = SACLearner(**args)
    assert any('operating_points' in key for key in learner.actor.state_dict()) == operating_points
    replay = ReplayBuffer(origin='real', seed=26)
    replay.add(real_transition)
    assert learner.act([real_transition.observation])
    checkpoint = tmp_path / 'recorded-real.pt'
    learner.save(checkpoint, replay)
    expected = learner.update(replay.sample(1))
    restored, recovered_replay, _ = SACLearner.load(checkpoint, **args)
    actual = restored.update(recovered_replay.sample(1))
    assert expected == actual
    for key, value in learner.actor.state_dict().items():
        assert torch.equal(value, restored.actor.state_dict()[key])
    for key, value in learner.critics.state_dict().items():
        assert torch.equal(value, restored.critics.state_dict()[key])
    with pytest.raises(ValueError, match='mismatch'):
        SACLearner.load(checkpoint, **args, reward_settings=RewardSettings(violation_shape='compressed'))


def test_persistent_transition_restores_all_fields(real_transition, tmp_path):
    transition = real_transition
    with ExperimentStore(tmp_path / 'recorded-real', RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', dict(origin='real', mode='recorded-evidence', fresh_simulator_calls=0))
        task, graph = store.call('task', transition.observation.graph, transition.observation.specs)
        store.call('begin', run, task, graph, dict(source='recorded-real'), eval_id=transition.candidate_id)
        last = transition.next_observation
        data = dict(status=last.status, metrics=last.metrics, metric_validity=last.metric_validity,
                    metric_units=last.metric_units, applied_parameters=transition.applied_parameters,
                    simulator_invocations=0, origin='real', evidence_record=transition.record_path)
        store.call('finish', transition.candidate_id, data, observation=last,
                   transition=dict(vars(transition), replay_eligible=True))
        restored = transition_from_store(store, transition.candidate_id)
        assert raw(vars(restored)) == raw(vars(transition))
        assert restored.fingerprint() == transition.fingerprint()


def test_dropped_corner_plan_cannot_be_replayed(real_transition):
    corner = SimulationCondition(PVTCorner('ss_hot_low', 'ss', 125, .9), purpose='pvt_training')
    plan = (real_transition.observation.condition, corner)
    first = replace(real_transition.observation, condition_policy='always', planned_conditions=plan)
    last = replace(real_transition.next_observation, condition_policy='always', planned_conditions=plan)
    assert not last.evaluation.complete and not last.evaluation.success
    with pytest.raises(ValueError, match='Incomplete'):
        replace(real_transition, observation=first, next_observation=last).validate()


@pytest.mark.parametrize('missing_corner', [False, True])
def test_reader_uses_recorded_condition_coverage(real_transition, tmp_path, missing_corner):
    from analog_optimizer.recording.reader import RunReader
    from analog_optimizer.recording.report import format_overview
    observation = real_transition.next_observation
    if missing_corner:
        # Declare an unmeasured corner. All numeric values still come from the real archive.
        corner = SimulationCondition(PVTCorner('ss_hot_low', 'ss', 125, .9), purpose='pvt_training')
        observation = replace(observation, condition_policy='always',
                              planned_conditions=(observation.condition, corner))
    root = tmp_path / 'recorded-real-reader'
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', dict(origin='real', mode='recorded-evidence', fresh_simulator_calls=0))
        task, graph = store.call('task', observation.graph, observation.specs)
        store.call('begin', run, task, graph, dict(source='recorded-real', phase='initial'), eval_id='archive')
        store.call('finish', 'archive', dict(status=observation.status, metrics=observation.metrics,
            metric_validity=observation.metric_validity, metric_units=observation.metric_units,
            simulator_invocations=0, origin='real', evidence_record=real_transition.record_path), observation=observation)
    with RunReader(root) as reader:
        overview = reader.overview(run)
        selected = overview['summary']['initial']
        assert selected['coverage_complete'] is (not missing_corner)
        assert selected['robust_feasible'] is (False if missing_corner else None)
        for constraint in selected['constraints']:
            if constraint['active'] and not constraint['nominal_only']:
                if missing_corner:
                    assert constraint['missing_coverage'] == ('ss_hot_low',)
                    assert constraint['valid'] is False and constraint['met'] is None
                else:
                    assert constraint['valid'] is True
                    assert constraint['value'] == observation.metrics[constraint['metric']]
        assert 'robust' in format_overview(overview)
        exported = reader.export(run, tmp_path / 'export')
        # An empty job table stays empty: no invented launch represents the unmeasured corner.
        assert not (exported / 'simulation_jobs.parquet').exists()


def test_any_registry_label_keeps_the_v2_layout():
    schema = SpecSchema(version='m6-toy-spec-input-v1')                # a label is identity, not a column layout
    assert schema.layout == 'spec-input-v2' and schema.width == 21 * len(schema.metrics) + 11
    with pytest.raises(ValueError, match='layout'):
        SpecSchema(layout='spec-input-v1')


def test_bonus_arithmetic_on_an_observed_feasible_real_record():
    report = read(EVIDENCE / 'vco/report.json')
    record = next(row for phase in report['phases'] for path in phase['records']
                  for row in [read(path)] if row['success'])
    assert record['origin'] == 'real' and record['evaluation_valid']
    specs = tuple(MetricSpec(**s) for s in record['observation']['specs'])
    objective = next(s for s in specs if s.active and s.lower != s.upper)
    specs = tuple(replace(s, objective='min' if s.upper is not None else 'max')
                  if s == objective else s for s in specs)
    base = SpecificationEvaluator(specs).evaluate(record['metrics'], record['metric_units'], record['metric_validity'])
    result = SpecificationEvaluator(specs, RewardSettings(objective_weight=.2, margin_weight=.3)).evaluate(
        record['metrics'], record['metric_units'], record['metric_validity'])
    margins = [spec_margin(s.lower, s.upper, s.scale, record['metrics'][s.metric_id])
               for s in specs if s.active and s.required and s.lower != s.upper]
    value = record['metrics'][objective.metric_id]
    improvement = ((objective.upper - value) if objective.upper is not None else (value - objective.lower)) / objective.scale
    expected = base.reward + .2 * min(1, max(0, improvement)) + .3 * min(margins) / (1 + min(margins))
    assert result.success and result.reward == pytest.approx(expected)
    # Bonus settings are applied only as arithmetic to this archive; no new optimizer run is claimed.
