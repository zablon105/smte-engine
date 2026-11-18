"""Non-executing Turtle Soup (false breakout / purge) calculations."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class TurtleSoupTargets:
    midpoint_tp1: float
    opposing_edge_tp2: float
    invalidation_stop: float


@dataclass(frozen=True)
class TurtleSoupEvaluation:
    is_valid: bool
    soup_type: Literal["TBS", "TWS", "NONE"]
    direction: Literal["BULLISH", "BEARISH"]
    targets: TurtleSoupTargets


def calculate_turtle_soup_targets(
    range_low: float,
    range_high: float,
    manipulation_extreme: float,
    direction: Literal["BULLISH", "BEARISH"],
) -> TurtleSoupTargets:
    """Calculate the 50% midpoint target, opposing range boundary, and stop loss.

    According to research notes (Turtle Soup / 22CRT):
    - Target 1: 50% midpoint of the original candle's range.
    - Target 2: 100% opposing edge of the range.
    - Invalidation stop: Extreme point reached by the manipulation/purge wick.
    """
    for price, label in (
        (range_low, "range_low"),
        (range_high, "range_high"),
        (manipulation_extreme, "manipulation_extreme"),
    ):
        if not isfinite(price):
            raise ValueError(f"{label} must be finite")

    if range_low >= range_high:
        raise ValueError("range_low must be strictly less than range_high")
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    midpoint = (range_low + range_high) / 2.0
    if direction == "BULLISH":
        opposing_edge = range_high
        if manipulation_extreme > range_low:
            raise ValueError("Bullish manipulation extreme must be <= range_low")
    else:
        opposing_edge = range_low
        if manipulation_extreme < range_high:
            raise ValueError("Bearish manipulation extreme must be >= range_high")

    return TurtleSoupTargets(
        midpoint_tp1=midpoint,
        opposing_edge_tp2=opposing_edge,
        invalidation_stop=manipulation_extreme,
    )


def evaluate_turtle_soup_sequence(
    c1_high: float,
    c1_low: float,
    c2_open: float,
    c2_close: float,
    c2_high: float,
    c2_low: float,
    c3_close: float,
    direction: Literal["BULLISH", "BEARISH"],
) -> TurtleSoupEvaluation:
    """Evaluate a 3-candle sequence for a Turtle Soup setup.

    - Candle 1 establishes the baseline range.
    - Candle 2 purges beyond the level:
        - Turtle Body Soup (TBS): Candle 2 closes beyond the level.
        - Turtle Wick Soup (TWS): Candle 2 wicks beyond the level but closes inside.
    - Candle 3 confirms reversal by trading back inside Candle 1's range.
    """
    for price in (c1_high, c1_low, c2_open, c2_close, c2_high, c2_low, c3_close):
        if not isfinite(price):
            raise ValueError("All prices must be finite")

    if c1_low >= c1_high:
        # Flat/zero-range candle cannot form a valid range baseline
        return TurtleSoupEvaluation(
            is_valid=False,
            soup_type="NONE",
            direction=direction,
            targets=TurtleSoupTargets(
                midpoint_tp1=0.0,
                opposing_edge_tp2=0.0,
                invalidation_stop=0.0,
            ),
        )
    if direction not in ("BULLISH", "BEARISH"):
        raise ValueError("direction must be 'BULLISH' or 'BEARISH'")

    soup_type: Literal["TBS", "TWS", "NONE"] = "NONE"
    is_valid = False

    if direction == "BULLISH":
        # Purge below c1_low
        has_purge = c2_low < c1_low
        if has_purge:
            if c2_close < c1_low:
                soup_type = "TBS"
            else:
                soup_type = "TWS"

            # Candle 3 confirmation: closes back above c1_low and inside c1 range
            if c3_close > c1_low and c3_close <= c1_high:
                is_valid = True

        targets = calculate_turtle_soup_targets(
            range_low=c1_low,
            range_high=c1_high,
            manipulation_extreme=min(c2_low, c1_low),
            direction="BULLISH",
        )
    else:
        # Purge above c1_high
        has_purge = c2_high > c1_high
        if has_purge:
            if c2_close > c1_high:
                soup_type = "TBS"
            else:
                soup_type = "TWS"

            # Candle 3 confirmation: closes back below c1_high and inside c1 range
            if c3_close < c1_high and c3_close >= c1_low:
                is_valid = True

        targets = calculate_turtle_soup_targets(
            range_low=c1_low,
            range_high=c1_high,
            manipulation_extreme=max(c2_high, c1_high),
            direction="BEARISH",
        )

    return TurtleSoupEvaluation(
        is_valid=is_valid,
        soup_type=soup_type if is_valid else "NONE",
        direction=direction,
        targets=targets,
    )

