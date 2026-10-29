"""TuRBO-1 with archived observations: `turbo_archive_v1`, the T+ arm of the comparison, and with an empty archive its T0
arm (plan section 5: "T+ is data transfer, not an RL-proposal warm start").

The method is production TuRBO-1 (`gator_workbench.bayes`: the same Gaussian process, trust region, candidate rule and
Thompson sampling, the same float32 Sobol draws) with these differences, fixed before any target run (WORKPLAN-steps2-7.md, item 5):
  - Archived designs (unit-cube points of the frozen target domain and their rewards under the run's goal view) are
    imported before the first proposal. They consume no ask, no budget and no trust-region success/failure step.
    An archived design without a reward counts as the worst archived reward (TuRBO's own rule for a failed design).
  - The process is fitted on EVERY archived and every online design. There is no newest-600 truncation; a fit larger
    than `max_fit_points` (default 1,415 = 600 archived + 800 online + 15 shared qualification) is refused, never cut.
  - The first trust region's data are the archived designs and the online designs, so it starts around the best design
    known. Its first `n_init` online designs are the run's common first designs, told with asked=False, and are not
    counted as successes or failures. Success and failure count online designs only.
  - When a region shrinks to nothing a new one starts from `n_init` fresh Sobol designs, centred on the best of its own
    designs - production's rule - but the process still fits every design, archived and online: nothing is dropped.
  - Online designs are told as the EXECUTED design (after the grid projection), the GP input the plan names.
`state_dict` / `load_state_dict` keep every number needed to resume exactly: data, region, counters, the process's
parameters, both Sobol sequences and the random generator.
"""
from __future__ import annotations

import math

import torch

from ..bayes import DTYPE, GaussianProcess, release_freed_memory
from .coords import to_proposal

VERSION = 'turbo_archive_v1'
FIT_CEILING = 1415


class ArchiveTrustRegionBO:
    """Maximizes. Points of the unit cube. `source_X` (n x dim) and `source_y` (n values, None for a failed design)."""

    def __init__(self, dim, *, seed=0, n_init=8, source_X=None, source_y=None, n_candidates=None, length_init=0.8,
                 length_min=0.5 ** 7, length_max=1.6, success_tolerance=3, failure_tolerance=None, fit_steps=40,
                 max_fit_points=FIT_CEILING):
        if dim < 1:
            raise ValueError('Bayesian optimization needs at least one variable')
        self.dim, self.seed = dim, int(seed)
        self.n_init = max(2, int(n_init))
        self.n_candidates = n_candidates or min(100 * dim, 2000)
        self.length_init, self.length_min, self.length_max = length_init, length_min, length_max
        self.success_tolerance = success_tolerance
        self.failure_tolerance = failure_tolerance or max(4, dim)
        self.fit_steps, self.max_fit_points = fit_steps, max_fit_points
        self.generator = torch.Generator().manual_seed(self.seed)
        self.initial = torch.quasirandom.SobolEngine(dim, scramble=True, seed=self.seed)
        self.inside = torch.quasirandom.SobolEngine(dim, scramble=True, seed=self.seed + 1)
        self.source_X, self.source_y, self.source_failed = self._import(source_X, source_y)
        self.X, self.y = [], []                     # online designs told, in the order told
        self.start = 0                              # the first online design of the current region
        self.region = 0                             # region 0 also holds the archived designs
        self.asked = 0
        self.restarts = 0
        self._begin()

    # ------------------------------------------------------------------------------------------------- archive
    def _import(self, source_X, source_y):
        if source_X is None or len(source_X) == 0:
            return torch.zeros((0, self.dim), dtype=DTYPE), [], 0
        X = torch.as_tensor(source_X, dtype=DTYPE)
        if X.ndim != 2 or X.shape[1] != self.dim or len(source_y) != len(X):
            raise ValueError('archived designs and rewards do not match the search space')
        if (X < 0).any() or (X > 1).any():
            raise ValueError('archived designs must lie in the unit cube of the target domain')
        valid = [float(v) for v in source_y if v is not None and math.isfinite(float(v))]
        worst = min(valid) if valid else -1.0
        y = [float(v) if v is not None and math.isfinite(float(v)) else worst for v in source_y]
        return X, y, len(y) - len(valid)

    def _begin(self):
        self.length, self.successes, self.failures, self.best = self.length_init, 0, 0, None
        self.process = GaussianProcess(self.dim)

    def _region_values(self):
        values = list(self.y[self.start:])
        return (list(self.source_y) + values) if self.region == 0 else values

    def _fit_data(self):
        X = [self.source_X] + ([torch.stack(self.X)] if self.X else [])
        X = torch.cat(X)
        y = torch.tensor(list(self.source_y) + list(self.y), dtype=DTYPE)
        if len(X) > self.max_fit_points:
            raise RuntimeError(f'{len(X)} designs exceed the fit ceiling of {self.max_fit_points}; nothing is ever cut')
        return X, y

    # -------------------------------------------------------------------------------------------------- ask
    def ask(self):
        """Propose a unit-cube design, using all archived and online observations when fitting the current region."""
        told = len(self.X) - self.start
        self.asked += 1
        fit_X, fit_y = self._fit_data()
        if (self.region > 0 and told + self.asked - 1 < self.n_init) or len(fit_X) < 2:
            return self.initial.draw(1).to(DTYPE)[0]
        spread = fit_y.std()
        z = (fit_y - fit_y.mean()) / (spread if spread > 1e-12 else 1.0)
        self.process.fit(fit_X, z, steps=self.fit_steps)
        # the region's centre: its best design (in region 0 the archived designs count)
        offset = len(self.source_y) + self.start if self.region > 0 else 0
        region_z = z[offset:] if self.region > 0 else z
        if len(region_z) == 0:                      # a new region with no design yet: its first Sobol design
            return self.initial.draw(1).to(DTYPE)[0]
        center = fit_X[offset + int(region_z.argmax())]
        length = self.process.parameters()[0].detach()
        weights = length / length.mean()
        weights = weights / torch.exp(torch.log(weights).mean())
        low = (center - weights * self.length / 2.0).clamp(0.0, 1.0)
        high = (center + weights * self.length / 2.0).clamp(0.0, 1.0)
        moved = low + (high - low) * self.inside.draw(self.n_candidates).to(DTYPE)
        change = torch.rand(self.n_candidates, self.dim, generator=self.generator, dtype=DTYPE) <= min(20.0 / self.dim,
            1.0)
        none = ~change.any(1)
        if none.any():
            change[none, torch.randint(0, self.dim, (int(none.sum()),), generator=self.generator)] = True
        candidates = center.expand(self.n_candidates, self.dim).clone()
        candidates[change] = moved[change]
        return candidates[int(self.process.sample(candidates, self.generator).argmax())]

    # -------------------------------------------------------------------------------------------------- tell
    def tell(self, x, value, *, asked=True, infrastructure=False):
        """One finished online design (its executed point). `asked` False: a design this object did not propose (the
        run's common first designs). `infrastructure`: the simulation failed for a reason outside the circuit (timeout,
        lost connection, licence): not evidence about the design, so it is not fitted (plan 4.2) - only the ask is
        settled. A design that failed physically (no convergence, a missing output) counts as the worst, as in TuRBO."""
        if asked:
            self.asked = max(0, self.asked - 1)
        if infrastructure:
            return
        region = self._region_values()
        if value is None or not math.isfinite(float(value)):
            value = min(region) if region else -1.0
        value = float(value)
        initial = len(self.y) - self.start < self.n_init
        self.X.append(torch.as_tensor(x, dtype=DTYPE).clamp(0.0, 1.0))
        self.y.append(value)
        if initial or self.best is None:
            self.best = max(self._region_values())
            return
        if value > self.best + 1e-3 * abs(self.best):
            self.successes, self.failures, self.best = self.successes + 1, 0, value
        else:
            self.successes, self.failures = 0, self.failures + 1
        if self.successes >= self.success_tolerance:
            self.length, self.successes = min(2.0 * self.length, self.length_max), 0
        elif self.failures >= self.failure_tolerance:
            self.length, self.failures = self.length / 2.0, 0
        if self.length < self.length_min:           # a new region from fresh Sobol designs; the fit keeps every design
            self.restarts += 1
            self.region += 1
            self.start = len(self.X)
            self._begin()

    def summary(self) -> dict:
        """Describe archive counts, online progress, the current trust region and the best known reward."""
        return dict(version=VERSION, archived=len(self.source_y), archived_failed=self.source_failed,
                    online=len(self.X),
                    in_this_region=len(self.X) - self.start, region=self.region, restarts=self.restarts,
                    length=self.length,
                    best=max(list(self.source_y) + list(self.y)) if (self.source_y or self.y) else None)

    # ------------------------------------------------------------------------------------------- save/restore
    def state_dict(self) -> dict:
        """Serialize observations, trust-region state and random generator positions needed for exact continuation."""
        return dict(version=VERSION, dim=self.dim, seed=self.seed, n_init=self.n_init, n_candidates=self.n_candidates,
                    length_init=self.length_init, length_min=self.length_min, length_max=self.length_max,
                    success_tolerance=self.success_tolerance, failure_tolerance=self.failure_tolerance,
                    fit_steps=self.fit_steps, max_fit_points=self.max_fit_points,
                    source_X=self.source_X.tolist(), source_y=list(self.source_y), source_failed=self.source_failed,
                    X=[x.tolist() for x in self.X], y=list(self.y), start=self.start, region=self.region,
                    asked=self.asked, restarts=self.restarts, length=self.length, successes=self.successes,
                    failures=self.failures, best=self.best, process_raw=self.process.raw.tolist(),
                    initial_drawn=int(self.initial.num_generated), inside_drawn=int(self.inside.num_generated),
                    generator_state=self.generator.get_state().tolist())

    @classmethod
    def from_state(cls, state: dict) -> 'ArchiveTrustRegionBO':
        """Restore the archived data, current region and random state of a supported saved search."""
        if state.get('version') != VERSION:
            raise ValueError(f"a {state.get('version')!r} search state is not {VERSION}")
        search = cls(state['dim'], seed=state['seed'], n_init=state['n_init'], n_candidates=state['n_candidates'],
                     length_init=state['length_init'], length_min=state['length_min'], length_max=state['length_max'],
                     success_tolerance=state['success_tolerance'], failure_tolerance=state['failure_tolerance'],
                     fit_steps=state['fit_steps'], max_fit_points=state['max_fit_points'])
        search.source_X = torch.tensor(state['source_X'], dtype=DTYPE).reshape(-1, state['dim'])
        search.source_y, search.source_failed = list(state['source_y']), state['source_failed']
        search.X = [torch.tensor(x, dtype=DTYPE) for x in state['X']]
        search.y = list(state['y'])
        for key in ('start', 'region', 'asked', 'restarts', 'length', 'successes', 'failures', 'best'):
            setattr(search, key, state[key])
        search.process.raw = torch.tensor(state['process_raw'], dtype=DTYPE)
        search.initial.fast_forward(state['initial_drawn'])
        search.inside.fast_forward(state['inside_drawn'])
        search.generator.set_state(torch.tensor(state['generator_state'], dtype=torch.uint8))
        return search


class ArchiveProposer:
    """The engine's side: proposals as the engine writes them (z in [-1, 1] per parameter group, in the groups' order),
    and each finished design told as its executed point with its reward."""
    SOURCE = 'bayes_opt'

    def __init__(self, groups, *, seed=0, archive=None, **options):
        self.groups = list(groups)
        self.group_ids = [g['id'] for g in self.groups]
        self._to_proposal = to_proposal
        source_X, source_y = (None, None) if archive is None else (archive['u'], archive['reward'])
        self.search = ArchiveTrustRegionBO(len(self.groups), seed=seed, source_X=source_X, source_y=source_y, **options)

    @property
    def observations(self) -> int:
        """Count online designs accepted by the search, excluding the imported archive."""
        return len(self.search.X)

    def propose(self) -> dict:
        """Return the next search design as one normalized proposal per parameter group."""
        point = self.search.ask()
        release_freed_memory()
        return {group: float(2.0 * point[index] - 1.0) for index, group in enumerate(self.group_ids)}

    def executed_point(self, executed: dict) -> list:
        """Map executed group values to the unit cube in the search's group order."""
        return [(self._to_proposal(g, executed[g['id']]) + 1.0) / 2.0 for g in self.groups]

    def observe(self, executed: dict, reward, *, asked, infrastructure=False) -> bool:
        """Record an executed design and report whether it restarted the trust region."""
        before = self.search.restarts
        self.search.tell(self.executed_point(executed), reward, asked=asked, infrastructure=infrastructure)
        return self.search.restarts != before

    def state_dict(self) -> dict:
        return dict(groups=self.groups, search=self.search.state_dict())

    @classmethod
    def from_state(cls, state: dict) -> 'ArchiveProposer':
        """Restore the parameter-group mapping and TuRBO search used by the run engine."""
        proposer = cls.__new__(cls)
        proposer.groups = list(state['groups'])
        proposer.group_ids = [g['id'] for g in proposer.groups]
        proposer._to_proposal = to_proposal
        proposer.search = ArchiveTrustRegionBO.from_state(state['search'])
        return proposer
