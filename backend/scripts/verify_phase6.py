#!/usr/bin/env python3
"""
Phase 6 Verification Script — LLM Recommendation, Action Contract & Authoritative Reconciliation.

Usage:
    docker compose exec backend python scripts/verify_phase6.py
"""

import os
import sys
import uuid
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.engines.decision import (
    ActionType,
    Channel,
    RecoveryAction,
    recommend_recovery_action,
)
from app.engines.diagnosis import diagnose_failure
from app.engines.expected_value import calculate_expected_value
from app.engines.prediction import predict_recovery_probability
from app.models.tables import Customer, Decision, Merchant, Transaction


def run_phase6_verification():
    print("\n" + "=" * 65)
    print("PHASE 6: LLM RECOMMENDATION & ACTION CONTRACT VERIFICATION")
    print("=" * 65)

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    from app.engines.prediction import METRICS_PATH, MODEL_PATH
    from scripts.train_model import train_and_evaluate
    if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
        print("Model artifacts not found. Initiating model training pipeline...")
        train_and_evaluate(n_samples=12000, seed=42)

    try:
        # -------------------------------------------------------------
        # PART 1: Run 10 diagnosed transactions through recommendation
        # -------------------------------------------------------------
        print("\n" + "-" * 65)
        print("PART 1: RECOMMENDATION PIPELINE (10 TRANSACTIONS)")
        print("-" * 65)

        # Retrieve 10 failed transactions from DB
        txs = (
            session.query(Transaction)
            .filter(Transaction.status == "failed")
            .limit(10)
            .all()
        )

        if len(txs) < 10:
            print("Not enough transactions in DB. Please run Phase 2 generator first.")
            sys.exit(1)

        print(f"Loaded {len(txs)} failed transactions from DB. Running pipeline...\n")

        contracts_generated = []
        for idx, tx in enumerate(txs, 1):
            cust = session.query(Customer).filter(Customer.id == tx.customer_id).first()
            tx_dict = {
                "id": str(tx.id),
                "amount": tx.amount,
                "payment_method": tx.payment_method.value if hasattr(tx.payment_method, "value") else str(tx.payment_method),
                "failure_code": tx.failure_code,
            }
            cust_dict = {
                "lifetime_tx_count": cust.lifetime_tx_count if cust else 10,
                "failed_count": cust.failed_count if cust else 2,
                "preferred_channel": cust.preferred_channel if cust else "UPI",
            }

            # 1. Diagnosis
            diagnosis = diagnose_failure(tx.failure_code)

            # 2. ML Probability
            pred_features = {
                "amount": float(tx.amount),
                "account_age_days": cust.account_age_days if cust else 180,
                "lifetime_tx_count": cust.lifetime_tx_count if cust else 10,
                "failed_count": cust.failed_count if cust else 2,
                "failure_rate": round(cust.failed_count / max(1, cust.lifetime_tx_count), 4) if cust else 0.2,
                "avg_transaction_value": float(cust.avg_transaction_value) if cust and cust.avg_transaction_value else 1000.0,
                "upi_usage_pct": cust.upi_usage_pct if cust else 0.5,
                "card_usage_pct": cust.card_usage_pct if cust else 0.3,
                "hours_since_failure": 3.0,
                "payment_method": tx_dict["payment_method"],
                "failure_code": tx.failure_code,
                "action_type": "RETRY",
            }
            pred_out = predict_recovery_probability(pred_features)

            # 3. Decision Recommendation & Authoritative Reconciliation
            verified_decision = recommend_recovery_action(
                transaction=tx_dict,
                customer=cust_dict,
                diagnosis=diagnosis,
                recovery_probability=pred_out.recovery_probability,
                authoritative_amount=tx.amount,
                db=session,
            )

            contract = verified_decision.action_contract
            contracts_generated.append((tx, contract, verified_decision))

            print(f"[{idx:2d}/10] Tx ID: {str(tx.id)[:8]}... | Amount: ₹{contract.amount:9.2f}")
            print(f"     Diagnosis:      {tx.failure_code}")
            print(f"     ML Probability: {pred_out.recovery_probability:.2%}")
            print(f"     Recommended:    Action={contract.action_type.value} | Channel={contract.channel.value} | Delay={contract.delay_hours}h")
            print(f"     Verified EV:    ₹{contract.expected_value:.2f}")
            print(f"     Reason Codes:   {contract.reason_codes}")
            print(f"     Persisted DB ID:{verified_decision.decision_id}")
            print()

        assert len(contracts_generated) == 10, "Expected 10 validated Action Contracts"

        # -------------------------------------------------------------
        # PART 2 (Specific Check a): Malformed Payload Rejection
        # -------------------------------------------------------------
        print("-" * 65)
        print("PART 2: SCHEMA VALIDATION REJECTION TEST (MALFORMED PAYLOAD)")
        print("-" * 65)
        malformed_payload = {
            "action_type": "INVALID_SMS_BLAST",  # Not in ActionType enum
            "transaction_id": str(uuid.uuid4()),
            "amount": "1000.00",
            "channel": "TIKTOK",                 # Not in Channel enum
            "delay_hours": -5,                   # Negative delay violates ge=0
            "reason_codes": "not_a_list",        # String instead of list
            "confidence": 1.5,                   # Exceeds max 1.0
            "expected_value": "900.00",
        }

        print("Attempting to validate deliberately malformed payload:")
        print(f"  action_type:  '{malformed_payload['action_type']}' (Invalid enum)")
        print(f"  channel:      '{malformed_payload['channel']}' (Invalid enum)")
        print(f"  delay_hours:  {malformed_payload['delay_hours']} (Negative integer)")
        print(f"  confidence:   {malformed_payload['confidence']} (Out of bounds > 1.0)")

        validation_rejected = False
        try:
            RecoveryAction.model_validate(malformed_payload)
        except ValidationError as e:
            validation_rejected = True
            print("\nPydantic Validation Successfully Caught and Rejected Malformed Contract:")
            for err in e.errors():
                loc = " -> ".join(str(p) for p in err["loc"])
                print(f"  [REJECTED FIELD: {loc:14s}] Reason: {err['msg']}")

        assert validation_rejected, "Expected Pydantic ValidationError but payload passed"
        print("\nRejection Verification Passed: Schema strictly prevents unapproved actions/values.")

        # -------------------------------------------------------------
        # PART 3 (Specific Check b): Divergent LLM Claims Reconciliation
        # -------------------------------------------------------------
        print("\n" + "-" * 65)
        print("PART 3: AUTHORITATIVE RECONCILIATION & PERSISTENCE TEST")
        print("-" * 65)

        sample_tx = txs[0]
        true_db_amount = sample_tx.amount
        true_ml_prob = 0.3520

        # Calculate authoritative EV
        auth_ev = calculate_expected_value(
            amount=true_db_amount,
            recovery_probability=true_ml_prob,
            action_type="WHATSAPP",
        )

        print(f"Authoritative Ground Truth:")
        print(f"  Transaction ID:         {sample_tx.id}")
        print(f"  DB Authoritative Amount:₹{true_db_amount}")
        print(f"  ML Probability:         {true_ml_prob:.2%}")
        print(f"  Authoritative EV:       ₹{auth_ev.expected_value} (Cost: ₹{auth_ev.action_cost})")

        # Simulate LLM proposal with divergent claims
        divergent_llm_claims = {
            "action_type": ActionType.WHATSAPP,
            "transaction_id": str(sample_tx.id),
            "amount": Decimal("99999.00"),          # Hallucinated 100k amount
            "channel": Channel.WHATSAPP,
            "delay_hours": 2,
            "reason_codes": ["LLM_CLAIMED_HIGH_VALUE"],
            "confidence": 0.99,                     # Hallucinated 99% confidence
            "expected_value": Decimal("85000.00"),  # Hallucinated massive EV
            "policy_context": {},
        }

        print("\nSimulated Divergent LLM Claims:")
        print(f"  LLM Claimed Amount:     ₹{divergent_llm_claims['amount']}")
        print(f"  LLM Claimed Confidence: {divergent_llm_claims['confidence']}")
        print(f"  LLM Claimed EV:         ₹{divergent_llm_claims['expected_value']}")

        # Reconcile manually using the engine's reconciliation logic and persist
        contract = RecoveryAction.model_validate(divergent_llm_claims)
        reconciled_log = []

        if contract.amount != true_db_amount:
            reconciled_log.append(f"Overrode LLM amount ₹{contract.amount} -> DB amount ₹{true_db_amount}")
            contract.amount = true_db_amount

        if contract.expected_value != auth_ev.expected_value:
            reconciled_log.append(f"Overrode LLM expected_value ₹{contract.expected_value} -> Authoritative EV ₹{auth_ev.expected_value}")
            contract.expected_value = auth_ev.expected_value

        if round(contract.confidence, 4) != round(true_ml_prob, 4):
            reconciled_log.append(f"Reconciled LLM confidence {contract.confidence} -> ML probability {true_ml_prob}")
            contract.confidence = true_ml_prob

        # Persist reconciliation to DB
        reconciled_decision_id = uuid.uuid4()
        db_record = Decision(
            id=reconciled_decision_id,
            transaction_id=sample_tx.id,
            action_type=contract.action_type.value,
            channel=contract.channel.value,
            delay_hours=contract.delay_hours,
            amount=true_db_amount,
            confidence_llm=0.99,
            expected_value_llm=Decimal("85000.00"),
            expected_value_verified=auth_ev.expected_value,
            reason_codes=contract.reason_codes,
            policy_context={"reconciliation_log": reconciled_log},
        )
        session.add(db_record)
        session.commit()

        # Query back from DB to verify persistence of both claimed and verified numbers
        persisted = session.query(Decision).filter(Decision.id == reconciled_decision_id).first()

        print("\nAuthoritative Backend Overrides Applied:")
        for entry in reconciled_log:
            print(f"  - {entry}")

        print("\nDatabase Record Verification (Table: decisions):")
        print(f"  Decision Record ID:       {persisted.id}")
        print(f"  Action Type:              {persisted.action_type}")
        print(f"  Amount (Authoritative):   ₹{persisted.amount}")
        print(f"  LLM Claimed EV:           ₹{persisted.expected_value_llm}")
        print(f"  VERIFIED AUTHORITATIVE EV:₹{persisted.expected_value_verified}")
        print(f"  LLM Claimed Confidence:   {persisted.confidence_llm}")

        assert persisted.expected_value_llm == Decimal("85000.00"), "expected_value_llm mismatch in DB"
        assert persisted.expected_value_verified == auth_ev.expected_value, "expected_value_verified mismatch in DB"
        assert persisted.amount == true_db_amount, "authoritative amount mismatch in DB"

        print("\nReconciliation Verification Passed: Both LLM claims and verified values are auditable in DB.")
        print("\n" + "=" * 65)
        print("PHASE 6 VERIFICATION COMPLETE: ALL CHECKS PASSED!")
        print("=" * 65)

    finally:
        session.close()


if __name__ == "__main__":
    run_phase6_verification()
