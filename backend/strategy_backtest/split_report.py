"""
split_report.py
Honest check of the trade signals, with two fixes over tiered_report.py:

1. ONE TRADE AT A TIME: for each symbol and direction, a new signal is
   skipped if an earlier accepted trade is still open when it would be
   entered. This removes near-duplicate signals that make the sample
   look bigger (and the results look more certain) than they really are.
2. TIME SPLIT: results are shown separately for trades entered BEFORE
   and AFTER a cutoff date, so you can see whether a score band that
   looked good earlier still works on later data.

Every win rate is shown with a 95% range (Wilson interval). With only a
few dozen trades that range is wide, and that is the honest picture of
how much we really know.

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.split_report
    python -m strategy_backtest.split_report --cutoff 2026-05-01 --rr 2.0
"""

import argparse
from datetime import datetime, timezone
from math import sqrt

from app.database.base import SessionLocal
from app.models.models import CrtSetup, SetupScore, TradeSignal
from strategy_backtest.signal_backtest import _find_confirmation_time, backtest_signal

# Score bands to report on: (low, high, label). Edit freely.
SCORE_BANDS = [
    (0, 9, "0-9"),
    (10, 14, "10-14"),
    (15, 19, "15-19"),
    (20, 999, "20+"),
]

LONG_AGO = datetime.min.replace(tzinfo=timezone.utc)
FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


def wilson_interval(wins, n, z=1.96):
    """95% range for a win rate. Returns (low, high) as fractions."""
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def band_label(score):
    for low, high, label in SCORE_BANDS:
        if low <= score <= high:
            return label
    return "other"


def collect_trades(db, timeframe):
    """Backtest every signal and return one record per tradable signal."""
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
            "score": score.total_score,
        })
    return trades


def one_trade_at_a_time(trades):
    """Drop signals that would be entered while an earlier accepted trade
    on the same symbol and direction is still open."""
    busy_until = {}
    kept = []
    skipped = 0

    for trade in sorted(trades, key=lambda t: t["entry_time"]):
        key = (trade["instrument_id"], trade["direction"])
        if trade["entry_time"] < busy_until.get(key, LONG_AGO):
            skipped += 1
            continue
        kept.append(trade)
        busy_until[key] = trade["hit_at"] or FAR_FUTURE

    return kept, skipped


def summarise(trades, rr):
    """Return (decided, wins, win_rate, expected_value, range_low, range_high)."""
    decided = [t for t in trades if t["result"] in ("TP_HIT", "SL_HIT")]
    n = len(decided)
    wins = sum(1 for t in decided if t["result"] == "TP_HIT")
    if n == 0:
        return 0, 0, 0.0, 0.0, 0.0, 0.0
    p = wins / n
    ev = p * rr - (1 - p)
    low, high = wilson_interval(wins, n)
    return n, wins, p, ev, low, high


def print_row(label, trades, rr):
    n, wins, p, ev, low, high = summarise(trades, rr)
    if n == 0:
        print(f"{label:<12}{0:>7}")
        return
    rng = f"{low * 100:.0f}-{high * 100:.0f}%"
    print(f"{label:<12}{n:>7}{wins:>6}{p * 100:>9.1f}%{rng:>14}{ev:>+9.2f}")


def print_period(title, trades, rr):
    print(f"\n{title}")
    print("-" * 70)
    print(f"{'Score band':<12}{'Trades':>7}{'Wins':>6}{'Win rate':>10}{'95% range':>14}{'EV (R)':>9}")
    for _, _, label in SCORE_BANDS:
        print_row(label, [t for t in trades if band_label(t["score"]) == label], rr)
    print_row("ALL", trades, rr)


def main():
    parser = argparse.ArgumentParser(description="Signal results with a one-trade-at-a-time rule and a time split.")
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

        print_period(f"EARLIER PERIOD (entered before {args.cutoff})", earlier, args.rr)
        print_period(f"LATER PERIOD (entered on/after {args.cutoff})", later, args.rr)
        print_period("ALL TRADES", trades, args.rr)

        print(f"\nBreak-even win rate at {args.rr}:1 is {break_even:.1f}%.")
        print("A band is only convincing if the LOW end of its 95% range is above that,")
        print("and it holds up in BOTH periods.")
    finally:
        db.close()


if __name__ == "__main__":
    main()