# Fixed M5 confirmation and target-horizon study

The previous ten-trade diagnosis suggested weak early M5 follow-through and
targets that were rarely reached within the configured one-hour holding cap.
Those observations motivated a fixed research proposal; they do not prove a
profitable filter. No live trading policy is changed by this study.

## Declared comparison

Four lanes use identical historical inputs, costs, R100,000 virtual starting
capital, 0.5% maximum risk fraction and 0.01-lot cap. Each chronological stage
resets independently. The control uses the verified v8 sweep/structural-timing
handoff. The interventions are:

| Lane | Extra M5 confirmation | Target package |
|---|---|---|
| Control | None | Original nearest HTF target |
| Entry only | Two consecutive aligned 8/21-close M5 trend readings and a close beyond the prior confirmed two-left/two-right swing | Original |
| Target only | None | Exact 2R target, only if original HTF geometry permits it and the distance fits the median of past closed one-hour ranges |
| Combined | Same extra confirmation | Same target package |

The target screen examines the latest twenty nonoverlapping twelve-M5-bar
blocks, requires at least twelve contiguous valid blocks, and uses no forming
or future candle. An hourly range is a rough feasibility reference, not an
estimate of a future directional move. The target package changes two related
properties (distance and eligibility); this comparison does not isolate them.

Natural protection, signal confidence, spread/cost assumptions, volatility
guard, affordability, session/risk limits, one-hour maximum hold, stale exit,
break-even and trailing management remain unchanged. No stop is tightened to
make an entry affordable. Confirmation retains the original three-bar window.

Only the combined lane was nominated for hypothesis review. The other lanes
are attribution controls, not alternatives from which to choose a retrospective
winner. There is no parameter search, automatic promotion or broker authority.

## Evidence and coverage

The primary May-November 2026 period motivated this proposal and is exploratory.
April 2026 is a separate, disjoint historical period with native higher-timeframe
warmup, but was already available and inspected in prior work. It is neither
blind validation nor prospective proof.

The first frozen study, `storage/entry_horizon_proposal_20261116`, inherited an
80-prior-bar continuity screen. It reproduced the original control's ten trades.
Its target-only package produced eight trades and -R220.84 summed across stage
resets; the extra-entry and combined lanes produced none. April had no eligible
aligned windows under that inherited screen. These results remain retained.

Inspection then found that the actual v7 detector requires only the latest
twenty M5 bars to be consecutive. Requiring eighty additionally excludes hours
after closures. The new study, `storage/entry_horizon_coverage_20261116`, freezes
the same intervention parameters and regenerates both periods using the actual
twenty-bar requirement. Every scored window still requires twelve future bars
for complete outcome availability, within its own chronological stage; entry
features themselves use closed past data only. This coverage correction does
not promise new trades or better returns. Old and new results are separate.

Raw detections are frozen before intervention evaluation. Candidate streams are
closed and receipt-hashed before shared portfolio outcome replay. Protocol,
source snapshot, raw observations, candidate streams and outcomes have SHA-256
receipts. The optional publisher verifies these before updating only Atlas's
existing read-only research comparison pointer. Paper observers and broker
configuration are unaffected.

## Acceptance and limits

Every primary chronological stage and the separate historical period must each
have at least thirty trades over at least two dates, positive mean net R, profit
factor at least 1.1, and maximum drawdown no greater than 6R. A pass would still
require independent review and prospective evidence before any policy decision.
No trades is an inconclusive strategy result, not a successful validation.

This is a shared-gate/management historical simulation of the declared sweep
hypothesis. It is not a backtest of every Atlas strategy, a broker tick replay,
or evidence of a natural automated broker lifecycle. Exact intrabar tick order
remains unverified. The FVG family is outside this intervention study.

Portable measured results and receipt links are recorded in
`ENTRY_HORIZON_RESULTS_20261116.json` when the corrected-coverage run completes.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tools.research_entry_horizon `
  --reference storage/smc_structural_v8_capacity_20261116_v2 `
  --patterns storage/smc_aligned_v7_20261116 `
  --baseline storage/smc_entry_rerun_20261116 `
  --archive storage/m5_stop_research_20261114 `
  --output storage/<new-unique-directory>
```

The runner requires a new output directory, verifies the existing provenance
chain and disjoint dates, freezes its source and protocol, and denies MT5
initialization/order submission during evaluation. It reads archived candles;
no native history call or backend restart is required.

## Corrected-coverage results

| Period and lane | Candidates | Trades | Wins | Net simulated rand | Review |
|---|---:|---:|---:|---:|---|
| primary / control | 26 | 14 | 4 | -432.21 | failed |
| primary / entry_only | 0 | 0 | 0 | 0.00 | failed |
| primary / target_only | 17 | 10 | 2 | -335.74 | failed |
| primary / combined | 0 | 0 | 0 | 0.00 | failed |
| separate / control | 0 | 0 | 0 | 0.00 | failed |
| separate / entry_only | 0 | 0 | 0 | 0.00 | failed |
| separate / target_only | 0 | 0 | 0 | 0.00 | failed |
| separate / combined | 0 | 0 | 0 | 0.00 | failed |

Net figures for the primary period sum independently reset stages; they are
not one continuous portfolio. All numbers are simulated and include the
declared spread/cost model. Stage-specific results and rejection counts are
in the portable JSON and the signed local report.

Corrected coverage increased the control's trade count from ten to fourteen.
All ten original entries, exits, execution prices and cash outcomes were
retained, alongside four additional losses. A later running balance changes
because of the additional earlier trades.
The 26 control candidates produced fourteen simulated trades
and four wins; twelve candidates were rejected by the unchanged volatility guard.
The target-only package produced ten trades and two wins. Neither negative result
establishes an improved edge. Extra confirmation and the combined proposal made
no trades, so they are not useful validated replacements.

In April, 4,158 eligible scanned windows reached detection: 4,135 failed
all-four-timeframe confluence, and 23 aligned windows had no valid micro-sweep.
A separate receipt-bound context audit reconstructed those same windows. It
found D1 freshness failures on 198 windows and H4 freshness failures on 44
(with some overlap); the remaining disagreements include opposing or flat
directional readings. Therefore April's lack of trades cannot be attributed
solely to missing data or to the old continuity screen. No freshness or
confluence rule was loosened. The audit is stored separately as
`separate_context_audit.json` in the corrected-coverage run.

**No strategy was activated.** The comparison does not demonstrate a profitable
replacement or a natural automated broker lifecycle. Future evidence must
remain separate from these already inspected historical outcomes.
