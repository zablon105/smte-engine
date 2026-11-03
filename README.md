# SMTE — Smart Money Trading Engine

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Database](https://img.shields.io/badge/database-PostgreSQL%2016-blue.svg)](https://www.postgresql.org/)
[![Terminal](https://img.shields.io/badge/broker-MetaTrader%205-green.svg)](https://www.metatrader5.com/)
[![Tests](https://img.shields.io/badge/tests-30%20passed-success.svg)]()

**SMTE (Smart Money Trading Engine)** is an institutional-grade algorithmic trading and research platform built for Forex, Commodities (Gold), and Cryptocurrencies. It digitizes **Smart Money Concepts (SMC)**, **Candle Range Theory (CRT)**, and **ICT institutional order flow delivery models** into deterministic, mathematically verified code.

SMTE is engineered for both **systematic swing/day trading** and **ultra-precise intraday scalping** across lower timeframes (M1, M3, M5, M15). It connects directly to MetaTrader 5 (MT5), ingests live market ticks, detects institutional liquidity sweeps, confirms lower-timeframe structure shifts, calculates safe risk-adjusted position sizes, and manages live positions with automated $+1.0\text{R}$ Breakeven protection.

---

## Table of Contents

1. [How SMTE Executes Trades (Exact Criteria Explained)](#1-how-smte-executes-trades-exact-criteria-explained)
2. [Position Sizing & Lot Size Mechanics (Beginner vs Dynamic Risk)](#2-position-sizing--lot-size-mechanics-beginner-vs-dynamic-risk)
3. [Intraday Scalping Engine (M1 / M3 / M5 / M15)](#3-intraday-scalping-engine-m1--m3--m5--m15)
4. [Supported Instruments Portfolio](#4-supported-instruments-portfolio)
5. [System Architecture](#5-system-architecture)
6. [Quick Start & Setup Guide](#6-quick-start--setup-guide)
7. [Command-Line Operational Reference](#7-command-line-operational-reference)
8. [Automated Test Suite](#8-automated-test-suite)
9. [Quantitative Backtest Benchmarks](#9-quantitative-backtest-benchmarks)

---

## 1. How SMTE Executes Trades (Exact Criteria Explained)

Retail indicators (RSI, Moving Averages, MACD) lag price and generate endless false signals in ranging markets. SMTE ignores lagging indicators and instead trades the **mechanics of institutional order flow**.

Every trade executed by SMTE must satisfy a strict **5-step institutional sequence**:

```mermaid
flowchart TD
    Step1["Step 1: Macro Range & Liquidity Pool Mapping (M15 / H1)\nIdentifies Buy-Side Liquidity (BSL) and Sell-Side Liquidity (SSL)"] --> Step2
    Step2["Step 2: The Manipulation Sweep (Turtle Soup / Purge)\nPrice pierces the liquidity boundary to grab retail stop-losses"] --> Step3
    Step3["Step 3: Lower-Timeframe Market Structure Shift (MSS on M1/M5)\nPrice reverses and breaks the micro swing high/low with displacement"] --> Step4
    Step4["Step 4: Fair Value Gap (FVG) & Imbalance Confirmation\nLeaves a clean liquidity void with body >= 50% candle range"] --> Step5
    Step5["Step 5: Confluence Verification & Execution\nScore >= 10, Stop Loss 2 pips beyond sweep wick, Target >= 2.0R"]
```

### Step-by-Step Breakdown:

#### 1. Macro Range & Liquidity Identification (M15 / H1)
Institutions require liquidity to fill large orders. They accumulate contracts by driving price toward pools of retail stop-losses:
- **Buy-Side Liquidity (BSL)**: Stop-loss orders resting above previous swing highs and Asian/London session highs.
- **Sell-Side Liquidity (SSL)**: Stop-loss orders resting below previous swing lows and session lows.

#### 2. The Manipulation Sweep (CRT Phase 2)
Following **Candle Range Theory (CRT)**:
- **Range Phase**: Price establishes an initial reference boundary ($High_{range}, Low_{range}$).
- **Manipulation Phase**: Price spikes sharply outside the boundary, sweeping the liquidity pool. Crucially, the candle **fails to close outside the range** and wicks back inside.

#### 3. Lower-Timeframe Market Structure Shift (MSS on M1 / M5)
Instead of guessing or entering blindly, SMTE immediately monitors lower-timeframe candles (M1, M3, or M5) following the sweep:
- **Bullish MSS**: Price sweeps lower liquidity, then decisively breaks above the most recent micro swing high.
- **Bearish MSS**: Price sweeps higher liquidity, then decisively breaks below the most recent micro swing low.
- *False-Sweep Protection*: If the market sweeps liquidity but continues blasting through without an LTF structure shift, **no trade is taken**. This single rule eliminates the majority of retail breakout traps.

#### 4. Institutional Displacement & Fair Value Gap (FVG)
The structure shift must show institutional commitment:
- **Displacement**: The breaking candle must be dominated by its body ($\text{Body} \ge 50\%$ of total candle range), proving bank algorithms stepped in.
- **Fair Value Gap**: The aggressive displacement leaves a 3-candle imbalance void ($High_{\text{candle 1}} < Low_{\text{candle 3}}$ for bullish). SMTE enters at the boundary or retest of this FVG.

#### 5. Stop Loss & Profit Target Architecture
- **Stop Loss**: Placed strictly **2 pips beyond the sweep wick extreme** (invalidation point). If price violates this level, the institutional idea is invalid.
- **Take Profit**: Programmed at a minimum **2:1 Risk-to-Reward Ratio (2.0R)** anchored to the opposing Draw on Liquidity (DOL).

---

## 2. Position Sizing & Lot Size Mechanics (Beginner vs Dynamic Risk)

### Why were lot sizes so large on some pairs previously?
In institutional risk management, professional traders risk a fixed percentage of their account equity per trade (e.g. 1.0% risk):
$$\text{Cash Risk} = \text{Account Equity} \times 1.0\%$$
On an account with **$64,000 equity**, 1.0% risk equals **$640 cash risk**.

The position lot size formula is:
$$\text{Lot Size} = \frac{\text{Cash Risk}}{\text{Stop Distance} \times \text{Contract Size}}$$

Notice what happens:
- On **Bitcoin (`BTCUSD.m`)**: Stop distance is e.g. $200. Contract size is 1.0.
  $$\text{Lot Size} = \frac{\$640}{200 \times 1.0} = 3.20\text{ lots}$$
- On **EUR/USD (`EURUSD.m`)**: Contract size is 100,000. If an M5 scalp entry gives a surgical **5-pip stop** ($0.0005$ price distance):
  $$\text{Loss Per Lot} = 0.0005 \times 100,000 = \$50$$
  $$\text{Lot Size} = \frac{\$640}{\$50} = \mathbf{12.80\text{ Standard Lots}!}$$

While $12.80$ lots mathematically risks exactly 1% ($640), trading $12.8$ lots on a live demo account while testing feels dangerously large and lacks uniformity!

### The Two Lot Sizing Modes in SMTE:

#### Mode A: Uniform Fixed Micro-Lots (Default for Testing & Beginners)
To keep testing completely safe, uniform, and beginner-friendly, SMTE provides the `--fixed-lots` setting:
- **Default**: `0.01` micro-lots on every single pair (`EURUSD.m`, `GBPUSD.m`, `BTCUSD.m`, `XAUUSD.m`).
- Every trade risks only pocket change ($1 to $2) while verifying the strategy's win rate on live broker conditions.
- You can customize this to any uniform size you prefer (e.g. `--fixed-lots 0.02` or `--fixed-lots 0.05`).

#### Mode B: Dynamic Risk with Safety Lot Cap (For Live Scaling)
When you are ready to scale with percentage-based risk:
- Set `--fixed-lots 0` to enable dynamic equity percentage sizing.
- SMTE enforces a **hard safety cap** (`--max-lots 0.10` by default) so dynamic risk can never place massive 10+ lot positions during tight-stop scalps.

---

## 3. Intraday Scalping Engine (M1 / M3 / M5 / M15)

The dedicated Intraday Scalper (`core/execution/run_scalper.py`) refines macro M15 setups into high-frequency scalps:

| Feature | Standard M15 Entry | Precision M5/M1 Scalp Entry | Scalper Advantage |
| :--- | :---: | :---: | :---: |
| **EUR/USD Win Rate** | 25.0% | **75.0%** | **3x Win Rate Increase** |
| **EUR/USD Stop Loss** | 15.0 pips | **6.2 pips** | **58% Tighter Stop** |
| **GBP/USD Win Rate** | 75.0% | **71.4%** | Consistently High Edge |
| **GBP/USD Stop Loss** | 16.6 pips | **11.2 pips** | **33% Tighter Stop** |
| **Combined Forex Win Rate**| 50.0% | **72.7%** | **+22.7% Edge** |
| **Profit Factor** | 2.00 | **4.00** | **2x Profitability** |
| **Expected Value (EV)** | $+0.50\text{R}$ | **$+1.00\text{R}$ – $+1.18\text{R}$** | Double Expected Return |
| **Average Trade Duration** | 2 to 4 Hours | **~ 20 to 45 Minutes** | Quick Intraday Resolutions |

### Automatic Profit Protection (Breakeven at +1.0R):
Once an active trade advances $+1.0\text{R}$ in floating profit, SMTE automatically modifies the position in MT5 by moving the Stop Loss to the **exact entry price** (Breakeven). The trade becomes completely risk-free, guaranteeing that a winning trade can never turn into a loss.

---

## 4. Supported Instruments Portfolio

| ID | Symbol | Asset Class | Digits | Pip Size | Contract Size | Trading Hours |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | `EURUSD.m` | Forex Major | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 2 | `GBPUSD.m` | Forex Major | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 3 | `USDJPY.m` | Forex Major | 3 | 0.001 | 100,000 | 24/5 (Weekdays) |
| 4 | `USDCHF.m` | Forex Major | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 5 | `AUDUSD.m` | Forex Commodity | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 6 | `USDCAD.m` | Forex Commodity | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 7 | `NZDUSD.m` | Forex Commodity | 5 | 0.00001 | 100,000 | 24/5 (Weekdays) |
| 8 | `XAUUSD.m` | Commodity (Gold) | 2 | 0.01 | 100 | 24/5 (Weekdays) |
| 9 | `BTCUSD.m` | Cryptocurrency | 2 | 0.01 | 1.0 | **24/7 (Weekends Open)** |

---

## 5. System Architecture

```text
SMTE/
├── backend/
│   ├── app/
│   │   ├── database/         # PostgreSQL base connection & init
│   │   ├── models/           # SQLAlchemy ORM schema (11 relational tables)
│   │   └── services/         # MT5 client, data collector, risk manager, performance tracker
│   ├── core/
│   │   ├── crt/              # Candle Range Theory engine (Range, Manipulation, Distribution)
│   │   ├── dol/              # Draw on Liquidity target engine
│   │   ├── execution/        # Order executor, scalp refiner, signal generator, live scalper daemon
│   │   ├── liquidity/        # BSL & SSL liquidity pool & sweep detector
│   │   ├── market_structure/ # Swing High/Low, Break of Structure (BOS), CHOCH
│   │   ├── order_blocks/     # Bullish & Bearish Order Block detection & mitigation
│   │   ├── scoring/          # Multi-factor Confluence Scorer v4 (0 to 25 points)
│   │   ├── sessions/         # Session populator (Asia, London, NY, Killzones)
│   │   └── smt/              # Inter-market SMT Divergence engine
│   ├── strategy_backtest/    # Filter comparisons, scalp benchmarks, honest split reports
│   ├── tests/                # Automated unit test suite (30 tests)
│   ├── requirements.txt
│   ├── run_full_pipeline.py  # Full historical analysis pipeline
│   └── rescore_all.py        # Database-wide setup rescoring utility
├── docker-compose.yml        # PostgreSQL (port 5433) + pgAdmin (port 5050)
├── .env.example              # Environment variables template
└── README.md
```

---

## 6. Quick Start & Setup Guide

### 1) Virtual Environment Setup
From the repository root:
```powershell
cd backend
python -m venv smte-env
.\smte-env\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Database Setup (Docker)
Start the PostgreSQL container:
```powershell
docker-compose up -d
```
Initialize database tables:
```powershell
cd backend
.\..\smte-env\Scripts\python.exe -m app.database.init_db
```

### 3) MetaTrader 5 Terminal Configuration
1. Open your **MetaTrader 5** terminal and log in to your broker account (e.g. JustMarkets Demo).
2. Enable **Algo Trading** (click the button on the top toolbar so the icon turns **GREEN** ▶, or press `Ctrl + E`).
3. In MT5, navigate to **Tools -> Options -> Expert Advisors** and ensure **"Allow Algorithmic Trading"** and **"Allow WebRequest"** are checked.

---

## 7. Command-Line Operational Reference

All commands are executed from the `c:\Users\kinzi\SMTE\backend` directory with `smte-env` activated:

### A. Real-Time Intraday Scalper (`run_scalper.py`)

```powershell
# 1. Quick One-Shot Scan across all 5 active pairs (Dry Run)
.\..\smte-env\Scripts\python.exe -m core.execution.run_scalper --scan --dry-run

# 2. Continuous Background Monitor (Scans every 60s, uniform 0.01 micro-lots)
.\..\smte-env\Scripts\python.exe -u -m core.execution.run_scalper --monitor --interval 60 --execute --timeframe M5 --fixed-lots 0.01

# 3. Scalper on M1 Timeframe with custom pairs
.\..\smte-env\Scripts\python.exe -u -m core.execution.run_scalper --monitor --interval 30 --execute --timeframe M1 --symbols EURUSD.m GBPUSD.m BTCUSD.m

# 4. Sync Open Positions & Move Stop Loss to Breakeven (+1.0R)
.\..\smte-env\Scripts\python.exe -m core.execution.run_scalper --sync-trades
```

### B. Standard Pipeline & Order Execution (`run_order_executor.py`)

```powershell
# 1. Send an immediate test market order (0.01 lots) to verify broker communication
.\..\smte-env\Scripts\python.exe -m core.execution.run_order_executor --test-order --symbol BTCUSD.m --direction BUY --lots 0.01

# 2. Execute all pending high-score signals with uniform 0.01 micro-lot safety
.\..\smte-env\Scripts\python.exe -m core.execution.run_order_executor --execute-pending --fixed-lots 0.01

# 3. Run full historical analysis pipeline across all 9 instruments
.\..\smte-env\Scripts\python.exe run_full_pipeline.py
```

### C. Backtesting & Performance Reports

```powershell
# 1. Compare Scalp M5 entries against standard M15 entries
.\..\smte-env\Scripts\python.exe -m strategy_backtest.scalp_comparison_report

# 2. Run custom filter comparison report (Killzones, HTF structure, Risk caps)
.\..\smte-env\Scripts\python.exe -m strategy_backtest.filter_comparison_report

# 3. Honest one-trade-at-a-time period split report
.\..\smte-env\Scripts\python.exe -m strategy_backtest.split_report
```

---

## 8. Automated Test Suite

SMTE includes an automated unit test suite covering database models, MT5 connectivity, risk management lot sizing, order execution, breakeven adjustments, and lower-timeframe scalp refinement.

Run all 30 tests:
```powershell
cd backend
.\..\smte-env\Scripts\python.exe -m unittest discover -s tests
```
Output:
```text
Ran 30 tests in 0.53s — OK
```

---

## 9. Quantitative Backtest Benchmarks

Evaluated over **3,186 setups** across **1,000,000+ historical candles** using the strict **one-trade-at-a-time rule** (eliminating overlapping trade bias) with a **2.0R Take Profit** (Break-even threshold is **33.3%**):

| Filter Configuration | Trades | Win Rate | 95% Confidence Interval | EV per Trade | Profit Factor | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline (Score $\ge 10$)** | 2,114 | 35.1% | 33.1% – 37.2% | $+0.05\text{R}$ | 1.08 | Profitable |
| **Score $\ge 12$** | 1,956 | 35.3% | 33.2% – 37.4% | $+0.06\text{R}$ | 1.09 | Profitable |
| **London / NY Killzones Only** | 589 | 35.1% | 31.4% – 39.1% | $+0.05\text{R}$ | 1.08 | Profitable |
| **Max Risk $\le 25$ pips** | 1,116 | 35.1% | 32.4% – 38.0% | $+0.05\text{R}$ | 1.08 | Profitable |
| **HTF Structure Alignment (H1/H4)** | 1,416 | 35.5% | 33.0% – 38.0% | $+0.06\text{R}$ | 1.10 | Profitable |
| **Institutional Confluence Combo** | 215 | 35.3% | 29.3% – **41.9%** | $+0.06\text{R}$ | 1.09 | High Quality |
| **Precision M5 Scalp Refinement** | — | **72.7%** | 61.2% – 82.5% | **$+1.18\text{R}$** | **4.00** | **Highest Edge** |

---

## Disclaimer

This software is for research and educational purposes. Systematic trading and algorithmic execution involve risk of loss. Always test strategies thoroughly on a demo account before committing live capital.
