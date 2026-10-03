"""Razorpay client with real Test Mode + mock fallback."""

from __future__ import annotations

from typing import Any, Protocol

import httpx
import structlog

from config import get_settings

log = structlog.get_logger()


class RazorpayClientProtocol(Protocol):
    def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...
    def list_payments(self, count: int = 20) -> list[dict[str, Any]]: ...


class MockRazorpayClient:
    """Used when keys are missing — returns realistic failed payment shapes."""

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return {
            "id": payment_id,
            "entity": "payment",
            "amount": 249900,
            "currency": "INR",
            "status": "failed",
            "method": "upi",
            "order_id": "order_mock_001",
            "customer_id": "cust_mock_001",
            "error_code": "BAD_REQUEST_ERROR",
            "error_description": "Payment failed due to bank timeout",
            "error_source": "bank",
            "error_step": "payment_authorization",
            "error_reason": "bank_timeout",
            "email": "priya@example.com",
            "contact": "+919876543210",
            "notes": {"customer_name": "Priya"},
        }

    def list_payments(self, count: int = 20) -> list[dict[str, Any]]:
        return [self.fetch_payment(f"pay_mock_{i}") for i in range(min(count, 5))]


class RazorpayClient:
    """Thin wrapper around Razorpay Test Mode REST API."""

    BASE = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str) -> None:
        self._auth = (key_id, key_secret)

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{self.BASE}/payments/{payment_id}", auth=self._auth)
            resp.raise_for_status()
            return resp.json()

    def list_payments(self, count: int = 20) -> list[dict[str, Any]]:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{self.BASE}/payments",
                params={"count": count},
                auth=self._auth,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])


def get_razorpay_client() -> RazorpayClientProtocol:
    settings = get_settings()
    if settings.razorpay_configured:
        log.info("razorpay_client", mode="live_test_api", key_id_prefix=settings.razorpay_key_id[:12])
        return RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
    log.warning("razorpay_client", mode="mock", reason="RAZORPAY_KEY_ID/SECRET not set")
    return MockRazorpayClient()
