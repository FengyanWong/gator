"""Operating points of Maestro-measured tasks (record 7.298): Spectre's binary PSF info results read without Virtuoso
(`psf_binary`), and the Maestro profile reading them for a run whose network uses them. The files are written here in
the format the reader documents - no simulator."""
import json
import math
import struct

import pytest

from gator_workbench import ocean, profiles, psf_binary, recipes
from task_save_support import saved_maestro_task


def _word(value):
    """Encode a signed integer as a big-endian PSF word."""
    return struct.pack('>i', value)


def _string(text):
    """Encode a length-prefixed Latin-1 PSF string with word-aligned padding."""
    raw = text.encode('latin-1')
    return _word(len(raw)) + raw + b'\0' * (-len(raw) % 4)


def _property(name, value):
    """Encode a named PSF property with the tag matching its value type."""
    if isinstance(value, str):
        return _word(33) + _string(name) + _string(value)
    if isinstance(value, int):
        return _word(34) + _string(name) + _word(value)
    return _word(35) + _string(name) + struct.pack('>d', value)


def write_psf(values, *, sweeps=0, model='bsim4'):
    """A binary PSF info result: every value a struct of `model` with the members of the first one (double, but
    'region' an int8 word), each followed by one property, as Spectre writes them."""
    members = list(next(iter(values.values())))
    types = {name: 100 + i for i, name in enumerate(members)}
    head = _word(0x500)
    header = b''.join(_property(k, v) for k, v in (('PSFversion', '1.1'), ('PSF sweeps', sweeps), ('PSF traces', len(values)),
                                                   ('analysis type', 'info'), ('tolerance.relative', 1e-3)))
    header_section = _word(21) + _word(4 + 8 + len(header)) + header
    definition = _word(16) + _word(99) + _string(model) + _word(0) + _word(16)
    for name in members:
        definition += _word(16) + _word(types[name]) + _string(name) + _word(0) + _word(1 if name == 'region' else 11)
        definition += _property('units', 'V')
    definition += _word(18)
    types_start = len(head) + len(header_section)
    types_end = types_start + 16 + len(definition)
    types_section = _word(21) + _word(types_end + 8) + _word(22) + _word(types_end) + definition + _word(19) + _word(0)
    items = b''
    for i, (name, record) in enumerate(values.items()):
        items += _word(16) + _word(500 + i) + _string(name) + _word(99)
        for member in members:
            items += _word(record[member]) if member == 'region' else struct.pack('>d', record[member])
        items += _property('description', 'transistor')
    values_start = types_start + len(types_section)
    values_end = values_start + 16 + len(items)
    values_section = _word(21) + _word(values_end + 8) + _word(22) + _word(values_end) + items + _word(19) + _word(0)
    body = head + header_section + types_section + values_section
    table = _word(0) + _word(4) + _word(1) + _word(types_start) + _word(4) + _word(values_start)
    return body + table + b'Clarissa' + _word(len(body))


POINT = dict(ids=2.1e-5, gm=3.3e-4, gds=1e-6, vgs=0.89, vds=0.6, vth=0.77, vdsat=0.14, region=2, trise=math.nan)


def test_a_psf_info_result_reads_into_one_record_per_instance(tmp_path):
    data = write_psf({'XU1.MN1': POINT, 'XU1.MN2': dict(POINT, ids=-1.0, region=3)})
    header, values = psf_binary.read(data)
    assert header['PSF traces'] == 2 and header['analysis type'] == 'info' and header['tolerance.relative'] == 1e-3
    assert values['XU1.MN1']['region'] == 2 and values['XU1.MN2']['ids'] == -1.0 and values['XU1.MN2']['region'] == 3
    assert math.isnan(values['XU1.MN1']['trise']) and values['XU1.MN1']['gm'] == pytest.approx(3.3e-4)
    path = tmp_path / 'dcOpInfo.info'
    path.write_bytes(data)
    assert repr(psf_binary.read_file(path)[1]) == repr(values)                 # NaN-safe equality


def test_what_the_reader_refuses():
    good = write_psf({'XU1.MN1': POINT})
    with pytest.raises(psf_binary.PsfError, match='swept'):
        psf_binary.read(write_psf({'XU1.MN1': POINT}, sweeps=1))
    with pytest.raises(psf_binary.PsfError, match='Clarissa'):
        psf_binary.read(good[:-12] + b'Mallory!' + good[-4:])
    with pytest.raises(psf_binary.PsfError):
        psf_binary.read(good[:200] + good[-12:])                       # cut in the middle
    with pytest.raises(psf_binary.PsfError):
        psf_binary.read(b'')


def test_operating_points_are_taken_from_dc_first_and_mapped_to_the_core_instance(tmp_path):
    (tmp_path / 'finalTimeOP.info').write_bytes(write_psf({'XU1.MN1': dict(POINT, vgs=9.9)}))
    points, note = recipes.maestro_operating_points(tmp_path, 'XU1', ('MN1', 'MN2'))
    assert points['XU1.MN1']['vgs'] == 9.9 and 'finalTimeOP.info: 1 of 2 transistors' in note
    (tmp_path / 'dcOpInfo.info').write_bytes(write_psf({'XU1.MN1': POINT, 'XU1.MN2': POINT, 'XU1.R1': POINT}))
    points, note = recipes.maestro_operating_points(tmp_path, 'XU1', ('MN1', 'MN2'))
    assert set(points) == {'XU1.MN1', 'XU1.MN2'} and 'dcOpInfo.info: 2 of 2' in note
    assert points['XU1.MN1'] == {k: v for k, v in POINT.items() if k in recipes.OPERATING_POINT_KEYS}   # trise left out
    (tmp_path / 'dcOpInfo.info').write_bytes(b'not psf')
    assert recipes.maestro_operating_points(tmp_path, 'XU1', ('MN1',))[0] == {}
    assert 'could not be read' in recipes.maestro_operating_points(tmp_path, 'XU1', ('MN1',))[1]
    assert recipes.maestro_operating_points(tmp_path / 'none', 'XU1', ('MN1',)) == (
        {}, 'No operating points: the Maestro deck saves neither dcOpInfo nor finalTimeOP for this run.')


def test_the_maestro_profile_reads_them_only_for_a_network_that_uses_them(tmp_path, monkeypatch):
    saved_maestro_task(tmp_path)
    profile = profiles.load_profile('ring_maestro')
    assert profile.read_operating_points is False
    job = tmp_path / 'job'
    raw = job / 'results' / 'input.raw'
    raw.mkdir(parents=True)
    (job / 'results' / 'spectre.out').write_text('spectre completes with 0 errors, 0 warnings, and 0 notices.\n')
    names = tuple(profile.mos_names)
    (raw / 'dcOpInfo.info').write_bytes(write_psf({f'{profile.core_instance}.{n}': POINT for n in names}))
    command = '/x/spectre -64 /tmp/vb/1/input.scs -raw /tmp/vb/1/input.raw +lqtimeout 900'
    result = dict(job_id='j1', analysis_settings=profile.analysis_settings, status='success', errors=[],
                  condition=dict(purpose='nominal', monte_carlo=None),
                  metadata=dict(returncode=0, spectre_command=command, output_dir=str(raw)))
    (job / 'bridge_result.json').write_text(json.dumps(result))
    monkeypatch.setattr(ocean, 'measure', lambda bridge, raw, outputs, client=None: {o['name']: 1.0 for o in outputs})
    monkeypatch.setattr('analog_optimizer.backends.spectre_validation.validate_completion', lambda *a, **k: dict(ok=True))
    assert profile.analyze(job, mos_names=names)['operating_points'] == {}
    profile.read_operating_points = True          # set before a run's first deck is built: the run records these settings
    (job / 'bridge_result.json').write_text(json.dumps(dict(result, analysis_settings=profile.analysis_settings)))
    measured = profile.analyze(job, mos_names=names)
    assert set(measured['operating_points']) == {f'{profile.core_instance}.{n}' for n in names}
    assert any('dcOpInfo.info' in note for note in measured['notes'])
    assert json.loads((job / 'measurements.json').read_text())['operating_points'] == measured['operating_points']


def test_a_run_with_operating_point_inputs_gets_the_dc_operating_point_in_its_deck(tmp_path):
    saved_maestro_task(tmp_path)
    profile = profiles.load_profile('ring_maestro')
    plain = profile.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    settings = profile.analysis_settings
    assert 'dcOpInfo' not in plain and 'operating_points' not in settings          # as before for every other run
    profile.read_operating_points = True
    deck = profile.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    assert deck.startswith(plain.rstrip('\n')) and deck.rstrip().endswith('dcOp dc\ndcOpInfo info what=oppoint where=rawfile')
    assert profile.analysis_settings == dict(settings, operating_points='added dcOp + dcOpInfo')
    assert recipes.with_dc_operating_point(deck) == deck                               # never twice
    existing = 'dcOp dc write="spectre.dc" \\\n  maxiters=150\nac ac\n'
    assert recipes.with_dc_operating_point(existing).split('\n')[2:4] == [
        '// GATOR (record 7.298): the DC operating point a network with operating-point inputs reads',
        'dcOpInfo info what=oppoint where=rawfile']                                     # right after its own DC solve
