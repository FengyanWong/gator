"""CLI recovery and fault injection; every backend here is explicitly synthetic."""
from dataclasses import dataclass
import importlib
import json
import multiprocessing
from pathlib import Path
import random
import sys
import time

import pytest
import torch

from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models import ModelConfig
from analog_optimizer.training.parallel import collect_parallel_episodes
from analog_optimizer.training.recovery import ROUND, RUN, restore_parallel
from analog_optimizer.training.runtime import RunResources
from analog_optimizer.training.workers import OwnedWorker, WorkerLimits, WorkerTimeout
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner

ROOT = Path(__file__).resolve().parents[1]


class HangingBackend(SyntheticSizingBackend):
    def run_simulation(self, request):
        if self.calls == 1:
            while True:
                time.sleep(.05)
        return super().run_simulation(request)


@dataclass
class ToyFactory:
    graph: object
    output: Path
    steps: int = 2
    hang_lane: int | None = None

    def __call__(self, lane):
        return self.create_recorded(lane, None)

    def create_recorded(self, lane, recorder):
        backend = HangingBackend if lane == self.hang_lane else SyntheticSizingBackend
        return CircuitSizingEnv(backend(self.graph, targets={'w': .4, 'c': -.3}), self.graph,
            (MetricSpec('score', 'fixture', 'min', 1, lower=.95),), self.output / str(lane),
            max_steps=self.steps, stop_on_success=False, expected_origin='synthetic', recorder=recorder)


def toy_learner():
    torch.set_num_threads(1)
    torch.manual_seed(12)
    return SACLearner(experiment=dict(origin='synthetic', split='offline-recovery', designs=['toy']),
                      model_config=ModelConfig(hidden_dim=16, heads=2, layers=1))


def ping():
    return 'ready'


def hang():
    while True:
        time.sleep(.05)


def crash():
    import os
    os._exit(7)


@pytest.mark.parametrize('operation', [hang, crash])
def test_owned_worker_deadline_and_exit_do_not_block_shutdown(operation):
    worker = OwnedWorker(0, WorkerLimits(30, .15, 2))
    try:
        assert worker.submit(ping).result() == 'ready'
        start = time.monotonic()
        with pytest.raises((WorkerTimeout, EOFError, ConnectionError)):
            worker.submit(operation, timeout=.2).result()
    finally:
        result = worker.shutdown()
    assert time.monotonic() - start < 3
    assert result['state'] != 'still_alive'
    assert not any(child.pid == result['pid'] for child in multiprocessing.active_children())


def test_hung_lane_keeps_peer_transition_and_reports_unknown_job(opamp, tmp_path, monkeypatch):
    original = OwnedWorker.submit
    def submit(self, function, *args, **kwargs):
        if function.__name__ == '_step':
            kwargs['timeout'] = .6
        return original(self, function, *args, **kwargs)
    monkeypatch.setattr(OwnedWorker, 'submit', submit)
    learner, replay, report = toy_learner(), ReplayBuffer(origin='synthetic'), {}
    with pytest.raises(WorkerTimeout):
        collect_parallel_episodes(ToyFactory(opamp, tmp_path, hang_lane=0), learner, replay,
            random.Random(3), max_workers=2, episodes=2, batch_size=2, report=report,
            limits=WorkerLimits(30, .2, 2))
    assert len(replay) == 1
    assert report['simulation_calls'] == 3  # Two resets, one confirmed peer step.
    assert report['call_count_kind'] == 'confirmed_lower_bound'
    assert report['unconfirmed_operations'][0]['lane'] == 0
    assert report['unfinished_workers'] and all(r['state'] != 'still_alive' for r in report['worker_shutdown'])
    assert not report['passed']


@pytest.mark.parametrize('fail_at', ['create_run', 'load_checkpoint', 'write_report'])
def test_cleanup_covers_initialization_and_report_errors(tmp_path, monkeypatch, fail_at):
    from analog_optimizer import recording
    from analog_optimizer.recording import setup
    from analog_optimizer.envs import sizing
    events = []
    class Store:
        def call(self, *args):
            events.append(args[0])
            return [] if args[0] == 'read' else 'asset'
        def close(self):
            events.append('close')
    class Manager:
        def shutdown(self):
            events.append('shutdown')
    monkeypatch.setattr(recording, 'start_service', lambda *a: (Manager(), Store()))
    def create(*a, **kw):
        if fail_at == 'create_run':
            raise ValueError('setup failed')
        return 'run'
    monkeypatch.setattr(setup, 'create_run', create)
    if fail_at == 'write_report':
        def broken(*a, **kw):
            raise OSError('report failed')
        monkeypatch.setattr(sizing, 'write_record', broken)
    report = {}
    with pytest.raises((ValueError, OSError), match={'create_run': 'setup', 'load_checkpoint': 'checkpoint', 'write_report': 'report'}[fail_at]):
        with RunResources(report, tmp_path / 'report.json', recording_root=tmp_path) as runtime:
            runtime.start(ROOT, {})
            if fail_at == 'load_checkpoint':
                raise ValueError('checkpoint rejected')
    assert events[-2:] == ['close', 'shutdown']


def test_cleanup_errors_preserve_original_exception(tmp_path, monkeypatch):
    from analog_optimizer.envs import sizing
    events = []
    class BrokenStore:
        def call(self, *args):
            events.append('end')
            raise OSError('database failure')
        def close(self):
            events.append('close')
            raise OSError('close failure')
    class Manager:
        def shutdown(self):
            events.append('shutdown')
    def broken_report(*args):
        raise OSError('report failure')
    monkeypatch.setattr(sizing, 'write_record', broken_report)
    original = ValueError('original training failure')
    report = {}
    with pytest.raises(ValueError) as failure:
        with RunResources(report, tmp_path / 'report.json') as runtime:
            runtime.store, runtime.manager, runtime.run_id = BrokenStore(), Manager(), 'run'
            raise original
    assert failure.value is original
    assert events == ['end', 'close', 'shutdown']
    assert len(report['cleanup_errors']) == 3


def test_parallel_cli_resumes_periodic_checkpoint_twice_with_cumulative_counts(opamp, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'examples'))
    entry = importlib.import_module('train_opamp_sac_parallel')
    from analog_optimizer.envs import sizing
    from analog_optimizer.recording.reader import RunReader
    config = tmp_path / 'recording.json'
    config.write_text(json.dumps(dict(min_free=0, temporary_reserve=0, checkpoint_interval=1)))
    records = tmp_path / 'records'
    def prepare(args, directory):
        learner = toy_learner()
        return ToyFactory(opamp, directory), learner.experiment, learner.model_config, {}, {}
    monkeypatch.setattr(entry, 'prepare_training', prepare)
    original_write = sizing.write_record
    interrupt = [True]
    def write(path, data):
        original_write(path, data)
        if Path(path).name == 'progress.json' and interrupt[0]:
            raise KeyboardInterrupt('injected after durable periodic checkpoint')
    monkeypatch.setattr(sizing, 'write_record', write)
    base = ['train_opamp_sac_parallel', '--env', str(tmp_path/'unused'), '--library', 'synthetic-fixture',
            '--creation-receipt', str(tmp_path/'unused'), '--model-file', 'synthetic-fixture',
            '--reference-measurements', str(tmp_path/'unused'),
            '--output', str(tmp_path/'output'), '--max-workers', '1', '--episodes', '1',
            '--steps-per-episode', '2', '--batch-size', '2', '--recording-root', str(records),
            '--recording-config', str(config), '--history-limit', '1']
    previous = None
    for expected_calls in (2, 4):
        monkeypatch.setattr(sys, 'argv', base + ([] if previous is None else ['--resume', str(previous)]))
        with pytest.raises(KeyboardInterrupt):
            entry.main()
        with RunReader(records) as reader:
            overview = reader.overview()
            assert overview['lifecycle'] == 'ended'
            previous = Path(overview['latest_checkpoint']['path'])
        payload = torch.load(previous, weights_only=False)
        assert payload['run_state']['boundary'] == ROUND
        assert payload['run_state']['simulation_calls'] == expected_calls
        assert payload['run_state']['completed_episodes'] == 0
    interrupt[0] = False
    monkeypatch.setattr(sys, 'argv', base + ['--resume', str(previous)])
    assert entry.main() == 0
    reports = [json.loads(p.read_text()) for p in (tmp_path/'output').glob('*/report.json')]
    final = next(row for row in reports if row['passed'])
    assert final['simulation_calls_before'] == 4 and final['total_simulation_calls'] == 7
    assert final['total_completed_episodes'] == 1 and final['replay_size'] == 4
    assert final['stages_count'] == 2 and len(final['stages']) == 1
    with RunReader(records) as reader:
        restored, replay, state = SACLearner.load(final['checkpoint'], experiment=toy_learner().experiment,
                                                model_config=toy_learner().model_config, store=reader)
        expected = restored.update(replay.sample(2))
        second, second_replay, _ = SACLearner.load(final['checkpoint'], experiment=restored.experiment,
                                                 model_config=restored.model_config, store=reader)
        assert second.update(second_replay.sample(2)) == expected
        assert state['boundary'] == RUN


def test_recovery_rejects_unknown_boundary():
    with pytest.raises(ValueError, match='completed parallel'):
        restore_parallel({'boundary': 'in_flight'}, random.Random(1))


def test_later_lane_deadline_is_watched_while_first_lane_is_active():
    from concurrent.futures import Future
    from analog_optimizer.training.workers import DeadlineFuture, wait_workers
    active = DeadlineFuture(Future(), 60, 'active', heartbeat=True)
    stalled = DeadlineFuture(Future(), .05, 'stalled', heartbeat=True)
    lane, future = next(wait_workers({0: active, 1: stalled}))
    assert lane == 1
    with pytest.raises(WorkerTimeout):
        future.result()


@pytest.mark.parametrize('training_error', [False, True])
def test_environment_report_failure_still_restores_and_closes(opamp, tmp_path, monkeypatch, training_error):
    from analog_optimizer.envs import sizing
    env = ToyFactory(opamp, tmp_path)(0)
    original = sizing.write_record
    def write(path, data):
        if Path(path).name == 'restoration.json':
            raise OSError('restoration report failure')
        return original(path, data)
    monkeypatch.setattr(sizing, 'write_record', write)
    with pytest.raises(ValueError if training_error else OSError):
        with env:
            env.reset()
            env.step({group: .8 for group in env.mapper.group_ids})
            if training_error:
                raise ValueError('original training failure')
    assert not env.backend.connected
    assert env.backend.parameters == env.backend.initial


def test_synthetic_cli_resumes_periodic_counters(tmp_path):
    import subprocess
    from analog_optimizer.recording.reader import RunReader
    config = tmp_path/'recording.json'
    config.write_text(json.dumps(dict(min_free=0, temporary_reserve=0, checkpoint_interval=3)))
    command = [sys.executable, str(ROOT/'examples/train_synthetic_sac.py'), '--episodes', '1', '--steps', '2',
        '--batch-size', '2', '--encoder', 'gatv2', '--output', str(tmp_path/'output'),
        '--recording-root', str(tmp_path/'records'), '--recording-config', str(config), '--history-limit', '1']
    first = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stdout + first.stderr
    with RunReader(tmp_path/'records') as reader:
        rows = reader.call('read', 'checkpoints')
        periodic = next(row['path'] for row in rows if row['kind'] == 'full' and row['step'] == 3)
    payload = torch.load(periodic, weights_only=False)
    assert payload['run_state']['completed_episodes'] == 1
    assert payload['run_state']['synthetic_calls'] == 5
    resumed = subprocess.run(command + ['--resume', periodic], capture_output=True, text=True, timeout=60)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    reports = [json.loads(p.read_text()) for p in (tmp_path/'output').glob('*/report.json')]
    final = next(row for row in reports if row['total_synthetic_calls'] == 11)
    assert final['passed'] and final['exact_resume'] and final['replay_size'] == 7
    assert final['stages_count'] == 2 and len(final['stages']) == 1
