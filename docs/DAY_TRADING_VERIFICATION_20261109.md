# Day-trading controls and verification ? 2026-11-09

> Operator clarification: the user states most or all historical trades were manual. Broker tags, expert reason codes and matching execution messages establish broker activity but do not establish autonomous origin. Treat these trades as manual/unverified for autonomous acceptance. Only fresh guarded decisions from the repaired deployment, with broker-linked lifecycle evidence, may satisfy that check.

## Authorized behavior

The user asked to complete the intraday controls, trade evidence, selectivity analysis and operational checks. This explicitly enables automatic risk-reducing exits on the configured demo account at the existing session cutoff. Entry strategies, timing requirements, risk limits and broker ownership checks remain authoritative. Account-capital sizing is deferred at the user's request.

A separate 15-second watchdog checks the broker independently of the main strategy cycle. The trader also checks before fetching market data. At cutoff, Atlas persists an entry barrier, cancels its pending entries, refreshes broker inventory and closes its positions using explicit position tickets. Only broker readback can confirm flat exposure. Foreign/manual exposure is counted separately and left alone.

The existing session calendar is used without changing its hours: Asia 00:00?07:00 UTC, London 08:00?16:30 Europe/London, New York 09:30?16:00 America/New_York, weekdays with a 10-minute close buffer. The calendar chooses the first matching session during overlaps; its cutoff remains authoritative. Session timezone conversion handles daylight saving independently of broker timestamp conversion. Existing early-close and holiday rules also apply. On 9 November, the New York cutoff begins at approximately 22:50 Johannesburg time (the calendar uses whole minutes).

## Recovery and controls

The separate atomic journal is `storage/automation_state.intraday_exit.json`. A dispatch intent is persisted before each broker mutation. Concurrent controllers share its action lock. Read-only status requests do not wait for that action lock. Restart recovery reconciles outstanding actions against broker inventory; an uncertain response is never blindly retried. A partial close can progress only after fresh inventory confirms a smaller remaining volume. A missed exit obligation persists into the next session until broker-confirmed flat.

The demo identity, ownership, terminal permissions, gate, runtime execution flag, kill switch and sleep controls remain enforced. Account identity is rechecked immediately before native close/cancel dispatch. Disabling execution or stopping the computer can prevent exits; no local program can guarantee broker execution during an outage. Unknown results deliberately require reconciliation/operator attention rather than risking duplicate orders. Corrupt journals and missing inventory block entries and never produce a flat confirmation.

The dashboard reports the latest exit-controller evidence. Flat confirmation older than three minutes is shown as unavailable/stale. Informational questions and API reads do not execute exits.

## Durable evidence and observation

Successful guarded demo entry references are appended and fsynced to an account-scoped decision index. The closed-position ledger and observer combine this index with retained decision events. Manual tests, synthetic broker IDs, unlinked fills, conflicting decision links, incomplete/partial lifecycles and open broker positions do not become verified strategy outcomes. This protects future evidence; missing historical decisions cannot be reconstructed reliably.

`tools/observe_day_trading.py` is read-only and records fresh status, broker inventory, new fills and uniquely linked balanced entry/exit lifecycles. It sends zero orders. Existing fills establish a baseline rather than being counted as new demonstration trades. Machine sleep, shutdown or terminal disconnection interrupt observation and are evidence gaps, not success. A natural setup is required before entry/management/exit can be demonstrated; no forced diagnostic trade is used.

## Filter selectivity findings

Artifact: `docs/baselines/baseline_20261109T190140Z_intraday_cost_sensitivity_20261109.json`.

The retained post-repair sample contains 65 complete timing-blocked hypothetical opportunities and zero executed controls. Before costs, 30 won and 35 lost; average outcome was approximately -0.109 R. Using recorded spread plus configured hypothetical slippage, 17 won and 48 lost; average outcome was approximately -1.074 R. The original fixed cost model was more pessimistic (-1.960 R average).

These are correlated, observational hypothetical trades, not portfolio returns. Commissions and actual slippage are unproven; there is no executed comparison group. They do not establish profitability or justify automatically loosening entry filters. Both gross and cost sensitivity results are preserved so the cost assumption is inspectable.

## Acceptance limits

Software tests can verify specific controls and failure behavior. They cannot guarantee daily income, prove a profitable strategy, recover absent history, explain the earlier native Python crash conclusively, or substitute for a naturally completed broker trade and sustained observation. R1,000 remains an objective, not a guaranteed daily payout. The prior native crash remains unresolved; the audit runner avoids the implicated periodic diagnostic stack-dump path while preserving normal crash reporting.

## Verified deployment

- Full non-backtest suite: 1,740 passed in 251 seconds. Separate backtest suite: 12 passed in 220 seconds. Final dashboard/account guards: 123 passed. Deduplicated across these runs: **1,754 distinct passing test cases**, zero failures/errors. These runs completed without a native fault; that does not establish the cause of the earlier crash.
- After a fresh matching-demo/zero-position/zero-pending check, the prior backend and frontend stopped cleanly. The normal wake launcher completed with `SUCCESS / backend_healthy_desktop_ready` at 19:28 UTC. New backend PID 31148; desktop ready; runtime execution enabled on demo.
- The live watchdog and compact API both report fresh broker-confirmed flat Atlas exposure. Independent 15-second checks are running. No diagnostic entry, close or cancellation was sent during deployment because there was no exposure.
- Browser verification: no page errors, successful compact-status polls, functioning view tabs/refresh, and no horizontal overflow at widths 1440, 768 and 390. The Safety card shows the fresh exit confirmation. All non-GET API requests were intercepted during the isolated browser check.
- Protective settings remain 0.5% risk per trade, 3% daily/6% weekly drawdown limits, the existing 0.01-lot guarded-demo cap, Gemini advisory only, and confirmed-demo-position performance evidence. The R1,000 daily objective remains advisory.

## Ongoing observation

The 24-hour observer started at 19:27:53 UTC / 21:27:53 Johannesburg time on 9 November. Actual worker PID: 1772 (venv launcher PID 24304). Expected finish: approximately 21:27 Johannesburg time on 10 November, provided the process and machine remain running.

At the final verification it had two healthy samples, zero stale-status samples, zero broker-unavailable samples, zero pending orders/positions, and zero verified natural trade cycles. Observation is **running, not complete**. No naturally completed broker trade has yet been demonstrated. This observer performs no broker mutations and does not guarantee a trade will occur.

Evidence:
- `docs/diagnostics/day_trader_test_summary_20261109.json`
- `docs/diagnostics/day_trader_final_runtime_20261109.json`
- `docs/diagnostics/day_trader_ui_smoke_20261109.json`
- `docs/diagnostics/day_trader_observation_20261109.summary.json` (continuously updated)
- `docs/diagnostics/day_trader_observation_20261109.jsonl` (read-only samples)

Remaining acceptance work is to review this completed observation and any naturally selected trades for entry, management, exit, costs, strategy attribution and recurring blockers. Strategy profitability, guaranteed daily income and the earlier native crash remain unproven/unresolved. Account-capital sizing remains deferred.
