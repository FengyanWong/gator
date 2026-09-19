"""Train nominal SAC with a verified finite CDF table and bounded Spectre workers."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from build_opamp_cdf_table import add_connection_arguments, configure


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--cdf-table', type=Path, required=True)
    parser.add_argument('--max-workers', type=positive, required=True,
                        help='Maximum simultaneous Spectre jobs; one isolated process per active environment')
    parser.add_argument('--episodes', type=positive, default=4, help='Total episodes across all workers')
    parser.add_argument('--steps-per-episode', type=positive, default=8)
    parser.add_argument('--batch-size', type=positive, default=8)
    parser.add_argument('--warmup', type=int, default=8)
    parser.add_argument('--timeout-seconds', type=float, default=120)
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--encoder', choices=('graph_transformer', 'mlp', 'gcn', 'rgcn', 'gat', 'port_gnn'),
                        default='graph_transformer')
    parser.add_argument('--specs', type=Path, default=ROOT / 'configs/gpdk045_opamp_smoke_specs.json')
    parser.add_argument('--reference-measurements', type=Path, required=True)
    parser.add_argument('--resume', type=Path, help='Trusted checkpoint from a completed parallel run; adds episodes')
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error('--warmup must be nonnegative')
    config, profile = configure(args)
    import torch
    from analog_optimizer.backends.cdf_table import CdfTable, content_hash
    from analog_optimizer.envs.sizing import write_record
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.parallel import TableEnvironmentFactory, collect_parallel_episodes
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.sac import SACLearner
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    table = CdfTable(args.cdf_table, profile, model_file=config.model_file)
    reference = json.loads(args.reference_measurements.read_text())
    if reference['origin'] != 'real':
        raise ValueError('Real baseline measurements required')
    specs = tuple(MetricSpec(**row) for row in json.loads(args.specs.read_text())['specs'])
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    factory = TableEnvironmentFactory(config, profile, args.cdf_table.resolve(), specs, directory,
                                      args.steps_per_episode, args.timeout_seconds, reference['metrics'])
    experiment = dict(origin='real', split='single-design-nominal-parallel-training-no-heldout-evaluation',
                      designs=[dict(library=config.library, table_sha256=table.data['sha256'],
                                    model_file=config.model_file, pdk=table.data['pdk'])],
                      specs=[asdict(s) for s in specs], condition=table.data['condition'],
                      reference_measurements_sha256=content_hash(reference),
                      seed=args.seed, max_steps=args.steps_per_episode,
                      max_workers=args.max_workers, batch_size=args.batch_size, warmup=args.warmup)
    model_config = ModelConfig(hidden_dim=32, heads=4, layers=2, encoder_type=args.encoder)
    completed_before = calls_before = 0
    if args.resume:
        learner, replay, state = SACLearner.load(args.resume, experiment=experiment, model_config=model_config)
        if state.get('boundary') != 'completed_parallel_run':
            raise ValueError('Resume requires a completed-run boundary; failed/in-flight workers cannot be resumed')
        rng.setstate(state['collector_rng'])
        completed_before, calls_before = state['completed_episodes'], state['simulation_calls']
    else:
        learner = SACLearner(experiment=experiment, model_config=model_config)
        replay = ReplayBuffer(origin='real', capacity=10000, seed=args.seed)
    report = dict(passed=False, origin='real', experiment=experiment, model_config=asdict(model_config),
                  simulation_budget=args.episodes * (args.steps_per_episode + 1),
                  preparation_simulation_calls=0, training_virtuoso_calls=0,
                  completed_episodes_before=completed_before, simulation_calls_before=calls_before,
                  note='Finite-table nominal training; concurrency is not evidence of convergence or speedup.')
    write_record(directory / 'config.json', report)
    try:
        def progress(current):
            write_record(directory / 'progress.json', current)
            print(f'Candidates: {len(current["stages"])}; SAC updates: {learner.updates}', flush=True)
        collect_parallel_episodes(factory, learner, replay, rng, max_workers=args.max_workers,
                                  episodes=args.episodes, warmup=args.warmup, batch_size=args.batch_size,
                                  report=report, progress=progress)
        checkpoint = directory / 'checkpoint.pt'
        learner.save(checkpoint, replay, run_state=dict(
            boundary='completed_parallel_run', collector_rng=rng.getstate(),
            completed_episodes=completed_before + report['completed_episodes'],
            simulation_calls=calls_before + report['simulation_calls']))
        report['checkpoint'] = str(checkpoint)
    finally:
        write_record(directory / 'report.json', report)
        print('REPORT', directory / 'report.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
