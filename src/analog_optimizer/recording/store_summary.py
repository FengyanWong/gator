"""A run's summary, kept current as each evaluation finishes: counts, first and best designs, wall time.

One of the parts ExperimentStore (store.py) is made of since 2026-10-09 (plan-refactoring E5); its methods run on
the store's writer thread, inside the transaction of the operation that called them."""
from .codec import pack, unpack


class RunSummary:
    def _summary(self, row):
        from analog_optimizer.measurements.specs import SpecificationEvaluator
        run = self.db.execute('SELECT * FROM runs WHERE id=?', (row['run_id'],)).fetchone()
        summary, result, request = unpack(run['summary']), row['result'], row['request']
        specs = self._asset(self._asset(row['task_id'])['spec_id'])
        observation = self._load_state(result.get('state_id'))
        evaluation = (observation.evaluation if observation is not None else
                      SpecificationEvaluator(specs).evaluate(result['metrics'], result.get('metric_units', {}), result['metric_validity']))
        valid = (evaluation.valid and (observation is not None or result.get('status') == 'ok')
                 and not result.get('environment', {}).get('truncated', False))
        feasible = valid and evaluation.success
        # Uncapped weighted violation distinguishes very bad infeasible candidates.
        violations = {}
        if valid:
            for spec in specs:
                if spec.active and spec.required:
                    value = evaluation.worst_values.get(spec.metric_id, result['metrics'].get(spec.metric_id))
                    violations[spec.metric_id] = (1.0 if value is None else max(
                        0.0, (spec.lower - value) / spec.scale if spec.lower is not None else 0.0,
                        (value - spec.upper) / spec.scale if spec.upper is not None else 0.0))
        weights = {s.metric_id: s.weight for s in specs if s.active and s.required}
        score = sum(violations[k] * weights[k] for k in violations) / sum(weights.values()) if valid else None
        candidate = dict(eval_id=row['id'], task_id=row['task_id'], parameters=result.get('applied_parameters'),
                         metrics=result['metrics'], worst_metrics=evaluation.worst_values,
                         valid=valid, feasible=feasible, nominal_feasible=evaluation.nominal_success,
                         coverage_complete=evaluation.complete if observation is not None else None,
                         clearance_margin=evaluation.clearance_margin,
                         tightest_clearance_spec=evaluation.tightest_clearance_spec,
                         reward=evaluation.reward,
                         violations=violations if valid else evaluation.violations, violation_score=score)
        summary['evaluations'] += 1
        real = request['source'] != 'cache' and bool(result.get('simulator_invocations', 0))
        summary['real_simulations'] += int(result.get('simulator_invocations', 0)) if real else 0
        summary['real_dispatches'] = summary.get('real_dispatches', 0) + int(request['source'] == 'spectre' and row['dispatched'])
        summary['unconfirmed_invocations'] = summary.get('unconfirmed_invocations', 0) + int(
            result.get('unconfirmed_invocations', result.get('invocation_uncertain', False)))
        summary['cache_hits'] += request['source'] == 'cache'
        summary['failures'] += result.get('status') != 'ok' or not evaluation.valid
        self._count_result(summary, result, request, valid, feasible)
        summary['wall_seconds'] = row['ended'] - run['started']
        if summary['initial'] is None and request['phase'] == 'initial':
            summary['initial'] = candidate
        # PVT/MC and validation have independent records; they do not change nominal best.
        nominal = request.get('sample_id') is None and request['phase'] not in ('validation', 'pvt_validation', 'mc_validation')
        if request.get('condition_id'):
            condition = self._asset(request['condition_id'])
            if condition is not None:
                purpose = condition.get('purpose') if isinstance(condition, dict) else condition.purpose
                nominal = nominal and purpose == 'nominal'
        if nominal and evaluation.nominal_success:
            summary.setdefault('first_nominal_feasible', dict(eval_id=row['id'],
                real_simulations=summary['real_simulations'], unconfirmed_invocations=summary['unconfirmed_invocations'],
                seconds=summary['wall_seconds']))
            previous = summary.get('best_nominal_feasible')
            if previous is None or (candidate['reward'] is not None and previous.get('reward') is not None
                                    and candidate['reward'] > previous['reward']):
                summary['best_nominal_feasible'] = candidate
        if nominal and feasible:
            if not summary['has_feasible']:
                summary['first_feasible'] = dict(eval_id=row['id'], real_simulations=summary['real_simulations'],
                                                 unconfirmed_invocations=summary['unconfirmed_invocations'],
                                                 seconds=summary['wall_seconds'])
            summary['has_feasible'] = True
            objective = summary['selection'].get('objective')
            old = summary['best_feasible']
            better = old is None
            if objective:
                metric, direction = objective['metric'], objective['direction']
                value = evaluation.worst_values.get(metric, result['metrics'].get(metric))
                if value is None or direction not in ('min', 'max'):
                    raise ValueError('Feasible selection objective unavailable or invalid')
                candidate['objective'] = value
                better = old is None or (value < old['objective'] if direction == 'min' else value > old['objective'])
            if better:
                summary['best_feasible'] = candidate
        elif nominal and valid:
            old = summary['best_infeasible']
            if old is None or score < old['violation_score']:
                summary['best_infeasible'] = candidate
        self.db.execute('UPDATE runs SET summary=? WHERE id=?', (pack(summary), row['run_id']))

    @staticmethod
    def _count_result(summary, result, request, valid, feasible):
        outcome = 'feasible' if feasible else 'infeasible' if valid else 'failed'
        for field, key in [('status_counts', result.get('status', 'unknown')),
                           ('source_counts', request.get('source', 'unknown')),
                           ('outcome_counts', outcome)]:
            counts = summary.setdefault(field, {})
            counts[key] = counts.get(key, 0) + 1
        if not valid:
            key = result.get('error_class') or result.get('status', 'unknown')
            if result.get('status') == 'ok':
                key = 'invalid_metrics'
            counts = summary.setdefault('error_counts', {})
            counts[key] = counts.get(key, 0) + 1
