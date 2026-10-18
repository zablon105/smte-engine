"""
run_builder.py
Command-line entry point for populating trading sessions (ASIA, LONDON, NEWYORK).

Usage (from SMTE/backend, with smte-env activated):
    python -m core.sessions.run_builder --symbol EURUSD.m --timeframe M15 --lookback 25000
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.sessions.builder import populate_sessions


def main():
    parser = argparse.ArgumentParser(description="Populate trading sessions (ASIA, LONDON, NEWYORK) from candles.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", default="M15", choices=["M1", "M5", "M15", "M30", "H1"])
    parser.add_argument("--lookback", type=int, default=25000, help="Number of candles to look back")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. Run data collector first.")
            return

        modified = populate_sessions(
            db,
            instrument.id,
            timeframe=args.timeframe,
            lookback=args.lookback,
        )

        print(f"[{args.symbol}] Sessions populated: {modified} records created or updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

