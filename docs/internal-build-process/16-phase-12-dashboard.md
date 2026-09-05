# Phase 12 — Dashboard (7 Screens)

**Depends on: Phase 11 (or earlier phases for progressive UI — see note below). Read `01-GROUND-TRUTH.md` AND `02-DESIGN-SYSTEM.md` first.**

## Goal
The React frontend, built against the now-working backend. This can start earlier than Phase 11 completion if you want visible progress sooner — but each screen should only be built once its backing data (from the relevant phase) is real, never mocked/hardcoded in the frontend.

## Do NOT
- Do not hardcode any number, chart value, or example transaction in the frontend — everything renders from real API responses.
- Do not build more than the 7 named screens.
- Do not deviate from the Design System tokens (colors, type, layout) — no ad-hoc styling choices.
- Do not build a chatbot-style interface anywhere.

## Deliverables — one screen at a time, verify each before starting the next
1. **Overview** — KPI cards (incremental ₹ recovered as primary, recovery rate, events, escalations, blocked), failure-reason breakdown, historic trend chart, "Simulation / Test Mode" badge, "Run Recovery" batch trigger with live progress.
2. **Transactions** (Transaction Explorer) — filterable/searchable table, click into a transaction to see its Decision Receipt.
3. **Recovery Queue** — from Phase 10's data, with reason codes and manual resolve action.
4. **Agent Replay** — forensic timeline view per transaction, reconstructed from `audit_events`.
5. **Policy Center** — real guardrail limits displayed as a control table, adjustable, with a live policy-evaluation trace for the selected transaction.
6. **Experiment Lab** — Baseline vs RecoverAI comparison from Phase 9's real experiment data, with re-run-by-seed capability.
7. **Decision Receipt component** — built once, reused in Transactions and Agent Replay, per Design System spec (recommend vs. authorize visually separated).

## Acceptance Checklist
- [ ] Every screen renders from a real API call, verifiable by killing the backend and seeing the screen fail/empty rather than show stale hardcoded data
- [ ] Design System tokens are used consistently across all 7 screens (same palette, same type scale)
- [ ] The Decision Receipt component is built once and reused, not duplicated with drift between usages
- [ ] "Simulation / Test Mode" indicator is visible on every screen showing recovered-₹ figures
- [ ] A full click-through — Overview → run a batch → click into a blocked high-value transaction → see why it was blocked → click a recovered transaction → see Agent Replay — takes under 60 seconds and requires no page reload/manual refresh

## Verification Steps
Do the full click-through above yourself and confirm it holds together. Then stop the backend and confirm the frontend visibly fails rather than silently showing old/fake data.
