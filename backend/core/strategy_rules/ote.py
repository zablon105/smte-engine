"""Non-executing OTE retracement calculations."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


OTE_LOWER_RETRACEMENT = 0.62
OTE_UPPER_RETRACEMENT = 0.79
OTE_SWEET_SPOT_RETRACEMENT = 0.705


@dataclass(frozen=True)
class OTEZone:
    low: float
    high: float
    sweet_spot: float


def calculate_ote_zone(
    swing_low: float,
    swing_high: float,
    direction: Literal["BULLISH", "BEARISH"],
) -> OTEZone:
    """Calculate the 62%-79% retracement zone of caller-selected swing anchors.

    Bullish retracements are measured down from the swing high; bearish
    retracements are measured up from the swing low. This function does not
    select swing points or place/execute orders.
    """
    if not isfinite(swing_low) or not isfinite(swing_high):
        raise ValueError("Swing prices must be finite")
    if swing_low >= swing_high:
        raise ValueError("swing_low must be less than swing_high")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    leg_size = swing_high - swing_low
    if direction == "BULLISH":
        return OTEZone(
            low=swing_high - OTE_UPPER_RETRACEMENT * leg_size,
            high=swing_high - OTE_LOWER_RETRACEMENT * leg_size,
            sweet_spot=swing_high - OTE_SWEET_SPOT_RETRACEMENT * leg_size,
        )

    return OTEZone(
        low=swing_low + OTE_LOWER_RETRACEMENT * leg_size,
        high=swing_low + OTE_UPPER_RETRACEMENT * leg_size,
        sweet_spot=swing_low + OTE_SWEET_SPOT_RETRACEMENT * leg_size,
    )
