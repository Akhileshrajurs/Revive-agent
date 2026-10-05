# Runbook — Webhook → Queue → Worker → Trace

Operational path for **Razorpay-scale** recovery traffic (bursty UPI peaks). Same contracts as the demo and [`ARCHITECTURE.md`](./ARCHITECTURE.md); different topology: partitioned consumers, backpressure, and exportable traces.

This is the system you would put next to Checkout volume — not a claim that the local Docker stack already is that volume.

---

## 1. Ingest (edge)

**Trigger:** Razorpay `payment.failed` (and optionally `payment.authorized` for outcome close-out later).

| Step | Action | Fail closed? |
|------|--------|--------------|
| 1 | Receive `POST /api/v1/webhooks/razorpay` | — |
| 2 | Verify `X-Razorpay-Signature` (HMAC) | Yes → **401** |
| 3 | Reject unknown events / oversized bodies | Yes → **400** |
| 4 | Extract payment entity → `FailedPaymentIn` | Yes if amount missing/invalid |
| 5 | **Enqueue** `{ payment_id, payload_hash, received_at }` | — |
| 6 | Respond **200** quickly | Never run LangGraph or LLM here |

**Idempotency at the edge:** optional Redis `SET payment_id NX EX …` to drop obvious duplicates before the queue; Postgres unique on `payment_id` remains the source of truth.

---

## 2. Queue (transport)

| Concern | Demo | Razorpay-scale |
|---------|------|----------------|
| Broker | Redis/Celery | **Kafka** or **SQS** (FIFO per merchant optional) |
| Partition key | n/a | `merchant_id` or `hash(payment_id) % N` |
| Ordering | Best-effort | Per-partition; never require global order |
| Backpressure | Single worker | Consumer lag alerts; shed non-critical enrichment first |
| Poison messages | Manual | DLQ after N failures; page on DLQ depth |

**Message body (stable contract):**

```json
{
  "payment_id": "pay_…",
  "event": "payment.failed",
  "failed_payment": { "...FailedPaymentIn fields..." },
  "ingest": {
    "received_at": "ISO-8601",
    "payload_hash": "sha256…",
    "source": "razorpay_webhook"
  }
}
```

Do not put secrets or full card PANs in the message. Minimize PII (hash contact if only needed for DNC).

---

## 3. Worker (decision + side effects)

Consumers run the same LangGraph loop as today:

`classify → profile → plan → policy_guard → (draft | skip) → evaluate | defer_delay | escalate`

### Rules

1. **Claim** row with `INSERT … ON CONFLICT (payment_id) DO NOTHING` (or equivalent). Conflict → load existing run, ack message, exit.
2. **Rules decide strategy.** Optional LLM only for copy; hard timeout; fail-open to templates.
3. **Policy authorizes** before any outbound comms or payment action.
4. **`delay_and_retry`** → write `status=scheduled`, enqueue **delay queue** with bank-window countdown (minutes, not demo 30s), **skip** Outcome Evaluator on the hot path.
5. Append Trace steps with `latency_ms` per node; persist `agent_trace` with the run.

### Partitioned consumers

```
Topic: recovery.ingest
  Partition 0 ──► Worker pool A
  Partition 1 ──► Worker pool B
  Partition 2 ──► Worker pool C
        …                …
Delay topic: recovery.delay
  Same partition key as ingest so a payment’s cool-down lands with related state affinity (optional).
```

Scale out by adding partitions + worker replicas. Keep **exactly-once effects** via DB uniqueness, not via “exactly-once Kafka” mythology.

---

## 4. Delay path

| Demo | Scale |
|------|-------|
| `execute_delayed_retry` Celery countdown | SQS delay / Kafka + scheduler / EventBridge |
| `DELAY_RETRY_DEMO_SECONDS` (~30s) | Per-failure playbook (e.g. 2–6h bank windows) |
| Single Redis | Dedicated delay consumer group + metrics |

Worker on fire:

1. Load run; no-op if status already terminal  
2. Run outcome evaluation (or re-plan once if policy allows)  
3. Append Trace step `delayed_retry_worker`  
4. Update `strategy_performance` for learning  

---

## 5. Trace export

Every accepted recovery exposes:

`GET /api/v1/recoveries/{run_id}/trace`

**Export shape (stable):**

```json
{
  "run_id": "uuid",
  "payment_id": "pay_…",
  "steps": [
    {
      "agent": "webhook_ingest|failure_classifier|…|policy_guard|…",
      "latency_ms": 0,
      "input": {},
      "output": {},
      "reasoning": "string"
    }
  ]
}
```

### Scale export options

| Mode | Use |
|------|-----|
| Sync API | Dashboard / interview drill-down |
| Batch to object store | `s3://…/traces/dt=…/run_id.json` for audit |
| Stream | `recovery.trace` topic → warehouse (ClickHouse/BigQuery) for recovery_rate, time_to_recover, $ recovered |

**PII rule:** redact `contact` / `email` in exported Trace for shared channels; keep full Trace in locked merchant tenant storage.

---

## 6. Operator checklist

### Deploy / config

- [ ] `RAZORPAY_WEBHOOK_SECRET` set; Test vs Live secrets never mixed  
- [ ] `LLM_PROVIDER=rules` on hot path; draft optional + timeout  
- [ ] Max retries / DNC / quiet hours per merchant  
- [ ] Kill switch: `RECOVERY_ENABLED=false` drops new enqueues, drains in-flight  

### Health

- [ ] Webhook edge: 2xx rate, p99 ACK latency  
- [ ] Consumer lag per partition  
- [ ] DLQ depth = 0 (or ticketed)  
- [ ] Idempotent hit ratio (duplicates / total) — expect spikes on Razorpay redelivery  
- [ ] Trace write failures = 0 (fail closed on persist if policy requires audit)  

### Incident plays

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Webhook 401 spike | Secret rotation / wrong env | Roll secret; replay from Razorpay dashboard if needed |
| Lag climbing | Worker crash / LLM timeouts | Scale workers; confirm rules path; check draft timeouts |
| Double WhatsApp | Idempotency bypass / wrong key | Halt outbound; verify unique `payment_id`; replay audit |
| All escalations | Shared demo `customer_id` or DNC | Check `prior_failures_24h` and merchant DNC list |
| Empty Trace | Persist failure after decide | Alert; do not ack until Trace+run committed (or outbox pattern) |

---

## 7. SLO / capacity sketch (India peak)

| Metric | Stretch target |
|--------|----------------|
| Ingest burst | Multi-k events/sec regional; partition for UPI evening peaks |
| Webhook ACK p99 | ≤ 200 ms |
| Decision p99 (rules) | ≤ 100 ms worker-side |
| End-to-end schedule delay | Broker + countdown; no request-thread wait |
| Recovery explainability | 100% runs with Trace exportable within 1 s of commit |

Cost control: **classify/plan with rules first**; LLM only where copy quality pays for itself; warehouse learning offline — never sync training on the webhook path.

---

## 8. What stays identical from this repo

- `FailedPaymentIn` / `RecoveryStrategy` / policy rules  
- Agent Trace step semantics  
- Paise-integer money  
- `scripts/prove_idempotency.py` and `scripts/prove_webhook.py` as contract tests  
- Offline evals (`backend/evals/`) for strategy uplift — separate from live GMV  

What changes at scale is **where** work runs (edge vs queue vs delay consumers), not **what** a recovery means.
