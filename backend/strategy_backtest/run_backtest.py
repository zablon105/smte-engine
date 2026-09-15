"""
run_backtest.py
Command-line entry point for backtesting all generated trade
signals for an instrument.

Usage (from SMTE/backend, with smte-env activated):
    python -m backtesting.run_backtest --symbol EURUSD.m --timeframe M15
"""

import argparse
from app.database.base import SessionLocal
from app.models.models import Instrument
from strategy_backtest.signal_backtest import backtest_all_signals


def main():
    parser = argparse.ArgumentParser(description="Backtest generated trade signals.")
    parser.add_argument("--symbol", required=True, help="Exact MT5 symbol name, e.g. EURUSD.m")
    parser.add_argument("--timeframe", default="M15", choices=[
        "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"
    ])
    args = parser.parse_args()

    db = SessionLocal()
    try:
        instrument = db.query(Instrument).filter_by(symbol=args.symbol).first()
        if instrument is None:
            print(f"No instrument found for symbol '{args.symbol}'.")
            return

        results = backtest_all_signals(db, instrument.id, args.timeframe)

        if not results:
            print(f"No trade signals found for {args.symbol}.")
            return

        tp_count = sum(1 for r in results if r["result"] == "TP_HIT")
        sl_count = sum(1 for r in results if r["result"] == "SL_HIT")
        pending_count = sum(1 for r in results if r["result"] == "NO_OUTCOME_YET")

        print(f"\n{args.symbol} backtest results ({len(results)} total signals):")
        print(f"  TP hit first:  {tp_count}")
        print(f"  SL hit first:  {sl_count}")
        print(f"  No outcome yet (ran out of data): {pending_count}")
        print()

        for r in results:
            print(f"  Signal #{r['signal_id']} [{r['direction']}] "
                  f"entry={r['entry_price']:.5f} SL={r['stop_loss']:.5f} TP={r['take_profit']:.5f} "
                  f"-> {r['result']} at {r['hit_at']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()