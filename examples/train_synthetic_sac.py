"""M4 CPU acceptance: two toy circuits, one group SAC, and exact checkpoint continuation."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import random
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import torch

from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv, write_record
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ENCODER_TYPES, ModelConfig
from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.runner import collect_episode
from analog_optimizer.training.sac import SACLearner, SACConfig
from analog_optimizer.training.runtime import RunResources, add_runtime_arguments, limits_from_args
from analog_optimizer.training.workers import append_history
from save_recording_summary import add_summary_to_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/m4-synthetic')
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--episodes', type=int, default=6, help='Episodes per topology in this invocation')
    parser.add_argument('--steps', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--encoder', choices=ENCODER_TYPES, default='graph_transformer')
    parser.add_argument('--resume', type=Path, help='Trusted checkpoint; resumes at a fresh episode boundary')
    add_runtime_arguments(parser)
    args = parser.parse_args()
    if min(args.episodes, args.steps, args.batch_size) < 1:
        parser.error('Episode, step and batch budgets must be positive')
    if args.episodes * args.steps * 2 < args.batch_size:
        parser.error('This acceptance needs enough new transitions for one mixed batch')
    limits = limits_from_args(args)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    model_config = ModelConfig(hidden_dim=32, heads=4, layers=2, encoder_type=args.encoder)
    graphs, manifests = [], []
    for name in ('opamp', 'ldo'):
        netlist, config = ROOT / f'tests/fixtures/synthetic/{name}.scs', ROOT / f'configs/{name}.json'
        graphs.append(SpectreParser(ParserConfig.from_file(config)).parse_file(netlist))
        manifests.append({'fixture': name, 'netlist_sha256': hashlib.sha256(netlist.read_bytes()).hexdigest(),
                          'mapping_sha256': hashlib.sha256(config.read_bytes()).hexdigest()})
    experiment = dict(origin='synthetic', split='training-only-plumbing', designs=manifests,
                      models_sha256=hashlib.sha256((ROOT / 'configs/synthetic_models.json').read_bytes()).hexdigest(),
                      seed=args.seed, steps=args.steps, batch_size=args.batch_size,
                      toy_targets={'w': .4, 'c': -.3}, score_targets=[.95, .98])
    run_state = {'completed_episodes': 0, 'synthetic_calls': 0}
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    report = dict(passed=False, origin='synthetic', seed=args.seed, experiment=experiment, stages=[],
                  real_simulation_calls=0, checkpoint=str(directory / 'checkpoint.pt'),
                  note='Analytic toy functions; no electrical solver or optimization-performance claim.')
    started = perf_counter()
    environments = []
    with RunResources(report, directory / 'report.json', recording_root=args.recording_root,
                      recording_config=args.recording_config, cleanup_seconds=limits.shutdown_seconds,
                      summary_export=add_summary_to_report) as resources:
        resources.start(ROOT, dict(experiment=experiment, model_config=asdict(model_config),
                                  algorithm_config=asdict(SACConfig()), pdk='synthetic'),
                        project_files=['configs/opamp.json', 'configs/ldo.json', 'configs/synthetic_models.json'],
                        templates={name: (ROOT / f'tests/fixtures/synthetic/{name}.scs').read_text() for name in ('opamp', 'ldo')})
        store, recorder, checkpoints, update_recorder = resources.store, resources.recorder, resources.checkpoints, resources.updates
        if args.resume:
            learner, replay, run_state = SACLearner.load(args.resume, experiment=experiment, model_config=model_config, store=store)
            for key in ('completed_episodes', 'synthetic_calls'):
                if type(run_state.get(key)) is not int or run_state[key] < 0:
                    raise ValueError(f'Checkpoint missing cumulative counter: {key}')
            rng.setstate(run_state['collector_rng'])
        else:
            learner = SACLearner(experiment=experiment, model_config=model_config)
            replay = ReplayBuffer(origin='synthetic', seed=args.seed, capacity=10000, store=store)
        with ExitStack() as stack:
            for i, graph in enumerate(graphs):
                backend = SyntheticSizingBackend(graph, targets=experiment['toy_targets'])
                env = CircuitSizingEnv(backend, graph,
                    [MetricSpec('score', 'fixture', 'min', 1, lower=experiment['score_targets'][i])],
                    directory / 'environments', max_steps=args.steps, stop_on_success=False,
                    expected_origin='synthetic',
                    recorder=None if recorder is None else replace(recorder, worker_id=str(i)))
                environments.append(stack.enter_context(env))
            for _ in range(args.episodes):
                for i, env in enumerate(environments):
                    before_calls = env.simulation_calls
                    rows = collect_episode(env, learner, replay, rng, batch_size=args.batch_size,
                                           checkpoints=checkpoints, update_recorder=update_recorder,
                                           run_state=run_state, history_limit=limits.history_limit)
                    append_history(report, 'stages', {'fixture': manifests[i]['fixture'],
                                   'steps': rows if store is None else env.steps},
                                   limits.history_limit if store is not None else None)
                    run_state['completed_episodes'] += 1
                    run_state['synthetic_calls'] += env.simulation_calls - before_calls
                print(json.dumps({'episodes': run_state['completed_episodes'], 'replay': len(replay),
                                  'updates': learner.updates}), flush=True)
        report['restored'] = all(json.loads((env.directory / 'restoration.json').read_text())['state'] == 'restored'
                                 for env in environments)
        calls = sum(env.simulation_calls for env in environments)
        run_state.update(collector_rng=rng.getstate(), boundary='completed_run')
        checkpoint = directory / 'checkpoint.pt'
        if checkpoints is None:
            learner.save(checkpoint, replay, run_state=run_state)
        else:
            checkpoint = checkpoints.maybe_save(learner, replay, replay.insertions, run_state=run_state, force=True)
            checkpoints.policy(learner, replay.insertions)
            update_recorder.flush()
            report.update(checkpoint=str(checkpoint))
        report.update(synthetic_calls_this_run=calls, total_synthetic_calls=run_state['synthetic_calls'],
                      replay_size=len(replay), training_updates=learner.updates,
                      action_counts=[len(env.mapper.groups) for env in environments])
        # Probe on disposable in-memory learners; saved training checkpoint stays at the episode boundary.
        expected = learner.update(replay.sample(args.batch_size))
        restored, saved_replay, _ = SACLearner.load(checkpoint, experiment=experiment,
                                                  model_config=model_config, store=store)
        actual = restored.update(saved_replay.sample(args.batch_size))
        tensors_match = all(torch.equal(a, b) for a, b in zip(
            list(learner.actor.parameters()) + list(learner.critics.parameters()) + list(learner.targets.parameters()),
            list(restored.actor.parameters()) + list(restored.critics.parameters()) + list(restored.targets.parameters())))
        report['exact_resume'] = expected == actual and tensors_match and torch.equal(learner.log_alpha, restored.log_alpha)
        report['passed'] = report['restored'] and report['exact_resume'] and learner.updates > 1
        if not report['passed']:
            raise RuntimeError('M4 synthetic acceptance failed')
        report['elapsed_seconds'] = perf_counter() - started
    print('REPORT', directory / 'report.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
