# Atlas timing, readiness and reliability repair — 5 November 2026

The screenshot showed a rejected entry candidate, not proof that MT5 was broken.
The timing rules require a suitable location, confirmed M1 momentum and the
existing visual checks. They remain enforced. This repair corrects clock
interpretation and misleading operator reporting; it does not loosen those rules.

## Repairs

- The dashboard consumes the API's readiness classification. A normal market or
  timing wait displays **WAITING**. Broker, recovery, safety and automation faults
  remain **BLOCKED/REVIEW**. A buy/sell candidate alone cannot produce READY.
- Readiness now includes paused/disabled automation, kill switch, reconciliation,
  forced-flat handling, session closure and old/invalid decision timestamps.
- Blocker questions use the shared Brain evidence path. Old execution/pilot
  failures and `runtime_context_required` no longer replace the current signal
  generation/ranking explanation. Current safety vetoes retain priority.
- A shared MT5 clock boundary converts rates, ticks, historical query bounds,
  deal-learning times and position opening dates consistently. The default is the
  documented MT5 UTC contract. This installation explicitly configures
  `MT5_SERVER_TIMEZONE=Europe/Athens` after verifying that this HFM server exposes
  wall-time epochs. Winter/summer offsets come from timezone rules, not a permanent
  two-hour subtraction or an estimate from a stale tick. Ambiguous/nonexistent
  DST wall times fail rather than invent a timestamp.
- Freshness treats naive strategy timestamps as UTC regardless of the operator's
  Windows timezone. Future bars and stopped backend snapshots cannot appear
  fresh. Clock basis and broker timezone are inspectable in the status API.
- Native pending-order cancellation now checks execution permission, the exact
  configured demo account, terminal/API permissions, symbol and Atlas magic.
  It sends REMOVE once and requires broker confirmation. It never closes a filled
  position, touches another strategy's pending order, or retries an uncertain send.
- Windows mutex/process handles now use pointer-width-correct native signatures.
  The duplicate voice-loop path closes its unused mutex handle. Cleanup no longer
  attempts to release a mutex that was created without ownership.

## Broker verification and compatibility

Before configuration, the raw broker tick was approximately **7,200 seconds ahead
of UTC**. The computer's UTC time matched an independent HTTPS Date header.
With the explicit clock setting, the observed tick age was **0.479 seconds**.
A 12-minute historical range returned the same timestamps and closes as the
position-based bar query. Both API boundaries were checked read-only.

All newly fetched strategy frames retain their existing naive-datetime shape,
with UTC semantics. OHLC values, strategy formulas, timing thresholds, sizing,
risk limits, pilot limits and execution approvals were not changed. Existing
historical files and learned outcomes were not rewritten. Earlier records without
clock provenance remain legacy evidence and must not be presented as newly
validated UTC history.

The [MT5 documentation](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py)
specifies UTC timestamps. HFM separately documents its platform's
[GMT+2/GMT+3 server clock](https://www.hfm.com/sc/en/trading-instruments/trading-hours).
The local override is justified by the measured API behaviour on the configured
demo server; HFM's platform clock alone is not proof that every MT5 server needs
the same override.

## Validation and runtime evidence

The new regression cases cover the screenshot's rejection, readiness safety
vetoes, actual JavaScript rendering, UTC and configured broker-time conversion,
DST edges, range-query parity, future/stale clocks, owned pending cancellation,
unknown cancellation results, native handle signatures and relevant blocker
answers in standard and voice modes.

The final isolated full suite passed **1,554 tests**, with **zero failures,
errors or skips**, in **546.59 seconds**. Normal pytest instrumentation remained
enabled. All 352 inventoried application, test and monitor files matched the
running workspace after the suite; no application fixes were added afterward.
`pip check`, Python compilation, JavaScript syntax and Git whitespace checks
also passed. No pytest workers remained after validation.

Final results and live verification are recorded in
`docs/diagnostics/system_repair_verification_20261105.json`.
The first isolated attempt omitted the executable monitor source stored under
`storage/monitoring/atlas_monitor.py`; its missing-file failures were a test-copy
problem. That incomplete attempt is retained separately. The final snapshot
includes the monitor source and all application/test files.

The normal launcher reported **SUCCESS**, with a verified backend heartbeat and
a newly opened desktop window. The restarted API reported WAITING, a connected
broker, enabled automation and fresh UTC bars. The current HOLD remains subject
to changing market evidence. No diagnostic order or cancellation was submitted
to the real terminal during verification.

The final live check confirmed the matching configured demo account, Algo Trading
and Python API permissions, zero positions and zero pending orders. Tick age was
**0.57 seconds**, and a fresh 12-closed-bar historical query exactly matched the
position-based query. Standard and voice blocker answers selected the `blocker`
intent and `blockers` domain; follow-up “Why?” retained that reasoning. All four
saved final answer checks passed relevance, including voice capabilities.

## Limits that software changes cannot erase

- The missing historical event journal object is still unavailable locally and
  this repository has no configured remote from which to fetch it. Its gap
  manifest and pointer remain preserved; historical trades were not invented.
- Software tests and healthy demo operation do not establish profitability or
  prove that the existing strategy filters are economically optimal. Natural
  qualifying entries and completed demo trades still need observation.
- The earlier native access violation has no established root cause. The native
  handle bugs were independently demonstrable defects; they must not be claimed
  as proof that the earlier crash is resolved. That crash did not recur in this
  complete run with normal instrumentation enabled.
- Physical microphone capture and a new broker-confirmed entry-to-exit lifecycle
  were not forced or claimed as demonstrated by mocked tests.

All previous user changes remain in place. Nothing was staged, committed or
published as part of this repair.
