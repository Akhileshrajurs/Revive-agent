import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class RecoveryStatus(str, enum.Enum):
    pending = "pending"
    classified = "classified"
    planned = "planned"
    messaged = "messaged"
    scheduled = "scheduled"  # delay_and_retry waiting for Celery
    recovered = "recovered"
    failed = "failed"
    escalated = "escalated"


class FailureType(str, enum.Enum):
    insufficient_funds = "insufficient_funds"
    wrong_otp = "wrong_otp"
    bank_timeout = "bank_timeout"
    card_blocked = "card_blocked"
    upi_mpin_incorrect = "upi_mpin_incorrect"
    netbanking_down = "netbanking_down"
    vpa_invalid = "vpa_invalid"
    threeds_failure = "3ds_failure"
    unknown = "unknown"


class RecoveryStrategy(str, enum.Enum):
    retry_same_method = "retry_same_method"
    suggest_alternate_method = "suggest_alternate_method"
    offer_emi = "offer_emi"
    offer_partial_payment = "offer_partial_payment"
    delay_and_retry = "delay_and_retry"
    escalate_to_human = "escalate_to_human"


class RecoveryRun(Base):
    __tablename__ = "recovery_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One recovery run per payment_id — duplicate webhooks must not double-act
    payment_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_error_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    failure_type: Mapped[FailureType | None] = mapped_column(Enum(FailureType), nullable=True)
    failure_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy: Mapped[RecoveryStrategy | None] = mapped_column(Enum(RecoveryStrategy), nullable=True)
    status: Mapped[RecoveryStatus] = mapped_column(
        Enum(RecoveryStatus), default=RecoveryStatus.pending, index=True
    )

    # Full LangGraph trace for Agent Trace View
    agent_trace: Mapped[dict] = mapped_column(JSONB, default=dict)

    customer_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    strategy_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    drafted_message: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"
    __table_args__ = (
        UniqueConstraint("strategy", "failure_type", name="uq_strategy_failure"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy: Mapped[RecoveryStrategy] = mapped_column(Enum(RecoveryStrategy), index=True)
    failure_type: Mapped[FailureType] = mapped_column(Enum(FailureType), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SimulatedOutcome(Base):
    """Stores simulated recovery outcomes until live retry webhooks exist."""

    __tablename__ = "simulated_outcomes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    method_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time_to_recovery_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strategy_used: Mapped[RecoveryStrategy | None] = mapped_column(Enum(RecoveryStrategy), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
