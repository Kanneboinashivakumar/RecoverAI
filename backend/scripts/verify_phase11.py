#!/usr/bin/env python3
"""
Phase 11 Verification Script — India-Specific Depth.

Verifies:
1. Mandate Lifecycle Modeling: End-to-end state machine trace.
2. Visibly Distinct Logic Paths: Card retries vs UPI Mandate retries under NPCI regulations.
3. Revoked/Expired Mandate Guardrail: Deterministic prohibition of standard retries (Check 6).
4. Contextual Hinglish Customer Messaging: 3 distinctly different live LLM examples.
5. Regression Check: All 5 original Phase 7 policy checks independently re-verified.
"""

import os
import sys
import uuid
from decimal import Decimal
from typing import Any, Dict

# Add backend root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.mandate.lifecycle import trace_mandate_lifecycle
from app.domain.mandate.messaging import generate_contextual_hinglish_message
from app.domain.mandate.models import MandateState
from app.domain.mandate.state_machine import (
    evaluate_mandate_eligibility,
    evaluate_payment_method_recovery_path,
)
from app.engines.decision import ActionType, Channel, RecoveryAction
from app.engines.policy import PolicyVerdict, evaluate_policy
from app.models.tables import Decision


def banner(title: str):
    print("\n" + "=" * 75)
    print(f"  {title}")
    print("=" * 75)


def create_decision_record(db, decision_id, tx_id, action_type="RETRY", amount=1000.0, channel="UPI"):
    from datetime import datetime, timezone
    dec = Decision(
        id=decision_id,
        transaction_id=tx_id,
        action_type=action_type,
        channel=channel,
        delay_hours=1,
        amount=Decimal(str(amount)),
        confidence_llm=0.8,
        expected_value_llm=Decimal(str(amount * 0.5)),
        expected_value_verified=Decimal(str(amount * 0.5)),
        reason_codes=["AUDIT_TEST"],
        policy_context={},
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(dec)
    db.commit()
    return dec


def part1_mandate_lifecycle_trace():
    banner("PART 1: UPI MANDATE LIFECYCLE STATE MACHINE TRACE")
    print("Simulating full lifecycle for a recurring subscription mandate debit failure...\n")

    tx_id = str(uuid.uuid4())
    trace = trace_mandate_lifecycle(
        transaction_id=tx_id,
        failure_code="UPI_MANDATE_FAILED",
        amount=1499.00,
        prior_retry_count=0,
        delay_hours=0,
    )

    print(f"Transaction ID: {tx_id}")
    print(f"Total Lifecycle State Transitions: {len(trace)}\n")

    for ev in trace:
        print(f"  [Step {ev.step}: {ev.event_name}]")
        print(f"    Transition: {ev.from_state.value} -> {ev.to_state.value}")
        print(f"    Actor:      {ev.actor}")
        print(f"    Timestamp:  {ev.timestamp}")
        print(f"    Details:    {ev.details}\n")

    # Confirm key lifecycle states are hit
    states = [ev.to_state for ev in trace]
    assert MandateState.ACTIVE in states, "Mandate never reached ACTIVE state!"
    assert MandateState.DEBIT_ATTEMPTED in states, "Debit attempt was not recorded!"
    assert MandateState.DEBIT_FAILED_TRANSIENT in states, "Debit failure state missing!"
    assert MandateState.RETRY_ELIGIBILITY_CHECK in states, "Eligibility check state missing!"
    assert MandateState.RETRY_WINDOW_ACTIVE in states, "NPCI 24h cooling-off window state missing!"

    print("PART 1 VERIFICATION: PASS (Complete 5-stage mandate state machine progression verified)")
    return True


def part2_distinct_logic_paths():
    banner("PART 2: CARD RETRIES VS UPI MANDATE RETRIES (DISTINCT LOGIC PATHS)")
    print("Directly contrasting recovery logic between Card and UPI Mandate under identical failure scenarios:\n")

    scenarios = [
        ("CARD", "ISSUER_TIMEOUT", "Card Gateway Timeout"),
        ("MANDATE", "UPI_MANDATE_FAILED", "Mandate Core Banking Switch Timeout"),
        ("CARD", "CARD_EXPIRED", "Card Instrument Expiry"),
        ("MANDATE", "MANDATE_REVOKED", "Customer Revoked Recurring AutoPay Mandate"),
    ]

    for pm, fc, desc in scenarios:
        path = evaluate_payment_method_recovery_path(pm, fc)
        print(f"Scenario: {desc}")
        print(f"  Payment Method:            {path.payment_method}")
        print(f"  Failure Code:              {path.failure_code}")
        print(f"  Allows Immediate Retry:    {path.allows_immediate_retry}")
        print(f"  Recommended Delay:         {path.recommended_retry_delay_hours} hours")
        print(f"  Requires Re-registration:  {path.requires_re_registration}")
        print(f"  Governing Regulatory Body: {path.governing_framework}")
        print(f"  Allowed Actions:           {path.allowed_actions}")
        print(f"  Prohibited Actions:        {path.prohibited_actions}")
        print(f"  Regulatory Explanation:    {path.explanation}\n")

    # Verify structural distinctions
    card_timeout = evaluate_payment_method_recovery_path("CARD", "ISSUER_TIMEOUT")
    mandate_timeout = evaluate_payment_method_recovery_path("MANDATE", "UPI_MANDATE_FAILED")
    assert card_timeout.allows_immediate_retry is True, "Card should allow immediate retry"
    assert mandate_timeout.allows_immediate_retry is False, "Mandate must NOT allow immediate retry under NPCI rules"
    assert mandate_timeout.recommended_retry_delay_hours == 24, "Mandate retry must observe 24h cooling off"

    mandate_revoked = evaluate_payment_method_recovery_path("MANDATE", "MANDATE_REVOKED")
    assert "RETRY" in mandate_revoked.prohibited_actions, "Revoked mandate must strictly prohibit RETRY"
    assert mandate_revoked.requires_re_registration is True, "Revoked mandate requires re-registration"

    print("PART 2 VERIFICATION: PASS (Visibly distinct logic paths between Card and Mandate verified)")
    return True


def part3_mandate_policy_guardrail():
    banner("PART 3: REVOKED & EXPIRED MANDATE GUARDRAIL (CHECK 6 IN POLICY ENGINE)")
    print("Testing Policy Engine Check 6 (check_mandate_compliance) on mandate transactions:\n")

    db = SessionLocal()
    try:
        # Get 4 distinct clean transactions for 3A, 3B, 3C, 3D
        rows = db.execute(text("""
            SELECT t.id FROM transactions t
            LEFT JOIN decisions d ON d.transaction_id = t.id
            WHERE t.status = 'failed' AND d.id IS NULL
            LIMIT 4 OFFSET 20
        """)).fetchall()
        if len(rows) < 4:
            raise RuntimeError("Not enough clean failed transactions in DB for isolated testing")
        tx_3a, tx_3b, tx_3c, tx_3d = rows[0][0], rows[1][0], rows[2][0], rows[3][0]

        # Test Case 3A: Prohibited RETRY on Revoked Mandate -> BLOCKED
        c_revoked_retry = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(tx_3a),
            amount=Decimal("2999.00"),
            channel=Channel.UPI,
            delay_hours=24,
            reason_codes=["AUDIT_TEST"],
            confidence=0.85,
            expected_value=Decimal("2500.00"),
            policy_context={
                "payment_method": "MANDATE",
                "failure_code": "MANDATE_REVOKED",
            },
        )
        did_3a = uuid.uuid4()
        create_decision_record(db, did_3a, tx_3a, "RETRY", 2999.0, "UPI")
        res_3a = evaluate_policy(contract=c_revoked_retry, decision_id=did_3a, db=db)
        print("  [Case 3A: RETRY on MANDATE_REVOKED]")
        print(f"    Verdict:       {res_3a.verdict} (Expected: BLOCKED)")
        print(f"    Reason Codes:  {res_3a.reasons}")
        assert res_3a.verdict == PolicyVerdict.BLOCKED
        assert "MANDATE_REVOKED_RETRY_PROHIBITED" in res_3a.reasons

        # Test Case 3B: Prohibited RETRY on Expired Mandate -> BLOCKED
        c_expired_retry = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(tx_3b),
            amount=Decimal("1200.00"),
            channel=Channel.UPI,
            delay_hours=24,
            reason_codes=["AUDIT_TEST"],
            confidence=0.85,
            expected_value=Decimal("1000.00"),
            policy_context={
                "payment_method": "MANDATE",
                "failure_code": "MANDATE_EXPIRED",
            },
        )
        did_3b = uuid.uuid4()
        create_decision_record(db, did_3b, tx_3b, "RETRY", 1200.0, "UPI")
        res_3b = evaluate_policy(contract=c_expired_retry, decision_id=did_3b, db=db)
        print("\n  [Case 3B: RETRY on MANDATE_EXPIRED]")
        print(f"    Verdict:       {res_3b.verdict} (Expected: BLOCKED)")
        print(f"    Reason Codes:  {res_3b.reasons}")
        assert res_3b.verdict == PolicyVerdict.BLOCKED
        assert "MANDATE_EXPIRED_RETRY_PROHIBITED" in res_3b.reasons

        # Test Case 3C: RETRY with Sub-24h Delay on Mandate -> BLOCKED (NPCI Window Violation)
        c_sub24_retry = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(tx_3c),
            amount=Decimal("1500.00"),
            channel=Channel.UPI,
            delay_hours=2,  # Sub-24h delay
            reason_codes=["AUDIT_TEST"],
            confidence=0.85,
            expected_value=Decimal("1200.00"),
            policy_context={
                "payment_method": "MANDATE",
                "failure_code": "UPI_MANDATE_FAILED",
            },
        )
        did_3c = uuid.uuid4()
        create_decision_record(db, did_3c, tx_3c, "RETRY", 1500.0, "UPI")
        res_3c = evaluate_policy(contract=c_sub24_retry, decision_id=did_3c, db=db)
        print("\n  [Case 3C: RETRY on Mandate with delay_hours=2 (< 24h)]")
        print(f"    Verdict:       {res_3c.verdict} (Expected: BLOCKED)")
        print(f"    Reason Codes:  {res_3c.reasons}")
        assert res_3c.verdict == PolicyVerdict.BLOCKED
        assert "MANDATE_NPCI_WINDOW_VIOLATION" in res_3c.reasons

        # Test Case 3D: Valid Re-Registration WHATSAPP outreach on Revoked Mandate -> APPROVED
        c_revoked_wa = RecoveryAction(
            action_type=ActionType.WHATSAPP,
            transaction_id=str(tx_3d),
            amount=Decimal("2999.00"),
            channel=Channel.WHATSAPP,
            delay_hours=0,
            reason_codes=["AUDIT_TEST"],
            confidence=0.85,
            expected_value=Decimal("2500.00"),
            policy_context={
                "payment_method": "MANDATE",
                "failure_code": "MANDATE_REVOKED",
                "action_already_taken": False,
                "prior_contacts_24h": 0,
            },
        )
        did_3d = uuid.uuid4()
        create_decision_record(db, did_3d, tx_3d, "WHATSAPP", 2999.0, "WHATSAPP")
        res_3d = evaluate_policy(contract=c_revoked_wa, decision_id=did_3d, db=db)
        print("\n  [Case 3D: WHATSAPP Re-registration Outreach on MANDATE_REVOKED]")
        print(f"    Verdict:       {res_3d.verdict} (Expected: APPROVED)")
        print(f"    Reason Codes:  {res_3d.reasons}")
        assert res_3d.verdict == PolicyVerdict.APPROVED

    finally:
        db.close()

    print("\nPART 3 VERIFICATION: PASS (Mandate regulatory guardrails deterministically enforced)")
    return True


def part4_contextual_hinglish_messaging():
    banner("PART 4: CONTEXTUAL HINGLISH CUSTOMER MESSAGING (3 DISTINCT EXAMPLES)")
    print("Generating 3 live, non-templated Hinglish messages via Gemini API (fails loudly if LLM unavailable):\n")

    examples = [
        {
            "label": "Example 1: Mandate Bank Timeout -> WhatsApp Notification with 24h Auto-Retry Notice",
            "failure_code": "UPI_MANDATE_FAILED",
            "action_type": "WHATSAPP",
            "amount": 1499.00,
            "channel": "WHATSAPP",
            "merchant_name": "Hotstar Premium",
        },
        {
            "label": "Example 2: Checkout Abandoned -> WhatsApp Incentive with 10% Discount Coupon",
            "failure_code": "CHECKOUT_ABANDONED",
            "action_type": "DISCOUNT",
            "amount": 3499.00,
            "channel": "WHATSAPP",
            "merchant_name": "Urban Company",
        },
        {
            "label": "Example 3: Mandate Revoked by Customer -> Email with 1-Click Re-Authorization Link",
            "failure_code": "MANDATE_REVOKED",
            "action_type": "EMAIL",
            "amount": 899.00,
            "channel": "EMAIL",
            "merchant_name": "Cult.fit Live",
        },
    ]

    messages = []
    for idx, ex in enumerate(examples, 1):
        print(f"[{ex['label']}]")
        print(f"  Failure: {ex['failure_code']} | Action: {ex['action_type']} | Amount: ₹{ex['amount']:,.2f}")

        # Calls Gemini API — fails loudly if LLM fails (allow_mock=False)
        msg = generate_contextual_hinglish_message(
            failure_code=ex["failure_code"],
            action_type=ex["action_type"],
            amount=ex["amount"],
            channel=ex["channel"],
            merchant_name=ex["merchant_name"],
            allow_mock=False,
        )
        print(f"  Generated Hinglish Message:\n    \"{msg}\"\n")
        messages.append(msg)

    # Prove meaningful difference across all 3 messages
    assert len(set(messages)) == 3, "Generated Hinglish messages must be distinct!"
    for msg in messages:
        assert "Aapka payment fail ho gaya" not in msg, "Canned template detected!"
        assert len(msg.split()) >= 10, "Message is too brief to be contextual!"

    print("PART 4 VERIFICATION: PASS (3 distinctly contextual Hinglish messages generated via live LLM)")
    return True


def part5_phase7_regression_check():
    banner("PART 5: PHASE 7 REGRESSION CHECK (RE-VERIFY ALL 5 ORIGINAL GUARDRAILS)")
    print("Confirming none of Phase 7's 5 original guardrails regressed after adding Check 6:\n")

    db = SessionLocal()
    try:
        clean_rows = db.execute(text("""
            SELECT t.id, t.amount, t.payment_method, t.failure_code
            FROM transactions t
            LEFT JOIN decisions d ON d.transaction_id = t.id
            WHERE t.status = 'failed' AND d.id IS NULL
            LIMIT 5
        """)).fetchall()

        if len(clean_rows) < 5:
            print("  FAIL: Not enough clean transactions for regression test")
            return False

        def test_guardrail(name, contract, test_tx_id, expected_verdict, expected_reason):
            did = uuid.uuid4()
            create_decision_record(db, did, test_tx_id, contract.action_type.value, float(contract.amount),
                                   contract.channel.value if hasattr(contract.channel, 'value') else contract.channel)
            eval_result = evaluate_policy(contract=contract, decision_id=did, db=db)
            passed = (eval_result.verdict == expected_verdict and expected_reason in eval_result.reasons)
            print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
            print(f"         Verdict: {eval_result.verdict} (expected: {expected_verdict})")
            print(f"         Reasons: {eval_result.reasons} (expected contains: {expected_reason})")
            return passed

        results = []

        # Check 1: Amount Tier Ceiling (> 25k)
        t1 = clean_rows[0]
        c1 = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(t1[0]),
            amount=Decimal("35000.00"),
            channel=Channel.UPI,
            delay_hours=1,
            reason_codes=["REGRESSION_TEST"],
            confidence=0.85,
            expected_value=Decimal("15000.00"),
        )
        results.append(test_guardrail(
            "Check 1: Amount Tier Ceiling (> ₹25,000)",
            c1, t1[0], PolicyVerdict.ESCALATED, "AMOUNT_TIER_HUMAN_ONLY"
        ))

        # Check 2: Retry Limit (prior retries >= 2)
        t2 = clean_rows[1]
        c2 = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(t2[0]),
            amount=Decimal("1500.00"),
            channel=Channel.UPI,
            delay_hours=1,
            reason_codes=["REGRESSION_TEST"],
            confidence=0.85,
            expected_value=Decimal("1200.00"),
            policy_context={"prior_retry_count": 2},
        )
        results.append(test_guardrail(
            "Check 2: Retry Limit Guardrail (prior retries >= 2)",
            c2, t2[0], PolicyVerdict.BLOCKED, "RETRY_LIMIT_REACHED"
        ))

        # Check 3: Contact Frequency (prior contacts >= 2)
        t3 = clean_rows[2]
        c3 = RecoveryAction(
            action_type=ActionType.WHATSAPP,
            transaction_id=str(t3[0]),
            amount=Decimal("2500.00"),
            channel=Channel.WHATSAPP,
            delay_hours=1,
            reason_codes=["REGRESSION_TEST"],
            confidence=0.80,
            expected_value=Decimal("2000.00"),
            policy_context={"prior_contacts_24h": 2},
        )
        results.append(test_guardrail(
            "Check 3: Contact Frequency Guardrail (prior contacts >= 2)",
            c3, t3[0], PolicyVerdict.BLOCKED, "CONTACT_FREQUENCY_EXCEEDED"
        ))

        # Check 4: Discount Limit (proposed discount > 10%)
        t4 = clean_rows[3]
        c4 = RecoveryAction(
            action_type=ActionType.DISCOUNT,
            transaction_id=str(t4[0]),
            amount=Decimal("4000.00"),
            channel=Channel.UPI,
            delay_hours=0,
            reason_codes=["REGRESSION_TEST"],
            confidence=0.90,
            expected_value=Decimal("3200.00"),
            policy_context={"discount_pct": 0.25},
        )
        results.append(test_guardrail(
            "Check 4: Discount Limit Guardrail (proposed discount > 10%)",
            c4, t4[0], PolicyVerdict.BLOCKED, "DISCOUNT_LIMIT_EXCEEDED"
        ))

        # Check 5: Action Idempotency (duplicate action)
        t5 = clean_rows[4]
        c5 = RecoveryAction(
            action_type=ActionType.RETRY,
            transaction_id=str(t5[0]),
            amount=Decimal("1000.00"),
            channel=Channel.UPI,
            delay_hours=1,
            reason_codes=["REGRESSION_TEST"],
            confidence=0.85,
            expected_value=Decimal("800.00"),
            policy_context={"action_already_taken": True},
        )
        results.append(test_guardrail(
            "Check 5: Action Idempotency Guardrail (duplicate action)",
            c5, t5[0], PolicyVerdict.BLOCKED, "ACTION_ALREADY_TAKEN"
        ))

    finally:
        db.close()

    all_passed = all(results)
    print(f"\nPART 5 VERIFICATION: {'PASS' if all_passed else 'FAIL'} (All 5 original Phase 7 checks verified without regression)")
    return all_passed


def main():
    print("\n" + "=" * 75)
    print("  PHASE 11: INDIA-SPECIFIC DEPTH VERIFICATION SUITE")
    print("=" * 75)

    p1 = part1_mandate_lifecycle_trace()
    p2 = part2_distinct_logic_paths()
    p3 = part3_mandate_policy_guardrail()
    p4 = part4_contextual_hinglish_messaging()
    p5 = part5_phase7_regression_check()

    banner("PHASE 11 FINAL SUMMARY")
    print(f"  Part 1 (Mandate Lifecycle Trace):              {'PASS' if p1 else 'FAIL'}")
    print(f"  Part 2 (Card vs Mandate Logic Distinction):    {'PASS' if p2 else 'FAIL'}")
    print(f"  Part 3 (Mandate Policy Guardrails - Check 6):  {'PASS' if p3 else 'FAIL'}")
    print(f"  Part 4 (Contextual Hinglish LLM Messaging):    {'PASS' if p4 else 'FAIL'}")
    print(f"  Part 5 (Phase 7 Non-Regression Suite):         {'PASS' if p5 else 'FAIL'}")

    all_ok = p1 and p2 and p3 and p4 and p5
    print("\n" + "=" * 75)
    print(f"  OVERALL RESULT: {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    print("=" * 75 + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
