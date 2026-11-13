# Confidence-penalty audit

The audit traced the existing runtime methods on an isolated read-only snapshot. No trading, risk, learning-memory or execution-policy changes were made. The current publication's eight candidate outputs were reproduced exactly using the captured learning state, and source files remained stable during that audit. This is a post-publication reconstruction, not an atomic pre-decision checkpoint or proof that every running module matches its on-disk version.

## Findings

The historical class-count penalties read `historical_loss_analysis` in learning state. Its recorded source is a **26 May 2026 historical backtest**, about 171 days old at this audit: 3,000 M1 bars, 303 simulated trades, 124 wins and 179 losses. Its classification totals are computed from sampled losses, not from a matched comparison of winners and losers under each entry condition.

| Historical loss class | Stored count | Existing count threshold | Conditional score multiplier |
|---|---:|---:|---:|
| Weak pullback | 72 | 50 | 0.82 for weak pullback momentum, or 0.90 at mid-range, for specified strategies |
| Stop hunt | 55 | 40 | 0.86 when wickiness is at least 0.55 |
| Late entry | 47 | 40 | 0.88 at breakout/extension conditions |
| False continuation | 5 | 3 | 0.90 for specified strategies without strong momentum |

There is **no expiry or recency check in this count-based path**. Several rules use global loss totals across strategies and conditions. Multiple applicable reductions can compound, with a 0.60 floor on this heuristic multiplier before the separate pattern-lesson adjustment. These numbers are programmed heuristics, not calibrated win probabilities.

The previously observed approximately 14% reduction is explained by the stop-hunt count and wickiness condition. A synthetic control using the real methods and stored state reproduced 0.50 → 0.43. A lower-wick control retained 0.50. These synthetic controls establish code behavior only; they are not market trades or evidence that disabling the penalty improves returns. Current candidate suppression can also happen before timing learning is reached.

The second layer, `_loss_pattern_lesson_adjustment`, matches fingerprints and may apply another bounded reduction. It requires at least two samples, at least one loss and a loss rate of at least 0.50, with exact/strong-partial matching and correction checks. The enclosing method returns early if the historical class-count dictionary is empty, so the two learning layers are coupled even though they read different evidence.

## Manual, diagnostic and broker provenance

Retained recent lesson memory contained **183 historical-backtest outcomes and 16 broker-recorded outcomes**. Three explicitly tagged manual plumbing tests were already excluded; no tagged manual or forced probes remained in that recent window. The aggregate driving the 0.86 multiplier had 179 historical-backtest loss samples, so those known manual tests do not explain that specific reduction.

A numeric broker ticket establishes neither autonomous strategy attribution nor a protected entry-to-exit lifecycle. Ordinary manual trades not carrying the diagnostic tags cannot be identified reliably from those tags alone. Context linkage is also different from execution verification. The audit therefore does not label the 16 broker-recorded outcomes as verified autonomous strategy evidence. Existing cached pattern lessons mix sources and do not retain a per-source contribution ledger.

## What the evidence does and does not support

The source and application of the penalty are now reproducible. Its **benefit remains unestablished**. Loss counts, a fingerprint match and bounded coefficients alone cannot demonstrate better future net returns. The existing timing-discipline matched backtests study the entry veto; they do not independently validate these confidence reductions as a separate policy change.

The next useful experiment would freeze one matched comparison of unchanged behavior versus a specifically defined penalty alternative, charge realistic costs, preserve every rejected/selected case and evaluate untouched future outcomes. Neither the fixed heuristic nor an alternative should be called validated before that test. Removing a penalty without evidence could admit worse entries.

## Reproduce and retain evidence

Run `.\.venv\Scripts\python.exe tools/audit_confidence_penalties.py`. Its local JSON report is `storage/audits/confidence_penalty_audit.json`. It includes input/code hashes, source counts, per-candidate stage traces, one-count-at-a-time score sensitivities, replay comparisons and clearly labelled synthetic controls. It does not write learning or runtime state, construct an execution adapter, send broker orders or rerun a historical market search.

Future publication archives now preserve `signal_generation` diagnostics and `historical_loss_analysis` so subsequent audits can inspect those inputs. Existing archive records remain unchanged, and the archive remains sampled, redacted and non-authoritative. This does not fill the old pre-decision evidence gaps. The trader and frozen experiments were not restarted or modified for this audit.

Validation: **53 focused tests passed**, covering real-method reconstruction, manual-test provenance, conditional reductions, distinct lesson stacking, the empty-aggregate coupling, prior suppression, archival redaction and independent supervision. Report: `docs/diagnostics/confidence_penalty_audit_20261113.xml`. Only the read-only acceptance supervisor was restarted to enable the additional archived diagnostic fields.
