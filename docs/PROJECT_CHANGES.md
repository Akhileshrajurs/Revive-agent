# ReviveAgent — What Owns This Project

Living map of the codebase you need to understand, plus a changelog of **main** changes (not every edit). Agents update this file when owning behavior changes. See `.cursor/rules/project-knowledge-changelog.mdc`.

---

## Codebase map

### Product intent

ReviveAgent recovers failed Razorpay payments via a multi-agent loop: **Perceive → Plan → Act → Evaluate**, with explainable `agent_trace` for every run. Amounts are always **paise (int)**. Secrets stay in `.env`.

### Layout (backend)

| Area | Path | What you must know |
|------|------|--------------------|
| API entry | `backend/main.py` | FastAPI app, `/health`, `POST /api/v1/recoveries`, recovery list/trace endpoints; persists classify result + `agent_trace` |
| Config | `backend/config.py` | Env-driven settings (Razorpay keys, LLM, CORS, DB/Redis) |
| Contracts | `backend/models/schemas.py` | Pydantic enums + I/O: `FailureType`, `RecoveryStrategy`, `RecoveryStatus`, `FailedPaymentIn`, agent outputs |
| Persistence | `backend/db/models.py`, `backend/db/database.py` | SQLAlchemy `RecoveryRun`, `StrategyPerformance`; async Postgres session |
| Graph | `backend/graph/recovery_graph.py` | LangGraph `RecoveryState`; Day-1 classify-only graph (`failure_classifier` → END) |
| Agents | `backend/agents/` | One module per agent: classifier, profiler, strategy planner, comms drafter, outcome evaluator |
| Payments | `backend/razorpay_client/client.py` | Real test-mode client or mock when keys absent |
| Async work | `backend/tasks/retry_scheduler.py` | Celery/Redis delayed retries (not the sync classify path) |
| Local sim | `scripts/simulate_failures.py` | Smoke failed-payment events into the API |
| Compose | `docker-compose.yml`, `backend/Dockerfile` | Postgres + Redis + API |
| Frontend | `frontend/src/` | Hire-me scroll landing + live console; `App.tsx` composes sections; Agent Trace is `#trace` |

### Agent pipeline (target)

1. **Failure Classifier** — map Razorpay errors → taxonomy + confidence + reasoning  
2. **Customer Profiler** — method prefs, risk, retry windows  
3. **Strategy Planner** — structured `RecoveryStrategy` + channel/timing + reasoning  
4. **Comms Drafter** — message + CTA (schema-wrapped)  
5. **Outcome Evaluator** — success from API/simulator; feed strategy performance  

Day 1–2: Agent 1 wired end-to-end. **Now:** Agents 1–5 in one LangGraph loop; dashboard consumes feed/funnel/trace/performance APIs.

### Cursor rules (domain)

| Rule | When |
|------|------|
| `staff-engineer-mindset.mdc` | Always — correctness, idempotency, auditability |
| `payments-fintech.mdc` | Payments / agents / models / scripts |
| `ai-agents-langgraph.mdc` | Agents, graph, tasks |
| `backend-fastapi.mdc` | `backend/**/*.py` |
| `frontend-dashboard.mdc` | Dashboard UI (when present) |
| `project-knowledge-changelog.mdc` | Always — keep this file current |

### How to verify

```bash
docker compose up --build
curl -s http://localhost:9000/health | jq
python scripts/simulate_failures.py
# OpenAPI: http://localhost:9000/docs
cd frontend && npm install && npm run dev
# Dashboard: http://localhost:6100
```

**DBeaver (Postgres):** `localhost:5432` / db `revive_agent` / user `revive` / password `revive` / SSL off.

---

## Changelog

Newest first. Main / owning changes only.

### 2026-10-02 — Live console overflow fix (right side clipped)

- **What:** Grid columns use `minmax(0, fr)`; panels `min-width: 0`; tables `table-layout: fixed` + ellipsis; chart box constrained. Two-col console only from 1100px+.
- **Why it matters:** Funnel + Strategy performance were pushed off-screen by long payment IDs; reviewers couldn’t see the full dashboard.
- **Paths:** `frontend/src/styles.css`, `frontend/src/components/RecoveryFunnel.tsx`

### 2026-10-02 — Footer Play → real recovery + Agent Trace

- **What:** “See it happen in the live console” now `POST`s a typed failed payment for the tapped scenario, refreshes feed/funnel/perf, selects the new `run_id`, scrolls to `#trace`, and shows a “Just ran” banner. Unique `payment_id` per click.
- **Why it matters:** Hire-page CTA no longer only scrolls — reviewers watch the multi-agent loop fire end-to-end from a mouse gesture.
- **Paths:** `frontend/src/demoFailures.ts`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/components/SiteFooter.tsx`, `frontend/src/components/LiveConsole.tsx`

### 2026-10-02 — Hire-me landing UI (Razorpay AI Builders–style)

- **What:** Full frontend overhaul: dark scroll storytelling (hero, process, interactive agent loop, strategy carousel, Celery delay chapter, scale tiers, footer “play” failure picker) + restyled live console (feed / funnel / Agent Trace / learning). Sticky nav + mobile overlay. Framer Motion `whileInView`. Live API polling only when `#live` is visible.
- **Why it matters:** Reviewers opening the share URL learn the multi-agent recovery loop by scrolling/hovering/clicking — Agent Trace stays the hire signal, not a plain admin grid.
- **Paths:** `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/components/{SiteNav,Hero,WhatSection,AgentLoop,StrategyCarousel,DelayTimeline,LiveConsole,ScaleSection,SiteFooter}.tsx`, `frontend/index.html`

### 2026-10-02 — LangGraph conditional branches + zero-latency rule

- **What:** Real `add_conditional_edges` after strategy (6 path nodes) and after comms (`outcome_evaluator` | `defer_to_celery` | `finalize_escalate`). Delay path skips immediate outcome scoring. Cursor rule `zero-unnecessary-latency.mdc`.
- **Why it matters:** Diagram is a state machine (not a line); request path never sleeps; Celery owns cool-down.
- **Paths:** `backend/graph/recovery_graph.py`, `.cursor/rules/zero-unnecessary-latency.mdc`

### 2026-10-02 — Cursor rules: Razorpay AI Builder bar everywhere

- **What:** Injected explicit **“Razorpay AI Builder bar”** into all `.cursor/rules/*.mdc` — build what they hire AI Builders for (multi-agent, pipelines, explainability), not wrappers.
- **Why it matters:** Keeps every future change aimed at the job signal.
- **Paths:** `.cursor/rules/*.mdc`

### 2026-10-02 — Cursor rules: scale + hire-me voice

- **What:** Always-on rules `razorpay-scale-options.mdc` (demo → merchant → Razorpay-scale options) and `hire-me-demo-voice.mdc` (max impressive integration + teen-plain post-build “why Razorpay hires you”).
- **Why it matters:** Keeps every suggestion aimed at callback-level ambition and understandable explanations.
- **Paths:** `.cursor/rules/razorpay-scale-options.mdc`, `.cursor/rules/hire-me-demo-voice.mdc`

### 2026-10-02 — Celery `delay_and_retry`

- **What:** When Agent 3 picks `delay_and_retry`, API sets status `scheduled` and enqueues Celery task. Worker later runs Outcome Evaluator. Demo countdown default **30s** (`DELAY_RETRY_DEMO_SECONDS`). Compose service `worker` added.
- **Why it matters:** Bank/netbanking outages need cool-down — not instant fake outcomes. Shows real async recovery ops.
- **Paths:** `backend/tasks/celery_app.py`, `backend/tasks/retry_scheduler.py`, `backend/main.py`, `docker-compose.yml`

### 2026-10-02 — Agent 5 learning loop + React dashboard

- **What:** Outcome evaluator simulates recovery, writes `strategy_performance` + `simulated_outcomes`, feeds rates back into Agent 3. Analytics APIs for funnel + strategy performance. React dashboard: Live Feed, Funnel, Agent Trace, Strategy Performance.
- **Why it matters:** Closes the Perceive→Plan→Act→Evaluate loop Razorpay merchants still run manually; Trace view is the demo callback surface.
- **Paths:** `backend/agents/outcome_evaluator.py`, `backend/graph/recovery_graph.py`, `backend/main.py`, `frontend/src/**`

### 2026-10-02 — Agents 2–4 + Gemini Flash

- **What:** Full LangGraph path `classifier → profiler → strategy_planner → comms_drafter`. Strategy chosen by rules; Gemini enriches reasoning + drafts messages. Default model **`gemini-3.8-flash`** (2.0-flash retired on this API). Soft fallback to templates if LLM fails.
- **Why it matters:** Demo-ready multi-agent loop with explainable Trace steps on free-tier Gemini.
- **Paths:** `backend/graph/recovery_graph.py`, `backend/agents/customer_profiler.py`, `backend/agents/strategy_planner.py`, `backend/agents/comms_drafter.py`, `backend/llm/gemini_client.py`, `backend/main.py`, `backend/config.py`

### 2026-10-02 — API on :9000 + DBeaver Postgres access

- **What:** API host port changed from 8000 → **9000**. Documented DBeaver connection to Compose Postgres on `localhost:5432`.
- **Why it matters:** Local API URL and DB GUI access are fixed for day-to-day work.
- **Paths:** `docker-compose.yml`, `backend/Dockerfile`, `scripts/simulate_failures.py`, `README.md`

### 2026-10-02 — Project knowledge docs + Cursor rule

- **What:** Added always-on rule `project-knowledge-changelog.mdc` and this living docs file (codebase map + changelog).
- **Why it matters:** Every main code change must be recorded here so you can see what owns and evolves the project without reading every diff.
- **Paths:** `.cursor/rules/project-knowledge-changelog.mdc`, `docs/PROJECT_CHANGES.md`

### 2026-10-02 — Baseline: Day 1–2 classify path (pre-existing)

- **What:** FastAPI + Postgres + LangGraph Agent 1 (Failure Classifier) ingest failed payments, classify, persist `RecoveryRun` + `agent_trace`. Mock/test Razorpay client, simulate script, Docker Compose stack.
- **Why it matters:** This is the current owning spine of the product; later agents and dashboard hang off these contracts.
- **Paths:** `backend/main.py`, `backend/graph/recovery_graph.py`, `backend/agents/failure_classifier.py`, `backend/models/schemas.py`, `backend/db/models.py`, `backend/razorpay_client/client.py`, `scripts/simulate_failures.py`, `docker-compose.yml`
