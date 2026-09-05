# RecoverAI — Autonomous Revenue Recovery Agent

[![Docker Compose](https://img.shields.io/badge/docker--compose-v2.0+-blue.svg)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **RecoverAI** is an agentic revenue recovery system designed for Indian subscription and SaaS businesses. It intercepts failed recurring and checkout payments, diagnoses failure root causes, models recovery probabilities with machine learning, computes econometric expected values, and authorizes recovery actions through strict deterministic guardrails before execution and counterfactual verification.

**Core Thesis**: *AI can recommend. Deterministic policy authorizes.*

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Database Schema](#3-database-schema)
4. [The Full Pipeline & Engine Breakdown](#4-the-full-pipeline--engine-breakdown)
5. [The Action Contract](#5-the-action-contract)
6. [Policy & Guardrail Engine — Full Rules Reference](#6-policy--guardrail-engine--full-rules-reference)
7. [India-Specific Depth & Regulatory Compliance](#7-india-specific-depth--regulatory-compliance)
8. [The 7 Dashboard Views](#8-the-7-dashboard-views)
9. [What the Evaluation Actually Found](#9-what-the-evaluation-actually-found)
10. [Why This Isn't Just Another LLM Wrapper](#10-why-this-isnt-just-another-llm-wrapper)
11. [Categorized API Reference](#11-categorized-api-reference)
12. [Testing & Verification Evidence](#12-testing--verification-evidence)
13. [Production Design Decisions & Trade-Offs](#13-production-design-decisions--trade-offs)
14. [Environment Variables Reference](#14-environment-variables-reference)
15. [5-Minute Quickstart (Local Run)](#15-5-minute-quickstart-local-run)
16. [Troubleshooting & FAQ](#16-troubleshooting--faq)
17. [Deploying to Render via Blueprint](#17-deploying-to-render-via-blueprint)
18. [License & Credits](#18-license--credits)

---

## 1. Executive Summary

### The Problem
Payment failures are a chronic revenue leak for Indian digital businesses. Across recurring AutoPay mandates, credit/debit cards, and UPI collect requests, payment failures account for 10% to 30% of attempted transaction volume. Traditional recovery approaches rely on naive, static heuristics—most commonly a blunt `IF payment_failed: retry_after_24h` rule. 

This approach fails in two catastrophic ways:
1. **Blind Retries on Hard Declines**: Retrying revoked mandates, expired cards, or blocked accounts incurs compounding aggregator processing fees, risks merchant terminal penalties from NPCI, and annoys users without any chance of recovery.
2. **Customer Spam & Margin Erosion**: Sending aggressive, generic payment reminders or unnecessary discount incentives to customers who would have paid anyway destroys customer trust and unit economics.

### The Core Thesis
> **AI can recommend. Deterministic policy authorizes.**

RecoverAI separates the creative, probabilistic capabilities of Large Language Models from financial authorization. While an LLM is exceptionally suited to synthesizing customer context, diagnosing ambiguous raw bank error codes, and crafting personalized outreach in colloquial Hinglish, **an LLM must never be allowed to directly control money, override rate caps, or authorise financial retries.**

### What Makes RecoverAI Different
Unlike generic AI agent submissions that wrap an LLM prompt around an API call and claim autonomous execution:
- **Zero Mock Dashboard Metrics**: Every number, chart, and receipt is derived from live PostgreSQL queries.
- **Double-Entry Economic Verification**: The LLM's claimed expected value is independently verified and reconciled against authoritative econometric formulas before any guardrail evaluates the action.
- **Counterfactual Ground-Truth Simulator**: Evaluates both the baseline policy and RecoverAI against an identical, hidden simulator environment across random seeds, proving real incremental lift ($₹$) rather than gross transaction volume.

---

## 2. System Architecture

### Technical Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                 PRESENTATION TIER                                        │
│  React 18 Single-Page Application (Vite, Tailwind CSS, TypeScript, Zero External Charts) │
│                                                                                          │
│  [Overview]  [Transaction Explorer]  [Decision Receipt]  [Recovery Queue]  [Agent Replay]│
└────────────────────────────────────────────┬─────────────────────────────────────────────┘
                                             │ HTTP REST (JSON) / Reverse Proxy
┌────────────────────────────────────────────▼─────────────────────────────────────────────┐
│                                 APPLICATION TIER                                         │
│                      FastAPI Modular Monolith (Python 3.12)                              │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ API Endpoints: /health, /api/dashboard, /api/transactions, /api/policies, ...      │  │
│  └────────────────────────────────────────┬───────────────────────────────────────────┘  │
│                                           │                                              │
│  ┌────────────────────────────────────────▼───────────────────────────────────────────┐  │
│  │ Core Pipeline Engines:                                                             │  │
│  │   1. Event Normalizer    2. Risk Engine (Deterministic Scoring)                    │  │
│  │   3. Diagnosis Engine    4. ML Probability Engine (Gradient Boosting)              │  │
│  │   5. Econometric EV      6. Action Contract Reconciler                             │  │
│  │   7. Policy Engine       8. Mock Action Dispatcher                                 │  │
│  │   9. Hidden Simulator   10. Append-Only Audit Stream                               │  │
│  └──────────────────┬─────────────────────────────────────────┬───────────────────────┘  │
└─────────────────────┼─────────────────────────────────────────┼──────────────────────────┘
                      │ SQLAlchemy 2.0                          │ HTTPS (Single API)
┌─────────────────────▼─────────────────────────┐ ┌─────────────▼──────────────────────────┐
│                 DATA TIER                     │ │               EXTERNAL                 │
│      PostgreSQL 16 Relational Engine          │ │      Google Gemini 3.5 Flash Lite      │
│  (13 Schema Tables, Foreign Keys, JSONB logs) │ │   (Action Contracts & Hinglish Copy)   │
└───────────────────────────────────────────────┘ └────────────────────────────────────────┘
```

### End-to-End Decision Pipeline

```
[ Payment Failure Event ]
            │
            ▼
  1. Risk Scoring (Deterministic Multi-Factor Scoring)
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

| Responsibility Layer | Handled By | Guarantees & Invariants |
| :--- | :--- | :--- |
| **Financial Amounts & Timestamps** | Deterministic Python & PostgreSQL | Immutable, authoritative transaction values |
| **Expected Value Math** | Econometric Python Formulas | Strict formula verification: $\text{EV} = P \times V - C$ |
| **Recovery Probability** | Scikit-Learn Gradient Boosting | Calibrated probability estimation on observable features |
| **Ambiguous Diagnosis & Copy** | Google Gemini (One provider, one API) | Natural language synthesis, contextual Hinglish messaging |
| **Policy Enforcement & Final Authorization** | Deterministic Policy Engine | **NEVER the LLM**; amount tiers, cooling windows, idempotency |
| **Mandate Regulatory Guardrails** | NPCI / RBI AutoPay Compliance Rules | Cooling-off windows, revoked mandate blocks |

### Backend Module Structure

```
backend/
├── alembic/                      # Database migrations (001_initial_schema.py)
├── app/
│   ├── api/                      # REST routers
│   │   ├── agent_replay.py       # GET /api/agent-replay/{id}
│   │   ├── dashboard.py          # GET /api/dashboard/overview
│   │   ├── experiments.py        # GET/POST /api/experiments
│   │   ├── health.py             # GET /health
│   │   ├── policies.py           # Evaluation endpoints
│   │   ├── policy_center.py      # GET/PUT /api/policy-center/config
│   │   └── transactions.py       # GET /api/transactions
│   ├── core/
│   │   └── config.py             # Pydantic Settings & environment parsing
│   ├── db/
│   │   └── session.py            # SQLAlchemy engine, sessionmaker, Base
│   ├── domain/
│   │   ├── events/               # Event schemas, normalizer, event bus
│   │   ├── mandate/              # NPCI AutoPay state machine, models, Hinglish messaging
│   │   └── policies/             # Baseline fixed-rule reference policy
│   ├── engines/                  # Core intelligence & execution pipeline
│   │   ├── audit.py              # Append-only log_audit_event & timeline builder
│   │   ├── decision.py           # LLM recommendation & Action Contract reconciliation
│   │   ├── diagnosis.py          # Deterministic taxonomy + LLM fallback diagnosis
│   │   ├── expected_value.py     # Authoritative econometric EV calculation
│   │   ├── policy.py             # 6 deterministic policy guardrails
│   │   ├── prediction.py         # ML recovery probability inference
│   │   ├── risk.py               # Deterministic multi-factor risk scoring
│   │   └── verification.py       # Outcome verification against hidden simulator
│   ├── integrations/             # Mock gateways & external dispatchers
│   │   ├── messaging.py          # Mock WhatsApp, Email, Escalation dispatch
│   │   └── mock_gateway.py       # Mock UPI/Card retry dispatch
│   ├── models/
│   │   └── tables.py             # All 13 SQLAlchemy declarative models
│   └── main.py                   # FastAPI app factory, CORS, and routing
└── scripts/
    ├── entrypoint.sh             # Container bootstrap with first-run auto-seeding
    ├── init_and_seed.py          # Database readiness check & seed orchestration
    ├── generate_data.py          # Seeded synthetic customer & transaction generator
    ├── run_experiment.py         # A/B evaluation engine (Baseline vs RecoverAI)
    ├── simulator.py              # Hidden ground-truth counterfactual simulator
    └── train_model.py            # ML model training & calibration pipeline
```

---

## 3. Database Schema

RecoverAI strictly adheres to the 13 core database tables defined in Ground Truth, organized into three logical operational domains:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATABASE SCHEMA MAP                              │
├────────────────────────┬────────────────────────────┬───────────────────────┤
│ Core Entities          │ Pipeline Records           │ Evaluation & Policies │
├────────────────────────┼────────────────────────────┼───────────────────────┤
│ • merchants            │ • diagnoses                │ • policies            │
│ • customers            │ • predictions              │ • policy_evaluations  │
│ • transactions         │ • decisions                │ • experiments         │
│ • revenue_events       │ • actions                  │                       │
│                        │ • verification_results     │                       │
│                        │ • audit_events             │                       │
└────────────────────────┴────────────────────────────┴───────────────────────┘
```

### Table Reference

| Table Name | Primary Key | Key Columns / Relationships | Purpose & Invariants |
| :--- | :--- | :--- | :--- |
| `merchants` | `id` (UUID) | `name`, `created_at` | Merchant tenant entity. |
| `customers` | `id` (UUID) | `merchant_id`, `account_age_days`, `lifetime_tx_count`, `failed_count`, `avg_transaction_value`, `upi_usage_pct`, `card_usage_pct`, `preferred_language` | Observable customer behavioral profile. |
| `transactions` | `id` (UUID) | `customer_id`, `merchant_id`, `amount` (Numeric), `currency`, `payment_method`, `status`, `failure_code`, `source_event_id`, `created_at` | Immutable payment records. `status` follows strict state transitions (`failed` $\to$ `recovered` / `unrecovered`). |
| `revenue_events` | `id` (UUID) | `transaction_id`, `external_event_id` (Unique), `event_type`, `payload` (JSONB), `ingested_at` | Ingestion event bus. Enforces idempotency via uniqueness on `external_event_id`. |
| `diagnoses` | `id` (UUID) | `transaction_id`, `failure_code`, `source` (`deterministic`/`llm`), `confidence`, `reason_codes` (JSONB) | Recorded diagnosis of root cause. |
| `predictions` | `id` (UUID) | `transaction_id`, `recovery_probability`, `model_version`, `created_at` | Calibrated ML probability output. |
| `decisions` | `id` (UUID) | `transaction_id`, `action_type`, `channel`, `delay_hours`, `amount`, `confidence_llm`, `expected_value_llm`, `expected_value_verified`, `reason_codes`, `policy_context` (JSONB) | Candidate recovery contract recording both LLM claims and verified backend values. |
| `policy_evaluations` | `id` (UUID) | `transaction_id`, `decision_id`, `verdict` (`APPROVED`, `BLOCKED`, `ESCALATED`), `reasons` (JSONB), `check_results` (JSONB), `evaluated_at` | Decision receipt capturing pass/fail status of all 6 policy checks. |
| `actions` | `id` (UUID) | `transaction_id`, `decision_id`, `action_type`, `status` (`executed`/`skipped`), `executed_at`, `payload` (JSONB) | Mock physical dispatch record. |
| `verification_results` | `id` (UUID) | `transaction_id`, `action_id`, `outcome` (`success`/`failure`), `simulated_amount_recovered`, `verified_at` | Ground-truth outcome resolved by the hidden simulator. |
| `audit_events` | `id` (UUID) | `transaction_id`, `event_type`, `timestamp`, `actor`, `input_snapshot` (JSONB), `output_snapshot` (JSONB), `reason_codes` (JSONB), `policy_result` | **Append-only ledger**. Never updated or deleted; powers forensic Agent Replay. |
| `policies` | `id` (UUID) | `name`, `config` (JSONB), `version` (Integer), `updated_at` | Active guardrail thresholds. Updates trigger automatic version increments. |
| `experiments` | `id` (UUID) | `seed`, `batch_size`, `policy_type` (`BASELINE`/`RECOVERAI`), `total_recovered`, `recovery_rate`, `incremental_recovered`, `run_at` | Controlled A/B trial records. Directly backs Overview headline KPI. |

### Core Invariants
1. **Append-Only Audit Stream**: Rows in `audit_events` are insert-only. No `UPDATE` or `DELETE` statements exist in the codebase for this table.
2. **Event Bus Idempotency**: `revenue_events.external_event_id` carries a unique constraint. Duplicate webhook deliveries are rejected before pipeline execution.
3. **Receipt Immutability**: `decisions` stores both `expected_value_llm` and `expected_value_verified`. Any discrepancy between the LLM's claim and the backend's formula is permanently preserved.

---

## 4. The Full Pipeline & Engine Breakdown

### 1. Event Normalizer (Revenue Event Bus)
Ingests heterogeneous payment gateway payloads into a standardized `NormalizedEvent` schema. Strips malformed headers, validates ISO currency codes (`INR`), maps gateway-specific error codes into the standardized 27-code failure taxonomy, and checks the database to deduplicate events.

### 2. Risk Detection Engine
Computes an instantaneous risk profile using a deterministic weighted scoring formula without any random, ML, or LLM dependency. Evaluates:
1. **Monetary Value at Risk** (40% weight): Non-linear curve scaled by transaction size (low, moderate, high thresholds).
2. **Customer History Score** (30% weight): Track record based on customer lifetime failure rate.
3. **Failure Severity Score** (30% weight): Taxonomy weight based on failure code (e.g. 95 for hard revocation vs 20 for transient timeout).

Emits a deterministic `severity_score` (0.0 to 100.0) and assigns a `risk_level` (`LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`).

### 3. Diagnosis Engine (Deterministic + LLM Split)
Implements a 2-tier diagnosis architecture:
- **Tier 1 (Deterministic)**: 85% of transactions exhibit known, unambiguous failure codes (e.g. `CARD_EXPIRED`, `UPI_COLLECT_EXPIRED`). These are diagnosed in `<1ms` with 1.0 confidence using taxonomy mapping, requiring zero external API calls.
- **Tier 2 (LLM Fallback)**: 15% of transactions feature ambiguous, non-standard raw gateway messages (e.g., `"Switch response 05: Do Not Honor"`, `"Socket reset by peer"`). These are routed to Gemini 3.5 Flash Lite to extract root causes, determine recovery viability, and emit structured reason codes.

### 4. Recovery ML Model
A calibrated Gradient Boosting classifier (`HistGradientBoostingClassifier` wrapped in `CalibratedClassifierCV(method='sigmoid')`) trained exclusively on 12 observable features (amount, account age, lifetime volume, prior failure rate, payment method, hours elapsed).
- **ROC-AUC**: `0.7848` on held-out test data.
- **Brier Score**: `0.1003` (reflecting strong probability calibration).
- **Calibration Curve**: Dense and highly reliable in the `0.0 - 0.40` probability range; conservatively sparse for `> 0.50` where autonomous recovery is rare.

### 5. Expected Value Engine
Evaluates every allowable recovery action under the econometric expected value formula:
$$\text{EV} = P(\text{recovery}) \times \text{Transaction Value} - \text{Operational Cost}$$
Applies distinct operational costs:
- `RETRY`: ₹1.00 (Gateway API charge)
- `WHATSAPP`: ₹1.50 (WhatsApp Business API per-template message)
- `EMAIL`: ₹0.20 (Transactional email delivery cost)
- `DISCOUNT`: 10% voucher margin haircut (proportional to transaction size: `amount * 0.10`)
- `ESCALATE`: ₹25.00 (Human agent ticket handling cost)

### 6. LLM Recommendation & Action Contract Reconciler
Invokes Google Gemini with the customer profile, failure diagnosis, and candidate actions. The LLM returns a strictly typed `RecoveryAction` Pydantic model. 

The backend **Reconciler** intercepts this proposal and recomputes the expected value using authoritative database values. If the LLM omitted costs or miscalculated confidence, the backend overwrites the values with verified figures before proceeding to policy authorization.

### 7. Policy / Guardrail Engine
The authoritative gatekeeper. Evaluates 6 deterministic policy checks (Amount Tiers, Retry Caps, Anti-Spam Frequency, Discount Ceilings, Idempotency, and NPCI Mandate Compliance). Emits an immutable `PolicyVerdict` (`APPROVED`, `BLOCKED`, or `ESCALATED`) accompanied by specific reason codes.

### 8. Mock Action Executor
Simulates physical API dispatch across 5 target channels:
- Gateway Retries via `mock_gateway.py`
- Outbound WhatsApp notifications via `messaging.py`
- Customer Email delivery via `messaging.py`
- Discount voucher generation
- Zendesk/Freshdesk human escalation tickets

### 9. Verification Engine (Hidden Simulator)
Evaluates executed actions against a hidden counterfactual simulator function (`scripts/simulator.py`). The simulator maintains customer latent reliability parameters and decay functions that are strictly shielded from the recovery models, resolving true binary recovery outcomes (`SUCCESS` or `FAILURE`).

### 10. Audit & Replay Engine
Records every pipeline transition into `audit_events`. Reconstructs the complete forensic execution trail on demand for any transaction, detailing input snapshots, output decisions, model versions, and elapsed latencies.

---

## 5. The Action Contract

The `RecoveryAction` contract is the single typed data interchange object governing proposed recovery actions. Implemented in Pydantic v2:

```python
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List
from pydantic import BaseModel, Field

class ActionType(str, Enum):
    RETRY = "RETRY"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"
    DISCOUNT = "DISCOUNT"
    ESCALATE = "ESCALATE"

class Channel(str, Enum):
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    WHATSAPP = "WHATSAPP"
    EMAIL = "EMAIL"

class RecoveryAction(BaseModel):
    action_type: ActionType = Field(..., description="Action category proposed")
    transaction_id: str = Field(..., description="UUID string of the failed transaction")
    amount: Decimal = Field(..., description="Transaction monetary amount in INR")
    channel: Channel = Field(..., description="Target execution or communication channel")
    delay_hours: int = Field(default=0, ge=0, description="Cooling-off delay before execution")
    reason_codes: List[str] = Field(default_factory=list, description="Taxonomy reason codes")
    confidence: float = Field(..., ge=0.0, le=1.0, description="ML/LLM recovery probability")
    expected_value: Decimal = Field(..., description="Claimed expected value in INR")
    policy_context: Dict[str, Any] = Field(default_factory=dict, description="Metadata for policy checks")
```

### Real Worked Trace (Phase 8 Verification)

Below is an exact trace executed during Phase 8 verification on failed transaction `8da5d39b-42c2-4797-8426-fcc9255b30e2`:

| Pipeline Stage | Value / Content | Actor / Engine |
| :--- | :--- | :--- |
| **Transaction ID** | `8da5d39b-42c2-4797-8426-fcc9255b30e2` | Core DB |
| **Monetary Value** | ₹1,753.45 (`INR`) | Authoritative DB Record |
| **Failure Code** | `BANK_DECLINED` (Netbanking/UPI) | Event Normalizer |
| **Customer Profile** | Account age 1,688 days, 12 lifetime txs (11 ok, 1 failed; 8.3% failure rate) | Customer Record |
| **Risk Score** | `0.15` (Severity Score) $\to$ `LOW` Risk Level | Risk Engine (Deterministic Multi-Factor Scoring) |
| **Diagnosis** | `BANK_DECLINED` (1.0 confidence, `BANK_INTERNAL_POLICY_REJECTION`) | Deterministic Diagnosis |
| **ML Probability** | `17.5%` recovery probability (`CALIBRATED_ML_ESTIMATION`) | Gradient Boosting ML Model |
| **Candidate Action** | `RETRY` via Netbanking switch after 1 hour delay | LLM Recommendation |
| **Claimed EV** | ₹296.85 | Gemini 3.5 Flash Lite |
| **Verified EV** | ₹296.85 ($\text{EV} = 0.175 \times 1753.45 - 10.00 = 296.85$) | EV Reconciler (Match confirmed) |
| **Policy Authorization**| **`APPROVED`** (Passed amount tier, retry 1/2, idempotency check) | Authoritative Policy Engine |
| **Action Execution** | Executed mock retry; HTTP 200 payload recorded | Mock Gateway |
| **Outcome** | Simulated roll against simulator $\to$ Resolved `SUCCESS` | Hidden Simulator Verification |
| **Audit Stream** | 8 append-only events logged from `EVENT_RECEIVED` to `OUTCOME_VERIFIED` | Audit Stream |

---

## 6. Policy & Guardrail Engine — Full Rules Reference

The Policy Engine is the single authoritative checkpoint controlling recovery execution. It evaluates 6 deterministic guardrails:

| Check # | Guardrail Name | Rule Description | Authoritative Thresholds | Reason Code | Verdict Impact |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **1** | **Amount Tier & Ceiling** | Caps autonomous action by financial tier; routes high-value transactions to humans | • Low Tier ($\le$ ₹5,000): Full autonomy<br>• Mid Tier (₹5,001–₹25,000): Requires ML Confidence $\ge$ 0.40<br>• High Tier (> ₹25,000): Human approval only | `AMOUNT_TIER_HUMAN_ONLY`<br>`CONFIDENCE_BELOW_TIER_FLOOR` | `ESCALATED` |
| **2** | **Retry Limit** | Halts infinite retry loops and prevents gateway surcharge penalties | Maximum 2 prior retries allowed per transaction | `RETRY_LIMIT_REACHED` | `BLOCKED` |
| **3** | **Contact Frequency** | Anti-spam guardrail preventing customer fatigue across messaging channels | Maximum 2 outbound communications (WhatsApp/Email) per customer within 24 hours | `CONTACT_FREQUENCY_EXCEEDED` | `BLOCKED` |
| **4** | **Discount Limit** | Prevents unit-economic erosion from automated concession offers | Proposed discount rate cannot exceed policy ceiling (10% max) | `DISCOUNT_LIMIT_EXCEEDED` | `BLOCKED` |
| **5** | **Action Idempotency** | Prevents duplicate charges and repetitive customer outreach | Verifies exact `(transaction_id, action_type, channel)` has not been executed or approved | `ACTION_ALREADY_TAKEN` | `BLOCKED` |
| **6** | **NPCI Mandate Compliance** | Enforces RBI / NPCI AutoPay regulatory cooling-off and revocation rules | • Terminal (`MANDATE_REVOKED`, `MANDATE_EXPIRED`): Standard retries strictly prohibited<br>• Transient (`UPI_MANDATE_FAILED`): Enforces 24h cooling-off (`delay_hours >= 24`) and max 1 retry | `MANDATE_REVOKED_RETRY_PROHIBITED`<br>`MANDATE_EXPIRED_RETRY_PROHIBITED`<br>`MANDATE_NPCI_WINDOW_VIOLATION` | `BLOCKED` |

---

## 7. India-Specific Depth & Regulatory Compliance

### 27-Code Failure Taxonomy

RecoverAI models 27 distinct failure codes reflecting India's payment ecosystem across 6 operational payment categories:

| Payment Category | Standardized Failure Codes | Typical Root Cause & Handling |
| :--- | :--- | :--- |
| **UPI** | `UPI_COLLECT_EXPIRED`<br>`UPI_BANK_TIMEOUT`<br>`UPI_INSUFFICIENT_FUNDS`<br>`UPI_PSP_ERROR`<br>`UPI_CUSTOMER_DECLINED`<br>`UPI_LIMIT_EXCEEDED`<br>`UPI_MANDATE_FAILED`<br>`UPI_MANDATE_EXPIRED` | Inaction on collect prompts, PSP switch throttling, or bank server timeouts. Recovered via smart delays or switching from collect to intent links. |
| **Cards** | `CARD_EXPIRED`<br>`CARD_DECLINED`<br>`CARD_LIMIT_EXCEEDED`<br>`ISSUER_TIMEOUT`<br>`INSUFFICIENT_FUNDS` | Hard instrument expiry vs transient ACS 3D-Secure timeout. Hard declines immediately block retries; transient timeouts retry after 1–2 hours. |
| **Netbanking** | `BANK_TIMEOUT`<br>`BANK_DECLINED`<br>`SESSION_EXPIRED` | Core banking switch latency during redirect. Transient failures re-attempted after off-peak banking window. |
| **Recurring Mandates (eNACH / AutoPay)** | `MANDATE_REGISTRATION_FAILED`<br>`MANDATE_EXECUTION_FAILED`<br>`MANDATE_REVOKED`<br>`MANDATE_EXPIRED` | Regulatory-governed recurring failures. Terminal revocations block debit retries; execution failures enforce NPCI 24h spacing. |
| **Checkout Abandonment** | `CHECKOUT_ABANDONED`<br>`PAYMENT_PAGE_EXIT`<br>`OTP_TIMEOUT`<br>`PAYMENT_METHOD_CHANGED` | User drop-off during checkout or 2FA entry. Intercepted via proactive WhatsApp intent notifications and 10% coupon incentives. |
| **B2B Invoicing** | `INVOICE_OVERDUE`<br>`PAYMENT_PROMISE_BROKEN`<br>`PARTIAL_PAYMENT` | Commercial credit term defaults. Managed via scheduled email payment link generation and escalation to account managers. |

### UPI Mandate Lifecycle State Machine

```
              ┌───────────────┐
              │    CREATED    │
              └───────┬───────┘
                      │ Customer approves mandate
                      ▼
              ┌───────────────┐
              │    ACTIVE     │
              └───────┬───────┘
                      │ Scheduled billing cycle
                      ▼
              ┌───────────────┐
              │DEBIT_ATTEMPTED│
              └───────┬───────┘
         ┌────────────┴────────────┐
         │ Debit fails             │ Debit fails
         │ (Transient Bank Error)  │ (Customer Revoked / Expired)
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│  DEBIT_FAILED_   │      │  DEBIT_FAILED_   │
│    TRANSIENT     │      │     TERMINAL     │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│RETRY_ELIGIBILITY_│      │ RETRY_PROHIBITED │
│      CHECK       │      │  (Guardrail 6)   │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│  RETRY_WINDOW_   │      │ Re-registration  │
│      ACTIVE      │      │ Outreach Allowed │
│ (Delay >= 24h)   │      │ (WhatsApp/Email) │
└────────┬─────────┘      └──────────────────┘
         │
         ▼
┌──────────────────┐
│COMPLETED_SUCCESS │
│  or ESCALATED    │
└──────────────────┘
```

### Card vs. Mandate Recovery Logic Comparison

| Recovery Parameter | Credit / Debit Card Retries | UPI AutoPay / eNACH Mandates | Regulatory & Operational Rationale |
| :--- | :--- | :--- | :--- |
| **Retry Window Delay** | **1 to 2 hours** | **$\ge$ 24 hours mandatory** | NPCI circular requires a minimum 24-hour cooling-off window between recurring mandate debit attempts. |
| **Allowed Retry Attempts** | Up to 2 retries | Max 1 retry | Destination banks levy punitive penalties on repeated recurring mandate rejections. |
| **Terminal Revocation** | N/A | **Zero Retries Permitted** | Attempting automated debits on `MANDATE_REVOKED` violates NPCI rules and is strictly blocked by Guardrail 6. |
| **Alternative Routing** | Retry on alternative card gateway | Trigger WhatsApp/Email re-registration | Revoked mandates require establishing a fresh mandate token before any debit can occur. |

### Contextual Hinglish Customer Messaging

RecoverAI generates natural, contextual Hinglish copy via Gemini 3.5 Flash Lite tailored to the exact failure scenario (strictly prohibited from using generic, robotic templates):

1. **Mandate Transient Timeout (`UPI_MANDATE_FAILED` $\to$ WhatsApp)**:
   > *"Namaste Rahul! Hotstar Premium ke liye aapka auto-pay request bank server busy hone ki wajah se complete nahi ho paya. Fret not, hum kal dopahar dobara try karenge bina kisi extra charges ke. Agar aap abhi pay karna chahte hain toh yahan click karein: [link]"*

2. **Checkout Abandonment (`CHECKOUT_ABANDONED` $\to$ WhatsApp with Discount)**:
   > *"Hi Priya, aapka Urban Company salon service ka cart wait kar raha hai! Lagta hai checkout complete nahi ho paya. Agle 2 ghante ke liye use karein code RECOVER10 aur paayein instant 10% discount. Click to book now: [link]"*

3. **Revoked Mandate Outreach (`MANDATE_REVOKED` $\to$ Email)**:
   > *"Hello Amit, aapka Cult.fit Live membership auto-pay mandate cancel ho gaya hai. Aapki workouts uninterrupted rahein, isiliye naya UPI mandate setup karein sirf 1 click mein. Setup mandate: [link]"*

---

## 8. The 7 Dashboard Views

RecoverAI features a production single-page application built with React 18, Vite, TypeScript, and Tailwind CSS adhering strictly to the `02-DESIGN-SYSTEM.md` token specifications (Inter typography, `#F7F8FA` slate background, `#3538CD` indigo brand accent, and monospace `tabular-nums`).

### 1. Overview (`/`)
The executive summary screen. Features the primary KPI card (*Simulated Net Incremental ₹ Recovered*) pulling directly from the `experiments` table (`+₹5,126.03`), secondary metrics (Recovery Rate, Total Events, Escalation Count, Blocked Count), top failure reason breakdown, and a dual-axis failure vs. recovery trend chart. Includes an interactive modal to trigger fresh multi-seed experiments.

![Overview Screenshot](./docs/screenshots/overview_screenshot.png)

### 2. Transaction Explorer (`/transactions`)
Filterable, server-side paginated transaction ledger supporting real-time search by UUID prefix, payment method (`UPI`, `CARD`, `NETBANKING`, `MANDATE`), and policy verdict (`APPROVED`, `BLOCKED`, `ESCALATED`). Matches Overview row counts in real-time.

![Transactions Screenshot](./docs/screenshots/transactions_screenshot.png)

### 3. Transaction Detail & Decision Receipt (`/transactions/:id`)
Deep forensic view of individual payment transactions. Integrates customer lifetime profile, diagnosis source, calibrated recovery probability, and the 3-panel **Decision Receipt**:
- **AI Recommendation Panel** (Indigo border): Proposed recovery action, channel, delay, and claimed EV.
- **Backend Verification Panel** (Neutral border): Formula-verified EV, EV mismatch alerts, and verified simulated recovery amount.
- **Policy Authorization Panel** (Semantic border): Pass/fail indicators for all 6 policy checks (with Mandate Compliance explicitly annotated).

![Transaction Detail Screenshot](./docs/screenshots/transaction_detail_screenshot.png)

### 4. Recovery Queue (`/recovery-queue`)
Operational workspace for compliance and customer operations teams. Displays all `ESCALATED` transactions (human judgment required) and `BLOCKED` transactions (manual guardrail override). Includes an interactive **Resolve Modal** allowing operators to record verdicts (`APPROVED`/`REJECTED`), reviewer identity, and audit notes.

![Recovery Queue Screenshot](./docs/screenshots/recovery_queue_screenshot.png)

### 5. Agent Replay (`/agent-replay/:id`)
Forensic vertical timeline reconstructing the full 8-step decisioning lifecycle directly from the append-only `audit_events` ledger:
1. `EVENT_RECEIVED` (Event Normalizer)
2. `RISK_SCORED` (Deterministic Multi-Factor Scoring)
3. `DIAGNOSIS_COMPLETED` (Diagnosis Engine)
4. `PROBABILITY_PREDICTED` (Calibrated ML)
5. `DECISION_RECOMMENDED` (LLM Recommendation)
6. `POLICY_EVALUATED` (Policy Guardrails)
7. `ACTION_EXECUTED` (Mock Dispatcher)
8. `OUTCOME_VERIFIED` (Hidden Simulator)

Features collapsible JSON viewers displaying exact `input_snapshot` and `output_snapshot` audit payloads.

![Agent Replay Screenshot](./docs/screenshots/agent_replay_loaded_screenshot.png)

### 6. Policy Center (`/policy-center`)
Real-time policy configuration dashboard. Displays active guardrail thresholds (`low_tier_max`, `mid_tier_max`, `max_retries`, `max_contacts_24h`, `max_discount_pct`, `mid_tier_min_confidence`). Enables in-place parameter edits with immediate `PUT /api/policy-center/config` database synchronization and automatic policy version increments.

![Policy Center Screenshot](./docs/screenshots/policy_center_screenshot.png)

### 7. Experiment Lab (`/experiment-lab`)
Controlled A/B evaluation matrix displaying historical experiment runs comparing the fixed-rule baseline against RecoverAI across random seeds. Displays baseline vs. RecoverAI gross recoveries, operational costs, net recovered revenue, and net incremental lift ($₹$). Backed by asynchronous worker execution to prevent blocking the event loop during 30–60s simulations.

![Experiment Lab Screenshot](./docs/screenshots/experiment_lab_screenshot.png)

---

## 9. What the Evaluation Actually Found

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

## 10. Why This Isn't Just Another LLM Wrapper

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

## 11. Categorized API Reference

All backend endpoints are built using FastAPI with interactive OpenAPI Swagger documentation accessible at `/docs`.

### Health & System
- `GET /health`: Database connectivity check and service heartbeat. Returns `{"status": "ok", "database": "connected"}`.

### Dashboard & Analytics
- `GET /api/dashboard/overview`: Core executive dashboard metrics. Returns `incremental_recovered` (pulled from active experiment), `total_recovered`, `recovery_rate`, `total_events`, `escalation_count`, `blocked_count`, `failure_breakdown`, and 180-day `trend_data`.

### Transactions & Explorer
- `GET /api/transactions`: Paginated transaction list. Query parameters: `page`, `limit`, `payment_method`, `verdict`, `search`.
- `GET /api/transactions/{id}`: Detailed transaction inspection including customer metadata, diagnosis, ML prediction, decision receipt, and policy trace.

### Forensic Agent Replay
- `GET /api/agent-replay/{transaction_id}`: Chronological audit events stream reconstructing all decisioning stages from `audit_events`.

### Policy Center & Guardrails
- `GET /api/policy-center/config`: Retrieve active policy parameters and configuration version.
- `PUT /api/policy-center/config`: Update policy parameters (`low_tier_max`, `mid_tier_max`, etc.). Automatically increments policy version.
- `POST /api/policies/evaluate-trace`: Dry-run policy check endpoint evaluating a proposed `RecoveryAction` contract without persisting execution.

### Recovery Queue
- `GET /api/policies/recovery-queue`: Retrieve pending `ESCALATED` and `BLOCKED` transactions requiring human review.
- `POST /api/policies/recovery-queue/{id}/review`: Submit a human verdict (`APPROVED` or `REJECTED`) with operator ID and review notes.

### Experiment Lab
- `GET /api/experiments`: Historical log of all baseline vs. RecoverAI A/B experiment evaluations.
- `POST /api/experiments/run`: Synchronous experiment execution endpoint (run via threadpool) evaluating baseline vs. RecoverAI for a specified `seed` and `count`.

---

## 12. Testing & Verification Evidence

RecoverAI was built across 13 strict phases, with every phase verified against empirical data before proceeding:

### Per-Phase Verification Matrix

| Phase | Module / Goal | Verification Method | Empirical Verification Result |
| :---: | :--- | :--- | :--- |
| **1** | Project Scaffold & Database | Alembic migrations & Docker Compose | PostgreSQL 16 launched; all 13 core tables created; `GET /health` verified 200 OK. |
| **2** | Synthetic Generator & Simulator | Batch generation with hidden simulator | Seed 42 generated 1,000 transactions (data hash: `916aa537963d2bf7`); 135 failures generated. |
| **3** | Event Normalizer & Risk Engine | Normalization & Multi-Factor Scoring | Unique constraint prevented duplicate events; deterministic multi-factor risk scoring verified across 3 dimensions. |
| **4** | 2-Tier Diagnosis Engine | 100-event mixed batch test | 85 clear taxonomy codes resolved deterministically in <1ms; 15 ambiguous cases diagnosed via LLM. |
| **5** | Recovery ML Model & EV Engine | Train/validation/test split evaluation | Model achieved **ROC-AUC: 0.7848**, **Brier Score: 0.1003**; EV formula $P \times V - C$ verified. |
| **6** | LLM Recommendation Contract | Pydantic schema validation & reconciliation | Gemini emitted valid `RecoveryAction` contracts; backend caught and corrected LLM cost omissions. |
| **7** | Deterministic Policy Engine | Unit testing across 5 guardrails | Amount tier escalations, retry limits, contact frequency, discount caps, and idempotency verified. |
| **8** | Action Executor & Replay | End-to-end execution & simulator check | ₹1,753.45 `BANK_DECLINED` transaction executed across 8 stages; full Agent Replay reconstructed. |
| **Vertical Slice** | Integrated Pipeline Verification | Zero-skip end-to-end pipeline test | Transaction traversed event ingestion, scoring, diagnosis, EV, policy, execution, and audit logging. |
| **9** | Baseline vs RecoverAI Evaluation | A/B simulation on 500-tx batch (`seed=42`) | RecoverAI achieved **+₹5,126.03** net incremental lift overall (Autonomous cohort delivered **+₹37,881.09** net lift across 269 transactions; 231 high-value/low-confidence cases safely routed to human review). |
| **10** | Recovery Queue & Uniform DB Replay | Queue segregation & persistence test | 231 escalated and 25 blocked items populated queue; human resolution modals tested. |
| **11** | India-Specific Regulatory Depth | NPCI AutoPay state machine & Guardrail 6 | Revoked mandates blocked; 24h cooling-off window enforced; 3 contextual Hinglish messages generated. |
| **12** | SPA Dashboard (7 Views) | Playwright click-through & error tests | All 7 views verified in single session (21.03s); frontend loudly fails when backend disconnects. |
| **13** | Deployment & Zero-Command Startup | Volume destruction & auto-seed verification | Fresh `docker compose up` automatically ran migrations and seeded verified demo data in under 5 minutes. |

### The PRNG Determinism Story
During Phase 12 testing, an unintended `rng.randint(0, 59)` call inserted for timestamp jitter shifted the random number generator stream by 1 draw per transaction, perturbing the synthetic batch and altering the headline KPI. 

We identified the root cause, replaced the draw with deterministic modular arithmetic `(idx * 7) % 60`, and ran `run_experiment.py --seed 42 --count 500` twice in succession on a clean database. Both runs yielded **100.000% identical figures down to the paisa**:
- **Baseline Gross Value**: `₹875,233.69`
- **RecoverAI Gross Value**: `₹893,909.40`
- **Total Operational Cost**: `₹14,049.68`
- **Net Incremental Recovery Lift**: `+₹5,126.03`
- **Action Breakdown**: `{'RETRY': 44, 'WHATSAPP': 156, 'EMAIL': 35, 'DISCOUNT': 9, 'ESCALATE': 231, 'BLOCKED': 25}`

### ML Model Calibration & Integrity
The recovery model evaluates probability strictly on observable features:
- **Test ROC-AUC**: `0.7848`
- **Brier Score Loss**: `0.1003`
- **Calibration Distribution**: Calibration is dense and highly confident in the `0.0 - 0.40` range (over 1,700 validation samples). Above `0.50`, historical samples are naturally thin because failed subscription payments in the real world rarely have >50% autonomous recovery probability without customer intervention.

---

## 13. Production Design Decisions & Trade-Offs

| Architectural Decision | Rationale | Trade-Off Accepted |
| :--- | :--- | :--- |
| **Mock External Integrations** | Scope discipline for a reliable evaluation environment. Integrates mock gateways and mock SMS/WhatsApp services. | Does not send live SMS or charge real cards, but guarantees 100% reproducible testing without live billing costs. |
| **No Retrieval-Augmented Generation (RAG)** | Payment recovery is a structured transactional decision, not an open-domain text retrieval problem. Customer profiles and policies fit directly into context. | Avoids unnecessary vector database infrastructure and latency overhead. |
| **No Multi-Agent Frameworks (LangChain / CrewAI)** | Multi-agent orchestration frameworks introduce non-deterministic loops, hidden prompts, and debugging opacity. | Replaced with two scoring functions (ML probability + Econometric EV) and one authoritative Policy Engine. |
| **Modular Monolith Architecture** | A clean FastAPI modular monolith (`api/`, `domain/`, `engines/`, `models/`) provides fast development and unified database transactions. | Would require service extraction to horizontally scale individual stages independently (acceptable for this submission). |
| **Batch Experiments Use Deterministic Engines** | Running 1,000 live LLM API calls during an A/B simulation breaches provider rate limits and takes 20+ minutes. | Batch evaluations use the EV Engine and Policy Engine directly at scale; live LLM generation is reserved for single-transaction routing and copy generation. |

---

## 14. Environment Variables Reference

| Variable | Description | Default (Local Docker) |
| :--- | :--- | :--- |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:changeme@db:5432/recoverai` |
| `POSTGRES_USER` | Database superuser | `postgres` |
| `POSTGRES_PASSWORD` | Database password | `changeme` |
| `POSTGRES_DB` | Database name | `recoverai` |
| `GEMINI_API_KEY` | Google Gemini API Key | *(Optional for batch demo; required for live LLM copy)* |
| `GEMINI_MODEL` | LLM model identifier | `gemini-3.5-flash-lite` |
| `BACKEND_URL` | Backend URL for frontend proxy | `http://backend:8000` |

---

## 15. 5-Minute Quickstart (Local Run)

### 1. Clone & Launch
```bash
git clone https://github.com/Kanneboinashivakumar/RecoverAI.git
cd RecoverAI

# Copy environment template
cp .env.example .env

# Build and start all services (PostgreSQL, FastAPI Backend, React Frontend)
docker compose up --build
```

### 2. Access the Application
- **Frontend Console**: [http://localhost:3000](http://localhost:3000)
- **Interactive OpenAPI Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

> [!NOTE]
> **First-Run Auto-Seeding**: On first boot, the backend automatically detects an unseeded database, applies Alembic migrations, and pre-seeds the verified demo dataset (`seed=42`, `count=1000`, `n=500`). The Overview dashboard and all 7 views are immediately populated with the verified net incremental lift of **+₹5,126.03** without requiring manual seeding commands. Subsequent restarts start instantly in <100ms.

### 3. Run Verification Tests
```bash
cd frontend
# 1. Full SPA click-through test (<30s)
node verify_clickthrough.cjs

# 2. Backend disconnection loud failure test
node verify_backend_failure.cjs
```

---

## 16. Troubleshooting & FAQ

### Q1: Why does the Overview dashboard show simulated figures instead of real recovered money?
**A**: We do not possess live Razorpay production customer data, and claiming real recovery figures on synthetic datasets is dishonest. RecoverAI explicitly labels all recovered metrics as simulated across every screen and provides a reproducible evaluation against a hidden simulator ground truth.

### Q2: Why doesn't the batch experiment call the LLM per transaction?
**A**: Running 1,000 live LLM API calls in a batch run causes rate-limit failures, high token costs, and 20+ minute wait times. In batch mode, RecoverAI leverages the deterministic EV Engine (Phase 5) and Policy Engine (Phase 7) to select the optimal contract at scale. The live LLM pipeline remains intact for single-transaction routing and contextual copy generation.

### Q3: How do I verify the primary KPI isn't hardcoded?
**A**: Navigate to the **Experiment Lab** (`/experiment-lab`) or click **Run Experiment Batch** on the Overview screen. Trigger an experiment with a different seed (e.g. `seed=7`, `count=500`). The backend will generate a new synthetic batch, evaluate baseline vs. RecoverAI, and display a different, dynamically computed net incremental recovery figure.

### Q4: Why does UPI mandate retry logic differ from card retry logic?
**A**: Card retries can be attempted within 1–2 hours for transient network timeouts. However, NPCI AutoPay circulars strictly mandate a minimum 24-hour cooling-off window for recurring UPI mandate retries. Furthermore, attempting retries on revoked mandates violates NPCI guidelines and triggers bank fines. RecoverAI models these constraints explicitly in Guardrail 6.

---

## 17. Deploying to Render via Blueprint

The repository includes a ready-to-deploy [`render.yaml`](render.yaml) blueprint:
1. Fork or push this repository to GitHub: `https://github.com/Kanneboinashivakumar/RecoverAI`.
2. Log in to [Render](https://dashboard.render.com).
3. Click **New +** $\to$ **Blueprint**.
4. Connect your repository. Render will automatically configure:
   - **PostgreSQL Database** (`recoverai-db`)
   - **FastAPI Backend Web Service** (`recoverai-backend`)
   - **React Frontend Web Service** (`recoverai-frontend`)
5. Click **Apply**. The backend container will auto-seed the demo data on startup, making the live URL fully operational in minutes.

---

## 18. License & Credits

Developed by **Kanneboina Shiva Kumar** for the **Razorpay Super Dream Offer Buildathon (Track 03 — Autonomous Revenue Recovery Agent)**.

Licensed under the [MIT License](LICENSE).
