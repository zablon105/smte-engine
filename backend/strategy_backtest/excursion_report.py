"""
excursion_report.py
Do confirmed CRT setups move any better afterwards than a random moment would?

Beginner glossary:
  R    = the trade's own risk (distance from entry to stop). A move of +2R
         means price went twice as far in your favor as the stop distance.
  MFE  = max favorable excursion: the furthest price moved IN your favor.
  MAE  = max adverse excursion: the furthest price moved AGAINST you.
  ATR  = average true range, a standard measure of how much price normally
         moves per candle. It lets us compare quiet and busy markets fairly.

How the test works:
  1. Take the same trades split_report uses (one trade at a time).
  2. For each, measure what price did over the next --horizon candles.
  3. Build a RANDOM baseline: for every signal, pick random entry moments on
     the same symbol, same direction, same month, same hour of day, and with
     the same risk size measured in ATR units. Measure the same things there.
  4. Compare. If confirmed setups carry no information, SIGNALS should look
     like RANDOM, and both should look like THEORY: in a coin-flip market a
     1R target beats a 1R stop 50% of the time, 2R 33.3%, 3R 25%.

DATE WINDOW: --start and --end limit the study to trades entered inside a
window (for example, older data that was never examined before). If
--cutoff is not given, the trades are split into two equal halves at their
median entry date.

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.excursion_report
    python -m strategy_backtest.excursion_report --horizon 96 --random-per-signal 30
    python -m strategy_backtest.excursion_report --end 2025-09-01
"""

import argparse

import numpy as np
import pandas as pd

from app.database.base import SessionLocal
from app.models.models import Candle, CrtSetup, TradeSignal
from strategy_backtest.signal_backtest import _find_confirmation_time, backtest_signal
from strategy_backtest.split_report import (
    PREFILTER_MARGIN,
    describe_window,
    filter_window,
    median_entry_time,
    one_trade_at_a_time,
    parse_date,
    wilson_interval,
)

ATR_PERIOD = 14


def compute_atr(high, low, close, period=ATR_PERIOD):
    """Average true range for every candle (NaN until enough candles exist)."""
    previous_close = np.roll(close, 1)
    previous_close[0] = close[0]
    true_range = np.maximum.reduce([
        high - low,
        np.abs(high - previous_close),
        np.abs(low - previous_close),
    ])
    return pd.Series(true_range).rolling(period).mean().to_numpy()


def build_series(db, instrument_id, timeframe, horizon):
    """
    Load one instrument's candles into arrays, plus lookup tables:
      index_of : candle open time -> position in the arrays
      buckets  : (year, month, hour) -> positions usable as random entries
                 (enough ATR history behind them, enough candles ahead)
    """
    rows = (
        db.query(Candle.open_time, Candle.high, Candle.low, Candle.close)
        .filter(Candle.instrument_id == instrument_id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.asc())
        .all()
    )
    times = [row[0] for row in rows]
    high = np.array([float(row[1]) for row in rows])
    low = np.array([float(row[2]) for row in rows])
    close = np.array([float(row[3]) for row in rows])
    atr = compute_atr(high, low, close)
    count = len(times)

    grouped = {}
    for i in range(ATR_PERIOD, count - horizon):
        if not atr[i] > 0:  # also skips NaN
            continue
        stamp = times[i]
        grouped.setdefault((stamp.year, stamp.month, stamp.hour), []).append(i)
    buckets = {key: np.array(positions) for key, positions in grouped.items()}

    return {
        "times": times,
        "index_of": {stamp: i for i, stamp in enumerate(times)},
        "high": high,
        "low": low,
        "close": close,
        "atr": atr,
        "buckets": buckets,
        "count": count,
    }


def simulate_path(high, low, close, start, sign, entry, risk, horizon, targets):
    """
    Walk forward `horizon` candles from `start` (first candle checked is
    start + 1) for a trade with the given entry and risk. sign is +1 for a
    BUY, -1 for a SELL. For each target (in R) it records which came first:
    the target ("TP"), or a 1R stop ("SL"), or neither (None). If both are
    touched inside the same candle the stop is counted first, which matches
    the existing backtest.
    """
    end = start + horizon
    candle_high = high[start + 1:end + 1]
    candle_low = low[start + 1:end + 1]

    if sign > 0:
        favorable = (candle_high - entry) / risk
        adverse = (entry - candle_low) / risk
    else:
        favorable = (entry - candle_low) / risk
        adverse = (candle_high - entry) / risk

    stop_hits = np.nonzero(adverse >= 1.0)[0]
    first_stop = stop_hits[0] if stop_hits.size else None

    outcomes = {}
    for target in targets:
        target_hits = np.nonzero(favorable >= target)[0]
        first_target = target_hits[0] if target_hits.size else None
        if first_stop is None and first_target is None:
            outcomes[target] = None
        elif first_target is None:
            outcomes[target] = "SL"
        elif first_stop is None:
            outcomes[target] = "TP"
        else:
            outcomes[target] = "SL" if first_stop <= first_target else "TP"

    return {
        "outcomes": outcomes,
        "end_move": float(sign * (close[end] - entry) / risk),
        "mfe": float(favorable.max()),
        "mae": float(adverse.max()),
    }


def collect_trades(db, timeframe, start=None, end=None):
    """Every signal (in the window) with a confirmed entry, plus when its trade would have ended."""
    query = (
        db.query(TradeSignal, CrtSetup)
        .join(CrtSetup, CrtSetup.id == TradeSignal.crt_setup_id)
    )
    if end is not None:
        query = query.filter(CrtSetup.detected_at < end)
    if start is not None:
        query = query.filter(CrtSetup.detected_at >= start - PREFILTER_MARGIN)
    rows = query.all()

    trades = []
    for signal, setup in rows:
        entry_time = _find_confirmation_time(db, setup, timeframe)
        if entry_time is None:
            continue  # never confirmed in the available data
        outcome = backtest_signal(db, signal, setup, timeframe)
        trades.append({
            "instrument_id": signal.instrument_id,
            "direction": signal.signal_direction,
            "entry_time": entry_time,
            "entry_price": float(signal.entry_price),
            "stop_loss": float(signal.stop_loss),
            "hit_at": outcome["hit_at"],
            "result": outcome["result"],
        })
    return trades


def fmt_rate(sims, target):
    wins = sum(1 for s in sims if s["outcomes"][target] == "TP")
    losses = sum(1 for s in sims if s["outcomes"][target] == "SL")
    decided = wins + losses
    if decided == 0:
        return "-"
    low, high = wilson_interval(wins, decided)
    return f"{decided:>6}  {wins / decided * 100:>5.1f}%  ({low * 100:.0f}-{high * 100:.0f}%)"


def stat(sims, key, func):
    return func([s[key] for s in sims]) if sims else float("nan")


def print_period(title, signal_sims, random_sims, targets):
    print(f"\n{title}   (signals: {len(signal_sims)}, random samples: {len(random_sims)})")
    print("-" * 84)
    print(f"{'Target':<8}{'Theory':>8}   {'RANDOM   decided  win%  95% range':<34}{'SIGNALS  decided  win%  95% range':<34}")
    for target in targets:
        label = f"{target:g}R"
        theory = 100 / (1 + target)
        print(f"{label:<8}{theory:>7.1f}%   {fmt_rate(random_sims, target):<34}{fmt_rate(signal_sims, target):<34}")

    print("\nAverage move after entry, in R (direction-adjusted)")
    print(f"{'':<30}{'RANDOM':>10}{'SIGNALS':>10}")
    rows = [
        ("mean at horizon end", "end_move", np.mean),
        ("median at horizon end", "end_move", np.median),
        ("median best move (MFE)", "mfe", np.median),
        ("median worst move (MAE)", "mae", np.median),
    ]
    for label, key, func in rows:
        print(f"{label:<30}{stat(random_sims, key, func):>+10.2f}{stat(signal_sims, key, func):>+10.2f}")


def main():
    parser = argparse.ArgumentParser(description="Signals versus a matched random-entry baseline.")
    parser.add_argument("--cutoff", type=parse_date, default=None,
                        help="YYYY-MM-DD: entries before this date count as the 'earlier' period. "
                             "Default: the median entry date (two equal halves). "
                             "Use 2026-05-01 to reproduce the old split.")
    parser.add_argument("--start", type=parse_date, default=None,
                        help="YYYY-MM-DD: only trades entered on/after this date")
    parser.add_argument("--end", type=parse_date, default=None,
                        help="YYYY-MM-DD: only trades entered before this date")
    parser.add_argument("--horizon", type=int, default=288,
                        help="Candles to follow each entry (288 = 3 days of M15)")
    parser.add_argument("--random-per-signal", type=int, default=20,
                        help="Random entries drawn for every signal")
    parser.add_argument("--targets", type=float, nargs="+", default=[1.0, 2.0, 3.0],
                        help="Target distances in R, each tested against a 1R stop")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (same seed = same result)")
    parser.add_argument("--timeframe", default="M15")
    args = parser.parse_args()

    if args.horizon < 1:
        parser.error("--horizon must be at least 1")
    if args.random_per_signal < 1:
        parser.error("--random-per-signal must be at least 1")
    if args.start and args.end and args.start >= args.end:
        parser.error("--start must be earlier than --end")

    rng = np.random.default_rng(args.seed)

    db = SessionLocal()
    try:
        all_trades = filter_window(
            collect_trades(db, args.timeframe, args.start, args.end), args.start, args.end
        )
        trades, skipped_overlap = one_trade_at_a_time(all_trades)

        if not trades:
            print("No trades found in this window.")
            return

        cutoff = args.cutoff or median_entry_time(trades)
        cutoff_label = cutoff.strftime("%Y-%m-%d")

        series_cache = {}
        signal_sims = []
        random_sims = []
        dropped_short = 0
        dropped_no_baseline = 0

        for trade in trades:
            instrument_id = trade["instrument_id"]
            if instrument_id not in series_cache:
                series_cache[instrument_id] = build_series(
                    db, instrument_id, args.timeframe, args.horizon
                )
            series = series_cache[instrument_id]

            entry_time = trade["entry_time"]
            start = series["index_of"].get(entry_time)
            risk = abs(trade["entry_price"] - trade["stop_loss"])

            usable = (
                start is not None
                and ATR_PERIOD <= start <= series["count"] - 1 - args.horizon
                and risk > 0
                and series["atr"][start] > 0
            )
            if not usable:
                dropped_short += 1  # too little forward data (or no usable ATR)
                continue

            candidates = series["buckets"].get((entry_time.year, entry_time.month, entry_time.hour))
            if candidates is None or len(candidates) == 0:
                dropped_no_baseline += 1
                continue

            sign = 1 if trade["direction"] == "BUY" else -1
            risk_in_atr = risk / series["atr"][start]

            signal_sim = simulate_path(
                series["high"], series["low"], series["close"],
                start, sign, trade["entry_price"], risk, args.horizon, args.targets,
            )
            signal_sim["entry_time"] = entry_time
            signal_sims.append(signal_sim)

            picks = rng.choice(
                candidates,
                size=args.random_per_signal,
                replace=len(candidates) < args.random_per_signal,
            )
            for position in picks:
                j = int(position)
                random_risk = risk_in_atr * series["atr"][j]
                sim = simulate_path(
                    series["high"], series["low"], series["close"],
                    j, sign, series["close"][j], random_risk, args.horizon, args.targets,
                )
                sim["entry_time"] = series["times"][j]
                random_sims.append(sim)

        print(f"\nWindow: {describe_window(args.start, args.end)}")
        print(f"Signals with a confirmed entry: {len(all_trades)}")
        print(f"Skipped (trade already open on same symbol/direction): {skipped_overlap}")
        print(f"Dropped (not enough data after entry): {dropped_short}")
        print(f"Dropped (no matching random moments): {dropped_no_baseline}")
        print(f"Signals analysed: {len(signal_sims)}   Random entries: {len(random_sims)}")
        print(f"Horizon: {args.horizon} candles after entry. Random entries match symbol, direction,")
        print("month, hour of day, and risk size in ATR units.")

        earlier_signals = [s for s in signal_sims if s["entry_time"] < cutoff]
        later_signals = [s for s in signal_sims if s["entry_time"] >= cutoff]
        earlier_random = [s for s in random_sims if s["entry_time"] < cutoff]
        later_random = [s for s in random_sims if s["entry_time"] >= cutoff]

        print_period(f"EARLIER PERIOD (before {cutoff_label})", earlier_signals, earlier_random, args.targets)
        print_period(f"LATER PERIOD (on/after {cutoff_label})", later_signals, later_random, args.targets)
        print_period("ALL", signal_sims, random_sims, args.targets)

        print("\nHow to read this:")
        print("  THEORY is what a coin-flip market gives for that target against a 1R stop.")
        print("  RANDOM is the same trade shape started at random moments.")
        print("  The setup only carries information if SIGNALS beat RANDOM clearly,")
        print("  in BOTH periods, and the average move is clearly better too.")
        print("  Unresolved paths (neither level reached in the horizon) are left out of win%.")
    finally:
        db.close()


if __name__ == "__main__":
    main()