"""The MOCK task synthetic:gpdk045_ota5 (user decision 2026-09-22, status record 7.59) - the netlist of the verified GPDK045
OTA5 circuit on the free analytic toy backend - was deleted from the workbench on 2026-09-30 (record 7.128). The tests
register it themselves as their stand-in (tests/conftest.py); the workbench refuses it, and the four toy-fixture tasks it
had replaced, with a plain reason. A model it trains never loads into a real run: that guard is circuit-independent and
tested in test_wb_aggregates (mock_isolation). Local files and the MOCK backend only."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import schema, task_registry, tasks
from gator_workbench.storage import read_json
from gator_workbench.api import create_app
from helpers import MOCK_TASK, execute, make_config, rows
from test_wb_api import probe

REPO = Path(__file__).resolve().parents[2]


def reference(task_id):
    return schema.CircuitReference(source='registered_task', task_id=task_id)


def test_there_is_one_mock_task_and_it_is_the_real_ota5_circuit():
    listed = [t for t in tasks.list_tasks() if t['kind'] == 'mock']
    assert [t['task_key'] for t in listed] == [MOCK_TASK]
    assert listed[0]['pdk_id'] == 'gpdk045' and listed[0]['circuit_class'] == 'opamp'
    assert 'MOCK' in listed[0]['description'] and 'OTA5' in listed[0]['description']
    mock, real = tasks.load_task(reference(MOCK_TASK)), tasks.REAL_PROFILES['gpdk045_ota5']
    assert mock.mock and 'MOCK' in mock.circuit['evaluation_backend']
    assert (mock.circuit['netlist_file'], mock.circuit['parser_config_file']) == (str(REPO / real['structure']), str(REPO / real['mapping']))
    assert sorted(d.id for d in mock.base_graph.devices if d.id.startswith('XU1/')) == [f'XU1/M{n}' for n in range(1, 6)]


def test_its_starter_is_the_three_width_groups_of_the_circuit():
    raw = tasks.starter_config(MOCK_TASK)
    assert [(p['variable_id'], p['instance_path'], p.get('binding_group')) for p in raw['parameters']] == [
        ('input_pair_width', 'XU1/M1', None), ('input_pair_width__XU1_M2', 'XU1/M2', 'input_pair_width'),
        ('mirror_pair_width', 'XU1/M3', None), ('mirror_pair_width__XU1_M4', 'XU1/M4', 'mirror_pair_width'),
        ('tail_width', 'XU1/M5', None)]
    assert raw['project'] == dict(name='mock-gpdk045-ota5', task_name='mock_gpdk045_ota5')
    assert [t['metric_id'] for t in raw['targets']] == ['score'] and [m['source_name'] for m in raw['measurements']] == ['score']


def test_a_short_run_is_free_and_labelled_mock(tmp_path):
    layout, state = execute(make_config(tmp_path, run=dict(max_evaluations=6, seed=5)), tmp_path)
    assert state == 'completed'
    assert '/mock/' in str(layout.run_dir).replace('\\', '/') and read_json(layout.manifest)['mock'] is True
    evaluated = rows(layout, 'evaluations')
    assert evaluated and all(row['provenance'] == 'mock' for row in evaluated)
    assert {row['instance_path'] for row in rows(layout, 'parameters')} == {f'XU1/M{n}' for n in range(1, 6)}


def test_the_workbench_itself_offers_no_mock_task(monkeypatch):
    monkeypatch.delenv(tasks.ENV_SYNTHETIC_FIXTURES, raising=False)
    assert tasks._registered_fixtures() == {}
    monkeypatch.setattr(task_registry, 'SYNTHETIC_FIXTURES', {})
    assert not [t for t in tasks.list_tasks() if t['kind'] == 'mock']


@pytest.mark.parametrize('removed', tasks.REMOVED_MOCK_TASKS)
def test_a_removed_mock_task_is_refused_with_a_plain_reason(removed, monkeypatch):
    monkeypatch.setattr(task_registry, 'SYNTHETIC_FIXTURES', {})                    # as in the workbench: no stand-in registered
    with pytest.raises(tasks.TaskBlocked) as caught:
        tasks.load_task(reference(removed))
    assert str(caught.value).startswith(f'{removed} no longer exists') and 'no MOCK task' in str(caught.value)
    with pytest.raises(KeyError):
        tasks.starter_config(removed)


def test_a_configuration_saved_with_a_removed_task_says_why_it_is_blocked(tmp_path):
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    assert [t['task_key'] for t in client.get('/api/tasks').json()['tasks'] if t['kind'] == 'mock'] == [MOCK_TASK]
    loaded = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:vco'))).json()
    assert loaded['loaded'] is False and loaded['blocker'].startswith('synthetic:vco no longer exists')
    assert client.get('/api/tasks/starter', params=dict(task_key='synthetic:vco')).status_code == 404
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit']['task_id'] = 'synthetic:vco'
    report = client.post('/api/config/validate', json=dict(config=config)).json()
    assert report['blocks_run'] and 'synthetic:vco no longer exists' in json.dumps(report['issues'])
