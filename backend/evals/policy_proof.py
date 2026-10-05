#!/usr/bin/env python3
"""Attack the policy engine — prove guardrails block illegal actions.

Offline. No HTTP/DB/LLM.

Usage:
  docker compose run --rm --no-deps api python -m evals.policy_proof
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from models.schemas import FailureType, RecoveryStrategy, StrategyDecision  # noqa: E402
from policy.engine import PolicyContext, apply_policy  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


def _dec(strategy: RecoveryStrategy) -> StrategyDecision:
    return StrategyDecision(
        strategy=strategy,
        channel="whatsapp",
        timing_offset_minutes=0,
        personalization_params={},
        reasoning="proposed by planner",
    )


def _check(name: str, ok: bool, detail: str) -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}: {detail}")
    return ok


def main() -> int:
    print()
    print("POLICY GUARDRAIL PROOFS")
    print("─" * 64)
    passed = 0
    total = 0

    cases = []

    # 1) max retries
    v = apply_policy(
        _dec(RecoveryStrategy.retry_same_method),
        PolicyContext(
            failure_type=FailureType.wrong_otp,
            strategy=RecoveryStrategy.retry_same_method,
            retry_count=3,
            prior_failures_24h=0,
        ),
    )
    cases.append(
        (
            "MAX_RETRIES blocks retry",
            v.strategy == RecoveryStrategy.escalate_to_human
            and "MAX_RETRIES_OR_REPEAT_FAILURES" in v.blocked_rules,
            f"→ {v.strategy.value} rules={v.blocked_rules}",
        )
    )

    # 2) DNC
    v = apply_policy(
        _dec(RecoveryStrategy.offer_emi),
        PolicyContext(
            failure_type=FailureType.insufficient_funds,
            strategy=RecoveryStrategy.offer_emi,
            customer_id="cust_dnc_demo",
            dnc_customer_ids=frozenset({"cust_dnc_demo"}),
        ),
    )
    cases.append(
        (
            "DNC blocks outbound",
            v.strategy == RecoveryStrategy.escalate_to_human and "DNC" in v.blocked_rules,
            f"→ {v.strategy.value} rules={v.blocked_rules}",
        )
    )

    # 3) permanent rail
    v = apply_policy(
        _dec(RecoveryStrategy.retry_same_method),
        PolicyContext(
            failure_type=FailureType.vpa_invalid,
            strategy=RecoveryStrategy.retry_same_method,
        ),
    )
    cases.append(
        (
            "PERMANENT_RAIL blocks same-method retry",
            v.strategy == RecoveryStrategy.suggest_alternate_method
            and "PERMANENT_RAIL_NO_RETRY" in v.blocked_rules,
            f"→ {v.strategy.value} rules={v.blocked_rules}",
        )
    )

    # 4) quiet hours → delay
    quiet_now = datetime(2026, 10, 5, 23, 30, tzinfo=IST)
    v = apply_policy(
        _dec(RecoveryStrategy.suggest_alternate_method),
        PolicyContext(
            failure_type=FailureType.card_blocked,
            strategy=RecoveryStrategy.suggest_alternate_method,
            now=quiet_now,
            quiet_hours_start=22,
            quiet_hours_end=8,
        ),
    )
    cases.append(
        (
            "QUIET_HOURS defers outbound",
            v.strategy == RecoveryStrategy.delay_and_retry and "QUIET_HOURS" in v.blocked_rules,
            f"→ {v.strategy.value} offset={v.decision.timing_offset_minutes}m",
        )
    )

    # 5) daytime pass-through
    day = datetime(2026, 10, 5, 14, 0, tzinfo=IST)
    v = apply_policy(
        _dec(RecoveryStrategy.retry_same_method),
        PolicyContext(
            failure_type=FailureType.wrong_otp,
            strategy=RecoveryStrategy.retry_same_method,
            retry_count=0,
            now=day,
        ),
    )
    cases.append(
        (
            "Daytime allows retry",
            v.allowed and v.strategy == RecoveryStrategy.retry_same_method,
            f"→ {v.strategy.value} allowed={v.allowed}",
        )
    )

    # 6) escalate already OK
    v = apply_policy(
        _dec(RecoveryStrategy.escalate_to_human),
        PolicyContext(
            failure_type=FailureType.unknown,
            strategy=RecoveryStrategy.escalate_to_human,
            customer_id="cust_dnc_demo",
            dnc_customer_ids=frozenset({"cust_dnc_demo"}),
        ),
    )
    cases.append(
        (
            "Escalate under DNC stays escalate",
            v.strategy == RecoveryStrategy.escalate_to_human,
            f"→ {v.strategy.value}",
        )
    )

    for name, ok, detail in cases:
        total += 1
        if _check(name, ok, detail):
            passed += 1

    print("─" * 64)
    print(f"Result: {passed}/{total} passed")
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
