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
from core.execution.order_executor import (
    execute_pending_signals,
    send_test_order,
    sync_and_manage_open_trades,
)


def main():
    parser = argparse.ArgumentParser(description="Execute pending signals and manage open positions on MT5.")
    parser.add_argument("--execute-pending", action="store_true", help="Execute all pending trade signals on MT5")
    parser.add_argument("--sync-trades", action="store_true", help="Sync open trades and move SL to Breakeven at +1R")
    parser.add_argument("--breakeven", type=float, default=1.0, help="Profit multiple (in R) to trigger Breakeven")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without sending orders")
    parser.add_argument("--max-age-minutes", type=int, default=60, help="Max signal age in minutes to execute (default 60)")
    parser.add_argument("--test-order", action="store_true", help="Place a small 0.01-lot test order to verify broker execution")
    parser.add_argument("--symbol", default="EURUSD.m", help="Symbol for test order (default EURUSD.m)")
    parser.add_argument("--direction", default="BUY", choices=["BUY", "SELL"], help="Direction for test order")
    parser.add_argument("--lots", type=float, default=0.01, help="Lot size for test order")
    parser.add_argument("--sl-pips", type=float, default=20.0, help="SL distance in pips")
    parser.add_argument("--tp-pips", type=float, default=40.0, help="TP distance in pips")
    parser.add_argument("--all", action="store_true", help="Execute pending signals AND sync open trades")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.test_order:
            ticket = send_test_order(
                db,
                symbol=args.symbol,
                direction=args.direction,
                lot_size=args.lots,
                sl_pips=args.sl_pips,
                tp_pips=args.tp_pips,
            )
            if ticket:
                print(f"[Order Executor] Test trade successfully opened! Ticket #{ticket}")
            return

        if not args.execute_pending and not args.sync_trades and not args.all:
            args.all = True

        if args.execute_pending or args.all:
            executed = execute_pending_signals(
                db,
                dry_run=args.dry_run,
                max_age_minutes=args.max_age_minutes,
            )
            print(f"[Order Executor] Executed {executed} trade(s) (dry_run={args.dry_run}).")

        if args.sync_trades or args.all:
            stats = sync_and_manage_open_trades(db, breakeven_trigger_r=args.breakeven)
            print(f"[Order Executor] Active trades sync: {stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
