# Frozen multi-timeframe SMC validation

The operator authorized the validation and conditional bounded demo trial on 13 November 2026. This change adds a separate historical diagnostic and a supervised prospective **paper** lifecycle observer. It does not register the composite as an executable strategy, modify broker approval or relax risk limits.

## Frozen evidence

The active run is `storage/smc_validation/frozen_20261113_v2`. Its signed manifest freezes the model source, validation source, safe settings, cost/unit reference, account-scope hash, environmental versions, historical dates, review rules and existing acceptance deadline. Native broker D1, H4, H1, M15 and M5 candles are copied and checksummed independently; higher timeframes are not invented by resampling an incomplete M5 history.

The earlier `frozen_20261113` directory remains preserved as an input-only preparation. Before any historical outcomes were evaluated, v2 made historical spreads strictly lagged: the last completed M5 candle's reported spread is used as the next candle's bid/ask proxy. The original directory contributes no results to this run. There is no rule tuning after inspecting the replay results.

The active freeze was **13 November 2026 at 20:58:24 SAST**. The requested replay is 180 days, with chronological 60% development, 20% validation and 20% holdout periods. Candles include warmup history before the replay. The initial download yielded 214 D1, 900 H4, 3,439 H1, 13,742 M15 and 35,699 M5 bars. Exact dates/hashes are retained locally. Weekends, market closures, missing windows and session restrictions remain explicit exclusions.

## Historical replay

Every eligible M5 decision sees only candles whose opens exist at that time; the shared higher-timeframe collector then removes unclosed candles. Confirmed swings and the SMC detector use only previously closed M5 input. The decision's quote proxy is the next M5 open with the previous closed bar's spread. The source bar's future high/low and final spread cannot approve its entry.

Outcomes use the existing M5 candle simulator, including stop-first ambiguity, fees, three adverse slippage points per side, existing break-even/trailing/stale exits and a 12-bar maximum horizon. Positions do not overlap. Full input/outcome windows must be continuous and stay inside the chronological stage. Entries retain a 70-minute session-close buffer. Nominal broker minimum volume is checked against frozen risk, margin, size, daily-loss, loss-streak and frequency limits.

Each stage requires at least 30 trades across two dates, positive mean net R, profit factor at least 1.1 (or only profitable trades), and no more than 6R maximum drawdown. No parameter search or automatic promotion is attached. A historical pass is a screen, not profitability proof.

The broker cash/fee/margin specification is a current reference, not historical currency conversion or observed strategy fills. Bar spreads are lagged proxies rather than actual entry-time spreads. M5 stop-first labels cannot reconstruct tick-level management. This is the combined detector with nominal session/risk checks, not full historical visual, macro, final-conviction and ExecutionGate parity.

## Forward paper lifecycle

The independent worker is launched through Atlas's installed acceptance supervisor and frozen source. It resumes an integrity-checked checkpoint and existing pending case, respects launch sleep/backend conditions, uses restart limits and ends at the unchanged **10 December 2026 at 21:51 SAST** acceptance deadline.

Only newly observed model candidates after the freeze can open a simulated position. A trigger candle/side is not issued twice. Entry uses the newly observed quote plus assumed slippage; protection is simulated. Quotes are read from the matching configured demo account. The order-send API is disabled in the worker. It never creates an execution request or broker position.

Pending simulated positions advance through broker bid/ask tick history, with fees/slippage, stop, target, break-even, trailing, stale and maximum-hold exits. Checkpoints preserve last processed tick identity across resume, including different quotes at the same millisecond. Future and pre-entry ticks are ignored. Missing tick windows do not fabricate an exit. Gaps longer than 120 seconds mark the case incomplete, excluding it from qualification counts. This continuity screen is not proof of actual fill quality or complete broker tick history.

Two prospective stages of 30 complete paper cases use the same review criteria. The dashboard shows both counters. Sixty total recorded cases end collection for review even if some have incomplete tick evidence; insufficient complete evidence cannot pass. No future timing or minimum sample count is guaranteed. A paper pass remains a review requirement and cannot activate orders automatically.

## Operation and limits

The main status's `smc_composite.validation` exposes read-only paper progress. The native UI and backend were restarted to load the progress display. Existing paper, natural-lifecycle, learner and confidence-penalty observers retain their own hypotheses and journals.

The parent supervisor passes an absolute authoritative storage path on future worker launches; it does not let a frozen-source working directory choose a different storage tree. The worker's explicit run-directory argument always identifies its own checkpoint. A damaged manifest, input, source snapshot or checkpoint stops for review instead of resetting evidence.

Local commands use the active frozen source:

```powershell
.\.venv\Scripts\python.exe storage/smc_validation/frozen_20261113_v2/frozen_source/tools/smc_validation.py history --run-dir storage/smc_validation/frozen_20261113_v2
```

Do not launch another paper worker while its watch lock is held. The supervisor handles it without Codex credits. Historical output is `history.json`/`history.sha256`; prospective output is `paper_status.json` plus the signed `paper_checkpoint.json`. Nothing in this validation establishes a natural broker entry/protection/exit or permissions for real-money trading.

## Software and operational verification

**79 focused checks passed**, covering causal historical-frame selection, quote-side exits and assumed costs, duplicate millisecond quotes, pre-entry/future ticks, incomplete tick evidence, sample minimums, supervision locks/deadlines, authoritative storage, shared progress answers and existing SMC/timeframe/research behavior. Report: `docs/diagnostics/smc_validation_20261113.xml` (local diagnostic).

The supervised frozen paper worker was observed running with an empty stderr log and a fresh `collecting_paper` report. At 21:08 SAST the dashboard's shared research API and both typed/voice Ask Atlas reported **0/30 first-stage cases, 0/30 validation cases, no pending paper position**, with no broker authority. Ask “How is the SMC validation doing?” for current counters. Original paper and natural-lifecycle observers remained active.

## Completed historical result

All three periods recorded **zero qualifying trades**. Development, validation and holdout therefore failed the minimum evidence screen; mean return and profit factor are undefined, not zero-win-rate estimates. The model has not qualified for a bounded broker demo trial.

The replay accounted for 35,607 windows after warmup/outcome-tail handling:

| Decision result | Windows |
|---|---:|
| Input/outcome continuity gap | 7,371 |
| Session or close buffer | 10,035 |
| Chronological split boundary purge | 23 |
| Higher-timeframe agreement missing | 15,156 |
| Premium/discount location rejected | 2,942 |
| No reclaimed sweep | 63 |
| No qualifying confirmed pre-sweep structure | 12 |
| Displacement/structure shift absent | 5 |

Only **80** windows passed both higher-timeframe direction and premium/discount into the remaining pattern checks; none completed the sequence. This supports the narrower inference that this combined specification is highly restrictive in the inspected sample. It does not establish that every rejected opportunity was worthwhile or that a particular relaxed replacement is profitable.

The exact rules remain frozen. No revision was selected using this holdout and no order authority was enabled. Future paper stages remain 0/30 + 0/30 at completion of this work. An alternative confluence/location design would need a separately declared hypothesis and new validation rather than treating this failed run as proof or silently retuning its rules.
