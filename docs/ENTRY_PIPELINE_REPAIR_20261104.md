# Entry pipeline and event-journal repair — 4 November 2026

## Entry correction

The confirmed defect was a mismatch between the breakout/retest strategy and the
generic location supplied to timing. A directional `gold_breakout_retest` signal
could include a retest while the generic context still said `breakout`, which the
existing fresh-entry gate rejects.

`GoldBreakoutRetestStrategy.confirmed_entry_evidence()` now recomputes the strategy
on the current frame and verifies an ordered breakout followed by a held retest
inside its configured confirmation window. The signal must still satisfy the
original direction, follow-through, EMA, body, and confidence calculations. Bar
times must be present, ordered, and unique.

The small adapter in `atlas_ai/analysis/entry_confirmation.py` resolves the timing
location to `retest` only when that evidence exists for the selected strategy and
side, and only when the generic location is `breakout`. It leaves the original
context unchanged. `AtlasTrader.step()` records the original/resolved locations and
evidence in `entry_location_resolution` before calling the existing timing gate.

This intentionally changes timing admission for verified retests. Plain breakouts,
retests before the breakout, saved confirmations unsupported by the current frame,
unusable timestamps, other strategies, and mid-range locations receive no exception.
Momentum, visual vetoes, higher-timeframe alignment, risk controls, approval, volume,
and pilot restrictions still apply. A flat signal's timing detail now explicitly
says the check is not applicable and does not represent entry approval.

No risk or execution source files changed. Raw strategy signal formulas and outputs
were preserved. The stored pilot still permits continuation only; corrected breakout
candidates must pass that later restriction rather than silently gain permission.

## Journal repair

The unresolved pointer formerly at `storage/events.jsonl` was preserved verbatim at:

`storage/archive/missing_events_lfs_wqj9py9q.pointer`

A valid forward journal was established with one explicitly attributed system event.
`storage/event_history_gap.json` retains the original object hash, expected size,
backup path, and `recovered: false`. The missing 261,418,685-byte historical body was
not recovered or reconstructed. No historical trading record was invented.

`tools/repair_event_journal.py` provides the repeatable offline repair. It refuses
mixed pointer/event files, existing unresolved manifests, and pointers whose original
object is available locally. Ordinary journals are left unchanged. Its CLI refuses
repair while an Atlas runtime is active. A second run on the repaired local journal
returned unchanged.

`tools/diagnose_trade_pipeline.py` now reports missing files/LFS pointers, retained
history gaps, and separate latest-event and latest-trading-decision timestamps.
An empty cutoff window is explicitly unavailable evidence, not proof of zero trades.
The new repair event therefore cannot masquerade as a fresh trader decision.

Protected runtime flags, account configuration, saved status, and heartbeat were
verified unchanged during the journal operation.

## Test-isolation corrections found during verification

The first full run exposed a replay harness reading freshly refreshed macro data
into a historical fixture. It shifted conviction from the stored 0.57 to 0.58.
Replays now suppress online macro refresh and use an isolated macro context. The
existing baseline values were kept unchanged.

A subsequent run exposed two broker reconciliation tests depending on actual MT5
initialization while the terminal was updating. Those tests now supply their own
terminal state. `tests/conftest.py` prevents unmocked MT5 initialization, login, and
order submission throughout the suite. Production broker behavior is unchanged.

## Verification

| Check | Result |
| --- | --- |
| Final full suite | 1,402 passed; no failures/errors/skips; 189.70 seconds |
| Broader focused checks with broker guard | 87 passed |
| Entry, replay, journal, and diagnostic checks | 32 passed |
| Fixed historical window | 460 M15 bars, 3–7 August 2026 |
| Before/after backtest | 192 simulated trades both times; all recorded metrics equal |
| Raw breakout/retest signal comparison | All 460 frame outputs equal, including 31 directional frames |
| Location-only timing probe | 22 ordered retests verified; 9 directional frames received no exception |
| Risk/execution source | Unchanged from commit `55b9e40` |
| Dependency integrity | `pip check` passed |

The historical backtester does not invoke the live timing adapter. Its unchanged
trade list demonstrates preserved raw/backtest behavior, not unchanged live timing
admission. Adapter and trader-step tests exercise the intended admission correction.
The location-only probe supplies strong momentum to isolate location resolution;
its counts are not executable trades or profitability results.

Baseline artifacts:

- `docs/baselines/baseline_20261104T074059Z_before_confirmed_retest_repair.json`
- `docs/baselines/baseline_20261104T074803Z_after_confirmed_retest_repair.json`
- `docs/baselines/confirmed_retest_repair_20261104_comparison.json`
- `docs/diagnostics/confirmed_retest_location_probe_20261104.json`
- `docs/diagnostics/event_journal_repair_20261104.json`
- `docs/diagnostics/entry_repair_verification_20261104.json`

The frozen input frame, original raw-signal vector, full test logs, and JUnit results
are in:

`C:\Users\rv010\AppData\Local\Temp\atlas-entry-repair-0ad69920d5e7400da8d60c95fd56a596`

The initial failed test runs remain there for inspection. The final full suite used
the corrected test isolation and broker-operation guard.

## Operational state

Atlas remains stopped under the saved October 23 shutdown instruction. No Atlas
backend or automatic restart task was started. The fixed-window capture read market
history through MT5 with execution disabled; subsequent comparison reused frozen
bars and blocked broker operations. No real order was submitted for this repair.

An explicitly requested demo restart is still needed to collect fresh forward
decisions. That will not override existing entry or pilot restrictions. Missing
historical journal data remains an external recovery gap, clearly recorded on disk.
