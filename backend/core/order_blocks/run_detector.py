"""
run_detector.py
Command-line entry point for order block detection.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.order_blocks.run_detector --symbol EURUSD.m --timeframe M15 --lookback 2000
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.order_blocks.detector import detect_order_blocks, mark_mitigated_blocks


def main():
    parser = argparse.ArgumentParser(description="Detect order blocks from stored candle data.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", required=True, choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--lookback", type=int, default=500)
    parser.add_argument("--impulse-multiplier", type=float, default=1.5)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. Run the data collector first.")
            return

        created = detect_order_blocks(db, instrument.id, args.timeframe, args.lookback, args.impulse_multiplier)
        mitigated = mark_mitigated_blocks(db, instrument.id, args.timeframe)

        print(f"{args.symbol} [{args.timeframe}]: created {created} new order block(s), "
              f"marked {mitigated} as newly mitigated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()