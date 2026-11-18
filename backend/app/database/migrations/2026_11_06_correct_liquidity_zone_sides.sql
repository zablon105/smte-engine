-- One-time data correction for zones produced by the pre-2026-11-06
-- liquidity detector, which stored equal highs as SELL_SIDE and equal lows
-- as BUY_SIDE.
--
-- Back up the database first. Apply only if the existing liquidity_zones
-- rows were created using that detector mapping; do not apply to a database
-- containing manually labeled zones. This migration is intentionally not
-- run automatically by init_db.py.
BEGIN;

UPDATE liquidity_zones
SET zone_type = CASE zone_type
    WHEN 'BUY_SIDE' THEN 'SELL_SIDE'
    WHEN 'SELL_SIDE' THEN 'BUY_SIDE'
    ELSE zone_type
END
WHERE zone_type IN ('BUY_SIDE', 'SELL_SIDE');

COMMIT;
