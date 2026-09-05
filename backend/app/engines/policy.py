import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.engines.decision import ActionType, Channel, RecoveryAction
from app.models.tables import Decision, Policy, PolicyEvaluation, Transaction
from app.domain.mandate.state_machine import is_mandate_transaction, evaluate_mandate_eligibility
from app.domain.mandate.models import MandateState


class PolicyVerdict(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    ESCALATED = "ESCALATED"


class CheckResult(BaseModel):
    """Result of an individual deterministic policy check."""
    check_name: str
    passed: bool
    verdict_impact: Optional[PolicyVerdict] = None  # Set to BLOCKED or ESCALATED when passed=False
    reason_code: Optional[str] = None
    description: str


class PolicyEvaluationTrace(BaseModel):
    """Full decision receipt trace holding every check outcome and final verdict."""
    decision_id: UUID
    transaction_id: UUID
    verdict: PolicyVerdict
    reasons: List[str]
    check_results: List[CheckResult]
    evaluated_at: datetime


# ---- Default Policy Configuration ----

DEFAULT_POLICY_CONFIG: Dict[str, Any] = {
    # Amount tier limits (INR)
    "low_tier_max": 5000.0,
    "mid_tier_max": 25000.0,
    "mid_tier_min_confidence": 0.40,
    # Execution caps
    "max_retries": 2,
    "max_contacts_24h": 2,
    # Discount cap (10% matches Phase 5 EV default)
    "max_discount_pct": 0.10,
}


def load_policy_config(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Loads active policy config from the policies DB table.
    Seeds the default policy if not already present.
    """
    if db is None:
        return dict(DEFAULT_POLICY_CONFIG)

    policy_row = db.query(Policy).filter(Policy.name == "default_recovery_policy").first()
    if policy_row and policy_row.config:
        return dict(policy_row.config)

    # Seed default policy into DB
    new_policy = Policy(
        id=uuid.uuid4(),
        name="default_recovery_policy",
        config=DEFAULT_POLICY_CONFIG,
        version=1,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(new_policy)
    db.commit()
    return dict(DEFAULT_POLICY_CONFIG)


def update_policy_config_in_db(new_config: Dict[str, Any], db: Session) -> Policy:
    """Updates policy configuration in database at runtime."""
    policy_row = db.query(Policy).filter(Policy.name == "default_recovery_policy").first()
    if not policy_row:
        policy_row = Policy(
            id=uuid.uuid4(),
            name="default_recovery_policy",
            config=new_config,
            version=1,
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(policy_row)
    else:
        policy_row.config = new_config
        policy_row.version += 1
        policy_row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    return policy_row


# ---- The 5 Deterministic Checks ----


def check_amount_tier(
    contract: RecoveryAction,
    config: Dict[str, Any],
) -> CheckResult:
    """
    Check 1: Amount-tier check (Confidence-aware tiered autonomy).
    - Amount > mid_tier_max (> 25k): High-value, human-only escalation.
    - Amount between low_tier and mid_tier (5k-25k): Requires confidence >= threshold, else escalation.
    - Amount <= low_tier (<= 5k): Automated autonomy.
    """
    amt = float(contract.amount)
    conf = float(contract.confidence)
    low_max = float(config.get("low_tier_max", 5000.0))
    mid_max = float(config.get("mid_tier_max", 25000.0))
    min_conf = float(config.get("mid_tier_min_confidence", 0.40))

    if amt > mid_max:
        return CheckResult(
            check_name="amount_tier_check",
            passed=False,
            verdict_impact=PolicyVerdict.ESCALATED,
            reason_code="AMOUNT_TIER_HUMAN_ONLY",
            description=f"Transaction amount ₹{amt:,.2f} exceeds automated ceiling (₹{mid_max:,.2f}). Human escalation required.",
        )

    if amt > low_max:
        if conf < min_conf:
            return CheckResult(
                check_name="amount_tier_check",
                passed=False,
                verdict_impact=PolicyVerdict.ESCALATED,
                reason_code="AMOUNT_TIER_APPROVAL_REQUIRED",
                description=f"Mid-tier amount ₹{amt:,.2f} has confidence {conf:.2%} (< {min_conf:.0%}). Tiered approval required.",
            )
        return CheckResult(
            check_name="amount_tier_check",
            passed=True,
            description=f"Mid-tier amount ₹{amt:,.2f} has sufficient confidence {conf:.2%} for automated action.",
        )

    return CheckResult(
        check_name="amount_tier_check",
        passed=True,
        description=f"Low-tier amount ₹{amt:,.2f} is within low-risk autonomy limit (₹{low_max:,.2f}).",
    )


def check_retry_limit(
    contract: RecoveryAction,
    config: Dict[str, Any],
    decision_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> CheckResult:
    """
    Check 2: Retry limit check.
    If action is RETRY, ensure prior retries on this transaction have not breached cap.
    """
    if contract.action_type != ActionType.RETRY:
        return CheckResult(
            check_name="retry_limit_check",
            passed=True,
            description="Not a RETRY action; check passed automatically.",
        )

    max_retries = int(config.get("max_retries", 2))

    # Read prior retry count from policy context or query DB
    prior_retries = contract.policy_context.get("prior_retry_count")
    if prior_retries is None and db is not None:
        tx_uuid = UUID(contract.transaction_id)
        query = db.query(Decision).filter(
            Decision.transaction_id == tx_uuid,
            Decision.action_type == "RETRY",
        )
        if decision_id is not None:
            query = query.filter(Decision.id != decision_id)
        prior_retries = query.count()

    prior_retries = int(prior_retries or 0)

    if prior_retries >= max_retries:
        return CheckResult(
            check_name="retry_limit_check",
            passed=False,
            verdict_impact=PolicyVerdict.BLOCKED,
            reason_code="RETRY_LIMIT_REACHED",
            description=f"Transaction has reached max retry attempts ({prior_retries} >= {max_retries}). Action blocked.",
        )

    return CheckResult(
        check_name="retry_limit_check",
        passed=True,
        description=f"Retry attempt {prior_retries + 1} of {max_retries} allowed.",
    )


def check_contact_frequency(
    contract: RecoveryAction,
    config: Dict[str, Any],
) -> CheckResult:
    """
    Check 3: Contact-frequency limit check (Anti-spam guardrail).
    If action is outbound communication (WhatsApp/Email), verify 24h cap.
    """
    is_contact_action = contract.action_type in (ActionType.WHATSAPP, ActionType.EMAIL) or contract.channel in (Channel.WHATSAPP, Channel.EMAIL)
    if not is_contact_action:
        return CheckResult(
            check_name="contact_frequency_check",
            passed=True,
            description="Non-communication action; contact frequency check passed.",
        )

    max_contacts = int(config.get("max_contacts_24h", 2))
    prior_contacts = int(contract.policy_context.get("prior_contacts_24h", 0))

    if prior_contacts >= max_contacts:
        return CheckResult(
            check_name="contact_frequency_check",
            passed=False,
            verdict_impact=PolicyVerdict.BLOCKED,
            reason_code="CONTACT_FREQUENCY_EXCEEDED",
            description=f"Customer already contacted {prior_contacts} times in last 24h (cap: {max_contacts}). Action blocked.",
        )

    return CheckResult(
        check_name="contact_frequency_check",
        passed=True,
        description=f"Customer contact count {prior_contacts} within 24h cap ({max_contacts}).",
    )


def check_discount_limit(
    contract: RecoveryAction,
    config: Dict[str, Any],
) -> CheckResult:
    """
    Check 4: Discount limit check.
    If action is DISCOUNT, verify proposed discount_pct in policy_context <= max_discount_pct.
    """
    if contract.action_type != ActionType.DISCOUNT:
        return CheckResult(
            check_name="discount_limit_check",
            passed=True,
            description="Not a DISCOUNT action; discount limit check passed.",
        )

    max_disc = Decimal(str(config.get("max_discount_pct", 0.10)))

    # Explicitly read discount_pct from contract.policy_context
    raw_discount = contract.policy_context.get("discount_pct", 0.10)
    proposed_disc = Decimal(str(raw_discount))

    if proposed_disc > max_disc:
        return CheckResult(
            check_name="discount_limit_check",
            passed=False,
            verdict_impact=PolicyVerdict.BLOCKED,
            reason_code="DISCOUNT_LIMIT_EXCEEDED",
            description=f"Proposed discount rate {proposed_disc:.1%} exceeds policy ceiling of {max_disc:.1%}. Action blocked.",
        )

    return CheckResult(
        check_name="discount_limit_check",
        passed=True,
        description=f"Proposed discount rate {proposed_disc:.1%} is within allowable ceiling ({max_disc:.1%}).",
    )


def check_action_idempotency(
    contract: RecoveryAction,
    decision_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> CheckResult:
    """
    Check 5: Action Idempotency check.
    Verifies that this exact action type has not already been executed or approved for this transaction.
    """
    # Check explicit flag in context if simulated, or check DB
    already_taken = contract.policy_context.get("action_already_taken")

    if already_taken is None and db is not None:
        tx_uuid = UUID(contract.transaction_id)
        from app.models.tables import Action
        # First check if action was executed in actions table
        prior_execution = (
            db.query(Action)
            .filter(
                Action.transaction_id == tx_uuid,
                Action.action_type == contract.action_type.value,
            )
            .first()
        )
        if prior_execution:
            already_taken = True
        else:
            # Check if an earlier decision exists for this transaction (excluding the decision currently being evaluated)
            query = db.query(Decision).filter(
                Decision.transaction_id == tx_uuid,
                Decision.action_type == contract.action_type.value,
                Decision.channel == contract.channel.value,
            )
            if decision_id is not None:
                query = query.filter(Decision.id != decision_id)
            already_taken = bool(query.first() is not None)

    if already_taken:
        return CheckResult(
            check_name="action_idempotency_check",
            passed=False,
            verdict_impact=PolicyVerdict.BLOCKED,
            reason_code="ACTION_ALREADY_TAKEN",
            description=f"Action {contract.action_type.value} via {contract.channel.value} was already recorded for this transaction. Duplicate action blocked.",
        )

    return CheckResult(
        check_name="action_idempotency_check",
        passed=True,
        description=f"Action {contract.action_type.value} has not been previously executed for this transaction.",
    )


def check_mandate_compliance(
    contract: RecoveryAction,
    config: Dict[str, Any],
    decision_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> CheckResult:
    """
    Check 6 (Phase 11): UPI Mandate Compliance Check (NPCI AutoPay Regulatory Guardrail).
    Runs independently as an additive check alongside the 5 Phase 7 checks.

    Rules:
    1. If transaction is NOT mandate-related -> Passed automatically.
    2. If mandate is TERMINAL (e.g. MANDATE_REVOKED, MANDATE_EXPIRED, UPI_MANDATE_EXPIRED):
       Standard RETRY is strictly prohibited -> BLOCKED with MANDATE_REVOKED_RETRY_PROHIBITED
       or MANDATE_EXPIRED_RETRY_PROHIBITED.
    3. If mandate is TRANSIENT (e.g. UPI_MANDATE_FAILED, MANDATE_EXECUTION_FAILED):
       - If action is RETRY, enforces NPCI 24-hour cooling-off window (delay_hours >= 24).
         If delay_hours < 24 -> BLOCKED with MANDATE_NPCI_WINDOW_VIOLATION.
       - If prior_retry_count >= 1 -> BLOCKED with MANDATE_MAX_RETRIES_EXCEEDED.
    4. Re-registration communication actions (WHATSAPP, EMAIL) or ESCALATE pass for revoked/expired mandates.
    """
    pm = contract.policy_context.get("payment_method")
    fc = contract.policy_context.get("failure_code")
    prior_retries = contract.policy_context.get("prior_retry_count")

    if (not pm or not fc) and db is not None:
        try:
            tx = db.query(Transaction).filter(Transaction.id == UUID(contract.transaction_id)).first()
            if tx:
                if not pm:
                    pm = tx.payment_method.value if hasattr(tx.payment_method, "value") else str(tx.payment_method)
                if not fc:
                    fc = tx.failure_code
        except Exception:
            pass

    # Non-mandate transactions pass automatically
    if not is_mandate_transaction(str(pm or ""), str(fc or "")):
        return CheckResult(
            check_name="mandate_compliance_check",
            passed=True,
            reason_code="NA_NON_MANDATE",
            description="N/A — not a mandate transaction",
        )

    # Calculate prior retries if not explicitly set in policy_context
    if prior_retries is None and db is not None:
        try:
            tx_uuid = UUID(contract.transaction_id)
            query = db.query(Decision).filter(
                Decision.transaction_id == tx_uuid,
                Decision.action_type == "RETRY",
            )
            if decision_id is not None:
                query = query.filter(Decision.id != decision_id)
            prior_retries = query.count()
        except Exception:
            prior_retries = 0

    prior_retries = int(prior_retries or 0)
    delay_hours = int(contract.delay_hours or 0)

    # Evaluate mandate eligibility under NPCI AutoPay guidelines
    eligibility = evaluate_mandate_eligibility(
        payment_method=str(pm),
        failure_code=str(fc or ""),
        prior_retry_count=prior_retries,
        delay_hours=delay_hours,
    )

    # Handle RETRY proposals
    if contract.action_type == ActionType.RETRY:
        if not eligibility.is_retry_eligible:
            clean_fc = str(fc or "").upper()
            if clean_fc == "MANDATE_REVOKED":
                reason = "MANDATE_REVOKED_RETRY_PROHIBITED"
            elif clean_fc in ("MANDATE_EXPIRED", "UPI_MANDATE_EXPIRED"):
                reason = "MANDATE_EXPIRED_RETRY_PROHIBITED"
            elif clean_fc == "MANDATE_REGISTRATION_FAILED":
                reason = "MANDATE_UNREGISTERED_RETRY_PROHIBITED"
            elif prior_retries >= 1:
                reason = "MANDATE_MAX_RETRIES_EXCEEDED"
            else:
                reason = "MANDATE_RETRY_PROHIBITED"

            return CheckResult(
                check_name="mandate_compliance_check",
                passed=False,
                verdict_impact=PolicyVerdict.BLOCKED,
                reason_code=reason,
                description=eligibility.reason,
            )

        if delay_hours < eligibility.min_retry_delay_hours:
            return CheckResult(
                check_name="mandate_compliance_check",
                passed=False,
                verdict_impact=PolicyVerdict.BLOCKED,
                reason_code="MANDATE_NPCI_WINDOW_VIOLATION",
                description=(
                    f"NPCI AutoPay requires minimum {eligibility.min_retry_delay_hours}h cooling-off "
                    f"before re-presenting mandate debit (proposed delay: {delay_hours}h)."
                ),
            )

    # Handle non-RETRY actions (e.g. DISCOUNT or other prohibited actions)
    if contract.action_type.value in eligibility.prohibited_actions:
        return CheckResult(
            check_name="mandate_compliance_check",
            passed=False,
            verdict_impact=PolicyVerdict.BLOCKED,
            reason_code="MANDATE_ACTION_INELIGIBLE",
            description=f"Action {contract.action_type.value} is prohibited under mandate state {eligibility.mandate_state.value}.",
        )

    return CheckResult(
        check_name="mandate_compliance_check",
        passed=True,
        description=f"Mandate compliance verified under {eligibility.npci_rule_reference}.",
    )


# ---- Policy Evaluation Engine ----


def evaluate_policy(
    contract: RecoveryAction,
    decision_id: Optional[UUID] = None,
    db: Optional[Session] = None,
    policy_override: Optional[Dict[str, Any]] = None,
) -> PolicyEvaluationTrace:
    """
    Executes all 6 deterministic policy checks on an Action Contract.
    Persists evaluation trace into policy_evaluations table.
    Zero LLM involvement.
    """
    if decision_id is None:
        decision_id = uuid.uuid4()

    # 1. Load active policy configuration
    config = load_policy_config(db=db)
    if policy_override:
        config.update(policy_override)

    # 2. Run all 6 checks independently — never skip a check
    check_results: List[CheckResult] = [
        check_amount_tier(contract, config),
        check_retry_limit(contract, config, decision_id=decision_id, db=db),
        check_contact_frequency(contract, config),
        check_discount_limit(contract, config),
        check_action_idempotency(contract, decision_id=decision_id, db=db),
        check_mandate_compliance(contract, config, decision_id=decision_id, db=db),
    ]

    # 3. Determine final aggregate verdict
    # Hard BLOCKED trumps ESCALATED; ESCALATED trumps APPROVED.
    blocked_reasons = [c.reason_code for c in check_results if c.verdict_impact == PolicyVerdict.BLOCKED and c.reason_code]
    escalated_reasons = [c.reason_code for c in check_results if c.verdict_impact == PolicyVerdict.ESCALATED and c.reason_code]

    if blocked_reasons:
        final_verdict = PolicyVerdict.BLOCKED
        final_reasons = blocked_reasons
    elif escalated_reasons:
        final_verdict = PolicyVerdict.ESCALATED
        final_reasons = escalated_reasons
    else:
        final_verdict = PolicyVerdict.APPROVED
        final_reasons = ["ALL_POLICY_CHECKS_PASSED"]

    tx_uuid = UUID(contract.transaction_id)
    eval_time = datetime.now(timezone.utc).replace(tzinfo=None)

    # 4. Persist check-by-check evaluations into policy_evaluations table
    if db is not None:
        for chk in check_results:
            eval_record = PolicyEvaluation(
                id=uuid.uuid4(),
                decision_id=decision_id,
                transaction_id=tx_uuid,
                check_name=chk.check_name,
                passed=chk.passed,
                reason_code=chk.reason_code,
                created_at=eval_time,
            )
            db.add(eval_record)
        db.commit()

    return PolicyEvaluationTrace(
        decision_id=decision_id,
        transaction_id=tx_uuid,
        verdict=final_verdict,
        reasons=final_reasons,
        check_results=check_results,
        evaluated_at=eval_time,
    )
