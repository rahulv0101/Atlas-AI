# SMC framework v4: evidence-led setup routing

The operator requested resolving the repeated zero-signal result. This work first captured actual late-stage failures, then froze one new framework hypothesis. It does not enable broker orders or change the executable strategy allowlist or risk limits.

## What the real traces showed

`tools/trace_smc_setups.py` replays verified native timeframe inputs and captures full decision inputs and retest callbacks for late-stage windows. It checks that instrumentation returns exactly the uninstrumented v3 output. The local result is `storage/audits/smc_retest_trace_20261113`.

The 17 late-stage windows represented repeated observations, not 17 independent trades:

- Seven were still waiting for a first zone touch. In the inspected May example, bearish displacement moved away from the FVG/order block without returning during the setup window.
- Three had breached their setup extreme. These are invalidations, not permission to remove a stop constraint.
- Seven reported a previous confirmation. Inspecting the earlier confirmation times found cases where the current-price reaction-zone requirement rejected the setup first; a later context check then saw that confirmation as already consumed.

This exposed two design issues: every continuation unnecessarily depended on a preceding liquidity sweep, and setup-zone evidence was checked at the confirmed entry price rather than retained from the preceding pullback. Earlier changes to retest confirmation alone could not resolve those issues.

## One framework, two explicit families

Both families retain closed D1/H4 directional agreement, valid H1/M15 evidence, countertrend pullback evidence and a reaction-zone reference. The reference is the relevant extreme among the latest 12 completed M5 candles, evaluated against the currently available closed H1/M15 ranges. It is explicitly recorded with its candle timestamp. This is a retrospective setup feature known at the decision time; it is not a claim that an institutional order or pre-existing limit order was observed there.

The actual entry quote must still lie inside the H4 reference range and within 0.25 ATR of the latest rejection close. It need not remain in the local range's favorable half after confirmation has moved price away from the pullback.

1. **Sweep setup:** the existing reclaimed liquidity sweep, confirmed structure break/shift, displacement, FVG plus opposite-candle order-block formation and first-zone confirmation. V3's invalidation, expiry, previous-confirmation and second-visit controls remain.
2. **BOS continuation:** pre-existing confirmed M5 structure must align with D1/H4. A fresh close through the last confirmed swing must have directional body at least 1.25 preceding ATR and body/range at least 60%. The setup must form a valid three-candle FVG or have a preceding opposite-candle order block; at least one entry zone is required. The existing bounded first-retest/rejection controls apply. This family does not require a preceding liquidity sweep.

A complete sweep setup has fixed priority; otherwise the continuation family is checked. No learned or outcome-based ranking is introduced. The observer reports family and per-family failure status. Stable setup IDs prevent reissuing the same sweep or BOS across different confirmation candles.

Both families use one shared protection/target geometry function: structural extreme plus the existing buffer, broker-point conversion, correct quote sides, nearest opposing higher-timeframe reference and at least 2R before fees/slippage. Historical and forward paper sizing, minimum-volume, margin, session, loss and frequency constraints remain unchanged. The fixed 0.65 research score is not a win probability or a raised live confidence threshold.

## Frozen protocol and preserved runs

The active run is `storage/smc_validation/framework_v4_fast_20261113`. It reuses the verified 180-day native D1/H4/H1/M15/M5 inputs; previous historical inspection is explicitly recorded. There is no new blind holdout claim. All old model manifests, code, cases and results remain preserved. The v3 paper worker was retired without a pending simulated position and with zero completed cases.

`framework_v4_20261113` is preserved as input-only preparation. Before any v4 historical outcomes were computed, the final snapshot replaced repeated DataFrame pivot scans with equivalent scalar comparisons. Randomized closed-input tests compare the same two-left/two-right pivot arithmetic, strict comparisons, last swings and bias. No threshold, lookback or risk rule changes in that optimization.

The active manifest freezes the model, source, inputs, safe settings, costs, review rules and unchanged 10 December acceptance deadline. The supervisor resumes its frozen paper worker locally without Codex credits. The model remains absent from executable strategy inventory, and `order_send` is disabled in the worker. A candidate is not broker approval.

## Verification and practical limits

**120 focused checks passed**, covering both long/short families, valid continuations without an invented sweep, preserved sweep priority and protection, pullback-location timing, unavailable context, absent BOS, future-candle exclusion, target minimums, pivot equivalence, research-only model selection, supervision and typed/voice answers.

The backend and native UI were restarted. Both the main observer and paper status identified `smc_framework_v4`; the dashboard's v4 label explains the alternative setup families separately from the active trader's execution gate. The forward worker had a fresh `collecting_paper` report and no pending simulated position during the operational check.

Historical labels remain nominal, cost-aware simulations with lagged bar-spread proxies and current reference currency/fees. Full historical visual, macro, final-conviction and ExecutionGate parity are not established. Neither simulated entries nor software tests prove profitability, actual protection or a natural broker lifecycle. Any demo activation must still be justified by the required evidence and policy checks.

## Completed historical result

The frozen six-month replay generated **two complete candidate evaluations**. One passed nominal sizing and produced a simulated BOS-continuation trade on **10 July 2026 at 18:20 UTC**. It used the broker minimum 0.01 lot, had modeled initial risk **R44.72**, and exited by simulated stop loss for **−R45.21 (−1.011R)** after modeled costs. These are historical simulation amounts, not an actual account loss or observed broker fill.

The other complete signal failed the minimum-volume risk/margin check. Static lot and margin constraints did not bind: minimum volume and size cap were both 0.01 and modeled minimum-volume margin was R131.28 against a nominal balance near R10,000. The limiting part was the frozen 0.5% risk budget, approximately R50, rather than a missing signal. No risk fraction or lot cap was raised.

Development had one trade and one loss; validation and holdout had zero trades. **All three periods failed qualification**. One losing trade does not establish a reliable loss rate or prove the strategy unprofitable; it also supplies no evidence for a profitable edge. The observed activity is insufficient for a validated frequent day-trading strategy.

Reported window counts were: 7,371 continuity exclusions; 10,029 session/buffer exclusions; 23 split-boundary purges; 8,588 D1/H4 direction rejections; 2,272 setup-location rejections; five absent pullback contexts; 7,153 without aligned BOS/displacement; 147 awaiting or rejecting continuation retests; five failing target/quote geometry; two complete candidates; one sizing rejection; and 12 overlapping-position windows. These categories reflect the router's final reported branch and are not counts of independent market opportunities. Per-family status is retained in model observations.

This resolves the implementation's all-or-nothing zero-signal behavior and preserves the earlier trace evidence. It does **not** resolve the larger lack of a qualified trading edge. The separately supervised forward paper run remains active with a new checkpoint and no automatic broker activation. At completion its counters were still 0/30 + 0/30 with no pending simulated position. No actual broker order was placed by this model.
