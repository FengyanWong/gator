"""Shared evaluation budget with strict accounting (specification section 9).

* ``max_evaluations`` counts NEW candidate evaluations that may START in the whole
  run. Every lane shares this one ledger.
* reserve -> start: a slot is reserved before dispatch and CHARGED when execution
  begins. A reservation that never started may be released. A started evaluation is
  never refunded, whatever its outcome.
* A retry keeps its ``evaluation_id`` and adds a simulator launch, not an evaluation.
* Simulator launches are counted separately, including failures and retries.
* Cache hits are never counted as simulations.
* Agent token usage is not tracked here at all; it must never mix with this budget.
"""
from __future__ import annotations

from copy import deepcopy
import threading
from uuid import uuid4


class BudgetError(RuntimeError):
    """An invalid evaluation or simulator-launch budget transition."""
    pass


class BudgetLedger:
    """Track reserved and charged evaluations, simulator launches, retries, and feasibility milestones under a lock."""
    VERSION = 'budget-ledger-v1'

    def __init__(self, max_evaluations, *, max_launches=None, max_retries=0):
        if type(max_evaluations) is not int or max_evaluations < 1:
            raise ValueError('max_evaluations must be a positive integer')
        if max_launches is not None and (type(max_launches) is not int or max_launches < 1):
            raise ValueError('max_launches must be a positive integer or None')
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError('max_retries must be a nonnegative integer')
        self.max_evaluations, self.max_launches, self.max_retries = max_evaluations, max_launches, max_retries
        self._lock = threading.RLock()
        self._reserved: dict[str, int] = {}
        self._in_flight: dict[str, dict] = {}      # evaluation_id -> {dispatch_index, attempts, launches}
        self._launch_holds = 0                     # attempts running whose launch is not yet confirmed
        self.charged = 0          # evaluations started (the budget figure)
        self.completed = 0
        self.failed = 0
        self.released = 0
        self.launches = 0         # actual simulator launches
        self.retries = 0
        self.cache_hits = 0
        self.first_feasible = None
        self.first_nominal_feasible = None
        self.uncertain_launches = 0

    # ------------------------------------------------------------------ evaluations
    def remaining(self) -> int:
        """Return evaluation capacity after both charged work and outstanding reservations."""
        with self._lock:
            return self.max_evaluations - self.charged - len(self._reserved)

    def _launch_room(self, extra=0) -> bool:
        if self.max_launches is None:
            return True
        pending_first = sum(item['allowance'] for item in self._in_flight.values() if item['attempts'] == 0)
        return self.launches + self._launch_holds + pending_first + sum(self._reserved.values()) + extra <= self.max_launches

    def reserve(self, evaluation_id=None, *, launches=1):
        """Reserve one evaluation before dispatch. Returns its ID, or None when exhausted."""
        with self._lock:
            if type(launches) is not int or launches < 1:
                raise ValueError('Reserve a positive finite number of launches for the whole candidate')
            if self.charged + len(self._reserved) >= self.max_evaluations:
                return None
            if not self._launch_room(extra=launches):
                return None
            evaluation_id = evaluation_id or uuid4().hex
            if evaluation_id in self._reserved or evaluation_id in self._in_flight:
                raise BudgetError(f'Evaluation {evaluation_id} is already reserved or running')
            self._reserved[evaluation_id] = launches
            return evaluation_id

    def release(self, evaluation_id) -> None:
        """Refund a reservation that never started (cancelled before dispatch)."""
        with self._lock:
            if evaluation_id in self._in_flight:
                raise BudgetError('A started evaluation is never refunded')
            if evaluation_id not in self._reserved:
                raise BudgetError(f'No reservation for {evaluation_id}')
            del self._reserved[evaluation_id]
            self.released += 1

    def start(self, evaluation_id) -> int:
        """Execution begins: charge the budget. Returns the 1-based dispatch index."""
        with self._lock:
            if evaluation_id not in self._reserved:
                raise BudgetError(f'Cannot start {evaluation_id} without a reservation')
            allowance = self._reserved.pop(evaluation_id)
            self.charged += 1
            self._in_flight[evaluation_id] = dict(dispatch_index=self.charged, attempts=0, launches=0,
                                                 allowance=allowance, attempt_active=False)
            return self.charged

    # ------------------------------------------------------------------ attempts / launches
    def may_retry(self, evaluation_id) -> bool:
        """Check whether an inactive evaluation attempt has retry and simulator-launch capacity."""
        with self._lock:
            item = self._in_flight.get(evaluation_id)
            if item is None:
                return False
            return (not item['attempt_active'] and item['attempts'] - 1 < self.max_retries
                    and self._launch_room(extra=item['allowance']))

    def begin_attempt(self, evaluation_id) -> int:
        """Returns the 1-based attempt number. Attempt > 1 is a retry of the SAME evaluation."""
        with self._lock:
            item = self._in_flight.get(evaluation_id)
            if item is None:
                raise BudgetError(f'{evaluation_id} is not running')
            if item['attempt_active']:
                raise BudgetError('Previous attempt has not completed')
            if item['attempts'] >= 1 + self.max_retries:
                raise BudgetError('max_retries exhausted')
            if item['attempts'] >= 1 and not self._launch_room(extra=item['allowance']):
                raise BudgetError('max_spectre_launches exhausted')
            item['attempts'] += 1
            item['attempt_active'] = True
            self._launch_holds += item['allowance']
            if item['attempts'] > 1:
                self.retries += 1
            return item['attempts']

    def attempt_allowance(self, evaluation_id):
        """Return the simulator-launch allowance of an active attempt or reject an inactive one."""
        with self._lock:
            item = self._in_flight[evaluation_id]
            if not item['attempt_active']:
                raise BudgetError('No active attempt allowance')
            return item['allowance']

    def end_attempt(self, evaluation_id, *, launches: int, uncertain=0) -> None:
        """Record how many simulator launches the attempt actually made (0 if it failed earlier)."""
        with self._lock:
            if type(launches) is not int or launches < 0:
                raise ValueError('launches must be a nonnegative integer')
            item = self._in_flight.get(evaluation_id)
            if item is None:
                raise BudgetError(f'{evaluation_id} is not running')
            if not item['attempt_active'] or launches > item['allowance']:
                raise BudgetError('No active attempt or reported calls exceed its reservation')
            if type(uncertain) is not int or not 0 <= uncertain <= launches:
                raise ValueError('Uncertain calls must be included in conservative charged launches')
            self._launch_holds -= item['allowance']
            item['attempt_active'] = False
            item['launches'] += launches
            self.launches += launches
            self.uncertain_launches += uncertain

    def complete(self, evaluation_id, *, failed=False, cache_hit=False) -> dict:
        """Finish an evaluation after all attempts settle and update completion, failure, and cache-hit counters."""
        with self._lock:
            item = self._in_flight.get(evaluation_id)
            if item is None:
                raise BudgetError(f'{evaluation_id} is not running')
            if cache_hit and item['launches']:
                raise BudgetError('A cache hit cannot have simulator launches')
            if item['attempt_active']:
                raise BudgetError('Cannot finish a candidate with an outstanding attempt')
            del self._in_flight[evaluation_id]
            self.completed += 1
            self.failed += int(failed)
            self.cache_hits += int(cache_hit)
            return item

    # ------------------------------------------------------------------ first feasibility
    def mark_first_feasible(self, evaluation_id, *, dispatch_index, commit_seq, active_seconds, wall_seconds, nominal=False):
        """Called when the scheduler RECEIVES a result and confirms every hard constraint.

        Primary convention: evaluations charged at that moment, INCLUDING those started and
        still in flight. The other figures allow alternative conventions to be analysed.
        """
        with self._lock:
            field = 'first_nominal_feasible' if nominal else 'first_feasible'
            if getattr(self, field) is not None:
                return None
            first = dict(
                evaluation_id=evaluation_id,
                first_feasible_eval_count=self.charged,
                dispatch_index=dispatch_index,
                completed_count=self.completed,
                in_flight_count=len(self._in_flight),
                in_flight_evaluation_ids=sorted(self._in_flight),
                spectre_launches=self.launches,
                commit_seq=commit_seq,
                active_seconds=active_seconds, wall_seconds=wall_seconds,
                convention='evaluations charged (started) when the scheduler confirmed feasibility, '
                           'including evaluations still in flight')
            setattr(self, field, first)
            return deepcopy(first)

    def restore_first_feasible(self, first, *, nominal=False) -> bool:
        """After a crash: the first (nominally) feasible design was found after the last save point, so the restored
        ledger does not know it. `first`: its record as `mark_first_feasible` made it (the run's log), or as the
        evaluations table gives it. Never replaces one the ledger holds. True when taken."""
        with self._lock:
            field = 'first_nominal_feasible' if nominal else 'first_feasible'
            if getattr(self, field) is not None:
                return False
            setattr(self, field, deepcopy(first))
            return True

    # ------------------------------------------------------------------ views / persistence
    def in_flight_ids(self):
        """Return a sorted snapshot of evaluation identifiers still in flight."""
        with self._lock:
            return sorted(self._in_flight)

    def snapshot(self) -> dict:
        """Return a locked snapshot of evaluation and launch budgets with feasibility milestones."""
        with self._lock:
            return dict(max_evaluations=self.max_evaluations, max_launches=self.max_launches,
                        max_retries=self.max_retries, charged=self.charged, reserved=len(self._reserved),
                        in_flight=len(self._in_flight), completed=self.completed, failed=self.failed,
                        released=self.released, remaining=self.max_evaluations - self.charged - len(self._reserved),
                        launches=self.launches, retries=self.retries, cache_hits=self.cache_hits,
                        reserved_launches=sum(self._reserved.values()) + self._launch_holds,
                        uncertain_launches=self.uncertain_launches,
                        confirmed_launches=self.launches - self.uncertain_launches,
                        first_nominal_feasible=deepcopy(self.first_nominal_feasible),
                        first_feasible=deepcopy(self.first_feasible))

    def state_dict(self) -> dict:
        """Persisted inside a checkpoint at a boundary with nothing reserved or in flight."""
        with self._lock:
            if self._reserved or self._in_flight:
                raise BudgetError('The ledger can only be saved at a quiescent boundary')
            return dict(version=self.VERSION, charged=self.charged, completed=self.completed, failed=self.failed,
                        released=self.released, launches=self.launches, retries=self.retries,
                        cache_hits=self.cache_hits, first_feasible=deepcopy(self.first_feasible),
                        uncertain_launches=self.uncertain_launches, first_nominal_feasible=deepcopy(self.first_nominal_feasible))

    def load_state(self, state) -> None:
        """resume keeps the existing counters (fine_tune creates a fresh ledger instead)."""
        with self._lock:
            if state.get('version') != self.VERSION:
                raise BudgetError('Unsupported ledger state')
            for key in ('charged', 'completed', 'failed', 'released', 'launches', 'retries', 'cache_hits'):
                value = state[key]
                if type(value) is not int or value < 0:
                    raise BudgetError(f'Invalid ledger counter {key}')
                setattr(self, key, value)
            if self.completed > self.charged:
                raise BudgetError('Inconsistent ledger: completed exceeds charged')
            self.first_feasible = deepcopy(state.get('first_feasible'))
            self.first_nominal_feasible = deepcopy(state.get('first_nominal_feasible'))
            self.uncertain_launches = state.get('uncertain_launches', 0)
            if type(self.uncertain_launches) is not int or not 0 <= self.uncertain_launches <= self.launches:
                raise BudgetError('Invalid uncertain launch counter')

    def reconcile(self, *, charged, completed, failed, launches, retries, cache_hits, uncertain=0) -> dict:
        """After a crash, durable tables are the source of truth: evaluations committed after the
        last checkpoint DID consume budget. Never lowers a counter."""
        with self._lock:
            before = self.state_dict()
            self.charged, self.completed = max(self.charged, charged), max(self.completed, completed)
            self.failed, self.launches = max(self.failed, failed), max(self.launches, launches)
            self.retries, self.cache_hits = max(self.retries, retries), max(self.cache_hits, cache_hits)
            self.uncertain_launches = max(self.uncertain_launches, uncertain)
            if not 0 <= self.uncertain_launches <= self.launches:
                raise BudgetError('Unresolved launch holds must be included in conservative cost')
            return dict(before=before, after=self.state_dict())
