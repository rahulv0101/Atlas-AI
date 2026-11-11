# Seven-day inactivity review

The operational review runs from **11 November 2026, 20:31:56 SAST** to **18 November 2026, 20:31:56 SAST**. It requires at least one verified natural demo cycle whose entry and exit broker timestamps both fall inside that window. This is a minimum functional activity check, not a daily trade quota, a profitability test, or permission to bypass entry rules.

The account-scoped protocol, deadline, criterion and evaluator source hash are frozen locally under `storage/activity_review`. Initialization refuses to overwrite an existing protocol. The acceptance supervisor updates the report every minute while it runs, reusing the existing publication archive and lifecycle observer. It does not contact the broker itself or change trading settings. The backend and the original prospective experiment are unchanged.

## Reading the report

```powershell
.\.venv\Scripts\python.exe tools/review_activity.py report
```

The report is also at `storage/activity_review/status.json` and under `activity_review` in `storage/acceptance_plan.status.json`.

It separates technical/data blocks, execution controls, risk/safety blocks, missing directional signals, directional signals rejected by filters, analysis eligibility that still requires execution gates, and insufficient evidence. It counts structured blocker codes, directional strategy samples, session samples and strategy coverage gaps. Daily rows use SAST and explicitly distinguish days with no captured samples. Stale, future/unverified and out-of-window publications cannot qualify as fresh activity evidence.

Counts are **sampled publications**, not unique setups, trades, uptime percentages or missed profits. Several codes may accompany one observation; `reason_codes` includes supporting context as well as blocking reasons, so it is not a list of rejection causes alone. A strategy can signal repeatedly for the same opportunity. Missing observations are a coverage failure, not proof that markets offered no trades. The existing blocker-selectivity reports remain exploratory; favorable subsequent price movement alone does not prove an executable, profitable missed trade. Any filter revision needs its own predeclared, cost-aware experiment with untouched future evidence.

## End-of-window decision

- `observing`: the fixed window is still open, with no qualifying cycle recorded yet.
- `activity_requirement_met`: the original lifecycle evidence verifies a strategy-linked natural entry, observed protective SL/TP and balanced exit, with broker times inside the window. Manual/forced diagnostics do not count. This does not demonstrate a profitable strategy or sustained reliability.
- `activity_requirement_failed`: the window ended without that evidence, including when monitoring coverage was insufficient. Atlas's natural operation remains unverified. Review technical availability, signal coverage and rejection reasons before proposing a separate tested change.
- `blocked_review_required`: evidence, scope or integrity needs inspection; the supervisor keeps independent collectors running.

No outcome automatically promotes a strategy, loosens a gate, starts the backend or sends a broker order. The existing 30-day acceptance deadline and both 30-case paper stages remain unchanged. Local protocol, checkpoint and journal artifacts remain ignored by Git.

Validation: **84 focused checks passed**, covering the activity window, broker clock conversion, manual-test exclusion, incremental resume without double counting, zero-observation failure, evidence integrity and related observation/supervision paths. Local report: `docs/diagnostics/activity_review_20261111.xml`.
