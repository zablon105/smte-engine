import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.models import CrtSetup, FairValueGap, Instrument, SetupScore
from core.scoring.confluence import score_crt_setups_v3


@compiles(BigInteger, "sqlite")
def _compile_big_integer_for_sqlite(_type, _compiler, **_kwargs):
    return "INTEGER"


class ScoreCrtSetupsV3Tests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        instrument = Instrument(
            id=1,
            symbol="EURUSD.test",
            digits=4,
            pip_size=0.0001,
            contract_size=100000,
        )
        self.session.add(instrument)

        base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        setups = [
            CrtSetup(
                id=1,
                instrument_id=1,
                timeframe="M15",
                setup_direction="BULLISH",
                phase="DISTRIBUTION",
                range_high=1.11,
                range_low=1.09,
                manipulation_price=1.1,
                detected_at=base_time,
                is_valid=True,
            ),
            CrtSetup(
                id=2,
                instrument_id=1,
                timeframe="M15",
                setup_direction="BULLISH",
                phase="DISTRIBUTION",
                range_high=1.11,
                range_low=1.09,
                manipulation_price=1.1,
                detected_at=base_time + timedelta(hours=2),
                is_valid=True,
            ),
        ]
        self.session.add_all(setups)
        self.session.flush()
        self.session.add_all(
            [
                FairValueGap(
                    instrument_id=1,
                    timeframe="M15",
                    gap_type="BULLISH",
                    bottom_price=1.0995,
                    top_price=1.1005,
                    formed_at=base_time - timedelta(minutes=30),
                    filled_at=base_time + timedelta(hours=1),
                    fill_percentage=100,
                ),
                FairValueGap(
                    instrument_id=1,
                    timeframe="H1",
                    gap_type="BULLISH",
                    bottom_price=1.0995,
                    top_price=1.1005,
                    formed_at=base_time + timedelta(hours=1),
                    filled_at=base_time + timedelta(hours=1, minutes=30),
                    fill_percentage=100,
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_scores_only_fvgs_not_filled_before_each_setup(self):
        processed = score_crt_setups_v3(
            self.session,
            instrument_id=1,
            digits=4,
            point=0.0001,
        )

        self.assertEqual(processed, 2)
        scores = {
            score.crt_setup_id: score
            for score in self.session.query(SetupScore).all()
        }
        self.assertEqual(scores[1].fvg_score, 5)
        self.assertEqual(scores[1].total_score, 8)
        self.assertEqual(scores[2].fvg_score, 0)
        self.assertEqual(scores[2].total_score, 3)


if __name__ == "__main__":
    unittest.main()
