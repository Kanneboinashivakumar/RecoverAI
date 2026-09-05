import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import joblib
import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.tables import Prediction

ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "recovery_model.joblib")
METRICS_PATH = os.path.join(ARTIFACTS_DIR, "metrics.json")

_MODEL_PIPELINE = None
_MODEL_VERSION = None


def get_model_and_version():
    """Lazily loads the model pipeline and reads dynamic model_version from metrics.json."""
    global _MODEL_PIPELINE, _MODEL_VERSION

    if _MODEL_PIPELINE is None:
        if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
            raise FileNotFoundError(
                f"Trained model artifacts not found at {ARTIFACTS_DIR}. "
                "Run `python scripts/train_model.py` first."
            )
        _MODEL_PIPELINE = joblib.load(MODEL_PATH)
        with open(METRICS_PATH, "r") as f:
            metrics_data = json.load(f)
            _MODEL_VERSION = metrics_data.get("model_version", "unknown_v1")

    return _MODEL_PIPELINE, _MODEL_VERSION


class PredictionOutput(BaseModel):
    """Output contract for ML recovery probability prediction."""
    model_config = {"protected_namespaces": ()}

    recovery_probability: float = Field(..., ge=0.0, le=1.0, description="Predicted recovery probability")
    model_version: str = Field(..., description="Dynamically loaded model version string from metrics.json")
    observable_features_used: Dict[str, Any] = Field(default_factory=dict)


def predict_recovery_probability(
    features: Dict[str, Any],
) -> PredictionOutput:
    """
    Predicts the recovery probability for a failed transaction using strictly observable features.
    """
    model, model_version = get_model_and_version()

    # Required observable features schema in strict column order 0..11
    feature_row = [
        float(features.get("amount", 1000.0)),
        int(features.get("account_age_days", 180)),
        int(features.get("lifetime_tx_count", 10)),
        int(features.get("failed_count", 2)),
        float(features.get("failure_rate", 0.20)),
        float(features.get("avg_transaction_value", 1000.0)),
        float(features.get("upi_usage_pct", 0.50)),
        float(features.get("card_usage_pct", 0.30)),
        float(features.get("hours_since_failure", 2.0)),
        str(features.get("payment_method", "UPI")),
        str(features.get("failure_code", "UPI_BANK_TIMEOUT")),
        str(features.get("action_type", "RETRY")),
    ]

    X_input = np.array([feature_row], dtype=object)
    prob = float(model.predict_proba(X_input)[0, 1])
    prob = round(max(0.0, min(1.0, prob)), 4)

    return PredictionOutput(
        recovery_probability=prob,
        model_version=model_version,
        observable_features_used=features,
    )


def record_prediction(
    transaction_id: UUID,
    probability: float,
    db: Session,
    model_version: Optional[str] = None,
) -> Prediction:
    """
    Persists prediction to the predictions database table, traceable by model_version.
    """
    if model_version is None:
        _, loaded_version = get_model_and_version()
        model_version = loaded_version

    pred = Prediction(
        id=uuid.uuid4(),
        transaction_id=transaction_id,
        recovery_probability=probability,
        model_version=model_version,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(pred)
    db.commit()
    return pred
