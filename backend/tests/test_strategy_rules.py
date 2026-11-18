import unittest
from datetime import datetime, timezone

from core.strategy_rules import (
    BoundaryInteraction,
    BreakerZone,
    CRTTargets,
    JudasSwingAssessment,
    MMXMLocationAssessment,
    OTEZone,
    PO3PricingAssessment,
    SessionWindow,
    TimeframeProfile,
    TurtleSoupEvaluation,
    TurtleSoupTargets,
    UnicornOverlap,
    UnicornValidation,
    active_session_windows,
    calculate_breaker_zone,
    calculate_crt_targets,
    calculate_dealing_range_equilibrium,
    calculate_ote_zone,
    calculate_turtle_soup_targets,
    calculate_unicorn_overlap,
    classify_liquidity_type,
    detect_judas_swing,
    evaluate_mmxm_location,
    evaluate_po3_pricing,
    evaluate_prior_boundary_interaction,
    evaluate_turtle_soup_sequence,
    get_aligned_entry_timeframes,
    get_timeframe_profile,
    is_breaker_mitigated,
    is_valid_timeframe_pairing,
    next_expected_liquidity_draw,
    validate_breaker_break,
    validate_unicorn_setup,
)


class CrtTargetTests(unittest.TestCase):
    def test_targets_midpoint_then_opposing_edge_for_bullish_crt(self):
        targets = calculate_crt_targets(100.0, 120.0, "BULLISH")

        self.assertEqual(targets.first, 110.0)
        self.assertEqual(targets.second, 120.0)

    def test_targets_midpoint_then_opposing_edge_for_bearish_crt(self):
        targets = calculate_crt_targets(100.0, 120.0, "BEARISH")

        self.assertEqual(targets.first, 110.0)
        self.assertEqual(targets.second, 100.0)

    def test_rejects_invalid_crt_range_or_direction(self):
        with self.assertRaisesRegex(ValueError, "range_low must be less"):
            calculate_crt_targets(100.0, 100.0, "BULLISH")
        with self.assertRaisesRegex(ValueError, "direction must be"):
            calculate_crt_targets(100.0, 120.0, "LONG")


class OteZoneTests(unittest.TestCase):
    def test_calculates_bullish_ote_band_from_explicit_anchors(self):
        zone = calculate_ote_zone(100.0, 120.0, "BULLISH")

        self.assertAlmostEqual(zone.low, 104.2)
        self.assertAlmostEqual(zone.high, 107.6)
        self.assertAlmostEqual(zone.sweet_spot, 105.9)
        self.assertEqual(zone, OTEZone(104.2, 107.6, 105.9))

    def test_calculates_bearish_ote_band_from_explicit_anchors(self):
        zone = calculate_ote_zone(100.0, 120.0, "BEARISH")

        self.assertAlmostEqual(zone.low, 112.4)
        self.assertAlmostEqual(zone.high, 115.8)
        self.assertAlmostEqual(zone.sweet_spot, 114.1)

    def test_rejects_invalid_swing_range(self):
        with self.assertRaisesRegex(ValueError, "swing_low must be less"):
            calculate_ote_zone(120.0, 100.0, "BULLISH")
        with self.assertRaisesRegex(ValueError, "swing_low must be less"):
            calculate_ote_zone(100.0, 100.0, "BEARISH")

    def test_rejects_non_finite_prices_and_unsupported_direction(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_ote_zone(float("nan"), 120.0, "BULLISH")
        with self.assertRaisesRegex(ValueError, "finite"):
            calculate_ote_zone(100.0, float("inf"), "BEARISH")
        with self.assertRaisesRegex(ValueError, "direction must be"):
            calculate_ote_zone(100.0, 120.0, "LONG")


class SessionWindowTests(unittest.TestCase):
    def test_profiles_preserve_conflicting_asian_windows(self):
        utc_time = datetime(2026, 1, 15, 1, 30, tzinfo=timezone.utc)

        self.assertIn("ASIA", active_session_windows(utc_time, "forex_handbook"))
        self.assertNotIn("ASIA", active_session_windows(utc_time, "forex_mansoori"))

    def test_new_york_local_windows_follow_daylight_saving(self):
        winter_open = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
        summer_open = datetime(2026, 7, 15, 7, 0, tzinfo=timezone.utc)

        self.assertIn("LONDON", active_session_windows(winter_open, "silver_bullet"))
        self.assertIn("LONDON", active_session_windows(summer_open, "silver_bullet"))

    def test_rejects_naive_timestamps_and_unknown_profiles(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            active_session_windows(datetime(2026, 1, 15, 3), "silver_bullet")
        with self.assertRaisesRegex(ValueError, "Unknown session window profile"):
            active_session_windows(datetime.now(timezone.utc), "unknown")


class BreakerBlockTests(unittest.TestCase):
    def test_calculates_breaker_zone_body_and_mean_threshold(self):
        # Candle open=102, close=108, low=100, high=110 (body range = 6, total = 10)
        zone = calculate_breaker_zone(
            open_price=102.0,
            close_price=108.0,
            high_price=110.0,
            low_price=100.0,
            direction="BULLISH",
            use_body=True,
        )
        self.assertEqual(zone.bottom, 102.0)
        self.assertEqual(zone.top, 108.0)
        self.assertEqual(zone.mean_threshold, 105.0)
        self.assertTrue(zone.use_body)

    def test_falls_back_to_full_candle_when_body_ratio_small(self):
        # Doji-like candle with tiny body: open=105.0, close=105.1, low=100.0, high=110.0 (body=0.1, total=10)
        zone = calculate_breaker_zone(
            open_price=105.0,
            close_price=105.1,
            high_price=110.0,
            low_price=100.0,
            direction="BEARISH",
            use_body=True,
            min_body_ratio=0.20,
        )
        self.assertEqual(zone.bottom, 100.0)
        self.assertEqual(zone.top, 110.0)
        self.assertEqual(zone.mean_threshold, 105.0)
        self.assertFalse(zone.use_body)

    def test_breaker_mitigation_detection(self):
        zone = BreakerZone(bottom=102.0, top=108.0, direction="BULLISH", mean_threshold=105.0, use_body=True)
        # Price range overlaps breaker zone
        self.assertTrue(is_breaker_mitigated(zone, current_low=101.0, current_high=103.0))
        # Price completely above zone
        self.assertFalse(is_breaker_mitigated(zone, current_low=109.0, current_high=115.0))
        # Price completely below zone
        self.assertFalse(is_breaker_mitigated(zone, current_low=95.0, current_high=101.0))

    def test_validate_breaker_break(self):
        # Bullish break must close above swing high
        self.assertTrue(validate_breaker_break(swing_extreme=110.0, break_candle_close=110.5, direction="BULLISH"))
        self.assertFalse(validate_breaker_break(swing_extreme=110.0, break_candle_close=109.8, direction="BULLISH"))

        # Bearish break must close below swing low
        self.assertTrue(validate_breaker_break(swing_extreme=100.0, break_candle_close=99.2, direction="BEARISH"))
        self.assertFalse(validate_breaker_break(swing_extreme=100.0, break_candle_close=100.4, direction="BEARISH"))

    def test_breaker_validation_errors(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            calculate_breaker_zone(float("nan"), 105.0, 110.0, 100.0, "BULLISH")
        with self.assertRaisesRegex(ValueError, "low_price must be less"):
            calculate_breaker_zone(105.0, 106.0, 100.0, 110.0, "BULLISH")


class UnicornModelTests(unittest.TestCase):
    def test_calculate_unicorn_overlap_valid(self):
        # Breaker zone: [100.0, 110.0], FVG zone: [105.0, 115.0] -> Overlap: [105.0, 110.0]
        overlap = calculate_unicorn_overlap(
            breaker_bottom=100.0,
            breaker_top=110.0,
            fvg_bottom=105.0,
            fvg_top=115.0,
        )
        self.assertIsNotNone(overlap)
        self.assertEqual(overlap.bottom, 105.0)
        self.assertEqual(overlap.top, 110.0)
        self.assertEqual(overlap.midpoint, 107.5)
        self.assertEqual(overlap.span, 5.0)

    def test_calculate_unicorn_overlap_no_overlap(self):
        # Disjoint zones: Breaker [100.0, 104.0], FVG [106.0, 112.0]
        overlap = calculate_unicorn_overlap(
            breaker_bottom=100.0,
            breaker_top=104.0,
            fvg_bottom=106.0,
            fvg_top=112.0,
        )
        self.assertIsNone(overlap)

    def test_validate_unicorn_setup(self):
        overlap = UnicornOverlap(bottom=105.0, top=110.0, midpoint=107.5, span=5.0)

        # All 4 conditions met
        result = validate_unicorn_setup(
            has_trigger_sweep_or_smt=True,
            has_aligned_breaker=True,
            has_aligned_fvg=True,
            has_clear_dol=True,
            overlap=overlap,
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.missing_requirements), 0)

        # Missing DOL and overlap
        result_incomplete = validate_unicorn_setup(
            has_trigger_sweep_or_smt=True,
            has_aligned_breaker=True,
            has_aligned_fvg=True,
            has_clear_dol=False,
            overlap=None,
        )
        self.assertFalse(result_incomplete.is_valid)
        self.assertIn("clear_dol", result_incomplete.missing_requirements)
        self.assertIn("breaker_fvg_overlap", result_incomplete.missing_requirements)


class TurtleSoupTests(unittest.TestCase):
    def test_calculates_turtle_soup_targets(self):
        # Bullish: Range [100.0, 120.0], purge extreme at 98.0
        targets = calculate_turtle_soup_targets(
            range_low=100.0,
            range_high=120.0,
            manipulation_extreme=98.0,
            direction="BULLISH",
        )
        self.assertEqual(targets.midpoint_tp1, 110.0)
        self.assertEqual(targets.opposing_edge_tp2, 120.0)
        self.assertEqual(targets.invalidation_stop, 98.0)

    def test_bullish_turtle_body_soup_sequence(self):
        # Candle 1: High 120, Low 100
        # Candle 2 (TBS): Opens 101, purges to low 97, closes below low at 99
        # Candle 3: Opens 99, closes inside Candle 1 range at 105
        eval_result = evaluate_turtle_soup_sequence(
            c1_high=120.0,
            c1_low=100.0,
            c2_open=101.0,
            c2_close=99.0,
            c2_high=102.0,
            c2_low=97.0,
            c3_close=105.0,
            direction="BULLISH",
        )
        self.assertTrue(eval_result.is_valid)
        self.assertEqual(eval_result.soup_type, "TBS")
        self.assertEqual(eval_result.targets.midpoint_tp1, 110.0)
        self.assertEqual(eval_result.targets.opposing_edge_tp2, 120.0)
        self.assertEqual(eval_result.targets.invalidation_stop, 97.0)

    def test_bearish_turtle_wick_soup_sequence(self):
        # Candle 1: High 120, Low 100
        # Candle 2 (TWS): Purges high to 123, but closes back inside at 118
        # Candle 3: Closes lower inside range at 112
        eval_result = evaluate_turtle_soup_sequence(
            c1_high=120.0,
            c1_low=100.0,
            c2_open=117.0,
            c2_close=118.0,
            c2_high=123.0,
            c2_low=115.0,
            c3_close=112.0,
            direction="BEARISH",
        )
        self.assertTrue(eval_result.is_valid)
        self.assertEqual(eval_result.soup_type, "TWS")
        self.assertEqual(eval_result.targets.midpoint_tp1, 110.0)
        self.assertEqual(eval_result.targets.opposing_edge_tp2, 100.0)
        self.assertEqual(eval_result.targets.invalidation_stop, 123.0)

    def test_turtle_soup_fails_without_candle3_confirmation(self):
        # Candle 3 closes outside range (e.g. continues lower)
        eval_result = evaluate_turtle_soup_sequence(
            c1_high=120.0,
            c1_low=100.0,
            c2_open=101.0,
            c2_close=99.0,
            c2_high=102.0,
            c2_low=97.0,
            c3_close=96.0,  # Fails to re-enter
            direction="BULLISH",
        )
        self.assertFalse(eval_result.is_valid)
        self.assertEqual(eval_result.soup_type, "NONE")


class TimeframeAlignmentTests(unittest.TestCase):
    def test_retrieves_standard_profiles(self):
        swing = get_timeframe_profile("swing")
        self.assertEqual(swing.htf_context, "1D")
        self.assertIn("4H", swing.ltf_entries)
        self.assertIn("1H", swing.ltf_entries)

        intraday = get_timeframe_profile("intraday")
        self.assertEqual(intraday.htf_context, "1H")
        self.assertIn("15M", intraday.ltf_entries)
        self.assertIn("5M", intraday.ltf_entries)

    def test_validates_timeframe_pairings(self):
        self.assertTrue(is_valid_timeframe_pairing("1D", "4H", "swing"))
        self.assertTrue(is_valid_timeframe_pairing("1H", "15M", "intraday"))
        self.assertFalse(is_valid_timeframe_pairing("1H", "1D", "intraday"))

    def test_get_aligned_entry_timeframes(self):
        entries = get_aligned_entry_timeframes("4H", "short_term")
        self.assertEqual(entries, ("1H", "15M"))

    def test_rejects_unknown_profile(self):
        with self.assertRaisesRegex(ValueError, "Unknown timeframe profile"):
            get_timeframe_profile("non_existent")


class PowerOfThreeTests(unittest.TestCase):
    def test_evaluates_po3_pricing_bullish(self):
        open_price = 100.0

        # Bullish: buying below open (discount) is valid
        discount_eval = evaluate_po3_pricing(open_price, 98.0, "BULLISH")
        self.assertTrue(discount_eval.is_valid_entry_zone)
        self.assertEqual(discount_eval.zone_type, "DISCOUNT")
        self.assertEqual(discount_eval.price_delta, -2.0)

        # Bullish: buying above open (premium) is invalid
        premium_eval = evaluate_po3_pricing(open_price, 102.0, "BULLISH")
        self.assertFalse(premium_eval.is_valid_entry_zone)
        self.assertEqual(premium_eval.zone_type, "PREMIUM")

    def test_evaluates_po3_pricing_bearish(self):
        open_price = 100.0

        # Bearish: selling above open (premium) is valid
        premium_eval = evaluate_po3_pricing(open_price, 103.0, "BEARISH")
        self.assertTrue(premium_eval.is_valid_entry_zone)
        self.assertEqual(premium_eval.zone_type, "PREMIUM")

        # Bearish: selling below open (discount) is invalid
        discount_eval = evaluate_po3_pricing(open_price, 97.0, "BEARISH")
        self.assertFalse(discount_eval.is_valid_entry_zone)
        self.assertEqual(discount_eval.zone_type, "DISCOUNT")

    def test_detect_judas_swing(self):
        open_price = 100.0

        # Bullish judas swing dips below open by at least 1.5
        judas = detect_judas_swing(open_price, period_extreme=98.0, bias="BULLISH", min_purge_distance=1.5)
        self.assertTrue(judas.has_judas_swing)
        self.assertEqual(judas.purge_distance, 2.0)

        # Fails if distance is smaller than minimum threshold
        weak_judas = detect_judas_swing(open_price, period_extreme=99.5, bias="BULLISH", min_purge_distance=1.0)
        self.assertFalse(weak_judas.has_judas_swing)


class DailyBiasTests(unittest.TestCase):
    def test_classify_and_next_draw(self):
        self.assertEqual(classify_liquidity_type(is_fvg=True), "IRL")
        self.assertEqual(classify_liquidity_type(is_fvg=False), "ERL")

        self.assertEqual(next_expected_liquidity_draw("IRL"), "ERL")
        self.assertEqual(next_expected_liquidity_draw("ERL"), "IRL")

    def test_prior_boundary_displacement_vs_sweep(self):
        boundary_high = 110.0

        # Displacement: candle closes above prior high
        disp = evaluate_prior_boundary_interaction(
            candle_open=108.0,
            candle_high=113.0,
            candle_low=107.0,
            candle_close=112.0,
            boundary_price=boundary_high,
            boundary_type="HIGH",
        )
        self.assertTrue(disp.tested)
        self.assertEqual(disp.interaction_type, "DISPLACEMENT")

        # Manipulation sweep: candle wicks above prior high but closes back below
        sweep = evaluate_prior_boundary_interaction(
            candle_open=108.0,
            candle_high=112.0,
            candle_low=106.0,
            candle_close=109.0,
            boundary_price=boundary_high,
            boundary_type="HIGH",
        )
        self.assertTrue(sweep.tested)
        self.assertEqual(sweep.interaction_type, "MANIPULATION_SWEEP")

        # Unreached
        unreached = evaluate_prior_boundary_interaction(
            candle_open=105.0,
            candle_high=108.0,
            candle_low=104.0,
            candle_close=106.0,
            boundary_price=boundary_high,
            boundary_type="HIGH",
        )
        self.assertFalse(unreached.tested)
        self.assertEqual(unreached.interaction_type, "UNREACHED")


class MarketMakerModelTests(unittest.TestCase):
    def test_calculate_dealing_range_equilibrium(self):
        eq = calculate_dealing_range_equilibrium(100.0, 120.0)
        self.assertEqual(eq, 110.0)

    def test_evaluate_mmxm_location(self):
        # Range: [100.0, 200.0], Equilibrium: 150.0
        # MMBM (Buy model) must base in DISCOUNT (< 150.0)
        buy_valid = evaluate_mmxm_location(125.0, 100.0, 200.0, "MMBM")
        self.assertTrue(buy_valid.is_valid_location)
        self.assertEqual(buy_valid.location_zone, "DISCOUNT")
        self.assertEqual(buy_valid.relative_position_pct, 25.0)

        buy_invalid = evaluate_mmxm_location(175.0, 100.0, 200.0, "MMBM")
        self.assertFalse(buy_invalid.is_valid_location)
        self.assertEqual(buy_invalid.location_zone, "PREMIUM")

        # MMSM (Sell model) must base in PREMIUM (> 150.0)
        sell_valid = evaluate_mmxm_location(175.0, 100.0, 200.0, "MMSM")
        self.assertTrue(sell_valid.is_valid_location)
        self.assertEqual(sell_valid.location_zone, "PREMIUM")

        sell_invalid = evaluate_mmxm_location(125.0, 100.0, 200.0, "MMSM")
        self.assertFalse(sell_invalid.is_valid_location)
        self.assertEqual(sell_invalid.location_zone, "DISCOUNT")


if __name__ == "__main__":
    unittest.main()
