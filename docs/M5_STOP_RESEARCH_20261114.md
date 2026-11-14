# M5 protection-distance research proposal

This study turns the November 14 loss review into an explicit, persistent research record. It does not retrain the live model, update its allocator or alter strategy, risk or execution settings.

## Observation and hypothesis

The completed recent M5 diagnostic produced ten simulated trades: eight stop losses and two target hits. All exits were within the first M5 execution candle. Stops were $1.00–$1.10 away in gold price terms, while the median preceding candle range was approximately $3.98. Two losing bars touched both stop and target; the simulator used stop-first ordering. These observations motivate a hypothesis; they do not establish that wider stops improve expectancy.

The active formulas compare an ATR measured in price units with fixed floors expressed in broker points. The repo already has a research-only adapter, `corrected_atr_signal`, that divides the ATR-derived price distance by broker point size. This study compares **one fixed intervention** with the unchanged baseline: apply that existing adapter to the six enabled built-in strategy candidates. Both stop and target use the adapter's already-declared strategy coefficients and floors. Signal direction, confidence, timestamps, higher-timeframe context and entry conditions are retained. No multiplier search or retuning after outcomes is allowed.

## Data and protocol

The proposal and checksum were frozen at `storage/m5_stop_research_20261114/protocol.json` before the outcome replay. Frozen source has a separately checksummed receipt. The discovery source is the completed `m5_system_backtest_20261114_v3` study. Validation decisions use **April 1–May 1, 2026 UTC**, disjoint from the October–November discovery window, with native Daily/H4/H1/M15 warmup and M5 entries. Warmup bars are context, not scored trades. Candidate signals and the corrected counterparts are checksummed before any outcomes for this study.

April is an earlier historical period, not a chronological forward test. Previous chart availability or broader history cannot establish blindness, so this is labelled **separate historical validation**, not fresh or blind proof. Fresh post-freeze observations remain necessary before any later promotion. The historical study alone cannot authorize execution.

## Unchanged boundaries and review

Both lanes retain the discovery study's nominal R10,000 capital, 0.5% risk budget, 0.01 minimum/capped lot, current-reference fees/currency/margin, three adverse slippage points per side, previous closed spread proxy, all-four top-down confluence, timing/conviction checks, risk/session/frequency limits, portfolio sequencing and stop-first M5 exits. Broker orders are denied, model stores are temporary, and no prospective observer pointer is replaced.

The fixed separate-period review requires at least **30 trades on two dates**, positive mean net R, profit factor at least **1.1** (or all wins), and maximum drawdown no greater than **6R**. Zero trades fail review. Fewer stopouts caused by sizing rejection do not establish improvement. Wider protection must fit the same risk budget; the study cannot increase risk or invent sub-minimum volume.

Historical visual approvals, external macro/news, Gemini decisions, adaptive model versions, tick fills and actual broker protection remain unavailable. Both lanes are diagnostic; this is not complete live-pipeline parity.

## Durable learning boundary

Persisting the observation, hypothesis, exact rules, results and rejection reasons is useful research memory. Treating a repeated simulated outcome as a verified broker outcome would contaminate performance evidence. Training on these losses and then evaluating the same sample would also overstate validation. Live model changes require a separate validated proposal; a remembered finding is not an execution instruction.

The dashboard study row and “How is the stop distance research doing?” share the same read-only status for typed and voice answers. Failed, unavailable and stale evidence cannot be presented as a successful correction.

## Completed results

The [portable summary](M5_STOP_RESEARCH_20261114.json) contains both matched periods and artifact checksums. The recent baseline reproduced all ten original trade identities and the -R94.06 result. Corrected ATR units produced **zero recent-period trades**, with **10 `no_risk_bounded_volume` rejections**. Consequently, the zero stopout count supplies no evidence of improved trade quality.

The separate April period contained **5,796 M5 decision bars**. Both baseline and correction produced **zero trades**. Sequential rejections were all-four higher-timeframe confluence (4,826), outside active session (707), close buffer (189), open buffer (19), timing discipline (15), and pilot setup family (1). The two lanes were identical here: no otherwise eligible entry reached the stop-sizing comparison. This period cannot validate improved win rate or expectancy.

The correction **failed the evidence threshold through insufficient trades**, not through demonstrated inferior returns. It was not promoted, no permanent live model weights were changed, and no broker orders were sent. Fresh forward validation remains unfulfilled; this study does not schedule an executable candidate. Existing prospective observers remain separate.

The factual lessons are permanent repo-visible research records: tight baseline protection, a risk/contract incompatibility for the reviewed ATR correction, and a separate period with no qualifying entries. They are not live performance statistics or control instructions. The proposal also adjusts target distance using the existing ATR coefficients, so it is not a stop-only causal experiment.

**72 focused regression checks passed**, covering correction units and unchanged direction/confidence, future-candle exclusion, disjoint periods, no zero-trade qualification, native M5 policy replay, dashboard failure/staleness wording, shared typed/voice status, relevance boundaries and existing visual-evidence guards. An older visual-evidence test fixture was updated to include its M1 timeframe; production gate logic was unchanged. All five validation input hashes, both candidate files, protocol/report receipts and 277 frozen source files were verified. Runtime API checks confirmed the updated UI and consistent typed/voice study responses.
