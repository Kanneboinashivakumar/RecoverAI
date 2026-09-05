"""
Domain models and schema definitions for UPI Mandate lifecycle and NPCI AutoPay compliance.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MandateState(str, Enum):
    """
    Formal NPCI AutoPay mandate lifecycle states.
    Created -> Active -> Debit Attempt -> Success/Failure -> Retry Eligibility -> Retry Window -> Success/Escalation.
    """
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    DEBIT_ATTEMPTED = "DEBIT_ATTEMPTED"
    DEBIT_FAILED_TRANSIENT = "DEBIT_FAILED_TRANSIENT"
    DEBIT_FAILED_TERMINAL = "DEBIT_FAILED_TERMINAL"
    RETRY_ELIGIBILITY_CHECK = "RETRY_ELIGIBILITY_CHECK"
    RETRY_WINDOW_ACTIVE = "RETRY_WINDOW_ACTIVE"
    RETRY_PROHIBITED = "RETRY_PROHIBITED"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    ESCALATED = "ESCALATED"


class MandateFailureCategory(str, Enum):
    """Classification of failure reasons under NPCI mandate rules."""
    TRANSIENT_EXECUTION_FAILURE = "TRANSIENT_EXECUTION_FAILURE"
    TERMINAL_REVOCATION = "TERMINAL_REVOCATION"
    TERMINAL_EXPIRY = "TERMINAL_EXPIRY"
    REGISTRATION_FAILURE = "REGISTRATION_FAILURE"
    NON_MANDATE = "NON_MANDATE"


class MandateEligibilityResult(BaseModel):
    """
    Deterministic result of mandate retry eligibility evaluation.
    Governed by NPCI AutoPay circulars on recurring debit spacing and revocation rules.
    """
    is_retry_eligible: bool = Field(..., description="Whether automated RETRY action is legally permitted")
    mandate_state: MandateState = Field(..., description="Current state in the mandate state machine")
    failure_category: MandateFailureCategory = Field(..., description="Failure classification")
    min_retry_delay_hours: int = Field(default=0, description="Minimum cooling-off delay required before re-debit attempt")
    allowed_actions: List[str] = Field(default_factory=list, description="List of valid action types under this state")
    prohibited_actions: List[str] = Field(default_factory=list, description="List of prohibited action types")
    reason: str = Field(..., description="Detailed regulatory or business rationale")
    npci_rule_reference: str = Field(..., description="NPCI / RBI AutoPay rule reference")


class PaymentMethodRecoveryPath(BaseModel):
    """
    Proof of visibly distinct logic paths between Card and UPI Mandate retries.
    """
    payment_method: str
    failure_code: str
    allows_immediate_retry: bool
    recommended_retry_delay_hours: int
    requires_re_registration: bool
    allowed_actions: List[str]
    prohibited_actions: List[str]
    governing_framework: str
    explanation: str


class MandateLifecycleEvent(BaseModel):
    """A single transition entry in the mandate lifecycle trace."""
    step: int
    from_state: MandateState
    to_state: MandateState
    event_name: str
    timestamp: str
    actor: str
    details: Dict[str, Any] = Field(default_factory=dict)
