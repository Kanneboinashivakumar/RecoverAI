# RecoverAI — Progress Tracker

Update this file yourself after each phase's verification genuinely passes — don't let Antigravity update this on your behalf without you personally confirming the verification steps. This file is the actual source of truth for "what's built," not the chat history.

## How to use
- [ ] unchecked = not started or not verified
- [~] in progress
- [x] verified done (verification steps in the phase file were actually run and passed)

## Phases

- [ ] Phase 1 — Project Scaffold & Database
- [ ] Phase 2 — Synthetic Data Generator + Counterfactual Simulator
- [ ] Phase 3 — Event Normalizer + Risk Detection
- [ ] Phase 4 — Diagnosis Engine (Deterministic + LLM)
- [ ] Phase 5 — Recovery ML Model + Expected Value Engine
- [ ] Phase 6 — LLM Recommendation + Action Contract
- [ ] Phase 7 — Policy / Guardrail Engine
- [ ] Phase 8 — Action Executor, Verification, Audit Trail
- [ ] **CHECKPOINT — Vertical Slice** (mandatory gate, do not skip)
- [ ] Phase 9 — Baseline + Experiment / Evaluation Engine
- [ ] Phase 10 — Recovery Queue
- [ ] Phase 11 — India-Specific Depth
- [ ] Phase 12 — Dashboard (7 screens)
  - [ ] Overview
  - [ ] Transactions
  - [ ] Recovery Queue
  - [ ] Agent Replay
  - [ ] Policy Center
  - [ ] Experiment Lab
  - [ ] Decision Receipt component
- [ ] Phase 13 — Deployment

## After all phases: final submission tasks (not in a phase file — do these yourself)
- [ ] Record the 5-minute pitch video around the demo story (high-value blocked transaction + smaller recovered transaction, same run)
- [ ] Write the application form's "what broke" answer using the REAL failure story from an actual bug encountered during the build (Phase 6 or 7 is the likely source — an invalid LLM proposal caught by validation)
- [ ] Fill in the application form's other 11 items (name, college, graduation year, track, project name, what it solves, GitHub URL, etc.)
- [ ] Final review: re-read `01-GROUND-TRUTH.md`'s non-negotiable rules and confirm the finished product doesn't violate any of them (no hardcoded numbers, simulation labeled everywhere, baseline stayed dumb, etc.)

## Notes / issues log
(Use this space to jot down anything a phase surfaced that needs revisiting — don't lose it in chat history.)
