"""Pure unit-aware specification evaluation; no simulator or learning dependency."""
from __future__ import annotations

from dataclasses import dataclass
import math


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
        if not isinstance(self.required, bool) or not isinstance(self.active, bool):
            raise ValueError('Specification flags must be booleans')


@dataclass(frozen=True)
class Evaluation:
    valid: bool
    success: bool
    reward: float | None
    violations: dict[str, float | None]
    errors: dict[str, str]


class SpecificationEvaluator:
    """Reward = negative weighted mean of violations, each capped at one.

    All active required metrics must be finite, correctly unit-labelled and valid.
    Missing optional metrics are excluded from the mean. Success depends on every
    required constraint, never on its weight. There is no success bonus.
    """

    def __init__(self, specs):
        self.specs = tuple(specs)
        if len({s.metric_id for s in self.specs}) != len(self.specs):
            raise ValueError('Duplicate metric ID')
        if not any(s.active and s.required for s in self.specs):
            raise ValueError('At least one active required specification is needed')

    @property
    def required_metrics(self):
        return tuple(s.metric_id for s in self.specs if s.active and s.required)

    def evaluate(self, metrics, units, validity):
        violations, errors = {}, {}
        for spec in self.specs:
            if not spec.active:
                continue
            key, value = spec.metric_id, metrics.get(spec.metric_id)
            reason = None
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                reason = 'missing_or_nonfinite'
            elif validity.get(key) is not True:
                reason = 'invalid_measurement'
            elif units.get(key) != spec.unit:
                reason = 'unit_mismatch'
            if reason:
                violations[key], errors[key] = None, reason
                continue
            terms = [0.0]
            if spec.lower is not None:
                terms.append((spec.lower - value) / spec.scale)
            if spec.upper is not None:
                terms.append((value - spec.upper) / spec.scale)
            violations[key] = min(1.0, max(terms))
        valid = all(violations[k] is not None for k in self.required_metrics)
        success = valid and all(violations[k] == 0 for k in self.required_metrics)
        reward = None
        if valid:
            included = [s for s in self.specs if s.active and violations[s.metric_id] is not None]
            # Rescale weights before summing to avoid overflow for large finite weights.
            max_weight = max(s.weight for s in included)
            total = sum(s.weight / max_weight for s in included)
            reward = -sum((s.weight / max_weight) * violations[s.metric_id] for s in included) / total
        return Evaluation(valid, success, reward, violations, errors)
