"""
factor_report.py
For each confluence factor, shows how trades performed when that factor
was PRESENT (score above 0) versus ABSENT (score of 0). This tells us
which factors actually carry information, instead of judging only the
combined total score.

Uses the same one-trade-at-a-time rule and time split as split_report.py.

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.factor_report
    python -m strategy_backtest.factor_report --cutoff 2026-05-01 --rr 2.0
"""

import argparse
from datetime import datetime, timezone

from app.database.base import SessionLocal
from app.models.models import CrtSetup, SetupScore, TradeSignal
from strategy_backtest.signal_backtest import _find_confirmation_time, backtest_signal
from strategy_backtest.split_report import one_trade_at_a_time, wilson_interval

# (display name, column on the setup_scores table)
FACTORS = [
    ("liquidity", "liquidity_score"),
    ("order block", "order_block_score"),
    ("fvg", "fvg_score"),
    ("structure", "structure_score"),
    ("smt", "smt_score"),
    ("session", "session_score"),
]


def collect_trades(db, timeframe):
    """Backtest every signal and keep each trade's per-factor scores."""
    rows = (
        db.query(TradeSignal, SetupScore, CrtSetup)
        .join(SetupScore, SetupScore.id == TradeSignal.setup_score_id)
        .join(CrtSetup, CrtSetup.id == TradeSignal.crt_setup_id)
        .all()
    )

    trades = []
    for signal, score, setup in rows:
        entry_time = _find_confirmation_time(db, setup, timeframe)
        if entry_time is None:
            continue  # never confirmed in the available data
        outcome = backtest_signal(db, signal, setup, timeframe)
        trades.append({
            "instrument_id": signal.instrument_id,
            "direction": signal.signal_direction,
            "entry_time": entry_time,
            "hit_at": outcome["hit_at"],
            "result": outcome["result"],
            "factors": {name: (getattr(score, column) or 0) for name, column in FACTORS},
        })
    return trades


def stats(trades):
    """Return (decided, wins, win_rate, range_low, range_high)."""
    decided = [t for t in trades if t["result"] in ("TP_HIT", "SL_HIT")]
    n = len(decided)
    wins = sum(1 for t in decided if t["result"] == "TP_HIT")
    if n == 0:
        return 0, 0, 0.0, 0.0, 0.0
    low, high = wilson_interval(wins, n)
    return n, wins, wins / n, low, high


def fmt(trades):
    n, _, rate, low, high = stats(trades)
    if n == 0:
        return "-"
    return f"{n:>4}  {rate * 100:>5.1f}%  ({low * 100:.0f}-{high * 100:.0f}%)"


def print_period(title, trades):
    print(f"\n{title}  ({len(trades)} trades)")
    print("-" * 74)
    print(f"{'Factor':<13}{'PRESENT  n   win%   95% range':<30}{'ABSENT  n   win%   95% range':<30}")
    for name, _ in FACTORS:
        present = [t for t in trades if t["factors"][name] > 0]
        absent = [t for t in trades if t["factors"][name] <= 0]
        print(f"{name:<13}{fmt(present):<30}{fmt(absent):<30}")


def main():
    parser = argparse.ArgumentParser(description="Win rate with each confluence factor present vs absent.")
    parser.add_argument("--cutoff", default="2026-05-01",
                        help="YYYY-MM-DD: trades entered before this date count as the 'earlier' period")
    parser.add_argument("--rr", type=float, default=2.0, help="Risk-reward ratio the signals were built with")
    parser.add_argument("--timeframe", default="M15")
    args = parser.parse_args()

    cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    break_even = 100 / (1 + args.rr)

    db = SessionLocal()
    try:
        all_trades = collect_trades(db, args.timeframe)
        trades, skipped = one_trade_at_a_time(all_trades)

        print(f"\nSignals with a confirmed entry: {len(all_trades)}")
        print(f"Skipped (trade already open on same symbol/direction): {skipped}")
        print(f"Trades kept: {len(trades)}")

        earlier = [t for t in trades if t["entry_time"] < cutoff]
        later = [t for t in trades if t["entry_time"] >= cutoff]

        print_period(f"EARLIER PERIOD (entered before {args.cutoff})", earlier)
        print_period(f"LATER PERIOD (entered on/after {args.cutoff})", later)
        print_period("ALL TRADES", trades)

        print(f"\nBreak-even win rate at {args.rr}:1 is {break_even:.1f}%.")
        print("Only trust a factor if PRESENT beats ABSENT in BOTH periods, and the")
        print("two 95% ranges do not mostly overlap. Treat anything else as noise.")
    finally:
        db.close()


if __name__ == "__main__":
    main()