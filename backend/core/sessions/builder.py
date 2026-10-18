"""
builder.py
Builds and populates trading sessions (ASIA, LONDON, NEWYORK) and calculates
their high/low price ranges for the SMTE sessions table.

Beginner note on trading sessions:
  In Forex / SMC:
  1. ASIA (Tokyo / Asian Range):
     Often acts as the baseline consolidation or liquidity range of the day.
     Default window: 00:00 - 08:00 UTC.

  2. LONDON:
     High volatility open. Often manipulates or sweeps the Asian high or low
     before establishing the true intraday direction (London Judases / sweeps).
     Default window: 07:00 - 16:00 UTC.

  3. NEWYORK:
     Overlaps with London (12:00 - 16:00 UTC) providing maximum daily volume,
     followed by afternoon continuation or reversal.
     Default window: 12:00 - 21:00 UTC.

  Storing these windows allows the confluence engine (v4) to score whether
  a setup took place during high-probability institutional killzones.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from app.models.models import Candle, TradingSession


# Default UTC session windows: (start_time, end_time)
DEFAULT_SESSIONS: Dict[str, Tuple[time, time]] = {
    "ASIA": (time(0, 0), time(8, 0)),
    "LONDON": (time(7, 0), time(16, 0)),
    "NEWYORK": (time(12, 0), time(21, 0)),
}


@dataclass
class SessionData:
    session_date: date
    session_name: str
    start_time: datetime
    end_time: datetime
    session_high: float
    session_low: float


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


def build_sessions_from_candles(
    candles: List[Any],
    session_definitions: Optional[Dict[str, Tuple[time, time]]] = None,
) -> List[SessionData]:
    """
    Pure logic: groups candles by day and session, calculating the exact
    start_time, end_time, session_high, and session_low for each active session.
    """
    if not candles:
        return []

    if session_definitions is None:
        session_definitions = DEFAULT_SESSIONS

    # Group candles by calendar date (UTC)
    day_candles = defaultdict(list)
    for c in candles:
        open_time = _normalize_time(_get_val(c, "open_time", "time", "date"))
        high = float(_get_val(c, "high"))
        low = float(_get_val(c, "low"))
        c_date = open_time.date()
        day_candles[c_date].append((open_time, high, low))

    sessions: List[SessionData] = []

    for c_date, candle_list in sorted(day_candles.items()):
        for name, (s_start_time, s_end_time) in session_definitions.items():
            start_dt = datetime.combine(c_date, s_start_time, tzinfo=timezone.utc)
            end_dt = datetime.combine(c_date, s_end_time, tzinfo=timezone.utc)

            # Collect all candles that opened inside [start_dt, end_dt)
            matching = [
                (h, l)
                for (ot, h, l) in candle_list
                if start_dt <= ot < end_dt
            ]

            if not matching:
                continue

            session_high = max(h for h, _ in matching)
            session_low = min(l for _, l in matching)

            sessions.append(
                SessionData(
                    session_date=c_date,
                    session_name=name.upper(),
                    start_time=start_dt,
                    end_time=end_dt,
                    session_high=session_high,
                    session_low=session_low,
                )
            )

    return sessions


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


def _to_date(val: Any) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val[:10])
    raise TypeError(f"Cannot convert {type(val)} to date: {val}")


def _times_equal(t1: Any, t2: Any) -> bool:
    if t1 is None and t2 is None:
        return True
    if t1 is None or t2 is None:
        return False
    try:
        dt1 = datetime.fromisoformat(str(t1)) if isinstance(t1, str) else t1
        dt2 = datetime.fromisoformat(str(t2)) if isinstance(t2, str) else t2
        return _normalize_time(dt1) == _normalize_time(dt2)
    except Exception:
        return str(t1) == str(t2)


def _floats_equal(f1: Any, f2: Any, tol: float = 1e-7) -> bool:
    if f1 is None and f2 is None:
        return True
    if f1 is None or f2 is None:
        return False
    return abs(float(f1) - float(f2)) < tol


def populate_sessions(
    db,
    instrument_id: int,
    timeframe: str = "M15",
    lookback: int = 25000,
    session_definitions: Optional[Dict[str, Tuple[time, time]]] = None,
) -> int:
    """
    Scans candles for the given instrument, computes session high/low ranges,
    and inserts or updates records in the `sessions` table.

    Returns the number of new/updated TradingSession rows.
    """
    candles = _fetch_candles(db, instrument_id, timeframe, lookback)
    if not candles:
        return 0

    session_data_list = build_sessions_from_candles(candles, session_definitions)
    if not session_data_list:
        return 0

    # Load existing sessions for this instrument to perform fast upsert
    existing_sessions = (
        db.query(TradingSession)
        .filter(TradingSession.instrument_id == instrument_id)
        .all()
    )
    # Index by (session_date, session_name)
    existing_map = {
        (
            _to_date(s.session_date),
            s.session_name.upper(),
        ): s
        for s in existing_sessions
    }

    modified_count = 0

    for s_data in session_data_list:
        key = (s_data.session_date, s_data.session_name)
        if key in existing_map:
            record = existing_map[key]
            changed = False
            if not _floats_equal(record.session_high, s_data.session_high):
                record.session_high = s_data.session_high
                changed = True
            if not _floats_equal(record.session_low, s_data.session_low):
                record.session_low = s_data.session_low
                changed = True
            if not _times_equal(record.start_time, s_data.start_time):
                record.start_time = s_data.start_time
                changed = True
            if not _times_equal(record.end_time, s_data.end_time):
                record.end_time = s_data.end_time
                changed = True
            if changed:
                modified_count += 1
        else:
            record = TradingSession(
                instrument_id=instrument_id,
                session_date=s_data.session_date,
                session_name=s_data.session_name,
                start_time=s_data.start_time,
                end_time=s_data.end_time,
                session_high=s_data.session_high,
                session_low=s_data.session_low,
            )
            db.add(record)
            existing_map[key] = record
            modified_count += 1

    db.commit()
    return modified_count
