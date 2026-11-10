# Recorded blocked-setup replay — 10 November 2026

The retained candidates do not support broadly relaxing the timing or higher-timeframe filters. Some rejected entries became hypothetical winners, but their cohorts lost overall after recorded spreads. This is a short observational audit, not proof that the filters are optimal or that Atlas is profitable.

## Sample and method

Reviewed the current journal from 9 November 00:00 UTC through 10 November 08:15 UTC. Replayed 365 timing rejections and 43 higher-timeframe rejections against 1,890 broker M1 candles. Only candidates with explicitly UTC-tagged market evidence and positive recorded stop/target distances qualified. Manual diagnostic tests are excluded. Future bars must be complete, ordered and contiguous; gaps and unmatched events are skipped. All 408 eligible candidates had a usable horizon in this window.

Entry is hypothetical at the next M1 open after the event minute. The existing backtest management simulator uses recorded stops/targets, up to 12 bars, break-even/trailing logic and stop-first ordering when a bar touches both stop and target. Broker point size was checked at 0.01. This is not a reconstruction of live fills or tick management.

Repeated signals can describe the same market move. Each cohort therefore also has a greedy version allowing no new hypothetical entry through the prior exit bar. Five older evolved-strategy records had stops smaller than their recorded spreads (four timing, one higher-timeframe); those were retained in the full results and separately removed for the sensitivity below. Historical distances were not corrected after the fact. Current StrategyFactory already converts ATR price distances to broker points and has a regression test for that conversion.

## Results excluding sub-spread stops and within-cohort overlap

| Rejection cohort | Cases | Gross average R | Average R after recorded spread | Winners after spread | Profit factor after spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| Timing discipline | 262 | -0.018 | -0.373 | 89 / 262 (34.0%) | 0.49 |
| Higher-timeframe disagreement | 38 | +0.004 | -0.369 | 15 / 38 (39.5%) | 0.52 |

R is the hypothetical recorded stop distance, not rand profit. Spreads alone turned approximately break-even gross cohorts into negative cohorts. Adding the configured hypothetical 1.5 basis-point slippage assumption worsened the averages to -0.997R and -1.015R respectively. That slippage is a sensitivity assumption, not measured broker slippage. Commissions are not supplied and are omitted in every scenario.

For timing rejections with recorded scores at least 65/100, the same sensitivity retained 71 nonoverlapping cases: 25 winners, 46 losers, average -0.392R after spread. Score stages vary across the pipeline; this is descriptive evidence, not calibrated probability. The higher-timeframe cohort had only one such case, insufficient for a conclusion.

Two previously cited high-score cases illustrate the distinction: gold_breakout_retest at 02:41:55 UTC and evolved_rule at 05:53:06 UTC on 10 November both scored 89/100 but hit their stops in the replay. Each returned -1.00R gross / -1.36R after its recorded spread. The 88/100 breakout case at 00:19:45 UTC exited at approximately +0.05R gross and -0.31R after spread.

## Interpretation and limits

The replay found possible missed winners, alongside more losing entries after spreads. It does not provide evidence to remove these gates wholesale or to force high-confidence trades. The main research concern is whether the strategy's expected move can overcome spread and other costs, rather than making the confidence display higher.

Small post-hoc pockets were positive before slippage/commission: six nonoverlapping evolved-rule higher-timeframe rejections averaged +0.118R after spread, and one micro-impulse case was positive. Those tiny selected subsets do not validate a new exception. They can be hypotheses for a later frozen-rule test rather than evidence for immediate activation.

There is no matched allowed-trade control cohort, randomized comparison, actual fill reconstruction or complete live management replay. Portfolio daily limits, cooldowns and session-forced exits are not reconstructed; cohort R cannot be summed into an account-return forecast. Other gates could still reject these candidates. Cohorts share market conditions even after removing overlap, and the sample is too short to establish sustainable performance. This audit cannot establish causal filter benefit, select an optimal replacement rule, or prove natural autonomous trading.

Next evidence should come from a frozen rule evaluated on a later untouched period, with cost-aware outcomes and matched pass/block candidates. No strategy, threshold, risk or execution setting was changed; no orders were submitted. The runtime was left running.

## Reproduction

`python tools/blocked_setup_replay.py --start 2026-11-09T00:00:00Z --end 2026-11-10T08:15:00Z --output docs/diagnostics/blocked_setup_replay_20261110.json`

Raw JSON, per-candidate results and broker candle CSV remain local under docs/diagnostics. Replay integrity tests cover timestamp units, missing evidence, complete forward horizons, gaps, manual-test exclusion, higher-timeframe cohort classification, stop-first ordering, overlapping positions and cost-summary reporting.

Validation: all 27 selected replay and research-worker integrity cases passed. The running API was checked after the audit and continued to report a connected broker. No runtime restart or trading-policy change was required.
