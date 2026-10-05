#!/usr/bin/env python3
"""Ablation: which layers actually move recovered ₹?

Versions on the same seeded batch:
  always_retry
  static_map
  rules_no_profile   — flat medium risk, no learning
  rules_no_learning  — real profile, empty performance
  revive_no_policy   — profile + learning, skip policy
  revive             — profile + learning + policy (production path)

Usage:
  docker compose run --rm --no-deps api python -m evals.ablation --n 2000 --seed 42
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agents.customer_profiler import build_customer_profile  # noqa: E402
from agents.outcome_evaluator import evaluate_outcome, expected_success_rate  # noqa: E402
from agents.strategy_planner import plan_strategy  # noqa: E402
from evals.baselines import always_retry, static_map  # noqa: E402
from evals.dataset import generate_batch  # noqa: E402
from evals.metrics import SystemReport, add_row, format_inr  # noqa: E402
from models.schemas import CustomerPaymentProfile, FailureType, RecoveryStrategy  # noqa: E402
from policy.engine import PolicyContext, apply_policy  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
# Fixed midday so quiet-hours doesn't dominate ablation variance
_EVAL_NOW = datetime(2026, 10, 5, 14, 0, tzinfo=IST)


def _flat_profile(method: str, prior: int) -> CustomerPaymentProfile:
    return CustomerPaymentProfile(
        preferred_method=method or "upi",
        success_rate_by_method={method or "upi": 0.7},
        best_retry_window="12:00-14:00 IST",
        risk_tier="medium",
        prior_failures_24h=prior,
        average_order_value_paise=None,
        last_success_method=None,
    )


def _decide(
    *,
    mode: str,
    failure_type: FailureType,
    amount_paise: int,
    method: str,
    customer_id: str,
    prior_failures_24h: int,
    retry_count: int,
    perf: dict,
):
    if mode == "always_retry":
        return always_retry(failure_type=failure_type), False
    if mode == "static_map":
        return static_map(failure_type=failure_type), False

    if mode == "rules_no_profile":
        profile = _flat_profile(method, prior_failures_24h)
        use_perf: dict = {}
        apply_pol = False
    elif mode == "rules_no_learning":
        profile = build_customer_profile(
            customer_id=customer_id,
            payment_method=method,
            amount_paise=amount_paise,
            prior_failures_24h=prior_failures_24h,
        )
        use_perf = {}
        apply_pol = False
    elif mode == "revive_no_policy":
        profile = build_customer_profile(
            customer_id=customer_id,
            payment_method=method,
            amount_paise=amount_paise,
            prior_failures_24h=prior_failures_24h,
        )
        use_perf = perf
        apply_pol = False
    else:  # revive
        profile = build_customer_profile(
            customer_id=customer_id,
            payment_method=method,
            amount_paise=amount_paise,
            prior_failures_24h=prior_failures_24h,
        )
        use_perf = perf
        apply_pol = True

    decision = plan_strategy(
        failure_type=failure_type,
        profile=profile,
        amount_paise=amount_paise,
        payment_method=method,
        retry_count=retry_count,
        strategy_performance=use_perf,
        use_llm=False,
    )
    if apply_pol:
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
        decision = verdict.decision
    return decision, mode in {"revive_no_policy", "revive"}


def _run(mode: str, events) -> SystemReport:
    report = SystemReport(name=mode)
    perf: dict[str, dict] = {}
    for ev in events:
        ft = FailureType(ev.failure_type)
        decision, learn = _decide(
            mode=mode,
            failure_type=ft,
            amount_paise=ev.amount_paise,
            method=ev.method,
            customer_id=ev.customer_id,
            prior_failures_24h=ev.prior_failures_24h,
            retry_count=ev.retry_count,
            perf=perf,
        )
        strategy = decision.strategy
        hist = perf.get(f"{strategy.value}|{ft.value}") or {}
        attempts = int(hist.get("attempts") or 0)
        successes = int(hist.get("successes") or 0)
        hist_rate = (successes / attempts) if attempts else None
        rate = expected_success_rate(
            strategy, ft, historical_rate=hist_rate, historical_attempts=attempts
        )
        outcome = evaluate_outcome(
            payment_id=ev.payment_id,
            strategy=strategy,
            failure_type=ft,
            payment_method=ev.method,
            suggested_method=(decision.personalization_params or {}).get("suggested_method"),
            historical_rate=hist_rate,
            historical_attempts=attempts,
        )
        add_row(
            report,
            failure_type=ft.value,
            strategy=strategy,
            amount_paise=ev.amount_paise,
            success=outcome.success,
            rate=rate,
        )
        if learn and strategy != RecoveryStrategy.escalate_to_human:
            key = f"{strategy.value}|{ft.value}"
            row = perf.setdefault(key, {"attempts": 0, "successes": 0})
            row["attempts"] += 1
            if outcome.success:
                row["successes"] += 1
    return report


MODES = [
    "always_retry",
    "static_map",
    "rules_no_profile",
    "rules_no_learning",
    "revive_no_policy",
    "revive",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    events = generate_batch(n=args.n, seed=args.seed)
    started = time.perf_counter()
    reports = [_run(m, events) for m in MODES]
    elapsed = int((time.perf_counter() - started) * 1000)

    base = reports[0]
    print()
    print("ABLATION STUDY  (simulator — same seed/batch)")
    print("─" * 78)
    print(f"{'Version':<20} {'Recovered':>14} {'Rate':>8} {'Δ vs retry':>12} {'Escalated':>10}")
    print("─" * 78)
    for r in reports:
        print(
            f"{r.name:<20} {format_inr(r.recovered_paise):>14} {r.recovery_rate:>7.1%} "
            f"{format_inr(r.recovered_paise - base.recovered_paise):>12} "
            f"{r.escalated_n:>10}"
        )
    print("─" * 78)
    print("Reading: each row adds one production layer. Policy should not crush ₹ —")
    print("it trades a little recovery for compliance (retries/DNC/quiet/permanent).")
    print(f"Wall time: {elapsed} ms")
    print()


if __name__ == "__main__":
    main()
