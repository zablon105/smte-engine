"""
signals.py
Pydantic schemas for signal-related API responses.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class SignalOut(BaseModel):
    id: int
    symbol: str
    instrument_id: int
    strategy: str
    signal_direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    total_score: Optional[int] = None
    status: str
    generated_at: datetime
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
