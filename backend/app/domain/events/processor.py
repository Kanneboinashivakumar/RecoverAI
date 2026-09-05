import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.domain.events.normalizer import normalize_event
from app.domain.events.schema import NormalizedRevenueEvent
from app.engines.risk import RiskScore, score_risk
from app.models.tables import Customer, RevenueEvent


class EventProcessingResult(BaseModel):
    """Result of event bus processing with idempotency status."""
    external_event_id: str
    is_duplicate: bool
    processed: bool
    status: str = Field(..., description="'processed' or 'duplicate_ignored'")
    risk_score: Optional[RiskScore] = None
    message: str = ""


def process_revenue_event(
    raw_event: Any,
    db: Session,
) -> EventProcessingResult:
    """
    Main event bus ingestion function.

    1. Normalizes the event into standard NormalizedRevenueEvent.
    2. Enforces idempotency via external_event_id check.
    3. Deterministically computes risk score.
    4. Persists new event to revenue_events table.
    """
    event: NormalizedRevenueEvent = normalize_event(raw_event)

    # Idempotency check: check if external_event_id already exists
    existing = (
        db.query(RevenueEvent)
        .filter(RevenueEvent.external_event_id == event.external_event_id)
        .first()
    )
    if existing:
        return EventProcessingResult(
            external_event_id=event.external_event_id,
            is_duplicate=True,
            processed=False,
            status="duplicate_ignored",
            message=f"Duplicate external_event_id '{event.external_event_id}' detected. Event ignored.",
        )

    # Fetch customer context for risk scoring
    customer = (
        db.query(Customer)
        .filter(Customer.id == event.customer_id)
        .first()
    )

    # Deterministic risk evaluation
    risk_result = score_risk(event, customer=customer)

    # Persist normalized event to database
    db_event = RevenueEvent(
        id=uuid.uuid4(),
        external_event_id=event.external_event_id,
        event_type=event.event_type,
        customer_id=event.customer_id,
        merchant_id=event.merchant_id,
        transaction_id=event.transaction_id,
        amount=event.amount,
        currency=event.currency,
        timestamp=event.timestamp,
        source=event.source,
        metadata_=event.metadata,
        processed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(db_event)
    db.commit()

    return EventProcessingResult(
        external_event_id=event.external_event_id,
        is_duplicate=False,
        processed=True,
        status="processed",
        risk_score=risk_result,
        message=f"Event '{event.external_event_id}' successfully normalized, evaluated, and stored.",
    )
