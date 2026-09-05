# Phase 11 — India-Specific Depth

**Depends on: Phase 10. Read `01-GROUND-TRUTH.md` first.**

## Goal
UPI mandate lifecycle modeling and contextual Hinglish messaging — the depth that differentiates this from a generic recovery bot.

## Do NOT
- Do not treat this as a cosmetic label change — the mandate lifecycle must actually gate what recovery actions are valid (a revoked mandate must not be retryable the same way a transient timeout is).
- Do not generate templated Hindi translation ("Aapka payment fail ho gaya") — Hinglish messages must be generated contextually from the specific failure + proposed action via the LLM, per Ground Truth.

## Deliverables
1. `app/domain/mandate/` — mandate state machine: Created → Active → Debit Attempt → Success/Failure → Retry Eligibility → Retry Window → Success/Escalation. Card retries and UPI mandate retries use visibly distinct logic paths.
2. LLM messaging prompt updated to generate contextual Hinglish output when a customer profile's preferred language is Hinglish (from Phase 2's customer profiles), tied to the specific failure reason and proposed action.

## Acceptance Checklist
- [ ] A mandate-related transaction's recovery options are visibly different from a card transaction's (not just a different label on the same logic)
- [ ] A revoked/expired mandate is correctly NOT offered a standard retry
- [ ] Generated Hinglish messages differ meaningfully based on failure reason and action (not the same templated sentence every time) — show 3 different examples

## Verification Steps
Show one full mandate-failure transaction's lifecycle trace, and 3 different generated Hinglish messages for 3 different failure/action combinations.
