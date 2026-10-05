# Architecture

One-page view of ReviveAgent at **merchant scale**: same contracts as the demo, with the async boundaries that keep webhook latency and recovery decisions honest.

Amounts are always **paise (int)**. Strategy is never authorized by an LLM.

---

## Contracts that do not change with scale

| Contract | Meaning |
|----------|---------|
| `FailedPaymentIn` | Razorpay-shaped failure fields; `amount_paise ≥ 1`; never invent money |
| `RecoveryStrategy` | Typed enum (`retry_same_method`, `delay_and_retry`, …) |
| Idempotency key | `payment_id` unique → one `RecoveryRun`; replays return `idempotent_replay` |
| Policy | Deterministic authorize/override (retries, DNC, quiet hours IST, permanent rail) |
| Agent Trace | Ordered steps: agent, input/output, `latency_ms`, reasoning |
| Delay | Cool-down is a **queue countdown**, never `sleep` on the request path |

Demo stack today: FastAPI + Postgres + Redis/Celery. Merchant-scale swaps the broker for SQS/Kafka and keeps these contracts.

---

## Sequence (happy path + delay)

```mermaid
sequenceDiagram
    autonumber
    participant RZ as Razorpay
    participant WH as Webhook API
    participant Q as Ingest queue<br/>(demo: sync / scale: SQS)
    participant AG as LangGraph workers
    participant PG as Postgres
    participant RD as Redis/Celery
    participant TR as Trace API

    RZ->>WH: POST payment.failed + HMAC
    WH->>WH: Verify signature (401 if bad)
    WH->>PG: Lookup payment_id
    alt already exists
        WH-->>RZ: 200 idempotent_replay
    else new failure
        WH->>Q: Enqueue recovery job
        Note over WH,Q: Merchant-scale: ack webhook fast;<br/>do not run LLM on this thread
        WH-->>RZ: 200 accepted
        Q->>AG: Consume job
        AG->>AG: classify → profile → plan → policy_guard
        AG->>AG: draft (templates; optional LLM off hot path)
        alt evaluate / escalate
            AG->>PG: Persist run + agent_trace + outcome
        else delay_and_retry
            AG->>PG: Persist status=scheduled
            AG->>RD: Countdown task (bank cool-down)
            RD->>AG: Worker fires later
            AG->>PG: Append delayed_retry Trace step + outcome
        end
    end
    TR->>PG: GET /recoveries/{run_id}/trace
    TR-->>TR: Exportable Agent Trace
```

**Branch rule:** `policy_guard` runs before any outbound side effect. Planner *proposes*; policy *authorizes*; Trace *explains*.

---

## Component map

```
                    ┌──────────────┐
  payment.failed ──►│ Webhook edge │── HMAC, clock skew, body size limits
                    └──────┬───────┘
                           │ enqueue (payment_id)
                           ▼
                    ┌──────────────┐
                    │ Recovery Q   │── at-least-once delivery
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Worker A     Worker B     Worker C     (horizontal scale)
              │            │            │
              └────────────┼────────────┘
                           ▼
              LangGraph: Perceive → Plan → Policy → Act/Defer
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          Postgres      Delay Q     Trace store
         (truth)     (Celery/SQS)  (agent_trace JSON)
```

---

## SLO notes (merchant-scale targets)

These are **design targets** for ~10³–10⁵ recoveries/day — not measured production SLOs on the local Docker stack.

| SLI | Target | Why |
|-----|--------|-----|
| Webhook ACK latency (p99) | **≤ 200 ms** | Razorpay retries on slow/failed delivery; HMAC + enqueue only |
| Decision latency rules path (p99) | **≤ 50 ms** in-process | Default `LLM_PROVIDER=rules`; no network LLM on strategy |
| Decision latency with optional draft (p99) | **≤ 3 s** hard timeout | Draft fail-open to templates; never block forever |
| Idempotent duplicate rate | **100%** safe | Same `payment_id` → no second message / second delay task |
| Trace completeness | **100%** of accepted runs | Every node writes a Trace step (incl. `webhook_ingest`, `policy_guard`) |
| Delay accuracy | Countdown ± broker skew | Bank cool-down owned by worker queue, not API thread |
| Money integrity | **0** invented amounts | Reject missing/invalid `amount`; paise int only |

### Latency budget (single recovery, rules path)

| Stage | Budget |
|-------|--------|
| HMAC + parse | ~5–15 ms |
| Idempotency lookup | ~5–20 ms |
| Graph (classify → policy → draft template) | ~10–40 ms |
| Persist + schedule | ~10–30 ms |
| **Total in-process** | **well under 200 ms** when webhook only enqueues |

LLM on the hot path blows this budget — that is why strategy stays rules-only.

### Failure modes to design for

| Mode | Behavior |
|------|----------|
| Duplicate webhook | Return existing run; `idempotent_replay=true` |
| Worker crash mid-graph | At-least-once redelivery; effects gated by `payment_id` uniqueness |
| Policy deny / quiet hours | Override strategy; Trace shows `blocked_rules` |
| Draft timeout / 429 | Template body; strategy unchanged |
| Delay worker late | Trace step still records execution time; no double-eval if status moved on |

---

## What this repo proves today vs what merchant-scale adds

| Today (demo) | Merchant-scale add-on |
|--------------|----------------------|
| Webhook may run graph in-request (Test Mode) | Webhook → queue → workers only |
| Celery on Redis, demo-short countdown | SQS/Kafka delay queues; minute-scale bank windows |
| Single Postgres | Same schema; read replicas for Trace/dashboard |
| Single merchant mental model | Per-merchant policy config (retries, DNC lists, quiet hours) |

Contracts, Trace shape, and policy semantics stay identical — only the transport and tenancy grow.

See also: [`RUNBOOK.md`](./RUNBOOK.md) for the Razorpay-scale path (partitions, backpressure, Trace export).
