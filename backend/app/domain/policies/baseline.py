"""
Baseline Recovery Policy.

Deliberately dumb fixed-rule policy:
    IF payment_failed: retry_after_24h

NON-NEGOTIABLE DESIGN CONSTRAINTS (per 01-GROUND-TRUTH.md & 13-phase-09-evaluation.md):
- Contains ZERO references to customer history (no lifetime_tx, no failure rate, no segment).
- Contains ZERO references to ML recovery probability.
- Contains ZERO references to Expected Value (EV) calculations.
- Contains ZERO policy guardrails (no retry limits, no amount tier ceilings, no anti-spam throttling).
- Simply emits a blind RETRY intervention after a fixed 24-hour delay.
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.engines.decision import ActionType, Channel, RecoveryAction


def get_baseline_action(
    transaction_id: str,
    amount: Decimal,
    channel: str = "UPI",
) -> RecoveryAction:
    """
    Fixed-rule dumb baseline recommendation.
    Blindly retries any failed payment 24 hours later, regardless of root cause or customer profile.
    """
    # Normalize channel to valid Channel enum if possible, default to UPI
    try:
        action_channel = Channel(channel.upper())
    except ValueError:
        action_channel = Channel.UPI

    return RecoveryAction(
        action_type=ActionType.RETRY,
        transaction_id=str(transaction_id),
        amount=amount,
        channel=action_channel,
        delay_hours=24,
        reason_codes=["BASELINE_FIXED_RULE_RETRY_24H"],
        confidence=0.0,
        expected_value=Decimal("0.00"),
        policy_context={},
    )
