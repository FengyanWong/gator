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


def test_each_proposal_gives_its_freed_memory_back_and_changes_no_number(monkeypatch):
    """Record 7.452, as TuRBO's 7.382: an M+ proposal drops its fitted models (one per output), kept by reference cycles
    until Python's occasional full collection, and glibc kept the memory they freed: an 800-design run's process grew to
    8-14 GB.
    `MoboProposer.propose` now collects and trims after every proposal. Memory work only: with the real collection and
    glibc's real `malloc_trim` after each proposal, the proposals are the same as with neither."""
    import types

    from gator_workbench import bayes
    from gator_workbench.archive_compare import mobo
    real_trim, real_collect = bayes._TRIM, mobo.gc.collect
    groups = [dict(id=k, scale='linear', lower=0.0, upper=1.0, step=None, domain='continuous') for k in ('a', 'b')]

    def proposals(give_back):
        """Five proposals with two lanes (the previous design still running), each followed by both steps or neither."""
        calls = []

        def trim(pad):                                # glibc's real trim, counted
            calls.append(('trim', pad))
            return real_trim(pad) if real_trim is not None else 1

        def collect():                                # Python's real full collection, counted
            calls.append(('collect',))
            return real_collect()
        monkeypatch.setattr(bayes, '_TRIM', trim if give_back else None)
        monkeypatch.setattr(mobo, 'gc', types.SimpleNamespace(collect=collect if give_back else lambda: 0))
        p = MoboProposer(groups, Problem(ROWS, OBJECTIVES), seed=3, settings=FAST)
        for x in torch.quasirandom.SobolEngine(2, scramble=True, seed=101).draw(6, dtype=torch.float64).tolist():
            m = circuit(x)
            p.observe(dict(a=x[0], b=x[1]), m, {k: True for k in m}, 'ok', asked=False)
        made, flying = [], []
        for _ in range(5):
            z = p.propose(pending_executed=flying)
            made.append((z, p.last))
            flying.append({k: (v + 1.0) / 2.0 for k, v in z.items()})
            if len(flying) == 2:
                done = flying.pop(0)
                m = circuit([done['a'], done['b']])
                p.observe(done, m, {k: True for k in m}, 'ok', asked=True)
        return made, calls
    given_back, calls = proposals(True)
    plain, none = proposals(False)
    assert given_back == plain and calls == [('collect',), ('trim', 0)] * 5 and none == []
    assert all(info['source'] == 'acquisition' for _, info in given_back)


def amended(seed=0, archive=None, **extra):
    """M0's settings (plan amendment A1): the frozen search with a cold start and/or the numerical fallback."""
    return MoboSearch(2, Problem(ROWS, OBJECTIVES), seed=seed, settings=dict(FAST, **extra), archive=archive)


def test_a_cold_start_proposes_sobol_designs_until_the_search_knows_enough_designs():
    s = amended(seed=3, cold_start_designs=6)
    first_designs(s, n=2)
    sources = []
    while len(s.X) < 6:
        x, info = s.ask()
        sources.append(info['source'])
        s.tell(x, told(s.problem, x)[0])
    assert sources == ['sobol_cold_start'] * 4
    assert s.ask()[1]['source'] == 'acquisition'
    # a search that starts with more archived designs than the cold start (M+: 600) never meets it
    points = torch.quasirandom.SobolEngine(2, scramble=True, seed=9).draw(6, dtype=torch.float64).tolist()
    archive = dict(u=points, y=[told(Problem(ROWS, OBJECTIVES), x)[0] for x in points])
    assert amended(seed=3, archive=archive, cold_start_designs=6).ask()[1]['source'] == 'acquisition'


def test_a_numerical_breakdown_falls_back_to_a_sobol_design_only_where_allowed(monkeypatch):
    import botorch.optim
    from botorch.exceptions.errors import OptimizationGradientError

    def broken(*args, **kwargs):                      # what stopped M0 on the amplifier and the flip-flop (seed 0)
        raise OptimizationGradientError('19 elements of the 38 element gradient array `gradf` are NaN.', current_x=None)
    allowed, frozen = amended(seed=5, numerical_fallback=True), search(seed=5)
    for s in (allowed, frozen):
        first_designs(s)
    monkeypatch.setattr(botorch.optim, 'optimize_acqf', broken)
    x, info = allowed.ask()
    assert info['source'] == 'sobol_fallback' and info['reason'].startswith('OptimizationGradientError')
    assert all(0.0 <= v <= 1.0 for v in x) and allowed.proposals == 1
    with pytest.raises(OptimizationGradientError):    # M+'s settings: the breakdown stops the run, exactly as before
        frozen.ask()
    allowed.tell(x, told(allowed.problem, x)[0])
    monkeypatch.undo()                                # the model works again: the search goes on with it
    assert allowed.ask()[1]['source'] == 'acquisition'


def test_a_model_fit_that_fails_every_attempt_falls_back_too(monkeypatch):
    import botorch.fit
    from botorch.exceptions.errors import ModelFittingError

    def failing(*args, **kwargs):                     # what stopped the amplifier's M0 run at design 146 (revision 2)
        raise ModelFittingError('All attempts to fit the model have failed.')
    allowed, frozen = amended(seed=7, numerical_fallback=True), search(seed=7)
    for s in (allowed, frozen):
        first_designs(s)
    monkeypatch.setattr(botorch.fit, 'fit_gpytorch_mll', failing)
    x, info = allowed.ask()
    assert info['source'] == 'sobol_fallback' and info['reason'].startswith('ModelFittingError')
    with pytest.raises(ModelFittingError):            # M+'s settings: unchanged, the error still stops the run
        frozen.ask()


def test_after_a_crash_an_m0_search_goes_on_after_every_used_number_and_m_plus_keeps_its_count():
    """Revision 3: restored from a save point 3 proposals before the crash, the search would hand out those 3 numbers -
    and so their Sobol designs - again. With an A1 setting it goes on after the numbers used; M+ keeps its count."""
    unbroken = amended(seed=4, cold_start_designs=12)
    first_designs(unbroken, n=2)
    for _ in range(2):
        x, _ = unbroken.ask()
        unbroken.tell(x, told(unbroken.problem, x)[0])
    saved = unbroken.state_dict()                     # the save point
    used = []
    for _ in range(3):                                # the proposals the crash loses
        x, info = unbroken.ask()
        used.append(x)
        unbroken.tell(x, told(unbroken.problem, x)[0])
    restored = MoboSearch.from_state(saved, unbroken.problem)
    for x in used:                                    # the engine tells the committed designs again (after_crash)
        restored.tell(x, told(restored.problem, x)[0], asked=False)
    assert restored.proposals == 2
    assert restored.continue_after_crash(5) == 5 and restored.continue_after_crash(4) is None
    x, info = restored.ask()
    assert info == dict(source='sobol_cold_start', proposal=5) and x not in used
    assert (x, info) == unbroken.ask()                # the design an unbroken search proposes next
    frozen = search(seed=4)                           # M+'s settings: the restored count stays, as before
    frozen.proposals = 2
    assert frozen.continue_after_crash(5) is None and frozen.proposals == 2


def test_an_output_with_fewer_than_two_values_is_a_breakdown_the_fallback_answers():
    def partial(problem, x):                          # vout missing everywhere: its model has nothing to fit
        m = {k: v for k, v in circuit(x).items() if k != 'vout_v'}
        return problem.outcome(m, {k: True for k in m}, 'measurement_error')[0]
    for allowed in (True, False):
        s = amended(seed=6, **({'numerical_fallback': True} if allowed else {}))
        for x in torch.quasirandom.SobolEngine(2, scramble=True, seed=101).draw(4, dtype=torch.float64).tolist():
            s.tell(x, partial(s.problem, x), asked=False)
        if allowed:
            assert s.ask()[1]['source'] == 'sobol_fallback'
        else:
            with pytest.raises(ValueError, match='fewer than 2 values'):
                s.ask()


def pair(seed):
    """An M0 search allowed to fall back and the frozen (M+) search with the same seed, both past their first designs."""
    allowed, frozen = amended(seed=seed, numerical_fallback=True), search(seed=seed)
    for s in (allowed, frozen):
        first_designs(s)
    return allowed, frozen


def test_a_matrix_that_is_not_positive_definite_falls_back_and_m_plus_still_raises(monkeypatch):
    """M0's most frequent breakdown (18 fallbacks on the amplifier, revision 2): NotPSDError, a RuntimeError (7.451)."""
    import botorch.fit
    from linear_operator.utils.errors import NotPSDError
    allowed, frozen = pair(11)

    def not_psd(*args, **kwargs):
        raise NotPSDError('Matrix not positive definite after repeatedly adding jitter up to 1.0e-06.')
    monkeypatch.setattr(botorch.fit, 'fit_gpytorch_mll', not_psd)
    x, info = allowed.ask()
    assert info['source'] == 'sobol_fallback' and info['reason'].startswith('NotPSDError')
    assert all(0.0 <= v <= 1.0 for v in x)
    with pytest.raises(NotPSDError):
        frozen.ask()


def test_a_plain_runtime_error_of_the_model_step_falls_back_and_m_plus_still_raises(monkeypatch):
    import botorch.optim
    allowed, frozen = pair(12)

    def cholesky(*args, **kwargs):
        raise RuntimeError('linalg.cholesky: The factorization could not be completed because the input is not '
                           'positive-definite (the leading minor of order 3 is not positive-definite).')
    monkeypatch.setattr(botorch.optim, 'optimize_acqf', cholesky)
    assert allowed.ask()[1]['reason'].startswith('RuntimeError: linalg.cholesky')
    with pytest.raises(RuntimeError, match='cholesky'):
        frozen.ask()


def test_a_non_finite_design_falls_back_and_m_plus_returns_it_as_before(monkeypatch):
    import botorch.optim
    allowed, frozen = pair(13)

    def nan_candidate(*args, **kwargs):
        return torch.tensor([[float('nan'), 0.5]], dtype=torch.float64), torch.tensor([0.0], dtype=torch.float64)
    monkeypatch.setattr(botorch.optim, 'optimize_acqf', nan_candidate)
    x, info = allowed.ask()
    assert info['source'] == 'sobol_fallback' and info['reason'] == 'the acquisition gave a non-finite design'
    assert all(0.0 <= v <= 1.0 for v in x)
    y, yinfo = frozen.ask()                           # M+'s settings: the design comes back unchanged, as before A1
    assert yinfo['source'] == 'acquisition' and y[0] != y[0]


def test_a_programming_error_is_not_turned_into_a_fallback(monkeypatch):
    import botorch.optim
    allowed, _ = pair(14)

    def bug(*args, **kwargs):
        raise TypeError("optimize_acqf() got an unexpected keyword argument 'options'")
    monkeypatch.setattr(botorch.optim, 'optimize_acqf', bug)
    with pytest.raises(TypeError):
        allowed.ask()


@pytest.mark.parametrize('extra, moves', [
    (dict(), False),
    (dict(numerical_fallback=False), False),
    (dict(cold_start_designs=12), True),
    (dict(numerical_fallback=True), True),
    (dict(cold_start_designs=12, numerical_fallback=True), True),
])
def test_only_a_search_with_an_amendment_setting_moves_its_count_after_a_crash(extra, moves):
    s = amended(seed=4, **extra)
    assert s.uses_amendment_settings() is moves
    s.proposals = 2
    assert s.continue_after_crash(2) is None and s.proposals == 2        # the same number: no move
    assert s.continue_after_crash(1) is None and s.proposals == 2        # a lower one: no move
    assert s.continue_after_crash(5) == (5 if moves else None)
    assert s.proposals == (5 if moves else 2)


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
