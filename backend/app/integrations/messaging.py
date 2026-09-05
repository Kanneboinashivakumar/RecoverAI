import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID

from app.engines.decision import ActionType, RecoveryAction
from app.integrations.mock_gateway import execute_mock_retry


def send_mock_whatsapp(
    transaction_id: UUID,
    amount: Decimal,
    customer_phone: str = "+919876543210",
) -> Dict[str, Any]:
    """
    Mock WhatsApp Business API adapter.
    Simulates sending an interactive payment link recovery template.
    """
    msg_id = f"wamid_mock_{uuid.uuid4().hex[:12]}"
    return {
        "status": "delivered",
        "mock_provider": "MockMetaWhatsAppBusinessAPI",
        "message_id": msg_id,
        "transaction_id": str(transaction_id),
        "amount": float(amount),
        "recipient": customer_phone,
        "template_name": "payment_failure_quick_recovery",
        "operational_cost": 1.50,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }


def send_mock_email(
    transaction_id: UUID,
    amount: Decimal,
    customer_email: str = "customer@example.com",
) -> Dict[str, Any]:
    """
    Mock Email delivery adapter (e.g. SendGrid / AWS SES mock).
    Simulates sending an invoice payment retry email.
    """
    msg_id = f"email_mock_{uuid.uuid4().hex[:12]}"
    return {
        "status": "delivered",
        "mock_provider": "MockSESEmailGateway",
        "message_id": msg_id,
        "transaction_id": str(transaction_id),
        "amount": float(amount),
        "recipient": customer_email,
        "subject": "Action Required: Complete your pending payment",
        "operational_cost": 0.20,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }


def send_mock_discount(
    transaction_id: UUID,
    amount: Decimal,
    discount_pct: Decimal = Decimal("0.10"),
    channel: str = "WHATSAPP",
) -> Dict[str, Any]:
    """
    Mock discount incentive adapter.
    Generates a promotional coupon code and delivers it via WhatsApp or Email.
    """
    coupon_code = f"RECOVER{int(discount_pct * 100)}_{uuid.uuid4().hex[:6].upper()}"
    discount_val = round(amount * discount_pct, 2)
    effective_amount = round(amount - discount_val, 2)
    return {
        "status": "delivered",
        "mock_provider": "MockDiscountCampaignManager",
        "coupon_code": coupon_code,
        "transaction_id": str(transaction_id),
        "original_amount": float(amount),
        "discount_pct": float(discount_pct),
        "discount_amount": float(discount_val),
        "effective_amount": float(effective_amount),
        "delivery_channel": channel.upper(),
        "operational_cost": float(discount_val),
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }


def execute_action(
    contract: RecoveryAction,
) -> Dict[str, Any]:
    """
    Central mock action dispatcher mapping Action Contract to specific mock integration.
    """
    tx_uuid = UUID(contract.transaction_id)
    action_type = contract.action_type

    if action_type == ActionType.RETRY:
        return execute_mock_retry(
            transaction_id=tx_uuid,
            amount=contract.amount,
            channel=contract.channel.value,
        )
    elif action_type == ActionType.WHATSAPP:
        return send_mock_whatsapp(
            transaction_id=tx_uuid,
            amount=contract.amount,
        )
    elif action_type == ActionType.EMAIL:
        return send_mock_email(
            transaction_id=tx_uuid,
            amount=contract.amount,
        )
    elif action_type == ActionType.DISCOUNT:
        raw_discount = contract.policy_context.get("discount_pct", Decimal("0.10"))
        discount_pct = Decimal(str(raw_discount))
        return send_mock_discount(
            transaction_id=tx_uuid,
            amount=contract.amount,
            discount_pct=discount_pct,
            channel=contract.channel.value,
        )
    elif action_type == ActionType.ESCALATE:
        reason_str = "; ".join(contract.reason_codes) if contract.reason_codes else "Escalation requested"
        return dispatch_mock_escalation(
            transaction_id=tx_uuid,
            amount=contract.amount,
            reason=reason_str,
        )
    else:
        raise ValueError(f"Unsupported action type for execution: {action_type}")


def dispatch_mock_escalation(
    transaction_id: UUID,
    amount: Decimal,
    reason: str = "Automated escalation to human review queue",
) -> Dict[str, Any]:
    """
    Mock Human Review / Support Ticketing Dispatch adapter (e.g. Zendesk / Jira Service Desk mock).
    Simulates queuing the transaction for manual agent review and merchant intervention.
    """
    ticket_id = f"TICK_mock_{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "queued_for_review",
        "mock_provider": "MockHumanReviewDispatch",
        "ticket_id": ticket_id,
        "transaction_id": str(transaction_id),
        "amount": float(amount),
        "queue": "high_priority_human_escalations",
        "reason": reason,
        "operational_cost": 25.00,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }
