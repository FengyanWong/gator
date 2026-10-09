"""Pure reward algebra, not simulator responses or circuit experiments."""
from dataclasses import replace
import math
from types import SimpleNamespace

import pytest

from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.measurements.specs import MetricSpec, RewardSettings, SpecificationEvaluator, spec_margin
from pathlib import Path
from analog_optimizer.models.inputs import SpecSchema


NOMINAL = SimulationCondition(PVTCorner('nominal', 'tt', 27, 1))
CORNER = SimulationCondition(PVTCorner('corner', 'ss', 125, .9), purpose='pvt_validation')


def arithmetic_row(values, *, condition=NOMINAL, status='ok', candidate_evaluated=True, validity=None):
    return SimpleNamespace(condition=condition, status=status, candidate_evaluated=candidate_evaluated,
                           metrics=values, metric_units={k: 'V' for k in values},
                           metric_validity={k: True for k in values} if validity is None else validity)


def test_endpoint_soft_violation_is_not_hard_failure():
    specs = [MetricSpec('hard', 'V', 'min', 1, lower=1),
             MetricSpec('soft', 'V', 'min', 1, lower=1, required=False)]
    row = arithmetic_row(dict(hard=1, soft=0))
    for share in (0, .5, 1):
        result = SpecificationEvaluator(specs, RewardSettings(worst_spec_share=share)).evaluate_conditions([row])
        assert result.success and result.reward == -(1 - share) / 2


@pytest.mark.parametrize('shape', ['capped', 'compressed'])
def test_worst_condition_and_nominal_only(shape):
    specs = [MetricSpec('x', 'V', 'min', 1, lower=1),
             MetricSpec('y', 'V', 'min', 1, lower=1, nominal_only=True)]
    evaluator = SpecificationEvaluator(specs, RewardSettings(violation_shape=shape, worst_spec_share=.5))
    rows = [arithmetic_row(dict(x=1, y=1)), arithmetic_row(dict(x=-1), condition=CORNER)]
    nominal, robust = evaluator.evaluate_conditions(rows[:1]), evaluator.evaluate_conditions(rows)
    assert robust.violations['x'] >= nominal.violations['x']
    assert robust.violations['y'] == 0 and robust.worst_values['x'] == -1
    assert robust.worst_conditions['x'] == 'corner' and not robust.success
    assert -1 <= robust.reward < 0


def test_complete_coverage_and_failure_penalty_without_fabricated_value():
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'min', 1, lower=1)],
                                       RewardSettings(violation_shape='compressed', margin_weight=1))
    plan = [NOMINAL, CORNER]
    partial = evaluator.evaluate_conditions([arithmetic_row(dict(x=2))], planned_conditions=plan)
    assert partial.valid and partial.nominal_success and not partial.success and not partial.complete
    assert partial.reward == 0 and partial.clearance == 0
    failure = evaluator.evaluate_conditions([arithmetic_row({}, status='nonconverged')], planned_conditions=plan)
    assert failure.valid and not failure.success and failure.reward == -1
    assert failure.worst_values['x'] is None and not failure.worst_valid['x']
    assert failure.violations['x'] == 1 and failure.errors['x'] == 'attributed_design_failure'
    unavailable = evaluator.evaluate_conditions([arithmetic_row({}, status='transport_error', candidate_evaluated=False)],
                                                 planned_conditions=plan)
    assert not unavailable.valid and unavailable.reward is None


def test_objective_and_tightest_margin_exclude_equality_only():
    specs = [MetricSpec('x', 'V', 'min', 1, lower=1, objective='max'),
             MetricSpec('y', 'V', 'range', 1, lower=0, upper=5),
             MetricSpec('count', 'V', 'range', 1, lower=1, upper=1)]
    evaluator = SpecificationEvaluator(specs, RewardSettings(objective_weight=.2, margin_weight=.3))
    rows = [arithmetic_row(dict(x=3, y=2, count=1)), arithmetic_row(dict(x=1.5, y=3, count=1), condition=CORNER)]
    result = evaluator.evaluate_conditions(rows)
    assert result.success and result.objective_improvement == .5
    assert result.clearance_margin == .5 and result.tightest_clearance_spec == 'x'
    assert result.clearance_excluded == ('count',) and result.margins['count'] == 0
    assert result.reward == pytest.approx(.2 * .5 + .3 / 3)
    failed = evaluator.evaluate_conditions([arithmetic_row(dict(x=1.5, y=2, count=0))])
    assert not failed.success and failed.objective_improvement == failed.clearance == 0
    assert failed.reward < 0


def test_optional_coverage_excludes_whole_spec_and_objective():
    specs = [MetricSpec('x', 'V', 'min', 1, lower=1),
             MetricSpec('y', 'V', 'max', 1, upper=5, required=False, objective='min')]
    evaluator = SpecificationEvaluator(specs, RewardSettings(objective_weight=1))
    result = evaluator.evaluate_conditions([arithmetic_row(dict(x=2, y=3)), arithmetic_row(dict(x=2), condition=CORNER)])
    assert result.success and result.reward == 0 and result.violations['y'] is None
    assert result.missing_coverage['y'] == ('corner',) and result.objective_improvement == 0


def test_equality_only_has_no_clearance():
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'range', 1, lower=1, upper=1)], RewardSettings(margin_weight=1))
    result = evaluator.evaluate_conditions([arithmetic_row(dict(x=1))])
    assert result.success and result.clearance_margin is None and result.reward == 0


@pytest.mark.parametrize('shape', ['capped', 'compressed'])
def test_finite_extremes_and_underflow_do_not_change_feasibility(shape):
    import json
    from dataclasses import asdict
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'min', 1e-308, lower=1e308)],
                                       RewardSettings(violation_shape=shape))
    result = evaluator.evaluate_conditions([arithmetic_row(dict(x=-1e308))])
    assert math.isfinite(result.reward) and result.reward == -1 and not result.success
    assert result.saturated_margins == ('x',) and math.isfinite(result.margins['x'])
    json.dumps(asdict(result), allow_nan=False)
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'min', 1e308, lower=1e-308)],
                                       RewardSettings(violation_shape=shape))
    result = evaluator.evaluate_conditions([arithmetic_row(dict(x=0))])
    assert result.reward == 0 and not result.success


def test_range_tie_is_nominal_and_one_sided_uses_adverse_value():
    specs = [MetricSpec('x', 'V', 'range', 1, lower=0, upper=1), MetricSpec('y', 'V', 'max', 1, upper=1)]
    result = SpecificationEvaluator(specs).evaluate_conditions(
        [arithmetic_row(dict(x=-3, y=2)), arithmetic_row(dict(x=5, y=5), condition=CORNER)])
    assert result.worst_conditions == dict(x='nominal', y='corner')


def test_plan_identity_and_order_validation():
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'min', 1, lower=1)])
    with pytest.raises(ValueError, match='Duplicate'):
        evaluator.evaluate_conditions([arithmetic_row(dict(x=1))], planned_conditions=[NOMINAL, NOMINAL])
    with pytest.raises(ValueError, match='unplanned'):
        evaluator.evaluate_conditions([arithmetic_row(dict(x=1)), arithmetic_row(dict(x=1), condition=CORNER)],
                                      planned_conditions=[NOMINAL])


def test_shared_margin_retains_signed_contract():
    assert spec_margin(1, 3, 2, 0) == -.5
    assert spec_margin(1, 3, 2, 2) == .5
    assert spec_margin(None, None, 1, 0) == math.inf


def test_overflowed_subtraction_with_finite_normalized_distance():
    evaluator = SpecificationEvaluator([MetricSpec('x', 'V', 'min', 1e308, lower=1e308)],
                                       RewardSettings(violation_shape='compressed'))
    assert evaluator.evaluate_conditions([arithmetic_row(dict(x=-1e308))]).reward == pytest.approx(-2 / 3)


@pytest.mark.parametrize('shape', ['capped', 'compressed'])
@pytest.mark.parametrize('share', [0, .5, 1])
def test_fixed_coverage_range_and_monotonicity(shape, share):
    specs = [MetricSpec('x', 'V', 'min', 1, lower=1, weight=1e-300),
             MetricSpec('y', 'V', 'max', 1, upper=1, weight=1e300, required=False)]
    evaluator = SpecificationEvaluator(specs, RewardSettings(violation_shape=shape, worst_spec_share=share))
    previous = None
    for value in (2, 1, .5, 0, -1, -100, -1e308):
        result = evaluator.evaluate_conditions([arithmetic_row(dict(x=value, y=2))])
        assert -1 <= result.reward <= 0
        assert result.success == (value >= 1)
        if previous is not None:
            assert result.violations['x'] >= previous.violations['x'] and result.reward <= previous.reward
        previous = result


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, 1.01])
def test_invalid_reward_settings(value):
    for field in ('worst_spec_share', 'objective_weight', 'margin_weight'):
        with pytest.raises(ValueError):
            RewardSettings(**{field: value})


def test_objective_contract():
    with pytest.raises(ValueError):
        MetricSpec('x', 'V', 'min', 1, lower=1, objective='min')
    spec = MetricSpec('x', 'V', 'min', 1, lower=1, objective='max')
    with pytest.raises(ValueError, match='one active objective'):
        SpecificationEvaluator([spec, replace(spec, metric_id='y')])


def test_the_registry_label_is_identity_and_the_layout_is_the_codes(opamp):
    """F2: the M6 modules name their registries; a name must not be refused as an input layout."""
    from analog_optimizer.evaluation.cross_category import load_categories
    schema = SpecSchema(version='physical-m6-registry-v1', metrics=(('a', 'V', 1.0),))
    assert schema.layout == 'spec-input-v2' and schema.width == 21 + 11
    assert load_categories(Path(__file__).resolve().parents[1])                  # constructs its own labelled registry
