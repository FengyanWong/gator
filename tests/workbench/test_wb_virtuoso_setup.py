"""The Virtuoso side of a task (`virtuoso_setup`, `working_copy.read_setup/write_setup`, `bridge_setup` setup ops):
what the working copy's Maestro view holds and how it maps onto the rows. FAKE write process only - no Virtuoso. The
answer shapes (spec lists, output expressions, bindings) are the ones the live IC23.1 gave on 2026-09-21."""
import json
from pathlib import Path
import sys

import pytest

from gator_workbench import bridge_setup, virtuoso_setup as vs, working_copy
from helpers import make_config
from test_wb_api import probe
from test_wb_working_copy import CELL, COPY, LIB, TB, fake_writer, imported

SETUP = dict(test='GATOR', model_files=[['/pdk/gpdk045.scs', 'tt']], analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}},
             outputs=[dict(name='freq', expression='frequency(VT("/OUT"))'), dict(name='vmax', expression='ymax(VT("/OUT"))')],
             specs=[dict(output='freq', op='gt', value='1e+09'), dict(output='vmax', op='range', value=['0.9', '1.1'])],
             variables={'VSUP': '1.0'}, bindings=[dict(cell=TB, instance='V0', parameter='vdc', variable='VSUP')])


def write(monitor, setup, **kw):
    """Write a setup into the cell's OWN working copy - `write_setup_on` on `draft_target`, the pair a task save and
    the agent's tool use. Raises `CopyError` when no copy was made."""
    return working_copy.write_setup_on(monitor, 'lab', working_copy.draft_target(LIB, CELL), setup, **kw)


def test_only_listed_calculator_functions_and_names_pass():
    assert vs.check_expression('frequency(VT("/OUT"))') == []
    assert vs.check_expression('average(IT("/V0/PLUS")) * VSUP', variables={'VSUP'}) == []
    assert vs.check_expression('cross(VT("/OUT") 0.5 1 "rising" nil nil)') == []
    assert vs.check_expression('settlingTime(VT("/OUT") 0 nil 1.0 t 5 ?multiple nil)') == []
    assert vs.check_expression('system("rm -rf ~")') == ['system() is not a calculator function the workbench accepts']
    assert 'VDD is neither a design variable' in vs.check_expression('VT("/OUT") / VDD')[0]
    assert any("';'" in p for p in vs.check_expression('ymax(VT("/OUT")); load("x.il")'))
    assert vs.check_expression('ymax(VT("/OUT")') == ['Unbalanced brackets']
    assert vs.check_expression('`(evalstring "x")')[0].startswith("'`'")
    assert vs.check_expression('') == ['The expression is empty']


def test_units_and_analyses_are_suggested_from_the_expression():
    assert (vs.suggested_unit('frequency(VT("/OUT"))'), vs.analysis_of('frequency(VT("/OUT"))')) == ('Hz', 'tran')
    assert (vs.suggested_unit('ymax(VT("/OUT"))'), vs.suggested_unit('average(IT("/V0/PLUS"))')) == ('V', 'A')
    assert (vs.suggested_unit('phaseMargin(VF("/OUT"))'), vs.analysis_of('phaseMargin(VF("/OUT"))')) == ('deg', 'ac')
    assert vs.suggested_unit('average(IT("/V0/PLUS")) * VT("/VDD")') == '1'           # mixed: no guess
    assert vs.analysis_of('VT("/A") - VF("/B")') == 'other'


def test_a_setup_is_checked_before_anything_is_written():
    bindable = {(TB, 'V0'): {'vdc', 'srcType'}}
    assert vs.validate(SETUP, bindable=bindable) == []
    bad = dict(SETUP, outputs=SETUP['outputs'] + [dict(name='freq', expression='system("x")')],
               specs=[dict(output='gone', op='gt', value='1'), dict(output='vmax', op='range', value='1')],
               bindings=[dict(cell=CELL, instance='MN1', parameter='w', variable='VSUP'), dict(cell=TB, instance='V0', parameter='dc', variable='NOPE')])
    problems = vs.validate(bad, bindable=bindable)
    assert 'Two outputs have the same name' in problems
    assert any('system() is not' in p for p in problems)
    assert any("output 'gone'" in p for p in problems) and any('range spec needs two values' in p for p in problems)
    assert any('MN1 in ring_osc_3stage cannot be set by a variable' in p for p in problems)
    assert any("V0 has no parameter 'dc'" in p for p in problems) and any('NOPE' in p for p in problems)


def test_differences_ignore_the_options_maestro_adds_and_name_what_differs():
    assert [vs.canonical(v) for v in ('1G', '1e+09', '1000000000', ' conservative ', '50n', '5e-08')] == \
        ['1000000000', '1000000000', '1000000000', 'conservative', '5e-08', '5e-08']
    found = json.loads(json.dumps(SETUP))
    found['analyses']['tran'].update(trannoisemethod='default', annotate='status')          # Maestro's own additions
    assert vs.differences(SETUP, found) == []
    assert vs.fingerprint(SETUP) == vs.fingerprint(json.loads(json.dumps(SETUP)))
    found['outputs'][0]['expression'] = 'frequency(VT("/N1"))'
    found['specs'][0]['value'] = '2e+09'
    found['variables']['VSUP'] = '1.1'
    found['bindings'] = []
    found['analyses']['ac'] = {'start': '1'}
    diffs = vs.differences(SETUP, found)
    assert any(d.startswith('Output freq') for d in diffs) and any(d.startswith('Spec on freq') for d in diffs)
    assert any('Design variable VSUP' in d for d in diffs) and any('V0.vdc' in d for d in diffs)
    assert any('also runs a ac' in d for d in diffs)


def test_rows_and_setup_map_onto_each_other():
    rows = vs.to_rows(SETUP)
    freq, vmax = rows['measurements']
    assert freq == dict(measurement_id='m_freq', analysis='tran', result_source='ade_output', source_name='freq',
                        signal='frequency(VT("/OUT"))', unit='Hz', notes=freq['notes']) and 'suggested' in freq['notes']
    spec_freq, spec_vmax = rows['targets']
    assert (spec_freq['equation'], spec_freq['constraint'], spec_freq['lower']) == ('m_freq', '>=', 1e9)
    assert (spec_vmax['constraint'], spec_vmax['lower'], spec_vmax['upper'], spec_vmax['unit']) == ('interval', 0.9, 1.1, 'V')

    def rows_into(raw):
        raw['measurements'] = rows['measurements'] + [dict(measurement_id='m_extra', analysis='tran', result_source='expression',
                                                           expression='m_freq * 2', unit='Hz')]
        raw['targets'] = rows['targets'] + [dict(metric_id='energy', equation='m_vmax / m_freq', unit='1', constraint='<=', upper=1,
                                                 normalization_scale=1.0)]
    config = make_config(Path('.'), mutate=rows_into)
    back = vs.from_rows(config, model_files=SETUP['model_files'], analyses=SETUP['analyses'], variables=SETUP['variables'],
                        bindings=SETUP['bindings'])
    assert vs.differences(SETUP, back) == []        # a formula over several probes stays in the workbench
    assert [o['name'] for o in back['outputs']] == ['freq', 'vmax']


def test_the_spec_answers_of_the_live_installation_are_read():
    assert bridge_setup.parse_spec('("gt" "1e+09")') == dict(op='gt', value='1e+09')
    assert bridge_setup.parse_spec('("range" "0.9" "1.1")') == dict(op='range', value=['0.9', '1.1'])
    assert bridge_setup.parse_spec('nil') is None and bridge_setup.parse_spec('') is None
    assert bridge_setup.parse_spec('("tol" "1" "5")')['op'] == 'unsupported'
    assert bridge_setup._q('a"b\\c') == '"a\\"b\\\\c"'


def test_initial_conditions_travel_as_a_file_the_test_includes():
    """A circuit that does not start by itself (an oscillator sits in its symmetric DC point) gets a start voltage per
    net. They are one ic file on the simulator host, registered with the test as a model file without a section, so
    Maestro's netlist includes it - and the deck's MODEL include is the one that names a section."""
    text = vs.ic_file_text({'OUT': '0.9', 'N1': 0, 'N2': '900m'})
    assert text.splitlines()[1] == 'ic N1=0 N2=0.9 OUT=0.9'                      # one order, one spelling
    assert vs.parse_ic_file(text) == {'N1': '0', 'N2': '0.9', 'OUT': '0.9'}
    assert vs.parse_ic_file('// nothing here\n') == {} and vs.ic_file_text({}).splitlines() == [vs.IC_HEADER.strip()]
    assert vs.differences(dict(initial_conditions={'OUT': '0.9'}), dict(initial_conditions={'OUT': '0.8', 'N1': '0'})) == [
        'Initial condition on N1: the task says (none), Virtuoso has 0',
        'Initial condition on OUT: the task says 0.9, Virtuoso has 0.8']
    problems = vs.validate(dict(initial_conditions={'OUT 1': '1', 'N1': 'later'}))
    assert any('a net is named as Virtuoso spells it' in p for p in problems) and any("'later' is not a voltage" in p for p in problems)
    head = 'include "/home/u/.gator/ic/L__T__GATOR.scs"\ninclude "/pdk/gpdk045.scs" section=tt\n'
    assert vs.deck_include(head) == ('/pdk/gpdk045.scs', 'tt') and len(vs.deck_includes(head)) == 2
    assert vs.deck_include('include "/pdk/gpdk045.scs"\n') == ('/pdk/gpdk045.scs', None)       # a task without conditions
    with pytest.raises(vs.SetupError, match='no single model include'):
        vs.deck_include('include "/a.scs"\ninclude "/b.scs"\n')


def test_the_conditions_are_written_with_the_setup_and_read_back(tmp_path):
    imported(tmp_path)
    working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    readback = working_copy.native_cells.cell_dir(LIB, CELL) / 'testbench_readback.json'
    readback.write_text(json.dumps(dict(instances=[dict(name='V0', lib='analogLib', cell='vdc', params=dict(vdc='1.0', srcType='dc')),
                                                   dict(name='XU1', lib=LIB, cell=CELL, params={})])))
    conditions = {'OUT': '0.9', 'N1': '0'}
    answer = dict(written_answer(), initial_conditions=conditions, ic_file='/home/u/.gator/ic/x.scs')
    result = write(probe(tmp_path), dict(SETUP, initial_conditions=conditions), command=setup_writer(tmp_path, answer))
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['request']['setup']['initial_conditions'] == conditions and result['matches']
    assert result['initial_conditions'] == conditions
    gone = write(probe(tmp_path), dict(SETUP, initial_conditions=conditions),
                 command=setup_writer(tmp_path, dict(written_answer(), initial_conditions={})))
    assert not gone['matches'] and gone['differences'] == ['Initial condition on N1: the task says 0, Virtuoso has (none)',
                                                           'Initial condition on OUT: the task says 0.9, Virtuoso has (none)']


def setup_writer(tmp_path, answer):
    """Stands in for the setup ops of `python -m gator_workbench.bridge_setup`: logs the request, answers `answer`."""
    script = tmp_path / 'setup_writer.py'
    script.write_text(f'''
import json, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv)}}
request = json.loads(Path(args['--request']).read_text())
with open({str(tmp_path / 'setup_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(dict(op=args['--op'], copy=args['--copy-library'], testbench=args['--testbench'], request=request)) + '\\n')
print(json.dumps({json.dumps(answer)!r} and json.loads({json.dumps(answer)!r})))
''')
    return [sys.executable, str(script)]


def written_answer():
    return dict(exists=True, tests=['GATOR'], test='GATOR', model_files=SETUP['model_files'],
                analyses={'tran': dict(SETUP['analyses']['tran'], trannoisemethod='default')}, variables=SETUP['variables'],
                outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={}, bindings=SETUP['bindings'])


def test_writing_a_setup_goes_to_the_copy_only_and_is_compared_on_the_way_back(tmp_path):
    imported(tmp_path)
    with pytest.raises(working_copy.CopyError, match='Make the working copy first'):
        write(probe(tmp_path), SETUP)
    working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    readback = working_copy.native_cells.cell_dir(LIB, CELL) / 'testbench_readback.json'
    readback.write_text(json.dumps(dict(instances=[dict(name='V0', lib='analogLib', cell='vdc', params=dict(vdc='1.0', srcType='dc')),
                                                   dict(name='XU1', lib=LIB, cell=CELL, params={})])))
    result = write(probe(tmp_path), SETUP, command=setup_writer(tmp_path, written_answer()))
    assert result['matches'] and result['differences'] == [] and result['fingerprint'] == vs.fingerprint(written_answer())
    assert [r['measurement_id'] for r in result['rows']['measurements']] == ['m_freq', 'm_vmax']
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert (call['op'], call['copy'], call['testbench']) == ('write_setup', COPY, TB)
    assert call['request']['setup']['outputs'] == SETUP['outputs'] and call['request']['restore'] == []
    assert call['request']['cells'] == [TB, CELL]
    # A variable no longer set on a parameter puts the ORIGINAL value back.
    write(probe(tmp_path), dict(SETUP, variables={}, bindings=[]),
          command=setup_writer(tmp_path, dict(written_answer(), variables={}, bindings=[])))
    last = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()][-1]
    assert last['request']['restore'] == [[TB, 'V0', 'vdc', '1.0']]
    # What differs on the way back is reported, not hidden.
    drifted = dict(written_answer(), specs=[dict(output='freq', op='gt', value='2e+09'), SETUP['specs'][1]])
    result = write(probe(tmp_path), SETUP, command=setup_writer(tmp_path, drifted))
    assert not result['matches'] and result['differences'] == ["Spec on freq: the task says ('gt', '1000000000'), Virtuoso has ('gt', '2000000000')"]


def test_a_setup_that_fails_its_checks_writes_nothing(tmp_path):
    imported(tmp_path)
    working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    bad = dict(SETUP, bindings=[dict(cell=CELL, instance='MN1', parameter='w', variable='VSUP')])
    with pytest.raises(vs.SetupError, match='MN1 in ring_osc_3stage cannot be set by a variable'):
        write(probe(tmp_path), bad, command=setup_writer(tmp_path, written_answer()))
    with pytest.raises(PermissionError, match='gate blocked writing the Maestro setup'):
        write(probe(tmp_path, daemon='failed'), dict(SETUP, bindings=[], variables={}),
              command=setup_writer(tmp_path, written_answer()))
    assert not (tmp_path / 'setup_calls.jsonl').exists()


def test_reading_an_empty_or_foreign_view_gives_no_rows(tmp_path):
    imported(tmp_path)
    working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))
    empty = dict(exists=False, tests=[], test=None, model_files=[], analyses={}, variables={}, outputs=[], specs=[], raw_specs={}, bindings=[])
    result = working_copy.read_setup(probe(tmp_path), 'lab', LIB, CELL, command=setup_writer(tmp_path, empty))
    assert result['fingerprint'] is None and result['rows'] == dict(measurements=[], targets=[])
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['op'] == 'read_setup' and call['request']['test'] == 'GATOR'


def test_the_copy_and_setup_routes_go_through_the_same_checks(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from gator_workbench.api import create_app
    imported(tmp_path)
    real_run = bridge_setup.run
    answers = dict(make_copy=None, read_setup=written_answer(), write_setup=written_answer())

    def fake_run(profile_id, op, *, args, output, timeout=600.0, command=None):
        command = fake_writer(tmp_path) if op == 'make_copy' else setup_writer(tmp_path, answers[op])
        return real_run(profile_id, op, args=args, output=output, timeout=timeout, command=command)
    monkeypatch.setattr(bridge_setup, 'run', fake_run)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    cell = dict(library=LIB, cell=CELL)
    assert client.post('/api/virtuoso/setup/read', json=dict(cell, profile_id='lab')).status_code == 409     # no copy yet
    made = client.post('/api/virtuoso/copy', json=dict(cell, profile_id='lab'))
    assert made.status_code == 200 and made.json()['verified']
    loaded = client.post('/api/circuit/load', json=dict(circuit=dict(source='virtuoso', library=LIB, cell=CELL, testbench_cell=TB))).json()
    assert loaded['working_copy']['copy']['library'] == COPY                      # the page learns of the copy with the circuit
    readback = working_copy.native_cells.cell_dir(LIB, CELL) / 'testbench_readback.json'
    readback.write_text(json.dumps(dict(instances=[dict(name='V0', lib='analogLib', cell='vdc', params=dict(vdc='1.0'))])))

    def with_rows(raw):
        rows = vs.to_rows(SETUP)
        raw['measurements'], raw['targets'] = rows['measurements'], rows['targets']
    task = make_config(tmp_path, mutate=with_rows)
    config = task.model_dump(mode='json')
    read = client.post('/api/virtuoso/setup/read', json=dict(cell, profile_id='lab', config=config)).json()
    assert read['editor_differences'] == [] and read['fingerprint'] == vs.fingerprint(written_answer())
    config['targets'][0]['lower'] = 2e9
    read = client.post('/api/virtuoso/setup/read', json=dict(cell, profile_id='lab', config=config)).json()
    assert read['editor_differences'] == ["Spec on freq: the task says ('gt', '2000000000'), Virtuoso has ('gt', '1000000000')"]
    config['targets'][0]['lower'] = 1e9
    # The rows are written into the copy through the pair a task save and the agent's tool use (the route that did
    # this had no caller left once "Write to Virtuoso" went, 7.65, and was removed in the review of 2026-09-23).
    written = write(probe(tmp_path), vs.from_rows(task, variables=SETUP['variables'], bindings=SETUP['bindings']))
    assert written['matches'], written
    last = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()][-1]
    assert last['op'] == 'write_setup' and last['request']['setup']['analyses'] is None       # the copy's analyses are kept
    with pytest.raises(vs.SetupError, match=r'system\(\) is not'):
        write(probe(tmp_path), dict(SETUP, outputs=[dict(name='x', expression='system("y")')], specs=[]))
    assert client.post('/api/virtuoso/copy', json=cell).status_code == 422                   # a connection profile is required
