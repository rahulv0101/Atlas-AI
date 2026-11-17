# Deployed M5 replay status

`tools.deployed_m5_parity.py` runs the configured M5 base inventory against
receipt-checked native archived candles through the existing shared policy
replay. It does not submit orders, activate a model or change runtime settings.

The protocol freezes sanitized settings, input hashes, source hashes and the
previous demo broker specification/limits. Virtual capital comes from the
configured backtest balance; it is not a fresh measurement of broker equity.
Historical cash conversion, fees, margin and pilot limits are frozen prior
snapshots, not proof of current broker parity.

The diagnostic records individual first-rejection reasons. A separate strict
screen refuses candidates reaching the point where historical visual, macro
and execution evidence is unavailable. A strict refusal is missing evidence,
not a demonstrated losing trade or a zero expected live frequency.

Missing historical learning/ranking state, visual and macro evidence, broker
quotes/occupancy, approval and ExecutionGate state remain explicit. The report
must retain `full_live_parity=false`, `frequency_claim_allowed=false` and an
unknown expected live rate while any such evidence is missing. It cannot
replace the live gate stack or support a full-system profitability claim.

The initial run is `storage/deployed_m5_parity_20261117T205724Z`.
Consult its progress and signed report; absence of a report means unfinished.
No completed result is claimed in this document.

Automatic visible MT5 switching and natural strategy-selected broker lifecycle
verification remain separate outstanding work. The earlier manual chart cycle
did not implement autonomous switching. Neither this diagnostic nor a display
fix proves profitability or completes that lifecycle.
