"""
confluence.py
Links CRT setups to liquidity zones they swept, and produces a
confluence score for each setup — the first real building block
of the setup_scores table.

Beginner note on the matching logic:
  A BULLISH CRT setup's manipulation candle dips BELOW the range
  low - that's a sweep of a BUY_SIDE liquidity zone (per our
  liquidity detector's naming: BUY_SIDE = equal lows, stops sit
  below). A BEARISH setup's manipulation spikes ABOVE the range
  high - that's a sweep of a SELL_SIDE zone (equal highs).

  We only match a zone if it existed BEFORE the manipulation
  candle happened (a zone formed afterward can't have caused it),
  and its price level is close to the manipulation price.
"""

from app.models.models import CrtSetup, LiquidityZone, OrderBlock, SetupScore


def _matching_zone_type(setup_direction: str) -> str:
    return "BUY_SIDE" if setup_direction == "BULLISH" else "SELL_SIDE"


def _true_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10
    return point


def _find_matching_zone(db, instrument_id: int, setup: CrtSetup, tolerance: float):
    """
    Looks for a liquidity zone that:
      - matches the zone type implied by the setup's direction
      - formed before the setup's manipulation candle
      - sits within `tolerance` of the manipulation price
    Returns the best matching zone (closest price + highest strength),
    or None if nothing matches.
    """
    zone_type = _matching_zone_type(setup.setup_direction)
    manipulation_price = float(setup.manipulation_price)

    candidates = (
        db.query(LiquidityZone)
        .filter(
            LiquidityZone.instrument_id == instrument_id,
            LiquidityZone.zone_type == zone_type,
            LiquidityZone.formed_at < setup.detected_at,
            LiquidityZone.price_level.between(
                manipulation_price - tolerance, manipulation_price + tolerance
            ),
        )
        .all()
    )

    if not candidates:
        return None

    # Prefer the closest price match; break ties with higher strength
    candidates.sort(
        key=lambda z: (abs(float(z.price_level) - manipulation_price), -(z.strength_score or 0))
    )
    return candidates[0]


def _find_matching_order_block(db, instrument_id: int, setup, tolerance: float):
    """
    Looks for an ACTIVE (unmitigated) order block that:
      - matches the direction implied by the setup (BULLISH setup ->
        BULLISH block, since that's where buyers likely stepped in)
      - formed before the setup's manipulation candle
      - the manipulation price falls within the block's range,
        expanded by `tolerance` on each side
    Returns the best matching block (smallest range = most precise
    zone), or None if nothing matches.
    """
    manipulation_price = float(setup.manipulation_price)

    candidates = (
        db.query(OrderBlock)
        .filter(
            OrderBlock.instrument_id == instrument_id,
            OrderBlock.block_type == setup.setup_direction,
            OrderBlock.is_mitigated == False,
            OrderBlock.formed_at < setup.detected_at,
        )
        .all()
    )

    matches = [
        b
        for b in candidates
        if (float(b.low_price) - tolerance)
        <= manipulation_price
        <= (float(b.high_price) + tolerance)
    ]

    if not matches:
        return None

    # Prefer the tightest (smallest range) matching block - a more
    # precise zone is a stronger signal than a wide, loose one.
    matches.sort(key=lambda b: float(b.high_price) - float(b.low_price))
    return matches[0]


def _score_already_exists(db, crt_setup_id: int) -> bool:
    return db.query(SetupScore).filter_by(crt_setup_id=crt_setup_id).first() is not None


def score_crt_setups(
    db,
    instrument_id: int,
    tolerance_pips: float = 5.0,
    digits: int = 5,
    point: float = 0.00001,
) -> int:
    """
    Scores every CRT setup that doesn't already have a SetupScore row.

    Currently only the liquidity confluence factor is populated
    (order_block_score, fvg_score, structure_score, smt_score,
    session_score all default to 0 until those detectors exist).
    total_score is just liquidity_score for now, and will become a
    real weighted sum once more factors are added.

    Returns the number of new SetupScore rows created.
    """
    true_pip = _true_pip_size(digits, point)
    tolerance = tolerance_pips * true_pip

    setups = db.query(CrtSetup).filter_by(instrument_id=instrument_id).all()
    created_count = 0

    for setup in setups:
        if _score_already_exists(db, setup.id):
            continue

        matched_zone = _find_matching_zone(db, instrument_id, setup, tolerance)

        # Liquidity score: use the matched zone's strength (touch count,
        # already capped 0-10 by the liquidity detector), or 0 if no match.
        liquidity_score = matched_zone.strength_score if matched_zone else 0

        # Distribution-confirmed setups get a small bonus baked into
        # total_score for now, since that phase is itself meaningful
        # confirmation - this will be replaced by a proper weighted
        # formula once more factors (order blocks, FVGs, etc.) exist.
        confirmation_bonus = 3 if setup.phase == "DISTRIBUTION" else 0

        score = SetupScore(
            crt_setup_id=setup.id,
            liquidity_score=liquidity_score,
            order_block_score=0,
            fvg_score=0,
            structure_score=0,
            smt_score=0,
            session_score=0,
            total_score=liquidity_score + confirmation_bonus,
        )
        db.add(score)
        created_count += 1

    db.commit()
    return created_count


def score_crt_setups_v2(
    db,
    instrument_id: int,
    liquidity_tolerance_pips: float = 15.0,
    order_block_tolerance_pips: float = 10.0,
    digits: int = 5,
    point: float = 0.00001,
) -> int:
    """
    Scores CRT setups using BOTH liquidity confluence AND order
    block confluence. Re-scores setups even if a SetupScore row
    already exists (unlike score_crt_setups, which skips existing
    rows) - use this version once order blocks are ready to be
    incorporated, since it supersedes the liquidity-only version.

    fvg_score, structure_score, smt_score, session_score remain 0
    until those detectors exist.

    Returns the number of SetupScore rows created or updated.
    """
    true_pip = _true_pip_size(digits, point)
    liquidity_tolerance = liquidity_tolerance_pips * true_pip
    order_block_tolerance = order_block_tolerance_pips * true_pip

    setups = db.query(CrtSetup).filter_by(instrument_id=instrument_id).all()
    processed_count = 0

    for setup in setups:
        matched_zone = _find_matching_zone(db, instrument_id, setup, liquidity_tolerance)
        liquidity_score = matched_zone.strength_score if matched_zone else 0

        matched_block = _find_matching_order_block(
            db, instrument_id, setup, order_block_tolerance
        )
        # Order block score: fixed value for a match, since order
        # blocks don't have a natural "strength" measure the way
        # liquidity zones do (touch count). A flat 5 reflects "yes,
        # this confluence factor is present" without overweighting it.
        order_block_score = 5 if matched_block else 0

        confirmation_bonus = 3 if setup.phase == "DISTRIBUTION" else 0

        existing_score = db.query(SetupScore).filter_by(crt_setup_id=setup.id).first()
        total = liquidity_score + order_block_score + confirmation_bonus

        if existing_score:
            existing_score.liquidity_score = liquidity_score
            existing_score.order_block_score = order_block_score
            existing_score.total_score = total
        else:
            score = SetupScore(
                crt_setup_id=setup.id,
                liquidity_score=liquidity_score,
                order_block_score=order_block_score,
                fvg_score=0,
                structure_score=0,
                smt_score=0,
                session_score=0,
                total_score=total,
            )
            db.add(score)

        processed_count += 1

    db.commit()
    return processed_count