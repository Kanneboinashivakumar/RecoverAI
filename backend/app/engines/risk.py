from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.domain.events.schema import NormalizedRevenueEvent

# Failure code severity weights (0.0 - 100.0)
FAILURE_SEVERITY_WEIGHTS: Dict[str, float] = {
    # Hard Declines & Contract/Revocation Failures (Severe)
    "CARD_EXPIRED": 95.0,
    "MANDATE_REVOKED": 95.0,
    "PAYMENT_PROMISE_BROKEN": 90.0,
    "CARD_DECLINED": 85.0,
    "BANK_DECLINED": 85.0,
    "UPI_CUSTOMER_DECLINED": 85.0,
    "CARD_LIMIT_EXCEEDED": 80.0,
    "UPI_LIMIT_EXCEEDED": 80.0,
    "INVOICE_OVERDUE": 80.0,
    # Medium Failures (Funds, Abandonment, Mandate setup)
    "UPI_INSUFFICIENT_FUNDS": 65.0,
    "INSUFFICIENT_FUNDS": 65.0,
    "CHECKOUT_ABANDONED": 60.0,
    "MANDATE_EXECUTION_FAILED": 60.0,
    "PAYMENT_PAGE_EXIT": 55.0,
    "PARTIAL_PAYMENT": 55.0,
    "MANDATE_REGISTRATION_FAILED": 55.0,
    "UPI_MANDATE_FAILED": 55.0,
    "MANDATE_EXPIRED": 50.0,
    "UPI_MANDATE_EXPIRED": 50.0,
    # Transient / Technical / Timeout Failures (Low)
    "UPI_COLLECT_EXPIRED": 30.0,
    "OTP_TIMEOUT": 30.0,
    "ISSUER_TIMEOUT": 25.0,
    "UPI_PSP_ERROR": 25.0,
    "UPI_BANK_TIMEOUT": 20.0,
    "BANK_TIMEOUT": 20.0,
    "SESSION_EXPIRED": 20.0,
    "PAYMENT_METHOD_CHANGED": 20.0,
}


class RiskScore(BaseModel):
    """Result of deterministic risk evaluation."""
    is_at_risk: bool = Field(..., description="Whether transaction is flagged at-risk")
    severity_score: float = Field(..., description="Deterministic score 0.0 to 100.0")
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    value_score: float = Field(..., description="Score component from transaction amount")
    customer_history_score: float = Field(..., description="Score component from customer history")
    failure_type_score: float = Field(..., description="Score component from failure code")
    reasons: List[str] = Field(default_factory=list, description="Rule justifications")


def _calculate_value_score(amount: Decimal) -> float:
    """Deterministic score based on monetary value (0.0 - 100.0)."""
    val = float(amount)
    if val >= 50000.0:
        return 100.0
    elif val >= 25000.0:
        return 80.0 + ((val - 25000.0) / 25000.0) * 20.0
    elif val >= 5000.0:
        return 50.0 + ((val - 5000.0) / 20000.0) * 30.0
    elif val >= 1000.0:
        return 25.0 + ((val - 1000.0) / 4000.0) * 25.0
    else:
        return max(0.0, (val / 1000.0) * 25.0)


def _calculate_customer_history_score(customer: Optional[Any]) -> float:
    """Deterministic score based on customer track record (0.0 - 100.0)."""
    if customer is None:
        return 50.0  # Neutral score for unknown customer

    lifetime_tx = getattr(customer, "lifetime_tx_count", None)
    failed_count = getattr(customer, "failed_count", None)

    # If customer is a dict
    if isinstance(customer, dict):
        lifetime_tx = customer.get("lifetime_tx_count", lifetime_tx)
        failed_count = customer.get("failed_count", failed_count)

    if lifetime_tx is not None and lifetime_tx > 0 and failed_count is not None:
        failure_rate = float(failed_count) / float(lifetime_tx)
        return min(100.0, max(0.0, failure_rate * 100.0))

    return 50.0


def _calculate_failure_score(failure_code: Optional[str]) -> float:
    """Deterministic score based on failure taxonomy code (0.0 - 100.0)."""
    if not failure_code:
        return 0.0
    return FAILURE_SEVERITY_WEIGHTS.get(failure_code.upper(), 50.0)


def score_risk(event: NormalizedRevenueEvent, customer: Optional[Any] = None) -> RiskScore:
    """
    Deterministic risk scoring engine.

    Evaluates:
      1. Value at risk (40% weight)
      2. Customer history / failure rate (30% weight)
      3. Failure type severity (30% weight)

    Returns deterministic RiskScore without any random, ML, or LLM dependency.
    """
    reasons: List[str] = []

    # Successful events are never at risk
    if event.event_type == "payment_success":
        return RiskScore(
            is_at_risk=False,
            severity_score=0.0,
            risk_level="LOW",
            value_score=0.0,
            customer_history_score=0.0,
            failure_type_score=0.0,
            reasons=["Successful payment transaction — no recovery needed"],
        )

    failure_code = event.metadata.get("failure_code") if event.metadata else None

    # Calculate components
    v_score = round(_calculate_value_score(event.amount), 2)
    c_score = round(_calculate_customer_history_score(customer), 2)
    f_score = round(_calculate_failure_score(failure_code), 2)

    # Component explanations
    if v_score >= 80.0:
        reasons.append(f"High transaction value at risk: ₹{event.amount}")
    elif v_score >= 40.0:
        reasons.append(f"Moderate transaction value: ₹{event.amount}")
    else:
        reasons.append(f"Low transaction value: ₹{event.amount}")

    if c_score >= 70.0:
        reasons.append(f"Customer has chronic failure history (score: {c_score:.1f}/100)")
    elif c_score <= 10.0:
        reasons.append(f"Customer has highly reliable transaction history (score: {c_score:.1f}/100)")

    if failure_code:
        if f_score >= 80.0:
            reasons.append(f"Hard failure code [{failure_code}] indicates deliberate or hard stop")
        elif f_score <= 35.0:
            reasons.append(f"Transient/network failure code [{failure_code}]")
        else:
            reasons.append(f"Failure code [{failure_code}] requiring intervention")

    # Weighted calculation
    severity = round(0.40 * v_score + 0.30 * c_score + 0.30 * f_score, 2)
    is_at_risk = severity >= 30.0

    if severity >= 75.0:
        risk_level = "CRITICAL"
    elif severity >= 50.0:
        risk_level = "HIGH"
    elif severity >= 30.0:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return RiskScore(
        is_at_risk=is_at_risk,
        severity_score=severity,
        risk_level=risk_level,
        value_score=v_score,
        customer_history_score=c_score,
        failure_type_score=f_score,
        reasons=reasons,
    )
