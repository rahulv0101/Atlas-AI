# Operator-approved M5 confluence policy

The operator explicitly selected M15 plus either H1 or H4 on November 19, 2026.
The entry gate now requires available closed-candle M15 evidence matching the
candidate, plus available matching H1 or H4 evidence. D1 is context only.
The other H1/H4 timeframe may disagree, be flat or unavailable. Missing, stale,
flat or opposing evidence cannot count as confirmation. Invalid context fails.
This changes the top-down M5 entry policy, not strategy generation or risk limits.

The context `aligned` field still reports four-way directional agreement for
analysis; it is not the entry gate. Execution uses `entry_gate.passed`.
The existing aggregate-bias conflict check cannot independently restore unanimity:
aggregate bias is directional only when all four agree; otherwise it is mixed.

Tests cover every combination of buy, sell, flat and unavailable across four
frames for both entry directions, plus invalid metadata and existing closed-bar
freshness tests. Passing these tests does not establish profitability.

Frozen earlier research records remain under their original protocol. The earlier
settled collector was found paused with terminal_attach_failed; its protocol is
not rewritten or resumed against changed source hashes. New-policy validation
must use a separately identified experiment.
