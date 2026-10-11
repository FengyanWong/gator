"""Offline archive pooling: no real backend, no source mutation, no held-out learning."""
from collections import Counter, defaultdict

import pytest

from gator_workbench import checkpoints, pretrain
from gator_workbench.compile import build_spec_schema
from gator_workbench.storage.atomic import read_json
from helpers import execute, make_config, other_circuits

pytestmark = pytest.mark.xdist_group('test_wb_pretrain')


@pytest.fixture(scope='module')
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp('offline-sources')
    def upper_goal(raw):
        raw['targets'][0].update(constraint='<=', lower=None, upper=0.95)
    a, state = execute(make_config(root, run=dict(max_evaluations=24), mutate=upper_goal,
                                   advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
    assert state == 'completed'
    with other_circuits('toy_ldo') as (task,):
        b, state = execute(make_config(root, task=task, run=dict(max_evaluations=24),
                                      advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3)), root)
        assert state == 'completed'
    return a, b


def request_for(sources):
    return dict(origin='synthetic', seed=7, holdout_fraction=0.2,
                runs=[dict(run_dir=str(s.run_dir), archive_sha256=pretrain.archive_identity(s.run_dir)) for s in sources],
                updates=3, batch_size=3, checkpoint_every=2,
                model=dict(hidden_dim=16, heads=2, layers=1),
                sac=dict(gamma=0., learning_rate=1e-3, initial_alpha=0.01))


def test_registry_conflicts_and_custom_schema_compatibility(sources, tmp_path):
    a, b = [('x', 'V', 1.)], [('x', 'V', 2.), ('y', 'A', 0.1)]
    with pytest.raises(ValueError, match='override required'):
        pretrain.shared_registry([a, b], {})
    with pytest.raises(ValueError, match='Conflicting units'):
        pretrain.shared_registry([a, [('x', 'A', 1.)]], {'x': 1.})
    schema = pretrain.shared_registry([b, a], {'x': 1.5})
    config = make_config(tmp_path)
    raw = config.model_dump()
    raw['run']['advanced']['spec_registry'] = [dict(metric_id=n, unit=u, reference=r) for n, u, r in schema.metrics]
    assert build_spec_schema(type(config).model_validate(raw)) == schema


def test_a_task_pooled_under_several_target_sets_is_re_scored_under_each_and_a_row_keeps_its_kind(sources):
    """Record 7.312 (the transfer experiment's multi-target models): `relabel_targets` pools every archived design of a
    task once as recorded and once more under each target set, each copy re-scored under its own limits - the limits a
    network that reads its specs as inputs is shown."""
    from analog_optimizer.measurements.specs import MetricSpec
    task = 'synthetic:gpdk045_ota5'
    plain = pretrain.prepare_pool(request_for(sources))
    request = request_for(sources)
    request['relabel_targets'] = {task: [{'score': {'upper': 0.8}}, {'score': {'upper': 0.5}}]}
    pool = pretrain.prepare_pool(request)
    recorded = len(plain.training[task]) + len(plain.validation[task])
    assert len(pool.training[task]) + len(pool.validation[task]) == 3 * recorded and pool.audit['relabeled'] == 2 * recorded
    assert pool.audit['relabel_target_sets'] == {task: 2} and 'relabel_target_sets' not in plain.audit
    rows = [r for r in pool.audit['split'] if r['task'] == task]
    assert Counter(r.get('target_set') for r in rows) == {None: recorded, 1: recorded, 2: recorded}
    assert all(r['relabeled'] == ('target_set' in r) for r in rows)
    by_candidate = defaultdict(set)
    for r in rows:
        by_candidate[r['candidate_id']].add(r['subset'])
    assert all(len(subsets) == 1 for subsets in by_candidate.values())            # a design and its copies stay on one side
    uppers = Counter(next(s.upper for s in t.observation.specs if s.metric_id == 'score') for t in pool.training[task] + pool.validation[task])
    assert uppers == {0.95: recorded, 0.8: recorded, 0.5: recorded}
    assert all(t.reward == t.next_observation.evaluation.reward for t in pool.training[task])      # each under its own limits
    assert len({t.reward for t in pool.training[task]}) > len({t.reward for t in plain.training[task]})
    # the other task of the pool is as it was, and the old one-target relabelling is unchanged beside it
    assert [t.reward for t in pool.training['synthetic:toy_ldo']] == [t.reward for t in plain.training['synthetic:toy_ldo']]
    # a row keeps its kind, and a scale that was the size of the limit follows the limit
    row = lambda **k: MetricSpec(**dict(dict(metric_id='x', unit='V', comparator='max', scale=1.0), **k))
    specs = (row(metric_id='p', upper=0.5, scale=0.5), row(metric_id='g', comparator='min', lower=30.0, scale=30.0),
             row(metric_id='f', comparator='range', lower=0.95, upper=1.05, scale=1.05), row(metric_id='s', upper=0.5, scale=0.2))
    moved = {s.metric_id: s for s in pretrain.retargeted_specs(specs, dict(p=dict(upper=0.29), g=dict(lower=31.0), f=dict(lower=1.14, upper=1.26),
                                                                           s=dict(upper=0.3)), 'a task')}
    assert (moved['p'].upper, moved['p'].scale) == (0.29, 0.29) and (moved['g'].lower, moved['g'].scale) == (31.0, 31.0)
    assert (moved['f'].lower, moved['f'].upper, moved['f'].scale) == (1.14, 1.26, 1.26) and moved['f'].comparator == 'range'
    assert (moved['s'].upper, moved['s'].scale) == (0.3, 0.2)                      # a stated scale stays
    for changes, words in ((dict(p=dict(lower=0.1)), 'has no lower limit to move'), (dict(g=dict(upper=40.0)), 'has no upper limit to move'),
                           (dict(f=dict(lower=1.2)), 'are not a range'), (dict(nobody=dict(upper=1.0)), 'Relabel metric absent')):
        with pytest.raises(ValueError, match=words):
            pretrain.retargeted_specs(specs, changes, 'a task')
    for bad, words in (({task: []}, 'must be a list of target sets'), ({task: [{}]}, 'must be a list of target sets'),
                       ({task: [{'score': {'at_most': 1.0}}]}, 'names "lower", "upper" or both'), ({'synthetic:nobody': [{'score': {'upper': 1.0}}]}, 'absent from pool')):
        with pytest.raises(ValueError, match=words):
            pretrain.prepare_pool(dict(request_for(sources), relabel_targets=bad))


def test_a_scale_the_task_states_stays_when_its_limit_is_moved_even_when_it_equals_that_limit(tmp_path):
    """Record 7.322: the rule told a stated scale from an empty Scale box by its number alone, so a scale typed in and
    equal to the size of its limit was taken for an empty box and moved with the limit - the relabelled copies were
    scored on another scale than the same task saved with the new limit (the online run of that configuration)."""
    from dataclasses import replace
    from gator_workbench.compile import build_specs
    task = 'synthetic:gpdk045_ota5'

    def stated(raw, upper=0.95):
        raw['targets'][0].update(constraint='<=', lower=None, upper=upper, normalization_scale=0.95)
    recorded = make_config(tmp_path, run=dict(max_evaluations=24), mutate=stated,
                           advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3))
    source, state = execute(recorded, tmp_path)
    assert state == 'completed'
    request = request_for([source])
    request['relabel_targets'] = {task: [{'score': {'upper': 0.5}}]}
    pool = pretrain.prepare_pool(request)
    moved = [t for t in pool.training[task] + pool.validation[task] if t.observation.specs[0].upper == 0.5]
    assert moved and {t.observation.specs[0].scale for t in moved} == {0.95}                  # it had become 0.5
    # the same designs under the task saved with the new limit - what an online run of that configuration scores
    online = build_specs(make_config(tmp_path, mutate=lambda raw: stated(raw, upper=0.5)))[0]
    assert moved[0].observation.specs == online
    assert all(t.reward == replace(t.next_observation, specs=online).evaluation.reward for t in moved)
    assert any(t.reward != replace(t.next_observation, specs=(replace(online[0], scale=0.5),)).evaluation.reward for t in moved)
    assert pretrain.stated_scales(read_json(source.effective_config)) == {'score'}
    # an empty Scale box still follows the limit, and the rule without the configuration is the one it was
    from analog_optimizer.measurements.specs import MetricSpec
    spec = (MetricSpec(metric_id='p', unit='V', comparator='max', scale=0.5, upper=0.5),)
    assert pretrain.retargeted_specs(spec, dict(p=dict(upper=0.3)), 'a task')[0].scale == 0.3
    assert pretrain.retargeted_specs(spec, dict(p=dict(upper=0.3)), 'a task', stated={'p'})[0].scale == 0.5
    # the rehearsal snapshot of the pool re-scores its copies the same way
    from gator_workbench.rehearsal import build_snapshot
    import gzip
    import json
    pretrain.execute(request, tmp_path / 'mock' / 'offline')
    build_snapshot(tmp_path / 'mock' / 'offline', tmp_path / 'mock' / 'rehearsal', capacity=64)
    from analog_optimizer.recording import codec
    from analog_optimizer.training.replay import Transition
    kept = [json.loads(line) for line in gzip.open(tmp_path / 'mock' / 'rehearsal' / 'transitions.jsonl.gz', 'rt')]
    copies = [Transition(**codec.untree(row['transition'])) for row in kept if row['selection'].get('target_set') == 1]
    assert copies and all(copy.observation.specs == online for copy in copies)


def test_split_is_reproducible_and_keeps_episodes_and_relabels_together(sources):
    request = request_for(sources)
    request['relabel_upper'] = {'synthetic:gpdk045_ota5': {'score': 0.8}}
    pool = pretrain.prepare_pool(request)
    again = pretrain.prepare_pool(request)
    assert pool.audit['split'] == again.audit['split']
    episodes = defaultdict(set)
    candidates = defaultdict(set)
    for row in pool.audit['split']:
        episodes[(row['run_id'], row['worker_id'], row['episode_id'])].add(row['subset'])
        candidates[row['candidate_id']].add(row['subset'])
    assert all(len(s) == 1 for s in episodes.values())
    assert all(len(s) == 1 for s in candidates.values())
    assert pool.audit['relabeled'] > 0
    assert pool.audit['source_evaluations'] == 48
    assert pool.audit['new_simulator_launches'] == 0
    for task in pool.training:
        assert pool.training[task] and pool.validation[task]
        for transition in pool.training[task] + pool.validation[task]:
            assert transition.observation.specs == transition.next_observation.specs
            assert transition.reward == transition.next_observation.evaluation.reward
    assert any(t.observation.specs[0].upper == 0.8 for t in pool.training['synthetic:gpdk045_ota5'])


def test_sampler_balances_tasks_across_batch_boundaries():
    sampler = pretrain.BalancedSampler({'a': ['a1'], 'b': ['b1', 'b2'], 'c': ['c1']}, 2)
    drawn = [x for _ in range(6) for x in sampler.sample(2)]
    assert Counter(x[0] for x in drawn) == dict(a=4, b=4, c=4)
    again = pretrain.BalancedSampler({'a': ['a1'], 'b': ['b1', 'b2'], 'c': ['c1']}, 2)
    assert drawn == again.sample(12)


def test_duplicate_source_and_changed_archive_rejected(sources):
    request = request_for(sources)
    request['runs'].append(request['runs'][0])
    with pytest.raises(ValueError, match='Duplicate source run'):
        pretrain.prepare_pool(request)
    request = request_for(sources)
    request['runs'][0]['archive_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Archive changed'):
        pretrain.prepare_pool(request)


def test_real_pool_rejects_mock_sources(sources):
    request = request_for(sources)
    request['origin'] = 'real'
    with pytest.raises(ValueError, match='Origin mismatch'):
        pretrain.prepare_pool(request)


def test_mixed_reward_and_exact_rescore_gate(sources, monkeypatch):
    from dataclasses import replace
    original = pretrain.TrajectoryLoader.transitions
    def changed(self):
        items = original(self)
        if self.run_dir == sources[1].run_dir:
            items[0] = replace(items[0], reward_settings=replace(items[0].reward_settings, margin_weight=0.7))
        return items
    monkeypatch.setattr(pretrain.TrajectoryLoader, 'transitions', changed)
    with pytest.raises(ValueError, match='Mixed reward settings'):
        pretrain.prepare_pool(request_for(sources))
    def changed_reward(self):
        items = original(self)
        items[0] = replace(items[0], reward=items[0].reward + 1e-13)
        return items
    monkeypatch.setattr(pretrain.TrajectoryLoader, 'transitions', changed_reward)
    with pytest.raises(ValueError, match='exactly reproduce'):
        pretrain.prepare_pool(request_for(sources))


def test_training_saves_verified_weights_and_leaves_sources_untouched(sources, tmp_path):
    request = request_for(sources)
    before = [pretrain.archive_identity(s.run_dir) for s in sources]
    output = tmp_path / 'mock' / 'offline'
    audit = pretrain.execute(request, output)
    assert read_json(output / 'status.json')['state'] == 'trained_unqualified'
    assert read_json(output / 'status.json')['updates'] == 3
    point = checkpoints.resolve_checkpoint(output, 'latest')
    assert checkpoints.verify_files(point) == []
    weights = checkpoints.load_weights(point)
    assert weights['updates'] == 3
    assert weights['contract']['spec_schema'] == audit['spec_schema'] or (
        weights['contract']['spec_schema']['metrics'] == [list(x) for x in audit['spec_schema']['metrics']])
    assert checkpoints.read_metadata(point)['restoration_capability'] == 'weights_only'
    curve = read_json(output / 'validation.json')
    assert [row['updates'] for row in curve] == [0, 2, 3]
    assert all(score['count'] > 0 and score['q1_mse'] >= 0 for score in curve[-1]['scores'].values())
    assert [pretrain.archive_identity(s.run_dir) for s in sources] == before
    with pytest.raises(FileExistsError):
        pretrain.execute(request, output)


def test_audit_only_and_output_origin(sources, tmp_path):
    request = request_for(sources)
    with pytest.raises(ValueError, match='mock/'):
        pretrain.execute(request, tmp_path / 'unlabeled')
    output = tmp_path / 'mock' / 'audit'
    pretrain.execute(request, output, audit_only=True)
    assert read_json(output / 'status.json')['state'] == 'audited'
    assert not (output / 'checkpoints').exists()


def test_own_model_can_use_the_general_registry(sources):
    request = request_for(sources[:1])
    pool = pretrain.prepare_pool(request)
    request['spec_registry'] = [dict(metric_id=n, unit=u, reference=r) for n, u, r in pool.schema.metrics]
    request['spec_registry'].append(dict(metric_id='extra', unit='V', reference=1.))
    own = pretrain.prepare_pool(request)
    assert len(own.schema.metrics) == len(pool.schema.metrics) + 1
    assert own.audit['split_sha256'] == pool.audit['split_sha256']
    request['spec_registry'] = [dict(metric_id='extra', unit='V', reference=1.)]
    with pytest.raises(ValueError, match='cover every source metric'):
        pretrain.prepare_pool(request)


def test_diagnostic_load_and_proposals(sources, tmp_path):
    from gator_workbench.offline_diagnostics import load_model, proposals
    request = request_for(sources)
    output = tmp_path / 'mock' / 'diagnostic'
    pretrain.execute(request, output)
    model, meta = load_model(checkpoints.resolve_checkpoint(output, 'latest'))
    pool = pretrain.prepare_pool(request)
    task = next(iter(pool.validation))
    observations = [pool.validation[task][0].observation]
    digest = checkpoints.weight_digest(model)
    rows = proposals(model, observations, best_recorded_reward=1., reward_rmse=.1)
    assert rows[0]['legal'] and 0 <= rows[0]['boundary_fraction'] <= 1
    assert model.updates == meta['counters']['learner_updates'] == 3
    assert checkpoints.weight_digest(model) == digest


def test_trajectory_candidate_subset(sources):
    from gator_workbench.trajectory import TrajectoryLoader
    loader = TrajectoryLoader(sources[0].run_dir)
    full = loader.transitions()
    selected = loader.transitions(candidate_ids={full[2].candidate_id})
    assert len(selected) == 1 and selected[0].fingerprint() == full[2].fingerprint()


@pytest.fixture(scope='module')
def rehearsal_artifact(sources, tmp_path_factory):
    from gator_workbench.rehearsal import build_snapshot, file_sha
    from gator_workbench.schema import RehearsalSettings
    root = tmp_path_factory.mktemp('rehearsal')
    output = root / 'mock' / 'offline'
    request = request_for(sources)
    request['relabel_upper'] = {'synthetic:gpdk045_ota5': {'score': 0.8}}
    pretrain.execute(request, output)
    snapshot = root / 'mock' / 'rehearsal'
    build_snapshot(output, snapshot, capacity=13)
    path = snapshot / 'manifest.json'
    return root, output, RehearsalSettings(pool_manifest=str(path), pool_sha256=file_sha(path))


def test_rehearsal_is_training_only_balanced_and_resumes_exactly(rehearsal_artifact):
    from gator_workbench.offline_diagnostics import load_model
    from gator_workbench.rehearsal import Rehearsal
    _, output, settings = rehearsal_artifact
    model, _ = load_model(checkpoints.resolve_checkpoint(output, 'latest'))
    replay = Rehearsal(settings, model, origin='synthetic', seed=2, batch_size=8)
    assert replay.source_size == replay.online_size == 4
    manifest, audit = read_json(settings.pool_manifest), read_json(output / 'pool.json')
    heldout = {r['candidate_id'] for r in audit['split'] if r['subset'] == 'validation'}
    assert not heldout & {r['candidate_id'] for r in manifest['selection']}
    assert manifest['count'] == 13
    replay.sampler.sample(7)
    state = replay.state_dict()
    expected = [t.fingerprint() for t in replay.sampler.sample(23)]
    again = Rehearsal(settings, model, origin='synthetic', seed=99, batch_size=8)
    again.load_state_dict(state)
    assert expected == [t.fingerprint() for t in again.sampler.sample(23)]
    assert len(set(replay.sampler.counts.values())) == 1
    before = {id(t): t.fingerprint() for items in replay.sampler.training.values() for t in items}
    sample = replay.sampler.sample(4)
    update = replay.update(sample, digests=[replay.digests[id(t)] for t in sample])
    assert len(update['action_counts']) == 8
    assert before == {id(t): t.fingerprint() for items in replay.sampler.training.values() for t in items}


def test_rehearsal_contract_and_tamper_checks(rehearsal_artifact, tmp_path):
    import shutil
    from pathlib import Path
    from gator_workbench.offline_diagnostics import load_model
    from gator_workbench.rehearsal import Rehearsal, file_sha
    from gator_workbench.storage.atomic import write_json
    _, output, settings = rehearsal_artifact
    model, _ = load_model(checkpoints.resolve_checkpoint(output, 'latest'))
    def load(config):
        return Rehearsal(config, model, origin='synthetic', seed=2, batch_size=8)
    with pytest.raises(ValueError, match='checksum'):
        load(settings.model_copy(update=dict(pool_sha256='0' * 64)))
    with pytest.raises(ValueError, match='origin'):
        Rehearsal(settings, model, origin='real', seed=2, batch_size=8)
    copy = tmp_path / 'copy'
    shutil.copytree(Path(settings.pool_manifest).parent, copy)
    path = copy / 'manifest.json'
    manifest = read_json(path)
    manifest['spec_schema']['metrics'][0][2] *= 2
    write_json(path, manifest)
    with pytest.raises(ValueError, match='schema'):
        load(settings.model_copy(update=dict(pool_manifest=str(path), pool_sha256=file_sha(path))))
    manifest = read_json(settings.pool_manifest)
    write_json(path, manifest)
    with (copy / manifest['data_file']).open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        load(settings.model_copy(update=dict(pool_manifest=str(path), pool_sha256=file_sha(path))))


def test_rehearsal_engine_checkpoint_resume(rehearsal_artifact, sources):
    import torch
    from gator_workbench import schema
    from helpers import rows
    root, output, settings = rehearsal_artifact
    # Transfer offline weights, then exercise a full-state online resume including its source sampler.
    own_request = request_for(sources[:1])
    own = root / 'mock' / 'own'
    pretrain.execute(own_request, own)
    from gator_workbench.rehearsal import build_snapshot, file_sha
    snapshot = root / 'mock' / 'own-rehearsal'
    build_snapshot(own, snapshot, capacity=10)
    from gator_workbench.offline_publish import publish
    source = publish(own, root, label='own', review=dict(allow_planned_probes=True, reason='synthetic test'))
    rehearsal = dict(pool_manifest=str(snapshot / 'manifest.json'), pool_sha256=file_sha(snapshot / 'manifest.json'))
    config = make_config(root, run=dict(mode='fine_tune', max_evaluations=16,
        rehearsal=rehearsal, model_source=dict(run_dir=str(source.run_dir), checkpoint_id='latest')),
        advanced=dict(gamma=0., batch_size=4, warmup_transitions=4, episode_length=3,
                      spec_registry=read_json(own / 'spec_registry.json')))
    target, state = execute(config, root, confirm_transfer=True)
    assert state == 'completed'
    point = checkpoints.resolve_checkpoint(target.run_dir, 'latest')
    payload = torch.load(point / 'training_state.pt', weights_only=False)
    collector = payload['run_state']['collector']['rehearsal']
    assert sum(collector['counts'].values()) == payload['updates'] * 2
    source_ids = {r['candidate_id'] for r in read_json(snapshot / 'manifest.json')['selection']}
    assert not source_ids & {t.candidate_id for t in payload['replay']['items']}
    saved = read_json(target.effective_config)
    saved['run'].update(mode='resume', max_evaluations=20,
                        model_source=dict(run_dir=str(target.run_dir), checkpoint_id='latest'))
    resumed, state = execute(schema.WorkbenchConfig.model_validate(saved), root)
    assert state == 'completed' and resumed.run_dir == target.run_dir
    payload = torch.load(checkpoints.resolve_checkpoint(target.run_dir, 'latest') / 'training_state.pt', weights_only=False)
    assert sum(payload['run_state']['collector']['rehearsal']['counts'].values()) == payload['updates'] * 2
    assert len(rows(target, 'evaluations')) == 20


def test_offline_publication_readers_and_cost(rehearsal_artifact):
    from gator_workbench import modes, runs, training_series
    from gator_workbench.offline_publish import publish
    from helpers import roots_for
    root, output, _ = rehearsal_artifact
    layout = publish(output, root, label='general', review=dict(allow_planned_probes=True, reason='synthetic test'))
    listed = runs.list_runs(roots_for(root), root)
    model = next(m for m in checkpoints.saved_models(listed) if m['run_dir'] == str(layout.run_dir))
    assert model['resumability'] == 'weights_only' and model['evaluations'] == 0
    assert modes.source_cost(layout.run_dir)['evaluations_charged'] == 48
    assert runs.run_status(layout.run_dir)['state'] == 'completed'
    result = training_series.read_training(layout.run_dir)
    assert result and training_series.learner_record(layout.run_dir)['recorded'] is False
    with pytest.raises(FileExistsError):
        publish(output, root, label='general', review=dict(allow_planned_probes=True, reason='synthetic test'))


def test_rehearsal_settings_preserve_legacy_hashes(tmp_path):
    from gator_workbench.schema import WorkbenchConfig, config_hash
    config = make_config(tmp_path)
    raw = config.model_dump(mode='json')
    assert raw['run'].pop('rehearsal') is None
    assert config_hash(config) == config_hash(WorkbenchConfig.model_validate(raw))
    raw['run']['rehearsal'] = dict(pool_manifest='/pool/manifest.json', pool_sha256='0' * 64)
    with pytest.raises(ValueError, match='fine_tune'):
        WorkbenchConfig.model_validate(raw)
