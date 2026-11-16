# Fixed sweep, structure-break and retest hypothesis

This research redesign tests a complete sequence instead of immediately buying
or selling a short local reclaim. It has no broker authority and is absent from
the live strategy inventory. No runtime risk, execution, volatility, confidence
threshold or position-management setting changes.

## Rules frozen before outcomes

1. D1, H4, H1 and M15 closed-candle direction must all agree. Entry is on M5.
2. A closed M5 candle must sweep and reclaim the prior twenty-bar liquidity
   extreme, with a wick at least 42% of its range.
3. Within the next three bars, the first crossing of a swing confirmed before
   the sweep must show displacement: at least 1.25 prior ATR and 60% directional
   body. The swing uses two already closed confirmation bars on each side.
4. Within six bars after the break, wait for the first visit to the broken
   swing zone. Its half-width is the greater of two symbol points or 0.1 prior
   ATR. Reuse the existing two-bar, first-visit retest rules: an earlier
   confirmation consumes the setup, a second visit is rejected, and a close
   through the far zone boundary invalidates it.
5. The entry confirmation must close beyond both the zone and the previous
   candle's opposite extreme, with at least 55% directional body. The quote
   must remain near that closed confirmation, using the existing geometry rule.
6. Protection stays beyond the sweep and entire episode extreme plus the
   existing buffer. A breached sweep extreme invalidates the sequence. There
   is no hindsight stop tightening.
7. The target is exactly 2R before costs, only when the existing nearest-HTF
   liquidity geometry already permits at least that distance. It does not
   extend through a nearer target obstruction.

These chart conventions are hypotheses, not proof of institutional activity or
a profitable edge. Constants reuse existing SMC conventions; no parameter grid,
best-lane selection or tuning against results is performed.

## Shared-system integration

`atlas_ai/testing/sweep_bos_retest.py` supplies a pure detector and a scoped
research feature adapter. The adapter reconstructs the sequence from closed
candles, quote and higher-timeframe context for this exact research name before
supplying `fresh_retest`/`turning` evidence. It cannot approve an order. Other
strategy names keep their original feature path, and the original method is
restored after the isolated research context exits.

`tools/research_sweep_bos_retest.py` freezes a source snapshot and protocol,
creates receipt-bound candidate streams before replaying outcomes, and denies
MT5 initialization and order submission. It reads existing archived candles;
there are no native terminal history queries or backend restarts.

Replay uses the existing session, risk, minimum-lot, spread/cost, margin,
volatility, timing, conviction, daily/weekly loss and management checks. The
one-hour holding cap, stale exit, break-even and trailing behavior stay fixed.
R100,000 is virtual starting capital with the existing 0.5% maximum risk
fraction and 0.01-lot cap; it is not a request to deposit funds.

## Comparison and evidence limits

The control is the receipt-verified v8 control from the previous corrected-
coverage study: same archived data, eligible decision times, costs, settings and
chronological boundaries. Its outcomes are reused explicitly, not represented
as a new independent replay. Candidate counts differ in meaning: the new model
counts complete affordable sequences before shared timing/volatility/conviction
checks; the old control also prefiltered timing. Executed simulation results
remain the relevant shared-gate comparison.

The primary May-November 2026 history has three independently reset stages.
It motivated this redesign and is exploratory. April 2026 is disjoint but was
already inspected; it is not blind validation. Future prospective evidence is
still required. The decision grid uses the detector-native recent-twenty-bar
continuity requirement and complete twelve-bar outcomes contained within each
stage. No outcome feature is used by the detector.

Every primary stage and April must independently pass the existing minimum
thirty trades, at least two dates, positive mean net R, profit factor at least
1.1 and maximum drawdown no greater than 6R. Zero trades cannot qualify. A
historical pass would not grant broker authority or prove the natural automated
broker lifecycle. Intrabar results retain the existing conservative bar model;
exact broker tick order is not demonstrated.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tools.research_sweep_bos_retest `
  --reference storage/entry_horizon_coverage_20261116 `
  --baseline storage/smc_entry_rerun_20261116 `
  --archive storage/m5_stop_research_20261114 `
  --output storage/<new-unique-directory>
```

Portable measured results and receipt hashes: `SWEEP_BOS_RETEST_RESULTS_20261116.json`.
Full local evidence: `storage/sweep_bos_retest_v10_20261116`.

## Measured results

| New sequence stage | Trades | Wins | Net simulated rand | Review |
|---|---:|---:|---:|---|
| development | 0 | 0 | 0.00 | failed |
| validation | 0 | 0 | 0.00 | failed |
| holdout | 0 | 0 | 0.00 | failed |
| separate_validation | 0 | 0 | 0.00 | failed |

Complete affordable candidate sequences: **0**.
Historical review passed: **False**.

The matched control had fourteen primary-period simulated trades, four wins
and a descriptive sum of -R432.21 across independent stage resets. April
had no control trades. A zero-trade new proposal is unproven, not a profitable
improvement over a losing control. All stages retain their original review
requirements. No model or paper observer is activated by publication.

The lack of entries occurs inside sequence detection, before affordability or
shared execution gates can reject a complete candidate. Primary-period reported
window reasons were:

| Reported reason | Windows |
|---|---:|
| Higher-timeframe confluence absent | 20,004 |
| No reclaimed twenty-bar sweep | 4,263 |
| Sweep extreme subsequently breached | 521 |
| Awaiting displacement through the pre-sweep swing | 238 |
| First crossing lacked displacement | 18 |
| Awaiting first retest and rejection | 6 |
| Retest window expired | 3 |

These are final reported reasons per evaluated window, including repeated
observations of an episode; they are not independent setups or trades. April
reported 4,135 windows without confluence and 23 without a complete sweep.
The detector's synthetic buy/sell tests demonstrate that it can emit valid
sequences, but do not establish a market edge. This declared sequence has not
shown sufficient frequency on the available periods and is not activated.

A receipt-bound near-miss audit reconstructed all nine reported retest windows with identical rejection reasons. This confirms reproduction, not a profitable repair. Run tools.audit_sequence_near_misses to retain the candles and reasons in a separate local audit. No thresholds or live policies changed.
