"""Running a Maestro-measured task (task flow part 5): Maestro's own deck of the working copy's test around the circuit
the run adapter exports, and the outputs measured with OCEAN on each run's results, their signal names translated by
Maestro's own name maps. FAKE netlister and a faked OCEAN answer - no Virtuoso, no simulation."""
import json
import os
from pathlib import Path
import sys
import types

import pytest

from gator_workbench import ocean, profiles, recipes, schema, tasks, virtuoso_setup as vs
from gator_workbench.spec_equations import SpecPlan
from gator_workbench.validation import validate
from helpers import bridge_is_importable  # noqa: F401 - an imported fixture belongs to this module
from task_save_support import config as cell_config, ready, save
from fakes_virtuoso import MAESTRO_HEAD, MAESTRO_TAIL, maestro_netlister
from fakes_virtuoso import SETUP, setup_writer
from task_save_support import saved_maestro_task

COMMAND = ('/opt/cadence/SPECTRE231/bin/spectre -64 /tmp/vb/15f61d39/input.scs +escchars +log /tmp/vb/15f61d39/spectre.out '
           '-format psfascii -raw /tmp/vb/15f61d39/input.raw +lqtimeout 900 -maxw 5 -maxn 5 +logstatus')


def amap(tmp_path):
    folder = tmp_path / 'amap'
    folder.mkdir()
    files = {'top_level_map.inst': [('__NEXT_FILE__', 'tb')], 'tb.inst': [('V0n', 'analogLib_vdc_spectre'), ('XU1n', 'ring')],
             'tb.net': [('gnd!v', '0v')], 'analogLib_vdc_spectre.inst': [('PLUSv', ':pv'), ('MINUSv', '(FUNCTION minus(root("PLUS")))v')],
             'ring.inst': [('MN1n MN2n', 'nmos'), ('OUTv', ':1v')], 'nmos.inst': [('Dv', ':dv')],
             '__simulator_information__': [('__artInstanceTerminalDelimiter__', ':'), ('__artHierarchyDelimiter__', '.')]}
    for name, pairs in files.items():
        (folder / name).write_text('HEADER\n"PSFversion" "1.00"\n' + ''.join('"%s" "%s"\n' % (k, v.replace('"', '\\"')) for k, v in pairs))
    return ocean.Names(folder)


def test_signal_names_are_translated_by_the_netlist_s_own_maps(tmp_path):
    names = amap(tmp_path)
    assert ocean.translate('frequency(VT("/OUT"))', names) == 'frequency(VT("OUT"))'
    assert ocean.translate('ymax(VT("/XU1/N1")) - ymin(VT("/XU1/N1"))', names) == 'ymax(VT("XU1.N1")) - ymin(VT("XU1.N1"))'
    assert ocean.translate('average(IT("/V0/PLUS"))', names) == 'average(IT("V0:p"))'
    assert ocean.translate('IT("/XU1/MN1/D")', names) == 'IT("XU1.MN1:d")'
    assert ocean.translate('VT("/gnd!")', names) == 'VT("0")'
    assert ocean.translate('OP("/XU1/MN2" "gm")', names) == 'OP("XU1.MN2" "gm")'
    assert ocean.translate('getData("/OUT" ?result "tran")', names) == 'getData("OUT" ?result "tran")'
    for expression, reason in (('IT("/V0/MINUS")', 'derived by the netlister'), ('VT("/XQ/N1")', 'XQ is not an instance'),
                               ('IT("/V0/NOPE")', 'NOPE is not a terminal of V0'), ('IT("/OUT")', 'names no terminal')):
        with pytest.raises(ocean.NameError_, match=reason):
            ocean.translate(expression, names)


def test_the_ocean_program_reads_one_result_folder_and_its_answer_is_parsed():
    assert ocean.remote_raw_dir(dict(spectre_command=COMMAND)) == '/tmp/vb/15f61d39/input.raw'
    with pytest.raises(ValueError, match='no result folder'):
        ocean.remote_raw_dir(dict(spectre_command='spectre -64 deck.scs'))
    with pytest.raises(ValueError, match='Unexpected result folder'):
        ocean.remote_raw_dir(dict(spectre_command='spectre -raw "/tmp/x y"'))
    outputs = [dict(name='freq', spectre_expression='frequency(VT("OUT"))', analysis='tran'),
               dict(name='gain', spectre_expression='dB20(VF("OUT"))', analysis='ac')]
    text = ocean.program('/tmp/vb/15f61d39/input.raw', outputs)
    assert text.count('openResults("/tmp/vb/15f61d39/input.raw")') == 1 and "selectResult('tran)" in text and "selectResult('ac)" in text
    assert 'car(errset(frequency(VT("OUT")) nil))' in text and 'simulator(' not in text and 'design(' not in text
    assert ocean.parse('freq=1209256473.1920419\ngain=nil\n', outputs) == dict(freq=1209256473.1920419, gain=None)
    with pytest.raises(ValueError):
        ocean.program('/tmp/x.raw', [dict(name='bad name', spectre_expression='1', analysis='tran')])


def test_a_client_for_ocean_leaves_the_bridge_variables_as_they_were(monkeypatch):
    fake = types.ModuleType('virtuoso_bridge')

    class Client:
        @classmethod
        def from_env(cls, **kwargs):
            os.environ['VB_ADDED_BY_LOADING'] = '1'                   # what loading an env file could do
            os.environ['VB_PROFILE_SEEN'] = 'changed'
            return cls()
    fake.VirtuosoClient = Client
    monkeypatch.setitem(sys.modules, 'virtuoso_bridge', fake)
    monkeypatch.setenv('VB_PROFILE_SEEN', 'as-bound')
    monkeypatch.setattr(ocean, '_CLIENTS', {})
    ocean._client(dict(profile=None, env_file='/x/.env'))
    assert 'VB_ADDED_BY_LOADING' not in os.environ and os.environ['VB_PROFILE_SEEN'] == 'as-bound'
    assert len(ocean._CLIENTS) == 1 and ocean._client(dict(profile=None, env_file='/x/.env')) is next(iter(ocean._CLIENTS.values()))


def test_maestro_s_deck_is_split_around_its_circuit():
    circuit = '\n// Library name: L\nsubckt ring OUT VDD VSS\n    MN1 (OUT A 0 0) g45n1svt w=1u\nends ring\nXU1 (OUT VDD 0) ring\n'
    head, tail = vs.split_deck(MAESTRO_HEAD + circuit + MAESTRO_TAIL, circuit)
    assert head.startswith(MAESTRO_HEAD) and 'tran tran stop=50n' in tail and 'MN1' not in head + tail
    assert vs.deck_include(head) == ('/pdk/model.scs', 'tt') and vs.deck_analyses(tail) == ['tran']
    with pytest.raises(vs.SetupError, match='exactly once'):
        vs.split_deck(MAESTRO_HEAD + circuit + circuit + MAESTRO_TAIL, circuit)
    with pytest.raises(vs.SetupError, match='simulator line or its model include'):
        vs.split_deck('global 0\n' + circuit + MAESTRO_TAIL, circuit)


def test_the_profile_runs_maestro_s_deck_around_the_export_and_measures_with_ocean(tmp_path, monkeypatch):
    saved_maestro_task(tmp_path)
    profile = profiles.load_profile('ring_maestro')
    assert isinstance(profile, recipes.GenericMaestroProfile) and profile.deck_name == 'input.scs'
    deck = profile.build_deck('XU1 (OUT VDD 0) ring_osc_3stage\n', '/pdk/model.scs', 'tt')
    assert deck.startswith('// Generated for: spectre') and 'XU1 (OUT VDD 0) ring_osc_3stage\n' in deck and deck.rstrip().endswith('save=allpub')
    with pytest.raises(recipes.RulesError, match='the connection names /other/model.scs'):
        profile.build_deck('X', '/other/model.scs', 'tt')
    settings = profile.analysis_settings
    assert settings['recipe'] == 'maestro' and [o['expression'] for o in settings['outputs']] == ['frequency(VT("OUT"))', 'ymax(VT("OUT"))']
    job = tmp_path / 'job'
    (job / 'results').mkdir(parents=True)
    (job / 'results' / 'spectre.out').write_text('spectre completes with 0 errors, 0 warnings, and 0 notices.\n')
    result = dict(job_id='j1', analysis_settings=settings, status='success', errors=[], condition=dict(purpose='nominal', monte_carlo=None),
                  metadata=dict(returncode=0, spectre_command=COMMAND))
    (job / 'bridge_result.json').write_text(json.dumps(result))
    asked = []
    monkeypatch.setattr(ocean, 'measure', lambda bridge, raw, outputs, client=None: asked.append((bridge, raw, [o['name'] for o in outputs]))
                        or dict(freq=1.2e9, vmax=None))
    monkeypatch.setattr('analog_optimizer.backends.spectre_validation.validate_completion', lambda *a, **k: dict(ok=True))
    profile.bridge = dict(profile='lab', env_file='/x/.env')
    measured = profile.analyze(job, mos_names=profile.mos_names)
    assert asked == [(dict(profile='lab', env_file='/x/.env'), '/tmp/vb/15f61d39/input.raw', ['freq', 'vmax'])]
    assert measured['metrics'] == dict(freq=1.2e9, vmax=None) and measured['metric_units'] == dict(freq='Hz', vmax='V')
    assert measured['metric_validity'] == dict(freq=True, vmax=False) and measured['operating_points'] == {}
    assert json.loads((job / 'measurements.json').read_text())['results_on_host'] == '/tmp/vb/15f61d39/input.raw'
    (job / 'bridge_result.json').write_text(json.dumps(dict(result, analysis_settings=dict(settings, deck_sha256='other'))))
    with pytest.raises(ValueError, match='differs from the one the executed netlist was built with'):
        profile.analyze(job)


def test_a_task_saved_before_it_has_no_deck_still_opens_and_says_what_to_do(tmp_path):
    saved_maestro_task(tmp_path)
    entry = profiles.list_profiles()['ring_maestro']
    (Path(entry['directory']) / profiles.FILES['maestro_deck']).unlink()
    profile = profiles.load_profile('ring_maestro')                      # opens: the deck is read only when a run needs it
    with pytest.raises(recipes.RulesError, match='press Save task once'):
        profile.build_deck('X', '/pdk/model.scs', 'tt')


def test_a_maestro_task_s_outputs_are_results_for_validation_and_the_specs(tmp_path):
    cfg = saved_maestro_task(tmp_path)
    runtime = tasks.load_task(cfg.circuit)
    report = validate(cfg, provided_metrics=set(runtime.provided_metrics)).as_dict()
    codes = {i['code'] for i in report['issues']}
    assert 'ade_outputs_not_wired' not in codes and 'spec_name_is_a_result' not in codes and 'metric_not_provided' not in codes
    draft = cell_config(probes=vs.to_rows(SETUP)['measurements'], specs=[])
    assert 'ade_outputs_not_wired' in {i['code'] for i in validate(draft, provided_metrics=set()).as_dict()['issues']}
    plan = SpecPlan.from_config(cfg)
    probes = plan.probe_values(dict(freq=1.2e9, vmax=1.0))
    assert probes['m_freq'] == 1.2e9 and probes['m_vmax'] == 1.0                   # read from the measured results, by output name
    assert any(s.spec_id == 'freq' and s.result_backed for s in plan.specs)


class RecordingClient:
    """Answers the SKILL calls of bridge_setup's Maestro functions with plausible values and records them."""
    def __init__(self, mode='Spectre'):
        self.calls, self.mode = [], mode

    def execute_skill(self, text, timeout=60):
        self.calls.append(text)
        answers = [('maeOpenSetup', '"fnxSession1"'), ('?typeName "tests"', '("GATOR")'), ("'uniMode) ", f'"{self.mode}"'),
                   ('maeGetEnabledAnalysis', '("tran")'), ('maeGetAnalysis', '(("stop" "50n"))'), ('?typeName "variables"', 'nil'),
                   ('maeGetTestOutputs', '""'), ('modelFiles', '(("/pdk/model.scs" "tt"))'), ('ddGetObj', '"yes"')]
        output = next((value for key, value in answers if key in text), 't')
        return types.SimpleNamespace(ok=True, errors=[], output=output)


def test_the_task_s_maestro_test_runs_plain_spectre_like_the_optimizer(monkeypatch):
    from gator_workbench import bridge_setup
    fake = types.ModuleType('virtuoso_bridge')
    fake.decode_skill_output = lambda text: text
    monkeypatch.setitem(sys.modules, 'virtuoso_bridge', fake)
    client = RecordingClient()
    setup = vs.normalize(dict(SETUP, analyses={'tran': {'stop': '50n'}}))
    bridge_setup.write_maestro(client, 'L_GATOR', 'tb', setup)
    [mode] = [i for i, text in enumerate(client.calls) if "asiSetHighPerformanceOptionVal(th 'uniMode \"Spectre\")" in text]
    [saved] = [i for i, text in enumerate(client.calls) if text.startswith('maeSaveSetup')]
    assert mode < saved                                                        # set before the setup is saved
    assert bridge_setup.read_maestro(RecordingClient(mode='APS'), 'L_GATOR', 'tb', test='GATOR')['simulator_mode'] == 'APS'
    told = vs.differences(dict(SETUP), dict(SETUP, simulator_mode='APS'))
    assert 'Simulator mode: the task says Spectre, Virtuoso has APS' in told
    assert vs.differences(dict(SETUP), dict(SETUP)) == [] and vs.normalize(dict(SETUP))['simulator_mode'] == vs.SIMULATOR_MODE
