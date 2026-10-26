"""One task per cell, and starting over: a built-in circuit's cell names its task, a generated profile is deleted by moving it aside, the API deletes one and the cell then offers a new one (refactoring package D4: from test_wb_profiles)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import native_cells, profiles, schema, tasks
from gator_workbench.paths import local_settings_dir

from helpers import probe, workbench_app
from ring_cell_support import CIRCUIT, config, connection_file, read_cell
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module


# ------------------------------------------------------------------------------------------------ one task per cell, and starting over
def test_a_cell_of_a_built_in_circuit_is_said_to_have_its_registered_task(tmp_path):
    """The four verified circuits are tasks too: their cell gets no second profile, and the form can say which task it has."""
    assert profiles.task_for_cell('GATOR_TESTS', 'vco_m6_v1') is None             # no connection states that library yet
    connection_file()
    assert profiles.task_for_cell('GATOR_TESTS', 'vco_m6_v1') == dict(task_key='real:gpdk045_vco', name='gpdk045_vco', generated=False)
    assert profiles.task_for_cell('GATOR_TESTS', 'ota5_v1')['task_key'] == 'real:gpdk045_ota5'
    assert profiles.task_for_cell('MY_COPIES', 'vco_m6_v1') is None               # the same name in another library is another cell
    assert profiles.task_for_cell('GATOR_TESTS', 'ring_osc_3stage') is None and profiles.task_for_cell('GATOR_TESTS', None) is None
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
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
    """Create a run manifest and list entry tied to the supplied task key."""
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
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
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
