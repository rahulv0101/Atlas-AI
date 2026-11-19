# Visible MT5 timeframe cycle

AtlasChartCycle is installed and running as an MT5 Service on the existing
XAUUSD chart. It cycles D1, H4, H1, M15, M5 with five seconds per frame and a
300-second cycle interval, then rests on M5. Each change waits for actual
ChartPeriod readback, enables chart autoscroll and navigates to current candles.
A screenshot verified current-day M5 after the complete native sequence.

The service is display-only. It contains no order, position-management, login,
DLL or network functions, and its individual Allow Algo Trading checkbox was
unchecked at activation. Existing Atlas execution permissions were untouched.
It binds exactly one XAUUSD chart, refuses charts with an attached Expert Advisor,
and holds an exclusive common-file lock to prevent a duplicate service. Changed
symbol, closed chart or failed switch stops the cycle. Stop cleanup requests M5
on the still-valid chart. Chart navigation does not change trading thresholds.

Source: mt5/AtlasChartCycle.mq5. Local installation is the configured terminal's
MQL5/Services/AtlasChartCycle.mq5 plus its locally compiled ex5. MetaEditor compiled
with zero errors and zero warnings. The compiled binary is not committed.
To stop: MT5 Navigator > Services > AtlasChartCycle > instance > Stop.
To resume: right-click that saved instance > Start. Keep individual Algo Trading
disabled. Do not attach an EA merely to cycle the chart.

Native status is overwritten in MT5 Common/Files/AtlasChartCycle_status.json.
It exposes actual timeframe, confirmed sequence, heartbeat, display_only=true
and broker_authority=false. Treat old status as stale, never as an execution
approval. The portable verification snapshot excludes chart/account identifiers.

The initial safeguard incorrectly compared a null Expert Advisor name to an empty
string; StringLen now handles the no-EA case. First activation also exposed MT5
retaining historical viewport positions; the final service navigates to CHART_END.

This visual scan is separate from Atlas's closed-candle MT5 data collection.
It does not replace OHLC higher-timeframe analysis or prove that screenshot pixels
map to a specific market-data candle. Visual timing evidence remains advisory under
the prior correction. The service does not grant visual execution authority.

MetaQuotes documents that running Services reload at terminal startup:
https://www.mql5.com/en/docs/runtime/running
No Windows or MT5 restart was performed to test that persistence in this turn.
ChartSetSymbolPeriod is asynchronous, so readback is required:
https://www.mql5.com/en/docs/chart_operations/chartsetsymbolperiod

The trading backend, collector and paper evaluator were not restarted by this
installation. No order was submitted as part of chart cycling.
