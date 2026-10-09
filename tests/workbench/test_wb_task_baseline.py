"""Creation owns one fixed baseline; calibration and training controls cannot change it."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from gator_workbench import profiles, runs, tasks
from gator_workbench.api import task_baseline
from gator_workbench.storage.atomic import read_json
from helpers import make_config, workbench_app
from helpers import probe, wait_for


def test_fixed_configuration_uses_saved_task_and_one_launch(tmp_path, monkeypatch):
    saved = make_config(tmp_path).model_dump(mode='json')
    saved['run'].update(mode='frozen', seed=51, concurrency=4, max_evaluations=999, max_retries=3)
    saved['output'].update(save_checkpoints=True)
    monkeypatch.setattr(tasks, 'starter_config', lambda key: saved)
    config = task_baseline.configuration('real:new_task', profile_id='lab', output_root=str(tmp_path))
    assert config.parameters == make_config(tmp_path).parameters
    assert (config.run.mode, config.run.seed, config.run.concurrency, config.run.max_evaluations,
            config.run.max_spectre_launches, config.run.max_retries) == ('scratch', 0, 1, 1, 1, 0)
    assert config.run.connection_profile_id == 'lab' and config.run.rehearsal is None
    assert not config.output.save_checkpoints and not config.output.save_transition_archive


def test_creation_starts_baseline_once_and_specs_only_update_does_not(tmp_path, monkeypatch):
    """The actual API/worker on a synthetic fixture: fixed initial evaluation, no calibration or training."""
    config = make_config(tmp_path)
    monkeypatch.setattr(tasks, 'starter_config', lambda key: config.model_dump(mode='json'))
    monkeypatch.setattr(task_baseline, '_directory', lambda key: tmp_path)
    created = [True]
    monkeypatch.setattr(profiles, 'save_task', lambda *a, **k: dict(task_key='real:new_task', created=created[0],
        baseline_kept=not created[0], revision=1 if created[0] else 2, changed=[]))
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True))
    raw = config.model_dump(mode='json')
    runs.save_settings(concurrency=4)
    raw['run'].update(mode='frozen', seed=99, concurrency=4, max_evaluations=10000, max_retries=9)
    response = client.post('/api/virtuoso/task/save', json=dict(name='new_task', profile_id='lab', config=raw))
    assert response.status_code == 200, response.text
    baseline = response.json()['baseline']
    assert baseline['state'] == 'started', baseline
    status = wait_for(client, baseline['run_dir'])
    assert status['state'] == 'completed' and status['budget']['charged'] == 1
    assert status['learner_updates'] == 0 and status['calibration'] is None
    assert runs.load_settings()['concurrency'] == 4      # its fixed lane count is not a new training default
    assert client.get('/api/tasks/saving').json()['last']['answer']['baseline']['run_dir'] == baseline['run_dir']
    created[0] = False
    response = client.post('/api/virtuoso/task/save', json=dict(name='new_task', task='new_task', profile_id='lab', config=raw))
    assert response.status_code == 200 and 'baseline' not in response.json()
    assert read_json(tmp_path / task_baseline.FILE)['run_dir'] == baseline['run_dir']


def test_blocked_baseline_preserves_saved_task_and_live_retry_reuses_run(tmp_path, monkeypatch):
    monkeypatch.setattr(task_baseline, '_directory', lambda key: tmp_path)
    monkeypatch.setattr(tasks, 'starter_config', lambda key: (_ for _ in ()).throw(ValueError('Connection unavailable')))
    made = dict(task_key='real:new_task', created=True)
    task_baseline.after_save(SimpleNamespace(), made)
    assert made['baseline'] == dict(state='blocked', reason='Connection unavailable')
    assert task_baseline.status('real:new_task') == made['baseline']
    live = dict(state='running', worker_alive=True, run_dir='/fixture/run')
    monkeypatch.setattr(task_baseline, 'status', lambda key: live)
    assert task_baseline.start(SimpleNamespace(), 'real:new_task') is live


def test_ngspice_without_specs_checks_measurement_presence_only(tmp_path, monkeypatch):
    saved = make_config(tmp_path).model_dump(mode='json')
    saved['targets'] = []
    monkeypatch.setattr(tasks, 'starter_config', lambda key: saved)
    config = task_baseline.configuration('ngspice:new_task', output_root=str(tmp_path))
    assert config.targets[0].equation == 'm_score - m_score' and config.targets[0].lower == 0
    assert saved['targets'] == []                         # no optimization spec written into the task


def test_new_ngspice_task_automatically_simulates_its_saved_start(tmp_path):
    from fakes_connection import NGSPICE, EXAMPLE, ngspice_probe, write_profiles
    from gator_workbench.storage.dataset import DatasetReader
    if not NGSPICE:
        pytest.skip('ngspice is not installed')
    write_profiles(sim=dict(kind='ngspice_local', ngspice_bin=NGSPICE))
    client = TestClient(workbench_app(tmp_path, monitor=ngspice_probe(tmp_path), auto_check_on_start=True))
    response = client.post('/api/ngspice/task/save', json=dict(name='new_ota', text=EXAMPLE.read_text(),
        source_path=str(EXAMPLE), profile_id='sim', output_root=str(tmp_path)))
    assert response.status_code == 200, response.text
    made = response.json()
    assert made['baseline']['state'] == 'started', made['baseline']
    directory = Path(made['baseline']['run_dir'])
    status = wait_for(client, str(directory))
    assert status['state'] == 'completed' and status['budget']['charged'] == status['budget']['launches'] == 1, status
    evaluations = DatasetReader(directory / 'data').rows('evaluations')
    assert len(evaluations) == 1 and evaluations[0]['phase'] == 'baseline' and evaluations[0]['valid']
    assert status['learner_updates'] == 0 and status['calibration'] is None
    assert made['starter']['targets'] == []               # measuring does not invent an optimization specification
