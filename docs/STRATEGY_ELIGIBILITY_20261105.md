# Current strategy eligibility audit

Snapshot: 2026-11-05T13:24:07.875466+00:00

This report calls the existing production eligibility filter without changing it.

| Strategy | Performance filter | Current signal | Reward observations |
|---|---|---|---:|
| ema_crossover | Restricted | sell | 3204 |
| momentum_continuation | Eligible | flat | 2424 |
| pullback_trend | Restricted | flat | 84 |
| gold_micro_impulse | Eligible | flat | 6 |
| gold_breakout_retest | Eligible | flat | 2 |
| gold_liquidity_sweep | Eligible | flat | 3 |
| evolved_rule(fast=18,slow=87,rsi_buy=47.8,rsi_sell=56.9) | Eligible | flat | 2 |
| evolved_mhr_hr | Eligible | flat | 2 |

## Evidence limitation

The allocator increments wins/losses for reward updates. Its code accepts both closed-trade outcomes and open-position feedback; explicitly persisted backtests are another possible input. Each new strategy also starts with one win and one loss as a prior. Legacy counts contain no source tags. They cannot be presented as verified completed-trade counts or attributed cleanly to a data source.

## Next action

Build a separate, source-tagged closed-position performance ledger and compare its eligibility decisions with the legacy filter in shadow mode. Keep current restrictions and risk limits unchanged until the difference is reviewed. Then evaluate actual strategy candidates with cost-aware, outcome-complete evidence and demonstrate a natural demo entry-to-exit lifecycle.

Detailed evidence: `strategy_eligibility_20261105T132419Z.json`.
