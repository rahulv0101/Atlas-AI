# Combined SMC model — observer only

The operator requested combining Atlas's SMC-related concepts into one model. `atlas_ai/strategies/smc_composite.py` implements `smc_composite_v1` and the live trader publishes its read-only observation at `status.smc_composite`. The dashboard displays its current stage. Typed and voice explanations use the same Brain v2 strategy knowledge and explicitly identify the observer boundary.

## One explicit sequence

1. **Higher-timeframe confluence:** existing completed-candle D1 → H4 → H1 → M15 directional agreement. This retains the current price-average direction method; it does not claim higher-timeframe institutional order-flow analysis.
2. **Premium/discount:** buy below the midpoint of the H4 recent 20-candle high/low range; sell above it. Entry must remain inside that range. This is an explicit range proxy rather than a discretionary swing-anchored dealing range.
3. **Liquidity sweep:** an M5 candle takes the previous 20 candles' low/high, closes back through it and has a rejection wick occupying at least 42% of its range. Sweeps expire after the bounded recent 12-bar search window.
4. **Confirmed structure:** pivots require two closed candles on both sides and must already be confirmed before the sweep. Two higher highs/higher lows establish bullish prior structure; lower highs/lower lows establish bearish prior structure. Unknown/mixed prior structure cannot qualify. A subsequent close through the opposing swing is BOS when aligned with prior structure, CHOCH when opposing it.
5. **Displacement:** within three bars of the sweep, a directional candle must close through that swing, with body at least 1.25 times the preceding ATR and body/range at least 60%.
6. **Fair value gap:** the displacement is the middle candle of a three-candle gap. Minimum width is the greater of two broker points or 5% of preceding ATR. The third candle must close before a retest can qualify.
7. **Order block and mitigation:** retain the last opposite-direction candle from the sweep neighborhood preceding displacement, using its full high/low as the block. The first later FVG or order-block retest must close with directional rejection and a body/range of at least 35%. A previous gap touch, prior block invalidation or current retest through the setup extreme rejects the setup. This implements an order block's first mitigation, not a separate breaker-block or mitigation-block strategy.
8. **Protection and liquidity target:** stop beyond both the sweep and order-block extreme, with the greater of two points or 10% of preceding ATR as buffer. Short protection includes spread. The nearest opposing D1/H4/H1/M15 recent high/low reference must offer at least 2R **before fees/slippage**. Long entry uses the observed ask; short entry uses bid and its ask-side target accounts for spread. Price distances are converted into broker points explicitly.

The entry reference must remain within 0.25 ATR of the rejection close. Quotes must be no older than 30 seconds and higher-timeframe context no older than 120 seconds. M5 inputs must be closed, ordered, valid and continuous. The detector is deterministic and reads no conversational memory. Its fixed 0.65 research score is not a win probability or an execution threshold.

## Authority and evidence boundaries

The model is deliberately absent from the executable strategy inventory and selection pool. Its candidate cannot reach the allocator, risk sizing or ExecutionGate. It cannot submit orders, replace strategies, change thresholds or promote itself. Existing higher-timeframe confluence and all active trading/risk/execution settings remain unchanged.

OHLC sweeps, blocks and gaps are defined research proxies. They do not reveal actual stop orders, institutional positions or intent. Current quote distances are nominal, before broker stop adjustment, fees and slippage. The 2R check therefore does not establish a cost-adjusted edge.

This implementation observes setups; it does not add a paper-fill/exit collector or claim a completed trading lifecycle. A performance study needs separately sourced historical higher-timeframe data, an untouched validation period, cost-aware sizing/fills and fresh prospective outcomes. Existing M1 frozen experiments remain separate. Their prior results do not validate this new composite.

The current observation, wait reason and qualifying sequence evidence are inspectable through live status. The publication archive's allowed fields include `smc_composite`; the archive supervisor was restarted to capture the field. Archive sampling can miss publications and is not a complete, atomic pre-entry journal.

## Verification

**154 focused tests passed.** Synthetic buy and sell paths verify the complete sequence, confirmed-pivot chronology, forming/future-candle exclusion, stale/missing/mixed input rejection, minimum target distance, broker point conversion, first-mitigation consumption, preserved read-only authority and typed/voice explanations. Existing timeframe, signal, archive and execution-audit tests also passed.

The backend and UI were restarted to load the observer. Operational checks of its published stage, dashboard delivery and typed/voice explanation are recorded in the completion notes. No forced or diagnostic broker trade is part of this change. Software tests do not establish profitability or justify broker activation.

Operational check on 13 November around 20:44 SAST: the observer published a sell-side `premium_discount` wait because price was not in the required upper half of the H4 reference range. Its candidate was null and `broker_eligible=false`. The served dashboard included the new observer label; typed and voice API queries selected the strategy-knowledge domain and stated that the model cannot execute. A subsequent archive read confirmed that composite observations were being captured. Existing paper, natural-lifecycle and penalty-comparison observers remained running. Trigger-candle time, evaluation time and quote time are recorded separately in valid model observations.
