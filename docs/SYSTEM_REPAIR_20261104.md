# Atlas system repairs and forward verification — 4 November 2026

## Completed repairs

- Startup reuses a connected MT5 session only when both configured account and
  server match. Disconnected or other accounts still require verified login.
  The local demo server configuration was aligned to `HFMarketsSC-Demo2`.
  Algo Trading remains enabled for the explicitly requested demo run; startup
  still refuses a disabled switch rather than toggling it automatically.
- Invalid guarded-demo launch commands now fail once without stopping an
  existing terminal or backend. This also closes a test-isolation defect.
- Signal diagnostics preserve the candidate before signal-generation filters,
  the result after filters, and the actual filter reason. Existing `signals`
  remain compatible and are explicitly labelled as after generation filters.
- Why-trace now distinguishes absent direction, generation suppression,
  performance eligibility filtering, and candidate ranking. Flat candidates
  cannot make the trace claim that all entry stages passed. Brain v2 synthesis
  uses these grounded signal-stage reasons in both typed and voice answers
  instead of replacing them with the first generic blocker-catalog entry.
- Old fills, rejects and approval failures are marked historical in snapshots,
  rather than only expiring two approval errors. Old gate checks are similarly
  annotated, and current runtime feed information takes precedence over an
  old saved simulation cycle for mode display. Audit records are retained.
- Execution-gate preflight blocks now appear as blocked with their reason,
  rather than an unexplained execution failure. Broker failures retain their
  failure reason. Admission and broker routing are unchanged.
- Historical backtest session classification now extracts the UTC hour from
  the timestamp correctly. Previously it attempted `int(timestamp).hour`,
  caught the resulting exception, and used hour zero / session `other`.
  The established London/New York/late-US boundaries are unchanged. Historical
  session labels and session-filtered backtest results may consequently differ;
  old saved training outcomes were not rewritten or retrained automatically.

No strategy formulas, entry thresholds, performance restrictions, risk limits,
pilot permissions or approval policy were loosened. The earlier verified retest
adapter remains in place. Tests now also reject real Windows process termination.

## What the fresh data shows

At 20:31 SAST, three weak directional candidates (EMA, pullback and an evolved
rule) existed before filters, at confidence approximately 0.05–0.16. Existing
low-energy filters flattened them. The strategy-output display previously
called its already-filtered values “raw”; those values alone could not establish
whether the original strategies were flat. The new evidence resolves that gap.

At 20:44–20:48, directional candidates began surviving the volatility filter.
EMA and pullback were then rejected by the existing performance eligibility
checks (recorded win rates approximately 21%). Remaining eligible strategies
were flat. The published why API now identifies `signal_ranking` as the first
stop and marks timing, risk and execution as not reached. This is an observed
restriction, not evidence that broker execution is broken.

The backend and desktop were restarted through the normal launcher, preserving
MT5. Launcher result was `SUCCESS` / `backend_healthy_desktop_ready`. The API
server was refreshed after the final why-trace correction. Fresh status confirms
guarded demo, broker-runtime data, and old execution truth marked not current.

## Execution verification and limits

- An isolated candidate traversed the real trader, timing gate, bounded demo
  approval, ExecutionGate, production MT5BrokerAdapter and TradeExecutor with
  a fake MT5 transport. Exactly one simulated order was constructed and filled;
  replaying the same request produced no additional submission.
- Separate injected failures for timing, risk, kill switch, higher-timeframe
  alignment and pilot family produced no broker submission.
- A real read-only MT5 `order_check` on the verified demo account accepted a
  synthetic 0.01-lot request built by Atlas (`retcode=0`, `Done`). This checks
  broker preflight compatibility; it does not place an order or demonstrate a fill.
- On 37 frozen market frames, all before/after signal outputs matched exactly.
  This covers signal-filter observability, not the intentional backtest timestamp fix.
- No diagnostic forced a real order. Forward cycles still had zero positions
  and zero trades at the recorded verification time. Natural broker submission
  remains conditional on a genuinely qualifying setup and all existing gates.

## Evidence

- `storage/signal_generation_probe_20261104.json` and corresponding frozen CSV.
- `storage/signal_filter_equivalence_20261104.json`.
- `storage/broker_preflight_check_20261104.json`.
- `storage/system_repair_restart_shutdown_20261104.json`.
- `storage/system_repair_launcher.err.log`.
- `storage/system_repair_live_verification_20261104.json`.
- `storage/system_repair_final_verification_20261104.json`.
- `storage/system_repair_test_workspace_20261104.json`.
- `storage/backtest_regression_workspace_20261104.json`.

The original missing historical event-journal LFS object remains unavailable;
this repair does not reconstruct or invent that history. Existing staged user
changes were preserved. These repairs have not been staged or committed.

## Final verification

At 21:02 SAST the final live check confirmed matching demo account/server,
connected terminal, Algo Trading enabled, Python API allowed, zero positions,
zero pending orders and zero trades today. The actual `/api/ask-atlas` answer
reported: “Blocked at signal ranking: Directional candidates failed the existing
strategy performance eligibility checks; no eligible buy or sell candidate
remained.” This was verified through the running UI server, not only a unit test.

Validation completed across isolated groups:

| Check | Result |
| --- | --- |
| Regression group excluding the 12 heavy backtests | 1,407 passed initially; 10 failures were missing copied fixtures |
| Restored monitor source and wake-config example fixtures | 14 passed, covering all 10 omitted-fixture failures plus 4 already passing cases |
| Separate legacy backtest group | 12 passed in 727.73 seconds |
| Final UTC session extraction and timezone boundaries | 12 passed |
| Latest why-engine / typed-voice / Brain v2 checks | 35 passed |
| Focused entry, timing, signal, snapshot, replay and layer checks | 95 passed before final answer refinements |
| Production adapter/executor plumbing and five veto conditions | 7 passed |
| Frozen-frame signal-filter equivalence | All 37 frames identical |
| Real demo broker preflight | Accepted, no order submitted |
| Git whitespace check | Passed |

This is coverage across test groups and source snapshots, not a claim that one
final all-tests invocation passed. The legacy backtest snapshot predates the
small UTC-hour correction; the correction itself is covered by the new 12-case
session test module. The final synthesis refinement is covered by the latest
35-case answer group.

An earlier instrumented full run encountered a native Windows access violation
while historical backtests were running. It did not reproduce in the separate
backtest run with the pytest faulthandler instrumentation disabled. The cause
was not established; no dependency or interpreter change is claimed to fix it.
The original failing and interrupted logs remain available in the recorded
temporary workspaces and storage. Live backend scanning continued normally.

No broad suite was rerun after the final passing groups, and no outstanding test
worker was intentionally left running. Natural market eligibility and actual
broker fills remain separate from synthetic tests and read-only order checks.
