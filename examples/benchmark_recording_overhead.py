"""Paired offline timing: existing JSON path vs SQLite, plus replay-readback ablation.

All variants run identical injected MockBackend evaluations and seeded SAC updates.
The JSON baseline is the existing recorder=None path, not a no-I/O simulator.
No Spectre/SSH; no estimate here is a measurement of real simulation overhead.
"""
import argparse
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from benchmark_recording import InjectedSizingMock
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ModelConfig
from analog_optimizer.netlist.config import ParserConfig
from analog_optimizer.netlist.spectre_parser import SpectreParser
from analog_optimizer.recording import ExperimentStore, RecordingConfig, RunRecorder
from analog_optimizer.recording.checkpoint import CheckpointManager, atomic_torch_save
from analog_optimizer.recording.codec import raw
from analog_optimizer.recording.session import transition_from_data
from analog_optimizer.recording.setup import create_run
from analog_optimizer.recording.space import disk_bytes, filesystem
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.sac import SACConfig, SACLearner


MODES = ('legacy_json', 'sqlite_full_readback', 'sqlite')


class FullReadbackReplay(ReplayBuffer):
    """Prior admission implementation, isolated from all other recorder changes."""
    def _verify_persistence(self, transition):
        persisted = transition_from_data(self.store.call('read', 'transition', transition.candidate_id), validate=False)
        if raw(vars(persisted)) != raw(vars(transition)):
            raise ValueError('Replay differs from durable transition')


def distribution(seconds):
    ordered = sorted(seconds)
    return dict(count=len(ordered), total_seconds=sum(ordered), mean_ms=1000 * statistics.mean(ordered),
                median_ms=1000 * statistics.median(ordered), p95_ms=1000 * ordered[math.ceil(.95 * len(ordered)) - 1]) if ordered else dict(count=0, total_seconds=0)


def trial(root, mode, evaluations, *, seed=19, update_every=10, checkpoint_interval=500):
    import numpy as np
    import torch
    from dataclasses import asdict
    root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    rng = random.Random(seed)
    graph = SpectreParser(ParserConfig.from_file(ROOT / 'configs/opamp.json')).parse_file(ROOT / 'tests/fixtures/synthetic/opamp.scs')
    config = RecordingConfig(checkpoint_interval=checkpoint_interval)
    model = ModelConfig(hidden_dim=32, heads=4, layers=2)
    learner = SACLearner(experiment=dict(origin='synthetic', split='recording-timing', designs=['mock-opamp']), model_config=model)
    backend = InjectedSizingMock(graph)
    timings = {key: [] for key in ('evaluation', 'transition_construction', 'replay_admission', 'update', 'checkpoint')}
    trace = hashlib.sha256()
    steps = 0
    last_checkpoint = 0
    saved_paths = []
    storage = ExperimentStore(root, config) if mode != 'legacy_json' else None
    with storage if storage is not None else nullcontext():
        run = create_run(storage, ROOT, dict(origin='mock', seed=seed, model_config=asdict(model),
                         algorithm_config=asdict(SACConfig()), update_every=update_every),
                         project_files=['configs/opamp.json'], templates={'mock': 'injected; no physics'}) if storage else None
        recorder = RunRecorder(storage, run) if storage else None
        replay_cls = FullReadbackReplay if mode == 'sqlite_full_readback' else ReplayBuffer
        replay = replay_cls(capacity=256, origin='synthetic', seed=seed, store=storage)
        manager = CheckpointManager(storage, run, root, interval=checkpoint_interval) if storage else None

        def checkpoint(force=False):
            nonlocal last_checkpoint
            if not force and steps - last_checkpoint < checkpoint_interval:
                return
            tick = time.perf_counter()
            if manager:
                manager.maybe_save(learner, replay, steps, force=force, run_state={'collector_rng': rng.getstate()})
            else:
                path = root / 'checkpoints' / f'full-{steps}.pt'
                learner.save(path, replay, run_state={'env_steps': steps, 'collector_rng': rng.getstate()})
                saved_paths.append(path)
                for old in saved_paths[:-2]:
                    old.unlink(missing_ok=True)
                del saved_paths[:-2]
            timings['checkpoint'].append(time.perf_counter() - tick)
            last_checkpoint = steps

        with CircuitSizingEnv(backend, graph, [MetricSpec('score', 'fixture', 'min', 1., lower=.95)],
                              root / 'collector', max_steps=199, stop_on_success=False,
                              expected_origin='synthetic', recorder=recorder) as env:
            setup_seconds = time.perf_counter() - started
            loop_start = time.perf_counter()
            observation = None
            while backend.calls < evaluations:
                reset = env._done
                proposal = None if reset else {key: rng.uniform(-1, 1) for key in env.mapper.group_ids}
                tick = time.perf_counter()
                if reset:
                    following, info = env.reset()
                    reward, terminated, truncated = None, info['terminated'], info['truncated']
                else:
                    step = env.step(proposal)
                    following, reward, terminated, truncated, info = step
                    steps += 1
                timings['evaluation'].append(time.perf_counter() - tick)
                trace.update(raw(dict(proposal=proposal, reward=reward, terminated=terminated, truncated=truncated,
                    status=info['status'], eligible=info['replay_eligible'], parameters=backend.read_parameters(),
                    metrics=None if following is None else following.metrics,
                    validity=None if following is None else following.metric_validity,
                    remaining=None if following is None else following.remaining_steps)))
                if not reset:
                    if info['replay_eligible']:
                        tick = time.perf_counter()
                        transition = Transition.from_step(observation, proposal, step)
                        timings['transition_construction'].append(time.perf_counter() - tick)
                        tick = time.perf_counter()
                        replay.add(transition)
                        timings['replay_admission'].append(time.perf_counter() - tick)
                    if steps % update_every == 0 and len(replay) >= 8:
                        tick = time.perf_counter()
                        learner.update(replay.sample(8))
                        timings['update'].append(time.perf_counter() - tick)
                    checkpoint()
                observation = following
            loop_seconds = time.perf_counter() - loop_start
        checkpoint(force=True)
        tick = time.perf_counter()
        if manager:
            manager.policy(learner, steps)
        else:
            atomic_torch_save(dict(actor=learner.actor.state_dict(), contract=learner.contract()), root / 'checkpoints/final_policy.pt')
        timings['checkpoint'].append(time.perf_counter() - tick)
        if storage:
            storage.call('end_run', run)
        # Verify all learned networks, not just the generated action trace.
        learned = hashlib.sha256()
        for network in (learner.actor, learner.critics, learner.targets):
            for name, value in network.state_dict().items():
                learned.update(name.encode())
                learned.update(value.detach().cpu().numpy().tobytes())
        learned.update(learner.log_alpha.detach().cpu().numpy().tobytes())
    total_seconds = time.perf_counter() - started
    return dict(mode=mode, root=str(root), run_id=run, seed=seed, evaluations=backend.calls, env_steps=steps,
                updates=learner.updates, replay_members=len(replay), trace_sha256=trace.hexdigest(), model_sha256=learned.hexdigest(),
                setup_seconds=setup_seconds, loop_seconds=loop_seconds, total_seconds=total_seconds,
                stages={key: distribution(value) for key, value in timings.items()},
                bytes={key: disk_bytes(root / key) for key in ('experiments.sqlite3', 'attachments', 'checkpoints', 'temporary')},
                total_bytes=disk_bytes(root), real_simulations=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--evaluations', type=int, default=600)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--update-every', type=int, default=10)
    parser.add_argument('--checkpoint-interval', type=int, default=500)
    args = parser.parse_args()
    if args.output.exists() or args.evaluations < 2 or min(args.repeats, args.update_every, args.checkpoint_interval) < 1:
        parser.error('Use a new output root, at least 2 evaluations, and positive intervals/repeats')
    args.output.mkdir(parents=True)
    # Warm every path; its cost and calls are excluded from timed trial statistics.
    for mode in MODES:
        trial(args.output / ('warmup-' + mode), mode, 30, update_every=args.update_every,
              checkpoint_interval=args.checkpoint_interval)
    results = []
    for repeat in range(args.repeats):
        order = MODES[repeat % 3:] + MODES[:repeat % 3]
        for mode in order:
            result = trial(args.output / f'{repeat}-{mode}', mode, args.evaluations, seed=19 + repeat,
                           update_every=args.update_every, checkpoint_interval=args.checkpoint_interval)
            results.append(result)
            print(json.dumps(dict(repeat=repeat, mode=mode, seconds=result['total_seconds'])), flush=True)
        paired = results[-3:]
        if any(len({row[key] for row in paired}) != 1 for key in
               ('trace_sha256', 'model_sha256', 'evaluations', 'env_steps', 'updates', 'replay_members')):
            raise RuntimeError('Paired modes changed simulation/learning results')
    medians = {}
    for mode in MODES:
        rows = [row for row in results if row['mode'] == mode]
        medians[mode] = dict(total_seconds=statistics.median(r['total_seconds'] for r in rows),
            loop_ms_per_evaluation=statistics.median(1000 * r['loop_seconds'] / r['evaluations'] for r in rows),
            evaluation_ms=statistics.median(r['stages']['evaluation']['mean_ms'] for r in rows),
            replay_admission_ms=statistics.median(r['stages']['replay_admission'].get('mean_ms', 0) for r in rows),
            checkpoint_mean_ms=statistics.median(r['stages']['checkpoint']['mean_ms'] for r in rows))
    report = dict(format_version='recording-overhead-v1', platform=platform.platform(), python=platform.python_version(),
        sqlite=sqlite3.sqlite_version, filesystem=filesystem(args.output), torch_threads=1,
        evaluations_per_trial=args.evaluations, repeats=args.repeats, update_every=args.update_every,
        checkpoint_interval=args.checkpoint_interval, baseline='existing recorder=None JSON journals and retained backend outputs',
        readback_ablation='same optimized SQLite writer; only replay admission uses previous full reconstruction/comparison',
        warmup_evaluations=90, real_simulations=0, results_identical=True, medians=medians, trials=results)
    delta = medians['sqlite']['loop_ms_per_evaluation'] - medians['legacy_json']['loop_ms_per_evaluation']
    report['sqlite_minus_legacy_loop_ms_per_evaluation'] = delta
    report['sqlite_loop_overhead_percent'] = 100 * delta / medians['legacy_json']['loop_ms_per_evaluation']
    destination = args.report or args.output / 'report.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'trials'}, indent=2))


if __name__ == '__main__':
    main()
