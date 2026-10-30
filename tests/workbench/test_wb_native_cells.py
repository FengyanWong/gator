"""Reading a Virtuoso cell INTO the workbench (`native_cells`, bridge_read op `import_cell`): the first half of
"create a circuit profile from a Virtuoso cell". FAKE reader process and recorded netlists only - no Virtuoso."""
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, native_cells, schema, tasks
from helpers import make_config, probe, workbench_app

from fakes_virtuoso import EXPORT, fake_reader, REPO   # the same folder as here
UNVERIFIED = EXPORT.rstrip('\n') + '\nC9 (VOUT 0 0) pdk_mystery_dev w=4.49u l=4.49u m=2\n'      # + a device type nobody verified


def reference(**fields):
    """Create a Virtuoso circuit reference to the recorded OTA test cell."""
    return schema.CircuitReference(source='virtuoso', library='GATOR_TESTS', cell='ota5_v1', **fields)


def test_the_mapping_of_a_draft_holds_only_models_this_project_verified():
    mapping, unverified = native_cells.build_mapping(EXPORT)
    assert sorted(mapping['models']) == ['capacitor', 'g45n1svt', 'g45p1svt', 'vsource'] and unverified == []
    assert mapping['models']['g45n1svt']['terminals'] == ['D', 'G', 'S', 'B']       # from configs/gpdk045_*.json, not from memory
    assert mapping['net_roles'] == {'0': ['ground']} and mapping['parameter_groups'] == []   # nothing else is guessed
    mapping, unverified = native_cells.build_mapping(UNVERIFIED)
    assert unverified == ['pdk_mystery_dev'] and 'pdk_mystery_dev' not in mapping['models']


def test_the_ideal_current_source_and_resistor_are_known_without_any_example_circuit(tmp_path, monkeypatch):
    """Only the LDO example's mapping file named these two: deleting the example circuits (record 7.128) made "Save task"
    refuse every cell that holds one - six of the seven MScR tasks. They are the workbench's own now (record 7.187),
    as that file had them, also in a repository without a single mapping file."""
    netlist = EXPORT.rstrip('\n') + '\nIREF (VDD VBIAS) isource dc=50u type=dc\nRFB (VOUT 0) resistor r=9.49K\n'   # as real exports write them
    mapping, unverified = native_cells.build_mapping(netlist)
    assert unverified == []
    assert mapping['models']['isource'] == dict(kind='isource', terminals=['p', 'n'], roles=['positive', 'negative'], parameters={'dc': 'dc'})
    assert mapping['models']['resistor'] == dict(kind='resistor', terminals=['p', 'n'], roles=['positive', 'negative'], parameters={'r': 'r'})
    assert mapping['mapping_version'] == 'native-draft-1'                         # no PDK was needed for them
    monkeypatch.setattr(native_cells, 'repo_root', lambda: tmp_path)
    assert sorted(native_cells.verified_models()) == ['isource', 'resistor']
    (tmp_path / 'configs').mkdir()
    (tmp_path / 'configs' / 'gpdk045_other.json').write_text(json.dumps(dict(models=dict(
        isource=dict(kind='isource', terminals=['n', 'p'], roles=['negative', 'positive'], parameters={'dc': 'dc'})))))
    assert sorted(native_cells.verified_models()) == ['resistor']                 # defined differently in a file: left out, not chosen


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
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
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
    down = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path, daemon='failed')))
    blocked = down.post('/api/virtuoso/import', json=dict(profile_id='lab', library='GATOR_TESTS', cell='ota5_v1'))
    assert blocked.status_code == 409 and blocked.json()['detail']['gate']['blocking'] == ['daemon']
    assert down.post('/api/virtuoso/import', json=dict(profile_id='lab', library='x y', cell='c')).status_code in (409, 422)


# ---------------------------------------------------------- the cell's PDK, read in the same press (user request 2026-09-27)
def pdk_reader(tmp_path, pdk='ok', technology_library='gpdk045', netlist=EXPORT):
    """The fake reader, answering `--op pdk` too: the demo045 material (pdk='ok') or a failure (pdk='fail'). Every call's
    arguments are logged, so a test can see what the backend asked for and in which order."""
    from pdk_support import raw_material
    material = tmp_path / 'pdk_material.json'
    material.write_text(json.dumps(raw_material()))
    script = tmp_path / 'reader_pdk.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
with open({str(tmp_path / 'calls.log')!r}, 'a') as log:
    log.write(json.dumps(args) + '\\n')
if args['--op'] == 'pdk':
    if {pdk!r} == 'fail':
        sys.exit('Traceback\\nRuntimeError: the model file is not on the fixture host')
    print('progress line the bridge might print')
    print(Path({str(material)!r}).read_text())
    sys.exit(0)
out = Path(args['--output'])
out.mkdir(parents=True)
(out / 'netlist.scs').write_text({netlist!r})
(out / 'core_readback.json').write_text(json.dumps(dict(origin='fixture', instances=[])))
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'),
                      technology_library={technology_library!r})))
''')
    return [sys.executable, str(script)]


def reader_calls(tmp_path):
    """Read the fake cell reader's recorded command arguments."""
    return [json.loads(line) for line in (tmp_path / 'calls.log').read_text().splitlines()]


def test_reading_a_cell_reads_its_pdk_in_the_same_press(tmp_path):
    from gator_workbench import pdk
    imported = bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                                testbench='tb_ota5_ac_v1', command=pdk_reader(tmp_path))
    step = imported['pdk']
    assert step['state'] == 'read' and step['technology_library'] == 'gpdk045'
    assert step['pdk_id'] == 'demo045' and step['vocabulary'] == 'pdk:demo045'    # the fixture material describes demo045
    assert step['summary']['devices'] == 8 and step['label'].startswith('PDK demo045 (8 components, version ') and step['sha256']
    calls = reader_calls(tmp_path)
    assert [c['--op'] for c in calls] == ['import_cell', 'pdk'] and calls[1]['--library'] == 'gpdk045'   # the cell, then ITS technology library
    assert [p['pdk_id'] for p in pdk.list_pdks()] == ['demo045']                    # stored exactly as a press of Load stores it
    assert imported['device_count'] == 10 and imported['exported_cell'] == 'tb_ota5_ac_v1'   # the cell itself, as before
    assert tasks.load_task(reference(pdk_id='unspecified')).circuit['native_draft']


def test_a_part_that_this_very_read_describes_is_recognized_in_the_cell_at_once(tmp_path):
    """Record 7.190: the PDK - and the ideal parts of the generic library, read with it - come before the cell's device
    mapping is built, so the first read of a cell with an ideal inductor names its pins; it took a second read before."""
    netlist = EXPORT.rstrip('\n') + '\nLX (VOUT 0) inductor l=2n\nEX (VOUT 0 VINP VINN) vcvs gain=10\n'
    imported = bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                                command=pdk_reader(tmp_path, technology_library='demo045', netlist=netlist))
    step = imported['pdk']
    assert step['state'] == 'read' and step['ideal_parts']['library'] == 'analogLib' and step['ideal_parts']['summary']['recognized'] == 8
    assert 'components' not in step['ideal_parts']                                  # the summary; the PDK window shows the list
    assert imported['unverified_models'] == [] and imported['ideal_described_models'] == ['inductor', 'vcvs']
    assert imported['pdk_described_models'] == [] and imported['device_count'] == 12
    mapping = json.loads(Path(native_cells.load_import('GATOR_TESTS', 'ota5_v1')['mapping_path']).read_text())
    assert mapping['models']['inductor']['parameters'] == {'l': 'ind'} and '+ideal-analogLib-' in mapping['mapping_version']
    assert [c['--op'] for c in reader_calls(tmp_path)] == ['import_cell', 'pdk']     # still one read of each, in this order


def test_a_failed_pdk_read_leaves_the_cell_read(tmp_path):
    from gator_workbench import pdk
    imported = bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                                command=pdk_reader(tmp_path, pdk='fail'))
    step = imported['pdk']
    assert step['state'] == 'not_read' and step['technology_library'] == 'gpdk045'
    assert 'model file is not on the fixture host' in step['reason']
    assert imported['library'] == 'GATOR_TESTS' and imported['cell'] == 'ota5_v1' and imported['device_count'] == 10
    assert pdk.list_pdks() == [] and tasks.load_task(reference(pdk_id='unspecified')).circuit['native_draft']


def test_no_technology_library_means_no_pdk_read(tmp_path):
    imported = bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1',
                                command=pdk_reader(tmp_path, technology_library=None))
    assert imported['pdk']['state'] == 'skipped' and 'no PDK was read with the cell' in imported['pdk']['reason']
    assert [c['--op'] for c in reader_calls(tmp_path)] == ['import_cell']            # the reader was not asked for a PDK
