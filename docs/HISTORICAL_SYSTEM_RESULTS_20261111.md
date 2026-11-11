# Historical Atlas audit: November 11, 2026

The available historical strategy engine lost money in the completed core run. This is a research result under that engine's assumptions, not a reconstruction of live Atlas account performance or a forecast.

## Core result

| Measure | Result |
|---|---:|
| Instrument | XAUUSD |
| Requested interval (UTC) | October 12, 2026 15:16 through November 11, 2026 15:16 |
| Closed M1 bars | 30,288 |
| Simulated trades | 6,033 |
| Wins / losses | 2,436 / 3,597 |
| Win rate | 40.38% |
| Profit factor after configured model costs | 0.9884 |
| Compounded simulated return | -25.93% |
| Maximum simulated equity drawdown | 62.65% |
| Positive / negative exit-date groups | 12 / 15 |

The model starts with 10,000 units of simulated capital. It uses a 0.5% account-risk fraction and subtracts fixed model costs of 3 account-return basis points for spread plus 1.5 for slippage per trade. These are not costs calibrated from natural fills. It applies its existing break-even, trailing, stale and maximum-hold exit simulation, research confidence threshold of 0.5, fresh allocator, exploration and configured evolved-strategy research.

The core has four enabled built-in strategies: EMA Crossover, Gold Breakout Retest, Momentum Continuation and Trend Pullback. It also evaluates its research-generated evolved rule. The two other enabled live strategies, Gold Micro Impulse and Gold Liquidity Sweep, are absent from this historical engine's strategy inventory.

An independent ledger check reproduced the compounded return and maximum drawdown, matched the wins/losses and trade count, found no overlapping core entries or invalid signal/entry/exit ordering, and verified the candle checksum and unchanged source hashes. Daily groups above compound trades by exit date; they do not reconstruct floating intraday exposure.

## What these figures do not establish

This is not full live-policy parity. The core does not replay every live session, daily/weekly loss, sizing, higher-timeframe, performance, visual, macro or execution gate. In particular, the 62.65% drawdown is not a claim that guarded live Atlas would continue trading through its existing risk limits. The run reports what the historical engine currently does.

Costs are model assumptions, bar-path stop/target order is inferred from candle direction, current parameters are replayed on previously inspected history, and allocator state starts fresh. The result neither proves a profitable edge nor completes the natural broker entry/protection/exit acceptance check. It also cannot replace either frozen prospective thirty-case stage. No strategy, risk setting, live allocator or experimental parameter was changed.

## Timing-filter diagnostic and sensitivity

The separate timing replay admitted **96 candidates** and blocked **7,956** after its pre-timing research filters. This is not the same allocator sequence as the core backtest, and hypothetical timing paths can overlap. The replay did not relax any timing rules.

| Fixed recorded timing-candidate stream | Cases | Mean R | Profit factor | Maximum cumulative drawdown R |
|---|---:|---:|---:|---:|
| Original gross outcomes | 96 | +0.1054 | 1.2064 | 14.65 |
| Subtract existing fixed model costs | 96 | +0.0154 | 1.0275 | 18.43 |
| Costs plus stop-first ambiguous candles | 96 | -0.0368 | 0.9355 | 21.22 |
| Costs, stop-first, greedy nonoverlapping subset | 95 | -0.0515 | 0.9107 | 21.22 |

Model costs correspond to 0.09R at the configured risk fraction. The independent candle-direction simulator reproduced all 96 original gross outcomes without a mismatch. Removing one overlapping entry and changing the intrabar assumption did not regenerate allocator choices; these are sensitivities of a fixed recorded stream, not full alternative portfolio reruns. They do not apply all live risk caps or establish calibrated real execution costs.

The apparently positive gross timing result is therefore not robust to the tested cost and intrabar assumptions. Neither this diagnostic nor the loss-making core result qualifies a strategy for activation.

## Software validation and artifacts

The isolated complete regression run passed **1,928 tests** in approximately 714 seconds, without a native crash during that run. It includes the historical-runner isolation tests, replay behavior, account/risk/session gates and lifecycle evidence checks. A final **19-test focused run** passed after hardening the audit launcher and adding reproducible sensitivity reporting. Passing tests do not demonstrate profitability.

The exact candle snapshot, checksum, source hashes, executed runner snapshot, policy summary, full core trade list and timing samples are local in `storage/system_backtest/20261111_30d`. `core_consistency.json` contains ledger checks and `timing_sensitivity.json` contains the independent sensitivity calculation. The reusable sensitivity function exactly reproduced those calculations. Test artifacts are local in `docs/diagnostics/full_system_backtest_tests_20261111` and `docs/diagnostics/historical_audit_final_20261111.xml`.

The audit completed with zero order dispatches. The live backend and the two original forward collectors remained running. Their evidence was neither reset nor promoted. The actual natural protected broker lifecycle and the two prospective thirty-case stages remain pending.

See [the reproducible audit workflow](HISTORICAL_SYSTEM_AUDIT.md) for commands and coverage limitations.
