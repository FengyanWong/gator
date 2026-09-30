from __future__ import annotations

from dataclasses import dataclass, field
import random


@dataclass
class Candidate:
    proposal: dict[str, float]
    source: str
    metadata: dict = field(default_factory=dict)


class RandomProposer:
    """The existing collector's draw order, including with a shared Random instance."""
    def __init__(self, group_ids, *, seed=0, rng=None):
        self.group_ids, self.rng = tuple(group_ids), rng if rng is not None else random.Random(seed)

    def propose(self, n, state=None):
        return [Candidate({g: self.rng.uniform(-1, 1) for g in self.group_ids}, 'random_warmup') for _ in range(n)]

    def observe(self, result):
        pass


class SeededProposer(RandomProposer):
    """Benchmark control: starting design followed by a seeded Latin hypercube."""
    def __init__(self, mapper, count, *, seed=0):
        if count < 1:
            raise ValueError('A seed design is required')
        super().__init__(mapper.group_ids, seed=seed)
        initial = {g.id: g.value for g in mapper.groups}
        self.queue = [Candidate(mapper.encode(initial), 'seeded_warmup')]
        self.refill_size = max(1, count - 1)
        self._refill(count - 1)

    def _refill(self, size):
        columns = {}
        for group in self.group_ids:
            values = [-1 + 2 * (i + self.rng.random()) / size for i in range(size)]
            self.rng.shuffle(values)
            columns[group] = values
        self.queue += [Candidate({g: columns[g][i] for g in self.group_ids}, 'seeded_warmup') for i in range(size)]

    def propose(self, n, state=None):
        while len(self.queue) < n:
            self._refill(self.refill_size)
        result, self.queue = self.queue[:n], self.queue[n:]
        return result


class SacProposer:
    def __init__(self, learner, *, deterministic=False):
        self.learner, self.deterministic = learner, deterministic

    def propose(self, n, state):
        observations = state['observations'][:n]
        return [Candidate(p, 'mean_policy' if self.deterministic else 'sac_policy')
                for p in self.learner.act(observations, deterministic=self.deterministic)]

    def observe(self, result):
        pass
