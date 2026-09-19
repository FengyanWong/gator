"""Single-worker M5 experiment runner with isolated replay and fixed budgets."""
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
from analog_optimizer.models import ENCODER_TYPES, ModelConfig
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.sac import SACLearner, source_digest
from .transfer import aggregate_runs, digest, freeze_protocol, summarize_run


METHODS = ('gt_scratch', 'gt_frozen', 'gt_adapt', 'random', 'pattern_search', 'gnn_adapt')
ENCODER_LABELS = dict(graph_transformer='gt', mlp='mlp', rgcn='rgcn', gat='gat', port_gnn='gnn', gcn='gcn')


def benchmark_models(settings):
    """Explicit selections get scratch/frozen/adapt for EVERY encoder.

    Omitted selection retains the six-method M5 protocol and its call budget.
    """
    selected = settings.get('encoders')
    legacy = selected is None
    if legacy:
        selected = ('graph_transformer', 'port_gnn')
    if (not isinstance(selected, (list, tuple)) or not selected
            or any(not isinstance(name, str) or name not in ENCODER_TYPES for name in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('encoders must be a nonempty, unique list of supported encoder types')
    models = {ENCODER_LABELS[name]: ModelConfig(
        encoder_type=name, hidden_dim=settings.get('hidden_dim', 32),
        heads=settings.get('heads', 4), layers=settings.get('layers', 2)) for name in selected}
    names = METHODS if legacy else tuple(f'{key}_{phase}' for key in models
                                         for phase in ('scratch', 'frozen', 'adapt')) + ('random', 'pattern_search')
    methods = {}
    for name in names:
        if name in ('random', 'pattern_search'):
            methods[name] = (None, 'frozen')
        else:
            model, suffix = name.rsplit('_', 1)
            methods[name] = (model, 'adaptation' if suffix == 'adapt' else suffix)
    return models, methods, ('gt',) if legacy else tuple(models)


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
                phase='frozen', warmup=1, checkpoint=None, baseline_check=None):
    seed_all(seed)
    rng = random.Random(seed)
    started = perf_counter()
    records, updates = [], []
    before = weight_digest(learner) if learner else None
    summary = dict(task=task.id, partition=task.partition, transfer=task.transfer, method=method,
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
        row = json.loads(Path(info['record_path']).read_text())
        row['time_from_start_seconds'] = perf_counter() - started
        records.append(row)
        summary['records'].append(info['record_path'])
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
                    step = env.step(proposal)
                    row = record(step[4])
                    row['action_source'] = action_source
                    summary['actions'].append(dict(candidate_id=row['candidate_id'], proposal=proposal,
                                                   source=action_source))
                    search.observe(proposal, step[1])
                    if training and step[4]['replay_eligible']:
                        admit_transition(replay, task, phase, observation, proposal, step)
                        if len(replay) >= batch_size:
                            start = perf_counter()
                            updates.append(learner.update(replay.sample(batch_size)))
                            summary['update_seconds'] += perf_counter() - start
                    observation = step[0]
                    if step[2] or step[3]:
                        break
        summary['completed'] = True
    except BaseException as exc:
        summary.update(exception_type=type(exc).__name__, error=str(exc))
        # Include any journal written before an exception (including charged failed calls).
        recorded = {r['candidate_id'] for r in records}
        for path in sorted((env.directory / 'candidates').glob('*.json')):
            row = json.loads(path.read_text())
            if row['candidate_id'] not in recorded:
                row['time_from_start_seconds'] = perf_counter() - started
                records.append(row)
                summary['records'].append(str(path))
        raise
    finally:
        summary.update(summarize_run(records, calls=env.simulation_calls,
                                     wall_seconds=perf_counter()-started, budget=1+env.max_steps))
        summary.update(updates=len(updates), update_log=updates, weight_before=before,
                       weight_after=weight_digest(learner) if learner else None,
                       replay_insertions=0 if replay is None else replay.insertions)
        restore = env.directory / 'restoration.json'
        summary['restoration'] = json.loads(restore.read_text()) if restore.exists() else {'state': 'unknown'}
        write_record(env.directory / 'run.json', summary)
    if not training and summary['weight_before'] != summary['weight_after']:
        raise RuntimeError('Frozen evaluation changed model weights')
    if checkpoint and training:
        learner.save(checkpoint, replay, run_state=dict(task=task.id, phase=phase, seed=seed,
                                                       simulation_calls=env.simulation_calls, summary=summary))
    return summary


def run_benchmark(tasks, env_factory, directory, *, origin, settings, provenance, progress=print,
                  baseline_check=None):
    """Factory(task, max_steps, output) must return a NEW restorable environment."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    seeds = settings['seeds']
    if (not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
            or any(type(settings[k]) is not int or settings[k] < 1 for k in
                   ('pretrain_steps', 'test_steps', 'batch_size', 'max_calls'))):
        raise ValueError('Invalid seed or call/update budgets')
    if settings['batch_size'] > min(settings['pretrain_steps'], settings['test_steps']):
        raise ValueError('Budget must allow learning in both pretraining and adaptation')
    train = [t for t in tasks if t.partition == 'train']
    validation = [t for t in tasks if t.partition == 'validation']
    test = [t for t in tasks if t.partition == 'test']
    models, methods, validation_models = benchmark_models(settings)
    planned = len(seeds) * (len(models)*len(train)*(1+settings['pretrain_steps']) +
                           2*len(validation_models)*len(validation) +
                           len(methods)*len(test)*(1+settings['test_steps']))
    if planned > settings['max_calls']:
        raise ValueError(f'Planned {planned} calls exceed max_calls={settings["max_calls"]}')
    frozen = dict(**settings, origin=origin, methods=tuple(methods), planned_calls=planned,
                  models={k: asdict(v) for k, v in models.items()}, provenance=provenance,
                  method_models={k: dict(model=v[0], phase=v[1]) for k, v in methods.items()},
                  validation_models=validation_models,
                  capacity_control='common width/depth; report actual actor+Q1+Q2 parameters, not parameter matched',
                  source_sha256=source_digest(), adaptation='fresh optimizers/replay; copied weights and alpha',
                  validation='frozen diagnostic only; no model/hyperparameter selection',
                  frozen_policy='deterministic mean, no parameter updates',
                  budget_unit='one nominal DC/AC candidate package including reset, no cache/retries',
                  normalizer='fixed physical references; no data fitting', stop_on_success=False)
    protocol_sha = freeze_protocol(directory / 'protocol.json', tasks, frozen)
    report = dict(origin=origin, protocol_sha256=protocol_sha, completed=False, phases=[], methods=tuple(methods),
                  models={k: asdict(v) for k, v in models.items()},
                  calls=0, planned_calls=planned, real_simulation_calls=0, synthetic_calls=0,
                  automatic_retries=0, cache_hits=0, pretraining_costs=[], test_runs=[],
                  validation_used_for_selection=False)
    started = perf_counter()

    def fresh(model, seed, phase, task_ids):
        seed_all(seed)
        return SACLearner(experiment=dict(origin=origin, split=phase, designs=task_ids,
                                         protocol_sha256=protocol_sha), model_config=models[model])

    def execute(task, method, steps, **kwargs):
        if report['calls'] + 1 + steps > settings['max_calls']:
            raise RuntimeError('Global call budget exhausted before environment creation')
        env = env_factory(task, steps, directory / 'environments')
        try:
            summary = run_episode(env, task, method, batch_size=settings['batch_size'],
                                  baseline_check=baseline_check, **kwargs)
        except BaseException:
            path = env.directory / 'run.json'
            if task.partition == 'test' and path.exists():
                report['test_runs'].append(json.loads(path.read_text()))
            raise
        finally:
            report['calls'] += env.simulation_calls
            path = env.directory / 'run.json'
            if path.exists():
                report['phases'].append(json.loads(path.read_text()))
            write_record(directory / 'report.json', report)
        progress(f'{task.id} {method} seed={kwargs["seed"]}: calls={report["calls"]}/{planned}, '
                 f'success={summary["success"]}, updates={summary["updates"]}')
        return summary

    try:
        for seed in seeds:
            sources, costs = {}, {}
            for model in models:
                source = fresh(model, seed, 'pretrain', [t.id for t in train])
                replay = ReplayBuffer(origin=origin, seed=seed)
                phases = []
                for i, task in enumerate(train):
                    phases.append(execute(task, model+'_pretrain', settings['pretrain_steps'],
                                          learner=source, replay=replay, seed=(seed+i) % 2**32, phase='pretrain'))
                source.save(directory / f'{model}-{seed}-pretrain.pt', replay,
                            run_state=dict(phase='pretrain', tasks=[t.id for t in train],
                                           protocol_sha256=protocol_sha, seed=seed))
                costs[model] = dict(model=model, seed=seed, calls=sum(p['calls'] for p in phases),
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
                            replay = ReplayBuffer(origin=origin, seed=seed)
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
                                         for m in methods for s in seeds if (t.id, m, s) not in finished]
        report['cost_by_partition'] = {part: dict(calls=sum(r['calls'] for r in report['phases'] if r['partition'] == part),
                                                  wall_seconds=sum(r['wall_seconds'] for r in report['phases'] if r['partition'] == part))
                                       for part in ('train', 'validation', 'test')}
        report.update(aggregate=aggregate_runs(report['test_runs']), elapsed_seconds=perf_counter()-started,
                      real_simulation_calls=report['calls'] if origin == 'real' else 0,
                      synthetic_calls=report['calls'] if origin == 'synthetic' else 0)
        write_record(directory / 'report.json', report)
    return report
