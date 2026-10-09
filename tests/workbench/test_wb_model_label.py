"""The RL model's own label (record 7.159; user, 2026-10-03: "remove the project name box in the Project module. Give the RL
model its own label, independent of the project name"). A run that saves a model is remembered under the label, the
default model to load follows it, the entries remembered under a project name before still answer, and a configuration
without a label keeps the hashes it had. Everything MOCK."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, runs, schema

from helpers import execute, make_config, roots_for, workbench_app


def test_the_label_is_typed_or_the_task_run_label():
    config = make_config('/tmp')
    assert config.run.model_label is None
    assert runs.model_label(config) == config.project.task_name
    assert runs.model_label(make_config('/tmp', run=dict(model_label='  ldo-gat-a  '))) == 'ldo-gat-a'
    assert runs.model_label(make_config('/tmp', run=dict(model_label='   '))) == config.project.task_name


def test_a_configuration_without_a_label_keeps_its_hashes():
    config = make_config('/tmp')
    data = config.model_dump(mode='json')
    before = dict(data, run={k: v for k, v in data['run'].items() if k != 'model_label'})     # written before the field existed
    assert schema.config_hash(before) == schema.config_hash(config)
    labelled = make_config('/tmp', run=dict(model_label='ldo-gat-a'))
    assert schema.config_hash(labelled) != schema.config_hash(config)
    assert schema.task_definition_hash(labelled) == schema.task_definition_hash(config)       # the same task


def test_only_a_run_that_saves_a_model_is_filed_under_a_label():
    run = lambda save=True: SimpleNamespace(output=SimpleNamespace(save_checkpoints=save))
    assert runs.saves_rl_model(run())
    assert not runs.saves_rl_model(run(save=False))             # a Baseline simulation


def test_a_run_is_remembered_under_its_label_not_the_project_name(tmp_path):
    config = make_config(tmp_path, run=dict(model_label='label-remembered'), project=dict(name='project-label-test'))
    layout, manifest = runs.prepare_run(config, roots_for(tmp_path))
    remembered = runs.load_settings()['last_run']
    assert remembered['label-remembered'] == str(layout.run_dir)
    assert remembered.get('project-label-test') != str(layout.run_dir)
    assert manifest['model_label'] == 'label-remembered'


def test_a_baseline_leaves_the_label_alone(tmp_path):
    config = make_config(tmp_path, run=dict(model_label='label-baseline'), output=dict(save_checkpoints=False))
    _, manifest = runs.prepare_run(config, roots_for(tmp_path))
    assert 'label-baseline' not in runs.load_settings().get('last_run', {})
    assert manifest['model_label'] is None


def test_the_default_model_follows_the_label_then_the_old_project_name(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(model_label='label-default')), tmp_path)
    client = TestClient(workbench_app(tmp_path))
    found = client.get('/api/runs/default-model', params=dict(label='label-default')).json()
    assert found['run_dir'] == str(layout.run_dir) and found['checkpoint_id'] == 'latest'
    # remembered under a project name before the label existed: asked when the label has none
    runs.save_settings(last_run={**runs.load_settings().get('last_run', {}), 'old-project-name': str(layout.run_dir)})
    legacy = client.get('/api/runs/default-model', params=dict(label='label-unused', project='old-project-name')).json()
    assert legacy['run_dir'] == str(layout.run_dir)
    none = client.get('/api/runs/default-model', params=dict(label='label-unused')).json()
    assert none['run_dir'] is None and 'label' in none['reason']
    listed = client.get('/api/runs/models', params=dict(output_root=str(tmp_path))).json()['models']
    assert [m['model_label'] for m in listed if m['run_dir'] == str(layout.run_dir)] == ['label-default']


# ---------------------------------------------------------------------------- names of their own (record 7.225)
# User, 2026-10-06: "for saved rl models with same names add numbering to them by default and add a functionality of rename
# saved model". No two models under one output root carry the same name; a rename lives in the run folder's model_label.json.
from gator_workbench.storage.atomic import read_json


def test_a_second_model_under_the_same_label_is_numbered(tmp_path):
    roots = roots_for(tmp_path)
    first, m1 = runs.prepare_run(make_config(tmp_path, run=dict(model_label='twin')), roots)
    second, m2 = runs.prepare_run(make_config(tmp_path, run=dict(model_label='twin')), roots)
    third, m3 = runs.prepare_run(make_config(tmp_path, run=dict(model_label=' twin ')), roots)
    assert (m1['model_label'], m2['model_label'], m3['model_label']) == ('twin', 'twin (2)', 'twin (3)')
    assert runs.load_settings()['last_run']['twin'] == str(third.run_dir)        # remembered under the label itself, as before
    rows = {r['run_dir']: r['model_label'] for r in runs.list_runs(roots)}
    assert rows == {str(first.run_dir): 'twin', str(second.run_dir): 'twin (2)', str(third.run_dir): 'twin (3)'}
    # no label typed: the task's run label, numbered the same way; a baseline takes no name
    a, ma = runs.prepare_run(make_config(tmp_path), roots)
    b, mb = runs.prepare_run(make_config(tmp_path), roots)
    _, mc = runs.prepare_run(make_config(tmp_path, output=dict(save_checkpoints=False)), roots)
    task = make_config(tmp_path).project.task_name
    assert (ma['model_label'], mb['model_label'], mc['model_label']) == (task, f'{task} (2)', None)
    assert runs.output_root_of(a.run_dir) == tmp_path and runs.output_root_of(first.run_dir) == tmp_path


def test_models_from_before_are_numbered_oldest_first_when_listed():
    rows = [dict(run_dir='/r/b', created_utc='2026-10-05T01:00', model_label='ota', renamed=False),
            dict(run_dir='/r/a', created_utc='2026-10-05T00:00', model_label='ota', renamed=False),
            dict(run_dir='/r/c', created_utc='2026-10-05T02:00', model_label='ota (2)', renamed=False),   # given at its start
            dict(run_dir='/r/d', created_utc='2026-10-04T00:00', model_label='ota', renamed=True),        # renamed: keeps its name
            dict(run_dir='/r/e', created_utc='2026-10-06T00:00', model_label=None, renamed=False)]        # a baseline: no model
    assert ckpt.unique_model_labels(rows) == {'/r/d': 'ota', '/r/a': 'ota (2)', '/r/b': 'ota (3)', '/r/c': 'ota (4)'}
    assert ckpt.unique_model_labels([]) == {}
    assert ckpt.free_model_label('x', set()) == 'x' and ckpt.free_model_label('x', {'x', 'x (2)'}) == 'x (3)'
    assert ckpt.free_model_label('x', {'x', 'x (3)'}) == 'x (2)'


def test_a_run_from_before_the_label_is_named_by_its_task_when_it_saved_a_model(tmp_path):
    from gator_workbench.storage.atomic import write_json
    old = dict(task_name='early_ota', created_utc='2026-09-21T00:00:00+00:00')        # no `model_label` key at all (before 7.159)
    saved, bare = tmp_path / 'saved', tmp_path / 'bare'
    (saved / 'checkpoints').mkdir(parents=True); (bare / 'checkpoints').mkdir(parents=True)
    write_json(saved / 'checkpoints' / 'latest.json', dict(checkpoint_id='ckpt-1'))
    assert ckpt.model_label_of(saved, old) == dict(model_label='early_ota', renamed=False)
    assert ckpt.model_label_of(bare, old) == dict(model_label=None, renamed=False)         # saved nothing: no model, no name
    assert ckpt.model_label_of(bare, dict(old, model_label=None)) == dict(model_label=None, renamed=False)   # a baseline since 7.159
    write_json(saved / 'model_label.json', dict(model_label=' renamed early '))
    assert ckpt.model_label_of(saved, old) == dict(model_label='renamed early', renamed=True)


def test_rename_a_saved_model(tmp_path):
    layout, _ = execute(make_config(tmp_path, run=dict(model_label='named')), tmp_path)
    other, _ = runs.prepare_run(make_config(tmp_path, run=dict(model_label='taken')), roots_for(tmp_path))
    client = TestClient(workbench_app(tmp_path))
    rename = lambda run_dir, name: client.post('/api/runs/model/rename', json=dict(run_dir=run_dir, model_label=name))
    done = rename(str(layout.run_dir), '  gold  ')
    assert done.status_code == 200 and done.json() == dict(run_dir=str(layout.run_dir), model_label='gold', previous='named')
    record = read_json(layout.run_dir / 'model_label.json')
    assert record['model_label'] == 'gold' and record['given_at_start'] == 'named' and record['history'][0]['model_label'] == 'named'
    assert read_json(layout.manifest)['model_label'] == 'named'            # the manifest keeps the name given at the start
    listed = client.get('/api/runs/models', params=dict(output_root=str(tmp_path))).json()['models']
    assert [m['model_label'] for m in listed] == ['gold']
    assert [r['model_label'] for r in runs.list_runs(roots_for(tmp_path)) if r['run_dir'] == str(layout.run_dir)] == ['gold']
    # refused: a name another model carries (also one without a save point yet), an empty name, an over-long one, not a run
    taken = rename(str(layout.run_dir), 'taken')
    assert taken.status_code == 409 and taken.json()['detail']['code'] == 'name_taken' and '"taken"' in taken.json()['detail']['message']
    assert rename(str(layout.run_dir), '   ').status_code == 422
    assert rename(str(layout.run_dir), 'x' * 81).status_code == 422
    assert rename(str(tmp_path / 'nowhere'), 'x').status_code in (403, 404)
    assert ckpt.model_label_of(layout.run_dir)['model_label'] == 'gold'                      # nothing changed by a refusal
    # the same name again changes nothing; the default model answers to the new name; a later start under it is numbered
    assert rename(str(layout.run_dir), 'gold').status_code == 200
    found = client.get('/api/runs/default-model', params=dict(label='gold')).json()
    assert found['run_dir'] == str(layout.run_dir) and found['checkpoint_id'] == 'latest'
    _, manifest = runs.prepare_run(make_config(tmp_path, run=dict(model_label='gold')), roots_for(tmp_path))
    assert manifest['model_label'] == 'gold (2)'
    assert rename(str(other.run_dir), 'gold (2)').status_code == 409          # a numbered name is a name like any other
    assert rename(str(other.run_dir), 'gold (3)').status_code == 200
