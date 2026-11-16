# M5 entry readiness repair

Atlas remains configured for M5 entries with native Daily/H4/H1/M15 confluence and all six enabled built-in strategies. This change repairs a data-availability bug, not strategy direction, risk limits or broker permission.

On Monday, the old elapsed-time check rejected the latest closed Friday broker D1 candle after the weekend. This made Daily `unknown` even though the current Monday daily candle and intraday data were present. Daily freshness now recognizes only that specific weekend gap: it requires Monday evaluation, Friday's candle ending at Saturday broker midnight, and a current forming Monday D1 bar whose timestamp is not in the future. Only closed candles contribute prices or directional bias. Missing Friday data, a feed without the current Monday bar, future-only timestamps, and older stale history still fail. Broker-local calendar arithmetic handles DST weekends.

The repaired direct broker check returned available SELL evidence on D1/H4/H1/M15. This establishes data availability, not trade approval. Existing all-four directional confluence, timing, volatility, sizing and execution gates remain active. The backend was refreshed only after verifying that the matching demo account had no open positions, preserving its launch arguments and trading policy.

The current fixed volatility cutoff is shared across timeframes; a separately validated M5 calibration is still unavailable. The earlier ATR-unit research also failed to establish a qualifying, affordable correction at the nominal risk budget. No unqualified research strategy or wider-risk setting was activated.

Earlier frozen historical reports retain their original daily-freshness implementation and cannot establish repaired-version performance. They are preserved. Current-version performance claims require a new frozen replay and independent forward evidence; a natural broker lifecycle remains separate.

Validation: 110 focused regression checks passed across native top-down confluence, M5 replay, historical policy, execution audit and SMC research. New cases cover Monday weekend recovery, broker DST, exclusion of forming prices, absence of current-feed proof, future timestamps, missing Friday data and a feed stuck at Friday through Tuesday.
