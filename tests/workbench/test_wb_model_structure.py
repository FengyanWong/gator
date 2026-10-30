"""The structure table of a saved RL model: every layer with its type, shape and parameter count, read from the
tensors of the save point. Layer types are reported only when the rebuilt network holds exactly the saved tensors,
the "never used" flag is pinned against REAL gradients for every encoder, and every layer has a plain-language line.
MOCK backend only; nothing is plotted."""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, model_structure, modes, tasks
from gator_workbench.compile import compile_task
from gator_workbench.engine import learner_experiment
from gator_workbench.schema import task_definition_hash
from helpers import execute, make_config, ScriptedEnvFactory, SMALL_NET, workbench_app

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.
pytestmark = pytest.mark.xdist_group('test_wb_model_structure')

ENCODERS = ('graph_transformer', 'rgcn', 'gatv2', 'graph_gps', 'group_cross_attention')


@pytest.fixture(scope='module')
def saved(tmp_path_factory):
    """Provide a completed synthetic run whose save points supply the model-structure tests."""
    root = tmp_path_factory.mktemp('structure')
    layout, state = execute(make_config(root, run=dict(max_evaluations=8, seed=3), project=dict(task_name='structure_source')), root)
    assert state == 'completed'
    return root, layout


def test_every_saved_tensor_is_in_the_table_with_type_shape_and_count(saved):
    _, layout = saved
    directory = ckpt.resolve_checkpoint(layout.run_dir, 'latest')
    table = model_structure.structure(directory)
    weights = ckpt.load_weights(directory)
    assert table['types_verified'] and table['types_problem'] is None and table['critics_identical']
    assert {k: table['network'][k] for k in SMALL_NET} == SMALL_NET
    actor, critic = table['parts']
    assert (actor['part'], critic['part']) == ('actor', 'critic')
    # Nothing is left out and nothing is invented: the rows are exactly the saved tensors, with their real sizes.
    listed = {f"{row['path']}.{t['name']}": t['shape'] for row in actor['layers'] for t in row['tensors']}
    assert listed == {name: list(tensor.shape) for name, tensor in weights['actor'].items()}
    assert actor['parameters'] == sum(t.numel() for t in weights['actor'].values())
    assert critic['parameters'] == sum(t.numel() for name, t in weights['critics'].items() if name.startswith('0.'))
    totals = table['totals']
    assert totals['trained'] == actor['parameters'] + 2 * critic['parameters'] + 1
    assert totals['saved'] == sum(t.numel() for part in ('actor', 'critics', 'targets') for t in weights[part].values()) + 1
    assert abs(sum(row['share'] for row in actor['layers']) - 1) < 1e-9
    assert sum(s['parameters'] for s in actor['sections']) == actor['parameters']
    first = actor['layers'][0]
    assert (first['path'], first['type'], first['shape'], first['parameters']) == ('encoder.device_values', 'Linear', '32 -> 16', 32 * 16 + 16)
    kinds = {row['path']: (row['type'], row['shape']) for row in actor['layers']}
    assert kinds['encoder.device_kind'] == ('Embedding', '8 entries x 16') and kinds['encoder.output_norm'] == ('LayerNorm', 'over 16')
    assert kinds['head.2'] == ('Linear', '16 -> 2')                       # mean and log-std of the action
    assert {row['path']: row['shape'] for row in critic['layers']}['head.2'] == '16 -> 1'          # one Q-value
    assert 'encoder.action_token.0' in {row['path'] for row in critic['layers']} - {row['path'] for row in actor['layers']}
    json.dumps(table, allow_nan=False)                                    # plain JSON for the API


@pytest.mark.parametrize('encoder', ENCODERS)
def test_never_used_is_what_real_gradients_say_and_every_layer_is_explained(tmp_path, encoder):
    """One real forward + backward pass of the policy and of a critic on a real observation of the MOCK task: the
    layers that receive NO gradient are exactly the layers the table flags as never used."""
    from analog_optimizer.training.sac import SACLearner
    config = make_config(tmp_path, run=dict(network=dict(encoder_type=encoder, hidden_dim=16, heads=2, layers=2)))
    task = tasks.load_task(config.circuit)
    compiled = compile_task(config, task.base_graph)
    with ScriptedEnvFactory(compiled.graph, compiled.specs, str(tmp_path / 'work'), 3)(0) as environment:
        observation, _ = environment.reset()
    learner = SACLearner(experiment=learner_experiment(config, task, task_definition_hash(config)),
                         model_config=modes.model_config_from(config.run.network),
                         config=modes.sac_config_from(config.run.advanced), spec_schema=compiled.spec_schema)
    batch = learner.batch([observation])
    sample = learner.actor.sample(batch)
    (sample.actions.sum() + sample.log_prob.sum()).backward()
    learner.critics[0](batch, sample.actions.detach()).sum().backward()
    for part, module in (('actor', learner.actor), ('critic', learner.critics[0])):
        # `grad is None` = the forward pass never touched the weights. A gradient that exists but is zero is another
        # matter and depends on the DATA (`binding_ratio` multiplies log(ratio), which is 0 when every ratio is 1):
        # such a layer is used, and is not flagged.
        untouched = {name.rpartition('.')[0] for name, p in module.named_parameters() if p.grad is None}
        rows = model_structure._rows(part, module.state_dict(), module)
        flagged = {row['path'] for row in rows if row['unused']}
        assert flagged == untouched, (encoder, part)
        assert all(row['note'] for row in rows if row['unused'])
        assert all(row['role'] and row['section'] != 'Other' for row in rows), [r['path'] for r in rows if not r['role']]
        assert [row['section'] for row in rows if row['section'].startswith('Block')].count('Block 2') > 0       # 2 layers asked
    if encoder in ('graph_transformer', 'graph_gps', 'group_cross_attention'):
        assert flagged == {'encoder.blocks.0.attention.lin_skip', 'encoder.blocks.1.attention.lin_skip'}
    else:
        assert flagged == set()


def test_types_are_never_guessed_and_a_changed_file_is_refused(saved, tmp_path, monkeypatch):
    _, layout = saved
    source = ckpt.resolve_checkpoint(layout.run_dir, 'latest')
    # The recorded settings no longer describe the file: every tensor is still listed, without types or flags.
    monkeypatch.setattr(model_structure, 'rebuild_network', lambda contract: (_ for _ in ()).throw(KeyError('feature_schema')))
    table = model_structure.structure(source)
    assert table['types_verified'] is False and 'could not be rebuilt' in table['types_problem']
    actor = table['parts'][0]
    assert all(row['type'] is None and row['unused'] is False for row in actor['layers']) and actor['unused_parameters'] == 0
    assert {row['path']: row['shape'] for row in actor['layers']}['encoder.device_values'] == '16x32, 16'
    assert actor['parameters'] == sum(t.numel() for t in ckpt.load_weights(source)['actor'].values())
    monkeypatch.undo()
    # A rebuilt network of ANOTHER size is not "verified" either.
    other = dict(ckpt.read_metadata(source)['contract'], model_config=dict(ckpt.read_metadata(source)['contract']['model_config'], hidden_dim=32))
    built = model_structure.rebuild_network(other)
    assert not model_structure.same_tensors(built['actor'], ckpt.load_weights(source)['actor'])
    # A weights file that does not match its recorded checksum is not read at all.
    copy = tmp_path / 'tampered'
    shutil.copytree(source, copy)
    with (copy / 'model_weights.pt').open('ab') as stream:
        stream.write(b'x')
    with pytest.raises(ValueError, match='checksum'):
        model_structure.structure(copy)


def test_the_api_serves_the_table_for_a_chosen_save_point(saved):
    root, layout = saved
    client = TestClient(workbench_app(root))
    point = ckpt.list_checkpoints(layout.run_dir)['checkpoints'][0]['checkpoint_id']
    response = client.post('/api/runs/model/structure', json=dict(run_dir=str(layout.run_dir), checkpoint_id=point))
    assert response.status_code == 200
    table = response.json()
    assert table['checkpoint_id'] == point and table['types_verified'] and [p['part'] for p in table['parts']] == ['actor', 'critic']
    assert table['totals']['never_used'] == 3 * table['parts'][0]['unused_parameters'] > 0          # graph_transformer: lin_skip
    latest = client.post('/api/runs/model/structure', json=dict(run_dir=str(layout.run_dir))).json()
    assert latest['checkpoint_id'] == ckpt.list_checkpoints(layout.run_dir)['latest']
    assert client.post('/api/runs/model/structure', json=dict(run_dir=str(layout.run_dir), checkpoint_id='ckpt-none')).status_code == 404
    assert client.post('/api/runs/model/structure', json=dict(run_dir='/etc', checkpoint_id='latest')).status_code == 403
    assert client.post('/api/runs/model/structure', json=dict(run_dir=str(layout.run_dir), extra='x')).status_code == 422


@pytest.mark.parametrize('encoder,version', [(name, 1) for name in ENCODERS] +
                         [('circuit_gps', version) for version in (1, 2, 3)])
def test_actor_only_rebuild_matches_the_full_builder_without_constructing_a_critic(encoder, version, monkeypatch):
    from dataclasses import asdict
    import torch
    from analog_optimizer.graph.pyg_converter import FeatureSchema
    from analog_optimizer.models import graph_transformer
    from analog_optimizer.models.inputs import SpecSchema
    from gator_workbench import graph_view
    contract = dict(feature_schema=asdict(FeatureSchema()), spec_schema=asdict(SpecSchema()),
                    model_config=dict(encoder_type=encoder, architecture_version=version, hidden_dim=8, heads=2, layers=1))
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(37)
        full = model_structure.rebuild_network(contract)
        assert list(full) == ['actor', 'critic']

        def unused_critic(*args, **kwargs):
            """Fail if actor reconstruction allocates a critic."""
            pytest.fail('Actor reconstruction must not allocate a critic')

        monkeypatch.setattr(graph_transformer, 'GraphCritic', unused_critic)
        torch.manual_seed(37)
        selected = model_structure.rebuild_network(contract, parts=('actor',))
        assert list(selected) == ['actor']
        expected = full['actor'].state_dict()
        assert list(selected['actor'].state_dict()) == list(expected)
        assert all(torch.equal(tensor, expected[name]) for name, tensor in selected['actor'].state_dict().items())
        restored = graph_view._actor(dict(contract=contract), dict(actor=expected))
        assert not restored.training
        assert all(torch.equal(tensor, expected[name]) for name, tensor in restored.state_dict().items())
        # The restored viewer owns its parameters; the loaded checkpoint tensors are not borrowed mutable storage.
        assert all(tensor.data_ptr() != expected[name].data_ptr() for name, tensor in restored.named_parameters())


@pytest.mark.parametrize('damage', ['contract', 'missing_tensor', 'wrong_shape'])
def test_actor_only_rebuild_keeps_contract_and_tensor_checks(saved, damage):
    from gator_workbench import graph_view
    directory = ckpt.resolve_checkpoint(saved[1].run_dir, 'latest')
    meta, weights = model_structure.load_verified(directory)
    if damage == 'contract':
        meta['contract']['model_config']['encoder_type'] = 'unknown'
        message = 'could not be rebuilt'
    else:
        weights['actor'] = dict(weights['actor'])
        name = next(iter(weights['actor']))
        if damage == 'missing_tensor':
            del weights['actor'][name]
        else:
            weights['actor'][name] = weights['actor'][name].reshape(-1)[:1]
        message = 'does not hold the same tensors'
    with pytest.raises(graph_view.GraphViewUnavailable, match=message):
        graph_view._actor(meta, weights)
