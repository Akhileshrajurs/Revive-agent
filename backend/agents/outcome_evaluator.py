"""Agent 5 — Outcome Evaluator + Feedback Loop.

Simulates whether the recovery action would recover the payment
(until live Razorpay webhooks exist), then records strategy performance
so Agent 3 can prefer high-yield paths on the next run.

This is the piece merchants still do by hand: close the loop.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from models.schemas import FailureType, RecoveryOutcome, RecoveryStrategy

# Base recovery probability by strategy × failure family (India checkout reality)
_BASE_RATE: dict[RecoveryStrategy, float] = {
    RecoveryStrategy.retry_same_method: 0.42,
    RecoveryStrategy.suggest_alternate_method: 0.67,
    RecoveryStrategy.offer_emi: 0.48,
    RecoveryStrategy.offer_partial_payment: 0.55,
    RecoveryStrategy.delay_and_retry: 0.51,
    RecoveryStrategy.escalate_to_human: 0.22,
}

# Hard mismatches — retrying a blocked card rarely works
_PENALTY: dict[tuple[RecoveryStrategy, FailureType], float] = {
    (RecoveryStrategy.retry_same_method, FailureType.card_blocked): -0.30,
    (RecoveryStrategy.retry_same_method, FailureType.vpa_invalid): -0.35,
    (RecoveryStrategy.retry_same_method, FailureType.insufficient_funds): -0.18,
    (RecoveryStrategy.suggest_alternate_method, FailureType.card_blocked): 0.08,
    (RecoveryStrategy.offer_emi, FailureType.insufficient_funds): 0.10,
    (RecoveryStrategy.offer_partial_payment, FailureType.insufficient_funds): 0.08,
    (RecoveryStrategy.delay_and_retry, FailureType.bank_timeout): 0.12,
    (RecoveryStrategy.delay_and_retry, FailureType.netbanking_down): 0.10,
}


def _clamp(x: float, lo: float = 0.05, hi: float = 0.92) -> float:
    return max(lo, min(hi, x))


def expected_success_rate(
    strategy: RecoveryStrategy,
    failure_type: FailureType,
    *,
    historical_rate: float | None = None,
    historical_attempts: int = 0,
) -> float:
    """Blend prior domain rates with learned rates once we have enough samples."""
    prior = _BASE_RATE.get(strategy, 0.4) + _PENALTY.get((strategy, failure_type), 0.0)
    prior = _clamp(prior)
    if historical_rate is None or historical_attempts < 5:
        return prior
    # Empirical Bayes-ish blend — trust data as n grows
    weight = min(0.75, historical_attempts / 40.0)
    return _clamp((1 - weight) * prior + weight * historical_rate)


def evaluate_outcome(
    *,
    payment_id: str,
    strategy: RecoveryStrategy,
    failure_type: FailureType,
    payment_method: str | None,
    suggested_method: str | None = None,
    historical_rate: float | None = None,
    historical_attempts: int = 0,
) -> RecoveryOutcome:
    """Simulate recovery success. Deterministic per payment_id for demo replayability."""
    if strategy == RecoveryStrategy.escalate_to_human:
        return RecoveryOutcome(
            success=False,
            method_used=payment_method,
            time_to_recovery_seconds=None,
            strategy_used=strategy,
        )

    rate = expected_success_rate(
        strategy,
        failure_type,
        historical_rate=historical_rate,
        historical_attempts=historical_attempts,
    )
    seed = int(hashlib.sha256(f"{payment_id}:{strategy.value}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    success = rng.random() < rate

    method_used = payment_method
    if success and strategy == RecoveryStrategy.suggest_alternate_method:
        method_used = suggested_method or "upi"
    elif success and strategy == RecoveryStrategy.offer_emi:
        method_used = "emi"
    elif success and strategy == RecoveryStrategy.offer_partial_payment:
        method_used = payment_method or "upi"

    ttr = None
    if success:
        ttr = int(rng.uniform(45, 900))
        if strategy == RecoveryStrategy.delay_and_retry:
            ttr = int(rng.uniform(3600, 14400))

    return RecoveryOutcome(
        success=success,
        method_used=method_used,
        time_to_recovery_seconds=ttr,
        strategy_used=strategy,
    )


def outcome_reasoning(outcome: RecoveryOutcome, rate: float) -> str:
    if outcome.strategy_used == RecoveryStrategy.escalate_to_human:
        return "Escalated to human — no automated recovery attempt scored as success."
    verb = "RECOVERED" if outcome.success else "NOT recovered"
    ttr = (
        f" time_to_recovery={outcome.time_to_recovery_seconds}s"
        if outcome.time_to_recovery_seconds is not None
        else ""
    )
    return (
        f"Simulated attempt {verb} via method={outcome.method_used} "
        f"(modelled_success_rate={rate:.0%}).{ttr} "
        f"Outcome feeds strategy_performance for the next planner decision."
    )


def maybe_prefer_learned_strategy(
    candidates: list[RecoveryStrategy],
    failure_type: FailureType,
    performance: dict[str, dict[str, Any]],
    default: RecoveryStrategy,
) -> tuple[RecoveryStrategy, str | None]:
    """If learned data clearly beats the rule default, switch — with audit note."""
    best = default
    best_rate = -1.0
    note = None
    for strat in candidates:
        key = f"{strat.value}|{failure_type.value}"
        row = performance.get(key) or {}
        attempts = int(row.get("attempts") or 0)
        successes = int(row.get("successes") or 0)
        if attempts < 8:
            continue
        rate = successes / attempts
        default_rate = expected_success_rate(default, failure_type)
        if rate > best_rate and rate >= default_rate + 0.08:
            best = strat
            best_rate = rate
            note = (
                f"Learning override: {strat.value} recovered {successes}/{attempts} "
                f"({rate:.0%}) for {failure_type.value} vs rule default "
                f"{default.value} (~{default_rate:.0%})."
            )
    return best, note
