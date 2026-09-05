#!/usr/bin/env python3
"""
Phase 5 — Recovery Probability Model Training Script.

Trains a scikit-learn model strictly on observable transaction and customer features,
using resolved binary outcomes from a simulated training slice.
Never exposes the hidden outcome function to the model feature matrix.

Saves:
  - app/engines/artifacts/recovery_model.joblib
  - app/engines/artifacts/metrics.json
"""

import json
import os
import random
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# Simulator outcome resolver (used ONLY to simulate real historical outcome labels)
from scripts.simulator import hidden_outcome_function

# Failure taxonomy codes
FAILURE_CODES = [
    "UPI_COLLECT_EXPIRED", "UPI_BANK_TIMEOUT", "UPI_INSUFFICIENT_FUNDS", "UPI_PSP_ERROR",
    "UPI_CUSTOMER_DECLINED", "UPI_LIMIT_EXCEEDED", "UPI_MANDATE_FAILED", "UPI_MANDATE_EXPIRED",
    "CARD_EXPIRED", "CARD_DECLINED", "CARD_LIMIT_EXCEEDED", "ISSUER_TIMEOUT", "INSUFFICIENT_FUNDS",
    "BANK_TIMEOUT", "BANK_DECLINED", "SESSION_EXPIRED",
    "MANDATE_REGISTRATION_FAILED", "MANDATE_EXECUTION_FAILED", "MANDATE_REVOKED", "MANDATE_EXPIRED",
    "CHECKOUT_ABANDONED", "PAYMENT_PAGE_EXIT", "OTP_TIMEOUT", "PAYMENT_METHOD_CHANGED",
    "INVOICE_OVERDUE", "PAYMENT_PROMISE_BROKEN", "PARTIAL_PAYMENT",
]

PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "MANDATE"]
ACTION_TYPES = ["RETRY", "WHATSAPP", "EMAIL", "DISCOUNT", "ESCALATE"]


def generate_training_slice(n_samples: int = 10000, seed: int = 42):
    """
    Generates a historical slice of recovery attempts.
    Each sample has:
      - Observable features (X)
      - Actual binary outcome resolved by simulator (y)
    The model receives ONLY X and y — never the hidden reliability score or formula.
    """
    rng = random.Random(seed)
    records = []
    labels = []

    for _ in range(n_samples):
        # 1. Customer profile (latent reliability generates observable history)
        if rng.random() < 0.55:
            hidden_reliability = rng.uniform(0.80, 0.95)
            account_age = rng.randint(180, 1800)
            avg_target = rng.uniform(500, 20000)
        elif rng.random() < 0.85:
            hidden_reliability = rng.uniform(0.60, 0.80)
            account_age = rng.randint(30, 365)
            avg_target = rng.uniform(200, 5000)
        else:
            hidden_reliability = rng.uniform(0.35, 0.60)
            account_age = rng.randint(1, 180)
            avg_target = rng.uniform(100, 3000)

        # Observable customer historical metrics
        lifetime_tx = max(1, int(account_age * rng.uniform(0.05, 0.5)))
        # Historical failed count shaped by reliability with noise
        observed_fail_rate = min(0.95, max(0.01, (1.0 - hidden_reliability) + rng.gauss(0, 0.05)))
        failed_count = int(lifetime_tx * observed_fail_rate)
        successful_count = lifetime_tx - failed_count
        upi_pct = round(rng.uniform(0.10, 0.70), 2)
        card_pct = round(rng.uniform(0.05, max(0.06, 0.90 - upi_pct)), 2)

        # 2. Failed Transaction (observable features)
        method = rng.choice(PAYMENT_METHODS)
        failure_code = rng.choice(FAILURE_CODES)
        amount = round(avg_target * rng.uniform(0.3, 2.5), 2)
        hours_since_failure = round(rng.uniform(0.5, 120.0), 1)
        action = rng.choice(ACTION_TYPES)

        # 3. Simulator resolves actual ground truth outcome (0 or 1)
        prob = hidden_outcome_function(
            customer_reliability=hidden_reliability,
            failure_code=failure_code,
            payment_method=method,
            hours_since_failure=hours_since_failure,
            action_type=action,
        )
        outcome = 1 if rng.random() < prob else 0

        # Feature vector contains STRICTLY observable features
        # Columns 0..8 are numeric, columns 9..11 are categorical
        feature_row = [
            amount,
            account_age,
            lifetime_tx,
            failed_count,
            round(failed_count / lifetime_tx, 4),
            round(avg_target, 2),
            upi_pct,
            card_pct,
            hours_since_failure,
            method,
            failure_code,
            action,
        ]
        records.append(feature_row)
        labels.append(outcome)

    X = np.array(records, dtype=object)
    y = np.array(labels, dtype=int)
    return X, y


def train_and_evaluate(n_samples: int = 12000, seed: int = 42):
    print("\n" + "=" * 65)
    print("PHASE 5: TRAINING RECOVERY PROBABILITY ML MODEL")
    print("=" * 65)
    print(f"Generating training slice: {n_samples} historical attempts (seed={seed})...")

    X, y = generate_training_slice(n_samples=n_samples, seed=seed)

    feature_cols = [
        "amount", "account_age_days", "lifetime_tx_count", "failed_count",
        "failure_rate", "avg_transaction_value", "upi_usage_pct", "card_usage_pct",
        "hours_since_failure", "payment_method", "failure_code", "action_type",
    ]
    numeric_indices = list(range(9))
    categorical_indices = [9, 10, 11]

    # Strict 70% Train, 15% Validation, 15% Test split
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, random_state=seed, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=(15 / 85), random_state=seed, stratify=y_train_val
    )

    print(f"Dataset split:")
    print(f"  Train set:      {len(X_train)} samples ({len(X_train)/len(X):.1%})")
    print(f"  Validation set: {len(X_val)} samples ({len(X_val)/len(X):.1%})")
    print(f"  Held-out Test:  {len(X_test)} samples ({len(X_test)/len(X):.1%})")

    # Build scikit-learn preprocessing pipeline
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_indices),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_indices),
        ]
    )

    from sklearn.ensemble import GradientBoostingClassifier

    base_estimator = GradientBoostingClassifier(
        n_estimators=80,
        learning_rate=0.08,
        max_depth=4,
        random_state=seed,
    )

    # Calibrate probability predictions using sigmoid/isotonic calibration
    calibrated_model = CalibratedClassifierCV(
        estimator=base_estimator,
        method="sigmoid",
        cv=3,
    )

    pipeline = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", calibrated_model),
    ])

    print("\nFitting model on training set...")
    pipeline.fit(X_train, y_train)

    # Validation check
    val_probs = pipeline.predict_proba(X_val)[:, 1]
    val_auc = roc_auc_score(y_val, val_probs)
    val_brier = brier_score_loss(y_val, val_probs)
    print(f"Validation Performance: ROC-AUC = {val_auc:.4f}, Brier Score = {val_brier:.4f}")

    # Held-out Test evaluation
    print("\nEvaluating on held-out test set...")
    test_probs = pipeline.predict_proba(X_test)[:, 1]
    test_auc = float(roc_auc_score(y_test, test_probs))
    test_brier = float(brier_score_loss(y_test, test_probs))

    # Explicit 10-bin calibration curve with sample counts per bin
    bin_edges = np.linspace(0.0, 1.0, 11)
    calibration_data = []
    for b in range(10):
        low, high = bin_edges[b], bin_edges[b + 1]
        if b == 9:
            mask = (test_probs >= low) & (test_probs <= high)
        else:
            mask = (test_probs >= low) & (test_probs < high)
        count = int(np.sum(mask))
        if count > 0:
            mean_pred = float(np.mean(test_probs[mask]))
            true_rate = float(np.mean(y_test[mask]))
            calibration_data.append({
                "bin": b + 1,
                "range": f"[{low:.1f}, {high:.1f}]",
                "sample_count": count,
                "prob_pred": round(mean_pred, 4),
                "prob_true": round(true_rate, 4),
                "is_empty": False,
            })
        else:
            calibration_data.append({
                "bin": b + 1,
                "range": f"[{low:.1f}, {high:.1f}]",
                "sample_count": 0,
                "prob_pred": None,
                "prob_true": None,
                "is_empty": True,
            })

    model_version = f"recov_ml_v1_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    metrics_payload = {
        "model_version": model_version,
        "algorithm": "GradientBoosting + CalibratedClassifierCV(sigmoid)",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "total_samples": len(X),
            "train_samples": len(X_train),
            "validation_samples": len(X_val),
            "test_samples": len(X_test),
        },
        "test_metrics": {
            "roc_auc": round(test_auc, 4),
            "brier_score": round(test_brier, 4),
        },
        "calibration_curve": calibration_data,
        "observable_features": feature_cols,
    }

    # Save artifacts
    artifacts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app", "engines", "artifacts"
    )
    os.makedirs(artifacts_dir, exist_ok=True)

    model_path = os.path.join(artifacts_dir, "recovery_model.joblib")
    metrics_path = os.path.join(artifacts_dir, "metrics.json")

    joblib.dump(pipeline, model_path)
    with open(metrics_path, "w") as f:
        json.dump(metrics_payload, f, indent=2)

    print(f"\nArtifacts saved successfully:")
    print(f"  Model binary: {model_path}")
    print(f"  Metrics JSON: {metrics_path}")
    print(f"\nHeld-out Test Results:")
    print(f"  Model Version:  {model_version}")
    print(f"  ROC-AUC Score:  {test_auc:.4f}")
    print(f"  Brier Score:    {test_brier:.4f}")
    print("=" * 65)

    return metrics_payload


if __name__ == "__main__":
    train_and_evaluate()
