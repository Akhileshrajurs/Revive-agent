from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.database import get_db, init_db
from db.models import FailureType as DBFailureType
from db.models import RecoveryRun
from db.models import RecoveryStatus as DBRecoveryStatus
from db.models import RecoveryStrategy as DBRecoveryStrategy
from db.models import SimulatedOutcome, StrategyPerformance
from graph.recovery_graph import run_recovery_pipeline
from models.schemas import (
    AgentTraceStep,
    ClassifyResponse,
    CustomerPaymentProfile,
    DraftedMessage,
    FailedPaymentIn,
    FailureClassification,
    FunnelOut,
    RecoveryOutcome,
    RecoveryRunOut,
    RecoveryStatus,
    StrategyDecision,
    StrategyPerformanceOut,
)
from razorpay_client.client import get_razorpay_client
from tasks.retry_scheduler import schedule_delayed_retry

log = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    mode = "razorpay_test" if settings.razorpay_configured else "mock"
    log.info(
        "startup",
        env=settings.app_env,
        payment_client=mode,
        llm_provider=settings.llm_provider,
        gemini=settings.gemini_configured,
        llm_draft_enabled=settings.llm_draft_enabled,
        llm_timeout_seconds=settings.llm_timeout_seconds,
        llm_calls_per_recovery_max=(
            1
            if settings.llm_provider == "gemini"
            and settings.gemini_configured
            and settings.llm_draft_enabled
            else 0
        ),
        delay_demo_seconds=settings.delay_retry_demo_seconds,
    )
    yield


app = FastAPI(
    title="ReviveAgent API",
    description="Autonomous multi-agent payment failure recovery — full Perceive→Plan→Act→Evaluate loop",
    version="0.4.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "service": "ReviveAgent",
        "docs": "/docs",
        "health": "/health",
        "version": "0.4.0",
        "loop": ["classify", "profile", "plan", "policy", "draft", "evaluate|schedule"],
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "razorpay": "configured" if settings.razorpay_configured else "mock",
        "llm_provider": settings.llm_provider,
        "gemini": "configured" if settings.gemini_configured else "missing",
        "llm_draft_enabled": settings.llm_draft_enabled,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
        "llm_calls_per_recovery_max": (
            1
            if settings.llm_provider == "gemini"
            and settings.gemini_configured
            and settings.llm_draft_enabled
            else 0
        ),
        "delay_retry_demo_seconds": settings.delay_retry_demo_seconds,
    }


async def _prior_failures_24h(db: AsyncSession, customer_id: str | None) -> int:
    if not customer_id:
        return 0
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = (
        select(func.count())
        .select_from(RecoveryRun)
        .where(RecoveryRun.customer_id == customer_id, RecoveryRun.created_at >= since)
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _load_strategy_performance(db: AsyncSession) -> dict[str, dict]:
    rows = (await db.execute(select(StrategyPerformance))).scalars().all()
    out: dict[str, dict] = {}
    for row in rows:
        key = f"{row.strategy.value}|{row.failure_type.value}"
        out[key] = {"attempts": row.attempts, "successes": row.successes}
    return out


async def _upsert_strategy_performance(
    db: AsyncSession,
    strategy: DBRecoveryStrategy,
    failure_type: DBFailureType,
    success: bool,
) -> None:
    stmt = select(StrategyPerformance).where(
        StrategyPerformance.strategy == strategy,
        StrategyPerformance.failure_type == failure_type,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = StrategyPerformance(
            strategy=strategy,
            failure_type=failure_type,
            attempts=1,
            successes=1 if success else 0,
        )
        db.add(row)
    else:
        row.attempts += 1
        if success:
            row.successes += 1


def _countdown_seconds(decision: StrategyDecision) -> int:
    if settings.delay_retry_use_demo_countdown:
        return max(1, settings.delay_retry_demo_seconds)
    return max(60, int(decision.timing_offset_minutes or 0) * 60)


def _classify_response_from_run(run: RecoveryRun, *, idempotent: bool) -> ClassifyResponse:
    from models.schemas import FailureType as SchemaFailureType

    steps = (run.agent_trace or {}).get("steps") or []
    ft = (
        SchemaFailureType(run.failure_type.value)
        if run.failure_type is not None
        else SchemaFailureType.unknown
    )
    classification = FailureClassification(
        failure_type=ft,
        confidence=float(run.failure_confidence or 0.0),
        raw_error_code=run.raw_error_code,
        payment_method=run.payment_method,
        reasoning="Idempotent replay — existing recovery run returned.",
    )
    profile = (
        CustomerPaymentProfile.model_validate(run.customer_profile)
        if run.customer_profile
        else None
    )
    decision = (
        StrategyDecision.model_validate(run.strategy_decision)
        if run.strategy_decision
        else None
    )
    draft = (
        DraftedMessage.model_validate(run.drafted_message) if run.drafted_message else None
    )
    outcome = None
    if run.outcome:
        try:
            outcome = RecoveryOutcome.model_validate(
                {
                    "success": bool(run.outcome.get("success")),
                    "method_used": run.outcome.get("method_used"),
                    "time_to_recovery_seconds": run.outcome.get("time_to_recovery_seconds"),
                    "strategy_used": run.outcome.get("strategy_used") or (
                        run.strategy.value if run.strategy else None
                    ),
                    "modelled_success_rate": run.outcome.get("modelled_success_rate"),
                }
            )
        except Exception:
            outcome = None
    return ClassifyResponse(
        run_id=run.id,
        payment_id=run.payment_id,
        classification=classification,
        status=RecoveryStatus(run.status.value),
        customer_profile=profile,
        strategy_decision=decision,
        drafted_message=draft,
        outcome=outcome,
        agent_trace=[AgentTraceStep.model_validate(s) for s in steps if isinstance(s, dict)],
        idempotent_replay=idempotent,
    )


@app.post("/api/v1/recoveries", response_model=ClassifyResponse)
async def start_recovery(body: FailedPaymentIn, db: AsyncSession = Depends(get_db)):
    """Full loop: classify → profile → plan → policy → draft → evaluate or schedule.

    Idempotent on `payment_id`: duplicate POSTs/webhooks return the existing run
    without re-running the pipeline or scheduling a second Celery task.
    """
    existing = (
        await db.execute(select(RecoveryRun).where(RecoveryRun.payment_id == body.payment_id))
    ).scalar_one_or_none()
    if existing is not None:
        log.info(
            "recovery_idempotent_hit",
            payment_id=body.payment_id,
            run_id=str(existing.id),
        )
        return _classify_response_from_run(existing, idempotent=True)

    prior = await _prior_failures_24h(db, body.customer_id)
    perf = await _load_strategy_performance(db)
    payload = body.model_dump()
    payload["prior_failures_24h"] = prior
    payload["strategy_performance"] = perf

    result = run_recovery_pipeline(payload)
    classification = FailureClassification.model_validate(result["classification"])
    profile = CustomerPaymentProfile.model_validate(result["customer_profile"])
    decision = StrategyDecision.model_validate(result["strategy_decision"])
    draft = DraftedMessage.model_validate(result["drafted_message"])
    immediate_outcome = RecoveryOutcome.model_validate(result["outcome"])

    deferred = bool(result.get("defer_celery")) or decision.strategy.value == "delay_and_retry"
    if decision.strategy.value == "escalate_to_human":
        status = DBRecoveryStatus.escalated
    elif deferred:
        status = DBRecoveryStatus.scheduled
    elif immediate_outcome.success:
        status = DBRecoveryStatus.recovered
    else:
        status = DBRecoveryStatus.failed

    steps = list(result.get("agent_trace") or [])
    celery_task_id = None
    countdown = _countdown_seconds(decision) if deferred else 0

    if deferred:
        execute_at = datetime.now(timezone.utc) + timedelta(seconds=countdown)
        outcome_blob = {
            "success": False,
            "deferred": True,
            "strategy_used": decision.strategy.value,
            "method_used": body.method,
            "countdown_seconds": countdown,
            "scheduled_for": execute_at.isoformat(),
            "modelled_success_rate": immediate_outcome.modelled_success_rate,
            "note": "Waiting for bank/netbanking cool-down; Celery will execute retry.",
        }
        response_outcome = RecoveryOutcome(
            success=False,
            method_used=body.method,
            time_to_recovery_seconds=None,
            strategy_used=decision.strategy,
            modelled_success_rate=immediate_outcome.modelled_success_rate,
        )
    else:
        outcome_blob = immediate_outcome.model_dump()
        response_outcome = immediate_outcome

    run = RecoveryRun(
        payment_id=body.payment_id,
        order_id=body.order_id,
        customer_id=body.customer_id,
        amount_paise=body.amount_paise,
        currency=body.currency,
        payment_method=body.method,
        raw_error_code=body.error_code or body.error_reason,
        raw_error_description=body.error_description,
        failure_type=DBFailureType(classification.failure_type.value),
        failure_confidence=classification.confidence,
        strategy=DBRecoveryStrategy(decision.strategy.value),
        status=status,
        agent_trace={"steps": steps},
        customer_profile=profile.model_dump(),
        strategy_decision=decision.model_dump(),
        drafted_message=draft.model_dump(),
        outcome=outcome_blob,
    )
    db.add(run)
    try:
        await db.flush()
    except IntegrityError:
        # Race: another request inserted the same payment_id
        await db.rollback()
        raced = (
            await db.execute(select(RecoveryRun).where(RecoveryRun.payment_id == body.payment_id))
        ).scalar_one_or_none()
        if raced is None:
            raise
        log.info(
            "recovery_idempotent_race",
            payment_id=body.payment_id,
            run_id=str(raced.id),
        )
        return _classify_response_from_run(raced, idempotent=True)

    if deferred:
        try:
            celery_task_id = schedule_delayed_retry(run.id, countdown)
            steps.append(
                {
                    "agent": "retry_scheduler",
                    "status": "ok",
                    "output": {
                        "celery_task_id": celery_task_id,
                        "countdown_seconds": countdown,
                        "strategy": "delay_and_retry",
                    },
                    "reasoning": (
                        f"Scheduled Celery delayed retry in {countdown}s "
                        f"(demo cool-down; production would use "
                        f"{decision.timing_offset_minutes} minutes)."
                    ),
                    "latency_ms": 0,
                }
            )
            run.agent_trace = {"steps": steps}
            flag_modified(run, "agent_trace")
            run.outcome = {**outcome_blob, "celery_task_id": celery_task_id}
            flag_modified(run, "outcome")
        except Exception as exc:
            log.error("schedule_delayed_retry_failed", error=str(exc), run_id=str(run.id))
            run.status = DBRecoveryStatus.failed
            status = DBRecoveryStatus.failed
            run.outcome = {**outcome_blob, "schedule_error": str(exc)}
    else:
        db.add(
            SimulatedOutcome(
                run_id=run.id,
                success=immediate_outcome.success,
                method_used=immediate_outcome.method_used,
                time_to_recovery_seconds=immediate_outcome.time_to_recovery_seconds,
                strategy_used=DBRecoveryStrategy(decision.strategy.value),
            )
        )
        if decision.strategy.value != "escalate_to_human":
            await _upsert_strategy_performance(
                db,
                DBRecoveryStrategy(decision.strategy.value),
                DBFailureType(classification.failure_type.value),
                immediate_outcome.success,
            )

    await db.refresh(run)

    log.info(
        "recovery_pipeline_complete",
        run_id=str(run.id),
        payment_id=run.payment_id,
        failure_type=classification.failure_type.value,
        strategy=decision.strategy.value,
        status=status.value,
        deferred=deferred,
        celery_task_id=celery_task_id,
    )

    return ClassifyResponse(
        run_id=run.id,
        payment_id=run.payment_id,
        classification=classification,
        status=RecoveryStatus(status.value),
        customer_profile=profile,
        strategy_decision=decision,
        drafted_message=draft,
        outcome=response_outcome,
        agent_trace=[
            AgentTraceStep.model_validate(s)
            for s in (run.agent_trace or {}).get("steps", steps)
        ],
        idempotent_replay=False,
    )


@app.get("/api/v1/recoveries", response_model=list[RecoveryRunOut])
async def list_recoveries(limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = select(RecoveryRun).order_by(RecoveryRun.created_at.desc()).limit(min(limit, 200))
    return (await db.execute(stmt)).scalars().all()


@app.get("/api/v1/recoveries/{run_id}", response_model=RecoveryRunOut)
async def get_recovery(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(RecoveryRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Recovery run not found")
    return run


@app.get("/api/v1/recoveries/{run_id}/trace")
async def get_agent_trace(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await db.get(RecoveryRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Recovery run not found")
    return {
        "run_id": run.id,
        "payment_id": run.payment_id,
        "amount_paise": run.amount_paise,
        "status": run.status,
        "failure_type": run.failure_type,
        "strategy": run.strategy,
        "customer_profile": run.customer_profile,
        "strategy_decision": run.strategy_decision,
        "drafted_message": run.drafted_message,
        "outcome": run.outcome,
        "steps": (run.agent_trace or {}).get("steps", []),
    }


@app.get("/api/v1/analytics/funnel", response_model=FunnelOut)
async def recovery_funnel(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(RecoveryRun))).scalars().all()
    failures = len(rows)
    attempted = sum(1 for r in rows if r.status != DBRecoveryStatus.pending)
    recovered = sum(1 for r in rows if r.status == DBRecoveryStatus.recovered)
    escalated = sum(1 for r in rows if r.status == DBRecoveryStatus.escalated)
    revenue = sum(r.amount_paise for r in rows if r.status == DBRecoveryStatus.recovered)
    by_type: dict[str, int] = {}
    for r in rows:
        key = r.failure_type.value if r.failure_type else "unknown"
        by_type[key] = by_type.get(key, 0) + 1
    return FunnelOut(
        failures=failures,
        attempted=attempted,
        recovered=recovered,
        escalated=escalated,
        revenue_saved_paise=revenue,
        by_failure_type=by_type,
    )


@app.get("/api/v1/analytics/strategy-performance", response_model=list[StrategyPerformanceOut])
async def strategy_performance(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(StrategyPerformance))).scalars().all()
    out = []
    for row in rows:
        rate = (row.successes / row.attempts) if row.attempts else 0.0
        out.append(
            StrategyPerformanceOut(
                strategy=row.strategy,
                failure_type=row.failure_type,
                attempts=row.attempts,
                successes=row.successes,
                recovery_rate=round(rate, 4),
            )
        )
    out.sort(key=lambda x: x.recovery_rate, reverse=True)
    return out


@app.post("/api/v1/recoveries/from-razorpay/{payment_id}", response_model=ClassifyResponse)
async def recover_from_razorpay(payment_id: str, db: AsyncSession = Depends(get_db)):
    client = get_razorpay_client()
    try:
        payment = client.fetch_payment(payment_id)
    except Exception as exc:
        log.error("razorpay_fetch_failed", payment_id=payment_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Razorpay fetch failed: {exc}") from exc

    body = FailedPaymentIn(
        payment_id=payment.get("id", payment_id),
        order_id=payment.get("order_id"),
        customer_id=payment.get("customer_id"),
        amount_paise=int(payment.get("amount") or 0) or 100,
        currency=payment.get("currency") or "INR",
        method=payment.get("method"),
        error_code=payment.get("error_code"),
        error_description=payment.get("error_description"),
        error_source=payment.get("error_source"),
        error_step=payment.get("error_step"),
        error_reason=payment.get("error_reason"),
        customer_name=(payment.get("notes") or {}).get("customer_name") or "Customer",
        email=payment.get("email"),
        contact=payment.get("contact"),
    )
    return await start_recovery(body, db)
