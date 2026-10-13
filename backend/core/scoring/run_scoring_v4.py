"""
Score CRT setups using liquidity, order-block, FVG, market-structure,
SMT, and recorded-session confluence.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.scoring.run_scoring_v4 --symbol EURUSD.m
"""

import argparse

from app.database.base import SessionLocal
from app.models.models import Instrument
from core.scoring.confluence import score_crt_setups_v4


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Score CRT setups using liquidity, order block, FVG, "
            "structure, SMT, and recorded sessions."
        )
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Exact MT5 symbol name, e.g. EURUSD.m",
    )
    parser.add_argument("--liq-tolerance-pips", type=float, default=15.0)
    parser.add_argument("--ob-tolerance-pips", type=float, default=10.0)
    parser.add_argument("--fvg-tolerance-pips", type=float, default=10.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        processed = score_crt_setups_v4(
            db,
            instrument.id,
            args.liq_tolerance_pips,
            args.ob_tolerance_pips,
            instrument.digits,
            float(instrument.pip_size),
            args.fvg_tolerance_pips,
        )
        print(
            f"{args.symbol}: processed {processed} setup score(s) "
            "(liquidity + order block + FVG + structure + SMT + session)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
