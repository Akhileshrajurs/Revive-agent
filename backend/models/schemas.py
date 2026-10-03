from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FailureType(str, Enum):
    insufficient_funds = "insufficient_funds"
    wrong_otp = "wrong_otp"
    bank_timeout = "bank_timeout"
    card_blocked = "card_blocked"
    upi_mpin_incorrect = "upi_mpin_incorrect"
    netbanking_down = "netbanking_down"
    vpa_invalid = "vpa_invalid"
    threeds_failure = "3ds_failure"
    unknown = "unknown"


class RecoveryStrategy(str, Enum):
    retry_same_method = "retry_same_method"
    suggest_alternate_method = "suggest_alternate_method"
    offer_emi = "offer_emi"
    offer_partial_payment = "offer_partial_payment"
    delay_and_retry = "delay_and_retry"
    escalate_to_human = "escalate_to_human"


class RecoveryStatus(str, Enum):
    pending = "pending"
    classified = "classified"
    planned = "planned"
    messaged = "messaged"
    scheduled = "scheduled"
    recovered = "recovered"
    failed = "failed"
    escalated = "escalated"


class FailedPaymentIn(BaseModel):
    """Inbound failed payment event — mirrors Razorpay payment object fields we care about."""

    payment_id: str = Field(..., examples=["pay_test_abc123"])
    order_id: str | None = None
    customer_id: str | None = None
    amount_paise: int = Field(..., ge=1, description="Amount in paise (₹1 = 100)")
    currency: str = "INR"
    method: str | None = Field(None, description="upi | card | netbanking | wallet")
    error_code: str | None = None
    error_description: str | None = None
    error_source: str | None = None
    error_step: str | None = None
    error_reason: str | None = None
    customer_name: str | None = "Customer"
    merchant_name: str | None = "Merchant"
    email: str | None = None
    contact: str | None = None


class FailureClassification(BaseModel):
    failure_type: FailureType
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_error_code: str | None = None
    payment_method: str | None = None
    reasoning: str


class CustomerPaymentProfile(BaseModel):
    preferred_method: str | None = None
    success_rate_by_method: dict[str, float] = Field(default_factory=dict)
    best_retry_window: str | None = None
    risk_tier: str = "medium"
    prior_failures_24h: int = 0
    average_order_value_paise: int | None = None
    last_success_method: str | None = None


class StrategyDecision(BaseModel):
    strategy: RecoveryStrategy
    channel: str = Field(..., description="whatsapp | sms | email")
    timing_offset_minutes: int = 0
    personalization_params: dict[str, Any] = Field(default_factory=dict)
    reasoning: str


class DraftedMessage(BaseModel):
    channel: str
    subject: str | None = None
    body: str
    cta_text: str
    cta_url: str
    utm_tagged: bool = True


class RecoveryOutcome(BaseModel):
    success: bool
    method_used: str | None = None
    time_to_recovery_seconds: int | None = None
    strategy_used: RecoveryStrategy | None = None
    modelled_success_rate: float | None = None


class AgentTraceStep(BaseModel):
    agent: str
    status: str
    output: dict[str, Any]
    reasoning: str | None = None
    latency_ms: int | None = None


class RecoveryRunOut(BaseModel):
    id: UUID
    payment_id: str
    amount_paise: int
    currency: str
    payment_method: str | None
    failure_type: FailureType | None
    failure_confidence: float | None
    strategy: RecoveryStrategy | None
    status: RecoveryStatus
    agent_trace: dict[str, Any]
    customer_profile: dict[str, Any] | None = None
    strategy_decision: dict[str, Any] | None = None
    drafted_message: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClassifyResponse(BaseModel):
    """Full pipeline response including outcome for the learning loop."""

    run_id: UUID
    payment_id: str
    classification: FailureClassification
    status: RecoveryStatus
    customer_profile: CustomerPaymentProfile | None = None
    strategy_decision: StrategyDecision | None = None
    drafted_message: DraftedMessage | None = None
    outcome: RecoveryOutcome | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)


class StrategyPerformanceOut(BaseModel):
    strategy: RecoveryStrategy
    failure_type: FailureType
    attempts: int
    successes: int
    recovery_rate: float


class FunnelOut(BaseModel):
    failures: int
    attempted: int
    recovered: int
    escalated: int
    revenue_saved_paise: int
    by_failure_type: dict[str, int]
