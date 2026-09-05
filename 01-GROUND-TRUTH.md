# RecoverAI — Ground Truth (paste this at the start of every Antigravity session)

## What this is
RecoverAI — an AI Revenue Recovery agent for Razorpay's Super Dream Offer buildathon, Track 03. It detects at-risk revenue events, decides whether and how to recover them, executes inside strict deterministic guardrails, and proves the outcome.

**Core thesis, non-negotiable:** AI can recommend. AI cannot directly control money.

## Architecture (do not deviate from this shape)

```
Synthetic Events (seeded, correlated, hidden counterfactual outcomes)
        ↓
Event Normalizer (Revenue Event Bus)
        ↓
Deterministic Risk Detection
        ↓
Diagnosis (deterministic for clear cases, LLM for ambiguous)
        ↓
Recovery ML Model → probability
        ↓
Expected Value Engine (probability × value − cost)
        ↓
LLM Recommendation → Action Contract (Pydantic, typed proposal)
        ↓
Backend verifies LLM's numeric claims against authoritative sources
        ↓
POLICY / GUARDRAIL ENGINE (deterministic: amount tier, confidence,
retry/contact caps, discount limits, idempotency)
        ↓
   BLOCKED → Recovery Queue (human escalation)
   APPROVED → Mock Action Executor → Verification → Audit Trail
        ↓
Evaluation Engine: Baseline (dumb, fixed 24h retry) vs RecoverAI,
same simulator, same hidden ground truth → incremental ₹ recovered
```

## Responsibility split — never blur this

| Layer | Handled by |
|---|---|
| Amounts, history, retry/contact counts, idempotency | Deterministic Python |
| Expected-value math | Deterministic Python |
| Policy limits, final authorization | Deterministic Python — NEVER the LLM |
| Recovery probability | ML model |
| Ambiguous diagnosis, customer messaging | LLM |

The LLM recommends. The Policy Engine authorizes. These are different pipeline stages with different names — never call both a "decision."

The LLM's numeric fields (confidence, expected_value, amount) in its Action Contract output are claims, not facts — the backend always re-verifies them against the EV Engine / DB before the Policy Engine evaluates the proposal.

## Tech stack (do not add anything not listed here)
- Backend: FastAPI (Python), Pydantic for all schemas/contracts
- DB: PostgreSQL
- ML: scikit-learn
- LLM: one provider, one API — no frameworks (no LangChain/CrewAI/AutoGen)
- Frontend: React + Tailwind
- Deployment: Docker Compose

Explicitly excluded, do not introduce under any circumstance: RAG, vector databases, multi-agent orchestration frameworks, Kafka/RabbitMQ, Kubernetes, microservices, mobile app, voice, blockchain, additional LLM providers.

## Action Contract (exact shape, implement as Pydantic model)

```python
class RecoveryAction(BaseModel):
    action_type: ActionType         # enum: RETRY, WHATSAPP, EMAIL, DISCOUNT, ESCALATE
    transaction_id: str
    amount: Decimal
    channel: Channel                # enum: UPI, CARD, NETBANKING, WHATSAPP, EMAIL
    delay_hours: int                # must be >= 0
    reason_codes: list[str]
    confidence: float
    expected_value: Decimal
    policy_context: dict
```

## Failure taxonomy (use these exact categories, extend within them if needed, don't replace them)
- UPI: UPI_COLLECT_EXPIRED, UPI_BANK_TIMEOUT, UPI_INSUFFICIENT_FUNDS, UPI_PSP_ERROR, UPI_CUSTOMER_DECLINED, UPI_LIMIT_EXCEEDED, UPI_MANDATE_FAILED, UPI_MANDATE_EXPIRED
- Cards: CARD_EXPIRED, CARD_DECLINED, CARD_LIMIT_EXCEEDED, ISSUER_TIMEOUT, INSUFFICIENT_FUNDS
- Netbanking: BANK_TIMEOUT, BANK_DECLINED, SESSION_EXPIRED
- Mandate: MANDATE_REGISTRATION_FAILED, MANDATE_EXECUTION_FAILED, MANDATE_REVOKED, MANDATE_EXPIRED
- Checkout: CHECKOUT_ABANDONED, PAYMENT_PAGE_EXIT, OTP_TIMEOUT, PAYMENT_METHOD_CHANGED
- B2B: INVOICE_OVERDUE, PAYMENT_PROMISE_BROKEN, PARTIAL_PAYMENT

## Core DB tables
merchants, customers, transactions, revenue_events, diagnoses, predictions, decisions, policy_evaluations, actions, verification_results, audit_events, experiments, policies

`audit_events` schema: id, transaction_id, event_type, timestamp, actor, input_snapshot, output_snapshot, reason_codes, policy_result

## Non-negotiable rules
1. No hardcoded demo numbers, anywhere. Every metric shown must come from an actual pipeline run with a seed. If a demo needs a specific scenario (e.g. a blocked high-value transaction), define it as a scenario type the generator matches, never a literal fixed value.
2. No new features beyond what a phase file specifies. If something seems missing, flag it to the user — don't add it unilaterally.
3. Every recovered-revenue figure is labeled as simulated ("Simulated Incremental Revenue Recovered" / a visible "Simulation / Test Mode" indicator) — never implied as real recovered money.
4. The baseline is deliberately dumb: `IF payment_failed: retry_after_24h`. No history, no probability, no EV, no policy. This is required for the A/B comparison to be scientifically valid.
5. The synthetic generator maintains a HIDDEN ground-truth outcome function that neither RecoverAI nor the baseline can see — both policies only see observable features; the simulator alone resolves the actual outcome. This is required for the A/B comparison to have a defensible ground truth.
6. Every claimed metric must be defensible if questioned — report the real number even if it's unimpressive.

## If Antigravity is unsure whether something is in scope
It is not authorized to guess. It should stop and ask, or state the assumption explicitly and flag it for review — not silently build it.
