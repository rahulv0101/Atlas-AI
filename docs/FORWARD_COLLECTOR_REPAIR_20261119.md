# Forward collection recovery

The retained old experiment remains paused and immutable. A short read-only
MT5 snapshot overlapped 802 of its saved M5 candles. One actual broker candle
changed: November 16 17:45 UTC close 3857.91 -> 3857.99 and tick volume
1602 -> 1832. That candle was the last retained row. This supports preserving
the revision stop; the exact feed snapshot at the original failure was not
retained, so the audit does not claim to reconstruct its precise cause.

The new comparison utility examines canonical timestamp and broker fields,
excluding derived ATR and CSV formatting/dtype differences. Genuine OHLC,
spread and volume changes still fail validation. Missing overlap is unknown,
not a pass. Old checkpoint hashes and forecasts were not reset or re-signed.

## Fresh collector

`tools.settled_m5_collector` now runs as a separate read-only experiment at
`storage/settled_m5_forward_20261119_v2`. The first setup attempt, with zero
forecasts, is retained at `storage/settled_m5_forward_20261119`.

- Wait at least 60 seconds after candle close before committing broker history.
  This settling delay is not a guarantee that a broker will never revise data;
  subsequent genuine changes still pause collection and preserve field details.
- Never backfill predictions more than 120 seconds after their source close.
- Freeze corrected-distance candidate sets using the prior R100,000 virtual
  research profile; no live limits, selected signals or orders are changed.
- Record observed quotes, closed-source bar time, publication time and a future
  scheduled entry boundary. Do not claim the earlier next-bar opening price was
  executable after a delayed observation.
- Preserve journal/checkpoint hashes, source hashes, account scope, revision
  safeguards, exclusive worker lock and a fixed 21-day deadline.
- No outcomes, trades or strategy qualification are claimed by this collector.
  A separately validated outcome/portfolio evaluator is still required.

The first forecast was published at 07:21:13 UTC (09:21:13 SAST) on November 19,
after its source candle closed at 07:20 UTC, for a scheduled boundary at 07:25
UTC. The record's `lag_seconds` measures source-snapshot lag (67.8 seconds);
publication lag is independently recoverable from `observed_at` (73.1 seconds).
Both precede the scheduled entry. The journal matched its signed checkpoint.

## Startup and reporting

The existing full-stack startup launcher now resumes the explicitly configured
collector through `tools.resume_settled_forecasts`. It does not duplicate a
running locked worker, clear a review pause, extend a deadline or initialize a
new experiment automatically. Startup uses the project's Python and hidden
process creation. The live collector was detected without spawning a duplicate.
No Windows reboot was performed to claim a new logon test.

The new read-only `settled_m5_forecasts` research field and shared typed/voice
answer distinguish fresh candidate sets from trade outcomes. The dashboard
source shows this status after the updated server code is loaded and the page
refreshed; the active trading backend was not restarted merely for display code.
The old calibration collector's blocked status is retained separately.

## Remaining work

Full prospective trade outcomes, two-stage qualification, a natural automated
broker lifecycle and automatic visible chart cycling are not completed by this
repair. Chart cycling still needs verified screenshot symbol/timeframe handling
before activation, to avoid using an H4 view as M5 evidence. Existing strategy,
risk and execution policies remain unchanged.

Portable verification: `FORWARD_COLLECTOR_REPAIR_20261119.json`. Actual collector
progress remains in its local status/journal files; the portable snapshot does
not pretend to be continuously updated.
