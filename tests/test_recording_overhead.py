"""Admission integrity, bounded inspection and redundant-I/O regression checks."""
from copy import deepcopy
from dataclasses import replace
import sqlite3

import pytest

from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.recording import ExperimentStore, RecordingConfig, RunRecorder
from analog_optimizer.recording.codec import pack, unpack
from analog_optimizer.recording.reader import RunReader
from analog_optimizer.recording.report import format_overview
from analog_optimizer.training.replay import ReplayBuffer, Transition


SPEC = (MetricSpec('score', 'fixture', 'min', 1., lower=.95),)


def record_steps(root, graph, steps=2):
    """Collect recorded synthetic transitions in a temporary store, closing the store if collection fails."""
    store = ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0))
    run = store.call('run', {})
    recorder = RunRecorder(store, run)
    items = []
    try:
        with CircuitSizingEnv(SyntheticSizingBackend(graph, targets={'w': .4, 'c': -.3}), graph, SPEC,
                              root / 'collector', max_steps=steps, stop_on_success=False,
                              expected_origin='synthetic', recorder=recorder) as env:
            observation, _ = env.reset()
            for _ in range(steps):
                proposal = {key: .1 for key in env.mapper.group_ids}
                step = env.step(proposal)
                items.append(Transition.from_step(observation, proposal, step))
                observation = step[0]
        return store, run, items
    except BaseException:
        store.close()
        raise


def test_admission_never_reconstructs_states_and_rejects_changed_content(opamp, tmp_path, monkeypatch):
    store, _, items = record_steps(tmp_path / 'db', opamp)
    with store:
        replay = ReplayBuffer(origin='synthetic', store=store)
        def forbidden(*args):
            pytest.fail('admission must not load dynamic states')
        monkeypatch.setattr(store, '_load_state', forbidden)
        for item in items:
            replay.add(item)
        changed = replace(items[0], next_observation=deepcopy(items[0].next_observation))
        changed.next_observation.graph.metadata['extra_dynamic_field'] = 123
        with pytest.raises(ValueError, match='differs from durable'):
            replay.add(changed)
        with pytest.raises(ValueError, match='committed'):
            replay.add(replace(items[0], candidate_id='uncommitted'))
        with pytest.raises(ValueError, match='differs from durable'):
            replay.add(replace(items[0], record_path='sqlite:wrong/provenance'))
        assert len(replay) == 2


def test_failed_transaction_cannot_authorize_admission(opamp, tmp_path, monkeypatch):
    store, run, items = record_steps(tmp_path / 'db', opamp)
    with store:
        row = store.call('read', 'evaluation', items[0].candidate_id)
        transition = store.call('read', 'transition', items[0].candidate_id)
        key = store.call('begin', run, row['task_id'], row['graph_id'], dict(source='mock'))
        transition.update(candidate_id=key, record_path=f'sqlite:{run}/{key}')
        monkeypatch.setattr(store, '_summary', lambda row: (_ for _ in ()).throw(ValueError('injected rollback')))
        with pytest.raises(ValueError, match='injected rollback'):
            store.call('finish', key, row['result'], observation=transition['next_observation'], transition=transition)
        with pytest.raises(ValueError, match='committed'):
            store.call('verify_transition', key, 'anything')
        assert store.call('read', 'evaluation', key)['result'] is None


def test_full_recovery_detects_corruption_and_old_rows_fall_back(opamp, tmp_path):
    root = tmp_path / 'db'
    store, _, items = record_steps(root, opamp)
    replay = ReplayBuffer(origin='synthetic', store=store)
    replay.add(items[0])
    manifest = replay.manifest()
    store.close()
    with sqlite3.connect(root / 'experiments.sqlite3') as db:
        original = unpack(db.execute('SELECT data FROM transitions WHERE id=?', (items[0].candidate_id,)).fetchone()[0])
        modified = dict(original, record_path='sqlite:corrupted')
        db.execute('UPDATE transitions SET data=? WHERE id=?', (pack(modified), items[0].candidate_id))
    with RunReader(root) as reader:
        with pytest.raises(ValueError, match='fingerprint'):
            ReplayBuffer.from_manifest(manifest, reader)
    with sqlite3.connect(root / 'experiments.sqlite3') as db:
        original.pop('replay_fingerprint')  # Genuine pre-optimization row format.
        db.execute('UPDATE transitions SET data=? WHERE id=?', (pack(original), items[0].candidate_id))
    with RunReader(root) as reader:
        restored = ReplayBuffer.from_manifest(manifest, reader)
        restored.add(items[0])
        assert restored.sample(1)[0].fingerprint() == items[0].fingerprint()


def test_no_repeated_asset_registration_or_next_state_write(opamp, tmp_path, monkeypatch):
    from collections import Counter
    with ExperimentStore(tmp_path / 'db', RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', {})
        recorder = RunRecorder(store, run)
        assets, state_calls, queries = Counter(), [], []
        asset, state = store._op_asset, store._state
        def count_asset(kind, value):
            assets[kind] += 1
            return asset(kind, value)
        def count_state(observation, *args):
            state_calls.append(observation)
            return state(observation, *args)
        monkeypatch.setattr(store, '_op_asset', count_asset)
        monkeypatch.setattr(store, '_state', count_state)
        store._op_trace = lambda: store.db.set_trace_callback(queries.append)
        store.call('trace')
        with CircuitSizingEnv(SyntheticSizingBackend(opamp, targets={'w': .4, 'c': -.3}), opamp, SPEC,
                              tmp_path / 'env', max_steps=3, stop_on_success=False,
                              expected_origin='synthetic', recorder=recorder) as env:
            env.reset()
            for _ in range(3):
                env.step({key: .2 for key in env.mapper.group_ids})
        assert assets['condition'] == assets['simulator_version'] == 1
        assert len(state_calls) == 7  # reset + two distinct state objects per step
        assert sum(q.startswith('INSERT INTO states') for q in queries) == 4
        row = store.call('read', 'evaluation', store.call('read', 'evaluations')[-1]['id'])
        assert 'metrics' not in row['result']['environment']
        assert row['result']['metrics']['score'] is not None
        assert 'condition' not in row['result']['environment']


def test_combined_workspace_transactions_keep_commit_and_liveness_gates(opamp, tmp_path):
    import os
    from pathlib import Path
    with ExperimentStore(tmp_path / 'db', RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', {})
        task, graph = store.call('task', opamp, SPEC)
        workspace = store.call('begin_workspace', run, task, graph, dict(source='mock'), eval_id='pending')
        assert store.call('begin_workspace', run, task, graph, dict(source='mock'), eval_id='pending') == workspace
        path = Path(workspace['path'])
        (path / 'important').write_text('result')
        with pytest.raises((ValueError, KeyError)):
            store.call('finalize_workspace', dict(eval_id='pending'), workspace['token'])
        assert path.exists()
        receipt = store.call('finish', 'pending', dict(status='ok', metrics={'score': .5},
            metric_validity={'score': True}, metric_units={'score': 'fixture'}, simulator_invocations=0))
        (path / 'spectre.pid').write_text(str(os.getpid()))
        with pytest.raises(ValueError, match='still alive'):
            store.call('finalize_workspace', receipt, workspace['token'])
        assert path.exists()
        (path / 'spectre.pid').unlink()
        store.call('finalize_workspace', receipt, workspace['token'])
        store.call('finalize_workspace', receipt, workspace['token'])
        assert not path.exists()
        assert len(store.call('read', 'evaluations')) == 1


def test_cleanup_metadata_rollback_can_be_reconciled_without_losing_core(opamp, tmp_path, monkeypatch):
    from pathlib import Path
    with ExperimentStore(tmp_path / 'db', RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', {})
        task, graph = store.call('task', opamp, SPEC)
        workspace = store.call('begin_workspace', run, task, graph, dict(source='mock'))
        receipt = store.call('finish', workspace['eval_id'], dict(status='ok', metrics={'score': .5},
            metric_validity={'score': True}, metric_units={'score': 'fixture'}, simulator_invocations=0))
        cleanup = store._op_finalize_workspace
        def cleanup_then_rollback(*args):
            """Delete retained artifacts before injecting a metadata rollback failure."""
            cleanup(*args)
            raise ValueError('injected post-delete rollback')
        monkeypatch.setattr(store, '_op_finalize_workspace', cleanup_then_rollback)
        with pytest.raises(ValueError, match='post-delete'):
            store.call('finalize_workspace', receipt, workspace['token'])
        assert not Path(workspace['path']).exists()
        assert store.call('read', 'evaluation', workspace['eval_id'])['result']['metrics']['score'] == .5
        monkeypatch.setattr(store, '_op_finalize_workspace', cleanup)
        store.call('finalize_workspace', receipt, workspace['token'])
        assert store.call('read', 'workspaces')[0]['cleaned'] == 1
        assert store.call('read', 'attachments')[0]['reason'] == 'workspace_missing_after_cleanup_or_recovery'


def test_summary_counts_constraints_pending_and_legacy_compatibility(opamp, tmp_path, monkeypatch):
    root = tmp_path / 'db'
    with ExperimentStore(root, RecordingConfig(min_free=0, temporary_reserve=0)) as store:
        run = store.call('run', {})
        task, graph = store.call('task', opamp, SPEC)
        for i, (status, value) in enumerate([('ok', .3), ('ok', .96), ('timeout', None), ('ok', .2)]):
            key = store.call('begin', run, task, graph, dict(source='mock', phase='initial' if i == 0 else 'training'))
            store.call('finish', key, dict(status=status, error_class='timeout' if value is None else None,
                metrics={'score': value}, metric_units={'score': 'fixture'}, metric_validity={'score': value is not None},
                applied_parameters={('M1', 'w'): 1.234567890123456e-6}, simulator_invocations=0))
        key = store.call('begin', run, task, graph, dict(source='mock'))
        store.call('start', key, {})
        store.call('end_run', run)
        with RunReader(root) as reader:
            monkeypatch.setattr(reader, 'evaluations', lambda _: pytest.fail('new overview must not scan history'))
            report = reader.overview(recent=2)
        assert report['lifecycle'] == 'ended_with_pending'
        assert report['pending_by_state'] == {'running': 1}
        assert report['summary']['outcome_counts'] == {'feasible': 1, 'infeasible': 2, 'failed': 1}
        assert report['summary']['error_counts'] == {'timeout': 1}
        assert report['summary']['best_feasible']['constraints'][0]['met']
        assert not report['summary']['initial']['constraints'][0]['met']
        assert len(report['recent_evaluations']) == 2
        text = format_overview(report)
        assert '1.234567890123456e-06' in text and '未达标 2 / 失败 1' in text
    with sqlite3.connect(root / 'experiments.sqlite3') as db:
        old = unpack(db.execute('SELECT summary FROM runs WHERE id=?', (run,)).fetchone()[0])
        for key in ('breakdown_complete', 'outcome_counts', 'error_counts', 'source_counts', 'status_counts'):
            old.pop(key)
        db.execute('UPDATE runs SET summary=? WHERE id=?', (pack(old), run))
    with RunReader(root) as reader:
        legacy = reader.overview(run, recent=0)
        assert legacy['summary']['outcome_counts'] == report['summary']['outcome_counts']
        with pytest.raises(KeyError):
            reader.overview('missing')
        with pytest.raises(ValueError):
            reader.overview(recent=1000)


def test_checkpoint_metadata_uses_the_position_in_the_saved_file(opamp, tmp_path, monkeypatch):
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.recording.checkpoint import CheckpointManager
    from analog_optimizer.training.sac import SACLearner
    store, run, items = record_steps(tmp_path / 'db', opamp)
    with store:
        learner = SACLearner(experiment=dict(origin='synthetic', split='checkpoint-position', designs=['mock-opamp']),
                             model_config=ModelConfig(hidden_dim=16, heads=2, layers=1))
        replay = ReplayBuffer(origin='synthetic', store=store)
        replay.add(items[0])
        original = learner.save
        def save_then_commit(*args, **kwargs):
            """Commit another evaluation after checkpoint saving to expose a moving database position."""
            position = original(*args, **kwargs)
            row = store.call('read', 'evaluation', items[0].candidate_id)
            key = store.call('begin', run, row['task_id'], row['graph_id'], dict(source='mock'))
            store.call('finish', key, row['result'])
            return position
        monkeypatch.setattr(learner, 'save', save_then_commit)
        path = CheckpointManager(store, run, store.root).maybe_save(learner, replay, 1, force=True)
        payload = torch.load(path, weights_only=False)
        metadata = unpack(store.call('read', 'checkpoints')[0]['data'])
        assert metadata['database'] == payload['replay']['database']
        assert store.call('position')['evaluation_seq'] > metadata['database']['evaluation_seq']
