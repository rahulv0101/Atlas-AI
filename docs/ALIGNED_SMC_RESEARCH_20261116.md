# Fresh aligned SMC research v7

This experiment tests two new chart detectors on every eligible closed-M5
window, rather than restricting a new adapter to the prior v5 candidates.
The new models remain research-only and cannot send broker orders.

## Fixed hypotheses

Both models require the existing Daily/H4/H1/M15 directional entry gate.
They do not also demand opposing H1/M15 closes. Actual M5 chart structure
provides the local setup; the shared Atlas gates still decide entry quality.

- **Aligned FVG continuation:** a close crossing a two-left/two-right confirmed
  swing with displacement of at least 1.25 ATR and body/range at least 0.6.
  Look back at most eight break bars. Require a three-candle FVG at least
  max(2 points, 0.05 ATR), then its first fresh retest using the existing
  first-visit routine. Protection is beyond the entire gap and retest episode
  extreme, plus the existing structural buffer.
- **Aligned local sweep/reclaim:** a five-bar local M5 liquidity proxy, sweep
  wick/range at least 0.42, then the first directional close beyond the sweep
  candle's opposite extreme within three bars. Reclaim body/range must be at
  least 0.35. Protection remains beyond the actual sweep extreme and buffer.

These are OHLC hypotheses, not proof of institutional orders or liquidity.
The local sweep deliberately has a different declared horizon from the older
twenty-bar model. There is no parameter grid or best-outcome selection.

The existing research confirmation adapter may wait up to three additional
closed bars after a raw setup. It uses actual shared timing evidence and a
directional close, retires stale/breached/gapped setups, and never tightens an
original stop. Targets must remain at least 2R before costs. Minimum-lot risk
includes fees and adverse slippage on both legs, and the unchanged portfolio
gates evaluate any remaining candidates again.

## Evidence and boundaries

Inputs come from the signed May 20–November 16, 2026 rerun. The old experiment's
eligible time grid includes 17,902 windows after its continuity, session and
outcome-availability screens. New detection runs across that whole grid. Those
screens limit coverage near market closures; this is not every possible M5
entry or an independent new dataset.

Rules, current source snapshot, settings and specification are frozen before
new predictions and outcomes. Predictions are persisted before outcome labels.
The original nominal R10,000 balance, 0.5% risk, 0.01 minimum lot/cap, session,
volatility, conviction and loss limits remain. Current frozen conversion,
margin and fee references are approximations, not measured historical fills.
Chronological development/validation/holdout are 60/20/20; each stage must
have thirty trades over two dates, positive mean net R, PF >= 1.1 (or all wins),
and drawdown <= 6R. Forward evidence and explicit review remain necessary.

The optional research name added to `Confirmation` preserves its default v6
names and behavior. A full default-path regression is compared with the prior
v6 report to detect changes in candidates, reasons and simulated portfolios.
The broker strategy registry and trading policy are not modified.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tools.validate_smc_confirmation --fresh-detectors `
  --source storage/smc_entry_rerun_20261116 `
  --output storage/smc_aligned_NEW_DIRECTORY
```

The directory must be new. Local signed evidence for this run is in
`storage/smc_aligned_v7_20261116`. No model receives trading authority merely
because the experiment runs or its result is displayed in Atlas.

## Completed outcome

All 17,902 inherited eligible windows were evaluated. Both models rejected
14,213 windows at the existing all-four confluence gate, leaving 3,689 aligned
windows to examine. The detectors are not limited to the earlier 89 v5 setups.

| Detector | Complete raw setups | Confirmed and affordable candidates | Simulated trades |
|---|---:|---:|---:|
| Aligned FVG continuation | 0 | 0 | 0 |
| Aligned five-bar sweep/reclaim | 29 | 0 | 0 |

For FVG, 3,423 aligned windows lacked the required structure/FVG sequence;
153 awaited the first rejection, 58 had already confirmed on a prior bar,
43 breached the setup extreme and twelve failed the nearest-target 2R rule.
These are sequential detector reasons, not missed trades with known outcomes.

Of the 29 raw micro-sweep setups, fifteen expired without actual shared timing
confirmation, nine breached protection, three lost alignment and two lost an
eligible confirmation window. The 85 wait observations are repeated checks of
pending setups, not 85 independent opportunities. No candidate reached the
affordability stage; the study does not demonstrate that min-lot affordability
has improved. Neither model passed any stage's qualification review.

The default v6-path regression reproduced both earlier models' counts,
candidates and every development/validation/holdout portfolio field exactly.
This separates the new detector experiment from a hidden change in the old
adapter. The new detectors remain unregistered and inactive.

The verified signed result was published through Atlas's existing read-only
research-status view, with raw detector counts preserved for inspection.
The prior operator pointer is retained beside that view. Existing trading,
SMC paper and M5 calibration observer configurations remain in place.

Portable metrics and artifact hashes are in `ALIGNED_SMC_RESULTS_20261116.json`.
These fixed hypotheses did not qualify in this historical test. The result
does not prove that the gates are universally impossible to satisfy, identify
a profitable alternative, measure fills or verify a natural broker lifecycle.
There was no outcome-driven retuning and no automatic activation.

No setup reached the affordability check in this run, so improved affordability
is unproven. The cost-inclusive sizing routine is covered by unit checks; those
checks do not replace market evidence. The full v6 default-path regression
reproduced its prior candidate counts, rejection counts and stage portfolios
exactly.

Sixty-three focused checks passed for the new detectors, existing models,
confirmation/protection rules, historical replay and read-only publication.
