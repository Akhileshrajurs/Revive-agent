"""Reproducible synthetic failed-payment batch.

Labeled `failure_type` is ground truth for strategy eval (isolates planner quality).
Amounts are paise (int). Seeded RNG — same --seed → same batch.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from models.schemas import FailureType

# India-checkout-ish mix (not uniform). Shares must sum to 1.0.
FAILURE_MIX: dict[FailureType, float] = {
    FailureType.insufficient_funds: 0.30,
    FailureType.bank_timeout: 0.18,
    FailureType.netbanking_down: 0.10,
    FailureType.wrong_otp: 0.10,
    FailureType.card_blocked: 0.08,
    FailureType.upi_mpin_incorrect: 0.07,
    FailureType.vpa_invalid: 0.05,
    FailureType.threeds_failure: 0.05,
    FailureType.unknown: 0.07,
}

_METHODS_BY_FAILURE: dict[FailureType, tuple[str, ...]] = {
    FailureType.insufficient_funds: ("card", "upi", "netbanking"),
    FailureType.bank_timeout: ("upi", "card", "netbanking"),
    FailureType.netbanking_down: ("netbanking",),
    FailureType.wrong_otp: ("card",),
    FailureType.card_blocked: ("card",),
    FailureType.upi_mpin_incorrect: ("upi",),
    FailureType.vpa_invalid: ("upi",),
    FailureType.threeds_failure: ("card",),
    FailureType.unknown: ("upi", "card", "wallet"),
}

_REASON_FOR_TYPE: dict[FailureType, str] = {
    FailureType.insufficient_funds: "insufficient_funds",
    FailureType.bank_timeout: "bank_timeout",
    FailureType.netbanking_down: "bank_not_available",
    FailureType.wrong_otp: "incorrect_otp",
    FailureType.card_blocked: "card_blocked",
    FailureType.upi_mpin_incorrect: "incorrect_mpin",
    FailureType.vpa_invalid: "invalid_vpa",
    FailureType.threeds_failure: "authentication_failed",
    FailureType.unknown: "unknown",
}


@dataclass(frozen=True)
class FailedEvent:
    payment_id: str
    customer_id: str
    amount_paise: int
    method: str
    failure_type: str
    error_reason: str
    prior_failures_24h: int
    retry_count: int

    def as_dict(self) -> dict:
        return asdict(self)


def _pick_type(rng: random.Random) -> FailureType:
    types = list(FAILURE_MIX.keys())
    weights = list(FAILURE_MIX.values())
    return rng.choices(types, weights=weights, k=1)[0]


def _amount_paise(rng: random.Random, failure: FailureType) -> int:
    """Ticket sizes that exercise EMI (≥ ₹3,000) and partial paths."""
    if failure == FailureType.insufficient_funds:
        # ~40% high-ticket so EMI vs partial is measurable
        if rng.random() < 0.40:
            return rng.randint(300_000, 1_250_000)  # ₹3k–₹12.5k
        return rng.randint(49_900, 299_900)
    if failure in {FailureType.card_blocked, FailureType.threeds_failure}:
        return rng.randint(99_900, 799_900)
    return rng.randint(29_900, 499_900)


def generate_batch(*, n: int = 2000, seed: int = 42) -> list[FailedEvent]:
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = random.Random(seed)
    events: list[FailedEvent] = []
    for i in range(n):
        ft = _pick_type(rng)
        methods = _METHODS_BY_FAILURE[ft]
        method = methods[rng.randrange(len(methods))]
        prior = rng.choices([0, 1, 2, 3, 4], weights=[55, 25, 12, 5, 3], k=1)[0]
        retry = 0 if prior == 0 else min(prior, rng.randint(0, 3))
        events.append(
            FailedEvent(
                payment_id=f"pay_eval_{seed}_{i:05d}",
                customer_id=f"cust_eval_{rng.randint(1, max(80, n // 8))}",
                amount_paise=_amount_paise(rng, ft),
                method=method,
                failure_type=ft.value,
                error_reason=_REASON_FOR_TYPE[ft],
                prior_failures_24h=prior,
                retry_count=retry,
            )
        )
    return events
