"""
detector.py
Market structure detection (Swing High/Low, BOS, CHOCH) for SMTE.

Beginner note on the concept:
  In Smart Money Concepts (SMC):
  1. SWING POINTS:
     - Swing High: A peak candle whose high is higher than surrounding candles.
     - Swing Low: A valley candle whose low is lower than surrounding candles.

  2. BOS (Break of Structure):
     - BULLISH BOS: When in an uptrend, a candle closes ABOVE the previous
       unbroken Swing High (Higher High continuation).
     - BEARISH BOS: When in a downtrend, a candle closes BELOW the previous
       unbroken Swing Low (Lower Low continuation).
     BOS represents trend continuation.

  3. CHOCH (Change of Character):
     - BULLISH CHOCH: When in a downtrend, a candle closes ABOVE the previous
       Lower High. This marks a structural shift from bearish to bullish.
     - BEARISH CHOCH: When in an uptrend, a candle closes BELOW the previous
       Higher Low. This marks a structural shift from bullish to bearish.
     CHOCH represents trend reversal / early warning of trend change.

  Each swing point is broken at most once (avoiding duplicate events during
  multi-candle impulse moves).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Union

from sqlalchemy import select
from app.models.models import Candle, MarketStructure


@dataclass
class MarketStructureEvent:
    event_type: str       # "BOS" or "CHOCH"
    direction: str        # "BULLISH" or "BEARISH"
    swing_price: float    # Price level of the swing that was broken
    break_price: float    # Closing price of the candle confirming the break
    occurred_at: Any      # Timestamp of the candle confirming the break
    candle_index: int     # Index in the provided candle sequence


def _get_val(c: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(c, dict) and key in c:
            return c[key]
        elif hasattr(c, key):
            return getattr(c, key)
    raise KeyError(f"None of {keys} found in candle {c}")


def _fetch_candles(db, instrument_id: int, timeframe: str, lookback: int):
    """
    Returns the most recent `lookback` candles for an instrument/timeframe,
    ordered oldest -> newest.
    """
    stmt = (
        select(Candle)
        .where(Candle.instrument_id == instrument_id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(lookback)
    )
    candles = db.execute(stmt).scalars().all()
    candles.reverse()  # oldest -> newest
    return candles


def _structure_already_exists(
    db,
    instrument_id: int,
    timeframe: str,
    event_type: str,
    direction: str,
    occurred_at: datetime,
) -> bool:
    existing = (
        db.query(MarketStructure)
        .filter(
            MarketStructure.instrument_id == instrument_id,
            MarketStructure.timeframe == timeframe,
            MarketStructure.event_type == event_type,
            MarketStructure.direction == direction,
            MarketStructure.occurred_at == occurred_at,
        )
        .first()
    )
    return existing is not None


def detect_structure_events(
    candles: List[Any],
    swing_length: int = 2,
) -> List[MarketStructureEvent]:
    """
    Pure detection logic: scans a chronological list of candles
    and identifies swing points, BOS, and CHOCH events without lookahead bias.

    `swing_length`: number of candles on each side required to confirm
    a swing high or swing low (default 2, meaning 2 lower highs on each side).
    """
    if len(candles) < (2 * swing_length + 1):
        return []

    highs = [float(_get_val(c, "high")) for c in candles]
    lows = [float(_get_val(c, "low")) for c in candles]
    closes = [float(_get_val(c, "close")) for c in candles]
    times = [_get_val(c, "open_time", "time", "date") for c in candles]

    events: List[MarketStructureEvent] = []

    current_trend: Optional[str] = None  # "BULLISH" or "BEARISH"
    active_swing_high: Optional[dict] = None
    active_swing_low: Optional[dict] = None

    total_candles = len(candles)

    for j in range(total_candles):
        # 1. Register confirmed swing points at index i = j - swing_length
        if j >= 2 * swing_length:
            i = j - swing_length

            # Check for Swing High at i
            is_swing_high = all(
                highs[i] > highs[i - k] and highs[i] > highs[i + k]
                for k in range(1, swing_length + 1)
            )
            if is_swing_high:
                active_swing_high = {
                    "price": highs[i],
                    "time": times[i],
                    "index": i,
                    "broken": False,
                }

            # Check for Swing Low at i
            is_swing_low = all(
                lows[i] < lows[i - k] and lows[i] < lows[i + k]
                for k in range(1, swing_length + 1)
            )
            if is_swing_low:
                active_swing_low = {
                    "price": lows[i],
                    "time": times[i],
                    "index": i,
                    "broken": False,
                }

        # 2. Check if current candle j breaks the active swing high
        if active_swing_high is not None and not active_swing_high["broken"]:
            if closes[j] > active_swing_high["price"]:
                if current_trend == "BULLISH":
                    event_type = "BOS"
                else:
                    event_type = "CHOCH"
                    current_trend = "BULLISH"

                events.append(
                    MarketStructureEvent(
                        event_type=event_type,
                        direction="BULLISH",
                        swing_price=active_swing_high["price"],
                        break_price=closes[j],
                        occurred_at=times[j],
                        candle_index=j,
                    )
                )
                active_swing_high["broken"] = True

        # 3. Check if current candle j breaks the active swing low
        if active_swing_low is not None and not active_swing_low["broken"]:
            if closes[j] < active_swing_low["price"]:
                if current_trend == "BEARISH":
                    event_type = "BOS"
                else:
                    event_type = "CHOCH"
                    current_trend = "BEARISH"

                events.append(
                    MarketStructureEvent(
                        event_type=event_type,
                        direction="BEARISH",
                        swing_price=active_swing_low["price"],
                        break_price=closes[j],
                        occurred_at=times[j],
                        candle_index=j,
                    )
                )
                active_swing_low["broken"] = True

    return events


def detect_market_structure(
    db,
    instrument_id: int,
    timeframe: str,
    lookback: int = 500,
    swing_length: int = 2,
) -> int:
    """
    Fetches candles for the given instrument and timeframe, detects
    BOS and CHOCH events, and stores newly identified events in PostgreSQL.

    Returns the number of new MarketStructure rows created.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    if len(candles) < (2 * swing_length + 1):
        return 0

    events = detect_structure_events(candles, swing_length=swing_length)
    created_count = 0

    for event in events:
        if _structure_already_exists(
            db,
            instrument_id,
            timeframe,
            event.event_type,
            event.direction,
            event.occurred_at,
        ):
            continue

        record = MarketStructure(
            instrument_id=instrument_id,
            timeframe=timeframe,
            event_type=event.event_type,
            direction=event.direction,
            swing_price=event.swing_price,
            break_price=event.break_price,
            occurred_at=event.occurred_at,
        )
        db.add(record)
        created_count += 1

    db.commit()
    return created_count

