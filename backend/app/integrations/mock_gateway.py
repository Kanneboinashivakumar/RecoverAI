import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID


def execute_mock_retry(
    transaction_id: UUID,
    amount: Decimal,
    channel: str = "UPI",
) -> Dict[str, Any]:
    """
    Mock payment gateway adapter for RETRY interventions.
    Simulates re-submitting a payment charge through Razorpay / Cashfree / Stripe mock APIs.
    """
    gateway_txn_id = f"mock_pay_{uuid.uuid4().hex[:12]}"
    return {
        "status": "submitted",
        "mock_provider": "MockPG-GatewaySimulator",
        "gateway_reference_id": gateway_txn_id,
        "transaction_id": str(transaction_id),
        "amount": float(amount),
        "channel": channel.upper(),
        "operational_cost": 1.00,
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }
