# No-trade follow-up ? 9 November 2026

> Operator clarification: the user states most or all historical trades were manual. Broker tags, expert reason codes and matching execution messages establish broker activity but do not establish autonomous origin. Treat these trades as manual/unverified for autonomous acceptance. Only fresh guarded decisions from the repaired deployment, with broker-linked lifecycle evidence, may satisfy that check.

## Finding

Atlas has historical broker executions on the currently configured demo account. This does **not** establish real-money trading, profitable performance, or a naturally completed trade by the newly repaired deployment. The concern about recent inactivity is supported by the retained history.

The broker query covered 1 January 2020 through the current time, subject to broker retention. Identity was checked against the exact configured demo account before and after the query. This audit sent no orders and changed no strategy, risk or execution policy.

## Historical evidence

- 158 broker entry fills match the configured symbol/magic and Atlas comment prefix. The broker labels all 158 as expert/programmatic entries.
- 94 have legacy Atlas identification without reliable strategy attribution; 63 have strategy tags without the current strict decision provenance; one is explicitly a manual test.
- The latest non-test Atlas-tagged entry is 19 May 2026 at 16:06:59 UTC. The latest Atlas-tagged entry overall is the manual test on 3 September at 11:37:33 UTC.
- Across 3,131 retained archive files plus the current journal, 145 historical records say Executed. 51 contain positive numeric broker references, and **all 51 match actual Atlas-tagged broker entry fills** by order/deal reference. The latest such exact match is 13 May 2026.
- The remaining Executed records lack adequate references; a success message alone is not fill confirmation. These historical records do not meet today's strict guarded decision schema and were not automatically promoted into live performance evidence.
- The missing 261,418,685-byte historical event object remains unrecovered. Missing data prevents a complete lifetime reconstruction. These findings apply to this configured demo account; they do not establish activity on other accounts.

## Current inactivity

At the retained-log snapshot (19:34 UTC), 9 November contains 649 chosen-status records: 468 HOLD and 181 blocked. The blocks comprise 163 timing and 18 higher-timeframe conflicts. These are logged records, not independent opportunities. An earlier bounded current-journal read split the 468 holds into 425 no-directional-signal and 43 low-confidence messages.

The live snapshots show two recurring paths:

1. EMA supplies a weak directional candidate that is flattened by the existing low-energy filter; the other seven eligible strategies return flat. No entry reaches broker submission.
2. EMA remains directional but fails timing requirements: mid-range location, weak M1 momentum, and insufficient visual confirmation. A recent conviction of 0.54 is also below the separate 0.55 guarded-demo automatic approval floor; clearing timing alone would not authorize that candidate.

Startup, demo account connectivity and the independent exit monitor are healthy. Current non-execution is observed before broker submission, rather than a demonstrated order-send rejection. This does not prove no latent execution defect exists; the repaired version still needs a natural end-to-end trade.

Real-money execution remains disabled; the account is demo. The active observer has no verified natural trade cycle so far. It remains running with healthy samples and sends no broker orders. A few minutes of monitoring cannot establish full-session behavior or profitability.

## Required follow-through

Complete and review the ongoing observation, preserving rejected candidate evidence and any natural order/fill/management/exit links. Evaluate strategy opportunity frequency and filter selectivity over representative sessions, including costs. Existing offline results do not justify blindly removing timing/risk checks. Any proposed entry-policy change must be concrete, tested and explicit under AGENTS.md.

## Evidence

- `docs/diagnostics/no_trade_followup_broker_20261109.json`
- `docs/diagnostics/no_trade_followup_execution_matches_20261109.json`
- `docs/diagnostics/no_trade_followup_historical_refs_20261109.json`
- `docs/diagnostics/no_trade_followup_pipeline_20261109.json`
- `docs/diagnostics/no_trade_followup_latest_status_20261109.json`
- `docs/diagnostics/no_trade_followup_summary_20261109.json`
- `docs/diagnostics/day_trader_observation_20261109.summary.json` (ongoing)
