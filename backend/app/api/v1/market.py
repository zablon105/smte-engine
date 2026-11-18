"""
market.py
FastAPI router for instruments, live candlestick data, and session killzones.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models.models import Instrument, Candle
from app.schemas.market import InstrumentOut, CandleOut, SessionOut
from app.services import mt5_client
from core.execution.run_scalper import is_market_session_active

router = APIRouter(prefix="/market", tags=["Market Data"])


@router.get("/instruments", response_model=List[InstrumentOut])
def get_instruments(db: Session = Depends(get_db)):
    """
    Returns all registered instruments with live quote data (bid, ask, spread).
    """
    instruments = db.query(Instrument).filter(Instrument.is_active == True).all()
    results = []

    mt5_connected = False
    try:
        mt5_connected = mt5_client.connect()
    except Exception:
        pass

    for inst in instruments:
        bid, ask, spread_pips = None, None, None
        is_open = True

        if mt5_connected:
            tick = mt5_client.get_symbol_tick(inst.symbol)
            if tick:
                bid = round(float(tick.bid), inst.digits)
                ask = round(float(tick.ask), inst.digits)
                pip_val = float(inst.pip_size) if float(inst.pip_size) > 0 else 0.0001
                spread_pips = round((ask - bid) / pip_val, 1)

            is_open = is_market_session_active(inst.symbol)

        results.append(
            InstrumentOut(
                id=inst.id,
                symbol=inst.symbol,
                description=inst.description,
                digits=inst.digits,
                pip_size=float(inst.pip_size),
                contract_size=float(inst.contract_size),
                is_active=inst.is_active,
                bid=bid,
                ask=ask,
                spread_pips=spread_pips,
                is_market_open=is_open,
            )
        )

    return results


@router.get("/candles", response_model=List[CandleOut])
def get_candles(
    symbol: str = Query("EURUSD.m"),
    timeframe: str = Query("M5", pattern="^(M1|M2|M3|M4|M5|M15|M30|H1|H4|D1)$"),
    count: int = Query(100, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    """
    Returns candlestick data formatted for financial charts.
    Tries live MT5 terminal first; falls back cleanly to PostgreSQL archive.
    """
    # 1. Attempt live MT5 fetch
    try:
        if mt5_client.connect():
            rates = mt5_client.fetch_candles_by_count(symbol, timeframe, count)
            if rates is not None and len(rates) > 0:
                candles = []
                for r in rates:
                    candles.append(
                        CandleOut(
                            time=int(r["time"]),
                            open=float(r["open"]),
                            high=float(r["high"]),
                            low=float(r["low"]),
                            close=float(r["close"]),
                            volume=int(r.get("tick_volume", r.get("real_volume", 0))),
                        )
                    )
                return candles
    except Exception:
        pass

    # 2. Fallback to PostgreSQL
    inst = db.query(Instrument).filter(Instrument.symbol == symbol).first()
    if not inst:
        return []

    db_candles = (
        db.query(Candle)
        .filter(Candle.instrument_id == inst.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.desc())
        .limit(count)
        .all()
    )

    candles = []
    for c in reversed(db_candles):
        candles.append(
            CandleOut(
                time=int(c.open_time.replace(tzinfo=timezone.utc).timestamp()),
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=int(c.volume or 0),
            )
        )

    return candles


@router.get("/sessions", response_model=SessionOut)
def get_session_info():
    """
    Computes current UTC market session, ICT Killzone status, and upcoming events.
    Killzones (UTC):
      - Asian Session: 00:00 - 06:00
      - London Open Killzone: 07:00 - 10:00
      - NY AM Killzone: 12:00 - 15:00
      - London Close Killzone: 15:00 - 17:00
    """
    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute
    current_time_dec = hour + (minute / 60.0)

    # Determine broad session
    if 0 <= current_time_dec < 7:
        session = "Asian Session"
    elif 7 <= current_time_dec < 12:
        session = "London Session"
    elif 12 <= current_time_dec < 17:
        session = "New York Session"
    else:
        session = "Market Maintenance / Late NY"

    # Determine ICT Killzone
    is_killzone = False
    current_kz = None
    upcoming_kz = None
    minutes_to_next = 0

    if 7.0 <= current_time_dec < 10.0:
        is_killzone = True
        current_kz = "London Open Killzone"
        upcoming_kz = "NY AM Killzone (12:00 UTC)"
        minutes_to_next = int((12.0 - current_time_dec) * 60)
    elif 12.0 <= current_time_dec < 15.0:
        is_killzone = True
        current_kz = "New York AM Killzone"
        upcoming_kz = "London Close Killzone (15:00 UTC)"
        minutes_to_next = int((15.0 - current_time_dec) * 60)
    elif 15.0 <= current_time_dec < 17.0:
        is_killzone = True
        current_kz = "London Close Killzone"
        upcoming_kz = "Asian Session Open (00:00 UTC)"
        minutes_to_next = int((24.0 - current_time_dec) * 60)
    elif current_time_dec < 7.0:
        is_killzone = False
        current_kz = "Off-Killzone (Asian Liquidity Building)"
        upcoming_kz = "London Open Killzone (07:00 UTC)"
        minutes_to_next = int((7.0 - current_time_dec) * 60)
    elif 10.0 <= current_time_dec < 12.0:
        is_killzone = False
        current_kz = "Off-Killzone (London Lunch Consolidation)"
        upcoming_kz = "New York AM Killzone (12:00 UTC)"
        minutes_to_next = int((12.0 - current_time_dec) * 60)
    else:
        is_killzone = False
        current_kz = "Off-Killzone (Late NY / Market Transition)"
        upcoming_kz = "Asian Session Open (00:00 UTC)"
        minutes_to_next = int((24.0 - current_time_dec) * 60)

    return SessionOut(
        current_utc_time=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        active_session=session,
        is_killzone=is_killzone,
        current_killzone=current_kz,
        upcoming_kz=upcoming_kz,
        minutes_to_next_killzone=max(0, minutes_to_next),
    )
