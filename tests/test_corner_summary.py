from dataclasses import replace, asdict
import json
from pathlib import Path

import pytest

from analog_optimizer.backends.backend import SimulationResult, SimulationStatus
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition
from analog_optimizer.evaluation.corners import NominalDesign, select_top_designs, summarize_corners
from analog_optimizer.measurements.specs import MetricSpec

NOMINAL = SimulationCondition(PVTCorner('nominal', 'tt', 27, 1))
CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'configs/gpdk045_conditions.json').read_text())
CORNERS = tuple(PVTCorner(**c) for c in CONFIG['screening_corners'])
SPECS = [MetricSpec('gain', 'dB', 'min', 10, lower=20),
         MetricSpec('power', 'W', 'max', 1, upper=3),
         MetricSpec('dc', 'V', 'range', 1, lower=0.2, upper=0.8)]


def design(name='a', reward=0, width=4e-6):
    return NominalDesign(name, 'same_circuit_and_specs', reward,
                          (('M1', 'w', width), ('M2', 'w', width)), NOMINAL, 'synthetic')


def result(candidate, corner, *, gain=25, power=2, dc=0.5):
    return SimulationResult(corner.id, 'synthetic_fixture', 'synthetic', SimulationStatus.OK,
        'injected', False, True, {'gain': gain, 'power': power, 'dc': dc},
        {'gain': 'dB', 'power': 'W', 'dc': 'V'}, {'gain': True, 'power': True, 'dc': True},
        candidate.assignments, Path('/synthetic'), 0, SimulationCondition(corner, 'pvt_validation'))


def test_top_three_rank_nominal_and_remove_executed_duplicates():
    candidates = [design('a', 0, 4e-6), design('b', -0.1, 4e-6), design('c', -0.2, 4.1e-6),
                  design('d', -0.3, 4.2e-6), design('e', -0.4, 4.3e-6)]
    assert [c.candidate_id for c in select_top_designs(candidates)] == ['a', 'c', 'd']
    assert [c.candidate_id for c in select_top_designs([design('z', 0, 4.1e-6), design('a')])] == ['a', 'z']
    assert CONFIG['post_validation']['top_k'] * len(CORNERS) == 15


@pytest.mark.parametrize('change', [{'problem_id': 'other_goal'}, {'origin': 'real'},
    {'condition': SimulationCondition(PVTCorner('other', 'tt', 27, 1))}])
def test_unrelated_candidates_cannot_be_compared(change):
    with pytest.raises(ValueError, match='share'):
        select_top_designs([design(), replace(design('b'), **change)])


def test_postvalidation_score_cannot_rescue_failed_design():
    candidate = design(reward=0)
    results = tuple(result(candidate, c, gain=19 if c.model_section == 'ss' else 25) for c in CORNERS)
    summary = summarize_corners(candidate, CORNERS, results, SPECS, lambda_failed=0.25)
    assert summary.complete and summary.failed_corners == 1 and summary.passed_corners == 4
    assert summary.pass_rate == 0.8 and summary.robust_score == -0.25
    assert summary.disposition == 'rejected' and not summary.replay_eligible
    assert candidate.nominal_reward == 0
    assert summary.worst_case_metrics['gain']['value'] == 19
    # Even lambda=0 cannot bypass the separate hard eligibility filter.
    assert summarize_corners(candidate, CORNERS, results, SPECS, lambda_failed=0).disposition == 'rejected'


def test_worst_case_respects_min_max_and_both_range_ends():
    candidate = design()
    results = [result(candidate, c) for c in CORNERS]
    results[0] = result(candidate, CORNERS[0], gain=23, dc=0.1)
    results[1] = result(candidate, CORNERS[1], power=4, dc=1.2)
    summary = summarize_corners(candidate, CORNERS, tuple(results), SPECS)
    assert summary.worst_case_metrics['gain']['value'] == 23
    assert summary.worst_case_metrics['power']['value'] == 4
    assert summary.worst_case_metrics['dc']['value'] == 1.2
    assert summary.failed_corners == 2


@pytest.mark.parametrize('mode', ['missing', 'timeout', 'measurement_error', 'nan', 'unit', 'not_evaluated'])
def test_unknown_results_never_imply_robust_pass_or_penalty(mode):
    candidate = design()
    results = [result(candidate, c) for c in CORNERS]
    if mode == 'missing':
        results.pop()
    elif mode == 'timeout':
        results[-1] = replace(results[-1], status=SimulationStatus.TIMEOUT)
    elif mode == 'measurement_error':
        results[-1] = replace(results[-1], status=SimulationStatus.MEASUREMENT_ERROR)
    elif mode == 'nan':
        results[-1] = replace(results[-1], metrics={'gain': float('nan')})
    elif mode == 'unit':
        results[-1] = replace(results[-1], metric_units={'gain': 'V'})
    else:
        results[-1] = replace(results[-1], candidate_evaluated=False)
    # An OK corner whose values are not numbers is an unknown corner only for specs that opt out of "missing value =
    # failed"; by the default since 2026-10-10 it is a failed corner (the test below). The other five never depend on it.
    specs = [replace(s, missing_is_failure=False) for s in SPECS] if mode == 'nan' else SPECS
    summary = summarize_corners(candidate, CORNERS, tuple(results), specs)
    assert not summary.complete and summary.disposition == 'inconclusive'
    assert summary.robust_score is None and summary.pass_rate is None
    assert summary.failed_corners == 0 and summary.unknown_corners == (CORNERS[-1].id,)


def test_an_ok_corner_without_its_values_is_a_failed_corner_by_default():
    candidate = design()
    results = [result(candidate, c) for c in CORNERS]
    results[-1] = replace(results[-1], metrics={'gain': float('nan')})
    summary = summarize_corners(candidate, CORNERS, tuple(results), SPECS)
    assert summary.failed_corners == 1 and summary.unknown_corners == () and summary.disposition == 'rejected'


def test_attributed_nonconvergence_counts_as_failed_corner():
    candidate = design()
    results = [result(candidate, c) for c in CORNERS]
    results[-1] = replace(results[-1], status=SimulationStatus.NONCONVERGED)
    summary = summarize_corners(candidate, CORNERS, tuple(results), SPECS)
    assert summary.complete and summary.failed_corners == 1 and summary.disposition == 'rejected'
    assert summary.worst_case_metrics['gain']['complete'] is False


@pytest.mark.parametrize('mode', ['duplicate', 'wrong_parameters', 'wrong_context', 'wrong_origin'])
def test_wrong_result_identity_is_rejected(mode):
    candidate = design()
    results = [result(candidate, c) for c in CORNERS]
    if mode == 'duplicate':
        results[-1] = results[0]
    elif mode == 'wrong_parameters':
        results[-1] = replace(results[-1], applied_parameters={('M1', 'w'): 1e-6})
    elif mode == 'wrong_context':
        results[-1] = replace(results[-1], condition=NOMINAL)
    else:
        results[-1] = replace(results[-1], origin='real')
    with pytest.raises(ValueError):
        summarize_corners(candidate, CORNERS, tuple(results), SPECS)


def test_import_rejects_validation_and_legacy_records():
    record = {'state': 'completed', 'status': 'ok', 'candidate_evaluated': True, 'evaluation_valid': True,
              'evaluation_purpose': 'nominal', 'condition': asdict(NOMINAL), 'candidate_id': 'a',
              'config_sha256': 'same_circuit_and_specs', 'reward': 0, 'origin': 'synthetic',
              'applied_parameters': [{'device': 'M1', 'parameter': 'w', 'value': 4e-6},
                                     {'device': 'M2', 'parameter': 'w', 'value': 4e-6}]}
    assert NominalDesign.from_record(record) == design()
    for changed in [dict(record, evaluation_purpose='pvt_validation'), dict(record, condition=None),
                    dict(record, candidate_evaluated=False), dict(record, reward=float('nan'))]:
        with pytest.raises(ValueError):
            NominalDesign.from_record(changed)


def test_all_passed_means_accepted_without_mutating_nominal_reward():
    candidate = design(reward=-0.1)
    summary = summarize_corners(candidate, CORNERS, tuple(result(candidate, c) for c in CORNERS), SPECS)
    assert summary.disposition == 'accepted' and summary.pass_rate == 1
    assert summary.robust_score == candidate.nominal_reward == -0.1


@pytest.mark.parametrize('gone', ['none', 'absent'])
def test_a_missing_value_counted_as_failure_fails_its_corner_without_breaking_the_summary(gone):
    specs = [replace(SPECS[0], missing_is_failure=True), *SPECS[1:]]
    candidate = design()
    results = []
    for c in CORNERS:
        corner_result = result(candidate, c)
        if c.model_section == 'ss':
            metrics, units, validity = dict(corner_result.metrics), dict(corner_result.metric_units), dict(corner_result.metric_validity)
            if gone == 'none':
                metrics['gain'], validity['gain'] = None, False
            else:
                del metrics['gain'], units['gain'], validity['gain']
            corner_result = replace(corner_result, metrics=metrics, metric_units=units, metric_validity=validity)
        results.append(corner_result)
    summary = summarize_corners(candidate, CORNERS, tuple(results), specs)   # raised TypeError / KeyError
    assert summary.failed_corners == 1 and summary.passed_corners == len(CORNERS) - 1
    assert summary.disposition == 'rejected'
    assert summary.worst_case_metrics['gain']['valid_corner_count'] == len(CORNERS) - 1
