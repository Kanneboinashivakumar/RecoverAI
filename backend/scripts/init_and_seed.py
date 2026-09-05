#!/usr/bin/env python3
"""
Pre-seeding & database readiness script for RecoverAI.
Guarantees that when running on a fresh database, demo data (seed 42, count 1000 / count 500)
is automatically generated and evaluated on first boot, so Overview is immediately populated.
Subsequent restarts skip this check in <100ms.
"""

import os
import sys
import time
import subprocess
from sqlalchemy import create_engine, text


def wait_for_db(max_retries=30, delay=1):
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[init_and_seed] ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print(f"[init_and_seed] Waiting for PostgreSQL at {db_url.split('@')[-1]}...")
    engine = create_engine(db_url)
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[init_and_seed] PostgreSQL is ready (attempt {attempt}).")
            return engine
        except Exception:
            print(f"[init_and_seed] Waiting for database (attempt {attempt}/{max_retries})...")
            time.sleep(delay)

    print("[init_and_seed] ERROR: Database connection timed out.", file=sys.stderr)
    sys.exit(1)


def is_seeded(engine):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT count(*) FROM experiments")).scalar()
            return bool(result and result > 0)
    except Exception:
        # Table might not exist yet
        return False


def seed_demo_data():
    print("=" * 70)
    print("[init_and_seed] First run detected: Database is empty.")
    print("[init_and_seed] Auto-seeding verified demo data (seed=42)...")
    print("=" * 70)

    # 1. Reset and populate default merchant & policy
    print("[init_and_seed] 1/3 Initializing default policies...")
    subprocess.run([sys.executable, "scripts/reset_and_populate.py"], check=True)

    # 2. Generate synthetic data (seed 42, count 1000)
    print("[init_and_seed] 2/3 Generating synthetic transaction dataset (seed 42, count 1000)...")
    subprocess.run([sys.executable, "scripts/generate_data.py", "--seed", "42", "--count", "1000"], check=True)

    # 3. Run verified experiment batch (seed 42, count 500)
    print("[init_and_seed] 3/3 Running verified experiment batch (seed 42, count 500)...")
    subprocess.run([sys.executable, "scripts/run_experiment.py", "--seed", "42", "--count", "500"], check=True)

    print("=" * 70)
    print("[init_and_seed] Auto-seeding complete! Overview and all 7 screens ready.")
    print("=" * 70)


def main():
    engine = wait_for_db()
    if not is_seeded(engine):
        seed_demo_data()
    else:
        print("[init_and_seed] Database already contains seeded experiment data. Skipping pre-seed.")


if __name__ == "__main__":
    main()
