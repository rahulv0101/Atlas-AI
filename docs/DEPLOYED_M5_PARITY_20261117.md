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
Consult its signed report and the completed result below. For future runs,
absence of a report means unfinished.

## Completed result

The initial run subsequently completed. Verified portable results are in
`DEPLOYED_M5_RESULTS_20261117.json`; the original signed local artifacts remain
in the run directory above. All 34,911 candidate bars are accounted for as
simulated trades or first-rejection events in each replay.

The diagnostic produced 47 simulated trades and 14 wins, net -R233.33 on
R10,000 virtual starting capital. Profit factor was 0.597, mean net return
-0.287R, and maximum drawdown 13.507R. This is a negative partial-parity
historical result, not a qualified strategy or a broker performance record.

The diagnostic's largest first-rejection counts were 23,448 higher-timeframe
confluence and 4,820 timing discipline. Session restrictions, loss-streak limits,
pilot setup family and volatility also rejected evaluations. Counts represent
repeated candidate bars, not distinct missed opportunities or causal estimates
of what would happen if a guard were removed.

The strict screen made no trades and rejected 48 otherwise eligible
evaluations for unavailable historical visual/macro/execution evidence. Its
other counts differ because it never records simulated executions or losses.
Do not subtract these counts from the diagnostic as if both had identical
portfolio state. No expected live trades/day can be inferred.

The exporter verifies protocol and candidate receipts, research-only authority,
and full candidate accounting. It also exposes current source hashes compared
with startup hashes. The runner's reporting code changed after launch; the
trading and shared replay source hashes remain independently inspectable. The
run was not retroactively re-signed or presented as a newly frozen rerun.

Future runs label the diagnostic and strict replay phases explicitly and save
a signed diagnostic checkpoint before the strict screen. Seven focused checks
cover refusal of altered artifacts, broadened authority, invented frequency
and missing candidate accounting.

Automatic visible MT5 switching and natural strategy-selected broker lifecycle
verification remain separate outstanding work. The earlier manual chart cycle
did not implement autonomous switching. Neither this diagnostic nor a display
fix proves profitability or completes that lifecycle.
