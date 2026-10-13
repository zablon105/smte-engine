# SMTE (Smart Money Trading Engine)

SMTE is a Python-based trading research and signal-generation system built around Smart Money Concepts (SMC), market structure analysis, and systematic backtesting. It ingests MT5 market data, detects liquidity zones, order blocks, CRT setups, and fair value gaps, scores the setups by confluence, generates trade signals, and evaluates them with a backtesting layer.

The project is organized around a backend pipeline, a PostgreSQL database, and a separate dashboard/front-end layer for monitoring and analysis.

## What the system does

The pipeline turns raw market data into tradable trade ideas:

- Collects OHLCV candles from MT5 across multiple timeframes
- Stores market data in PostgreSQL
- Detects market microstructure concepts:
  - liquidity zones
  - order blocks
  - market structure shifts
  - fair value gaps
  - CRT setups
- Scores setups using confluence logic
- Generates trade signals with entries, stops, and take-profit levels
- Runs backtests to evaluate signal quality and robustness
- Produces split-period reports to check whether results hold across time

This is designed as a research engine for trading idea generation and validation, not as a turnkey broker execution system.

## Repository structure

```text
SMTE/
├── backend/
│   ├── app/
│   │   ├── database/
│   │   ├── models/
│   │   ├── services/
│   │   └── ...
│   ├── core/
│   │   ├── crt/
│   │   ├── execution/
│   │   ├── liquidity/
│   │   ├── market_analysis/
│   │   ├── order_blocks/
│   │   ├── scoring/
│   │   └── ...
│   ├── strategies/
│   ├── strategy_backtest/
│   ├── requirements.txt
│   ├── run_full_pipeline.py
│   └── ...
├── dashboard/
├── data/
├── docs/
├── mt5/
├── research/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## Core backend components

### app

Contains the application layer for database access, ORM models, and MT5 integration.

- `app/database/` manages the PostgreSQL connection and database initialization
- `app/models/models.py` contains the SQLAlchemy schema used by the engine
- `app/services/` includes the MT5 connector and candle collector

### core

This is the analytics engine where the market structure and scoring logic lives.

- `core/crt/` detects CRT setup patterns
- `core/liquidity/` detects liquidity pools and sweeps
- `core/order_blocks/` detects bullish/bearish order blocks
- `core/market_analysis/` covers FVG and related structure logic
- `core/scoring/` ranks setups by confluence strength
- `core/execution/` prepares trade signals from valid setups

### strategy_backtest

Responsible for evaluating the generated trade signals.

- `signal_backtest.py` performs the underlying backtest logic
- `split_report.py` reports results with a one-trade-at-a-time rule and period split
- `tiered_report.py` provides banded score-based summaries

## Database model

The system uses PostgreSQL and stores all market and analysis data in a relational model. Major tables include:

- `instruments`
- `candles`
- `sessions`
- `liquidity_zones`
- `order_blocks`
- `fair_value_gaps`
- `market_structure`
- `crt_setups`
- `setup_scores`
- `trade_signals`
- analytics and backtest tables

The schema is defined in `backend/app/database/schema.sql` and can be created from the SQLAlchemy models via `app.database.init_db`.

## System workflow

The full analysis pipeline usually runs in the following order:

1. Connect to MT5
2. Pull candles for required symbols and timeframes
3. Save market data into PostgreSQL
4. Detect liquidity zones and order blocks
5. Detect market structure and CRT setups
6. Detect FVGs and other confluence inputs
7. Score CRT setups with the confluence engine
8. Generate trade signals based on valid, high-score setups
9. Run historical backtests to evaluate outcomes
10. Review performance by score band, time period, and signal quality

## Quick start

### 1) Setup environment

From the repository root:

```bash
cd backend
python -m venv smte-env
# Windows PowerShell
./smte-env/Scripts/Activate.ps1
# Linux/macOS
source smte-env/bin/activate
pip install -r requirements.txt
```

### 2) Configure environment variables

Copy the sample environment file and set your database and MT5 credentials:

```bash
cp .env.example .env
```

Then update the values in `.env` for:

- PostgreSQL database settings
- MT5 login, password, and server

### 3) Start PostgreSQL

The repository includes Docker Compose for the database stack:

```bash
docker-compose up -d
```

This launches:

- PostgreSQL on `localhost:5433`
- pgAdmin on `http://localhost:5050`

### 4) Initialize the database

```bash
cd backend
python -m app.database.init_db
```

### 5) Collect market data

```bash
cd backend
python -m app.services.run_collector --symbol EURUSD.m --timeframe M15 --count 1000
```

You can also run the complete pipeline for multiple symbols:

```bash
cd backend
python run_full_pipeline.py --min-gap-pips 1.0
```

## Running the pipeline and analysis

### Full pipeline

```bash
cd backend
python run_full_pipeline.py --min-gap-pips 1.0
```

This script loops through the configured symbols, runs each stage of the engine, and prints an aggregate summary of the results.

### Signal backtest

You can evaluate trade signals directly with the backtest utilities:

```bash
cd backend
python -m strategy_backtest.run_backtest
```

### Score band and period reporting

The project includes a more honest reporting style that avoids overcounting overlapping signals and shows results across time splits.

```bash
cd backend
python -m strategy_backtest.split_report
python -m strategy_backtest.split_report --cutoff 2026-05-01 --rr 2.0
```

This report helps answer questions like:

- Did the signal quality hold in both earlier and later market periods?
- Are results driven by a few duplicate trades?
- Is a score band still strong once the one-trade-at-a-time rule is applied?

## Important design notes

### One trade at a time

The reporting layer includes a filter that ignores new signals on the same symbol and direction when an earlier accepted trade is still open. This reduces overstatement caused by near-duplicate trades being treated as independent samples.

### Time-split validation

Reports can be split by entry date using a cutoff. This is valuable because a strategy can look good on older data yet fail on later, more recent market conditions.

### Wilson interval handling

The reporting system uses Wilson confidence intervals for win-rate estimates. This is useful when sample sizes are limited and simple percentages can appear more certain than they really are.

## Dependencies

The backend primarily uses:

- Python 3.10+
- SQLAlchemy
- PostgreSQL
- pandas / numpy
- FastAPI
- MetaTrader 5 integration layer
- timezone-aware market data processing

See `backend/requirements.txt` for the full dependency list.

## Use cases

This project is best suited for:

- research-driven trading system development
- signal validation for SMC-style setups
- market structure analysis and pattern detection
- historical market evaluation across multiple symbols and timeframes
- generating quantified trade idea statistics before live execution

## Notes

- The system depends on real MT5 market data and broker connectivity for full historical collection.
- It is intended for research, analysis, and backtesting workflows rather than direct automated execution by default.
- The process is iterative: the market patterns, scoring rules, and signal filters are designed to be adjusted and tested against live historical data.

## Recommended next step

If you are starting from a blank environment, the most practical path is:

1. start PostgreSQL
2. initialize the database
3. collect a few symbol/timeframe datasets
4. run the pipeline for one or two instruments
5. inspect the signal/output reports before expanding to broader scans

This keeps the system grounded in real market data while preserving enough flexibility to refine the strategy logic.
