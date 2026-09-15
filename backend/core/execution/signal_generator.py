"""
signal_generator.py
Converts high-scoring CRT setups into actual trade signals with
entry, stop-loss, and take-profit levels.

Beginner note on the price logic:
  ENTRY: the manipulation candle's close - this is the point where
  price already reclaimed the range, confirming the sweep. Entering
  here (rather than trying to catch the exact wick) is more
  realistic and safer.

  STOP-LOSS: placed just beyond the manipulation wick's extreme
  (the actual low/high of the sweep), plus a small buffer. If price
  revisits that extreme, the premise of the setup (that liquidity
  was swept and won't be revisited) is invalidated.

  TAKE-PROFIT: calculated using a fixed risk-reward ratio off the
  stop distance. This is a placeholder target until a proper
  "next liquidity zone" or "next FVG" detector exists to set a
  more precise, structure-based target.
"""

from app.models.models import CrtSetup, SetupScore, TradeSignal


def _true_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10
    return point


def _signal_already_exists(db, crt_setup_id: int) -> bool:
    return db.query(TradeSignal).filter_by(crt_setup_id=crt_setup_id).first() is not None


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

    Only CONFIRMED (phase = 'DISTRIBUTION') setups are eligible -
    a MANIPULATION-only setup hasn't shown real follow-through yet,
    regardless of its confluence score, so it's not safe to trade.

    Returns the number of new TradeSignal rows created.
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

        manipulation_price = float(setup.manipulation_price)
        range_high = float(setup.range_high)
        range_low = float(setup.range_low)

        if setup.setup_direction == "BULLISH":
            direction = "BUY"
            entry_price = range_low  # approximate reclaim level; refined below
            stop_loss = manipulation_price - stop_buffer
            risk_distance = entry_price - stop_loss
            take_profit = entry_price + (risk_distance * risk_reward_ratio)
        else:  # BEARISH
            direction = "SELL"
            entry_price = range_high
            stop_loss = manipulation_price + stop_buffer
            risk_distance = stop_loss - entry_price
            take_profit = entry_price - (risk_distance * risk_reward_ratio)

        if risk_distance <= 0:
            continue  # safety check: invalid setup geometry, skip rather than create a broken signal

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