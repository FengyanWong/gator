"""Real spawned workers with synthetic environments; no Cadence/network access."""
from dataclasses import dataclass, replace
import json
from pathlib import Path
import random
import time

import pytest
import torch

from analog_optimizer.backends.backend import SimulationStatus
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ModelConfig
from analog_optimizer.training.parallel import collect_parallel_episodes
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner


class TimedBackend(SyntheticSizingBackend):
    def __init__(self, graph, output, lane, failure):
        super().__init__(graph, targets={'w': .4, 'c': -.3})
        self.output, self.lane, self.failure = output, lane, failure

    def run_simulation(self, request):
        start = time.time()
        time.sleep(.15 if self.lane == 0 else .25)
        result = super().run_simulation(request)
        (self.output / f'timing-{self.lane}-{self.calls}.json').write_text(json.dumps(
            dict(lane=self.lane, start=start, end=time.time())))
        if self.failure and self.lane == 0 and self.calls == 2:
            result = replace(result, status=SimulationStatus.TIMEOUT, candidate_evaluated=False,
                             metrics={}, metric_units={}, metric_validity={})
        return result


@dataclass
class Factory:
    graph: object
    output: Path
    failure: bool = False

    def __call__(self, lane):
        return self.create_recorded(lane, None)

    def create_recorded(self, lane, recorder):
        return CircuitSizingEnv(TimedBackend(self.graph, self.output, lane, self.failure), self.graph,
                                (MetricSpec('score', 'fixture', 'min', 1, lower=.95),), self.output,
                                max_steps=2, stop_on_success=False, expected_origin='synthetic', recorder=recorder)


def make_learner():
    torch.set_num_threads(1)
    torch.manual_seed(91)
    return SACLearner(experiment={'origin': 'synthetic', 'split': 'parallel-test', 'designs': ['fixture']},
                      model_config=ModelConfig(hidden_dim=16, heads=2, layers=1))


@pytest.mark.parametrize('workers,episodes', [(1, 2), (2, 3)])
def test_parallel_budget_transitions_concurrency_and_checkpoint(opamp, tmp_path, workers, episodes):
    learner = make_learner()
    replay = ReplayBuffer(origin='synthetic', seed=9)
    report = collect_parallel_episodes(Factory(opamp, tmp_path), learner, replay, random.Random(8),
                                      max_workers=workers, episodes=episodes, warmup=1, batch_size=2)
    assert report['passed'] and report['completed_episodes'] == episodes
    assert report['simulation_calls'] == episodes * 3
    assert len(replay) == 2 * episodes and learner.updates == 2 * episodes - 1
    assert report['peak_in_flight'] == workers
    assert len({w['pid'] for w in report['workers']}) == workers
    assert all(r['state'] == 'restored' for r in report['restorations'])
    for worker in report['workers']:
        rows = [s for s in report['stages'] if Path(s['record_path']).parent.parent == Path(worker['directory'])]
        for row in rows:
            record = json.loads(Path(row['record_path']).read_text())
            assert record['proposal'] == row['proposal']
    intervals = [json.loads(p.read_text()) for p in tmp_path.glob('timing-*.json')]
    events = sorted([(d['start'], 1) for d in intervals] + [(d['end'], -1) for d in intervals])
    active = peak = 0
    for _, change in events:
        active += change
        peak = max(peak, active)
    assert peak == workers
    checkpoint = tmp_path / 'checkpoint.pt'
    learner.save(checkpoint, replay)
    expected = learner.update(replay.sample(2))
    restored, buffer, _ = SACLearner.load(checkpoint, experiment=learner.experiment,
                                         model_config=learner.model_config)
    assert restored.update(buffer.sample(2)) == expected


def test_failed_worker_is_excluded_peers_drained_and_every_worker_closed(opamp, tmp_path):
    learner, replay, report = make_learner(), ReplayBuffer(origin='synthetic'), {}
    with pytest.raises(RuntimeError, match='ineligible'):
        collect_parallel_episodes(Factory(opamp, tmp_path, failure=True), learner, replay, random.Random(8),
                                  max_workers=2, episodes=2, batch_size=2, report=report)
    assert not report['passed'] and len(replay) == 1
    assert report['simulation_calls'] == 4
    assert len(report['restorations']) == 2 and all(r['state'] == 'restored' for r in report['restorations'])
    assert [s['replay_eligible'] for s in report['stages']] == [False, True]


@pytest.mark.parametrize('value', [0, -1, True, 1.5])
def test_invalid_worker_limit_rejected_before_starting(value):
    with pytest.raises(ValueError, match='max_workers'):
        collect_parallel_episodes(None, None, None, None, max_workers=value, episodes=1)


def test_parallel_recording_with_shared_writer_and_durable_replay(opamp, tmp_path):
    from analog_optimizer.recording import start_service, RunRecorder
    from analog_optimizer.recording.codec import raw
    manager, store = start_service(tmp_path / 'records', dict(min_free=0, temporary_reserve=0))
    try:
        run = store.call('run', {})
        replay = ReplayBuffer(origin='synthetic', store=store)
        learner = make_learner()
        report = collect_parallel_episodes(Factory(opamp, tmp_path), learner, replay, random.Random(8),
            max_workers=2, episodes=2, warmup=1, batch_size=2, recorder=RunRecorder(store, run))
        assert report['passed'] and len(replay) == 4
        assert store.call('read', 'run', run)['summary']['evaluations'] == 6
        saved = ReplayBuffer.from_manifest(replay.manifest(), store)
        assert raw(vars(saved.sample(1)[0])) == raw(vars(replay.sample(1)[0]))
        assert not list((tmp_path / 'records/temporary').iterdir())
        assert not list(tmp_path.rglob('config.json'))
        assert not list(tmp_path.rglob('candidates'))
    finally:
        store.close()
        manager.shutdown()
