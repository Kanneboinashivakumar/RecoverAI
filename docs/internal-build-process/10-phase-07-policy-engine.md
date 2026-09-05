# Phase 7 — Policy / Guardrail Engine

**Depends on: Phase 6. Read `01-GROUND-TRUTH.md` first. This is the most important phase — the entire pitch rests on this being real, not decorative.**

## Goal
A deterministic authorization layer that every Action Contract must pass through before execution. Never the LLM. Approve, block, or escalate — with reasons.

## Do NOT
- Do not let this engine call the LLM at any point — it is 100% deterministic.
- Do not let an approved action skip any check "for simplicity" — every listed check must actually run and actually be capable of blocking.
- Do not make this cosmetic (i.e. don't build a UI that shows checks passing without the backend genuinely evaluating them).

## Deliverables
1. `app/engines/policy.py` implementing, at minimum:
   - Amount-tier check (confidence-aware tiered autonomy: low-value+high-confidence → auto; mid → approval-required; high-value → human-only)
   - Retry limit check
   - Contact-frequency limit check
   - Discount limit check
   - Idempotency check (has this exact action already been taken for this transaction)
2. Each check outputs a pass/fail with a specific reason code (e.g. `RETRY_LIMIT_REACHED`, `DISCOUNT_LIMIT_EXCEEDED`).
3. Final result: `APPROVED`, `BLOCKED`, or `ESCALATED`, with the full list of check results attached — this is what populates the Decision Receipt UI later.
4. A test case that deliberately sends an invalid/excessive proposal (e.g. a discount above the limit) and confirms it is actually blocked, not merely logged.

## Acceptance Checklist
- [ ] Every check listed above is implemented and independently testable
- [ ] At least one deliberate "bad" proposal is shown being blocked, with the correct reason code
- [ ] A policy limit (e.g. discount %) can be changed via config and a re-run shows the changed behavior
- [ ] No LLM call exists anywhere in this module
- [ ] The full policy evaluation trace (all checks, pass/fail, reasons) is stored per transaction, not just the final verdict

## Verification Steps
Run 20 Action Contracts from Phase 6 through the Policy Engine. Report how many were approved/blocked/escalated and why. Then show one specific deliberately-bad case (over-limit discount, excessive retry count) being correctly blocked with its reason code.
