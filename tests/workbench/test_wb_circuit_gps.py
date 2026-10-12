"""Structured measurement compilation and a complete MOCK CircuitGPS workbench run."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
import torch

from gator_workbench import checkpoints, graph_view, model_structure, network_inputs, pretrain, spec_programs, spec_descriptors
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
