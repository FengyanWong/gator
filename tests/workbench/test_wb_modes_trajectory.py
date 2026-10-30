"""scratch / resume / fine_tune / frozen semantics, checkpoint consistency and compatibility, transfer
across different topologies and action dimensions, and reloading of configuration + trajectories.
The complete experience archive is tested against the finite replay snapshot."""
import json
import pickle
import shutil

import pytest
import torch

from gator_workbench import checkpoints as ckpt, modes, runs, schema
from gator_workbench.storage import read_json
from gator_workbench.trajectory import TrajectoryLoader
from helpers import execute, make_config, other_circuits, roots_for, rows, summary

# Under --dist loadgroup one xdist worker runs this whole module, so its module-scoped fixture is built once.
pytestmark = pytest.mark.xdist_group('test_wb_modes_trajectory')


def latest(layout):
    """Return the latest save-point directory and its metadata."""
    directory = ckpt.resolve_checkpoint(layout.run_dir, 'latest')
    return directory, ckpt.read_metadata(directory)


def transfer_config(tmp_path, source_layout, mode, task='synthetic:gpdk045_ota5', **kwargs):
    """Build a transfer configuration using the source run's network and saved-model location."""
    network = read_json(source_layout.effective_config)['run']['network']
    run = dict(dict(max_evaluations=12, mode=mode, network=network), **kwargs.pop('run', {}))
    config = make_config(tmp_path, task, run=run, **kwargs)
    config.run.model_source.run_dir = str(source_layout.run_dir)
    return config


@pytest.fixture(scope='module', params=['graph_transformer', 'graph_gps', 'group_cross_attention'])
def source_run(tmp_path_factory, request):
    """One trained MOCK source model shared by the transfer tests (never modified by them)."""
    root = tmp_path_factory.mktemp('source')
    network = dict(encoder_type=request.param, hidden_dim=16, heads=2, layers=1)
    layout, state = execute(make_config(root, run=dict(max_evaluations=24, seed=7, network=network), project=dict(task_name='source')), root)
    assert state == 'completed'
    return root, layout


# ------------------------------------------------------------------------------- checkpoints
def test_checkpoint_is_one_consistency_boundary_with_declared_capability(source_run):
    _, layout = source_run
    directory, meta = latest(layout)
    assert meta['restoration_capability'] == 'full_state' and meta['missing_components'] == []
    assert set(ckpt.FULL_COMPONENTS) == set(meta['restorable_components'])
    assert 'never saved or restored' in meta['recoverable_boundary']           # no claim about running simulators
    assert ckpt.verify_files(directory) == []
    assert set(meta['files']) == {'training_state.pt', 'model_weights.pt', 'replay_buffer/manifest.json'}
    s = summary(layout)
    assert meta['ledger']['charged'] == s['totals']['candidate_evaluations_charged'] == meta['data_cursor']['commit_seq']
    assert meta['counters']['learner_updates'] == s['totals']['gradient_updates']
    # the embedded replay really matches the counters saved beside it
    payload = torch.load(directory / 'training_state.pt', map_location='cpu', weights_only=False)
    assert payload['updates'] == meta['counters']['learner_updates']
    assert len(payload['replay']['items']) == meta['replay']['size'] == meta['counters']['replay_size']
    assert payload['run_state']['ledger'] == meta['ledger'] and payload['run_state']['data_cursor'] == meta['data_cursor']
    manifest = read_json(directory / 'replay_buffer' / 'manifest.json')
    assert manifest['member_candidate_ids'] == [t.candidate_id for t in payload['replay']['items']]
    pointer = read_json(layout.checkpoints / 'latest.json')
    assert pointer['checkpoint_id'] == meta['checkpoint_id'] and 'NOT automatically the best' in pointer['meaning']
    assert read_json(layout.checkpoints / 'best_policy.json')['status'] == 'not_selected'
    assert not list(layout.checkpoints.glob('.staging-*'))


def test_weights_file_is_tensor_only_and_loads_without_unpickling_objects(source_run):
    directory, _ = latest(source_run[1])
    payload = torch.load(directory / 'model_weights.pt', map_location='cpu', weights_only=True)   # safe loader
    assert payload['format'] == 'gator-workbench-weights-v1' and set(payload) >= {'actor', 'critics', 'targets', 'log_alpha'}
    with pytest.raises(pickle.UnpicklingError, match='Weights only load failed'):
        torch.load(directory / 'training_state.pt', map_location='cpu', weights_only=True)  # holds dataclasses: trusted-only


def test_tampered_checkpoint_is_rejected(tmp_path, source_run):
    root, layout = source_run
    copy = tmp_path / 'copy'
    shutil.copytree(layout.run_dir, copy)
    directory, _ = latest(type(layout)(copy))
    with (directory / 'model_weights.pt').open('ab') as stream:
        stream.write(b'tampered')
    assert ckpt.verify_files(directory) == ['checksum mismatch model_weights.pt']


def test_best_policy_needs_an_explicit_validation_rule_and_records_its_cost(tmp_path, source_run):
    copy = tmp_path / 'copy'
    shutil.copytree(source_run[1].run_dir, copy)
    store = ckpt.CheckpointStore(copy, run_id='r', task_id='t', task_definition_hash='h')
    checkpoint_id = read_json(copy / 'checkpoints' / 'latest.json')['checkpoint_id']
    with pytest.raises(ValueError):
        store.select_best_policy(checkpoint_id, validation_rule=None, score=1.0, selection_cost_evaluations=5)
    rule = dict(metric='validation_success_rate', direction='max', tasks=['val-1'])
    assert store.select_best_policy(checkpoint_id, validation_rule=rule, score=0.5, selection_cost_evaluations=5)
    assert not store.select_best_policy(checkpoint_id, validation_rule=rule, score=0.4, selection_cost_evaluations=5)
    best = read_json(copy / 'checkpoints' / 'best_policy.json')
    assert best['selected'] == checkpoint_id and best['score'] == 0.5 and best['selection_cost_evaluations'] == 10
    with pytest.raises(ValueError):
        store.select_best_policy(checkpoint_id, validation_rule=dict(rule, direction='min'), score=0.1,
                                 selection_cost_evaluations=1)


# ------------------------------------------------------------------------------- compatibility
def test_compatibility_failures_are_visible_per_component_and_never_fall_back(tmp_path, source_run):
    root, layout = source_run
    config = transfer_config(root, layout, 'fine_tune', run=dict(network=dict(encoder_type='gatv2', hidden_dim=16, heads=2, layers=1)))
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(config, roots_for(root), confirm_transfer=True)
    assert error.value.code == 'incompatible_checkpoint'
    bad = [c['component'] for c in error.value.report['checks'] if c['status'] == 'incompatible']
    assert bad == ['network architecture']
    assert not [r for r in runs.list_runs(roots_for(root), root) if r['mode'] == 'fine_tune']   # no run was created


def test_code_digest_change_blocks_resume_but_only_warns_for_transfer(source_run):
    _, meta = latest(source_run[1])
    changed = json.loads(json.dumps(meta))
    changed['contract']['code_sha256'] = '0' * 64            # as if a file under src/analog_optimizer/ had changed
    contract = meta['contract']
    strict = ckpt.check_compatibility(changed, mode='resume', task_definition_hash=meta['task_definition_hash'], contract=contract)
    digest = next(c for c in strict['checks'] if c['component'] == 'optimizer source code digest')
    assert not strict['compatible'] and digest['status'] == 'incompatible' and strict['suggestion'] == 'fine_tune'
    assert 'src/analog_optimizer/' in digest['detail'] and 'exact match' in digest['detail']
    for mode in ('fine_tune', 'frozen'):
        report = ckpt.check_compatibility(changed, mode=mode, task_definition_hash='other-task', contract=contract)
        digest = next(c for c in report['checks'] if c['component'] == 'optimizer source code digest')
        assert report['compatible'] and digest['status'] == 'warning' and 'provenance' in digest['detail']


def test_node_count_and_action_dimension_are_not_compatibility_criteria(source_run):
    _, meta = latest(source_run[1])
    report = ckpt.check_compatibility(meta, mode='fine_tune', task_definition_hash='another', contract=meta['contract'])
    components = ' '.join(c['component'] for c in report['checks']).lower()
    assert 'node' not in components and 'dimension' not in components and report['compatible']


# ------------------------------------------------------------------------------- fine_tune
def test_fine_tune_needs_confirmation_for_a_new_task_and_records_its_parent(source_run):
    root, layout = source_run
    config = transfer_config(root, layout, 'fine_tune', threshold=0.97, project=dict(task_name='target'))
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(config, roots_for(root))
    assert error.value.code == 'confirm_transfer' and error.value.report['requires_confirmation']
    source_digest_before = latest(layout)[1]['weight_sha256']
    target, state = execute(config, root, confirm_transfer=True)
    assert state == 'completed' and target.run_dir != layout.run_dir                   # a NEW run
    manifest = read_json(target.manifest)
    assert manifest['parent']['run_id'] == read_json(layout.manifest)['run_id'] and manifest['parent']['relation'] == 'fine_tune'
    policy = manifest['segments'][0]['load_policy']
    assert 'actor (encoder + head)' in policy['loaded'] and 'twin critics' in policy['loaded']
    assert any('replay_buffer (new' in r for r in policy['reset']) and any('task_counters' in r for r in policy['reset'])
    assert any('No source replay data' in n for n in policy['notes'])
    s = summary(target)
    assert s['totals']['candidate_evaluations_charged'] == 12                            # NEW target-task counters
    assert manifest['seeds'] == dict(manifest['seeds'], target_seed=11, pretrain_seed=7, pretrain_seed_origin='source_run_manifest')
    assert s['source_model_cost']['status'] == 'known' and s['source_model_cost']['evaluations_charged'] == 24
    assert 'adapt' in {e['phase'] for e in rows(target, 'evaluations')}
    assert latest(layout)[1]['weight_sha256'] == source_digest_before                    # the source is never overwritten
    assert ckpt.verify_files(latest(layout)[0]) == []
    # the target replay holds target-task experience only
    payload = torch.load(latest(target)[0] / 'training_state.pt', map_location='cpu', weights_only=False)
    source_ids = {t['candidate_id'] for t in rows(layout, 'transitions')}
    assert payload['replay']['items'] and not source_ids & {t.candidate_id for t in payload['replay']['items']}


def test_transfer_to_a_different_topology_and_action_dimension(source_run):
    root, layout = source_run                                   # source: the OTA5, 3 action variables
    fix_one = lambda raw: next(p for p in raw['parameters'] if not p.get('binding_group')).update(optimized=False)
    with other_circuits('toy_ldo', 'toy_opamp_two_stage') as (ldo, ota7):      # two other circuits (toy, record 7.128)
        for task, dimensions, mutate in ((ldo, 1, None), (ota7, 2, fix_one)):
            config = transfer_config(root, layout, 'fine_tune', task=task, project=dict(task_name=task.split(':')[1]), mutate=mutate)
            target, state = execute(config, root, confirm_transfer=True)
            assert state == 'completed', summary(target)['error']
            step = next(t for t in rows(target, 'transitions'))
            assert len(step['action']) == dimensions
            parameters = [p for p in rows(target, 'parameters') if p['role'] == 'independent']
            assert len({p['variable_id'] for p in parameters if p['raw_policy_action'] is not None}) == dimensions
            assert summary(target)['totals']['gradient_updates'] > 0


def test_encoder_only_transfer_critic_reset_and_frozen_encoder(source_run):
    root, layout = source_run
    weights = ckpt.load_weights(latest(layout)[0])
    config = transfer_config(root, layout, 'fine_tune', threshold=0.97, project=dict(task_name='ablation'),
                             advanced=dict(encoder_only_transfer=True, reset_critic=True, freeze_encoder=True,
                                           reset_temperature=True))
    target, state = execute(config, root, confirm_transfer=True)
    assert state == 'completed'
    policy = read_json(target.manifest)['segments'][0]['load_policy']
    assert policy['loaded'] == ['actor.encoder'] and 'actor.head (random)' in policy['reset']
    assert 'critics (random)' in policy['reset'] and any('temperature' in r for r in policy['reset'])
    assert policy['frozen_modules'] == ['actor.encoder', 'critics[0].encoder', 'critics[1].encoder']
    after = ckpt.load_weights(latest(target)[0])
    assert summary(target)['totals']['gradient_updates'] > 0
    encoder = [k for k in after['actor'] if k.startswith('encoder.')]
    head = [k for k in after['actor'] if k.startswith('head.')]
    assert encoder and all(torch.equal(after['actor'][k], weights['actor'][k]) for k in encoder)     # stayed frozen
    assert any(not torch.equal(after['actor'][k], weights['actor'][k]) for k in head)               # heads did learn
    critic_encoder = [k for k in after['critics'] if '.encoder.' in k]
    assert any(not torch.equal(after['critics'][k], weights['critics'][k]) for k in critic_encoder)  # reset => not the source


def test_continual_learning_needs_an_explicit_label(source_run):
    root, layout = source_run
    first = transfer_config(root, layout, 'fine_tune', threshold=0.97, project=dict(task_name='test_a'),
                            research=dict(split='test'))
    adapted, _ = execute(first, root, confirm_transfer=True)
    second = transfer_config(root, adapted, 'fine_tune', threshold=0.98, project=dict(task_name='test_b'),
                             research=dict(split='test'))
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(second, roots_for(root), confirm_transfer=True)
    assert error.value.code == 'continual_learning'             # default: every test task starts from the fixed source
    second.run.continual_learning = True
    chained, state = execute(second, root, confirm_transfer=True)
    assert state == 'completed'
    cost = summary(chained)['source_model_cost']
    assert [link['evaluations_charged'] for link in cost['provenance_chain']] == [12, 24] and cost['evaluations_charged'] == 36


# ------------------------------------------------------------------------------- frozen
@pytest.mark.parametrize('action, source_name', [('deterministic', 'mean_policy'), ('sampled', 'sampled_policy')])
def test_frozen_changes_nothing_and_writes_no_fictitious_updates(source_run, action, source_name):
    root, layout = source_run
    config = transfer_config(root, layout, 'frozen', project=dict(task_name=f'frozen_{action}'), run=dict(frozen_action=action))
    target, state = execute(config, root)
    assert state == 'completed'
    s, manifest = summary(target), read_json(target.manifest)
    assert s['totals']['gradient_updates'] == 0 and rows(target, 'learner_updates') == []
    assert manifest['execution']['frozen_action'] == action                       # deterministic vs sampled is recorded
    source_meta, target_meta = latest(layout)[1], latest(target)[1]
    assert target_meta['weight_sha256'] == source_meta['weight_sha256']           # weights, alpha: unchanged
    assert torch.equal(ckpt.load_weights(latest(target)[0])['log_alpha'], ckpt.load_weights(latest(layout)[0])['log_alpha'])
    evaluations = rows(target, 'evaluations')
    steps = [e for e in evaluations if e['phase'] == 'frozen_eval']
    assert steps and {e['action_source'] for e in steps} == {source_name}
    assert {e['policy_version'] for e in steps} == {source_meta['counters']['learner_updates']}
    assert 'warmup' not in {e['phase'] for e in evaluations}                       # no random exploration either
    assert target_meta['restoration_capability'] == 'full_state' and target_meta['not_applicable_components']
    transitions = rows(target, 'transitions')
    assert transitions and not any(t['replay_admitted'] for t in transitions)      # archived, never trained on
    assert s['source_model_cost']['evaluations_charged'] == 24


def test_a_paused_frozen_run_can_continue(source_run):
    root, layout = source_run
    config = transfer_config(root, layout, 'frozen', project=dict(task_name='frozen_resume'), run=dict(max_evaluations=6))
    target, _ = execute(config, root)
    more = config.model_copy(deep=True)
    more.run.mode, more.run.max_evaluations, more.run.model_source.run_dir = 'resume', 10, str(target.run_dir)
    again, _ = runs.prepare_run(more, roots_for(root))
    from helpers import run_prepared
    assert run_prepared(again) == 'completed'
    s = summary(target)
    assert s['totals']['candidate_evaluations_charged'] == 10 and s['totals']['gradient_updates'] == 0 and s['mode'] == 'frozen'
    assert latest(target)[1]['weight_sha256'] == latest(layout)[1]['weight_sha256']


def test_mode_suggestions(source_run):
    root, layout = source_run
    same = make_config(root, run=dict(max_evaluations=24, seed=7), project=dict(task_name='source'))
    assert runs.suggest_mode(same)['mode'] == 'scratch'
    assert runs.suggest_mode(same, layout.run_dir) == dict(mode='resume', reason='Full training state exists for the same task.',
                                                           requires_confirmation=False)
    other = make_config(root, threshold=0.5)
    suggestion = runs.suggest_mode(other, layout.run_dir)
    assert suggestion['mode'] == 'fine_tune' and suggestion['requires_confirmation']


# ------------------------------------------------------------------------------- replay options
def test_without_replay_snapshots_checkpoints_are_weights_only_and_resume_is_refused(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=10), output=dict(save_replay_snapshots=False))
    layout, _ = execute(config, tmp_path)
    meta = latest(layout)[1]
    assert meta['restoration_capability'] == 'weights_only' and 'replay_snapshot' in meta['missing_components'][0]
    assert summary(layout)['output']['resumability'] == 'weights_only'
    resume = config.model_copy(deep=True)
    resume.run.mode, resume.run.max_evaluations, resume.run.model_source.run_dir = 'resume', 20, str(layout.run_dir)
    with pytest.raises(runs.RunRejected) as error:
        runs.prepare_run(resume, roots_for(tmp_path))
    failed = [c['component'] for c in error.value.report['checks'] if c['status'] == 'incompatible']
    assert failed == ['restoration capability']
    assert rows(layout, 'transitions')                       # the archive is an independent switch and still complete


def test_archive_and_replay_snapshot_are_independent_switches(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=10), output=dict(save_transition_archive=False))
    layout, _ = execute(config, tmp_path)
    assert rows(layout, 'transitions') == [] and rows(layout, 'states') == []
    assert latest(layout)[1]['restoration_capability'] == 'full_state'          # replay snapshot unaffected


# ------------------------------------------------------------------------------- trajectory reload
def test_complete_archive_outlives_the_finite_replay_buffer(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=26), advanced=dict(replay_capacity=5))
    layout, _ = execute(config, tmp_path)
    meta = latest(layout)[1]
    archived = rows(layout, 'transitions')
    assert meta['replay']['size'] == 5 and meta['replay']['evicted'] == meta['replay']['insertions'] - 5 > 0
    assert len(archived) == meta['replay']['insertions'] > 5                     # nothing evicted from the archive
    manifest = read_json(latest(layout)[0] / 'replay_buffer' / 'manifest.json')
    assert 'no longer holds the complete history' in manifest['note']
    assert set(manifest['member_candidate_ids']) <= {t['candidate_id'] for t in archived}


def test_transitions_reload_as_valid_optimizer_objects_without_waveforms_or_work_files(tmp_path):
    from analog_optimizer.training.replay import Transition
    config = make_config(tmp_path, run=dict(max_evaluations=16))
    layout, _ = execute(config, tmp_path)
    directory, meta = latest(layout)
    saved = torch.load(directory / 'training_state.pt', map_location='cpu', weights_only=False)['replay']['items']
    shutil.rmtree(layout.work); shutil.rmtree(layout.waveforms)                 # reload needs neither
    loader = TrajectoryLoader(layout.run_dir)
    transitions = loader.transitions()                                          # validate() runs on every one
    assert len(transitions) == len(rows(layout, 'transitions')) and all(isinstance(t, Transition) for t in transitions)
    reloaded = {t.candidate_id: t for t in transitions}
    for original in saved:                                                      # bit-exact replay items
        assert reloaded[original.candidate_id].fingerprint() == original.fingerprint()
    current, following = loader.training_batch(transitions[:4])                 # real network inputs
    learner = modes._new_learner(meta['experiment'], modes.model_config_from(config.run.network),
                                 modes.sac_config_from(config.run.advanced), None)
    with torch.no_grad():
        assert learner.actor.sample(current).actions.shape[0] == int(current.action_counts.sum())
    state = loader.state_rows()[rows(layout, 'transitions')[0]['state_ref']]
    assert state['group_ids'] == ['input_pair_width', 'mirror_pair_width', 'tail_width'] and state['group_mutable'] == [True, True, True]
    assert len(state['members']) == 5 and state['metric_ids'] == ['score'] and state['normalizer_version']
    assert len(loader.state_rows()) == len({s['state_id'] for s in rows(layout, 'states')})   # de-duplicated


def test_effective_config_reloads_into_the_same_task(tmp_path):
    config = make_config(tmp_path, run=dict(max_evaluations=4))
    layout, _ = execute(config, tmp_path)
    reloaded = schema.WorkbenchConfig.model_validate(read_json(layout.effective_config))
    manifest = read_json(layout.manifest)
    assert schema.task_definition_hash(reloaded) == manifest['task_definition_hash']
    assert schema.config_hash(reloaded) == manifest['config_sha256']
    for key in ('experiment_id', 'run_id', 'task_id', 'comparison_pair_id', 'task_order', 'run_kind', 'mode', 'mock',
                'circuit', 'test_conditions', 'definitions', 'architecture', 'source_model', 'research', 'seeds',
                'initial_dimensions', 'initial_dimensions_sha256', 'budgets', 'execution', 'code', 'environment',
                'created_utc', 'parent', 'output'):
        assert key in manifest, key
    assert manifest['source_model']['cost_status'] == 'not_applicable' and manifest['code']['git_commit']
    assert set(manifest['seeds']) >= {'target_seed', 'pretrain_seed'}            # never one ambiguous seed field
