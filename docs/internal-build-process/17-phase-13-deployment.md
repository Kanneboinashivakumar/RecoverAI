# Phase 13 — Deployment

**Depends on: Phase 12. Read `01-GROUND-TRUTH.md` first.**

## Goal
A reviewer can either open a live hosted link or run `docker compose up` locally and have the full app working in under 5 minutes, with no manual config.

## Do NOT
- Do not require any manual environment setup beyond copying `.env.example` to `.env` and filling in an LLM API key.
- Do not commit real API keys or secrets to the repo.

## Deliverables
1. Full `docker-compose.yml` covering backend, frontend, and Postgres, with seeded demo data pre-loaded on first run so Overview isn't empty on first open.
2. Deployment to a free-tier host (Railway/Render or similar) with a stable public URL.
3. A short `README.md` at repo root: one-command local run instructions, the live URL, and a 2-3 sentence project summary linking back to the blueprint's problem statement.

## Acceptance Checklist
- [ ] A clean clone of the repo + `docker compose up` results in a fully working app, tested from a genuinely fresh environment (not just "works on my machine")
- [ ] The hosted live URL works and shows real data, not an empty/broken state
- [ ] No secrets are committed anywhere in the repo (double-check `.env` is gitignored)
- [ ] README is accurate — every command in it actually works if followed literally

## Verification Steps
Have someone else (or a genuinely fresh clone/container) run the setup instructions exactly as written and confirm it works with zero deviation from the README.
