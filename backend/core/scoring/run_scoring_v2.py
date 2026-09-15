"""
run_scoring_v2.py
Command-line entry point for scoring CRT setups using BOTH
liquidity and order block confluence.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.scoring.run_scoring_v2 --symbol EURUSD.m --liq-tolerance-pips 15 --ob-tolerance-pips 10
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.scoring.confluence import score_crt_setups_v2


def main():
    parser = argparse.ArgumentParser(description="Score CRT setups using liquidity + order block confluence.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--liq-tolerance-pips", type=float, default=15.0)
    parser.add_argument("--ob-tolerance-pips", type=float, default=10.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        processed = score_crt_setups_v2(
            db, instrument.id, args.liq_tolerance_pips, args.ob_tolerance_pips,
            instrument.digits, float(instrument.pip_size)
        )
        print(f"{args.symbol}: processed {processed} setup score(s) (liquidity + order block confluence).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
