"""Run engine: shared-budget asynchronous scheduler around the EXISTING environment,
learner and replay buffer. The SAC algorithm is untouched; this module only decides
when evaluations are dispatched, and records everything that happens.

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
import random
import shutil
import socket
import time
import traceback
from typing import NamedTuple
from uuid import uuid4

from . import best_design, checkpoints as ckpt, modes
from .budget import BudgetLedger
from .compile import compile_task, hard_constraints
from .connection import classify_infrastructure_failure
from .engine_host import HostMaintenance
from .engine_retention import Retention
from .engine_rows import CommitRows
from .lanes import ScratchLinked, open_lanes, unlink_scratch
from .layout import RunLayout, build_artifact_manifest, local_scratch, run_bytes
from .pdk import run_vocabulary
from .schema import WorkbenchConfig, task_definition_hash
from .security import redact
from .storage.atomic import JsonlAppender, PersistenceError, read_json, read_jsonl, write_json
from .storage.dataset import DatasetReader, RawDataset, utcnow
from .summary import build_run_summary
from .trajectory import StateEncoder, TrajectoryLoader
# re-exported: moved to run_lock.py by the refactoring (docs/plan-refactoring.md)
from .run_lock import iso, RunLock
# re-exported: moved to run_definitions.py by the refactoring (docs/plan-refactoring.md)
from .run_definitions import INFRASTRUCTURE_FAILURES, decode_action, learner_experiment
# re-exported: moved to engine_host.py by the refactoring (docs/plan-refactoring.md)
from .engine_host import HOST_JOB_FOLDER, HOST_CLEANUP_CHUNK
# re-exported: moved to engine_rows.py by the refactoring (docs/plan-refactoring.md)
from .engine_rows import PROBE_AGGREGATION

TERMINAL_STATES = ('completed', 'paused', 'stopped', 'cancelled', 'failed')
TIMING_BATCH = 16                                   # evaluations per append to logs/timings.jsonl (record 7.280)
# What the environment raises when the run's stop file reached a candidate before its first launch (analog_optimizer.envs.
# sizing): nothing was simulated, the run itself stopped it.
STOPPED_BEFORE_LAUNCH = 'Candidate stopped before nominal evaluation'


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


class RunEngine(HostMaintenance, CommitRows, Retention):
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
        self.lock = lock or RunLock(self.layout.control / 'run.lock')
        self.stop_reason = self.requested = None
        self.forced = False
        self.error = None
        self._status_written = 0.0
        # Raw-output retention, read once per engine: the work folder does not move during a run, and waveforms/index.json
        # has no writer but this engine (_apply_retention) while it holds the run lock. A MOCK evaluation re-resolved the
        # folder three times and re-read the index every time.
        self._work_resolved = self._waveform_index = None
        self._scratch = None              # the run's simulator scratch on the local disk, when it has one (_prepare)

    # ================================================================== lifecycle
    def run(self):
        if not self.lock.held_here:
            self.lock.acquire()
        self._segment_started, self._wall_started = self._clock(), utcnow()
        self.events = JsonlAppender(self.layout.logs / 'events.jsonl')
        self.errors = JsonlAppender(self.layout.logs / 'errors.jsonl')
        self.dispatch_log = JsonlAppender(self.layout.data / '_journal' / 'dispatch.jsonl')
        self._timings = []                               # what each evaluation's stages took, for logs/timings.jsonl
        # Record 7.281 (switch run.advanced.update_after_dispatch): updates that wait until their lane has its next design,
        # and the rows of updates learned since the last commit, which go with the next one.
        self._learn_after_dispatch = bool(self.config.run.advanced.update_after_dispatch)
        self._pending_updates, self._update_rows_waiting = [], []
        # Record 7.282: the simulator host's folders of designs whose raw output this run did not keep, removed at each save
        # point and at the end, and the runner on that host (False: not looked for yet).
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
            self.stop_reason, self.error = 'checkpoint_incompatible', redact(str(exc), 4000)
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
        return {'pause': 'paused', 'stop': 'stopped'}.get(self.requested, 'completed' if self.error is None else 'failed')

    # ================================================================== preparation
    def _prepare(self):
        cfg, out, adv = self.config, self.config.output, self.config.run.advanced
        enabled = {'evaluations', 'parameters', 'metrics', 'simulator_jobs'}
        if out.save_learner_updates and not self.frozen:
            enabled.add('learner_updates')
        if out.save_transition_archive:
            enabled |= {'transitions', 'states'}
        self.dataset = RawDataset(self.layout.data, enabled_tables=enabled, flush_every=out.flush_every_evaluations)
        self.archive = out.save_transition_archive
        experiment = learner_experiment(cfg, self.task, self.task_hash)
        self.experiment = experiment
        self.vocabulary = run_vocabulary(self.layout.run_dir)      # the run's own component list; None = standard
        input_options = modes.runtime_options(cfg, self.vocabulary)
        source_dir = source_meta = None
        if self.entry == 'resume':
            source_dir = ckpt.resolve_checkpoint(self.layout.run_dir, 'latest')
            source_meta = ckpt.read_metadata(source_dir)
        elif self.mode in ('fine_tune', 'frozen'):
            parent = self.manifest['parent']
            source_dir = ckpt.resolve_checkpoint(parent['run_dir'], parent['checkpoint_id'])
            source_meta = ckpt.read_metadata(source_dir)
        built = modes.build('resume' if self.entry == 'resume' else self.mode, experiment=experiment,
                            model_config=modes.model_config_from(cfg.run.network),
                            sac_config=modes.sac_config_from(adv), spec_schema=self.compiled.spec_schema,
                            advanced=adv, seed=cfg.run.seed, origin=self.task.origin, source_dir=source_dir,
                            source_metadata=source_meta, task_definition_hash=self.task_hash, vocabulary=self.vocabulary,
                            runtime=input_options)
        self.learner, self.replay, self.freeze = built['learner'], built['replay'], built['freeze']
        self.load_policy = built['policy']
        self.rehearsal = None
        if cfg.run.rehearsal is not None:
            from .rehearsal import Rehearsal  # lazy: rehearsal imports torch
            self.rehearsal = Rehearsal(cfg.run.rehearsal, self.learner, origin=self.task.origin,
                                       seed=cfg.run.seed, batch_size=adv.batch_size)
        if self.frozen:
            for module in (self.learner.actor, self.learner.critics, self.learner.targets):
                module.requires_grad_(False).eval()
            self.replay = None
        if self.entry == 'start' and self.mode == 'fine_tune' and adv.freeze_encoder and self.freeze is None:
            self.freeze = modes.EncoderFreeze(self.learner)
        if self.entry == 'resume' and self.mode == 'fine_tune' and adv.freeze_encoder:
            self.freeze = modes.EncoderFreeze(self.learner)
        self.frozen_digest = ckpt.weight_digest(self.learner) if self.frozen else None
        run = cfg.run
        self.ledger = BudgetLedger(run.max_evaluations, max_launches=run.max_spectre_launches,
                                   max_retries=run.max_retries)
        self.rng = random.Random(run.seed)
        self.tracker = best_design.BestDesignTracker(self.compiled.preference)
        self.counters = dict(global_env_step=0, completion_index=0, episodes=0, baseline_done=False,
                             consecutive_failures=0, consecutive_infrastructure_failures=0,
                             infrastructure_failures=0, last_successful_evaluation_utc=None,
                             active_seconds_before=0.0, sum_job_runtime_seconds=0.0,
                             failures=0, retries=0, last_checkpoint_commit=0, launches_unconfirmed_after_crash=0,
                             interrupted_evaluations=0, feasible_evaluations=0, valid_evaluations=0)
        self.previous_best_waveform = None
        # A baseline run asked to calibrate (record 7.197): until its baseline evaluation is committed and valid, no other
        # lane starts and no random design is drawn (`_dispatch`, `_commit`). Any other run never waits.
        self._baseline_checked = self.calibration_only or not self.manifest.get('calibration') or self.entry == 'resume'
        self.encoder = None
        if self.archive:
            self.encoder = StateEncoder(self.layout.data / 'states' / 'static', task_id=self.task_id,
                                        graph=self.compiled.graph, specs=self.compiled.specs,
                                        feature_schema_version=input_options['feature_schema'].version,
                                        spec_schema_version=self.compiled.spec_schema.version)
        if self.entry == 'resume':
            self._restore(built['run_state'])
        if self.ledger.uncertain_launches:
            write_json(self._condition_stop_file, dict(reason='unresolved_launch_intent'))
            raise RuntimeError('Unresolved physical launch intents/leases must be reconciled before resume; no lanes opened')
        self.checkpoints = ckpt.CheckpointStore(self.layout.run_dir, run_id=self.run_id, task_id=self.task_id,
                                                task_definition_hash=self.task_hash,
                                                save_replay=out.save_replay_snapshots, keep_last=out.keep_last_checkpoints)
        self._record_load_policy()
        count = min(run.concurrency, self.task.max_concurrency)
        env_run = run.model_copy(deep=True)
        factory = self._lane_factory or self.task.env_factory_builder(self.compiled, self.layout.work, env_run)
        circuit = getattr(factory, 'profile', None) or getattr(getattr(factory, 'inner', None), 'profile', None)
        if getattr(circuit, 'model_library_event', None) is not None:    # which parts of the model file the decks load
            self._event('model_library', **circuit.model_library_event)
        from analog_optimizer.training.workers import WorkerLimits
        # A real (native) factory needs ONE owner of the Virtuoso session, alive from before the first lane opens until
        # after the last one closed: the optimizer's preparation service. Entered here exactly as its own training loop
        # does (training/parallel.py); without it a real lane cannot even connect. Closed in _finalize, after the lanes.
        prepare_context = getattr(factory, 'preparation_context', None)
        if callable(prepare_context):
            from contextlib import ExitStack
            self.preparation_report = {}
            self._preparation = ExitStack()
            factory = self._preparation.enter_context(prepare_context(WorkerLimits(), self.preparation_report))
            self._event('preparation_service_started', session=(self.preparation_report.get('preparation') or {}).get('session_dir'))
        limits = WorkerLimits(operation_seconds=max(300., (1 + len(run.conditions.corners)) * adv.simulation_timeout_seconds + 180.))
        self._scratch = local_scratch(self.layout)
        if self._scratch is not None:                    # wrapped last: it keeps the preparation service's factory as is
            factory = ScratchLinked(factory, self._scratch)
            self._event('simulator_scratch', path=str(self._scratch),
                        note='export packages and per-job folders on the local disk; kept job folders move to the run folder')
        self.lanes = open_lanes(factory, count, use_processes=self.use_processes, limits=limits)
        self.lane_state = {lane.lane_id: dict(observation=None, needs_reset=True, busy=None, finished=False,
                                              episode_id=None, reset_cache_valid=False, resets_since_check=0)
                           for lane in self.lanes}
        for lane in self.lanes:
            if lane.info['origin'] != self.task.origin:
                raise RuntimeError('Lane origin differs from the task origin')
        self.last_checkpoint_time = self._clock()
        self.checkpoint_due = False
        # "Save now" (command `checkpoint`): the next due save is of kind `manual`, and the request is answered in
        # status.json so that the page knows when ITS request has been written.
        self.checkpoint_kind, self.manual_save = 'periodic', None

    def _record_load_policy(self):
        segment = self.manifest['segments'][-1]
        segment.update(load_policy=self.load_policy, started_utc=iso(self._wall_started), pid=os.getpid(),
                       host=socket.gethostname(), lanes='process' if self.use_processes else 'thread')
        write_json(self.layout.manifest, self.manifest)

    def _restore(self, run_state):
        """resume keeps counters. Durable tables are the source of truth for cost after a crash."""
        if not run_state or run_state.get('version') != 'workbench-run-state-v1':
            raise RuntimeError('The checkpoint carries no workbench run state; it cannot continue this run')
        if run_state['run_id'] != self.run_id or run_state['task_definition_hash'] != self.task_hash:
            raise RuntimeError('Checkpoint belongs to another run or task')
        self.ledger.load_state(run_state['ledger'])
        self.counters.update(run_state['counters'])
        collector = run_state['collector']
        self.rng.setstate(collector['rng_state'])
        self.tracker = best_design.BestDesignTracker(self.compiled.preference, collector.get('best_design'))
        self.previous_best_waveform = collector.get('previous_best_waveform')
        if self.rehearsal is not None:
            if 'rehearsal' not in collector:
                raise RuntimeError('Checkpoint lacks rehearsal sampler state')
            self.rehearsal.load_state_dict(collector['rehearsal'])
        cursor = run_state['data_cursor']
        report = dict(checkpoint_commit_seq=cursor['commit_seq'], recovery=self.dataset.recovery)
        # The best design is also written on every improvement (best_design/tracker_state.json), which reaches further
        # than the last checkpoint. Without it a crash after the only feasible evaluation resumed with an empty tracker,
        # finalized as "no feasible design" and DELETED parameters.csv / optimized_dut.scs of a design its own
        # evaluations table still held (review of 2026-09-23).
        later = read_json(self.layout.best_design / 'tracker_state.json', default=None)
        if later and (later.get('last_commit_seq') or 0) > cursor['commit_seq']:
            self.tracker = best_design.BestDesignTracker(self.compiled.preference, later)
            report['best_design_after_checkpoint'] = later['last_commit_seq']
        self.dataset.flush()
        interrupted = self._record_interrupted()
        post = self.dataset.last_seq - cursor['commit_seq']
        if post or interrupted:
            reader = DatasetReader(self.layout.data)
            evaluations = reader.rows('evaluations', ['evaluation_id', 'status', 'cache_hit', 'attempts', 'valid'])
            jobs = reader.rows('simulator_jobs', ['launch_counted', 'invocation_confirmed'])
            unresolved = read_json(self.layout.data / '_journal' / 'unresolved-launch-leases.json', default={})
            unknown = sum(item['allowance'] for item in unresolved.values())
            report['reconciled'] = self.ledger.reconcile(
                charged=len(evaluations), completed=len(evaluations),
                failed=sum(1 for e in evaluations if not e['valid']),
                launches=sum(1 for j in jobs if j['launch_counted']) + unknown,
                uncertain=sum(1 for j in jobs if j['launch_counted'] and j['invocation_confirmed'] is None) + unknown,
                retries=sum(max(0, e['attempts'] - 1) for e in evaluations),
                cache_hits=sum(1 for e in evaluations if e['cache_hit']))
            self.counters['completion_index'] = max(self.counters['completion_index'], len(evaluations))
            report['post_checkpoint_evaluations'] = post
            if post and not self.frozen and self.replay is not None and self.archive:
                readmitted = 0
                loader = TrajectoryLoader(self.layout.run_dir)
                rows = {r['candidate_id']: r for r in loader.transition_rows()}
                for transition in loader.transitions():
                    row = rows[transition.candidate_id]
                    if row['commit_seq'] > cursor['commit_seq'] and row['replay_admitted']:
                        self.replay.add(transition)
                        readmitted += 1
                report['readmitted_transitions'] = readmitted
                report['note'] = ('Learner weights are those of the checkpoint. Experience committed after it was '
                                  're-admitted to replay; the learner updates made after it are not recoverable.')
        if self.encoder is not None:
            self.encoder.written = {r['state_id'] for r in DatasetReader(self.layout.data).rows('states', ['state_id'])}
        # A pause for infrastructure failures asks for the connection gate to pass again, and a resume passes it: the count
        # starts over. Restored as saved it was still at the limit, so every Resume paused again at once, nothing evaluated
        # (review of 2026-10-01).
        self.counters['consecutive_infrastructure_failures'] = 0
        self._pending_events = [('resumed', report)]

    def _record_interrupted(self):
        """Evaluations that STARTED (budget charged) but were never committed because the process died."""
        started = {r['evaluation_id']: r for r in read_jsonl(self.layout.data / '_journal' / 'dispatch.jsonl')}
        lost = [r for key, r in started.items() if not self.dataset.has(key)]
        lease_path = self.layout.data / '_journal' / 'unresolved-launch-leases.json'
        leases = read_json(lease_path, default={})
        for record in sorted(lost, key=lambda r: r['dispatch_index']):
            if not self.task.mock:
                # A real dispatch without a coordinator receipt cannot release its allocation: an unknown lease,
                # not a fabricated simulator job or confirmed call. The toy backend launches nothing: no lease.
                leases[record['evaluation_id']] = dict(allowance=record.get('launch_allowance', 1),
                                                      dispatch=record, state='unresolved')
                write_json(lease_path, leases)
            seq, now = self.dataset.next_seq(), iso()
            self.counters['completion_index'] += 1
            row = dict(run_id=self.run_id, evaluation_id=record['evaluation_id'], task_id=self.task_id,
                       proposal_id=record['proposal_id'], worker_id=record['worker_id'],
                       episode_id=record.get('episode_id') or 'unknown', episode_step=record.get('episode_step', 0),
                       global_env_step=self.counters['global_env_step'], dispatch_index=record['dispatch_index'],
                       completion_index=self.counters['completion_index'], commit_seq=seq, phase=record['phase'],
                       action_source=record['action_source'], policy_version=record.get('policy_version'),
                       proposed_at=record['proposed_at'], started_at=record['started_at'], completed_at=now,
                       committed_at=now, queue_seconds=0.0, execution_seconds=0.0, provenance=self.provenance,
                       result_source='simulation', cache_hit=False, attempts=1,
                       parameters_ref=record['evaluation_id'], metrics_ref=record['evaluation_id'], reward=None,
                       reward_components=None, valid=False, all_hard_constraints_satisfied=False,
                       normalized_constraint_violation=None, env_success=None,
                       best_so_far_evaluation_id=(self.tracker.best or {}).get('evaluation_id'),
                       best_so_far_feasible=bool(self.tracker.feasible),
                       best_so_far_violation=(self.tracker.best or {}).get('violation'),
                       best_so_far_metrics=(self.tracker.best or {}).get('metrics'),
                       cumulative_evaluations_charged=max(self.ledger.charged, record['dispatch_index']),
                       cumulative_completed=self.ledger.completed, cumulative_launches=self.ledger.launches,
                       in_flight_at_commit=0, after_first_feasible=self.ledger.first_feasible is not None,
                       in_flight_at_first_feasible=False, status='interrupted', failure_type='interrupted_by_crash',
                       diagnostics='The worker process ended while this evaluation was running. It stays charged. ' + (
                                   'Whether the toy backend was called is unknown; nothing physical happened.' if self.task.mock else
                                   'Its full launch allowance remains charged as unresolved, separately from confirmed '
                                   'jobs. Reconcile the worker launch journals before any resume.'),
                       terminated=False, truncated=True, replay_eligible=False, duplicate_of=None)
            self.dataset.commit(dict(evaluation_id=record['evaluation_id'], commit_seq=seq, rows=dict(evaluations=[row])))
            self.counters['interrupted_evaluations'] += 1
            self.counters['launches_unconfirmed_after_crash'] += record.get('launch_allowance', 1)
        if lost:
            self.dataset.flush()
        return len(lost)

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
        command = read_json(self.layout.control / 'command.json', default={})
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
        elif name == 'checkpoint' and self.stop_reason is None and self.config.output.save_checkpoints:
            # "Save now": taken like a periodic save, at the next boundary with nothing in flight (dispatch waits
            # for it), then the run goes on. A run that is already stopping saves by itself.
            self.checkpoint_due, self.checkpoint_kind = True, 'manual'
            self.manual_save = dict(id=command.get('id'), state='waiting', requested_utc=command.get('issued_utc'),
                                    checkpoint_id=None, saved_utc=None, evaluations=None)
            self._event('control', command='checkpoint', note='save requested; taken at the next boundary with nothing in flight')
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
            self.error = (f"{self.counters['consecutive_infrastructure_failures']} consecutive infrastructure failures; "
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
                        layers=[dict(layer=i['layer'], state=i['state'], reason_code=i['reason_code']) for i in result['layers']])
        except Exception as exc:
            self._event('connection_check', status='unavailable', error=redact(str(exc), 300))

    def _active_seconds(self):
        return self.counters['active_seconds_before'] + (self._clock() - self._segment_started)

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
                and lane.info.get('supports_reset_reuse') and state.get('resets_since_check', 0) + 1 < self.RESET_RECHECK_EVERY)

    def _dispatch_reused_reset(self, lane, state):
        """A reset from the lane's last valid one: nothing is reserved, charged, launched or recorded as an evaluation."""
        if self.ledger.remaining() < 1:              # no step could follow it: the lane is done, as a refused reservation says
            state['finished'] = True
            return
        self._poll_control()
        if self.stop_reason is not None:
            return
        self.counters['episodes'] += 1
        state['episode_id'] = f'{lane.lane_id}-{self.counters["episodes"]:06d}'
        state['busy'] = dict(evaluation_id=None, op='reset_reused', phase='episode_reset_reused', attempts=[],
                             episode_id=state['episode_id'], attempt_dispatched_at=utcnow(),
                             handle=lane.submit('reset_reused', None, allowance=0, stop_file=str(self._condition_stop_file)))

    def _on_reused_reset(self, lane, busy, handle):
        state = self.lane_state[lane.lane_id]
        state['busy'] = None
        try:
            result = handle.result()
        except BaseException as exc:                 # the lane itself failed; the next (simulated) reset will say so
            result = dict(ok=False, exception=dict(type=type(exc).__name__, message=str(exc)[:4000]))
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
        if not self._baseline_checked and self.counters['baseline_done']:      # the baseline is in flight: see `_commit`
            return
        state = self.lane_state[lane.lane_id]
        if not self.calibration_only and state['needs_reset'] and self._reuse_reset(lane, state):
            return self._dispatch_reused_reset(lane, state)
        allowance = 1 if state['needs_reset'] and not self.calibration_only else lane.info.get('step_launches', 1)
        evaluation_id = self.ledger.reserve(launches=allowance)
        if evaluation_id is None:
            state['finished'] = True
            return
        self._poll_control()
        if self.stop_reason is not None:            # cancelled before it started: refund the reservation
            self.ledger.release(evaluation_id)
            return
        proposed_at = utcnow()
        policy_version = None
        if self.calibration_only:
            op, source, phase = 'calibration', 'random_warmup', 'warmup'
            proposal = {g: self.rng.uniform(-1, 1) for g in lane.info['group_ids']}
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
            if self.frozen:
                deterministic = self.config.run.frozen_action == 'deterministic'
                proposal = self.learner.act([state['observation']], deterministic=deterministic)[0]
                source, phase, policy_version = ('mean_policy' if deterministic else 'sampled_policy'), 'frozen_eval', self.learner.updates
            else:
                pending = sum(1 for s in self.lane_state.values() if s['busy'] and s['busy']['op'] not in ('reset', 'reset_reused'))
                if self.replay.insertions + pending < self.config.run.advanced.warmup_transitions:
                    proposal = {g: self.rng.uniform(-1, 1) for g in group_ids}
                    source, phase = 'random_warmup', 'warmup'
                else:
                    proposal = self.learner.act([state['observation']])[0]
                    source, policy_version = 'sac_policy', self.learner.updates
                    phase = 'adapt' if self.mode == 'fine_tune' else 'search'
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
                          exception=dict(type=type(exc).__name__, message=str(exc)[:4000]), lane_failure=True,
                          episode=None, episode_step=None)
        if (self.stop_reason is not None and not result['ok'] and not result.get('launches')
                and (result.get('exception') or {}).get('message') == STOPPED_BEFORE_LAUNCH):
            # Dispatched just before the run stopped, stopped by it before any launch: recorded as cancelled, like a forced
            # cancel, not as an infrastructure failure - one more "failure" of the link that never happened.
            result['cancelled'] = True
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
            busy['handle'] = lane.submit('retry', allowance=busy['launch_allowance'], stop_file=str(self._condition_stop_file))
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
            if busy['op'] == 'reset_reused':         # it launches nothing and charges nothing: there is nothing to record
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
        state = self.lane_state[lane.lane_id]
        completed_at = utcnow()
        self.counters['completion_index'] += 1
        commit_seq = self.dataset.next_seq()
        evaluation_id = busy['evaluation_id']
        record = result.get('record') or {}
        step = result['step'] if result['ok'] else None
        observation = step[0] if step else None
        reward = step[1] if step else None
        terminated, truncated = (bool(step[2]), bool(step[3])) if step else (False, True)
        info = step[4] if step else {}
        outcome = self._outcome(record, result, observation, truncated)
        (status, raw_metrics, raw_validity, raw_units, derived, spec_values, metric_values, constraint_rows, valid, feasible,
         nominal_feasible, violation) = outcome
        if op_is_step := busy['op'] != 'reset':
            self.counters['global_env_step'] += 1
        if not self._baseline_checked and busy['phase'] == 'baseline':
            # The calibration's random designs follow a valid baseline only: without one no lane can start an episode, and
            # every further evaluation would be the same failing reset. The run ends here as a baseline run of one evaluation.
            self._baseline_checked = True
            if not valid and self.stop_reason is None:
                self.stop_reason = 'baseline_invalid'
                self._event('limit_reached', reason=self.stop_reason,
                            note='the starting design gave no valid result: no calibration design is simulated')
        failed = not valid
        infrastructure = None if valid else classify_infrastructure_failure(
            status, record.get('reason_code'), ' '.join(str(x) for x in (record.get('error'), (result.get('exception') or {}).get('message')) if x))
        receipts = record.get('jobs') or [dict(status=status, reason_code=record.get('reason_code'))]
        for receipt_index, job in enumerate(receipts):
            job_failure = classify_infrastructure_failure(job.get('status'), job.get('reason_code'), '')
            if job_failure and not result.get('cancelled'):
                infrastructure = job_failure
                self.counters['consecutive_infrastructure_failures'] += 1
                self.counters['infrastructure_failures'] += 1
            else:
                self.counters['consecutive_infrastructure_failures'] = 0
            self._event('condition_receipt', evaluation_id=evaluation_id, job_id=job.get('job_id'),
                        candidate_receipt_index=self.counters['completion_index'], condition_receipt_index=receipt_index,
                        status=job.get('status'), infrastructure_failure=job_failure)
        if valid:
            self.counters['last_successful_evaluation_utc'] = iso(completed_at)
        self.ledger.complete(evaluation_id, failed=failed)
        self.counters['failures'] += int(failed)
        self.counters['valid_evaluations'] += int(valid)
        self.counters['feasible_evaluations'] += int(feasible)
        self.counters['consecutive_failures'] = self.counters['consecutive_failures'] + 1 if failed else 0
        env_success = info.get('success') if step else None
        if valid and env_success is not None and bool(env_success) != feasible:
            self._event('feasibility_disagreement', evaluation_id=evaluation_id, independent=feasible,
                        environment=bool(env_success), note='The independent threshold check is authoritative')
        # ---- learner receipt: replay admission and the updates it triggers
        transition_rows, state_rows, update_rows, admitted = [], [], [], False
        eligible = bool(info.get('replay_eligible')) if step else False
        if not self.calibration_only and op_is_step and step is not None and observation is not None and reward is not None:
            transition = None
            if eligible:
                from analog_optimizer.training.replay import Transition
                transition = Transition.from_step(busy['previous'], busy['proposal'], step)
                if not self.frozen:
                    self.replay.add(transition)
                    admitted = True
            if self.archive:
                transition_rows, state_rows = self._transition_rows(busy, step, lane, commit_seq, admitted, record)
            if self._pending_updates and not self._defer_updates():
                self._run_pending_updates()              # no later commit is sure to come: earlier results' updates now (7.281)
            if admitted and self._defer_updates():
                if self._updates_due():                  # decided now, run once the lane has its next design (7.281)
                    self._pending_updates.append(commit_seq)
            elif admitted:
                update_rows = self._maybe_update(commit_seq)
        # ---- first feasibility: decided when the scheduler receives the result
        in_flight_before, after_first = self._first_feasibility(busy, evaluation_id, commit_seq, nominal_feasible, feasible)
        role, best = self._offer(busy, record, info, observation, reward, commit_seq, outcome)
        job_rows, retention_plan = self._job_rows(busy, lane, role, failed)
        if infrastructure and job_rows:
            job_rows[-1]['exit_status'] = f"{job_rows[-1]['exit_status']}:{infrastructure}"   # distinguishable in simulator_jobs
        self.counters['retries'] = self.ledger.retries
        committed_at = utcnow()
        diagnostics = None
        if result.get('exception'):
            diagnostics = f"{result['exception']['type']}: {result['exception']['message']}"
        elif record.get('error') or record.get('reason_code'):
            diagnostics = f"{record.get('reason_code') or ''} {record.get('error') or ''}".strip()
        evaluation = dict(
            run_id=self.run_id, evaluation_id=evaluation_id, task_id=self.task_id, proposal_id=busy['proposal_id'],
            worker_id=lane.lane_id, episode_id=busy['episode_id'], episode_step=int(result.get('episode_step') or 0),
            global_env_step=self.counters['global_env_step'], dispatch_index=busy['dispatch_index'],
            completion_index=self.counters['completion_index'], commit_seq=commit_seq, phase=busy['phase'],
            action_source=busy['action_source'], policy_version=busy['policy_version'],
            proposed_at=iso(busy['proposed_at']), started_at=iso(busy['started_at']), completed_at=iso(completed_at),
            committed_at=iso(committed_at),
            queue_seconds=(busy['started_at'] - busy['proposed_at']).total_seconds(),
            execution_seconds=(completed_at - busy['started_at']).total_seconds(), provenance=self.provenance,
            result_source='simulation', cache_hit=False, attempts=len(busy['attempts']),
            parameters_ref=evaluation_id, metrics_ref=evaluation_id, reward=reward,
            reward_components=None if reward is None else {k: v for k, v in (info.get('violations') or {}).items()
                                                           if v is not None},
            valid=valid, all_hard_constraints_satisfied=feasible, normalized_constraint_violation=violation,
            env_success=None if env_success is None else bool(env_success),
            reward_version=record.get('reward_version'), condition_policy=record.get('condition_policy'),
            conditions_planned=info.get('conditions_planned'), conditions_evaluated=info.get('conditions_evaluated'),
            conditions_complete=info.get('conditions_complete'), nominal_feasible=nominal_feasible,
            robust_feasible=feasible if self.config.run.conditions.policy != 'off' else None,
            clearance_margin=info.get('clearance_margin'), tightest_clearance_spec=info.get('tightest_clearance_spec'),
            clearance_rule=record.get('clearance_rule'),
            condition_results_json=json.dumps(record['condition_results']) if record.get('condition_results') else None,
            best_so_far_evaluation_id=None if best is None else best['evaluation_id'],
            best_so_far_feasible=bool(self.tracker.feasible),
            best_so_far_violation=None if best is None else best['violation'],
            best_so_far_metrics=None if best is None else {k: v for k, v in best['metrics'].items() if v is not None},
            cumulative_evaluations_charged=self.ledger.charged, cumulative_completed=self.ledger.completed,
            cumulative_launches=self.ledger.launches, in_flight_at_commit=len(self.ledger.in_flight_ids()),
            after_first_feasible=after_first, in_flight_at_first_feasible=evaluation_id in in_flight_before,
            status=status, failure_type=None if valid else (
                infrastructure or ('invalid_measurement' if status == 'ok' else (record.get('reason_code') or status))),
            diagnostics=redact(diagnostics, 2000), terminated=terminated, truncated=truncated,
            replay_eligible=eligible, duplicate_of=record.get('duplicate_of'))
        if self._update_rows_waiting:                    # updates learned since the last commit go with this one (7.281)
            update_rows, self._update_rows_waiting = self._update_rows_waiting + update_rows, []
        bundle = dict(evaluation_id=evaluation_id, commit_seq=commit_seq, rows=dict(
            evaluations=[evaluation], parameters=self._parameter_rows(busy, record, evaluation_id),
            metrics=self._metric_rows(evaluation_id, raw_metrics, raw_validity, raw_units, derived, spec_values,
                                      constraint_rows, status, record.get('condition_results')),
            simulator_jobs=job_rows, learner_updates=update_rows, states=state_rows, transitions=transition_rows))
        self.dataset.commit(bundle)                              # <- durable acknowledgement
        timings = record.get('timings')
        if isinstance(timings, dict) and timings:
            self._timings.append(dict(evaluation_id=evaluation_id, worker_id=lane.lane_id, phase=busy['phase'],
                                      committed_at=iso(committed_at), seconds=timings))
            if len(self._timings) >= TIMING_BATCH:
                self._write_timings()
        if role is not None:
            write_json(self.layout.best_design / 'tracker_state.json',
                       dict(last_commit_seq=commit_seq, **self.tracker.state_dict()))
        self._apply_retention(retention_plan, role)
        # ---- lane state for the next dispatch
        if result.get('exception') and not result.get('cancelled'):
            state['finished'] = True
            if self.stop_reason is None:
                self.stop_reason = 'evaluation_exception'
                self.error = redact(diagnostics, 2000)
                self._log_error('evaluation_exception', None, evaluation_id=evaluation_id, detail=diagnostics)
        else:
            state['observation'] = observation
            state['needs_reset'] = terminated or truncated or observation is None
            if busy['op'] == 'reset':                # the lane keeps a valid simulated reset for the next reused ones
                state['reset_cache_valid'] = bool(result['ok'] and info.get('evaluation_valid') and observation is not None
                                                  and not terminated and not truncated)
                state['resets_since_check'] = 0
        every, seconds = self.config.output.checkpoint_every_evaluations, self.config.output.checkpoint_every_seconds
        if self.config.output.save_checkpoints and (
                (every and commit_seq - self.counters['last_checkpoint_commit'] >= every)
                or (seconds and self._clock() - self.last_checkpoint_time >= seconds)):
            self.checkpoint_due = True
        self._write_status('running', throttle=0.5)

    def _outcome(self, record, result, observation, truncated):
        """What the evaluation measured, judged against the Specs: its status, the simulator's own results, the probes and
        specs worked out from them, and whether the design is valid and feasible (at every condition it ran at)."""
        # The lane's record also carries the computed specs (spec_equations: added to the simulation result so that the
        # reward sees them). The simulator's own results are everything else; they alone feed the probes and raw rows.
        plan, computed = self.compiled.plan, set(self.compiled.plan.injected)
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
        for target in self.compiled.targets:
            value = spec_values.get(target['metric_id'])
            ok = value is not None and status in ('ok', 'measurement_error')
            metric_values[target['metric_id']], metric_valid[target['metric_id']] = (value if ok else None), ok
        valid, feasible, constraint_rows, violation = hard_constraints(self.compiled.targets, metric_values, metric_valid)
        nominal_feasible = feasible
        if observation is not None and observation.condition_results:
            evaluation = observation.evaluation
            checks = []
            for index, row in enumerate(observation.condition_results):
                targets = tuple(t for t in self.compiled.targets if index == 0 or not t['nominal_only'])
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

    def _first_feasibility(self, busy, evaluation_id, commit_seq, nominal_feasible, feasible):
        """The run's first (nominally) feasible design, decided when the scheduler receives the result; the stop at the first
        feasible design. Returns (the evaluations in flight at the first feasible one, whether it came before)."""
        in_flight_before = set(self.ledger.first_feasible['in_flight_evaluation_ids']) if self.ledger.first_feasible else set()
        after_first = self.ledger.first_feasible is not None
        if nominal_feasible and self.ledger.first_nominal_feasible is None:
            first = self.ledger.mark_first_feasible(evaluation_id, dispatch_index=busy['dispatch_index'],
                commit_seq=commit_seq, active_seconds=self._active_seconds(),
                wall_seconds=(utcnow() - self._run_created()).total_seconds(), nominal=True)
            self._event('first_nominal_feasible', **first)
        if feasible and not after_first:
            first = self.ledger.mark_first_feasible(evaluation_id, dispatch_index=busy['dispatch_index'],
                                                    commit_seq=commit_seq, active_seconds=self._active_seconds(),
                                                    wall_seconds=(utcnow() - self._run_created()).total_seconds())
            self._event('first_feasible', **first)
            if self.config.run.stop_at_first_feasible and self.stop_reason is None:
                self.stop_reason = 'first_feasible'
        return in_flight_before, after_first

    def _offer(self, busy, record, info, observation, reward, commit_seq, outcome):
        """The evaluation as a candidate of the best-design tracker. Returns (its role there, the tracker's best)."""
        (status, raw_metrics, raw_validity, raw_units, derived, spec_values, metric_values, constraint_rows, valid, feasible,
         nominal_feasible, violation) = outcome
        candidate = self._candidate(busy, record, metric_values, raw_units, constraint_rows, valid, feasible,
                                    violation, reward, commit_seq)
        candidate.update(nominal_feasible=nominal_feasible, nominal_metrics=record.get('metrics'),
                         robust_feasible=feasible if self.config.run.conditions.policy != 'off' else None,
                         worst_metrics=metric_values, conditions_complete=info.get('conditions_complete'),
                         conditions_evaluated=info.get('conditions_evaluated'), conditions_planned=info.get('conditions_planned'),
                         clearance_margin=info.get('clearance_margin'), tightest_clearance_spec=info.get('tightest_clearance_spec'),
                         clearance_rule=record.get('clearance_rule'),
                         conditions=[row['condition']['corner']['id'] if row['condition'] else 'nominal'
                                     for row in record.get('condition_results', [])] or ['nominal'])
        if candidate['robust_feasible'] and self.compiled.preference and observation is not None:
            preference = self.compiled.preference
            spec = next(s for s in observation.specs if s.metric_id == preference['metric'])
            applicable = observation.condition_results[:1] if spec.nominal_only else observation.condition_results
            values = [row.metrics.get(spec.metric_id) for row in applicable
                      if row.metric_validity.get(spec.metric_id) is True]
            candidate['worst_metrics'] = dict(metric_values)
            candidate['worst_metrics'][spec.metric_id] = ((max(values) if preference['direction'] == 'min' else min(values))
                                                         if len(values) == len(applicable) else None)
        role = self.tracker.offer(candidate)
        best = self.tracker.best
        return role, best

    def _run_created(self):
        return datetime.fromisoformat(self.manifest['created_utc'])

    def _updates_due(self):
        adv = self.config.run.advanced
        return len(self.replay) >= adv.batch_size and not self.replay.insertions % adv.update_every

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
        return result

    def _checkpoint(self, kind):
        self._run_pending_updates()                      # the save point holds every update so far (7.281)
        self._persist_waiting_rows()                     # and its data cursor covers their rows (7.283)
        self._clean_host()                               # the lanes are idle: the host's dropped job folders go (7.282)
        if not self.config.output.save_checkpoints:
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
        if (kind != 'final' or last is None or last.get('kind') != 'periodic' or not self.config.output.save_checkpoints
                or (self.manual_save and self.manual_save['state'] == 'waiting')):
            return None
        counters = last['counters']
        if (last['data_cursor']['commit_seq'] != self.dataset.last_seq
                or counters['learner_updates'] != int(getattr(self.learner, 'updates', 0))
                or counters['replay_insertions'] != (0 if self.replay is None else self.replay.insertions)):
            return None
        metadata = self.checkpoints.relabel(last['checkpoint_id'], kind, was=last['kind'])
        self.last_checkpoint = metadata
        self._event('checkpoint_saved', checkpoint_id=metadata['checkpoint_id'], kind=kind, relabelled_from=last['kind'],
                    capability=metadata['restoration_capability'], commit_seq=self.dataset.last_seq)
        return metadata

    # ------------------------------------------------------------------ finalize
    def _clear_scratch(self):
        """Once the lanes and the preparation service are closed: the links in the lanes' folders, then the run's local
        scratch itself (`layout.local_scratch`). Each kept job folder moved to the run folder when its result was
        durable; the rest are temporaries, as in work/."""
        if self._scratch is None:
            return
        for lane in self.lanes:
            directory = (getattr(lane, 'info', None) or {}).get('directory')
            if directory:
                try:
                    unlink_scratch(directory)
                except OSError:
                    pass
        shutil.rmtree(self._scratch, ignore_errors=True)
        try:
            self._scratch.parent.rmdir()              # the experiment's folder, once none of its runs has scratch left
        except OSError:
            pass

    def _finalize(self, final_state):
        self._write_timings()
        try:
            self._run_pending_updates()                  # before the last save point and its "unchanged" check (7.281)
            self._persist_waiting_rows()                 # no commit comes after them: their rows go as their own record (7.283)
        except Exception as exc:
            self._log_error('pending_updates_failed', exc)
        problems = []
        for lane in self.lanes:
            try:
                outcome = lane.close()
                if outcome.get('state') not in ('restored', 'not_connected', 'already_closed'):
                    problems.append(f"lane {lane.lane_id}: environment restoration state {outcome.get('state')}")
            except BaseException as exc:
                problems.append(f'lane {lane.lane_id}: {type(exc).__name__}: {exc}')
        if self._preparation is not None:                # after every lane: the owner restores the schematic and lets go
            try:
                self._preparation.close()
                restoration = (self.preparation_report or {}).get('preparation_restoration') or {}
                if restoration.get('state') != 'restored':
                    problems.append(f"preparation service: restoration state {restoration.get('state')}")
            except BaseException as exc:
                problems.append(f'preparation service: {type(exc).__name__}: {exc}')
            self._preparation = None
        self._clear_scratch()
        try:                                             # every lane is closed: the host's dropped job folders go (7.282)
            self._clean_host()
            self._log_virtuoso_memory('end')
        except Exception as exc:
            self._log_error('simulator_host_cleanup_failed', exc)
        checkpoint = None
        persistence_ok = self.dataset is not None and self.dataset.failed is None
        if persistence_ok and hasattr(self, 'ledger'):
            try:
                self.dataset.flush()
                if not self.ledger.in_flight_ids():
                    kind = {'paused': 'pause', 'stopped': 'stop', 'completed': 'final'}.get(final_state, 'safety')
                    checkpoint = self._relabel_unchanged(kind) or self._checkpoint(kind)
            except BaseException as exc:
                persistence_ok = False
                problems.append(f'final save failed: {type(exc).__name__}: {exc}')
                self._log_error('final_save_failed', exc)
        if problems and final_state == 'completed':
            final_state = 'failed'
        if problems:
            self.error = redact('; '.join(filter(None, [self.error, *problems])), 4000)
        try:
            if hasattr(self, 'ledger'):
                self._write_outputs(final_state, checkpoint, persistence_ok)
        except BaseException as exc:
            self._log_error('summary_failed', exc)
            final_state = 'failed'
            self.error = redact(f'{self.error or ""} summary failed: {exc}', 4000)
        if self.dataset is not None:
            try:
                self.dataset.close()
            except BaseException:
                pass
        ended = utcnow()
        segment = self.manifest['segments'][-1]
        segment.update(ended_utc=iso(ended), end_state=final_state, stop_reason=self.stop_reason,
                       active_seconds=self._clock() - self._segment_started)
        self.manifest['state'] = final_state
        self._adopt_baseline()
        self._calibrate()
        write_json(self.layout.manifest, self.manifest)
        self._event('segment_ended', state=final_state, stop_reason=self.stop_reason, error=self.error)
        self._write_status(final_state)
        try:
            build_artifact_manifest(self.layout, run_id=self.run_id, final=final_state in ('completed', 'stopped'),
                                    dataset_status=None if self.dataset is None else self.dataset.status(),
                                    notes=getattr(self, 'manifest_notes', []))
        except BaseException as exc:
            self._log_error('artifact_manifest_failed', exc)
        for stream in (self.events, self.errors, self.dispatch_log):
            stream.close()
        return final_state

    def _adopt_baseline(self):
        """A finished "Baseline simulation" of a generated task becomes the task's reference by itself
        (profiles.adopt_baseline_run, record 7.78) - only that run kind, after the tables are closed and the manifest
        says how the run ended, before it is written. What it did or why not goes into the manifest's notes. Nothing
        here may fail the run: a problem is logged and the run ends as it would have."""
        if self.manifest.get('run_kind') != 'baseline_preflight':
            return
        try:
            from . import profiles  # lazy: in the try: a failure of the import is handled with the rest
            outcome = profiles.adopt_baseline_run(self.layout.run_dir, manifest=self.manifest)
        except BaseException as exc:
            self._log_error('baseline_reference_failed', exc)
            return
        if outcome:
            self.manifest.setdefault('notes', []).append(outcome['note'])
            self.manifest_notes = [*getattr(self, 'manifest_notes', []), outcome['note']]
            self._event('baseline_reference', recorded=outcome['recorded'], task=f"real:{outcome['name']}", note=outcome['note'])

    def _calibrate(self):
        """A baseline run asked to calibrate (record 7.197) writes its proposals - a Scale per Specs row and the Initial
        alpha, from its random designs - into calibration.json of the run folder, and says so in the manifest's notes.
        Nothing is applied: the page offers them. As with the baseline's adoption, nothing here may fail the run."""
        if not self.manifest.get('calibration') or self.dataset is None:
            return
        try:
            from . import calibration  # lazy: in the try: a failure of the import is handled with the rest
            result = calibration.from_run(self.layout.run_dir, manifest=self.manifest)
            write_json(self.layout.run_dir / calibration.FILE, result)
        except BaseException as exc:
            self._log_error('calibration_failed', exc)
            return
        note = calibration.sentence(result)
        self.manifest.setdefault('notes', []).append(note)
        self.manifest_notes = [*getattr(self, 'manifest_notes', []), note]
        self._event('calibration', status=result['status'], designs=result['designs'], note=note)

    def _write_outputs(self, final_state, checkpoint, persistence_ok):
        task = self.task
        reparse, exporter, netlist_name = None, None, 'optimized_dut.scs'
        if task.netlist_path and task.parser_config_path:
            def reparse(text):
                from analog_optimizer.netlist.config import ParserConfig
                from analog_optimizer.netlist.spectre_parser import SpectreParser
                return SpectreParser(ParserConfig.from_file(task.parser_config_path)).parse_text(
                    text, source=task.netlist_path, top=task.circuit.get('dut_hierarchy'))
        elif task.circuit.get('simulator') == 'ngspice':          # a SPICE deck: its own writer, values also inside a once-used subcircuit
            from .ngspice_tasks import export_deck  # lazy: ngspice_tasks imports the optimizer
            exporter, netlist_name = export_deck(task), 'optimized_dut.cir'
        notes = best_design.write_outputs(
            self.layout.best_design, self.tracker,
            task=dict(task_id=self.task_id, task_key=task.task_key, circuit=task.circuit, provenance=self.provenance),
            config_summary=dict(targets=list(self.compiled.targets), variables=list(self.compiled.variables)),
            netlist_text=task.netlist_text, graph=self.compiled.graph, reparse=reparse, exporter=exporter, netlist_name=netlist_name)
        self.manifest_notes = [f'best_design/{k}: {v}' for k, v in notes.items()]
        summary = build_run_summary(self, final_state, checkpoint, persistence_ok)
        write_json(self.layout.summary, summary)
        if self.config.output.export_summary_csv:
            try:                                  # derived CSVs only; a failure here never loses raw data
                # lazy: in the try: a failure of the import is handled with the rest
                from .aggregates import export_aggregates
                export_aggregates(self.layout.experiment_dir)
            except BaseException as exc:
                self._log_error('aggregate_export_failed', exc)

    # ------------------------------------------------------------------ status / logs
    def _event(self, name, **fields):
        self.events.append(dict(time_utc=iso(), event=name, run_id=self.run_id, **fields))

    def _log_error(self, name, exc, **fields):
        self.errors.append(dict(time_utc=iso(), error=name, run_id=self.run_id,
                                type=None if exc is None else type(exc).__name__,
                                message=None if exc is None else redact(str(exc), 4000),
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
