"""Structured measurement compilation and a complete MOCK CircuitGPS workbench run."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

from gator_workbench import (checkpoints, compile as compile_mod, graph_view, model_structure, modes, network_inputs, pretrain,
                             runs, schema, spec_programs, spec_descriptors, tasks)
from gator_workbench.compile import build_spec_schema
from gator_workbench.schema import NetworkConfig
from gator_workbench.storage.atomic import read_json
from helpers import make_config, execute

pytestmark = pytest.mark.xdist_group('test_wb_circuit_gps')


def program(expression, *, equation='p', analysis='tran', source='ade_output', unit='V', bench=None):
    probe = SimpleNamespace(measurement_id='p', analysis=analysis, result_source=source, signal=expression, unit=unit)
    target = SimpleNamespace(metric_id='s', equation=equation)
    return spec_programs.describe_programs(SimpleNamespace(measurements=[probe], targets=[target]),
                                          bench=bench or spec_descriptors.Bench())['s']


def walk(tree):
    yield tree
    for child in tree.get('children', ()):
        yield from walk(child)


@pytest.mark.parametrize('a,b', [('riseTime', 'fallTime'), ('ymax', 'ymin'), ('rms', 'average')])
def test_measurement_operators_that_used_to_collide_are_distinct(a, b):
    first, second = program(f'{a}(VT("/out"))'), program(f'{b}(VT("/out"))')
    assert first != second
    assert a.lower() in {n['op'] for n in walk(first)}
    assert b.lower() in {n['op'] for n in walk(second)}


def test_order_thresholds_windows_current_terminals_units_and_excitations():
    assert program('VT("/out")', equation='p / 2') != program('VT("/out")', equation='2 / p')
    a = program('cross(clip(VT("/out") 1n 10n) 0.7 1 "rising")')
    nodes = list(walk(a))
    assert {'cross', 'clip', 'rising', 'unit:V'} <= {n['op'] for n in nodes}
    assert sorted(n['value'] for n in nodes if n['op'] == 'number') == [1e-9, 1e-8, .7, 1.]
    current = program('IDC("/DUT/M9/D")', analysis='dc', unit='A')
    assert dict(kind='device', id='DUT/M9', role='drain') in [b for n in walk(current) for b in n.get('bindings', ())]
    assert 'unit:A' in {n['op'] for n in walk(current)}
    excited = program('value(VF("/out") 1M)', analysis='ac', bench=spec_descriptors.Bench(ac_sources=frozenset({'VIN'})))
    assert dict(kind='device', id='VIN', role='excitation') in [b for n in walk(excited) for b in n.get('bindings', ())]


def test_unknown_expressions_and_size_formulas_are_explicit():
    assert 'unknown' in {n['op'] for n in walk(program('unreadable @ expression'))}
    sized = program('larger(fingers("mn*", 2u), fingers("mp*", 3u))', source='size_estimate', unit='count')
    assert {'larger', 'fingers'} <= {n['op'] for n in walk(sized)}
    assert {b['id'] for n in walk(sized) for b in n.get('bindings', ())} == {'mn*', 'mp*'}
    assert 'unknown' not in {n['op'] for n in walk(sized)}


def test_schema_defaults_and_view_identity_include_programs(tmp_path):
    config = make_config(tmp_path, run=dict(network=dict(encoder_type='circuit_gps', hidden_dim=16, heads=2, layers=2)))
    assert config.run.network.spec_input == 'structured' and config.run.network.structural_encoding == 'rwse'
    assert NetworkConfig().spec_input == 'slots'
    assert build_spec_schema(config).layout == 'spec-program-v1'
    before, record = network_inputs.prepared(config)
    assert record['measurement_programs']['version'] == 'measurement-program-v1'
    changed = deepcopy(before.programs)
    first = next(iter(changed))
    changed[first] = dict(op='number', value=.25)
    after = network_inputs.NetworkView(descriptors=before.descriptors, programs=changed)
    assert before.key != after.key


@pytest.fixture(scope='module')
def joint_run(tmp_path_factory):
    root = tmp_path_factory.mktemp('circuit-gps-mock')
    config = make_config(root, run=dict(max_evaluations=8, network=dict(encoder_type='circuit_gps', hidden_dim=16, heads=2, layers=2)),
                         advanced=dict(updates_per_transition=1, gamma=0.))
    layout, state = execute(config, root)
    assert state == 'completed'
    return config, layout


def test_saved_network_structure_and_attention_are_inspectable(joint_run):
    config, layout = joint_run
    directory = checkpoints.resolve_checkpoint(layout.run_dir, 'latest')
    meta = checkpoints.read_metadata(directory)
    assert meta['contract']['model_config']['encoder_type'] == 'circuit_gps'
    assert meta['contract']['spec_schema']['layout'] == 'spec-program-v1'
    table = model_structure.structure(directory)
    assert table['types_verified'], table['types_problem']
    for part in table['parts']:
        assert all(row['role'] for row in part['layers']), [row['path'] for row in part['layers'] if not row['role']]
    view = graph_view.graph_view(layout.run_dir)
    for scope in ('global_layers', 'group_layers'):
        assert len(view['node_attention'][scope]) == 2
        assert torch.isfinite(torch.tensor(view['node_attention'][scope])).all()
        weights = torch.tensor(view['node_attention'][scope])
        assert weights.shape[-1] == len(view['node_attention']['nodes'])
        torch.testing.assert_close(weights.sum(-1), torch.ones_like(weights.sum(-1)))
    record = read_json(layout.run_dir / network_inputs.RUN_FILE)
    assert record['measurement_programs']['specs']


def test_offline_pool_rebuilds_the_same_structured_inputs(joint_run, tmp_path):
    config, layout = joint_run
    request = dict(origin='synthetic', runs=[dict(run_dir=str(layout.run_dir), archive_sha256=pretrain.archive_identity(layout.run_dir))],
                   model=dict(encoder_type='circuit_gps', hidden_dim=16, heads=2, layers=2))
    pool = pretrain.prepare_pool(request)
    assert pool.schema == build_spec_schema(config)
    assert pool.audit['inputs']['spec_input'] == 'structured'
    assert sum(len(rows) for rows in pool.training.values()) > 0
    request.update(updates=2, batch_size=2, checkpoint_every=1,
                   sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=.01))
    output = tmp_path / 'mock' / 'joint-offline'
    pretrain.execute(request, output)
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(output, 'latest'))
    assert meta['contract']['model_config']['encoder_type'] == 'circuit_gps'
    assert meta['contract']['spec_schema']['layout'] == 'spec-program-v1'


def test_version_3_is_chosen_in_the_network_and_its_model_loads_only_as_version_3(tmp_path):
    """Record 7.356: run.network.architecture_version 3 builds CircuitGPS with its sums averaged. Unset or at the encoder's
    default it hashes as absent, so every configuration written before keeps its hashes, and unset it is not written, so
    a configuration saved now loads where the field is not known. A MOCK run trains version 3, its save point records it,
    and a fine-tune loads it only into a version-3 network."""
    net = dict(encoder_type='circuit_gps', hidden_dim=16, heads=2, layers=2)
    networks = {None: net, 2: dict(net, architecture_version=2), 3: dict(net, architecture_version=3)}
    made = {v: make_config(tmp_path, run=dict(max_evaluations=8, network=n), advanced=dict(updates_per_transition=1, gamma=0.))
            for v, n in networks.items()}
    assert [modes.model_config_from(c.run.network).architecture_version for c in made.values()] == [2, 2, 3]
    assert schema.config_hash(made[None]) == schema.config_hash(made[2]) != schema.config_hash(made[3])
    written = {v: c.model_dump(mode='json')['run']['network'] for v, c in made.items()}      # unset: not written at all
    assert 'architecture_version' not in written[None]
    assert [written[v]['architecture_version'] for v in (2, 3)] == [2, 3]
    for encoder, version in (('circuit_gps', 4), ('graph_gps', 2), ('rgcn', 3)):
        with pytest.raises(ValueError, match='architecture_version'):
            NetworkConfig(encoder_type=encoder, architecture_version=version)
    layout, state = execute(made[3], tmp_path)
    assert state == 'completed'
    meta = checkpoints.read_metadata(checkpoints.resolve_checkpoint(layout.run_dir, 'latest'))
    assert meta['contract']['model_config']['architecture_version'] == 3
    loaded = tasks.load_task(made[3].circuit)
    spec_schema = compile_mod.compile_task(made[3], loaded.base_graph).spec_schema
    for version, expected in ((3, True), (None, False)):
        contract = runs.learner_contract(made[version], loaded, 'h' * 64, spec_schema, runs._vocabulary_for(made[version]))
        report = checkpoints.check_compatibility(meta, mode='fine_tune', contract=contract, task_definition_hash='h' * 64)
        refused = [c['component'] for c in report['checks'] if c['status'] == 'incompatible']
        assert report['compatible'] is expected and refused == ([] if expected else ['network architecture']), report
