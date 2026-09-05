# Phase 5 — Recovery ML Model + Expected Value Engine

**Depends on: Phase 4. Read `01-GROUND-TRUTH.md` first.**

## Goal
A probability model that predicts recovery likelihood from observable features (never the hidden simulator function), and a deterministic EV engine on top of it.

## Do NOT
- Do not let the model see the hidden ground-truth outcome function from Phase 2 — it trains/predicts only on observable features (customer history, failure reason, amount, method, timing).
- Do not report bare accuracy as the headline ML metric.
- Do not let the LLM (later phases) compute or override the EV — this stays deterministic Python.

## Deliverables
1. `scripts/train_model.py` — scikit-learn model trained on observable features + actual outcomes (drawn from the simulator's resolved outcomes on a training slice, not the hidden function itself), with a proper train/validation/held-out-test split (e.g. 70/15/15).
2. Calibration reporting: ROC-AUC, Brier score / calibration curve — reported and stored, not just printed once and discarded.
3. `app/engines/prediction.py` — loads the trained model, outputs a recovery probability per transaction.
4. `app/engines/expected_value.py` — deterministic: `probability × recoverable_amount − cost`, where cost is a simple configurable constant per action type at this stage (rich cost modeling is a later stretch item, not required here).

## Acceptance Checklist
- [ ] Model never had access to the hidden outcome function during training — only observable features and resolved outcomes from its training slice
- [ ] Train/validation/held-out-test split is real and reported, not fabricated
- [ ] Calibration metrics (ROC-AUC, Brier score) are computed and stored, not just accuracy
- [ ] EV calculation is deterministic Python, reproducible, no LLM involvement
- [ ] EV Engine correctly ranks a low-probability high-value transaction against a high-probability low-value one (sanity check the ranking makes sense)

## Verification Steps
Report the actual held-out test metrics (ROC-AUC, Brier score) from a real training run — not placeholder numbers. Show 3 transactions with their probability, amount, and computed EV, and confirm the ranking is sensible.
