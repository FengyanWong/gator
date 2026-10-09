"""Units, bindings, measurements, targets: one schema, semantic validation, compilation to the
optimizer's existing ParameterGroup / MetricSpec objects."""
import json

import pytest
from pydantic import ValidationError

from gator_workbench import compile as comp, schema, spec_equations, tasks, units, validation
from gator_workbench.engine import decode_action
from helpers import make_config
from helpers import check, issues
import math
import random
from analog_optimizer.graph.circuit_graph import ParameterBinding, ParameterGroup
from gator_workbench import engine as engine_module
from helpers import execute, rows
from helpers import TOP


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
    assert constraint['options'] == ['>=', '<=', 'interval']                 # target +/- tolerance retired on 2026-10-03


# ------------------------------------------------------------------------------- parameters
def test_valid_starter_config_counts_independent_actions(tmp_path):
    report, _ = check(make_config(tmp_path))
    assert not report.blocks_run, [i.as_dict() for i in report.issues]
    assert report.facts['independent_action_variables'] == 3 and report.facts['parameter_rows'] == 5      # the OTA5's three width groups
    assert report.facts['circuit_checked'] is True


def test_equal_initial_values_do_not_imply_a_binding(tmp_path):
    def unbind(raw):
        row = next(p for p in raw['parameters'] if p.get('binding_group'))
        row.update(binding_group=None, lower=1e-6, upper=8e-6, scale='log')
    report, _ = check(make_config(tmp_path, mutate=unbind))
    assert not report.blocks_run
    assert report.facts['independent_action_variables'] == 4     # both inputs start at 4u yet stay independent


@pytest.mark.parametrize('change, code', [
    (lambda p: p[0].update(lower=11e-6), 'invalid_bounds'),               # above its upper bound, 10 um
    (lambda p: p[0].update(unit='pF'), 'unit_mismatch'),
    (lambda p: p[0].update(unit='furlong'), 'unknown_unit'),
    (lambda p: p[0].update(scale='log', lower=-1e-6), 'log_scale_nonpositive'),
    (lambda p: p[0].update(initial_value=12e-6), 'initial_out_of_bounds'),
    (lambda p: p[0].update(initial_value=3e-6), 'initial_differs_from_circuit'),   # the netlist says 4 um
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


# ------------------------------------------------------------------------------- targets
@pytest.mark.parametrize('target, code', [
    (dict(constraint='>=', lower=None), 'missing_threshold'),
    (dict(constraint='>=', lower=0.9, upper=1.0), 'unexpected_threshold'),
    (dict(constraint='interval', lower=1.0, upper=0.5), 'invalid_interval'),
    (dict(equation='nope'), 'equation_unknown_probe'),
    (dict(unit='dB'), 'target_unit_mismatch'),
    (dict(hard=False), 'no_hard_constraint'),
])
def test_target_errors(tmp_path, target, code):
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(target)))
    assert code in issues(report, 'error'), [i.as_dict() for i in report.issues]


def test_unregistered_metric_is_added_to_the_registry_or_blocked_by_a_configured_one(tmp_path):
    """A spec is an equation over the probes, under its own name: a name the result registry lacks gets an entry
    (spec_equations.registry_entries). A registry stated in the configuration is taken as given."""
    def rename(raw):
        raw['targets'][0]['metric_id'] = 'my_noise'
    report, _ = check(make_config(tmp_path, mutate=rename))
    assert 'spec_adds_registry_entry' in issues(report, 'info') and not report.blocks_run
    report, _ = check(make_config(tmp_path, mutate=rename, advanced=dict(spec_registry=[dict(metric_id='score', unit='fixture',
                                                                                             reference=1.0)])))
    assert 'metric_not_in_registry' in issues(report, 'blocker')


def test_only_one_post_feasibility_preference(tmp_path):
    def two(raw):
        raw['targets'][0]['direction_after_feasible'] = 'maximize'
        raw['targets'].append(dict(metric_id='score2', equation='m_score*2', unit='fixture', constraint='>=', lower=0,
                                   normalization_scale=1, direction_after_feasible='minimize'))
    report, _ = check(make_config(tmp_path, mutate=two))
    assert 'multiple_preferences' in issues(report, 'error')


@pytest.mark.parametrize('hard, active, missing_is_failure, warned', [
    (False, True, True, True),                     # the one case: ticked on an active soft spec, where it does nothing
    (True, True, True, False),                     # a hard spec: the optimizer honours it
    (False, False, True, False),                   # an inactive spec affects nothing anyway
    (False, True, False, False),
])
def test_missing_value_failed_on_a_soft_spec_is_named(tmp_path, hard, active, missing_is_failure, warned):
    """The optimizer counts a missing value as failed only on a hard spec (measurements.specs._missing_failure); on a
    soft spec a missing value just leaves the spec out of the reward, so the tick is named instead of ignored (7.114)."""
    def second(raw):
        raw['targets'].append(dict(raw['targets'][0], metric_id='score_again', hard=hard, active=active,
                                   missing_is_failure=missing_is_failure))
    report, _ = check(make_config(tmp_path, mutate=second))
    found = [i for i in report.issues if i.code == 'missing_is_failure_on_soft_spec']
    assert bool(found) == warned
    if warned:
        assert found[0].level == 'warning' and found[0].path == 'targets[1].missing_is_failure' and not report.blocks_run


# ------------------------------------------------------------------------------- measurements
def measurement(**fields):
    base = dict(measurement_id='m_x', analysis='tran', result_source='ade_output', source_name='x', unit='Hz')
    base.update(fields)
    return lambda raw: raw['measurements'].append(base)


def test_unsupported_measurement_sources_are_rejected_not_faked(tmp_path):
    report, _ = check(make_config(tmp_path, mutate=measurement()))
    assert 'ade_outputs_not_wired' in issues(report, 'blocker')
    report, _ = check(make_config(tmp_path, mutate=lambda raw: raw['measurements'][0].update(source_name='gain_db')))
    assert 'metric_not_provided' in issues(report, 'error')


def test_restricted_equations_never_execute_code(tmp_path):
    """Formulas live in the Specs' equations since probes computed from other probes were retired (2026-10-03): the same
    whitelist reads them, and nothing is ever executed."""
    bad = lambda text: make_config(tmp_path, mutate=lambda raw: raw['targets'].append(dict(
        raw['targets'][0], metric_id='bad', equation=text, hard=False, direction_after_feasible='none')))
    for text in ('__import__("os").system("true")', 'm_score.real', 'abs(m_score)', 'm_score if 1 else 2'):
        report, _ = check(bad(text))
        assert 'equation_rejected' in issues(report, 'error'), text
    report, _ = check(bad('undefined_measurement * 2'))
    assert 'equation_unknown_probe' in issues(report, 'error')
    plan = spec_equations.SpecPlan.from_config(bad('(m_score * 2) - 1'))
    assert plan.spec_values({'score': 0.75})['bad'] == 0.5
    assert plan.spec_values({})['bad'] is None              # a missing (invalid) input stays invalid, never a number


@pytest.mark.parametrize('reference', ['equation', 'measurement_id'])
def test_a_probe_computed_from_others_becomes_the_equation_of_its_specs(tmp_path, reference):
    """Review of 2026-10-03: a probe computed from other probes (result_source expression) was the Specs equation's job
    since record 7.52. An older configuration loads with its arithmetic written into the specs that use it - the same
    numbers - and without the probe; a cycle never ran and is refused; a row on its own is refused in plain words."""
    def computed(raw):
        raw['measurements'] += [dict(measurement_id='m_half', analysis='other', result_source='expression', expression='m_twice / 4', unit='fixture'),
                                dict(measurement_id='m_twice', analysis='other', result_source='expression', expression='m_score * 2', unit='fixture')]
        target = dict(raw['targets'][0], metric_id='half', hard=False, direction_after_feasible='none')
        target.pop('measurement_id', None); target.pop('equation', None)
        target[reference] = 'm_half' if reference == 'measurement_id' else 'm_half - 0.1'
        raw['targets'].append(target)
    config = make_config(tmp_path, mutate=computed)
    assert [m.measurement_id for m in config.measurements] == ['m_score']
    assert config.targets[-1].equation == '((m_score * 2) / 4)' + (' - 0.1' if reference == 'equation' else '')
    assert spec_equations.SpecPlan.from_config(config).spec_values({'score': 0.8})['half'] == pytest.approx(0.3 if reference == 'equation' else 0.4)
    def cycle(raw):
        raw['measurements'] += [dict(measurement_id='m_a', analysis='other', result_source='expression', expression='m_b', unit='fixture'),
                                dict(measurement_id='m_b', analysis='other', result_source='expression', expression='m_a', unit='fixture')]
        raw['targets'].append(dict(raw['targets'][0], metric_id='loop', equation='m_a', hard=False, direction_after_feasible='none'))
    with pytest.raises(ValidationError, match='computed from itself'):
        make_config(tmp_path, mutate=cycle)
    with pytest.raises(ValidationError, match='no longer offered'):
        schema.MeasurementDefinition.model_validate(dict(measurement_id='m_x', analysis='other', result_source='expression',
                                                         expression='1', unit='1'))


def test_target_and_tolerance_become_the_limits_they_meant(tmp_path):
    """Review of 2026-10-03: "target +/- tolerance" was an interval and a tolerance loosened a limit. An older spec loads
    with those limits (and the size its empty scale had); one at the defaults keeps its hashes; one that never ran is
    refused in plain words."""
    plain = make_config(tmp_path)
    stated = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(target=None, tolerance=0.0))
    assert schema.task_definition_hash(stated) == schema.task_definition_hash(plain)
    assert schema.config_hash(stated) == schema.config_hash(plain)
    target = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(constraint='target', lower=None, target=0.9,
                                                                              tolerance=0.05, normalization_scale=None))
    row = target.targets[0]
    assert (row.constraint, row.lower, row.upper, row.normalization_scale) == ('interval', pytest.approx(0.85), pytest.approx(0.95), 0.9)
    loose = make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(tolerance=0.01, normalization_scale=None))
    assert loose.targets[0].lower == pytest.approx(plain.targets[0].lower - 0.01)
    assert loose.targets[0].normalization_scale == pytest.approx(abs(plain.targets[0].lower))
    with pytest.raises(ValidationError, match='no longer offered'):
        make_config(tmp_path, mutate=lambda raw: raw['targets'][0].update(constraint='target', lower=None, target=0.9, tolerance=0.0))


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
    assert [m.device_id for m in width.members] == ['XU1/M1', 'XU1/M2']
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
    # One checkpoint interval: every N evaluations OR every S seconds. An absent evaluations field is the default (200 since
    # record 7.280).
    for both in (dict(checkpoint_every_evaluations=50, checkpoint_every_seconds=600), dict(checkpoint_every_seconds=600)):
        raw = make_config(tmp_path, output=both).model_dump(mode='json')
        if 'checkpoint_every_evaluations' not in both:
            del raw['output']['checkpoint_every_evaluations']
        report, _ = check(schema.WorkbenchConfig.model_validate(raw))
        clash = next(i for i in report.issues if i.code == 'checkpoint_interval_both')
        every = both.get('checkpoint_every_evaluations', 200)
        assert clash.level == 'error' and report.blocks_run and f'every {every} evaluations OR every 600 seconds' in clash.message
    for one in (dict(checkpoint_every_evaluations=50), dict(checkpoint_every_seconds=600.0), dict(checkpoint_every_evaluations=None)):
        assert 'checkpoint_interval_both' not in issues(check(make_config(tmp_path, output=one))[0])
    report, _ = check(make_config(tmp_path, run=dict(network=dict(encoder_type='gatv2', hidden_dim=30, heads=4, layers=1))))
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


# A width range as a user types it: 1.84 .. 42.38 um in 0.02 um steps. The optimizer's top grid point, lower + n*step,
# is 4.2380000000000004e-05 m - a hair above 42.38 um (4.238e-05). OTA5's input pair is 4 um wide: on that grid.
TYPED = dict(unit='um', lower=1.84, upper=42.38, step=0.02)


def decimal_range(raw):
    next(r for r in raw['parameters'] if r['variable_id'] == 'input_pair_width').update(TYPED)


# ------------------------------------------------------------------------------ A7: the top of a decimal range
def test_the_optimizers_top_grid_point_is_the_compiled_upper_bound_and_nothing_else_moves(tmp_path):
    config = make_config(tmp_path, mutate=decimal_range)
    base = tasks.load_task(config.circuit).base_graph
    compiled = comp.compile_task(config, base)
    group = next(g for g in compiled.graph.parameter_groups if g.id == 'input_pair_width')
    typed = units.to_canonical(42.38, 'um')
    assert typed == 4.238e-05 and group.upper == TOP > typed
    assert group.project(1.0) == TOP                          # its top value is legal now: the group accepts it as its value
    ParameterGroup(group.id, group.parameter_kind, group.unit, TOP, group.lower, group.upper, group.members,
                   step=group.step).validate()
    assert next(v for v in compiled.variables if v['variable_id'] == 'input_pair_width')['upper'] == TOP
    # every other grid point is the one the typed bound gave
    before = ParameterGroup('g', 'w', 'm', group.value, group.lower, typed, (ParameterBinding('M1', 'w'),), step=group.step)
    for k in range(0, 2027, 7):
        value = group.lower + k * group.step
        assert group.project(value) == before.project(value)
    # a range whose top point is not above its bound compiles to exactly what was typed (bitwise)
    plain = comp.compile_task(make_config(tmp_path), base)
    assert [(g.lower, g.upper, g.step) for g in plain.graph.parameter_groups] == [
        (1e-06, 1e-05, None), (2e-06, 2e-05, None), (1e-06, 1e-05, None)]


def test_a_followers_own_clamp_at_the_leaders_range_moves_with_the_top_point(tmp_path):
    def clamp_follower(raw):
        decimal_range(raw)
        follower = next(r for r in raw['parameters'] if r.get('binding_group') == 'input_pair_width')
        follower.update(unit='um', lower=1.84, upper=42.38)        # its own clamp: the same range
    config = make_config(tmp_path, mutate=clamp_follower)
    compiled = comp.compile_task(config, tasks.load_task(config.circuit).base_graph)
    group = next(g for g in compiled.graph.parameter_groups if g.id == 'input_pair_width')
    follower = group.members[1]
    assert group.upper == TOP and follower.upper == TOP and follower.lower == 1.84e-06


def test_grid_top_is_the_top_that_project_reaches_on_thousands_of_typed_ranges():
    rng = random.Random(5)
    moved = 0
    for _ in range(20000):
        step_um = rng.choice([0.005, 0.01, 0.02, 0.05, 0.1, 0.12, 0.2])
        low_um = round(rng.randrange(1, 200) * step_um, 6)
        high_um = round(low_um + rng.randrange(1, 3000) * step_um, 6)
        lower, upper, step = (units.to_canonical(low_um, 'um'), units.to_canonical(high_um, 'um'),
                              units.scale_to_canonical(step_um, 'um'))
        typed = ParameterGroup('g', 'w', 'm', lower, lower, upper, (ParameterBinding('M', 'w'),), step=step)
        top = comp.grid_top(lower, upper, step)
        grid = lower + math.floor((upper - lower) / step + 1e-12) * step       # the optimizer's own top grid point
        if grid <= upper:
            assert top is upper                                  # untouched: the very float that was typed
            continue
        moved += 1
        assert top == grid
        assert typed.project(upper) == upper                     # the package clamps since the round-5 optimizer step
        snapped = ParameterGroup('g', 'w', 'm', lower, lower, top, (ParameterBinding('M', 'w'),), step=step)
        assert snapped.project(top) == top and snapped.project(upper) == top
        for value in (lower, (lower + upper) / 2, upper - step):
            assert snapped.project(value) == typed.project(value)
    assert 3000 < moved < 10000                                   # about a quarter of such ranges overshoot


class _AlwaysTop(random.Random):
    """Every random warm-up proposal at the top of its range (z = +1)."""
    def uniform(self, a, b):
        return b


def test_a_mock_run_that_always_proposes_the_top_of_a_decimal_range_evaluates_every_candidate(tmp_path, monkeypatch):
    # Before: each such candidate failed "invalid bounds/current value" in the optimizer's own group check (an
    # execution_error), and the first one ended the run.
    prepare = engine_module.RunEngine._prepare

    def always_top(self):
        prepare(self)
        self.rng = _AlwaysTop(0)
    monkeypatch.setattr(engine_module.RunEngine, '_prepare', always_top)
    config = make_config(tmp_path, run=dict(max_evaluations=9), advanced=dict(warmup_transitions=50), mutate=decimal_range)
    layout, state = execute(config, tmp_path)
    evaluations = rows(layout, 'evaluations', ['evaluation_id', 'action_source', 'status', 'valid', 'failure_type'])
    steps = [e for e in evaluations if e['action_source'] == 'random_warmup']
    assert state == 'completed' and len(evaluations) == 9 and len(steps) == 6, evaluations
    assert all(e['status'] == 'ok' and e['valid'] for e in evaluations), evaluations
    executed = {(r['evaluation_id'], r['instance_path']): (r['executed_value'], r['upper'], r['raw_policy_action'])
                for r in rows(layout, 'parameters', ['evaluation_id', 'instance_path', 'executed_value', 'upper', 'raw_policy_action'])}
    for e in steps:
        for device in ('XU1/M1', 'XU1/M2'):                       # the leader and its follower, both at the top point
            assert executed[e['evaluation_id'], device] == (TOP, TOP, 1.0)
