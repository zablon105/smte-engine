"""
run_detector.py
Command-line entry point for SMT divergence detection between correlated instruments.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.smt.run_detector --symbol EURUSD.m --timeframe M15 --lookback 2000
    python -m core.smt.run_detector --symbol EURUSD.m --correlated GBPUSD.m --timeframe M15
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from core.smt.detector import detect_all_smt_divergences, detect_smt_divergence


def main():
    parser = argparse.ArgumentParser(description="Detect SMT divergence between correlated pairs.")
    parser.add_argument("--symbol", required=True, help="Target MT5 symbol, e.g. EURUSD.m")
    parser.add_argument("--correlated", help="Optional specific correlated symbol, e.g. GBPUSD.m")
    parser.add_argument("--timeframe", default="M15", choices=["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
    parser.add_argument("--lookback", type=int, default=1000)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        target = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if target is None:
            print(f"Target symbol '{args.symbol}' not found in database.")
            return

        if args.correlated:
            correlated = db.query(Instrument).filter_by(symbol=args.correlated).first()
            if correlated is None:
                print(f"Correlated symbol '{args.correlated}' not found in database.")
                return
            created = detect_smt_divergence(
                db,
                instrument_id=target.id,
                correlated_instrument_id=correlated.id,
                timeframe=args.timeframe,
                lookback=args.lookback,
            )
            print(f"[{args.symbol} vs {args.correlated}] [{args.timeframe}]: created {created} SMT divergence record(s).")
        else:
            created = detect_all_smt_divergences(
                db,
                instrument_id=target.id,
                timeframe=args.timeframe,
                lookback=args.lookback,
            )
            print(f"[{args.symbol}] [{args.timeframe}]: created {created} SMT divergence record(s) across correlated pairs.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

