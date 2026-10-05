#!/usr/bin/env python3
"""Replay a synthetic failed-payment batch through baselines vs Revive.

Offline: no HTTP, Postgres, Redis, or Gemini.
Outcomes use production Agent 5 (`evaluate_outcome`) — simulated India-checkout
rates, not live Razorpay captures. Same seed → same table.

Usage (from repo root):
  PYTHONPATH=backend python3 backend/evals/replay.py
  PYTHONPATH=backend python3 backend/evals/replay.py --n 2000 --seed 42

Docker:
  docker compose run --rm --no-deps api python -m evals.replay --n 2000 --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

# Allow `python backend/evals/replay.py` from repo root.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from agents.outcome_evaluator import evaluate_outcome, expected_success_rate  # noqa: E402
from evals.baselines import always_retry, revive_rules, static_map  # noqa: E402
from evals.dataset import generate_batch  # noqa: E402
from evals.metrics import SystemReport, add_row, format_inr  # noqa: E402
from models.schemas import FailureType, RecoveryStrategy  # noqa: E402

SYSTEMS: list[tuple[str, Callable, bool]] = [
    ("always_retry", always_retry, False),
    ("static_map", static_map, False),
    ("revive", revive_rules, True),
]


def _run_system(name: str, policy: Callable, use_learning: bool, events) -> SystemReport:
    report = SystemReport(name=name)
    perf: dict[str, dict] = {}
    for ev in events:
        ft = FailureType(ev.failure_type)
        decision = policy(
            failure_type=ft,
            amount_paise=ev.amount_paise,
            method=ev.method,
            customer_id=ev.customer_id,
            prior_failures_24h=ev.prior_failures_24h,
            retry_count=ev.retry_count,
            strategy_performance=perf if use_learning else None,
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
        if use_learning and strategy != RecoveryStrategy.escalate_to_human:
            key = f"{strategy.value}|{ft.value}"
            row = perf.setdefault(key, {"attempts": 0, "successes": 0})
            row["attempts"] += 1
            if outcome.success:
                row["successes"] += 1
    return report


def _print_table(reports: list[SystemReport]) -> None:
    base = reports[0]
    print()
    print("REVIVE EVALUATION  (simulator — not live Razorpay GMV)")
    print("─" * 72)
    print(f"{'System':<16} {'N':>6} {'At risk':>14} {'Recovered':>14} {'Rate':>8} {'Uplift ₹':>12}")
    print("─" * 72)
    for r in reports:
        uplift = r.recovered_paise - base.recovered_paise
        print(
            f"{r.name:<16} {r.n:>6} {format_inr(r.at_risk_paise):>14} "
            f"{format_inr(r.recovered_paise):>14} {r.recovery_rate:>7.1%} "
            f"{format_inr(uplift):>12}"
        )
    print("─" * 72)
    print(
        f"Expected ₹ (sum amount × modelled rate):  "
        + "  |  ".join(f"{r.name} {format_inr(r.expected_paise)}" for r in reports)
    )
    revive = next(r for r in reports if r.name == "revive")
    print(
        f"Revive escalations: {revive.escalated_n}/{revive.n}  "
        f"({revive.escalated_n / revive.n:.1%})"
    )
    print()
    print("Revive strategy mix")
    for strat, count in sorted(revive.by_strategy.items(), key=lambda x: -x[1]):
        print(f"  {strat:<28} {count:>6}  ({count / revive.n:.1%})")
    print()
    print("Revive recovered by failure type")
    print(f"  {'failure_type':<24} {'n':>6} {'rate':>8} {'recovered':>14}")
    for ft, b in sorted(revive.by_failure.items()):
        rate = (b["recovered_n"] / b["n"]) if b["n"] else 0.0
        print(
            f"  {ft:<24} {b['n']:>6} {rate:>7.1%} {format_inr(b['recovered_paise']):>14}"
        )
    print()
    print("Limitation: outcomes are Agent 5's modelled rates (seeded), not bank captures.")
    print("Evidence this measures: strategy selection quality vs dumb/static policies.")


def _to_json(reports: list[SystemReport], n: int, seed: int, elapsed_ms: int) -> dict:
    return {
        "n": n,
        "seed": seed,
        "elapsed_ms": elapsed_ms,
        "simulator": "agents.outcome_evaluator.evaluate_outcome",
        "limitation": "Synthetic events + modelled success rates. Not live Razorpay GMV.",
        "systems": [
            {
                "name": r.name,
                "n": r.n,
                "at_risk_paise": r.at_risk_paise,
                "recovered_n": r.recovered_n,
                "recovered_paise": r.recovered_paise,
                "expected_paise": int(round(r.expected_paise)),
                "recovery_rate": round(r.recovery_rate, 4),
                "escalated_n": r.escalated_n,
                "uplift_paise_vs_always_retry": r.recovered_paise - reports[0].recovered_paise,
                "by_strategy": dict(r.by_strategy),
                "by_failure": dict(r.by_failure),
            }
            for r in reports
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay recovery baselines vs Revive")
    parser.add_argument("--n", type=int, default=2000, help="batch size (default 2000)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="write machine-readable report JSON",
    )
    args = parser.parse_args()

    events = generate_batch(n=args.n, seed=args.seed)
    started = time.perf_counter()
    reports = [
        _run_system(name, policy, learn, events) for name, policy, learn in SYSTEMS
    ]
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    _print_table(reports)
    print(f"Replay wall time: {elapsed_ms} ms  ({elapsed_ms / max(args.n, 1):.2f} ms/event, 3 systems)")

    payload = _to_json(reports, args.n, args.seed, elapsed_ms)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2))
        print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
