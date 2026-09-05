from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Set
from uuid import UUID

from app.domain.events.schema import NormalizedRevenueEvent

# Ground Truth failure taxonomy
ALL_TAXONOMY_FAILURE_CODES: Set[str] = {
    # UPI
    "UPI_COLLECT_EXPIRED",
    "UPI_BANK_TIMEOUT",
    "UPI_INSUFFICIENT_FUNDS",
    "UPI_PSP_ERROR",
    "UPI_CUSTOMER_DECLINED",
    "UPI_LIMIT_EXCEEDED",
    "UPI_MANDATE_FAILED",
    "UPI_MANDATE_EXPIRED",
    # Cards
    "CARD_EXPIRED",
    "CARD_DECLINED",
    "CARD_LIMIT_EXCEEDED",
    "ISSUER_TIMEOUT",
    "INSUFFICIENT_FUNDS",
    # Netbanking
    "BANK_TIMEOUT",
    "BANK_DECLINED",
    "SESSION_EXPIRED",
    # Mandate
    "MANDATE_REGISTRATION_FAILED",
    "MANDATE_EXECUTION_FAILED",
    "MANDATE_REVOKED",
    "MANDATE_EXPIRED",
    # Checkout
    "CHECKOUT_ABANDONED",
    "PAYMENT_PAGE_EXIT",
    "OTP_TIMEOUT",
    "PAYMENT_METHOD_CHANGED",
    # B2B
    "INVOICE_OVERDUE",
    "PAYMENT_PROMISE_BROKEN",
    "PARTIAL_PAYMENT",
}


def normalize_event(raw: Any) -> NormalizedRevenueEvent:
    """
    Normalizes a raw incoming event payload (dict or model) into the standard
    NormalizedRevenueEvent format.

    Validates taxonomy failure codes and extracts metadata consistently.
    """
    if isinstance(raw, NormalizedRevenueEvent):
        return raw

    if isinstance(raw, dict):
        data = dict(raw)
    elif hasattr(raw, "__dict__"):
        data = {k: v for k, v in raw.__dict__.items() if not k.startswith("_")}
    else:
        raise ValueError(f"Unsupported event payload type: {type(raw)}")

    # Extract event ID for idempotency
    external_event_id = str(
        data.get("external_event_id")
        or data.get("event_id")
        or data.get("id")
        or ""
    )
    if not external_event_id:
        raise ValueError("Raw event must contain an event identifier (external_event_id, event_id, or id)")

    # Extract or infer event_type & failure_code
    raw_event_type = str(data.get("event_type") or "").strip()
    metadata: Dict[str, Any] = dict(data.get("metadata") or data.get("metadata_") or {})

    failure_code = (
        data.get("failure_code")
        or metadata.get("failure_code")
        or (raw_event_type if raw_event_type in ALL_TAXONOMY_FAILURE_CODES else None)
    )

    if failure_code:
        failure_code = str(failure_code).strip()
        metadata["failure_code"] = failure_code
        event_type = "payment_failed"
    elif raw_event_type in ("payment_failed", "payment.failed"):
        event_type = "payment_failed"
    elif raw_event_type in ("payment_success", "payment.success"):
        event_type = "payment_success"
    else:
        event_type = raw_event_type or "unknown"

    # Extract payment method into metadata if available
    payment_method = data.get("payment_method") or metadata.get("payment_method")
    if payment_method:
        metadata["payment_method"] = str(payment_method)

    # Extract amount
    raw_amount = data.get("amount")
    if raw_amount is None:
        raise ValueError("Raw event missing required amount field")
    amount = Decimal(str(raw_amount))

    # Extract currency
    currency = str(data.get("currency") or "INR")

    # Extract timestamp
    raw_ts = data.get("timestamp") or data.get("created_at") or datetime.now(timezone.utc).replace(tzinfo=None)
    if isinstance(raw_ts, str):
        timestamp = datetime.fromisoformat(raw_ts)
    elif isinstance(raw_ts, datetime):
        timestamp = raw_ts
    else:
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    # Extract customer_id, merchant_id, transaction_id
    raw_cust_id = data.get("customer_id")
    if not raw_cust_id:
        raise ValueError("Raw event missing required customer_id field")
    customer_id = UUID(str(raw_cust_id))

    raw_merch_id = data.get("merchant_id")
    if not raw_merch_id:
        raise ValueError("Raw event missing required merchant_id field")
    merchant_id = UUID(str(raw_merch_id))

    raw_tx_id = data.get("transaction_id")
    transaction_id = UUID(str(raw_tx_id)) if raw_tx_id else None

    source = str(data.get("source") or "revenue_event_bus")

    return NormalizedRevenueEvent(
        external_event_id=external_event_id,
        event_type=event_type,
        customer_id=customer_id,
        merchant_id=merchant_id,
        transaction_id=transaction_id,
        amount=amount,
        currency=currency,
        timestamp=timestamp,
        source=source,
        metadata=metadata,
    )
