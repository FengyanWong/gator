"""Towards the first real baseline of a generated task: the measurements its circuit type produces, the gated no-simulation check, the first REAL baseline as its reference, the result registry its targets need (refactoring package D4: from test_wb_profiles)."""

import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import profiles, recipes, schema, tasks
from gator_workbench.paths import bridge_state_dir

from helpers import probe, workbench_app
from ring_cell_support import CIRCUIT, config, connection_file, read_cell, ROWS
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module


# ------------------------------------------------------------------------------------------------ towards the first real baseline
def measurement(measurement_id, source_name):
    """Describe a transient-frequency measurement supplied by the backend profile."""
    return dict(measurement_id=measurement_id, analysis='tran', result_source='backend_profile', source_name=source_name, unit='Hz')


def test_measurements_must_use_results_the_circuit_type_produces(tmp_path):
    read_cell(tmp_path)
    wrong = schema.WorkbenchConfig.model_validate(dict(circuit=CIRCUIT, parameters=ROWS, measurements=[measurement('f', 'frequency')], run=dict(max_evaluations=5)))
    with pytest.raises(profiles.ProfileError, match='Available: osc_frequency_hz'):
        profiles.create_profile('ring_m', wrong, recipe='ring_oscillator', expected_frequency_hz=1e9)
    right = wrong.model_copy(update=dict(measurements=[schema.MeasurementDefinition(**measurement('f', 'osc_frequency_hz'))]))
    assert profiles.create_profile('ring_m', right, recipe='ring_oscillator', expected_frequency_hz=1e9)['task_key'] == 'real:ring_m'


def test_the_no_simulation_check_is_gated_and_reports_the_step_that_failed(tmp_path):
    from gator_workbench import profile_preflight
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    fake = tmp_path / 'check.py'
    fake.write_text('import json, sys\nprint("bridge progress")\nprint(json.dumps(dict(profile_preflight=True, name=sys.argv[2], ok=False, simulated=False, deck=None,'
                    ' steps=[dict(step="profile", ok=True, detail="ok"), dict(step="connect", ok=False, detail="RuntimeError: Existing bridge tunnel required")])))\n')
    result = profile_preflight.preflight(probe(tmp_path), 'ring_osc_3stage', 'lab', command=[sys.executable, str(fake)])
    assert result['ok'] is False and result['simulated'] is False and [s['step'] for s in result['steps'] if not s['ok']] == ['connect']
    assert (Path(result['work_root']) / 'preflight.json').is_file() and Path(result['work_root']).parent.name == 'preflight'
    with pytest.raises(KeyError):
        profile_preflight.preflight(probe(tmp_path), 'no_such_profile', 'lab', command=[sys.executable, str(fake)])
    with pytest.raises(PermissionError):
        profile_preflight.preflight(probe(tmp_path, session_readiness='not_ready'), 'ring_osc_3stage', 'lab', command=[sys.executable, str(fake)])
    # in-process, offline: without a tunnel the adapter refuses at "connect" and the check reports it instead of raising.
    # The adapter's session lock lives in paths.bridge_state_dir(), which the test setup points into this test's folder.
    outcome = profile_preflight.run('ring_osc_3stage', 'lab', tmp_path / 'work')
    assert bridge_state_dir().is_dir() and bridge_state_dir().is_relative_to(tmp_path), outcome   # failed once under load: say why
    assert outcome['ok'] is False and outcome['simulated'] is False and outcome['steps'][0] == dict(step='profile', ok=True, detail=profile_preflight.MEANING['profile'])
    assert outcome['steps'][1]['step'] == 'connect' and outcome['steps'][1]['ok'] is False
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path, tunnel='failed', daemon='not_checked', session_readiness='not_checked')))
    # "Check against Virtuoso" became a part of the check before every run (consistency.py): its own route is gone
    assert client.post('/api/virtuoso/profile/preflight', json=dict(name='ring_osc_3stage', profile_id='lab')).status_code in (404, 405)
    from gator_workbench import runs
    runs.save_settings(output_root=str(tmp_path))          # the runs searched are this test's, not the default root's (the user's own)
    assert client.post('/api/virtuoso/profile/reference', json=dict(name='ring_osc_3stage')).json()['detail']['code'] == 'no_baseline_run'


def test_a_finished_real_baseline_becomes_the_reference_once(tmp_path, monkeypatch):
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    (run_dir / 'effective_config.json').write_text(json.dumps(dict(circuit=dict(source='registered_task', task_id='real:ring_osc_3stage'))))
    (run_dir / 'run_manifest.json').write_text(json.dumps(dict(run_id='r1', mock=False)))
    values = dict(zip(recipes.RING_METRICS, (1.2092e9, 1.96e-4, 1.96e-4, 0.999, 0.508, 1e-6, 1e-6, 3.1e-9)))
    tables = dict(
        evaluations=[dict(evaluation_id='e0', phase='baseline', provenance='real', result_source='simulation', completed_at='2026-09-21T10:00:00'),
                     dict(evaluation_id='e1', phase='search', provenance='real', result_source='simulation', completed_at='2026-09-21T10:02:00')],
        metrics=[dict(evaluation_id='e0', measurement_id=None, metric_name=k, raw_value=v, unit=recipes.RING_METRICS[k], valid=True,
                      aggregation_level='condition') for k, v in values.items()]
        + [dict(evaluation_id='e0', measurement_id='f_osc', metric_name='f_osc', raw_value=1.2092e9, unit='Hz', valid=True,      # a defined measurement: not raw
                aggregation_level='aggregate'),
           dict(evaluation_id='e0', measurement_id=None, metric_name='energy_per_cycle', raw_value=1.62e-13, unit='J', valid=True,    # a spec's formula: not raw either
                aggregation_level='aggregate'),
           dict(evaluation_id='e1', measurement_id=None, metric_name='osc_frequency_hz', raw_value=9e8, unit='Hz', valid=True,
                aggregation_level='condition')])

    class FakeReader:
        """A reader that verifies the baseline data path and serves projected fixture rows."""
        def __init__(self, data_dir):
            assert Path(data_dir) == run_dir / 'data'

        def rows(self, table, columns=None):
            return [{c: row[c] for c in columns} for row in tables[table]]
    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', FakeReader)
    assert profiles.latest_baseline_run('ring_osc_3stage', [str(tmp_path / 'other'), str(run_dir)]) == str(run_dir)
    reference = profiles.record_reference('ring_osc_3stage', run_dir)
    assert reference['origin'] == 'real' and reference['metrics'] == values and reference['evaluation_id'] == 'e0'
    assert profiles.reference_metrics('ring_osc_3stage') == values
    listed = {t['task_key']: t for t in tasks.list_tasks()}['real:ring_osc_3stage']
    assert listed['verified'] is True
    with pytest.raises(profiles.ProfileError, match='never replaced'):
        profiles.record_reference('ring_osc_3stage', run_dir)
    # refused: another task's run, a mock run, an invalid or incomplete baseline
    (profiles.profile_dir('ring_osc_3stage') / 'reference_measurements.json').unlink()
    tables['metrics'][0]['valid'] = False
    with pytest.raises(profiles.ProfileError, match='not a complete, valid measurement'):
        profiles.record_reference('ring_osc_3stage', run_dir)
    tables['metrics'][0]['valid'] = True
    tables['evaluations'][0]['provenance'] = 'mock'
    with pytest.raises(profiles.ProfileError, match='no real baseline'):
        profiles.record_reference('ring_osc_3stage', run_dir)
    (run_dir / 'effective_config.json').write_text(json.dumps(dict(circuit=dict(source='registered_task', task_id='real:gpdk045_vco'))))
    with pytest.raises(profiles.ProfileError, match='did not simulate'):
        profiles.record_reference('ring_osc_3stage', run_dir)


def test_a_generated_profile_brings_the_result_registry_its_targets_need(tmp_path):
    """Found before the first baseline: the default RL specification registry knows op-amp results only, so a target on
    `osc_frequency_hz` was a blocker - and the UI has no editor for the registry."""
    from gator_workbench.compile import compile_task
    from gator_workbench.validation import registry_for, validate
    read_cell(tmp_path)
    connection_file()
    target = dict(metric_id='osc_frequency_hz', equation='f_osc', unit='GHz', constraint='>=', lower=1.0, hard=True, normalization_scale=1.0)
    power = dict(metric_id='supply_power_w', equation='p_supply', unit='uW', constraint='<=', upper=400.0, hard=False,
                 direction_after_feasible='minimize', normalization_scale=100.0)
    rows = dict(parameters=ROWS, run=dict(max_evaluations=5), targets=[target, power],
                measurements=[measurement('f_osc', 'osc_frequency_hz'), dict(measurement('p_supply', 'supply_power_w'), unit='W')])
    draft = schema.WorkbenchConfig.model_validate(dict(rows, circuit=CIRCUIT))
    assert registry_for(draft) is None                                               # a cell without a profile: nothing to check yet
    draft_graph = tasks.load_task(draft.circuit).base_graph
    assert 'metric_not_in_registry' not in [i.code for i in validate(draft, graph=draft_graph).issues]
    made = profiles.create_profile('ring_osc_3stage', draft, recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    assert [e['metric_id'] for e in made['spec_registry']] == list(recipes.RING_METRICS)
    assert made['spec_registry'][0] == dict(metric_id='osc_frequency_hz', unit='Hz', reference=1.2e9)
    registered = schema.WorkbenchConfig.model_validate(dict(rows, parameters=made['parameters'],
                                                            circuit=dict(source='registered_task', task_id='real:ring_osc_3stage')))
    assert registry_for(registered) == dict(recipes.RING_METRICS)
    runtime = tasks.load_task(registered.circuit, profile_id='lab')
    report = validate(registered, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    assert not report.blocks_run, [(i.level, i.code, i.message) for i in report.issues if i.level in ('error', 'blocker')]
    compiled = compile_task(registered, runtime.base_graph)
    assert compiled.spec_schema.version == 'spec-input-generated-profile-v1'
    assert [m[0] for m in compiled.spec_schema.metrics] == list(recipes.RING_METRICS) and compiled.spec_schema.metrics[0][2] == 1.2e9
    assert sorted(spec.metric_id for spec in compiled.specs) == ['osc_frequency_hz', 'supply_power_w']
    # a registry stated in the configuration still wins, and other tasks keep the default one
    explicit = registered.model_copy(deep=True)
    explicit.run.advanced.spec_registry = [schema.SpecRegistryEntry(metric_id='osc_frequency_hz', unit='Hz', reference=5e8)]
    assert registry_for(explicit) == dict(osc_frequency_hz='Hz')
    other = schema.WorkbenchConfig.model_validate(dict(circuit=dict(source='registered_task', task_id='synthetic:gpdk045_ota5'), run=dict(max_evaluations=5)))
    assert 'gain_db_at_start' in registry_for(other) and 'osc_frequency_hz' not in registry_for(other)
    # a spec under a name the registry lacks is added to it (spec_equations); a configured registry takes it as given
    unknown = dict(target, metric_id='osc_phase_noise', equation='f_osc')
    bad = registered.model_copy(update=dict(targets=[schema.PerformanceTarget(**unknown)]))
    found = validate(bad, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
    assert 'spec_adds_registry_entry' in [i.code for i in found.issues if i.level == 'info'] and not found.blocks_run
    explicit_bad = explicit.model_copy(update=dict(targets=[schema.PerformanceTarget(**unknown)]))
    assert 'metric_not_in_registry' in [i.code for i in validate(explicit_bad, graph=runtime.base_graph,
                                                                 provided_metrics=set(runtime.provided_metrics)).issues if i.level == 'blocker']
