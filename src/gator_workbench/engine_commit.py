"""Commit one completed evaluation on the scheduler's single writer thread.

Receipt accounting, replay admission and learning precede the feasibility decision;
the durable dataset acknowledgement precedes tracker persistence and raw retention.
The supplied engine owns this state and all scheduler callbacks. No lane writes it.
"""
from __future__ import annotations

import json
from typing import NamedTuple

from . import bayes, engine_comparison
from .compile import hard_constraints
from .connection import classify_infrastructure_failure
from .run_definitions import saves_state
from .run_lock import iso
from .security import redact
from .storage.atomic import write_json
from .storage.dataset import utcnow


class Outcome(NamedTuple):
    """What one evaluation measured, judged against the Specs (RunEngine._outcome)."""
    status: str
    raw_metrics: dict
    raw_validity: dict
    raw_units: dict
    derived: dict
    spec_values: dict
    metric_values: dict
    constraint_rows: list
    valid: bool
    feasible: bool
    nominal_feasible: bool
    violation: object


def commit(engine, lane, busy, result, *, timing_batch):
    state = engine.lane_state[lane.lane_id]
    completed_at = utcnow()
    engine.counters['completion_index'] += 1
    commit_seq = engine.dataset.next_seq()
    evaluation_id = busy['evaluation_id']
    record = result.get('record') or {}
    step = result['step'] if result['ok'] else None
    observation = step[0] if step else None
    reward = step[1] if step else None
    terminated, truncated = (bool(step[2]), bool(step[3])) if step else (False, True)
    info = step[4] if step else {}
    outcome = engine._outcome(record, result, observation, truncated)
    (status, raw_metrics, raw_validity, raw_units, derived, spec_values, metric_values, constraint_rows, valid, feasible,
     nominal_feasible, violation) = outcome
    if op_is_step := busy['op'] != 'reset':
        engine.counters['global_env_step'] += 1
    if not engine._baseline_checked and busy['phase'] == 'baseline':
        # The calibration's random designs follow a valid baseline only: without one no lane can start an episode, and
        # every further evaluation would be the same failing reset. The run ends here as a baseline run of one evaluation.
        engine._baseline_checked = True
        if not valid and engine.stop_reason is None:
            engine.stop_reason = 'baseline_invalid'
            engine._event('limit_reached', reason=engine.stop_reason,
                        note='the starting design gave no valid result: no calibration design is simulated')
    failed = not valid
    infrastructure = None if valid else classify_infrastructure_failure(
        status, record.get('reason_code'), ' '.join(str(x) for x in (record.get('error'), (result.get('exception') or {}).get('message')) if x))
    receipts = record.get('jobs') or [dict(status=status, reason_code=record.get('reason_code'))]
    for receipt_index, job in enumerate(receipts):
        job_failure = classify_infrastructure_failure(job.get('status'), job.get('reason_code'), '')
        if job_failure and not result.get('cancelled'):
            infrastructure = job_failure
            engine.counters['consecutive_infrastructure_failures'] += 1
            engine.counters['infrastructure_failures'] += 1
        else:
            engine.counters['consecutive_infrastructure_failures'] = 0
        engine._event('condition_receipt', evaluation_id=evaluation_id, job_id=job.get('job_id'),
                    candidate_receipt_index=engine.counters['completion_index'], condition_receipt_index=receipt_index,
                    status=job.get('status'), infrastructure_failure=job_failure)
    if valid:
        engine.counters['last_successful_evaluation_utc'] = iso(completed_at)
    engine.ledger.complete(evaluation_id, failed=failed)
    engine.counters['failures'] += int(failed)
    engine.counters['valid_evaluations'] += int(valid)
    engine.counters['feasible_evaluations'] += int(feasible)
    engine.counters['consecutive_failures'] = engine.counters['consecutive_failures'] + 1 if failed else 0
    env_success = info.get('success') if step else None
    if valid and env_success is not None and bool(env_success) != feasible:
        engine._event('feasibility_disagreement', evaluation_id=evaluation_id, independent=feasible,
                    environment=bool(env_success), note='The independent threshold check is authoritative')
    # ---- Bayesian optimization (record 7.304): every finished design and its reward, the random warm-up's included;
    # a design without a reward (its simulation failed) counts as the worst seen
    if engine.config.run.optimizer == 'bayes' and not engine.calibration_only and op_is_step and busy['proposal'] is not None:
        asked = busy['action_source'] == bayes.Proposer.SOURCE
        if engine._proposer(lane.info['group_ids']).observe(busy['proposal'], reward, asked=asked):
            engine._event('bayes_region_restarted', evaluation_id=evaluation_id, **engine.proposer.search.state())
    # ---- learner receipt: replay admission and the updates it triggers
    transition_rows, state_rows, update_rows, admitted = [], [], [], False
    eligible = bool(info.get('replay_eligible')) if step else False
    if not engine.calibration_only and op_is_step and step is not None and observation is not None and reward is not None:
        transition = None
        if eligible:
            from analog_optimizer.training.replay import Transition
            transition = Transition.from_step(busy['previous'], busy['proposal'], step)
            if not engine.frozen:
                engine.replay.add(transition)
                admitted = True
        if engine.archive:
            transition_rows, state_rows = engine._transition_rows(busy, step, lane, commit_seq, admitted, record)
        if engine._pending_updates and not engine._defer_updates():
            engine._run_pending_updates()              # no later commit is sure to come: earlier results' updates now (7.281)
        if admitted and engine._defer_updates():
            if engine._updates_due():                  # decided now, run once the lane has its next design (7.281)
                engine._pending_updates.append(commit_seq)
        elif admitted:
            update_rows = engine._maybe_update(commit_seq)
    # ---- first feasibility: decided when the scheduler receives the result
    in_flight_before, after_first = engine._first_feasibility(busy, evaluation_id, commit_seq, nominal_feasible, feasible)
    role, best = engine._offer(busy, record, info, observation, reward, commit_seq, outcome)
    # A class may improve without replacing the overall best (e.g. an infeasible design after a feasible one).
    # Keep recording every class improvement, but replace raw outputs only for the selected design.
    retention_role = role if best is not None and best['evaluation_id'] == evaluation_id else None
    job_rows, retention_plan = engine._job_rows(busy, lane, retention_role, failed)
    if infrastructure and job_rows:
        job_rows[-1]['exit_status'] = f"{job_rows[-1]['exit_status']}:{infrastructure}"   # distinguishable in simulator_jobs
    engine.counters['retries'] = engine.ledger.retries
    committed_at = utcnow()
    diagnostics = None
    if result.get('exception'):
        diagnostics = f"{result['exception']['type']}: {result['exception']['message']}"
    elif record.get('error') or record.get('reason_code'):
        diagnostics = f"{record.get('reason_code') or ''} {record.get('error') or ''}".strip()
    evaluation = dict(
        run_id=engine.run_id, evaluation_id=evaluation_id, task_id=engine.task_id, proposal_id=busy['proposal_id'],
        worker_id=lane.lane_id, episode_id=busy['episode_id'], episode_step=int(result.get('episode_step') or 0),
        global_env_step=engine.counters['global_env_step'], dispatch_index=busy['dispatch_index'],
        completion_index=engine.counters['completion_index'], commit_seq=commit_seq, phase=busy['phase'],
        action_source=busy['action_source'], policy_version=busy['policy_version'],
        proposed_at=iso(busy['proposed_at']), started_at=iso(busy['started_at']), completed_at=iso(completed_at),
        committed_at=iso(committed_at),
        queue_seconds=(busy['started_at'] - busy['proposed_at']).total_seconds(),
        execution_seconds=(completed_at - busy['started_at']).total_seconds(), provenance=engine.provenance,
        result_source='simulation', cache_hit=False, attempts=len(busy['attempts']),
        parameters_ref=evaluation_id, metrics_ref=evaluation_id, reward=reward,
        reward_components=None if reward is None else {k: v for k, v in (info.get('violations') or {}).items()
                                                       if v is not None},
        valid=valid, all_hard_constraints_satisfied=feasible, normalized_constraint_violation=violation,
        env_success=None if env_success is None else bool(env_success),
        reward_version=record.get('reward_version'), condition_policy=record.get('condition_policy'),
        conditions_planned=info.get('conditions_planned'), conditions_evaluated=info.get('conditions_evaluated'),
        conditions_complete=info.get('conditions_complete'), nominal_feasible=nominal_feasible,
        robust_feasible=feasible if engine.config.run.conditions.policy != 'off' else None,
        clearance_margin=info.get('clearance_margin'), tightest_clearance_spec=info.get('tightest_clearance_spec'),
        clearance_rule=record.get('clearance_rule'),
        condition_results_json=json.dumps(record['condition_results']) if record.get('condition_results') else None,
        best_so_far_evaluation_id=None if best is None else best['evaluation_id'],
        best_so_far_feasible=bool(engine.tracker.feasible),
        best_so_far_violation=None if best is None else best['violation'],
        best_so_far_metrics=None if best is None else {k: v for k, v in best['metrics'].items() if v is not None},
        cumulative_evaluations_charged=engine.ledger.charged, cumulative_completed=engine.ledger.completed,
        cumulative_launches=engine.ledger.launches, in_flight_at_commit=len(engine.ledger.in_flight_ids()),
        after_first_feasible=after_first, in_flight_at_first_feasible=evaluation_id in in_flight_before,
        status=status, failure_type=None if valid else (
            infrastructure or ('invalid_measurement' if status == 'ok' else (record.get('reason_code') or status))),
        diagnostics=redact(diagnostics, 2000), terminated=terminated, truncated=truncated,
        replay_eligible=eligible, duplicate_of=record.get('duplicate_of'))
    if engine._update_rows_waiting:                    # updates learned since the last commit go with this one (7.281)
        update_rows, engine._update_rows_waiting = engine._update_rows_waiting + update_rows, []
    bundle = dict(evaluation_id=evaluation_id, commit_seq=commit_seq, rows=dict(
        evaluations=[evaluation], parameters=engine._parameter_rows(busy, record, evaluation_id),
        metrics=engine._metric_rows(evaluation_id, raw_metrics, raw_validity, raw_units, derived, spec_values,
                                  constraint_rows, status, record.get('condition_results')),
        simulator_jobs=job_rows, learner_updates=update_rows, states=state_rows, transitions=transition_rows))
    engine.dataset.commit(bundle)                              # <- durable acknowledgement
    # ---- the archive comparison's search (T0/T+/M+): told each finished design once it is durable; a crash before this
    # line leaves the design in the tables, and the resume tells it (engine_comparison.after_crash)
    if (engine_comparison.is_search(engine.config) and not engine.calibration_only and op_is_step
            and busy['proposal'] is not None):
        engine_comparison.observe(engine, evaluation_id=evaluation_id, action_source=busy['action_source'],
                                  proposal=busy['proposal'], status=status, reward=reward,
                                  parameter_rows=bundle['rows']['parameters'], metric_rows=bundle['rows']['metrics'])
    timings = record.get('timings')
    if isinstance(timings, dict) and timings:
        engine._timings.append(dict(evaluation_id=evaluation_id, worker_id=lane.lane_id, phase=busy['phase'],
                                  committed_at=iso(committed_at), seconds=timings))
        if len(engine._timings) >= timing_batch:
            engine._write_timings()
    if role is not None:
        write_json(engine.layout.best_design / 'tracker_state.json',
                   dict(last_commit_seq=commit_seq, **engine.tracker.state_dict()))
    engine._apply_retention(retention_plan, retention_role)
    # ---- lane state for the next dispatch
    if result.get('exception') and not result.get('cancelled'):
        state['finished'] = True
        if engine.stop_reason is None:
            engine.stop_reason = 'evaluation_exception'
            engine.error = redact(diagnostics, 2000)
            engine._log_error('evaluation_exception', None, evaluation_id=evaluation_id, detail=diagnostics)
    else:
        state['observation'] = observation
        state['needs_reset'] = terminated or truncated or observation is None
        if busy['op'] == 'reset':                # the lane keeps a valid simulated reset for the next reused ones
            state['reset_cache_valid'] = bool(result['ok'] and info.get('evaluation_valid') and observation is not None
                                              and not terminated and not truncated)
            state['resets_since_check'] = 0
    every, seconds = engine.config.output.checkpoint_every_evaluations, engine.config.output.checkpoint_every_seconds
    if saves_state(engine.config) and (
            (every and commit_seq - engine.counters['last_checkpoint_commit'] >= every)
            or (seconds and engine._clock() - engine.last_checkpoint_time >= seconds)):
        engine.checkpoint_due = True
    engine._write_status('running', throttle=0.5)


def outcome(engine, record, result, observation, truncated):
    """What the evaluation measured, judged against the Specs: its status, the simulator's own results, the probes and
    specs worked out from them, and whether the design is valid and feasible (at every condition it ran at)."""
    # The lane's record also carries the computed specs (spec_equations: added to the simulation result so that the
    # reward sees them). The simulator's own results are everything else; they alone feed the probes and raw rows.
    plan, computed = engine.compiled.plan, set(engine.compiled.plan.injected)
    raw_metrics = {k: v for k, v in (record.get('metrics') or {}).items() if k not in computed}
    raw_validity = {k: v for k, v in (record.get('metric_validity') or {}).items() if k not in computed}
    raw_units = {k: v for k, v in (record.get('metric_units') or {}).items() if k not in computed}
    status = record.get('status') or ('cancelled' if result.get('cancelled') else 'execution_error')
    if not result['ok'] and not result.get('cancelled'):
        status = 'execution_error'
    usable = {k: v for k, v in raw_metrics.items() if raw_validity.get(k) is True and v is not None}
    derived = plan.probe_values(usable)
    spec_values = plan.spec_values(probes=derived)
    metric_values, metric_valid = {}, {}
    for target in engine.compiled.targets:
        value = spec_values.get(target['metric_id'])
        ok = value is not None and status in ('ok', 'measurement_error')
        metric_values[target['metric_id']], metric_valid[target['metric_id']] = (value if ok else None), ok
    valid, feasible, constraint_rows, violation = hard_constraints(engine.compiled.targets, metric_values, metric_valid)
    nominal_feasible = feasible
    if observation is not None and observation.condition_results:
        evaluation = observation.evaluation
        checks = []
        for index, row in enumerate(observation.condition_results):
            targets = tuple(t for t in engine.compiled.targets if index == 0 or not t['nominal_only'])
            validity = {t['metric_id']: row.metric_validity.get(t['metric_id']) is True
                        and row.metric_units.get(t['metric_id']) == t['unit'] and row.status in ('ok', 'measurement_error')
                        and row.candidate_evaluated for t in targets}
            checks.append(hard_constraints(targets, row.metrics, validity))
        valid = all(check[0] for check in checks) and not truncated
        feasible = valid and evaluation.complete and all(check[1] for check in checks)
        nominal_feasible = checks[0][1]
        violation = max((check[3] or 0 for check in checks), default=0) if valid else None
        metric_values = evaluation.worst_values
        spec_values = metric_values
        by_metric = {}
        for _, _, checked, _ in checks:
            for row in checked:
                old = by_metric.get(row['metric_id'])
                if old is None or (row.get('normalized_violation') or 0) > (old.get('normalized_violation') or 0):
                    by_metric[row['metric_id']] = row
        constraint_rows = list(by_metric.values())
    return Outcome(status, raw_metrics, raw_validity, raw_units, derived, spec_values, metric_values, constraint_rows,
                   valid, feasible, nominal_feasible, violation)


def first_feasibility(engine, busy, evaluation_id, commit_seq, nominal_feasible, feasible):
    """The run's first (nominally) feasible design, decided when the scheduler receives the result; the stop at the first
    feasible design. Returns (the evaluations in flight at the first feasible one, whether it came before)."""
    in_flight_before = set(engine.ledger.first_feasible['in_flight_evaluation_ids']) if engine.ledger.first_feasible else set()
    after_first = engine.ledger.first_feasible is not None
    if nominal_feasible and engine.ledger.first_nominal_feasible is None:
        first = engine.ledger.mark_first_feasible(evaluation_id, dispatch_index=busy['dispatch_index'],
            commit_seq=commit_seq, active_seconds=engine._active_seconds(),
            wall_seconds=(utcnow() - engine._run_created()).total_seconds(), nominal=True)
        engine._event('first_nominal_feasible', **first)
    if feasible and not after_first:
        first = engine.ledger.mark_first_feasible(evaluation_id, dispatch_index=busy['dispatch_index'],
                                                commit_seq=commit_seq, active_seconds=engine._active_seconds(),
                                                wall_seconds=(utcnow() - engine._run_created()).total_seconds())
        engine._event('first_feasible', **first)
        if engine.config.run.stop_at_first_feasible and engine.stop_reason is None:
            engine.stop_reason = 'first_feasible'
    return in_flight_before, after_first


def offer(engine, busy, record, info, observation, reward, commit_seq, outcome):
    """The evaluation as a candidate of the best-design tracker. Returns (its role there, the tracker's best)."""
    (status, raw_metrics, raw_validity, raw_units, derived, spec_values, metric_values, constraint_rows, valid, feasible,
     nominal_feasible, violation) = outcome
    candidate = engine._candidate(busy, record, metric_values, raw_units, constraint_rows, valid, feasible,
                                violation, reward, commit_seq)
    candidate.update(nominal_feasible=nominal_feasible, nominal_metrics=record.get('metrics'),
                     robust_feasible=feasible if engine.config.run.conditions.policy != 'off' else None,
                     worst_metrics=metric_values, conditions_complete=info.get('conditions_complete'),
                     conditions_evaluated=info.get('conditions_evaluated'), conditions_planned=info.get('conditions_planned'),
                     clearance_margin=info.get('clearance_margin'), tightest_clearance_spec=info.get('tightest_clearance_spec'),
                     clearance_rule=record.get('clearance_rule'),
                     conditions=[row['condition']['corner']['id'] if row['condition'] else 'nominal'
                                 for row in record.get('condition_results', [])] or ['nominal'])
    if candidate['robust_feasible'] and engine.compiled.preference and observation is not None:
        preference = engine.compiled.preference
        spec = next(s for s in observation.specs if s.metric_id == preference['metric'])
        applicable = observation.condition_results[:1] if spec.nominal_only else observation.condition_results
        values = [row.metrics.get(spec.metric_id) for row in applicable
                  if row.metric_validity.get(spec.metric_id) is True]
        candidate['worst_metrics'] = dict(metric_values)
        candidate['worst_metrics'][spec.metric_id] = ((max(values) if preference['direction'] == 'min' else min(values))
                                                     if len(values) == len(applicable) else None)
    role = engine.tracker.offer(candidate)
    best = engine.tracker.best
    return role, best
