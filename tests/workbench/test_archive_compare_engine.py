"""The archive comparison inside a run (docs/plan-bo-mobo-rl-archive-comparison.md; gator_workbench.engine_comparison): the
common first designs, the searches T0/T+ (`turbo_archive`) and M+ (`mobo`) proposing the designs, their save points,
an exact continuation and a continuation after a crash - on the MOCK task (the analytic toy backend: nothing here is a
circuit result). The M+ runs need BoTorch: they run in the comparison's own environment (~/gator/envs/archive-compare-venv)
and are skipped elsewhere."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random

import pytest
import torch

from analog_optimizer.parameters.actions import ActionMapper
from gator_workbench import checkpoints, runs, schema, tasks
from gator_workbench.archive_compare import coords, initial, runtime
from gator_workbench.compile import compile_task
from gator_workbench.storage.atomic import read_json, read_jsonl, write_json
from helpers import check, execute, issues, make_config, roots_for, rows, run_prepared, summary
from helpers import bridge_is_importable   # noqa: F401 - an imported fixture belongs to this module

NEVER = 1.5          # a score the toy backend never reaches: no episode ends early, each is 1 reset + 3 steps (4 evaluations)
FAST_MOBO = dict(num_restarts=2, raw_samples=32, mc_samples=16, maxiter=25, refit_every=4)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_designs(root, seed=101, mutate=None):
    """The MOCK task's common first designs for one rollout seed, written as the comparison's step 2 writes them."""
    config = make_config(root, mutate=mutate)
    compiled = compile_task(config, tasks.load_task(config.circuit).base_graph)
    groups = coords.group_rows(compiled)
    start = {g.id: g.value for g in compiled.graph.parameter_groups if g.mutable}
    designs = initial.initial_designs(ActionMapper(compiled.graph), groups, start, seed=seed)
    path = root / f'initial-seed{seed}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(designs))
    return dict(initial_designs=str(path), initial_designs_sha256=sha(path)), designs, groups


def search_config(root, block, *, optimizer='turbo_archive', lanes=1, evaluations=16, seed=101, output=None, mutate=None,
                  **run):
    return make_config(root, threshold=NEVER, mutate=mutate, output=output,
                       run=dict(dict(optimizer=optimizer, comparison=block, concurrency=lanes, max_evaluations=evaluations,
                                     seed=seed), **run))


def executed(layout):
    """Every evaluation in commit order: (its source, phase, executed group values, reward)."""
    values = {}
    for p in rows(layout, 'parameters'):
        if p['role'] == 'independent':
            values.setdefault(p['evaluation_id'], {})[p['variable_id']] = p['executed_value']
    return [(e['action_source'], e['phase'], values.get(e['evaluation_id']), e['reward'])
            for e in sorted(rows(layout, 'evaluations'), key=lambda e: e['commit_seq'])]


def steps_in_dispatch_order(layout):
    return [e for e in sorted(rows(layout, 'evaluations'), key=lambda e: e['dispatch_index']) if e['action_source'] != 'reset']


def resume(layout, root, evaluations):
    """Continue: the run's own configuration with a larger budget, as the page's Continue presses it."""
    raw = read_json(layout.effective_config)
    raw['run'].update(mode='resume', max_evaluations=evaluations,
                      model_source=dict(run_dir=str(layout.run_dir), checkpoint_id='latest'))
    again, _ = runs.prepare_run(schema.WorkbenchConfig.model_validate(raw), roots_for(root))
    assert again.run_dir == layout.run_dir
    return run_prepared(again)


def saved_search(layout):
    payload = torch.load(checkpoints.resolve_checkpoint(layout.run_dir, 'latest') / 'training_state.pt', weights_only=False)
    return payload['run_state']


def events(layout, name=None):
    return [e for e in read_jsonl(layout.logs / 'events.jsonl') if name is None or e['event'] == name]


# --------------------------------------------------------------------------------------------- T0 in a run
def test_a_t0_run_evaluates_its_start_then_the_common_designs_then_searches_and_trains_no_network(tmp_path):
    block, designs, _ = first_designs(tmp_path)
    layout, state = execute(search_config(tmp_path, block, lanes=2, evaluations=24), tmp_path)
    assert state == 'completed'
    evaluations = sorted(rows(layout, 'evaluations'), key=lambda e: e['dispatch_index'])
    assert evaluations[0]['phase'] == 'baseline' and evaluations[0]['action_source'] == 'reset'
    steps = steps_in_dispatch_order(layout)
    assert [e['action_source'] for e in steps[:8]] == ['common_initial'] * 8
    assert {e['phase'] for e in steps[:8]} == {'warmup'}
    assert {e['action_source'] for e in steps[8:]} == {'bayes_opt'} and {e['phase'] for e in steps[8:]} == {'search'}
    values = {}
    for p in rows(layout, 'parameters'):
        if p['role'] == 'independent':
            values.setdefault(p['evaluation_id'], {})[p['variable_id']] = p['executed_value']
    # the designs of the file, in its order, whatever lane took them
    assert [values[e['evaluation_id']] for e in steps[:8]] == [d['group_values'] for d in designs['designs']]
    assert rows(layout, 'learner_updates') == []                      # the network is neither asked nor trained
    started = events(layout, 'search_started')
    assert len(started) == 1 and started[0]['version'] == 'turbo_archive_v1' and started[0]['archived'] == 0
    assert started[0]['initial_designs'] == 8
    proposals = events(layout, 'search_proposal')
    assert len(proposals) == len(steps) - 8 and all(p['seconds'] >= 0 for p in proposals)
    # its save point holds the search, and it is no RL model
    run_state = saved_search(layout)
    assert run_state['collector']['comparison']['optimizer'] == 'turbo_archive'
    assert len(run_state['collector']['comparison']['proposer']['search']['X']) == len(steps)
    assert run_state['counters']['initial_given'] == 8
    assert checkpoints.read_metadata(checkpoints.resolve_checkpoint(layout.run_dir, 'latest'))['restoration_capability'] == 'full_state'
    manifest = read_json(layout.manifest)
    assert manifest['architecture']['optimizer'] == 'turbo_archive' and manifest['model_label'] is None
    assert checkpoints.saved_models(runs.list_runs(roots_for(tmp_path), tmp_path)) == []
    with pytest.raises(runs.RunRejected) as refused:
        checkpoints.describe(layout.run_dir)
    assert refused.value.code == 'no_rl_model'
    assert runs.continuation(layout.run_dir, max_evaluations=30)['eligible']


def test_a_search_stopped_and_continued_proposes_exactly_the_designs_of_one_run_through(tmp_path):
    block, _, _ = first_designs(tmp_path)
    straight, state = execute(search_config(tmp_path / 'straight', block, evaluations=32), tmp_path / 'straight')
    assert state == 'completed'
    halves, state = execute(search_config(tmp_path / 'halves', block, evaluations=16), tmp_path / 'halves')
    assert state == 'completed'
    assert resume(halves, tmp_path / 'halves', 32) == 'completed'
    assert executed(halves) == executed(straight)
    sources = [source for source, *_ in executed(straight)]
    assert sources.count('reset') == 8 and sources.count('common_initial') == 8 and sources.count('bayes_opt') == 16
    assert saved_search(halves)['collector']['comparison'] == saved_search(straight)['collector']['comparison']


def test_after_a_crash_the_search_is_told_again_what_the_run_committed_after_its_save_point(tmp_path):
    block, _, _ = first_designs(tmp_path)
    layout, state = execute(search_config(tmp_path, block, evaluations=32,
                                          output=dict(checkpoint_every_evaluations=8, keep_last_checkpoints=None)), tmp_path)
    assert state == 'completed'
    # as a crash leaves a run: its newest save point is an older one, its tables hold what came after
    older = next(d.name for d in layout.checkpoints.glob('ckpt-*')
                 if read_json(d / 'metadata.json')['data_cursor']['commit_seq'] == 16)
    latest = read_json(layout.checkpoints / 'latest.json')
    write_json(layout.checkpoints / 'latest.json', dict(latest, checkpoint_id=older, path=f'checkpoints/{older}',
                                                        commit_seq=16, kind='periodic'))
    assert len(saved_search(layout)['collector']['comparison']['proposer']['search']['X']) == 12
    assert resume(layout, tmp_path, 40) == 'completed'
    report = events(layout, 'resumed')[-1]
    assert report['comparison'] == dict(initial_given=8, retold=12, observations=24)
    assert report['search']['observations'] == 24
    after = executed(layout)
    assert len(after) == 40 and [source for source, *_ in after[32:]].count('bayes_opt') == 6
    assert len(saved_search(layout)['collector']['comparison']['proposer']['search']['X']) == 30


def test_a_search_run_charges_every_failure_but_fits_only_circuit_results(tmp_path):
    """A timeout is no evidence about the circuit: charged, its proposal settled, never fitted. A design that failed
    physically (invalid_design) is a circuit result: charged and fitted with the reward the task gives it."""
    from gator_workbench.archive_compare.mobo import SCORED_STATUSES
    block, _, _ = first_designs(tmp_path)
    layout, state = execute(search_config(tmp_path, block, evaluations=20), tmp_path,
                            scripts={'0': {3: 'timeout', 13: 'invalid_design', 18: 'timeout'}})
    assert state == 'completed'
    evaluations = rows(layout, 'evaluations')
    assert len(evaluations) == 20 and summary(layout)['totals']['candidate_evaluations_charged'] == 20
    steps = [e for e in evaluations if e['action_source'] != 'reset']
    assert sorted(e['status'] for e in steps if e['status'] != 'ok') == ['invalid_design', 'timeout', 'timeout']
    assert {e['action_source'] for e in steps if e['status'] == 'timeout'} == {'common_initial', 'bayes_opt'}
    search = saved_search(layout)['collector']['comparison']['proposer']['search']
    assert len(search['X']) == sum(e['status'] in SCORED_STATUSES for e in steps) == len(steps) - 2
    assert search['asked'] == 0                                      # every proposal settled, the timed-out one too


# --------------------------------------------------------------------------------------------- T+ and its archive
def test_a_t_plus_run_imports_its_pinned_archive_at_no_cost_and_another_file_is_refused(tmp_path):
    block, _, groups = first_designs(tmp_path)
    generator = random.Random(4)
    u = [[generator.random() for _ in groups] for _ in range(30)]
    archive = dict(format=runtime.TURBO_ARCHIVE_FORMAT, case='mock', view='panel_a', group_ids=[g['id'] for g in groups],
                   design_keys=[f'd{i}' for i in range(30)], u=u, reward=[-sum((x - 0.7) ** 2 for x in p) for p in u])
    path = tmp_path / 'turbo-panel_a.json'
    path.write_text(json.dumps(archive))
    pinned = dict(block, archive=str(path), archive_sha256=sha(path))
    layout, state = execute(search_config(tmp_path, pinned, evaluations=12), tmp_path)
    assert state == 'completed'
    started = events(layout, 'search_started')[0]
    assert started['archived'] == 30 and started['archived_failed'] == 0 and started['online'] == 0
    assert summary(layout)['totals']['candidate_evaluations_charged'] == 12          # the archive costs nothing
    run_state = saved_search(layout)
    assert len(run_state['collector']['comparison']['proposer']['search']['source_y']) == 30
    path.write_text(json.dumps(dict(archive, reward=archive['reward'][::-1])))        # another file under the pinned name
    report, _ = check(search_config(tmp_path, pinned))
    assert 'comparison_file_not_pinned' in issues(report, 'blocker')
    with pytest.raises(runs.RunRejected):
        runs.prepare_run(search_config(tmp_path, pinned), roots_for(tmp_path))
    other = dict(archive, group_ids=archive['group_ids'][::-1])                       # pinned, but of another domain
    path.write_text(json.dumps(other))
    compiled = compile_task(search_config(tmp_path, pinned), tasks.load_task(make_config(tmp_path).circuit).base_graph)
    with pytest.raises(runtime.ComparisonFileError, match='groups'):
        runtime.build_proposer(search_config(tmp_path, dict(pinned, archive_sha256=sha(path))), compiled)


# --------------------------------------------------------------------------------------------- SAC with the common designs
def test_a_sac_run_of_the_comparison_starts_with_the_common_designs_and_then_learns(tmp_path):
    block, designs, _ = first_designs(tmp_path)
    config = make_config(tmp_path, threshold=NEVER, run=dict(comparison=block, concurrency=1, max_evaluations=24, seed=101),
                         advanced=dict(warmup_transitions=0))
    layout, state = execute(config, tmp_path)
    assert state == 'completed'
    steps = steps_in_dispatch_order(layout)
    assert [e['action_source'] for e in steps[:8]] == ['common_initial'] * 8
    assert {e['action_source'] for e in steps[8:]} == {'sac_policy'}
    assert rows(layout, 'learner_updates')
    assert 'comparison' not in saved_search(layout)['collector'] and saved_search(layout)['counters']['initial_given'] == 8


# --------------------------------------------------------------------------------------------- the checks before a run
def test_the_checks_refuse_a_comparison_run_that_would_run_otherwise_than_the_plan_says(tmp_path):
    block, _, _ = first_designs(tmp_path)
    report, _ = check(make_config(tmp_path, run=dict(comparison=block)))           # SAC with its random warm-up still on
    assert 'comparison_designs_replace_warmup' in issues(report, 'blocker')
    report, _ = check(make_config(tmp_path, run=dict(comparison=block), advanced=dict(warmup_transitions=0)))
    assert not issues(report, 'blocker')
    report, _ = check(make_config(tmp_path, run=dict(comparison=block, optimizer='bayes')))
    assert 'comparison_not_for_bayes' in issues(report, 'blocker')
    report, _ = check(search_config(tmp_path, block, mode='frozen'))
    assert 'comparison_search_needs_scratch' in issues(report, 'blocker')
    report, _ = check(search_config(tmp_path, block))
    assert 'comparison_search_run' in issues(report) and not issues(report, 'blocker')
    report, _ = check(search_config(tmp_path, block, output=dict(save_checkpoints=False)))
    assert 'comparison_search_not_resumable' in issues(report, 'warning')
    with pytest.raises(ValueError, match='needs run.comparison'):
        make_config(tmp_path, run=dict(optimizer='turbo_archive'))
    with pytest.raises(ValueError, match='exactly two'):
        search_config(tmp_path, block, optimizer='mobo')
    with pytest.raises(ValueError, match='read only by'):
        make_config(tmp_path, run=dict(comparison=dict(block, archive=block['initial_designs'],
                                                       archive_sha256=block['initial_designs_sha256'])))
    objectives = [dict(metric='score', orientation='maximize', base_limit=0.0),
                  dict(metric='cost', orientation='minimize', base_limit=2.0)]
    report, _ = check(search_config(tmp_path, dict(block, objectives=objectives), optimizer='mobo'))
    assert ('mobo_needs_botorch' in issues(report, 'blocker')) == (importlib.util.find_spec('botorch') is None)


# --------------------------------------------------------------------------------------------- M+ (BoTorch only)
def two_objectives(raw):
    """A second spec row on the toy score, so that M+ has two objectives: score up, cost = score squared down (MOCK: a
    test of the plumbing, not a front worth having)."""
    raw['targets'].append(dict(raw['targets'][0], metric_id='cost', equation='m_score * m_score', constraint='<=',
                               lower=None, upper=4.0))


MOBO_OBJECTIVES = [dict(metric='score', orientation='maximize', base_limit=0.0),
                   dict(metric='cost', orientation='minimize', base_limit=4.0)]


def mobo_config(root, block, **options):
    return search_config(root, dict(block, objectives=MOBO_OBJECTIVES, settings=FAST_MOBO), optimizer='mobo',
                         mutate=two_objectives, **options)


def test_an_m_plus_run_is_told_every_output_and_values_its_designs_with_those_in_flight(tmp_path):
    pytest.importorskip('botorch')
    block, _, _ = first_designs(tmp_path, mutate=two_objectives)
    layout, state = execute(mobo_config(tmp_path, block, lanes=2, evaluations=20), tmp_path)
    assert state == 'completed'
    steps = steps_in_dispatch_order(layout)
    assert [e['action_source'] for e in steps[:8]] == ['common_initial'] * 8 and len(steps) > 8
    proposals = events(layout, 'search_proposal')
    assert len(proposals) == len(steps) - 8 and {p['source'] for p in proposals} == {'acquisition'}
    assert max(p['pending'] for p in proposals) >= 1                                # the other lane's design was in flight
    search = saved_search(layout)['collector']['comparison']['proposer']['search']
    assert search['archived'] == 0 and len(search['X']) == len(steps)
    assert all(y[0] is not None and y[1] is not None and y[-1] == 1.0 for y in search['Y'])     # score, cost, valid
    assert rows(layout, 'learner_updates') == []


def test_an_m_plus_run_stopped_and_continued_proposes_exactly_the_designs_of_one_run_through(tmp_path):
    pytest.importorskip('botorch')
    block, _, _ = first_designs(tmp_path, mutate=two_objectives)
    straight, state = execute(mobo_config(tmp_path / 'straight', block, evaluations=24), tmp_path / 'straight')
    assert state == 'completed'
    halves, state = execute(mobo_config(tmp_path / 'halves', block, evaluations=12), tmp_path / 'halves')
    assert state == 'completed'
    assert resume(halves, tmp_path / 'halves', 24) == 'completed'
    assert executed(halves) == executed(straight)
    assert saved_search(halves)['collector']['comparison'] == saved_search(straight)['collector']['comparison']


# --------------------------------------------------------------------------------------------- goal views of a saved task
def test_a_comparison_run_may_differ_from_its_saved_task_only_in_a_goal_views_four_fields(tmp_path, bridge_is_importable):
    """A saved task runs exactly as it was saved - except that a comparison run (run.comparison) scores the saved task's
    simulations under a goal view: its limits, stated scales and preferred direction (archive_compare.views.view_config).
    Any other difference of a Specs row, and any goal-view difference without the comparison block, is refused as before."""
    from task_save_support import saved_ring
    from gator_workbench.validation import validate
    cfg = saved_ring(tmp_path)
    path = tmp_path / 'first.json'
    path.write_text('{}')
    raw = cfg.model_dump(mode='json')
    raw['run']['comparison'] = dict(initial_designs=str(path), initial_designs_sha256=sha(path))
    raw['run'].setdefault('advanced', {})['warmup_transitions'] = 0
    view = schema.WorkbenchConfig.model_validate(raw)
    spec = view.targets[0]
    spec.lower = spec.lower * 1.05                                       # a tightened limit ...
    spec.normalization_scale = abs(spec.lower)                           # ... its stated scale ...
    spec.direction_after_feasible = 'maximize'                           # ... and the preferred direction
    codes = {i.code: i.level for i in validate(view).issues}
    assert 'task_not_saved' not in codes and codes.get('comparison_goal_view') == 'info'
    other = view.model_copy(deep=True)
    other.targets[0].soft_weight = 2.0                                   # not a goal-view field
    assert 'task_not_saved' in {i.code for i in validate(other).issues}
    plain = cfg.model_copy(deep=True)
    plain.targets[0].lower = spec.lower                                  # the same change without a comparison block
    issues_ = {i.code for i in validate(plain).issues}
    assert 'task_not_saved' in issues_ and 'comparison_goal_view' not in issues_
