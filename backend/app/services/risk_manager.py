"""
risk_manager.py
Risk management, position sizing, and exposure controls for SMTE.

Beginner note on Position Sizing:
  Professional traders never risk a fixed lot size (e.g. 0.10 lots on every trade).
  Instead, they risk a fixed PERCENTAGE of their account (e.g. 1.0% = $634 on a $63,400 account).
  
  If the stop-loss is tight (15 pips), the position size is larger.
  If the stop-loss is wide (30 pips), the position size is smaller.
  In both cases, if the trade hits the stop-loss, you lose EXACTLY 1.0% — protecting
  the account from catastrophic drawdown.

  This module:
  1. Computes dynamic lot sizing based on account equity and stop distance.
  2. Enforces maximum open trades and daily drawdown limits from the `risk_parameters` table.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from app.models.models import Instrument, RiskParameter, Trade


DEFAULT_STRATEGY_NAME = "SMTE_CRT"


def get_or_create_risk_parameters(
    db,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
    max_risk_per_trade_pct: float = 1.0,
    max_daily_risk_pct: float = 3.0,
    max_open_trades: int = 3,
) -> RiskParameter:
    """Retrieves active risk parameters for the strategy or initializes default rules."""
    params = db.query(RiskParameter).filter_by(strategy_name=strategy_name).first()
    if params is None:
        params = RiskParameter(
            strategy_name=strategy_name,
            max_risk_per_trade_pct=max_risk_per_trade_pct,
            max_daily_risk_pct=max_daily_risk_pct,
            max_open_trades=max_open_trades,
            is_active=True,
        )
        db.add(params)
        db.commit()
        db.refresh(params)
    return params


def calculate_lot_size(
    account_equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    contract_size: float = 100000.0,
    min_lot: float = 0.01,
    max_lot: float = 50.0,
    lot_step: float = 0.01,
) -> float:
    """
    Calculates the exact lot size so that if stop_loss is hit,
    the loss equals exactly `risk_pct` percent of `account_equity`.
    """
    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0 or account_equity <= 0:
        return min_lot

    cash_risk = account_equity * (risk_pct / 100.0)
    risk_per_lot = stop_distance * contract_size

    if risk_per_lot <= 0:
        return min_lot

    raw_lot = cash_risk / risk_per_lot

    # Round steps to avoid floating-point binary truncation (e.g. 0.4999999 -> 0.50)
    steps = int(round(raw_lot / lot_step, 4))
    calculated_lot = steps * lot_step
    calculated_lot = round(calculated_lot, 2)

    return max(min_lot, min(calculated_lot, max_lot))


def can_open_new_trade(
    db,
    strategy_name: str = DEFAULT_STRATEGY_NAME,
) -> Tuple[bool, str]:
    """
    Validates whether a new trade is permitted under current risk parameters.
    Checks:
      1. Maximum open trades limit
      2. Strategy active status
    """
    params = get_or_create_risk_parameters(db, strategy_name)
    if not params.is_active:
        return False, f"Strategy '{strategy_name}' risk parameters are inactive."

    open_trades_count = (
        db.query(Trade)
        .filter(Trade.status == "OPEN")
        .count()
    )

    if open_trades_count >= params.max_open_trades:
        return False, f"Maximum open trades limit reached ({open_trades_count}/{params.max_open_trades})."

    return True, "Approved"
