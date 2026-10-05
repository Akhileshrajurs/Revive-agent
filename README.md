# ReviveAgent

**An event-driven multi-agent system for recovering failed Razorpay payments.**

Given a `payment.failed` event (webhook or API), ReviveAgent classifies the failure, profiles the customer, selects a typed recovery strategy, runs that proposal through a deterministic **policy guard**, drafts customer copy, and either evaluates the outcome, schedules a Celery cool-down, or escalates to a human — with a full **Agent Trace** on every run.

> **Prototype scope.** Built as a Razorpay AI Builder / revenue-recovery demo. Amounts are always **paise (int)**. Offline money tables use a **seeded outcome simulator** (Agent 5 modelled rates) — not live bank captures or production GMV. Live proof of ingest is Razorpay **Test Mode** webhooks. See [Limitations](#limitations--prototype-scope) and [What broke](#what-broke-and-how-we-got-out).

**Live:** [Dashboard (Vercel)](https://revive-agent-ecru.vercel.app) · [API health (Render)](https://revive-backend-kenj.onrender.com/health) · OpenAPI `/docs`

---

## Contents

[The problem](#the-problem) · [Why this is not “LLM + eval”](#why-this-is-not-llm--eval) · [Key capabilities](#key-capabilities) · [Architecture](#architecture) · [Measured results](#measured-results) · [What broke](#what-broke-and-how-we-got-out) · [Tech stack](#tech-stack) · [API](#api) · [Local setup](#local-setup) · [Project structure](#project-structure) · [Limitations](#limitations--prototype-scope)

---

## The problem

Payment failure recovery in India is still largely **manual**: bulk SMS, no personalization, no feedback loop, no audit trail of *why* a merchant retried UPI vs offered EMI vs waited for the bank.

A thin “call Gemini with the error string” demo fails production scrutiny for the same reasons fraud wrappers fail:

1. **No measurable baseline** — you can’t show uplift vs always-retry or a static playbook  
2. **LLM on the money path** — free-tier 429s and multi-second hangs on webhook/API latency budgets  
3. **No authorization layer** — the model can propose infinite retries at 2am to a DNC customer  
4. **No idempotency** — Razorpay will redeliver `payment.failed`; naive systems double-act  

ReviveAgent separates concerns the way a payments engineer would: **rules decide strategy → policy authorizes → optional LLM drafts copy → Celery owns time → Trace explains everything**.

---

## Why this is not “LLM + eval”

| Toy system | ReviveAgent |
|------------|-------------|
| One prompt → free-text “retry UPI” | Typed `RecoveryStrategy` enum + structured Trace |
| LLM chooses the money action | **Rules + learning** choose; LLM never authorizes |
| Notebook metrics only | Offline evals **and** live Test Mode webhook ingest |
| Sync `sleep()` for “wait and retry” | Celery delay queue; **zero sleep** on request path |
| Duplicate webhook = duplicate SMS | Unique `payment_id` + `idempotent_replay` |
| Black-box success | Agent Trace: every node, latency_ms, reasoning, policy rule |

**Where this project is stronger than a simple eval harness:** it is a **closed recovery loop with side effects and guardrails** — ingest → decide → authorize → act/schedule → learn — that you can attack (policy proofs, idempotency proofs) and run against real Razorpay Test failures.

**Where a classical ML risk repo may still be ahead:** LightGBM/SHAP held-out precision on fraud labels. That is a different Razorpay track. We do not pretend offline recovery rates are live GMV.

---

## Key capabilities

- **Razorpay `payment.failed` webhook** — HMAC (`X-Razorpay-Signature`) verified; invalid signature → 401; amount never invented  
- **Idempotent recovery starts** — same `payment_id` → one `RecoveryRun`, no second Celery task  
- **LangGraph state machine** — classify → profile → plan → **policy_guard** → branch → draft → evaluate | defer_celery | escalate  
- **Deterministic policy engine** — max retries, DNC, quiet hours (IST), permanent-rail no same-method retry  
- **Learning loop** — Agent 5 outcomes feed `strategy_performance`; Agent 3 may override when evidence is strong  
- **Cost-aware LLM use** — default `LLM_PROVIDER=rules` → **0 Gemini calls**; optional draft with **2.5s hard timeout**, fail-open to templates  
- **Agent Trace** — every node’s I/O + reasoning (including `webhook_ingest` and `policy_guard`)  
- **Offline evidence suite** — replay, ablation, policy attacks, cost/latency (`backend/evals/`)  
- **Hire dashboard** — Live feed, funnel, Trace, strategy performance (Vercel → Render)

---

## Architecture

```
Razorpay Test Mode
   payment.failed
        │
        ▼
HMAC verify ──401──► reject
        │
        ▼
idempotency (payment_id unique)
        │
        ▼
┌───────────────────┐
│ Failure Classifier│  rules (Razorpay error → taxonomy)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Customer Profiler │  rules (risk, priors, method prefs)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Strategy Planner  │  rules + strategy_performance learning
└─────────┬─────────┘     ← no LLM on this path
          ▼
┌───────────────────┐
│   Policy Guard    │  authorize / override (never LLM)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Comms Drafter    │  templates; optional ≤1 Gemini
└─────────┬─────────┘
          ▼
    ┌─────┼─────────────────┐
    ▼     ▼                 ▼
 evaluate  Celery delay   escalate
    │
    ▼
 strategy_performance  (next run)
```

Three independently auditable layers: **propose** (planner) → **authorize** (policy) → **explain** (Trace). Changing copy generation cannot silently change the recovery strategy.

---

## Measured results

All offline numbers: seed **`42`**, reproducible. Labelled **simulator**.

### Baseline vs Revive (N = 2000)

```bash
docker compose run --rm --no-deps api python -m evals.replay --n 2000 --seed 42
```

| System | Recovered | Rate | Uplift vs always-retry |
|--------|-----------|------|------------------------|
| always_retry | ₹2,086,462 | 32.0% | — |
| static_map | ₹2,753,529 | 40.6% | +₹667,066 |
| **revive** | **₹3,460,643** | **52.9%** | **+₹1,374,181** |

At risk on batch: **₹6,654,115**. Replay wall ~90 ms.

### Ablation (same batch)

```bash
docker compose run --rm --no-deps api python -m evals.ablation --n 2000 --seed 42
```

| Version | Recovered | Rate | Layer added |
|---------|-----------|------|-------------|
| always_retry | ₹2,086,462 | 32.0% | — |
| static_map | ₹2,753,529 | 40.6% | fixed playbook |
| rules_no_profile | ₹3,167,055 | 48.7% | planner |
| rules_no_learning | ₹3,167,055 | 48.7% | + profile |
| revive_no_policy | ₹3,460,643 | 52.9% | + learning |
| **revive** | **₹3,460,643** | **52.9%** | + policy (daytime / no DNC) |

**Reading:** after rules, **learning** is the main ₹ lift. Policy is for compliance; on this midday batch it does not steal recovery.

### Cost + latency (decision path, N = 200)

```bash
docker compose run --rm --no-deps api python -m evals.cost_latency --n 200 --seed 42
```

| Metric | This config (`rules`) | Legacy (2 Gemini / recovery) |
|--------|------------------------|------------------------------|
| Gemini calls | **0** | 2 |
| LLM ₹ / recovery | **₹0.00** | ₹0.10 illustrative |
| p50 / p95 / p99 | **0.021 / 0.024 / 0.034 ms** | network-bound |

### Guardrail + idempotency + webhook proofs

```bash
docker compose run --rm --no-deps api python -m evals.policy_proof          # expect 6/6
python3 scripts/prove_idempotency.py http://localhost:9000               # 5 POSTs → 1 run_id
python3 scripts/prove_webhook.py http://localhost:9000                   # 401 then 200 + duplicate
```

**Live ingest (not simulated):** Razorpay Test Mode payment link failure → `POST /api/v1/webhooks/razorpay` → real `pay_…` in the Live Console with Trace step `webhook_ingest`.

---

## What broke and how we got out

| Incident | Symptom | Root cause | Fix |
|----------|---------|------------|-----|
| Gemini quota / hang | UI “Running agents…” >60s; Render 429 | 2 sync Gemini calls / recovery on free tier; no hard timeout | Rules-only strategy; ≤1 optional draft; **2.5s** wall-clock; frontend AbortController |
| Play CTA dead | Scroll only, no Trace | Footer link didn’t `POST` | Real `POST /recoveries` + select `run_id` + scroll to Trace |
| Webhook gap | Test fails never appeared | Route removed from tree | Restored HMAC webhook; shared mapper; **no invented amounts** |
| Demo “always escalate” | Insufficient funds → human | Same `customer_id` hammered → `prior_failures_24h ≥ 3` | Guardrail working as designed (not a classifier bug) |
| Live console clipped | Funnel/strategy off-screen | CSS grid overflow | `minmax(0,fr)` + table ellipsis |

Full rationale lives in the incident table above and in `backend/evals/` (reproduce commands).

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Agents | LangGraph `StateGraph`, typed Pydantic I/O |
| Policy | Pure Python guard (`backend/policy/`) |
| API | FastAPI, async SQLAlchemy, Postgres |
| Async | Celery + Redis (`delay_and_retry`) |
| Payments | Razorpay Test Mode client + signed webhooks |
| LLM | Optional Gemini Flash (draft only); default off |
| Evals | Offline replay / ablation / policy / cost_latency |
| Frontend | React + Vite dashboard (Agent Trace first-class) |
| Deploy | Render (API) + Vercel (UI) |

---

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + razorpay / webhook / llm flags |
| POST | `/api/v1/webhooks/razorpay` | Signed `payment.failed` ingest |
| POST | `/api/v1/recoveries` | Start recovery (idempotent on `payment_id`) |
| POST | `/api/v1/recoveries/from-razorpay/{payment_id}` | Fetch payment then recover |
| GET | `/api/v1/recoveries` | Live feed |
| GET | `/api/v1/recoveries/{run_id}/trace` | Full Agent Trace |
| GET | `/api/v1/analytics/funnel` | Funnel + ₹ recovered (stored runs) |
| GET | `/api/v1/analytics/strategy-performance` | Learning table |

Interactive docs: `/docs`.

---

## Local setup

```bash
cp .env.example .env
# RAZORPAY_KEY_ID / SECRET (test), RAZORPAY_WEBHOOK_SECRET
# LLM_PROVIDER=rules  LLM_DRAFT_ENABLED=false

docker compose up --build
curl -s http://localhost:9000/health | jq
python scripts/simulate_failures.py

cd frontend && npm install && npm run dev   # http://localhost:6100
```

Razorpay Dashboard → Webhooks (Test Mode) →  
`https://<your-api>/api/v1/webhooks/razorpay` · event **`payment.failed`**.

---

## Project structure

```
revive_Agent/
├── backend/
│   ├── agents/           # classifier, profiler, planner, drafter, evaluator
│   ├── policy/           # deterministic authorization
│   ├── graph/            # LangGraph recovery state machine
│   ├── evals/            # replay, ablation, policy_proof, cost_latency
│   ├── razorpay_client/  # Test API + webhook HMAC
│   ├── tasks/            # Celery delay worker
│   ├── db/               # RecoveryRun, StrategyPerformance
│   └── main.py           # FastAPI
├── frontend/             # hire dashboard + Live Console / Trace
├── scripts/              # simulate_failures, prove_idempotency, prove_webhook
├── docs/DECISIONS.md
└── docs/PROJECT_CHANGES.md
```

---

## Limitations / prototype scope

- **Simulator ≠ GMV.** Offline recovered ₹ uses Agent 5 modelled rates. Do not cite as production revenue.  
- **Test Mode only.** Live keys / live charges are out of scope for this demo.  
- **No outbound WA/SMS provider.** Drafter produces copy + CTA URL; no BSP send receipts yet.  
- **No auth on the dashboard.** Fine for a public hire demo; not multi-tenant production.  
- **Celery cool-down is demo-short** (`DELAY_RETRY_DEMO_SECONDS`, default 30s) vs production minute-scale bank windows.  
- **Not a fraud model.** No LightGBM/SHAP claim; policy is rule-based authorization, not SHAP additivity.  
- **Cold / repeated demo customers escalate** by design after ≥3 failures / 24h.

---

## Why a Razorpay engineer might care

Merchants still recover checkout failures by hand. ReviveAgent is the system you’d put **next to** Checkout volume: structured decisions, policy boundaries, idempotent webhook ingest, async delay, a learning loop, and an Agent Trace you can open in an interview without hand-waving.

We did not assume the agent was better. We measured it against dumb baselines, attacked our own guardrails, cut LLM cost to zero on the hot path when it hurt us, and kept the limitations in the README on purpose.
