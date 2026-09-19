"""Recorded seed parallelism must preserve budgets, weights and data partitions."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import torch

from analog_optimizer.evaluation.benchmark import run_benchmark
from analog_optimizer.evaluation.runtime import BenchmarkFactory
from analog_optimizer.evaluation.streaming import RunStatistics
from analog_optimizer.evaluation.transfer import TransferTask, summarize_run
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.recording import RunRecorder, start_service
from analog_optimizer.training.workers import WorkerLimits


ROOT = Path(__file__).resolve().parents[1]


def tasks(graph):
    return [TransferTask(name, name, 'specification', 'toy', graph,
                        (MetricSpec('score', 'fixture', 'min', 1, lower=target),))
            for name, target in [('train', .9), ('validation', .95), ('test', .99)]]


def settings():
    return dict(seeds=[17, 29], encoders=['mlp'], hidden_dim=16, heads=2, layers=1,
                pretrain_steps=2, test_steps=2, batch_size=2, max_calls=40)


def test_recorded_parallel_seeds_match_serial_and_keep_replays_isolated(opamp, tmp_path):
    torch.set_num_threads(1)
    factory = BenchmarkFactory('synthetic')
    serial = run_benchmark(tasks(opamp), factory, tmp_path/'serial', origin='synthetic', settings=settings(),
                           provenance={}, progress=lambda _: None)
    manager, store = start_service(tmp_path/'records', dict(min_free=0, temporary_reserve=0, checkpoint_interval=1))
    try:
        parent = store.call('run', {'purpose': 'offline parallel benchmark test'})
        parallel = run_benchmark(tasks(opamp), factory, tmp_path/'parallel', origin='synthetic', settings=settings(),
            provenance={}, progress=lambda _: None, recorder=RunRecorder(store, parent), max_workers=2,
            limits=WorkerLimits(60, 5, 1))
        assert parallel['completed'] and parallel['worker_count'] == 2
        assert parallel['calls'] == parallel['planned_calls'] == serial['calls'] == 40
        assert parallel['protocol_sha256'] == serial['protocol_sha256']
        for a, b in zip(serial['test_runs'], parallel['test_runs']):
            for key in ('task', 'method', 'seed', 'calls', 'success', 'best_reward', 'best_parameters',
                        'first_feasible_call', 'updates', 'weight_before', 'weight_after', 'replay_insertions'):
                assert a[key] == b[key], (key, a['method'], a['seed'])
            assert len(b['actions']) <= 1 and len(b['best_so_far']) <= 1
            assert b['actions_count'] == 2 and b['records_count'] == 3
            assert b['history_truncated']
            run = store.call('read', 'run', b['recording_run_id'])
            assert run['ended'] is not None and run['summary']['evaluations'] == 3
            if b['phase'] != 'frozen':
                payload = torch.load(b['checkpoint'], weights_only=False)
                assert payload['replay_format'] == 'replay-ids-v1'
                # A held-out learner contains only this task's two transitions.
                from analog_optimizer.training.replay import ReplayBuffer
                buffer = ReplayBuffer.from_manifest(payload['replay'], store)
                assert len(buffer) == 2
                for transition in buffer.sample(2):
                    evaluation = store.call('read', 'evaluation', transition.candidate_id)
                    assert evaluation['run_id'] == b['recording_run_id']
        assert len(store.call('read', 'evaluations')) == 40
        assert not list((tmp_path/'parallel').rglob('candidates/*.json'))
        assert not store.call('pending')
    finally:
        store.close()
        manager.shutdown()


def test_parallel_rejects_mutable_schematic_before_environment_creation(opamp, tmp_path):
    factory = BenchmarkFactory('real')
    with pytest.raises(ValueError, match='isolated immutable'):
        run_benchmark(tasks(opamp), factory, tmp_path, origin='real', settings=settings(), provenance={}, max_workers=2)


def test_streamed_statistics_keep_full_counts_and_early_best():
    rows = [dict(candidate_id=str(i), evaluation_valid=status == 'ok', reward=value,
                 success=value == 0, status=status, simulation_calls=i+1, time_from_start_seconds=i*.1,
                 metrics={'score': value}, metric_units={'score': 'fixture'}, applied_parameters=[{'value': i}],
                 violations={'score': None if value is None else -value}, duplicate_of='first' if i == 3 else None)
            for i, (status, value) in enumerate([('ok', 0), ('ok', -.2), ('timeout', None), ('ok', -.3)])]
    statistics = RunStatistics(1)
    for row in rows:
        statistics.add(row)
    expected = summarize_run(rows, calls=4, wall_seconds=1, budget=4)
    actual = statistics.summary(calls=4, wall_seconds=1, budget=4)
    for key in expected:
        if key != 'best_so_far':
            assert actual[key] == expected[key]
    assert actual['best_so_far'] == expected['best_so_far'][-1:]


def test_benchmark_cli_recording_and_parallel_budget(tmp_path):
    config = tmp_path/'recording.json'
    config.write_text(json.dumps(dict(min_free=0, temporary_reserve=0)))
    command = [sys.executable, str(ROOT/'examples/benchmark_transfer.py'), '--origin', 'synthetic',
        '--seeds', '17', '29', '--encoders', 'mlp', '--hidden-dim', '16', '--heads', '2', '--layers', '1',
        '--pretrain-steps', '2', '--test-steps', '2', '--max-calls', '76', '--max-workers', '2',
        '--recording-root', str(tmp_path/'records'), '--recording-config', str(config),
        '--history-limit', '1', '--output', str(tmp_path/'output')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(next((tmp_path/'output').glob('*/report.json')).read_text())
    assert report['completed'] and report['calls'] == report['planned_calls'] == 76
    assert report['worker_count'] == 2 and Path(report['summary_path']).exists()
