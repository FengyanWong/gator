"""M5 leakage, isolation and cost accounting acceptance (the port-GNN behavioural test left with port_gnn, 2026-09-24)."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.backends.backend import SimulationStatus
from analog_optimizer.backends.synthetic_sizing import SyntheticSizingBackend
from analog_optimizer.envs.sizing import CircuitSizingEnv
from analog_optimizer.evaluation.benchmark import (
    PatternSearch, admit_transition, benchmark_models, run_benchmark, run_episode, transfer_weights, weight_digest)
from analog_optimizer.evaluation.transfer import TransferTask, aggregate_runs, freeze_protocol, same_topology, validate_split
from analog_optimizer.measurements.specs import MetricSpec
from analog_optimizer.models.graph_transformer import ModelConfig
from analog_optimizer.training.replay import ReplayBuffer
from analog_optimizer.training.sac import SACLearner
from research_support import cpu


def task(graph, name='train', partition='train', target=.99, transfer='specification'):
    return TransferTask(name, partition, transfer, 'toy_ota', graph,
                        (MetricSpec('score', 'fixture', 'min', 1, lower=target),))


def learner(origin='synthetic', mode='local_port_attention', encoder=None):
    return SACLearner(experiment=dict(origin=origin, split='unit-test', designs=['fixture']),
                      model_config=ModelConfig(hidden_dim=16, heads=2, layers=2, attention_mode=None if encoder else mode,
                                               encoder_type=encoder))


def make_env(t, steps, output):
    return CircuitSizingEnv(SyntheticSizingBackend(t.graph, targets={'w': .4, 'c': -.3}),
                            t.graph, t.specs, output, max_steps=steps, stop_on_success=False,
                            expected_origin='synthetic')


def rename(graph):
    g = deepcopy(graph)
    ids = {d.id: f'device_{i}' for i, d in enumerate(g.devices)}
    nets = {n.id: f'net_{i}' for i, n in enumerate(g.nets)}
    g.devices = [replace(d, id=ids[d.id]) for d in reversed(g.devices)]
    g.nets = [replace(n, id=nets[n.id]) for n in reversed(g.nets)]
    g.connections = [replace(c, device_id=ids[c.device_id], net_id=nets[c.net_id]) for c in reversed(g.connections)]
    g.parameters = {ids[k]: v for k, v in g.parameters.items()}
    g.parameter_groups = [replace(p, id=f'parameter_{i}', members=tuple(
        replace(m, device_id=ids[m.device_id]) for m in p.members)) for i, p in enumerate(g.parameter_groups)]
    return g


def test_topology_identity_rejects_renaming_and_sizing_as_new(opamp, ldo):
    assert same_topology(opamp, rename(opamp))
    resized = deepcopy(opamp)
    resized.parameters['input_left']['w'] = replace(resized.parameters['input_left']['w'], value=3e-6)
    assert same_topology(opamp, resized)
    assert not same_topology(opamp, ldo)
    changed = deepcopy(opamp)
    c = changed.connections[0]
    changed.connections[0] = replace(c, net_id=next(n.id for n in changed.nets if n.id != c.net_id))
    assert not same_topology(opamp, changed)


def test_split_rejects_alias_leakage_and_reweighted_goal(opamp):
    tasks = [task(opamp), task(opamp, 'validation', 'validation', .95), task(opamp, 'test', 'test', .98)]
    validate_split(tasks)
    with pytest.raises(ValueError, match='isomorphic'):
        validate_split(tasks[:2] + [task(rename(opamp), 'test', 'test', .98, 'topology')])
    renamed = task(rename(opamp), 'test', 'test', .99)
    renamed = replace(renamed, specs=(replace(renamed.specs[0], scale=2, weight=.1),))
    with pytest.raises(ValueError, match='Leaked'):
        validate_split(tasks[:2] + [renamed])


def test_split_rejects_missing_partition_and_wrong_family(opamp, tmp_path):
    with pytest.raises(ValueError, match='Freeze'):
        validate_split([task(opamp)])
    tasks = [task(opamp), task(opamp, 'validation', 'validation', .95), task(opamp, 'test', 'test', .98)]
    with pytest.raises(ValueError, match='same declared family'):
        validate_split(tasks[:2] + [replace(tasks[2], family='other')])
    sha = freeze_protocol(tmp_path / 'protocol.json', tasks, {'seeds': [1, 2, 3]})
    assert json.loads((tmp_path / 'protocol.json').read_text())['sha256'] == sha
    with pytest.raises(FileExistsError):
        freeze_protocol(tmp_path / 'protocol.json', tasks, {})


def test_frozen_policy_never_updates_and_baseline_cost_counts(opamp, tmp_path):
    t = task(opamp, 'test', 'test', target=0)
    model = learner()
    before = weight_digest(model)
    result = run_episode(make_env(t, 3, tmp_path), t, 'gt_frozen', learner=model)
    assert result['calls'] == 4 and result['first_feasible_call'] == 1
    assert result['completed'] and not result['right_censored']
    assert result['updates'] == result['replay_insertions'] == model.updates == 0
    assert result['weight_before'] == result['weight_after'] == before
    assert result['restoration']['state'] == 'restored'
    assert len(result['best_so_far']) == 4


def test_validation_update_rejected_before_backend_calls(opamp, tmp_path):
    t = task(opamp, 'validation', 'validation')
    env = make_env(t, 2, tmp_path)
    with pytest.raises(ValueError, match='Partition/phase'):
        run_episode(env, t, 'gt_adapt', phase='adaptation', learner=learner(),
                    replay=ReplayBuffer(origin='synthetic'))
    assert env.backend.calls == 0
    with pytest.raises(ValueError, match='must not receive'):
        run_episode(env, t, 'gt_frozen', learner=learner(), replay=ReplayBuffer(origin='synthetic'))


def test_replay_rejects_wrong_task_and_heldout_pretraining(opamp, tmp_path):
    t = task(opamp)
    with make_env(t, 2, tmp_path) as env:
        obs, _ = env.reset()
        action = {k: .2 for k in env.mapper.group_ids}
        step = env.step(action)
        replay = ReplayBuffer(origin='synthetic')
        with pytest.raises(ValueError, match='another task'):
            admit_transition(replay, task(opamp, target=.9), 'pretrain', obs, action, step)
        with pytest.raises(ValueError, match='Partition/phase'):
            admit_transition(replay, replace(t, partition='test'), 'pretrain', obs, action, step)
        assert len(replay) == 0
        admit_transition(replay, t, 'pretrain', obs, action, step)
        assert len(replay) == 1


def test_transfer_copies_weights_without_optimizer_replay_or_aliasing(opamp, tmp_path):
    source = learner()
    t = task(opamp)
    source_replay = ReplayBuffer(origin='synthetic')
    run_episode(make_env(t, 3, tmp_path), t, 'gt_pretrain', phase='pretrain', learner=source,
                replay=source_replay, batch_size=2)
    destination = learner()
    transfer_weights(source, destination)
    assert weight_digest(source) == weight_digest(destination)
    assert destination.updates == 0 and not destination.actor_optimizer.state
    with torch.no_grad():
        next(destination.actor.parameters()).add_(1)
    assert weight_digest(source) != weight_digest(destination)
    assert len(source_replay) == 3
    with pytest.raises(ValueError, match='Incompatible'):
        transfer_weights(source, learner(encoder='rgcn'))                     # another architecture is refused


def test_infrastructure_failure_is_censored_and_charged(opamp, tmp_path):
    t = task(opamp, 'test', 'test', target=1)
    env = make_env(t, 3, tmp_path)
    original = env.backend.run_simulation
    def fail_second(request):
        result = original(request)
        if env.backend.calls == 2:
            return replace(result, status=SimulationStatus.TRANSPORT_ERROR, candidate_evaluated=False,
                           reason_code='injected_transport_error', retryable=True)
        return result
    env.backend.run_simulation = fail_second
    result = run_episode(env, t, 'random')
    assert result['right_censored'] and result['first_feasible_call'] is None
    assert result['calls'] == 2 and result['call_budget'] == 4
    assert result['failure_counts'] == {'transport_error': 1}
    assert result['restoration']['state'] == 'restored'


def test_exception_during_simulation_keeps_cost_and_restores(opamp, tmp_path):
    t = task(opamp, 'test', 'test')
    env = make_env(t, 3, tmp_path)
    def fail(request):
        raise RuntimeError('injected exception')
    env.backend.run_simulation = fail
    with pytest.raises(RuntimeError, match='injected'):
        run_episode(env, t, 'random')
    result = json.loads((env.directory / 'run.json').read_text())
    assert result['calls'] == 1 and result['right_censored']
    assert result['failure_counts'] == {'execution_error': 1}
    assert result['restoration']['state'] == 'restored'


def test_pattern_search_polls_bounds_then_improves(opamp):
    from analog_optimizer.parameters.actions import ActionMapper
    search = PatternSearch(ActionMapper(opamp).groups)
    def reward(action):
        return -sum((a-.4)**2 for a in action.values())
    search.observe(None, reward(search.center))
    initial = search.best
    for _ in range(32):
        action = search.propose()
        assert all(-1 <= a <= 1 for a in action.values())
        search.observe(action, reward(action))
    assert search.best > initial


def test_multi_seed_report_keeps_censoring():
    rows = [dict(task='test', method='random', seed=seed, success=success, calls=4, wall_seconds=.1,
                 best_reward=0 if success else -.2, first_feasible_call=2 if success else None,
                 time_to_first_feasible_seconds=.01 if success else None)
            for seed, success in [(1, True), (2, False), (3, False)]]
    report = aggregate_runs(rows)[0]
    assert report['runs'] == 3 and report['success_rate'] == pytest.approx(1/3)
    assert report['censored_runs'] == 2 and report['calls'] == 12
    assert report['first_feasible_calls'] == [2, None, None]
    assert report['success_wilson_95'][0] < 1/3 < report['success_wilson_95'][1]


def test_suite_budget_replay_and_pretrain_isolation(opamp, tmp_path):
    tasks = [task(opamp, target=.9), task(opamp, 'validation', 'validation', .95),
             task(opamp, 'test', 'test', .999)]
    settings = dict(seeds=[17], pretrain_steps=2, test_steps=3, batch_size=2, max_calls=25, encoders=['graph_transformer'])
    report = run_benchmark(tasks, make_env, tmp_path, origin='synthetic', settings=settings,
                           provenance={'test': True}, progress=lambda x: None)
    assert report['completed'] and report['calls'] == report['planned_calls'] == 25    # 3 pretrain + 2 validation + 5 x 4
    assert report['synthetic_calls'] == 25 and report['real_simulation_calls'] == 0
    assert len(report['test_runs']) == 5                # gt scratch/frozen/adapt, random, pattern search
    assert all(r['calls'] == 4 for r in report['test_runs'])
    for method in ('gt_scratch', 'gt_adapt'):
        row = next(r for r in report['test_runs'] if r['method'] == method)
        assert row['updates'] == 2 and row['replay_insertions'] == 3
        payload = torch.load(tmp_path / f'test-{method}-17.pt', weights_only=False)
        assert all(t.observation.specs == tasks[-1].specs for t in payload['replay']['items'])
    for model in ('gt',):
        payload = torch.load(tmp_path / f'{model}-17-pretrain.pt', weights_only=False)
        assert all(t.observation.specs == tasks[0].specs for t in payload['replay']['items'])
    random_run = next(r for r in report['test_runs'] if r['method'] == 'random')
    scratch = next(r for r in report['test_runs'] if r['method'] == 'gt_scratch')
    a, b = [json.loads(open(r['records'][1]).read())['proposal'] for r in (random_run, scratch)]
    assert a == b
    assert next(r for r in report['test_runs'] if r['method'] == 'gt_adapt')['pretraining_plus_online_calls'] == 7
    assert report['unexecuted_test_runs'] == []


def test_suite_rejects_budget_before_backend_creation(opamp, tmp_path):
    tasks = [task(opamp), task(opamp, 'validation', 'validation', .95), task(opamp, 'test', 'test', .98)]
    with pytest.raises(ValueError, match='exceed'):
        run_benchmark(tasks, lambda *a: pytest.fail('Should not create backend'), tmp_path,
                      origin='synthetic', settings=dict(seeds=[1], pretrain_steps=2, test_steps=3, batch_size=2,
                                                       max_calls=24, encoders=['graph_transformer']), provenance={})


def test_aborted_suite_keeps_failed_run_and_unexecuted_runs(opamp, tmp_path):
    tasks = [task(opamp), task(opamp, 'validation', 'validation', .95), task(opamp, 'test', 'test', .98)]
    def factory(t, steps, output):
        env = make_env(t, steps, output)
        if t.partition == 'test':
            def fail(request):
                raise RuntimeError('test phase failure')
            env.backend.run_simulation = fail
        return env
    with pytest.raises(RuntimeError, match='test phase failure'):
        run_benchmark(tasks, factory, tmp_path, origin='synthetic', settings=dict(
            seeds=[17], pretrain_steps=2, test_steps=3, batch_size=2, max_calls=25, encoders=['graph_transformer']),
            provenance={}, progress=lambda x: None)
    report = json.loads((tmp_path / 'report.json').read_text())
    assert not report['completed'] and report['calls'] == 6      # 3 pretrain + 2 validation + the failing test call
    assert len(report['test_runs']) == 1 and report['test_runs'][0]['right_censored']
    assert len(report['unexecuted_test_runs']) == 4
    assert report['aggregate'][0]['censored_runs'] == 1


@pytest.mark.parametrize('encoders', [[], ['gatv2', 'gatv2'], ['unknown'], 'gatv2', ['gat'], ['port_gnn'], ['mlp'], ['gcn'], None])
def test_invalid_encoder_selection_fails_before_backend_creation(opamp, tmp_path, encoders):
    tasks = [task(opamp), task(opamp, 'validation', 'validation', .95), task(opamp, 'test', 'test', .98)]
    with pytest.raises(ValueError, match='encoders'):
        run_benchmark(tasks, lambda *a: pytest.fail('Should not create backend'), tmp_path,
                      origin='synthetic', settings=dict(seeds=[1], pretrain_steps=2, test_steps=2,
                                                       batch_size=2, max_calls=100, encoders=encoders), provenance={})


def test_selected_encoders_have_complete_isolated_transfer_matrix(opamp, tmp_path):
    tasks = [task(opamp, target=.9), task(opamp, 'validation', 'validation', .95),
             task(opamp, 'test', 'test', .999)]
    settings = dict(seeds=[17], pretrain_steps=2, test_steps=2, batch_size=2, max_calls=48,
                    encoders=['graph_transformer', 'rgcn', 'gatv2'], hidden_dim=16, heads=2, layers=2)
    report = run_benchmark(tasks, make_env, tmp_path, origin='synthetic', settings=settings,
                           provenance={'test': True}, progress=lambda x: None)
    assert report['completed'] and report['calls'] == report['planned_calls'] == 48
    assert len(report['test_runs']) == 11 and report['unexecuted_test_runs'] == []
    assert report['cost_by_partition']['train']['calls'] == 9
    assert report['cost_by_partition']['validation']['calls'] == 6
    assert report['cost_by_partition']['test']['calls'] == 33
    for label, encoder in zip(('gt', 'rgcn', 'gatv2'), settings['encoders']):
        source = torch.load(tmp_path / f'{label}-17-pretrain.pt', weights_only=False)
        assert source['contract']['model_config']['encoder_type'] == encoder
        assert all(t.observation.specs == tasks[0].specs for t in source['replay']['items'])
        for phase in ('scratch', 'frozen', 'adapt'):
            row = next(r for r in report['test_runs'] if r['method'] == f'{label}_{phase}')
            assert row['model_config']['encoder_type'] == encoder and row['parameters'] > 0
            assert row['calls'] == 3 and row['restoration']['state'] == 'restored'
            assert row['updates'] == (0 if phase == 'frozen' else 1)
            assert row['pretraining_plus_online_calls'] == (3 if phase == 'scratch' else 6)
            if phase == 'frozen':
                cost = next(c for c in report['pretraining_costs'] if c['model'] == label)
                assert row['weight_before'] == row['weight_after'] == cost['weight_sha256']
                assert row['replay_insertions'] == 0
            else:
                payload = torch.load(tmp_path / f'test-{label}_{phase}-17.pt', weights_only=False)
                assert all(t.observation.specs == tasks[-1].specs for t in payload['replay']['items'])
    settings['max_calls'] = 47
    with pytest.raises(ValueError, match='exceed'):
        run_benchmark(tasks, lambda *a: pytest.fail('Should not create backend'), tmp_path / 'over-budget',
                      origin='synthetic', settings=settings, provenance={})
    models, methods, validation = benchmark_models({'encoders': ['rgcn']})
    assert list(models) == ['rgcn'] and validation == ('rgcn',)
    assert set(methods) == {'rgcn_scratch', 'rgcn_frozen', 'rgcn_adapt', 'random', 'pattern_search'}


@pytest.mark.parametrize('encoder', ['rgcn', 'gatv2'])
def test_weight_transfer_rejects_cross_architecture(encoder):
    destination = SACLearner(experiment=dict(origin='synthetic', split='unit-test', designs=['fixture']),
                             model_config=ModelConfig(hidden_dim=16, heads=2, layers=2, encoder_type=encoder))
    with pytest.raises(ValueError, match='Incompatible'):
        transfer_weights(learner(), destination)
