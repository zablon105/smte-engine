"""
detector.py
SMT (Smart Money Tool / Technique) Divergence detection for SMTE.

Beginner note on SMT Divergence:
  In Smart Money Concepts (SMC):
  Positively correlated pairs (like EURUSD and GBPUSD, or AUDUSD and NZDUSD)
  should generally move in tandem. When they diverge at swing extremes, it reveals
  institutional accumulation or distribution:

  1. BULLISH SMT DIVERGENCE:
     - Pair A sweeps sell-side liquidity by forming a LOWER LOW (LL),
       while Pair B forms a HIGHER LOW (HL) (refusing to break lower).
     - Or Pair A forms a HIGHER LOW while Pair B sweeps lower.
     - The non-confirmation indicates that the selloff in Pair A was an engineered
       liquidity sweep and that "smart money" is buying into the move.

  2. BEARISH SMT DIVERGENCE:
     - Pair A sweeps buy-side liquidity by forming a HIGHER HIGH (HH),
       while Pair B forms a LOWER HIGH (LH) (refusing to break higher).
     - Or Pair A forms a LOWER HIGH while Pair B sweeps higher.
     - The non-confirmation indicates that the rally was an engineered
       liquidity grab and that "smart money" is distributing.

  Storing these divergences enables confluence scoring (v4) to give +5 points
  to CRT setups that align with inter-market institutional divergence.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from app.models.models import Candle, Instrument, SmtDivergence


# Default correlated pairs mapping (base currency pairs)
DEFAULT_CORRELATION_PAIRS: Dict[str, List[str]] = {
    "EURUSD": ["GBPUSD", "AUDUSD", "NZDUSD"],
    "GBPUSD": ["EURUSD", "AUDUSD"],
    "AUDUSD": ["NZDUSD", "EURUSD"],
    "NZDUSD": ["AUDUSD", "EURUSD"],
    "USDJPY": ["USDCHF", "USDCAD"],
    "USDCHF": ["USDJPY", "USDCAD"],
    "USDCAD": ["USDCHF", "USDJPY"],
}


@dataclass
class SmtDivergenceEvent:
    divergence_type: str       # "BULLISH" or "BEARISH"
    detected_at: datetime      # Timestamp when divergence was confirmed
    notes: str                 # Contextual explanation of the divergence


def _get_val(c: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(c, dict) and key in c:
            return c[key]
        elif hasattr(c, key):
            return getattr(c, key)
    raise KeyError(f"None of {keys} found in candle {c}")


def _normalize_time(dt: Any) -> datetime:
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    elif isinstance(dt, (int, float)):
        return datetime.fromtimestamp(dt, tz=timezone.utc)
    raise TypeError(f"Unsupported datetime type: {type(dt)}")


def _clean_symbol(symbol: str) -> str:
    """Strips broker suffixes like .m, _i, pro, etc."""
    s = symbol.upper()
    s = re.sub(r"[^A-Z]", "", s)
    # Extract standard 6-char currency pair if present
    if len(s) >= 6:
        return s[:6]
    return s


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


def _smt_already_exists(
    db,
    instrument_id: int,
    correlated_instrument_id: int,
    timeframe: str,
    divergence_type: str,
    detected_at: datetime,
) -> bool:
    existing = (
        db.query(SmtDivergence)
        .filter(
            SmtDivergence.instrument_id == instrument_id,
            SmtDivergence.correlated_instrument_id == correlated_instrument_id,
            SmtDivergence.timeframe == timeframe,
            SmtDivergence.divergence_type == divergence_type,
            SmtDivergence.detected_at == detected_at,
        )
        .first()
    )
    return existing is not None


def _find_swings(candles: List[Any], swing_length: int = 2):
    """Identifies confirmed swing highs and lows in a candle series."""
    if len(candles) < 2 * swing_length + 1:
        return [], []

    highs = [float(_get_val(c, "high")) for c in candles]
    lows = [float(_get_val(c, "low")) for c in candles]
    times = [_normalize_time(_get_val(c, "open_time", "time", "date")) for c in candles]

    swing_highs = []
    swing_lows = []

    for i in range(swing_length, len(candles) - swing_length):
        if all(highs[i] > highs[i - k] and highs[i] > highs[i + k] for k in range(1, swing_length + 1)):
            # Confirmation time is when the rightmost bar closes
            confirm_time = times[i + swing_length]
            swing_highs.append({
                "price": highs[i],
                "time": times[i],
                "confirm_time": confirm_time,
                "index": i,
            })

        if all(lows[i] < lows[i - k] and lows[i] < lows[i + k] for k in range(1, swing_length + 1)):
            confirm_time = times[i + swing_length]
            swing_lows.append({
                "price": lows[i],
                "time": times[i],
                "confirm_time": confirm_time,
                "index": i,
            })

    return swing_highs, swing_lows


def detect_smt_events(
    candles_a: List[Any],
    candles_b: List[Any],
    swing_length: int = 2,
    time_tolerance_hours: float = 4.0,
) -> List[SmtDivergenceEvent]:
    """
    Pure detection logic: compares confirmed swing points between Asset A and Asset B
    to detect Bullish and Bearish SMT divergence.

    `time_tolerance_hours`: maximum time difference between corresponding swings
    in Asset A and Asset B to consider them part of the same market structure move.
    """
    highs_a, lows_a = _find_swings(candles_a, swing_length)
    highs_b, lows_b = _find_swings(candles_b, swing_length)

    events: List[SmtDivergenceEvent] = []
    max_delta = timedelta(hours=time_tolerance_hours)

    # 1. Check for Bullish SMT (comparing consecutive swing lows)
    for i in range(1, len(lows_a)):
        low_a1 = lows_a[i - 1]
        low_a2 = lows_a[i]

        # Find matching swing lows in B for low_a1 and low_a2
        match_b1 = [b for b in lows_b if abs(b["time"] - low_a1["time"]) <= max_delta]
        match_b2 = [b for b in lows_b if abs(b["time"] - low_a2["time"]) <= max_delta]

        if not match_b1 or not match_b2:
            continue

        low_b1 = min(match_b1, key=lambda b: abs(b["time"] - low_a1["time"]))
        low_b2 = min(match_b2, key=lambda b: abs(b["time"] - low_a2["time"]))

        # Check for divergence:
        # Case 1: A makes LL, B makes HL (A swept liquidity)
        # Case 2: A makes HL, B makes LL (A showed relative strength)
        a_lower = low_a2["price"] < low_a1["price"]
        b_lower = low_b2["price"] < low_b1["price"]

        if a_lower and not b_lower:
            detected_at = max(low_a2["confirm_time"], low_b2["confirm_time"])
            events.append(
                SmtDivergenceEvent(
                    divergence_type="BULLISH",
                    detected_at=detected_at,
                    notes=f"Bullish SMT: Asset A made Lower Low ({low_a1['price']:.5f} -> {low_a2['price']:.5f}) while Asset B made Higher Low ({low_b1['price']:.5f} -> {low_b2['price']:.5f}).",
                )
            )
        elif not a_lower and b_lower:
            detected_at = max(low_a2["confirm_time"], low_b2["confirm_time"])
            events.append(
                SmtDivergenceEvent(
                    divergence_type="BULLISH",
                    detected_at=detected_at,
                    notes=f"Bullish SMT: Asset A showed relative strength with Higher Low ({low_a1['price']:.5f} -> {low_a2['price']:.5f}) while Asset B made Lower Low ({low_b1['price']:.5f} -> {low_b2['price']:.5f}).",
                )
            )

    # 2. Check for Bearish SMT (comparing consecutive swing highs)
    for i in range(1, len(highs_a)):
        high_a1 = highs_a[i - 1]
        high_a2 = highs_a[i]

        match_b1 = [b for b in highs_b if abs(b["time"] - high_a1["time"]) <= max_delta]
        match_b2 = [b for b in highs_b if abs(b["time"] - high_a2["time"]) <= max_delta]

        if not match_b1 or not match_b2:
            continue

        high_b1 = min(match_b1, key=lambda b: abs(b["time"] - high_a1["time"]))
        high_b2 = min(match_b2, key=lambda b: abs(b["time"] - high_a2["time"]))

        a_higher = high_a2["price"] > high_a1["price"]
        b_higher = high_b2["price"] > high_b1["price"]

        if a_higher and not b_higher:
            detected_at = max(high_a2["confirm_time"], high_b2["confirm_time"])
            events.append(
                SmtDivergenceEvent(
                    divergence_type="BEARISH",
                    detected_at=detected_at,
                    notes=f"Bearish SMT: Asset A made Higher High ({high_a1['price']:.5f} -> {high_a2['price']:.5f}) while Asset B made Lower High ({high_b1['price']:.5f} -> {high_b2['price']:.5f}).",
                )
            )
        elif not a_higher and b_higher:
            detected_at = max(high_a2["confirm_time"], high_b2["confirm_time"])
            events.append(
                SmtDivergenceEvent(
                    divergence_type="BEARISH",
                    detected_at=detected_at,
                    notes=f"Bearish SMT: Asset A showed relative weakness with Lower High ({high_a1['price']:.5f} -> {high_a2['price']:.5f}) while Asset B made Higher High ({high_b1['price']:.5f} -> {high_b2['price']:.5f}).",
                )
            )

    return events


def detect_smt_divergence(
    db,
    instrument_id: int,
    correlated_instrument_id: int,
    timeframe: str,
    lookback: int = 500,
    swing_length: int = 2,
    time_tolerance_hours: float = 4.0,
) -> int:
    """
    Scans candles between two instruments and records any newly identified
    SMT divergences in PostgreSQL.

    Returns the number of new SmtDivergence rows created.
    """
    if instrument_id == correlated_instrument_id:
        return 0

    candles_a = _fetch_candles(db, instrument_id, timeframe, lookback)
    candles_b = _fetch_candles(db, correlated_instrument_id, timeframe, lookback)

    if not candles_a or not candles_b:
        return 0

    events = detect_smt_events(
        candles_a,
        candles_b,
        swing_length=swing_length,
        time_tolerance_hours=time_tolerance_hours,
    )

    created_count = 0
    for ev in events:
        if _smt_already_exists(
            db,
            instrument_id,
            correlated_instrument_id,
            timeframe,
            ev.divergence_type,
            ev.detected_at,
        ):
            continue

        record = SmtDivergence(
            instrument_id=instrument_id,
            correlated_instrument_id=correlated_instrument_id,
            timeframe=timeframe,
            divergence_type=ev.divergence_type,
            detected_at=ev.detected_at,
            notes=ev.notes,
        )
        db.add(record)
        created_count += 1

    db.commit()
    return created_count


def detect_all_smt_divergences(
    db,
    instrument_id: int,
    timeframe: str,
    lookback: int = 500,
    swing_length: int = 2,
) -> int:
    """
    Automatically discovers configured correlated pairs for the target instrument
    and detects SMT divergence against all available correlated instruments in the database.
    """
    target = db.query(Instrument).filter_by(id=instrument_id).first()
    if target is None:
        return 0

    target_clean = _clean_symbol(target.symbol)
    correlated_names = DEFAULT_CORRELATION_PAIRS.get(target_clean, [])

    if not correlated_names:
        return 0

    all_instruments = db.query(Instrument).all()
    # Find matching instruments by clean symbol name
    candidates = [
        inst for inst in all_instruments
        if inst.id != instrument_id and _clean_symbol(inst.symbol) in correlated_names
    ]

    total_created = 0
    for cand in candidates:
        total_created += detect_smt_divergence(
            db,
            instrument_id=instrument_id,
            correlated_instrument_id=cand.id,
            timeframe=timeframe,
            lookback=lookback,
            swing_length=swing_length,
        )

    return total_created

