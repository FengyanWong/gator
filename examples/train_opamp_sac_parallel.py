"""Train SAC with serial native CDF preparation and at most four Spectre workers."""
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

from opamp_connection import add_connection_arguments, configure
from analog_optimizer.training.runtime import RunResources, add_runtime_arguments, limits_from_args
from analog_optimizer.training.recovery import parallel_state, restore_parallel, RUN
from save_recording_summary import add_summary_to_report


def positive(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return result


def prepare_training(args, directory):
    config, profile = configure(args)
    from analog_optimizer.backends.provenance import content_hash, profile_contract
    from analog_optimizer.backends.conditions import SimulationCondition
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.parallel import NativeEnvironmentFactory
    reference = json.loads(args.reference_measurements.read_text())
    if reference['origin'] != 'real':
        raise ValueError('Real baseline measurements required')
    specs = tuple(MetricSpec(**row) for row in json.loads(args.specs.read_text())['specs'])
    factory = NativeEnvironmentFactory(config, profile, specs, directory,
                                      args.steps_per_episode, args.timeout_seconds, reference['metrics'])
    parameter_contract = dict(profile_sha256=profile_contract(profile),
                              groups=[asdict(g) for g in profile.optimization_graph().parameter_groups])
    experiment = dict(origin='real', split='single-design-nominal-parallel-training-no-heldout-evaluation',
                      preparation='actual-candidate-cdf-native-export',
                      designs=[dict(library=config.library, model_file=config.model_file, **parameter_contract)],
                      specs=[asdict(s) for s in specs], condition=asdict(SimulationCondition(profile.nominal_corner)),
                      reference_measurements_sha256=content_hash(reference),
                      seed=args.seed, max_steps=args.steps_per_episode,
                      max_workers=args.max_workers, batch_size=args.batch_size, warmup=args.warmup)
    model_config = ModelConfig(hidden_dim=32, heads=4, layers=2, encoder_type=args.encoder)
    return factory, experiment, model_config, {}, dict(
        assets={'parameter_contract_asset_id': ('pdk_parameter_contract', parameter_contract),
                'specifications_asset_id': ('specifications', json.loads(args.specs.read_text()))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_arguments(parser)
    parser.add_argument('--max-workers', type=positive, choices=range(1, 5), default=4,
                        help='Maximum simultaneous Spectre jobs; one isolated process per active environment')
    parser.add_argument('--episodes', type=positive, default=4, help='Total episodes across all workers')
    parser.add_argument('--steps-per-episode', type=positive, default=8)
    parser.add_argument('--batch-size', type=positive, default=8)
    parser.add_argument('--warmup', type=int, default=8)
    parser.add_argument('--timeout-seconds', type=float, default=120)
    parser.add_argument('--seed', type=int, default=20260919)
    parser.add_argument('--encoder', choices=('graph_transformer', 'rgcn', 'gatv2'),
                        default='graph_transformer')
    parser.add_argument('--specs', type=Path, default=ROOT / 'configs/gpdk045_opamp_smoke_specs.json')
    parser.add_argument('--reference-measurements', type=Path, required=True)
    parser.add_argument('--resume', type=Path, help='Trusted completed-round/run checkpoint; adds fresh episodes')
    add_runtime_arguments(parser)
    args = parser.parse_args()
    if args.warmup < 0:
        parser.error('--warmup must be nonnegative')
    limits = limits_from_args(args)
    import torch
    from analog_optimizer.envs.sizing import write_record
    from analog_optimizer.training.parallel import collect_parallel_episodes
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.sac import SACLearner, SACConfig
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    directory = args.output.resolve() / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    factory, experiment, model_config, metadata, recording = prepare_training(args, directory)
    report = dict(passed=False, origin=experiment['origin'], experiment=experiment, model_config=asdict(model_config),
                  simulation_budget=args.episodes * (args.steps_per_episode + 1),
                  preparation_simulation_calls=0,
                  note='Serial native CDF preparation, parallel Spectre; resume starts fresh episodes.')
    with RunResources(report, directory / 'report.json', recording_root=args.recording_root,
                      recording_config=args.recording_config, cleanup_seconds=limits.shutdown_seconds,
                      summary_export=add_summary_to_report) as resources:
        resources.start(ROOT, dict(experiment=experiment, model_config=asdict(model_config),
                                  algorithm_config=asdict(SACConfig()), **metadata), **recording)
        completed_before = calls_before = 0
        if args.resume:
            learner, replay, state = SACLearner.load(args.resume, experiment=experiment,
                                                    model_config=model_config, store=resources.store)
            state = restore_parallel(state, rng)
            completed_before, calls_before = state['completed_episodes'], state['simulation_calls']
            report.update(resumed_from=str(args.resume), resume_boundary=state['boundary'],
                          recovery='fresh episodes; learner/replay restored to checkpoint position')
        else:
            learner = SACLearner(experiment=experiment, model_config=model_config)
            replay = ReplayBuffer(origin=experiment['origin'], capacity=10000, seed=args.seed, store=resources.store)
        report.update(completed_episodes_before=completed_before, simulation_calls_before=calls_before)
        write_record(directory / 'config.json', report)
        def progress(current):
            write_record(directory / 'progress.json', current)
            print(f'Candidates: {current["stages_count"]}; SAC updates: {learner.updates}', flush=True)
        collect_parallel_episodes(factory, learner, replay, rng, max_workers=args.max_workers,
                                  episodes=args.episodes, warmup=args.warmup, batch_size=args.batch_size,
                                  report=report, progress=progress, recorder=resources.recorder,
                                  checkpoints=resources.checkpoints, update_recorder=resources.updates,
                                  limits=limits, completed_before=completed_before, calls_before=calls_before)
        state = parallel_state(rng, report, completed_before=completed_before,
                               calls_before=calls_before, boundary=RUN)
        checkpoint = directory / 'checkpoint.pt'
        if resources.checkpoints is None:
            learner.save(checkpoint, replay, run_state=state)
        else:
            checkpoint = resources.checkpoints.maybe_save(learner, replay, replay.insertions,
                                                          run_state=state, force=True)
            resources.checkpoints.policy(learner, replay.insertions)
        report.update(checkpoint=str(checkpoint), total_simulation_calls=state['simulation_calls'],
                      total_completed_episodes=state['completed_episodes'],
                      recorded_steps=report['stages_count'], recorded_resets=report['resets_count'])
    print('REPORT', directory / 'report.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
