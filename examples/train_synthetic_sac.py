"""M4 CPU acceptance: two toy circuits, one group SAC, and exact checkpoint continuation."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
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
from analog_optimizer.training.sac import SACLearner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/local/m4-synthetic')
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--episodes', type=int, default=6, help='Episodes per topology in this invocation')
    parser.add_argument('--steps', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--encoder', choices=ENCODER_TYPES, default='graph_transformer')
    parser.add_argument('--resume', type=Path, help='Trusted checkpoint; resumes at a fresh episode boundary')
    args = parser.parse_args()
    if min(args.episodes, args.steps, args.batch_size) < 1:
        parser.error('Episode, step and batch budgets must be positive')
    if args.episodes * args.steps * 2 < args.batch_size:
        parser.error('This acceptance needs enough new transitions for one mixed batch')
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
    if args.resume:
        learner, replay, run_state = SACLearner.load(args.resume, experiment=experiment, model_config=model_config)
        rng.setstate(run_state['collector_rng'])
    else:
        learner = SACLearner(experiment=experiment, model_config=model_config)
        replay = ReplayBuffer(origin='synthetic', seed=args.seed, capacity=10000)
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True)
    report = dict(passed=False, origin='synthetic', seed=args.seed, experiment=experiment, stages=[],
                  real_simulation_calls=0, checkpoint=str(directory / 'checkpoint.pt'),
                  note='Analytic toy functions; no electrical solver or optimization-performance claim.')
    started = perf_counter()
    environments = []
    try:
        with ExitStack() as stack:
            for i, graph in enumerate(graphs):
                backend = SyntheticSizingBackend(graph, targets=experiment['toy_targets'])
                env = CircuitSizingEnv(backend, graph,
                    [MetricSpec('score', 'fixture', 'min', 1, lower=experiment['score_targets'][i])],
                    directory / 'environments', max_steps=args.steps, stop_on_success=False,
                    expected_origin='synthetic')
                environments.append(stack.enter_context(env))
            for _ in range(args.episodes):
                for i, env in enumerate(environments):
                    rows = collect_episode(env, learner, replay, rng, batch_size=args.batch_size)
                    report['stages'].append({'fixture': manifests[i]['fixture'], 'steps': rows})
                    run_state['completed_episodes'] += 1
                print(json.dumps({'episodes': run_state['completed_episodes'], 'replay': len(replay),
                                  'updates': learner.updates}), flush=True)
        report['restored'] = all(json.loads((env.directory / 'restoration.json').read_text())['state'] == 'restored'
                                 for env in environments)
        calls = sum(env.simulation_calls for env in environments)
        run_state.update(synthetic_calls=run_state['synthetic_calls'] + calls, collector_rng=rng.getstate())
        learner.save(directory / 'checkpoint.pt', replay, run_state=run_state)
        report.update(synthetic_calls_this_run=calls, total_synthetic_calls=run_state['synthetic_calls'],
                      replay_size=len(replay), training_updates=learner.updates,
                      action_counts=[len(env.mapper.groups) for env in environments])
        # Probe on disposable in-memory learners; saved training checkpoint stays at the episode boundary.
        expected = learner.update(replay.sample(args.batch_size))
        restored, saved_replay, _ = SACLearner.load(directory / 'checkpoint.pt', experiment=experiment,
                                                  model_config=model_config)
        actual = restored.update(saved_replay.sample(args.batch_size))
        tensors_match = all(torch.equal(a, b) for a, b in zip(
            list(learner.actor.parameters()) + list(learner.critics.parameters()) + list(learner.targets.parameters()),
            list(restored.actor.parameters()) + list(restored.critics.parameters()) + list(restored.targets.parameters())))
        report['exact_resume'] = expected == actual and tensors_match and torch.equal(learner.log_alpha, restored.log_alpha)
        report['passed'] = report['restored'] and report['exact_resume'] and learner.updates > 1
        if not report['passed']:
            raise RuntimeError('M4 synthetic acceptance failed')
    except BaseException as exc:
        report.update(passed=False, exception_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        report['synthetic_calls_this_run'] = sum(env.simulation_calls for env in environments)
        report['elapsed_seconds'] = perf_counter() - started
        write_record(directory / 'report.json', report)
        print('REPORT', directory / 'report.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
