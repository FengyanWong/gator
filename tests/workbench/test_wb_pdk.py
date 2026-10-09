"""Load PDK: every component of one PDK becomes known to the network, without touching src/analog_optimizer.

The PDK here is the invented `demo045` (tests/workbench/fixtures/pdk_demo): model files in Spectre syntax and the
query output of its "CDF", in the exact form the bridge returns it (backslashes doubled). No real PDK file is copied.
`ideal.txt` is the same kind of answer for an invented generic library read with it (a few cells shaped like analogLib's:
sources that share one Spectre component with two pin orders, ideal R / C / L, a probe, a controlled source).
Everything is MOCK: the analytic toy backend, no Virtuoso, no Spectre.
"""
import json
from pathlib import Path

import pytest

from gator_workbench import checkpoints as ckpt, pdk, runs, schema, task_registry, tasks, validation
from gator_workbench.storage import read_json
from helpers import execute, make_config, roots_for, run_prepared, SMALL_NET, workbench_app
from pdk_support import FIXTURE, raw_material
from gator_workbench import pdk_record
import re
import shutil
from pdk_support import demo_config, load_demo, parser_config

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.


@pytest.fixture
def demo_task(tmp_path, monkeypatch):
    """A MOCK registered task on the demo circuit (analytic toy score), with demo045 loaded in this test's settings."""
    record = load_demo()
    mapping = parser_config(tmp_path, record)
    monkeypatch.setitem(task_registry.SYNTHETIC_FIXTURES, 'pdk_demo', dict(netlist=str(FIXTURE / 'demo_circuit.scs'),
                                                                   config=str(mapping), circuit_class='opamp'))
    return record


# ------------------------------------------------------------------------------------------ reading the PDK
def test_every_component_is_classified_from_the_model_files_with_its_pins():
    record = load_demo()
    devices = record['devices']
    assert sorted(devices) == ['dm_dio', 'dm_ind', 'dm_mim', 'dm_ncap', 'dm_nch', 'dm_npn', 'dm_pch', 'dm_rpoly']
    facts = {m: (d['family'], d['polarity'], [p['role'] for p in d['pins']]) for m, d in devices.items()}
    assert facts['dm_nch'] == ('mos', 'n', ['drain', 'gate', 'source', 'bulk'])      # gate reached through the gate resistor
    assert facts['dm_pch'] == ('mos', 'p', ['drain', 'gate', 'source', 'bulk'])
    assert facts['dm_ncap'] == ('mos', 'n', ['drain', 'gate', 'source', 'bulk'])     # type=n from a binned top-level card
    assert facts['dm_npn'] == ('bjt', 'npn', ['collector', 'base', 'emitter', 'bulk'])
    assert facts['dm_dio'] == ('diode', None, ['anode', 'cathode'])
    assert facts['dm_rpoly'] == ('resistor', None, ['positive', 'negative', 'bulk'])  # diodes to the body do not count
    assert facts['dm_ind'][0] == 'inductor' and facts['dm_mim'][0] == 'capacitor'
    assert all(not d['problems'] for d in devices.values())
    assert devices['dm_nch']['cells'] == ['nmos', 'nmos_3']                          # the 4-pin cell names the pins
    assert [p['name'] for p in devices['dm_nch']['pins']] == ['D', 'G', 'S', 'B']
    assert devices['dm_rpoly']['netlisted_through'] == ['primres3'] and devices['dm_rpoly']['cells'] == ['rpoly']
    assert {c['cell'] for c in record['not_netlisted']} == {'guard', 'primres3'}
    assert record['layout_only'] == [dict(cell='xcross', views=['layout'])]
    assert 'dm_rg' in record['model_file_definitions_not_used']                     # a building block no cell uses
    standard = {m: (d['standard_kind'], d['standard_roles']) for m, d in devices.items()}
    assert standard['dm_nch'] == ('nmos', ['drain', 'gate', 'source', 'bulk'])
    assert standard['dm_npn'] == ('unknown', ['unknown'] * 4)                         # the standard list has no bipolar kind


def test_a_diode_wrapped_with_its_series_resistance_is_a_diode():
    """Some PDKs place a diode inside a subcircuit with its series resistance; the element is not named after the
    subcircuit, so the inline rule does not see it. Invented definitions, shaped like such a wrapper."""
    scan = pdk.scan_model_text('\n'.join([
        'simulator lang=spectre',
        'inline subckt dm_sdio (1 2)', 'parameters area=1e-10 rs=1e-6', '  r1 (1 3) resistor r=rs/area', '  diode (3 2) dm_dcore area=area', 'ends dm_sdio',
        'subckt dm_rdio (k a)', '  r1 (k n1) resistor r=10', '  d1 (a n1) dm_dcore', 'ends dm_rdio',           # cathode pin first
        'subckt dm_pdio (a c)', '  d1 (a c) dm_dcore', 'ends dm_pdio',                                           # no resistance at all
        'subckt dm_bdio (a c body)', '  r1 (a n1) resistor r=10', '  d1 (n1 c) dm_dcore', '  d2 (body n1) dm_dcore', 'ends dm_bdio',
        'subckt dm_rpar (n1 n2)', '  r1 (n1 n2) resistor r=1k', '  d1 (n1 n2) dm_dcore', 'ends dm_rpar',     # a path without the diode
        'subckt dm_2dio (a c)', '  d1 (a n1) dm_dcore', '  d2 (n1 c) dm_dcore', 'ends dm_2dio',                # two diodes in series
        'model dm_dcore diode is=1e-15']), '/pdk/demo/wrapped.scs')

    def facts(name):
        found = pdk.classify_model(name, scan)
        return found['family'], [p['role'] for p in pdk.pin_roles(name, found, scan)]
    assert facts('dm_sdio') == ('diode', ['anode', 'cathode'])          # the first pin reaches the anode through r1
    assert facts('dm_rdio') == ('diode', ['cathode', 'anode'])
    assert facts('dm_pdio') == ('diode', ['anode', 'cathode'])
    assert facts('dm_bdio')[0] == 'diode'                                # a diode to the body is not on the path
    assert 'with only resistance in series' in pdk.classify_model('dm_sdio', scan)['family_basis']
    assert facts('dm_rpar')[0] == 'other' and facts('dm_2dio')[0] == 'other'


def test_parameters_get_units_scales_and_columns_by_rule():
    record = load_demo()

    def param(model, name):
        return next(p for p in record['devices'][model]['parameters'] if p['name'] == name)
    w = param('dm_nch', 'w')
    assert (w['cdf'], w['unit'], w['unit_declared'], w['column'], w['reference'], w['action_class']) == ('simW', 'm', True, 'w', 1e-6, 'w')
    assert param('dm_nch', 'm')['unit'] == 'count' and param('dm_nch', 'nf')['action_class'] == 'nf'
    assert not param('dm_nch', 'region')['numeric'] and not param('dm_nch', 'trise')['numeric']
    radius = param('dm_ind', 'r')                     # an inductor's r is its RADIUS, not the standard resistance
    assert (radius['canonical'], radius['column'], radius['unit'], radius['action_class']) == ('rad', 'rad', 'm', 'l')
    assert param('dm_ind', 'w')['default'] == pytest.approx(3e-6)          # iPar -> a cyclic's default
    assert param('dm_ind', 'nr')['action_class'] is None                     # no declared unit: the row must state one
    assert param('dm_npn', 'area')['column'] == 'bjt.area' and param('dm_dio', 'area')['column'] == 'diode.area'
    assert param('dm_rpoly', 'l')['default'] == pytest.approx(8e-6)          # pPar -> the cell that places the primitive
    assert param('dm_mim', 'ic')['unit'] == 'V' and param('dm_mim', 'ic')['action_class'] == 'dc'
    vocabulary = record['vocabulary']
    standard = pdk.standard_schema()
    assert vocabulary['parameters'][:8] == list(standard.parameters) and vocabulary['references'][:8] == list(standard.references)
    assert vocabulary['device_kinds'][:8] == list(standard.device_kinds)
    assert vocabulary['terminal_roles'][:7] == list(standard.terminal_roles)
    assert {'anode', 'cathode', 'collector', 'base', 'emitter'} <= set(vocabulary['terminal_roles'])


def test_the_component_list_is_deterministic_and_named_by_its_content():
    first, second = load_demo(), load_demo()
    assert first['sha256'] == second['sha256'] and first['vocabulary']['version'] == f"pdk-demo045-{first['sha256'][:16]}"
    shuffled = raw_material()                       # the library may list its cells in any order, and lines may come mixed
    shuffled['cdf_text'] = '\n'.join(reversed(shuffled['cdf_text'].splitlines()))
    assert pdk.build_record('demo045', pdk.parse_cdf_text(shuffled['cdf_text']), shuffled['scans'])['sha256'] == first['sha256']
    versions = list((pdk.pdk_dir('demo045') / 'versions').glob('*.json'))
    assert [v.stem for v in versions] == [first['sha256']]
    assert pdk.list_pdks()[0]['label'].startswith('PDK demo045 (8 components, version ')


def test_the_skill_output_parser_reads_the_bridge_form():
    assert pdk.skill_value(r'(nil D \\:d G \\:g)') == [None, 'D', ':d', 'G', ':g']
    assert pdk.skill_value(r'"iPar(\\"w\\")"') == 'iPar("w")'
    assert pdk.skill_value('(1 2.5 t nil "x y")') == [1, 2.5, True, None, 'x y']
    assert pdk.query_fields('PARAM|c|p|"a | b"|nil') == ['PARAM', 'c', 'p', '"a | b"', 'nil']


def test_reading_downloads_into_a_temporary_folder_and_follows_includes(tmp_path):
    seen, folders = [], []

    class Result:
        def __init__(self, ok=True, output='', errors=()):
            self.ok, self.output, self.errors = ok, output, list(errors)

    class FakeClient:
        ideal = 'ok'

        def execute_skill(self, text, timeout):
            if 'ddGetObj("analogLib")' in text:           # the ideal parts: one more query, which opens nothing
                assert 'dbOpen' not in text and 'PARAM' not in text
                return Result(output=(FIXTURE / 'ideal.txt').read_text()) if self.ideal == 'ok' else Result(
                    ok=False, errors=['*Error* the session is busy'])
            assert 'ddGetObj("demo045")' in text and 'dbClose' in text
            return Result(output=(FIXTURE / 'cdf.txt').read_text())

        def download_file(self, remote, local, timeout=None):
            seen.append(remote)
            folders.append(Path(local).parent)
            Path(local).write_bytes((FIXTURE / 'models' / Path(remote).name).read_bytes())
            return Result()
    raw = pdk.read_from_virtuoso(FakeClient(), technology_library='demo045', model_file='/pdk/demo045/models/demo045.scs',
                                 decode=lambda text: text)
    assert seen == ['/pdk/demo045/models/demo045.scs', '/pdk/demo045/models/demo045_mos.scs',
                    '/pdk/demo045/models/demo045_passive.scs']
    assert not folders[0].exists() and not str(folders[0]).startswith(str(Path(__file__).parents[2]))
    assert [s['sha256'] for s in raw['sources']['model_files']] and pdk.finish_load(raw)['summary']['devices'] == 8
    assert raw['ideal']['library'] == 'analogLib' and raw['ideal']['cdf_text'].startswith('CELL|vdc|')   # read in the same press
    assert pdk.load_record('demo045')['ideal_parts']['summary']['components'] == 10
    with pytest.raises(ValueError):
        pdk.read_from_virtuoso(FakeClient(), technology_library='demo045', model_file='relative/x.scs', decode=lambda t: t)
    # The ideal parts can never cost the PDK: a failed query is a reason beside a PDK that is read and stored all the same,
    # and what an earlier read brought is kept.
    busy = FakeClient()
    busy.ideal = 'fail'
    raw = pdk.read_from_virtuoso(busy, technology_library='demo045', model_file='/pdk/demo045/models/demo045.scs', decode=lambda text: text)
    assert raw['ideal'] == dict(library='analogLib', error='*Error* the session is busy')
    kept = pdk.finish_load(raw)['ideal_parts']
    assert kept['summary']['components'] == 10 and kept['not_read_again'] == '*Error* the session is busy'


# ------------------------------------------------------------------------------------------ the network
def test_the_network_view_relabels_pdk_devices_and_leaves_the_task_graph_alone(demo_task):
    vocabulary = pdk.vocabulary_of_record(demo_task)
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='synthetic:pdk_demo'))
    graph = runtime.base_graph
    assert graph.complete and {d.id: d.kind for d in graph.devices}['XU1/Q1'] == 'unknown'
    assert 'rad' in graph.parameters['XU1/L1'] and graph.parameters['XU1/L1']['rad'].source_name == 'r'
    seen = vocabulary.view_graph(graph)
    kinds = {d.id: d.kind for d in seen.devices}
    assert kinds['XU1/M1'] == 'demo045:dm_nch' and kinds['XU1/Q1'] == 'demo045:dm_npn' and kinds['VDD'] == 'vsource'
    roles = {(c.device_id, c.terminal): c.role for c in seen.connections}
    assert roles[('XU1/Q1', 'B')] == 'base' and roles[('XU1/D1', 'PLUS')] == 'anode' and roles[('VIN', 'PLUS')] == 'positive'
    assert 'bjt.area' in seen.parameters['XU1/Q1'] and 'area' in graph.parameters['XU1/Q1']
    assert {d.id: d.kind for d in graph.devices}['XU1/M1'] == 'nmos'             # the task graph itself is unchanged
    from analog_optimizer.graph.pyg_converter import to_pyg
    data = to_pyg(seen, vocabulary.schema)
    assert tuple(data['device'].x.shape) == (len(graph.devices), len(vocabulary.schema.parameters))
    with pytest.raises(ValueError):
        to_pyg(seen)                                  # the standard list cannot even read the relabelled graph


def test_the_learner_acts_learns_saves_and_loads_only_with_its_own_list(demo_task, tmp_path):
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.replay import ReplayBuffer, Transition
    from analog_optimizer.training.sac import SACLearner
    vocabulary = pdk.vocabulary_of_record(demo_task)
    config = demo_config(tmp_path)
    runtime = tasks.load_task(config.circuit)
    from gator_workbench.compile import compile_task
    compiled = compile_task(config, runtime.base_graph)
    assert {g.id: (g.parameter_kind, g.unit) for g in compiled.graph.parameter_groups} == {
        'input_w': ('w', 'm'), 'input_nf': ('nf', '1'), 'coil_radius': ('l', 'm')}     # a count is '1' for the optimizer
    factory = tasks.SyntheticEnvFactory(compiled.graph, compiled.specs, dict(tasks.MOCK_TARGETS), str(tmp_path / 'work'), 3, 30.0, False)
    experiment = dict(origin='synthetic', split='train', designs=['demo'])
    net = ModelConfig(hidden_dim=16, heads=2, layers=1)
    learner = pdk.learner_class(vocabulary)(experiment=experiment, model_config=net, feature_schema=vocabulary.schema)
    replay = ReplayBuffer(32, origin='synthetic', seed=1)
    with factory(0) as env:
        observation, _ = env.reset()
        for step in range(8):
            proposal = learner.act([observation])[0]
            following, reward, terminated, truncated, info = env.step(proposal)
            if info['replay_eligible']:
                applied = following.graph.assignments({g.id: g.value for g in following.graph.parameter_groups if g.mutable})
                replay.add(Transition(observation, proposal, reward, following, terminated, truncated, not terminated,
                                      applied, f'c{step}', 'memory'))
            observation = env.reset()[0] if terminated or truncated else following
    assert learner.update(replay.sample(4))['updates'] == 1
    learner.save(tmp_path / 'state.pt', replay)
    loaded, _, _ = pdk.learner_class(vocabulary).load(tmp_path / 'state.pt', experiment=experiment, model_config=net,
                                                      feature_schema=vocabulary.schema)
    assert loaded.contract() == learner.contract() and loaded.contract()['feature_schema']['version'] == vocabulary.version
    with pytest.raises(ValueError, match='mismatch'):
        SACLearner.load(tmp_path / 'state.pt', experiment=experiment, model_config=net)


def test_the_pdk_view_learner_takes_lent_replay_samples_like_copied_ones(demo_task, tmp_path):
    """Record 7.221: ReplayBuffer.update_learner hands a PdkViewLearner the stored transitions plus their digests; the
    view makes new objects, so the learner keys them by their own content - same updates as from copied samples."""
    import torch
    from analog_optimizer.models import ModelConfig
    from analog_optimizer.training.replay import ReplayBuffer, Transition
    vocabulary = pdk.vocabulary_of_record(demo_task)
    config = demo_config(tmp_path)
    runtime = tasks.load_task(config.circuit)
    from gator_workbench.compile import compile_task
    compiled = compile_task(config, runtime.base_graph)
    factory = tasks.SyntheticEnvFactory(compiled.graph, compiled.specs, dict(tasks.MOCK_TARGETS), str(tmp_path / 'work'), 3, 30.0, False)
    experiment = dict(origin='synthetic', split='train', designs=['demo'])
    net = ModelConfig(hidden_dim=16, heads=2, layers=1)
    learners = []
    for _ in range(2):
        torch.manual_seed(4)
        learners.append(pdk.learner_class(vocabulary)(experiment=experiment, model_config=net, feature_schema=vocabulary.schema))
    replays = [ReplayBuffer(32, origin='synthetic', seed=1) for _ in range(2)]
    with factory(0) as env:
        observation, _ = env.reset()
        for step in range(8):
            proposal = learners[0].act([observation], deterministic=True)[0]
            following, reward, terminated, truncated, info = env.step(proposal)
            if info['replay_eligible']:
                applied = following.graph.assignments({g.id: g.value for g in following.graph.parameter_groups if g.mutable})
                for replay in replays:
                    replay.add(Transition(observation, proposal, reward, following, terminated, truncated, not terminated,
                                          applied, f'c{step}', 'memory'))
            observation = env.reset()[0] if terminated or truncated else following
    for _ in range(3):
        before = torch.get_rng_state()
        expected = learners[1].update(replays[1].sample(4))
        torch.set_rng_state(before)
        assert replays[0].update_learner(learners[0], 4) == expected
    for a, b in zip(learners[0].actor.parameters(), learners[1].actor.parameters()):
        assert torch.equal(a, b)


# ------------------------------------------------------------------------------------------ configuration and checks
def test_the_standard_list_keeps_every_existing_hash(tmp_path):
    config = make_config(tmp_path)
    assert config.run.network.vocabulary == 'standard'
    dumped = config.model_dump(mode='json')
    before = json.loads(json.dumps(dumped))
    del before['run']['network']['vocabulary']                     # a configuration written before the field existed
    assert schema.config_hash(dumped) == schema.config_hash(before)
    assert schema.config_hash(schema.WorkbenchConfig.model_validate(before)) == schema.config_hash(config)
    other = config.model_copy(deep=True)
    other.run.network.vocabulary = 'pdk:demo045'
    assert schema.config_hash(other) != schema.config_hash(config)
    assert schema.task_definition_hash(other) == schema.task_definition_hash(config)   # the task is the same task


def test_validation_lets_pdk_parameters_vary_only_under_the_pdk_list(demo_task, tmp_path):
    runtime = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='synthetic:pdk_demo'))

    def issues(config):
        report = validation.validate(config, graph=runtime.base_graph, provided_metrics=set(runtime.provided_metrics))
        return {(i.code, i.level): i.message for i in report.issues}
    under_pdk = issues(demo_config(tmp_path))
    assert not [key for key in under_pdk if key[1] in ('error', 'blocker')], under_pdk
    assert ('pdk_vocabulary', 'info') in under_pdk
    standard = issues(demo_config(tmp_path, vocabulary='standard'))
    message = standard[('parameter_kind_unsupported', 'blocker')]
    assert "'rad'" in message and 'choose the component list "PDK demo045"' in message

    def with_row(row, vocabulary='pdk:demo045'):
        return demo_config(tmp_path, vocabulary, mutate=lambda raw: raw['parameters'].append(row))
    area = issues(with_row(dict(variable_id='bjt_area', instance_path='XU1/Q1', parameter_name='area', unit='1',
                                lower=4, upper=100)))
    assert ('pdk_unit_undeclared', 'warning') in area and not [k for k in area if k[1] in ('error', 'blocker')]
    wrong = issues(with_row(dict(variable_id='coil_r', instance_path='XU1/L1', parameter_name='rad', unit='ohm',
                                 lower=1, upper=2)))
    assert ('unit_mismatch', 'error') in wrong and 'declared by the PDK' in wrong[('unit_mismatch', 'error')]
    region = issues(with_row(dict(variable_id='region', instance_path='XU1/M1', parameter_name='region', unit='1',
                                  lower=0, upper=1)))
    assert ('pdk_parameter_not_numeric', 'blocker') in region
    missing = demo_config(tmp_path, 'pdk:nothere')
    assert ('pdk_not_loaded', 'blocker') in issues(missing)
    assert ('pdk_not_in_circuit', 'warning') not in under_pdk
    toy = make_config(tmp_path, run=dict(network=dict(SMALL_NET, vocabulary='pdk:demo045')))     # the MOCK op-amp: no demo045 part
    toy_runtime = tasks.load_task(toy.circuit)
    toy_issues = {i.code for i in validation.validate(toy, graph=toy_runtime.base_graph, provided_metrics=set(toy_runtime.provided_metrics)).issues}
    assert 'pdk_not_in_circuit' in toy_issues and 'pdk_vocabulary' in toy_issues


def test_the_api_lists_shows_and_loads_a_pdk(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from gator_workbench import bridge_read
    from gator_workbench.api import create_app
    calls = []

    def fake_read(monitor, profile_id, op, **kwargs):
        calls.append((profile_id, op, kwargs))
        return pdk.describe(pdk.finish_load(raw_material()))
    monkeypatch.setattr(bridge_read, 'read', fake_read)
    client = TestClient(workbench_app(tmp_path))
    assert client.get('/api/pdks').json()['pdks'] == []
    loaded = client.post('/api/pdks/load', json=dict(profile_id='lab', technology_library='demo045')).json()
    assert calls == [('lab', 'pdk', dict(library='demo045', model_file=None))]
    assert loaded['summary']['devices'] == 8 and len(loaded['devices']) == 8
    assert loaded['ideal_parts']['summary']['recognized'] == 8 and len(loaded['ideal_parts']['components']) == 10   # shown with the PDK
    listed = client.get('/api/pdks').json()
    assert listed['pdks'][0]['ideal_parts']['library'] == 'analogLib' and 'components' not in listed['pdks'][0]['ideal_parts']
    assert [p['vocabulary'] for p in listed['pdks']] == ['pdk:demo045'] and listed['standard']['vocabulary'] == 'standard'
    assert client.get('/api/pdks/demo045').json()['sha256'] == loaded['sha256']
    assert client.get('/api/pdks/unknown').status_code == 404
    assert client.post('/api/pdks/load', json=dict(profile_id='lab', technology_library='bad name')).status_code == 422


# ------------------------------------------------------------------------------------------ the ideal parts
def test_load_pdk_reads_what_the_generic_library_says_about_its_parts():
    parts = load_demo()['ideal_parts']
    assert parts['library'] == 'analogLib' and parts['format'] == pdk.IDEAL_FORMAT and len(parts['sha256']) == 64
    assert parts['summary'] == dict(cells=16, components=10, recognized=8, as_unknown=2, without_pins=['mutual_inductor', 'nport'],
                                    with_a_kind=['capacitor', 'inductor', 'iprobe', 'isource', 'resistor', 'vsource'])
    source = parts['components']['vsource']                    # three cells netlist one component, with two pin orders
    assert source['cells'] == ['vdc', 'vpulse', 'vsource'] and source['kind'] == 'vsource' and source['parameters'] == {'dc': 'dc'}
    assert [(o['pins'], o['cells']) for o in source['pin_orders']] == [
        (['PLUS', 'MINUS'], ['vdc', 'vpulse']), (['PLUS', 'MINUS', 'P1', 'M1', 'P2', 'M2'], ['vsource'])]
    assert parts['components']['inductor']['parameters'] == {'l': 'ind'}          # `l` on an inductor's line is no length
    assert parts['components']['iprobe']['kind'] == 'vsource' and '0 V source' in parts['components']['iprobe']['basis']
    assert parts['components']['vcvs']['kind'] == 'unknown' and parts['components']['vcvs']['pin_orders'][0]['pins'] == ['PLUS', 'MINUS', 'NC+', 'NC-']
    assert parts['components']['winding']['pin_orders'][0]['pins'] == ['t', 'b']    # a pin called t is not SKILL's truth value
    assert parts['components']['mutual_inductor']['pin_orders'] == [] and parts['components']['mutual_inductor']['cells_without_pin_order'] == ['mind']
    assert parts['components']['nport']['pin_orders'] == [] and parts['components']['nport']['cells_with_too_many_pins'] == ['bigport']
    assert parts['not_components'] == [dict(cell='nmos4', reason='netlists with a model named on the instance'),
                                       dict(cell='title', reason='no Spectre entry (not netlisted)')]
    assert parts['layout_only'] == [dict(cell='gnd', views=['symbol'])]


def test_an_ideal_part_is_read_with_the_pin_order_that_fits_the_netlist():
    record = load_demo()
    models = pdk.ideal_models(record)                             # without a netlist: the order most cells state
    assert models['vsource'] == dict(kind='vsource', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'dc': 'dc'})
    assert models['inductor'] == dict(kind='inductor', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'l': 'ind'})
    assert models['iprobe'] == dict(kind='vsource', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={})
    assert models['vcvs'] == dict(kind='unknown', terminals=['PLUS', 'MINUS', 'NC+', 'NC-'], roles=['unknown'] * 4, parameters={})
    assert 'mutual_inductor' not in models and 'nport' not in models
    counted = pdk.ideal_models(record, dict(vsource={6}, resistor={3}, capacitor={2, 3}, inductor={4}, isource={2}))
    assert counted['vsource'] == dict(kind='unknown', terminals=['PLUS', 'MINUS', 'P1', 'M1', 'P2', 'M2'], roles=['unknown'] * 6, parameters={})
    assert counted['resistor'] == dict(kind='unknown', terminals=['t1', 't2', 't0'], roles=['unknown'] * 3, parameters={})
    assert counted['isource']['kind'] == 'isource'
    assert sorted(counted) == ['isource', 'resistor', 'vsource']     # lines of two lengths, or of a length no cell states: no mapping
    assert pdk.ideal_models(None) == {} and pdk.ideal_models(dict(ideal_parts=dict(error='not read', components={}))) == {}


def test_a_pdk_loaded_before_the_ideal_parts_were_read_says_so_and_changes_nothing(tmp_path):
    record = load_demo()
    old = {k: v for k, v in record.items() if k != 'ideal_parts'}                 # as every record stored before 7.190
    assert pdk.describe(old)['ideal_parts'] is None and pdk.ideal_models(old) == {}
    raw = raw_material()
    del raw['ideal']                                                              # an older reader's answer
    assert pdk.finish_load(raw)['ideal_parts']['summary']['components'] == 10      # what was read before is kept
    described = pdk.describe(pdk.load_record('demo045'), brief=True)['ideal_parts']
    assert described['not_read_again'].startswith('this read did not ask for them') and 'components' not in described


def test_a_cell_s_ideal_parts_are_recognized_from_what_was_read_with_its_pdk():
    from gator_workbench import native_cells
    text = (FIXTURE / 'demo_circuit.scs').read_text() + ('LX (VOUT 0) inductor l=2n\nEX (VOUT 0 VIN 0) vcvs gain=10\n'
                                                           'IX (VDD VOUT) isource dc=10u\nRX (VOUT 0) resistor r=1K\n')
    load_demo()
    mapping, unverified, origin = native_cells._mapping(text, technology_library='demo045')
    assert unverified == [] and origin['inductor'] == origin['vcvs'] == 'ideal' and origin['dm_npn'] == 'pdk'
    assert mapping['models']['inductor'] == dict(kind='inductor', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'l': 'ind'})
    assert mapping['models']['vcvs']['terminals'] == ['PLUS', 'MINUS', 'NC+', 'NC-'] and mapping['models']['vcvs']['kind'] == 'unknown'
    # A part the project had verified keeps the very pin names its saved tasks have: a current source's are p and n there,
    # whatever the library calls them, so no saved task's circuit description changes.
    assert origin['isource'] == origin['resistor'] == origin['vsource'] == 'verified'
    assert mapping['models']['isource']['terminals'] == ['p', 'n'] and mapping['models']['resistor']['terminals'] == ['p', 'n']
    sha = pdk.load_record('demo045')['ideal_parts']['sha256'][:12]
    assert mapping['mapping_version'].startswith('native-draft-1+pdk-demo045-') and mapping['mapping_version'].endswith(f'+ideal-analogLib-{sha}')
    from analog_optimizer.netlist.config import DeviceMapping, ParserConfig
    from analog_optimizer.netlist.spectre_parser import SpectreParser
    config = ParserConfig(models={name: DeviceMapping(kind=m['kind'], terminals=tuple(m['terminals']), roles=tuple(m['roles']),
                                                       parameters=m['parameters']) for name, m in mapping['models'].items()})
    graph = SpectreParser(config).parse_text(text, source='<test>', circuit_id='demo')
    kinds = {d.id: d.kind for d in graph.devices}
    assert kinds['LX'] == 'inductor' and kinds['EX'] == 'unknown' and graph.parameters['LX']['ind'].value == pytest.approx(2e-9)
    # Without the PDK - and the library read with it - the same cell keeps its unrecognized parts, by name.
    assert native_cells.build_mapping(text)[1] == ['dm_dio', 'dm_ind', 'dm_mim', 'dm_ncap', 'dm_nch', 'dm_npn', 'dm_pch', 'dm_rpoly', 'inductor', 'vcvs']
    # A description is used only for lines it fits: a six-node source is the library's six-pin part, and lines of two
    # lengths under one component are left unrecognized instead of stopping the parser.
    six = text.replace('VIN (VIN 0) vsource dc=0.5', 'VIN (VIN 0 a b c d) vsource type=prbs').replace('VDD (VDD 0) vsource dc=1.0', 'VDD (VDD 0 e f g h) vsource type=prbs')
    mapping, unverified, origin = native_cells._mapping(six, technology_library='demo045')
    assert origin['vsource'] == 'ideal' and mapping['models']['vsource']['terminals'] == ['PLUS', 'MINUS', 'P1', 'M1', 'P2', 'M2'] and unverified == []
    mixed = text.replace('VIN (VIN 0) vsource dc=0.5', 'VIN (VIN 0 a b c d) vsource type=prbs')
    assert native_cells._mapping(mixed, technology_library='demo045')[1] == ['vsource']


def test_a_cell_read_from_virtuoso_parses_its_pdk_components_once_the_pdk_is_loaded():
    from gator_workbench import native_cells
    text = (FIXTURE / 'demo_circuit.scs').read_text()
    _, unverified = native_cells.build_mapping(text)
    assert 'dm_npn' in unverified and 'dm_nch' in unverified
    load_demo()
    mapping, unverified = native_cells.build_mapping(text, technology_library='demo045')
    assert unverified == []                          # the sources and the ideal capacitor were verified models already
    assert mapping['models']['dm_npn']['terminals'] == ['C', 'B', 'E', 'S'] and mapping['mapping_version'].startswith('native-draft-1+pdk-demo045-')


@pytest.fixture
def demo_pdk(tmp_path, monkeypatch):
    """demo045 loaded in this test's settings and the MOCK demo circuit registered (as test_wb_pdk does)."""
    scans = [pdk.scan_model_text((FIXTURE / 'models' / name).read_text(), f'/pdk/demo045/models/{name}')
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')]
    record = pdk.finish_load(dict(technology_library='demo045', cdf_text=(FIXTURE / 'cdf.txt').read_text(), scans=scans,
                                  sources=dict(model_files=[])))
    models = pdk.parse_models(record)
    models['vsource'] = dict(kind='vsource', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'dc': 'dc'})
    models['capacitor'] = dict(kind='capacitor', terminals=['PLUS', 'MINUS'], roles=['positive', 'negative'], parameters={'c': 'c'})
    mapping = tmp_path / 'demo_mapping.json'
    mapping.write_text(json.dumps(dict(mapping_version='demo045-test', models=models, global_nets=['0'], net_roles={'0': ['ground']},
                                       parameter_groups=[dict(id='input_w', parameter_kind='w', unit='m', lower=1e-6, upper=10e-6,
                                                              members=[dict(device_id='XU1/M1', parameter='w')])])))
    monkeypatch.setitem(task_registry.SYNTHETIC_FIXTURES, 'pdk_demo', dict(netlist=str(FIXTURE / 'demo_circuit.scs'), config=str(mapping),
                                                                   circuit_class='opamp'))
    loads = dict(load_record=0, list_pdks=0)
    load, listing = pdk_record.load_record, pdk_record.list_pdks

    def counted_load(*args, **kwargs):
        loads['load_record'] += 1
        return load(*args, **kwargs)

    def counted_list(*args, **kwargs):
        loads['list_pdks'] += 1
        return listing(*args, **kwargs)
    monkeypatch.setattr(pdk_record, 'load_record', counted_load)          # where validation and list_pdks read it
    monkeypatch.setattr(pdk_record, 'list_pdks', counted_list)
    return loads


def test_a_validation_reads_the_pdk_record_once_and_lists_the_loaded_pdks_once(demo_pdk, tmp_path):
    extra = [dict(variable_id=f'x{i}', instance_path=device, parameter_name=name, unit='1', lower=1, upper=4)
             for i, (device, name) in enumerate((('XU1/Q1', 'area'), ('XU1/L1', 'nr'), ('XU1/M1', 'region'), ('XU1/M2', 'sa')))]

    def config(vocabulary):
        def mutate(raw):
            raw['run']['network']['vocabulary'] = vocabulary
            raw['parameters'] += extra
        return make_config(tmp_path, 'synthetic:pdk_demo', mutate=mutate)
    graph = tasks.load_task(schema.CircuitReference(source='registered_task', task_id='synthetic:pdk_demo')).base_graph
    demo_pdk.update(load_record=0, list_pdks=0)
    under_pdk = validation.validate(config('pdk:demo045'), graph=graph)
    assert demo_pdk == dict(load_record=1, list_pdks=0)            # it was read four times
    assert 'pdk_vocabulary' in [i.code for i in under_pdk.issues]
    demo_pdk.update(load_record=0, list_pdks=0)
    standard = validation.validate(config('standard'), graph=graph)
    assert demo_pdk == dict(load_record=2, list_pdks=1)            # one listing (it loads each PDK) + one read, for all rows
    hints = [i.message for i in standard.issues if i.code == 'parameter_kind_unsupported']
    assert len(hints) == 4 and sum('The loaded PDK demo045 knows it' in m for m in hints) == 2


def test_a_row_outside_the_pdks_own_range_is_refused_when_the_task_is_saved(tmp_path, monkeypatch):
    """The PDK declares in its CDF what its property form accepts. It was never read, so a row outside it passed every
    offline check and the first candidate the PDK clamped stopped the run - after a real evaluation was paid for."""
    from gator_workbench import cdf_rules, pdk
    text = '\n'.join([
        'CELL|nmos1v|"nch"|("D" "G" "S" "B")|nil|("w" "l")|nil|nil|nil|nil|("schematic")',
        'PARAM|nmos1v|w|"float"|"lengthMetric"|1e-06|"Width"|t|t|nil|nil|(1e-07 1e-05)',
        'PARAM|nmos1v|l|"float"|"lengthMetric"|4.5e-08|"Length"|t|t|nil|nil|nil'])
    cells = pdk.parse_cdf_text(text)['cells']
    assert cells['nmos1v']['parameters']['w']['range'] == [1e-07, 1e-05]       # read from the PDK
    assert cells['nmos1v']['parameters']['l']['range'] is None                 # the PDK declares none: unchanged
    source = pdk.write_source(cells, 'nmos1v', 'w')
    assert source['range'] == [1e-07, 1e-05]                                   # and it reaches the rules
    assert pdk.numeric_range('(2 1)') is None and pdk.numeric_range(['1u', '5u']) is None      # only a plain pair counts
    assert cdf_rules is not None


PDK_FIXTURE = Path(__file__).parent / 'fixtures' / 'pdk_demo'


MODEL = '/pdk/demo045/models/demo045.scs'


# ---- the PDK's model files ----------------------------------------------------------------------------------------------
class _Result:
    def __init__(self, ok=True, output='', errors=()):
        self.ok, self.output, self.errors = ok, output, list(errors)


class _Host:
    """The simulator host and Virtuoso, as the PDK reader sees them: the demo045 files, each with a modification time."""
    def __init__(self, files, modified):
        self.files, self.modified, self.downloads, self.stamp_queries, self.stamps_answer = files, modified, [], 0, True

    def execute_skill(self, text, timeout):
        if 'fileTimeModified' in text:
            self.stamp_queries += 1
            if not self.stamps_answer:
                return _Result(ok=False, errors=['*Error* the session is busy'])
            lines = [f'{p}|{len(self.files[p])}|{self.modified[p]}' if p in self.files else f'{p}|missing'
                     for p in re.findall(r'"(/[^"]+)"', text)]
            return _Result(output='\n'.join(lines))
        if 'ddGetObj("analogLib")' in text:
            return _Result(output=(PDK_FIXTURE / 'ideal.txt').read_text())
        return _Result(output=(PDK_FIXTURE / 'cdf.txt').read_text())

    def download_file(self, remote, local, timeout=None):
        self.downloads.append(remote)
        Path(local).write_bytes(self.files[remote])
        return _Result()


def test_the_pdk_model_files_are_downloaded_only_when_the_host_holds_others():
    files = {f'/pdk/demo045/models/{name}': (PDK_FIXTURE / 'models' / name).read_bytes()
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')}
    modified = {path: '1727000000' for path in files}

    def read(host):
        return pdk.read_from_virtuoso(host, technology_library='demo045', model_file=MODEL, decode=lambda text: text)
    first_host = _Host(files, modified)
    first = read(first_host)
    assert sorted(first_host.downloads) == sorted(files)                       # the first read downloads every file
    again = _Host(files, modified)
    assert read(again) == first and again.downloads == [] and again.stamp_queries == 1   # nothing changed: nothing downloaded
    passive = '/pdk/demo045/models/demo045_passive.scs'
    changed_files = dict(files, **{passive: files[passive] + b'\n* one more line\n'})
    changed = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    answer = read(changed)
    assert changed.downloads == [passive]                                      # only the file the host holds anew
    assert answer['sources']['model_files'] != first['sources']['model_files']
    copy = pdk.ModelFileCache('demo045')
    kept = copy.folder / copy.index[MODEL]['sha256']
    kept.write_bytes(b'* not the file any more\n')                              # a copy that changed is not trusted
    damaged = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    assert read(damaged) == answer and damaged.downloads == [MODEL]
    busy = _Host(changed_files, dict(modified, **{passive: '1727000100'}))
    busy.stamps_answer = False                                                 # no answer about the files: all downloaded
    assert read(busy) == answer and sorted(busy.downloads) == sorted(files) and busy.stamp_queries == 1
    shutil.rmtree(copy.folder)


def test_the_model_file_copies_are_kept_per_host():
    """Record 7.283 (Astra's review of 7.279): the same path on two hosts can carry the same size and modification time
    with different content; the copies are kept per host, so the second host is never served the first one's file."""
    files = {f'/pdk/demo045/models/{name}': (PDK_FIXTURE / 'models' / name).read_bytes()
             for name in ('demo045.scs', 'demo045_mos.scs', 'demo045_passive.scs')}
    modified = {path: '1727000000' for path in files}
    passive = '/pdk/demo045/models/demo045_passive.scs'
    other = dict(files, **{passive: files[passive][:-1] + (b'Y' if files[passive][-1:] != b'Y' else b'Z')})    # the same length

    def read(host, identity):
        return pdk.read_from_virtuoso(host, technology_library='demo045', model_file=MODEL, decode=lambda text: text, cache_host=identity)
    folders = [pdk.ModelFileCache('demo045', identity).folder for identity in ('minlei@vm-a', 'minlei@vm-b')]
    assert [f.parent.name for f in folders] == ['minlei@vm-a', 'minlei@vm-b'] and folders[0].parent.parent == folders[1].parent.parent
    assert pdk.host_folder_name('user@host:22/../x') == 'user@host_22_.._x' and pdk.host_folder_name('') == 'host'
    try:
        a = read(_Host(files, modified), 'minlei@vm-a')
        second = _Host(other, modified)                                           # the same stamps, another file
        b = read(second, 'minlei@vm-b')
        assert sorted(second.downloads) == sorted(files)                          # its own copies: everything downloaded
        assert b['sources']['model_files'] != a['sources']['model_files']
        again = _Host(files, modified)
        assert read(again, 'minlei@vm-a') == a and again.downloads == []          # the first host's copies still serve it
    finally:
        for folder in folders:
            shutil.rmtree(folder.parent, ignore_errors=True)
