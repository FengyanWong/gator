from dataclasses import replace
import pytest

from analog_optimizer.measurements.specs import MetricSpec, SpecificationEvaluator


def test_min_max_range_and_weighted_reward():
    specs = [MetricSpec('gain', 'dB', 'min', 10, lower=20, weight=2),
             MetricSpec('power', 'W', 'max', 2, upper=4),
             MetricSpec('dc', 'V', 'range', 1, lower=0.2, upper=0.8)]
    evaluator = SpecificationEvaluator(specs)
    units, valid = {'gain': 'dB', 'power': 'W', 'dc': 'V'}, dict.fromkeys(['gain', 'power', 'dc'], True)
    result = evaluator.evaluate({'gain': 15, 'power': 5, 'dc': 0.9}, units, valid)
    assert result.valid and not result.success
    assert result.reward == pytest.approx(-0.4)
    assert result.violations == pytest.approx({'gain': 0.5, 'power': 0.5, 'dc': 0.1})
    result = evaluator.evaluate({'gain': 20, 'power': 4, 'dc': 0.2}, units, valid)
    assert result.success and result.reward == 0


@pytest.mark.parametrize('value,unit,valid', [(None, 'dB', True), (float('nan'), 'dB', True),
    (float('inf'), 'dB', True), (True, 'dB', True), (30, 'V', True), (30, 'dB', False)])
def test_invalid_required_metric_never_succeeds(value, unit, valid):
    evaluator = SpecificationEvaluator([MetricSpec('gain', 'dB', 'min', 10, lower=20)])
    result = evaluator.evaluate({'gain': value}, {'gain': unit}, {'gain': valid})
    assert not result.success and not result.valid and result.reward is None
    assert result.violations['gain'] is None


def test_optional_inactive_and_tiny_weight_cannot_hide_required_failure():
    evaluator = SpecificationEvaluator([
        MetricSpec('gain', 'dB', 'min', 1, lower=-1, weight=1e-30),
        MetricSpec('power', 'W', 'max', 1, upper=0),
        MetricSpec('optional', 'V', 'min', 1, lower=0, required=False),
        MetricSpec('inactive', 'V', 'min', 1, lower=0, active=False)])
    result = evaluator.evaluate({'gain': -2, 'power': -0.1}, {'gain': 'dB', 'power': 'W'},
                                {'gain': True, 'power': True})
    assert result.valid and not result.success and result.reward < 0
    assert result.errors == {'optional': 'missing_or_nonfinite'}
    assert 'inactive' not in result.violations


def test_extreme_values_have_finite_bounded_penalty():
    evaluator = SpecificationEvaluator([MetricSpec('x', '1', 'min', 1e-300, lower=1e308)])
    result = evaluator.evaluate({'x': -1e308}, {'x': '1'}, {'x': True})
    assert result.reward == -1 and result.violations['x'] == 1 and not result.success


@pytest.mark.parametrize('change', [{'scale': 0}, {'weight': -1}, {'lower': float('inf')},
                                  {'comparator': 'range'}, {'upper': 3}, {'active': 'yes'}])
def test_invalid_spec_definitions(change):
    with pytest.raises(ValueError):
        replace(MetricSpec('gain', 'dB', 'min', 1, lower=0), **change)


def test_duplicate_or_no_required_specs_are_rejected():
    spec = MetricSpec('gain', 'dB', 'min', 1, lower=0)
    for specs in ([], [replace(spec, required=False)], [spec, spec]):
        with pytest.raises(ValueError):
            SpecificationEvaluator(specs)
