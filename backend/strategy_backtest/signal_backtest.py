"""
signal_backtest.py
Backtest for generated trade signals, corrected to avoid look-ahead
bias: TP/SL checking starts from AFTER the candle that actually
confirmed DISTRIBUTION phase - not from the original manipulation
candle. Starting earlier would let the backtest "see" the same
favorable move that already qualified the setup as confirmed,
artificially inflating the win rate.
"""

from app.models.models import Candle, CrtSetup, TradeSignal


def _fetch_forward_candles(db, instrument_id, timeframe, start_time, limit=1000):
    return (
        db.query(Candle)
        .filter(
            Candle.instrument_id == instrument_id,
            Candle.timeframe == timeframe,
            Candle.open_time > start_time,
        )
        .order_by(Candle.open_time.asc())
        .limit(limit)
        .all()
    )


def _find_confirmation_time(db, setup: CrtSetup, timeframe: str):
    """
    Re-derives the exact candle that confirmed DISTRIBUTION (closed
    beyond the opposite range boundary), so the backtest can start
    AFTER that point instead of at the manipulation candle.
    """
    candles = _fetch_forward_candles(db, setup.instrument_id, timeframe, setup.detected_at)
    range_high = float(setup.range_high)
    range_low = float(setup.range_low)

    for candle in candles:
        close = float(candle.close)
        if setup.setup_direction == "BULLISH" and close > range_high:
            return candle.open_time
        elif setup.setup_direction == "BEARISH" and close < range_low:
            return candle.open_time
    return None  # not confirmed within available data


def backtest_signal(db, signal: TradeSignal, setup: CrtSetup, timeframe: str = "M15"):
    confirmation_time = _find_confirmation_time(db, setup, timeframe)
    if confirmation_time is None:
        return {"result": "NO_OUTCOME_YET", "hit_at": None}

    # Only look at candles STRICTLY AFTER the confirmation candle -
    # this is the earliest point a trader could realistically have
    # acted on the confirmed signal.
    candles = _fetch_forward_candles(db, signal.instrument_id, timeframe, confirmation_time)

    entry = float(signal.entry_price)
    stop = float(signal.stop_loss)
    target = float(signal.take_profit)
    direction = signal.signal_direction

    for candle in candles:
        high = float(candle.high)
        low = float(candle.low)

        if direction == "BUY":
            if low <= stop:
                return {"result": "SL_HIT", "hit_at": candle.open_time}
            if high >= target:
                return {"result": "TP_HIT", "hit_at": candle.open_time}
        else:
            if high >= stop:
                return {"result": "SL_HIT", "hit_at": candle.open_time}
            if low <= target:
                return {"result": "TP_HIT", "hit_at": candle.open_time}

    return {"result": "NO_OUTCOME_YET", "hit_at": None}


def backtest_all_signals(db, instrument_id: int, timeframe: str = "M15"):
    signals = db.query(TradeSignal).filter_by(instrument_id=instrument_id).all()
    results = []

    for signal in signals:
        setup = db.query(CrtSetup).filter_by(id=signal.crt_setup_id).first()
        if setup is None:
            continue

        outcome = backtest_signal(db, signal, setup, timeframe)
        results.append({
            "signal_id": signal.id,
            "direction": signal.signal_direction,
            "entry_price": float(signal.entry_price),
            "stop_loss": float(signal.stop_loss),
            "take_profit": float(signal.take_profit),
            "detected_at": setup.detected_at,
            "result": outcome["result"],
            "hit_at": outcome["hit_at"],
        })

    return results