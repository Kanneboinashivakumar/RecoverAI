#!/usr/bin/env python3
"""Phase 3 idempotency verification."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.domain.events.processor import process_revenue_event
from sqlalchemy import text

db = SessionLocal()

# Get a real transaction to build a valid event
row = db.execute(text("SELECT t.id, t.customer_id, t.merchant_id, t.amount, t.currency FROM transactions t LIMIT 1")).fetchone()
tx_id, cust_id, merch_id, amount, currency = row

# Create a raw event with a fixed external_event_id
raw = {
    "external_event_id": "IDEMPOTENCY_TEST_001",
    "event_type": "payment_failed",
    "customer_id": str(cust_id),
    "merchant_id": str(merch_id),
    "transaction_id": str(tx_id),
    "amount": float(amount),
    "currency": currency,
    "timestamp": "2025-01-15T12:00:00Z",
    "source": "test_gateway",
    "metadata": {}
}

# First ingestion
r1 = process_revenue_event(raw, db)
print(f"Run 1: status={r1.status}, is_duplicate={r1.is_duplicate}, processed={r1.processed}")

# Second ingestion (same event)
r2 = process_revenue_event(raw, db)
print(f"Run 2: status={r2.status}, is_duplicate={r2.is_duplicate}, processed={r2.processed}")

# Count records
count = db.execute(text("SELECT COUNT(*) FROM revenue_events WHERE external_event_id='IDEMPOTENCY_TEST_001'")).scalar()
print(f"Records in DB with this ID: {count}")
print(f"Idempotency holds: {count == 1}")

db.close()
