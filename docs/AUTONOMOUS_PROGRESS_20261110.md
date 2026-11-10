# Autonomous strategy work and overnight recovery ? 10 November 2026

## What is implemented

- Bounded candle-driven strategy invention and mutation, historical train/holdout tests, immutable dataset snapshots and later frozen-rule forward paper evaluation.
- Research-only operation: no generated candidate can promote itself into broker trading or write arbitrary strategy code. Existing demo strategy/risk/execution gates remain authoritative.
- Correct ATR price-distance to broker-point conversion in generated strategies, with matching point conversion in the legacy shadow consumer.
- Autonomous broker acceptance requires a fresh guarded decision, actual entry fill, observed valid protective SL/TP, correctly directed/sequenced balanced exits, and broker-flat confirmation. Manual and forced tests do not satisfy it.
- All six trader runtime writers update their own fields atomically. A stale trader snapshot can no longer restore starting state or overwrite newer execution controls.

## What happened overnight

The normal launcher completed successfully and that completion remained persisted across subsequent cycles. The observer and research worker later encountered Windows reader/file-replacement conflicts. The observer stopped after 592 samples at 23:39:31 SAST on 9 November. The research report last updated around 02:56 SAST on 10 November; its failure-report write also encountered a lock and the thread exited. The backend and its fresh trading heartbeat continued running.

These interruptions mean the old observation did **not** complete a healthy 24-hour run. The interval from the observer's last sample to its replacement is an explicit evidence gap. Old summaries and process logs are preserved and the observer is marked failed, rather than left appearing continuously running.

The broker was queried independently for the entire window from 22:00 SAST on 9 November through the recovery check on 10 November. It returned **zero trade fills**, zero open positions, zero pending orders and zero durable autonomous entry decisions on the exact configured demo account. The conclusion of no new autonomous trade is therefore supported by broker history, not an assumption about the missing observer samples.

## Persistence repair

A shared atomic JSON writer now uses unique temporary files, fsync, and bounded retry for transient Windows replacement errors. It preserves the previous valid file when replacement remains unavailable; it never truncates the target as a fallback. Research, observation, intraday exit state and the closed-position ledger use it. Event-journal rotation also retries transient replacement conflicts.

The observer records publication failures independently of broker connection failures and continues sampling. The research worker survives a failed attempt to publish its own error report and retries the next cycle. The dashboard marks stale research heartbeats explicitly, as it already does for stale broker-lifecycle evidence.

Regression cases cover transient and persistent reader locks, old-file preservation, invalid JSON numbers, observer publication failures, and survival after a research error-report failure. The focused persistence/control/evidence suite passed 183 cases; store/event checks passed 33. Across the completed full audit, backtest and final targeted runs there are **1,777 distinct passing cases**. This does not prove profitability or eliminate the need for sustained observation.

## Recovery and current acceptance

The backend/frontend were reloaded through the normal launcher after exact matching-demo and zero-exposure checks. The replacement observer began at approximately 07:27:27 SAST on 10 November, polls every ten seconds, and sends no orders. Its 24-hour target runs into 11 November if the computer/process remains running. The old interrupted segment is retained separately.

The autonomous broker lifecycle remains **awaiting a qualifying natural entry**. A manual order, synthetic replay or paper result will not be relabelled as broker proof. Candidate research can continue while this acceptance condition remains pending.

## Evidence

- `docs/diagnostics/autonomous_final_system_20261109/tests.xml` ? 1,760 broad cases passed.
- `docs/diagnostics/autonomous_backtest_20261109/tests.xml` ? 12 backtest cases passed.
- `docs/diagnostics/overnight_persistence_repair_20261110.xml`
- `docs/diagnostics/overnight_event_rotation_repair_20261110.xml`
- `docs/diagnostics/autonomous_final_test_summary_20261110.json`
- `docs/diagnostics/overnight_broker_evidence_20261110.json`
- `docs/diagnostics/overnight_persistence_deployment_20261110.json`
- `docs/diagnostics/autonomous_demo_acceptance_20261110.summary.json` ? live observer summary.
- `storage/strategy_research/state.json` ? inspectable frozen research candidates and results.

Final recovery verification:

- Normal launcher: SUCCESS / backend_healthy_desktop_ready; startup_in_progress remained false and dispatch completed after subsequent trader cycles.
- Backend PID 25280; desktop ready; research report and lifecycle observer timestamps fresh.
- Research completed two batches; the latest contains two candidates, both research-only. Latest training results are negative; its held-out segment has no qualifying trades. No positive validation is inferred from a zero-trade result.
- Replacement observer: 23 healthy samples at final check, zero broker/stale-status/publication errors, zero positions/pending orders and no verified autonomous cycle.
- Browser: no page errors, successful API polls, refresh/view controls checked, no horizontal overflow at 1440/768/390 widths. Research and pending lifecycle proof are visible; mutating browser API requests were intercepted during testing.
- Risk remains 0.5% per trade, with existing 3% daily/6% weekly drawdown limits, R1,000 objective and Gemini advisory-only. Learning force mode is off. No diagnostic order was sent.

Evidence: `docs/diagnostics/autonomous_final_runtime_20261110.json` and `docs/diagnostics/autonomous_ui_smoke_20261110.json`. Ongoing samples and results may change after this recorded check.


## Subsequent authorized broker test

At 08:27 SAST, the operator-authorized automated demo mechanics test completed successfully: one 0.01-lot entry, broker SL/TP readback, one close, balanced broker fills and a flat account. Net diagnostic result -R5.89. This is deliberately excluded from natural strategy proof. See `docs/BROKER_LIFECYCLE_VERIFIED_20261110.md`.
