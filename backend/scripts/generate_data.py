#!/usr/bin/env python3
"""
RecoverAI Synthetic Data Generator.

Produces seeded, deterministic customer profiles and revenue events
using the exact failure taxonomy from Ground Truth.

Usage (inside Docker container):
    python scripts/generate_data.py --seed 42 --count 1000
"""

import argparse
import hashlib
import os
import random
import sys
import uuid
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.tables import Customer, Merchant, RevenueEvent, Transaction

# ---- Constants ----

BASE_TIME = datetime(2026, 1, 1)

LANGUAGES = ["en", "hi", "ta", "te", "bn", "mr", "gu", "kn", "ml"]
CHANNELS = ["UPI", "CARD", "NETBANKING"]

# Exact failure taxonomy from Ground Truth (01-GROUND-TRUTH.md)
FAILURE_CODES_BY_METHOD = {
    "UPI": [
        "UPI_COLLECT_EXPIRED",
        "UPI_BANK_TIMEOUT",
        "UPI_INSUFFICIENT_FUNDS",
        "UPI_PSP_ERROR",
        "UPI_CUSTOMER_DECLINED",
        "UPI_LIMIT_EXCEEDED",
        "UPI_MANDATE_FAILED",
        "UPI_MANDATE_EXPIRED",
    ],
    "CARD": [
        "CARD_EXPIRED",
        "CARD_DECLINED",
        "CARD_LIMIT_EXCEEDED",
        "ISSUER_TIMEOUT",
        "INSUFFICIENT_FUNDS",
    ],
    "NETBANKING": [
        "BANK_TIMEOUT",
        "BANK_DECLINED",
        "SESSION_EXPIRED",
    ],
    "MANDATE": [
        "MANDATE_REGISTRATION_FAILED",
        "MANDATE_EXECUTION_FAILED",
        "MANDATE_REVOKED",
        "MANDATE_EXPIRED",
    ],
}

CHECKOUT_FAILURES = [
    "CHECKOUT_ABANDONED",
    "PAYMENT_PAGE_EXIT",
    "OTP_TIMEOUT",
    "PAYMENT_METHOD_CHANGED",
]

B2B_FAILURES = [
    "INVOICE_OVERDUE",
    "PAYMENT_PROMISE_BROKEN",
    "PARTIAL_PAYMENT",
]


# ---- Helpers ----


def make_uuid(rng: random.Random) -> uuid.UUID:
    """Generate a deterministic UUID from the seeded RNG."""
    return uuid.UUID(int=rng.getrandbits(128), version=4)


def pick_payment_method(rng: random.Random, upi_pct: float, card_pct: float) -> str:
    """Pick a payment method based on customer's usage percentages."""
    roll = rng.random()
    if roll < upi_pct:
        return "UPI"
    if roll < upi_pct + card_pct:
        return "CARD"
    # Remaining split: 70% netbanking, 30% mandate
    remaining = 1.0 - upi_pct - card_pct
    netbanking_threshold = upi_pct + card_pct + remaining * 0.7
    if roll < netbanking_threshold:
        return "NETBANKING"
    return "MANDATE"


def pick_failure_code(rng: random.Random, payment_method: str) -> str:
    """Pick a failure code from the Ground Truth taxonomy."""
    roll = rng.random()
    if roll < 0.70:
        # Method-specific failure
        return rng.choice(FAILURE_CODES_BY_METHOD[payment_method])
    elif roll < 0.95:
        # Checkout failure (cross-method)
        return rng.choice(CHECKOUT_FAILURES)
    else:
        # B2B failure
        return rng.choice(B2B_FAILURES)


# ---- Generation ----


def generate(rng: random.Random, count: int, merchant_id: uuid.UUID):
    """
    Generate customers, transactions, and revenue events.

    Returns (customers, transactions, revenue_events) as lists of dicts.
    Customer dicts include internal fields prefixed with _ (not written to DB).
    """
    num_customers = min(max(10, count // 10), count)

    # Step 1: Customer skeletons (archetype + preferences, no tx counts yet)
    skeletons = []
    for _ in range(num_customers):
        roll = rng.random()
        if roll < 0.55:
            archetype = "reliable"
            reliability = rng.uniform(0.80, 0.95)
            age = rng.randint(180, 1800)
            avg_target = rng.uniform(500, 20000)
        elif roll < 0.85:
            archetype = "moderate"
            reliability = rng.uniform(0.60, 0.80)
            age = rng.randint(30, 365)
            avg_target = rng.uniform(200, 5000)
        else:
            archetype = "risky"
            reliability = rng.uniform(0.35, 0.60)
            age = rng.randint(1, 180)
            avg_target = rng.uniform(100, 3000)

        upi_pct = round(rng.uniform(0.10, 0.70), 2)
        card_pct = round(rng.uniform(0.05, max(0.06, 0.90 - upi_pct)), 2)

        skeletons.append(
            {
                "id": make_uuid(rng),
                "archetype": archetype,
                "reliability": reliability,
                "account_age_days": age,
                "avg_value_target": avg_target,
                "upi_usage_pct": upi_pct,
                "card_usage_pct": card_pct,
                "preferred_language": rng.choice(LANGUAGES),
                "preferred_channel": rng.choice(CHANNELS),
            }
        )

    # Step 2: Distribute transactions across customers (weighted by activity)
    activity_weights = [s["account_age_days"] for s in skeletons]
    tx_assignments = rng.choices(
        range(num_customers), weights=activity_weights, k=count
    )
    tx_per_customer = Counter(tx_assignments)

    # Step 3: Generate transactions and revenue events
    all_transactions = []
    all_events = []
    customer_txs: dict[int, list] = {i: [] for i in range(num_customers)}

    for cust_idx in range(num_customers):
        s = skeletons[cust_idx]
        n_tx = tx_per_customer.get(cust_idx, 0)

        for _ in range(n_tx):
            method = pick_payment_method(rng, s["upi_usage_pct"], s["card_usage_pct"])
            is_success = rng.random() < s["reliability"]
            status = "success" if is_success else "failed"
            failure_code = None if is_success else pick_failure_code(rng, method)

            variance = rng.uniform(0.3, 2.5)
            amount = Decimal(str(round(s["avg_value_target"] * variance, 2)))

            tx_time = BASE_TIME + timedelta(
                hours=rng.randint(0, 24 * 180),
                minutes=rng.randint(0, 59),
            )

            tx_id = make_uuid(rng)
            evt_id = make_uuid(rng)
            ext_event_id = f"evt_{evt_id}"

            tx = {
                "id": tx_id,
                "customer_id": s["id"],
                "merchant_id": merchant_id,
                "amount": amount,
                "currency": "INR",
                "payment_method": method,
                "status": status,
                "failure_code": failure_code,
                "source_event_id": ext_event_id,
                "created_at": tx_time,
            }
            all_transactions.append(tx)
            customer_txs[cust_idx].append(tx)

            event = {
                "id": evt_id,
                "external_event_id": ext_event_id,
                "event_type": "payment_failed" if not is_success else "payment_success",
                "customer_id": s["id"],
                "merchant_id": merchant_id,
                "transaction_id": tx_id,
                "amount": amount,
                "currency": "INR",
                "timestamp": tx_time,
                "source": "synthetic_generator",
                "metadata": None,
                "processed_at": None,
            }
            all_events.append(event)

    # Step 4: Build customer records with actual counts from generated data
    customers = []
    for cust_idx, s in enumerate(skeletons):
        txs = customer_txs[cust_idx]
        successful = sum(1 for t in txs if t["status"] == "success")
        failed = sum(1 for t in txs if t["status"] == "failed")
        amounts = [t["amount"] for t in txs]
        avg_value = round(sum(amounts) / len(amounts), 2) if amounts else Decimal("0")

        customers.append(
            {
                "id": s["id"],
                "merchant_id": merchant_id,
                "account_age_days": s["account_age_days"],
                "lifetime_tx_count": len(txs),
                "successful_count": successful,
                "failed_count": failed,
                "avg_transaction_value": avg_value,
                "upi_usage_pct": s["upi_usage_pct"],
                "card_usage_pct": s["card_usage_pct"],
                "preferred_language": s["preferred_language"],
                "preferred_channel": s["preferred_channel"],
                "created_at": BASE_TIME - timedelta(days=s["account_age_days"]),
                # Internal fields (not written to DB)
                "_archetype": s["archetype"],
                "_reliability": s["reliability"],
            }
        )

    return customers, all_transactions, all_events


def compute_hash(customers, transactions, events) -> str:
    """Compute a deterministic SHA-256 hash of all generated data."""
    h = hashlib.sha256()
    for c in sorted(customers, key=lambda x: str(x["id"])):
        h.update(
            f"C|{c['id']}|{c['account_age_days']}|{c['lifetime_tx_count']}"
            f"|{c['successful_count']}|{c['failed_count']}"
            f"|{c['avg_transaction_value']}\n".encode()
        )
    for t in sorted(transactions, key=lambda x: str(x["id"])):
        h.update(
            f"T|{t['id']}|{t['amount']}|{t['payment_method']}"
            f"|{t['status']}|{t['failure_code']}\n".encode()
        )
    for e in sorted(events, key=lambda x: str(x["id"])):
        h.update(f"E|{e['id']}|{e['event_type']}|{e['amount']}\n".encode())
    return h.hexdigest()[:16]


# ---- DB write ----


def write_to_db(session, merchant_id, customers, transactions, events):
    """Write all generated data to the database."""
    # Create default merchant
    session.add(Merchant(id=merchant_id, name="Default Merchant", created_at=BASE_TIME))
    session.flush()

    # Write customers (strip internal _ fields)
    for c in customers:
        db_fields = {k: v for k, v in c.items() if not k.startswith("_")}
        session.add(Customer(**db_fields))
    session.flush()

    # Write transactions
    for t in transactions:
        session.add(Transaction(**t))
    session.flush()

    # Write revenue events (use metadata_ attribute for the JSONB column)
    for e in events:
        session.add(
            RevenueEvent(
                id=e["id"],
                external_event_id=e["external_event_id"],
                event_type=e["event_type"],
                customer_id=e["customer_id"],
                merchant_id=e["merchant_id"],
                transaction_id=e["transaction_id"],
                amount=e["amount"],
                currency=e["currency"],
                timestamp=e["timestamp"],
                source=e["source"],
                metadata_=e["metadata"],
                processed_at=e["processed_at"],
            )
        )


# ---- Main ----


def main():
    parser = argparse.ArgumentParser(description="RecoverAI Synthetic Data Generator")
    parser.add_argument("--seed", type=int, required=True, help="Random seed")
    parser.add_argument("--count", type=int, required=True, help="Number of transactions")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Clear existing synthetic data
        print("Clearing existing synthetic data...")
        session.execute(
            text("TRUNCATE merchants, customers, transactions, revenue_events CASCADE")
        )
        session.commit()

        # Generate
        merchant_id = make_uuid(rng)
        print(f"Generating data: seed={args.seed}, count={args.count}")
        customers, transactions, events = generate(rng, args.count, merchant_id)

        # Compute hash before writing (deterministic from in-memory data)
        data_hash = compute_hash(customers, transactions, events)

        # Write to DB
        print("Writing to database...")
        write_to_db(session, merchant_id, customers, transactions, events)
        session.commit()

        # ---- Summary ----
        failed = sum(1 for t in transactions if t["status"] == "failed")
        succeeded = len(transactions) - failed
        print(f"\n{'='*60}")
        print(f"Generation complete!")
        print(f"  Seed:           {args.seed}")
        print(f"  Customers:      {len(customers)}")
        print(f"  Transactions:   {len(transactions)}")
        print(f"  Revenue Events: {len(events)}")
        print(f"  Failed txns:    {failed} ({100*failed/len(transactions):.1f}%)")
        print(f"  Successful:     {succeeded} ({100*succeeded/len(transactions):.1f}%)")
        print(f"  Data Hash:      {data_hash}")
        print(f"{'='*60}")

        # ---- Sample: 5 customers ----
        print(f"\nSample customers (first 5):")
        for c in customers[:5]:
            sr = (
                f"{c['successful_count']}/{c['lifetime_tx_count']}"
                if c["lifetime_tx_count"] > 0
                else "n/a"
            )
            print(
                f"  [{c['_archetype']:8s}] id={str(c['id'])[:8]}... "
                f"age={c['account_age_days']:4d}d "
                f"txns={c['lifetime_tx_count']:3d} (ok/total={sr}) "
                f"avg=INR {c['avg_transaction_value']:>9.2f}  "
                f"upi={c['upi_usage_pct']:.0%} card={c['card_usage_pct']:.0%}  "
                f"lang={c['preferred_language']}"
            )

        # ---- Sample: transactions for first customer with data ----
        for c in customers:
            c_txs = [t for t in transactions if t["customer_id"] == c["id"]]
            if c_txs:
                print(
                    f"\nSample transactions for customer "
                    f"{str(c['id'])[:8]}... ({c['_archetype']}):"
                )
                for t in c_txs[:5]:
                    fc = f" [{t['failure_code']}]" if t["failure_code"] else ""
                    print(
                        f"  INR {t['amount']:>10.2f}  {t['payment_method']:10s}  "
                        f"{t['status']:7s}{fc}"
                    )
                break

    except Exception as ex:
        session.rollback()
        print(f"ERROR: {ex}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
