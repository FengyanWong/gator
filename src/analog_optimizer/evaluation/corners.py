"""Pure M3 hooks for future nominal top-k -> fixed-corner post-validation.

Nothing in this module runs simulations, trains a policy, or writes replay.
Keep nominal_reward intact. robust_score is ONLY a post-validation ranking key;
any failed corner rejects a design even if its robust_score exceeds another's.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from analog_optimizer.backends.backend import SimulationResult, SimulationStatus
from analog_optimizer.backends.conditions import PVTCorner, SimulationCondition, finite_number
from analog_optimizer.measurements.specs import SpecificationEvaluator


@dataclass(frozen=True)
class NominalDesign:
    candidate_id: str
    # This identifies the same circuit, specifications and nominal evaluation
    # contract. Do not compare rewards from unrelated goals/testbenches.
    problem_id: str
    nominal_reward: float
    parameters: tuple[tuple[str, str, float], ...]
    condition: SimulationCondition
    origin: str

    def __post_init__(self):
        if not self.candidate_id or not self.problem_id or not finite_number(self.nominal_reward):
            raise ValueError('Candidate identity, problem identity and finite nominal reward required')
        if not self.condition.nominal_only or self.origin not in ('real', 'synthetic'):
            raise ValueError('Only explicitly nominal candidates may enter top-k selection')
        keys = [(d, p) for d, p, _ in self.parameters]
        if not keys or len(set(keys)) != len(keys) or any(not finite_number(v) for _, _, v in self.parameters):
            raise ValueError('Candidate parameters must be finite and uniquely bound')

    @property
    def assignments(self):
        return {(d, p): v for d, p, v in self.parameters}

    @classmethod
    def from_record(cls, record):
        """Import only completed, evaluated nominal M3 records, never PVT or errors.

        v1 logs lack a condition and need an explicit audited migration. Do not
        infer nominal provenance from missing fields or a filename.
        """
        if (record.get('state') != 'completed' or record.get('status') != 'ok'
                or record.get('candidate_evaluated') is not True
                or record.get('evaluation_valid') is not True
                or record.get('evaluation_purpose') != 'nominal'
                or record.get('condition') is None):
            raise ValueError('A completed valid nominal candidate record is required')
        return cls(record['candidate_id'], record['config_sha256'], record['reward'],
                   tuple((r['device'], r['parameter'], r['value']) for r in record['applied_parameters']),
                   SimulationCondition.from_dict(record['condition']), record['origin'])


def select_top_designs(candidates, *, k=3):
    """Rank distinct executed designs by nominal reward; ties use candidate ID.

    Projected duplicates do not occupy multiple slots. This is a deterministic
    data utility, not an optimizer; a saturated reward can leave many ties.
    """
    if type(k) is not int or k < 1:
        raise ValueError('k must be a positive integer')
    candidates = tuple(candidates)
    if len({(c.problem_id, c.condition, c.origin) for c in candidates}) > 1:
        raise ValueError('Top-k candidates must share problem, nominal condition and origin')
    identities = {}
    for candidate in candidates:
        old = identities.setdefault(candidate.candidate_id, candidate)
        if old != candidate:
            raise ValueError('Conflicting candidate identity')
    selected, seen = [], set()
    for candidate in sorted(identities.values(), key=lambda c: (-c.nominal_reward, c.candidate_id)):
        key = tuple(sorted(candidate.parameters))
        if key not in seen:
            selected.append(candidate)
            seen.add(key)
        if len(selected) == k:
            break
    return tuple(selected)


@dataclass(frozen=True)
class CornerSummary:
    candidate_id: str
    complete: bool
    disposition: str  # accepted | rejected | inconclusive
    passed_corners: int
    failed_corners: int
    unknown_corners: tuple[str, ...]
    pass_rate: float | None
    robust_score: float | None
    # The value causing greatest normalized violation, using comparator direction.
    # A range may fail at either end; never arbitrarily call its minimum "worst".
    worst_case_metrics: dict
    corner_details: dict
    replay_eligible: bool = False


def summarize_corners(design: NominalDesign, corners: tuple[PVTCorner, ...],
                      results: tuple[SimulationResult, ...], specs, *, lambda_failed=1.0):
    """Aggregate one deterministic result per configured corner, never average away failures.

    Missing/measurement/infrastructure failures leave the validation inconclusive:
    no robust_score or full-suite pass_rate is fabricated. Their attempts must
    still count toward an execution budget in the future caller. Circuit failures
    count only when the backend explicitly attributes an evaluated candidate.
    """
    if not finite_number(lambda_failed) or lambda_failed < 0:
        raise ValueError('lambda_failed must be finite and nonnegative')
    expected = {c.id: c for c in corners}
    if not corners or len(expected) != len(corners):
        raise ValueError('Validation corners must have unique identities')
    evaluator = SpecificationEvaluator(specs)
    indexed = {}
    for result in results:
        condition = result.condition
        if (condition is None or condition.purpose != 'pvt_validation' or condition.monte_carlo is not None
                or result.sample_index is not None or result.origin != design.origin):
            raise ValueError('Only matching deterministic PVT validation results are accepted')
        corner = condition.corner
        if expected.get(corner.id) != corner or corner.id in indexed:
            raise ValueError('Unexpected, mismatched or duplicate corner result')
        actual, proposed = result.applied_parameters, design.assignments
        if actual.keys() != proposed.keys() or any(not finite_number(actual[k]) or
                not math.isclose(actual[k], v, rel_tol=1e-8, abs_tol=1e-24) for k, v in proposed.items()):
            raise ValueError('Corner result belongs to different executed parameters')
        indexed[corner.id] = result
    passed, failed, unknown, details = 0, 0, [], {}
    observations = {s.metric_id: [] for s in evaluator.specs if s.active}
    for corner in corners:
        result = indexed.get(corner.id)
        if result is None:
            unknown.append(corner.id)
            details[corner.id] = {'state': 'missing'}
            continue
        evaluation = evaluator.evaluate(result.metrics, result.metric_units, result.metric_validity)
        if result.status == SimulationStatus.OK and result.candidate_evaluated and evaluation.valid:
            state = 'passed' if evaluation.success else 'failed'
            passed += evaluation.success
            failed += not evaluation.success
            for spec in evaluator.specs:
                if not spec.active or evaluation.violations[spec.metric_id] is None:
                    continue
                value = result.metrics.get(spec.metric_id)
                if value is None:       # "Missing value = failed": the corner fails, and there is no value to rank
                    continue
                # Unclipped distance chooses the true worst failing sample;
                # min/max tie-breaking also selects the weakest passing margin.
                if spec.comparator == 'min':
                    severity = spec.lower - value
                elif spec.comparator == 'max':
                    severity = value - spec.upper
                else:
                    severity = max(spec.lower - value, value - spec.upper)
                observations[spec.metric_id].append((severity, corner.id, value))
        elif result.status in (SimulationStatus.INVALID_DESIGN, SimulationStatus.NONCONVERGED) and result.candidate_evaluated:
            state = 'failed'
            failed += 1
        else:
            state = 'unknown'
            unknown.append(corner.id)
        details[corner.id] = {'state': state, 'job_id': result.job_id, 'status': result.status.value,
                              'reason_code': result.reason_code, 'violations': evaluation.violations,
                              'evaluation_errors': evaluation.errors}
    worst = {}
    for name, points in observations.items():
        if points:
            _, corner_id, value = max(points)
            worst[name] = {'value': value, 'corner_id': corner_id,
                           'valid_corner_count': len(points), 'complete': len(points) == len(corners)}
        else:
            worst[name] = {'value': None, 'corner_id': None, 'valid_corner_count': 0, 'complete': False}
    complete = not unknown
    score = design.nominal_reward - lambda_failed * failed if complete else None
    if score is not None and not math.isfinite(score):
        raise ValueError('robust_score overflow; use a smaller lambda_failed')
    disposition = 'rejected' if failed else ('accepted' if complete else 'inconclusive')
    return CornerSummary(design.candidate_id, complete, disposition, passed, failed, tuple(unknown),
                         passed / len(corners) if complete else None, score, worst, details)
