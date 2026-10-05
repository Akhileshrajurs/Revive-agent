"""LangGraph recovery pipeline with real conditional branching.

Pipeline spine:
  classify → profile → plan → [branch] → comms → [branch] → evaluate | defer | escalate

Branching is LangGraph conditional edges (Agent Studio–style state machine).
Delay cool-down is linked to Celery via `defer_to_celery` (no sleep on the request path).
"""

from __future__ import annotations

import time
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agents.comms_drafter import draft_communication
from agents.customer_profiler import build_customer_profile
from agents.failure_classifier import classify_failure
from agents.outcome_evaluator import evaluate_outcome, expected_success_rate, outcome_reasoning
from agents.strategy_planner import plan_strategy
from config import get_settings
from models.schemas import (
    CustomerPaymentProfile,
    FailureClassification,
    RecoveryStrategy,
    StrategyDecision,
)
from policy.engine import PolicyContext, apply_policy

BranchName = Literal[
    "path_retry",
    "path_alternate",
    "path_emi",
    "path_partial",
    "path_delay",
    "path_escalate",
]


class RecoveryState(TypedDict, total=False):
    payment_id: str
    order_id: str | None
    customer_id: str | None
    amount_paise: int
    currency: str
    payment_method: str | None
    error_code: str | None
    error_description: str | None
    error_reason: str | None
    customer_name: str | None
    merchant_name: str | None
    prior_failures_24h: int
    payment_history: list[dict[str, Any]]
    strategy_performance: dict[str, dict[str, Any]]
    retry_count: int
    max_retries: int
    classification: dict[str, Any]
    customer_profile: dict[str, Any]
    strategy_decision: dict[str, Any]
    drafted_message: dict[str, Any]
    outcome: dict[str, Any]
    graph_branch: str
    defer_celery: bool
    agent_trace: list[dict[str, Any]]


_STRATEGY_TO_BRANCH: dict[str, BranchName] = {
    RecoveryStrategy.retry_same_method.value: "path_retry",
    RecoveryStrategy.suggest_alternate_method.value: "path_alternate",
    RecoveryStrategy.offer_emi.value: "path_emi",
    RecoveryStrategy.offer_partial_payment.value: "path_partial",
    RecoveryStrategy.delay_and_retry.value: "path_delay",
    RecoveryStrategy.escalate_to_human.value: "path_escalate",
}

_BRANCH_LABELS: dict[str, str] = {
    "path_retry": "retry_same_method",
    "path_alternate": "suggest_alternate_method",
    "path_emi": "offer_emi",
    "path_partial": "offer_partial_payment",
    "path_delay": "delay_and_retry → Celery",
    "path_escalate": "escalate_to_human",
}


def _append_trace(
    state: RecoveryState,
    agent: str,
    output: dict[str, Any],
    reasoning: str | None,
    latency_ms: int,
) -> list[dict[str, Any]]:
    trace = list(state.get("agent_trace") or [])
    trace.append(
        {
            "agent": agent,
            "status": "ok",
            "output": output,
            "reasoning": reasoning,
            "latency_ms": latency_ms,
        }
    )
    return trace


def _failure_classifier_node(state: RecoveryState) -> dict[str, Any]:
    started = time.perf_counter()
    result = classify_failure(
        error_code=state.get("error_code"),
        error_description=state.get("error_description"),
        error_reason=state.get("error_reason"),
        payment_method=state.get("payment_method"),
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "classification": result.model_dump(),
        "agent_trace": _append_trace(
            state, "failure_classifier", result.model_dump(), result.reasoning, latency_ms
        ),
    }


def _customer_profiler_node(state: RecoveryState) -> dict[str, Any]:
    started = time.perf_counter()
    profile = build_customer_profile(
        customer_id=state.get("customer_id"),
        payment_method=state.get("payment_method"),
        amount_paise=state.get("amount_paise") or 0,
        prior_failures_24h=state.get("prior_failures_24h") or 0,
        payment_history=state.get("payment_history"),
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    reasoning = (
        f"risk_tier={profile.risk_tier}; preferred={profile.preferred_method}; "
        f"window={profile.best_retry_window}; prior_failures_24h={profile.prior_failures_24h}"
    )
    return {
        "customer_profile": profile.model_dump(),
        "agent_trace": _append_trace(
            state, "customer_profiler", profile.model_dump(), reasoning, latency_ms
        ),
    }


def _strategy_planner_node(state: RecoveryState) -> dict[str, Any]:
    started = time.perf_counter()
    classification = FailureClassification.model_validate(state["classification"])
    profile = CustomerPaymentProfile.model_validate(state["customer_profile"])
    # Rules-only strategy (0 Gemini). Comms may use ≤1 Gemini call for copy.
    decision = plan_strategy(
        failure_type=classification.failure_type,
        profile=profile,
        amount_paise=state.get("amount_paise") or 0,
        payment_method=state.get("payment_method"),
        retry_count=state.get("retry_count") or 0,
        customer_name=state.get("customer_name"),
        strategy_performance=state.get("strategy_performance") or {},
        use_llm=False,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "strategy_decision": decision.model_dump(),
        "agent_trace": _append_trace(
            state, "strategy_planner", decision.model_dump(), decision.reasoning, latency_ms
        ),
    }


def _policy_guard_node(state: RecoveryState) -> dict[str, Any]:
    """Deterministic guardrails after plan — LLM/rules cannot bypass."""
    started = time.perf_counter()
    settings = get_settings()
    classification = FailureClassification.model_validate(state["classification"])
    decision = StrategyDecision.model_validate(state["strategy_decision"])
    verdict = apply_policy(
        decision,
        PolicyContext(
            failure_type=classification.failure_type,
            strategy=decision.strategy,
            retry_count=int(state.get("retry_count") or 0),
            prior_failures_24h=int(state.get("prior_failures_24h") or 0),
            customer_id=state.get("customer_id"),
            dnc_customer_ids=settings.dnc_customer_id_set,
            max_retries=int(state.get("max_retries") or settings.policy_max_retries),
            quiet_hours_start=settings.policy_quiet_hours_start,
            quiet_hours_end=settings.policy_quiet_hours_end,
        ),
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "strategy_decision": verdict.decision.model_dump(),
        "agent_trace": _append_trace(
            state,
            "policy_guard",
            verdict.as_trace_output(),
            verdict.reason,
            latency_ms,
        ),
    }


def _make_branch_node(branch: BranchName):
    """Zero-I/O branch marker — only annotates state for Trace + routing."""

    def _node(state: RecoveryState) -> dict[str, Any]:
        label = _BRANCH_LABELS[branch]
        output = {"graph_branch": branch, "strategy_label": label}
        return {
            "graph_branch": branch,
            "defer_celery": branch == "path_delay",
            "agent_trace": _append_trace(
                state,
                "graph_branch",
                output,
                f"LangGraph conditional edge selected `{branch}` ({label}).",
                0,
            ),
        }

    _node.__name__ = branch
    return _node


def _route_after_strategy(state: RecoveryState) -> BranchName:
    strategy = (state.get("strategy_decision") or {}).get("strategy") or ""
    return _STRATEGY_TO_BRANCH.get(strategy, "path_escalate")


def _comms_drafter_node(state: RecoveryState) -> dict[str, Any]:
    started = time.perf_counter()
    classification = FailureClassification.model_validate(state["classification"])
    profile = CustomerPaymentProfile.model_validate(state["customer_profile"])
    decision = StrategyDecision.model_validate(state["strategy_decision"])
    draft = draft_communication(
        customer_name=state.get("customer_name"),
        merchant_name=state.get("merchant_name"),
        amount_paise=state.get("amount_paise") or 0,
        failure_type=classification.failure_type,
        decision=decision,
        profile=profile,
        payment_id=state["payment_id"],
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "drafted_message": draft.model_dump(),
        "agent_trace": _append_trace(
            state, "comms_drafter", draft.model_dump(), draft.body, latency_ms
        ),
    }


def _route_after_comms(state: RecoveryState) -> str:
    branch = state.get("graph_branch") or ""
    if branch == "path_delay":
        return "defer_to_celery"
    if branch == "path_escalate":
        return "finalize_escalate"
    return "outcome_evaluator"


def _outcome_evaluator_node(state: RecoveryState) -> dict[str, Any]:
    started = time.perf_counter()
    classification = FailureClassification.model_validate(state["classification"])
    decision = StrategyDecision.model_validate(state["strategy_decision"])
    perf = state.get("strategy_performance") or {}
    key = f"{decision.strategy.value}|{classification.failure_type.value}"
    row = perf.get(key) or {}
    attempts = int(row.get("attempts") or 0)
    successes = int(row.get("successes") or 0)
    hist_rate = (successes / attempts) if attempts else None

    rate = expected_success_rate(
        decision.strategy,
        classification.failure_type,
        historical_rate=hist_rate,
        historical_attempts=attempts,
    )
    outcome = evaluate_outcome(
        payment_id=state["payment_id"],
        strategy=decision.strategy,
        failure_type=classification.failure_type,
        payment_method=state.get("payment_method"),
        suggested_method=(decision.personalization_params or {}).get("suggested_method"),
        historical_rate=hist_rate,
        historical_attempts=attempts,
    )
    payload = outcome.model_dump()
    payload["modelled_success_rate"] = round(rate, 4)
    reasoning = outcome_reasoning(outcome, rate)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "outcome": payload,
        "agent_trace": _append_trace(state, "outcome_evaluator", payload, reasoning, latency_ms),
    }


def _defer_to_celery_node(state: RecoveryState) -> dict[str, Any]:
    """Mark deferred — Celery owns the clock. No sleep. No outcome simulation here."""
    decision = StrategyDecision.model_validate(state["strategy_decision"])
    offset = int(decision.timing_offset_minutes or 0)
    payload = {
        "success": False,
        "deferred": True,
        "defer_celery": True,
        "strategy_used": decision.strategy.value,
        "method_used": state.get("payment_method"),
        "timing_offset_minutes": offset,
        "note": "Graph branched to defer_to_celery; worker will evaluate after cool-down.",
    }
    return {
        "outcome": payload,
        "defer_celery": True,
        "agent_trace": _append_trace(
            state,
            "defer_to_celery",
            payload,
            "Skipped Outcome Evaluator on request path — Celery linked for delay_and_retry.",
            0,
        ),
    }


def _finalize_escalate_node(state: RecoveryState) -> dict[str, Any]:
    payload = {
        "success": False,
        "escalated": True,
        "strategy_used": RecoveryStrategy.escalate_to_human.value,
        "method_used": state.get("payment_method"),
        "note": "Human escalation — no automated recovery score.",
    }
    return {
        "outcome": payload,
        "defer_celery": False,
        "agent_trace": _append_trace(
            state,
            "finalize_escalate",
            payload,
            "Graph branched to escalate — skipped automated outcome scoring.",
            0,
        ),
    }


def build_recovery_graph():
    graph = StateGraph(RecoveryState)

    graph.add_node("failure_classifier", _failure_classifier_node)
    graph.add_node("customer_profiler", _customer_profiler_node)
    graph.add_node("strategy_planner", _strategy_planner_node)
    graph.add_node("policy_guard", _policy_guard_node)
    for branch in _STRATEGY_TO_BRANCH.values():
        graph.add_node(branch, _make_branch_node(branch))
    graph.add_node("comms_drafter", _comms_drafter_node)
    graph.add_node("outcome_evaluator", _outcome_evaluator_node)
    graph.add_node("defer_to_celery", _defer_to_celery_node)
    graph.add_node("finalize_escalate", _finalize_escalate_node)

    graph.set_entry_point("failure_classifier")
    graph.add_edge("failure_classifier", "customer_profiler")
    graph.add_edge("customer_profiler", "strategy_planner")
    graph.add_edge("strategy_planner", "policy_guard")

    graph.add_conditional_edges(
        "policy_guard",
        _route_after_strategy,
        {
            "path_retry": "path_retry",
            "path_alternate": "path_alternate",
            "path_emi": "path_emi",
            "path_partial": "path_partial",
            "path_delay": "path_delay",
            "path_escalate": "path_escalate",
        },
    )

    for branch in _STRATEGY_TO_BRANCH.values():
        graph.add_edge(branch, "comms_drafter")

    graph.add_conditional_edges(
        "comms_drafter",
        _route_after_comms,
        {
            "outcome_evaluator": "outcome_evaluator",
            "defer_to_celery": "defer_to_celery",
            "finalize_escalate": "finalize_escalate",
        },
    )

    graph.add_edge("outcome_evaluator", END)
    graph.add_edge("defer_to_celery", END)
    graph.add_edge("finalize_escalate", END)

    return graph.compile()


recovery_graph = build_recovery_graph()


def run_recovery_pipeline(payload: dict[str, Any]) -> RecoveryState:
    initial: RecoveryState = {
        "payment_id": payload["payment_id"],
        "order_id": payload.get("order_id"),
        "customer_id": payload.get("customer_id"),
        "amount_paise": payload["amount_paise"],
        "currency": payload.get("currency") or "INR",
        "payment_method": payload.get("method"),
        "error_code": payload.get("error_code"),
        "error_description": payload.get("error_description"),
        "error_reason": payload.get("error_reason"),
        "customer_name": payload.get("customer_name"),
        "merchant_name": payload.get("merchant_name"),
        "prior_failures_24h": int(payload.get("prior_failures_24h") or 0),
        "payment_history": payload.get("payment_history") or [],
        "strategy_performance": payload.get("strategy_performance") or {},
        "retry_count": int(payload.get("retry_count") or 0),
        "max_retries": 3,
        "defer_celery": False,
        "agent_trace": [],
    }
    return recovery_graph.invoke(initial)


def run_classification(payload: dict[str, Any]) -> RecoveryState:
    return run_recovery_pipeline(payload)
