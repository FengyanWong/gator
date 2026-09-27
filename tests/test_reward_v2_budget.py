"""Pure shared-reservation arithmetic. No simulated circuit or backend."""
import pytest

from gator_workbench.budget import BudgetError, BudgetLedger


def finish(ledger, key, calls):
    ledger.start(key)
    ledger.begin_attempt(key)
    ledger.end_attempt(key, launches=calls)
    ledger.complete(key)


def test_stage_c_full_plan_admission_before_dispatch():
    ledger = BudgetLedger(20, max_launches=11)
    for _ in range(2):
        finish(ledger, ledger.reserve(launches=1), 1)
    first = ledger.reserve(launches=5)
    assert first is not None and ledger.reserve(launches=5) is None
    finish(ledger, first, 5)
    assert ledger.launches == 7 and ledger.reserve(launches=5) is None
    assert ledger.snapshot()['reserved_launches'] == 0


def test_partial_candidate_releases_only_unused_capacity():
    ledger = BudgetLedger(10, max_launches=10)
    a, b = ledger.reserve(launches=5), ledger.reserve(launches=5)
    assert a and b and ledger.reserve() is None
    finish(ledger, a, 2)
    assert ledger.launches == 2 and ledger.snapshot()['reserved_launches'] == 5
    assert ledger.reserve(launches=4) is None
    c = ledger.reserve(launches=3)
    assert c
    ledger.release(c)
    finish(ledger, b, 5)
    assert ledger.launches == 7


def test_double_receipt_and_overspend_refused():
    ledger = BudgetLedger(10, max_launches=5)
    key = ledger.reserve(launches=5)
    ledger.start(key)
    ledger.begin_attempt(key)
    assert ledger.attempt_allowance(key) == 5
    with pytest.raises(BudgetError):
        ledger.end_attempt(key, launches=6)
    with pytest.raises(BudgetError):
        ledger.begin_attempt(key)
    ledger.end_attempt(key, launches=5, uncertain=5)
    with pytest.raises(BudgetError):
        ledger.end_attempt(key, launches=0)
    ledger.complete(key, failed=True)
    assert ledger.snapshot()['confirmed_launches'] == 0 and ledger.launches == 5
    restored = BudgetLedger(10, max_launches=5)
    restored.load_state(ledger.state_dict())
    assert restored.snapshot()['uncertain_launches'] == 5 and restored.reserve() is None


def test_standalone_collectors_share_whole_candidate_budget(tmp_path):
    from analog_optimizer.training.runner import LaunchBudget
    budget = LaunchBudget(11, journal=tmp_path / 'ledger.json')
    assert budget.reserve('lane-0', 1) and budget.reserve('lane-1', 1)
    budget.finish('lane-0', 1)
    budget.finish('lane-1', 1)
    assert budget.reserve('lane-0', 5)
    assert not budget.reserve('lane-1', 5)
    budget.finish('lane-0', 5)
    assert not budget.reserve('lane-1', 5)
    assert budget.snapshot()['charged_calls'] == 7


def test_crash_reconciliation_cannot_release_unknown_allowance():
    ledger = BudgetLedger(10, max_launches=11)
    report = ledger.reconcile(charged=2, completed=2, failed=1, launches=6,
                              uncertain=5, retries=0, cache_hits=0)
    assert report['after']['uncertain_launches'] == 5
    ledger.reconcile(charged=1, completed=1, failed=0, launches=1, uncertain=0, retries=0, cache_hits=0)
    assert ledger.snapshot()['launches'] == 6 and ledger.snapshot()['confirmed_launches'] == 1
