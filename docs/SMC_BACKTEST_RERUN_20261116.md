# Fresh SMC backtest, November 16, 2026

This reruns the unchanged `smc_event_retest_v5` (OB/FVG event retest) and
`smc_sweep_reclaim_v5` models with newly downloaded history and the current
frozen code. Neither model is enabled for broker orders.

## Why the earlier study had one trade per model

The May 17–November 13 frozen comparison had 13 event-retest candidate
observations and 67 sweep/reclaim observations. Twelve event candidates and
66 sweep candidates exceeded the minimum-lot stop-risk budget. Their median
minimum-lot stop risks were R91.96 and R118.20, versus the nominal R50 budget.
These were candidate observations before portfolio allocation, not extra
executed or proven profitable trades. Remaining guards also applied.

The resulting event-retest trade lost in development; the sweep trade won
in holdout. One observation in either direction cannot establish an edge.

## Rerun method

- Evaluation interval: May 20, 2026 09:50 UTC to November 16, 2026 09:50 UTC.
- 35,699 M5 bars were downloaded, including a two-day warmup, plus separate
  native Daily, H4, H1 and M15 histories. This is not 35,699 complete trades.
- Freeze current code, settings, input hashes, specification and costs before
  prediction/outcome generation. Both models reuse one verified input/cost
  snapshot. The corrected Daily freshness implementation is included.
- Unchanged nominal starting balance R10,000, risk 0.5%, minimum lot 0.01,
  demo cap 0.01, daily research cap six trades, loss-streak cap two and daily
  loss cap 0.6%. No money or trading parameters were changed.
- Next-M5-open entry, previous closed spread proxy, three points adverse
  slippage per side, and existing stop-first M5 management/60-minute horizon.
- The current frozen fee reference is zero; this is not evidence that all
  actual execution is free. Currency conversion and margin use a current
  specification approximation, not historical exchange rates/specifications.
- Chronological 60/20/20 development, validation and holdout. Each stage
  requires 30 trades across two dates, positive mean net R, PF >= 1.1 (or all
  wins) and drawdown <= 6R. No parameter search or outcome-driven retuning.
- Predictions for both models are written and checksummed before outcomes.
  Native screening excludes windows crossing data gaps, session-close buffers
  or split boundaries. Continuity checks use future timestamps only to screen
  outcome availability; future prices are not signal features.

The separate compatibility replay submits the same frozen SMC candidates to
Atlas's shared deterministic confluence, timing, conviction, risk and session
methods. It does not register the models as enabled strategies. It starts
each chronological stage independently at the nominal starting balance; the
native SMC screen carries its simulated balance through the whole interval.
These are separate evidence lanes, not one portfolio to add together.

This is retrospective research, with much of the period previously inspected.
It is not a new blind test, a recreation of historical visual/news/macro state,
measured broker fills, proof of a natural lifecycle, or permission to activate.
The existing paper observers and activation pointers remain separate.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tools.rerun_smc_backtest `
  --run-dir storage/smc_entry_rerun_NEW_UNIQUE_NAME
```

Preparation requires the configured matching demo account for read-only market
data/specification access. Order dispatch is denied. Evaluation runs from the
frozen source with broker initialization and order dispatch denied. A fresh
directory is required; prior evidence cannot be overwritten by this command.

Local signed artifacts are in `storage/smc_entry_rerun_20261116`: protocol,
per-model manifests/inputs, predictions and receipt, native screening report,
and shared-policy report. Raw candles and account-scoped artifacts are ignored
by Git; only a compact summary should be committed.

## Completed results

The prediction phase recorded 17,902 eligible windows before outcome labels,
with 34 checks that shared-context caching did not alter either model's output.

| Model | Complete candidate observations | Above initial R50 stop-risk budget | Native simulated portfolio result |
|---|---:|---:|---|
| OB/FVG event retest | 14 | 13 | One development loss, -R45.25; no validation/holdout trades |
| Sweep and reclaim | 75 | 74 | One holdout win, +R217.32; no development/validation trades |

Median minimum-lot stop risk was R90.80 for event retests and R115.64 for
sweeps, before additional friction. Neither the lot cap nor modeled margin
caused the initial-balance audit's sizing rejections. Both models failed all
stage qualification requirements; no model was selected for forward paper or
broker trading. The two trades belong to separate model portfolios and their
cash results must not be added as one executable Atlas portfolio.

The native screen additionally excluded 7,304 input/outcome-gap windows per
model and approximately 9,900 session/close-buffer windows. It requires eighty
contiguous preceding M5 candles and a contiguous twelve-bar outcome window.
Some gaps are expected market closures; excluded windows are not evidence of
missed profitable trades. This continuity screen limits coverage near closures.

### Compatibility with the shared Atlas gates

| Model | Higher-timeframe confluence rejection | Timing rejection | Shared-policy trades |
|---|---:|---:|---:|
| OB/FVG event retest | 13 | 1 | 0 |
| Sweep and reclaim | 65 | 10 | 0 |

The sizing audit and gate replay are independent, overlapping explanations:
do not add 87 sizing failures to the 89 gate rejections. All shared-policy
candidates were rejected before sizing was reached in that replay.

This confirms a compatibility restriction: the SMC detectors allow higher-
timeframe pullback contexts that often fail the shared all-four directional
confluence gate. Passing the detector's own entry geometry also does not imply
passing the shared timing gate. The current research models cannot simply be
enabled and expected to trade under the present policy. Any redesign must
target those requirements explicitly, preserve risk, use a new frozen version,
and earn independent evidence. Relabeling these failures as qualified would
not fix them.

Compared with the earlier study, the candidate observations increased from
13/67 to 14/75, while simulated executions stayed one per model. The tiny cash
differences use the new specification/currency reference; they are not proof
of a better edge. The interval, freshness implementation and reference changed,
so this is not a controlled attribution of individual changes.

Portable metrics and artifact hashes are in
`SMC_BACKTEST_RERUN_RESULTS_20261116.json`. No broker orders were sent and no
trading rules were changed. Thirty-seven focused regression checks passed.
