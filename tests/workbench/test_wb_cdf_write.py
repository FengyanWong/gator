"""Real runs that write any value the PDK's property form lets a user type (cdf_facts -> cdf_rules -> cdf_write).

The recorded REAL ring oscillator (fixtures/ring_osc: export, readbacks, and core_cdf.json = what the form of each of its
instances lets a user type, read-only). The Virtuoso side is a fake that runs the writer's SKILL the way the form would:
the fields it sets, then their callbacks - emulated here (a test model, not the PDK's: a transistor keeps total width =
fingers x finger width and folds when told to, a MIM capacitor side is clamped). No Virtuoso, no simulation."""
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import sys
from types import SimpleNamespace

import pytest

from analog_optimizer.backends.virtuoso_bridge import BridgeConfig, VirtuosoBridgeBackend
from gator_workbench import bridge_read, cdf_facts, cdf_write, paths, profiles, schema, tasks
from gator_workbench.generic_profile import GenericMosWidthProfile
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from helpers import probe

from ring_cell_support import CIRCUIT, FIXTURE                                    # the same cell as the profile tests'
from cdf_write_support import config, make, read_cell, row, stage_rows


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
    assert cdf_write.backend_class(profile) is VirtuosoBridgeBackend


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


# ------------------------------------------------------------------------------------------ the fake Virtuoso
MOS_NETLIST = dict(w='w', l='l', nf='fingers', m='m', **{k: k for k in ('as', 'ad', 'ps', 'pd', 'nrd', 'nrs')})
CAP_NETLIST = dict(w='w', l='l', m='m')
SET = re.compile(r'cdfgData~>(\w+)~>value = ("(?:[^"\\]|\\.)*"|[^\s)]+)')
CALL = re.compile(r'unless\(errsetstring\("((?:[^"\\]|\\.)*)"\) error')
BLOCK = re.compile(r'x~>name == "([^"]+)"')
HOLDS = re.compile(r'funcall\(same cdfParseFloatString\(or\(cdfgData~>(\w+)~>value ""\)\) ([-\d.e+]+)\)'
                   r'|funcall\(same cdfgData~>(\w+)~>value ([-\d.e+]+)\)'
                   r'|equal\(cdfgData~>(\w+)~>value "([^"]*)"\)'
                   r'|equal\(cdfgData~>(\w+)~>value (\d+)\)')
FINAL = re.compile(r'unless\((.+?) error\("%s" "((?:[^"\\]|\\.)*)"\)\)$')
ROUNDS = re.compile(r'rounds < (\d+)')
PROC = re.compile(r'funcall\(stringToSymbol\("(\w+)"\) (cdfgData|inst)\)')


def holds_of(text):
    """(field, wanted, numeric) of a generated "does the instance hold this value" test."""
    m = HOLDS.search(text)
    if not m:
        return None
    groups = [g for g in m.groups() if g is not None]
    field, wanted = groups[0], groups[1]
    return field, wanted, m.group(5) is None


def num(text):
    from analog_optimizer.backends.gpdk045 import number
    return number(text)


def wpe(length):
    """Stand-in for a GPDK045 well-proximity value (sca): its width callback computes it from the current length."""
    return format(3.25e-6 / length, '.7g')


class FakeVirtuoso:
    """Runs the writer's SKILL as the form would: the fields it sets, then the callbacks. Test model only."""

    def __init__(self, reference, netlist, *, clamp=5.6e-6, fold_above=None, keep_capacitance=False, proximity=False):
        self.state, self.netlist, self.clamp, self.fold_above = deepcopy(reference), netlist, clamp, fold_above
        self.proximity = proximity                                           # model the well-proximity value (sca)
        self.keep_capacitance = keep_capacitance
        self.skill, self.saves, self.opened, self.form_calls, self.rounds = [], 0, [], [], {}
        self.schematic = SimpleNamespace(read=lambda *a, **kw: deepcopy(self.state), export_netlist=self.export)

    def list_windows(self):
        return []

    def close(self):
        pass

    def params(self, name):
        return next(i for i in self.state['instances'] if i['name'] == name)['params']

    def callback(self, name, text):
        p, field = self.params(name), re.search(r"'\s*(\w+)", text).group(1)
        if text.startswith('gpdk045_mosCB'):
            w, fingers = num(p['w']), num(p['fingers'])
            if field == 'w' and self.fold_above and w > self.fold_above:
                fingers = math.ceil(w / self.fold_above)                     # the form folds a wide transistor
                p['fingers'] = str(fingers)
            if field == 'fw':
                w = num(p['fw']) * fingers
                p['w'] = format(w, '.12g')
            p['fw'] = format(w / fingers, '.12g')
            for key in ('ad', 'as'):
                p[key] = format(w * 1.4e-7, '.12g')
            for key in ('pd', 'ps'):
                p[key] = format(2 * w + 2.8e-7, '.12g')
            for key in ('nrd', 'nrs'):
                p[key] = format(1.4e-7 / w, '.12g')
            if field == 'w' and self.proximity:                              # from the length it has NOW (GPDK045's does)
                p['sca'] = wpe(num(p['l']))
        elif text.startswith('gpdk045_capCB'):
            if field == 'm' and self.keep_capacitance:                       # a form that keeps the total capacitance
                p['w'] = format(num(p['w']) * 0.5, '.12g')                   # moves a value written before it
            else:
                p[field] = format(min(self.clamp, max(1e-6, num(p[field]))), '.12g')
            w, l = num(p['w']), num(p['l'])
            p['c'] = format(1.025e-3 * w * l + 2.425e-10 * 2 * (w + l), '.6g')       # area + fringe, 6 digits
            p['pasUpdateParamList'] = f'{field} c'                           # bookkeeping the form rewrites

    def holds(self, name, test):
        field, wanted, numeric = test
        have = self.params(name).get(field)
        return (have is not None and num(have) is not None and math.isclose(num(have), float(wanted), rel_tol=1e-9, abs_tol=1e-30)
                if numeric else have == wanted)

    def blocks(self, skill):
        """The generated SKILL as the writer means it: per instance its form procedures, the ordered (test, field, value,
        callback) of the round, the round limit and the final checks. Nothing is assumed: what is not in the text does not
        happen here either."""
        out, current = [], None
        for line in skill.splitlines():
            block = BLOCK.search(line)
            if block:
                current = dict(instance=block.group(1), init=None, done=None, rounds=0, targets=[], final=[], pending=[])
                out.append(current)
            if current is None:
                continue
            for name, argument in PROC.findall(line):
                current['init' if argument == 'cdfgData' else 'done'] = name
            if 'when(or(' in line:
                current['pending'] = [t for t in (holds_of(part) for part in line.split(' !')) if t]
            found = ROUNDS.search(line)
            if found:
                current['rounds'] = int(found.group(1))
            if 'lengthTyped = t' in line:
                current['retype'] = True                                     # the width is typed again after a length
            if line.strip().startswith('unless(') and holds_of(line) and 'error(' not in line:
                current['test'] = holds_of(line)                             # the round's "unless it already holds"
            setter = SET.search(line)
            if setter and current.get('test'):
                value = setter.group(2)
                current['targets'].append(dict(test=current.pop('test'), field=setter.group(1),
                                               value=json.loads(value) if value.startswith('"') else value, callback=None))
            called = CALL.search(line)
            if called and current['targets']:
                current['targets'][-1]['callback'] = json.loads(f'"{called.group(1)}"')
            end = FINAL.search(line.strip())
            if end and holds_of(end.group(1)) and 'value = ' not in line:
                current['final'].append((holds_of(end.group(1)), end.group(2)))
        return out

    def execute_skill(self, skill, timeout=60):
        """Run it as Virtuoso would: an instance whose values all hold is not touched, the round repeats while something
        was written (at most the generated limit), and a generated final check that fails is the answer."""
        self.skill.append(skill)
        changed = False
        for block in self.blocks(skill):
            name = block['instance']
            if block['pending'] and all(self.holds(name, test) for test in block['pending']):
                continue                                                     # untouched: no form procedure, no callback
            self.opened.append(name)
            if block['init']:
                self.form_calls.append((name, block['init']))
            for round_number in range(block['rounds']):
                self.rounds[name] = round_number + 1
                wrote, length_typed = False, False
                for target in block['targets']:
                    again = block.get('retype') and target['field'] == 'w' and length_typed
                    if self.holds(name, target['test']) and not again:
                        continue
                    self.params(name)[target['field']] = target['value']
                    if target['callback']:
                        self.callback(name, target['callback'])
                    length_typed = target['field'] == 'l' or (length_typed and target['field'] != 'w')
                    wrote = True
                if not wrote:
                    break
            for test, message in block['final']:
                if not self.holds(name, test):
                    return SimpleNamespace(ok=False, output=None, errors=[message])
            if block['done']:
                self.form_calls.append((name, block['done']))
            changed = True
        if changed:
            self.saves += 1
        return SimpleNamespace(ok=True, output='t', errors=[])

    def export(self, lib, cell, output, timeout):
        """The fixture's netlist with the values of the cell as it is now."""
        output.mkdir()
        text = self.netlist.replace('\\\n', ' ')
        for inst in self.state['instances']:
            names = MOS_NETLIST if inst['cell'] in ('nmos1v', 'pmos1v') else CAP_NETLIST
            def put(match):
                key = match.group(1)
                return f'{key}={inst["params"][names[key]]}' if key in names and names[key] in inst['params'] else match.group(0)
            text = re.sub(rf'(?m)^(\s*{inst["name"]} \(.*)$',
                          lambda line: re.sub(r'\b(\w+)=\(?([^\s()]+)\)?', put, line.group(1)), text)
        (output / 'netlist').write_text(text)
        return {'input_file': str(output / 'input.scs')}


def backend_of(tmp_path, monkeypatch, profile, directory, **fake):
    client = FakeVirtuoso(profile.reference, (directory / 'structure.scs').read_text(), **fake)

    def attach(self):
        self.bridge_version = 'offline-fault-injection'
        return client
    monkeypatch.setattr(VirtuosoBridgeBackend, '_attach', attach)
    env = tmp_path / 'bridge.env'
    env.write_text('# offline test configuration\n')
    config = BridgeConfig(env, 'GPDK045_RINGOSC', directory / 'creation.json', tmp_path / 'state', '/models/gpdk045.scs')
    return cdf_write.backend_class(profile)(config, profile), client


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
    assert 'when(cdfgData~>doneProc error("%s" "C1: its form has a done procedure now"))' in skill
    bare = cdf_write.write_skill('LIB', 'cell', [dict(instance='C1', form={}, targets=[(field, 3e-6)])])
    assert 'when(cdfgData~>formInitProc error("%s" "C1: its form has an init procedure now"))' in bare


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
