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
    nominal_gate_band: float = 0.5
    objective_shape: str = 'clipped'

    def __post_init__(self):
        if self.violation_shape not in ('capped', 'compressed'):
            raise ValueError('Unknown violation shape')
        if self.objective_shape not in ('clipped', 'compressed'):
            raise ValueError('Objective shape must be clipped or compressed')
        if (isinstance(self.nominal_gate_band, bool) or not isinstance(self.nominal_gate_band, (int, float))
                or not math.isfinite(self.nominal_gate_band) or not 0 < self.nominal_gate_band < 1):
            raise ValueError('Nominal gate band must be finite and strictly between 0 and 1')
        for value in (self.worst_spec_share, self.objective_weight, self.margin_weight):
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError('Reward shares and bonus weights must be finite in [0, 1]')


def spec_margin(lower, upper, scale, value, margin_sides='both'):
    """Signed nearest-limit distance; equality constraints deliberately have zero clearance."""
    sides = []
    if margin_sides not in ('both', 'lower', 'upper'):
        raise ValueError('Margin sides must be both, lower or upper')
    if lower is not None and margin_sides != 'upper':
        sides.append((value - lower) / scale)
    if upper is not None and margin_sides != 'lower':
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
    if spec.missing_is_failure and key in row.metric_units and row.metric_units[key] != spec.unit:
        return 'unit_mismatch'
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
    # A completed simulation whose value for this required spec is missing or invalid makes the spec a FAILED row - the
    # full capped miss - and the design stays scored, replayed and learned from, its other specs on their measured
    # values. The default since 2026-10-10 (user: "change in the optimizer"). Before, the default was False and such a
    # design was an error: no reward, never replayed, the episode cut - a two-stage amplifier whose random designs
    # have no gain in half the cases (no unity-gain frequency, no phase margin) lost half of its budget that way,
    # each lost design with seven good measurements. False keeps the old rule for one spec. A wrong unit and an
    # infrastructure error remain errors either way.
    missing_is_failure: bool = True
    margin_sides: str = 'both'

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
        if any(not isinstance(v, bool) for v in (self.required, self.active, self.nominal_only, self.missing_is_failure)):
            raise ValueError('Specification flags must be booleans')
        if self.margin_sides not in ('both', 'lower', 'upper'):
            raise ValueError('Margin sides must be both, lower or upper')
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
    missing_counted_as_failure: dict[str, tuple[str, ...]] = field(default_factory=dict)


class SpecificationEvaluator:
    """Pure v2 reward with bit-identical default nominal penalty arithmetic.

    Condition rows expose condition, status, candidate_evaluated, metrics,
    metric_units and metric_validity. Explicit plans distinguish partial evidence
    from robust feasibility. No missing measurement is replaced with a number: on a
    completed simulation the missing value of a required spec is a failed row (the
    full capped miss; MetricSpec.missing_is_failure, the default since 2026-10-10).
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

    @staticmethod
    def _missing_failure(spec, row):
        # An explicitly reported wrong unit is a configuration fault even when
        # the value is absent. Absence of both value and unit is still absence.
        return (spec.required and spec.missing_is_failure and row.candidate_evaluated
                and row.status in ('ok', 'measurement_error')
                and _measurement_error(spec, row) in ('missing_or_nonfinite', 'invalid_measurement'))

    def missing_failures(self, row, *, nominal=True):
        return tuple(s.metric_id for s in self.specs if s.active and (nominal or not s.nominal_only)
                     and self._missing_failure(s, row))

    def row_scorable(self, row, *, nominal=True):
        """Shared evaluator/execution admission; no infrastructure attribution."""
        if not row.candidate_evaluated:
            return False
        if row.status in ('invalid_design', 'nonconverged'):
            return True
        if row.status not in ('ok', 'measurement_error'):
            return False
        missing = self.missing_failures(row, nominal=nominal)
        # A measurement-error status needs failure evidence - a required value counted as
        # failed (missing_is_failure, the default); an unexplained error cannot become
        # scorable by vacuous truth.
        if row.status == 'measurement_error' and not missing:
            return False
        return all(_measurement_error(s, row) is None or s.metric_id in missing
                   for s in self.specs if s.active and s.required and (nominal or not s.nominal_only))

    def evaluate(self, metrics, units, validity):
        return self.evaluate_conditions((SimpleNamespace(
            condition=None, status='ok', candidate_evaluated=True,
            metrics=metrics, metric_units=units, metric_validity=validity),))

    def evaluate_conditions(self, results, *, planned_conditions=None, condition_policy='off'):
        rows, conditions, plan, names = self._plan(results, planned_conditions, condition_policy)
        (labels, complete, failed, missing_failures, accepted_status,
         unavailable) = self._rows(rows, conditions, plan, names)
        (violations, errors, worst_values, worst_valid, worst_conditions, margins, missing,
         satisfied) = self._scores(rows, names, labels, failed, accepted_status)
        (valid, success, nominal_success, excluded, tightest, clearance_margin, objective_improvement,
         clearance) = self._outcome(rows, unavailable, complete, failed, violations, satisfied, accepted_status,
                                    margins, missing)
        reward = self._reward(valid, success, violations, nominal_success, rows, condition_policy,
                              objective_improvement, clearance)
        # Keep diagnostic records JSON-finite even beyond representable margin size;
        # the saturation list makes these bounds explicit, never measured values.
        saturated = tuple(key for key, value in margins.items() if value is not None and not math.isfinite(value))
        margins = {key: math.copysign(sys.float_info.max, value) if key in saturated else value
                   for key, value in margins.items()}
        clearance_margin = margins[tightest] if tightest is not None else None
        return Evaluation(valid, success, reward, violations, errors, complete, nominal_success,
                          worst_values, worst_valid, worst_conditions, missing, margins,
                          clearance_margin, tightest, excluded, objective_improvement, clearance, saturated,
                          missing_failures)

    def _plan(self, results, planned_conditions, condition_policy):
        """The results checked against the plan of conditions (nominal first, then deterministic corners in the planned
        order, each from its own simulation job): (rows, conditions, plan, names)."""
        if condition_policy not in ('off', 'always', 'after_nominal'):
            raise ValueError('Unknown training condition policy')
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
        return rows, conditions, plan, names

    def _rows(self, rows, conditions, plan, names):
        """Each result's condition label and standing: (labels, complete, failed, missing_failures, accepted_status,
        unavailable)."""
        labels = tuple(names[plan.index(c)] for c in conditions)
        complete = conditions == plan
        failed = tuple(row.candidate_evaluated and row.status in ('invalid_design', 'nonconverged') for row in rows)
        missing_failures = {labels[i]: self.missing_failures(row, nominal=i == 0) for i, row in enumerate(rows)}
        missing_failures = {key: value for key, value in missing_failures.items() if value}
        scorable = tuple(self.row_scorable(row, nominal=i == 0) for i, row in enumerate(rows))
        accepted_status = tuple(row.status == 'ok' or (row.status == 'measurement_error' and scorable[i])
                                for i, row in enumerate(rows))
        unavailable = any(not row.candidate_evaluated or (not accepted_status[i] and not failed[i])
                          for i, row in enumerate(rows))
        return labels, complete, failed, missing_failures, accepted_status, unavailable

    def _scores(self, rows, names, labels, failed, accepted_status):
        """Per active spec, over its conditions: the violation, error, worst value and condition, margin, missing
        conditions and whether every condition satisfies it."""
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
                missing_failure = self._missing_failure(spec, row)
                if (failed[i] and spec.required) or missing_failure:
                    scores.append(1.0)
                    penalty_without_value, passed = True, False
                    absent.append(labels[i])
                    errors[key] = 'missing_counted_as_failure' if missing_failure else 'attributed_design_failure'
                    continue
                if not accepted_status[i] or not row.candidate_evaluated:
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
                if spec.lower is not None and spec.margin_sides != 'upper':
                    limits.append(_distance(value, spec.lower, spec.scale))
                if spec.upper is not None and spec.margin_sides != 'lower':
                    limits.append(_distance(spec.upper, value, spec.scale))
                if limits:
                    distances.append(min(limits))
                passed = passed and _satisfied(spec, value)
            expected = names[:1] if spec.nominal_only else names
            missing[key] = tuple(name for name in expected if name not in labels or name in absent)
            invalid = any((accepted_status[i] and _measurement_error(spec, rows[i]) and not self._missing_failure(spec, rows[i]))
                          or (not accepted_status[i] and not (failed[i] and spec.required))
                          or not rows[i].candidate_evaluated for i in indices)
            violations[key] = None if invalid else max(scores, default=None)
            satisfied[key] = passed
            worst_valid[key] = bool(values) and not absent and not penalty_without_value
            worst_values[key] = worst_conditions[key] = None
            margins[key] = min(distances) if worst_valid[key] and distances else None
            if worst_valid[key]:
                if spec.comparator == 'min':
                    worst = min(values, key=lambda item: item[0])
                elif spec.comparator == 'max':
                    worst = max(values, key=lambda item: item[0])
                else:
                    worst = max(values, key=lambda item: item[1])
                worst_values[key], _, worst_conditions[key] = worst
        return violations, errors, worst_values, worst_valid, worst_conditions, margins, missing, satisfied

    def _outcome(self, rows, unavailable, complete, failed, violations, satisfied, accepted_status, margins, missing):
        """Validity, success, the nominal gate's success, the clearance margin's spec and the objective improvement."""
        valid = not unavailable and all(violations[k] is not None for k in self.required_metrics)
        success = valid and complete and not any(failed) and all(satisfied[k] for k in self.required_metrics)
        nominal_success = (accepted_status[0] and rows[0].candidate_evaluated and all(
            _measurement_error(s, rows[0]) is None and _satisfied(s, rows[0].metrics[s.metric_id])
            for s in self.specs if s.active and s.required))
        excluded = tuple(s.metric_id for s in self.specs if s.active and s.required and
                         (s.lower == s.upper or (s.margin_sides == 'lower' and s.lower is None)
                          or (s.margin_sides == 'upper' and s.upper is None)))
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
                if self.settings.objective_shape == 'clipped':
                    objective_improvement = min(max(0.0, min(1.0, v)) for v in improvements)
                else:
                    objective_improvement = min(min(math.nextafter(1.0, 0.0), _compressed(max(0.0, v)))
                                                for v in improvements)
        return (valid, success, nominal_success, excluded, tightest, clearance_margin, objective_improvement,
                clearance)

    def _reward(self, valid, success, violations, nominal_success, rows, condition_policy, objective_improvement,
                clearance):
        """The reward of a valid evaluation (None otherwise): weighted violations, the worst-spec share, the nominal
        gate, and for a success the objective and clearance bonuses."""
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
            if condition_policy == 'after_nominal':
                band = self.settings.nominal_gate_band
                if nominal_success:
                    reward *= band
                else:
                    if len(rows) != 1:
                        raise ValueError('A failed nominal gate must not have corner results')
                    reward = min(-band + (1.0 - band) * reward, math.nextafter(-band, -math.inf))
            if success and (self.settings.objective_weight or self.settings.margin_weight):
                reward += self.settings.objective_weight * objective_improvement + self.settings.margin_weight * clearance
        return reward
