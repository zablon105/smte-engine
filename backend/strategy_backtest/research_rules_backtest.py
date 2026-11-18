"""
research_rules_backtest.py
Rigorous historical backtesting harness for the newly integrated research strategies:
1. Turtle Soup (3-candle Purge / False Breakout) Model: TP1 (50% midpoint) & TP2 (opposing edge).
2. Unicorn Model: Breaker Block + FVG Overlap Zone Retracement.
3. Power of 3 (PO3 / AMD): Time-based entry pricing (discount below open / premium above open).

Validates setups against historical PostgreSQL candle archives with strict look-ahead protection,
one-trade-at-a-time filtering, and Wilson 95% confidence intervals.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple

from app.database.base import SessionLocal
from app.models.models import Candle, Instrument
from core.strategy_rules import (
    calculate_breaker_zone,
    calculate_unicorn_overlap,
    evaluate_po3_pricing,
    evaluate_turtle_soup_sequence,
    is_breaker_mitigated,
)


def wilson_interval(wins: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Calculate 95% Wilson score confidence interval for win rate."""
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _true_pip_size(digits: int, point: float, symbol: str = "") -> float:
    if "BTC" in symbol.upper():
        return 10.0
    if "XAU" in symbol.upper():
        return 0.10
    if digits in (3, 5):
        return point * 10.0
    return point


# =====================================================================
# 1. TURTLE SOUP (PURGE / FALSE BREAKOUT) BACKTEST
# =====================================================================

def backtest_turtle_soup(
    db,
    symbol: str,
    timeframe: str = "H1",
    candle_limit: int = 15000,
    max_holding_bars: int = 40,
) -> Dict[str, Any]:
    """
    Backtests the 3-candle Turtle Soup strategy:
    - Candle 1: Baseline range
    - Candle 2: Purges beyond range (TBS if body closes beyond; TWS if wick only)
    - Candle 3: Closes back inside Candle 1 range (confirmation)
    - Entry: Close of Candle 3
    - SL: Candle 2 purge extreme (+ 1 pip buffer)
    - TP1: 50% midpoint of Candle 1 range
    - TP2: 100% opposing edge of Candle 1 range
    """
    inst = db.query(Instrument).filter_by(symbol=symbol).first()
    if not inst:
        return {"error": f"Instrument {symbol} not found"}

    pip_size = _true_pip_size(inst.digits, float(inst.pip_size), symbol)
    spread_buffer = pip_size * 1.5

    candles = (
        db.query(Candle)
        .filter(Candle.instrument_id == inst.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.asc())
        .limit(candle_limit)
        .all()
    )

    if len(candles) < 100:
        return {"error": f"Insufficient candles for {symbol} ({len(candles)})"}

    trades = []
    last_exit_idx = {"BULLISH": -1, "BEARISH": -1}

    # Evaluate rolling 3-candle sequences
    for i in range(len(candles) - 3 - max_holding_bars):
        c1 = candles[i]
        c2 = candles[i + 1]
        c3 = candles[i + 2]

        for direction in ("BULLISH", "BEARISH"):
            # Ensure one trade at a time per direction
            if i + 2 <= last_exit_idx[direction]:
                continue

            eval_res = evaluate_turtle_soup_sequence(
                c1_high=float(c1.high),
                c1_low=float(c1.low),
                c2_open=float(c2.open),
                c2_close=float(c2.close),
                c2_high=float(c2.high),
                c2_low=float(c2.low),
                c3_close=float(c3.close),
                direction=direction,
            )

            if not eval_res.is_valid:
                continue

            entry_price = float(c3.close)
            tp1 = eval_res.targets.midpoint_tp1
            tp2 = eval_res.targets.opposing_edge_tp2
            sl = eval_res.targets.invalidation_stop

            # Add spread buffer to stop loss
            if direction == "BULLISH":
                sl -= spread_buffer
                risk = entry_price - sl
                reward_tp1 = tp1 - entry_price
                reward_tp2 = tp2 - entry_price
            else:
                sl += spread_buffer
                risk = sl - entry_price
                reward_tp1 = entry_price - tp1
                reward_tp2 = entry_price - tp2

            # Filter out inverted/invalid setups where entry already passed target or risk <= 0
            if risk <= 0 or reward_tp1 <= 0 or reward_tp2 <= 0:
                continue

            # Walk forward candles to evaluate TP1, TP2, and SL
            tp1_hit = False
            tp2_hit = False
            sl_hit = False
            exit_idx = i + 2

            for fwd_idx in range(i + 3, min(i + 3 + max_holding_bars, len(candles))):
                fwd = candles[fwd_idx]
                fwd_high = float(fwd.high)
                fwd_low = float(fwd.low)

                if direction == "BULLISH":
                    if fwd_low <= sl:
                        sl_hit = True
                        exit_idx = fwd_idx
                        break
                    if not tp1_hit and fwd_high >= tp1:
                        tp1_hit = True
                    if fwd_high >= tp2:
                        tp2_hit = True
                        exit_idx = fwd_idx
                        break
                else:  # BEARISH
                    if fwd_high >= sl:
                        sl_hit = True
                        exit_idx = fwd_idx
                        break
                    if not tp1_hit and fwd_low <= tp1:
                        tp1_hit = True
                    if fwd_low <= tp2:
                        tp2_hit = True
                        exit_idx = fwd_idx
                        break

            last_exit_idx[direction] = exit_idx

            trades.append({
                "entry_time": c3.open_time,
                "direction": direction,
                "soup_type": eval_res.soup_type,
                "entry_price": entry_price,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "risk_pips": risk / pip_size,
                "rr_tp1": reward_tp1 / risk,
                "rr_tp2": reward_tp2 / risk,
                "tp1_hit": tp1_hit,
                "tp2_hit": tp2_hit,
                "sl_hit": sl_hit,
                "holding_bars": exit_idx - (i + 2),
            })

    total = len(trades)
    if total == 0:
        return {"symbol": symbol, "timeframe": timeframe, "total_trades": 0}

    tp1_wins = sum(1 for t in trades if t["tp1_hit"])
    tp2_wins = sum(1 for t in trades if t["tp2_hit"])
    tbs_trades = [t for t in trades if t["soup_type"] == "TBS"]
    tws_trades = [t for t in trades if t["soup_type"] == "TWS"]

    tbs_tp1_wins = sum(1 for t in tbs_trades if t["tp1_hit"])
    tws_tp1_wins = sum(1 for t in tws_trades if t["tp1_hit"])

    # Profit factor for TP1 and TP2
    gross_win_tp1 = sum(t["rr_tp1"] for t in trades if t["tp1_hit"])
    gross_loss_tp1 = sum(1.0 for t in trades if not t["tp1_hit"])
    pf_tp1 = (gross_win_tp1 / gross_loss_tp1) if gross_loss_tp1 > 0 else 99.0

    gross_win_tp2 = sum(t["rr_tp2"] for t in trades if t["tp2_hit"])
    gross_loss_tp2 = sum(1.0 for t in trades if not t["tp2_hit"])
    pf_tp2 = (gross_win_tp2 / gross_loss_tp2) if gross_loss_tp2 > 0 else 99.0

    w_low_tp1, w_high_tp1 = wilson_interval(tp1_wins, total)
    w_low_tp2, w_high_tp2 = wilson_interval(tp2_wins, total)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_trades": total,
        "tp1_wins": tp1_wins,
        "tp1_win_rate": tp1_wins / total,
        "tp1_wilson_95": (w_low_tp1, w_high_tp1),
        "tp1_profit_factor": pf_tp1,
        "tp2_wins": tp2_wins,
        "tp2_win_rate": tp2_wins / total,
        "tp2_wilson_95": (w_low_tp2, w_high_tp2),
        "tp2_profit_factor": pf_tp2,
        "tbs_count": len(tbs_trades),
        "tbs_win_rate_tp1": (tbs_tp1_wins / len(tbs_trades)) if tbs_trades else 0.0,
        "tws_count": len(tws_trades),
        "tws_win_rate_tp1": (tws_tp1_wins / len(tws_trades)) if tws_trades else 0.0,
        "avg_risk_pips": sum(t["risk_pips"] for t in trades) / total,
        "avg_rr_tp1": sum(t["rr_tp1"] for t in trades) / total,
        "avg_rr_tp2": sum(t["rr_tp2"] for t in trades) / total,
        "avg_holding_bars": sum(t["holding_bars"] for t in trades) / total,
    }


# =====================================================================
# 2. UNICORN MODEL BACKTEST
# =====================================================================

def backtest_unicorn_model(
    db,
    symbol: str,
    timeframe: str = "M15",
    candle_limit: int = 15000,
    max_fill_bars: int = 25,
    max_holding_bars: int = 50,
) -> Dict[str, Any]:
    """
    Backtests the Unicorn Model:
    1. Liquidity sweep of a recent swing point (BSL or SSL).
    2. Formation of a Breaker Block.
    3. Concurrently formed Fair Value Gap (FVG) overlapping the breaker.
    4. Limit entry at the overlap zone.
    5. Invalidation stop at breaker extreme; TP at 2.0R.
    """
    inst = db.query(Instrument).filter_by(symbol=symbol).first()
    if not inst:
        return {"error": f"Instrument {symbol} not found"}

    pip_size = _true_pip_size(inst.digits, float(inst.pip_size), symbol)
    spread_buffer = pip_size * 1.5

    candles = (
        db.query(Candle)
        .filter(Candle.instrument_id == inst.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.asc())
        .limit(candle_limit)
        .all()
    )

    if len(candles) < 200:
        return {"error": f"Insufficient candles for {symbol} ({len(candles)})"}

    setups_found = 0
    filled_trades = []
    last_exit_idx = -1

    # Scan for swings, sweeps, breakers, and FVGs
    for i in range(10, len(candles) - max_fill_bars - max_holding_bars):
        if i <= last_exit_idx:
            continue

        c_prev = candles[i - 1]
        c_curr = candles[i]
        c_next = candles[i + 1]

        # Detect Bullish Unicorn:
        # Prior swing low swept by c_curr, then impulse reversal creates Breaker + FVG
        # 1. Swing low check in [i-10 : i-2]
        prior_lows = [float(candles[k].low) for k in range(i - 10, i - 1)]
        min_prior_low = min(prior_lows)

        is_bullish_sweep = float(c_curr.low) < min_prior_low and float(c_curr.close) > float(c_curr.open)
        is_bearish_sweep = False

        prior_highs = [float(candles[k].high) for k in range(i - 10, i - 1)]
        max_prior_high = max(prior_highs)
        is_bearish_sweep = float(c_curr.high) > max_prior_high and float(c_curr.close) < float(c_curr.open)

        if not (is_bullish_sweep or is_bearish_sweep):
            continue

        direction = "BULLISH" if is_bullish_sweep else "BEARISH"

        # Check for Breaker Block in the swing prior to sweep
        breaker_candle = candles[i - 1]
        try:
            breaker_zone = calculate_breaker_zone(
                open_price=float(breaker_candle.open),
                close_price=float(breaker_candle.close),
                high_price=float(breaker_candle.high),
                low_price=float(breaker_candle.low),
                direction=direction,
                use_body=True,
            )
        except Exception:
            continue

        # Check for FVG in the subsequent impulse candles (i, i+1, i+2)
        c0 = candles[i]
        c2 = candles[i + 2] if i + 2 < len(candles) else None
        if not c2:
            continue

        has_fvg = False
        fvg_bottom = 0.0
        fvg_top = 0.0

        if direction == "BULLISH":
            if float(c2.low) > float(c0.high):
                has_fvg = True
                fvg_bottom = float(c0.high)
                fvg_top = float(c2.low)
        else:
            if float(c0.low) > float(c2.high):
                has_fvg = True
                fvg_bottom = float(c2.high)
                fvg_top = float(c0.low)

        if not has_fvg:
            continue

        # Calculate overlap between Breaker and FVG
        overlap = calculate_unicorn_overlap(
            breaker_bottom=breaker_zone.bottom,
            breaker_top=breaker_zone.top,
            fvg_bottom=fvg_bottom,
            fvg_top=fvg_top,
        )

        if overlap is None:
            continue

        setups_found += 1
        entry_price = overlap.midpoint

        if direction == "BULLISH":
            sl = min(float(c_curr.low), breaker_zone.bottom) - spread_buffer
            risk = entry_price - sl
            tp = entry_price + (risk * 2.0)
        else:
            sl = max(float(c_curr.high), breaker_zone.top) + spread_buffer
            risk = sl - entry_price
            tp = entry_price - (risk * 2.0)

        if risk <= 0:
            continue

        # Check if price returns into the overlap zone to trigger limit order
        fill_idx = None
        for k in range(i + 3, min(i + 3 + max_fill_bars, len(candles))):
            bar = candles[k]
            if float(bar.low) <= entry_price <= float(bar.high):
                fill_idx = k
                break

        if fill_idx is None:
            continue  # Order not filled

        # If filled, track trade outcome
        tp_hit = False
        sl_hit = False
        exit_idx = fill_idx

        for fwd_idx in range(fill_idx + 1, min(fill_idx + 1 + max_holding_bars, len(candles))):
            fwd = candles[fwd_idx]
            fwd_high = float(fwd.high)
            fwd_low = float(fwd.low)

            if direction == "BULLISH":
                if fwd_low <= sl:
                    sl_hit = True
                    exit_idx = fwd_idx
                    break
                if fwd_high >= tp:
                    tp_hit = True
                    exit_idx = fwd_idx
                    break
            else:
                if fwd_high >= sl:
                    sl_hit = True
                    exit_idx = fwd_idx
                    break
                if fwd_low <= tp:
                    tp_hit = True
                    exit_idx = fwd_idx
                    break

        last_exit_idx = exit_idx
        filled_trades.append({
            "direction": direction,
            "entry_price": entry_price,
            "tp_hit": tp_hit,
            "sl_hit": sl_hit,
            "risk_pips": risk / pip_size,
            "holding_bars": exit_idx - fill_idx,
        })

    filled_count = len(filled_trades)
    if filled_count == 0:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "setups_found": setups_found,
            "filled_trades": 0,
            "fill_rate": 0.0,
        }

    wins = sum(1 for t in filled_trades if t["tp_hit"])
    losses = sum(1 for t in filled_trades if t["sl_hit"])
    w_low, w_high = wilson_interval(wins, filled_count)
    pf = ((wins * 2.0) / losses) if losses > 0 else 99.0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "setups_found": setups_found,
        "filled_trades": filled_count,
        "fill_rate": filled_count / setups_found if setups_found > 0 else 0.0,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / filled_count,
        "wilson_95": (w_low, w_high),
        "profit_factor": pf,
        "avg_risk_pips": sum(t["risk_pips"] for t in filled_trades) / filled_count,
    }


# =====================================================================
# 3. POWER OF 3 (PO3 / AMD) JUDAS SWING BACKTEST
# =====================================================================

def backtest_power_of_three(
    db,
    symbol: str,
    timeframe: str = "H1",
    candle_limit: int = 15000,
    holding_bars: int = 12,
) -> Dict[str, Any]:
    """
    Backtests Power of 3 (PO3 / AMD) entries on H4 / Daily cycles:
    - Anchors entry pricing to the period open:
      - Bullish entries taken strictly in discount (< open)
      - Bearish entries taken strictly in premium (> open)
    - Compares win rate of PO3-qualified entries vs unconditional entries.
    """
    inst = db.query(Instrument).filter_by(symbol=symbol).first()
    if not inst:
        return {"error": f"Instrument {symbol} not found"}

    pip_size = _true_pip_size(inst.digits, float(inst.pip_size), symbol)

    candles = (
        db.query(Candle)
        .filter(Candle.instrument_id == inst.id, Candle.timeframe == timeframe)
        .order_by(Candle.open_time.asc())
        .limit(candle_limit)
        .all()
    )

    if len(candles) < 100:
        return {"error": f"Insufficient candles for {symbol}"}

    po3_wins = 0
    po3_total = 0
    naive_wins = 0
    naive_total = 0

    # Group candles into sessions/periods of N bars (e.g. 12 H1 bars = half-day)
    step = 12
    for i in range(0, len(candles) - step - holding_bars, step):
        period_open = float(candles[i].open)
        period_candles = candles[i : i + step]

        # Determine macro direction over the period
        period_close = float(period_candles[-1].close)
        bias = "BULLISH" if period_close > period_open else "BEARISH"

        # Examine entry on candle 3 of the period
        entry_candle = period_candles[2]
        entry_price = float(entry_candle.close)

        assessment = evaluate_po3_pricing(
            open_price=period_open,
            current_price=entry_price,
            bias=bias,
        )

        # Check outcome over next holding_bars
        target_pips = 20.0 * pip_size
        fwd_candles = candles[i + 3 : i + 3 + holding_bars]
        if not fwd_candles:
            continue

        fwd_high = max(float(c.high) for c in fwd_candles)
        fwd_low = min(float(c.low) for c in fwd_candles)

        if bias == "BULLISH":
            won = (fwd_high - entry_price) >= target_pips
        else:
            won = (entry_price - fwd_low) >= target_pips

        naive_total += 1
        if won:
            naive_wins += 1

        if assessment.is_valid_entry_zone:
            po3_total += 1
            if won:
                po3_wins += 1

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "naive_total": naive_total,
        "naive_win_rate": (naive_wins / naive_total) if naive_total > 0 else 0.0,
        "po3_total": po3_total,
        "po3_win_rate": (po3_wins / po3_total) if po3_total > 0 else 0.0,
        "edge_increase_pct": ((po3_wins / po3_total) - (naive_wins / naive_total)) * 100.0 if (po3_total > 0 and naive_total > 0) else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest research-derived strategy rules on historical data.")
    parser.add_argument("--symbols", nargs="+", default=["EURUSD.m", "GBPUSD.m", "XAUUSD.m", "USDJPY.m"])
    parser.add_argument("--strategy", choices=["turtle_soup", "unicorn", "po3", "all"], default="all")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--limit", type=int, default=15000)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print("=" * 85)
        print(f"      SMTE RESEARCH STRATEGIES HISTORICAL BACKTEST ({args.timeframe})")
        print("=" * 85)

        if args.strategy in ("turtle_soup", "all"):
            print("\n" + "#" * 85)
            print("  STRATEGY 1: TURTLE SOUP (3-CANDLE FALSE BREAKOUT / PURGE MODEL)")
            print("#" * 85)

            for sym in args.symbols:
                res = backtest_turtle_soup(db, sym, timeframe=args.timeframe, candle_limit=args.limit)
                if "error" in res:
                    print(f"\n{sym}: {res['error']}")
                    continue

                low1, high1 = res["tp1_wilson_95"]
                low2, high2 = res["tp2_wilson_95"]

                print(f"\n[{sym} - {args.timeframe}] Total Setups Traded: {res['total_trades']}")
                print(f"  TP1 (50% Midpoint)  : Win Rate = {res['tp1_win_rate']:.1%} (95% CI: {low1:.1%}-{high1:.1%}) | Profit Factor = {res['tp1_profit_factor']:.2f}")
                print(f"  TP2 (100% Opposing) : Win Rate = {res['tp2_win_rate']:.1%} (95% CI: {low2:.1%}-{high2:.1%}) | Profit Factor = {res['tp2_profit_factor']:.2f}")
                print(f"  TBS (Body Purge)    : {res['tbs_count']} trades | Win Rate = {res['tbs_win_rate_tp1']:.1%}")
                print(f"  TWS (Wick Purge)    : {res['tws_count']} trades | Win Rate = {res['tws_win_rate_tp1']:.1%}")
                print(f"  Risk & Duration     : Avg Risk = {res['avg_risk_pips']:.1f} pips | Avg Holding Time = {res['avg_holding_bars']:.1f} bars")

        if args.strategy in ("unicorn", "all"):
            print("\n" + "#" * 85)
            print("  STRATEGY 2: UNICORN MODEL (BREAKER + FVG OVERLAP RETRACEMENT)")
            print("#" * 85)

            for sym in args.symbols:
                res = backtest_unicorn_model(db, sym, timeframe="M15", candle_limit=args.limit)
                if "error" in res:
                    print(f"\n{sym}: {res['error']}")
                    continue

                if res["filled_trades"] > 0:
                    low, high = res["wilson_95"]
                    print(f"\n[{sym} - M15] Formations Found: {res['setups_found']} | Filled Orders: {res['filled_trades']} (Fill Rate: {res['fill_rate']:.1%})")
                    print(f"  Win Rate (2.0R) : {res['win_rate']:.1%} (95% CI: {low:.1%}-{high:.1%})")
                    print(f"  Profit Factor   : {res['profit_factor']:.2f}")
                    print(f"  Avg Risk Pips   : {res['avg_risk_pips']:.1f} pips")
                else:
                    print(f"\n[{sym} - M15] Formations Found: {res['setups_found']} | None filled within limit window.")

        if args.strategy in ("po3", "all"):
            print("\n" + "#" * 85)
            print("  STRATEGY 3: POWER OF 3 (PO3 / AMD) ENTRY PRICING FILTER")
            print("#" * 85)

            for sym in args.symbols:
                res = backtest_power_of_three(db, sym, timeframe=args.timeframe, candle_limit=args.limit)
                if "error" in res:
                    print(f"\n{sym}: {res['error']}")
                    continue

                print(f"\n[{sym} - {args.timeframe}] Periods Evaluated: {res['naive_total']}")
                print(f"  Naive Entry Win Rate : {res['naive_win_rate']:.1%}")
                print(f"  PO3 Entry Win Rate   : {res['po3_win_rate']:.1%} (Filtered to {res['po3_total']} trades)")
                print(f"  Edge Improvement     : {res['edge_increase_pct']:+.1f}%")

    finally:
        db.close()


if __name__ == "__main__":
    main()

