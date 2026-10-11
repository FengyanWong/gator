"""Bayesian optimization as a second search method (record 7.304, run.optimizer "bayes"): the method itself on functions
whose optimum is known, and a run searched by it - the same run in everything but who proposes the designs."""
import math

import pytest
import torch

from gator_workbench import bayes, schema
from gator_workbench.storage import tables
from gator_workbench.storage.atomic import read_jsonl
from helpers import check, execute, issues, make_config, rows, summary

D = torch.float64
A = torch.tensor([[10, 3, 17, 3.5, 1.7, 8], [0.05, 10, 17, 0.1, 8, 14], [3, 3.5, 1.7, 10, 17, 8], [17, 8, 0.05, 10, 0.1, 14]], dtype=D)
P = 1e-4 * torch.tensor([[1312, 1696, 5569, 124, 8283, 5886], [2329, 4135, 8307, 3736, 1004, 9991],
                         [2348, 1451, 3522, 2883, 3047, 6650], [4047, 8828, 8732, 5743, 1091, 381]], dtype=D)
ALPHA = torch.tensor([1.0, 1.2, 3.0, 3.2], dtype=D)


def hartmann6(x):
    """The six-variable Hartmann function as a maximum: 3.32237 at its best point, 3.2032 at its second."""
    return float((ALPHA * torch.exp(-(A * (x - P) ** 2).sum(1))).sum())


def search(function, dim, designs, seed, lanes=4, **options):
    """`designs` evaluations with `lanes` designs in flight, as a run's lanes ask and tell."""
    bo, flying, best, asked = bayes.TrustRegionBO(dim, seed=seed, **options), [], -math.inf, []
    for _ in range(designs):
        while len(flying) < lanes:
            flying.append(bo.ask())
        x = flying.pop(0)
        asked.append(x)
        value = function(x)
        bo.tell(x, value)
        best = max(best, value)
    return best, asked, bo


def test_the_process_follows_a_smooth_function_and_is_sure_where_it_has_data():
    generator = torch.Generator().manual_seed(0)
    X = torch.rand(40, 2, generator=generator, dtype=D)
    f = lambda x: torch.sin(6 * x[:, 0]) + x[:, 1] ** 2
    process = bayes.GaussianProcess(2)
    process.fit(X, f(X), steps=80)
    new = torch.rand(50, 2, generator=generator, dtype=D)
    mean, covariance = process.posterior(new)
    assert float((mean - f(new)).abs().max()) < 0.15
    at_data, covariance_at_data = process.posterior(X[:5])
    assert float((at_data - f(X[:5])).abs().max()) < 0.05 and float(torch.diagonal(covariance_at_data).max()) < 0.02
    assert float(torch.diagonal(covariance).min()) >= -1e-9          # a covariance: no negative variance


@pytest.mark.parametrize('seed', [0, 2])
def test_it_finds_an_optimum_of_a_known_function_that_random_search_does_not(seed):
    best, asked, bo = search(hartmann6, 6, 120, seed, n_candidates=500)
    generator = torch.Generator().manual_seed(seed)
    random_best = max(hartmann6(torch.rand(6, generator=generator, dtype=D)) for _ in range(120))
    assert best > 3.15, best                                         # one of the function's two best points (3.32 and 3.20)
    assert best > random_best + 0.3, (best, random_best)
    assert all(0.0 <= float(x.min()) and float(x.max()) <= 1.0 for x in asked)
    assert bo.state()['designs'] == 120


def test_the_same_seed_proposes_the_same_designs_and_another_seed_others():
    first = search(hartmann6, 6, 30, 5, n_candidates=200)[1]
    again = search(hartmann6, 6, 30, 5, n_candidates=200)[1]
    other = search(hartmann6, 6, 30, 6, n_candidates=200)[1]
    assert all(torch.equal(a, b) for a, b in zip(first, again))
    assert not all(torch.equal(a, b) for a, b in zip(first, other))


def test_a_design_without_a_value_counts_as_the_worst_and_a_region_that_shrinks_to_nothing_starts_again():
    bo = bayes.TrustRegionBO(3, seed=0, n_init=4, n_candidates=100, failure_tolerance=1, length_min=0.3)
    for value in (0.5, 0.2, None, 0.9):                              # the initial designs; one failed
        bo.tell(bo.ask(), value)
    assert bo.y == [0.5, 0.2, 0.2, 0.9] and bo.best == 0.9 and bo.restarts == 0
    bo.tell([0.1, 0.1, 0.1], 0.1, asked=False)                       # a design it did not propose: no improvement, the box halves
    assert bo.length == pytest.approx(0.4) and bo.asked == 0
    bo.tell(bo.ask(), 0.1)                                           # again: below the smallest box, a new region begins
    assert bo.restarts == 1 and bo.length == pytest.approx(0.8) and bo.state()['in_this_region'] == 0
    assert bo.state()['best'] == 0.9                                 # what was found stays the run's best


def test_a_run_searched_by_bayesian_optimization_is_the_same_run_but_for_who_proposes(tmp_path):
    options = dict(max_evaluations=40, concurrency=2, seed=3)
    bo_layout, state = execute(make_config(tmp_path / 'bo', run=dict(options, optimizer='bayes')), tmp_path / 'bo')
    assert state == 'completed'
    sac_layout, _ = execute(make_config(tmp_path / 'sac', run=options), tmp_path / 'sac')
    by_seq = lambda layout: sorted(rows(layout, 'evaluations'), key=lambda e: e['commit_seq'])
    bo, sac = by_seq(bo_layout), by_seq(sac_layout)
    assert len(bo) == 40 and summary(bo_layout)['totals']['candidate_evaluations_charged'] == 40
    sources = {e['action_source'] for e in bo}
    assert 'bayes_opt' in sources and not sources & {'sac_policy', 'sampled_policy', 'mean_policy'}
    assert 'sac_policy' in {e['action_source'] for e in sac}
    # the network of the Bayesian run was never trained
    assert rows(bo_layout, 'learner_updates') == [] and rows(sac_layout, 'learner_updates') != []
    # the random warm-up designs are the SAC run's own, for the same seed (in whatever order the two lanes finished them)
    warmup = lambda layout, evaluations: sorted(sorted((p['variable_id'], p['executed_value']) for p in rows(layout, 'parameters')
                                                       if p['evaluation_id'] == e['evaluation_id'] and p['role'] == 'independent')
                                                for e in evaluations if e['action_source'] == 'random_warmup')
    assert warmup(bo_layout, bo) == warmup(sac_layout, sac) and len(warmup(bo_layout, bo)) == 4
    # every proposal is a legal design with a reward, and the run says how the search was set up
    assert all(e['reward'] is not None and e['status'] == 'ok' for e in bo if e['action_source'] == 'bayes_opt')
    events = [e['event'] for e in read_jsonl(bo_layout.logs / 'events.jsonl')]
    assert events.count('bayes_started') == 1
    manifest = __import__('json').loads(bo_layout.manifest.read_text())
    assert manifest['architecture']['optimizer'] == 'bayes'
    assert 'optimizer' not in __import__('json').loads(sac_layout.manifest.read_text())['architecture']


def test_a_sac_configuration_keeps_its_hash_and_a_bayesian_run_from_a_saved_model_is_refused(tmp_path):
    plain = make_config(tmp_path)
    assert plain.run.optimizer == 'sac'
    stated = make_config(tmp_path, run=dict(optimizer='sac'))
    without = plain.model_dump(mode='json')
    without['run'].pop('optimizer')
    assert schema.config_hash(plain) == schema.config_hash(stated) == schema.config_hash(without)
    assert schema.config_hash(make_config(tmp_path, run=dict(optimizer='bayes'))) != schema.config_hash(plain)
    assert 'bayes_opt' in tables.ACTION_SOURCES
    report, _ = check(make_config(tmp_path, run=dict(optimizer='bayes')))
    assert 'bayes_run' in issues(report) and 'bayes_needs_scratch' not in issues(report)
    refused, _ = check(make_config(tmp_path, run=dict(optimizer='bayes', mode='fine_tune')))
    assert 'bayes_needs_scratch' in issues(refused, 'blocker')
