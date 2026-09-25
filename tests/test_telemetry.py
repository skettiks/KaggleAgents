import pytest

from kaggle_agents.contracts import Budget, Usage
from kaggle_agents.telemetry import BudgetExhausted, BudgetLedger


def test_retry_cannot_reset_wall_clock_or_attempt_budget(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("kaggle_agents.telemetry.time.monotonic", lambda: clock[0])
    ledger = BudgetLedger(Budget(max_wall_seconds=10, max_attempts=2))
    assert ledger.reserve(8) == 8
    with pytest.raises(RuntimeError):
        ledger.reserve(8)
    clock[0] += 7
    ledger.settle(Usage(total_tokens=10, cost_usd=0.01, cost_source="reported"))
    assert ledger.reserve(8) == 3
    clock[0] += 3
    ledger.settle(Usage())
    with pytest.raises(BudgetExhausted):
        ledger.reserve(8)
    assert ledger.attempts == 2
    assert ledger.reserved_seconds == 0
    assert ledger.remaining == 0


def test_attempt_cap_also_applies_when_time_remains():
    ledger = BudgetLedger(Budget(max_wall_seconds=100, max_attempts=1))
    ledger.reserve(1)
    ledger.settle(Usage())
    with pytest.raises(BudgetExhausted):
        ledger.reserve(1)
    with pytest.raises(RuntimeError):
        ledger.settle(Usage())


def test_unknown_attempt_prevents_false_total():
    ledger = BudgetLedger(Budget(max_wall_seconds=100, max_attempts=2))
    for usage in [Usage(total_tokens=20, cost_usd=0.1, cost_source="estimated"), Usage()]:
        ledger.reserve(1)
        ledger.settle(usage)
    summary = ledger.usage_summary()
    assert summary.total_tokens is None
    assert summary.known_tokens == 20
    assert summary.total_cost_usd is None
    assert summary.known_cost_usd == 0.1
    assert summary.unknown_cost_attempts == 1
    assert summary.estimated_cost_attempts == 1
