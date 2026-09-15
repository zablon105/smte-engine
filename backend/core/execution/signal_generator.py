"""
signal_generator.py
Converts high-scoring, CONFIRMED CRT setups into trade signals with
entry, stop-loss, and take-profit levels.

IMPORTANT FIX: entry price is now based on the candle that actually
CONFIRMED distribution (closed beyond the opposite range boundary) -
not the original range_low/range_high. Using the original range
level as "entry" was unrealistic: by the time a setup is confirmed,
price has already moved well past that level, so it isn't a price
a trader could actually still enter at. Using the confirmation
candle's close reflects the earliest realistic point a trader could
have acted on the now-confirmed setup.
"""

from app.models.models import Candle, CrtSetup, SetupScore, TradeSignal


def _true_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10
    return point


def _signal_already_exists(db, crt_setup_id: int) -> bool:
    return db.query(TradeSignal).filter_by(crt_setup_id=crt_setup_id).first() is not None


def _find_confirmation_candle(db, setup: CrtSetup, timeframe: str = "M15", limit: int = 1000):
    """
    Finds the actual candle that confirmed distribution (closed
    beyond the opposite range boundary). Returns the Candle object,
    or None if not found within the available forward data.
    """
    candles = (
        db.query(Candle)
        .filter(
            Candle.instrument_id == setup.instrument_id,
            Candle.timeframe == timeframe,
            Candle.open_time > setup.detected_at,
        )
        .order_by(Candle.open_time.asc())
        .limit(limit)
        .all()
    )

    range_high = float(setup.range_high)
    range_low = float(setup.range_low)

    for candle in candles:
        close = float(candle.close)
        if setup.setup_direction == "BULLISH" and close > range_high:
            return candle
        elif setup.setup_direction == "BEARISH" and close < range_low:
            return candle
    return None


def generate_signals(
    db,
    instrument_id: int,
    min_total_score: int = 10,
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 3.0,
    digits: int = 5,
    point: float = 0.00001,
) -> int:
    """
    Scans setup_scores for setups meeting the minimum score threshold
    and generates a TradeSignal for each one that doesn't already
    have one.

    Entry is the CONFIRMATION candle's close (the realistic point a
    trader could act, now that distribution is confirmed) - not the
    original range level. Stop-loss is still anchored to the
    manipulation wick's extreme (the invalidation point). Take-profit
    is a fixed risk-reward multiple of that stop distance from entry.
    """
    true_pip = _true_pip_size(digits, point)
    stop_buffer = stop_buffer_pips * true_pip

    qualifying = (
        db.query(CrtSetup, SetupScore)
        .join(SetupScore, SetupScore.crt_setup_id == CrtSetup.id)
        .filter(
            CrtSetup.instrument_id == instrument_id,
            CrtSetup.phase == "DISTRIBUTION",
            CrtSetup.is_valid == True,
            SetupScore.total_score >= min_total_score,
        )
        .all()
    )

    created_count = 0

    for setup, score in qualifying:
        if _signal_already_exists(db, setup.id):
            continue

        confirmation_candle = _find_confirmation_candle(db, setup)
        if confirmation_candle is None:
            continue  # shouldn't happen since phase=DISTRIBUTION implies this exists, but guard anyway

        manipulation_price = float(setup.manipulation_price)
        entry_price = float(confirmation_candle.close)

        if setup.setup_direction == "BULLISH":
            direction = "BUY"
            stop_loss = manipulation_price - stop_buffer
            risk_distance = entry_price - stop_loss
            take_profit = entry_price + (risk_distance * risk_reward_ratio)
        else:
            direction = "SELL"
            stop_loss = manipulation_price + stop_buffer
            risk_distance = stop_loss - entry_price
            take_profit = entry_price - (risk_distance * risk_reward_ratio)

        if risk_distance <= 0:
            continue  # invalid geometry (e.g. entry already beyond stop), skip

        signal = TradeSignal(
            instrument_id=instrument_id,
            crt_setup_id=setup.id,
            setup_score_id=score.id,
            signal_direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="PENDING",
        )
        db.add(signal)
        created_count += 1

    db.commit()
    return created_count