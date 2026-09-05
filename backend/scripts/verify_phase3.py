#!/usr/bin/env python3
"""
Phase 3 Verification Script — Event Normalizer, Deterministic Risk Engine & Idempotency

Usage:
    docker compose exec backend python scripts/verify_phase3.py
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.domain.events.normalizer import ALL_TAXONOMY_FAILURE_CODES, normalize_event
from app.domain.events.processor import process_revenue_event
from app.domain.events.schema import NormalizedRevenueEvent
from app.engines.risk import score_risk
from app.models.tables import Customer, Merchant, RevenueEvent


def verify_taxonomy_normalization():
    print("\n" + "=" * 65)
    print("STEP 1: TAXONOMY NORMALIZATION VERIFICATION")
    print("=" * 65)
    print(f"Total taxonomy failure codes in Ground Truth: {len(ALL_TAXONOMY_FAILURE_CODES)}")

    dummy_cust_id = uuid.uuid4()
    dummy_merch_id = uuid.uuid4()
    success_count = 0

    for code in sorted(ALL_TAXONOMY_FAILURE_CODES):
        raw_payload = {
            "external_event_id": f"test_norm_{code}",
            "event_type": code,
            "customer_id": str(dummy_cust_id),
            "merchant_id": str(dummy_merch_id),
            "amount": "1500.00",
            "currency": "INR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "gateway_webhook",
        }
        normalized = normalize_event(raw_payload)
        assert isinstance(normalized, NormalizedRevenueEvent), f"Failed to normalize {code}"
        assert normalized.event_type == "payment_failed", f"Expected payment_failed for {code}"
        assert normalized.metadata.get("failure_code") == code, f"Missing failure_code for {code}"
        success_count += 1

    print(f"All {success_count} taxonomy failure codes normalized successfully!")
    return True


def verify_idempotency(session):
    print("\n" + "=" * 65)
    print("STEP 2: IDEMPOTENCY HANDLING (DUPLICATE WEBHOOK DELIVERY)")
    print("=" * 65)

    # Ensure a merchant and customer exist for testing
    merchant = session.query(Merchant).first()
    if not merchant:
        merchant = Merchant(id=uuid.uuid4(), name="Test Merchant", created_at=datetime.now(timezone.utc))
        session.add(merchant)
        session.commit()

    customer = session.query(Customer).first()
    if not customer:
        customer = Customer(
            id=uuid.uuid4(),
            merchant_id=merchant.id,
            account_age_days=100,
            lifetime_tx_count=10,
            successful_count=8,
            failed_count=2,
            avg_transaction_value=Decimal("1500.00"),
            upi_usage_pct=0.7,
            card_usage_pct=0.3,
            preferred_language="en",
            preferred_channel="UPI",
            created_at=datetime.now(timezone.utc),
        )
        session.add(customer)
        session.commit()

    # Create a test batch of 5 events with fixed unique IDs
    run_id = uuid.uuid4().hex[:6]
    test_batch = [
        {
            "external_event_id": f"evt_webhook_{run_id}_{i:03d}",
            "event_type": "payment_failed",
            "failure_code": "UPI_BANK_TIMEOUT",
            "customer_id": str(customer.id),
            "merchant_id": str(merchant.id),
            "amount": f"{200 + i * 100}.00",
            "currency": "INR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "razorpay_webhook",
        }
        for i in range(1, 6)
    ]

    event_ids = [e["external_event_id"] for e in test_batch]
    print(f"Feeding test batch of {len(test_batch)} events:")
    for eid in event_ids:
        print(f"  - {eid}")

    # Pass 1: First delivery
    print("\n--- Pass 1 (First Delivery) ---")
    pass1_processed = 0
    pass1_duplicates = 0
    for raw in test_batch:
        res = process_revenue_event(raw, session)
        if res.processed and not res.is_duplicate:
            pass1_processed += 1
        elif res.is_duplicate:
            pass1_duplicates += 1
        print(f"  [{res.status:18s}] ID: {res.external_event_id} | Risk: {res.risk_score.risk_level if res.risk_score else 'N/A'}")

    print(f"Pass 1 Summary: {pass1_processed} processed, {pass1_duplicates} duplicates")

    # Pass 2: Duplicate delivery (same events re-sent)
    print("\n--- Pass 2 (Simulated Duplicate Delivery) ---")
    pass2_processed = 0
    pass2_duplicates = 0
    for raw in test_batch:
        res = process_revenue_event(raw, session)
        if res.processed and not res.is_duplicate:
            pass2_processed += 1
        elif res.is_duplicate:
            pass2_duplicates += 1
        print(f"  [{res.status:18s}] ID: {res.external_event_id} | {res.message}")

    print(f"Pass 2 Summary: {pass2_processed} processed, {pass2_duplicates} duplicates ignored")

    # Verify DB state
    db_count = (
        session.query(RevenueEvent)
        .filter(RevenueEvent.external_event_id.in_(event_ids))
        .count()
    )
    print(f"\nDatabase verification: Records in DB with batch IDs = {db_count} (Expected: 5)")
    assert pass1_processed == 5, f"Expected 5 processed in pass 1, got {pass1_processed}"
    assert pass2_duplicates == 5, f"Expected 5 duplicates in pass 2, got {pass2_duplicates}"
    assert db_count == 5, f"Expected exactly 5 DB records, got {db_count}"
    print("Idempotency successfully verified!")
    return True


def verify_risk_scoring():
    print("\n" + "=" * 65)
    print("STEP 3: DETERMINISTIC RISK SCORING — 3 DISTINCT PROFILES")
    print("=" * 65)

    dummy_cust_id = uuid.uuid4()
    dummy_merch_id = uuid.uuid4()

    # Profile 1: High Risk
    # ₹50,000 card decline from a high-failure-history customer (8 fails / 10 total = 80% failure rate)
    customer_high_risk = {
        "lifetime_tx_count": 10,
        "failed_count": 8,
        "successful_count": 2,
    }
    event_high_risk = normalize_event({
        "external_event_id": "test_high_risk_001",
        "event_type": "payment_failed",
        "failure_code": "CARD_DECLINED",
        "customer_id": str(dummy_cust_id),
        "merchant_id": str(dummy_merch_id),
        "amount": "50000.00",
        "currency": "INR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "gateway",
    })

    # Profile 2: Medium Risk
    # ₹5,000 UPI insufficient funds from a moderate customer (2 fails / 10 total = 20% failure rate)
    customer_med_risk = {
        "lifetime_tx_count": 10,
        "failed_count": 2,
        "successful_count": 8,
    }
    event_med_risk = normalize_event({
        "external_event_id": "test_med_risk_002",
        "event_type": "payment_failed",
        "failure_code": "UPI_INSUFFICIENT_FUNDS",
        "customer_id": str(dummy_cust_id),
        "merchant_id": str(dummy_merch_id),
        "amount": "5000.00",
        "currency": "INR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "gateway",
    })

    # Profile 3: Low Risk
    # ₹200 UPI timeout from a reliable customer (1 fail / 50 total = 2% failure rate)
    customer_low_risk = {
        "lifetime_tx_count": 50,
        "failed_count": 1,
        "successful_count": 49,
    }
    event_low_risk = normalize_event({
        "external_event_id": "test_low_risk_003",
        "event_type": "payment_failed",
        "failure_code": "UPI_BANK_TIMEOUT",
        "customer_id": str(dummy_cust_id),
        "merchant_id": str(dummy_merch_id),
        "amount": "200.00",
        "currency": "INR",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "gateway",
    })

    score1 = score_risk(event_high_risk, customer_high_risk)
    score2 = score_risk(event_med_risk, customer_med_risk)
    score3 = score_risk(event_low_risk, customer_low_risk)

    profiles = [
        ("Profile 1: HIGH RISK (₹50,000 CARD_DECLINED, 80% failure history)", event_high_risk, score1),
        ("Profile 2: MEDIUM RISK (₹5,000 UPI_INSUFFICIENT_FUNDS, 20% failure history)", event_med_risk, score2),
        ("Profile 3: LOW RISK (₹200 UPI_BANK_TIMEOUT, 2% failure history)", event_low_risk, score3),
    ]

    for title, evt, sc in profiles:
        print(f"\n--- {title} ---")
        print(f"  Amount:          ₹{evt.amount}")
        print(f"  Failure Code:    {evt.metadata.get('failure_code')}")
        print(f"  Value Score:     {sc.value_score:.2f} / 100")
        print(f"  Customer Score:  {sc.customer_history_score:.2f} / 100")
        print(f"  Failure Score:   {sc.failure_type_score:.2f} / 100")
        print(f"  SEVERITY SCORE:  {sc.severity_score:.2f} / 100")
        print(f"  RISK LEVEL:      {sc.risk_level}")
        print(f"  IS AT RISK:      {sc.is_at_risk}")
        print(f"  Reasons:         {', '.join(sc.reasons)}")

    # Verification assertions
    assert score1.severity_score > score2.severity_score > score3.severity_score, (
        f"Score order violation: {score1.severity_score} > {score2.severity_score} > {score3.severity_score}"
    )
    assert score1.is_at_risk is True
    assert score3.is_at_risk is False

    # Confirm determinism across multiple runs
    for _ in range(5):
        assert score_risk(event_high_risk, customer_high_risk).severity_score == score1.severity_score
        assert score_risk(event_med_risk, customer_med_risk).severity_score == score2.severity_score
        assert score_risk(event_low_risk, customer_low_risk).severity_score == score3.severity_score
    print("\nDeterminism confirmed: Repeated runs yield identical scores byte-for-byte.")
    return True


def main():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        verify_taxonomy_normalization()
        verify_idempotency(session)
        verify_risk_scoring()

        print("\n" + "=" * 65)
        print("PHASE 3 VERIFICATION COMPLETE: ALL CHECKS PASSED!")
        print("=" * 65)
    finally:
        session.close()


if __name__ == "__main__":
    main()
