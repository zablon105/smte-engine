"""
detector.py
Liquidity zone detection for SMTE.

Beginner note on the concept:
  Retail traders place stop-losses and pending orders just beyond
  swing highs/lows. When price touches the SAME high/low level
  more than once (an "equal high" or "equal low"), it means there's
  likely a cluster of orders sitting just beyond that level - a
  pool of liquidity. Smart money often pushes price into these
  pools (sweeping them) before reversing.

  This version CLUSTERS nearby swing points together (instead of
  comparing every pair against every other pair), so each real
  liquidity level produces ONE zone, not dozens of overlapping
  near-duplicates.
"""

from sqlalchemy import select
from app.models.models import Candle, LiquidityZone


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


def _true_pip_size(digits: int, point: float) -> float:
    """
    Converts MT5's raw 'point' value into a real pip size.
    5-digit and 3-digit brokers quote in fractional pips, so their
    point is 1/10th of a real pip. 4-digit and 2-digit brokers quote
    directly in pips, so point == pip.
    """
    if digits in (3, 5):
        return point * 10
    return point


def _zone_already_exists(db, instrument_id: int, timeframe: str, zone_type: str, price_level: float, tolerance: float) -> bool:
    existing = (
        db.query(LiquidityZone)
        .filter(
            LiquidityZone.instrument_id == instrument_id,
            LiquidityZone.timeframe == timeframe,
            LiquidityZone.zone_type == zone_type,
            LiquidityZone.price_level.between(price_level - tolerance, price_level + tolerance),
        )
        .first()
    )
    return existing is not None


def _cluster_swings(swing_points, price_attr: str, tolerance: float):
    """
    Groups swing points into clusters of "equal" levels.
    Sorts by price, then walks through grouping any points within
    `tolerance` of the current cluster's starting price into the
    same cluster. Only clusters with 2+ touches count as real
    liquidity (a single touch isn't "equal highs/lows").

    Returns a list of (representative_candle, touch_count) tuples,
    one per cluster with 2+ touches.
    """
    sorted_points = sorted(swing_points, key=lambda c: getattr(c, price_attr))
    clusters = []
    current_cluster = []

    for candle in sorted_points:
        price = float(getattr(candle, price_attr))
        if not current_cluster:
            current_cluster = [candle]
            continue
        cluster_start_price = float(getattr(current_cluster[0], price_attr))
        if abs(price - cluster_start_price) <= tolerance:
            current_cluster.append(candle)
        else:
            if len(current_cluster) >= 2:
                # use the most recent candle in the cluster as the reference point
                representative = max(current_cluster, key=lambda c: c.open_time)
                clusters.append((representative, len(current_cluster)))
            current_cluster = [candle]

    if len(current_cluster) >= 2:
        representative = max(current_cluster, key=lambda c: c.open_time)
        clusters.append((representative, len(current_cluster)))

    return clusters


def detect_liquidity_zones(
    db,
    instrument_id: int,
    timeframe: str,
    lookback: int = 500,
    equal_tolerance_pips: float = 3.0,
    digits: int = 5,
    point: float = 0.00001,
) -> int:
    """
    Scans candles for clustered equal highs (SELL_SIDE liquidity)
    and equal lows (BUY_SIDE liquidity).

    Returns the number of NEW liquidity zone rows created.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    true_pip = _true_pip_size(digits, point)
    tolerance = equal_tolerance_pips * true_pip
    created_count = 0

    if len(candles) < 3:
        return 0

    swing_highs = []
    swing_lows = []
    for i in range(1, len(candles) - 1):
        prev_c, curr_c, next_c = candles[i - 1], candles[i], candles[i + 1]
        if curr_c.high > prev_c.high and curr_c.high > next_c.high:
            swing_highs.append(curr_c)
        if curr_c.low < prev_c.low and curr_c.low < next_c.low:
            swing_lows.append(curr_c)

    for representative, touch_count in _cluster_swings(swing_highs, "high", tolerance):
        price_level = float(representative.high)
        if _zone_already_exists(db, instrument_id, timeframe, "SELL_SIDE", price_level, tolerance):
            continue
        zone = LiquidityZone(
            instrument_id=instrument_id,
            timeframe=timeframe,
            zone_type="SELL_SIDE",
            price_level=price_level,
            formed_at=representative.open_time,
            is_swept=False,
            strength_score=min(touch_count, 10),  # more touches = stronger pool, capped at 10
        )
        db.add(zone)
        created_count += 1

    for representative, touch_count in _cluster_swings(swing_lows, "low", tolerance):
        price_level = float(representative.low)
        if _zone_already_exists(db, instrument_id, timeframe, "BUY_SIDE", price_level, tolerance):
            continue
        zone = LiquidityZone(
            instrument_id=instrument_id,
            timeframe=timeframe,
            zone_type="BUY_SIDE",
            price_level=price_level,
            formed_at=representative.open_time,
            is_swept=False,
            strength_score=min(touch_count, 10),
        )
        db.add(zone)
        created_count += 1

    db.commit()
    return created_count


def mark_swept_zones(db, instrument_id: int, timeframe: str) -> int:
    """
    Checks all currently un-swept liquidity zones and marks them as
    swept if a later candle has traded through that price level.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback=2000)
    zones = (
        db.query(LiquidityZone)
        .filter_by(instrument_id=instrument_id, timeframe=timeframe, is_swept=False)
        .all()
    )
    swept_count = 0

    for zone in zones:
        for candle in candles:
            if candle.open_time <= zone.formed_at:
                continue
            if zone.zone_type == "SELL_SIDE" and float(candle.high) > float(zone.price_level):
                zone.is_swept = True
                zone.swept_at = candle.open_time
                swept_count += 1
                break
            elif zone.zone_type == "BUY_SIDE" and float(candle.low) < float(zone.price_level):
                zone.is_swept = True
                zone.swept_at = candle.open_time
                swept_count += 1
                break

    db.commit()
    return swept_count