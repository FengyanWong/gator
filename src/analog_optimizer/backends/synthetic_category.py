"""Named analytic objectives for cross-category plumbing, never circuit metrics."""
from dataclasses import replace
import math

from .synthetic_sizing import SyntheticSizingBackend


class SyntheticCategoryBackend(SyntheticSizingBackend):
    """Apply an explicit affine transform to the executed quadratic toy score.

    Distinct metric IDs exercise the fixed registry and min/max/range masks.
    No electrical metric, oscillation test or simulator behavior is implied.
    """
    def __init__(self, graph, *, targets, metric_id, score_multiplier, score_offset):
        super().__init__(graph, targets=targets)
        if not isinstance(metric_id, str) or not metric_id.startswith('toy_'):
            raise ValueError('Synthetic category metrics must have an explicit toy_ identity')
        if (not all(math.isfinite(v) for v in (score_multiplier, score_offset))
                or score_multiplier == 0):
            raise ValueError('Toy score transform must be finite and nonconstant')
        self.metric_id = metric_id
        self.score_multiplier, self.score_offset = score_multiplier, score_offset

    def run_simulation(self, request):
        result = super().run_simulation(request)
        value = self.score_offset + self.score_multiplier * result.metrics['score']
        return replace(result, backend_kind='analytic-category-sizing-v1',
                       reason_code='synthetic_category_objective_not_circuit_simulation',
                       metrics={self.metric_id: value}, metric_units={self.metric_id: 'fixture'},
                       metric_validity={self.metric_id: True})
