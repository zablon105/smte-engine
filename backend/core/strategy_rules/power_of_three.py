"""Non-executing Power of 3 (PO3 / AMD) and Judas Swing calculations."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class PO3PricingAssessment:
    is_valid_entry_zone: bool
    bias: Literal["BULLISH", "BEARISH"]
    open_price: float
    current_price: float
    price_delta: float
    zone_type: Literal["DISCOUNT", "PREMIUM", "AT_OPEN"]


@dataclass(frozen=True)
class JudasSwingAssessment:
    has_judas_swing: bool
    bias: Literal["BULLISH", "BEARISH"]
    open_price: float
    manipulation_extreme: float
    purge_distance: float


def evaluate_po3_pricing(
    open_price: float,
    current_price: float,
    bias: Literal["BULLISH", "BEARISH"],
) -> PO3PricingAssessment:
    """Assess whether current price is in the appropriate PO3 entry zone relative to the open.

    According to PO3 / AMD research notes:
    - Smart money positions within the wick:
      - For BULLISH bias: buy BELOW the candle/period opening price (time-based discount).
      - For BEARISH bias: sell ABOVE the candle/period opening price (time-based premium).
    """
    if not isfinite(open_price) or not isfinite(current_price):
        raise ValueError("Prices must be finite")
    if bias not in ("BULLISH", "BEARISH"):
        raise ValueError("bias must be 'BULLISH' or 'BEARISH'")

    delta = current_price - open_price
    if delta < 0:
        zone_type = "DISCOUNT"
    elif delta > 0:
        zone_type = "PREMIUM"
    else:
        zone_type = "AT_OPEN"

    if bias == "BULLISH":
        is_valid = current_price < open_price
    else:
        is_valid = current_price > open_price

    return PO3PricingAssessment(
        is_valid_entry_zone=is_valid,
        bias=bias,
        open_price=open_price,
        current_price=current_price,
        price_delta=delta,
        zone_type=zone_type,
    )


def detect_judas_swing(
    open_price: float,
    period_extreme: float,
    bias: Literal["BULLISH", "BEARISH"],
    min_purge_distance: float = 0.0,
) -> JudasSwingAssessment:
    """Evaluate whether an initial false move (Judas Swing) occurred beyond the open.

    - For BULLISH bias: Judas swing is a move below the opening price into discount.
    - For BEARISH bias: Judas swing is a move above the opening price into premium.
    """
    if not isfinite(open_price) or not isfinite(period_extreme):
        raise ValueError("Prices must be finite")
    if min_purge_distance < 0:
        raise ValueError("min_purge_distance must be non-negative")
    if bias not in ("BULLISH", "BEARISH"):
        raise ValueError("bias must be 'BULLISH' or 'BEARISH'")

    if bias == "BULLISH":
        purge_distance = max(0.0, open_price - period_extreme)
        has_judas = (period_extreme < open_price) and (purge_distance >= min_purge_distance)
    else:
        purge_distance = max(0.0, period_extreme - open_price)
        has_judas = (period_extreme > open_price) and (purge_distance >= min_purge_distance)

    return JudasSwingAssessment(
        has_judas_swing=has_judas,
        bias=bias,
        open_price=open_price,
        manipulation_extreme=period_extreme,
        purge_distance=purge_distance,
    )

