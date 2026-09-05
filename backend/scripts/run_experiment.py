#!/usr/bin/env python3
"""
Phase 9 & 10 — Baseline vs RecoverAI Evaluation & Experiment Engine.

Runs an apples-to-apples A/B comparison between the fixed-rule baseline policy
and RecoverAI against the identical batch of synthetic failed transactions,
using the same hidden ground-truth simulator instance and seed.

Explicit Labeling (per user requirement):
    RecoverAI's batch decisioning in this experiment uses the deterministic
    EV Engine (Phase 5) + Policy Engine (Phase 7) directly to select and authorize
    the highest-EV action contract at scale, rather than making 1,000 live LLM API calls.
    The per-transaction LLM recommendation pipeline (Phase 6) remains intact for single
    transaction routing.

Primary Metric:
    NET Incremental ₹ Recovered (Gross Recovered minus Total Operational Costs).
    Stored in experiments.incremental_recovered.

Phase 10 Uniform Replay Persistence:
    Every transaction in the batch persists real `decisions`, `policy_evaluations`,
    and `audit_events` rows (via log_audit_event) into PostgreSQL, enabling forensic
    Agent Replay and populating the Recovery Queue for human review.

Usage:
    docker compose exec backend python scripts/run_experiment.py --seed 42 --count 1000
    docker compose exec backend python scripts/run_experiment.py --seed 7 --count 1000
"""

import argparse
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.domain.policies.baseline import get_baseline_action
from app.engines.audit import log_audit_event
from app.engines.decision import ActionType, Channel, RecoveryAction
from app.engines.diagnosis import diagnose_failure
from app.engines.expected_value import calculate_expected_value
from app.engines.policy import PolicyVerdict, evaluate_policy
from app.engines.prediction import METRICS_PATH, MODEL_PATH, predict_recovery_probability
from app.models.tables import (
    Action,
    ActionStatus,
    AuditEvent,
    Customer,
    Decision,
    Diagnosis,
    DiagnosisSource,
    Experiment,
    Merchant,
    PolicyEvaluation,
    PolicyType,
    Prediction,
    Transaction,
    VerificationOutcome,
    VerificationResult,
)
from scripts.simulator import hidden_outcome_function
from scripts.train_model import train_and_evaluate

HARD_DECLINE_CODES = {
    "CARD_EXPIRED",
    "MANDATE_REVOKED",
    "MANDATE_EXPIRED",
    "UPI_CUSTOMER_DECLINED",
    "BANK_DECLINED",
}

FAILURE_CODES_LIST = [
    "UPI_COLLECT_EXPIRED", "UPI_BANK_TIMEOUT", "UPI_INSUFFICIENT_FUNDS", "UPI_PSP_ERROR",
    "UPI_CUSTOMER_DECLINED", "UPI_LIMIT_EXCEEDED", "UPI_MANDATE_FAILED", "UPI_MANDATE_EXPIRED",
    "CARD_EXPIRED", "CARD_DECLINED", "CARD_LIMIT_EXCEEDED", "ISSUER_TIMEOUT", "INSUFFICIENT_FUNDS",
    "BANK_TIMEOUT", "BANK_DECLINED", "SESSION_EXPIRED",
    "MANDATE_REGISTRATION_FAILED", "MANDATE_EXECUTION_FAILED", "MANDATE_REVOKED", "MANDATE_EXPIRED",
    "CHECKOUT_ABANDONED", "PAYMENT_PAGE_EXIT", "OTP_TIMEOUT", "PAYMENT_METHOD_CHANGED",
    "INVOICE_OVERDUE", "PAYMENT_PROMISE_BROKEN", "PARTIAL_PAYMENT",
]

PAYMENT_METHODS_LIST = ["UPI", "CARD", "NETBANKING", "MANDATE"]


def generate_experiment_batch(count: int, seed: int) -> List[Dict[str, Any]]:
    """
    Generates a deterministic synthetic batch of failed transactions.
    Contains both observable features and latent simulation parameters.
    """
    rng = random.Random(seed)
    batch = []

    for idx in range(count):
        # Latent customer reliability (hidden ground truth)
        roll = rng.random()
        if roll < 0.60:
            hidden_reliability = rng.uniform(0.75, 0.95)
            lifetime_tx = rng.randint(10, 80)
            failed_count = rng.randint(0, int(lifetime_tx * 0.20))
            account_age = rng.randint(180, 1500)
            avg_val = rng.uniform(800, 15000)
        elif roll < 0.85:
            hidden_reliability = rng.uniform(0.40, 0.75)
            lifetime_tx = rng.randint(5, 40)
            failed_count = rng.randint(1, int(lifetime_tx * 0.40))
            account_age = rng.randint(30, 400)
            avg_val = rng.uniform(400, 8000)
        else:
            hidden_reliability = rng.uniform(0.10, 0.40)
            lifetime_tx = rng.randint(1, 15)
            failed_count = rng.randint(1, max(1, lifetime_tx))
            account_age = rng.randint(1, 90)
            avg_val = rng.uniform(200, 4000)

        failure_rate = round(failed_count / max(1, lifetime_tx), 4)

        # Payment details
        payment_method = rng.choice(PAYMENT_METHODS_LIST)
        failure_code = rng.choice(FAILURE_CODES_LIST)
        variance = rng.uniform(0.4, 2.5)
        amount = Decimal(str(round(avg_val * variance, 2)))
        hours_since_failure = round(rng.uniform(0.5, 12.0), 1)

        # Distribute failure dates across the 180-day timeline matching synthetic dataset without consuming PRNG draws
        day_offset = (idx * 17) % 180
        hour_offset = int(hours_since_failure)
        minute_offset = (idx * 7) % 60
        tx_created_at = datetime(2026, 1, 1) + timedelta(days=day_offset, hours=hour_offset, minutes=minute_offset)

        batch.append({
            "index": idx,
            "transaction_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
            "amount": amount,
            "payment_method": payment_method,
            "failure_code": failure_code,
            "hours_since_failure": hours_since_failure,
            "created_at": tx_created_at,
            # Observable customer features
            "account_age_days": account_age,
            "lifetime_tx_count": lifetime_tx,
            "failed_count": failed_count,
            "failure_rate": failure_rate,
            "avg_transaction_value": round(avg_val, 2),
            "upi_usage_pct": 0.60 if payment_method == "UPI" else 0.20,
            "card_usage_pct": 0.50 if payment_method == "CARD" else 0.15,
            # Latent parameter (used ONLY by hidden simulator)
            "_hidden_reliability": hidden_reliability,
        })

    return batch


def ensure_batch_in_db(batch: List[Dict[str, Any]], session: Session):
    """
    Ensures all transactions and supporting customer records exist in PostgreSQL
    so that decisions, policy_evaluations, and audit_events have valid foreign keys.
    """
    merchant = session.query(Merchant).first()
    if not merchant:
        merchant = Merchant(
            id=uuid.uuid4(),
            name="Default Merchant",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(merchant)
        session.flush()

    customer = session.query(Customer).first()
    if not customer:
        customer = Customer(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            account_age_days=365,
            lifetime_tx_count=25,
            successful_count=22,
            failed_count=3,
            avg_transaction_value=Decimal("4500.00"),
            upi_usage_pct=0.6,
            card_usage_pct=0.3,
            preferred_language="en",
            preferred_channel="UPI",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        session.add(customer)
        session.flush()

    tx_uuids = [UUID(it["transaction_id"]) for it in batch]
    existing_txs = set(
        r[0] for r in session.query(Transaction.id).filter(Transaction.id.in_(tx_uuids)).all()
    )

    # If re-running an experiment on the same batch, clean up prior decision & audit records
    # for these specific transactions so idempotency checks evaluate the batch fresh
    if existing_txs:
        session.query(VerificationResult).filter(VerificationResult.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(Action).filter(Action.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(PolicyEvaluation).filter(PolicyEvaluation.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(Decision).filter(Decision.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(Prediction).filter(Prediction.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(Diagnosis).filter(Diagnosis.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.query(AuditEvent).filter(AuditEvent.transaction_id.in_(existing_txs)).delete(synchronize_session=False)
        session.commit()

    new_tx_records = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for it in batch:
        u = UUID(it["transaction_id"])
        if u not in existing_txs:
            new_tx_records.append(
                Transaction(
                    id=u,
                    customer_id=customer.id,
                    merchant_id=merchant.id,
                    amount=it["amount"],
                    currency="INR",
                    payment_method=it["payment_method"],
                    status="failed",
                    failure_code=it["failure_code"],
                    source_event_id=f"evt_{u}",
                    created_at=it.get("created_at", now),
                )
            )

    if new_tx_records:
        session.bulk_save_objects(new_tx_records)
        session.commit()


def evaluate_baseline_policy(
    batch: List[Dict[str, Any]],
    seed: int,
) -> Dict[str, Any]:
    """
    Evaluates the dumb fixed-rule baseline policy against the batch.
    Baseline rule: IF payment_failed: retry_after_24h.
    ZERO access to customer history, ML probability, EV, or policy checks.
    """
    total_recovered = Decimal("0.00")
    total_cost = Decimal("0.00")
    recovered_count = 0
    unnecessary_count = 0
    action_counts = {"RETRY": 0}
    per_item_results: Dict[int, Dict[str, Any]] = {}

    for item in batch:
        # 1. Baseline decides action with zero external context
        contract = get_baseline_action(
            transaction_id=item["transaction_id"],
            amount=item["amount"],
            channel=item["payment_method"],
        )
        action_counts[contract.action_type.value] += 1
        operational_cost = Decimal("1.00")  # Constant RETRY cost
        total_cost += operational_cost

        # Track unnecessary interventions (blind retries on dead/expired failures)
        if item["failure_code"] in HARD_DECLINE_CODES:
            unnecessary_count += 1

        # 2. Simulator resolves outcome (blind to which policy chose the action)
        sample_rng = random.Random(seed * 10000 + item["index"])
        true_prob = hidden_outcome_function(
            customer_reliability=item["_hidden_reliability"],
            failure_code=item["failure_code"],
            payment_method=item["payment_method"],
            hours_since_failure=24.0,  # Fixed 24h delay
            action_type="RETRY",
        )
        is_recovered = sample_rng.random() < true_prob

        item_rec = Decimal("0.00")
        if is_recovered:
            recovered_count += 1
            item_rec = item["amount"]
            total_recovered += item_rec

        per_item_results[item["index"]] = {
            "recovered": is_recovered,
            "amount_recovered": item_rec,
            "cost": operational_cost,
        }

    batch_size = len(batch)
    recovery_rate = round(recovered_count / batch_size, 4) if batch_size > 0 else 0.0

    return {
        "policy": "BASELINE",
        "batch_size": batch_size,
        "recovered_count": recovered_count,
        "recovery_rate": recovery_rate,
        "total_recovered": total_recovered,
        "total_cost": total_cost,
        "net_recovered": total_recovered - total_cost,
        "action_counts": action_counts,
        "unnecessary_interventions": unnecessary_count,
        "escalations_count": 0,
        "per_item_results": per_item_results,
    }


def evaluate_recoverai_policy(
    batch: List[Dict[str, Any]],
    seed: int,
    session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Evaluates RecoverAI policy against the batch.
    Uses ML probability prediction + deterministic EV ranking + Policy Engine.
    When session is provided, persists decisions, policy_evaluations, and audit_events
    for every transaction in the batch (reusing Phase 8's log_audit_event).
    """
    total_recovered = Decimal("0.00")
    total_cost = Decimal("0.00")
    recovered_count = 0
    unnecessary_count = 0
    escalations_count = 0
    high_tier_escalations_count = 0
    high_tier_escalations_val = Decimal("0.00")
    mid_tier_escalations_count = 0
    mid_tier_escalations_val = Decimal("0.00")

    action_counts = {
        "RETRY": 0,
        "WHATSAPP": 0,
        "EMAIL": 0,
        "DISCOUNT": 0,
        "ESCALATE": 0,
        "BLOCKED": 0,
    }
    per_item_results: Dict[int, Dict[str, Any]] = {}

    candidate_actions = ["RETRY", "WHATSAPP", "EMAIL", "DISCOUNT"]

    for item in batch:
        diagnosis = diagnose_failure(item["failure_code"])
        tx_uuid = UUID(item["transaction_id"])

        # Score all candidate actions using ML model + EV engine
        ranked_proposals = []
        for act in candidate_actions:
            features = {
                "amount": float(item["amount"]),
                "account_age_days": item["account_age_days"],
                "lifetime_tx_count": item["lifetime_tx_count"],
                "failed_count": item["failed_count"],
                "failure_rate": item["failure_rate"],
                "avg_transaction_value": item["avg_transaction_value"],
                "upi_usage_pct": item["upi_usage_pct"],
                "card_usage_pct": item["card_usage_pct"],
                "hours_since_failure": item["hours_since_failure"],
                "payment_method": item["payment_method"],
                "failure_code": item["failure_code"],
                "action_type": act,
            }
            pred = predict_recovery_probability(features)
            ev_res = calculate_expected_value(
                amount=item["amount"],
                recovery_probability=pred.recovery_probability,
                action_type=act,
            )
            ranked_proposals.append({
                "action_type": act,
                "confidence": pred.recovery_probability,
                "expected_value": ev_res.expected_value,
                "cost": ev_res.action_cost,
            })

        # Sort by expected value descending
        ranked_proposals.sort(key=lambda x: x["expected_value"], reverse=True)
        best_candidate = ranked_proposals[0]

        # Determine proposed action type
        if best_candidate["expected_value"] <= Decimal("0.00"):
            # If all automated actions produce negative EV:
            if item["amount"] >= Decimal("10000.00"):
                chosen_action_type = ActionType.ESCALATE
                delay_hours = 0
                confidence = 0.50
                ev_val = Decimal("0.00")
            else:
                chosen_action_type = ActionType.EMAIL  # Lowest cost notification
                delay_hours = 2
                confidence = best_candidate["confidence"]
                ev_val = best_candidate["expected_value"]
        else:
            chosen_action_type = ActionType(best_candidate["action_type"])
            delay_hours = 1 if chosen_action_type == ActionType.RETRY else 0
            confidence = best_candidate["confidence"]
            ev_val = best_candidate["expected_value"]

        # Determine channel
        if chosen_action_type == ActionType.RETRY:
            channel = Channel(item["payment_method"]) if item["payment_method"] in Channel.__members__ else Channel.UPI
        elif chosen_action_type == ActionType.WHATSAPP:
            channel = Channel.WHATSAPP
        elif chosen_action_type == ActionType.EMAIL:
            channel = Channel.EMAIL
        elif chosen_action_type == ActionType.DISCOUNT:
            channel = Channel.WHATSAPP
        else:
            channel = Channel.EMAIL

        policy_ctx = {}
        if chosen_action_type == ActionType.DISCOUNT:
            policy_ctx["discount_pct"] = 0.10

        contract = RecoveryAction(
            action_type=chosen_action_type,
            transaction_id=item["transaction_id"],
            amount=item["amount"],
            channel=channel,
            delay_hours=delay_hours,
            reason_codes=diagnosis.reason_codes,
            confidence=confidence,
            expected_value=ev_val,
            policy_context=policy_ctx,
        )

        decision_id = uuid.uuid4()
        eval_now = item.get("created_at", datetime.now(timezone.utc).replace(tzinfo=None))

        # Persist full pipeline state & audit events if session provided
        if session is not None:
            # Stage 1: EVENT_RECEIVED
            log_audit_event(
                transaction_id=tx_uuid,
                event_type="EVENT_RECEIVED",
                actor="event_normalizer",
                input_snapshot={"event_id": f"evt_{tx_uuid}", "amount": float(item["amount"])},
                output_snapshot={"failure_code": item["failure_code"], "payment_method": item["payment_method"]},
                reason_codes=["EVENT_NORMALIZED"],
                db=session,
            )

            # Stage 2: RISK_SCORED
            severity = 0.85 if item["failure_code"] in HARD_DECLINE_CODES else 0.15
            risk_lvl = "HIGH" if severity > 0.5 else "LOW"
            log_audit_event(
                transaction_id=tx_uuid,
                event_type="RISK_SCORED",
                actor="risk_engine",
                input_snapshot={"amount": float(item["amount"]), "lifetime_tx": item["lifetime_tx_count"]},
                output_snapshot={"severity_score": severity, "risk_level": risk_lvl},
                reason_codes=["DETERMINISTIC_RISK_HIGH" if severity > 0.5 else "DETERMINISTIC_RISK_NORMAL"],
                db=session,
            )

            # Stage 3: DIAGNOSIS_COMPLETED & persist Diagnosis row
            diag_row = Diagnosis(
                id=uuid.uuid4(),
                transaction_id=tx_uuid,
                failure_code=item["failure_code"],
                source=DiagnosisSource(diagnosis.source.value),
                confidence=diagnosis.confidence,
                reason_codes=diagnosis.reason_codes,
                created_at=eval_now,
            )
            session.add(diag_row)

            log_audit_event(
                transaction_id=tx_uuid,
                event_type="DIAGNOSIS_COMPLETED",
                actor="diagnosis_engine",
                input_snapshot={"failure_code": item["failure_code"]},
                output_snapshot={
                    "failure_code": diagnosis.failure_code,
                    "confidence": diagnosis.confidence,
                    "source": diagnosis.source.value,
                },
                reason_codes=diagnosis.reason_codes,
                db=session,
            )

            # Stage 4: PROBABILITY_PREDICTED & persist Prediction row
            pred_row = Prediction(
                id=uuid.uuid4(),
                transaction_id=tx_uuid,
                recovery_probability=float(best_candidate["confidence"]),
                model_version="gradient_boosting_v1",
                created_at=eval_now,
            )
            session.add(pred_row)

            log_audit_event(
                transaction_id=tx_uuid,
                event_type="PROBABILITY_PREDICTED",
                actor="ml_prediction_engine",
                input_snapshot={"features": {"amount": float(item["amount"]), "failure_code": item["failure_code"], "payment_method": item["payment_method"]}},
                output_snapshot={"recovery_probability": float(best_candidate["confidence"]), "model_version": "gradient_boosting_v1"},
                reason_codes=["CALIBRATED_ML_ESTIMATION"],
                db=session,
            )

            # Stage 5: DECISION_RECOMMENDED & persist Decision row
            d_row = Decision(
                id=decision_id,
                transaction_id=tx_uuid,
                action_type=contract.action_type.value,
                channel=contract.channel.value,
                delay_hours=contract.delay_hours,
                amount=contract.amount,
                confidence_llm=contract.confidence,
                expected_value_llm=contract.expected_value,
                expected_value_verified=contract.expected_value,
                reason_codes=contract.reason_codes,
                policy_context=contract.policy_context,
                created_at=eval_now,
            )
            session.add(d_row)
            session.flush()

            log_audit_event(
                transaction_id=tx_uuid,
                event_type="DECISION_RECOMMENDED",
                actor="decision_engine",
                input_snapshot={"action_type": contract.action_type.value, "channel": contract.channel.value},
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

        # Policy Engine Guardrail Check (Phase 7)
        pol_trace = evaluate_policy(contract, decision_id=decision_id, db=session)

        # Stage 6: POLICY_EVALUATED
        if session is not None:
            log_audit_event(
                transaction_id=tx_uuid,
                event_type="POLICY_EVALUATED",
                actor="policy_engine",
                input_snapshot={
                    "action": contract.action_type.value,
                    "amount": float(contract.amount),
                    "channel": contract.channel.value,
                },
                output_snapshot={
                    "verdict": pol_trace.verdict.value,
                    "checks_evaluated": len(pol_trace.check_results),
                },
                reason_codes=pol_trace.reasons,
                policy_result=pol_trace.verdict.value,
                db=session,
            )

        # Track unnecessary interventions
        if item["failure_code"] in HARD_DECLINE_CODES and pol_trace.verdict == PolicyVerdict.APPROVED:
            unnecessary_count += 1

        # Resolve outcome via hidden simulator using the EXACT same random seed
        sample_rng = random.Random(seed * 10000 + item["index"])

        item_rec = Decimal("0.00")
        item_cost = Decimal("0.00")
        is_escalated = False

        if pol_trace.verdict == PolicyVerdict.BLOCKED:
            action_counts["BLOCKED"] += 1
            # Action was blocked by policy: 0 cost, 0 recovery
            per_item_results[item["index"]] = {
                "verdict": "BLOCKED",
                "action": "BLOCKED",
                "is_escalated": False,
                "recovered": False,
                "amount_recovered": Decimal("0.00"),
                "cost": Decimal("0.00"),
            }
            if session is not None and item["index"] % 100 == 0:
                session.commit()
            continue

        elif pol_trace.verdict == PolicyVerdict.ESCALATED:
            action_counts["ESCALATE"] += 1
            escalations_count += 1
            is_escalated = True
            item_cost = Decimal("25.00")
            total_cost += item_cost

            # Track reason for escalation
            if item["amount"] > Decimal("25000.00"):
                high_tier_escalations_count += 1
                high_tier_escalations_val += item["amount"]
            else:
                mid_tier_escalations_count += 1
                mid_tier_escalations_val += item["amount"]

            true_prob = hidden_outcome_function(
                customer_reliability=item["_hidden_reliability"],
                failure_code=item["failure_code"],
                payment_method=item["payment_method"],
                hours_since_failure=item["hours_since_failure"],
                action_type="ESCALATE",
            )
            is_recovered = sample_rng.random() < true_prob
            if is_recovered:
                recovered_count += 1
                item_rec = item["amount"]
                total_recovered += item_rec

            per_item_results[item["index"]] = {
                "verdict": "ESCALATED",
                "action": "ESCALATE",
                "is_escalated": True,
                "recovered": is_recovered,
                "amount_recovered": item_rec,
                "cost": item_cost,
            }

        else:  # APPROVED
            action_counts[contract.action_type.value] += 1
            # Calculate operational cost
            if contract.action_type == ActionType.RETRY:
                item_cost = Decimal("1.00")
            elif contract.action_type == ActionType.WHATSAPP:
                item_cost = Decimal("1.50")
            elif contract.action_type == ActionType.EMAIL:
                item_cost = Decimal("0.20")
            elif contract.action_type == ActionType.DISCOUNT:
                item_cost = round(item["amount"] * Decimal("0.10"), 2)
            else:
                item_cost = Decimal("25.00")

            total_cost += item_cost

            # Simulator resolution
            true_prob = hidden_outcome_function(
                customer_reliability=item["_hidden_reliability"],
                failure_code=item["failure_code"],
                payment_method=item["payment_method"],
                hours_since_failure=item["hours_since_failure"] + delay_hours,
                action_type=contract.action_type.value,
            )
            is_recovered = sample_rng.random() < true_prob

            if is_recovered:
                recovered_count += 1
                if contract.action_type == ActionType.DISCOUNT:
                    item_rec = round(item["amount"] * Decimal("0.90"), 2)
                else:
                    item_rec = item["amount"]
                total_recovered += item_rec

            # Persist action and outcome if session provided
            if session is not None:
                act_row = Action(
                    id=uuid.uuid4(),
                    transaction_id=tx_uuid,
                    decision_id=decision_id,
                    action_type=contract.action_type.value,
                    status=ActionStatus.EXECUTED,
                    executed_at=eval_now + timedelta(hours=int(contract.delay_hours or 0)),
                )
                session.add(act_row)
                session.flush()

                log_audit_event(
                    transaction_id=tx_uuid,
                    event_type="ACTION_EXECUTED",
                    actor="action_executor",
                    input_snapshot={"channel": contract.channel.value, "action_type": contract.action_type.value},
                    output_snapshot={"amount": float(contract.amount), "status": "executed", "cost": float(item_cost)},
                    reason_codes=["ACTION_DISPATCHED_TO_MOCK"],
                    db=session,
                )

                verif_row = VerificationResult(
                    id=uuid.uuid4(),
                    transaction_id=tx_uuid,
                    action_id=act_row.id,
                    outcome=VerificationOutcome.SUCCESS if is_recovered else VerificationOutcome.FAILURE,
                    simulated_amount_recovered=item_rec,
                    verified_at=eval_now + timedelta(hours=int(contract.delay_hours or 0) + 1),
                )
                session.add(verif_row)

                log_audit_event(
                    transaction_id=tx_uuid,
                    event_type="OUTCOME_VERIFIED",
                    actor="verification_engine",
                    input_snapshot={"action_id": str(act_row.id)},
                    output_snapshot={"outcome": verif_row.outcome.value, "simulated_amount_recovered": float(item_rec)},
                    reason_codes=["SIMULATOR_OUTCOME_SUCCESS" if is_recovered else "SIMULATOR_OUTCOME_FAILURE"],
                    db=session,
                )

            per_item_results[item["index"]] = {
                "verdict": "APPROVED",
                "action": contract.action_type.value,
                "is_escalated": False,
                "recovered": is_recovered,
                "amount_recovered": item_rec,
                "cost": item_cost,
            }

        if session is not None and item["index"] % 100 == 0:
            session.commit()

    if session is not None:
        session.commit()

    batch_size = len(batch)
    recovery_rate = round(recovered_count / batch_size, 4) if batch_size > 0 else 0.0

    return {
        "policy": "RECOVERAI",
        "batch_size": batch_size,
        "recovered_count": recovered_count,
        "recovery_rate": recovery_rate,
        "total_recovered": total_recovered,
        "total_cost": total_cost,
        "net_recovered": total_recovered - total_cost,
        "action_counts": action_counts,
        "unnecessary_interventions": unnecessary_count,
        "escalations_count": escalations_count,
        "high_tier_escalations_count": high_tier_escalations_count,
        "high_tier_escalations_val": high_tier_escalations_val,
        "mid_tier_escalations_count": mid_tier_escalations_count,
        "mid_tier_escalations_val": mid_tier_escalations_val,
        "per_item_results": per_item_results,
    }


def save_experiment_results_to_db(
    seed: int,
    batch_size: int,
    baseline_res: Dict[str, Any],
    recoverai_res: Dict[str, Any],
    incremental_net: Decimal,
    session: Optional[Session] = None,
) -> Tuple[UUID, UUID]:
    """Persists two rows to experiments table: one for BASELINE, one for RECOVERAI."""
    close_session = False
    if session is None:
        engine = create_engine(settings.database_url)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        close_session = True

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        # Row 1: BASELINE
        row_base = Experiment(
            id=uuid.uuid4(),
            seed=seed,
            batch_size=batch_size,
            policy_type=PolicyType.BASELINE,
            total_recovered=baseline_res["net_recovered"],
            recovery_rate=baseline_res["recovery_rate"],
            incremental_recovered=Decimal("0.00"),
            run_at=now_utc,
        )
        session.add(row_base)

        # Row 2: RECOVERAI
        row_rec = Experiment(
            id=uuid.uuid4(),
            seed=seed,
            batch_size=batch_size,
            policy_type=PolicyType.RECOVERAI,
            total_recovered=recoverai_res["net_recovered"],
            recovery_rate=recoverai_res["recovery_rate"],
            incremental_recovered=incremental_net,
            run_at=now_utc,
        )
        session.add(row_rec)
        session.commit()

        return row_base.id, row_rec.id
    finally:
        if close_session:
            session.close()


def run_experiment(seed: int = 42, count: int = 1000, save_db: bool = True):
    print("\n" + "=" * 75, flush=True)
    print(f"PHASE 9/10: A/B EVALUATION EXPERIMENT (Seed: {seed}, Batch Count: {count})", flush=True)
    print("=" * 75, flush=True)

    # Ensure model artifacts exist
    if not os.path.exists(MODEL_PATH) or not os.path.exists(METRICS_PATH):
        print("Model artifacts not found. Initiating model training pipeline...", flush=True)
        train_and_evaluate(n_samples=12000, seed=42)

    print("\nGenerating simulated failed transactions batch...", flush=True)
    batch = generate_experiment_batch(count=count, seed=seed)
    total_pipeline_val = sum(item["amount"] for item in batch)
    print(f"Batch generated: {len(batch)} failed transactions | Total Failed Value: ₹{total_pipeline_val:,.2f}", flush=True)

    session = None
    if save_db:
        engine = create_engine(settings.database_url)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        print("\nEnsuring all batch transactions exist in PostgreSQL database...", flush=True)
        ensure_batch_in_db(batch, session)

    # 1. Evaluate Baseline
    print("\nRunning Baseline Policy (Rule: IF payment_failed: retry_after_24h)...", flush=True)
    base_res = evaluate_baseline_policy(batch, seed=seed)

    # 2. Evaluate RecoverAI (with real DB persistence if save_db)
    print("\nRunning RecoverAI Policy (EV Engine + Policy Engine direct batch mode)...", flush=True)
    rec_res = evaluate_recoverai_policy(batch, seed=seed, session=session)

    # Calculate Deltas
    inc_gross = rec_res["total_recovered"] - base_res["total_recovered"]
    inc_net = rec_res["net_recovered"] - base_res["net_recovered"]
    rate_diff = (rec_res["recovery_rate"] - base_res["recovery_rate"]) * 100

    # Persist to DB (PRIMARY METRIC is NET incremental recovered)
    exp_base_id, exp_rec_id = None, None
    if save_db and session is not None:
        exp_base_id, exp_rec_id = save_experiment_results_to_db(
            seed=seed,
            batch_size=count,
            baseline_res=base_res,
            recoverai_res=rec_res,
            incremental_net=inc_net,
            session=session,
        )
        session.close()

    # -----------------------------------------------------------------
    # Print Comprehensive Side-by-Side Results
    # -----------------------------------------------------------------
    print("\n" + "=" * 75, flush=True)
    print("EXPERIMENT COMPARISON RESULTS (A/B EVALUATION)", flush=True)
    print("=" * 75, flush=True)
    print(f"Note: RecoverAI batch decisioning uses EV-Engine (Phase 5) + Policy Engine (Phase 7).", flush=True)
    print(f"Both policies were evaluated on the identical synthetic batch against the same hidden simulator.\n", flush=True)

    col_w = 26
    print(f"{'Metric':<32} | {'Baseline':>{col_w}} | {'RecoverAI':>{col_w}}", flush=True)
    print("-" * 75, flush=True)
    print(f"{'Total Failed Transactions':<32} | {base_res['batch_size']:>{col_w},d} | {rec_res['batch_size']:>{col_w},d}", flush=True)
    print(f"{'Transactions Recovered':<32} | {base_res['recovered_count']:>{col_w},d} | {rec_res['recovered_count']:>{col_w},d}", flush=True)
    print(f"{'Recovery Rate (%)':<32} | {base_res['recovery_rate'] * 100:>{col_w - 1}.2f}% | {rec_res['recovery_rate'] * 100:>{col_w - 1}.2f}%", flush=True)
    print(f"{'Gross Value Recovered (₹)':<32} | ₹{base_res['total_recovered']:>{col_w - 1},.2f} | ₹{rec_res['total_recovered']:>{col_w - 1},.2f}", flush=True)
    print(f"{'Total Operational Cost (₹)':<32} | ₹{base_res['total_cost']:>{col_w - 1},.2f} | ₹{rec_res['total_cost']:>{col_w - 1},.2f}", flush=True)
    print(f"{'Net Value Recovered (₹)':<32} | ₹{base_res['net_recovered']:>{col_w - 1},.2f} | ₹{rec_res['net_recovered']:>{col_w - 1},.2f}", flush=True)
    print(f"{'Unnecessary Interventions':<32} | {base_res['unnecessary_interventions']:>{col_w},d} | {rec_res['unnecessary_interventions']:>{col_w},d}", flush=True)
    print(f"{'Escalated to Human Review':<32} | {base_res['escalations_count']:>{col_w},d} | {rec_res['escalations_count']:>{col_w},d}", flush=True)
    print("-" * 75, flush=True)
    print(f"{'PRIMARY METRIC (Net Incremental ₹)':<32} | {'Reference (₹0.00)':>{col_w}} | ₹{inc_net:>{col_w - 1},.2f}", flush=True)
    print(f"{'Gross Incremental Lift (₹)':<32} | {'-':>{col_w}} | ₹{inc_gross:>{col_w - 1},.2f}", flush=True)
    print(f"{'Recovery Rate Delta (% pts)':<32} | {'-':>{col_w}} | {rate_diff:>+{col_w - 1}.2f}%", flush=True)
    print("-" * 75, flush=True)

    print("\nAction Breakdown:", flush=True)
    print(f"  Baseline Actions:  {base_res['action_counts']}", flush=True)
    print(f"  RecoverAI Actions: {rec_res['action_counts']}", flush=True)

    # -----------------------------------------------------------------
    # Forensic Slice Analysis: Escalated vs Autonomous Segments
    # -----------------------------------------------------------------
    base_items = base_res["per_item_results"]
    rec_items = rec_res["per_item_results"]

    escalated_indices = [idx for idx, r in rec_items.items() if r["is_escalated"]]
    autonomous_indices = [idx for idx, r in rec_items.items() if not r["is_escalated"]]

    base_rec_on_esc = sum(base_items[idx]["amount_recovered"] for idx in escalated_indices)
    rec_rec_on_esc = sum(rec_items[idx]["amount_recovered"] for idx in escalated_indices)
    rec_cost_on_esc = sum(rec_items[idx]["cost"] for idx in escalated_indices)

    base_rec_on_auto = sum(base_items[idx]["amount_recovered"] for idx in autonomous_indices)
    rec_rec_on_auto = sum(rec_items[idx]["amount_recovered"] for idx in autonomous_indices)
    base_cost_on_auto = sum(base_items[idx]["cost"] for idx in autonomous_indices)
    rec_cost_on_auto = sum(rec_items[idx]["cost"] for idx in autonomous_indices)

    print("\n" + "-" * 75, flush=True)
    print("FORENSIC SLICE ANALYSIS (Escalated vs Autonomous Cohorts):", flush=True)
    print("-" * 75, flush=True)
    print(f"1. Human Escalation Cohort ({len(escalated_indices)} transactions):", flush=True)
    print(f"   - Ceiling Violations (>₹25k): {rec_res['high_tier_escalations_count']} txs (₹{rec_res['high_tier_escalations_val']:,.2f})", flush=True)
    print(f"   - Confidence Gate (<0.40):   {rec_res['mid_tier_escalations_count']} txs (₹{rec_res['mid_tier_escalations_val']:,.2f})", flush=True)
    print(f"   - RecoverAI Gross Recovered:  ₹{rec_rec_on_esc:,.2f} (Charged ₹{rec_cost_on_esc:,.2f} ticket costs)", flush=True)
    print(f"   - Baseline Blind Retries:     ₹{base_rec_on_esc:,.2f} (Recovered on high-risk cases that policy gated)", flush=True)
    print(f"   - Cohort Delta (RecoverAI - Baseline): ₹{(rec_rec_on_esc - rec_cost_on_esc) - (base_rec_on_esc - Decimal(str(len(escalated_indices)))):,.2f}", flush=True)

    print(f"\n2. Autonomous Action Cohort ({len(autonomous_indices)} transactions):", flush=True)
    print(f"   - Baseline Net Recovered:    ₹{base_rec_on_auto - base_cost_on_auto:,.2f}", flush=True)
    print(f"   - RecoverAI Net Recovered:   ₹{rec_rec_on_auto - rec_cost_on_auto:,.2f}", flush=True)
    auto_net_lift = (rec_rec_on_auto - rec_cost_on_auto) - (base_rec_on_auto - base_cost_on_auto)
    print(f"   - Autonomous Net Lift:       ₹{auto_net_lift:+,.2f}", flush=True)

    if save_db:
        print(f"\nPersisted Experiment Rows to `experiments` Table in PostgreSQL:", flush=True)
        print(f"  Baseline Row ID:  {exp_base_id}", flush=True)
        print(f"  RecoverAI Row ID: {exp_rec_id} (Stored NET incremental: ₹{inc_net:,.2f})", flush=True)
        print(f"  Uniform DB Persistence: All batch decisions, policy evaluations, and audit events saved to DB.", flush=True)

    print("=" * 75 + "\n", flush=True)
    return base_res, rec_res, inc_net


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RecoverAI Phase 9/10 A/B Experiment Engine")
    parser.add_argument("--seed", type=int, default=42, help="Seed for random number generator")
    parser.add_argument("--count", type=int, default=1000, help="Number of failed transactions to evaluate")
    parser.add_argument("--no-db", action="store_true", help="Do not persist results to experiments table")

    args = parser.parse_args()
    run_experiment(seed=args.seed, count=args.count, save_db=not args.no_db)
