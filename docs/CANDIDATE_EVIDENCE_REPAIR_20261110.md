# Candidate evidence and distance repair

Fixed stale candle-context reuse in the visual confirmation path, added explicit evidence clocks/methods, and made the reviewed ATR conversion a shared tested adapter. The closed-bar view remains a shadow preview and corrected-distance strategies remain research-only; none has qualified for activation. Risk limits, strategy selection, entry thresholds and execution authority are unchanged.

## What was wrong

The entry momentum classifier counts the latest eight candle changes and evaluates the latest candle body/range. Screenshot momentum measures pixel displacement across the visible viewport. These are different time/measurement bases; a strong image label cannot establish a confirmed M1 entry. The current live strategy path can also read a still-forming candle, whose body changes during the minute.

There was an additional reuse defect: a recently captured screenshot result could carry a confirmation blended with the previous decision's candle context. Fresh capture age alone did not establish fresh feature context. Both early and late trader reuse paths now rebuild the blended interpretation against the current decision's candle features while preserving the original parsed pixels and capture timestamp. Stale, future-dated, wrong-symbol, wrong-timeframe or non-terminal evidence cannot be rebased. The current timing rules still require their existing candle and visual checks; visual strength does not override weak candle momentum.

## Operator evidence

Visual reads now retain the candle bar/evaluation timestamps used for their feature context. Alignment evidence distinguishes label agreement from actual screen-bar alignment. It never claims the screen's bar is known from viewport pixels alone. The API/UI show the candle measure and chart-viewport measure separately, including whether the indicator used a forming bar.

A closed-bar preview excludes the forming candle and records the last complete bar's momentum, location and enabled built-in signals. It is stored separately from chosen/action and cannot select or submit a trade. This allows comparison of forming and completed-bar evidence without silently changing active strategy logic. Candidate distance review also preserves the active candidate geometry separately from the reviewed ATR geometry, before broker stop adjustments.

## Distance correction

The shared adapter converts price ATR to broker points as ATR × multiplier ÷ broker point, then applies the existing point floor. It supports the six enabled built-ins and the legacy evolved-rule family. It clones a signal, preserving its side and confidence; it does not register or activate strategies. Research uses this shared implementation instead of a duplicate conversion formula.

All 54 saved strategy/variant/period comparisons were replayed on the hashed candle dataset and saved past-only signal cache. Entry times, exit times and cost-adjusted R matched the frozen results within numeric tolerance. This validates implementation parity; it does not validate profitability.

## Frozen forward evidence

The original run_20261110 experiment continues from an exact source snapshot made before these repairs. Its manifest source hashes were verified. Only Python sources were copied; no credentials were copied. The observer still uses the original frozen rules and artifacts, preventing a mid-experiment change of methods. Current source edits therefore do not rewrite the experiment under observation.

The evidence reviewer applies the existing research requirements per comparison: at least twelve training, ten reserved-period and thirty forward cases; at least two days; positive modeled mean; required profit factor and bounded drawdown. Counts from different or overlapping comparisons cannot be summed to pass. Source integrity, recent observation and finite statistics are checked. Even a passing result only becomes eligible for operator review; broker eligibility remains false and no promotion/order is executed.

At this review there were thirty-one overlapping paper outcomes across eighteen comparisons, all from one forward day. No comparison qualified. Some previously promising historical lanes were negative in the early forward sample; momentum continuation had no forward entries yet. The early sample is too small to conclude a sustainable edge, and it does not justify activation.

## Longer historical audit in progress

The first experiment has no training-qualified winner. More forward cases cannot repair its frozen training result. A separate experiment, `storage/cost_research/run_20261110_extended`, therefore declares longer windows and stricter sample requirements before calculating outcomes. Training is October 12–26 UTC, holdout October 26–November 7 UTC, and November 9 onward is explicitly marked already inspected. The requirements are at least thirty cases in each training, holdout and prospective stage, rather than reducing sample requirements to obtain a passing result. The same eighteen predeclared strategy/distance/confirmation comparisons are used, with a winner selected from training alone.

The matching demo supplied 32,453 closed M1 bars from October 8 through November 10 at 13:06 UTC, including warm-up history. As of the 13:18 UTC review, exact original strategy-signal calculations are still running at background priority. No results or winner are claimed for this larger audit. Its manifest, candle dataset and source hashes are saved locally. On completion, inspect `results.json` and `selection.json` in that directory; a selected candidate must pass the reserved period and subsequent paper observation before operator review. This process cannot activate broker trading.

The audit accepts explicit increasing, disjoint windows and rejects reductions below the original sample floors. The reviewer uses the stricter requirements saved in each manifest, rejects nonfinite profit factors and reports a historical-only experiment as pending forward evidence rather than failing to load it.

## Validation and operation

The selected broader suite passed 264 cases. A subsequent 114-case deployment suite passed, including qualification checks for nonfinite returns and stale observation separately from source integrity. The final reviewer suite passed ten cases, and the extended research protocol suite passed nineteen cases before its launch. Tests cover capture-clock preservation, immutable parsed pixels, wrong/stale/future evidence rejection, explicit unverified screen alignment, forming-bar exclusion, unchanged chosen signals, correct point conversion, existing timing gates and qualification isolation. Historical distance parity passed all 54 comparisons.

The replay harness also had an empty storage path, allowing synthetic reports to be written into the working directory. It now owns validated temporary storage for both its store and settings. All sixteen replay/confirmed-retest checks passed after isolation, including unchanged behaviour baselines and a working-directory pollution regression. Six test-modified tracked root reports were backed up locally and restored to their pre-task tracked versions. Existing root journals and production storage were not deleted.

Deployment uses the normal guarded-demo launcher after a matching idle-demo preflight. The separate natural-lifecycle observer and frozen paper observer stay running. The labelled diagnostic lifecycle remains separate from proof of a natural strategy-selected broker trade.

The deployed API confirmed a fresh connected broker, current candle-feature alignment, preserved screenshot clocks, a completed-bar preview and advisory distance geometry (for example, a 100-point EMA candidate stop versus approximately 388 reviewed ATR points in one observed cycle). The source-independent pixel measure remained separately labelled and same-screen-bar alignment remained explicitly unverified. Startup completed successfully in the native desktop.

Current review:

```powershell
.venv\Scripts\python.exe tools/review_cost_research.py --run-dir storage/cost_research/run_20261110
```

If the existing frozen observer needs an explicit restart after it has stopped, use its snapshot rather than the changed live research source:

```powershell
.venv\Scripts\python.exe storage/cost_research/run_20261110/frozen_source/tools/observe_cost_research.py --run-dir storage/cost_research/run_20261110 --hours 24
```

Do not launch a duplicate observer. Raw deployment, parity and review evidence stays local in docs/diagnostics and storage/cost_research. Qualification, actual executable profitability and a natural autonomous broker lifecycle remain evidence to collect, not outcomes this repair can guarantee.
