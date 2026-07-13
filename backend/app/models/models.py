"""
models.py
SQLAlchemy ORM models for the SMTE database.

Beginner note: each class below represents one database table.
Class attributes become table columns. `relationship()` fields let
you navigate between related tables in Python (e.g. trade.instrument
instead of writing a manual SQL join every time).

This file mirrors backend/app/database/schema.sql exactly — if you
change one, change the other to keep them in sync.
"""

from sqlalchemy import (
    Column, Integer, BigInteger, SmallInteger, String, Numeric,
    Boolean, TIMESTAMP, ForeignKey, Text, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from app.database.base import Base


# ------------------------------------------------------------
# 1. Instrument
# ------------------------------------------------------------
class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(20), nullable=False, unique=True)
    description = Column(String(100))
    digits = Column(SmallInteger, nullable=False)
    pip_size = Column(Numeric(12, 8), nullable=False)
    contract_size = Column(Numeric(15, 2), nullable=False, default=100000)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    candles = relationship("Candle", back_populates="instrument")


# ------------------------------------------------------------
# 2. Candle
# ------------------------------------------------------------
class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "open_time"),
    )

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    open_time = Column(TIMESTAMP(timezone=True), nullable=False)
    open = Column(Numeric(15, 8), nullable=False)
    high = Column(Numeric(15, 8), nullable=False)
    low = Column(Numeric(15, 8), nullable=False)
    close = Column(Numeric(15, 8), nullable=False)
    volume = Column(BigInteger, nullable=False, default=0)
    spread = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    instrument = relationship("Instrument", back_populates="candles")


# ------------------------------------------------------------
# 3. Session (trading session, not a web session)
# ------------------------------------------------------------
class TradingSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("instrument_id", "session_date", "session_name"),
    )

    id = Column(Integer, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    session_date = Column("session_date", TIMESTAMP(timezone=False), nullable=False)
    session_name = Column(String(20), nullable=False)
    start_time = Column(TIMESTAMP(timezone=True), nullable=False)
    end_time = Column(TIMESTAMP(timezone=True), nullable=False)
    session_high = Column(Numeric(15, 8))
    session_low = Column(Numeric(15, 8))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 4. LiquidityZone
# ------------------------------------------------------------
class LiquidityZone(Base):
    __tablename__ = "liquidity_zones"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    zone_type = Column(String(20), nullable=False)  # BUY_SIDE / SELL_SIDE
    price_level = Column(Numeric(15, 8), nullable=False)
    formed_at = Column(TIMESTAMP(timezone=True), nullable=False)
    swept_at = Column(TIMESTAMP(timezone=True))
    is_swept = Column(Boolean, nullable=False, default=False)
    strength_score = Column(SmallInteger)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 5. OrderBlock
# ------------------------------------------------------------
class OrderBlock(Base):
    __tablename__ = "order_blocks"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    block_type = Column(String(10), nullable=False)  # BULLISH / BEARISH
    high_price = Column(Numeric(15, 8), nullable=False)
    low_price = Column(Numeric(15, 8), nullable=False)
    formed_at = Column(TIMESTAMP(timezone=True), nullable=False)
    mitigated_at = Column(TIMESTAMP(timezone=True))
    is_mitigated = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 6. FairValueGap
# ------------------------------------------------------------
class FairValueGap(Base):
    __tablename__ = "fair_value_gaps"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    gap_type = Column(String(10), nullable=False)  # BULLISH / BEARISH
    top_price = Column(Numeric(15, 8), nullable=False)
    bottom_price = Column(Numeric(15, 8), nullable=False)
    formed_at = Column(TIMESTAMP(timezone=True), nullable=False)
    filled_at = Column(TIMESTAMP(timezone=True))
    fill_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 7. MarketStructure
# ------------------------------------------------------------
class MarketStructure(Base):
    __tablename__ = "market_structure"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    event_type = Column(String(10), nullable=False)  # BOS / CHOCH
    direction = Column(String(10), nullable=False)   # BULLISH / BEARISH
    swing_price = Column(Numeric(15, 8), nullable=False)
    break_price = Column(Numeric(15, 8), nullable=False)
    occurred_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 8. DolTarget (Draw on Liquidity)
# ------------------------------------------------------------
class DolTarget(Base):
    __tablename__ = "dol_targets"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    target_price = Column(Numeric(15, 8), nullable=False)
    liquidity_zone_id = Column(BigInteger, ForeignKey("liquidity_zones.id", ondelete="SET NULL"))
    identified_at = Column(TIMESTAMP(timezone=True), nullable=False)
    reached_at = Column(TIMESTAMP(timezone=True))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 9. CrtSetup
# ------------------------------------------------------------
class CrtSetup(Base):
    __tablename__ = "crt_setups"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    range_candle_id = Column(BigInteger, ForeignKey("candles.id", ondelete="SET NULL"))
    setup_direction = Column(String(10), nullable=False)  # BULLISH / BEARISH
    phase = Column(String(20), nullable=False)  # RANGE / MANIPULATION / DISTRIBUTION
    range_high = Column(Numeric(15, 8), nullable=False)
    range_low = Column(Numeric(15, 8), nullable=False)
    manipulation_price = Column(Numeric(15, 8))
    detected_at = Column(TIMESTAMP(timezone=True), nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    scores = relationship("SetupScore", back_populates="crt_setup")


# ------------------------------------------------------------
# 10. SmtDivergence
# ------------------------------------------------------------
class SmtDivergence(Base):
    __tablename__ = "smt_divergence"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    correlated_instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    timeframe = Column(String(5), nullable=False)
    divergence_type = Column(String(20), nullable=False)  # BULLISH / BEARISH
    detected_at = Column(TIMESTAMP(timezone=True), nullable=False)
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 11. SetupScore
# ------------------------------------------------------------
class SetupScore(Base):
    __tablename__ = "setup_scores"

    id = Column(BigInteger, primary_key=True)
    crt_setup_id = Column(BigInteger, ForeignKey("crt_setups.id", ondelete="CASCADE"), nullable=False)
    liquidity_score = Column(SmallInteger, nullable=False, default=0)
    order_block_score = Column(SmallInteger, nullable=False, default=0)
    fvg_score = Column(SmallInteger, nullable=False, default=0)
    structure_score = Column(SmallInteger, nullable=False, default=0)
    smt_score = Column(SmallInteger, nullable=False, default=0)
    session_score = Column(SmallInteger, nullable=False, default=0)
    total_score = Column(SmallInteger, nullable=False, default=0)
    scored_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    crt_setup = relationship("CrtSetup", back_populates="scores")


# ------------------------------------------------------------
# 12. TradeSignal
# ------------------------------------------------------------
class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id = Column(BigInteger, primary_key=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    crt_setup_id = Column(BigInteger, ForeignKey("crt_setups.id", ondelete="SET NULL"))
    setup_score_id = Column(BigInteger, ForeignKey("setup_scores.id", ondelete="SET NULL"))
    signal_direction = Column(String(10), nullable=False)  # BUY / SELL
    entry_price = Column(Numeric(15, 8), nullable=False)
    stop_loss = Column(Numeric(15, 8), nullable=False)
    take_profit = Column(Numeric(15, 8), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    generated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    trades = relationship("Trade", back_populates="trade_signal")


# ------------------------------------------------------------
# 13. Trade
# ------------------------------------------------------------
class Trade(Base):
    __tablename__ = "trades"

    id = Column(BigInteger, primary_key=True)
    trade_signal_id = Column(BigInteger, ForeignKey("trade_signals.id", ondelete="SET NULL"))
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    # NOTE: MT5 ticket numbers can exceed the range of a 32-bit integer,
    # which caused an overflow bug in an earlier project. BigInteger avoids that.
    mt5_ticket = Column(BigInteger, unique=True)
    direction = Column(String(10), nullable=False)  # BUY / SELL
    lot_size = Column(Numeric(10, 2), nullable=False)
    entry_price = Column(Numeric(15, 8), nullable=False)
    exit_price = Column(Numeric(15, 8))
    stop_loss = Column(Numeric(15, 8))
    take_profit = Column(Numeric(15, 8))
    profit = Column(Numeric(15, 2))
    opened_at = Column(TIMESTAMP(timezone=True), nullable=False)
    closed_at = Column(TIMESTAMP(timezone=True))
    status = Column(String(20), nullable=False, default="OPEN")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    trade_signal = relationship("TradeSignal", back_populates="trades")


# ------------------------------------------------------------
# 14. RiskParameter
# ------------------------------------------------------------
class RiskParameter(Base):
    __tablename__ = "risk_parameters"

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50), nullable=False, unique=True)
    max_risk_per_trade_pct = Column(Numeric(5, 2), nullable=False, default=1.00)
    max_daily_risk_pct = Column(Numeric(5, 2), nullable=False, default=3.00)
    max_open_trades = Column(SmallInteger, nullable=False, default=3)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ------------------------------------------------------------
# 15. PerformanceMetric
# ------------------------------------------------------------
class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id = Column(BigInteger, primary_key=True)
    strategy_name = Column(String(50), nullable=False)
    period_start = Column("period_start", TIMESTAMP(timezone=False), nullable=False)
    period_end = Column("period_end", TIMESTAMP(timezone=False), nullable=False)
    total_trades = Column(Integer, nullable=False, default=0)
    win_count = Column(Integer, nullable=False, default=0)
    loss_count = Column(Integer, nullable=False, default=0)
    win_rate_pct = Column(Numeric(5, 2))
    avg_r_multiple = Column(Numeric(6, 2))
    max_drawdown_pct = Column(Numeric(5, 2))
    net_profit = Column(Numeric(15, 2))
    calculated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
