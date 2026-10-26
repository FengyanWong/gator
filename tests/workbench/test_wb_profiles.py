"""Create profile: a cell read out of Virtuoso + the rows of the editors -> a registered `real:<name>` task.

Recorded REAL export / readbacks of the user's 3-stage ring oscillator (fixtures/ring_osc), a fake reader process,
no Virtuoso, no simulation. The real-run machinery itself is exercised as far as it goes offline: the profile object,
the deck, the environment factory."""
import json
from pathlib import Path
import pickle

import pytest
from fastapi.testclient import TestClient

from gator_workbench import baseline_reference, native_cells, profiles, recipes, run_index, schema, tasks
from helpers import fabricate_run, probe, workbench_app
from ring_cell_support import CIRCUIT, ROWS, config, connection_file, read_cell, row
from helpers import bridge_installed  # noqa: F401 - a fixture its marked tests use


@pytest.mark.usefixtures('bridge_installed')
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
    # the verified factory, with the workbench's preparation - whose adapter holds the cell's lock (record 7.311)
    assert [c.__name__ for c in type(factory).__mro__[:2]] == ['CdfNativeEnvironmentFactory', 'NativeEnvironmentFactory']
    assert factory.reference_metrics is None                                                              # no baseline yet
    assert factory.config.library == 'GPDK045_RINGOSC' and factory.config.creation_receipt == (directory / 'creation.json').resolve()
    widened = [dict(r, upper=4.0) if r['variable_id'] == 'wp' else r for r in made['parameters']]
    with pytest.raises(tasks.TaskBlocked, match='differ from what was saved'):
        runnable.env_factory_builder(compile_task(config(rows=widened).model_copy(update=dict(circuit=reference)), runnable.base_graph), tmp_path, registered.run)
    # a recorded real baseline becomes the reference every worker's first evaluation is compared with
    (directory / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.2e9))))
    again = tasks.load_task(reference, allow_real=True, profile_id='lab')
    assert again.env_factory_builder(compiled, tmp_path, registered.run).reference_metrics == dict(osc_frequency_hz=1.2e9)


@pytest.mark.usefixtures('bridge_installed')
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


@pytest.mark.usefixtures('bridge_installed')
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


@pytest.mark.usefixtures('bridge_installed')
def test_a_created_profile_makes_the_cell_a_registered_task_over_the_api(tmp_path):
    read_cell(tmp_path)
    connection_file()
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
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


def test_a_cell_read_from_virtuoso_is_validated_the_same_way_everywhere(tmp_path, monkeypatch):
    # Before: the page left the metrics of a cell without a task unchecked, while the start checklist checked them against
    # an EMPTY list - every probe was "metric_not_provided" there and nowhere else.
    monkeypatch.setattr(tasks, 'bridge_importable', lambda: True)
    read_cell(tmp_path)
    connection_file()
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
    loaded = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert loaded['native_draft'] and loaded['testbench_probes']['rows']
    raw = config().model_dump(mode='json')
    raw['measurements'] = loaded['testbench_probes']['rows']
    page = client.post('/api/config/validate', json=dict(config=raw)).json()
    checklist = client.post('/api/agent/readiness', json=dict(config=raw)).json()
    assert 'metric_not_provided' not in [i['code'] for i in page['issues']]
    assert 'metric_not_provided' not in json.dumps(checklist) and 'it provides []' not in json.dumps(checklist)
    assert 'circuit_profile_missing' in [i['code'] for i in page['issues']]            # and it still cannot be started


def write_profile(folder_name, **fields):
    """Write a minimal saved profile record with optional field overrides."""
    folder = profiles.store_root() / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    entry = dict(format=profiles.FORMAT, name=folder_name, circuit_class='oscillator', library='LIB', core_cell=f'{folder_name}_cell')
    (folder / profiles.FILES['entry']).write_text(json.dumps({**entry, **fields}))
    return folder


# ---- one task's profile --------------------------------------------------------------------------------------------
def test_one_profile_is_read_as_the_whole_list_reads_it():
    write_profile('ring_a')
    write_profile('ring_b', revision=3)
    write_profile('other_format', format='gator-generated-profile-0')
    write_profile('not_its_name', name='someone_else')
    (profiles.store_root() / 'bad_json').mkdir()
    (profiles.store_root() / 'bad_json' / profiles.FILES['entry']).write_text('{not json')
    (profiles.store_root() / 'no_entry').mkdir()
    listed = profiles.list_profiles()
    assert set(listed) == {'ring_a', 'ring_b'}
    for name in ('ring_a', 'ring_b', 'other_format', 'not_its_name', 'bad_json', 'no_entry', 'missing', 'Ring_a', '', '../x', None, 7):
        assert profiles.profile_entry(name) == listed.get(name), name


# ---- the task list ----------------------------------------------------------------------------------------------------
def test_the_task_list_asks_once_what_blocks_generated_tasks_and_reads_each_reference_once(monkeypatch):
    for name in ('ring_a', 'ring_b', 'ring_c'):
        write_profile(name)
    write_profile('maestro_x', recipe=profiles.MAESTRO, runnable=False)
    blockers, references = [], []
    monkeypatch.setattr(tasks, 'generated_backend_blocker', lambda profile_id=None: blockers.append(profile_id) or 'no link')
    monkeypatch.setattr(profiles, 'reference_metrics', lambda name: references.append(name) or (dict(x=1) if name == 'ring_b' else None))
    listed = {t['task_key']: t for t in tasks.list_tasks() if t.get('generated')}
    assert blockers == [None] and sorted(references) == ['maestro_x', 'ring_a', 'ring_b', 'ring_c']
    assert [listed[f'real:{n}']['blocker'] for n in ('ring_a', 'ring_b', 'ring_c')] == ['no link'] * 3
    assert listed['real:maestro_x']['blocker'] == profiles.MAESTRO_NOT_RUNNABLE
    assert listed['real:ring_b']['verified'] and not listed['real:ring_a']['verified']
    assert listed['real:ring_a']['description'].endswith('No real baseline recorded yet.')
    assert listed['real:ring_b']['description'].endswith('(Virtuoso + Spectre). ')


def test_a_task_load_finds_its_newest_baseline_through_the_run_cache(tmp_path, monkeypatch):
    fabricate_run(tmp_path, 'old', created='2026-10-01T10:00:00+00:00', kind=profiles.BASELINE_KIND)
    newest = fabricate_run(tmp_path, 'new', created='2026-10-05T10:00:00+00:00', kind=profiles.BASELINE_KIND)
    fabricate_run(tmp_path, 'failed', created='2026-10-06T10:00:00+00:00', kind=profiles.BASELINE_KIND, state='failed')
    fabricate_run(tmp_path, 'other', created='2026-10-07T10:00:00+00:00', kind=profiles.BASELINE_KIND, task='real:ring_b')
    fabricate_run(tmp_path, 'train', created='2026-10-07T11:00:00+00:00')
    given = []

    def adopt(run_dir, manifest=None):
        """Record baseline adoption and mutate its supplied manifest to test cache isolation."""
        given.append((Path(run_dir), manifest))
        manifest['state'] = 'changed by the callee'                         # a copy: the run list's cache keeps its own
        return dict(recorded=True, name='ring_a')
    monkeypatch.setattr(baseline_reference, 'adopt_baseline_run', adopt)
    assert profiles.adopt_latest_baseline('ring_a', tmp_path) == dict(recorded=True, name='ring_a')
    assert [run for run, _ in given] == [newest]
    assert run_index.run_facts(newest)['manifest']['state'] == 'completed'
    assert profiles.adopt_latest_baseline('ring_none', tmp_path) is None
