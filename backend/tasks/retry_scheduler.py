"""Celery tasks: execute delayed recovery retries.

When Agent 3 chooses `delay_and_retry`, the API schedules
`execute_delayed_retry` with a countdown. The worker later
runs Outcome Evaluator and closes the loop (recovered/failed).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from agents.outcome_evaluator import evaluate_outcome, expected_success_rate, outcome_reasoning
from config import get_settings
from db.models import FailureType as DBFailureType
from db.models import RecoveryRun
from db.models import RecoveryStatus as DBRecoveryStatus
from db.models import RecoveryStrategy as DBRecoveryStrategy
from db.models import SimulatedOutcome, StrategyPerformance
from models.schemas import FailureType, RecoveryStrategy
from tasks.celery_app import celery_app

log = structlog.get_logger()


def _sync_engine():
    settings = get_settings()
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    return create_engine(url, pool_pre_ping=True)


def _upsert_perf(session: Session, strategy: DBRecoveryStrategy, failure_type: DBFailureType, success: bool) -> None:
    row = session.execute(
        select(StrategyPerformance).where(
            StrategyPerformance.strategy == strategy,
            StrategyPerformance.failure_type == failure_type,
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            StrategyPerformance(
                strategy=strategy,
                failure_type=failure_type,
                attempts=1,
                successes=1 if success else 0,
            )
        )
    else:
        row.attempts += 1
        if success:
            row.successes += 1


@celery_app.task(name="tasks.retry_scheduler.execute_delayed_retry", bind=True, max_retries=2)
def execute_delayed_retry(self, run_id: str) -> dict:
    """Wake up after bank downtime window and score the recovery attempt."""
    engine = _sync_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as session:
        run = session.get(RecoveryRun, UUID(run_id))
        if not run:
            log.error("delayed_retry_missing_run", run_id=run_id)
            return {"ok": False, "error": "run_not_found"}

        if run.status != DBRecoveryStatus.scheduled:
            log.info("delayed_retry_skip", run_id=run_id, status=str(run.status))
            return {"ok": False, "error": "not_scheduled", "status": str(run.status)}

        failure_type = FailureType(run.failure_type.value) if run.failure_type else FailureType.unknown
        strategy = RecoveryStrategy.delay_and_retry
        params = (run.strategy_decision or {}).get("personalization_params") or {}

        # Historical rates for blended success model
        perf_row = session.execute(
            select(StrategyPerformance).where(
                StrategyPerformance.strategy == DBRecoveryStrategy.delay_and_retry,
                StrategyPerformance.failure_type == run.failure_type,
            )
        ).scalar_one_or_none()
        hist_attempts = perf_row.attempts if perf_row else 0
        hist_rate = (perf_row.successes / perf_row.attempts) if perf_row and perf_row.attempts else None

        rate = expected_success_rate(
            strategy,
            failure_type,
            historical_rate=hist_rate,
            historical_attempts=hist_attempts,
        )
        outcome = evaluate_outcome(
            payment_id=f"{run.payment_id}:delayed:{run.retry_count + 1}",
            strategy=strategy,
            failure_type=failure_type,
            payment_method=run.payment_method,
            suggested_method=params.get("suggested_method"),
            historical_rate=hist_rate,
            historical_attempts=hist_attempts,
        )
        payload = outcome.model_dump()
        payload["modelled_success_rate"] = round(rate, 4)
        payload["delayed"] = True
        payload["executed_at"] = datetime.now(timezone.utc).isoformat()
        reasoning = outcome_reasoning(outcome, rate)

        run.retry_count = (run.retry_count or 0) + 1
        run.status = DBRecoveryStatus.recovered if outcome.success else DBRecoveryStatus.failed
        run.outcome = payload

        steps = list((run.agent_trace or {}).get("steps") or [])
        steps.append(
            {
                "agent": "delayed_retry_worker",
                "status": "ok",
                "output": payload,
                "reasoning": (
                    f"Celery executed delayed retry after bank/netbanking cool-down. {reasoning}"
                ),
                "latency_ms": 0,
            }
        )
        run.agent_trace = {"steps": steps}
        flag_modified(run, "agent_trace")
        run.outcome = payload
        flag_modified(run, "outcome")

        session.add(
            SimulatedOutcome(
                run_id=run.id,
                success=outcome.success,
                method_used=outcome.method_used,
                time_to_recovery_seconds=outcome.time_to_recovery_seconds,
                strategy_used=DBRecoveryStrategy.delay_and_retry,
            )
        )
        _upsert_perf(
            session,
            DBRecoveryStrategy.delay_and_retry,
            run.failure_type or DBFailureType.unknown,
            outcome.success,
        )
        session.commit()

        log.info(
            "delayed_retry_complete",
            run_id=run_id,
            payment_id=run.payment_id,
            success=outcome.success,
            status=run.status.value,
        )
        return {
            "ok": True,
            "run_id": run_id,
            "success": outcome.success,
            "status": run.status.value,
        }


def schedule_delayed_retry(run_id: UUID, countdown_seconds: int) -> str:
    """Enqueue delayed retry. Returns Celery task id."""
    async_result = execute_delayed_retry.apply_async(
        args=[str(run_id)],
        countdown=max(1, int(countdown_seconds)),
    )
    log.info(
        "delayed_retry_scheduled",
        run_id=str(run_id),
        countdown_seconds=countdown_seconds,
        task_id=async_result.id,
    )
    return async_result.id
