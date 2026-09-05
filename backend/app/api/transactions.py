"""
Transactions API Router.

Provides paginated, filterable transaction list and single-transaction detail
(Decision Receipt data). All data queried live from DB.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engines.audit import get_agent_replay
from app.models.tables import (
    Action,
    ActionStatus,
    AuditEvent,
    Customer,
    Decision,
    Diagnosis,
    Merchant,
    PolicyEvaluation,
    Prediction,
    Transaction,
    VerificationOutcome,
    VerificationResult,
)

logger = logging.getLogger("recoverai.transactions")

router = APIRouter()


# ---- Response Models ----

class TransactionSummary(BaseModel):
    id: str
    customer_id: str
    merchant_id: str
    amount: float
    currency: str
    payment_method: str
    status: str
    failure_code: Optional[str]
    created_at: str
    # Decision summary
    action_type: Optional[str] = None
    channel: Optional[str] = None
    policy_verdict: Optional[str] = None
    recovery_outcome: Optional[str] = None
    recovered_amount: Optional[float] = None


class TransactionListResponse(BaseModel):
    total_count: int
    items: List[TransactionSummary]


class PolicyCheckResult(BaseModel):
    check_name: str
    passed: bool
    reason_code: Optional[str] = None


class DecisionDetail(BaseModel):
    decision_id: str
    action_type: str
    channel: str
    delay_hours: int
    amount: float
    confidence_llm: Optional[float] = None
    expected_value_llm: Optional[float] = None
    expected_value_verified: Optional[float] = None
    reason_codes: Optional[List[str]] = None
    policy_context: Optional[Dict[str, Any]] = None
    created_at: str


class TransactionDetail(BaseModel):
    # Transaction
    id: str
    customer_id: str
    merchant_id: str
    amount: float
    currency: str
    payment_method: str
    status: str
    failure_code: Optional[str]
    created_at: str
    # Customer context
    customer_language: Optional[str] = None
    customer_channel: Optional[str] = None
    # Diagnosis
    diagnosis_source: Optional[str] = None
    diagnosis_confidence: Optional[float] = None
    diagnosis_reason_codes: Optional[List[str]] = None
    # Prediction
    recovery_probability: Optional[float] = None
    model_version: Optional[str] = None
    # Decision (LLM recommendation)
    decision: Optional[DecisionDetail] = None
    # Policy checks
    policy_verdict: Optional[str] = None
    policy_checks: List[PolicyCheckResult] = []
    # Execution & Verification
    action_status: Optional[str] = None
    verification_outcome: Optional[str] = None
    recovered_amount: Optional[float] = None


# ---- Endpoints ----

@router.get("", response_model=TransactionListResponse)
def list_transactions(
    payment_method: Optional[str] = Query(None, description="Filter by payment method: UPI, CARD, NETBANKING, MANDATE"),
    failure_code: Optional[str] = Query(None, description="Filter by failure code"),
    verdict: Optional[str] = Query(None, description="Filter by policy verdict: APPROVED, BLOCKED, ESCALATED"),
    amount_min: Optional[float] = Query(None, description="Min amount filter"),
    amount_max: Optional[float] = Query(None, description="Max amount filter"),
    search: Optional[str] = Query(None, description="Search by transaction ID prefix"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Paginated, filterable transaction list with decision/verdict summaries."""

    query = db.query(Transaction)

    # Apply filters
    if payment_method:
        query = query.filter(Transaction.payment_method == payment_method)
    if failure_code:
        query = query.filter(Transaction.failure_code == failure_code)
    if amount_min is not None:
        query = query.filter(Transaction.amount >= Decimal(str(amount_min)))
    if amount_max is not None:
        query = query.filter(Transaction.amount <= Decimal(str(amount_max)))
    if search:
        from sqlalchemy import String as SAString
        query = query.filter(Transaction.id.cast(SAString).ilike(f"{search}%"))

    total_count = query.count()

    transactions = (
        query.order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not transactions:
        return TransactionListResponse(total_count=total_count, items=[])

    tx_ids = [t.id for t in transactions]

    # Batch-fetch decisions
    decisions = (
        db.query(Decision)
        .filter(Decision.transaction_id.in_(tx_ids))
        .all()
    )
    decision_map: Dict[UUID, Decision] = {}
    for d in decisions:
        if d.transaction_id not in decision_map:
            decision_map[d.transaction_id] = d

    # Batch-fetch policy verdicts from audit_events
    policy_events = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.transaction_id.in_(tx_ids),
            AuditEvent.event_type == "POLICY_EVALUATED",
        )
        .order_by(AuditEvent.timestamp.desc())
        .all()
    )
    verdict_map: Dict[UUID, str] = {}
    for ev in policy_events:
        if ev.transaction_id not in verdict_map:
            verdict_map[ev.transaction_id] = ev.policy_result or "UNKNOWN"

    # Batch-fetch verification results
    verifications = (
        db.query(VerificationResult)
        .filter(VerificationResult.transaction_id.in_(tx_ids))
        .all()
    )
    verif_map: Dict[UUID, VerificationResult] = {}
    for v in verifications:
        if v.transaction_id not in verif_map:
            verif_map[v.transaction_id] = v

    items = []
    for tx in transactions:
        dec = decision_map.get(tx.id)
        ver = verif_map.get(tx.id)
        pv = verdict_map.get(tx.id)

        # Apply verdict filter if specified
        if verdict and pv != verdict:
            continue

        items.append(TransactionSummary(
            id=str(tx.id),
            customer_id=str(tx.customer_id),
            merchant_id=str(tx.merchant_id),
            amount=float(tx.amount),
            currency=tx.currency,
            payment_method=str(tx.payment_method.value) if hasattr(tx.payment_method, 'value') else str(tx.payment_method),
            status=tx.status,
            failure_code=tx.failure_code,
            created_at=tx.created_at.isoformat() if tx.created_at else "",
            action_type=dec.action_type if dec else None,
            channel=dec.channel if dec else None,
            policy_verdict=pv,
            recovery_outcome=ver.outcome.value if ver and hasattr(ver.outcome, 'value') else (str(ver.outcome) if ver else None),
            recovered_amount=float(ver.simulated_amount_recovered) if ver and ver.simulated_amount_recovered else None,
        ))

    # Adjust total if verdict filter applied post-query
    if verdict:
        total_count = len(items)
        items = items[offset:offset + limit] if offset > 0 else items[:limit]

    return TransactionListResponse(total_count=total_count, items=items)


@router.get("/{transaction_id}", response_model=TransactionDetail)
def get_transaction_detail(
    transaction_id: str,
    db: Session = Depends(get_db),
):
    """Full transaction detail for Decision Receipt display."""
    try:
        tx_uuid = UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {transaction_id}")

    tx = db.query(Transaction).filter(Transaction.id == tx_uuid).first()
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    # Customer
    customer = db.query(Customer).filter(Customer.id == tx.customer_id).first()

    # Diagnosis
    diagnosis = (
        db.query(Diagnosis)
        .filter(Diagnosis.transaction_id == tx_uuid)
        .order_by(Diagnosis.created_at.desc())
        .first()
    )

    # Prediction
    prediction = (
        db.query(Prediction)
        .filter(Prediction.transaction_id == tx_uuid)
        .order_by(Prediction.created_at.desc())
        .first()
    )

    # Decision
    decision = (
        db.query(Decision)
        .filter(Decision.transaction_id == tx_uuid)
        .order_by(Decision.created_at.desc())
        .first()
    )

    decision_detail = None
    if decision:
        decision_detail = DecisionDetail(
            decision_id=str(decision.id),
            action_type=decision.action_type,
            channel=decision.channel,
            delay_hours=decision.delay_hours,
            amount=float(decision.amount),
            confidence_llm=decision.confidence_llm,
            expected_value_llm=float(decision.expected_value_llm) if decision.expected_value_llm else None,
            expected_value_verified=float(decision.expected_value_verified) if decision.expected_value_verified else None,
            reason_codes=decision.reason_codes,
            policy_context=decision.policy_context,
            created_at=decision.created_at.isoformat() if decision.created_at else "",
        )

    # Policy checks
    policy_checks = []
    policy_verdict = None
    if decision:
        pe_rows = (
            db.query(PolicyEvaluation)
            .filter(PolicyEvaluation.decision_id == decision.id)
            .all()
        )
        for pe in pe_rows:
            policy_checks.append(PolicyCheckResult(
                check_name=pe.check_name,
                passed=pe.passed,
                reason_code=pe.reason_code or ("NA_NON_MANDATE" if pe.check_name == "mandate_compliance_check" else None),
            ))

        check_names = {pe.check_name for pe in pe_rows}
        if "mandate_compliance_check" not in check_names:
            policy_checks.append(PolicyCheckResult(
                check_name="mandate_compliance_check",
                passed=True,
                reason_code="NA_NON_MANDATE",
            ))

    # Get verdict from audit_events
    policy_event = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.transaction_id == tx_uuid,
            AuditEvent.event_type == "POLICY_EVALUATED",
        )
        .order_by(AuditEvent.timestamp.desc())
        .first()
    )
    if policy_event:
        policy_verdict = policy_event.policy_result

    # Action & Verification
    action = (
        db.query(Action)
        .filter(Action.transaction_id == tx_uuid)
        .first()
    )
    verification = (
        db.query(VerificationResult)
        .filter(VerificationResult.transaction_id == tx_uuid)
        .first()
    )

    return TransactionDetail(
        id=str(tx.id),
        customer_id=str(tx.customer_id),
        merchant_id=str(tx.merchant_id),
        amount=float(tx.amount),
        currency=tx.currency,
        payment_method=str(tx.payment_method.value) if hasattr(tx.payment_method, 'value') else str(tx.payment_method),
        status=tx.status,
        failure_code=tx.failure_code,
        created_at=tx.created_at.isoformat() if tx.created_at else "",
        customer_language=customer.preferred_language if customer else None,
        customer_channel=customer.preferred_channel if customer else None,
        diagnosis_source=diagnosis.source.value if diagnosis and hasattr(diagnosis.source, 'value') else (str(diagnosis.source) if diagnosis else None),
        diagnosis_confidence=diagnosis.confidence if diagnosis else None,
        diagnosis_reason_codes=diagnosis.reason_codes if diagnosis else None,
        recovery_probability=prediction.recovery_probability if prediction else None,
        model_version=prediction.model_version if prediction else None,
        decision=decision_detail,
        policy_verdict=policy_verdict,
        policy_checks=policy_checks,
        action_status=action.status.value if action and hasattr(action.status, 'value') else (str(action.status) if action else None),
        verification_outcome=verification.outcome.value if verification and hasattr(verification.outcome, 'value') else (str(verification.outcome) if verification else None),
        recovered_amount=float(verification.simulated_amount_recovered) if verification and verification.simulated_amount_recovered else None,
    )
