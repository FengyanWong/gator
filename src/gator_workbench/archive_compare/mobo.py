"""Constrained Pareto MOBO: `mobo_qlognehvi_v1`, the M+ arm of the comparison (plan section 5: "M+ is one specified
algorithm"). It needs BoTorch, which lives only in the comparison's isolated environment
(~/gator/envs/archive-compare-venv): this module imports it when a search is built, never at import time.

Fixed before any target run (WORKPLAN-steps2-7.md, item 6), in `SETTINGS`:
  - Outputs: the two objectives in maximization form (a minimized metric negated), every other base hard row's metric,
    and a validity output (1 when the simulation gave every required output, else 0). Each is divided by its row's frozen
    scale. One `SingleTaskGP` per output (ARD Matern-5/2 in a ScaleKernel, a learned homoskedastic Gaussian noise, the
    outcome standardized), fitted only on the designs where that output is valid: partial results keep their valid
    outputs and miss the rest. Infrastructure failures are left out of every model.
  - The flip-flop's decision D6: its energy objective is missing for a design whose six delays are not all present.
  - Acquisition: `qLogNoisyExpectedHypervolumeImprovement` over the two objectives, the reference point at their base
    limits, the other rows as outcome constraints (lower/scale - y <= 0, y - upper/scale <= 0) and validity >= 0.5;
    `prune_baseline`, Sobol QMC samples seeded per proposal (`mc_samples`). One new design per call, valued jointly with
    the designs still in flight (`X_pending`): with four lanes a batch of at most 4. `optimize_acqf` under a seed per
    proposal, with the restarts, raw samples and iterations of `SETTINGS`.
  - Hyperparameters refitted (maximum marginal likelihood, warm-started, at most `fit_maxiter` iterations) at the first
    proposal and when the online designs reach each count of `refit_at`; in between the last ones are kept and only the
    data change. (The settings were made cheaper at the step-6 resource gate, before any target run: see `SETTINGS`.)
  - Archived designs are imported before the first proposal and cost no budget.
`state_dict` / `from_state` keep the data, the pending designs, the hyperparameters and the counters a resume needs.
"""
from __future__ import annotations

import math

from .coords import to_proposal

VERSION = 'mobo_qlognehvi_v1'
# Frozen 2026-10-23 at the step-6 resource gate, before any target run (WORKPLAN item 6c; step6/mobo_settings.json): the
# first settings (10 restarts, 512 raw samples, 128 MC samples, 200 iterations, a full refit every 8 designs) cost 1-2 min
# per proposal and 200 s per refit on the LDO archive (600 rows, 27 dims, 6 outputs) - one to two days of compute per
# 800-design run. These reach the same front on the unit tests' known problem at a third of the cost; refits follow the
# online designs (16, 32, ..., 512), warm-started and capped at 200 iterations.
SETTINGS = dict(num_restarts=2, raw_samples=64, mc_samples=64, maxiter=30, batch_limit=5, refit_every=8,
                refit_at=(16, 32, 64, 128, 256, 512), fit_maxiter=200, cache_root=True, validity_threshold=0.5, kernel='ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=d))',
                outcome_transform='Standardize(m=1)', noise='learned homoskedastic Gaussian likelihood (BoTorch default)',
                batch_rule='one new design per call, valued with the designs in flight (X_pending); at most 4 with 4 lanes',
                infrastructure_statuses='every status but ok, measurement_error, nonconverged, invalid_design')
SCORED_STATUSES = ('ok', 'measurement_error', 'nonconverged', 'invalid_design')
DFF_ENERGY_WINDOW = ('tcq_r', 'tcq_f', 'tcqn_f', 'tcqn_r', 'm_tcq_r_late', 'm_tcq_f_late')


class Problem:
    """What M+ models for one case: built from the case's base view rows (cases.json goal view `panel_a`) and its two
    Panel B objectives (cases.json objectives.panel_b)."""

    def __init__(self, rows, objectives, *, energy_rule=False):
        by_metric = {row['metric']: row for row in rows}
        if len(objectives) != 2 or any(o['metric'] not in by_metric for o in objectives):
            raise ValueError('M+ needs two objectives, each a row of the view')
        self.objectives = [dict(metric=o['metric'], sign=1.0 if o['orientation'] == 'maximize' else -1.0,
                                scale=float(by_metric[o['metric']]['scale']), limit=float(o['base_limit'])) for o in objectives]
        names = {o['metric'] for o in objectives}
        self.constraint_rows = [row for row in rows if row['metric'] not in names]
        self.required = [row['metric'] for row in rows]
        self.outputs = [o['metric'] for o in self.objectives] + [row['metric'] for row in self.constraint_rows] + ['__valid__']
        self.energy_rule = energy_rule
        self.ref_point = [o['sign'] * o['limit'] / o['scale'] for o in self.objectives]

    def outcome(self, metrics: dict, validity: dict, status: str):
        """(y: one number or None per output, infrastructure: bool). None = missing (left out of that output's model)."""
        if status not in SCORED_STATUSES:
            return [None] * len(self.outputs), True
        good = lambda m: (validity.get(m) is True and isinstance(metrics.get(m), (int, float))
                          and not isinstance(metrics.get(m), bool) and math.isfinite(metrics[m]))
        y = []
        for o in self.objectives:
            known = good(o['metric'])
            if known and self.energy_rule and o['metric'] == 'energy_int_j':
                known = all(good(m) for m in DFF_ENERGY_WINDOW)          # decision D6
            y.append(o['sign'] * metrics[o['metric']] / o['scale'] if known else None)
        for row in self.constraint_rows:
            y.append(metrics[row['metric']] / float(row['scale']) if good(row['metric']) else None)
        y.append(1.0 if all(good(m) for m in self.required) else 0.0)
        return y, False

    def constraint_functions(self):
        """BoTorch outcome constraints over the model's outputs: negative values are feasible."""
        functions = []
        for k, row in enumerate(self.constraint_rows):
            index, scale = 2 + k, float(row['scale'])
            if row['lower'] is not None:
                functions.append(lambda Y, i=index, b=row['lower'] / scale: b - Y[..., i])
            if row['upper'] is not None:
                functions.append(lambda Y, i=index, b=row['upper'] / scale: Y[..., i] - b)
        valid = len(self.outputs) - 1
        functions.append(lambda Y, i=valid, t=SETTINGS['validity_threshold']: t - Y[..., i])
        return functions

    def describe(self) -> dict:
        return dict(objectives=self.objectives, constraint_rows=self.constraint_rows, outputs=self.outputs,
                    ref_point=self.ref_point, energy_rule=self.energy_rule)


class MoboSearch:
    """Points of the unit cube. `tell` one finished design's outputs; `ask` the next design given those in flight."""

    def __init__(self, dim, problem: Problem, *, seed=0, settings=None, archive=None):
        self.dim, self.problem, self.seed = dim, problem, int(seed)
        self.settings = dict(SETTINGS, **(settings or {}))
        self.X, self.Y = [], []                      # every told design (archived first), its outputs (None = missing)
        self.archived = 0
        self.asked = self.proposals = self.refits = self.since_refit = 0
        self.fitted_online = 0                       # the online designs the last refit saw (refit_at)
        self.hyper = None                            # the last fitted hyperparameters, per output
        if archive is not None:
            for x, y in zip(archive['u'], archive['y']):
                self._add(x, y)
            self.archived = len(self.X)

    def _add(self, x, y):
        if len(x) != self.dim or any(not 0.0 <= float(v) <= 1.0 for v in x) or len(y) != len(self.problem.outputs):
            raise ValueError('a design outside the unit cube or with the wrong outputs')
        self.X.append([float(v) for v in x])
        self.Y.append([None if v is None else float(v) for v in y])

    def tell(self, x, y, *, asked=True, infrastructure=False):
        if asked:
            self.asked = max(0, self.asked - 1)
        if infrastructure:                           # not evidence about the circuit: left out of every model
            return
        self._add(x, y)
        self.since_refit += 1

    def _models(self, torch):
        from botorch.models import ModelListGP, SingleTaskGP
        from botorch.models.transforms.outcome import Standardize
        from gpytorch.kernels import MaternKernel, ScaleKernel
        models = []
        for i in range(len(self.problem.outputs)):
            rows = [(x, y[i]) for x, y in zip(self.X, self.Y) if y[i] is not None]
            if len(rows) < 2:
                raise ValueError(f'output {self.problem.outputs[i]} has fewer than 2 values')
            X = torch.tensor([r[0] for r in rows], dtype=torch.float64)
            Y = torch.tensor([[r[1]] for r in rows], dtype=torch.float64)
            covar = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=self.dim))
            models.append(SingleTaskGP(X, Y, covar_module=covar, outcome_transform=Standardize(m=1)))
        return ModelListGP(*models)

    def _fit(self, torch, model):
        from botorch.fit import fit_gpytorch_mll
        from gpytorch.mlls import ExactMarginalLogLikelihood
        schedule = self.settings.get('refit_at')
        if schedule is not None:                     # refit when the online designs reach each listed count
            online = len(self.X) - self.archived
            due = self.hyper is None or any(self.fitted_online < count <= online for count in schedule)
        else:
            due = self.hyper is None or self.since_refit >= self.settings['refit_every']
        if not due:                                  # keep the fitted hyperparameters, condition on the new data
            for sub, state in zip(model.models, self.hyper):
                sub.load_state_dict(state, strict=False)
            return False
        with torch.random.fork_rng():
            torch.manual_seed(self.seed * 1000003 + self.refits)
            limit = self.settings.get('fit_maxiter')
            options = {} if limit is None else dict(optimizer_kwargs=dict(options=dict(maxiter=int(limit))))
            for i, sub in enumerate(model.models):
                if self.hyper is not None:           # start from the last fit
                    sub.load_state_dict(self.hyper[i], strict=False)
                fit_gpytorch_mll(ExactMarginalLogLikelihood(sub.likelihood, sub), **options)
        self.hyper = [{k: v for k, v in sub.state_dict().items() if not k.startswith(('train_', 'outcome_transform'))}
                      for sub in model.models]
        self.refits += 1
        self.since_refit = 0
        self.fitted_online = len(self.X) - self.archived
        return True

    def ask(self, pending=()):
        import torch
        from botorch.acquisition.multi_objective.logei import qLogNoisyExpectedHypervolumeImprovement
        from botorch.acquisition.multi_objective.objective import IdentityMCMultiOutputObjective
        from botorch.optim import optimize_acqf
        from botorch.sampling import SobolQMCNormalSampler
        self.asked += 1
        index = self.proposals
        self.proposals += 1
        objective_known = [y[0] is not None and y[1] is not None for y in self.Y]
        if sum(objective_known) < 2:                 # nothing to model yet: a Sobol design (recorded as such)
            engine = torch.quasirandom.SobolEngine(self.dim, scramble=True, seed=self.seed + 7919)
            engine.fast_forward(index)
            return engine.draw(1, dtype=torch.float64)[0].tolist(), dict(source='sobol', proposal=index)
        baseline = torch.tensor(self.X, dtype=torch.float64)
        pending_X = torch.tensor([list(p) for p in pending], dtype=torch.float64) if len(pending) else None
        seed = self.seed * 1000003 + 7 * index
        bounds = torch.stack([torch.zeros(self.dim, dtype=torch.float64), torch.ones(self.dim, dtype=torch.float64)])
        # Every random draw of a proposal comes from its own seed: the acquisition's construction draws too (BoTorch prunes
        # the baseline with posterior samples seeded from torch's global generator), so it is built inside the fork as
        # well - outside it, a proposal depended on whatever had used that generator before, and a resumed search
        # proposed other designs than an unbroken one.
        with torch.random.fork_rng():
            torch.manual_seed(seed)
            model = self._models(torch)
            refitted = self._fit(torch, model)
            acquisition = qLogNoisyExpectedHypervolumeImprovement(
                model=model, ref_point=self.problem.ref_point, X_baseline=baseline,
                objective=IdentityMCMultiOutputObjective(outcomes=[0, 1]), constraints=self.problem.constraint_functions(),
                X_pending=pending_X, prune_baseline=True, cache_root=bool(self.settings.get('cache_root', False)),
                sampler=SobolQMCNormalSampler(sample_shape=torch.Size([self.settings['mc_samples']]), seed=seed))
            candidate, value = optimize_acqf(acquisition, bounds=bounds, q=1, num_restarts=self.settings['num_restarts'],
                                             raw_samples=self.settings['raw_samples'],
                                             options=dict(batch_limit=self.settings['batch_limit'],
                                                          maxiter=self.settings['maxiter']))
        point = candidate[0].clamp(0.0, 1.0).tolist()
        return point, dict(source='acquisition', proposal=index, refitted=refitted, pending=len(pending),
                           acquisition_value=float(value.reshape(-1)[0]))

    def state_dict(self) -> dict:
        import torch
        hyper = None if self.hyper is None else [{k: v.tolist() for k, v in state.items()} for state in self.hyper]
        return dict(version=VERSION, dim=self.dim, seed=self.seed, settings=self.settings, problem=self.problem.describe(),
                    X=self.X, Y=self.Y, archived=self.archived, asked=self.asked, proposals=self.proposals,
                    refits=self.refits, since_refit=self.since_refit, fitted_online=self.fitted_online, hyper=hyper,
                    torch=torch.__version__)

    @classmethod
    def from_state(cls, state: dict, problem: Problem) -> 'MoboSearch':
        import torch
        if state.get('version') != VERSION:
            raise ValueError(f"a {state.get('version')!r} search state is not {VERSION}")
        if state['problem'] != problem.describe():
            raise ValueError('the saved search belongs to another problem')
        search = cls(state['dim'], problem, seed=state['seed'], settings=state['settings'])
        search.X, search.Y = [list(x) for x in state['X']], [list(y) for y in state['Y']]
        for key in ('archived', 'asked', 'proposals', 'refits', 'since_refit'):
            setattr(search, key, state[key])
        search.fitted_online = state.get('fitted_online', 0)
        search.hyper = None if state['hyper'] is None else [
            {k: torch.tensor(v, dtype=torch.float64) for k, v in s.items()} for s in state['hyper']]
        return search


class MoboProposer:
    """The engine's side: proposals as z in [-1, 1] per parameter group, finished designs told as their executed points
    with every recorded measurement, their validity and their status."""
    SOURCE = 'bayes_opt'

    def __init__(self, groups, problem: Problem, *, seed=0, archive=None, settings=None):
        self.groups = list(groups)
        self.group_ids = [g['id'] for g in self.groups]
        self.problem = problem
        self.search = MoboSearch(len(self.groups), problem, seed=seed, settings=settings, archive=archive)
        self.last = None

    @property
    def observations(self) -> int:
        return len(self.search.X) - self.search.archived

    def executed_point(self, executed: dict) -> list:
        return [(to_proposal(g, executed[g['id']]) + 1.0) / 2.0 for g in self.groups]

    def propose(self, pending_executed=()) -> dict:
        point, self.last = self.search.ask([self.executed_point(p) for p in pending_executed])
        return {group: float(2.0 * point[index] - 1.0) for index, group in enumerate(self.group_ids)}

    def observe(self, executed: dict, metrics: dict, validity: dict, status: str, *, asked) -> None:
        y, infrastructure = self.problem.outcome(metrics, validity, status)
        self.search.tell(self.executed_point(executed), y, asked=asked, infrastructure=infrastructure)

    def state_dict(self) -> dict:
        return dict(groups=self.groups, search=self.search.state_dict())

    @classmethod
    def from_state(cls, state: dict, problem: Problem) -> 'MoboProposer':
        proposer = cls.__new__(cls)
        proposer.groups = list(state['groups'])
        proposer.group_ids = [g['id'] for g in proposer.groups]
        proposer.problem = problem
        proposer.search = MoboSearch.from_state(state['search'], problem)
        proposer.last = None
        return proposer


def hypervolume(points, ref_point) -> float:
    """The 2-D hypervolume dominated by `points` (maximization) above `ref_point`, computed exactly by sweeping - the
    measure of Panel B (plan section 7), independent of BoTorch so the two can check each other."""
    good = sorted({(float(a), float(b)) for a, b in points if a > ref_point[0] and b > ref_point[1]}, reverse=True)
    volume, best_b = 0.0, ref_point[1]
    for a, b in good:                                 # descending in the first objective
        if b > best_b:
            volume += (a - ref_point[0]) * (b - best_b)
            best_b = b
    return volume
