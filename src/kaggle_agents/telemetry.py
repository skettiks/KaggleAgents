"""Per-invocation time/attempt budget and append-only structured lifecycle events."""

import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kaggle_agents.contracts import Budget, Usage, UsageSummary


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class BudgetExhausted(Exception):
    pass


class BudgetLedger:
    """Single invocation, single active attempt. Persistent/concurrent ledger is M3+."""

    def __init__(self, budget: Budget) -> None:
        self.budget = budget
        self.started = time.monotonic()
        self.attempts = 0
        self.reserved_seconds = 0.0
        self.active = False
        self.usage: list[Usage] = []

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget.max_wall_seconds - self.elapsed)

    def reserve(self, timeout_seconds: float) -> float:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Timeout must be finite and positive")
        if self.active:
            raise RuntimeError("An attempt is already reserved")
        if self.attempts >= self.budget.max_attempts or self.remaining <= 0:
            raise BudgetExhausted
        self.reserved_seconds = min(timeout_seconds, self.remaining)
        self.attempts += 1
        self.active = True
        return self.reserved_seconds

    def settle(self, usage: Usage) -> None:
        if not self.active:
            raise RuntimeError("No reserved attempt")
        self.usage.append(usage)
        self.reserved_seconds = 0.0
        self.active = False

    def usage_summary(self) -> UsageSummary:
        unknown_tokens = sum(item.total_tokens is None for item in self.usage)
        unknown_costs = sum(item.cost_usd is None for item in self.usage)
        tokens = sum(item.total_tokens or 0 for item in self.usage)
        cost = math.fsum(item.cost_usd or 0 for item in self.usage)
        return UsageSummary(
            total_tokens=None if unknown_tokens else tokens,
            known_tokens=tokens,
            unknown_token_attempts=unknown_tokens,
            total_cost_usd=None if unknown_costs else cost,
            known_cost_usd=cost,
            unknown_cost_attempts=unknown_costs,
            estimated_cost_attempts=sum(item.cost_source == "estimated" for item in self.usage),
        )


class EventLog:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "schema_version": "0",
            "at": timestamp(),
            "run_id": self.run_id,
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
