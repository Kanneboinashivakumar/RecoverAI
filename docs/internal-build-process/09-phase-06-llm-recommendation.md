# Phase 6 — LLM Recommendation + Action Contract

**Depends on: Phase 5. Read `01-GROUND-TRUTH.md` first.**

## Goal
The LLM proposes an intervention as a structured, schema-validated Action Contract — never a free-form action, never trusted on its own numbers.

## Do NOT
- Do not let the LLM's output execute anything directly — this phase produces a proposal only, nothing is authorized or executed yet (that's Phase 7/8).
- Do not trust the LLM's stated `confidence`, `expected_value`, or `amount` as final — the backend must re-verify these against the EV Engine (Phase 5) and DB before passing the proposal onward.
- Do not let the LLM invent an `action_type` outside the defined enum.

## Deliverables
1. `RecoveryAction(BaseModel)` — implement exactly the Pydantic schema from Ground Truth.
2. `app/engines/decision.py` — calls the LLM with the diagnosis + probability + EV context, constrained to output a schema-valid `RecoveryAction` proposal, choosing among valid candidate actions (RETRY / WHATSAPP / EMAIL / DISCOUNT / ESCALATE) rather than inventing arbitrary ones.
3. A verification step immediately after LLM output: re-check `confidence`, `expected_value`, `amount` against the authoritative EV Engine / DB values; if they diverge, the authoritative values win, and this is logged.
4. Reject and re-prompt (or fall back to a safe default) on schema-invalid LLM output (e.g. `delay_hours < 0`).

## Acceptance Checklist
- [ ] Pydantic validation actually rejects a malformed test payload (write a test that feeds an invalid contract and confirms it's rejected)
- [ ] LLM-stated numeric fields are shown to be overwritten/reconciled with authoritative values when they diverge (test this explicitly with a case where they'd differ)
- [ ] The LLM never outputs an `action_type` outside the enum in a batch of test runs
- [ ] Nothing executes at this stage — output is a validated proposal object only

## Verification Steps
Run the LLM recommendation step on 10 diagnosed transactions. Show the resulting Action Contracts. Then deliberately feed one malformed/invalid proposal into the validation step and show it gets rejected with a clear reason.
