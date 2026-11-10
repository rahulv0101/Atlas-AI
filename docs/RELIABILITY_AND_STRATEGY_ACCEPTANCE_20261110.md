# Reliability repairs and trading acceptance

The live backend has scoped automatic-sleep protection and prospective execution-cost recording. Historical strategy work completed without a qualifying replacement. The natural-lifecycle observer remains active. Profitability, natural broker acceptance and the cause of the earlier native fault are not declared resolved.

## Delivered reliability repairs

`atlas_ai.runtime_power.live_power_guard` acquires `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` only around the live worker, on its main thread. It restores the prior thread request on normal exit or Python exception; Windows removes the request when the process ends. It changes neither the Windows power plan nor display, manual sleep or lid-close policy. Set `ATLAS_PREVENT_IDLE_SLEEP=0` to disable it. A per-process JSON record under `storage/runtime_power` records acquisition/release/failure, so a short-lived duplicate worker cannot overwrite another worker's evidence. An active record from a terminated process must not be treated as a current request.

Windows recorded sleep events today at 10:47 UTC and 14:57 UTC. The deployed worker, PID 15468, successfully acquired the native request at 17:16:38 UTC. The `powercfg /requests` inspection required administrator privileges and could not independently confirm the OS request list; successful return from the native API and the live process record were verified. Explicit/manual sleep can still interrupt Atlas.

Speech outputs previously created a permanently waiting audio-bridge thread on construction even if never used. Bridge startup is now lazy and protected by a lock; the first queued utterance starts exactly one sender. Routing, synthesis and spoken content are unchanged. This removes unused workers, but it is not evidence that those threads caused the earlier native fault.

Native fault logs now include interpreter architecture, MT5/numpy/pandas/pythonnet/pywebview versions and an orderly Python-exit marker. An absent marker alone is not proof of a crash, since forced termination bypasses cleanup. Normal fatal-fault handling remains enabled without adding periodic all-thread stack walking. Existing Windows records identify three Python access violations on November 9 in `python312.dll`; the current event query found no later Python Application Error 1000 record. Earlier symbol mapping points into traceback/line-number handling but does not establish the original corruption cause. No runtime upgrade or speculative native fix was applied.

## Execution cost evidence

Entry dispatches and position-close paths now record requested/fill prices, side, available bid/ask quote, raw broker quote clock, response identifiers, response status and elapsed dispatch time. Raw broker time is explicitly labelled raw. The observation wrapper calls the original sender once and preserves its return object or exception. Evidence-write failure cannot resubmit an order or change execution success. It records no credentials.

`tools/execution_quality_report.py` reports signed adverse request-to-fill differences, sample counts, timing distributions and missing evidence. Rejections, submitted-only responses and unknown outcomes cannot become measured fills. Labelled diagnostic entries are excluded from the measurement aggregate; an exit count alone is never proof of a natural trade. Quotes and response prices measure request-to-fill difference, not venue-only slippage. No measured value automatically changes a frozen experiment or risk/execution policy.

At deployment there were zero measured fills. The report therefore returns `awaiting_measured_fills` and null cost estimates, rather than claiming zero slippage. A fresh broker fee query still returned ten deal samples and zero observed commission/fee estimate; manual deals are fee evidence only, and this remains a small sample with approximate currency conversion.

```powershell
.venv\Scripts\python.exe tools/execution_quality_report.py --storage-dir storage --output docs/diagnostics/execution_quality_CURRENT.json
```

## Completed candidate work

The larger audit evaluated eighteen fixed built-in strategy/distance/confirmation comparisons on 32,453 closed M1 bars. Training covered ten trading days from October 12; holdout covered ten trading days from October 26. Its minimum was thirty cases per training, holdout and eventual forward stage. All eighteen had negative configured-cost mean returns in both historical periods. No training winner qualified. ATR-point conversion alone did not establish an edge.

Costs materially affect the results. Corrected immediate momentum averaged +0.065R gross, -0.003R after spread/observed fees and -0.123R with the assumed slippage charge in training. Holdout was +0.129R, +0.071R and -0.027R respectively. These three views reprice the same paths selected under configured costs; they do not simulate different cost-dependent daily stopping paths. Thus the assumed slippage must not be described as measured, and a positive gross result must not be described as executable profitability.

A second, predeclared exploratory experiment applied a fixed raw-score floor of 0.55 to six strategies and two corrected-distance entry variants. It reused the saved past-only signal cache and unchanged simulator; it did not scan thresholds or change the live selector. All twelve comparisons remained negative after configured costs in both historical periods. For example, immediate EMA improved from -0.275R to -0.092R in training, but remained -0.115R in the historical validation period. Higher raw score alone did not solve candidate quality.

Those historical periods were already inspected by this second experiment, so none of its results is a new blind holdout or permission for promotion. The latest chart-invented candidate also had negative training results despite two positive holdout cases and a positive average across six forward cases; it remains unqualified. No further parameter search was used to manufacture a passing model. Future candidate work needs a new predeclared hypothesis and genuinely subsequent evidence.

Local artifacts: `storage/cost_research/run_20261110_extended`, `storage/cost_research/score_floor_20261110`, and `storage/strategy_research/state.json`. Raw account-derived files remain local. Strategy selection, risk limits, trading sessions and execution authority are unchanged.

## Broker lifecycle and operation

Deployment used a matching, flat demo preflight, stopped only the backend and restarted through the normal system launcher. Startup returned SUCCESS at 17:17:22 UTC; the frontend and both read-only observers remained running. Deployment sent no broker orders. The post-restart API responded with a current higher-timeframe alignment blocker, and the natural observer confirmed broker/history availability with no verified natural lifecycle yet.

The existing natural observer requires a guarded autonomous decision linked to broker entry, observed protection, balanced exit fills and a broker-flat position. Manual trades and forced diagnostics are excluded. The previous labelled diagnostic checks broker mechanics but cannot satisfy this acceptance condition. An entry cannot be forced while retaining the meaning of a natural strategy-selected trade.

The frozen paper observer has forty-one potentially overlapping outcomes, zero training-qualified candidates and no order authority. One day or a sum across comparisons is insufficient evidence of a sustainable edge. Both existing observation windows are bounded; their eventual completion is not automatic qualification.

## Validation

The initial execution/power regression passed 63 checks. The additional observation, speech, report, native-diagnostic and watchdog suite passed 38. The final focused native/speech/power/report suite passed ten. The full isolated system suite passed 1,870 tests in 462.90 seconds with no native crash. Broker mutations and process termination were blocked by test fixtures, and execution telemetry was replaced with an isolated sink to prevent synthetic fills polluting production measurements. The full run collected tests before the final speech-lifecycle tests were added; those two tests also passed in the focused runs. XML and durable progress are local under `docs/diagnostics/system_completion_20261110`.

Unproven outcomes remain explicit: a profitable candidate after realistic costs, a natural autonomous broker lifecycle, and the causal explanation of the historical native fault. These require evidence beyond passing software checks.
