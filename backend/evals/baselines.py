"""Decision policies under test. Revive uses the production planner — not a copy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from agents.customer_profiler import build_customer_profile
from agents.strategy_planner import plan_strategy
from models.schemas import FailureType, RecoveryStrategy, StrategyDecision
from policy.engine import PolicyContext, apply_policy

Policy = Callable[..., StrategyDecision]

# Midday IST so quiet-hours don't dominate money benchmarks
_EVAL_NOW = datetime(2026, 10, 5, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def _decision(strategy: RecoveryStrategy, reasoning: str) -> StrategyDecision:
    return StrategyDecision(
        strategy=strategy,
        channel="sms",
        timing_offset_minutes=0,
        personalization_params={},
        reasoning=reasoning,
    )


def always_retry(*, failure_type: FailureType, **_kwargs) -> StrategyDecision:
    return _decision(
        RecoveryStrategy.retry_same_method,
        "Baseline A: every failure → retry_same_method.",
    )


# Ops playbook: one strategy per failure type. No amount, profile, or retry_count.
STATIC_MAP: dict[FailureType, RecoveryStrategy] = {
    FailureType.insufficient_funds: RecoveryStrategy.retry_same_method,
    FailureType.wrong_otp: RecoveryStrategy.retry_same_method,
    FailureType.bank_timeout: RecoveryStrategy.retry_same_method,
    FailureType.card_blocked: RecoveryStrategy.suggest_alternate_method,
    FailureType.upi_mpin_incorrect: RecoveryStrategy.retry_same_method,
    FailureType.netbanking_down: RecoveryStrategy.delay_and_retry,
    FailureType.vpa_invalid: RecoveryStrategy.suggest_alternate_method,
    FailureType.threeds_failure: RecoveryStrategy.suggest_alternate_method,
    FailureType.unknown: RecoveryStrategy.escalate_to_human,
}


def static_map(*, failure_type: FailureType, **_kwargs) -> StrategyDecision:
    strategy = STATIC_MAP.get(failure_type, RecoveryStrategy.escalate_to_human)
    return _decision(
        strategy,
        f"Baseline B: static map {failure_type.value} → {strategy.value}.",
    )


def revive_rules(
    *,
    failure_type: FailureType,
    amount_paise: int,
    method: str,
    customer_id: str,
    prior_failures_24h: int,
    retry_count: int,
    strategy_performance: dict | None = None,
    **_kwargs,
) -> StrategyDecision:
    """Production Agent 2 + 3 + policy guard. Zero LLM."""
    profile = build_customer_profile(
        customer_id=customer_id,
        payment_method=method,
        amount_paise=amount_paise,
        prior_failures_24h=prior_failures_24h,
    )
    decision = plan_strategy(
        failure_type=failure_type,
        profile=profile,
        amount_paise=amount_paise,
        payment_method=method,
        retry_count=retry_count,
        strategy_performance=strategy_performance or {},
        use_llm=False,
    )
    verdict = apply_policy(
        decision,
        PolicyContext(
            failure_type=failure_type,
            strategy=decision.strategy,
            retry_count=retry_count,
            prior_failures_24h=prior_failures_24h,
            customer_id=customer_id,
            now=_EVAL_NOW,
        ),
    )
    return verdict.decision
