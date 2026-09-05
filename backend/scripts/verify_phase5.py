#!/usr/bin/env python3
"""
Phase 5 Verification Script — ML Probability Model & Deterministic EV Engine.

Usage:
    docker compose exec backend python scripts/verify_phase5.py
"""

import json
import os
import sys
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.engines.expected_value import calculate_expected_value, rank_recovery_opportunities
from app.engines.prediction import METRICS_PATH, MODEL_PATH, predict_recovery_probability
from scripts.train_model import train_and_evaluate


def verify_phase5():
    print("\n" + "=" * 65)
    print("PHASE 5: ML RECOVERY PROBABILITY & EXPECTED VALUE VERIFICATION")
    print("=" * 65)

    # Step 1: Ensure model is trained and artifacts exist
    if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
        print("Artifacts not found. Initiating model training pipeline...")
        train_and_evaluate(n_samples=12000, seed=42)

    # Step 2: Report stored calibration metrics from held-out test set
    print("\n" + "-" * 65)
    print("STEP 1: HELD-OUT TEST CALIBRATION METRICS (FROM ARTIFACT)")
    print("-" * 65)
    with open(METRICS_PATH, "r") as f:
        metrics = json.load(f)

    print(f"  Model Version:         {metrics['model_version']}")
    print(f"  Algorithm:             {metrics['algorithm']}")
    print(f"  Trained Timestamp:     {metrics['trained_at']}")
    print(f"  Total Dataset:         {metrics['dataset']['total_samples']} samples")
    print(f"  Train Set (70%):       {metrics['dataset']['train_samples']} samples")
    print(f"  Validation Set (15%):  {metrics['dataset']['validation_samples']} samples")
    print(f"  Held-out Test (15%):   {metrics['dataset']['test_samples']} samples")
    print(f"  Held-out ROC-AUC:      {metrics['test_metrics']['roc_auc']:.4f}")
    print(f"  Held-out Brier Score:  {metrics['test_metrics']['brier_score']:.4f}")

    # Check if metrics need regeneration with full 10-bin structure
    if "sample_count" not in metrics.get("calibration_curve", [{}])[0]:
        print("Updating model metrics with explicit 10-bin sample counts...")
        metrics = train_and_evaluate(n_samples=12000, seed=42)

    print("\n  Calibration Curve (Held-out Test — All 10 Bins with Sample Counts):")
    print("    Bin | Range      | Samples | Mean Pred Prob | Empirical True Rate | Status")
    print("    ----+------------+---------+----------------+---------------------+----------------------")
    for b in metrics.get("calibration_curve", []):
        if b.get("is_empty"):
            print(f"    {b['bin']:3d} | {b['range']:10s} | {b['sample_count']:7d} |      N/A       |         N/A         | [EMPTY — 0 samples]")
        else:
            print(f"    {b['bin']:3d} | {b['range']:10s} | {b['sample_count']:7d} |     {b['prob_pred']:.4f}     |       {b['prob_true']:.4f}        | Populated")

    # Assert model performance passes reasonable statistical baselines
    assert metrics['test_metrics']['roc_auc'] > 0.70, f"ROC-AUC too low: {metrics['test_metrics']['roc_auc']}"
    assert metrics['test_metrics']['brier_score'] < 0.25, f"Brier score too high: {metrics['test_metrics']['brier_score']}"

    # Step 3: Run 3 transactions with different probability & value profiles
    print("\n" + "-" * 65)
    print("STEP 2: PREDICTION & EXPECTED VALUE EVALUATION (3 TRANSACTIONS)")
    print("-" * 65)

    tx1_features = {
        "name": "Tx 1: High-Probability / Low-Value (₹400, Reliable customer, Timeout, RETRY)",
        "amount": 400.0,
        "account_age_days": 600,
        "lifetime_tx_count": 50,
        "failed_count": 2,
        "failure_rate": 0.04,
        "avg_transaction_value": 450.0,
        "upi_usage_pct": 0.60,
        "card_usage_pct": 0.20,
        "hours_since_failure": 1.5,
        "payment_method": "UPI",
        "failure_code": "UPI_BANK_TIMEOUT",
        "action_type": "RETRY",
    }

    tx2_features = {
        "name": "Tx 2: Moderate-Probability / High-Value (₹35,000, Overdue Invoice, WHATSAPP)",
        "amount": 35000.0,
        "account_age_days": 365,
        "lifetime_tx_count": 20,
        "failed_count": 4,
        "failure_rate": 0.20,
        "avg_transaction_value": 25000.0,
        "upi_usage_pct": 0.10,
        "card_usage_pct": 0.10,
        "hours_since_failure": 24.0,
        "payment_method": "NETBANKING",
        "failure_code": "INVOICE_OVERDUE",
        "action_type": "WHATSAPP",
    }

    tx3_features = {
        "name": "Tx 3: Low-Probability / Moderate-Value (₹2,500, Risky customer, Hard Decline, ESCALATE)",
        "amount": 2500.0,
        "account_age_days": 45,
        "lifetime_tx_count": 5,
        "failed_count": 3,
        "failure_rate": 0.60,
        "avg_transaction_value": 1500.0,
        "upi_usage_pct": 0.20,
        "card_usage_pct": 0.70,
        "hours_since_failure": 48.0,
        "payment_method": "CARD",
        "failure_code": "CARD_DECLINED",
        "action_type": "ESCALATE",
    }

    test_txs = [tx1_features, tx2_features, tx3_features]
    eval_list = []

    for tx in test_txs:
        pred_out = predict_recovery_probability(tx)
        ev_out = calculate_expected_value(
            amount=tx["amount"],
            recovery_probability=pred_out.recovery_probability,
            action_type=tx["action_type"],
        )
        eval_list.append({
            "name": tx["name"],
            "amount": tx["amount"],
            "action_type": tx["action_type"],
            "recovery_probability": pred_out.recovery_probability,
            "model_version": pred_out.model_version,
            "action_cost": ev_out.action_cost,
            "expected_value": ev_out.expected_value,
        })

    for item in eval_list:
        print(f"\n[{item['name']}]")
        print(f"  Recoverable Amount:   ₹{item['amount']:.2f}")
        print(f"  Action Selected:      {item['action_type']}")
        print(f"  Model Version Used:   {item['model_version']}")
        print(f"  Recovery Probability: {item['recovery_probability']:.2%}")
        print(f"  Deterministic Cost:   ₹{item['action_cost']:.2f}")
        print(f"  EXPECTED VALUE (EV):  ₹{item['expected_value']:.2f}")

    # Step 4: EV Ranking
    print("\n" + "-" * 65)
    print("STEP 3: EXPECTED VALUE RANKING VERIFICATION")
    print("-" * 65)
    ranked = rank_recovery_opportunities(eval_list)

    for rank, r in enumerate(ranked, 1):
        print(f"  Rank #{rank}: {r.action_type} on ₹{r.amount} | Prob: {r.recovery_probability:.1%} | Cost: ₹{r.action_cost} | EV: ₹{r.expected_value}")

    # Verify ranking intuition: High-value moderate-prob (Tx 2) must produce vastly higher EV than low-value high-prob (Tx 1)
    assert ranked[0].amount == Decimal("35000.00"), "Expected Tx 2 (₹35,000) to rank #1 due to massive value EV"
    print("\nRanking Intuition Verified: High-value transaction correctly outranks low-value transaction based on net expected monetary recovery.")

    # Step 5: Test Discount Rate scaling
    print("\n" + "-" * 65)
    print("STEP 4: PROPORTIONAL DISCOUNT COST VERIFICATION")
    print("-" * 65)
    disc_small = calculate_expected_value(amount=500.0, recovery_probability=0.50, action_type="DISCOUNT", discount_pct=Decimal("0.10"))
    disc_large = calculate_expected_value(amount=50000.0, recovery_probability=0.50, action_type="DISCOUNT", discount_pct=Decimal("0.10"))
    print(f"  ₹500 txn with 10% discount:  Cost = ₹{disc_small.action_cost} (EV = ₹{disc_small.expected_value})")
    print(f"  ₹50,000 txn with 10% discount: Cost = ₹{disc_large.action_cost} (EV = ₹{disc_large.expected_value})")
    assert disc_small.action_cost == Decimal("50.00"), "Expected ₹50 cost for ₹500 discount"
    assert disc_large.action_cost == Decimal("5000.00"), "Expected ₹5,000 cost for ₹50,000 discount"
    print("Proportional discount scaling verified: Cost scales strictly with transaction value.")

    print("\n" + "=" * 65)
    print("PHASE 5 VERIFICATION COMPLETE: ALL CHECKS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    verify_phase5()
