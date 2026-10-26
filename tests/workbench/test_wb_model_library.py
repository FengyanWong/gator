"""The trimmed model library (record 7.154): the library's layout read by names with the awk script (run here by bash
with the system's gawk and with mawk, as the host runs it), the parts kept per section for a circuit's devices, the deck's
model include replaced, and when a run gets it. A made-up library in GPDK045's shape - no PDK file, no simulator."""
import os
import shutil
import subprocess

import pytest

from gator_workbench import model_library as ml, profiles, recipes
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module

TOP = '''// a made-up library in GPDK045's shape
library toplib
section tt
  include "dev_mos.scs" section=tt
  include "dev_mos.scs" section=tt_hv
  include "dev_cap.scs" section=tt_cap
  include "dev_res.scs" section=tt_res
  include "soa.scs" section=OFF
endsection tt
section ff
  include "dev_mos.scs" section=ff
  include "dev_mos.scs" section=ff_hv
  include "dev_cap.scs" section=tt_cap
  include "dev_res.scs" section=tt_res
  include "soa.scs" section=OFF
endsection ff
section own
  parameters x=1
  include "dev_mos.scs" section=tt
endsection own
section broken
  include "missing.scs" section=tt
  include "dev_cap.scs" section=tt_cap
endsection broken
endlibrary toplib
'''
MOS = '''simulator lang=spectre
library mos
section tt
  parameters dvt=0
  include "dev_mos.scs" section=core
  include "./dev_mos.scs" section = rg
endsection tt
section ff
  parameters dvt=-0.05
  include "dev_mos.scs" section=core
  include "dev_mos.scs" section=rg
endsection ff
section tt_hv
  include "dev_mos.scs" section=core_hv
endsection tt_hv
section ff_hv
  include "dev_mos.scs" section=core_hv
endsection ff_hv
section core
* a SPICE-style comment line
inline subckt nch (d g s b)
  parameters w=1u l=1u
  xr (g gi) rgate r=10
  nch (d gi s b) nch_mod w=w l=l // the device itself
ends nch
model nch_mod bsim4 type=n \\
    vth0=0.4 \\
    u0=0.03
inline subckt pch (d g s b)
  pch (d g s b) pch_mod
ends pch
model pch_mod bsim4 type=p
endsection core
section core_hv
subckt nch_hv (d g s b)
  m1 (d g s b) nch_mod
ends nch_hv
endsection core_hv
section rg
subckt rgate (a b)
  parameters r=1
  r0 (a b) resistor r=r
ends rgate
endsection rg
endlibrary mos
'''
CAP = '''section tt_cap
  include "dev_cap.scs" section=cap
endsection
section cap
subckt mimcap (a b)
  c0 (a b) capacitor c=1f
ends mimcap
endsection
'''
RES = '''simulator lang=spice
.lib tt_res
.subckt rpoly a b
c1 a b mimcap
r1 a b 1k
.ends rpoly
.model rmod r rsh=100
+ tc1=0.001
.endl tt_res
'''
SOA = '''section OFF
  parameters soa_on=0
endsection
'''


@pytest.fixture
def library(tmp_path):
    """Write an invented model-library tree with MOS, capacitor, resistor and SOA sections."""
    folder = tmp_path / 'lib'
    folder.mkdir()
    for name, text in dict(top=TOP, dev_mos=MOS, dev_cap=CAP, dev_res=RES, soa=SOA).items():
        (folder / f'{name}.scs').write_text(text)
    return folder


def runner(tmp_path, awk):
    """run(script) as the host runs it: bash, with `awk` = the given implementation."""
    found = shutil.which(awk)
    if found is None:
        pytest.skip(f'{awk} is not installed')
    bin_dir = tmp_path / f'bin-{awk}'
    bin_dir.mkdir(exist_ok=True)
    if not (bin_dir / 'awk').exists():
        (bin_dir / 'awk').symlink_to(found)
    calls = []

    def run(script):
        """Run and record the model-library script with the selected local awk implementation."""
        calls.append(script)
        done = subprocess.run(['bash'], input=script, capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}'))
        assert done.returncode == 0, done.stderr
        return done.stdout
    run.calls = calls
    return run


@pytest.mark.parametrize('awk', ['gawk', 'mawk'])
def test_the_layout_is_read_by_names_in_rounds_and_both_awks_agree(tmp_path, library, awk):
    run = runner(tmp_path, awk)
    files, sections = ml.read_structure(run, str(library / 'top.scs'))
    assert len(run.calls) == 2                                   # the model file, then the four files it includes
    assert files[str(library / 'missing.scs')] is None and files[str(library / 'top.scs')][0] == str(len(TOP))
    mos = str(library / 'dev_mos.scs')
    assert sections[mos, 'core']['defines'] == {'nch', 'nch_mod', 'pch', 'pch_mod'}
    assert sections[mos, 'core']['refs'] == {'rgate', 'nch_mod', 'pch_mod'}           # what its subcircuits use
    assert sections[mos, 'tt']['includes'] == [('dev_mos.scs', 'core'), ('./dev_mos.scs', 'rg')]
    assert sections[mos, 'tt']['own'] == 1 and sections[mos, 'core']['own'] == 4    # parameters / 4 definitions
    res = str(library / 'dev_res.scs')
    assert sections[res, 'tt_res']['defines'] == {'rpoly', 'rmod'} and 'mimcap' in sections[res, 'tt_res']['refs']
    top = str(library / 'top.scs')
    assert sections[top, 'own']['own'] == 1 and sections[top, 'tt']['own'] == 0 and sections[top, 'tt']['span'] == (3, 9)
    other = runner(tmp_path, 'gawk' if awk == 'mawk' else 'mawk')
    assert ml.read_structure(other, top) == (files, sections)


def test_a_section_keeps_the_parts_its_devices_need_and_every_part_without_devices(tmp_path, library):
    top = str(library / 'top.scs')
    plan = ml.plan_library(ml.read_structure(runner(tmp_path, 'gawk'), top), top,
                           {'nch', 'pch', 'mimcap', 'resistor', 'vsource', 'XU1_sub'})
    lib = str(library)
    assert plan['sections']['tt'] == [f'include "{lib}/dev_mos.scs" section=tt', f'include "{lib}/dev_cap.scs" section=tt_cap',
                                      f'include "{lib}/soa.scs" section=OFF']
    assert plan['sections']['ff'][0] == f'include "{lib}/dev_mos.scs" section=ff'           # a corner gets its own parts
    assert plan['parts'] == dict(tt=[3, 5], ff=[3, 5])
    assert plan['devices'] == ['mimcap', 'nch', 'pch']
    assert 'statements of its own' in plan['not_trimmed']['own'] and 'cannot be read' in plan['not_trimmed']['broken']


def test_a_part_a_kept_subcircuit_uses_is_kept_too(tmp_path, library):
    top = str(library / 'top.scs')
    plan = ml.plan_library(ml.read_structure(runner(tmp_path, 'gawk'), top), top, {'rpoly'})
    assert [line.split('section=')[1] for line in plan['sections']['tt']] == ['tt_cap', 'tt_res', 'OFF']   # rpoly uses mimcap


def test_nothing_is_trimmed_when_every_part_is_needed(tmp_path, library):
    top = str(library / 'top.scs')
    plan = ml.plan_library(ml.read_structure(runner(tmp_path, 'gawk'), top), top, {'nch', 'nch_hv', 'mimcap', 'rpoly'})
    assert 'tt' not in plan['sections'] and plan['not_trimmed']['tt'] == 'the circuit needs every part it includes'


def test_the_deck_s_one_model_include_is_replaced_for_its_own_section_only():
    library = dict(model_file='/pdk/model.scs', sections=dict(tt=['include "/pdk/a.scs" section=tt', 'include "/pdk/b.scs"']),
                   parts=dict(tt=[2, 9]))
    deck = 'simulator lang=spectre\nglobal 0\ninclude "/pdk/model.scs" section=tt\ninclude "/run/ic.scs"\nM1 (a b c d) nch\n'
    trimmed = ml.apply(deck, '/pdk/model.scs', 'tt', library)
    assert trimmed == ('simulator lang=spectre\nglobal 0\n'
                       '// GATOR trimmed model library: 2 of the 9 parts of /pdk/model.scs section tt (record 7.154)\n'
                       'include "/pdk/a.scs" section=tt\ninclude "/pdk/b.scs"\ninclude "/run/ic.scs"\nM1 (a b c d) nch\n')
    assert ml.apply(deck, '/pdk/model.scs', 'ff', library) == deck                     # no trimmed ff: the whole file
    assert ml.apply(deck, '/pdk/other.scs', 'tt', library) == deck
    assert ml.apply(deck, '/pdk/model.scs', 'tt', None) == deck
    twice = deck + 'include "/pdk/model.scs" section=tt\n'
    assert ml.apply(twice, '/pdk/model.scs', 'tt', library) == twice                  # not exactly one: left alone


def test_the_devices_of_a_deck_are_its_instances_masters():
    deck = ('subckt amp (a b)\n  M1 (a b 0 0) g45n1svt w=1u \\\n    l=45n\n  C1 (a b) g45cmim m=2\nends amp\n'
            'XU1 (n1 n2) amp\nV0 (n1 0) vsource dc=1\n// M9 (x y) commented\ndcOp dc\n')
    assert ml.devices_used(deck) == {'g45n1svt', 'g45cmim', 'vsource'}
    with pytest.raises(ml.LibraryError, match='SPICE syntax'):
        ml.devices_used('simulator lang=spice\nM1 a b c d nch\n')


class Profile:
    """A profile stand-in supplying the nominal model section and temperature."""
    nominal_corner = type('Corner', (), dict(model_section='tt', temperature_c=27.0))()


def test_a_run_gets_the_library_only_with_a_recorded_baseline(tmp_path, library, monkeypatch):
    top = str(library / 'top.scs')
    config = type('Config', (), dict(model_file=top))()
    structure = 'subckt c (a b)\nM1 (a b 0 0) nch\nC1 (a b) mimcap\nends c\nX1 (a b) c\n'
    run = runner(tmp_path, 'gawk')
    profile = Profile()
    assert ml.attach(profile, config, reference={'gain': 1.0}, structure=structure, run=run) is not None
    event = profile.model_library_event
    assert event['trimmed'] and event['parts']['tt'] == [3, 5] and event['devices'] == ['mimcap', 'nch'] and '1e-6' in event['note']
    assert ml.apply(f'include "{top}" section=tt\n', top, 'tt', profile.model_library).count('include') == 3

    assert ml.attach(profile, config, reference=None, structure=structure, run=run) is None
    assert profile.model_library is None and 'No recorded baseline yet' in profile.model_library_event['note']
    monkeypatch.setenv(ml.ENV, 'full')
    assert ml.attach(profile, config, reference={'gain': 1.0}, structure=structure, run=run) is None
    assert 'GATOR_MODEL_LIBRARY=full' in profile.model_library_event['note']
    monkeypatch.setenv(ml.ENV, 'half')
    with pytest.raises(ValueError, match='must be one of trimmed, full'):
        ml.attach(profile, config, reference={'gain': 1.0}, structure=structure, run=run)
    monkeypatch.delenv(ml.ENV)

    def unreachable(script):
        """Raise the model-library error for an unavailable simulator-host connection."""
        raise ml.LibraryError('the bridge connection to the simulator host is not running')
    assert ml.attach(profile, config, reference={'gain': 1.0}, structure=structure, run=unreachable) is None
    assert 'could not be read' in profile.model_library_event['note'] and profile.model_library is None


def test_a_path_with_shell_characters_never_reaches_the_script():
    with pytest.raises(ml.LibraryError, match='not a plain absolute path'):
        ml.structure_script(['/pdk/x.scs; rm -rf /'])
    assert ml.resolve('/pdk/top.scs', '../lib/$(id).scs') is None and ml.resolve('/pdk/top.scs', 'a.scs') == '/pdk/a.scs'


LIBRARY = dict(model_file='/pdk/model.scs', sections=dict(tt=['include "/pdk/mos.scs" section=tt']), parts=dict(tt=[1, 23]))


def test_a_maestro_deck_takes_the_run_s_library(tmp_path):
    from task_save_support import saved_maestro_task
    saved_maestro_task(tmp_path)
    maestro = profiles.load_profile('ring_maestro')
    whole = maestro.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    maestro.model_library = LIBRARY
    trimmed = maestro.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    assert 'include "/pdk/model.scs" section=tt' in whole and 'include "/pdk/model.scs"' not in trimmed
    assert trimmed.replace('// GATOR trimmed model library: 1 of the 23 parts of /pdk/model.scs section tt (record 7.154)\n'
                           'include "/pdk/mos.scs" section=tt', 'include "/pdk/model.scs" section=tt') == whole


def test_the_ring_and_adapter_decks_take_the_run_s_library(tmp_path):
    from ring_cell_support import config as ring_config, read_cell
    from analog_optimizer.backends.virtuoso_bridge import build_deck
    read_cell(tmp_path)
    profiles.create_profile('ring_osc_3stage', ring_config(), recipe='ring_oscillator', expected_frequency_hz=1.2e9)
    ring = profiles.load_profile('ring_osc_3stage')
    plain = ring.build_deck('// structure only', '/pdk/model.scs')
    ring.model_library = LIBRARY
    assert ring.build_deck('// structure only', '/pdk/model.scs').count('include "/pdk/mos.scs" section=tt') == 1
    assert 'include "/pdk/model.scs" section=tt' in plain
    adapter = recipes.GenericMosWidthProfile.build_deck(ring, '// structure only', '/pdk/model.scs')   # the op-amp recipe's deck
    assert 'include "/pdk/mos.scs" section=tt' in adapter and 'ac ac start=10' in adapter
    ring.model_library = None
    assert recipes.GenericMosWidthProfile.build_deck(ring, '// structure only', '/pdk/model.scs') == build_deck(
        '// structure only', '/pdk/model.scs')


def test_a_run_says_which_parts_of_the_model_file_its_decks_load(tmp_path, monkeypatch):
    from dataclasses import fields, replace
    import json
    import types
    from gator_workbench import tasks
    from helpers import execute, make_config
    event = dict(trimmed=True, model_file='/pdk/model.scs', parts=dict(tt=[3, 23]), devices=['nch'], not_trimmed={},
                 read_seconds=0.5, note='only these parts')

    class WithProfile(tasks.SyntheticEnvFactory):          # a real run's factory carries the profile with its library
        """A synthetic environment factory carrying a real-run-style model-library event."""
        profile = types.SimpleNamespace(model_library_event=event)
    load = tasks.load_task

    def loading(*args, **kwargs):
        """Load a task whose environment factory also exposes the fixture model-library event."""
        task = load(*args, **kwargs)
        build = task.env_factory_builder

        def builder(*inputs):
            """Wrap the task's synthetic factory with the fixture profile."""
            factory = build(*inputs)
            return WithProfile(**{f.name: getattr(factory, f.name) for f in fields(factory)})
        return replace(task, env_factory_builder=builder)
    monkeypatch.setattr(tasks, 'load_task', loading)
    out = tmp_path / 'out'
    run, state = execute(make_config(out, run=dict(max_evaluations=2)), out)
    events = [json.loads(line) for line in (run.logs / 'events.jsonl').read_text().splitlines()]
    said = [e for e in events if e['event'] == 'model_library']
    assert state == 'completed' and len(said) == 1 and said[0]['parts'] == {'tt': [3, 23]} and said[0]['trimmed']
