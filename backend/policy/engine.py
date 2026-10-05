"""Deterministic policy guard — LLM/rules cannot authorize a blocked action.

Runs after strategy selection. Fail closed on financial/comms actions that
violate retry, DNC, quiet-hours, or permanent-failure rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from models.schemas import FailureType, RecoveryStrategy, StrategyDecision

IST = ZoneInfo("Asia/Kolkata")

# Retrying these with the same rail is almost never correct.
_PERMANENT_RAILS: frozenset[FailureType] = frozenset(
    {
        FailureType.vpa_invalid,
        FailureType.card_blocked,
    }
)

_OUTBOUND: frozenset[RecoveryStrategy] = frozenset(
    {
        RecoveryStrategy.retry_same_method,
        RecoveryStrategy.suggest_alternate_method,
        RecoveryStrategy.offer_emi,
        RecoveryStrategy.offer_partial_payment,
    }
)


@dataclass(frozen=True)
class PolicyContext:
    failure_type: FailureType
    strategy: RecoveryStrategy
    retry_count: int = 0
    prior_failures_24h: int = 0
    customer_id: str | None = None
    dnc_customer_ids: frozenset[str] = frozenset()
    max_retries: int = 3
    quiet_hours_start: int = 22  # inclusive, IST
    quiet_hours_end: int = 8  # exclusive, IST
    now: datetime | None = None  # inject for tests; default = now IST


@dataclass
class PolicyVerdict:
    allowed: bool
    strategy: RecoveryStrategy
    decision: StrategyDecision
    rule: str
    reason: str
    blocked_rules: list[str] = field(default_factory=list)

    def as_trace_output(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "rule": self.rule,
            "reason": self.reason,
            "strategy": self.strategy.value,
            "blocked_rules": self.blocked_rules,
            "overridden": self.strategy != self.decision.strategy
            or bool(self.blocked_rules),
        }


def _in_quiet_hours(now: datetime, start: int, end: int) -> bool:
    hour = now.astimezone(IST).hour
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    # wraps midnight, e.g. 22 → 8
    return hour >= start or hour < end


def _minutes_until_quiet_end(now: datetime, end: int) -> int:
    local = now.astimezone(IST)
    target = local.replace(hour=end, minute=0, second=0, microsecond=0)
    if local >= target:
        target = target + timedelta(days=1)
    return max(30, int((target - local).total_seconds() // 60))


def apply_policy(decision: StrategyDecision, ctx: PolicyContext) -> PolicyVerdict:
    """Validate/override a proposed strategy. Never invents money movement."""
    strategy = decision.strategy
    params = dict(decision.personalization_params or {})
    channel = decision.channel
    offset = int(decision.timing_offset_minutes or 0)
    blocked: list[str] = []
    rule = "PASS"
    reason = "Policy OK — strategy unchanged."

    now = ctx.now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)

    # 1) Hard retry / spam cap
    if ctx.retry_count >= ctx.max_retries or ctx.prior_failures_24h >= 3:
        if strategy != RecoveryStrategy.escalate_to_human:
            blocked.append("MAX_RETRIES_OR_REPEAT_FAILURES")
            strategy = RecoveryStrategy.escalate_to_human
            channel = "email"
            offset = 0
            params = {"reason": "max_retries_or_repeat_failures", "policy": True}
            rule = "MAX_RETRIES_OR_REPEAT_FAILURES"
            reason = (
                f"Blocked automated recovery: retry_count={ctx.retry_count}, "
                f"prior_failures_24h={ctx.prior_failures_24h}, max={ctx.max_retries}."
            )

    # 2) DNC — no outbound recovery messaging
    cid = (ctx.customer_id or "").strip()
    if cid and cid in ctx.dnc_customer_ids and strategy != RecoveryStrategy.escalate_to_human:
        blocked.append("DNC")
        strategy = RecoveryStrategy.escalate_to_human
        channel = "email"
        offset = 0
        params = {"reason": "dnc", "policy": True}
        rule = "DNC"
        reason = f"Customer `{cid}` is on DNC — escalate only, no outbound recovery."

    # 3) Permanent rail — never retry_same_method
    if (
        strategy == RecoveryStrategy.retry_same_method
        and ctx.failure_type in _PERMANENT_RAILS
    ):
        blocked.append("PERMANENT_RAIL_NO_RETRY")
        strategy = RecoveryStrategy.suggest_alternate_method
        channel = "whatsapp"
        offset = 0
        params = {
            "suggested_method": "upi" if ctx.failure_type == FailureType.card_blocked else "card",
            "policy": True,
            "reason": "permanent_rail",
        }
        rule = "PERMANENT_RAIL_NO_RETRY"
        reason = (
            f"{ctx.failure_type.value} cannot use retry_same_method — "
            "forced suggest_alternate_method."
        )

    # 4) Quiet hours — no immediate outbound; schedule cool-down instead
    if (
        strategy in _OUTBOUND
        and _in_quiet_hours(now, ctx.quiet_hours_start, ctx.quiet_hours_end)
    ):
        blocked.append("QUIET_HOURS")
        wait = _minutes_until_quiet_end(now, ctx.quiet_hours_end)
        strategy = RecoveryStrategy.delay_and_retry
        channel = "sms"
        offset = wait
        params = {"wait_hours": max(1, wait // 60), "policy": True, "reason": "quiet_hours"}
        rule = "QUIET_HOURS"
        reason = (
            f"Quiet hours IST {ctx.quiet_hours_start:02d}:00–{ctx.quiet_hours_end:02d}:00 — "
            f"deferred {wait} minutes (no immediate customer contact)."
        )

    new_decision = StrategyDecision(
        strategy=strategy,
        channel=channel,
        timing_offset_minutes=offset,
        personalization_params=params,
        reasoning=(
            decision.reasoning
            if not blocked
            else f"{decision.reasoning} | POLICY[{rule}]: {reason}"
        ),
    )
    allowed = len(blocked) == 0
    return PolicyVerdict(
        allowed=allowed,
        strategy=strategy,
        decision=new_decision,
        rule=rule if blocked else "PASS",
        reason=reason if blocked else "Policy OK — strategy unchanged.",
        blocked_rules=blocked,
    )
