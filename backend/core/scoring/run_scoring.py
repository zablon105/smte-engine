"""
run_scoring.py
Command-line entry point for scoring CRT setups against liquidity
zone confluence.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.scoring.run_scoring --symbol EURUSD.m --tolerance-pips 5
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.scoring.confluence import score_crt_setups


def main():
    parser = argparse.ArgumentParser(description="Score CRT setups using liquidity confluence.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--tolerance-pips", type=float, default=5.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        created = score_crt_setups(
            db, instrument.id, args.tolerance_pips, instrument.digits, float(instrument.pip_size)
        )
        print(f"{args.symbol}: created {created} new setup score(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()