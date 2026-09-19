"""Constant-memory run statistics plus a bounded recent best-reward curve."""
from copy import deepcopy


class RunStatistics:
    def __init__(self, history_limit):
        self.limit = history_limit
        self.first = self.best = None
        self.valid = self.duplicates = self.count = 0
        self.failures, self.curve = {}, []

    def add(self, row):
        self.count += 1
        valid = row.get('evaluation_valid') and row.get('reward') is not None
        self.valid += bool(valid)
        self.duplicates += bool(row.get('duplicate_of'))
        if valid:
            if row.get('success') and self.first is None:
                self.first = deepcopy(row)
            if self.best is None or row['reward'] > self.best['reward']:
                self.best = deepcopy(row)
        if row.get('status') != 'ok' or not row.get('evaluation_valid'):
            key = row.get('status', row.get('state', 'unknown'))
            self.failures[key] = self.failures.get(key, 0) + 1
        self.curve.append(dict(call=row.get('simulation_calls'), best_reward=None if self.best is None else self.best['reward']))
        if self.limit is not None:
            del self.curve[:max(0, len(self.curve)-self.limit)]

    def summary(self, *, calls, wall_seconds, budget):
        first, best = self.first, self.best
        return dict(success=first is not None, calls=calls, call_budget=budget, wall_seconds=wall_seconds,
                    first_feasible_call=None if first is None else first['simulation_calls'],
                    time_to_first_feasible_seconds=None if first is None else first['time_from_start_seconds'],
                    right_censored=first is None, censor_call=calls, censor_seconds=wall_seconds,
                    valid_evaluations=self.valid, failure_counts=self.failures, duplicate_candidates=self.duplicates,
                    best_reward=None if best is None else best['reward'],
                    best_metrics=None if best is None else best['metrics'],
                    best_metric_units=None if best is None else best['metric_units'],
                    best_parameters=None if best is None else best['applied_parameters'],
                    worst_normalized_violation=None if best is None else max(
                        (v for v in best['violations'].values() if v is not None), default=None),
                    best_so_far=self.curve, history_truncated=len(self.curve) < self.count)
