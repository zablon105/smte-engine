"""
history_loader.py
Loads a large amount of candle history from MT5 into the database.

Why this works in date windows:
  mt5.copy_rates_from_pos(...) asks MT5 for "the last N candles". For a very
  large N, MT5 refuses with "Invalid params" (the terminal reports a cap of
  100,000 bars). Instead, this loader walks BACKWARDS through time in small
  date windows, a few thousand candles at a time, until it has the number
  of candles requested or the broker has no older history.

  Each window is saved right away in small chunks, so memory use and the
  size of each database statement stay small. It is safe to re-run:
  candles that already exist are skipped.
"""

import time
from datetime import datetime, timedelta, timezone

import MetaTrader5 as mt5

from app.database.base import SessionLocal
from app.services import mt5_client
from app.services.data_collector import ensure_instrument, save_candles
from app.services.mt5_client import TIMEFRAME_MAP

CHUNK_SIZE = 5000

# Days covered by one window. Each is sized so a window holds at most about
# 5,760 candles, well under MT5's limits:
#   M15: 60 days x 96 = 5,760    H1: 240 days x 24 = 5,760    H4: 960 days x 6 = 5,760
WINDOW_DAYS = {"M15": 60, "H1": 240, "H4": 960}

# Stop when this many windows in a row come back empty (the broker has no older history).
MAX_EMPTY_WINDOWS = 3
RETRY_PAUSE_SECONDS = 2


def _fetch_window(symbol: str, timeframe: str, window_start, window_end):
    """
    Fetch candles between window_start and window_end. Returns a (possibly
    empty) array. Retries once on an empty answer, because MT5 may begin
    downloading older history when it is first asked for it.
    """
    mt5_timeframe = TIMEFRAME_MAP[timeframe]
    rates = []
    for attempt in range(2):
        rates = mt5.copy_rates_range(symbol, mt5_timeframe, window_start, window_end)
        if rates is None:
            error = mt5.last_error()
            if error[0] != 1:  # code 1 just means "success, nothing to return"
                raise RuntimeError(
                    f"copy_rates_range failed for {symbol} {timeframe}: {error}"
                )
            rates = []
        if len(rates) > 0:
            return rates
        if attempt == 0:
            time.sleep(RETRY_PAUSE_SECONDS)
    return rates


def _date_label(epoch_seconds):
    if epoch_seconds is None:
        return "n/a"
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d")


def collect_history(symbol: str, timeframe: str, count: int):
    """
    Walk backwards in date windows until about `count` candles have been
    fetched (it can overshoot by up to one window) or the broker's history
    runs out. Every window is saved as it arrives.
    """
    if timeframe not in WINDOW_DAYS:
        raise ValueError(
            f"collect_history supports {sorted(WINDOW_DAYS)}, got '{timeframe}'"
        )

    mt5_client.connect()
    db = SessionLocal()
    try:
        instrument = ensure_instrument(db, symbol)

        window = timedelta(days=WINDOW_DAYS[timeframe])
        # Start slightly in the future: MT5 candle times follow the broker's
        # clock, which can be ahead of UTC, so this makes sure the newest
        # candles are included.
        window_end = datetime.now(timezone.utc) + timedelta(days=2)

        fetched = 0
        inserted = 0
        windows_done = 0
        empty_in_a_row = 0
        oldest = None

        while fetched < count and empty_in_a_row < MAX_EMPTY_WINDOWS:
            window_start = window_end - window
            rates = _fetch_window(symbol, timeframe, window_start, window_end)

            if len(rates) == 0:
                empty_in_a_row += 1
            else:
                empty_in_a_row = 0
                fetched += len(rates)
                first_time = int(rates["time"].min())
                oldest = first_time if oldest is None else min(oldest, first_time)
                for start in range(0, len(rates), CHUNK_SIZE):
                    inserted += save_candles(
                        db, instrument, timeframe, rates[start:start + CHUNK_SIZE]
                    )

            windows_done += 1
            if windows_done % 5 == 0 and oldest is not None:
                print(f"  [{symbol} {timeframe}] {fetched} candles so far, back to {_date_label(oldest)}")

            window_end = window_start

        if fetched == 0:
            raise RuntimeError(
                f"MT5 returned no candles for {symbol} {timeframe}. "
                f"Check the symbol name and that MT5 is connected."
            )

        print(
            f"{symbol} [{timeframe}]: fetched {fetched} candles back to "
            f"{_date_label(oldest)}, inserted {inserted} new rows."
        )
        if fetched < count:
            print(
                f"  note: asked for {count} candles, but the broker's history "
                f"runs out at {fetched}."
            )
    finally:
        db.close()
        mt5_client.disconnect()