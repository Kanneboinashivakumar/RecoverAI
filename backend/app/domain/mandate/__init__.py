"""
RecoverAI UPI Mandate Domain Module.
Implements NPCI AutoPay lifecycle modeling and contextual Hinglish messaging.
"""

from app.domain.mandate.models import (
    MandateState,
    MandateFailureCategory,
    MandateEligibilityResult,
    MandateLifecycleEvent,
)
from app.domain.mandate.state_machine import (
    evaluate_mandate_eligibility,
    evaluate_payment_method_recovery_path,
    transition_mandate_state,
)
from app.domain.mandate.lifecycle import trace_mandate_lifecycle
from app.domain.mandate.messaging import generate_contextual_hinglish_message

__all__ = [
    "MandateState",
    "MandateFailureCategory",
    "MandateEligibilityResult",
    "MandateLifecycleEvent",
    "evaluate_mandate_eligibility",
    "evaluate_payment_method_recovery_path",
    "transition_mandate_state",
    "trace_mandate_lifecycle",
    "generate_contextual_hinglish_message",
]
