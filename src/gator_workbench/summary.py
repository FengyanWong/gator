"""run_summary.json: one summary per run for research statistics (specification 8.H, 9).

Two costs are never merged:
  * first-feasibility cost  - the budget charged when the scheduler CONFIRMED a feasible design,
    including evaluations then still in flight;
  * final run cost          - everything the run consumed, including work after feasibility.
When no feasible design was found, ``first_feasible_eval_count`` is null and the observation
is right-censored at ``observation_limit``; the budget B is never written as if success had
occurred at step B.
"""
from __future__ import annotations

from datetime import datetime

from . import OUTPUT_LAYOUT_VERSION
from .storage.dataset import utcnow


def durations(manifest, *, current_active=None):
    """active = sum of segment active times; paused = gaps BETWEEN segments. Parallel job runtime is
    a third, different quantity and is reported separately."""
    segments = manifest.get('segments', [])
    active = sum(s.get('active_seconds') or 0.0 for s in segments[:-1])
    active += current_active if current_active is not None else (segments[-1].get('active_seconds') or 0.0 if segments else 0.0)
    paused = 0.0
    for before, after in zip(segments, segments[1:]):
        if before.get('ended_utc') and after.get('started_utc'):
            gap = (datetime.fromisoformat(after['started_utc']) - datetime.fromisoformat(before['ended_utc'])).total_seconds()
            paused += max(0.0, gap)
    return active, paused


def build_run_summary(engine, final_state, checkpoint, persistence_ok):
    """Build the run's research summary with feasibility, censoring, costs, provenance and persistence status."""
    ledger, counters, manifest = engine.ledger, engine.counters, engine.manifest
    snapshot = ledger.snapshot()
    first = snapshot['first_feasible']
    active, paused = durations(manifest, current_active=engine.segment_seconds())
    feasible, infeasible = engine.tracker.feasible, engine.tracker.infeasible
    complete = final_state == 'completed'
    if first is not None:
        censoring = dict(status='observed', first_feasible_eval_count=first['first_feasible_eval_count'],
                         observation_limit=snapshot['charged'], reason=None)
    else:
        reason = {'budget_exhausted': 'The evaluation budget was exhausted without a feasible design.',
                  'user_pause': 'Paused by the user before a feasible design was found; the run can continue.',
                  'user_stop': 'Stopped by the user before a feasible design was found.',
                  'user_cancel': 'Cancelled by the user.', 'wall_time_limit': 'The wall-time limit was reached.',
                  'infrastructure_failures': 'Paused safely after repeated infrastructure failures (lost bridge, '
                                             'silent daemon or no license). Not evidence about the design.',
                  }.get(engine.stop_reason, f'Ended early ({engine.stop_reason}).')
        censoring = dict(status='right_censored', first_feasible_eval_count=None,
                         observation_limit=snapshot['charged'], reason=reason,
                         note='Not a failure at the full budget unless observation_limit equals max_evaluations '
                              'and the stop reason is budget_exhausted.')
    full_state = bool(checkpoint) and checkpoint['restoration_capability'] == 'full_state'
    source = manifest.get('source_model') or {}
    best = engine.tracker.best
    return dict(
        layout_version=OUTPUT_LAYOUT_VERSION, generated_utc=utcnow().isoformat(),
        run_id=engine.run_id, experiment_id=manifest['experiment_id'], task_id=engine.task_id,
        task_name=manifest['task_name'], mode=engine.mode, provenance=engine.provenance, mock=engine.task.mock,
        seeds=manifest['seeds'], comparison_pair_id=manifest['research']['comparison_pair_id'],
        status=final_state, stop_reason=engine.stop_reason, error=engine.error,
        feasibility=dict(found=first is not None, feasible_evaluations=counters['feasible_evaluations'],
                         valid_evaluations=counters['valid_evaluations']),
        first_feasible=first,                      # evaluation, budget, launches and time AT the event
        first_nominal_feasible=snapshot['first_nominal_feasible'],
        reward=(manifest.get('definitions') or {}).get('reward'),
        first_feasible_eval_count=None if first is None else first['first_feasible_eval_count'],
        censoring=censoring,
        totals=dict(environment_steps=counters['global_env_step'], episodes=counters['episodes'],
                    candidate_evaluations_charged=snapshot['charged'],
                    candidate_evaluations_completed=snapshot['completed'],
                    spectre_launches=snapshot['launches'],
                    confirmed_spectre_launches=snapshot['confirmed_launches'],
                    uncertain_launches=snapshot['uncertain_launches'],
                    launches_unconfirmed_after_crash=counters['launches_unconfirmed_after_crash'],
                    interrupted_evaluations=counters['interrupted_evaluations'],
                    failures=snapshot['failed'], cache_hits=snapshot['cache_hits'], retries=snapshot['retries'],
                    released_reservations=snapshot['released'],
                    gradient_updates=int(getattr(engine.learner, 'updates', 0)) if not engine.frozen else 0,
                    policy_version_loaded=int(engine.learner.updates) if engine.frozen else None),
        budget=dict(max_evaluations=snapshot['max_evaluations'], max_spectre_launches=snapshot['max_launches'],
                    max_retries=snapshot['max_retries'], remaining=snapshot['remaining'],
                    definition='new candidate evaluations STARTED in the whole run, shared by all workers'),
        target_task_cost=dict(evaluations_charged=snapshot['charged'], spectre_launches=snapshot['launches'],
                              active_seconds=active,
                              note='Final cost of this run. Distinct from first_feasible, which is the cost at the '
                                   'first-feasibility event.'),
        source_model_cost=dict(status=source.get('cost_status', 'not_applicable' if engine.mode == 'scratch' else 'unknown'),
                               evaluations_charged=source.get('cost_evaluations'),
                               provenance_chain=source.get('provenance_chain', []),
                               source_run_id=source.get('run_id'), source_checkpoint_id=source.get('checkpoint_id'),
                               note='unknown is never treated as 0'),
        time=dict(active_seconds=active, paused_seconds=paused,
                  sum_job_runtime_seconds=counters['sum_job_runtime_seconds'],
                  note='sum_job_runtime_seconds adds parallel jobs and is NOT elapsed time'),
        best_design=None if best is None else dict(
            evaluation_id=best['evaluation_id'], feasible=best['feasible'], metrics=best['metrics'],
            metric_units=best['metric_units'], normalized_constraint_violation=best['violation'],
            independent_variables=best['variables'], nominal_feasible=best.get('nominal_feasible'),
            robust_feasible=best.get('robust_feasible'), conditions_complete=best.get('conditions_complete'),
            conditions_evaluated=best.get('conditions_evaluated'), conditions_planned=best.get('conditions_planned'),
            clearance_margin=best.get('clearance_margin'), tightest_clearance_spec=best.get('tightest_clearance_spec')),
        best_feasible_evaluation_id=None if feasible is None else feasible['evaluation_id'],
        best_infeasible_evaluation_id=None if infeasible is None else infeasible['evaluation_id'],
        output=dict(completeness='complete' if complete and persistence_ok else 'partial',
                    persistence_ok=persistence_ok,
                    resumability=checkpoint['restoration_capability'] if checkpoint else 'none',
                    latest_checkpoint=None if not checkpoint else checkpoint['checkpoint_id'],
                    transition_archive=engine.archive, replay_snapshots=engine.config.output.save_replay_snapshots,
                    data_cursor=engine.dataset.cursor(),
                    # why no save point was written at the end, when the run never opened them (engine_finalization)
                    **({'note': engine.final_save_note} if getattr(engine, 'final_save_note', None) else {})),
        termination=dict(state=final_state, reason=engine.stop_reason, forced=engine.forced,
                         normal_completion=complete, in_flight_lost=counters['interrupted_evaluations']),
        segments=len(manifest['segments']), concurrency=engine.config.run.concurrency, research=manifest['research'])
