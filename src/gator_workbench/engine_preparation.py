"""Prepare scheduler-owned run state, then open its simulation lanes.

The engine is passed explicitly and remains the sole owner of mutable state. Resume
reconciliation completes before any lane opens; closing belongs to finalization.
`local_scratch` is supplied by the scheduler so its filesystem policy stays explicit.
"""
from __future__ import annotations

import os
import random
import socket

from . import best_design, checkpoints as ckpt, engine_comparison, modes, network_inputs
from .budget import BudgetLedger
from .lanes import ScratchLinked, open_lanes
from .pdk import run_vocabulary
from .run_definitions import learner_experiment
from .run_lock import iso
from .storage.atomic import write_json
from .storage.dataset import RawDataset
from .trajectory import StateEncoder


def prepare(engine, *, local_scratch):
    cfg, out, adv = engine.config, engine.config.output, engine.config.run.advanced
    enabled = {'evaluations', 'parameters', 'metrics', 'simulator_jobs'}
    if out.save_learner_updates and not engine.frozen:
        enabled.add('learner_updates')
    if out.save_transition_archive:
        enabled |= {'transitions', 'states'}
    engine.dataset = RawDataset(engine.layout.data, enabled_tables=enabled, flush_every=out.flush_every_evaluations)
    engine.archive = out.save_transition_archive
    experiment = learner_experiment(cfg, engine.task, engine.task_hash)
    engine.experiment = experiment
    engine.vocabulary = run_vocabulary(engine.layout.run_dir)      # the run's own component list; None = standard
    input_options = modes.runtime_options(cfg, engine.vocabulary)
    source_dir = source_meta = None
    if engine.entry == 'resume':
        source_dir = ckpt.resolve_checkpoint(engine.layout.run_dir, 'latest')
        source_meta = ckpt.read_metadata(source_dir)
    elif engine.mode in ('fine_tune', 'frozen'):
        parent = engine.manifest['parent']
        source_dir = ckpt.resolve_checkpoint(parent['run_dir'], parent['checkpoint_id'])
        source_meta = ckpt.read_metadata(source_dir)
    built = modes.build('resume' if engine.entry == 'resume' else engine.mode, experiment=experiment,
                        model_config=modes.model_config_from(cfg.run.network),
                        sac_config=modes.sac_config_from(adv), spec_schema=engine.compiled.spec_schema,
                        advanced=adv, seed=cfg.run.seed, origin=engine.task.origin, source_dir=source_dir,
                        source_metadata=source_meta, task_definition_hash=engine.task_hash, vocabulary=engine.vocabulary,
                        runtime=input_options, view=network_inputs.view_for(cfg, engine.vocabulary))
    engine.learner, engine.replay, engine.freeze = built['learner'], built['replay'], built['freeze']
    engine.load_policy = built['policy']
    engine.rehearsal = None
    if cfg.run.rehearsal is not None:
        from .rehearsal import Rehearsal  # lazy: rehearsal imports torch
        engine.rehearsal = Rehearsal(cfg.run.rehearsal, engine.learner, origin=engine.task.origin,
                                   seed=cfg.run.seed, batch_size=adv.batch_size)
    if engine.frozen:
        for module in (engine.learner.actor, engine.learner.critics, engine.learner.targets):
            module.requires_grad_(False).eval()
        engine.replay = None
    if engine.entry == 'start' and engine.mode == 'fine_tune' and adv.freeze_encoder and engine.freeze is None:
        engine.freeze = modes.EncoderFreeze(engine.learner)
    if engine.entry == 'resume' and engine.mode == 'fine_tune' and adv.freeze_encoder:
        engine.freeze = modes.EncoderFreeze(engine.learner)
    engine.frozen_digest = ckpt.weight_digest(engine.learner) if engine.frozen else None
    run = cfg.run
    engine.ledger = BudgetLedger(run.max_evaluations, max_launches=run.max_spectre_launches,
                               max_retries=run.max_retries)
    engine.rng = random.Random(run.seed)
    # Bayesian optimization instead of the policy (run.optimizer, record 7.304): its proposer is made at the first
    # design it is asked for, with the lanes' parameter groups. Its state lives in this process only, so such a run
    # is a from-scratch run that is not continued.
    engine.proposer = None
    if run.optimizer == 'bayes' and (engine.mode != 'scratch' or engine.entry == 'resume'):
        raise ValueError('A Bayesian-optimization run (run.optimizer "bayes") is a from-scratch run and cannot be '
                         'resumed or started from a saved model: its search state is not saved. Start a new run.')
    if engine_comparison.is_search(cfg) and engine.mode != 'scratch':
        raise ValueError(f'A {run.optimizer} run (the archive comparison) starts its own search and loads no saved model: '
                         'its mode is scratch (a resume continues it from its own save point).')
    engine.tracker = best_design.BestDesignTracker(engine.compiled.preference)
    engine.counters = dict(global_env_step=0, completion_index=0, episodes=0, baseline_done=False,
                         consecutive_failures=0, consecutive_infrastructure_failures=0,
                         infrastructure_failures=0, last_successful_evaluation_utc=None,
                         active_seconds_before=0.0, sum_job_runtime_seconds=0.0,
                         failures=0, retries=0, last_checkpoint_commit=0, launches_unconfirmed_after_crash=0,
                         interrupted_evaluations=0, feasible_evaluations=0, valid_evaluations=0, initial_given=0)
    engine.previous_best_waveform = None
    # A baseline run asked to calibrate (record 7.197): until its baseline evaluation is committed and valid, no other
    # lane starts and no random design is drawn (`_dispatch`, `_commit`). Any other run never waits.
    engine._baseline_checked = engine.calibration_only or not engine.manifest.get('calibration') or engine.entry == 'resume'
    engine.encoder = None
    if engine.archive:
        engine.encoder = StateEncoder(engine.layout.data / 'states' / 'static', task_id=engine.task_id,
                                    graph=engine.compiled.graph, specs=engine.compiled.specs,
                                    feature_schema_version=input_options['feature_schema'].version,
                                    spec_schema_version=engine.compiled.spec_schema.version)
    engine_comparison.prepare(engine)           # the archive comparison's first designs and search (a resume restores it)
    if engine.entry == 'resume':
        engine._restore(built['run_state'])
    if engine.ledger.uncertain_launches:
        write_json(engine._condition_stop_file, dict(reason='unresolved_launch_intent'))
        raise RuntimeError('Unresolved physical launch intents/leases must be reconciled before resume; no lanes opened')
    engine.checkpoints = ckpt.CheckpointStore(engine.layout.run_dir, run_id=engine.run_id, task_id=engine.task_id,
                                            task_definition_hash=engine.task_hash,
                                            save_replay=out.save_replay_snapshots, keep_last=out.keep_last_checkpoints)
    engine._record_load_policy()
    count = min(run.concurrency, engine.task.max_concurrency)
    env_run = run.model_copy(deep=True)
    factory = engine._lane_factory or engine.task.env_factory_builder(engine.compiled, engine.layout.work, env_run)
    circuit = getattr(factory, 'profile', None) or getattr(getattr(factory, 'inner', None), 'profile', None)
    if getattr(circuit, 'model_library_event', None) is not None:    # which parts of the model file the decks load
        engine._event('model_library', **circuit.model_library_event)
    from analog_optimizer.training.workers import WorkerLimits
    # A real (native) factory needs ONE owner of the Virtuoso session, alive from before the first lane opens until
    # after the last one closed: the optimizer's preparation service. Entered here exactly as its own training loop
    # does (training/parallel.py); without it a real lane cannot even connect. Closed in _finalize, after the lanes.
    prepare_context = getattr(factory, 'preparation_context', None)
    if callable(prepare_context):
        from contextlib import ExitStack
        engine.preparation_report = {}
        engine._preparation = ExitStack()
        factory = engine._preparation.enter_context(prepare_context(WorkerLimits(), engine.preparation_report))
        engine._event('preparation_service_started', session=(engine.preparation_report.get('preparation') or {}).get('session_dir'))
    limits = WorkerLimits(operation_seconds=max(300., (1 + len(run.conditions.corners)) * adv.simulation_timeout_seconds + 180.))
    engine._scratch = local_scratch(engine.layout)
    if engine._scratch is not None:                    # wrapped last: it keeps the preparation service's factory as is
        factory = ScratchLinked(factory, engine._scratch)
        engine._event('simulator_scratch', path=str(engine._scratch),
                    note='export packages and per-job folders on the local disk; kept job folders move to the run folder')
    engine.lanes = open_lanes(factory, count, use_processes=engine.use_processes, limits=limits)
    engine.lane_state = {lane.lane_id: dict(observation=None, needs_reset=True, busy=None, finished=False,
                                          episode_id=None, reset_cache_valid=False, resets_since_check=0)
                       for lane in engine.lanes}
    for lane in engine.lanes:
        if lane.info['origin'] != engine.task.origin:
            raise RuntimeError('Lane origin differs from the task origin')
    engine.last_checkpoint_time = engine._clock()
    engine.checkpoint_due = False
    # "Save now" (command `checkpoint`): the next due save is of kind `manual`, and the request is answered in
    # status.json so that the page knows when ITS request has been written.
    engine.checkpoint_kind, engine.manual_save = 'periodic', None


def record_load_policy(engine):
    segment = engine.manifest['segments'][-1]
    segment.update(load_policy=engine.load_policy, started_utc=iso(engine._wall_started), pid=os.getpid(),
                   host=socket.gethostname(), lanes='process' if engine.use_processes else 'thread')
    write_json(engine.layout.manifest, engine.manifest)
