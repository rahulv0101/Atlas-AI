# Current M5 policy backtest

The corrected 30-day run is `storage/m5_system_backtest_20261114_v3`. A portable result summary is in [M5_SYSTEM_BACKTEST_20261114.json](M5_SYSTEM_BACKTEST_20261114.json). Local inputs, frozen source, settings without credentials, candidates and reports have checksums; candidates were saved before outcomes. Their checksums and all five native input files were verified after completion.

The replay includes all six currently enabled strategies: EMA crossover, momentum continuation, trend pullback, gold micro impulse, gold breakout retest and gold liquidity sweep. It uses native D1/H4/H1/M15 closed candles and configured M5 entries. Existing all-four confluence is retained. Proposed observer-only SMC models remain separate and inactive for execution.

The diagnostic combined portfolio produced **10 simulated trades, 2 wins and 8 losses (20% win rate)**, net **-R94.06 (-0.94%)** from nominal R10,000. Profit factor was **0.345**, maximum nominal equity drawdown **0.94%**, and mean net outcome **-0.532R**. This small losing sample does not qualify an edge. It is not a forecast of account performance.

The replay shares signal generation/gating, strategy filtering, contextual selection, top-down entry confluence, timing discipline, volatility protection, conviction thresholds, session limits, loss limits, risk sizing, lot caps, margin checks and the existing stop-first historical position simulator. The assumed execution model uses next M5 open, prior completed-bar spread, observed reference fees and 3 points of adverse slippage per side. Current contract/currency/margin values approximate historical costs. One modelled position is allowed at a time.

The diagnostic lane's main sequential rejections were higher-timeframe confluence (3,752), timing discipline (859), outside active session (629), consecutive-loss cap (290), close buffer (182), pilot setup family (39), open buffer (33), and volatility protection (2). These counts depend on preceding gates and portfolio state; they are not independent missed profitable opportunities.

The strict lane produced **zero trades**: 10 otherwise surviving opportunities lacked reconstructed historical visual/macro/execution evidence. Screenshots, Gemini, external news/macro state, learned model versions and actual broker acknowledgements/fills are unavailable. The replay does not reproduce the entire live pipeline, cannot prove a protected broker lifecycle and sent no orders. The diagnostic and strict lanes evolve different portfolio state, so their later rejection counts differ.

Two earlier attempts are retained: the first failed on a progress-callback argument; the second omitted the inventory's M5 top-down flag and covered only three strategies. Neither is the authoritative six-strategy result. The corrected third run completed both lanes. No model was promoted or risk limit relaxed.

The default `python -m atlas_ai.main backtest` now routes configured M5/top-down operation to this native-history runner instead of forcing M1. A bounded manual invocation is:

```powershell
.venv\Scripts\python.exe -m tools.m5_system_backtest --output storage\m5_system_backtest_NEW_ID --days 30
```

Each run requires a new directory and configured matching demo connection for read-only history and cost evidence. Order dispatch is denied, and learning writes stay isolated. Existing prospective observation pointers are unchanged.

User-facing M1 assumptions were removed from the dashboard timing summary, setup explanations, lesson templates, teaching guidance and general readiness knowledge. The timing summary uses the observed/current timeframe; absent evidence remains unspecified. Genuine dated M1 historical examples and internal compatibility identifiers remain intact. Strategy/risk/execution rules are unchanged.

Validation: **125 focused regression checks passed** (124 in the combined run, plus one newly added M5 execution-interval check). Coverage includes native closed-candle evidence, no single-frame fallback, matching M5 gold-strategy inventory, five-minute entry/execution intervals, 12-bar/60-minute horizon, confluence rejection before decision synthesis, backtest entrypoint safety, dashboard timeframe labels, lesson wording, knowledge relevance and typed/voice continuity. This is focused regression coverage, not a new full-suite run.
