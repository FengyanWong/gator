"""Recording acceptance uses injected MockBackend/toy fixtures only; no Spectre."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import random
import sqlite3

import pytest

from analog_optimizer.backends.backend import SimulationRequest, SimulationStatus
from analog_optimizer.backends.mock import MockBackend
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.recording import ExperimentStore, RecordingConfig, RunRecorder, SpaceExhausted
from analog_optimizer.recording.codec import raw, unpack, pack
from analog_optimizer.recording.space import create_workspace, remove_workspace
from analog_optimizer.recording.store import wal_fixed


SPEC = (MetricSpec('score', 'fixture', 'min', 1., lower=.95),)


@pytest.fixture
def store(tmp_path):
    """Open a temporary experiment store with free-space thresholds disabled and close it after use."""
    with ExperimentStore(tmp_path / 'recording', RecordingConfig(min_free=0, temporary_reserve=0)) as value:
        yield value


def setup(store, graph):
    """Register a run, task and graph and return their IDs as an evaluation context."""
    run = store.call('run', {})
    task, gid = store.call('task', graph, SPEC)
    return run, task, gid


def begin(store, context, i='e', **kwargs):
    """Begin a mock evaluation in the registered run, task and graph."""
    return store.call('begin', *context, dict(source='mock', **kwargs), eval_id=i)


def result(value=.96, status='ok'):
    """Build an injected metric result with no simulator invocations."""
    return dict(status=status, metrics={'score': value}, metric_validity={'score': value is not None},
                metric_units={'score': 'fixture'}, applied_parameters={('M1', 'm'): 3}, simulator_invocations=0)


def test_static_idempotent_parallel_and_summaries(store, opamp):
    context = setup(store, opamp)
    assert store.call('task', opamp, SPEC) == context[1:]
    def worker(i):
        """Finish the same mock evaluation twice and require identical acknowledgements."""
        key = begin(store, context, str(i), worker_id=str(i), phase='initial' if i == 0 else 'training')
        data = result(.96 if i % 2 else .5)
        ack = store.call('finish', key, data)
        assert store.call('finish', key, data) == ack
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(40)))
    run = store.call('read', 'run', context[0])
    assert run['summary']['evaluations'] == 40
    assert run['summary']['has_feasible']
    assert run['summary']['real_simulations'] == 0
    assert len([a for a in store.call('read', 'assets') if a['kind'] == 'graph']) == 1
    with pytest.raises(ValueError, match='Conflicting'):
        store.call('finish', '0', result(.4))


@pytest.mark.parametrize('status,value', [('ok', .99), ('ok', .4), ('timeout', None),
                                        ('nonconverged', None), ('measurement_error', None)])
def test_actual_mock_attempts(store, opamp, tmp_path, status, value):
    context = setup(store, opamp)
    key = begin(store, context, phase='initial')
    backend = MockBackend('simulator lang=spectre\n', metrics={'score': value}, metric_units={'score': 'fixture'},
                          status=SimulationStatus(status))
    with backend:
        artifact = backend.generate_netlist(tmp_path / 'mock')
        store.call('start', key, {})
        measured = backend.run_simulation(SimulationRequest(artifact, tmp_path / 'results', ('score',)))
        store.call('finish', key, dict(result(value, measured.status.value),
                                      metrics=measured.metrics, metric_validity=measured.metric_validity))
    row = store.call('read', 'evaluation', key)
    assert row['state'] == 'completed' and row['result']['status'] == status
    if value is None:
        assert row['result']['metrics']['score'] is None
    assert store.call('read', 'run', context[0])['summary']['has_feasible'] == (status == 'ok' and value >= .95)


def test_env_replay_lossless_rounded_execution_and_no_candidate_files(store, opamp, tmp_path):
    from analog_optimizer.training.replay import ReplayBuffer, Transition
    from analog_optimizer.recording.session import transition_from_store
    opamp.parameter_groups[0] = replace(opamp.parameter_groups[0], step=1e-6, scale='linear')
    context = setup(store, opamp)
    recorder = RunRecorder(store, context[0])
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    replay = ReplayBuffer(capacity=1, origin='synthetic', store=store)
    with CircuitSizingEnv(backend, opamp, SPEC, tmp_path / 'env', max_steps=2, stop_on_success=False,
                          expected_origin='synthetic', recorder=recorder) as env:
        observation, _ = env.reset()
        for _ in range(2):
            proposal = {k: .123456789 for k in env.mapper.group_ids}
            step = env.step(proposal)
            transition = Transition.from_step(observation, proposal, step)
            replay.add(transition)
            restored = transition_from_store(store, transition.candidate_id)
            assert raw(vars(restored)) == raw(vars(transition))
            row = store.call('read', 'evaluation', transition.candidate_id)
            assert row['result']['applied_parameters'] == backend.parameters
            observation = step[0]
    assert len(replay) == 1 and len(store.call('read', 'transitions')) == 2
    assert not list(env.directory.rglob('*/*.json'))
    assert not list((store.root / 'temporary').iterdir())
    restored = ReplayBuffer.from_manifest(replay.manifest(), store)
    assert raw(vars(replay.sample(1)[0])) == raw(vars(restored.sample(1)[0]))


def test_failure_transition_keeps_raw_metrics_and_end_flags(store, opamp, tmp_path):
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    original = backend.run_simulation
    recorder = RunRecorder(store, setup(store, opamp)[0])
    with CircuitSizingEnv(backend, opamp, SPEC, tmp_path / 'env', stop_on_success=False,
                          expected_origin='synthetic', recorder=recorder) as env:
        observation, _ = env.reset()
        backend.run_simulation = lambda req: replace(original(req), status=SimulationStatus.TIMEOUT,
                                                       candidate_evaluated=False, metric_validity={'score': False})
        step = env.step({k: 0. for k in env.mapper.group_ids})
    transition = store.call('read', 'transition', step[4]['eval_id'])
    assert not transition['terminated'] and transition['truncated'] and transition['reward'] is None
    assert transition['next_observation'] is None
    assert raw(transition['observation']) == raw(observation)
    assert store.call('read', 'evaluation', step[4]['eval_id'])['result']['metrics']['score'] is None


def test_restart_pending_and_cleaning_requires_ack(opamp, tmp_path):
    root = tmp_path / 'store'
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        context = setup(store, opamp)
        key = begin(store, context)
        workspace = store.call('workspace', key)
        (Path(workspace['path']) / 'wave.raw').write_bytes(b'expensive')
        store.call('workspace_finished', workspace['token'])
        with pytest.raises((ValueError, KeyError)):
            store.call('cleanup', dict(eval_id=key), workspace['token'])
        assert Path(workspace['path']).exists()
        store.call('start', key, {('M1', 'm'): 3})
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        assert store.call('pending')[0]['state'] == 'running'
        store.call('recover', [key])
        assert store.call('pending')[0]['state'] == 'interrupted'
        ack = store.call('finish', key, result())
        store.call('cleanup', ack, workspace['token'])
        assert not Path(workspace['path']).exists()
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        assert store.call('read', 'evaluation', key)['result']['metrics']['score'] == .96
        assert not store.call('pending')


def test_cleanup_refuses_running_symlinks_and_foreign_paths(store, opamp, tmp_path):
    context = setup(store, opamp)
    key = begin(store, context)
    workspace = store.call('workspace', key)
    ack = store.call('finish', key, result())
    with pytest.raises(ValueError, match='running'):
        store.call('cleanup', ack, workspace['token'])
    store.call('workspace_finished', workspace['token'])
    (Path(workspace['path']) / 'escape').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='Symlink'):
        store.call('cleanup', ack, workspace['token'])
    with pytest.raises(ValueError):
        remove_workspace(dict(workspace, path=str(tmp_path), finished=True))


def test_capacity_stops_dispatch_and_preserves_core(opamp, tmp_path):
    with ExperimentStore(tmp_path / 'small', RecordingConfig(project_budget=500_000,
                         min_free=0, temporary_reserve=0, journal_reserve=0, result_reserve=0)) as store:
        context = setup(store, opamp)
        key = begin(store, context)
        store.call('finish', key, result())
        with pytest.raises(SpaceExhausted):
            store.call('preflight', extra=1_000_000)
        assert store.call('read', 'evaluation', key)['result']['metrics']['score'] == .96
        assert len(store.call('read', 'evaluations')) == 1


def test_failed_space_preflight_commits_eviction_metadata(store, opamp):
    context = setup(store, opamp)
    key = begin(store, context)
    workspace = store.call('workspace', key)
    (Path(workspace['path']) / 'wave').write_bytes(b'x' * 4096)
    receipt = store.call('finish', key, result())
    store.call('workspace_finished', workspace['token'])
    store.call('attach', receipt, workspace['token'], 'initial')
    store.call('cleanup', receipt, workspace['token'])
    store.config = replace(store.config, project_budget=1)
    with pytest.raises(SpaceExhausted):
        store.call('preflight')
    attachment = store.call('read', 'attachments')[0]
    assert attachment['status'] == 'evicted' and not Path(attachment['path']).exists()
    assert store.call('read', 'evaluation', key)['result']['metrics']['score'] == .96


def test_float64_int_and_float32_arrays_are_exact():
    import numpy as np
    data = dict(parameters={('m', 'm'): 7, ('m', 'w'): 1.234567890123456e-6},
                fields=['a', 'b'], array=np.asarray([[.123456789, .8]], dtype=np.float32))
    restored = unpack(pack(data))
    assert type(restored['parameters']['m', 'm']) is int
    assert restored['parameters'] == data['parameters']
    assert restored['array'].dtype == np.float32 and restored['array'].shape == (1, 2)
    assert restored['array'].tobytes() == data['array'].tobytes()
    assert restored['fields'] == data['fields']


def test_asset_hash_deduplicates_mapping_order(store):
    assert store.call('asset', 'config', {'a': 1, 'b': 2}) == store.call('asset', 'config', {'b': 2, 'a': 1})


def test_local_live_process_blocks_cleanup(store, opamp):
    import os
    context = setup(store, opamp)
    key = begin(store, context)
    workspace = store.call('workspace', key)
    (Path(workspace['path']) / 'spectre.pid').write_text(str(os.getpid()))
    ack = store.call('finish', key, result())
    store.call('workspace_finished', workspace['token'])
    with pytest.raises(ValueError, match='still alive'):
        store.call('cleanup', ack, workspace['token'])


def test_wal_versions_and_local_filesystem():
    assert not wal_fixed((3, 37, 2)) and not wal_fixed((3, 51, 2)) and not wal_fixed((3, 52, 0))
    assert all(wal_fixed(v) for v in [(3, 44, 6), (3, 50, 7), (3, 51, 3), (3, 53, 0)])


def test_request_retry_cache_seed_and_idempotent_start(store, opamp):
    context = setup(store, opamp)
    key = begin(store, context, phase='initial')
    store.call('start', key, {('M1', 'm'): 3})
    assert begin(store, context, phase='initial') == key
    store.call('finish', key, dict(result(), simulator_invocations=1))
    cache = store.call('begin', *context, dict(source='cache', cache_eval_id=key), eval_id='cache')
    store.call('finish', cache, result())
    for seed in (1, 2):
        new = begin(store, context, str(seed), seed=seed, sample_id=seed, retry=seed)
        store.call('finish', new, result())
    summary = store.call('read', 'run', context[0])['summary']
    assert summary['evaluations'] == 4 and summary['cache_hits'] == 1
    assert summary['real_simulations'] == 1
    assert summary['first_feasible']['real_simulations'] == 1
    with pytest.raises(ValueError):
        store.call('start', cache, {})
    with pytest.raises(ValueError, match='random sample'):
        store.call('begin', *context, dict(source='cache', cache_eval_id=key, seed=21))


def test_commit_failure_retains_pending_and_artifacts(opamp, tmp_path):
    root = tmp_path / 'failure'
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        context = setup(store, opamp)
        key = begin(store, context)
        workspace = store.call('workspace', key)
        (Path(workspace['path']) / 'precious.raw').write_bytes(b'keep')
        store.call('workspace_finished', workspace['token'])
        # A real SQLite transaction abort, not a mocked success return.
        with sqlite3.connect(store.path) as connection:
            connection.execute("CREATE TRIGGER reject_result BEFORE UPDATE OF result ON evaluations "
                               "BEGIN SELECT RAISE(ABORT, 'disk failure fixture'); END")
        with pytest.raises(sqlite3.IntegrityError, match='disk failure'):
            store.call('finish', key, result())
        with pytest.raises(RuntimeError, match='previously failed'):
            begin(store, context, 'must_not_dispatch')
        assert store.call('read', 'evaluation', key)['result'] is None
        assert (Path(workspace['path']) / 'precious.raw').read_bytes() == b'keep'


def test_attachments_both_count_and_byte_limits_and_replacement(store, opamp):
    context = setup(store, opamp)
    for i, role in enumerate(['initial', 'initial', 'failure', 'failure', 'failure', 'best', 'best']):
        key = begin(store, context, str(i))
        workspace = store.call('workspace', key)
        (Path(workspace['path']) / 'wave.raw').write_bytes(bytes(range(256)) * 8)
        ack = store.call('finish', key, result())
        store.call('workspace_finished', workspace['token'])
        store.call('attach', ack, workspace['token'], role, 'timeout' if i == 2 else 'nonconverged')
        store.call('cleanup', ack, workspace['token'])
    rows = store.call('read', 'attachments')
    retained = [r for r in rows if r['status'] == 'retained']
    assert [r['role'] for r in retained].count('initial') == 1
    assert [r['role'] for r in retained].count('failure') == 2
    assert [r['role'] for r in retained].count('best') == 1
    assert sum(r['status'] == 'omitted' for r in rows) == 2
    assert sum(r['status'] == 'evicted' for r in rows) == 1
    store.config = replace(store.config, attachment_budget=1)
    key = begin(store, context, 'oversize')
    workspace = store.call('workspace', key)
    ack = store.call('finish', key, result())
    store.call('workspace_finished', workspace['token'])
    store.call('attach', ack, workspace['token'], 'best')
    assert store.call('read', 'attachments')[-1]['reason'] == 'attachment_byte_budget'


def test_managed_checkpoint_exact_learner_resume_and_retention(store, opamp, tmp_path):
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.recording.checkpoint import CheckpointManager
    from analog_optimizer.training.replay import ReplayBuffer
    from analog_optimizer.training.runner import collect_episode
    from analog_optimizer.training.sac import SACLearner
    torch.set_num_threads(1)
    torch.manual_seed(21)
    config = ModelConfig(hidden_dim=16, heads=2, layers=1)
    learner = SACLearner(experiment=dict(origin='synthetic', split='recording-test', designs=['opamp']), model_config=config)
    run = setup(store, opamp)[0]
    recorder = RunRecorder(store, run)
    checkpoints = CheckpointManager(store, run, store.root, interval=1)
    replay = ReplayBuffer(origin='synthetic', store=store)
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    with CircuitSizingEnv(backend, opamp, SPEC, tmp_path / 'env', max_steps=3, stop_on_success=False,
                          expected_origin='synthetic', recorder=recorder) as env:
        collect_episode(env, learner, replay, random.Random(5), batch_size=2, checkpoints=checkpoints)
    checkpoints.policy(learner, 3)
    checkpoints.policy(learner, 4)
    rows = [r for r in store.call('read', 'checkpoints') if r['status'] == 'retained']
    assert len(rows) == 3 and len(list((store.root / 'checkpoints').glob('*.pt'))) == 3
    assert [r['kind'] for r in rows].count('full') == 2
    latest = next(r['path'] for r in rows if r['kind'] == 'full' and r['step'] == 3)
    payload = torch.load(latest, weights_only=False)
    assert 'items' not in payload['replay'] and payload['replay_format'] == 'replay-ids-v1'
    expected = learner.update(replay.sample(2))
    restored, buffer, state = SACLearner.load(latest, experiment=learner.experiment, model_config=config, store=store)
    assert restored.update(buffer.sample(2)) == expected
    assert all(torch.equal(a, b) for a, b in zip(learner.actor.parameters(), restored.actor.parameters()))
    assert state['env_steps'] == 3
    with pytest.raises(ValueError, match='requires'):
        SACLearner.load(latest, experiment=learner.experiment, model_config=config)


def test_export_parquet_roundtrip_and_reader(store, opamp, tmp_path):
    import pyarrow.parquet as pq
    from analog_optimizer.recording.reader import RunReader
    context = setup(store, opamp)
    for i, value in enumerate([None, .9876543210123456]):
        key = begin(store, context, str(i))
        store.call('finish', key, result(value, 'timeout' if value is None else 'ok'))
    with RunReader(store.root) as reader:
        reader.export(context[0], tmp_path / 'export', batch_size=1)
        assert len(list(reader.evaluations(context[0]))) == 2
        with pytest.raises(ValueError, match='read-only'):
            reader.call('begin')
    metrics = pq.read_table(tmp_path / 'export/metrics.parquet').to_pylist()
    assert metrics[0]['value'] is None and metrics[1]['value'] == .9876543210123456
    rows = pq.read_table(tmp_path / 'export/evaluations.parquet').to_pylist()
    assert unpack(rows[1]['result'])['metrics']['score'] == metrics[1]['value']


def test_export_does_not_leak_other_run_states_with_same_task(store, opamp, tmp_path):
    import pyarrow.parquet as pq
    from analog_optimizer.envs.sizing import Observation
    from analog_optimizer.recording.reader import RunReader
    runs = [setup(store, opamp), setup(store, opamp)]
    assert runs[0][1:] == runs[1][1:]
    state_ids = []
    for i, context in enumerate(runs):
        key = begin(store, context, str(i))
        observation = Observation(opamp, SPEC, {'score': i + .01}, {'score': True},
                                  {'score': 'fixture'}, 'ok', 'synthetic', 2, key)
        store.call('finish', key, result(i + .01), observation=observation)
        state_ids.append(store.call('read', 'evaluation', key)['result']['state_id'])
    with RunReader(store.root) as reader:
        reader.export(runs[0][0], tmp_path / 'isolated', batch_size=2048)
    assert pq.read_table(tmp_path / 'isolated/states.parquet')['id'].to_pylist() == [state_ids[0]]


def _process_record(store, context, worker):
    """Finish worker-tagged evaluations in a subprocess and check idempotent acknowledgements."""
    for i in range(5):
        key = begin(store, context, f'{worker}-{i}', worker_id=str(worker))
        ack = store.call('finish', key, result(i / 10))
        assert store.call('finish', key, result(i / 10)) == ack


def test_spawned_process_workers_share_one_writer(opamp, tmp_path):
    import multiprocessing
    from analog_optimizer.recording import start_service
    manager, proxy = start_service(tmp_path / 'service', dict(min_free=0, temporary_reserve=0))
    try:
        context = setup(proxy, opamp)
        processes = [multiprocessing.get_context('spawn').Process(target=_process_record, args=(proxy, context, i)) for i in range(3)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(30)
            assert process.exitcode == 0
        assert proxy.call('read', 'run', context[0])['summary']['evaluations'] == 15
        for row in proxy.call('read', 'evaluations'):
            assert unpack(row['request'])['worker_id'] == row['id'].split('-')[0]
    finally:
        proxy.close()
        manager.shutdown()


def test_remote_helper_ownership_space_and_finished_gate(tmp_path):
    import subprocess
    import sys
    from analog_optimizer.recording.remote import HELPER
    root = tmp_path / 'spectre-host'
    def invoke(operation, **kwargs):
        """Run the remote-helper protocol in a local subprocess and decode its JSON response."""
        run = subprocess.run([sys.executable, '-c', HELPER, json.dumps(dict(operation=operation, root=str(root), **kwargs))],
                             capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stderr)
        return json.loads(run.stdout)
    workspace = invoke('create', eval_id='e', budget=1000000, min_free=0, reserve=1000)
    values = {k: workspace[k] for k in ('path', 'token', 'eval_id')}
    (Path(workspace['path']) / 'spectre.raw').write_bytes(b'important')
    with pytest.raises(RuntimeError, match='not finished'):
        invoke('delete', **values)
    with pytest.raises(RuntimeError, match='capacity'):
        invoke('create', eval_id='f', budget=1, min_free=0, reserve=1000)
    with pytest.raises(RuntimeError, match='ownership'):
        invoke('finish', **dict(values, token='wrong'))
    link = Path(workspace['path']) / 'foreign'
    link.symlink_to(tmp_path)
    with pytest.raises(RuntimeError, match='Symlink'):
        invoke('finish', **values)
    link.unlink()
    import os
    pid = Path(workspace['path']) / 'spectre.pid'
    pid.write_text(str(os.getpid()))
    with pytest.raises(RuntimeError, match='still alive'):
        invoke('finish', **values)
    pid.unlink()
    with pytest.raises(RuntimeError, match='escaped'):
        invoke('finish', **dict(values, path=str(tmp_path)))
    invoke('finish', **values)
    invoke('delete', **values)
    assert not Path(workspace['path']).exists()
    assert root.exists()


@pytest.mark.parametrize('executable', ['python3', 'python'])
def test_remote_helper_selects_available_interpreter(tmp_path, executable):
    import os
    import subprocess
    import sys
    from analog_optimizer.recording.remote import BridgeScratch
    commands = tmp_path / 'bin'
    commands.mkdir()
    (commands / executable).symlink_to(sys.executable)
    class Runner:
        """A local shell runner used to exercise remote interpreter selection."""
        def run_command(self, command, timeout):
            """Execute a local shell command with the test interpreter directory as its PATH."""
            return subprocess.run(['/bin/sh', '-c', command], timeout=timeout,
                                  env=dict(os.environ, PATH=str(commands)), capture_output=True, text=True)
    scratch = BridgeScratch.__new__(BridgeScratch)
    scratch.root, scratch.runner = str(tmp_path / 'scratch'), Runner()
    workspace = scratch.command('create', eval_id='e', budget=1000000, min_free=0, reserve=1000)
    values = {k: workspace[k] for k in ('path', 'token', 'eval_id')}
    scratch.command('finish', **values)
    scratch.command('delete', **values)
    assert not Path(workspace['path']).exists()


def _crash_after_commit(root, graph):
    """Exit the process after committing one evaluation and leaving another pending."""
    import os
    store = ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0))
    context = setup(store, graph)
    key = begin(store, context, 'committed')
    store.call('finish', key, result())
    begin(store, context, 'pending')
    os._exit(23)


def test_abnormal_process_exit_keeps_commits_and_pending(opamp, tmp_path):
    import multiprocessing
    root = tmp_path / 'crash'
    process = multiprocessing.get_context('spawn').Process(target=_crash_after_commit, args=(root, opamp))
    process.start()
    process.join(30)
    assert process.exitcode == 23
    with ExperimentStore(root) as recovered:
        assert recovered.call('read', 'evaluation', 'committed')['result']['metrics']['score'] == .96
        assert [r['id'] for r in recovered.call('pending')] == ['pending']


def test_checkpoint_failed_validation_preserves_previous_file(tmp_path, monkeypatch):
    import torch
    from analog_optimizer.recording.checkpoint import atomic_torch_save
    path = tmp_path / 'saved.pt'
    atomic_torch_save({'value': 1}, path)
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise IOError('checkpoint verification fixture')
    monkeypatch.setattr(torch, 'load', fail)
    with pytest.raises(IOError, match='verification'):
        atomic_torch_save({'value': 2}, path)
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]


def test_best_selection_uses_constraints_before_explicit_objective(store, opamp):
    run = store.call('run', {'selection': {'objective': {'metric': 'score', 'direction': 'max'}}})
    task, gid = store.call('task', opamp, SPEC)
    for i, (value, reward) in enumerate([(.6, 999.), (.96, -100.), (.99, -200.)]):
        key = begin(store, (run, task, gid), str(i), phase='initial' if i == 0 else 'training')
        store.call('finish', key, dict(result(value), reward=reward))
    summary = store.call('read', 'run', run)['summary']
    assert summary['best_feasible']['eval_id'] == '2'
    assert summary['best_infeasible']['eval_id'] == '0'
    assert summary['initial']['eval_id'] == '0'


def test_cancellation_and_long_errors_are_recorded_without_cleanup(store, opamp, tmp_path):
    backend = SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3})
    recorder = RunRecorder(store, setup(store, opamp)[0])
    def cancel(request):
        raise KeyboardInterrupt('取消' * 20000)
    with CircuitSizingEnv(backend, opamp, SPEC, tmp_path / 'env', stop_on_success=False,
                          expected_origin='synthetic', recorder=recorder) as env:
        env.reset()
        backend.run_simulation = cancel
        with pytest.raises(KeyboardInterrupt):
            env.step({k: 0. for k in env.mapper.group_ids})
    rows = store.call('read', 'evaluations')
    last = store.call('read', 'evaluation', rows[-1]['id'])
    assert last['result']['status'] == 'cancelled'
    assert len(last['result']['error_summary'].encode('utf8')) <= 16384
    assert list((store.root / 'temporary').iterdir())


def test_project_snapshot_captures_uncommitted_sources_without_pdk(tmp_path):
    from analog_optimizer.recording.provenance import project_snapshot, fingerprint
    source = tmp_path / 'project.py'
    source.write_text('x = 1.234567890123456\n')
    snapshot = project_snapshot(tmp_path, ['project.py'])
    assert snapshot['git_commit'] is None and snapshot['git_status'] == 'unavailable'
    assert snapshot['files']['project.py'] == source.read_bytes()
    assert fingerprint(source)['bytes'] == source.stat().st_size
    (tmp_path / 'license.dat').write_text('do not copy')
    with pytest.raises(ValueError):
        project_snapshot(tmp_path, ['license.dat'])
