import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.tables import Action, Transaction, VerificationOutcome, VerificationResult
from scripts.simulator import hidden_outcome_function


def verify_action_outcome(
    action_id: UUID,
    transaction_id: UUID,
    action_type: str,
    amount: Decimal,
    customer_reliability: float,
    failure_code: str,
    payment_method: str,
    hours_since_failure: float = 2.0,
    policy_context: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
    seed: Optional[int] = None,
) -> VerificationResult:
    """
    Resolves the actual post-intervention outcome using Phase 2's hidden simulator function.

    Single Source of Truth: Neither the ML model nor the policy engine can see this outcome
    until verification runs. The simulator alone decides if the customer pays.
    """
    if policy_context is None:
        policy_context = {}

    # 1. Call the hidden outcome function from Phase 2 simulator
    true_prob = hidden_outcome_function(
        customer_reliability=customer_reliability,
        failure_code=failure_code,
        payment_method=payment_method,
        hours_since_failure=hours_since_failure,
        action_type=action_type.upper(),
    )

    # 2. Resolve binary outcome via RNG against true simulator probability
    rng = random.Random(seed) if seed is not None else random.Random()
    is_recovered = rng.random() < true_prob

    # 3. Calculate simulated recovered amount
    if is_recovered:
        if action_type.upper() == "DISCOUNT":
            disc_rate = Decimal(str(policy_context.get("discount_pct", 0.10)))
            simulated_amount_recovered = round(amount * (Decimal("1.00") - disc_rate), 2)
        else:
            simulated_amount_recovered = amount
        outcome = VerificationOutcome.SUCCESS
    else:
        simulated_amount_recovered = Decimal("0.00")
        outcome = VerificationOutcome.FAILURE

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # 4. Record to verification_results table
    res = VerificationResult(
        id=uuid.uuid4(),
        transaction_id=transaction_id,
        action_id=action_id,
        outcome=outcome,
        simulated_amount_recovered=simulated_amount_recovered,
        verified_at=now_utc,
    )

    if db is not None:
        db.add(res)
        if is_recovered:
            # Update transaction status
            tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
            if tx:
                tx.status = "recovered"
        db.commit()

    return res
