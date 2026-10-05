"""Razorpay webhook signature verify + payment.failed → FailedPaymentIn."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException
from models.schemas import FailedPaymentIn


def verify_razorpay_signature(*, body: bytes, signature: str | None, secret: str) -> None:
    """Fail closed: missing/invalid HMAC → 401."""
    if not secret:
        raise HTTPException(status_code=500, detail="RAZORPAY_WEBHOOK_SECRET is not configured")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Razorpay-Signature")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid Razorpay webhook signature")


def parse_webhook_event(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")
    return payload


def payment_entity_to_failed_payment(payment: dict[str, Any], *, payment_id_fallback: str = "") -> FailedPaymentIn:
    """Map Razorpay payment entity → typed inbound event. Never invent money."""
    payment_id = str(payment.get("id") or payment_id_fallback or "").strip()
    if not payment_id:
        raise HTTPException(status_code=400, detail="Payment entity missing id")

    raw_amount = payment.get("amount")
    try:
        amount_paise = int(raw_amount)
    except (TypeError, ValueError):
        amount_paise = 0
    if amount_paise < 1:
        raise HTTPException(
            status_code=400,
            detail=f"Payment {payment_id} has invalid amount_paise={raw_amount!r} (refuse to invent money)",
        )

    notes = payment.get("notes") if isinstance(payment.get("notes"), dict) else {}
    return FailedPaymentIn(
        payment_id=payment_id,
        order_id=payment.get("order_id"),
        customer_id=payment.get("customer_id"),
        amount_paise=amount_paise,
        currency=payment.get("currency") or "INR",
        method=payment.get("method"),
        error_code=payment.get("error_code"),
        error_description=payment.get("error_description"),
        error_source=payment.get("error_source"),
        error_step=payment.get("error_step"),
        error_reason=payment.get("error_reason"),
        customer_name=(notes or {}).get("customer_name") or "Customer",
        merchant_name=(notes or {}).get("merchant_name") or "Merchant",
        email=payment.get("email"),
        contact=payment.get("contact"),
    )


def extract_payment_failed_entity(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return payment entity for payment.failed; None if not that event."""
    event = payload.get("event")
    if event != "payment.failed":
        return None
    entity = (
        payload.get("payload", {})
        .get("payment", {})
        .get("entity")
    )
    if not isinstance(entity, dict):
        raise HTTPException(status_code=400, detail="payment.failed webhook missing payment.entity")
    return entity
