# Closed-timeframe candidate comparison

Completed a bounded offline comparison of existing closed-confirmation EMA and pullback templates. No new candidate met every predeclared historical requirement, and none was registered for broker trading. The strongest training-selected candidate failed validation after modeled costs.

## Protocol

Three fixed recipes were declared before evaluating outcomes: closed-confirmation EMA on M5, the same template on M15, and the existing M15 pullback template. Parameters come from the repository's existing strategy classes. Research converts ATR price distances into broker points while retaining each template's point floor. Signals use exactly 120 complete chart bars; no parameter grid or threshold search is performed.

Input is the earlier hashed 32,453-bar XAUUSD M1 dataset. Training covers October 12–26 UTC; historical validation covers October 26–November 7; November 9 onward is descriptive recent evidence. These periods were already inspected in previous work. This is exploratory evidence, not a fresh blind holdout or a replay of the full live engine.

Higher-timeframe bars require every consecutive M1 constituent. Partial and missing-minute groups are rejected. Entry is modeled at the M1 open when the signal's chart bar has completed; no signal can enter before that availability timestamp. A real implementation would also incur analysis and dispatch latency. Exit paths use M1 OHLC, stop-first ambiguity, existing R-based break-even/trailing logic and a fixed maximum of sixty minutes. Reported exit timestamps identify the modeled M1 exit bar, not a measured tick fill time.

The first comparison retains the four-M1-bar stale exit. A separately declared second comparison interprets four bars in the strategy timeframe: twenty minutes for M5 and sixty minutes for M15. All holds remain capped at sixty minutes. The second clock was specified before its outcomes were computed. It is not an activation-policy change. Both definitions and outcomes are retained; the tool accepts explicit `--exit-clock m1` or `--exit-clock strategy`.

Recorded spread, the observed fee estimate and hypothetical 1.5-basis-point slippage are charged. The existing research spread ceiling, six-trade daily limit, two-consecutive-loss stop and daily loss stop remain. These isolated hypothetical R outcomes do not establish exact account loss limits or real fills. Selection uses training only: at least thirty cases on two days, positive cost-adjusted mean, PF at least 1.1 (or all wins), and drawdown at most 6R. The same minimum thirty cases applies to historical validation; future evidence remains necessary regardless of historical checks.

## Outcomes

Cells contain mean modeled R followed by sample count. R is initial hypothetical stop risk, not rand profit. Counts across overlapping comparisons must not be combined to pass a requirement.

| Recipe | Stale-exit clock | Training | Historical validation |
| --- | --- | ---: | ---: |
| Closed EMA M5 | M1 | +0.060 (30) | -0.037 (33) |
| Closed EMA M15 | M1 | -0.018 (26) | -0.114 (17) |
| Pullback M15 | M1 | -0.073 (28) | -0.036 (28) |
| Closed EMA M5 | Strategy bars | -0.013 (34) | -0.180 (32) |
| Closed EMA M15 | Strategy bars | -0.106 (26) | -0.058 (21) |
| Pullback M15 | Strategy bars | +0.006 (43) | +0.100 (43) |

The M1-exit-clock M5 EMA was the sole training-qualified selection: PF 1.359, drawdown 1.652R. Its validation PF was 0.855 with negative average return, so it failed despite sufficient sample count. Its validation mean was +0.045R gross and +0.015R after spread/observed fees, before the assumed slippage charge reduced it to -0.037R. That thin margin cannot establish executable profitability while actual request-to-fill measurements remain absent.

With strategy-bar exit timing, M15 pullback had positive means in both historical periods, but its training PF of 1.033 failed the predeclared 1.1 requirement. It was not selected after inspecting the favorable later period. Its five already-inspected recent cases averaged -0.534R, another reason not to infer a reliable edge from the favorable validation window.

No comparison passed the full selection/validation process. No extra paper observer was launched for these rejected hypotheses, and no trading gate was weakened. The existing bounded chart-invention research and seven-day natural-lifecycle observer remain active.

## Reproduction and checks

The reusable offline tool is `tools/closed_timeframe_research.py`. Each run saves its protocol before calculation, including source/dependency hashes, source-manifest and candle hashes, symbol, recipes, costs, periods and exit-clock definition. It freezes the training selection before calculating later-period outcomes and rejects source changes during evaluation. Final local results are in `storage/closed_timeframe_research/final_m1_clock_20261110` and `final_strategy_clock_20261110`; earlier implementation snapshots and metadata-only reproductions are retained locally. All nine mean/sample/trade-path comparisons in the M1-clock metadata clarification matched the original results exactly.

Twenty-two related replay/cost tests passed. They cover closed-bar completeness, fixed past-only windows, future-data isolation, availability-clock validation, M1 entry timing, missing fill paths, phase boundaries, unchanged spread/loss stops and elapsed-time preservation for strategy-bar exits.

The live runtime still responds and the broker/history observer is fresh. A Windows Application Error 1000 query found no Python application crash on November 10. This does not establish the cause of the earlier native fault. No measured broker fills have yet been recorded by the prospective cost collector, and no natural autonomous broker lifecycle is verified. These remain evidence requirements rather than completed outcomes.
