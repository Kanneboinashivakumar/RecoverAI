# Phase 9 — Baseline + Experiment / Evaluation Engine

**Depends on: Checkpoint passed. Read `01-GROUND-TRUTH.md` first.**

## Goal
Run the dumb baseline and RecoverAI against the same batch and the same hidden simulator, and produce an honest A/B comparison.

## Do NOT
- Do not give the baseline access to customer history, probability, EV, or policy logic — it must be exactly `IF payment_failed: retry_after_24h`, nothing smarter.
- Do not fabricate or round up any comparison number — report exactly what the run produces.
- Do not let either policy see the hidden simulator function directly — both only choose actions based on observable features; the simulator resolves outcomes for both, blind to which policy chose the action.

## Deliverables
1. `app/domain/policies/baseline.py` — the deliberately dumb fixed-rule policy.
2. `scripts/run_experiment.py` — runs a batch (parameterized by seed and count) through both Baseline and RecoverAI, using the SAME simulator instance/seed so both are compared against the same hidden ground truth.
3. Output metrics: incremental ₹ recovered (primary), recovery rate, unnecessary interventions, escalations, for both policies — stored in the `experiments` table.

## Acceptance Checklist
- [ ] Baseline policy contains zero references to customer history, ML probability, or EV
- [ ] Both policies are run against the identical simulated batch (same seed) so the comparison is apples-to-apples
- [ ] The experiment can be re-run with a different seed and produces a different but still-plausible result (not identical every time, not nonsensical)
- [ ] Primary reported metric is incremental ₹ recovered, not just recovery rate
- [ ] No number in the output is hand-edited or rounded beyond normal currency display

## Verification Steps
Run the experiment at seed=42, count=1000. Report the actual real numbers: baseline recovery, RecoverAI recovery, incremental delta, action counts. Then re-run at seed=7 and show the numbers differ.
