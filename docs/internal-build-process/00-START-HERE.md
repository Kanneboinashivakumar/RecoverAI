# RecoverAI Build Docs — How to Use These With Antigravity

This folder is the entire build plan, split into small, verifiable chunks. It exists to solve one specific problem: agentic coding tools drift and hallucinate over long sessions — they forget constraints, invent features, or claim something works without proving it. These docs are structured to prevent that.

## The workflow

1. **Start every new Antigravity session by giving it `01-GROUND-TRUTH.md`.** This is the condensed, non-negotiable context — architecture, schemas, rules. It's short on purpose so it fits easily in context and can be re-pasted cheaply. Never let Antigravity build from memory of a previous session alone — always ground it fresh.
2. **Work through the phase files in order (`02` through `14`).** Give Antigravity ONE phase file per session/task. Each phase is scoped to be buildable and independently verifiable — don't hand it two phases at once.
3. **Each phase file ends with an Acceptance Checklist and Verification Steps.** Do not mark a phase done, and do not move to the next phase, until every checklist item is genuinely checked — actually run the verification steps yourself (or have Antigravity run them and show you real output), not just accept a claim that it works.
4. **After each phase passes verification, update `03-PROGRESS-TRACKER.md`** by checking off that phase and its features. This is your single source of truth for "what's actually done" — trust this file over your memory of the conversation.
5. **Bring me (Claude) the actual output** — error messages, screenshots, test results — when you want a feature checked. I'll tell you honestly whether it matches the spec in the phase file, not just whether it looks plausible.

## Why this structure prevents hallucination

- Every phase file names its exact inputs/outputs/schemas — Antigravity isn't free to invent field names or reinterpret scope.
- Every phase has an explicit "Do NOT" list — the most common failure mode is an agent quietly adding something adjacent-but-unrequested (an extra dashboard chart, a "helpful" retry rule). These lists exist to block that.
- Every phase has a concrete verification step with expected output — "looks right" is not a pass condition; "ran X, got Y" is.
- The progress tracker is checkbox-based and lives outside the chat — it survives context resets and gives you a fast way to sanity-check "is this actually built" without re-reading transcripts.

## File index

| File | Purpose |
|---|---|
| `01-GROUND-TRUTH.md` | Paste this at the start of every session — architecture, principles, schemas |
| `02-DESIGN-SYSTEM.md` | UI/UX tokens — clean fintech look, Razorpay-adjacent, give this to Antigravity before any UI work |
| `03-PROGRESS-TRACKER.md` | Master checklist — update after every phase, check before starting the next |
| `04` – `14` | One phase each, in build order — see tracker for the full list |

## Rule for you, not just Antigravity

Don't let a session run long and "vibes-based." If a phase's verification step fails, stop and fix that phase before moving forward — don't let Antigravity move on and patch it later "once everything's built." Debt compounds fast in agentic builds; each phase should be genuinely solid before the next one depends on it.
