"""Agent 3 — Recovery Strategy Planner.

Rules pick the strategy (deterministic, audit-safe).
Learned strategy_performance can override when evidence is strong.
Gemini enriches `reasoning` for the Agent Trace View when available.
"""

from __future__ import annotations

from typing import Any

from agents.outcome_evaluator import maybe_prefer_learned_strategy
from llm.gemini_client import generate_json
from models.schemas import (
    CustomerPaymentProfile,
    FailureType,
    RecoveryStrategy,
    StrategyDecision,
)

_ALT_METHODS = {
    "card": "upi",
    "upi": "card",
    "netbanking": "upi",
    "wallet": "upi",
}


def _pick_strategy(
    failure_type: FailureType,
    profile: CustomerPaymentProfile,
    amount_paise: int,
    payment_method: str | None,
    retry_count: int,
) -> tuple[RecoveryStrategy, str, int, dict[str, Any]]:
    """Return strategy, channel, timing_offset_minutes, personalization_params."""
    if profile.prior_failures_24h >= 3 or retry_count >= 3:
        return (
            RecoveryStrategy.escalate_to_human,
            "email",
            0,
            {"reason": "repeated_failures"},
        )

    if failure_type == FailureType.bank_timeout:
        if retry_count == 0:
            return RecoveryStrategy.retry_same_method, "whatsapp", 5, {"method": payment_method}
        return RecoveryStrategy.delay_and_retry, "sms", 240, {"wait_hours": 4}

    if failure_type == FailureType.netbanking_down:
        return RecoveryStrategy.delay_and_retry, "whatsapp", 180, {"wait_hours": 3}

    if failure_type in {FailureType.card_blocked, FailureType.vpa_invalid, FailureType.threeds_failure}:
        alt = profile.preferred_method or _ALT_METHODS.get(payment_method or "card", "upi")
        if alt == payment_method:
            alt = _ALT_METHODS.get(payment_method or "card", "upi")
        return (
            RecoveryStrategy.suggest_alternate_method,
            "whatsapp",
            0,
            {"suggested_method": alt},
        )

    if failure_type == FailureType.insufficient_funds:
        if amount_paise >= 300000:  # ₹3,000+
            return (
                RecoveryStrategy.offer_emi,
                "whatsapp",
                0,
                {"emi_hint": True, "amount_paise": amount_paise},
            )
        if profile.risk_tier in {"low", "medium"} and profile.prior_failures_24h <= 1:
            return (
                RecoveryStrategy.offer_partial_payment,
                "whatsapp",
                0,
                {"partial_pct": 50},
            )
        return (
            RecoveryStrategy.suggest_alternate_method,
            "whatsapp",
            30,
            {"suggested_method": profile.preferred_method or "upi"},
        )

    if failure_type in {FailureType.wrong_otp, FailureType.upi_mpin_incorrect}:
        return RecoveryStrategy.retry_same_method, "sms", 2, {"gentle_retry": True}

    return RecoveryStrategy.escalate_to_human, "email", 0, {"reason": "unknown_failure"}


def _rule_reasoning(
    strategy: RecoveryStrategy,
    failure_type: FailureType,
    profile: CustomerPaymentProfile,
    params: dict[str, Any],
    learning_note: str | None,
) -> str:
    base = (
        f"Selected {strategy.value} because failure_type={failure_type.value}, "
        f"risk_tier={profile.risk_tier}, prior_failures_24h={profile.prior_failures_24h}, "
        f"params={params}."
    )
    if learning_note:
        return f"{base} {learning_note}"
    return base


def plan_strategy(
    *,
    failure_type: FailureType,
    profile: CustomerPaymentProfile,
    amount_paise: int,
    payment_method: str | None,
    retry_count: int = 0,
    customer_name: str | None = None,
    strategy_performance: dict[str, dict[str, Any]] | None = None,
    use_llm: bool = True,
) -> StrategyDecision:
    strategy, channel, offset, params = _pick_strategy(
        failure_type, profile, amount_paise, payment_method, retry_count
    )
    learning_note = None
    perf = strategy_performance or {}

    if strategy != RecoveryStrategy.escalate_to_human:
        candidates = [
            RecoveryStrategy.retry_same_method,
            RecoveryStrategy.suggest_alternate_method,
            RecoveryStrategy.offer_emi,
            RecoveryStrategy.offer_partial_payment,
            RecoveryStrategy.delay_and_retry,
        ]
        learned, learning_note = maybe_prefer_learned_strategy(
            candidates, failure_type, perf, strategy
        )
        if learned != strategy:
            strategy = learned
            if strategy == RecoveryStrategy.suggest_alternate_method and "suggested_method" not in params:
                params["suggested_method"] = profile.preferred_method or _ALT_METHODS.get(
                    payment_method or "card", "upi"
                )
            if strategy == RecoveryStrategy.delay_and_retry and "wait_hours" not in params:
                params["wait_hours"] = 4
            params["learning_override"] = True

    base_reasoning = _rule_reasoning(strategy, failure_type, profile, params, learning_note)

    # Replan / hot path: skip Gemini — rules already chose; saves hundreds of ms
    if not use_llm:
        return StrategyDecision(
            strategy=strategy,
            channel=channel,
            timing_offset_minutes=offset,
            personalization_params=params,
            reasoning=base_reasoning + " (rules-only replan; LLM skipped for latency)",
        )

    perf_summary = []
    for k, row in list(perf.items())[:8]:
        attempts = row.get("attempts") or 0
        successes = row.get("successes") or 0
        if attempts:
            perf_summary.append(f"{k}={successes}/{attempts}")

    prompt = f"""You are a senior payments recovery strategist at an Indian fintech (Razorpay-like).
Explain in 2-3 crisp sentences WHY this recovery strategy is correct for this failed payment.
Mention learning data only if relevant. Do not change the strategy.
Return JSON only: {{"reasoning": "..."}}

Customer: {customer_name or "Customer"}
Failure type: {failure_type.value}
Amount paise: {amount_paise}
Current method: {payment_method}
Preferred method: {profile.preferred_method}
Risk tier: {profile.risk_tier}
Prior failures 24h: {profile.prior_failures_24h}
Chosen strategy (LOCKED): {strategy.value}
Channel: {channel}
Params: {params}
Learning note: {learning_note or "none"}
Recent performance: {", ".join(perf_summary) or "insufficient data"}
"""
    enriched = generate_json(prompt, fallback={"reasoning": base_reasoning})
    reasoning = str(enriched.get("reasoning") or base_reasoning)

    return StrategyDecision(
        strategy=strategy,
        channel=channel,
        timing_offset_minutes=offset,
        personalization_params=params,
        reasoning=reasoning,
    )
