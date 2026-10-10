"""Reward v2.1 arithmetic/fuzz checks. No physical evidence or simulator calls."""
from dataclasses import asdict, replace
import importlib.util
import math
from pathlib import Path
import random
import struct
import sys
from types import SimpleNamespace

import pytest

from analog_optimizer.measurements.specs import MetricSpec, RewardSettings, SpecificationEvaluator, spec_margin
from reward_v21_support import NOMINAL, CORNERS, PLAN


def row(values, condition=NOMINAL, status='ok', evaluated=True, **kwargs):
    return SimpleNamespace(condition=condition, status=status, candidate_evaluated=evaluated,
        metrics=values, metric_units=kwargs.get('units', {k: 'V' for k in values}),
        metric_validity=kwargs.get('validity', {k: True for k in values}))


def test_fuzz_legacy_defaults_against_pre_edit_snapshot():
    path = Path(__file__).parent / 'fixtures/reward_v21_preedit_specs.py'
    spec = importlib.util.spec_from_file_location('reward_v21_frozen_evaluator', path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    rng = random.Random(20260929)
    for case in range(2500):
        goals = [dict(metric_id=k, unit='V', comparator='range', scale=10 ** rng.uniform(-3, 3),
                      lower=-1., upper=1., weight=10 ** rng.uniform(-10, 10), required=k != 'soft',
                      nominal_only=rng.choice([True, False])) for k in ('a', 'b', 'soft')]
        settings = dict(violation_shape=rng.choice(['capped', 'compressed']),
                        worst_spec_share=rng.choice([0., .5, 1.]), margin_weight=.2)
        rows = [row({k: rng.choice([None, rng.uniform(-3., 3.)]) for k in ('a', 'b', 'soft')}, condition=c,
                    status=rng.choice(['ok', 'ok', 'measurement_error', 'nonconverged', 'timeout']),
                    evaluated=rng.random() > .1) for c in PLAN[:rng.randrange(1, 4)]]
        a = old.SpecificationEvaluator([old.MetricSpec(**s) for s in goals], old.RewardSettings(**settings)).evaluate_conditions(rows, planned_conditions=PLAN)
        # the snapshot's one rule is today's opt-out: missing_is_failure was False by default until 2026-10-10
        b = SpecificationEvaluator([MetricSpec(**s, missing_is_failure=False) for s in goals], RewardSettings(**settings)).evaluate_conditions(rows, planned_conditions=PLAN)
        actual = asdict(b)
        assert actual.pop('missing_counted_as_failure') == {}
        assert actual == asdict(a), case
        if a.reward is not None:
            assert struct.pack('!d', a.reward) == struct.pack('!d', b.reward)


@pytest.mark.parametrize('shape', ['capped', 'compressed'])
@pytest.mark.parametrize('status', ['ok', 'measurement_error'])
@pytest.mark.parametrize('value,valid', [(None, False), (float('nan'), True), (float('inf'), True), (3., False), (True, True)])
def test_missing_failure_scores_one_and_preserves_other_metrics(shape, status, value, valid):
    goals = [MetricSpec('a', 'V', 'min', 1., lower=1., missing_is_failure=True),
             MetricSpec('b', 'V', 'min', 1., lower=1.)]
    evaluator = SpecificationEvaluator(goals, RewardSettings(violation_shape=shape))
    measured = row({'a': value, 'b': 2.}, status=status, validity={'a': valid, 'b': True})
    result = evaluator.evaluate_conditions([measured])
    assert evaluator.row_scorable(measured)
    assert result.valid and not result.success and not result.nominal_success
    assert result.violations == {'a': 1., 'b': 0.} and result.reward == -.5
    assert result.worst_values == {'a': None, 'b': 2.}
    assert result.missing_counted_as_failure == {'nominal': ('a',)}
    assert result.errors['a'] == 'missing_counted_as_failure'


@pytest.mark.parametrize('failure', ['unflagged', 'unit', 'invalid_unit', 'infrastructure', 'unattributed', 'unexplained'])
def test_missing_opt_in_never_attributes_configuration_or_infrastructure(failure):
    goal = MetricSpec('a', 'V', 'min', 1., lower=1., missing_is_failure=failure != 'unflagged')
    measured = row({'a': None}, status='measurement_error')
    if failure in ('unit', 'invalid_unit'):
        measured.metric_units['a'] = 'A'
        if failure == 'unit': measured.metrics['a'] = 2.
    if failure == 'infrastructure': measured.status = 'timeout'
    if failure == 'unattributed': measured.candidate_evaluated = False
    if failure == 'unexplained': measured.metrics['a'] = 2.
    evaluator = SpecificationEvaluator([goal])
    assert not evaluator.row_scorable(measured)
    result = evaluator.evaluate_conditions([measured])
    assert not result.valid and result.reward is None


@pytest.mark.parametrize('shape', ['capped', 'compressed'])
@pytest.mark.parametrize('band', [.1, .5, .9])
def test_gate_band_strict_order_including_underflow_and_rounding(shape, band):
    rng = random.Random(17)
    for scale, weight in [(1., 1.), (1e308, 1.), (1., 1e-300)]:
        goals = [MetricSpec('a', 'V', 'min', scale, lower=1., weight=weight),
                 MetricSpec('soft', 'V', 'min', 1., lower=1., weight=1e300, required=False)]
        for share in (0., .5, 1.):
            evaluator = SpecificationEvaluator(goals, RewardSettings(shape, share, nominal_gate_band=band))
            failed = [evaluator.evaluate_conditions([row({'a': value, 'soft': 1.})], planned_conditions=PLAN,
                       condition_policy='after_nominal').reward
                      for value in [math.nextafter(1., 0.), 0., -1e308, *[rng.uniform(-10, .9) for _ in range(10)]]]
            passed = evaluator.evaluate_conditions([row({'a': 2., 'soft': 1.}),
                      row({}, CORNERS[0], status='nonconverged'), row({}, CORNERS[1], status='nonconverged')],
                      planned_conditions=PLAN, condition_policy='after_nominal')
            assert all(-1. <= reward < -band <= passed.reward <= 0. for reward in failed)


def test_compressed_objective_has_direction_beyond_one_and_uses_least_improvement():
    goal = MetricSpec('a', 'V', 'min', 1., lower=0., objective='max')
    evaluator = SpecificationEvaluator([goal], RewardSettings(objective_weight=1., objective_shape='compressed'))
    values = [0., .01, .1, 1., 2., 10., 100., 1e6, 1e16, 1e17, 1e308]
    scores = [evaluator.evaluate_conditions([row({'a': x})]).reward for x in values]
    assert all(0 <= r < 1 for r in scores)
    assert all(a <= b for a, b in zip(scores, scores[1:]))
    assert all(a < b for a, b in zip(scores[:8], scores[1:8]))
    result = evaluator.evaluate_conditions([row({'a': 10.}), row({'a': 2.}, CORNERS[0])])
    assert result.objective_improvement == pytest.approx(2 / 3)


def test_margin_side_fuzz_never_changes_violation_or_feasibility():
    rng = random.Random(913)
    for _ in range(1000):
        value = rng.uniform(-2., 5.)
        goal = MetricSpec('a', 'V', 'range', .5, lower=0., upper=3.)
        results = [SpecificationEvaluator([replace(goal, margin_sides=side)]).evaluate_conditions([row({'a': value})])
                   for side in ('both', 'lower', 'upper')]
        assert all(r.violations == results[0].violations and r.success == results[0].success for r in results)
        for side, result in zip(('both', 'lower', 'upper'), results):
            assert result.margins['a'] == spec_margin(0., 3., .5, value, side)
    assert spec_margin(0., 3., 1., .1, 'upper') > spec_margin(0., 3., 1., 1.5, 'upper')


@pytest.mark.parametrize('value', [0., 1., -1., True, float('nan'), float('inf')])
def test_invalid_gate_band(value):
    with pytest.raises(ValueError, match='gate band'):
        RewardSettings(nominal_gate_band=value)
