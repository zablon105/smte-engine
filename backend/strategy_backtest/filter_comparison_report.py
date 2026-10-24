"""
filter_comparison_report.py
Evaluates and compares the win rate, expected value (EV), and trade quality
across various custom filter combinations on the SMTE historical dataset:

1. Baseline: All confirmed trades (Score >= 10, no extra filters)
2. Score >= 12 (Moderate/High Confluence)
3. Score >= 15 (High Institutional Confluence)
4. Killzones Only (London 07:00-10:00 UTC & NY 12:00-15:00 UTC)
5. Max Risk Filter (Stop distance <= 25 pips)
6. HTF Market Structure Alignment (H1/H4 BOS in trade direction)
7. Combo A: Killzone + Max Risk <= 25 pips
8. Combo B: Score >= 12 + Killzone + Max Risk <= 25 pips
9. Ultimate Institutional Combo: Score >= 12 + Killzone + Max Risk <= 25 pips + HTF Alignment

Applies the honest one-trade-at-a-time rule to eliminate overlapping trades.

Usage (from SMTE/backend, with smte-env activated):
    python -m strategy_backtest.filter_comparison_report
"""

from datetime import datetime, timedelta, timezone
from math import sqrt
from typing import Dict, List, Any

from app.database.base import SessionLocal
from app.models.models import Candle, CrtSetup, Instrument, MarketStructure, SetupScore, TradeSignal
from strategy_backtest.signal_backtest import _find_confirmation_time, backtest_signal
from strategy_backtest.split_report import wilson_interval, one_trade_at_a_time, FAR_FUTURE, LONG_AGO


def _true_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10
    return point


def load_all_trade_records(db, timeframe: str = "M15") -> List[Dict[str, Any]]:
    """
    Loads all signals, joins their setup, score, and instrument metadata,
    and runs backtest simulation with pre-computed filter flags.
    """
    print("[1/3] Loading instruments and historical market structure...")
    instruments = {inst.id: inst for inst in db.query(Instrument).all()}

    # Pre-cache HTF MarketStructure events (H1, H4) for fast lookups
    htf_structures = (
        db.query(MarketStructure)
        .filter(MarketStructure.timeframe.in_(("H1", "H4")))
        .order_by(MarketStructure.occurred_at.asc())
        .all()
    )

    from collections import defaultdict
    htf_by_inst_dir = defaultdict(list)
    for ms in htf_structures:
        htf_by_inst_dir[(ms.instrument_id, ms.direction)].append(ms.occurred_at)

    print("[2/3] Fetching all signals and running backtest outcomes...")
    query = (
        db.query(TradeSignal, SetupScore, CrtSetup)
        .join(SetupScore, SetupScore.id == TradeSignal.setup_score_id)
        .join(CrtSetup, CrtSetup.id == TradeSignal.crt_setup_id)
    )
    rows = query.all()
    print(f"      Total raw signals in database: {len(rows)}")

    trades = []
    for signal, score, setup in rows:
        inst = instruments.get(signal.instrument_id)
        if not inst:
            continue

        entry_time = _find_confirmation_time(db, setup, timeframe)
        if entry_time is None:
            continue

        outcome = backtest_signal(db, signal, setup, timeframe)
        if outcome["result"] not in ("TP_HIT", "SL_HIT"):
            continue

        true_pip = _true_pip_size(inst.digits, float(inst.pip_size))
        entry_price = float(signal.entry_price)
        stop_loss = float(signal.stop_loss)
        risk_distance = abs(entry_price - stop_loss)
        risk_pips = risk_distance / true_pip if true_pip > 0 else 0.0

        # Filter 1: Killzone check (London 07-10 UTC, NY 12-15 UTC)
        h = entry_time.hour if hasattr(entry_time, "hour") else 0
        in_killzone = (7 <= h < 10) or (12 <= h < 15)

        # Filter 2: HTF structure alignment (recent H1/H4 BOS in setup direction within 48h)
        ms_dir = "BULLISH" if signal.signal_direction in ("BUY", "BULLISH") else "BEARISH"
        dir_events = htf_by_inst_dir.get((signal.instrument_id, ms_dir), [])
        window_start = entry_time - timedelta(hours=48)
        has_htf_align = any(window_start <= ev_time <= entry_time for ev_time in dir_events)

        trades.append({
            "instrument_id": signal.instrument_id,
            "direction": signal.signal_direction,
            "entry_time": entry_time,
            "hit_at": outcome["hit_at"],
            "result": outcome["result"],
            "score": score.total_score,
            "risk_pips": risk_pips,
            "in_killzone": in_killzone,
            "has_htf_align": has_htf_align,
        })

    print(f"      Evaluated confirmed trades: {len(trades)}")
    return trades


def evaluate_filter_set(name: str, trades: List[Dict[str, Any]], rr: float = 2.0):
    # Apply one-trade-at-a-time rule
    kept, skipped = one_trade_at_a_time(trades)
    n = len(kept)
    if n == 0:
        return {
            "name": name,
            "trades": 0,
            "wins": 0,
            "win_rate": 0.0,
            "ev": 0.0,
            "range_str": "N/A",
            "net_r": 0.0,
            "profit_factor": 0.0,
        }

    wins = sum(1 for t in kept if t["result"] == "TP_HIT")
    losses = n - wins
    p = wins / n
    ev = p * rr - (1 - p)
    low, high = wilson_interval(wins, n)
    range_str = f"{low * 100:.1f}% - {high * 100:.1f}%"
    net_r = (wins * rr) - losses
    profit_factor = (wins * rr) / losses if losses > 0 else 99.0

    return {
        "name": name,
        "trades": n,
        "wins": wins,
        "win_rate": p * 100.0,
        "ev": ev,
        "range_str": range_str,
        "net_r": net_r,
        "profit_factor": profit_factor,
    }


def main():
    db = SessionLocal()
    try:
        all_trades = load_all_trade_records(db)
        print("\n[3/3] Computing filter comparisons with one-trade-at-a-time rule...")

        filters = [
            ("1. Baseline (Score >= 10)", [t for t in all_trades if t["score"] >= 10]),
            ("2. Score >= 12", [t for t in all_trades if t["score"] >= 12]),
            ("3. Score >= 15", [t for t in all_trades if t["score"] >= 15]),
            ("4. Killzones Only (LDN/NY)", [t for t in all_trades if t["score"] >= 10 and t["in_killzone"]]),
            ("5. Max Risk <= 25 pips", [t for t in all_trades if t["score"] >= 10 and t["risk_pips"] <= 25.0]),
            ("6. HTF BOS Alignment", [t for t in all_trades if t["score"] >= 10 and t["has_htf_align"]]),
            ("7. Combo: Killzone + Risk<=25p", [t for t in all_trades if t["score"] >= 10 and t["in_killzone"] and t["risk_pips"] <= 25.0]),
            ("8. Combo: Score>=12 + KZ + Risk<=25p", [t for t in all_trades if t["score"] >= 12 and t["in_killzone"] and t["risk_pips"] <= 25.0]),
            ("9. Institutional: Score>=12 + KZ + Risk<=25p + HTF", [t for t in all_trades if t["score"] >= 12 and t["in_killzone"] and t["risk_pips"] <= 25.0 and t["has_htf_align"]]),
        ]

        print("\n" + "=" * 95)
        print(f"{'FILTER CONFIGURATION':<40}{'TRADES':>7}{'WINS':>6}{'WIN RATE':>10}{'95% CONF INTERVAL':>20}{'EV (R)':>9}{'PROFIT FACTOR':>15}")
        print("=" * 95)

        for name, subset in filters:
            res = evaluate_filter_set(name, subset)
            print(
                f"{res['name']:<40}"
                f"{res['trades']:>7}"
                f"{res['wins']:>6}"
                f"{res['win_rate']:>9.1f}%"
                f"{res['range_str']:>20}"
                f"{res['ev']:>+9.2f}"
                f"{res['profit_factor']:>14.2f}"
            )

        print("=" * 95)
        print("Note: Break-even win rate at 2.0R is 33.3%. Any win rate above 33.3% produces positive EV.")
        print("Profit Factor > 1.0 indicates a profitable strategy; > 1.20 indicates robust edge.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
