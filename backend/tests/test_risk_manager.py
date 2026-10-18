import unittest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import RiskParameter, Trade
from app.services.risk_manager import (
    calculate_lot_size,
    can_open_new_trade,
    get_or_create_risk_parameters,
)


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class RiskManagerTests(unittest.TestCase):
    def test_calculate_lot_size_exact_cash_risk(self):
        # Account = $10,000, 1% risk = $100 risk.
        # EURUSD: Entry = 1.1000, Stop = 1.0980 (20 pips distance = 0.0020).
        # Contract size = 100,000.
        # Loss per 1.00 lot = 0.0020 * 100,000 = $200.
        # Expected lot size = $100 / $200 = 0.50 lots.
        lots = calculate_lot_size(
            account_equity=10000.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss=1.0980,
            contract_size=100000.0,
        )
        self.assertAlmostEqual(lots, 0.50)

    def test_calculate_lot_size_clamps_to_min_and_max(self):
        # Huge stop distance or tiny account clamps to min_lot
        lots_min = calculate_lot_size(
            account_equity=50.0,
            risk_pct=1.0,
            entry_price=1.1000,
            stop_loss=1.0000,
            min_lot=0.01,
        )
        self.assertEqual(lots_min, 0.01)

        # Huge account with tight stop clamps to max_lot
        lots_max = calculate_lot_size(
            account_equity=10000000.0,
            risk_pct=2.0,
            entry_price=1.1000,
            stop_loss=1.0999,
            max_lot=50.0,
        )
        self.assertEqual(lots_max, 50.0)

    def test_can_open_new_trade_checks_open_count(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()

        # Initialize parameters with max_open_trades = 2
        params = get_or_create_risk_parameters(session, max_open_trades=2)
        self.assertEqual(params.max_open_trades, 2)

        # 0 open trades -> Approved
        allowed, msg = can_open_new_trade(session)
        self.assertTrue(allowed)

        from datetime import datetime, timezone

        # Add 2 open trades
        session.add_all([
            Trade(
                id=1,
                instrument_id=1,
                mt5_ticket=101,
                direction="BUY",
                lot_size=0.10,
                entry_price=1.1000,
                status="OPEN",
                opened_at=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            Trade(
                id=2,
                instrument_id=1,
                mt5_ticket=102,
                direction="SELL",
                lot_size=0.10,
                entry_price=1.1000,
                status="OPEN",
                opened_at=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
            ),
        ])
        session.commit()

        # Now 2 open trades -> Should be rejected
        allowed_full, msg_full = can_open_new_trade(session)
        self.assertFalse(allowed_full)
        self.assertIn("Maximum open trades limit reached", msg_full)
        session.close()
