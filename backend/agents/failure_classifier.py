"""Agent 1 — Failure Classifier.

Maps Razorpay error_code / error_reason / description → typed FailureType.
Rule-based first (deterministic, demo-reliable). LLM optional later.
"""

from __future__ import annotations

import time
from typing import Any

from models.schemas import FailureClassification, FailureType

# Razorpay-ish reasons / substrings → our taxonomy
_REASON_MAP: dict[str, FailureType] = {
    "insufficient_funds": FailureType.insufficient_funds,
    "payment_failed_due_to_insufficient_funds": FailureType.insufficient_funds,
    "incorrect_otp": FailureType.wrong_otp,
    "wrong_otp": FailureType.wrong_otp,
    "otp_mismatch": FailureType.wrong_otp,
    "bank_timeout": FailureType.bank_timeout,
    "gateway_timeout": FailureType.bank_timeout,
    "server_error": FailureType.bank_timeout,
    "card_blocked": FailureType.card_blocked,
    "card_declined": FailureType.card_blocked,
    "do_not_honour": FailureType.card_blocked,
    "incorrect_mpin": FailureType.upi_mpin_incorrect,
    "upi_mpin": FailureType.upi_mpin_incorrect,
    "mpin": FailureType.upi_mpin_incorrect,
    "netbanking": FailureType.netbanking_down,
    "bank_not_available": FailureType.netbanking_down,
    "invalid_vpa": FailureType.vpa_invalid,
    "vpa": FailureType.vpa_invalid,
    "3ds": FailureType.threeds_failure,
    "authentication_failed": FailureType.threeds_failure,
    "authentication": FailureType.threeds_failure,
}

_DESC_HINTS: list[tuple[str, FailureType]] = [
    ("insufficient", FailureType.insufficient_funds),
    ("fund", FailureType.insufficient_funds),
    ("otp", FailureType.wrong_otp),
    ("timeout", FailureType.bank_timeout),
    ("timed out", FailureType.bank_timeout),
    ("blocked", FailureType.card_blocked),
    ("declined", FailureType.card_blocked),
    ("mpin", FailureType.upi_mpin_incorrect),
    ("netbanking", FailureType.netbanking_down),
    ("bank is down", FailureType.netbanking_down),
    ("vpa", FailureType.vpa_invalid),
    ("upi id", FailureType.vpa_invalid),
    ("3d secure", FailureType.threeds_failure),
    ("3ds", FailureType.threeds_failure),
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_").replace("-", "_")


def classify_failure(
    *,
    error_code: str | None,
    error_description: str | None,
    error_reason: str | None = None,
    payment_method: str | None = None,
) -> FailureClassification:
    started = time.perf_counter()
    reason = _normalize(error_reason)
    code = _normalize(error_code)
    desc = (error_description or "").lower()

    failure_type = FailureType.unknown
    confidence = 0.4
    reasoning_parts: list[str] = []

    if reason and reason in _REASON_MAP:
        failure_type = _REASON_MAP[reason]
        confidence = 0.95
        reasoning_parts.append(f"Matched error_reason='{error_reason}' → {failure_type.value}")
    else:
        for key, mapped in _REASON_MAP.items():
            if key in reason or key in code:
                failure_type = mapped
                confidence = 0.85
                reasoning_parts.append(f"Matched key '{key}' in code/reason → {mapped.value}")
                break

    if failure_type == FailureType.unknown and desc:
        for hint, mapped in _DESC_HINTS:
            if hint in desc:
                failure_type = mapped
                confidence = 0.75
                reasoning_parts.append(f"Description hint '{hint}' → {mapped.value}")
                break

    if failure_type == FailureType.unknown:
        reasoning_parts.append(
            "No strong match on Razorpay error fields; defaulting to unknown for safe escalation path."
        )
        confidence = 0.35

    latency_ms = int((time.perf_counter() - started) * 1000)
    reasoning_parts.append(f"classifier_latency_ms={latency_ms}")

    return FailureClassification(
        failure_type=failure_type,
        confidence=confidence,
        raw_error_code=error_code or error_reason,
        payment_method=payment_method,
        reasoning=" | ".join(reasoning_parts),
    )


def classify_from_payment_payload(payment: dict[str, Any]) -> FailureClassification:
    return classify_failure(
        error_code=payment.get("error_code"),
        error_description=payment.get("error_description"),
        error_reason=payment.get("error_reason"),
        payment_method=payment.get("method"),
    )
