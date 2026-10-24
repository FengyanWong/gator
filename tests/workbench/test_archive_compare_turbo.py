"""turbo_archive_v1 (the comparison's T0/T+ arms, docs/plan-bo-mobo-rl-archive-comparison.md section 5): made-up functions
with known answers only; no circuit, no simulator."""
import math

import pytest
import torch

from gator_workbench.archive_compare.turbo_archive import ArchiveProposer, ArchiveTrustRegionBO
from gator_workbench.bayes import TrustRegionBO


def bowl(x, center=0.3):
    """Maximum 0 at x = center in every variable."""
    return -float(((torch.as_tensor(x) - center) ** 2).sum())


def run(search, f, n, *, asked=True):
    for _ in range(n):
        x = search.ask()
        search.tell(x, f(x), asked=asked)
    return search


def test_with_no_archive_it_proposes_exactly_what_production_turbo_proposes():
    """T0 is production TuRBO-1 but for the documented differences (no newest-600 cut, a restart keeps the data, the
    first designs come from the run): before any of them can matter, the two give the same designs bit for bit."""
    dim = 4
    production = TrustRegionBO(dim, seed=5, n_init=8, fit_steps=10)
    archive = ArchiveTrustRegionBO(dim, seed=5, n_init=8, fit_steps=10)
    first = torch.quasirandom.SobolEngine(dim, scramble=True, seed=101).draw(8).to(torch.float64)
    for x in first:                                      # the run's common first designs, told to both alike
        production.tell(x, bowl(x), asked=False)
        archive.tell(x, bowl(x), asked=False)
    for step in range(40):
        a, b = production.ask(), archive.ask()
        assert torch.equal(a, b), step
        production.tell(a, bowl(a))
        archive.tell(b, bowl(b))
    assert production.restarts == archive.restarts == 0


def test_archived_designs_cost_no_ask_budget_or_trust_region_step_and_the_first_region_starts_at_their_best():
    dim = 3
    gen = torch.Generator().manual_seed(1)
    source_X = torch.rand(30, dim, generator=gen, dtype=torch.float64)
    source_y = [bowl(x) for x in source_X]
    search = ArchiveTrustRegionBO(dim, seed=2, source_X=source_X, source_y=source_y, fit_steps=5)
    assert (search.asked, search.successes, search.failures, len(search.X), search.restarts) == (0, 0, 0, 0, 0)
    fit_X, fit_y = search._fit_data()
    assert len(fit_X) == 30 and fit_y.tolist() == source_y
    # the first proposal is drawn around the best archived design (the region's centre)
    best = source_X[int(torch.tensor(source_y).argmax())]
    x = search.ask()
    assert float((x - best).abs().max()) <= search.length / 2 * 3 + 1e-12      # inside the box (weights within a factor 3)
    # the run's common first designs are told with asked=False and are not counted as successes or failures
    for k in range(8):
        search.tell(torch.full((dim,), 0.05 * k, dtype=torch.float64), -10.0, asked=False)
        assert (search.successes, search.failures) == (0, 0)
    assert search.best == max(source_y)


def test_a_failed_archived_design_counts_as_the_worst_archived_reward():
    search = ArchiveTrustRegionBO(2, source_X=[[0.1, 0.1], [0.5, 0.5], [0.9, 0.2]], source_y=[-1.0, None, -3.0])
    assert search.source_y == [-1.0, -3.0, -3.0] and search.source_failed == 1


def test_a_restart_opens_a_new_region_but_never_drops_a_design_from_the_fit():
    dim = 2
    source_X = [[0.2, 0.2], [0.8, 0.8], [0.5, 0.1]]
    search = ArchiveTrustRegionBO(dim, seed=3, source_X=source_X, source_y=[bowl(x) for x in source_X], n_init=4,
                                  failure_tolerance=1, length_min=0.4, fit_steps=3)
    for k in range(4):                                   # the common first designs
        search.tell(torch.tensor([0.9, 0.9 - 0.1 * k], dtype=torch.float64), -5.0, asked=False)
    while search.restarts == 0:                          # every proposal told as a failure: the region shrinks
        search.tell(search.ask(), -100.0)
    assert search.region == 1 and search.start == len(search.X)
    fit_X, _ = search._fit_data()
    assert len(fit_X) == 3 + len(search.X)               # every archived and every online design is still fitted
    # the new region begins with its own fresh designs and centres on its own best, not on the archive's
    for _ in range(search.n_init):
        x = search.ask()
        search.tell(x, bowl(x))
    assert len(search.X) - search.start == search.n_init


def test_the_fit_ceiling_is_refused_never_cut():
    search = ArchiveTrustRegionBO(2, source_X=[[0.1 * k, 0.5] for k in range(5)], source_y=[0.0] * 5, max_fit_points=6)
    search.tell([0.5, 0.5], 1.0, asked=False)
    search.tell([0.6, 0.5], 1.0, asked=False)
    with pytest.raises(RuntimeError, match='nothing is ever cut'):
        search.ask()


def test_a_saved_and_restored_search_continues_exactly_as_one_that_was_never_stopped():
    dim = 3
    source_X = torch.rand(12, dim, generator=torch.Generator().manual_seed(4), dtype=torch.float64)
    make = lambda: ArchiveTrustRegionBO(dim, seed=9, source_X=source_X, source_y=[bowl(x) for x in source_X],
                                        n_init=4, failure_tolerance=2, length_min=0.2, fit_steps=4)
    whole, part = make(), make()
    run(whole, bowl, 25)
    run(part, bowl, 25)
    restored = ArchiveTrustRegionBO.from_state(part.state_dict())
    for step in range(25):
        a, b = whole.ask(), restored.ask()
        assert torch.equal(a, b), step
        whole.tell(a, bowl(a))
        restored.tell(b, bowl(b))
    assert whole.state_dict() == restored.state_dict()
    assert whole.restarts >= 1                            # the comparison covered a restart


def test_a_good_archive_brings_the_search_to_the_optimum_sooner_than_no_archive():
    """A sanity check of the transfer itself on a known bowl (not evidence about circuits)."""
    dim = 6
    gen = torch.Generator().manual_seed(11)
    near = (0.3 + 0.08 * (torch.rand(40, dim, generator=gen, dtype=torch.float64) - 0.5)).clamp(0, 1)
    with_archive = ArchiveTrustRegionBO(dim, seed=1, source_X=near, source_y=[bowl(x) for x in near], fit_steps=10)
    without = ArchiveTrustRegionBO(dim, seed=1, fit_steps=10)
    for search in (with_archive, without):
        for k in range(8):                                # the same common first designs for both
            x = torch.quasirandom.SobolEngine(dim, scramble=True, seed=101).draw(k + 1, dtype=torch.float64)[-1]
            search.tell(x, bowl(x), asked=False)
        run(search, bowl, 30)
    best = lambda s: max(s.y)
    assert best(with_archive) > best(without)


def test_the_proposer_speaks_the_engines_proposals_and_tells_executed_points():
    groups = [dict(id='w', scale='log', lower=1e-6, upper=1e-4, step=None, domain='continuous'),
              dict(id='n', scale='linear', lower=1.0, upper=9.0, step=1.0, domain='integer')]
    archive = dict(u=[[0.5, 0.5], [0.25, 0.75]], reward=[-1.0, -2.0])
    proposer = ArchiveProposer(groups, seed=0, archive=archive, fit_steps=2)
    z = proposer.propose()
    assert set(z) == {'w', 'n'} and all(-1.0 <= v <= 1.0 for v in z.values())
    point = proposer.executed_point({'w': 1e-5, 'n': 5.0})
    assert math.isclose(point[0], 0.5, abs_tol=1e-15) and point[1] == 0.5
    proposer.observe({'w': 1e-5, 'n': 5.0}, -0.5, asked=True)
    restored = ArchiveProposer.from_state(proposer.state_dict())
    assert restored.search.state_dict() == proposer.search.state_dict() and restored.group_ids == ['w', 'n']
