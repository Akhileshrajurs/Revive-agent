#!/usr/bin/env python3
"""Prove duplicate payment_id POSTs create one RecoveryRun.

Requires API up (local Docker or Render).

  python3 scripts/prove_idempotency.py
  python3 scripts/prove_idempotency.py http://localhost:9000
"""

from __future__ import annotations

import sys
import uuid

import httpx


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"
    payment_id = f"pay_idem_{uuid.uuid4().hex[:12]}"
    body = {
        "payment_id": payment_id,
        "order_id": "order_idem_demo",
        "customer_id": "cust_idem_demo",
        "amount_paise": 199900,
        "method": "upi",
        "error_code": "GATEWAY_ERROR",
        "error_description": "Bank timed out while authorizing UPI payment",
        "error_reason": "bank_timeout",
        "customer_name": "Idem",
        "merchant_name": "Acme",
    }

    print()
    print("IDEMPOTENCY PROOF")
    print("─" * 56)
    print(f"API: {base}")
    print(f"payment_id: {payment_id}")
    print("POSTing same payload 5 times…")

    run_ids: list[str] = []
    flags: list[bool] = []
    with httpx.Client(timeout=30.0) as client:
        for i in range(5):
            r = client.post(f"{base}/api/v1/recoveries", json=body)
            r.raise_for_status()
            data = r.json()
            run_ids.append(str(data["run_id"]))
            flags.append(bool(data.get("idempotent_replay")))
            print(
                f"  #{i + 1} run_id={data['run_id']} "
                f"idempotent_replay={data.get('idempotent_replay')} "
                f"status={data.get('status')}"
            )

    unique = set(run_ids)
    ok = len(unique) == 1 and flags[0] is False and all(flags[1:])
    print("─" * 56)
    print(f"Unique run_ids: {len(unique)}  (want 1)")
    print(f"First fresh / rest replay: first={flags[0]} rest={flags[1:]}  (want False + all True)")
    print(f"Result: {'PASS' if ok else 'FAIL'}")
    print()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
