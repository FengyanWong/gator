"""The device-family component list (record 7.298): one fixed list every PDK maps into by rule, the list of a new model;
a MOCK run with it, its model loading on another circuit, the classification rules it relies on, and pretraining with it.
The PDK record and model text below are invented. MOCK backend only."""
import json

import pytest

from gator_workbench import checkpoints, compile as compile_mod, families, model_scan, network_inputs, pdk_record, pretrain, runs, tasks
from gator_workbench.storage.atomic import read_json
from gator_workbench.validation import validate
from gator_workbench.vocabulary import run_vocabulary, schema_label
from helpers import execute, make_config, other_circuits

pytestmark = pytest.mark.xdist_group('test_wb_families')
FAMILIES = dict(vocabulary='families')


def with_network(network):
    """Return a configuration mutator that applies the requested network options."""
    def mutate(raw):
        raw['run']['network'].update(network)
    return mutate


def invented_record(devices):
    """Build a synthetic PDK record for the supplied device descriptions."""
    return dict(format=pdk_record.FORMAT, pdk_id='demo', sha256='d' * 64, devices=devices, sources=dict(model_files=[]))


DEVICES = {
    'nch': dict(family='mos', polarity='n', pins=[dict(role=r) for r in ('drain', 'gate', 'source', 'bulk')],
                parameters=[dict(name='w', numeric=True, canonical='w'), dict(name='l', numeric=True, canonical='l'),
                            dict(name='sa', numeric=True, canonical='sa')]),
    'npn5': dict(family='bjt', polarity='npn', pins=[dict(role=r) for r in ('collector', 'base', 'emitter', 'bulk')],
                 parameters=[dict(name='area', numeric=True, canonical='area'), dict(name='m', numeric=True, canonical='m')]),
    'dio': dict(family='diode', polarity=None, pins=[dict(role='anode'), dict(role='cathode')], parameters=[]),
    'moscap': dict(family='varactor', polarity=None, pins=[dict(role='positive'), dict(role='negative')], parameters=[]),
    'wellcon': dict(family='other', polarity=None, pins=[dict(role='unknown'), dict(role='unknown')], parameters=[]),
}


def test_every_family_of_a_record_and_nothing_by_name(monkeypatch):
    monkeypatch.setattr(pdk_record, 'load_record', lambda pdk_id, sha256=None: invented_record(DEVICES) if pdk_id == 'demo' else None)
    block = families.block_for('demo')
    kinds = {model: entry['kind'] for model, entry in block['devices'].items()}
    assert kinds == dict(nch='nmos', npn5='npn', dio='diode', moscap='varactor', wellcon='unknown')
    assert block['devices']['nch']['columns'] == dict(w='w', l='l')                        # `sa` is not a family column
    assert block['devices']['npn5']['roles'] == ['collector', 'base', 'emitter', 'bulk']
    listed = families.FamilyList(block)
    assert listed.name == 'families' and listed.label == 'device families (11 kinds)' and listed.schema.version == 'families-v1'
    assert listed.schema.device_kinds == families.KINDS and listed.schema.parameters[-1] == 'area'
    assert families.block_for('missing')['devices'] == {} and families.block_for('demo')['sha256'] == block['sha256']
    assert families.family_kind('mos', None) == 'unknown' and families.family_kind('inductor') == 'inductor'


def test_the_classification_rules_the_list_relies_on():
    text = '\n'.join(['subckt rchain (p n b)', 'r1 (p x p n) bsource r=100', 'r2 (x n p n) bsource r=100', 'd1 (b p) dsub',
                      'ends rchain', 'model dsub diode is=1e-15'])
    scan = model_scan.scan_model_text(text, '/pdk/demo.scs')
    found = model_scan.classify_model('rchain', scan, cdf_units=['lengthMetric'])
    assert found['family'] == 'resistor' and 'resistive behavioural sources' in found['family_basis']
    primitive = model_scan.classify_model('capacitor', scan)
    assert primitive['family'] == 'capacitor' and "Spectre's own" in primitive['family_basis']
    assert [p['role'] for p in model_scan.pin_roles('capacitor', primitive, scan)] == ['positive', 'negative']
    assert model_scan.classify_model('wellcon', scan)['family'] == 'other'                 # still never guessed


@pytest.fixture(scope='module')
def family_run(tmp_path_factory):
    """Provide a completed MOCK run using the family-vocabulary network configuration."""
    root = tmp_path_factory.mktemp('families')
    layout, state = execute(make_config(root, run=dict(max_evaluations=12), mutate=with_network(FAMILIES)), root)
    assert state == 'completed'
    return layout


def test_a_new_model_with_the_family_list_and_its_model_on_another_circuit(family_run, tmp_path):
    own = run_vocabulary(family_run.run_dir)
    assert isinstance(own, families.FamilyList) and own.version == 'families-v1'
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(family_run.run_dir, 'latest'))
    assert meta['contract']['feature_schema']['version'] == 'families-v1'
    assert schema_label(meta['contract']['feature_schema']) == 'device families (11 kinds)'
    with other_circuits('toy_ldo') as (task,):
        for network, expected in ((FAMILIES, True), (dict(vocabulary='standard'), False)):
            config = make_config(tmp_path, task=task, mutate=with_network(network))
            loaded = tasks.load_task(config.circuit)
            compiled = compile_mod.compile_task(config, loaded.base_graph)
            vocabulary = runs._vocabulary_for(config)
            contract = runs.learner_contract(config, loaded, 'h' * 64, compiled.spec_schema, vocabulary)
            report = checkpoints.check_compatibility(meta, mode='fine_tune', contract=contract, task_definition_hash='h' * 64)
            assert report['compatible'] is expected, report


def test_a_new_model_still_on_the_standard_list_is_told(tmp_path):
    config = make_config(tmp_path)
    graph = tasks.load_task(config.circuit).base_graph
    warnings = {i.code for i in validate(config, graph=graph).issues if i.level == 'warning'}
    assert 'standard_list_new_model' in warnings
    families_config = make_config(tmp_path, mutate=with_network(FAMILIES))
    assert 'standard_list_new_model' not in {i.code for i in validate(families_config, graph=graph).issues}
    raw = config.model_dump(mode='json')
    raw['run']['mode'] = 'frozen'                                       # continuing an old model: no word about it
    assert 'standard_list_new_model' not in {i.code for i in validate(type(config).model_validate(raw), graph=graph).issues}


def test_pretraining_with_the_family_list(family_run, tmp_path):
    root = tmp_path / 'sources'
    with other_circuits('toy_ldo') as (task,):
        other, state = execute(make_config(root, task=task, run=dict(max_evaluations=24),
                                           advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
        first, _ = execute(make_config(root, run=dict(max_evaluations=24),
                                       advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
        request = dict(origin='synthetic', seed=7, holdout_fraction=0.2, inputs=dict(vocabulary='families', spec_input='set'),
                       runs=[dict(run_dir=str(s.run_dir), archive_sha256=pretrain.archive_identity(s.run_dir)) for s in (first, other)],
                       updates=2, batch_size=3, checkpoint_every=2, model=dict(hidden_dim=16, heads=2, layers=1),
                       sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01))
        audit = pretrain.execute(request, tmp_path / 'mock' / 'offline')
    assert audit['feature_schema']['version'] == 'families-v1' and audit['inputs']['vocabulary'] == 'families'
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(tmp_path / 'mock' / 'offline', 'latest'))
    assert meta['contract']['feature_schema']['version'] == 'families-v1'
