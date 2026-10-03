"""Agent 2 — Customer Profile Analyzer.

Builds behavioral payment profile from current event + prior failure signals.
Deterministic — no LLM (fintech-safe).
"""

from __future__ import annotations

import hashlib
from typing import Any

from models.schemas import CustomerPaymentProfile


def _stable_bucket(customer_id: str | None, buckets: int = 3) -> int:
    seed = (customer_id or "anonymous").encode()
    return int(hashlib.sha256(seed).hexdigest(), 16) % buckets


def build_customer_profile(
    *,
    customer_id: str | None,
    payment_method: str | None,
    amount_paise: int,
    prior_failures_24h: int = 0,
    payment_history: list[dict[str, Any]] | None = None,
) -> CustomerPaymentProfile:
    history = payment_history or []
    method_stats: dict[str, list[bool]] = {}
    for row in history:
        method = row.get("method") or "unknown"
        ok = bool(row.get("success"))
        method_stats.setdefault(method, []).append(ok)

    success_rate_by_method: dict[str, float] = {}
    for method, outcomes in method_stats.items():
        success_rate_by_method[method] = round(sum(outcomes) / len(outcomes), 2)

    # Preferred method: last success, else highest success rate, else current method
    last_success = next((h.get("method") for h in reversed(history) if h.get("success")), None)
    if not last_success and success_rate_by_method:
        last_success = max(success_rate_by_method, key=success_rate_by_method.get)
    preferred = last_success or payment_method or "upi"

    # Heuristic AOV from history or current amount
    amounts = [int(h["amount_paise"]) for h in history if h.get("amount_paise")]
    aov = int(sum(amounts) / len(amounts)) if amounts else amount_paise

    # Retry window heuristic (India peak UPI mornings/evenings)
    bucket = _stable_bucket(customer_id)
    windows = ["09:00-11:00 IST", "18:00-21:00 IST", "12:00-14:00 IST"]
    best_window = windows[bucket]

    if prior_failures_24h >= 3:
        risk = "high"
    elif prior_failures_24h == 2 or aov >= 500000:  # ₹5,000+
        risk = "elevated"
    elif prior_failures_24h == 0 and (success_rate_by_method.get(preferred, 1.0) >= 0.8):
        risk = "low"
    else:
        risk = "medium"

    return CustomerPaymentProfile(
        preferred_method=preferred,
        success_rate_by_method=success_rate_by_method or {preferred: 0.7},
        best_retry_window=best_window,
        risk_tier=risk,
        prior_failures_24h=prior_failures_24h,
        average_order_value_paise=aov,
        last_success_method=last_success,
    )
