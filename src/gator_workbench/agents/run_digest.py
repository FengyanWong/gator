"""What one finished or running RL run produced, as a compact digest an agent can read.

The agent gets no file access. The backend reads the run's own records - status, effective configuration, the raw
tables, the error log - and condenses them here: outcome and budget, every target against the best design, where the
search spent its evaluations (and whether it piled up at a bound), what failed and why, and whether the learner
moved at all. Deterministic, bounded in size, numbers only from the run itself. It is DATA in the request.

``build`` works on plain rows, so it can be tested without a run on disk; ``load`` reads a run directory.
"""
from __future__ import annotations

from collections import Counter
import math
import statistics

EDGE = 0.02            # a value within 2 % of its range from a bound counts as "at the bound"
KEEP_BEST, KEEP_LAST, CURVE_POINTS = 8, 5, 20


def _num(value, digits=6):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(f'{value:.{digits}g}') if isinstance(value, float) else value
    return value


def _stats(values):
    clean = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
    if not clean:
        return None
    return dict(n=len(clean), min=_num(min(clean)), median=_num(statistics.median(clean)), max=_num(max(clean)))


def _trend(values):
    """First third against last third of a series: did it move? None when there is too little to say."""
    clean = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    if len(clean) < 9:
        return None
    third = len(clean) // 3
    return dict(first_third_mean=_num(statistics.fmean(clean[:third])), last_third_mean=_num(statistics.fmean(clean[-third:])), n=len(clean))


def build(*, status: dict, config: dict, evaluations: list, parameters: list, metrics: list, updates: list, errors: list) -> dict:
    order = sorted(evaluations, key=lambda row: (row.get('completion_index') or 0, row.get('dispatch_index') or 0))
    by_eval_parameters, by_eval_metrics = {}, {}
    for row in parameters:
        if row.get('role') == 'independent':
            by_eval_parameters.setdefault(row.get('evaluation_id'), {})[row.get('variable_id')] = row.get('executed_value')
    for row in metrics:
        if row.get('aggregation_level') in (None, 'aggregate'):
            by_eval_metrics.setdefault(row.get('evaluation_id'), {})[row.get('metric_name')] = row.get('raw_value')

    def picture(row):
        return dict(charged=row.get('cumulative_evaluations_charged'), phase=row.get('phase'), chosen_by=row.get('action_source'),
                    status=row.get('status'), feasible=bool(row.get('all_hard_constraints_satisfied')),
                    violation=_num(row.get('normalized_constraint_violation')), reward=_num(row.get('reward')),
                    metrics={k: _num(v) for k, v in (by_eval_metrics.get(row.get('evaluation_id')) or {}).items()},
                    parameters={k: _num(v) for k, v in (by_eval_parameters.get(row.get('evaluation_id')) or {}).items()})

    valid = [row for row in order if row.get('valid')]
    ranked = sorted(valid, key=lambda row: (not row.get('all_hard_constraints_satisfied'),
                                            row.get('normalized_constraint_violation') if row.get('normalized_constraint_violation') is not None else math.inf))
    chosen = (status.get('best_design') or {}).get('evaluation_id')            # the run's own selection rule, when it has spoken
    best = next((row for row in order if chosen and row.get('evaluation_id') == chosen), ranked[0] if ranked else None)

    # where the search went, per optimized variable
    variables = []
    leaders = [row for row in config.get('parameters') or [] if not row.get('binding_group')]
    for leader in leaders:
        name, lower, upper = leader.get('variable_id'), leader.get('lower'), leader.get('upper')
        tried = [values.get(name) for values in by_eval_parameters.values() if isinstance(values.get(name), (int, float))]
        span = (upper - lower) if isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and upper > lower else None
        record = dict(variable_id=name, unit=leader.get('unit'), lower=_num(lower), upper=_num(upper), optimized=leader.get('optimized', True),
                      tried=_stats(tried), at_best=_num((by_eval_parameters.get(best.get('evaluation_id')) or {}).get(name)) if best else None)
        if span and tried:
            record['share_at_lower_bound'] = _num(sum(1 for v in tried if v <= lower + EDGE * span) / len(tried), 3)
            record['share_at_upper_bound'] = _num(sum(1 for v in tried if v >= upper - EDGE * span) / len(tried), 3)
        variables.append(record)

    # every target against what the run reached
    targets = []
    for target in config.get('targets') or []:
        name = target.get('metric_id')
        rows = [row for row in metrics if row.get('metric_name') == name and row.get('aggregation_level') in (None, 'aggregate')]
        judged = [row for row in rows if row.get('satisfied') is not None]
        targets.append(dict(metric_id=name, equation=target.get('equation') or target.get('measurement_id'),      # an older run named one probe
                            constraint=target.get('constraint'), lower=_num(target.get('lower')), upper=_num(target.get('upper')),
                            target=_num(target.get('target')), unit=target.get('unit'), hard=target.get('hard', True), active=target.get('active', True),
                            reached=_stats([row.get('raw_value') for row in rows if row.get('valid')]),
                            at_best=_num((by_eval_metrics.get(best.get('evaluation_id')) or {}).get(name)) if best else None,
                            share_satisfied=_num(sum(1 for row in judged if row.get('satisfied')) / len(judged), 3) if judged else None,
                            invalid_measurements=sum(1 for row in rows if not row.get('valid')),
                            invalid_because=dict(Counter(str(row.get('failure_reason')) for row in rows if not row.get('valid')).most_common(3))))

    failed = [row for row in order if row.get('status') not in (None, 'ok')]
    curve_rows = order[::max(1, len(order) // CURVE_POINTS)] + (order[-1:] if order else [])
    policy = [row.get('reward') for row in order if row.get('action_source') in ('sac_policy', 'mean_policy', 'sampled_policy')]
    budget, run = status.get('budget') or {}, config.get('run') or {}
    mock = bool((status.get('manifest') or {}).get('mock')) or any(row.get('provenance') == 'mock' for row in order[:1])
    caveats = ['One run with one seed is an anecdote: nothing here supports a claim about an encoder, about transfer or about an algorithm.']
    if mock:
        caveats.insert(0, 'MOCK run: the numbers come from an analytic toy backend. They show that the plumbing works, not how a circuit behaves.')
    if status.get('worker_alive'):
        caveats.append('The run is still going: this is a snapshot.')
    return dict(
        run=dict(state=status.get('state'), stop_reason=status.get('stop_reason'), mode=status.get('mode') or run.get('mode'), mock=mock,
                 seed=run.get('seed'), network=run.get('network'), concurrency=run.get('concurrency'), error=status.get('error'),
                 active_seconds=_num(status.get('active_seconds'))),
        budget=dict(max_evaluations=budget.get('max_evaluations'), charged=budget.get('charged'), completed=budget.get('completed'),
                    failed=budget.get('failed'), launches=budget.get('launches'), retries=budget.get('retries'), remaining=budget.get('remaining')),
        training=dict(settings={k: (run.get('advanced') or {}).get(k) for k in ('learning_rate', 'batch_size', 'warmup_transitions', 'update_every',
                                                                           'updates_per_transition', 'replay_capacity', 'episode_length', 'gamma')},
                      learner_updates=status.get('learner_updates'), evaluations_by_how_chosen=dict(Counter(str(row.get('action_source')) for row in order)),
                      policy_reward_trend=_trend(policy), critic_loss_trend=_trend([row.get('critic_loss') for row in updates]),
                      alpha_trend=_trend([row.get('alpha') for row in updates])),
        first_feasible=status.get('first_feasible'),
        feasible_evaluations=sum(1 for row in order if row.get('all_hard_constraints_satisfied')), valid_evaluations=len(valid), evaluations=len(order),
        best=picture(best) if best else None, targets=targets, variables=variables,
        failures=dict(count=len(failed), by_status=dict(Counter(str(row.get('status')) for row in failed)),
                      by_type=dict(Counter(str(row.get('failure_type')) for row in failed if row.get('failure_type'))),
                      typical=[str(text)[:200] for text, _ in Counter(row.get('diagnostics') for row in failed if row.get('diagnostics')).most_common(3)]),
        progress=[dict(charged=row.get('cumulative_evaluations_charged'), best_feasible=row.get('best_so_far_feasible'),
                       best_violation=_num(row.get('best_so_far_violation'))) for row in curve_rows],
        best_evaluations=[picture(row) for row in ranked[:KEEP_BEST]], last_evaluations=[picture(row) for row in order[-KEEP_LAST:]],
        errors=[dict(error=str(entry.get('error'))[:120], message=str(entry.get('message') or entry.get('detail') or '')[:240]) for entry in errors[-5:]],
        caveats=caveats)


def load(run_dir) -> dict:
    """Read one run directory (already authorized by the caller) and condense it. Reads only; a live run is fine."""
    from .. import runs
    from ..layout import RunLayout
    from ..storage.atomic import read_json, read_jsonl
    from ..storage.dataset import DatasetReader
    layout = RunLayout(run_dir)
    reader = DatasetReader(layout.data)
    status = runs.run_status(run_dir)
    return build(status=status, config=read_json(layout.effective_config, default={}) or {},
                 evaluations=reader.rows('evaluations'), parameters=reader.rows('parameters'), metrics=reader.rows('metrics'),
                 updates=reader.rows('learner_updates'), errors=list(read_jsonl(layout.logs / 'errors.jsonl')) if (layout.logs / 'errors.jsonl').is_file() else [])
