#!/usr/bin/env python3
"""
Phase 7 Verification Script — Policy / Guardrail Engine.

Demonstrates:
  1. Batch evaluation of 20 Action Contracts (reporting APPROVED / BLOCKED / ESCALATED).
  2. Individual violation test for EACH of the 5 checks (amount tier, retry limit, contact limit, discount limit, idempotency).
  3. Dynamic policy configuration update (changing discount limit at runtime).

Usage:
    docker compose exec backend python scripts/verify_phase7.py
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
from app.engines.decision import (
    ActionType,
    Channel,
    RecoveryAction,
    recommend_recovery_action,
)
from app.engines.diagnosis import diagnose_failure
from app.engines.expected_value import calculate_expected_value
from app.engines.policy import (
    DEFAULT_POLICY_CONFIG,
    PolicyVerdict,
    evaluate_policy,
    load_policy_config,
    update_policy_config_in_db,
)
from app.engines.prediction import METRICS_PATH, MODEL_PATH, predict_recovery_probability
from app.models.tables import Customer, Decision, PolicyEvaluation, Transaction
from scripts.train_model import train_and_evaluate


def run_phase7_verification():
    print("\n" + "=" * 65, flush=True)
    print("PHASE 7: POLICY & GUARDRAIL ENGINE VERIFICATION", flush=True)
    print("=" * 65, flush=True)

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
        print("Model artifacts not found. Initiating model training pipeline...", flush=True)
        train_and_evaluate(n_samples=12000, seed=42)

    try:
        # Reset decisions and policy_evaluations to ensure clean state for batch evaluation
        session.query(PolicyEvaluation).delete()
        session.query(Decision).delete()
        session.commit()

        # -------------------------------------------------------------
        # PART 1: 20 Action Contracts through Policy Engine
        # -------------------------------------------------------------
        print("\n" + "-" * 65, flush=True)
        print("PART 1: BATCH EVALUATION (20 ACTION CONTRACTS)", flush=True)
        print("-" * 65, flush=True)

        txs = (
            session.query(Transaction)
            .filter(Transaction.status == "failed")
            .limit(30)
            .all()
        )

        if len(txs) < 20:
            print("Not enough transactions in DB. Please run Phase 2 generator first.", flush=True)
            sys.exit(1)

        results_summary = {"APPROVED": 0, "BLOCKED": 0, "ESCALATED": 0}

        for idx, tx in enumerate(txs[:20], 1):
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

            diagnosis = diagnose_failure(tx.failure_code)
            pred_out = predict_recovery_probability({
                "amount": float(tx.amount),
                "account_age_days": cust.account_age_days if cust else 180,
                "lifetime_tx_count": cust.lifetime_tx_count if cust else 10,
                "failed_count": cust.failed_count if cust else 2,
                "failure_rate": round(cust.failed_count / max(1, cust.lifetime_tx_count), 4) if cust else 0.2,
                "avg_transaction_value": float(cust.avg_transaction_value) if cust and cust.avg_transaction_value else 1000.0,
                "upi_usage_pct": cust.upi_usage_pct if cust else 0.5,
                "card_usage_pct": cust.card_usage_pct if cust else 0.3,
                "hours_since_failure": 2.0,
                "payment_method": tx_dict["payment_method"],
                "failure_code": tx.failure_code,
                "action_type": "RETRY",
            })

            # Recommend contract (Phase 6)
            decision = recommend_recovery_action(
                transaction=tx_dict,
                customer=cust_dict,
                diagnosis=diagnosis,
                recovery_probability=pred_out.recovery_probability,
                authoritative_amount=tx.amount,
                db=session,
            )

            # Evaluate through Policy Engine (Phase 7)
            trace = evaluate_policy(
                contract=decision.action_contract,
                decision_id=decision.decision_id,
                db=session,
            )

            results_summary[trace.verdict.value] += 1
            print(f"[{idx:2d}/20] Tx: {str(tx.id)[:8]}... | Amount: ₹{decision.action_contract.amount:9.2f} | "
                  f"Action: {decision.action_contract.action_type.value:8s} | "
                  f"VERDICT: {trace.verdict.value:9s} | Reason: {', '.join(trace.reasons)}", flush=True)

        print("\nBatch Evaluation Totals:", flush=True)
        print(f"  APPROVED:  {results_summary['APPROVED']:2d} / 20", flush=True)
        print(f"  BLOCKED:   {results_summary['BLOCKED']:2d} / 20", flush=True)
        print(f"  ESCALATED: {results_summary['ESCALATED']:2d} / 20", flush=True)

        # -------------------------------------------------------------
        # PART 2: Specific Real Violation Cases for EACH of the 5 Checks
        # -------------------------------------------------------------
        print("\n" + "=" * 65, flush=True)
        print("PART 2: SPECIFIC VIOLATION CASES FOR EACH OF THE 5 CHECKS", flush=True)
        print("=" * 65, flush=True)

        def make_test_decision(tx_obj, action_type: str, channel: str, amount: Decimal) -> UUID:
            d_id = uuid.uuid4()
            d = Decision(
                id=d_id,
                transaction_id=tx_obj.id,
                action_type=action_type,
                channel=channel,
                delay_hours=0,
                amount=amount,
                confidence_llm=0.8,
                expected_value_llm=amount * Decimal("0.8"),
                expected_value_verified=amount * Decimal("0.8"),
                reason_codes=["POLICY_UNIT_TEST"],
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(d)
            session.commit()
            return d_id

        # --- CHECK 1: Amount Tier Check (High Value > 25k -> ESCALATED) ---
        print("\n[CHECK 1: Amount Tier Autonomy Ceiling]", flush=True)
        tx_c1 = txs[20] if len(txs) > 20 else txs[0]
        c1_decision_id = make_test_decision(tx_c1, "WHATSAPP", "WHATSAPP", Decimal("45000.00"))
        c1_contract = RecoveryAction(
            action_type=ActionType.WHATSAPP,
            transaction_id=str(tx_c1.id),
            amount=Decimal("45000.00"),  # ₹45,000 > ₹25,000 high-tier ceiling
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["HIGH_VALUE_TRANSACTION"],
            confidence=0.85,
            expected_value=Decimal("38000.00"),
            policy_context={},
        )
        t1 = evaluate_policy(c1_contract, c1_decision_id, db=session)
        c1_result = next(c for c in t1.check_results if c.check_name == "amount_tier_check")
        print(f"  Input Amount:   ₹{c1_contract.amount} (Ceiling: ₹25,000.00)", flush=True)
        print(f"  Check Passed:   {c1_result.passed}", flush=True)
        print(f"  Verdict Impact: {c1_result.verdict_impact.value if c1_result.verdict_impact else 'None'}", flush=True)
        print(f"  Reason Code:    {c1_result.reason_code}", flush=True)
        print(f"  Description:    {c1_result.description}", flush=True)
        assert c1_result.passed is False
        assert c1_result.reason_code == "AMOUNT_TIER_HUMAN_ONLY"
        assert t1.verdict == PolicyVerdict.ESCALATED

        # --- CHECK 2: Retry Limit Check (Prior Retries >= 2 -> BLOCKED) ---
        print("\n[CHECK 2: Retry Limit Exceeded]", flush=True)
        tx_c2 = txs[21] if len(txs) > 21 else txs[1]
        c2_decision_id = make_test_decision(tx_c2, "RETRY", "CARD", Decimal("1500.00"))
        c2_contract = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(tx_c2.id),
            amount=Decimal("1500.00"),
            channel=Channel.CARD,
            delay_hours=1,
            reason_codes=["RETRY_ATTEMPT"],
            confidence=0.50,
            expected_value=Decimal("749.00"),
            policy_context={"prior_retry_count": 2},  # 2 retries already attempted (max 2)
        )
        t2 = evaluate_policy(c2_contract, c2_decision_id, db=session)
        c2_result = next(c for c in t2.check_results if c.check_name == "retry_limit_check")
        print(f"  Action Type:    {c2_contract.action_type.value}", flush=True)
        print(f"  Prior Retries:  2 (Allowed cap: 2)", flush=True)
        print(f"  Check Passed:   {c2_result.passed}", flush=True)
        print(f"  Verdict Impact: {c2_result.verdict_impact.value if c2_result.verdict_impact else 'None'}", flush=True)
        print(f"  Reason Code:    {c2_result.reason_code}", flush=True)
        print(f"  Description:    {c2_result.description}", flush=True)
        assert c2_result.passed is False
        assert c2_result.reason_code == "RETRY_LIMIT_REACHED"
        assert t2.verdict == PolicyVerdict.BLOCKED

        # --- CHECK 3: Contact Frequency Check (Prior Contacts 24h >= 2 -> BLOCKED) ---
        print("\n[CHECK 3: Contact Frequency Throttling / Anti-Spam]", flush=True)
        tx_c3 = txs[22] if len(txs) > 22 else txs[2]
        c3_decision_id = make_test_decision(tx_c3, "WHATSAPP", "WHATSAPP", Decimal("1500.00"))
        c3_contract = RecoveryAction(
            action_type=ActionType.WHATSAPP,
            transaction_id=str(tx_c3.id),
            amount=Decimal("1500.00"),
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["CUSTOMER_CONTACT"],
            confidence=0.50,
            expected_value=Decimal("748.50"),
            policy_context={"prior_contacts_24h": 2},  # 2 messages already sent in 24h (cap: 2)
        )
        t3 = evaluate_policy(c3_contract, c3_decision_id, db=session)
        c3_result = next(c for c in t3.check_results if c.check_name == "contact_frequency_check")
        print(f"  Action Channel: {c3_contract.channel.value}", flush=True)
        print(f"  Prior Contacts: 2 in last 24h (Cap: 2)", flush=True)
        print(f"  Check Passed:   {c3_result.passed}", flush=True)
        print(f"  Verdict Impact: {c3_result.verdict_impact.value if c3_result.verdict_impact else 'None'}", flush=True)
        print(f"  Reason Code:    {c3_result.reason_code}", flush=True)
        print(f"  Description:    {c3_result.description}", flush=True)
        assert c3_result.passed is False
        assert c3_result.reason_code == "CONTACT_FREQUENCY_EXCEEDED"
        assert t3.verdict == PolicyVerdict.BLOCKED

        # --- CHECK 4: Discount Limit Check (Proposed discount 20% > 10% ceiling -> BLOCKED) ---
        print("\n[CHECK 4: Discount Rate Ceiling]", flush=True)
        tx_c4 = txs[23] if len(txs) > 23 else txs[3]
        c4_decision_id = make_test_decision(tx_c4, "DISCOUNT", "WHATSAPP", Decimal("2000.00"))
        c4_contract = RecoveryAction(
            action_type=ActionType.DISCOUNT,
            transaction_id=str(tx_c4.id),
            amount=Decimal("2000.00"),
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["OFFER_DISCOUNT"],
            confidence=0.60,
            expected_value=Decimal("800.00"),
            policy_context={"discount_pct": 0.20},  # 20% proposed discount vs 10% policy ceiling
        )
        t4 = evaluate_policy(c4_contract, c4_decision_id, db=session)
        c4_result = next(c for c in t4.check_results if c.check_name == "discount_limit_check")
        print(f"  Proposed Rate:  20.0% (Policy ceiling: 10.0%)", flush=True)
        print(f"  Check Passed:   {c4_result.passed}", flush=True)
        print(f"  Verdict Impact: {c4_result.verdict_impact.value if c4_result.verdict_impact else 'None'}", flush=True)
        print(f"  Reason Code:    {c4_result.reason_code}", flush=True)
        print(f"  Description:    {c4_result.description}", flush=True)
        assert c4_result.passed is False
        assert c4_result.reason_code == "DISCOUNT_LIMIT_EXCEEDED"
        assert t4.verdict == PolicyVerdict.BLOCKED

        # --- CHECK 5: Action Idempotency Check (Duplicate Action -> BLOCKED) ---
        print("\n[CHECK 5: Action Idempotency Duplicate Guardrail]", flush=True)
        tx_c5 = txs[24] if len(txs) > 24 else txs[4]
        # First decision taken on tx_c5
        _ = make_test_decision(tx_c5, "WHATSAPP", "WHATSAPP", Decimal("1500.00"))
        # Second decision attempting the identical action on the same transaction
        c5_second_decision_id = make_test_decision(tx_c5, "WHATSAPP", "WHATSAPP", Decimal("1500.00"))
        c5_contract = RecoveryAction(
            action_type=ActionType.WHATSAPP,
            transaction_id=str(tx_c5.id),
            amount=Decimal("1500.00"),
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["PROMPT_PAYMENT"],
            confidence=0.50,
            expected_value=Decimal("748.50"),
            policy_context={},  # Let it check DB for duplicate decisions
        )
        t5 = evaluate_policy(c5_contract, c5_second_decision_id, db=session)
        c5_result = next(c for c in t5.check_results if c.check_name == "action_idempotency_check")
        print(f"  Action Attempt: {c5_contract.action_type.value} via {c5_contract.channel.value}", flush=True)
        print(f"  Prior Duplicate in DB: True", flush=True)
        print(f"  Check Passed:   {c5_result.passed}", flush=True)
        print(f"  Verdict Impact: {c5_result.verdict_impact.value if c5_result.verdict_impact else 'None'}", flush=True)
        print(f"  Reason Code:    {c5_result.reason_code}", flush=True)
        print(f"  Description:    {c5_result.description}", flush=True)
        assert c5_result.passed is False
        assert c5_result.reason_code == "ACTION_ALREADY_TAKEN"
        assert t5.verdict == PolicyVerdict.BLOCKED

        # -------------------------------------------------------------
        # PART 3: Dynamic Runtime Policy Configuration Update
        # -------------------------------------------------------------
        print("\n" + "=" * 65, flush=True)
        print("PART 3: RUNTIME POLICY CONFIGURATION UPDATE TEST", flush=True)
        print("=" * 65, flush=True)

        print("Testing dynamic policy change: Updating max_discount_pct from 10% to 25%...", flush=True)
        updated_config = dict(DEFAULT_POLICY_CONFIG)
        updated_config["max_discount_pct"] = 0.25
        update_policy_config_in_db(updated_config, db=session)

        # Re-evaluate the exact same 20% discount contract from Check 4
        print(f"Re-evaluating the 20% discount contract under new policy ceiling (25%)...", flush=True)
        tx_retest = txs[25] if len(txs) > 25 else txs[5]
        c4_retest_decision_id = make_test_decision(tx_retest, "DISCOUNT", "WHATSAPP", Decimal("2000.00"))
        c4_retest_contract = RecoveryAction(
            action_type=ActionType.DISCOUNT,
            transaction_id=str(tx_retest.id),
            amount=Decimal("2000.00"),
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["OFFER_DISCOUNT"],
            confidence=0.60,
            expected_value=Decimal("800.00"),
            policy_context={"discount_pct": 0.20},
        )
        t4_retest = evaluate_policy(c4_retest_contract, c4_retest_decision_id, db=session)
        c4_retest_res = next(c for c in t4_retest.check_results if c.check_name == "discount_limit_check")

        print(f"  Proposed Rate:  20.0% (New Ceiling: 25.0%)", flush=True)
        print(f"  Check Passed:   {c4_retest_res.passed}", flush=True)
        print(f"  Verdict:        {t4_retest.verdict.value}", flush=True)
        print(f"  Description:    {c4_retest_res.description}", flush=True)

        assert c4_retest_res.passed is True
        assert t4_retest.verdict == PolicyVerdict.APPROVED
        print("\nDynamic Policy Update Passed: Policy limit updated at runtime and re-run reflected changed behavior.", flush=True)

        # Restore default policy in DB
        update_policy_config_in_db(DEFAULT_POLICY_CONFIG, db=session)
        print("Restored default policy configuration in DB.", flush=True)

        # Check policy_evaluations table in DB
        db_eval_count = (
            session.query(PolicyEvaluation)
            .filter(PolicyEvaluation.decision_id == c4_retest_decision_id)
            .count()
        )
        print(f"\nTraceability Verification: {db_eval_count} individual check rows persisted for test decision.", flush=True)
        assert db_eval_count == 5, "Expected 5 policy evaluation checks in DB"

        print("\n" + "=" * 65, flush=True)
        print("PHASE 7 VERIFICATION COMPLETE: ALL CHECKS PASSED!", flush=True)
        print("=" * 65, flush=True)

    finally:
        session.close()


if __name__ == "__main__":
    run_phase7_verification()
