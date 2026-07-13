"""
mt5_client.py
Handles connecting to the running MT5 terminal and provides
helper functions for fetching candle data.

Beginner note: MetaTrader5's Python package talks directly to
your already-open MT5 terminal (the JustMarkets one you have
open and logged into). It does NOT open its own separate
connection to your broker - it piggybacks on the terminal that's
already running on your machine.
"""

from datetime import datetime
import MetaTrader5 as mt5

# Maps the string names we use in our database/config to MT5's
# internal timeframe constants.
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


def connect():
    """
    Initializes the connection to the running MT5 terminal.
    Raises a RuntimeError with the MT5 error code if it fails.
    """
    if not mt5.initialize():
        error = mt5.last_error()
        raise RuntimeError(f"MT5 initialize() failed, error code = {error}")
    return True


def disconnect():
    mt5.shutdown()


def get_symbol_info(symbol: str):
    """
    Returns MT5's metadata for a symbol (digits, pip size, contract size).
    Returns None if the symbol isn't found.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    # Some brokers hide symbols from Market Watch by default; this
    # makes sure the symbol is selected/visible so data can be fetched.
    if not info.visible:
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
    return info


def fetch_candles_by_count(symbol: str, timeframe_str: str, count: int):
    """
    Fetches the most recent `count` candles for a symbol/timeframe.
    Returns a numpy structured array (MT5's native format).
    """
    timeframe = TIMEFRAME_MAP[timeframe_str]
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        raise RuntimeError(
            f"copy_rates_from_pos failed for {symbol} {timeframe_str}: {mt5.last_error()}"
        )
    return rates


def fetch_candles_by_range(symbol: str, timeframe_str: str, date_from: datetime, date_to: datetime):
    """
    Fetches all candles for a symbol/timeframe between two dates.
    Useful for historical backfills.
    """
    timeframe = TIMEFRAME_MAP[timeframe_str]
    rates = mt5.copy_rates_range(symbol, timeframe, date_from, date_to)
    if rates is None:
        raise RuntimeError(
            f"copy_rates_range failed for {symbol} {timeframe_str}: {mt5.last_error()}"
        )
    return rates