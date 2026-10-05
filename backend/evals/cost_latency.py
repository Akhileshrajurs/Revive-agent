#!/usr/bin/env python3
"""Cost + latency evidence for the recovery decision path.

Default demo path uses LLM_PROVIDER=rules → **₹0 LLM cost**, **0 Gemini calls**.
We still measure wall-clock for N offline recoveries (production planner + policy +
outcome simulator — no HTTP/DB).

Hypothetical Gemini draft cost is labelled clearly: not billed unless LLM_DRAFT_ENABLED.

Usage:
  docker compose run --rm --no-deps api python -m evals.cost_latency --n 200 --seed 42
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import get_settings  # noqa: E402
from evals.baselines import revive_rules  # noqa: E402
from evals.dataset import generate_batch  # noqa: E402
from agents.outcome_evaluator import evaluate_outcome, expected_success_rate  # noqa: E402
from models.schemas import FailureType, RecoveryStrategy  # noqa: E402

# Published Gemini Flash free/paid ballpark for README honesty — not a live invoice.
# Used only when illustrating "if we had kept 2 LLM calls / recovery".
_INR_PER_GEMINI_JSON_CALL = 0.05  # ₹ — illustrative, not Google billing


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    settings = get_settings()
    events = generate_batch(n=args.n, seed=args.seed)
    latencies_ms: list[float] = []
    perf: dict[str, dict] = {}

    for ev in events:
        ft = FailureType(ev.failure_type)
        t0 = time.perf_counter()
        decision = revive_rules(
            failure_type=ft,
            amount_paise=ev.amount_paise,
            method=ev.method,
            customer_id=ev.customer_id,
            prior_failures_24h=ev.prior_failures_24h,
            retry_count=ev.retry_count,
            strategy_performance=perf,
        )
        hist = perf.get(f"{decision.strategy.value}|{ft.value}") or {}
        attempts = int(hist.get("attempts") or 0)
        successes = int(hist.get("successes") or 0)
        hist_rate = (successes / attempts) if attempts else None
        rate = expected_success_rate(
            decision.strategy, ft, historical_rate=hist_rate, historical_attempts=attempts
        )
        outcome = evaluate_outcome(
            payment_id=ev.payment_id,
            strategy=decision.strategy,
            failure_type=ft,
            payment_method=ev.method,
            suggested_method=(decision.personalization_params or {}).get("suggested_method"),
            historical_rate=hist_rate,
            historical_attempts=attempts,
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if decision.strategy != RecoveryStrategy.escalate_to_human:
            key = f"{decision.strategy.value}|{ft.value}"
            row = perf.setdefault(key, {"attempts": 0, "successes": 0})
            row["attempts"] += 1
            if outcome.success:
                row["successes"] += 1
        _ = rate

    latencies_ms.sort()
    llm_enabled = (
        settings.llm_provider == "gemini"
        and settings.gemini_configured
        and settings.llm_draft_enabled
    )
    calls_per = 1 if llm_enabled else 0
    # Actual path cost (demo default = 0)
    cost_per = calls_per * _INR_PER_GEMINI_JSON_CALL
    # Legacy dual-call architecture we removed (strategy enrich + draft)
    legacy_calls = 2
    legacy_cost = legacy_calls * _INR_PER_GEMINI_JSON_CALL

    print()
    print("COST + LATENCY  (offline decision path — no HTTP/DB/Gemini network)")
    print("─" * 64)
    print(f"N={args.n}  seed={args.seed}")
    print(f"llm_provider={settings.llm_provider}  llm_draft_enabled={settings.llm_draft_enabled}")
    print(f"gemini_calls_per_recovery (this config) = {calls_per}")
    print()
    print("Latency (plan + policy + outcome sim)")
    print(f"  mean   {statistics.mean(latencies_ms):8.3f} ms")
    print(f"  p50    {_percentile(latencies_ms, 50):8.3f} ms")
    print(f"  p95    {_percentile(latencies_ms, 95):8.3f} ms")
    print(f"  p99    {_percentile(latencies_ms, 99):8.3f} ms")
    print()
    print("LLM cost (illustrative ₹ / recovery)")
    print(f"  this config          ₹{cost_per:.2f}   ({calls_per} call(s))")
    print(f"  legacy (2 Gemini)    ₹{legacy_cost:.2f}   (strategy enrich + draft)")
    if legacy_cost > 0:
        saved = (legacy_cost - cost_per) / legacy_cost * 100.0
        print(f"  reduction vs legacy  {saved:.0f}%")
    print()
    print(f"Batch LLM cost @ N={args.n}: this ₹{cost_per * args.n:.2f}  |  legacy ₹{legacy_cost * args.n:.2f}")
    print()
    print("Notes")
    print("  • Default hire-demo path is rules-only → ₹0 Gemini, 0 network LLM RTT.")
    print("  • ₹/call is illustrative for README math — not a Google invoice.")
    print("  • Request-path never sleeps on 429; drafts fail open to templates.")
    print()


if __name__ == "__main__":
    main()
