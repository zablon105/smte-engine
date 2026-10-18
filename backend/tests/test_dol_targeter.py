import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, DolTarget, Instrument, LiquidityZone
from core.dol.targeter import find_active_dol, identify_dol_targets, update_dol_targets


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class DolTargeterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.instrument = Instrument(
            id=1,
            symbol="EURUSD.m",
            digits=5,
            pip_size=0.00001,
            contract_size=100000,
        )
        self.session.add(self.instrument)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_identify_and_update_dol_targets(self):
        base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        # Create two liquidity zones: one equal highs at 1.1100 (BUY_SIDE DOL), one equal lows at 1.0900
        lz_high = LiquidityZone(
            id=101,
            instrument_id=1,
            timeframe="H1",
            zone_type="SELL_SIDE",  # equal highs
            price_level=1.1100,
            formed_at=base_time,
            is_swept=False,
            strength_score=3,
        )
        lz_low = LiquidityZone(
            id=102,
            instrument_id=1,
            timeframe="H1",
            zone_type="BUY_SIDE",  # equal lows
            price_level=1.0900,
            formed_at=base_time,
            is_swept=False,
            strength_score=2,
        )
        self.session.add_all([lz_high, lz_low])
        self.session.commit()

        # Step 1: Identify DOL targets
        identified = identify_dol_targets(self.session, instrument_id=1, timeframe="H1")
        self.assertEqual(identified, 2)

        # Step 2: find_active_dol for BUY at current price 1.1000 -> should find 1.1100
        target = find_active_dol(self.session, instrument_id=1, signal_direction="BUY", current_price=1.1000)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target, 1.1100)

        # find_active_dol for SELL at current price 1.1000 -> should find 1.0900
        target_sell = find_active_dol(self.session, instrument_id=1, signal_direction="SELL", current_price=1.1000)
        self.assertIsNotNone(target_sell)
        self.assertAlmostEqual(target_sell, 1.0900)

        # Step 3: Candle trades through 1.1100 -> update_dol_targets marks it reached
        reach_candle = Candle(
            instrument_id=1,
            timeframe="M15",
            open_time=base_time + timedelta(hours=2),
            open=1.1050,
            high=1.1120,
            low=1.1040,
            close=1.1110,
            volume=500,
        )
        self.session.add(reach_candle)
        self.session.commit()

        updated = update_dol_targets(self.session, instrument_id=1, timeframe="M15")
        self.assertEqual(updated, 1)

        # High target is now reached/inactive
        dol_rec = self.session.query(DolTarget).filter_by(target_price=1.1100).first()
        self.assertFalse(dol_rec.is_active)
        self.assertIsNotNone(dol_rec.reached_at)
