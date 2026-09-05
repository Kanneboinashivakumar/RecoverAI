#!/usr/bin/env python3
"""
Phase 8 Verification Script — Action Executor, Simulator Verification & Audit Trail.

Demonstrates:
  1. Mock executor demo for each action type (RETRY, WHATSAPP, EMAIL, DISCOUNT).
  2. Outcome verification genuinely powered by Phase 2's hidden simulator function.
  3. End-to-end execution of a transaction through all 8 stages, with complete
     Agent Replay audit trail reconstructed purely from audit_events.

Usage:
    docker compose exec backend python scripts/verify_phase8.py
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.domain.events.normalizer import normalize_event
from app.engines.audit import get_agent_replay, log_audit_event
from app.engines.decision import (
    ActionType,
    Channel,
    RecoveryAction,
    recommend_recovery_action,
)
from app.engines.diagnosis import diagnose_failure
from app.engines.policy import evaluate_policy
from app.engines.prediction import METRICS_PATH, MODEL_PATH, predict_recovery_probability
from app.engines.risk import score_risk
from app.engines.verification import verify_action_outcome
from app.integrations.messaging import (
    dispatch_mock_escalation,
    execute_action,
    send_mock_discount,
    send_mock_email,
    send_mock_whatsapp,
)
from app.integrations.mock_gateway import execute_mock_retry
from app.models.tables import (
    Action,
    ActionStatus,
    AuditEvent,
    Customer,
    Decision,
    PolicyEvaluation,
    Transaction,
    VerificationOutcome,
    VerificationResult,
)
from scripts.simulator import hidden_outcome_function
from scripts.train_model import train_and_evaluate


def run_phase8_verification():
    print("\n" + "=" * 65, flush=True)
    print("PHASE 8: ACTION EXECUTOR, VERIFICATION & AUDIT TRAIL", flush=True)
    print("=" * 65, flush=True)

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
        print("Model artifacts not found. Initiating model training pipeline...", flush=True)
        train_and_evaluate(n_samples=12000, seed=42)

    try:
        # -------------------------------------------------------------
        # PART 1: Mock Executor Demo for EACH Action Type
        # -------------------------------------------------------------
        print("\n" + "-" * 65, flush=True)
        print("PART 1: MOCK EXECUTOR DEMO FOR EACH ACTION TYPE", flush=True)
        print("-" * 65, flush=True)

        demo_tx_id = uuid.uuid4()
        demo_amount = Decimal("2500.00")

        # 1. RETRY
        res_retry = execute_mock_retry(demo_tx_id, demo_amount, channel="UPI")
        print("[ACTION 1: RETRY via Mock Payment Gateway]", flush=True)
        print(f"  Provider:       {res_retry['mock_provider']}", flush=True)
        print(f"  Gateway Ref ID: {res_retry['gateway_reference_id']}", flush=True)
        print(f"  Status:         {res_retry['status']}", flush=True)
        print(f"  Operational Fee:₹{res_retry['operational_cost']:.2f}", flush=True)
        print(f"  Simulated Flag: {res_retry['simulated']}", flush=True)

        # 2. WHATSAPP
        res_wa = send_mock_whatsapp(demo_tx_id, demo_amount)
        print("\n[ACTION 2: WHATSAPP via Mock Meta Business API]", flush=True)
        print(f"  Provider:       {res_wa['mock_provider']}", flush=True)
        print(f"  Message ID:     {res_wa['message_id']}", flush=True)
        print(f"  Status:         {res_wa['status']}", flush=True)
        print(f"  Template:       {res_wa['template_name']}", flush=True)
        print(f"  Operational Fee:₹{res_wa['operational_cost']:.2f}", flush=True)
        print(f"  Simulated Flag: {res_wa['simulated']}", flush=True)

        # 3. EMAIL
        res_email = send_mock_email(demo_tx_id, demo_amount)
        print("\n[ACTION 3: EMAIL via Mock SES Gateway]", flush=True)
        print(f"  Provider:       {res_email['mock_provider']}", flush=True)
        print(f"  Message ID:     {res_email['message_id']}", flush=True)
        print(f"  Status:         {res_email['status']}", flush=True)
        print(f"  Subject:        {res_email['subject']}", flush=True)
        print(f"  Operational Fee:₹{res_email['operational_cost']:.2f}", flush=True)
        print(f"  Simulated Flag: {res_email['simulated']}", flush=True)

        # 4. DISCOUNT
        res_disc = send_mock_discount(demo_tx_id, demo_amount, discount_pct=Decimal("0.10"), channel="WHATSAPP")
        print("\n[ACTION 4: DISCOUNT Incentive via Mock Campaign Manager]", flush=True)
        print(f"  Provider:       {res_disc['mock_provider']}", flush=True)
        print(f"  Coupon Code:    {res_disc['coupon_code']}", flush=True)
        print(f"  Original Amount:₹{res_disc['original_amount']:.2f}", flush=True)
        print(f"  Discount (10%): -₹{res_disc['discount_amount']:.2f}", flush=True)
        print(f"  Effective Amount:₹{res_disc['effective_amount']:.2f}", flush=True)
        print(f"  Operational Fee:₹{res_disc['operational_cost']:.2f}", flush=True)
        print(f"  Simulated Flag: {res_disc['simulated']}", flush=True)

        # 5. ESCALATE
        res_esc = dispatch_mock_escalation(demo_tx_id, demo_amount, reason="High value transaction requires human approval")
        print("\n[ACTION 5: ESCALATE via Mock Human Review Dispatch]", flush=True)
        print(f"  Provider:       {res_esc['mock_provider']}", flush=True)
        print(f"  Ticket ID:      {res_esc['ticket_id']}", flush=True)
        print(f"  Status:         {res_esc['status']}", flush=True)
        print(f"  Queue:          {res_esc['queue']}", flush=True)
        print(f"  Reason:         {res_esc['reason']}", flush=True)
        print(f"  Operational Fee:₹{res_esc['operational_cost']:.2f}", flush=True)
        print(f"  Simulated Flag: {res_esc['simulated']}", flush=True)

        # -------------------------------------------------------------
        # PART 2: Simulator-Backed Outcome Verification
        # -------------------------------------------------------------
        print("\n" + "-" * 65, flush=True)
        print("PART 2: SIMULATOR-BACKED OUTCOME VERIFICATION", flush=True)
        print("-" * 65, flush=True)

        # Demonstrate that verification outcome is calculated strictly via Phase 2 hidden simulator
        print("Evaluating Hidden Simulator Outcome Function across two contrasting scenarios:\n", flush=True)

        # --- SCENARIO A: High Probability Recovery ---
        prob_a = hidden_outcome_function(
            customer_reliability=0.95,
            failure_code="UPI_BANK_TIMEOUT",
            payment_method="UPI",
            hours_since_failure=1.0,
            action_type="RETRY",
        )
        print("[SCENARIO A: High Probability Recovery Context]", flush=True)
        print(f"  Parameters:     Reliability=0.95 | Code=UPI_BANK_TIMEOUT | Age=1.0h | Action=RETRY", flush=True)
        print(f"  Simulator Prob: {prob_a:.2%} (Hidden Ground Truth)", flush=True)

        tx_a = session.query(Transaction).filter(Transaction.status == "failed").first()
        dec_a_id = uuid.uuid4()
        act_a_id = uuid.uuid4()

        d_a = Decision(
            id=dec_a_id,
            transaction_id=tx_a.id,
            action_type="RETRY",
            channel="UPI",
            delay_hours=0,
            amount=Decimal("2500.00"),
            confidence_llm=0.80,
            expected_value_llm=Decimal("2000.00"),
            expected_value_verified=Decimal("1999.00"),
            reason_codes=["SCENARIO_A_TEST"],
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(d_a)
        session.flush()

        act_a = Action(
            id=act_a_id,
            transaction_id=tx_a.id,
            decision_id=dec_a_id,
            action_type="RETRY",
            status=ActionStatus.EXECUTED,
            executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(act_a)
        session.commit()

        verif_a = verify_action_outcome(
            action_id=act_a_id,
            transaction_id=tx_a.id,
            action_type="RETRY",
            amount=Decimal("2500.00"),
            customer_reliability=0.95,
            failure_code="UPI_BANK_TIMEOUT",
            payment_method="UPI",
            hours_since_failure=1.0,
            db=session,
            seed=42,
        )

        print(f"  Resolution:     Seeded roll against {prob_a:.2%} -> Resolved: {verif_a.outcome.value.upper()}", flush=True)
        print(f"  Verification ID:{verif_a.id}", flush=True)
        print(f"  Outcome in DB:  {verif_a.outcome.value.upper()}", flush=True)
        print(f"  Recovered Amt:  ₹{verif_a.simulated_amount_recovered:.2f} (Flagged as simulated)", flush=True)
        print(f"  -> Explanation: SUCCESS directly generated by Scenario A's {prob_a:.2%} simulator probability.\n", flush=True)

        assert verif_a.outcome == VerificationOutcome.SUCCESS
        assert verif_a.simulated_amount_recovered == Decimal("2500.00")

        # --- SCENARIO B: Low Probability Recovery ---
        prob_b = hidden_outcome_function(
            customer_reliability=0.20,
            failure_code="MANDATE_REVOKED",
            payment_method="UPI",
            hours_since_failure=72.0,
            action_type="EMAIL",
        )
        print("[SCENARIO B: Low Probability Recovery Context]", flush=True)
        print(f"  Parameters:     Reliability=0.20 | Code=MANDATE_REVOKED | Age=72.0h | Action=EMAIL", flush=True)
        print(f"  Simulator Prob: {prob_b:.2%} (Hidden Ground Truth)", flush=True)

        tx_b = session.query(Transaction).filter(Transaction.status == "failed").offset(1).first()
        dec_b_id = uuid.uuid4()
        act_b_id = uuid.uuid4()

        d_b = Decision(
            id=dec_b_id,
            transaction_id=tx_b.id,
            action_type="EMAIL",
            channel="EMAIL",
            delay_hours=0,
            amount=Decimal("1500.00"),
            confidence_llm=0.10,
            expected_value_llm=Decimal("100.00"),
            expected_value_verified=Decimal("50.00"),
            reason_codes=["SCENARIO_B_TEST"],
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(d_b)
        session.flush()

        act_b = Action(
            id=act_b_id,
            transaction_id=tx_b.id,
            decision_id=dec_b_id,
            action_type="EMAIL",
            status=ActionStatus.EXECUTED,
            executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(act_b)
        session.commit()

        verif_b = verify_action_outcome(
            action_id=act_b_id,
            transaction_id=tx_b.id,
            action_type="EMAIL",
            amount=Decimal("1500.00"),
            customer_reliability=0.20,
            failure_code="MANDATE_REVOKED",
            payment_method="UPI",
            hours_since_failure=72.0,
            db=session,
            seed=42,
        )

        print(f"  Resolution:     Seeded roll against {prob_b:.2%} -> Resolved: {verif_b.outcome.value.upper()}", flush=True)
        print(f"  Verification ID:{verif_b.id}", flush=True)
        print(f"  Outcome in DB:  {verif_b.outcome.value.upper()}", flush=True)
        print(f"  Recovered Amt:  ₹{verif_b.simulated_amount_recovered:.2f} (Flagged as simulated)", flush=True)
        print(f"  -> Explanation: FAILURE directly generated by Scenario B's {prob_b:.2%} simulator probability.", flush=True)

        assert verif_b.outcome == VerificationOutcome.FAILURE
        assert verif_b.simulated_amount_recovered == Decimal("0.00")
        print("\nSimulator Verification Passed: Both high and low probability scenarios resolved faithfully.", flush=True)

        # -------------------------------------------------------------
        # PART 3: End-to-End Pipeline & Agent Replay Reconstruction
        # -------------------------------------------------------------
        print("\n" + "=" * 65, flush=True)
        print("PART 3: END-TO-END PIPELINE & FORENSIC AGENT REPLAY", flush=True)
        print("=" * 65, flush=True)

        target_tx = (
            session.query(Transaction)
            .filter(Transaction.status == "failed", Transaction.amount <= 5000)
            .first()
        )
        if not target_tx:
            target_tx = session.query(Transaction).filter(Transaction.status == "failed").first()

        target_cust = session.query(Customer).filter(Customer.id == target_tx.customer_id).first()

        # Clear any prior records for target transaction to test clean 8-stage reconstruction
        session.query(AuditEvent).filter(AuditEvent.transaction_id == target_tx.id).delete()
        session.query(VerificationResult).filter(VerificationResult.transaction_id == target_tx.id).delete()
        session.query(PolicyEvaluation).filter(PolicyEvaluation.transaction_id == target_tx.id).delete()
        session.query(Action).filter(Action.transaction_id == target_tx.id).delete()
        session.query(Decision).filter(Decision.transaction_id == target_tx.id).delete()
        session.commit()

        print(f"Running full 8-stage pipeline for Transaction: {target_tx.id}...", flush=True)

        # --- Stage 1: EVENT_RECEIVED ---
        raw_event = {
            "event_id": f"evt_{uuid.uuid4().hex[:10]}",
            "merchant_id": str(target_tx.merchant_id),
            "transaction_id": str(target_tx.id),
            "customer_id": str(target_cust.id),
            "amount": float(target_tx.amount),
            "currency": "INR",
            "payment_method": "UPI",
            "failure_code": target_tx.failure_code,
            "raw_error_message": f"Bank gateway rejected transaction: {target_tx.failure_code}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        norm_event = normalize_event(raw_event)
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="EVENT_RECEIVED",
            actor="event_normalizer",
            input_snapshot={"raw_event_id": raw_event["event_id"], "amount": raw_event["amount"]},
            output_snapshot={"normalized_event_id": norm_event.external_event_id, "failure_code": norm_event.metadata.get("failure_code")},
            reason_codes=["EVENT_NORMALIZED"],
            db=session,
        )

        # --- Stage 2: RISK_SCORED ---
        risk_res = score_risk(norm_event, customer=target_cust)
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="RISK_SCORED",
            actor="risk_engine",
            input_snapshot={"amount": float(target_tx.amount), "lifetime_tx": target_cust.lifetime_tx_count},
            output_snapshot={"severity_score": risk_res.severity_score, "risk_level": risk_res.risk_level},
            reason_codes=risk_res.reasons,
            db=session,
        )

        # --- Stage 3: DIAGNOSIS_COMPLETED ---
        failure_code_str = norm_event.metadata.get("failure_code", target_tx.failure_code)
        diag_res = diagnose_failure(failure_code_str)
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="DIAGNOSIS_COMPLETED",
            actor="diagnosis_engine",
            input_snapshot={"failure_code": failure_code_str},
            output_snapshot={"failure_code": diag_res.failure_code, "confidence": diag_res.confidence, "source": diag_res.source.value},
            reason_codes=diag_res.reason_codes,
            db=session,
        )

        # --- Stage 4: PROBABILITY_PREDICTED ---
        ml_features = {
            "amount": float(target_tx.amount),
            "account_age_days": target_cust.account_age_days,
            "lifetime_tx_count": target_cust.lifetime_tx_count,
            "failed_count": target_cust.failed_count,
            "failure_rate": round(target_cust.failed_count / max(1, target_cust.lifetime_tx_count), 4),
            "avg_transaction_value": float(target_cust.avg_transaction_value or 1000.0),
            "upi_usage_pct": target_cust.upi_usage_pct or 0.5,
            "card_usage_pct": target_cust.card_usage_pct or 0.3,
            "hours_since_failure": 2.0,
            "payment_method": "UPI",
            "failure_code": target_tx.failure_code,
            "action_type": "RETRY",
        }
        pred_res = predict_recovery_probability(ml_features)
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="PROBABILITY_PREDICTED",
            actor="ml_prediction_engine",
            input_snapshot={"features": ml_features},
            output_snapshot={"recovery_probability": pred_res.recovery_probability, "model_version": pred_res.model_version},
            reason_codes=["CALIBRATED_ML_ESTIMATION"],
            db=session,
        )

        # --- Stage 5: DECISION_RECOMMENDED ---
        cust_profile = {
            "lifetime_tx_count": target_cust.lifetime_tx_count,
            "failed_count": target_cust.failed_count,
            "preferred_channel": target_cust.preferred_channel or "UPI",
        }
        dec_res = recommend_recovery_action(
            transaction={"id": str(target_tx.id), "amount": target_tx.amount, "payment_method": "UPI", "failure_code": target_tx.failure_code},
            customer=cust_profile,
            diagnosis=diag_res,
            recovery_probability=pred_res.recovery_probability,
            authoritative_amount=target_tx.amount,
            db=session,
        )
        contract = dec_res.action_contract
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="DECISION_RECOMMENDED",
            actor="llm_recommendation_engine",
            input_snapshot={"llm_claims": dec_res.raw_llm_claims},
            output_snapshot={
                "action_type": contract.action_type.value,
                "channel": contract.channel.value,
                "delay_hours": contract.delay_hours,
                "authoritative_amount": float(contract.amount),
                "authoritative_ev": float(contract.expected_value),
            },
            reason_codes=contract.reason_codes,
            db=session,
        )

        # --- Stage 6: POLICY_EVALUATED ---
        pol_trace = evaluate_policy(contract, dec_res.decision_id, db=session)
        log_audit_event(
            transaction_id=target_tx.id,
            event_type="POLICY_EVALUATED",
            actor="policy_engine",
            input_snapshot={"contract_amount": float(contract.amount), "action": contract.action_type.value},
            output_snapshot={"verdict": pol_trace.verdict.value, "checks_count": len(pol_trace.check_results)},
            reason_codes=pol_trace.reasons,
            policy_result=pol_trace.verdict.value,
            db=session,
        )

        # --- Stage 7: ACTION_EXECUTED (Only if APPROVED) ---
        if pol_trace.verdict.value == "APPROVED":
            exec_res = execute_action(contract)
            db_action = Action(
                id=uuid.uuid4(),
                transaction_id=target_tx.id,
                decision_id=dec_res.decision_id,
                action_type=contract.action_type.value,
                status=ActionStatus.EXECUTED,
                executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(db_action)
            session.commit()

            log_audit_event(
                transaction_id=target_tx.id,
                event_type="ACTION_EXECUTED",
                actor="action_executor",
                input_snapshot={"action_type": contract.action_type.value, "channel": contract.channel.value},
                output_snapshot=exec_res,
                reason_codes=["ACTION_DISPATCHED_TO_MOCK"],
                db=session,
            )

            # --- Stage 8: OUTCOME_VERIFIED ---
            verif_out = verify_action_outcome(
                action_id=db_action.id,
                transaction_id=target_tx.id,
                action_type=contract.action_type.value,
                amount=contract.amount,
                customer_reliability=0.85,
                failure_code=target_tx.failure_code,
                payment_method="UPI",
                policy_context=contract.policy_context,
                db=session,
                seed=77,
            )

            log_audit_event(
                transaction_id=target_tx.id,
                event_type="OUTCOME_VERIFIED",
                actor="verification_engine",
                input_snapshot={"action_id": str(db_action.id), "simulator": "hidden_outcome_function"},
                output_snapshot={
                    "outcome": verif_out.outcome.value,
                    "simulated_amount_recovered": float(verif_out.simulated_amount_recovered),
                },
                reason_codes=[f"SIMULATOR_OUTCOME_{verif_out.outcome.value.upper()}"],
                db=session,
            )

        # -------------------------------------------------------------
        # AGENT REPLAY RECONSTRUCTION PURELY FROM audit_events TABLE
        # -------------------------------------------------------------
        print("\n" + "-" * 65, flush=True)
        print(f"RECONSTRUCTING AGENT REPLAY FOR TRANSACTION {target_tx.id}", flush=True)
        print("  (Queried 100% purely from `audit_events` table - zero other tables used)", flush=True)
        print("-" * 65, flush=True)

        replay = get_agent_replay(transaction_id=target_tx.id, db=session)

        for step in replay:
            print(f"\n[STEP {step['step']}: {step['event_type']}]", flush=True)
            print(f"  Timestamp:     {step['timestamp']}", flush=True)
            print(f"  Actor:         {step['actor']}", flush=True)
            if step["policy_result"]:
                print(f"  Policy Result: {step['policy_result']}", flush=True)
            print(f"  Reason Codes:  {step['reason_codes']}", flush=True)
            print(f"  Input:         {json.dumps(step['input_snapshot'])}", flush=True)
            print(f"  Output:        {json.dumps(step['output_snapshot'])}", flush=True)

        assert len(replay) == 8, f"Expected full 8-stage audit trail, found {len(replay)} steps"
        print("\n" + "=" * 65, flush=True)
        print("PHASE 8 VERIFICATION COMPLETE: ALL CHECKS PASSED!", flush=True)
        print("=" * 65, flush=True)

    finally:
        session.close()


if __name__ == "__main__":
    run_phase8_verification()
