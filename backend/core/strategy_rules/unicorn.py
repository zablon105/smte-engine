"""Non-executing Unicorn Model calculations and setup validation."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Optional


@dataclass(frozen=True)
class UnicornOverlap:
    bottom: float
    top: float
    midpoint: float
    span: float


@dataclass(frozen=True)
class UnicornValidation:
    is_valid: bool
    overlap: Optional[UnicornOverlap]
    missing_requirements: tuple[str, ...]


def calculate_unicorn_overlap(
    breaker_bottom: float,
    breaker_top: float,
    fvg_bottom: float,
    fvg_top: float,
) -> Optional[UnicornOverlap]:
    """Calculate the overlap zone between a Breaker Block and a Fair Value Gap.

    According to the Unicorn Model research notes:
    - Entry occurs where the Breaker Block overlaps the FVG.
    - Overlap zone = [max(breaker_bottom, fvg_bottom), min(breaker_top, fvg_top)].
    - Valid only if bottom < top. Returns None if there is no positive overlap.
    """
    for price, label in (
        (breaker_bottom, "breaker_bottom"),
        (breaker_top, "breaker_top"),
        (fvg_bottom, "fvg_bottom"),
        (fvg_top, "fvg_top"),
    ):
        if not isfinite(price):
            raise ValueError(f"{label} must be finite")

    if breaker_bottom >= breaker_top:
        raise ValueError("breaker_bottom must be strictly less than breaker_top")
    if fvg_bottom >= fvg_top:
        raise ValueError("fvg_bottom must be strictly less than fvg_top")

    overlap_bottom = max(breaker_bottom, fvg_bottom)
    overlap_top = min(breaker_top, fvg_top)

    if overlap_bottom < overlap_top:
        span = overlap_top - overlap_bottom
        midpoint = (overlap_bottom + overlap_top) / 2.0
        return UnicornOverlap(
            bottom=overlap_bottom,
            top=overlap_top,
            midpoint=midpoint,
            span=span,
        )
    return None


def validate_unicorn_setup(
    has_trigger_sweep_or_smt: bool,
    has_aligned_breaker: bool,
    has_aligned_fvg: bool,
    has_clear_dol: bool,
    overlap: Optional[UnicornOverlap],
) -> UnicornValidation:
    """Validate all 4 prerequisite steps of the Unicorn Model.

    Steps from research notes:
    1. Trigger: A liquidity sweep OR an SMT divergence.
    2. Breaker Block in the direction of bias.
    3. FVG aligned with and overlapping the Breaker Block.
    4. Clear DOL (Draw on Liquidity, e.g. equal highs/lows) established before entry.
    """
    missing = []
    if not has_trigger_sweep_or_smt:
        missing.append("trigger_sweep_or_smt")
    if not has_aligned_breaker:
        missing.append("aligned_breaker")
    if not has_aligned_fvg:
        missing.append("aligned_fvg")
    if not has_clear_dol:
        missing.append("clear_dol")
    if overlap is None:
        missing.append("breaker_fvg_overlap")

    is_valid = len(missing) == 0
    return UnicornValidation(
        is_valid=is_valid,
        overlap=overlap,
        missing_requirements=tuple(missing),
    )

