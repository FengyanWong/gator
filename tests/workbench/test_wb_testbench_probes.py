"""The Probes tab follows the testbench a Virtuoso cell was read through (`profiles.testbench_probes`).

Recorded REAL exports only (the user's ring oscillator in fixtures/ring_osc, the verified OTA testbench in
examples/circuits), fake reader processes, no Virtuoso, no simulation."""
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from gator_workbench import bridge_read, native_cells, profiles, recipes, schema, tasks
from helpers import probe, workbench_app
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from ring_cell_support import CIRCUIT, FIXTURE, config, connection_file, read_cell

REPO = Path(__file__).resolve().parents[2]
RING_SIGNALS = dict(m_osc_frequency_hz='OUT', m_supply_power_w='V0:p', m_supply_current_a='V0:p', m_osc_minimum_swing_v='OUT XU1.N1 XU1.N2',
                    m_osc_duty_cycle='OUT', m_osc_max_period_spread='OUT XU1.N1 XU1.N2', m_osc_max_window_drift='OUT XU1.N1 XU1.N2',
                    m_osc_startup_detection_s='OUT XU1.N1 XU1.N2')


def ring_import():
    return native_cells.load_import('GPDK045_RINGOSC', 'ring_osc_3stage')


def import_cell(tmp_path, *, library, cell, testbench, netlist, testbench_instances):
    """A fake reader that writes a recorded export plus a testbench readback listing `testbench_instances`."""
    script = tmp_path / f'reader_{cell}.py'
    readback = dict(origin='fixture', instances=[dict(name=n, lib=lib, cell=c) for n, lib, c in testbench_instances])
    script.write_text(f'''
import json, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
(out / 'netlist.scs').write_text({netlist!r})
(out / 'core_readback.json').write_text(json.dumps(dict(origin='fixture', instances=[])))
(out / 'testbench_readback.json').write_text(json.dumps({readback!r}))
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library=library, cell=cell, testbench=testbench, command=[sys.executable, str(script)])
    return native_cells.load_import(library, cell)


def test_the_ring_testbench_brings_the_ring_oscillator_probes_with_its_own_nets(tmp_path):
    read_cell(tmp_path)
    found = profiles.testbench_probes(ring_import())
    assert found['testbench_cell'] == 'tb_ring_osc_3stage' and found['circuit_type'] == 'ring_oscillator' and found['reason'] is None
    rows = found['rows']
    assert [r['source_name'] for r in rows] == list(recipes.RING_METRICS) and {r['analysis'] for r in rows} == {'tran'}
    assert {r['source_name']: r['unit'] for r in rows} == dict(recipes.RING_METRICS)
    assert {r['measurement_id']: r['signal'] for r in rows} == RING_SIGNALS           # the supply V0 and the nets of THIS testbench
    assert all(r['result_source'] == 'backend_profile' and 'tb_ring_osc_3stage' in r['notes'] for r in rows)
    assert 'V0' in next(r['notes'] for r in rows if r['source_name'] == 'supply_power_w')
    for r in rows:                                                                     # every row is a valid Probes row
        schema.MeasurementDefinition.model_validate(r)
    assert list(found['not_fitting']) == ['Op-amp / OTA (AC gain)'] and 'Missing here' in found['not_fitting']['Op-amp / OTA (AC gain)']


def test_a_cell_read_without_its_testbench_brings_no_probes(tmp_path):
    read_cell(tmp_path, testbench=None)
    found = profiles.testbench_probes(ring_import())
    assert found['rows'] == [] and found['circuit_type'] is None and 'without a testbench' in found['reason']


def test_the_verified_ota_testbench_brings_the_op_amp_probes(tmp_path):
    export = (REPO / 'examples/circuits/gpdk045_ota5.scs').read_text()                   # a recorded REAL export of tb_ota5_ac_v1
    imported = import_cell(tmp_path, library='OTA_LIB', cell='ota5_v1', testbench='tb_ota5_ac_v1', netlist=export,
                           testbench_instances=[('XU1', 'OTA_LIB', 'ota5_v1'), ('VDD', 'analogLib', 'vdc')])
    found = profiles.testbench_probes(imported)
    assert found['circuit_type'] == 'opamp_ac' and found['reason'] is None
    rows = {r['source_name']: r for r in found['rows']}
    from analog_optimizer.models.inputs import SpecSchema
    assert list(rows) == [m for m in recipes.OPAMP_METRICS if m in {name for name, _, _ in SpecSchema().metrics}]
    assert rows['gain_db_at_start']['signal'] == 'VOUT' and rows['gain_db_at_start']['analysis'] == 'ac'
    assert rows['supply_power_w']['signal'] == 'VDD:p' and rows['supply_power_w']['analysis'] == 'dc'
    assert 'exactly one voltage source' in found['not_fitting']['Ring oscillator (free-running)']


def test_a_testbench_that_fits_no_circuit_type_says_why_and_brings_nothing(tmp_path):
    netlist = (FIXTURE / 'netlist.scs').read_text() + 'V1 (NX 0) vsource dc=0.5 type=dc\n'     # a second source: not a free-running ring
    imported = import_cell(tmp_path, library='GPDK045_RINGOSC', cell='ring_osc_3stage', testbench='tb_two_sources', netlist=netlist,
                           testbench_instances=[('XU1', 'GPDK045_RINGOSC', 'ring_osc_3stage')])
    found = profiles.testbench_probes(imported)
    assert found['rows'] == [] and found['circuit_type'] is None and 'fits none of the circuit types' in found['reason']
    assert sorted(found['not_fitting']) == ['Op-amp / OTA (AC gain)', 'Ring oscillator (free-running)']
    assert 'found 2' in found['not_fitting']['Ring oscillator (free-running)']


def test_a_testbench_without_the_cell_says_so(tmp_path):
    imported = import_cell(tmp_path, library='GPDK045_RINGOSC', cell='ring_osc_3stage', testbench='tb_other',
                           netlist=(FIXTURE / 'netlist.scs').read_text(), testbench_instances=[('XU1', 'GPDK045_RINGOSC', 'another_cell')])
    found = profiles.testbench_probes(imported)
    assert found['rows'] == [] and 'exactly once (found 0 times)' in found['reason']


def test_the_circuit_load_answers_the_probes_of_the_copy_and_they_validate(tmp_path):
    read_cell(tmp_path)
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
    loaded = client.post('/api/circuit/load', json=dict(circuit=CIRCUIT)).json()
    assert loaded['native_draft'] and loaded['circuit']['testbench_cell'] == 'tb_ring_osc_3stage'
    assert loaded['testbench_probes'] == json.loads(json.dumps(profiles.testbench_probes(ring_import())))
    # The form may show another testbench than the copy was read through: the answer is still the copy's.
    other = client.post('/api/circuit/load', json=dict(circuit=dict(CIRCUIT, testbench_cell='tb_something_else'))).json()
    assert other['testbench_probes']['testbench_cell'] == 'tb_ring_osc_3stage'
    full = config().model_dump(mode='json')
    full['measurements'] = loaded['testbench_probes']['rows']
    report = client.post('/api/config/validate', json=dict(config=full)).json()
    assert not [i for i in report['issues'] if i['path'].startswith('measurements') and i['level'] in ('error', 'blocker')]
    browse = client.post('/api/circuit/load', json=dict(circuit=dict(CIRCUIT, cell='never_read'))).json()
    assert 'testbench_probes' not in browse                                          # no copy, nothing to say
    mock = client.post('/api/circuit/load', json=dict(circuit=dict(source='registered_task', task_id='synthetic:gpdk045_ota5'))).json()
    assert 'testbench_probes' not in mock


def test_after_create_profile_the_task_brings_exactly_the_rows_the_testbench_brought(tmp_path):
    read_cell(tmp_path)
    connection_file()
    rows = profiles.testbench_probes(ring_import())['rows']
    profiles.create_profile('ring_osc_3stage', config().model_copy(update=dict(
        measurements=[schema.MeasurementDefinition.model_validate(r) for r in rows])), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    starter = tasks.starter_config('real:ring_osc_3stage')['measurements']
    assert json.dumps(starter) == json.dumps(rows)                                   # key order too: the form compares JSON text
