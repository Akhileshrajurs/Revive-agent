# Engineering Decisions

Short record of why ReviveAgent looks the way it does. Written for Razorpay reviewers.

## Why rules (not Gemini) pick the recovery strategy

Money-adjacent decisions must be deterministic, auditable, and fast.
Gemini is optional for **message copy only** (`LLM_DRAFT_ENABLED`).
Strategy enums come from typed rules + a learning override from `strategy_performance`.

## Why a policy guard after the planner

An agent (or a rule table) can *propose* a strategy. It must not *authorize* spam.
Policy enforces: max retries, DNC, quiet hours (IST), permanent-rail no same-method retry.
LLM / rules cannot bypass this node — Trace shows every override.

## Why ≤1 Gemini call (and usually 0)

Early demos used 2 free-tier calls per recovery and hit 429 / multi-minute hangs.
We cut strategy enrichment, added a hard wall-clock timeout, and defaulted
`LLM_PROVIDER=rules`. Recovery never waits on a hung LLM.

Measured offline: see `python -m evals.cost_latency`.

## Why PostgreSQL + Redis/Celery

- Postgres holds recovery truth, Trace JSON, and unique `payment_id`.
- Celery owns `delay_and_retry` cool-down — **no `sleep` on the request path**.

## Why synthetic eval data

Razorpay production dumps are unavailable for an internship demo.
We publish seeded replay/ablation tables and label them **simulator**, not live GMV.
Live proof of ingest is separate: Test Mode `payment.failed` webhook → Trace `webhook_ingest`.

## Why idempotent webhooks

Duplicate `payment.failed` deliveries must not double-message or double-schedule Celery.
`POST /recoveries` and the webhook share the same `payment_id` uniqueness contract.

## What broke (honest)

1. **Gemini free-tier 429 / hung “Running agents…”** — fixed by rules-default + timeout + frontend abort.
2. **Play CTA only scrolled** — fixed by real `POST` + Trace select.
3. **Webhook missing from tree** — restored with HMAC verify, no invented amounts.
4. **Demo customers self-escalating** — `prior_failures_24h ≥ 3` after many Play taps; guardrail working as designed.

## Non-goals (on purpose)

- Not a fraud LightGBM/SHAP scorer (different Razorpay track).
- Not live WhatsApp send (draft + CTA URL only).
- Not claiming production GMV from the offline money table.
