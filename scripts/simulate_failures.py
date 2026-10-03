#!/usr/bin/env python3
"""Seed sample failed-payment payloads for local smoke tests (no live charge)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

SAMPLES = [
    {
        "payment_id": "pay_sim_insufficient_01",
        "order_id": "order_sim_01",
        "customer_id": "cust_priya",
        "amount_paise": 249900,
        "method": "card",
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Payment failed due to insufficient funds",
        "error_reason": "insufficient_funds",
        "customer_name": "Priya",
        "merchant_name": "Acme Store",
    },
    {
        "payment_id": "pay_sim_timeout_02",
        "order_id": "order_sim_02",
        "customer_id": "cust_arjun",
        "amount_paise": 99900,
        "method": "upi",
        "error_code": "GATEWAY_ERROR",
        "error_description": "Bank timed out while authorizing UPI payment",
        "error_reason": "bank_timeout",
        "customer_name": "Arjun",
        "merchant_name": "Acme Store",
    },
    {
        "payment_id": "pay_sim_otp_03",
        "order_id": "order_sim_03",
        "customer_id": "cust_neha",
        "amount_paise": 150000,
        "method": "card",
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Incorrect OTP entered by customer",
        "error_reason": "incorrect_otp",
        "customer_name": "Neha",
        "merchant_name": "Acme Store",
    },
    {
        "payment_id": "pay_sim_blocked_04",
        "order_id": "order_sim_04",
        "customer_id": "cust_vikram",
        "amount_paise": 459900,
        "method": "card",
        "error_code": "BAD_REQUEST_ERROR",
        "error_description": "Card blocked by issuing bank",
        "error_reason": "card_blocked",
        "customer_name": "Vikram",
        "merchant_name": "Acme Store",
    },
    {
        "payment_id": "pay_sim_netbanking_05",
        "order_id": "order_sim_05",
        "customer_id": "cust_meera",
        "amount_paise": 320000,
        "method": "netbanking",
        "error_code": "GATEWAY_ERROR",
        "error_description": "Netbanking is temporarily unavailable at the bank",
        "error_reason": "bank_not_available",
        "customer_name": "Meera",
        "merchant_name": "Acme Store",
    },
]


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"
    out = []
    with httpx.Client(timeout=90.0) as client:
        for sample in SAMPLES:
            r = client.post(f"{base}/api/v1/recoveries", json=sample)
            r.raise_for_status()
            data = r.json()
            out.append(data)
            strategy = (data.get("strategy_decision") or {}).get("strategy")
            outcome = data.get("outcome") or {}
            print(
                f"OK {data['payment_id']} → {data['classification']['failure_type']} "
                f"| strategy={strategy} | recovered={outcome.get('success')} "
                f"| status={data['status']} | run_id={data['run_id']}"
            )
            draft = (data.get("drafted_message") or {}).get("body")
            if draft:
                print(f"   draft: {draft[:120]}...")
    Path("/tmp/revive_agent_seed.json").write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(out)} results")


if __name__ == "__main__":
    main()
