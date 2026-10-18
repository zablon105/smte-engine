"""
order_executor.py
Executes pending trade signals on MetaTrader 5 and manages active positions.

Beginner note on Trade Execution:
  1. Turning signals into live positions:
     When the pipeline identifies an A+ setup, `signal_generator.py` marks it as
     a PENDING TradeSignal. This module reads those pending signals, verifies that
     current risk limits (max daily risk, max open trades) are respected,
     calculates the lot size based on 1.0% account risk, and executes the market order.

  2. Trade Monitoring & Breakeven Protection:
     Once a trade is open, this module tracks its progress. When price reaches
     +1.0R in profit, it automatically adjusts the stop-loss on MT5 to the entry price
     (Breakeven). This guarantees that a winning trade will never turn into a loss.
"""

from datetime import datetime, timezone
import MetaTrader5 as mt5

from app.models.models import Instrument, Trade, TradeSignal
from app.services import mt5_client
from app.services.risk_manager import (
    calculate_lot_size,
    can_open_new_trade,
    get_or_create_risk_parameters,
)


DEFAULT_MAGIC_NUMBER = 888123


def execute_pending_signals(
    db,
    magic: int = DEFAULT_MAGIC_NUMBER,
    max_slippage_points: int = 20,
) -> int:
    """
    Scans for PENDING TradeSignals, verifies risk parameters, and executes
    market orders directly on the MT5 broker terminal.

    Returns the number of successfully executed trades.
    """
    mt5_client.connect()
    try:
        account_info = mt5_client.get_account_info()
        account_equity = float(account_info.equity)

        pending_signals = (
            db.query(TradeSignal)
            .filter_by(status="PENDING")
            .order_by(TradeSignal.generated_at.asc())
            .all()
        )

        if not pending_signals:
            return 0

        executed_count = 0
        risk_params = get_or_create_risk_parameters(db)

        for signal in pending_signals:
            allowed, reason = can_open_new_trade(db)
            if not allowed:
                print(f"[Execution Engine] Trade skipped: {reason}")
                break

            instrument = db.query(Instrument).filter_by(id=signal.instrument_id).first()
            if instrument is None:
                continue

            symbol = instrument.symbol
            tick = mt5_client.get_symbol_tick(symbol)
            if tick is None:
                continue

            # Calculate dynamic lot size based on account equity and stop loss
            lot_size = calculate_lot_size(
                account_equity=account_equity,
                risk_pct=float(risk_params.max_risk_per_trade_pct),
                entry_price=float(signal.entry_price),
                stop_loss=float(signal.stop_loss),
                contract_size=float(instrument.contract_size or 100000.0),
            )

            order_type = mt5.ORDER_TYPE_BUY if signal.signal_direction == "BUY" else mt5.ORDER_TYPE_SELL
            current_price = tick.ask if signal.signal_direction == "BUY" else tick.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": order_type,
                "price": current_price,
                "sl": float(signal.stop_loss),
                "tp": float(signal.take_profit),
                "deviation": max_slippage_points,
                "magic": magic,
                "comment": f"SMTE_SIG_{signal.id}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            try:
                result = mt5_client.send_order(request)
                signal.status = "EXECUTED"

                trade = Trade(
                    trade_signal_id=signal.id,
                    instrument_id=instrument.id,
                    mt5_ticket=result.order,
                    direction=signal.signal_direction,
                    lot_size=lot_size,
                    entry_price=result.price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    opened_at=datetime.now(timezone.utc),
                    status="OPEN",
                )
                db.add(trade)
                executed_count += 1
                print(f"[Execution Engine] EXECUTED {signal.signal_direction} {lot_size} lots on {symbol} @ {result.price} (Ticket #{result.order})")
            except Exception as e:
                print(f"[Execution Engine] Failed to execute signal #{signal.id} on {symbol}: {e}")

        db.commit()
        return executed_count
    finally:
        mt5_client.disconnect()


def sync_and_manage_open_trades(
    db,
    breakeven_trigger_r: float = 1.0,
) -> dict:
    """
    Monitors all active trades:
      1. Moves stop-loss to Breakeven (+1R trigger) to secure risk-free status.
      2. Detects closed trades in MT5 and updates profit, exit_price, and status.
    """
    mt5_client.connect()
    try:
        open_trades = db.query(Trade).filter_by(status="OPEN").all()
        if not open_trades:
            return {"managed": 0, "closed": 0, "breakeven_set": 0}

        closed_count = 0
        be_count = 0

        for trade in open_trades:
            instrument = db.query(Instrument).filter_by(id=trade.instrument_id).first()
            if not instrument:
                continue

            # Check if position is currently active on MT5
            positions = mt5_client.get_positions()
            active_pos = next((p for p in positions if p.ticket == trade.mt5_ticket), None) if positions else None

            if active_pos:
                # 1. Breakeven Management
                entry = float(trade.entry_price)
                initial_stop = float(trade.stop_loss)
                current_price = float(active_pos.price_current)
                risk_distance = abs(entry - initial_stop)

                # Check if trade reached +1R and has not yet moved SL to entry
                if trade.direction == "BUY":
                    favorable_move = current_price - entry
                    already_at_be = float(trade.stop_loss) >= entry
                    if favorable_move >= (risk_distance * breakeven_trigger_r) and not already_at_be:
                        try:
                            mt5_client.modify_position(trade.mt5_ticket, sl=entry, tp=float(trade.take_profit))
                            trade.stop_loss = entry
                            be_count += 1
                            print(f"[Trade Manager] Moved Ticket #{trade.mt5_ticket} to BREAKEVEN @ {entry}")
                        except Exception as e:
                            print(f"[Trade Manager] Could not move to BE: {e}")
                else:
                    favorable_move = entry - current_price
                    already_at_be = float(trade.stop_loss) <= entry
                    if favorable_move >= (risk_distance * breakeven_trigger_r) and not already_at_be:
                        try:
                            mt5_client.modify_position(trade.mt5_ticket, sl=entry, tp=float(trade.take_profit))
                            trade.stop_loss = entry
                            be_count += 1
                            print(f"[Trade Manager] Moved Ticket #{trade.mt5_ticket} to BREAKEVEN @ {entry}")
                        except Exception as e:
                            print(f"[Trade Manager] Could not move to BE: {e}")
            else:
                # 2. Position has closed in MT5 - pull final deal P&L
                deals = mt5_client.get_position_deals(trade.mt5_ticket)
                if deals:
                    # Closing deal is typically the last deal
                    closing_deal = deals[-1]
                    trade.status = "CLOSED"
                    trade.exit_price = float(closing_deal.price)
                    trade.profit = float(sum(d.profit + d.swap + d.commission for d in deals))
                    trade.closed_at = datetime.fromtimestamp(int(closing_deal.time), tz=timezone.utc)
                    closed_count += 1
                    print(f"[Trade Manager] Closed Ticket #{trade.mt5_ticket}: P&L = ${trade.profit:.2f}")
                else:
                    trade.status = "CLOSED"
                    trade.closed_at = datetime.now(timezone.utc)
                    closed_count += 1

        db.commit()
        return {"managed": len(open_trades), "closed": closed_count, "breakeven_set": be_count}
    finally:
        mt5_client.disconnect()
