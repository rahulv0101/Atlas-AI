# Why the latest structural strategy failed qualification

This is a diagnosis of the fixed v8 research result, not a claim about real
broker losses or every strategy in Atlas. All ten recorded simulated trades
were reproduced from the signed input candles, original signals and management
settings with matching entry, exit, cash, R and exit reason. No strategy, risk
or execution parameter was changed by this diagnosis.

## Confirmed findings

1. **The sweep/reclaim often failed to develop directional follow-through.**
   Four trades lost approximately a full initial risk unit, with stops in the
   first one, two, two and three M5 bars respectively. Completed bars before
   three of those exits showed at most 0.17R, 0.14R and 0R favorable excursion.
   The fourth stopped in its entry candle, so there is no completed pre-exit
   bar. Exit-bar tick ordering remains unknown.

2. **Higher-timeframe direction did not establish an M5 trend change.**
   Seven of ten entries opposed the generic eight/21-close M5 trend measure.
   Five of the six losers were in that group, but so were two winners. This is
   a small-sample association, not evidence that adding an M5 filter will
   reliably improve results. The accepted structural turn is an early reversal
   hypothesis; it is not proof that the M5 trend has durably changed.

3. **Planned reward and realized reward differed substantially.**
   Initial targets ranged from 2.06R to 6.49R, with a median of 3.13R. No trade
   reached its configured take-profit. The winners averaged about 1.03R after
   the existing one-hour cap and stop management. A minimum 2R initial target
   does not mean realized winners earn 2R. This suggests an entry/target/holding-
   horizon mismatch worth testing; it does not prove that extending the hold
   or removing protection would improve performance.

4. **The observed payoffs did not offset the losses.**
   The fixed sample had four winners totaling R385.42 and six losers totaling
   R427.03, net -R41.61 and pooled profit factor 0.90. Average winner: R96.36;
   average loser: R71.17. At those observed payoffs, break-even requires about
   42.5% wins; the sample delivered 40%. These are descriptive pooled metrics
   across independently reset chronological stages, not one live portfolio or
   a stable estimate of future win rate.

5. **There is too little evidence even if the recent wins look encouraging.**
   Development had five trades and five losses; validation had one loss;
   holdout had four wins. The model needs thirty trades in each stage, and
   positive expectancy/profit-factor requirements also failed in the earlier
   two stages. Four recent wins cannot establish a qualified replacement.
   The FVG family had no complete candidates at all. Only nineteen sweep
   candidates survived the upstream research checks, and the unchanged
   volatility guard blocked nine before entry.

## The losses by exit type

| Losing exit | Count | Meaning |
|---|---:|---|
| Full-risk stop | 4 | Price reversed through original protection early |
| One-hour time limit | 1 | Follow-through faded; the position ended below entry |
| Stale exit | 1 | Insufficient favorable progress by the fourth M5 bar |

Two winning trades also have `stop_loss` exit labels because protection had
already moved above break-even. Therefore six `stop_loss` labels do not mean
six losing stop-outs. Two other winners ended at the one-hour time limit.

## What remains uncertain

The strongest supported interpretation is that the local reclaim sometimes
fires before a sustained M5 reversal, while the selected distant HTF targets
are not realized under the current management horizon. Causal proof needs
more data and an independently tested comparison. Ten trades cannot separate
random variation from a durable market-condition effect.

The optional broker tick-history check did not complete in the read-only
diagnostic window. It was stopped after a hanging native request; no tick
ordering conclusion was claimed. Backend status subsequently refreshed
without restarting Atlas. The optional tool now refuses to share blocking
native history reads with an active or unverified Atlas backend. Quote-path
review belongs on an idle test terminal. This does not establish whether any
bar-level full loss could have been managed differently intrabar.

## Research implications, not activated fixes

- Test stronger **closed-M5 structure/persistence evidence**, using a declared
  hypothesis, rather than treating a single reclaim as a durable reversal.
- Test whether target selection and the one-hour/stale/stop management form
  a coherent expectancy model. Change one component at a time.
- Use data not selected from these ten outcomes, followed by prospective
  observation. Keep matched capital, costs and risk and retain failed results.

No hindsight filter, longer hold, looser stop, volatility bypass or strategy
activation follows this diagnosis. The missing evidence handoff was a software
problem; a profitable, sufficiently frequent entry model remains unproven.

## Evidence

- `tools/diagnose_structural_strategy.py`: receipt-bound candle reproduction and
  pre-exit path/payoff audit.
- `storage/smc_strategy_diagnosis_20261116_v2`: full signed local diagnosis.
- `storage/smc_early_stops_tick_review_20261116/review_status.json`: unresolved
  optional tick review, kept separate from verified candle findings.
- `docs/STRUCTURAL_STRATEGY_DIAGNOSIS_20261116.json`: portable findings/receipts.

The diagnostic excursion calculation excludes the exit candle and uses Ask
for short exits. Tests protect against using a favorable high that occurred
after the trade had already stopped, and against active-terminal tick audits.
