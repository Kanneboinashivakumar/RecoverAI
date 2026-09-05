from decimal import Decimal
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field

# Flat operational cost constants (INR)
DEFAULT_ACTION_COSTS: Dict[str, Decimal] = {
    "RETRY": Decimal("1.00"),       # Gateway re-submission fee
    "WHATSAPP": Decimal("1.50"),    # WhatsApp Business API per-template message
    "EMAIL": Decimal("0.20"),       # Transactional email delivery cost
    "ESCALATE": Decimal("25.00"),   # Human support agent review cost
}

DEFAULT_DISCOUNT_PCT: Decimal = Decimal("0.10")  # 10% discount rate


class ExpectedValueResult(BaseModel):
    """Result of deterministic Expected Value calculation."""
    action_type: str = Field(..., description="Action evaluated (RETRY, WHATSAPP, EMAIL, DISCOUNT, ESCALATE)")
    amount: Decimal = Field(..., description="Original recoverable transaction amount (INR)")
    recovery_probability: float = Field(..., ge=0.0, le=1.0, description="Predicted recovery probability")
    action_cost: Decimal = Field(..., description="Deterministic cost of taking the action (INR)")
    expected_value: Decimal = Field(..., description="Expected net recovery value: (probability * amount) - cost")
    is_positive_ev: bool = Field(..., description="Whether expected value exceeds cost (EV > 0)")


def calculate_action_cost(
    action_type: str,
    amount: Union[Decimal, float, str],
    discount_pct: Decimal = DEFAULT_DISCOUNT_PCT,
) -> Decimal:
    """
    Computes deterministic operational cost for an action.
    - RETRY: ₹1.00
    - WHATSAPP: ₹1.50
    - EMAIL: ₹0.20
    - ESCALATE: ₹25.00
    - DISCOUNT: discount_pct * amount (proportional to transaction size)
    """
    action = action_type.strip().upper()
    dec_amount = Decimal(str(amount))

    if action == "DISCOUNT":
        # Discount cost scales with transaction size
        return round(dec_amount * discount_pct, 2)

    return DEFAULT_ACTION_COSTS.get(action, Decimal("1.00"))


def calculate_expected_value(
    amount: Union[Decimal, float, str],
    recovery_probability: float,
    action_type: str = "RETRY",
    discount_pct: Decimal = DEFAULT_DISCOUNT_PCT,
) -> ExpectedValueResult:
    """
    Deterministic Expected Value calculation:
        EV = (probability * recoverable_amount) - cost

    No LLM involvement. Pure deterministic financial logic.
    """
    dec_amount = Decimal(str(amount))
    prob_dec = Decimal(str(round(recovery_probability, 4)))
    action_cost = calculate_action_cost(action_type, dec_amount, discount_pct=discount_pct)

    expected_recovery = dec_amount * prob_dec
    net_ev = round(expected_recovery - action_cost, 2)

    return ExpectedValueResult(
        action_type=action_type.upper(),
        amount=dec_amount,
        recovery_probability=float(prob_dec),
        action_cost=action_cost,
        expected_value=net_ev,
        is_positive_ev=bool(net_ev > Decimal("0.00")),
    )


def rank_recovery_opportunities(
    opportunities: List[Dict[str, Any]],
) -> List[ExpectedValueResult]:
    """
    Calculates EV for multiple opportunities and ranks them descending by expected value.
    """
    results = []
    for opp in opportunities:
        ev_res = calculate_expected_value(
            amount=opp["amount"],
            recovery_probability=opp["recovery_probability"],
            action_type=opp.get("action_type", "RETRY"),
            discount_pct=opp.get("discount_pct", DEFAULT_DISCOUNT_PCT),
        )
        results.append(ev_res)

    # Deterministic ranking: highest EV first
    results.sort(key=lambda x: x.expected_value, reverse=True)
    return results
