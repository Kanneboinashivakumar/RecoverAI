"""
Policy & Recovery Queue API Router.

Deliverables (Phase 10):
1. GET /api/policies/recovery-queue:
   Returns all ESCALATED and BLOCKED transactions with their exact, un-truncated
   reason codes directly from Policy Engine audit logs.
   Clearly distinguishes ESCALATED (routine human review path) from BLOCKED
   (guardrail override path where is_override=True).

2. POST /api/policies/recovery-queue/{transaction_id}/review:
   Allows a human reviewer to mark a queued transaction as APPROVED or REJECTED.
   Forensically writes to audit_events (event_type=HUMAN_REVIEW_DECIDED) to preserve
   the end-to-end replay trail.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engines.audit import log_audit_event
from app.models.tables import AuditEvent, Decision, PolicyEvaluation, Transaction

logger = logging.getLogger("recoverai.recovery_queue")

router = APIRouter()


class ReviewVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class HumanReviewRequest(BaseModel):
    verdict: ReviewVerdict = Field(..., description="Human review verdict: APPROVED or REJECTED")
    reviewer: str = Field(..., min_length=1, description="Identifier of the human reviewer / ops analyst")
    notes: Optional[str] = Field(None, description="Optional explanation or justification for the review decision")


class RecoveryQueueItem(BaseModel):
    transaction_id: str
    decision_id: Optional[str] = None
    amount: Decimal
    currency: str = "INR"
    payment_method: str
    failure_code: str
    action_type: str
    channel: str
    original_verdict: str           # ESCALATED or BLOCKED
    is_override: bool               # True if BLOCKED (approving means deliberately overriding a fired guardrail)
    reason_codes: List[str]         # Exact reason codes passed from Policy Engine
    review_status: str              # PENDING_REVIEW, APPROVED, REJECTED
    confidence: Optional[float] = None
    expected_value: Optional[Decimal] = None
    evaluated_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewer: Optional[str] = None
    reviewer_notes: Optional[str] = None


class RecoveryQueueResponse(BaseModel):
    total_count: int
    pending_count: int
    approved_count: int
    rejected_count: int
    items: List[RecoveryQueueItem]


@router.get("/recovery-queue", response_model=RecoveryQueueResponse)
def get_recovery_queue(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING_REVIEW, APPROVED, REJECTED"),
    verdict_filter: Optional[str] = Query(None, alias="verdict", description="Filter by original verdict: ESCALATED, BLOCKED"),
    limit: int = Query(50, ge=1, le=1000, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    """
    Returns queryable list of transactions that were BLOCKED or ESCALATED by the Policy Engine.
    Preserves exact reason codes and tracks human review status via audit_events.
    """
    # 1. Fetch all policy evaluation audit events for ESCALATED and BLOCKED
    policy_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.event_type == "POLICY_EVALUATED",
            AuditEvent.policy_result.in_(["ESCALATED", "BLOCKED"]),
        )
        .order_by(AuditEvent.timestamp.desc())
        .all()
    )

    # Deduplicate by transaction_id (keeping latest policy evaluation)
    seen_tx = set()
    latest_policy_events: List[AuditEvent] = []
    for ev in policy_events:
        if ev.transaction_id not in seen_tx:
            seen_tx.add(ev.transaction_id)
            latest_policy_events.append(ev)

    if not latest_policy_events:
        return RecoveryQueueResponse(
            total_count=0,
            pending_count=0,
            approved_count=0,
            rejected_count=0,
            items=[],
        )

    tx_ids = [ev.transaction_id for ev in latest_policy_events]

    # 2. Fetch any corresponding human review audit events
    review_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.transaction_id.in_(tx_ids),
            AuditEvent.event_type == "HUMAN_REVIEW_DECIDED",
        )
        .order_by(AuditEvent.timestamp.desc())
        .all()
    )
    latest_reviews: Dict[UUID, AuditEvent] = {}
    for rev in review_events:
        if rev.transaction_id not in latest_reviews:
            latest_reviews[rev.transaction_id] = rev

    # 3. Fetch Transaction and Decision details
    transactions_map = {
        tx.id: tx
        for tx in db.query(Transaction).filter(Transaction.id.in_(tx_ids)).all()
    }
    decisions_list = (
        db.query(Decision)
        .filter(Decision.transaction_id.in_(tx_ids))
        .order_by(Decision.created_at.desc())
        .all()
    )
    decisions_map: Dict[UUID, Decision] = {}
    for d in decisions_list:
        if d.transaction_id not in decisions_map:
            decisions_map[d.transaction_id] = d

    # 4. Construct queue items
    all_items: List[RecoveryQueueItem] = []
    pending_count = 0
    approved_count = 0
    rejected_count = 0

    for ev in latest_policy_events:
        tx = transactions_map.get(ev.transaction_id)
        decision = decisions_map.get(ev.transaction_id)
        rev = latest_reviews.get(ev.transaction_id)

        # Review status
        if rev is not None:
            review_status = rev.policy_result or "PENDING_REVIEW"
            reviewed_at = rev.timestamp
            rev_snapshot = rev.output_snapshot or {}
            reviewer = rev_snapshot.get("reviewer")
            reviewer_notes = rev_snapshot.get("notes")
        else:
            review_status = "PENDING_REVIEW"
            reviewed_at = None
            reviewer = None
            reviewer_notes = None

        if review_status == "PENDING_REVIEW":
            pending_count += 1
        elif review_status == "APPROVED":
            approved_count += 1
        elif review_status == "REJECTED":
            rejected_count += 1

        original_verdict = ev.policy_result or "ESCALATED"
        is_override = (original_verdict == "BLOCKED")

        # Details from Transaction / Decision / Event
        amount = tx.amount if tx else Decimal(str(ev.input_snapshot.get("amount", 0)))
        currency = tx.currency if tx else "INR"
        payment_method = tx.payment_method if tx else (decision.channel if decision else "UPI")
        failure_code = tx.failure_code if (tx and tx.failure_code) else "UNKNOWN_FAILURE"
        action_type = decision.action_type if decision else str(ev.input_snapshot.get("action", "ESCALATE"))
        channel = decision.channel if decision else str(ev.input_snapshot.get("channel", payment_method))
        confidence = decision.confidence_llm if decision else None
        expected_value = decision.expected_value_verified if decision else None
        reason_codes = ev.reason_codes if ev.reason_codes else []

        item = RecoveryQueueItem(
            transaction_id=str(ev.transaction_id),
            decision_id=str(decision.id) if decision else None,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            failure_code=failure_code,
            action_type=action_type,
            channel=channel,
            original_verdict=original_verdict,
            is_override=is_override,
            reason_codes=reason_codes,
            review_status=review_status,
            confidence=confidence,
            expected_value=expected_value,
            evaluated_at=ev.timestamp,
            reviewed_at=reviewed_at,
            reviewer=reviewer,
            reviewer_notes=reviewer_notes,
        )
        all_items.append(item)

    # 5. Apply filters
    filtered_items = all_items
    if status_filter:
        filtered_items = [it for it in filtered_items if it.review_status.upper() == status_filter.upper()]
    if verdict_filter:
        filtered_items = [it for it in filtered_items if it.original_verdict.upper() == verdict_filter.upper()]

    total_filtered = len(filtered_items)
    paginated_items = filtered_items[offset : offset + limit]

    return RecoveryQueueResponse(
        total_count=total_filtered,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        items=paginated_items,
    )


@router.post("/recovery-queue/{transaction_id}/review", response_model=RecoveryQueueItem)
def review_queue_item(
    transaction_id: str,
    request: HumanReviewRequest,
    db: Session = Depends(get_db),
):
    """
    Manually resolves an ESCALATED or BLOCKED item in the Recovery Queue.
    Logs the resolution action to audit_events (HUMAN_REVIEW_DECIDED).
    If original verdict was BLOCKED, an APPROVED verdict represents a deliberate policy override.
    """
    try:
        tx_uuid = UUID(transaction_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID string format: {transaction_id}",
        )

    # 1. Verify that this transaction was actually routed to escalation or blocked
    latest_policy_event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.transaction_id == tx_uuid,
            AuditEvent.event_type == "POLICY_EVALUATED",
            AuditEvent.policy_result.in_(["ESCALATED", "BLOCKED"]),
        )
        .order_by(AuditEvent.timestamp.desc())
        .first()
    )

    if not latest_policy_event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction {transaction_id} is not present in the recovery escalation queue.",
        )

    original_verdict = latest_policy_event.policy_result
    is_override = (original_verdict == "BLOCKED")

    # 2. Check if this transaction has already been reviewed
    existing_review = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.transaction_id == tx_uuid,
            AuditEvent.event_type == "HUMAN_REVIEW_DECIDED",
        )
        .order_by(AuditEvent.timestamp.desc())
        .first()
    )

    review_reason_codes = [f"HUMAN_{request.verdict.value}"]
    if is_override:
        review_reason_codes.append("POLICY_GUARDRAIL_OVERRIDE" if request.verdict == ReviewVerdict.APPROVED else "POLICY_GUARDRAIL_UPHELD")
    else:
        review_reason_codes.append("HUMAN_ESCALATION_RESOLVED")

    # 3. Log to audit_events
    log_audit_event(
        transaction_id=tx_uuid,
        event_type="HUMAN_REVIEW_DECIDED",
        actor=f"human_reviewer:{request.reviewer}",
        input_snapshot={
            "transaction_id": str(tx_uuid),
            "original_policy_verdict": original_verdict,
            "is_override_action": is_override,
            "policy_reason_codes": latest_policy_event.reason_codes,
        },
        output_snapshot={
            "review_verdict": request.verdict.value,
            "reviewer": request.reviewer,
            "notes": request.notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        },
        reason_codes=review_reason_codes,
        policy_result=request.verdict.value,
        db=db,
    )

    # 4. Return updated item
    tx = db.query(Transaction).filter(Transaction.id == tx_uuid).first()
    decision = (
        db.query(Decision)
        .filter(Decision.transaction_id == tx_uuid)
        .order_by(Decision.created_at.desc())
        .first()
    )

    return RecoveryQueueItem(
        transaction_id=str(tx_uuid),
        decision_id=str(decision.id) if decision else None,
        amount=tx.amount if tx else Decimal(str(latest_policy_event.input_snapshot.get("amount", 0))),
        currency=tx.currency if tx else "INR",
        payment_method=tx.payment_method if tx else (decision.channel if decision else "UPI"),
        failure_code=tx.failure_code if (tx and tx.failure_code) else "UNKNOWN_FAILURE",
        action_type=decision.action_type if decision else str(latest_policy_event.input_snapshot.get("action", "ESCALATE")),
        channel=decision.channel if decision else str(latest_policy_event.input_snapshot.get("channel", "EMAIL")),
        original_verdict=original_verdict,
        is_override=is_override,
        reason_codes=latest_policy_event.reason_codes or [],
        review_status=request.verdict.value,
        confidence=decision.confidence_llm if decision else None,
        expected_value=decision.expected_value_verified if decision else None,
        evaluated_at=latest_policy_event.timestamp,
        reviewed_at=datetime.now(timezone.utc),
        reviewer=request.reviewer,
        reviewer_notes=request.notes,
    )
