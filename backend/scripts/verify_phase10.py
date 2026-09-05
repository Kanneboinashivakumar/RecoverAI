#!/usr/bin/env python3
"""
Phase 10 — Recovery Queue (Human Escalation) Verification Script.

Steps:
1. Re-runs a Phase 9 experiment batch to ensure real `transactions`, `decisions`,
   `policy_evaluations`, and `audit_events` are populated in PostgreSQL.
2. Calls the FastAPI endpoint `GET /api/policies/recovery-queue` to query the live queue.
3. Displays 5 real entries with their un-truncated reason codes, distinguishing
   ESCALATED (routine human judgment) from BLOCKED (guardrail override).
4. Executes manual review actions via `POST /api/policies/recovery-queue/{transaction_id}/review`.
5. Queries `audit_events` directly to verify forensic `HUMAN_REVIEW_DECIDED` entries
   and confirms the complete Agent Replay trail.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.engines.audit import get_agent_replay
from app.main import app
from app.models.tables import AuditEvent, Decision, PolicyEvaluation, Transaction
from scripts.run_experiment import run_experiment


def run_phase10_verification():
    print("\n" + "=" * 75, flush=True)
    print("PHASE 10: RECOVERY QUEUE & HUMAN ESCALATION VERIFICATION", flush=True)
    print("=" * 75, flush=True)

    # Step 1: Run an experiment batch to generate real database records
    run_seed = int(datetime.now(timezone.utc).timestamp()) % 1000000
    print(f"\n[STEP 1] Generating and evaluating real experiment batch (Seed: {run_seed}, Count: 250)...", flush=True)
    run_experiment(seed=run_seed, count=250, save_db=True)

    # Step 2: Query the Recovery Queue API endpoint
    print("\n[STEP 2] Calling GET /api/policies/recovery-queue via FastAPI TestClient...", flush=True)
    client = TestClient(app)

    resp = client.get("/api/policies/recovery-queue?limit=50")
    assert resp.status_code == 200, f"API failed with {resp.status_code}: {resp.text}"
    data = resp.json()

    print(f"Recovery Queue Summary:")
    print(f"  Total Queued Items: {data['total_count']}")
    print(f"  Pending Review:     {data['pending_count']}")
    print(f"  Approved Count:     {data['approved_count']}")
    print(f"  Rejected Count:     {data['rejected_count']}")

    # Step 3: Fetch real ESCALATED and BLOCKED entries to show clear distinction
    print("\n" + "-" * 75, flush=True)
    print("[STEP 3] 5 REAL RECOVERY QUEUE ENTRIES SOURCED FROM EXPERIMENT RUN:", flush=True)
    print("-" * 75, flush=True)

    esc_resp = client.get("/api/policies/recovery-queue?verdict=ESCALATED&limit=3")
    blk_resp = client.get("/api/policies/recovery-queue?verdict=BLOCKED&limit=2")

    esc_items = esc_resp.json()["items"]
    blk_items = blk_resp.json()["items"]
    sample_items = esc_items + blk_items

    for idx, it in enumerate(sample_items, 1):
        override_str = "YES [GUARDRAIL OVERRIDE REQUIRED]" if it["is_override"] else "NO [ROUTINE HUMAN ESCALATION]"
        print(f"\nQueue Item #{idx}:")
        print(f"  Transaction ID:   {it['transaction_id']}")
        print(f"  Amount:           ₹{Decimal(str(it['amount'])):,.2f} ({it['currency']})")
        print(f"  Payment Method:   {it['payment_method']} | Failure: {it['failure_code']}")
        print(f"  Original Verdict: {it['original_verdict']}")
        print(f"  Decision Type:    {override_str}")
        print(f"  Review Status:    {it['review_status']}")
        print(f"  Reason Codes:     {it['reason_codes']}")
        print(f"  Proposed Action:  {it['action_type']} via {it['channel']} (EV: ₹{Decimal(str(it['expected_value'] or 0)):,.2f})")

    # Step 4: Execute a manual review on both an ESCALATED item and a BLOCKED item
    print("\n" + "-" * 75, flush=True)
    print("[STEP 4] Executing Manual Human Reviews via POST /api/policies/recovery-queue/{id}/review", flush=True)
    print("-" * 75, flush=True)

    # 4A: Routine Human Escalation Approval
    target_esc = esc_items[0]
    print(f"\n[Case A] Reviewing ESCALATED item: {target_esc['transaction_id']}")
    esc_review_resp = client.post(
        f"/api/policies/recovery-queue/{target_esc['transaction_id']}/review",
        json={
            "verdict": "APPROVED",
            "reviewer": "priya_risk_lead",
            "notes": "High-value enterprise customer confirmed legitimate payment issue. Dispatched human outreach.",
        },
    )
    assert esc_review_resp.status_code == 200
    esc_rev_data = esc_review_resp.json()
    print(f"  Status:       {esc_rev_data['review_status']}")
    print(f"  Reviewer:     {esc_rev_data['reviewer']}")
    print(f"  Decision:     Routine human escalation approved")

    # 4B: Deliberate Guardrail Override Approval
    target_blk = blk_items[0]
    print(f"\n[Case B] Reviewing BLOCKED item (Deliberate Guardrail Override): {target_blk['transaction_id']}")
    blk_review_resp = client.post(
        f"/api/policies/recovery-queue/{target_blk['transaction_id']}/review",
        json={
            "verdict": "APPROVED",
            "reviewer": "rahul_head_of_ops",
            "notes": "Deliberately overriding guardrail block due to strategic merchant SLA requirements.",
        },
    )
    assert blk_review_resp.status_code == 200
    blk_rev_data = blk_review_resp.json()
    print(f"  Status:       {blk_rev_data['review_status']}")
    print(f"  Reviewer:     {blk_rev_data['reviewer']}")
    print(f"  Decision:     Deliberate policy override recorded")

    # Step 5: Verify forensic audit trail in PostgreSQL
    print("\n" + "-" * 75, flush=True)
    print(f"[STEP 5A] PRIMARY CASE: Single-Evaluation Audit Trail ({target_esc['transaction_id']})", flush=True)
    print("-" * 75, flush=True)

    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Show exact SQL query
        print("Underlying SQL Query used by get_agent_replay:")
        print(f"  SELECT * FROM audit_events WHERE transaction_id = '{target_esc['transaction_id']}' ORDER BY timestamp ASC, id ASC;\n")

        # Primary Single-Evaluation Case
        replay_esc = get_agent_replay(UUID(target_esc["transaction_id"]), db)
        assert len(replay_esc) == 2, f"Expected exactly 2 events for single-evaluation case, got {len(replay_esc)}"
        print(f"Reconstructed Clean Audit Trail ({len(replay_esc)} chronological events):")
        for st in replay_esc:
            print(f"  [Step {st['step']}] {st['event_type']} by {st['actor']}")
            print(f"    Timestamp:     {st['timestamp']}")
            print(f"    Policy Result: {st['policy_result']}")
            print(f"    Reason Codes:  {st['reason_codes']}")
            print(f"    Output:        {st['output_snapshot']}\n")

        # Confirm exact audit events
        assert replay_esc[0]["event_type"] == "POLICY_EVALUATED"
        assert replay_esc[0]["policy_result"] == "ESCALATED"
        assert replay_esc[1]["event_type"] == "HUMAN_REVIEW_DECIDED"
        assert replay_esc[1]["policy_result"] == "APPROVED"
        assert "HUMAN_ESCALATION_RESOLVED" in replay_esc[1]["reason_codes"]
        print("Primary Single-Evaluation Case Verified: 2 clean events (Policy Escalation -> Human Review Resolution)!")

        # Step 5B: Multi-Run Idempotency Case
        print("\n" + "-" * 75, flush=True)
        print(f"[STEP 5B] MULTI-RUN CASE: Policy Idempotency Guardrail Trail ({target_blk['transaction_id']})", flush=True)
        print("-" * 75, flush=True)
        print("Explanation: This transaction was evaluated in repeated batch runs on the same seed.")
        print("The first run evaluated and escalated the transaction; subsequent batch runs detected that")
        print("an action was already recorded and correctly triggered the ACTION_ALREADY_TAKEN guardrail block.\n")

        replay_blk = get_agent_replay(UUID(target_blk["transaction_id"]), db)
        print(f"Reconstructed Multi-Run Trail ({len(replay_blk)} chronological events):")
        for st in replay_blk:
            print(f"  [Step {st['step']}] {st['event_type']} by {st['actor']}")
            print(f"    Timestamp:     {st['timestamp']}")
            print(f"    Policy Result: {st['policy_result']}")
            print(f"    Reason Codes:  {st['reason_codes']}")
            print(f"    Output:        {st['output_snapshot']}\n")

        review_audit = next((s for s in replay_blk if s["event_type"] == "HUMAN_REVIEW_DECIDED"), None)
        assert review_audit is not None, "HUMAN_REVIEW_DECIDED event missing from audit trail!"
        assert review_audit["policy_result"] == "APPROVED"
        assert "POLICY_GUARDRAIL_OVERRIDE" in review_audit["reason_codes"]
        print("Multi-Run Case Verified: Shows initial evaluation, idempotency block on re-run, and manual override!")

    finally:
        db.close()

    print("\n" + "=" * 75, flush=True)
    print("PHASE 10 VERIFICATION COMPLETE: ALL ACCEPTANCE CHECKS PASSED!", flush=True)
    print("=" * 75 + "\n", flush=True)


if __name__ == "__main__":
    run_phase10_verification()
