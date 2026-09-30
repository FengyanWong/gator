"""Persistable decisions only: no threads, simulator calls, or learner mutations."""
from dataclasses import dataclass, asdict
import math

METHODS = ('sac', 'llm_warmstart', 'llm', 'sac_llm_rescue')


@dataclass
class SearchSchedule:
    method: str
    warm_count: int = 8
    initial_updates: int = 8
    stall_window: int = 8
    max_rounds: int = 2
    admitted: int = 0
    trained: int = 0
    degraded: str | None = None
    stalled: int = 0
    rounds: int = 0
    armed: bool = False
    round_pending: bool = False
    best: tuple | None = None

    def __post_init__(self):
        if self.method not in METHODS:
            raise ValueError('Unknown search method')
        if any(type(n) is not int or n < 1 for n in (self.warm_count, self.initial_updates, self.stall_window, self.max_rounds)):
            raise ValueError('Search counts must be positive integers')
        if self.best is not None:
            self.best = tuple(self.best)

    @property
    def phase(self):
        if self.method == 'llm':
            return 'llm_search'
        if self.method == 'llm_warmstart':
            if self.admitted < self.warm_count:
                return 'llm_warmup'
            if self.trained < self.initial_updates:
                return 'initial_learning'
        return 'search'

    def available_seeds(self, pending=0):
        return max(0, self.warm_count - self.admitted - pending)

    def observe(self, result):
        if self.method == 'llm_warmstart' and self.phase == 'llm_warmup' and result.get('admitted'):
            self.admitted += 1
        if self.method != 'sac_llm_rescue':
            return
        score = None
        if result.get('valid'):
            value = result.get('reward') if result.get('feasible') else result.get('violation')
            if isinstance(value, (int, float)) and math.isfinite(value):
                score = (int(bool(result.get('feasible'))), value if result.get('feasible') else -value)
        improved = score is not None and (self.best is None or score > self.best)
        if improved:
            self.best, self.stalled = score, 0
        if result.get('source') == 'sac_policy':
            self.armed = True
        if (self.armed and not improved and not result.get('reset') and not result.get('infrastructure')
                and not self.round_pending):
            self.stalled += 1

    def rescue_due(self):
        return (self.method == 'sac_llm_rescue' and self.armed and not self.round_pending
                and self.rounds < self.max_rounds and self.stalled >= self.stall_window)

    def start_round(self):
        if not self.rescue_due():
            raise ValueError('No rescue is due')
        self.rounds += 1
        self.round_pending = True

    def finish_round(self):
        self.round_pending, self.stalled = False, 0

    def state_dict(self):
        return asdict(self)
