# Demo performance-filter correction (activated with operator approval)

Confirmed issue: the current strategy performance veto uses allocator reward
observations, which include open-position updates and initial priors. EMA
Crossover is excluded using 3,204 reward observations, and Trend Pullback using
84. These are not verified counts of completed strategy trades. Their reported
win rates must not be treated as such.

An explicit opt-in is prepared: STRATEGY_FILTER_EVIDENCE_SOURCE=confirmed_demo_positions.
The code default remains allocator_rewards. The operator explicitly approved
activation on demo, and .env now selects confirmed_demo_positions.
The new source uses the existing ledger of broker-confirmed, balanced, flat,
strategy-linked, non-test demo positions. The ledger validates the configured
demo account. Unavailable, malformed, future or older-than-180-second evidence
fails closed. A strategy with insufficient verified history receives no learned
performance veto; it remains unproven. Existing sample thresholds and win-rate
rules still exclude strategies when sufficient confirmed evidence is poor.

Preview: current eligibility contains six strategies; proposed eligibility adds
ema_crossover and pullback_trend. There are zero verified strategy-linked closed
positions. This is eligibility only, not evidence that these candidates should
be traded, that blocked trades were profitable, or that any gate will clear.
Confidence, timing, alignment, consensus, risk and execution checks remain.
Allocator statistics and stored history are not reset or rewritten.

Validation: 114 tests passed, covering the new source, closed-position ledger,
trader learning, signal generation, confirmed retest adapter and settings
precedence. Regression cases cover legacy default preservation, good and bad
confirmed outcomes, invalid/stale evidence, no mutation of legacy reward state,
and unknown source rejection. An additional 38 risk, cross-process execution-gate, guarded-demo and pipeline
checks passed (152 tests total across the two runs). No diagnostic order was
submitted.

Artifacts: docs/diagnostics/performance_filter_proposal_20261109.json and
performance_filter_proposal_tests_20261109.xml. The operator explicitly approved activation in chat. The backend was stopped
cleanly after matching-demo and zero-exposure checks, then relaunched through
the normal launcher. Runtime verification confirms both strategies eligible,
the confirmed evidence source active, and unchanged risk limits, daily demo
objective and advisory-only Gemini. Launcher completed SUCCESS with desktop
ready. The current HOLD remains a decision under the remaining entry gates.
Activation proof: docs/diagnostics/performance_filter_activation_20261109.json.
