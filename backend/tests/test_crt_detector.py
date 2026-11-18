import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import Candle, CrtSetup, Instrument
from core.crt.detector import detect_crt_setups
from core.crt.detector import detect_crt_setups_mtf


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeQuery:
    def __init__(self, db):
        self.db = db
        self.filters = {}

    def filter_by(self, **_):
        self.filters = _
        return self

    def first(self):
        return next(
            (
                setup for setup in self.db.setups
                if all(getattr(setup, key) == value for key, value in self.filters.items())
            ),
            None,
        )


class FakeDB:
    def __init__(self, candles):
        self.candles = candles
        self.setups = []

    def execute(self, _):
        return FakeResult(list(reversed(self.candles)))

    def query(self, _):
        return FakeQuery(self)

    def add(self, setup):
        self.setups.append(setup)

    def commit(self):
        pass


def make_candle(candle_id, high, low, close):
    return SimpleNamespace(
        id=candle_id,
        high=high,
        low=low,
        close=close,
        open_time=datetime(2025, 1, 1, 10, candle_id, tzinfo=timezone.utc),
    )


class SingleTimeframeCrtTests(unittest.TestCase):
    def detect_phase(self, candles):
        db = FakeDB(candles)

        created = detect_crt_setups(db, instrument_id=1, timeframe="M15")

        self.assertEqual(created, 1)
        self.assertEqual(len(db.setups), 1)
        return db.setups[0].phase

    def test_bullish_distribution_requires_close_beyond_opposite_range_edge(self):
        candles = [
            make_candle(1, high=10.0, low=0.0, close=5.0),
            make_candle(2, high=9.0, low=-1.0, close=1.0),
            make_candle(3, high=8.5, low=0.5, close=5.0),
        ]

        self.assertEqual(self.detect_phase(candles), "MANIPULATION")

    def test_bullish_distribution_confirms_above_range_high(self):
        candles = [
            make_candle(1, high=10.0, low=0.0, close=5.0),
            make_candle(2, high=9.0, low=-1.0, close=1.0),
            make_candle(3, high=11.0, low=0.5, close=10.5),
        ]

        self.assertEqual(self.detect_phase(candles), "DISTRIBUTION")

    def test_bearish_distribution_requires_close_beyond_opposite_range_edge(self):
        candles = [
            make_candle(1, high=10.0, low=0.0, close=5.0),
            make_candle(2, high=11.0, low=1.0, close=9.0),
            make_candle(3, high=9.5, low=0.5, close=5.0),
        ]

        self.assertEqual(self.detect_phase(candles), "MANIPULATION")

    def test_bearish_distribution_confirms_below_range_low(self):
        candles = [
            make_candle(1, high=10.0, low=0.0, close=5.0),
            make_candle(2, high=11.0, low=1.0, close=9.0),
            make_candle(3, high=9.5, low=-1.0, close=-0.5),
        ]

        self.assertEqual(self.detect_phase(candles), "DISTRIBUTION")

    def test_pending_setup_promotes_when_a_later_candle_confirms_distribution(self):
        candles = [
            make_candle(1, high=10.0, low=0.0, close=5.0),
            make_candle(2, high=9.0, low=-1.0, close=1.0),
            make_candle(3, high=8.5, low=0.5, close=5.0),
        ]
        db = FakeDB(candles)

        created = detect_crt_setups(db, instrument_id=1, timeframe="M15")

        self.assertEqual(created, 1)
        self.assertEqual(db.setups[0].phase, "MANIPULATION")

        db.candles.append(make_candle(4, high=11.0, low=0.5, close=10.5))
        created = detect_crt_setups(db, instrument_id=1, timeframe="M15")

        self.assertEqual(created, 0)
        self.assertEqual(len(db.setups), 1)
        self.assertEqual(db.setups[0].phase, "DISTRIBUTION")


class MultiTimeframeCrtTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.base_time = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        self.session.add(
            Instrument(
                id=1,
                symbol="EURUSD.test",
                digits=4,
                pip_size=0.0001,
                contract_size=100000,
            )
        )
        self.add_candle("H4", 0, high=10.0, low=0.0, close=5.0)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add_candle(self, timeframe, minutes_after_base, high, low, close):
        self.session.add(
            Candle(
                instrument_id=1,
                timeframe=timeframe,
                open_time=self.base_time + timedelta(minutes=minutes_after_base),
                open=(high + low) / 2,
                high=high,
                low=low,
                close=close,
                volume=100,
            )
        )
        self.session.commit()

    def test_pending_setup_promotes_when_later_ltf_candle_confirms(self):
        self.add_candle("M15", 15, high=9.0, low=-1.0, close=1.0)
        self.add_candle("M15", 30, high=8.5, low=0.5, close=5.0)
        self.add_candle("M15", 45, high=8.0, low=0.5, close=6.0)

        created = detect_crt_setups_mtf(self.session, instrument_id=1)

        self.assertEqual(created, 1)
        setup = self.session.query(CrtSetup).one()
        self.assertEqual(setup.phase, "MANIPULATION")

        self.add_candle("M15", 60, high=11.0, low=5.0, close=10.5)
        created = detect_crt_setups_mtf(self.session, instrument_id=1)

        self.assertEqual(created, 0)
        self.assertEqual(setup.phase, "DISTRIBUTION")

    def test_manipulation_opened_at_range_end_is_not_inside_range_window(self):
        self.add_candle("M15", 225, high=9.0, low=0.5, close=5.0)
        self.add_candle("M15", 240, high=9.0, low=-1.0, close=1.0)

        created = detect_crt_setups_mtf(self.session, instrument_id=1)

        self.assertEqual(created, 0)


if __name__ == "__main__":
    unittest.main()
