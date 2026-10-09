"""The user's own copy (2026-09-23, user request): the workbench makes no working copy of its own any more. Reading a
cell with `work_here` declares the cell that was read as the task flow's working copy (copy == original); the route
that made a copy refuses; a task saves into that cell and writes its Maestro setup there; the cells that carry the
frozen M6 evidence are refused. FAKE processes and recorded netlists only - no Virtuoso."""
import json

import pytest
from fastapi.testclient import TestClient

from gator_workbench import bridge_read, profiles, tasks, working_copy, virtuoso_setup as vs
from helpers import bridge_is_importable, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from helpers import probe
from fakes_virtuoso import fake_reader
from ring_cell_support import connection_file, read_cell
from task_save_support import config
from fakes_virtuoso import copy_reader, maestro_netlister
from fakes_virtuoso import SETUP, setup_writer
from fakes_virtuoso import CELL, COPY, LIB, RING, TB, fake_writer, imported


def test_the_cells_of_a_declared_copy_come_from_the_netlister_comments():
    assert working_copy.netlist_cells(RING, LIB) == [dict(cell=CELL, views=['schematic']), dict(cell=TB, views=['schematic'])]
    assert working_copy.netlist_cells(RING, 'ANOTHER_LIB') == []
    twice = RING + '\n// Library name: GPDK045_RINGOSC\n// Cell name: ring_osc_3stage\n// View name: symbol\n'
    assert working_copy.netlist_cells(twice, LIB)[0] == dict(cell=CELL, views=['schematic', 'symbol'])


def test_a_read_cell_becomes_the_working_copy_once_the_user_says_it_is_a_copy(tmp_path):
    with pytest.raises(working_copy.CopyError, match='Read the cell into the workbench first'):
        working_copy.declare('lab', LIB, CELL)
    imported(tmp_path)
    assert working_copy.load(LIB, CELL) is None                                 # reading alone declares nothing
    record = working_copy.declare('lab', LIB, CELL)
    assert record['declared'] and record['verified'] and not record['already'] and record['problems'] == []
    assert record['copy'] == dict(library=LIB, cell=CELL, testbench=TB, path=None)
    assert record['original'] == dict(library=LIB, cell=CELL, testbench=TB, netlist_sha256=record['original']['netlist_sha256'])
    assert working_copy.is_declared(record) and [c['cell'] for c in record['cells']] == [CELL, TB]
    again = working_copy.declare('lab', LIB, CELL)
    assert again['already'] and again['created_utc'] == record['created_utc']
    target = working_copy.draft_target(LIB, CELL)                                # what every write into "the copy" addresses
    assert target['copy'] == record['copy'] and target['names'] == {CELL: CELL, TB: TB} and target['schematics'] == [CELL, TB]
    assert working_copy.is_declared(target)
    assert working_copy.reverify(LIB, CELL)['declared']                          # nothing to compare: no separate original
    assert not working_copy.is_declared(dict(original=dict(library=LIB, cell=CELL), copy=dict(library=COPY, cell=CELL)))


def test_a_made_copy_from_before_keeps_its_record_and_is_not_declared(tmp_path):
    imported(tmp_path)
    made = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    assert made['verified'] and not made.get('declared') and not working_copy.is_declared(made)
    kept = working_copy.declare('lab', LIB, CELL)                                # a task saved on that copy keeps running on it
    assert kept['already'] and kept['copy']['library'] == COPY and not kept.get('declared')


def test_the_pdk_itself_and_a_cell_read_the_wrong_way_are_refused(tmp_path):
    """Any design cell the user imports may be declared (user decision 2026-09-23, relayed by the flow session: the
    built-in M6 cells are examples, not a protected set). Only the PDK's own library, an export that does not name the
    cell, and a cell read without its testbench are refused."""
    reader = fake_reader(tmp_path)
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='gpdk045', cell='ota5_v1', testbench='tb_ota5_ac_v1', command=reader)
    with pytest.raises(working_copy.CopyError, match='the PDK itself'):
        working_copy.declare('lab', 'gpdk045', 'ota5_v1')
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='MINE', cell='ota5_v1', testbench='tb_ota5_ac_v1', command=reader)
    with pytest.raises(working_copy.CopyError, match='does not name both'):      # the export names GATOR_TESTS cells, not MINE's
        working_copy.declare('lab', 'MINE', 'ota5_v1')
    bridge_read.read(probe(tmp_path), 'lab', 'import_cell', library='GATOR_TESTS', cell='ota5_v1', command=reader)     # no testbench
    with pytest.raises(working_copy.CopyError, match='through its testbench first'):
        working_copy.declare('lab', 'GATOR_TESTS', 'ota5_v1')
    assert working_copy.load('gpdk045', 'ota5_v1') is None and working_copy.load('MINE', 'ota5_v1') is None


def test_the_import_route_declares_on_request_and_the_copy_route_refuses(tmp_path, monkeypatch):
    real_read = bridge_read.read
    reader = fake_reader(tmp_path)
    monkeypatch.setattr(bridge_read, 'read', lambda monitor, profile_id, op, **kw: real_read(monitor, profile_id, op, command=reader, **kw))
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path)))
    body = dict(profile_id='lab', library='MY_LIB', cell='ota5_v1', testbench='tb_ota5_ac_v1')
    circuit = dict(source='virtuoso', library='MY_LIB', cell='ota5_v1', testbench_cell='tb_ota5_ac_v1')
    monkeypatch.setattr(working_copy, 'netlist_cells', lambda text, library: [dict(cell='ota5_v1', views=['schematic']), dict(cell='tb_ota5_ac_v1', views=['schematic'])])
    plain = client.post('/api/virtuoso/import', json=body)
    assert plain.status_code == 200 and 'working_copy' not in plain.json() and working_copy.load('MY_LIB', 'ota5_v1') is None
    loaded = client.post('/api/circuit/load', json=dict(circuit=circuit)).json()
    assert loaded['loaded'] and loaded['native_draft'] and loaded['working_copy'] is None
    declared = client.post('/api/virtuoso/import', json=dict(body, work_here=True))
    assert declared.status_code == 200, declared.json()
    assert declared.json()['working_copy']['declared'] and declared.json()['working_copy']['copy'] == dict(library='MY_LIB', cell='ota5_v1', testbench='tb_ota5_ac_v1', path=None)
    loaded = client.post('/api/circuit/load', json=dict(circuit=circuit)).json()
    assert loaded['working_copy']['verified'] and loaded['working_copy']['declared']   # the page learns of it with the circuit
    refused = client.post('/api/virtuoso/copy', json=dict(profile_id='lab', library='MY_LIB', cell='ota5_v1'))
    assert refused.status_code == 409 and refused.json()['detail']['code'] == 'copies_not_made'
    assert 'copy the cell and its testbench in Virtuoso yourself' in refused.json()['detail']['message']
    bad = client.post('/api/virtuoso/import', json=dict(body, library='gpdk045', work_here=True))
    assert bad.status_code == 409 and 'PDK itself' in bad.json()['detail']['message'] and bad.json()['detail']['code'] == 'refused'
    early = client.post('/api/virtuoso/import', json=dict(body, cell='other_v1', testbench=None, work_here=True))
    assert early.status_code == 409 and 'Testbench cell first' in early.json()['detail']['message']
    assert working_copy.native_cells.load_import('MY_LIB', 'other_v1') is None                # refused before any export


def test_a_task_saved_on_a_declared_copy_writes_and_runs_in_that_cell(tmp_path):
    connection_file()
    read_cell(tmp_path)
    working_copy.declare('lab', LIB, CELL)
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    made = profiles.save_task(probe(tmp_path), 'lab', 'ring_own', cfg, library=LIB, cell=CELL, extras=dict(analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}),
                              commands=dict(read=copy_reader(tmp_path), setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path)))
    assert made['created'] and made['runnable'] and made['maestro_matches']
    assert made['copy'] == dict(library=LIB, cell=CELL, testbench=TB, path=None) and made['original']['library'] == LIB
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['op'] == 'write_setup' and call['copy'] == LIB and call['testbench'] == TB      # the Maestro test goes into the cell itself
    [netlisted] = [json.loads(line) for line in (tmp_path / 'netlister_calls.jsonl').read_text().splitlines()]
    assert netlisted == dict(op='maestro_netlist', copy=LIB, testbench=TB)
    entry = profiles.list_profiles()['ring_own']
    assert entry['library'] == LIB and entry['core_cell'] == CELL and working_copy.load(LIB, CELL)['claimed_by'] == 'ring_own'
    config_, _, _ = tasks.generated_bridge_config('ring_own')
    assert config_.library == LIB                                                  # a run's size writes go into this cell
    data = profiles.task_file('ring_own')
    assert data['cell']['library'] == LIB and data['copy']['library'] == LIB
    assert profiles.task_for_cell(LIB, CELL) == dict(task_key='real:ring_own', name='ring_own', generated=True)
