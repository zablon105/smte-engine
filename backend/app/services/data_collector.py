"""
data_collector.py
Pulls candle data from MT5 and stores it in the `instruments` and
`candles` tables via SQLAlchemy.

Beginner note: "upsert" means insert a row, but if it already exists
(same instrument + timeframe + open_time), skip it instead of erroring.
This lets you safely re-run the collector without creating duplicates,
which matters a lot once you start scheduling this to run repeatedly.
"""

from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.base import SessionLocal
from app.models.models import Instrument, Candle
from app.services import mt5_client


def ensure_instrument(db, symbol: str) -> Instrument:
    """
    Looks up the instrument in the database. If it doesn't exist yet,
    pulls its metadata from MT5 and creates it automatically.
    """
    instrument = db.query(Instrument).filter_by(symbol=symbol).first()
    if instrument:
        return instrument

    info = mt5_client.get_symbol_info(symbol)
    if info is None:
        raise ValueError(f"Symbol '{symbol}' not found in MT5. Check the exact symbol name (e.g. 'EURUSD.m').")

    instrument = Instrument(
        symbol=symbol,
        description=info.description,
        digits=info.digits,
        pip_size=info.point,
        contract_size=info.trade_contract_size,
        is_active=True,
    )
    db.add(instrument)
    db.commit()
    db.refresh(instrument)
    print(f"Created new instrument record for {symbol}")
    return instrument


def save_candles(db, instrument: Instrument, timeframe: str, rates) -> int:
    """
    Inserts fetched MT5 candle rows into the database, skipping any
    that already exist. Returns the number of NEW rows inserted.
    """
    if len(rates) == 0:
        return 0

    rows = []
    for r in rates:
        rows.append({
            "instrument_id": instrument.id,
            "timeframe": timeframe,
            "open_time": datetime.fromtimestamp(int(r["time"]), tz=timezone.utc),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r["tick_volume"]),
            "spread": int(r["spread"]),
        })

    stmt = pg_insert(Candle).values(rows)
    # ON CONFLICT DO NOTHING relies on the UNIQUE constraint defined
    # in schema.sql: (instrument_id, timeframe, open_time)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["instrument_id", "timeframe", "open_time"]
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount


def collect(symbol: str, timeframe: str, count: int = 1000):
    """
    Main entry point: connects to MT5, ensures the instrument exists,
    fetches the most recent `count` candles, and saves any new ones.
    """
    mt5_client.connect()
    db = SessionLocal()
    try:
        instrument = ensure_instrument(db, symbol)
        rates = mt5_client.fetch_candles_by_count(symbol, timeframe, count)
        inserted = save_candles(db, instrument, timeframe, rates)
        print(f"{symbol} [{timeframe}]: fetched {len(rates)} candles, inserted {inserted} new rows.")
    finally:
        db.close()
        mt5_client.disconnect()