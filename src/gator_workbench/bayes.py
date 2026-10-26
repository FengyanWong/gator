"""Bayesian optimization as a second search method beside SAC (record 7.304; transfer experiment, plan section 6.2: "SAC
against Bayesian optimization", user 2026-10-10: "different opt on one circuit from scratch (sac bayesian)").

A run with `run.optimizer = "bayes"` is the same run in everything but who proposes the next design: the same task, the
same environment and reward, the same lanes, budget and recorded tables, the same random warm-up designs for the same
seed. Where a SAC run asks its policy, this run asks `Proposer.propose`; every finished design is told to it
(`Proposer.observe`), and the network is never updated. The optimizer package is not touched.

The method is TuRBO-1 (Eriksson et al., "Scalable global optimization via local Bayesian optimization", NeurIPS 2019),
the usual choice for some tens of variables, in its asynchronous form: one design per free lane.
  - a Gaussian process with a Matern-5/2 kernel and one length scale per variable, fitted by maximum marginal likelihood
    on the designs of the current trust region's run;
  - a trust region around the best design so far - a box whose sides follow the length scales - that doubles after 3
    improvements in a row, halves after max(4, variables) designs without one, and starts again from fresh random
    designs when it has shrunk to nothing;
  - Thompson sampling: one joint sample of the process over candidate designs in the box, the best of it is proposed.
Written with torch only (the pinned environment holds numpy, torch and PyG; no package is added). Designs live in the unit
cube here; the engine's proposals are the same numbers on [-1, 1].
"""
from __future__ import annotations

import ctypes
import ctypes.util
import math

import torch

DTYPE = torch.float64


def _malloc_trim():
    """glibc's `malloc_trim`, or None on a system without it."""
    try:
        return ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6').malloc_trim
    except (OSError, AttributeError):
        return None


_TRIM = _malloc_trim()


def release_freed_memory():
    """Give the memory a proposal freed back to the system (record 7.382). A proposal fits the process on up to 600
    designs and draws it jointly at 2,000 candidates: matrices of up to ~30 MB, freed when it returns. glibc's allocator
    keeps such freed blocks instead of returning them (its mmap threshold rises to the size of the freed block), so a
    run's process grew to 12-13 GB over 800 designs of a 22-variable task while 0.1 MB of tensors were alive. Trimming
    after each proposal keeps it near 0.3 GB, costs 8-14 % of the method's own time and changes no number."""
    if _TRIM is not None:
        _TRIM(0)


class GaussianProcess:
    """Matern-5/2, one length scale per input, a constant (zero) mean - the caller standardizes the targets - and
    Gaussian noise. `fit` maximizes the marginal likelihood from where the last fit ended."""
    LENGTH, SIGNAL, NOISE = (0.005, 2.0), (0.05, 20.0), (5e-4, 0.2)

    def __init__(self, dim):
        self.dim = dim
        start = [(0.5, self.LENGTH)] * dim + [(1.0, self.SIGNAL), (0.005, self.NOISE)]
        self.raw = torch.tensor([math.log((v - lo) / (hi - v)) for v, (lo, hi) in start], dtype=DTYPE)
        self.X = self.L = self.alpha = None

    def parameters(self, raw=None):
        """(length scales, signal variance, noise variance), each inside its bounds."""
        raw = self.raw if raw is None else raw
        bound = lambda r, lo_hi: lo_hi[0] + (lo_hi[1] - lo_hi[0]) * torch.sigmoid(r)
        return bound(raw[:self.dim], self.LENGTH), bound(raw[self.dim], self.SIGNAL), bound(raw[self.dim + 1], self.NOISE)

    @staticmethod
    def _kernel(A, B, length, signal):
        a, b = A / length, B / length
        squared = (a * a).sum(1, keepdim=True) + (b * b).sum(1) - 2.0 * a @ b.T
        s = math.sqrt(5.0) * torch.sqrt(squared.clamp_min(0.0) + 1e-12)
        return signal * (1.0 + s + s * s / 3.0) * torch.exp(-s)

    @staticmethod
    def _cholesky(K):
        eye = torch.eye(len(K), dtype=DTYPE)
        for jitter in (0.0, 1e-8, 1e-6, 1e-4, 1e-2):
            try:
                return torch.linalg.cholesky(K + jitter * eye)
            except torch.linalg.LinAlgError:
                continue
        raise torch.linalg.LinAlgError('the kernel matrix is not positive definite')

    def _negative_log_likelihood(self, raw, X, y):
        length, signal, noise = self.parameters(raw)
        L = torch.linalg.cholesky(self._kernel(X, X, length, signal) + noise * torch.eye(len(X), dtype=DTYPE))
        alpha = torch.cholesky_solve(y.unsqueeze(1), L).squeeze(1)
        return 0.5 * y @ alpha + torch.log(torch.diagonal(L)).sum() + 0.5 * len(X) * math.log(2.0 * math.pi)

    def fit(self, X, y, *, steps=40, learning_rate=0.1):
        """Fit the process and return its best finite negative log-likelihood, or None if none is found."""
        raw = self.raw.clone().requires_grad_(True)
        optimizer = torch.optim.Adam([raw], lr=learning_rate)
        best, best_raw = None, self.raw.clone()
        for _ in range(steps):
            optimizer.zero_grad()
            try:
                loss = self._negative_log_likelihood(raw, X, y)
            except torch.linalg.LinAlgError:
                break
            if not torch.isfinite(loss):
                break
            if best is None or loss.item() < best:
                best, best_raw = loss.item(), raw.detach().clone()
            loss.backward()
            optimizer.step()
        self.raw = best_raw
        with torch.no_grad():
            length, signal, noise = self.parameters()
            self.L = self._cholesky(self._kernel(X, X, length, signal) + noise * torch.eye(len(X), dtype=DTYPE))
            self.X, self.alpha = X, torch.cholesky_solve(y.unsqueeze(1), self.L).squeeze(1)
        return best

    def posterior(self, candidates):
        """(mean, covariance) of the process at `candidates`, given the fitted data."""
        with torch.no_grad():
            length, signal, _ = self.parameters()
            cross = self._kernel(candidates, self.X, length, signal)
            mean = cross @ self.alpha
            covariance = self._kernel(candidates, candidates, length, signal) - cross @ torch.cholesky_solve(cross.T, self.L)
            return mean, 0.5 * (covariance + covariance.T)

    def sample(self, candidates, generator):
        """One joint draw of the process at `candidates`."""
        mean, covariance = self.posterior(candidates)
        noise = torch.randn(len(candidates), generator=generator, dtype=DTYPE)
        try:
            return mean + self._cholesky(covariance) @ noise
        except torch.linalg.LinAlgError:              # numerically singular: independent draws from the marginals
            return mean + torch.sqrt(torch.diagonal(covariance).clamp_min(0.0)) * noise


class TrustRegionBO:
    """TuRBO-1, asked for one design at a time (ask) and told results in any order (tell). Maximizes. Designs are
    points of the unit cube. A design told without a value (its simulation failed) counts as the worst seen so far."""

    def __init__(self, dim, *, seed=0, n_init=None, n_candidates=None, length_init=0.8, length_min=0.5 ** 7, length_max=1.6,
                 success_tolerance=3, failure_tolerance=None, fit_steps=40, max_fit_points=600):
        if dim < 1:
            raise ValueError('Bayesian optimization needs at least one variable')
        self.dim = dim
        self.n_init = max(2, n_init if n_init is not None else 2 * dim)
        self.n_candidates = n_candidates or min(100 * dim, 2000)
        self.length_init, self.length_min, self.length_max = length_init, length_min, length_max
        self.success_tolerance = success_tolerance
        self.failure_tolerance = failure_tolerance or max(4, dim)
        self.fit_steps, self.max_fit_points = fit_steps, max_fit_points
        self.generator = torch.Generator().manual_seed(int(seed))
        self.initial = torch.quasirandom.SobolEngine(dim, scramble=True, seed=int(seed))
        self.inside = torch.quasirandom.SobolEngine(dim, scramble=True, seed=int(seed) + 1)
        self.X, self.y = [], []                     # every design told, in the order told
        self.start = 0                              # the first design of the current trust region's run
        self.asked = 0                              # designs asked here and not told yet
        self.restarts = 0
        self._begin()

    def _begin(self):
        self.length, self.successes, self.failures, self.best = self.length_init, 0, 0, None
        self.process = GaussianProcess(self.dim)

    # -------------------------------------------------------------------------------------------------- ask
    def ask(self):
        """Propose an initial sample or a posterior-selected candidate inside the current trust region."""
        told = len(self.X) - self.start
        self.asked += 1
        if told + self.asked - 1 < self.n_init or told < 2:
            return self.initial.draw(1).to(DTYPE)[0]
        X, y = torch.stack(self.X[self.start:]), torch.tensor(self.y[self.start:], dtype=DTYPE)
        if len(X) > self.max_fit_points:            # the newest designs and the best one: a fit stays under a second
            keep = torch.arange(len(X) - self.max_fit_points, len(X))
            best = int(y.argmax())
            if best < keep[0]:
                keep = torch.cat([torch.tensor([best]), keep[1:]])
            X, y = X[keep], y[keep]
        spread = y.std()
        z = (y - y.mean()) / (spread if spread > 1e-12 else 1.0)
        self.process.fit(X, z, steps=self.fit_steps)
        center = X[int(z.argmax())]
        length = self.process.parameters()[0].detach()
        weights = length / length.mean()
        weights = weights / torch.exp(torch.log(weights).mean())          # geometric mean 1: the box keeps its volume
        low = (center - weights * self.length / 2.0).clamp(0.0, 1.0)
        high = (center + weights * self.length / 2.0).clamp(0.0, 1.0)
        moved = low + (high - low) * self.inside.draw(self.n_candidates).to(DTYPE)
        change = torch.rand(self.n_candidates, self.dim, generator=self.generator, dtype=DTYPE) <= min(20.0 / self.dim, 1.0)
        none = ~change.any(1)                       # every candidate differs from the centre in at least one variable
        if none.any():
            change[none, torch.randint(0, self.dim, (int(none.sum()),), generator=self.generator)] = True
        candidates = center.expand(self.n_candidates, self.dim).clone()
        candidates[change] = moved[change]
        return candidates[int(self.process.sample(candidates, self.generator).argmax())]

    # -------------------------------------------------------------------------------------------------- tell
    def tell(self, x, value, *, asked=True):
        """One finished design. `asked` False: a design this object did not propose (the run's random warm-up)."""
        if asked:
            self.asked = max(0, self.asked - 1)
        mine = self.y[self.start:]
        if value is None or not math.isfinite(float(value)):
            value = min(mine) if mine else -1.0
        value = float(value)
        initial = len(mine) < self.n_init
        self.X.append(torch.as_tensor(x, dtype=DTYPE).clamp(0.0, 1.0))
        self.y.append(value)
        if initial or self.best is None:
            self.best = max(self.y[self.start:])
            return
        if value > self.best + 1e-3 * abs(self.best):
            self.successes, self.failures, self.best = self.successes + 1, 0, value
        else:
            self.successes, self.failures = 0, self.failures + 1
        if self.successes >= self.success_tolerance:
            self.length, self.successes = min(2.0 * self.length, self.length_max), 0
        elif self.failures >= self.failure_tolerance:
            self.length, self.failures = self.length / 2.0, 0
        if self.length < self.length_min:           # the region shrank to nothing: a new one from fresh random designs
            self.restarts += 1
            self.start = len(self.X)
            self._begin()

    def state(self) -> dict:
        """Summarize the observed designs, current trust region, restarts, and best reward."""
        return dict(designs=len(self.X), in_this_region=len(self.X) - self.start, restarts=self.restarts, length=self.length,
                    best=max(self.y) if self.y else None)


class Proposer:
    """The engine's side: proposals as the engine writes them - a number in [-1, 1] per parameter group, in the groups'
    order - and the reward of every finished design."""
    SOURCE = 'bayes_opt'

    def __init__(self, group_ids, *, seed=0, warmup=0, **options):
        self.group_ids = list(group_ids)
        options.setdefault('n_init', max(2 * len(self.group_ids), int(warmup)))
        self.search = TrustRegionBO(len(self.group_ids), seed=seed, **options)

    @property
    def observations(self) -> int:
        return len(self.search.X)

    def propose(self) -> dict:
        """Return a search proposal mapped to the workbench's normalized action coordinates."""
        point = self.search.ask()
        release_freed_memory()
        return {group: float(2.0 * point[index] - 1.0) for index, group in enumerate(self.group_ids)}

    def observe(self, proposal, reward, *, asked):
        """Record a proposal's reward and report whether the trust region restarted."""
        point = [(float(proposal[group]) + 1.0) / 2.0 for group in self.group_ids]
        before = self.search.restarts
        self.search.tell(point, reward, asked=asked)
        return self.search.restarts != before        # True when the trust region just started again
