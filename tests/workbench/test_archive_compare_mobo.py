"""mobo_qlognehvi_v1 (the comparison's M+ arm, docs/plan-bo-mobo-rl-archive-comparison.md section 5): made-up two-objective
functions with known answers; no circuit, no simulator. Needs BoTorch: run with ~/gator/envs/archive-compare-venv (the
comparison's isolated environment); skipped where BoTorch is not installed (the live environment never gets it)."""
import math
import random

import pytest

botorch = pytest.importorskip('botorch')
import torch  # noqa: E402

from gator_workbench.archive_compare.mobo import MoboProposer, MoboSearch, Problem, hypervolume  # noqa: E402

ROWS = [dict(metric='power_w', unit='W', constraint='<=', lower=None, upper=1.0, scale=1.0),
        dict(metric='psrr_db', unit='dB', constraint='>=', lower=0.5, upper=None, scale=1.0),
        dict(metric='vout_v', unit='V', constraint='interval', lower=0.2, upper=0.8, scale=1.0)]
OBJECTIVES = [dict(metric='power_w', orientation='minimize', base_limit=1.0),
              dict(metric='psrr_db', orientation='maximize', base_limit=0.5)]
FAST = dict(num_restarts=2, raw_samples=32, mc_samples=16, maxiter=30, refit_every=4)


def circuit(x):
    """A made-up 'circuit': power rises with x0, PSRR with x1 and falls with x0; vout must stay within 0.2..0.8."""
    x0, x1 = float(x[0]), float(x[1])
    return dict(power_w=0.2 + x0, psrr_db=0.3 + 0.6 * x1 - 0.3 * x0, vout_v=0.1 + 0.8 * x1)


def told(problem, x, status='ok'):
    """Evaluate the synthetic circuit and encode its measurements as a search outcome."""
    m = circuit(x)
    return problem.outcome(m, {k: True for k in m}, status)


def test_outcomes_are_signed_scaled_masked_and_infrastructure_is_left_out():
    p = Problem(ROWS, OBJECTIVES)
    assert p.outputs == ['power_w', 'psrr_db', 'vout_v', '__valid__'] and p.ref_point == [-1.0, 0.5]
    y, infra = p.outcome(dict(power_w=0.5, psrr_db=0.7, vout_v=0.5), dict(power_w=True, psrr_db=True, vout_v=True), 'ok')
    assert y == [-0.5, 0.7, 0.5, 1.0] and not infra
    y, _ = p.outcome(dict(power_w=0.5, vout_v=0.5), dict(power_w=True, vout_v=True), 'measurement_error')
    assert y == [-0.5, None, 0.5, 0.0]                     # a missing output stays missing; the design is not valid
    y, infra = p.outcome({}, {}, 'transport_error')
    assert infra and y == [None] * 4
    # the constraints are negative exactly where the rows pass
    Y = torch.tensor([[-0.5, 0.7, 0.5, 1.0], [-0.5, 0.7, 0.9, 1.0], [-0.5, 0.7, 0.5, 0.0]])
    values = torch.stack([f(Y) for f in p.constraint_functions()])
    assert (values[:, 0] <= 0).all() and (values[:, 1] > 0).any() and (values[:, 2] > 0).any()


def test_the_flip_flop_energy_is_missing_unless_all_six_delays_are_present():
    rows = [dict(metric='energy_int_j', unit='J', constraint='<=', lower=None, upper=1.0, scale=1.0),
            dict(metric='tcq_mean', unit='s', constraint='<=', lower=None, upper=1.0, scale=1.0)]
    objectives = [dict(metric='energy_int_j', orientation='minimize', base_limit=1.0),
                  dict(metric='tcq_mean', orientation='minimize', base_limit=1.0)]
    p = Problem(rows, objectives, energy_rule=True)
    window = dict(tcq_r=1, tcq_f=1, tcqn_f=1, tcqn_r=1, m_tcq_r_late=1, m_tcq_f_late=1)
    full = dict(window, energy_int_j=0.3, tcq_mean=0.4)
    assert p.outcome(full, {k: True for k in full}, 'ok')[0][0] == -0.3
    late_missing = {k: v for k, v in full.items() if k != 'm_tcq_f_late'}
    assert p.outcome(late_missing, {k: True for k in late_missing}, 'ok')[0][0] is None


def test_the_hypervolume_is_exact_on_hand_worked_fixtures_and_agrees_with_botorch():
    assert hypervolume([(3, 1), (1, 3)], (0, 0)) == 5.0                      # 3 + 3 - 1
    assert hypervolume([(3, 1), (1, 3), (2, 2)], (0, 0)) == 6.0               # adds the 1 x 1 corner
    assert hypervolume([(3, 1), (-1, 5)], (0, 0)) == 3.0                      # a point beyond the reference adds nothing
    assert hypervolume([], (0, 0)) == 0.0
    from botorch.utils.multi_objective.box_decompositions.dominated import DominatedPartitioning
    rng = random.Random(3)
    for _ in range(20):
        points = [(rng.uniform(-1, 2), rng.uniform(-1, 2)) for _ in range(12)]
        ref = (0.0, 0.0)
        theirs = DominatedPartitioning(ref_point=torch.tensor(ref, dtype=torch.float64),
                                       Y=torch.tensor(points, dtype=torch.float64)).compute_hypervolume().item()
        assert math.isclose(hypervolume(points, ref), theirs, rel_tol=1e-12, abs_tol=1e-12)


def search(seed=0, archive=None):
    """Create a two-dimensional synthetic search with the shared constraints and small search settings."""
    return MoboSearch(2, Problem(ROWS, OBJECTIVES), seed=seed, settings=FAST, archive=archive)


def first_designs(s, n=6):
    """Give the search a reproducible Sobol design history before it proposes any points."""
    for x in torch.quasirandom.SobolEngine(2, scramble=True, seed=101).draw(n, dtype=torch.float64).tolist():
        s.tell(x, told(s.problem, x)[0], asked=False)


def test_the_same_seed_proposes_the_same_designs():
    a, b = search(seed=4), search(seed=4)
    for s in (a, b):
        first_designs(s)
    for _ in range(3):
        xa, _ = a.ask()
        xb, _ = b.ask()
        assert xa == xb
        a.tell(xa, told(a.problem, xa)[0])
        b.tell(xb, told(b.problem, xb)[0])


def test_a_saved_and_restored_search_proposes_what_an_unbroken_one_proposes():
    whole, part = search(seed=2), search(seed=2)
    for s in (whole, part):
        first_designs(s)
        for _ in range(3):
            x, _ = s.ask()
            s.tell(x, told(s.problem, x)[0])
    restored = MoboSearch.from_state(part.state_dict(), Problem(ROWS, OBJECTIVES))
    for _ in range(3):
        xa, _ = whole.ask()
        xb, _ = restored.ask()
        assert xa == xb
        whole.tell(xa, told(whole.problem, xa)[0])
        restored.tell(xb, told(restored.problem, xb)[0])


def test_pending_designs_are_taken_into_account_and_an_archive_costs_nothing():
    s = search(seed=1)
    first_designs(s)
    x1, info1 = s.ask()
    x2, info2 = s.ask(pending=[x1])                    # a second lane while the first design is still running
    assert info2['pending'] == 1 and x1 != x2
    archive = dict(u=[[0.1, 0.9], [0.5, 0.5], [0.9, 0.1]],
                   y=[told(Problem(ROWS, OBJECTIVES), x)[0] for x in ([0.1, 0.9], [0.5, 0.5], [0.9, 0.1])])
    with_archive = search(seed=1, archive=archive)
    assert with_archive.archived == 3 and with_archive.asked == 0 and with_archive.proposals == 0


def test_it_improves_the_feasible_front_over_its_first_designs_on_a_known_problem():
    """A sanity check of the search itself (not evidence about circuits)."""
    s = search(seed=0)
    first_designs(s)
    def front():
        """Measure the hypervolume of the search's valid feasible observations."""
        pts = []
        for y in s.Y:
            if y[3] == 1.0 and y[0] is not None and y[1] is not None and 0.2 <= y[2] <= 0.8:
                pts.append((y[0], y[1]))
        return hypervolume(pts, s.problem.ref_point)
    before = front()
    for _ in range(10):
        x, _ = s.ask()
        s.tell(x, told(s.problem, x)[0])
    assert front() > before


def test_the_proposer_speaks_the_engines_proposals_and_tells_executed_points():
    groups = [dict(id='a', scale='linear', lower=0.0, upper=1.0, step=None, domain='continuous'),
              dict(id='b', scale='linear', lower=0.0, upper=1.0, step=None, domain='continuous')]
    p = MoboProposer(groups, Problem(ROWS, OBJECTIVES), seed=0, settings=FAST)
    for x in torch.quasirandom.SobolEngine(2, scramble=True, seed=101).draw(6, dtype=torch.float64).tolist():
        m = circuit(x)
        p.observe(dict(a=x[0], b=x[1]), m, {k: True for k in m}, 'ok', asked=False)
    z = p.propose(pending_executed=[dict(a=0.5, b=0.5)])
    assert set(z) == {'a', 'b'} and all(-1.0 <= v <= 1.0 for v in z.values()) and p.last['pending'] == 1
    p.observe(dict(a=0.2, b=0.2), {}, {}, 'license_error', asked=True)   # an infrastructure failure: not in any model
    assert p.observations == 6
    restored = MoboProposer.from_state(p.state_dict(), Problem(ROWS, OBJECTIVES))
    assert restored.search.state_dict() == p.search.state_dict()


def test_a_proposal_does_not_depend_on_what_used_the_global_random_generator_before():
    """BoTorch prunes the baseline with posterior samples seeded from torch's global generator: a proposal built outside
    its own seeded block depended on whatever drew numbers before it (a resumed search then proposed otherwise)."""
    proposals = []
    for noise in (0, 1, 2):
        s = search(seed=2)
        first_designs(s)
        for _ in range(3):
            x, _ = s.ask()
            s.tell(x, told(s.problem, x)[0])
        torch.manual_seed(1000 + noise)                  # someone else's draws
        torch.rand(17 * (noise + 1))
        proposals.append(s.ask()[0])
    assert proposals[0] == proposals[1] == proposals[2]
