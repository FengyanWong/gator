"""Pure unit-aware specification evaluation; no simulator or learning dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import sys
from types import SimpleNamespace


REWARD_VERSION = 'constraint_violation_v2'
CLEARANCE_RULE = 'tightest_eligible_hard_spec_v1'


@dataclass(frozen=True)
class RewardSettings:
    violation_shape: str = 'capped'
    worst_spec_share: float = 0.0
    objective_weight: float = 0.0
    margin_weight: float = 0.0

    def __post_init__(self):
        if self.violation_shape not in ('capped', 'compressed'):
            raise ValueError('Unknown violation shape')
        for value in (self.worst_spec_share, self.objective_weight, self.margin_weight):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError('Reward shares and bonus weights must be finite in [0, 1]')


def spec_margin(lower, upper, scale, value):
    """Signed nearest-limit distance; equality constraints deliberately have zero clearance."""
    sides = []
    if lower is not None:
        sides.append((value - lower) / scale)
    if upper is not None:
        sides.append((upper - value) / scale)
    return min(sides) if sides else math.inf


def _compressed(value):
    # The input can overflow from finite subtraction/division; never compute inf/inf.
    return value / (1.0 + value) if value <= 1.0 else 1.0 - 1.0 / (1.0 + value)


def _distance(high, low, scale):
    difference = high - low
    return difference / scale if math.isfinite(difference) else high / scale - low / scale


def _satisfied(spec, value):
    return ((spec.lower is None or value >= spec.lower)
            and (spec.upper is None or value <= spec.upper))


def _measurement_error(spec, row):
    key, value = spec.metric_id, row.metrics.get(spec.metric_id)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 'missing_or_nonfinite'
    if row.metric_validity.get(key) is not True:
        return 'invalid_measurement'
    if row.metric_units.get(key) != spec.unit:
        return 'unit_mismatch'
    return None


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    unit: str
    comparator: str
    scale: float
    lower: float | None = None
    upper: float | None = None
    weight: float = 1.0
    required: bool = True
    active: bool = True
    objective: str = 'none'
    nominal_only: bool = False

    def __post_init__(self):
        if not self.metric_id or not self.unit or self.comparator not in ('min', 'max', 'range'):
            raise ValueError('Invalid metric identity, unit or comparator')
        for v in (self.scale, self.weight):
            if isinstance(v, bool) or not math.isfinite(v) or v <= 0:
                raise ValueError('Specification scale and weight must be finite and positive')
        bounds = (self.lower, self.upper)
        if any(v is not None and (isinstance(v, bool) or not math.isfinite(v)) for v in bounds):
            raise ValueError('Targets must be finite')
        if ((self.comparator == 'min' and (self.lower is None or self.upper is not None))
                or (self.comparator == 'max' and (self.upper is None or self.lower is not None))
                or (self.comparator == 'range' and
                    (None in bounds or self.lower > self.upper))):
            raise ValueError('Targets do not match the comparator')
        if any(not isinstance(v, bool) for v in (self.required, self.active, self.nominal_only)):
            raise ValueError('Specification flags must be booleans')
        if (self.objective not in ('none', 'min', 'max')
                or (self.objective == 'min' and self.upper is None)
                or (self.objective == 'max' and self.lower is None)):
            raise ValueError('Objective requires its directional limit')


@dataclass(frozen=True)
class Evaluation:
    valid: bool
    success: bool
    reward: float | None
    violations: dict[str, float | None]
    errors: dict[str, str]
    complete: bool = True
    nominal_success: bool = False
    worst_values: dict[str, float | None] = field(default_factory=dict)
    worst_valid: dict[str, bool] = field(default_factory=dict)
    worst_conditions: dict[str, str | None] = field(default_factory=dict)
    missing_coverage: dict[str, tuple[str, ...]] = field(default_factory=dict)
    margins: dict[str, float | None] = field(default_factory=dict)
    clearance_margin: float | None = None
    tightest_clearance_spec: str | None = None
    clearance_excluded: tuple[str, ...] = ()
    objective_improvement: float = 0.0
    clearance: float = 0.0
    saturated_margins: tuple[str, ...] = ()


class SpecificationEvaluator:
    """Pure v2 reward with bit-identical default nominal penalty arithmetic.

    Condition rows expose condition, status, candidate_evaluated, metrics,
    metric_units and metric_validity. Explicit plans distinguish partial evidence
    from robust feasibility. No missing measurement is replaced with a number.
    """

    def __init__(self, specs, settings: RewardSettings | None = None):
        self.specs = tuple(specs)
        self.settings = settings if settings is not None else RewardSettings()
        if not isinstance(self.settings, RewardSettings):
            raise ValueError('Typed reward settings are required')
        if len({s.metric_id for s in self.specs}) != len(self.specs):
            raise ValueError('Duplicate metric ID')
        if not any(s.active and s.required for s in self.specs):
            raise ValueError('At least one active required specification is needed')
        if sum(s.active and s.objective != 'none' for s in self.specs) > 1:
            raise ValueError('At most one active objective is permitted')

    @property
    def required_metrics(self):
        return tuple(s.metric_id for s in self.specs if s.active and s.required)

    def evaluate(self, metrics, units, validity):
        return self.evaluate_conditions((SimpleNamespace(
            condition=None, status='ok', candidate_evaluated=True,
            metrics=metrics, metric_units=units, metric_validity=validity),))

    def evaluate_conditions(self, results, *, planned_conditions=None):
        rows = tuple(results)
        if not rows:
            raise ValueError('Nominal result is required')
        conditions = tuple(row.condition for row in rows)
        plan = conditions if planned_conditions is None else tuple(planned_conditions)
        if not plan or conditions[0] != plan[0]:
            raise ValueError('Results must start with the planned nominal condition')
        if plan[0] is not None and not plan[0].nominal_only:
            raise ValueError('The first condition must be nominal')
        names = tuple(c.corner.id if c is not None else 'nominal' for c in plan)
        if len(set(plan)) != len(plan) or len(set(names)) != len(names):
            raise ValueError('Duplicate planned condition')
        if any(c is None or c.nominal_only or c.monte_carlo is not None for c in plan[1:]):
            raise ValueError('Only deterministic non-nominal corners may follow nominal')
        if len(set(conditions)) != len(conditions) or any(c not in plan for c in conditions):
            raise ValueError('Duplicate or unplanned result condition')
        if tuple(sorted(conditions, key=plan.index)) != conditions:
            raise ValueError('Results must follow the planned condition order')
        jobs = [getattr(row, 'job_id', None) for row in rows]
        known_jobs = [job for job in jobs if job is not None]
        if len(known_jobs) != len(set(known_jobs)):
            raise ValueError('A simulation job cannot supply two conditions')
        labels = tuple(names[plan.index(c)] for c in conditions)
        complete = conditions == plan
        failed = tuple(row.candidate_evaluated and row.status in ('invalid_design', 'nonconverged') for row in rows)
        unavailable = any(not row.candidate_evaluated or (row.status != 'ok' and not failure)
                          for row, failure in zip(rows, failed))
        violations, errors, worst_values, worst_valid, worst_conditions = {}, {}, {}, {}, {}
        margins, missing, satisfied = {}, {}, {}
        for spec in self.specs:
            if not spec.active:
                continue
            key = spec.metric_id
            indices = (0,) if spec.nominal_only else range(len(rows))
            values, scores, distances, absent = [], [], [], []
            passed, penalty_without_value = True, False
            for i in indices:
                row = rows[i]
                reason = _measurement_error(spec, row)
                if failed[i] and spec.required:
                    scores.append(1.0)
                    penalty_without_value, passed = True, False
                    absent.append(labels[i])
                    errors[key] = 'attributed_design_failure'
                    continue
                if row.status != 'ok' or not row.candidate_evaluated:
                    reason = 'condition_unavailable'
                if reason:
                    absent.append(labels[i])
                    errors.setdefault(key, reason)
                    passed = False
                    continue
                value = row.metrics[key]
                terms = [0.0]
                if spec.lower is not None:
                    terms.append(_distance(spec.lower, value, spec.scale))
                if spec.upper is not None:
                    terms.append(_distance(value, spec.upper, spec.scale))
                d = max(terms)
                score = min(1.0, d) if self.settings.violation_shape == 'capped' else _compressed(d)
                scores.append(score)
                values.append((value, score, labels[i]))
                limits = []
                if spec.lower is not None:
                    limits.append(_distance(value, spec.lower, spec.scale))
                if spec.upper is not None:
                    limits.append(_distance(spec.upper, value, spec.scale))
                distances.append(min(limits))
                passed = passed and _satisfied(spec, value)
            expected = names[:1] if spec.nominal_only else names
            missing[key] = tuple(name for name in expected if name not in labels or name in absent)
            invalid = any((rows[i].status == 'ok' and _measurement_error(spec, rows[i]))
                          or (rows[i].status != 'ok' and not (failed[i] and spec.required))
                          or not rows[i].candidate_evaluated for i in indices)
            violations[key] = None if invalid else max(scores, default=None)
            satisfied[key] = passed
            worst_valid[key] = bool(values) and not absent and not penalty_without_value
            worst_values[key] = worst_conditions[key] = None
            margins[key] = min(distances) if worst_valid[key] else None
            if worst_valid[key]:
                if spec.comparator == 'min':
                    worst = min(values, key=lambda item: item[0])
                elif spec.comparator == 'max':
                    worst = max(values, key=lambda item: item[0])
                else:
                    worst = max(values, key=lambda item: item[1])
                worst_values[key], _, worst_conditions[key] = worst
        valid = not unavailable and all(violations[k] is not None for k in self.required_metrics)
        success = valid and complete and not any(failed) and all(satisfied[k] for k in self.required_metrics)
        nominal_success = (rows[0].status == 'ok' and rows[0].candidate_evaluated and all(
            _measurement_error(s, rows[0]) is None and _satisfied(s, rows[0].metrics[s.metric_id])
            for s in self.specs if s.active and s.required))
        excluded = tuple(s.metric_id for s in self.specs if s.active and s.required and s.lower == s.upper)
        eligible = [s.metric_id for s in self.specs if s.active and s.required and s.metric_id not in excluded]
        tightest = min(eligible, key=lambda k: margins[k]) if eligible and all(margins[k] is not None for k in eligible) else None
        clearance_margin = margins[tightest] if tightest is not None else None
        objective_improvement, clearance = 0.0, 0.0
        if success:
            clearance = _compressed(max(0.0, clearance_margin)) if clearance_margin is not None else 0.0
            objective = next((s for s in self.specs if s.active and s.objective != 'none'), None)
            if objective is not None and not missing[objective.metric_id]:
                applicable = rows[:1] if objective.nominal_only else rows
                improvements = [(_distance(objective.upper, r.metrics[objective.metric_id], objective.scale)
                                 if objective.objective == 'min' else
                                 _distance(r.metrics[objective.metric_id], objective.lower, objective.scale))
                                for r in applicable]
                objective_improvement = min(max(0.0, min(1.0, v)) for v in improvements)
        reward = None
        if valid:
            included = [s for s in self.specs if s.active and violations[s.metric_id] is not None]
            # Rescale weights before summing to avoid overflow for large finite weights.
            max_weight = max(s.weight for s in included)
            total = sum(s.weight / max_weight for s in included)
            reward = -sum((s.weight / max_weight) * violations[s.metric_id] for s in included) / total
            if self.settings.worst_spec_share:
                share = self.settings.worst_spec_share
                reward = (1.0 - share) * reward - share * max(violations[k] for k in self.required_metrics)
            if success and (self.settings.objective_weight or self.settings.margin_weight):
                reward += self.settings.objective_weight * objective_improvement + self.settings.margin_weight * clearance
        # Keep diagnostic records JSON-finite even beyond representable margin size;
        # the saturation list makes these bounds explicit, never measured values.
        saturated = tuple(key for key, value in margins.items() if value is not None and not math.isfinite(value))
        margins = {key: math.copysign(sys.float_info.max, value) if key in saturated else value
                   for key, value in margins.items()}
        clearance_margin = margins[tightest] if tightest is not None else None
        return Evaluation(valid, success, reward, violations, errors, complete, nominal_success,
                          worst_values, worst_valid, worst_conditions, missing, margins,
                          clearance_margin, tightest, excluded, objective_improvement, clearance, saturated)
