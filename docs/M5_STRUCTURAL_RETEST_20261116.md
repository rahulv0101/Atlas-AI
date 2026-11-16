# M5 structural-entry research and tick loss reconstruction

This is research evidence, not activation or a promise to recover losses.
The six enabled broker strategies remain EMA Crossover, Trend Pullback,
Momentum Continuation, Gold Micro Impulse, Gold Breakout Retest and Gold
Liquidity Sweep. Dedicated SMC OB/FVG models, the calibrated M5 proposal and
this structural proposal have no broker authority.

## Loss reconstruction

`tools/reconstruct_m5_losses.py` checks the ten recorded validation trades from
`storage/m5_calibration_20261116_v3`. It queries broker quotes without sending
orders, tests explicit UTC and configured server-clock interpretations, and
accepts only a unique clock interpretation matching the original Bid candle
within 1.01 points with bounded quote gaps. Short exits use Ask, long exits Bid.
Equal-millisecond stop/target events remain unresolved.

All ten recorded first-bar paths passed those checks. All eight recorded losses
hit their recorded stop before the target, including both originally ambiguous
candles. Both recorded wins hit their target first. The separate first-quote
entry diagnostic is an approximation; it is not an observed broker fill.
No portfolio result has been recomputed from those diagnostics.

The eight losses were simulated, not demonstrated live losses. Quote history
does not prove complete venue history, executable fills, protection acceptance,
latency or actual slippage. Raw quotes and signed artifacts remain locally in
`storage/tick_loss_reconstruction_20261116`.

## One fixed structural hypothesis

`m5_structural_retest_v1` uses closed M5 candles with aligned Daily/H4/H1/M15
context. It requires a close crossing a confirmed two-left/two-right swing,
a breakout body at least half its range, and the first retest within six bars.
The retest must reclaim the level with a directional close. The last twenty
M5 bars must be contiguous. Forming candles cannot contribute.

The retest band is max(2 points, 0.1 pre-break ATR). Protection goes beyond
both the retest wick and broken-level band with the existing structural buffer.
The existing geometry adapter requires a nearby quote and an HTF target with
at least 2R before costs. Sell protection accounts for Ask-side exits.
Protection is never reduced to fit account capital. Fixed confidence 0.65 is
an input to shared research gates, not a predicted win probability.

This is a break/retest hypothesis; it does not itself require OB or FVG detection.
Its source hash and rules were frozen before the tick reconstruction labels.

## Evaluation boundaries

`tools/research_structural_retest.py` evaluates every eligible closed M5 bar,
records candidate observations before outcome labels, and reuses the original
shared deterministic replay gates. The original volatility guard, min-lot
sizing, fees, adverse slippage, sessions, loss limits and confluence remain.
The failed calibrated volatility proposal is not used.

Development is October 1–15 UTC; validation is October 15–November 14 UTC.
These are previously inspected retrospective periods, not blind validation.
The existing baseline is reused only after checking its signed receipts,
input hashes, frozen source and current Atlas policy dependency hashes.

Each period must have at least 30 trades across two dates, positive mean net R,
profit factor at least 1.1 (or all wins) and drawdown at most 6R. Passing would
still require independent forward evidence and explicit activation. There is
no automatic promotion or order dispatch. Missing historical visual, news and
macro state means this is not a full recreation of the live pipeline.

Signed protocol, source snapshot, predictions and results are in
`storage/m5_structural_retest_20261116`. The separate prospective calibrated-M5
observer continues under its existing frozen protocol and deadline.

## Completed result

Seven complete candidates were generated. Development had one, rejected by
timing discipline. Validation had six: five rejected by timing discipline and
one by minimum-lot risk sizing (`no_risk_bounded_volume`). Both periods had zero
trades and failed qualification. This does not establish profitability or prove
that rejected candidates were worthwhile trades. The model stays research-only.

The timing gate was deliberately retained. Structural confluence alone is not
enough to establish compatibility with the remaining entry requirements. A new
proposal would need an explicit version and separate evaluation; these outcomes
must not be used to quietly retune this frozen experiment.

The compact durable receipt is `M5_STRUCTURAL_RESULTS_20261116.json`. Source,
protocol and prediction hashes bind the full local artifacts; raw broker/account
data remain in ignored storage. Tests cover both entry directions, forming-bar
exclusion, gap rejection, single-use retests, tick clock and quote ordering,
and rejection of a changed frozen model.
