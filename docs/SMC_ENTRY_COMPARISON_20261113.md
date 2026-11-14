# Matched SMC entry research

The operator requested fixing the combined model's low activity and unproven performance. This study compares **two predeclared entry hypotheses** against the same verified native timeframe inputs, costs, nominal capital and risk limits. It does not retune rules until one wins or enable broker orders.

## Hypotheses and unchanged boundaries

`smc_event_retest_v5` treats displacement and the structure break as a sequence. A qualifying directional impulse can occur on the break candle or either of its two preceding closed M5 candles. The opposing swing must already be confirmed before that window. The close must genuinely cross the swing. M5 prior structure can oppose the D1/H4 direction during the pullback; the result is labelled BOS, CHOCH or confirmed structure reclaim according to actual evidence rather than requiring an already aligned M5 trend.

A fresh FVG or opposite-candle order block must then receive its first bounded retest after both structure confirmation and zone formation. A zone used before that confirmation is excluded. Protection covers the chosen zone and the actual first-visit episode's extreme plus the existing buffer. This replaces using an unrelated broader block for an FVG entry; it does not shrink a stop merely to pass a lot-size check. Quote proximity, minimum target distance and broker protection checks remain.

`smc_sweep_reclaim_v5` is a separate sweep entry. A candle must take and reclaim a previous 20-candle extreme with a rejection wick of at least 42% of its range. Within three later completed M5 candles, the first directional close must exceed the sweep candle's opposite extreme with a body/range of at least 35%. A repeated confirmation or intervening breach of the sweep extreme rejects the setup. Its stop remains beyond the sweep; it does not require unrelated FVG/order-block conditions.

Both hypotheses share D1/H4 direction, valid H1/M15 pullback evidence and a recent closed M5 reaction-zone reference. Both retain at least 2R before costs, current quote freshness and proximity, structural protection, nominal 0.5% account risk, the 0.01-lot broker minimum/cap, margin, loss-streak, daily-loss, frequency and session checks. Neither appears in the executable strategy inventory. Their fixed research score is not a win probability.

## Frozen comparison and selection

The study root is `storage/smc_entry_comparison_20261113`. `protocol.json` and its checksum were written before outcome evaluation. Each model has its own frozen source, manifest, input hashes and eventual historical report. Preparation used `--reuse-costs --no-activate`: matched verified reference costs and settings, no broker access and no change to the active paper pointer.

The 180-day history has already been inspected by earlier studies. The chronological 60% development, 20% validation and 20% holdout periods are **reused retrospective diagnostics**, not new blind or prospective evidence.

The predeclared screen requires at least 30 trades across two dates per stage, positive mean net R, profit factor at least 1.1 (or all wins), and maximum drawdown no greater than 6R. Paper-candidate selection uses **development qualification only**, then highest development mean R and model ID as a deterministic tie-break. It cannot select a model because the holdout happened to win or because all other models lost more. No broker model is selected automatically, even if every historical stage passes.

## Predictions before labels

`tools/research_smc_entries.py` builds both predictions on one pass, sharing the same context computation. Sampled equivalence checks compare shared results with direct independent evaluation. Every prediction records decision time, last closed M5 input candle and quote proxy. The completed prediction file is checksummed before any exit labels are calculated.

Historical portfolio replay then reads that immutable prediction stream. Decision time, quote and input candle must match the replay exactly; missing or changed predictions fail rather than becoming HOLD. Each model maintains independent nominal balance, risk, overlap and daily counters. Cached predictions cannot bypass those checks.

Future input/outcome timestamp continuity is screened for data quality, as in the existing replay; future high/low/close prices are not decision features. This excludes unavailable windows and can limit coverage. Quote and outcome spreads are lagged closed-bar proxies, fees/currency/margin use a frozen current reference, and M5 outcomes use the existing stop-first simulator and management settings. This is not historical tick-fill reconstruction or full visual/macro/conviction/ExecutionGate parity.

## Operation and verification

The comparison uses one offline worker to limit memory pressure. Active Atlas strategies, risk settings and broker approval remain unchanged while it runs. The dashboard's Entry-model comparison row and “How is the entry model comparison doing?” use the same read-only report in typed and voice paths. Missing/stale reports are not presented as verified progress. Capability and limitation questions are excluded from this specific status intent.

**131 strategy/research regression checks passed.** A separate **37-check** shared status/knowledge/voice run passed after the progress-view changes. These overlapping sets are not added into a unique-test total. Checks cover asynchronous impulses, countertrend M5 structure reclaim, zone-specific protection, real sweeps, no future-candle leakage, target constraints, no broker registration, matched offline preparation without activation, immutable quote/time replay, development-only selection and shared-context equivalence.

The current paper observer remains the previous frozen v4 unless this study produces a development-qualified paper candidate and that separate checkpoint is explicitly selected. Any later paper trial uses only new post-freeze observations and retains its frozen deadline and risk boundaries. Simulated profitability cannot establish an actual protected broker lifecycle or guarantee daily profit.

## Completed results and sizing attribution

The completed comparison selected **neither model**. Event-retest produced 13 complete signals and only one simulated development trade (loss R45.21, -1.011R). Sweep-reclaim produced 67 complete signals and only one simulated holdout trade (win R217.15, +5.673R). Every stage failed its frozen review criteria. The isolated holdout win cannot justify selection: selection uses development qualification only. There is no demonstrated edge or new broker lifecycle evidence.

`tools.audit_smc_sizing` verifies the report and immutable prediction receipt, then creates a separate checksummed `sizing_audit.json`. It does not rewrite frozen reports or model sources. At the frozen **R10,000 initial simulation balance and 0.5% risk budget (R50)**, minimum-lot structural-stop risk exceeds budget for 12/13 event signals and 66/67 sweep signals: **78/80 overall**. Median risk is R91.96 and R118.20 respectively. Neither lot cap nor margin excludes any of these predictions at that initial balance; minimum-lot margin is R131.28. This is per-prediction attribution at initial capital, not a new portfolio replay, actual account valuation or recommendation to deposit funds. Broker gaps/slippage can exceed nominal stop risk.

A read-only inventory of the configured demo account on November 14 SAST found no smaller-minimum-exposure tradable USD gold variant: the available variants share the 100-unit contract and 0.01 minimum lot. Disabled symbols and gold-related equities are not alternative executable gold contracts. No symbol, risk budget, stop rule or trading permission was changed.

The dashboard and shared typed/voice research answer now expose that simulation sizing blocker explicitly. The v4 forward observer remains active. Further qualification requires enough independent new observations and an entry approach whose genuine protection fits the existing contract/risk constraints; increasing risk or moving stops solely to pass sizing would not supply that evidence. **40 focused sizing, status, knowledge and voice checks passed** after adding the attribution (overlapping earlier checks).
