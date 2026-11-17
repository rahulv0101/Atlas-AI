# Why the deployed-preset M5 diagnostic lost money

All 47 original simulated entries, exits, prices, initial cash risk and net cash
outcomes were reproduced from the signed candidate stream and archived candles.
This is a fixed-sample diagnosis, not fresh validation, live broker evidence or
proof that a proposed correction is profitable. No policy or parameter changed.

## Confirmed findings

- All 47 trades exited in their entry M5 candle: 33 losing stops and 14 targets.
  The one-hour holding cap, trailing and stale-exit management therefore did
  not determine these recorded exits. We cannot assume a management change
  would save them.
- Stops were $0.85, $1.00 or $1.10 in gold price. The median was $1.00; median
  preceding closed ATR was approximately $4.52. The median per-trade ratio of
  stop distance to preceding ATR was 0.230. This suggests a geometry/timeframe
  mismatch; it is not proof that wider protection improves expectancy.
- Eight trades touched stop and target in the same M5 candle. The simulator
  used its conservative stop-first convention. Exact intrabar order remains
  unknown. No favorable high from the exit candle is counted as evidence that
  a trade could have been rescued before stopping.
- Average simulated winner was R24.66 and average loser R17.53. At those
  observed payoffs, break-even requires about 41.55% wins. The sample achieved
  29.79% (14/47), losing R233.33. These sample payoffs are not a live forecast.
- EMA crossover supplied 39 trades, ten wins and -R257.18. Micro impulse had
  only three trades; pullback had five. Positive small subgroups cannot justify
  selecting strategies, directions or sessions retrospectively.

## Specific unit inconsistency to test

`EMACrossoverStrategy.generate_signal()` in `strategies/built_in.py` calculates
ATR in price units but passes `max(vol * 2, 100)` as stop **points**, and
`max(vol * 3, 150)` as target points. With point size 0.01, a price ATR around
4.52 gives about 904 points for a two-ATR stop, while the legacy expression
usually floors it at 100 points ($1.00). The existing research adapter in
`strategies/distance_units.py` already implements explicit price-to-point
conversion. The live generation path has not activated that adapter.

This is a concrete dimensional inconsistency in the intended ATR scaling.
Correcting it changes protection, target distances and minimum-lot affordability,
so the diagnosis does not silently activate new geometry. Earlier research
already tested related conversion/confirmation variants without qualification;
this finding must not be presented as a newly discovered profitable strategy.

The bounded next experiment is to compare unchanged geometry with the existing
unit-corrected adapter on the same frozen base inventory, then separate archived
and prospective data. Preserve risk fractions, lot caps, costs, sessions and
execution gates. Report unaffordable trades as rejected; do not raise capital
or tighten stops to manufacture entries. Use observed tick order on a separate
idle test terminal to resolve ambiguous candles where available. Never replace
stop-first results with optimistic ordering solely to improve performance.

## Evidence and verification

- `tools/diagnose_deployed_m5_losses.py`: receipt checks, exact reproduction,
  subgroup/payoff analysis and pre-exit-only excursions.
- `storage/deployed_m5_loss_diagnosis_20261117/report.json`: signed detailed
  reproduction of all 47 trades, with modeled quote-side costs.
- `DEPLOYED_M5_LOSS_DIAGNOSIS_20261117.json`: portable summary and receipts.
- Nine focused tests cover payoff/flat classification and the existing excursion
  and native-terminal audit guards.

Broker conversion and costs remain modeled using the frozen specification.
Fees configured as zero are not proof that natural execution costs are zero.
Full live parity, a qualified profitable model, automatic chart switching and
natural automated broker lifecycle verification are not established here.
