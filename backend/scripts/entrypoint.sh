#!/bin/sh
set -e

echo "=== RecoverAI Backend Bootstrapping ==="

# 1. Run database schema migrations
echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

# 2. Check and auto-seed on first run (seed=42, n=500 verified demo)
echo "[entrypoint] Verifying database seed status..."
python scripts/init_and_seed.py

# 3. Launch application server
echo "[entrypoint] Starting FastAPI server on port 8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
