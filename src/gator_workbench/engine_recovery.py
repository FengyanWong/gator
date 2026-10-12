"""Restore a checkpoint and reconcile the durable records written after it.

All accounting mutates the supplied scheduler context before simulation lanes open.
Checkpoint weights and RNG are restored first; tables recover cost, feasibility and
replay receipts, and unfinished dispatches retain their launch leases.
"""
from __future__ import annotations

from . import best_design
from .run_lock import iso
from .storage.atomic import read_json, read_jsonl, write_json
from .storage.dataset import DatasetReader
from .trajectory import TrajectoryLoader


def restore(engine, run_state):
    """resume keeps counters. Durable tables are the source of truth for cost after a crash."""
    if not run_state or run_state.get('version') != 'workbench-run-state-v1':
        raise RuntimeError('The checkpoint carries no workbench run state; it cannot continue this run')
    if run_state['run_id'] != engine.run_id or run_state['task_definition_hash'] != engine.task_hash:
        raise RuntimeError('Checkpoint belongs to another run or task')
    engine.ledger.load_state(run_state['ledger'])
    engine.counters.update(run_state['counters'])
    collector = run_state['collector']
    engine.rng.setstate(collector['rng_state'])
    engine.tracker = best_design.BestDesignTracker(engine.compiled.preference, collector.get('best_design'))
    engine.previous_best_waveform = collector.get('previous_best_waveform')
    if engine.rehearsal is not None:
        if 'rehearsal' not in collector:
            raise RuntimeError('Checkpoint lacks rehearsal sampler state')
        engine.rehearsal.load_state_dict(collector['rehearsal'])
    cursor = run_state['data_cursor']
    report = dict(checkpoint_commit_seq=cursor['commit_seq'], recovery=engine.dataset.recovery)
    # The best design is also written on every improvement (best_design/tracker_state.json), which reaches further
    # than the last checkpoint. Without it a crash after the only feasible evaluation resumed with an empty tracker,
    # finalized as "no feasible design" and DELETED parameters.csv / optimized_dut.scs of a design its own
    # evaluations table still held (review of 2026-09-23).
    later = read_json(engine.layout.best_design / 'tracker_state.json', default=None)
    if later and (later.get('last_commit_seq') or 0) > cursor['commit_seq']:
        engine.tracker = best_design.BestDesignTracker(engine.compiled.preference, later)
        report['best_design_after_checkpoint'] = later['last_commit_seq']
    engine.dataset.flush()
    if engine.dataset.last_seq > cursor['commit_seq']:
        report['counters_after_checkpoint'] = engine._count_since(cursor['commit_seq'])
    interrupted = engine._record_interrupted()
    post = engine.dataset.last_seq - cursor['commit_seq']
    if post or interrupted:
        reader = DatasetReader(engine.layout.data)
        evaluations = reader.rows('evaluations', ['evaluation_id', 'status', 'cache_hit', 'attempts', 'valid'])
        jobs = reader.rows('simulator_jobs', ['launch_counted', 'invocation_confirmed'])
        unresolved = read_json(engine.layout.data / '_journal' / 'unresolved-launch-leases.json', default={})
        unknown = sum(item['allowance'] for item in unresolved.values())
        report['reconciled'] = engine.ledger.reconcile(
            charged=len(evaluations), completed=len(evaluations),
            failed=sum(1 for e in evaluations if not e['valid']),
            launches=sum(1 for j in jobs if j['launch_counted']) + unknown,
            uncertain=sum(1 for j in jobs if j['launch_counted'] and j['invocation_confirmed'] is None) + unknown,
            retries=sum(max(0, e['attempts'] - 1) for e in evaluations),
            cache_hits=sum(1 for e in evaluations if e['cache_hit']))
        engine.counters['completion_index'] = max(engine.counters['completion_index'], len(evaluations))
        report['post_checkpoint_evaluations'] = post
        if post and not engine.frozen and engine.replay is not None and engine.archive:
            readmitted = 0
            loader = TrajectoryLoader(engine.layout.run_dir)
            rows = {r['candidate_id']: r for r in loader.transition_rows()}
            for transition in loader.transitions():
                row = rows[transition.candidate_id]
                if row['commit_seq'] > cursor['commit_seq'] and row['replay_admitted']:
                    engine.replay.add(transition)
                    readmitted += 1
            report['readmitted_transitions'] = readmitted
            report['note'] = ('Learner weights are those of the checkpoint. Experience committed after it was '
                              're-admitted to replay; the learner updates made after it are not recoverable.')
    if engine.encoder is not None:
        engine.encoder.written = {r['state_id'] for r in DatasetReader(engine.layout.data).rows('states', ['state_id'])}
    # A pause for infrastructure failures asks for the connection gate to pass again, and a resume passes it: the count
    # starts over. Restored as saved it was still at the limit, so every Resume paused again at once, nothing evaluated
    # (review of 2026-10-01).
    engine.counters['consecutive_infrastructure_failures'] = 0
    engine._pending_events = [('resumed', report)]


def count_since(engine, checkpoint_seq):
    """The run's own counts, brought up to the evaluations it committed after the save point (record 7.322). The
    tables hold them, but the save point's older numbers were restored as they stood: a row of failures that a
    success had since ended was still counted, so one more failure stopped the run; failures made after the save
    point were forgotten; and a first passing design found after it was lost - the summary said none was found, and
    a run told to stop at its first passing design went on to a second one. Each evaluation is counted as `_commit`
    counted it. The row of an evaluation an earlier crash interrupted is none: it never came back. Returns what
    the resume event says of it."""
    columns = ['evaluation_id', 'commit_seq', 'status', 'valid', 'all_hard_constraints_satisfied', 'nominal_feasible',
               'global_env_step', 'episode_id', 'completed_at', 'dispatch_index', 'cumulative_evaluations_charged',
               'cumulative_completed', 'cumulative_launches', 'in_flight_at_commit']
    later = sorted((row for row in DatasetReader(engine.layout.data).rows('evaluations', columns)
                    if row['commit_seq'] > checkpoint_seq and row['status'] != 'interrupted'), key=lambda row: row['commit_seq'])
    try:        # the record made at the event (its seconds, what was in flight); the table's own numbers without it
        logged = {(e.get('event'), e.get('evaluation_id')): e for e in read_jsonl(engine.layout.logs / 'events.jsonl')}
    except (OSError, ValueError):
        logged = {}
    found = None
    for row in later:
        failed = not row['valid']
        engine.counters['failures'] += int(failed)
        engine.counters['valid_evaluations'] += int(not failed)
        engine.counters['feasible_evaluations'] += int(bool(row['all_hard_constraints_satisfied']))
        engine.counters['consecutive_failures'] = engine.counters['consecutive_failures'] + 1 if failed else 0
        engine.counters['global_env_step'] = max(engine.counters['global_env_step'], row['global_env_step'] or 0)
        if not failed and row['completed_at'] is not None:
            engine.counters['last_successful_evaluation_utc'] = iso(row['completed_at'])
        # an episode begun after the save point keeps its number: the next one must not take it again
        number = (row['episode_id'] or '').rpartition('-')[2]
        if number.isdigit():
            engine.counters['episodes'] = max(engine.counters['episodes'], int(number))
        for field, column in (('first_nominal_feasible', 'nominal_feasible'), ('first_feasible', 'all_hard_constraints_satisfied')):
            if not row[column] or getattr(engine.ledger, field) is not None:
                continue
            event = logged.get((field, row['evaluation_id']))
            first = {k: v for k, v in event.items() if k not in ('time_utc', 'event', 'run_id')} if event else dict(
                evaluation_id=row['evaluation_id'], first_feasible_eval_count=row['cumulative_evaluations_charged'],
                dispatch_index=row['dispatch_index'], completed_count=row['cumulative_completed'],
                in_flight_count=row['in_flight_at_commit'], in_flight_evaluation_ids=[],
                spectre_launches=row['cumulative_launches'], commit_seq=row['commit_seq'], active_seconds=None,
                wall_seconds=None, convention='from the evaluations table after a crash: evaluations charged when '
                                              'this design was committed; the seconds at the event are not known')
            engine.ledger.restore_first_feasible(first, nominal=field == 'first_nominal_feasible')
            if field == 'first_feasible':
                found = row['evaluation_id']
    if found and engine.config.run.stop_at_first_feasible:        # the stop it asked for was cut off by the crash
        engine.stop_reason = 'first_feasible'
    return dict(evaluations=len(later), consecutive_failures=engine.counters['consecutive_failures'], first_feasible=found)


def record_interrupted(engine):
    """Evaluations that STARTED (budget charged) but were never committed because the process died."""
    started = {r['evaluation_id']: r for r in read_jsonl(engine.layout.data / '_journal' / 'dispatch.jsonl')}
    lost = [r for key, r in started.items() if not engine.dataset.has(key)]
    lease_path = engine.layout.data / '_journal' / 'unresolved-launch-leases.json'
    leases = read_json(lease_path, default={})
    for record in sorted(lost, key=lambda r: r['dispatch_index']):
        if not engine.task.mock:
            # A real dispatch without a coordinator receipt cannot release its allocation: an unknown lease,
            # not a fabricated simulator job or confirmed call. The toy backend launches nothing: no lease.
            leases[record['evaluation_id']] = dict(allowance=record.get('launch_allowance', 1),
                                                  dispatch=record, state='unresolved')
            write_json(lease_path, leases)
        seq, now = engine.dataset.next_seq(), iso()
        engine.counters['completion_index'] += 1
        row = dict(run_id=engine.run_id, evaluation_id=record['evaluation_id'], task_id=engine.task_id,
                   proposal_id=record['proposal_id'], worker_id=record['worker_id'],
                   episode_id=record.get('episode_id') or 'unknown', episode_step=record.get('episode_step', 0),
                   global_env_step=engine.counters['global_env_step'], dispatch_index=record['dispatch_index'],
                   completion_index=engine.counters['completion_index'], commit_seq=seq, phase=record['phase'],
                   action_source=record['action_source'], policy_version=record.get('policy_version'),
                   proposed_at=record['proposed_at'], started_at=record['started_at'], completed_at=now,
                   committed_at=now, queue_seconds=0.0, execution_seconds=0.0, provenance=engine.provenance,
                   result_source='simulation', cache_hit=False, attempts=1,
                   parameters_ref=record['evaluation_id'], metrics_ref=record['evaluation_id'], reward=None,
                   reward_components=None, valid=False, all_hard_constraints_satisfied=False,
                   normalized_constraint_violation=None, env_success=None,
                   best_so_far_evaluation_id=(engine.tracker.best or {}).get('evaluation_id'),
                   best_so_far_feasible=bool(engine.tracker.feasible),
                   best_so_far_violation=(engine.tracker.best or {}).get('violation'),
                   best_so_far_metrics=(engine.tracker.best or {}).get('metrics'),
                   cumulative_evaluations_charged=max(engine.ledger.charged, record['dispatch_index']),
                   cumulative_completed=engine.ledger.completed, cumulative_launches=engine.ledger.launches,
                   in_flight_at_commit=0, after_first_feasible=engine.ledger.first_feasible is not None,
                   in_flight_at_first_feasible=False, status='interrupted', failure_type='interrupted_by_crash',
                   diagnostics='The worker process ended while this evaluation was running. It stays charged. ' + (
                               'Whether the toy backend was called is unknown; nothing physical happened.' if engine.task.mock else
                               'Its full launch allowance remains charged as unresolved, separately from confirmed '
                               'jobs. Reconcile the worker launch journals before any resume.'),
                   terminated=False, truncated=True, replay_eligible=False, duplicate_of=None)
        engine.dataset.commit(dict(evaluation_id=record['evaluation_id'], commit_seq=seq, rows=dict(evaluations=[row])))
        engine.counters['interrupted_evaluations'] += 1
        engine.counters['launches_unconfirmed_after_crash'] += record.get('launch_allowance', 1)
    if lost:
        engine.dataset.flush()
    return len(lost)
