"""Run engine: shared-budget asynchronous scheduler around the EXISTING environment,
learner and replay buffer. The SAC algorithm is untouched; this module only decides
when evaluations are dispatched, and records everything that happens.

Preparation, recovery, evaluation commitment and finalization are explicit phase
functions. This module owns dispatch, retry, learning and checkpoint ordering; the
phase functions receive this same scheduler-owned state and never run concurrently.

Single-writer rule: only this scheduler writes data tables, checkpoints and the budget
ledger. Lanes (one isolated simulation job each) only return attempt results.

Order of events for one evaluation
  reserve budget -> (stop requested? release) -> start = CHARGE + dispatch_index + fsynced
  dispatch record -> attempt(s) (a retry keeps the evaluation_id) -> result RECEIVED by the
  scheduler = completion_index -> learner receipt (replay, updates) -> first-feasibility
  decision -> durable commit (commit_seq) -> raw-output retention.

Pause / stop: stop dispatch -> wait for in-flight jobs and record them -> flush ->
consistent checkpoint -> status. Forced cancellation records unfinished evaluations as
cancelled; they stay charged because they started.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, wait as wait_for_futures
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import time
import traceback
from uuid import uuid4

from analog_optimizer.training.collect import random_proposal

from . import bayes, checkpoints as ckpt
from . import engine_commit, engine_comparison, engine_finalization, engine_preparation, engine_recovery
from .compile import compile_task
from .engine_host import HostMaintenance
from .engine_retention import Retention
from .engine_rows import CommitRows
from .layout import RunLayout, local_scratch, run_bytes
from .schema import WorkbenchConfig, task_definition_hash
from .security import redact
from .storage.atomic import JsonlAppender, PersistenceError, read_json, write_json
from .storage.dataset import utcnow
# re-exported: moved to run_lock.py by the refactoring (docs/plan-refactoring.md)
from .run_lock import iso, RunLock
# re-exported: moved to run_definitions.py by the refactoring (docs/plan-refactoring.md)
from .run_definitions import INFRASTRUCTURE_FAILURES, decode_action, learner_experiment, saves_rl_model, saves_state
# re-exported: moved to engine_host.py by the refactoring (docs/plan-refactoring.md)
from .engine_host import HOST_JOB_FOLDER, HOST_CLEANUP_CHUNK
# re-exported: moved to engine_rows.py by the refactoring (docs/plan-refactoring.md)
from .engine_rows import PROBE_AGGREGATION
# re-exported: the evaluation value is now defined beside its commit operations.
from .engine_commit import Outcome

_MAX_ERROR_CHARS = 4000


TERMINAL_STATES = ('completed', 'paused', 'stopped', 'cancelled', 'failed')
TIMING_BATCH = 16                                   # evaluations per append to logs/timings.jsonl (record 7.280)
# What the environment raises when the run's stop file reached a candidate before its first launch
# (analog_optimizer.envs. sizing): nothing was simulated, the run itself stopped it.
STOPPED_BEFORE_LAUNCH = 'Candidate stopped before nominal evaluation'


class RunEngine(HostMaintenance, CommitRows, Retention):
    """The scheduler of one run: its lanes, shared budget, learning, saving and final restoration."""
    def __init__(self, run_dir, *, task, use_processes=None, lane_factory=None, clock=time.monotonic, lock=None):
        self.layout = RunLayout(Path(run_dir))
        self.manifest = read_json(self.layout.manifest)
        self.config = WorkbenchConfig.model_validate(read_json(self.layout.effective_config))
        self.task = task
        self.run_id, self.task_id = self.manifest['run_id'], self.manifest['task_id']
        self.task_hash = task_definition_hash(self.config)
        if self.task_hash != self.manifest['task_definition_hash']:
            raise RuntimeError('effective_config.json no longer matches the task this run was created for')
        self.compiled = compile_task(self.config, task.base_graph)
        self.mode = self.manifest['mode']                    # the run's ORIGINAL mode
        self.entry = self.manifest['segments'][-1]['entry']  # 'start' | 'resume'
        self.frozen = self.mode == 'frozen'
        self.calibration_only = bool((self.manifest.get('calibration') or {}).get('random_only'))
        self.provenance = 'mock' if task.mock else 'real'
        self.use_processes = (not task.mock) if use_processes is None else use_processes
        self._lane_factory, self._clock = lane_factory, clock
        self.lock = lock or RunLock(self.layout.run_lock)
        self.stop_reason = self.requested = None
        self.forced = False
        self.error = None
        self._status_written = 0.0
        # Raw-output retention, read once per engine: the work folder does not move during a run, and
        # waveforms/index.json has no writer but this engine (_apply_retention) while it holds the run lock. A MOCK
        # evaluation re-resolved the folder three times and re-read the index every time.
        self._work_resolved = self._waveform_index = None
        self._scratch = None              # the run's simulator scratch on the local disk, when it has one (_prepare)

    # ================================================================== lifecycle
    def run(self):
        """Run this segment under the run lock and return its end state; failures in it are logged, not raised."""
        if not self.lock.held_here:
            self.lock.acquire()
        self._segment_started, self._wall_started = self._clock(), utcnow()
        self.events = JsonlAppender(self.layout.logs / 'events.jsonl')
        self.errors = JsonlAppender(self.layout.logs / 'errors.jsonl')
        self.dispatch_log = JsonlAppender(self.layout.data / '_journal' / 'dispatch.jsonl')
        self._timings = []                               # what each evaluation's stages took, for logs/timings.jsonl
        # Record 7.281 (switch run.advanced.update_after_dispatch): updates that wait until their lane has its next
        # design, and the rows of updates learned since the last commit, which go with the next one.
        self._learn_after_dispatch = bool(self.config.run.advanced.update_after_dispatch)
        self._pending_updates, self._update_rows_waiting = [], []
        # Record 7.282: the simulator host's folders of designs whose raw output this run did not keep, removed at each
        # save point and at the end, and the runner on that host (False: not looked for yet).
        self._host_folders, self._host_run = [], False
        final_state = 'failed'
        self.lanes, self.dataset = [], None
        self._preparation, self.preparation_report = None, None
        try:
            self._condition_stop_file = self.layout.control / 'stop-condition-jobs.json'
            self._condition_stop_file.unlink(missing_ok=True)
            self._write_status('starting')
            self._prepare()
            self._event('segment_started', entry=self.entry, mode=self.mode, pid=os.getpid(),
                        concurrency=len(self.lanes), budget=self.ledger.snapshot())
            self._loop()
            final_state = self._final_state()
        except PersistenceError as exc:
            self.stop_reason, self.error = 'persistence_failure', redact(str(exc), 2000)
            self._log_error('persistence_failure', exc)
        except ckpt.CheckpointIncompatible as exc:
            self.stop_reason, self.error = 'checkpoint_incompatible', redact(str(exc), _MAX_ERROR_CHARS)
            self._log_error('checkpoint_incompatible', exc, report=exc.report)
        except BaseException as exc:
            self.stop_reason = self.stop_reason or 'exception'
            self.error = redact(f'{type(exc).__name__}: {exc}', 2000)
            self._log_error('exception', exc)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                final_state = 'cancelled'
        finally:
            final_state = self._finalize(final_state)
            self.lock.release()
        return final_state

    def _final_state(self):
        if self.forced:
            return 'cancelled'
        return {'pause': 'paused', 'stop': 'stopped'}.get(self.requested,
            'completed' if self.error is None else 'failed')

    # ================================================================== preparation
    def _prepare(self):
        return engine_preparation.prepare(self, local_scratch=local_scratch)

    def _record_load_policy(self):
        return engine_preparation.record_load_policy(self)

    def _restore(self, run_state):
        return engine_recovery.restore(self, run_state)

    def _count_since(self, checkpoint_seq):
        return engine_recovery.count_since(self, checkpoint_seq)

    def _record_interrupted(self):
        return engine_recovery.record_interrupted(self)

    # ================================================================== scheduler loop
    def _loop(self):
        for name, payload in getattr(self, '_pending_events', []):
            self._event(name, **payload)
        idle_sleep = 0.002 if self.task.mock else 0.05
        self._log_virtuoso_memory('start')
        while True:
            self._poll_control()
            self._check_limits()
            if self.stop_reason is not None and not self._condition_stop_file.exists():
                write_json(self._condition_stop_file, dict(reason=self.stop_reason))
            busy = [l for l in self.lanes if self.lane_state[l.lane_id]['busy']]
            if self.checkpoint_due and not busy and self.stop_reason is None:
                self._checkpoint(self.checkpoint_kind)
            if self.stop_reason is None and not self.checkpoint_due:
                for lane in self.lanes:
                    state = self.lane_state[lane.lane_id]
                    if state['busy'] is None and not state['finished'] and self.stop_reason is None:
                        self._dispatch(lane)
            if self._pending_updates:                    # the lanes have their next designs: now learn (7.281)
                self._run_pending_updates()
            busy = [l for l in self.lanes if self.lane_state[l.lane_id]['busy']]
            if not busy:
                if self.stop_reason is None and all(s['finished'] for s in self.lane_state.values()):
                    self.stop_reason = 'budget_exhausted'
                if self.stop_reason is not None:
                    return
                continue
            if self.forced:
                self._cancel_in_flight(busy)
                return
            progressed = False
            for lane in busy:
                handle = self.lane_state[lane.lane_id]['busy']['handle']
                if handle.done():
                    progressed = True
                    self._on_attempt(lane, handle)
            if not progressed:
                self._wait_for_a_lane(busy, idle_sleep)
            self._write_status('running', throttle=1.0)

    def _wait_for_a_lane(self, busy, seconds):
        """Up to `seconds` until a busy lane's result is in, woken by it (record 7.280): the loop slept the whole 50 ms
        between looks, so a result waited 25 ms on average before the scheduler took it - and its lane with it."""
        handles = [self.lane_state[lane.lane_id]['busy']['handle'] for lane in busy]
        futures = [getattr(handle, '_future', None) or getattr(handle, 'future', None) for handle in handles]
        if futures and all(isinstance(future, Future) for future in futures):
            wait_for_futures(futures, timeout=seconds, return_when=FIRST_COMPLETED)
        else:
            time.sleep(seconds)

    def _write_timings(self):
        """logs/timings.jsonl: what each evaluation's stages took - preparation, queue wait, parameter update, netlisting,
        graph, simulation (record 7.280). The environment measured them, and they went with the per-candidate journal.
        Diagnostics: written TIMING_BATCH at a time, without an fsync of their own."""
        lines, self._timings = getattr(self, '_timings', None) or [], []
        if not lines:
            return
        try:
            with (self.layout.logs / 'timings.jsonl').open('a', encoding='utf8') as stream:
                stream.write(''.join(json.dumps(line, default=str) + '\n' for line in lines))
        except OSError as exc:
            self._log_error('timings_not_written', exc)

    def _poll_control(self):
        command = read_json(self.layout.command, default={})
        if not command or command.get('id') == getattr(self, '_last_command', None):
            return
        self._last_command = command.get('id')
        name = command.get('command')
        if name in ('pause', 'stop') and self.stop_reason is None:
            self.requested, self.stop_reason = name, f'user_{name}'
            write_json(self._condition_stop_file, dict(reason=self.stop_reason))
            self._event('control', command=name, note='dispatch stopped; waiting for in-flight jobs')
            self._write_status('pausing' if name == 'pause' else 'stopping')
        elif name == 'cancel':
            self.requested, self.stop_reason, self.forced = 'cancel', 'user_cancel', True
            write_json(self._condition_stop_file, dict(reason=self.stop_reason))
            self._event('control', command='cancel', note='forced cancellation')
        elif name == 'checkpoint' and self.stop_reason is None and saves_state(self.config):
            # "Save now": taken like a periodic save, at the next boundary with nothing in flight (dispatch waits
            # for it), then the run goes on. A run that is already stopping saves by itself.
            self.checkpoint_due, self.checkpoint_kind = True, 'manual'
            self.manual_save = dict(id=command.get('id'), state='waiting', requested_utc=command.get('issued_utc'),
                                    checkpoint_id=None, saved_utc=None, evaluations=None)
            self._event('control', command='checkpoint',
                note='save requested; taken at the next boundary with nothing in flight')
            self._write_status('running')

    def _check_limits(self):
        if self.stop_reason is not None:
            return
        run, out = self.config.run, self.config.output
        if run.max_wall_seconds is not None and self._active_seconds() >= run.max_wall_seconds:
            self.stop_reason = 'wall_time_limit'
        elif self.counters['consecutive_infrastructure_failures'] >= run.max_consecutive_infrastructure_failures:
            # A dead link, not a bad design: pause (resumable) rather than fail, and record which layer broke.
            self.requested, self.stop_reason = 'pause', 'infrastructure_failures'
            self.error = (
                f"{self.counters['consecutive_infrastructure_failures']} consecutive infrastructure failures; "
                          'paused safely. Continuing requires the connection gate to pass again.')
            self._record_connection_check()
        elif self.counters['consecutive_failures'] >= run.max_consecutive_failures:
            self.stop_reason = 'consecutive_failures'
            self.error = f'{self.counters["consecutive_failures"]} consecutive failed evaluations; stopped safely'
        elif self.dataset.failed is not None:
            raise PersistenceError(self.dataset.failed)
        else:
            free = shutil.disk_usage(self.layout.run_dir).free
            if free < out.min_free_bytes:
                self.stop_reason = 'insufficient_storage'
                self.error = f'Only {free} bytes free on the output filesystem (minimum {out.min_free_bytes})'
        if self.stop_reason is not None:
            self._event('limit_reached', reason=self.stop_reason)

    def _record_connection_check(self):
        """Record WHICH layer is broken. Observation only; never for mock runs, never a repair."""
        if self.task.mock:
            self._event('connection_check', status='not_applicable', reason='mock run: no bridge is involved')
            return
        try:
            # lazy: in the try: a failure of the import is handled with the rest
            from .connection import ConnectionMonitor
            profile = self.config.run.connection_profile_id
            result = ConnectionMonitor().check(profile, scope='interactive', trigger='run_safety')
            self._event('connection_check', overall=result['overall'],
                        layers=[dict(layer=i['layer'], state=i['state'],
                            reason_code=i['reason_code']) for i in result['layers']])
        except Exception as exc:
            self._event('connection_check', status='unavailable', error=redact(str(exc), 300))

    def segment_seconds(self):
        """Active seconds of this segment: since this worker started or resumed the run."""
        return self._clock() - self._segment_started

    def _active_seconds(self):
        return self.counters['active_seconds_before'] + self.segment_seconds()

    # ------------------------------------------------------------------ dispatch
    # Every 5th reset of a lane simulates the starting design; the others start from the lane's last valid reset (user
    # decision of 2026-09-30: the unchanged design used to be simulated at every reset, 1 evaluation in 5 of a
    # one-condition task). The drift check against the verified reference runs at every simulated reset. A MOCK run
    # simulates every reset: it costs nothing, and its data stays as it was.
    RESET_RECHECK_EVERY = 5

    def _resets_are_reused(self):
        return not self.task.mock

    def _reuse_reset(self, lane, state):
        return (self._resets_are_reused() and self.counters['baseline_done'] and state.get('reset_cache_valid')
                and lane.info.get('supports_reset_reuse') and state.get('resets_since_check',
                    0) + 1 < self.RESET_RECHECK_EVERY)

    def _dispatch_reused_reset(self, lane, state):
        (
            "A reset from the lane's last valid one: nothing is reserved, charged, launched or recorded as an "
            'evaluation.'
        )
        # no step could follow it: the lane is done, as a refused reservation says
        if self.ledger.remaining() < 1:
            state['finished'] = True
            return
        self._poll_control()
        if self.stop_reason is not None:
            return
        self.counters['episodes'] += 1
        state['episode_id'] = f'{lane.lane_id}-{self.counters["episodes"]:06d}'
        state['busy'] = dict(evaluation_id=None, op='reset_reused', phase='episode_reset_reused', attempts=[],
                             episode_id=state['episode_id'], attempt_dispatched_at=utcnow(),
                             handle=lane.submit('reset_reused', None, allowance=0,
                                 stop_file=str(self._condition_stop_file)))

    def _on_reused_reset(self, lane, busy, handle):
        state = self.lane_state[lane.lane_id]
        state['busy'] = None
        try:
            result = handle.result()
        except BaseException as exc:                 # the lane itself failed; the next (simulated) reset will say so
            result = dict(ok=False, exception=dict(type=type(exc).__name__, message=str(exc)[:_MAX_ERROR_CHARS]))
        if result.get('ok'):
            state.update(observation=result['step'][0], needs_reset=False,
                         resets_since_check=state.get('resets_since_check', 0) + 1)
            self._event('episode_reset_reused', worker_id=lane.lane_id, episode_id=busy['episode_id'],
                        reused_candidate_id=result['step'][4].get('reused_candidate_id'))
        else:                                        # nothing to reuse after all: the next reset is simulated
            state.update(reset_cache_valid=False, needs_reset=True)
            self._event('episode_reset_reused', worker_id=lane.lane_id, episode_id=busy['episode_id'], status='refused',
                        error=redact(str((result.get('exception') or {}).get('message')), 300))

    def _dispatch(self, lane):
        # the baseline is in flight: see `_commit`
        if not self._baseline_checked and self.counters['baseline_done']:
            return
        state = self.lane_state[lane.lane_id]
        if not self.calibration_only and state['needs_reset'] and self._reuse_reset(lane, state):
            return self._dispatch_reused_reset(lane, state)
        # ---- Reserve the launch allowance and honor a stop before choosing a new design.
        allowance = 1 if state['needs_reset'] and not self.calibration_only else lane.info.get('step_launches', 1)
        evaluation_id = self.ledger.reserve(launches=allowance)
        if evaluation_id is None:
            state['finished'] = True
            return
        self._poll_control()
        if self.stop_reason is not None:            # cancelled before it started: refund the reservation
            self.ledger.release(evaluation_id)
            return
        # ---- Choose the operation and proposal from calibration, reset, or search state.
        proposed_at = utcnow()
        policy_version = None
        if self.calibration_only:
            op, source, phase = 'calibration', 'random_warmup', 'warmup'
            proposal = random_proposal(self.rng, lane.info['group_ids'])
            self.counters['episodes'] += 1
            state['episode_id'] = f'{lane.lane_id}-{self.counters["episodes"]:06d}'
        elif state['needs_reset']:
            op, proposal, source = 'reset', None, 'reset'
            phase = 'episode_reset' if self.counters['baseline_done'] else 'baseline'
            self.counters['baseline_done'] = True
            self.counters['episodes'] += 1
            state['episode_id'] = f'{lane.lane_id}-{self.counters["episodes"]:06d}'
        else:
            op = 'step'
            group_ids = lane.info['group_ids']
            initial = engine_comparison.next_initial(self)          # the archive comparison's common first designs
            if initial is not None:
                proposal, source, phase = initial, engine_comparison.INITIAL_SOURCE, engine_comparison.INITIAL_PHASE
            elif self.frozen:
                deterministic = self.config.run.frozen_action == 'deterministic'
                proposal = self.learner.act([state['observation']], deterministic=deterministic)[0]
                source, phase, policy_version = (
                    'mean_policy' if deterministic else 'sampled_policy'), 'frozen_eval', self.learner.updates
            else:
                pending = sum(1 for s in self.lane_state.values() if s['busy'] and s['busy']['op'] not in ('reset',
                    'reset_reused'))
                if engine_comparison.is_search(self.config):         # T0/T+/M+: no random warm-up of their own
                    proposal = engine_comparison.propose(self, evaluation_id)
                    source, policy_version, phase = self.proposer.SOURCE, self.proposer.observations, 'search'
                elif self.replay.insertions + pending < self.config.run.advanced.warmup_transitions:
                    proposal = random_proposal(self.rng, group_ids)
                    source, phase = 'random_warmup', 'warmup'
                elif self.config.run.optimizer == 'bayes':
                    proposal = self._proposer(group_ids).propose()
                    source, policy_version, phase = bayes.Proposer.SOURCE, self.proposer.observations, 'search'
                else:
                    proposal = self.learner.act([state['observation']])[0]
                    source, policy_version = 'sac_policy', self.learner.updates
                    phase = 'adapt' if self.mode == 'fine_tune' else 'search'
        # ---- Record the charged dispatch before submitting work to the lane.
        dispatch_index = self.ledger.start(evaluation_id)
        started_at = utcnow()
        busy = dict(evaluation_id=evaluation_id, proposal_id=uuid4().hex, op=op, proposal=proposal,
                    action_source=source, phase=phase, policy_version=policy_version, proposed_at=proposed_at,
                    started_at=started_at, dispatch_index=dispatch_index, attempts=[],
                    previous=state['observation'], episode_id=state['episode_id'], launch_allowance=allowance)
        self.dispatch_log.append(dict(evaluation_id=evaluation_id, proposal_id=busy['proposal_id'],
                                      dispatch_index=dispatch_index, worker_id=lane.lane_id, phase=phase,
                                      action_source=source, policy_version=policy_version,
                                      episode_id=state['episode_id'], proposed_at=iso(proposed_at),
                                      started_at=iso(started_at), launch_allowance=allowance,
                                      worker_directory=lane.info['directory']))
        self.ledger.begin_attempt(evaluation_id)
        busy['handle'] = lane.submit(op, proposal, allowance=allowance, stop_file=str(self._condition_stop_file))
        busy['attempt_dispatched_at'] = utcnow()
        state['busy'] = busy

    # ------------------------------------------------------------------ attempt / retry
    def _on_attempt(self, lane, handle):
        state = self.lane_state[lane.lane_id]
        busy = state['busy']
        if busy['op'] == 'reset_reused':             # no evaluation: nothing to account, retry or commit
            return self._on_reused_reset(lane, busy, handle)
        try:
            result = handle.result()
        except BaseException as exc:                 # the lane itself failed (worker died, deadline exceeded)
            result = dict(op=busy['op'], ok=False, step=None, record=None, records=[], launches=0,
                          started_at=iso(busy['attempt_dispatched_at']), ended_at=iso(),
                          exception=dict(type=type(exc).__name__, message=str(exc)[:_MAX_ERROR_CHARS]),
                          lane_failure=True,
                          episode=None, episode_step=None)
        if (self.stop_reason is not None and not result['ok'] and not result.get('launches')
                and (result.get('exception') or {}).get('message') == STOPPED_BEFORE_LAUNCH):
            # Dispatched just before the run stopped, stopped by it before any launch: recorded as cancelled, like a
            # forced cancel, not as an infrastructure failure - one more "failure" of the link that never happened.
            result['cancelled'] = True
        # ---- Account for uncertain launches before deciding whether another attempt is allowed.
        if result.get('lane_failure') and not self.task.mock:
            result['launches'] = busy['launch_allowance']         # conservative: the physical launch state is unknown
            result['launch_unknown'] = True
            uncertain = busy['launch_allowance']
        elif result.get('lane_failure'):
            uncertain = 0                                          # the toy backend launched nothing
        else:
            uncertain = sum(job.get('uncertain_calls', 0) for job in (result.get('record') or {}).get('jobs', []))
        self.ledger.end_attempt(busy['evaluation_id'], launches=int(result['launches']), uncertain=uncertain)
        if uncertain:
            self.stop_reason = 'unresolved_launch_intent'
            self.error = 'Physical launch state is unresolved; automatic continuation is blocked pending reconciliation'
            write_json(self._condition_stop_file, dict(reason=self.stop_reason))
        result['dispatched_at'] = iso(busy['attempt_dispatched_at'])
        busy['attempts'].append(result)
        record = result.get('record') or {}
        retryable = (result['ok'] and result['step'][3] and record.get('retryable') is True
                     and record.get('status') in INFRASTRUCTURE_FAILURES and lane.info.get('supports_retry'))
        if retryable and self.stop_reason is None and not self.forced and self.ledger.may_retry(busy['evaluation_id']):
            self.ledger.begin_attempt(busy['evaluation_id'])
            busy['retry_reason'] = f"retryable {record.get('status')}: {record.get('reason_code')}"
            busy['handle'] = lane.submit('retry', allowance=busy['launch_allowance'],
                stop_file=str(self._condition_stop_file))
            busy['attempt_dispatched_at'] = utcnow()
            return
        state['busy'] = None
        self._commit(lane, busy, result)

    def _cancel_in_flight(self, busy_lanes):
        """Forced cancellation: unfinished evaluations are recorded as cancelled and stay charged."""
        for lane in busy_lanes:
            state = self.lane_state[lane.lane_id]
            busy = state['busy']
            if busy['handle'].done():
                self._on_attempt(lane, busy['handle'])
                continue
            # it launches nothing and charges nothing: there is nothing to record
            if busy['op'] == 'reset_reused':
                state['busy'] = None
                continue
            unknown = 0 if self.task.mock else busy['launch_allowance']     # only a real launch can be left unresolved
            self.ledger.end_attempt(busy['evaluation_id'], launches=unknown, uncertain=unknown)
            result = dict(op=busy['op'], ok=False, step=None, record=None, records=[], launches=unknown, cancelled=True,
                          started_at=iso(busy['attempt_dispatched_at']), ended_at=iso(),
                          dispatched_at=iso(busy['attempt_dispatched_at']), launch_unknown=not self.task.mock,
                          exception=dict(type='Cancelled', message='Forced cancellation while the job was running; '
                                                                   'the remote job state is unknown'),
                          episode=None, episode_step=None)
            busy['attempts'].append(result)
            state['busy'] = None
            self._commit(lane, busy, result)

    # ------------------------------------------------------------------ commit (learner receipt)
    def _commit(self, lane, busy, result):
        return engine_commit.commit(self, lane, busy, result, timing_batch=TIMING_BATCH)

    def _outcome(self, record, result, observation, truncated):
        return engine_commit.outcome(self, record, result, observation, truncated)

    def _first_feasibility(self, busy, evaluation_id, commit_seq, nominal_feasible, feasible):
        return engine_commit.first_feasibility(self, busy, evaluation_id, commit_seq, nominal_feasible, feasible)

    def _offer(self, busy, record, info, observation, reward, commit_seq, outcome):
        return engine_commit.offer(self, busy, record, info, observation, reward, commit_seq, outcome)

    def _run_created(self):
        return datetime.fromisoformat(self.manifest['created_utc'])

    def _updates_due(self):
        adv = self.config.run.advanced
        # another method proposes: the network is neither asked nor trained
        if self.config.run.optimizer != 'sac':
            return False
        return len(self.replay) >= adv.batch_size and not self.replay.insertions % adv.update_every

    def _proposer(self, group_ids):
        if self.proposer is None:
            self.proposer = bayes.Proposer(group_ids, seed=self.config.run.seed,
                warmup=self.config.run.advanced.warmup_transitions)
            self._event('bayes_started', variables=len(self.proposer.group_ids),
                        initial_designs=self.proposer.search.n_init,
                        candidates=self.proposer.search.n_candidates,
                        failure_tolerance=self.proposer.search.failure_tolerance)
        return self.proposer

    def _maybe_update(self, commit_seq):
        return self._run_updates(commit_seq) if self._updates_due() else []

    def _defer_updates(self):
        """Whether a result's updates wait until the lanes have their next designs (record 7.281, switch
        run.advanced.update_after_dispatch): only while budget is left and the run is not stopping - then an evaluation
        dispatched after them is sure to commit later and carry their rows. A lane already at work is not enough: its
        result may commit in the same pass, before the waiting updates have run."""
        return (self._learn_after_dispatch and self.stop_reason is None and not self.forced
                and self.ledger.remaining() > 0)

    def _run_pending_updates(self):
        """The updates of results whose lanes got their next designs first (record 7.281). Their rows go with the next
        commit; a save point runs them first, so it holds all that was learned."""
        pending, self._pending_updates = getattr(self, '_pending_updates', None) or [], []
        for commit_seq in pending:
            self._update_rows_waiting += self._run_updates(commit_seq)

    def _persist_waiting_rows(self):
        """The rows of updates learned since the last commit, when no later commit is sure to carry them: before a save
        point and at the end (record 7.283; Astra's review of 7.281: a pause right after them, or the save point itself,
        counted the updates but kept no row). Written as a rows-only record at the last commit's number
        (RawDataset.record_rows), so the save point's data cursor covers them. Nothing is lost silently: without a
        working dataset the old event says so."""
        rows, self._update_rows_waiting = getattr(self, '_update_rows_waiting', None) or [], []
        if not rows:
            return
        if self.dataset is not None and self.dataset.failed is None:
            self.dataset.record_rows('learner_updates', rows, origin='learner_updates_after_commit')
        else:
            self._event('learner_update_rows_unrecorded', count=len(rows),
                        note='the learner state and its save points hold these updates; only their rows are missing')

    def _run_updates(self, commit_seq):
        adv, rows = self.config.run.advanced, []
        every = self.config.output.learner_update_log_every
        for _ in range(adv.updates_per_transition):
            if self.freeze is not None:
                self.freeze.apply()
            started = self._clock()
            update = self.replay.update_learner(self.rehearsal or self.learner,
                self.rehearsal.online_size if self.rehearsal else adv.batch_size)   # lent, not copied (7.221)
            if update['updates'] % every == 0:
                rows.append(dict(run_id=self.run_id, update_id=f"{self.run_id}:u{update['updates']:09d}",
                                 updated_at=iso(), evaluations_collected=commit_seq,
                                 actor_loss=update['actor_loss'], critic_loss=update['critic_loss'],
                                 alpha_loss=update['alpha_loss'], alpha=update['alpha'],
                                 mean_log_prob=update['mean_log_prob'], target_mean=update['target_mean'],
                                 critic_grad_norm=update['critic_grad_norm'], actor_grad_norm=update['actor_grad_norm'],
                                 learning_rate=adv.learning_rate, replay_size=len(self.replay),
                                 batch_size=adv.batch_size, cumulative_updates=update['updates'],
                                 policy_version=update['updates'], update_seconds=self._clock() - started))
        return rows

    # ------------------------------------------------------------------ checkpoint
    def _collector_state(self):
        result = dict(rng_state=self.rng.getstate(), best_design=self.tracker.state_dict(),
                      previous_best_waveform=self.previous_best_waveform)
        if self.rehearsal is not None:
            result['rehearsal'] = self.rehearsal.state_dict()
        search = engine_comparison.state(self)                     # the archive comparison's search (T0/T+/M+)
        if search is not None:
            result['comparison'] = search
        return result

    def _checkpoint(self, kind):
        self._run_pending_updates()                      # the save point holds every update so far (7.281)
        self._persist_waiting_rows()                     # and its data cursor covers their rows (7.283)
        self._clean_host()                               # the lanes are idle: the host's dropped job folders go (7.282)
        if not saves_state(self.config):
            self.checkpoint_due = False
            return None
        self.dataset.flush()
        counters = dict(self.counters, active_seconds_before=self._active_seconds(),
                        evaluations_committed=self.dataset.last_seq,
                        learner_updates=int(getattr(self.learner, 'updates', 0)),
                        replay_size=0 if self.replay is None else len(self.replay),
                        replay_insertions=0 if self.replay is None else self.replay.insertions)
        counters['last_checkpoint_commit'] = self.dataset.last_seq
        if self.frozen and ckpt.weight_digest(self.learner) != self.frozen_digest:
            raise RuntimeError('Frozen mode changed model weights')
        metadata = self.checkpoints.save(
            self.learner, self.replay, ledger_state=self.ledger.state_dict(), data_cursor=self.dataset.cursor(),
            counters=counters, collector_state=self._collector_state(), mode=self.mode, kind=kind,
            effective_experiment=self.experiment, frozen=self.frozen)
        self.dataset.compact_journal()
        self.counters['last_checkpoint_commit'] = self.dataset.last_seq
        self.last_checkpoint_time, self.checkpoint_due, self.checkpoint_kind = self._clock(), False, 'periodic'
        self.last_checkpoint = metadata
        self._event('checkpoint_saved', checkpoint_id=metadata['checkpoint_id'], kind=kind,
                    capability=metadata['restoration_capability'], commit_seq=self.dataset.last_seq)
        if self.manual_save and self.manual_save['state'] == 'waiting':
            # ANY save written after the request holds what the user asked to keep (a pause that overtook it, too).
            self.manual_save = dict(self.manual_save, state='saved', checkpoint_id=metadata['checkpoint_id'],
                                    saved_utc=metadata['created_utc'], evaluations=self.ledger.completed)
            if self.stop_reason is None:                # a run on its way down writes its final status right after
                self._write_status('running')
        return metadata

    def _relabel_unchanged(self, kind):
        """A run that completes right after a periodic save (its budget a multiple of the checkpoint interval) would
        write the very same state a second time, replay buffer and all. That save becomes the final one instead. Only
        for 'final' and only when nothing moved since: the same commit, learner updates and replay insertions."""
        last = getattr(self, 'last_checkpoint', None)
        if (kind != 'final' or last is None or last.get('kind') != 'periodic' or not saves_state(self.config)
                or (self.manual_save and self.manual_save['state'] == 'waiting')):
            return None
        counters = last['counters']
        if (last['data_cursor']['commit_seq'] != self.dataset.last_seq
                or counters['learner_updates'] != int(getattr(self.learner, 'updates', 0))
                or counters['replay_insertions'] != (0 if self.replay is None else self.replay.insertions)):
            return None
        metadata = self.checkpoints.relabel(last['checkpoint_id'], kind, was=last['kind'])
        self.last_checkpoint = metadata
        self._event('checkpoint_saved', checkpoint_id=metadata['checkpoint_id'], kind=kind,
                    relabelled_from=last['kind'],
                    capability=metadata['restoration_capability'], commit_seq=self.dataset.last_seq)
        return metadata

    # ------------------------------------------------------------------ finalize
    def _clear_scratch(self):
        return engine_finalization.clear_scratch(self)

    def _finalize(self, final_state):
        return engine_finalization.finalize(self, final_state)

    def _adopt_baseline(self):
        return engine_finalization.adopt_baseline(self)

    def _calibrate(self):
        return engine_finalization.calibrate(self)

    def _write_outputs(self, final_state, checkpoint, persistence_ok):
        return engine_finalization.write_outputs(self, final_state, checkpoint, persistence_ok)

    # ------------------------------------------------------------------ status / logs
    def _event(self, name, **fields):
        self.events.append(dict(time_utc=iso(), event=name, run_id=self.run_id, **fields))

    def _log_error(self, name, exc, **fields):
        self.errors.append(dict(time_utc=iso(), error=name, run_id=self.run_id,
                                type=None if exc is None else type(exc).__name__,
                                message=None if exc is None else redact(str(exc), _MAX_ERROR_CHARS),
                                traceback=None if exc is None else redact(traceback.format_exc(), 8000), **fields))

    def _write_status(self, state, throttle=0.0):
        now = time.monotonic()
        if throttle and now - self._status_written < throttle:
            return
        self._status_written = now
        ledger = getattr(self, 'ledger', None)
        tracker = getattr(self, 'tracker', None)
        best = tracker.best if tracker else None
        dataset = getattr(self, 'dataset', None)
        write_json(self.layout.status, dict(
            state=state, run_id=self.run_id, mode=self.mode, entry=self.entry, provenance=self.provenance,
            mock=self.task.mock, pid=os.getpid(), host=socket.gethostname(), heartbeat_utc=iso(),
            stop_reason=self.stop_reason, error=self.error,
            budget=None if ledger is None else ledger.snapshot(),
            active_workers=[dict(worker_id=k, evaluation_id=v['busy']['evaluation_id'], phase=v['busy']['phase'],
                                 attempt=len(v['busy']['attempts']) + 1)
                            for k, v in getattr(self, 'lane_state', {}).items() if v['busy']],
            concurrency=len(getattr(self, 'lanes', [])),
            learner_updates=int(getattr(self.learner, 'updates', 0)) if hasattr(self, 'learner') else 0,
            first_feasible=None if ledger is None else ledger.first_feasible,
            last_successful_evaluation_utc=(getattr(self, 'counters', {}) or {}).get('last_successful_evaluation_utc'),
            infrastructure_failures=(getattr(self, 'counters', {}) or {}).get('infrastructure_failures', 0),
            connection_profile_id=self.config.run.connection_profile_id,
            best_design=best,
            persistence=None if dataset is None else dataset.status(),
            last_checkpoint_utc=(None if not getattr(self, 'checkpoints', None) or not self.checkpoints.last_saved_at
                                 else iso(self.checkpoints.last_saved_at)),
            manual_save=getattr(self, 'manual_save', None),
            paths=self.layout.subpaths(), bytes_written=run_bytes(self.layout) if state in TERMINAL_STATES else None,
            active_seconds=self._active_seconds() if hasattr(self, 'counters') else 0.0))
