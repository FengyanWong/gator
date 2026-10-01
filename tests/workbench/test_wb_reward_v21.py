"""Reward v2.1 workbench contracts; no physical calls or backend sessions."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gator_workbench import corner_check, tasks
from gator_workbench.compile import build_specs, normalization_scale, training_conditions
from gator_workbench.modes import sac_config_from
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash, editor_columns
from gator_workbench.reward_diagnostics import steering, VERDICT


def ota(**run):
    """A configuration of the tests' MOCK stand-in (the OTA5). These contracts were first written on real:gpdk045_ota7;
    it was removed on 2026-09-30 (record 7.128) with its corner training and the tests that needed that."""
    return WorkbenchConfig.model_validate({**tasks.starter_config('synthetic:gpdk045_ota5'),
                                           'run': dict(max_evaluations=10, **run)})


def test_legacy_defaults_keep_exact_pinned_hashes():
    c = ota()
    assert config_hash(c) == 'a32dbd027a6769bc1d28ca48d4f55fb430e77be9b097fff3f3dce5a80785b9d7'       # pinned on the stand-in
    assert task_definition_hash(c) == '5f181ef30c4ba6b5a1663871f07d48c9ed976334b6b8babd9870a7157c8a978a'   # (7.128)
    assert c.run.reward.violation_shape == 'capped' and c.run.advanced.alpha_learning_rate is None
    legacy = c.model_dump(mode='json')
    legacy['run']['reward'].pop('nominal_gate_band')
    legacy['run']['reward'].pop('objective_shape')
    legacy['run']['advanced'].pop('alpha_learning_rate')
    for row in legacy['targets']:
        row.pop('missing_is_failure'); row.pop('margin_sides')
    assert config_hash(legacy) == config_hash(c)
    legacy['run']['reward']['worst_spec_share'] = .4
    assert config_hash(legacy) == config_hash(WorkbenchConfig.model_validate(legacy))


@pytest.mark.parametrize('field,value', [('nominal_gate_band', 0.), ('nominal_gate_band', 1.), ('objective_shape', 'bad')])
def test_reward_settings_reject_invalid_values(field, value):
    with pytest.raises(ValidationError):
        ota(reward={field: value})


@pytest.mark.parametrize('rate', [0, -1, float('inf')])
def test_alpha_rate_requires_finite_positive_value(rate):
    with pytest.raises(ValidationError):
        ota(advanced=dict(alpha_learning_rate=rate))


def test_new_fields_change_contracts_and_compile():
    c = ota(max_spectre_launches=20, reward=dict(nominal_gate_band=.4, objective_shape='compressed'),
            advanced=dict(alpha_learning_rate=.003))
    c.targets[0].missing_is_failure = True
    c.targets[0].margin_sides = 'lower'
    specs, targets, _ = build_specs(c)
    assert specs[0].missing_is_failure and specs[0].margin_sides == targets[0]['margin_sides'] == 'lower'
    assert training_conditions(c) == ()                                          # no task trains at corners (7.128)
    assert sac_config_from(c.run.advanced).alpha_learning_rate == .003
    assert config_hash(c) != config_hash(ota()) and task_definition_hash(c) != task_definition_hash(ota())
    hidden = {row['name'] for row in editor_columns('targets') if row['advanced']}
    assert {'missing_is_failure', 'margin_sides'} <= hidden


def test_saved_empty_scale_retains_threshold_rule():
    c = ota()
    c.targets[0].normalization_scale = None
    assert normalization_scale(c.targets[0]) == abs(c.targets[0].lower)
    assert c.targets[0].normalization_scale is None


def test_no_task_trains_at_corners_now():
    for key in ('real:gpdk045_ota7', 'synthetic:gpdk045_ota5', 'ngspice:ota5_level1', 'real:mscr_ota7t'):
        assert tasks.training_capabilities(key) == dict(corners=False, policies=['off'])


def test_steering_uses_last_50_scored_in_completion_order():
    rows = [dict(completion_index=i, reward=float(i)) for i in range(60)]
    rows += [dict(completion_index=61, reward=None), dict(completion_index=62, reward=float('nan'))]
    check = steering(rows[::-1], [dict(alpha=2., mean_log_prob=-30.)])
    assert check['scored_designs'] == 50
    assert check['reward_spread'] == pytest.approx(39.2)
    assert check['exploration_bonus'] == 60
    assert check['verdict'] == VERDICT
    assert steering(rows, [dict(alpha=.01, mean_log_prob=-1)])['verdict'] is None


def test_steering_missing_latest_update_does_not_use_stale_bonus():
    assert steering([], []) == dict(scored_designs=0, reward_spread=None, exploration_bonus=None, verdict=None)
    check = steering([dict(reward=0.)], [dict(alpha=.2, mean_log_prob=-2), dict(alpha=None)])
    assert check['reward_spread'] is None and check['exploration_bonus'] is None and check['verdict'] is None


def test_readiness_exposes_nonblocking_reachability_warning():
    from gator_workbench.agents.readiness import build
    result = build(ota().model_dump(mode='json'), validation=dict(blocks_run=False, issues=[dict(
        level='warning', code='corner_reachability', path='run.conditions', message='The reference misses gain. Use Corner check.')]))
    item = next(i for i in result['items'] if i['id'] == 'corner_reachability')
    assert item['status'] == 'warning' and 'reference misses' in item['detail']


def test_corner_margin_side_does_not_change_failure_grading():
    from analog_optimizer.backends.backend import SimulationStatus
    from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator
    target = dict(metric_id='power', lower=0., upper=10., scale=1., active=True, hard=True, unit='W', margin_sides='upper')
    assert corner_check._margin(target, 1.) > corner_check._margin(target, 5.)
    evaluator = SpecificationEvaluator([MetricSpec('power', 'W', 'range', 1., lower=0., upper=10., margin_sides='upper')])
    result = SimpleNamespace(metrics={'power': -1.}, metric_units={'power': 'W'}, metric_validity={'power': True},
                             status=SimulationStatus.OK, candidate_evaluated=True)
    state, evaluation, failing = corner_check.grade(result, evaluator, [target])
    assert state == 'failed' and not evaluation.success and failing[0]['violation'] == 1


