"""The RL model's own label (record 7.159; user, 2026-10-03: "remove the project name box in the Project module. Give the RL
model its own label, independent of the project name"). A run that saves a model is remembered under the label, the
default model to load follows it, the entries remembered under a project name before still answer, and a configuration
without a label keeps the hashes it had. Everything MOCK."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from gator_workbench import runs, schema
from gator_workbench.api import create_app

from helpers import execute, make_config, roots_for


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
    run = lambda method, save=True: SimpleNamespace(output=SimpleNamespace(save_checkpoints=save), run=SimpleNamespace(search=SimpleNamespace(method=method)))
    assert runs.saves_rl_model(run('sac')) and runs.saves_rl_model(run('llm_warmstart'))
    assert not runs.saves_rl_model(run('llm'))                  # LLM only: no policy weights
    assert not runs.saves_rl_model(run('sac', save=False))      # a Single baseline simulation


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
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False))
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
