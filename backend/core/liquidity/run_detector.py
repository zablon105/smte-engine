"""
run_detector.py
Command-line entry point for liquidity zone detection.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.liquidity.run_detector --symbol EURUSD.m --timeframe M15 --lookback 500
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.liquidity.detector import detect_liquidity_zones, mark_swept_zones


def main():
    parser = argparse.ArgumentParser(description="Detect liquidity zones from stored candle data.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", required=True, choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--lookback", type=int, default=500)
    parser.add_argument("--tolerance-pips", type=float, default=3.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. Run the data collector first.")
            return

        created = detect_liquidity_zones(
            db,
            instrument.id,
            args.timeframe,
            args.lookback,
            args.tolerance_pips,
            instrument.digits,
            float(instrument.pip_size),
        )
        swept = mark_swept_zones(db, instrument.id, args.timeframe)

        print(f"{args.symbol} [{args.timeframe}]: created {created} new liquidity zone(s), "
              f"marked {swept} as newly swept.")
    finally:
        db.close()


if __name__ == "__main__":
    main()