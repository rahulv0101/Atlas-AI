# Structural timing handoff and capital-profile correction

This work repairs a specific research evidence handoff. It does **not** turn a
failed strategy into a qualified broker model or alter Atlas's live gates.

## Two problems established

The deterministic candle-feature functions emit generic range-percentile
locations and `strong`, `weak` or `mixed` momentum. They do not emit a verified
FVG retest/sweep location or `turning` momentum, although the shared timing gate
explicitly accepts those classifications. The earlier research adapters passed
only signal fields into that generic feature path. Thus actual structural
evidence could be lost before timing checks.

A controlled OHLC fixture reproduces the problem: a valid sweep/reclaim is
blocked with generic mixed momentum, then accepted by the **same** timing
method when independent reconstruction supplies the structural evidence.

Separately, prior risk-budget results used R10,000 nominal research capital
(R50 at 0.5%). A read-only query found the configured demo has capacity above
the conservative R100,000 test tier. The R50 rejection results remain valid
for the small-capital scenario; they cannot establish unaffordability on that
current demo account. No account balance, lot cap, risk percentage or `.env`
setting was changed. Exact account information remains in ignored storage.

## Evidence adapter

`atlas_ai/testing/structural_timing.py` reconstructs evidence from closed M5
candles rather than accepting a strategy label:

- Require all-four Daily/H4/H1/M15 alignment and fresh quotes/context.
- Reconstruct the actual five-bar sweep or confirmed FVG formation/first
  visit from its OHLC sequence, validating claimed levels against candles.
- Require the first directional closed body of at least 55% of candle range
  beyond both the previous candle's opposite extreme and the setup's
  confirmation level. A weak candle cannot merely be renamed `turning`.
- Reject stale anchors, repeated confirmations, second FVG visits, invalidated
  zones and breached original protection. Forming candles cannot help.
- Supply `sweep_rejection`/`fresh_retest` and `turning` only after those checks.
  Preserve the generic classifications alongside the verified evidence.

The adapter is explicitly scoped to two v8 **research** names in an isolated
process. Unrelated strategies retain identical features; the original method
is restored after the experiment. The live trader's feature method, risk,
volatility, conviction and execution policy are unchanged. Nothing here
registers a new executable strategy or sends an order.

## Frozen matched comparison

The source population is the frozen v7 scan, including 29 raw micro-sweeps
and no complete FVG candidates. It is not a new search across all chart bars.
Source receipts, code and candle hashes are checked; rules and new predictions
are frozen before generating outcomes. All data are previously inspected
retrospective history, not independent validation.

There are three distinct capital/evidence comparisons:

1. **Original R10,000 scenario with evidence:** twenty observations verified a
   structural location/turn. Nineteen failed cost-inclusive minimum-lot sizing;
   one failed the current nearest-target 2R requirement. No trade resulted.
2. **R100,000 matched control without structural evidence:** zero candidates
   and trades. Increasing virtual capital alone did not solve timing.
3. **R100,000 with verified evidence:** nineteen candidates, of which nine were
   blocked by the unchanged volatility guard; ten were simulated.

The capital tier is chosen mechanically as the largest power of ten not above
the fresh matching demo balance. It is not selected to maximize outcomes.
The two R100,000 comparisons have identical input observations, specification,
costs, risk fraction and caps. Only structural feature supplementation differs.
The 0.01 lot cap remains, so larger virtual capital does not enlarge orders.

| Stage, independently reset | Simulated trades | Wins | Net cash | Review |
|---|---:|---:|---:|---|
| Development | 5 | 0 | -R355.35 | Failed sample and performance checks |
| Validation | 1 | 0 | -R71.68 | Failed sample and performance checks |
| Holdout | 4 | 4 | +R385.42 | Failed minimum thirty-trade sample |

These are three separate stage replays, not a demonstrated live portfolio.
Four holdout wins do not override failed development/validation or qualify the
model. The FVG path remains untested on actual candidates in this population.
The software handoff can be repaired while the strategy still lacks an edge.

No model qualified, no new broker strategy was activated, and natural broker
entry/protection/exit remains unproven. Further policy or strategy changes need
their own declared experiment and separate evidence; these results do not
justify loosening controls or assuming profit.

## Artifacts and operation

- `storage/smc_structural_evidence_v8_20261116_v2`: original small-capital scenario.
- `storage/smc_structural_v8_capacity_control_20261116_v2`: matched control.
- `storage/smc_structural_v8_capacity_20261116_v2`: corrected handoff/capital study.
- `docs/STRUCTURAL_TIMING_RESULTS_20261116.json`: portable metrics and receipts.

`tools/research_structural_timing.py` supports an explicit signed `--capacity`
snapshot and `--control-without-evidence`; it never silently changes the default
research capital. Capacity evidence must be fresh, demo-scoped, match the
source's account/currency/minimum lot and retain its risk fraction. The operator
view publishes completed research through the existing read-only path, with
no change to broker or paper-observer authority.

The v1 artifacts were rejected before publication because the final buffered
prediction-log bytes had not been flushed before its receipt was calculated.
The prediction boundary now flushes before hashing and verifies immutability
again after replay. All three scenarios were rerun in fresh v2 directories;
old receipts were not retroactively repaired after seeing outcomes.

Seventy-six focused checks passed, including positive/negative structural
reconstruction, first-confirmation freshness, method restoration, unrelated
strategy preservation, capacity-scope guards and existing research/replay
integration. The operator view reports no qualified candidate.
