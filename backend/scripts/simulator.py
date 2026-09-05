"""
Simulator module containing the hidden ground-truth outcome function.

========================================================================
  WARNING: This module must NOT be imported by any code in app/engines/.
  It is the hidden ground truth used exclusively by the synthetic data
  generator and (in later phases) the evaluation engine.
========================================================================

The hidden outcome function resolves what ACTUALLY happens when a recovery
action is taken. Neither RecoverAI nor the baseline policy can see this
function — both only see observable features. The simulator alone resolves
the actual outcome. This separation is required for the A/B comparison to
have a defensible ground truth (see Ground Truth rule #5).
"""

# --- Hidden ground-truth recoverability by failure code ---

_FAILURE_RECOVERABILITY = {
    # UPI failures
    "UPI_COLLECT_EXPIRED": 0.55,
    "UPI_BANK_TIMEOUT": 0.60,
    "UPI_INSUFFICIENT_FUNDS": 0.35,
    "UPI_PSP_ERROR": 0.50,
    "UPI_CUSTOMER_DECLINED": 0.15,
    "UPI_LIMIT_EXCEEDED": 0.30,
    "UPI_MANDATE_FAILED": 0.25,
    "UPI_MANDATE_EXPIRED": 0.20,
    # Card failures
    "CARD_EXPIRED": 0.10,
    "CARD_DECLINED": 0.20,
    "CARD_LIMIT_EXCEEDED": 0.35,
    "ISSUER_TIMEOUT": 0.55,
    "INSUFFICIENT_FUNDS": 0.30,
    # Netbanking failures
    "BANK_TIMEOUT": 0.60,
    "BANK_DECLINED": 0.15,
    "SESSION_EXPIRED": 0.65,
    # Mandate failures
    "MANDATE_REGISTRATION_FAILED": 0.30,
    "MANDATE_EXECUTION_FAILED": 0.35,
    "MANDATE_REVOKED": 0.05,
    "MANDATE_EXPIRED": 0.15,
    # Checkout failures
    "CHECKOUT_ABANDONED": 0.45,
    "PAYMENT_PAGE_EXIT": 0.40,
    "OTP_TIMEOUT": 0.55,
    "PAYMENT_METHOD_CHANGED": 0.50,
    # B2B failures
    "INVOICE_OVERDUE": 0.60,
    "PAYMENT_PROMISE_BROKEN": 0.35,
    "PARTIAL_PAYMENT": 0.50,
}

# --- Action effectiveness by (action_type, failure_category) ---

_ACTION_EFFECTIVENESS = {
    ("RETRY", "timeout"): 1.4,
    ("RETRY", "expired"): 0.3,
    ("RETRY", "declined"): 0.5,
    ("RETRY", "insufficient"): 0.7,
    ("RETRY", "abandoned"): 0.6,
    ("RETRY", "mandate"): 0.4,
    ("RETRY", "b2b"): 0.5,
    ("WHATSAPP", "timeout"): 0.8,
    ("WHATSAPP", "expired"): 0.4,
    ("WHATSAPP", "declined"): 0.6,
    ("WHATSAPP", "insufficient"): 0.9,
    ("WHATSAPP", "abandoned"): 1.5,
    ("WHATSAPP", "mandate"): 0.5,
    ("WHATSAPP", "b2b"): 0.7,
    ("EMAIL", "timeout"): 0.6,
    ("EMAIL", "expired"): 0.3,
    ("EMAIL", "declined"): 0.4,
    ("EMAIL", "insufficient"): 0.7,
    ("EMAIL", "abandoned"): 1.2,
    ("EMAIL", "mandate"): 0.4,
    ("EMAIL", "b2b"): 0.8,
    ("DISCOUNT", "timeout"): 0.5,
    ("DISCOUNT", "expired"): 0.2,
    ("DISCOUNT", "declined"): 0.6,
    ("DISCOUNT", "insufficient"): 1.3,
    ("DISCOUNT", "abandoned"): 1.4,
    ("DISCOUNT", "mandate"): 0.3,
    ("DISCOUNT", "b2b"): 0.9,
    ("ESCALATE", "timeout"): 0.4,
    ("ESCALATE", "expired"): 0.2,
    ("ESCALATE", "declined"): 0.3,
    ("ESCALATE", "insufficient"): 0.5,
    ("ESCALATE", "abandoned"): 0.3,
    ("ESCALATE", "mandate"): 0.6,
    ("ESCALATE", "b2b"): 1.0,
}


def _categorize_failure(failure_code: str) -> str:
    """Map a specific failure code to a broad category for action lookup."""
    code = failure_code.upper()
    if "TIMEOUT" in code or "PSP_ERROR" in code:
        return "timeout"
    if "EXPIRED" in code:
        return "expired"
    if "DECLINED" in code or "LIMIT" in code:
        return "declined"
    if "INSUFFICIENT" in code:
        return "insufficient"
    if any(kw in code for kw in ("ABANDONED", "EXIT", "OTP", "CHANGED")):
        return "abandoned"
    if "MANDATE" in code:
        return "mandate"
    if any(kw in code for kw in ("INVOICE", "PROMISE", "PARTIAL")):
        return "b2b"
    return "timeout"  # default fallback


def hidden_outcome_function(
    customer_reliability: float,
    failure_code: str,
    payment_method: str,
    hours_since_failure: float,
    action_type: str,
) -> float:
    """
    The HIDDEN ground-truth outcome function.

    Returns the probability (0.0-1.0) that a recovery action succeeds
    for a given transaction context.

    Parameters:
        customer_reliability: 0.0-1.0 reliability score of the customer
        failure_code: exact failure code from the taxonomy
        payment_method: UPI / CARD / NETBANKING / MANDATE
        hours_since_failure: hours elapsed since the original failure
        action_type: RETRY / WHATSAPP / EMAIL / DISCOUNT / ESCALATE

    This function must NEVER be called by any code in app/engines/.
    """
    # Base recoverability from failure type
    base = _FAILURE_RECOVERABILITY.get(failure_code, 0.25)

    # Action effectiveness multiplier
    category = _categorize_failure(failure_code)
    action_mult = _ACTION_EFFECTIVENESS.get((action_type, category), 0.5)

    # Customer reliability boost (reliable customers recover more often)
    reliability_factor = 0.5 + 0.5 * customer_reliability

    # Time decay — recovery probability decreases over ~1 week, floor at 10%
    time_decay = max(0.10, 1.0 - (hours_since_failure / 168.0))

    probability = base * action_mult * reliability_factor * time_decay
    return min(max(probability, 0.0), 1.0)
