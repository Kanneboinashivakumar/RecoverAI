# Phase 8 — Action Executor, Verification, Audit Trail

**Depends on: Phase 7. Read `01-GROUND-TRUTH.md` first.**

## Goal
Execute approved actions against a mock provider, resolve the outcome via the hidden simulator function, and log a complete forensic audit trail.

## Do NOT
- Do not build any real external integration (no real WhatsApp/email/payment API calls) — mock providers only, per Ground Truth's excluded-integrations rule.
- Do not resolve outcomes randomly/independently of the Phase 2 hidden simulator function — the simulator is the single source of truth for what "actually happened."
- Do not skip logging any pipeline stage to `audit_events` — the replay must be complete, not partial.

## Deliverables
1. `app/integrations/mock_gateway.py`, `app/integrations/messaging.py` — simple mock executors for RETRY/WHATSAPP/EMAIL/DISCOUNT actions.
2. `app/engines/verification.py` — after execution, calls the hidden simulator function (Phase 2) to resolve success/failure, and records the simulated ₹ outcome.
3. Every pipeline stage (event received → risk → diagnosis → prediction → decision → policy → action → verification) writes a row to `audit_events` with the exact schema from Ground Truth.
4. An Agent Replay query function that reconstructs a transaction's full timeline purely from `audit_events` rows, in order.

## Acceptance Checklist
- [ ] A full transaction can be replayed end-to-end purely by querying `audit_events` — no other table needed for the replay view
- [ ] Verification outcomes come from the hidden simulator, not a separate random roll
- [ ] All action types (RETRY/WHATSAPP/EMAIL/DISCOUNT/ESCALATE) have a working mock executor
- [ ] Every recovered-value field is clearly labeled/flagged as simulated in the stored record, not just in the UI layer

## Verification Steps
Pick one transaction and print its full reconstructed audit trail (every stage, in order, with timestamps and reason codes) purely from querying `audit_events`. Confirm it matches what actually happened when you trace it manually.
