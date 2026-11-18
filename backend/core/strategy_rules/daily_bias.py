"""Non-executing Daily Bias and IRL/ERL cycle calculations."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class BoundaryInteraction:
    boundary_type: Literal["HIGH", "LOW"]
    boundary_price: float
    tested: bool
    interaction_type: Literal["DISPLACEMENT", "MANIPULATION_SWEEP", "UNREACHED"]


def classify_liquidity_type(is_fvg: bool) -> Literal["IRL", "ERL"]:
    """Classify liquidity as Internal Range Liquidity (IRL) or External Range Liquidity (ERL).

    According to the Daily Bias & IRL/ERL research notes:
    - IRL = Internal Range Liquidity (FVGs and imbalances).
    - ERL = External Range Liquidity (old highs and lows, swing points, time-based extremes).
    """
    return "IRL" if is_fvg else "ERL"


def next_expected_liquidity_draw(last_tapped_type: Literal["IRL", "ERL"]) -> Literal["IRL", "ERL"]:
    """Return the next expected draw on liquidity in the alternating cycle.

    Market alternates between IRL and ERL: internal -> external -> internal, repeating.
    """
    if last_tapped_type not in ("IRL", "ERL"):
        raise ValueError("last_tapped_type must be 'IRL' or 'ERL'")
    return "ERL" if last_tapped_type == "IRL" else "IRL"


def evaluate_prior_boundary_interaction(
    candle_open: float,
    candle_high: float,
    candle_low: float,
    candle_close: float,
    boundary_price: float,
    boundary_type: Literal["HIGH", "LOW"],
) -> BoundaryInteraction:
    """Evaluate whether price action displaced through or swept a prior candle's high/low.

    According to Daily Bias research notes:
    - Close beyond previous high/low = displacement (continuation).
    - Wick beyond previous high/low but failure to close beyond = manipulation / sweep (reversal signal).
    """
    for price in (candle_open, candle_high, candle_low, candle_close, boundary_price):
        if not isfinite(price):
            raise ValueError("All prices must be finite")

    if candle_low > candle_high:
        raise ValueError("candle_low must be less than or equal to candle_high")
    if not (candle_low <= candle_open <= candle_high and candle_low <= candle_close <= candle_high):
        raise ValueError("open and close prices must fall within the low-high range")
    if boundary_type not in ("HIGH", "LOW"):
        raise ValueError("boundary_type must be 'HIGH' or 'LOW'")

    if boundary_type == "HIGH":
        tested = candle_high > boundary_price
        if not tested:
            interaction_type = "UNREACHED"
        elif candle_close > boundary_price:
            interaction_type = "DISPLACEMENT"
        else:
            interaction_type = "MANIPULATION_SWEEP"
    else:
        tested = candle_low < boundary_price
        if not tested:
            interaction_type = "UNREACHED"
        elif candle_close < boundary_price:
            interaction_type = "DISPLACEMENT"
        else:
            interaction_type = "MANIPULATION_SWEEP"

    return BoundaryInteraction(
        boundary_type=boundary_type,
        boundary_price=boundary_price,
        tested=tested,
        interaction_type=interaction_type,
    )

