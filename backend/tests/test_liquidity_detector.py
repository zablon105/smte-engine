import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, Instrument, LiquidityZone
from core.liquidity.detector import detect_liquidity_zones, mark_swept_zones
from core.scoring.confluence import _matching_zone_type


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class LiquidityDetectorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.session.add(
            Instrument(
                id=1,
                symbol="EURUSD.test",
                digits=4,
                pip_size=0.0001,
                contract_size=100000,
            )
        )
        self.session.commit()
        self.base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_candle(self, index, high, low, close=None):
        self.session.add(
            Candle(
                instrument_id=1,
                timeframe="M15",
                open_time=self.base_time + timedelta(minutes=15 * index),
                open=(high + low) / 2,
                high=high,
                low=low,
                close=close if close is not None else (high + low) / 2,
                volume=100,
            )
        )

    def test_equal_highs_are_buy_side_and_equal_lows_are_sell_side(self):
        highs = [
            1.1080, 1.1090, 1.1100, 1.1085, 1.1090,
            1.1080, 1.1102, 1.1090, 1.1110,
        ]
        lows = [
            1.1020, 1.1010, 1.1000, 1.0990, 1.0980,
            1.0970, 1.0960, 1.0950, 1.0940,
        ]
        for index, (high, low) in enumerate(zip(highs, lows)):
            self.add_candle(index, high, low)
        self.session.commit()

        created = detect_liquidity_zones(
            self.session,
            instrument_id=1,
            timeframe="M15",
            lookback=20,
            equal_tolerance_pips=3,
            digits=4,
            point=0.0001,
        )

        zones = self.session.query(LiquidityZone).all()
        self.assertEqual(created, 1)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].zone_type, "BUY_SIDE")
        self.assertAlmostEqual(float(zones[0].price_level), 1.1102)

    def test_sweep_direction_matches_buy_side_highs_and_sell_side_lows(self):
        high_zone = LiquidityZone(
            instrument_id=1,
            timeframe="M15",
            zone_type="BUY_SIDE",
            price_level=1.1100,
            formed_at=self.base_time,
            is_swept=False,
            strength_score=2,
        )
        low_zone = LiquidityZone(
            instrument_id=1,
            timeframe="M15",
            zone_type="SELL_SIDE",
            price_level=1.0900,
            formed_at=self.base_time,
            is_swept=False,
            strength_score=2,
        )
        self.session.add_all([high_zone, low_zone])
        self.add_candle(1, high=1.1110, low=1.0950)
        self.add_candle(2, high=1.1050, low=1.0890)
        self.session.commit()

        swept = mark_swept_zones(self.session, instrument_id=1, timeframe="M15")

        self.assertEqual(swept, 2)
        self.assertTrue(high_zone.is_swept)
        self.assertEqual(high_zone.swept_at, (self.base_time + timedelta(minutes=15)).replace(tzinfo=None))
        self.assertTrue(low_zone.is_swept)
        self.assertEqual(low_zone.swept_at, (self.base_time + timedelta(minutes=30)).replace(tzinfo=None))

    def test_bullish_and_bearish_crt_match_the_swept_liquidity_side(self):
        self.assertEqual(_matching_zone_type("BULLISH"), "SELL_SIDE")
        self.assertEqual(_matching_zone_type("BEARISH"), "BUY_SIDE")


if __name__ == "__main__":
    unittest.main()
