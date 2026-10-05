"""Money and mix rollups. Amounts stay paise until display."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from models.schemas import RecoveryStrategy


def recovered_paise(amount_paise: int, strategy: RecoveryStrategy, success: bool) -> int:
    if not success or strategy == RecoveryStrategy.escalate_to_human:
        return 0
    if strategy == RecoveryStrategy.offer_partial_payment:
        return amount_paise // 2
    return amount_paise


def expected_paise(amount_paise: int, strategy: RecoveryStrategy, rate: float) -> float:
    if strategy == RecoveryStrategy.escalate_to_human:
        return 0.0
    frac = 0.5 if strategy == RecoveryStrategy.offer_partial_payment else 1.0
    return amount_paise * frac * rate


def format_inr(paise: int | float) -> str:
    rupees = int(round(paise / 100.0))
    return f"₹{rupees:,}"


@dataclass
class SystemReport:
    name: str
    n: int = 0
    at_risk_paise: int = 0
    recovered_n: int = 0
    recovered_paise: int = 0
    expected_paise: float = 0.0
    escalated_n: int = 0
    by_failure: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(_fail_bucket))
    by_strategy: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def recovery_rate(self) -> float:
        return (self.recovered_n / self.n) if self.n else 0.0


def _fail_bucket() -> dict[str, int]:
    return {"n": 0, "recovered_n": 0, "at_risk_paise": 0, "recovered_paise": 0}


def add_row(
    report: SystemReport,
    *,
    failure_type: str,
    strategy: RecoveryStrategy,
    amount_paise: int,
    success: bool,
    rate: float,
) -> None:
    report.n += 1
    report.at_risk_paise += amount_paise
    rec = recovered_paise(amount_paise, strategy, success)
    report.recovered_paise += rec
    report.expected_paise += expected_paise(amount_paise, strategy, rate)
    if success and strategy != RecoveryStrategy.escalate_to_human:
        report.recovered_n += 1
    if strategy == RecoveryStrategy.escalate_to_human:
        report.escalated_n += 1
    report.by_strategy[strategy.value] += 1
    b = report.by_failure[failure_type]
    b["n"] += 1
    b["at_risk_paise"] += amount_paise
    b["recovered_paise"] += rec
    if success and strategy != RecoveryStrategy.escalate_to_human:
        b["recovered_n"] += 1
