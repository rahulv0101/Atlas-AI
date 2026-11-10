# Broker-confirmed strategy evidence — 9 November 2026

Atlas now keeps a separate closed-position ledger and compares its evidence with
the current weak-strategy filter in shadow mode. Strategy selection, allocator
learning, timing, risk limits and execution policy remain unchanged. Gemini's
explicitly selected advisory-only role remains active.

## What changed

- `atlas_ai/learning/closed_position_ledger.py` accepts history only from the
  matching configured demo account and symbol. It groups native fill records by
  position, counts partial fills once, and includes reported profit, commission,
  swap and fees in each net outcome. It preserves broker-time conversion to UTC.
- Open positions, incomplete volume, reversals, conflicting directions, invalid
  sequences and quarantined records cannot enter strict strategy statistics.
  Manual-test labels persist across later snapshots, even if comments change.
- Strict strategy evidence additionally requires a unique link to a successful
  guarded demo decision. Broker comments alone are insufficient; ambiguous short
  decision IDs are rejected. Future execution samples include the broker order
  reference and request origin needed for this linkage.
- The ledger is isolated from allocator memory and uses a cross-process lock and
  atomic replacement. Corrupt files or failed writes preserve the previous file.
  Unavailable history or position inventory produces unavailable evidence.
- The trader updates evidence during closed-trade reconciliation. Status and the
  dashboard API expose `strategy_evidence`, including current eligibility and
  shadow eligibility using the same weak-strategy filter. Missing or insufficient
  confirmed samples produce `null` shadow eligibility, never an implied pass.
- `tools/sync_closed_position_ledger.py` provides read-only broker backfill. The
  bounded demo observer now records the evidence summary alongside decisions.

## Findings

The one-year backfill retrieved **316 fills and 158 balanced closed positions**.
One position is identified as a manual test. **Zero positions have sufficient
decision provenance for strict autonomous-strategy statistics.** The historical
positions remain visible but cannot establish current strategy performance.

The existing allocator combines reward observations, including open-position
feedback, with other retained outcomes and initial priors. Its win/loss counters
must not be described as a clean count of completed strategy trades. This change
does not reset or replace that allocator or relax its restrictions.

Two of the eight observed strategies remain excluded by the existing weak-strategy
filter. All eight shadow comparisons report insufficient confirmed evidence.
This comparison covers that filter only; passing it would not waive other gates.

The normal guarded launcher restored the stopped demo system and reported
`SUCCESS / backend_healthy_desktop_ready`. Live status and API exposed the ledger,
Gemini influence remained false, and independent broker checks found zero open
positions and pending orders. Observed decisions included waiting for a fresh
entry/retest and HOLD with no directional candidate. No diagnostic order was sent.
A two-hour read-only observer was started; its completion is not claimed here.

## Validation and limits

The focused integration run passed **183 tests** covering ledger accounting,
learning, UTC conversion, replay, the guarded pipeline, UI API and bounded event
reads. After the final manual-label preservation change, all **27 ledger tests**
passed. The advisory test now compares against an equivalent pipeline without
Gemini rather than assuming a session-dependent absolute confidence score.
Python compilation and Git whitespace checks passed. Tests use simulated broker
submission; the native checks read account/history/inventory only.

The new ledger cannot reconstruct the missing original event journal, prove
profitability, or establish whether excluded opportunities would have performed
well. Broker retention can omit entry legs or separately booked charges. It does
not claim a natural entry-management-exit demonstration or resolve the historical
unexplained native crash. Unattended watchdog behaviour remains unchanged.

Artifacts:

- `docs/diagnostics/closed_position_ledger_20261109.json`
- `docs/diagnostics/closed_position_live_verification_20261109.json`
- `docs/diagnostics/closed_position_tests_20261109.xml`
- `storage/performance/closed_positions_<account-fingerprint>.json`
- `storage/demo_observations/observation_20261109T072635Z.jsonl`
