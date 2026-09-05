# Phase 1 — Project Scaffold & Database

**Read `01-GROUND-TRUTH.md` first. This phase does not touch UI or AI/ML — pure infrastructure.**

## Goal
A running FastAPI + PostgreSQL skeleton, with the full schema created, Docker Compose working, and nothing else.

## Do NOT
- Do not implement any business logic (risk detection, diagnosis, ML, LLM calls) in this phase.
- Do not add any table not listed in Ground Truth's "Core DB tables" section.
- Do not add Redis, Kafka, or any other datastore.

## Deliverables
1. `backend/` FastAPI project using the module structure: `app/api/`, `app/domain/`, `app/engines/`, `app/integrations/`, `app/models/`, `app/db/`, `app/core/`, plus `tests/` and `scripts/`.
2. PostgreSQL schema/migrations for all tables listed in Ground Truth, including the exact `audit_events` columns specified.
3. `docker-compose.yml` that brings up backend + Postgres with one command.
4. A single working health-check endpoint (`GET /health`) that confirms DB connectivity.

## Acceptance Checklist
- [ ] `docker compose up` starts backend + Postgres with no manual steps
- [ ] `GET /health` returns 200 and confirms DB connection
- [ ] All 13 tables exist in the DB with correct columns (spot-check `audit_events` columns match spec exactly)
- [ ] No business-logic code exists yet — this phase is infra only
- [ ] Repo has a `.env.example` (no real secrets committed)

## Verification Steps (run these, paste real output back)
```
docker compose up -d
curl http://localhost:8000/health
docker compose exec db psql -U postgres -c "\dt"
```
Expected: health check returns success; `\dt` lists all 13 tables.
