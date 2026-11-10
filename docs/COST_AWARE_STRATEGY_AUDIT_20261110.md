# Cost-aware strategy audit and frozen paper observation

Implemented a separate research workflow for the six enabled built-in strategies, three fixed entry/distance comparisons, the retained evolved-strategy baselines, and subsequent paper observation. It has no execution adapter or promotion route. No live strategy logic, risk limit, threshold or execution setting was changed.

## Distance and cost findings

Several built-in formulas compare ATR in price units directly with point-denominated floors. At the configured XAUUSD broker point of 0.01 this suppresses the intended ATR distance and often leaves the fixed floor dominant. The research correction converts ATR price distance to points before applying the same multipliers and existing floors. The baseline signal direction/confidence is unchanged. Correction is deliberately isolated from live classes because the resulting distances change strategy behaviour and need validation.

The broker symbol point and tick size were both 0.01; minimum stops level was zero and freeze level eight points. Ten available broker deals reported zero commission/fee, yielding a zero observed round-trip fee estimate. Manual deals were permitted only as fee evidence, never as strategy performance. This small fee sample and current currency-conversion approximation are not a guarantee of future broker costs. Recorded candle spreads and configured hypothetical slippage of 1.5 basis points are charged separately. Gross and spread/fee-only results are retained as sensitivities.

## Frozen experiment

The manifest was written before fetching/evaluating the data, with source hashes, ATR multipliers/floors, simulator settings, hypotheses, date splits and qualification criteria. Broker data supplied 10,257 closed M1 bars including warmup. Original strategy classes generate signals using only the trailing 1,200 bars. Outcomes enter on the next bar and use stop-first ordering for ambiguous bars. Missing candles and incomplete horizons are rejected. Session entry/exit buffers apply, and each isolated lane permits at most six trades per day, two consecutive losses and a 0.6% daily loss budget at configured per-trade risk. These are conservative research constraints, not a complete reproduction of the engine's sizing and gates.

The three comparisons were fixed in advance: current distances with immediate entry; corrected ATR distances with immediate entry; corrected ATR distances with a confirmation within three later closed bars. Confirmation requires a retest of the original trigger close within 0.25 ATR, a close holding that level with directional candle/momentum, and no chase exceeding one ATR. It cannot confirm across a missing minute or session change. Corrected variants also require the target to exceed twice recorded spread plus fee points. All scenarios still deduct assumed slippage.

Training: 2–4 November UTC. Reserved historical check: 5–6 November UTC. Recent validation: 9 November through the run cutoff on 10 November UTC. That recent period was already inspected in earlier work and is explicitly not blind. The reserved historical period was held out for this run but cannot be claimed untouched by every earlier project experiment.

Research selection uses training only: at least 12 trades across two days, positive cost-adjusted mean, profit factor at least 1.1 (or all wins), and drawdown no greater than 6R. A selected candidate would then need at least ten qualifying historical holdout trades. Prospective evidence requires at least 30. These are research review requirements; passing them never authorizes broker trading. None of the 18 lanes qualified in training, so no winner was selected and no strategy was promoted.

## Reserved-period results

Each cell shows average R after spread, observed fee estimate and assumed slippage, followed by sample count. R is hypothetical stop risk, not rand return. These isolated lane results are not forecasts for Atlas's account.

| Strategy | Current distances | Corrected ATR | Corrected ATR + confirmed retest |
| --- | ---: | ---: | ---: |
| EMA crossover | -1.971 (2) | +0.137 (8) | +0.397 (10) |
| Trend pullback | -1.883 (2) | -0.126 (8) | +0.513 (9) |
| Momentum continuation | -0.586 (6) | +0.156 (12) | -0.041 (8) |
| Gold micro impulse | -2.129 (2) | -0.430 (4) | -0.774 (3) |
| Gold breakout retest | -0.743 (4) | -0.132 (8) | -0.869 (3) |
| Gold liquidity sweep | -2.083 (2) | +0.118 (8) | -0.523 (5) |

Corrected-distance momentum continuation was positive in training (+0.120R, ten cases), reserved validation (+0.156R, twelve) and the already-inspected recent period (+0.100R, seven). It is a promising but unqualified research hypothesis: the training sample did not meet the fixed twelve-case minimum. Trend pullback with confirmation was negative in training despite later positive windows. EMA corrections were positive in the reserved window but negative in the recent window. No result justifies choosing a winner after inspecting the later period.

The retained evolved_rule baseline was negative in all three windows. The operator-retained evolved_mhr_hr chromosome was approximately flat in training (+0.001R, eight cases), negative in the reserved check (-1.168R, three) and positive in the recent window (+0.165R, two). These are baseline reviews of current frozen parameters, not a claim those parameters existed historically. The separate chart-driven research worker also had negative forward modeled results for its latest candidates when inspected; they remain research-only.

## Forward observation and operator visibility

An initial bounded 24-hour sidecar observes all 18 frozen built-in comparisons on subsequently closed broker bars. Its forward start is the saved selection-freeze timestamp, after training computation and before historical holdout review. It stores paper outcomes separately, checks strategy-source hashes, freezes simulator settings and fails closed on source or symbol changes. A process lock prevents duplicate observers for the same run. Errors and stale heartbeats are visible rather than treated as successful research. The initial window may be insufficient to collect thirty cases under day-trading limits; completion is not qualification.

The UI's cost-research line reports heartbeat state, comparison count, overlapping paper-outcome count and training qualification count. It never presents paper outcomes as verified broker trades. The pre-existing demo observer continues to require a fresh autonomous decision, matched entry fill, observed protection, balanced exit fills and a flat broker position. Manual and forced diagnostic tests remain excluded from natural lifecycle proof. The earlier labelled mechanics diagnostic does not satisfy that proof.

## Artifacts and verification

Local evidence: storage/cost_research/run_20261110 contains the frozen manifest, hashed candle data, signal cache, training-only selection, all lane outcomes, legacy manifest/results and prospective observation. storage/cost_research/latest.json is the small read-only UI summary. Raw account-derived evidence remains local.

Commands:

```powershell
.venv\Scripts\python.exe tools/broker_fee_profile.py --output docs/diagnostics/strategy_fee_profile_NEW.json
.venv\Scripts\python.exe tools/cost_aware_strategy_audit.py audit --run-dir storage/cost_research/NEW_RUN --fee-file docs/diagnostics/strategy_fee_profile_NEW.json
.venv\Scripts\python.exe tools/legacy_strategy_cost_audit.py --run-dir storage/cost_research/NEW_RUN
.venv\Scripts\python.exe tools/observe_cost_research.py --run-dir storage/cost_research/NEW_RUN --hours 24
```

The current observer uses run_20261110; do not start a duplicate. A restart can resume the same run only while its source hashes and retained forward data remain compatible. Reboot, sleep, terminal outages or code changes can interrupt observation. They do not authorize fallback orders or silent rule replacement.

Validation: 141 selected audit, cost-status, confidence, UI-server, refresh-isolation, research-worker and replay-integrity cases passed. A final twenty-case observation/audit run also passed, including a new missing/stale-bar display case. Covered failure cases include unit conversion, no future confirmation leakage, loss stopping, missing data, stale UI state, invalid research boundaries and source-change rejection.

The reusable broker-fee collector passed three additional tests for round-trip volume arithmetic, absent-history rejection and unknown fees when no deals exist. Its live reproduction returned the same ten fee samples and zero observed fee-point estimate. No fee evidence requires manually reconstructing a temporary script.

Deployment verification: only the frontend was reloaded; the trading backend and natural-lifecycle observer stayed running. The actual desktop showed broker/UI connected, the new eighteen-comparison paper-observation line and zero qualified training candidates. The API returned the same research boundary with zero orders and no broker eligibility. Frozen source hashes were checked against the saved manifest. During inspection the existing runtime independently reported 85/100 conviction and a missing M1-momentum entry condition; confidence was not stuck at a low value.

What remains unproven: a replacement rule with enough independent future evidence, realistic net profitability, and a natural autonomous broker lifecycle. The workflow is implemented and running; those outcomes cannot be manufactured by software checks or by forcing a trade.
