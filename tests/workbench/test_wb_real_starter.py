"""Choosing a REAL task brings that task's rows: the parameters its profile fixes, and no invented target - not the MOCK
fixture's `score`. The built-in verified circuits and their targets of record are gone (the last two, OTA7 and LDO, on
2026-09-30, record 7.128, with their tests). Local files only; nothing here contacts a bridge or starts a simulation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import profiles, recipes, schema, tasks
from gator_workbench.api import create_app
from gator_workbench.compile import compile_task
from gator_workbench.validation import validate
from test_wb_api import probe
from test_wb_profiles import ROWS, config as cell_config, connection_file, read_cell

REPO = Path(__file__).resolve().parents[2]


def as_config(raw, **run):
    return schema.WorkbenchConfig.model_validate(dict(raw, run=dict(dict(max_evaluations=200), **run)))


def test_the_regulation_units_of_the_ldo_are_known():
    from gator_workbench import units
    assert units.canonical_unit('V/V') == 'V/V' and units.to_canonical(15, 'mV/V') == pytest.approx(0.015)
    assert units.canonical_unit('mV/mA') == 'V/A' and not units.compatible('V/A', 'ohm')


def test_the_mock_starter_is_what_it_was():
    raw = tasks.starter_config('synthetic:gpdk045_ota5')
    assert set(raw) == {'project', 'circuit', 'parameters', 'measurements', 'targets', 'run'}
    assert [t['metric_id'] for t in raw['targets']] == ['score'] and raw['circuit']['pdk_id'] == 'gpdk045'   # a real GPDK045 netlist (7.59)
    assert raw['run'] == dict(max_evaluations=60, seed=17)
    with pytest.raises(KeyError):
        tasks.starter_config('real:no_such_circuit')
    with pytest.raises(KeyError):
        tasks.starter_config('synthetic:no_such_fixture')
    with pytest.raises(KeyError):
        tasks.starter_config('synthetic:opamp')                                               # one of the four removed in 7.59


def test_a_generated_profile_gets_its_parameters_and_probes_and_no_invented_target(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, 'bridge_importable', lambda: True)
    read_cell(tmp_path)
    connection_file()
    made = profiles.create_profile('ring_osc_3stage', cell_config(ROWS), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    raw = tasks.starter_config('real:ring_osc_3stage')
    assert raw['targets'] == []                                                               # requirements are never inferred from the circuit
    assert [m['source_name'] for m in raw['measurements']] == list(recipes.RING_METRICS) and {m['analysis'] for m in raw['measurements']} == {'tran'}
    assert {m['source_name']: m['unit'] for m in raw['measurements']} == dict(recipes.RING_METRICS)
    assert raw['circuit'] == dict(source='registered_task', task_id='real:ring_osc_3stage', circuit_class='vco', pdk_id=made['pdk_id'])
    configured = as_config(raw)
    runtime = tasks.load_task(configured.circuit, profile_id='lab')
    report = validate(configured, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    assert sorted({i.code for i in report.issues if i.level in ('error', 'blocker')}) == ['no_hard_constraint']    # the one thing left to the user
    from analog_optimizer.envs.sizing import graph_contract
    assert graph_contract(compile_task(as_config(dict(raw, targets=[dict(
        metric_id='osc_frequency_hz', equation='m_osc_frequency_hz', unit='GHz', constraint='>=', lower=1.0, normalization_scale=1.0)])),
        runtime.base_graph).graph) == graph_contract(runtime.base_graph)


def test_the_api_serves_the_rows_and_each_task_names_its_pdk(tmp_path):
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    listed = {t['task_key']: t for t in client.get('/api/tasks').json()['tasks']}
    assert listed['synthetic:gpdk045_ota5']['pdk_id'] == 'gpdk045'                            # the tests' stand-in
    for key, row in listed.items():                                                           # the page tells a starter-made project name by these
        assert row['starter_project'] == tasks.starter_config(key)['project'], key
    answer = client.get('/api/tasks/starter', params=dict(task_key='synthetic:gpdk045_ota5'))
    assert answer.status_code == 200 and [t['metric_id'] for t in answer.json()['targets']] == ['score']
    assert client.get('/api/tasks/starter', params=dict(task_key='real:no_such_circuit')).status_code == 404
    for removed in tasks.REMOVED_REAL_TASKS:                                                  # 7.73 and 7.128
        assert client.get('/api/tasks/starter', params=dict(task_key=removed)).status_code == 404


def test_the_removed_example_tasks_are_refused_in_words():
    """All four built-in verified tasks were removed on user request: real:gpdk045_ota5 and real:gpdk045_vco on 2026-09-23
    (status record 7.73, their example cells deleted from Virtuoso), real:gpdk045_ota7 and real:gpdk045_ldo on 2026-09-30
    (record 7.128, their example files deleted too). Nothing lists, loads or starts them any more, an old configuration
    naming one says why, and their names stay reserved (test_wb_profiles: a saved task cannot take such a name)."""
    listed = {t['task_key'] for t in tasks.list_tasks()}
    starter = tasks.starter_config('synthetic:gpdk045_ota5')
    for key in tasks.REMOVED_REAL_TASKS:
        assert key not in listed
        with pytest.raises(tasks.TaskBlocked, match='no longer exists') as raised:
            tasks.load_task(schema.CircuitReference(source='registered_task', task_id=key), allow_real=True)
        assert ('2026-09-30' in str(raised.value)) == (key in ('real:gpdk045_ota7', 'real:gpdk045_ldo'))
        with pytest.raises(KeyError):
            tasks.starter_config(key)
        old = as_config(dict(starter, circuit=dict(starter['circuit'], task_id=key)))
        assert ('error', 'task_removed') in {(i.level, i.code) for i in validate(old).issues}
