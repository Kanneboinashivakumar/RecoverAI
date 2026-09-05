# CHECKPOINT — Vertical Slice (do this before Phase 9)

This is not a build phase — it's a mandatory gate. Per the master blueprint's build order: prove ONE transaction can move through the ENTIRE loop before scaling to volume or adding breadth (evaluation, escalation UI, India-specific depth, dashboard).

## What to do
Take exactly one synthetic transaction and run it manually through Phases 3–8 in sequence:
detect → diagnose → predict → compute EV → LLM recommend → policy authorize → execute (mock) → verify → audit.

## Why this matters more than any individual phase
If this doesn't work cleanly end-to-end, every later phase (evaluation engine, dashboard, India depth) will be built on a shaky foundation and you'll find the real bugs much later, at much higher cost to fix. This is the single highest-leverage checkpoint in the whole build.

## Acceptance Checklist
- [ ] One transaction, traced by hand, produces a complete and correct `audit_events` trail
- [ ] The Decision Receipt (per Design System) can be rendered from that trail's data — even as a raw JSON dump at this stage, not yet styled
- [ ] Every stage's output is exactly what Ground Truth's schemas specify — no ad-hoc field names snuck in along the way
- [ ] You (the user) have personally read through the trace and it makes logical sense end-to-end — not just "it ran without erroring"

## Do not proceed to Phase 9 until this checkpoint genuinely passes.
If something is off here, fix it now — don't note it as a "known issue" and move on. Bugs at this layer get expensive fast once volume and UI are built on top.
