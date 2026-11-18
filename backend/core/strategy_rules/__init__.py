"""Reusable, non-executing calculations for research-derived strategies."""

from core.strategy_rules.breaker import (
    BreakerZone,
    calculate_breaker_zone,
    is_breaker_mitigated,
    validate_breaker_break,
)
from core.strategy_rules.crt import CRTTargets, calculate_crt_targets
from core.strategy_rules.daily_bias import (
    BoundaryInteraction,
    classify_liquidity_type,
    evaluate_prior_boundary_interaction,
    next_expected_liquidity_draw,
)
from core.strategy_rules.market_maker_model import (
    MMXMLocationAssessment,
    calculate_dealing_range_equilibrium,
    evaluate_mmxm_location,
)
from core.strategy_rules.ote import OTEZone, calculate_ote_zone
from core.strategy_rules.power_of_three import (
    JudasSwingAssessment,
    PO3PricingAssessment,
    detect_judas_swing,
    evaluate_po3_pricing,
)
from core.strategy_rules.session_windows import (
    SessionWindow,
    WINDOW_PROFILES,
    active_session_windows,
)
from core.strategy_rules.timeframe_alignment import (
    TIMEFRAME_PROFILES,
    TimeframeProfile,
    get_aligned_entry_timeframes,
    get_timeframe_profile,
    is_valid_timeframe_pairing,
)
from core.strategy_rules.turtle_soup import (
    TurtleSoupEvaluation,
    TurtleSoupTargets,
    calculate_turtle_soup_targets,
    evaluate_turtle_soup_sequence,
)
from core.strategy_rules.unicorn import (
    UnicornOverlap,
    UnicornValidation,
    calculate_unicorn_overlap,
    validate_unicorn_setup,
)

__all__ = [
    # CRT
    "CRTTargets",
    "calculate_crt_targets",
    # OTE
    "OTEZone",
    "calculate_ote_zone",
    # Session Windows
    "SessionWindow",
    "WINDOW_PROFILES",
    "active_session_windows",
    # Breaker Block
    "BreakerZone",
    "calculate_breaker_zone",
    "is_breaker_mitigated",
    "validate_breaker_break",
    # Unicorn Model
    "UnicornOverlap",
    "UnicornValidation",
    "calculate_unicorn_overlap",
    "validate_unicorn_setup",
    # Turtle Soup
    "TurtleSoupTargets",
    "TurtleSoupEvaluation",
    "calculate_turtle_soup_targets",
    "evaluate_turtle_soup_sequence",
    # Timeframe Alignment
    "TimeframeProfile",
    "TIMEFRAME_PROFILES",
    "get_timeframe_profile",
    "get_aligned_entry_timeframes",
    "is_valid_timeframe_pairing",
    # Power of 3
    "PO3PricingAssessment",
    "JudasSwingAssessment",
    "evaluate_po3_pricing",
    "detect_judas_swing",
    # Daily Bias
    "BoundaryInteraction",
    "classify_liquidity_type",
    "next_expected_liquidity_draw",
    "evaluate_prior_boundary_interaction",
    # Market Maker Model
    "MMXMLocationAssessment",
    "calculate_dealing_range_equilibrium",
    "evaluate_mmxm_location",
]
