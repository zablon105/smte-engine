"""
trades.py
Pydantic schemas for trade-related API requests and responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TradeBase(BaseModel):
    instrument_id: int
    symbol: Optional[str] = None
    mt5_ticket: Optional[int] = None
    direction: str
    lot_size: float
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    profit: Optional[float] = None
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None


class TradeOut(TradeBase):
    id: int
    current_price: Optional[float] = None
    floating_profit: Optional[float] = None
    r_multiple: Optional[float] = None
    is_breakeven: bool = False
    strategy: Optional[str] = "SMTE"

    model_config = ConfigDict(from_attributes=True)


class TradeActionRequest(BaseModel):
    ticket: int


class TradeActionResponse(BaseModel):
    success: bool
    message: str
    ticket: Optional[int] = None
