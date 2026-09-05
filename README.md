# RecoverAI — Autonomous Revenue Recovery Agent

[![Docker Compose](https://img.shields.io/badge/docker--compose-v2.0+-blue.svg)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **RecoverAI** is an agentic revenue recovery system designed for Indian subscription and SaaS businesses. It intercepts failed recurring and checkout payments, diagnoses failure root causes, models recovery probabilities with machine learning, computes econometric expected values, and authorizes recovery actions through strict deterministic guardrails before execution and counterfactual verification.

**Core Thesis**: *AI can recommend. Deterministic policy authorizes.*

---

## What the Evaluation Actually Found

Most recovery systems claim their AI works. We ran a controlled experiment to check.

We compared RecoverAI against a deliberately dumb, fixed-rule baseline
(`IF payment_failed: retry_after_24h`, with zero access to customer
history, ML probability, or expected value) — both evaluated on the
identical synthetic batch, against the same hidden ground-truth outcome
function, across multiple random seeds.

**The honest result: RecoverAI's overall net incremental recovery varies
by seed** — because roughly half of at-risk transaction value is
correctly routed to human escalation rather than acted on automatically,
and this simulation doesn't model a human resolving those tickets, so
escalated value is conservatively uncredited. Meanwhile the baseline
blindly retries *everything*, including high-risk transactions our
guardrails correctly refuse to automate — occasionally winning by
recklessness alone.

**But on every transaction RecoverAI is confident enough to act on
autonomously, it beat the baseline in every single seed we tested**,
by margins from +₹172K to +₹349K on 1,000-transaction batches. That's
not a cherry-picked run — it's the consistent pattern across every seed,
reported alongside the overall (more conservative) number, not instead
of it.

We think this is a more honest and more interesting finding than a flat
"our AI recovers more money" claim: **it demonstrates that knowing when
not to automate is itself the intelligent behavior**, showing up
quantitatively, not just as a design principle we assert.

Full methodology and per-seed breakdown: see `FINDINGS.md`.

---

## Live Deployment & Hosted Link

- **Live Dashboard**: [https://recoverai-frontend.onrender.com](https://recoverai-frontend.onrender.com) *(Render Blueprint)*
- **API Documentation**: [https://recoverai-backend.onrender.com/docs](https://recoverai-backend.onrender.com/docs)
- **Health Check**: [https://recoverai-backend.onrender.com/health](https://recoverai-backend.onrender.com/health)

---

## 5-Minute Quickstart (One Command, Zero Config)

### 1. Clone & Launch
```bash
git clone https://github.com/Kanneboinashivakumar/RecoverAI.git
cd RecoverAI

# Copy environment template (no secrets required for local demo)
cp .env.example .env

# Build and start all services (PostgreSQL, FastAPI Backend, React Frontend)
docker compose up --build
```

### 2. Open the Dashboard
- **Frontend Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

> [!NOTE]
> **First-Run Auto-Seeding**: On first boot, the backend automatically detects an unseeded database, applies Alembic migrations, and pre-seeds the verified demo dataset (`seed=42`, `count=1000`, `n=500`). The Overview dashboard and all 7 views are immediately populated with the verified net incremental lift of **+₹5,126.03** without requiring manual seeding commands. Subsequent restarts start instantly in <100ms.

---

## Architecture & Execution Pipeline

```
[ Payment Failure Event ]
            │
            ▼
  1. Risk Scoring (Isolation Forest ML Anomaly Detection)
            │
            ▼
  2. Deterministic Rule-Based Diagnosis (Failure codes & taxonomy)
            │
            ▼
  3. ML Recovery Probability (Calibrated Gradient Boosting)
            │
            ▼
  4. Econometric Expected Value Engine (EV = P(rec) × Value − Cost)
            │
            ▼
  5. LLM Recommendation (Gemini 3.5 Flash Lite → Structured Action Contract)
            │
            ▼
  6. Backend Verification (Authoritative numeric checks on LLM claims)
            │
            ▼
  7. Policy / Guardrail Engine (6 Authoritative Deterministic Guardrails)
       ├── APPROVED  ──► Mock Action Executor ──► Outcome Verification ──► Audit Trail
       ├── ESCALATED ──► Recovery Queue (Human Review with Reason Codes)
       └── BLOCKED   ──► Policy Stoppage (Zero-Cost Guardrail Protection)
```

### Separation of Responsibilities

| Pipeline Responsibility | Handled By | Guarantees |
| :--- | :--- | :--- |
| **Financial Amounts & Timestamps** | Deterministic Python & PostgreSQL | Immutable, audited transaction values |
| **Expected Value Verification** | Econometric Python Formulas | Strict EV formula verification before execution |
| **Recovery Probability** | Scikit-Learn Gradient Boosting | Calibrated probability estimation |
| **Action Proposal & Copy** | Google Gemini (One provider, one API) | Context-aware, personalized messaging |
| **Policy Enforcement & Final Authorization** | Deterministic Policy Engine | **NEVER the LLM**; amount tiers, cooling windows, idempotency |
| **Mandate Regulatory Guardrails** | NPCI / RBI AutoPay Compliance Rules | Cooling-off windows, revoked mandate blocks |

---

## The 7 Dashboard Views

1. **Overview (`/`)**: Headline KPI card displaying *Simulated Net Incremental ₹ Recovered* (`+₹5,126.03`), secondary recovery rate and event metrics, top failure reasons, and a dual-axis failure vs. recovery trend chart. Includes an interactive modal to run multi-seed batch experiments.
2. **Transaction Explorer (`/transactions`)**: Searchable, paginated data table filterable by payment method (`UPI`, `CARD`, `NETBANKING`, `MANDATE`), policy verdict (`APPROVED`, `BLOCKED`, `ESCALATED`), and UUID prefix.
3. **Transaction Detail & Decision Receipt (`/transactions/:id`)**: Complete metadata inspection featuring the 3-panel **Decision Receipt**:
   - *AI Recommendation* (Indigo): Proposed action, channel, delay, and claimed EV.
   - *Backend Verification* (Neutral): Authoritative formula verification and claim checks.
   - *Policy Authorization* (Semantic color): Individual pass/fail verdicts for all 6 policy checks (Amount Tiers, Retries, Contacts, Discounts, Idempotency, Mandate Compliance).
4. **Recovery Queue (`/recovery-queue`)**: Operational workflow queue for compliance teams to review and resolve `ESCALATED` and `BLOCKED` transactions with interactive decision resolution modals.
5. **Agent Replay (`/agent-replay/:id`)**: Forensic vertical timeline reconstructing the full 8-step decisioning lifecycle directly from `audit_events` with collapsible JSON snapshot payloads.
6. **Policy Center (`/policy-center`)**: Real-time policy parameter configuration (`PUT /api/policy-center/config`) with instant version increments and complete rule catalog.
7. **Experiment Lab (`/experiment-lab`)**: Side-by-side A/B evaluation matrix comparing the fixed-rule baseline against RecoverAI across arbitrary seeds.

---

## Why This Isn't Just Another LLM Wrapper

- **The LLM never controls money — we can prove it, not just claim it.**
  Every Action Contract the LLM proposes is independently re-verified: its
  stated `confidence` and `expected_value` are recomputed against the
  authoritative EV Engine before any Policy check runs. During
  development, we caught a real case where the LLM's stated expected
  value omitted an action's operational cost — overstating the true
  value by exactly that cost. Our reconciliation step caught and
  corrected it automatically. Both the LLM's original claim and the
  corrected value are stored, so this is auditable in the product itself
  (see any Transaction Detail page → "Backend Verification" panel), not
  just described here.
- **We show what we didn't do, not just what we did.** The Recovery
  Queue and every blocked/escalated Decision Receipt show cases where
  RecoverAI deliberately declined to act automatically, with the exact
  policy reason code — a system that tries to recover every rupee isn't
  intelligent; one that knows when not to try is.
- **Every ₹ figure is labeled as simulated, on every screen that shows
  one.** We don't have real Razorpay production data, so we don't imply
  we do. Every number is reproducible from a stated seed — change the
  seed, get a different but internally consistent result.
- **The LLM is used only where it adds value.** Deterministic Python
  handles amounts, retry/contact limits, and all policy authorization.
  ML handles probability estimation. The LLM is reserved for genuinely
  ambiguous failure diagnosis and customer-facing messaging — never for
  financial decisions.

---

## Automated Verification

The repository includes standalone Playwright verification suites to prove end-to-end functionality:

### 1. End-to-End User Click-Through Verification
Navigates through all 7 views in a single session without page reloads, verifying API synchronization, table rendering, Decision Receipts, and full 8-step Agent Replays:
```bash
cd frontend
node verify_clickthrough.cjs
```
*Expected duration: <10 seconds. All checks pass.*

### 2. Backend Disconnection & Loud Failure Test
Confirms the application adheres to Ground Truth Rule 1 (Zero Mock Data) by stopping the backend and proving the frontend fails loudly with error banners rather than falling back to silent mock numbers:
```bash
cd frontend
node verify_backend_failure.cjs
```
*Expected result: "PASSED: Frontend visibly and loudly fails on backend disconnect."*

---

## Environment Variables Reference

| Variable | Description | Default (Local) |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:changeme@db:5432/recoverai` |
| `POSTGRES_USER` | PostgreSQL superuser username | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password | `changeme` |
| `POSTGRES_DB` | PostgreSQL database name | `recoverai` |
| `GEMINI_API_KEY` | Google Gemini API Key (for single-transaction LLM routing) | *(Optional for batch demo)* |
| `GEMINI_MODEL` | LLM model identifier | `gemini-3.5-flash-lite` |
| `BACKEND_URL` | Backend URL for frontend proxy | `http://backend:8000` |

---

## Deploying to Render via Blueprint

The repository includes a ready-to-deploy [`render.yaml`](render.yaml) blueprint:
1. Fork or push this repository to GitHub: `https://github.com/Kanneboinashivakumar/RecoverAI`.
2. Log in to [Render](https://dashboard.render.com).
3. Click **New +** $\to$ **Blueprint**.
4. Connect your repository. Render will automatically configure:
   - **PostgreSQL Database** (`recoverai-db`)
   - **FastAPI Backend Web Service** (`recoverai-backend`)
   - **React Frontend Web Service** (`recoverai-frontend`)
5. Click **Apply**. The backend container will auto-seed the demo data on startup, making the live URL fully operational in minutes.
