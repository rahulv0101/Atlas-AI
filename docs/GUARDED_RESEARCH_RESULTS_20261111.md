# Guarded research results: November 11, 2026

The test framework was repaired and 28 broker-unit comparisons completed. **No variant qualified for forward selection or broker activation.** The result is not a demonstration that live Atlas is profitable, nor a complete reconstruction of its historical decisions.

## Engineering changes

- Live and historical construction share the same strategy inventory, with live order/defaults preserved. All six configured M1 strategies are available to the historical framework.
- The normal backtest command uses isolated storage and cannot reconcile live execution flags, log into another account or accept a live execution override.
- The guarded replay uses Atlas structured conviction and its active-profile effective threshold. Raw strategy confidence is not compared as if it were final conviction.
- Broker-unit quotes, lot steps, sizing limits, current tick-value conversion, recorded spread and per-lot fees replace the old fixed account-return cost model in the new command.
- Declared current and fee/slippage-aware exit variants use conservative stop-first handling, adverse stop gaps and prior-bar-only stop adjustments.
- Frozen training-only selection precedes validation. Independent forward collection can use new post-freeze data without resetting the original experiment or automatically promoting a strategy.
- The acceptance supervisor now reads sleep mode from the persisted `payload` wrapper. Its live deployment reused the original collectors and did not restart the trading worker.

## Study design and scope

The study used the previously inspected 30,288-bar XAUUSD M1 snapshot from October 12 at 15:16 UTC through November 11 at 15:16 UTC. Training ends at November 3 at 01:49 UTC; diagnostic validation follows. **Neither historical period is blind.** Portfolio/allocator state starts fresh in each window.

The corrected v2 research protocol froze on November 11 at **19:25 SAST**. Source, dependency versions, settings, costs, variants, selection rules and data checksums were preserved. An earlier prototype was retired before forward testing because it used raw confidence rather than Atlas conviction. Its signals were reused only after checking identical input/settings, unchanged signal-generation AST and matching Atlas dependencies. Its decisions and outcomes were not reused as evidence.

The captured limits were six trades per day, two consecutive losses, a 0.6% daily loss budget, the configured weekly limit, a 0.01-lot cap and the current pilot's continuation setup family. Risk remaining at entry includes modeled stop loss, fees and declared slippage. Historical conversion/margin and intraminute quotes remain approximate.

Gold Breakout Retest and Gold Liquidity Sweep are in the strategy inventory, but their breakout family is not eligible under the current continuation-only pilot. Their zero eligible cases are not a performance verdict. No execution policy was broadened to admit them.

## Main comparison

The table uses three price points of adverse slippage on each leg, recorded bar spread embedded once in bid/ask execution prices, observed fee evidence and 10,000 units of simulated starting capital per window. Cash is in the configured account currency, ZAR. Current and cost-aware lock variants are separate research paths; live exit parameters remain unchanged.

| Combined strategy selection | Training cases / wins | Training net cash | Training profit factor | Validation cases / wins | Validation net cash | Validation profit factor |
|---|---:|---:|---:|---:|---:|---:|
| Current exit lock | 35 / 4 | -R465.70 | 0.0957 | 21 / 7 | -R116.74 | 0.5019 |
| Cost-aware research lock | 35 / 4 | -R463.71 | 0.0996 | 21 / 7 | -R114.75 | 0.5104 |

Each window is a separate cold-start experiment. These cash results must not be added and presented as a continuous portfolio return. The exit adjustment made only a small improvement and did not establish an edge. Several standalone strategies also lacked thirty eligible cases. None met all training requirements: thirty cases across two dates, positive mean net R, profit factor at least 1.1 (or all wins), and cumulative drawdown no larger than 6R.

The strict evidence replay admitted no modelled trades. It refused 171 otherwise eligible candidates because historical visual, macro and execution evidence was unavailable. Other candidates failed timing, higher-timeframe or pilot-family checks. The diagnostic comparison does not reconstruct full sizing-band, learned-state, promoted-gene or broker-execution history, and retains `full_live_policy_parity=false` throughout.

These figures are not directly comparable with the earlier 6,033-trade legacy backtest: the populations, entry restrictions, position size and cost/path assumptions differ. The earlier and corrected studies both fail to establish a profitable replacement.

## Cost and software checks

Four read-only current broker profit calculations agreed with model tick/volume conversion. Fee evidence covered twelve deals, including manual and diagnostic deals for fees only. Natural slippage calibration remains unavailable.

The earlier labelled two-fill diagnostic was checked independently. Its 34-point recorded quote spread, zero entry price deviation and one-point adverse exit deviation matched the stored price arithmetic. Reconstructing its -R5.79 net result with the new frozen current conversion produced approximately -R5.81: a -R0.019 residual. This is retained as conversion uncertainty. One diagnostic is not representative natural execution evidence.

The final isolated full regression run passed **1,951 tests**. Focused tests additionally exercised the final conviction/profile behavior, frozen forward resume/integrity and explicit UTC ledger formatting. Independent ledger checks covered 722 records across alternative scenarios, with no count, balance, overlap, volume-cap or conviction-threshold errors. Those alternative records are not independent live trades and are never pooled into acceptance counts.

The completed study retains its executed source. Its entry timestamps include UTC offsets; the original v2 exit strings identify UTC-normalized M1 bars. The current serializer emits explicit UTC offsets for both. These are model bar times, not measured tick fill timestamps.

## Operational result and remaining evidence

The updated sign-in supervisor is running. Both original collectors remained active, with the original frozen paper experiment at two first-stage outcomes and zero validation outcomes at the final check. No natural protected broker cycle has been verified. Measured natural fill observations remain zero; two diagnostic fills remain separately labelled.

No new strategy or exit variant was activated, no order was dispatched by the research/audit code, no loss limit was loosened, and no experiment's losing outcomes were reset. The additional research observer correctly reports `no_training_candidate`. A new frozen hypothesis must qualify on training before its thirty-plus-thirty-case forward collection can start.

Exact artifacts are local in `storage/guarded_research/full_v2_20261111`, including `manifest.json`, `report.json`, `selection.json`, `ledger_checks.json`, `recorded_cost_validation.json` and frozen source. The full suite is recorded in `docs/diagnostics/guarded_final_full_tests_20261111`. See [the guarded research workflow](GUARDED_RESEARCH.md) for commands and limitations.
