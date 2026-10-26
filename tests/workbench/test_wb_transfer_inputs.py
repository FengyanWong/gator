"""The transferable network inputs (record 7.298) through the workbench: a MOCK run reading its specs as a set, its model
loading on a task with other specs, PDK-relative sizes and device model features from an invented PDK's numbers, the
pretraining pool with these inputs, and the checks that refuse what a task cannot give. MOCK backend only."""
from dataclasses import asdict
import json

import pytest

from gator_workbench import checkpoints, compile as compile_mod, device_models, network_inputs, pretrain, runs, spec_descriptors, tasks
from gator_workbench.pdk_record import FORMAT as PDK_FORMAT
from gator_workbench.storage.atomic import read_json
from gator_workbench.validation import validate
from helpers import execute, make_config, other_circuits, roots_for

pytestmark = pytest.mark.xdist_group('test_wb_transfer_inputs')
SET = dict(spec_input='set')
TRANSFER = dict(spec_input='set', size_features='pdk_relative', device_model_features=True)
NUMBERS = dict(g45n1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=0.42, u0=0.03, vsat=1.1e5, tox=2.1e-9),
               g45p1svt=dict(lmin=45e-9, wmin=120e-9, basis='model bin', vth0=-0.41, u0=0.009, vsat=8e4, tox=2.2e-9))


def with_network(network):
    """Return a configuration mutation applying the requested network settings."""
    def mutate(raw):
        """Apply the fixture's network-input settings to a starter configuration."""
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


@pytest.fixture(scope='module')
def set_run(tmp_path_factory):
    """Provide a completed synthetic run using specifications as a transferable set."""
    root = tmp_path_factory.mktemp('transfer-set')
    layout, state = execute(make_config(root, run=dict(max_evaluations=12), mutate=with_network(SET)), root)
    assert state == 'completed'
    return layout


def test_a_run_reading_its_specs_as_a_set_records_what_it_showed_its_network(set_run, tmp_path):
    record = read_json(set_run.run_dir / network_inputs.RUN_FILE)
    assert record['spec_input'] == 'set' and record['size_features'] == 'absolute' and not record['device_model_features']
    assert set(record['spec_descriptors']) == {'score'} and record['view_key']
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(set_run.run_dir, 'latest'))
    assert meta['contract']['spec_schema']['layout'] == 'spec-set-v1' and 'metrics' not in meta['contract']['spec_schema']
    manifest = read_json(set_run.manifest)
    assert manifest['architecture']['spec_schema']['version'] == 'spec-set-v1/' + spec_descriptors.DESCRIPTOR_VERSION
    config = make_config(tmp_path, mutate=with_network(SET))
    report = validate(config, graph=tasks.load_task(config.circuit).base_graph)
    infos = {i.code: i for i in report.issues if i.level == 'info'}
    assert 'spec_input_set' in infos and infos['spec_input_set_item'].path == 'targets[0]'
    assert "a built-in analyzer's result" in infos['spec_input_set_item'].message


def test_its_model_loads_on_a_task_with_other_specs(set_run, tmp_path):
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(set_run.run_dir, 'latest'))
    with other_circuits('toy_ldo') as (task,):
        for network, expected in ((SET, True), (dict(spec_input='slots'), False)):
            config = make_config(tmp_path, task=task, mutate=with_network(network))
            loaded = tasks.load_task(config.circuit)
            compiled = compile_mod.compile_task(config, loaded.base_graph)
            contract = runs.learner_contract(config, loaded, 'h' * 64, compiled.spec_schema, None)
            report = checkpoints.check_compatibility(meta, mode='fine_tune', contract=contract, task_definition_hash='h' * 64)
            assert report['compatible'] is expected, report
            assert {c['component'] for c in report['checks'] if c['status'] == 'incompatible'} == (
                set() if expected else {'goal/spec input schema'})


def test_pdk_relative_sizes_and_device_numbers_reach_the_network_and_nothing_else(tmp_path, monkeypatch):
    settings = tmp_path / '_settings'
    invented_pdk(settings)
    config = make_config(tmp_path, mutate=with_network(TRANSFER))          # its three width groups
    runtime = tasks.load_task(config.circuit)
    report = validate(config, graph=runtime.base_graph)
    assert not [i for i in report.issues if i.level in ('blocker', 'error')], report.issues
    compiled = compile_mod.compile_task(config, runtime.base_graph)
    view = network_inputs.view_for(config)
    seen = view.view_graph(compiled.graph)
    seen.validate()                                              # still a consistent graph: groups and members agree
    assert view.view_graph(seen) is seen                         # never viewed twice
    for device in compiled.graph.devices:
        original, shown = compiled.graph.parameters[device.id], seen.parameters[device.id]
        if device.kind in ('nmos', 'pmos'):
            assert shown['w'].value == pytest.approx(original['w'].value / 120e-9)
            assert shown['l'].value == pytest.approx(original['l'].value / 45e-9)
            assert shown['tech_vth0'].value == NUMBERS[device.model_ref]['vth0']
        else:
            assert not any(k.startswith('tech_') for k in shown)
    for group, shown in zip(compiled.graph.parameter_groups, seen.parameter_groups):
        assert shown.value == pytest.approx(group.value / (120e-9 if group.parameter_kind == 'w' else 45e-9 if group.parameter_kind == 'l' else 1))
    assert all('tech_vth0' not in v for v in compiled.graph.parameters.values())       # the recorded graph is untouched
    from gator_workbench import modes
    schema = modes.runtime_options(config)['feature_schema']
    assert schema.version.endswith('+pdk-relative-sizes-v1+device-model-features-v1')
    assert schema.parameters[-4:] == network_inputs.MODEL_COLUMNS and schema.references[schema.parameters.index('w')] == 1.0
    from gator_workbench.vocabulary import schema_label
    assert schema_label(asdict(schema)) == 'standard (8 generic kinds), sizes relative to the PDK, device model features'
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    assert read_json(layout.run_dir / network_inputs.RUN_FILE)['pdk_record_sha256'] == 'c' * 64
    assert 'vth0' not in (layout.run_dir / network_inputs.RUN_FILE).read_text()          # the numbers stay in the PDK folder


def test_what_a_task_cannot_give_is_refused_in_words(tmp_path):
    config = make_config(tmp_path, mutate=with_network(TRANSFER))
    graph = tasks.load_task(config.circuit).base_graph
    codes = {i.code: i for i in validate(config, graph=graph).issues if i.level == 'blocker'}
    assert 'pdk_numbers_unavailable' in codes and 'load that PDK' in codes['pdk_numbers_unavailable'].message
    invented_pdk(tmp_path / '_settings', dict(g45n1svt=NUMBERS['g45n1svt']))
    codes = {i.code: i for i in validate(config, graph=graph).issues if i.level in ('blocker', 'warning')}
    assert 'g45p1svt' in codes['pdk_sizes_missing'].message and codes['device_numbers_missing'].level == 'warning'
    assert '0.42' not in codes['device_numbers_missing'].message                     # names only, never the numbers


def test_the_pretraining_pool_reads_each_archive_with_its_own_view(set_run, tmp_path):
    root = tmp_path / 'sources'
    with other_circuits('toy_ldo') as (task,):
        other, state = execute(make_config(root, task=task, run=dict(max_evaluations=24),
                                           advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
        assert state == 'completed'
        first, state = execute(make_config(root, run=dict(max_evaluations=24),
                                           advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
        request = dict(origin='synthetic', seed=7, holdout_fraction=0.2, inputs=SET,
                       runs=[dict(run_dir=str(s.run_dir), archive_sha256=pretrain.archive_identity(s.run_dir)) for s in (first, other)],
                       updates=3, batch_size=3, checkpoint_every=2, model=dict(hidden_dim=16, heads=2, layers=1),
                       sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01))
        pool = pretrain.prepare_pool(request)
        assert pool.audit['spec_schema']['layout'] == 'spec-set-v1' and pool.audit['inputs']['spec_input'] == 'set'
        for transitions in pool.training.values():
            assert all('spec_descriptors' in t.observation.graph.metadata for t in transitions)
        audit = pretrain.execute(request, tmp_path / 'mock' / 'offline')
        meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(tmp_path / 'mock' / 'offline', 'latest'))
        assert meta['contract']['spec_schema'] == json.loads(json.dumps(audit['spec_schema']))
    with pytest.raises(ValueError, match='Unknown network inputs'):
        pretrain.request_inputs(dict(inputs=dict(operating_points=True)))


def test_rehearsal_and_exact_resume_keep_the_inputs_they_started_with(set_run, tmp_path):
    config = make_config(tmp_path, mutate=with_network(SET))
    raw = config.model_dump(mode='json')
    raw['run']['mode'], raw['run']['model_source'] = 'resume', dict(run_dir=str(set_run.run_dir), checkpoint_id='latest')
    raw['run']['network']['spec_input'] = 'slots'
    with pytest.raises(runs.RunRejected, match='network inputs'):
        runs.prepare_run(type(config).model_validate(raw), roots_for(set_run.run_dir.parents[3]))
