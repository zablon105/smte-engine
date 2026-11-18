"""
signals.py
FastAPI router for institutional signals, active setups, and on-demand scanning.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.base import get_db
from app.models.models import TradeSignal, Instrument, SetupScore
from app.schemas.signals import SignalOut
from core.execution.run_scalper import scan_symbol_for_scalp, DEFAULT_SCALP_SYMBOLS

router = APIRouter(prefix="/signals", tags=["Signals"])


@router.get("/active", response_model=List[SignalOut])
def get_active_signals(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Returns recent generated trade signals from the database.
    """
    signals = (
        db.query(TradeSignal)
        .order_by(TradeSignal.generated_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for s in signals:
        inst = db.query(Instrument).filter(Instrument.id == s.instrument_id).first()
        symbol = inst.symbol if inst else "UNKNOWN"
        digits = inst.digits if inst else 5

        entry = float(s.entry_price)
        sl = float(s.stop_loss)
        tp = float(s.take_profit)
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = round(reward / risk, 2) if risk > 0 else 2.0

        score = None
        if s.setup_score_id:
            sc = db.query(SetupScore).filter(SetupScore.id == s.setup_score_id).first()
            if sc:
                score = sc.total_score

        results.append(
            SignalOut(
                id=s.id,
                symbol=symbol,
                instrument_id=s.instrument_id,
                strategy="SMC / CRT Confluence",
                signal_direction=s.signal_direction,
                entry_price=round(entry, digits),
                stop_loss=round(sl, digits),
                take_profit=round(tp, digits),
                risk_reward=rr,
                total_score=score or 15,
                status=s.status,
                generated_at=s.generated_at,
                details=f"Confluence Score: {score or 15}/25 | R:R = {rr}:1",
            )
        )

    return results


@router.get("/scan-now")
def run_live_scan(
    strategy: str = Query("all", pattern="^(crt|unicorn|turtle_soup|po3|all)$"),
    timeframe: str = Query("M5", pattern="^(M1|M3|M5|M15)$"),
    db: Session = Depends(get_db),
):
    """
    Executes an on-demand real-time institutional scalp scan across all active pairs.
    Returns any detected setups meeting criteria.
    """
    setups = []
    for symbol in DEFAULT_SCALP_SYMBOLS:
        setup = scan_symbol_for_scalp(
            db=db,
            symbol=symbol,
            ltf=timeframe,
            strategy_name=strategy,
            dry_run=True,
        )
        if setup:
            setups.append(setup)

    return {
        "scanned_symbols": DEFAULT_SCALP_SYMBOLS,
        "strategy": strategy,
        "timeframe": timeframe,
        "count": len(setups),
        "setups": setups,
    }
