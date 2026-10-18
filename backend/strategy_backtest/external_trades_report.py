"""
external_trades_report.py
Test trades from ANOTHER system (for example your EMA/ADX Expert Advisor)
against the same matched random-entry baseline used by excursion_report.py.

It answers one question: do this system's ENTRIES carry any information, or
would random entries (same symbol, same direction, same month, same hour of
day, same risk size in ATR units) have done just as well?

Only entries and the initial stop distance are used. The system's own exits
(trailing stops, take-profits) are not evaluated: every trade is judged against
fixed 1R / 2R / 3R targets with a 1R stop, exactly like the SMTE signals.

Trade file (CSV). The first row must be the column names (not case sensitive):
  time         when the trade was opened, e.g. 2025.03.14 10:15:00 (MT5 style)
               or 2025-03-14 10:15:00
  symbol       e.g. EURUSD or EURUSD.m
  direction    buy / sell   (a column called type, side or action also works)
  entry_price  the price the trade was opened at
  stop_loss    the initial stop PRICE   (or a stop_distance column, in price units)

Use the time exactly as MT5 shows it (broker server time): the candles in the
database use that same clock.

If the file has no stop column, --fixed-stop-distance sets one stop size (in
price units, for example 0.0030) for every trade.

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.external_trades_report C:\\path\\to\\trades.csv
    python -m strategy_backtest.external_trades_report trades.csv --fixed-stop-distance 0.0030
"""

import argparse
import csv
import re
from bisect import bisect_right
from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from app.database.base import SessionLocal
from app.models.models import Instrument
from strategy_backtest.excursion_report import (
    ATR_PERIOD,
    build_series,
    print_period,
    simulate_path,
)
from strategy_backtest.split_report import median_entry_time, parse_date

# Accepted column names, after lower-casing and removing spaces and symbols
# (so "S / L" becomes "sl" and "Open Time" becomes "opentime").
TIME_NAMES = ["time", "opentime", "entrytime", "datetime", "date"]
SYMBOL_NAMES = ["symbol", "instrument", "pair"]
SIDE_NAMES = ["side", "action", "type", "direction"]  # checked in this order
PRICE_NAMES = ["entryprice", "openprice", "price", "entry"]
STOP_NAMES = ["stoploss", "sl"]
DISTANCE_NAMES = ["stopdistance", "riskdistance", "risk"]


def normalize(header):
    return re.sub(r"[^a-z0-9]", "", header.lower())


def find_name(headers, names):
    for name in names:
        if name in headers:
            return name
    return None


def read_table(path):
    """Read the CSV into (column names, list of row dicts)."""
    text = None
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            with open(path, "r", encoding=encoding, newline="") as handle:
                text = handle.read()
            break
        except FileNotFoundError:
            raise SystemExit(f"File not found: {path}")
        except UnicodeError:
            continue
    if text is None:
        raise SystemExit(f"Could not read {path} (tried UTF-8 and UTF-16).")

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    rows = [
        row for row in csv.reader(text.splitlines(), dialect)
        if any(cell.strip() for cell in row)
    ]
    if len(rows) < 2:
        raise SystemExit("The file needs a header row and at least one trade.")

    headers = [normalize(h) for h in rows[0]]
    records = []
    for row in rows[1:]:
        record = {}
        for name, value in zip(headers, row):
            record.setdefault(name, value.strip())  # the first column with a name wins
        records.append(record)
    return headers, records


def parse_number(text):
    cleaned = text.replace("\u00a0", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def parse_time(text):
    """Accepts 2025.03.14 10:15:00 (MT5) and 2025-03-14 10:15:00. Naive times are labelled UTC."""
    cleaned = re.sub(r"^(\d{4})\.(\d{2})\.(\d{2})", r"\1-\2-\3", text.strip())
    value = pd.to_datetime(cleaned).to_pydatetime()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def pick_side_column(headers, records):
    for name in SIDE_NAMES:
        if name not in headers:
            continue
        if any(re.search(r"buy|sell|long|short", record.get(name, "").lower()) for record in records):
            return name
    return None


def pick_entry_flag_column(headers, records):
    """MT5 deal lists have a 'Direction' column holding in/out. Only 'in' rows are entries."""
    if "direction" not in headers:
        return None
    values = {re.sub(r"[^a-z]", "", record.get("direction", "").lower()) for record in records}
    values.discard("")
    if values and values <= {"in", "out", "inout"}:
        return "direction"
    return None


def build_trades(headers, records, fixed_stop_distance):
    time_name = find_name(headers, TIME_NAMES)
    symbol_name = find_name(headers, SYMBOL_NAMES)
    price_name = find_name(headers, PRICE_NAMES)
    side_name = pick_side_column(headers, records)
    stop_name = find_name(headers, STOP_NAMES)
    distance_name = find_name(headers, DISTANCE_NAMES)
    entry_flag = pick_entry_flag_column(headers, records)

    missing = []
    if time_name is None:
        missing.append("time")
    if symbol_name is None:
        missing.append("symbol")
    if price_name is None:
        missing.append("entry_price")
    if side_name is None:
        missing.append("direction (buy/sell)")
    if missing:
        raise SystemExit(f"Missing column(s): {', '.join(missing)}. Columns found: {', '.join(headers)}")
    if stop_name is None and distance_name is None and not fixed_stop_distance:
        raise SystemExit(
            "No stop information. Add a stop_loss column (price), a stop_distance column "
            "(price units), or run with --fixed-stop-distance."
        )

    trades = []
    skipped = {"exit or other rows": 0, "unreadable rows": 0, "no stop size": 0}

    for record in records:
        if entry_flag is not None:
            flag = re.sub(r"[^a-z]", "", record.get(entry_flag, "").lower())
            if flag != "in":
                skipped["exit or other rows"] += 1
                continue

        side_text = record.get(side_name, "").lower()
        if re.search(r"buy|long", side_text):
            direction = "BUY"
        elif re.search(r"sell|short", side_text):
            direction = "SELL"
        else:
            skipped["unreadable rows"] += 1
            continue

        try:
            entry_time = parse_time(record[time_name])
            entry_price = parse_number(record[price_name])
            symbol = record[symbol_name].strip()
            if not symbol:
                raise ValueError("empty symbol")

            risk = None
            if stop_name and record.get(stop_name):
                stop = parse_number(record[stop_name])
                if stop > 0:  # a stop of 0 means "no stop set"
                    risk = abs(entry_price - stop)
            if risk is None and distance_name and record.get(distance_name):
                risk = abs(parse_number(record[distance_name]))
            if risk is None and fixed_stop_distance:
                risk = fixed_stop_distance
        except (KeyError, ValueError):
            skipped["unreadable rows"] += 1
            continue

        if not risk or risk <= 0:
            skipped["no stop size"] += 1
            continue

        trades.append({
            "symbol": symbol,
            "direction": direction,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "risk": risk,
        })

    return trades, skipped


def resolve_instrument(db, symbol, cache):
    if symbol in cache:
        return cache[symbol]
    instrument = db.query(Instrument).filter_by(symbol=symbol).first()
    if instrument is None and not symbol.lower().endswith(".m"):
        instrument = db.query(Instrument).filter_by(symbol=symbol + ".m").first()
    cache[symbol] = instrument
    return instrument


def main():
    parser = argparse.ArgumentParser(description="Test another system's trades against matched random entries.")
    parser.add_argument("csv_path", help="CSV file with the trades (see the notes at the top of this file)")
    parser.add_argument("--fixed-stop-distance", type=float, default=None,
                        help="Stop size in PRICE units (for example 0.0030) when the file has no stop column")
    parser.add_argument("--cutoff", type=parse_date, default=None,
                        help="YYYY-MM-DD: trades before this date are the 'earlier' half. "
                             "Default: the median entry date (two equal halves).")
    parser.add_argument("--horizon", type=int, default=288,
                        help="Candles to follow each entry (288 = 3 days of M15)")
    parser.add_argument("--random-per-signal", type=int, default=20,
                        help="Random entries drawn for every trade")
    parser.add_argument("--targets", type=float, nargs="+", default=[1.0, 2.0, 3.0],
                        help="Target distances in R, each tested against a 1R stop")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (same seed = same result)")
    parser.add_argument("--timeframe", default="M15")
    args = parser.parse_args()

    if args.horizon < 1:
        parser.error("--horizon must be at least 1")
    if args.random_per_signal < 1:
        parser.error("--random-per-signal must be at least 1")
    if args.fixed_stop_distance is not None and args.fixed_stop_distance <= 0:
        parser.error("--fixed-stop-distance must be positive")

    headers, records = read_table(args.csv_path)
    trades, skipped = build_trades(headers, records, args.fixed_stop_distance)
    if not trades:
        print("No usable trades were found in the file.")
        print(f"Skipped: {skipped}")
        return

    rng = np.random.default_rng(args.seed)

    db = SessionLocal()
    try:
        instruments = {}
        series_cache = {}
        signal_sims = []
        random_sims = []
        dropped = {
            "symbol not in the database": 0,
            "no candle data at that time": 0,
            "not enough candles before or after": 0,
            "no matching random moments": 0,
        }
        near_open = 0

        for trade in trades:
            instrument = resolve_instrument(db, trade["symbol"], instruments)
            if instrument is None:
                dropped["symbol not in the database"] += 1
                continue

            if instrument.id not in series_cache:
                series = build_series(db, instrument.id, args.timeframe, args.horizon)
                times = series["times"]
                gaps = [times[i + 1] - times[i] for i in range(min(200, len(times) - 1))]
                series["bar"] = min(gaps) if gaps else timedelta(minutes=15)
                series_cache[instrument.id] = series
            series = series_cache[instrument.id]
            times = series["times"]

            # The candle that contains the trade time. The entry is treated as
            # happening at that candle's open, which is the previous candle's close,
            # so price is followed from the entry candle onward.
            idx = bisect_right(times, trade["entry_time"]) - 1
            if idx < 1 or trade["entry_time"] - times[idx] > 2 * series["bar"]:
                dropped["no candle data at that time"] += 1
                continue

            start = idx - 1
            if not (ATR_PERIOD <= start <= series["count"] - 1 - args.horizon) or not series["atr"][start] > 0:
                dropped["not enough candles before or after"] += 1
                continue

            entry_stamp = times[idx]
            candidates = series["buckets"].get((entry_stamp.year, entry_stamp.month, entry_stamp.hour))
            if candidates is None or len(candidates) == 0:
                dropped["no matching random moments"] += 1
                continue

            if trade["entry_time"] - entry_stamp <= timedelta(seconds=60):
                near_open += 1

            sign = 1 if trade["direction"] == "BUY" else -1
            risk = trade["risk"]
            risk_in_atr = risk / series["atr"][start]

            signal_sim = simulate_path(
                series["high"], series["low"], series["close"],
                start, sign, trade["entry_price"], risk, args.horizon, args.targets,
            )
            signal_sim["entry_time"] = entry_stamp
            signal_sim["direction"] = trade["direction"]
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
                sim["entry_time"] = times[j]
                sim["direction"] = trade["direction"]
                random_sims.append(sim)

        print(f"\nTrades read from the file: {len(trades)}")
        print(f"Skipped while reading: {skipped}")
        print(f"Dropped while testing: {dropped}")
        print(f"Trades analysed: {len(signal_sims)}   Random entries: {len(random_sims)}")
        if signal_sims:
            share = near_open / len(signal_sims) * 100
            print(f"{share:.0f}% of trades were opened within a minute of a candle open.")
            if share < 70:
                print("  Many entries happen mid-candle, which adds some noise to this test.")
        print(f"Horizon: {args.horizon} candles after entry. Random entries match symbol, direction,")
        print("month, hour of day, and risk size in ATR units. In the tables below the")
        print("SIGNALS column means YOUR system's trades.")

        if not signal_sims:
            return

        subsets = [("ALL TRADES", None), ("BUY TRADES ONLY", "BUY"), ("SELL TRADES ONLY", "SELL")]
        for title, wanted in subsets:
            mine = [s for s in signal_sims if wanted is None or s["direction"] == wanted]
            baseline = [s for s in random_sims if wanted is None or s["direction"] == wanted]
            if mine:
                print_period(title, mine, baseline, args.targets)

        cutoff = args.cutoff or median_entry_time(signal_sims)
        label = cutoff.strftime("%Y-%m-%d")
        early_mine = [s for s in signal_sims if s["entry_time"] < cutoff]
        late_mine = [s for s in signal_sims if s["entry_time"] >= cutoff]
        early_random = [s for s in random_sims if s["entry_time"] < cutoff]
        late_random = [s for s in random_sims if s["entry_time"] >= cutoff]
        if early_mine:
            print_period(f"EARLIER HALF (before {label}), all trades", early_mine, early_random, args.targets)
        if late_mine:
            print_period(f"LATER HALF (on/after {label}), all trades", late_mine, late_random, args.targets)

        print("\nHow to read this:")
        print("  Your trades only carry information if SIGNALS beat RANDOM clearly,")
        print("  in BOTH halves, and the average move is clearly better too.")
        print("  Unresolved paths (neither level reached in the horizon) are left out of win%.")
    finally:
        db.close()


if __name__ == "__main__":
    main()