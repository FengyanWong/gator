"""Repeatable timing of one SAC learner step - what the workbench engine records as `update_seconds`.

Not a test (pytest collects only test_*.py). Offline: no simulator, no backend, nothing written to any run.

    OMP_NUM_THREADS=1 PYTHONPATH=src ~/analog-optimizer-venv/bin/python tests/perf/learner_update_profile.py \
        [--checkpoint <save point>/training_state.pt] [--encoders graph_transformer,rgcn,gatv2] [--threads 1] \
        [--updates 100] [--warmup 30] [--wait-load 6 --wait-max 900] [--json out.json]

Fixtures:
- default: the synthetic op-amp replay (16 transitions, origin=synthetic) of the 2026-10-05 performance audit;
- `--checkpoint`: a workbench save point's `training_state.pt` with its embedded replay (for example the recorded
  `mscr_ota7t` Spectre runs of 2026-10-05). Real transitions are much larger than the synthetic ones (41 kB pickled
  vs a few kB), so replay copying and cache keys weigh more there: measure on both.
The input cache is warmed with every replay observation first, as in a live run (the policy batched each observation
when it acted on it). Each encoder is timed twice: once uninstrumented (the step totals) and once with the phases
wrapped (the shares). Resources are explicit and recorded: torch threads, OMP_NUM_THREADS, host load before and after
each arm (`--wait-load` waits for a quiet machine first; see docs/performance-measurement.md).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

import torch  # noqa: E402

from analog_optimizer.graph.pyg_converter import FeatureSchema  # noqa: E402
from analog_optimizer.measurements.specs import RewardSettings  # noqa: E402
from analog_optimizer.models import ModelConfig  # noqa: E402
from analog_optimizer.models.inputs import SpecSchema  # noqa: E402
from analog_optimizer.training.replay import ReplayBuffer, Transition  # noqa: E402
from analog_optimizer.training.sac import SACConfig, SACLearner, source_digest  # noqa: E402

# The workbench's starting presets (src/gator_workbench/network_presets.py, record 7.192).
PRESETS = dict(graph_transformer=dict(hidden_dim=48, heads=4, layers=4),
               rgcn=dict(hidden_dim=32, heads=4, layers=4),
               gatv2=dict(hidden_dim=192, heads=3, layers=4))


def _dataclass(cls, values):
    return cls(**{f.name: (tuple(values[f.name]) if isinstance(values[f.name], list) else values[f.name])
                  for f in dataclasses.fields(cls) if f.name in values})


def synthetic_fixture():
    from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
    from analog_optimizer.envs.sizing import CircuitSizingEnv
    from analog_optimizer.measurements.specs import MetricSpec
    from analog_optimizer.netlist.config import ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    import tempfile
    graph = SpectreParser(ParserConfig.from_file(ROOT / 'configs/opamp.json')).parse_file(
        ROOT / 'tests/fixtures/synthetic/opamp.scs')
    backend = SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3})
    replay = ReplayBuffer(origin='synthetic', seed=41)
    with tempfile.TemporaryDirectory(prefix='learner-profile-') as folder:
        with CircuitSizingEnv(backend, graph, (MetricSpec('score', 'fixture', 'min', 1, lower=.95),), Path(folder),
                              max_steps=16, stop_on_success=False, expected_origin='synthetic') as env:
            observation, _ = env.reset()
            for index in range(16):
                action = {key: -.8 + index * .1 for key in env.mapper.group_ids}
                step = env.step(action)
                replay.add(Transition.from_step(observation, action, step))
                observation = step[0]
    options = dict(experiment={'origin': 'synthetic', 'split': 'offline-profile', 'designs': ['opamp']},
                   config=SACConfig(gamma=0, initial_alpha=.01, learning_rate=.001))
    return 'synthetic op-amp, 16 transitions', replay, options


def checkpoint_fixture(path):
    payload = torch.load(path, map_location='cpu', weights_only=False)  # trusted local save point
    contract = payload['contract']
    replay = ReplayBuffer.from_state_dict(payload['replay'])
    options = dict(experiment=contract['experiment'],
                   feature_schema=_dataclass(FeatureSchema, contract['feature_schema']),
                   spec_schema=_dataclass(SpecSchema, contract['spec_schema']),
                   config=_dataclass(SACConfig, contract['config']),
                   reward_settings=_dataclass(RewardSettings, contract['reward_settings']),
                   condition_policy=contract['condition_policy'])
    stat = Path(path).stat()
    return f'{path} ({len(replay)} transitions, {stat.st_size} bytes)', replay, options


def wait_for_load(limit, longest):
    started = time.monotonic()
    while limit is not None and os.getloadavg()[0] >= limit and time.monotonic() - started < longest:
        time.sleep(5)
    return round(time.monotonic() - started, 1)


def step_function(replay, learner, batch_size):
    """The call the workbench engine makes for one learner step (engine._maybe_update)."""
    lend = getattr(replay, 'update_learner', None)
    if lend is not None:
        return 'lent (no copy)', lambda: lend(learner, batch_size)
    return 'sample() deep copy', lambda: learner.update(replay.sample(batch_size))


class Phases:
    """Wraps the learner's phases on THIS learner only (instance attributes) plus Transition.validate."""

    def __init__(self, learner, replay):
        self.times = {}
        self.learner, self.replay = learner, replay
        self.batches = self.samples = 0
        self.original_validate = Transition.validate

    def _timed(self, name, function):
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.times.setdefault(name, []).append(time.perf_counter() - started)
        return wrapper

    def install(self):
        learner = self.learner
        batch, sample = learner.batch, learner.actor.sample

        def batch_phase(*args, **kwargs):
            self.batches += 1
            # update() batches the current states first and the next states second (when it needs them).
            name = 'current batch' if self.batches % 2 == 1 or self.following_skipped() else 'next-state batch'
            return self._timed(name, batch)(*args, **kwargs)

        def sample_phase(*args, **kwargs):
            self.samples += 1
            name = 'next-state actor' if self.samples % 2 == 1 and not self.following_skipped() else 'current actor'
            return self._timed(name, sample)(*args, **kwargs)

        learner.batch, learner.actor.sample = batch_phase, sample_phase
        for index, target in enumerate(learner.targets):
            target.forward = self._timed(f'target critic {index}', target.forward)
        learner.update = self._timed('learner.update', learner.update)
        Transition.validate = self._timed('validation', self.original_validate)

    def following_skipped(self):
        return getattr(self.learner, 'skips_unused_bootstrap', lambda: False)()

    def restore(self):
        Transition.validate = self.original_validate

    def begin(self):
        self.times.clear()
        self.batches = self.samples = 0


def profile(fixture, replay, options, encoder, args):
    torch.manual_seed(17)
    random.seed(17)
    model = ModelConfig(encoder_type=encoder, **PRESETS[encoder])
    learner = SACLearner(model_config=model, **options)
    for transition in replay._items:      # warm the input cache as a live run does
        learner.batch([transition.observation])
        learner.batch([transition.next_observation])
    path, step = step_function(replay, learner, args.batch)
    for _ in range(args.warmup):
        step()
    waited = wait_for_load(args.wait_load, args.wait_max)
    load_before = os.getloadavg()[0]
    totals = []
    for _ in range(args.updates):
        started = time.perf_counter()
        step()
        totals.append(time.perf_counter() - started)
    phases = Phases(learner, replay)
    phases.install()
    try:
        steps = []
        for _ in range(args.updates):
            phases.begin()
            started = time.perf_counter()
            step()
            total = time.perf_counter() - started
            steps.append({name: sum(values) for name, values in phases.times.items()} | {'step': total})
    finally:
        phases.restore()
    medians = {name: statistics.median(s.get(name, 0.0) for s in steps) * 1e3 for name in sorted({k for s in steps for k in s})}
    medians['replay sampling (step - learner.update)'] = statistics.median(
        (s['step'] - s.get('learner.update', 0.0)) for s in steps) * 1e3
    totals.sort()
    return dict(fixture=fixture, encoder=encoder, model=dataclasses.asdict(model), gamma=learner.config.gamma,
                batch=args.batch, sampling=path, warmup=args.warmup, timed=args.updates,
                step_ms=dict(median=statistics.median(totals) * 1e3, p90=totals[int(.9 * (len(totals) - 1))] * 1e3),
                phase_medians_ms=medians, cache=learner.input_cache.info(),
                load=dict(waited_s=waited, before=round(load_before, 2), after=round(os.getloadavg()[0], 2)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--checkpoint', help="a save point's training_state.pt (trusted local file)")
    parser.add_argument('--encoders', default='graph_transformer,rgcn,gatv2')
    parser.add_argument('--threads', type=int, default=1, help='torch CPU threads (the workbench worker uses 1)')
    parser.add_argument('--batch', type=int, default=8)
    parser.add_argument('--updates', type=int, default=100)
    parser.add_argument('--warmup', type=int, default=30)
    parser.add_argument('--wait-load', type=float, help='wait until the 1-minute load average is below this, per arm')
    parser.add_argument('--wait-max', type=float, default=900, help='longest wait per arm, seconds')
    parser.add_argument('--json', help='also write the report here')
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    fixture, replay, options = checkpoint_fixture(args.checkpoint) if args.checkpoint else synthetic_fixture()
    try:
        revision = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                  check=False).stdout.strip() or None
    except OSError:
        revision = None
    report = dict(origin='real' if args.checkpoint else 'synthetic', provenance='recorded' if args.checkpoint else 'mock',
                  source_digest=source_digest(), git_revision=revision, python=platform.python_version(),
                  torch=torch.__version__, torch_threads=torch.get_num_threads(),
                  omp_num_threads=os.environ.get('OMP_NUM_THREADS'), cpus=os.cpu_count(), results=[])
    for encoder in [e for e in args.encoders.split(',') if e]:
        row = profile(fixture, replay, options, encoder, args)
        report['results'].append(row)
        phases = ', '.join(f'{k} {v:.2f}' for k, v in row['phase_medians_ms'].items())
        print(f"{encoder}: step median {row['step_ms']['median']:.2f} ms, p90 {row['step_ms']['p90']:.2f} "
              f"({row['sampling']}; load {row['load']['before']}->{row['load']['after']}) | {phases}", flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
