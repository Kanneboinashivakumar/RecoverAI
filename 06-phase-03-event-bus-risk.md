# Phase 3 — Event Normalizer + Risk Detection

**Depends on: Phase 2. Read `01-GROUND-TRUTH.md` first.**

## Goal
Normalize raw generated events into the Revenue Event Bus format, and score each as at-risk or not, deterministically.

## Do NOT
- Do not call any ML model or LLM in this phase — risk scoring here is deterministic rules only.
- Do not skip the normalization step and read raw generator output directly in later phases — everything downstream reads from the normalized event schema.

## Deliverables
1. `app/domain/events/` — normalized `RevenueEvent` schema: `event_type, customer_id, merchant_id, amount, currency, timestamp, source, metadata`.
2. `app/engines/risk.py` — deterministic risk scoring: given a normalized event, output an at-risk boolean + severity score, based on value, customer history, and failure type.
3. Idempotency handling: duplicate `event_id`s are detected and ignored, not reprocessed.

## Acceptance Checklist
- [ ] Every event type from the taxonomy normalizes correctly into `RevenueEvent`
- [ ] Risk scoring is deterministic — same input always produces same output (no randomness, no LLM call)
- [ ] Sending the same `event_id` twice results in exactly one processed record, not two
- [ ] Risk score correlates sensibly with severity (a ₹50,000 card decline from a high-failure-history customer scores as more at-risk than a ₹200 UPI timeout from a reliable customer)

## Verification Steps
Feed the same batch of events through twice (simulating a duplicate webhook delivery) and confirm no duplicate processing. Pick 3 transactions with obviously different risk profiles and show their risk scores line up with intuition — paste the 3 examples with scores back.
