"""Reward v2.1 workbench contracts; no physical calls or backend sessions."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from gator_workbench import corner_check, tasks
from gator_workbench.compile import build_specs, normalization_scale, training_conditions
from gator_workbench.modes import sac_config_from
from gator_workbench.schema import WorkbenchConfig, config_hash, task_definition_hash, editor_columns
from gator_workbench.reward_diagnostics import steering, VERDICT
from gator_workbench.reachability import assess, _qualification_reference


def ota(**run):
    return WorkbenchConfig.model_validate(dict(**tasks.real_starter_config('real:gpdk045_ota7'),
        run=dict(max_evaluations=10, **run)))


def test_legacy_defaults_keep_exact_pinned_hashes():
    c = ota()
    assert config_hash(c) == '9a4deb7aa143c9cf3063cac7b05f4db61148746885bfe6f0e46d73e86ff3c568'
    assert task_definition_hash(c) == 'b9ca139a4c4a40223bb5379bfaf9a58cba6a809f61063b4ab90d3f26a586f6dd'
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
    c = ota(max_spectre_launches=20, conditions=dict(policy='after_nominal', corners=['ss_hot_low']),
            reward=dict(nominal_gate_band=.4, objective_shape='compressed'), advanced=dict(alpha_learning_rate=.003))
    c.targets[0].missing_is_failure = True
    c.targets[0].margin_sides = 'lower'
    specs, targets, _ = build_specs(c)
    assert specs[0].missing_is_failure and specs[0].margin_sides == targets[0]['margin_sides'] == 'lower'
    assert len(training_conditions(c)) == 2
    assert sac_config_from(c.run.advanced).alpha_learning_rate == .003
    assert config_hash(c) != config_hash(ota()) and task_definition_hash(c) != task_definition_hash(ota())
    hidden = {row['name'] for row in editor_columns('targets') if row['advanced']}
    assert {'missing_is_failure', 'margin_sides'} <= hidden


def test_saved_empty_scale_retains_threshold_rule():
    c = ota()
    c.targets[0].normalization_scale = None
    assert normalization_scale(c.targets[0]) == abs(c.targets[0].lower)
    assert c.targets[0].normalization_scale is None


def test_backend_capabilities_are_task_specific():
    assert tasks.training_capabilities('real:gpdk045_ota7')['policies'] == ['off', 'after_nominal', 'always']
    for key in ('synthetic:gpdk045_ota5', 'ngspice:ota5_level1', 'real:gpdk045_ldo'):
        assert not tasks.training_capabilities(key)['corners']


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


@pytest.mark.requires_evidence('artifacts/local/reward-v2-real/20260926-qualification-04/stage-a/report.json')
def test_real_reference_warning_recomputes_current_targets():
    c = ota(max_spectre_launches=20, conditions=dict(policy='after_nominal', corners=['ss_hot_low', 'fs_nominal']))
    records = _qualification_reference(c)
    assert records
    result = assess(c, records)
    assert not result['observed_feasible'] and '3.78 dB' in result['warning'] and 'Corner check' in result['warning']
    assert result['best_design'] == 'reference'
    for target in c.targets:
        if target.constraint == '>=': target.lower = -1e9
        elif target.constraint == '<=': target.upper = 1e9
        else: target.lower, target.upper = -1e9, 1e9
    assert assess(c, records)['observed_feasible']
    broken = deepcopy(records)
    broken[0]['conditions']['ss_hot_low']['metric_units']['gain_db_at_start'] = 'V'
    assert not assess(c, broken)['observed_feasible']
    assert not assess(c, [dict(id='nominal-only', conditions={'nominal': records[0]['conditions']['nominal']})])['observed_feasible']


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


def test_reference_can_be_planned_without_nominal_feasibility(tmp_path, monkeypatch):
    from gator_workbench.compile import compile_task
    c = ota()
    graph = tasks._verified_profile('gpdk045_ota7').optimization_graph()
    compiled = compile_task(c, graph)
    source = lambda d, p: graph.parameters[d][p].source_name or p
    expected = {(d, source(d, p)) for d, p in graph.assignments({g.id: g.value for g in graph.parameter_groups if g.mutable})}
    context = SimpleNamespace(mock=False, compiled=compiled, layout=SimpleNamespace(data=tmp_path), expected_keys=expected,
                              source_name=source)
    chosen, counts = corner_check.candidates(context)
    assert counts['feasible'] == 0 and len(chosen) == 1
    assert chosen[0]['evaluation_id'] == 'task_reference' and chosen[0]['reward'] is None
    assert {(a['device'], a['parameter']) for a in chosen[0]['assignment']} == expected


@pytest.mark.requires_evidence('artifacts/local/reward-v2-real/20260926-qualification-04/stage-a/report.json')
def test_missing_corner_never_proves_reachability_even_for_nominal_only_specs():
    c = ota(max_spectre_launches=20, conditions=dict(policy='after_nominal', corners=['ss_hot_low']))
    records = _qualification_reference(c)
    for target in c.targets:
        target.nominal_only = True
        if target.constraint == '>=': target.lower = -1e9
        elif target.constraint == '<=': target.upper = 1e9
        else: target.lower, target.upper = -1e9, 1e9
    records[0]['conditions'].pop('ss_hot_low')
    assert not assess(c, records)['observed_feasible']


def test_reachability_warning_in_validation_is_nonblocking(tmp_path, monkeypatch):
    from gator_workbench.api.support import validate_loaded
    from gator_workbench import reachability
    c = ota(max_spectre_launches=20, conditions=dict(policy='after_nominal', corners=['ss_hot_low']))
    graph = tasks._verified_profile('gpdk045_ota7').optimization_graph()
    runtime = SimpleNamespace(base_graph=graph, circuit={}, provided_metrics=[t.metric_id for t in c.targets])
    monkeypatch.setattr(reachability, 'check', lambda *a, **kw: dict(warning='No recorded design. Use Corner check.', observed_feasible=False))
    report = validate_loaded(c, runtime)
    assert not report.blocks_run
    assert any(i.code == 'corner_reachability' and i.level == 'warning' for i in report.issues)
