"""Choosing which saved RL model to load: every save point of a run is listed from its small
metadata files, a run without a saved model is never offered, a chosen EARLIER save point is the one
that really gets loaded, and pruning never removes a selected best policy. MOCK backend only."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, runs
from gator_workbench.api import create_app
from gator_workbench.storage import read_json
from helpers import SMALL_NET, execute, make_config, roots_for

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.
pytestmark = pytest.mark.xdist_group('test_wb_model_chooser')


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    """One MOCK run that saved several models: periodic saves every 6 evaluations plus the final one."""
    root = tmp_path_factory.mktemp('chooser')
    config = make_config(root, run=dict(max_evaluations=20, seed=5), project=dict(task_name='chooser_source'),
                         output=dict(checkpoint_every_evaluations=6))
    layout, state = execute(config, root)
    assert state == 'completed'
    return root, layout


def test_every_save_point_is_listed_oldest_first_without_hashing_a_file(trained, monkeypatch):
    _, layout = trained
    monkeypatch.setattr(ckpt, 'sha256_file', lambda path: pytest.fail(f'the list must not hash {path}'))
    listing = ckpt.list_checkpoints(layout.run_dir)
    points = listing['checkpoints']
    assert len(points) >= 3 and [p['kind'] for p in points[:-1]] == ['periodic'] * (len(points) - 1)
    assert points[-1]['kind'] == 'final' and points[-1]['is_latest'] and listing['latest'] == points[-1]['checkpoint_id']
    assert [p['is_latest'] for p in points[:-1]] == [False] * (len(points) - 1)
    evaluations = [p['evaluations'] for p in points]
    assert evaluations == sorted(evaluations) and evaluations[0] < evaluations[-1] == 20
    assert [p['created_utc'] for p in points] == sorted(p['created_utc'] for p in points)
    assert all(p['network'] == SMALL_NET and p['restoration_capability'] == 'full_state' for p in points)
    # No validation-set selection ever happened, so no best policy is offered (and the reason is carried along).
    assert listing['best_policy']['selected'] is None and listing['best_policy']['status'] == 'not_selected'
    assert not any(p['is_best_policy'] for p in points)


def test_an_earlier_save_point_is_the_model_that_really_gets_loaded(trained):
    root, layout = trained
    points = ckpt.list_checkpoints(layout.run_dir)['checkpoints']
    early, newest = points[0], points[-1]
    digest = {p['checkpoint_id']: ckpt.read_metadata(ckpt.resolve_checkpoint(layout.run_dir, p['checkpoint_id']))['weight_sha256']
              for p in (early, newest)}
    assert digest[early['checkpoint_id']] != digest[newest['checkpoint_id']]         # training moved the weights
    config = make_config(root, run=dict(max_evaluations=6, mode='frozen'), project=dict(task_name='frozen_early'))
    config.run.model_source.run_dir, config.run.model_source.checkpoint_id = str(layout.run_dir), early['checkpoint_id']
    target, state = execute(config, root)
    assert state == 'completed'
    assert read_json(target.manifest)['source_model']['checkpoint_id'] == early['checkpoint_id']
    frozen = ckpt.read_metadata(ckpt.resolve_checkpoint(target.run_dir, 'latest'))
    assert frozen['weight_sha256'] == digest[early['checkpoint_id']]                 # the early weights, not `latest`


def test_runs_without_a_saved_model_and_damaged_save_points_are_never_offered(tmp_path):
    saved, _ = execute(make_config(tmp_path, run=dict(max_evaluations=8), project=dict(task_name='with_model')), tmp_path)
    execute(make_config(tmp_path, run=dict(max_evaluations=8), project=dict(task_name='no_model'),
                        output=dict(save_checkpoints=False)), tmp_path)
    listed = runs.list_runs(roots_for(tmp_path))
    assert len(listed) == 2                                                          # both runs exist ...
    models = ckpt.saved_models(listed)
    assert [m['task_name'] for m in models] == ['with_model']                        # ... one holds a model
    model = models[0]
    assert model['run_dir'] == str(saved.run_dir) and model['circuit_task'] == 'synthetic:gpdk045_ota5' and model['mock'] is True
    assert model['network'] == SMALL_NET and model['trained_evaluations'] == 8
    assert model['latest'] == model['checkpoints'][-1]['checkpoint_id'] and model['saved_utc']
    json.dumps(models, allow_nan=False)                                              # plain JSON for the API
    # A half-written or damaged directory is not a model: no metadata -> not listed, and the rest still is.
    root = saved.run_dir / 'checkpoints'
    (root / '.staging-ckpt-00000099-deadbeef').mkdir()
    broken = root / 'ckpt-00000099-deadbeef'
    shutil.copytree(root / model['latest'], broken)
    (broken / 'metadata.json').write_text('{not json', encoding='utf8')
    assert [p['checkpoint_id'] for p in ckpt.list_checkpoints(saved.run_dir)['checkpoints']] == \
        [p['checkpoint_id'] for p in model['checkpoints']]
    # The run whose only save point is gone drops out of the chooser instead of failing on selection.
    shutil.rmtree(broken)
    for directory in root.glob('ckpt-*'):
        shutil.rmtree(directory)
    assert ckpt.saved_models(runs.list_runs(roots_for(tmp_path))) == []


def test_the_api_serves_the_list_and_keeps_the_path_restriction(trained, tmp_path):
    root, layout = trained
    client = TestClient(create_app(extra_output_roots=[str(root)], serve_frontend=False))
    response = client.get('/api/runs/models', params=dict(output_root=str(root)))
    assert response.status_code == 200
    models = response.json()['models']
    source = next(m for m in models if m['run_dir'] == str(layout.run_dir))
    assert source['task_name'] == 'chooser_source' and len(source['checkpoints']) >= 3
    assert {'checkpoint_id', 'kind', 'created_utc', 'evaluations', 'learner_updates', 'network',
            'restoration_capability', 'is_latest', 'is_best_policy'} <= set(source['checkpoints'][0])
    # The chosen save point is then described and verified exactly as `latest` always was.
    early = source['checkpoints'][0]['checkpoint_id']
    described = client.post('/api/runs/model', json=dict(run_dir=source['run_dir'], checkpoint_id=early)).json()
    assert described['description']['checkpoint_id'] == early and described['description']['file_problems'] == []
    assert client.get('/api/runs/models', params=dict(output_root=str(tmp_path / 'elsewhere'))).status_code == 403
    assert client.get('/api/runs/models', params=dict(output_root=str(root), include_mock=False)).json()['models'] == []


def test_pruning_never_removes_the_selected_best_policy(tmp_path):
    store = ckpt.CheckpointStore(tmp_path, run_id='r', task_id='t', task_definition_hash='h', keep_last=2)
    names = [f'ckpt-{n:08d}-aaaaaaaa' for n in (5, 10, 15, 20)]
    for name in names:
        (store.root / name).mkdir()
        (store.root / name / 'metadata.json').write_text(json.dumps(dict(checkpoint_id=name, kind='periodic')), encoding='utf8')
    (store.root / 'best_policy.json').write_text(json.dumps(dict(selected=names[0], status='selected')), encoding='utf8')
    removed = store._prune(names[-1])
    assert removed == [names[1]]                                                     # the oldest UNSELECTED periodic save
    assert sorted(p.name for p in store.root.glob('ckpt-*')) == [names[0], names[2], names[3]]


def test_an_incomplete_configuration_never_hides_the_saved_model(trained):
    """User report 2026-09-21: every chosen save point answered "CompileError: mp1_w: bounds are required" - a 500,
    because the configuration ON THE PAGE had an optimized row without bounds. The model's facts have nothing to do
    with that: they are still returned, and what is missing is said in plain words."""
    root, layout = trained
    client = TestClient(create_app(extra_output_roots=[str(root)], serve_frontend=False))
    raw = make_config(root).model_dump(mode='json')
    row = raw['parameters'][0]
    row['lower'] = row['upper'] = None
    response = client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest', config=raw))
    assert response.status_code == 200
    answer = response.json()
    assert answer['description']['checkpoint_id'] and answer['description']['file_problems'] == []       # the model is all there
    assert 'compatibility' not in answer
    said = answer['compatibility_unchecked']
    assert row['variable_id'] in said['what'] and 'no lower and no upper bound' in said['what'] and 'Parameters table' in said['what']
    assert 'says nothing about the saved model' in said['note'] and said['technical'] == f"CompileError: {row['variable_id']}: bounds are required"
    assert 'CompileError' not in said['title'] + said['what'] + said['note']                           # developer words stay folded away
    # With the bounds back the comparison is made as before.
    complete = client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest',
                                                        config=make_config(root).model_dump(mode='json'))).json()
    assert 'compatibility_unchecked' not in complete and complete['compatibility']['checks']
