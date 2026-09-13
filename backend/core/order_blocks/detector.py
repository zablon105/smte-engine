"""
detector.py
Order block detection for SMTE.

Beginner note on the concept:
  A BULLISH order block is the last DOWN candle before a strong,
  decisive UP move away from it. The idea: that down candle is
  where institutions were likely still accumulating buy orders
  right before price reversed - so if price returns to that
  candle's range later, it's expected to react (bounce) again.

  A BEARISH order block is the mirror: the last UP candle before
  a strong decisive DOWN move.

  "Strong move away" here means the next candle's range is
  meaningfully larger than the order block candle's own range -
  a rough proxy for a decisive, impulsive move rather than a
  gradual drift.
"""

from sqlalchemy import select
from app.models.models import Candle, OrderBlock


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


def _block_already_exists(db, instrument_id: int, timeframe: str, formed_at) -> bool:
    return (
        db.query(OrderBlock)
        .filter_by(instrument_id=instrument_id, timeframe=timeframe, formed_at=formed_at)
        .first()
        is not None
    )


def detect_order_blocks(
    db,
    instrument_id: int,
    timeframe: str,
    lookback: int = 500,
    impulse_multiplier: float = 1.5,
) -> int:
    """
    Scans candles for order blocks: the last opposite-direction
    candle before a strong impulsive move.

    `impulse_multiplier`: the next candle's range must be at least
    this many times the order-block candle's own range to count as
    a "strong" move (filters out gradual, low-conviction drifts).

    Returns the number of NEW order block rows created.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    created_count = 0

    if len(candles) < 2:
        return 0

    for i in range(len(candles) - 1):
        candle = candles[i]
        next_candle = candles[i + 1]

        candle_range = float(candle.high) - float(candle.low)
        next_range = float(next_candle.high) - float(next_candle.low)

        if candle_range == 0:
            continue  # avoid division by zero on flat candles

        is_impulsive = next_range >= candle_range * impulse_multiplier

        candle_is_down = candle.close < candle.open
        candle_is_up = candle.close > candle.open
        next_is_up = next_candle.close > next_candle.open
        next_is_down = next_candle.close < next_candle.open

        block_type = None
        if candle_is_down and next_is_up and is_impulsive:
            block_type = "BULLISH"
        elif candle_is_up and next_is_down and is_impulsive:
            block_type = "BEARISH"

        if block_type is None:
            continue

        if _block_already_exists(db, instrument_id, timeframe, candle.open_time):
            continue

        block = OrderBlock(
            instrument_id=instrument_id,
            timeframe=timeframe,
            block_type=block_type,
            high_price=candle.high,
            low_price=candle.low,
            formed_at=candle.open_time,
            is_mitigated=False,
        )
        db.add(block)
        created_count += 1

    db.commit()
    return created_count


def mark_mitigated_blocks(
    db, instrument_id: int, timeframe: str, penetration_pct: float = 0.5
) -> int:
    """
    Checks all currently un-mitigated order blocks and marks them as
    mitigated only if a later candle CLOSES back into at least
    `penetration_pct` of the block's range (default 50%) - not
    merely wicks through it. A close is a much stronger signal that
    price genuinely absorbed the order flow in that zone, rather
    than just briefly overlapping it.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback=2000)
    blocks = (
        db.query(OrderBlock)
        .filter_by(instrument_id=instrument_id, timeframe=timeframe, is_mitigated=False)
        .all()
    )
    mitigated_count = 0

    for block in blocks:
        block_high = float(block.high_price)
        block_low = float(block.low_price)
        block_range = block_high - block_low
        if block_range == 0:
            continue

        if block.block_type == "BULLISH":
            threshold = block_high - (block_range * penetration_pct)
        else:
            threshold = block_low + (block_range * penetration_pct)

        for candle in candles:
            if candle.open_time <= block.formed_at:
                continue

            close_price = float(candle.close)
            if block.block_type == "BULLISH" and close_price < threshold:
                block.is_mitigated = True
                block.mitigated_at = candle.open_time
                mitigated_count += 1
                break
            elif block.block_type == "BEARISH" and close_price > threshold:
                block.is_mitigated = True
                block.mitigated_at = candle.open_time
                mitigated_count += 1
                break

    db.commit()
    return mitigated_count