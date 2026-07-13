"""
run_detector_mtf.py
Command-line entry point for the multi-timeframe CRT detector
(higher timeframe range, lower timeframe manipulation/distribution).

Usage (from SMTE/backend, with smte-env activated):
    python -m core.crt.run_detector_mtf --symbol EURUSD.m --range-tf H4 --manip-tf M15 --lookback 100
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.crt.detector import detect_crt_setups_mtf


def main():
    parser = argparse.ArgumentParser(description="Multi-timeframe CRT setup detection.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--range-tf", default="H4", choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--manip-tf", default="M15", choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    parser.add_argument("--lookback", type=int, default=100, help="How many range candles to scan")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'. Run the data collector first.")
            return

        created = detect_crt_setups_mtf(
            db, instrument.id, args.range_tf, args.manip_tf, args.lookback
        )
        print(f"{args.symbol} [{args.range_tf} range -> {args.manip_tf} manipulation]: "
              f"scanned {args.lookback} range candles, created {created} new CRT setup(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()