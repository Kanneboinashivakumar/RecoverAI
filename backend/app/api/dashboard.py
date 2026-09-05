"""
Dashboard Overview API Router.

Primary KPI: Pulls incremental_recovered directly from the most recent
RecoverAI experiment row in the experiments table — the same net incremental
figure Phase 9 computes. Never recomputed from verification_results.

Secondary KPIs: Aggregated from full DB (total events, recovery rate,
escalation/blocked counts).
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tables import (
    AuditEvent,
    Experiment,
    PolicyType,
    RevenueEvent,
    Transaction,
    VerificationResult,
    VerificationOutcome,
)

logger = logging.getLogger("recoverai.dashboard")

router = APIRouter()


class TrendPoint(BaseModel):
    date: str
    events: int
    recovered: float


class FailureBreakdown(BaseModel):
    failure_code: str
    count: int


class OverviewResponse(BaseModel):
    # Primary KPI — from experiments table, NOT recomputed
    incremental_recovered: float
    incremental_recovered_label: str = "Simulated Net Incremental ₹ Recovered"
    experiment_seed: Optional[int] = None
    experiment_batch_size: Optional[int] = None
    experiment_run_at: Optional[str] = None

    # Secondary KPIs — aggregated from full DB
    total_events: int
    total_recovered: float  # gross recovered across all verification_results
    recovery_rate: float  # recovered / total events
    escalation_count: int
    blocked_count: int

    # Breakdowns
    failure_breakdown: List[FailureBreakdown]
    trend_data: List[TrendPoint]


@router.get("/overview", response_model=OverviewResponse)
def get_overview(db: Session = Depends(get_db)):
    """
    Returns the dashboard overview KPIs.

    Primary KPI sourced from the most recent RecoverAI experiment row's
    incremental_recovered — the exact same net incremental value Phase 9
    computes and stores. No secondary computation path.
    """

    # ---- Primary KPI: from experiments table ----
    latest_recoverai_exp = (
        db.query(Experiment)
        .filter(Experiment.policy_type == PolicyType.RECOVERAI)
        .order_by(Experiment.run_at.desc())
        .first()
    )

    if latest_recoverai_exp and latest_recoverai_exp.incremental_recovered is not None:
        incremental_recovered = float(latest_recoverai_exp.incremental_recovered)
        experiment_seed = latest_recoverai_exp.seed
        experiment_batch_size = latest_recoverai_exp.batch_size
        experiment_run_at = latest_recoverai_exp.run_at.isoformat() if latest_recoverai_exp.run_at else None
    else:
        # No experiment has been run yet
        incremental_recovered = 0.0
        experiment_seed = None
        experiment_batch_size = None
        experiment_run_at = None

    # ---- Secondary KPIs: full DB aggregation ----

    # Total events (matches Transaction Explorer total count)
    total_events = db.query(func.count(Transaction.id)).scalar() or 0

    # Gross recovered (sum of simulated_amount_recovered where outcome=success)
    total_recovered_dec = (
        db.query(func.sum(VerificationResult.simulated_amount_recovered))
        .filter(VerificationResult.outcome == VerificationOutcome.SUCCESS)
        .scalar()
    )
    total_recovered = float(total_recovered_dec) if total_recovered_dec else 0.0

    # Recovery rate
    total_verified = db.query(func.count(VerificationResult.id)).scalar() or 0
    successful_verified = (
        db.query(func.count(VerificationResult.id))
        .filter(VerificationResult.outcome == VerificationOutcome.SUCCESS)
        .scalar() or 0
    )
    recovery_rate = (successful_verified / total_verified * 100) if total_verified > 0 else 0.0

    # Escalation and blocked counts from unique transactions in audit_events (matches Recovery Queue)
    escalation_count = (
        db.query(func.count(func.distinct(AuditEvent.transaction_id)))
        .filter(
            AuditEvent.event_type == "POLICY_EVALUATED",
            AuditEvent.policy_result == "ESCALATED",
        )
        .scalar() or 0
    )

    blocked_count = (
        db.query(func.count(func.distinct(AuditEvent.transaction_id)))
        .filter(
            AuditEvent.event_type == "POLICY_EVALUATED",
            AuditEvent.policy_result == "BLOCKED",
        )
        .scalar() or 0
    )

    # ---- Failure breakdown ----
    failure_rows = (
        db.query(
            Transaction.failure_code,
            func.count(Transaction.id).label("count"),
        )
        .filter(Transaction.failure_code.isnot(None))
        .group_by(Transaction.failure_code)
        .order_by(func.count(Transaction.id).desc())
        .all()
    )
    failure_breakdown = [
        FailureBreakdown(failure_code=row[0], count=row[1])
        for row in failure_rows
    ]

    # ---- Trend data (daily aggregation) ----
    # Events per day from Transaction table
    event_trend = (
        db.query(
            cast(Transaction.created_at, Date).label("date"),
            func.count(Transaction.id).label("count"),
        )
        .group_by(cast(Transaction.created_at, Date))
        .order_by(cast(Transaction.created_at, Date))
        .all()
    )

    # Recovered per day: join VerificationResult on transaction_id
    recovered_trend = (
        db.query(
            cast(Transaction.created_at, Date).label("date"),
            func.sum(VerificationResult.simulated_amount_recovered).label("recovered"),
        )
        .join(VerificationResult, Transaction.id == VerificationResult.transaction_id)
        .filter(VerificationResult.outcome == VerificationOutcome.SUCCESS)
        .group_by(cast(Transaction.created_at, Date))
        .order_by(cast(Transaction.created_at, Date))
        .all()
    )
    recovered_map = {str(row[0]): float(row[1]) for row in recovered_trend if row[0]}

    trend_data = [
        TrendPoint(
            date=str(row[0]),
            events=row[1],
            recovered=recovered_map.get(str(row[0]), 0.0),
        )
        for row in event_trend
        if row[0]
    ]

    return OverviewResponse(
        incremental_recovered=incremental_recovered,
        experiment_seed=experiment_seed,
        experiment_batch_size=experiment_batch_size,
        experiment_run_at=experiment_run_at,
        total_events=total_events,
        total_recovered=total_recovered,
        recovery_rate=round(recovery_rate, 2),
        escalation_count=escalation_count,
        blocked_count=blocked_count,
        failure_breakdown=failure_breakdown,
        trend_data=trend_data,
    )
