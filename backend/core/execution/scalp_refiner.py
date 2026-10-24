"""
scalp_refiner.py
Precision Lower-Timeframe (LTF) Scalping & Entry Refinement Engine.

Transforms Higher-Timeframe (M15 / H1) Institutional Setups into razor-sharp,
high-win-rate scalping entries on M1, M3, and M5 timeframes.

Institutional Scalping Methodology:
  1. Higher-Timeframe (HTF) Macro Bias:
     Identifies that an M15 / H1 CRT manipulation or liquidity sweep has occurred.
     This establishes the directional bias (BULLISH or BEARISH) and macro invalidation level.

  2. Lower-Timeframe (LTF: M1/M3/M5) Execution Signature:
     Instead of entering after an entire M15 candle closes far away (risking 20-35 pips),
     we zoom into the LTF immediately following the manipulation sweep:
       a) LTF Market Structure Shift (MSS / CHOCH): Price breaks the micro swing high/low.
       b) Institutional Displacement: The shift occurs with strong body momentum (body >= 50% of range).
       c) LTF Fair Value Gap (FVG): The displacement leaves an imbalance / liquidity void.
       d) Precision Entry: Limit/market entry at the LTF FVG or displacement close.
       e) Ultra-Tight Stop Loss: Anchored strictly to the LTF sweep wick (+ spread buffer).

  3. Scalping Edge:
     - Stop distance shrinks from 20-35 pips down to 5-10 pips.
     - A 2.0R take-profit requires only a 10-20 pip move, routinely hit in minutes.
     - False sweeps without an LTF displacement MSS are rejected before any capital is risked.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any

from app.models.models import Candle, CrtSetup, Instrument, TradeSignal


@dataclass
class ScalpEntry:
    setup_id: int
    instrument_id: int
    direction: str              # "BUY" or "SELL"
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_pips: float
    reward_pips: float
    risk_reward_ratio: float
    entry_time: datetime
    execution_timeframe: str    # "M1", "M3", or "M5"
    has_fvg: bool
    fvg_top: Optional[float]
    fvg_bottom: Optional[float]
    displacement_candle_index: int
    mss_swing_price: float
    invalidation_price: float


def _true_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10
    return point


def detect_ltf_mss_and_fvg(
    ltf_candles: List[Any],
    direction: str,
    sweep_price: float,
    pip_size: float = 0.0001,
    min_body_ratio: float = 0.50,
    max_search_candles: int = 20,
) -> Optional[Dict[str, Any]]:
    """
    Scans a chronological list of LTF candles immediately following a sweep
    to find an institutional Market Structure Shift (MSS) and Fair Value Gap (FVG).

    Returns a dictionary of refined scalp entry parameters, or None if no valid MSS occurred.
    """
    if len(ltf_candles) < 3:
        return None

    # Limit search to the first N candles after the sweep
    search_candles = ltf_candles[:max_search_candles]

    # Calculate average candle range for displacement comparison
    ranges = [float(c.high) - float(c.low) for c in search_candles]
    avg_range = sum(ranges) / len(ranges) if ranges else pip_size

    # 1. Identify local swing points prior to the displacement
    # For BULLISH: Find the lowest point (the sweep) and the last micro swing high before/at the sweep
    # For BEARISH: Find the highest point (the sweep) and the last micro swing low before/at the sweep

    if direction == "BULLISH":
        # Price swept liquidity downwards; we look for a bullish MSS (break above a swing high)
        lowest_idx = 0
        lowest_low = float(search_candles[0].low)
        for i, c in enumerate(search_candles):
            if float(c.low) < lowest_low:
                lowest_low = float(c.low)
                lowest_idx = i

        # Look for the reference swing high between candle 0 and the lowest low,
        # or the high of the sweep candle itself
        ref_swing_high = float(search_candles[0].high)
        for i in range(lowest_idx + 1):
            if float(search_candles[i].high) > ref_swing_high:
                ref_swing_high = float(search_candles[i].high)

        # Look for bullish displacement breaking above ref_swing_high after lowest_idx
        for i in range(lowest_idx, len(search_candles)):
            c = search_candles[i]
            c_open = float(c.open)
            c_close = float(c.close)
            c_high = float(c.high)
            c_low = float(c.low)
            body = c_close - c_open
            candle_range = c_high - c_low

            # Bullish displacement criteria:
            # 1. Bullish close (close > open)
            # 2. Breaks above ref_swing_high (MSS)
            # 3. Strong body (body >= 50% of range) and range >= 0.8 * avg_range
            is_break = c_close > ref_swing_high
            is_displacement = (
                body > 0
                and candle_range > 0
                and (body / candle_range) >= min_body_ratio
                and candle_range >= (avg_range * 0.8)
            )

            if is_break and is_displacement:
                # Check for Bullish FVG in the 3-candle sequence ending at i
                # Candle 1 (i-2), Candle 2 (i-1 displacement), Candle 3 (i)
                has_fvg = False
                fvg_top = None
                fvg_bottom = None

                if i >= 2:
                    c1 = search_candles[i - 2]
                    c3 = search_candles[i]
                    if float(c3.low) > float(c1.high):
                        has_fvg = True
                        fvg_top = float(c3.low)
                        fvg_bottom = float(c1.high)

                # Entry: If FVG exists, enter at the FVG top (or 50% equilibrium), else at close of displacement
                entry_price = fvg_top if (has_fvg and fvg_top) else c_close
                stop_loss = lowest_low - (pip_size * 2.0)  # 2 pip buffer below sweep wick

                return {
                    "direction": "BUY",
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "entry_time": c.open_time,
                    "has_fvg": has_fvg,
                    "fvg_top": fvg_top,
                    "fvg_bottom": fvg_bottom,
                    "displacement_index": i,
                    "mss_swing_price": ref_swing_high,
                    "invalidation_price": lowest_low,
                }

    else:  # BEARISH
        # Price swept liquidity upwards; we look for a bearish MSS (break below a swing low)
        highest_idx = 0
        highest_high = float(search_candles[0].high)
        for i, c in enumerate(search_candles):
            if float(c.high) > highest_high:
                highest_high = float(c.high)
                highest_idx = i

        ref_swing_low = float(search_candles[0].low)
        for i in range(highest_idx + 1):
            if float(search_candles[i].low) < ref_swing_low:
                ref_swing_low = float(search_candles[i].low)

        # Look for bearish displacement breaking below ref_swing_low after highest_idx
        for i in range(highest_idx, len(search_candles)):
            c = search_candles[i]
            c_open = float(c.open)
            c_close = float(c.close)
            c_high = float(c.high)
            c_low = float(c.low)
            body = c_open - c_close
            candle_range = c_high - c_low

            is_break = c_close < ref_swing_low
            is_displacement = (
                body > 0
                and candle_range > 0
                and (body / candle_range) >= min_body_ratio
                and candle_range >= (avg_range * 0.8)
            )

            if is_break and is_displacement:
                has_fvg = False
                fvg_top = None
                fvg_bottom = None

                if i >= 2:
                    c1 = search_candles[i - 2]
                    c3 = search_candles[i]
                    if float(c1.low) > float(c3.high):
                        has_fvg = True
                        fvg_top = float(c1.low)
                        fvg_bottom = float(c3.high)

                entry_price = fvg_bottom if (has_fvg and fvg_bottom) else c_close
                stop_loss = highest_high + (pip_size * 2.0)  # 2 pip buffer above sweep wick

                return {
                    "direction": "SELL",
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "entry_time": c.open_time,
                    "has_fvg": has_fvg,
                    "fvg_top": fvg_top,
                    "fvg_bottom": fvg_bottom,
                    "displacement_index": i,
                    "mss_swing_price": ref_swing_low,
                    "invalidation_price": highest_high,
                }

    return None


def refine_setup_to_scalp_entry(
    db,
    setup: CrtSetup,
    instrument: Instrument,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: Optional[float] = None,
    live_candles: Optional[List[Any]] = None,
) -> Optional[ScalpEntry]:
    """
    Takes an HTF CrtSetup and refines it into a high-precision scalp entry
    using lower timeframe (M1, M3, or M5) candles.

    If `live_candles` is provided, evaluates against those (e.g. pulled from MT5).
    Otherwise queries historical LTF candles stored in PostgreSQL.
    """
    true_pip = _true_pip_size(instrument.digits, float(instrument.pip_size))

    # Pull LTF candles
    if live_candles is not None:
        ltf_candles = live_candles
    else:
        # Query candles strictly after detected_at (the manipulation start)
        ltf_candles = (
            db.query(Candle)
            .filter(
                Candle.instrument_id == setup.instrument_id,
                Candle.timeframe == ltf,
                Candle.open_time >= setup.detected_at,
            )
            .order_by(Candle.open_time.asc())
            .limit(30)
            .all()
        )

    if not ltf_candles:
        return None

    sweep_price = float(setup.manipulation_price) if setup.manipulation_price else float(setup.range_low if setup.setup_direction == "BULLISH" else setup.range_high)

    result = detect_ltf_mss_and_fvg(
        ltf_candles=ltf_candles,
        direction=setup.setup_direction,
        sweep_price=sweep_price,
        pip_size=true_pip,
    )

    if result is None:
        return None

    entry_price = float(result["entry_price"])
    stop_loss = float(result["stop_loss"])
    direction = result["direction"]

    if direction == "BUY":
        risk_distance = entry_price - stop_loss
        take_profit = entry_price + (risk_distance * risk_reward_ratio)
    else:
        risk_distance = stop_loss - entry_price
        take_profit = entry_price - (risk_distance * risk_reward_ratio)

    if risk_distance <= 0:
        return None

    risk_pips = risk_distance / true_pip if true_pip > 0 else 0.0
    reward_pips = (abs(take_profit - entry_price)) / true_pip if true_pip > 0 else 0.0

    # Max risk filter for scalping (e.g. reject scalps with stop > 15 pips)
    if max_risk_pips is not None and risk_pips > max_risk_pips:
        return None

    return ScalpEntry(
        setup_id=setup.id,
        instrument_id=instrument.id,
        direction=direction,
        entry_price=round(entry_price, instrument.digits),
        stop_loss=round(stop_loss, instrument.digits),
        take_profit=round(take_profit, instrument.digits),
        risk_pips=round(risk_pips, 1),
        reward_pips=round(reward_pips, 1),
        risk_reward_ratio=risk_reward_ratio,
        entry_time=result["entry_time"],
        execution_timeframe=ltf,
        has_fvg=result["has_fvg"],
        fvg_top=result["fvg_top"],
        fvg_bottom=result["fvg_bottom"],
        displacement_candle_index=result["displacement_index"],
        mss_swing_price=result["mss_swing_price"],
        invalidation_price=result["invalidation_price"],
    )
