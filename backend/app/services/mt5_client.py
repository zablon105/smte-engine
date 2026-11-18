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
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
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
    Attempts initialization with credentials first, falling back to default running terminal,
    and self-heals authorization if necessary.
    """
    import os
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())
    login_str = os.getenv("MT5_LOGIN", "0")
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "")

    initialized = False
    if login_str.isdigit() and int(login_str) > 0 and password and server:
        initialized = mt5.initialize(login=int(login_str), password=password, server=server)

    if not initialized:
        initialized = mt5.initialize()

    if not initialized:
        error = mt5.last_error()
        raise RuntimeError(f"MT5 initialize() failed, error code = {error}")

    # Self-healing login check
    acc = mt5.account_info()
    if acc is None:
        if login_str.isdigit() and int(login_str) > 0 and password and server:
            mt5.login(login=int(login_str), password=password, server=server)

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
        mt5.symbol_select(symbol, True)
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


def get_account_info():
    """Returns MT5 account details including balance and equity."""
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"account_info failed: {mt5.last_error()}")
    return info


def get_symbol_tick(symbol: str):
    """Returns the latest tick (bid, ask, last, volume, time) for a symbol."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"symbol_info_tick failed for {symbol}: {mt5.last_error()}")
    return tick


def send_order(request: dict):
    """Sends a trade request to the MT5 broker terminal."""
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = mt5.last_error() if result is None else result.comment
        raise RuntimeError(f"order_send failed: {err}")
    return result


def modify_position(ticket: int, sl: float, tp: float):
    """Modifies the stop-loss and take-profit of an open MT5 position."""
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": sl,
        "tp": tp,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = mt5.last_error() if result is None else result.comment
        raise RuntimeError(f"modify_position failed for ticket {ticket}: {err}")
    return result


def get_positions(symbol: str = None):
    """Returns open positions, optionally filtered by symbol."""
    if symbol:
        return mt5.positions_get(symbol=symbol)
    return mt5.positions_get()


def get_position_deals(ticket: int):
    """Fetches deal history associated with a position ticket."""
    return mt5.history_deals_get(position=ticket)