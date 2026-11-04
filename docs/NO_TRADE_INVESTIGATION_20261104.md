# Why Atlas is not taking trades — 4 November 2026

Follow-up: the confirmed retest-location mismatch and forward-journal defect were
subsequently repaired. See [the entry pipeline repair](ENTRY_PIPELINE_REPAIR_20261104.md)
for the code changes, retained history gap, and final verification. This document
records the preceding investigation.

## Current cause: the trading backend is stopped

At inspection, MT5 was running (PID 9844), but no Atlas Python backend was running.
The saved backend heartbeat is from **23 October, 07:13:47 SAST**. A saved `running`
label and `execute_trades=true` do not establish a running trading loop.

The shutdown was intentional: `docs/operator_shutdown_20261023.md` requires Atlas
to remain stopped until an explicit restart request. This investigation did not
restart it or enable an automatic restart task.

## MT5 permission check

At 09:12 SAST on 4 November, a read-only attachment to the already running terminal
confirmed:

- Connected to the configured **demo** account; account identity matches the project
  configuration. No account number, password, or login operation was needed.
- Terminal trading allowed; Python trading API not disabled.
- Account trading and Expert Advisor trading allowed.
- XAUUSD exists, is selected, and reports full trading mode.
- Zero open XAUUSD positions at the check.

These flags establish basic readiness, not successful order execution. No order was
sent. The Python attachment was closed afterward; the terminal was left open.
Evidence: `docs/diagnostics/mt5_read_only_20261104.json`.

## Last saved strategy decision

The most recent saved status is **23 October, 07:17:41 SAST**:

- Action: `hold`.
- Reason: `No directional trade signal selected.`
- Chosen strategy: `momentum_continuation`; side: `flat`.
- Raw signal confidence seed: 0; displayed conviction: 0.45.
- Effective confidence threshold: 0.44; same-side directional support: 0.
- Setup family: `no_trade`.

A displayed conviction above threshold does not turn a flat signal into a buy/sell
candidate. This cycle stopped at signal selection, before an entry request existed.
Its timing record says `passed=true` because the timing hard block only applies to
directional signals. That does not mean the missing timing conditions were satisfied
or that a trade was ready.

This is a historical cycle, not an assessment of today's market.

## Earlier running-period blockers

The retained written investigation `docs/automated_trade_blockers_20261014.md`
reports, for its explicitly defined October 13–14 window:

| Decision records | Count |
| --- | ---: |
| Flat/non-directional holds | 661 |
| Directional candidates stopped by timing discipline | 67 |
| Directional candidates stopped by higher-timeframe alignment | 18 |
| Records reaching execution/submission | 0 |

Those counts are historical reported records, not independently re-counted October
data in this investigation and not a count of unique market opportunities.

The inspected code still has the relevant constraints:

- Timing requires suitable entry location and momentum, with visual vetoes when
  visual-watch evidence is used for decisions.
- Plain `breakout` is not in the fresh-entry/retest location allowlist. The prior
  investigation documents a potential interface mismatch: a breakout/retest strategy
  can confirm its own retest while the downstream generic location still says
  `breakout`. That can reject a high-confidence candidate before execution.
- Higher-timeframe alignment is enabled.
- Guarded automatic demo approval has a separate confidence floor of
  `max(effective_threshold, 0.55)` and size cap 0.01.
- The persisted pilot permits `continuation` only. A breakout candidate surviving
  earlier checks can still fail pilot-family restrictions later.

Passing any one check does not establish that later checks will pass. The timing
and higher-timeframe gates precede automatic approval, so lowering confidence alone
does not resolve those first blockers. Current configured same-side support is 1;
older historical consensus blocks requiring 2 must not be treated as current policy.

The latest stored successful broker result is an explicitly attributed manual
plumbing test (`operator_manual_test` / `manual_broker_test`), not fresh evidence of
an automatic trading cycle.

## History coverage gap

The current `storage/events.jsonl` is a **Git LFS pointer**, not the journal body.
It references a 261,418,685-byte object that is absent from the local LFS cache.
No Git remote is configured to retrieve it here.

A fresh stream/deduplication scan inspected 3,132 journal/archive paths. Parseable
event timestamps extend only to **18 September 2026**. Archive filenames extending
into October contain September events; filename dates cannot replace event dates.
The scan therefore cannot reconstruct October 15–23. Missing records are not proof
of zero trades or zero evaluations in that interval.

The separate rejected-analysis log extends to October 23, but such analysis records
are not authoritative proof that `AtlasTrader` reached execution. It was not used
as the trading-decision denominator.

Coverage warnings and older locally parseable counts are recorded in
`docs/diagnostics/atlas_pipeline_20261104_post_oct15.json`.

## Verification and next boundary

Eighteen existing diagnostic/policy/integration tests passed, including a simulated
eligible candidate traversing the guarded execution route. The tests preserve
current timing distinctions and the independent 0.55 automatic-approval floor.
No thresholds, risk limits, strategy rules, or execution controls were changed.

The immediate operational requirement for fresh trading decisions is an explicit
backend restart. Once requested, verify fresh heartbeat/status, account mode, and
the first actual stopping stage. Restoring the missing journal is necessary for
a complete retrospective October audit. Neither task is equivalent to disabling
entry safeguards or forcing a trade.

Additional observation: raw MT5 tick timestamps appeared approximately two hours
ahead of UTC during the check. This matches the existing broker-clock diagnostic
backlog; it is not identified as today's trading blocker because no backend cycle
was running.
