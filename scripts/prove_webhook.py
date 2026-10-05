#!/usr/bin/env python3
"""Local proof for Razorpay webhook HMAC + payment.failed ingest.

Usage (API up, RAZORPAY_WEBHOOK_SECRET set in .env / Compose):

  python3 scripts/prove_webhook.py
  python3 scripts/prove_webhook.py http://localhost:9000 my_webhook_secret
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

# Load secret from repo .env if present (no dependency on dotenv)
def _secret_from_dotenv() -> str:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        if line.startswith("RAZORPAY_WEBHOOK_SECRET="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"
    secret = sys.argv[2] if len(sys.argv) > 2 else (
        os.getenv("RAZORPAY_WEBHOOK_SECRET") or _secret_from_dotenv()
    )
    if not secret:
        print("FAIL: set RAZORPAY_WEBHOOK_SECRET in .env or pass as argv[2]")
        return 1

    payment_id = f"pay_wh_{uuid.uuid4().hex[:12]}"
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 249900,
                    "currency": "INR",
                    "status": "failed",
                    "method": "upi",
                    "order_id": "order_wh_demo",
                    "customer_id": "cust_wh_demo",
                    "error_code": "GATEWAY_ERROR",
                    "error_description": "Bank timed out while authorizing UPI payment",
                    "error_reason": "bank_timeout",
                    "email": "demo@example.com",
                    "contact": "+919999999999",
                    "notes": {"customer_name": "Webhook Demo"},
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    good_sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    print()
    print("WEBHOOK PROOF")
    print("─" * 56)
    print(f"API: {base}")
    print(f"payment_id: {payment_id}")

    with httpx.Client(timeout=30.0) as client:
        bad = client.post(
            f"{base}/api/v1/webhooks/razorpay",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "deadbeef",
            },
        )
        print(f"  bad signature → {bad.status_code} (want 401)")

        ok = client.post(
            f"{base}/api/v1/webhooks/razorpay",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": good_sig,
            },
        )
        print(f"  payment.failed → {ok.status_code}")
        data = ok.json() if ok.status_code == 200 else {}
        print(f"  run_id={data.get('run_id')} idempotent={data.get('idempotent_replay')}")

        again = client.post(
            f"{base}/api/v1/webhooks/razorpay",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": good_sig,
            },
        )
        data2 = again.json() if again.status_code == 200 else {}
        print(f"  duplicate → run_id={data2.get('run_id')} idempotent={data2.get('idempotent_replay')}")

    passed = (
        bad.status_code == 401
        and ok.status_code == 200
        and again.status_code == 200
        and data.get("run_id")
        and data.get("run_id") == data2.get("run_id")
        and data.get("idempotent_replay") is False
        and data2.get("idempotent_replay") is True
    )
    print("─" * 56)
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    print()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
