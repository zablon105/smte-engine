"""
Command-line entry point for detecting and storing Fair Value Gaps.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.market_analysis.run_fvg --symbol EURUSD.m --timeframes M15 H1 --min-gap-pips 1.0
"""

import argparse

from app.database.base import SessionLocal
from app.models.models import Instrument
from core.market_analysis.fvg_detector import detect_and_store_fvgs


def main():
    parser = argparse.ArgumentParser(
        description="Detect Fair Value Gaps and store them."
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Exact MT5 symbol name, e.g. EURUSD.m",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["M15", "H1"],
        help="Timeframes to scan (default: M15 H1)",
    )
    parser.add_argument(
        "--min-gap-pips",
        type=float,
        default=1.0,
        help="Ignore FVGs smaller than this pip size (default: 1.0).",
    )
    args = parser.parse_args()
    if args.min_gap_pips < 0:
        parser.error("--min-gap-pips must be non-negative")

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        point = float(instrument.pip_size)
        true_pip = point * 10 if instrument.digits in (3, 5) else point
        min_gap_size = args.min_gap_pips * true_pip

        for timeframe in args.timeframes:
            stored = detect_and_store_fvgs(
                db, instrument.id, timeframe, min_gap_size
            )
            print(
                f"{args.symbol} [{timeframe}]: {stored} FVG(s) stored "
                f"(min gap {args.min_gap_pips} pips)."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
