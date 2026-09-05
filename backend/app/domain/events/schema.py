from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NormalizedRevenueEvent(BaseModel):
    """
    Normalized Revenue Event Bus Schema.

    Strictly conforms to Ground Truth specification:
    event_type, customer_id, merchant_id, amount, currency, timestamp, source, metadata
    along with external_event_id (for idempotency) and optional transaction_id.
    """
    model_config = ConfigDict(from_attributes=True)

    external_event_id: str = Field(..., description="Unique event identifier for idempotency check")
    event_type: str = Field(..., description="Event type, e.g. payment_failed, payment_success")
    customer_id: UUID = Field(..., description="Customer ID")
    merchant_id: UUID = Field(..., description="Merchant ID")
    amount: Decimal = Field(..., description="Event monetary amount")
    currency: str = Field(default="INR", description="Currency code (defaults to INR)")
    timestamp: datetime = Field(..., description="Timestamp of event creation")
    source: str = Field(default="revenue_event_bus", description="Source system/producer")
    transaction_id: Optional[UUID] = Field(default=None, description="Associated transaction ID if known")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary (failure code, channel, etc.)")
