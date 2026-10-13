"""
run_signal_generator.py
Command-line entry point for generating trade signals from
high-scoring, confirmed CRT setups.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.execution.run_signal_generator --symbol EURUSD.m --min-score 10 --rr 2.0
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.execution.signal_generator import generate_signals


def main():
    parser = argparse.ArgumentParser(description="Generate trade signals from confirmed, high-scoring CRT setups.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--min-score", type=int, default=15, help="Minimum total_score to qualify")
    parser.add_argument("--rr", type=float, default=2.0, help="Risk-reward ratio for take-profit")
    parser.add_argument("--stop-buffer-pips", type=float, default=3.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        created = generate_signals(
            db, instrument.id, args.min_score, args.rr, args.stop_buffer_pips,
            instrument.digits, float(instrument.pip_size)
        )
        print(f"{args.symbol}: created {created} new trade signal(s) "
              f"(min_score={args.min_score}, RR={args.rr}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()