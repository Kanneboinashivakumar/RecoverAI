# Phase 4 — Diagnosis Engine (Deterministic + LLM)

**Depends on: Phase 3. Read `01-GROUND-TRUTH.md` first.**

## Goal
For each at-risk event, produce a diagnosis: deterministic lookup for clear failure reasons, LLM call only for genuinely ambiguous ones.

## Do NOT
- Do not send every event to the LLM — this defeats the deterministic/LLM split that is central to the whole pitch. Most failure reasons in the taxonomy are clear-cut and must be resolved without any LLM call.
- Do not let the LLM output free text only — its diagnosis output must include structured reason codes.

## Deliverables
1. `app/engines/diagnosis.py` — a lookup table mapping clear taxonomy codes (e.g. `CARD_EXPIRED`) directly to a diagnosis with no LLM call.
2. For genuinely ambiguous cases (e.g. unstructured/unclear gateway error text) — an LLM call that returns a diagnosis + confidence + reason codes.
3. Every diagnosis, deterministic or LLM-sourced, is tagged with its source (`deterministic` or `llm`) — this tag must be visible later in Agent Replay.

## Acceptance Checklist
- [ ] The majority of test events resolve via the deterministic path, with zero LLM calls
- [ ] Only genuinely ambiguous cases trigger an LLM call
- [ ] Every diagnosis record includes a `source` field (`deterministic` / `llm`)
- [ ] LLM diagnosis output is structured (parseable reason codes), not just prose

## Verification Steps
Run a batch of 100 mixed events. Report: how many were diagnosed deterministically vs via LLM, and show 2 examples of each with their reason codes.
