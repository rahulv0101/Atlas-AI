# Full-stream corrected ATR geometry comparison

This experiment follows the fixed 47-trade diagnosis and affordability screen.
It uses the existing ATR-price-to-broker-points adapter on every signal in the
frozen primary candidate stream, including signals not selected in the old
portfolio. The replay can re-rank candidates, select different entries and
apply position occupancy and existing management using corrected geometry.
It is not limited to replaying the original 47 selected entries.

## Frozen design

- Primary: archived May-November M5/native HTF histories and all 34,911 cached
  candidate bars from the deployed-preset diagnostic. Side/confidence and signal
  eligibility remain unchanged by distance conversion. The unchanged control is
  reused explicitly from its signed original report, not called a new replay.
- Separate period: April 1-May 1, 2026. Native candles include prior warmup.
  Base-inventory candidates are regenerated, then both unchanged and corrected
  geometry pass through the same portfolio replay. Candidate entries are
  restricted to April; complete exits must remain within its end boundary.
- Capital: R10,000 virtual initial balance in both periods. This is the preset's
  research balance, not a claim about actual demo equity or a funding request.
- Risk fraction, lot cap, session/loss limits, broker specification, modeled
  costs, volatility and confidence checks, timing and management stay frozen.
  Broker conversion and pilot limits are prior snapshots, not newly verified.
- No parameter search, automatic activation, order submission or live setting
  change. MT5 initialization and order submission are denied during evaluation.
- Protocol and source snapshots precede candidate transformation and outcomes;
  candidate caches are signed before outcome replay. Each completed lane has
  its own signed checkpoint and a combined signed report.

## Interpretation limits

Both historical periods have been inspected previously. April is disjoint,
not blind or prospective. The shared replay still lacks the historical learning,
ranking, visual/macro, approval and broker state documented in the original
parity audit. Full live parity and expected live trades/day remain unconfirmed.
Conversion correctness, affordability and strategy profitability are separate
questions. A zero-trade result cannot qualify a replacement or show zero live
opportunity. A positive retrospective result alone cannot authorize activation.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tools.replay_corrected_m5 --period primary --output storage/<new-primary-directory>
.venv\Scripts\python.exe -m tools.replay_corrected_m5 --period separate --output storage/<new-april-directory>
```

Initial local run directories:

- `storage/full_corrected_m5_primary_20261118`
- `storage/full_corrected_m5_april_20261118`

Consult the signed reports when completed. An unfinished progress file is not
a completed validation result. No result is inferred from the earlier 47-entry
affordability screen.

## Completed comparison

| Period | Geometry | Simulated trades | Wins | Net simulated rand | Review |
|---|---|---:|---:|---:|---|
| primary | unchanged | 47 | 14 | -233.33 | failed |
| primary | corrected | 0 | 0 | 0.00 | failed |
| separate_April | unchanged | 0 | 0 | 0.00 | failed |
| separate_April | corrected | 0 | 0 | 0.00 | failed |

Partial live parity; previously inspected periods. Capital and broker conversion are frozen research assumptions. No automatic broker activation or live-rate forecast.

Correction affordability is distinct from profitability. No strategy or observer is activated.
Passing the software tests does not qualify a trading edge. Full live execution and fresh prospective evidence remain unproven.

The full primary corrected replay had 48 sizing rejections with
`no_risk_bounded_volume` after the preceding shared checks. These are candidate
evaluations, not 48 unique setups or demonstrated missed winners. The risk
budget was R50 at R10,000 virtual balance and 0.5% risk. No lot satisfying the
existing minimum-volume/risk rules was available for those evaluations.

The primary control lost R233.33 over 47 simulations. The corrected lane's
zero net cash reflects no entries, not demonstrated improved profitability.
Its other first-rejection counts differ because it incurred no trades/losses
and therefore did not follow the control's loss-streak/portfolio state.

April's two lanes had identical rejection counts and zero trades; HTF
confluence and earlier timing/session restrictions prevented a sizing-stage
comparison there. Both periods failed the existing research review. All
candidate bars are accounted for in each lane as a trade or first rejection.

The existing research dashboard pointer now exposes the four verified lanes
as a read-only comparison. No model or paper observer was selected, and the
previous pointer is preserved in the operator view directory. Full live parity,
an actual-account capital assessment and natural broker lifecycle proof remain
separate from this result. Live strategy/risk/execution settings are unchanged.
