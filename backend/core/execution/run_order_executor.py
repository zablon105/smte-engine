"""
run_order_executor.py
Command-line entry point for executing pending signals and managing open positions on MT5.

Usage (from SMTE/backend, with smte-env activated):
    python -m core.execution.run_order_executor --execute-pending
    python -m core.execution.run_order_executor --sync-trades --breakeven 1.0
    python -m core.execution.run_order_executor --all
"""

import argparse
from app.database.base import SessionLocal
from core.execution.order_executor import execute_pending_signals, sync_and_manage_open_trades


def main():
    parser = argparse.ArgumentParser(description="Execute pending signals and manage open positions on MT5.")
    parser.add_argument("--execute-pending", action="store_true", help="Execute all pending trade signals on MT5")
    parser.add_argument("--sync-trades", action="store_true", help="Sync open trades and move SL to Breakeven at +1R")
    parser.add_argument("--breakeven", type=float, default=1.0, help="Profit multiple (in R) to trigger Breakeven")
    parser.add_argument("--all", action="store_true", help="Execute pending signals AND sync open trades")
    args = parser.parse_args()

    if not args.execute_pending and not args.sync_trades and not args.all:
        args.all = True

    db = SessionLocal()
    try:
        if args.execute_pending or args.all:
            executed = execute_pending_signals(db)
            print(f"[Order Executor] Executed {executed} new trade(s).")

        if args.sync_trades or args.all:
            stats = sync_and_manage_open_trades(db, breakeven_trigger_r=args.breakeven)
            print(f"[Order Executor] Active trades sync: {stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
