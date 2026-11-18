"""Non-executing CRT target calculations."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CRTTargets:
    first: float
    second: float


def calculate_crt_targets(
    range_low: float,
    range_high: float,
    direction: Literal["BULLISH", "BEARISH"],
) -> CRTTargets:
    """Return the CRT midpoint target and opposing range-boundary target."""
    if range_low >= range_high:
        raise ValueError("range_low must be less than range_high")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    midpoint = (range_low + range_high) / 2
    opposing_edge = range_high if direction == "BULLISH" else range_low
    return CRTTargets(first=midpoint, second=opposing_edge)
