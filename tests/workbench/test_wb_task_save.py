"""Saved tasks (`profiles.save_task`, `task_files`, the /api/virtuoso/task/* routes): "Save task" updates the open task,
"Save as" makes another with a working copy of its own, and the task file says everything a task is. FAKE bridge
processes and the recorded real ring-oscillator export only - no Virtuoso, no simulation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gator_workbench import profiles, recipes, schema, task_files, tasks, virtuoso_setup as vs, working_copy
from helpers import bridge_is_importable, probe, workbench_app   # noqa: F401 - an imported fixture belongs to this module
from ring_cell_support import FIXTURE, ROWS, connection_file, read_cell
from fakes_virtuoso import CELL, COPY, copy_reader, fake_writer, LIB, MAESTRO_HEAD, maestro_netlister, SETUP, setup_writer, TB
from task_save_support import FREQUENCY_PROBE, FREQUENCY_SPEC, config, ready, save


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
    # the task window's facts (record 7.227), all from the task's own entry: its testbench, when it was saved, no baseline yet,
    # how many sizes it varies and results it measures
    assert listed['testbench'] == TB and listed['saved_utc'] == entry['saved_utc'] and listed['baseline_recorded_utc'] is None
    assert listed['variables'] == len(leaders) and listed['results'] == len(recipes.RING_METRICS) and listed['status'].startswith('unverified')
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='real:ring_osc'))
    assert runtime.provided_metrics == tuple(recipes.RING_METRICS) and not runtime.authorized
    config_, _, _ = tasks.generated_bridge_config('ring_osc')
    assert config_.library == COPY                                                                  # the real adapter opens the copy
    assert profiles.tasks_for_cell(LIB, CELL) == [dict(task_key='real:ring_osc', name='ring_osc', generated=True)]
    with pytest.raises(profiles.ProfileError, match='already has the task'):                        # a second FIRST save of the cell
        save(tmp_path, name='other', extras=dict(expected_frequency_hz=1.2e9))


def test_a_note_alone_keeps_the_recorded_baseline(tmp_path):
    """Review of 2026-10-03: editing only a row's note dropped the recorded baseline - a real simulation to record again."""
    ready(tmp_path)
    save(tmp_path, extras=dict(expected_frequency_hz=1.2e9))
    folder = profiles.profile_dir('ring_osc')
    (folder / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(osc_frequency_hz=1.209e9))))
    noted = [dict(r, notes='sized for 1.2 GHz') if r['variable_id'] == 'wn' else r for r in ROWS]
    again = save(tmp_path, cfg=config(rows=noted), task='ring_osc')
    assert again['changed'] == ['notes'] and again['baseline_kept']
    assert profiles.reference_metrics('ring_osc') == dict(osc_frequency_hz=1.209e9)
    assert task_files.what_changed(dict(probes=[dict(measurement_id='m', unit='Hz', notes='a')]),
                                   dict(probes=[dict(measurement_id='m', unit='kHz', notes='a')])) == {'probes'}


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


@pytest.mark.parametrize('model, corner, kept', [('/pdk/model.scs', 'ss', False), ('/pdk/other.scs', 'tt', False),
                                               ('/pdk/model.scs', 'tt', True)])
def test_a_saved_baseline_depends_on_the_model_file_and_corner(tmp_path, model, corner, kept):
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    analyses = {'tran': {'stop': '50n', 'errpreset': 'conservative'}}

    def saving(model_file, section, task=None):
        """Save the fixture task with a selected model file and matching Maestro section."""
        answer = dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[[model_file, section]], analyses=analyses,
                      variables={}, bindings=[], outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={})
        head = MAESTRO_HEAD.replace('/pdk/model.scs', model_file).replace('section=tt', f'section={section}')
        return save(tmp_path, name='ring_models', task=task, cfg=cfg,
                    extras=dict(analyses=analyses, model_files=answer['model_files']),
                    commands=dict(setup=setup_writer(tmp_path, answer), deck=maestro_netlister(tmp_path, head=head)))

    saving('/pdk/model.scs', 'tt')
    folder = profiles.profile_dir('ring_models')
    reference = dict(origin='real', metrics=dict(freq=1.2e9, vmax=1.0))
    (folder / profiles.FILES['reference']).write_text(json.dumps(reference))
    again = saving(model, corner, task='ring_models')
    assert profiles.task_file('ring_models')['maestro']['model_files'] == [[model, corner]]
    deck = json.loads((folder / profiles.FILES['maestro_deck']).read_text())
    assert f'include "{model}" section={corner}' in deck['head']
    assert again['changed'] == ([] if kept else ['model_files'])
    assert again['baseline_kept'] is kept
    assert profiles.reference_metrics('ring_models') == (reference['metrics'] if kept else None)
    assert json.loads((folder / 'history' / 'r1' / profiles.FILES['reference']).read_text()) == reference


def test_a_task_starts_its_oscillator_with_initial_conditions(tmp_path):
    """A circuit that does not start by itself gets a start voltage per net: they go into the copy with the rest of the
    setup, into the task file, and changing them drops the recorded baseline - what is simulated changed."""
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    conditions = {'N1': '0', 'N2': '0.9', 'OUT': '0.9'}

    def answer(ic):
        """Build a Maestro setup response with optional initial conditions and their file."""
        return dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']],
                    analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}, variables={}, bindings=[],
                    outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={}, initial_conditions=ic,
                    ic_file='/home/u/.gator/ic/GPDK045_RINGOSC_GATOR__tb__GATOR.scs' if ic else None)

    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    extras = dict(analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}, initial_conditions=conditions)
    made = save(tmp_path, name='ring_ic', cfg=cfg, extras=extras,
                commands=dict(setup=setup_writer(tmp_path, answer(conditions)), deck=maestro_netlister(tmp_path)))
    assert made['runnable'] and made['maestro_matches']
    [call] = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()]
    assert call['request']['setup']['initial_conditions'] == conditions            # written with the setup, not by hand
    assert profiles.task_file('ring_ic')['maestro']['initial_conditions'] == conditions
    (profiles.profile_dir('ring_ic') / 'reference_measurements.json').write_text(json.dumps(dict(origin='real', metrics=dict(freq=1.2e9))))
    other = dict(conditions, OUT='0.8')
    again = save(tmp_path, name='ring_ic', task='ring_ic', cfg=cfg, extras=dict(extras, initial_conditions=other),
                 commands=dict(setup=setup_writer(tmp_path, answer(other)), deck=maestro_netlister(tmp_path)))
    assert again['changed'] == ['initial_conditions'] and not again['baseline_kept']
    assert profiles.task_file('ring_ic')['maestro']['initial_conditions'] == other


def test_saving_the_task_again_keeps_its_initial_conditions(tmp_path):
    """The sequence that lost them live on 2026-09-22 (23:08): save with conditions, then save the OPEN task again with
    nothing said about them. A setup that does not mention a part means "leave it as the copy has it" - it must not read
    as "this test has none", and the ic file must stay registered even when the model files are stated."""
    ready(tmp_path)
    rows = vs.to_rows(SETUP)
    conditions = {'N1': '0', 'OUT': '0.9'}

    def answer(ic):
        """Build a saved-task setup response carrying the tested initial conditions."""
        return dict(exists=True, tests=['GATOR'], test='GATOR', model_files=[['/pdk/model.scs', 'tt']],
                    analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}, variables={}, bindings=[],
                    outputs=SETUP['outputs'], specs=SETUP['specs'], raw_specs={}, initial_conditions=ic,
                    ic_file='/home/u/.gator/ic/x.scs' if ic else None)

    cfg = config(probes=rows['measurements'], specs=rows['targets'])
    extras = dict(analyses={'tran': {'stop': '50n', 'errpreset': 'conservative'}}, initial_conditions=conditions)
    save(tmp_path, name='ring_keep', cfg=cfg, extras=extras,
         commands=dict(setup=setup_writer(tmp_path, answer(conditions)), deck=maestro_netlister(tmp_path)))
    again = save(tmp_path, name='ring_keep', task='ring_keep', cfg=cfg,                       # no extras at all
                 commands=dict(setup=setup_writer(tmp_path, answer(conditions)), deck=maestro_netlister(tmp_path)))
    assert again['revision'] == 2 and again['maestro_matches'] and 'initial_conditions' not in (again['changed'] or [])
    assert profiles.task_file('ring_keep')['maestro']['initial_conditions'] == conditions
    second = [json.loads(line) for line in (tmp_path / 'setup_calls.jsonl').read_text().splitlines()][-1]
    assert second['request']['setup']['initial_conditions'] in (None, conditions)      # kept or stated again - never {}


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
        """Build a Maestro setup response with the copy's current transient stop time."""
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
    assert profiles.measurement_kind(config(probes=[FREQUENCY_PROBE], specs=[])) == 'ring_oscillator'
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
    client = TestClient(workbench_app(tmp_path, monitor=probe(tmp_path), auto_check_on_start=True))
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
    real = profiles.save_task

    def with_fakes(*args, **kwargs):
        """Read the task draft through the recorded working-copy fixture."""
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
