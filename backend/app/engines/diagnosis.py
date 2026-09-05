import json
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.tables import DiagnosisSource

# All 27 Ground Truth taxonomy failure codes mapped deterministically
DETERMINISTIC_TAXONOMY_DIAGNOSES: Dict[str, Dict[str, Any]] = {
    # UPI
    "UPI_COLLECT_EXPIRED": {
        "confidence": 1.0,
        "reason_codes": ["CUSTOMER_INACTION", "COLLECT_WINDOW_ELAPSED", "TRANSIENT_FAILURE"],
        "description": "UPI collect request timed out before customer approval in UPI app.",
    },
    "UPI_BANK_TIMEOUT": {
        "confidence": 1.0,
        "reason_codes": ["REMITTER_BANK_UNRESPONSIVE", "NPCI_LATENCY", "TRANSIENT_TECHNICAL_GLITCH"],
        "description": "Issuing bank or NPCI core banking switch timed out during UPI auth.",
    },
    "UPI_INSUFFICIENT_FUNDS": {
        "confidence": 1.0,
        "reason_codes": ["ACCOUNT_BALANCE_LOW", "FUNDING_SOURCE_EMPTY"],
        "description": "Customer bank account has insufficient balance to complete UPI transfer.",
    },
    "UPI_PSP_ERROR": {
        "confidence": 1.0,
        "reason_codes": ["PSP_APP_CRASH_OR_FAILURE", "THIRD_PARTY_SERVICE_DEGRADATION"],
        "description": "UPI Payment Service Provider (Google Pay/PhonePe/Paytm) returned system error.",
    },
    "UPI_CUSTOMER_DECLINED": {
        "confidence": 1.0,
        "reason_codes": ["BUYER_REJECTION", "EXPLICIT_USER_DECLINE"],
        "description": "Customer explicitly rejected UPI collect authorization or mandate prompt.",
    },
    "UPI_LIMIT_EXCEEDED": {
        "confidence": 1.0,
        "reason_codes": ["DAILY_UPI_LIMIT_BREACHED", "BANK_TRANSACTION_CEILING"],
        "description": "Per-day or per-transaction UPI velocity limit exceeded for the account.",
    },
    "UPI_MANDATE_FAILED": {
        "confidence": 1.0,
        "reason_codes": ["AUTOPAY_DEBIT_FAILED", "MANDATE_EXECUTION_REJECTED"],
        "description": "Recurring UPI AutoPay debit execution failed at destination bank.",
    },
    "UPI_MANDATE_EXPIRED": {
        "confidence": 1.0,
        "reason_codes": ["AUTOPAY_VALIDITY_ENDED", "MANDATE_END_DATE_PASSED"],
        "description": "UPI recurring autopay mandate validity period has expired.",
    },
    # Cards
    "CARD_EXPIRED": {
        "confidence": 1.0,
        "reason_codes": ["INSTRUMENT_EXPIRED", "CARD_VALIDITY_LAPSED", "HARD_STOP"],
        "description": "Card expiry date has passed. Instrument cannot process further charges.",
    },
    "CARD_DECLINED": {
        "confidence": 1.0,
        "reason_codes": ["ISSUER_DECLINED_CHARGE", "SUSPECTED_FRAUD_OR_POLICY_BLOCK"],
        "description": "Card issuing bank declined the transaction without specific funds error.",
    },
    "CARD_LIMIT_EXCEEDED": {
        "confidence": 1.0,
        "reason_codes": ["CREDIT_LIMIT_EXCEEDED", "ATM_POS_ONLINE_CEILING_BREACH"],
        "description": "Credit or debit limit on card breached for billing cycle or daily cap.",
    },
    "ISSUER_TIMEOUT": {
        "confidence": 1.0,
        "reason_codes": ["CARD_NETWORK_TIMEOUT", "ISSUER_ACS_UNRESPONSIVE", "TRANSIENT_TECHNICAL_GLITCH"],
        "description": "Card issuer ACS (Access Control Server) did not respond in time.",
    },
    "INSUFFICIENT_FUNDS": {
        "confidence": 1.0,
        "reason_codes": ["ACCOUNT_BALANCE_LOW", "OVERDRAFT_UNAVAILABLE"],
        "description": "Card account has insufficient funds or available credit line.",
    },
    # Netbanking
    "BANK_TIMEOUT": {
        "confidence": 1.0,
        "reason_codes": ["NETBANKING_GATEWAY_TIMEOUT", "CORE_BANKING_SWITCH_DOWN"],
        "description": "Netbanking portal or core banking host timed out during checkout.",
    },
    "BANK_DECLINED": {
        "confidence": 1.0,
        "reason_codes": ["BANK_INTERNAL_POLICY_REJECTION", "ACCOUNT_RESTRICTED"],
        "description": "Bank rejected netbanking debit attempt.",
    },
    "SESSION_EXPIRED": {
        "confidence": 1.0,
        "reason_codes": ["USER_SESSION_TIMEOUT", "IDLE_PAGE_ABANDONMENT"],
        "description": "Netbanking login or OTP verification session timed out before completion.",
    },
    # Mandate
    "MANDATE_REGISTRATION_FAILED": {
        "confidence": 1.0,
        "reason_codes": ["ENACH_SETUP_FAILED", "RECURRING_AUTH_REJECTED"],
        "description": "Customer failed to authenticate or complete recurring mandate registration.",
    },
    "MANDATE_EXECUTION_FAILED": {
        "confidence": 1.0,
        "reason_codes": ["RECURRING_DEBIT_FAILED", "NACH_CLEARING_REJECTED"],
        "description": "Scheduled automated mandate debit execution rejected by destination bank.",
    },
    "MANDATE_REVOKED": {
        "confidence": 1.0,
        "reason_codes": ["CUSTOMER_CANCELLED_MANDATE", "HARD_STOP_REVOCATION"],
        "description": "Mandate was explicitly revoked or cancelled by customer via bank or app.",
    },
    "MANDATE_EXPIRED": {
        "confidence": 1.0,
        "reason_codes": ["MANDATE_END_DATE_PASSED", "TERM_COMPLETED"],
        "description": "Standing mandate end date has arrived; no further debits permitted.",
    },
    # Checkout
    "CHECKOUT_ABANDONED": {
        "confidence": 1.0,
        "reason_codes": ["USER_DROPOFF", "WINDOW_CLOSED_BEFORE_PAYMENT"],
        "description": "Customer loaded checkout page but left without initiating payment.",
    },
    "PAYMENT_PAGE_EXIT": {
        "confidence": 1.0,
        "reason_codes": ["NAVIGATION_AWAY", "BROWSER_TAB_CLOSED"],
        "description": "Customer closed or navigated away from the hosted payment page.",
    },
    "OTP_TIMEOUT": {
        "confidence": 1.0,
        "reason_codes": ["TWO_FACTOR_EXPIRED", "OTP_NOT_SUBMITTED_IN_TIME"],
        "description": "3D Secure / OTP entry window elapsed before customer submitted code.",
    },
    "PAYMENT_METHOD_CHANGED": {
        "confidence": 1.0,
        "reason_codes": ["SWITCHED_INSTRUMENT", "INCOMPLETE_PRIOR_ATTEMPT"],
        "description": "Customer abandoned this attempt to switch to another payment method.",
    },
    # B2B
    "INVOICE_OVERDUE": {
        "confidence": 1.0,
        "reason_codes": ["CREDIT_PERIOD_ELAPSED", "NET_TERMS_EXCEEDED"],
        "description": "B2B commercial invoice unpaid past agreed net payment terms.",
    },
    "PAYMENT_PROMISE_BROKEN": {
        "confidence": 1.0,
        "reason_codes": ["PROMISED_DATE_PASSED", "UNMET_COMMITMENT"],
        "description": "Customer agreed payment commitment date passed without settlement.",
    },
    "PARTIAL_PAYMENT": {
        "confidence": 1.0,
        "reason_codes": ["UNDERPAID_INVOICE", "OUTSTANDING_BALANCE_REMAINS"],
        "description": "Partial installment received but remaining invoice balance is unpaid.",
    },
}


class DiagnosisResult(BaseModel):
    """Result of failure diagnosis."""
    failure_code: str = Field(..., description="Standardized failure code or taxonomy category")
    source: DiagnosisSource = Field(..., description="deterministic or llm")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reason_codes: List[str] = Field(..., description="Structured uppercase reason codes")
    description: str = Field(..., description="Human-readable diagnosis explanation")
    is_ambiguous: bool = Field(..., description="True if input required LLM disambiguation")


def _call_gemini_for_diagnosis(
    error_text: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calls Google Gemini API (AI Studio) directly with JSON mode and backoff retry."""
    import time

    api_key = settings.gemini_api_key
    model = settings.gemini_model or "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    context_str = json.dumps(context or {}, default=str)
    system_prompt = (
        "You are RecoverAI's Payment Diagnosis Engine. Your task is to analyze unstructured, "
        "ambiguous, or generic payment gateway error messages and diagnose the root cause.\n"
        "Map the error to the closest standardized failure category (or one of the RecoverAI taxonomy codes "
        "such as CARD_DECLINED, BANK_TIMEOUT, UPI_PSP_ERROR, INSUFFICIENT_FUNDS, ISSUER_TIMEOUT, etc. if applicable).\n"
        "Provide a confidence score (float between 0.0 and 1.0) and a list of uppercase structured REASON_CODES.\n\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "failure_code": "STRING_UPPERCASE",\n'
        '  "confidence": 0.85,\n'
        '  "reason_codes": ["REASON_CODE_1", "REASON_CODE_2"],\n'
        '  "description": "Detailed root cause explanation"\n'
        "}"
    )

    user_prompt = f"Raw Gateway Error: {error_text}\nContext: {context_str}"

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }

    headers = {"Content-Type": "application/json"}
    max_retries = 4
    with httpx.Client(timeout=45.0) as client:
        for attempt in range(max_retries):
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 429 and attempt < max_retries - 1:
                # Quota backoff wait
                time.sleep(12.0)
                continue
            if response.status_code != 200:
                raise RuntimeError(f"Gemini API returned status {response.status_code}: {response.text}")
            data = response.json()
            break

    try:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)
    except (KeyError, IndexError, json.JSONDecodeError) as err:
        raise RuntimeError(f"Failed to parse Gemini API response: {data}") from err


def diagnose_failure(
    failure_code_or_text: str,
    context: Optional[Dict[str, Any]] = None,
    allow_mock: bool = False,
) -> DiagnosisResult:
    """
    Diagnoses a payment failure:
    1. If failure_code_or_text is in the 27 taxonomy codes -> Deterministic path (zero LLM calls).
    2. If genuinely ambiguous -> LLM path returning structured reason codes and confidence.
    """
    clean_code = str(failure_code_or_text).strip().upper()

    # Deterministic lookup path for all 27 defined taxonomy codes
    if clean_code in DETERMINISTIC_TAXONOMY_DIAGNOSES:
        info = DETERMINISTIC_TAXONOMY_DIAGNOSES[clean_code]
        return DiagnosisResult(
            failure_code=clean_code,
            source=DiagnosisSource.DETERMINISTIC,
            confidence=info["confidence"],
            reason_codes=info["reason_codes"],
            description=info["description"],
            is_ambiguous=False,
        )

    # Ambiguous path: Raw/unstructured error text
    if not settings.gemini_api_key:
        if allow_mock:
            # Explicit opt-in mock mode
            return DiagnosisResult(
                failure_code="UNRESOLVED_GATEWAY_ERROR",
                source=DiagnosisSource.LLM,
                confidence=0.75,
                reason_codes=["MOCK_LLM_DIAGNOSED", "UNSTRUCTURED_GATEWAY_RESPONSE"],
                description=f"Mock LLM diagnosis for ambiguous error: {failure_code_or_text}",
                is_ambiguous=True,
            )
        raise RuntimeError(
            "GEMINI_API_KEY is not configured in environment / .env. "
            "Genuinely ambiguous failure errors require an LLM call per Ground Truth. "
            "Please set GEMINI_API_KEY to proceed."
        )

    # Real LLM call via Gemini API
    llm_output = _call_gemini_for_diagnosis(failure_code_or_text, context=context)
    failure_code = str(llm_output.get("failure_code") or "AMBIGUOUS_GATEWAY_ERROR").upper()
    confidence = float(llm_output.get("confidence") or 0.70)
    confidence = max(0.0, min(1.0, confidence))
    reason_codes = list(llm_output.get("reason_codes") or ["LLM_INFERRED_ERROR"])
    description = str(llm_output.get("description") or f"LLM diagnosed failure: {failure_code_or_text}")

    return DiagnosisResult(
        failure_code=failure_code,
        source=DiagnosisSource.LLM,
        confidence=confidence,
        reason_codes=reason_codes,
        description=description,
        is_ambiguous=True,
    )
