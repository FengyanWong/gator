"""Units, bindings, measurements, targets: one schema, semantic validation, compilation to the
optimizer's existing ParameterGroup / MetricSpec objects."""
import json
import math

import pytest
from pydantic import ValidationError

from gator_workbench import compile as comp, schema, tasks, units, validation
from gator_workbench.engine import decode_action
from helpers import make_config


def issues(report, level=None):
    return {i.code for i in report.issues if level is None or i.level == level}


def check(config, task='synthetic:opamp'):
    runtime = tasks.load_task(config.circuit)
    return validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics)), runtime


# ------------------------------------------------------------------------------- units
def test_units_are_explicit_and_unknown_units_are_rejected():
    assert units.to_canonical(4, 'um') == pytest.approx(4e-6)
    assert units.to_canonical(10, 'kohm') == pytest.approx(1e4)
    assert units.to_canonical(300, 'K') == pytest.approx(26.85)          # affine
    assert units.scale_to_canonical(5, 'K') == 5                         # a tolerance has no offset
    assert units.compatible('um', 'nm') and not units.compatible('um', 'pF')
    with pytest.raises(units.UnitError):
        units.to_canonical(1, 'meg')
    with pytest.raises(units.UnitError):
        units.to_canonical(float('nan'), 'um')


def test_schema_rejects_unknown_keys_and_non_finite_numbers(tmp_path):
    raw = make_config(tmp_path).model_dump(mode='json')
    raw['skip_validation'] = True
    with pytest.raises(ValidationError):
        schema.WorkbenchConfig.model_validate(raw)
    raw.pop('skip_validation')
    raw['targets'][0]['lower'] = float('nan')
    with pytest.raises(ValidationError):
        schema.WorkbenchConfig.model_validate(raw)


def test_json_roundtrip_is_lossless_and_hash_is_stable(tmp_path):
    config = make_config(tmp_path)
    again = schema.WorkbenchConfig.model_validate(json.loads(json.dumps(config.model_dump(mode='json'))))
    assert again == config and schema.config_hash(again) == schema.config_hash(config)
    changed = again.model_copy(deep=True)
    changed.run.max_evaluations += 1
    assert schema.config_hash(changed) != schema.config_hash(config)
    assert schema.task_definition_hash(changed) == schema.task_definition_hash(config)   # budget is not the task
    changed.targets[0].lower = 0.5
    assert schema.task_definition_hash(changed) != schema.task_definition_hash(config)


def test_editor_columns_come_from_the_schema():
    for section, model in schema.SECTIONS.items():
        columns = schema.editor_columns(section)
        assert [c['name'] for c in columns] == list(model.model_fields)
        assert all(c['guidance'] for c in columns), [c['name'] for c in columns if not c['guidance']]
    constraint = next(c for c in schema.editor_columns('targets') if c['name'] == 'constraint')
    assert constraint['options'] == ['>=', '<=', 'interval', 'target']


# ------------------------------------------------------------------------------- parameters
def test_valid_starter_config_counts_independent_actions(tmp_path):
    report, _ = check(make_config(tmp_path))
    assert not report.blocks_run, [i.as_dict() for i in report.issues]
    assert report.facts['independent_action_variables'] == 2 and report.facts['parameter_rows'] == 3
    assert report.facts['circuit_checked'] is True


def test_equal_initial_values_do_not_imply_a_binding(tmp_path):
    def unbind(raw):
        row = next(p for p in raw['parameters'] if p.get('binding_group'))
        row.update(binding_group=None, lower=1e-6, upper=8e-6, scale='log')
    report, _ = check(make_config(tmp_path, mutate=unbind))
    assert not report.blocks_run
    assert report.facts['independent_action_variables'] == 3     # both inputs start at 2u yet stay independent


@pytest.mark.parametrize('change, code', [
    (lambda p: p[0].update(lower=9e-6), 'invalid_bounds'),
    (lambda p: p[0].update(unit='pF'), 'unit_mismatch'),
    (lambda p: p[0].update(unit='furlong'), 'unknown_unit'),
    (lambda p: p[0].update(scale='log', lower=-1e-6), 'log_scale_nonpositive'),
    (lambda p: p[0].update(initial_value=9e-6), 'initial_out_of_bounds'),
    (lambda p: p[0].update(initial_value=3e-6), 'initial_differs_from_circuit'),
    (lambda p: p[0].update(step=1e-3), 'step_exceeds_range'),
    (lambda p: p[0].update(instance_path='no_such_instance'), 'unknown_instance'),
    (lambda p: p[0].update(parameter_name='zz'), 'unknown_parameter'),
    (lambda p: p[1].update(binding_group='missing_leader'), 'binding_graph'),
    (lambda p: p[1].update(instance_path=p[0]['instance_path']), 'conflicting_targets'),
    (lambda p: p[1].update(upper=1e-6), 'binding_violates_member_bound'),
    (lambda p: p[1].update(ratio=2.0), 'binding_initial_mismatch'),
])
def test_parameter_errors(tmp_path, change, code):
    report, _ = check(make_config(tmp_path, mutate=lambda raw: change(raw['parameters'])))
    assert code in issues(report, 'error'), [i.as_dict() for i in report.issues]
    assert report.blocks_run


def test_binding_cycle_is_detected(tmp_path):
    def cycle(raw):
        raw['parameters'][0]['binding_group'] = raw['parameters'][1]['variable_id']
    report, _ = check(make_config(tmp_path, mutate=cycle))
    assert any('cycle' in i.message for i in report.issues if i.code == 'binding_graph')


def test_integer_constraints(tmp_path):
    def integer(raw):
        raw['parameters'].append(dict(variable_id='fingers', instance_path='input_left', parameter_name='nf',
                                      unit='count', value_type='integer', lower=1, upper=8.5))
    report, _ = check(make_config(tmp_path, mutate=integer))
    assert 'integer_constraint' in issues(report, 'error')


def test_expression_relations_only_execute_as_positive_ratios(tmp_path):
    assert validation.linear_ratio('2*leader') == pytest.approx(2)
    assert validation.linear_ratio('leader/4') == pytest.approx(0.25)
    assert validation.linear_ratio('leader + 1e-6') is None
    assert validation.linear_ratio('leader**2') is None
    assert validation.linear_ratio('-leader') is None
    assert validation.linear_ratio('__import__("os").system("x")') is None      # never evaluated as code
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['parameters'][1].update(
        relation='expression', expression='leader**2')))
    assert 'expression_not_executable' in issues(report, 'blocker')


def test_discrete_candidates_need_a_uniform_grid(tmp_path):
    grid = lambda raw: raw['parameters'][0].update(value_type='discrete', candidates=[1e-6, 2e-6, 3e-6, 4e-6],
                                                   lower=None, upper=None, scale='linear')
    report, runtime = check(make_config(tmp_path, mutate=grid))
    assert not report.blocks_run
    group = comp.compile_task(make_config(tmp_path, mutate=grid), runtime.base_graph).graph.parameter_groups[0]
    assert (group.lower, group.upper, group.step) == pytest.approx((1e-6, 4e-6, 1e-6))
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['parameters'][0].update(
        value_type='discrete', candidates=[1e-6, 2e-6, 5e-6], lower=None, upper=None)))
    assert 'nonuniform_candidates' in issues(report, 'blocker')


def test_design_variable_targets_are_kept_but_block_a_run(tmp_path):
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['parameters'].append(dict(
        variable_id='vbias', target_kind='design_variable', parameter_name='vbias', unit='V', lower=0.3, upper=0.7))))
    assert 'design_variable_writeback_unsupported' in issues(report, 'blocker')


# ------------------------------------------------------------------------------- targets
@pytest.mark.parametrize('target, code', [
    (dict(constraint='>=', lower=None), 'missing_threshold'),
    (dict(constraint='>=', lower=0.9, upper=1.0), 'unexpected_threshold'),
    (dict(constraint='interval', lower=1.0, upper=0.5), 'invalid_interval'),
    (dict(constraint='target', lower=None, target=0.9, tolerance=0.0), 'target_needs_tolerance'),
    (dict(measurement_id='nope'), 'unknown_measurement'),
    (dict(unit='dB'), 'target_unit_mismatch'),
    (dict(hard=False), 'no_hard_constraint'),
])
def test_target_errors(tmp_path, target, code):
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(target)))
    assert code in issues(report, 'error'), [i.as_dict() for i in report.issues]


def test_unregistered_metric_is_a_visible_blocker(tmp_path):
    def rename(raw):
        raw['targets'][0]['metric_id'] = 'my_noise'
    report, _ = check(make_config(tmp_path, mutate=rename))
    assert 'metric_not_in_registry' in issues(report, 'blocker')


def test_only_one_post_feasibility_preference(tmp_path):
    def two(raw):
        raw['targets'][0]['direction_after_feasible'] = 'maximize'
        raw['measurements'].append(dict(measurement_id='m2', analysis='other', result_source='expression',
                                        expression='m_score*2', unit='fixture'))
        raw['targets'].append(dict(metric_id='score2', measurement_id='m2', unit='fixture', constraint='>=', lower=0,
                                   normalization_scale=1, direction_after_feasible='minimize'))
    report, _ = check(make_config(tmp_path, mutate=two))
    assert 'multiple_preferences' in issues(report, 'error')


# ------------------------------------------------------------------------------- measurements
def measurement(**fields):
    base = dict(measurement_id='m_x', analysis='tran', result_source='ade_output', source_name='x', unit='Hz')
    base.update(fields)
    return lambda raw: raw['measurements'].append(base)


@pytest.mark.parametrize('fields, code', [
    (dict(function='frequency'), 'frequency_needs_window'),
    (dict(function='frequency', analysis='ac'), 'frequency_needs_time_domain'),
    (dict(function='average_power', unit='W', signal='VDD:p'), 'power_needs_direction'),
    (dict(function='phase_margin', unit='deg', analysis='stb'), 'margin_needs_loop'),
    (dict(function='phase_margin', unit='deg', analysis='stb', loop_definition='stb probe IPRB0'), 'margin_needs_crossover'),
    (dict(function='spot_noise', unit='V/sqrt(Hz)', analysis='noise'), 'needs_frequency_point'),
    (dict(function='integrated_noise', unit='Vrms', analysis='noise'), 'noise_needs_band'),
    (dict(function='integrated_noise', unit='Vrms', analysis='noise', integration_band_hz=[1e6, 10]), 'noise_needs_band'),
    (dict(window=dict(start=2e-9, stop=1e-9, unit='s')), 'invalid_window'),
])
def test_measurement_domain_rules(tmp_path, fields, code):
    report, _ = check(make_config(tmp_path, mutate=measurement(**fields)))
    assert code in issues(report, 'error'), [i.as_dict() for i in report.issues]


def test_unsupported_measurement_sources_are_rejected_not_faked(tmp_path):
    report, _ = check(make_config(tmp_path, mutate=measurement()))
    assert 'ade_outputs_not_wired' in issues(report, 'blocker')
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(source_name='gain_db')))
    assert 'metric_not_provided' in issues(report, 'error')
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(
        conditions=['nominal', 'ss_125c'], aggregation='worst_case')))
    assert 'nominal_only_backend' in issues(report, 'blocker')
    with pytest.raises(ValidationError):            # there is no "treat a failure as feasible" option at all
        make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(on_failure='feasible'))


def test_restricted_expressions_never_execute_code(tmp_path):
    bad = lambda text: make_config(tmp_path, mutate=lambda raw: raw['measurements'].append(dict(
        measurement_id='m_bad', analysis='other', result_source='expression', expression=text, unit='fixture')))
    for text in ('__import__("os").system("true")', 'm_score.real', 'abs(m_score)', 'm_score if 1 else 2'):
        report, _ = check(bad(text))
        assert 'expression_rejected' in issues(report, 'error'), text
    report, _ = check(bad('undefined_measurement * 2'))
    assert 'expression_unknown_symbol' in issues(report, 'error')
    config = bad('(m_score * 2) - 1')
    values = comp.evaluate_expression_measurements(config, {'score': 0.75})
    assert values == {'m_score': 0.75, 'm_bad': 0.5}
    assert comp.evaluate_expression_measurements(config, {'score': None})['m_bad'] is None    # invalid stays invalid


# ------------------------------------------------------------------------------- compile / feasibility
def test_compile_produces_existing_optimizer_objects(tmp_path):
    from analog_optimizer.graph.circuit_graph import ParameterGroup
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.parameters.actions import ActionMapper
    config = make_config(tmp_path)
    runtime = tasks.load_task(config.circuit)
    compiled = comp.compile_task(config, runtime.base_graph)
    assert all(isinstance(g, ParameterGroup) for g in compiled.graph.parameter_groups)
    assert all(isinstance(s, MetricSpec) for s in compiled.specs)
    width = compiled.graph.parameter_groups[0]
    assert [m.device_id for m in width.members] == ['input_left', 'input_right']
    mapper = ActionMapper(compiled.graph)
    for z in (-1.0, -0.37, 0.0, 0.61, 1.0):          # decode_action mirrors the optimizer's mapper
        legal = mapper.legalize({g: z for g in mapper.group_ids})
        for variable in compiled.variables:
            decoded = decode_action(z, variable['lower'], variable['upper'], variable['scale'])
            assert legal.group_values[variable['variable_id']] == pytest.approx(decoded, rel=1e-12)


def test_tolerance_and_target_map_to_the_same_acceptance_region(tmp_path):
    config = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(
        constraint='target', lower=None, target=0.9, tolerance=0.05))
    spec = comp.build_specs(config)[0][0]
    assert (spec.comparator, spec.lower, spec.upper) == ('range', pytest.approx(0.85), pytest.approx(0.95))
    config = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(tolerance=0.01))
    assert comp.build_specs(config)[0][0].lower == pytest.approx(0.94)


def test_feasibility_is_independent_of_reward_and_never_true_for_bad_measurements(tmp_path):
    targets = comp.build_specs(make_config(tmp_path))[1]
    assert comp.hard_constraints(targets, {'score': 0.96}, {'score': True})[:2] == (True, True)
    valid, feasible, rows, violation = comp.hard_constraints(targets, {'score': 0.5}, {'score': True})
    assert (valid, feasible) == (True, False) and violation == pytest.approx(0.45) and rows[0]['satisfied'] is False
    for value, flag in ((float('nan'), True), (None, True), (0.99, False), (float('inf'), True), (True, True)):
        valid, feasible, _, violation = comp.hard_constraints(targets, {'score': value}, {'score': flag})
        assert (valid, feasible, violation) == (False, False, None)
    assert comp.hard_constraints(targets, {}, {})[:2] == (False, False)        # missing measurement


def test_run_setting_rules(tmp_path):
    report, _ = check(make_config(tmp_path, run=dict(mode='fine_tune')))
    assert 'missing_model_source' in issues(report, 'error')                   # no silent fallback to scratch
    report, _ = check(make_config(tmp_path, advanced=dict(freeze_encoder=True)))
    assert 'fine_tune_only_option' in issues(report, 'error')
    report, _ = check(make_config(tmp_path, output=dict(save_replay_snapshots=False)))
    warning = next(i for i in report.issues if i.code == 'no_full_resume')
    assert warning.level == 'warning' and 'FULL training-state resume' in warning.message
    report, _ = check(make_config(tmp_path, run=dict(network=dict(encoder_type='gat', hidden_dim=30, heads=4, layers=1))))
    assert 'heads_divisibility' in issues(report, 'error')


def test_research_labels_are_optional_for_a_single_run_but_required_for_generalization(tmp_path):
    config = make_config(tmp_path)
    runtime = tasks.load_task(config.circuit)
    normal = validation.validate(config, graph=runtime.base_graph, provided_metrics={'score'})
    assert not normal.blocks_run and 'research_labels_unspecified' in issues(normal, 'info')
    strict = validation.validate(config, graph=runtime.base_graph, provided_metrics={'score'}, for_generalization=True)
    assert 'research_labels_unspecified' in issues(strict, 'error')
    leak = make_config(tmp_path, research=dict(generalization_level='unseen_circuit_class', training_sources=['opamp']))
    assert 'class_leak' in issues(validation.validate(leak, graph=runtime.base_graph, provided_metrics={'score'}), 'error')


def test_without_a_circuit_checks_are_reported_as_not_performed(tmp_path):
    report = validation.validate(make_config(tmp_path))
    assert report.facts['circuit_checked'] is False and 'circuit_not_loaded' in issues(report, 'unresolved')
