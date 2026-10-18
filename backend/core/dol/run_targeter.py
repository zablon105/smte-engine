"""
run_targeter.py
Command-line entry point for Draw on Liquidity (DOL) targeting.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.dol.run_targeter --symbol EURUSD.m --timeframe H1
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.dol.targeter import identify_dol_targets, update_dol_targets


def main():
    parser = argparse.ArgumentParser(description="Identify and update Draw on Liquidity (DOL) targets.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol, e.g. EURUSD.m")
    parser.add_argument("--timeframe", default="H1", choices=["M15", "H1", "H4", "D1"])
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        identified = identify_dol_targets(db, instrument.id, args.timeframe)
        updated = update_dol_targets(db, instrument.id, "M15")
        print(f"[{args.symbol}] [{args.timeframe}]: {identified} DOL targets created, {updated} marked reached.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
