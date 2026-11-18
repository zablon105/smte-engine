"""
market.py
Pydantic schemas for instruments, candles, and market session responses.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class InstrumentOut(BaseModel):
    id: int
    symbol: str
    description: Optional[str] = None
    digits: int
    pip_size: float
    contract_size: float
    is_active: bool
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread_pips: Optional[float] = None
    is_market_open: bool = True

    model_config = ConfigDict(from_attributes=True)


class CandleOut(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int


class SessionOut(BaseModel):
    current_utc_time: str
    active_session: str
    is_killzone: bool
    current_killzone: Optional[str] = None
    upcoming_killzone: Optional[str] = None
    minutes_to_next_killzone: Optional[int] = None
