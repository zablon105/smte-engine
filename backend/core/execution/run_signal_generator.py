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
    parser.add_argument("--max-risk-pips", type=float, default=None, help="Filter out trades with stop distance > X pips")
    parser.add_argument("--killzones-only", action="store_true", help="Only take setups confirmed during London/NY open")
    parser.add_argument("--htf-align", action="store_true", help="Require alignment with H1/H4 market structure")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        created = generate_signals(
            db,
            instrument.id,
            args.min_score,
            args.rr,
            args.stop_buffer_pips,
            instrument.digits,
            float(instrument.pip_size),
            max_risk_pips=args.max_risk_pips,
            killzones_only=args.killzones_only,
            require_htf_alignment=args.htf_align,
        )
        print(f"{args.symbol}: created {created} new trade signal(s) "
              f"(min_score={args.min_score}, RR={args.rr}, max_risk={args.max_risk_pips}, kz={args.killzones_only}, htf={args.htf_align}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()