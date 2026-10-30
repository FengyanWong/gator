"""What a run or an offline pool showed its network, kept and checked (record 7.319, four findings of a review):
Continue asks for a run's view with the run's own component list; a published offline model keeps the list it was built
with, and the model chooser reads it; an offline pool pins what each source was shown; the variables of a test keep
their case. MOCK backend only."""
import copy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from analog_optimizer.graph.circuit_graph import CircuitGraph, Connection, Device, Net, ParameterValue, SourceSpan
from gator_workbench import checkpoints, device_models, families, network_inputs, pretrain, runs
from gator_workbench.offline_diagnostics import qualify
from gator_workbench.offline_publish import publish
from gator_workbench.pdk_record import FORMAT as PDK_FORMAT
from gator_workbench.storage.atomic import read_json
from gator_workbench.vocabulary import RUN_FILE, run_vocabulary, run_vocabulary_facts
from helpers import edit_json, execute, make_config, other_circuits, roots_for, run_prepared, workbench_app

pytestmark = pytest.mark.xdist_group('test_wb_input_fingerprints')
SPAN = SourceSpan('test', 1)
SMALL = dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)
NUMBERS = dict(g45n1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=0.42, u0=0.03, vsat=1.1e5, tox=2.1e-9),
               g45p1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=-0.41, u0=0.009, vsat=8e4, tox=2.2e-9))
REVIEW = dict(allow_planned_probes=True, reason='synthetic test')


def with_network(network):
    """Return a configuration mutator that applies the requested network options."""
    def mutate(raw):
        raw['run']['network'].update(network)
    return mutate


def invented_pdk(settings, numbers=NUMBERS):
    """An invented gpdk045 record and its device numbers in the test's own settings folder."""
    folder = settings / 'pdks' / 'gpdk045'
    folder.mkdir(parents=True, exist_ok=True)
    record = dict(format=PDK_FORMAT, pdk_id='gpdk045', sha256='c' * 64, technology_library='gpdk045', devices={},
                  sources=dict(model_files=[]))
    (folder / 'pdk.json').write_text(json.dumps(record))
    (folder / device_models.FILE).write_text(json.dumps(dict(format=device_models.FORMAT, pdk_id='gpdk045', record_sha256='c' * 64,
                                                             entry=None, section='tt', files_missing=[], devices=numbers,
                                                             problems={})))


# ------------------------------------------------------------------------------------------- Continue
def test_a_run_with_the_family_list_and_a_spec_set_continues_unchanged_and_a_changed_view_is_still_refused(tmp_path):
    """Until record 7.319 Continue rebuilt the run's view without the run's own component list, so its key never
    matched: every unchanged run with the family list (every new model) and a transferable input was refused."""
    config = make_config(tmp_path, run=dict(max_evaluations=12), mutate=with_network(dict(spec_input='set', vocabulary='families')))
    layout, state = execute(config, tmp_path)
    assert state == 'completed' and isinstance(run_vocabulary(layout.run_dir), families.FamilyList)
    answer = runs.continuation(layout.run_dir, max_evaluations=16)
    assert answer['eligible'] and answer['code'] is None and answer['remaining'] == 4
    raw = config.model_dump(mode='json')
    raw['run'].update(mode='resume', max_evaluations=16, model_source=dict(run_dir=str(layout.run_dir), checkpoint_id='latest'))
    again, _ = runs.prepare_run(type(config).model_validate(raw), roots_for(tmp_path))            # the press itself
    assert again.run_dir == layout.run_dir and run_prepared(again) == 'completed'
    assert read_json(layout.summary)['totals']['candidate_evaluations_charged'] == 16
    edit_json(layout.run_dir / network_inputs.RUN_FILE, lambda record: record.update(view_key='0' * 64))
    refused = runs.continuation(layout.run_dir, max_evaluations=20)
    assert not refused['eligible'] and refused['code'] == 'network_inputs_changed'


# ------------------------------------------------------------------------------------------- the variables of a test
def test_the_variables_of_a_test_keep_their_case():
    deck = dict(head='simulator lang=spectre\nparameters BIAS=900m bias=100m Il=1m\n', tail='')
    variables = network_inputs.variables_of_deck(deck)
    assert variables == dict(BIAS=0.9, bias=0.1, Il=1e-3)
    word = lambda raw: ParameterValue(raw, None, SPAN, reason='not a number')                                  # noqa: E731
    devices = [Device(name, 'vsource', 'vsource', ('PLUS', 'MINUS'), SPAN) for name in ('V1', 'V2', 'V3')]
    connections = [Connection(name, net, terminal, ordinal, role) for name, node in (('V1', 'A'), ('V2', 'B'), ('V3', 'C'))
                   for ordinal, (net, terminal, role) in enumerate(((node, 'PLUS', 'positive'), ('0', 'MINUS', 'negative')))]
    parameters = dict(V1=dict(dc=word('BIAS')), V2=dict(dc=word('bias')), V3=dict(dc=word('IL')))
    graph = CircuitGraph('case', devices, [Net('A'), Net('B'), Net('C'), Net('0', ('ground',), 'mapping')], connections, parameters, [])
    graph.validate()
    seen = network_inputs.NetworkView(bench_features=True, variables=variables).view_graph(graph)
    assert seen.parameters['V1']['dc'].value == 0.9 and seen.parameters['V2']['dc'].value == 0.1     # each its own: both read 0.1
    assert not seen.parameters['V3']['dc'].valid                    # IL is not Il: Spectre would not take it for it either
    bench = network_inputs.bench_of_graph(graph, variables)
    assert (bench.supply_source, bench.supply_v) == ('V1', 0.9)


def test_a_view_made_before_keeps_its_key_and_two_names_of_one_spelling_move_it():
    """The key of a view is what Continue and the circuit's network view compare a saved run by. Names that differ in
    more than case hash as they did (the literal is the key the code before record 7.319 gave this view), so no saved
    run is refused; a view that had read two variables as one shows other numbers now and has another key."""
    before = 'fa574ee3a4a06d192e14d90042cf6e1de7d02fb637f8b15806c4b9bf9a199829'
    view = lambda variables, **options: network_inputs.NetworkView(bench_features=True, variables=variables, **options)   # noqa: E731
    assert view(dict(IL=1e-3, vin=0.9), net_rule=True, measured_nets=('VOUT',)).key == before
    assert view(dict(il=1e-3, vin=0.9), net_rule=True, measured_nets=('VOUT',)).key == before
    assert view(dict(BIAS=0.9, bias=0.1)).key != view(dict(bias=0.1)).key
    config = SimpleNamespace(run=SimpleNamespace(network=SimpleNamespace(operating_points=False, bench_features='relative')),
                             circuit=SimpleNamespace(pdk_id=None))
    assert network_inputs.run_record(config, view(dict(IL=1e-3, vin=0.9)))['second_build']['test_variables'] == ['IL', 'vin']


# ------------------------------------------------------------------------------------------- offline models
@pytest.fixture(scope='module')
def sources(tmp_path_factory):
    """Two recorded MOCK runs to pool: the stand-in OTA5 (PDK id gpdk045) and another circuit."""
    root = tmp_path_factory.mktemp('fingerprint-sources')
    first, state = execute(make_config(root, run=dict(max_evaluations=24), advanced=SMALL), root)
    assert state == 'completed'
    with other_circuits('toy_ldo') as (task,):
        other, state = execute(make_config(root, task=task, run=dict(max_evaluations=24), advanced=SMALL), root)
        assert state == 'completed'
    return root, first, other


def request_for(runs_, inputs):
    """Build a synthetic offline-training request tied to the supplied archive identities."""
    return dict(origin='synthetic', seed=7, holdout_fraction=0.2, inputs=inputs,
                runs=[dict(run_dir=str(s.run_dir), archive_sha256=pretrain.archive_identity(s.run_dir)) for s in runs_],
                updates=2, batch_size=3, checkpoint_every=2, model=dict(hidden_dim=16, heads=2, layers=1),
                sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01))


@pytest.fixture(scope='module')
def family_model(sources, tmp_path_factory):
    """Provide an offline model trained from the fixture runs with family-vocabulary inputs."""
    root, first, other = sources
    output = tmp_path_factory.mktemp('fingerprint-offline') / 'mock' / 'offline'
    with other_circuits('toy_ldo'):
        pretrain.execute(request_for((first, other), dict(vocabulary='families', spec_input='set')), output)
    return root, output


def test_a_published_family_list_model_is_chosen_as_one(family_model, tmp_path):
    """Until record 7.319 publication kept no component list, so the model chooser read a family-list model as one of
    the standard list, set the page's list to it, and the compatibility check then refused the model."""
    root, output = family_model
    layout = publish(output, tmp_path, label='general', review=REVIEW)
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(layout.run_dir, 'latest'))
    assert meta['contract']['feature_schema']['version'] == 'families-v1'
    kept = run_vocabulary(layout.run_dir)
    assert isinstance(kept, families.FamilyList) and kept.devices == {} and kept.pdk_id is None       # the list, no PDK's mapping
    recorded = read_json(layout.manifest)['architecture']['vocabulary']
    assert recorded['name'] == 'families' and recorded['file'] == RUN_FILE and recorded['sha256'] == kept.sha256
    facts = run_vocabulary_facts(layout.run_dir)
    assert facts == dict(name='families', label='device families (11 kinds)', pdk_id=None, sha256=kept.sha256, loaded=True)

    client = TestClient(workbench_app(tmp_path, auto_check_on_start=True))
    chosen = make_config(tmp_path, run=dict(mode='fine_tune', model_source=dict(run_dir=str(layout.run_dir), checkpoint_id='latest')),
                         mutate=with_network(dict(spec_input='set')))
    answer = client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest')).json()
    assert answer['vocabulary']['name'] == 'families'
    # ... and the page's configuration with the list the chooser names is compatible; with the standard list it is not
    as_named = chosen.model_dump(mode='json')
    as_named['run']['network']['vocabulary'] = answer['vocabulary']['name']
    for raw, compatible in ((as_named, True), (chosen.model_dump(mode='json'), False)):
        verdict = client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest', config=raw)).json()
        assert verdict['compatibility']['compatible'] is compatible, verdict['compatibility']

    # A folder published before kept no list: the save point's own contract says which list it is.
    (layout.run_dir / RUN_FILE).unlink()
    assert run_vocabulary_facts(layout.run_dir)['name'] == 'standard'                      # the folder alone cannot tell
    inferred = run_vocabulary_facts(layout.run_dir, meta['contract']['feature_schema'])
    assert (inferred['name'], inferred['label'], inferred['loaded']) == ('families', 'device families (11 kinds)', True)
    assert client.post('/api/runs/model', json=dict(run_dir=str(layout.run_dir), checkpoint_id='latest')).json()['vocabulary']['name'] == 'families'


def test_a_published_standard_list_model_stays_one(sources, tmp_path):
    root, first, other = sources
    output = tmp_path / 'mock' / 'offline'
    with other_circuits('toy_ldo'):
        audit = pretrain.execute(request_for((first, other), {}), output)
    assert all('inputs_sha256' not in source for source in audit['sources'])           # a pool as recorded pins no view
    assert pretrain.inputs_identity(first.run_dir, {}) is None
    layout = publish(output, tmp_path, label='general', review=REVIEW)
    assert run_vocabulary(layout.run_dir) is None and not (layout.run_dir / RUN_FILE).exists()
    assert read_json(layout.manifest)['architecture']['vocabulary']['name'] == 'standard'
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(layout.run_dir, 'latest'))
    assert run_vocabulary_facts(layout.run_dir, meta['contract']['feature_schema'])['name'] == 'standard'


# ------------------------------------------------------------------------------------------- what a pool shows, pinned
def shown_widths(pool):
    """Return rounded distinct widths from the first pooled training transition."""
    transition = next(iter(pool.training.values()))[0]
    return sorted({round(values['w'].value, 6) for values in transition.observation.graph.parameters.values() if 'w' in values})


def test_an_offline_pool_pins_what_each_source_was_shown(sources, tmp_path):
    """Until record 7.319 a pool read each source's PDK numbers, family mapping, spec descriptions and test variables
    as they stood at that moment and recorded none of it: the PDK loaded again with another minimum width gave other
    inputs under the same request and the same audit."""
    root, first, other = sources
    settings = tmp_path / '_settings'
    inputs = dict(spec_input='set', size_features='pdk_relative')
    request = request_for((first,), inputs)
    invented_pdk(settings)
    pool = pretrain.prepare_pool(copy.deepcopy(request))
    pinned = pretrain.inputs_identity(first.run_dir, inputs)
    assert [source['inputs_sha256'] for source in pool.audit['sources']] == [pinned] and len(pinned) == 64
    frozen = tmp_path / 'mock' / 'audit'
    pretrain.execute(copy.deepcopy(request), frozen, audit_only=True)
    assert read_json(frozen / 'pool.json')['sources'][0]['inputs_sha256'] == pinned

    doubled = copy.deepcopy(NUMBERS)
    for numbers in doubled.values():
        numbers['wmin'] *= 2
    invented_pdk(settings, doubled)                                    # the PDK loaded again: another minimum width
    moved = pretrain.prepare_pool(copy.deepcopy(request))
    assert shown_widths(moved) == pytest.approx([width / 2 for width in shown_widths(pool)], abs=1e-5)       # 33.3 -> 16.7
    assert moved.audit['request_sha256'] == pool.audit['request_sha256']               # the same request ...
    assert moved.audit['sources'][0]['inputs_sha256'] != pinned and moved.audit != pool.audit       # ... and the audit tells
    # The frozen pool is not read another way later: qualification refuses a pool with these inputs before it reads it
    # (record 7.352; it used to rebuild the pool first, then say that the inputs changed).
    with pytest.raises(ValueError, match='transferable network inputs'):
        qualify(frozen)

    request['runs'][0]['inputs_sha256'] = pinned                       # a request that pins what it selected
    with pytest.raises(ValueError, match='Network inputs changed after selection'):
        pretrain.prepare_pool(copy.deepcopy(request))
    invented_pdk(settings)                                             # the numbers it selected: accepted again
    assert pretrain.prepare_pool(copy.deepcopy(request)).audit['sources'][0]['inputs_sha256'] == pinned


def test_the_family_mapping_of_a_source_is_pinned_too(sources, tmp_path, monkeypatch):
    root, first, other = sources
    inputs = dict(vocabulary='families')
    before = pretrain.inputs_identity(first.run_dir, inputs)
    pins = [dict(role=role) for role in ('drain', 'gate', 'source', 'bulk')]
    record = dict(format=PDK_FORMAT, pdk_id='gpdk045', sha256='e' * 64, sources=dict(model_files=[]),
                  devices=dict(g45n1svt=dict(family='mos', polarity='n', pins=pins, parameters=[])))
    monkeypatch.setattr(families.pdk_record, 'load_record', lambda pdk_id, sha256=None: record if pdk_id == 'gpdk045' else None)
    after = pretrain.inputs_identity(first.run_dir, inputs)
    assert before != after
    request = request_for((first,), inputs)
    request['runs'][0]['inputs_sha256'] = before
    with pytest.raises(ValueError, match='Network inputs changed after selection'):
        pretrain.prepare_pool(request)
