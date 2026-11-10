# Entry evidence repair — 9 November 2026

Two confirmed defects were repaired in the visual-evidence boundary:

1. Missing, malformed, timezone-naive or future capture timestamps could be
   treated as fresh. These records are now rejected for fresh evidence use.
2. Trader cache reuse did not validate the record's symbol and timeframe. Both
   reuse sites now require matching configured context. A rejected cache follows
   the existing capture/analysis fallback; it cannot supply cached confirmation
   or a cached veto for a different context.

The loader exposes `rejection_reasons`. Non-object JSON is also rejected cleanly.
Valid aware timestamps, including SAST offsets, remain accepted. This validates
record metadata; it does not prove that a terminal screenshot displays the stated
instrument or that the image parser understands it correctly.

Strategy evidence now explicitly identifies the current filter's allocator reward
statistics and the shadow filter's broker-confirmed closed-position statistics.
The live allocator and filter thresholds have not been reset or changed.

The reviewed current-journal window contained 20 timing-rejection records, 20
no-directional-signal records and 3 higher-timeframe alignment conflicts. These
are logged records in a bounded window, not distinct market opportunities. The
current mid-range/mixed-momentum rejection is consistent with existing checks;
these software repairs do not establish that it was a false rejection.

Validation: **226 tests passed**, including chart evidence, trader learning,
signal generation, confirmed-retest translation, closed-position accounting,
guarded execution, replay and UI API. New regression cases cover absent/invalid/
naive/future/expired timestamps, wrong or missing symbol/timeframe, a valid SAST
timestamp, and invalid JSON root types.

The R1,000 daily demo objective, 3% daily and 6% weekly drawdown thresholds,
Gemini advisory-only choice and other deterministic gates remain unchanged.
Native demo account and zero position/pending inventory were checked before
the guarded reload. No diagnostic order was sent.

The missing historical journal, unproven profitability, insufficient strategy
attribution and lack of a newly demonstrated natural entry-management-exit remain
evidence limitations. They cannot be repaired by inventing outcomes or sending
an artificial trade.

Artifacts:

- `docs/diagnostics/entry_evidence_tests_20261109.xml`
- `docs/diagnostics/entry_blockers_20261109.json`
- `docs/diagnostics/entry_evidence_live_20261109.json`
