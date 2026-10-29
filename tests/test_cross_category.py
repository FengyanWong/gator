"""M6 class holdout, metric identity, variable actions and replay isolation."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

torch = pytest.importorskip('torch')
pytest.importorskip('torch_geometric')

from analog_optimizer.envs.sizing import graph_contract
from analog_optimizer.evaluation.benchmark import benchmark_call_budget, run_benchmark, weight_digest
from analog_optimizer.evaluation.cross_category import category_tasks, load_categories
from analog_optimizer.evaluation.transfer import digest, freeze_protocol, validate_split
from analog_optimizer.models import ENCODER_TYPES, ModelConfig
from analog_optimizer.models.inputs import context_features
from analog_optimizer.training.replay import ReplayBuffer, Transition
from analog_optimizer.training.sac import SACLearner
from research_support import cpu

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def categories():
    """Load the repository category contracts for offline split and budget checks."""
    return load_categories(ROOT)


def settings(schema, encoders=('graph_transformer',)):
    """Build a short single-seed benchmark configuration from the supplied schema and encoders."""
    return dict(seeds=[17], encoders=list(encoders), pretrain_steps=2, test_steps=2,
                batch_size=2, hidden_dim=16, heads=2, layers=1, max_calls=200,
                spec_schema=asdict(schema))


@pytest.mark.parametrize('heldout', ['opamp', 'ldo', 'vco'])
def test_category_holdouts_are_disjoint_and_frozen(categories, heldout, tmp_path):
    factory, schema, _ = categories
    tasks = category_tasks(factory, heldout)
    assert {t.circuit_class for t in tasks if t.partition == 'train'} == set(factory.graphs)-{heldout}
    assert {t.circuit_class for t in tasks if t.partition == 'validation'} == set(factory.graphs)-{heldout}
    assert {t.circuit_class for t in tasks if t.partition == 'test'} == {heldout}
    path = tmp_path / 'protocol.json'
    sha = freeze_protocol(path, tasks, settings(schema))
    payload = json.loads(path.read_text())
    assert payload.pop('sha256') == sha == digest(payload)
    assert payload['version'] == 'm6-cross-category-v1'


def test_category_rejects_missing_labels_and_development_leakage(categories):
    factory, _, _ = categories
    tasks = category_tasks(factory, 'vco')
    with pytest.raises(ValueError, match='explicit circuit classes'):
        validate_split([replace(t, circuit_class=None) if t.partition == 'train' else t for t in tasks])
    target = next(t for t in tasks if t.partition == 'test')
    for partition in ('train', 'validation'):
        leaked = replace(target, id='leaked', partition=partition, transfer='specification',
                         specs=(replace(target.specs[0], lower=.1),))
        with pytest.raises(ValueError, match='Held-out category'):
            validate_split([leaked] + tasks if partition == 'train' else tasks + [leaked])
    with pytest.raises(ValueError, match='test task'):
        replace(target, partition='validation')


def test_category_cannot_relabel_topology_or_lineage(categories):
    factory, _, _ = categories
    tasks = category_tasks(factory, 'vco')
    source = next(t for t in tasks if t.partition == 'train')
    for changes in (dict(graph=deepcopy(source.graph)), dict(family=source.family)):
        altered = [replace(t, **changes) if t.partition == 'test' else t for t in tasks]
        with pytest.raises(ValueError, match='relabeling'):
            validate_split(altered)
    alias = replace(source, id='alias', family='other', circuit_class='another')
    with pytest.raises(ValueError, match='relabeling'):
        validate_split(tasks + [alias])


def test_unknown_metrics_and_over_budget_fail_before_backend(categories, tmp_path):
    factory, schema, _ = categories
    tasks = category_tasks(factory, 'vco')
    config = settings(schema)
    assert benchmark_call_budget(tasks, config) == 25
    def forbidden(*args):
        pytest.fail('Backend must not be constructed')
    config['max_calls'] = 24
    with pytest.raises(ValueError, match='exceed'):
        run_benchmark(tasks, forbidden, tmp_path/'budget', origin='synthetic', settings=config, provenance={})
    config['max_calls'] = 25
    config.pop('spec_schema')
    with pytest.raises(ValueError, match='metric identity/unit'):
        run_benchmark(tasks, forbidden, tmp_path/'schema', origin='synthetic', settings=config, provenance={})


def test_suite_budget_is_global_and_dry_run_creates_no_output(tmp_path):
    command = [sys.executable, str(ROOT/'examples/benchmark_cross_category.py'), '--dry-run',
               '--encoders', 'graph_transformer', 'rgcn', 'gatv2',
               '--seeds', '17', '--pretrain-steps', '2', '--test-steps', '2', '--output', str(tmp_path/'output')]
    result = subprocess.run(command+['--max-calls', '189'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['planned_calls'] == 189
    assert summary['encoders'] == ['graph_transformer', 'rgcn', 'gatv2']
    result = subprocess.run(command+['--max-calls', '188'], capture_output=True, text=True)
    assert result.returncode != 0 and 'across all folds' in result.stderr
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('encoder', ['mlp', 'gcn'])
def test_m6_cli_rejects_excluded_encoders_before_output(tmp_path, encoder):
    result = subprocess.run([sys.executable, str(ROOT/'examples/benchmark_cross_category.py'),
        '--encoders', encoder, '--output', str(tmp_path/'output')], capture_output=True, text=True)
    assert result.returncode != 0 and 'invalid choice' in result.stderr
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('encoder', ENCODER_TYPES)
def test_all_encoders_mix_classes_metrics_actions_and_resume(categories, encoder, tmp_path):
    factory, schema, _ = categories
    replay = ReplayBuffer(origin='synthetic', seed=17)
    observations = []
    for name in ('ldo', 'opamp', 'vco'):
        task = next(t for t in category_tasks(factory, name) if t.partition == 'test')
        with factory(task, 2, tmp_path) as env:
            obs, _ = env.reset()
            observations.append(obs)
            proposal = {key: .1 for key in env.mapper.group_ids}
            step = env.step(proposal)
            replay.add(Transition.from_step(obs, proposal, step))
            assert set(obs.metrics) == {task.specs[0].metric_id}
            assert obs.origin == 'synthetic'
            slots = context_features(obs, schema)[:-11].reshape(len(schema.metrics), 21)    # spec-input-v2 layout
            assert slots[:, 0].sum() == 1 and slots[:, 10].sum() == 1
            if name == 'vco':
                for stage in ('a', 'b', 'c'):
                    values = env.backend.read_parameters()
                    assert values[f'stage_{stage}/pull_up', 'w'] == pytest.approx(
                        2 * values[f'stage_{stage}/pull_down', 'w'])
    config = ModelConfig(hidden_dim=16, heads=2, layers=1, encoder_type=encoder)
    model = SACLearner(experiment=dict(origin='synthetic', split='unit-test', designs=['three-toy-classes']),
                       spec_schema=schema, model_config=config)
    assert model.batch(observations).action_counts.tolist() == [1, 2, 3]
    before = weight_digest(model)
    update = model.update(replay.sample(3))
    assert sorted(update['action_counts']) == [1, 2, 3] and weight_digest(model) != before
    path = tmp_path / 'mixed.pt'
    model.save(path, replay)
    expected = model.update(replay.sample(3))
    resumed, replay2, _ = SACLearner.load(path, experiment=model.experiment, spec_schema=schema, model_config=config)
    assert resumed.update(replay2.sample(3)) == expected
    assert weight_digest(resumed) == weight_digest(model)


def test_cross_category_matrix_isolated_shared_source_and_frozen_target(categories, tmp_path):
    factory, schema, provenance = categories
    tasks = category_tasks(factory, 'vco')
    config = settings(schema, ('graph_transformer', 'rgcn', 'gatv2'))
    report = run_benchmark(tasks, factory, tmp_path, origin='synthetic', settings=config,
                           provenance=provenance, progress=lambda message: None)
    assert report['completed'] and report['calls'] == report['planned_calls'] == 63
    assert report['real_simulation_calls'] == 0 and len(report['test_runs']) == 11
    assert {r['method'] for r in report['test_runs']} == {
        f'{encoder}_{phase}' for encoder in ('gt', 'rgcn', 'gatv2')
        for phase in ('scratch', 'frozen', 'adapt')
    } | {'random', 'pattern_search'}
    source_tasks = [t for t in tasks if t.partition == 'train']
    target = next(t for t in tasks if t.partition == 'test')
    for cost in report['pretraining_costs']:
        assert cost['circuit_classes'] == ['ldo', 'opamp'] and cost['calls'] == 6
        payload = torch.load(tmp_path/f'{cost["model"]}-17-pretrain.pt', weights_only=False)
        items = payload['replay']['items']
        assert len(items) == 4
        assert {t.observation.specs for t in items} == {t.specs for t in source_tasks}
        assert all(any(graph_contract(item.observation.graph) == graph_contract(t.graph)
                       for t in source_tasks) for item in items)
    for row in report['test_runs']:
        assert row['circuit_class'] == 'vco' and row['transfer'] == 'category'
        assert row['restoration']['state'] == 'restored' and row['calls'] == 3
        if row['upfront_cost']:
            assert row['weight_before'] == row['upfront_cost']['weight_sha256']
        if row['method'].endswith('_frozen'):
            assert row['updates'] == row['replay_insertions'] == 0
            assert row['weight_before'] == row['weight_after']
        if row['phase'] in ('scratch', 'adaptation'):
            payload = torch.load(tmp_path/f'vco-test-{row["method"]}-17.pt', weights_only=False)
            assert len(payload['replay']['items']) == 2
            assert all(t.observation.specs == target.specs and
                       graph_contract(t.observation.graph) == graph_contract(target.graph)
                       for t in payload['replay']['items'])
