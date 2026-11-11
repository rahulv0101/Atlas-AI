# Separate learned candidate-ranking experiment

Atlas now has a bounded research experiment that learns how indicator context relates to cost-adjusted candidate outcomes. It does **not** replace the running trader or alter its strategies, confidence, risk limits or execution gates. It also leaves the original frozen paper experiment and seven-day activity review unchanged.

## What learns

One ridge-regression model predicts nominal net return in stop-risk units (R). It uses only information available when a candle closes: strategy identity, signal confidence, recent directional price changes, candle body, distance from a trailing price average, spread relative to ATR, relative volume, higher-timeframe agreement, regime and UTC time of day. Rolling calculations use current and earlier candles only.

The learned research policy ranks existing base-strategy candidates and abstains unless the highest predicted net return is at least **0.10R**. This is one bounded candidate policy; it does not invent executable code or arbitrary new strategies. Its comparator chooses the highest-confidence candidate from the same candidate universe. Each nominal paper portfolio allows one position at a time and at most six entries per UTC date. Neither portfolio is the complete live Atlas policy.

The model trains once using the earlier 70% of an already inspected historical snapshot. Complete outcome horizons that cross the split are purged. Training uses nonoverlapping full-horizon groups, divides same-time weight among candidates, clips training targets at +/-5R, and uses a fixed regularization strength of 10. There is no parameter search, automatic retraining or automatic model promotion.

Labels reuse the broker-unit simulator: recorded bid/ask spread, observed fee estimate, adverse slippage assumed at three points per side, stop-first ambiguity resolution and the existing research exit rules. These are nominal minimum-lot outcomes with frozen current currency conversion. They do not reproduce live sizing, margin, risk budgets, visual/macro approvals, execution gates or actual fills. Natural slippage is still uncalibrated.

## Initial result

The first version fitted **1,978 training examples in 1,135 nonoverlapping time groups across 17 dates**. These are simulated labels, not broker trades, and are not claimed statistically independent.

| Previously inspected window | Highest-confidence baseline | Learned policy |
|---|---:|---:|
| Earlier training period | 98 paper trades, -44.36R, PF 0.40 | 0 trades |
| Later diagnostic period | 42 paper trades, -14.58R, PF 0.50 | 0 trades |

The model selected no candidate above its frozen expected-return threshold. It **failed historical review**; avoiding losses by abstaining does not establish a trading edge or useful trading activity. The later historical period is diagnostic, not blind validation. No threshold was lowered after seeing this result.

## Fresh observation

Version one froze on **11 November 2026 at 20:45:46 SAST**. The observer replays only new post-freeze closed-candle outcomes, with the same frozen model and method, through the existing acceptance deadline of **10 December 2026 at 21:51:19 SAST**. This is frozen-model forward paper replay, not proof that predictions were submitted before entry and not broker execution.

The observer obtains candles from the existing collector, verifies immutable observed prefixes, and caches signal generation incrementally. It never connects to the broker. The signed manifest, model, historical report and input checksums are stored with a frozen source snapshot under ignored `storage/learning_experiments/candidate_ranker_20261111`. There is no conversational-memory input. Interrupted or revised evidence blocks review rather than resetting results.

The acceptance supervisor resumes a healthy observer without duplicates, respects backend availability and operator sleep for launches, and limits restarts. Other collectors continue if the learning observer fails. After 30 and a further 30 learner paper trades, each stage is checked for positive mean net R, at least two dates, PF at least 1.1 (or all wins), drawdown no greater than 6R and greater total net R/cash than the baseline inside that stage's time window. Different selections and overlapping market conditions mean this is a screening comparison, not a statistical proof. If it remains inactive, sample requirements stay unmet; it does not pass by default.

Every outcome remains paper-only, `broker_eligible=false`, `auto_promotion=false`, and zero orders. Future retraining must create a separate version and preserve this version's results. Activation would require a separate review and explicit decision.

## Inspection and validation

Inspect `learning_experiment` in `storage/acceptance_plan.status.json`, or open the experiment's `forward_status.json`, `model.json` and `historical_report.json`. To update once without starting a background process:

```powershell
.\.venv\Scripts\python.exe storage/learning_experiments/candidate_ranker_20261111/frozen_source/tools/learn_candidate_ranker.py once --run-dir storage/learning_experiments/candidate_ranker_20261111
```

**108 focused tests passed**, including causal features, split purging, costs, deterministic training, abstention, minimum evidence, source/model/data tampering, immutable forward observations, resume without double counting, no forward retraining and independent supervision. The local test report is `docs/diagnostics/learned_ranker_20261111.xml`. A real historical training run and one forward observer pass also completed with zero broker orders.
