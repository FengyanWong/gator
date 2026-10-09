"""Runs made with a PDK component list: built with the list, refused across lists, fine-tuned and resumed, shown in the graph view (refactoring package D3: the tests of test_wb_pdk that use its module-scoped run, kept on one worker)."""

import json
import pytest
from gator_workbench import checkpoints as ckpt, pdk, runs, schema, task_registry
from gator_workbench.storage import read_json
from helpers import execute, make_config, roots_for, run_prepared, SMALL_NET
from pdk_support import FIXTURE, raw_material
from pdk_support import demo_config, load_demo, parser_config

# one worker builds the module's PDK run once for the four tests that use it (--dist loadgroup)
pytestmark = pytest.mark.xdist_group('test_wb_pdk_run')


# ------------------------------------------------------------------------------------------ a whole run
@pytest.fixture(scope='module')
def pdk_run(tmp_path_factory):
    """One MOCK training run built with the demo PDK's component list (module scope: the settings folder of THIS
    moment holds the loaded PDK; the run keeps its own copy of the list)."""
    from _pytest.monkeypatch import MonkeyPatch
    root = tmp_path_factory.mktemp('pdk-run')
    patch = MonkeyPatch()
    patch.setenv('GATOR_WORKBENCH_SETTINGS_DIR', str(root / '_settings'))
    record = load_demo()
    mapping = parser_config(root, record)
    patch.setitem(task_registry.SYNTHETIC_FIXTURES, 'pdk_demo', dict(netlist=str(FIXTURE / 'demo_circuit.scs'), config=str(mapping),
                                                             circuit_class='opamp'))
    layout, state = execute(demo_config(root, run=dict(max_evaluations=20, seed=5), project=dict(task_name='pdk_source')), root)
    yield root, layout, state, record
    patch.undo()


def test_a_run_is_built_with_the_pdk_list_and_keeps_its_own_copy(pdk_run):
    root, layout, state, record = pdk_run
    assert state == 'completed'
    manifest = read_json(layout.manifest)
    assert manifest['architecture']['vocabulary']['name'] == 'pdk:demo045'
    assert manifest['architecture']['vocabulary']['sha256'] == record['sha256']
    assert pdk.run_vocabulary(layout.run_dir).sha256 == record['sha256']
    meta = ckpt.read_metadata(ckpt.resolve_checkpoint(layout.run_dir, 'latest'))
    assert meta['contract']['feature_schema']['version'] == record['vocabulary']['version']
    assert meta['counters']['learner_updates'] > 0
    from analog_optimizer.training.sac import source_digest
    assert meta['contract']['code_sha256'] == source_digest()      # the optimizer package itself is untouched


def test_models_of_the_two_lists_refuse_each_other_in_plain_words(pdk_run):
    root, layout, _, _ = pdk_run
    config = demo_config(root, 'standard', run=dict(max_evaluations=6, mode='fine_tune'), project=dict(task_name='std'),
                         mutate=lambda raw: raw.__setitem__('parameters', [r for r in raw['parameters'] if r['variable_id'] != 'coil_radius']))
    config.run.model_source.run_dir = str(layout.run_dir)
    with pytest.raises(runs.RunRejected) as refused:
        runs.prepare_run(config, roots_for(root), confirm_transfer=True)
    assert refused.value.code == 'incompatible_checkpoint'
    check = next(c for c in refused.value.report['checks'] if c['component'].startswith('graph feature schema'))
    assert check['status'] == 'incompatible' and 'PDK demo045 (8 components' in check['detail'] and 'standard' in check['detail']


def test_a_pdk_model_is_fine_tuned_with_its_own_list_and_resumed(pdk_run):
    root, layout, _, record = pdk_run
    load_demo()                                     # this test's own settings folder: the PDK is loaded here too
    config = demo_config(root, run=dict(max_evaluations=8, mode='fine_tune'), project=dict(task_name='tuned'), threshold=0.97)
    config.run.model_source.run_dir = str(layout.run_dir)
    target, state = execute(config, root, confirm_transfer=True)
    assert state == 'completed' and pdk.run_vocabulary(target.run_dir).sha256 == record['sha256']
    more = config.model_copy(deep=True)
    more.run.mode, more.run.max_evaluations, more.run.model_source.run_dir = 'resume', 12, str(target.run_dir)
    again, _ = runs.prepare_run(more, roots_for(root))
    assert run_prepared(again) == 'completed'


def test_the_graph_view_and_the_structure_table_show_what_the_network_saw(pdk_run):
    from gator_workbench import graph_view, model_structure
    root, layout, _, _ = pdk_run
    view = graph_view.graph_view(layout.run_dir, 'latest')
    devices = {d['id']: d for d in view['devices']}
    assert devices['XU1/M1']['kind'] == 'demo045:dm_nch' and devices['XU1/M1']['family'] == 'nmos'
    assert devices['XU1/Q1']['family'] == 'bjt' and devices['VDD']['family'] == 'vsource'
    assert view['vocabulary']['name'] == 'pdk:demo045'
    assert {c['role'] for c in view['connections']} >= {'collector', 'base', 'emitter', 'anode', 'cathode'}
    table = model_structure.structure(ckpt.resolve_checkpoint(layout.run_dir, 'latest'))
    assert table['types_verified']
    import torch
    from gator_workbench import modes
    from gator_workbench.trajectory import TrajectoryLoader
    loader = TrajectoryLoader(layout.run_dir)                  # the archive replays the exact network inputs, PDK view included
    vocabulary = pdk.run_vocabulary(layout.run_dir)
    current, _ = loader.training_batch(loader.transitions()[:3], vocabulary=vocabulary)
    meta = ckpt.read_metadata(ckpt.resolve_checkpoint(layout.run_dir, 'latest'))
    learner = modes._new_learner(meta['experiment'], modes.model_config_from(schema.NetworkConfig(**SMALL_NET)),
                                 modes.sac_config_from(schema.AdvancedRL()), None, vocabulary)
    with torch.no_grad():
        assert learner.actor.sample(current).actions.shape[0] == int(current.action_counts.sum())
