import builtins


def print_f(*args, **kwargs):
    kwargs.setdefault("flush", True)
    builtins.print(*args, **kwargs)

"""
run_scalper.py
Command-line Intraday Scalper & Precision Execution Engine for SMTE.

Operates on Lower Timeframes (M1 / M3 / M5 / M15) with multiple institutional strategy models:
  1. CRT (default): M15 Range Liquidity Sweep + LTF (M1/M5) MSS & FVG refinement.
  2. UNICORN: Swing Liquidity Sweep + Breaker Block + FVG Overlap Zone Retracement.
  3. TURTLE_SOUP: 3-candle False Breakout Purge (TBS / TWS) with 50% midpoint target.
  4. PO3: Power of 3 (AMD) Judas Swing & time-based discount/premium entry pricing.
  5. ALL: Scans all active strategy models simultaneously.

Features:
  - Precision entries with tight risk-managed stop losses (4-15 pips).
  - Automated Breakeven protection at +1.0R profit via live trade manager.
  - Safe uniform micro-lots (0.01) for testing or dynamic equity % risk with hard lot caps.
"""

import argparse
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional, Any

from app.database.base import SessionLocal
from app.models.models import Instrument, RiskParameter, Trade
from app.services import mt5_client
from app.services.risk_manager import calculate_lot_size, can_open_new_trade, get_or_create_risk_parameters
from core.execution.order_executor import get_filling_type, sync_and_manage_open_trades, DEFAULT_MAGIC_NUMBER
from core.execution.scalp_refiner import detect_ltf_mss_and_fvg, _true_pip_size
from core.strategy_rules import (
    active_session_windows,
    calculate_breaker_zone,
    calculate_unicorn_overlap,
    evaluate_po3_pricing,
    evaluate_turtle_soup_sequence,
)
import MetaTrader5 as mt5


def is_market_session_active(symbol: str, max_idle_seconds: int = 300) -> bool:
    """Check if live ticks are actively streaming for a symbol (skips closed weekend markets)."""
    try:
        tick = mt5_client.get_symbol_tick(symbol)
        if tick is None or not hasattr(tick, "time"):
            return False
        if isinstance(tick.time, (int, float)):
            return abs(time.time() - tick.time) <= max_idle_seconds
        return True
    except Exception:
        return True



DEFAULT_SCALP_SYMBOLS = [
    "EURUSD.m",
    "GBPUSD.m",
    "USDJPY.m",
    "XAUUSD.m",
    "BTCUSD.m",
]

SUPPORTED_STRATEGIES = ["crt", "unicorn", "turtle_soup", "po3", "all"]


# =====================================================================
# 1. STRATEGY SCANNER: CRT SWEEP + LTF MSS/FVG
# =====================================================================

def _scan_crt(
    inst: Instrument,
    symbol: str,
    true_pip: float,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: float = 25.0,
) -> Optional[Dict[str, Any]]:
    # Pull recent M15 candles to identify reference range & sweep
    m15_rates = mt5_client.fetch_candles_by_count(symbol, "M15", 40)
    if m15_rates is None or len(m15_rates) < 15:
        return None

    lookback_range = m15_rates[-12:-3]
    range_high = max(float(r['high']) for r in lookback_range)
    range_low = min(float(r['low']) for r in lookback_range)
    recent_bars = m15_rates[-3:]

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
        "strategy": "CRT",
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
        "details": f"M15 CRT sweep + {ltf} MSS displacement",
    }


# =====================================================================
# 2. STRATEGY SCANNER: UNICORN MODEL (BREAKER + FVG OVERLAP)
# =====================================================================

def _scan_unicorn(
    inst: Instrument,
    symbol: str,
    true_pip: float,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: float = 30.0,
) -> Optional[Dict[str, Any]]:
    rates = mt5_client.fetch_candles_by_count(symbol, ltf, 35)
    if rates is None or len(rates) < 15:
        return None

    # Check for recent sweep of swing high or low in prior bars
    prior_bars = rates[-15:-3]
    recent_bars = rates[-3:]

    prior_high = max(float(r['high']) for r in prior_bars)
    prior_low = min(float(r['low']) for r in prior_bars)

    c_curr = recent_bars[-2]
    c_prev = recent_bars[-3]

    is_bull_sweep = float(c_curr['low']) < prior_low and float(c_curr['close']) > float(c_curr['open'])
    is_bear_sweep = float(c_curr['high']) > prior_high and float(c_curr['close']) < float(c_curr['open'])

    if not (is_bull_sweep or is_bear_sweep):
        return None

    direction = "BULLISH" if is_bull_sweep else "BEARISH"
    breaker_bar = c_prev

    try:
        breaker_zone = calculate_breaker_zone(
            open_price=float(breaker_bar['open']),
            close_price=float(breaker_bar['close']),
            high_price=float(breaker_bar['high']),
            low_price=float(breaker_bar['low']),
            direction=direction,
            use_body=True,
        )
    except Exception:
        return None

    # Check for aligned FVG across the sweep/displacement sequence
    c0 = recent_bars[-3]
    c2 = recent_bars[-1]
    has_fvg = False
    fvg_bottom, fvg_top = 0.0, 0.0

    if direction == "BULLISH":
        if float(c2['low']) > float(c0['high']):
            has_fvg = True
            fvg_bottom = float(c0['high'])
            fvg_top = float(c2['low'])
    else:
        if float(c0['low']) > float(c2['high']):
            has_fvg = True
            fvg_bottom = float(c2['high'])
            fvg_top = float(c0['low'])

    if not has_fvg:
        return None

    overlap = calculate_unicorn_overlap(
        breaker_bottom=breaker_zone.bottom,
        breaker_top=breaker_zone.top,
        fvg_bottom=fvg_bottom,
        fvg_top=fvg_top,
    )
    if overlap is None:
        return None

    entry_price = overlap.midpoint
    spread_buffer = true_pip * stop_buffer_pips

    if direction == "BULLISH":
        trade_dir = "BUY"
        sl = min(float(c_curr['low']), breaker_zone.bottom) - spread_buffer
        risk_dist = entry_price - sl
        tp = entry_price + (risk_dist * risk_reward_ratio)
    else:
        trade_dir = "SELL"
        sl = max(float(c_curr['high']), breaker_zone.top) + spread_buffer
        risk_dist = sl - entry_price
        tp = entry_price - (risk_dist * risk_reward_ratio)

    if risk_dist <= 0:
        return None

    risk_pips = risk_dist / true_pip
    if risk_pips > max_risk_pips:
        return None

    return {
        "strategy": "UNICORN",
        "symbol": symbol,
        "instrument_id": inst.id,
        "direction": trade_dir,
        "entry_price": round(entry_price, inst.digits),
        "stop_loss": round(sl, inst.digits),
        "take_profit": round(tp, inst.digits),
        "risk_pips": round(risk_pips, 1),
        "reward_pips": round(risk_pips * risk_reward_ratio, 1),
        "has_fvg": True,
        "ltf": ltf,
        "contract_size": float(inst.contract_size or 100000.0),
        "digits": inst.digits,
        "details": f"Breaker [{breaker_zone.bottom:.5f}-{breaker_zone.top:.5f}] + FVG Overlap [{overlap.bottom:.5f}-{overlap.top:.5f}]",
    }


# =====================================================================
# 3. STRATEGY SCANNER: TURTLE SOUP (3-CANDLE PURGE / FALSE BREAKOUT)
# =====================================================================

def _scan_turtle_soup(
    inst: Instrument,
    symbol: str,
    true_pip: float,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 1.5,
    max_risk_pips: float = 25.0,
) -> Optional[Dict[str, Any]]:
    rates = mt5_client.fetch_candles_by_count(symbol, ltf, 10)
    if rates is None or len(rates) < 4:
        return None

    # Completed 3-candle sequence: c1, c2, c3
    c1 = rates[-3]
    c2 = rates[-2]
    c3 = rates[-1]

    spread_buffer = true_pip * stop_buffer_pips

    for direction in ("BULLISH", "BEARISH"):
        eval_res = evaluate_turtle_soup_sequence(
            c1_high=float(c1['high']),
            c1_low=float(c1['low']),
            c2_open=float(c2['open']),
            c2_close=float(c2['close']),
            c2_high=float(c2['high']),
            c2_low=float(c2['low']),
            c3_close=float(c3['close']),
            direction=direction,
        )

        if not eval_res.is_valid:
            continue

        trade_dir = "BUY" if direction == "BULLISH" else "SELL"
        entry_price = float(c3['close'])
        tp1 = eval_res.targets.midpoint_tp1
        tp2 = eval_res.targets.opposing_edge_tp2
        sl = eval_res.targets.invalidation_stop

        if direction == "BULLISH":
            sl -= spread_buffer
            risk_dist = entry_price - sl
            # Primary target: 50% midpoint if favorable R:R, or opposing edge
            tp = tp2 if (tp1 - entry_price) < (risk_dist * 1.0) else tp1
        else:
            sl += spread_buffer
            risk_dist = sl - entry_price
            tp = tp2 if (entry_price - tp1) < (risk_dist * 1.0) else tp1

        if risk_dist <= 0:
            continue

        risk_pips = risk_dist / true_pip
        if risk_pips > max_risk_pips:
            continue

        reward_dist = abs(tp - entry_price)
        reward_pips = reward_dist / true_pip

        return {
            "strategy": "TURTLE_SOUP",
            "symbol": symbol,
            "instrument_id": inst.id,
            "direction": trade_dir,
            "entry_price": round(entry_price, inst.digits),
            "stop_loss": round(sl, inst.digits),
            "take_profit": round(tp, inst.digits),
            "risk_pips": round(risk_pips, 1),
            "reward_pips": round(reward_pips, 1),
            "has_fvg": False,
            "ltf": ltf,
            "contract_size": float(inst.contract_size or 100000.0),
            "digits": inst.digits,
            "details": f"Turtle Soup ({eval_res.soup_type}) | TP: {'50% Midpoint' if tp == tp1 else 'Opposing Edge'}",
        }

    return None


# =====================================================================
# 4. STRATEGY SCANNER: POWER OF 3 (PO3 / AMD)
# =====================================================================

def _scan_po3(
    inst: Instrument,
    symbol: str,
    true_pip: float,
    ltf: str = "M5",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: float = 25.0,
) -> Optional[Dict[str, Any]]:
    # Pull current day/session candles
    rates = mt5_client.fetch_candles_by_count(symbol, "H1", 24)
    if rates is None or len(rates) < 6:
        return None

    # Use first bar of recent 12 hours as the period open
    period_open = float(rates[-6]['open'])
    current_close = float(rates[-1]['close'])

    # Determine trend bias from recent swing
    bias = "BULLISH" if current_close > period_open else "BEARISH"

    pricing = evaluate_po3_pricing(
        open_price=period_open,
        current_price=current_close,
        bias=bias,
    )

    if not pricing.is_valid_entry_zone:
        return None  # Price not in PO3 discount/premium zone relative to open

    trade_dir = "BUY" if bias == "BULLISH" else "SELL"
    entry_price = current_close
    spread_buffer = true_pip * stop_buffer_pips

    # SL at recent period extreme
    if bias == "BULLISH":
        period_low = min(float(r['low']) for r in rates[-6:])
        sl = period_low - spread_buffer
        risk_dist = entry_price - sl
        tp = entry_price + (risk_dist * risk_reward_ratio)
    else:
        period_high = max(float(r['high']) for r in rates[-6:])
        sl = period_high + spread_buffer
        risk_dist = sl - entry_price
        tp = entry_price - (risk_dist * risk_reward_ratio)

    if risk_dist <= 0:
        return None

    risk_pips = risk_dist / true_pip
    if risk_pips > max_risk_pips:
        return None

    return {
        "strategy": "PO3",
        "symbol": symbol,
        "instrument_id": inst.id,
        "direction": trade_dir,
        "entry_price": round(entry_price, inst.digits),
        "stop_loss": round(sl, inst.digits),
        "take_profit": round(tp, inst.digits),
        "risk_pips": round(risk_pips, 1),
        "reward_pips": round(risk_pips * risk_reward_ratio, 1),
        "has_fvg": False,
        "ltf": ltf,
        "contract_size": float(inst.contract_size or 100000.0),
        "digits": inst.digits,
        "details": f"PO3 {bias} in {pricing.zone_type} relative to Open ({period_open:.5f})",
    }


# =====================================================================
# UNIFIED SYMBOL SCANNER (DISPATCHER)
# =====================================================================

def scan_symbol_for_scalp(
    db,
    symbol: str,
    ltf: str = "M5",
    strategy: str = "crt",
    risk_reward_ratio: float = 2.0,
    stop_buffer_pips: float = 2.0,
    max_risk_pips: float = 25.0,
) -> Optional[Dict[str, Any]]:
    """
    Connects to MT5, pulls recent candles, and evaluates institutional scalping strategies.
    Supported strategies: 'crt', 'unicorn', 'turtle_soup', 'po3', 'all'.
    """
    inst = db.query(Instrument).filter_by(symbol=symbol).first()
    if not inst:
        return None

    true_pip = _true_pip_size(inst.digits, float(inst.pip_size), symbol)
    strat_key = strategy.lower()

    if strat_key == "crt":
        return _scan_crt(inst, symbol, true_pip, ltf, risk_reward_ratio, stop_buffer_pips, max_risk_pips)
    elif strat_key == "unicorn":
        return _scan_unicorn(inst, symbol, true_pip, ltf, risk_reward_ratio, stop_buffer_pips, max_risk_pips)
    elif strat_key == "turtle_soup":
        return _scan_turtle_soup(inst, symbol, true_pip, ltf, risk_reward_ratio, stop_buffer_pips, max_risk_pips)
    elif strat_key == "po3":
        return _scan_po3(inst, symbol, true_pip, ltf, risk_reward_ratio, stop_buffer_pips, max_risk_pips)
    elif strat_key == "all":
        # Scan in order of priority: Unicorn -> Turtle Soup -> CRT -> PO3
        for scanner in (_scan_unicorn, _scan_turtle_soup, _scan_crt, _scan_po3):
            setup = scanner(inst, symbol, true_pip, ltf, risk_reward_ratio, stop_buffer_pips, max_risk_pips)
            if setup is not None:
                return setup
        return None

    raise ValueError(f"Unknown strategy: {strategy}. Must be one of {SUPPORTED_STRATEGIES}")


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
    strat = scalp.get("strategy", "SCALP")

    if dry_run:
        print_f(f"[Scalper - DRY RUN] -> Would execute [{strat}] {direction} {lot_size} lots on {symbol} @ {price} | SL: {sl} ({scalp['risk_pips']} pips) | TP: {tp} ({scalp['reward_pips']} pips) | {scalp.get('details', '')}")
        return None

    tick = mt5_client.get_symbol_tick(symbol)
    if not tick:
        print_f(f"[Scalper] Could not get tick for {symbol}")
        return None

    exec_price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    comment_text = f"SMTE_{strat}_{scalp['ltf']}"[:31]

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
        "comment": comment_text,
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
        print_f(f"[Scalper] EXECUTED [{strat}] {direction} {lot_size} lots {symbol} @ {res.price} (Ticket #{res.order}) | Risk: {scalp['risk_pips']} pips")
        return res.order
    except Exception as e:
        print_f(f"[Scalper] Execution failed on {symbol}: {e}")
        return None


def run_scalp_cycle(
    db,
    symbols: List[str],
    ltf: str,
    strategy: str = "crt",
    dry_run: bool = True,
    killzones_only: bool = False,
    fixed_lots: Optional[float] = 0.01,
    max_lots: float = 0.10,
):
    mt5_client.connect()
    try:
        now_utc = datetime.now(timezone.utc)
        if killzones_only:
            active_kz = active_session_windows(now_utc, profile="silver_bullet") or active_session_windows(now_utc, profile="forex_handbook")
            if not active_kz:
                print_f(f"\n[{now_utc.strftime('%H:%M:%S UTC')}] Outside active institutional killzones (Silver Bullet / London / NY Open). Skipping scan.")
                return

        print_f(f"\n[{now_utc.strftime('%H:%M:%S UTC')}] Scanning {len(symbols)} pairs ({', '.join(symbols)}) for {ltf} scalps [Strategy: {strategy.upper()}]...")
        found_any = False

        for symbol in symbols:
            try:
                # Fast check: skip closed weekend/holiday markets to avoid spamming failed requests
                if not is_market_session_active(symbol):
                    continue

                scalp = scan_symbol_for_scalp(db, symbol, ltf=ltf, strategy=strategy)
                if scalp:
                    found_any = True
                    strat = scalp.get("strategy", "SCALP")
                    print_f(f"[MATCH - {strat}] {symbol} {scalp['direction']} | Entry: {scalp['entry_price']} | SL: {scalp['stop_loss']} ({scalp['risk_pips']} pips) | TP: {scalp['take_profit']} | {scalp.get('details', '')}")
                    execute_scalp(db, scalp, dry_run=dry_run, fixed_lots=fixed_lots, max_lots=max_lots)
            except Exception as e:
                print_f(f"[{symbol}] Error scanning: {e}")

        if not found_any:
            print_f(f"         No active {strategy.upper()} setups detected across scanned pairs at this moment.")

        if not dry_run:
            stats = sync_and_manage_open_trades(db, breakeven_trigger_r=1.0)
            if stats["managed"] > 0:
                print_f(f"[Trade Manager] Open trades: {stats['managed']} | Closed: {stats['closed']} | Breakeven Set: {stats['breakeven_set']}")
    finally:
        mt5_client.disconnect()


def main():
    parser = argparse.ArgumentParser(description="SMTE Intraday Scalper Engine.")
    parser.add_argument("--scan", action="store_true", help="Perform a scan for current scalping opportunities")
    parser.add_argument("--execute", action="store_true", help="Execute real market orders on MT5 (live demo)")
    parser.add_argument("--dry-run", action="store_true", help="Scan and simulate entries without placing orders or managing open trades")
    parser.add_argument("--strategy", choices=SUPPORTED_STRATEGIES, default="crt", help="Trading strategy model to scan and execute (default: crt)")
    parser.add_argument("--killzones-only", action="store_true", help="Only take scalps during active institutional killzones (London, NY Open, Silver Bullet)")
    parser.add_argument("--sync-trades", action="store_true", help="Sync active trades and manage Breakeven")
    parser.add_argument("--monitor", action="store_true", help="Run continuously in background monitor mode")
    parser.add_argument("--interval", type=int, default=60, help="Interval in seconds between scan cycles (default 60)")
    parser.add_argument("--timeframe", default="M5", choices=["M1", "M3", "M5", "M15"], help="Execution timeframe (default M5)")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SCALP_SYMBOLS, help="Symbols to scan")
    parser.add_argument("--fixed-lots", type=float, default=0.01, help="Fixed uniform lot size for all pairs (default 0.01 micro-lots for beginner safety, set 0 for dynamic % risk)")
    parser.add_argument("--max-lots", type=float, default=0.10, help="Maximum allowed lot size cap when using dynamic risk (default 0.10)")
    args = parser.parse_args()

    is_dry_run = args.dry_run or not args.execute

    db = SessionLocal()
    try:
        if args.sync_trades:
            if args.dry_run:
                print_f("[Order Executor] Dry run: skipped trade synchronization and management.")
                return
            stats = sync_and_manage_open_trades(db)
            print_f(f"[Order Executor] Active trades sync: {stats}")
            return

        if args.monitor:
            print_f(f"[SMTE Scalper] Starting continuous monitoring on {args.timeframe} across {args.symbols} (strategy={args.strategy.upper()}, dry_run={is_dry_run})...")
            while True:
                try:
                    run_scalp_cycle(
                        db,
                        symbols=args.symbols,
                        ltf=args.timeframe,
                        strategy=args.strategy,
                        dry_run=is_dry_run,
                        killzones_only=args.killzones_only,
                        fixed_lots=args.fixed_lots,
                        max_lots=args.max_lots,
                    )
                except KeyboardInterrupt:
                    print_f("\n[SMTE Scalper] Continuous monitoring stopped by user.")
                    break
                except Exception as loop_err:
                    print_f(f"[SMTE Scalper] Cycle error: {loop_err}. Retrying in {args.interval}s...")
                time.sleep(args.interval)
        else:
            run_scalp_cycle(
                db,
                symbols=args.symbols,
                ltf=args.timeframe,
                strategy=args.strategy,
                dry_run=is_dry_run,
                killzones_only=args.killzones_only,
                fixed_lots=args.fixed_lots,
                max_lots=args.max_lots,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
