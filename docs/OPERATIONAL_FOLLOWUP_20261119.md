# Operational follow-up

## Collector continuity
The prior v2 collector stopped with terminal_attach_failed. The configured terminal
executable exists and a read-only attach succeeded on November 19. No original
failure snapshot establishes a more specific cause. A single attach failure now
receives at most three consecutive attempts, 15 seconds apart. Success resets the
counter. Account mismatch, source changes and candle revisions still stop for
review immediately; the checkpoint is never reset. No login or order is allowed.

A fresh v3 experiment freezes the currently approved M15-plus-H1-or-H4 policy
and visual-advisory timing source. Old v2 evidence is untouched. The active pointer
now selects v3; startup resume detects its held lock without spawning a duplicate.
The first prospective candidate set was published successfully. These remain
ATR-corrected research candidate forecasts, not full live-policy executions,
resolved paper outcomes, strategy qualification or broker fills.

## Gate evidence
`python -m tools.review_gate_evidence --output docs/GATE_EVIDENCE_20261119.json`
provides a bounded tail report. The initial 500 publications contained 375
directional publications, all timing-blocked. It includes old visual vetoes and
both confluence policies. Candidates can recur; these are not 375 unique trades.
Unrecorded outcomes are explicitly unknown. This report cannot establish a
counterfactual survival rate or expected trades per day. Preserve policy-specific
prospective evidence instead of pooling before/after observations.

## Crash status correction
The earlier generic unresolved-crash summary overlooked existing evidence in
FOUR_ACCEPTANCE_TASKS_20261110.md. An isolated subprocess probe reproduced an
asynchronous faulthandler timer crash without Atlas or MT5. The tracked audit
runner avoids that timer; normal fatal-fault diagnostics remain enabled. Existing
native-diagnostic regression tests passed again. This supports the instrumented
audit crash mechanism, not a universal attribution for all historical events.
The hazardous reproducer was not rerun against the active trading system.

## Remaining acceptance work
Profitability, two-stage independent validation and a natural strategy-selected
entry/protection/exit require future qualified observations; they cannot be
completed by changing software or forcing trades. The forecast collector does
not yet evaluate outcomes. Automatic visible MT5 chart cycling remains
unimplemented: any integration must verify symbol/timeframe before screenshot
use and return to M5. No guessed chart-control automation was installed.

No new strategy, volatility limit, risk budget or broker authority was activated.
The running backend continues the explicitly approved confluence and visual
advisory corrections from the preceding commits. This repair does not require
restarting the trading backend or MT5.
