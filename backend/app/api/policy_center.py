"""
Policy Center API Router.

Read/write policy configuration and live policy evaluation trace.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engines.policy import DEFAULT_POLICY_CONFIG, load_policy_config
from app.models.tables import Policy

router = APIRouter()


class PolicyConfigResponse(BaseModel):
    config: Dict[str, Any]
    version: int


class PolicyConfigUpdate(BaseModel):
    config: Dict[str, Any]


@router.get("/config", response_model=PolicyConfigResponse)
def get_policy_config(db: Session = Depends(get_db)):
    """Returns current policy guardrail limits."""
    config = load_policy_config(db)
    policy_row = db.query(Policy).filter(Policy.name == "default_recovery_policy").first()
    version = policy_row.version if policy_row else 1
    return PolicyConfigResponse(config=config, version=version)


@router.put("/config", response_model=PolicyConfigResponse)
def update_policy_config(
    update: PolicyConfigUpdate,
    db: Session = Depends(get_db),
):
    """Updates policy configuration values. Merges with existing config."""
    policy_row = db.query(Policy).filter(Policy.name == "default_recovery_policy").first()

    if not policy_row:
        # Create if not exists
        current_config = dict(DEFAULT_POLICY_CONFIG)
        current_config.update(update.config)
        policy_row = Policy(
            id=uuid.uuid4(),
            name="default_recovery_policy",
            config=current_config,
            version=1,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(policy_row)
    else:
        # Merge update into existing
        current_config = dict(policy_row.config) if policy_row.config else dict(DEFAULT_POLICY_CONFIG)
        current_config.update(update.config)
        policy_row.config = current_config
        policy_row.version = (policy_row.version or 0) + 1
        policy_row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(policy_row)

    return PolicyConfigResponse(config=dict(policy_row.config), version=policy_row.version)
