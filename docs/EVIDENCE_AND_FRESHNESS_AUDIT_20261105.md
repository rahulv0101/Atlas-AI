# Atlas: additional faults and evidence gaps, 5 November 2026

The clock normalization and native pending-order cancellation listed in the
earlier concerns are already implemented. This follow-up found additional faults
in execution freshness and research evidence. It also recovered broker history
that changes the performance assessment from merely unknown to historically
adverse, with important attribution limits.

## Confirmed faults repaired

1. **Fresh cycle did not imply fresh market data.** The execution gate previously
   received cycle age alone. A responsive cycle could therefore use old quotes.
   The submission payload now independently checks recorded UTC tick and bar
   timestamps, recomputing their age at submission. Tick age uses the existing
   120-second execution freshness window; bar age uses the existing freshness
   contract, max(180 seconds, eight timeframe intervals). Missing, unverified,
   future or expired evidence vetoes execution. The API exposes the same faults.
   This is a stricter data-validity check; entry thresholds and risk sizes remain
   unchanged.
2. **Counterfactual matching compared different timestamp units.** The timing
   selectivity tool compared nanosecond bar indexes against second timestamps,
   skipping otherwise valid samples. Both now use nanoseconds, with tests for
   nanosecond, microsecond and millisecond input indexes. Unsorted, duplicate,
   stale or unavailable bars are rejected.
3. **Research controls could count a request as an executed trade.** The tool now
   requires broker fill evidence. Submitted/pending orders and request creation
   do not qualify as completed fills.
4. **Journal records omitted original stop and target distances.** Forward
   compact events now retain them and clock provenance. Replay excludes legacy
   records missing this evidence instead of inventing 100/160-point distances.
   Existing records are preserved without speculative backfill.
5. **Research could score incomplete outcomes or favorable intrabar guesses.**
   The analysis requires a complete forward horizon, uses stop-first when both
   stop and target are touched, and subtracts configured spread/slippage costs.
   Existing live learning/backtest defaults remain compatible; the conservative
   policy is explicit in this diagnostic. Reports identify missing commission
   modelling and correlated/overlapping hypothetical opportunities. Profit factor
   is undefined rather than an invented 999 when no losses exist.
6. **Native crashes lacked a dedicated durable trace.** CLI processes now enable
   all-thread native fault tracing to process-specific files under
   `storage/native_crashes`, preserving an already enabled handler. This supplies
   evidence for another incident; it does not establish the previous cause.
7. **Shutdown stopped only one frontend process.** Atlas has separate desktop and
   API processes. Shutdown now inventories every UI/API mode in this project,
   stops desktop wrappers before the API, and verifies no matching process
   remains. Another project's processes are excluded; unavailable inventory
   cannot be reported as a clean shutdown. The change passed 62 startup, command,
   voice and supervisor checks. An actual frontend restart stopped both observed
   PIDs, verified an empty remaining inventory, and successfully reopened the UI
   while retaining the healthy trading backend.
8. **Invalid confidence could become maximum confidence.** Applying the old
   numeric clamp to NaN could yield 1.0. Invalid/non-finite confidence now becomes
   a flat signal with zero confidence. Existing finite-value clipping and evolved
   strategy treatment remain unchanged. Nine new cases plus signal generation,
   replay baselines and guarded execution checks cover this boundary.
9. **Both remote advisor paths were failing.** Logs showed Gemini requests
   returning 404 and OpenAI requests returning 401. The Gemini model was
   hardcoded. Atlas now supports explicit model configuration and uses
   `gemini-2.5-flash`, verified against this account's model list and a successful
   live text response. Legacy clients use the same configured model. Model and
   authentication faults now receive a six-hour cooldown, and health output
   stores sanitized classifications rather than raw exceptions. OpenAI still
   needs a valid local credential. Trading influence remains off.

The filter report is diagnostic only. No live filter was removed, weakened or
retuned, and no learned state was silently replaced.

## Recovered performance evidence

Read-only history retrieval on the matching configured demo account recovered
**316 fill legs**, forming **158 completed position groups** with matched entry
and exit volumes. The grouped recorded results are:

| Measure | Recovered records |
|---|---:|
| Wins | 49 |
| Losses | 109 |
| Win rate | 31.01% |
| Profit factor | 0.697 |

This group lost money overall. Profit values include the broker's recorded
commission and swap. These records may include older strategies and diagnostic
or manual trades using the same Atlas magic number. They do not prove that the
current strategy has the same performance, nor do they justify changing filters
without matched evidence.

Artifacts:

- `storage/recovered_history/broker_fills_20261105T103238Z.json`
- `docs/diagnostics/recovered_execution_evidence_20261105.json`

Recovery did not write to trading memory, send an order or replace the missing
event journal. The original history-gap manifest remains unresolved. Broker
fills cannot reconstruct rejected opportunities or the reasoning behind trades.

## Sustained observation

A bounded, read-only observer was started for **120 minutes**, sampling the
current status at 60-second intervals and retaining each distinct decision.
Files are under `storage/demo_observations`. It records decision timestamps,
signals, timing evidence, market clocks and reported execution state. It cannot
route commands, send trades, modify policies or train models. Reported execution
state still requires independent broker confirmation.

The first observer and runtime stack stopped during the interruption. No native
fault trace established a cause. The stack was restored through the normal
launcher and a fresh bounded observation run was started. Final checks confirmed
the configured demo account, healthy backend and desktop/API, enabled broker
permissions, and zero positions/pending orders. Current readiness was WAITING
for a directional signal. Observation results remain pending; uninterrupted
two-hour coverage is not claimed.

The repaired timing-selectivity report defaults to the current journal. Archives
require an explicit option. Only provenance-complete, mature samples are scored;
an insufficient-data report is a valid result, not proof of zero opportunity.

## Additional issues and limits still requiring work or evidence

- **Historical attribution is weak.** Recovered fills lack a complete matching
  decision journal, so older performance cannot be cleanly assigned to the
  currently running strategy and filters.
- **OpenAI fallback remains unavailable.** Its credential was rejected with HTTP
  401. Gemini text generation was verified independently. The
  [official OpenAI error guide](https://developers.openai.com/api/docs/guides/error-codes)
  identifies 401 as an authentication problem. A valid `OPENAI_API_KEY` must be
  configured locally to restore that optional provider.
- **Current selectivity remains economically unvalidated.** Counts of HOLDs are
  not independent missed opportunities. Outcome-complete, cost-aware comparisons
  and a natural current entry/management/exit sequence are still needed.
- **Legacy backtest assumptions remain relevant.** The historical backtester can
  infer stop/target order from candle direction. Conservative analysis now
  exposes this sensitivity without silently changing learning or strategy policy.
- **Native crash cause remains unknown.** The earlier complete run passed with
  normal instrumentation; crash tracing is now available for recurrence.
- **Continuous training is limited.** Live background historical training remains
  disabled while its MT5/threading/process isolation issue is unresolved. The
  current Python 3.12 environment is working; voice resampling still needs a
  replacement before a Python 3.13 migration.
- **Resource headroom matters.** Only about 723 MB of system memory was available
  during the audit, coinciding with slow test/startup work. Atlas's WebView
  helpers belonged to the current desktop; no orphaned Atlas browser instance
  was established or removed. Unrelated applications were left running.
- **Unattended recovery is not verified as active.** The existing watchdog does
  not clearly honor intentional shutdown before restarting a missing worker.
  It was not enabled or registered as an automatic supervisor by this audit.
  Recovery supervision needs explicit desired-state handling and bounded retry
  tests before deployment.

Final test results, current health and artifact paths are recorded separately
in `docs/diagnostics/evidence_hardening_verification_20261105.json`.

## Validation scope

The isolated full suite passed **1,583 tests**, with zero failures, errors or
skips, in **1,329 seconds**, using normal instrumentation. After that snapshot,
the frontend shutdown/inventory fix received **62 passing related checks**, and
the invalid-confidence fix received **53 passing signal/replay/pipeline checks**.
These groups overlap and must not be added as disjoint counts. Later application
changes were `atlas_full_shutdown.py`, `runtime_processes.py`, the narrow
confidence-validation branch in `trader.py`, and advisor model/error handling in
`llm/gemini_helper.py`. Provider handling received **44 passing related checks**,
followed by focused default-model validation. Research count labels were also
clarified with **10 passing integrity checks**. Core freshness and research
algorithms match the full-suite snapshot. No test result proves profitability.
