"""Create profile: a cell read out of Virtuoso + the rows of the editors -> a registered `real:<name>` task.

Recorded REAL export / readbacks of the user's 3-stage ring oscillator (fixtures/ring_osc), a fake reader process,
no Virtuoso, no simulation. The real-run machinery itself is exercised as far as it goes offline: the profile object,
the deck, the environment factory."""
import json
from pathlib import Path
import pickle
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, native_cells, profiles, recipes, schema, tasks
from gator_workbench.api import create_app
from gator_workbench.paths import bridge_state_dir, local_settings_dir
from gator_workbench.storage.atomic import sha256_file
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from test_wb_api import probe

FIXTURE = Path(__file__).parent / 'fixtures' / 'ring_osc'
CIRCUIT = dict(source='virtuoso', library='GPDK045_RINGOSC', cell='ring_osc_3stage', testbench_cell='tb_ring_osc_3stage', circuit_class='vco')


def fake_reader(tmp_path, *, testbench=True):
    script = tmp_path / 'ring_reader.py'
    script.write_text(f'''
import json, shutil, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
for name in ('netlist.scs', 'core_readback.json') + (('testbench_readback.json',) if {testbench!r} else ()):
    shutil.copy(Path({str(FIXTURE)!r}) / name, out / name)
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def read_cell(tmp_path, testbench='tb_ring_osc_3stage'):
    return bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GPDK045_RINGOSC', cell='ring_osc_3stage',
                            testbench=testbench, command=fake_reader(tmp_path, testbench=bool(testbench)))


def row(variable_id, instance, lower=None, upper=None, leader=None, **more):
    return dict(dict(variable_id=variable_id, instance_path=instance, parameter_name='w', unit='um', optimized=True, lower=lower,
                     upper=upper, binding_group=leader, ratio=1.0), **more)


ROWS = [row('wn', 'XU1/MN1', 0.6, 1.6), row('wn2', 'XU1/MN2', leader='wn'), row('wn3', 'XU1/MN3', leader='wn'),
        row('wp', 'XU1/MP1', 1.2003, 3.2), row('wp2', 'XU1/MP2', leader='wp'), row('wp3', 'XU1/MP3', leader='wp')]


def config(rows=ROWS, **circuit):
    return schema.WorkbenchConfig.model_validate(dict(circuit=dict(CIRCUIT, **circuit), parameters=rows, run=dict(max_evaluations=5)))


def connection_file():
    target = local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env', library='GATOR_TESTS', model_file='/pdk/model.scs')))))


def test_the_ring_oscillator_becomes_a_registered_real_task(tmp_path):
    meta = read_cell(tmp_path)
    assert meta['unverified_models'] == [] and meta['device_count'] == 10          # the MIM capacitor is a verified model now
    made = profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    assert made['task_key'] == 'real:ring_osc_3stage' and made['circuit_class'] == 'vco' and made['core_instance'] == 'XU1'
    leaders = {r['variable_id']: (r['lower'], r['upper'], r['step']) for r in made['parameters'] if not r['binding_group']}
    assert leaders == dict(wn=(0.6, 1.6, 0.005), wp=(1.205, 3.2, 0.005))            # snapped INWARD onto the 5 nm grid, step filled in
    directory = Path(made['directory'])
    design = json.loads((directory / 'design.json').read_text())
    assert (design['supply_source'], design['supply_net'], design['supply_v']) == ('V0', 'VDD', '1')
    assert design['stage_nets'] == ['OUT', 'XU1.N1', 'XU1.N2'] and design['initial_conditions'] == {'OUT': '0', 'XU1.N1': '1', 'XU1.N2': '0'}
    receipt = json.loads((directory / 'creation.json').read_text())
    assert receipt['config'] == design and (receipt['library'], receipt['core_cell']) == ('GPDK045_RINGOSC', 'ring_osc_3stage')

    profile = profiles.load_profile('ring_osc_3stage')                               # every check of the verified classes ran
    assert isinstance(profile, recipes.GenericRingOscillatorProfile) and len(profile.writable_keys) == 6
    assert set(profile.mos_names) == {'MN1', 'MN2', 'MN3', 'MP1', 'MP2', 'MP3'} and set(profile.fixed_instances) == {'C1', 'C2', 'C3'}
    recorded = profile.assignments()
    assert recorded['XU1/MN1', 'w'] == pytest.approx(1e-6) and recorded['XU1/MP3', 'w'] == pytest.approx(2e-6)
    moved = profile.assignments(dict(wn=1.2e-6))
    assert {moved[f'XU1/MN{i}', 'w'] for i in (1, 2, 3)} == {1.2e-6}                 # the three NMOS move together
    with pytest.raises(ValueError):
        profile.validate_assignment(dict(moved, **{}) | {('XU1/MN2', 'w'): 1.205e-6})    # one stage alone: refused
    deck = profile.build_deck('// structure only', '/pdk/model.scs')
    assert 'ic OUT=0 XU1.N1=1 XU1.N2=0\n' in deck and 'save VDD OUT XU1.N1 XU1.N2 V0:p\n' in deck
    assert 'tranNom tran stop=5e-08 maxstep=8.33333e-12 errpreset=conservative ic=all skipdc=no\n' in deck
    assert profile.analysis_settings['start_s'] == pytest.approx(20 / 1.2e9, rel=1e-5)
    assert pickle.loads(pickle.dumps(profile)).assignments() == recorded              # workers receive it pickled

    # ---- registered: listed, loadable, never executable without the explicit authorization ---------------------------
    connection_file()
    listed = {t['task_key']: t for t in tasks.list_tasks()}['real:ring_osc_3stage']
    assert listed['generated'] and listed['available'] and listed['verified'] is False and listed['circuit_class'] == 'vco'
    reference = schema.CircuitReference(source='registered_task', task_id='real:ring_osc_3stage')
    shown = tasks.load_task(reference, profile_id='lab')
    assert not shown.mock and not shown.authorized and shown.provided_metrics[0] == 'osc_frequency_hz'
    assert shown.circuit['generated_profile'] and shown.circuit['baseline_recorded'] is False
    with pytest.raises(tasks.TaskBlocked, match='explicit user action'):
        shown.env_factory_builder(None, tmp_path, None)
    # ---- authorized: the environment factory of the REAL backend is assembled (nothing is contacted by building it) ----
    from gator_workbench.compile import compile_task
    registered = config(rows=made['parameters']).model_copy(update=dict(circuit=reference))
    runnable = tasks.load_task(reference, allow_real=True, profile_id='lab')
    compiled = compile_task(registered, runnable.base_graph)
    factory = runnable.env_factory_builder(compiled, tmp_path, registered.run)
    assert type(factory).__name__ == 'NativeEnvironmentFactory' and factory.reference_metrics is None     # no baseline yet
    assert factory.config.library == 'GPDK045_RINGOSC' and factory.config.creation_receipt == (directory / 'creation.json').resolve()
    widened = [dict(r, upper=4.0) if r['variable_id'] == 'wp' else r for r in made['parameters']]
    with pytest.raises(tasks.TaskBlocked, match='differ from what was saved'):
        runnable.env_factory_builder(compile_task(config(rows=widened).model_copy(update=dict(circuit=reference)), runnable.base_graph), tmp_path, registered.run)
    # a recorded real baseline becomes the reference every worker's first evaluation is compared with
    (directory / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.2e9))))
    again = tasks.load_task(reference, allow_real=True, profile_id='lab')
    assert again.env_factory_builder(compiled, tmp_path, registered.run).reference_metrics == dict(osc_frequency_hz=1.2e9)


@pytest.mark.parametrize('rows, recipe, frequency, reason', [
    ([row('c1', 'XU1/C1', 1, 5, parameter_name='w')], 'ring_oscillator', 1e9, 'only change transistor widths'),
    ([row('ln', 'XU1/MN1', 0.045, 0.1, parameter_name='l')], 'ring_oscillator', 1e9, 'only change transistor widths'),
    ([row('wn', 'XU1/MN1', 0.6, 1.6, scale='log')], 'ring_oscillator', 1e9, 'linear'),
    ([row('wn', 'XU1/MN1', 1.2, 1.6)], 'ring_oscillator', 1e9, 'must contain the present width'),
    ([row('wn', 'XU1/MN1')], 'ring_oscillator', 1e9, 'lower and an upper bound'),
    ([row('wn', 'XU1/MN1', 0.6, 1.6, optimized=False)], 'ring_oscillator', 1e9, 'Nothing is marked as optimized'),
    ([row('wn', 'XU1/MN1', 0.6, 1.6, step=0.003)], 'ring_oscillator', 1e9, '5 nm width grid'),
    (ROWS, 'ring_oscillator', None, 'expected oscillation frequency'),
    (ROWS, 'ring_oscillator', 1e15, 'between 1 kHz and 100 GHz'),
    (ROWS, 'opamp_ac', None, 'op-amp recipe expects'),
    (ROWS, 'bandgap', None, 'Unknown circuit type'),
])
def test_what_the_real_backend_cannot_do_is_refused_in_plain_words(tmp_path, rows, recipe, frequency, reason):
    read_cell(tmp_path)
    with pytest.raises(profiles.ProfileError, match=reason):
        profiles.create_profile('ring_try', config(rows=rows), recipe=recipe, expected_frequency_hz=frequency)
    assert profiles.list_profiles() == {} and not list(profiles.store_root().glob('*')) or not any(profiles.store_root().iterdir())


def test_preconditions_names_and_duplicates(tmp_path):
    with pytest.raises(profiles.ProfileError, match='Read the cell into the workbench first'):
        profiles.create_profile('ring_a', config(), recipe='ring_oscillator', expected_frequency_hz=1e9)
    read_cell(tmp_path, testbench=None)
    with pytest.raises(profiles.ProfileError, match='Choose the testbench cell'):
        profiles.create_profile('ring_a', config(), recipe='ring_oscillator', expected_frequency_hz=1e9)
    read_cell(tmp_path)
    for bad in ('Ring', 'r', '../x', 'has space', 'gpdk045_ota5'):
        with pytest.raises(profiles.ProfileError):
            profiles.create_profile(bad, config(), recipe='ring_oscillator', expected_frequency_hz=1e9)
    profiles.create_profile('ring_a', config(), recipe='ring_oscillator', expected_frequency_hz=1e9)
    for name in ('ring_a', 'ring_b'):                     # the same name, and a second profile for the same cell
        with pytest.raises(profiles.ProfileError, match='already'):
            profiles.create_profile(name, config(), recipe='ring_oscillator', expected_frequency_hz=1e9)
    # an older copy of the cell (read without the `view` of each instance) is named as such, not a KeyError
    readback = native_cells.cell_dir('GPDK045_RINGOSC', 'ring_osc_3stage') / 'core_readback.json'
    data = json.loads(readback.read_text())
    for item in data['instances']:
        item.pop('view')
    readback.write_text(json.dumps(data))
    import shutil
    shutil.rmtree(profiles.profile_dir('ring_a'))
    with pytest.raises(profiles.ProfileError, match='Read the cell again'):
        profiles.create_profile('ring_c', config(), recipe='ring_oscillator', expected_frequency_hz=1e9)


def test_a_created_profile_makes_the_cell_a_registered_task_over_the_api(tmp_path):
    read_cell(tmp_path)
    connection_file()
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False, monitor=probe(tmp_path)))
    before = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert before['native_draft'] and before['profile_task'] is None and 'profile_recipes' not in before
    # The Create profile form went in 7.57 and its route on 2026-09-22 (the page saves tasks); create_profile stays the
    # generator's plain path and is called directly.
    with pytest.raises(profiles.ProfileError, match='expected oscillation frequency'):
        profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=None)
    made = profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    assert made['task_key'] == 'real:ring_osc_3stage' and len(made['parameters']) == 6
    assert client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()['profile_task'] == 'real:ring_osc_3stage'
    assert 'real:ring_osc_3stage' in [t['task_key'] for t in client.get('/api/tasks').json()['tasks']]
    registered = dict(source='registered_task', task_id='real:ring_osc_3stage')
    loaded = client.post('/api/circuit/load', json=dict(circuit=registered)).json()
    assert loaded['loaded'] and loaded['generated_profile'] and loaded['baseline_recorded'] is False and loaded['mock'] is False
    assert any('Baseline simulation' in note for note in loaded['notes'])
    full = config(rows=made['parameters']).model_dump(mode='json')
    full['circuit'] = registered
    report = client.post('/api/config/validate', json=dict(config=full)).json()
    assert 'circuit_profile_missing' not in [i['code'] for i in report['issues']]
    # without the explicit authorization nothing starts and nothing is created
    started = client.post('/api/runs/start', json=dict(config=full))
    assert started.status_code >= 400 and not list(tmp_path.glob('**/run_manifest.json'))


# ------------------------------------------------------------------------------------------------ towards the first real baseline
def measurement(measurement_id, source_name):
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
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                                   monitor=probe(tmp_path, tunnel='failed', daemon='not_checked', session_readiness='not_checked')))
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


# ------------------------------------------------------------------------------------------------ one task per cell, and starting over
def test_a_cell_of_a_built_in_circuit_is_said_to_have_its_registered_task(tmp_path):
    """The four verified circuits are tasks too: their cell gets no second profile, and the form can say which task it has."""
    assert profiles.task_for_cell('GATOR_TESTS', 'vco_m6_v1') is None             # no connection states that library yet
    connection_file()
    assert profiles.task_for_cell('GATOR_TESTS', 'vco_m6_v1') == dict(task_key='real:gpdk045_vco', name='gpdk045_vco', generated=False)
    assert profiles.task_for_cell('GATOR_TESTS', 'ota5_v1')['task_key'] == 'real:gpdk045_ota5'
    assert profiles.task_for_cell('MY_COPIES', 'vco_m6_v1') is None               # the same name in another library is another cell
    assert profiles.task_for_cell('GATOR_TESTS', 'ring_osc_3stage') is None and profiles.task_for_cell('GATOR_TESTS', None) is None
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False, monitor=probe(tmp_path)))
    shown = client.post('/api/circuit/load', json=dict(circuit=dict(source='virtuoso', library='GATOR_TESTS', cell='vco_m6_v1'))).json()
    assert shown['loaded'] is False and shown['profile_task'] == 'real:gpdk045_vco' and shown['profile_task_generated'] is False
    # ... and Create profile refuses it, whatever was read: the ring oscillator stands in for such a cell here
    read_cell(tmp_path)
    target = local_settings_dir() / 'bridge_connection.json'
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env', library='GPDK045_RINGOSC', model_file='/pdk/model.scs')))))
    import gator_workbench.tasks as registered
    design = tmp_path / 'builtin_design.json'
    design.write_text(json.dumps(dict(core_cell='ring_osc_3stage', testbench_cell='tb_ring_osc_3stage')))
    original = dict(registered.REAL_PROFILES['gpdk045_vco'])
    registered.REAL_PROFILES['gpdk045_vco'] = dict(original, design=str(design))
    try:
        with pytest.raises(profiles.ProfileError, match='already has the registered task real:gpdk045_vco .a verified built-in circuit.'):
            profiles.create_profile('ring_again', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    finally:
        registered.REAL_PROFILES['gpdk045_vco'] = original
    assert not profiles.profile_dir('ring_again').exists()


def working_run(tmp_path, task_key, state='running'):
    run_dir = tmp_path / f'run_{len(list(tmp_path.glob("run_*")))}'
    run_dir.mkdir()
    (run_dir / 'run_manifest.json').write_text(json.dumps(dict(run_id='run-1', circuit=dict(task_key=task_key))))
    return dict(run_dir=str(run_dir), run_id='run-1', state=state, mock=False)


def test_a_generated_profile_is_deleted_by_moving_it_aside(tmp_path):
    read_cell(tmp_path)
    made = profiles.create_profile('ring_a', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    (Path(made['directory']) / profiles.FILES['reference']).write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.2e9))))
    with pytest.raises(profiles.ProfileError, match='run-1 of real:ring_a is working right now'):
        profiles.delete_profile('ring_a', run_rows=[working_run(tmp_path, 'real:ring_a')])
    assert 'ring_a' in profiles.list_profiles()
    # a run of another task, a run at rest and a MOCK run do not hold it
    rows = [working_run(tmp_path, 'real:other'), working_run(tmp_path, 'real:ring_a', state='paused'), dict(working_run(tmp_path, 'real:ring_a'), mock=True)]
    gone = profiles.delete_profile('ring_a', run_rows=rows[:1])
    assert gone['deleted'] == 'real:ring_a' and gone['baseline_recorded'] is True
    assert (gone['library'], gone['cell'], gone['testbench_cell']) == ('GPDK045_RINGOSC', 'ring_osc_3stage', 'tb_ring_osc_3stage')
    kept = Path(gone['kept_copy'])
    assert kept.parent == profiles.store_root() / '.deleted' and kept.name.startswith('ring_a.')
    assert {f.name for f in kept.iterdir()} >= {'profile.json', 'design.json', 'rules.json', 'reference_measurements.json'}   # nothing is erased
    assert profiles.list_profiles() == {} and profiles.task_for_cell('GPDK045_RINGOSC', 'ring_osc_3stage') is None
    assert 'real:ring_a' not in [t['task_key'] for t in tasks.list_tasks()]
    assert native_cells.load_import('GPDK045_RINGOSC', 'ring_osc_3stage') is not None        # the copy of the cell stays
    with pytest.raises(tasks.TaskBlocked):
        tasks.load_task(schema.CircuitReference(source='registered_task', task_id='real:ring_a'), allow_real=True)
    # the name and the cell are free again; a second deletion keeps its own copy
    profiles.create_profile('ring_a', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    again = profiles.delete_profile('ring_a', run_rows=rows[1:])
    assert again['baseline_recorded'] is False and again['kept_copy'] != gone['kept_copy'] and kept.is_dir()
    for name, reason in (('ring_a', 'Unknown generated profile'), ('gpdk045_vco', 'verified built-in circuit')):
        with pytest.raises(profiles.ProfileError, match=reason):
            profiles.delete_profile(name)
    assert (Path(__file__).parents[2] / 'configs' / 'gpdk045_vco_design.json').is_file()


def test_the_api_deletes_a_generated_profile_and_the_cell_offers_a_new_one(tmp_path):
    read_cell(tmp_path)
    connection_file()
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False, monitor=probe(tmp_path)))
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    shown = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert shown['profile_task'] == 'real:ring_osc_3stage' and shown['profile_task_generated'] is True
    gone = client.post('/api/virtuoso/profile/delete', json=dict(name='ring_osc_3stage'))
    assert gone.status_code == 200 and gone.json()['deleted'] == 'real:ring_osc_3stage' and gone.json()['cell'] == 'ring_osc_3stage'
    assert 'real:ring_osc_3stage' not in [t['task_key'] for t in client.get('/api/tasks').json()['tasks']]
    after = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert after['native_draft'] and after['profile_task'] is None
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)   # starting over works
    for name, status in (('nothing_here', 409), ('gpdk045_ota5', 409), ('Bad Name', 422), ('../x', 422)):
        refused = client.post('/api/virtuoso/profile/delete', json=dict(name=name))
        assert refused.status_code == status
    assert 'built-in' in client.post('/api/virtuoso/profile/delete', json=dict(name='gpdk045_ota5')).json()['detail']['message']


# ------------------------------------------------------------------------------------------------ a finished baseline records itself (7.78)
RING_VALUES = dict(zip(recipes.RING_METRICS, (1.2092e9, 1.96e-4, 1.96e-4, 0.999, 0.508, 1e-6, 1e-6, 3.1e-9)))


def baseline_run(tmp_path, monkeypatch, run_dir, *, run_id='r1', run_kind='baseline_preflight', state='completed', mock=False,
                 task_key='real:ring_osc_3stage', created='2026-09-23T22:45:18+00:00', valid=True, circuit=None):
    """A Baseline simulation of the ring task as its run directory holds it: the manifest the worker writes
    (run_kind, circuit.task_key, state) and the tables the reference is read from (a fake reader, counted)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'effective_config.json').write_text(json.dumps(dict(circuit=dict(source='registered_task', task_id=task_key))))
    directory = profiles.profile_dir('ring_osc_3stage')
    facts = dict(task_key=task_key, netlist_sha256=sha256_file(directory / 'structure.scs'),
                 parser_config_sha256=sha256_file(directory / 'mapping.json'), **(circuit or {}))
    manifest = dict(run_id=run_id, mock=mock, run_kind=run_kind, state=state, created_utc=created, circuit=facts,
                    segments=[dict(segment=1, ended_utc='2026-09-23T22:45:32+00:00')], notes=[])
    (run_dir / 'run_manifest.json').write_text(json.dumps(manifest))
    tables = dict(
        evaluations=[dict(evaluation_id='e0', phase='baseline', provenance='real', result_source='simulation', completed_at='2026-09-23T22:45:30')],
        metrics=[dict(evaluation_id='e0', measurement_id=None, metric_name=k, raw_value=v, unit=recipes.RING_METRICS[k], valid=valid,
                      aggregation_level='condition') for k, v in RING_VALUES.items()])
    reads = []

    class FakeReader:
        def __init__(self, data_dir):
            reads.append(Path(data_dir))

        def rows(self, table, columns=None):
            return [{c: row[c] for c in columns} for row in tables[table]]
    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', FakeReader)
    return manifest, reads


def test_a_finished_single_baseline_simulation_records_itself(tmp_path, monkeypatch):
    """Record 7.78: after the user's first real baseline the column still said "no real baseline yet" - recording the
    reference was a press of its own. The worker now asks for it at the end of a baseline_preflight run."""
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    entry_file = profiles.profile_dir('ring_osc_3stage') / profiles.FILES['entry']
    entry_file.write_text(json.dumps(dict(json.loads(entry_file.read_text()), saved_utc='2026-09-23T02:56:41+00:00')))   # as Save task records it
    run_dir = tmp_path / 'run1'
    manifest, reads = baseline_run(tmp_path, monkeypatch, run_dir)
    # not one to record: an optimization run, a MOCK run, a verified built-in circuit - nothing to say
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, run_kind='optimization')) is None
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, mock=True)) is None
    assert profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, circuit=dict(manifest['circuit'], task_key='real:gpdk045_ota7'))) is None
    # a run that did not complete, or one the task has outlived (saved again after it): said, not recorded
    ended = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, state='failed'))
    assert ended['recorded'] is False and 'ended as failed' in ended['note']
    stale = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, circuit=dict(manifest['circuit'], netlist_sha256='0' * 64)))
    assert stale['recorded'] is False and 'saved again after that run' in stale['note']
    older = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, created_utc='2020-01-01T00:00:00+00:00'))
    assert older['recorded'] is False and 'saved again after that run' in older['note']
    assert profiles.reference_metrics('ring_osc_3stage') is None and not reads
    # the run as it is: recorded, from the run's own tables
    done = profiles.adopt_baseline_run(run_dir)                       # the manifest read from the run directory
    assert done['recorded'] is True and done['name'] == 'ring_osc_3stage' and done['note'].startswith('Recorded as the reference of real:ring_osc_3stage')
    assert profiles.reference_metrics('ring_osc_3stage') == RING_VALUES and reads == [run_dir / 'data']
    entry = profiles.list_profiles()['ring_osc_3stage']
    assert entry['status'].startswith('baseline recorded') and entry['baseline_recorded_utc'] and 'baseline_attempt' not in entry
    # never replaced: a second baseline run says so and reads no table
    again = profiles.adopt_baseline_run(run_dir, manifest=dict(manifest, run_id='r2'))
    assert again['recorded'] is False and 'never replaced' in again['note'] and len(reads) == 1


def test_a_refused_baseline_is_remembered_and_said_until_a_good_one_comes(tmp_path, monkeypatch):
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    bad = tmp_path / 'bad'
    manifest, reads = baseline_run(tmp_path, monkeypatch, bad, run_id='bad1', valid=False)
    refused = profiles.adopt_baseline_run(bad)
    assert refused['recorded'] is False and 'not a complete, valid measurement' in refused['note']
    attempt = profiles.list_profiles()['ring_osc_3stage']['baseline_attempt']
    assert attempt['run_id'] == 'bad1' and attempt['run_dir'] == str(bad) and attempt['ended_utc'] == '2026-09-23T22:45:32+00:00'
    assert 'not a complete, valid measurement' in attempt['reason']
    # the same run again (the task loaded once more): the answer is known, no table is read
    assert profiles.adopt_baseline_run(bad)['note'] == refused['note'] and len(reads) == 1
    # the column is told why the task still has no baseline
    loaded = tasks.load_task(schema.CircuitReference.model_validate(dict(source='registered_task', task_id='real:ring_osc_3stage')))
    assert loaded.circuit['baseline_recorded'] is False and loaded.circuit['baseline_attempt']['run_id'] == 'bad1'
    # a good one afterwards: recorded, and the refusal goes with it
    good = tmp_path / 'good'
    baseline_run(tmp_path, monkeypatch, good, run_id='good1')
    assert profiles.adopt_baseline_run(good)['recorded'] is True
    entry = profiles.list_profiles()['ring_osc_3stage']
    assert 'baseline_attempt' not in entry and profiles.reference_metrics('ring_osc_3stage') == RING_VALUES


def test_a_baseline_made_before_is_adopted_when_the_task_is_loaded(tmp_path, monkeypatch):
    """The user's own case (2026-09-24): the baseline run was made before runs recorded themselves. Loading the task
    finds the newest completed Baseline simulation of the task under the remembered output root and records it;
    no output root remembered (no run ever made here) - nothing is scanned."""
    from gator_workbench import runs
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    out = tmp_path / 'out'
    older = out / 'experiment__a' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed1__older'
    newest = out / 'experiment__a' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed2__newest'
    running = out / 'experiment__b' / 'runs' / 'ring_osc_3stage.baseline' / 'scratch__seed3__running'
    other = out / 'experiment__b' / 'runs' / 'other' / 'scratch__seed4__other'
    baseline_run(tmp_path, monkeypatch, older, run_id='older', created='2026-09-22T10:00:00+00:00')
    baseline_run(tmp_path, monkeypatch, running, run_id='running', state='running', created='2026-09-24T10:00:00+00:00')
    baseline_run(tmp_path, monkeypatch, other, run_id='other', task_key='real:gpdk045_ota7', created='2026-09-24T11:00:00+00:00')
    _, reads = baseline_run(tmp_path, monkeypatch, newest, run_id='newest', created='2026-09-23T22:45:18+00:00')
    (out / 'mock' / 'experiment__m' / 'runs' / 'x' / 'y').mkdir(parents=True)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False, monitor=probe(tmp_path)))
    registered = dict(circuit=dict(source='registered_task', task_id='real:ring_osc_3stage'))
    assert client.post('/api/circuit/load', json=registered).json()['baseline_recorded'] is False and not reads      # nothing remembered: no scan
    runs.save_settings(output_root=str(out))
    loaded = client.post('/api/circuit/load', json=registered).json()
    assert loaded['baseline_recorded'] is True and loaded['baseline_attempt'] is None and reads == [newest / 'data']
    assert any('only its recorded baseline has been simulated' in note for note in loaded['notes'])
    assert profiles.list_profiles()['ring_osc_3stage']['baseline_recorded_utc']
    assert client.post('/api/virtuoso/profile/reference', json=dict(name='ring_osc_3stage')).json()['detail']['code'] == 'reference_refused'


def test_a_maestro_measured_task_records_its_own_outputs_as_the_reference(tmp_path, monkeypatch):
    """Found on the user's first real baseline (2026-09-24, a Maestro task with outputs freq / vmax): record_reference
    expected the recipe's results, and a Maestro recipe has none, so every Maestro baseline was refused as "unexpected
    metrics". The task's own provided_metrics are what its baseline holds."""
    read_cell(tmp_path)
    connection_file()
    profiles.create_profile('ring_osc_3stage', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    entry_file = profiles.profile_dir('ring_osc_3stage') / profiles.FILES['entry']
    entry_file.write_text(json.dumps(dict(json.loads(entry_file.read_text()), recipe=profiles.MAESTRO, provided_metrics=['freq', 'vmax'])))
    run_dir = tmp_path / 'maestro_run'
    baseline_run(tmp_path, monkeypatch, run_dir, run_id='m1')
    outputs = dict(freq=1208362157.05, vmax=1.0027)
    tables = dict(evaluations=[dict(evaluation_id='e0', phase='baseline', provenance='real', result_source='simulation', completed_at='2026-09-23T22:45:30')],
                  metrics=[dict(evaluation_id='e0', measurement_id=None, metric_name=k, raw_value=v, unit=None, valid=True, aggregation_level='condition') for k, v in outputs.items()]
                  + [dict(evaluation_id='e0', measurement_id='m_freq', metric_name='freq', raw_value=1208362157.05, unit='Hz', valid=True, aggregation_level='aggregate')])

    class MaestroReader:
        def __init__(self, data_dir):
            pass

        def rows(self, table, columns=None):
            return [{c: row[c] for c in columns} for row in tables[table]]
    monkeypatch.setattr('gator_workbench.storage.dataset.DatasetReader', MaestroReader)
    done = profiles.adopt_baseline_run(run_dir)
    assert done['recorded'] is True, done
    assert profiles.reference_metrics('ring_osc_3stage') == outputs
