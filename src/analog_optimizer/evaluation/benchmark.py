"""M5 experiment runner with isolated replay, bounded seed workers and fixed budgets."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
from time import perf_counter

import torch

from analog_optimizer.envs.sizing import graph_contract, write_record
from analog_optimizer.models import ENCODER_TYPES, REMOVED_ENCODERS, ModelConfig
from analog_optimizer.models.inputs import SpecSchema
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.sac import SACLearner, source_digest
from analog_optimizer.training.runtime import write_report_preserving_error
from .transfer import aggregate_runs, freeze_protocol, validate_split


ENCODER_LABELS = dict(graph_transformer='gt', rgcn='rgcn', gatv2='gatv2',
                      graph_gps='gps', group_cross_attention='group_ca')


def benchmark_models(settings):
    """The selected encoders get scratch/frozen/adapt each, plus random and pattern search.

    `settings['encoders']` is required. Until 2026-09-24 an omitted selection meant the six-method M5 protocol
    (graph_transformer + port_gnn); port_gnn was removed that day, so that protocol runs only from source commit bbdfe36.
    """
    selected = settings.get('encoders')
    if selected is None:
        raise ValueError("settings['encoders'] is required: the omitted selection used to mean the M5 six-method "
                         'protocol with port_gnn, which was removed on 2026-09-24 (source commit bbdfe36 still runs it)')
    if isinstance(selected, (list, tuple)):
        for name in selected:
            if isinstance(name, str) and name in REMOVED_ENCODERS:
                raise ValueError(f'encoders: {REMOVED_ENCODERS[name]}')
    if (not isinstance(selected, (list, tuple)) or not selected
            or any(not isinstance(name, str) or name not in ENCODER_TYPES for name in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('encoders must be a nonempty, unique list of supported encoder types')
    models = {ENCODER_LABELS[name]: ModelConfig(
        encoder_type=name, hidden_dim=settings.get('hidden_dim', 32),
        heads=settings.get('heads', 4), layers=settings.get('layers', 2),
        structural_encoding=settings.get('structural_encodings', {}).get(name)) for name in selected}
    names = tuple(f'{key}_{phase}' for key in models for phase in ('scratch', 'frozen', 'adapt')) + ('random', 'pattern_search')
    methods = {}
    for name in names:
        if name in ('random', 'pattern_search'):
            methods[name] = (None, 'frozen')
        else:
            model, suffix = name.rsplit('_', 1)
            methods[name] = (model, 'adaptation' if suffix == 'adapt' else suffix)
    return models, methods, tuple(models)


def benchmark_call_budget(tasks, settings):
    """Validate and count a complete matrix before constructing any backend."""
    validate_split(tasks)
    seeds = settings['seeds']
    if (not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
            or any(type(settings[k]) is not int or settings[k] < 1 for k in
                   ('pretrain_steps', 'test_steps', 'batch_size', 'max_calls'))):
        raise ValueError('Invalid seed or call/update budgets')
    if settings['batch_size'] > min(settings['pretrain_steps'], settings['test_steps']):
        raise ValueError('Budget must allow learning in both pretraining and adaptation')
    models, methods, validation_models = benchmark_models(settings)
    counts = {p: sum(t.partition == p for t in tasks) for p in ('train', 'validation', 'test')}
    planned = len(seeds) * (len(models)*counts['train']*(1+settings['pretrain_steps']) +
                           2*len(validation_models)*counts['validation'] +
                           len(methods)*counts['test']*(1+settings['test_steps']))
    if planned > settings['max_calls']:
        raise ValueError(f'Planned {planned} calls exceed max_calls={settings["max_calls"]}')
    return planned


def seed_all(seed):
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def weight_digest(learner):
    h = hashlib.sha256()
    for module in (learner.actor, learner.critics, learner.targets):
        for key, value in module.state_dict().items():
            h.update(key.encode())
            h.update(value.detach().cpu().numpy().tobytes())
    h.update(learner.log_alpha.detach().cpu().numpy().tobytes())
    return h.hexdigest()


def transfer_weights(source, destination):
    """Initialize a new task from trained weights; optimizer/replay stay fresh."""
    if (source.feature_schema != destination.feature_schema or source.spec_schema != destination.spec_schema
            or source.model_config != destination.model_config or source.config != destination.config
            or source.experiment['origin'] != destination.experiment['origin']):
        raise ValueError('Incompatible transfer contract')
    for target, original in ((destination.actor, source.actor), (destination.critics, source.critics),
                             (destination.targets, source.targets)):
        target.load_state_dict(deepcopy(original.state_dict()))
    with torch.no_grad():
        destination.log_alpha.copy_(source.log_alpha)


def admit_transition(replay, task, phase, observation, proposal, step):
    if not ((phase == 'pretrain' and task.partition == 'train') or
            (phase in ('adaptation', 'scratch') and task.partition == 'test')):
        raise ValueError('Partition/phase cannot contribute to this replay')
    transition = Transition.from_step(observation, proposal, step)
    if (transition.observation.specs != task.specs or
            graph_contract(transition.observation.graph) != graph_contract(task.graph)):
        raise ValueError('Transition belongs to another task')
    replay.add(transition)


class PatternSearch:
    """Bounded coordinate polling from the common baseline, step halving per sweep."""
    def __init__(self, groups):
        import math
        self.ids = [g.id for g in groups]
        self.center = {}
        for g in groups:
            value, lower, upper = g.value, g.lower, g.upper
            if g.scale == 'log':
                value, lower, upper = map(math.log, (value, lower, upper))
            self.center[g.id] = 2 * (value-lower) / (upper-lower) - 1
        self.best = None
        self.index, self.radius = 0, .5
        self.poll_center = dict(self.center)
        self.improved = False

    def observe(self, proposal, reward):
        if reward is not None and (self.best is None or reward > self.best):
            self.best = reward
            if proposal is not None:
                self.center = dict(proposal)
                self.improved = True

    def propose(self):
        if self.index == 2 * len(self.ids):
            self.index = 0
            if not self.improved:
                self.radius *= .5
            self.poll_center, self.improved = dict(self.center), False
        action = dict(self.poll_center)
        key = self.ids[self.index // 2]
        action[key] = min(1., max(-1., action[key] + self.radius * (1 if self.index % 2 == 0 else -1)))
        self.index += 1
        return action


def run_episode(env, task, method, *, learner=None, replay=None, seed=0, batch_size=2,
                phase='frozen', warmup=1, checkpoint=None, baseline_check=None,
                history_limit=100, checkpoints=None, update_recorder=None):
    seed_all(seed)
    rng = random.Random(seed)
    started = perf_counter()
    from analog_optimizer.training.workers import append_history, worker_progress
    from .streaming import RunStatistics
    limit = history_limit if env.recorder is not None else None
    records, updates = [], []
    history = dict(records=records, updates=updates, records_count=0, updates_count=0)
    statistics = RunStatistics(limit)
    last_recorded = None
    before = weight_digest(learner) if learner else None
    summary = dict(task=task.id, partition=task.partition, transfer=task.transfer,
                   circuit_class=task.circuit_class, family=task.family, method=method,
                   seed=seed, phase=phase, origin=env.expected_origin, records=[],
                   actions=[], inference_seconds=0., update_seconds=0., updates=0, completed=False)
    summary['model_config'] = asdict(learner.model_config) if learner else None
    summary['parameters'] = (sum(p.numel() for module in (learner.actor, learner.critics)
                                  for p in module.parameters()) if learner else 0)
    training = phase in ('pretrain', 'adaptation', 'scratch')
    if training and (learner is None or replay is None):
        raise ValueError('Learning episodes require an isolated learner and replay')
    if training and not ((phase == 'pretrain' and task.partition == 'train') or
                         (phase in ('adaptation', 'scratch') and task.partition == 'test')):
        raise ValueError('Partition/phase mismatch before simulation')
    if not training and replay is not None:
        raise ValueError('Frozen evaluation must not receive a replay buffer')

    def record(info):
        nonlocal last_recorded
        if env.recorder is None:
            row = json.loads(Path(info['record_path']).read_text())
        else:
            from analog_optimizer.recording.session import evaluation_record
            row = evaluation_record(env.recorder.store, info['candidate_id'])
        row['time_from_start_seconds'] = perf_counter() - started
        statistics.add(row)
        last_recorded = row['candidate_id']
        append_history(history, 'records', row, limit)
        append_history(summary, 'records', info['record_path'], limit)
        worker_progress(dict(task=task.id, method=method, seed=seed, call=env.simulation_calls))
        return row

    try:
        with env:
            observation, info = env.reset()
            baseline = record(info)
            if baseline_check:
                baseline_check(baseline)
            search = PatternSearch(env.mapper.groups)
            search.observe(None, baseline.get('reward'))
            if observation is not None and not info['terminated'] and not info['truncated']:
                for _ in range(env.max_steps):
                    start = perf_counter()
                    if method == 'random' or (phase in ('pretrain', 'scratch') and replay.insertions < warmup):
                        proposal = {g: rng.uniform(-1, 1) for g in env.mapper.group_ids}
                        action_source = 'random'
                    elif method == 'pattern_search':
                        proposal, action_source = search.propose(), 'coordinate_poll'
                    else:
                        # Frozen mean policy is the zero-shot control. No updates even on successful candidates.
                        proposal = learner.act([observation], deterministic=not training)[0]
                        action_source = 'stochastic_policy' if training else 'mean_policy'
                    summary['inference_seconds'] += perf_counter() - start
                    if env.recorder is not None:
                        env.recorder.phase = phase
                        env.recorder.policy_version = learner.updates if learner is not None else None
                    step = env.step(proposal)
                    row = record(step[4])
                    row['action_source'] = action_source
                    append_history(summary, 'actions', dict(candidate_id=row['candidate_id'], proposal=proposal,
                                                           source=action_source), limit)
                    search.observe(proposal, step[1])
                    if training and step[4]['replay_eligible']:
                        admit_transition(replay, task, phase, observation, proposal, step)
                        if len(replay) >= batch_size:
                            start = perf_counter()
                            update = learner.update(replay.sample(batch_size))
                            append_history(history, 'updates', update, limit)
                            if update_recorder is not None:
                                update_recorder.add(update)
                            summary['update_seconds'] += perf_counter() - start
                    if checkpoints is not None and training:
                        checkpoints.maybe_save(learner, replay, replay.insertions,
                            run_state=dict(task=task.id, phase=phase, seed=seed, collector_rng=rng.getstate(),
                                           simulation_calls=env.simulation_calls,
                                           boundary='completed_benchmark_step; fresh episode required'))
                    observation = step[0]
                    if step[2] or step[3]:
                        break
        summary['completed'] = True
    except BaseException as exc:
        summary.update(exception_type=type(exc).__name__, error=str(exc))
        # Include any journal written before an exception (including charged failed calls).
        if env.recorder is None:
            recorded = {r['candidate_id'] for r in records}
            for path in sorted((env.directory / 'candidates').glob('*.json')):
                row = json.loads(path.read_text())
                if row['candidate_id'] not in recorded:
                    record(dict(record_path=str(path), candidate_id=row['candidate_id']))
        elif env.recorder.last_eval_id is not None and env.recorder.last_eval_id != last_recorded:
            try:
                record(dict(candidate_id=env.recorder.last_eval_id,
                            record_path=f'sqlite:{env.recorder.run_id}/{env.recorder.last_eval_id}'))
            except Exception as recording_error:
                summary['unconfirmed_evaluation'] = dict(id=env.recorder.last_eval_id, error=str(recording_error))
        raise
    finally:
        summary.update(statistics.summary(calls=env.simulation_calls,
                                     wall_seconds=perf_counter()-started, budget=1+env.max_steps))
        summary.update(updates=history['updates_count'], update_log=updates, weight_before=before,
                       weight_after=weight_digest(learner) if learner else None,
                       replay_insertions=0 if replay is None else replay.insertions)
        restore = env.directory / 'restoration.json'
        summary['restoration'] = json.loads(restore.read_text()) if restore.exists() else {'state': 'unknown'}
        write_report_preserving_error(env.directory / 'run.json', summary)
    if not training and summary['weight_before'] != summary['weight_after']:
        raise RuntimeError('Frozen evaluation changed model weights')
    if training:
        state = dict(task=task.id, phase=phase, seed=seed, simulation_calls=env.simulation_calls,
                     boundary='completed_benchmark_episode', summary=summary)
        if checkpoints is not None:
            path = checkpoints.maybe_save(learner, replay, replay.insertions, run_state=state, force=True)
            checkpoints.policy(learner, replay.insertions)
            summary['checkpoint'] = str(path)
        elif checkpoint:
            learner.save(checkpoint, replay, run_state=state)
    return summary


def run_benchmark(tasks, env_factory, directory, *, origin, settings, provenance, progress=print,
                  baseline_check=None, recorder=None, max_workers=1, limits=None, _execution_seeds=None, report=None):
    """Factory(task, max_steps, output) must return a NEW restorable environment."""
    from analog_optimizer.training.workers import WorkerLimits
    limits = limits or WorkerLimits()
    from analog_optimizer.backends.native_preparation import validate_workers
    validate_workers(max_workers)
    if max_workers > 1 and not getattr(env_factory, 'parallel_safe', False):
        raise ValueError('Parallel benchmark requires isolated immutable-netlist or synthetic environments')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    planned = benchmark_call_budget(tasks, settings)
    schema_settings = settings.get('spec_schema')
    spec_schema = (SpecSchema() if schema_settings is None else SpecSchema(
        version=schema_settings['version'], metrics=tuple(tuple(m) for m in schema_settings['metrics'])))
    registry = {name: unit for name, unit, _ in spec_schema.metrics}
    for task in tasks:
        if any(registry.get(s.metric_id) != s.unit for s in task.specs):
            raise ValueError('Task metric identity/unit is absent from the frozen specification schema')
    seeds = settings['seeds']
    train = [t for t in tasks if t.partition == 'train']
    validation = [t for t in tasks if t.partition == 'validation']
    test = [t for t in tasks if t.partition == 'test']
    models, methods, validation_models = benchmark_models(settings)
    frozen = dict(**settings, origin=origin, methods=tuple(methods), planned_calls=planned,
                  models={k: asdict(v) for k, v in models.items()}, provenance=provenance,
                  method_models={k: dict(model=v[0], phase=v[1]) for k, v in methods.items()},
                  validation_models=validation_models,
                  capacity_control='common width/depth; report actual actor+Q1+Q2 parameters, not parameter matched',
                  source_sha256=source_digest(), adaptation='fresh optimizers/replay; copied weights and alpha',
                  validation='frozen diagnostic only; no model/hyperparameter selection',
                  frozen_policy='deterministic mean, no parameter updates',
                  budget_unit=('one analytic toy evaluation including reset, no cache/retries' if origin == 'synthetic'
                               else 'one nominal candidate package including reset, no cache/retries'),
                  resolved_spec_schema=asdict(spec_schema),
                  source_task_order=[t.id for t in train],
                  source_sampling='sequential episodes; one shared learner/replay per encoder and seed',
                  normalizer='fixed physical references; no data fitting', stop_on_success=False)
    protocol_sha = freeze_protocol(directory / 'protocol.json', tasks, frozen)
    report = {} if report is None else report
    report.update(origin=origin, protocol_sha256=protocol_sha, completed=False, phases=[], methods=tuple(methods),
                  models={k: asdict(v) for k, v in models.items()},
                  calls=0, planned_calls=planned, real_simulation_calls=0, synthetic_calls=0,
                  automatic_retries=0, cache_hits=0, pretraining_costs=[], test_runs=[],
                  validation_used_for_selection=False)
    started = perf_counter()
    execution_seeds = seeds if _execution_seeds is None else _execution_seeds
    if max_workers > 1:
        from .parallel import run_seeds
        return run_seeds(tasks, env_factory, directory, origin=origin, settings=settings,
                         provenance=provenance, report=report, baseline_check=baseline_check,
                         recorder=recorder, limits=limits, max_workers=max_workers, progress=progress)

    def fresh(model, seed, phase, task_ids):
        seed_all(seed)
        return SACLearner(experiment=dict(origin=origin, split=phase, designs=task_ids,
                                         protocol_sha256=protocol_sha), model_config=models[model],
                          spec_schema=spec_schema)

    def execute(task, method, steps, **kwargs):
        if report['calls'] + 1 + steps > settings['max_calls']:
            raise RuntimeError('Global call budget exhausted before environment creation')
        env = None
        phase_recorder = checkpoints = update_recorder = None
        run_id = None
        primary = None
        try:
            if recorder is not None:
                from analog_optimizer.recording import RunRecorder, UpdateAggregator
                from analog_optimizer.recording.checkpoint import CheckpointManager
                run_id = recorder.store.call('run', dict(parent_run_id=recorder.run_id,
                    parent_configuration_asset_id=recorder.store.call('read', 'run', recorder.run_id)['config_id'],
                    protocol_sha256=protocol_sha, task=task.id, method=method, seed=kwargs['seed'], phase=kwargs['phase']))
                phase_recorder = RunRecorder(recorder.store, run_id, worker_id=f"seed-{kwargs['seed']}", phase=kwargs['phase'])
                config = recorder.store.call('configuration')
                if kwargs.get('replay') is not None:
                    checkpoints = CheckpointManager(recorder.store, run_id, recorder.store.call('recording_root'),
                                                    interval=config['checkpoint_interval'])
                    update_recorder = UpdateAggregator(recorder.store, run_id, interval=config['update_interval'])
            if phase_recorder is None:
                env = env_factory(task, steps, directory / 'environments')
            else:
                env = env_factory.create_recorded(task, steps, directory / 'environments', phase_recorder)
            check = (baseline_check.for_task(task) if hasattr(baseline_check, 'for_task')
                     else baseline_check)
            summary = run_episode(env, task, method, batch_size=settings['batch_size'],
                                  baseline_check=check, history_limit=limits.history_limit,
                                  checkpoints=checkpoints, update_recorder=update_recorder, **kwargs)
            if phase_recorder is not None:
                summary['recording_run_id'] = phase_recorder.run_id
        except BaseException as exc:
            primary = exc
            path = None if env is None else env.directory / 'run.json'
            if task.partition == 'test' and path is not None and path.exists():
                report['test_runs'].append(json.loads(path.read_text()))
            raise
        finally:
            handling_error = primary is not None
            if env is not None:
                report['calls'] += env.simulation_calls
            def collect_summary():
                if env is None:
                    return
                path = env.directory / 'run.json'
                if path.exists():
                    row = json.loads(path.read_text())
                    if phase_recorder is not None:
                        row['recording_run_id'] = phase_recorder.run_id
                    report['phases'].append(row)
            # Cleanup attempts are independent and never replace a training error.
            cleanup = []
            if update_recorder is not None:
                cleanup.append(update_recorder.flush)
            if run_id is not None:
                cleanup.append(lambda: recorder.store.call('end_run', run_id))
            cleanup.append(collect_summary)
            cleanup.append(lambda: write_record(directory / 'report.json', report))
            for operation in cleanup:
                try:
                    operation()
                except BaseException as exc:
                    if primary is None:
                        primary = exc
                    else:
                        report.setdefault('cleanup_errors', []).append(str(exc))
            if primary is not None and not handling_error:
                raise primary
        progress(f'{task.id} {method} seed={kwargs["seed"]}: calls={report["calls"]}/{planned}, '
                 f'success={summary["success"]}, updates={summary["updates"]}')
        return summary

    try:
        for seed in execution_seeds:
            sources, costs = {}, {}
            for model in models:
                source = fresh(model, seed, 'pretrain', [t.id for t in train])
                replay = ReplayBuffer(origin=origin, seed=seed, store=None if recorder is None else recorder.store)
                phases = []
                for i, task in enumerate(train):
                    phases.append(execute(task, model+'_pretrain', settings['pretrain_steps'],
                                          learner=source, replay=replay, seed=(seed+i) % 2**32, phase='pretrain'))
                source.save(directory / f'{model}-{seed}-pretrain.pt', replay,
                            run_state=dict(phase='pretrain', tasks=[t.id for t in train],
                                           protocol_sha256=protocol_sha, seed=seed))
                costs[model] = dict(model=model, seed=seed, calls=sum(p['calls'] for p in phases),
                                    tasks=[t.id for t in train],
                                    circuit_classes=sorted({t.circuit_class for t in train if t.circuit_class}),
                                    wall_seconds=sum(p['wall_seconds'] for p in phases), updates=source.updates,
                                    parameters=sum(p.numel() for module in (source.actor, source.critics)
                                                   for p in module.parameters()), weight_sha256=weight_digest(source))
                report['pretraining_costs'].append(costs[model])
                sources[model] = source
            for task in validation:
                for model in validation_models:
                    execute(task, model+'_validation_frozen', 1, learner=sources[model], seed=seed, phase='frozen')
            for task in test:
                for method, (model, phase) in methods.items():
                    learner, replay, checkpoint = None, None, None
                    if model is not None:
                        learner = fresh(model, seed, phase, [task.id])
                        if phase != 'scratch':
                            transfer_weights(sources[model], learner)
                        if phase != 'frozen':
                            replay = ReplayBuffer(origin=origin, seed=seed, store=None if recorder is None else recorder.store)
                            checkpoint = directory / f'{task.id}-{method}-{seed}.pt'
                    row = execute(task, method, settings['test_steps'], learner=learner, replay=replay,
                                  seed=seed, phase=phase, checkpoint=checkpoint)
                    row['upfront_cost'] = costs[model] if phase != 'scratch' and learner else None
                    row['marginal_online_calls'] = row['calls']
                    row['pretraining_plus_online_calls'] = row['calls'] + (costs[model]['calls'] if row['upfront_cost'] else 0)
                    report['test_runs'].append(row)
            for model, source in sources.items():
                if weight_digest(source) != costs[model]['weight_sha256']:
                    raise RuntimeError('Source model changed during held-out evaluation')
        report['completed'] = True
    except BaseException as exc:
        report.update(exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        finished = {(r['task'], r['method'], r['seed']) for r in report['test_runs']}
        report['unexecuted_test_runs'] = [dict(task=t.id, method=m, seed=s) for t in test
                                         for m in methods for s in execution_seeds if (t.id, m, s) not in finished]
        report['cost_by_partition'] = {part: dict(calls=sum(r['calls'] for r in report['phases'] if r['partition'] == part),
                                                  wall_seconds=sum(r['wall_seconds'] for r in report['phases'] if r['partition'] == part))
                                       for part in ('train', 'validation', 'test')}
        report.update(aggregate=aggregate_runs(report['test_runs']), elapsed_seconds=perf_counter()-started,
                      real_simulation_calls=report['calls'] if origin == 'real' else 0,
                      synthetic_calls=report['calls'] if origin == 'synthetic' else 0)
        write_report_preserving_error(directory / 'report.json', report)
    return report
