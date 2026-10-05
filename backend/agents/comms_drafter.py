"""Agent 4 — Communication Drafter.

At most ONE Gemini call per recovery (strategy is rules-only).
Template fallback on missing key, LLM_DRAFT_ENABLED=false, or any API error (incl. 429).
Never sleeps / retries — fail open instantly for p99.
"""

from __future__ import annotations

from typing import Any

from config import get_settings
from llm.gemini_client import generate_json
from models.schemas import CustomerPaymentProfile, DraftedMessage, FailureType, StrategyDecision


def _paise_to_inr(amount_paise: int) -> str:
    rupees = amount_paise / 100
    if rupees >= 1000:
        return f"₹{rupees:,.2f}"
    return f"₹{rupees:.2f}"


def _failure_plain_english(failure_type: FailureType) -> str:
    mapping = {
        FailureType.insufficient_funds: "there weren't enough funds in the account",
        FailureType.wrong_otp: "the OTP didn't match",
        FailureType.bank_timeout: "the bank took too long to respond",
        FailureType.card_blocked: "the card appears temporarily blocked",
        FailureType.upi_mpin_incorrect: "the UPI MPIN didn't match",
        FailureType.netbanking_down: "netbanking looks temporarily unavailable",
        FailureType.vpa_invalid: "the UPI ID looks invalid",
        FailureType.threeds_failure: "card authentication (3D Secure) didn't complete",
        FailureType.unknown: "the payment couldn't be completed",
    }
    return mapping.get(failure_type, "the payment couldn't be completed")


def _template_draft(
    *,
    customer_name: str,
    merchant_name: str,
    amount_paise: int,
    failure_type: FailureType,
    decision: StrategyDecision,
    payment_id: str,
) -> DraftedMessage:
    amount = _paise_to_inr(amount_paise)
    reason = _failure_plain_english(failure_type)
    params = decision.personalization_params
    suggested = params.get("suggested_method", "UPI")

    if decision.strategy.value == "suggest_alternate_method":
        body = (
            f"Hi {customer_name}, your {amount} payment to {merchant_name} couldn't go through — "
            f"{reason}. You can complete it in one tap with {str(suggested).upper()}. "
            f"[Pay via {str(suggested).upper()} →]"
        )
        cta = f"Pay via {str(suggested).upper()}"
    elif decision.strategy.value == "offer_emi":
        body = (
            f"Hi {customer_name}, your {amount} payment to {merchant_name} failed ({reason}). "
            f"Split it into easy EMIs and finish checkout without stressing your balance. [View EMI options →]"
        )
        cta = "View EMI options"
    elif decision.strategy.value == "offer_partial_payment":
        body = (
            f"Hi {customer_name}, we couldn't collect the full {amount} for {merchant_name} "
            f"because {reason}. Pay 50% now and the rest later to secure your order. [Pay partial →]"
        )
        cta = "Pay partial now"
    elif decision.strategy.value == "delay_and_retry":
        hours = params.get("wait_hours", 4)
        body = (
            f"Hi {customer_name}, your {amount} payment to {merchant_name} hit a temporary bank issue. "
            f"We'll retry automatically in about {hours} hours — no action needed. "
            f"Or pay now if you're ready. [Pay now →]"
        )
        cta = "Pay now"
    elif decision.strategy.value == "escalate_to_human":
        body = (
            f"Hi {customer_name}, we're still unable to complete your {amount} payment to {merchant_name}. "
            f"A support specialist will help you finish this securely. [Talk to support →]"
        )
        cta = "Talk to support"
    else:
        body = (
            f"Hi {customer_name}, your {amount} payment to {merchant_name} couldn't go through — {reason}. "
            f"Please retry once when ready. [Retry payment →]"
        )
        cta = "Retry payment"

    cta_url = (
        f"https://pay.example.com/recover/{payment_id}"
        f"?utm_source=reviveagent&utm_medium={decision.channel}&utm_campaign={decision.strategy.value}"
    )
    subject = f"Complete your {amount} payment to {merchant_name}"
    return DraftedMessage(
        channel=decision.channel,
        subject=subject if decision.channel == "email" else None,
        body=body,
        cta_text=cta,
        cta_url=cta_url,
        utm_tagged=True,
    )


def draft_communication(
    *,
    customer_name: str | None,
    merchant_name: str | None,
    amount_paise: int,
    failure_type: FailureType,
    decision: StrategyDecision,
    profile: CustomerPaymentProfile,
    payment_id: str,
    use_llm: bool | None = None,
) -> DraftedMessage:
    name = customer_name or "there"
    merchant = merchant_name or "the merchant"
    fallback = _template_draft(
        customer_name=name,
        merchant_name=merchant,
        amount_paise=amount_paise,
        failure_type=failure_type,
        decision=decision,
        payment_id=payment_id,
    )

    settings = get_settings()
    allow_llm = settings.llm_draft_enabled if use_llm is None else use_llm
    if not allow_llm or settings.llm_provider == "rules":
        return fallback

    prompt = f"""You are an expert Indian fintech growth copywriter for payment recovery.
Write a short personalized {decision.channel} message (WhatsApp-style if whatsapp/sms).
Constraints:
- Use ₹ amounts correctly
- Mention the failure in plain English (no raw error codes)
- Include a clear CTA matching strategy={decision.strategy.value}
- Warm, trustworthy, not spammy; max 3 short sentences in body
- Return JSON only with keys: subject (string|null), body, cta_text

Customer name: {name}
Merchant: {merchant}
Amount paise: {amount_paise} (= {_paise_to_inr(amount_paise)})
Failure: {failure_type.value} ({_failure_plain_english(failure_type)})
Strategy: {decision.strategy.value}
Channel: {decision.channel}
Params: {decision.personalization_params}
Preferred method: {profile.preferred_method}
Strategy reasoning (context only — do not invent a new strategy): {decision.reasoning}
"""
    data: dict[str, Any] = generate_json(
        prompt,
        fallback={
            "subject": fallback.subject,
            "body": fallback.body,
            "cta_text": fallback.cta_text,
        },
    )

    cta_url = (
        f"https://pay.example.com/recover/{payment_id}"
        f"?utm_source=reviveagent&utm_medium={decision.channel}&utm_campaign={decision.strategy.value}"
    )
    return DraftedMessage(
        channel=decision.channel,
        subject=data.get("subject") or fallback.subject,
        body=str(data.get("body") or fallback.body),
        cta_text=str(data.get("cta_text") or fallback.cta_text),
        cta_url=cta_url,
        utm_tagged=True,
    )
