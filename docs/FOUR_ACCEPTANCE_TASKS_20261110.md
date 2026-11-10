# Execution, costs, crash diagnosis and prospective strategy evidence

Completed a fresh broker mechanics/cost diagnostic and isolated a reproducible audit-crash mechanism. A fixed prospective paper experiment and the natural-lifecycle observer are running. A profitable trading edge and a natural strategy-selected broker lifecycle are not declared achieved.

## Measured demo execution

On November 10 at 21:27 SAST, one explicitly labelled 0.01-lot demo diagnostic passed the existing account, quote, execution, session and risk gates. The estimated protective-stop loss was R24.80 against the existing R603.54 risk budget. There was exactly one entry dispatch and one position-specific close. Broker readback confirmed protective SL/TP, balanced opposite fills and a flat position. The complete diagnostic took 1.234 seconds and lost R5.79 in demo funds.

The recorder captured both fills. Entry matched its requested price. Exit was one broker point worse than its request, approximately 0.024805 basis points adverse. Quote spread was 34 points. Dispatch times were approximately 415 ms and 381 ms. The mean signed request-to-fill difference across the two fills was approximately 0.012402 basis points; this is a description of two correlated observations, not a calibrated future slippage estimate.

A diagnostic-role context now follows the adapter's exit path, keeping the exit measurement in the same diagnostic category as the entry. The report exposes diagnostic and strategy observations separately. Submitted/rejected/unknown responses cannot become measured fills. Diagnostic results cannot become natural trading proof or strategy performance. No trading request, retry, risk limit or execution authority changes through this evidence role. The research stress charge of 1.5 basis points remains unchanged; two demo fills do not establish live-account costs.

Local evidence: `measured_cost_demo_diagnostic_20261110.json`, `measured_demo_cost_report_20261110.json`, the prospective dispatch journal and refreshed broker fee profile under `docs/diagnostics`/`storage`. Raw account-derived evidence remains local.

## Audit-crash diagnosis and mitigation

The original temporary audit runner enabled `faulthandler.dump_traceback_later(60, repeat=True)`. Earlier Windows fault offsets mapped into `_Py_DumpTraceback` and `PyCode_Addr2Line`. CPython documents races when native asynchronous fault-handler code walks thread/frame state concurrently with thread activity: [issue 116008](https://github.com/python/cpython/issues/116008), [timer-thread reproducer 131580](https://github.com/python/cpython/issues/131580).

A bounded local subprocess experiment now reproduces this failure without importing Atlas, pandas, MT5 or any broker module. In the confirmed nine-child run, all three asynchronous-timer children terminated with access violation `0xc0000005`; all three plain and all three Python-thread-controlled snapshot children completed successfully. Successful controls completed real frame-allocation/thread-churn workloads with zero worker exceptions. An earlier independent nine-child run produced the same pattern. Child PID/trace records distinguish these intentional diagnostic crashes from live-backend faults. Windows error dialogs were suppressed only within the isolated probe children.

This provides strong causal evidence for the instrumented audit failure mechanism, consistent with the recorded native functions. It does not prove that every historical native event had the identical cause. The legacy temporary runner was backed up locally and replaced with a wrapper invoking the safe, tracked `tools/run_system_audit_tests.py`. That runner uses durable Python progress hooks and leaves normal fatal tracing enabled. A regression test rejects reintroduction of the asynchronous timer or disabling fatal tracing. The deliberately hazardous reproducer is a bounded, explicitly invoked tool, never an automatic runtime sampler.

The full suite through the repaired entry point passed 1,902 tests in 414.70 seconds with no native crash. This run began before the subsequent higher-timeframe arithmetic refactor; final focused suites cover that later change and the prospective worker. No interpreter/dependency upgrade or speculative memory patch was applied to the live environment.

## Bias arithmetic repair

The live higher-timeframe classifier accepted 25–29 closes but divided its slow-window sum by thirty. Twenty-five identical 100-valued closes therefore appeared bullish because the slow mean became 83.33. The shared classifier now requires a complete thirty-close window and finite positive prices, returning unknown otherwise. For valid data it preserves the existing fast-ten/slow-thirty arithmetic and 0.02% directional band. This repairs insufficient-data handling; it does not tune entry thresholds or change strategy/risk policy.

## New prospective strategy protocol

One new paper-only hypothesis is frozen: the existing M15 pullback template, corrected ATR-point geometry, strategy-bar stale-exit timing, completed-H1 bias agreement and the same modeled costs. Its motivation comes from previously inspected historical work, so historical outcomes are not rebranded as independent validation. Only subsequently available signals count.

The first thirty subsequent completed paper cases and the following thirty form separate successive evidence stages. Each requires at least two trading days, positive modeled mean, PF at least 1.1 (or all wins) and drawdown no greater than 6R. Counts cannot be pooled to make a stage pass. A passing experiment only becomes ready for research review; `broker_eligible` and auto-promotion remain false. The simulator omits several live gates and does not establish actual broker fills or account profitability.

The protocol freezes source/dependency hashes, account/server/symbol/magic scope, broker timezone, simulator settings, clock units and cost assumptions. Checkpoints hash both collected candles and saved signals; missing or changed integrity metadata fails closed. It appends only new closed bars and retains original observations. The higher-timeframe filter cannot read an unfinished H1 bar. Duplicate watcher locks and bounded history/runtime prevent uncontrolled collection or automatic retraining. An initial zero-outcome bootstrap was retired before final account/clock freezing; its artifacts remain separate and contribute no cases. An exact local snapshot of the indexed Python sources preserves the final experiment independently of future repository edits; required hashes, snapshot imports and configured account scope were verified. No credentials were copied. The current watcher continues on the validated current implementation and will fail closed if those files change; the snapshot is available for an explicit compatible continuation after it stops.

The active experiment is `storage/prospective_pullback/frozen_20261110`, frozen on November 10 at 21:51 SAST. Its first live fetch and restart passed integrity checks with zero completed future outcomes, as expected. The seven-day paper window ends approximately November 17 at 21:53 SAST; it may collect fewer than sixty cases. Ending the window does not establish qualification. After it has stopped, explicit continuation can retain the frozen rule and evidence:

```powershell
.venv\Scripts\python.exe storage/prospective_pullback/frozen_20261110/frozen_source/tools/prospective_pullback.py watch --run-dir storage/prospective_pullback/frozen_20261110 --hours 168
```

Do not run a duplicate watcher. Separately, the existing natural-lifecycle observer continues through its own bounded window. It still requires a real guarded strategy decision, matched entry, observed protection, balanced exit and flat broker position. The diagnostic above remains excluded; that natural acceptance is still pending.

## Deployment and validation

The diagnostic/cost regression passed 68 checks. The crash-isolation/safe-runner checks passed four. The final focused suite passed 54, and seven final prospective/bias cases passed after account/timezone freezing and duration reporting. Tests cover actual simulated resume, historical-signal exclusion, future-H1 isolation, manifest/data tampering, complete bias windows and separation of diagnostic measurements from natural evidence.

After a matching flat-demo preflight, only the backend was restarted using the configured launcher spawn. The frontend and existing observers stayed running. The new backend acquired scoped sleep protection and returned fresh decisions. The new paper watcher returned fresh closed-bar timestamps, zero orders and false broker eligibility. No experimental strategy was activated. Deployment sent no broker orders beyond the separately labelled single diagnostic.
