"""
run_detector.py
Command-line entry point for market structure detection (BOS and CHOCH).

Usage (from SMTE/backend, with smte-env activated):
    python -m core.market_structure.run_detector --symbol EURUSD.m --timeframe M15 --lookback 2000
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.market_structure.detector import detect_market_structure


def main():
    parser = argparse.ArgumentParser(description="Detect market structure (BOS/CHOCH) from stored candles.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", required=True, choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--lookback", type=int, default=500, help="Number of candles to look back")
    parser.add_argument("--swing-length", type=int, default=2, help="Candles on each side to define swing pivot")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. Run data collector first.")
            return

        created = detect_market_structure(
            db,
            instrument.id,
            args.timeframe,
            lookback=args.lookback,
            swing_length=args.swing_length,
        )

        print(f"[{args.symbol}] [{args.timeframe}]: created {created} new market structure event(s) (BOS/CHOCH).")
    finally:
        db.close()


if __name__ == "__main__":
    main()

