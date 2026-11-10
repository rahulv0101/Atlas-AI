# Restart-safe broker lifecycle observation

Fixed an evidence-continuity defect in the read-only demo observer. Its baseline fill IDs, newly observed fills and observed protection IDs previously lived only in memory. Restarting could discard the entry/protection evidence required to verify a later exit. A completed process also left a last acceptance packet without an explicit completed-observer state.

The observer now saves atomic checkpoints after journal publication and supports explicit `--resume`. Checkpoints are bound to the configured account/server, symbol, magic and exact journal path. Missing/corrupt/incompatible checkpoints fail rather than silently resetting the baseline. A storage-scoped OS lock rejects duplicate checkpoint-aware collectors. The running/completed state and bounded window end are published separately from actual trade acceptance.

Restoring a checkpoint never fabricates a missed observation. A trade with no observed broker protection remains unverified. Existing natural-trade requirements, manual/forced-diagnostic exclusions and matching-demo checks are unchanged. The collector has no order submission or strategy promotion path. It does not automatically restart itself after Windows reboot; explicit resume uses the saved evidence and a new bounded duration.

Verification passed 27 checkpoint, lifecycle and atomic-publication tests. The integrated resume test began with a saved entry and protective-position observation, then received only an exit from the fake broker and verified a balanced flat lifecycle with zero orders. Other cases reject wrong account/server/symbol/magic, mismatched journals, corrupt evidence and duplicate observers. Missing protection still fails acceptance.

Live cutover first captured and validated a matching, flat demo sample in a new journal. The legacy observer's summary was backed up locally, and only that identified read-only process was stopped. The validated journal then resumed for seven days, through November 17 at approximately 18:30 UTC. The trading backend and frontend stayed running. The new collector's live PID was 32924; it published fresh broker/history checks and a valid checkpoint after multiple samples, with zero orders and no verified autonomous lifecycle yet. Process IDs are historical deployment evidence, not a permanent service identity.

After the current collector has stopped, it can be resumed explicitly with a bounded duration, for example:

```powershell
.venv\Scripts\python.exe tools/observe_day_trading.py --resume --minutes 1440 --interval-seconds 10 --output docs/diagnostics/autonomous_demo_checkpoint_20261110.jsonl
```

Do not start a second collector while the existing one is running. Raw journals, account-derived checkpoints, migration metadata and test XML stay local under `docs/diagnostics` and `storage`. This repair preserves evidence collection; it does not establish profitable candidate selection, measured fill costs where no fills exist, or the cause of the earlier native crash.
