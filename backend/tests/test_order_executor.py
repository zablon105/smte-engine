import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Instrument, RiskParameter, Trade, TradeSignal
from core.execution.order_executor import (
    execute_pending_signals,
    sync_and_manage_open_trades,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class OrderExecutorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Seed instrument
        self.inst = Instrument(
            symbol="EURUSD.m",
            description="EUR/USD Mini",
            digits=5,
            pip_size=0.0001,
            contract_size=100000,
            is_active=True,
        )
        self.db.add(self.inst)

        # Seed risk parameter
        self.risk = RiskParameter(
            strategy_name="CRT_CONFLUENCE",
            max_daily_risk_pct=3.0,
            max_risk_per_trade_pct=1.0,
            max_open_trades=3,
        )
        self.db.add(self.risk)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    @patch("core.execution.order_executor.mt5_client")
    def test_execute_pending_signals_dry_run(self, mock_mt5):
        mock_acc = MagicMock()
        mock_acc.equity = 10000.0
        mock_mt5.get_account_info.return_value = mock_acc

        mock_tick = MagicMock()
        mock_tick.ask = 1.1000
        mock_tick.bid = 1.0998
        mock_mt5.get_symbol_tick.return_value = mock_tick

        # Add pending signal
        signal = TradeSignal(
            instrument_id=self.inst.id,
            signal_direction="BUY",
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            status="PENDING",
            generated_at=datetime.now(timezone.utc),
        )
        self.db.add(signal)
        self.db.commit()

        executed = execute_pending_signals(self.db, dry_run=True, max_age_minutes=60)
        self.assertEqual(executed, 1)

    @patch("core.execution.order_executor.mt5_client")
    def test_stale_signal_is_marked_expired(self, mock_mt5):
        mock_acc = MagicMock()
        mock_acc.equity = 10000.0
        mock_mt5.get_account_info.return_value = mock_acc

        # Signal generated 2 hours ago
        signal = TradeSignal(
            instrument_id=self.inst.id,
            signal_direction="BUY",
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            status="PENDING",
            generated_at=datetime.now(timezone.utc) - timedelta(minutes=120),
        )
        self.db.add(signal)
        self.db.commit()

        executed = execute_pending_signals(self.db, dry_run=False, max_age_minutes=60)
        self.assertEqual(executed, 0)
        self.assertEqual(signal.status, "EXPIRED")

    @patch("core.execution.order_executor.mt5_client")
    def test_sync_moves_sl_to_breakeven_at_1r(self, mock_mt5):
        # Trade: Entry 1.1000, SL 1.0980 (risk = 0.0020). Target = 1.1040 (2R).
        trade = Trade(
            instrument_id=self.inst.id,
            mt5_ticket=99901,
            direction="BUY",
            lot_size=0.50,
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            opened_at=datetime.now(timezone.utc),
            status="OPEN",
        )
        self.db.add(trade)
        self.db.commit()

        # Mock MT5 active position showing current price reached 1.1025 (+1.25R > +1.0R)
        mock_pos = MagicMock()
        mock_pos.ticket = 99901
        mock_pos.price_current = 1.1025
        mock_mt5.get_positions.return_value = [mock_pos]

        stats = sync_and_manage_open_trades(self.db, breakeven_trigger_r=1.0)
        self.assertEqual(stats["managed"], 1)
        self.assertEqual(stats["breakeven_set"], 1)
        # Verify SL was updated to entry price
        self.assertAlmostEqual(float(trade.stop_loss), 1.1000)
        mock_mt5.modify_position.assert_called_once_with(99901, sl=1.1000, tp=1.1040)

    @patch("core.execution.order_executor.mt5_client")
    def test_sync_detects_closed_position_and_records_profit(self, mock_mt5):
        trade = Trade(
            instrument_id=self.inst.id,
            mt5_ticket=99902,
            direction="BUY",
            lot_size=0.50,
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1040,
            opened_at=datetime.now(timezone.utc),
            status="OPEN",
        )
        self.db.add(trade)
        self.db.commit()

        # No active positions on MT5 (trade has closed)
        mock_mt5.get_positions.return_value = []

        # Mock closing deal from history
        mock_deal = MagicMock()
        mock_deal.price = 1.1040
        mock_deal.profit = 200.0
        mock_deal.swap = 0.0
        mock_deal.commission = -2.0
        mock_deal.time = int(datetime.now(timezone.utc).timestamp())
        mock_mt5.get_position_deals.return_value = [mock_deal]

        stats = sync_and_manage_open_trades(self.db)
        self.assertEqual(stats["closed"], 1)
        self.assertEqual(trade.status, "CLOSED")
        self.assertAlmostEqual(float(trade.profit), 198.0)
        self.assertAlmostEqual(float(trade.exit_price), 1.1040)


if __name__ == "__main__":
    unittest.main()
