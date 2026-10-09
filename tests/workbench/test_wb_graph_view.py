"""The data behind the circuit graph view: a SAVED policy replayed on a state its own run archived. Nothing is
simulated or written; attention is read by hooks that leave the policy's output untouched; every connection of the
circuit carries the attention of both directions and, per receiving node, a head's values sum to 1. MOCK only."""
import json
import math

import pytest
import torch
from fastapi.testclient import TestClient

from gator_workbench import checkpoints as ckpt, graph_view, model_structure, tasks
from gator_workbench.engine import decode_action
from gator_workbench.storage.dataset import map_to_dict
from gator_workbench.trajectory import TrajectoryLoader
from helpers import execute, make_config, workbench_app
from pathlib import Path
from helpers import bridge_installed  # noqa: F401 - a fixture its marked tests use

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.
pytestmark = pytest.mark.xdist_group('test_wb_graph_view')


def trained(root, encoder, name, **output):
    network = dict(encoder_type=encoder, hidden_dim=16, heads=2, layers=2)
    config = make_config(root, run=dict(max_evaluations=14, seed=4, network=network), project=dict(task_name=name),
                         output=dict(dict(checkpoint_every_evaluations=6), **output))
    layout, state = execute(config, root)
    assert state == 'completed'
    return config, layout


@pytest.fixture(scope='module', params=['graph_transformer', 'gatv2', 'graph_gps', 'group_cross_attention'])
def transformer(tmp_path_factory, request):
    root = tmp_path_factory.mktemp('graph_view')
    return (root, *trained(root, request.param, f'view_{request.param}'))


def test_the_circuit_and_both_directions_of_attention_are_complete_and_normalized(transformer):
    _, config, layout = transformer
    view = graph_view.graph_view(layout.run_dir)
    graph = tasks.load_task(config.circuit).base_graph
    assert [d['id'] for d in view['devices']] == [d.id for d in graph.devices]
    assert [n['id'] for n in view['nets']] == [n.id for n in graph.nets]
    assert {(c['device'], c['net'], c['terminal']) for c in view['connections']} == {(c.device_id, c.net_id, c.terminal) for c in graph.connections}
    assert len(view['connections']) == len(graph.connections)
    assert view['attention'] == dict(available=True, layers=2, heads=2, reason=None)
    for layer in range(2):
        into_device, into_net = {}, {}
        for c in view['connections']:
            slot = c['attention'][layer]
            assert slot['layer'] == layer + 1 and len(slot['to_device_heads']) == len(slot['to_net_heads']) == 2
            assert math.isclose(slot['to_device'], sum(slot['to_device_heads']) / 2) and 0 <= slot['to_device'] <= 1
            into_device.setdefault(c['device'], []).append((slot['to_device_heads'], slot['to_device_uniform']))
            into_net.setdefault(c['net'], []).append((slot['to_net_heads'], slot['to_net_uniform']))
        # Softmax per RECEIVING node and head: the mapping from the network's edge list back to connections is right
        # exactly when every such sum is 1 and the uniform share is 1 / (number of arriving connections).
        for arriving in list(into_device.values()) + list(into_net.values()):
            for head in range(2):
                assert math.isclose(sum(heads[head] for heads, _ in arriving), 1.0, abs_tol=1e-5)
            assert all(math.isclose(uniform, 1 / len(arriving)) for _, uniform in arriving)
    assert 'per RECEIVING node' in view['reading'] and 'not why' in view['reading']
    json.dumps(view, allow_nan=False)


def test_global_and_group_weights_have_separate_scopes_and_real_query_ids(transformer):
    _, _, layout = transformer
    view = graph_view.graph_view(layout.run_dir)
    dense, encoder = view['node_attention'], view['network']['encoder_type']
    assert dense['nodes'] == [f"d:{d['id']}" for d in view['devices']] + [f"n:{n['id']}" for n in view['nets']]
    assert dense['groups'] == [g['id'] for g in view['groups']]
    assert len(dense['global_layers']) == (2 if encoder == 'graph_gps' else 0)
    assert len(dense['group_layers']) == (1 if encoder == 'group_cross_attention' else 0)
    for scope in ('global', 'group'):
        for layer in dense[f'{scope}_layers']:
            assert len(layer) == 2
            for head in layer:
                assert len(head) == len(dense['nodes'] if scope == 'global' else dense['groups'])
                for query in head:
                    assert len(query) == len(dense['nodes'])
                    assert all(0 <= weight <= 1 for weight in query)
                    assert sum(query) == pytest.approx(1, abs=1e-6)
    assert 'not physical connections' in dense['reading']


def test_the_hooks_do_not_change_what_the_policy_proposes_and_the_recorded_action_is_the_runs_own(transformer):
    _, _, layout = transformer
    view = graph_view.graph_view(layout.run_dir)
    directory = ckpt.resolve_checkpoint(layout.run_dir, 'latest')
    meta, weights = model_structure.load_verified(directory)
    actor = graph_view._actor(meta, weights)
    features, spec = model_structure.schemas(meta['contract'])
    loader = TrajectoryLoader(layout.run_dir)
    row = next(r for r in loader.transition_rows() if r['commit_seq'] == view['step']['evaluation'])
    from analog_optimizer.models.inputs import batch_observations
    batch = batch_observations([loader.observation(row['state_ref'])], features, spec)
    with torch.no_grad():
        plain = batch.proposals(actor.sample(batch, deterministic=True).actions)[0]          # no hook anywhere
    assert {g['id']: g['policy_action'] for g in view['groups'] if g['policy_action'] is not None} == plain
    for group in view['groups']:
        assert group['policy_value'] == decode_action(group['policy_action'], group['lower'], group['upper'], group['scale'])
        assert group['lower'] <= group['policy_value'] <= group['upper']
        assert group['recorded_action'] == pytest.approx(map_to_dict(row['action'])[group['id']])
        assert {m['device'] for m in group['members']} <= {d['id'] for d in view['devices']}
    assert not any(module._forward_hooks for module in actor.modules())                        # hooks are removed again


def test_the_step_is_the_last_one_the_save_point_had_seen_unless_another_is_asked(transformer):
    _, _, layout = transformer
    points = ckpt.list_checkpoints(layout.run_dir)['checkpoints']
    early = points[0]
    view = graph_view.graph_view(layout.run_dir, early['checkpoint_id'])
    assert view['checkpoint_id'] == early['checkpoint_id'] and view['step']['saved_at'] == early['evaluations']
    assert view['step']['evaluation'] <= early['evaluations'] < view['step']['last']
    asked = graph_view.graph_view(layout.run_dir, early['checkpoint_id'], evaluation=view['step']['last'])
    assert asked['step']['evaluation'] == view['step']['last']
    # The picture really follows the chosen evaluation: for EVERY archived one, the sizes shown are the ones the
    # archive holds for the state before it - and the run did move through different states.
    loader, seen = TrajectoryLoader(layout.run_dir), set()
    for row in loader.transition_rows():
        shown = graph_view.graph_view(layout.run_dir, evaluation=row['commit_seq'])
        state = loader.state_rows()[row['state_ref']]
        assert {g['id']: g['value'] for g in shown['groups']} == dict(zip(state['group_ids'], state['group_values']))
        seen.add(tuple(g['value'] for g in shown['groups']))
    assert len(seen) > 1
    with pytest.raises(graph_view.GraphViewUnavailable, match='no archived evaluation 9999'):
        graph_view.graph_view(layout.run_dir, evaluation=9999)


def test_an_encoder_without_attention_still_shows_the_circuit_and_the_proposals(tmp_path):
    _, layout = trained(tmp_path, 'rgcn', 'view_rgcn')
    view = graph_view.graph_view(layout.run_dir)
    assert view['attention']['available'] is False and 'rgcn encoder has no attention' in view['attention']['reason']
    assert all(c['attention'] == [] for c in view['connections']) and view['connections']
    assert all(g['policy_action'] is not None for g in view['groups'] if g['mutable'])


def test_a_run_without_an_archive_and_a_changed_file_are_refused_in_plain_words(tmp_path, transformer):
    _, layout = trained(tmp_path, 'graph_transformer', 'view_no_archive', save_transition_archive=False)
    with pytest.raises(graph_view.GraphViewUnavailable, match='kept no archive'):
        graph_view.graph_view(layout.run_dir)
    _, _, good = transformer
    import shutil
    copy = tmp_path / 'copy'
    shutil.copytree(good.run_dir, copy)
    target = ckpt.resolve_checkpoint(copy, 'latest') / 'model_weights.pt'
    with target.open('ab') as stream:
        stream.write(b'x')
    with pytest.raises(ValueError, match='checksum'):
        graph_view.graph_view(copy)


def test_the_api_serves_the_view_and_writes_nothing(transformer):
    root, _, layout = transformer
    before = sorted((p.relative_to(layout.run_dir).as_posix(), p.stat().st_mtime_ns) for p in layout.run_dir.rglob('*') if p.is_file())
    client = TestClient(workbench_app(root))
    response = client.post('/api/runs/model/graph-view', json=dict(run_dir=str(layout.run_dir)))
    assert response.status_code == 200
    view = response.json()
    assert view['attention']['available'] and view['devices'] and view['groups'] and view['step']['evaluation'] >= 1
    chosen = client.post('/api/runs/model/graph-view', json=dict(run_dir=str(layout.run_dir), evaluation=view['step']['first'])).json()
    assert chosen['step']['evaluation'] == view['step']['first']
    refused = client.post('/api/runs/model/graph-view', json=dict(run_dir=str(layout.run_dir), evaluation=9999))
    assert refused.status_code == 409 and 'no archived evaluation' in refused.json()['detail']['message']
    assert client.post('/api/runs/model/graph-view', json=dict(run_dir=str(layout.run_dir), checkpoint_id='ckpt-none')).status_code == 404
    assert client.post('/api/runs/model/graph-view', json=dict(run_dir='/etc')).status_code == 403
    assert client.post('/api/runs/model/graph-view', json=dict(run_dir=str(layout.run_dir), picture='x')).status_code == 422
    after = sorted((p.relative_to(layout.run_dir).as_posix(), p.stat().st_mtime_ns) for p in layout.run_dir.rglob('*') if p.is_file())
    assert after == before                                                      # nothing drawn or derived is written into the run


# ------------------------------------------------------------------------------ B4: the graph view reads what it shows
@pytest.mark.usefixtures('bridge_installed')
def test_the_graph_view_reads_one_transition_part_and_its_state_newest_first(tmp_path, monkeypatch):
    config = make_config(tmp_path, run=dict(max_evaluations=30), output=dict(flush_every_evaluations=3, checkpoint_every_evaluations=10))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    import pyarrow.parquet as pq
    filtered, read = [], pq.read_table

    def counting(path, *args, **kwargs):
        if kwargs.get('filters'):
            filtered.append(Path(path).parent.name)
        return read(path, *args, **kwargs)
    monkeypatch.setattr(pq, 'read_table', counting)
    # The transition: the one part of the flush that holds its number. Its state: that part or the one before (a state is
    # written once, with the transition that first sees it - here the previous evaluation's). It was every part, oldest
    # first, for both.
    view = graph_view.graph_view(layout.run_dir)
    assert filtered in (['transitions', 'states'], ['transitions', 'states', 'states']), filtered
    from gator_workbench.trajectory import TrajectoryLoader
    loader = TrajectoryLoader(layout.run_dir)
    numbers = sorted(loader.reader.table('transitions', ['commit_seq'])['commit_seq'].to_pylist())
    assert len(numbers) == view['step']['count'] > 10 and len(loader.reader.flushes) > 5          # parts to skip
    for number in numbers:
        filtered.clear()
        row, _ = graph_view._step(loader, number, None)
        assert filtered in (['transitions', 'states'], ['transitions', 'states', 'states']), (number, filtered)
        whole = graph_view._one_row(loader.reader, 'transitions', 'commit_seq', number)            # every part, oldest first
        assert {k: whole[k] for k in row} == row
        assert loader._states == {row['state_ref']: graph_view._one_row(loader.reader, 'states', 'state_id', row['state_ref'])}
