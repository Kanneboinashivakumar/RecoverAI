"""
Agent Replay API Router.

Wraps the existing get_agent_replay() from audit.py as an HTTP endpoint.
Returns chronological audit_events timeline for a single transaction.
"""

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engines.audit import get_agent_replay

router = APIRouter()


@router.get("/{transaction_id}")
def get_replay(
    transaction_id: str,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Returns chronological audit_events timeline for one transaction."""
    try:
        tx_uuid = UUID(transaction_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {transaction_id}")

    timeline = get_agent_replay(tx_uuid, db)

    if not timeline:
        raise HTTPException(status_code=404, detail=f"No audit events found for transaction {transaction_id}")

    return timeline
