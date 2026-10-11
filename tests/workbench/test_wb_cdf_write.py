"""Real runs that write any value the PDK's property form lets a user type (cdf_facts -> cdf_rules -> cdf_write).

The recorded REAL ring oscillator (fixtures/ring_osc: export, readbacks, and core_cdf.json = what the form of each of its
instances lets a user type, read-only). The Virtuoso side is a fake that runs the writer's SKILL the way the form would:
the fields it sets, then their callbacks - emulated here (a test model, not the PDK's: a transistor keeps total width =
fingers x finger width and folds when told to, a MIM capacitor side is clamped). No Virtuoso, no simulation."""
from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from analog_optimizer.backends.virtuoso_bridge import VirtuosoBridgeBackend
from gator_workbench import cdf_facts, cdf_write, compile as comp, paths, profiles, schema, tasks
from gator_workbench.generic_profile import GenericMosWidthProfile
from helpers import bridge_is_importable, probe   # noqa: F401 - an imported fixture belongs to this module

from ring_cell_support import CIRCUIT, FIXTURE   # the same cell as the profile tests'
from cdf_write_support import config, make, read_cell, row, stage_rows
from analog_optimizer.parameters.actions import ActionMapper
from fakes_virtuoso import FakeVirtuoso, backend_of, num, wpe


# ------------------------------------------------------------------------------------------ what the form lets you type
def test_the_form_rules_are_read_with_the_cell(tmp_path):
    meta = read_cell(tmp_path)
    assert meta['form_rules'] == dict(read=True, instances=9, modified_after=False)
    facts = json.loads((Path(meta['directory']) / cdf_facts.FILE).read_text())
    assert facts['opened_mode'] == 'a' and facts['modified_after'] is False     # the cell was open for edit; nothing changed
    assert {n: i['cell'] for n, i in facts['instances'].items()} == {**{f'MN{i}': 'nmos1v' for i in (1, 2, 3)},
                                                                     **{f'MP{i}': 'pmos1v' for i in (1, 2, 3)},
                                                                     **{f'C{i}': 'mimcap' for i in (1, 2, 3)}}
    mos = cdf_facts.sources(facts, 'XU1', 'XU1/MN1')
    assert {k: mos[k]['cdf'] for k in ('w', 'l', 'nf', 'm', 'as')} == {'w': 'w', 'l': 'l', 'nf': 'fingers', 'm': 'm', 'as': 'as'}
    assert mos['w']['on'] == 'self'                                             # netlist w = simW = iPar("w"): the user types w
    assert cdf_facts.editable(facts, 'MN1', mos['w']) is None                  # decided by the open form: trusted
    assert 'greys it out' in cdf_facts.editable(facts, 'MN1', mos['as'])       # areas: computed unless editAreaPerim
    cap = cdf_facts.sources(facts, 'XU1', 'XU1/C1')
    assert facts['rules']['C1']['w'] == dict(editable='yes') and facts['rules']['C1']['c'] == dict(editable='no')
    assert cdf_facts.editable(facts, 'C1', cap['w']) is None and cap['w']['callback'] == "gpdk045_capCB('w)"
    assert cdf_facts.form_of(facts, 'mimcap') == dict(init='PasCdfFormInit', done=None)
    assert cdf_facts.form_of(facts, 'nmos1v') == dict(init='PasCdfFormInit', done='PasCdfDone')


def test_an_import_without_the_form_rules_keeps_the_width_writer_and_says_why(tmp_path):
    read_cell(tmp_path, files=('netlist.scs', 'core_readback.json', 'testbench_readback.json'))
    with pytest.raises(profiles.ProfileError, match='only change transistor widths.*Read the cell again'):
        profiles.create_profile('ring_try', config(stage_rows('l', 'ln', 0.045, 0.1)), recipe='ring_oscillator',
                                expected_frequency_hz=1.2e9)


# ------------------------------------------------------------------------------------------ Save task: rows -> rules
def test_save_takes_the_form_writer_for_lengths_capacitors_and_counts(tmp_path):
    made = make(tmp_path)
    assert made['writer'] == 'form'
    leaders = {r['variable_id']: (r['lower'], r['upper'], r['step'], r['value_type']) for r in made['parameters'] if not r['binding_group']}
    assert leaders == dict(wn=(0.6, 1.6, 0.005, 'continuous'), ln=(0.045, 0.1, 0.005, 'continuous'),
                           wc=(2.0, 5.6, 0.005, 'continuous'), mc=(1.0, 4.0, 1.0, 'integer'))
    rules = json.loads((Path(made['directory']) / 'rules.json').read_text())
    assert rules['format'] == 'gator-profile-rules-2' and rules['mos_instances'] == ['MP3', 'MP2', 'MP1', 'MN3', 'MN2', 'MN1']
    writes = {(w['device'], w['parameter']): w for w in rules['writes']}
    assert set(writes) == {(f'XU1/{n}', p) for n in ('MN1', 'MN2', 'MN3') for p in ('w', 'l')} | {
        (f'XU1/C{i}', 'w') for i in (1, 2, 3)} | {('XU1/C1', 'm')}
    assert writes['XU1/C1', 'w']['rule'] == 'cdfgData->calcParam->value!="width"'
    assert writes['XU1/MN1', 'w']['rule'] == "gpdk045_mosEditable( 'w )" and writes['XU1/MN1', 'w']['callback'] == "gpdk045_mosCB( 'w )"
    assert writes['XU1/C1', 'm']['integer'] and writes['XU1/C1', 'm']['step'] == 1.0
    held = {(h['instance'], h['cdf']): h['value'] for h in rules['held']}
    assert held[('MN1', 'fingers')] == 1.0 and held[('MN1', 'm')] == 1.0 and held[('C2', 'm')] == 2.0
    assert held[('C1', 'l')] == pytest.approx(4.49e-6) and ('C1', 'm') not in held and ('MN1', 'l') not in held
    assert 'pasUpdateParamList' in rules['cells']['nmos1v']['internal'] and 'calcParam' in rules['cells']['mimcap']['modes']

    profile = profiles.load_profile('ring_cdf')                                   # every check ran on the recorded files
    assert type(profile).__name__ == 'CdfRingOscillatorProfile' and profile.written_instances == ('C1', 'C2', 'C3', 'MN1', 'MN2', 'MN3')
    assert profile.fixed_instances == ('MP1', 'MP2', 'MP3') and profile.mos_names == tuple(rules['mos_instances'])
    moved = profile.assignments(dict(wn=1.2e-6, ln=6e-8, wc=3e-6, mc=3))
    assert moved['XU1/MN3', 'l'] == pytest.approx(6e-8) and moved['XU1/C1', 'm'] == 3
    for bad in ({('XU1/C1', 'm'): 2.5}, {('XU1/MN1', 'l'): 6.1e-8}, {('XU1/C1', 'w'): 5.7e-6}):
        with pytest.raises(ValueError):
            profile.validate_assignment({**moved, **bad})
    import pickle
    assert pickle.loads(pickle.dumps(profile)).assignments() == profile.assignments()     # the helper process gets it pickled
    assert cdf_write.backend_class(profile) is cdf_write.CdfBridgeBackend


def test_single_finger_widths_keep_the_verified_width_writer(tmp_path):
    made = make(tmp_path, rows=stage_rows('w', 'wn', 0.6, 1.6))
    assert made['writer'] == 'widths'
    profile = profiles.load_profile('ring_cdf')
    assert isinstance(profile, GenericMosWidthProfile) and not isinstance(profile, cdf_write.CdfWritableProfile)
    adapter = cdf_write.backend_class(profile)             # the verified adapter itself, under its cell's lock (record 7.311)
    assert adapter.__mro__[:3] == (adapter, cdf_write.CellLocked, VirtuosoBridgeBackend) and adapter is cdf_write.backend_class(profile)
    assert {name for name in vars(adapter) if not name.startswith('_')} == set()      # nothing of the adapter is replaced
    import analog_optimizer.training.parallel as verified
    assert issubclass(cdf_write.factory_class(profile), verified.NativeEnvironmentFactory)


@pytest.mark.parametrize('rows, reason', [
    ([row('as1', 'XU1/MN1', 'as', 'um', 0.1, 0.2)], 'greys it out'),
    (stage_rows('w', 'wn', 0.6, 1.6) + [row('nf1', 'XU1/MN1', 'nf', 'count', 1, 4, value_type='integer')], 'not both'),
    ([row('mc', 'XU1/C1', 'm', 'um', 1, 4)], 'holds a count'),
    ([row('lc', 'XU1/C1', 'l', 'um', 1.0, 4.0)], 'must contain the present value'),
    ([row('wp', 'XU1/MP1', 'w', 'um', 1.0, 3.0, step=0.003)], 'grid'),
    ([row('mn', 'XU1/MN1', 'm', 'count', 0, 4, value_type='integer')], 'starts at 1'),
    ([row('tr', 'XU1/MN1', 'trise', '1', 0, 4)], 'not a number'),
    ([row('nf1', 'XU1/MN1', 'nf', 'count', 1, 3, value_type='integer')], r'off the 5 nm grid at 3 fingers.*that fit: 1, 2'),
])
def test_what_the_form_does_not_let_you_type_is_refused_in_plain_words(tmp_path, rows, reason):
    read_cell(tmp_path)
    with pytest.raises(profiles.ProfileError, match=reason):
        profiles.create_profile('ring_try', config(rows), recipe='ring_oscillator', expected_frequency_hz=1.2e9)


def test_a_finger_count_that_keeps_the_finger_width_on_the_grid_is_written_by_the_form(tmp_path):
    made = make(tmp_path, rows=[row('nf1', 'XU1/MN1', 'nf', 'count', 1, 2, value_type='integer')])
    assert made['writer'] == 'form'
    rules = json.loads((Path(made['directory']) / 'rules.json').read_text())
    assert [(w['cdf'], w['lower'], w['upper'], w['integer']) for w in rules['writes']] == [('fingers', 1.0, 2.0, True)]
    held = {h['cdf']: h['value'] for h in rules['held'] if h['instance'] == 'MN1'}
    assert held['w'] == pytest.approx(1e-6) and held['l'] == pytest.approx(4.5e-8) and held['m'] == 1.0   # w stays: fw = w / nf


def test_a_rule_that_says_no_in_the_instance_is_refused(tmp_path):
    meta = read_cell(tmp_path)
    facts_file = Path(meta['directory']) / cdf_facts.FILE
    facts = json.loads(facts_file.read_text())
    facts['rules']['C1']['w'] = dict(editable='no')                               # as if C1 were set to "Calculate: width"
    facts_file.write_text(json.dumps(facts))
    with pytest.raises(profiles.ProfileError, match=r'C1\.w .*greys it out in the setting C1 has now'):
        profiles.create_profile('ring_try', config([row('wc', 'XU1/C1', 'w', 'um', 2.0, 5.6)]), recipe='ring_oscillator',
                                expected_frequency_hz=1.2e9)


# ------------------------------------------------------------------------------------------ the writer's SKILL
def test_one_candidate_is_one_transaction_and_pdk_text_stays_a_string():
    field = cdf_write.Field('C1', 'w', 'string', 'cdfgData->calcParam->value!="width"', "gpdk045_capCB('w)")
    count = cdf_write.Field('C1', 'm', 'string', True, None)
    skill = cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form=dict(init='PasCdfFormInit', done=None),
                                                      targets=[(field, 3e-6), (count, 2.0)])])
    assert skill.count('dbOpenCellViewByType("LIB" "cell" "schematic" "schematic" "a")') == 1 and skill.count('dbSave(cv)') == 1
    assert 'errsetstring("cdfgData->calcParam->value!=\\"width\\"")' in skill       # the rule, quoted - never spliced in
    assert 'cdfgData~>w~>value = "3e-06"' in skill and 'cdfgData~>m~>value = "2"' in skill
    assert 'funcall(stringToSymbol("PasCdfFormInit") cdfgData)' in skill and 'PasCdfDone' not in skill
    assert f'rounds < {cdf_write.PASSES}' in skill and 'when(changed' in skill
    assert re.search(r'error\((?!"%s")', skill) is None                           # a message is never a format string
    assert cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form={}, targets=[])]) is None
    with pytest.raises(ValueError):
        cdf_write.write_skill('LIB"', 'cell', [])
    with pytest.raises(ValueError):
        cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form=dict(init='x); system("rm'), targets=[(count, 2.0)])])


def test_the_form_writer_writes_checks_exports_and_restores(tmp_path, monkeypatch):
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    backend.connect()
    initial = backend.read_parameters()
    moved = profile.assignments(dict(wn=1.2e-6, ln=6e-8, wc=3e-6, mc=3))
    backend.set_parameters(moved)
    assert backend.read_parameters() == pytest.approx(moved)
    assert client.params('MN2')['fw'] == '1.2e-06' and client.params('C1')['m'] == '3' and client.params('C2')['m'] == '2'
    assert client.params('MP1') == [i for i in profile.reference['instances'] if i['name'] == 'MP1'][0]['params']
    skill = client.skill[-1]
    assert skill.count('dbOpenCellViewByType') == 1 and 'x~>name == "MP1"' not in skill        # a fixed instance is never opened
    artifact = backend.generate_netlist(tmp_path / 'work')                                       # the export carries the values read back
    assert 'ic OUT=0' in artifact.path.read_text()
    backend.close()                                                                               # restores the recorded values
    assert profile.validate_readback(client.state) == pytest.approx(initial)
    profile.compare_written(client.state, profile.reference)            # every field as recorded, bookkeeping aside
    assert client.params('C1')['pasUpdateParamList'] != 'c w l'                 # rewritten by the form: not compared


def test_a_value_the_pdk_does_not_keep_is_rolled_back(tmp_path, monkeypatch):
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(profiles.list_profiles()['ring_cdf']['directory']), clamp=5.0e-6)
    backend.connect()
    before = backend.read_parameters()
    with pytest.raises(RuntimeError, match=r'C1\.w did not keep the value 5\.6e-06'):
        backend.set_parameters(profile.assignments(dict(wc=5.6e-6)))
    assert backend.read_parameters() == pytest.approx(before)                  # rolled back to the values before
    journal = [json.loads(p.read_text()) for p in backend.session_dir.glob('update-*.json')]
    assert [j['status'] for j in journal] == ['rolled_back']
    backend.close()


def test_a_callback_that_moves_a_value_written_before_it_settles_in_the_next_round(tmp_path, monkeypatch):
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(profiles.list_profiles()['ring_cdf']['directory']),
                                 keep_capacitance=True)                       # typing m halves the width typed before it
    backend.connect()
    moved = profile.assignments(dict(wc=3e-6, mc=3))
    backend.set_parameters(moved)
    assert client.params('C1')['m'] == '3' and num(client.params('C1')['w']) == pytest.approx(3e-6)
    assert client.rounds['C1'] >= 2 and 'MN1' not in client.rounds            # round 2 put the width back; MN1 untouched
    backend.close()


def test_a_transistor_the_form_folds_gets_its_finger_count_back(tmp_path, monkeypatch):
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(profiles.list_profiles()['ring_cdf']['directory']),
                                 fold_above=1.1e-6)
    backend.connect()
    moved = profile.assignments(dict(wn=1.5e-6))
    backend.set_parameters(moved)                                             # w folds to 2 fingers, the held count is put back
    assert client.params('MN1')['fingers'] == '1' and client.params('MN1')['fw'] == '1.5e-06'
    assert backend.read_parameters()['XU1/MN1', 'w'] == pytest.approx(1.5e-6)
    backend.close()


def test_a_changed_setting_or_held_value_is_never_accepted(tmp_path):
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    for name, key, value, reason in (('C1', 'calcParam', 'width', 'setting'), ('MN1', 'fingers', '2', 'must stay as recorded'),
                                     ('MP1', 'w', '3u', 'Fixed instance MP1 changed'), ('MN1', 'fw', '0.9u', 'Stale finger width')):
        snapshot = deepcopy(profile.reference)
        next(i for i in snapshot['instances'] if i['name'] == name)['params'][key] = value
        with pytest.raises(ValueError, match=reason):
            profile.validate_readback(snapshot)
    snapshot = deepcopy(profile.reference)                                      # bookkeeping the form rewrites is not compared
    next(i for i in snapshot['instances'] if i['name'] == 'MN1')['params']['pasUpdateParamList'] = 'w'
    profile.validate_readback(snapshot)
    profile.compare_written(snapshot, profile.reference)


def test_an_export_that_disagrees_with_the_cell_is_refused(tmp_path):
    """The netlist must carry the written values, what the form computed from them, and the record for everything else."""
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    structure = Path(made['directory']) / 'structure.scs'
    assert profile.validate_export(structure, profile.reference)              # as exported and read back: accepted
    for before, after, reason in (('as=140f ad=140f', 'as=9.9e-07 ad=140f', 'not what the form computed'),
                                  ('nf=1 as=140f', 'nf=2 as=140f', r'mismatch: XU1/MN3\.nf'),
                                  ('w=(1u) l=45n', 'w=(1.2u) l=45n', 'is not the value the form reads back'),   # all three
                                  ('w=(2u) l=45n nf=1 as=280f', 'w=(2.4u) l=45n nf=1 as=280f', r'mismatch: XU1/MP3\.w')):
        changed = tmp_path / 'changed.scs'
        times = 3 if before.startswith('w=(1u)') else 1        # the three bound transistors move together or not at all
        changed.write_text(structure.read_text().replace(before, after, times))
        with pytest.raises(ValueError, match=reason):
            profile.validate_export(changed, profile.reference)


def test_a_restoration_that_left_a_computed_value_behind_is_refused(tmp_path):
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    snapshot = deepcopy(profile.reference)
    next(i for i in snapshot['instances'] if i['name'] == 'MN1')['params']['ad'] = '1f'
    profile.validate_readback(snapshot)                                       # a value the form computes: not compared there
    with pytest.raises(RuntimeError, match=r'Restoration mismatch: MN1\.ad'):
        profile.compare_written(snapshot, profile.reference)                  # but the cell must come back as it was
    profile.compare_written(profile.reference, profile.reference)


def test_the_width_callback_sees_the_final_length_in_a_candidate_and_in_the_restoration():
    """GPDK045's width callback computes the well-proximity values from the length the transistor has at that moment and
    the length callback leaves them alone. Found on the MScR ring (2026-09-30): with the width typed first, a restoration
    left values for the last candidate's length and every candidate ran with the previous one's. The writer types a
    length before everything else of its instance, so the values belong to the final length."""
    start = dict(w='1e-06', l='4.5e-08', fingers='1', fw='1e-06', sca=wpe(4.5e-8))
    client = FakeVirtuoso(dict(instances=[dict(name='MN1', cell='nmos1v', params=dict(start))]), '', proximity=True)
    width = cdf_write.Field('MN1', 'w', 'string', True, "gpdk045_mosCB('w)")
    length = cdf_write.Field('MN1', 'l', 'string', True, "gpdk045_mosCB('l)")

    def write(w, l):
        skill = cdf_write.write_skill('LIB', 'cell', [dict(instance='MN1', form={}, targets=[(width, w), (length, l)])])
        assert client.execute_skill(skill).ok
    write(2e-6, 6e-8)
    assert client.params('MN1')['sca'] == wpe(6e-8)                           # not the value for 45 nm
    write(1e-6, 4.5e-8)                                                       # the restoration
    assert {key: client.params('MN1')[key] for key in start} == start


def test_a_written_length_types_the_held_width_again_so_the_values_follow_it():
    """Only the width, finger width and finger count callbacks recompute the well-proximity values; the length and count
    callbacks never do. A task that writes lengths and holds the widths (the MScR OTA7T) therefore ran every candidate
    with the build's values (MScR session, 2026-09-30): a round that types a length types the width again, unchanged."""
    start = dict(w='5e-07', l='4.5e-08', fingers='1', fw='5e-07', sca=wpe(4.5e-8))
    client = FakeVirtuoso(dict(instances=[dict(name='M1', cell='nmos1v', params=dict(start))]), '', proximity=True)
    length = cdf_write.Field('M1', 'l', 'string', True, "gpdk045_mosCB('l)")
    held = cdf_write.Field('M1', 'w', 'string', True, "gpdk045_mosCB('w)")    # held: the task keeps it as recorded
    skill = cdf_write.write_skill('LIB', 'cell', [dict(instance='M1', form={}, targets=[(length, 6e-8), (held, 5e-7)])])
    assert client.execute_skill(skill).ok
    assert client.params('M1')['sca'] == wpe(6e-8) and client.params('M1')['w'] == '5e-07'


def test_the_form_must_still_have_the_procedures_the_task_recorded():
    field = cdf_write.Field('C1', 'w', 'string', True, None)
    skill = cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form=dict(init='PasCdfFormInit', done=None),
                                                       targets=[(field, 3e-6)])])
    assert ('when(and(cdfgData~>doneProc cdfgData~>doneProc != "") '
            'error("%s" "C1: its form has a done procedure now"))') in skill
    bare = cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form={}, targets=[(field, 3e-6)])])
    assert ('when(and(cdfgData~>formInitProc cdfgData~>formInitProc != "") '
            'error("%s" "C1: its form has an init procedure now"))') in bare
    # A PDK that states its procedures as empty strings (a second foundry PDK, 2026-10-09: formInitProc = "", which SKILL takes as
    # true) has none: the form facts record '', the script is the bare one, and its guard lets "" through.
    empty = cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form=dict(init='', done=''), targets=[(field, 3e-6)])])
    assert empty == bare


def test_a_rules_file_whose_step_left_the_pdk_grid_does_not_load(tmp_path):
    made = make(tmp_path)
    rules = Path(made['directory']) / 'rules.json'
    saved = json.loads(rules.read_text())
    assert {w['grid'] for w in saved['writes']} == {5e-09, 1.0}                # what the PDK itself works on
    for change, reason in ((dict(step=7e-9), 'not a multiple'), (dict(lower=6.02e-7), 'off the')):
        broken = deepcopy(saved)
        broken['writes'][0].update(change)
        rules.write_text(json.dumps(broken))
        with pytest.raises(Exception, match=reason):
            profiles.load_profile('ring_cdf')


# ------------------------------------------------------------------------------------------ the run
def test_a_real_run_of_such_a_task_prepares_candidates_with_the_form_writer(tmp_path):
    made = make(tmp_path)
    target = paths.local_settings_dir() / 'bridge_connection.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(active='lab', profiles=dict(lab=dict(env_file='/x/.env', library='GATOR_TESTS',
                                                                          model_file='/pdk/model.scs')))))
    from gator_workbench.compile import compile_task
    reference = schema.CircuitReference(source='registered_task', task_id='real:ring_cdf')
    registered = config(made['parameters']).model_copy(update=dict(circuit=reference))
    runnable = tasks.load_task(reference, allow_real=True, profile_id='lab')
    factory = runnable.env_factory_builder(compile_task(registered, runnable.base_graph), tmp_path, registered.run)
    inner = getattr(factory, 'inner', factory)
    assert type(inner) is cdf_write.CdfNativeEnvironmentFactory and isinstance(inner.profile, cdf_write.CdfWritableProfile)
    assert cdf_write.CdfPreparationFactory(inner.config, inner.profile)().__class__ is cdf_write.CdfBridgeBackend


def test_a_saved_task_accepts_an_export_whose_values_changed(tmp_path):
    """A group of a saved task's mapping holds no recorded value (as the verified mappings): the parser reads it from the
    netlist. With the value recorded, every export of a changed candidate failed its own graph check."""
    made = make(tmp_path, rows=stage_rows('w', 'wn', 0.6, 1.6))                    # the verified width writer
    directory = Path(made['directory'])
    assert all('value' not in group for group in json.loads((directory / 'mapping.json').read_text())['parameter_groups'])
    changed = tmp_path / 'changed.scs'
    changed.write_text((directory / 'structure.scs').read_text().replace('w=(1u)', 'w=(1.2u)'))
    graph = profiles.load_profile('ring_cdf').optimization_graph(changed)
    assert {g.id: g.value for g in graph.parameter_groups if g.mutable} == dict(wn=pytest.approx(1.2e-6))


def test_a_netlist_built_from_the_readback_has_the_statements_of_the_cells_own_export(tmp_path, monkeypatch):
    """Record 7.140 (check-only mode): the form's values put into an earlier export's value slots give the statements of
    the export the cell itself gives - after a write, and after writing the first values back."""
    from analog_optimizer.backends.native_preparation import first_difference
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    backend.connect()
    exported = lambda artifact: Path(backend._exports[artifact.job_id][2]['original_structure_path']).read_text()
    template = exported(backend.generate_netlist(tmp_path / 'first'))
    initial = backend.read_parameters()
    for step, values in enumerate((profile.assignments(dict(wn=1.2e-6, ln=6e-8, wc=3e-6, mc=3)), initial)):
        backend.set_parameters(values)
        native = exported(backend.generate_netlist(tmp_path / f'step{step}', just_written=True))
        built = profile.render_export(template, backend.written_snapshot())
        assert first_difference(built, native) is None, step
        if step == 0:
            assert built != template
    backend.close()


def test_a_netlister_that_spells_its_numbers_another_way_still_gives_the_built_netlist(tmp_path, monkeypatch):
    """Record 7.309 (user, 2026-10-11: "14.05 is the same as 14.050"): one netlister prints an SI number with a zero per
    integer digit beyond the first (168.00f for the form's 168f), typed values and derived ones alike. The netlist built
    from the form's text then has other characters and the same numbers, and the run's comparison accepts it; another
    number is still a difference."""
    from analog_optimizer.backends.native_preparation import first_difference
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    backend.connect()
    exported = lambda artifact: Path(backend._exports[artifact.job_id][2]['original_structure_path']).read_text()
    template = exported(backend.generate_netlist(tmp_path / 'first'))
    backend.set_parameters(profile.assignments(dict(wn=1.25e-6, ln=6e-8, wc=3e-6, mc=3)))
    native = exported(backend.generate_netlist(tmp_path / 'step', just_written=True))
    spelled = re.sub(r'(?<==)(\(?)([^\s()\\]+)', lambda m: m.group(1) + cdf_write.significant_digit_spelling(m.group(2)), native)
    built = profile.render_export(template, backend.written_snapshot())
    assert spelled != native and first_difference(built, native) is None and first_difference(built, spelled) is None
    other = spelled.replace('w=1.25e-06', 'w=1.26e-06', 1)                     # the fake cell exports a written width so
    assert other != spelled and 'statement' in first_difference(built, other)
    backend.close()


def test_the_built_netlist_keeps_the_netlisters_brackets_line_breaks_and_fixed_values(tmp_path):
    """On the user's real ring export: a written value keeps its brackets, a derived one is the form's text, the line
    breaks stay, and every statement of an instance the change does not touch is left as it was."""
    from analog_optimizer.backends.native_preparation import netlist_statements
    make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    template = (Path(__file__).parent / 'fixtures/ring_osc/netlist.scs').read_text()
    snapshot = deepcopy(profile.reference)
    params = next(i for i in snapshot['instances'] if i['name'] == 'MN1')['params']
    params.update({'w': '1.2u', 'fw': '1.2u', 'l': '60n', 'as': '168f', 'ad': '168f'})
    built = profile.render_export(template, snapshot)
    old, new = netlist_statements(template), netlist_statements(built)
    changed = [(a, b) for a, b in zip(old, new) if a != b]
    assert len(old) == len(new) and [b.split()[0] for _, b in changed] == ['MN1']
    assert all(token in changed[0][1].split() for token in ('w=(1.2u)', 'l=60n', 'as=168f', 'ad=168f'))
    assert 'w=(1u)' in changed[0][0].split() and 'l=45n' in changed[0][0].split()
    assert built.count('\n') == template.count('\n') and built.count('\\\n') == template.count('\\\n')


def test_by_default_most_netlists_are_built_from_the_readback_and_each_is_the_cells_own_export(tmp_path, monkeypatch):
    """Record 7.142 (the default since the user's decision of 2026-10-02): through the preparation service, the 1st and
    6th candidate are exported and compared, the others built from the readback - and every one has the statements of the
    export the cell itself gives."""
    from analog_optimizer.backends.native_preparation import PreparationService, first_difference
    monkeypatch.delenv('GATOR_NETLIST_BUILD', raising=False)
    made = make(tmp_path)
    profile = profiles.load_profile('ring_cdf')
    backend, client = backend_of(tmp_path, monkeypatch, profile, Path(made['directory']))
    service = PreparationService(lambda: backend, timeout_seconds=30)
    service.baseline()
    rows = [(1.2e-6, 6e-8, 3e-6, 3), (1e-6, 5e-8, 2.5e-6, 2), (1.4e-6, 8e-8, 4e-6, 4), (8e-7, 4.5e-8, 2e-6, 1),
            (1.6e-6, 1e-7, 5.6e-6, 2), (1.1e-6, 7e-8, 3.5e-6, 3)]
    try:
        sources = []
        for index, (wn, ln, wc, mc) in enumerate(rows):
            _, _, metadata = service.prepare(profile.assignments(dict(wn=wn, ln=ln, wc=wc, mc=mc)), tmp_path / 'work',
                                             backend.nominal_condition(), f'c{index}')
            sources.append(metadata['netlist_source'])
            client.export('lib', 'cell', tmp_path / f'own{index}', 0)                 # what the cell itself exports now
            assert first_difference(Path(metadata['original_structure_path']).read_text(),
                                    (tmp_path / f'own{index}' / 'netlist').read_text()) is None, index
        assert sources == ['native export'] + ['built from the readback'] * 4 + ['native export']
    finally:
        service.close()


def test_a_form_writer_task_saved_before_keeps_matching_its_rows_and_its_top_value(tmp_path):
    # The recorded ring oscillator's MIM capacitor side, 2 .. 5.6 um on the 5 nm grid, tops out at 5.600000000000001e-06.
    # Such a task ran before (the form writer allows 1e-12 at its bounds); saved before compile took the top point, its
    # mapping and rules hold 5.6e-06 - its rows must still pass the check at Start, without saving it again.
    from analog_optimizer.envs.sizing import graph_contract
    from gator_workbench import profiles
    from cdf_write_support import config, make
    entry = make(tmp_path)
    directory = Path(entry['directory'])
    mapping, rules = json.loads((directory / 'mapping.json').read_text()), json.loads((directory / 'rules.json').read_text())
    side = next(g for g in mapping['parameter_groups'] if g['id'] == 'wc')
    assert side['upper'] == 5.600000000000001e-06                          # saved now: the top grid point
    side['upper'] = 5.6e-06
    for write in rules['writes']:
        if write['upper'] == 5.600000000000001e-06:
            write['upper'] = 5.6e-06
    (directory / 'mapping.json').write_text(json.dumps(mapping))
    (directory / 'rules.json').write_text(json.dumps(rules))
    profile = profiles.load_profile('ring_cdf')
    graph = profile.optimization_graph()
    compiled, _ = comp.build_graph(config(entry['parameters']), graph)
    assert graph_contract(compiled) == graph_contract(graph)
    top = ActionMapper(graph).legalize({g.id: 1.0 for g in graph.parameter_groups if g.mutable}).assignments
    profile.validate_assignment(top)
    assert {v for (device, name), v in top.items() if device.startswith('XU1/C') and name == 'w'} == {5.600000000000001e-06}


def test_a_cell_of_a_pdk_whose_quirks_say_so_gets_no_netlist_built_from_its_readback(tmp_path):
    """2026-10-10: one netlister re-spells typed values and prints changed poly-resistor lengths in a form the renderer does
    not reproduce. Such a PDK says so in its own folder of the local settings (quirks.json, never in the repository), and a
    profile on it offers no render_export: every candidate is exported natively. The PDK here is invented. (Since record
    7.309 the run's comparison takes two spellings of a number as one value; the switch stays for a netlister that changes
    more than the spelling.)"""
    from gator_workbench import pdk_record
    made = make(tmp_path)
    assert callable(profiles.load_profile('ring_cdf').render_export) and profiles.load_profile('ring_cdf').pdk_quirks == {}
    design = Path(made['directory']) / 'design.json'
    data = json.loads(design.read_text())
    design.write_text(json.dumps(dict(data, pdk_library='foundry180')))
    assert callable(profiles.load_profile('ring_cdf').render_export)          # the name alone decides nothing
    folder = pdk_record.pdk_dir('foundry180')
    folder.mkdir(parents=True)
    (folder / cdf_write.PDK_QUIRKS_FILE).write_text(json.dumps(dict(derived_value_spelling='significant_digits')))
    spelled = profiles.load_profile('ring_cdf')
    assert callable(spelled.render_export) and spelled.pdk_quirks == dict(derived_value_spelling='significant_digits')
    (folder / cdf_write.PDK_QUIRKS_FILE).write_text(json.dumps(dict(netlist_from_readback=False)))
    assert profiles.load_profile('ring_cdf').render_export is None
    (folder / cdf_write.PDK_QUIRKS_FILE).write_text('not json')
    assert callable(profiles.load_profile('ring_cdf').render_export)          # unreadable = none: the comparison then speaks


# ------------------------------------------------------------------------------------------ a computed field with a typed twin
def _computed_multiplier(tmp_path, *, typed=True, field_m=None):
    """The recorded cell with its transistors' multiplier as the second foundry's PDK has it (2026-10-10): the netlister takes m
    from `simM`, which the form computes (never typed, no iPar link to another field), while a user types the field `m`."""
    meta = read_cell(tmp_path)
    directory = Path(meta['directory'])
    facts = json.loads((directory / cdf_facts.FILE).read_text())
    for cell in ('nmos1v', 'pmos1v'):
        parameters = facts['cells'][cell]['parameters']
        parameters['simM'] = dict(parameters['simM'], default='1', editable=False)
        if not typed:
            del parameters['m']
    (directory / cdf_facts.FILE).write_text(json.dumps(facts))
    readback = json.loads((directory / 'core_readback.json').read_text())
    for inst in readback['instances']:
        if inst['name'].startswith('M'):
            inst['params']['simM'] = '1'
            if field_m is not None and inst['name'] == 'MN1':
                inst['params']['m'] = field_m
    (directory / 'core_readback.json').write_text(json.dumps(readback))


COUNT = [row('mn', 'XU1/MN1', 'm', 'count', 1, 4, value_type='integer')]


def test_a_value_the_form_computes_is_written_through_the_typed_field_of_its_own_name(tmp_path):
    _computed_multiplier(tmp_path)
    made = profiles.create_profile('ring_m', config(COUNT), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    assert made['writer'] == 'form'
    rules = json.loads((Path(made['directory']) / 'rules.json').read_text())
    assert [(w['instance'], w['cdf'], w['lower'], w['upper'], w['integer']) for w in rules['writes']] == [('MN1', 'm', 1.0, 4.0, True)]
    assert ('MN1', 'simM') not in {(h['instance'], h['cdf']) for h in rules['held']}       # computed: never typed, never held
    plan = profiles.load_profile('ring_m').cdf_plan({('XU1/MN1', 'm'): 3.0})
    assert 'cdfgData~>m~>value' in cdf_write.write_skill('GPDK045_RINGOSC', 'ring_osc_3stage', plan)
    assert 'cdfgData~>simM~>value' not in cdf_write.write_skill('GPDK045_RINGOSC', 'ring_osc_3stage', plan)


def test_the_typed_twin_is_refused_while_it_does_not_hold_the_netlisted_number(tmp_path):
    _computed_multiplier(tmp_path, field_m='2')              # as two fingers would leave it: the form's m is not the netlist's
    with pytest.raises(profiles.ProfileError, match=r'MN1\.m = .+ in the netlist, but its form field m holds .2.: the PDK computes'):
        profiles.create_profile('ring_m', config(COUNT), recipe='ring_oscillator', expected_frequency_hz=1.2e9)


def test_a_computed_value_without_a_typed_field_of_its_name_stays_refused(tmp_path):
    _computed_multiplier(tmp_path, typed=False)
    with pytest.raises(profiles.ProfileError, match=r'MN1\.m \(form field simM\): the form never lets a user type it'):
        profiles.create_profile('ring_m', config(COUNT), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
