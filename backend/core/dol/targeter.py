"""
targeter.py
Draw on Liquidity (DOL) targeting engine for SMTE.

Beginner note on Draw on Liquidity (DOL):
  In Smart Money Concepts (SMC):
  Price does not move aimlessly - it is systematically drawn towards pools
  of liquidity (resting buy stops above swing highs / sell stops below swing lows).

  - When smart money accumulates long positions (e.g. via a Bullish CRT or sweep),
    the primary target (Draw on Liquidity) is the opposing BUY_SIDE liquidity pool
    (equal highs, session highs, or previous day/week highs).
  - When smart money distributes short positions, the primary target is the
    opposing SELL_SIDE liquidity pool (equal lows, session lows, etc.).

  This module:
  1. Identifies and registers active DOL targets from unswept liquidity zones.
  2. Updates and resolves targets when price reaches them (`reached_at`).
  3. Provides `find_active_dol()` to supply high-probability profit targets.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import and_, select
from app.models.models import Candle, DolTarget, LiquidityZone


def _fetch_candles(db, instrument_id: int, timeframe: str, lookback: int):
    stmt = (
        select(Candle)
        .where(Candle.instrument_id == instrument_id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(lookback)
    )
    candles = db.execute(stmt).scalars().all()
    candles.reverse()
    return candles


def identify_dol_targets(
    db,
    instrument_id: int,
    timeframe: str = "H1",
) -> int:
    """
    Scans liquidity zones and registers any active (unswept) zone
    as a DolTarget if it doesn't already have one.

    Returns the number of new DolTarget records created.
    """
    zones = (
        db.query(LiquidityZone)
        .filter(
            LiquidityZone.instrument_id == instrument_id,
            LiquidityZone.timeframe == timeframe,
        )
        .all()
    )

    created_count = 0
    for zone in zones:
        existing = (
            db.query(DolTarget)
            .filter_by(
                instrument_id=instrument_id,
                timeframe=timeframe,
                liquidity_zone_id=zone.id,
            )
            .first()
        )
        if existing is not None:
            continue

        target = DolTarget(
            instrument_id=instrument_id,
            timeframe=timeframe,
            target_price=zone.price_level,
            liquidity_zone_id=zone.id,
            identified_at=zone.formed_at,
            reached_at=zone.swept_at if zone.is_swept else None,
            is_active=not zone.is_swept,
        )
        db.add(target)
        created_count += 1

    db.commit()
    return created_count


def update_dol_targets(
    db,
    instrument_id: int,
    timeframe: str = "M15",
    lookback: int = 1000,
) -> int:
    """
    Checks active DolTargets against recent candle data to determine
    if price has reached the target, updating `reached_at` and setting
    `is_active = False`.
    """
    active_targets = (
        db.query(DolTarget)
        .filter_by(instrument_id=instrument_id, is_active=True)
        .all()
    )
    if not active_targets:
        return 0

    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    if not candles:
        return 0

    updated_count = 0
    for target in active_targets:
        target_price = float(target.target_price)
        for candle in candles:
            if candle.open_time <= target.identified_at:
                continue

            high = float(candle.high)
            low = float(candle.low)

            if low <= target_price <= high:
                target.is_active = False
                target.reached_at = candle.open_time
                updated_count += 1
                break

    db.commit()
    return updated_count


def find_active_dol(
    db,
    instrument_id: int,
    signal_direction: str,
    current_price: float,
    as_of_time: Optional[datetime] = None,
    timeframes: tuple = ("H1", "H4"),
) -> Optional[float]:
    """
    Finds the nearest valid active Draw on Liquidity target price
    in the direction of the trade:
      - For "BUY": Nearest target above current_price
      - For "SELL": Nearest target below current_price

    Returns the target price float, or None if no active DOL is found.
    """
    query = (
        db.query(DolTarget)
        .filter(
            DolTarget.instrument_id == instrument_id,
            DolTarget.timeframe.in_(timeframes),
        )
    )

    if as_of_time is not None:
        # Target must have been identified before as_of_time and not reached before as_of_time
        query = query.filter(
            DolTarget.identified_at < as_of_time,
            (DolTarget.reached_at.is_(None) | (DolTarget.reached_at > as_of_time)),
        )
    else:
        query = query.filter(DolTarget.is_active == True)

    targets = query.all()
    if not targets:
        return None

    if signal_direction in ("BUY", "BULLISH"):
        candidates = [float(t.target_price) for t in targets if float(t.target_price) > current_price]
        return min(candidates) if candidates else None
    else:
        candidates = [float(t.target_price) for t in targets if float(t.target_price) < current_price]
        return max(candidates) if candidates else None
