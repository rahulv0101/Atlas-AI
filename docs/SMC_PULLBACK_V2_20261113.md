# SMC pullback v2 — separate research hypothesis

The operator requested correcting the conflict found in the original combined model. `smc_pullback_v2` changes the context roles while sharing the existing M5 sequence detector. It remains an observer and paper model, absent from the executable strategy inventory. Existing trader/risk/execution settings are unchanged.

## Corrected context roles

- **D1 and H4:** both must agree on buy or sell direction using closed-candle evidence. Missing, neutral or conflicting direction blocks the setup.
- **H1 and M15:** both must supply valid closed data and reference ranges. Their directional biases may oppose D1/H4 during a pullback; neutral lower-timeframe bias is also allowed. At least one of the two must show a countertrend close change within its latest six completed closes.
- **Reaction location:** entry must be inside the H4 recent range. The previous blanket H4-midpoint veto is replaced with a local reaction zone: below the midpoint of an H1 or M15 range for buys, above it for sells, while inside the selected local range. The range convention remains the recent 20 completed candles; it is not discretionary swing anchoring.
- **M5 entry:** the original reclaimed liquidity sweep, previously confirmed structure, displacement, FVG, opposite-candle order block, first retest, quote proximity, protection and minimum 2R target rules are retained. The new context does not create an entry without that sequence.

This explicitly allows a lower-timeframe pullback against a higher-timeframe trend. It does not require a pullback to coexist with four matching directional averages. OHLC proxies do not establish institutional intent or resting order locations.

## Version separation and provenance

The failed original remains at `storage/smc_validation/frozen_20261113_v2`, with its original manifest, source, inputs, zero-trade history and checkpoint preserved. Its paper worker was retired with zero completed cases and no pending simulated position; a separate retirement receipt records that fact. The original detector's default context behavior is preserved by regression tests.

The revised run is `storage/smc_validation/pullback_v2_20261113`. Its signed manifest explicitly selects `smc_pullback_v2`. Input reuse verifies all five native timeframe CSV hashes and copies them into the new run. The historical period is reused after the earlier diagnostic; no split is described as fresh, blind evidence for this revision. New forward cases can only start after this revision's own freeze and use a separate checkpoint.

Model selection accepts only the two explicit built-in research IDs. It cannot import an arbitrary strategy from a runtime string, change the executable allowlist or enable broker orders. The live observer selects the same signed model ID as the paper worker. The dashboard identifies the observer's version separately from the active trader's four-timeframe confluence gate.

The historical loop caches context only within each 15-minute bucket, updating the evaluation timestamp per M5 decision. All native higher-timeframe closing boundaries used here fall on those boundaries. A regression test compares the cached path with direct closed-candle collection. This is a computation optimization, not a different context policy or future-candle shortcut.

## Verification

**102 focused tests passed**, including:

- Synthetic long and short complete setups with opposing H1 and neutral M15 context.
- Local reaction zones qualifying when the old H4 midpoint would reject the setup.
- D1/H4 conflict, missing lower-timeframe evidence, absent pullback, absent local zone and incomplete M5 trigger remaining blocked.
- Forming/future/stale evidence and preserved original model behavior.
- Explicit frozen model selection, absence from executable inventory, supervision, research reporting and typed/voice knowledge.

The backend and native UI were restarted. Live status and the paper worker both identified `smc_pullback_v2`, the worker had a fresh `collecting_paper` status, and the dashboard served the versioned observer label. A spoken explanation correctly reported D1/H4 direction, H1/M15 pullback zones and the M5 sequence, with no broker authority. At the first operational check the observer was waiting for an H1/M15 reaction zone and had no candidate or pending paper position.

The six-month replay uses the same costs, nominal sizing, session/risk checks and review thresholds as the prior validation. Revised historical results are diagnostic. Broker activation still requires adequate evidence and a bounded policy review; neither software tests nor a change in candidate count establishes a profitable edge.

## Completed replay and remaining limitation

The revised model was frozen at **21:18 SAST on 13 November**. It reused the verified historical interval **17 May 18:55 UTC through 13 November 18:55 UTC**. All three retrospective periods again recorded zero qualifying trades; mean return and profit factor remain undefined and historical review failed. This is not a zero-percent estimated win rate.

The context correction allowed **6,034** decision windows to reach the remaining M5 sequence, compared with **80** in the original run. These are overlapping decision windows, not independent setups or trades. It demonstrates the intended removal of the context conflict, not improved trading returns.

| Revised reported result | Windows |
|---|---:|
| Input/outcome continuity gap | 7,371 |
| Session/close buffer | 10,035 |
| Split-boundary purge | 23 |
| D1/H4 agreement missing | 8,588 |
| Local setup location rejected | 3,551 |
| Pullback context absent | 5 |
| No reclaimed M5 sweep | 4,418 |
| Confirmed pre-sweep structure missing | 572 |
| Displacement/structure shift absent | 1,027 |
| Setup previously mitigated/invalidated | 10 |
| First-retest/rejection conditions absent | 7 |

The remaining bottleneck is the full M5 sequence, not the original demand for four matching timeframe directions plus an H4 midpoint. No M5 thresholds or risk limits were relaxed after these results. The revision remains a research hypothesis with zero completed forward cases at this audit, and has not qualified for broker activation. Further entry-sequence research needs an explicitly separate experiment and fresh evidence.
