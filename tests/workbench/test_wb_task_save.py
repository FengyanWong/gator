"""Saved tasks (`profiles.save_task`, `task_files`, the /api/virtuoso/task/* routes): "Save task" updates the open task,
"Save as" makes another with a working copy of its own, and the task file says everything a task is. FAKE bridge
processes and the recorded real ring-oscillator export only - no Virtuoso, no simulation."""
import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

from gator_workbench import profiles, schema, task_files, tasks, virtuoso_setup as vs, working_copy
from gator_workbench.api import create_app
from test_wb_api import probe
from test_wb_profiles import FIXTURE, ROWS, connection_file, read_cell, row
from test_wb_virtuoso_setup import SETUP, setup_writer
from test_wb_working_copy import CELL, COPY, LIB, TB, fake_writer

FREQUENCY_PROBE = dict(measurement_id='m_osc_frequency_hz', analysis='tran', result_source='backend_profile', source_name='osc_frequency_hz', unit='Hz')
FREQUENCY_SPEC = dict(metric_id='osc_frequency_hz', equation='m_osc_frequency_hz', unit='Hz', constraint='>=', lower=1.1e9, normalization_scale=1e9)


@pytest.fixture(autouse=True)
def _bridge_is_importable(monkeypatch):
    monkeypatch.setattr(tasks, 'bridge_importable', lambda: True)


def copy_reader(tmp_path):
    """Stands in for `bridge_read` reading a working copy INTO the workbench: the recorded export, with the names
    Virtuoso gives the copy (its library in the comments, renamed cells for a "Save as" copy)."""
    script = tmp_path / 'copy_reader.py'
    script.write_text(f'''
import json, re, shutil, sys
from pathlib import Path
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
out = Path(args['--output']); out.mkdir(parents=True)
text = (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: ' + args['--library'])
text = re.sub(r'\\btb_ring_osc_3stage\\b', args['--testbench'], text)
text = re.sub(r'(?<![A-Za-z0-9_])ring_osc_3stage(?![A-Za-z0-9_])', args['--cell'], text)
(out / 'netlist.scs').write_text(text)
shutil.copy(Path({str(FIXTURE)!r}) / 'core_readback.json', out / 'core_readback.json')
bench = json.loads((Path({str(FIXTURE)!r}) / 'testbench_readback.json').read_text())
for item in bench['instances']:                      # the copied testbench points at the copied cell
    if item.get('cell') == 'ring_osc_3stage':
        item.update(lib=args['--library'], cell=args['--cell'])
(out / 'testbench_readback.json').write_text(json.dumps(bench))
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench_cell=args.get('--testbench'), technology_library='gpdk045')))
''')
    return [sys.executable, str(script)]


def task_copier(tmp_path):
    """Stands in for `bridge_setup make_copy` making a "Save as" copy with renamed cells inside the copy library."""
    script = tmp_path / 'task_copier.py'
    script.write_text(f'''
import json, re, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv) and not argv[i + 1].startswith('--')}}
rename = json.loads(args['--rename'])
with open({str(tmp_path / 'copier_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(args) + '\\n')
out = Path(args['--output'])
text = (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: {COPY}')
for old, new in sorted(rename.items(), key=lambda kv: -len(kv[0])):
    text = re.sub(r'(?<![A-Za-z0-9_])' + re.escape(old) + r'(?![A-Za-z0-9_])', new, text)
(out / 'progress.json').write_text(json.dumps(dict(created_library=False, copied=[v + '/schematic' for v in rename.values()])))
(out / 'netlist.scs').write_text(text)
same = 'a' * 64
print(json.dumps(dict(library=args['--library'], cell=args['--cell'], testbench=args['--testbench'], copy_library=args['--copy-library'],
                      copy_path='/home/minlei/{COPY}', copy_cell=rename[args['--cell']], copy_testbench=rename[args['--testbench']],
                      rename=rename, technology_library='gpdk045', copy_technology_library='gpdk045', working_dir='/home/minlei',
                      created_library=False, cds_lib='/home/minlei/cds.lib', cells=[], copied=[dict(cell=v, view='schematic') for v in rename.values()],
                      remastered={{}}, originals_before={{k: same for k in rename}}, originals_after={{k: same for k in rename}})))
''')
    return [sys.executable, str(script)]


MAESTRO_HEAD = ('// Generated for: spectre\nsimulator lang=spectre\nglobal 0\nparameters temperature=27\n'
                'include "/pdk/model.scs" section=tt\n\n')
MAESTRO_TAIL = ('\nsimulatorOptions options psfversion="1.4.0" reltol=1e-3 temp=27\n'
                'tran tran stop=50n errpreset=conservative write="spectre.ic" annotate=status\n'
                'finalTimeOP info what=oppoint where=rawfile\nsaveOptions options save=allpub\n')


def maestro_netlister(tmp_path, circuit=None):
    """Stands in for `bridge_setup maestro_netlist`: Maestro's netlist folder of the copy's test - input.scs = a head, the
    circuit (the recorded export with the copy's names, as the copy reader gives it), a tail - plus name maps in the
    format the real netlister writes (amap/). `circuit` replaces the circuit part (a netlist that differs)."""
    script = tmp_path / 'maestro_netlister.py'
    script.write_text(f'''
import json, re, sys
from pathlib import Path
argv = sys.argv[1:]
args = {{a: argv[i + 1] for i, a in enumerate(argv) if a.startswith('--') and i + 1 < len(argv)}}
with open({str(tmp_path / 'netlister_calls.jsonl')!r}, 'a') as f:
    f.write(json.dumps(dict(op=args['--op'], copy=args['--copy-library'], testbench=args['--testbench'])) + '\\n')
text = {circuit!r} or (Path({str(FIXTURE)!r}) / 'netlist.scs').read_text().replace('// Library name: {LIB}', '// Library name: ' + args['--copy-library'])
text = re.sub(r'\\btb_ring_osc_3stage\\b', args['--testbench'], text)
text = re.sub(r'(?<![A-Za-z0-9_])ring_osc_3stage(?![A-Za-z0-9_])', args['--cell'], text)
folder = Path(args['--output']) / 'maestro_netlist' / 'netlist'
(folder / 'amap').mkdir(parents=True)
(folder / 'netlist').write_text(text)
(folder / 'input.scs').write_text({MAESTRO_HEAD!r} + text + {MAESTRO_TAIL!r})
maps = {{'top_level_map.inst': [('__NEXT_FILE__', args['--testbench'])],
        '__simulator_information__': [('__artInstanceTerminalDelimiter__', ':'), ('__artHierarchyDelimiter__', '.')],
        args['--testbench'] + '.inst': [('V0n', 'analogLib_vdc_spectre'), ('XU1n', args['--cell'])],
        args['--testbench'] + '.net': [('gnd!v', '0v')],
        'analogLib_vdc_spectre.inst': [('PLUSv', ':pv'), ('MINUSv', '(FUNCTION minus(root("PLUS")))v')],
        args['--cell'] + '.inst': [('MN1n MN2n MN3n', 'gpdk045_nmos1v_spectre'), ('OUTv', ':1v')],
        'gpdk045_nmos1v_spectre.inst': [('Dv', ':dv'), ('Gv', ':gv')]}}
for name, pairs in maps.items():
    (folder / 'amap' / name).write_text('HEADER\\n"PSFversion" "1.00"\\n' + ''.join('"%s" "%s"\\n' % (k, v.replace('"', '\\\\"')) for k, v in pairs))
print(json.dumps(dict(test='GATOR', remote='/tmp/gator_maestro_netlist/x', folder=str(folder))))
''')
    return [sys.executable, str(script)]


def config(probes=(FREQUENCY_PROBE,), specs=(FREQUENCY_SPEC,), rows=ROWS):
    return schema.WorkbenchConfig.model_validate(dict(
        circuit=dict(source='virtuoso', library=LIB, cell=CELL, testbench_cell=TB, circuit_class='vco'),
        parameters=list(rows), measurements=list(probes), targets=list(specs), run=dict(max_evaluations=5)))


def ready(tmp_path):
    """The user's ring oscillator read into the workbench through its testbench, with a verified working copy."""
    connection_file()
    read_cell(tmp_path)
    assert working_copy.make(probe(tmp_path), 'lab', LIB, CELL, command=fake_writer(tmp_path))['verified']


def save(tmp_path, name='ring_osc', cfg=None, **kwargs):
    commands = dict(read=copy_reader(tmp_path), copy=task_copier(tmp_path), **kwargs.pop('commands', {}))
    return profiles.save_task(probe(tmp_path), 'lab', name, cfg or config(), library=LIB, cell=CELL, commands=commands, **kwargs)


def test_the_first_save_takes_the_cell_s_copy_and_registers_a_task_that_runs_on_the_copy(tmp_path):
    ready(tmp_path)
    with pytest.raises(profiles.NeedsFrequency, match='rough expected oscillation frequency'):
        save(tmp_path)
    assert profiles.list_profiles() == {} and 'claimed_by' not in working_copy.load(LIB, CELL)      # a refusal leaves nothing
    made = save(tmp_path, extras=dict(expected_frequency_hz=1.2e9, notes='first try'))
    assert made['task_key'] == 'real:ring_osc' and made['revision'] == 1 and made['runnable'] and made['created']
    assert made['measurement'] == dict(kind='ring_oscillator', expected_frequency_hz=1.2e9)
    assert {k: made['copy'][k] for k in ('library', 'cell', 'testbench')} == dict(library=COPY, cell=CELL, testbench=TB)
    assert made['original']['library'] == LIB
    entry = profiles.list_profiles()['ring_osc']
    assert entry['library'] == COPY and entry['recipe'] == 'ring_oscillator' and entry['revision'] == 1   # runs write into the COPY
    assert working_copy.load(LIB, CELL)['claimed_by'] == 'ring_osc'
    data = profiles.task_file('ring_osc')
    assert data['format'] == task_files.FORMAT and data['notes'] == 'first try' and '_help' in data
    assert [p['measurement_id'] for p in data['probes']] == ['m_osc_frequency_hz'] and data['specs'][0]['lower'] == 1.1e9
    leaders = {r['variable_id']: (r['lower'], r['upper'], r['step']) for r in data['parameters'] if not r.get('binding_group')}
    assert leaders == dict(wn=(0.6, 1.6, 0.005), wp=(1.205, 3.2, 0.005))                            # snapped onto the grid, as registered
    starter = tasks.real_starter_config('real:ring_osc')                                           # opening the task brings ITS rows
    assert starter['parameters'] == data['parameters'] and starter['measurements'] == data['probes'] and starter['targets'] == data['specs']
    listed = next(t for t in tasks.list_tasks() if t['task_key'] == 'real:ring_osc')
    assert listed['available'] and listed['generated']
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='real:ring_osc'))
    assert runtime.provided_metrics == tuple(profiles.recipes.RING_METRICS) and not runtime.authorized
    config_, _, _ = tasks.generated_bridge_config('ring_osc')
    assert config_.library == COPY                                                                  # the real adapter opens the copy
    assert profiles.tasks_for_cell(LIB, CELL) == [dict(task_key='real:ring_osc', name='ring_osc', generated=True)]
    with pytest.raises(profiles.ProfileError, match='already has the task'):                        # a second FIRST save of the cell
        save(tmp_path, name='other', extras=dict(expected_frequency_hz=1.2e9))


def test_save_task_updates_the_open_task_and_keeps_the_baseline_only_while_the_measurement_stands(tmp_path):
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    folder = profiles.profile_dir('ring_osc')
    (folder / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.209e9))))
    tighter = dict(FREQUENCY_SPEC, lower=1.15e9)
    again = save(tmp_path, cfg=config(specs=[tighter]), task='ring_osc')
    assert again['revision'] == 2 and not again['created'] and again['changed'] == ['specs'] and again['baseline_kept']
    assert profiles.reference_metrics('ring_osc') == dict(osc_frequency_hz=1.209e9)
    assert json.loads((folder / 'history' / 'r1' / 'task.json').read_text())['revision'] == 1
    assert profiles.task_file('ring_osc')['specs'][0]['lower'] == 1.15e9
    assert profiles.task_file('ring_osc')['measurement']['expected_frequency_hz'] == 1.2e9           # kept from revision 1
    wider = [dict(r, upper=1.8) if r['variable_id'] == 'wn' else r for r in ROWS]
    third = save(tmp_path, cfg=config(specs=[tighter], rows=wider), task='ring_osc')
    assert third['revision'] == 3 and 'parameters' in third['changed'] and not third['baseline_kept']
    assert profiles.reference_metrics('ring_osc') is None                                           # a moved reference is not a reference
    assert (folder / 'history' / 'r2' / 'reference_measurements.json').is_file()                     # nothing erased
    assert len(list((folder.parent / profiles.TRASH).glob('ring_osc.r*'))) == 2
    with pytest.raises(profiles.ProfileError, match='keeps the task name'):
        save(tmp_path, name='renamed', task='ring_osc')
    with pytest.raises(profiles.ProfileError, match='Unknown task'):
        save(tmp_path, task='nope')


def test_save_as_makes_another_task_with_a_working_copy_of_its_own(tmp_path):
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    made = save(tmp_path, name='ring_fast', task='ring_osc', as_new=True)
    assert made['task_key'] == 'real:ring_fast' and made['revision'] == 1 and made['created']
    assert made['copy'] == dict(library=COPY, cell=f'{CELL}_ring_fast', testbench=f'{TB}_ring_fast')
    [call] = [json.loads(line) for line in (tmp_path / 'copier_calls.jsonl').read_text().splitlines()]
    assert json.loads(call['--rename']) == {CELL: f'{CELL}_ring_fast', TB: f'{TB}_ring_fast'} and call['--copy-library'] == COPY
    assert profiles.list_profiles()['ring_fast']['core_cell'] == f'{CELL}_ring_fast'
    assert profiles.task_file('ring_fast')['measurement']['expected_frequency_hz'] == 1.2e9           # carried over from the open task
    assert profiles.list_profiles()['ring_osc']['revision'] == 1                                   # the open task is unchanged
    assert {t['task_key'] for t in profiles.tasks_for_cell(LIB, CELL)} == {'real:ring_osc', 'real:ring_fast'}
    with pytest.raises(profiles.ProfileError, match='already exists'):
        save(tmp_path, name='ring_fast', task='ring_osc', as_new=True)


def test_a_maestro_measured_task_writes_its_setup_and_netlists_its_test_once(tmp_path):
    ready(tmp_path)
    readback = working_copy.native_cells.cell_dir(LIB, CELL) / 'testbench_readback.json'
    data = json.loads(readback.read_text())
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    made = save(tmp_path, name='ring_maestro', cfg=cfg, extras=dict(analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}),
                commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path)))
    assert made['measurement'] == dict(kind='maestro') and made['runnable'] and made['maestro_matches']
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['op'] == 'write_setup' and call['copy'] == COPY and call['request']['setup']['outputs'] == SETUP['outputs']
    assert call['request']['setup']['analyses'] == {'tran': {'stop': '5e-08', 'errpreset': 'conservative'}}
    [netlisted] = [json.loads(line) for line in (tmp_path / 'netlister_calls.jsonl').read_text().splitlines()]
    assert netlisted == dict(op='maestro_netlist', copy=COPY, testbench=TB)                          # once, of the copy's test
    entry = profiles.list_profiles()['ring_maestro']
    assert entry['recipe'] == 'maestro' and entry['provided_metrics'] == ['freq', 'vmax'] and entry['runnable']
    assert [(e['metric_id'], e['unit']) for e in entry['spec_registry']] == [('freq', 'Hz'), ('vmax', 'V')]    # exactly its outputs
    deck = json.loads((Path(entry['directory']) / profiles.FILES['maestro_deck']).read_text())
    assert deck['head'].rstrip('\n') == MAESTRO_HEAD.rstrip('\n') and deck['tail'].lstrip('\n').startswith('simulatorOptions') and deck['analyses'] == ['tran']
    assert [(o['name'], o['spectre_expression'], o['analysis']) for o in deck['outputs']] == [
        ('freq', 'frequency(VT("OUT"))', 'tran'), ('vmax', 'ymax(VT("OUT"))', 'tran')]                # Maestro's names -> Spectre's
    saved = profiles.task_file('ring_maestro')
    assert saved['maestro']['outputs'] == [dict(name='freq', expression='frequency(VT("/OUT"))'), dict(name='vmax', expression='ymax(VT("/OUT"))')]
    listed = next(t for t in tasks.list_tasks() if t['task_key'] == 'real:ring_maestro')
    assert profiles.MAESTRO_NOT_RUNNABLE != listed.get('blocker')
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='real:ring_maestro'))
    assert runtime.provided_metrics == ('freq', 'vmax') and 'Measured by Maestro' in runtime.notes[0]
    with pytest.raises(tasks.TaskBlocked, match='authoriz'):                                     # runnable now: only the budget question is left
        runtime.env_factory_builder(None, tmp_path, None)
    assert data                                                                                     # the readback fixture was there


def test_a_maestro_netlist_that_does_not_fit_saves_nothing(tmp_path):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                  variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    with pytest.raises(profiles.ProfileError, match='differently from its schematic export'):
        save(tmp_path, name='ring_maestro', cfg=cfg, extras=dict(analyses={'tran': {'stop': '50n'}}),
             commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path, circuit='V9 (A 0) vsource dc=1\n')))
    unknown = [dict(m, signal='frequency(VT("/XQ/OUT"))') if m['source_name'] == 'freq' else m for m in rows['measurements']]
    with pytest.raises(vs.SetupError, match='XQ is not an instance'):
        save(tmp_path, name='ring_maestro', cfg=config(probes=unknown, specs=rows['targets']), extras=dict(analyses={'tran': {'stop': '50n'}}),
             commands=dict(setup=setup_writer(tmp_path, dict(answer, outputs=[dict(SETUP['outputs'][0], expression='frequency(VT("/XQ/OUT"))')] + SETUP['outputs'][1:])),
                           deck=maestro_netlister(tmp_path)))
    assert profiles.list_profiles() == {} and 'claimed_by' not in working_copy.load(LIB, CELL)


def test_save_task_keeps_what_was_written_into_the_copy_after_the_last_save(tmp_path):
    """An approved agent setup (or "Write to Virtuoso") writes into the open task's copy after its last save: the next Save
    task - and a Save as from it - carries that newer setup on, not the one saved with the task."""
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    def answer(stop):
        return dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': stop}},
                    variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
    save(tmp_path, name='ring_maestro', cfg=cfg, extras=dict(analyses={'tran': {'stop': '50n'}}), commands=dict(setup=setup_writer(tmp_path, answer('50n')), deck=maestro_netlister(tmp_path)))
    target = profiles.list_profiles()['ring_maestro']['copy_target']
    assert working_copy.write_setup_on(probe(tmp_path), 'lab', target, vs.from_rows(cfg, analyses={'tran': {'stop': '40n'}}),
                                       command=setup_writer(tmp_path, answer('40n')))['matches']          # what the agent's apply does
    made = save(tmp_path, name='ring_maestro', task='ring_maestro', cfg=cfg, commands=dict(setup=setup_writer(tmp_path, answer('40n')), deck=maestro_netlister(tmp_path)))
    assert made['revision'] == 2
    save(tmp_path, name='ring_maestro_b', task='ring_maestro', as_new=True, cfg=cfg, commands=dict(setup=setup_writer(tmp_path, answer('40n')), deck=maestro_netlister(tmp_path)))
    calls = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert [c['request']['setup']['analyses']['tran']['stop'] for c in calls] == ['5e-08', '4e-08', '4e-08', '4e-08']
    assert calls[-1]['testbench'] == f'{TB}_ring_maestro_b'
    assert profiles.task_file('ring_maestro_b')['maestro']['analyses'] == profiles.task_file('ring_maestro')['maestro']['analyses']


def test_save_as_from_a_task_made_before_working_copies_is_refused_in_words(tmp_path):
    connection_file()
    read_cell(tmp_path)
    profiles.create_profile('ring_old', config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    with pytest.raises(profiles.ProfileError, match='made before tasks had working copies'):
        save(tmp_path, name='ring_new', task='ring_old', as_new=True)
    assert set(profiles.list_profiles()) == {'ring_old'}


def test_a_setup_that_reads_back_differently_saves_nothing(tmp_path):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    drifted = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']], analyses={'tran': {'stop': '50n'}},
                   variables={}, bindings=[], outputs=SETUP['outputs'][:1], specs=[], raw_specs={})
    with pytest.raises(profiles.ProfileError, match='reads back differently'):
        save(tmp_path, name='ring_maestro', cfg=config(probes=rows['measurements'], specs=rows['targets']),
             extras=dict(analyses={'tran': {'stop': '50n'}}), commands=dict(setup=setup_writer(tmp_path, drifted)))
    assert profiles.list_profiles() == {} and 'claimed_by' not in working_copy.load(LIB, CELL)


def test_what_a_task_measures_is_read_from_its_probes(tmp_path):
    ready(tmp_path)
    ade = vs.to_rows(SETUP)['measurements'][0]
    gain = dict(measurement_id='m_gain', analysis='ac', result_source='backend_profile', source_name='gain_db_at_start', unit='dB')
    power = dict(measurement_id='m_power', analysis='tran', result_source='backend_profile', source_name='supply_power_w', unit='W')
    derived = dict(measurement_id='m_twice', analysis='tran', result_source='expression', expression='m_osc_frequency_hz * 2', unit='Hz')
    assert profiles.measurement_kind(config(probes=[FREQUENCY_PROBE, derived], specs=[])) == 'ring_oscillator'
    assert profiles.measurement_kind(config(probes=[gain], specs=[])) == 'opamp_ac'
    assert profiles.measurement_kind(config(probes=[ade], specs=[])) == 'maestro'
    for probes, message in (([], 'Probes is empty'), ([ade, FREQUENCY_PROBE], 'mix Maestro outputs'), ([power], 'fit both circuit types'),
                            ([FREQUENCY_PROBE, gain], 'no circuit type gives together')):
        with pytest.raises(profiles.ProfileError, match=message):
            profiles.measurement_kind(config(probes=probes, specs=[]))


def test_deleting_the_task_frees_the_cell_s_copy_for_a_new_one(tmp_path):
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    gone = profiles.delete_profile('ring_osc')
    assert gone['deleted'] == 'real:ring_osc' and 'claimed_by' not in working_copy.load(LIB, CELL)
    # The page puts the answer into its Circuit source: the user's own cell and testbench, never the working copy.
    assert (gone['library'], gone['cell'], gone['testbench_cell']) == (LIB, CELL, TB)
    assert save(tmp_path, name='ring_osc2', extras=dict(expected_frequency_hz=1.2e9))['revision'] == 1


def test_the_task_file_routes_show_the_draft_and_check_hand_edits(tmp_path):
    ready(tmp_path)
    client = TestClient(create_app(extra_output_roots=[str(tmp_path)], serve_frontend=False, monitor=probe(tmp_path)))
    body = dict(config=config().model_dump(mode='json'), library=LIB, cell=CELL, extras=dict(expected_frequency_hz=1.2e9))
    answer = client.post('/api/virtuoso/task/file', json=body).json()
    data = json.loads(answer['text'])
    assert '_help' in data and data['copy']['library'] == COPY and data['cell']['library'] == LIB and not answer['saved']
    assert data['measurement'] == dict(expected_frequency_hz=1.2e9) and data['probes'][0]['measurement_id'] == 'm_osc_frequency_hz'
    data['specs'][0]['lower'] = 1.3e9
    data['maestro']['analyses'] = {'tran': {'stop': '40n'}}
    data['notes'] = 'edited by hand'
    checked = client.post('/api/virtuoso/task/file/check', json=dict(text=json.dumps(data))).json()
    assert checked['ok'] and checked['rows']['targets'][0]['lower'] == 1.3e9
    assert checked['extras']['analyses'] == {'tran': {'stop': '40n'}} and checked['extras']['notes'] == 'edited by hand'
    data['probes'][0]['analysis'] = 'sometimes'
    data['maestro']['bindings'] = [dict(cell=TB, instance='V0')]
    bad = client.post('/api/virtuoso/task/file/check', json=dict(text=json.dumps(data))).json()
    assert not bad['ok'] and any(p.startswith('probes[0] analysis') for p in bad['problems']) and any('bindings' in p for p in bad['problems'])
    assert client.post('/api/virtuoso/task/file/check', json=dict(text='{"a": ')).json()['problems'][0].startswith('Not valid JSON')
    # Save task through the route: a refusal for the missing frequency is its own code, so the page can ask for it.
    import functools
    real = profiles.save_task

    def with_fakes(*args, **kwargs):
        return real(*args, **dict(kwargs, commands=dict(read=copy_reader(tmp_path))))
    profiles.save_task = with_fakes
    try:
        refused = client.post('/api/virtuoso/task/save', json=dict(profile_id='lab', name='ring_osc', config=config().model_dump(mode='json'),
                                                                    library=LIB, cell=CELL))
        assert refused.status_code == 409 and refused.json()['detail']['code'] == 'needs_expected_frequency'
        saved = client.post('/api/virtuoso/task/save', json=dict(profile_id='lab', name='ring_osc', config=config().model_dump(mode='json'),
                                                                  library=LIB, cell=CELL, extras=dict(expected_frequency_hz=1.2e9)))
        assert saved.status_code == 200 and saved.json()['task_key'] == 'real:ring_osc'
    finally:
        profiles.save_task = real
    reopened = json.loads(client.post('/api/virtuoso/task/file', json=dict(config=config().model_dump(mode='json'), task='ring_osc')).json()['text'])
    assert reopened['revision'] == 1 and reopened['copy']['library'] == COPY and reopened['measurement']['kind'] == 'ring_oscillator'
