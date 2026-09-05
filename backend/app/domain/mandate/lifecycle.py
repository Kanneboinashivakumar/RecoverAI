"""
Mandate Lifecycle Trace Helper.

Reconstructs and records the step-by-step state machine progression
for a UPI AutoPay mandate from creation through debit failure and retry/escalation.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.domain.mandate.models import MandateState, MandateLifecycleEvent
from app.domain.mandate.state_machine import evaluate_mandate_eligibility, transition_mandate_state


def trace_mandate_lifecycle(
    transaction_id: str,
    failure_code: str,
    amount: float,
    prior_retry_count: int = 0,
    delay_hours: int = 0,
    base_time: Optional[datetime] = None,
) -> List[MandateLifecycleEvent]:
    """
    Generates a full chronological state-machine lifecycle trace for a mandate failure transaction.
    Demonstrates:
    Created -> Active -> Debit Attempt -> Failure -> Retry Eligibility -> Retry Window -> Success/Escalation.
    """
    if base_time is None:
        base_time = datetime.now(timezone.utc)

    events: List[MandateLifecycleEvent] = []
    step = 1

    def record_step(
        from_st: MandateState,
        to_st: MandateState,
        ev_name: str,
        t_delta_minutes: int,
        actor: str,
        details: Dict[str, Any],
    ):
        nonlocal step
        timestamp = (base_time + timedelta(minutes=t_delta_minutes)).isoformat()
        events.append(
            MandateLifecycleEvent(
                step=step,
                from_state=from_st,
                to_state=to_st,
                event_name=ev_name,
                timestamp=timestamp,
                actor=actor,
                details=details,
            )
        )
        step += 1

    # Stage 1: Mandate Creation
    record_step(
        from_st=MandateState.CREATED,
        to_st=MandateState.ACTIVE,
        ev_name="MANDATE_REGISTERED_AND_ACTIVE",
        t_delta_minutes=0,
        actor="npci_autopay_gateway",
        details={
            "transaction_id": transaction_id,
            "max_amount": amount,
            "frequency": "MONTHLY",
            "status": "ACTIVE",
        },
    )

    # Stage 2: Scheduled Debit Attempt
    record_step(
        from_st=MandateState.ACTIVE,
        to_st=MandateState.DEBIT_ATTEMPTED,
        ev_name="SCHEDULED_DEBIT_TRIGGERED",
        t_delta_minutes=120,
        actor="mandate_scheduler",
        details={
            "debit_amount": amount,
            "pre_debit_notification_sent": True,
            "attempt_number": 1,
        },
    )

    # Stage 3: Debit Failure
    is_terminal = failure_code in ("MANDATE_REVOKED", "MANDATE_EXPIRED", "UPI_MANDATE_EXPIRED", "MANDATE_REGISTRATION_FAILED")
    target_fail_state = MandateState.DEBIT_FAILED_TERMINAL if is_terminal else MandateState.DEBIT_FAILED_TRANSIENT

    record_step(
        from_st=MandateState.DEBIT_ATTEMPTED,
        to_st=target_fail_state,
        ev_name="DEBIT_EXECUTION_FAILED",
        t_delta_minutes=122,
        actor="issuing_bank_cbs",
        details={
            "failure_code": failure_code,
            "is_terminal": is_terminal,
            "bank_response": f"Debit rejected with code {failure_code}",
        },
    )

    # Stage 4: Retry Eligibility Evaluation under NPCI AutoPay circulars
    eligibility = evaluate_mandate_eligibility(
        payment_method="MANDATE",
        failure_code=failure_code,
        prior_retry_count=prior_retry_count,
        delay_hours=delay_hours,
    )

    record_step(
        from_st=target_fail_state,
        to_st=MandateState.RETRY_ELIGIBILITY_CHECK,
        ev_name="EVALUATE_NPCI_RETRY_ELIGIBILITY",
        t_delta_minutes=123,
        actor="mandate_policy_engine",
        details={
            "is_retry_eligible": eligibility.is_retry_eligible,
            "failure_category": eligibility.failure_category.value,
            "npci_rule": eligibility.npci_rule_reference,
            "allowed_actions": eligibility.allowed_actions,
            "prohibited_actions": eligibility.prohibited_actions,
        },
    )

    # Stage 5: Final Transition based on Eligibility
    record_step(
        from_st=MandateState.RETRY_ELIGIBILITY_CHECK,
        to_st=eligibility.mandate_state,
        ev_name=f"APPLY_STATE_{eligibility.mandate_state.value}",
        t_delta_minutes=125,
        actor="mandate_lifecycle_coordinator",
        details={
            "final_state": eligibility.mandate_state.value,
            "min_cooling_off_hours": eligibility.min_retry_delay_hours,
            "reason": eligibility.reason,
        },
    )

    return events
