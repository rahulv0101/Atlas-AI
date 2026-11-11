# Running a historical Atlas system audit

For the newer broker-unit guarded replay, use [guarded research](GUARDED_RESEARCH.md). The standard `atlas_ai.main backtest` command now routes there. The tool below is retained as a legacy comparison with its documented fixed-account-cost and partial-policy assumptions.

Run the historical engine and its separate timing-filter replay without using the live launcher:

```powershell
.venv\Scripts\python.exe tools/historical_system_audit.py --days 30 --output storage/system_backtest/new_run
```

The output directory must be new. The tool attaches to the configured matching demo terminal for historical data, saves only completed UTC M1 candles, validates the dataset, and records its checksum and source hashes. It disables order dispatch in its own process and runs with isolated storage and learning persistence disabled. It never resets the frozen prospective paper run or changes the running backend.

`progress.json` records the current phase. `report.json` contains the data window, enabled historical strategies, configured costs, complete core trade list and separate timing comparison. `candles.csv` permits inspection of the exact historical data used. Raw artifacts remain local because they can reveal broker-derived information.

The runner also archives its exact source, clears AI keys in the isolated settings and suppresses current external macro context in the timing lane. Sensitivity reporting checks the fixed timing-candidate stream with model costs, conservative stop-first handling and a greedy nonoverlapping subset. It checks reproduction of the original candle-direction outcomes. These sensitivities do not regenerate allocator/candidate decisions or enforce all live gates.

The core backtest applies the existing historical engine, including its configured evolved-strategy research, allocator and exit simulator. The timing lane applies the existing timing-discipline replay to the same saved candle snapshot. It does not relax timing rules. The two lanes are different models and must not be combined into one portfolio result.

These runs are **not complete historical reproductions of the live system**. In particular:

- Historical and live strategy inventories differ; the report lists the historical inventory and configured enabled strategies so gaps are visible.
- Live risk caps, sessions, sizing, higher-timeframe gates, performance filters, screenshots, macro evidence, Gemini advice and broker protection acknowledgements are not all replayed by the historical engine.
- Core costs are fixed account-return basis points. The timing comparison reports gross hypothetical paths that can overlap; its figures are not cost-adjusted executable portfolio returns.
- When both stop and target occur in the same candle, the historical simulator uses candle direction. Actual intrabar order is unknown.
- A fresh allocator and current parameters do not reconstruct the historical runtime state. Previously inspected data is not a blind holdout.

An engine backtest therefore cannot establish natural broker execution or replace either thirty-case prospective stage. A complete live-policy backtester would need additional historical adapters and explicit parity tests before its results could be described that way.

For independent software checks, run the isolated audit test runner:

```powershell
.venv\Scripts\python.exe tools/run_system_audit_tests.py --output-dir docs/diagnostics/new_system_tests
```

It uses temporary storage, clears AI credentials in the test process and retains normal fatal fault handling. Its passing results establish tested software behavior, not profitability.
