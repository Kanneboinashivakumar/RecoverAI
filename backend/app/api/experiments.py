"""
Experiments API Router.

Lists past experiments and triggers new experiment runs.
POST /run uses a synchronous def (not async def) so FastAPI's threadpool
handles the 30-60s blocking operation without blocking the event loop.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.tables import Experiment, PolicyType

logger = logging.getLogger("recoverai.experiments")

router = APIRouter()


class ExperimentRow(BaseModel):
    id: str
    seed: int
    batch_size: int
    policy_type: str
    total_recovered: Optional[float] = None
    recovery_rate: Optional[float] = None
    incremental_recovered: Optional[float] = None
    run_at: Optional[str] = None


class ExperimentPair(BaseModel):
    seed: int
    batch_size: int
    baseline: Optional[ExperimentRow] = None
    recoverai: Optional[ExperimentRow] = None
    net_incremental: Optional[float] = None
    run_at: Optional[str] = None


class ExperimentListResponse(BaseModel):
    experiments: List[ExperimentPair]


class RunExperimentRequest(BaseModel):
    seed: int = Field(42, description="Random seed for deterministic experiment")
    count: int = Field(500, ge=10, le=5000, description="Number of transactions to evaluate")


class RunExperimentResponse(BaseModel):
    seed: int
    count: int
    baseline_recovered: float
    recoverai_recovered: float
    net_incremental: float
    recovery_rate_baseline: float
    recovery_rate_recoverai: float


@router.get("", response_model=ExperimentListResponse)
def list_experiments(db: Session = Depends(get_db)):
    """Lists all experiment runs, paired by seed (baseline + recoverai)."""
    all_exps = (
        db.query(Experiment)
        .order_by(Experiment.run_at.desc())
        .all()
    )

    # Group by (seed, batch_size, approximate run_at)
    pairs: Dict[int, ExperimentPair] = {}
    for exp in all_exps:
        key = exp.seed
        if key not in pairs:
            pairs[key] = ExperimentPair(seed=exp.seed, batch_size=exp.batch_size)

        row = ExperimentRow(
            id=str(exp.id),
            seed=exp.seed,
            batch_size=exp.batch_size,
            policy_type=exp.policy_type.value if hasattr(exp.policy_type, 'value') else str(exp.policy_type),
            total_recovered=float(exp.total_recovered) if exp.total_recovered else None,
            recovery_rate=exp.recovery_rate,
            incremental_recovered=float(exp.incremental_recovered) if exp.incremental_recovered else None,
            run_at=exp.run_at.isoformat() if exp.run_at else None,
        )

        pt = exp.policy_type.value if hasattr(exp.policy_type, 'value') else str(exp.policy_type)
        if pt == "baseline":
            pairs[key].baseline = row
        elif pt == "recoverai":
            pairs[key].recoverai = row
            pairs[key].net_incremental = row.incremental_recovered
            pairs[key].run_at = row.run_at

    return ExperimentListResponse(experiments=list(pairs.values()))


# This is a synchronous def (not async def) so FastAPI runs it in a threadpool,
# preventing the 30-60s experiment from blocking the event loop.
@router.post("/run", response_model=RunExperimentResponse)
def run_experiment_endpoint(
    req: RunExperimentRequest,
    db: Session = Depends(get_db),
):
    """Triggers a new A/B experiment run. Synchronous — takes 30-60s."""

    # Import run_experiment from scripts
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    try:
        from scripts.run_experiment import run_experiment
        base_res, rec_res, inc_net = run_experiment(
            seed=req.seed, count=req.count, save_db=True
        )
    except Exception as e:
        logger.error(f"Experiment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Experiment failed: {str(e)}")

    return RunExperimentResponse(
        seed=req.seed,
        count=req.count,
        baseline_recovered=float(base_res["net_recovered"]),
        recoverai_recovered=float(rec_res["net_recovered"]),
        net_incremental=float(inc_net),
        recovery_rate_baseline=base_res["recovery_rate"] * 100,
        recovery_rate_recoverai=rec_res["recovery_rate"] * 100,
    )
