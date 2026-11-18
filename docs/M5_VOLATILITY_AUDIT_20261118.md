# M5 volatility guard: verified formula and isolated test

## Active rule

`AtlasTrader._market_regime()` takes 60 closes in the live decision path and
computes `100 * mean(abs(successive close differences)) / abs(last close)`,
rounded to four decimals: 59 close-to-close moves. This is not true-range ATR,
standard deviation, or a percentile. In enabled M5 top-down mode, `step()`
filters unfinished M5 candles before constructing this window. The calculator
itself accepts closes and cannot independently verify candle timestamps.

`_volatility_safety_state()` uses the same fixed price boundaries for M1 and
M5: 0.045% elevated, 0.07% extreme. VIX extreme/panic independently blocks
entries. Therefore the screenshot's 0.0735% exceeds the configured price cap;
it does not independently prove that the market is statistically extreme.

## Reproduced calibration and coverage

The previous input-only calibration was reproduced exactly from receipt-checked
native M1/M5 history: 2,160 paired, gap-free, completed 295-minute windows
across ten dates in October 1-15, 2026. Median M5/M1 ratio: 2.19468024.
Proposed boundaries remain 0.09876061% elevated and 0.15362762% extreme.
There was no parameter search or outcome-driven retuning.

In the October 15-November 14 retrospective validation, 4,707 valid paired
windows had median M5 movement 0.05154%. The current price cutoff classified
about 18.08% as extreme; the scaled cutoff classified zero. The screenshot
value lies around the 86.68th percentile. These are coverage estimates using
unrounded paired-window measurements, not exact live event rejection rates.
Calibration-period extreme fractions were about 8.47% versus zero.

Zero scaled price vetoes in both periods is an untested tail-protection concern,
not proof that every previously blocked entry is safe. VIX panic/extreme vetoes
remain active in both policies and are covered by tests.

## Volatility-only matched comparison

The test uses corrected ATR point distances in both lanes, R100,000 virtual
capital, identical candidate stream, costs, lot/risk limits and shared checks.
Only volatility price boundaries change. It does not include the old combined
proposal's extra entry-confirmation intervention. Both periods were previously
available/inspected; validation is chronological and retrospective, not blind.

| October 15-November 14 | Trades | Wins | Net simulated rand | Mean net R |
|---|---:|---:|---:|---:|
| Current boundaries | 9 | 7 | 669.37 | 0.5421 |
| Scaled M5 boundaries | 11 | 7 | 555.33 | 0.3471 |

All nine original entry/exit/cash outcomes were retained. The candidate added
two losses: -R102.18 on October 23 and -R11.86 on November 13. Net deterioration:
R114.05. Both lanes fail the existing minimum-thirty-trade review. This small
sample does not prove the current threshold optimal, but does not support
activating the tested replacement or loosening a guard merely to obtain entries.
Full live parity, historical visual/macro evidence and measured natural fills
remain incomplete. No live policy changed and no orders were submitted.

## Related results and forward evidence

The completed demo-representative distance comparison is separately retained in
`DEMO_REPRESENTATIVE_M5_RESULTS_20261118.json`: corrected geometry produced forty
primary-period simulations, twenty-nine wins and +R3,146.17, while unchanged
geometry lost R233.33. April had no trades in either lane. That positive reused
primary result is not proof of a qualified replacement and must not be attributed
to the unactivated volatility change.

The old calibration forward collector is `blocked_review_required` because
`observed_closed_candles_revised` was detected. Its receipts/status are preserved;
it was not reset or described as collecting successful fresh validation. History
revision review and a separately frozen future experiment remain outstanding.

## Artifacts

- `tools/audit_m5_volatility.py`: calibration reproduction and isolated replay.
- `storage/m5_volatility_isolation_20261118`: signed protocol, candidates,
  lane checkpoints and final report.
- `M5_VOLATILITY_AUDIT_20261118.json`: portable results and receipts.
- Read-only research status retains the capital comparison and adds these two
  volatility lanes. No strategy or observer was selected for activation.

The new runner source hash is recorded after the run and is explicitly labelled
as such; it is not represented as a pre-outcome frozen source snapshot. Existing
calibration/candidate/reference receipts and protocol precede outcome replay.
Source code is repo-visible. Four new tests plus existing calibration checks
cover the active arithmetic, boundary behavior, gap/future exclusion and VIX veto.
