"""
app/schemas/__init__.py
Re-exports all Pydantic schemas for SMTE REST API.
"""

from app.schemas.trades import TradeOut, TradeActionRequest, TradeActionResponse
from app.schemas.signals import SignalOut
from app.schemas.market import InstrumentOut, CandleOut, SessionOut
from app.schemas.analytics import AccountSummaryOut, PerformanceOverviewOut, StrategyPerformanceOut

__all__ = [
    "TradeOut",
    "TradeActionRequest",
    "TradeActionResponse",
    "SignalOut",
    "InstrumentOut",
    "CandleOut",
    "SessionOut",
    "AccountSummaryOut",
    "PerformanceOverviewOut",
    "StrategyPerformanceOut",
]
