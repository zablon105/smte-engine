"""Non-executing Breaker Block calculations and zone validation."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Optional


@dataclass(frozen=True)
class BreakerZone:
    bottom: float
    top: float
    direction: Literal["BULLISH", "BEARISH"]
    mean_threshold: float
    use_body: bool


def calculate_breaker_zone(
    open_price: float,
    close_price: float,
    high_price: float,
    low_price: float,
    direction: Literal["BULLISH", "BEARISH"],
    use_body: bool = True,
    min_body_ratio: float = 0.20,
) -> BreakerZone:
    """Calculate the zone boundaries and mean threshold for a breaker candle.

    According to research notes:
    - Bullish breaker: up-close candle in the most recent swing high prior to an
      old low being violated.
    - Bearish breaker: down-close candle in the most recent swing low prior to an
      old high being violated.
    - Zone sizing: Use body (open to close) unless the body is very small relative
      to the full candle range, in which case the full candle range is used.
    """
    for price, label in (
        (open_price, "open_price"),
        (close_price, "close_price"),
        (high_price, "high_price"),
        (low_price, "low_price"),
    ):
        if not isfinite(price):
            raise ValueError(f"{label} must be finite")

    if low_price > high_price:
        raise ValueError("low_price must be less than or equal to high_price")
    if not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
        raise ValueError("open and close prices must fall within the low-high range")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    total_range = high_price - low_price
    body_low = min(open_price, close_price)
    body_high = max(open_price, close_price)
    body_range = body_high - body_low

    body_ratio = (body_range / total_range) if total_range > 0 else 1.0
    effective_use_body = use_body and (body_ratio >= min_body_ratio)

    if effective_use_body:
        bottom = body_low
        top = body_high
    else:
        bottom = low_price
        top = high_price

    mean_threshold = (bottom + top) / 2.0
    return BreakerZone(
        bottom=bottom,
        top=top,
        direction=direction,
        mean_threshold=mean_threshold,
        use_body=effective_use_body,
    )


def is_breaker_mitigated(
    zone: BreakerZone,
    current_low: float,
    current_high: float,
) -> bool:
    """Check if price has entered/tapped into the breaker zone."""
    if not isfinite(current_low) or not isfinite(current_high):
        raise ValueError("Current prices must be finite")
    if current_low > current_high:
        raise ValueError("current_low must be less than or equal to current_high")

    return not (current_high < zone.bottom or current_low > zone.top)


def validate_breaker_break(
    swing_extreme: float,
    break_candle_close: float,
    direction: Literal["BULLISH", "BEARISH"],
) -> bool:
    """Validate whether subsequent price action broke through the swing extreme.

    - Bullish breaker is confirmed when price breaks ABOVE the swing high that
      contained the breaker candle.
    - Bearish breaker is confirmed when price breaks BELOW the swing low that
      contained the breaker candle.
    """
    if not isfinite(swing_extreme) or not isfinite(break_candle_close):
        raise ValueError("Prices must be finite")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    if direction == "BULLISH":
        return break_candle_close > swing_extreme
    return break_candle_close < swing_extreme

