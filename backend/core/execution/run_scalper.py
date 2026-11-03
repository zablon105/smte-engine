import builtins


def print_f(*args, **kwargs):
    kwargs.setdefault("flush", True)
    builtins.print(*args, **kwargs)

"""
run_scalper.py
Command-line Intraday Scalper & Precision Execution Engine for SMTE.

Operates on Lower Timeframes (M1 / M3 / M5) to capture high-probability,
low-risk scalping opportunities:
  1. Identifies HTF (M15) CRT Liquidity Sweeps
  2. Confirms LTF (M5/M1) Market Structure Shifts (MSS) & Fair Value Gaps (FVG)
  3. Executes precision entries with ultra-tight stop losses (4-8 pips)
  4. Automatically moves open trades to Breakeven at +1.0R to lock in risk-free gains

Default Active Portfolio:
  - EURUSD.m (EUR/USD Forex Major)
  - GBPUSD.m (GBP/USD Forex Major)
  - USDJPY.m (USD/JPY Forex Major)
  - XAUUSD.m (Gold)
  - BTCUSD.m (Bitcoin 24/7)
"""

import argparse
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import List, Optional

from app.database.base import SessionLocal
from app.models.models import Instrument, RiskParameter, Trade
from app.services import mt5_client
from app.services.risk_manager import calculate_lot_size, can_open_new_trade, get_or_create_risk_parameters
from core.execution.order_executor import get_filling_type, sync_and_manage_open_trades, DEFAULT_MAGIC_NUMBER
from core.execution.scalp_refiner import detect_ltf_mss_and_fvg, _true_pip_size
import MetaTrader5 as mt5


DEFAULT_SCALP_SYMBOLS = [
    "EURUSD.m",
    "GBPUSD.m",
    "USDJPY.m",
    "XAUUSD.m",
    "BTCUSD.m",
]


def scan_symbol_for_scalp(
    db,
    symbol: str,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: float = 25.0,
):
    """
    Connects to MT5, pulls recent M15 and M5 candles, and checks
    if an active CRT sweep + LTF Market Structure Shift is active right now.
    """
    inst = db.query(Instrument).filter_by(symbol=symbol).first()
    if not inst:
        return None

    true_pip = _true_pip_size(inst.digits, float(inst.pip_size), symbol)

    # Pull recent M15 candles to identify reference range & sweep
    m15_rates = mt5_client.fetch_candles_by_count(symbol, "M15", 40)
    if m15_rates is None or len(m15_rates) < 15:
        return None

    # Reference range from prior 8 bars before the recent 3 bars
    lookback_range = m15_rates[-12:-3]
    range_high = max(float(r['high']) for r in lookback_range)
    range_low = min(float(r['low']) for r in lookback_range)
    recent_bars = m15_rates[-3:]

    # Check if any of the recent 3 bars swept the range
    swept_bullish = False
    swept_bearish = False
    sweep_price = None

    for bar in reversed(recent_bars):
        b_low = float(bar['low'])
        b_high = float(bar['high'])
        b_close = float(bar['close'])
        if b_low < range_low and b_close > range_low:
            swept_bullish = True
            sweep_price = b_low
            break
        elif b_high > range_high and b_close < range_high:
            swept_bearish = True
            sweep_price = b_high
            break

    if not swept_bullish and not swept_bearish:
        return None

    direction = "BULLISH" if swept_bullish else "BEARISH"

    # Pull LTF (M5/M1) candles covering the recent sweep
    ltf_rates = mt5_client.fetch_candles_by_count(symbol, ltf, 25)
    if ltf_rates is None or len(ltf_rates) < 5:
        return None

    ltf_candles = [
        SimpleNamespace(
            open=float(r['open']),
            high=float(r['high']),
            low=float(r['low']),
            close=float(r['close']),
            open_time=datetime.fromtimestamp(int(r['time']), tz=timezone.utc),
        )
        for r in ltf_rates
    ]

    result = detect_ltf_mss_and_fvg(
        ltf_candles=ltf_candles,
        direction=direction,
        sweep_price=sweep_price,
        pip_size=true_pip,
    )

    if result is None:
        return None

    entry_price = float(result["entry_price"])
    stop_loss = float(result["stop_loss"])
    trade_dir = result["direction"]

    if trade_dir == "BUY":
        risk_dist = entry_price - stop_loss
        take_profit = entry_price + (risk_dist * risk_reward_ratio)
    else:
        risk_dist = stop_loss - entry_price
        take_profit = entry_price - (risk_dist * risk_reward_ratio)

    if risk_dist <= 0:
        return None

    risk_pips = risk_dist / true_pip
    if risk_pips > max_risk_pips:
        return None

    return {
        "symbol": symbol,
        "instrument_id": inst.id,
        "direction": trade_dir,
        "entry_price": round(entry_price, inst.digits),
        "stop_loss": round(stop_loss, inst.digits),
        "take_profit": round(take_profit, inst.digits),
        "risk_pips": round(risk_pips, 1),
        "reward_pips": round(risk_pips * risk_reward_ratio, 1),
        "has_fvg": result["has_fvg"],
        "ltf": ltf,
        "contract_size": float(inst.contract_size or 100000.0),
        "digits": inst.digits,
    }


def execute_scalp(
    db,
    scalp: dict,
    dry_run: bool = True,
    magic: int = DEFAULT_MAGIC_NUMBER,
    fixed_lots: Optional[float] = 0.01,
    max_lots: float = 0.10,
):
    # Check if an open trade for this instrument already exists
    existing_open = (
        db.query(Trade)
        .filter_by(instrument_id=scalp["instrument_id"], status="OPEN")
        .first()
    )
    if existing_open:
        return None

    allowed, reason = can_open_new_trade(db)
    if not allowed:
        print_f(f"[Scalper] Trade rejected by risk manager: {reason}")
        return None

    risk_params = get_or_create_risk_parameters(db)
    acc = mt5_client.get_account_info()
    equity = float(acc.equity)

    # Lot sizing: uniform fixed micro-lots (default 0.01) for beginner safety, or capped dynamic % risk
    if fixed_lots is not None and fixed_lots > 0:
        lot_size = fixed_lots
    else:
        lot_size = calculate_lot_size(
            account_equity=equity,
            risk_pct=float(risk_params.max_risk_per_trade_pct),
            entry_price=scalp["entry_price"],
            stop_loss=scalp["stop_loss"],
            contract_size=scalp["contract_size"],
            max_lot=max_lots,
        )

    symbol = scalp["symbol"]
    direction = scalp["direction"]
    price = scalp["entry_price"]
    sl = scalp["stop_loss"]
    tp = scalp["take_profit"]

    if dry_run:
        print_f(f"[Scalper - DRY RUN] -> Would execute {direction} {lot_size} lots on {symbol} @ {price} | SL: {sl} ({scalp['risk_pips']} pips) | TP: {tp} ({scalp['reward_pips']} pips)")
        return None

    tick = mt5_client.get_symbol_tick(symbol)
    if not tick:
        print_f(f"[Scalper] Could not get tick for {symbol}")
        return None

    exec_price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": exec_price,
        "sl": sl,
        "tp": tp,
        "deviation": 15,
        "magic": magic,
        "comment": f"SMTE_SCALP_{scalp['ltf']}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(symbol),
    }

    try:
        res = mt5_client.send_order(request)
        trade = Trade(
            instrument_id=scalp["instrument_id"],
            mt5_ticket=res.order,
            direction=direction,
            lot_size=lot_size,
            entry_price=res.price,
            stop_loss=sl,
            take_profit=tp,
            opened_at=datetime.now(timezone.utc),
            status="OPEN",
        )
        db.add(trade)
        db.commit()
        print_f(f"[Scalper] EXECUTED {direction} {lot_size} lots {symbol} @ {res.price} (Ticket #{res.order}) | Risk: {scalp['risk_pips']} pips")
        return res.order
    except Exception as e:
        print_f(f"[Scalper] Execution failed on {symbol}: {e}")
        return None


def run_scalp_cycle(db, symbols: List[str], ltf: str, dry_run: bool = True, fixed_lots: Optional[float] = 0.01, max_lots: float = 0.10):
    mt5_client.connect()
    try:
        print_f(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] Scanning {len(symbols)} pairs ({', '.join(symbols)}) for {ltf} scalps...")
        found_any = False

        for symbol in symbols:
            try:
                scalp = scan_symbol_for_scalp(db, symbol, ltf=ltf)
                if scalp:
                    found_any = True
                    print_f(f"[MATCH] {symbol} {scalp['direction']} | Entry: {scalp['entry_price']} | SL: {scalp['stop_loss']} ({scalp['risk_pips']} pips) | TP: {scalp['take_profit']} | FVG: {scalp['has_fvg']}")
                    execute_scalp(db, scalp, dry_run=dry_run, fixed_lots=fixed_lots, max_lots=max_lots)
            except Exception as e:
                print_f(f"[{symbol}] Error scanning: {e}")

        if not found_any:
            print_f("         No active sweep + LTF displacement at this moment.")

        # Always sync open trades
        stats = sync_and_manage_open_trades(db, breakeven_trigger_r=1.0)
        if stats["managed"] > 0:
            print_f(f"[Trade Manager] Open trades: {stats['managed']} | Closed: {stats['closed']} | Breakeven Set: {stats['breakeven_set']}")
    finally:
        mt5_client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="SMTE Intraday Scalper Engine.")
    parser.add_argument("--scan", action="store_true", help="Perform a scan for current scalping opportunities")
    parser.add_argument("--execute", action="store_true", help="Execute real market orders on MT5 (live demo)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing orders")
    parser.add_argument("--sync-trades", action="store_true", help="Sync active trades and manage Breakeven")
    parser.add_argument("--monitor", action="store_true", help="Run continuously in background monitor mode")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds between scan cycles (default 60)")
    parser.add_argument("--timeframe", default="M5", choices=["M1", "M3", "M5"], help="Execution timeframe (default M5)")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SCALP_SYMBOLS, help="Symbols to scan")
    parser.add_argument("--fixed-lots", type=float, default=0.01, help="Fixed uniform lot size for all pairs (default 0.01 micro-lots for beginner safety, set 0 for dynamic % risk)")
    parser.add_argument("--max-lots", type=float, default=0.10, help="Maximum allowed lot size cap when using dynamic risk (default 0.10)")
    args = parser.parse_args()

    is_dry_run = not args.execute

    db = SessionLocal()
    try:
        if args.sync_trades:
            stats = sync_and_manage_open_trades(db)
            print_f(f"[Order Executor] Active trades sync: {stats}")
            return

        if args.monitor:
            print_f(f"[SMTE Scalper] Starting continuous monitoring on {args.timeframe} across {args.symbols} (dry_run={is_dry_run})...")
            while True:
                run_scalp_cycle(db, symbols=args.symbols, ltf=args.timeframe, dry_run=is_dry_run, fixed_lots=args.fixed_lots, max_lots=args.max_lots)
                time.sleep(args.interval)
        else:
            run_scalp_cycle(db, symbols=args.symbols, ltf=args.timeframe, dry_run=is_dry_run, fixed_lots=args.fixed_lots, max_lots=args.max_lots)
    finally:
        db.close()


if __name__ == "__main__":
    main()
