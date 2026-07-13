"""
run_detector.py
Command-line entry point for running CRT pattern detection over
candles already stored in the database (via the data collector).

Usage (from SMTE/backend, with smte-env activated):
    python -m core.crt.run_detector --symbol EURUSD.m --timeframe M15 --lookback 200
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.crt.detector import detect_crt_setups


def main():
    parser = argparse.ArgumentParser(description="Detect CRT setups from stored candle data.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", required=True, choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--lookback", type=int, default=200, help="How many recent candles to scan")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. "
                  f"Run the data collector for this symbol first.")
            return

        created = detect_crt_setups(db, instrument.id, args.timeframe, args.lookback)
        print(f"{args.symbol} [{args.timeframe}]: scanned {args.lookback} candles, "
              f"created {created} new CRT setup(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()