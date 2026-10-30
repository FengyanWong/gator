"""One way of writing a quantity (record 7.208): the number, an SI prefix and the unit, as Virtuoso's forms write them, in
English letters only (user: "dont use greek characters for unit, use english letters instead") - the
stored number's own digits, moved and never computed. The page writes and reads the same way (frontend/src/units.ts) from
the table /api/schema sends; frontend/scripts/unit_text_check.mjs checks the page against the same cases."""
import pytest
from fastapi.testclient import TestClient

from gator_workbench import units
from helpers import workbench_app

CASES = [  # stored number, the row's unit, as it is written
    (4.5e-7, 'm', '450 nm'), (0.6, 'um', '600 nm'), (1.205, 'um', '1.205 um'), (0.045, 'um', '45 nm'), (20.0, 'um', '20 um'),
    (0.01, 'um', '10 nm'), (0.0004, 'A', '400 uA'), (1e8, 'Hz', '100 MHz'), (1.1e9, 'Hz', '1.1 GHz'), (-30.0, 'dB', '-30 dB'),
    (60.0, 'deg', '60 deg'), (9535.0, 'ohm', '9.535 kohm'), (477.0, 'ohm', '477 ohm'), (0.22, 'V', '220 mV'), (0.032, 'V', '32 mV'),
    (1.2, 'V', '1.2 V'), (-1e9, 'Hz/V', '-1 GHz/V'), (12, 'count', '12'), (0.006, '1', '0.006'), (45.0, '%', '45 %'),
    (400.0, 'V/V', '400 V/V'), (5.0, 'mV/V', '5 mV/V'), (0.0005, 'W', '500 uW'), (0.0, 'um', '0 um'), (0.0, 'A', '0 A'), (1e-21, 'm', '1e-21 m'),
    (3.3e16, 'Hz', '3.3e16 Hz'), (999e12, 'Hz', '999 THz'), (27.0, 'degC', '27 degC'), (4.99e-14, 'F', '49.9 fF'),
    (0.5, 'pF', '500 fF'), (0.001, 'm', '1 mm'), (-0.00045, 'A', '-450 uA'), (0.1 + 0.2, 'V', '300.00000000000004 mV'),
]


@pytest.mark.parametrize('value, unit, written', CASES)
def test_a_stored_number_is_written_with_its_own_digits_a_prefix_and_its_unit(value, unit, written):
    assert units.text(value, unit) == written


def test_what_is_not_a_number_or_not_a_known_unit_stays_as_it_is():
    assert units.text(None, 'V') == '' and units.text('abc', 'V') == 'abc' and units.text(float('nan'), 'V') == 'nan'
    assert units.text(2.5, 'furlong') == '2.5 furlong' and units.text(3.0, None) == '3' and units.text(True, 'V') == 'True'


def test_the_page_gets_the_same_table_with_the_schema(tmp_path):
    client = TestClient(workbench_app(tmp_path, auto_check_on_start=True))
    forms = client.get('/api/schema').json()['unit_forms']
    assert forms['spellings']['um'] == ['m', 1e-6, 0.0] and forms['spellings']['kΩ'] == ['ohm', 1e3, 0.0]
    assert 'Hz' in forms['prefixable'] and 'dB' not in forms['prefixable'] and forms['symbols']['Ω'] == 'ohm'
    assert not any(set(written) & set('µμΩ°') for written in forms['symbols'].values())          # written in English letters
    assert {rule[0] for rule in forms['spellings'].values()} <= set(forms['quantities'])     # every quantity can be named
    assert forms['kinds'] == dict(w='m', l='m', m='count', nf='count', r='ohm', c='F', ind='H')   # a parameter's quantity (no Unit column)
