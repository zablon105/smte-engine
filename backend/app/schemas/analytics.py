"""
analytics.py
Pydantic schemas for account metrics and quantitative performance analytics.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AccountSummaryOut(BaseModel):
    login: int
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: Optional[float] = None
    floating_profit: float
    open_positions_count: int
    is_connected: bool


class PerformanceOverviewOut(BaseModel):
    total_trades: int
    win_count: int
    loss_count: int
    win_rate_pct: float
    profit_factor: float
    avg_r_multiple: float
    net_profit: float
    max_drawdown_pct: float
    equity_curve: List[Dict[str, Any]]


class StrategyPerformanceOut(BaseModel):
    strategy_name: str
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    avg_r: float
