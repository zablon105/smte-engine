"""
trades.py
FastAPI router for trade management, active positions, and trade history.
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models.models import Trade, Instrument
from app.schemas.trades import TradeOut, TradeActionRequest, TradeActionResponse
from app.services import mt5_client

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("/open", response_model=List[TradeOut])
def get_open_trades(db: Session = Depends(get_db)):
    """
    Returns all currently open trades.
    If MT5 is connected, enriches trades with live tick prices, floating P&L, and breakeven status.
    """
    trades = db.query(Trade).filter(Trade.status == "OPEN").order_by(Trade.opened_at.desc()).all()
    results = []

    mt5_positions_map = {}
    try:
        if mt5_client.connect():
            positions = mt5_client.get_positions()
            if positions:
                for p in positions:
                    mt5_positions_map[p.ticket] = p
    except Exception:
        # MT5 may be busy or offline; fallback cleanly to DB records
        pass

    for t in trades:
        inst = db.query(Instrument).filter(Instrument.id == t.instrument_id).first()
        symbol = inst.symbol if inst else "UNKNOWN"
        digits = inst.digits if inst else 5

        current_price = float(t.entry_price)
        floating_profit = 0.0
        is_breakeven = False
        r_mult = 0.0

        pos = mt5_positions_map.get(t.mt5_ticket)
        if pos:
            current_price = float(pos.price_current)
            floating_profit = float(pos.profit)
            entry = float(t.entry_price)
            sl = float(t.stop_loss or entry)
            risk = abs(entry - sl)
            if t.direction == "BUY":
                is_breakeven = sl >= entry
                favorable = current_price - entry
            else:
                is_breakeven = sl <= entry
                favorable = entry - current_price

            if risk > 0:
                r_mult = round(favorable / risk, 2)
        else:
            entry = float(t.entry_price)
            sl = float(t.stop_loss or entry)
            is_breakeven = (sl >= entry) if t.direction == "BUY" else (sl <= entry)

        results.append(
            TradeOut(
                id=t.id,
                instrument_id=t.instrument_id,
                symbol=symbol,
                mt5_ticket=t.mt5_ticket,
                direction=t.direction,
                lot_size=float(t.lot_size),
                entry_price=round(float(t.entry_price), digits),
                exit_price=float(t.exit_price) if t.exit_price else None,
                stop_loss=round(float(t.stop_loss), digits) if t.stop_loss else None,
                take_profit=round(float(t.take_profit), digits) if t.take_profit else None,
                profit=float(t.profit) if t.profit is not None else None,
                current_price=round(current_price, digits),
                floating_profit=round(floating_profit, 2),
                r_multiple=r_mult,
                is_breakeven=is_breakeven,
                status=t.status,
                opened_at=t.opened_at,
                closed_at=t.closed_at,
                strategy="SMTE Institutional",
            )
        )

    return results


@router.get("/history", response_model=List[TradeOut])
def get_trade_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Returns closed trade history ordered by closed_at descending.
    """
    query = db.query(Trade).filter(Trade.status == "CLOSED")

    if symbol:
        inst = db.query(Instrument).filter(Instrument.symbol == symbol).first()
        if inst:
            query = query.filter(Trade.instrument_id == inst.id)

    trades = query.order_by(Trade.closed_at.desc().nullslast(), Trade.id.desc()).offset(offset).limit(limit).all()
    results = []

    for t in trades:
        inst = db.query(Instrument).filter(Instrument.id == t.instrument_id).first()
        symbol_name = inst.symbol if inst else "UNKNOWN"
        digits = inst.digits if inst else 5

        results.append(
            TradeOut(
                id=t.id,
                instrument_id=t.instrument_id,
                symbol=symbol_name,
                mt5_ticket=t.mt5_ticket,
                direction=t.direction,
                lot_size=float(t.lot_size),
                entry_price=round(float(t.entry_price), digits),
                exit_price=round(float(t.exit_price), digits) if t.exit_price else None,
                stop_loss=round(float(t.stop_loss), digits) if t.stop_loss else None,
                take_profit=round(float(t.take_profit), digits) if t.take_profit else None,
                profit=round(float(t.profit), 2) if t.profit is not None else None,
                current_price=round(float(t.exit_price or t.entry_price), digits),
                floating_profit=0.0,
                r_multiple=2.0 if (t.profit or 0) > 0 else -1.0,
                is_breakeven=False,
                status=t.status,
                opened_at=t.opened_at,
                closed_at=t.closed_at,
                strategy="SMTE Institutional",
            )
        )

    return results


@router.post("/breakeven", response_model=TradeActionResponse)
def move_to_breakeven(req: TradeActionRequest, db: Session = Depends(get_db)):
    """
    Manually triggers moving an active trade's stop loss to entry price (Breakeven).
    """
    trade = db.query(Trade).filter(Trade.mt5_ticket == req.ticket, Trade.status == "OPEN").first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Active trade with ticket #{req.ticket} not found in DB")

    try:
        mt5_client.connect()
        entry = float(trade.entry_price)
        tp = float(trade.take_profit) if trade.take_profit else 0.0
        success = mt5_client.modify_position(trade.mt5_ticket, sl=entry, tp=tp)
        if success:
            trade.stop_loss = entry
            db.commit()
            return TradeActionResponse(success=True, message=f"Moved Ticket #{req.ticket} to Breakeven @ {entry}", ticket=req.ticket)
        else:
            raise HTTPException(status_code=500, detail="MT5 rejected modify_position request")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move to breakeven: {str(e)}")


@router.post("/close", response_model=TradeActionResponse)
def close_trade_manually(req: TradeActionRequest, db: Session = Depends(get_db)):
    """
    Manually closes an active position in MT5 immediately at market price.
    """
    trade = db.query(Trade).filter(Trade.mt5_ticket == req.ticket, Trade.status == "OPEN").first()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Active trade with ticket #{req.ticket} not found")

    try:
        mt5_client.connect()
        success = mt5_client.close_position(req.ticket)
        if success:
            trade.status = "CLOSED"
            trade.closed_at = datetime.now(timezone.utc)
            db.commit()
            return TradeActionResponse(success=True, message=f"Successfully closed Ticket #{req.ticket}", ticket=req.ticket)
        else:
            raise HTTPException(status_code=500, detail="MT5 rejected close_position request")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to close trade: {str(e)}")
