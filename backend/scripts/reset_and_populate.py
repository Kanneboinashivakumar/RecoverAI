#!/usr/bin/env python3
"""
Clean Database Reset & Deterministic Population Script for Phase 12.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.tables import Policy
from app.engines.policy import DEFAULT_POLICY_CONFIG
from datetime import datetime, timezone
import uuid

def reset_database():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("=== 1. TRUNCATING ALL TABLES ===")
    tables = [
        "audit_events",
        "verification_results",
        "actions",
        "policy_evaluations",
        "decisions",
        "predictions",
        "diagnoses",
        "revenue_events",
        "transactions",
        "customers",
        "merchants",
        "experiments",
        "policies",
    ]
    for t in tables:
        session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
    session.commit()
    print("All tables truncated successfully.")

    # Insert default policy
    default_pol = Policy(
        id=uuid.uuid4(),
        name="default_recovery_policy",
        config=DEFAULT_POLICY_CONFIG,
        version=1,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(default_pol)
    session.commit()
    print("Default policy initialized at version 1.")
    session.close()

if __name__ == "__main__":
    reset_database()
