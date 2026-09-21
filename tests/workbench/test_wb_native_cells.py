"""Reading a Virtuoso cell INTO the workbench (`native_cells`, bridge_read op `import_cell`): the first half of
"create a circuit profile from a Virtuoso cell". FAKE reader process and recorded netlists only - no Virtuoso."""
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, native_cells, schema, tasks
from gator_workbench.api import create_app
from helpers import make_config
from test_wb_api import probe

REPO = Path(__file__).resolve().parents[2]
EXPORT = (REPO / 'examples/circuits/gpdk045_ota5.scs').read_text()            # a recorded REAL Virtuoso export
UNVERIFIED = EXPORT.rstrip('\n') + '\nC9 (VOUT 0 0) pdk_mystery_dev w=4.49u l=4.49u m=2\n'      # + a device type nobody verified


def fake_reader(tmp_path, netlist=EXPORT, fail=False):
    """Stands in for `python -m gator_workbench.bridge_read`: writes what the real reader writes."""
    script = tmp_path / 'reader.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output'])
out.mkdir(parents=True)
(out / 'netlist.scs').write_text({netlist!r})
(out / 'core_readback.json').write_text(json.dumps(dict(origin='fixture', instances=[])))
if {fail!r}:
    sys.exit('Traceback\\nRuntimeError: export failed on the fixture')
print('progress line the bridge might print')
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'),
                      technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def reference(**fields):
    return schema.CircuitReference(source='virtuoso', library='GATOR_TESTS', cell='ota5_v1', **fields)


def test_the_mapping_of_a_draft_holds_only_models_this_project_verified():
    mapping, unverified = native_cells.build_mapping(EXPORT)
    assert sorted(mapping['models']) == ['capacitor', 'g45n1svt', 'g45p1svt', 'vsource'] and unverified == []
    assert mapping['models']['g45n1svt']['terminals'] == ['D', 'G', 'S', 'B']       # from configs/gpdk045_*.json, not from memory
    assert mapping['net_roles'] == {'0': ['ground']} and mapping['parameter_groups'] == []   # nothing else is guessed
    mapping, unverified = native_cells.build_mapping(UNVERIFIED)
    assert unverified == ['pdk_mystery_dev'] and 'pdk_mystery_dev' not in mapping['models']


def test_an_imported_cell_loads_from_its_local_copy_and_can_never_execute(tmp_path):
    with pytest.raises(tasks.TaskBlocked, match='verified circuit profile'):        # before any import: browse only
        tasks.load_task(reference())
    meta = bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                            testbench='tb_ota5_ac_v1', command=fake_reader(tmp_path, UNVERIFIED))
    assert meta['device_count'] == 11 and meta['unverified_models'] == ['pdk_mystery_dev'] and meta['exported_cell'] == 'tb_ota5_ac_v1'
    assert not list(native_cells.store_root().glob('.incoming-*'))
    runtime = tasks.load_task(reference(pdk_id='unspecified'))                    # no bridge, no gate: the local copy
    assert runtime.task_key == 'virtuoso:GATOR_TESTS/ota5_v1' and not runtime.mock and not runtime.authorized
    assert runtime.circuit['native_draft'] and runtime.circuit['pdk_id'] == 'gpdk045' and runtime.provided_metrics == ()
    kinds = {device.id: device.kind for device in runtime.base_graph.devices}
    assert kinds['XU1/M1'] == 'nmos' and kinds['XU1/M3'] == 'pmos' and kinds['C9'] == 'unknown'
    assert any('pdk_mystery_dev' in note for note in runtime.notes)
    for attempt in (lambda: tasks.load_task(reference(), allow_real=True),          # a run start
                    lambda: runtime.env_factory_builder(None, tmp_path, None)):     # and the builder itself
        with pytest.raises(tasks.TaskBlocked, match='no circuit profile yet'):
            attempt()
    # What is shown must be what Virtuoso exported: a changed local copy is not loaded.
    netlist = native_cells.cell_dir('GATOR_TESTS', 'ota5_v1') / 'netlist.scs'
    netlist.write_text(netlist.read_text().replace('w=(4u)', 'w=(9u)'))
    assert native_cells.load_import('GATOR_TESTS', 'ota5_v1') is None
    with pytest.raises(tasks.TaskBlocked, match='verified circuit profile'):
        tasks.load_task(reference())


def test_a_second_import_replaces_the_first_and_a_failed_one_leaves_nothing(tmp_path):
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1', command=fake_reader(tmp_path))
    first = native_cells.load_import('GATOR_TESTS', 'ota5_v1')
    assert first['device_count'] == 10 and first['testbench_cell'] is None and first['exported_cell'] == 'ota5_v1'
    with pytest.raises(RuntimeError, match='export failed'):
        bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                         command=fake_reader(tmp_path, fail=True))
    assert native_cells.load_import('GATOR_TESTS', 'ota5_v1')['netlist_sha256'] == first['netlist_sha256']     # untouched
    assert not list(native_cells.store_root().glob('.incoming-*'))
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1', command=fake_reader(tmp_path, UNVERIFIED))
    assert native_cells.load_import('GATOR_TESTS', 'ota5_v1')['device_count'] == 11
    assert sorted(p.name for p in native_cells.cell_dir('GATOR_TESTS', 'ota5_v1').parent.iterdir()) == ['ota5_v1']
    for bad in (dict(library='a"b', cell='c'), dict(library='L', cell='../x'), dict(library='L', cell='c', testbench='t;rm')):
        with pytest.raises(ValueError):
            bridge_read.read(probe(tmp_path), 'lab', 'import_cell', command=fake_reader(tmp_path), **bad)


def test_the_api_shows_a_draft_and_keeps_it_from_starting(tmp_path):
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                     testbench='tb_ota5_ac_v1', command=fake_reader(tmp_path))
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                                   monitor=probe(tmp_path)))
    circuit = dict(source='virtuoso', library='GATOR_TESTS', cell='ota5_v1', testbench_cell='tb_ota5_ac_v1')
    loaded = client.post('/api/circuit/load', json=dict(circuit=circuit)).json()
    assert loaded['loaded'] and loaded['native_draft'] and loaded['mock'] is False and loaded['summary']['device_count'] == 10
    config = make_config(tmp_path).model_dump(mode='json')
    config['circuit'] = circuit
    report = client.post('/api/config/validate', json=dict(config=config)).json()
    assert report['blocks_run'] and 'circuit_profile_missing' in [issue['code'] for issue in report['issues']]
    assert not [issue for issue in report['issues'] if issue['code'] == 'circuit_not_loaded']     # the circuit IS checked
    for authorize in (False, True):                       # refused before any budget question, and with one
        started = client.post('/api/runs/start', json=dict(config=config, authorize_real_simulation=authorize))
        assert started.status_code >= 400 and 'no circuit profile yet' in json.dumps(started.json())
    assert not list(tmp_path.glob('**/run_manifest.json'))
    down = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, auto_check_on_start=False,
                                 monitor=probe(tmp_path, daemon='failed')))
    blocked = down.post('/api/virtuoso/import', json=dict(profile_id='lab', library='GATOR_TESTS', cell='ota5_v1'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['daemon']
    assert down.post('/api/virtuoso/import', json=dict(profile_id='lab', library='x y', cell='c')).status_code in (409, 422)
