import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.tables import AuditEvent


def _json_safe(obj: Any) -> Any:
    """Recursively converts Decimal, UUID, datetime, etc. to JSON serializable primitives."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return obj


def log_audit_event(
    transaction_id: UUID,
    event_type: str,
    actor: str,
    input_snapshot: Optional[Dict[str, Any]] = None,
    output_snapshot: Optional[Dict[str, Any]] = None,
    reason_codes: Optional[List[str]] = None,
    policy_result: Optional[str] = None,
    db: Optional[Session] = None,
) -> AuditEvent:
    """
    Logs an immutable forensic audit event for a transaction at each pipeline stage.
    """
    safe_input = _json_safe(input_snapshot) if input_snapshot else {}
    safe_output = _json_safe(output_snapshot) if output_snapshot else {}
    safe_reasons = _json_safe(reason_codes) if reason_codes else []

    event = AuditEvent(
        id=uuid.uuid4(),
        transaction_id=transaction_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        actor=actor,
        input_snapshot=safe_input,
        output_snapshot=safe_output,
        reason_codes=safe_reasons,
        policy_result=policy_result,
    )

    if db is not None:
        db.add(event)
        db.commit()

    return event


def get_agent_replay(
    transaction_id: UUID,
    db: Session,
) -> List[Dict[str, Any]]:
    """
    Agent Replay query function.
    Reconstructs the complete lifecycle timeline of a transaction
    PURELY from audit_events rows, in strict chronological order.
    No other table is queried or required.
    """
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.transaction_id == transaction_id)
        .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
        .all()
    )

    timeline = []
    for idx, ev in enumerate(events, 1):
        timeline.append({
            "step": idx,
            "event_id": str(ev.id),
            "event_type": ev.event_type,
            "timestamp": ev.timestamp.isoformat(),
            "actor": ev.actor,
            "input_snapshot": ev.input_snapshot,
            "output_snapshot": ev.output_snapshot,
            "reason_codes": ev.reason_codes or [],
            "policy_result": ev.policy_result,
        })

    return timeline
