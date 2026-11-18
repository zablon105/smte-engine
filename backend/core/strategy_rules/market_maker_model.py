"""Non-executing Market Maker Model (MMXM: MMBM/MMSM) calculations."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class MMXMLocationAssessment:
    is_valid_location: bool
    model_type: Literal["MMBM", "MMSM"]
    current_price: float
    equilibrium_50pct: float
    relative_position_pct: float
    location_zone: Literal["DISCOUNT", "PREMIUM", "AT_EQUILIBRIUM"]


def calculate_dealing_range_equilibrium(range_low: float, range_high: float) -> float:
    """Calculate the 50% equilibrium level of a dealing range."""
    if not isfinite(range_low) or not isfinite(range_high):
        raise ValueError("Range prices must be finite")
    if range_low >= range_high:
        raise ValueError("range_low must be strictly less than range_high")
    return (range_low + range_high) / 2.0


def evaluate_mmxm_location(
    current_price: float,
    range_low: float,
    range_high: float,
    model_type: Literal["MMBM", "MMSM"],
) -> MMXMLocationAssessment:
    """Assess whether an MMXM base/reversal forms in the correct dealing range location.

    According to MMXM research notes:
    - Market Maker Buy Model (MMBM) bases start in an HTF DISCOUNT (< 50% equilibrium).
    - Market Maker Sell Model (MMSM) bases start in an HTF PREMIUM (> 50% equilibrium).
    """
    if not isfinite(current_price):
        raise ValueError("current_price must be finite")
    if range_low >= range_high:
        raise ValueError("range_low must be strictly less than range_high")
    if model_type not in ("MMBM", "MMSM"):
        raise ValueError("model_type must be 'MMBM' or 'MMSM'")

    eq = calculate_dealing_range_equilibrium(range_low, range_high)
    range_span = range_high - range_low
    pos_pct = ((current_price - range_low) / range_span) * 100.0

    if current_price < eq:
        location_zone = "DISCOUNT"
    elif current_price > eq:
        location_zone = "PREMIUM"
    else:
        location_zone = "AT_EQUILIBRIUM"

    if model_type == "MMBM":
        is_valid = current_price < eq
    else:
        is_valid = current_price > eq

    return MMXMLocationAssessment(
        is_valid_location=is_valid,
        model_type=model_type,
        current_price=current_price,
        equilibrium_50pct=eq,
        relative_position_pct=pos_pct,
        location_zone=location_zone,
    )

