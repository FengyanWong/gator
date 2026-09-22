"""Choosing a REAL task brings that task's rows: the parameters its profile fixes and, for a verified circuit, its TARGETS
OF RECORD - not the MOCK fixture's `score`. Local files only; nothing here contacts a bridge or starts a simulation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import profiles, recipes, schema, tasks
from gator_workbench.api import create_app
from gator_workbench.compile import compile_task
from gator_workbench.validation import registry_for, validate
from test_wb_api import probe
from test_wb_profiles import ROWS, config as cell_config, connection_file, read_cell

REPO = Path(__file__).resolve().parents[2]
VERIFIED = sorted(tasks.REAL_PROFILES)


def of_record(name):
    file, *keys = tasks.REAL_TARGETS_OF_RECORD[name]
    specs = json.loads((REPO / file).read_text())
    for key in keys:
        specs = specs[key]
    return specs


def as_config(raw, **run):
    return schema.WorkbenchConfig.model_validate(dict(raw, run=dict(dict(max_evaluations=200), **run)))


@pytest.mark.parametrize('name', VERIFIED)
def test_a_verified_circuit_starts_from_its_targets_of_record(name):
    raw = tasks.starter_config(f'real:{name}')
    assert set(raw) == {'project', 'circuit', 'parameters', 'measurements', 'targets'}       # no `run`: a real budget is never suggested
    assert raw['circuit'] == dict(source='registered_task', task_id=f'real:{name}', pdk_id='gpdk045',
                                  circuit_class=tasks.REAL_PROFILES[name]['circuit_class'])
    assert raw['project'] == dict(name=name.replace('_', '-'), task_name=name)               # a real run is not filed under mock_*
    assert 'score' not in [t['metric_id'] for t in raw['targets']] and 'fixture' not in [t['unit'] for t in raw['targets']]
    assert all('of record' in t['basis'] and tasks.REAL_TARGETS_OF_RECORD[name][0] in t['basis'] for t in raw['targets'])

    configured, graph = as_config(raw), tasks._verified_profile(name).optimization_graph()
    report = validate(configured, graph=graph, provided_metrics={spec['metric_id'] for spec in of_record(name)})
    assert [(i.level, i.code, i.path) for i in report.issues if i.level in ('error', 'blocker', 'warning')] == []
    compiled = compile_task(configured, graph)
    from analog_optimizer.envs.sizing import graph_contract
    assert graph_contract(compiled.graph) == graph_contract(graph)                           # exactly the rows a real run accepts
    assert [(s.metric_id, s.unit, s.comparator, s.lower, s.upper, s.scale) for s in compiled.specs] == [
        (s['metric_id'], s['unit'], s['comparator'], s.get('lower'), s.get('upper'), s['scale']) for s in of_record(name)]
    assert [m['source_name'] for m in raw['measurements']] == [t['metric_id'] for t in raw['targets']]


def test_each_result_is_labelled_with_the_analysis_that_produces_it():
    analysis = lambda name: {m['source_name']: m['analysis'] for m in tasks.starter_config(f'real:{name}')['measurements']}
    assert analysis('gpdk045_ota5') == dict(phase_margin_estimate_deg='ac', supply_power_w='dc', output_dc_v='dc',
                                            unity_downward_crossings='ac', gain_db_at_start='ac', unity_gain_hz='ac')
    ldo = analysis('gpdk045_ldo')
    assert (ldo['ldo_psrr_1khz_db'], ldo['ldo_step_deviation_v'], ldo['ldo_line_regulation_v_per_v'], ldo['supply_power_w']) == ('ac', 'tran', 'dc', 'dc')
    assert set(analysis('gpdk045_vco').values()) == {'tran'}                                  # an oscillator: everything from its transient run


def test_the_ldo_and_vco_bring_the_registry_of_their_experiment_and_the_ota_keeps_the_default():
    m6 = json.loads((REPO / 'configs/m6_real_cross_category.json').read_text())['schema']
    for name in ('gpdk045_ldo', 'gpdk045_vco'):
        configured = as_config(tasks.starter_config(f'real:{name}'))
        assert registry_for(configured) == {metric: unit for metric, unit, _ in m6['metrics']}
        spec_schema = compile_task(configured, tasks._verified_profile(name).optimization_graph()).spec_schema
        assert spec_schema.version == m6['version'] and [list(m) for m in spec_schema.metrics] == m6['metrics']
    for name in ('gpdk045_ota5', 'gpdk045_ota7'):                                             # unchanged: models stay interchangeable
        configured = as_config(tasks.starter_config(f'real:{name}'))
        assert 'score' in registry_for(configured) and 'ldo_psrr_1khz_db' not in registry_for(configured)
        assert compile_task(configured, tasks._verified_profile(name).optimization_graph()).spec_schema.version == 'spec-input-v1'
    stated = as_config(tasks.starter_config('real:gpdk045_ldo'))                              # a registry stated in the configuration still wins
    stated.run.advanced.spec_registry = [schema.SpecRegistryEntry(metric_id='supply_power_w', unit='W', reference=1e-5)]
    assert registry_for(stated) == dict(supply_power_w='W')
    mock = as_config(tasks.starter_config('synthetic:gpdk045_ota5'))
    assert 'score' in registry_for(mock) and 'ldo_psrr_1khz_db' not in registry_for(mock)     # the MOCK task brings no registry of record


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
    assert listed['real:gpdk045_ota5']['pdk_id'] == 'gpdk045' and listed['synthetic:gpdk045_ota5']['pdk_id'] == 'gpdk045'
    for key, row in listed.items():                                                           # the page tells a starter-made project name by these
        assert row['starter_project'] == tasks.starter_config(key)['project'], key
    answer = client.get('/api/tasks/starter', params=dict(task_key='real:gpdk045_ota5'))
    assert answer.status_code == 200
    targets = {t['metric_id']: t for t in answer.json()['targets']}
    assert targets['gain_db_at_start']['constraint'] == '>=' and targets['gain_db_at_start']['lower'] == 25.01
    assert targets['supply_power_w']['constraint'] == 'interval' and targets['supply_power_w']['upper'] == 2.1e-06
    assert client.get('/api/tasks/starter', params=dict(task_key='real:no_such_circuit')).status_code == 404
