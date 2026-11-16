# Bounded SMC confirmation correction

Two new **research-only** adapters, `smc_event_retest_confirmed_v6` and
`smc_sweep_reclaim_confirmed_v6`, wrap the unchanged frozen v5 observations.
They are not registered executable strategies and cannot send broker orders.

## Implemented correction

- Require Atlas's existing Daily/H4/H1/M15 directional entry gate before arming
  and again before confirmation. Do not substitute a weaker context policy.
- Hold one setup per model for at most three additional closed M5 bars after
  the original signal. Use the actual shared timing method and a directional
  candle close at or beyond the anchor close. Do not fabricate momentum labels.
- Keep the original buffered structural stop. Widened sell-side Ask spread can
  widen protection; it cannot tighten it. Round protection outward to the grid.
- Retire setups after protection breaches, alignment loss, missing eligible
  confirmation windows or expiry. Repeated observations of the same closed
  candle cannot advance or consume a pending setup.
- Re-evaluate the nearest current HTF target, minimum 2R before costs, and
  proximity of the entry quote to the closed confirmation candle.
- Reject unaffordable geometry at the minimum lot, including the frozen fee
  reference and adverse slippage on both legs. Broker protection and margin
  constraints still apply. The stop is never shortened to satisfy a cash target.
- Submit any remaining candidates to unchanged shared portfolio gates again.
  Volatility, conviction, sessions, loss caps and live strategy inventory remain
  unchanged. Qualification does not happen automatically.

This is an adapter correction, not a new chart-pattern detector. It can only
use the source study's 89 complete observations and their inherited eligible
windows. It cannot establish whether a different detector would find better
setups outside that source population.

## Test and result

The source is the signed 180-day current-code rerun in
`storage/smc_entry_rerun_20261116`. Existing source dependencies, candle hashes
and prediction receipts are checked before use. New rules, source snapshot and
protocol were frozen before new observation/outcome generation. All broker
initialization and order dispatch are denied during the offline experiment.

The authoritative artifact is
`storage/smc_confirmation_correction_20261116_v2`. The earlier artifact retains
the same economic rules and zero-entry result; v2 corrects duplicate-bar
handling and explicitly reports retirement when an eligible window is skipped.
No strategy parameters were tuned to improve an outcome.

| Model | Raw observations failing all-four alignment | Confirmation result | Eligible entries |
|---|---:|---|---:|
| Event retest v6 | 13 | One aligned anchor expired without confirmation | 0 |
| Sweep/reclaim v6 | 65 | Seven anchors expired; two breached protection; one lost its eligible confirmation window | 0 |

The wait counters contain repeated observations of pending setups, not extra
independent trade opportunities. No setup reached the new affordability check;
therefore this experiment does not show improved affordability. Both models
made zero trades in development, validation and holdout, and neither qualified.

This is previously inspected retrospective data, not independent prospective
proof, measured fills or a natural automated lifecycle. Fixing the flow between
research signals and gates does not establish a trading edge. The remaining
research problem is finding setups that naturally meet the entry policy and
budget, not changing the result label to "qualified".

## Operator integration

`tools/publish_smc_confirmation.py` verifies the completed result and receipts,
then publishes a signed compatibility view through the existing read-only
`smc_entry_comparison_active.json` pointer. The previous operator pointer is
saved beside the view for reversal. This pointer is only consumed by research
reporting; it cannot activate broker models or paper observers. Existing paper
and calibration observers are retained. UI and typed/voice answers use the same
current report. The verified answer reports no qualified candidate.

Fifty-seven focused checks passed, covering the state-machine safety cases,
unchanged SMC/replay behavior, publication integrity and existing research
integration. Portable results and artifact receipts are in
`SMC_CONFIRMATION_RESULTS_20261116.json`.

```powershell
.venv\Scripts\python.exe -m tools.validate_smc_confirmation `
  --source storage/smc_entry_rerun_20261116 `
  --output storage/smc_confirmation_NEW_DIRECTORY
```

The output directory must be new. To publish a completed result, use
`python -m tools.publish_smc_confirmation --run-dir <new-result-directory>`
with the project venv. Only research-status reporting changes.
