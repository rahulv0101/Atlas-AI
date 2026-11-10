# Atlas system audit - 9 November 2026

Completed bounded software and operational audit. This is not proof of strategy
profitability or a guarantee that every defect has been found.

## Confirmed repairs deployed

- Invalid/nonpositive sizing inputs no longer fall back to a base lot. Accounts
  unable to fund the broker minimum within the configured risk budget get zero
  feasible volume and an explicit sizing blocker before an order request.
- Lot quantities round down to the permitted broker step, including after a
  maximum-volume cap. Rounding cannot increase the requested quantity.
- Risk sizing accounts for point size versus tick size. The final broker order
  preflight checks margin and estimated currency loss at the final stop against
  the existing per-trade risk fraction. Missing/nonfinite loss or margin data is
  rejected. This estimates stop loss risk; gaps, slippage and fees can increase
  actual losses.
- A stale startup marker no longer bypasses recovery merely because the listener
  still says running or started_async. Fresh startup dispatches remain protected.

Strategy logic, the approved confirmed-demo performance filter, drawdown limits,
Gemini authority and the daily demo objective have not been loosened.

## Broker sizing evidence

The configured matching demo account uses ZAR. Its XAUUSD minimum is 0.01 lots,
with increments of 0.01 lots. At the checked quote, the minimum buy needed R135.31
margin; an illustrative 100-point stop represented about R16.43 before fees and
slippage. At the configured 0.5% per-trade risk fraction, that example needs about
R3,286 equity to fit the risk budget. These are changing broker values, not a
universal deposit minimum or a recommendation to fund the account.

Read-only order preflight and MT5 order_check passed for the matching demo
account. No order was submitted. Artifact: sizing_broker_spec_20261109.json and
full_system_broker_preflight_20261109.json in docs/diagnostics.

## Runtime and interaction checks

Compact status, runtime and AI-decision endpoints responded. Market freshness
was reported fresh and the approved confirmed_demo_positions policy was active.
After a clean idle reload, the normal launcher completed SUCCESS /
backend_healthy_desktop_ready. A new backend process and ready desktop were
verified. Protected settings match the pre-reload snapshot: 0.5% per-trade risk,
3% daily and 6% weekly drawdown limits, R1,000 objective, Gemini advisory-only
and the approved confirmed-demo performance filter. The latest entry was held
by the existing fresh-entry/retest requirement; this gate was not bypassed.
Capabilities, limitations and market-knowledge questions returned the expected
informational intents without changing execution controls. Dependency consistency
passed pip check. Source compilation and JavaScript syntax checks passed.
A synthetic Gemini request succeeded with text, using the configured model and
key; no account or market data was sent. Browser checks confirmed status polling,
Overview/Diagnostics switching, suggested question input and no overflow at
1440, 768 and 390 pixels. All browser POST requests were intercepted.

## Test investigation

An initial monolithic test run stalled in historical backtesting and was stopped.
Diagnostic runs with periodic faulthandler stack dumping then produced native
access-violation records and terminated without completed test reports. A single
isolated backtest passed. Without periodic stack dumping, the backtest suite
passed 12 tests. The remaining suite ran 1,679 cases and found two obsolete UI
label assertions; these were updated to the current API-readiness and answer-mode
contracts. All 25 UI regression checks then passed. The final focused repairs
run passed 68 tests. The union of reports covers **1,692 distinct cases with
passing latest outcomes**, with no skips. This is a combined result from isolated
runs and focused reruns, not a successful monolithic run. No native fault was
recorded in the non-periodic-dump reruns. This does not establish the fault's
cause. A related upstream diagnostic race is documented at
https://github.com/python/cpython/issues/158200 ; its applicability to this
Python 3.12.2 installation is unproven.

Separately, a native COM fault record exists for desktop window creation; the
recorded desktop process remained alive and responding afterward. A fault-log
entry alone is not evidence that that process terminated.

## Remaining limits

Natural autonomous trade entry, management and exit have not been demonstrated
by this audit. Historical event gaps and incomplete decision attribution remain.
Broker preflight and test success do not establish profitability. Very small
accounts can correctly remain unable to trade because of broker minimums and
risk limits. Adapter cancellation remains an explicit unsupported capability. Physical
microphone-to-speaker operation was not exercised; voice/typed routing and
command isolation were covered by automated tests.

## Final artifacts

All are under docs/diagnostics/: full_system_test_summary_20261109.json,
full_system_combined_tests_20261109.xml, full_system_final_runtime_20261109.json,
full_system_broker_preflight_20261109.json, full_system_ui_smoke_20261109.json,
full_system_answer_smoke_20261109.json and full_system_gemini_probe_20261109.json.
Original failed instrumented logs and the two initially failing UI checks are
retained alongside their successful reruns for inspectability.

## Follow-up: small volume and native-path verification

See SMALL_VOLUME_SUPPORT_20261109.md for subsequent sizing/precision and guarded
demo cap repairs, a complete single-process run without native faults, correction
of a collection-time timestamp fixture, Windows native-fault mappings and final
deployment. Latest passing outcomes now cover 1,702 distinct tests across the
complete run and the focused correction run. The underlying cause of invalid
interpreter memory in the earlier instrumented runs is not conclusively proven.
