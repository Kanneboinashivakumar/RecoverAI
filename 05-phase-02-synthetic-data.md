# Phase 2 — Synthetic Data Generator + Counterfactual Simulator

**Depends on: Phase 1. Read `01-GROUND-TRUTH.md` first.**

## Goal
A seeded, regenerable generator that produces realistic, correlated revenue events AND maintains the hidden ground-truth outcome function required for a valid baseline-vs-RecoverAI comparison later.

## Do NOT
- Do not generate independent random noise per event (no `amount = random()`, `customer = random()`) — customer profiles must persist and shape their own transactions.
- Do not expose the hidden outcome function to anything outside the simulator itself — no engine built in later phases may read it directly.
- Do not build merchant segments in this phase — single segment first; segments are a later stretch item, not required here.

## Deliverables
1. `scripts/generate_data.py` — accepts `--seed` and `--count`, produces persistent customer profiles (account age, lifetime tx count, success/fail history, avg value, UPI/card mix, preferred language, preferred channel) and events drawn from those profiles.
2. Events use the exact failure taxonomy categories from Ground Truth.
3. A hidden outcome function `f(customer, failure_reason, payment_method, time, action) → success probability`, stored/accessible only internally to the simulator module — this resolves the actual outcome of whichever action any policy (baseline or RecoverAI) later chooses for a given transaction.
4. Output written to the DB (`customers`, `transactions`, `revenue_events` tables from Phase 1).

## Acceptance Checklist
- [ ] Running the generator twice with the same seed produces identical output
- [ ] Running with a different seed produces different but still-coherent output (realistic distributions, not garbage)
- [ ] A given customer's transactions are visibly consistent with their profile (e.g. a "reliable" customer profile mostly produces successful/low-risk transactions)
- [ ] All failure reasons used come from the Ground Truth taxonomy — no invented categories
- [ ] The hidden outcome function exists and is NOT imported/accessible from any engine outside the simulator module

## Verification Steps
```
python scripts/generate_data.py --seed 42 --count 1000
python scripts/generate_data.py --seed 42 --count 1000   # re-run, same seed
# diff the two runs' output — should be identical
python scripts/generate_data.py --seed 7 --count 1000    # different seed
# inspect: distributions should differ from seed 42 but still look realistic
```
Paste a sample of 5 generated customers + their transactions back for a sanity check.
