"""Working copies (`working_copy`, `bridge_setup` op `make_copy`): the task flow edits COPIES in Virtuoso, never the
user's cells. FAKE write process and recorded netlists only - no Virtuoso."""
import json
from pathlib import Path
import sys

import pytest

from gator_workbench import bridge_read, bridge_setup, working_copy
from helpers import probe
from fakes_virtuoso import CELL, COPY, LIB, RING, TB, fake_writer, imported


def calls(tmp_path, log='calls.jsonl'):
    return [json.loads(line) for line in (tmp_path / log).read_text().splitlines()]


def test_the_hierarchy_answer_is_read_in_discovery_order():
    cells = bridge_setup.parse_hierarchy(f'{TB}|views=schematic |cdf=nil\n{CELL}|views=symbol schematic |cdf=nil\n'
                                         'sub|views=symbol |cdf=t\n bad name|views=x|cdf=nil\n')
    assert cells == [dict(cell=TB, views=['schematic'], has_cdf=False), dict(cell=CELL, views=['schematic', 'symbol'], has_cdf=False),
                     dict(cell='sub', views=['symbol'], has_cdf=True)]


def test_a_copy_must_netlist_like_the_original_and_point_at_itself():
    copy = RING.replace(f'// Library name: {LIB}', f'// Library name: {COPY}')
    assert working_copy.compare(RING, copy, copy_library=COPY, copied_cells=[CELL, TB]) == []
    assert working_copy.netlist_libraries(copy) == {CELL: COPY, TB: COPY}
    # The testbench still using the ORIGINAL cell netlists identically - only the library comment tells.
    half = copy.replace(f'// Library name: {COPY}\n// Cell name: {CELL}', f'// Library name: {LIB}\n// Cell name: {CELL}', 1)
    assert working_copy.compare(RING, half, copy_library=COPY, copied_cells=[CELL, TB]) == \
        [f'In the copy these cells still come from another library: {CELL}']
    changed = copy.replace('w=(2u)', 'w=(3u)', 1)
    [problem] = working_copy.compare(RING, changed, copy_library=COPY, copied_cells=[CELL, TB])
    assert 'does not netlist like the original in subckt ring_osc_3stage' in problem and 'w=(3u)' in problem
    # Re-pointing an instance moves it in Virtuoso's database, so the netlister writes it elsewhere (seen on the real
    # copy: XU1 after V0). The order of statements means nothing to Spectre.
    reordered = copy.replace('XU1 (OUT VDD 0) ring_osc_3stage\nV0 (VDD 0) vsource dc=1.0 type=dc',
                             'V0 (VDD 0) vsource dc=1.0 type=dc\nXU1 (OUT VDD 0) ring_osc_3stage')
    assert reordered != copy and working_copy.compare(RING, reordered, copy_library=COPY, copied_cells=[CELL, TB]) == []
    # Continuation lines are one statement: a changed value on the second line of a transistor is still found.
    wrapped = copy.replace('sca=56.99756', 'sca=57.5', 1)
    assert 'only in the copy' in working_copy.compare(RING, wrapped, copy_library=COPY, copied_cells=[CELL, TB])[0]
    blocks = working_copy.structure(RING)
    assert set(blocks) == {'(top level)', 'subckt ring_osc_3stage'} and len(blocks['subckt ring_osc_3stage']) == 9


def test_a_copy_is_made_once_verified_and_recorded(tmp_path):
    with pytest.raises(working_copy.CopyError, match='Read the cell into the workbench first'):
        working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    imported(tmp_path)
    record = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    assert record['verified'] and record['problems'] == [] and record['originals_unchanged'] and not record['already']
    assert record['copy'] == dict(library=COPY, cell=CELL, testbench=TB, path=f'/home/minlei/{COPY}')
    assert record['original']['library'] == LIB and record['created_library']
    assert working_copy.own_libraries()[COPY]['for_library'] == LIB
    [call] = calls(tmp_path)
    assert call['--op'] == 'make_copy' and call['--copy-library'] == COPY and call['--testbench'] == TB
    assert '--reuse-library' not in call and json.loads(call['--overwrite']) == []
    assert not list(working_copy.store_root().rglob('.incoming-*'))
    # A copy is made once: the second press answers with the record and writes nothing.
    again = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    assert again['already'] and len(calls(tmp_path)) == 1
    assert working_copy.load(LIB, CELL)['verified']


def test_a_copy_that_stopped_half_way_is_finished_by_the_next_press_and_nothing_else(tmp_path):
    imported(tmp_path)
    with pytest.raises(RuntimeError, match='dbCopyCellView refused'):
        working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path, fail_after=2))
    assert working_copy.load(LIB, CELL) is None
    assert working_copy.own_libraries()[COPY]['path'] == f'/home/minlei/{COPY}'      # the library it made is still ours
    attempt = json.loads((working_copy.store_root() / LIB / f'{CELL}.{working_copy.ATTEMPT}').read_text())
    assert attempt['copied'] == [f'{CELL}/schematic', f'{TB}/schematic']            # sorted
    record = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    assert record['verified']
    last = calls(tmp_path)[-1]
    assert '--reuse-library' in last and json.loads(last['--overwrite']) == [f'{CELL}/schematic', f'{TB}/schematic']
    assert not (working_copy.store_root() / LIB / f'{CELL}.{working_copy.ATTEMPT}').exists()


def test_a_copy_that_differs_or_touched_the_original_is_kept_but_not_verified(tmp_path):
    imported(tmp_path)
    record = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path, touched=True,
                                                                                         netlist=RING.replace('w=(1u)', 'w=(4u)', 1)))
    assert not record['verified'] and not record['originals_unchanged']
    assert any('does not netlist like the original' in p for p in record['problems'])
    assert any('read back differently' in p for p in record['problems'])


def test_no_write_without_the_gate_or_without_a_testbench(tmp_path):
    imported(tmp_path)
    with pytest.raises(PermissionError, match='gate blocked writing'):
        working_copy.make(probe(tmp_path, tunnel='failed'), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    assert not (tmp_path / 'calls.jsonl').exists()
    meta = working_copy.native_cells.cell_dir(LIB, CELL) / 'meta.json'
    data = json.loads(meta.read_text())
    meta.write_text(json.dumps(dict(data, testbench_cell=None)))
    with pytest.raises(working_copy.CopyError, match='through its testbench'):
        working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))


def test_a_stored_copy_can_be_checked_again_without_virtuoso(tmp_path):
    imported(tmp_path)
    record = working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path, netlist=RING.replace(
        f'// Library name: {LIB}', f'// Library name: {COPY}').replace('XU1 (OUT VDD 0) ring_osc_3stage\nV0 (VDD 0) vsource dc=1.0 type=dc',
                                                                     'V0 (VDD 0) vsource dc=1.0 type=dc\nXU1 (OUT VDD 0) ring_osc_3stage')))
    assert record['verified']
    stored = working_copy.record_dir(LIB, CELL) / 'netlist.scs'
    stored.write_text(stored.read_text().replace('w=(1u)', 'w=(5u)', 1))
    again = working_copy.reverify(LIB, CELL)
    assert not again['verified'] and 'reverified_utc' in again and working_copy.load(LIB, CELL)['verified'] is False
    assert working_copy.reverify('GPDK045_RINGOSC', 'other') is None


def test_library_names_stay_plain_cadence_names():
    assert working_copy.copy_library_name('GPDK045_RINGOSC') == COPY
    with pytest.raises(working_copy.CopyError):
        working_copy.copy_library_name('L' * 70)
    with pytest.raises(working_copy.CopyError):
        working_copy.record_dir('bad name', CELL)


def test_a_task_saved_under_another_settings_folder_keeps_its_copy_records_in_this_one():
    """A saved task stores its working-copy folder as an absolute path into the settings folder that saved it. Under a
    scratch settings folder holding copies of the task files, or after the repository moved, the setup read wrote its logs
    into the old folder until record 7.137 (a scratch run's five read logs in the live folder, 2026-10-01)."""
    here = working_copy.store_root()
    saved = dict(state_dir='/elsewhere/configs/local/workbench/working_copies/MScR/mscr_ota7t')
    assert working_copy.state_path(saved) == here / 'MScR' / 'mscr_ota7t'
    assert working_copy.state_path(dict(state_dir='/old/repo/working_copies/_tasks/t2')) == here / '_tasks' / 't2'   # Save as
    assert working_copy.state_path(dict(state_dir=str(here / LIB / CELL))) == here / LIB / CELL                       # unchanged
    assert working_copy.state_path(dict(state_dir='/tmp/state')) == Path('/tmp/state')     # not a working-copy folder: as stored
    (here / 'MScR' / 'mscr_ota7t').mkdir(parents=True)
    (here / 'MScR' / 'mscr_ota7t' / 'last_written_setup.json').write_text(json.dumps(dict(test='GATOR')))
    assert working_copy.last_written(saved) == dict(test='GATOR')
    assert working_copy._request_dir(saved).parent == here / 'MScR' / 'mscr_ota7t' / 'setup'
