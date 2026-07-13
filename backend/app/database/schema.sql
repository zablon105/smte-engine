-- ============================================================
-- SMTE (Smart Money Trading Engine) Database Schema
-- PostgreSQL 16
-- 15 tables covering: market data, SMC concepts, CRT setups,
-- scoring, execution, and analytics.
-- ============================================================

-- ------------------------------------------------------------
-- 1. instruments
-- Tradeable symbols and their metadata (pip size, digits, etc.)
-- ------------------------------------------------------------
CREATE TABLE instruments (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL UNIQUE,       -- e.g. 'EURUSD.m'
    description     VARCHAR(100),
    digits          SMALLINT NOT NULL,                 -- price decimal places
    pip_size        NUMERIC(12, 8) NOT NULL,           -- e.g. 0.0001
    contract_size   NUMERIC(15, 2) NOT NULL DEFAULT 100000,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 2. candles
-- OHLCV data. Single table for all timeframes, distinguished
-- by the `timeframe` column (e.g. 'M1', 'M15', 'H1', 'H4', 'D1').
-- ------------------------------------------------------------
CREATE TABLE candles (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe       VARCHAR(5) NOT NULL,
    open_time       TIMESTAMPTZ NOT NULL,
    open            NUMERIC(15, 8) NOT NULL,
    high            NUMERIC(15, 8) NOT NULL,
    low             NUMERIC(15, 8) NOT NULL,
    close           NUMERIC(15, 8) NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    spread          INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (instrument_id, timeframe, open_time)
);
CREATE INDEX idx_candles_lookup ON candles (instrument_id, timeframe, open_time DESC);

-- ------------------------------------------------------------
-- 3. sessions
-- Trading session boundaries per day (Asian/London/NY) used
-- for CRT range detection and session-based analysis.
-- ------------------------------------------------------------
CREATE TABLE sessions (
    id              SERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    session_date    DATE NOT NULL,
    session_name    VARCHAR(20) NOT NULL,               -- 'ASIA', 'LONDON', 'NEWYORK'
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    session_high    NUMERIC(15, 8),
    session_low     NUMERIC(15, 8),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (instrument_id, session_date, session_name)
);

-- ------------------------------------------------------------
-- 4. liquidity_zones
-- Buy-side/sell-side liquidity pools (equal highs/lows,
-- trendline liquidity, session highs/lows).
-- ------------------------------------------------------------
CREATE TABLE liquidity_zones (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe       VARCHAR(5) NOT NULL,
    zone_type       VARCHAR(20) NOT NULL,               -- 'BUY_SIDE', 'SELL_SIDE'
    price_level     NUMERIC(15, 8) NOT NULL,
    formed_at       TIMESTAMPTZ NOT NULL,
    swept_at        TIMESTAMPTZ,                        -- null until liquidity taken
    is_swept        BOOLEAN NOT NULL DEFAULT FALSE,
    strength_score  SMALLINT,                            -- 1-10 confluence rating
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_liquidity_lookup ON liquidity_zones (instrument_id, timeframe, is_swept);

-- ------------------------------------------------------------
-- 5. order_blocks
-- Bullish/bearish order block detections.
-- ------------------------------------------------------------
CREATE TABLE order_blocks (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe       VARCHAR(5) NOT NULL,
    block_type      VARCHAR(10) NOT NULL,               -- 'BULLISH', 'BEARISH'
    high_price      NUMERIC(15, 8) NOT NULL,
    low_price       NUMERIC(15, 8) NOT NULL,
    formed_at       TIMESTAMPTZ NOT NULL,
    mitigated_at    TIMESTAMPTZ,
    is_mitigated    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_orderblocks_lookup ON order_blocks (instrument_id, timeframe, is_mitigated);

-- ------------------------------------------------------------
-- 6. fair_value_gaps
-- FVG / imbalance zones and their fill status.
-- ------------------------------------------------------------
CREATE TABLE fair_value_gaps (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe       VARCHAR(5) NOT NULL,
    gap_type        VARCHAR(10) NOT NULL,               -- 'BULLISH', 'BEARISH'
    top_price       NUMERIC(15, 8) NOT NULL,
    bottom_price    NUMERIC(15, 8) NOT NULL,
    formed_at       TIMESTAMPTZ NOT NULL,
    filled_at       TIMESTAMPTZ,
    fill_percentage NUMERIC(5, 2) NOT NULL DEFAULT 0,   -- 0-100
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fvg_lookup ON fair_value_gaps (instrument_id, timeframe, filled_at);

-- ------------------------------------------------------------
-- 7. market_structure
-- BOS/CHoCH events with swing point references.
-- ------------------------------------------------------------
CREATE TABLE market_structure (
    id              BIGSERIAL PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe       VARCHAR(5) NOT NULL,
    event_type      VARCHAR(10) NOT NULL,               -- 'BOS', 'CHOCH'
    direction       VARCHAR(10) NOT NULL,               -- 'BULLISH', 'BEARISH'
    swing_price     NUMERIC(15, 8) NOT NULL,
    break_price     NUMERIC(15, 8) NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_structure_lookup ON market_structure (instrument_id, timeframe, occurred_at DESC);

-- ------------------------------------------------------------
-- 8. dol_targets
-- Draw on Liquidity — where price is likely being drawn to.
-- ------------------------------------------------------------
CREATE TABLE dol_targets (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe           VARCHAR(5) NOT NULL,
    target_price        NUMERIC(15, 8) NOT NULL,
    liquidity_zone_id   BIGINT REFERENCES liquidity_zones(id) ON DELETE SET NULL,
    identified_at       TIMESTAMPTZ NOT NULL,
    reached_at          TIMESTAMPTZ,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dol_lookup ON dol_targets (instrument_id, timeframe, is_active);

-- ------------------------------------------------------------
-- 9. crt_setups
-- Detected CRT patterns: range candle, manipulation,
-- distribution phase tracking.
-- ------------------------------------------------------------
CREATE TABLE crt_setups (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe           VARCHAR(5) NOT NULL,
    range_candle_id     BIGINT REFERENCES candles(id) ON DELETE SET NULL,
    setup_direction     VARCHAR(10) NOT NULL,           -- 'BULLISH', 'BEARISH'
    phase               VARCHAR(20) NOT NULL,           -- 'RANGE', 'MANIPULATION', 'DISTRIBUTION'
    range_high          NUMERIC(15, 8) NOT NULL,
    range_low           NUMERIC(15, 8) NOT NULL,
    manipulation_price  NUMERIC(15, 8),
    detected_at         TIMESTAMPTZ NOT NULL,
    is_valid            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_crt_lookup ON crt_setups (instrument_id, timeframe, is_valid);

-- ------------------------------------------------------------
-- 10. smt_divergence
-- Smart Money divergence between correlated pairs.
-- ------------------------------------------------------------
CREATE TABLE smt_divergence (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    correlated_instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    timeframe           VARCHAR(5) NOT NULL,
    divergence_type     VARCHAR(20) NOT NULL,           -- 'BULLISH', 'BEARISH'
    detected_at          TIMESTAMPTZ NOT NULL,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_smt_lookup ON smt_divergence (instrument_id, timeframe, detected_at DESC);

-- ------------------------------------------------------------
-- 11. setup_scores
-- Confluence scoring for each detected CRT setup.
-- ------------------------------------------------------------
CREATE TABLE setup_scores (
    id                  BIGSERIAL PRIMARY KEY,
    crt_setup_id        BIGINT NOT NULL REFERENCES crt_setups(id) ON DELETE CASCADE,
    liquidity_score     SMALLINT NOT NULL DEFAULT 0,
    order_block_score   SMALLINT NOT NULL DEFAULT 0,
    fvg_score           SMALLINT NOT NULL DEFAULT 0,
    structure_score     SMALLINT NOT NULL DEFAULT 0,
    smt_score           SMALLINT NOT NULL DEFAULT 0,
    session_score       SMALLINT NOT NULL DEFAULT 0,
    total_score         SMALLINT NOT NULL DEFAULT 0,
    scored_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_scores_setup ON setup_scores (crt_setup_id);

-- ------------------------------------------------------------
-- 12. trade_signals
-- Final generated signals ready for execution.
-- ------------------------------------------------------------
CREATE TABLE trade_signals (
    id                  BIGSERIAL PRIMARY KEY,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    crt_setup_id        BIGINT REFERENCES crt_setups(id) ON DELETE SET NULL,
    setup_score_id      BIGINT REFERENCES setup_scores(id) ON DELETE SET NULL,
    signal_direction    VARCHAR(10) NOT NULL,           -- 'BUY', 'SELL'
    entry_price         NUMERIC(15, 8) NOT NULL,
    stop_loss           NUMERIC(15, 8) NOT NULL,
    take_profit         NUMERIC(15, 8) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING','EXECUTED','CANCELLED','EXPIRED'
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_signals_status ON trade_signals (instrument_id, status);

-- ------------------------------------------------------------
-- 13. trades
-- Actual executed trades, linked back to MT5 tickets.
-- ------------------------------------------------------------
CREATE TABLE trades (
    id                  BIGSERIAL PRIMARY KEY,
    trade_signal_id     BIGINT REFERENCES trade_signals(id) ON DELETE SET NULL,
    instrument_id       INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    mt5_ticket          BIGINT UNIQUE,                  -- MT5 uses large ticket numbers; BIGINT avoids overflow
    direction           VARCHAR(10) NOT NULL,           -- 'BUY', 'SELL'
    lot_size            NUMERIC(10, 2) NOT NULL,
    entry_price         NUMERIC(15, 8) NOT NULL,
    exit_price          NUMERIC(15, 8),
    stop_loss           NUMERIC(15, 8),
    take_profit          NUMERIC(15, 8),
    profit              NUMERIC(15, 2),
    opened_at           TIMESTAMPTZ NOT NULL,
    closed_at           TIMESTAMPTZ,
    status              VARCHAR(20) NOT NULL DEFAULT 'OPEN', -- 'OPEN','CLOSED','CANCELLED'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_trades_status ON trades (instrument_id, status);

-- ------------------------------------------------------------
-- 14. risk_parameters
-- Position sizing and risk rules per strategy version.
-- ------------------------------------------------------------
CREATE TABLE risk_parameters (
    id                      SERIAL PRIMARY KEY,
    strategy_name           VARCHAR(50) NOT NULL,       -- e.g. 'SMTE_v1', 'Setup_A_EMA_ADX'
    max_risk_per_trade_pct  NUMERIC(5, 2) NOT NULL DEFAULT 1.00,
    max_daily_risk_pct      NUMERIC(5, 2) NOT NULL DEFAULT 3.00,
    max_open_trades         SMALLINT NOT NULL DEFAULT 3,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (strategy_name)
);

-- ------------------------------------------------------------
-- 15. performance_metrics
-- Aggregated stats per strategy/setup type over time.
-- ------------------------------------------------------------
CREATE TABLE performance_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    strategy_name       VARCHAR(50) NOT NULL,
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    total_trades        INTEGER NOT NULL DEFAULT 0,
    win_count           INTEGER NOT NULL DEFAULT 0,
    loss_count          INTEGER NOT NULL DEFAULT 0,
    win_rate_pct        NUMERIC(5, 2),
    avg_r_multiple      NUMERIC(6, 2),
    max_drawdown_pct    NUMERIC(5, 2),
    net_profit          NUMERIC(15, 2),
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_performance_lookup ON performance_metrics (strategy_name, period_start);
