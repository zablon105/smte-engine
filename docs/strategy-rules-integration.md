# Research Rules Integration Map

This document maps the research notes in `SMTE_Research/verified_rules` to
the current SMTE backend. It is an implementation roadmap, not a claim that
the research rules are validated or profitable.

## Integration principles

- Keep the PDF library, extracted text, evidence, and draft rules in the
  separate `SMTE_Research` workspace. Jupyter is needed to continue the
  research workflow, but not to keep already-saved outputs available.
- Treat evidence files as source leads, not verified trading instructions.
  Check cited source pages, note OCR uncertainty and source independence,
  and preserve disagreements between sources.
- Reuse existing detectors where possible. Do not silently add a second
  detector for a concept SMTE already implements.
- Turn ambiguous interpretations into separately named, configurable
  experiments rather than changing established behavior without comparison.
- Test detection and signal changes with unit tests and historical data,
  accounting for execution costs and avoiding look-ahead. Do not infer future
  profitability from research claims or selected examples.
- Keep research-derived changes out of live execution by default until the
  user has reviewed the behavior and the relevant tests and backtests pass.

## Rule-to-code map

| Research rule | Existing SMTE code | Integration work |
|---|---|---|
| CRT / Candle Range Theory | `backend/core/crt/detector.py`; `backend/core/strategy_rules/crt.py`; signal generation in `backend/core/execution/signal_generator.py` | Both detectors require a close beyond the opposite range boundary and promote a previously pending setup when a later candle confirms. A non-executing helper calculates the documented 50% and opposing-edge targets. Still compare range selection and timeframe variants with the draft; keep disagreements distinct. |
| Liquidity, equal highs/lows, sweeps, DOL | `backend/core/liquidity/detector.py`; `backend/core/dol/targeter.py`; `backend/core/scoring/confluence.py` | Highs now map to buy-side liquidity and lows to sell-side liquidity, including sweep detection and CRT confluence matching. Equality tolerance remains configurable; whether a sweep requires a wick or close remains a research variant. Existing database zone labels created by the old reversed mapping need a reviewed rebuild or correction before relying on historical liquidity confluence. |
| Market Structure / MSS / BOS / CHOCH | `backend/core/market_structure/detector.py`; `backend/core/execution/scalp_refiner.py` | Compare swing confirmation, close-based breaks, sweep-before-MSS, displacement, and swing tiers. Keep the existing swing-length behavior measurable against draft variants. |
| Fair Value Gap | `backend/core/market_analysis/fvg_detector.py`; `backend/core/execution/scalp_refiner.py` | Audit formation, mitigation, and entry semantics against the cited pages; distinguish general FVG detection from model-specific entry requirements. |
| Order Block | `backend/core/order_blocks/detector.py` | Compare the existing opposite-candle/impulse heuristic with the competing source definitions, validation rules, zone sizes, and 50% variants. Do not replace the current heuristic on draft evidence alone. |
| Breaker Block | No dedicated breaker detector found | Define and test breaker candle selection, zone boundaries, and validation before adding a detector. Resolve or expose the source variants as experiments. |
| SMT Divergence | `backend/core/smt/detector.py`; confluence in `backend/core/scoring/` | Audit correlation direction, swing matching, time tolerance, and its role as confluence. Drafts caution against treating SMT alone as an entry. |
| Killzones / Silver Bullet / session times | `backend/core/sessions/builder.py`; `backend/core/strategy_rules/session_windows.py`; `backend/core/execution/signal_generator.py` | A research-only helper supports named Handbook, Mansoori, index, and Silver Bullet windows in New York local time, including daylight-saving changes. Conflicting profiles are preserved and are not wired into execution. Compare them with current UTC behavior before changing defaults. |
| OTE | `backend/core/strategy_rules/ote.py` (calculation only); scalp refinement has its own entry logic | A non-executing helper calculates the documented 62%-79% band and 70.5% midpoint from explicit caller-supplied anchors. Swing selection, stops, extensions, and skipped-zone behavior remain unresolved; no signal or order uses this helper. |
| Daily Bias / IRL-ERL / premium-discount | Related concepts exist in liquidity, FVG, DOL, and scoring modules; no dedicated daily-bias engine found | The notes describe a framework, not a numeric long/short formula. First define measurable inputs and separate interpretations; do not manufacture a bias from the narrative alone. |
| Power of 3 / AMD / Judas Swing | CRT and sessions provide related primitives; no dedicated PO3 module found | Specify candle/open selection, timezone, manipulation, and distribution conditions. Treat day-of-week and timing claims as testable hypotheses, not defaults. |
| Turtle Soup | CRT and liquidity detectors provide related primitives; no dedicated module found | Reconcile it with the CRT definition and specify the purge, confirmation, stop, and target. Avoid duplicate signals for the same setup. |
| Unicorn Model | Related breaker, FVG, liquidity, and SMT components; no composite model found | Once breaker semantics are defined, test the ordered sweep/SMT, breaker, FVG overlap, and pre-existing DOL requirements as a separate composite strategy. |
| Market Maker Models (MMXM/MMSM/MMBM) | CRT, DOL, market structure, FVG, and order-block components | The notes primarily define a narrative and phases. Map these to measurable existing events before designing a composite; avoid subjective labels as executable conditions. |
| Timeframe Alignment | MTF CRT, HTF filters in signal generation, and timeframe-specific detectors | Compare the different two- and three-timeframe schemes as named configurations; do not choose one from conflicting source claims. |
| Risk, drawdown, pivots, support/resistance, range deviations, candle/time notes | `backend/app/services/risk_manager.py`; related levels in liquidity and DOL | These notes include caveats and unresolved definitions. Audit existing risk behavior separately; add only well-defined, independently testable calculations. |

### Existing liquidity database rows

The old detector stored equal highs and lows using the opposite side labels.
The detector and scoring code now use conventional BSL/SSL direction. If the
database contains zones generated by the old detector, back it up and review
the one-time SQL correction at
`backend/app/database/migrations/2026_11_06_correct_liquidity_zone_sides.sql`.
Do not apply it to manually labeled zone data. The migration is not run
automatically.

## Suggested implementation sequence

1. **Audit the foundations:** CRT, liquidity/sweeps, market structure, FVG, and
   order blocks. Document exact current behavior and add or update focused
   tests before changing detector behavior.
2. **Compare variants:** session/killzone timezones, timeframe alignment, SMT
   filters, and explicit OTE calculations. Keep conflicting variants
   selectable for research and backtesting.
3. **Build composite models:** Breaker, Silver Bullet, Turtle Soup, Unicorn,
   PO3, Daily Bias, and Market Maker Models using shared primitives rather
   than parallel copies.
4. **Validate risk and performance:** assess signal-level and portfolio-level
   behavior with historical data, realistic costs, time-ordered splits, and
   existing safety controls before considering any live-use change.

For each implementation, record the source pages, the exact interpretation
chosen, relevant alternative variants, tests, and backtest configuration.

## Completed in the current pass

- CRT distribution confirmation and promotion of pending setups.
- Buy-side/sell-side naming and sweep direction for equal-high/equal-low zones.
- Non-executing CRT target calculation for the documented range midpoint and
  opposing edge.
- OTE retracement-zone calculation from explicit anchors, without automatic
  swing selection or trade execution.
- Source-specific New York session-window profiles for research/backtesting,
  not connected to signal generation.
- Breaker Block calculation (`backend/core/strategy_rules/breaker.py`):
  body vs. full candle sizing, mean threshold (50%), break validation, and mitigation checks.
- Unicorn Model (`backend/core/strategy_rules/unicorn.py`): Breaker + FVG overlap zone
  calculation and 4-step setup verification (sweep/SMT, breaker, FVG, DOL).
- Turtle Soup / Purge Model (`backend/core/strategy_rules/turtle_soup.py`): 3-candle sequence
  evaluation (TBS / TWS), manipulation extreme invalidation, and 50% / opposing-edge targets.
- Timeframe Alignment (`backend/core/strategy_rules/timeframe_alignment.py`): Standardized multi-timeframe
  profiles (position, swing, short_term, intraday, daily_bias, crt_intraday) and pairing validators.
- Power of 3 / AMD (`backend/core/strategy_rules/power_of_three.py`): Time-based entry pricing
  (discount below open for longs, premium above open for shorts) and Judas swing detection.
- Daily Bias & IRL/ERL (`backend/core/strategy_rules/daily_bias.py`): Internal vs. external range liquidity
  transitions, and prior candle displacement vs. manipulation sweep evaluation.
- Market Maker Model (`backend/core/strategy_rules/market_maker_model.py`): Dealing range equilibrium
  and base qualification (discount for MMBM, premium for MMSM).

