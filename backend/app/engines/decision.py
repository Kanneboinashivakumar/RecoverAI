import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.mandate.messaging import generate_contextual_hinglish_message
from app.domain.mandate.state_machine import evaluate_mandate_eligibility, is_mandate_transaction
from app.engines.expected_value import calculate_expected_value
from app.models.tables import Decision

logger = logging.getLogger("recoverai.decision")


# ---- Enums & Action Contract (Ground Truth specification) ----


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
    """
    Action Contract — exact shape from 01-GROUND-TRUTH.md.
    Every intervention proposed by the LLM must conform to this schema.
    """
    model_config = ConfigDict(use_enum_values=False)

    action_type: ActionType = Field(..., description="Enum: RETRY, WHATSAPP, EMAIL, DISCOUNT, ESCALATE")
    transaction_id: str = Field(..., description="Associated transaction UUID string")
    amount: Decimal = Field(..., description="Transaction amount")
    channel: Channel = Field(..., description="Enum: UPI, CARD, NETBANKING, WHATSAPP, EMAIL")
    delay_hours: int = Field(..., ge=0, description="Delay in hours before execution (must be >= 0)")
    reason_codes: List[str] = Field(..., description="List of uppercase machine-readable reason codes")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score claimed (0.0 to 1.0)")
    expected_value: Decimal = Field(..., description="Expected net recovery value claimed")
    policy_context: Dict[str, Any] = Field(default_factory=dict, description="Contextual parameters for policy evaluation")


class VerifiedDecision(BaseModel):
    """
    Result of LLM proposal generation followed by authoritative backend reconciliation.
    """
    action_contract: RecoveryAction
    raw_llm_claims: Dict[str, Any]
    reconciled: bool
    reconciliation_log: List[str]
    decision_id: Optional[UUID] = None


# ---- LLM Call Helpers ----


def _call_gemini_recommendation(
    prompt_messages: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Invokes Google Gemini API with JSON mode for structured recommendation."""
    api_key = settings.gemini_api_key
    model = settings.gemini_model or "gemini-3.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    contents = []
    for msg in prompt_messages:
        contents.append({"parts": [{"text": f"[{msg['role'].upper()}]: {msg['content']}"}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }
    headers = {"Content-Type": "application/json"}

    with httpx.Client(timeout=35.0) as client:
        response = client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"Gemini API returned status {response.status_code}: {response.text}")
        data = response.json()

    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw_text)


def _build_system_prompt() -> str:
    return (
        "You are RecoverAI's Intervention Recommendation Engine.\n"
        "Your task is to analyze payment failure diagnosis, ML recovery probability, "
        "and expected value calculations to propose an intervention as a schema-valid Action Contract.\n\n"
        "Strict Requirements:\n"
        "1. action_type must be ONE OF: RETRY, WHATSAPP, EMAIL, DISCOUNT, ESCALATE.\n"
        "2. channel must be ONE OF: UPI, CARD, NETBANKING, WHATSAPP, EMAIL.\n"
        "3. delay_hours must be an integer >= 0 (e.g. 0 for immediate action, 2 for retry on network timeout).\n"
        "4. reason_codes must be a list of uppercase reason strings.\n"
        "5. Output MUST be a valid JSON object matching the RecoveryAction schema exactly:\n"
        "{\n"
        '  "action_type": "RETRY",\n'
        '  "transaction_id": "...",\n'
        '  "amount": 1000.00,\n'
        '  "channel": "UPI",\n'
        '  "delay_hours": 1,\n'
        '  "reason_codes": ["TIMEOUT_RECOVERY", "POSITIVE_EV"],\n'
        '  "confidence": 0.65,\n'
        '  "expected_value": 649.00,\n'
        '  "policy_context": {}\n'
        "}\n\n"
        "6. UPI Mandate / AutoPay Specific Rules (NPCI Compliance):\n"
        "   - If mandate is revoked (MANDATE_REVOKED) or expired (MANDATE_EXPIRED), standard RETRY is legally prohibited.\n"
        "     You MUST propose WHATSAPP, EMAIL, or ESCALATE to request fresh mandate re-registration.\n"
        "   - For transient mandate failures, NPCI requires a cooling-off window with delay_hours >= 24.\n"
    )


# ---- Main Recommendation Engine ----


def recommend_recovery_action(
    transaction: Dict[str, Any],
    customer: Dict[str, Any],
    diagnosis: Any,
    recovery_probability: float,
    authoritative_amount: Decimal,
    db: Optional[Session] = None,
    allow_mock: bool = False,
) -> VerifiedDecision:
    """
    Generates an intervention proposal:
    1. Prompts the LLM with diagnosis, ML probability, and EV context.
    2. Validates output against RecoveryAction schema.
       - If validation fails, re-prompts once with validation error details.
       - If re-prompt also fails, falls back to safe ESCALATE action.
    3. Authoritative Reconciliation:
       - Overwrites claimed amount with authoritative DB amount.
       - Overwrites claimed expected_value with authoritative EV from EV Engine.
       - Logs any divergence.
    4. Persists the decision to the decisions table.
    """
    tx_id_str = str(transaction.get("id"))
    failure_code = getattr(diagnosis, "failure_code", transaction.get("failure_code", "UNKNOWN"))
    diagnosis_reasons = getattr(diagnosis, "reason_codes", [])

    user_context = {
        "transaction_id": tx_id_str,
        "amount": float(authoritative_amount),
        "payment_method": transaction.get("payment_method"),
        "failure_code": failure_code,
        "diagnosis_reason_codes": diagnosis_reasons,
        "customer": {
            "lifetime_tx_count": customer.get("lifetime_tx_count"),
            "failed_count": customer.get("failed_count"),
            "preferred_channel": customer.get("preferred_channel"),
        },
        "ml_recovery_probability": round(recovery_probability, 4),
    }

    preferred_lang = str(customer.get("preferred_language", "en")).lower()
    pm_str = str(transaction.get("payment_method", ""))
    mandate_mode = is_mandate_transaction(pm_str, failure_code)
    m_eligibility = None

    if mandate_mode:
        m_eligibility = evaluate_mandate_eligibility(
            payment_method=pm_str,
            failure_code=failure_code,
        )
        user_context["mandate_regulatory_rules"] = {
            "is_mandate": True,
            "mandate_state": m_eligibility.mandate_state.value,
            "is_retry_eligible": m_eligibility.is_retry_eligible,
            "min_retry_delay_hours": m_eligibility.min_retry_delay_hours,
            "allowed_actions": m_eligibility.allowed_actions,
            "prohibited_actions": m_eligibility.prohibited_actions,
            "guideline": m_eligibility.reason,
        }

    raw_proposal_dict: Optional[Dict[str, Any]] = None
    validated_contract: Optional[RecoveryAction] = None

    if allow_mock or not settings.gemini_api_key:
        # Mock mode for testing without LLM
        if mandate_mode and m_eligibility and not m_eligibility.is_retry_eligible:
            mock_action = "WHATSAPP" if "WHATSAPP" in m_eligibility.allowed_actions else "EMAIL"
            mock_channel = "WHATSAPP" if mock_action == "WHATSAPP" else "EMAIL"
            mock_delay = 0
            mock_reasons = ["MANDATE_RE_REGISTRATION_REQUIRED", "RETRY_LEGALLY_PROHIBITED"]
        elif mandate_mode and m_eligibility and m_eligibility.is_retry_eligible:
            mock_action = "RETRY"
            mock_channel = "UPI"
            mock_delay = m_eligibility.min_retry_delay_hours
            mock_reasons = ["MANDATE_TRANSIENT_FAILURE", "NPCI_WINDOW_COMPLIANT"]
        else:
            mock_action = "RETRY" if "TIMEOUT" in failure_code else "WHATSAPP"
            mock_channel = "UPI" if transaction.get("payment_method") == "UPI" else "WHATSAPP"
            mock_delay = 1
            mock_reasons = ["DIAGNOSED_TRANSIENT_FAILURE", "FAVORABLE_PROBABILITY"]

        raw_proposal_dict = {
            "action_type": mock_action,
            "transaction_id": tx_id_str,
            "amount": float(authoritative_amount),
            "channel": mock_channel,
            "delay_hours": mock_delay,
            "reason_codes": mock_reasons,
            "confidence": round(recovery_probability, 2),
            "expected_value": float(authoritative_amount * Decimal(str(round(recovery_probability, 2)))),
            "policy_context": {},
        }
        validated_contract = RecoveryAction.model_validate(raw_proposal_dict)
    else:
        # Step 1 & 2: Call LLM with re-prompt logic
        prompt_messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": f"Transaction Context for Recovery Proposal:\n{json.dumps(user_context, indent=2)}"},
        ]

        try:
            raw_proposal_dict = _call_gemini_recommendation(prompt_messages)
            validated_contract = RecoveryAction.model_validate(raw_proposal_dict)
        except (ValidationError, Exception) as first_err:
            logger.warning("LLM proposal validation failed on attempt 1: %s. Re-prompting once...", first_err)
            # Re-prompt once with error context
            retry_messages = list(prompt_messages)
            retry_messages.append({"role": "assistant", "content": json.dumps(raw_proposal_dict or {})})
            retry_messages.append({
                "role": "user",
                "content": f"Your proposal was INVALID: {first_err}. Please correct the schema errors and return ONLY a valid RecoveryAction JSON object.",
            })

            try:
                raw_proposal_dict = _call_gemini_recommendation(retry_messages)
                validated_contract = RecoveryAction.model_validate(raw_proposal_dict)
            except Exception as second_err:
                logger.error("LLM proposal validation failed on attempt 2: %s. Falling back to safe ESCALATE.", second_err)
                # Safe Fallback: ESCALATE to human review
                raw_proposal_dict = raw_proposal_dict or {}
                validated_contract = RecoveryAction(
                    action_type=ActionType.ESCALATE,
                    transaction_id=tx_id_str,
                    amount=authoritative_amount,
                    channel=Channel.EMAIL,
                    delay_hours=0,
                    reason_codes=["SCHEMA_VALIDATION_FAILED", "SAFE_FALLBACK_ESCALATE"],
                    confidence=0.0,
                    expected_value=Decimal("0.00"),
                    policy_context={"fallback_reason": str(second_err)},
                )

    # Step 3: Authoritative Backend Reconciliation
    reconciled = False
    reconciliation_log = []

    # Store raw LLM claims for auditing
    raw_claims = {
        "amount_claimed": Decimal(str(raw_proposal_dict.get("amount", authoritative_amount))),
        "confidence_claimed": float(raw_proposal_dict.get("confidence", recovery_probability)),
        "expected_value_claimed": Decimal(str(raw_proposal_dict.get("expected_value", Decimal("0.00")))),
    }

    # Verify amount against DB authoritative amount
    if validated_contract.amount != authoritative_amount:
        reconciled = True
        reconciliation_log.append(
            f"Overrode LLM amount ₹{validated_contract.amount} with DB authoritative amount ₹{authoritative_amount}"
        )
        validated_contract.amount = authoritative_amount

    # Compute authoritative EV using the EV Engine
    auth_ev_result = calculate_expected_value(
        amount=authoritative_amount,
        recovery_probability=recovery_probability,
        action_type=validated_contract.action_type.value,
    )
    authoritative_ev = auth_ev_result.expected_value

    # Verify expected_value against authoritative EV Engine
    if validated_contract.expected_value != authoritative_ev:
        reconciled = True
        reconciliation_log.append(
            f"Overrode LLM expected_value ₹{validated_contract.expected_value} with authoritative EV ₹{authoritative_ev} "
            f"(prob={recovery_probability:.2%}, cost=₹{auth_ev_result.action_cost})"
        )
        validated_contract.expected_value = authoritative_ev

    # Verify confidence against ML recovery probability
    if round(validated_contract.confidence, 4) != round(recovery_probability, 4):
        reconciled = True
        reconciliation_log.append(
            f"Reconciled LLM confidence {validated_contract.confidence:.2f} to authoritative ML probability {recovery_probability:.4f}"
        )
        validated_contract.confidence = round(recovery_probability, 4)

    # Ensure failure_code and payment_method are attached for policy engine evaluation
    validated_contract.policy_context["failure_code"] = failure_code
    validated_contract.policy_context["payment_method"] = pm_str

    # Phase 11: Contextual Hinglish messaging (fails loudly per Ground Truth if LLM unavailable)
    if preferred_lang in ("hi", "hinglish"):
        hinglish_msg = generate_contextual_hinglish_message(
            failure_code=failure_code,
            action_type=validated_contract.action_type.value,
            amount=authoritative_amount,
            channel=validated_contract.channel.value,
            merchant_name="RecoverAI Merchant",
            customer_context=customer,
            allow_mock=allow_mock,
        )
        validated_contract.policy_context["customer_message"] = hinglish_msg
        validated_contract.policy_context["customer_message_language"] = "hinglish"

    # Step 4: Persist to decisions table
    decision_id = uuid.uuid4()
    if db is not None:
        db_decision = Decision(
            id=decision_id,
            transaction_id=UUID(tx_id_str),
            action_type=validated_contract.action_type.value,
            channel=validated_contract.channel.value,
            delay_hours=validated_contract.delay_hours,
            amount=authoritative_amount,
            confidence_llm=raw_claims["confidence_claimed"],
            expected_value_llm=raw_claims["expected_value_claimed"],
            expected_value_verified=authoritative_ev,
            reason_codes=validated_contract.reason_codes,
            policy_context={
                "reconciled": reconciled,
                "reconciliation_log": reconciliation_log,
                "ml_probability": recovery_probability,
                "action_cost": float(auth_ev_result.action_cost),
                **validated_contract.policy_context,
            },
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(db_decision)
        db.commit()

    return VerifiedDecision(
        action_contract=validated_contract,
        raw_llm_claims=raw_claims,
        reconciled=reconciled,
        reconciliation_log=reconciliation_log,
        decision_id=decision_id,
    )
