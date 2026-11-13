# Low-energy filter audit — 13 November 2026

The historical diagnostic does **not support disabling the low-energy veto**. Atlas's live strategies, configuration, learning state, risk policy and execution policy were unchanged. No broker orders were sent.

## What the rule actually measures

`AtlasTrader._market_regime` uses absolute first-to-last close drift over the latest 60 closes for `trend_strength`. This is neither a regression slope nor ATR. Volatility is the mean absolute close-to-close move divided by the last close. The generation gate suppresses directional signals when trend strength is below 0.18%, volatility is below 0.03%, and the classifier says range, unknown or high-volatility range.

With the default cutoffs and enough valid closes, a low-volatility range already has drift below 0.12%. Reducing the 0.18% threshold to 0.12% therefore does not release these signals. The separate UI structure/regime analysis can call the same market trending because it uses another definition. Different labels do not establish a timestamp or calculation bug.

## Comparison and boundaries

The isolated alternative sets only the generation gate's trend threshold to -1, making that one predicate false. It does not enable learning mode. All later session, momentum, weak-trend and learning-policy calls remain in the real signal-generation function. Production settings are never written.

Both historical arms use empty learning state. This avoids applying later outcomes to earlier decisions, but cannot reconstruct Atlas's historical or present learning state. The study regenerates 15 existing built-in strategies; evolved strategies are not reconstructed. Disabled strategies are labelled as research comparisons.

The fixed sample is every 15 minutes, using 1,200 previously closed M1 bars and next-minute entry. Input and execution windows must be continuous; the entire configured outcome horizon must remain within one session and date. The simulator uses existing protection distances, broker minimum volume, observed bid/ask spread, the frozen reference fee estimate, three adverse slippage points on each leg, and existing research exit rules. Currency conversion and fees use the 11 November broker reference rather than historical conversion or calibrated natural fills.

Hypothetical outcomes are labelled even for candidates whose alternative remains suppressed. Reports distinguish all rejected candidates from those retained by the remaining signal filters. **Retention does not mean final conviction, timing, risk, ranking, margin or broker execution would permit a trade.** Per-strategy cases can overlap across strategies and must not be added as portfolio returns.

## Historical findings

The input contained **30,288 M1 bars**, from 12 October 2026 at 15:16 UTC to 11 November at 15:15 UTC. Of 1,930 potential grid windows, 1,678 were excluded because their 1,200-bar input contained a gap. The 252 remaining windows included 120 outside allowed sessions and 60 low-energy windows. This is limited coverage: market closures and gaps exclude most of the input windows. Results are descriptive, reused-data diagnostics, not untouched validation or proof that the veto is optimal.

There were **260 hypothetical rejected-candidate cases**. Selected results after costs:

| Strategy | Currently enabled | Cases retained after bypass | Wins | Mean net R | Profit factor |
|---|---|---:|---:|---:|---:|
| EMA crossover | Yes | 60 | 18 | -0.412 | 0.409 |
| Trend pullback | Yes | 45 | 15 | -0.295 | 0.545 |
| Gold breakout retest | Yes | 6 | 3 | -0.039 | 0.925 |
| Gold liquidity sweep | Yes | 7 | 2 | -0.351 | 0.524 |
| Gold micro impulse | Yes | 2 | 1 | +0.170 | 1.329 |
| RSI mean reversion | No | 15 | 5 | -0.320 | 0.534 |
| Bollinger mean reversion | No | 4 | 2 | -0.168 | 0.674 |
| Stochastic reversal | No | 7 | 1 | -0.668 | 0.242 |
| VWAP proxy reversion | No | 4 | 2 | -0.382 | 0.258 |
| Gold micro structure reversion | No | 0 | 0 | — | — |

Two gold micro impulse cases cannot establish a profitable alternative. Other strategies and all case-level labels are retained in the local report. No new range strategy qualified for activation from this study.

## Ongoing inactivity has multiple causes

A separate bounded archive summary deduplicates publication timestamps, categorizes primary blockers, and counts candidates vetoed by this rule. These are published decisions, not independent trades or proven opportunities. It demonstrates why a low-energy veto in one current snapshot must not be described as the explanation for every earlier HOLD. Timing and higher-timeframe alignment also stop directional candidates. The precise sample boundaries and counts are in the report rather than treated as permanent runtime state.

The final archive sample covered **208 unique publications**, from 14:52:46 to 18:59:57 SAST on 13 November. Of these, **183 selected a direction** and **15 contained a low-energy-vetoed candidate**. Primary blockers were timing discipline (112), higher-timeframe alignment (59), insufficient confidence (15), no directional signal (12), and session cutoff/flat confirmation (10). A candidate veto count can coexist with a different primary blocker; these totals are different measurements. At the final operational check around 19:01 SAST, the current primary blocker had changed to timing discipline. Original paper/natural observers and the separate penalty shadow observer were still running.

## Verification and artifacts

**51 focused tests passed**, covering isolated setting changes, preserved session and momentum filters, rejection of learning-mode substitutions, closed-bar inputs, future-price independence of predictions, missing-bar exclusion, archive deduplication and existing signal/historical-policy behavior.

The final local run is `storage/audits/low_energy_20261113_v2`. It contains copied candles, a signed manifest with method/settings/input/code hashes, a frozen source snapshot, progress and `report.json`. The first run remains preserved at `storage/audits/low_energy_20261113`; its historical findings were unchanged by adding copied-input validation and the deduplicated archive summary.

To repeat the diagnostic into a **new** local directory:

```powershell
.\.venv\Scripts\python.exe tools/audit_low_energy.py --output storage/audits/low_energy_new_run
```

No observer, automatic promotion or policy activation is attached to this diagnostic. The existing prospective penalty comparison remains a separate experiment. A live change would require a precisely bounded proposal and fresh evidence beyond this reused historical study.
