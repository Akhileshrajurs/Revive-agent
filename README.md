# ReviveAgent

Event-driven recovery for failed Razorpay payments.

**Perceive → Plan → Policy → Act → Evaluate** — with Agent Trace on every run.

We did not assume the agent is better. We measured it.

**Live demo:** [Vercel dashboard](https://revive-agent-ecru.vercel.app) · **API:** [Render `/health`](https://revive-backend-kenj.onrender.com/health)

> Amounts are **paise (int)**. Outcomes in eval tables are **simulated** (Agent 5 modelled rates), not live Razorpay GMV. That limitation is intentional and labelled everywhere.

---

## Evidence first (seed `42`, N=`2000`)

Reproduce anytime:

```bash
docker compose run --rm --no-deps api python -m evals.replay --n 2000 --seed 42
docker compose run --rm --no-deps api python -m evals.ablation --n 2000 --seed 42
docker compose run --rm --no-deps api python -m evals.policy_proof
docker compose run --rm --no-deps api python -m evals.cost_latency --n 200 --seed 42
# API must be up:
python3 scripts/prove_idempotency.py http://localhost:9000
python3 scripts/prove_webhook.py http://localhost:9000
```

### Money table (Phase 1) — seed `42`, N=`2000`

| System | Recovered | Rate | Uplift vs always-retry |
|--------|-----------|------|------------------------|
| always_retry | ₹2,086,462 | 32.0% | — |
| static_map | ₹2,753,529 | 40.6% | +₹667,066 |
| **revive** | **₹3,460,643** | **52.9%** | **+₹1,374,181** |

At risk: **₹6,654,115**. Replay wall time: **~90 ms**. Same seed → identical ₹.

### Ablation (Phase 2) — same seed/batch

```bash
docker compose run --rm --no-deps api python -m evals.ablation --n 2000 --seed 42
```

| Version | Recovered | Rate | What changed |
|---------|-----------|------|----------------|
| always_retry | ₹2,086,462 | 32.0% | Blind retry |
| static_map | ₹2,753,529 | 40.6% | Fixed playbook |
| rules_no_profile | ₹3,167,055 | 48.7% | Planner, flat profile |
| rules_no_learning | ₹3,167,055 | 48.7% | + real profile |
| revive_no_policy | ₹3,460,643 | 52.9% | + learning loop |
| **revive** | **₹3,460,643** | **52.9%** | + policy (daytime batch; compliance ≠ ₹ crush) |

**Reading:** learning is the main ₹ lift after rules. Policy is for safety (retries/DNC/quiet/permanent) — on this midday batch with no DNC ids it does not steal recovery.

### Cost + latency (decision path)

```bash
docker compose run --rm --no-deps api python -m evals.cost_latency --n 200 --seed 42
```

Default hire-demo config (`LLM_PROVIDER=rules`, drafts off):

| Metric | Value |
|--------|-------|
| Gemini calls / recovery | **0** |
| LLM ₹ / recovery | **₹0.00** |
| Legacy (2 Gemini calls) | ₹0.10 illustrative |
| Cost reduction vs legacy | **100%** on the hot path |
| Decision-path p50 / p95 / p99 | **0.021 / 0.024 / 0.034 ms** (N=200, seed 42, offline) |

Engineering rationale: [`docs/DECISIONS.md`](docs/DECISIONS.md).

### Guardrails (Phase 2)

```bash
docker compose run --rm --no-deps api python -m evals.policy_proof
```

Proves:

| Attack | Policy rule |
|--------|-------------|
| `retry_count ≥ 3` | → escalate |
| Customer on DNC | → escalate, no outbound |
| `vpa_invalid` + same-method retry | → force alternate |
| Quiet hours (22:00–08:00 IST) | → delay, no immediate SMS/WA |
| Midday normal failure | → pass through |

### Idempotency (Phase 2)

```bash
python3 scripts/prove_idempotency.py http://localhost:9000
```

5× POST same `payment_id` → **1** `run_id`. First `idempotent_replay=false`, rest `true`. No second Celery schedule.

### Live ingest — Razorpay webhook

```bash
# Razorpay Dashboard → Webhooks → URL:
#   https://YOUR-RENDER.onrender.com/api/v1/webhooks/razorpay
# Active events: payment.failed
# Set RAZORPAY_WEBHOOK_SECRET on Render to the webhook signing secret

python3 scripts/prove_webhook.py http://localhost:9000
```

HMAC reject (401) + `payment.failed` → recovery + duplicate → same `run_id`. Agent Trace shows **Webhook Ingest**.

---

## Architecture

```
payment.failed / POST /recoveries
        │
        ▼
   idempotency check (payment_id unique)
        │
        ▼
   Failure Classifier (rules)
        │
        ▼
   Customer Profiler (rules)
        │
        ▼
   Strategy Planner (rules + learning)     ← money-safe, no LLM
        │
        ▼
   Policy Guard (retries / DNC / quiet / permanent)
        │
        ▼
   Comms Drafter (templates; optional ≤1 Gemini, 2.5s hard timeout)
        │
        ├── delay_and_retry → Celery (no sleep on request path)
        ├── escalate → human
        └── else → Outcome Evaluator → strategy_performance
```

**AI judgment:** Gemini is optional copy only. Strategy + policy stay deterministic. Free-tier 429 cannot stall recovery.

---

## Quick start

```bash
cp .env.example .env
# add Razorpay TEST keys; keep LLM_PROVIDER=rules for zero LLM latency

docker compose up --build
curl -s http://localhost:9000/health | jq
python scripts/simulate_failures.py
cd frontend && npm install && npm run dev   # http://localhost:6100
```

| Surface | URL |
|---------|-----|
| API docs | http://localhost:9000/docs |
| Dashboard | http://localhost:6100 |
| Evals | `backend/evals/README.md` |

Env knobs that matter:

| Var | Demo-safe value |
|-----|-----------------|
| `LLM_PROVIDER` | `rules` |
| `LLM_DRAFT_ENABLED` | `false` |
| `LLM_TIMEOUT_SECONDS` | `2.5` |
| `POLICY_DNC_CUSTOMER_IDS` | comma-separated ids |
| `POLICY_QUIET_HOURS_START` / `_END` | `22` / `8` (IST) |

---

## What is real vs mock

| Piece | Status |
|-------|--------|
| Razorpay test keys / fetch payment | Real (when configured) |
| LangGraph multi-agent loop + Agent Trace | Real |
| Celery `delay_and_retry` | Real |
| Strategy learning table | Real |
| Policy guard + idempotent `payment_id` | Real |
| Customer message send (WA/SMS) | Draft only (no provider send yet) |
| Recovery outcomes in eval / demo | **Simulated** Agent 5 rates |
| Live production GMV | **Not claimed** |

---

## Engineering decisions (short)

- **Rules for strategy, not Gemini** — money-safe, low latency, auditable Trace.
- **Policy after plan** — model/rules propose; policy authorizes.
- **≤1 optional LLM call** with hard timeout — 429/hang never blocks recovery.
- **Idempotent `payment_id`** — duplicate webhooks must not double-act.
- **Synthetic eval data** — Razorpay prod dumps unavailable; we label the simulator.

See [`docs/DECISIONS.md`](docs/DECISIONS.md) for why rules > LLM on strategy, why policy exists, and what broke.
See `docs/PROJECT_CHANGES.md` for the living codebase map.

---

## Why Razorpay should care

Merchants still recover failures by hand — bulk SMS, no personalization, no feedback loop, no audit trail.

ReviveAgent is the system you’d put next to Checkout volume: structured decisions, guardrails, measurable ₹ uplift vs baselines, and Agent Trace so a reviewer can see **why** each rupee path was chosen.
