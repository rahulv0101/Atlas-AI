# Daily demo profit objective — 9 November 2026

The operator explicitly selected **R1,000 per day** as a demo objective.
The project `.env` now sets `DAILY_PROFIT_TARGET_ZAR=1000`.

The existing daily drawdown threshold (3%), weekly threshold (6%), strategy,
timing, execution and other risk gates remain unchanged. Gemini remains
advisory-only. There is no monthly target or guaranteed return.

The existing target behaviour is retained: reaching the objective activates
defensive sizing for subsequent permitted entries. It does not force trades to
reach the objective, increase risk after losses, stop all trading at the target,
or automatically close positions. Other gates can block entries at any time.

`daily_profit_objective` in status and the dashboard API now reports the target,
progress, remaining amount, whether it has been reached, and the accounting
basis. Progress is equity minus the tracked daily starting balance; this includes
unrealised P/L and account cash flows and must not be described as net realised
strategy profit. Existing daily accounting uses UTC, resetting at 02:00 SAST.

Validation: 136 integration tests passed across the guarded pipeline, replay,
trader learning and UI API. After extending target boundary coverage, all 14
pipeline tests passed. Tests cover disabled/below-target/reached-target states,
defensive sizing and deterministic blockers with the target enabled. Broker
submission is simulated in tests. The demo account and zero position/order
inventory were checked before the normal guarded reload.

Live verification is recorded in
`docs/diagnostics/daily_objective_live_20261109.json`; the focused test report is
`docs/diagnostics/daily_objective_tests_20261109.xml`.
