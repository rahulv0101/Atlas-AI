# Autonomous research and trade acceptance ? 9 November 2026

## Historical correction

The operator states most or all historical trades were manual. Broker comments, magic values, expert reason codes and archived Executed messages cannot establish who chose a trade. Prior findings are corrected accordingly: historical broker activity is manual/unverified for autonomous acceptance. Raw history and reward records were preserved. They were not promoted into verified autonomous outcomes.

## Confirmed defects and corrections

1. The background evolution scheduler was disabled. `EVOLUTION_ENABLED=true` now activates the new, explicitly bounded `EVOLUTION_RESEARCH_ONLY=true` worker. This is separate from the legacy promotion path.
2. The legacy shadow path replays historical bars and can repeat/overlap its training evidence. It is unsuitable as proof of forward performance. The new worker uses an explicit training/held-out split, frozen candidate rules and subsequent new closed bars for forward paper evaluation. It never calls the legacy broker-promotion path.
3. Generated-strategy ATR distances were returned in price units in fields named stop/take-profit points. The strategy factory now divides ATR price distance by point size; the legacy shadow consumer converts points back into price distance. Research and evolution evaluation pass the explicit configured point size. The XAUUSD deployment uses 0.01. This corrects the existing contract; strategy thresholds, monetary risk limits and execution authorization gates were preserved. The correction can change generated strategies' protective distances, so prior results are not interchangeable with corrected evaluations.
4. Fill-only lifecycle accounting did not establish that an open trade had been observed under protection. The new acceptance check additionally requires broker-observed valid SL/TP on the open position. A completed fill cycle without that observation remains management-evidence-missing.
5. Forced demo/probe flags were not carried into durable decision evidence. They now propagate from trader status, and forced entries are excluded from the autonomous decision index and acceptance check.

6. Final rollout verification exposed a stale-snapshot runtime write race: trader guard/learning/alert saves could overwrite newer launcher and execution-control state. All six trader writes now update only their owned fields under the existing atomic runtime update API. A regression preserves a newer execution-disabled control and completed startup while saving guard counters. The focused runtime/launcher/store/UI regression passed 163 cases.

## What strategy creation now does

The worker derives a regime from closed training candles, designs proposals using Atlas's existing bounded strategy-invention library, and generates bounded mutations. It creates up to six validated candidates per batch, every six hours. This combines and varies permitted rules; it does not write or execute arbitrary Python, change live strategies from chat memory, or retrain without limits.

For each frozen batch:
- The first 70% of closed bars form the training segment. Candidate construction cannot see the held-out segment.
- The last 30% supply an explicitly historical holdout. This is distinct from forward paper observation.
- Signals use only prior/closed candles. Hypothetical entries occur at the next bar open, with nonoverlapping trades, conservative stop-first ambiguous bars and existing session cutoffs.
- Recorded spread and configured hypothetical slippage are charged in stop-risk units. Commissions are not supplied, so these are not executable net-profit claims.
- Forward evaluation starts after the batch's creation window, records only new outcomes and persists a cursor across restarts. Missing retained data is flagged as a gap. Incomplete horizons do not become completed results.
- Candidate rules, split dates and compressed candle snapshots with SHA256 hashes remain inspectable under `storage/strategy_research/`.
- Four batches remain active in memory/state; older research is archived. The preliminary warmup is preserved separately.

Every generated candidate is marked `research_only_not_broker_eligible`. The worker has no order-submission or promotion capability and uses execute_trades=False. It cannot silently insert a candidate into the trader's live/demo population. Promotion requires a separate concrete validation/policy decision. Current strategy entry and execution gates still govern normal demo trading.

The versioned real-data run created two candidates. Holdout results after recorded spread and assumed slippage were approximately -0.496 R/trade over 30 trades, and -0.295 R/trade over 13 trades. Both are negative and have limited samples. They provide no basis to activate either strategy. Detailed results and source-data hashes are in `docs/diagnostics/autonomous_research_versioned_cycle_20261109.json`.

## Autonomous broker acceptance

The read-only observer now polls every ten seconds. It requires all of:

1. A fresh successful guarded autonomous decision with a numeric broker reference.
2. A matching actual broker entry fill on the configured demo account.
3. Observation of the open broker position with valid protective SL/TP.
4. Correctly directed and chronologically valid balanced exit fills.
5. Broker confirmation that the position is no longer open.

Manual trades, forced probes, ambiguous links, reversed/invalid fill sequences, incomplete exits and missing inventory cannot satisfy acceptance. Broker history/account failures and stale observer evidence are exposed. A very short position may close between polls; the observer then reports missing management evidence rather than inventing it.

The previous observer's 33 healthy samples are preserved as an interrupted upgrade segment. The new 24-hour run began at 20:00:40 UTC / 22:00:40 Johannesburg time, worker PID 17812. Its data is `docs/diagnostics/autonomous_demo_acceptance_20261109.jsonl`, with an adjacent continually updated summary. Current acceptance is also published read-only to `storage/lifecycle_acceptance.json` and the dashboard Safety card. The Setup search card separately reports research candidate and forward-paper counts.

No diagnostic broker trade was forced. A naturally selected entry, management and exit in the repaired deployment remains pending until it actually occurs. Software repairs, backtests and manual broker orders cannot be substituted for this proof. R1,000 remains a daily objective, not a guarantee.

## Validation and deployment

The broad suite passed 1,753 cases, the final affected-component run passed 224, and the separate backtest suite passed 12. Deduplicated: **1,771 distinct passing cases**, zero final failures/errors. Earlier fixture failures are retained in diagnostic files; final tests supersede them. New regressions cover holdout isolation, cost/point units, closed bars, repeated forward bars, restart/corrupt-state handling, research/promotion separation, manual/forced exclusions, protective-stop observations and invalid fill sequences.

The exact configured demo account and zero position/pending inventory were verified before a clean backend/frontend restart through the normal launcher. Live risk controls and real-money prohibition were retained. Final launcher, browser and observation evidence is recorded in the artifacts below after completion.

## Evidence

- `docs/diagnostics/autonomous_test_summary_20261109.json`
- `docs/diagnostics/autonomous_research_versioned_cycle_20261109.json`
- `docs/diagnostics/autonomous_research_deployment_20261109.json`
- `docs/diagnostics/autonomous_ui_smoke_20261109.json`
- `docs/diagnostics/autonomous_demo_acceptance_20261109.summary.json`
