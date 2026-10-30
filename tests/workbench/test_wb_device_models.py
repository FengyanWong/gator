"""Technology numbers of a PDK's MOS models from its Spectre model library (record 7.298): sections and includes,
"+" and "\\" continued lines, brace bins, inline subckt wrappers with their own parameters, expressions with spaces,
Spectre's temp and a subckt's implicit m. The library below is invented; no real PDK is read."""
import json
import math

import pytest

from gator_workbench import device_models as dm

TOP = '''// invented library
library demo
section tt
  parameters
  +dvth_n=0.02 dvsat=0 tox_n=2.1e-9 vthmis=0
  include "demo_mos.scs" section=mos
endsection tt
section ff
  parameters dvth_n=-0.05 dvsat=0.1 tox_n=2.0e-9 vthmis=0
  include "demo_mos.scs" section=mos
endsection ff
endl demo
'''
MOS = '''library demo_mos
section mos
inline subckt nmos1v (d g s b)
  parameters l=45n w=120n nf=1 geo=1/sqrt(l*w*nf*m)
  nmos1v (d g s b) n_main l=l w=w nf=nf
  model n_main bsim4 type=n {
    1: lmin=45n lmax=1u wmin=120n wmax=10u vth0= 0.40 + dvth_n + vthmis*geo u0=0.03 \\
       vsat=1.1e5*(1+dvsat) toxe=tox_n
    2: lmin=1u lmax=20u wmin=120n wmax=10u vth0=0.38 u0=320 vsat=9e4 toxe=tox_n
  }
ends nmos1v
model pch bsim3v3 type=p lmin=180n wmin=220n vth0=-0.45*(1+0.001*(temp-27)) uo=120 vsat=8e4 tox=4.1e-9
statistics {
  process { vary dvth_n dist=gauss std=0.01 }
}
endsection mos
endl demo_mos
'''
RECORD = dict(devices=dict(
    nmos1v=dict(standard_kind='nmos', parameters=[dict(name='w', default='1u'), dict(name='l', default='45n')]),
    pch=dict(standard_kind='pmos', parameters=[]),
    ncap=dict(standard_kind='nmos', parameters=[dict(name='w', default='2u'), dict(name='l', default='1u')]),
    rpoly=dict(standard_kind='resistor', parameters=[])))
FILES = {'/pdk/models/demo.scs': TOP, '/pdk/models/demo_mos.scs': MOS}


def read(path):
    return FILES.get(path)


def test_the_nominal_section_s_numbers_of_every_mos_model():
    library = dm.read_library(read, '/pdk/models/demo.scs', 'tt')
    assert not library.missing and 'nmos1v' in library.wrappers and 'pch' in library.cards
    found, problems = dm.mos_numbers(library, RECORD)
    n, p, cap = found['nmos1v'], found['pch'], found['ncap']
    assert n['basis'] == 'model bin' and n['lmin'] == pytest.approx(45e-9) and n['wmin'] == pytest.approx(120e-9)
    assert n['vth0'] == pytest.approx(0.42) and n['u0'] == pytest.approx(0.03) and n['vsat'] == pytest.approx(1.1e5)
    assert n['tox'] == pytest.approx(2.1e-9)
    assert p['vth0'] == pytest.approx(-0.45) and p['u0'] == pytest.approx(0.012) and p['tox'] == pytest.approx(4.1e-9)
    assert cap == dict(lmin=pytest.approx(1e-6), wmin=pytest.approx(2e-6), basis='CDF default size')   # no card: sizes only
    assert 'rpoly' not in found and not problems                                               # not a MOS model
    corner = dm.mos_numbers(dm.read_library(read, '/pdk/models/demo.scs', 'ff'), RECORD)[0]['nmos1v']
    assert corner['vth0'] == pytest.approx(0.35) and corner['vsat'] == pytest.approx(1.21e5)
    hot = dm.mos_numbers(library, RECORD, temperature_c=127.0)[0]['pch']
    assert hot['vth0'] == pytest.approx(-0.45 * 1.1)


def test_a_model_the_section_does_not_reach_is_named_a_problem():
    record = dict(devices=dict(RECORD['devices'], nrf=dict(standard_kind='nmos', parameters=[])))
    found, problems = dm.mos_numbers(dm.read_library(read, '/pdk/models/demo.scs', 'tt'), record)
    assert 'nrf' not in found and problems == {'nrf': 'not found in the nominal section of the cached model library'}
    library = dm.read_library(lambda path: None, '/pdk/models/demo.scs', 'tt')
    assert library.missing == ['/pdk/models/demo.scs']


def test_expressions_are_evaluated_without_running_code():
    scope = dict(a='2', b='a*3', loop='loop+1')
    assert dm.evaluate('b + 1k', scope) == pytest.approx(1006.0) and dm.evaluate('2^3', {}) == 8.0
    assert dm.evaluate('sqrt(a) * 1n', scope) == pytest.approx(math.sqrt(2) * 1e-9)
    for refused in ('loop', 'undefined', '__import__("os")', 'a if a else b', 'agauss(0, 1, 3)', '1/0', '"text"'):
        assert dm.evaluate(refused, scope) is None
    assert dm.assignments('vth0= -0.5 + d  u0=1 x==2 w=1u') == {'vth0': '-0.5 + d', 'u0': '1 x==2', 'w': '1u'}


def test_build_and_load_keep_the_numbers_beside_the_record(tmp_path, monkeypatch):
    from gator_workbench import pdk_record
    monkeypatch.setenv('GATOR_WORKBENCH_SETTINGS_DIR', str(tmp_path))
    record = dict(RECORD, format=pdk_record.FORMAT, pdk_id='demo', sha256='a' * 64, technology_library='demo',
                  sources=dict(model_files=[dict(path=p, bytes=len(t), sha256=f'{i}' * 64) for i, (p, t) in enumerate(FILES.items())]))
    monkeypatch.setattr(dm, 'load_record', lambda pdk_id, sha256=None: record if pdk_id == 'demo' else None)
    cache = tmp_path / 'pdk-model-files' / 'user@host' / 'demo'
    cache.mkdir(parents=True)
    index = {}
    for i, (path, text) in enumerate(FILES.items()):
        (cache / (f'{i}' * 64)).write_text(text)
        index[path] = dict(bytes=len(text), modified=0, sha256=f'{i}' * 64)
    (cache / 'index.json').write_text(json.dumps(index))
    document = dm.build('demo')
    saved = json.loads((tmp_path / 'pdks' / 'demo' / dm.FILE).read_text())
    assert saved == document and saved['entry'] == '/pdk/models/demo.scs' and saved['record_sha256'] == 'a' * 64
    assert set(saved['devices']) == {'nmos1v', 'pch', 'ncap'} and dm.load('demo') == saved
    assert dm.summary(saved) == '3 of 3 MOS models read (2 with all four technology numbers, 2 minimum sizes from their model bins)'
    record['sha256'] = 'b' * 64                                   # the PDK was loaded again: the numbers are read again
    assert dm.load('demo')['record_sha256'] == 'b' * 64
    assert dm.load('other') is None
