# Broker-aware historical and forward research

The standard backtest command now starts isolated guarded research:

```powershell
.venv\Scripts\python.exe -m atlas_ai.main backtest
```

It reads the matching configured demo terminal for M1 history, symbol specifications and fees. It does not log into another account, reconcile execution-mode flags, mutate the live allocator or send an order. A live execution override is rejected. Existing live settings and the original frozen M15/H1 paper experiment remain separate.

To audit an existing candle snapshot:

```powershell
.venv\Scripts\python.exe tools/guarded_research_audit.py --source storage/system_backtest/20261111_30d/candles.csv --output storage/guarded_research/new_run
```

The output directory must be new. Source, dependency versions, settings without credentials, broker specifications, data checksum, variants, selection rule and future observation deadline are frozen before evaluation.

## Shared behavior and explicit boundaries

Live Atlas and the legacy backtester now construct their strategy inventory from the same factory. Live construction order and class defaults are preserved. All six configured M1 strategies are available, including Gold Micro Impulse and Gold Liquidity Sweep, which the old historical engine omitted.

The guarded replay reuses Atlas's signal-generation filters, contextual ranking, structured conviction calculation, active-profile confidence cap, higher-timeframe bias arithmetic, timing checks, risk manager, session calendar and sizing functions. Higher-timeframe groups must be complete before their values become available. A raw strategy score is never substituted for final Atlas conviction.

Entry restrictions include the captured pilot setup family, lot cap, daily trade and loss-streak limits, daily loss budget, weekly loss limit, spread, broker minimum/step, model margin and the remaining day/week loss budget. One position is modeled at a time. The model reserves stop risk plus fees and slippage before entry; this conservative reservation is not a claim of exact historical gate sequencing.

Historical visual captures, macro state, adaptive lessons, promoted evolved/chromosome versions, meta-model state, full sizing-band logic, execution clusters and past operator controls are not reconstructed. A strict evidence lane refuses to invent them. Every research result keeps `full_live_policy_parity=false`, `broker_eligible=false` and zero orders.

The normal guarded-demo worker was not restarted to activate research settings. The factory extraction preserves its existing strategy behavior; experimental exit changes never modify live stops or parameters.

## Costs and exits

Buys enter at reconstructed ask and exit on bid; sells enter at bid and exit on reconstructed ask. The historical bar's recorded spread is embedded once in these quotes. Cash P&L uses quantity, tick size and separate profit/loss tick values. Commission and fees are charged per traded lot. Current symbol conversion and margin are frozen estimates, not historical currency/leverage reconstructions. Quotes within a minute and actual fills remain unknown.

Four predeclared variants compare the existing break-even lock and a fee/slippage-aware research lock, each at zero or three points of adverse slippage per side. Zero is a baseline assumption, not a measured estimate. The three-point case is a declared sensitivity, not a maximum possible loss or fill guarantee. Natural slippage remains uncalibrated.

Stops take precedence when both stop and target occur in a candle. Gaps through a stop fill at the worse opening quote. Break-even/trailing levels use only earlier completed bars, and the session buffer can shorten a hold. Incomplete exit horizons do not count as completed forward outcomes. These are M1 management approximations, not exact reproductions of every live position-management event.

Read-only `order_calc_profit` checks validate current unit conversion on both sides. The recorded two-fill demo diagnostic is also crosschecked for spread and signed price differences; it remains excluded from natural execution proof. A residual from current versus historical currency conversion is retained rather than forced to zero.

## Selection and new evidence

Each exit/slippage variant is evaluated for every strategy separately and for combined selection: 28 comparisons. The first 70% of the already inspected historical snapshot is training; the later 30% is diagnostic validation. Neither is labelled blind.

Training qualification requires at least 30 completed cases across two dates, positive mean net R, profit factor at least 1.1 (or all wins) and drawdown no larger than 6R. Selection uses only training, ranks by mean net R, and resolves ties lexically. The chosen research hypothesis and checksum are saved before validation is evaluated. No qualifying training result means no candidate is forced into forward testing.

When a candidate qualifies, a separate read-only observer uses only new outcomes after the declared future freeze. It reads the existing collector's closed-candle journal and never accesses the broker. The original frozen experiment is not rewritten or reset. First and subsequent 30-case forward stages are independent and retain their losses.

The new observer checks frozen source/environment/settings, immutable candle prefixes and artifact hashes, and resumes its candidate cache incrementally. The acceptance supervisor reuses healthy collectors, respects persisted sleep state, limits restarts and enforces the existing deadline. Failed or completed evidence requires review; no automatic trading promotion exists.

The source-cache reuse option verifies identical input/settings, unchanged signal-generation AST and all Atlas signal dependencies. It may reuse signals after a decision-rule correction; it never carries decisions or outcomes from a retired experiment into a new one.
