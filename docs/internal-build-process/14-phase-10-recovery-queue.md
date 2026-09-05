# Phase 10 — Recovery Queue (Human Escalation)

**Depends on: Phase 9. Read `01-GROUND-TRUTH.md` first.**

## Goal
A queryable list of transactions the Policy Engine blocked or routed to human review, each carrying its reason codes.

## Do NOT
- Do not build any actual human-approval workflow automation (e.g. auto-approve after N hours) — this phase is display + simple manual-approve/reject only.
- Do not lose the reason codes between Policy Engine output and this queue's display — they must pass through unchanged.

## Deliverables
1. `app/api/policies.py` (or similar) endpoint returning all `ESCALATED`/`BLOCKED` transactions with their reason codes.
2. A simple manual action: a human can mark a queued item as reviewed/approved/rejected — this writes to `audit_events` like everything else, so it's part of the replay trail too.

## Acceptance Checklist
- [ ] Every blocked/escalated transaction appears in the queue with its actual reason codes (not a generic "blocked" label)
- [ ] Manually resolving a queue item is itself logged to `audit_events`
- [ ] The queue reflects real Policy Engine output — no separate hardcoded escalation list

## Verification Steps
Show 5 real entries in the Recovery Queue with their reason codes, sourced from an actual experiment run (Phase 9), not manually inserted test data.
