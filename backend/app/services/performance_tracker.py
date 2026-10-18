"""
performance_tracker.py
Computes, tracks, and persists quantitative performance metrics for SMTE
into the `performance_metrics` table.

Beginner note on Trading Performance Metrics:
  1. Win Rate %:
     Percentage of closed trades that hit take-profit.
  2. Average R-Multiple (Expectancy):
     Average return per trade measured in risk units (R). For example, at 2.0R target,
     each win is +2R and each loss is -1R. A positive EV means the strategy grows capital over time.
  3. Max Drawdown %:
     The largest peak-to-trough drop in the equity/R curve, representing the historical
     maximum pain or risk of the strategy.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from app.models.models import PerformanceMetric, Trade


DEFAULT_STRATEGY_NAME = "SMTE_CRT"


def calculate_metrics_from_outcomes(
    outcomes: List[Dict[str, Any]],
    risk_reward: float = 2.0,
) -> Dict[str, Any]:
    """
    Computes win rate, average R multiple, net R, and maximum drawdown
    from a list of trade outcomes (dicts containing 'result' == 'TP_HIT' | 'SL_HIT' or profit).
    """
    decided = [t for t in outcomes if t.get("result") in ("TP_HIT", "SL_HIT") or t.get("profit") is not None]
    total = len(decided)
    if total == 0:
        return {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
            "avg_r_multiple": 0.0,
            "max_drawdown_pct": 0.0,
            "net_r": 0.0,
        }

    wins = sum(
        1 for t in decided
        if t.get("result") == "TP_HIT" or (t.get("profit") is not None and float(t["profit"]) > 0)
    )
    losses = total - wins
    win_rate = (wins / total) * 100.0

    # Calculate equity curve in R units: wins = +risk_reward, losses = -1.0
    r_curve = []
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0

    for t in decided:
        is_win = t.get("result") == "TP_HIT" or (t.get("profit") is not None and float(t["profit"]) > 0)
        r_change = risk_reward if is_win else -1.0
        cumulative += r_change
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    avg_r = cumulative / total

    return {
        "total_trades": total,
        "win_count": wins,
        "loss_count": losses,
        "win_rate_pct": round(win_rate, 2),
        "avg_r_multiple": round(avg_r, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "net_r": round(cumulative, 2),
    }


def record_performance_metric(
    db,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    outcomes: Optional[List[Dict[str, Any]]] = None,
    risk_reward: float = 2.0,
) -> PerformanceMetric:
    """
    Computes performance metrics and saves a new record in `performance_metrics`.
    If `outcomes` is not provided, pulls closed trades from the `trades` table.
    """
    if period_start is None:
        period_start = datetime(2020, 1, 1)
    if period_end is None:
        period_end = datetime.now()

    if outcomes is None:
        # Pull closed trades from the database
        db_trades = (
            db.query(Trade)
            .filter(
                Trade.status == "CLOSED",
                Trade.opened_at >= period_start,
                Trade.opened_at <= period_end,
            )
            .all()
        )
        outcomes = [
            {"result": "TP_HIT" if (t.profit or 0) > 0 else "SL_HIT", "profit": float(t.profit or 0)}
            for t in db_trades
        ]

    metrics = calculate_metrics_from_outcomes(outcomes, risk_reward=risk_reward)

    record = PerformanceMetric(
        strategy_name=strategy_name,
        period_start=period_start.replace(tzinfo=None) if hasattr(period_start, "replace") else period_start,
        period_end=period_end.replace(tzinfo=None) if hasattr(period_end, "replace") else period_end,
        total_trades=metrics["total_trades"],
        win_count=metrics["win_count"],
        loss_count=metrics["loss_count"],
        win_rate_pct=metrics["win_rate_pct"],
        avg_r_multiple=metrics["avg_r_multiple"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        net_profit=metrics["net_r"],
        calculated_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

